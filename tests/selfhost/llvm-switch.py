#!/usr/bin/env python3
"""LL4 switch 门：多值 case/default、无 fallthrough、嵌套与循环内 break。

验收（与实施方案 LL4 的 switch 行对应）：
  * switch 控制值只求值一次，case 常量比较链生成分支 CFG，各体块无 fallthrough；
  * 贯穿路径在退出块用 N 元 phi 合流，循环内赋值仍参与循环携带；
  * O0 文本与 `default<O2>` 管线后的对象分别汇编、链接并原生运行，退出码 0；
  * 非编译期常量的 case 值必须带来源拒绝。
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp" / "llvm-migration" / "llvm-switch"
TARGET = "x86_64-unknown-linux-gnu"

SOURCE = """module switchcase;

// pick：多值 case 与 default，各分支直接 return。
fn pick(v int) int {
    switch v {
        case 1 { return 10; }
        case 2, 3 { return 20; }
        default { return 30; }
    }
    return 99;
}

fn main() int {
    if (pick(1) != 10) { return 1; }
    if (pick(2) != 20) { return 2; }
    if (pick(3) != 20) { return 3; }
    if (pick(9) != 30) { return 4; }
    let x int = 2;
    let r int = 0;
    switch x {
        case 2 { r = 5; }
        default { r = 7; }
    }
    if (r != 5) { return 5; }
    let total int = 0;
    let i int = 0;
    for i < 5 {
        switch i {
            case 0 { total += 1; }
            case 1, 2 { total += 10; }
            default { total += 100; }
        }
        i += 1;
    }
    if (total != 221) { return 6; }
    let k int = 0;
    let seen int = 0;
    for k < 10 {
        switch k {
            case 3 { break; }
            default { seen += 1; }
        }
        k += 1;
    }
    if (seen != 3 || k != 3) { return 7; }
    let n int = 0;
    let j int = 0;
    for j < 3 {
        switch j {
            case 0 {
                switch j + 5 {
                    case 5 { n += 5; }
                    default { n += 50; }
                }
            }
            default { n += 100; }
        }
        j += 1;
    }
    if (n != 205) { return 8; }
    return 0;
}
"""

REJECT = """module bad;

// bad_case：case 值必须是编译期常量；变量必须带来源拒绝。
fn bad_case(x int) int {
    let c int = 1;
    switch x {
        case c { return 1; }
        default { return 0; }
    }
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
    """按 O0/O2 核对 switch lowering，并验证非常量 case 被拒绝。"""
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
    source = WORK / "switch.yh"
    source.write_text(SOURCE, encoding="utf-8")
    reject = WORK / "bad.yh"
    reject.write_text(REJECT, encoding="utf-8")

    for level in (0, 2):
        llfile = WORK / f"switch-O{level}.ll"
        text = emit_text(compiler, source, level, llfile)
        # case 比较链必须真的生成条件分支与合流 phi。
        assert text.count("icmp eq ") >= 4, f"O{level} 文本缺少 case 比较\n{text[-800:]}"
        assert text.count("phi ") >= 2, f"O{level} 文本缺少合流 phi\n{text[-800:]}"
        verify = run([tools["opt"], "-passes=verify", "-S", str(llfile), "-o", os.devnull])
        assert verify.returncode == 0, f"O{level} opt 验证失败\n{verify.stderr[-1200:]}"
        obj_source = llfile
        if level == 2:
            optimized = WORK / "switch-O2-opt.ll"
            result = run([tools["opt"], "-S", "-passes=default<O2>", str(llfile),
                          "-o", str(optimized)])
            assert result.returncode == 0, f"O2 管线失败\n{result.stderr[-1200:]}"
            obj_source = optimized
        obj = WORK / f"switch-O{level}.o"
        result = run([tools["clang"], "-c", str(obj_source), "-o", str(obj)])
        assert result.returncode == 0, f"O{level} 汇编失败\n{result.stderr[-1200:]}"
        executable = WORK / f"switch-O{level}"
        result = run([tools["cc"], "-no-pie", str(obj), "-o", str(executable)])
        assert result.returncode == 0, f"O{level} 链接失败\n{result.stderr[-1200:]}"
        result = run([str(executable)])
        assert result.returncode == 0, (
            f"O{level} 原生运行失败 rc={result.returncode}\n{result.stdout[-400:]}")

    # 非常量 case 值必须带来源位置拒绝，且不发布产物。
    output = WORK / "bad-out"
    result = run([compiler, "--backend", "llvm", "--target", TARGET, "-O0",
                  "-o", str(output), str(reject)])
    assert result.returncode != 0, "非常量 case 未被拒绝"
    assert ".yh:" in result.stderr and "编译期常量" in result.stderr, result.stderr[-800:]
    assert not output.exists(), "拒绝路径仍发布了产物"

    print("LL4 switch 通过：多值 case/default、无 fallthrough、嵌套/循环合流、O0/O2 原生运行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
