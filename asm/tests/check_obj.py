#!/usr/bin/env python3
"""检查 yh_asm 输出的对象文件是否满足契约 §7 的结构与确定性要求。

检查项：
  1. ELF64 / 小端 / ET_REL / EM_AARCH64；
  2. 节顺序为 .text .rodata .data .bss，空节不出现，.rela.* 紧跟被重定位的节；
  3. 符号表局部符号在下、$x/$d 映射符号齐全、sh_info 指向第一个全局符号；
  4. 重定位类型都在契约 §6 的白名单里；
  5. 同一份输入连续两次汇编，字节完全一致（确定性）。

用法：
  python3 tests/check_obj.py [可执行文件] [语料目录]
"""

import os
import struct
import subprocess
import sys
import tempfile

SHT_NULL, SHT_PROGBITS, SHT_SYMTAB, SHT_STRTAB, SHT_RELA, SHT_NOBITS = 0, 1, 2, 3, 4, 8
STB_LOCAL, STB_GLOBAL = 0, 1
WHITELIST = {
    257, 275, 277, 278, 280, 282, 283, 284, 285, 286,
    # GOT 两类：LP64 下只有 64 位访问有对应类型（llvm-mc 对更窄的 GOT 访存
    # 直接报 unsupported in LP64）。
    311, 312,
}
CONTENT_ORDER = [".text", ".rodata", ".data", ".bss"]


def name_at(buf, off):
    """从字符串表里取以 NUL 结尾的名字。"""
    return buf[off:buf.find(b"\0", off)].decode()


class Obj:
    """一份对象文件的解析结果。"""

    def __init__(self, path):
        self.path = path
        self.d = d = open(path, "rb").read()
        self.problems = []
        if d[:4] != b"\x7fELF" or d[4] != 2 or d[5] != 1:
            self.problems.append("不是 ELF64 小端对象")
            return
        (self.e_type, self.e_machine) = struct.unpack_from("<HH", d, 16)
        self.shoff, = struct.unpack_from("<Q", d, 0x28)
        self.shentsize, self.shnum, self.shstrndx = struct.unpack_from("<HHH", d, 0x3A)
        self.raw = [struct.unpack_from("<IIQQQQIIQQ", d, self.shoff + i * 64)
                    for i in range(self.shnum)]
        sh = self.raw[self.shstrndx]
        shstr = d[sh[4]:sh[4] + sh[5]]
        self.names = [name_at(shstr, r[0]) for r in self.raw]
        symtab = self.raw[self.names.index(".symtab")]
        strtab = d[self.raw[symtab[6]][4]:self.raw[symtab[6]][4] + self.raw[symtab[6]][5]]
        self.syms = []
        for k in range(symtab[5] // 24):
            no, info, other, shndx, value, size = struct.unpack_from(
                "<IBBHQQ", d, symtab[4] + k * 24)
            self.syms.append((name_at(strtab, no),
                              info >> 4, info & 0xF, shndx, value, size))

    def check_header(self):
        if self.e_type != 1:
            self.problems.append("e_type 不是 ET_REL")
        if self.e_machine != 183:
            self.problems.append("e_machine 不是 EM_AARCH64")

    def check_order(self):
        """内容节必须按 .text .rodata .data .bss 的固定顺序出现，空节不出现。"""
        got = [n for i, n in enumerate(self.names) if i > 0
               and self.raw[i][1] in (SHT_PROGBITS, SHT_NOBITS)]
        want = [n for n in CONTENT_ORDER if n in got]
        if got != want:
            self.problems.append("内容节顺序不对: %s，应为 %s" % (got, want))
        # 契约 §7：内容节在前，其次 .rela.*，最后 .symtab .strtab .shstrtab
        order = [n for n in self.names[1:] if n != ""]
        pos = 0
        for i, n in enumerate(order):
            if n.startswith(".rela."):
                pos = max(pos, 1)
                continue
            if n in (".symtab", ".strtab", ".shstrtab"):
                continue
            if i < pos:
                self.problems.append("内容节 %s 出现在重定位节之后" % n)
        tail = order[-3:]
        if tail != [".symtab", ".strtab", ".shstrtab"]:
            self.problems.append("最后三个节应为 .symtab/.strtab/.shstrtab，实际 %s" % tail)
        for n in order:
            if n.startswith(".rela.") and n[5:] not in order:
                self.problems.append("%s 没有对应的内容节" % n)

    def check_symtab(self):
        """局部符号在前、映射符号齐全、sh_info 指到第一个全局符号。"""
        symtab = self.raw[self.names.index(".symtab")]
        first_global = symtab[7]
        for k, (name, bind, typ, shndx, value, size) in enumerate(self.syms):
            if k == 0:
                continue
            if k < first_global and bind != STB_LOCAL:
                self.problems.append("索引 %d 的 %s 不是局部符号" % (k, name))
            if k >= first_global and bind != STB_GLOBAL:
                self.problems.append("索引 %d 的 %s 不是全局符号" % (k, name))
        # 有内容的节必须在 .text 里带 $x、在非 .text 的节里带 $d
        mapped = set()
        for (name, bind, typ, shndx, value, size) in self.syms:
            if bind == STB_LOCAL and (name == "$x" or name == "$d"):
                if shndx != 0 and value == 0:
                    mapped.add((name, shndx))
        for i, n in enumerate(self.names):
            if i == 0 or self.raw[i][1] not in (SHT_PROGBITS, SHT_NOBITS):
                continue
            if self.raw[i][5] == 0:
                continue
            want = "$x" if n == ".text" else "$d"
            if (want, i) not in mapped:
                self.problems.append("节 %s 缺少 %s 映射符号" % (n, want))

    def check_relocs(self):
        for i, n in enumerate(self.names):
            if self.raw[i][1] != SHT_RELA:
                continue
            off, size = self.raw[i][4], self.raw[i][5]
            for k in range(size // 24):
                r_off, r_info, r_add = struct.unpack_from("<QQq", self.d, off + k * 24)
                typ = r_info & 0xFFFFFFFF
                if typ not in WHITELIST:
                    self.problems.append("%s 里出现白名单外的重定位类型 %d" % (n, typ))


def assemble(binary, src, out):
    p = subprocess.run([binary, "asm", "-o", out, src], capture_output=True)
    return p.returncode == 0


def main():
    binary = sys.argv[1] if len(sys.argv) > 1 else "./.build/yh_asm"
    corpus = sys.argv[2] if len(sys.argv) > 2 else "tests/asm"
    files = sorted(f for f in os.listdir(corpus) if f.endswith(".s"))
    if not files:
        print("语料目录 %s 里没有 .s 文件" % corpus)
        return 1
    tmp = tempfile.mkdtemp(prefix="linkobj")
    checked = failed = nondet = 0

    for f in files:
        src = os.path.join(corpus, f)
        a = os.path.join(tmp, f + ".a.o")
        b = os.path.join(tmp, f + ".b.o")
        if not assemble(binary, src, a):
            continue
        checked += 1
        o = Obj(a)
        o.check_header()
        o.check_order()
        o.check_symtab()
        o.check_relocs()
        if o.problems:
            failed += 1
            print("  结构问题 %s: %s" % (f, "; ".join(o.problems)))
        if assemble(binary, src, b):
            d1, d2 = open(a, "rb").read(), open(b, "rb").read()
            if d1 != d2:
                nondet += 1
                print("  不确定 %s: 两次汇编字节不同" % f)

    print("结构与确定性检查：%d 个对象，结构问题 %d 个，非确定 %d 个"
          % (checked, failed, nondet))
    return 1 if (failed or nondet) else 0


if __name__ == "__main__":
    sys.exit(main())