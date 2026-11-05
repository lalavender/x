#!/usr/bin/env python3
"""编译体验基线：冷编 / 全量重编（含写缓存）/ 热编 / 单函数改动的可复跑对照。

对齐 docs/02-plan/yh-编译器性能测试方案-2026-10-23.md 的 PF0/PF1：

- 冻结输入：把 compiler/ 复制到工作目录，记录源文件清单与 SHA-256（`corpus_sha256`），
  之后每次都在这份副本上测，不受工作区改动影响；
- 四个场景先做 `--warmup` 轮不计分预热，再各采样 `--iterations` 轮，记录墙钟、
  yh --stats 的父进程阶段耗时、本轮 load、缓存写入量；
- 汇总给出 median / p95 / MAD；有失败或超时样本、或编译器路径不存在时整批标为
  `invalid`，报告不给出性能通过结论；
- 可选 A/B：`--ab PATH` 给第二个编译器，成对交错（A1 B1 A2 B2 …）并给出变化率；
- 原始样本与汇总写入 `tmp/perf/<run-id>/{raw.json,report.md}`。

用法：
    python3 tools/perf-baseline.py                     # 当前 ./yh，3 轮 + 3 轮预热
    python3 tools/perf-baseline.py --iterations 20     # 正式口径（PF1b）
    python3 tools/perf-baseline.py --ab /path/to/old/yh --iterations 20
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
import tempfile
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
STAGE_RE = re.compile(
    r"time_front_ns=(\d+) time_lower_ns=(\d+) time_irbuild_ns=(\d+) "
    r"time_bridge_ns=(\d+)")
LOWER_RE = re.compile(
    r"time_lower_prep_ns=(\d+) time_lower_decl_ns=(\d+) "
    r"time_lower_build_ns=(\d+) time_lower_verify_ns=(\d+) "
    r"time_lower_lookup_ns=(\d+) time_lower_cache_ns=(\d+) "
    r"time_lower_fn_ns=(\d+) time_lower_capture_ns=(\d+)")
PHASE_NAMES = ("project", "schedule", "object", "link", "total")
# PF2 归因字段：worker 内四段累计，四段互斥（不含链接与 LLVM 文本写出）。
STAGE_NAMES = ("front", "lower", "irbuild", "bridge")
# PL1：lowering 内部七段（前四段互斥覆盖整个 lowering，后三段覆盖 build 内部）。
LOWER_NAMES = ("prep", "decl", "build", "verify", "lookup", "cache", "fn",
               "capture")
# 进程树 RSS 采样间隔：采样本身要起 ps，太密会把测量污染得比信号还大。
RSS_INTERVAL_S = 0.2
# 内存口径：footprint（Darwin 物理足迹 / Linux VmHWM 高水位）或 rss（ps 采样）。
MEM_MODES = ("footprint", "rss")
# 方案 §7/§8：负载明显异常（其他构建并发）时该批次不可比。
LOAD_LIMIT = 8.0
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


def stage_corpus(work: Path, name: str) -> Path:
    """把冻结语料复制到 `work/name/compiler`；tmp 与 .build 不参与测量。

    A/B 各用一份独立副本（`name` 为 a/b）：缓存与产物互不覆盖，否则交错的
    修改会互相污染，hot/单函数场景会退化成全量重编（方案 §5 第 2 条）。

    语料目录只是 `compiler/`，但复制后仍须补齐它的同层依赖：

    - `../tmp`：闭包与桥产物（软链到仓库 tmp，本次测量不重建）；
    - `../libs`：标准库是显式跨项目依赖（`project.toml` 的
      `libs = {path = "../libs"}`），缺了它每轮构建会立刻以
      `yh: 无法打开文件: ../libs/project.toml` 退出——2026-11-06 的
      perf run 42097618792 就是这样红的（当时 `perf.yml` 上一轮还失败在更早的
      冷编步骤，所以这个缺依赖从 CLI-R 起一直没被跑到）。

    `libs` 不计入 `corpus_sha256`（该哈希只描述被测的 `compiler/` 语料）：
    标准库改动不会改变语料版本号，只会体现在耗时上。
    """
    base = work / name
    project = base / "compiler"
    if project.exists():
        shutil.rmtree(project)
    base.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CORPUS, project,
                    ignore=shutil.ignore_patterns(".build", "tmp"))
    # 依赖副本同样丢掉 .build/tmp：场景里的冷编只清 compiler/.build，
    # 副本若带历史构建产物会污染 cold 场景。
    libs = base / "libs"
    if libs.exists():
        shutil.rmtree(libs)
    shutil.copytree(ROOT / "libs", libs,
                    ignore=shutil.ignore_patterns(".build", "tmp"))
    # 编译器项目把闭包路径写成 ../tmp/llvm-migration/…，副本需要同一个相对布局。
    link = base / "tmp"
    if not link.exists():
        link.symlink_to(ROOT / "tmp", target_is_directory=True)
    return project


def _darwin_footprint_mb(pid: int) -> float:
    """Darwin：proc_pid_rusage(RUSAGE_INFO_V4) 的 ri_phys_footprint（MB）。

    物理足迹是内核记账的「该进程实际占用」：包含 dirty/压缩页，不重复计入
    共享的干净文件页，因此比 ps 的 RSS 更接近真实占用。字段偏移来自
    struct rusage_info_v4：ri_uuid[16] 之后第 7 个 u64 即 ri_phys_footprint。
    """
    try:
        import ctypes
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
        buf = ctypes.create_string_buffer(1024)
        if libproc.proc_pid_rusage(pid, 4, buf) != 0:
            return 0.0
        return int.from_bytes(buf.raw[72:80], "little") / (1024.0 * 1024.0)
    except Exception:  # noqa: BLE001 —— 缺 libproc/权限时退化为 0，报告会写明
        return 0.0


def _linux_hwm_mb(pid: int) -> float:
    """Linux：/proc/<pid>/status 的 VmHWM（进程自身高水位，采样不会低估）。"""
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return 0.0


def tree_pids(root_pid: int) -> list[int]:
    """以 root_pid 为根的进程树（按 ppid 展开），用于逐进程取内存。"""
    try:
        listing = subprocess.run(["ps", "-axo", "pid,ppid"],
                                 capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return [root_pid]
    children: dict[int, list[int]] = {}
    for line in listing.splitlines()[1:]:
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        children.setdefault(ppid, []).append(pid)
    out, stack, seen = [], [root_pid], set()
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
        stack.extend(children.get(pid, []))
    return out


def tree_footprint_mb(root_pid: int) -> float:
    """进程树内存：逐进程取物理足迹（Darwin）/ VmHWM（Linux）后求和。

    仍是**采样**：进程在两拍之间退出时看不到它的峰值（Linux 的 VmHWM 是内核
    高水位，采样不会低于真实值；Darwin 的 footprint 是当前值，可能漏掉短峰）。
    """
    total = 0.0
    for pid in tree_pids(root_pid):
        if platform.system() == "Darwin":
            total += _darwin_footprint_mb(pid)
        else:
            total += _linux_hwm_mb(pid)
    return total


def tree_rss_mb(root_pid: int) -> float:
    """采样以 root_pid 为根的进程树 RSS（MB）。

    方案 §6 的口径：这是**采样峰值**，不是精确峰值；共享页会在父子间重复计入，
    因此不能当并行构建总内存，只能横向对比同机同负载。
    """
    try:
        listing = subprocess.run(["ps", "-axo", "pid,ppid,rss"],
                                 capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    children: dict[int, list[int]] = {}
    rss: dict[int, int] = {}
    for line in listing.splitlines()[1:]:
        parts = line.split()
        if len(parts) != 3:
            continue
        try:
            pid, ppid, kb = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        children.setdefault(ppid, []).append(pid)
        rss[pid] = kb
    total = 0
    stack = [root_pid]
    seen = set()
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        total += rss.get(pid, 0)
        stack.extend(children.get(pid, []))
    return total / 1024.0


def build_args(opt: str | None) -> list[str]:
    """构建参数：`--opt 2` 时插 `-O2`（优化级别是被测负载，不是工具自身）。"""
    args = [f"-O{opt}"] if opt else []
    return args + ["build", "--stats"]


def run_build(compiler: Path, project: Path, timeout: int,
              mem_mode: str | None = None, opt: str | None = None) -> dict:
    """执行一次 yh build，收集墙钟、阶段耗时与缓存计数。

    退出码本身不足以证明这一轮可用：方案 §6 要求“缺失字段写不支持，不能默认为零”。
    因此缺少 `time_*_ns` / `ir_*` / `check_*` 统计行时，该轮记 `error`，由
    summarize/validity 算作失败并使整批 `invalid`（不静默当 0 ms）。
    """
    load = load_average()
    started = time.perf_counter()
    timeout_sample = {"exit": -1, "error": f"timeout>{timeout}s",
                      "wall_ns": int((time.perf_counter() - started) * 1e9),
                      "load1": load,
                      "phases_ns": {name: 0 for name in PHASE_NAMES},
                      "ir_hits": 0, "ir_misses": 0, "check_hits": 0,
                      "check_misses": 0, "stage_ns": {name: 0 for name in STAGE_NAMES},
                      "stage_missing": True, "rss_peak_mb": 0.0, "tail": ""}
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as sink:
        # 输出走临时文件而不是管道：构建输出可能超过管道缓冲，读得晚会死锁。
        proc = subprocess.Popen([str(compiler)] + build_args(opt), cwd=project,
                                stdout=sink, stderr=subprocess.STDOUT, text=True)
        deadline = started + timeout
        mem_peak = 0.0
        while proc.poll() is None:
            if mem_mode == "footprint":
                mem_peak = max(mem_peak, tree_footprint_mb(proc.pid))
            elif mem_mode == "rss":
                mem_peak = max(mem_peak, tree_rss_mb(proc.pid))
            if time.perf_counter() > deadline:
                proc.kill()
                proc.wait()
                timeout_sample["wall_ns"] = int((time.perf_counter() - started) * 1e9)
                timeout_sample["mem_peak_mb"] = round(mem_peak, 1)
                timeout_sample["mem_mode"] = mem_mode
                return timeout_sample
            time.sleep(RSS_INTERVAL_S)
        exit_code = proc.returncode
        sink.seek(0)
        output = sink.read()
    elapsed = time.perf_counter() - started
    # 父进程与 worker 都会打 stats 行；只有父进程带真实的阶段耗时，取每列最大值。
    rows = [tuple(int(v) for v in m.groups()) for m in PHASE_RE.finditer(output)]
    phases = {name: (max(row[i] for row in rows) if rows else 0)
              for i, name in enumerate(PHASE_NAMES)}
    ir_hits = sum(int(m.group(2)) for m in IR_RE.finditer(output))
    ir_misses = sum(int(m.group(3)) for m in IR_RE.finditer(output))
    check = CHECK_RE.search(output)
    # PF2 四段：worker 各进程各打一行，按行相加得「累计工作量」（不是墙钟）。
    # 旧编译器不输出这些字段时记“不支持”，不当作 0。
    stage = {name: 0 for name in STAGE_NAMES}
    stage_missing = True
    for m in STAGE_RE.finditer(output):
        stage_missing = False
        for i, name in enumerate(STAGE_NAMES):
            stage[name] += int(m.group(i + 1))
    # PL1：lowering 内部七段，同样按行相加。
    lower_stage = {name: 0 for name in LOWER_NAMES}
    lower_missing = True
    for m in LOWER_RE.finditer(output):
        lower_missing = False
        for i, name in enumerate(LOWER_NAMES):
            lower_stage[name] += int(m.group(i + 1))
    # 先查字段是否存在，再谈值：缺失就是“不支持”，不是 0。
    missing = []
    if not rows:
        missing.append("time_*_ns")
    if not IR_RE.search(output):
        missing.append("ir_*")
    if check is None:
        missing.append("check_*")
    return {
        "exit": exit_code,
        "error": (f"缺统计：{'/'.join(missing)}" if missing else None),
        "stats_missing": missing,
        "wall_ns": int(elapsed * 1e9),
        "load1": load,
        "phases_ns": phases,
        "ir_hits": ir_hits,
        "ir_misses": ir_misses,
        "check_hits": int(check.group(1)) if check else 0,
        "check_misses": int(check.group(2)) if check else 0,
        "stage_ns": stage,
        "stage_missing": stage_missing,
        # PL1：lowering 细分；旧编译器没有这些字段时记“不支持”。
        "lower_ns": lower_stage,
        "lower_missing": lower_missing,
        "mem_peak_mb": round(mem_peak, 1) if mem_mode else None,
        "mem_mode": mem_mode,
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


def scenarios(project: Path, compiler: Path, iterations: int, warmup: int,
              timeout: int, mem_mode: str | None, opt: str | None) -> dict:
    """先按场景顺序做不计分预热，再采样；返回 {场景: [样本]}。

    预热与正式采样走完全相同的准备步骤（清缓存/改接口常量/改函数体），
    避免把文件读取、页缓存与首次链接差异算进正式样本。
    """
    def once(prefix: int) -> None:
        """跑一遍四场景但不留样本（prefix 用于区分预热与采样的修改值）。"""
        shutil.rmtree(project / ".build", ignore_errors=True)
        run_build(compiler, project, timeout, mem_mode, opt)
        bump_probe(project, prefix)
        run_build(compiler, project, timeout, mem_mode, opt)
        run_build(compiler, project, timeout, mem_mode, opt)
        bump_function(project, prefix % 100)
        run_build(compiler, project, timeout, mem_mode, opt)

    for w in range(warmup):
        once(3000 + w)

    out = {"cold": [], "full-rebuild": [], "hot": [], "one-function": []}
    for i in range(iterations):
        shutil.rmtree(project / ".build", ignore_errors=True)
        sample = run_build(compiler, project, timeout, mem_mode, opt)
        sample["fir_records"] = fir_records(project)
        out["cold"].append(sample)
    for i in range(iterations):
        bump_probe(project, 1000 + i)
        out["full-rebuild"].append(run_build(compiler, project, timeout, mem_mode, opt))
    for i in range(iterations):
        out["hot"].append(run_build(compiler, project, timeout, mem_mode, opt))
    for i in range(iterations):
        bump_function(project, 40 + i)
        out["one-function"].append(run_build(compiler, project, timeout, mem_mode, opt))
    return out


def usable(sample: dict) -> bool:
    """该轮能否当样本：退出码 0 且无 error（超时、缺统计行都算不可用）。"""
    return sample["exit"] == 0 and not sample.get("error")


def _mem(samples: list[dict], pick) -> float | None:
    """内存统计；本批未采样（--mem 关闭）时返回 None，报告写“未采”而不是 0。"""
    values = [s["mem_peak_mb"] for s in samples
              if usable(s) and s.get("mem_peak_mb") is not None]
    return round(pick(values), 1) if values else None


def summarize(samples: list[dict]) -> dict:
    """中位数、nearest-rank p95 与 MAD；失败/缺统计样本单独计，不参与统计。"""
    walls = sorted(s["wall_ns"] / 1e6 for s in samples if usable(s))
    if not walls:
        return {"iterations": len(samples), "failed": len(samples),
                "errors": sorted({s.get("error") or f"exit={s['exit']}"
                                  for s in samples})}
    p95 = walls[max(0, min(len(walls) - 1, int(len(walls) * 0.95 + 0.999) - 1))]
    median = statistics.median(walls)
    # MAD（中位绝对偏差）比标准差更抗离群样本；方案 §5 要求保留全部原始值。
    mad = statistics.median(abs(w - median) for w in walls)
    phases = {}
    for key in PHASE_NAMES:
        values = sorted(s["phases_ns"][key] / 1e6 for s in samples if usable(s))
        phases[key] = round(statistics.median(values), 1) if values else 0.0
    stage_ms = {}
    stage_seen = [s for s in samples if usable(s) and not s.get("stage_missing")]
    for key in STAGE_NAMES:
        values = sorted(s["stage_ns"][key] / 1e6 for s in stage_seen)
        stage_ms[key] = round(statistics.median(values), 1) if values else None
    lower_seen = [s for s in samples if usable(s) and not s.get("lower_missing")]
    lower_ms = {}
    for key in LOWER_NAMES:
        values = sorted(s["lower_ns"][key] / 1e6 for s in lower_seen)
        lower_ms[key] = round(statistics.median(values), 1) if values else None
    lower_supported = len(lower_seen) > 0
    hits = [s["ir_hits"] for s in samples if usable(s)]
    misses = [s["ir_misses"] for s in samples if usable(s)]
    checks = [s["check_hits"] for s in samples if usable(s)]
    return {
        "iterations": len(samples),
        "failed": len(samples) - len(walls),
        "median_ms": round(median, 1),
        "p95_ms": round(p95, 1),
        "mad_ms": round(mad, 1),
        "load1_max": round(max(s["load1"] for s in samples), 2),
        "errors": sorted({s["error"] for s in samples if s.get("error")}),
        "load1_median": round(statistics.median(s["load1"] for s in samples), 2),
        "phases_ms": phases,
        "stage_ms": stage_ms,
        "stage_rounds": len(stage_seen),
        "stage_supported": len(stage_seen) > 0,
        "lower_ms": lower_ms,
        "lower_supported": lower_supported,
        "mem_median_mb": _mem(samples, statistics.median),
        "mem_max_mb": _mem(samples, max),
        "mem_mode": next((s.get("mem_mode") for s in samples if s.get("mem_mode")),
                         None),
        "ir_hits": sorted(set(hits)),
        "ir_misses": sorted(set(misses)),
        "check_hits": sorted(set(checks)),
        "fir_records": sorted(set(s.get("fir_records", -1) for s in samples)),
    }


def validity(scenarios_data: dict) -> dict:
    """整批有效性：失败/超时样本即 invalid；高负载单列提醒（方案 §7/§8）。

    只有 `status == "ok"` 的批次才能用来下性能结论；invalid 批次仍保留报告，
    供事后归因与重跑对照。
    """
    reasons = []
    high_load = []
    for name, data in scenarios_data.items():
        for tag in ("a", "b"):
            summary = data.get(tag)
            if not summary:
                continue
            if summary.get("failed"):
                detail = "、".join(summary.get("errors") or ["见 raw.json"])
                reasons.append(f"{name}/{tag} 有 {summary['failed']} 轮失败/超时/缺统计"
                               f"（{detail}）")
            if summary.get("load1_max", 0) > LOAD_LIMIT:
                high_load.append(f"{name}/{tag} load1 峰值 {summary['load1_max']}")
    return {"status": "invalid" if reasons else "ok",
            "reasons": reasons, "high_load": high_load}


def main() -> int:
    """解析参数、冻结语料、跑场景并按需做 A/B 对照。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(ROOT / "yh"),
                        help="基线编译器（默认仓库根 yh）")
    parser.add_argument("--ab", help="第二编译器：与之成对交错，给出变化率")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=3,
                        help="每场景不计分预热轮数（每轮仍按完整场景流程跑一遍）")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="单轮 yh build 超时秒数，超时计作失败样本")
    parser.add_argument("--workdir", default=str(WORK_ROOT / "baseline-work"))
    parser.add_argument("--opt", help="编译优化级别（0/2）；缺省用编译器默认")
    parser.add_argument("--mem", choices=MEM_MODES,
                        help="采进程树内存（footprint=Darwin 物理足迹/Linux VmHWM；"
                             "rss=ps 采样）。采样本身有 5–7%% 时间开销，单独跑")
    parser.add_argument("--rss", action="store_true",
                        help="等价于 --mem rss（旧名）")
    parser.add_argument("--keep-work", action="store_true")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations 必须大于 0")
    if args.rss:
        args.mem = "rss"
    if args.warmup < 0:
        parser.error("--warmup 不能为负")

    # run-id 只到秒；同秒内连跑两次会互相覆盖，故遇到同名目录加序号。
    base_id = time.strftime("%Y%m%d-%H%M%S")
    run_id = base_id
    out_dir = WORK_ROOT / run_id
    suffix = 2
    while out_dir.exists():
        run_id = f"{base_id}-{suffix}"
        out_dir = WORK_ROOT / run_id
        suffix += 1
    out_dir.mkdir(parents=True)
    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    project = stage_corpus(work, "a")
    corpus_hash, files, size = digest_tree(project)

    def compiler_info(path: Path) -> dict:
        """编译器身份；路径不存在时只记 missing，不因缺文件而崩掉整次测量。"""
        if not path.is_file():
            return {"path": str(path), "sha256": None, "missing": True}
        return {"path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    a = Path(args.compiler).resolve()
    b = Path(args.ab).resolve() if args.ab else None
    report = {
        "run_id": run_id,
        "host": platform.platform(),
        "cpu": platform.processor(),
        "cpu_count": os.cpu_count(),
        "target": f"{platform.system()}/{platform.machine()}",
        "corpus": CORPUS.relative_to(ROOT).as_posix(),
        "corpus_version": f"{CORPUS.relative_to(ROOT).as_posix()}@{corpus_hash[:16]}",
        "corpus_sha256": corpus_hash,
        "corpus_files": files,
        "corpus_bytes": size,
        "iterations": args.iterations,
        "warmup": args.warmup,
        "timeout_s": args.timeout,
        "compiler_a": compiler_info(a),
        "scenarios": {},
    }
    if b is not None:
        report["compiler_b"] = compiler_info(b)

    missing = [str(p) for p in (a, b) if p is not None and not p.is_file()]
    if missing:
        # 无编译器就没样本：写一份标为 invalid 的报告并返回非零，不留空白答案。
        report["validity"] = {
            "status": "invalid",
            "reasons": [f"编译器不存在：{p}" for p in missing],
            "high_load": [],
        }
    elif b is None:
        raw = scenarios(project, a, args.iterations, args.warmup, args.timeout,
                        args.mem, args.opt)
        report["scenarios"] = {name: {"a": summarize(samples), "samples": samples}
                               for name, samples in raw.items()}
    else:
        # A/B 成对交错：同一场景内 A_i、B_i 相邻执行，顺序每轮左右交替。
        # 两侧各用独立语料副本，缓存/产物永不交叉，热场景才真是热场景。
        report["scenarios"] = {}
        proj_b = stage_corpus(work, "b")
        if digest_tree(proj_b)[0] != corpus_hash:
            raise SystemExit("A/B 语料副本哈希不一致，拒绝测量")
        proj_of = {"a": project, "b": proj_b}
        pairs = {name: {"a": [], "b": []} for name in
                 ("cold", "full-rebuild", "hot", "one-function")}
        # 预热同样的四场景流程；两侧副本各自的页缓存/链接器缓存都要预热。
        for w in range(args.warmup):
            for tag, compiler in (("a", a), ("b", b)):
                p = proj_of[tag]
                shutil.rmtree(p / ".build", ignore_errors=True)
                run_build(compiler, p, args.timeout, args.mem, args.opt)
                bump_probe(p, 4000 + w)
                run_build(compiler, p, args.timeout, args.mem, args.opt)
                run_build(compiler, p, args.timeout, args.mem, args.opt)
                bump_function(p, 90 + w)
                run_build(compiler, p, args.timeout, args.mem, args.opt)
        for i in range(args.iterations):
            order = (("a", a), ("b", b)) if i % 2 == 0 else (("b", b), ("a", a))
            for tag, compiler in order:
                p = proj_of[tag]
                shutil.rmtree(p / ".build", ignore_errors=True)
                pairs["cold"][tag].append(run_build(compiler, p, args.timeout, args.mem, args.opt))
            for tag, compiler in order:
                p = proj_of[tag]
                bump_probe(p, 2000 + i * 2 + (0 if tag == "a" else 1))
                pairs["full-rebuild"][tag].append(run_build(compiler, p, args.timeout, args.mem, args.opt))
            for tag, compiler in order:
                pairs["hot"][tag].append(
                    run_build(compiler, proj_of[tag], args.timeout))
            for tag, compiler in order:
                p = proj_of[tag]
                bump_function(p, 60 + i * 2 + (0 if tag == "a" else 1))
                pairs["one-function"][tag].append(
                    run_build(compiler, p, args.timeout, args.mem, args.opt))
        for name, sides in pairs.items():
            sa = summarize(sides["a"])
            sb = summarize(sides["b"])
            delta = None
            if sa.get("median_ms") and sb.get("median_ms"):
                delta = round((sb["median_ms"] / sa["median_ms"] - 1) * 100, 1)
            report["scenarios"][name] = {"a": sa, "b": sb, "delta_pct": delta,
                                         "samples": sides}

    if "validity" not in report:
        report["validity"] = validity(report["scenarios"])

    (out_dir / "raw.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    verdict = report["validity"]
    lines = [f"# 编译体验基线 {run_id}", "",
             f"- 机器：{report['host']} / {report['cpu']} × {report['cpu_count']}"
             f"（target {report['target']}）",
             f"- 语料：{report['corpus']}（{files} 文件、{size} 字节、版本 "
             f"`{report['corpus_version']}`、SHA-256 `{corpus_hash[:16]}…`）",
             f"- A：`{report['compiler_a']['path']}` "
             f"`{(report['compiler_a']['sha256'] or 'missing')[:16]}…`"]
    if report.get("compiler_b"):
        lines.append(f"- B：`{report['compiler_b']['path']}` "
                     f"`{(report['compiler_b']['sha256'] or 'missing')[:16]}…`")
    lines += [f"- 每场景轮数：{args.iterations}（另有 {args.warmup} 轮不计分预热；"
              f"单轮超时 {args.timeout} s）",
              f"- 有效性：**{verdict['status']}**"
              + ("；" + "；".join(verdict["reasons"]) if verdict["reasons"] else "")]
    for note in verdict["high_load"]:
        lines.append(f"  - 高负载提醒（>{LOAD_LIMIT}）：{note}，该批次仅作参考")
    if verdict["status"] != "ok":
        lines.append("  - 本批次样本不足或含失败，**不得据此得出性能通过/回退结论**")
    lines += ["",
              "| 场景 | 中位 ms | p95 ms | MAD ms | load1 中位/峰值 | schedule | "
              "object | link | IR 命中 | check 命中 | 进程树内存 MB（中位/最大）|",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, data in report["scenarios"].items():
        for tag in ("a", "b"):
            summary = data.get(tag)
            if not summary:
                continue
            label = name if tag == "a" else name + " (B)"
            phases = summary.get("phases_ms", {})
            if summary.get("median_ms") is None:
                # 全部样本失败/超时时无统计值：显式标“—”，不留 None 误导读者。
                lines.append(f"| {label} | — | — | — | — | — | — | — | — | — | — |")
                continue
            lines.append(
                f"| {label} | {summary.get('median_ms')} | {summary.get('p95_ms')} | "
                f"{summary.get('mad_ms')} | {summary.get('load1_median')}/"
                f"{summary.get('load1_max')} | {phases.get('schedule')} | "
                f"{phases.get('object')} | {phases.get('link')} | "
                f"{summary.get('ir_hits')} | {summary.get('check_hits')} | "
                f"{summary.get('mem_median_mb') if summary.get('mem_median_mb') is not None else '未采'}/"
                f"{summary.get('mem_max_mb') if summary.get('mem_max_mb') is not None else '未采'} |")
        if data.get("delta_pct") is not None:
            lines.append(
                f"| {name} 变化率 | {data['delta_pct']}% | | | | | | | | | |")
    # PF2 归因表：四段累计 vs schedule（墙钟），并给出有效并发 ≈ 累计/墙钟。
    lines += ["", "### worker 阶段归因（四段累计，中位）", "",
              "| 场景 | 前端 | lowering | IR 构造 | 内嵌桥 | 四段合计 | schedule（墙钟）"
              " | 有效并发 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, data in report["scenarios"].items():
        for tag in ("a", "b"):
            summary = data.get(tag)
            if not summary:
                continue
            label = name if tag == "a" else name + " (B)"
            if not summary.get("stage_supported"):
                # 旧编译器没有归因字段：写“不支持”，不写 0。
                lines.append(f"| {label} | 不支持 | 不支持 | 不支持 | 不支持 | — | — | — |")
                continue
            stage = summary["stage_ms"]
            schedule = summary.get("phases_ms", {}).get("schedule") or 0
            parts = [stage[key] for key in STAGE_NAMES]
            total = sum(parts)
            # 无 worker 编译（全命中）时累计为 0，并发比无意义。
            concurrency = (f"{total / schedule:.2f}×"
                           if schedule and total > 0 else "—")
            lines.append(
                f"| {label} | {stage['front']} | {stage['lower']} | "
                f"{stage['irbuild']} | {stage['bridge']} | {round(total, 1)} | "
                f"{schedule} | {concurrency} |")
    # PL1：lowering 细分表（前四段互斥覆盖 lowering，后三段覆盖 build 内部）。
    lines += ["", "### lowering 细分（PL1，累计中位）", "",
              "| 场景 | prep | decl | build | verify | build 内：lookup | "
              "cache 合并 | 真 lowering | capture |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, data in report["scenarios"].items():
        for tag in ("a", "b"):
            summary = data.get(tag)
            if not summary:
                continue
            label = name if tag == "a" else name + " (B)"
            if not summary.get("lower_supported"):
                lines.append(f"| {label} | 不支持 | 不支持 | 不支持 | 不支持 | "
                             "不支持 | 不支持 | 不支持 | 不支持 |")
                continue
            part = summary["lower_ms"]
            lines.append(
                f"| {label} | {part['prep']} | {part['decl']} | {part['build']} | "
                f"{part['verify']} | {part['lookup']} | {part['cache']} | "
                f"{part['fn']} | {part['capture']} |")
    # 逐轮明细：load1 与墙钟按轮次列出，便于事后核噪声而不必再翻 JSON。
    lines += ["", "### 逐轮样本（load1 / 墙钟 ms）", ""]
    for name, data in report["scenarios"].items():
        raw = data.get("samples")
        for tag in ("a", "b"):
            rounds = raw.get(tag, []) if isinstance(raw, dict) else (raw or [])
            if tag == "b" and not isinstance(raw, dict):
                continue
            if not rounds:
                continue
            loads = ", ".join(str(round(s["load1"], 2)) for s in rounds)
            walls = ", ".join(str(round(s["wall_ns"] / 1e6, 1)) for s in rounds)
            label = name if tag == "a" else name + " (B)"
            lines.append(f"- {label} load1 [{loads}]")
            lines.append(f"- {label} 墙钟 [{walls}]")
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n原始样本：{out_dir / 'raw.json'}")
    if not args.keep_work:
        # 两侧副本都清 .build；语料副本本身保留，避免重构下一次复制开销。
        for name in ("a", "b"):
            shutil.rmtree(work / name / "compiler" / ".build", ignore_errors=True)
    return 0 if verdict["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
