#!/usr/bin/env python3
"""libs/os 自有验收 runner。

两段：
  1. Linux 目标类型检查：把仓库 tests/modules/projects 里的 os/sys 平台用例
     逐个复制到工作目录，用 `-target aarch64-unknown-linux-gnu check` 检查
     平台文件组合与公开签名（Linux 原生运行仍由 tests/modules 的 Linux
     专属用例承担）。
  2. Darwin 契约：构建 libs/os/test/main.yh 并运行端到端断言（文件 API 与
     错误分类、getattrlistbulk 目录读取、cwd、环境、时间/映射、管道、
     posix_spawn 的退出码/信号/EACCES/ENOENT 与 wait 错误）。非 Darwin 宿主
     明确 SKIP，不做降级运行。

fixture 与 runner 都在 libs/os/test/，只依赖当前编译器与 libs 目录。

用法:
    python3 libs/os/test/run.py
    python3 libs/os/test/run.py --compiler ./yh --workdir tmp/os-test --keep

退出码：通过或 SKIP 为 0；失败为 1。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent  # libs/os/test -> 仓库根
LONG_NAME = "n" * 60
LINUX_TARGET = "aarch64-unknown-linux-gnu"
LINUX_FIXTURES = [
    "sysraw", "sysfiles", "osfiles", "syseintr", "sysprocess", "osprocess",
    "systime", "sysmemory", "sysdirs", "osdirs", "osenv",
]


def run(cmd, cwd, env, timeout=300):
    """运行子命令并返回 CompletedProcess。"""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=env)


def linux_typecheck(compiler: Path, work: Path, env, quiet: bool) -> tuple:
    """逐个检查 Linux 平台用例；返回 (通过数, 总数, 是否可运行)。"""
    source = ROOT / "tests" / "modules" / "projects"
    if not source.is_dir():
        return 0, 0, False
    root = work / "linux-check"
    root.mkdir(parents=True, exist_ok=True)
    passed = 0
    total = 0
    for name in LINUX_FIXTURES:
        fixture = source / name
        if not fixture.is_dir():
            continue
        total += 1
        dst = root / name
        shutil.copytree(fixture, dst)
        checked = run([str(compiler), "-target", LINUX_TARGET, "check"],
                      dst, env)
        if checked.returncode == 0:
            passed += 1
            if not quiet:
                print(f"OK   linux-check/{name}")
        else:
            print(f"FAIL linux-check/{name}: rc={checked.returncode}")
            print((checked.stderr or checked.stdout)[-500:])
    return passed, total, True


def darwin_contract(compiler: Path, work: Path, env, quiet: bool) -> int:
    """构建并运行 Darwin 端到端断言；返回 0 通过、1 失败。"""
    dst = work / "darwin"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / "project.toml", dst / "project.toml")
    shutil.copy2(HERE / "main.yh", dst / "main.yh")
    # 目录测试的固定样本：一个 60 字节名称、一个普通文件、一个子目录。
    sample = dst / "work"
    sample.mkdir()
    (sample / LONG_NAME).write_text("")
    (sample / "short.txt").write_text("")
    (sample / "subdir").mkdir()

    built = run([str(compiler), "build"], dst, env)
    binary = dst / ".build" / "oscheck"
    if built.returncode != 0 or not binary.exists():
        print(f"FAIL os-darwin: 构建失败 rc={built.returncode}")
        print((built.stderr or built.stdout)[-600:])
        return 1
    shown = run([str(binary)], dst, env)
    if shown.returncode == 0 and "os8 darwin ok" in shown.stdout:
        if not quiet:
            print("OK   os-darwin")
        return 0
    print(f"FAIL os-darwin: rc={shown.returncode}; "
          f"stdout={shown.stdout[-300:]!r}; stderr={shown.stderr[-300:]!r}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="libs/os 自有验收 runner")
    ap.add_argument("--compiler", default=str(ROOT / "yh"),
                    help="编译器路径（默认仓库根 ./yh）")
    ap.add_argument("--stdlib", default=str(ROOT / "libs"),
                    help="标准库根（默认仓库根 libs/）")
    ap.add_argument("--workdir", default=str(ROOT / "tmp" / "os-test"),
                    help="用例工作目录（默认 tmp/os-test）")
    ap.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    ap.add_argument("--keep", action="store_true", help="保留工作目录")
    args = ap.parse_args()

    compiler = Path(args.compiler).resolve()
    if not compiler.exists():
        print(f"编译器不存在: {compiler}")
        return 1
    stdlib = Path(args.stdlib).resolve()
    if not (stdlib / "os").is_dir():
        print(f"标准库根缺少 os 模块: {stdlib}")
        return 1

    work = Path(args.workdir).resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["YH_STDLIB"] = str(stdlib)
    failed = 0

    linux_passed, linux_total, linux_ran = linux_typecheck(
        compiler, work, env, args.quiet)
    failed += linux_total - linux_passed

    darwin_ran = sys.platform == "darwin"
    if darwin_ran:
        failed += darwin_contract(compiler, work, env, args.quiet)

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    linux_note = (f"linux-check {linux_passed}/{linux_total}"
                  if linux_ran else "linux-check SKIP（缺少 tests/modules）")
    darwin_note = ("darwin-contract 1/1" if darwin_ran
                   else f"darwin-contract SKIP（宿主 {sys.platform}）")
    print(f"os: {linux_note}；{darwin_note}（编译器 {compiler}）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
