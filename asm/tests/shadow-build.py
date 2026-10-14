#!/usr/bin/env python3
"""影子验收：让编译器**显式**用 yh_asm 顶替逐模块汇编步，冷编一份编译器并跑
两代固定点（ASM-7）。

本轮汇编器**不接入编译器**（见 docs/02-plan/yh-asm汇编器稳定化实施方案.md）：
编译器仍按 `yh_link` 名字发现汇编器，仓库根不再产出该名字。所以这里不碰
compiler/**、不改 make 目标，只用编译器的 `YH_LINK` 显式入口：

    YH_LINK=<汇编器路径>  <种子编译器> build -o <输出>

汇编器的 argv 契约与编译器期望一致（`asm [-t darwin] -o out.o in.s`），因此
无需任何包装适配。为了让「真的用上了」可证，脚本在 tmp/shadow 里生成一个
转发脚本（记录每次调用的耗时与参数），把 YH_LINK 指向它。

验收内容：
  1. 第一代：种子编译器 + 汇编器 → gen1 的编译器；
  2. 第二代：gen1 的编译器 + 汇编器 → gen2 的编译器；
  3. 两代的模块 `.s` 与 `.s.i` 逐字节相同（固定点）；
  4. 汇编调用次数、汇编总耗时、失败数写进 tmp/shadow/report.md。

用法：
    python3 asm/tests/shadow-build.py [--seed bin/yh-linux-arm64]
                                      [--project compiler]
                                      [--out tmp/shadow]
                                      [--assembler asm/.build/yh_asm]
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time

TESTS = os.path.dirname(os.path.abspath(__file__))
ASM_DIR = os.path.dirname(TESTS)
REPO = os.path.dirname(ASM_DIR)


def log(msg):
    print(msg, flush=True)


def copy_sources(src, dst):
    """拷一份项目源码（不带 .build 缓存），两代各自独立构建。"""
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".build"))


def make_wrapper(box, assembler):
    """生成转发脚本并返回其路径：记录每次调用的耗时与参数，再 exec 真身。"""
    tools = os.path.join(box, "tools")
    os.makedirs(tools, exist_ok=True)
    path = os.path.join(tools, "yh_asm")
    calls = os.path.join(box, "calls.log")
    with open(path, "w") as fh:
        fh.write("#!/bin/sh\n"
                 's=$(date +%%s%%N)\n'
                 '"%s" "$@"\n'
                 'rc=$?\n'
                 'e=$(date +%%s%%N)\n'
                 'echo "$((e-s)) $*" >> "%s"\n'
                 'exit $rc\n' % (assembler, calls))
    os.chmod(path, 0o755)
    return path, calls


def build(compiler, project, output, wrapper, env):
    """用给定编译器冷编项目（cwd=项目目录，与 tools/seed-build.py 一致）。"""
    shutil.rmtree(os.path.join(project, ".build"), ignore_errors=True)
    run_env = dict(env)
    run_env["YH_LINK"] = wrapper
    start = time.time()
    r = subprocess.run([compiler, "build", "-o", output], cwd=project,
                       env=run_env, capture_output=True, text=True)
    return r, time.time() - start


def module_artifacts(project):
    """收集模块产物：.build/asm/*.s 与 .build/iface/*.s.i。"""
    out = {}
    for sub, suffix in (("asm", ".s"), ("iface", ".s.i")):
        d = os.path.join(project, ".build", sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(suffix):
                with open(os.path.join(d, f), "rb") as fh:
                    out["%s/%s" % (sub, f)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def read_calls(calls):
    """读转发脚本记录的调用：返回 (次数, 总纳秒)。"""
    n, total = 0, 0
    if not os.path.isfile(calls):
        return (0, 0)
    with open(calls) as fh:
        for line in fh:
            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue
            n += 1
            total += int(parts[0])
    return (n, total)


def main():
    ap = argparse.ArgumentParser(description="用 yh_asm 影子构建编译器并验固定点")
    default_seed = os.path.join(REPO, "bin", "yh-linux-arm64")
    if not os.path.isfile(default_seed):
        default_seed = os.path.join(REPO, "bin", "yh")
    ap.add_argument("--seed", default=default_seed, help="第一代的种子编译器")
    ap.add_argument("--project", default=os.path.join(REPO, "compiler"),
                    help="要构建的项目（默认 compiler）")
    ap.add_argument("--out", default=os.path.join(REPO, "tmp", "shadow"),
                    help="影子构建根目录（默认 tmp/shadow）")
    ap.add_argument("--assembler", default=os.path.join(ASM_DIR, ".build", "yh_asm"),
                    help="被验收的汇编器（默认 asm/.build/yh_asm）")
    args = ap.parse_args()

    seed = os.path.abspath(args.seed)
    project = os.path.abspath(args.project)
    box = os.path.abspath(args.out)
    assembler = os.path.abspath(args.assembler)
    for path, what in ((seed, "种子编译器"), (assembler, "汇编器")):
        if not os.path.isfile(path):
            log("找不到%s：%s" % (what, path))
            return 2
    if not os.path.isfile(os.path.join(project, "project.toml")):
        log("不是项目（缺 project.toml）：%s" % project)
        return 2

    os.makedirs(box, exist_ok=True)
    wrapper, calls = make_wrapper(box, assembler)
    env = dict(os.environ)
    # WSL 上的交叉工具链包装（gcc → aarch64-linux-gnu-gcc）：链接步要用。
    crossbin = os.path.join(REPO, "tmp", "boot", "crossbin")
    if os.path.isdir(crossbin):
        env["PATH"] = crossbin + os.pathsep + env.get("PATH", "")

    gen1 = os.path.join(box, "gen1", os.path.basename(project))
    gen2 = os.path.join(box, "gen2", os.path.basename(project))
    out1 = os.path.join(box, "yh-gen1")
    out2 = os.path.join(box, "yh-gen2")
    copy_sources(project, gen1)

    log("=== 第一代：种子 %s + 汇编器 %s ===" % (seed, assembler))
    r1, t1 = build(seed, gen1, out1, wrapper, env)
    if r1.returncode != 0:
        log("第一代构建失败：\n%s%s" % (r1.stdout[-4000:], r1.stderr[-4000:]))
        return 1
    log("第一代完成：%.1fs → %s" % (t1, out1))

    log("=== 第二代：gen1 编译器 + 同一汇编器 ===")
    copy_sources(project, gen2)
    r2, t2 = build(out1, gen2, out2, wrapper, env)
    if r2.returncode != 0:
        log("第二代构建失败：\n%s%s" % (r2.stdout[-4000:], r2.stderr[-4000:]))
        return 1
    log("第二代完成：%.1fs → %s" % (t2, out2))

    a1, a2 = module_artifacts(gen1), module_artifacts(gen2)
    names = sorted(set(a1) | set(a2))
    diff = [n for n in names if a1.get(n) != a2.get(n)]
    calls_n, calls_ns = read_calls(calls)

    report = os.path.join(box, "report.md")
    with open(report, "w") as fh:
        fh.write("# yh_asm 影子验收报告\n\n")
        fh.write("- 种子编译器：`%s`\n" % os.path.relpath(seed, REPO))
        fh.write("- 汇编器：`%s`（sha256 `%s`）\n"
                 % (os.path.relpath(assembler, REPO), sha256(assembler)))
        fh.write("- 项目：`%s`（两代各自独立拷贝，不共享 .build）\n"
                 % os.path.relpath(project, REPO))
        fh.write("- 接线方式：显式 `YH_LINK=<转发脚本>`，编译器源码与默认行为未改\n\n")
        fh.write("| 项 | 值 |\n| --- | --- |\n")
        fh.write("| 第一代构建 | %.1fs |\n" % t1)
        fh.write("| 第二代构建 | %.1fs |\n" % t2)
        fh.write("| 汇编调用次数 | %d |\n" % calls_n)
        fh.write("| 汇编总耗时 | %.1fs |\n" % (calls_ns / 1e9))
        fh.write("| 模块产物 | %d 个（.s + .s.i） |\n" % len(names))
        fh.write("| 固定点不一致 | %d |\n" % len(diff))
        fh.write("| 结论 | %s |\n" % ("通过" if not diff else "失败"))
        if diff:
            fh.write("\n不一致产物：%s\n" % ", ".join(diff))
    log("影子验收：调用 %d 次，汇编总耗时 %.1fs，固定点不一致 %d 个"
        % (calls_n, calls_ns / 1e9, len(diff)))
    log("报告：%s" % report)
    return 1 if diff else 0


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
