#!/usr/bin/env python3
"""LL5 聚合首片门：局部定长数组的字面量、下标、取址与按值复制。

验收（与实施方案 LL5 局部数据/副本切片对应）：
  * 数组绑定统一 ALLOCA 字节存储；下标读写走 GEP（常量/动态偏移）+ LOAD/STORE；
  * 数组字面量逐元素写入；按值复制用 llvm.memcpy（落到同对象 memcpy 弱定义）；
  * O0 文本与 `default<O2>` 管线后的对象分别汇编、链接并原生运行，退出码 0；
  * 结构体等尚未支持的聚合形态必须带来源拒绝。
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp" / "llvm-migration" / "llvm-array"
TARGET = "x86_64-unknown-linux-gnu"

SOURCE = """module arraycase;

fn main() int {
    let a [3]int = [1, 2, 3];
    let sum int = 0;
    let i int = 0;
    for i < 3 {
        sum += a[i];
        i += 1;
    }
    if (sum != 6) { return 1; }
    a[1] = 20;
    if (a[1] != 20) { return 2; }
    let p *int = &a[0];
    *p = 5;
    if (a[0] != 5) { return 3; }
    let b [3]int = a;
    if (b[0] != 5 || b[2] != 3) { return 4; }
    b[2] = 7;
    if (a[2] != 3) { return 5; }
    let c [2][3]int = [[1, 2, 3], [4, 5, 6]];
    if (c[1][2] != 6) { return 6; }
    c[0][1] = 9;
    if (c[0][1] != 9 || c[1][0] != 4) { return 7; }
    let d [3]int = [0, 0, 0];
    d = a;
    d[0] = 11;
    if (a[0] != 5 || d[0] != 11) { return 8; }
    let k int = 0;
    for k < 2 {
        a = [k + 5, k + 6, k + 7];
        k += 1;
    }
    if (a[0] != 6 || a[2] != 8) { return 9; }
    return 0;
}
"""

REJECT = """module badagg;

struct Pair { x int; y int; }

// bad_struct：结构体局部聚合不在首片；必须带来源拒绝，不能静默回退。
fn bad_struct(x int) int {
    let q Pair = Pair{ x: 1, y: 2 };
    return q.x;
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
    """按 O0/O2 核对数组 lowering，并验证结构体仍被来源拒绝。"""
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
    source = WORK / "array.yh"
    source.write_text(SOURCE, encoding="utf-8")
    reject = WORK / "bad.yh"
    reject.write_text(REJECT, encoding="utf-8")

    for level in (0, 2):
        llfile = WORK / f"array-O{level}.ll"
        text = emit_text(compiler, source, level, llfile)
        # 数组存储/寻址/复制三件套必须在文本里真实出现。
        for token in ("= alloca i8", "getelementptr i8, ptr", "llvm.memcpy"):
            assert token in text, f"O{level} 文本缺少聚合 lowering 痕迹: {token}\n{text[-800:]}"
        verify = run([tools["opt"], "-passes=verify", "-S", str(llfile), "-o", os.devnull])
        assert verify.returncode == 0, f"O{level} opt 验证失败\n{verify.stderr[-1200:]}"
        obj_source = llfile
        if level == 2:
            optimized = WORK / "array-O2-opt.ll"
            result = run([tools["opt"], "-S", "-passes=default<O2>", str(llfile),
                          "-o", str(optimized)])
            assert result.returncode == 0, f"O2 管线失败\n{result.stderr[-1200:]}"
            obj_source = optimized
        obj = WORK / f"array-O{level}.o"
        result = run([tools["clang"], "-c", str(obj_source), "-o", str(obj)])
        assert result.returncode == 0, f"O{level} 汇编失败\n{result.stderr[-1200:]}"
        executable = WORK / f"array-O{level}"
        result = run([tools["cc"], "-no-pie", str(obj), "-o", str(executable)])
        assert result.returncode == 0, f"O{level} 链接失败\n{result.stderr[-1200:]}"
        result = run([str(executable)])
        assert result.returncode == 0, (
            f"O{level} 原生运行失败 rc={result.returncode}\n{result.stdout[-400:]}")

    # 结构体聚合仍不在首片：必须带来源位置拒绝，且不发布产物。
    output = WORK / "bad-out"
    result = run([compiler, "--backend", "llvm", "--target", TARGET, "-O0",
                  "-o", str(output), str(reject)])
    assert result.returncode != 0, "结构体聚合未被拒绝"
    assert ".yh:" in result.stderr and "聚合" in result.stderr, result.stderr[-800:]
    assert not output.exists(), "拒绝路径仍发布了产物"

    print("LL5 聚合首片通过：数组字面量/下标/取址/复制、O0/O2 原生运行、结构体带来源拒绝")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
