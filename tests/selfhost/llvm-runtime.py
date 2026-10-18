#!/usr/bin/env python3
"""LL8a/LL8b 运行时门：LLVM helper、完整 x64 runtime 与宿主桥。

验收（与实施方案 LL8a 对应）：
  * memory：保持 LL8a 的 helper、O0/O2 对象、自递归与 C 边界驱动检查；
  * complete：保留 memory 检查，并在 O0/O2 编译、验证、优化及原生运行
    allocator/printf 和 Linux x64 宿主桥用例；
  * clang/opt/objdump 只作开发差分 oracle，产物仍来自编译器自己的桥。
"""

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp" / "llvm-migration" / "llvm-runtime"
TARGET = "x86_64-unknown-linux-gnu"
HELPERS = ("memcpy", "memset", "strlen")
RUNTIME_IMPORTS = {"malloc", "free", "memcpy", "memmove", "memset", "strlen",
                   "printf", "linux_syscall6", "__divti3", "__modti3",
                   "__udivti3", "__umodti3", "__multi3", "__stack_chk_fail"}

# helpers.yh：无 main 的发射源，供 clang 汇编驱动链接；probe.yh：带 main，
# 供编译器经内嵌桥产可执行文件，验证真实管线下的 O0/O2 产物。
HELPERS_SOURCE = """module helpers;

// probe：让模块非空；helper 与用户函数必须共存。
fn probe(x int) int { return x + 1; }
"""

PROBE_SOURCE = """module probe;

// main：桥链接形态的最小入口，只验证 helper 与用户函数共存且可运行。
fn main() int { return 0; }
"""

DRIVER_SOURCE = r"""/* LL8a 边界驱动：链接对象中的 weak helper，覆盖复制/清零/字符串契约。 */
#include <stdint.h>

extern void *memcpy(void *, const void *, unsigned long);
extern void *memset(void *, int, unsigned long);
extern unsigned long strlen(const char *);

int main(void) {
    static unsigned char src[4100];
    static unsigned char dst[4100];
    static const unsigned long sizes[] = {0, 1, 7, 8, 16, 31, 32, 4096};

    for (unsigned i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++) {
        unsigned long n = sizes[i];
        for (unsigned long k = 0; k < 4100; k++) {
            src[k] = (unsigned char)(k * 31 + 7);
            dst[k] = 0xAA;
        }
        if (memcpy(dst, src, n) != dst) return 1;
        for (unsigned long k = 0; k < n; k++) if (dst[k] != src[k]) return 2;
        if (n < 4096 && dst[n] != 0xAA) return 3;
        if (memset(dst, 0x1FF, n) != dst) return 4;
        for (unsigned long k = 0; k < n; k++) if (dst[k] != 0xFF) return 5;
        if (n < 4096 && dst[n] != 0xAA) return 6;
    }

    if (strlen("") != 0) return 7;
    if (strlen("a") != 1) return 8;
    if (strlen("1234567") != 7) return 9;
    if (strlen("12345678") != 8) return 10;
    if (strlen("\xe9\x9b\xaa") != 3) return 11;
    static char big[4099];
    memset(big, 'q', 4098);
    big[4098] = 0;
    if (strlen(big) != 4098) return 12;
    return 0;
}
"""


def run(command, **kwargs):
    """执行真候选或差分工具，保留有界输出；超时视为门失败。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=300, **kwargs)


def locate(*names):
    """按 /usr/bin 优先、PATH 回落的顺序查找宿主差分工具。

    这些门需要宿主 x86_64 的 clang/opt/gcc；PATH 上可能有 crossbin 交叉包装器，
    因此先固定 /usr/bin，再允许 PATH 提供其它发行路径。
    """
    for name in names:
        fallback = Path("/usr/bin") / name
        if fallback.is_file():
            return str(fallback)
        found = shutil.which(name)
        if found:
            return found
    return None


def emit_text(compiler, source, level, output):
    """用真编译器发射 LLVM 文本（不调用桥），返回文本内容。"""
    result = run([compiler, "--emit-asm", "--backend", "llvm", "--target", TARGET,
                  f"-O{level}", "--emit-llvm", str(source)])
    assert result.returncode == 0, (
        f"O{level} LLVM 文本发射失败 rc={result.returncode}\n{result.stderr[-1200:]}")
    output.write_text(result.stdout, encoding="utf-8")
    return result.stdout


def check_text(text, level):
    """核对三个入口的 weak 定义与 llvm.used 契约；缺一即失败。"""
    for name in HELPERS:
        assert re.search(rf"define weak \w+ @{name}\(", text), (
            f"O{level} 文本缺少 {name} 弱定义\n{text[-800:]}")
    assert f"@llvm.used = appending global [3 x ptr]" in text, (
        f"O{level} 文本缺少 llvm.used 固定\n{text[-800:]}")


def check_object(tools, llfile, level):
    """汇编对象并检查定义、未解析导入与自递归；返回对象路径。"""
    obj = WORK / f"helpers-O{level}.o"
    result = run([tools["clang"], "-c", str(llfile), "-o", str(obj)])
    assert result.returncode == 0, f"O{level} clang 汇编失败\n{result.stderr[-1200:]}"
    defined = run([tools["nm"], str(obj)]).stdout
    for name in HELPERS:
        assert re.search(rf" [WwTt] {name}$", defined, re.M), (
            f"O{level} 对象缺少 {name} 定义\n{defined[-800:]}")
    undefined = run([tools["nm"], "-u", str(obj)]).stdout
    leaked = [line for line in undefined.splitlines()
              if line.split() and line.split()[-1] in HELPERS]
    assert not leaked, f"O{level} 内存入口仍是未定义导入: {leaked}"
    for name in HELPERS:
        disasm = run([tools["objdump"], "-d", f"--disassemble={name}", str(obj)]).stdout
        assert re.search(rf"\b(call|bl)\b.*<{name}>", disasm) is None, (
            f"O{level} {name} 出现自我递归\n{disasm[-800:]}")
    return obj


def parse_expected(source):
    """读取 .yh 语料的逐行 stdout 与退出码期望。"""
    expected = []
    exit_code = 0
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("// expect:"):
            expected.append(line[len("// expect:"):].removeprefix(" "))
        elif line.startswith("// expect-more:"):
            expected.append(line[len("// expect-more:"):].removeprefix(" "))
        elif line.startswith("// exit:"):
            exit_code = int(line[len("// exit:"):].strip())
    return expected, exit_code


def undefined_symbols(tools, obj):
    """返回原生对象的未定义符号名集合。"""
    result = run([tools["nm"], "-u", str(obj)])
    assert result.returncode == 0, f"nm -u 失败: {result.stderr[-800:]}"
    return {line.split()[-1] for line in result.stdout.splitlines() if line.split()}


def required_runtime_symbols(source):
    """返回用例必须触发的运行时入口，保留按需注入语义。"""
    required = ["linux_syscall6", "printf", "memcpy", "memset", "strlen",
                "yh_printf_write", "yh_printf_emit", "yh_printf_integer"]
    if source.name == "llvm-runtime-complete.yh":
        required.extend(("malloc", "free"))
    return tuple(required)


def check_complete_object(tools, obj, source, level):
    """核对完整运行时弱定义、未解析运行时入口与 LLVM 生成 libcall。"""
    symbols = run([tools["nm"], str(obj)])
    assert symbols.returncode == 0, f"O{level} nm 失败: {symbols.stderr[-800:]}"
    required = required_runtime_symbols(source)
    for name in required:
        assert re.search(rf" [WwTt] {name}$", symbols.stdout, re.M), (
            f"{source.name} O{level} 对象缺少运行时定义 {name}\n{symbols.stdout[-1200:]}")

    imports = undefined_symbols(tools, obj)
    allowed = {"close"} if source.name == "llvm-runtime-complete.yh" else {
        "close", "execvp", "exit", "fork", "open", "waitpid"}
    leaked_runtime = sorted(imports.intersection(RUNTIME_IMPORTS))
    unexpected = sorted(imports - allowed)
    assert not leaked_runtime, (
        f"{source.name} O{level} 仍导入运行时/libcall: {leaked_runtime}")
    assert not unexpected, f"{source.name} O{level} 有未审核导入: {unexpected}"

    for name in required:
        disasm = run([tools["objdump"], "-d", f"--disassemble={name}", str(obj)])
        assert disasm.returncode == 0, f"O{level} objdump {name} 失败"
        assert re.search(rf"\b(call|bl)\b.*<{name}>", disasm.stdout) is None, (
            f"O{level} {name} 出现自递归\n{disasm.stdout[-800:]}")


def check_complete_fixture(compiler, tools, source, level):
    """发射、验证、优化、链接并原生运行一份 LL8b 源级契约用例。"""
    prefix = source.stem
    llfile = WORK / f"{prefix}-compiler-O{level}.ll"
    text = emit_text(compiler, source, level, llfile)
    assert "@linux_syscall6" in text, f"{source.name} O{level} 未触发 syscall runtime"
    for name in required_runtime_symbols(source):
        linkage = "internal" if name.startswith("yh_printf_") else "weak"
        assert re.search(rf"define {linkage} \w+ @{name}\(", text), (
            f"{source.name} O{level} 文本缺少 {name} {linkage} 定义")

    verify = run([tools["opt"], "-passes=verify", "-disable-output", str(llfile)])
    assert verify.returncode == 0, (
        f"{source.name} O{level} opt 验证失败\n{verify.stderr[-1600:]}")
    optimized = WORK / f"{prefix}-LLVM-O{level}.ll"
    result = run([tools["opt"], "-S", "-passes=default<O2>",
                  str(llfile), "-o", str(optimized)])
    assert result.returncode == 0, (
        f"{source.name} O{level} LLVM O2 优化失败\n{result.stderr[-1600:]}")
    optimized_verify = run([tools["opt"], "-passes=verify", "-disable-output",
                            str(optimized)])
    assert optimized_verify.returncode == 0, (
        f"{source.name} O{level} 优化后 IR 无效\n{optimized_verify.stderr[-1600:]}")

    artifact = optimized if level == 2 else llfile
    obj = WORK / f"{prefix}-O{level}.o"
    result = run([tools["clang"], "-c", str(artifact), "-o", str(obj)])
    assert result.returncode == 0, (
        f"{source.name} O{level} clang 汇编失败\n{result.stderr[-1600:]}")
    check_complete_object(tools, obj, source, level)

    executable = WORK / f"{prefix}-O{level}"
    result = run([tools["cc"], "-fno-builtin", "-O0", "-no-pie",
                  str(obj), "-o", str(executable)])
    assert result.returncode == 0, (
        f"{source.name} O{level} 链接失败\n{result.stderr[-1600:]}")
    if source.name == "llvm-linux-x64-host.yh":
        host_probe = ROOT / "tmp" / "llvm-migration" / "host-probe-目录"
        if host_probe.exists():
            shutil.rmtree(host_probe)
    result = run([str(executable)], cwd=ROOT)
    expected, exit_code = parse_expected(source)
    actual = result.stdout.rstrip("\n").split("\n") if result.stdout else []
    assert result.returncode == exit_code, (
        f"{source.name} O{level} 退出码 {result.returncode}，期望 {exit_code}; "
        f"stderr={result.stderr[-800:]!r}")
    assert actual == expected, (
        f"{source.name} O{level} stdout 不符\n期望={expected!r}\n实际={actual!r}")


def main():
    """构建隔离工作区，运行 LL8a memory 或 LL8b complete 验收套件。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--suite", choices=("memory", "complete"), default="memory")
    args = parser.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    assert Path(compiler).is_file(), f"编译器不存在: {compiler}"
    tools = {name: locate(*candidates) for name, candidates in {
        "clang": ("clang-21", "clang"), "opt": ("opt-21", "opt"),
        "cc": ("x86_64-linux-gnu-gcc", "gcc", "cc"),
        "nm": ("nm",), "objdump": ("objdump",)}.items()}
    missing = [name for name, path in tools.items() if path is None]
    assert not missing, f"LL8a 差分工具缺失: {missing}（仅开发门使用 clang/opt/objdump）"
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    helpers_source = WORK / "helpers.yh"
    probe_source = WORK / "probe.yh"
    helpers_source.write_text(HELPERS_SOURCE, encoding="utf-8")
    probe_source.write_text(PROBE_SOURCE, encoding="utf-8")
    driver = WORK / "driver.c"
    driver.write_text(DRIVER_SOURCE, encoding="utf-8")

    for level in (0, 2):
        llfile = WORK / f"helpers-O{level}.ll"
        text = emit_text(compiler, helpers_source, level, llfile)
        check_text(text, level)

        # opt 作为独立 oracle：验证 IR，并确认 O2 管线不丢弃 weak 定义。
        verify = run([tools["opt"], "-passes=verify", "-S", str(llfile), "-o", os.devnull])
        assert verify.returncode == 0, f"O{level} opt 验证失败\n{verify.stderr[-1200:]}"
        optimized = WORK / f"helpers-O{level}-opt.ll"
        result = run([tools["opt"], "-S", "-passes=default<O2>", str(llfile), "-o", str(optimized)])
        assert result.returncode == 0, f"O{level} O2 管线失败\n{result.stderr[-1200:]}"
        assert optimized.read_text(encoding="utf-8").count("define weak") == 3, (
            f"O{level} O2 丢弃了弱定义（llvm.used 未生效）")

        # 对象检查与原生边界驱动：clang 只负责把文本变成本地对象。
        obj = check_object(tools, llfile, level)
        executable = WORK / f"driver-O{level}"
        result = run([tools["cc"], "-fno-builtin", "-O0", "-no-pie",
                      str(driver), str(obj), "-o", str(executable)])
        assert result.returncode == 0, f"O{level} 驱动链接失败\n{result.stderr[-1200:]}"
        result = run([str(executable)])
        assert result.returncode == 0, (
            f"O{level} 边界驱动失败 rc={result.returncode}\n{result.stdout[-400:]}")

        # 桥路径：编译器自己产对象并链接，核对真实管线产物的 weak 定义与运行。
        # 链接子进程必须用宿主 x86_64 gcc；crossbin 包装器在 PATH 上时需清掉。
        bridge_exe = WORK / f"probe-O{level}"
        result = run([compiler, "--backend", "llvm", "--target", TARGET,
                      f"-O{level}", "-o", str(bridge_exe), str(probe_source)],
                     env=dict(os.environ, PATH="/usr/bin:/bin"))
        assert result.returncode == 0, f"O{level} 桥链接失败\n{result.stderr[-1200:]}"
        defined = run([tools["nm"], str(bridge_exe)]).stdout
        for name in HELPERS:
            assert re.search(rf" [Ww] {name}$", defined, re.M), (
                f"O{level} 桥产物缺少 {name} 定义\n{defined[-800:]}")
        result = run([str(bridge_exe)])
        assert result.returncode == 0, f"O{level} 桥产物运行失败 rc={result.returncode}"

    if args.suite == "complete":
        fixtures = (ROOT / "tests" / "yh-run" / "run" / "llvm-runtime-complete.yh",
                    ROOT / "tests" / "yh-run" / "run" / "llvm-linux-x64-host.yh")
        runtime_memory = ROOT / "tests" / "selfhost" / "runtime-memory.py"
        result = run(["python3", str(runtime_memory), "--compiler-path", compiler,
                      "--llvm-x64"], cwd=ROOT)
        assert result.returncode == 0, (
            f"runtime-memory LLVM 导入审计失败\n{result.stdout[-1200:]}"
            f"{result.stderr[-1200:]}")
        for fixture in fixtures:
            for level in (0, 2):
                check_complete_fixture(compiler, tools, fixture, level)
        print("LL8b 完整运行时通过：内存 helper、allocator/printf、x64 syscall/宿主桥，O0/O2 原生运行与导入审计")
    else:
        print("LL8a 内存 helper 通过：weak 定义/llvm.used、O0/O2 对象、无自递归、原生边界驱动")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
