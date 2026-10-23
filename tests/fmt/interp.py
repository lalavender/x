#!/usr/bin/env python3
"""字符串插值负例门：逐例生成最小项目，断言编译器在预期位置报错。

覆盖缺 import、空表达式、未终结、花括号、顶层三元、非法 spec、spec 类型
不匹配与不支持类型。成功返回 0；任一例未被拒绝或诊断不含期望片段返回 1。

usage: python3 tests/fmt/interp.py [--compiler ./yh] [--stdlib ./libs]
                                   [--workdir tmp/fmt-interp] [--keep]
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

# name -> (main 源码, 期望诊断片段)
CASES = {
    "missing-import": ('''module main

import string

fn main() int {
    let text string.String = "x=${1}"
    string.release(&text)
    return 0
}
''', "字符串插值需要 import fmt"),
    "empty-expr": ('''module main

import fmt
import string

fn main() int {
    let text string.String = "${}"
    string.release(&text)
    return 0
}
''', "插值表达式不能为空"),
    "unclosed": ('''module main

import fmt
import string

fn main() int {
    let text string.String = "${1"
    string.release(&text)
    return 0
}
''', "插值未终结"),
    "braces": ('''module main

import fmt
import string

fn main() int {
    let text string.String = "${1 + {2}}"
    string.release(&text)
    return 0
}
''', "插值表达式内暂不支持花括号"),
    "ternary": ('''module main

import fmt
import string

fn main() int {
    let text string.String = "${true ? 1 : 2}"
    string.release(&text)
    return 0
}
''', "插值内的三元表达式需要加括号"),
    "bad-spec": ('''module main

import fmt
import string

fn main() int {
    let text string.String = "${1:z}"
    string.release(&text)
    return 0
}
''', "非法格式说明符"),
    "spec-type": ('''module main

import fmt
import string

fn main() int {
    let text string.String = "${1:f}"
    string.release(&text)
    return 0
}
''', "非法格式说明符"),
    "unsupported-type": ('''module main

import fmt
import string

struct Point {
    x int
    y int
}

fn main() int {
    let point Point = Point{ x: 1, y: 2 }
    let text string.String = "${point}"
    string.release(&text)
    return 0
}
''', "该类型不支持字符串插值"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="字符串插值负例门")
    parser.add_argument("--compiler", default=str(ROOT / "yh"))
    parser.add_argument("--stdlib", default=str(ROOT / "libs"))
    parser.add_argument("--workdir", default=str(ROOT / "tmp" / "fmt-interp"))
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    work = Path(args.workdir).resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["YH_STDLIB"] = str(Path(args.stdlib).resolve())
    failed = 0
    for name, (source, expected) in CASES.items():
        root = work / name
        (root / "src" / "main").mkdir(parents=True, exist_ok=True)
        (root / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\n'
            f'name = "interp_{name.replace("-", "_")}"\nsource = "src"\n')
        (root / "src" / "main" / "main.yh").write_text(source)
        result = subprocess.run([args.compiler, "build"], cwd=root,
                                capture_output=True, text=True,
                                timeout=300, env=env)
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 0 or expected not in output:
            failed += 1
            print(f"FAIL {name}: rc={result.returncode} "
                  f"expect={expected!r} output={output[-300:]!r}")
        else:
            print(f"OK   {name}")
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    print(f"结果: {len(CASES) - failed} passed; {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
