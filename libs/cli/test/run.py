#!/usr/bin/env python3
"""libs/cli 自有验收 runner。

cli 标准库的用例与全局 tests/ 解耦：fixture 与 runner 都放在 libs/cli/test/，
只依赖当前编译器与 libs 目录，不经过 tests/modules 的用例登记。

每个用例把 fixture 复制到工作目录后构建，再用给定 argv 运行产物，比较
退出码与 stdout/stderr 子串。默认编译器是仓库根 ./yh，标准库根是 libs/。

用法:
    python3 libs/cli/test/run.py
    python3 libs/cli/test/run.py --compiler ./yh --workdir tmp/cli-test
    python3 libs/cli/test/run.py --quiet --keep

退出码：全部通过 0；有失败 1。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent  # libs/cli/test -> 仓库根

# (用例名, fixture 目录, argv, 期望退出码, stdout 子串, stderr 子串)
CASES = [
    ("cli0-model-abi", "climodel", [], 0, "yh cli model ok", None),
    ("cli1-basics-selftest", "clibasics", ["--selftest"], 0, None, None),
    ("cli1-pack-run", "clibasics", ["in.txt", "-v", "-o", "out.bin"], 0,
     "output=out.bin source=in.txt verbose=1", None),
    ("cli1-pack-help", "clibasics", ["--help"], 0, "usage: pack", None),
    ("cli1-pack-missing", "clibasics", [], 2, None, "缺少必需的位置参数"),
    ("cli2-actions", "cliactions", ["--selftest"], 0, None, None),
    ("cli3-commands", "clicommands", ["--selftest"], 0, None, None),
    ("cli4-extensions", "cliextensions", ["--selftest"], 0, None, None),
    ("cli5-help", "clihelp", ["--selftest"], 0, None, None),
    ("cli6-warning-entry", "cliwarnings", ["--old", "x", "in.txt"], 0,
     "warnings=0 src=in.txt", "弃用"),
]


def run(cmd, cwd, env, timeout=300):
    """运行子命令并返回 CompletedProcess。"""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=env)


def binary_of(fixture: Path) -> Path:
    """返回项目产物路径：.build/<project.name>。"""
    text = (fixture / "project.toml").read_text()
    name = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("name") and "=" in line:
            name = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
    if not name:
        name = fixture.name
    return fixture / ".build" / name


def main() -> int:
    ap = argparse.ArgumentParser(description="libs/cli 自有验收 runner")
    ap.add_argument("--compiler", default=str(ROOT / "yh"),
                    help="编译器路径（默认仓库根 ./yh）")
    ap.add_argument("--stdlib", default=str(ROOT / "libs"),
                    help="标准库根（默认仓库根 libs/）")
    ap.add_argument("--workdir", default=str(ROOT / "tmp" / "cli-test"),
                    help="用例工作目录（默认 tmp/cli-test）")
    ap.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    ap.add_argument("--keep", action="store_true", help="保留工作目录")
    args = ap.parse_args()

    compiler = Path(args.compiler).resolve()
    if not compiler.exists():
        print(f"编译器不存在: {compiler}")
        return 1
    stdlib = Path(args.stdlib).resolve()
    if not (stdlib / "cli").is_dir():
        print(f"标准库根缺少 cli 模块: {stdlib}")
        return 1

    work = Path(args.workdir).resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["YH_STDLIB"] = str(stdlib)

    failed = 0
    for name, fixture, argv, expect, out_contains, err_contains in CASES:
        dst = work / name
        shutil.copytree(HERE / fixture, dst)
        built = run([str(compiler), "build"], dst, env)
        binary = binary_of(dst)
        if built.returncode != 0 or not binary.exists():
            failed += 1
            print(f"FAIL {name}: 构建失败 rc={built.returncode}")
            print((built.stderr or built.stdout)[-500:])
            continue
        shown = run([str(binary), *argv], dst, env)
        ok = shown.returncode == expect
        if ok and out_contains is not None:
            ok = out_contains in shown.stdout
        if ok and err_contains is not None:
            ok = err_contains in shown.stderr
        if ok:
            if not args.quiet:
                print(f"OK   {name}")
        else:
            failed += 1
            print(f"FAIL {name}: rc={shown.returncode} 期望 {expect}; "
                  f"stdout={shown.stdout[-160:]!r}; stderr={shown.stderr[-160:]!r}")

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    total = len(CASES)
    print(f"cli: 通过 {total - failed}/{total}（编译器 {compiler}）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
