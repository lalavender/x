#!/usr/bin/env python3
"""从最近的 GitHub Release 下载平台种子。

CI 与 Release 的共同约定：当前提交通用**上一版已发布 Release** 的
`yh-<tag>-<platform>.tar.gz` 作为种子，而不是仓库里的固定 bin/ 种子。
这样每次提交都在验证「上一版编译器能否编出当前源码」。

选择规则：
  - 忽略 draft、`seed-*`（种子里程碑）与 `--exclude-tag`（rc 仍是种子来源）
    （当前 tag 自身，避免用当前版本测试当前版本）；
  - 从新到旧找第一个带目标平台资产的 Release；
  - 找不到且目标种子已存在时退回该文件（首次发布/离线开发），否则失败。

产物：
  bin/yh-linux-arm64       / bin/yh-linux-x64 / bin/yh-darwin-arm64
以及相邻的 `<seed>.sha256`，格式与 tools/selfhost_snapshot_gate.py 一致。
"""

import argparse
import hashlib
import http.client
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
PLATFORMS = {
    "linux-arm64": ("yh-linux-arm64", "bin/yh-linux-arm64"),
    "linux-x86_64": ("yh-linux-x64", "bin/yh-linux-x64"),
    "darwin-arm64": ("yh-darwin-arm64", "bin/yh-darwin-arm64"),
    "windows-x64": ("yh-windows-x64", "bin/yh-windows-x64"),
}


class FetchError(RuntimeError):
    """无法取得上一版种子；调用方应显式失败而不是静默回退。"""


def api_request(url, token, accept="application/vnd.github+json", attempts=3):
    """执行 GitHub API 请求，返回响应对象。

    CI 上到 api.github.com 的连接偶发 SSL/EOF 中断；5xx/429 与传输层错误按
    退避有限重试，4xx 立即失败（鉴权/路径问题重试无意义）。
    """
    headers = {"Accept": accept, "User-Agent": "yh-ci-seed-fetcher"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    last = None
    for attempt in range(attempts):
        try:
            return urllib.request.urlopen(request, timeout=180)
        except urllib.error.HTTPError as error:
            if error.code < 500 and error.code != 429:
                raise FetchError(f"GitHub API {error.code}: {url}") from error
            last = error
        except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
            last = error
        if attempt + 1 < attempts:
            time.sleep(2 * (attempt + 1))
    raise FetchError(f"GitHub API 连接失败（重试 {attempts} 次）：{url}: {last}")


def read_releases(repo, token):
    """读取最近的 Release，并显式按发布时间倒序；不依赖 API 返回顺序。"""
    url = f"{API}/repos/{repo}/releases?per_page=30"
    with api_request(url, token) as response:
        releases = json.load(response)
    return sorted(releases, key=lambda release: release.get("published_at")
                  or release.get("created_at") or "", reverse=True)


def find_asset(repo, token, platform, exclude_tag):
    """返回 (tag, asset) 或 None；只接受带目标平台 tar.gz 的正式 Release。"""
    asset_name = f"yh-{{tag}}-{platform}.tar.gz"
    for release in read_releases(repo, token):
        tag = release.get("tag_name") or ""
        # rc 也是种子来源：rc.N 用 rc.N-1、正式版用该版最后一个 rc（见 AGENTS
        # 版本与发布）。只跳过 draft 与 seed-* 里程碑。
        if release.get("draft"):
            continue
        if not tag or tag == exclude_tag or tag.startswith("seed-"):
            continue
        expected = asset_name.format(tag=tag)
        for asset in release.get("assets", []):
            if asset.get("name") == expected:
                return tag, asset
    return None


def download_asset_once(asset, token, destination):
    """下载一次资产并核对 API 给出的字节数，截断时按可重试错误处理。"""
    total = 0
    with api_request(asset["url"], token, "application/octet-stream") as response:
        with destination.open("wb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
                total += len(block)
    expected = int(asset.get("size", -1))
    if expected >= 0 and total != expected:
        raise FetchError(f"Release 资产下载不完整：{total}/{expected} 字节")


def download_asset(asset, token, destination):
    """下载资产；网络截断/连接中断时有限重试，避免 CI 偶发失败。"""
    last = None
    for attempt in range(3):
        try:
            download_asset_once(asset, token, destination)
            return
        except (FetchError, OSError, http.client.IncompleteRead) as error:
            last = error
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise FetchError(f"Release 资产下载失败（重试 3 次）：{last}")


def extract_yh(archive, destination):
    """从 tar.gz 中提取唯一顶层 yh，校验成员路径并设置 0755。"""
    with tarfile.open(archive, "r:gz") as tar:
        members = [member for member in tar.getmembers()
                   if member.isfile() and Path(member.name).name == "yh"]
        if len(members) != 1:
            raise FetchError(f"Release 资产中 yh 数量异常：{len(members)}")
        member = members[0]
        if Path(member.name).is_absolute() or ".." in Path(member.name).parts:
            raise FetchError(f"Release 资产路径不安全：{member.name}")
        source = tar.extractfile(member)
        if source is None:
            raise FetchError("Release 资产中的 yh 不可读")
        destination.write_bytes(source.read())
    destination.chmod(0o755)


def write_hash(seed):
    """写入 verify_seed 需要的相邻 SHA-256 文件。"""
    digest = hashlib.sha256(seed.read_bytes()).hexdigest()
    Path(str(seed) + ".sha256").write_text(f"{digest}  {seed.name}\n",
                                           encoding="utf-8")
    return digest


def install_seed(destination, tag, asset, token):
    """下载、解压、校验并发布目标种子。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yh-seed-") as temp:
        archive = Path(temp) / "seed.tar.gz"
        download_asset(asset, token, archive)
        extract_yh(archive, destination)
    digest = write_hash(destination)
    print(f"Release 种子：{tag} -> {destination} sha256={digest}")


def infer_repo_from_git() -> str:
    """从 `git remote get-url origin` 推断 owner/repo；失败返回空串。

    本地开发常常没有 GITHUB_REPOSITORY（那是 Actions 注入的），但仓库一定有
    origin 远端；这样 `just fetch-seed` 在开发者机器上无需任何环境变量。
    """
    try:
        result = subprocess.run(["git", "remote", "get-url", "origin"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    url = result.stdout.strip()
    if not url:
        return ""
    match = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if not match:
        return ""
    return f"{match.group(1)}/{match.group(2)}"


def main(argv):
    """解析参数并执行一次种子获取。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=tuple(PLATFORMS), required=True)
    parser.add_argument("--dest", type=Path,
                        help="目标种子路径（缺省按平台写入 bin/）")
    parser.add_argument("--exclude-tag", default="",
                        help="排除当前 tag；空字符串表示使用最新 Release")
    parser.add_argument("--fallback", type=Path,
                        help="找不到 Release 时使用的已有种子")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--token", default=os.environ.get("GH_TOKEN")
                        or os.environ.get("GITHUB_TOKEN") or "")
    args = parser.parse_args(argv)

    _asset_prefix, default_dest = PLATFORMS[args.platform]
    destination = args.dest or Path(default_dest)
    fallback = args.fallback or (destination if destination.is_file() else None)
    if fallback is not None:
        # 未执行 git lfs pull 时 bin 里是 LFS 指针，不是可执行种子；不能把它
        # 当成 fallback 发布，否则 just 会在 exec 阶段报 Exec format error。
        with fallback.open("rb") as source:
            if source.read(64).startswith(b"version https://git-lfs.github.com/spec/v1"):
                fallback = None
    try:
        if not args.repo:
            args.repo = infer_repo_from_git()
        if not args.repo:
            raise FetchError("缺少 GITHUB_REPOSITORY（且无法从 git remote 推断）")
        found = find_asset(args.repo, args.token, args.platform, args.exclude_tag)
        if found is None:
            raise FetchError(
                f"没有找到带 {args.platform} 资产的已发布 Release"
                f"（exclude={args.exclude_tag or '<none>'}）")
        tag, asset = found
        install_seed(destination, tag, asset, args.token)
        return 0
    except FetchError as error:
        if fallback is None:
            print(f"FAIL 获取上一版 Release 种子：{error}", file=sys.stderr)
            return 1
        destination.write_bytes(fallback.read_bytes())
        destination.chmod(0o755)
        digest = write_hash(destination)
        print(f"警告：{error}；退回已有种子 {fallback} sha256={digest}",
              file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
