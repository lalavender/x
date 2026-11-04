#!/usr/bin/env python3
"""W1-4 门禁：Windows SDK stub（文本 .def → COFF 导入库）的生成、确定性与导入面。

校验四件事，缺一不可：

1. **清单 ↔ .def 一致**：`vendor/windows-sdk/manifest.json` 的 `exports` 与
   `.def` 的 `EXPORTS` 段逐项相等，`def_sha256` 与文件内容相符（防「改了 def 忘同步」）；
2. **生成确定性**：同一 `.def` 生成两次到不同目录，逐字节相同（`.lib` 里的时间戳必须为 0，
   否则 `rb5`-类「同源不同字节」问题会从链接期冒出来）；
3. **符号面**：每个导出在导入库里同时有 `X`（跳板）与 `__imp_X`（IAT 槽），没有多余 `__imp_`；
4. **导入面与可运行性**：用 clang 出 COFF 对象 + `lld-link` 链接生成的最小程序
   - 只依赖 `KERNEL32.dll`（`llvm-readobj --coff-imports` 断言，防 msvcrt/ucrt 旁车）；
   - 在能运行 PE 的宿主（Windows）上**真的执行**，核对 stdout 与退出码；
   - 调用未导出函数（`Beep`）必须链接失败且不产出文件。

这一层特意写纯 Python：它不依赖 yh 是否能编 Windows 目标，所以可以在 W1-1 之前
独立跑绿（方案 §12 的 lane B）。

用法：
    python3 tests/selfhost/llvm-windows-sdk.py [--tool-root <LLVM bin>]

退出码：0 通过；1 失败（带原始输出）；2 用法错误。
"""

import argparse
import json
import platform
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

# Windows 控制台默认 GBK，中文/箭头会抛 UnicodeEncodeError；统一成 UTF-8 + 可替换。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "vendor/windows-sdk"
WORK = ROOT / "tmp/windows-sdk-gate"
SDK_TOOL = ROOT / "tools/windows-sdk.py"

# 探针程序：显式声明（不用 __declspec(dllimport)），与 yh 将要发射的 extern 调用形态一致。
PROBE_SOURCE = r"""
typedef void *HANDLE;
HANDLE __stdcall GetStdHandle(unsigned long);
int __stdcall WriteFile(HANDLE, const void *, unsigned long, unsigned long *, void *);
void __stdcall ExitProcess(unsigned int);

int main(void) {
    HANDLE out = GetStdHandle((unsigned long)-11);
    unsigned long written = 0;
    WriteFile(out, "windows-sdk-probe\n", 18, &written, 0);
    ExitProcess(5);
}
"""

# 负例：`Beep` 是真实 KERNEL32 导出、但不在我们的最小导出面里，必须链接失败
# （证明 stub 真的限定了边界）。注意别选 `Sleep`——它随 usleep 的零 CRT 实现
# 进入导出面（2026-11-02 复核），用它当负例会让门禁与清单互相矛盾。
NEGATIVE_SOURCE = r"""
void __stdcall Beep(unsigned long, unsigned long);
int main(void) { Beep(0, 0); return 0; }
"""


def run(command: list[str]) -> subprocess.CompletedProcess:
    """执行一条命令并保留输出，供失败信息使用（不用 shell，避免路径/引号差异）。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=600)


def require(command: list[str], what: str) -> subprocess.CompletedProcess:
    """执行必须成功的命令；失败时把原始 stdout/stderr 一起抛出。"""
    result = run(command)
    if result.returncode != 0:
        raise RuntimeError(f"{what} 失败：{' '.join(command)}\n{result.stdout}{result.stderr}")
    return result


def find_tool(name: str, tool_root: Path | None) -> str:
    """定位 LLVM 工具：--tool-root 优先，其次 PATH；缺了就报可操作的安装提示。"""
    if tool_root is not None:
        for candidate in (tool_root / name, tool_root / f"{name}.exe"):
            if candidate.is_file():
                return str(candidate)
    found = shutil.which(name)
    if found is None:
        raise RuntimeError(
            f"找不到 {name}：本门需要 LLVM 工具链（clang / lld-link / llvm-readobj / llvm-nm）。\n"
            f"  - Windows：scoop install llvm；\n"
            f"  - Debian/Ubuntu：apt-get install llvm-21 clang-21 lld-21（并建软链）；\n"
            f"  - 或用 --tool-root 指向 LLVM bin 目录。")
    return found


def pe_imports(readobj: str, path: Path) -> tuple[list[str], list[str]]:
    """从 llvm-readobj --coff-imports 里解析 (DLL 名列表, 符号列表)。"""
    output = require([readobj, "--coff-imports", str(path)], "llvm-readobj").stdout
    dlls: list[str] = []
    symbols: list[str] = []
    for line in output.splitlines():
        text = line.strip()
        if text.startswith("Name: "):
            dlls.append(text[len("Name: "):].split()[0])
        elif text.startswith("Symbol: "):
            symbols.append(text[len("Symbol: "):].split()[0])
    return dlls, symbols


def check_manifest_and_def(tool: dict, bundle: Path, out: Path, problems: list[str]) -> None:
    """清单 ↔ .def 一致性 + 生成产物自校验（复用 tools/windows-sdk.py 的 check）。"""
    try:
        found = tool["check"](bundle, out)
    except Exception as error:  # noqa: BLE001 - 统一转成门禁问题
        problems.append(f"check 抛出异常：{error}")
        return
    problems.extend(found)


def check_determinism(tool: dict, bundle: Path, problems: list[str]) -> None:
    """同一 .def 生成两次，逐字节相同才算过（含 identity.json）。"""
    first = WORK / "gen-a"
    second = WORK / "gen-b"
    for directory in (first, second):
        shutil.rmtree(directory, ignore_errors=True)
    tool["generate"](bundle, first)
    tool["generate"](bundle, second)
    manifest = tool["load_manifest"](bundle)
    for library in manifest["libraries"]:
        name = library["import_library"]
        left = (first / "lib" / name).read_bytes()
        right = (second / "lib" / name).read_bytes()
        if left != right:
            problems.append(f"{name} 两次生成字节不同（{len(left)} vs {len(right)} 字节）："
                            "导入库时间戳没有归零")
    left_identity = (first / "identity.json").read_bytes()
    right_identity = (second / "identity.json").read_bytes()
    if left_identity != right_identity:
        problems.append("identity.json 两次生成不同：生成器身份或哈希记录不稳定")


def check_tamper_guard(tool: dict, out: Path, problems: list[str]) -> None:
    """负例：只改 .def 不改清单 / 只改清单不改 .def，check 都必须失败。"""
    tampered = WORK / "bundle-tampered"
    shutil.rmtree(tampered, ignore_errors=True)
    shutil.copytree(BUNDLE, tampered)
    def_path = tampered / "def/kernel32.def"
    def_path.write_text(def_path.read_text(encoding="utf-8") + "    CreateFileA\n",
                        encoding="utf-8")
    if not tool["check"](tampered, out):
        problems.append("只改 .def 未同步 manifest，check 仍通过（防漂移失效）")

    tampered_manifest = WORK / "bundle-manifest-drift"
    shutil.rmtree(tampered_manifest, ignore_errors=True)
    shutil.copytree(BUNDLE, tampered_manifest)
    path = tampered_manifest / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["libraries"][0]["exports"] = data["libraries"][0]["exports"][:-1]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not tool["check"](tampered_manifest, out):
        problems.append("manifest.exports 与 .def 不一致，check 仍通过（导出面核对失效）")


def check_symbol_surface(tool: dict, out: Path, nm: str, problems: list[str]) -> None:
    """符号面：每个导出都有 __imp_X，且没有清单外的 __imp_ 符号。"""
    manifest = tool["load_manifest"](BUNDLE)
    for library in manifest["libraries"]:
        library_file = out / "lib" / library["import_library"]
        symbols = tool["symbol_surface"](library_file, nm)
        expected = {f"__imp_{name}" for name in library["exports"]}
        missing = sorted(expected - symbols)
        extra = sorted({s for s in symbols if s.startswith("__imp_")} - expected)
        if missing:
            problems.append(f"{library_file.name} 缺少导入符号：{missing}")
        if extra:
            problems.append(f"{library_file.name} 有清单外的导入符号：{extra}")


def check_link_probe(out: Path, tool: dict, tools: dict, problems: list[str]) -> None:
    """链接探针：最小程序只依赖 KERNEL32.dll；能跑就真的跑一遍；未导出符号必须链接失败。"""
    manifest = tool["load_manifest"](BUNDLE)
    library = out / "lib" / manifest["libraries"][0]["import_library"]
    probe_dir = WORK / "link-probe"
    shutil.rmtree(probe_dir, ignore_errors=True)
    probe_dir.mkdir(parents=True)

    source = probe_dir / "probe.c"
    source.write_text(PROBE_SOURCE, encoding="utf-8")
    obj = probe_dir / "probe.obj"
    require([tools["clang"], "--target=x86_64-pc-windows-msvc", "-O2", "-c",
             str(source), "-o", str(obj)], "clang 出 COFF 对象")
    exe = probe_dir / "probe.exe"
    require([tools["lld-link"], "/nodefaultlib", "/subsystem:console", "/entry:main",
             "/Brepro", f"/out:{exe}", str(obj), str(library)], "lld-link 链接探针")
    if not exe.is_file() or exe.read_bytes()[:2] != b"MZ":
        problems.append(f"探针产物不是 PE：{exe}")
        return
    dlls, symbols = pe_imports(tools["readobj"], exe)
    if sorted(set(dlls)) != ["KERNEL32.dll"]:
        problems.append(f"探针的导入 DLL 不是只有 KERNEL32.dll：{sorted(set(dlls))}")
    expected = {"GetStdHandle", "WriteFile", "ExitProcess"}
    if set(symbols) != expected:
        problems.append(f"探针的导入符号不符：实际 {sorted(set(symbols))} 期望 {sorted(expected)}")

    if platform.system() == "Windows":
        ran = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
        if ran.stdout != "windows-sdk-probe\n" or ran.returncode != 5:
            problems.append(f"探针运行结果不符：rc={ran.returncode} stdout={ran.stdout!r}")

    negative_source = probe_dir / "negative.c"
    negative_source.write_text(NEGATIVE_SOURCE, encoding="utf-8")
    negative_obj = probe_dir / "negative.obj"
    require([tools["clang"], "--target=x86_64-pc-windows-msvc", "-O2", "-c",
             str(negative_source), "-o", str(negative_obj)], "clang 出负例对象")
    negative_exe = probe_dir / "negative.exe"
    result = run([tools["lld-link"], "/nodefaultlib", "/subsystem:console", "/entry:main",
                  f"/out:{negative_exe}", str(negative_obj), str(library)])
    if result.returncode == 0:
        problems.append("调用未导出函数 Beep 仍然链接成功：stub 的导出面没有真正限定")
    if negative_exe.is_file():
        problems.append("负例链接失败却留下了输出文件（违反「不发布半产物」）")


def main() -> int:
    parser = argparse.ArgumentParser(description="W1-4 Windows SDK stub 门禁")
    parser.add_argument("--tool-root", default=None, help="LLVM bin 目录（可选）")
    args = parser.parse_args()
    tool_root = Path(args.tool_root) if args.tool_root else None

    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / "sdk"
    shutil.rmtree(out, ignore_errors=True)

    tool = runpy.run_path(str(SDK_TOOL))
    tools = {
        "clang": find_tool("clang", tool_root),
        "lld-link": find_tool("lld-link", tool_root),
        "readobj": find_tool("llvm-readobj", tool_root),
        "nm": find_tool("llvm-nm", tool_root),
    }
    tool["generate"](BUNDLE, out, None, str(tool_root) if tool_root else None)

    problems: list[str] = []
    check_manifest_and_def(tool, BUNDLE, out, problems)
    check_symbol_surface(tool, out, tools["nm"], problems)
    check_determinism(tool, BUNDLE, problems)
    check_tamper_guard(tool, out, problems)
    check_link_probe(out, tool, tools, problems)

    if problems:
        for problem in problems:
            print(f"失败：{problem}", file=sys.stderr)
        print("修复：检查 vendor/windows-sdk/{manifest.json,def/*.def} 与 LLVM 工具链",
              file=sys.stderr)
        return 1
    print("W1-4 门禁通过：def 与 manifest 一致、生成确定性、符号面限定、探针只依赖 "
          "KERNEL32.dll" + ("、PE 实机运行正确" if platform.system() == "Windows" else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
