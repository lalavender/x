#!/usr/bin/env python3
"""用上一代 yh 在默认配置下冷编项目（可选：把静态 LLVM 桥链进产物）。

默认行为与旧路径完全一致：直接执行 `<种子> build -o <输出>`。
给出 --llvm-host 时，按宿主选择 Linux 或 Darwin 链接包装器，并把它的目录
前置到种子的 PATH、通过 YH_CC 显式绑定驱动，使种子内部最终链接
（compiler/cmd/link_cache.yh 的 mb_link）自动链入内嵌桥与静态 LLVM。

LLVM 不是构建的失败点：--llvm-mode auto（默认）下任何缺失都只打印一条
明确诊断，然后按原路径继续构建；只有显式 --llvm-mode require 才让准备
失败中止构建。这样旧路径全门（make test / make selfhost-native）不受影响。
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST_DRIVERS = {
    "darwin-aarch64": ROOT / "tools/llvm-darwin-host.py",
    "linux-x86_64": ROOT / "tools/llvm-host.py",
    "linux-aarch64": ROOT / "tools/llvm-host.py",
}


def llvm_shim(host: str, mode: str) -> Path | None:
    """请求链接包装器目录；不可用时按模式返回 None 或抛错。

    返回值是包装器所在目录（内含名为 gcc 的包装器），调用方把它前置到
    子进程 PATH。失败信息取自驱动自身的 stderr，保证诊断里带着
    「缺什么」与「下一步跑什么命令」。
    """
    if mode == "off":
        print(f"提示：YH_LLVM_HOST=0，本次不接入内嵌 LLVM 桥（{host}）", file=sys.stderr)
        return None
    host_driver = HOST_DRIVERS[host]
    request = [sys.executable, str(host_driver), "shim", "--host", host,
               "--mode", "require" if mode == "require" else "auto"]
    result = subprocess.run(request, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"退出码 {result.returncode}"
        if mode == "require":
            raise RuntimeError(f"显式要求链入内嵌 LLVM 桥，但准备失败：{detail}")
        print(f"警告：本次未链入内嵌 LLVM 桥，按原路径（系统 cc）构建。\n{detail}",
              file=sys.stderr)
        return None
    record = json.loads([line for line in result.stdout.splitlines() if line.strip()][-1])
    sdk_identity = record.get("sdk_sha256", record.get("sdk_host_sha256", "unknown"))
    print(f"内嵌 LLVM 桥已接入链接：host={record['host']} "
          f"bridge={record['bridge_sha256'][:12]} sdk={sdk_identity[:12]} "
          f"shim={record['shim_dir']}", file=sys.stderr)
    return Path(record["shim_dir"])


def main() -> int:
    """解析参数、按需准备包装器，然后用种子冷编项目。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--backend", choices=("legacy", "llvm"),
                        help="显式选择构建候选时使用的后端")
    parser.add_argument("--target", help="候选编译器的目标 triple")
    parser.add_argument("--opt-level", choices=("0", "2"),
                        help="LLVM 候选优化级别")
    parser.add_argument("--emit-llvm", action="store_true",
                        help="同时保存每个模块的 LLVM 文本")
    parser.add_argument("--stats", action="store_true",
                        help="输出受检/发射/回退统计")
    parser.add_argument("--llvm-host", choices=tuple(HOST_DRIVERS),
                        help="把静态 LLVM 桥链入产物的宿主架构；缺省不接入")
    parser.add_argument("--llvm-mode", choices=("auto", "require", "off"), default="auto",
                        help="auto：缺失只警告并回退；require：缺失即构建失败；off：不接入")
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve()
    project = Path(args.project).resolve()
    output = Path(args.output).resolve()
    environment = dict(os.environ)
    # 只有构建 compiler/ 自身才把固定桥/LLVM 闭包注入最终链接；普通项目
    # 不能继承该标记，否则会把 LLVM 静态库链进用户程序。
    if project == (ROOT / "compiler").resolve():
        environment["YH_LLVM_SELFHOST"] = "1"
    if args.llvm_host:
        shim = llvm_shim(args.llvm_host, args.llvm_mode)
        if shim:
            environment["PATH"] = str(shim) + os.pathsep + environment.get("PATH", "")
            # LLVM x64 target 会选择 /usr/bin/gcc 绕过 PATH；显式绑定同一 shim，
            # 让过渡种子可链接出目标机型正确且含固定桥的候选编译器。
            compiler_shim = "clang" if args.llvm_host == "darwin-aarch64" else "gcc"
            environment["YH_CC"] = str(shim / compiler_shim)
    command = [str(compiler)]
    if args.backend:
        command += ["--backend", args.backend]
    if args.target:
        command += ["--target", args.target]
    if args.opt_level:
        command += [f"-O{args.opt_level}"]
    if args.emit_llvm:
        command.append("--emit-llvm")
    if args.stats:
        command.append("--stats")
    command += ["build", "-o", str(output)]
    result = subprocess.run(command, cwd=project, check=False, env=environment)
    return result.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"seed-build：{error}", file=sys.stderr)
        sys.exit(1)
