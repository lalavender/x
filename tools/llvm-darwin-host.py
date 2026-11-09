#!/usr/bin/env python3
"""构建 Darwin/ARM64 编译器桥，并为自举链接生成局部 clang 包装器。"""

import argparse
import hashlib
import json
import os
import platform
import re
import runpy
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from llvm_cache import cache_root  # noqa: E402
from llvm_recipe import (host_recipe_digest, sdk_recipe_digest,  # noqa: E402
                         closure_stamp_ok, closure_stamp_write)
WORK = cache_root()
HOST = "darwin-aarch64"
SDK_BUILDER = ROOT / "tools/llvm-darwin-sdk.py"
SDK_PREFIX = WORK / "darwin-sdk/sdk-darwin-aarch64"
SDK_RECORD = SDK_PREFIX / "host.json"
MANIFEST = ROOT / "vendor/llvm/sdk.lock.json"
BRIDGE = ROOT / "compiler/llvm/bridge.c"
BRIDGE_HEADER = ROOT / "compiler/llvm/bridge.h"
LLD_BRIDGE = ROOT / "compiler/llvm/lld_bridge.cpp"
HOST_BUILDER = Path(__file__).resolve()
LLD_ARCHIVES = ("liblldCommon.a", "liblldELF.a", "liblldMachO.a", "liblldCOFF.a")
LLVM_COMPONENTS = ("core", "analysis", "irreader", "target", "codegen", "passes",
                   "mc", "mcparser", "support", "x86codegen", "x86asmparser",
                   "aarch64codegen", "aarch64asmparser", "option", "lto",
                   "windowsdriver", "windowsmanifest", "libdriver")
MIN_OS = "14.0.0"
NOT_READY = 3


class NotReady(RuntimeError):
    """固定 Darwin LLVM 宿主尚未准备好，可由 auto 模式回退。"""


def describe(path):
    """把路径显示为相对仓库的短形式；在仓库外（如 $YH_LLVM_CACHE）时返回绝对路径。

    Darwin 闭包默认落在 $HOME/Documents/x/tmp/llvm-migration（仓库外），
    此时 Path.relative_to(ROOT) 会抛 ValueError——身份记录与日志都必须能同时
    服务「仓库内 tmp/」与「仓库外缓存根」两种布局。
    """
    path = Path(path)
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def digest(path):
    """分块计算桥、SDK 或可执行文件的 SHA-256。"""
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def has_macos_build_version(load_commands):
    """otool 的 platform 字段可能显示名称或 Mach-O 常量 1，二者都表示 macOS。"""
    if "LC_BUILD_VERSION" not in load_commands:
        return False
    return re.search(r"^\s*platform\s+(?:MACOS|1)\s*$", load_commands,
                     re.MULTILINE) is not None


def run(command, label, timeout=None):
    """执行工具并保存 stdout/stderr；失败时指出 tmp 日志位置。"""
    directory = workdir()
    directory.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            check=False, timeout=timeout)
    (directory / f"{label}.stdout").write_text(result.stdout, encoding="utf-8")
    (directory / f"{label}.stderr").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{label} 失败（{result.returncode}）：{result.stderr[-3000:]}; "
                           f"日志位于 {describe(directory)}")
    return result


def workdir():
    """返回 Darwin 静态桥、自举探针与 host.json 的固定临时目录。"""
    return WORK / f"llvm-host-{HOST}"


def shim_path(directory=None):
    """链接包装器（clang）路径；标记检查用它判断 shim 是否可用。"""
    return (directory or workdir()) / "shim" / "clang"


def selfhost_flags_path(directory=None):
    """自举闭包文件：构建机在链接时通过 YH_LLVM_SELFHOST_FLAGS 提供。"""
    return (directory or workdir()) / "selfhost-flags.txt"


def selfhost_runtime_path(directory=None):
    """非归档运行库参数：通过 YH_LINK_RUNTIME_FLAGS 追加到最终链接。"""
    return (directory or workdir()) / "selfhost-runtime.txt"


def selfhost_flags_text(flags):
    """把闭包参数排成「每行一个」：yh 运行时按行读取，不做 shell 切分。"""
    return "".join(f"{flag}\n" for flag in flags)


def write_selfhost_flags(record, directory=None):
    """把闭包写成本地文件并回填身份字段（种子不再内置构建机绝对路径）。"""
    path = selfhost_flags_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(selfhost_flags_text(record["selfhost_link_flags"]), encoding="utf-8")
    record["selfhost_flags_file"] = describe(path)
    record["selfhost_flags_sha256"] = digest(path)
    runtime = [flag for flag in record["selfhost_link_flags"]
               if flag != "-force_load" and not flag.startswith("/")]
    # 闭包已用 libc++.tbd 提供 C++ 运行库时不再传 -lc++：否则同一次链接会
    # 同时拿到 stub 输入和 -l 参数，重复且与闭包身份不一致。
    if record.get("cxx_tbd"):
        runtime = [flag for flag in runtime if flag != "-lc++"]
    runtime_path = selfhost_runtime_path(directory)
    runtime_path.write_text(selfhost_flags_text(runtime), encoding="utf-8")
    record["selfhost_runtime_file"] = describe(runtime_path)
    record["selfhost_runtime_sha256"] = digest(runtime_path)
    return path


def cxx_stub_path(directory=None):
    """闭包里的 libc++ 文本 stub 路径。

    libc++ 是 C++ 桥（lld/LLVM）必需的系统运行库，而随编译器分发的 SDK stub
    只带 libSystem。把宿主 SDK 的 libc++.tbd 复制进构建机闭包后，项目只要在
    [link-<目标>] 里引用它就能链接，不再依赖 YH_LINK_RUNTIME_FLAGS。
    """
    return (directory or workdir()) / "libc++.tbd"


def write_cxx_stub(record, directory=None):
    """把宿主 SDK 的 libc++.tbd 复制进闭包，并回填身份字段。"""
    sdk_root = Path(record.get("sdk_root", ""))
    source = sdk_root / "usr/lib/libc++.tbd"
    if not source.is_file():
        return
    path = cxx_stub_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source.read_bytes())
    record["cxx_tbd"] = describe(path)
    record["cxx_tbd_sha256"] = digest(path)


def is_compile_call(argv):
    """识别编译/预处理类调用，这些调用必须原样交给 Apple clang。"""
    return bool({"-c", "-E", "-S", "-fsyntax-only"} & set(argv))


def compile_argv(argv, min_os):
    """为自举编译对象固定与最终链接相同的 macOS 最低版本。"""
    output = []
    i = 0
    while i < len(argv):
        if argv[i] == "-mmacosx-version-min":
            i += 2
        elif argv[i].startswith("-mmacosx-version-min="):
            i += 1
        else:
            output.append(argv[i])
            i += 1
    return [*output, f"-mmacosx-version-min={min_os}"]


def is_driver_query(argv):
    """识别 clang 查询，避免将版本与搜索路径请求误当成最终链接。"""
    if not argv:
        return True
    exact = {"--version", "-version", "-v", "-dumpversion", "-dumpmachine",
             "-print-search-dirs", "-print-sysroot", "-print-resource-dir"}
    prefixes = ("-print-file-name=", "-print-prog-name=")
    return all(item in exact or item.startswith(prefixes) for item in argv)


def link_argv(argv, fixed_flags):
    """保留原有链接参数并在末尾追加固定的桥和 LLVM 静态输入。"""
    if "-o" not in argv or argv.index("-o") + 1 >= len(argv):
        raise RuntimeError("Darwin LLVM 链接调用缺少 -o 输出路径")
    if not any(not item.startswith("-") for item in argv):
        raise RuntimeError("Darwin LLVM 链接调用没有对象或源文件输入")
    return [*argv, *fixed_flags]


def load_sdk_record():
    """读取固定 LLVM SDK 身份并验证所有已锁定静态归档。"""
    try:
        record = json.loads(SDK_RECORD.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise NotReady(f"Darwin LLVM SDK 尚未构建：{error}") from error
    if record.get("host") != HOST or record.get("manifest_sha256") != digest(MANIFEST):
        raise NotReady("Darwin LLVM SDK host 或锁文件身份已变化")
    if record.get("builder_sha256") != sdk_recipe_digest():
        raise NotReady("Darwin LLVM SDK 构建器已变化")
    for name, expected in record.get("archives", {}).items():
        archive = SDK_PREFIX / "lib" / name
        if not archive.is_file() or digest(archive) != expected:
            raise NotReady(f"Darwin LLVM SDK 静态归档缺失或摘要错误：{archive}")
    for name, expected in record.get("tools", {}).items():
        executable = SDK_PREFIX / "bin" / name
        if not executable.is_file() or digest(executable) != expected:
            raise NotReady(f"Darwin LLVM SDK 工具缺失或摘要错误：{executable}")
    return record


def llvm_archives(sdk_record):
    """只解析 C emitter、优化管线与 X86/AArch64 目标所需的静态闭包。"""
    tool = SDK_PREFIX / "bin/llvm-config"
    if not tool.is_file():
        raise RuntimeError(f"固定 Darwin SDK 缺少 llvm-config：{tool}")
    result = run([str(tool), "--link-static", "--libs", *LLVM_COMPONENTS],
                 "llvm-config-libs")
    libraries = []
    for token in shlex.split(result.stdout):
        if not token.startswith("-l"):
            continue
        name = token[2:]
        archive = SDK_PREFIX / "lib" / f"lib{name}.a"
        if not archive.is_file():
            raise RuntimeError(f"llvm-config 引用了未打包的静态库：{archive}")
        if archive not in libraries:
            libraries.append(archive)
    if not libraries or any(not path.name.startswith("libLLVM") for path in libraries):
        raise RuntimeError("llvm-config 没有给出预期的 LLVM 静态组件闭包")
    missing = [name for name in LLD_ARCHIVES
               if not (SDK_PREFIX / "lib" / name).is_file()]
    if missing:
        raise RuntimeError(f"Darwin SDK 缺少 lld 静态组件：{missing}")
    return libraries


def fixed_link_flags(archive, sdk_record, libraries):
    """生成仅供编译器自举链接使用的 Apple ld force-load 参数。"""
    flags = ["-isysroot", sdk_record["sdk_root"],
             f"-mmacosx-version-min={sdk_record['min_os']}",
             f"-Wl,-force_load,{archive}"]
    for name in LLD_ARCHIVES:
        flags.append(f"-Wl,-force_load,{SDK_PREFIX / 'lib' / name}")
    flags.extend(f"-Wl,-force_load,{path}" for path in libraries)
    return flags


def raw_selfhost_flags(flags):
    """把 clang 链接参数折算成 raw ld64.lld 自举链接参数。

    yh 自举时的最终链接由内嵌 lld 直接执行（Darwin 走完整 argv 路径，不借用
    GNU 模板），因此需要 Apple 形式的 `-force_load <归档>`；加上 `-lc++`
    解析 LLVM/lld 静态闭包的 C++ 运行库引用。SDK 与部署版本已由链接前缀给出，
    clang 专用参数在此剔除。
    """
    raw = []
    for flag in flags:
        if flag.startswith("-Wl,-force_load,"):
            raw.append("-force_load")
            raw.append(flag[len("-Wl,-force_load,"):])
    raw.append("-lc++")
    return raw


def generate_lld_config(output, identity, selfhost_flags):
    """为 raw lld ABI 生成 Mach-O host 记录；不借用 GNU/ELF 链接模板。"""
    sdk = runpy.run_path(str(ROOT / "tools/llvm-sdk.py"))
    sdk["write_lld_config_header"](output, ["ld64.lld"], [], [],
                                   selfhost_flags, identity)


def compile_bridge(sdk_record, libraries):
    """编译 C emitter 与 raw lld C++ ABI，并归档成自举链接输入。"""
    directory = workdir()
    directory.mkdir(parents=True, exist_ok=True)
    toolchain = sdk_record["toolchain"]
    archive = directory / "libyh-llvm-bridge.a"
    flags = fixed_link_flags(archive, sdk_record, libraries)
    selfhost_flags = raw_selfhost_flags(flags)
    # 身份只取内容与构建参数，不取构建机路径：闭包路径属于构建环境
    # （YH_LLVM_SELFHOST_FLAGS），算进身份会让同一份源码在不同 worktree 生成
    # 不同身份的编译器，种子无法跨机复现。
    lld_identity = hashlib.sha256(json.dumps({
        "sdk": sdk_record["archives"], "bridge": digest(BRIDGE),
        "header": digest(BRIDGE_HEADER), "lld": digest(LLD_BRIDGE),
        "components": [path.name for path in libraries],
        "min_os": sdk_record["min_os"],
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    config_header = directory / "lld_link_config.h"
    # 自举闭包不再编进编译器：绝对路径随种子跨机器必然失效（Zig 式做法是
    # 让构建机在链接时给出配方），因此这里只写空闭包，真实参数落到
    # selfhost-flags.txt，由 seed-build.py 通过 YH_LLVM_SELFHOST_FLAGS 传给 yh。
    generate_lld_config(config_header, lld_identity, [])
    include = str(SDK_PREFIX / "include")
    common = ["-O2", "-Wall", "-Wextra", "-Werror", "-isysroot", sdk_record["sdk_root"],
              f"-mmacosx-version-min={sdk_record['min_os']}", "-I" + include]
    bridge_object = directory / "bridge.o"
    lld_object = directory / "lld_bridge.o"
    run([toolchain["clang"], "-std=c11", *common, "-I" + str(BRIDGE.parent),
         "-c", str(BRIDGE), "-o", str(bridge_object)], "compile-bridge")
    run([toolchain["clangxx"], "-std=c++17", *common, "-I" + str(directory),
         "-c", str(LLD_BRIDGE), "-o", str(lld_object)], "compile-lld-bridge")
    libtool = toolchain["libtool"]
    run([libtool, "-static", "-o", str(archive), str(bridge_object), str(lld_object)],
        "archive-bridge")
    return archive, flags, selfhost_flags, lld_identity


def linker_command(clangxx, lld, sdk_root, min_os, obj, output):
    """从 Apple clang 的真实 link argv 得到 SDK 参数，再交给固定 ld64.lld。"""
    result = run([clangxx, "-###", "-arch", "arm64", "-isysroot", sdk_root,
                  f"-mmacosx-version-min={min_os}", "-stdlib=libc++", str(obj),
                  "-o", str(output)], "apple-link-plan")
    for line in result.stderr.splitlines():
        try:
            argv = shlex.split(line)
        except ValueError:
            continue
        if argv and Path(argv[0]).name in ("ld", "ld64"):
            argv[0] = str(lld)
            filtered = []
            skip_next = False
            for item in argv:
                if skip_next:
                    skip_next = False
                    continue
                if item == "-lto_library":
                    skip_next = True
                    continue
                filtered.append(item)
            return filtered
    raise RuntimeError("Apple clang -### 输出中没有可复用的 Darwin 链接命令")


def probe_sdk_lld(sdk_record):
    """用固定 ld64.lld 解析 SDK 的 libc++/libSystem reexport 与 SDK 版本标签。"""
    directory = workdir()
    source = directory / "sdk-link-probe.cpp"
    object_file = directory / "sdk-link-probe.o"
    executable = directory / "sdk-link-probe"
    source.write_text("#include <string>\nint main() { std::string s(\"darwin\"); "
                      "return s == \"darwin\" ? 0 : 1; }\n", encoding="utf-8")
    toolchain = sdk_record["toolchain"]
    run([toolchain["clangxx"], "-std=c++17", "-arch", "arm64", "-isysroot",
         sdk_record["sdk_root"], f"-mmacosx-version-min={sdk_record['min_os']}",
         "-stdlib=libc++", "-c", str(source), "-o", str(object_file)],
        "compile-sdk-link-probe")
    lld = SDK_PREFIX / "bin/ld64.lld"
    run(linker_command(toolchain["clangxx"], str(lld), sdk_record["sdk_root"],
                       sdk_record["min_os"], object_file, executable),
        "link-sdk-probe", timeout=180)
    dependencies = run([toolchain["otool"], "-L", str(executable)],
                       "sdk-link-dependencies").stdout
    if "libSystem" not in dependencies or "libc++" not in dependencies:
        raise RuntimeError(f"固定 ld64.lld 未解析到 SDK 的 libSystem/libc++：{dependencies}")
    load_commands = run([toolchain["otool"], "-l", str(executable)],
                        "sdk-link-load-commands").stdout
    if not has_macos_build_version(load_commands):
        raise RuntimeError("固定 ld64.lld 输出缺少 macOS LC_BUILD_VERSION 标签")
    if f"sdk {sdk_record['sdk_version']}" not in load_commands:
        raise RuntimeError("固定 ld64.lld 输出没有保留 SDK 版本标签")
    return {"dependencies": dependencies.splitlines()[1:],
            "load_command": "LC_BUILD_VERSION", "sdk_version": sdk_record["sdk_version"]}


def probe_bridge(archive, flags, sdk_record):
    """执行真实静态桥，验证 v2 Mach-O 输出、坏 IR 诊断和旧文件保留。"""
    directory = workdir()
    source = directory / "bridge-probe.c"
    object_file = directory / "bridge-probe.o"
    executable = directory / "bridge-probe"
    emitted = directory / "emitted-arm64.o"
    retained = directory / "retained.o"
    source.write_text(f'''#include "bridge.h"
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {{
    if (argc != 2 || strcmp(yh_llvm_version(), "21.1.8") != 0) return 1;
    const char *path = argv[1];
    FILE *file = fopen(path, "wb");
    if (!file) return 2;
    const char old[] = "old output";
    if (fwrite(old, 1, sizeof(old), file) != sizeof(old) || fclose(file)) return 3;
    char diagnostic[8];
    if (yh_llvm_emit_v2("invalid", 7, "aarch64-apple-darwin", "14.0.0",
            0, 0, path, diagnostic, sizeof(diagnostic)) == 0) return 4;
    file = fopen(path, "rb");
    char check[sizeof(old)];
    if (!file || fread(check, 1, sizeof(check), file) != sizeof(check)
            || fclose(file) || memcmp(check, old, sizeof(old)) != 0) return 5;
    const char ir[] = "define i32 @probe() {{ ret i32 0 }}\\n";
    if (yh_llvm_emit_v2(ir, sizeof(ir) - 1, "aarch64-apple-darwin", "14.0.0",
            0, 0, path, diagnostic, sizeof(diagnostic)) != 0) return 6;
    return 0;
}}
''', encoding="utf-8")
    toolchain = sdk_record["toolchain"]
    run([toolchain["clang"], "-std=c11", "-Wall", "-Wextra", "-Werror",
         "-isysroot", sdk_record["sdk_root"],
         f"-mmacosx-version-min={sdk_record['min_os']}",
         "-I" + str(ROOT / "compiler/llvm"), "-c", str(source), "-o", str(object_file)],
        "compile-bridge-probe")
    command = [toolchain["clangxx"], str(object_file), str(archive), "-o", str(executable),
               *flags]
    run(command, "link-bridge-probe", timeout=300)
    run([str(executable), str(retained)], "run-bridge-probe", timeout=120)
    file_description = run(["file", str(retained)], "emitted-object-file").stdout
    if "Mach-O" not in file_description or "arm64" not in file_description:
        raise RuntimeError(f"Darwin v2 桥没有发射 ARM64 Mach-O 对象：{file_description}")
    load_commands = run([sdk_record["toolchain"]["otool"], "-l", str(retained)],
                        "emitted-object-load-commands").stdout
    if not has_macos_build_version(load_commands):
        raise RuntimeError("Darwin v2 桥对象缺少 macOS LC_BUILD_VERSION")
    dependencies = run([sdk_record["toolchain"]["otool"], "-L", str(executable)],
                       "bridge-probe-dependencies").stdout
    if "libLLVM" in dependencies or "libclang" in dependencies:
        raise RuntimeError(f"桥探针仍动态依赖 LLVM/Clang：{dependencies}")
    return {"emitted_object": file_description.strip(),
            "dependencies": dependencies.splitlines()[1:]}


def build_host(jobs):
    """构建固定 SDK、桥归档、真实 emitter 与 lld SDK 链接探针。"""
    if platform.system() != "Darwin" or platform.machine() not in ("arm64", "aarch64"):
        raise RuntimeError("Darwin LLVM host 只能在原生 Darwin/ARM64 上构建")
    if not check(full=True):
        return json.loads((workdir() / "host.json").read_text(encoding="utf-8"))
    result = run([sys.executable, str(SDK_BUILDER), "build", "--min-os",
                  os.environ.get("MACOSX_DEPLOYMENT_TARGET", MIN_OS), "--jobs", str(jobs)],
                 "build-sdk")
    prefix = Path(result.stdout.strip().splitlines()[-1])
    if prefix.resolve() != SDK_PREFIX.resolve():
        raise RuntimeError(f"SDK 构建器返回了非锁定目录：{prefix}")
    sdk_record = load_sdk_record()
    libraries = llvm_archives(sdk_record)
    archive, flags, selfhost_flags, lld_identity = compile_bridge(sdk_record, libraries)
    lld_probe = probe_sdk_lld(sdk_record)
    bridge_probe = probe_bridge(archive, flags, sdk_record)
    record = {
        "host": HOST, "llvm_version": "21.1.8", "bridge_abi": 2,
        "sdk_host_sha256": digest(SDK_RECORD), "manifest_sha256": digest(MANIFEST),
        "host_builder_sha256": host_recipe_digest(),
        "sdk_builder_sha256": sdk_recipe_digest(),
        "bridge_source_sha256": digest(BRIDGE), "bridge_header_sha256": digest(BRIDGE_HEADER),
        "lld_bridge_source_sha256": digest(LLD_BRIDGE), "bridge_sha256": digest(archive),
        "bridge_archive": describe(archive),
        "sdk_prefix": describe(SDK_PREFIX),
        "llvm_archives": {path.name: digest(path) for path in libraries},
        "lld_archives": {name: digest(SDK_PREFIX / "lib" / name) for name in LLD_ARCHIVES},
        "link_flags": flags, "selfhost_link_flags": selfhost_flags,
        "lld_identity": lld_identity,
        "sdk_link_probe": lld_probe, "bridge_probe": bridge_probe,
        "toolchain": sdk_record["toolchain"], "sdk_root": sdk_record["sdk_root"],
        "sdk_version": sdk_record["sdk_version"], "min_os": sdk_record["min_os"],
    }
    # 闭包文件与 host.json 同目录，并记录其摘要；种子只保留 compiler 本体，
    # 绝对路径永远来自构建机的这次 prepare。
    write_cxx_stub(record)
    write_selfhost_flags(record)
    (workdir() / "host.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def check(full=True):
    """核对 host 配置与当前桥/SDK身份；full 模式同时重算静态库摘要。"""
    path = workdir() / "host.json"
    if not path.is_file():
        return [f"缺少 Darwin LLVM host 身份记录：{describe(path)}"]
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        sdk = json.loads(SDK_RECORD.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"Darwin LLVM host 身份记录不可读：{error}"]
    problems = []
    if record.get("host") != HOST or record.get("manifest_sha256") != digest(MANIFEST):
        problems.append("host 键或 SDK 锁文件已变化")
    if record.get("host_builder_sha256") != host_recipe_digest():
        problems.append("Darwin LLVM host 构建器已变化")
    if record.get("sdk_builder_sha256") != sdk_recipe_digest():
        problems.append("Darwin LLVM SDK 构建器已变化")
    if record.get("sdk_host_sha256") != digest(SDK_RECORD):
        problems.append("固定 Darwin SDK 身份已变化")
    if record.get("bridge_source_sha256") != digest(BRIDGE):
        problems.append("compiler/llvm/bridge.c 已变化")
    if record.get("bridge_header_sha256") != digest(BRIDGE_HEADER):
        problems.append("compiler/llvm/bridge.h 已变化")
    if record.get("lld_bridge_source_sha256") != digest(LLD_BRIDGE):
        problems.append("compiler/llvm/lld_bridge.cpp 已变化")
    flags_file = ROOT / record.get("selfhost_flags_file", "")
    if not record.get("selfhost_flags_file") or not flags_file.is_file():
        problems.append("Darwin 自举闭包文件缺失（需要重新 prepare）")
    elif full and digest(flags_file) != record.get("selfhost_flags_sha256"):
        problems.append("Darwin 自举闭包文件摘要错误")
    runtime_file = ROOT / record.get("selfhost_runtime_file", "")
    if not record.get("selfhost_runtime_file") or not runtime_file.is_file():
        problems.append("Darwin 运行库参数文件缺失（需要重新 prepare）")
    elif full and digest(runtime_file) != record.get("selfhost_runtime_sha256"):
        problems.append("Darwin 运行库参数文件摘要错误")
    archive = ROOT / record.get("bridge_archive", "")
    if not archive.is_file() or (full and digest(archive) != record.get("bridge_sha256")):
        problems.append("Darwin LLVM 桥归档缺失或摘要错误")
    cxx = ROOT / record.get("cxx_tbd", "")
    if not record.get("cxx_tbd") or not cxx.is_file():
        problems.append("Darwin 闭包缺少 libc++ 文本 stub（需要重新 prepare）")
    elif full and digest(cxx) != record.get("cxx_tbd_sha256"):
        problems.append("Darwin 闭包 libc++ 文本 stub 摘要错误")
    for name, expected in {**record.get("llvm_archives", {}),
                           **record.get("lld_archives", {})}.items():
        item = SDK_PREFIX / "lib" / name
        if not item.is_file() or (full and digest(item) != expected):
            problems.append(f"Darwin LLVM/lld 静态库缺失或摘要错误：{name}")
    for name, expected in sdk.get("tools", {}).items():
        item = SDK_PREFIX / "bin" / name
        if not item.is_file() or (full and digest(item) != expected):
            problems.append(f"Darwin LLVM SDK 工具缺失或摘要错误：{name}")
    if sdk.get("source_sha256") != "4633a23617fa31a3ea51242586ea7fb1da7140e426bd62fc164261fe036aa142":
        problems.append("Darwin SDK 源码不是锁定的 LLVM 21.1.8")
    if sdk.get("builder_sha256") != sdk_recipe_digest():
        problems.append("Darwin LLVM SDK 构建器身份已变化")
    return problems


def ensure(mode):
    """准备 host；auto 仅复用本地固定源码包，不会触发网络下载。

    第一步只读 `.sealed-<host>.json` 标记：命中就直接返回记录，不再校验归档、
    也不改写缓存（构建一次之后其余构建都是只读快路径）。
    """
    record_path = workdir() / "host.json"
    sealed = closure_stamp_ok(HOST, record_path,
                             [shim_path(), selfhost_flags_path(),
                              selfhost_runtime_path()])
    if sealed is not None:
        return sealed
    problems = check(full=False)
    if not problems:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        closure_stamp_write(HOST, record_path)
        return record
    source = runpy.run_path(str(SDK_BUILDER))["source_archive_path"]()
    if mode == "auto" and not Path(source).is_file():
        raise NotReady("；".join(problems) + "；本地缺少固定源码包，auto 模式不联网下载")
    record = build_host(int(os.environ.get("LLVM_JOBS", "2")))
    closure_stamp_write(HOST, record_path)
    return record


def write_shim(record):
    """生成只在本次编译器构建环境使用的 clang 链接包装器。"""
    directory = workdir() / "shim"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "clang"
    text = f'''#!/usr/bin/env python3
"""由 tools/llvm-darwin-host.py 生成的编译器自举链接包装器。"""
import os
import sys
os.execv(sys.executable, [sys.executable, {str(Path(__file__).resolve())!r},
                          "link", "--", *sys.argv[1:]])
'''
    if not path.is_file() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def command_link(argv):
    """编译类调用透传 Apple clang；最终链接仅追加固定 SDK 的静态桥。"""
    record = ensure("auto")
    if is_compile_call(argv):
        arguments = compile_argv(argv, record["min_os"])
        os.execv(record["toolchain"]["clang"], [record["toolchain"]["clang"], *arguments])
    if is_driver_query(argv):
        os.execv(record["toolchain"]["clang"], [record["toolchain"]["clang"], *argv])
    command = link_argv(argv, record["link_flags"])
    os.execv(record["toolchain"]["clangxx"], [record["toolchain"]["clangxx"], *command])


def split_passthrough(argv):
    """在第一个 `--` 处切分驱动参数与透传参数（兼容不同 Python 的 argparse）。"""
    argv = list(argv)
    if "--" not in argv:
        return argv, []
    cut = argv.index("--")
    return argv[:cut], argv[cut + 1:]


def main(argv):
    """提供 prepare/status/shim/link 四种 Makefile 与 seed-build 操作。"""
    head, passthrough = split_passthrough(argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "status", "shim", "link"))
    parser.add_argument("--host", choices=(HOST,), default=HOST)
    parser.add_argument("--mode", choices=("auto", "require"), default="auto")
    parser.add_argument("--jobs", type=int, default=int(os.environ.get("LLVM_JOBS", "2")))
    parser.add_argument("tail", nargs="*", help="传给 Apple clang 的原始调用参数")
    args = parser.parse_args(head)
    if args.command == "link":
        command_link(list(args.tail) + passthrough)
    if args.command == "status":
        problems = check(full=True)
        if problems:
            raise NotReady("；".join(problems))
        record = json.loads((workdir() / "host.json").read_text(encoding="utf-8"))
        print(json.dumps({"host": HOST, "ready": True,
                          "bridge_sha256": record["bridge_sha256"],
                          "sdk_host_sha256": record["sdk_host_sha256"],
                          "probe": record["bridge_probe"]}, ensure_ascii=False))
        return 0
    if args.command == "shim":
        record = ensure(args.mode)
        print(json.dumps({"host": HOST, "shim_dir": str(write_shim(record).parent),
                          "bridge_sha256": record["bridge_sha256"],
                          "selfhost_flags": str(selfhost_flags_path()),
                          "selfhost_runtime": str((ROOT / record["selfhost_runtime_file"]).resolve())
                          if record.get("selfhost_runtime_file") else "",
                          "sdk_host_sha256": record["sdk_host_sha256"]}, ensure_ascii=False))
        return 0
    if args.command == "prepare":
        if args.jobs < 1:
            raise RuntimeError("LLVM 并行构建数必须大于零")
        # 幂等：先看“已封装”标记（第一步检测）。命中就直接复用，不再校验归档、
        # 也不改写缓存；只有标记缺失/配方变化时才做一次全量校验。
        record_path = workdir() / "host.json"
        sealed = closure_stamp_ok(HOST, record_path,
                                 [shim_path(), selfhost_flags_path(),
                                  selfhost_runtime_path()])
        if sealed is not None:
            print(json.dumps({"host": HOST, "reused": True,
                              "bridge_sha256": sealed["bridge_sha256"],
                              "sdk_host_sha256": sealed["sdk_host_sha256"],
                              "probe": sealed["bridge_probe"]}, ensure_ascii=False))
            return 0
        problems = check(full=True)
        if not problems:
            closure_stamp_write(HOST, record_path)
            record = json.loads(record_path.read_text(encoding="utf-8"))
            print(json.dumps({"host": HOST, "reused": True,
                              "bridge_sha256": record["bridge_sha256"],
                              "sdk_host_sha256": record["sdk_host_sha256"],
                              "probe": record["bridge_probe"]}, ensure_ascii=False))
            return 0
        record = build_host(args.jobs)
        closure_stamp_write(HOST, record_path)
        print(json.dumps({"host": HOST, "bridge_sha256": record["bridge_sha256"],
                          "sdk_host_sha256": record["sdk_host_sha256"],
                          "probe": record["bridge_probe"]}, ensure_ascii=False))
        return 0
    raise RuntimeError(f"未知 host 子命令：{args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except NotReady as error:
        print(f"Darwin LLVM host 尚未准备：{error}\n"
              "准备命令：python3 tools/llvm-darwin-host.py prepare --jobs 2", file=sys.stderr)
        raise SystemExit(NOT_READY)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Darwin LLVM host：{error}", file=sys.stderr)
        raise SystemExit(1)
