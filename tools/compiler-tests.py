#!/usr/bin/env python3
"""在自举 LLVM 闭包环境下运行 compiler/ 的内建 yh test 测试（YT3b）。

compiler/ 项目在 `[link-*]` 里声明了内嵌 LLVM 桥/lld 闭包，测试二进制与编译器
本身一样需要构建机提供的链接环境（闭包参数、shim 目录与 SDKROOT）。本工具复用
`tools/llvm-*-host.py shim` 的记录准备该环境，然后对每个模块执行

    yh test <模块> --timeout <秒>

并要求输出含 `结果: N passed; 0 skipped; 0 failed`。

用法：
    python3 tools/compiler-tests.py --compiler-path ./yh
    python3 tools/compiler-tests.py --compiler-path ./yh --modules gen lex parse

退出码：全部通过 0；任一模块失败或被跳过 1；环境准备失败时按提示处理。
"""

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPILER = ROOT / "compiler"
DEFAULT_MODULES = ["gen", "lex", "parse"]

HOST_DRIVERS = {
    "darwin-aarch64": "llvm-darwin-host.py",
    "linux-aarch64": "llvm-host.py",
    "linux-x86_64": "llvm-host.py",
}


def host_key() -> str:
    """按宿主平台给出闭包 host 键。"""
    system = platform.system()
    machine = platform.machine().lower()
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    if system == "Darwin":
        return f"darwin-{arch}"
    return f"linux-{arch}"


def llvm_cache() -> Path:
    """与 Makefile/YH_LLVM_CACHE 一致的闭包缓存根。"""
    override = os.environ.get("YH_LLVM_CACHE")
    if override:
        return Path(override)
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "llvm_cache.py")],
        capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return ROOT / "tmp" / "llvm-migration"


def prepare_env(host: str) -> dict:
    """准备自举链接环境；宿主不具备固定闭包时返回未加修饰的环境。"""
    env = dict(os.environ)
    driver = HOST_DRIVERS.get(host)
    if driver is None:
        return env
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / driver), "shim",
         "--host", host, "--mode", "auto"],
        cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        # 没有固定闭包时仍尝试运行：链接阶段会给出明确诊断。
        print(f"提示：未能准备 {host} 固定 LLVM 闭包，按原环境运行", file=sys.stderr)
        return env
    record = json.loads(result.stdout)
    shim = record.get("shim_dir")
    flags = record.get("selfhost_flags")
    if shim:
        env["PATH"] = shim + os.pathsep + env.get("PATH", "")
        tool = "clang" if host.startswith("darwin") else "gcc"
        env["YH_CC"] = str(Path(shim) / tool)
    if flags and Path(flags).is_file():
        env["YH_LLVM_SELFHOST"] = "1"
        env["YH_LLVM_SELFHOST_FLAGS"] = flags
    if host.startswith("darwin"):
        sdk_record = llvm_cache() / "darwin-sdk" / f"sdk-{host}" / "host.json"
        if sdk_record.is_file():
            sdk_root = json.loads(sdk_record.read_text()).get("sdk_root")
            if sdk_root:
                env.setdefault("SDKROOT", sdk_root)
    return env


def run_module(compiler: Path, module: str, timeout: int, env: dict) -> int:
    """运行一个模块的内建测试，返回失败数（0 或 1）。"""
    proc = subprocess.run(
        [str(compiler), "test", module, "--timeout", str(timeout)],
        cwd=COMPILER, capture_output=True, text=True, env=env, timeout=1800)
    text = proc.stdout + proc.stderr
    expected = "结果: "
    ok = proc.returncode == 0 and expected in text and "0 failed" in text
    if ok:
        summary = [line for line in text.splitlines() if line.startswith(expected)]
        print(f"PASS compiler-tests/{module}: {summary[-1] if summary else ''}")
        return 0
    print(f"FAIL compiler-tests/{module}: 退出码 {proc.returncode}")
    print(text[-2000:])
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="compiler/ 内建 yh test 测试门")
    ap.add_argument("--compiler-path", default=str(ROOT / "yh"))
    ap.add_argument("--modules", nargs="+", default=DEFAULT_MODULES,
                    help=f"要运行的模块（缺省 {' '.join(DEFAULT_MODULES)}）")
    ap.add_argument("--timeout", type=int, default=120, help="单例超时秒数")
    args = ap.parse_args()
    compiler = Path(args.compiler_path).resolve()
    if not compiler.exists():
        print(f"编译器不存在: {compiler}")
        return 1
    env = prepare_env(host_key())
    failed = 0
    for module in args.modules:
        failed += run_module(compiler, module, args.timeout, env)
    total = len(args.modules)
    print(f"compiler-tests: 通过 {total - failed}/{total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
