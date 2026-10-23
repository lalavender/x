#!/usr/bin/env python3
"""把三端构建产物发布到 GitHub Release。

由 Gitea Actions 的发布 workflow（.gitea/workflows/release.yml）调用：

  python3 tools/publish-release.py --repo lalavender/x --tag 0.0.8 \
      --dist dist --notes docs/01-finished/release-0.0.8.md

约定：
  - 资产名：yh-<tag>-<platform>.tar.gz + .sha256；
  - 三端资产缺一即失败（不允许发布半套 Release）；
  - tag 含 `-rc.` 时发布 prerelease；
  - Release 已存在时先删除同名资产再上传，保证可重跑。

环境变量 GITHUB_TOKEN 必填（repo 权限）。
"""

import argparse
import http.client
import json
import os
import time
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.github.com"
UPLOAD_API = "https://uploads.github.com"
PLATFORMS = ("linux-arm64", "linux-x86_64", "darwin-arm64")


class PublishError(RuntimeError):
    """发布失败；调用方应让构建失败。"""


def request(method, url, token, data=None, content_type=None):
    """带鉴权地请求 GitHub API，返回 (状态码, 响应字节)。"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "yh-publish",
    }
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", "replace")
            # 5xx/429 与传输中断可重试；4xx 立即失败（鉴权/参数问题）。
            if error.code < 500 and error.code != 429:
                raise PublishError(f"GitHub API {error.code}: {method} {url}: {body}") from error
            last = PublishError(f"GitHub API {error.code}: {method} {url}: {body}")
        except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
            last = PublishError(f"GitHub API 连接失败: {method} {url}: {error}")
        if attempt < 2:
            time.sleep(2 * (attempt + 1))
    raise last


def find_release(repo, token, tag):
    """按 tag 查 Release；不存在返回 None。"""
    url = f"{API}/repos/{repo}/releases/tags/{urllib.parse.quote(tag, safe='')}"
    try:
        _status, body = request("GET", url, token)
    except PublishError as error:
        if " 404:" in str(error):
            return None
        raise
    return json.loads(body)


def delete_asset(repo, token, asset):
    """删除同名旧资产，让重跑幂等。"""
    request("DELETE", asset["url"], token)


def upload_asset(repo, token, release_id, path):
    """上传单个资产到 uploads.github.com；已存在视为成功（重跑幂等）。"""
    url = (f"{UPLOAD_API}/repos/{repo}/releases/{release_id}/assets"
           f"?name={urllib.parse.quote(path.name, safe='')}")
    try:
        request("POST", url, token, data=path.read_bytes(),
                content_type="application/octet-stream")
    except PublishError as error:
        # 上一次尝试可能已创建、只是响应中断；同名资产在 GitHub 上是 422。
        if "already_exists" in str(error) or " 422:" in str(error):
            print(f"资产已存在，跳过：{path.name}")
            return
        raise


def collect_assets(dist, tag):
    """校验三端 tar.gz 与 .sha256 齐全，返回待上传文件列表。"""
    safe_tag = tag.replace("/", "_")
    files = []
    missing = []
    for platform in PLATFORMS:
        name = f"yh-{safe_tag}-{platform}"
        archive = dist / f"{name}.tar.gz"
        checksum = dist / f"{name}.sha256"
        for path in (archive, checksum):
            if not path.is_file() or path.stat().st_size == 0:
                missing.append(str(path))
            else:
                files.append(path)
    if missing:
        raise PublishError("发布资产不完整，缺少：" + ", ".join(missing))
    return files


def read_notes(path):
    """优先用仓库里的 release 说明；缺失时用统一兜底文案。"""
    if path and path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return "自举构建：Linux/AArch64、Linux/x86_64、Darwin/ARM64"


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--tag", required=True)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--notes", type=Path)
    parser.add_argument("--prerelease", action="store_true",
                        help="强制 prerelease；缺省按 tag 是否含 -rc. 自动判断")
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("FAIL 缺少 GITHUB_TOKEN", file=sys.stderr)
        return 1
    if not args.repo:
        print("FAIL 缺少 GITHUB_REPOSITORY", file=sys.stderr)
        return 1

    try:
        files = collect_assets(args.dist, args.tag)
        prerelease = args.prerelease or "-rc." in args.tag
        release = find_release(args.repo, token, args.tag)
        if release is None:
            payload = {
                "tag_name": args.tag,
                "name": args.tag,
                "body": read_notes(args.notes),
                "draft": False,
                "prerelease": prerelease,
            }
            _status, body = request(
                "POST", f"{API}/repos/{args.repo}/releases", token,
                data=json.dumps(payload).encode("utf-8"),
                content_type="application/json")
            release = json.loads(body)
            print(f"创建 Release {args.tag} id={release['id']} prerelease={prerelease}")
        else:
            print(f"Release {args.tag} 已存在，更新资产")

        existing = {asset["name"]: asset for asset in release.get("assets", [])}
        for path in files:
            if path.name in existing:
                delete_asset(args.repo, token, existing[path.name])
            upload_asset(args.repo, token, release["id"], path)
            print(f"上传 {path.name}")

        # 上传后再核对一次远端大小：防止打包目录被旧产物覆盖（0.0.8 首版发布
        # 就出现过资产被换成上一代二进制，种子不支持无分号语法导致 CI 全红）。
        _status, body = request(
            "GET", f"{API}/repos/{args.repo}/releases/{release['id']}", token)
        remote = {a["name"]: a["size"] for a in json.loads(body).get("assets", [])}
        for path in files:
            local_size = path.stat().st_size
            if remote.get(path.name) != local_size:
                raise PublishError(
                    f"上传后大小不一致：{path.name} 远端={remote.get(path.name)} "
                    f"本地={local_size}")
        print("校验：远端资产大小与本地一致")

        print(f"完成：https://github.com/{args.repo}/releases/tag/{args.tag}")
        return 0
    except PublishError as error:
        print(f"FAIL 发布 Release：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
