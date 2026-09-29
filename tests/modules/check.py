#!/usr/bin/env python3
"""tests/modules 模块语法语料校验（MOD-U1）。

遍历 tests/modules/ 下的 .yh 语料，用自举编译器（yh-new）--syntax-check
验证模块头语法：

    accept/*.yh  必须被接受（退出码 0）
    reject/*.yh  必须被拒绝（退出码非 0）

本 runner 只跑自举产物：module/import 是 ADR-0006 之后的新语法，
stage0 种子（src/ 冻结）不识别，因此不进 tests/yh 的 stage0 语料。
纯语法检查不解析 mod.toml、不搜索依赖：未知模块不是语法错误。

用法：
    python3 tests/modules/check.py
    python3 tests/modules/check.py --compiler-path ./yh-new
    python3 tests/modules/check.py --quiet

退出码：全部通过 0；有失败 1。
"""

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # tests/modules
ROOT = HERE.parent.parent                        # 仓库根


def run_batch(compiler: Path, subdir: str, expect_ok: bool, quiet: bool) -> int:
    """跑一个目录的语料，返回失败数。expect_ok=True 期望接受，否则期望拒绝。"""
    files = sorted((HERE / subdir).glob("*.yh"))
    if not files:
        print(f"modules/{subdir}: 无语料（缺用例）")
        return 1
    failed = 0
    for f in files:
        proc = subprocess.run(
            [str(compiler), "--syntax-check", str(f)],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
        ok = (proc.returncode == 0)
        if ok != expect_ok:
            failed += 1
            verb = "接受" if expect_ok else "拒绝"
            print(f"FAIL {subdir}/{f.name}: 应被{verb}，退出码 {proc.returncode}")
            if proc.stdout.strip():
                print(proc.stdout.strip())
            if proc.stderr.strip():
                print(proc.stderr.strip())
        elif not quiet:
            verdict = "接受" if expect_ok else "拒绝"
            print(f"OK   {subdir}/{f.name}（{verdict}）")
    return failed


def main() -> int:
    ap = argparse.ArgumentParser(description="yh 模块语法语料校验")
    ap.add_argument("--compiler-path", default=str(ROOT / "yh-new"),
                    help="自举编译器路径（默认 ./yh-new）")
    ap.add_argument("--quiet", action="store_true", help="只打印失败项")
    args = ap.parse_args()

    compiler = Path(args.compiler_path).resolve()
    if not compiler.exists():
        print(f"编译器不存在: {compiler}")
        return 1

    failed = run_batch(compiler, "accept", True, args.quiet)
    failed += run_batch(compiler, "reject", False, args.quiet)

    total_ok = len(list((HERE / "accept").glob("*.yh"))
                   + list((HERE / "reject").glob("*.yh")))
    print(f"modules: 通过 {total_ok - failed}/{total_ok}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
