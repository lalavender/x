#!/usr/bin/env python3
"""tests/modules 模块语法语料校验（MOD-U1）。

遍历 tests/modules/ 下的 .yh 语料，用自举编译器（yh）--syntax-check
验证模块头语法：

    accept/*.yh  必须被接受（退出码 0）
    reject/*.yh  必须被拒绝（退出码非 0）

本 runner 只跑自举产物：module/import 是 ADR-0006 之后的新语法，
stage0 种子（src/ 冻结）不识别，因此不进 tests/yh 的 stage0 语料。
纯语法检查不解析 project.toml、不搜索依赖：未知模块不是语法错误。

用法：
    python3 tests/modules/check.py
    python3 tests/modules/check.py --compiler-path ./yh
    python3 tests/modules/check.py --jobs 1       # 串行（缺省 min(8, CPU 核数)）
    python3 tests/modules/check.py --quiet

退出码：全部通过 0；有失败 1。
"""

import argparse
import concurrent.futures
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # tests/modules
ROOT = HERE.parent.parent                        # 仓库根

# 并发语料数缺省上限：每个文件一次编译器进程，上限 8 兼顾核数不多的机器。
DEFAULT_JOBS = max(1, min(8, os.cpu_count() or 1))


def run_batch(compiler: Path, subdir: str, expect_ok: bool, quiet: bool,
              jobs: int, compiler_flags: list[str]) -> int:
    """跑一个目录的语料，返回失败数。expect_ok=True 期望接受，否则期望拒绝。"""
    files = sorted((HERE / subdir).glob("*.yh"))
    if not files:
        print(f"modules/{subdir}: 无语料（缺用例）")
        return 1

    def run_one(path: Path):
        """跑一个语料，返回 (路径, 退出码, 是否被接受, 诊断文本)。"""
        proc = subprocess.run(
            [str(compiler), *compiler_flags, "--syntax-check", str(path)],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
        return path, proc.returncode, proc.returncode == 0, \
            (proc.stdout.strip(), proc.stderr.strip())

    if jobs > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            outcomes = list(pool.map(run_one, files))
    else:
        outcomes = [run_one(path) for path in files]

    failed = 0
    for path, code, accepted, (stdout, stderr) in outcomes:
        if accepted != expect_ok:
            failed += 1
            verb = "接受" if expect_ok else "拒绝"
            print(f"FAIL {subdir}/{path.name}: 应被{verb}，退出码 {code}")
            if stdout:
                print(stdout)
            if stderr:
                print(stderr)
        elif not quiet:
            verdict = "接受" if expect_ok else "拒绝"
            print(f"OK   {subdir}/{path.name}（{verdict}）")
    return failed


def main() -> int:
    ap = argparse.ArgumentParser(description="yh 模块语法语料校验")
    ap.add_argument("--compiler-path", default=str(ROOT / "yh"),
                    help="自举编译器路径（默认 ./yh）")
    ap.add_argument("--quiet", action="store_true", help="只打印失败项")
    ap.add_argument("--backend", choices=("llvm",),
                    help="显式选择编译后端（LLVM 是唯一后端）")
    ap.add_argument("--target", help="显式选择输出目标 triple")
    ap.add_argument("--opt-level", choices=("0", "2"),
                    help="显式选择 LLVM 优化级别")
    ap.add_argument("--jobs", type=int, default=DEFAULT_JOBS,
                    help=f"并发语料数（缺省 {DEFAULT_JOBS}；1 为串行）")
    args = ap.parse_args()

    compiler = Path(args.compiler_path).resolve()
    if not compiler.exists():
        print(f"编译器不存在: {compiler}")
        return 1

    jobs = max(1, args.jobs)
    compiler_flags = []
    if args.backend:
        compiler_flags += ["--backend", args.backend]
    if args.target:
        compiler_flags += ["--target", args.target]
    if args.opt_level:
        compiler_flags += [f"-O{args.opt_level}"]
    failed = run_batch(compiler, "accept", True, args.quiet, jobs,
                       compiler_flags)
    failed += run_batch(compiler, "reject", False, args.quiet, jobs,
                        compiler_flags)

    total_ok = len(list((HERE / "accept").glob("*.yh"))
                   + list((HERE / "reject").glob("*.yh")))
    print(f"modules: 通过 {total_ok - failed}/{total_ok}（并发 {jobs}）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
