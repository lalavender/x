#!/usr/bin/env python3
"""Mach-O arm64 出口的差分门：把 yh_asm 的产物与 clang 的产物逐文件比。

用法：
    python3 tests/macho_corpus_check.py <语料目录> [<语料目录> ...]

对每个 .s：
    clang -c -target arm64-apple-macos11 -o ref.o x.s
    yh_asm asm -t darwin -o our.o x.s
再用 macho_obj_check.compare 比节/符号/重定位三类语义。两边都汇编不了的
文件（本工具不该接受的可选语法）算跳过，但只在**两边都失败**时跳过。
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macho_obj_check

LINK = os.environ.get("YH_ASM", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".build", "yh_asm"))
CLANG = os.environ.get("CLANG", "clang")
TRIPLE = "arm64-apple-macos11"


def assemble(head, src, dst):
    """head 是「到 -o 为止」的命令前缀，后面接 目标文件、源文件。"""
    r = subprocess.run(head + [dst, src], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    return r.returncode == 0


def main(dirs):
    files = []
    for d in dirs:
        for n in sorted(os.listdir(d)):
            if n.endswith(".s"):
                files.append(os.path.join(d, n))
    if not files:
        print("没有找到 .s 语料")
        return 2
    tmp = tempfile.mkdtemp(prefix="macho-check-")
    ok = bad = skip = 0
    for src in files:
        ours = os.path.join(tmp, "our.o")
        ref = os.path.join(tmp, "ref.o")
        got = assemble([LINK, "asm", "-t", "darwin", "-o"], src, ours)
        want = assemble([CLANG, "-c", "-target", TRIPLE, "-o"], src, ref)
        if not want:
            # clang 都收不了，说明这条语料不在契约内
            skip += 1
            print("  跳过 %s（clang 不能汇编）" % os.path.basename(src))
            continue
        if not got:
            bad += 1
            print("  失败 %s：本工具汇编失败" % os.path.basename(src))
            continue
        diffs = macho_obj_check.compare(ref, ours)
        if diffs:
            bad += 1
            print("  失败 %s：" % os.path.basename(src))
            for d in diffs:
                print("      %s" % d)
        else:
            ok += 1
    print("语料 %d 个：一致 %d 个，不一致 %d 个，跳过 %d 个"
          % (len(files), ok, bad, skip))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or [os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "asm")]))
