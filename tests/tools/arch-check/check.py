#!/usr/bin/env python3
"""arch-check 自测：确认守护既能通过，也能真的抓到违规。

失败模式是"永远通过"（正则腐烂、路径写错），所以两条路径都要测：
  1. 真实仓库树 → 0；
  2. 注入超预算文件的副本 → 非 0，且报出 max_file_lines。
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


def main():
    failed = 0

    r = run()
    ok = r.returncode == 0 and "架构检查通过" in r.stdout
    print(("PASS" if ok else "FAIL") + " arch-check 真实树通过")
    if not ok:
        failed += 1
        print(r.stdout[-800:], r.stderr[-400:])

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shutil.copytree(ROOT / "compiler", root / "compiler",
                        ignore=shutil.ignore_patterns(".build", "tmp"))
        # 取当前最大的 .yh 作为注入目标：文件会随重构搬家，不能写死路径。
        victim = max(root.rglob("*.yh"), key=lambda p: len(p.read_text(errors="ignore")))
        victim.write_text(victim.read_text() + "\n" * 4000)
        r2 = run(root)
        caught = r2.returncode != 0 and "max_file_lines" in r2.stdout
        print(("PASS" if caught else "FAIL") + " arch-check 抓到超预算文件")
        if not caught:
            failed += 1
            print(r2.stdout[-800:], r2.stderr[-400:])

    print(f"arch-check 自测: 通过 {2 - failed}/2")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
