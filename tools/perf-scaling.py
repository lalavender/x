#!/usr/bin/env python3
"""合成规模序列：按函数数 / 模块数 / 依赖深度三个轴放大负载，测冷编伸缩。

对齐 docs/02-plan/yh-编译器性能测试方案-2026-10-23.md 的 PF3「规模增长」：

- 每个轴只改一个维度，其余（语言特性、优化级别、调度并发）保持默认；
- 生成的工程写到 tmp/perf/scaling/<axis>-<size>/，每次测量前删 .build；
- 记录冷编墙钟（median/p95/MAD）、worker 四段归因累计、IR/check 计数、
  产物 `.text` 与文件大小，以及运行校验（累加值必须等于生成器算的期望）；
- 报告写入 tmp/perf/scaling-<run-id>/{scaling.json,scaling.md}。

用法：
    python3 tools/perf-scaling.py                    # 三个轴 × 1/2/4/8，各 3 轮
    python3 tools/perf-scaling.py --rounds 5 --axes functions
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

# --stats 已从 CLI 移除（2026-11-10）：统计输出改由 YH_STATS=1 开启。
os.environ.setdefault("YH_STATS", "1")

ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / "tmp" / "perf" / "scaling"
PHASE_RE = re.compile(
    r"time_schedule_ns=(\d+) time_object_ns=(\d+) time_link_ns=(\d+)")
STAGE_RE = re.compile(
    r"time_front_ns=(\d+) time_lower_ns=(\d+) time_irbuild_ns=(\d+) "
    r"time_bridge_ns=(\d+)")
IR_RE = re.compile(r"ir_functions=(\d+) ir_cache_hits=(\d+) ir_cache_misses=(\d+)")
# PL1：lowering 细分（prep/decl/build/verify/lookup/cache/fn/capture）。
LOWER_RE = re.compile(
    r"time_lower_prep_ns=(\d+) time_lower_decl_ns=(\d+) "
    r"time_lower_build_ns=(\d+) time_lower_verify_ns=(\d+) "
    r"time_lower_lookup_ns=(\d+) time_lower_cache_ns=(\d+) "
    r"time_lower_fn_ns=(\d+) time_lower_capture_ns=(\d+)")
LOWER_NAMES = ("prep", "decl", "build", "verify", "lookup", "cache", "fn", "capture")
PROJECT_TOML = """[project]
os = "host"
arch = "host"
name = "{name}"
source = "src"
"""


def write_project(root: Path, name: str, files: dict[str, str]) -> None:
    """按 {相对路径: 内容} 写一个工程；先清空旧目录，避免残留旧模块。"""
    if root.exists():
        shutil.rmtree(root)
    (root / "src").mkdir(parents=True)
    (root / "project.toml").write_text(PROJECT_TOML.format(name=name),
                                       encoding="utf-8")
    for rel, text in files.items():
        path = root / "src" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def gen_functions(root: Path, size: int) -> int:
    """函数数轴：单模块 N = 64×size 个小函数，main 全部调用。

    返回运行期期望的累加值（main 返回 acc - expected，0 表示校验通过）。
    """
    count = 64 * size
    body = ["module main;\n"]
    total = 0
    for i in range(count):
        # 名字不能用 f32/f64：它们是浮点类型关键字，不能当函数名。
        body.append(f"\nfn fun{i}(x int) int {{\n    return x + {i};\n}}\n")
        total += 1 + i
    calls = "\n".join(f"    acc += fun{i}(1);" for i in range(count))
    body.append(f"\nfn main() int {{\n    let acc int = 0;\n{calls}\n"
                f"    return acc - {total};\n}}\n")
    write_project(root, f"scale_functions_{count}", {"main/main.yh": "".join(body)})
    return total


def gen_modules(root: Path, size: int) -> int:
    """模块数轴：4×size 个模块，每模块 16 个公开函数，main 逐模块调用一个。"""
    modules = 4 * size
    files = {}
    total = 0
    imports = []
    calls = []
    for m in range(modules):
        fn_lines = ["module m%d;\n" % m]
        for k in range(16):
            fn_lines.append(f"\npub fn g{m}_{k}(x int) int {{\n    return x + {m * 100 + k};\n}}\n")
        files[f"m{m}/m{m}.yh"] = "".join(fn_lines)
        imports.append(f"import m{m};")
        calls.append(f"    acc += m{m}.g{m}_0(1);")
        total += 1 + m * 100
    main = ["module main;\n", "\n".join(imports), "\n\nfn main() int {",
            "    let acc int = 0;"] + calls + [f"    return acc - {total};", "}", ""]
    files["main/main.yh"] = "\n".join(main)
    write_project(root, f"scale_modules_{modules}", files)
    return total


def gen_depth(root: Path, size: int) -> int:
    """依赖深度轴：2×size 个模块串成链，main 导入链首，每层 +1。"""
    depth = 2 * size
    files = {}
    for level in range(depth):
        if level + 1 < depth:
            text = (f"module m{level};\n\nimport m{level + 1};\n\n"
                    f"pub fn step(x int) int {{\n"
                    f"    return m{level + 1}.step(x) + 1;\n}}\n")
        else:
            text = (f"module m{level};\n\npub fn step(x int) int {{\n"
                    f"    return x + 1;\n}}\n")
        files[f"m{level}/m{level}.yh"] = text
    expected = depth
    files["main/main.yh"] = (
        "module main;\n\nimport m0;\n\nfn main() int {\n"
        f"    return m0.step(0) - {expected};\n}}\n")
    write_project(root, f"scale_depth_{depth}", files)
    return expected


AXES = {
    "functions": (gen_functions, 64),
    "modules": (gen_modules, 4),
    "depth": (gen_depth, 2),
}


def run_build(compiler: Path, project: Path, timeout: int) -> dict:
    """一次冷编：返回墙钟、阶段、四段归因、IR 计数与产物大小。"""
    load = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
    started = time.perf_counter()
    proc = subprocess.run([str(compiler), "build"], cwd=project,
                          capture_output=True, text=True, timeout=timeout)
    elapsed = (time.perf_counter() - started) * 1000
    output = proc.stdout + proc.stderr
    phases = {k: 0 for k in ("schedule", "object", "link")}
    for m in PHASE_RE.finditer(output):
        for i, key in enumerate(("schedule", "object", "link")):
            phases[key] = max(phases[key], int(m.group(i + 1)))
    stages = {k: 0 for k in ("front", "lower", "irbuild", "bridge")}
    for m in STAGE_RE.finditer(output):
        for i, key in enumerate(("front", "lower", "irbuild", "bridge")):
            stages[key] += int(m.group(i + 1))
    lower = {name: 0 for name in LOWER_NAMES}
    for m in LOWER_RE.finditer(output):
        for i, name in enumerate(LOWER_NAMES):
            lower[name] += int(m.group(i + 1))
    ir = {"functions": 0, "hits": 0, "misses": 0}
    for m in IR_RE.finditer(output):
        ir["functions"] += int(m.group(1))
        ir["hits"] += int(m.group(2))
        ir["misses"] += int(m.group(3))
    return {"exit": proc.returncode, "wall_ms": round(elapsed, 1), "load1": load,
            "phases_ms": {k: round(v / 1e6, 1) for k, v in phases.items()},
            "stages_ms": {k: round(v / 1e6, 1) for k, v in stages.items()},
            "ir": ir,
            "lower_ms": {k: round(v / 1e6, 1) for k, v in lower.items()},
            "tail": output[-400:]}


def project_binary(project: Path) -> Path | None:
    """默认产物的路径：.build/<project.name>（与 yh build 的产物命名一致）。"""
    match = re.search(r'^name\s*=\s*"([^"]+)"', (project / "project.toml").read_text(
        encoding="utf-8"), re.MULTILINE)
    if not match:
        return None
    path = project / ".build" / match.group(1)
    return path if path.is_file() else None


def binary_size(project: Path) -> dict:
    """产物文件大小与 .text 段（与 perf-product.py 同口径）。"""
    binary = project_binary(project)
    if binary is None:
        return {"file_bytes": 0, "text_bytes": 0}
    text = 0
    if platform.system() == "Darwin":
        out = subprocess.run(["size", "-m", str(binary)],
                             capture_output=True, text=True).stdout
        inside = False
        for line in out.splitlines():
            stripped = line.strip()
            if stripped.startswith("Segment"):
                inside = "__TEXT" in stripped
            elif inside and stripped.startswith("Section __text:"):
                text = int(stripped.split(":")[1])
    else:
        out = subprocess.run(["size", "-A", str(binary)],
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0] == ".text" and parts[1].isdigit():
                text = int(parts[1])
    return {"file_bytes": binary.stat().st_size, "text_bytes": text}


def measure_write_cache(compiler: Path, project: Path, rounds: int,
                        timeout: int) -> dict:
    """写缓存路径：每轮删对象逼出 worker，测 capture（IR 序列化）与重编函数数。

    PC3 之后冷编不写函数缓存；只有「manifest/link.manifest 存在」的重编才写
    `.fir`，所以这里保留 manifest、只删对象。删掉 link.manifest 会让构建退回
    冷编路径（capture 恒为 0），是本目录踩过的坑。
    """
    samples = []
    for _ in range(rounds):
        for path in project.glob(".build/targets/*/llvm/*/obj/*.o"):
            path.unlink()
        sample = run_build(compiler, project, timeout)
        samples.append(sample)
    ok = [s for s in samples if s["exit"] == 0]
    if not ok:
        return {"failed": len(samples)}
    capture = sorted(s["lower_ms"]["capture"] for s in ok)
    lowered = sorted(s["ir"]["misses"] for s in ok)
    return {
        "write_rounds": len(ok),
        "write_capture_ms": round(statistics.median(capture), 1),
        "write_lowered": int(statistics.median(lowered)),
        "write_wall_ms": round(statistics.median(s["wall_ms"] for s in ok), 1),
        "write_capture_per_fn_ms": round(statistics.median(capture) /
                                         max(1, statistics.median(lowered)), 2),
    }


def measure(compiler: Path, project: Path, rounds: int, warmup: int,
            timeout: int) -> dict:
    """冷编 rounds 轮（每轮先删 .build），前 warmup 轮不计分；返回汇总。"""
    samples = []
    for index in range(warmup + rounds):
        shutil.rmtree(project / ".build", ignore_errors=True)
        sample = run_build(compiler, project, timeout)
        if index >= warmup:
            samples.append(sample)
    walls = sorted(s["wall_ms"] for s in samples if s["exit"] == 0)
    failed = len(samples) - len(walls)
    result = {"rounds": rounds, "failed": failed,
              "samples_ms": [s["wall_ms"] for s in samples]}
    if walls:
        median = statistics.median(walls)
        result.update({
            "median_ms": round(median, 1),
            "p95_ms": round(walls[max(0, min(len(walls) - 1,
                                             int(len(walls) * 0.95 + 0.999) - 1))], 1),
            "mad_ms": round(statistics.median(abs(w - median) for w in walls), 1),
        })
        ok = [s for s in samples if s["exit"] == 0]
        result["phases_ms"] = {k: round(statistics.median(s["phases_ms"][k] for s in ok), 1)
                              for k in ("schedule", "object", "link")}
        result["stages_ms"] = {k: round(statistics.median(s["stages_ms"][k] for s in ok), 1)
                              for k in ("front", "lower", "irbuild", "bridge")}
        result["lower_ms"] = {k: round(statistics.median(s["lower_ms"][k] for s in ok), 1)
                             for k in LOWER_NAMES}
        result["ir"] = {k: int(statistics.median(s["ir"][k] for s in ok))
                        for k in ("functions", "hits", "misses")}
        result["load1_median"] = round(statistics.median(s["load1"] for s in ok), 2)
        # 产物校验：程序必须按生成器算出的期望返回 0。
        run = project_binary(project)
        if run is not None:
            done = subprocess.run([str(run)], cwd=project, capture_output=True)
            result["run_exit"] = done.returncode
            result.update(binary_size(project))
    return result


def main() -> int:
    """生成三个轴的规模序列，逐档冷编并出报告。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(ROOT / "yh"))
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--axes", default="functions,modules,depth")
    parser.add_argument("--sizes", default="1,2,4,8")
    parser.add_argument("--workers", default="", help="设置 YH_WORKERS（默认不设）")
    parser.add_argument("--write-cache", action="store_true",
                        help="额外测写缓存路径（capture 序列化）：删对象不删 manifest")
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve()
    if not compiler.is_file():
        print(f"编译器不存在：{compiler}", file=sys.stderr)
        return 2
    sizes = [int(item) for item in args.sizes.split(",") if item.strip()]
    run_id = time.strftime("%Y%m%d-%H%M%S")
    outdir = ROOT / "tmp" / "perf" / f"scaling-{run_id}"
    outdir.mkdir(parents=True, exist_ok=True)
    # worker 上限通过环境变量传给被测编译器（run_build 继承当前进程环境）。
    if args.workers:
        os.environ["YH_WORKERS"] = args.workers
    report = {"run_id": run_id, "target": f"{platform.system()}/{platform.machine()}",
              "host": platform.platform(), "cpu_count": os.cpu_count(),
              "compiler": {"path": str(compiler),
                           "sha256": hashlib.sha256(compiler.read_bytes()).hexdigest()},
              "rounds": args.rounds, "warmup": args.warmup,
              "workers": args.workers or "default", "axes": {}, "problems": []}

    for axis in [item.strip() for item in args.axes.split(",") if item.strip()]:
        if axis not in AXES:
            print(f"未知轴：{axis}", file=sys.stderr)
            return 2
        gen, unit = AXES[axis]
        rows = []
        for size in sizes:
            project = WORK_ROOT / f"{axis}-{size}"
            expected = gen(project, size)
            measured = measure(compiler, project, args.rounds, args.warmup,
                               args.timeout)
            if args.write_cache:
                measured.update(measure_write_cache(compiler, project,
                                                    max(1, args.rounds), args.timeout))
            measured.update({"size_multiplier": size,
                             "functions": unit * size if axis == "functions" else
                             (16 * 4 * size if axis == "modules" else 2 * size),
                             "expected": expected})
            if measured.get("failed"):
                report["problems"].append(f"{axis}-{size} 有 {measured['failed']} 轮构建失败")
            if measured.get("run_exit") not in (0, None):
                report["problems"].append(
                    f"{axis}-{size} 产物运行返回 {measured['run_exit']}（期望 0）")
            rows.append(measured)
        report["axes"][axis] = rows
        print(f"{axis}: " + ", ".join(
            f"{row['size_multiplier']}x={row.get('median_ms')}ms" for row in rows))

    (outdir / "scaling.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [f"# 合成规模序列 {run_id}", "",
             f"- 机器：{report['host']} × {report['cpu_count']}（target {report['target']}）",
             f"- 编译器：`{report['compiler']['path']}` "
             f"`{report['compiler']['sha256'][:16]}…`",
             f"- 每档 {args.rounds} 轮冷编（{args.warmup} 轮预热），YH_WORKERS="
             f"{report['workers']}", ""]
    for axis, rows in report["axes"].items():
        lines += [f"## {axis}", "",
                  "| 档 | 规模 | 中位 ms | p95 | MAD | schedule | 前端 | lowering | "
                  "其中 verify | 其中真 lowering | IR 构造 | 内嵌桥 | IR 函数 | 运行 | "
                  ".text B | 文件 B | 写缓存 capture | 其中每函数 ms |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | "
                  "--- | --- | --- | --- | --- | --- | --- |"]
        for row in rows:
            stages = row.get("stages_ms", {})
            phases = row.get("phases_ms", {})
            lower = row.get("lower_ms", {})
            lines.append(
                f"| {row['size_multiplier']}× | {row['functions']} 单元 | "
                f"{row.get('median_ms')} | {row.get('p95_ms')} | {row.get('mad_ms')} | "
                f"{phases.get('schedule')} | {stages.get('front')} | "
                f"{stages.get('lower')} | {lower.get('verify')} | "
                f"{lower.get('fn')} | {stages.get('irbuild')} | "
                f"{stages.get('bridge')} | {row.get('ir', {}).get('functions')} | "
                f"{row.get('run_exit')} | {row.get('text_bytes')} | "
                f"{row.get('file_bytes')} | {row.get('write_capture_ms', '-')} | "
                f"{row.get('write_capture_per_fn_ms', '-')} |")
        lines.append("")
    if report["problems"]:
        lines += ["## 无效项", ""] + [f"- {p}" for p in report["problems"]] + [""]
    (outdir / "scaling.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[3:]))
    print(f"\n报告：{outdir / 'scaling.md'}")
    return 0 if not report["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
