#!/usr/bin/env python3
"""F2-2 Darwin/ARM64 LLVM 首对象门：文本、O0/O2 Mach-O 与部署版本。"""

import os
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests/yh-run/run/llvm-darwin-object.yh"
PROJECT_FIXTURE = ROOT / "tests/modules/projects/llvmdarwinlink"
WORK = ROOT / "tmp/llvm-migration/darwin-object"
TRIPLE = "aarch64-apple-darwin"
LAYOUT = "e-m:o-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-n32:64-S128-Fn32"


def require(condition, message):
    """报告明确失败原因，避免依赖可被 Python -O 关闭的 assert。"""
    if not condition:
        raise RuntimeError(message)


def run(label, command, env=None, cwd=ROOT):
    """保存每条真实命令的输出，失败时返回完整结果供报告诊断。"""
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                            text=True, timeout=120)
    (WORK / f"{label}.stdout").write_text(result.stdout, encoding="utf-8")
    (WORK / f"{label}.stderr").write_text(result.stderr, encoding="utf-8")
    return result


def main():
    """经当前 yh 驱动生成 IR、Mach-O 对象与汇编，并验收最低系统版本。"""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--min-os", default="14.0.0")
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    WORK.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["MACOSX_DEPLOYMENT_TARGET"] = args.min_os

    check_env = env.copy()
    check_env["MACOSX_DEPLOYMENT_TARGET"] = "bad-version"
    check_env["SDKROOT"] = str(WORK / "missing-sdk")
    check = run("check-without-sdk", [str(compiler), "--backend", "llvm",
        "--target", TRIPLE, "check", str(SOURCE)], check_env)
    require(check.returncode == 0, "check 模式意外依赖 Darwin SDK 或部署版本")

    text = run("ir", [str(compiler), "--backend", "llvm", "--target", TRIPLE,
                       "--emit-llvm", "--emit-asm", str(SOURCE)], env)
    require(text.returncode == 0, f"Darwin LLVM IR 发射失败：{text.stderr[-3000:]}")
    require(f'target triple = "{TRIPLE}"' in text.stdout, "LLVM 文本目标 triple 不符")
    require(f'target datalayout = "{LAYOUT}"' in text.stdout,
            "LLVM 文本目标数据布局不符")
    min_parts = tuple(map(int, args.min_os.split(".")))
    canonical_min = ".".join(str(value) for value in
                              min_parts + (0,) * (3 - len(min_parts)))
    require(f"; yh-macos-min-os = {canonical_min}" in text.stdout,
            "LLVM 文本没有记录规范化 macOS 部署版本")
    require('define internal i64 @"adjust$yhllvmv1"' in text.stdout,
            "内部函数逻辑符号被意外加上 Darwin 前导下划线")
    require("alloca" in text.stdout and "br i1" in text.stdout,
            "纯整数探针没有覆盖局部内存和条件分支")
    require("syscall" not in text.stdout, "Darwin 纯计算模块混入 Linux syscall 模板")

    rejected = run("darwin-x64", [str(compiler), "--backend", "llvm",
        "--target", "x86_64-apple-darwin", "--emit-llvm", "--emit-asm", str(SOURCE)], env)
    require(rejected.returncode != 0 and "平台尚不支持" in rejected.stderr,
            "Darwin/x64 错误地进入首期 ARM64 emitter")
    rejected = run("unknown-target", [str(compiler), "--backend", "llvm",
        "--target", "aarch64-apple-unknown", "--emit-asm", str(SOURCE)], env)
    require(rejected.returncode != 0, "未识别的 Darwin triple 没有被拒绝")

    invalid_version = env.copy()
    invalid_version["MACOSX_DEPLOYMENT_TARGET"] = "14..0"
    rejected = run("invalid-min-os", [str(compiler), "--backend", "llvm",
        "--target", TRIPLE, "--emit-llvm", "--emit-asm", str(SOURCE)], invalid_version)
    require(rejected.returncode != 0 and "MACOSX_DEPLOYMENT_TARGET" in rejected.stderr,
            "非法部署版本未在发射前明确拒绝")

    invalid_sdk = env.copy()
    invalid_sdk["SDKROOT"] = str(WORK / "missing-sdk")
    rejected = run("explicit-sdkroot", [str(compiler), "--backend", "llvm",
        "--target", TRIPLE, "--emit-llvm", "--emit-asm", str(SOURCE)], invalid_sdk)
    require(rejected.returncode != 0 and "SDKROOT" in rejected.stderr,
            "显式 SDKROOT 无效时没有优先拒绝该值")

    # emit-only 只依赖 minOS，不得因为未安装 SDK 而失败；同时目标门仍应在
    # 后端拒绝 Linux syscall，而不是先报交叉链接缺 SDK。
    no_sdk = env.copy()
    no_sdk.pop("SDKROOT", None)
    no_sdk.pop("MACOSX_DEPLOYMENT_TARGET", None)
    emitted = run("no-sdk-asm", [str(compiler), "--backend", "llvm",
        "--target", TRIPLE, "--emit-asm", str(SOURCE)], no_sdk)
    require(emitted.returncode == 0 and "_main:" in emitted.stdout,
            f"无 SDK 的 Darwin emit-asm 失败：{emitted.stderr[-2000:]}")
    linux_syscall = ROOT / "tests/modules/projects/linuxsyscall/main.linux.x64.yh"
    gated = run("no-sdk-target-gate", [str(compiler), "--backend", "llvm",
        "--target", TRIPLE, "--emit-asm", str(linux_syscall)], no_sdk)
    require(gated.returncode != 0 and "未声明" in gated.stderr,
            "Darwin 目标门被 SDK 查找抢先拒绝："
            f"rc={gated.returncode}\n{gated.stderr[-2000:]}")

    for opt in ("-O0", "-O2"):
        project = WORK / f"object-project-{opt[2:]}"
        if project.exists():
            shutil.rmtree(project)
        shutil.copytree(PROJECT_FIXTURE, project)
        result = run(f"object-{opt[2:]}", [str(compiler), "--backend", "llvm",
            "--target", TRIPLE, opt, "build"], env, cwd=project)
        obj = project / ".build/targets/aarch64-apple-darwin/llvm" / opt[1:] / "obj/llvmdarwinlink-main.o"
        require(result.returncode == 0 and obj.is_file(),
                f"{opt} 项目没有发布 Darwin 模块对象：{result.stderr[-3000:]}")
        info = run(f"file-{opt[2:]}", ["file", str(obj)])
        require(info.returncode == 0 and "Mach-O 64-bit object arm64" in info.stdout,
                f"{opt} 输出不是 arm64 Mach-O 对象：{info.stdout.strip()}")

        result = run(f"assembly-{opt[2:]}", [str(compiler), "--backend", "llvm",
            "--target", TRIPLE, opt, "--emit-asm", str(SOURCE)], env)
        require(result.returncode == 0 and result.stdout,
                f"{opt} Darwin 汇编发射失败：{result.stderr[-3000:]}")
        asm_text = result.stdout
        require("_main:" in asm_text and "__main:" not in asm_text,
                f"{opt} Darwin main 外部符号没有由 LLVM 恰好添加一次前导下划线")
        if opt == "-O0":
            require("_adjust$yhllvmv1:" in asm_text,
                    "O0 内部函数没有按 yh LLVM ABI 名称发射")

        load = run(f"load-command-{opt[2:]}", ["otool", "-l", str(obj)])
        require(load.returncode == 0 and "LC_BUILD_VERSION" in load.stdout,
                f"{opt} 对象没有 LC_BUILD_VERSION：{load.stderr[-2000:]}")
        match = re.search(r"\bminos\s+(\d+(?:\.\d+){1,2})", load.stdout)
        actual_min = tuple(map(int, match.group(1).split("."))) if match else ()
        expected_min = tuple(map(int, args.min_os.split(".")))
        actual_min += (0,) * (3 - len(actual_min))
        expected_min += (0,) * (3 - len(expected_min))
        require(match is not None and actual_min == expected_min,
                f"{opt} 对象最低系统版本与会话配置不符")

        before_min_change = hashlib.sha256(obj.read_bytes()).digest()
        changed_min = env.copy()
        changed_min["MACOSX_DEPLOYMENT_TARGET"] = "15.0.0"
        rebuilt = run(f"object-min-os-change-{opt[2:]}", [str(compiler), "--backend", "llvm",
            "--target", TRIPLE, opt, "build"], changed_min, cwd=project)
        require(rebuilt.returncode == 0,
                f"{opt} 改变部署版本后项目重建失败：{rebuilt.stderr[-3000:]}")
        after_min_change = hashlib.sha256(obj.read_bytes()).digest()
        require(after_min_change != before_min_change,
                f"{opt} 改变 MACOSX_DEPLOYMENT_TARGET 后错误命中旧对象缓存")
        changed_load = run(f"load-command-min-os-change-{opt[2:]}",
                           ["otool", "-l", str(obj)])
        changed_match = re.search(r"\bminos\s+(\d+(?:\.\d+){1,2})",
                                  changed_load.stdout)
        changed_min_parts = tuple(map(int, changed_match.group(1).split("."))) \
            if changed_match else ()
        changed_min_parts += (0,) * (3 - len(changed_min_parts))
        require(changed_load.returncode == 0 and changed_min_parts == (15, 0, 0),
                f"{opt} 重建对象没有采用新的 macOS 部署版本")

    print("PASS Darwin/ARM64 LLVM 首对象门：IR、O0/O2 Mach-O、汇编与部署版本")


if __name__ == "__main__":
    main()
