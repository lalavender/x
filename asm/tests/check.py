#!/usr/bin/env python3
"""check.py —— yh_asm（asm/ 汇编器项目）验收门。

1. 用指定编译器冷编 asm/ 项目，产出 .build/yh_asm；
2. 运行 yh_asm 自检（编码向量 + 公共层 + 汇编端到端），退出码即门；
3. --full 时追加 llvm-mc 差分门：check_enc.py、check_corpus.py、check_obj.py
   （需要 /opt/homebrew/opt/llvm/bin/llvm-mc）。

用法：
    python3 tests/check.py                          # 构建 + 自检
    python3 tests/check.py --full                   # 再加编码/语料/结构差分
    python3 tests/check.py --full ../tmp/inv        # 指定语料目录
    python3 tests/check.py --compiler /path/to/yh
"""

import argparse
import os
import shutil
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
ASM_DIR = os.path.dirname(TESTS)
ROOT = os.path.dirname(ASM_DIR)


def run(cmd, **kw):
    """跑一条命令，返回 CompletedProcess（文本模式）。"""
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main() -> int:
    ap = argparse.ArgumentParser(description="构建并测试 yh_asm 汇编器项目")
    ap.add_argument("--compiler", default=os.path.join(ROOT, "yh"),
                    help="用于构建 asm/ 项目的 yh 编译器路径")
    ap.add_argument("--full", action="store_true",
                    help="追加 llvm-mc 差分门（需要 llvm-mc）")
    ap.add_argument("corpus", nargs="?", default=os.path.join(ROOT, "tmp", "inv"),
                    help="--full 的语料目录，默认仓库 tmp/inv")
    args = ap.parse_args()

    compiler = args.compiler
    if not os.path.isfile(compiler):
        compiler = os.path.join(ROOT, "bin", "yh")
    if not os.path.isfile(compiler):
        print("错误: 找不到 yh 编译器（用 --compiler 指定）", file=sys.stderr)
        return 2

    env = dict(os.environ)
    env.setdefault("TMPDIR", os.path.join(ROOT, "tmp"))

    # 1) 冷编 asm/ 项目（清缓存，保证结果可重复）
    build_dir = os.path.join(ASM_DIR, ".build")
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir)
    r = run([compiler, "build"], cwd=ASM_DIR, env=env)
    if r.returncode != 0:
        print("asm/ 项目构建失败：\n" + (r.stdout + r.stderr).strip(),
              file=sys.stderr)
        return 2

    product = os.path.join(build_dir, "yh_asm")
    if not os.path.isfile(product):
        print("错误: 构建产物缺失 %s" % product, file=sys.stderr)
        return 2

    # 2) 自检
    r = run([product], env=env)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    if r.returncode != 0:
        print("yh_asm 自检失败 rc=%d" % r.returncode, file=sys.stderr)
        return r.returncode
    print("yh_asm 自检通过")

    if not args.full:
        return 0

    # 3) llvm-mc 差分门
    for script, extra in (("check_enc.py", []),
                          ("check_corpus.py", [args.corpus, product]),
                          ("check_obj.py", [product, args.corpus])):
        r = run([sys.executable, os.path.join(TESTS, script)] + extra, env=env)
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        if r.returncode != 0:
            print("%s 失败 rc=%d" % (script, r.returncode), file=sys.stderr)
            return r.returncode
    print("差分门全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
