#!/usr/bin/env python3
"""link_accept.py —— yh_link 端到端验收门（汇编 → 链接 → 结构核对 → 真跑）。

链路完全走命令行，两个项目只通过 ELF ET_REL 对象通信（用户要求 link/ 与
asm/ 解耦，本脚本因此**不 import** 汇编器的任何 Python 模块）：

    yh_asm asm  -o x.o   link/tests/asm/x.s
    yh_link link -o x    x.o [y.o ...]
    ./x                  → 退出码必须等于期望值

每个用例三件事都要过：

  1. **可运行**：产物在当前宿主上真跑（aarch64 宿主原生跑；x86_64 + qemu-user
     下经 binfmt 模拟跑，验证记录里要写明是模拟）；
  2. **结构**：ELF64/ET_EXEC/AArch64、3 个 PT_LOAD、段同余与 filesz ≤ memsz、
     RW 段不可执行、e_shstrndx 指向真正的 .shstrtab、.symtab 的 sh_link 指向
     真正的 .strtab（这两条是「产物合法」的最低要求，外部工具读节名/符号名
     要靠它们）；
  3. **确定性**：同一输入链接两次，产物逐字节相同。

用法：
    python3 link/tests/link_accept.py --link link/.build/yh_link \
        --asm asm/.build/yh_asm
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

# 用例表：(名称, 源文件列表, 期望退出码, 说明)
# 期望退出码由语料自身的语义决定，见各 .s 文件头部的说明。
CASES = [
    ("01-exit42", ["01-exit42.s"], 42,
     "最小可执行：单对象、无外部符号、无数据"),
    ("02-twoobj", ["02-twoobj-main.s", "02-twoobj-helper.s"], 49,
     "多对象：跨对象 CALL26 + 跨对象 adrp/add 数据取址"),
    ("03-abs64", ["03-abs64.s"], 42,
     "绝对地址：.data 里的 .xword 回填目标最终地址，blr 过去可用"),
    ("04-page", ["04-page-high.s", "04-page-helper.s"], 48,
     "非零页差 ADRP + 跨 64 KiB 的长距离 CALL26"),
    ("05-adrp-only", ["05-adrp-only.s"], 43,
     "只取址不访存：把页寻址重定位与访存问题分开"),
    ("06-load-rodata", ["06-load-rodata.s"], 44,
     "跨段访存：从 .rodata 读一个字"),
    ("07-symoffset", ["07-symoffset.s"], 42,
     "符号取值：节内偏移非 0 的标签（跨对象错位的根因）"),
]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def read_image_structure(path: str):
    """读出映像的关键结构字段，返回 dict；解析失败抛 ValueError。"""
    d = open(path, "rb").read()
    if len(d) < 64 or d[:4] != b"\x7fELF":
        raise ValueError("不是 ELF 文件")
    (e_type, e_machine) = struct.unpack_from("<HH", d, 16)
    (e_entry, e_phoff, e_shoff) = struct.unpack_from("<QQQ", d, 24)
    (e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum,
     e_shstrndx) = struct.unpack_from("<HHHHHH", d, 52)
    phdrs = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        (p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz,
         p_align) = struct.unpack_from("<IIQQQQQQ", d, off)
        phdrs.append(dict(type=p_type, flags=p_flags, offset=p_offset,
                          vaddr=p_vaddr, filesz=p_filesz, memsz=p_memsz,
                          align=p_align))
    shdrs = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        shdrs.append(struct.unpack_from("<IIQQQQIIQQ", d, off))
    return dict(data=d, type=e_type, machine=e_machine, entry=e_entry,
                phnum=e_phnum, shnum=e_shnum, shstrndx=e_shstrndx,
                phdrs=phdrs, shdrs=shdrs)


def section_names(img) -> list:
    """按 e_shstrndx 解出全部节名；下标越界或串未终止抛 ValueError。"""
    if img["shstrndx"] >= img["shnum"]:
        raise ValueError("e_shstrndx=%d 越界（节头表只有 %d 项）"
                         % (img["shstrndx"], img["shnum"]))
    sh = img["shdrs"][img["shstrndx"]]
    if sh[1] != 3:
        raise ValueError("e_shstrndx 指向的节不是 SHT_STRTAB（type=%d）" % sh[1])
    tab = img["data"][sh[4]:sh[4] + sh[5]]
    names = []
    for r in img["shdrs"]:
        no = r[0]
        if no >= len(tab):
            raise ValueError("节名偏移 %d 超出 .shstrtab（长度 %d）"
                             % (no, len(tab)))
        end = tab.find(b"\0", no)
        if end < 0:
            raise ValueError("节名未以 NUL 结尾（偏移 %d）" % no)
        names.append(tab[no:end].decode("latin1"))
    return names


def check_structure(path: str) -> int:
    """核对产物结构。返回 0 通过，非 0 失败。"""
    try:
        img = read_image_structure(path)
    except ValueError as e:
        print("  结构核对失败: %s" % e, file=sys.stderr)
        return 1
    if img["type"] != 2:
        print("  结构核对失败: e_type=%d 不是 ET_EXEC" % img["type"],
              file=sys.stderr)
        return 1
    if img["machine"] != 183:
        print("  结构核对失败: e_machine=%d 不是 AArch64" % img["machine"],
              file=sys.stderr)
        return 1
    if img["entry"] != 0x400000:
        print("  结构核对失败: e_entry=0x%x 不是 0x400000" % img["entry"],
              file=sys.stderr)
        return 1
    loads = [p for p in img["phdrs"] if p["type"] == 1]
    if len(loads) != 3:
        print("  结构核对失败: PT_LOAD 有 %d 个（期望 3）" % len(loads),
              file=sys.stderr)
        return 1
    for i, p in enumerate(loads):
        if p["filesz"] > p["memsz"]:
            print("  结构核对失败: %d 号段 filesz>memsz" % i, file=sys.stderr)
            return 1
        if p["offset"] % p["align"] != p["vaddr"] % p["align"]:
            print("  结构核对失败: %d 号段 p_offset 与 p_vaddr 不同余" % i,
                  file=sys.stderr)
            return 1
        if p["vaddr"] % p["align"] != 0:
            print("  结构核对失败: %d 号段虚拟地址未按页对齐" % i,
                  file=sys.stderr)
            return 1
    if loads[2]["flags"] & 1:
        print("  结构核对失败: RW 段带可执行权限", file=sys.stderr)
        return 1
    if loads[0]["flags"] & 1 == 0:
        print("  结构核对失败: 首段不可执行", file=sys.stderr)
        return 1
    try:
        names = section_names(img)
    except ValueError as e:
        print("  结构核对失败: %s" % e, file=sys.stderr)
        return 1
    for want in (".text", ".rodata", ".data", ".bss", ".strtab", ".symtab",
                 ".shstrtab"):
        if want not in names:
            print("  结构核对失败: 缺少节 %s（实得 %s）" % (want, names),
                  file=sys.stderr)
            return 1
    # .symtab 的 sh_link 必须指向 .strtab，sh_entsize 必须是 24
    for r in img["shdrs"]:
        if r[1] == 2:            # SHT_SYMTAB
            if r[9] != 24:
                print("  结构核对失败: .symtab 的 sh_entsize=%d（期望 24）" % r[9],
                      file=sys.stderr)
                return 1
            link = r[6]
            if link >= img["shnum"]:
                print("  结构核对失败: .symtab 的 sh_link=%d 越界" % link,
                      file=sys.stderr)
                return 1
            if img["shdrs"][link][1] != 3:
                print("  结构核对失败: .symtab 的 sh_link 指向的不是 SHT_STRTAB",
                      file=sys.stderr)
                return 1
            break
    else:
        print("  结构核对失败: 没有 SHT_SYMTAB 节", file=sys.stderr)
        return 1
    return 0


def run_case(link: str, asm: str, name: str, srcs, want: int, note: str) -> int:
    """汇编 → 链接 → 结构核对 → 真跑 + 确定性。返回 0 通过。"""
    print("  用例 %s：%s" % (name, note))
    objs = []
    for src in srcs:
        obj = os.path.join(BOX, name + "-" + os.path.basename(src) + ".o")
        r = run([asm, "asm", "-o", obj, os.path.join(ASM_FIX, src)])
        if r.returncode != 0:
            print("    汇编失败 %s：%s" % (src, (r.stdout + r.stderr).strip()),
                  file=sys.stderr)
            return 1
        objs.append(obj)
    out1 = os.path.join(BOX, name)
    out2 = os.path.join(BOX, name + ".again")
    for out in (out1, out2):
        r = run([link, "link", "-o", out] + objs)
        if r.returncode != 0:
            print("    链接失败：%s" % (r.stdout + r.stderr).strip(),
                  file=sys.stderr)
            return 1
    if open(out1, "rb").read() != open(out2, "rb").read():
        print("    确定性失败：两次链接的产物不同", file=sys.stderr)
        return 1
    if check_structure(out1) != 0:
        return 1
    r = run([out1])
    if r.returncode != want:
        print("    运行退出码 %d，期望 %d" % (r.returncode, want),
              file=sys.stderr)
        return 1
    print("    通过（退出码 %d，结构合法，产物确定）" % r.returncode)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="yh_link 端到端验收")
    ap.add_argument("--link", default=os.path.join(LINK_DIR, ".build", "yh_link"),
                    help="待验收的 yh_link 路径")
    ap.add_argument("--asm", default=os.path.join(ROOT, "asm", ".build", "yh_asm"),
                    help="用于产出对象的 yh_asm 路径")
    args = ap.parse_args()
    args.link = os.path.abspath(args.link)
    args.asm = os.path.abspath(args.asm)

    for path, what in ((args.link, "yh_link"), (args.asm, "yh_asm")):
        if not os.path.isfile(path):
            print("错误: 找不到 %s（%s）" % (what, path), file=sys.stderr)
            return 2
    if not os.path.isdir(ASM_FIX):
        print("错误: 找不到语料目录 %s" % ASM_FIX, file=sys.stderr)
        return 2
    os.makedirs(BOX, exist_ok=True)

    bad = 0
    for name, srcs, want, note in CASES:
        if run_case(args.link, args.asm, name, srcs, want, note) != 0:
            bad += 1
    if bad:
        print("端到端验收: %d/%d 个用例失败" % (bad, len(CASES)), file=sys.stderr)
        return 1
    print("端到端验收: %d 个用例全部通过" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
