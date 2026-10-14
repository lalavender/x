#!/usr/bin/env python3
"""用独立 oracle 复核 yh_asm 编码层的全部用例。

oracle 解析与 check_corpus.py 共用（oracle_kind / oracle_asm）：

  * llvm-mc：`--assemble --show-encoding` 逐条回显文本与机器字（原路径）；
    文本被规范化过（movz→mov、uxtb→and、beq→b.eq 等）时退化为「机器字是否
    出现在本次输出集合中」。
  * clang：集成汇编器没有 --show-encoding，改为把全部用例**按原顺序**汇成
    一个 .s，汇编后按顺序读 .text 的机器字逐位比对。用例一一对应，比文本
    比对更严，也就不需要别名退化。

用法：python3 tests/check_enc.py
"""

import os
import re
import struct
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS)
from check_corpus import oracle_kind, oracle_asm, read_elf      # noqa: E402

ROOT = os.path.dirname(TESTS)
BIN = os.path.join(ROOT, ".build", "yh_asm")
TRIPLE = "aarch64-linux-gnu"
TMP = os.path.join(os.path.dirname(ROOT), "tmp")


def dump_cases():
    """跑 `yh_asm --dump-enc`，返回 [(指令文本, 本实现的机器字)]。"""
    r = subprocess.run([BIN, "--dump-enc"], capture_output=True, text=True,
                       timeout=60)
    if r.returncode != 0:
        print("yh_asm 自检失败，rc=%d\n%s" % (r.returncode, r.stderr.strip()))
        sys.exit(1)
    cases = []
    for line in r.stdout.splitlines():
        if "\t" not in line:
            continue
        name, word = line.split("\t", 1)
        cases.append((re.sub(r"\s+", " ", name).strip(), word.strip()))
    return cases


def oracle_llvm_mc(tool, cases):
    """一次汇编全部文本，返回 {文本: 机器字}。"""
    src = "\n".join(name for name, _ in cases)
    r = subprocess.run([tool, "--assemble", "-triple=" + TRIPLE,
                        "--show-encoding"],
                       input=src, capture_output=True, text=True, timeout=60)
    found = {}
    for line in r.stdout.splitlines():
        m = re.match(r"\s*(.*?)\s*//\s*encoding:\s*\[([^\]]+)\]", line)
        if not m:
            continue
        text = re.sub(r"\s+", " ", m.group(1)).strip()
        b = [int(x, 16) for x in m.group(2).replace(" ", "").split(",")]
        found[text] = b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)
    return found


def oracle_clang(tool, cases):
    """把用例按顺序汇成一个 .s，汇编后按顺序返回 .text 里的机器字。

    输入留在 tmp/enc-oracle.s 便于失败时定位；返回 None 表示汇编失败。
    """
    os.makedirs(TMP, exist_ok=True)
    src = os.path.join(TMP, "enc-oracle.s")
    dst = os.path.join(TMP, "enc-oracle.o")
    with open(src, "w") as fh:
        fh.write("\t.text\n")
        for name, _ in cases:
            fh.write("\t" + name + "\n")
    if not oracle_asm("clang", tool, src, dst, TRIPLE):
        print("oracle（clang）汇编失败，输入留在 %s" % src)
        return None
    secs, _ = read_elf(dst)
    text = secs.get(".text", (0, b"", 0, 0))[1]
    return [struct.unpack_from("<I", text, i)[0]
            for i in range(0, len(text) - 3, 4)]


def compare_text(found, cases):
    """llvm-mc 路径：文本直比对，别名规范化时退化为机器字集合比对。"""
    words = set("%08x" % w for w in found.values())
    direct = indirect = 0
    diff = []
    lost = []
    for name, word in cases:
        want = found.get(name)
        if want is None:
            if word in words:
                indirect += 1
            else:
                lost.append((name, word))
            continue
        if "%08x" % want == word:
            direct += 1
        else:
            diff.append((name, word, "%08x" % want))
    print("用例 %d 条：文本直比对 %d 条，别名间接比对 %d 条，不一致 %d 条，无从比对 %d 条"
          % (len(cases), direct, indirect, len(diff), len(lost)))
    for (name, got, want) in diff:
        print("  不一致 %-32s yh=%s oracle=%s" % (name, got, want))
    for (name, got) in lost:
        print("  缺失   %-32s yh=%s" % (name, got))
    return 1 if diff or lost else 0


def main():
    if not os.path.exists(BIN):
        print("缺 %s，先跑 `../yh build`" % BIN)
        return 1
    kind, tool = oracle_kind()
    if kind == "":
        print("找不到独立 oracle：给 LLVM_MC=<llvm-mc 路径> 或把 clang 放进 PATH")
        return 2
    print("oracle: %s (%s)" % (kind, tool))
    cases = dump_cases()
    if kind == "llvm-mc":
        return compare_text(oracle_llvm_mc(tool, cases), cases)

    words = oracle_clang(tool, cases)
    if words is None:
        return 1
    if len(words) != len(cases):
        print("oracle 给出 %d 个机器字，用例 %d 条（数量不符）"
              % (len(words), len(cases)))
        return 1
    diff = [(name, want, "%08x" % got)
            for (name, want), got in zip(cases, words) if "%08x" % got != want]
    print("用例 %d 条：按顺序逐条比对，不一致 %d 条" % (len(cases), len(diff)))
    for (name, mine, theirs) in diff:
        print("  不一致 %-32s yh=%s oracle=%s" % (name, mine, theirs))
    return 1 if diff else 0


if __name__ == "__main__":
    raise SystemExit(main())
