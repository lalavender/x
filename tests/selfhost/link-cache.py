#!/usr/bin/env python3
"""验证热构建跳过汇编/链接，且实现变化只重汇编所属模块。"""

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "modules" / "projects" / "tokenreplay"
STATS_RE = re.compile(r"yh-stats .* asm=(\d+) link=(\d+) compiler_hashes=(\d+)")


def run_build(compiler: Path, project: Path, output: Path, env: dict) -> subprocess.CompletedProcess:
    """在 fixture 项目目录构建指定程序。"""
    return subprocess.run(
        [str(compiler), "build", "--stats", "-o", str(output)], cwd=project, env=env,
        capture_output=True, text=True, timeout=120,
    )


def read_calls(log: Path) -> list[str]:
    """读取 wrapper 捕获的汇编与链接调用。"""
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

def n_assemble(calls: list[str]) -> int:
    """汇编调用次数，不区分用哪个汇编器。"""
    return sum(1 for line in calls if line.startswith("assemble "))

def n_link(calls: list[str]) -> int:
    """最终链接调用次数。"""
    return sum(1 for line in calls if line.startswith("link "))


def stat_counts(result: subprocess.CompletedProcess) -> tuple[int, int, int]:
    """合并父进程与 worker 的汇编/链接/编译器身份计数。"""
    output = result.stdout + result.stderr
    counts = [tuple(int(value) for value in match) for match in STATS_RE.findall(output)]
    return tuple(sum(item[index] for item in counts) for index in range(3))


def main() -> int:
    """冷构建、热构建和依赖函数变化三次测量缓存边界。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    # 汇编步用系统 cc；门要验证的是**缓存边界**，不是「用的是哪个汇编器」，
    # 因此统一按 assemble/link 两类计数。
    real_tools = {name: shutil.which(name) for name in ("gcc", "clang")}
    real_tools = {name: path for name, path in real_tools.items() if path is not None}
    if not real_tools:
        print("找不到 gcc/clang，无法验证链接缓存")
        return 1

    temp_root = ROOT / "tmp"
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="link-cache-", dir=temp_root) as temp:
        work = Path(temp)
        project = work / "project"
        shutil.copytree(FIXTURE, project)
        wrappers = work / "tools"
        wrappers.mkdir()
        log = work / "tool-calls.log"
        for name, real_tool in real_tools.items():
            wrapper = wrappers / name
            wrapper.write_text(
                "#!/bin/sh\n"
                f'real_tool="$YH_LINK_CACHE_REAL_{name.upper()}"\n'
                'case "$1" in\n'
                '  -print-search-dirs|-print-sysroot|-dumpmachine|-dumpversion|'
                '-dumpfullversion|-dumpspecs|-print-file-name=*|-print-prog-name=*) '
                'exec "$real_tool" "$@" ;;\n'
                'esac\n'
                'kind=link\n'
                'if [ "$1" = "-c" ] || [ "$1" = "asm" ]; then kind=assemble; fi\n'
                f'printf "%s {name}\\n" "$kind" >> "$YH_LINK_CACHE_LOG"\n'
                'exec "$real_tool" "$@"\n',
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = str(wrappers) + os.pathsep + env.get("PATH", "")
        env["YH_LINK_CACHE_LOG"] = str(log)
        for tool_name, tool_path in real_tools.items():
            env[f"YH_LINK_CACHE_REAL_{tool_name.upper()}"] = tool_path
        output = work / "program"

        # RS3b 按文件对象：冷构建汇编次数 = 每源文件一个 .s + 每模块一个
        # 运行时桩对象 <tag>.stub.s。
        sources = list(project.rglob("*.yh"))
        modules = {
            re.search(r"(?m)^\s*module\s+([A-Za-z_][A-Za-z0-9_]*)\s*;",
                      path.read_text(encoding="utf-8")).group(1)
            for path in sources
        }
        expected_asm = len(sources) + len(modules)

        cold = run_build(compiler, project, output, env)
        if cold.returncode != 0:
            print(f"冷构建失败：\n{cold.stdout}{cold.stderr}")
            return 1
        first = read_calls(log)
        if n_assemble(first) != expected_asm or n_link(first) != 1 or \
                stat_counts(cold) != (expected_asm, 1, 1):
            print(f"冷构建调用次数不符（期望 {expected_asm} 次汇编）：{first}")
            return 1
        if subprocess.run([str(output)], check=False).returncode != 42:
            print("冷构建程序结果不符")
            return 1

        hot = run_build(compiler, project, output, env)
        second = read_calls(log)
        if hot.returncode != 0 or second != first or stat_counts(hot) != (0, 0, 1):
            print(f"热构建未复用对象/链接结果：\n{hot.stdout}{hot.stderr}\n{second}")
            return 1

        object_file = next((project / ".build" / "obj").rglob("*.o"))
        object_file.write_bytes(b"corrupt object\n")
        repaired_object = run_build(compiler, project, output, env)
        third = read_calls(log)
        delta = third[len(second):]
        if repaired_object.returncode != 0 or \
                n_assemble(delta) != 1 or n_link(delta) != 0 or \
                stat_counts(repaired_object) != (1, 0, 1):
            print(f"损坏对象未被安全重建：\n{repaired_object.stdout}{repaired_object.stderr}\n{delta}")
            return 1
        if subprocess.run([str(output)], check=False).returncode != 42:
            print("对象修复后程序结果不符")
            return 1
        second = third

        output.write_bytes(b"corrupt executable\n")
        repaired_output = run_build(compiler, project, output, env)
        third = read_calls(log)
        delta = third[len(second):]
        if repaired_output.returncode != 0 or \
                n_assemble(delta) != 0 or n_link(delta) != 1 or \
                stat_counts(repaired_output) != (0, 1, 1):
            print(f"损坏可执行文件未被安全重链：\n{repaired_output.stdout}{repaired_output.stderr}\n{delta}")
            return 1
        if subprocess.run([str(output)], check=False).returncode != 42:
            print("链接修复后程序结果不符")
            return 1
        second = third

        implementation = next(
            path for path in project.rglob("*.yh")
            if "return n * 2;" in path.read_text(encoding="utf-8")
        )
        implementation.write_text(
            implementation.read_text(encoding="utf-8").replace(
                "return n * 2;", "return n * 3;"),
            encoding="utf-8",
        )
        changed = run_build(compiler, project, output, env)
        third = read_calls(log)
        delta = third[len(second):]
        if changed.returncode != 0:
            print(f"函数变化后构建失败：\n{changed.stdout}{changed.stderr}")
            return 1
        if n_assemble(delta) != 1 or n_link(delta) != 1 or \
                stat_counts(changed) != (1, 1, 1):
            print(f"函数变化的调用次数不符：{delta}")
            return 1
        if subprocess.run([str(output)], check=False).returncode != 63:
            print("增量构建结果未更新")
            return 1

    print("对象与链接缓存：热构建 0/0，损坏对象 1/0，损坏程序 0/1，函数变化 1/1（汇编/链接）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
