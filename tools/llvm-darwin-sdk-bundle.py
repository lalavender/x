#!/usr/bin/env python3
"""生成/校验随编译器分发的 Darwin SDK 链接 stub（compiler/darwin-sdk）。

只复制 Mach-O 链接所需的 TAPI stub 与最小 SDKSettings.json，不复制完整
Apple SDK（头文件、libc++、frameworks 仍属遗留边界，见
docs/03-design/yh-Darwin交叉编译遗留边界.md）。

用法：
    python3 tools/llvm-darwin-sdk-bundle.py --check
    python3 tools/llvm-darwin-sdk-bundle.py --from-zig <zig-libc/darwin>
    python3 tools/llvm-darwin-sdk-bundle.py --from-sdk "$(xcrun --show-sdk-path)"
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "compiler/darwin-sdk"
KNOWN_UNSUPPORTED = "arm64e.x1"


def digest(path: Path) -> str:
    """返回文件内容的 SHA-256。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(output: Path, version: str, source: str):
    """按 output 下实际文件写 manifest（排序保证确定性）。"""
    files = {}
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files[str(path.relative_to(output))] = digest(path)
    manifest = {
        "name": "yh-darwin-sdk",
        "sdk_version": version,
        "min_os": "14.0.0",
        "source": source,
        "files": files,
        "note": "仅用于 Mach-O 链接期解析 libSystem 符号/install name/reexport；"
                "不是完整 SDK，不含头文件、libc++、frameworks。",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def check(output: Path) -> int:
    """校验 manifest 中列出的文件/摘要，并报告版本。"""
    manifest_path = output / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"缺少 manifest：{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require = [
        ("usr/lib/libSystem.tbd", output / "usr/lib/libSystem.tbd"),
        ("SDKSettings.json", output / "SDKSettings.json"),
    ]
    for rel, path in require:
        if not path.is_file():
            raise RuntimeError(f"缺少 {rel}")
        if manifest.get("files", {}).get(rel) != digest(path):
            raise RuntimeError(f"摘要不匹配：{rel}")
    settings = json.loads((output / "SDKSettings.json").read_text(encoding="utf-8"))
    if settings.get("Version") != manifest.get("sdk_version"):
        raise RuntimeError("SDKSettings.json 与 manifest 的 SDK 版本不一致")
    print(f"Darwin SDK bundle 校验通过：version={manifest['sdk_version']}，"
          f"{len(manifest.get('files', {}))} 个文件，output={output.relative_to(ROOT)}")
    return 0


def prepare_output(output: Path):
    """清空输出目录（保留 README），准备写入 stub。"""
    output.mkdir(parents=True, exist_ok=True)
    for name in ("usr", "SDKSettings.json", "manifest.json"):
        target = output / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def from_zig(source: Path, output: Path, version: str):
    """从 Zig 的 libc/darwin 复制聚合 libSystem.tbd。"""
    tbd = source / "libSystem.tbd"
    if not tbd.is_file():
        raise RuntimeError(f"Zig 目录缺少 libSystem.tbd：{source}")
    prepare_output(output)
    (output / "usr/lib").mkdir(parents=True)
    shutil.copy2(tbd, output / "usr/lib/libSystem.tbd")
    (output / "SDKSettings.json").write_text(
        json.dumps({"Version": version, "MinimalDisplayName": version}) + "\n",
        encoding="utf-8")
    manifest = write_manifest(
        output, version, f"Zig libc/darwin/libSystem.tbd（Apple macOS SDK {version} TAPI 聚合）")
    print(f"已生成 bundle：version={manifest['sdk_version']}，"
          f"libSystem.tbd={digest(output / 'usr/lib/libSystem.tbd')[:12]}…")


def from_sdk(sdk: Path, output: Path, version: str, allow_unsupported: bool):
    """从已安装 SDK 复制 libSystem stub 与系统 reexport 闭包。

    Apple SDK 27 的 `arm64e.x1` 目标标签不被固定 LLVM 21.1.8 lld 支持；
    默认拒绝，避免生成“能打包但不能链接”的 bundle。
    """
    lib = sdk / "usr/lib/libSystem.tbd"
    system = sdk / "usr/lib/system"
    if not lib.is_file() or not system.is_dir():
        raise RuntimeError(f"不是有效的 macOS SDK：{sdk}")
    content = lib.read_bytes()
    if KNOWN_UNSUPPORTED.encode() in content and not allow_unsupported:
        raise RuntimeError(
            f"SDK 含固定 lld 21.1.8 不支持的 {KNOWN_UNSUPPORTED} 标签；"
            "请改用已验证 SDK（如 26.5）或显式 --allow-unsupported")
    prepare_output(output)
    (output / "usr/lib/system").mkdir(parents=True)
    shutil.copy2(lib, output / "usr/lib/libSystem.tbd")
    copied = 0
    for tbd in sorted(system.glob("*.tbd")):
        shutil.copy2(tbd, output / "usr/lib/system" / tbd.name)
        copied += 1
    (output / "SDKSettings.json").write_text(
        json.dumps({"Version": version, "MinimalDisplayName": version}) + "\n",
        encoding="utf-8")
    manifest = write_manifest(output, version, f"macOS SDK {version} 的 libSystem TAPI 子集")
    print(f"已生成 bundle：version={manifest['sdk_version']}，"
          f"libSystem + {copied} 个系统 stub")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--from-zig", type=Path,
                        help="Zig 的 libc/darwin 目录（含聚合 libSystem.tbd）")
    parser.add_argument("--from-sdk", type=Path,
                        help="已安装的 macOS SDK 根（含 usr/lib/libSystem.tbd）")
    parser.add_argument("--version", help="SDK 版本（缺省从 SDKSettings 或 26.4）")
    parser.add_argument("--allow-unsupported", action="store_true",
                        help="允许含 arm64e.x1 等未验证标签的 SDK")
    parser.add_argument("--check", action="store_true", help="只校验现有 bundle")
    args = parser.parse_args()
    try:
        if args.check or (args.from_zig is None and args.from_sdk is None):
            return check(args.output)
        if args.from_zig and args.from_sdk:
            raise RuntimeError("--from-zig 与 --from-sdk 只能二选一")
        version = args.version
        if args.from_zig:
            if not version:
                settings = args.from_zig / "SDKSettings.json"
                if settings.is_file():
                    version = json.loads(settings.read_text(encoding="utf-8")).get(
                        "MinimalDisplayName")
            from_zig(args.from_zig, args.output, version or "26.4")
        else:
            if not version:
                settings = args.from_sdk / "SDKSettings.json"
                if settings.is_file():
                    version = json.loads(settings.read_text(encoding="utf-8")).get("Version")
                if not version:
                    raise RuntimeError("请用 --version 指定 SDK 版本")
            from_sdk(args.from_sdk, args.output, version, args.allow_unsupported)
        return check(args.output)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"llvm-darwin-sdk-bundle: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
