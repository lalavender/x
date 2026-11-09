#!/usr/bin/env python3
"""验证 yh check 的项目语义结果与无后端产物契约。"""

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VALID = ROOT / "tests" / "modules" / "projects" / "tokenreplay"
INVALID = ROOT / "tests" / "modules" / "projects" / "checkbad"


def check_artifacts(project: Path, label: str) -> bool:
    """确认全新项目的检查结果没有留下任何构建文件。"""
    build = project / ".build"
    found = [str(path.relative_to(project)) for path in build.rglob("*")
             if path.is_file()] if build.exists() else []
    if found:
        print(f"{label} 留下构建产物：{found}")
        return False
    return True


def check_transient_artifacts(project: Path, label: str) -> bool:
    """确认本轮独立 check 目录没有留下任何文件。"""
    transient = project / ".build" / "check"
    found = [str(path.relative_to(project)) for path in transient.rglob("*")
             if path.is_file()] if transient.exists() else []
    if found:
        print(f"{label} 留下 check 临时文件：{found}")
        return False
    return True


def main() -> int:
    """运行有效/无效项目检查，并监视 PATH 中的汇编器和链接器。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    temp_root = ROOT / "tmp"
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="check-command-", dir=temp_root) as temp:
        work = Path(temp)
        wrappers = work / "tools"
        wrappers.mkdir()
        log = work / "tool-calls.log"
        for name in ("gcc", "clang"):
            wrapper = wrappers / name
            wrapper.write_text(
                "#!/bin/sh\n"
                'printf "%s\\n" "${0##*/}" >> "$YH_CHECK_TOOL_LOG"\n'
                "exit 91\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = str(wrappers) + os.pathsep + env.get("PATH", "")
        env["YH_CHECK_TOOL_LOG"] = str(log)
        # --stats 已从 CLI 移除（2026-11-10）：统计由环境变量开启。
        env["YH_STATS"] = "1"
        for label, fixture, want_ok in (
            ("valid", VALID, True),
            ("invalid", INVALID, False),
        ):
            project = work / label
            shutil.copytree(fixture, project)
            result = subprocess.run(
                [str(compiler), "check"],
                cwd=project, env=env,
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout + result.stderr
            passed = (result.returncode == 0) if want_ok else result.returncode != 0
            if want_ok and "检查通过" not in result.stdout:
                passed = False
            if want_ok and not any(int(count) > 0
                                   for count in re.findall(r"ast_nodes=(\d+)", output)):
                passed = False
            if want_ok and not any(int(count) > 0
                                   for count in re.findall(r"stmt_nodes=(\d+)", output)):
                passed = False
            if want_ok and not any(int(count) > 0
                                   for count in re.findall(r"decl_nodes=(\d+)", output)):
                passed = False
            if want_ok and not any(int(count) > 0
                                   for count in re.findall(r"ast_refs=(\d+)", output)):
                passed = False
            if want_ok and not any(int(count) > 0
                                   for count in re.findall(r"ast_bindings=(\d+)", output)):
                passed = False
            if want_ok and sum(int(count) for count in
                               re.findall(r"ast_bindings=(\d+)", output)) < 18:
                passed = False
            if not want_ok and "错误:" not in output:
                passed = False
            if not passed:
                print(f"{label} 项目 check 结果错误：退出码 {result.returncode}\n{output[-1200:]}")
                return 1
            if not check_artifacts(project, label):
                return 1
        for label, fixture, want_ok in (
            ("file-valid", ROOT / "tests" / "modules" / "fixtures" / "check-file-valid.yh", True),
            ("file-invalid", ROOT / "tests" / "modules" / "fixtures" / "check-file-invalid.yh", False),
        ):
            directory = work / label
            directory.mkdir()
            source = directory / "unit.yh"
            shutil.copyfile(fixture, source)
            result = subprocess.run(
                [str(compiler), "check", str(source)], cwd=directory, env=env,
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout + result.stderr
            passed = (result.returncode == 0) if want_ok else result.returncode != 0
            if want_ok:
                passed = passed and "检查通过" in result.stdout
            else:
                passed = passed and "未声明" in output
            if sorted(path.name for path in directory.iterdir()) != ["unit.yh"]:
                passed = False
            if not passed:
                print(f"{label} 单文件 check 结果错误：退出码 {result.returncode}\n{output[-1200:]}")
                return 1
        cached = work / "cached"
        shutil.copytree(VALID, cached)
        sentinel = cached / ".build" / "iface" / "preserved.s.i"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_bytes(b"preserve formal cache\n")
        result = subprocess.run(
            [str(compiler), "check"], cwd=cached, env=env,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0 or sentinel.read_bytes() != b"preserve formal cache\n":
            print(f"check 覆盖了正式构建缓存：退出码 {result.returncode}\n{result.stdout}{result.stderr}")
            return 1
        if not check_transient_artifacts(cached, "cached"):
            return 1
        if log.exists() and log.read_text(encoding="utf-8").strip():
            print(f"yh check 调用了外部汇编器/链接器：{log.read_text(encoding='utf-8')}")
            return 1
    print("yh check：有效/无效项目通过预期检查，未生成后端产物或调用汇编器/链接器")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
