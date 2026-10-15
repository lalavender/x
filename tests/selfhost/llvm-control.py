#!/usr/bin/env python3
"""LL4 首片门：嵌套循环、break/continue、无限循环的 lowering 与原生运行。

验收（与实施方案 LL4 前两行对应）：
  * 嵌套循环的 break/continue 只作用于最内层；无限循环 `for {}` 的退出只经 break；
  * 循环携带值（含内层写入外层绑定）在两趟协议下生成合法 phi，`opt` 验证通过；
  * O0 文本与 `default<O2>` 管线后的对象分别汇编、链接并原生运行，退出码 0；
  * 尚未支持的 `goto` 带来源位置拒绝，不静默回退。
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp" / "llvm-migration" / "llvm-control"
TARGET = "x86_64-unknown-linux-gnu"

SOURCE = """module control;

// main：与 tests/yh-run/run/llvm-control-flow.yh 同源的语义断言。
fn main() int {
    let total int = 0;
    let i int = 0;
    for i < 3 {
        let j int = 0;
        for j < 10 {
            if (j == 2) { break; }
            total += 1;
            j += 1;
        }
        total += 10;
        i += 1;
    }
    if (total != 36) { return 1; }
    let n int = 0;
    let k int = 0;
    for {
        k += 1;
        if (k % 2 == 0) { continue; }
        n += 1;
        if (k >= 7) { break; }
    }
    if (n != 4 || k != 7) { return 2; }
    let m int = 0;
    let a int = 0;
    for a < 2 {
        let b int = 0;
        for b < 4 {
            b += 1;
            if (b == 2) { continue; }
            m += 1;
        }
        a += 1;
    }
    if (m != 6) { return 3; }
    let s int = 0;
    let t int = 0;
    for t < 10 {
        let u int = 0;
        for u < 2 { s += 1; u += 1; }
        if (t == 1) { break; }
        t += 1;
    }
    if (s != 4) { return 4; }
    let w int = 0;
    let q int = 0;
    for q < 2 {
        let z int = 10;
        z += 1;
        w += z;
        q += 1;
    }
    if (w != 22) { return 5; }
    return 0;
}
"""

REJECT = """module bad;

// bad_goto：goto/label 不在 LL4 首片；必须带来源拒绝，不能静默回退。
fn bad_goto(x int) int {
    goto done;
    done:
    return x;
}

fn main() int { return 0; }
"""


def run(command, **kwargs):
    """执行真候选或差分工具，保留有界输出；超时视为门失败。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=300, **kwargs)


def locate(*names):
    """按 /usr/bin 优先、PATH 回落的顺序查找宿主差分工具。"""
    for name in names:
        fallback = Path("/usr/bin") / name
        if fallback.is_file():
            return str(fallback)
        found = shutil.which(name)
        if found:
            return found
    return None


def emit_text(compiler, source, level, output):
    """用真编译器发射 LLVM 文本（不调用桥），返回文本内容。"""
    result = run([compiler, "--emit-asm", "--backend", "llvm", "--target", TARGET,
                  f"-O{level}", "--emit-llvm", str(source)])
    assert result.returncode == 0, (
        f"O{level} LLVM 文本发射失败 rc={result.returncode}\n{result.stderr[-1200:]}")
    output.write_text(result.stdout, encoding="utf-8")
    return result.stdout


def main():
    """按 O0/O2 核对控制流 lowering，并验证 goto 被拒绝。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    assert Path(compiler).is_file(), f"编译器不存在: {compiler}"
    tools = {name: locate(*candidates) for name, candidates in {
        "clang": ("clang",), "opt": ("opt",), "cc": ("gcc", "cc")}.items()}
    missing = [name for name, path in tools.items() if path is None]
    assert not missing, f"LL4 差分工具缺失: {missing}（仅开发门使用 clang/opt）"
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    source = WORK / "control.yh"
    source.write_text(SOURCE, encoding="utf-8")
    reject = WORK / "bad.yh"
    reject.write_text(REJECT, encoding="utf-8")

    for level in (0, 2):
        llfile = WORK / f"control-O{level}.ll"
        text = emit_text(compiler, source, level, llfile)
        # 嵌套循环必须真的产生多组回边与携带 phi，而不是被优化成顺序代码。
        assert text.count("phi ") >= 4, f"O{level} 文本缺少循环携带 phi\n{text[-800:]}"
        assert text.count("br i1 ") >= 3, f"O{level} 文本缺少条件回边\n{text[-800:]}"
        verify = run([tools["opt"], "-passes=verify", "-S", str(llfile), "-o", os.devnull])
        assert verify.returncode == 0, f"O{level} opt 验证失败\n{verify.stderr[-1200:]}"
        obj_source = llfile
        if level == 2:
            optimized = WORK / "control-O2-opt.ll"
            result = run([tools["opt"], "-S", "-passes=default<O2>", str(llfile),
                          "-o", str(optimized)])
            assert result.returncode == 0, f"O2 管线失败\n{result.stderr[-1200:]}"
            obj_source = optimized
        obj = WORK / f"control-O{level}.o"
        result = run([tools["clang"], "-c", str(obj_source), "-o", str(obj)])
        assert result.returncode == 0, f"O{level} 汇编失败\n{result.stderr[-1200:]}"
        executable = WORK / f"control-O{level}"
        result = run([tools["cc"], "-no-pie", str(obj), "-o", str(executable)])
        assert result.returncode == 0, f"O{level} 链接失败\n{result.stderr[-1200:]}"
        result = run([str(executable)])
        assert result.returncode == 0, (
            f"O{level} 原生运行失败 rc={result.returncode}\n{result.stdout[-400:]}")

    # goto 仍不在首片：必须带来源位置拒绝，且不发布产物。
    output = WORK / "bad-out"
    result = run([compiler, "--backend", "llvm", "--target", TARGET, "-O0",
                  "-o", str(output), str(reject)])
    assert result.returncode != 0, "goto 未被拒绝"
    assert ".yh:" in result.stderr and "bad_goto" in result.stderr, result.stderr[-800:]
    assert not output.exists(), "拒绝路径仍发布了产物"

    print("LL4 首片通过：嵌套循环、break/continue、无限循环、O0/O2 原生运行、goto 带来源拒绝")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
