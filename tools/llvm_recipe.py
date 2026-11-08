#!/usr/bin/env python3
"""固定 LLVM 闭包的「配方摘要」，供宿主/SDK 两个构建器共用。

为什么不用构建器脚本自身的文件摘要：`tools/llvm-darwin-sdk.py` 的注释、日志措辞、
错误提示改动都会让 30 分钟的 LLVM 重编失效，而产物其实没变。真正决定产物的是
`vendor/llvm/sdk.lock.json` 里的源码包摘要与 darwin_build 规格，因此身份就取这两项。
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "vendor/llvm/sdk.lock.json"


def sdk_recipe_digest() -> str:
    """返回固定 Darwin SDK 的配方摘要（源码包 sha256 + darwin_build 规格）。"""
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    source = lock.get("darwin_source", {}) or {}
    build = lock.get("darwin_build", {}) or {}
    payload = json.dumps({"source_sha256": source.get("sha256", ""), "build": build},
                         sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def host_recipe_digest() -> str:
    """返回 Darwin 宿主闭包的配方摘要。

    输入是真正决定产物的东西：桥/lld 源码摘要、最低部署版本、锁文件摘要。
    刻意不含 `tools/llvm-darwin-host.py` 自身——脚本的注释与错误措辞改动不应
    触发 30 分钟的 LLVM 闭包重建。
    """
    import hashlib as _hash

    def digest(path: Path) -> str:
        return _hash.sha256(path.read_bytes()).hexdigest()

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    min_os = (lock.get("darwin_build", {}) or {}).get("deployment_target", "")
    payload = {
        "bridge": digest(ROOT / "compiler/llvm/bridge.c"),
        "bridge_header": digest(ROOT / "compiler/llvm/bridge.h"),
        "lld_bridge": digest(ROOT / "compiler/llvm/lld_bridge.cpp"),
        "manifest": digest(LOCK),
        "min_os": min_os,
        "sdk_recipe": sdk_recipe_digest(),
    }
    return _hash.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
