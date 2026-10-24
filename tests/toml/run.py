#!/usr/bin/env python3
"""libs/toml 自有验收 runner（TOML T0–T4 API 组）。

fixture 位于 tests/modules/projects/toml*/，每个用例复制到工作目录后构建并
运行；程序退出码 0 表示该组断言通过。runner 只依赖当前编译器与 libs/，
标准库根通过 YH_STDLIB 传给项目。

用法:
    python3 tests/toml/run.py
    python3 tests/toml/run.py --compiler ./yh --workdir tmp/toml-test
    python3 tests/toml/run.py --group model,strings --quiet --keep

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
    ("model", "tomlmodel", "toml model ok"),
    ("strings", "tomlstrings", "toml strings ok"),
    ("scalars", "tomlscalars", "toml scalars ok"),
    ("tables", "tomltables", "toml tables ok"),
    ("errors", "tomlerrors", "toml errors ok"),
    ("files", "tomlfiles", "toml files ok"),
]


def run(cmd, cwd, env, timeout=600):
    """运行子命令并返回 CompletedProcess。"""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=env)


def main() -> int:
    ap = argparse.ArgumentParser(description="yh TOML API 验收 runner")
    ap.add_argument("--compiler", default=str(ROOT / "yh"),
                    help="编译器路径（默认仓库根 ./yh）")
    ap.add_argument("--stdlib", default=str(ROOT / "libs"),
                    help="标准库根（默认仓库根 libs/）")
    ap.add_argument("--workdir", default=str(ROOT / "tmp" / "toml-test"),
                    help="用例工作目录（默认 tmp/toml-test）")
    ap.add_argument("--group", default="",
                    help="只跑指定组（逗号分隔，缺省全部）")
    ap.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    ap.add_argument("--keep", action="store_true", help="保留工作目录")
    ap.add_argument("--conformance", action="store_true",
                    help="API 组之后跑固定 toml-test 一致性门")
    ap.add_argument("--prepare-corpus", action="store_true",
                    help="下载并校验固定 toml-test 语料后退出")
    args = ap.parse_args()

    if args.prepare_corpus:
        return subprocess.run(
            [sys.executable, str(HERE / "conformance.py"), "--prepare"],
            cwd=ROOT).returncode
    compiler = Path(args.compiler).resolve()
    if not compiler.exists():
        print(f"编译器不存在: {compiler}")
        return 1
    stdlib = Path(args.stdlib).resolve()
    if not (stdlib / "toml").is_dir():
        print(f"标准库根缺少 toml 模块: {stdlib}")
        return 1
    work = Path(args.workdir).resolve()
    if work.exists():
        # 清理失败不应阻断验收：沙箱可能拦截大批量删除，copytree 允许覆盖。
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["YH_STDLIB"] = str(stdlib)

    wanted = {g.strip() for g in args.group.split(",") if g.strip()}
    selected = [c for c in CASES if not wanted or c[0] in wanted]
    unknown = wanted - {c[0] for c in CASES}
    if unknown:
        print(f"未知组: {','.join(sorted(unknown))}")
        return 1
    failed = 0
    for name, fixture, expected in selected:
        src = PROJECTS / fixture
        if not (src / "project.toml").exists():
            failed += 1
            print(f"FAIL {name}: fixture 缺失 {src}")
            continue
        dst = work / name
        shutil.copytree(src, dst, dirs_exist_ok=True)
        built = run([str(compiler), "build"], dst, env)
        binary = dst / ".build" / fixture
        if built.returncode != 0 or not binary.exists():
            failed += 1
            print(f"FAIL {name}: 构建失败 rc={built.returncode}")
            print((built.stderr or built.stdout)[-600:])
            continue
        shown = run([str(binary)], dst, env)
        ok = shown.returncode == 0 and expected in shown.stdout
        if ok:
            if not args.quiet:
                print(f"OK   {name}")
        else:
            failed += 1
            print(f"FAIL {name}: rc={shown.returncode}")
            print(f"stdout: {shown.stdout[-600:]!r}")
            print(f"stderr: {shown.stderr[-600:]!r}")

    api_failed = failed
    if args.conformance:
        conf_work = work.parent / (work.name + "-conformance")
        result = subprocess.run(
            [sys.executable, str(HERE / "conformance.py"),
             "--compiler", str(compiler), "--stdlib", str(stdlib),
             "--workdir", str(conf_work)],
            cwd=ROOT)
        if result.returncode != 0:
            failed += 1

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    total = len(selected)
    print(f"toml API: 通过 {total - api_failed}/{total}（编译器 {compiler}）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
