#!/usr/bin/env python3
"""yh 汇编语料重建与盘点（分期实施方案 TC0 落地）。

把编译器**实际发射**的汇编收集成可重复的语料，并统计助记符、伪指令与符号
修饰符形态，与首版汇编子集契约（docs/03-design/yh-link独立项目与首版汇编子集
契约.md 的 §3/§4）对照，给出「契约外出现」与「契约内未出现」两张清单。

产出的目录就是汇编器差分门的输入：
    python3 asm/tests/check_corpus.py tmp/inv --bin asm/.build/yh_asm
    python3 asm/tests/elf_link_native.py tmp/inv --bin asm/.build/yh_asm

用法：
    python3 tools/yh-toolchain-inventory.py --compiler ./yh --output tmp/inv
    python3 tools/yh-toolchain-inventory.py --compiler ./yh --no-build   # 只盘点
    python3 tools/yh-toolchain-inventory.py --compiler ./yh --dirs tests/yh-run/run

默认语料来源：
  * 单文件：`yh --emit-asm` 逐文件发射（默认 tests/yh-run/run、tests/yh-run/pass，
    都是可运行程序；语法语料用 --dirs 追加）；
  * 模块：`yh build` 后收 `.build/asm/*.s`（默认只收编译器自身项目 compiler/，
    用 --projects 追加 tests/modules/projects 下的 fixture）。

可重复性：同一编译器与同一批源码两次运行产出逐字节相同的语料与 inventory.md
（文件内容不含时间戳；编译器身份用 sha256 记录）。
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 契约 §3 的助记符白名单（v1）。`b.<cond>` 按前缀匹配，别名（beq/bne…）另列。
CONTRACT_MNEMONICS = set("""
add adds sub subs cmp tst neg mov movz movk mvn
and ands orr eor bic mul msub sdiv udiv
lsl lslv lsrv asrv
sxtb sxth sxtw uxtb uxth sbfx
ldr ldrb ldrh ldrsb ldrsw ldrsh str strb strh stp ldp
b bl br blr ret cbz cbnz beq bne blt ble bgt bge bcc bcs
csel cset
adrp nop brk svc hlt dsb dmb isb
fadd fsub fmul fdiv fcmp fcvt fcvtzs scvtf ucvtf fmov
""".split())

# 契约 §4 的伪指令白名单（v1）。
CONTRACT_DIRECTIVES = set("""
.text .data .bss .section
.globl .global .local
.balign .p2align
.byte .hword .word .xword .quad .zero .skip
.type .size
""".split())

# 符号修饰符形态：编译器两个方言各用一套，盘点里都要能看到。
MODIFIER_RE = re.compile(r"(:lo12:|:got_lo12:|:got:|@PAGE\b|@PAGEOFF\b|@GOTPAGE\b|@GOTPAGEOFF\b)")
INSN_RE = re.compile(r"^\t([a-z][a-z0-9.]*)")
DIR_RE = re.compile(r"^\t(\.[a-z0-9_]+)")


def run(cmd, cwd=None, env=None):
    """跑一条命令，返回 CompletedProcess（文本模式）。"""
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=env)


def sha256(path):
    """文件 sha256（编译器身份）。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def rel_name(path, suffix):
    """语料文件名：仓库相对路径把分隔符换成 __，保证不同目录不重名。"""
    rel = os.path.relpath(path, REPO).replace(os.sep, "__")
    if suffix and rel.endswith(suffix):
        rel = rel[:-len(suffix)]
    return rel


def collect_single(compiler, dirs, out_dir, skipped):
    """单文件语料：逐文件 `yh --emit-asm`，失败记 skipped 而不是静默丢。"""
    n = 0
    for d in dirs:
        full = d if os.path.isabs(d) else os.path.join(REPO, d)
        if not os.path.isdir(full):
            skipped.append((d, "目录不存在"))
            continue
        for root, _, files in os.walk(full):
            for f in sorted(files):
                if not f.endswith(".yh"):
                    continue
                path = os.path.join(root, f)
                r = run([compiler, "--emit-asm", path])
                if r.returncode != 0:
                    why = (r.stderr or r.stdout).strip().split("\n")[0]
                    skipped.append((rel_name(path, ".yh"), "emit-asm 失败: " + why))
                    continue
                with open(os.path.join(out_dir, rel_name(path, ".yh") + ".s"), "w") as fh:
                    fh.write(r.stdout)
                n += 1
    return n


def collect_modules(compiler, projects, out_dir, env, skipped):
    """模块语料：`yh build` 后收 `.build/asm/*.s`（模块模式与单文件模式不同）。"""
    n = 0
    for proj in projects:
        full = proj if os.path.isabs(proj) else os.path.join(REPO, proj)
        if not os.path.isfile(os.path.join(full, "project.toml")):
            skipped.append((proj, "不是项目（缺 project.toml）"))
            continue
        r = run([compiler, "build"], cwd=full, env=env)
        if r.returncode != 0:
            why = (r.stderr or r.stdout).strip().split("\n")[0]
            skipped.append((proj, "yh build 失败: " + why))
            continue
        asm_dir = os.path.join(full, ".build", "asm")
        if not os.path.isdir(asm_dir):
            skipped.append((proj, "没有 .build/asm 产物"))
            continue
        tag = os.path.basename(full.rstrip(os.sep))
        for f in sorted(os.listdir(asm_dir)):
            if not f.endswith(".s"):
                continue
            dst = "mod-%s-%s" % (tag, f)
            shutil.copyfile(os.path.join(asm_dir, f), os.path.join(out_dir, dst))
            n += 1
    return n


def scan_corpus(files):
    """统计助记符、伪指令与符号修饰符形态。"""
    mnemonics = Counter()
    directives = Counter()
    modifiers = Counter()
    for path in files:
        with open(path, errors="replace") as fh:
            for line in fh:
                m = INSN_RE.match(line)
                if m:
                    mnemonics[m.group(1)] += 1
                d = DIR_RE.match(line)
                if d:
                    directives[d.group(1)] += 1
                for mod in MODIFIER_RE.findall(line):
                    modifiers[mod] += 1
    return mnemonics, directives, modifiers


def contract_flags(name, table):
    """契约归属：完全在表里 / b.<cond> 前缀形态 / 表外。"""
    if name in table:
        return "契约内"
    if table is CONTRACT_MNEMONICS and name.startswith("b.") and len(name) > 2:
        return "契约内（b.<cond>）"
    return "契约外"


def table_lines(counter, table):
    """按「次数降序 + 名字升序」输出 Markdown 表，保证可重复。"""
    out = ["| 名称 | 次数 | 契约 |", "| --- | --- | --- |"]
    for name in sorted(counter, key=lambda k: (-counter[k], k)):
        out.append("| `%s` | %d | %s |" % (name, counter[name],
                                           contract_flags(name, table)))
    return out


def main():
    ap = argparse.ArgumentParser(description="重建并盘点 yh 汇编语料")
    ap.add_argument("--compiler", default=os.path.join(REPO, "yh"),
                    help="编译器路径（默认仓库根 yh）")
    ap.add_argument("--output", default=os.path.join(REPO, "tmp", "inv"),
                    help="语料输出目录（默认 tmp/inv）")
    ap.add_argument("--dirs", nargs="*",
                    default=["tests/yh-run/run", "tests/yh-run/pass"],
                    help="单文件语料源码目录（相对仓库根）")
    ap.add_argument("--projects", nargs="*", default=["compiler"],
                    help="要收模块汇编的项目目录（默认 compiler）")
    ap.add_argument("--no-build", action="store_true",
                    help="只盘点现有语料，不调用编译器")
    args = ap.parse_args()

    compiler = os.path.abspath(args.compiler)
    if not os.path.isfile(compiler):
        print("找不到编译器：%s" % compiler, file=sys.stderr)
        return 2
    out_dir = os.path.abspath(args.output)
    os.makedirs(out_dir, exist_ok=True)

    skipped = []
    single = modules = 0
    env = dict(os.environ)

    if args.no_build:
        files = sorted(os.path.join(out_dir, f) for f in os.listdir(out_dir)
                       if f.endswith(".s"))
        print("只盘点：%d 个已有语料" % len(files))
    else:
        if not shutil.which("gcc") and not shutil.which("clang"):
            print("警告：PATH 上没有 gcc/clang，模块语料的链接步可能失败",
                  file=sys.stderr)
        for f in os.listdir(out_dir):
            os.unlink(os.path.join(out_dir, f))
        single = collect_single(compiler, args.dirs, out_dir, skipped)
        modules = collect_modules(compiler, args.projects, out_dir, env, skipped)
        files = sorted(os.path.join(out_dir, f) for f in os.listdir(out_dir)
                       if f.endswith(".s"))
        print("单文件语料 %d 个，模块语料 %d 个，跳过 %d 个"
              % (single, modules, len(skipped)))

    if not files:
        print("语料为空，无法盘点", file=sys.stderr)
        return 1

    with open(os.path.join(out_dir, "skipped.txt"), "w") as fh:
        for name, why in skipped:
            fh.write("%s\t%s\n" % (name, why))

    mnemonics, directives, modifiers = scan_corpus(files)
    total_bytes = sum(os.path.getsize(p) for p in files)
    outside = sorted(k for k in mnemonics if contract_flags(k, CONTRACT_MNEMONICS) == "契约外")
    unused = sorted(k for k in CONTRACT_MNEMONICS if mnemonics.get(k, 0) == 0
                    and not k.startswith("b."))

    md = []
    md.append("# yh 汇编语料盘点\n")
    md.append("编译器：`%s`\n" % os.path.relpath(compiler, REPO))
    md.append("编译器 sha256：`%s`（%d 字节）\n" % (sha256(compiler),
                                                os.path.getsize(compiler)))
    md.append("语料：%d 个文件、%d 字节（%s）\n"
              % (len(files), total_bytes, os.path.relpath(out_dir, REPO)))
    md.append("跳过：%d 个（见 skipped.txt）\n" % len(skipped))
    md.append("\n## 助记符\n")
    md.extend(table_lines(mnemonics, CONTRACT_MNEMONICS))
    md.append("\n## 伪指令\n")
    md.extend(table_lines(directives, CONTRACT_DIRECTIVES))
    md.append("\n## 符号修饰符形态\n")
    md.append("| 形态 | 次数 |")
    md.append("| --- | --- |")
    for name in sorted(modifiers, key=lambda k: (-modifiers[k], k)):
        md.append("| `%s` | %d |" % (name, modifiers[name]))
    md.append("\n## 结论\n")
    md.append("- 契约外出现：%s" % (", ".join("`%s`" % k for k in outside) if outside else "无"))
    md.append("- 契约内未出现：%s" % (", ".join("`%s`" % k for k in unused) if unused else "无"))
    md.append("- 跳过语料：%s" % (", ".join(n for n, _ in skipped) if skipped else "无"))
    md.append("")
    with open(os.path.join(out_dir, "inventory.md"), "w") as fh:
        fh.write("\n".join(md))

    print("助记符 %d 种，伪指令 %d 种，契约外出现 %d 种"
          % (len(mnemonics), len(directives), len(outside)))
    for k in outside:
        print("  契约外: %s（%d 次）" % (k, mnemonics[k]))
    print("inventory: %s" % os.path.join(out_dir, "inventory.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
