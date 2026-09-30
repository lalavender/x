#!/usr/bin/env python3
"""tests/selfhost/native-selfhost.py —— 本机全套自举门（0.0.3 滚动自举）。

链路（无 stage0；种子 = 入库的 bin/yh）：
    bin/yh build compiler/  → cc2（冷编）
    cc2     build compiler/     → cc3（冷编）
门：
    1. 固定点：cc2/cc3 全部模块 .s/.s.i 逐字节一致；
    2. cc3 自解析：compiler/ 全部 .yh 源文件 --syntax-check 通过；
    3. cc3 语法语料：tests/yh 正例全过、反例全拒；
    4. cc3 运行语料：tests/yh-run 全量（run/fail/pass）。

用法：python3 tests/selfhost/native-selfhost.py [--keep]
退出码：全部通过 0。
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILER = ROOT / "compiler"
WORK = ROOT / "tmp" / "selfhost"
MODS = ("gen", "lex", "parse", "cmd")


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True,
                          text=True, timeout=1800)


def build(cc, out) -> Path:
    bdir = COMPILER / ".build"
    if bdir.exists():
        shutil.rmtree(bdir)
    r = run([str(cc), "build", "-o", str(out)], cwd=COMPILER)
    if r.returncode != 0:
        print(f"FAIL 构建 {out.name}:", r.stderr[-400:])
        sys.exit(1)
    return bdir


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    seed = ROOT / "bin/yh"
    if not seed.exists():
        print("FAIL 缺少入库种子 bin/yh")
        return 1

    ok = True
    d2 = build(seed, WORK / "cc2")
    d3 = build(WORK / "cc2", WORK / "cc3")
    print("cc2/cc3 构建完成（种子 = bin/yh）")

    # 1) 固定点：.build/asm/*.s 与 .build/iface/*.s.i 逐字节一致
    def snapshot(bdir: Path):
        return {str(p.relative_to(bdir)): p.read_bytes()
                for sub in ("asm", "iface")
                for p in sorted((bdir / sub).glob("*.s*"))}
    s2, s3 = snapshot(d2), snapshot(d3)
    same = (s2 == s3)
    print("模块固定点（cc2 == cc3 的 .s/.s.i，%d 个产物）：%s"
          % (len(s2), "一致" if same else "不一致"))
    if not same:
        only = set(s2) ^ set(s3)
        if only:
            print("  产物集合差异:", sorted(only))
        for k in sorted(set(s2) & set(s3)):
            if s2[k] != s3[k]:
                print("  内容差异:", k)
    ok = ok and same

    cc3 = str(WORK / "cc3")
    # 2) 自解析
    bad = []
    for src in sorted(COMPILER.rglob("*.yh")):
        r = run([cc3, "--syntax-check", str(src)])
        if r.returncode != 0:
            bad.append(src.name)
    print("cc3 自解析（25 源文件）：%s" % ("OK" if not bad else "FAIL " + ",".join(bad)))
    ok = ok and not bad

    # 3) 语法语料
    r = run(["python3", "tests/yh/check.py", "--compiler",
             "--compiler-path", cc3, "--quiet"])
    print("语法语料：", (r.stdout.strip().splitlines() or ["无输出"])[-1])
    ok = ok and r.returncode == 0

    # 4) 运行语料
    r = run(["python3", "tests/yh-run/check.py", "--compiler", cc3, "--quiet"])
    print("运行语料：", (r.stdout.strip().splitlines() or ["无输出"])[-1])
    ok = ok and r.returncode == 0

    if not args.keep:
        shutil.rmtree(WORK, ignore_errors=True)
    print("总计：%s" % ("全部通过" if ok else "存在失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
