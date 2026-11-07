#!/usr/bin/env python3
"""arch-check 自测：确认守护既能通过，也能真的抓到违规。

失败模式是"永远通过"（正则腐烂、路径写错），所以六条路径都要测：
  1. 真实仓库树 → 0；
  2. 注入越界 import 的副本 → 非 0，且报出"越界依赖"；
  3. 子目录里的源码 → 仍被递归扫描并抓到越界；
  4. gen 的 `pub fn` 预算越界 → 非 0；
  5. comptime 新增 gen 依赖 → 非 0；
  6. 追加大量空行的副本 → 仍 0（arch-check 不再检查代码行数）。
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


TOTAL = 8  # 自测用例数；新增用例必须同步这里


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
        # gen 已随 F4 收尾删除：把 gen 目录塞回去（含超过预算的 pub fn）必须红灯。
        root = copy_compiler(tmp, "gen-removed")
        gen_dir = root / "compiler" / "gen"
        gen_dir.mkdir(parents=True, exist_ok=True)
        (gen_dir / "value_rules.yh").write_text(
            "module gen\nimport support\n\n" +
            "".join(f"pub fn injected_budget_probe_{i}() int {{ return 0 }}\n"
                    for i in range(3)),
            encoding="utf-8")
        r4 = run(root)
        caught = r4.returncode != 0 and "gen" in r4.stdout
        print(("PASS" if caught else "FAIL") + " arch-check 抓已删除的 gen 模块回归")
        if not caught:
            failed += 1
            print(r4.stdout[-800:], r4.stderr[-400:])

    with tempfile.TemporaryDirectory() as tmp:
        root = copy_compiler(tmp, "ast-view-count")
        victim = root / "compiler" / "check" / "checked_slice.yh"
        victim.write_text(
            victim.read_text(errors="ignore") +
            "\nfn injected_view_count_probe() void { let v int = 0 }\n",
            encoding="utf-8")
        # 直接注入一行视图计数累加（模拟 2026-11-07 回归写法）。
        victim.write_text(
            victim.read_text(encoding="utf-8") +
            "\nfn injected_view_probe(v int) void { v.stmt_count += 1 }\n",
            encoding="utf-8")
        r8 = run(root)
        caught = r8.returncode != 0 and "max_ast_view_count_writes" in r8.stdout
        print(("PASS" if caught else "FAIL") + " arch-check 抓 AST 视图计数就地累加")
        if not caught:
            failed += 1
            print(r8.stdout[-600:], r8.stderr[-300:])

    with tempfile.TemporaryDirectory() as tmp:
        root = copy_compiler(tmp, "ct-row-write")
        victim = root / "compiler" / "comptime" / "ct_layout.yh"
        victim.write_text(
            victim.read_text(errors="ignore") +
            "\nfn injected_row_write_probe() void { ct_type_row(0).size = -1 }\n",
            encoding="utf-8")
        r7 = run(root)
        caught = r7.returncode != 0 and "max_ct_row_field_writes" in r7.stdout
        print(("PASS" if caught else "FAIL") + " arch-check 抓镜像行按值写回")
        if not caught:
            failed += 1
            print(r7.stdout[-800:], r7.stderr[-400:])

    with tempfile.TemporaryDirectory() as tmp:
        # gen 已删除后，最重要的硬约束是「comptime 不得依赖 check」（会成环）。
        root = copy_compiler(tmp, "comptime-check")
        victim = root / "compiler" / "comptime" / "ct_facts.yh"
        victim.write_text(
            victim.read_text(errors="ignore") +
            "\nimport check\nfn injected_dependency_probe() int { return check.ct_types_bound() }\n",
            encoding="utf-8")
        r6 = run(root)
        caught = r6.returncode != 0 and "comptime" in r6.stdout and "check" in r6.stdout
        print(("PASS" if caught else "FAIL") + " arch-check 抓 comptime→check 越界")
        if not caught:
            failed += 1
            print(r6.stdout[-800:], r6.stderr[-400:])

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

    print(f"arch-check 自测: 通过 {TOTAL - failed}/{TOTAL}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
