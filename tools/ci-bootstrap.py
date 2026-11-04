#!/usr/bin/env python3
"""tools/ci-bootstrap.py —— 过渡期自举桥：用 0.0.11 种子编出「认识 W2 平台标记」的编译器。

背景（2026-11-03）：W2 把 Windows 平台变体与 `[link-windows-x64]` 合入 llvm 主线，
但 0.0.11 Release 的 Linux/macOS 种子是合入 W2 之前的编译器，它有三处不认识 HEAD：

  1. comptime 标记 `windows`：0.0.11 的 `ct_target_symbol` 只认 linux/darwin/arm64/x64，
     HEAD 的 10 处 `$if (windows)` 会让它在编译期报「引用了未声明的名字」；
  2. `*.windows.*.yh` 平台变体（15 个文件）：0.0.11 的 project_index 没有 windows
     标记登记，会把这些文件当普通源码编入本目标，造成顶层符号重定义；
  3. 清单里的 `[link-windows-x64]`：0.0.11 判成非法链接节，直接失败。

Windows 种子已按 HEAD 重编并上传到 0.0.11（`yh-0.0.11-windows-x64.tar.gz`），
认识 W2 的变体/标记/链接节。2026-11-05 起 Linux/macOS 与 Windows 都走两代
自举——所有宿主都要处理 VTEST 测试文件改名（`.test.yh` 无排序前缀，0.0.11
代种子按字典序扫描会排错；staging 临时加回 `zz_` 前缀，见 test_rename_pairs），
Windows 宿主跳过变体/标记/链接节三类改写：

  第 1 代：把源码临时改成「0.0.11 认识的等价形态」——
          * 15 个 `*.windows.*.yh` 变体暂时移出；
          * 10 处 `$if (windows)` 改成对侧 OS 标记（Linux 宿主改 darwin，Darwin 宿主
            改 linux）：两者在**非 Windows 宿主**上恒为假，语义与 windows 分支相同；
            yh1 编译 HEAD 时要用到 windows 标记识别，识别代码（ct_target_symbol）
            是普通源码，不改动，所以 yh1 仍然认识 windows；
          * 清单去掉两个 windows 链接节。
          用 Release 种子冷编 → yh1（含 HEAD 全部逻辑与平台变体过滤，仅 Windows
          宿主行为不适用——它只在本机非 Windows 宿主上跑）。
  第 2 代：原样恢复源码与清单，用 yh1 冷编全量 HEAD → 仓库根目录 yh。

此后 CI 的平台门与自举门都以根目录 yh 为准；`selfhost-native` 要显式
`SEED=<仓库绝对路径>/yh`，否则会退回不认识 W2 的 0.0.11 种子。

生命安全线：所有临时改动在进程内 finally 恢复；同时把原始内容备份到
`<staged>/orig/`，进程若被强杀，下次运行开头会先按备份恢复（崩溃恢复）。

生命周期：本脚本只服务「0.0.11 种子不认识 W2」这一过渡期。等包含 W2 种子的
新 Release 发布（下一次 0.0.12-rc.1 起），CI 与 justfile 的接线、本脚本一起删除，
见 docs/todo.md 的对应条目。

用法（先 `just llvm-host` 备好固定闭包）：
    python3 tools/ci-bootstrap.py run [--seed 路径] [--output 路径]
                                     [--staged 路径] [--keep-staged]

退出码：0 成功；1 任一步失败（失败时也会尽力恢复源码与清单）。
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_BUILD = ROOT / "tools/seed-build.py"

# 旧种子不认识、必须在第 1 代暂时移出的 Windows 平台变体（共 15 个）。
VARIANT_PATTERNS = ("*.windows.yh", "*.windows.*.yh")
VARIANT_ROOTS = ("compiler", "libs")

# 旧种子会判非法的 Windows 专有链接节；第 1 代构建期间从清单里整节去掉。
HIDDEN_SECTIONS = ("link-windows-x64", "link-options-windows-x64")
MANIFEST = ROOT / "compiler/project.toml"

# `$if (windows)` 在非 Windows 宿主上恒为假；第 1 代替换成同样恒假的对侧 OS 标记。
WINDOWS_MARKER = re.compile(r"\$if\s*\(\s*windows\s*\)")
SOURCE_ROOTS = ("compiler", "libs")
OTHER_MARKER = {"Linux": "darwin", "Darwin": "linux",
                 # Windows 宿主不做标记改写（0.0.11-windows 种子认识 windows），
                 # 该键仅为查表完整性保留。
                 "Windows": "windows"}

# 与 justfile 的 seed_platform/llvm_host 变量保持一致。
HOST_TABLE = {
    ("Linux", "x86_64"): ("linux-x86_64", "linux-x64"),
    ("Linux", "aarch64"): ("linux-aarch64", "linux-arm64"),
    ("Linux", "arm64"): ("linux-aarch64", "linux-arm64"),
    ("Darwin", "arm64"): ("darwin-aarch64", "darwin-arm64"),
    ("Darwin", "aarch64"): ("darwin-aarch64", "darwin-arm64"),
    # Windows：0.0.11-windows 种子（按 2026-11-03 HEAD 重编）认识 W2 的
    # 变体/标记/链接节，只有测试文件排序需要 staging（见 TEST_RENAME）。
    ("Windows", "AMD64"): ("windows-x86_64", "windows-x64"),
}

# VTEST（2026-11-05）：`.test.yh` 测试文件改名后没有排序前缀，0.0.11 时代的
# 种子按文件名字典序扫描会把它们排到生产文件前（报「未知类型」）。staging
# 把它们临时加回 `zz_` 前缀（字典序最后），gen-2 用 yh1（HEAD 逻辑含
# test-last 排序）构建原样源码，无需该前缀。
TEST_RENAME_GLOB = "*.test.yh"
TEST_RENAME_ROOTS = ("compiler", "libs")
STAGED_TEST_PREFIX = "zz_"


def host_ids() -> tuple[str, str]:
    """返回（LLVM 宿主标识, 种子文件名后缀），与 justfile 的两个变量一一对应。"""
    key = (platform.system(), platform.machine())
    if key not in HOST_TABLE:
        raise SystemExit(f"ci-bootstrap：不支持的宿主 {key[0]}/{key[1]}")
    return HOST_TABLE[key]


def test_rename_pairs() -> list[tuple[Path, Path]]:
    """返回（原路径, staging 路径）：所有 `*.test.yh` 加 `zz_` 排序前缀。"""
    pairs: list[tuple[Path, Path]] = []
    for root in TEST_RENAME_ROOTS:
        for path in sorted((ROOT / root).rglob(TEST_RENAME_GLOB)):
            pairs.append((path, path.with_name(STAGED_TEST_PREFIX + path.name)))
    return pairs


def variant_sources() -> list[Path]:
    """返回所有需要暂时移出的 Windows 平台变体文件。"""
    files: list[Path] = []
    for root in VARIANT_ROOTS:
        for pattern in VARIANT_PATTERNS:
            files.extend(sorted((ROOT / root).rglob(pattern)))
    return files


def marker_sources() -> list[Path]:
    """返回源码里真正出现 `$if (windows)` 的 .yh 文件。"""
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        for path in sorted((ROOT / root).rglob("*.yh")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if WINDOWS_MARKER.search(text):
                files.append(path)
    return files


def strip_sections(text: str) -> str:
    """删掉清单里 HIDDEN_SECTIONS 的整节；其余字节原样保留。"""
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^\[([^\]]+)\]\s*$", lines[index])
        if match and match.group(1) in HIDDEN_SECTIONS:
            index += 1
            while index < len(lines) and not lines[index].lstrip().startswith("["):
                index += 1
            continue
        kept.append(lines[index])
        index += 1
    return "".join(kept)


def backup_originals(state_dir: Path, files: list[Path], manifest_bytes: bytes,
                     renames: list[tuple[Path, Path]]) -> dict[str, str]:
    """把即将改动的文件与清单原文写到 <staged>/orig/，返回恢复用的相对路径清单。

    清单按**字节**备份/恢复：Linux/macOS 的 checkout 是 LF，但本地副本可能带 CRLF，
    文本读写会把行尾规范化，恢复后就不是逐字节原文了。

    renames 的每项（原路径, staging 路径）记两条：原路径 → "file"（内容备份），
    staging 路径 → "staged"（恢复时删除该改名副本）。
    """
    originals = state_dir / "orig"
    shutil.rmtree(originals, ignore_errors=True)
    originals.mkdir(parents=True)
    recorded: dict[str, str] = {}
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        target = originals / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        recorded[relative] = "file"
    for original, staged in renames:
        for path, kind in ((original, "file"), (staged, "staged")):
            relative = path.relative_to(ROOT).as_posix()
            target = originals / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if kind == "file":
                shutil.copyfile(path, target)
            recorded[relative] = kind
    (originals / "project.toml").write_bytes(manifest_bytes)
    recorded["project.toml"] = "manifest"
    (state_dir / "pending.json").write_text(
        json.dumps({"files": recorded}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return recorded


def restore_from_backup(state_dir: Path) -> None:
    """按 <staged>/orig/ 的备份恢复源码与清单（进程被强杀后的下一次启动调用）。"""
    pending = state_dir / "pending.json"
    if not pending.is_file():
        return
    record = json.loads(pending.read_text(encoding="utf-8"))
    originals = state_dir / "orig"
    for relative, kind in record.get("files", {}).items():
        if kind == "staged":
            # 改名产生的临时副本：直接删除，原文按 "file" 条目恢复。
            (ROOT / relative).unlink(missing_ok=True)
            continue
        source = originals / ("project.toml" if kind == "manifest" else relative)
        target = MANIFEST if kind == "manifest" else (ROOT / relative)
        if not source.is_file():
            raise RuntimeError(f"崩溃恢复失败：备份缺失 {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    shutil.rmtree(originals, ignore_errors=True)
    pending.unlink(missing_ok=True)
    print("[ci-bootstrap] 已从上次中断的备份恢复源码与清单", flush=True)


def apply_transform(other_marker: str, backup: dict[str, str],
                    windows_host: bool) -> list[Path]:
    """执行第 1 代源码变换并返回被改动的文件清单。

    非 Windows 宿主：移出 Windows 变体、改写标记、裁剪 windows 链接节
    （0.0.11 的 Linux/macOS 种子不认识 W2）。Windows 宿主：0.0.11-windows
    种子认识 W2，跳过这三类。测试文件改名（test_rename_pairs）对所有宿主
    生效：VTEST 后 `.test.yh` 无排序前缀，0.0.11 按字典序扫描会把它们排到
    生产文件前报「未知类型」。
    """
    renames = test_rename_pairs()
    variants: list[Path] = []
    markers: list[Path] = []
    if not windows_host:
        variants = variant_sources()
        markers = marker_sources()
        for path in variants + markers:
            backup[path.relative_to(ROOT).as_posix()] = "file"
        for path in variants:
            path.unlink()
        for path in markers:
            text = path.read_text(encoding="utf-8")
            path.write_text(WINDOWS_MARKER.sub(f"$if ({other_marker})", text),
                            encoding="utf-8")
        MANIFEST.write_text(strip_sections(MANIFEST.read_text(encoding="utf-8")),
                            encoding="utf-8")
    for original, staged in renames:
        backup[original.relative_to(ROOT).as_posix()] = "file"
        backup[staged.relative_to(ROOT).as_posix()] = "staged"
        shutil.move(str(original), str(staged))
    print(f"[ci-bootstrap] 第 1 代源码变换：移出 {len(variants)} 个 Windows 变体、"
          f"改写 {len(markers)} 个文件里的 $if (windows) → $if ({other_marker})、"
          f"去掉 {len(HIDDEN_SECTIONS)} 个链接节、"
          f"改名 {len(renames)} 个测试文件（zz_ 前缀）", flush=True)
    return variants + markers + [staged for _, staged in renames]


def run_stage(label: str, compiler: Path, output: Path, llvm_host: str) -> None:
    """用指定编译器冷编 compiler/；输出进度与耗时，失败时抛 RuntimeError。"""
    if not compiler.is_file():
        raise RuntimeError(f"{label}：找不到编译器 {compiler}")
    shutil.rmtree(ROOT / "compiler/.build", ignore_errors=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["YH_BUILD_CACHE"] = ""
    command = [
        sys.executable, str(SEED_BUILD),
        "--compiler", str(compiler),
        "--project", str(ROOT / "compiler"),
        "--output", str(output),
        "--llvm-host", llvm_host,
        "--llvm-mode", "auto",
    ]
    print(f"[ci-bootstrap] {label}：{compiler.name} → {output}", flush=True)
    started = time.time()
    result = subprocess.run(command, cwd=str(ROOT), env=environment)
    elapsed = time.time() - started
    if result.returncode != 0:
        raise RuntimeError(f"{label} 失败（退出码 {result.returncode}，{elapsed:.1f} s）")
    if not output.is_file():
        raise RuntimeError(f"{label} 结束但产物不存在：{output}")
    print(f"[ci-bootstrap] {label} 完成：{elapsed:.1f} s", flush=True)


def bootstrap(seed: Path, output: Path, staged: Path, keep_staged: bool) -> int:
    """两代自举：先编出认识 W2 标记的 yh1，再用它全量冷编 HEAD。"""
    llvm_host, suffix = host_ids()
    system = platform.system()
    windows_host = system == "Windows"
    other_marker = OTHER_MARKER[system]
    staged.mkdir(parents=True, exist_ok=True)
    restore_from_backup(staged)  # 上次进程被强杀时先把源码恢复干净
    original_manifest = MANIFEST.read_bytes()
    renames = test_rename_pairs()
    backup = backup_originals(staged, variant_sources() + marker_sources(),
                              original_manifest, renames)
    staged_yh = staged / "yh1"
    try:
        apply_transform(other_marker, backup, windows_host)
        run_stage("第 1 代（等价形态冷编）", seed, staged_yh, llvm_host)
    finally:
        # 无论第 1 代成败，都立刻按盘上备份恢复，后续步骤看到的一定是原始工程。
        restore_from_backup(staged)
    run_stage("第 2 代（全量 HEAD 冷编）", staged_yh, output, llvm_host)
    # verify-seed（selfhost_snapshot_gate.py --verify-seed）要求种子旁有 <种子>.sha256；
    # 这里按与 fetch-release-seed.py 相同的格式补写，供自举门 `SEED=…/yh` 使用。
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (output.parent / f"{output.name}.sha256").write_text(
        f"{digest}  {output.name}\n", encoding="utf-8")
    print(f"[ci-bootstrap] 已写 {output.name}.sha256（{digest[:16]}…）", flush=True)
    # 自举门还要一份**带平台名**的种子：justfile 的 llvm_host 与
    # tests/selfhost/native-selfhost.py 的 llvm_shim_for_seed() 都按种子文件名
    # 推断平台，根目录 `yh` 不含平台标记会退化成「无闭包参数」并链接失败。
    # 写成 bin/<平台种子名> 后，后续 `just SEED="$PWD/bin/yh-<平台>-<架构>"` 可用；
    # CI 的 bin/ 里原本是 Release 种子，这里被本次 HEAD 产物覆盖是预期行为。
    seed_out = ROOT / "bin" / f"yh-{suffix}"
    seed_out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(output, seed_out)
    (ROOT / "bin" / f"yh-{suffix}.sha256").write_text(
        f"{digest}  {seed_out.name}\n", encoding="utf-8")
    print(f"[ci-bootstrap] 已写平台种子：{seed_out}", flush=True)
    if not keep_staged:
        shutil.rmtree(staged, ignore_errors=True)
    print(f"[ci-bootstrap] 完成：{output}\n"
          f"[ci-bootstrap] 后续自举门请用 SEED={output.resolve()} "
          f"just SKIP_CORPUS=1 selfhost-native", flush=True)
    return 0


def main(argv: list[str]) -> int:
    """解析参数并执行一次过渡期自举。"""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="执行两代自举，产出根目录 yh")
    run.add_argument("--seed", type=Path,
                     help="Release 种子路径；缺省按宿主平台取 bin/yh-<平台>-<架构>")
    run.add_argument("--output", type=Path,
                    default=ROOT / ("yh.exe" if platform.system() == "Windows" else "yh"))
    run.add_argument("--staged", type=Path, default=ROOT / "tmp/ci-bootstrap")
    run.add_argument("--keep-staged", action="store_true",
                     help="保留第 1 代产物目录（排查用）")
    args = parser.parse_args(argv)
    _llvm_host, suffix = host_ids()
    seed = args.seed or ROOT / f"bin/yh-{suffix}"
    return bootstrap(seed, args.output, args.staged, args.keep_staged)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"FAIL ci-bootstrap：{error}", file=sys.stderr)
        raise SystemExit(1)
