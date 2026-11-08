#!/usr/bin/env python3
"""Darwin legacy 桩门：用真实 yh 汇编调用者链接弱桩并验证 C ABI。"""

import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "tests/selfhost/darwin/llvm-darwin-bridge-probe.yh"
STUB = ROOT / "compiler/llvm/bridge_stub.c"
WORK = ROOT / "tmp/llvm-migration/darwin-bridge-probe"
TARGET = "aarch64-apple-darwin"


def require(condition, message):
    """统一失败出口，防止错误宿主或空汇编被当成有效探针。"""
    if not condition:
        raise RuntimeError(message)


def run(command, label):
    """执行一步编译/链接/运行并保留完整 stdout/stderr。"""
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            check=False, timeout=120)
    (WORK / f"{label}.stdout").write_text(result.stdout, encoding="utf-8")
    (WORK / f"{label}.stderr").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{label} 失败（{result.returncode}）：{result.stderr[-3000:]}")
    return result


def main():
    """冷编 YH ABI 调用者，和未配置 LLVM 的 Darwin 弱桩链接并执行。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--cc", default=None, help="默认使用 xcrun 定位 Apple clang")
    parser.add_argument("--require-embedded", action="store_true",
                        help="断言被测 yh 强链接真实 LLVM/lld 桥且没有动态 LLVM 依赖")
    args = parser.parse_args()
    require(platform.system() == "Darwin" and platform.machine() == "arm64",
            "Darwin 桥探针只在原生 Darwin/ARM64 执行")
    compiler = Path(args.compiler_path).resolve()
    require(compiler.is_file(), f"找不到 yh 编译器：{compiler}")
    compiler_symbols = []
    compiler_dependencies = []
    if args.require_embedded:
        symbols = subprocess.run(["nm", "-g", str(compiler)], capture_output=True,
                                 text=True, check=True).stdout.splitlines()
        for name in ("_yh_llvm_emit_v2", "_yh_lld_link"):
            require(any(len(line.split()) >= 3 and line.split()[-2] == "T"
                        and line.split()[-1] == name for line in symbols),
                    f"被测 yh 没有强定义 {name}；seed-build 未注入固定桥")
        compiler_symbols = [line.strip() for line in symbols
                            if line.split() and line.split()[-1] in
                            ("_yh_llvm_emit_v2", "_yh_lld_link")]
        dependencies = subprocess.run(["otool", "-L", str(compiler)], capture_output=True,
                                      text=True, check=True).stdout
        require("libLLVM" not in dependencies and "libclang" not in dependencies,
                "被测 yh 动态依赖 LLVM/Clang")
        compiler_dependencies = dependencies.splitlines()[1:]
    WORK.mkdir(parents=True, exist_ok=True)
    cc = args.cc
    if cc is None:
        cc = subprocess.run(["xcrun", "--find", "clang"], capture_output=True,
                            text=True, check=True).stdout.strip()
    sdk_root = subprocess.run(["xcrun", "--sdk", "macosx", "--show-sdk-path"],
                              capture_output=True, text=True, check=True).stdout.strip()
    assembly = WORK / "probe.s"
    probe_object = WORK / "probe.o"
    stub_object = WORK / "bridge_stub.o"
    executable = WORK / "probe"
    retained = WORK / "retained.o"
    canary = b"existing output must survive a failed bridge call\n"
    retained.write_bytes(canary)

    emitted = run([str(compiler), "--target", TARGET, "--emit-asm", str(SOURCE)], "emit-asm")
    require(emitted.stdout.strip(), "yh 没有输出调用桥的 Darwin 汇编")
    assembly.write_text(emitted.stdout, encoding="utf-8")
    run([cc, "-isysroot", sdk_root, "-c", "-x", "assembler", str(assembly),
         "-o", str(probe_object)], "assemble")
    run([cc, "-isysroot", sdk_root, "-std=c11", "-Wall", "-Wextra", "-Werror", "-c", str(STUB),
         "-o", str(stub_object)], "compile-stub")
    run([cc, "-isysroot", sdk_root, str(probe_object), str(stub_object),
         "-o", str(executable)], "link")
    run([str(executable)], "run")
    require(retained.read_bytes() == canary, "失败桩改写了旧输出")
    dependencies = run(["otool", "-L", str(executable)], "dependencies").stdout
    require("libLLVM" not in dependencies and "libclang" not in dependencies,
            "legacy 失败桩意外依赖动态 LLVM/Clang")
    with compiler.open("rb") as executable_file:
        compiler_sha256 = hashlib.file_digest(executable_file, "sha256").hexdigest()
    (WORK / "report.json").write_text(json.dumps({
        "host": "darwin-arm64", "compiler": str(compiler),
        "compiler_sha256": compiler_sha256,
        "embedded_bridge_required": args.require_embedded,
        "strong_bridge_symbols": compiler_symbols,
        "compiler_dynamic_dependencies": compiler_dependencies,
        "probe_dynamic_dependencies": dependencies.splitlines()[1:],
        "result": "PASS",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PASS Darwin 桥 ABI：重复失败、诊断截断、lld 失败与旧输出保留"
          + ("；yh 静态桥身份通过" if args.require_embedded else "；legacy 弱桩通过"))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Darwin 桥桩门：{error}")
        raise SystemExit(1)
