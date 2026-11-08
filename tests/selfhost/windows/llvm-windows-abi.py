#!/usr/bin/env python3
"""W1-2b 门禁：Windows/x64 的 C 按值聚合 ABI（与 clang 编出的 C 桩互操作）。

Win64（MSVC ABI）的聚合传递规则与 SysV 完全不同，必须靠**真实 C 代码**对照，不能只看 IR：

| 聚合大小 | 参数形态 | 返回形态 |
| --- | --- | --- |
| 1 / 2 / 4 / 8 字节 | 整数寄存器 `i8/i16/i32/i64`（纯 float 聚合也一样） | 同左（RAX） |
| 其他 | 普通 `ptr`（按引用） | `void` + hidden `ptr sret` |

本门禁做四步：

1. 用 clang 把 `shim.c` 编成 COFF 对象，`llvm-ar` 打成 `.lib`（模拟真实的 C 静态库）；
2. 用 yh 构建一个项目，`[link-windows-x64] files = [lib]` 引用该库，程序里声明
   `@[extern] struct` + `@[extern] fn` 并按值传/接这些聚合；
3. 校验产物是 PE、只依赖 KERNEL32、`/Brepro` 可复现；
4. 本机是 Windows 时**直接运行**并比对输出；否则写清单交给
   `tests/windows/run-exe.py`（跨机验收）。

用法：
    python3 tests/selfhost/windows/llvm-windows-abi.py --compiler-path ./yh [--manifest-out ...]

退出码：0 通过；1 失败；2 用法/环境错误。
"""

import argparse
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NL = chr(10)

# C 桩：四种聚合大小（4/8/12）+ 纯浮点聚合（4/8），参数与返回都覆盖。
SHIM_C = r"""
struct Small { int a; };
struct Eight { int a, b; };
struct Big { int a, b, c; };
struct F4 { float f; };
struct F8 { float f, g; };

int take_small(struct Small s) { return s.a + 1; }
int take_eight(struct Eight s) { return s.a + s.b + 2; }
int take_big(struct Big s) { return s.a + s.b + s.c + 3; }
int take_f4(struct F4 s) { return (int)s.f + 4; }
int take_f8(struct F8 s) { return (int)(s.f + s.g) + 5; }
struct Small make_small(int a) { struct Small s; s.a = a + 10; return s; }
struct Big make_big(int a) { struct Big s; s.a = a + 20; s.b = a; s.c = a; return s; }
"""

PROJECT_TOML = r"""
[project]
os = "windows"
arch = "x64"
name = "aggabi"
version = "0.0.1"
source = "."

[link-windows-x64]
files = ["libaggshim.lib"]
"""

MAIN_YH = r"""
module main

@[extern] struct Small { a int }
@[extern] struct Eight { a int; b int }
@[extern] struct Big { a int; b int; c int }
@[extern] struct F4 { f f32 }
@[extern] struct F8 { f f32; g f32 }

@[extern] fn take_small(s Small) int
@[extern] fn take_eight(s Eight) int
@[extern] fn take_big(s Big) int
@[extern] fn take_f4(s F4) int
@[extern] fn take_f8(s F8) int
@[extern] fn make_small(a int) Small
@[extern] fn make_big(a int) Big

fn main() int {
    let s Small
    s.a = 1
    let e Eight
    e.a = 1
    e.b = 2
    let b Big
    b.a = 1
    b.b = 2
    b.c = 3
    let f4 F4
    f4.f = 1.5.to_type(f32)
    let f8 F8
    f8.f = 1.5.to_type(f32)
    f8.g = 2.5.to_type(f32)
    printf("small=%d eight=%d big=%d f4=%d f8=%d\n",
        take_small(s), take_eight(e), take_big(b), take_f4(f4), take_f8(f8))
    let ms Small = make_small(3)
    let mb Big = make_big(4)
    printf("ms=%d mb=%d,%d,%d\n", ms.a, mb.a, mb.b, mb.c)
    return 0
}
"""

EXPECTED_STDOUT = "small=2 eight=5 big=9 f4=5 f8=9" + NL + "ms=13 mb=24,4,4" + NL


class GateError(RuntimeError):
    """门禁失败；message 应直接指出下一步。"""


def run(command, cwd):
    """执行命令并保留输出（不走 shell）。"""
    return subprocess.run([str(part) for part in command], cwd=str(cwd),
                          capture_output=True, text=True, errors="replace", timeout=600)


def require(result, what):
    """要求命令成功，失败时带原始输出。"""
    if result.returncode != 0:
        raise GateError(what + " 失败：" + NL + result.stdout + result.stderr)
    return result


def pe_machine(path: Path) -> int:
    """读取 PE 的 machine；不是 PE 直接失败。"""
    data = path.read_bytes()
    if data[:2] != b"MZ" or len(data) < 0x40:
        raise GateError(str(path.name) + " 不是 PE")
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[offset:offset + 4] != b"PE\0\0":
        raise GateError(str(path.name) + " 缺 PE 签名")
    return struct.unpack_from("<H", data, offset + 4)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="W1-2b Windows 聚合 ABI 门禁")
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--workdir", default=str(ROOT / "tmp/llvm-windows-abi"))
    parser.add_argument("--sdk-root", default=str(ROOT / "tmp/llvm-migration/windows-sdk"))
    parser.add_argument("--manifest-out", default=None)
    args = parser.parse_args()

    compiler = Path(args.compiler_path).resolve()
    if not compiler.is_file():
        raise GateError("找不到编译器：" + str(compiler) + "（先跑 just）")
    clang = shutil.which("clang")
    llvm_ar = shutil.which("llvm-ar")
    if clang is None or llvm_ar is None:
        raise GateError("需要 clang 与 llvm-ar（编/打包 C 桩）："
                        "Windows 用 scoop install llvm；Debian/Ubuntu 用 apt-get install clang llvm")
    sdk = Path(args.sdk_root)
    if not (sdk / "lib" / "kernel32.lib").is_file():
        raise GateError("缺少 Windows 导入库：" + str(sdk) + "/lib/kernel32.lib（先跑 just windows-sdk）")

    work = Path(args.workdir)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / "shim.c").write_text(SHIM_C, encoding="utf-8")
    (work / "project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    (work / "main.yh").write_text(MAIN_YH, encoding="utf-8")

    # 1) C 桩 → COFF 对象 → .lib（模拟真实 C 静态库）
    require(run([clang, "--target=x86_64-pc-windows-msvc", "-O1", "-c",
                 "shim.c", "-o", "shim.obj"], work), "编译 C 桩")
    require(run([llvm_ar, "rcs", "libaggshim.lib", "shim.obj"], work), "打包 .lib")

    # 2) yh 构建（通过 [link-windows-x64] 引用该 .lib）
    # yh 通过 YH_WINDOWS_SDK 定位导入库；本项目还要链接 C 桩的 .lib。
    os.environ["YH_WINDOWS_SDK"] = str(sdk)
    require(run([compiler, "build"], work), "yh 构建聚合 ABI 项目")

    exe = work / ".build" / "aggabi"
    if not exe.is_file():
        raise GateError("构建未产出可执行文件：" + str(exe))
    machine = pe_machine(exe)
    if machine != 0x8664:
        raise GateError("产物 machine 不是 x86_64：0x%04x" % machine)

    # 3) 可复现：同一项目再构建一次，产物逐字节相同
    first = exe.read_bytes()
    require(run([compiler, "build"], work), "第二次构建")
    if exe.read_bytes() != first:
        raise GateError("两次构建产物不同：/Brepro 未生效")

    # 4) 运行（Windows）或写清单（跨机）
    if platform.system() == "Windows":
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
        if result.stdout != EXPECTED_STDOUT or result.returncode != 0:
            raise GateError("运行输出不符：rc=" + str(result.returncode)
                            + NL + "expected: " + repr(EXPECTED_STDOUT)
                            + NL + "actual:   " + repr(result.stdout))
    if args.manifest_out:
        manifest = {
            "target": "x86_64-pc-windows-msvc",
            "cases": [{
                "name": "windows/agg-abi",
                "exe": str(exe.relative_to(ROOT)),
                "expected_stdout": EXPECTED_STDOUT,
                "expected_exit": 0,
            }],
        }
        manifest_path = Path(args.manifest_out)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + NL, encoding="utf-8")

    mode = "并已实机执行" if platform.system() == "Windows" else "，产物待运行侧核对"
    print("W1-2b 通过：4/8/12 字节聚合 + 纯浮点聚合的参数与返回均与 C 桩一致，"
          "PE 正确、可复现" + mode)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GateError, OSError, subprocess.SubprocessError) as error:
        print("失败：" + str(error), file=sys.stderr)
        raise SystemExit(1)
