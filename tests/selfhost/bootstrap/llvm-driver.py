#!/usr/bin/env python3
"""LL9 驱动门：项目、单文件与 check 共享目标/后端/优化参数。"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

# --stats 已从 CLI 移除（2026-11-10）：统计输出改由 YH_STATS=1 开启。
os.environ.setdefault("YH_STATS", "1")

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "tests/yh-run/run/llvm-project-cache.yh"
FIXTURE = ROOT / "tests/modules/projects/llvmcache"
TARGET = "x86_64-unknown-linux-gnu"


def run(command, cwd, env=None):
    """运行测试进程并收集标准输出和诊断。"""
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=300)


def main():
    """检查无 LLVM 工具的 check 与 LLVM 单文件、build、run 入口。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    if not compiler.is_file():
        raise SystemExit(f"编译器不存在: {compiler}")
    temp_root = ROOT / "tmp"
    temp_root.mkdir(exist_ok=True)
    work = temp_root / "llvm-driver-空间 test"
    shutil.rmtree(work, ignore_errors=True)
    source = work / "源码 with spaces.yh"
    source.parent.mkdir(parents=True)
    shutil.copy2(SOURCE, source)
    project = work / "项目 with spaces"
    shutil.copytree(FIXTURE, project)
    env = dict(os.environ)
    env["PATH"] = "/nonexistent"

    check = run([str(compiler), "--backend", "llvm", "--target", TARGET,
                 "-O2", "check"], cwd=project, env=env)
    assert check.returncode == 0, check.stdout + check.stderr
    assert not list((project / ".build/check").rglob("*.o")), \
        "check 无工具模式生成了对象"

    syntax = run([str(compiler), "--backend", "llvm", "--target", TARGET,
                  "-O0", "--syntax-check", str(source)], cwd=work, env=env)
    assert syntax.returncode == 0, syntax.stdout + syntax.stderr

    emitted = run([str(compiler), "--backend", "llvm", "--target", TARGET,
                   "-O0", "--emit-asm", str(source)], cwd=work, env=env)
    assert emitted.returncode == 0, emitted.stdout + emitted.stderr
    assert ".text" in emitted.stdout or ".section" in emitted.stdout, emitted.stdout[:500]

    output = work / "单文件 输出"
    single = run([str(compiler), "--backend", "llvm", "--target", TARGET,
                  "-O0", str(source), "-o", str(output)], cwd=work)
    assert single.returncode == 0, single.stdout + single.stderr
    assert subprocess.run([str(output)]).returncode == 42

    built = run([str(compiler), "--backend", "llvm", "--target", TARGET,
                 "-O2", "build"], cwd=project)
    assert built.returncode == 0, built.stdout + built.stderr
    stats = [dict(item.split("=", 1) for item in line.split()[1:])
             for line in built.stderr.splitlines() if line.startswith("yh-stats ")]
    assert stats, "LLVM build 未报告受检/发射计数"
    checked = sum(int(row["checked_functions"]) for row in stats)
    emitted = sum(int(row["backend_emitted_functions"]) for row in stats)
    fallback = sum(int(row["fallback_functions"]) for row in stats)
    assert checked == emitted == 1 and fallback == 0, \
        f"LLVM 覆盖计数不符：checked={checked} emitted={emitted} fallback={fallback}"
    executed = run([str(compiler), "--backend", "llvm", "--target", TARGET,
                    "-O2", "run"], cwd=project)
    assert executed.returncode == 42, executed.stdout + executed.stderr

    print("LLVM 驱动通过：check 无外部工具、语法检查、emit、单文件编译、build/run 与空格路径")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
