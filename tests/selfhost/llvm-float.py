#!/usr/bin/env python3
"""LL6 浮点门：校验语义 lowering、LLVM IR 和 O0/O2 原生运行。"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp" / "llvm-migration" / "llvm-float"
SOURCE = ROOT / "tests" / "yh-run" / "run" / "llvm-float-lowering.yh"
TARGET = "x86_64-unknown-linux-gnu"


def run(command, **kwargs):
    """执行有界门禁命令并保留诊断文本。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=300, **kwargs)


def locate(name):
    """优先使用系统 LLVM 工具；它们只用于开发期 IR 验证与代码生成。"""
    fixed = Path("/usr/bin") / name
    if fixed.is_file():
        return str(fixed)
    return shutil.which(name)


def main():
    """对同一 `.yh` 输入分别发射、验证并原生运行 O0/O2。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    assert Path(compiler).is_file(), f"编译器不存在：{compiler}"
    clang, opt, cc = (locate(name) for name in ("clang", "opt", "gcc"))
    assert clang and opt and cc, "LL6 门缺少 clang/opt/gcc 开发工具"
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)

    for level in (0, 2):
        llfile = WORK / f"float-O{level}.ll"
        emitted = run([compiler, "--emit-asm", "--backend", "llvm", "--target", TARGET,
                       f"-O{level}", "--emit-llvm", str(SOURCE)])
        assert emitted.returncode == 0, (
            f"O{level} LLVM 发射失败\n{emitted.stderr[-1600:]}")
        llfile.write_text(emitted.stdout, encoding="utf-8")
        ir_text = emitted.stdout
        assert " fadd " in ir_text and " fmul " in ir_text and " fdiv " in ir_text, ir_text[-1600:]
        assert "fcmp " in ir_text and "fptrunc" in ir_text and "sitofp" in ir_text, ir_text[-1600:]
        assert "uitofp" in ir_text and "@llvm.fptosi.sat.i64.f64" in ir_text
        assert "@llvm.fptoui.sat.i64.f32" in ir_text and "load double, ptr" in ir_text
        assert "store double" in ir_text
        assert "fast" not in ir_text and "nnan" not in ir_text and "ninf" not in ir_text
        verified = run([opt, "-passes=verify", "-S", str(llfile), "-o", os.devnull])
        assert verified.returncode == 0, f"O{level} verifier 失败\n{verified.stderr[-1600:]}"

        compile_ir = llfile
        if level == 2:
            optimized = WORK / "float-O2-opt.ll"
            optimized_result = run([opt, "-S", "-passes=default<O2>", str(llfile),
                                    "-o", str(optimized)])
            assert optimized_result.returncode == 0, optimized_result.stderr[-1600:]
            compile_ir = optimized
        obj = WORK / f"float-O{level}.o"
        compiled = run([clang, "-c", str(compile_ir), "-o", str(obj)])
        assert compiled.returncode == 0, f"O{level} 汇编失败\n{compiled.stderr[-1600:]}"
        executable = WORK / f"float-O{level}"
        linked = run([cc, "-no-pie", str(obj), "-o", str(executable)])
        assert linked.returncode == 0, f"O{level} 链接失败\n{linked.stderr[-1600:]}"
        executed = run([str(executable)])
        assert executed.returncode == 0, (
            f"O{level} 运行失败 rc={executed.returncode}\n{executed.stderr[-800:]}")

    print("LL6 通过：浮点常量/算术/比较/转换/内存的 LLVM O0/O2 原生运行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
