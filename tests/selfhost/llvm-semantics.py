#!/usr/bin/env python3
"""以同一批真实 .yh 探针对照单文件与项目 SSA，记录实际发射和失败诊断。"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    """从运行语料建独立项目，保留编译/运行证据；不能用旧发射成功冒充 SSA 覆盖。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--filter", default="llvm-")
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    work = ROOT / "tmp/llvm-migration/semantics-projects"
    work.mkdir(parents=True, exist_ok=True)
    sources = sorted((ROOT / "tests/yh-run/run").glob(f"*{args.filter}*.yh"))
    assert sources, f"没有语义探针：{args.filter}"
    records = []
    for source in sources:
        project = work / source.stem
        shutil.rmtree(project, ignore_errors=True)
        (project / "main").mkdir(parents=True)
        text = source.read_text(encoding="utf-8")
        (project / "main/main.yh").write_text("module main;\n" + text, encoding="utf-8")
        (project / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "probe"\nversion = "0.0.1"\nsource = "."\n', encoding="utf-8")
        compiled = subprocess.run([str(compiler), "build", "--stats"], cwd=project,
                                  capture_output=True, text=True, timeout=120)
        (project / "compile.log").write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
        assert compiled.returncode == 0, f"{source.name}: {compiled.stderr}"
        result = subprocess.run([str(project / ".build/probe")], capture_output=True,
                                text=True, timeout=20)
        expected = [line.split(":", 1)[1].lstrip() for line in text.splitlines()
                    if line.startswith(("// expect:", "// expect-more:"))]
        assert result.returncode == 0, f"{source.name} 项目路径退出 {result.returncode}: {result.stderr}"
        assert result.stdout.splitlines() == expected, f"{source.name}: {result.stdout!r} != {expected}"
        stats = [dict(item.split("=", 1) for item in line.split()[1:])
                 for line in compiled.stderr.splitlines() if line.startswith("yh-stats ")]
        emitted = sum(int(row["backend_emitted_functions"]) for row in stats)
        if "bool-memory" in source.name:
            assert emitted >= 8, f"bool 探针没有实际发射八种 SSA 函数：{stats}"
        if "call-block-order" in source.name:
            assert emitted >= 2, f"调用/合流探针没有实际发射两个 SSA 函数：{stats}"
        if "integer-boundaries" in source.name:
            assert emitted >= 11, f"整数探针没有实际发射十一种 SSA 函数：{stats}"
        if "unary-types" in source.name:
            assert emitted >= 1, f"一元逻辑非没有实际发射 SSA 函数：{stats}"
        records.append({"source": source.name, "stdout": result.stdout,
                        "exit_code": result.returncode, "backend_emitted_functions": emitted})
    (work / "report.json").write_text(json.dumps(records, ensure_ascii=False, indent=2)
                                       + "\n", encoding="utf-8")
    print(f"语义项目门通过：{len(records)} 个探针，实际发射计数已记录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
