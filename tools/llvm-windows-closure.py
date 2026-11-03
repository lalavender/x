#!/usr/bin/env python3
"""tools/llvm-windows-closure.py —— Windows/x86_64 固定 LLVM 闭包的可重定位准备。

为什么需要它
------------
Windows 没有厂家分发的静态 `libLLVM*.lib` / `liblld*.lib`（官方安装只给 DLL 导入库），
而 yh 的种子必须自包含（ADR-0014 / LL11）、lld 必须进程内调用，所以 Windows 宿主
闭包只能用 MSVC 从固定源码构建一次（`/MT` 静态 CRT）。本脚本把这件事做成一条幂等
命令，CI 与本地共用：

    build [--jobs N]   准备闭包：身份/归档都齐 → 秒级复用；否则源码构建后复制归档
    status             离线复核身份记录（等价 tools/llvm-windows-host.py status）

布局的唯一真源是 `compiler/project.toml` 的 `[link-windows-x64]`：里面每条归档必须写成
canonical 相对路径 `<闭包根>/<组>/<文件名>`（闭包根 = `<缓存根>/windows-llvm-closure`）。
本脚本**从清单反推**闭包根与四组成员，而不是自己再定义一套目录名——这样「编译器读的
路径」和「脚本写的路径」永远是同一个，不会出现脚本准备好一份、编译器去找另一份。

写路径（与 CI 的 actions/cache 约定一致，只有这三处）：
    <缓存根>/windows-llvm-closure/{bridge,lld,llvm,support}/  闭包本体
    <缓存根>/llvm-host-windows-x86_64/host.json               身份记录（由 llvm-windows-host.py 写）
    <缓存根>/windows-sdk/                                     导入库（由 tools/windows-sdk.py 写，本脚本不碰）

源码包、解包目录与 CMake 构建树是**一次性工作区**，不进缓存：默认放系统 temp，
可用 `YH_LLVM_WINDOWS_WORK` 指到空间充足的盘（本机 C: 只剩几 GB 时用它），构建
成功后整个目录可以删掉。

只在 Windows 上可用：Linux 用 `tools/llvm-host.py`（Ubuntu deb），Darwin 用
`tools/llvm-darwin-host.py`（本机 SDK 源码构建）；其他平台明确报错退出 1。

退出码：0 成功；3 未准备/身份失效（仅 status 会返回）；1 其他错误。
"""

import argparse
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from llvm_cache import cache_root  # noqa: E402

MANIFEST = ROOT / "compiler/project.toml"
LOCK = ROOT / "vendor/llvm/sdk.lock.json"
HOST_TOOL = ROOT / "tools/llvm-windows-host.py"
SDK_TOOL = ROOT / "tools/llvm-sdk.py"
BRIDGE_DIR = ROOT / "compiler/llvm"
HOST = "windows-x86_64"
SECTION = "link-windows-x64"
# 归档组与清单同名：bridge 是 yh 自己的桥，lld/llvm 由源码构建，support 是
# MSVC 静态 CRT 与 Windows SDK 导入库（随 VS/SDK 安装，必须每次从本机取）。
GROUPS = ("bridge", "lld", "llvm", "support")
# vswhere 是 VS 安装器固定提供的定位工具：托管 runner 上 CMake 自带的 VS 探测曾失败
# （2026-11-03 CI 实测 "could not find any instance of Visual Studio"），显式把实例
# 路径经 CMAKE_GENERATOR_INSTANCE 传给 CMake 即可绕过探测。
VSWHERE = (Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
           / "Microsoft Visual Studio/Installer/vswhere.exe")
# 桥的三个 COFF 对象：与 docs/03-design/yh-Windows-LLVM后端设计.md §13 记录的命令一致。
BRIDGE_OBJECTS = (
    ("bridge.c", "bridge.obj", ("/TC",)),
    ("lld_bridge.cpp", "lld_bridge.obj", ("/std:c++17", "/EHsc", "/TP")),
    ("windows_shim.c", "windows_shim.obj", ("/TC",)),
)
# 锁文件里的 windows_build 布尔项 → CMake 变量；口径照抄本机 configure.sh
# （D:/tmp/llvm-win/configure.sh），保证任何机器构建出的闭包与已验证的一致。
CMAKE_BOOLEANS = (
    ("include_tests", "LLVM_INCLUDE_TESTS"),
    ("include_examples", "LLVM_INCLUDE_EXAMPLES"),
    ("include_benchmarks", "LLVM_INCLUDE_BENCHMARKS"),
    ("include_docs", "LLVM_INCLUDE_DOCS"),
    ("enable_zlib", "LLVM_ENABLE_ZLIB"),
    ("enable_zstd", "LLVM_ENABLE_ZSTD"),
    ("enable_libxml2", "LLVM_ENABLE_LIBXML2"),
    ("enable_terminfo", "LLVM_ENABLE_TERMINFO"),
    ("enable_assertions", "LLVM_ENABLE_ASSERTIONS"),
    ("enable_bindings", "LLVM_ENABLE_BINDINGS"),
    ("build_llvm_dylib", "LLVM_BUILD_LLVM_DYLIB"),
    ("link_llvm_dylib", "LLVM_LINK_LLVM_DYLIB"),
    ("build_tools", "LLVM_BUILD_TOOLS"),
    ("build_utils", "LLVM_BUILD_UTILS"),
)
NOT_READY = 3


def describe(path: Path) -> str:
    """把路径显示为相对仓库的短形式；缓存根在仓库外时返回绝对路径。"""
    path = Path(path)
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def digest(path: Path) -> str:
    """分块计算文件身份；闭包累计 485 MB，不整块读入内存。"""
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def require_windows() -> None:
    """闭包由 MSVC 构建：其他平台直接拒绝，并指出各自的替代脚本。"""
    if sys.platform != "win32":
        raise RuntimeError(
            f"本脚本只在 Windows 上可用（当前平台 {sys.platform}）："
            "Linux 用 tools/llvm-host.py，Darwin 用 tools/llvm-darwin-host.py")


def workdir() -> Path:
    """身份记录与构建日志目录：与 tools/llvm-windows-host.py 的 record_path() 同一处。"""
    return cache_root() / f"llvm-host-{HOST}"


def work_root() -> Path:
    """一次性工作区：源码包、解包目录、CMake 构建树（不入缓存，构建完可删）。"""
    env = os.environ.get("YH_LLVM_WINDOWS_WORK")
    if env:
        return Path(env).expanduser().resolve()
    return Path(tempfile.gettempdir()) / "yh-llvm-windows-build"


def run(command, label: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """执行外部命令并把 stdout/stderr 落到工作区日志；失败时给出日志位置与末尾输出。"""
    directory = workdir()
    directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    result = subprocess.run([str(item) for item in command], cwd=cwd or ROOT,
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", check=False)
    (directory / f"{label}.stdout").write_text(result.stdout, encoding="utf-8")
    (directory / f"{label}.stderr").write_text(result.stderr, encoding="utf-8")
    elapsed = time.monotonic() - started
    if result.returncode:
        tail = (result.stderr or result.stdout).strip()[-4000:]
        raise RuntimeError(f"{label} 失败（退出码 {result.returncode}，{elapsed:.0f}s）：{tail}\\n"
                           f"完整日志：{describe(directory / label)}.stderr/.stdout")
    print(f"  {label} 完成（{elapsed:.0f}s）")
    return result


def load_lock() -> dict:
    """读取固定 SDK 清单；缺 windows_source/windows_build 时给出可执行的下一步。"""
    with LOCK.open("rb") as source:
        lock = json.load(source)
    for key in ("windows_source", "windows_build"):
        if key not in lock:
            raise RuntimeError(f"vendor/llvm/sdk.lock.json 缺少 {key}：Windows 闭包需要显式声明"
                               "源码包与 MSVC 构建参数")
    return lock


def layout() -> dict:
    """从 `[link-windows-x64]` 反推闭包根与四组成员。

    每条形如 `../tmp/llvm-migration/windows-llvm-closure/<组>/<文件名>`。清单是编译器
    与脚本的共同契约，所以这里只校验形态、不自己拼目录；形态不符就报错，而不是
    静默写到编译器看不见的地方。
    """
    with MANIFEST.open("rb") as source:
        manifest = tomllib.load(source)
    section = manifest.get(SECTION)
    if section is None:
        raise RuntimeError(f"{MANIFEST} 缺少 [{SECTION}]：Windows 宿主无法链接")
    roots: set[Path] = set()
    groups: dict[str, list[Path]] = {}
    for group in GROUPS:
        entries = section.get(group) or []
        if not entries:
            raise RuntimeError(f"[{SECTION}].{group} 为空：Windows 闭包的 {group} 组不能缺")
        paths = []
        for entry in entries:
            path = Path(entry)
            if path.is_absolute():
                raise RuntimeError(f"[{SECTION}].{group} 仍是绝对路径 {entry}："
                                   "改成 ../tmp/llvm-migration/windows-llvm-closure/"
                                   f"{group}/<文件名> 的 canonical 相对路径")
            resolved = (MANIFEST.parent / path).resolve()
            if resolved.parent.name != group:
                raise RuntimeError(f"[{SECTION}].{group} 的 {entry} 不在 {group}/ 目录下："
                                   "布局必须是 <闭包根>/<组>/<文件名>")
            roots.add(resolved.parent.parent)
            paths.append(resolved)
        groups[group] = paths
    if len(roots) != 1:
        raise RuntimeError(f"[{SECTION}] 的四组归档不在同一个闭包根下：{sorted(map(str, roots))}")
    return {"root": roots.pop(), "groups": groups}


def missing_archives(layout_spec: dict) -> list[Path]:
    """按清单顺序列出缺失的归档（不计算哈希：完整路径校验比身份校验更便宜）。"""
    return [path for group in GROUPS for path in layout_spec["groups"][group]
            if not path.is_file()]


def host_status() -> int:
    """离线复核身份记录：0 就绪；3 未准备或内容已变化。"""
    result = subprocess.run([sys.executable, str(HOST_TOOL), "status", "--host", HOST],
                            cwd=ROOT, check=False)
    return result.returncode


def prepare() -> int:
    """按清单重算身份记录（tools/llvm-windows-host.py prepare 是唯一写入方）。"""
    result = subprocess.run([sys.executable, str(HOST_TOOL), "prepare", "--host", HOST],
                            cwd=ROOT, check=False)
    return result.returncode


def summarize(layout_spec: dict) -> str:
    """把四组数量排成一行摘要，供日志与失败诊断引用。"""
    counts = "、".join(f"{group} {len(layout_spec['groups'][group])}" for group in GROUPS)
    return f"{counts}（{describe(layout_spec['root'])}）"


def materialize_source(lock: dict) -> Path:
    """下载/校验/解包 llvm-project 源码，返回 `<源>/llvm` 的父目录。

    缓存语义按内容判断：tar 的 SHA-256 与锁一致才复用，解包目录里有
    `llvm/CMakeLists.txt` 才认为完整，否则重下/重解。
    """
    spec = lock["windows_source"]
    work = work_root()
    work.mkdir(parents=True, exist_ok=True)
    tarball = work / spec["package"]
    if tarball.is_file() and digest(tarball) == spec["sha256"]:
        print(f"源码包已在工作区：{describe(tarball)}")
    else:
        print(f"下载 {spec['url']}（{spec['size_bytes'] / 1048576:.0f} MiB）…")
        partial = tarball.with_suffix(tarball.suffix + ".partial")
        with urllib.request.urlopen(spec["url"]) as response, partial.open("wb") as sink:
            shutil.copyfileobj(response, sink, length=1 << 20)
        actual = digest(partial)
        if actual != spec["sha256"]:
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"源码包校验失败：期望 {spec['sha256']}，实际 {actual}；"
                               "删除工作区后重试，或检查网络代理是否改写了内容")
        partial.replace(tarball)
        print(f"源码包校验通过（SHA-256 {actual[:12]}）")
    extracted = work / spec["package"].removesuffix(".tar.xz")
    if (extracted / "llvm/CMakeLists.txt").is_file():
        print(f"源码已解包：{describe(extracted)}")
        return extracted
    print(f"解包到 {describe(extracted)}（约 2 GB，需几分钟）…")
    with tarfile.open(tarball) as archive:
        # filter="data" 拒绝绝对路径/设备文件等危险成员（Python 3.12+）。
        if hasattr(tarfile, "data_filter"):
            archive.extractall(work, filter="data")
        else:
            archive.extractall(work)
    if not (extracted / "llvm/CMakeLists.txt").is_file():
        raise RuntimeError(f"解包后没有 {describe(extracted / 'llvm/CMakeLists.txt')}："
                           "源码包结构异常，删除工作区后重试")
    return extracted


def cmake_definitions(build: dict) -> list[str]:
    """把 lock 的 windows_build 展开成 CMake -D 参数（与 configure.sh 一一对应）。"""
    for key in ("build_type", "vc_runtime_library", "projects", "targets"):
        if key not in build:
            raise RuntimeError(f"vendor/llvm/sdk.lock.json 的 windows_build 缺少 {key}")
    definitions = [
        f"-DCMAKE_BUILD_TYPE={build['build_type']}",
        f"-DCMAKE_MSVC_RUNTIME_LIBRARY={build['vc_runtime_library']}",
        f"-DLLVM_ENABLE_PROJECTS={';'.join(build['projects'])}",
        f"-DLLVM_TARGETS_TO_BUILD={';'.join(build['targets'])}",
    ]
    for key, name in CMAKE_BOOLEANS:
        if key not in build:
            raise RuntimeError(f"vendor/llvm/sdk.lock.json 的 windows_build 缺少 {key}")
        definitions.append(f"-D{name}={'ON' if build[key] else 'OFF'}")
    return definitions


def visual_studio_instance() -> str:
    """用 vswhere 定位带 C++ 工具链的 VS 实例；找不到返回空串（让 CMake 自行探测）。"""
    if not VSWHERE.is_file():
        return ""
    result = subprocess.run(
        [str(VSWHERE), "-latest", "-products", "*",
         "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
         "-property", "installationPath"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def configure_and_build(source: Path, lock: dict, jobs: int) -> Path:
    """CMake 配置 + Release 构建，返回 `<构建树>/Release/lib`。"""
    build_spec = lock["windows_build"]
    generator = build_spec.get("generator", "Visual Studio 17 2022")
    work = work_root()
    build_dir = work / "build"
    instance = visual_studio_instance()
    definitions = list(cmake_definitions(build_spec))
    if instance:
        definitions.append(f"-DCMAKE_GENERATOR_INSTANCE={instance}")
        print(f"  Visual Studio 实例：{instance}")
    print(f"CMake 配置（{generator}，{build_spec['build_type']}，/MT）…")
    try:
        run(["cmake", "-G", generator, "-A", build_spec.get("architecture", "x64"),
             *definitions, "-S", source / "llvm", "-B", build_dir],
            "cmake-configure", cwd=work)
    except RuntimeError as error:
        raise RuntimeError(
            f"{error}\n诊断：cmake={shutil.which('cmake')}；"
            f"vswhere={VSWHERE if VSWHERE.is_file() else '<缺失>'}；"
            f"VS 实例={instance or '<vswhere 未找到带 C++ 工具链的实例>'}") from error
    print(f"CMake 构建（{jobs} 路并行，首次约 30–90 分钟）…")
    run(["cmake", "--build", build_dir, "--config", build_spec["build_type"],
         "--parallel", str(jobs)], "cmake-build", cwd=work)
    libraries = build_dir / build_spec["build_type"] / "lib"
    if not libraries.is_dir():
        raise RuntimeError(f"构建后没有 {describe(libraries)}："
                           "确认 windows_build 的 build_type 与实际配置一致")
    return libraries


def find_llvm_tool(name: str) -> str:
    """定位 clang-cl / llvm-lib：PATH 优先，其次官方 LLVM 安装目录。"""
    found = shutil.which(name)
    if found:
        return found
    fallback = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "LLVM/bin" / f"{name}.exe"
    if fallback.is_file():
        return str(fallback)
    raise RuntimeError(f"找不到 {name}：安装 LLVM（winget install LLVM.LLVM）或把它加入 PATH")


def write_lld_config(directory: Path, identity: str) -> Path:
    """生成 `lld_link_config.h`：Windows 用自己的 lld 驱动，默认模板只有 `ld.lld`。

    复用 tools/llvm-sdk.py 的写头函数（与 Linux 同一份格式），避免出现第二套
    「默认链接参数」的实现。
    """
    sdk = runpy.run_path(str(SDK_TOOL))
    header = directory / "lld_link_config.h"
    sdk["write_lld_config_header"](header, ["ld.lld"], [], [], [], identity)
    return header


def lld_identity(lock: dict, layout_spec: dict) -> str:
    """桥身份：只取内容与固定参数，不含构建机路径（换机器不改变身份）。"""
    payload = {
        "lock": digest(LOCK),
        "bridge": digest(BRIDGE_DIR / "bridge.c"),
        "header": digest(BRIDGE_DIR / "bridge.h"),
        "lld": digest(BRIDGE_DIR / "lld_bridge.cpp"),
        "shim": digest(BRIDGE_DIR / "windows_shim.c"),
        "groups": {group: [path.name for path in layout_spec["groups"][group]]
                   for group in GROUPS},
        "build": lock["windows_build"],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def build_bridge(source: Path, libraries: Path, lock: dict, layout_spec: dict) -> Path:
    """用 clang-cl /MT 编三个 COFF 对象，llvm-lib 打包成闭包里的桥归档。"""
    directory = workdir() / "bridge"
    directory.mkdir(parents=True, exist_ok=True)
    clang = find_llvm_tool("clang-cl")
    lib_tool = find_llvm_tool("llvm-lib")
    write_lld_config(directory, lld_identity(lock, layout_spec))
    include = [source / "llvm/include", libraries.parent.parent / "include"]
    lld_include = [source / "lld/include", libraries.parent.parent / "tools/lld/include"]
    print("用 clang-cl /MT 编译桥（bridge.c + lld_bridge.cpp + windows_shim.c）…")
    objects = []
    for script, name, flags in BRIDGE_OBJECTS:
        target = directory / name
        extra_include = [f"-I{item}" for item in lld_include] if script.endswith(".cpp") else []
        run([clang, "/nologo", "/MT", "/O2", "/W3", *flags, "/c", BRIDGE_DIR / script,
             *[f"-I{item}" for item in include], *extra_include,
             f"-I{directory}", f"/Fo{target}"], f"clang-{name}")
        objects.append(target)
    archive = layout_spec["groups"]["bridge"][0]
    archive.parent.mkdir(parents=True, exist_ok=True)
    run([lib_tool, "/nologo", f"/OUT:{archive}", *objects], "llvm-lib-bridge")
    return archive


def version_key(text: str) -> tuple[int, ...]:
    """把 `14.41.34120` / `10.0.22621.0` 这类目录名变成可比较的版本元组。"""
    parts = []
    for chunk in text.split("."):
        digits = "".join(char for char in chunk if char.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def visual_studio_paths() -> list[Path]:
    """用 vswhere + 注册表定位 MSVC 与 Windows SDK 的 x64 归档目录。

    `cl`/`lib` 不在 PATH 是 Windows runner 的常态，所以不能依赖环境变量；
    vswhere 随 VS Installer 固定安装，注册表键 KitsRoot10 指向 Windows SDK。
    """
    vswhere = (Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
               / "Microsoft Visual Studio/Installer/vswhere.exe")
    if not vswhere.is_file():
        raise RuntimeError(f"找不到 {vswhere}：安装 Visual Studio 2022（含 MSVC x64 生成工具）")
    result = subprocess.run([str(vswhere), "-latest", "-products", "*", "-property",
                             "installationPath"], capture_output=True, text=True,
                            check=False)
    installation = result.stdout.strip()
    if result.returncode or not installation:
        raise RuntimeError(f"vswhere 未找到 Visual Studio 安装：{result.stderr.strip()[-1000:]}；"
                           "安装 VS 2022 的「使用 C++ 的桌面开发」工作负载")
    tools = Path(installation) / "VC/Tools/MSVC"
    versions = sorted((path for path in tools.glob("*") if path.is_dir()),
                      key=lambda path: version_key(path.name))
    if not versions:
        raise RuntimeError(f"{describe(tools)} 下没有 MSVC 版本：安装「使用 C++ 的桌面开发」工作负载")
    msvc_lib = versions[-1] / "lib/x64"
    sdk_root = windows_sdk_root()
    sdk_versions = sorted((path for path in (sdk_root / "Lib").glob("10.*") if path.is_dir()),
                          key=lambda path: version_key(path.name))
    if not sdk_versions:
        raise RuntimeError(f"{describe(sdk_root / 'Lib')} 下没有 Windows SDK：安装 Windows 10/11 SDK")
    sdk = sdk_versions[-1]
    return [msvc_lib, sdk / "ucrt/x64", sdk / "um/x64"]


def windows_sdk_root() -> Path:
    """Windows SDK 根目录：注册表 KitsRoot10（有尾反斜杠，交给 Path 归一）。"""
    try:
        import winreg
    except ImportError as error:  # 只在 Windows 上运行，理论到不了这里
        raise RuntimeError(f"无法读取 Windows Kits 注册表：{error}")
    key_path = r"SOFTWARE\Microsoft\Windows Kits\Installed Roots"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            root = winreg.QueryValueEx(key, "KitsRoot10")[0]
    except OSError as error:
        raise RuntimeError(f"注册表 {key_path} 没有 KitsRoot10：安装 Windows SDK（{error}）")
    return Path(root)


def install_archives(layout_spec: dict, libraries: Path) -> None:
    """把构建产物与支撑归档按清单落到闭包目录（成员与顺序完全按清单）。"""
    root = layout_spec["root"]
    for group in ("lld", "llvm"):
        for name in (path.name for path in layout_spec["groups"][group]):
            source = libraries / name
            if not source.is_file():
                raise RuntimeError(f"构建产物缺少 {group}/{name}：清单成员与 windows_build 的 "
                                   "projects/targets 不一致；先确认清单没有过期")
            destination = root / group / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        print(f"  复制 {group} 组 {len(layout_spec['groups'][group])} 个归档")
    search = visual_studio_paths()
    print(f"从本机 MSVC/SDK 取 support 归档（{describe(search[0])} 等）：")
    for name in (path.name for path in layout_spec["groups"]["support"]):
        found = next((directory / name for directory in search if (directory / name).is_file()),
                     None)
        if found is None:
            raise RuntimeError(f"找不到 support 归档 {name}：在 "
                               f"{'、'.join(describe(directory) for directory in search)} 中都没有；"
                               "确认 VS 2022（14.x）与 Windows SDK 已安装")
        destination = root / "support" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(found, destination)
    print(f"  复制 support 组 {len(layout_spec['groups']['support'])} 个归档")


def build(args) -> int:
    """幂等入口：复用 → 只刷身份 → 否则完整源码构建，最后写身份记录。"""
    require_windows()
    layout_spec = layout()
    started = time.monotonic()
    if host_status() == 0:
        print(f"Windows 固定闭包已就绪，直接复用：{summarize(layout_spec)}")
        return 0
    missing = missing_archives(layout_spec)
    if not missing:
        print(f"闭包归档齐全，只刷新身份记录：{summarize(layout_spec)}")
        code = prepare()
        print(f"完成（{time.monotonic() - started:.1f}s）")
        return code
    print(f"Windows 固定闭包缺 {len(missing)} 个归档（例如 {describe(missing[0])}），"
          f"开始源码构建；工作区 {describe(work_root())}")
    lock = load_lock()
    source = materialize_source(lock)
    libraries = configure_and_build(source, lock, args.jobs)
    build_bridge(source, libraries, lock, layout_spec)
    install_archives(layout_spec, libraries)
    code = prepare()
    if code == 0:
        print(f"Windows 固定闭包构建完成：{summarize(layout_spec)}"
              f"（总耗时 {time.monotonic() - started:.0f}s）")
    return code


def status(_args) -> int:
    """等价 tools/llvm-windows-host.py status：0 就绪，3 未准备/已变化。"""
    require_windows()
    return host_status()


def main() -> int:
    """解析子命令并分派。"""
    parser = argparse.ArgumentParser(description="Windows/x86_64 固定 LLVM 闭包准备")
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build", help="准备闭包（幂等）")
    build_parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4,
                              help="CMake 并行度（默认 CPU 核数；CI 由 LLVM_JOBS 控制）")
    sub.add_parser("status", help="离线复核身份记录")
    args = parser.parse_args()
    if args.command == "status":
        return status(args)
    return build(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"llvm-windows-closure：{error}", file=sys.stderr)
        sys.exit(1)
