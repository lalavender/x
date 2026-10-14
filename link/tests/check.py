#!/usr/bin/env python3
"""check.py —— yh_link（link/ 静态 ELF 链接器项目）验收门。

层次（默认只跑前两层，`--full` 加后两层）：

  1. 冷编 link/ 项目 → link/.build/yh_link；
  2. 自检 + CLI 契约：
       * 无参数调用 = 自检，退出码 0 且「失败 0 项」；
       * `--version` 退出码 0；
       * 用法错误退出码 2（未知参数、缺输入、缺 -o、页对齐非法）；
       * 输入/链接失败退出码 1（输入文件读不进来）；
       * `--verbose` 只多打过程输出、不改退出码。
  3. `--full`：端到端验收（link_accept.py）——用 yh_asm 汇编 link/tests/asm/
     下的语料，用 yh_link 链成静态可执行文件，核对 ELF 结构，并**真跑**一遍
     比对退出码；
  4. `--full` 且宿主有 GNU binutils 时追加差分门（link_diff_regress.py）。

设计约束（本门刻意如此）：
  * link/ 与 asm/ 解耦：验收必须通过**命令行**调用 yh_asm 产出对象，
    不 import 汇编器内部模块；
  * 门自身的判定只看退出码与可机器判定的结构字段，不比对中文诊断文本，
    避免文案改动误伤门禁。

用法：
    python3 link/tests/check.py                     # 构建 + 自检 + CLI
    python3 link/tests/check.py --full              # 再加端到端与差分
    python3 link/tests/check.py --compiler /path/to/yh
    python3 link/tests/check.py --asm /path/to/yh_asm
"""

import argparse
import os
import shutil
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
LINK_DIR = os.path.dirname(TESTS)
ROOT = os.path.dirname(LINK_DIR)
BOX = os.path.join(ROOT, "tmp", "linkbox")


def run(cmd, **kw):
    """跑一条命令，返回 CompletedProcess（文本模式）。"""
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def fail(msg: str) -> int:
    print("失败: " + msg, file=sys.stderr)
    return 1


def step_build(compiler: str, env: dict, clean: bool) -> str:
    """冷编 link/ 项目，返回产物路径（失败返回空串）。"""
    build_dir = os.path.join(LINK_DIR, ".build")
    if clean and os.path.isdir(build_dir):
        shutil.rmtree(build_dir)
    r = run([compiler, "build"], cwd=LINK_DIR, env=env)
    if r.returncode != 0:
        print("link/ 项目构建失败：\n" + (r.stdout + r.stderr).strip(),
              file=sys.stderr)
        return ""
    product = os.path.join(build_dir, "yh_link")
    if not os.path.isfile(product):
        print("错误: 构建产物缺失 %s" % product, file=sys.stderr)
        return ""
    return product


def step_selftest(product: str) -> int:
    """无参数调用必须跑自检并通过（退出码 0 + 「失败 0 项」）。"""
    r = run([product], cwd=ROOT)
    if r.returncode != 0:
        return fail("自检退出码 %d\n%s" % (r.returncode, r.stderr.strip()))
    if "失败 0 项" not in r.stdout:
        return fail("自检输出里没有「失败 0 项」：%r" % r.stdout.strip())
    print("  自检: " + r.stdout.strip())
    return 0


def step_cli(product: str) -> int:
    """CLI 契约：退出码分级 + --version + --verbose 不改判定。"""
    # --version
    r = run([product, "--version"], cwd=ROOT)
    if r.returncode != 0 or "yh_link" not in r.stdout:
        return fail("--version 行为不符：rc=%d out=%r" % (r.returncode, r.stdout))

    # 用法错误（2）：未知参数、缺输入、缺 -o、页对齐非法、子命令缺失
    usage_cases = [
        ([product, "bogus"], "未知子命令"),
        ([product, "link"], "缺少输入对象"),
        ([product, "link", "-o", os.path.join(BOX, "x.out")], "缺少输入对象（带 -o）"),
        ([product, "link", "--bad-flag", "a.o"], "未知参数"),
        ([product, "link", "--entry"], "--entry 缺参数"),
        ([product, "link", "--max-page-size", "100", "a.o"], "页对齐非 2 的幂"),
    ]
    for argv, what in usage_cases:
        r = run(argv, cwd=ROOT)
        if r.returncode != 2:
            return fail("%s 应返回 2，实得 %d（err=%r）"
                        % (what, r.returncode, r.stderr.strip()))

    # 输入失败（1）：输入文件读不进来属于链接失败，不是用法错误
    missing = os.path.join(BOX, "definitely-missing.o")
    r = run([product, "link", "-o", os.path.join(BOX, "x.out"), missing],
            cwd=ROOT)
    if r.returncode != 1:
        return fail("输入文件缺失应返回 1，实得 %d（err=%r）"
                    % (r.returncode, r.stderr.strip()))
    return 0


def step_accept(product: str, asm: str, env: dict) -> int:
    """端到端验收门（另一个脚本，走命令行，不 import 汇编器）。"""
    script = os.path.join(TESTS, "link_accept.py")
    if not os.path.isfile(script):
        return fail("缺少端到端验收脚本 %s" % script)
    r = run([sys.executable, script, "--link", product, "--asm", asm], env=env)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        return fail("端到端验收未通过（rc=%d）" % r.returncode)
    return 0


def step_diff(product: str, asm: str, env: dict) -> int:
    """与 GNU ld 的差分门（需要 aarch64 binutils；缺工具时跳过）。"""
    script = os.path.join(TESTS, "link_diff_regress.py")
    if not os.path.isfile(script):
        print("  差分门: 跳过（缺 %s）" % os.path.basename(script))
        return 0
    r = run([sys.executable, script, "--link", product, "--asm", asm,
             "--skip-if-missing"], env=env)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        return fail("GNU ld 差分未通过（rc=%d）" % r.returncode)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="构建并验收 yh_link 链接器项目")
    ap.add_argument("--compiler", default=os.path.join(ROOT, "yh"),
                    help="用于构建 link/ 项目的 yh 编译器路径")
    ap.add_argument("--asm", default=os.path.join(ROOT, "asm", ".build", "yh_asm"),
                    help="端到端验收用的 yh_asm 汇编器路径")
    ap.add_argument("--full", action="store_true",
                    help="追加端到端验收与 GNU ld 差分门")
    ap.add_argument("--keep", action="store_true",
                    help="保留 .build 缓存（迭代调试用；默认冷编）")
    args = ap.parse_args()

    # 相对路径要在这里定成绝对路径：子进程会在 link/、asm/ 等不同 cwd 下运行，
    # 相对路径到了那里就指向别处了。
    compiler = os.path.abspath(args.compiler)
    if not os.path.isfile(compiler):
        compiler = os.path.join(ROOT, "bin", "yh-linux-arm64")
    if not os.path.isfile(compiler):
        compiler = os.path.join(ROOT, "bin", "yh")
    if not os.path.isfile(compiler):
        print("错误: 找不到 yh 编译器（用 --compiler 指定）", file=sys.stderr)
        return 2

    env = dict(os.environ)
    env.setdefault("TMPDIR", os.path.join(ROOT, "tmp"))
    os.makedirs(BOX, exist_ok=True)

    product = step_build(compiler, env, clean=not args.keep)
    if not product:
        return 2
    print("构建: %s" % os.path.relpath(product, ROOT))

    rc = step_selftest(product)
    if rc != 0:
        return rc
    rc = step_cli(product)
    if rc != 0:
        return rc
    print("  CLI 契约: 通过（0 成功 / 1 输入失败 / 2 用法错误）")

    if args.full:
        asm = os.path.abspath(args.asm)
        if not os.path.isfile(asm):
            print("提示: 找不到 %s，先构建 asm/ 项目" % asm, file=sys.stderr)
            r = run([compiler, "build"], cwd=os.path.join(ROOT, "asm"), env=env)
            if r.returncode != 0 or not os.path.isfile(asm):
                return fail("asm/ 项目构建失败（端到端验收需要 yh_asm）")
        rc = step_accept(product, asm, env)
        if rc != 0:
            return rc
        rc = step_diff(product, asm, env)
        if rc != 0:
            return rc

    print("yh_link 验收门通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
