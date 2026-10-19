#!/usr/bin/env python3
"""Darwin LLVM SDK 配置契约门；不下载、不解包，也不伪称 SDK 已构建。"""

import json
import runpy
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/llvm-migration/darwin-sdk-test"
SDK_TOOL = ROOT / "tools/llvm-darwin-sdk.py"


def require(condition, message):
    """让配置契约在优化模式下也会拒绝错误结果。"""
    if not condition:
        raise RuntimeError(message)


def main():
    """验证宿主键、最低版本、SDK 元数据和固定源码包摘要的正反例。"""
    sdk = runpy.run_path(str(SDK_TOOL))
    select_host = sdk["select_host"]
    parse_min_os = sdk["parse_min_os"]
    load_sdk_version = sdk["load_sdk_version"]
    resolve_sdk_root = sdk["resolve_sdk_root"]
    source_spec = sdk["source_spec"]
    build_spec = sdk["build_spec"]
    verify_archive = sdk["verify_archive"]
    package_sdk = sdk["package_sdk"]

    require(select_host("Darwin", "arm64") == "darwin-aarch64",
            "Darwin/ARM64 宿主键错误")
    for system, machine in (("Linux", "x86_64"), ("Darwin", "x86_64"),
                            ("Windows", "ARM64")):
        try:
            select_host(system, machine)
        except RuntimeError:
            continue
        raise RuntimeError(f"误接受不支持的 LLVM SDK 宿主：{system}/{machine}")

    require(parse_min_os("14.0") == "14.0.0", "两段部署版本未规范化")
    require(parse_min_os("15.2.1") == "15.2.1", "三段部署版本被改写")
    for value in ("14", "14.0.0.1", "14.-1", "0.0", "14.x", " 14.0"):
        try:
            parse_min_os(value)
        except RuntimeError:
            continue
        raise RuntimeError(f"误接受非法最低系统版本：{value}")

    WORK.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=WORK) as temporary:
        sdk_root = Path(temporary) / "MacOSX.sdk"
        sdk_root.mkdir()
        (sdk_root / "SDKSettings.json").write_text(
            json.dumps({"Version": "27.0", "CanonicalName": "macosx27.0"}),
            encoding="utf-8")
        require(load_sdk_version(sdk_root) == "27.0", "SDKSettings.json 版本读取错误")
        explicit = resolve_sdk_root({"SDKROOT": str(sdk_root)}, "Linux", "x86_64")
        require(explicit == sdk_root.resolve(), "显式 SDKROOT 没有优先于宿主平台")

        def discover(command, **_):
            require(command == ["xcrun", "--sdk", "macosx", "--show-sdk-path"],
                    "SDK 自动发现命令错误")
            return subprocess.CompletedProcess(command, 0, str(sdk_root), "")

        require(resolve_sdk_root({}, "Darwin", "arm64", discover) == sdk_root.resolve(),
                "Darwin 原生 xcrun SDK 发现失败")
        try:
            resolve_sdk_root({}, "Linux", "x86_64", discover)
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Linux 缺 SDKROOT 时没有拒绝")
        (sdk_root / "SDKSettings.json").write_text("{}", encoding="utf-8")
        try:
            load_sdk_version(sdk_root)
        except RuntimeError:
            pass
        else:
            raise RuntimeError("SDK 缺少版本元数据时未拒绝")

        source = Path(temporary) / "source.tar.xz"
        source.write_bytes(b"not the pinned LLVM release")
        try:
            verify_archive(source, source_spec())
        except RuntimeError:
            pass
        else:
            raise RuntimeError("源码包摘要错误时未拒绝")

        source_tree = Path(temporary) / "source"
        build_tree = Path(temporary) / "build"
        prefix = Path(temporary) / "package"
        (source_tree / "llvm/include/llvm-c").mkdir(parents=True)
        (source_tree / "llvm/include/llvm-c/Analysis.h").write_text("header", encoding="ascii")
        (build_tree / "lib").mkdir(parents=True)
        (build_tree / "bin").mkdir()
        (build_tree / "include/llvm/Config").mkdir(parents=True)
        (build_tree / "lib/libLLVMCore.a").write_bytes(b"archive")
        (build_tree / "include/llvm/Config/llvm-config.h").write_text(
            "config", encoding="ascii")
        for name in ("clang", "opt", "llvm-config", "ld.lld", "ld64.lld"):
            (build_tree / "bin" / name).write_bytes(name.encode("ascii"))
        package_sdk(source_tree, build_tree, prefix)
        require((prefix / "include/llvm-c/Analysis.h").is_file(),
                "Darwin SDK 没有打包 LLVM C API 头文件")
        require((prefix / "bin/llvm-config").is_file(),
                "Darwin SDK 没有打包 llvm-config")
        require((prefix / "bin/ld64.lld").is_file(),
                "Darwin SDK 没有打包 Mach-O lld 驱动")

    lock = source_spec()
    require(lock["sha256"] ==
            "4633a23617fa31a3ea51242586ea7fb1da7140e426bd62fc164261fe036aa142",
            "LLVM 源码摘要与已冻结的 21.1.8 发布包不一致")
    config = build_spec()
    require(config["deployment_target"] == "14.0.0" and config["architectures"] == ["arm64"]
            and not config["build_shared_libs"] and not config["llvm_build_llvm_dylib"]
            and not config["llvm_link_llvm_dylib"] and not config["enable_zlib"]
            and not config["enable_zstd"] and not config["enable_libxml2"],
            "Darwin SDK 部署版本或静态链接配置错误")
    actual_package = Path(sdk["source_archive_path"]())
    if actual_package.is_file():
        verify_archive(actual_package, lock)
    print("PASS Darwin LLVM SDK 配置门：宿主 1/1、部署版本 2/8、SDK/SDKROOT 通过、坏包拒绝")


if __name__ == "__main__":
    main()
