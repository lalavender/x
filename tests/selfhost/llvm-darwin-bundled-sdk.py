#!/usr/bin/env python3
"""验证随编译器分发的 Darwin SDK stub：无 SDKROOT/无 xcrun 也能链接运行。

门禁要点：
- 清空 SDKROOT/YH_DARWIN_SDK，PATH 只放会记录调用并退出的假工具；
- 编译并运行一个纯 .yh 程序，断言 Mach-O、LC_BUILD_VERSION 的 sdk 来自
  `vendor/darwin-sdk/manifest.json`（26.4），且没有任何外部工具调用；
- 显式 SDKROOT 仍覆盖 bundle（宿主 SDK 版本）。
"""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "vendor/darwin-sdk"
WORK = ROOT / "tmp/llvm-migration/darwin-bundled-sdk"
PROBE = ROOT / "tests/selfhost/llvm-darwin-fixedpoint.yh"
TRIPLE = "aarch64-apple-darwin"


def require(condition, message):
    """稳定的失败原因，不依赖 assert。"""
    if not condition:
        raise RuntimeError(message)


def run(command, cwd, env):
    """执行命令并捕获输出。"""
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=300)


def profile(executable: Path, key: str):
    """从 otool -l 读取 LC_BUILD_VERSION 的一个字段。"""
    result = subprocess.run(["/usr/bin/otool", "-l", str(executable)],
                            capture_output=True, text=True, timeout=60)
    require(result.returncode == 0, f"otool 失败：{result.stderr[-500:]}")
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith(key + " "):
            return line.split()[-1]
    return None


def fake_tools(directory: Path, log: Path):
    """生成只记录调用的假工具，确保编译器不会外调系统链接器/工具。"""
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("clang", "clang++", "ld", "ld64.lld", "codesign", "xcrun", "cc", "gcc"):
        path = directory / name
        path.write_text(f"#!/bin/sh\necho {name} \"$@\" >> \"{log}\"\nexit 127\n",
                        encoding="utf-8")
        path.chmod(0o755)


def build_and_run(compiler: Path, env: dict, label: str):
    """编译探针、运行，并返回可执行文件。"""
    output = WORK / f"{label}.bin"
    built = run([str(compiler), "-o", str(output), str(PROBE)], WORK, env)
    require(built.returncode == 0, f"{label} 构建失败：{built.stderr[-2000:]}")
    executed = run([str(output)], WORK, env)
    require(executed.returncode == 0,
            f"{label} 运行失败：{executed.stderr[-800:]}")
    return output


def main():
    """执行 bundle 链接、覆盖与工具隔离断言。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    require(compiler.is_file(), f"编译器不存在：{compiler}")
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["sdk_version"]

    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    log = WORK / "tools.log"
    tools = WORK / "fake-tools"
    fake_tools(tools, log)

    env = dict(os.environ)
    env.pop("SDKROOT", None)
    env.pop("YH_DARWIN_SDK", None)
    env["PATH"] = str(tools)
    env["MACOSX_DEPLOYMENT_TARGET"] = "14.0.0"

    bundled = build_and_run(compiler, env, "bundled")
    require(profile(bundled, "minos") == "14.0",
            "bundle 链接的 minOS 不是 14.0")
    require(profile(bundled, "sdk") == version,
            f"bundle 链接的 SDK 不是 {version}：{profile(bundled, 'sdk')}")
    tool_calls = log.read_text(encoding="utf-8") if log.exists() else ""
    if tool_calls.strip():
        raise RuntimeError("bundle 链接仍调用了外部工具：\n" + tool_calls[-800:])

    # 显式 SDKROOT 必须覆盖 bundle；优先用固定 SDK 记录（已验证与
    # lld 21.1.8 兼容），xcrun 默认可能指向 SDK 27 的 arm64e.x1 标签。
    record = ROOT / "tmp/llvm-migration/darwin-sdk/sdk-darwin-aarch64/host.json"
    host_sdk = None
    if record.is_file():
        value = json.loads(record.read_text(encoding="utf-8")).get("sdk_root")
        if value:
            host_sdk = Path(value)
    if host_sdk is None:
        found = subprocess.run(
            ["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"],
            capture_output=True, text=True, check=False).stdout.strip()
        host_sdk = Path(found) if found else None
    if host_sdk is not None and host_sdk.is_dir():
        settings = json.loads((host_sdk / "SDKSettings.json").read_text(encoding="utf-8"))
        host_version = settings.get("Version", "")
        override = dict(env)
        override["PATH"] = os.environ.get("PATH", "")
        override["SDKROOT"] = str(host_sdk)
        overridden = build_and_run(compiler, override, "override")
        require(profile(overridden, "sdk") == host_version,
                f"SDKROOT 未覆盖 bundle：{profile(overridden, 'sdk')} != {host_version}")

    print(f"PASS Darwin SDK bundle：无 SDKROOT/无 xcrun 链接运行，sdk={version}；"
          "显式 SDKROOT 覆盖生效")


if __name__ == "__main__":
    main()
