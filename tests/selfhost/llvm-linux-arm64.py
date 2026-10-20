#!/usr/bin/env python3
"""Linux/AArch64 LLVM 后端门（F1）：运行时、C ABI、对象架构与 O0/O2。

前置：在 Linux/aarch64 容器内原生运行；编译器已由固定 LLVM 宿主构建。
开发期只调用 gcc/readelf/nm 做 C 侧与对象检查，编译器本身仍只经内嵌桥。

覆盖：
  * 运行时：malloc/free/printf/memcpy/memset/strlen、AArch64 syscall 与 va_list；
  * C ABI：窄整数、_Bool、混合整浮、HFA2/HFA3、16 字节聚合、24 字节聚合、
    C→YH→C 函数指针回调；
  * 对象：O0/O2 均为 ELF64 AArch64，运行时符号不得留成未定义导入；
  * LLVM 文本：完整目标身份与 AArch64 syscall 内联汇编。

用法：python3 tests/selfhost/llvm-linux-arm64.py [--compiler-path ./yh]
退出码：全部通过 0，失败非 0。
"""

import argparse
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp" / "llvm-migration" / "llvm-linux-arm64"
TARGET = "aarch64-unknown-linux-gnu"
RUNTIME = ROOT / "tests" / "selfhost" / "llvm-linux-arm64-runtime.yh"
RUNTIME_FULL = ROOT / "tests" / "yh-run" / "run" / "llvm-runtime-complete.yh"
ABI_SOURCE = ROOT / "tests" / "selfhost" / "llvm-linux-arm64-abi.yh"
ABI_BRIDGE = ROOT / "tests" / "selfhost" / "llvm-linux-arm64-abi.c"
RUNTIME_IMPORTS = {"malloc", "free", "memcpy", "memmove", "memset", "strlen",
                   "printf", "linux_syscall6", "__divti3", "__modti3",
                   "__udivti3", "__umodti3", "__multi3", "__stack_chk_fail"}


def run(command, **kwargs):
    """执行限时子进程并保留有界输出；失败时由调用方拼接诊断。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=300,
                          **kwargs)


def locate(name):
    """固定 /usr/bin 优先，避免 PATH 上的交叉包装器改变本机工具语义。"""
    fixed = Path("/usr/bin") / name
    return str(fixed) if fixed.is_file() else shutil.which(name)


def require(condition, message):
    """统一门禁失败格式，不依赖 assert（避免 -O 下被裁掉）。"""
    if not condition:
        raise RuntimeError(message)


def expected_output(source):
    """读取 .yh 语料的 expect/expect-more/exit 注释。"""
    lines = []
    exit_code = 0
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("// expect:"):
            lines.append(line[len("// expect:"):].removeprefix(" "))
        elif line.startswith("// expect-more:"):
            lines.append(line[len("// expect-more:"):].removeprefix(" "))
        elif line.startswith("// exit:"):
            exit_code = int(line[len("// exit:"):].strip())
    return lines, exit_code


def check_machine(tools, path, level):
    """确认产物是 AArch64 ELF；machine 183 与目标身份一致。"""
    result = run([tools["readelf"], "-h", str(path)])
    require(result.returncode == 0, f"O{level} readelf 失败\n{result.stderr[-800:]}")
    machine = next((line for line in result.stdout.splitlines()
                    if line.strip().startswith("Machine:")), "")
    require("AArch64" in machine, f"O{level} 产物不是 AArch64：{machine!r}")


def check_imports(tools, path, level):
    """运行时入口必须由模块自带弱定义满足，不留给 libc。"""
    result = run([tools["nm"], "-u", str(path)])
    require(result.returncode == 0, f"O{level} nm -u 失败\n{result.stderr[-800:]}")
    imports = {line.split()[-1] for line in result.stdout.splitlines() if line.split()}
    leaked = sorted(imports.intersection(RUNTIME_IMPORTS))
    require(not leaked, f"O{level} 仍有未定义运行时导入: {leaked}")


def compile_and_run_runtime(compiler, tools, level, source, tag):
    """编译运行时用例，运行并核对 stdout/退出码。"""
    exe = WORK / f"{tag}-O{level}"
    result = run([compiler, "--backend", "llvm", "--target", TARGET,
                  f"-O{level}", "-o", str(exe), str(source)],
                 env=dict(os.environ, PATH="/usr/bin:/bin"))
    require(result.returncode == 0,
            f"O{level} 运行时用例编译/链接失败\n{result.stderr[-2000:]}")
    check_machine(tools, exe, level)
    check_imports(tools, exe, level)
    expected, exit_code = expected_output(source)
    executed = run([str(exe)], cwd=ROOT)
    actual = executed.stdout.rstrip("\n").split("\n") if executed.stdout else []
    require(executed.returncode == exit_code,
            f"O{level} 运行时退出码 {executed.returncode}，期望 {exit_code}; "
            f"stderr={executed.stderr[-800:]!r}")
    require(actual == expected,
            f"O{level} 运行时输出不符\n期望={expected!r}\n实际={actual!r}")


def check_llvm_text(compiler, level):
    """单文件 --emit-llvm 必须写出完整 AArch64 目标与 syscall 分支。"""
    result = run([compiler, "--backend", "llvm", "--target", TARGET,
                  f"-O{level}", "--emit-asm", "--emit-llvm", str(RUNTIME)])
    require(result.returncode == 0,
            f"O{level} LLVM 文本发射失败\n{result.stderr[-1600:]}")
    text = result.stdout
    require(f'target triple = "{TARGET}"' in text,
            f"O{level} LLVM 文本缺少目标 triple")
    require('asm sideeffect "svc #0"' in text,
            f"O{level} LLVM 文本缺少 AArch64 syscall")
    require('define weak i32 @printf(ptr %fmt, ...)' in text,
            f"O{level} LLVM 文本缺少 printf 弱定义")
    require('call i64 @linux_syscall6(i64 222' in text,
            f"O{level} LLVM 文本未使用 AArch64 mmap 号 222")
    require('call i64 @linux_syscall6(i64 64' in text,
            f"O{level} LLVM 文本未使用 AArch64 write 号 64")


def check_embedded_lld(compiler, tools, level):
    """无 PATH 下完成默认后端编译/链接/运行，证明内嵌 lld 不依赖宿主 gcc。"""
    exe = WORK / f"default-lld-O{level}"
    exe.unlink(missing_ok=True)
    result = run([compiler, f"-O{level}", "-o", str(exe), str(RUNTIME)],
                 env={"PATH": "/nonexistent"})
    require(result.returncode == 0,
            f"O{level} 默认后端/内嵌 lld 链接失败（不应回退宿主 gcc）\n"
            f"{result.stderr[-1600:]}")
    check_machine(tools, exe, level)
    expected, exit_code = expected_output(RUNTIME)
    executed = run([str(exe)])
    actual = executed.stdout.rstrip("\n").split("\n") if executed.stdout else []
    require(executed.returncode == exit_code and actual == expected,
            f"O{level} 默认后端产物输出不符：rc={executed.returncode} {actual!r}")


def check_compiler_bridge(compiler, tools):
    """编译器自身必须静态定义 LLVM/lld 桥，且不动态依赖 libLLVM/lld。"""
    dynamic = run([tools["readelf"], "-d", compiler])
    require(dynamic.returncode == 0, f"readelf -d 编译器失败\n{dynamic.stderr[-800:]}")
    require(not re.search(r"lib(?:LLVM|lld)", dynamic.stdout, re.IGNORECASE),
            "编译器动态依赖 libLLVM/lld")
    symbols = run([tools["nm"], compiler])
    require(symbols.returncode == 0, f"nm 编译器失败\n{symbols.stderr[-800:]}")
    for name in ("yh_llvm_emit", "yh_lld_link_driver", "yh_lld_link_identity"):
        require(re.search(rf"(?m) [TtWw] {name}$", symbols.stdout) is not None,
                f"编译器未静态定义桥符号 {name}")


def check_c_abi(compiler, tools, level):
    """发射 AArch64 汇编，与 gcc 编出的 C 桥链接并双向运行。"""
    assembly = WORK / f"abi-O{level}.s"
    emitted = run([compiler, "--backend", "llvm", "--target", TARGET,
                   f"-O{level}", "--emit-asm", str(ABI_SOURCE)])
    require(emitted.returncode == 0,
            f"O{level} ABI 汇编发射失败\n{emitted.stderr[-2000:]}")
    assembly.write_text(emitted.stdout, encoding="utf-8")
    yh_obj = WORK / f"abi-yh-O{level}.o"
    c_obj = WORK / f"abi-c-O{level}.o"
    executable = WORK / f"abi-O{level}"
    for command, label in (
        ([tools["gcc"], "-O2", "-c", str(assembly), "-o", str(yh_obj)], "YH 汇编"),
        ([tools["gcc"], f"-O{level}", "-c", str(ABI_BRIDGE), "-o", str(c_obj)], "C 桥"),
        ([tools["gcc"], "-no-pie", str(yh_obj), str(c_obj), "-o", str(executable)], "链接"),
    ):
        result = run(command)
        require(result.returncode == 0,
                f"O{level} {label}失败\n{result.stderr[-1600:]}")
    check_machine(tools, executable, level)
    executed = run([str(executable)])
    require(executed.returncode == 0,
            f"O{level} C ABI 双向运行失败 rc={executed.returncode}\n"
            f"stdout={executed.stdout[-800:]!r}\nstderr={executed.stderr[-800:]!r}")


def main():
    """逐项执行 F1 门；失败立即退出并保留工作目录供诊断。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    require(Path(compiler).is_file(), f"编译器不存在：{compiler}")
    require(platform.system() == "Linux" and platform.machine() in ("aarch64", "arm64"),
            "本门要求在 Linux/AArch64 容器内原生运行")
    tools = {name: locate(tool) for name, tool in
             (("gcc", "gcc"), ("readelf", "readelf"), ("nm", "nm"))}
    missing = [name for name, path in tools.items() if path is None]
    require(not missing, f"缺少开发工具：{missing}")
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)

    check_compiler_bridge(compiler, tools)
    for level in (0, 2):
        compile_and_run_runtime(compiler, tools, level, RUNTIME, "runtime")
        compile_and_run_runtime(compiler, tools, level, RUNTIME_FULL, "runtime-full")
        check_llvm_text(compiler, level)
        check_embedded_lld(compiler, tools, level)
        check_c_abi(compiler, tools, level)
        print(f"PASS O{level}: 默认 LLVM/内嵌 lld、运行时、AArch64 syscall、C ABI 与对象架构")
    print("PASS Linux/AArch64 LLVM F1 门：O0/O2 运行时、C ABI 与 ELF 产物")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"FAIL Linux/AArch64 LLVM F1 门：{error}")
        raise SystemExit(1)
