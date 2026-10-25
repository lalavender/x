#!/usr/bin/env python3
"""编译体验基线：冷编 / 全量重编（含写缓存）/ 热编 / 单函数改动的可复跑对照。

对齐 docs/02-plan/yh-编译器性能测试方案-2026-10-23.md 的 PF0/PF1：

- 冻结输入：把 compiler/ 复制到工作目录，记录源文件清单与 SHA-256（`corpus_sha256`），
  之后每次都在这份副本上测，不受工作区改动影响；
- 四个场景各自 ≥3 轮，记录墙钟、yh --stats 的父进程阶段耗时、本轮 load、缓存写入量；
- 可选 A/B：`--ab PATH` 给第二个编译器，成对交错（A1 B1 A2 B2 …）并给出变化率；
- 原始样本与汇总写入 `tmp/perf/<run-id>/{raw.json,report.md}`。

用法：
    python3 tools/perf-baseline.py                    # 当前 ./yh，每场景 3 轮
    python3 tools/perf-baseline.py --iterations 5
    python3 tools/perf-baseline.py --ab /path/to/old/yh --iterations 5
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "compiler"
WORK_ROOT = ROOT / "tmp" / "perf"
PHASE_RE = re.compile(
    r"time_project_ns=(\d+) time_schedule_ns=(\d+) time_object_ns=(\d+) "
    r"time_link_ns=(\d+) time_total_ns=(\d+)")
IR_RE = re.compile(r"ir_functions=(\d+) ir_cache_hits=(\d+) ir_cache_misses=(\d+)")
CHECK_RE = re.compile(r"check_cache_hits=(\d+) check_cache_misses=(\d+)")
PROBE_CONST = "PERF_PROBE_VERSION"
PROBE_ANCHOR = "pub fn write_all(fd int, buf *u8, n int) int {\n    let done int = 0"


def load_average() -> float:
    """1 分钟 load average；测量期间必须记录，否则数字不可比。"""
    try:
        return os.getloadavg()[0]
    except OSError:
        return 0.0


def digest_tree(root: Path) -> tuple[str, int, int]:
    """源文件清单 SHA-256（只算 .yh 与 project.toml），返回 (摘要, 文件数, 字节数)。"""
    h = hashlib.sha256()
    files = 0
    size = 0
    for path in sorted(root.rglob("*")):
        if path.is_dir() or path.suffix not in (".yh",) and path.name != "project.toml":
            continue
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        h.update(rel.encode())
        h.update(b"\0")
        h.update(data)
        files += 1
        size += len(data)
    return h.hexdigest(), files, size


def stage_corpus(work: Path) -> Path:
    """复制冻结语料到工作目录；tmp 与 .build 不参与测量。"""
    project = work / "compiler"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(CORPUS, project,
                    ignore=shutil.ignore_patterns(".build", "tmp"))
    # 编译器项目把闭包路径写成 ../tmp/llvm-migration/…，副本需要同一个相对布局。
    link = work / "tmp"
    if not link.exists():
        link.symlink_to(ROOT / "tmp", target_is_directory=True)
    return project


def run_build(compiler: Path, project: Path) -> dict:
    """执行一次 yh build，收集墙钟、阶段耗时与缓存计数。"""
    load = load_average()
    started = time.perf_counter()
    result = subprocess.run([str(compiler), "build", "--stats"], cwd=project,
                            capture_output=True, text=True, timeout=1800)
    elapsed = time.perf_counter() - started
    output = result.stdout + result.stderr
    # 父进程与 worker 都会打 stats 行；只有父进程带真实的阶段耗时，取每列最大值。
    names = ("project", "schedule", "object", "link", "total")
    rows = [tuple(int(v) for v in m.groups()) for m in PHASE_RE.finditer(output)]
    phases = {name: (max(row[i] for row in rows) if rows else 0)
              for i, name in enumerate(names)}
    ir_hits = sum(int(m.group(2)) for m in IR_RE.finditer(output))
    ir_misses = sum(int(m.group(3)) for m in IR_RE.finditer(output))
    check = CHECK_RE.search(output)
    return {
        "exit": result.returncode,
        "wall_ns": int(elapsed * 1e9),
        "load1": load,
        "phases_ns": phases,
        "ir_hits": ir_hits,
        "ir_misses": ir_misses,
        "check_hits": int(check.group(1)) if check else 0,
        "check_misses": int(check.group(2)) if check else 0,
        "tail": output[-600:],
    }


def bump_probe(project: Path, value: int) -> None:
    """改 gen 的接口常量：让 13 个模块全部重编（全量重编场景）。"""
    path = project / "gen" / "state.yh"
    text = path.read_text(encoding="utf-8")
    line = f"pub const {PROBE_CONST} int = {value};"
    if PROBE_CONST in text:
        text = re.sub(rf"pub const {PROBE_CONST} int = \d+;", line, text)
    else:
        text = text.rstrip("\n") + "\n\n" + line + "\n"
    path.write_text(text, encoding="utf-8")


def bump_function(project: Path, value: int) -> None:
    """改一个私有函数的函数体：只让 gen 模块重编，用于单函数改动场景。"""
    path = project / "gen" / "buffer.yh"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"    if \(n < \d+\) \{\n        return -1\n    \}\n", "", text, count=1)
    text = text.replace(
        PROBE_ANCHOR,
        PROBE_ANCHOR.replace("    let done int = 0",
                             f"    if (n < {value}) {{\n        return -1\n    }}\n    let done int = 0", 1),
        1)
    path.write_text(text, encoding="utf-8")


def fir_records(project: Path) -> int:
    """本轮写下的函数级 IR 缓存记录数（PC3 之后冷编应为 0）。"""
    return sum(1 for _ in project.glob(".build/targets/*/*/*/firc/*/*.fir"))


def scenarios(project: Path, compiler: Path, iterations: int) -> dict:
    """跑四个场景；每轮都记录样本，返回 {场景: [样本]}。"""
    out = {"cold": [], "full-rebuild": [], "hot": [], "one-function": []}
    for i in range(iterations):
        shutil.rmtree(project / ".build", ignore_errors=True)
        sample = run_build(compiler, project)
        sample["fir_records"] = fir_records(project)
        out["cold"].append(sample)
    for i in range(iterations):
        bump_probe(project, 1000 + i)
        out["full-rebuild"].append(run_build(compiler, project))
    for i in range(iterations):
        out["hot"].append(run_build(compiler, project))
    for i in range(iterations):
        bump_function(project, 40 + i)
        out["one-function"].append(run_build(compiler, project))
    return out


def summarize(samples: list[dict]) -> dict:
    """中位数和 nearest-rank p95；失败样本单独计。"""
    walls = sorted(s["wall_ns"] / 1e6 for s in samples if s["exit"] == 0)
    if not walls:
        return {"iterations": len(samples), "failed": len(samples)}
    p95 = walls[max(0, min(len(walls) - 1, int(len(walls) * 0.95 + 0.999) - 1))]
    phases = {}
    for key in ("project", "schedule", "object", "link", "total"):
        values = sorted(s["phases_ns"][key] / 1e6 for s in samples if s["exit"] == 0)
        phases[key] = round(statistics.median(values), 1) if values else 0.0
    hits = [s["ir_hits"] for s in samples if s["exit"] == 0]
    misses = [s["ir_misses"] for s in samples if s["exit"] == 0]
    checks = [s["check_hits"] for s in samples if s["exit"] == 0]
    return {
        "iterations": len(samples),
        "failed": len(samples) - len(walls),
        "median_ms": round(statistics.median(walls), 1),
        "p95_ms": round(p95, 1),
        "load1_median": round(statistics.median(s["load1"] for s in samples), 2),
        "phases_ms": phases,
        "ir_hits": sorted(set(hits)),
        "ir_misses": sorted(set(misses)),
        "check_hits": sorted(set(checks)),
        "fir_records": sorted(set(s.get("fir_records", -1) for s in samples)),
    }


def main() -> int:
    """解析参数、冻结语料、跑场景并按需做 A/B 对照。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(ROOT / "yh"),
                        help="基线编译器（默认仓库根 yh）")
    parser.add_argument("--ab", help="第二编译器：与之成对交错，给出变化率")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--workdir", default=str(WORK_ROOT / "baseline-work"))
    parser.add_argument("--keep-work", action="store_true")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations 必须大于 0")

    run_id = time.strftime("%Y%m%d-%H%M%S")
    out_dir = WORK_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    project = stage_corpus(work)
    corpus_hash, files, size = digest_tree(project)

    a = Path(args.compiler).resolve()
    b = Path(args.ab).resolve() if args.ab else None
    report = {
        "run_id": run_id,
        "host": platform.platform(),
        "cpu": platform.processor(),
        "cpu_count": os.cpu_count(),
        "corpus_sha256": corpus_hash,
        "corpus_files": files,
        "corpus_bytes": size,
        "iterations": args.iterations,
        "compiler_a": {"path": str(a),
                       "sha256": hashlib.sha256(a.read_bytes()).hexdigest()},
        "scenarios": {},
    }
    if b is not None:
        report["compiler_b"] = {"path": str(b),
                                "sha256": hashlib.sha256(b.read_bytes()).hexdigest()}

    if b is None:
        raw = scenarios(project, a, args.iterations)
        report["scenarios"] = {name: {"a": summarize(samples), "samples": samples}
                               for name, samples in raw.items()}
    else:
        # A/B 成对交错：同一场景内 A_i、B_i 相邻执行，顺序每轮左右交替。
        report["scenarios"] = {}
        for name in ("cold", "full-rebuild", "hot", "one-function"):
            for compiler in (a, b):
                pass
        pairs = {name: {"a": [], "b": []} for name in
                 ("cold", "full-rebuild", "hot", "one-function")}
        for i in range(args.iterations):
            order = ((a, "a"), (b, "b")) if i % 2 == 0 else ((b, "b"), (a, "a"))
            # 冷编：每轮先清缓存，两侧各测一次会互相污染，故交替使用两份副本。
            shutil.rmtree(project / ".build", ignore_errors=True)
            for compiler, tag in order:
                if tag == "b":
                    shutil.rmtree(project / ".build", ignore_errors=True)
                pairs["cold"][tag].append(run_build(compiler, project))
            for compiler, tag in order:
                bump_probe(project, 2000 + i * 2 + (0 if tag == "a" else 1))
                pairs["full-rebuild"][tag].append(run_build(compiler, project))
            for compiler, tag in order:
                pairs["hot"][tag].append(run_build(compiler, project))
            for compiler, tag in order:
                bump_function(project, 60 + i * 2 + (0 if tag == "a" else 1))
                pairs["one-function"][tag].append(run_build(compiler, project))
        for name, sides in pairs.items():
            sa = summarize(sides["a"])
            sb = summarize(sides["b"])
            delta = None
            if sa.get("median_ms") and sb.get("median_ms"):
                delta = round((sb["median_ms"] / sa["median_ms"] - 1) * 100, 1)
            report["scenarios"][name] = {"a": sa, "b": sb, "delta_pct": delta,
                                         "samples": sides}

    (out_dir / "raw.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [f"# 编译体验基线 {run_id}", "",
             f"- 机器：{report['host']} / {report['cpu']} × {report['cpu_count']}",
             f"- 语料：{CORPUS.relative_to(ROOT)}（{files} 文件、{size} 字节、"
             f"SHA-256 `{corpus_hash[:16]}…`）",
             f"- A：`{report['compiler_a']['path']}` `{report['compiler_a']['sha256'][:16]}…`",
             f"- 每场景轮数：{args.iterations}", "",
             "| 场景 | 墙钟中位 ms | p95 ms | load1 | schedule | object | link | IR 命中 | check 命中 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, data in report["scenarios"].items():
        for tag in ("a", "b"):
            summary = data.get(tag)
            if not summary:
                continue
            label = name if tag == "a" else name + " (B)"
            phases = summary.get("phases_ms", {})
            lines.append(
                f"| {label} | {summary.get('median_ms')} | {summary.get('p95_ms')} | "
                f"{summary.get('load1_median')} | {phases.get('schedule')} | "
                f"{phases.get('object')} | {phases.get('link')} | "
                f"{summary.get('ir_hits')} | {summary.get('check_hits')} |")
        if data.get("delta_pct") is not None:
            lines.append(f"| {name} 变化率 | {data['delta_pct']}% | | | | | | | |")
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n原始样本：{out_dir / 'raw.json'}")
    if not args.keep_work:
        shutil.rmtree(project / ".build", ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
