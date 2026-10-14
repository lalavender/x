#!/usr/bin/env python3
"""用容器里的 GNU 交叉链接器验证 yh_asm 产出的 ELF 对象：能链接、能跑、跑对。

为什么需要容器：宿主是 Darwin，没有 AArch64 的 ELF 链接器（无 GNU ld、无
lld），也没有 Linux 系统调用环境。容器一次补齐这两样。
（Linux 宿主不需要容器——用 tests/elf_link_native.py 的交叉 ld + qemu 门。）

判定是**差分式**的：同一份汇编分别由本工具和独立 oracle（llvm-mc 或 clang，
见 check_corpus.oracle_kind）汇编，两边都在容器里链成静态可执行并运行，要求
退出码与标准输出完全一致。这样门自己校准——遇到运行时桩不全导致的崩溃
（两个参照都崩），不会被误判成汇编器的错。

用法：python3 tests/elf_link_check.py [语料目录]
需要：docker 与本机可执行的 .build/yh_asm。
"""

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_corpus import to_gnu, oracle_kind, oracle_asm     # noqa: E402

TRIPLE = "aarch64-linux-gnu"
IMAGE = os.environ.get("LINK_IMAGE", "yh-link-elf:latest")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # asm/
BINARY = os.path.join(ROOT, ".build", "yh_asm")
BOX = os.path.join(os.path.dirname(ROOT), "tmp", "linkbox")          # 必须在工作区内


def host_asm(binary, src, dst):
    r = subprocess.run([binary, "asm", "-o", dst, src], capture_output=True)
    return r.returncode == 0


def ref_asm(kind, tool, src, dst):
    gnu = dst + ".gnu.s"
    with open(gnu, "w") as fh:
        fh.write(to_gnu(open(src).read()))
    return oracle_asm(kind, tool, gnu, dst, TRIPLE)


def main():
    corpus = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(ROOT), "tmp", "inv")
    if shutil.which("docker") is None:
        print("跳过：宿主没有 docker。Linux 宿主用 tests/elf_link_native.py"
              "（交叉 aarch64-linux-gnu-ld + qemu-aarch64）跑同一道差分门。")
        return 2
    kind, tool = oracle_kind()
    if kind == "":
        print("找不到独立 oracle：给 LLVM_MC=<llvm-mc 路径> 或把 clang 放进 PATH")
        return 2
    print("oracle: %s (%s)" % (kind, tool))
    for sub in ("obj", "ref", "bin"):
        os.makedirs(os.path.join(BOX, sub), exist_ok=True)
        for f in os.listdir(os.path.join(BOX, sub)):
            os.remove(os.path.join(BOX, sub, f))

    for f in ("start.s", "yhr.s"):
        if not host_asm(BINARY, os.path.join(ROOT, "tests", "elf", f),
                        os.path.join(BOX, f[:-2] + ".o")):
            print("运行时桩汇编失败：%s" % f)
            return 1

    names = []
    for f in sorted(os.listdir(corpus)):
        if not f.endswith(".s"):
            continue
        b = f[:-2]
        if host_asm(BINARY, os.path.join(corpus, f),
                    os.path.join(BOX, "obj", b + ".o")) and \
           ref_asm(kind, tool, os.path.join(corpus, f),
                   os.path.join(BOX, "ref", b + ".o")):
            names.append(b)
    print("可汇编对象：%d 个" % len(names))

    script = """
cd /w
n=0; bad=0; skip=0
for b in %s; do
  o1=1; r1=1
  aarch64-linux-gnu-ld -r -o /dev/null obj/$b.o 2>/dev/null || o1=0
  aarch64-linux-gnu-ld -r -o /dev/null ref/$b.o 2>/dev/null || r1=0
  if [ $o1 -ne $r1 ]; then echo "重定位链接结果不同 $b 本工具=$o1 参照=$r1"; bad=$((bad+1)); continue; fi
  if [ $o1 -eq 0 ]; then skip=$((skip+1)); continue; fi
  o2=1; r2=1
  aarch64-linux-gnu-ld -static -nostdlib -e _start -o bin/o_$b obj/$b.o start.o yhr.o 2>/dev/null || o2=0
  aarch64-linux-gnu-ld -static -nostdlib -e _start -o bin/r_$b ref/$b.o start.o yhr.o 2>/dev/null || r2=0
  if [ $o2 -ne $r2 ]; then echo "静态链接结果不同 $b 本工具=$o2 参照=$r2"; bad=$((bad+1)); continue; fi
  if [ $o2 -eq 0 ]; then skip=$((skip+1)); continue; fi
  oo=$(timeout 5 bin/o_$b 2>&1); orc=$?
  ro=$(timeout 5 bin/r_$b 2>&1); rrc=$?
  if [ "$oo" != "$ro" ] || [ "$orc" != "$rrc" ]; then
    echo "行为不一致 $b 本工具(退出码=$orc 输出=$oo) 参照(退出码=$rrc 输出=$ro)"; bad=$((bad+1)); continue
  fi
  n=$((n+1))
done
echo "行为一致 $n 个，不一致 $bad 个，两边同样链不上而跳过 $skip 个"
[ $bad -eq 0 ]
""" % " ".join(names)

    r = subprocess.run(["docker", "run", "--rm", "-v", BOX + ":/w", IMAGE,
                        "sh", "-c", script], capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    # 容器 stderr 只会有 shell 对崩溃程序的信号报告（两个参照崩得一样时属于
    # 已知情况），成功时不回显，避免噪声。
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
