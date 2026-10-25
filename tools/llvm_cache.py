#!/usr/bin/env python3
"""解析 LLVM 闭包缓存根目录（YH_LLVM_CACHE 自动定位）。

解析顺序：
  1. 显式 `YH_LLVM_CACHE`（CI / 容器 / 换机器）；
  2. 当前仓库的 `tmp/llvm-migration`；
  3. 同一 Git 仓库的主 worktree 的 `tmp/llvm-migration`
     （`git rev-parse --git-common-dir` 的父目录，新 worktree 自动复用）；
  4. 兜底返回当前仓库的 `tmp/llvm-migration`（尚未准备，由 just llvm-host 创建）。

用法：
    python3 tools/llvm-cache.py          # 打印缓存根
    python3 tools/llvm-cache.py --check  # 存在则 0，否则 1
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "tmp/llvm-migration"


def _main_worktree_cache(repo: Path) -> Path | None:
    """主 worktree 的缓存目录；不是 git worktree 或没有缓存时返回 None。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = (repo / common).resolve()
    candidate = common.parent / "tmp/llvm-migration"
    return candidate if candidate.is_dir() else None


def cache_root() -> Path:
    env = os.environ.get("YH_LLVM_CACHE")
    if env:
        return Path(env).expanduser().resolve()
    if DEFAULT.is_dir():
        return DEFAULT.resolve()
    shared = _main_worktree_cache(ROOT)
    if shared is not None:
        return shared.resolve()
    return DEFAULT.resolve()


if __name__ == "__main__":
    root = cache_root()
    if "--check" in sys.argv:
        sys.exit(0 if root.is_dir() else 1)
    print(root)
