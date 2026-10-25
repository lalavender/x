#!/usr/bin/env python3
"""string 标准库专项门（ST1–ST6）。

用 tests/modules/projects/string* 真实项目 fixture 验证 View、切分、拥有者、
变换、UTF-8 与 TOML 互操作。普通组把 fixture 复制到 --workdir 后执行
`yh run`；resources 组把标准库复制到 --workdir，逐次改写
`STRING_TEST_FAIL_AFTER` 注入分配失败，再构建一次 fixture 并逐个场景运行。

usage: python3 tests/string/run.py [--compiler ./yh] [--stdlib ./libs]
                                  [--workdir tmp/string-test]
                                  [--group model,interop,resources|all]
                                  [--opt-level 0|2]

退出码：全部通过 0；构建失败、断言失败、超时或注入矩阵不完整均为 1。
不向原 fixture 写 .build，不联网下载。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PROJ = ROOT / "tests" / "modules" / "projects"

# 组名 -> (fixture 目录, 成功输出行)。resources 单独处理。
GROUPS = {
    # view/owned/transform/utf8 的断言已迁入 libs/string/99_tests.yh；
    # model 与 interop 保留为公开面/跨库消费者 smoke。
    "model": ("stringmodel", "string model ok\n"),
    "interop": ("stringinterop", "string interop ok\n"),
}

# 失败注入场景号 -> 名称；0..9 覆盖数据/状态分配点与主要增长路径。
RESOURCE_SCENARIOS = {
    0: "from_view",
    1: "append_grow",
    2: "assign_grow",
    3: "clone",
    4: "concat",
    5: "replace",
    6: "join",
    7: "append_rune",
    8: "reserve",
    9: "append_byte",
}

# 测试副本中要改写的常量；产品源码保持 -1。
FAIL_CONST_RE = re.compile(r"const STRING_TEST_FAIL_AFTER int = -?\d+")


def run(cmd, cwd, env, timeout):
    """运行命令并返回 CompletedProcess；超时视为失败。"""
    try:
        return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(
            cmd, 124, error.stdout or "", (error.stderr or "") + "\n[timeout]")


def copy_fixture(fixture, destination):
    """复制 fixture 到工作目录，并清掉可能残留的 .build。"""
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(PROJ / fixture, destination,
                    ignore=shutil.ignore_patterns(".build"))
    build = destination / ".build"
    if build.exists():
        shutil.rmtree(build)
    return destination


def copy_stdlib(stdlib, destination):
    """复制标准库用于注入；不把仓库里的 .build 带进临时副本。"""
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(stdlib, destination,
                    ignore=shutil.ignore_patterns(".build", "__pycache__"))
    return destination


def set_fail_after(stdlib_copy, value):
    """把标准库副本的注入常量改成 value；找不到常量直接失败。"""
    target = stdlib_copy / "string" / "00_model.yh"
    text = target.read_text()
    updated, count = FAIL_CONST_RE.subn(
        f"const STRING_TEST_FAIL_AFTER int = {value}", text)
    if count != 1:
        raise RuntimeError(f"{target} 中未找到唯一的 STRING_TEST_FAIL_AFTER 常量")
    target.write_text(updated)


def check_group(name, fixture, success_line, compiler, stdlib, workdir,
                opt_level):
    """普通组：复制 fixture，执行 yh run，检查退出码与成功行。"""
    destination = copy_fixture(fixture, workdir / name)
    env = dict(os.environ)
    env["YH_STDLIB"] = str(stdlib)
    result = run([str(compiler), f"-O{opt_level}", "run"], destination, env, 1800)
    if result.returncode != 0 or not result.stdout.endswith(success_line):
        print(f"FAIL {name}: rc={result.returncode} "
              f"stdout={result.stdout[-200:]!r} stderr={result.stderr[-400:]!r}")
        return False
    print(f"PASS {name}")
    return True


def check_resources(compiler, stdlib, workdir, opt_level):
    """resources：逐次注入分配失败，验证失败原子性并覆盖成功路径。"""
    base = workdir / "resources"
    stdlib_copy = copy_stdlib(stdlib, base / "stdlib")
    observations = {scenario: {"failed": 0, "ok": 0, "setup": 0}
                    for scenario in RESOURCE_SCENARIOS}
    env = dict(os.environ)
    env["YH_STDLIB"] = str(stdlib_copy)
    ok = True
    # 0..7 覆盖所有场景：append_grow 前置 4 次分配，第 4/5 次注入失败，
    # 第 6 次成功；其余场景在 0..4 内覆盖失败与成功。
    for fail_after in range(0, 8):
        set_fail_after(stdlib_copy, fail_after)
        fixture = copy_fixture("stringresources", base / f"n{fail_after}")
        built = run([str(compiler), f"-O{opt_level}", "build"], fixture, env, 1800)
        if built.returncode != 0:
            print(f"FAIL resources n={fail_after}: build rc={built.returncode}\n"
                  f"{built.stderr[-600:]}")
            ok = False
            continue
        binary = fixture / ".build" / "example_stringresources"
        if not binary.exists():
            print(f"FAIL resources n={fail_after}: 缺少产物 {binary}")
            ok = False
            continue
        for scenario in RESOURCE_SCENARIOS:
            result = run([str(binary), str(scenario)], fixture, env, 60)
            if result.returncode == 99:
                observations[scenario]["setup"] += 1
                continue
            if result.returncode != 0:
                print(f"FAIL resources n={fail_after} scenario={scenario}"
                      f"({RESOURCE_SCENARIOS[scenario]}): rc={result.returncode} "
                      f"stdout={result.stdout[-200:]!r} stderr={result.stderr[-400:]!r}")
                ok = False
                continue
            line = result.stdout.strip()
            if line == "failed":
                observations[scenario]["failed"] += 1
            elif line == "ok":
                observations[scenario]["ok"] += 1
            else:
                print(f"FAIL resources n={fail_after} scenario={scenario}"
                      f"({RESOURCE_SCENARIOS[scenario]}): 未知输出 {line!r}")
                ok = False
    for scenario, counts in observations.items():
        if counts["failed"] == 0 or counts["ok"] == 0:
            print(f"FAIL resources scenario={scenario}"
                  f"({RESOURCE_SCENARIOS[scenario]}): 注入矩阵不完整 {counts}")
            ok = False
    if ok:
        print("PASS resources")
    return ok


def parse_args(argv):
    parser = argparse.ArgumentParser(description="string 标准库专项门")
    parser.add_argument("--compiler", default="./yh", help="yh 编译器路径")
    parser.add_argument("--stdlib", default=str(ROOT / "libs"),
                        help="标准库根（libs/）")
    parser.add_argument("--workdir", default=str(ROOT / "tmp" / "string-test"),
                        help="临时工作目录")
    parser.add_argument("--group", default="all",
                        help="逗号分隔组名或 all：model,interop,"
                             "utf8,interop,resources")
    parser.add_argument("--opt-level", default="0", choices=("0", "2"),
                        help="优化级别 0 或 2")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    compiler = Path(args.compiler).resolve()
    stdlib = Path(args.stdlib).resolve()
    workdir = Path(args.workdir).resolve()
    if not compiler.exists():
        print(f"FAIL 编译器不存在: {compiler}")
        return 1
    if not (stdlib / "string").is_dir():
        print(f"FAIL 标准库缺少 string 模块: {stdlib}")
        return 1
    workdir.mkdir(parents=True, exist_ok=True)

    if args.group == "all":
        selected = ["model", "interop", "resources"]
    else:
        selected = [item.strip() for item in args.group.split(",")
                    if item.strip()]
    unknown = [item for item in selected
               if item not in GROUPS and item != "resources"]
    if unknown:
        print(f"FAIL 未知组: {', '.join(unknown)}")
        return 1
    if not selected:
        print("FAIL 未选择任何组")
        return 1

    ok = True
    for name in selected:
        if name == "resources":
            ok = check_resources(compiler, stdlib, workdir, args.opt_level) and ok
        else:
            fixture, success = GROUPS[name]
            ok = check_group(name, fixture, success, compiler, stdlib, workdir,
                             args.opt_level) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
