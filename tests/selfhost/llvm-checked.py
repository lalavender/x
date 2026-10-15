#!/usr/bin/env python3
"""LL2 受检模块所有权门：独立复制语义表，并在旧 arena 重置后真实执行检查。"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/llvm-migration/snapshot"


def run(command, cwd):
    """运行实际编译器或产物，给长 qemu 启动留出有界超时。"""
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=600)


def main():
    """构建包含真实 ast/gen 源码的隔离项目，验证快照脱离原存储仍可用。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    project = WORK / "ownership"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(ROOT / "tests/modules/projects/llvmchecked", project,
                    ignore=shutil.ignore_patterns("fixture.yh", ".build"))
    core = project / "compiler"
    core.mkdir()
    for module in ("gen", "lex", "ast", "comptime", "ir", "backend"):
        # llvm_bridge.yh 只声明内嵌桥的 C ABI；本门不链接桥，拷入时排除。
        shutil.copytree(ROOT / "compiler" / module, core / module,
                        ignore=shutil.ignore_patterns("llvm_bridge.yh"))
    (core / "project.toml").write_text('[project]\nname = "checkedcore"\nsource = "."\n')
    shutil.copyfile(ROOT / "tests/modules/projects/llvmchecked/fixture.yh",
                    core / "ast/checked_fixture.yh")
    result = run([str(compiler), "build"], project)
    assert result.returncode == 0, result.stdout + result.stderr
    result = run([str(project / ".build/llvmchecked")], project)
    assert result.returncode == 0 and result.stdout == "checked-snapshot=ok\n", (
        result.returncode, result.stdout, result.stderr)
    (WORK / "checked-report.json").write_text(json.dumps({
        "ownership": "ok", "arena_reset": "ok", "type_name_source_copy": "ok",
        "aggregate_type_closure": "ok", "repeat_release": "ok",
        "invalid_capture_cleanup": "ok", "legacy_asm_ranges_independent": "ok",
        "compiler": str(compiler),
    }, indent=2) + "\n")
    print("LL2 快照通过：AST/声明/类型/绑定/名称/源码独立复制、重复释放")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
