#!/usr/bin/env python3
"""验证项目 worker 复用文件 token，且构建统计准确。"""

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "modules" / "projects" / "tokenreplay"
STATS_RE = re.compile(
    r"yh-stats lex=(\d+) syntax=(\d+) index=(\d+) pass1=(\d+) "
    r"globals=(\d+) functions=(\d+) (?:ir_functions=\d+ )?"
    r"(?:ir_cache_hits=\d+ ir_cache_misses=\d+ )?"
    r"(?:ast_nodes=\d+ stmt_nodes=\d+ decl_nodes=\d+ ast_refs=\d+ "
    r"ast_bindings=\d+ )?(?:ast_functions=\d+ )?workers=(\d+)"
)
TIMING_RE = re.compile(
    r"yh-stats .* time_project_ns=(\d+) time_schedule_ns=(\d+) "
    r"time_object_ns=(\d+) time_link_ns=(\d+) time_total_ns=(\d+)"
)


def main() -> int:
    """构建多文件/多模块项目并校验词法、解析与 worker 计数。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    temp_root = ROOT / "tmp"
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lex-stats-", dir=temp_root) as temp:
        project = Path(temp) / "project"
        shutil.copytree(FIXTURE, project)
        output = Path(temp) / "app"
        result = subprocess.run(
            [str(compiler), "build", "--stats", "-o", str(output)],
            cwd=project, capture_output=True, text=True, timeout=120,
        )
        output_text = result.stdout + result.stderr
        if result.returncode != 0:
            print(f"多模块构建失败：\n{output_text[-2000:]}")
            return 1
        rows = [tuple(int(value) for value in match)
                for match in STATS_RE.findall(output_text)]
        timing_rows = [tuple(int(value) for value in match)
                       for match in TIMING_RE.findall(output_text)]
        parent_timing = [row for row in timing_rows if row[3] > 0]
        totals = tuple(sum(row[index] for row in rows) for index in range(7))
        # 父进程为四个文件只建一次索引；fork worker 继承只读快照，main
        # 仅额外词法分析 mathx 接口。每个模块仍执行 pass1/全局/函数语义遍。
        expected = (5, 9, 4, 4, 4, 4, 2)
        if len(rows) != 3 or totals != expected or len(parent_timing) != 1:
            print(f"阶段计数错误：进程数={len(rows)}，总计={totals}，期望={expected}")
            print(output_text[-2000:])
            return 1
        project_ns, schedule_ns, object_ns, link_ns, total_ns = parent_timing[0]
        if min(project_ns, schedule_ns, object_ns, link_ns, total_ns) <= 0 \
                or project_ns + schedule_ns + object_ns + link_ns > total_ns:
            print(f"构建阶段计时无效：{parent_timing}")
            return 1
        run = subprocess.run([str(output)], cwd=project, timeout=15)
        if run.returncode != 42:
            print(f"token replay 程序退出码 {run.returncode}，期望 42")
            return 1
        warm = subprocess.run(
            [str(compiler), "build", "--stats", "-o", str(output)],
            cwd=project, capture_output=True, text=True, timeout=120,
        )
        warm_rows = [tuple(int(value) for value in match)
                     for match in STATS_RE.findall(warm.stdout + warm.stderr)]
        warm_timing = [tuple(int(value) for value in match)
                       for match in TIMING_RE.findall(warm.stdout + warm.stderr)]
        warm_expected = (4, 0, 4, 0, 0, 0, 0)
        if warm.returncode != 0 or len(warm_rows) != 1 or warm_rows[0] != warm_expected:
            print(f"热缓存仍进入声明解析/worker：行={warm_rows}，期望={warm_expected}\n"
                  f"{(warm.stdout + warm.stderr)[-1200:]}")
            return 1
        if len(warm_timing) != 1 or min(warm_timing[0]) <= 0 \
                or sum(warm_timing[0][:4]) > warm_timing[0][4]:
            print(f"热构建阶段计时无效：{warm_timing}")
            return 1
    print("前端快照复用：通过（词法 5，声明索引 9，项目文件 4，热构建跳过索引，fork worker 2）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
