#!/usr/bin/env python3
"""tools/selfbuild-gate.py —— 验收连续自举代的模块固定点。

链路：
    平台入库种子 → yh build compiler/（cc2）→ cc2 build compiler/（cc3）
            → cc3 build compiler/（cc4）
门：
    1. 每代保存独立、非空且完整的模块汇编/接口快照；
    2. 最终候选 cc3/cc4 快照逐字节一致；
    3. cc4 编译并运行固定点探针，modules 项目语料通过。

用法：python3 tools/selfbuild-gate.py
退出码：全部通过 0。
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "tmp" / "selfbuild-gate"
COMPILER = ROOT / "compiler"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))
from selfhost_snapshot_gate import default_seed, expected_artifacts, save_snapshot
from selfhost_snapshot_gate import self_test, snapshot_errors, verify_seed

PROBE = ROOT / "tests" / "selfhost" / "probes" / "fixedpoint-probe.yh"


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True,
                          text=True, timeout=1800)


def main() -> int:
    """执行三代固定点、语言探针及 modules 语料门。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=Path, default=default_seed(ROOT))
    args = ap.parse_args()
    if not self_test():
        print("FAIL 自举快照门自检")
        return 1
    print("自举快照门自检：OK")
    WORK.mkdir(parents=True, exist_ok=True)
    expected = expected_artifacts(COMPILER)
    seed_cc = args.seed.resolve()
    try:
        seed_hash = verify_seed(seed_cc)
    except (OSError, ValueError) as error:
        print(f"FAIL 自举种子：{error}")
        return 1
    print(f"stage1 = {seed_cc}（SHA-256 {seed_hash}）")

    prev = seed_cc
    gens = []
    for name in ("cc2", "cc3", "cc4"):
        bdir = COMPILER / ".build"
        if bdir.exists():
            shutil.rmtree(bdir)
        out = WORK / name
        command = [str(prev), "build"]
        command.extend(("-o", str(out)))
        r = run(command, cwd=COMPILER)
        if r.returncode != 0:
            print(f"FAIL {name} 构建:", r.stderr[-400:])
            return 1
        snapshot = save_snapshot(bdir, WORK / "snapshots" / name)
        errors = snapshot_errors([(name, snapshot)], expected)
        if errors:
            print(f"FAIL {name} 产物：", "；".join(errors))
            return 1
        gens.append((name, snapshot, out))
        prev = out
        print(f"{name} 构建完成")

    # 快照在对应代构建后立即保存，不会随 compiler/.build 被覆盖。
    snaps = [(name, artifacts) for name, artifacts, _ in gens]
    transition = snapshot_errors(snaps[:2], expected)
    if transition:
        print(f"种子迁移后续跑验证：cc2→cc3 有 {len(transition)} 项内容变化")
    errors = snapshot_errors(snaps[-2:], expected)
    if errors:
        print("FAIL 模块固定点：", "；".join(errors))
        return 1
    for (n1, _), (n2, _) in zip(snaps[-2:], snaps[-1:]):
        print(f"模块固定点 {n1}→{n2}：全部 {len(expected)} 个产物逐字节一致")

    # 运行覆盖前向调用、聚合浮点和循环的固定点探针。
    binp = WORK / "fixedpoint-probe"
    r = run([str(WORK / "cc4"), str(PROBE), "-o", str(binp)])
    if r.returncode != 0:
        print("FAIL cc4 编译固定点探针：", r.stderr[-300:])
        return 1
    else:
        r2 = subprocess.run([str(binp)], capture_output=True)
        if r2.returncode != 0:
            print(f"FAIL 固定点探针退出码 {r2.returncode} 期望 0")
            return 1
        else:
            print("cc4 固定点探针：OK")

    r = run(["python3", "tests/modules/check.py",
             "--compiler-path", str(WORK / "cc4")])
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "modules runner 无输出")
    if r.returncode != 0:
        return 1

    print("总计：全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
