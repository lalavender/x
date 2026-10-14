#!/usr/bin/env python3
"""核对真实后端覆盖、拒绝来源及运行结果，不把 SSA 验证数当成发射数。"""

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ("checked_functions", "ir_functions", "backend_emitted_functions",
          "rejected_functions", "backend_rejected_functions", "fallback_functions")


def environment_probe(work: Path) -> dict:
    """记录旧/新工具身份，独立用 clang oracle 验证 x64 ELF 与原生链接运行。"""
    tools = {}
    for name in ("clang-21", "gcc", "aarch64-linux-gnu-gcc", "qemu-aarch64"):
        path = Path("/usr/bin") / name
        version = subprocess.run([str(path), "--version"], check=True,
                                 capture_output=True, text=True, timeout=10)
        tools[name] = {"path": str(path), "version": version.stdout.splitlines()[0],
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    assert "21.1.8" in tools["clang-21"]["version"]
    ir = work / "native-probe.ll"
    ir.write_text("define i32 @main() { ret i32 0 }\n", encoding="utf-8")
    obj, executable = work / "native-probe.o", work / "native-probe"
    subprocess.run(["/usr/bin/clang-21", "-x", "ir", "-c", "--target=x86_64-unknown-linux-gnu",
                    str(ir), "-o", str(obj)], check=True, capture_output=True, timeout=30)
    subprocess.run(["/usr/bin/gcc", "-no-pie", str(obj), "-o", str(executable)],
                   check=True, capture_output=True, timeout=30)
    data = executable.read_bytes()
    assert data[:5] == b"\x7fELF\x02" and int.from_bytes(data[18:20], "little") == 62
    subprocess.run([str(executable)], check=True, timeout=15)
    source_hash = hashlib.sha256()
    for path in sorted((ROOT / "compiler").rglob("*.yh")):
        source_hash.update(str(path.relative_to(ROOT)).encode())
        source_hash.update(path.read_bytes().replace(b"\r\n", b"\n"))
    cpuinfo = Path("/proc/cpuinfo").read_text()
    cpu = next(line.split(":", 1)[1].strip() for line in cpuinfo.splitlines()
               if line.startswith("model name"))
    return {"host": platform.platform(), "machine": platform.machine(), "cpu": cpu,
            "tools": tools, "native_probe_machine": 62, "native_probe_exit": 0,
            "seed_sha256": hashlib.sha256((ROOT / "bin/yh-linux-arm64").read_bytes()).hexdigest(),
            "compiler_sources_sha256_lf": source_hash.hexdigest()}


def build_stats(compiler: Path, project: Path) -> tuple[dict, list[str]]:
    """冷编副本并提取各 worker 的覆盖；忽略无函数的父调度进程计数。"""
    shutil.rmtree(project / ".build", ignore_errors=True)
    result = subprocess.run([str(compiler), "build", "--stats"], cwd=project,
                            capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    rows = []
    for line in result.stderr.splitlines():
        if line.startswith("yh-stats "):
            row = dict(item.split("=", 1) for item in line.split()[1:])
            missing = set(FIELDS) - row.keys()
            assert not missing, f"未实现真实覆盖计数：{sorted(missing)}"
            counts = {name: int(row[name]) for name in FIELDS}
            assert counts["checked_functions"] == (counts["ir_functions"]
                                                   + counts["rejected_functions"])
            assert counts["backend_emitted_functions"] <= counts["ir_functions"]
            assert counts["ir_functions"] == (counts["backend_emitted_functions"]
                                              + counts["backend_rejected_functions"])
            assert counts["fallback_functions"] == (counts["rejected_functions"]
                                                     + counts["backend_rejected_functions"])
            rows.append(counts)
    assert rows, "没有输出 yh-stats"
    totals = {name: sum(row[name] for row in rows) for name in FIELDS}
    rejects = sorted(line for line in result.stderr.splitlines()
                     if line.startswith("yh-reject "))
    assert len(rejects) == totals["fallback_functions"], "拒绝来源数与回退数不同"
    return totals, rejects


def main() -> int:
    """验收最小覆盖 fixture，按需重测真实 compiler/，结果保存在 tmp。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    work = ROOT / "tmp/llvm-migration/baseline"
    work.mkdir(parents=True, exist_ok=True)
    fixture = work / "fixture"
    shutil.copytree(ROOT / "tests/modules/projects/llvmcoverage", fixture,
                    dirs_exist_ok=True, ignore=shutil.ignore_patterns(".build"))
    totals, rejects = build_stats(compiler, fixture)
    assert totals["checked_functions"] == 3, totals
    assert totals["backend_emitted_functions"] >= 1, totals
    assert any("function=mutate " in line and "reason=" in line for line in rejects)
    executable = fixture / ".build/llvmcoverage"
    subprocess.run([str(executable)], check=True, timeout=15)
    report = {"schema": 1, "compiler_sha256": hashlib.sha256(compiler.read_bytes()).hexdigest(),
              "fixture": totals, "fixture_rejections": rejects}
    if args.full:
        report["environment"] = environment_probe(work)
        project = work / "compiler"
        shutil.copytree(ROOT / "compiler", project, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".build", "llvm"))
        report["compiler"], report["compiler_rejections"] = build_stats(compiler, project)
        # R0 语料早于字段 pub 删除，不能用它宣称当前编译器的冷编性能。
        # 当前语料另行冻结到 tmp，规范化 LF 并保存完整内容清单供迁移后复测。
        corpus = work / "performance-corpus"
        corpus.mkdir(exist_ok=True)
        snapshot = corpus / "compiler"
        shutil.rmtree(snapshot, ignore_errors=True)
        shutil.copytree(ROOT / "compiler", snapshot,
                        ignore=shutil.ignore_patterns(".build", "llvm"))
        entries = []
        for path in sorted([snapshot / "project.toml", *snapshot.rglob("*.yh")]):
            data = path.read_bytes().replace(b"\r\n", b"\n")
            path.write_bytes(data)
            entries.append(f"{hashlib.sha256(data).hexdigest()}  {path.relative_to(corpus)}")
        (corpus / "SHA256SUMS").write_text("\n".join(entries) + "\n", encoding="utf-8")
        report["performance_corpus"] = str(corpus)
    (work / "coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)
                                       + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items()
                      if not key.endswith("rejections")}, ensure_ascii=False))
    print("LLVM 基线覆盖门通过（当前是旧 ARM64 后端，不代表 LLVM 发射）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
