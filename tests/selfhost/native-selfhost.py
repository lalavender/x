#!/usr/bin/env python3
"""tests/selfhost/native-selfhost.py —— 本机全套自举门（0.0.3 滚动自举）。

链路（无 stage0；种子 = 入库的 bin/yh-<平台>-<架构>）：
    bin/yh-<平台>-<架构> build compiler/  → cc2（冷编）
    cc2     build compiler/     → cc3（冷编）
    cc3     build compiler/     → cc4（冷编）
门：
    1. 固定点：候选 cc3/cc4 全部模块 .s/.s.i/.s.ct 逐字节一致；
    2. cc4 自解析：compiler/ 全部 .yh 源文件 --syntax-check 通过；
    3. cc4 语法语料：tests/yh 正例全过、反例全拒；
    4. cc4 运行语料：tests/yh-run 全量（run/fail/pass）。

用法：python3 tests/selfhost/native-selfhost.py [--keep] [--jobs N]
    自解析与两遍语料按 --jobs 并发（缺省 min(8, CPU 核数)）；--workdir 可把
    候选编译器与语料产物放到快速文件系统（cc2/cc3/cc4 会被反复 exec）；
    --skip-corpus 供「同一轮 make test 已跑过等价语料」时省掉重复的一遍。
退出码：全部通过 0。
"""

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILER = ROOT / "compiler"
WORK = ROOT / "tmp" / "selfhost"
HOST_DRIVER = ROOT / "tools" / "llvm-host.py"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))
from selfhost_snapshot_gate import (default_seed, expected_artifacts,
                                    expected_seed_flat_artifacts,
                                    save_snapshot)
from selfhost_snapshot_gate import self_test, snapshot_errors, verify_seed

# 并发上限：自解析与两遍语料都是「一个文件一次编译器进程」，进程启动在
# qemu/容器里约 0.5s，串行跑 86 个源文件与 300 多个用例是纯等待。
DEFAULT_JOBS = max(1, min(8, os.cpu_count() or 1))

# 自举链每一代都要编译 compiler/backend/llvm_bridge.yh，因此各代链接必须能拿到
# 内嵌静态 LLVM 桥。这里复用 tools/llvm-host.py 的链接包装器：准备成功就把它的
# 目录前置到子进程 PATH；未准备（无 SDK）时只警告并按原路径继续，不把 LLVM 变成
# 自举的失败点（与 make / seed-build.py 的 auto 语义一致）。
SHIM_DIR = None


def llvm_shim_for_seed(seed: Path):
    """按种子文件名推导 LLVM 宿主架构并请求链接包装器目录；不可用时返回 None。

    固定 LLVM SDK 只发布 Linux 宿主（tools/llvm-host.py 的 hosts 表），
    因此非 Linux 种子（如 bin/yh-darwin-arm64）直接返回 None，不去请求
    不存在的宿主，避免打印误导性警告。
    """
    name = seed.name
    if "linux" not in name:
        return None
    if "aarch64" in name or "arm64" in name:
        host = "linux-aarch64"
    elif "x64" in name or "x86_64" in name:
        host = "linux-x86_64"
    else:
        return None
    request = [sys.executable, str(HOST_DRIVER), "shim", "--host", host, "--mode", "auto"]
    result = subprocess.run(request, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"警告：本次自举未链入内嵌 LLVM 桥（{host}）："
              f"{(result.stderr or result.stdout).strip()[-200:]}", file=sys.stderr)
        return None
    record = json.loads([line for line in result.stdout.splitlines() if line.strip()][-1])
    print(f"自举链接已接入内嵌 LLVM 桥：host={record['host']} "
          f"bridge={record['bridge_sha256'][:12]}", file=sys.stderr)
    return Path(record["shim_dir"])


def run(cmd, cwd=None, shim=False):
    """执行子命令；shim=True 时把内嵌桥的链接包装器前置到 PATH。

    只有「编译 compiler/ 自身」的调用需要 shim（那一步会链接 llvm_bridge.yh）；
    语料检查、自解析等步骤必须保持原始 PATH，否则会把桥链接强加给语料程序。
    """
    environment = dict(os.environ)
    if shim and SHIM_DIR is not None:
        environment["PATH"] = str(SHIM_DIR) + os.pathsep + environment.get("PATH", "")
    return subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True,
                          text=True, timeout=1800, env=environment)


def build(cc, out, generation, expected, compatible=()):
    """冷编一代，并在共享的 .build 被后续代覆盖前保存其产物。"""
    bdir = COMPILER / ".build"
    if bdir.exists():
        shutil.rmtree(bdir)
    command = [str(cc), "build", "-o", str(out)]
    r = run(command, cwd=COMPILER, shim=True)
    if r.returncode != 0:
        print(f"FAIL 构建 {out.name}:", r.stderr[-400:])
        sys.exit(1)
    snapshot = save_snapshot(bdir, WORK / "snapshots" / generation)
    errors = snapshot_errors([(generation, snapshot)], expected)
    if errors:
        for compatible_expected in compatible:
            if not snapshot_errors([(generation, snapshot)], compatible_expected):
                errors = []
                break
    if errors:
        print(f"FAIL {generation} 产物：", "；".join(errors))
        sys.exit(1)
    return snapshot


def run_fixedpoint_probe(cc, generation):
    """构建并运行覆盖前向调用、聚合浮点与循环的 .yh 自举探针。"""
    source = ROOT / "tests" / "selfhost" / "fixedpoint-probe.yh"
    output = WORK / f"fixedpoint-probe-{generation}"
    result = run([cc, str(source), "-o", str(output)])
    if result.returncode != 0:
        print(f"FAIL {generation} 探针构建：", result.stderr[-400:])
        return False
    result = run([str(output)])
    if result.returncode != 0:
        print(f"FAIL {generation} 探针退出码：{result.returncode}")
        return False
    print(f"{generation} 固定点探针：OK")
    return True


def run_cli_probe(cc):
    """CLI 冒烟：裸调用与坏参数必须打印完整用法并以用法错误码 2 退出。"""
    ok = True
    r = run([cc])
    # 末行必须出现，防止用法输出被截断；信号死亡时 returncode 为负值。
    if r.returncode != 2 or "用法: yh" not in r.stderr \
            or "yh list" not in r.stderr:
        print(f"FAIL cli 裸调用：rc={r.returncode}, stderr 尾部：{r.stderr[-120:]}")
        ok = False
    r = run([cc, "--bogus-flag", "x.yh"])
    if r.returncode != 2 or "用法: yh" not in r.stderr:
        print(f"FAIL cli 坏参数：rc={r.returncode}, stderr 尾部：{r.stderr[-120:]}")
        ok = False
    print("CLI 冒烟（裸调用/坏参数，用法完整且退出码 2）："
          + ("OK" if ok else "FAIL"))
    return ok


def main() -> int:
    """运行种子迁移后的最终双代固定点与语言全量语料。"""
    global SHIM_DIR, WORK
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--seed", type=Path, default=default_seed(ROOT))
    ap.add_argument("--jobs", type=int, default=DEFAULT_JOBS,
                    help=f"自解析与语料并发数（缺省 {DEFAULT_JOBS}；1 为串行）")
    ap.add_argument("--workdir", default=str(WORK),
                    help="候选编译器与探针产物目录（缺省 tmp/selfhost；"
                         "可指向快速文件系统，cc2/cc3/cc4 会被反复 exec）")
    ap.add_argument("--skip-corpus", action="store_true",
                    help="跳过两遍语料（仅当同一轮里 make test 已用等价编译器"
                         "跑过语料时才用；默认不跳过）")
    args = ap.parse_args()
    args.jobs = max(1, args.jobs)
    WORK = Path(args.workdir)
    WORK.mkdir(parents=True, exist_ok=True)
    if not self_test():
        print("FAIL 自举快照门自检")
        return 1
    print("自举快照门自检：OK")
    seed = args.seed.resolve()
    try:
        seed_hash = verify_seed(seed)
    except (OSError, ValueError) as error:
        print(f"FAIL 自举种子：{error}")
        return 1
    print(f"自举种子 SHA-256：{seed_hash}")
    SHIM_DIR = llvm_shim_for_seed(seed)

    ok = True
    expected = expected_artifacts(COMPILER)
    # 滚动种子可能早于或已包含 .s.ct / RS3b 按文件对象布局；首代只接受
    # 这些历史完整产物集合之一，后续代必须全部使用当前格式并进入固定点。
    legacy_expected = {path for path in expected if not path.endswith(".s.ct")}
    seed_flat = expected_seed_flat_artifacts(COMPILER)
    d2 = build(seed, WORK / "cc2", "cc2", expected,
               (legacy_expected, seed_flat))
    d3 = build(WORK / "cc2", WORK / "cc3", "cc3", expected)
    d4 = build(WORK / "cc3", WORK / "cc4", "cc4", expected)
    print(f"cc2/cc3/cc4 构建完成（种子 = {seed}）")

    # 1) 旧种子可产生一次迁移差异；最终候选相邻两代必须达到固定点。
    transition = snapshot_errors([("cc2", d2), ("cc3", d3)], expected)
    if transition:
        print(f"种子迁移后续跑验证：cc2→cc3 有 {len(transition)} 项内容变化")
    errors = snapshot_errors([("cc3", d3), ("cc4", d4)], expected)
    if errors:
        print("FAIL 模块固定点：", "；".join(errors))
        ok = False
    else:
        print(f"模块固定点（候选 cc3→cc4，共 {len(expected)} 个产物）：一致")

    cc4 = str(WORK / "cc4")
    # 2) 最终候选自解析（每个源文件一次进程，并发跑）
    sources = sorted(COMPILER.rglob("*.yh"))

    def self_parse(src):
        """返回自解析失败的源文件名（成功返回 None）。"""
        return None if run([cc4, "--syntax-check", str(src)]).returncode == 0 \
            else src.name

    if args.jobs > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            bad = [name for name in pool.map(self_parse, sources) if name]
    else:
        bad = [name for name in (self_parse(src) for src in sources) if name]
    print(f"cc4 自解析（{len(sources)} 个源文件，并发 {args.jobs}）："
          + ("OK" if not bad else "FAIL " + ",".join(bad)))
    ok = ok and not bad

    # 3) 固定点探针
    ok = run_fixedpoint_probe(cc4, "cc4") and ok

    # 3b) CLI 冒烟
    ok = run_cli_probe(cc4) and ok

    # 4/5) 语法语料与运行语料。--skip-corpus 供「同一轮里 make test 已经用
    # 等价编译器跑过两遍语料」时省掉这 1 分钟；默认不跳过，门不因此变松。
    if args.skip_corpus:
        print("语法语料与运行语料：按 --skip-corpus 跳过（调用方已跑过）")
    else:
        corpus_work = WORK / "yh-run-work"
        r = run(["python3", "tests/yh/check.py", "--compiler",
                 "--compiler-path", cc4, "--quiet", "--jobs", str(args.jobs)])
        print("语法语料：", (r.stdout.strip().splitlines() or ["无输出"])[-1])
        if r.returncode != 0:
            print(r.stdout, r.stderr, sep="\n")
        ok = ok and r.returncode == 0

        r = run(["python3", "tests/yh-run/check.py", "--compiler", cc4,
                 "--quiet", "--jobs", str(args.jobs),
                 "--workdir", str(corpus_work)])
        print("运行语料：", (r.stdout.strip().splitlines() or ["无输出"])[-1])
        if r.returncode != 0:
            print(r.stdout, r.stderr, sep="\n")
        ok = ok and r.returncode == 0

    if not args.keep:
        shutil.rmtree(WORK, ignore_errors=True)
    print("总计：%s" % ("全部通过" if ok else "存在失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
