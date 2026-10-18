#!/usr/bin/env python3
"""LL5 前端门：真实 .yh 全局初始化经 LLVM 重定位/O0/O2 后运行。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests/yh-run/run/llvm-global-data.yh"
WORK = ROOT / "tmp/ll5-complete/global-data"
TARGET = "x86_64-unknown-linux-gnu"


def run(command):
    """执行候选编译器或 LLVM 工具，保留完整标准输出以便失败时定位。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=300)


def main():
    """直接从前端发射全局数据，验证重定位文本并运行优化前后产物。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    clang = "/usr/bin/clang"
    cc = "/usr/bin/gcc"
    opt = "/usr/bin/opt-21"
    assert Path(clang).is_file() and Path(cc).is_file() and Path(opt).is_file(), (
        "缺少 LLVM O0/O2 验证与本机链接工具")
    compiler = str(Path(args.compiler_path).resolve())
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    # 前端语料中的 printf 只供旧后端输出断言；LLVM 首片不接入可变参数调用，
    # 这里移除该状态行，以退出码验证同一段全局数据语义。
    source = WORK / "global-data-input.yh"
    source_text = SOURCE.read_text(encoding="utf-8")
    source_text = source_text.replace('    printf("global-data=ok\\n");\n', "")
    field_check = "        || text.label[0] != 110\n"
    assert field_check in source_text, "全局结构体字段检查行已变化"
    source_text = source_text.replace(
        field_check, "        || text.value != 9 || text.label[0] != 110\n", 1)
    source.write_text(source_text, encoding="utf-8")

    for level in (0, 2):
        emitted = run([compiler, "--emit-asm", "--backend", "llvm", "--target", TARGET,
                       f"-O{level}", "--emit-llvm", str(source)])
        assert emitted.returncode == 0, (
            f"O{level} 全局数据发射失败\n{emitted.stdout[-1000:]}\n{emitted.stderr[-1800:]}")
        irfile = WORK / f"global-data-O{level}.ll"
        irfile.write_text(emitted.stdout, encoding="utf-8")
        assert "getelementptr (i8, ptr @\"" in emitted.stdout, emitted.stdout
        view = re.search(r'^@"ct_view" = .*ptr getelementptr \(i8, ptr @"([^\"]+)", i64 0\)',
                         emitted.stdout, re.MULTILINE)
        assert view, "CT 返回切片应重定位到独立 backing"
        backing = f'@"{view.group(1)}" = internal global [12 x i8] '
        assert backing in emitted.stdout and (
            'c"\\15\\00\\00\\00\\16\\00\\00\\00\\17\\00\\00\\00"'
            in emitted.stdout), "CT 切片 backing 应保存返回视图的三个元素"
        text_global = next((line for line in emitted.stdout.splitlines()
                            if line.startswith('@"text" = ')), "")
        assert '[8 x i8] c"\\09\\00\\00\\00\\00\\00\\00\\00"' in text_global, (
            "结构体整数字段应按目标字段偏移写入全局对象")
        assert '@"global-data"' not in emitted.stdout, "源文件标签不应成为 LLVM 全局对象"
        verified = run(["/usr/bin/opt-21", "-passes=verify", "-disable-output", str(irfile)])
        assert verified.returncode == 0, f"O{level} LLVM verifier 失败\n{verified.stderr}"

        object_input = irfile
        if level == 2:
            optimized = WORK / "global-data-O2-optimized.ll"
            optimized_result = run([opt, "-S", "-passes=default<O2>", str(irfile),
                                    "-o", str(optimized)])
            assert optimized_result.returncode == 0, (
                f"O2 优化失败\n{optimized_result.stderr[-1200:]}")
            object_input = optimized
        obj = WORK / f"global-data-O{level}.o"
        assembled = run([clang, "-c", str(object_input), "-o", str(obj)])
        assert assembled.returncode == 0, (
            f"O{level} LLVM 汇编失败\n{assembled.stderr[-1200:]}")
        executable = WORK / f"global-data-O{level}"
        linked = run([cc, "-no-pie", str(obj), "-o", str(executable)])
        assert linked.returncode == 0, (
            f"O{level} 全局数据链接失败\n{linked.stderr[-1200:]}")
        result = run([str(executable)])
        assert result.returncode == 0 and result.stdout == "", (
            f"O{level} 全局数据运行失败 rc={result.returncode}\n"
            f"{result.stdout}\n{result.stderr[-1000:]}")

    print("LL5 全局前端通过：CT/字面切片 backing、切片共享、字符串重定位与布局、O0/O2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
