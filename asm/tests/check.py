#!/usr/bin/env python3
"""check.py —— yh_asm（asm/ 汇编器项目）验收门。

1. 用指定编译器冷编 asm/ 项目，产出 .build/yh_asm；
2. 运行 yh_asm 自检（公共层 + 编码向量 + 端到端 + GNU 方言端到端 + 拒绝层），
   退出码即门；
3. --full 追加：拒绝路径门（check_neg.py）、编码差分（check_enc.py）、
   定向与 GNU 方言语料差分（check_corpus.py，含给定的程序级语料）、
   ELF 结构与确定性（check_obj.py）、Darwin 字节快照（ASM-8）；
4. 给定语料目录时再跑链接运行门：Linux 宿主用交叉 ld + qemu
   （elf_link_native.py，不需要 docker），其他宿主用容器门
   （elf_link_check.py）。

oracle 由 check_corpus.oracle_kind 解析：`LLVM_MC` 环境变量 → Homebrew 默认
路径 → clang 集成汇编器，因此只有 clang 的宿主（例如 WSL）也能跑完整差分。

用法：
    python3 tests/check.py                          # 构建 + 自检
    python3 tests/check.py --full                   # 再加差分/拒绝路径/快照门
    python3 tests/check.py --full ../tmp/inv        # 指定程序级语料
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

    # 3) 差分门与拒绝路径门。oracle 由 check_corpus.oracle_kind 解析
    #    （LLVM_MC 环境变量 → Homebrew 默认 → clang 集成汇编器），所以
    #    只有 clang 的宿主（WSL）也能跑完整差分。
    gates = [
        ("check_neg.py", [product]),                       # 拒绝路径 + 诊断位置
        ("check_enc.py", []),                              # 134 条编码
        ("check_corpus.py", ["tests/asm", "tests/asm-gnu", "--bin", product]),
        ("check_obj.py", [product, "tests/asm"]),          # ELF 结构 + 确定性
        ("check_obj.py", [product, "tests/asm", "--target", "darwin",
                          "--snapshot", "tests/darwin-snapshot.txt"]),
    ]
    # 语料目录给定时追加：它是程序级语料，同时喂对象差分与链接运行门。
    if os.path.isdir(args.corpus):
        gates.append(("check_corpus.py", [args.corpus, "--bin", product]))
    for script, extra in gates:
        r = run([sys.executable, os.path.join(TESTS, script)] + extra, env=env,
                cwd=ASM_DIR)
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        if r.returncode != 0:
            print("%s 失败 rc=%d" % (script, r.returncode), file=sys.stderr)
            return r.returncode

    # 4) 链接运行门：Linux 宿主用交叉 ld + qemu（不需要 docker），
    #    其他宿主用容器门；宿主没有对应工具时明确跳过并说明。
    if os.path.isdir(args.corpus):
        if shutil.which("aarch64-linux-gnu-ld"):
            script, extra = "elf_link_native.py", [args.corpus, "--bin", product]
        else:
            script, extra = "elf_link_check.py", [args.corpus]
        r = run([sys.executable, os.path.join(TESTS, script)] + extra, env=env,
                cwd=ASM_DIR)
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        if r.returncode == 2:
            print("%s 跳过（宿主缺工具，见上面的原因）" % script)
        elif r.returncode != 0:
            print("%s 失败 rc=%d" % (script, r.returncode), file=sys.stderr)
            return r.returncode
    else:
        print("未给定语料目录，跳过链接运行门（%s 不存在）" % args.corpus)

    print("差分门全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
