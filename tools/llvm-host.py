#!/usr/bin/env python3
"""tools/llvm-host.py —— 内嵌静态 LLVM 宿主的薄驱动（供 Makefile/seed-build.py 调用）。

真正的构建与验收都在 tests/selfhost/llvm-host.py；本文件只做四件事：

    prepare  构建宿主可执行文件与身份记录（首次需要 SDK 包，可能联网下载）
    status   离线校验已准备的宿主是否仍然有效，输出身份 JSON（失效时退出码 3）
    shim     在 <宿主目录>/shim/gcc 生成链接包装器，让编译器自身的
             `gcc ... -o out` 链接命令自动链入内嵌桥与静态 LLVM
    link     包装器的实际实现：编译类调用（-c/-E/-S）透传固定 C 驱动，
             链接调用交给 tools/llvm-sdk.py 的 link()，用 memfd 传入归档

为什么需要包装器：编译器的链接命令（compiler/cmd/link_cache.yh 的 mb_link）
只执行 PATH 上的 `gcc`，没有「追加对象/参数」的接口。把包装器目录前置到
PATH，就能在不改动 yh 源码的前提下让产物链接进桥；包装器只改最终链接，
汇编（gcc -c）原样透传，因此对旧路径完全透明。

退出码：0 成功；3 表示宿主尚未准备或身份已失效（调用方应打印警告并回退旧路径）；
1 表示其他错误。失败信息一律带可执行的下一步命令。
"""

import argparse
import hashlib
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / "tmp/llvm-migration"
SDK_TOOL = ROOT / "tools/llvm-sdk.py"
BUILDER = ROOT / "tests/selfhost/llvm-host.py"
MANIFEST = ROOT / "vendor/llvm/sdk.lock.json"
BRIDGE_SOURCE = ROOT / "compiler/llvm/bridge.c"
BRIDGE_HEADER = ROOT / "compiler/llvm/bridge.h"
LLD_BRIDGE_SOURCE = ROOT / "compiler/llvm/lld_bridge.cpp"
LLD_STUB_SOURCE = ROOT / "compiler/llvm/lld_stub.cpp"
HOSTS = ("linux-x86_64", "linux-aarch64")
NOT_READY = 3

# SHIM_TEMPLATE：生成的 gcc 包装器。它只把参数原样转交给本文件的 link 子命令，
# 所有解析与链接逻辑留在本文件里，避免出现第二份会漂移的实现。
SHIM_TEMPLATE = '''#!/usr/bin/env python3
"""由 tools/llvm-host.py 生成的 gcc 包装器（宿主 {host}，SDK {sdk_short}）。

编译类调用（-c/-E/-S）原样透传给固定 C 驱动；链接调用改用固定 C++ 驱动并
追加内嵌桥与静态 LLVM 组件（经 memfd 传入，避免 WSL/DrvFS 逐成员 RPC）。
重新生成：python3 tools/llvm-host.py shim --host {host}
"""

import os
import sys

os.execv(sys.executable, [sys.executable, {driver!r}, "link", "--host", {host!r}, "--",
                          *sys.argv[1:]])
'''


class NotReady(RuntimeError):
    """宿主尚未准备或身份已失效；调用方据此回退旧路径而不是构建失败。"""


def digest(path: Path) -> str:
    """分块计算文件身份；宿主可达几十 MB，不整块读入内存。"""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def workdir(host: str) -> Path:
    """宿主产物的固定目录：tmp/llvm-migration/llvm-host-<host>/。"""
    return WORK_ROOT / f"llvm-host-{host}"


def identity(host: str) -> dict:
    """读取身份记录；缺失或不可解析时按未准备处理。"""
    path = workdir(host) / "host.json"
    if not path.is_file():
        raise NotReady(f"缺少身份记录 {path.relative_to(ROOT)}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise NotReady(f"身份记录不可读：{error}")


def check(host: str, full: bool = True) -> list[str]:
    """离线核对身份记录与磁盘现状，返回问题列表；空列表表示可用。

    full=True 还会重算宿主可执行文件的 SHA-256（链接路径上跳过这项，
    因为它每次都要读几十 MB，而链接本身已经要读全部静态归档）。
    """
    try:
        record = identity(host)
    except NotReady as error:
        return [str(error)]
    problems = []
    if record.get("host") != host:
        problems.append(f"身份记录的宿主是 {record.get('host')}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    host_lock = manifest["hosts"][host]
    if record.get("sdk_manifest_sha256") != digest(MANIFEST):
        problems.append("固定 SDK 清单 vendor/llvm/sdk.lock.json 已变化")
    if record.get("bridge_source_sha256") != digest(BRIDGE_SOURCE):
        problems.append("桥源码 compiler/llvm/bridge.c 已变化")
    if record.get("bridge_header_sha256") != digest(BRIDGE_HEADER):
        problems.append("桥接口 compiler/llvm/bridge.h 已变化")
    if record.get("lld_stub_source_sha256") != digest(LLD_STUB_SOURCE):
        problems.append("lld 占位桥源码 compiler/llvm/lld_stub.cpp 已变化")
    if record.get("sdk_builder_sha256") != digest(SDK_TOOL):
        problems.append("LLVM SDK 构建脚本 tools/llvm-sdk.py 已变化")
    if lld := host_lock.get("lld"):
        if record.get("lld_version") != lld["version"]:
            problems.append("宿主身份记录中的 lld 版本与固定 SDK 不一致")
        if record.get("lld_bridge_source_sha256") != digest(LLD_BRIDGE_SOURCE):
            problems.append("lld 桥源码 compiler/llvm/lld_bridge.cpp 已变化")
    selfhost = ROOT / record.get("selfhost_flags", "")
    if not record.get("selfhost_flags"):
        problems.append("宿主身份记录缺少自举闭包文件")
    elif not selfhost.is_file():
        problems.append(f"自举闭包文件不存在：{selfhost}")
    elif digest(selfhost) != record.get("selfhost_flags_sha256"):
        problems.append("自举闭包文件内容与身份记录不一致")
    selfhost_runtime = ROOT / record.get("selfhost_runtime", "")
    if not record.get("selfhost_runtime"):
        problems.append("宿主身份记录缺少运行库参数文件")
    elif not selfhost_runtime.is_file():
        problems.append(f"运行库参数文件不存在：{selfhost_runtime}")
    elif digest(selfhost_runtime) != record.get("selfhost_runtime_sha256"):
        problems.append("运行库参数文件内容与身份记录不一致")
    archive = ROOT / record.get("bridge_archive", "")
    if not archive.is_file():
        problems.append(f"桥归档不存在：{archive}")
    elif digest(archive) != record.get("bridge_sha256"):
        problems.append("桥归档内容与身份记录不一致")
    executable = ROOT / record.get("executable", "")
    if not executable.is_file():
        problems.append(f"宿主可执行文件不存在：{executable}")
    elif full and digest(executable) != record.get("executable_sha256"):
        problems.append("宿主可执行文件与身份记录不一致")
    if any("llvm" in name.lower() or "clang" in name.lower()
           for name in record.get("needed", ["libLLVM"])):
        problems.append(f"宿主动态依赖 LLVM：{record.get('needed')}")
    return problems


def offline_capable(host: str) -> bool:
    """判断能否在不联网的前提下重新准备：固定 SDK 的包必须都在本地缓存里。"""
    lock = json.loads(MANIFEST.read_text(encoding="utf-8"))
    specs = [lock["hosts"][host], *lock["hosts"][host].get("support_packages", [])]
    return all((WORK_ROOT / spec["package"]).is_file() for spec in specs)


def prepare(host: str) -> None:
    """调用验收脚本真正构建宿主。

    验收脚本的输出统一转到 stderr：stdout 是本驱动的 JSON 协议，
    不能让子进程的通过信息混进去（调用方按整行解析身份）。
    """
    result = subprocess.run([sys.executable, str(BUILDER), "--host", host], cwd=ROOT,
                            capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.rstrip(), file=sys.stderr)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"退出码 {result.returncode}"
        raise RuntimeError(f"构建静态 LLVM 宿主失败（{BUILDER.relative_to(ROOT)} "
                           f"--host {host}）：{detail}")


def ensure(host: str, mode: str) -> dict:
    """把宿主准备到可用状态并返回身份记录。

    mode=auto    只在本地已有 SDK 包或已准备成功时使用，绝不因缺包去联网；
                 仍然不可用时抛 NotReady，让调用方回退旧路径。
    mode=require 允许联网补齐 SDK，仍失败则自报错误（显式开关才会走到这里）。
    """
    problems = check(host)
    if not problems:
        return identity(host)
    if mode == "require":
        prepare(host)
    elif offline_capable(host):
        prepare(host)
    else:
        raise NotReady("；".join(problems) +
                       "；本地也缺少固定 SDK 包，auto 模式不联网下载")
    problems = check(host)
    if problems:
        raise NotReady("；".join(problems))
    return identity(host)


def split_link_argv(argv: list[str]) -> tuple[list[str], str, list[str]]:
    """把编译器的链接命令拆成（对象, 输出, 其他驱动参数）。

    形态不认识时必须明确失败：宁可让这一步报错，也不能静默链出一个
    缺少桥或缺少 LLVM 的可执行文件。
    """
    objects, extra, output = [], [], None
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "-o":
            if index + 1 >= len(argv):
                raise RuntimeError("链接命令缺少 -o 的输出路径")
            output = argv[index + 1]
            index += 2
            continue
        if argument.startswith("-"):
            extra.append(argument)
        else:
            objects.append(argument)
        index += 1
    if output is None or not objects:
        raise RuntimeError(f"无法识别的链接命令：{argv}")
    return objects, output, extra


def is_driver_query(argv: list[str]) -> bool:
    """识别 gcc 查询调用，让缓存身份探测交给真实驱动而不进入链接器。"""
    if not argv:
        return False
    exact = {
        "-print-search-dirs", "-print-sysroot", "-dumpmachine",
        "-dumpversion", "-dumpfullversion", "-dumpspecs",
    }
    prefixes = ("-print-file-name=", "-print-prog-name=")
    return all(argument in exact or argument.startswith(prefixes)
               for argument in argv)


def bridge_flags(record: dict) -> list[str]:
    """在固定 SDK 的链接参数上把桥归档强制整份纳入。

    静态归档只贡献「能解决当前未定义符号」的成员：编译器源码还没引用
    yh_llvm_* 时，桥归档一个成员都不会被拉进来，`nm ./yh` 里也就没有
    yh_llvm_* 定义。用 --whole-archive 把桥归档整份先拉进来，再让后面的
    --start-group 解析它引用的 LLVM 组件，这样「make 产出的宿主已经静态
    链入桥」是链接结果的确定属性，而不取决于某个调用点。
    """
    bridge = str((ROOT / record["bridge_archive"]).resolve())
    flags, found = [], False
    for flag in record["link_flags"]:
        if flag == bridge:
            flags += ["-Wl,--whole-archive", flag, "-Wl,--no-whole-archive"]
            found = True
        else:
            flags.append(flag)
    if not found:
        raise RuntimeError("固定 SDK 的链接参数里找不到桥归档，拒绝生成缺少桥的宿主")
    return flags


def command_link(host: str, argv: list[str]) -> int:
    """包装器的实现：编译透传，链接注入内嵌桥与静态 LLVM。"""
    record = ensure(host, "auto")
    if {"-c", "-E", "-S"} & set(argv):
        # 汇编/C 源编译与桥无关，用固定 C 驱动原样执行（不回到 PATH 上的自己）。
        os.execv(record["cc"], [record["cc"], *argv])
    if is_driver_query(argv):
        # yh 的链接缓存会查询 gcc 搜索路径、版本和默认工具；查询不产生链接产物，
        # 必须返回真实宿主驱动的答案，不能把查询参数误当成 lld 的链接输入。
        os.execv(record["cc"], [record["cc"], *argv])
    objects, output, extra = split_link_argv(argv)
    config = {"cxx": record["cxx"], "link_flags": bridge_flags(record)}
    sdk = runpy.run_path(str(SDK_TOOL))
    sdk["link"](config, objects, Path(output), extra)
    return 0


def write_shim(host: str, record: dict) -> Path:
    """写入链接包装器并返回其路径；已存在且内容相同时不重复落盘。"""
    directory = workdir(host) / "shim"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "gcc"
    text = SHIM_TEMPLATE.format(host=host, driver=str(ROOT / "tools/llvm-host.py"),
                                sdk_short=record["sdk_sha256"][:12])
    if not path.is_file() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def split_passthrough(argv: list[str]) -> tuple[list[str], list[str]]:
    """在第一个 `--` 处切分驱动参数与透传参数。

    argparse 的 `--` 处理在部分 Python 版本/参数布局下会把分隔符留在
    `nargs="*"` 中；C 源编译（`gcc -c`）会因此被当成链接参数拒绝。
    """
    argv = list(argv)
    if "--" not in argv:
        return argv, []
    cut = argv.index("--")
    return argv[:cut], argv[cut + 1:]


def main(argv: list[str]) -> int:
    """解析子命令；所有子命令都以 JSON（或包装器执行结果）收尾。"""
    head, passthrough = split_passthrough(argv)
    parser = argparse.ArgumentParser(description="内嵌静态 LLVM 宿主驱动")
    parser.add_argument("command", choices=("prepare", "status", "shim", "link"))
    parser.add_argument("--host", choices=HOSTS, required=True)
    parser.add_argument("--mode", choices=("auto", "require"), default="auto",
                        help="auto 只用本地已有的 SDK 包，require 允许联网补齐")
    parser.add_argument("tail", nargs="*", help="link 子命令透传的编译器参数")
    args = parser.parse_args(head)
    if args.command == "link":
        return command_link(args.host, list(args.tail) + passthrough)
    if args.command == "status":
        # status 是纯离线查询：只报告现状，不准备、不联网，便于门禁与排查。
        problems = check(args.host)
        if problems:
            raise NotReady("；".join(problems))
        record = identity(args.host)
        print(json.dumps({"host": args.host, "ready": True,
                          "executable": record["executable"],
                          "executable_sha256": record["executable_sha256"],
                          "bridge_sha256": record["bridge_sha256"],
                          "sdk_sha256": record["sdk_sha256"],
                          "needed": record["needed"]}, ensure_ascii=False))
        return 0
    if args.command == "shim":
        record = ensure(args.host, args.mode)
        path = write_shim(args.host, record)
        selfhost_flags = (ROOT / record["selfhost_flags"]).resolve() \
            if record.get("selfhost_flags") else None
        selfhost_runtime = (ROOT / record["selfhost_runtime"]).resolve() \
            if record.get("selfhost_runtime") else None
        print(json.dumps({"host": args.host, "shim_dir": str(path.parent),
                          "shim": str(path), "mode": args.mode,
                          "executable": record["executable"],
                          "executable_sha256": record["executable_sha256"],
                          "bridge_sha256": record["bridge_sha256"],
                          "sdk_sha256": record["sdk_sha256"],
                          "selfhost_flags": str(selfhost_flags) if selfhost_flags else "",
                          "selfhost_runtime": str(selfhost_runtime) if selfhost_runtime else "",
                          "cxx": record["cxx"], "cc": record["cc"]}, ensure_ascii=False))
        return 0
    record = ensure(args.host, "require")
    print(json.dumps({"host": args.host, "ready": True, "executable": record["executable"],
                      "executable_sha256": record["executable_sha256"],
                      "bridge_sha256": record["bridge_sha256"],
                      "sdk_sha256": record["sdk_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except NotReady as error:
        print(f"LLVM 宿主尚未准备：{error}\n"
              f"准备命令：python3 tools/llvm-host.py prepare --host "
              f"{next((a for a in sys.argv if a.startswith('linux-')), 'linux-x86_64')}",
              file=sys.stderr)
        raise SystemExit(NOT_READY)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"LLVM 宿主驱动：{error}", file=sys.stderr)
        raise SystemExit(1)
