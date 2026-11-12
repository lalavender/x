#!/usr/bin/env python3
"""构建并验收 yh 的 Darwin/ARM64 静态 LLVM/lld SDK。"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 本文件既可直接运行，也会被 runpy.run_path（自举门禁）加载；两种方式下都要
# 先把 tools/ 放进 sys.path，才能 import 同目录的 llvm_recipe。
sys.path.insert(0, str(ROOT / "tools"))
from llvm_recipe import sdk_recipe_digest  # noqa: E402  固定闭包配方摘要
from llvm_cache import cache_root  # noqa: E402  闭包根唯一来源（项目外）
WORK = cache_root() / "darwin-sdk"
MANIFEST = ROOT / "vendor/llvm/sdk.lock.json"
DEFAULT_MIN_OS = "14.0.0"
MIN_FREE_BYTES = 8 * 1024**3
MIN_BUILD_FREE_BYTES = 5 * 1024**3
MIN_REPACK_FREE_BYTES = 2 * 1024**3

# 空间不足时给出的清理建议（只列仓库内可安全删除的构建缓存）。
CLEANUP_HINT = ("可清理：~/Library/Caches/yh（YH_CACHE 全局缓存）、"
                "tmp/modcheck、tmp/fx-*、compiler/.build、.codegraph；"
                "或用 YH_LLVM_CACHE 把闭包缓存指到别的磁盘")


def select_host(system=None, machine=None):
    """只接受当前首期可原生运行桥的 Darwin/ARM64 宿主。"""
    system = platform.system() if system is None else system
    machine = platform.machine() if machine is None else machine
    if system == "Darwin" and machine in ("arm64", "aarch64"):
        return "darwin-aarch64"
    raise RuntimeError(f"Darwin LLVM SDK 当前只支持 Darwin/ARM64 宿主，收到 {system}/{machine}")


def parse_min_os(value):
    """校验并规范 MACOSX_DEPLOYMENT_TARGET 为三段十进制版本。"""
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)(?:\.([0-9]+))?", value or "")
    if not match:
        raise RuntimeError(f"最低 macOS 版本格式无效：{value!r}，需要 major.minor[.patch]")
    major, minor, patch = (int(part or 0) for part in match.groups())
    if major <= 0 or minor < 0 or patch < 0:
        raise RuntimeError(f"最低 macOS 版本组件无效：{value!r}")
    return f"{major}.{minor}.{patch}"


def source_spec():
    """读取锁定的 Darwin LLVM 源码包，并核验版本、URL 与摘要格式。"""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    spec = manifest.get("darwin_source", {})
    if manifest.get("llvm_version") != "21.1.8" or not spec.get("url"):
        raise RuntimeError("SDK 清单缺少固定 LLVM 21.1.8 Darwin 源码包")
    if not re.fullmatch(r"[0-9a-f]{64}", spec.get("sha256", "")):
        raise RuntimeError("SDK 清单中的 LLVM 源码 SHA-256 格式无效")
    return spec


def build_spec():
    """读取必须随 LLVM 源码版本一起锁定的 Darwin CMake 构建配置。"""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    spec = manifest.get("darwin_build", {})
    if spec.get("deployment_target") != DEFAULT_MIN_OS:
        raise RuntimeError("Darwin SDK 默认部署版本与锁定构建配置不一致")
    if (spec.get("projects") != ["clang", "lld"]
            or spec.get("targets") != ["AArch64", "X86"]
            or spec.get("architectures") != ["arm64"]):
        raise RuntimeError("Darwin SDK 项目或后端目标与固定闭包不一致")
    disabled = ("build_shared_libs", "llvm_build_llvm_dylib", "llvm_build_llvm_c_dylib",
                "llvm_link_llvm_dylib", "enable_zlib", "enable_zstd", "enable_libxml2",
                "include_tests", "include_examples", "include_benchmarks", "include_docs")
    if spec.get("build_type") != "Release" or any(spec.get(key) is not False for key in disabled):
        raise RuntimeError("Darwin LLVM SDK 必须是 Release、纯静态且关闭可选依赖/测试")
    return spec


def digest(path):
    """分块计算源归档或 SDK 静态库摘要。"""
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verify_archive(path, spec):
    """在解包前同时核对固定源归档字节数和 SHA-256。"""
    path = Path(path)
    if not path.is_file():
        raise RuntimeError(f"LLVM 源码包不存在：{path}")
    if path.stat().st_size != spec["size_bytes"]:
        raise RuntimeError("LLVM 源码包字节数与固定发行包不符")
    if digest(path) != spec["sha256"]:
        raise RuntimeError("LLVM 源码包 SHA-256 与固定发行包不符")
    return path


def load_sdk_version(sdk_root):
    """从 Apple SDKSettings.json 读取 SDK 版本并拒绝非 macOS SDK。"""
    settings_path = Path(sdk_root) / "SDKSettings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"无法读取 Apple SDK 元数据 {settings_path}: {error}") from error
    version = settings.get("Version")
    canonical = settings.get("CanonicalName", "")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", version):
        raise RuntimeError("SDKSettings.json 缺少有效的 Version")
    if canonical and not canonical.startswith("macosx"):
        raise RuntimeError(f"SDK 不是 macOS SDK：{canonical}")
    return version


# 固定 LLVM 21.1.8 的 lld TAPI 解析器不认识 SDK 27 的 arm64e.x1 目标标签；
# 与 tools/llvm-darwin-sdk-bundle.py 的 KNOWN_UNSUPPORTED 保持同一条边界。
UNSUPPORTED_TAPI_TARGET = "arm64e.x1"


def reject_incompatible_sdk(root):
    """在解析 SDK 时立刻拒绝固定 lld 解析不了的目标标签。

    否则要等 LLVM 构建数十分钟后、在 lld 链接探针上才发现，代价太高。
    """
    for name in ("usr/lib/libSystem.tbd", "usr/lib/libc++.tbd"):
        path = Path(root) / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if UNSUPPORTED_TAPI_TARGET in text:
            raise RuntimeError(
                f"SDK 的 {name} 含 {UNSUPPORTED_TAPI_TARGET}：固定 lld 21 无法解析；"
                "请把 SDKROOT 指向 26.x SDK（例如 MacOSX26.5.sdk）")


def _accept_sdk(root):
    """校验候选 SDK：版本可读且不含固定 lld 解析不了的目标标签。"""
    load_sdk_version(root)
    reject_incompatible_sdk(root)


def xcode_sdk_candidates():
    """按版本从新到旧列出 Xcode 自带的 macOS SDK（26.x 等）。

    Command Line Tools 通常只有最新一个 SDK；当它与固定 LLVM 21.1.8 的 lld
    不兼容（例如 27 的 `arm64e.x1`）时，需要回退到 Xcode 里的旧 SDK。
    这里只做「列出候选」，是否可用仍由 _accept_sdk 判定。
    """
    pattern = "Xcode*.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX*.sdk"
    found = sorted(Path("/Applications").glob(pattern))
    if not found:
        return []
    def version_key(path):
        match = re.search(r"MacOSX([0-9]+)(?:\.([0-9]+))?", path.name)
        if not match:
            return (0, 0)
        return (int(match.group(1)), int(match.group(2) or 0))
    return sorted(found, key=version_key, reverse=True)


def resolve_sdk_root(environment=None, system=None, machine=None, run=None):
    """解析可用的 macOS SDK。

    顺序：显式 SDKROOT → xcrun 默认 -sdk → Xcode 自带 SDK（从新到旧）。
    默认 SDK 不兼容固定 lld（`arm64e.x1` 等）时自动回退，并在 stderr 说明
    实际使用的 SDK，避免使用者手工设置 SDKROOT。
    """
    environment = os.environ if environment is None else environment
    explicit = environment.get("SDKROOT", "").strip()
    if explicit:
        root = Path(explicit).expanduser().resolve()
        _accept_sdk(root)
        return root
    select_host(system, machine)
    run = subprocess.run if run is None else run
    result = run(["xcrun", "--sdk", "macosx", "--show-sdk-path"],
                 capture_output=True, text=True, check=False)
    if result.returncode == 0 and result.stdout.strip():
        root = Path(result.stdout.strip()).resolve()
        try:
            _accept_sdk(root)
            return root
        except RuntimeError as error:
            default_error = error
    else:
        default_error = RuntimeError("未找到 macOS SDK；设置 SDKROOT 或安装 Xcode Command Line Tools")
    for candidate in xcode_sdk_candidates():
        try:
            _accept_sdk(candidate)
        except RuntimeError:
            continue
        print(f"提示：默认 SDK 不适用于固定 LLVM（{default_error}）；改用 {candidate}",
              file=sys.stderr)
        return candidate.resolve()
    raise default_error


def source_archive_path():
    """返回固定源码包的 tmp 缓存路径，避免复用用户安装的 Homebrew 组件。"""
    return WORK / source_spec()["package"]


def download_source():
    """只下载清单锁定的 LLVM 源码，并在原子改名之前验证字节数与摘要。"""
    spec = source_spec()
    WORK.mkdir(parents=True, exist_ok=True)
    package = source_archive_path()
    if package.exists():
        return verify_archive(package, spec)
    temporary = package.with_suffix(package.suffix + ".download")
    try:
        with urllib.request.urlopen(spec["url"], timeout=60) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        verify_archive(temporary, spec)
        temporary.replace(package)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return package


def run_logged(command, cwd, logfile):
    """执行固定构建命令并把完整输出写入 tmp，错误时报告日志位置。"""
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    Path(logfile).write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"命令失败（{result.returncode}）：{' '.join(map(str, command))}；日志：{logfile}")
    return result.stdout + result.stderr


def sdk_toolchain():
    """解析构建和验收使用的 Apple 工具绝对路径及编译器版本。"""
    paths = {}
    for name, command in (("clang", ["xcrun", "--find", "clang"]),
                          ("clangxx", ["xcrun", "--find", "clang++"]),
                          ("ar", ["xcrun", "--find", "ar"]),
                          ("libtool", ["xcrun", "--find", "libtool"]),
                          ("lipo", ["xcrun", "--find", "lipo"]),
                          ("otool", ["xcrun", "--find", "otool"])):
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode or not result.stdout.strip():
            raise RuntimeError(f"Apple 工具链缺少 {name}：{' '.join(command)}")
        paths[name] = result.stdout.strip()
    cmake = shutil.which("cmake")
    if not cmake:
        raise RuntimeError("缺少 CMake；请安装 CMake 后重试")
    paths["cmake"] = str(Path(cmake).resolve())
    ninja = shutil.which("ninja")
    if not ninja:
        raise RuntimeError("缺少 Ninja；Darwin LLVM SDK 使用 Ninja 构建")
    paths["ninja"] = str(Path(ninja).resolve())
    paths["versions"] = {}
    for name in ("clang", "clangxx", "cmake", "ninja"):
        result = subprocess.run([paths[name], "--version"], capture_output=True,
                                text=True, check=False)
        if result.returncode:
            raise RuntimeError(f"无法读取固定 SDK 工具链版本：{paths[name]}")
        paths["versions"][name] = result.stdout.splitlines()[0]
    return paths


def verify_artifacts(record, prefix):
    """逐个校验身份记录里的静态归档、固定工具与许可证摘要。"""
    for directory, key in (("lib", "archives"), ("bin", "tools")):
        for name, expected in record.get(key, {}).items():
            item = prefix / directory / name
            if not item.is_file() or digest(item) != expected:
                return False
    for name, expected in record.get("licenses", {}).items():
        item = prefix / name
        if not item.is_file() or digest(item) != expected:
            return False
    return True


def recipe_matches(record, sdk_root, toolchain):
    """判定已有 SDK 与当前配方是否一致：只认真正决定产物的三项。

    刻意不含 `vendor/llvm/sdk.lock.json` 的整文件摘要：同一份锁文件同时钉住
    Windows 闭包，那边加段或重排格式就会让整文件摘要变化，从而把完好的 Darwin
    SDK 判成过期、每次构建重编整棵 LLVM（实测约 30 分钟）。产物真正的输入是
    `darwin_build` 构建规格（`build_spec()`）、Apple SDK 设置与工具链。
    """
    return (record.get("build_configuration") == build_spec()
            and record.get("sdk_settings_sha256") == digest(Path(sdk_root) / "SDKSettings.json")
            and record.get("toolchain") == toolchain)


def build_sdk(min_os, jobs):
    """从固定完整源码构建 X86/AArch64 LLVM、clang oracle 与 ELF/Mach-O/COFF lld。"""
    host = select_host()
    min_os = parse_min_os(min_os)
    sdk_root = resolve_sdk_root()
    sdk_version = load_sdk_version(sdk_root)
    toolchain = sdk_toolchain()
    package = download_source()
    source = WORK / "source-llvm-project-21.1.8.src"
    build = WORK / "build-llvm-project-21.1.8"
    prefix = WORK / "sdk-darwin-aarch64"
    marker = source / ".yh-source-sha256"
    extracted_source = marker.is_file() and marker.read_text().strip() == source_spec()["sha256"]

    reusable_prefix = prefix.exists()
    reusable_build = extracted_source and (build / "CMakeCache.txt").is_file()
    if reusable_prefix:
        record_path = prefix / "host.json"
        if not record_path.is_file():
            raise RuntimeError(f"SDK 输出目录已存在但缺少身份记录，保留现场：{prefix}")
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError(f"SDK 身份记录不可读，保留现场：{error}") from error
        if (record.get("source_sha256") != source_spec()["sha256"]
                or record.get("min_os") != min_os
                or record.get("sdk_root") != str(sdk_root)
                or record.get("sdk_version") != sdk_version):
            raise RuntimeError(f"已有 Darwin SDK 的源码/目标/Apple SDK 不同，保留现场：{prefix}")
        # 配方（怎么编译）与产物（编译结果）分开校验：recipe 覆盖 Darwin 构建规格、
        # Apple SDK 设置和工具链；builder_sha256 只是构建器源码摘要。
        recipe = recipe_matches(record, sdk_root, toolchain)
        artifacts_ok = recipe and verify_artifacts(record, prefix)
        if artifacts_ok and record.get("builder_sha256") == sdk_recipe_digest():
            return prefix
        if artifacts_ok:
            # 构建器源码改过、但配方与全部产物摘要逐一致：只重写身份记录。
            # 旧逻辑在这里会重新 configure 并重跑整棵 LLVM 的增量编译——重写生成
            # 头文件会让 2748 个目标全部重编（实测约 30 分钟、需要数 GiB 磁盘），
            # 对「只改 SDK 解析顺序 / 诊断文案」这类构建器改动得不偿失；
            # 而配方与产物都已逐个校验，锁文件仍然钉住版本与构建配置。
            write_host_record(host, min_os, sdk_root, sdk_version, toolchain, package, prefix)
            return prefix

    usage = shutil.disk_usage(ROOT)
    minimum_free = (MIN_REPACK_FREE_BYTES if reusable_prefix or reusable_build else
                    MIN_BUILD_FREE_BYTES if extracted_source else MIN_FREE_BYTES)
    if usage.free < minimum_free:
        raise RuntimeError(f"磁盘剩余空间不足：需要至少 {minimum_free // 1024**3} GiB，"
                           f"当前 {usage.free // 1024**3} GiB；未解包或修改已有目录。"
                           + CLEANUP_HINT)

    if source.exists() and (not marker.is_file() or marker.read_text().strip() != source_spec()["sha256"]):
        raise RuntimeError(f"源码目录已存在但身份不匹配，保留现场并另选 tmp 路径：{source}")
    if not marker.is_file():
        source.parent.mkdir(parents=True, exist_ok=True)
        run_logged(["tar", "-xf", str(package), "-C", str(WORK)], ROOT,
                   WORK / "extract.log")
        extracted = WORK / "llvm-project-21.1.8.src"
        extracted.rename(source)
        marker.write_text(source_spec()["sha256"] + "\n", encoding="ascii")
    usage = shutil.disk_usage(ROOT)
    if usage.free < minimum_free:
        raise RuntimeError(f"准备构建/重打包后剩余空间不足：需要至少 {minimum_free // 1024**3} GiB "
                           f"用于构建与归档，当前 {usage.free // 1024**3} GiB；源码保留在 {source}。"
                           + CLEANUP_HINT)

    config = build_spec()
    configure = [toolchain["cmake"], "-S", str(source / "llvm"), "-B", str(build), "-G", "Ninja",
                 f"-DCMAKE_MAKE_PROGRAM={toolchain['ninja']}",
                 f"-DCMAKE_BUILD_TYPE={config['build_type']}", f"-DCMAKE_C_COMPILER={toolchain['clang']}",
                 f"-DCMAKE_CXX_COMPILER={toolchain['clangxx']}",
                 f"-DCMAKE_AR={toolchain['ar']}", f"-DCMAKE_OSX_SYSROOT={sdk_root}",
                 f"-DCMAKE_OSX_DEPLOYMENT_TARGET={min_os}",
                 f"-DCMAKE_OSX_ARCHITECTURES={';'.join(config['architectures'])}",
                 f"-DCMAKE_INSTALL_PREFIX={prefix}",
                 f"-DLLVM_ENABLE_PROJECTS={';'.join(config['projects'])}",
                 f"-DLLVM_TARGETS_TO_BUILD={';'.join(config['targets'])}",
                 "-DLLVM_ENABLE_ASSERTIONS=OFF",
                 f"-DLLVM_INCLUDE_TESTS={'ON' if config['include_tests'] else 'OFF'}",
                 f"-DLLVM_INCLUDE_EXAMPLES={'ON' if config['include_examples'] else 'OFF'}",
                 f"-DLLVM_INCLUDE_BENCHMARKS={'ON' if config['include_benchmarks'] else 'OFF'}",
                 f"-DLLVM_INCLUDE_DOCS={'ON' if config['include_docs'] else 'OFF'}",
                 f"-DLLVM_BUILD_LLVM_DYLIB={'ON' if config['llvm_build_llvm_dylib'] else 'OFF'}",
                 f"-DLLVM_BUILD_LLVM_C_DYLIB={'ON' if config['llvm_build_llvm_c_dylib'] else 'OFF'}",
                 f"-DLLVM_LINK_LLVM_DYLIB={'ON' if config['llvm_link_llvm_dylib'] else 'OFF'}",
                 f"-DLLVM_ENABLE_ZLIB={'ON' if config['enable_zlib'] else 'OFF'}",
                 f"-DLLVM_ENABLE_ZSTD={'ON' if config['enable_zstd'] else 'OFF'}",
                 f"-DLLVM_ENABLE_LIBXML2={'ON' if config['enable_libxml2'] else 'OFF'}",
                 f"-DBUILD_SHARED_LIBS={'ON' if config['build_shared_libs'] else 'OFF'}",
                 "-DLLD_BUILD_TOOLS=ON", "-DCLANG_BUILD_TOOLS=ON"]
    WORK.mkdir(parents=True, exist_ok=True)
    run_logged(configure, ROOT, WORK / "configure.log")
    run_logged([toolchain["cmake"], "--build", str(build), "--target", "clang", "opt", "lld",
                "llvm-config",
                "--parallel", str(jobs)], ROOT, WORK / "build.log")
    package_sdk(source, build, prefix)
    write_host_record(host, min_os, sdk_root, sdk_version, toolchain, package, prefix)
    return prefix


def package_sdk(source, build, prefix):
    """收集构建出的所有 LLVM/lld 静态归档、头文件和固定 oracle 工具。"""
    prefix.mkdir(parents=True, exist_ok=True)
    (prefix / "lib").mkdir(exist_ok=True)
    (prefix / "include").mkdir(exist_ok=True)
    (prefix / "bin").mkdir(exist_ok=True)
    libraries = sorted((build / "lib").glob("*.a"))
    if not libraries:
        raise RuntimeError("LLVM 构建目录没有静态归档")
    current_libraries = {library.name for library in libraries}
    for old in (prefix / "lib").glob("*.a"):
        if old.name not in current_libraries:
            old.unlink()
    for library in libraries:
        shutil.copy2(library, prefix / "lib" / library.name)
    for project in ("llvm", "clang", "lld"):
        source_include = source / project / "include" / project
        if source_include.is_dir():
            shutil.copytree(source_include, prefix / "include" / project,
                            dirs_exist_ok=True)
        generated_include = build / "include" / project
        if generated_include.is_dir():
            shutil.copytree(generated_include, prefix / "include" / project,
                            dirs_exist_ok=True)
    llvm_c_headers = source / "llvm" / "include" / "llvm-c"
    if llvm_c_headers.is_dir():
        shutil.copytree(llvm_c_headers, prefix / "include" / "llvm-c",
                        dirs_exist_ok=True)
    for project in ("clang", "opt", "llvm-config", "ld.lld", "ld64.lld"):
        executable = build / "bin" / project
        if not executable.is_file():
            raise RuntimeError(f"LLVM 构建目录缺少固定工具：{executable}")
        shutil.copy2(executable, prefix / "bin" / project)
    resource = build / "lib" / "clang" / "21" / "include"
    if resource.is_dir():
        shutil.copytree(resource, prefix / "lib" / "clang" / "21" / "include",
                        dirs_exist_ok=True)


def write_host_record(host, min_os, sdk_root, sdk_version, toolchain, package, prefix):
    """记录源码、SDK、部署版本、工具链和实际静态归档身份。"""
    libraries = sorted(path for path in (prefix / "lib").glob("*.a") if path.is_file())
    if not any(path.name.startswith("libLLVM") for path in libraries):
        raise RuntimeError("Darwin SDK 没有安装 LLVM 静态归档")
    for library in libraries:
        architecture = subprocess.run([toolchain["lipo"], "-archs", str(library)],
                                      capture_output=True, text=True, check=True).stdout.split()
        if architecture != ["arm64"]:
            raise RuntimeError(f"Darwin 静态库不是纯 arm64：{library.name} {architecture}")
    for required in ("liblldCommon.a", "liblldELF.a", "liblldMachO.a", "liblldCOFF.a"):
        if not (prefix / "lib" / required).is_file():
            raise RuntimeError(f"Darwin SDK 缺少 lld 静态驱动：{required}")
    required_tools = ("clang", "opt", "llvm-config", "ld.lld", "ld64.lld")
    missing = [name for name in required_tools if not (prefix / "bin" / name).is_file()]
    if missing:
        raise RuntimeError(f"Darwin SDK 缺少固定 oracle 工具：{missing}")
    for name in required_tools:
        dependencies = subprocess.run([toolchain["otool"], "-L", str(prefix / "bin" / name)],
                                      capture_output=True, text=True, check=True).stdout
        if "libLLVM" in dependencies or "libclang" in dependencies:
            raise RuntimeError(f"SDK 工具 {name} 意外动态依赖 LLVM/Clang")
        architecture = subprocess.run([toolchain["lipo"], "-archs", str(prefix / "bin" / name)],
                                      capture_output=True, text=True, check=True).stdout.split()
        if architecture != ["arm64"]:
            raise RuntimeError(f"SDK 工具不是纯 arm64：{name} {architecture}")
    tool_versions = {}
    for name in required_tools:
        result = subprocess.run([str(prefix / "bin" / name), "--version"],
                                 capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError(f"SDK 工具无法报告版本：{name}")
        version_line = next((line.strip() for line in result.stdout.splitlines()
                             if "21.1.8" in line), "")
        if not version_line:
            raise RuntimeError(f"SDK 工具版本不符合 LLVM 21.1.8：{name} {result.stdout[:200]}")
        tool_versions[name] = version_line
    record = {"host": host, "llvm_version": "21.1.8",
              "source_package": source_spec()["package"],
              "source_sha256": source_spec()["sha256"], "sdk_version": sdk_version,
              "sdk_settings_sha256": digest(Path(sdk_root) / "SDKSettings.json"),
              "sdk_root": str(sdk_root), "min_os": min_os, "toolchain": toolchain,
              "builder_sha256": sdk_recipe_digest(),
              "build_configuration": build_spec(),
              "tool_versions": tool_versions,
              "tools": {name: digest(prefix / "bin" / name) for name in required_tools},
              "archives": {path.name: digest(path) for path in libraries},
              "license_files": ["share/LICENSE-LLVM", "share/LICENSE-Clang", "share/LICENSE-lld"]}
    share = prefix / "share"
    share.mkdir(parents=True, exist_ok=True)
    for project, filename in (("llvm", "LICENSE-LLVM"), ("clang", "LICENSE-Clang"),
                              ("lld", "LICENSE-lld")):
        source_license = WORK / "source-llvm-project-21.1.8.src" / project / "LICENSE.TXT"
        if not source_license.is_file():
            source_license = WORK / "source-llvm-project-21.1.8.src" / project / "LICENSE"
        if source_license.is_file():
            shutil.copyfile(source_license, share / filename)
        else:
            raise RuntimeError(f"Darwin SDK 缺少许可证：{source_license}")
    record["licenses"] = {name: digest(prefix / name) for name in record["license_files"]}
    output = prefix / "host.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(output)


def preflight():
    """只读验证宿主、SDK 元数据、部署版本与锁包，不触发下载或构建。"""
    host = select_host()
    sdk_root = resolve_sdk_root()
    sdk_version = load_sdk_version(sdk_root)
    min_os = parse_min_os(os.environ.get("MACOSX_DEPLOYMENT_TARGET", DEFAULT_MIN_OS))
    spec = source_spec()
    result = {"host": host, "sdk_root": str(sdk_root), "sdk_version": sdk_version,
              "min_os": min_os, "source_package": spec["package"],
              "source_sha256": spec["sha256"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    """提供只读 preflight 与固定源码完整 SDK 构建两种操作。"""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight", help="核对当前宿主和 Apple SDK，不下载源码")
    build = subparsers.add_parser("build", help="构建 LLVM/lld Darwin 静态 SDK")
    build.add_argument("--min-os", default=os.environ.get("MACOSX_DEPLOYMENT_TARGET", DEFAULT_MIN_OS))
    build.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.command == "preflight":
        preflight()
        return
    if args.jobs < 1:
        raise RuntimeError("并行构建数必须大于零")
    print(build_sdk(args.min_os, args.jobs))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Darwin LLVM SDK：{error}", file=sys.stderr)
        sys.exit(1)
