#!/usr/bin/env python3
"""tools/windows-sdk.py —— Windows 导入库（SDK stub）生成与校验（W1-4）。

仓库只保存**文本** `.def`（`compiler/windows-sdk/def/*.def`）与清单
（`compiler/windows-sdk/manifest.json`）。`.lib` 是 COFF 归档，按仓库根
`.gitignore`（`*.lib`）属构建产物，因此按需生成到缓存目录，不入库。

生成器优先级：`llvm-dlltool -m i386:x86-64` → `lld-link /lib /def:` → `lib.exe`。
2026-10-27 实测前两者的产物**逐字节相同**（同一 def、同样字节数、同一 sha256），
所以换生成器不会让身份漂移；但调用方仍需记录实际用了哪个工具（identity.json）。

子命令：

    generate [--out DIR]   按清单生成 <out>/lib/<name>.lib 与 <out>/identity.json
    check    [--out DIR]   校验 def 哈希、导出面、生成幂等与符号面
    paths                  打印解析结果（JSON），供 justfile / 编译器侧对照

解析顺序（编译器 W1-5 必须镜像同一顺序）：
    1. `$YH_WINDOWS_SDK` —— 指向含 `lib/` 与 `manifest.json` 的 SDK 根；
    2. 仓库 bundle `compiler/windows-sdk`（本地开发时可直接 `--out` 到它）；
    3. 都没有时给出可操作诊断，**不静默回退**到系统 Windows SDK。

用法示例：

    python3 tools/windows-sdk.py generate              # 写到缓存目录
    python3 tools/windows-sdk.py check                 # 校验已生成产物
    python3 tools/windows-sdk.py generate --out compiler/windows-sdk

退出码：0 成功；1 失败（带可执行下一步）；2 用法错误。
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Windows 控制台默认 GBK，中文输出会抛 UnicodeEncodeError；统一成 UTF-8 + 可替换。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from llvm_cache import cache_root  # noqa: E402

# bundle：仓库内的文本 SDK（源文件 + 清单），永远是身份的来源。
BUNDLE = ROOT / "compiler/windows-sdk"
# 生成产物的默认位置：与 LLVM 闭包同级的缓存根，避免污染工作树。
DEFAULT_OUT = cache_root() / "windows-sdk"

# llvm-dlltool 的机器名（不是 LLVM triple）：x86_64 对应 i386:x86-64。
DLLTOOL_MACHINE = "i386:x86-64"
# PE/COFF machine 编号：IMAGE_FILE_MACHINE_AMD64 = 0x8664。
VALID_MACHINES = {0x8664: "x86_64-pc-windows-msvc"}


class SdkError(RuntimeError):
    """SDK 生成/校验失败；message 必须带可执行的下一步。"""


def sha256_file(path: Path) -> str:
    """分块计算文件 sha256；导入库只有几 KB，但保持与仓库其它校验一致的写法。"""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def load_manifest(bundle: Path = BUNDLE) -> dict:
    """读取并做最小结构校验；字段缺失时立刻失败，避免生成半个 SDK。"""
    path = bundle / "manifest.json"
    if not path.is_file():
        raise SdkError(f"缺少清单：{path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SdkError(f"清单不是合法 JSON：{path}: {error}") from error
    if manifest.get("machine") not in VALID_MACHINES:
        raise SdkError(
            f"清单的 machine 不是支持的 PE 机器码：{manifest.get('machine')}（应为 34404/0x8664）")
    for library in manifest.get("libraries", []):
        for field in ("dll", "def", "import_library", "def_sha256", "exports"):
            if field not in library:
                raise SdkError(f"清单条目缺少字段 {field}：{library}")
        if not (bundle / library["def"]).is_file():
            raise SdkError(f"清单引用的 .def 不存在：{bundle / library['def']}")
    if not manifest.get("libraries"):
        raise SdkError(f"清单没有任何库：{path}")
    return manifest


def parse_def_exports(path: Path) -> list[str]:
    """从 .def 文本里取出导出名（保持出现顺序）。

    只支持本项目实际用到的子集：`LIBRARY` 头部、`EXPORTS` 段、每行一个名字
    （允许 `名字 @序号`、`名字=别名`、`;` 注释）。遇到超出子集的写法直接失败，
    不去猜——.def 是我们自己写的，猜错只会让导入库与清单悄悄漂移。
    """
    exports: list[str] = []
    in_exports = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("EXPORTS"):
            in_exports = True
            rest = line[len("EXPORTS"):].strip()
            if rest:
                exports.append(_def_name(rest, path))
            continue
        if not in_exports:
            if upper.startswith(("LIBRARY", "NAME", "DESCRIPTION", "STACKSIZE", "HEAPSIZE",
                                 "SECTIONS", "VERSION", "CODE", "DATA")):
                continue
            raise SdkError(f".def 在 EXPORTS 之前出现未支持的行：{path}: {line}")
        exports.append(_def_name(line, path))
    if not exports:
        raise SdkError(f".def 没有导出任何符号：{path}")
    return exports


def _def_name(line: str, path: Path) -> str:
    """取一行导出的符号名；拒绝序号/别名/修饰写法（需要时再显式扩展）。"""
    name = line.split()[0]
    if "=" in name or name.startswith("@") or not name.replace("_", "a").isalnum():
        raise SdkError(f".def 导出写法超出支持范围（只接受纯名字）：{path}: {line}")
    return name


def resolve_generator(explicit: str | None, tool_root: str | None) -> tuple[str, Path]:
    """定位导入库生成器，返回 (kind, 可执行文件路径)。

    kind 会写进 identity.json：换生成器不改变产物字节（已实测），但换了的**事实**
    必须可追溯。tool_root 用于 CI/容器把 LLVM bin 目录显式指出来。
    """
    search_dir = Path(tool_root) if tool_root else None
    candidates = []
    if explicit:
        if not Path(explicit).is_file():
            raise SdkError(f"--tool 指向的生成器不存在：{explicit}")
        candidates.append(("llvm-dlltool", explicit))
    for name, kind in (("llvm-dlltool", "llvm-dlltool"), ("lld-link", "lld-link"),
                       ("lib", "lib"), ("lib.exe", "lib")):
        found = None
        if search_dir is not None:
            for suffix in ("", ".exe"):
                probe = search_dir / f"{name}{suffix}"
                if probe.is_file():
                    found = str(probe)
                    break
        if found is None:
            found = shutil.which(name)
        if found is not None:
            candidates.append((kind, found))
    if not candidates:
        raise SdkError(
            "找不到导入库生成器：需要 llvm-dlltool（LLVM 工具链）或 lld-link / lib.exe。\n"
            "  - Windows：安装 LLVM（scoop install llvm）或 VS 的 C++ 工具链；\n"
            "  - Debian/Ubuntu：apt-get install llvm-21（提供 llvm-dlltool-21，建软链为 llvm-dlltool）；\n"
            "  - 或用 --tool / --tool-root 显式指定。")
    kind, path = candidates[0]
    return kind, Path(path)


def tool_identity(kind: str, path: Path) -> dict:
    """记录生成器身份：种类 + 文件名 + 内容哈希（不依赖 --version 输出格式）。"""
    return {"kind": kind, "name": path.name, "sha256": sha256_file(path)}


def find_c_compiler(clang: str | None) -> str:
    """定位能把 C 编成 COFF 的 clang（栈探测桩需要）。"""
    if clang:
        if not Path(clang).is_file():
            raise SdkError(f"--clang 指向的编译器不存在：{clang}")
        return clang
    for name in ("clang", "clang.exe"):
        found = shutil.which(name)
        if found:
            return found
    raise SdkError(
        "找不到 clang：生成栈探测桩需要能把 C 编到 x86_64-pc-windows-msvc 的 clang；\n"
        "  - Windows：scoop install llvm；Debian/Ubuntu：apt-get install clang；\n"
        "  - 或用 --clang 显式指定。")


def generate_object(clang_bin: str, source: Path, out_path: Path) -> None:
    """把 SDK 里的 C 桩编成 COFF 对象（栈探测桩，W1-3c）。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    command = [clang_bin, "--target=x86_64-pc-windows-msvc", "-O1",
               "-fno-stack-protector", "-c", str(source), "-o", str(out_path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, errors="replace")
    except OSError as error:
        raise SdkError(f"无法执行 clang：{error}") from error
    if result.returncode != 0 or not out_path.is_file():
        raise SdkError(f"编译 {source.name} 失败：\n{result.stdout}{result.stderr}")
    # COFF 头 4..7 是 TimeDateStamp：clang 写当前时间，同一份源码两次生成会字节
    # 不同（tests/selfhost/llvm-windows-sdk.py 的确定性门）。归零即可复现。
    data = bytearray(out_path.read_bytes())
    if len(data) >= 8 and data[0:2] == b"\x64\x86":
        data[4:8] = b"\x00\x00\x00\x00"
        out_path.write_bytes(bytes(data))


def generate_library(kind: str, tool: Path, def_path: Path, out_path: Path) -> None:
    """用一个 .def 生成导入库；失败时带原始输出抛 SdkError。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    if kind == "llvm-dlltool":
        command = [str(tool), "-m", DLLTOOL_MACHINE, "-d", str(def_path), "-l", str(out_path)]
    elif kind == "lld-link":
        command = [str(tool), "/lib", f"/def:{def_path}", "/machine:x64",
                   f"/out:{out_path}"]
    else:
        command = [str(tool), "/nologo", f"/def:{def_path}", "/machine:x64",
                   f"/out:{out_path}"]
    # errors="replace"：某些工具在非 UTF-8 环境下回中文/本地化输出，不能让它中断生成。
    try:
        result = subprocess.run(command, capture_output=True, text=True, errors="replace")
    except OSError as error:
        raise SdkError(f"无法执行导入库生成器 {tool}：{error}") from error
    if result.returncode != 0 or not out_path.is_file():
        raise SdkError(f"生成导入库失败（{' '.join(command)}）：\n{result.stdout}{result.stderr}")
    if out_path.stat().st_size == 0:
        raise SdkError(f"生成器产出空文件：{out_path}")


def generate(bundle: Path, out: Path, explicit_tool: str | None = None,
             tool_root: str | None = None, explicit_clang: str | None = None) -> dict:
    """按清单生成全部导入库，并写 identity.json（原子发布）。"""
    manifest = load_manifest(bundle)
    kind, tool = resolve_generator(explicit_tool, tool_root)
    lib_dir = out / "lib"
    records = []
    for library in manifest["libraries"]:
        def_path = bundle / library["def"]
        library_file = lib_dir / library["import_library"]
        generate_library(kind, tool, def_path, library_file)
        records.append({
            "dll": library["dll"],
            "def": library["def"],
            "def_sha256": sha256_file(def_path),
            "import_library": library["import_library"],
            "lib_sha256": sha256_file(library_file),
            "lib_bytes": library_file.stat().st_size,
            "exports": library["exports"],
        })
    # 额外的 COFF 桩对象（导出 __yh_chkstk）：LLVM 对 >4KB 的栈帧会发 call __chkstk，
    # 零 CRT 下没人提供它 —— 由这里的 naked asm 桩补上，链接期经 /alternatename 接手。
    objects = []
    if manifest.get("objects"):
        clang_bin = find_c_compiler(explicit_clang)
        for entry in manifest["objects"]:
            source = bundle / entry["source"]
            if not source.is_file():
                raise SdkError(f"清单引用的 C 桩不存在：{source}")
            target = lib_dir / entry["output"]
            generate_object(clang_bin, source, target)
            objects.append({
                "source": entry["source"],
                "output": entry["output"],
                "sha256": sha256_file(target),
                "bytes": target.stat().st_size,
                "compiler": tool_identity("clang", Path(clang_bin)),
            })
    identity = {
        "sdk": manifest["name"],
        "objects": objects,
        "version": manifest["version"],
        "abi": manifest["abi"],
        "machine": manifest["machine"],
        "generator": tool_identity(kind, tool),
        "libraries": records,
    }
    out.mkdir(parents=True, exist_ok=True)
    target = out / "identity.json"
    temporary = out / "identity.json.tmp"
    temporary.write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(target)
    return identity


def symbol_surface(library_file: Path, nm: str | None) -> set[str] | None:
    """读导入库里的 __imp_ 符号；没有 llvm-nm 时返回 None（由调用方决定是否降级）。"""
    if nm is None:
        return None
    result = subprocess.run([nm, str(library_file)], capture_output=True, text=True)
    if result.returncode != 0:
        raise SdkError(f"llvm-nm 读取失败：{library_file}:\n{result.stderr}")
    symbols = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] in ("I", "T"):
            symbols.add(parts[2])
    return symbols


def check(bundle: Path, out: Path, tool_root: str | None = None) -> list[str]:
    """返回问题列表（空 = 通过）。不做“部分通过”，全部核对一致才算过。"""
    problems: list[str] = []
    manifest = load_manifest(bundle)
    for library in manifest["libraries"]:
        def_path = bundle / library["def"]
        actual = sha256_file(def_path)
        if actual != library["def_sha256"]:
            problems.append(
                f"{library['def']} 内容已变（manifest 记录 {library['def_sha256'][:12]}…，"
                f"实际 {actual[:12]}…）：改过 .def 就要同步 manifest 的 def_sha256",
            )
        declared = parse_def_exports(def_path)
        if declared != library["exports"]:
            problems.append(
                f"{library['def']} 的导出与 manifest.exports 不一致：def={declared} "
                f"manifest={library['exports']}")
    identity_path = out / "identity.json"
    if not identity_path.is_file():
        problems.append(f"缺少生成产物清单：{identity_path}（先跑 generate）")
        return problems
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    if identity.get("abi") != manifest["abi"]:
        problems.append(f"identity.json 的 abi 与清单不一致：{identity.get('abi')}")
    nm = shutil.which("llvm-nm")
    for record in identity.get("libraries", []):
        library_file = out / "lib" / record.get("import_library", "")
        if not library_file.is_file():
            problems.append(f"缺少导入库：{library_file}（先跑 generate）")
            continue
        if sha256_file(library_file) != record.get("lib_sha256"):
            problems.append(f"导入库内容与 identity.json 不符（可能被就地改过）：{library_file}")
        expected = {f"__imp_{name}" for name in record.get("exports", [])}
        surface = symbol_surface(library_file, nm)
        if surface is None:
            print("警告：找不到 llvm-nm，跳过导入库符号面核对", file=sys.stderr)
        else:
            missing = sorted(expected - surface)
            if missing:
                problems.append(f"{library_file.name} 缺少导入符号：{missing}")
    nm_tool = shutil.which("llvm-nm")
    for record in identity.get("objects", []):
        target = out / "lib" / record.get("output", "")
        if not target.is_file():
            problems.append(f"缺少桩对象：{target}（先跑 generate）")
            continue
        if sha256_file(target) != record.get("sha256"):
            problems.append(f"桩对象内容与 identity.json 不符：{target}")
        data = target.read_bytes()
        if len(data) < 20 or data[0] != 0x64 or data[1] != 0x86:
            problems.append(f"{target.name} 不是 x86_64 COFF 对象")
        elif nm_tool is not None:
            result = subprocess.run([nm_tool, str(target)], capture_output=True,
                                    text=True, errors="replace")
            if "__yh_chkstk" not in result.stdout:
                problems.append(f"{target.name} 没有导出 __yh_chkstk")
    defs_in_identity = {record["def"] for record in identity.get("libraries", [])}
    defs_in_manifest = {library["def"] for library in manifest["libraries"]}
    if defs_in_identity != defs_in_manifest:
        problems.append(
            f"identity.json 与清单的库集合不同：identity={sorted(defs_in_identity)} "
            f"manifest={sorted(defs_in_manifest)}（重新 generate）")
    return problems


def paths(bundle: Path, out: Path) -> dict:
    """打印解析结果，供 justfile 与编译器侧（W1-5）对照解析顺序。"""
    env = os.environ.get("YH_WINDOWS_SDK")
    resolved = Path(env).expanduser() if env else out
    try:
        load_manifest(bundle)
        manifest_ok = True
    except SdkError:
        manifest_ok = False
    ready = (resolved / "lib").is_dir() and (resolved / "identity.json").is_file()
    return {
        "bundle": str(bundle),
        "cache_out": str(out),
        "YH_WINDOWS_SDK": env or "",
        "resolved_sdk_root": str(resolved),
        "lib_dir": str(resolved / "lib"),
        "manifest_ok": manifest_ok,
        "ready": ready,
    }


def main(argv: list[str] | None = None) -> int:
    # 公共选项同时挂在主命令与子命令上：`--out` 写在子命令前/后都成立，
    # justfile 与手跑的命令行不必记顺序（历史上 just 变量覆盖顺序就踩过坑）。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--bundle", default=str(BUNDLE),
                        help="文本 SDK 目录（含 manifest.json 与 def/）")
    common.add_argument("--out", default=str(DEFAULT_OUT),
                        help="生成/校验目录（默认缓存根下的 windows-sdk）")
    common.add_argument("--tool", default=None, help="显式指定生成器路径")
    common.add_argument("--tool-root", default=None, help="生成器所在目录（LLVM bin）")
    common.add_argument("--clang", default=None, help="编译 C 桩的 clang（生成 yh_chkstk.obj）")
    parser = argparse.ArgumentParser(
        description="Windows 导入库（SDK stub）生成与校验", parents=[common])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate", parents=[common], help="按清单生成导入库与 identity.json")
    sub.add_parser("check", parents=[common], help="校验 def 哈希、导出面与已生成导入库")
    sub.add_parser("paths", parents=[common], help="打印解析结果（JSON）")
    args = parser.parse_args(argv)
    bundle = Path(args.bundle)
    out = Path(args.out)
    try:
        if args.command == "generate":
            identity = generate(bundle, out, args.tool, args.tool_root, args.clang)
            print(f"已生成 {len(identity['libraries'])} 个导入库 -> {out / 'lib'}")
            for record in identity["libraries"]:
                print(f"  {record['dll']}: {record['import_library']} "
                      f"{record['lib_bytes']} 字节 sha256={record['lib_sha256'][:12]}…")
        elif args.command == "check":
            problems = check(bundle, out, args.tool_root)
            if problems:
                for problem in problems:
                    print(f"错误：{problem}", file=sys.stderr)
                print("修复：python3 tools/windows-sdk.py generate", file=sys.stderr)
                return 1
            print("Windows SDK stub 校验通过：def 哈希、导出面、导入库内容与符号面一致")
        else:
            print(json.dumps(paths(bundle, out), ensure_ascii=False, indent=2))
        return 0
    except SdkError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
