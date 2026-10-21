#!/usr/bin/env python3
"""本机 push 后触发 Jenkins（不依赖 GitHub webhook）。

组成：
  - pre-push 钩子把本次 push 的 ref 交给本脚本，由后台子进程等远端更新后
    调 Jenkins API；
  - Jenkins 侧 yh-ci / yh-release 两个 job 分别接收 BRANCH / TAG 参数；
  - 配置从 ~/.config/yh-jenkins/env 读取（setup.py 生成，0600）。

用法：
  python3 tools/jenkins/trigger.py install-hook
  python3 tools/jenkins/trigger.py trigger --branch llvm
  python3 tools/jenkins/trigger.py trigger --tag 0.0.8-rc.1
  python3 tools/jenkins/trigger.py wait-and-trigger --remote origin --refs-file /tmp/refs
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TRACKED_BRANCHES = {"arm64", "llvm", "main"}
VERSION_BRANCH = re.compile(r"^\d+\.\d+\.\d+-(rc|release)$")
VERSION_TAG = re.compile(r"^\d+\.\d+\.\d+(-rc\.\d+)?$")
HOOK_MARKER = "yh-jenkins-trigger"
DEFAULT_ENV = Path.home() / ".config" / "yh-jenkins" / "env"


class TriggerError(RuntimeError):
    """触发失败；调用方应显式报错而不是静默。"""


def load_config():
    """读取配置：先文件后环境变量，环境变量优先。"""
    path = Path(os.environ.get("YH_JENKINS_ENV") or DEFAULT_ENV)
    values = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("JENKINS_URL", "JENKINS_USER", "JENKINS_TOKEN",
                "JENKINS_CI_JOB", "JENKINS_RELEASE_JOB"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    if not values.get("JENKINS_URL") or not values.get("JENKINS_TOKEN"):
        raise TriggerError(
            f"缺少 Jenkins 配置：{path}（先运行 tools/jenkins/setup.py）")
    values["JENKINS_URL"] = values["JENKINS_URL"].rstrip("/")
    values.setdefault("JENKINS_USER", "jenkins")
    values.setdefault("JENKINS_CI_JOB", "yh-ci")
    values.setdefault("JENKINS_RELEASE_JOB", "yh-release")
    return values


def auth_header(user, token):
    """Jenkins API token 用 Basic 认证。"""
    raw = f"{user}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def get_crumb(config):
    """取 CSRF crumb；关闭 CSRF 的实例返回 None。"""
    url = f"{config['JENKINS_URL']}/crumbIssuer/api/json"
    req = urllib.request.Request(url)
    req.add_header("Authorization", auth_header(config["JENKINS_USER"], config["JENKINS_TOKEN"]))
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.load(response)
        return data.get("crumbRequestField"), data.get("crumb")
    except urllib.error.HTTPError as error:
        if error.code in (403, 404):
            return None
        raise TriggerError(f"取 CSRF crumb 失败：HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise TriggerError(f"连接 Jenkins 失败：{error}") from error


def post_build(config, job, params):
    """带参数触发一个 job。"""
    crumb = get_crumb(config)
    job_path = urllib.parse.quote(job, safe="")
    query = urllib.parse.urlencode(params)
    url = f"{config['JENKINS_URL']}/job/{job_path}/buildWithParameters?{query}"
    req = urllib.request.Request(url, data=b"", method="POST")
    req.add_header("Authorization", auth_header(config["JENKINS_USER"], config["JENKINS_TOKEN"]))
    if crumb:
        req.add_header(crumb[0], crumb[1])
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            location = response.headers.get("Location", "")
        print(f"已触发 {job} {params} {location}")
        return True
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        raise TriggerError(f"触发 {job} 失败：HTTP {error.code} {body}") from error
    except urllib.error.URLError as error:
        raise TriggerError(f"触发 {job} 失败：{error}") from error


def trigger_ref(config, ref):
    """按 ref 选择 job；不关心的分支/tag 静默跳过。"""
    if ref.startswith("refs/heads/"):
        branch = ref[len("refs/heads/"):]
        if branch not in TRACKED_BRANCHES and not VERSION_BRANCH.match(branch):
            print(f"跳过分支 {branch}（只构建 arm64/llvm/main 与 <ver>-rc/<ver>-release）")
            return False
        return post_build(config, config["JENKINS_CI_JOB"], {"BRANCH": branch})
    if ref.startswith("refs/tags/"):
        tag = ref[len("refs/tags/"):]
        if not VERSION_TAG.match(tag):
            print(f"跳过 tag {tag}（只发布 x.y.z 与 x.y.z-rc.N）")
            return False
        return post_build(config, config["JENKINS_RELEASE_JOB"], {"TAG": tag})
    print(f"跳过 ref {ref}")
    return False


def read_refs(path):
    """解析 git pre-push 的 stdin：local-ref local-sha remote-ref remote-sha。"""
    refs = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, remote_ref, _remote_sha = parts
        if set(local_sha) == {"0"}:
            continue  # 删除远端 ref，不触发
        refs.append((remote_ref, local_sha))
    return refs


def wait_remote(remote, ref, sha, timeout):
    """等远端 ref 真的变成 sha；push 失败或超时返回 False。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["git", "ls-remote", "--refs", remote, ref],
            capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.split() and line.split()[0] == sha:
                    return True
        time.sleep(1)
    return False


def wait_and_trigger(config, remote, refs_file, timeout):
    """等远端更新后逐个触发；这是 pre-push 钩子的后台工作。"""
    refs = read_refs(refs_file)
    if not refs:
        return 0
    pending = []
    for ref, sha in refs:
        if wait_remote(remote, ref, sha, timeout):
            pending.append(ref)
        else:
            print(f"等待远端超时：{ref} {sha}", file=sys.stderr)
    for ref in pending:
        trigger_ref(config, ref)
    return 0 if pending else 1


def install_hook(repo_root):
    """安装 pre-push 钩子；已有的旧钩子（如 git-lfs）改名保留并串联。"""
    hooks = Path(repo_root) / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    target = hooks / "pre-push"
    backup = hooks / "pre-push.before-jenkins"
    if target.is_file() and HOOK_MARKER not in target.read_text(encoding="utf-8", errors="replace"):
        if backup.exists():
            backup.unlink()
        target.rename(backup)
        backup.chmod(0o755)
        print(f"已备份原 pre-push 钩子到 {backup}")
    script = f"""#!/bin/sh
# {HOOK_MARKER}：push 完成后触发本地 Jenkins（由 tools/jenkins/trigger.py 生成）。
# 原有 pre-push 钩子（如有）保存在 pre-push.before-jenkins，先执行再触发。
refs="$(mktemp -t yh-jenkins-refs)"
cat > "$refs"
status=0
hooks_dir="$(dirname "$0")"
if [ -x "$hooks_dir/pre-push.before-jenkins" ]; then
  "$hooks_dir/pre-push.before-jenkins" "$@" < "$refs" || status=$?
fi
if [ "$status" -ne 0 ]; then
  rm -f "$refs"
  exit "$status"
fi
repo="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
nohup python3 "$repo/tools/jenkins/trigger.py" wait-and-trigger --remote "$1" --refs-file "$refs" >/dev/null 2>&1 &
exit 0
"""
    target.write_text(script, encoding="utf-8")
    target.chmod(0o755)
    print(f"已安装 {target}")
    print("push 后若未触发，运行：python3 tools/jenkins/trigger.py trigger --branch <分支>")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    hook = sub.add_parser("install-hook", help="安装/更新 pre-push 钩子")
    hook.add_argument("--repo", default=".")

    manual = sub.add_parser("trigger", help="手动触发一次")
    group = manual.add_mutually_exclusive_group(required=True)
    group.add_argument("--branch")
    group.add_argument("--tag")

    wait = sub.add_parser("wait-and-trigger", help="钩子后台用：等远端更新后触发")
    wait.add_argument("--remote", default="origin")
    wait.add_argument("--refs-file", required=True)
    wait.add_argument("--timeout", type=int, default=180)

    args = parser.parse_args(argv)
    if args.command == "install-hook":
        install_hook(args.repo)
        return 0
    try:
        config = load_config()
        if args.command == "trigger":
            ref = (f"refs/heads/{args.branch}" if args.branch
                   else f"refs/tags/{args.tag}")
            return 0 if trigger_ref(config, ref) else 1
        return wait_and_trigger(config, args.remote, args.refs_file, args.timeout)
    except TriggerError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    finally:
        if args.command == "wait-and-trigger":
            Path(args.refs_file).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
