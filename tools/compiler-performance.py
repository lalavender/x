#!/usr/bin/env python3
"""测量冻结编译器语料的热构建、函数体修改与清缓存构建。"""

import argparse
import hashlib
import json
import math
import os
import platform
import re
import resource
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "perf" / "corpus-r0"
FROZEN_PROJECT = CORPUS / "compiler"
STATS_RE = re.compile(
    r"yh-stats lex=(\d+) syntax=(\d+) index=(\d+) pass1=(\d+) "
    r"globals=(\d+) functions=(\d+) (?:ir_functions=(\d+) )?"
    r"(?:ir_cache_hits=\d+ ir_cache_misses=\d+ )?"
    r"(?:ast_nodes=\d+ stmt_nodes=\d+ decl_nodes=\d+ ast_refs=\d+ "
    r"ast_bindings=\d+ )?(?:ast_functions=(\d+) )?workers=(\d+) "
    r"(?:workers_peak=\d+ iface_early=\d+ )?asm=(\d+) link=(\d+) "
    r"compiler_hashes=(\d+)"
)
TIME_RE = re.compile(
    r"yh-stats .* time_project_ns=(\d+) time_schedule_ns=(\d+) "
    r"time_object_ns=(\d+) time_link_ns=(\d+) time_total_ns=(\d+)"
)
ORIGINAL_FUNCTION = b'''pub fn pj_file_exists(path *char) int {
    let fd int = open(path, 0);
    if (fd < 0) {
        return 0;
    }
    close(fd);
    return 1;
}'''
CHANGED_FUNCTION = b'''pub fn pj_file_exists(path *char) int {
    return 0;
}'''


def verify_corpus() -> tuple[int, int, int]:
    """核对冻结语料清单，并返回源文件数、行数和字节数。"""
    manifest = CORPUS / "SHA256SUMS"
    seen = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, rel = line.split("  ", 1)
        path = CORPUS / rel
        # 冻结清单对应入库 LF 文本，Windows 检出的 CRLF 不算内容变化。
        actual = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if actual != digest:
            raise RuntimeError(f"冻结语料校验失败：{rel}")
        seen.add(path.resolve())
    expected = {FROZEN_PROJECT / "project.toml", *FROZEN_PROJECT.rglob("*.yh")}
    if seen != {path.resolve() for path in expected}:
        raise RuntimeError("冻结语料文件集合与 SHA256SUMS 不一致")
    sources = sorted(FROZEN_PROJECT.rglob("*.yh"))
    size = sum(len(path.read_bytes().replace(b"\r\n", b"\n")) for path in sources)
    lines = sum(len(path.read_bytes().splitlines()) for path in sources)
    return len(sources), lines, size


def module_inventory() -> dict[str, int]:
    """统计冻结语料中各 module 声明包含的源文件数。"""
    counts = {}
    for source in FROZEN_PROJECT.rglob("*.yh"):
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.startswith("module ") and line.endswith(";"):
                name = line[7:-1]
                counts[name] = counts.get(name, 0) + 1
                break
    return counts


def prepare_wrappers(path: Path) -> dict[str, str]:
    """创建轻量汇编/链接计数器，并返回可用工具的真实路径。"""
    path.mkdir()
    real_tools = {name: shutil.which(name) for name in ("gcc", "clang")}
    for name, real in real_tools.items():
        if not real:
            continue
        wrapper = path / name
        wrapper.write_text(
            "#!/bin/sh\n"
            'name=${0##*/}\n'
            'kind=link\n'
            '[ "$1" = "-c" ] && kind=assemble\n'
            'printf "%s %s\\n" "$name" "$kind" >> "$YH_TOOL_LOG"\n'
            'if [ "$name" = "gcc" ]; then exec "$YH_REAL_GCC" "$@"; fi\n'
            'exec "$YH_REAL_CLANG" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
    return {name: real for name, real in real_tools.items() if real}


def one_build(compiler: Path, project: Path, wrapper_dir: Path,
              real_tools: dict[str, str], log_path: Path,
              build_args: str = "") -> dict:
    """以独立采样进程执行一次构建并读取其子进程峰值 RSS。"""
    env = dict(os.environ)
    env["PATH"] = str(wrapper_dir) + os.pathsep + env.get("PATH", "")
    env["YH_TOOL_LOG"] = str(log_path)
    for name, real in real_tools.items():
        env[f"YH_REAL_{name.upper()}"] = real
    started = time.perf_counter_ns()
    profile = []
    if b"system(" in (project / "cmd/project_state.yh").read_bytes():
        profile = ["--legacy-system"]
    result = subprocess.run(
        [str(compiler), "build", *shlex.split(build_args), *profile,
         "--stats", "-o", "../yh"], cwd=project,
        capture_output=True, text=True, env=env, timeout=600,
    )
    elapsed_ns = time.perf_counter_ns() - started
    output = result.stdout + result.stderr
    compiled_modules = [line.split("[编译]", 1)[1].strip()
                        for line in output.splitlines() if "[编译]" in line]
    cached_modules = [line.split("[缓存]", 1)[1].strip()
                      for line in output.splitlines() if "[缓存]" in line]
    stat_names = ("lex", "syntax", "index", "pass1", "globals", "functions",
                  "ir_functions", "ast_functions", "workers", "asm", "link",
                  "compiler_hashes")
    stats = [tuple(int(value or 0) for value in match)
             for match in STATS_RE.findall(output)]
    phase_times = [tuple(int(value) for value in match)
                   for match in TIME_RE.findall(output)]
    phase_counts = {name: sum(row[index] for row in stats)
                    for index, name in enumerate(stat_names)}
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    peak_rss = int(usage.ru_maxrss)
    if platform.system() != "Darwin":
        peak_rss *= 1024
    tool_lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
    return {
        "exit_code": result.returncode,
        "elapsed_ns": elapsed_ns,
        "peak_rss_bytes": peak_rss,
        "module_rebuilds": len(compiled_modules),
        "module_cache_hits": len(cached_modules),
        "compiled_modules": compiled_modules,
        "cached_modules": cached_modules,
        "phase_counts": phase_counts,
        "phase_times_ns": {
            name: sum(row[index] for row in phase_times)
            for index, name in enumerate(("project", "schedule", "objects", "link", "total"))
        },
        "assembler_calls": sum(line.endswith(" assemble") for line in tool_lines),
        "link_calls": sum(line.endswith(" link") for line in tool_lines),
        "output_tail": output[-1200:],
    }


def sample_worker(args: argparse.Namespace) -> int:
    """子进程采样入口，保证 ru_maxrss 仅属于当前一次构建。"""
    values = one_build(Path(args.compiler), Path(args.project),
                       Path(args.wrapper_dir), json.loads(args.real_tools),
                       Path(args.tool_log), getattr(args, "build_args", "") or "")
    print(json.dumps(values, ensure_ascii=False))
    return 0


def measure(compiler: Path, project: Path, wrapper_dir: Path,
            real_tools: dict[str, str], log_path: Path,
            build_args: str = "") -> dict:
    """启动隔离采样进程，避免之前构建污染本次峰值内存数据。"""
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker",
         str(compiler), str(project), str(wrapper_dir), json.dumps(real_tools),
         str(log_path), build_args],
        capture_output=True, text=True, timeout=900,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    value = json.loads(result.stdout)
    if value["exit_code"] != 0:
        raise RuntimeError(value["output_tail"])
    return value


def make_project(work: Path) -> Path:
    """复制一次冻结项目到临时工作区并返回构建目录。"""
    work.mkdir(parents=True, exist_ok=True)
    project = work / "compiler"
    shutil.copytree(FROZEN_PROJECT, project)
    # 仅规范化 tmp 中的测量副本，不改写入库冻结源；每轮负载字节保持一致。
    for path in [project / "project.toml", *project.rglob("*.yh")]:
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    return project


def verify_function_change(binary: Path, cwd: Path, changed: bool) -> None:
    """运行生成的编译器，确认函数体变化产生可观察的行为变化。"""
    result = subprocess.run([str(binary), "version"], cwd=cwd,
                            capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    if changed:
        if result.returncode == 0 or "未找到 project.toml" not in output:
            raise RuntimeError("变化后的函数体未改变编译器行为")
    elif result.returncode != 0 or "yh 0.0.4" not in output:
        raise RuntimeError("恢复原函数体后编译器行为未恢复")


def summarize(samples: list[dict]) -> dict:
    """按中位数和 nearest-rank p95 汇总独立进程样本。"""
    times = sorted(item["elapsed_ns"] / 1_000_000 for item in samples)
    p95 = times[max(0, math.ceil(len(times) * 0.95) - 1)]
    compiled = samples[0]["compiled_modules"]
    phase_times = {}
    for name in samples[0]["phase_times_ns"]:
        values = sorted(item["phase_times_ns"][name] for item in samples)
        phase_times[name] = {
            "median_ns": statistics.median(values),
            "p95_ns": values[max(0, math.ceil(len(values) * 0.95) - 1)],
        }
    return {
        "iterations": len(samples),
        "median_ms": statistics.median(times),
        "p95_ms": p95,
        "peak_rss_mib": max(item["peak_rss_bytes"] for item in samples) / (1024 * 1024),
        "module_rebuilds_per_sample": sorted(set(item["module_rebuilds"] for item in samples)),
        "module_cache_hits_per_sample": sorted(set(item["module_cache_hits"] for item in samples)),
        "module_rebuilds": compiled,
        "phase_counts_per_sample": {
            key: sorted(set(item["phase_counts"][key] for item in samples))
            for key in samples[0]["phase_counts"]
        },
        "phase_times_ns_per_sample": phase_times,
        "assembler_calls_per_sample": sorted(set(item["assembler_calls"] for item in samples)),
        "link_calls_per_sample": sorted(set(item["link_calls"] for item in samples)),
    }


def run_scenario(name: str, project: Path, compiler: Path, wrapper_dir: Path,
                 real_tools: dict[str, str], iterations: int, work: Path,
                 build_args: str = "",
                 ) -> dict:
    """预热指定构建场景并采集多轮独立进程样本。"""
    source = project / "cmd" / "project_state.yh"
    original = source.read_bytes()
    original_function = ORIGINAL_FUNCTION
    changed_function = CHANGED_FUNCTION
    if original.count(original_function) == 0:
        original_function = original_function.removeprefix(b"pub ")
        changed_function = changed_function.removeprefix(b"pub ")
    if original.count(original_function) != 1:
        raise RuntimeError("冻结源中的 pj_file_exists 函数与预期不符")
    sample_log = work / "tool-calls.log"
    samples = []
    if name == "no-change":
        source.write_bytes(original)
        measure(compiler, project, wrapper_dir, real_tools, sample_log, build_args)
        warmup = measure(compiler, project, wrapper_dir, real_tools, sample_log, build_args)
        if warmup["module_cache_hits"] == 0:
            raise RuntimeError("无改动场景预热没有建立对象缓存")
        for _ in range(iterations):
            sample_log.unlink(missing_ok=True)
            samples.append(measure(compiler, project, wrapper_dir, real_tools, sample_log, build_args))
    elif name == "function-change":
        source.write_bytes(original)
        measure(compiler, project, wrapper_dir, real_tools, sample_log, build_args)
        binary = project.parent / "yh"
        verify_function_change(binary, project, changed=False)
        for index in range(iterations):
            changed = index % 2 == 0
            body = changed_function if changed else original_function
            source.write_bytes(original.replace(original_function, body, 1))
            sample_log.unlink(missing_ok=True)
            samples.append(measure(compiler, project, wrapper_dir, real_tools, sample_log, build_args))
            verify_function_change(binary, project, changed=changed)
    elif name == "cold-build":
        source.write_bytes(original)
        measure(compiler, project, wrapper_dir, real_tools, sample_log, build_args)
        for _ in range(iterations):
            shutil.rmtree(project / ".build", ignore_errors=True)
            sample_log.unlink(missing_ok=True)
            samples.append(measure(compiler, project, wrapper_dir, real_tools, sample_log, build_args))
    else:
        raise ValueError(name)
    report = summarize(samples)
    report["samples"] = samples
    return report


def main() -> int:
    """验证冻结输入并运行三组性能场景。"""
    global CORPUS, FROZEN_PROJECT
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--compiler", default=str(ROOT / "yh"))
    parser.add_argument("--build-args", default="",
                        help="追加到每次 yh build 的参数，如 --backend llvm --target x86_64-unknown-linux-gnu -O2")
    parser.add_argument("--scenarios", default="no-change,function-change,cold-build",
                        help="逗号分隔的场景子集")
    parser.add_argument("--output", type=Path, help="保存包含原始样本的 JSON 报告")
    parser.add_argument("--corpus", type=Path, help="指定含 compiler/ 和 SHA256SUMS 的冻结快照")
    parser.add_argument("--worker", nargs=6,
                        metavar=("COMPILER", "PROJECT", "WRAPPERS", "TOOLS_JSON", "LOG", "BUILD_ARGS"))
    args = parser.parse_args()
    if args.worker:
        (args.compiler, args.project, args.wrapper_dir, args.real_tools,
         args.tool_log, args.build_args) = args.worker
        return sample_worker(args)
    if args.iterations < 1:
        parser.error("--iterations 必须大于 0")
    if args.corpus:
        CORPUS = args.corpus.resolve()
        FROZEN_PROJECT = CORPUS / "compiler"
    count, lines, size = verify_corpus()
    module_file_counts = module_inventory()
    compiler = Path(args.compiler).resolve()
    temp_root = ROOT / "tmp"
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="compiler-performance-", dir=temp_root) as temp:
        work = Path(temp)
        wrapper_dir = work / "tools"
        real_tools = prepare_wrappers(wrapper_dir)
        if not real_tools:
            raise RuntimeError("未找到 gcc 或 clang，无法记录汇编/链接调用")
        tool_versions = {}
        for name, real in real_tools.items():
            version = subprocess.run([real, "--version"], capture_output=True,
                                     text=True, timeout=10)
            tool_versions[name] = (version.stdout or version.stderr).splitlines()[0]
        host_model = platform.machine()
        memory_bytes = None
        if sys.platform == "darwin":
            model = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                   capture_output=True, text=True, timeout=10)
            memory = subprocess.run(["sysctl", "-n", "hw.memsize"],
                                    capture_output=True, text=True, timeout=10)
            if model.returncode == 0:
                host_model = model.stdout.strip()
            if memory.returncode == 0:
                memory_bytes = int(memory.stdout.strip())
        report = {
            "corpus_revision": (hashlib.sha256((CORPUS / "SHA256SUMS").read_bytes()).hexdigest()
                                if args.corpus else "8e17bdbb41b4dcb66306c79e784c89dc4420a6d9"),
            "corpus_files": count,
            "corpus_lines": lines,
            "corpus_bytes": size,
            "module_file_counts": module_file_counts,
            "host": platform.platform(),
            "machine": host_model,
            "memory_bytes": memory_bytes,
            "iterations": args.iterations,
            "compiler": str(compiler),
            "compiler_sha256": hashlib.sha256(compiler.read_bytes()).hexdigest(),
            "build_args": args.build_args,
            "compiler_profile": ("--legacy-system" if b"system(" in
                                 (FROZEN_PROJECT / "cmd/project_state.yh").read_bytes()
                                 else "systemless 默认配置"),
            "tool_versions": tool_versions,
            "scenarios": {},
        }
        for name in args.scenarios.split(","):
            name = name.strip()
            project = make_project(work / name)
            report["scenarios"][name] = run_scenario(
                name, project, compiler, wrapper_dir, real_tools,
                args.iterations, work / name, args.build_args,
            )
            summary = {key: value for key, value in report["scenarios"][name].items()
                       if key != "samples"}
            print(f"{name}: {json.dumps(summary, ensure_ascii=False)}", flush=True)
        report["tooling"] = {
            "assembler_linker": sorted(real_tools),
            "counted": "PATH 中 gcc/clang 汇编与链接调用；目录/环境 API、ls/printenv 不计",
            "phase_visibility": "模块重编/缓存、词法、顶层声明索引、项目索引、模块遍历、worker、SSA 函数数、项目装载、模块调度、对象缓存/汇编与链接决策耗时及单次 yh 进程峰值 RSS；语义/check 与发射耗时仍未独立计数",
            "rss_note": "RUSAGE_CHILDREN 单次样本的最大子进程 RSS，不是并发进程 RSS 总和",
        }
        serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized, encoding="utf-8")
            print(f"原始样本报告：{args.output}")
        else:
            print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
