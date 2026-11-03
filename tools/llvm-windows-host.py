#!/usr/bin/env python3
"""tools/llvm-windows-host.py —— Windows/x86_64 固定 LLVM 闭包的身份记录（W2-5）。

Windows 宿主与 Linux/Darwin 有一个结构差异：闭包（桥 + lld + 静态 LLVM + 静态
CRT）由 MSVC/cmake 在 Windows 上构建，归档直接写进 `compiler/project.toml` 的
`[link-windows-x64]`，**不需要链接包装器（shim）**——Windows 上的最终链接由
内嵌 lld 的 WinLink 驱动在进程内完成，不存在「拼 gcc 命令行」这一步。

因此本脚本不构建任何东西，只做三件事：

    prepare  读取 `[link-windows-x64]`，确认每一组归档真的存在，把整组内容的
             聚合身份写进 `<缓存根>/llvm-host-windows-x86_64/host.json`
    status   离线复核记录：归档缺失或内容变化则退出码 3（调用方据此报明确诊断）
    shim     准备后输出记录 JSON（tools/seed-build.py 经 --llvm-host 消费；
             清单模式下不生成包装器，`shim_dir` 字段留空）

为什么需要它：`just bootstrap` / `just llvm-host` 在所有宿主上都要能回答
「本机的固定闭包是否就绪」。没有这个驱动时，Windows 上的 llvm_host 是空串，
`just bootstrap` 只会打印「当前种子没有对应的固定 LLVM SDK」，看不出真实原因
（闭包路径失效 / MSVC 升级导致 CRT 路径变化 / 归档被清理）。

闭包本体由 `tools/llvm-windows-closure.py` 准备到缓存根的
`windows-llvm-closure/{bridge,lld,llvm,support}`，清单里写的是指向那里的 canonical
相对路径；本脚本只负责**证明它还在、内容没变**：归档缺失或内容变化都能被发现，
错误提示指向可执行的下一步，而不是让链接阶段报天书。

退出码：0 成功；3 未准备或身份失效；1 其他错误。
"""

import argparse
import hashlib
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from llvm_cache import cache_root  # noqa: E402

MANIFEST = ROOT / "compiler/project.toml"
HOST = "windows-x86_64"
SECTION = "link-windows-x64"
NOT_READY = 3
# 归档组：bridge 是 yh 自己的桥，其余由固定 SDK 提供；support 里的静态 CRT 来自
# 本机 MSVC 安装，随 Visual Studio 升级而变，因此单独统计、失败时给出定向提示。
GROUPS = ("bridge", "lld", "llvm", "support")


def digest(path: Path) -> str:
    """分块计算文件身份；静态归档累计 485 MB，不整块读入内存。"""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def record_path() -> Path:
    """身份记录位置：缓存根下按宿主命名，与 llvm-host-<宿主> 的约定一致。"""
    return cache_root() / "llvm-host-windows-x86_64" / "host.json"


def closure_archives() -> dict[str, list[Path]]:
    """从项目清单读出 `[link-windows-x64]` 四组归档的绝对路径。

    相对路径按 `compiler/` 解析（与编译器的解释一致），所以清单里的 canonical
    条目 `../tmp/llvm-migration/windows-llvm-closure/<组>/<文件名>` 无论缓存根
    落在仓库内还是仓库外，都能按仓库内路径解析到同一处。
    """
    with MANIFEST.open("rb") as source:
        manifest = tomllib.load(source)
    section = manifest.get(SECTION)
    if section is None:
        raise RuntimeError(f"{MANIFEST} 缺少 [{SECTION}]：Windows 宿主无法链接")
    archives: dict[str, list[Path]] = {}
    for group in GROUPS:
        entries = section.get(group, [])
        paths = []
        for entry in entries:
            path = Path(entry)
            if not path.is_absolute():
                path = (MANIFEST.parent / path).resolve()
            paths.append(path)
        archives[group] = paths
    if not archives["bridge"]:
        raise RuntimeError(f"[{SECTION}] 缺少 bridge 组：桥归档没有提供")
    return archives


def inspect(archives: dict[str, list[Path]]) -> dict:
    """校验归档存在性并计算聚合身份；缺失项按组收集，便于定向报错。"""
    missing: dict[str, list[str]] = {}
    identity: dict[str, dict[str, str]] = {}
    for group in GROUPS:
        identity[group] = {}
        for path in archives[group]:
            if not path.is_file():
                missing.setdefault(group, []).append(str(path))
                continue
            identity[group][str(path)] = digest(path)
    # 聚合身份覆盖四组内容：任一组归档内容变化（重编 SDK / 升级 MSVC CRT）
    # 都会改变它，从而让 status 明确报「闭包已变化」而不是静默复用旧记录。
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return {
        "archives": {group: [str(p) for p in paths] for group, paths in archives.items()},
        "missing": missing,
        "identity": identity,
        "closure_sha256": hashlib.sha256(payload).hexdigest(),
        "bridge_sha256": next(iter(identity["bridge"].values()), ""),
    }


def failure_hint(missing: dict[str, list[str]]) -> str:
    """把缺失的归档组翻译成可执行的下一步。"""
    lines = ["固定 LLVM 闭包不完整："]
    for group, paths in missing.items():
        lines.append(f"  {group}：缺 {len(paths)} 个，例如 {paths[0]}")
    if "support" in missing:
        lines.append("  support 组来自本机 MSVC 与 Windows SDK：升级 VS/SDK 后重新运行 "
                     "just llvm-host（tools/llvm-windows-closure.py 会用 vswhere 重新复制）")
    if "lld" in missing or "llvm" in missing:
        lines.append("  静态 LLVM/lld 闭包缺失：运行 just llvm-host 从固定源码重建"
                     "（或恢复 $YH_LLVM_CACHE 下的 windows-llvm-closure）")
    if "bridge" in missing:
        lines.append("  桥归档缺失：运行 just llvm-host——它会用 clang-cl /MT 编 "
                     "bridge.c + lld_bridge.cpp + windows_shim.c 并打包到闭包里")
    return "\n".join(lines)


def prepare(args, quiet: bool = False) -> int:
    """校验清单里的闭包并写入身份记录（幂等：内容不变就不重写）。

    quiet 只在 `shim` 里为真：那条路径要求 stdout 只有一个 JSON 记录，摘要会污染它。
    """
    archives = closure_archives()
    report = inspect(archives)
    if report["missing"]:
        print(failure_hint(report["missing"]), file=sys.stderr)
        return NOT_READY
    record = {
        "host": HOST,
        "build_host": HOST,
        "scope": "manifest",
        "shim_dir": "",
        "closure_sha256": report["closure_sha256"],
        "bridge_archive": report["archives"]["bridge"][0],
        "bridge_sha256": report["bridge_sha256"],
        "archives": report["archives"],
        "counts": {group: len(paths) for group, paths in report["archives"].items()},
    }
    target = record_path()
    if target.is_file():
        try:
            previous = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
        if previous.get("closure_sha256") != record["closure_sha256"]:
            previous = {}
    else:
        previous = {}
    if not previous:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    if not quiet:
        counts = "、".join(f"{group} {count}" for group, count in record["counts"].items())
        print(f"Windows 固定闭包已记录：{counts}；identity {record['closure_sha256'][:12]}"
              f"（{target}）")
    return 0


def status(_args) -> int:
    """离线复核记录：记录缺失、闭包缺失或内容变化都判为未就绪。"""
    target = record_path()
    if not target.is_file():
        print(f"Windows 固定闭包尚未记录：先运行 just llvm-host（{target}）",
              file=sys.stderr)
        return NOT_READY
    record = json.loads(target.read_text(encoding="utf-8"))
    report = inspect(closure_archives())
    if report["missing"]:
        print(failure_hint(report["missing"]), file=sys.stderr)
        return NOT_READY
    if report["closure_sha256"] != record.get("closure_sha256"):
        print("Windows 固定闭包内容已变化：重新运行 just llvm-host 刷新记录",
              file=sys.stderr)
        return NOT_READY
    counts = "、".join(f"{group} {count}" for group, count in record["counts"].items())
    print(f"Windows 固定闭包与记录一致：{counts}；identity "
          f"{record['closure_sha256'][:12]}（{target}）")
    return 0


def shim(args) -> int:
    """为 tools/seed-build.py 输出宿主记录；清单模式下没有包装器目录。

    与 Linux/Darwin 的 shim 不同，这里不准备任何东西就能直接返回记录——归档已经
    写在项目清单里，链接由内嵌 lld 在进程内完成。失败返回非零，由 seed-build
    按自己的 --llvm-mode 决定是警告还是中止。
    """
    # 失败一律返回非零：seed-build 的 auto 模式据此打印诊断后继续构建，
    # require 模式据此中止。记录本身作为唯一一行 JSON 输出给调用方。
    code = prepare(args, quiet=True)
    if code != 0:
        return code
    print(json.dumps(json.loads(record_path().read_text(encoding="utf-8")),
                     ensure_ascii=False))
    return 0


def main() -> int:
    """解析子命令并分派。"""
    parser = argparse.ArgumentParser(description="Windows/x86_64 固定 LLVM 闭包记录")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "status", "shim"):
        item = sub.add_parser(name)
        item.add_argument("--host", default=HOST)
        item.add_argument("--mode", choices=("auto", "require"), default="auto")
    args = parser.parse_args()
    if args.host != HOST:
        print(f"错误：本驱动只支持 {HOST}，收到 {args.host}", file=sys.stderr)
        return 1
    if args.command == "prepare":
        return prepare(args)
    if args.command == "status":
        return status(args)
    return shim(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"llvm-windows-host：{error}", file=sys.stderr)
        sys.exit(1)
