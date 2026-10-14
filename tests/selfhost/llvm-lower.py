#!/usr/bin/env python3
"""LL3 纯快照降低门：真实 .yh 受检、销毁原 arena、模块 SSA/phi/call 验证及严格拒绝。"""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/llvm-migration/checked-lower"
FIXTURE = ROOT / "tests/modules/projects/llvmlower"


def run(command, cwd):
    """执行有界的真实候选或产物，保留失败诊断。"""
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=600)


def main():
    """复制真实编译器模块并注入测试前端，输入语义与最终 IR 都需通过实际校验。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    project = WORK / "project"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(FIXTURE, project, ignore=shutil.ignore_patterns("fixture.yh", ".build"))
    core = project / "compiler"
    core.mkdir()
    for module in ("gen", "lex", "ast", "parse", "comptime", "ir", "backend"):
        shutil.copytree(ROOT / "compiler" / module, core / module)
    (core / "project.toml").write_text('[project]\nname = "lowercore"\nsource = "."\n')
    shutil.copyfile(FIXTURE / "fixture.yh", project / "main/fixture.yh")
    result = run([str(Path(args.compiler_path).resolve()), "build"], project)
    (WORK / "build.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    executable = project / ".build/llvmlower"
    for name, expected in (("scalar", "0"), ("pointer", "1"), ("aggregate", "1")):
        result = run([str(executable), str(project / f"input/{name}.yh"), expected], project)
        (WORK / f"{name}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, (name, result.returncode, result.stdout, result.stderr)
        if expected == "0":
            assert "functions=5" in result.stdout and "calls=4" in result.stdout, result.stdout
            assert "phis=0" not in result.stdout, result.stdout
        else:
            assert "lower-rejected=ok" in result.stdout and f"{name}_body" in result.stderr, result
            assert ".yh:" in result.stderr and "LLVM" in result.stderr, result.stderr
    print("LL3 纯快照降低门通过：arena销毁后SSA/phi/固定调用、typedCT排除、不支持体严格拒绝")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
