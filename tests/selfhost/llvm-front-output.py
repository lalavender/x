#!/usr/bin/env python3
"""独立的受检前端门：使用真实 gen 模块确认旧输出四缓冲为零。"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    """复制隔离 fixture，编译并运行入口；日志保存于本门独占目录。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    work = ROOT / "tmp/llvm-migration/front-output"
    project = work / "project"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(ROOT / "tests/modules/projects/llvmfront", project)
    shutil.copytree(ROOT / "compiler/gen", project / "gen",
                    ignore=shutil.ignore_patterns(".build"))
    (project / "gen/project.toml").write_text(
        '[project]\nos = "host"\narch = "host"\nname = "gen"\nsource = "."\n', encoding="utf-8")
    result = subprocess.run([str(compiler), "build"], cwd=project,
                            env=os.environ.copy(), capture_output=True, text=True)
    (work / "build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(project / ".build/llvmfront")], cwd=project,
                            capture_output=True, text=True)
    (work / "run.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, (result.returncode, result.stderr)
    assert "front-boundary=ok" in result.stdout, result.stdout
    print("LL2 受检前端输出门通过：边界进入/退出恢复通过")


if __name__ == "__main__":
    main()
