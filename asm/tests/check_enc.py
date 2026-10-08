#!/usr/bin/env python3
"""用 llvm-mc 复核 yh_asm 编码层的全部用例。

用法：python3 tests/check_enc.py

yh_asm --dump-enc 输出「指令文本<TAB>机器字」，本脚本把同一批文本交给
llvm-mc 汇编，逐条比对。llvm 规范化过别名的用例（movz→mov、uxtb→and、beq→b.eq 等）文本对不上，
退化为「机器字是否出现在本次 llvm 输出集合中」，仍算核对通过。
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, ".build", "yh_asm")
MC = os.environ.get("LLVM_MC", "/opt/homebrew/opt/llvm/bin/llvm-mc")


def dump_cases():
    r = subprocess.run([BIN, "--dump-enc"], capture_output=True, text=True, timeout=60)
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


def oracle(cases):
    """一次汇编全部文本，返回 {文本: 机器字}；失败的记进 bad。"""
    src = "\n".join(name for name, _ in cases)
    r = subprocess.run([MC, "--assemble", "-triple=aarch64-linux-gnu",
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


def main():
    if not os.path.exists(BIN):
        print("缺 %s，先跑 `yh run`" % BIN)
        return 1
    cases = dump_cases()
    found = oracle(cases)
    words = set("%08x" % w for w in found.values())
    direct = 0
    indirect = 0
    diff = []
    lost = []
    for name, word in cases:
        want = found.get(name)
        if want is None:
            # llvm 把别名规范化成了另一种写法（movz→mov、uxtb→and、beq→b.eq），
            # 文本对不上，退化成「本次输出的机器字集合里有没有它」
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
        print("  不一致 %-32s yh=%s llvm=%s" % (name, got, want))
    for (name, got) in lost:
        print("  缺失   %-32s yh=%s" % (name, got))
    return 1 if diff or lost else 0


if __name__ == "__main__":
    raise SystemExit(main())
