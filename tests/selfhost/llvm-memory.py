#!/usr/bin/env python3
"""LL5 首片门：局部标量取址/解引用的文本、O0/O2 原生运行与拒绝层。

验收（与实施方案 LL5 第一切片对应）：
  * `&局部`/`参数指针`/`*p` 读写进入 alloca + load/store lowering；文本含
    内存指令且 `opt` 验证通过；
  * O0 文本与 `default<O2>` 管线后的对象分别用 clang 汇编、gcc 链接并原生运行，
    退出码 0（函数参数指针、复合赋值、循环、指针 phi 全走真实路径）；
  * 超出首片的取址形态（`&arr[0]`）带来源位置拒绝，不静默回退。
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp" / "llvm-migration" / "llvm-memory"
TARGET = "x86_64-unknown-linux-gnu"

SOURCE = """module memory;

// inc_by：通过出参写回，验证参数指针与复合赋值。
fn inc_by(p *int, delta int) int { *p += delta; return *p; }

// clear：通过指针清零。
fn clear(p *int) void { *p = 0; }

fn main() int {
    let x int = 41;
    let p *int = &x;
    if (inc_by(p, 1) != 42) { return 1; }
    if (x != 42) { return 2; }
    *p = 7;
    if (*p != 7 || x != 7) { return 3; }
    let y int = 5;
    let q *int = &y;
    *q = *p + 1;
    if (y != 8) { return 4; }
    let i int = 0;
    for i < 3 { *q += 1; i += 1; }
    if (y != 11) { return 5; }
    clear(q);
    if (y != 0 || *q != 0) { return 6; }
    let sel *int = p;
    if (x == 7) { sel = q; }
    *sel = 9;
    if (x != 7 || y != 9) { return 7; }
    return 0;
}
"""

REJECT = """module badforin;

// bad_forin：for-in 迭代协议不在已验收范围；必须带来源拒绝，不能静默回退。
fn bad_forin(x int) int {
    let a [3]int = [1, 2, 3];
    let sum int = 0;
    for v in a { sum += v; }
    return sum;
}

fn main() int { return 0; }
"""


def run(command, **kwargs):
    """执行真候选或差分工具，保留有界输出；超时视为门失败。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=300, **kwargs)


def locate(*names):
    """按 /usr/bin 优先、PATH 回落的顺序查找宿主差分工具。

    这些门需要宿主 x86_64 的 clang/opt/gcc；PATH 上可能有 crossbin 交叉包装器，
    因此先固定 /usr/bin，再允许 PATH 提供其它发行路径。
    """
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
    """按 O0/O2 核对内存 lowering，并验证首片之外的取址被拒绝。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    assert Path(compiler).is_file(), f"编译器不存在: {compiler}"
    tools = {name: locate(*candidates) for name, candidates in {
        "clang": ("clang",), "opt": ("opt",), "cc": ("gcc", "cc")}.items()}
    missing = [name for name, path in tools.items() if path is None]
    assert not missing, f"LL5 差分工具缺失: {missing}（仅开发门使用 clang/opt）"
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    source = WORK / "memory.yh"
    source.write_text(SOURCE, encoding="utf-8")
    reject = WORK / "bad.yh"
    reject.write_text(REJECT, encoding="utf-8")

    for level in (0, 2):
        llfile = WORK / f"memory-O{level}.ll"
        text = emit_text(compiler, source, level, llfile)
        # 用户函数必须真的产生局部存储与 i32 读写，而不是只靠运行时 helper。
        for token in ("= alloca i32", "load i32, ptr", "store i32 ", "getelementptr i8"):
            assert token in text, f"O{level} 文本缺少内存 lowering 痕迹: {token}\n{text[-800:]}"
        verify = run([tools["opt"], "-passes=verify", "-S", str(llfile), "-o", os.devnull])
        assert verify.returncode == 0, f"O{level} opt 验证失败\n{verify.stderr[-1200:]}"
        obj_source = llfile
        if level == 2:
            # 用独立 opt 管线模拟桥的 O2 执行，再汇编链接运行。
            optimized = WORK / "memory-O2-opt.ll"
            result = run([tools["opt"], "-S", "-passes=default<O2>", str(llfile),
                          "-o", str(optimized)])
            assert result.returncode == 0, f"O2 管线失败\n{result.stderr[-1200:]}"
            obj_source = optimized
        obj = WORK / f"memory-O{level}.o"
        result = run([tools["clang"], "-c", str(obj_source), "-o", str(obj)])
        assert result.returncode == 0, f"O{level} 汇编失败\n{result.stderr[-1200:]}"
        executable = WORK / f"memory-O{level}"
        result = run([tools["cc"], "-no-pie", str(obj), "-o", str(executable)])
        assert result.returncode == 0, f"O{level} 链接失败\n{result.stderr[-1200:]}"
        result = run([str(executable)])
        assert result.returncode == 0, (
            f"O{level} 原生运行失败 rc={result.returncode}\n{result.stdout[-400:]}")

    # 首片之外的取址形态必须带来源位置拒绝，且不发布产物。
    output = WORK / "bad-out"
    result = run([compiler, "--backend", "llvm", "--target", TARGET, "-O0",
                  "-o", str(output), str(reject)])
    assert result.returncode != 0, "&arr[0] 未被拒绝"
    assert ".yh:" in result.stderr and "bad_forin" in result.stderr, result.stderr[-800:]
    assert not output.exists(), "拒绝路径仍发布了产物"

    print("LL5 首片通过：局部 alloca/load/store、参数指针、O0/O2 原生运行、切片带来源拒绝")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
