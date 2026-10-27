#!/usr/bin/env python3
"""校验一次性能批次是否可用：validity=ok 且产物 checksum 全部相符。

CI 的 perf workflow 用它把「测量本身失败」与「性能回退」区分开：
前者让 job 变红，后者只出报告（本仓库不设性能硬门）。

用法：
    python3 tools/perf-batch-check.py tmp/perf/20261026-214202
    python3 tools/perf-batch-check.py --latest
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / "tmp" / "perf"
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}(-\d+)?$")


def latest_run() -> Path:
    """按 run-id 排序取最新一目录（run-id 本身可按字典序比较）。"""
    candidates = [p for p in WORK_ROOT.iterdir()
                  if p.is_dir() and RUN_ID_RE.match(p.name)]
    if not candidates:
        raise SystemExit(f"{WORK_ROOT} 下没有批次目录")
    return sorted(candidates)[-1]


def main() -> int:
    """读取 raw.json/product.json，打印结论并按有效性返回退出码。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("run", nargs="?", help="批次目录（缺省配合 --latest）")
    parser.add_argument("--latest", action="store_true", help="取最新一批")
    args = parser.parse_args()
    if args.latest or not args.run:
        run_dir = latest_run()
    else:
        run_dir = Path(args.run)
        if not run_dir.is_absolute():
            run_dir = ROOT / run_dir
    raw_path = run_dir / "raw.json"
    if not raw_path.is_file():
        print(f"缺少 raw.json：{raw_path}", file=sys.stderr)
        return 2
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    validity = raw.get("validity", {})
    status = validity.get("status")
    reasons = validity.get("reasons") or []
    high_load = validity.get("high_load") or []
    problems = []
    warnings = []
    product_path = run_dir / "product.json"
    if product_path.is_file():
        problems = json.loads(product_path.read_text(encoding="utf-8")).get(
            "problems") or []
    else:
        # 本地小批次不一定测产物；CI 的 perf workflow 会先跑 perf-product，
        # 那一步失败就直接让 job 变红，所以这里只提醒。
        warnings.append("缺少 product.json（本批未测产物质量）")
    print(f"batch={run_dir.name} validity={status} "
          f"corpus={raw.get('corpus_version')} compiler={raw.get('compiler_a', {}).get('sha256', '')[:16]}…")
    for item in reasons:
        print(f"  无效原因：{item}")
    for item in high_load:
        print(f"  负载提醒：{item}")
    for item in warnings:
        print(f"  提醒：{item}")
    for item in problems:
        print(f"  产物问题：{item}")
    ok = status == "ok" and not problems
    print("结论：" + ("批次可用（性能回退需另行判定，本仓库不设硬门）" if ok
                     else "批次无效，不得据此下结论"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
