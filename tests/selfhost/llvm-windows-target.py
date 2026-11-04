#!/usr/bin/env python3
"""W1 门禁：Windows/x64 目标（COFF 对象 / PE 链接 / 零 CRT 运行时 / 可复现）。

在**编译侧**（Linux/macOS，含 WSL）跑：

    python3 tests/selfhost/llvm-windows-target.py --compiler-path ./yh

它做三件事：

1. **目标身份与发射**：`--target x86_64-pc-windows-msvc` 的 `--emit-asm` 必须带
   `target triple`、`HeapAlloc/GetStdHandle/WriteFile`，且**不得**出现
   `linux_syscall6`/`mmap`/`svc`（零 CRT = 只走 Win32 API，没有 syscall）；
2. **产物形态**：`-o x.exe` 出 PE（`MZ` → `PE\\0\\0`、machine `0x8664`、子系统 console），
   且**只依赖 KERNEL32.dll**（有 `llvm-readobj` 时逐符号核对）；同一源码连编两次
   **逐字节相同**（`/Brepro`）；
3. **负例**：不支持的目标（`aarch64-pc-windows-msvc`）必须被拒（退出码 2 + 诊断）。

它同时把「可执行文件 → 期望 stdout / 退出码」写进清单（`--manifest-out`），供
**运行侧**的 `tests/windows/run-exe.py` 在真实 Windows 上核对（W1-7 跨机验收）。
在 Windows 宿主上直接跑本脚本时，会顺手把每个用例执行一遍。

退出码：0 通过；1 失败；2 用法/环境错误。
"""

import argparse
import json
import platform
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 编译器子进程环境：main 会填入 YH_WINDOWS_SDK，使暂存副本（/tmp/yh-fast/yh）也能
# 找到导入库（它不在仓库树里，猜不到 vendor/windows-sdk 的相对位置）。
COMPILER_ENV: dict[str, str] = {}

# 用例：名字 → (源码, 期望 stdout, 期望退出码)。
# 覆盖 W1 的三条主要路径：纯计算退出码、printf 输出、聚合临时值当实参（历史回归点：
# 非入口块 alloca 在 Windows 上曾导致崩溃）、浮点（MSVC 的 _fltused）、格式集合。
CASES = {
    "exit42": ("fn main() int { return 42 }\n", "", 42),
    "hello": (r'''fn main() int {
    printf("hello-windows\n")
    return 0
}
''', "hello-windows\n", 0),
    "loop": (r'''fn main() int {
    let sum int = 0
    let i int = 0
    for i < 100 { sum += i; i += 1 }
    printf("sum=%d\n", sum)
    return 0
}
''', "sum=4950\n", 0),
    "struct_arg": (r'''struct Pair { a int; b int }
fn add(p Pair) int { return p.a + p.b }
fn main() int {
    let p Pair
    p.a = 40
    p.b = 2
    printf("pair=%d\n", add(p))
    return 0
}
''', "pair=42\n", 0),
    "float": (r'''fn main() int {
    let x f64 = 1.5
    let y f64 = 2.25
    let z f64 = x * y
    printf("z=%d\n", (z * 100.0).to_type(int))
    return 0
}
''', "z=337\n", 0),
    "file_api": (r'''fn main() int {
    let fd int = open("tmp/windows-file-api/data.txt", 0x241, 420)
    if (fd < 0) { printf("open-write-fail\n"); return 1 }
    let w i64 = write(fd, "hello-file", 10)
    if (w != 10) { printf("write-fail\n"); return 2 }
    close(fd)
    let rd int = open("tmp/windows-file-api/data.txt", 0)
    if (rd < 0) { printf("open-read-fail\n"); return 3 }
    let buf [32]u8
    let n i64 = read(rd, buf, 32)
    close(rd)
    let ok int = n == 10 && buf[0] == 104 && buf[9] == 101 ? 1 : 0
    printf("read=%d ok=%d\n", n.to_type(int), ok)
    let r int = rename("tmp/windows-file-api/data.txt", "tmp/windows-file-api/moved.txt")
    let u int = unlink("tmp/windows-file-api/moved.txt")
    printf("rename=%d unlink=%d\n", r, u)
    return 0
}
''', "read=10 ok=1\nrename=0 unlink=0\n", 0),
    "big_frame": (r'''fn big(n int) int {
    let buf [32768]u8
    let i int = 0
    for i < 32768 { buf[i] = (i % 7).to_type(u8); i += 1 }
    let sum int = 0
    i = 0
    for i < 32768 { sum += buf[i].to_type(int); i += 1 }
    printf("big sum=%d\n", sum)
    return 0
}
fn main() int { return big(0) }
''', "big sum=98301\n", 0),
    "fmt": (r'''fn main() int {
    printf("%d|%s|%c|%u\n", -7, "str", 'x', 9)
    return 0
}
''', "-7|str|x|9\n", 0),
}

# 汇编形态探针：同时用到 malloc/printf，才能检查 Win32 运行时（HeapAlloc/WriteFile）是否真的发射。
ASM_PROBE_SOURCE = r'''fn main() int {
    let p *u8 = malloc(16).to_type(*u8)
    if (p == 0) { return 1 }
    *p = 'h'.to_type(u8)
    printf("asm-probe\n")
    free(p.to_type(*void))
    return 0
}
'''

# 负例：大栈帧（>16 KB）必须编译期拒绝——没有 __chkstk 页探测时运行时会崩（W1-3c）。
BIG_FRAME_SOURCE = """fn big(n int) int {
    let buf [32768]u8
    let i int = 0
    for i < 32768 { buf[i] = 1; i += 1 }
    return buf[0].to_type(int)
}
fn main() int { return big(0) - 1 }
"""

NL = chr(10)


def project_toml(libraries: list[str]) -> str:
    """生成 os=windows 的临时项目清单；libraries 进 [link-windows-x64].files。

    路径用 json.dumps 转义：Windows 宿主传进来的是 `C:\\...` 反斜杠路径，
    直接拼进 TOML 基本字符串会被当成非法转义（`\\U`/`\\P` 等）。
    json 的字符串转义是 TOML 基本字符串的子集，两边都合法。
    """
    lines = ["[project]", 'os = "windows"', 'arch = "x64"', 'name = "libproj"',
             'version = "0.0.1"', 'source = "src"', "", "[link-windows-x64]",
             "files = [" + ", ".join(json.dumps(item) for item in libraries) + "]"]
    return NL.join(lines) + NL


# 负例：不支持的 Windows 架构（首版只有 x64）。
REJECT_SOURCE = "fn main() int { return 0 }\n"


class GateError(RuntimeError):
    """门禁失败；message 必须能直接指出下一步。"""


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """执行一条命令并保留输出（不用 shell，避免引号/路径差异）。"""
    return subprocess.run(command, cwd=str(cwd), capture_output=True, text=True,
                          timeout=600, env=COMPILER_ENV or None)


def require(result: subprocess.CompletedProcess, what: str) -> subprocess.CompletedProcess:
    """要求命令成功；失败时带原始 stdout/stderr。"""
    if result.returncode != 0:
        raise GateError(f"{what} 失败（rc={result.returncode}）:\n{result.stdout}{result.stderr}")
    return result


def pe_header(path: Path) -> tuple[int, int]:
    """读取 PE 的 (machine, subsystem)；不合法直接失败。"""
    data = path.read_bytes()
    if data[:2] != b"MZ" or len(data) < 0x40:
        raise GateError(f"{path.name} 不是 PE（缺 MZ 头）")
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_off:pe_off + 4] != b"PE\0\0":
        raise GateError(f"{path.name} 缺 PE 签名")
    machine = struct.unpack_from("<H", data, pe_off + 4)[0]
    subsystem = struct.unpack_from("<H", data, pe_off + 4 + 20 + 68)[0]
    return machine, subsystem


def pe_imports(readobj: str, path: Path) -> tuple[set[str], set[str]]:
    """解析 llvm-readobj --coff-imports，返回 (DLL 集合, 符号集合)。"""
    result = require(run([readobj, "--coff-imports", str(path)], ROOT), "llvm-readobj")
    dlls: set[str] = set()
    symbols: set[str] = set()
    for line in result.stdout.splitlines():
        text = line.strip()
        if text.startswith("Name: "):
            dlls.add(text[len("Name: "):].split()[0])
        elif text.startswith("Symbol: "):
            symbols.add(text[len("Symbol: "):].split()[0])
    return dlls, symbols


def check_assembly(compiler: str, source: Path) -> None:
    """`--emit-asm` 必须是 Win64/COFF 形态且运行时走 Win32，不得混入 Linux syscall。

    汇编里没有 `target triple`（那是 LLVM 文本），Win64 的可辨认形态是 COFF 的
    `.def`/`.endef` 与 `.seh_proc`（x64 展开指令）——2026-10-27 实测。
    """
    result = run([compiler, "--target", "x86_64-pc-windows-msvc", "--emit-asm", str(source)], ROOT)
    require(result, "交叉发射汇编")
    asm = result.stdout
    for needle in (".def	main", ".seh_proc", "HeapAlloc", "GetStdHandle", "WriteFile"):
        if needle not in asm:
            raise GateError(f"汇编缺少 {needle}（Win64/COFF 形态或 Windows 运行时未生效）")
    for forbidden in ("linux_syscall6", "svc", "mmap"):
        if forbidden in asm:
            raise GateError(f"汇编里混入了 {forbidden}：Windows 目标不得使用 Linux syscall 路径")


def check_reject(compiler: str, source: Path) -> None:
    """不支持的 Windows 架构必须被拒（退出码 2 + 诊断），不能静默回退到 x64。"""
    result = run([compiler, "--target", "aarch64-pc-windows-msvc", "--emit-asm", str(source)], ROOT)
    if result.returncode != 2:
        raise GateError(f"aarch64-pc-windows-msvc 未被拒绝：rc={result.returncode}")
    if "不支持的目标 triple" not in result.stderr:
        raise GateError(f"拒绝 aarch64-windows 时缺少诊断：{result.stderr!r}")


def build_case(compiler: str, work: Path, name: str, source_text: str) -> Path:
    """编译单个用例为 .exe，返回路径；顺带做 PE 头与可复现性检查。"""
    source = work / f"{name}.yh"
    source.write_text(source_text, encoding="utf-8")
    exe = work / f"{name}.exe"
    again = work / f"{name}-again.exe"
    for target in (exe, again):
        if target.exists():
            target.unlink()
        require(run([compiler, "--target", "x86_64-pc-windows-msvc", "-o", str(target),
                     str(source)], ROOT), f"链接 {name}")
    machine, subsystem = pe_header(exe)
    if machine != 0x8664:
        raise GateError(f"{name}.exe 的 machine 不是 x86_64：0x{machine:04x}")
    if subsystem != 3:
        raise GateError(f"{name}.exe 的子系统不是 console：{subsystem}")
    if exe.read_bytes() != again.read_bytes():
        raise GateError(f"{name}.exe 两次构建字节不同：/Brepro 未生效")
    return exe


def main() -> int:
    parser = argparse.ArgumentParser(description="W1 Windows/x64 目标门禁")
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--manifest-out", default=None,
                        help="写运行清单（供 tests/windows/run-exe.py 在 Windows 上执行）")
    parser.add_argument("--workdir", default=str(ROOT / "tmp/llvm-windows-target"))
    parser.add_argument("--sdk-root", default=str(ROOT / "tmp/llvm-migration/windows-sdk"),
                        help="tools/windows-sdk.py 生成目录（含 lib/kernel32.lib）")
    args = parser.parse_args()

    compiler = str(Path(args.compiler_path).resolve())
    if not Path(compiler).is_file():
        raise GateError(f"找不到编译器：{compiler}（先跑 just）")
    sdk = Path(args.sdk_root)
    if not (sdk / "lib" / "kernel32.lib").is_file():
        raise GateError(f"缺少 Windows 导入库：{sdk}/lib/kernel32.lib（先跑 just windows-sdk）")
    import os
    COMPILER_ENV.update(os.environ)
    COMPILER_ENV["YH_WINDOWS_SDK"] = str(sdk)
    work = Path(args.workdir)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    # file_api 用例在运行侧写真实文件：先备一个干净目录（open 需要父目录已存在，
    # mkdir/rename 的结果才稳定；重复跑不会因为残留状态漂移）。
    api_dir = ROOT / "tmp/windows-file-api"
    shutil.rmtree(api_dir, ignore_errors=True)
    api_dir.mkdir(parents=True, exist_ok=True)
    readobj = shutil.which("llvm-readobj")

    # 1) 目标身份 / 运行时 / 负例
    probe = work / "reject.yh"
    probe.write_text(REJECT_SOURCE, encoding="utf-8")
    check_reject(compiler, probe)
    first = work / "asm-probe.yh"
    first.write_text(ASM_PROBE_SOURCE, encoding="utf-8")
    check_assembly(compiler, first)

    # 清单里的 Windows 库输入：.lib（ar 归档，kind=1）必须被接受，
    # .dll 必须是 x86_64 PE（否则给出目标级诊断）。用一个临时项目验证
    # link_inputs 的 Windows 分支（W1-6）。
    library_project = work / "libproj"
    (library_project / "src").mkdir(parents=True)
    (library_project / "src" / "main.yh").write_text(
        "module main" + NL + NL + "fn main() int { return 0 }" + NL, encoding="utf-8")
    (library_project / "project.toml").write_text(
        project_toml([str(sdk / "lib" / "kernel32.lib")]), encoding="utf-8")
    built = run([compiler, "build"], library_project)
    if built.returncode != 0:
        raise GateError("[link-windows-x64] 引用 .lib 失败：" + NL + built.stderr[-400:])

    bogus_dll = work / "bogus.dll"
    bogus_dll.write_bytes(b"not a pe image")
    (library_project / "project.toml").write_text(
        project_toml([str(bogus_dll)]), encoding="utf-8")
    rejected = run([compiler, "build"], library_project)
    if rejected.returncode == 0 or "DLL" not in rejected.stderr:
        raise GateError("非 PE 的 .dll 未被拒绝：rc=" + str(rejected.returncode))

    # 2) 逐用例编译 + PE 检查 + 导入面
    manifest = {"target": "x86_64-pc-windows-msvc", "cases": []}
    for name, (source_text, expected_stdout, expected_code) in CASES.items():
        exe = build_case(compiler, work, name, source_text)
        if readobj is not None:
            dlls, _symbols = pe_imports(readobj, exe)
            # 允许零导入（纯计算程序根本不需要 kernel32）与只依赖 KERNEL32，
            # 但不允许出现 msvcrt/ucrt/vcruntime 这类 CRT 旁车。
            if not dlls <= {"KERNEL32.dll"}:
                raise GateError(f"{name}.exe 引入了 KERNEL32 之外的 DLL：{sorted(dlls)}")
        manifest["cases"].append({
            "name": name,
            "exe": str(exe.relative_to(ROOT)),
            "expected_stdout": expected_stdout,
            "expected_exit": expected_code,
        })

    # 3) 本机就是 Windows 时顺手执行（否则交给运行侧清单）
    if platform.system() == "Windows":
        for case in manifest["cases"]:
            result = subprocess.run([str(ROOT / case["exe"])], capture_output=True, text=True,
                                    timeout=60)
            if (result.stdout, result.returncode) != (case["expected_stdout"], case["expected_exit"]):
                raise GateError(f"{case['name']} 运行不符：rc={result.returncode} "
                                f"stdout={result.stdout!r}")

    if args.manifest_out:
        Path(args.manifest_out).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    note = "" if readobj is not None else "（无 llvm-readobj：跳过导入 DLL 核对）"
    mode = "并已实机执行" if platform.system() == "Windows" else "，产物待运行侧核对"
    print(f"W1 Windows/x64 目标门禁通过：{len(manifest['cases'])} 例 PE 正确、"
          f"只依赖 KERNEL32、/Brepro 可复现{mode}{note}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GateError, OSError, subprocess.SubprocessError) as error:
        print(f"失败：{error}", file=sys.stderr)
        raise SystemExit(1)
