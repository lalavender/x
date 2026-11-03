#!/usr/bin/env python3
"""生成产物基准：编译 tests/perf/bench-*.yh，测运行时间与代码体积。

对齐 docs/02-plan/yh-编译器性能测试方案-2026-10-23.md 的「产物质量」：

- 每个用例用 O0/O2 各编译一次单文件产物（`yh <src> -O0|-O2 -o <out>`）；
- 运行时传入规模参数（防常量折叠让负载消失），checksum 由本文件的 Python
  参照实现独立算出，与程序输出逐次比对，不一致即判该用例无效；
- 每档先预热再采样，给出 median / p95 / MAD；
- 体积分三段：`.text`、只读数据（__cstring/__const* 等）、总文件大小；
  编译器自身（静态链接 LLVM）的体积单独记一条，不混入产物代码质量；
- 结果写入 `--outdir` 下的 product.json 与 product.md（默认 tmp/perf/product-<时间>）。

用法：
    python3 tools/perf-product.py                     # ./yh，每档 5 轮
    python3 tools/perf-product.py --runs 9 --outdir tmp/perf/<run-id>
"""

import argparse
import hashlib
import json
import platform
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "tests" / "perf"
OPT_LEVELS = ("O0", "O2")
MASK64 = 1 << 64
LCG_MOD = 1 << 31
LCG_MUL = 1103515245
LCG_ADD = 12345
MOD = 1000000007


def lcg(seed: int) -> int:
    """基准里统一的线性同余发生器（与 .yh 端逐位一致）。"""
    return (seed * LCG_MUL + LCG_ADD) % LCG_MOD


def ref_loop_sum(n: int) -> int:
    """bench-loop-sum 参照：Σ (i*2654435761 % 1000003) mod 1e9+7。

    逐项取模与"先累加后取模"等价；周期为 P/gcd(P,MULT)，故按周期求和加速。
    """
    p, mult = 1000003, 2654435761
    period = p // _gcd(p, mult)
    cycle = sum((i * mult) % p for i in range(period))
    full, rest = divmod(n, period)
    partial = sum((i * mult) % p for i in range(rest))
    return (full * cycle + partial) % MOD


def _gcd(a: int, b: int) -> int:
    """欧几里得算法；仅用于求参照实现的周期长度。"""
    while b:
        a, b = b, a % b
    return a


def _lcg_array(seed: int, count: int, modulus: int) -> tuple[list[int], int]:
    """按 LCG 生成 count 个元素（seed 取模 modulus），返回 (元素, 末态 seed)。"""
    out = []
    for _ in range(count):
        seed = lcg(seed)
        out.append(seed % modulus)
    return out, seed


def ref_array_scan(rounds: int) -> int:
    """bench-array-scan 参照：1024 槽数组按轮次累加取模。"""
    lanes, _ = _lcg_array(12345, 1024, 1000)
    return (rounds * sum(lanes)) % MOD


def ref_sort(rounds: int) -> int:
    """bench-sort-insertion 参照：512 个元素插入排序后的加权和。"""
    src, _ = _lcg_array(987654321, 512, 100000)
    ordered = sorted(src)
    return sum(v * (i + 1) for i, v in enumerate(ordered)) % MOD


def ref_hash(n: int) -> int:
    """bench-hash-fnv 参照：LCG 字节流上的 FNV-1a 32 位哈希。"""
    h = 2166136261
    seed = 1013904223
    for _ in range(n):
        seed = lcg(seed)
        b = (seed // 65536) % 256
        h = ((h ^ b) * 16777619) % (1 << 32)
    return h


def ref_struct_slice(rounds: int) -> int:
    """bench-struct-slice 参照：Vec3 数组按 (x+2y+3z)*k 加权累加。"""
    points, seed = _lcg_array(20240101, 1024 * 3, 1000)
    scores = [points[3 * j] + 2 * points[3 * j + 1] + 3 * points[3 * j + 2]
              for j in range(1024)]
    total = 0
    for r in range(rounds):
        total = (total + sum(scores) * (r + 1)) % MOD
    return total


def ref_call(n: int) -> int:
    """bench-call 参照：迭代版 fib(n) mod 1e9+7（与递归版同值）。"""
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a % MOD


# 用例表：文件 stem → (默认规模, 参照实现, 说明)。规模必须与 .yh 里的缺省一致。
CASES = {
    "bench-loop-sum": (50000000, ref_loop_sum, "整数循环：乘法+取模+累加"),
    "bench-array-scan": (20000, ref_array_scan, "数组扫描：1024 槽累加与求最大"),
    "bench-sort-insertion": (1800, ref_sort, "排序：512 槽插入排序 × 轮数"),
    "bench-hash-fnv": (36000000, ref_hash, "哈希：FNV-1a 32 位 over LCG 字节流"),
    "bench-struct-slice": (16000, ref_struct_slice, "结构体+切片：Vec3 视图传参"),
    "bench-call": (39, ref_call, "函数调用：递归 fib(n)"),
}


def sections(binary: Path) -> dict:
    """解析 Mach-O 的 .text 与只读数据；Linux 走 `size -A` 的 .text/.rodata。

    只统计 __text 与 __cstring/__const* 这类明确的代码/只读常量段，
    不含 __unwind_info/__eh_frame，避免把元数据算成代码体积。
    """
    text = rodata = 0
    if platform.system() == "Darwin":
        out = subprocess.run(["size", "-m", str(binary)],
                             capture_output=True, text=True).stdout
        in_text = False
        for line in out.splitlines():
            stripped = line.strip()
            if stripped.startswith("Segment"):
                in_text = "__TEXT" in stripped
                continue
            match = re.match(r"Section (__\w+): (\d+)", stripped)
            if not match:
                continue
            name, size = match.group(1), int(match.group(2))
            if not in_text:
                continue
            if name == "__text":
                text += size
            elif name.startswith(("__cstring", "__const", "__literal")):
                rodata += size
    else:
        out = subprocess.run(["size", "-A", str(binary)],
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) != 3 or not parts[1].isdigit():
                continue
            if parts[0] == ".text":
                text = int(parts[1])
            elif parts[0] == ".rodata" or parts[0].startswith(".rodata."):
                rodata += int(parts[1])
    return {"text_bytes": text, "rodata_bytes": rodata,
            "file_bytes": binary.stat().st_size}


def timed_runs(binary: Path, arg: str, runs: int, warmup: int) -> dict:
    """预热后计时 runs 次：返回 wall_ms 样本、checksum 与失败原因。"""
    samples, checksums, errors = [], [], []
    for _ in range(warmup):
        subprocess.run([str(binary), arg], capture_output=True, text=True)
    for _ in range(runs):
        started = time.perf_counter()
        result = subprocess.run([str(binary), arg], capture_output=True, text=True,
                                timeout=600)
        samples.append((time.perf_counter() - started) * 1000)
        if result.returncode != 0:
            errors.append(f"退出码 {result.returncode}: {result.stdout.strip()}")
            continue
        match = re.search(r"checksum=(\d+)", result.stdout)
        if not match:
            errors.append(f"缺少 checksum 输出: {result.stdout.strip()[:80]}")
            continue
        checksums.append(int(match.group(1)))
    values = sorted(samples)
    median = statistics.median(values) if values else None
    return {
        "samples_ms": [round(v, 3) for v in samples],
        "median_ms": round(median, 3) if median else None,
        "p95_ms": round(values[max(0, min(len(values) - 1,
                                          int(len(values) * 0.95 + 0.999) - 1))], 3)
        if values else None,
        "mad_ms": round(statistics.median(abs(v - median) for v in values), 3)
        if values else None,
        "checksums": sorted(set(checksums)),
        "errors": errors,
    }


def main() -> int:
    """编译每个用例的 O0/O2 产物，跑参考校验与计时，输出 JSON/Markdown 报告。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(ROOT / "yh"))
    parser.add_argument("--runs", type=int, default=5, help="每档计次（不含预热）")
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--outdir", help="报告目录（默认 tmp/perf/product-<时间>）")
    parser.add_argument("--append-to", help="把产物质量表追加到该 report.md（同批次）")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs 必须大于 0")

    compiler = Path(args.compiler).resolve()
    if not compiler.is_file():
        print(f"编译器不存在：{compiler}", file=sys.stderr)
        return 2
    run_id = time.strftime("%Y%m%d-%H%M%S")
    outdir = Path(args.outdir) if args.outdir else ROOT / "tmp" / "perf" / f"product-{run_id}"
    outdir.mkdir(parents=True, exist_ok=True)
    bindir = outdir / "bin"
    bindir.mkdir(exist_ok=True)

    report = {
        "run_id": run_id,
        "target": f"{platform.system()}/{platform.machine()}",
        "host": platform.platform(),
        "compiler": {"path": str(compiler),
                     "sha256": hashlib.sha256(compiler.read_bytes()).hexdigest(),
                     # 编译器静态链接 LLVM，体积单列，不当作产物代码质量。
                     "file_bytes": compiler.stat().st_size},
        "runs": args.runs,
        "warmup": args.warmup,
        "cases": {},
        "problems": [],
    }

    for stem, (default_arg, ref, note) in CASES.items():
        source = CASES_DIR / f"{stem}.yh"
        if not source.is_file():
            report["problems"].append(f"缺少用例源文件：{source}")
            continue
        expected = ref(default_arg)
        case = {"source": source.relative_to(ROOT).as_posix(),
                "description": note, "input": str(default_arg),
                "expected_checksum": expected, "levels": {}}
        for opt in OPT_LEVELS:
            binary = bindir / f"{stem}-{opt}"
            build = subprocess.run([str(compiler), str(source), f"-{opt}",
                                    "-o", str(binary)],
                                   capture_output=True, text=True)
            if build.returncode != 0:
                report["problems"].append(
                    f"{stem} {opt} 编译失败：{(build.stdout + build.stderr).strip()[-200:]}")
                continue
            measured = timed_runs(binary, str(default_arg), args.runs, args.warmup)
            measured.update(sections(binary))
            measured["checksum_ok"] = measured["checksums"] == [expected]
            if not measured["checksum_ok"]:
                report["problems"].append(
                    f"{stem} {opt} checksum 不符：期望 {expected}，实际 "
                    f"{measured['checksums']}")
            case["levels"][opt] = measured
        report["cases"][stem] = case

    (outdir / "product.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [f"# 生成产物基准 {run_id}", "",
             f"- 机器：{report['host']}（target {report['target']}）",
             f"- 编译器：`{report['compiler']['path']}` "
             f"`{report['compiler']['sha256'][:16]}…`"
             f"（{report['compiler']['file_bytes']} 字节，静态链接 LLVM，单列不计入产物质量）",
             f"- 每档轮数：{args.runs}（另 {args.warmup} 次预热）；checksum 由 Python 参照独立计算",
             f"- 有效性：**{'invalid' if report['problems'] else 'ok'}**"
             + ("；" + "；".join(report["problems"]) if report["problems"] else "")]
    table = ["| 用例 | 输入 | 期望 checksum | 档 | 中位 ms | p95 ms | MAD ms | .text B | 只读 B | 文件 B |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for stem, case in report["cases"].items():
        for opt, data in case["levels"].items():
            table.append(
                f"| {stem} | {case['input']} | {case['expected_checksum']} | {opt} | "
                f"{data['median_ms']} | {data['p95_ms']} | {data['mad_ms']} | "
                f"{data['text_bytes']} | {data['rodata_bytes']} | {data['file_bytes']} |")
    lines = lines + [""] + table
    if report["problems"]:
        lines += ["", "## 无效原因", ""] + [f"- {p}" for p in report["problems"]]
    (outdir / "product.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # --append-to：把同一批次的产物质量表并入编译体验报告，保持单一 run-id。
    if args.append_to:
        target = Path(args.append_to)
        if not target.is_file():
            print(f"--append-to 目标不存在：{target}", file=sys.stderr)
            return 2
        with target.open("a", encoding="utf-8") as handle:
            handle.write("\n## 生成产物质量（O0/O2，同批次）\n\n")
            handle.write("每档 " + str(args.runs) + " 轮，checksum 由 Python 参照独立计算；"
                         "`只读` 只统计 __cstring/__const*，不含 unwind/eh_frame。\n\n")
            handle.write("\n".join(table) + "\n")
    print("\n".join(lines))
    print(f"\n原始数据：{outdir / 'product.json'}")
    return 0 if not report["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
