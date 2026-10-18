#!/usr/bin/env python3
"""LL5 切片门：数组切片、切片字面量、共享下标与运行期 len。

验收（与实施方案 LL5 切片共享/按值副本切片对应）：
  * 切片绑定为 16 字节头 {len u64, ptr *void} 的 ALLOCA；字面量后备数组
    在函数入口预分配、循环内复用；
  * `a[i..j]`/`s[i..j]`/`[..]` 字面量写入头部；`s[k]` 读写共享底层数组；
    切片副本按 16 字节 MEMCPY；`len(s)` 读头部长度；
  * O0 文本与 `default<O2>` 管线后的对象分别汇编、链接并原生运行；
  * 尚未支持的 `for-in` 带来源拒绝。
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp" / "llvm-migration" / "llvm-slice"
TARGET = "x86_64-unknown-linux-gnu"

SOURCE = """module slicecase;

fn main() int {
    let a [5]int = [1, 2, 3, 4, 5];
    let s []int = a[1..4];
    if (len(s) != 3) { return 1; }
    if (s[0] != 2 || s[2] != 4) { return 2; }
    s[1] = 30;
    if (a[2] != 30) { return 3; }
    let t []int = s;
    if (len(t) != 3 || t[1] != 30) { return 4; }
    t[0] = 99;
    if (a[1] != 99) { return 5; }
    let u []int = [7, 8, 9];
    if (len(u) != 3 || u[2] != 9) { return 6; }
    let v []int = u[1..3];
    if (len(v) != 2 || v[0] != 8 || v[1] != 9) { return 7; }
    let dyn int = 1;
    let w []int = a[dyn..4];
    if (len(w) != 3 || w[0] != 99) { return 8; }
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
    """按 O0/O2 核对切片 lowering，并验证 for-in 仍被来源拒绝。"""
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
    source = WORK / "slice.yh"
    source.write_text(SOURCE, encoding="utf-8")
    reject = WORK / "bad.yh"
    reject.write_text(REJECT, encoding="utf-8")

    for level in (0, 2):
        llfile = WORK / f"slice-O{level}.ll"
        text = emit_text(compiler, source, level, llfile)
        for token in ("= alloca i8", "getelementptr i8, ptr", "llvm.memmove"):
            assert token in text, f"O{level} 文本缺少切片 lowering 痕迹: {token}\n{text[-800:]}"
        verify = run([tools["opt"], "-passes=verify", "-S", str(llfile), "-o", os.devnull])
        assert verify.returncode == 0, f"O{level} opt 验证失败\n{verify.stderr[-1200:]}"
        obj_source = llfile
        if level == 2:
            optimized = WORK / "slice-O2-opt.ll"
            result = run([tools["opt"], "-S", "-passes=default<O2>", str(llfile),
                          "-o", str(optimized)])
            assert result.returncode == 0, f"O2 管线失败\n{result.stderr[-1200:]}"
            obj_source = optimized
        obj = WORK / f"slice-O{level}.o"
        result = run([tools["clang"], "-c", str(obj_source), "-o", str(obj)])
        assert result.returncode == 0, f"O{level} 汇编失败\n{result.stderr[-1200:]}"
        executable = WORK / f"slice-O{level}"
        result = run([tools["cc"], "-no-pie", str(obj), "-o", str(executable)])
        assert result.returncode == 0, f"O{level} 链接失败\n{result.stderr[-1200:]}"
        result = run([str(executable)])
        assert result.returncode == 0, (
            f"O{level} 原生运行失败 rc={result.returncode}\n{result.stdout[-400:]}")

    # for-in 仍不在已验收范围：必须带来源位置拒绝，且不发布产物。
    output = WORK / "bad-out"
    result = run([compiler, "--backend", "llvm", "--target", TARGET, "-O0",
                  "-o", str(output), str(reject)])
    assert result.returncode != 0, "for-in 未被拒绝"
    assert ".yh:" in result.stderr and "bad_forin" in result.stderr, result.stderr[-800:]
    assert not output.exists(), "拒绝路径仍发布了产物"

    print("LL5 切片通过：数组切片/字面量/共享读写/副本/len、O0/O2 原生运行、for-in 带来源拒绝")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
