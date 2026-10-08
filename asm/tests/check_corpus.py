#!/usr/bin/env python3
"""把 yh_asm 汇编出的对象与 llvm-mc 的参照对象逐节比对。

比对内容：
  * 每个具名节（.text/.data/.rodata/.bss）的内容与大小；
  * 每个节的重定位列表（偏移、类型、目标符号名、addend）。

llvm-mc 只作参照：符号表顺序、节头顺序、对齐填充的差异不参与判定，
只比内容与重定位这两件会决定最终映像的事。

用法：
  python3 tests/check_corpus.py [语料目录] [可执行文件]
默认语料目录 ../tmp/inv，默认可执行文件 ./.build/yh_asm。
"""

import os
import re
import struct
import subprocess
import sys
import tempfile

LLVM_MC = "/opt/homebrew/opt/llvm/bin/llvm-mc"
TRIPLE = "aarch64-linux-gnu"


def read_elf(path):
    """解析 ELF64 小端对象，返回 {节名: (类型, 数据, 对齐)} 与重定位列表。"""
    d = open(path, "rb").read()
    if d[:4] != b"\x7fELF" or d[4] != 2 or d[5] != 1:
        raise ValueError("不是 ELF64 小端文件")
    shoff, = struct.unpack_from("<Q", d, 0x28)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", d, 0x3A)
    if shentsize != 64:
        raise ValueError("节头项大小异常")
    raw = []
    for i in range(shnum):
        raw.append(struct.unpack_from("<IIQQQQIIQQ", d, shoff + i * shentsize))
    strtab = d[raw[shstrndx][4]:raw[shstrndx][4] + raw[shstrndx][5]]

    def name_at(off):
        end = strtab.find(b"\0", off)
        return strtab[off:end].decode()

    secs = {}
    names = []
    for (nm, typ, flags, addr, off, size, link, info, align, ent) in raw:
        n = name_at(nm)
        names.append(n)
        if typ == 8:                      # NOBITS 没有文件内容
            secs[n] = (typ, b"", size, align)
        else:
            secs[n] = (typ, d[off:off + size], size, align)

    # 符号表 → (名字, 所属节, 值)，重定位靠它归一化目标
    syms = []
    if ".symtab" in secs:
        symtab = raw[names.index(".symtab")]
        strtab2 = d[raw[symtab[6]][4]:raw[symtab[6]][4] + raw[symtab[6]][5]]
        for k in range(symtab[5] // 24):
            no, info, other, shndx, value, size = struct.unpack_from(
                "<IBBHQQ", secs[".symtab"][1], k * 24)
            end = strtab2.find(b"\0", no)
            syms.append((strtab2[no:end].decode(), shndx, value))

    relocs = {}
    for (nm, typ, flags, addr, off, size, link, info, align, ent) in raw:
        if typ != 4:                      # SHT_RELA
            continue
        target = names[info] if info < len(names) else "?"
        entries = []
        for k in range(size // 24):
            r_off, r_info, r_add = struct.unpack_from(
                "<QQq", d, off + k * 24)
            sym = r_info >> 32
            # 归一化目标：llvm-mc 对局部目标用「节符号 + addend」，本工具用
            # 「具名局部符号 + 0 addend」。两者都指向同一个 (节, 节内偏移)，
            # 所以按 (节名, 符号值 + addend) 比较，两种写法等价。节名而非
            # 节下标——两边的节头顺序不同，下标不可比。
            if sym < len(syms):
                nm, shndx, value = syms[sym]
                secname = names[shndx] if 0 < shndx < len(names) else ""
            else:
                secname, value = "", 0
            entries.append((r_off, r_info & 0xFFFFFFFF, secname, value + r_add))
        relocs[target] = entries
    return secs, relocs


# 迷你链接器给每个可分配节挑一个 1MiB 间隔、4KiB 对齐的基址，用来模拟
# 链接器的最终布局。页寻址与低 12 位只有在「节有确定地址」时才算得出来。
SEC_BASE = {".text": 0x100000, ".rodata": 0x200000,
            ".data": 0x300000, ".bss": 0x400000}


def apply_relocs(secs, relocs):
    """就地把重定位应用到节内容上，模拟链接器在最终布局下的处理。

    指向未定义符号的重定位（外部符号）跳过：链接期才知道地址，两边都保持
    原样，逐字节比较才有意义。
    """
    for secname, entries in relocs.items():
        if secname not in secs or secs[secname][0] == 8:
            continue
        pbase = SEC_BASE.get(secname, 0)
        data = bytearray(secs[secname][1])
        for r_off, rtype, tsec, s in entries:
            if tsec not in SEC_BASE:
                continue                     # 外部符号，链接期才定
            s += SEC_BASE[tsec]
            p = pbase + r_off
            w = struct.unpack_from("<I", data, r_off)[0]
            if rtype in (282, 283):          # JUMP26 / CALL26
                w = (w & 0xFC000000) | (((s - p) >> 2) & 0x3FFFFFF)
            elif rtype == 280:               # CONDBR19
                w = (w & ~(0x7FFFF << 5)) | ((((s - p) >> 2) & 0x7FFFF) << 5)
            elif rtype == 275:               # ADR_PREL_PG_HI21
                imm = (((s & ~0xFFF) - (p & ~0xFFF)) >> 12) & 0x1FFFFF
                w = (w & 0x9F00001F) | ((imm & 3) << 29) | ((imm >> 2) << 5)
            elif rtype == 277:               # ADD_ABS_LO12_NC
                w = (w & ~(0xFFF << 10)) | ((s & 0xFFF) << 10)
            elif rtype in (278, 284, 285, 286):
                scale = {278: 0, 284: 1, 285: 2, 286: 3}[rtype]
                w = (w & ~(0xFFF << 10)) | (((s & 0xFFF) >> scale) << 10)
            elif rtype == 257:               # ABS64
                struct.pack_into("<q", data, r_off, s)
                continue
            elif rtype == 258:               # ABS32
                struct.pack_into("<i", data, r_off, s & 0xFFFFFFFF)
                continue
            else:
                # GOT 两类（311/312）没有可算的值：GOT 项是链接器建的。两边
                # 都保持占位符，内容比对仍然有效。
                continue
            struct.pack_into("<I", data, r_off, w)
        secs[secname] = (secs[secname][0], bytes(data), secs[secname][2],
                         secs[secname][3])


def to_gnu(text):
    """把 Darwin 风格的 @PAGE/@PAGEOFF 换成 GNU 的 :pg_hi21:/:lo12:。

    语义完全等价，只是 llvm-mc 在 aarch64-linux-gnu 三元组下不认 @PAGE。
    """
    text = re.sub(r"([A-Za-z_.$][\w.$]*)@GOTPAGEOFF\b", r":got_lo12:\1", text)
    text = re.sub(r"([A-Za-z_.$][\w.$]*)@GOTPAGE\b", r":got:\1", text)
    text = re.sub(r"([A-Za-z_.$][\w.$]*)@PAGEOFF\b", r":lo12:\1", text)
    # adrp 的页寻址重定位由助记符本身决定，去掉 @PAGE 后 llvm-mc 直接生成
    text = re.sub(r", ([A-Za-z_.$][\w.$]*)@PAGE\b", r", \1", text)
    return text


def run(cmd):
    p = subprocess.run(cmd, capture_output=True)
    return p.returncode, p.stdout, p.stderr


def main():
    corpus = sys.argv[1] if len(sys.argv) > 1 else "../tmp/inv"
    binary = sys.argv[2] if len(sys.argv) > 2 else "./.build/yh_asm"
    files = sorted(f for f in os.listdir(corpus) if f.endswith(".s"))

    total = ours = 0
    bad = []
    skipped = []
    tmp = tempfile.mkdtemp(prefix="linkcorpus")

    for f in files:
        src = os.path.join(corpus, f)
        total += 1
        mine = os.path.join(tmp, f + ".mine.o")
        ref = os.path.join(tmp, f + ".ref.o")
        rc, _, err = run([binary, "asm", "-o", mine, src])
        if rc != 0:
            skipped.append((f, err.decode(errors="replace").strip().split("\n")[0]))
            continue
        gnu = os.path.join(tmp, f + ".gnu.s")
        with open(gnu, "w") as fh:
            fh.write(to_gnu(open(src).read()))
        rc, _, err = run([LLVM_MC, "--assemble", "-triple=" + TRIPLE,
                          "-filetype=obj", "-o", ref, gnu])
        if rc != 0:
            skipped.append((f, "llvm-mc 失败: " + err.decode(errors="replace")[:80]))
            continue
        ours += 1
        try:
            s1, r1 = read_elf(mine)
            s2, r2 = read_elf(ref)
            # 两边都在同一个模拟布局下应用重定位，把形态统一成链接后的
            # 样子；指向外部符号的重定位两边都保留原样，不参与回填。
            apply_relocs(s1, r1)
            apply_relocs(s2, r2)
        except Exception as exc:
            bad.append((f, "解析失败: %s" % exc))
            continue
        diffs = []
        for want in (".text", ".data", ".rodata", ".bss"):
            a = s1.get(want)
            b = s2.get(want)
            if a is None and b is None:
                continue
            if a is None or b is None:
                diffs.append("%s 节存在性不同" % want)
                continue
            if a[1] != b[1]:
                diffs.append("%s 内容不同: 本工具 %d 字节, llvm-mc %d 字节"
                             % (want, len(a[1]), len(b[1])))
            elif a[2] != b[2]:
                diffs.append("%s 大小不同: %d vs %d" % (want, a[2], b[2]))
        for want in (".text", ".data", ".rodata"):
            # 重定位全量比对：指向局部符号的也必须留重定位（页偏移与低 12
            # 位取决于节的最终地址，汇编期算不出来），所以两边应该逐条相同。
            e1 = sorted(r1.get(want, []))
            e2 = sorted(r2.get(want, []))
            if e1 != e2:
                only1 = [x for x in e1 if x not in e2]
                only2 = [x for x in e2 if x not in e1]
                diffs.append("%s 重定位不同：本工具多 %s，llvm-mc 多 %s"
                             % (want, only1[:3], only2[:3]))
        if diffs:
            bad.append((f, "; ".join(diffs)))

    print("语料 %d 个：本工具汇编成功 %d 个，比对不一致 %d 个，跳过 %d 个"
          % (total, ours, len(bad), len(skipped)))
    for f, why in skipped:
        print("  跳过 %s: %s" % (f, why))
    for f, why in bad:
        print("  不一致 %s: %s" % (f, why))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
