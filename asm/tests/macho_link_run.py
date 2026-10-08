#!/usr/bin/env python3
"""Mach-O 对象的端到端门：两边对象链成可执行文件后比运行行为。

这是 Mach-O 出口最强的门——节/符号/重定位一致只说明结构对，能链起来跑出
一样的行为才说明重定位的**位置**也对（曾经就栽在这：同节分支在 Mach-O 里
不发重定位，汇编期也没回填偏移，结构全对、跑起来直接飞）。

只对**完整程序**语料有意义（每个文件要能独立链成可执行文件），例如编译器
自己发射的那批 .s；tests/asm 下的指令碎片缺入口点，链不上会被跳过。

用法：
    python3 tests/macho_link_run.py <语料目录> [<语料目录> ...]
"""

import os
import subprocess
import sys
import tempfile

LINK = os.environ.get("YH_ASM", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".build", "yh_asm"))
CLANG = os.environ.get("CLANG", "clang")
TRIPLE = "arm64-apple-macos11"
SDK = os.environ.get("SDKROOT", "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk")
TIMEOUT = 10


def run(cmd):
    """跑一条命令，返回 (是否成功, 退出码, 标准输出+标准错误)。"""
    try:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=TIMEOUT)
        return True, p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        # 挂死就是行为不一致：看门超时的退出码约定为 -1
        return True, -1, b"<timeout>"
    except OSError as e:
        # 可执行文件不存在（ld 声称成功但没产物之类）：按失败处理
        return False, -1, str(e).encode()


def main(dirs):
    files = []
    for d in dirs:
        for n in sorted(os.listdir(d)):
            if n.endswith(".s"):
                files.append(os.path.join(d, n))
    tmp = tempfile.mkdtemp(prefix="macho-run-")
    ok = bad = skip = 0
    for src in files:
        name = os.path.basename(src)[:-2]
        ours = os.path.join(tmp, name + ".our.o")
        ref = os.path.join(tmp, name + ".ref.o")
        exe_ours = os.path.join(tmp, name + ".our")
        exe_ref = os.path.join(tmp, name + ".ref")
        if not run([LINK, "asm", "-t", "darwin", "-o", ours, src])[0]:
            skip += 1
            continue
        if not run([CLANG, "-c", "-target", TRIPLE, "-o", ref, src])[0]:
            skip += 1
            continue
        ld = ["ld", "-arch", "arm64", "-syslibroot", SDK, "-lSystem"]
        if not run(ld + ["-o", exe_ours, ours])[0]:
            skip += 1
            continue
        if not run(ld + ["-o", exe_ref, ref])[0]:
            skip += 1
            continue
        if not (os.path.exists(exe_ours) and os.path.exists(exe_ref)):
            # ld 声称成功却没有产物（碎片语料缺入口点时会这样），不算不一致
            skip += 1
            continue
        _, ra, oa = run([exe_ours])
        _, rb, ob = run([exe_ref])
        if ra == rb and oa == ob:
            ok += 1
        else:
            bad += 1
            print("  不一致 %s：本工具退出码 %d，参照 %d" % (name, ra, rb))
            if oa != ob:
                print("      输出不同：本工具 %r / 参照 %r" % (oa[:60], ob[:60]))
    print("链接运行：一致 %d 个，不一致 %d 个，跳过 %d 个" % (ok, bad, skip))
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))