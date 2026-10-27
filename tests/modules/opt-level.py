#!/usr/bin/env python3
"""依赖项目优化级门（J6-L3）：依赖/标准库按 O2 发射，根项目仍用命令行值。

背景：yh 的链接粒度是「一个模块一个对象」，O0 会把整套 stdlib 实现带进
产物（实测 fmt 版 hello：`__text` 35.7 KB，依赖侧改 O2 后 12.5 KB）。本门
用当前编译器验证四条契约：

  1. 缺省（不设 YH_DEP_OPT）时，导入 fmt 的程序比 `YH_DEP_OPT=0` 更小；
  2. 两种配置的程序行为一致（stdout 逐字节相同）；
  3. 先构建 `YH_DEP_OPT=0` 再构建缺省，仍得到较小产物——证明优化级进入
     模块缓存键，没有命中旧对象；
  4. 没有任何依赖的项目在两种配置下产物大小一致——证明开关不触碰根项目
     （用户代码仍按命令行优化级发射，缺省 O0）。

usage: python3 tests/modules/opt-level.py [--compiler-path ./yh]
                                          [--workdir tmp/dep-opt]
退出码：全部通过 0；否则 1。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # tests/modules
ROOT = HERE.parent.parent
WORK = ROOT / "tmp" / "dep-opt"
EXPECTED = "n=42 s=hi\n"

MANIFEST = """[project]
os = "host"
arch = "host"
name = "{name}"
source = "src"
"""

# 依赖侧探针：一次打印同时走 fmt 的整数与字符串叶子。
DEP_MAIN = """module main

import fmt
import string

// view_of 把已知有效的 NUL 结尾文本转成视图。
fn view_of(text *char) string.View {
    let result string.ViewResult = string.view_cstr(text)
    return result.value
}

// main 打印一行后返回 0。
fn main() int {
    fmt.print([fmt.of_cstr("n="), fmt.of_int(42),
        fmt.of_cstr(" s="), fmt.of_str(view_of("hi")), fmt.of_cstr("\\n")])
    return 0
}
"""

# 根项目探针：不导入任何模块，优化级开关对它必须没有影响。
LEAF_MAIN = """module main

// main 只打印一行，不依赖标准库。
fn main() int {
    printf("n=42 s=hi\\n")
    return 0
}
"""


def require(condition, message):
    """报告确定性的门禁失败，避免依赖可被 -O 移除的 assert。"""
    if not condition:
        print(f"FAIL {message}")
        raise SystemExit(1)


def env_for(dep_opt):
    """构造构建环境；dep_opt=None 表示不设开关（走缺省）。"""
    env = dict(os.environ)
    env.pop("YH_DEP_OPT", None)
    env.setdefault("YH_STDLIB", str(ROOT / "libs"))
    if dep_opt is not None:
        env["YH_DEP_OPT"] = dep_opt
    return env


def write_project(base, name, main_text):
    """在工作目录里落一个最小项目，返回项目目录。"""
    project = base / name
    if project.exists():
        shutil.rmtree(project)
    (project / "src" / "main").mkdir(parents=True)
    (project / "project.toml").write_text(MANIFEST.format(name=name))
    (project / "src" / "main" / "main.yh").write_text(main_text)
    return project


def build(compiler, project, dep_opt):
    """构建项目，返回产物路径；失败直接判门禁失败。"""
    proc = subprocess.run([str(compiler), "build"], cwd=str(project),
                          capture_output=True, text=True, timeout=300,
                          env=env_for(dep_opt))
    require(proc.returncode == 0,
            f"{project.name} 构建失败（YH_DEP_OPT={dep_opt}）：{proc.stderr.strip()}")
    binary = project / ".build" / project.name
    require(binary.is_file(), f"{project.name} 未产出可执行文件")
    return binary


def run_binary(binary, label):
    """运行产物并比对 stdout。"""
    proc = subprocess.run([str(binary)], capture_output=True, text=True,
                          timeout=120)
    require(proc.returncode == 0, f"{label}：退出码 {proc.returncode}")
    require(proc.stdout == EXPECTED, f"{label}：stdout 不符（{proc.stdout!r}）")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--workdir", default=str(WORK))
    args = parser.parse_args()

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    compiler = Path(args.compiler_path).resolve()
    require(compiler.is_file(), f"编译器不存在：{compiler}")

    dep = write_project(workdir, "depapp", DEP_MAIN)
    optimized = build(compiler, dep, None)
    run_binary(optimized, "依赖缺省 O2")
    optimized_size = optimized.stat().st_size

    baseline = build(compiler, dep, "0")
    run_binary(baseline, "YH_DEP_OPT=0")
    baseline_size = baseline.stat().st_size
    require(optimized_size < baseline_size,
            f"依赖项目未按 O2 发射：缺省 {optimized_size} B 不小于 "
            f"YH_DEP_OPT=0 的 {baseline_size} B")
    print(f"PASS 依赖项目缺省 O2：{optimized_size} B < {baseline_size} B")

    # 关键顺序：先构建关闭态，再构建缺省态；后者必须重新发射依赖对象。
    again = build(compiler, dep, None)
    run_binary(again, "关闭态之后重建缺省态")
    again_size = again.stat().st_size
    require(again_size == optimized_size,
            f"缺省链接命中了关闭态缓存：{again_size} B != {optimized_size} B")
    print("PASS 优化级进入模块缓存键（0 → 缺省不复用旧对象）")

    leaf = write_project(workdir, "leafapp", LEAF_MAIN)
    leaf_default = build(compiler, leaf, None).stat().st_size
    leaf_off = build(compiler, leaf, "0").stat().st_size
    require(leaf_default == leaf_off,
            f"根项目受依赖开关影响：缺省 {leaf_default} B != {leaf_off} B")
    print("PASS 根项目不受依赖优化级影响（仍走命令行值）")

    print("结果: 4 passed; 0 failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
