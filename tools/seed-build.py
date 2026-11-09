#!/usr/bin/env python3
"""用上一代 yh 在默认配置下冷编项目（可选：把静态 LLVM 桥链进产物）。

默认行为与旧路径完全一致：直接执行 `<种子> build -o <输出>`。
给出 --llvm-host 时，按宿主选择 Linux 或 Darwin 链接包装器，并把它的目录
前置到种子的 PATH、通过 YH_CC 显式绑定驱动，使种子内部最终链接
（compiler/cmd/link_cache.yh 的 mb_link）自动链入内嵌桥与静态 LLVM。

LLVM 不是构建的失败点：--llvm-mode auto（默认）下任何缺失都只打印一条
明确诊断，然后按原路径继续构建；只有显式 --llvm-mode require 才让准备
失败中止构建。这样旧路径全门（just test / just selfhost-native）不受影响。
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from llvm_cache import cache_root  # noqa: E402  闭包根唯一定义处（项目外）
HOST_DRIVERS = {
    "darwin-aarch64": ROOT / "tools/llvm-darwin-host.py",
    "linux-x86_64": ROOT / "tools/llvm-host.py",
    "linux-aarch64": ROOT / "tools/llvm-host.py",
    "windows-x86_64": ROOT / "tools/llvm-windows-host.py",
}


def ensure_closure_path() -> None:
    """把仓库内的兼容路径桥到项目外缓存；已就绪时**什么都不做**。

    0.0.13 种子还不支持清单里的 `${...}` 展开，所以 `compiler/project.toml` 仍写
    `../tmp/llvm-migration/...`。这里只在缺失时建软链，缓存数据本身位于项目外
    （`tools/llvm_cache.py` 的默认位置），仓库里只留一个指针。
    """
    target = cache_root()
    link = ROOT / "tmp/llvm-migration"
    if link.is_symlink():
        try:
            if link.resolve() == target:
                return
        except OSError:
            pass
    if link.exists() and not link.is_symlink():
        return  # 旧布局的真实目录：迁移期直接复用，不做改动
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        link.unlink()
    link.symlink_to(target, target_is_directory=True)


def prepare_llvm_host(host: str, mode: str) -> dict | None:
    """请求本机固定 LLVM 宿主记录；不可用时按模式返回 None 或抛错。

    返回值是 tools/llvm-*-host.py `shim` 子命令的 JSON 记录：`shim_dir` 是链接
    包装器目录，`selfhost_flags` 是「每行一个参数」的闭包文件。调用方把包装器
    目录前置到 PATH，并把闭包文件通过 YH_LLVM_SELFHOST_FLAGS 传给种子。闭包
    路径属于构建机（Zig 式做法：配方由构建环境给出，不编进种子）。
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
        print(f"警告：本次未准备固定 LLVM 闭包，自举链接将回退到种子内烘焙的路径"
              f"（仅过渡种子可用；新种子会报缺少闭包）。\n{detail}", file=sys.stderr)
        return None
    record = json.loads([line for line in result.stdout.splitlines() if line.strip()][-1])
    sdk_identity = record.get("sdk_sha256", record.get("sdk_host_sha256", "unknown"))
    print(f"内嵌 LLVM 桥已接入链接：host={record['host']} "
          f"bridge={record['bridge_sha256'][:12]} sdk={sdk_identity[:12]} "
          f"shim={record['shim_dir']}", file=sys.stderr)
    return record


def project_uses_link_manifest(project: Path) -> bool:
    """项目清单是否已声明 [link] 组；是则改用清单归档，不再注入旧闭包归档。"""
    manifest = project / "project.toml"
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(r"^\[link(?:-[a-z0-9-]+)?\]", text, re.MULTILINE) is not None


def main() -> int:
    """解析参数、按需准备包装器，然后用种子冷编项目。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--backend", choices=("llvm",),
                        help="显式选择构建候选时使用的后端（LLVM 是唯一后端）")
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
    # 编译器清单一旦声明 [link]，归档改由清单提供，旧闭包归档注入必须关闭；
    # 第一代候选仍走旧注入，避免旧种子不认识 [link]。
    is_compiler = project == (ROOT / "compiler").resolve()
    manifest_mode = is_compiler and project_uses_link_manifest(project)
    if is_compiler and not manifest_mode:
        environment["YH_LLVM_SELFHOST"] = "1"
    if args.llvm_host:
        ensure_closure_path()
        record = prepare_llvm_host(args.llvm_host, args.llvm_mode)
        if record:
            if not manifest_mode:
                shim = Path(record["shim_dir"])
                environment["PATH"] = str(shim) + os.pathsep + environment.get("PATH", "")
                # LLVM x64 target 会选择 /usr/bin/gcc 绕过 PATH；显式绑定同一 shim，
                # 让过渡种子可链接出目标机型正确且含固定桥的候选编译器。
                compiler_shim = "clang" if args.llvm_host == "darwin-aarch64" else "gcc"
                environment["YH_CC"] = str(shim / compiler_shim)
            else:
                environment.pop("YH_CC", None)
            if manifest_mode:
                # 归档来自 [link]；运行库参数走独立配方文件。
                environment.pop("YH_LLVM_SELFHOST", None)
                environment.pop("YH_LLVM_SELFHOST_FLAGS", None)
                environment["YH_LINK_MANIFEST_ONLY"] = "1"
                runtime_file = record.get("selfhost_runtime")
                if runtime_file and Path(runtime_file).is_file():
                    environment["YH_LINK_RUNTIME_FLAGS"] = str(runtime_file)
            else:
                # 闭包由构建机提供（种子不再烘焙绝对路径）；文件缺失时保持不设置，
                # 让链接阶段给出「缺少闭包」的可操作诊断，而不是静默降级。
                flags_file = record.get("selfhost_flags")
                if flags_file and Path(flags_file).is_file():
                    environment["YH_LLVM_SELFHOST_FLAGS"] = str(flags_file)
    command = [str(compiler)]
    if args.backend:
        command += ["--backend", args.backend]
    if args.target:
        command += ["--target", args.target]
    if args.opt_level:
        command += [f"-O{args.opt_level}"]
    command += ["build"]
    if args.emit_llvm:
        command.append("--emit-llvm")
    command += ["-o", str(output)]
    result = subprocess.run(command, cwd=project, check=False, env=environment)
    return result.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"seed-build：{error}", file=sys.stderr)
        sys.exit(1)
