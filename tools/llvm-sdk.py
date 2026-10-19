#!/usr/bin/env python3
"""从固定、校验的私有 SDK 构建静态 LLVM 桥；不发现系统 LLVM 或调用 llvm-config。"""

import argparse
import contextlib
import hashlib
import json
import os
import platform
import re
import shutil
import shlex
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "tmp/llvm-migration/sdk"
HEADER_INCLUDE = re.compile(r'^\s*#\s*include\s*([<"])([^">]+)[">]', re.MULTILINE)
LLD_OUTPUT_MARKER = "@YH_LLD_OUTPUT@"
LLD_INPUT_MARKER = "@YH_LLD_INPUTS@"


def build_host() -> str:
    """规范化构建机架构；SDK host 指最终运行 LLVM 桥的架构，发射目标由桥参数决定。"""
    machine = {"arm64": "aarch64", "amd64": "x86_64"}.get(platform.machine(), platform.machine())
    host = "linux-" + machine
    if platform.system() != "Linux" or host not in ("linux-x86_64", "linux-aarch64"):
        raise RuntimeError("固定 SDK 构建仅支持 Linux/x86_64 或 Linux/AArch64")
    return host


def toolchain(host: str) -> dict:
    """原生构建使用固定系统 GCC；跨架构使用对应 GNU 交叉工具，避免误用 PATH 包装。"""
    prefix = "" if host == build_host() else host.removeprefix("linux-") + "-linux-gnu-"
    result = {name: f"/usr/bin/{prefix}{program}" for name, program in
              (("cc", "gcc"), ("cxx", "g++"), ("ar", "ar"))}
    for path in result.values():
        if not Path(path).is_file():
            raise RuntimeError(f"{host} 普通构建工具缺失：{path}")
    return result


def digest(path: Path) -> str:
    """分块计算下载包或桥源码身份，不把整个 SDK 读入内存。"""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def download(spec: dict) -> Path:
    """下载并逐次校验固定发行包；缓存及未完成下载都不能绕过 SHA-256 检查。"""
    WORK.mkdir(parents=True, exist_ok=True)
    package = WORK.parent / spec["package"]
    if not package.exists():
        temporary = package.with_suffix(".download")
        with urllib.request.urlopen(spec["url"], timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if digest(temporary) != spec["sha256"]:
            temporary.unlink()
            raise RuntimeError("LLVM SDK 下载 SHA-256 不符")
        temporary.replace(package)
    if digest(package) != spec["sha256"]:
        raise RuntimeError("LLVM SDK 缓存包 SHA-256 不符，请移除坏包后重试")
    return package


def lld_header_closure(headers: dict[str, bytes]) -> set[str]:
    """从 lld 公共入口递归收集实际需要的 LLVM/lld 头文件，避免写入整个 SDK 头树。"""
    pending = ["lld/Common/Driver.h"]
    selected = set()
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        content = headers.get(name)
        if content is None:
            raise RuntimeError(f"固定 lld SDK 缺少 C++ 头文件：include/{name}")
        selected.add(name)
        parent = Path(name).parent
        for quote, include in HEADER_INCLUDE.findall(content.decode("utf-8", errors="replace")):
            if include.startswith(("llvm/", "llvm-c/", "lld/")):
                child = include
            elif quote == '"':
                child = (parent / include).as_posix()
            else:
                continue
            if child.startswith(("llvm/", "llvm-c/", "lld/")) and child not in selected:
                pending.append(child)
    return selected


def lld_driver_config(compilers: dict, output: Path) -> tuple[list[str], list[str], list[str]]:
    """从固定宿主 GCC 的 -### 输出捕获 GNU/ELF 启动文件、搜索目录与默认库参数。"""
    assembly = output / "lld-link-config.s"
    obj = output / "lld-link-config.o"
    executable = output / "lld-link-config-output"
    assembly.write_text(".text\n.globl yh_lld_config_probe\nyh_lld_config_probe:\n  ret\n",
                        encoding="utf-8")
    subprocess.run([compilers["cc"], "-c", str(assembly), "-o", str(obj)], check=True)
    probe = subprocess.run([compilers["cc"], "-###", "-no-pie", "-o", str(executable),
                            str(obj)], capture_output=True, text=True, check=False)
    command = next((line.strip() for line in probe.stderr.splitlines()
                    if "collect2 " in line), None)
    if probe.returncode != 0 or command is None:
        raise RuntimeError("固定 GCC 未提供可解析的 ELF 链接配置（-###）")
    tokens = shlex.split(command)
    if not tokens or not tokens[0].endswith("collect2"):
        raise RuntimeError("固定 GCC -### 输出不是 collect2 链接命令")
    link_args = []
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token == "-plugin":
            i += 2
            continue
        if token == "-plugin-opt" or token.startswith("-plugin-opt="):
            i += 2 if token == "-plugin-opt" else 1
            continue
        link_args.append(token)
        i += 1
    try:
        output_index = link_args.index("-o") + 1
        object_index = link_args.index(str(obj))
    except ValueError as error:
        raise RuntimeError("固定 GCC -### 输出缺少输出路径或探针对象") from error
    if output_index >= len(link_args) or link_args[output_index] != str(executable):
        raise RuntimeError("固定 GCC -### 输出路径格式不受支持")
    link_args[output_index] = LLD_OUTPUT_MARKER
    link_args[object_index] = LLD_INPUT_MARKER
    template = ["ld.lld", *link_args]

    default_files = []
    default_libraries = []
    i = 0
    while i < len(template):
        token = template[i]
        if token.startswith("/") and Path(token).is_file() and token not in default_files:
            default_files.append(token)
        if token.startswith("-l") and len(token) > 2 and token[2:] not in default_libraries:
            default_libraries.append(token[2:])
        i += 1
    if LLD_INPUT_MARKER not in template or LLD_OUTPUT_MARKER not in template:
        raise RuntimeError("固定 GCC -### 模板标记缺失")
    return template, default_files, default_libraries


def cpp_string(value: str) -> str:
    """把 ASCII argv 项编码为 C++ 字符串字面量。"""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') \
        .replace("\n", "\\n").replace("\r", "\\r") + '"'


def write_lld_config_header(path: Path, template: list[str], default_files: list[str],
                            default_libraries: list[str], selfhost_flags: list[str],
                            identity: str) -> None:
    """生成默认 ELF 链接模板、自举桥参数与稳定身份。"""
    def array(name: str, items: list[str]) -> str:
        counts = {
            "yh_lld_link_template": "YH_LLD_LINK_TEMPLATE_COUNT",
            "yh_lld_default_files": "YH_LLD_DEFAULT_FILES_COUNT",
            "yh_lld_default_libraries": "YH_LLD_DEFAULT_LIBRARIES_COUNT",
            "yh_llvm_selfhost_link_flags": "YH_LLVM_SELFHOST_LINK_FLAGS_COUNT",
        }
        values = ",\n    ".join(cpp_string(item) for item in items) or "nullptr"
        return (f"#define {counts[name]} {len(items)}\n"
                f"static const char *const {name}[] = {{\n    {values}\n}};\n")

    content = "#pragma once\n" + array("yh_lld_link_template", template) \
        + array("yh_lld_default_files", default_files) \
        + array("yh_lld_default_libraries", default_libraries) \
        + array("yh_llvm_selfhost_link_flags", selfhost_flags) \
        + f"static const char yh_lld_identity_value[] = {cpp_string(identity)};\n"
    path.write_text(content, encoding="ascii")


def lld_search_paths(template: list[str]) -> list[str]:
    """按 lld 命令行顺序取出 GCC 默认的 `-L` 搜索目录。"""
    paths = []
    i = 0
    while i < len(template):
        token = template[i]
        if token == "-L" and i + 1 < len(template):
            paths.append(template[i + 1])
            i += 2
            continue
        if token.startswith("-L") and len(token) > 2:
            paths.append(token[2:])
        i += 1
    return paths


def resolve_lld_library(name: str, search_paths: list[str]) -> Path | None:
    """按 ELF GNU 链接器的共享库优先顺序找出固定默认库文件。"""
    for directory in search_paths:
        for suffix in (".so", ".a"):
            candidate = Path(directory) / f"lib{name}{suffix}"
            if candidate.is_file():
                return candidate
    return None


def prepare(lock: dict) -> Path:
    """按运行宿主提取私有 LLVM 与普通静态支持库，绝不混用架构或安装系统 LLVM。"""
    prefix = WORK / ("linux-x64-capi" if lock["host"] == "linux-x86_64" else "linux-arm64-capi")
    # 基础桥只展开 C API/配置头；启用 lld 时再展开其 C++ 编译所需的固定 LLVM 头树。
    # 每次仍从校验包重新读取所需字节，不能把解包目录当作可信输入。
    libraries = {f"{lock['prefix']}/lib/lib{name}.a" for name in lock["static_components"]}
    lld_components = set()
    lld_headers: dict[str, bytes] = {}
    deferred_headers = set()
    for spec in [lock, *lock.get("support_packages", [])]:
        package = download(spec)
        extracted = set()
        process = subprocess.Popen(["/usr/bin/dpkg-deb", "--fsys-tarfile", str(package)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with process.stdout, tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                name = member.name.removeprefix("./")
                if member.isfile() and lock.get("lld"):
                    llvm_header_root = "usr/include/llvm-21/llvm/"
                    if spec is lock and name.startswith(llvm_header_root):
                        key = "llvm/" + name.removeprefix(llvm_header_root)
                        with archive.extractfile(member) as source:
                            lld_headers[key] = source.read()
                        continue
                    llvm_c_header_root = "usr/include/llvm-c-21/llvm-c/"
                    if spec is lock and name.startswith(llvm_c_header_root):
                        key = "llvm-c/" + name.removeprefix(llvm_c_header_root)
                        with archive.extractfile(member) as source:
                            lld_headers[key] = source.read()
                        continue
                    if spec is not lock and name in spec["files"]:
                        target = Path(spec["files"][name])
                        if target.as_posix().startswith("include/lld/"):
                            key = target.relative_to("include").as_posix()
                            with archive.extractfile(member) as source:
                                lld_headers[key] = source.read()
                            deferred_headers.add(str(target))
                            continue
                relative = None
                if spec is lock and lock.get("lld") and name.startswith(
                        f"{lock['prefix']}/lib/libLLVM") and name.endswith(".a"):
                    lld_components.add(name)
                    relative = Path("lib") / Path(name).name
                elif spec is not lock:
                    relative = Path(spec["files"][name]) if name in spec["files"] else None
                elif name in libraries:
                    relative = Path("lib") / Path(name).name
                elif name.startswith("usr/include/llvm-c-21/llvm-c/"):
                    relative = Path("include/llvm-c") / name.removeprefix("usr/include/llvm-c-21/llvm-c/")
                elif name.startswith("usr/include/llvm-21/llvm/Config/"):
                    relative = Path("include/llvm/Config") / name.removeprefix("usr/include/llvm-21/llvm/Config/")
                elif name == "usr/share/doc/llvm-21-dev/copyright":
                    relative = Path("share/LICENSE")
                if relative is None or not member.isfile():
                    continue
                if relative.is_absolute() or ".." in relative.parts:
                    process.kill()
                    raise RuntimeError("LLVM SDK 包含非法文件路径")
                target = prefix / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                extracted.add(str(relative))
        error = process.stderr.read()
        process.stderr.close()
        if process.wait():
            raise RuntimeError(error.decode(errors="replace"))
        if spec is not lock:
            expected = set(spec["files"].values())
        else:
            expected = {str(Path("lib") / Path(name).name) for name in libraries} | {"share/LICENSE"}
            if lock.get("lld"):
                component_count = lock["lld"]["llvm_component_count"]
                if len(lld_components) != component_count:
                    raise RuntimeError(f"固定 LLVM SDK 组件数不符：{len(lld_components)}，期望 {component_count}")
                expected |= {str(Path("lib") / Path(name).name) for name in lld_components}
        if missing := expected - extracted:
            missing -= deferred_headers
        if missing:
            raise RuntimeError(f"固定包未实际提供所需文件：{sorted(missing)}")
    if lock.get("lld"):
        header_names = lld_header_closure(lld_headers)
        required_headers = {"lld/Common/Driver.h", "llvm/ADT/ArrayRef.h",
                            "llvm/Support/raw_ostream.h"}
        if not required_headers <= header_names:
            raise RuntimeError("lld C++ 头文件闭包未包含 shim 所需头文件")
        # C API 与配置头必须全量落地：bridge.c 只经 llvm-c 头引入，但
        # llvm-c/Target.h 会展开 llvm/Config/Targets.def 等 .def 文件，
        # 它们不在 lld shim 的头文件闭包里（实测 linux-x86_64 因此编译失败）。
        header_names |= {name for name in lld_headers
                         if name.startswith(("llvm-c/", "llvm/Config/"))}
        for name in header_names:
            target = prefix / "include" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(lld_headers[name])
    required_archives = [*(f"lib{name}.a" for name in lock["static_components"]),
                         *lock.get("support_archives", [])]
    if lock.get("lld"):
        required_archives += lock["lld"]["archives"] + lock["lld"]["link_group_archives"]
    for name in required_archives:
        library = prefix / "lib" / name
        if not library.is_file():
            raise RuntimeError(f"固定 SDK 缺少静态组件：{name}")
    return prefix


def build(lock: dict, prefix: Path) -> dict:
    """用固定 C/C++ 工具链构建桥归档，返回静态 LLVM/lld 参数与可追踪身份。"""
    output = WORK / ("bridge" if lock["host"] == "linux-x86_64" else "bridge-linux-arm64")
    output.mkdir(exist_ok=True)
    compilers = toolchain(lock["host"])
    source = ROOT / "compiler/llvm/bridge.c"
    archive = output / "libyh_llvm.a"
    bridge_objects = [output / "bridge.o"]
    subprocess.run([compilers["cc"], "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I" + str(prefix / "include"), "-c", str(source), "-o",
                    str(bridge_objects[0])], check=True)
    lld_source = None
    lld_link_identity = ""
    lld_default_files: list[str] = []
    lld_default_libraries: list[str] = []
    if lock.get("lld"):
        component_paths = sorted((prefix / "lib").glob("libLLVM*.a"))
        if len(component_paths) != lock["lld"]["llvm_component_count"]:
            raise RuntimeError(f"提取的 LLVM 组件数不符：{len(component_paths)}")
        libraries = [str(path) for path in component_paths]
        lld_archives = [str(prefix / "lib" / name)
                        for name in lock["lld"]["linked_archives"]]
        lld_support = [str(prefix / "lib" / name)
                       for name in lock["lld"]["link_group_archives"]]
    else:
        libraries = [str(prefix / "lib" / f"lib{name}.a")
                     for name in lock["static_components"]]
        lld_archives = []
        lld_support = []
    support = [str(prefix / "lib" / name)
               for name in lock.get("support_archives", [])]
    flags = ["-Wl,--whole-archive", str(archive), "-Wl,--no-whole-archive",
             "-Wl,--start-group", *lld_archives, *libraries,
             *lld_support, "-Wl,--end-group",
             "-static-libstdc++", "-static-libgcc", *support,
             *lock["system_libraries"]]
    selfhost_flags = []
    for flag in flags:
        if flag.startswith("-Wl,"):
            selfhost_flags.append(flag[4:])
        elif flag == "-static-libstdc++":
            selfhost_flags.append("-lstdc++")
        elif flag == "-pthread":
            selfhost_flags.append("-lpthread")
        elif flag != "-static-libgcc":
            selfhost_flags.append(flag)
    if lock.get("lld"):
        lld_source = ROOT / "compiler/llvm/lld_bridge.cpp"
        template, lld_default_files, lld_default_libraries = lld_driver_config(
            compilers, output)
        search_paths = lld_search_paths(template)
        resolved_defaults = {}
        for name in lld_default_libraries:
            resolved = resolve_lld_library(name, search_paths)
            if resolved is None:
                raise RuntimeError(f"固定宿主链接配置无法解析默认系统库：lib{name}")
            resolved_defaults[name] = {"path": str(resolved), "sha256": digest(resolved)}
        input_digests = {path: digest(Path(path)) for path in lld_default_files}
        identity_payload = {
            "host": lock["host"], "llvm_version": lock["llvm_version"],
            "sdk_sha256": lock["sha256"],
            "support_packages": [{"package": spec["package"], "sha256": spec["sha256"]}
                                 for spec in lock.get("support_packages", [])],
            "lld": lock["lld"], "lld_source_sha256": digest(lld_source),
            "link_template": template, "default_files": input_digests,
            "default_libraries": resolved_defaults,
            "link_driver_sha256": digest(Path(compilers["cc"])),
            "selfhost_link_flags": selfhost_flags,
        }
        lld_link_identity = hashlib.sha256(json.dumps(identity_payload, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        write_lld_config_header(output / "lld_link_config.h", template,
                                lld_default_files, lld_default_libraries,
                                selfhost_flags, lld_link_identity)
        lld_object = output / "lld_bridge.o"
        subprocess.run([compilers["cxx"], "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-I" + str(prefix / "include"), "-I" + str(output),
                        "-c", str(lld_source), "-o",
                        str(lld_object)], check=True)
        bridge_objects.append(lld_object)
    else:
        lld_source = ROOT / "compiler/llvm/lld_stub.cpp"
        lld_object = output / "lld_stub.o"
        subprocess.run([compilers["cxx"], "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-c", str(lld_source), "-o", str(lld_object)], check=True)
        bridge_objects.append(lld_object)
    subprocess.run([compilers["ar"], "rcsD", str(archive),
                    *(str(obj) for obj in bridge_objects)], check=True)
    lld_identity = {}
    if lock.get("lld"):
        lld_identity = {
            "lld_version": lock["lld"]["version"],
            "lld_bridge_source_sha256": digest(lld_source),
            "lld_archives": {name: digest(prefix / "lib" / name)
                             for name in lock["lld"]["linked_archives"]},
            "lld_link_group_archives": {name: digest(prefix / "lib" / name)
                                        for name in lock["lld"]["link_group_archives"]},
            "lld_component_count": len(libraries),
            "lld_link_config_sha256": lld_link_identity,
            "lld_default_files": lld_default_files,
            "lld_default_libraries": lld_default_libraries,
        }
    config = {"llvm_version": lock["llvm_version"], "sdk_sha256": lock["sha256"],
              "host": lock["host"], "build_host": build_host(), **compilers,
              "bridge_abi": lock["bridge_abi"], "bridge_source_sha256": digest(source),
              "bridge_header_sha256": digest(ROOT / "compiler/llvm/bridge.h"),
              "lld_stub_source_sha256": digest(ROOT / "compiler/llvm/lld_stub.cpp"),
              "sdk_builder_sha256": digest(Path(__file__)),
              "sdk_manifest_sha256": digest(ROOT / "vendor/llvm/sdk.lock.json"),
              "support_packages": [{key: spec[key] for key in ("package", "sha256")}
                                   for spec in lock.get("support_packages", [])],
              "bridge_sha256": digest(archive), "license": str(prefix / "share/LICENSE"),
              "licenses": [str(prefix / "share/LICENSE"),
                           *(str(prefix / name) for spec in lock.get("support_packages", [])
                             for name in spec["files"].values() if name.startswith("share/"))],
              "prefix": str(prefix), "archive": str(archive), "link_flags": flags,
              **lld_identity}
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config


def link(config: dict, objects: list[str], output: Path, extra_flags: list[str] = ()) -> None:
    """以 GNU 链接器静态链接桥；归档以匿名内存 fd 传入，避免 WSL/DrvFS 逐成员 RPC。

    每个 fd 保存固定 SDK 归档的原始字节，不改变符号或链接顺序。所有持久文件仍在 tmp，
    内存 fd 在成功/失败后统一关闭；不要求 LLVM 链接工具或系统 LLVM 安装。
    extra_flags 原样插在输出路径与静态 SDK 参数之间，供调用方补充驱动选项
    （例如编译器自身的 -no-pie 与 -lm）；不参与归档顺序。
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as resources:
        flags, descriptors = [], []
        for flag in config["link_flags"]:
            if flag.endswith(".a"):
                fd = os.memfd_create("yh-llvm-static", flags=0)
                resources.callback(os.close, fd)
                with open(flag, "rb") as source, os.fdopen(fd, "wb", closefd=False) as memory:
                    shutil.copyfileobj(source, memory, length=1024 * 1024)
                descriptors.append(fd)
                flags.append(f"/proc/self/fd/{fd}")
            else:
                flags.append(flag)
        output_fd = os.memfd_create("yh-llvm-executable", flags=0)
        resources.callback(os.close, output_fd)
        descriptors.append(output_fd)
        result = subprocess.run([config["cxx"], *objects, "-o", f"/proc/self/fd/{output_fd}",
                                 *extra_flags, *flags],
                                pass_fds=descriptors, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError(result.stderr)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.",
                                             delete=False) as target:
                temporary = Path(target.name)
                with os.fdopen(output_fd, "rb", closefd=False) as executable:
                    executable.seek(0)
                    shutil.copyfileobj(executable, target, length=1024 * 1024)
            temporary.chmod(0o755)
            temporary.replace(output)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)


def main() -> int:
    """准备/构建私有 SDK，或静态链接调用方对象；以 JSON 返回精确身份与输入。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "build", "link"))
    parser.add_argument("--host", choices=("linux-x86_64", "linux-aarch64"),
                        help="运行 LLVM 桥的架构；默认构建机架构，可在 x64 上交叉构建 ARM64")
    parser.add_argument("--object", action="append", default=[], help="链接调用方对象，可重复")
    parser.add_argument("--output", type=Path, help="静态宿主输出路径")
    args = parser.parse_args()
    lock = json.loads((ROOT / "vendor/llvm/sdk.lock.json").read_text(encoding="utf-8"))
    actual_host = build_host()
    host = args.host or actual_host
    lock = {**lock, **lock["hosts"][host], "host": host}
    prefix = prepare(lock)
    result = build(lock, prefix) if args.command != "prepare" else {
        "prefix": str(prefix), "host": host, "sdk_sha256": lock["sha256"]}
    if args.command == "link":
        if not args.object or not args.output:
            parser.error("link 需要 --object 和 --output")
        link(result, args.object, args.output)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"LLVM SDK：{error}", file=sys.stderr)
        raise SystemExit(1)
