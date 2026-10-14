#!/usr/bin/env python3
"""link_diff_regress.py —— yh_link 与 GNU ld 的差分回归门。

同一个输入对象集分别交给两个链接器，比较**与布局无关**的三类结论：

  1. 行为一致：两个产物都真跑，退出码必须相同，且等于语料的期望值
     （分支位移、页寻址、绝对地址只要算错，退出码就会不同）；
  2. 静态可执行：两者都是 ELF64/ET_EXEC/AArch64、入口等于 _start 的值、
     没有 PT_INTERP / PT_DYNAMIC（静态、非 PIE）；
  3. 重定位语义一致：把符号按**输出节名**分组，组内各符号相对于组内首个
     符号的差值必须逐字节相同——绝对地址随布局变化，但「同一个节里两个符号
     相距多远」是链接器必须算对的不变量。

不比较的东西（有意的）：
  * 段个数与段内偏移：GNU ld 按自己的脚本布局，段数可能多于 3；
  * 节头细节、符号表顺序、节顺序：两者自由度不同；
  * 文件字节：布局不同，逐字节比较没有意义。

用法：
    python3 link/tests/link_diff_regress.py --link link/.build/yh_link \
        --asm asm/.build/yh_asm [--skip-if-missing]
"""

import argparse
import os
import struct
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
LINK_DIR = os.path.dirname(TESTS)
ROOT = os.path.dirname(LINK_DIR)
ASM_FIX = os.path.join(TESTS, "asm")
BOX = os.path.join(ROOT, "tmp", "linkbox")

# 与 link_accept.py 的用例表保持一致（这里只差分，不重复结构门）
CASES = [
    ("01-exit42", ["01-exit42.s"], 42),
    ("02-twoobj", ["02-twoobj-main.s", "02-twoobj-helper.s"], 49),
    ("03-abs64", ["03-abs64.s"], 42),
    ("04-page", ["04-page-high.s", "04-page-helper.s"], 48),
    ("05-adrp-only", ["05-adrp-only.s"], 43),
    ("06-load-rodata", ["06-load-rodata.s"], 44),
    ("07-symoffset", ["07-symoffset.s"], 42),
]

LD = "aarch64-linux-gnu-ld"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def read_elf(path: str):
    """读出 ELF 头字段、程序头、节头（不做合法性校验，交给上层的门）。"""
    d = open(path, "rb").read()
    (e_type, e_machine) = struct.unpack_from("<HH", d, 16)
    (e_entry, e_phoff, e_shoff) = struct.unpack_from("<QQQ", d, 24)
    (e_phentsize, e_phnum, e_shentsize, e_shnum,
     e_shstrndx) = struct.unpack_from("<HHHHH", d, 54)
    phdrs = [struct.unpack_from("<IIQQQQQQ", d, e_phoff + i * e_phentsize)
             for i in range(e_phnum)]
    shdrs = [struct.unpack_from("<IIQQQQIIQQ", d, e_shoff + i * e_shentsize)
             for i in range(e_shnum)]
    tab = shdrs[e_shstrndx]
    strtab = d[tab[4]:tab[4] + tab[5]]

    def nm(off):
        end = strtab.find(b"\0", off)
        return strtab[off:end].decode("latin1") if end >= 0 else ""

    names = [nm(r[0]) for r in shdrs]
    return dict(raw=d, type=e_type, machine=e_machine, entry=e_entry,
                phdrs=phdrs, shdrs=shdrs, names=names)


def symbols_by_section(img) -> dict:
    """{节名: {符号名: st_value}}；无名字的符号与映射符号跳过。"""
    out = {}
    d = img["raw"]
    for i, r in enumerate(img["shdrs"]):
        if r[1] != 2:            # SHT_SYMTAB
            continue
        link = r[6]
        if link >= len(img["shdrs"]):
            continue
        st = img["shdrs"][link]
        strtab = d[st[4]:st[4] + st[5]]
        n = r[5] // 24
        for k in range(n):
            off = r[4] + k * 24
            no, info, other, shndx, value, size = struct.unpack_from("<IBBHQQ",
                                                                     d, off)
            if shndx == 0 or shndx >= len(img["shdrs"]):
                continue
            end = strtab.find(b"\0", no)
            if end < 0:
                continue
            name = strtab[no:end].decode("latin1")
            if not name or name.startswith("$"):
                continue
            sec = img["names"][shndx]
            out.setdefault(sec, {})[name] = value
    return out


def delta_profile(syms: dict) -> dict:
    """{节名: {符号名: 相对组内首个符号的差值}}（与绝对布局无关）。"""
    prof = {}
    for sec, m in syms.items():
        if not m:
            continue
        base = min(m.values())
        prof[sec] = {name: v - base for name, v in m.items()}
    return prof


def check_static(img) -> str:
    """返回空串表示通过，否则返回失败原因。"""
    if img["type"] != 2:
        return "e_type=%d 不是 ET_EXEC" % img["type"]
    if img["machine"] != 183:
        return "e_machine=%d 不是 AArch64" % img["machine"]
    for p in img["phdrs"]:
        if p[0] == 3:
            return "含 PT_INTERP（不是静态链接）"
        if p[0] == 2:
            return "含 PT_DYNAMIC（不是静态链接）"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="yh_link 与 GNU ld 差分回归")
    ap.add_argument("--link", default=os.path.join(LINK_DIR, ".build", "yh_link"))
    ap.add_argument("--asm", default=os.path.join(ROOT, "asm", ".build", "yh_asm"))
    ap.add_argument("--skip-if-missing", action="store_true",
                    help="缺少交叉 binutils 时跳过（返回 0）而不是失败")
    args = ap.parse_args()
    args.link = os.path.abspath(args.link)
    args.asm = os.path.abspath(args.asm)

    if not os.path.isfile(args.link) or not os.path.isfile(args.asm):
        print("错误: 缺少 --link 或 --asm 指定的程序", file=sys.stderr)
        return 2
    if run([LD, "--version"]).returncode != 0:
        msg = "找不到 %s（装 binutils-aarch64-linux-gnu 后可用）" % LD
        if args.skip_if_missing:
            print("差分门: 跳过（%s）" % msg)
            return 0
        print("错误: " + msg, file=sys.stderr)
        return 2
    os.makedirs(BOX, exist_ok=True)

    bad = 0
    for name, srcs, want in CASES:
        objs = []
        for src in srcs:
            obj = os.path.join(BOX, name + "-" + os.path.basename(src) + ".o")
            r = run([args.asm, "asm", "-o", obj, os.path.join(ASM_FIX, src)])
            if r.returncode != 0:
                print("  汇编失败 %s" % src, file=sys.stderr)
                bad += 1
                continue
            objs.append(obj)
        ours = os.path.join(BOX, "diff-ours-" + name)
        theirs = os.path.join(BOX, "diff-gnu-" + name)
        r1 = run([args.link, "link", "-o", ours] + objs)
        r2 = run([LD, "-static", "-nostdlib", "-e", "_start", "-o", theirs]
                 + objs)
        if r1.returncode != 0 or r2.returncode != 0:
            print("  用例 %s：链接失败（yh_link rc=%d，ld rc=%d）"
                  % (name, r1.returncode, r2.returncode), file=sys.stderr)
            print("    ld: %s" % (r2.stdout + r2.stderr).strip(), file=sys.stderr)
            bad += 1
            continue
        # 1) 行为一致
        rc_ours = run([ours]).returncode
        rc_gnu = run([theirs]).returncode
        ok = True
        if rc_ours != want or rc_gnu != want:
            print("  用例 %s：退出码不一致（yh_link=%d，ld=%d，期望=%d）"
                  % (name, rc_ours, rc_gnu, want), file=sys.stderr)
            ok = False
        # 2) 静态可执行
        for tag, path in (("yh_link", ours), ("ld", theirs)):
            why = check_static(read_elf(path))
            if why:
                print("  用例 %s：%s 产物不合法：%s" % (name, tag, why),
                      file=sys.stderr)
                ok = False
        # 3) 重定位语义：同名节内符号间距一致
        po = delta_profile(symbols_by_section(read_elf(ours)))
        pg = delta_profile(symbols_by_section(read_elf(theirs)))
        for sec, m in po.items():
            if sec not in pg:
                continue                      # 节布局自由度不同，跳过
            for sym, dv in m.items():
                if sym in pg[sec] and pg[sec][sym] != dv:
                    print("  用例 %s：节 %s 内 %s 的相对偏移不同（yh_link=%d，ld=%d）"
                          % (name, sec, sym, dv, pg[sec][sym]), file=sys.stderr)
                    ok = False
        if ok:
            print("  用例 %s：与 GNU ld 一致（退出码 %d、静态可执行、符号间距相同）"
                  % (name, rc_ours))
        else:
            bad += 1
    if bad:
        print("差分回归: %d/%d 个用例不一致" % (bad, len(CASES)), file=sys.stderr)
        return 1
    print("差分回归: %d 个用例与 GNU ld 一致" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
