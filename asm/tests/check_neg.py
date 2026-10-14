#!/usr/bin/env python3
"""拒绝路径与诊断质量的文件级门。

内建自检的**拒绝层**（asm/src/asm/70_selftest.yh 的 neg_selftest）验的是
「该拒绝的都拒绝了、该接受的都接受了」，但它把诊断关掉了（Ctx.quiet），
验不到诊断本身。本脚本在子进程里跑真实 CLI，逐条断言：

  1. 退出码为 1（输入/诊断错误；用法错误是 2，见 README 的退出码契约）；
  2. stderr 首行是 `<path>:<line>:<col>: 错误: <msg>` 形态（位置必须真实存在）；
  3. 诊断里出现期望的类别关键字。

用法：python3 tests/check_neg.py [可执行文件]
默认可执行文件 ./.build/yh_asm，语料目录 tests/asm-neg。
"""

import os
import re
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
CORPUS = os.path.join(TESTS, "asm-neg")
BIN = os.path.join(ROOT, ".build", "yh_asm")

# (语料文件, 期望诊断里出现的关键字)
CASES = [
    ("01-unknown-mnemonic.s", "不在冻结子集内的指令"),
    ("02-unknown-directive.s", "未知伪指令"),
    ("03-balign-not-pow2.s", ".balign 的对齐必须是 2 的幂"),
    ("04-branch-modifier.s", "分支目标只能是标签或数字"),
    ("05-undefined-local.s", "局部标签未定义"),
    ("06-type-unsupported.s", ".type 只支持 %function 与 %object"),
    ("07-got-narrow.s", "GOT 访存只支持 64 位宽度"),
    ("08-adrp-lo12.s", "adrp 需要符号"),
    ("09-width-mismatch.s", "位宽"),
    ("10-unterminated-comment.s", "块注释未闭合"),
]

POS_RE = re.compile(r"^.*:\d+:\d+: 错误: .+$")


def main():
    binary = sys.argv[1] if len(sys.argv) > 1 else BIN
    if not os.path.isfile(binary):
        print("缺 %s，先跑 `../yh build`" % binary)
        return 1
    failed = 0
    for name, keyword in CASES:
        src = os.path.join(CORPUS, name)
        if not os.path.isfile(src):
            print("  缺语料 %s" % src)
            failed += 1
            continue
        out = os.path.join("/tmp", name + ".o")
        r = subprocess.run([binary, "asm", "-o", out, src],
                           capture_output=True, text=True)
        problems = []
        if r.returncode != 1:
            problems.append("退出码 %d（期望 1）" % r.returncode)
        first = r.stderr.strip().split("\n")[0] if r.stderr.strip() else ""
        if not POS_RE.match(first):
            problems.append("诊断首行不是 <path>:<line>:<col>: 错误: 形态：%r" % first)
        if keyword not in r.stderr:
            problems.append("诊断里没有关键字 %r" % keyword)
        if problems:
            failed += 1
            print("  FAIL %s: %s" % (name, "; ".join(problems)))
            if first:
                print("       实际: %s" % first)
        else:
            print("  PASS %s: %s" % (name, first))
    print("拒绝路径 %d 条：失败 %d 条" % (len(CASES), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
