#!/usr/bin/env python3
"""tests/selfhost/native-selfhost.py —— 本机全套自举门（0.0.3 滚动自举）。

链路（无 stage0；种子 = 入库的 bin/yh）：
    bin/yh build compiler/  → cc2（冷编）
    cc2     build compiler/     → cc3（冷编）
    cc3     build compiler/     → cc4（冷编）
门：
    1. 固定点：候选 cc3/cc4 全部模块 .s/.s.i/.s.ct 逐字节一致；
    2. cc4 自解析：compiler/ 全部 .yh 源文件 --syntax-check 通过；
    3. cc4 语法语料：tests/yh 正例全过、反例全拒；
    4. cc4 运行语料：tests/yh-run 全量（run/fail/pass）。

用法：python3 tests/selfhost/native-selfhost.py [--keep]
退出码：全部通过 0。
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILER = ROOT / "compiler"
WORK = ROOT / "tmp" / "selfhost"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))
from selfhost_snapshot_gate import default_seed, expected_artifacts, save_snapshot
from selfhost_snapshot_gate import self_test, snapshot_errors, verify_seed


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True,
                          text=True, timeout=1800)


def build(cc, out, generation, expected, compatible=()):
    """冷编一代，并在共享的 .build 被后续代覆盖前保存其产物。"""
    bdir = COMPILER / ".build"
    if bdir.exists():
        shutil.rmtree(bdir)
    command = [str(cc), "build", "-o", str(out)]
    r = run(command, cwd=COMPILER)
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--seed", type=Path, default=default_seed(ROOT))
    args = ap.parse_args()
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

    ok = True
    expected = expected_artifacts(COMPILER)
    # 滚动种子可能早于或已包含 .s.ct；首代只接受这两种完整产物集合之一，
    # 后续代必须全部使用当前格式并进入固定点。
    legacy_expected = {path for path in expected if not path.endswith(".s.ct")}
    d2 = build(seed, WORK / "cc2", "cc2", expected, (legacy_expected,))
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
    # 2) 最终候选自解析
    bad = []
    sources = sorted(COMPILER.rglob("*.yh"))
    for src in sources:
        r = run([cc4, "--syntax-check", str(src)])
        if r.returncode != 0:
            bad.append(src.name)
    print(f"cc4 自解析（{len(sources)} 个源文件）："
          + ("OK" if not bad else "FAIL " + ",".join(bad)))
    ok = ok and not bad

    # 3) 固定点探针
    ok = run_fixedpoint_probe(cc4, "cc4") and ok

    # 3b) CLI 冒烟
    ok = run_cli_probe(cc4) and ok

    # 4) 语法语料
    r = run(["python3", "tests/yh/check.py", "--compiler",
             "--compiler-path", cc4, "--quiet"])
    print("语法语料：", (r.stdout.strip().splitlines() or ["无输出"])[-1])
    if r.returncode != 0:
        print(r.stdout, r.stderr, sep="\n")
    ok = ok and r.returncode == 0

    # 5) 运行语料
    r = run(["python3", "tests/yh-run/check.py", "--compiler", cc4, "--quiet"])
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
