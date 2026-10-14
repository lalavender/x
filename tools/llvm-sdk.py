#!/usr/bin/env python3
"""从固定、校验的私有 SDK 构建静态 LLVM 桥；不发现系统 LLVM 或调用 llvm-config。"""

import argparse
import contextlib
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "tmp/llvm-migration/sdk"


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


def prepare(lock: dict) -> Path:
    """按运行宿主提取私有 LLVM 与普通静态支持库，绝不混用架构或安装系统 LLVM。"""
    prefix = WORK / ("linux-x64-capi" if lock["host"] == "linux-x86_64" else "linux-arm64-capi")
    # 只展开 C API/配置头、实际静态组件和许可，避免在 DrvFS 写入上万个无用 C++ 头。
    # 每次仍从校验包重新读取所需字节，不能把解包目录当作可信输入。
    libraries = {f"{lock['prefix']}/lib/lib{name}.a" for name in lock["static_components"]}
    for spec in [lock, *lock.get("support_packages", [])]:
        package = download(spec)
        extracted = set()
        process = subprocess.Popen(["/usr/bin/dpkg-deb", "--fsys-tarfile", str(package)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with process.stdout, tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                name = member.name.removeprefix("./")
                relative = None
                if spec is not lock:
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
        expected = (set(spec["files"].values()) if spec is not lock else
                    {str(Path("lib") / Path(name).name) for name in libraries} | {"share/LICENSE"})
        if missing := expected - extracted:
            raise RuntimeError(f"固定包未实际提供所需文件：{sorted(missing)}")
    for name in [*(f"lib{name}.a" for name in lock["static_components"]), *lock.get("support_archives", [])]:
        library = prefix / "lib" / name
        if not library.is_file():
            raise RuntimeError(f"固定 SDK 缺少静态组件：{name}")
    return prefix


def build(lock: dict, prefix: Path) -> dict:
    """用普通 C 编译器构建桥归档，返回静态 LLVM 链接参数与可追踪身份。"""
    output = WORK / ("bridge" if lock["host"] == "linux-x86_64" else "bridge-linux-arm64")
    output.mkdir(exist_ok=True)
    compilers = toolchain(lock["host"])
    source = ROOT / "compiler/llvm/bridge.c"
    obj, archive = output / "bridge.o", output / "libyh_llvm.a"
    subprocess.run([compilers["cc"], "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I" + str(prefix / "include"), "-c", str(source), "-o", str(obj)], check=True)
    subprocess.run([compilers["ar"], "rcsD", str(archive), str(obj)], check=True)
    libraries = [str(prefix / "lib" / f"lib{name}.a") for name in lock["static_components"]]
    support = [str(prefix / "lib" / name) for name in lock.get("support_archives", [])]
    flags = [str(archive), "-Wl,--start-group", *libraries, "-Wl,--end-group",
             "-static-libstdc++", "-static-libgcc", *support, *lock["system_libraries"]]
    config = {"llvm_version": lock["llvm_version"], "sdk_sha256": lock["sha256"],
              "host": lock["host"], "build_host": build_host(), **compilers,
              "bridge_abi": lock["bridge_abi"], "bridge_source_sha256": digest(source),
              "bridge_header_sha256": digest(ROOT / "compiler/llvm/bridge.h"),
              "sdk_manifest_sha256": digest(ROOT / "vendor/llvm/sdk.lock.json"),
              "support_packages": [{key: spec[key] for key in ("package", "sha256")}
                                   for spec in lock.get("support_packages", [])],
              "bridge_sha256": digest(archive), "license": str(prefix / "share/LICENSE"),
              "licenses": [str(prefix / "share/LICENSE"),
                           *(str(prefix / name) for spec in lock.get("support_packages", [])
                             for name in spec["files"].values() if name.startswith("share/"))],
              "prefix": str(prefix), "archive": str(archive), "link_flags": flags}
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config


def link(config: dict, objects: list[str], output: Path) -> None:
    """以 GNU 链接器静态链接桥；归档以匿名内存 fd 传入，避免 WSL/DrvFS 逐成员 RPC。

    每个 fd 保存固定 SDK 归档的原始字节，不改变符号或链接顺序。所有持久文件仍在 tmp，
    内存 fd 在成功/失败后统一关闭；不要求 LLVM 链接工具或系统 LLVM 安装。
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
        result = subprocess.run([config["cxx"], *objects, "-o", f"/proc/self/fd/{output_fd}", *flags],
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
