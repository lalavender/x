#!/usr/bin/env python3
"""S4-2 影子门：check 从语法节点重算表达式语义，必须与 parse 注解逐字段一致。

做法：在正常编译路径（`compile=1`，节点带着 parse 当场算出的注解）下打开
`YH_AST_FULL_CHECK=1`，模块 worker 在函数体全部解析完之后从节点重算常量链
（字面量 / 括号 / 一元 / 二元折叠），不一致即构建失败。同时该模式要求至少
判定过一个节点——覆盖为空也算失败，避免门禁空转。

夹具刻意覆盖：常量初始化式、数组长度、一元/二元混合、括号、进制与移位，
这些正是旧路径在 `c_fold` 上下文里折叠的形态。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_COMPILER = ROOT / "yh"
WORK = ROOT / "tmp" / "front-full-test"

FIXTURE = """module main

const BASE int = 2 + 3

const SCALED int = BASE * 2

const MASKED int = (0xF0 >> 4) | 1

const NAMED int = BASE + 1

const CYCLED int = NAMED * 2 - MASKED

type Row = [NAMED]int

struct Packet {
    items [BASE + 1]int;
    tag int;
}

fn main() int {
    let a [SCALED]int = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    let k [NAMED]int = [1, 2, 3, 4, 5, 6]
    let r Row
    let b int = ~0 + 1 + 'A' - 64
    let c int = -(-(BASE))
    let d int = (1 == 2) + 1
    let e int = 7 % 4 + MASKED + NAMED
    let f int = len(r)
    printf("%d\\n", a[0] + b + c + d + e + f + sizeof(Packet))
    return 0
}
"""


def write_project(work: Path) -> Path:
    """写入单模块夹具项目。"""
    if work.exists():
        shutil.rmtree(work)
    (work / "src").mkdir(parents=True)
    (work / "project.toml").write_text(
        '[project]\nos = "host"\narch = "host"\n'
        'name = "frontfull"\nsource = "src"\n',
        encoding="utf-8")
    (work / "src" / "main.yh").write_text(FIXTURE, encoding="utf-8")
    return work


def run(compiler: Path, work: Path, env: dict) -> subprocess.CompletedProcess:
    """在夹具项目里运行 yh check。"""
    return subprocess.run(
        [str(compiler), "check"], cwd=work, env=env,
        capture_output=True, text=True, errors="replace", timeout=180)


def main() -> int:
    """普通 check 通过后，再开影子门重跑；两者都要通过。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(DEFAULT_COMPILER))
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve()
    work = write_project(WORK)

    base_env = os.environ.copy()
    base_env.pop("YH_AST_FULL_CHECK", None)
    normal = run(compiler, work, base_env)
    if normal.returncode != 0:
        print(normal.stdout + normal.stderr, file=sys.stderr)
        print("FAIL 夹具普通 check 未通过", file=sys.stderr)
        return 1

    full_env = base_env.copy()
    full_env["YH_AST_FULL_CHECK"] = "1"
    full = run(compiler, work, full_env)
    if full.returncode != 0:
        print(full.stdout + full.stderr, file=sys.stderr)
        print("FAIL 影子门判定出现不一致或覆盖为空", file=sys.stderr)
        return 1
    if "检查通过" not in full.stdout:
        print(full.stdout + full.stderr, file=sys.stderr)
        print("FAIL 影子门模式未走 check 成功路径", file=sys.stderr)
        return 1

    print("PASS S4-2 影子门：常量链重算与 parse 注解一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
