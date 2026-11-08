#!/usr/bin/env python3
"""Darwin/ARM64 C ABI 门：LLVM 签名 oracle、Mach-O 与双向互调运行。"""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "tmp/llvm-migration/darwin-abi"
PROBE = ROOT / "tests/selfhost/darwin/llvm-darwin-abi-probe.yh"
UNSUPPORTED = ROOT / "tests/selfhost/darwin/llvm-darwin-abi-reject-slice.yh"
VARARGS = ROOT / "tests/selfhost/darwin/llvm-darwin-abi-reject-varargs.yh"
AGGREGATE_PROBE = ROOT / "tests/selfhost/darwin/llvm-darwin-abi-aggregate.yh"
AGGREGATE_BRIDGE = ROOT / "tests/selfhost/darwin/llvm-darwin-abi-aggregate.c"
BRIDGE = ROOT / "tests/selfhost/darwin/llvm-darwin-abi-bridge.c"
SDK_PACKAGE = ROOT / "tmp/llvm-migration/darwin-sdk/sdk-darwin-aarch64"
HOST_RECORD = SDK_PACKAGE / "host.json"
TRIPLE = "aarch64-apple-darwin"


def require(condition, message):
    """报告稳定的门禁失败原因，不使用可能被 Python -O 移除的 assert。"""
    if not condition:
        raise RuntimeError(message)


def run(label, command, environment, timeout=120, cwd=ROOT):
    """执行一条门禁命令并把原始输出保存到 tmp，便于复现失败。"""
    result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True,
                            text=True, timeout=timeout)
    (WORK / f"{label}.stdout").write_text(result.stdout, encoding="utf-8")
    (WORK / f"{label}.stderr").write_text(result.stderr, encoding="utf-8")
    return result


def canonical_signature(text, name):
    """提取 LLVM 定义/声明签名并剔除 Clang 独有的 noundef 与参数名。"""
    pattern = rf"^(?:define|declare)\s+(.*?)\s+@(?:\"{re.escape(name)}\"|{re.escape(name)})\((.*?)\)"
    match = re.search(pattern, text, re.MULTILINE)
    require(match is not None, f"LLVM 文本缺少函数签名：{name}")
    result = " ".join(match.group(1).replace("dso_local", "").split())
    parameters = []
    for item in match.group(2).split(","):
        item = re.sub(r"\s+%[-\w.$]+\s*$", "", item)
        item = " ".join(item.replace("noundef", "").split())
        parameters.append(item)
    return result, tuple(parameters)


def canonical_abi_shape(text, name):
    """抽取 LLVM C ABI 的返回类型、物理参数类型及 sret 位置。"""
    pattern = rf"^(?:define|declare)\s+(.*?)\s+@(?:\"{re.escape(name)}\"|{re.escape(name)})\("
    match = re.search(pattern, text, re.MULTILINE)
    require(match is not None, f"LLVM 文本缺少聚合 ABI 签名：{name}")
    start = match.end()
    depth = 1
    end = start
    while end < len(text) and depth > 0:
        if text[end] == "(":
            depth += 1
        elif text[end] == ")":
            depth -= 1
        end += 1
    require(depth == 0, f"LLVM 聚合 ABI 签名括号不完整：{name}")
    parameters_text = text[start:end - 1]

    def llvm_type(prefix):
        """从 LLVM 类型前缀中提取完整的标量、向量或命名结构类型。"""
        prefix = re.sub(r"\b(?:dso_local|zeroext|signext|noundef)\b", " ", prefix)
        prefix = prefix.strip()
        if prefix.startswith("["):
            array = re.match(r"\[[^\]]+\]", prefix)
            return array.group(0) if array else ""
        if prefix.startswith("{"):
            depth = 0
            for index, char in enumerate(prefix):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return prefix[:index + 1]
            return ""
        if prefix.startswith("%"):
            named = re.match(r"%[-\w.$]+", prefix)
            return named.group(0) if named else ""
        scalar = re.match(r"(?:void|ptr|i\d+|float|double)\b", prefix)
        require(scalar is not None, f"无法解析 LLVM ABI 类型：{prefix}")
        return scalar.group(0)

    raw_params = []
    start = 0
    depth = 0
    for index, char in enumerate(parameters_text):
        if char in "[({":
            depth += 1
        elif char in "])}":
            depth -= 1
        elif char == "," and depth == 0:
            raw_params.append(parameters_text[start:index].strip())
            start = index + 1
    tail = parameters_text[start:].strip()
    if tail:
        raw_params.append(tail)
    params = []
    for raw in raw_params:
        raw = re.sub(r"\s+%[-\w.$]+\s*$", "", raw)
        params.append((llvm_type(raw), int(re.search(r"\bsret\(", raw) is not None)))
    result_type = llvm_type(match.group(1))
    # Clang 用命名聚合（%struct.X / %union.X）当返回类型，YH 用同形字面量
    # （{double, double}）。二者在 Apple ABI 上等价，归一成 aggregate 后比较。
    if result_type.startswith("%struct.") or result_type.startswith("%union.") \
            or result_type.startswith("{"):
        result_type = "aggregate"
    return result_type, tuple(params)


def run_aggregate_suite(args, compiler, sdk_root, oracle, environment):
    """对照 Apple 小整数聚合/间接返回签名，并 O0/O2 运行 C↔YH 互调。"""
    ir = run("aggregate-probe-ir", [compiler, "--backend", "llvm", "--target",
        TRIPLE, "--emit-llvm", "--emit-asm", str(AGGREGATE_PROBE)], environment)
    require(ir.returncode == 0,
            f"Darwin LLVM 聚合 ABI 发射失败：{ir.stderr[-3000:]}")
    oracle_ir = run("aggregate-clang-oracle", [str(oracle), "-target", TRIPLE,
        "-isysroot", str(sdk_root), f"-mmacosx-version-min={args.min_os}",
        "-S", "-emit-llvm", "-O0", str(AGGREGATE_BRIDGE), "-o",
        str(WORK / "aggregate-clang-oracle.ll")], environment)
    require(oracle_ir.returncode == 0,
            f"Apple 聚合 ABI Clang oracle 失败：{oracle_ir.stderr[-2000:]}")
    expected = Path(WORK / "aggregate-clang-oracle.ll").read_text(encoding="utf-8")
    signature_pairs = (
        ("yh_round_byte", "yh_round_byte"),
        ("yh_round_triple", "yh_round_triple"),
        ("yh_round_word", "yh_round_word"),
        ("yh_round_pair16", "yh_round_pair16"),
        ("yh_round_nine", "yh_round_nine"),
        ("yh_round_union", "yh_round_union"),
        ("yh_round_float_union", "yh_round_float_union"),
        ("yh_round_float2", "yh_round_float2"),
        ("yh_round_hfa3", "yh_round_hfa3"),
        ("yh_adjust_hfa", "yh_adjust_hfa"),
        ("yh_nested_hfa", "yh_nested_hfa"),
        ("yh_call_hfa_callback", "yh_call_hfa_callback"),
        ("yh_call_returned_hfa_callback", "yh_call_returned_hfa_callback"),
        ("c_apply_hfa_callback", "c_apply_hfa_callback"),
        ("c_choose_hfa_callback", "c_choose_hfa_callback"),
        ("yh_sum_hfa_overflow", "yh_sum_hfa_overflow"),
        ("yh_round_wide", "yh_round_wide"),
        ("yh_call_byte", "c_round_byte"),
        ("yh_call_triple", "c_round_triple"),
        ("yh_call_word", "c_round_word"),
        ("yh_call_pair16", "c_round_pair16"),
        ("yh_call_nine", "c_round_nine"),
        ("yh_call_union", "c_round_union"),
        ("yh_call_float_union", "c_round_float_union"),
        ("yh_call_float2", "c_round_float2"),
        ("yh_call_hfa3", "c_round_hfa3"),
        ("yh_call_hfa_overflow", "c_sum_hfa_overflow"),
        ("yh_call_wide", "c_round_wide"),
    )
    for actual_name, oracle_name in signature_pairs:
        require(canonical_abi_shape(ir.stdout, actual_name)
                == canonical_abi_shape(expected, oracle_name),
                f"YH 与 Clang Apple 聚合 ABI 物理签名不一致：{actual_name}")

    for opt in ("-O0", "-O2"):
        project = WORK / f"aggregate-project-{opt[2:]}"
        if project.exists():
            shutil.rmtree(project)
        (project / "src").mkdir(parents=True)
        (project / "c").mkdir()
        shutil.copy2(AGGREGATE_PROBE, project / "src/main.yh")
        shutil.copy2(AGGREGATE_BRIDGE, project / "c/bridge.c")
        (project / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "llvmdarwinaggregate"\nsource = "src"\n\n'
            '[c]\nsources = ["c/bridge.c"]\n', encoding="utf-8")
        built = run(f"aggregate-build-{opt[2:]}", [compiler, "--backend", "llvm",
            "--target", TRIPLE, opt, "build"], environment, cwd=project)
        executable = project / ".build/llvmdarwinaggregate"
        require(built.returncode == 0 and executable.is_file(),
                f"{opt} Apple 聚合项目链接失败：{built.stderr[-3000:]}")
        executed = run(f"aggregate-run-{opt[2:]}", [str(executable)], environment)
        require(executed.returncode == 0,
                f"{opt} Apple 聚合 C↔YH 运行失败：退出码 {executed.returncode}")


def find_sdk_root(record, environment):
    """优先使用显式 SDKROOT，其次使用固定 Darwin 包记录的 SDK，再发现本机 SDK。"""
    if environment.get("SDKROOT"):
        return Path(environment["SDKROOT"]).resolve()
    if record.get("sdk_root"):
        return Path(record["sdk_root"])
    result = subprocess.run(["xcrun", "--sdk", "macosx", "--show-sdk-path"],
                            capture_output=True, text=True, check=False)
    require(result.returncode == 0 and result.stdout.strip(), "xcrun 未找到 macOS SDK")
    return Path(result.stdout.strip())


def main():
    """执行 Darwin 标量 ABI 的目标 IR 对照、拒绝矩阵和 O0/O2 实际互调。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("scalar", "aggregate", "full"), default="scalar")
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--min-os", default="14.0.0")
    args = parser.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    WORK.mkdir(parents=True, exist_ok=True)
    require(HOST_RECORD.is_file(), "缺少固定 Darwin LLVM host.json；先准备静态 LLVM SDK")
    record = json.loads(HOST_RECORD.read_text(encoding="utf-8"))
    sdk_root = find_sdk_root(record, os.environ)
    require((sdk_root / "SDKSettings.json").is_file(), f"无效 macOS SDKROOT：{sdk_root}")
    oracle = SDK_PACKAGE / "bin/clang"
    require(oracle.is_file(), f"固定 LLVM 21.1.8 C ABI oracle 不存在：{oracle}")
    linker_clang = record.get("toolchain", {}).get("clang")
    require(linker_clang and Path(linker_clang).is_file(), "Darwin host 记录缺少 Apple clang")
    environment = os.environ.copy()
    environment["SDKROOT"] = str(sdk_root)
    environment["MACOSX_DEPLOYMENT_TARGET"] = args.min_os

    if args.suite == "aggregate":
        run_aggregate_suite(args, compiler, sdk_root, oracle, environment)
        print("PASS Darwin/ARM64 聚合 ABI：Clang oracle、O0/O2 Mach-O 双向互调")
        return

    ir = run("probe-ir", [compiler, "--backend", "llvm", "--target", TRIPLE,
                           "--emit-llvm", "--emit-asm", str(PROBE)], environment)
    require(ir.returncode == 0, f"Darwin LLVM 标量 IR 发射失败：{ir.stderr[-3000:]}")
    oracle_ir = run("clang-oracle", [str(oracle), "-target", TRIPLE,
        "-isysroot", str(sdk_root), f"-mmacosx-version-min={args.min_os}",
        "-S", "-emit-llvm", "-O0", str(BRIDGE), "-o", str(WORK / "clang-oracle.ll")],
        environment)
    require(oracle_ir.returncode == 0, f"固定 Clang ABI oracle 失败：{oracle_ir.stderr[-2000:]}")
    expected = Path(WORK / "clang-oracle.ll").read_text(encoding="utf-8")
    for name in ("c_scalar", "yh_narrow10", "yh_fp9", "yh_pointer"):
        require(canonical_signature(ir.stdout, name) == canonical_signature(expected, name),
                f"YH 与固定 Clang 的 Apple C ABI 签名不一致：{name}")
    require("call i32 %v0(i32 %v1)" in ir.stdout,
            "YH 对 C 函数指针的间接调用签名没有进入 LLVM IR")
    require("; yh-macos-min-os = " in ir.stdout, "Darwin IR 缺少部署版本身份")

    unsupported = run("reject-slice", [compiler, "--backend", "llvm", "--target",
        TRIPLE, "--emit-llvm", "--emit-asm", str(UNSUPPORTED)], environment)
    require(unsupported.returncode != 0 and "C ABI 不支持该参数类型" in unsupported.stderr,
            "Darwin LLVM 错误地接受了没有 C ABI 映射的 yh 切片")
    varargs = run("reject-varargs", [compiler, "--backend", "llvm", "--target",
        TRIPLE, "--emit-llvm", "--emit-asm", str(VARARGS)], environment)
    require(varargs.returncode != 0 and "用户源码不允许裸变参" in varargs.stderr,
            "裸 C 变参没有按现有语言规则拒绝")

    for opt in ("-O0", "-O2"):
        project = WORK / f"project-{opt[2:]}"
        if project.exists():
            shutil.rmtree(project)
        (project / "src").mkdir(parents=True)
        (project / "c").mkdir()
        shutil.copy2(PROBE, project / "src/main.yh")
        shutil.copy2(BRIDGE, project / "c/bridge.c")
        (project / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "llvmdarwinabi"\nsource = "src"\n\n'
            '[c]\nsources = ["c/bridge.c"]\n', encoding="utf-8")
        object_file = (project / ".build/targets/aarch64-apple-darwin/llvm"
            / opt[1:] / "obj/llvmdarwinabi-main.o")
        executable = WORK / f"abi-{opt[2:]}"
        executable.unlink(missing_ok=True)
        built = run(f"object-{opt[2:]}", [compiler, "--backend", "llvm", "--target",
            TRIPLE, opt, "build"], environment, cwd=project)
        require(built.returncode == 0 and object_file.is_file(),
                f"{opt} Darwin LLVM 对象生成失败：{built.stderr[-3000:]}")
        kind = run(f"file-{opt[2:]}", ["file", str(object_file)], environment)
        require(kind.returncode == 0 and "Mach-O 64-bit object arm64" in kind.stdout,
                f"{opt} 输出不是 arm64 Mach-O：{kind.stdout.strip()}")
        linked = run(f"link-{opt[2:]}", [linker_clang, "-arch", "arm64", "-isysroot",
            str(sdk_root), f"-mmacosx-version-min={args.min_os}", str(BRIDGE),
            str(object_file), "-o", str(executable)], environment)
        require(linked.returncode == 0 and executable.is_file(),
                f"{opt} 临时测试链接失败：{linked.stderr[-3000:]}")
        executed = run(f"run-{opt[2:]}", [str(executable)], environment)
        require(executed.returncode == 0,
                f"{opt} Apple 标量 ABI 双向互调失败：退出码 {executed.returncode}")

    if args.suite == "full":
        run_aggregate_suite(args, compiler, sdk_root, oracle, environment)
        print("PASS Darwin/ARM64 标量与聚合 ABI：LLVM 21 oracle、负例、O0/O2 Mach-O 双向互调")
    else:
        print("PASS Darwin/ARM64 标量 ABI：LLVM 21 oracle、负例、O0/O2 Mach-O 双向互调")


if __name__ == "__main__":
    main()
