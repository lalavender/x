#!/usr/bin/env python3
"""YH_BUILD_CACHE 验收：构建缓存可整体迁到指定目录（多 worktree 各指一处）。

用例把 tests/modules/projects/inlineorder 复制到 tmp/build-cache 后构建三次：

    1. 设置 YH_BUILD_CACHE        → 对象等中间产物落在缓存根 targets/...，
                                     项目内不产生 .build/targets；
    2. 同一缓存再构建一次          → 增量缓存命中，仍成功且对象仍在；
    3. 不设置 YH_BUILD_CACHE      → 回到项目内 .build/targets（缺省行为不变）。

用法：
    python3 tests/build-cache/check.py [--compiler-path ./yh]

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
FIXTURE = ROOT / "tests" / "modules" / "projects" / "inlineorder"
WORK = ROOT / "tmp" / "build-cache"


def copy_fixture(dst: Path) -> None:
    """复制一个最小的宿主项目；不带缓存目录，避免旧产物干扰。"""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(FIXTURE, dst,
                    ignore=shutil.ignore_patterns(".build", "tmp"))


def run_build(compiler: Path, project: Path, cache: Path | None):
    """在项目里执行 yh build；cache 非空时经 YH_BUILD_CACHE 指定缓存根。"""
    env = dict(os.environ)
    env.pop("YH_BUILD_CACHE", None)
    env.setdefault("YH_STDLIB", str(ROOT / "libs"))
    if cache is not None:
        env["YH_BUILD_CACHE"] = str(cache)
    return subprocess.run([str(compiler), "build"], cwd=project,
                          capture_output=True, text=True, env=env, timeout=300)


def objects(cache: Path):
    """缓存里的模块对象（布局 targets/<triple>/llvm/O<n>/obj/*.o）。"""
    return sorted(cache.glob("targets/*/llvm/O*/obj/*.o"))


def main() -> int:
    """跑三个用例，逐个打印 PASS/FAIL，失败任一返回 1。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = ap.parse_args()
    compiler = Path(args.compiler_path).resolve()
    WORK.mkdir(parents=True, exist_ok=True)
    failed = 0

    def check(case: str, ok: bool, detail: str = "") -> None:
        nonlocal failed
        if ok:
            print(f"PASS {case}")
            return
        failed += 1
        print(f"FAIL {case}" + (f": {detail}" if detail else ""))

    # 1+2：缓存根在项目外；产物与对象都不应落进项目 .build/targets。
    project = WORK / "cached"
    cache = WORK / "cache"
    shutil.rmtree(cache, ignore_errors=True)
    copy_fixture(project)
    first = run_build(compiler, project, cache)
    built = objects(cache)
    check("cache-env-build", first.returncode == 0 and bool(built),
          f"退出码 {first.returncode}，缓存对象 {len(built)}，stderr={first.stderr[-400:]!r}")
    check("cache-env-keeps-project-clean",
          not (project / ".build" / "targets").exists(),
          f"项目内仍出现 .build/targets: {project / '.build'}")
    second = run_build(compiler, project, cache)
    check("cache-env-incremental",
          second.returncode == 0 and len(objects(cache)) == len(built),
          f"退出码 {second.returncode}，对象数 {len(objects(cache))}（首轮 {len(built)}），"
          f"stderr={second.stderr[-400:]!r}")

    # 3：不设置环境变量时缺省布局不变。
    default = WORK / "default"
    copy_fixture(default)
    plain = run_build(compiler, default, None)
    check("cache-default-layout",
          plain.returncode == 0
          and bool(list((default / ".build").glob("targets/*/llvm/O*/obj/*.o"))),
          f"退出码 {plain.returncode}，stderr={plain.stderr[-400:]!r}")

    if failed:
        print(f"总计：失败 {failed}")
        return 1
    print("总计：全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
