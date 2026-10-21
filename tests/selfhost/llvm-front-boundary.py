#!/usr/bin/env python3
"""LL2 目标边界门：严格解析、构建身份与无 LLVM 工具的 check，后续接受检快照门。"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/llvm-migration/front-boundary"


def run(command, cwd=ROOT, env=None):
    """执行真实候选，保留有界输出和超时，不调用 LLVM 工具。"""
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=180)


def main():
    """先验 CLI 拒绝层，再校验目标 API 的跨模块消费者与无工具项目检查。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    WORK.mkdir(parents=True, exist_ok=True)
    arm = ROOT / "tests/selfhost/llvm-target-arm64.yh"
    x64 = ROOT / "tests/selfhost/llvm-target-x64.yh"
    for flag in ("-target", "--target"):
        result = run([str(compiler), flag, "unsupported-unknown-linux-gnu", "check", str(arm)])
        assert result.returncode == 2 and "不支持的目标" in result.stderr, (
            f"未知目标未明确拒绝：{flag}, rc={result.returncode}, {result.stderr}")
        result = run([str(compiler), flag])
        assert result.returncode == 2 and "缺少目标" in result.stderr, result
    no_tools = WORK / "no-tools"
    no_tools.mkdir(exist_ok=True)
    isolated = dict(os.environ, PATH=str(no_tools))
    for options, source in (([], arm), (["--target", "aarch64-unknown-linux-gnu"], arm),
                            (["--target", "x86_64-unknown-linux-gnu"], x64)):
        result = run([str(compiler), *options, "check", str(source)], env=isolated)
        assert result.returncode == 0, result.stderr
    for alias in ("gnu", "linux", "elf", "darwin", "macho", "macos"):
        result = run([str(compiler), "-target", alias, "check", str(arm)], env=isolated)
        assert result.returncode == 0, f"旧别名映射错误 {alias}: {result.stderr}"
    result = run([str(compiler), "--target", "x86_64-unknown-linux-gnu", "--emit-asm", str(x64)])
    assert result.returncode != 0 and "旧后端" in result.stderr and not result.stdout, result
    selection = WORK / "source-selection"
    shutil.rmtree(selection, ignore_errors=True)
    selection.mkdir()
    (selection / "project.toml").write_text('[project]\nos = "host"\narch = "host"\nname = "selection"\nsource = "."\n')
    for suffix, condition in (("linux.arm64", "linux && arm64"),
                              ("linux.x64", "linux && x64"), ("darwin.x64", "darwin && x64")):
        (selection / f"main.{suffix}.yh").write_text(
            'module main;\nfn main() int {\n'
            f' $if ({condition}) {{ }} $else {{ $compile_error("选择了错误目标源文件"); }}\n'
            ' return 0;\n}\n')
    for triple in ("aarch64-unknown-linux-gnu", "x86_64-unknown-linux-gnu", "x86_64-apple-darwin"):
        result = run([str(compiler), "--target", triple, "check"], cwd=selection, env=isolated)
        assert result.returncode == 0, f"目标源文件筛选错误 {triple}: {result.stderr}"
    project = WORK / "model"
    shutil.rmtree(project, ignore_errors=True)
    shutil.copytree(ROOT / "tests/modules/projects/llvmtarget", project)
    shutil.copytree(ROOT / "compiler/gen", project / "gen")
    (project / "gen/project.toml").write_text('[project]\nos = "host"\narch = "host"\nname = "gen"\nsource = "."\n')
    result = run([str(compiler), "build"], cwd=project)
    assert result.returncode == 0, result.stdout + result.stderr
    result = run([str(project / ".build/llvmtarget")])
    assert result.returncode == 0 and result.stdout == "target-model=ok\n", result
    checked = WORK / "check-model"
    shutil.rmtree(checked, ignore_errors=True)
    shutil.copytree(project, checked, ignore=shutil.ignore_patterns(".build"))
    result = run([str(compiler), "--target", "x86_64-unknown-linux-gnu", "check"],
                 cwd=checked, env=isolated)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not [p for p in (checked / ".build").rglob("*") if p.is_file()], "check 发布后端产物"
    (WORK / "target-report.json").write_text(json.dumps({"target_model": "ok", "check_without_tools": "ok",
                                                       "unknown_target_rejected": True}, indent=2) + "\n")
    print("LL2 目标边界通过：解析/构建身份/无工具 check/旧后端拒绝 x64")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
