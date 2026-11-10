#!/usr/bin/env python3
"""纯语法 AST 地基回归：项目上下文下 parse 不查语义也能产出 AST。

用 `YH_SYNTAX_AST=1 yh check` 跑一个覆盖类型语法、sizeof、结构体/数组
字面量、函数类型与控制流的单模块项目。该模式在 module worker 里走
compile=0 + ast_capture=1，只解析并检查 AST 非空，不进入 check/lower。

同一夹具先用普通 `yh check` 验证语义合法，避免用非法输入“通过”语法门。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_COMPILER = ROOT / "yh"
WORK = ROOT / "tmp" / "front-syntax-test"

FIXTURE = """module main

struct Point {
    x int;
    y int;
}

union Value {
    i int;
    f f64;
}

enum Color {
    Red;
    Green;
}

type Alias = Point

fn add(a int, b int) int {
    return a + b;
}

fn apply(f fn(int, int) int, a int, b int) int {
    return f(a, b);
}

fn main() int {
    let p Point = Point{1, 2}
    let q Point = Point{y: 3, x: 4}
    let a [2]int = [1, 2]
    let f fn(int, int) int = add
    let cfn @[extern] fn(*char) int
    let i int = 0
    for i < 2 {
        i += 1
    }
    if (sizeof(Point) + sizeof(*Alias) + sizeof(p) + sizeof(cfn) < 0) {
        return 1
    }
    if (p.x + q.y + a[0] == 8) {
        return apply(f, 1, 2)
    }
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
        'name = "frontsyntax"\nsource = "src"\n',
        encoding="utf-8")
    (work / "src" / "main.yh").write_text(FIXTURE, encoding="utf-8")
    return work


def run(compiler: Path, work: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    """在夹具项目里运行 yh check。"""
    return subprocess.run(
        [str(compiler), "check"], cwd=work, env=env,
        capture_output=True, text=True, errors="replace", timeout=180)


def main() -> int:
    """先语义 check，再纯语法 AST check；任一失败返回 1。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(DEFAULT_COMPILER))
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve()
    work = write_project(WORK)

    base_env = os.environ.copy()
    normal = run(compiler, work, base_env)
    if normal.returncode != 0:
        print(normal.stdout + normal.stderr, file=sys.stderr)
        print("FAIL 夹具普通 check 未通过", file=sys.stderr)
        return 1

    syntax_env = base_env.copy()
    syntax_env["YH_SYNTAX_AST"] = "1"
    syntax = run(compiler, work, syntax_env)
    if syntax.returncode != 0:
        print(syntax.stdout + syntax.stderr, file=sys.stderr)
        print("FAIL 纯语法 AST 解析失败", file=sys.stderr)
        return 1
    if "检查通过" not in syntax.stdout:
        print(syntax.stdout + syntax.stderr, file=sys.stderr)
        print("FAIL 纯语法 AST 模式未走 check 成功路径", file=sys.stderr)
        return 1

    print("PASS 纯语法 AST：类型/字面量/控制流项目解析成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())
