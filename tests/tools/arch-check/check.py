#!/usr/bin/env python3
"""arch-check 自测：确认守护既能通过，也能真的抓到违规。

失败模式是"永远通过"（正则腐烂、路径写错），所以五条路径都要测：
  1. 真实仓库树 → 0；
  2. 注入越界 import 的副本 → 非 0，且报出"越界依赖"；
  3. 子目录里的源码 → 仍被递归扫描并抓到越界；
  4. gen 的 `pub fn` 预算 +1 → 非 0；
  5. 追加大量空行的副本 → 仍 0（arch-check 不再检查代码行数）。
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools" / "arch-check.py"


def run(root=None):
    cmd = [sys.executable, str(TOOL)]
    if root:
        cmd += ["--root", str(root)]
    return subprocess.run(cmd, capture_output=True, text=True)


def copy_compiler(tmp, name):
    root = Path(tmp) / name
    shutil.copytree(ROOT / "compiler", root / "compiler",
                    ignore=shutil.ignore_patterns(".build", "tmp"))
    return root


def largest_source(root):
    return max(root.rglob("*.yh"), key=lambda p: len(p.read_text(errors="ignore")))


def main():
    failed = 0

    r = run()
    ok = r.returncode == 0 and "架构检查通过" in r.stdout
    print(("PASS" if ok else "FAIL") + " arch-check 真实树通过")
    if not ok:
        failed += 1
        print(r.stdout[-800:], r.stderr[-400:])

    with tempfile.TemporaryDirectory() as tmp:
        root = copy_compiler(tmp, "bad-import")
        victim = largest_source(root)
        victim.write_text("import injected_unknown_module\n" + victim.read_text(errors="ignore"),
                          encoding="utf-8")
        r2 = run(root)
        caught = r2.returncode != 0 and "越界依赖" in r2.stdout
        print(("PASS" if caught else "FAIL") + " arch-check 抓到越界依赖")
        if not caught:
            failed += 1
            print(r2.stdout[-800:], r2.stderr[-400:])

    with tempfile.TemporaryDirectory() as tmp:
        root = copy_compiler(tmp, "nested-import")
        nested = root / "compiler" / "extra" / "nested"
        nested.mkdir(parents=True)
        (nested / "probe.yh").write_text(
            "module extra\nimport injected_unknown_module\n", encoding="utf-8")
        r3 = run(root)
        caught = r3.returncode != 0 and "未登记模块 extra" in r3.stdout
        print(("PASS" if caught else "FAIL") + " arch-check 递归抓子目录越界")
        if not caught:
            failed += 1
            print(r3.stdout[-800:], r3.stderr[-400:])

    with tempfile.TemporaryDirectory() as tmp:
        root = copy_compiler(tmp, "gen-budget")
        # 预算按当前实测值只减不增：注入到「实际 + 1 > 预算」才该红灯，
        # 所以先读预算与实际，再补足差额，避免测试随基线下降而失效。
        gen_files = list((root / "compiler" / "gen").glob("*.yh"))
        actual = sum(len(re.findall(r"(?m)^pub fn ", p.read_text(errors="ignore")))
                     for p in gen_files)
        budget = int(re.search(r'"max_gen_pub_fns":\s*(\d+)',
                               TOOL.read_text(encoding="utf-8")).group(1))
        need = max(1, budget - actual + 1)
        victim = root / "compiler" / "gen" / "state.yh"
        victim.write_text(
            victim.read_text(errors="ignore") +
            "\n" + "".join(
                f"pub fn injected_budget_probe_{i}() int {{ return 0 }}\n"
                for i in range(need)),
            encoding="utf-8")
        r4 = run(root)
        caught = r4.returncode != 0 and "max_gen_pub_fns" in r4.stdout
        print(("PASS" if caught else "FAIL") + " arch-check 抓 gen pub fn 预算")
        if not caught:
            failed += 1
            print(r4.stdout[-800:], r4.stderr[-400:])

    with tempfile.TemporaryDirectory() as tmp:
        root = copy_compiler(tmp, "long-file")
        victim = largest_source(root)
        victim.write_text(victim.read_text(errors="ignore") + "\n" * 4000,
                          encoding="utf-8")
        r5 = run(root)
        ok = r5.returncode == 0 and "架构检查通过" in r5.stdout
        print(("PASS" if ok else "FAIL") + " arch-check 不按代码行数阻断")
        if not ok:
            failed += 1
            print(r3.stdout[-800:], r3.stderr[-400:])

    print(f"arch-check 自测: 通过 {5 - failed}/5")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
