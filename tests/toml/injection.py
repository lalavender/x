#!/usr/bin/env python3
"""TOML T4.1 分配失败注入与预算强制失败门。

产品 `libs/toml` 只保留默认关闭的私有注入常量；本 runner 复制标准库到
临时目录并做两份测试构建：

1. 注入运行时设置函数，替换 pool_alloc 的注入条件；`tomlinject` 从 0 开始
   逐次允许更多池分配，直到文档成功。每个失败点都必须返回
   parse_resource_error + error_out_of_memory、没有 document.handle，
   且同一进程内重复解析仍干净失败。
2. 把 TOML_MAX_BYTES 调低到 2048；`tomlbudget` 解析一个正常文档，必须在
   预算内失败并返回 parse_resource_error + error_resource_limit。

用法:
    python3 tests/toml/injection.py
    python3 tests/toml/injection.py --compiler ./yh --workdir tmp/toml-inject

退出码：通过 0；失败 1。
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
INJECTION_GLOBAL = "toml_test_fail_after"
BUDGET_BYTES = 2048


def copy_stdlib(source: Path, target: Path) -> None:
    """复制标准库，跳过测试目录与构建产物。"""
    ignore = shutil.ignore_patterns("test", ".build", "__pycache__", "*.pyc")
    shutil.copytree(source, target, ignore=ignore)


def inject_test_seam(libs: Path) -> None:
    """在临时标准库副本中加入运行时失败注入接缝。"""
    inject = libs / "toml" / "05_inject.yh"
    inject.write_text(
        "module toml\n\n"
        "// 测试构建专用：运行时设置池分配失败点；产品构建没有本文件。\n"
        f"let {INJECTION_GLOBAL} int = -1\n\n"
        "pub fn test_set_fail_after(count int) void {\n"
        f"    {INJECTION_GLOBAL} = count\n"
        "}\n",
        encoding="utf-8",
    )
    storage = libs / "toml" / "document.yh"
    text = storage.read_text(encoding="utf-8")
    original = ("if (TOML_TEST_FAIL_AFTER >= 0 && p.alloc_count"
                " >= TOML_TEST_FAIL_AFTER) {")
    replacement = (f"if ({INJECTION_GLOBAL} >= 0 && p.alloc_count"
                   f" >= {INJECTION_GLOBAL}) {{")
    if original not in text:
        raise SystemExit("无法定位 pool_alloc 注入条件；产品源码结构已变化")
    storage.write_text(text.replace(original, replacement), encoding="utf-8")


def set_budget(libs: Path, byte_count: int) -> None:
    """把临时标准库副本的单文档分配预算调低。"""
    types = libs / "toml" / "base.yh"
    text = types.read_text(encoding="utf-8")
    original = "const TOML_MAX_BYTES u64 = 134217728"
    replacement = f"const TOML_MAX_BYTES u64 = {byte_count}"
    if original not in text:
        raise SystemExit("无法定位 TOML_MAX_BYTES；产品源码结构已变化")
    types.write_text(text.replace(original, replacement), encoding="utf-8")


def run_case(compiler: Path, libs: Path, fixture: str, work: Path,
             expected: str) -> str:
    """复制 fixture、用给定标准库构建并运行，返回 stdout。"""
    case = work / fixture
    shutil.copytree(PROJECTS / fixture, case)
    env = dict(os.environ)
    env["YH_STDLIB"] = str(libs)
    built = subprocess.run([str(compiler), "build"], cwd=case,
                           capture_output=True, text=True, timeout=900,
                           env=env)
    binary = case / ".build" / fixture
    if built.returncode != 0 or not binary.exists():
        print(f"FAIL {fixture} 构建失败 rc={built.returncode}")
        print((built.stderr or built.stdout)[-1000:])
        raise SystemExit(1)
    shown = subprocess.run([str(binary)], cwd=case, capture_output=True,
                           text=True, timeout=1800, env=env)
    output = (shown.stdout or "").strip()
    if shown.returncode != 0 or not output.startswith(expected):
        print(f"FAIL {fixture} rc={shown.returncode}")
        print(f"stdout: {shown.stdout[-800:]!r}")
        print(f"stderr: {shown.stderr[-800:]!r}")
        raise SystemExit(1)
    return output


def main() -> int:
    ap = argparse.ArgumentParser(description="TOML 分配失败注入门")
    ap.add_argument("--compiler", default=str(ROOT / "yh"),
                    help="编译器路径（默认仓库根 ./yh）")
    ap.add_argument("--stdlib", default=str(ROOT / "libs"),
                    help="标准库根（默认仓库根 libs/）")
    ap.add_argument("--workdir", default=str(ROOT / "tmp" / "toml-inject"),
                    help="工作目录（默认 tmp/toml-inject）")
    ap.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    ap.add_argument("--keep", action="store_true", help="保留工作目录")
    args = ap.parse_args()

    compiler = Path(args.compiler).resolve()
    stdlib = Path(args.stdlib).resolve()
    if not compiler.exists() or not (stdlib / "toml").is_dir():
        print("编译器或标准库路径无效")
        return 1
    work = Path(args.workdir).resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    fail_libs = work / "fail-libs"
    copy_stdlib(stdlib, fail_libs)
    inject_test_seam(fail_libs)
    output = run_case(compiler, fail_libs, "tomlinject", work, "INJECT_OK ")
    count = int(output.split()[1])
    if count < 1:
        print(f"FAIL 注入点数异常: {count}")
        return 1

    budget_libs = work / "budget-libs"
    copy_stdlib(stdlib, budget_libs)
    set_budget(budget_libs, BUDGET_BYTES)
    run_case(compiler, budget_libs, "tomlbudget", work, "BUDGET_OK")

    if not args.quiet:
        print(f"OK   分配失败注入：{count} 个失败点，最终成功")
        print(f"OK   预算强制失败：TOML_MAX_BYTES={BUDGET_BYTES}")
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    print(f"toml injection: 通过（{count} 个分配失败点 + 预算门）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
