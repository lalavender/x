#!/usr/bin/env python3
"""失效矩阵：多模块工程上验证「改什么 → 重做什么」，并与清缓存构建逐字节对照。

对齐 docs/02-plan/yh-编译器性能测试方案-2026-10-23.md 的 PF2「接口/编译期失效矩阵」：

| 场景 | 期望 |
| --- | --- |
| 仅注释 | 函数级 IR/check 全命中；产物与清缓存构建一致 |
| 私有函数体 | 只有该函数 miss；其余命中；结果与清缓存一致 |
| 公有接口 | 消费者重新检查（check miss > 0）；结果与清缓存一致 |
| 编译期常量 | 依赖模块重新求值；结果与清缓存一致 |
| 缺对象 | 该模块重新发射；结果与清缓存一致 |
| 缺函数缓存 | 该模块回退为完整重编，不能当命中；结果一致 |

工程在 tmp/perf/invalidation-<run-id>/ 下现生成（三个模块：leaf←mid←main）。
判定依据是编译器 `--stats` 的计数与**产物对象/程序输出**比对，不依赖 PATH 包装器。

用法：
    python3 tools/perf-invalidation.py                # 跑全部场景
    python3 tools/perf-invalidation.py --scenario comment
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# --stats 已从 CLI 移除（2026-11-10）：统计输出改由 YH_STATS=1 开启。
os.environ.setdefault("YH_STATS", "1")

ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / "tmp" / "perf"

FIXTURE = {
    "project.toml": """[project]
os = "host"
arch = "host"
name = "perfinval"
source = "src"
""",
    "src/leaf/leaf.yh": """module leaf;

pub const SCALE int = 3;

pub fn base(x int) int {
    return x + 1;
}

fn hidden(x int) int {
    return x + 2;
}

pub fn pub_use(x int) int {
    return hidden(x);
}
""",
    "src/mid/mid.yh": """module mid;

import leaf;

pub fn compute(x int) int {
    return leaf.pub_use(x) * leaf.SCALE;
}
""",
    "src/main/main.yh": """module main;

import mid;

fn main() int {
    printf("%d\\n", mid.compute(1));
    return 0;
}
""",
}

COUNTERS = ("checked_functions", "backend_emitted_functions", "ir_cache_hits",
            "ir_cache_misses", "check_cache_hits", "check_cache_misses")


def write_fixture(root: Path, edits: list[tuple[str, str, str]] | None = None) -> None:
    """写工程到 root，并按 (相对路径, 原文, 替换) 依次打补丁。"""
    if root.exists():
        shutil.rmtree(root)
    for rel, text in FIXTURE.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for rel, old, new in edits or []:
        path = root / rel
        body = path.read_text(encoding="utf-8")
        if old not in body:
            raise SystemExit(f"补丁锚点不存在：{rel} :: {old[:40]}")
        path.write_text(body.replace(old, new, 1), encoding="utf-8")


def stats_of(output: str) -> dict:
    """把本次构建所有 yh-stats 行的计数相加（父进程 + 各 worker）。"""
    totals = {key: 0 for key in COUNTERS}
    totals["lines"] = 0
    for line in output.splitlines():
        if not line.startswith("yh-stats "):
            continue
        totals["lines"] += 1
        row = dict(item.split("=", 1) for item in line.split()[1:] if "=" in item)
        for key in COUNTERS:
            totals[key] += int(row.get(key, 0))
    return totals


def objects_of(project: Path) -> dict[str, str]:
    """每个模块对象的 内容 SHA-256（相对路径 → 摘要），用于跨构建比对。"""
    result = {}
    for path in sorted(project.glob(".build/targets/*/llvm/*/obj/*.o")):
        result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def build(project: Path, compiler: Path, timeout: int) -> tuple[dict, dict, str]:
    """构建一次，返回 (计数汇总, 对象摘要, 程序输出)。"""
    proc = subprocess.run([str(compiler), "build"], cwd=project,
                          capture_output=True, text=True, timeout=timeout)
    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        return {"error": f"构建失败 rc={proc.returncode}"}, {}, output[-800:]
    binary = project / ".build" / "perfinval"
    ran = subprocess.run([str(binary)], cwd=project, capture_output=True, text=True)
    return stats_of(output), objects_of(project), ran.stdout.strip()


def prime(project: Path, compiler: Path, timeout: int) -> tuple[dict, dict, str]:
    """强制一次真实重编，把函数级 IR/check 缓存写出来。

    PC3 之后冷编不写函数缓存；而「无改动再编一次」根本不会启动 worker，
    同样写不出缓存。只有删掉 manifest 与对象逼出 worker 才会落盘，
    这与 tests/selfhost/cache/llvm-function-cache.py 的 priming 方式一致。
    """
    # 只删对象：**不能**删 manifest 目录下的 link.manifest，它是「本轮可写函数
    # 缓存」的开关（见 build_scheduler 的 c_firc_write_off），删了会让 priming
    # 变成冷编而不写任何 .fir，后续 “0 命中” 就成了假象。
    for path in project.glob(".build/targets/*/llvm/*/obj/*.o"):
        path.unlink()
    return build(project, compiler, timeout)


def scenario(name: str, edits, expect, work: Path, compiler: Path,
             timeout: int) -> dict:
    """一个场景：基线构建 → 打补丁 → 增量构建 → 与清缓存构建对照。"""
    project = work / name
    write_fixture(project)
    # 先冷编，再强制一次重编把函数级缓存落到磁盘（PC3 冷编不写、无改动不启 worker）。
    build(project, compiler, timeout)
    base_stats, base_objects, base_output = prime(project, compiler, timeout)
    if "error" in base_stats:
        return {"scenario": name, "ok": False, "error": base_stats["error"]}
    # 在已就绪的工程上打补丁，随后做增量构建。
    for rel, old, new in edits:
        path = project / rel
        body = path.read_text(encoding="utf-8")
        if old not in body:
            return {"scenario": name, "ok": False, "error": f"补丁锚点不存在：{rel}"}
        path.write_text(body.replace(old, new, 1), encoding="utf-8")
    stats, objects, output = build(project, compiler, timeout)
    if "error" in stats:
        return {"scenario": name, "ok": False, "error": stats["error"]}

    # 清缓存对照：同一份最终源码在独立目录里冷编。
    clean = work / f"{name}-clean"
    write_fixture(clean, edits)
    clean_stats, clean_objects, clean_output = build(clean, compiler, timeout)
    if "error" in clean_stats:
        return {"scenario": name, "ok": False, "error": clean_stats["error"]}

    checks = {
        "output_matches_expected": output == expect,
        "output_matches_clean": output == clean_output,
        "objects_match_clean": objects == clean_objects,
    }
    return {"scenario": name, "ok": all(checks.values()), "checks": checks,
            "stats": stats, "clean_stats": clean_stats,
            "output": output, "expected_output": expect,
            "base_output": base_output,
            "object_count": len(objects),
            "object_diff": sorted(set(clean_objects) - set(objects))
            + sorted(set(objects) - set(clean_objects))}


def main() -> int:
    """跑失效矩阵并写 JSON/Markdown 报告。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(ROOT / "yh"))
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--scenario", help="只跑一个场景（comment/private/iface/comptime/object/firc）")
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve()
    if not compiler.is_file():
        print(f"编译器不存在：{compiler}", file=sys.stderr)
        return 2
    run_id = time.strftime("%Y%m%d-%H%M%S")
    work = WORK_ROOT / f"invalidation-{run_id}"
    work.mkdir(parents=True, exist_ok=True)

    leaf = "src/leaf/leaf.yh"
    cases = {
        # 仅注释：函数级缓存应全命中，产物不变。
        "comment": ([("src/leaf/leaf.yh",
                      "pub fn base(x int) int {",
                      "// 仅注释变化，不进入 token 流\npub fn base(x int) int {")],
                    "9"),
        # 私有函数体：只有 hidden 失效，pub_use 仍命中，结果 6×3=18。
        "private": ([(leaf, "return x + 2;", "return x + 5;")], "18"),
        # 公有接口：base 签名变化，消费者必须重新检查（结果不变，9）。
        "iface": ([(leaf,
                    "pub fn base(x int) int {\n    return x + 1;\n}",
                    "pub fn base(x int, y int) int {\n    return x + y + 1;\n}")], "9"),
        # 编译期常量：依赖模块重新求值，结果 3×4=12。
        "comptime": ([(leaf, "pub const SCALE int = 3;",
                      "pub const SCALE int = 4;")], "12"),
    }
    results = []
    for name, (edits, expect) in cases.items():
        if args.scenario and args.scenario not in (name, {"object": "object",
                                                          "firc": "firc"}.get(name)):
            continue
        results.append(scenario(name, edits, expect, work, compiler, args.timeout))
        print(f"{name}: {'ok' if results[-1]['ok'] else 'FAIL'}")

    # 缺产物：删掉 leaf 的对象 / 函数缓存后重编，必须恢复且与清缓存一致。
    for name, pattern in (("object", ".build/targets/*/llvm/*/obj/*-leaf.o"),
                          ("firc", ".build/targets/*/llvm/O*/firc/*-leaf")):
        if args.scenario and args.scenario != name:
            continue
        project = work / name
        write_fixture(project)
        build(project, compiler, args.timeout)
        prime(project, compiler, args.timeout)
        removed = list(project.glob(pattern))
        for path in removed:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
        if name == "firc":
            # 删除缓存目录本身不会触发重编（manifest 与对象都还在），必须再删
            # leaf 的对象才能观测「缓存缺失时是否回退为完整重编」。
            for path in project.glob(".build/targets/*/llvm/*/obj/*-leaf.o"):
                path.unlink()
                removed.append(path)
        stats, objects, output = build(project, compiler, args.timeout)
        clean = work / f"{name}-clean"
        write_fixture(clean)
        _, clean_objects, clean_output = build(clean, compiler, args.timeout)
        checks = {"removed_something": bool(removed),
                  "output_matches_expected": output == "9",
                  "objects_match_clean": objects == clean_objects,
                  "rebuilt_something": stats.get("backend_emitted_functions", 0) > 0}
        # 缺对象：应当复用函数缓存重编；缺函数缓存：必须老实 miss 重编，
        # 不能把「缺产物的成功退出」当成命中。
        if name == "object":
            checks["cache_reused"] = stats.get("ir_cache_hits", 0) > 0
        else:
            checks["no_false_hit"] = stats.get("ir_cache_hits", 0) == 0
            checks["recompiled_functions"] = stats.get("ir_cache_misses", 0) >= 3
        results.append({"scenario": name, "ok": all(checks.values()),
                        "checks": checks, "stats": stats,
                        "removed": [str(p.name) for p in removed],
                        "output": output})
        print(f"{name}: {'ok' if results[-1]['ok'] else 'FAIL'}")

    report = {"run_id": run_id, "target": f"{platform.system()}/{platform.machine()}",
              "host": platform.platform(),
              "compiler": {"path": str(compiler),
                           "sha256": hashlib.sha256(compiler.read_bytes()).hexdigest()},
              "results": results}
    (work / "matrix.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [f"# 失效矩阵 {run_id}", "",
             f"- 编译器：`{report['compiler']['path']}` "
             f"`{report['compiler']['sha256'][:16]}…`（{report['target']}）", "",
             "| 场景 | 结果 | 输出 | 期望 | IR 命中/未命中 | check 命中/未命中 | "
             "重编函数 | 对象与清缓存一致 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in results:
        stats = row.get("stats", {})
        checks = row.get("checks", {})
        lines.append(
            f"| {row['scenario']} | {'通过' if row['ok'] else '失败'} | "
            f"{row.get('output')} | {row.get('expected_output', '-')} | "
            f"{stats.get('ir_cache_hits')}/{stats.get('ir_cache_misses')} | "
            f"{stats.get('check_cache_hits')}/{stats.get('check_cache_misses')} | "
            f"{stats.get('backend_emitted_functions')} | "
            f"{checks.get('objects_match_clean')} |")
    failed = [row for row in results if not row["ok"]]
    if failed:
        lines += ["", "## 失败详情", ""]
        for row in failed:
            lines.append(f"- {row['scenario']}: {row.get('error') or row.get('checks')}")
    (work / "matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[3:]))
    print(f"\n报告：{work / 'matrix.md'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
