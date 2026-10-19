#!/usr/bin/env python3
"""F2-4 Darwin/ARM64 生产链接门：进程内 lld、签名、运行与失败原子性。"""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/llvm-migration/darwin-link"
SOURCE = ROOT / "tests/yh-run/run/llvm-darwin-link.yh"
REJECT = ROOT / "tests/selfhost/llvm-darwin-link-reject.yh"
SDK_PACKAGE = ROOT / "tmp/llvm-migration/darwin-sdk/sdk-darwin-aarch64"
HOST_RECORD = SDK_PACKAGE / "host.json"
PROJECT_FIXTURE = ROOT / "tests/modules/projects/llvmdarwinlink"
PROJECT_REJECT = ROOT / "tests/selfhost/llvm-darwin-project-link-reject.yh"


def require(condition, message):
    """以稳定诊断报告失败，不依赖可被 Python -O 移除的 assert。"""
    if not condition:
        raise RuntimeError(message)


def run(label, command, environment, cwd=ROOT):
    """保存命令输出到临时目录，便于复现生产链接失败。"""
    result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True,
                            text=True, timeout=120)
    (WORK / f"{label}.stdout").write_text(result.stdout, encoding="utf-8")
    (WORK / f"{label}.stderr").write_text(result.stderr, encoding="utf-8")
    return result


def file_hash(path):
    """计算已有可执行文件摘要，比较失败链接前后的发布状态。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_executable(label, executable, environment, min_os):
    """核对 Darwin 产物架构、部署命令、嵌入签名，并在当前 Mac 上运行。"""
    executable = Path(executable)
    kind = run(f"{label}-file", ["file", str(executable)], environment)
    require(kind.returncode == 0 and "Mach-O 64-bit executable arm64" in kind.stdout,
            f"{label} 不是 arm64 Mach-O 可执行文件：{kind.stdout.strip()}")
    commands = run(f"{label}-load-commands", ["otool", "-l", str(executable)], environment)
    require(commands.returncode == 0 and "LC_BUILD_VERSION" in commands.stdout,
            f"{label} 缺少 LC_BUILD_VERSION：{commands.stderr[-2000:]}")
    require("LC_CODE_SIGNATURE" in commands.stdout,
            f"{label} 没有嵌入 ad-hoc code signature")
    require("platform 1" in commands.stdout or "platform MACOS" in commands.stdout,
            f"{label} 没有标记 macOS platform")
    match = re.search(r"\bminos\s+(\d+(?:\.\d+){1,2})", commands.stdout)
    actual = tuple(map(int, match.group(1).split("."))) if match else ()
    expected = tuple(map(int, min_os.split(".")))
    actual += (0,) * (3 - len(actual))
    expected += (0,) * (3 - len(expected))
    require(match is not None and actual == expected,
            f"{label} 的 LC_BUILD_VERSION 与部署版本 {min_os} 不符")
    signature = run(f"{label}-codesign-verify", ["codesign", "--verify",
        "--verbose=2", str(executable)], environment)
    require(signature.returncode == 0,
            f"{label} ad-hoc code signature 验证失败：{signature.stderr[-2000:]}")
    executed = run(f"{label}-execute", [str(executable)], environment)
    require(executed.returncode == 0,
            f"{label} 运行失败：退出码 {executed.returncode}")


def main():
    """真实链接最小 Darwin 程序并核对 Mach-O、load command、签名及旧产物。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--min-os", default="14.0.0")
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    require(HOST_RECORD.is_file(), "缺少固定 Darwin LLVM host.json")
    record = json.loads(HOST_RECORD.read_text(encoding="utf-8"))
    sdk_root = Path(os.environ.get("SDKROOT") or record.get("sdk_root", "")).resolve()
    require((sdk_root / "SDKSettings.json").is_file(), f"无效 Darwin SDKROOT：{sdk_root}")
    compiler = Path(args.compiler_path).resolve()
    output_dir = WORK / "中文 输出 路径"
    output_dir.mkdir(parents=True, exist_ok=True)
    executable = output_dir / "可运行程序"
    executable.unlink(missing_ok=True)

    watched_tools = {"clang": None, "clang++": None, "ld": None,
                     "ld64.lld": str(SDK_PACKAGE / "bin/ld64.lld"),
                     "codesign": None}
    for name in ("clang", "clang++", "ld", "codesign"):
        found = subprocess.run(["xcrun", "--find", name], capture_output=True,
                               text=True, check=False)
        require(found.returncode == 0 and found.stdout.strip(),
                f"无法定位系统 {name} 以构造外部调用监视器")
        watched_tools[name] = found.stdout.strip()
    wrapper_dir = WORK / "external-tool-watch"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    marker = WORK / "external-link-tool-called.txt"
    marker.unlink(missing_ok=True)
    for name, tool_path in watched_tools.items():
        wrapper = wrapper_dir / name
        wrapper.write_text("#!/bin/sh\n"
            "printf '%s\\n' \"$0\" >> \"$YH_DARWIN_EXTERNAL_TOOLS_LOG\"\n"
            f"exec {shlex.quote(tool_path)} \"$@\"\n", encoding="utf-8")
        wrapper.chmod(0o755)

    environment = os.environ.copy()
    environment["SDKROOT"] = str(sdk_root)
    environment["MACOSX_DEPLOYMENT_TARGET"] = args.min_os
    environment["YH_DARWIN_EXTERNAL_TOOLS_LOG"] = str(marker)
    environment["PATH"] = str(wrapper_dir) + os.pathsep + environment.get("PATH", "")
    environment.pop("YH_CC", None)

    built = run("build", [str(compiler), "--backend", "llvm", "--target",
        "aarch64-apple-darwin", "-o", str(executable), str(SOURCE)], environment)
    require(built.returncode == 0 and executable.is_file(),
            f"Darwin LLVM 最小可执行文件链接失败：{built.stderr[-3000:]}")
    require(not marker.exists(), "生产 Darwin LLVM 链接调用了外部 clang/ld/codesign")

    verify_executable("single", executable, environment, args.min_os)
    marker.unlink(missing_ok=True)

    before = file_hash(executable)
    incomplete_sdk = WORK / "sdk-without-libSystem"
    if incomplete_sdk.exists():
        shutil.rmtree(incomplete_sdk)
    incomplete_sdk.mkdir(parents=True)
    shutil.copy2(sdk_root / "SDKSettings.json", incomplete_sdk / "SDKSettings.json")
    missing_system = environment.copy()
    missing_system["SDKROOT"] = str(incomplete_sdk)
    failed = run("missing-libSystem", [str(compiler), "--backend", "llvm", "--target",
        "aarch64-apple-darwin", "-o", str(executable), str(SOURCE)], missing_system)
    require(failed.returncode != 0 and "Darwin SDK 缺少链接库" in failed.stderr,
            f"缺少 libSystem 的 Darwin SDK 没有明确失败：{failed.stderr[-2000:]}")
    require(executable.is_file() and file_hash(executable) == before,
            "缺少 libSystem 时覆盖了已有 Darwin 可执行文件")
    require(not marker.exists(), "缺少 libSystem 的生产链接调用了外部 clang/ld/codesign")

    failed = run("unresolved-symbol", [str(compiler), "--backend", "llvm", "--target",
        "aarch64-apple-darwin", "-o", str(executable), str(REJECT)], environment)
    require(failed.returncode != 0, "未解析 Darwin 外部符号错误地链接成功")
    require(executable.is_file() and file_hash(executable) == before,
            "Darwin 链接失败覆盖了已有可执行文件")
    require(not marker.exists(), "失败的生产 Darwin LLVM 链接调用了外部 clang/ld/codesign")
    leftovers = list(output_dir.glob("*.yh-tmp.*"))
    require(not leftovers, f"失败链接留下未发布临时产物：{leftovers}")

    for level in (0, 2):
        project = WORK / f"project-O{level}"
        if project.exists():
            shutil.rmtree(project)
        shutil.copytree(PROJECT_FIXTURE, project)
        project_env = environment.copy()
        marker.unlink(missing_ok=True)
        built = run(f"project-O{level}", [str(compiler), "--backend", "llvm",
            "--target", "aarch64-apple-darwin", f"-O{level}", "build"],
            project_env, cwd=project)
        product = project / ".build/llvmdarwinlink"
        require(built.returncode == 0 and product.is_file(),
                f"O{level} 多模块 Darwin LLVM 项目链接失败：{built.stderr[-3000:]}")
        require(not marker.exists(), f"O{level} 项目生产链接调用了外部 clang/ld/codesign")
        verify_executable(f"project-O{level}", product, project_env, args.min_os)
        if level == 2:
            product_hash = file_hash(product)
            manifests = list(project.rglob("link.manifest"))
            require(len(manifests) == 1, "多模块项目没有唯一成功链接 manifest")
            manifest = manifests[0]
            manifest_hash = file_hash(manifest)
            (project / "main/main.yh").write_text(
                PROJECT_REJECT.read_text(encoding="utf-8"), encoding="utf-8")
            marker.unlink(missing_ok=True)
            failed = run("project-link-failure", [str(compiler), "--backend", "llvm",
                "--target", "aarch64-apple-darwin", "-O2", "build"],
                project_env, cwd=project)
            require(failed.returncode != 0, "项目未解析外部符号错误地链接成功")
            require(product.is_file() and file_hash(product) == product_hash,
                    "项目链接失败覆盖了原有 Darwin 可执行文件")
            require(manifest.is_file() and file_hash(manifest) == manifest_hash,
                    "项目链接失败破坏了原有成功 manifest")
            require(not marker.exists(), "项目链接失败路径调用了外部 clang")
            leftovers = list((project / ".build").rglob("*.yh-tmp.*"))
            require(not leftovers, f"项目链接失败留下未发布临时产物：{leftovers}")

            (project / "main/main.yh").write_text(
                (PROJECT_FIXTURE / "main/main.yh").read_text(encoding="utf-8"),
                encoding="utf-8")
            wrong_source = WORK / "wrong-architecture.c"
            wrong_object = project / "wrong-architecture.o"
            wrong_source.write_text("int yh_wrong_architecture(void) { return 0; }\n",
                                    encoding="utf-8")
            clang = watched_tools["clang"]
            wrong = run("wrong-architecture-object", [clang, "-arch", "x86_64",
                "-isysroot", str(sdk_root), f"-mmacosx-version-min={args.min_os}",
                "-c", str(wrong_source), "-o", str(wrong_object)], environment)
            require(wrong.returncode == 0 and wrong_object.is_file(),
                    f"无法生成 x86_64 Mach-O 负例：{wrong.stderr[-2000:]}")
            project_config = project / "project.toml"
            project_config.write_text(
                project_config.read_text(encoding="utf-8")
                + '\n[c]\nobjects = ["wrong-architecture.o"]\n', encoding="utf-8")
            marker.unlink(missing_ok=True)
            wrong_link = run("wrong-architecture-link", [str(compiler), "--backend", "llvm",
                "--target", "aarch64-apple-darwin", "-O2", "build"],
                project_env, cwd=project)
            require(wrong_link.returncode != 0,
                    "Darwin arm64 lld 错误地接受 x86_64 外部对象")
            require(file_hash(product) == product_hash
                    and file_hash(manifest) == manifest_hash,
                    "错误架构对象破坏了原有可执行文件或成功 manifest")
            require(not marker.exists(), "错误架构链接路径调用了外部 clang/ld/codesign")
            leftovers = list((project / ".build").rglob("*.yh-tmp.*"))
            require(not leftovers, f"错误架构链接留下未发布临时产物：{leftovers}")

    print("PASS Darwin/ARM64 生产链接：进程内 lld、Mach-O、LC_BUILD_VERSION、ad-hoc 签名、运行与失败保留")


if __name__ == "__main__":
    main()
