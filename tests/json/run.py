#!/usr/bin/env python3
"""libs/json 自有验收 runner（J3–J6 API 组）。

fixture 位于 tests/modules/projects/json*/，每个用例复制到工作目录后构建并
运行；程序退出码 0 表示该组断言通过。runner 只依赖当前编译器与 libs/，
标准库根通过 YH_STDLIB 传给项目。

用法:
    python3 tests/json/run.py
    python3 tests/json/run.py --compiler ./yh --workdir tmp/json-test
    python3 tests/json/run.py --group model,strings --quiet --keep

退出码：全部通过 0；有失败 1。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PROJECTS = ROOT / "tests" / "modules" / "projects"

# (组名, fixture 目录, 期望 stdout 子串)
CASES = [
    ("model", "jsonmodel", "json model ok"),
    ("strings", "jsonstrings", "json strings ok"),
    ("numbers", "jsonnumbers", "json numbers ok"),
    ("containers", "jsoncontainers", "json containers ok"),
    ("errors", "jsonerrors", "json errors ok"),
    ("files", "jsonfiles", "json files ok"),
]


def run(cmd, cwd, env, timeout=600):
    """运行子命令并返回 CompletedProcess。"""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=env)


def main() -> int:
    ap = argparse.ArgumentParser(description="yh JSON API 验收 runner")
    ap.add_argument("--compiler", default=str(ROOT / "yh"),
                    help="编译器路径（默认仓库根 ./yh）")
    ap.add_argument("--stdlib", default=str(ROOT / "libs"),
                    help="标准库根（默认仓库根 libs/）")
    ap.add_argument("--workdir", default=str(ROOT / "tmp" / "json-test"),
                    help="用例工作目录（默认 tmp/json-test）")
    ap.add_argument("--group", default="",
                    help="只跑指定组（逗号分隔，缺省全部）")
    ap.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    ap.add_argument("--keep", action="store_true", help="保留工作目录")
    args = ap.parse_args()

    compiler = Path(args.compiler).resolve()
    if not compiler.exists():
        print(f"编译器不存在: {compiler}")
        return 1
    stdlib = Path(args.stdlib).resolve()
    if not (stdlib / "json").is_dir():
        print(f"标准库根缺少 json 模块: {stdlib}")
        return 1
    selected = [name for name in args.group.split(",") if name]
    cases = [c for c in CASES if not selected or c[0] in selected]
    if not cases:
        print(f"没有匹配的组: {args.group}")
        return 1

    work = Path(args.workdir).resolve()
    # 清理失败不应阻断验收：沙箱可能拦截大批量删除，下面的 copytree 允许覆盖。
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["YH_STDLIB"] = str(stdlib)

    failures = []
    for name, fixture, expect in cases:
        source = PROJECTS / fixture
        target = work / name
        shutil.copytree(source, target,
                        ignore=shutil.ignore_patterns(".build"),
                        dirs_exist_ok=True)
        build = run([str(compiler), "build"], target, env)
        if build.returncode != 0:
            failures.append((name, "build", build.stdout + build.stderr))
            if not args.quiet:
                print(f"[FAIL] {name}: 构建失败")
            continue
        program = target / ".build" / fixture
        if not program.exists():
            failures.append((name, "build", "缺少产物 " + str(program)))
            continue
        result = run([str(program)], target, env, timeout=120)
        output = result.stdout + result.stderr
        if result.returncode != 0 or expect not in output:
            failures.append((name, "run", output))
            if not args.quiet:
                print(f"[FAIL] {name}: 断言未通过")
                for line in output.strip().splitlines()[-12:]:
                    print("  " + line)
            continue
        if not args.quiet:
            print(f"[ok] {name}")

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)

    total = len(cases)
    print(f"json API: {total - len(failures)}/{total} 通过")
    if failures:
        for name, stage, detail in failures:
            print(f"--- {name} ({stage}) ---")
            print(detail.strip()[-2000:])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
