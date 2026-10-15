#!/usr/bin/env python3
"""LL8a 内存 helper 门：LLVM 文本、O0/O2 对象、自递归检查与原生边界驱动。

验收（与实施方案 LL8a 对应）：
  * `memcpy`/`memset`/`strlen` 以 weak 定义 + llvm.used 出现在每个 LLVM 模块，
    `opt` 验证通过，O2 管线不会丢弃弱定义；
  * 对象中三个入口有定义且不留下未解析的内存导入，反汇编没有自我递归；
  * 用 C 边界驱动（0/1/7/8/16/31/32/4096 字节复制/清零与字符串边界）链接
    真实对象并原生运行；
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
    """按 PATH 与 /usr/bin 顺序查找差分工具；找不到返回 None 由调用方报告。"""
    for name in names:
        found = shutil.which(name)
        if found:
            return found
        fallback = Path("/usr/bin") / name
        if fallback.is_file():
            return str(fallback)
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


def main():
    """构建隔离工作区，按 O0/O2 核对文本、对象、桥产物与原生边界驱动。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    assert Path(compiler).is_file(), f"编译器不存在: {compiler}"
    tools = {name: locate(*candidates) for name, candidates in {
        "clang": ("clang",), "opt": ("opt",), "cc": ("cc", "gcc"),
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
        bridge_exe = WORK / f"probe-O{level}"
        result = run([compiler, "--backend", "llvm", "--target", TARGET,
                      f"-O{level}", "-o", str(bridge_exe), str(probe_source)])
        assert result.returncode == 0, f"O{level} 桥链接失败\n{result.stderr[-1200:]}"
        defined = run([tools["nm"], str(bridge_exe)]).stdout
        for name in HELPERS:
            assert re.search(rf" [Ww] {name}$", defined, re.M), (
                f"O{level} 桥产物缺少 {name} 定义\n{defined[-800:]}")
        result = run([str(bridge_exe)])
        assert result.returncode == 0, f"O{level} 桥产物运行失败 rc={result.returncode}"

    print("LL8a 内存 helper 通过：weak 定义/llvm.used、O0/O2 对象、无自递归、原生边界驱动")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
