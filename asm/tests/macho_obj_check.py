#!/usr/bin/env python3
"""Mach-O arm64 可重定位对象的读取与差分比对。

用途：给 yh_asm 的 Mach-O 出口当 oracle。llvm-mc/clang 对同一份汇编产出的
对象在节、符号、重定位三个层面必须与本工具一致（不要求文件逐字节相同——
符号可以按不同顺序排、节也可以有 clang 自己的补充节）。

用法：
    python3 tests/macho_obj_check.py a.o b.o     # 差分比对
    python3 tests/macho_obj_check.py a.o         # 打印结构
"""

import re
import struct
import sys

MH_MAGIC_64 = 0xFEEDFACF
MH_OBJECT = 1
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2
LC_DYSYMTAB = 0xB

# nlist_64 的 n_type 位
N_STAB, N_PEXT, N_TYPE, N_EXT = 0xE0, 0x10, 0x0E, 0x01
N_UNDF, N_ABS, N_SECT, N_PBUD, N_INDR = 0x0, 0x2, 0xE, 0xC, 0xA

# mach-o/arm64/reloc.h
RELOC_NAMES = {
    0: "UNSIGNED", 1: "SUBTRACTOR", 2: "BRANCH26", 3: "PAGE21",
    4: "PAGEOFF12", 5: "GOT_LOAD_PAGE21", 6: "GOT_LOAD_PAGEOFF12",
    7: "POINTER_TO_GOT", 8: "TLVP_LOAD_PAGE21", 9: "TLVP_LOAD_PAGEOFF12",
    10: "ADDEND", 11: "AUTHENTICATED_POINTER",
}


def cstr(buf, off, n):
    return buf[off:off + n].split(b"\0")[0].decode("utf-8", "replace")


class MachO(object):
    """一个 Mach-O 对象的结构化视图：节、符号、重定位。"""

    def __init__(self, path):
        self.path = path
        d = open(path, "rb").read()
        self.d = d
        (magic, cputype, cpusub, filetype, ncmds, sizeofcmds, flags, res
         ) = struct.unpack_from("<IiiIIIII", d, 0)
        if magic != MH_MAGIC_64:
            raise ValueError("%s: 不是 64 位 Mach-O（magic %#x）" % (path, magic))
        self.cputype = cputype
        self.filetype = filetype
        self.flags = flags
        self.sections = []          # [(seg, sect, addr, size, off, align, flags)]
        self.symtab = []            # [(name, n_type, n_sect, n_desc, n_value)]
        self.relocs = {}            # "seg,sect" -> [(addr, pcrel, len, ext, type, sym)]
        self.symoff = self.nsyms = self.stroff = self.strlen = 0

        o = 32
        for _ in range(ncmds):
            cmd, cmdsize = struct.unpack_from("<II", d, o)
            if cmd == LC_SEGMENT_64:
                self._segment(d, o)
            elif cmd == LC_SYMTAB:
                (self.symoff, self.nsyms, self.stroff, self.strlen
                 ) = struct.unpack_from("<IIII", d, o + 8)
            o += cmdsize
        self._symbols()
        self._relocs()
        # 重定位内容要用符号名而不是符号下标来比，下标顺序两边不一定一样
        self.relocs = {k: [self._named(v) for v in vs]
                       for k, vs in self.relocs.items()}

    def _segment(self, d, o):
        fileoff, filesize, nsects = struct.unpack_from("<QQ", d, o + 40)[0], \
            struct.unpack_from("<QQ", d, o + 48)[0], \
            struct.unpack_from("<I", d, o + 64)[0]
        so = o + 72
        for _ in range(nsects):
            sn = cstr(d, so, 16)
            sg = cstr(d, so + 16, 16)
            addr, size, off, align, reloff, nreloc, sflags = \
                struct.unpack_from("<QQIIIII", d, so + 32)
            self.sections.append((sg, sn, addr, size, off, align, sflags,
                                  reloff, nreloc))
            so += 80

    def _symbols(self):
        for i in range(self.nsyms):
            strx, n_type, n_sect, n_desc, n_value = \
                struct.unpack_from("<IBBHQ", self.d, self.symoff + i * 16)
            name = cstr(self.d, self.stroff + strx, self.strlen)
            self.symtab.append((name, n_type, n_sect, n_desc, n_value))

    def _relocs(self):
        for (sg, sn, addr, size, off, align, sflags, reloff, nreloc
             ) in self.sections:
            out = []
            for i in range(nreloc):
                r_address, word = struct.unpack_from("<iI", self.d, reloff + i * 8)
                pcrel = (word >> 24) & 1
                length = (word >> 25) & 3
                extern = (word >> 27) & 1
                rtype = (word >> 28) & 0xF
                sym = word & 0xFFFFFF
                out.append((r_address, pcrel, length, extern, rtype, sym))
            self.relocs["%s,%s" % (sg, sn)] = out

    def _named(self, r):
        """把符号下标换成名字；局部符号带节名限定，避免不同节同名标签撞车。"""
        addr, pcrel, length, extern, rtype, sym = r
        if extern or sym >= len(self.symtab):
            try:
                nm = self.symtab[sym][0]
            except IndexError:
                nm = "#%d" % sym
        else:
            nm = "#%d" % sym
        return (addr, pcrel, length, extern, RELOC_NAMES.get(rtype, str(rtype)), nm)

    def dump(self):
        print("%s: cputype=%d filetype=%d flags=%#x"
              % (self.path, self.cputype, self.filetype, self.flags))
        for (sg, sn, addr, size, off, align, sflags, reloff, nreloc
             ) in self.sections:
            print("  节 %s,%s addr=%#x size=%#x off=%d align=2^%d flags=%#x nreloc=%d"
                  % (sg, sn, addr, size, off, align, sflags, nreloc))
        globals_ = [(n, v) for (n, t, s, dsc, v) in self.symtab
                    if (t & N_EXT) and (t & N_TYPE) == N_SECT]
        undef = [n for (n, t, s, dsc, v) in self.symtab
                 if (t & N_TYPE) == N_UNDF and (t & N_EXT)]
        locals_ = [n for (n, t, s, dsc, v) in self.symtab
                   if (t & N_TYPE) == N_SECT and not (t & N_EXT)]
        print("  全局定义 %d 个: %s" % (len(globals_), sorted(globals_)[:6]))
        print("  未定义 %d 个: %s" % (len(undef), sorted(undef)[:6]))
        print("  局部 %d 个" % len(locals_))
        for k in sorted(self.relocs):
            if self.relocs[k]:
                print("  重定位 %s: %d 条" % (k, len(self.relocs[k])))
                for r in self.relocs[k][:8]:
                    print("     %s" % (r,))


# clang 会为内部临时标签发 ltmpN 符号，那是 MC 的私有产物，本工具不发。
IGNORE_SYM = re.compile(r"^ltmp\d+$")


def _sect_base(obj, sectno):
    """节号（1 基）→ 该节的段内起始地址。"""
    if 1 <= sectno <= len(obj.sections):
        return obj.sections[sectno - 1][2]
    return 0


def compare(pa, pb):
    """语义差分：节集合与大小、符号集合与**节内偏移**、每节重定位三元组。

    刻意不比节的 addr：两边对 .data 的对齐取法不同（本工具按 8，clang 按 1），
    节的段内起点因此整体平移，链接器不在乎，但会让逐字节比对全红。真正要
    一致的是符号在自己节里的偏移，以及重定位的作用地址。
    """
    a, b = MachO(pa), MachO(pb)
    bad = []
    if a.cputype != b.cputype:
        bad.append("cputype 不同 %d vs %d" % (a.cputype, b.cputype))
    sa = {("%s,%s" % (sg, sn)): size
          for (sg, sn, addr, size, off, align, sflags, ro, nr) in a.sections}
    sb = {("%s,%s" % (sg, sn)): size
          for (sg, sn, addr, size, off, align, sflags, ro, nr) in b.sections}
    for k in sorted(set(sa) | set(sb)):
        if k not in sa:
            bad.append("少了节 %s" % k)
        elif k not in sb:
            bad.append("多了节 %s" % k)
        elif sa[k] != sb[k]:
            bad.append("节 %s 大小不同 %d vs %d" % (k, sa[k], sb[k]))
    na = {n: (t & N_TYPE, t & N_EXT, sec, v - _sect_base(a, sec))
          for (n, t, sec, dsc, v) in a.symtab if not IGNORE_SYM.match(n)}
    nb = {n: (t & N_TYPE, t & N_EXT, sec, v - _sect_base(b, sec))
          for (n, t, sec, dsc, v) in b.symtab if not IGNORE_SYM.match(n)}
    for n in sorted(set(na) | set(nb)):
        if n not in na:
            bad.append("少了符号 %s" % n)
        elif n not in nb:
            bad.append("多了符号 %s" % n)
        elif na[n] != nb[n]:
            bad.append("符号 %s 不同 %s vs %s" % (n, na[n], nb[n]))
    for k in sorted(set(a.relocs) | set(b.relocs)):
        ra, rb = a.relocs.get(k, []), b.relocs.get(k, [])
        if ra != rb:
            only_a = [x for x in ra if x not in rb][:3]
            only_b = [x for x in rb if x not in ra][:3]
            bad.append("重定位 %s 不同：仅本工具 %s；仅参照 %s"
                       % (k, only_a, only_b))
    return bad


def main():
    if len(sys.argv) == 2:
        MachO(sys.argv[1]).dump()
        return 0
    if len(sys.argv) == 3:
        bad = compare(sys.argv[1], sys.argv[2])
        for b in bad:
            print("  差异 %s" % b)
        if bad:
            print("不一致 %d 处" % len(bad))
            return 1
        print("节/符号/重定位一致")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
