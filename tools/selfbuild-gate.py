#!/usr/bin/env python3
"""tools/selfbuild-gate.py —— ADR-0007 P5 验收：四代自举链与模块固定点。

链路：
    stage0(yh, C) → seed 编译器（bootstrap/seed 扁平化快照，stage1）
                 → yh build 活跃项目（compiler/，-o cc2）
                 → cc2 build -o cc3
                 → cc3 build -o cc4
门：
    1. 各代构建成功；
    2. cc2/cc3/cc4 两两之间全部模块 .s 与 .s.i 逐字节一致（固定点）；
    3. cc4 冒烟（编译 hello 返回正确退出码）与 modules 语法语料通过。

用法：python3 tools/selfbuild-gate.py
退出码：全部通过 0。
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "tmp" / "selfbuild-gate"
COMPILER = ROOT / "compiler"


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True,
                          text=True, timeout=1800)


def main() -> int:
    ok = True
    WORK.mkdir(parents=True, exist_ok=True)
    seed_cc = WORK / "seed-compiler"
    r = run(["./yh", "bootstrap/seed/compiler.yh", "-o", str(seed_cc),
             "-B", str(ROOT)])
    if r.returncode != 0:
        print("FAIL seed 编译器构建:", r.stderr[-300:])
        return 1
    print("stage1（seed 编译器）构建完成")

    prev = seed_cc
    gens = []
    for name in ("cc2", "cc3", "cc4"):
        bdir = COMPILER / "tmp/yh-build"
        if bdir.exists():
            shutil.rmtree(bdir)
        out = WORK / name
        r = run([str(prev), "build", "-o", str(out)], cwd=COMPILER)
        if r.returncode != 0:
            print(f"FAIL {name} 构建:", r.stderr[-400:])
            return 1
        gens.append((name, bdir, out))
        prev = out
        print(f"{name} 构建完成")

    # 固定点：相邻两代全部模块产物逐字节一致
    for (n1, d1, _), (n2, d2, _) in zip(gens, gens[1:]):
        for mod in ("gen", "lex", "parse", "cmd"):
            for ext in (".s", ".s.i"):
                a, b = d1 / (mod + ext), d2 / (mod + ext)
                if a.read_bytes() != b.read_bytes():
                    print(f"FAIL 固定点 {n1}→{n2} {mod}{ext} 不一致")
                    ok = False
        if ok:
            print(f"固定点 {n1}→{n2}：gen/lex/parse/cmd 全部 .s/.s.i 逐字节一致")

    # stage4 冒烟 + 语料
    hello = WORK / "hello.yh"
    hello.write_text("fn main() int {\n    return 42;\n}\n")
    binp = WORK / "hello.bin"
    r = run([str(WORK / "cc4"), str(hello), "-o", str(binp)])
    if r.returncode != 0:
        print("FAIL cc4 编译 hello:", r.stderr[-300:])
        ok = False
    else:
        r2 = subprocess.run([str(binp)], capture_output=True)
        if r2.returncode != 42:
            print(f"FAIL cc4 hello 退出码 {r2.returncode} 期望 42")
            ok = False
        else:
            print("cc4 冒烟：hello 退出码 42 ✓")

    r = run(["python3", "tests/modules/check.py",
             "--compiler-path", str(WORK / "cc4")])
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "modules runner 无输出")
    if r.returncode != 0:
        ok = False

    print("总计：%s" % ("全部通过" if ok else "存在失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
