#!/usr/bin/env python3
"""验证 yh 自有内存运行时与 Darwin/Linux 导入边界。"""

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "modules" / "projects" / "runtimebytes"
PLAIN_FIXTURE = ROOT / "tests" / "modules" / "projects" / "runtimeplain"
WORK = ROOT / "tmp" / "runtime-memory"
PLAIN_WORK = ROOT / "tmp" / "runtime-plain"


def run(command, cwd):
    """运行真实编译器或二进制并保留输出，便于报告失败原因。"""
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                          timeout=120)


def main():
    """构建运行 fixture，检查本地分配器及平台映射接口。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree(FIXTURE, WORK)

    build = run([compiler, "build"], WORK)
    binary = WORK / ".build" / "runtimebytes"
    if build.returncode != 0 or not binary.exists():
        print(f"FAIL 构建 runtimebytes: rc={build.returncode}\n{build.stderr[-1200:]}")
        return 1

    execution = run([str(binary)], WORK)
    if execution.returncode != 0:
        print(f"FAIL 自有内存运行时结果: rc={execution.returncode}\n"
              f"{execution.stderr[-800:]}")
        return 1
    expected_output = "fmt:-7 8 -9 10 str A %\nargs:12345678\n" + "x" * 299
    if execution.stdout != expected_output:
        print(f"FAIL 自有格式化输出: {execution.stdout!r}")
        return 1

    imports = run(["nm", "-u", str(binary)], WORK)
    if imports.returncode != 0:
        print(f"FAIL 检查未定义符号: rc={imports.returncode}\n{imports.stderr[-800:]}")
        return 1
    names = {line.split()[-1].lstrip("_") for line in imports.stdout.splitlines()
             if line.split()}
    forbidden = sorted(names.intersection(
        {"malloc", "free", "memcpy", "strlen", "printf"}))
    if forbidden:
        print(f"FAIL 产物仍从 C runtime 导入: {', '.join(forbidden)}")
        return 1
    # 宿主产物导入边界：Darwin（Mach-O）经 libSystem 显式导入
    # mmap/munmap/write；Linux（ELF）的 yh 运行时用 svc 直调，`nm -u`
    # 只余 gcc/glibc 起动辅助（版本化 GLIBC 符号与 libgcc/起动别名），
    # 显式 C 运行库导入已在上方拒绝。
    darwin_host = sys.platform == "darwin"
    # 集合元素与上方 lstrip("_") 后的名字一致（nm 的 _ 前缀已被剥除）。
    aux_ok = {"gmon_start__", "libc_start_main",
              "ITM_deregisterTMCloneTable", "ITM_registerTMCloneTable"}
    if darwin_host:
        if not {"mmap", "munmap", "write"}.issubset(names):
            print(f"FAIL Darwin 可执行文件未显式导入映射/输出 OS API: {sorted(names)}")
            return 1
    else:
        unexpected = sorted(n for n in names
                            if "@" not in n and n not in aux_ok)
        if unexpected:
            print(f"FAIL Linux 可执行文件未预期的未定义符号: {unexpected}")
            return 1

    linux_asm = run([compiler, "-target", "linux", "--emit-asm", "main.yh"], WORK)
    linux_syscalls = ("mov\tx8, #222" in linux_asm.stdout
                     and "mov\tx8, #215" in linux_asm.stdout
                     and "mov\tx8, #64" in linux_asm.stdout)
    if (linux_asm.returncode != 0 or "\nmemcpy:\n" not in linux_asm.stdout
            or "\nstrlen:\n" not in linux_asm.stdout
            or "\nmalloc:\n" not in linux_asm.stdout
            or "\nfree:\n" not in linux_asm.stdout or not linux_syscalls):
        print(f"FAIL Linux arm64 未生成本地内存运行时: rc={linux_asm.returncode}\n"
              f"{linux_asm.stderr[-800:]} {linux_asm.stdout[-400:]}")
        return 1
    asm_path = WORK / "linux-main.s"
    obj_path = WORK / "linux-main.o"
    asm_path.write_text(linux_asm.stdout)
    # 组装 Linux 目标：宿主本来就是 aarch64（如 CI 的 arm64 容器）时系统 gcc
    # 原生汇编即可；x86_64 宿主才需要交叉汇编器，此时显式取系统 clang
    # （PATH 上的 clang 可能被项目工具链包装劫持成认不出 -target 的交叉 gcc）。
    # 容器里只装 build-essential+python3，没有 clang，故不能只留 clang 一条路。
    if sys.platform == "darwin":
        assembler = ["clang", "-target", "aarch64-linux-gnu", "-c"]
    elif platform.machine().lower() in ("aarch64", "arm64"):
        assembler = ["gcc", "-c"]
    else:
        clang_tool = "/usr/bin/clang" if Path("/usr/bin/clang").exists() \
            else shutil.which("clang")
        if clang_tool is None:
            print("FAIL 找不到交叉汇编器 clang（x86_64 宿主汇编 aarch64 目标需要它）")
            return 1
        assembler = [clang_tool, "-target", "aarch64-linux-gnu", "-c"]
    assembled = run(assembler + [str(asm_path), "-o", str(obj_path)], WORK)
    if assembled.returncode != 0:
        print(f"FAIL Linux arm64 运行时汇编: rc={assembled.returncode}\n"
              f"{assembled.stderr[-1000:]}")
        return 1
    linux_imports = run(["nm", "-u", str(obj_path)], WORK)
    if linux_imports.returncode != 0 or linux_imports.stdout.strip():
        print(f"FAIL Linux runtimebytes 对象仍有未定义符号:\n"
              f"{linux_imports.stderr[-800:]}{linux_imports.stdout[-800:]}")
        return 1

    compiler_build = run([compiler, "build"], ROOT / "compiler")
    compiler_binary = ROOT / "compiler" / ".build" / "yh"
    if compiler_build.returncode != 0 or not compiler_binary.exists():
        print(f"FAIL 编译器自编导入审计构建: rc={compiler_build.returncode}\n"
              f"{compiler_build.stderr[-1000:]}")
        return 1
    compiler_imports = run(["nm", "-u", str(compiler_binary)], ROOT / "compiler")
    if compiler_imports.returncode != 0:
        print(f"FAIL 检查自编编译器未定义符号: rc={compiler_imports.returncode}\n"
              f"{compiler_imports.stderr[-800:]}")
        return 1
    compiler_names = {line.split()[-1].lstrip("_")
                      for line in compiler_imports.stdout.splitlines() if line.split()}
    compiler_forbidden = sorted(compiler_names.intersection(
        {"malloc", "free", "memcpy", "strlen", "printf"}))
    if compiler_forbidden:
        print(f"FAIL 自编译器仍从 C runtime 导入: {', '.join(compiler_forbidden)}")
        return 1
    if darwin_host:
        if not {"mmap", "munmap"}.issubset(compiler_names):
            print(f"FAIL 自编译器未导入审核后的映射 OS API: {sorted(compiler_names)}")
            return 1
    else:
        unexpected_c = sorted(n for n in compiler_names
                              if "@" not in n and n not in aux_ok)
        if unexpected_c:
            print(f"FAIL Linux 自编译器未预期的未定义符号: {unexpected_c}")
            return 1

    if PLAIN_WORK.exists():
        shutil.rmtree(PLAIN_WORK)
    shutil.copytree(PLAIN_FIXTURE, PLAIN_WORK)
    plain_build = run([compiler, "build"], PLAIN_WORK)
    plain_binary = PLAIN_WORK / ".build" / "runtimeplain"
    if plain_build.returncode != 0 or not plain_binary.exists():
        print(f"FAIL 构建无运行时依赖项目: rc={plain_build.returncode}\n"
              f"{plain_build.stderr[-800:]}")
        return 1
    plain_imports = run(["nm", "-u", str(plain_binary)], PLAIN_WORK)
    if plain_imports.returncode != 0:
        print(f"FAIL 检查无运行时依赖项目: rc={plain_imports.returncode}\n"
              f"{plain_imports.stderr[-800:]}")
        return 1
    plain_names = {line.split()[-1].lstrip("_")
                   for line in plain_imports.stdout.splitlines() if line.split()}
    unused = sorted(plain_names.intersection(
        {"malloc", "free", "memcpy", "strlen", "printf", "mmap", "munmap", "write"}))
    if unused:
        print(f"FAIL 无分配/输出调用的程序仍带入运行时 OS API: {', '.join(unused)}")
        return 1
    print("自有运行时：格式化、函数值、按需发射裁剪、OS API 导入与 Linux 汇编通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
