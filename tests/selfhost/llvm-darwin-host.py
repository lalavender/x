#!/usr/bin/env python3
"""Darwin 静态 LLVM host 包装器和链接参数的契约测试。"""

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/llvm-darwin-host.py"


def require(condition, message):
    """无论 Python 优化选项如何，都明确检查契约。"""
    if not condition:
        raise RuntimeError(message)


def main():
    """验证 host 键、链接/编译区分、参数保留和 Mach-O 强制装载。"""
    host = runpy.run_path(str(TOOL))
    require(host["HOST"] == "darwin-aarch64", "Darwin host 键错误")
    require(host["has_macos_build_version"]("LC_BUILD_VERSION\n platform 1\n"),
            "otool 的数字 macOS platform 标签被漏认")
    require(host["has_macos_build_version"]("LC_BUILD_VERSION\n platform MACOS\n"),
            "otool 的具名 macOS platform 标签被漏认")
    require(not host["has_macos_build_version"]("LC_BUILD_VERSION\n platform 2\n"),
            "其他 Mach-O 平台被误认成 macOS")
    require("passes" in host["LLVM_COMPONENTS"]
            and "x86codegen" in host["LLVM_COMPONENTS"]
            and "aarch64codegen" in host["LLVM_COMPONENTS"]
            and "option" in host["LLVM_COMPONENTS"]
            and {"lto", "windowsdriver", "windowsmanifest", "libdriver"}.issubset(
                host["LLVM_COMPONENTS"])
            and "all" not in host["LLVM_COMPONENTS"],
            "静态 LLVM 闭包没有限定到优化管线和两个目标架构")
    archives = host["llvm_archives"](host["load_sdk_record"]())
    archive_names = {path.name for path in archives}
    require({"libLLVMOption.a", "libLLVMWindowsDriver.a", "libLLVMWindowsManifest.a",
             "libLLVMLTO.a", "libLLVMLibDriver.a"}.issubset(archive_names),
            "内嵌 lld 所需的 option、Windows driver/manifest 或 LTO 组件未纳入静态闭包")
    require(host["is_compile_call"](["-c", "a.s", "-o", "a.o"]),
            "汇编调用被误判成最终链接")
    compile_args = host["compile_argv"](["-c", "a.s", "-o", "a.o"], "14.0.0")
    require(compile_args[-1] == "-mmacosx-version-min=14.0.0",
            "自举对象没有固定到与最终链接相同的最低系统版本")
    explicit_args = host["compile_argv"](
        ["-c", "a.c", "-mmacosx-version-min=15.0.0"], "14.0.0")
    require(explicit_args.count("-mmacosx-version-min=14.0.0") == 1
            and "-mmacosx-version-min=15.0.0" not in explicit_args,
            "自举对象部署版本没有与 host.json 链接身份统一")
    require(host["is_compile_call"](["-E", "a.c"]), "预处理调用被误判成最终链接")
    require(host["is_driver_query"](["--version"]), "clang 查询被误判成链接")
    require(not host["is_driver_query"](["a.o", "-o", "a"]), "对象链接被误判成查询")

    fixed = host["fixed_link_flags"]("/tmp/libbridge.a",
        {"sdk_root": "/Apple SDK", "min_os": "14.0.0"}, [Path("/tmp/libLLVMCore.a")])
    require(all("--start-group" not in flag and "memfd" not in flag for flag in fixed),
            "Darwin 链接误用了 GNU group 或 memfd")
    require(fixed[:3] == ["-isysroot", "/Apple SDK", "-mmacosx-version-min=14.0.0"],
            "Darwin SDKROOT 或最低系统版本没有固定到链接参数")
    require(sum("-force_load" in flag for flag in fixed) == 6,
            "桥、四种 lld 和 LLVM 组件必须全部 force-load")

    command = ["a.o", "-o", "out file", "-Wl,-dead_strip"]
    augmented = host["link_argv"](command, ["-Wl,-force_load,/tmp/libbridge.a", "-lSystem"])
    require(augmented[:len(command)] == command, "链接输入参数顺序或空格路径被改写")
    require(augmented[len(command):] == ["-Wl,-force_load,/tmp/libbridge.a", "-lSystem"],
            "固定桥参数没有追加到链接命令尾部")
    try:
        host["link_argv"](["a.o"], ["-lLLVMCore"])
    except RuntimeError:
        pass
    else:
        raise RuntimeError("缺少输出路径时未拒绝 host 链接")

    config_dir = ROOT / "tmp/llvm-migration/darwin-host-test"
    config_dir.mkdir(parents=True, exist_ok=True)
    host["generate_lld_config"](config_dir / "lld_link_config.h", "test", [])
    header = (config_dir / "lld_link_config.h").read_text(encoding="ascii")
    require("#define YH_LLD_DEFAULT_FILES_COUNT 0" in header
            and "#define YH_LLVM_SELFHOST_LINK_FLAGS_COUNT 0" in header
            and "nullptr" in header,
            "空 Darwin lld 配置没有安全的零长度计数表示")
    # 自举闭包：raw ld64.lld 参数必须原样编入配置，供 yh 侧拼装 argv。
    host["generate_lld_config"](config_dir / "lld_link_config.h", "test",
                                ["-force_load", "/tmp/libbridge.a", "-lc++"])
    header = (config_dir / "lld_link_config.h").read_text(encoding="ascii")
    require("#define YH_LLVM_SELFHOST_LINK_FLAGS_COUNT 3" in header
            and '" -force_load"' not in header
            and '"-force_load"' in header
            and '"/tmp/libbridge.a"' in header and '"-lc++"' in header,
            "Darwin 自举链接闭包没有编入 lld 配置")
    # 自举闭包：构建机提供的文件必须是「每行一个参数」，空闭包写空文件。
    text = host["selfhost_flags_text"](["-force_load", "/tmp/libbridge.a", "-lc++"])
    require(text == "-force_load\n/tmp/libbridge.a\n-lc++\n",
            "自举闭包文件必须是每行一个参数且以换行结尾")
    require(host["selfhost_flags_text"]([]) == "", "空闭包必须写成空文件")
    require(host["selfhost_flags_path"]().name == "selfhost-flags.txt",
            "自举闭包文件名必须稳定，构建机与门禁按名字发现")
    print("PASS Darwin LLVM host 契约：编译透传、查询透传、链接注入与参数保留")


if __name__ == "__main__":
    main()
