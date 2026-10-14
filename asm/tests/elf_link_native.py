#!/usr/bin/env python3
"""Linux 宿主上的 ELF 链接运行差分门（不依赖 docker）。

判定与容器门 tests/elf_link_check.py 一致，只是把「容器里的 GNU 交叉链接器」
换成宿主上的交叉 binutils + qemu：同一份汇编分别由本工具与独立 oracle
（llvm-mc 或 clang，见 check_corpus.oracle_kind）汇编，两边各自用同一套运行时
桩（tests/elf/start-linux.s）静态链接成可执行，再运行比对退出码与标准输出。

差分语义：两边同样链不上（例如缺运行时符号）计为**跳过**并记录原因，不误判成
汇编器的错；只有「一边成功一边失败」或「两边都跑起来但行为不同」才是不一致。

用法：
  python3 tests/elf_link_native.py [语料目录...] [--bin 可执行文件]
默认语料目录 ../tmp/inv，默认可执行文件 ./.build/yh_asm。
需要：aarch64-linux-gnu-ld（LD 可覆盖）、qemu-aarch64（QEMU 可覆盖，
      没有 qemu 时按 binfmt 直接执行）、独立 oracle。
"""

import os
import shutil
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS)
from check_corpus import oracle_kind, oracle_asm, to_gnu      # noqa: E402

ROOT = os.path.dirname(TESTS)                                  # asm/
REPO = os.path.dirname(ROOT)
BINARY = os.path.join(ROOT, ".build", "yh_asm")
BOX = os.path.join(REPO, "tmp", "elf-native")                  # 中间产物
TRIPLE = "aarch64-linux-gnu"
STUBS = [os.path.join(TESTS, "elf", "start-linux.s"),
         os.path.join(TESTS, "elf", "yhr-linux.s")]
TIMEOUT = 5


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def link(ld, out, objs):
    """ld -static -nostdlib -e _start -o out objs...；返回 rc。"""
    return run([ld, "-static", "-nostdlib", "-e", "_start", "-o", out] + objs).returncode


def execute(runner, path):
    """跑一个 aarch64 可执行文件，返回 (退出码, stdout)。超时记 -1。"""
    try:
        p = run(runner + [path], timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return (-1, "")
    return (p.returncode, p.stdout)


def main():
    argv = sys.argv[1:]
    binary = BINARY
    if "--bin" in argv:
        i = argv.index("--bin")
        if i + 1 >= len(argv):
            print("--bin 后面需要可执行文件路径")
            return 2
        binary = argv[i + 1]
        del argv[i:i + 2]
    corpora = argv if argv else [os.path.join(REPO, "tmp", "inv")]

    ld = os.environ.get("LD", "aarch64-linux-gnu-ld")
    if shutil.which(ld) is None:
        print("跳过：宿主没有 %s（Linux 的 ELF 链接门需要交叉 binutils）" % ld)
        return 2
    qemu = os.environ.get("QEMU", "qemu-aarch64")
    runner = [qemu] if shutil.which(qemu) else []
    kind, tool = oracle_kind()
    if kind == "":
        print("找不到独立 oracle：给 LLVM_MC=<llvm-mc 路径> 或把 clang 放进 PATH")
        return 2
    if not os.path.exists(binary):
        print("缺 %s，先跑 `../yh build`" % binary)
        return 1
    print("链接器: %s；运行: %s；oracle: %s (%s)"
          % (ld, " ".join(runner) if runner else "直接执行", kind, tool))

    for sub in ("obj", "ref", "bin"):
        d = os.path.join(BOX, sub)
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            os.unlink(os.path.join(d, f))

    # 运行时桩两侧各用自己的汇编产物，桩本身的编码问题同样是差分的一部分。
    ours_stubs = []
    ref_stubs = []
    for stub in STUBS:
        ours = os.path.join(BOX, "obj", os.path.basename(stub)[:-2] + ".o")
        ref = os.path.join(BOX, "ref", os.path.basename(stub)[:-2] + ".o")
        if run([binary, "asm", "-o", ours, stub]).returncode != 0:
            print("本工具汇编运行时桩失败：%s" % stub)
            return 1
        if not oracle_asm(kind, tool, stub, ref, TRIPLE):
            print("oracle 汇编运行时桩失败：%s" % stub)
            return 1
        ours_stubs.append(ours)
        ref_stubs.append(ref)

    total = same = bad = skipped = 0
    bad_list = []
    skip_list = []
    for corpus in corpora:
        if not os.path.isdir(corpus):
            continue
        for f in sorted(os.listdir(corpus)):
            if not f.endswith(".s"):
                continue
            total += 1
            b = f[:-2]
            src = os.path.join(corpus, f)
            o_obj = os.path.join(BOX, "obj", b + ".o")
            r_obj = os.path.join(BOX, "ref", b + ".o")
            o_bin = os.path.join(BOX, "bin", "o_" + b)
            r_bin = os.path.join(BOX, "bin", "r_" + b)
            gnu = os.path.join(BOX, "ref", b + ".gnu.s")
            with open(gnu, "w") as fh:
                fh.write(to_gnu(open(src).read()))
            o_ok = run([binary, "asm", "-o", o_obj, src]).returncode == 0
            r_ok = oracle_asm(kind, tool, gnu, r_obj, TRIPLE)
            # 差分语义优先：一边拒绝一边接受是**方言分歧**，要人看；两边都拒绝
            #（例如符号名与寄存器同名，clang 同样拒）才计跳过。
            if not o_ok and not r_ok:
                skipped += 1
                skip_list.append((corpus, f, "两边都拒绝汇编"))
                continue
            if o_ok != r_ok:
                bad += 1
                bad_list.append((corpus, f, "接受面不同：本工具=%s 参照=%s"
                                 % (o_ok, r_ok)))
                continue
            if not o_ok:
                skipped += 1
                skip_list.append((corpus, f, "汇编失败"))
                continue

            o_rc = link(ld, o_bin, [o_obj] + ours_stubs)
            r_rc = link(ld, r_bin, [r_obj] + ref_stubs)
            if (o_rc == 0) != (r_rc == 0):
                bad += 1
                bad_list.append((corpus, f, "链接结果不同：本工具=%d 参照=%d"
                                 % (o_rc, r_rc)))
                continue
            if o_rc != 0:
                skipped += 1
                skip_list.append((corpus, f, "两边同样链不上（缺入口/运行时符号）"))
                continue

            o_out = execute(runner, o_bin)
            r_out = execute(runner, r_bin)
            if o_out != r_out:
                bad += 1
                bad_list.append((corpus, f, "行为不同：本工具=%s 参照=%s"
                                 % (o_out, r_out)))
                continue
            same += 1

    print("语料 %d 个：行为一致 %d 个，不一致 %d 个，跳过 %d 个"
          % (total, same, bad, skipped))
    for corpus, f, why in bad_list:
        print("  不一致 %s/%s: %s" % (os.path.basename(corpus), f, why))
    for corpus, f, why in skip_list:
        print("  跳过 %s/%s: %s" % (os.path.basename(corpus), f, why))
    if total == 0:
        print("语料目录为空：%s" % ", ".join(corpora))
        return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
