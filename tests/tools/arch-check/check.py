#!/usr/bin/env python3
"""arch-check 自测：确认守护既能通过，也能真的抓到违规。

失败模式是"永远通过"（正则腐烂、路径写错），所以三条路径都要测：
  1. 真实仓库树 → 0；
  2. 注入越界 import 的副本 → 非 0，且报出"越界依赖"；
  3. 追加大量空行的副本 → 仍 0（arch-check 不再检查代码行数）。
"""

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
        root = copy_compiler(tmp, "long-file")
        victim = largest_source(root)
        victim.write_text(victim.read_text(errors="ignore") + "\n" * 4000,
                          encoding="utf-8")
        r3 = run(root)
        ok = r3.returncode == 0 and "架构检查通过" in r3.stdout
        print(("PASS" if ok else "FAIL") + " arch-check 不按代码行数阻断")
        if not ok:
            failed += 1
            print(r3.stdout[-800:], r3.stderr[-400:])

    print(f"arch-check 自测: 通过 {3 - failed}/3")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
