#!/usr/bin/env python3
"""产物体积报告（J6 度量物）：printf 基线与 fmt 基线的体积对照。

构建 tests/perf/fmt-size/ 下的两个 fixture（本机目标、默认开关），输出文件
大小与主要段大小，便于验证 J6 各项优化（-dead_strip、依赖项目 O2、-x）的实际
效果。默认只报告（软门）：`fmt/printf` 比值超过 --budget-ratio 时打印告警但
仍返回 0；`--strict` 才把它变成失败。

usage:
    python3 tools/size-report.py [--compiler ./yh] [--workdir tmp/size-report]
                                [--budget-ratio 1.2] [--json] [--strict]
退出码：构建失败 1；否则 0（--strict 时超预算也返回 1）。
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "perf" / "fmt-size"
CASES = ("printf-hello", "fmt-hello")


def build(compiler, workdir, case):
    """把 fixture 复制到工作目录后构建，返回产物路径。"""
    target = workdir / case
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(FIXTURES / case, target)
    proc = subprocess.run([str(compiler), "build"], cwd=str(target),
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise SystemExit(f"FAIL 构建 {case}：{proc.stderr.strip()[-400:]}")
    name = (target / "project.toml").read_text().split('name = "')[1].split('"')[0]
    binary = target / ".build" / name
    if not binary.is_file():
        raise SystemExit(f"FAIL {case} 未产出可执行文件")
    return binary


def sections(binary):
    """读取主要段/节大小；Darwin 用 size -m，Linux 用 size -A（缺失则跳过）。"""
    result = {}
    if sys.platform == "darwin":
        proc = subprocess.run(["size", "-m", str(binary)],
                              capture_output=True, text=True)
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == "Section":
                result[parts[1].rstrip(":")] = int(parts[2])
        for line in proc.stdout.splitlines():
            if line.startswith("Segment __TEXT:"):
                result["__TEXT"] = int(line.split(":")[1].split()[0])
    else:
        proc = subprocess.run(["size", "-A", str(binary)],
                              capture_output=True, text=True)
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0].startswith(".text"):
                result[".text"] = int(parts[1])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(ROOT / "yh"))
    parser.add_argument("--workdir", default=str(ROOT / "tmp" / "size-report"))
    parser.add_argument("--budget-ratio", type=float, default=1.2,
                        help="fmt/printf 文件大小比值上限（软门）")
    parser.add_argument("--json", action="store_true", help="只输出 JSON")
    parser.add_argument("--strict", action="store_true", help="超预算时返回 1")
    args = parser.parse_args()

    compiler = Path(args.compiler).resolve()
    if not compiler.is_file():
        raise SystemExit(f"FAIL 编译器不存在：{compiler}")
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    report = {}
    for case in CASES:
        binary = build(compiler, workdir, case)
        report[case] = {"file": binary.stat().st_size, "sections": sections(binary)}

    ratio = report["fmt-hello"]["file"] / report["printf-hello"]["file"]
    report["ratio"] = round(ratio, 4)
    report["budget_ratio"] = args.budget_ratio
    report["within_budget"] = ratio <= args.budget_ratio

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for case in CASES:
            entry = report[case]
            parts = " ".join(f"{k}={v}" for k, v in sorted(entry["sections"].items()))
            print(f"{case:14s} file={entry['file']:>8} B  {parts}")
        state = "OK" if report["within_budget"] else "超预算"
        print(f"比值 fmt/printf = {ratio:.3f}（上限 {args.budget_ratio}）：{state}")

    return 0 if (report["within_budget"] or not args.strict) else 1


if __name__ == "__main__":
    sys.exit(main())
