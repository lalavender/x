#!/usr/bin/env python3
"""F2 目标门：保存 Darwin 目标的真实命令证据，明确区分拒绝基线与发射验收。"""

import argparse
import copy
import hashlib
import json
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = "aarch64-apple-darwin"
SOURCE = ROOT / "tests/yh-run/run/llvm-darwin-target.yh"
WORK = ROOT / "tmp/llvm-migration/darwin-target"
ENVIRONMENT = ("system", "sdk-version", "sdk-build", "sdk-path", "clang-path",
               "clang-version", "linker-path", "linker-version")


def require(condition, message):
    """统一报告契约失败，不能用 Python -O 关闭断言而误放行。"""
    if not condition:
        raise RuntimeError(message)


def digest(path):
    """分块计算真实输入文件的摘要，供基线回放和种子核对。"""
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def compiler_source_identity():
    """按相对路径与内容计算编译器源码树身份，确保报告可对应具体工作树。"""
    files = sorted(path for path in (ROOT / "compiler").rglob("*")
                   if path.is_file() and path.suffix in (".yh", ".c", ".cpp", ".h", ".toml"))
    identity = hashlib.sha256()
    for path in files:
        identity.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        identity.update(b"\0")
        identity.update(bytes.fromhex(digest(path)))
    return identity.hexdigest(), len(files)


def execute(label, command, work, env=None):
    """执行真实程序并保留完整输出；报告仅保存有界尾部与独立日志路径。"""
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                            text=True, timeout=120)
    (work / f"{label}.stdout").write_text(result.stdout, encoding="utf-8")
    (work / f"{label}.stderr").write_text(result.stderr, encoding="utf-8")
    return {"label": label, "command": list(map(str, command)),
            "returncode": result.returncode, "stdout_bytes": len(result.stdout.encode()),
            "stdout": result.stdout[-4096:], "diagnostic": result.stderr[-4096:]}


def validate_report(report):
    """拒绝错误平台、漏命令、成功伪装拒绝与发布半产物等错误验收报告。"""
    require(report.get("target") == TARGET, "报告目标不是 Darwin/ARM64")
    require(report.get("mode") == "baseline", "本片只确认拒绝基线，不确认对象发射")
    require(isinstance(report.get("source_file_count"), int)
            and report["source_file_count"] > 0, "报告缺少编译器源码文件数")
    require(len(report.get("source_tree_sha256", "")) == 64,
            "报告缺少编译器源码树 SHA-256")
    rows = {row["label"]: row for row in report.get("commands", [])}
    good = ("syntax", "check", "legacy-build", "legacy-run")
    rejected = ("llvm-text", "llvm-asm", "llvm-link", "unknown-target")
    require(len(rows) == len(good + rejected), "报告漏命令或混入其他步骤")
    for label in good:
        require(label in rows and rows[label]["returncode"] == 0,
                f"{label} 未成功")
    for label in rejected:
        require(label in rows and rows[label]["returncode"] != 0,
                f"{label} 未按预期拒绝")
    for label in ("llvm-text", "llvm-asm", "llvm-link"):
        require("平台尚不支持" in rows[label]["diagnostic"],
                f"{label} 未证明 emitter 平台拒绝")
    require(rows["llvm-text"]["stdout_bytes"] == 0, "拒绝后仍输出 LLVM 文本")
    require(report.get("existing_output_preserved") is True, "失败破坏了旧输出")
    environment = report.get("environment", {})
    require(set(environment) == set(ENVIRONMENT), "报告缺少 SDK/工具链环境记录")
    require(all(environment[label].get("returncode") == 0 for label in ENVIRONMENT),
            "系统、SDK 或固定目标工具查询失败")
    require(all((environment[label].get("stdout", "")
                 + environment[label].get("diagnostic", "")).strip()
                for label in ENVIRONMENT), "SDK/工具路径或版本输出为空")


def self_test():
    """用手工报告验证验收器不会把漏步骤、错误目标或发射成功当作拒绝基线。"""
    rows = [{"label": label, "returncode": 0, "stdout_bytes": 0, "diagnostic": ""}
            for label in ("syntax", "check", "legacy-build", "legacy-run")]
    rows += [{"label": label, "returncode": 1, "stdout_bytes": 0,
              "diagnostic": "平台尚不支持"}
             for label in ("llvm-text", "llvm-asm", "llvm-link", "unknown-target")]
    good = {"target": TARGET, "mode": "baseline", "commands": rows,
            "existing_output_preserved": True, "source_file_count": 1,
            "source_tree_sha256": "0" * 64,
            "environment": {label: {"returncode": 0, "stdout": "recorded"}
                            for label in ENVIRONMENT}}
    validate_report(good)
    bad = []
    wrong = copy.deepcopy(good)
    wrong["target"] = "x86_64-unknown-linux-gnu"
    bad.append(wrong)
    wrong = copy.deepcopy(good)
    wrong["commands"].pop()
    bad.append(wrong)
    wrong = copy.deepcopy(good)
    wrong["commands"][4]["returncode"] = 0
    bad.append(wrong)
    wrong = copy.deepcopy(good)
    wrong["commands"][4]["diagnostic"] = "语法错误"
    bad.append(wrong)
    wrong = copy.deepcopy(good)
    wrong["existing_output_preserved"] = False
    bad.append(wrong)
    for index, report in enumerate(bad):
        try:
            validate_report(report)
        except RuntimeError:
            continue
        raise RuntimeError(f"验收器误放行负报告 {index}")
    print("PASS Darwin 目标报告门自测：1 个正例、5 个拒绝案例")


def main():
    """执行无固定 SDK 的目标检查与旧后端运行，保存 LLVM 当前拒绝的原始证据。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--baseline", action="store_true", help="核对尚未接入的拒绝基线")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    require(args.baseline, "F2-0 使用 --baseline；完整发射门由 F2-2 接入")
    require(platform.system() == "Darwin" and platform.machine() == "arm64",
            "本门要求 Darwin/ARM64 原生宿主")
    compiler = str(Path(args.compiler_path).resolve())
    WORK.mkdir(parents=True, exist_ok=True)
    legacy = WORK / "legacy-target"
    existing = WORK / "retained-output"
    canary = b"previous successful output\n"
    existing.write_bytes(canary)
    source_tree_sha256, source_file_count = compiler_source_identity()
    report = {"mode": "baseline", "target": TARGET,
              "compiler_sha256": digest(compiler), "source_sha256": digest(SOURCE),
              "source_tree_sha256": source_tree_sha256,
              "source_file_count": source_file_count,
              "seed_sha256": digest(ROOT / "bin/yh-darwin-arm64"), "commands": [],
              "environment": {}}
    commands = [
        ("syntax", [compiler, "--target", TARGET, "--syntax-check", str(SOURCE)]),
        ("check", [compiler, "--target", TARGET, "check", str(SOURCE)]),
        ("legacy-build", [compiler, "--backend", "legacy", "--target", TARGET,
                          str(SOURCE), "-o", str(legacy)]),
        ("legacy-run", [str(legacy)]),
        ("llvm-text", [compiler, "--backend", "llvm", "--target", TARGET,
                       "--emit-llvm", "--emit-asm", str(SOURCE)]),
        ("llvm-asm", [compiler, "--backend", "llvm", "--target", TARGET,
                      "--emit-asm", str(SOURCE)]),
        ("llvm-link", [compiler, "--backend", "llvm", "--target", TARGET,
                       str(SOURCE), "-o", str(existing)]),
        ("unknown-target", [compiler, "--target", "aarch64-apple-unknown",
                            "--emit-asm", str(SOURCE)]),
    ]
    for label, command in commands:
        row = execute(label, command, WORK)
        report["commands"].append(row)
        print(f"{label}: rc={row['returncode']}")
        if label == "legacy-build":
            require(row["returncode"] == 0, row["diagnostic"])
    report["existing_output_preserved"] = existing.read_bytes() == canary
    for label, command in (("system", ["sw_vers"]),
                           ("sdk-version", ["xcrun", "--sdk", "macosx", "--show-sdk-version"]),
                           ("sdk-build", ["xcrun", "--sdk", "macosx", "--show-sdk-build-version"]),
                           ("sdk-path", ["xcrun", "--sdk", "macosx", "--show-sdk-path"]),
                           ("clang-path", ["xcrun", "--find", "clang"]),
                           ("clang-version", ["xcrun", "clang", "--version"]),
                           ("linker-path", ["xcrun", "--find", "ld"]),
                           ("linker-version", ["xcrun", "ld", "-v"])):
        report["environment"][label] = execute(label, command, WORK)
    (WORK / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    validate_report(report)
    print(f"PASS Darwin 目标拒绝基线：{WORK / 'report.json'}")


if __name__ == "__main__":
    main()
