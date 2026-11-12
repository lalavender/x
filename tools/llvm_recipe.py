#!/usr/bin/env python3
"""固定 LLVM 闭包的「配方摘要」，供宿主/SDK 两个构建器共用。

为什么不用构建器脚本自身的文件摘要：`tools/llvm-darwin-sdk.py` 的注释、日志措辞、
错误提示改动都会让 30 分钟的 LLVM 重编失效，而产物其实没变。真正决定产物的是
`vendor/llvm/sdk.lock.json` 里的源码包摘要与 darwin_build 规格，因此身份就取这两项。
"""

import hashlib
import json
from pathlib import Path

from llvm_cache import cache_root

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

    输入是真正决定产物的东西：桥/lld 源码摘要、最低部署版本与 SDK 配方。
    刻意不含 `tools/llvm-darwin-host.py` 自身——脚本的注释与错误措辞改动不应
    触发 30 分钟的 LLVM 闭包重建；也不含 `vendor/llvm/sdk.lock.json` 的整文件
    摘要——同一份锁文件还钉着 Windows 闭包，那边加段或重排格式与 Darwin 桥
    无关（产物输入已由 `sdk_recipe` 覆盖）。
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
        "min_os": min_os,
        "sdk_recipe": sdk_recipe_digest(),
    }
    return _hash.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def closure_stamp_path(host: str) -> Path:
    """“已校验”标记的位置：缓存根下的 .sealed-<host>.json（项目外）。"""
    return cache_root() / f".sealed-{host}.json"


def closure_stamp_key(host: str) -> str:
    """标记的键：SDK 配方 + 宿主配方 + 缓存根。任一项变了就重新校验。"""
    payload = {"sdk": sdk_recipe_digest(), "host": host_recipe_digest(),
               "root": str(cache_root())}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _stat_fingerprint(path: Path) -> list[int]:
    """闭包文件的轻量指纹：只取 size 与 mtime_ns，不读 3.7 GB 归档内容。"""
    info = path.stat()
    return [info.st_size, info.st_mtime_ns]


def closure_stamp_ok(host: str, record_path: Path,
                     extra: list[Path]) -> dict | None:
    """第一步检测：命中标记且记录/关键文件都在 → 直接返回记录，不再校验摘要。

    这是每次构建只做一次的最小检查（读一个几百字节的 JSON + stat 几个文件），
    通过后不再改动缓存里的任何内容。标记同时记录闭包归档的 (size, mtime_ns)：
    归档原地重建（路径不变、内容变了）会让标记失效，回落到全量摘要校验；
    旧格式标记没有 guarded 字段，同样视为失效。
    """
    try:
        stamp = json.loads(closure_stamp_path(host).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if stamp.get("key") != closure_stamp_key(host):
        return None
    if not record_path.is_file():
        return None
    if hashlib.sha256(record_path.read_bytes()).hexdigest() != stamp.get("record_sha256"):
        return None
    if any(not path.exists() for path in extra):
        return None
    guarded = stamp.get("guarded")
    if not isinstance(guarded, dict):
        return None
    for name, expected in guarded.items():
        try:
            if _stat_fingerprint(Path(name)) != expected:
                return None
        except OSError:
            return None
    try:
        return json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def closure_stamp_write(host: str, record_path: Path,
                        guarded: list[Path] = ()) -> None:
    """完整校验/重建成功后封装：写标记（原子替换），之后走第一步快路径。

    guarded 是闭包里会被原地重建的归档/产物；调用方必须传入实际路径，
    写入前逐个 stat。
    """
    data = {"host": host, "key": closure_stamp_key(host),
            "record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
            "guarded": {str(path): _stat_fingerprint(path) for path in guarded}}
    path = closure_stamp_path(host)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(path)
