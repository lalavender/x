#!/usr/bin/env python3
"""LL5 结构体切片门：字段、嵌套、字面量、复制与联合体共享存储。

验收（与实施方案 LL5 局部数据/副本切片对应）：
  * 结构体/联合体绑定 ALLOCA 字节存储；字段地址按快照字段表偏移走 GEP；
  * 结构体字面量逐字段写入（含嵌套字面量/结构体数组）；按值复制用 memmove；
  * 未初始化 `let`（标量/聚合）与联合体共享存储按旧后端语义工作；
  * O0 文本与 `default<O2>` 管线后的对象分别汇编、链接并原生运行；
  * 切片等尚未支持的聚合形态必须带来源拒绝。
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp" / "llvm-migration" / "llvm-struct"
TARGET = "x86_64-unknown-linux-gnu"

SOURCE = """module structcase;

pub union Val {
    i int;
    b u8;
}

struct Pair {
    x int;
    y int;
}

struct Box {
    inner Pair;
    tag int;
}

fn main() int {
    let p Pair = Pair{ x: 1, y: 2 };
    if (p.x != 1 || p.y != 2) { return 1; }
    p.x = 10;
    p.y += 5;
    if (p.x != 10 || p.y != 7) { return 2; }
    let q Pair = p;
    q.x = 99;
    if (p.x != 10 || q.x != 99) { return 3; }
    let pp *Pair = &p;
    (*pp).y = 42;
    if (p.y != 42) { return 4; }
    let b Box = Box{ inner: Pair{ x: 5, y: 6 }, tag: 7 };
    if (b.inner.x != 5 || b.inner.y != 6 || b.tag != 7) { return 5; }
    b.inner.x = 8;
    if (b.inner.x != 8 || b.inner.y != 6) { return 6; }
    let ep *int = &p.x;
    *ep = 21;
    if (p.x != 21) { return 7; }
    let arr [2]Pair = [Pair{ x: 1, y: 2 }, Pair{ x: 3, y: 4 }];
    if (arr[1].x != 3 || arr[0].y != 2) { return 8; }
    arr[0].x = 11;
    if (arr[0].x != 11 || arr[1].x != 3) { return 9; }
    let v Val;
    v.i = 258;
    if (v.b != 2) { return 10; }
    let uninit Pair;
    uninit.x = 4;
    if (uninit.x != 4) { return 11; }
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
    """按 O0/O2 核对结构体 lowering，并验证切片仍被来源拒绝。"""
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
    source = WORK / "struct.yh"
    source.write_text(SOURCE, encoding="utf-8")
    reject = WORK / "bad.yh"
    reject.write_text(REJECT, encoding="utf-8")

    for level in (0, 2):
        llfile = WORK / f"struct-O{level}.ll"
        text = emit_text(compiler, source, level, llfile)
        for token in ("= alloca i8", "getelementptr i8, ptr", "llvm.memmove"):
            assert token in text, f"O{level} 文本缺少结构体 lowering 痕迹: {token}\n{text[-800:]}"
        verify = run([tools["opt"], "-passes=verify", "-S", str(llfile), "-o", os.devnull])
        assert verify.returncode == 0, f"O{level} opt 验证失败\n{verify.stderr[-1200:]}"
        obj_source = llfile
        if level == 2:
            optimized = WORK / "struct-O2-opt.ll"
            result = run([tools["opt"], "-S", "-passes=default<O2>", str(llfile),
                          "-o", str(optimized)])
            assert result.returncode == 0, f"O2 管线失败\n{result.stderr[-1200:]}"
            obj_source = optimized
        obj = WORK / f"struct-O{level}.o"
        result = run([tools["clang"], "-c", str(obj_source), "-o", str(obj)])
        assert result.returncode == 0, f"O{level} 汇编失败\n{result.stderr[-1200:]}"
        executable = WORK / f"struct-O{level}"
        result = run([tools["cc"], "-no-pie", str(obj), "-o", str(executable)])
        assert result.returncode == 0, f"O{level} 链接失败\n{result.stderr[-1200:]}"
        result = run([str(executable)])
        assert result.returncode == 0, (
            f"O{level} 原生运行失败 rc={result.returncode}\n{result.stdout[-400:]}")

    # 切片仍不在首片：必须带来源位置拒绝，且不发布产物。
    output = WORK / "bad-out"
    result = run([compiler, "--backend", "llvm", "--target", TARGET, "-O0",
                  "-o", str(output), str(reject)])
    assert result.returncode != 0, "切片聚合未被拒绝"
    assert ".yh:" in result.stderr and "bad_forin" in result.stderr, result.stderr[-800:]
    assert not output.exists(), "拒绝路径仍发布了产物"

    print("LL5 结构体切片通过：字段/嵌套/字面量/复制/联合体、O0/O2 原生运行、切片带来源拒绝")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
