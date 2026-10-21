#!/usr/bin/env python3
"""创建/更新本地 Jenkins 的 yh-ci、yh-release 两个 job 和 GitHub 凭据。

运行前准备：
  1. Jenkins 用户（默认 jenkins）的 API Token：Jenkins → 右上角用户 →
     Configure → API Token → Add new token；
  2. 一个有 repo 权限的 GitHub Token（取种、clone、发布 Release）；
  3. 磁盘：LLVM 闭包缓存 + 构建产物至少预留 15 GB。

示例：
  JENKINS_TOKEN=... GITHUB_TOKEN=... \\
    python3 tools/jenkins/setup.py --user jenkins --repo lalavender/x

成功后：
  - 生成 ~/.config/yh-jenkins/env（0600），供 pre-push 钩子读取；
  - 安装 pre-push 钩子（备份原有钩子）；
  - 手动触发：python3 tools/jenkins/trigger.py trigger --branch llvm
"""

import argparse
import glob
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import xml.sax.saxutils as xml_escape
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:8080"
DEFAULT_REPO = "lalavender/x"
STORE = "system::system::jenkins"
DOMAIN = "_"


class SetupError(RuntimeError):
    """配置失败；打印出来让用户修。"""


def find_cli_jar(url, user, token):
    """优先用 Homebrew Jenkins 自带的 CLI jar，否则从服务器下载。"""
    candidates = sorted(glob.glob("/opt/homebrew/opt/jenkins-lts/libexec/cli-*.jar"))
    if candidates:
        return Path(candidates[-1])
    target = Path("tmp") / "jenkins-cli.jar"
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(f"{url}/jnlpJars/jenkins-cli.jar")
    request.add_header("Authorization", basic_auth(user, token))
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            target.write_bytes(response.read())
    except (urllib.error.HTTPError, urllib.error.URLError) as error:
        raise SetupError(f"下载 Jenkins CLI 失败：{error}") from error
    return target


def basic_auth(user, token):
    """Jenkins Basic 认证头。"""
    import base64
    raw = f"{user}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def cli(jar, url, user, token, args, data=None):
    """调用 Jenkins CLI；token 走临时文件，不出现在命令行。"""
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write(f"{user}:{token}\n")
        auth_file = handle.name
    os.chmod(auth_file, 0o600)
    try:
        command = ["java", "-jar", str(jar), "-s", url, "-http",
                   "-auth", f"@{auth_file}", *args]
        result = subprocess.run(command, input=data, capture_output=True)
    finally:
        os.unlink(auth_file)
    return result


def check_server(url, user, token):
    """确认 Jenkins 可达且 token 有效。"""
    request = urllib.request.Request(f"{url}/api/json")
    request.add_header("Authorization", basic_auth(user, token))
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            import json
            data = json.load(response)
        print(f"Jenkins {data.get('version', '?')} 可访问：{url}")
    except (urllib.error.HTTPError, urllib.error.URLError) as error:
        raise SetupError(f"连接 Jenkins 失败（检查 URL/token）：{error}") from error


def credential_xmls(token, github_user):
    """返回 (id, xml) 列表：HTTPS clone 与 Secret text 各一份。"""
    escaped = xml_escape.escape(token)
    https = f"""<?xml version='1.1' encoding='UTF-8'?>
<com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl>
  <scope>GLOBAL</scope>
  <id>github-https</id>
  <description>GitHub HTTPS clone for yh CI</description>
  <username>{xml_escape.escape(github_user)}</username>
  <password>{escaped}</password>
</com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl>
"""
    secret = f"""<?xml version='1.1' encoding='UTF-8'?>
<org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl>
  <scope>GLOBAL</scope>
  <id>github-token</id>
  <description>GitHub token for yh seed fetch and release publish</description>
  <secret>{escaped}</secret>
</org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl>
"""
    return [("github-https", https), ("github-token", secret)]


def job_xml(name, description, param_name, param_default, param_desc, repo_url, branch):
    """生成 Pipeline script from SCM 的 job 配置。"""
    return f"""<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <actions/>
  <description>{xml_escape.escape(description)}</description>
  <keepDependencies>false</keepDependencies>
  <properties>
    <hudson.model.ParametersDefinitionProperty>
      <parameterDefinitions>
        <hudson.model.StringParameterDefinition>
          <name>{param_name}</name>
          <description>{xml_escape.escape(param_desc)}</description>
          <defaultValue>{xml_escape.escape(param_default)}</defaultValue>
          <trim>true</trim>
        </hudson.model.StringParameterDefinition>
      </parameterDefinitions>
    </hudson.model.ParametersDefinitionProperty>
  </properties>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition" plugin="workflow-cps">
    <scm class="hudson.plugins.git.GitSCM" plugin="git">
      <configVersion>2</configVersion>
      <userRemoteConfigs>
        <hudson.plugins.git.UserRemoteConfig>
          <url>{xml_escape.escape(repo_url)}</url>
          <credentialsId>github-https</credentialsId>
        </hudson.plugins.git.UserRemoteConfig>
      </userRemoteConfigs>
      <branches>
        <hudson.plugins.git.BranchSpec>
          <name>*/{xml_escape.escape(branch)}</name>
        </hudson.plugins.git.BranchSpec>
      </branches>
      <doGenerateSubmoduleConfigurations>false</doGenerateSubmoduleConfigurations>
      <submoduleCfg class="empty-list"/>
      <extensions/>
    </scm>
    <scriptPath>Jenkinsfile</scriptPath>
    <lightweight>true</lightweight>
  </definition>
  <triggers/>
  <disabled>false</disabled>
</flow-definition>
"""


def ensure_job(jar, url, user, token, name, xml):
    """存在则更新，不存在则创建。"""
    existing = cli(jar, url, user, token, ["get-job", name])
    if existing.returncode == 0:
        result = cli(jar, url, user, token, ["update-job", name], xml.encode("utf-8"))
        action = "更新"
    else:
        result = cli(jar, url, user, token, ["create-job", name], xml.encode("utf-8"))
        action = "创建"
    if result.returncode != 0:
        raise SetupError(
            f"{action} job {name} 失败：{result.stderr.decode('utf-8', 'replace')}")
    print(f"已{action} job：{name}")


def ensure_credential(jar, url, user, token, cred_id, xml):
    """先删后建，保证 token 更新后能覆盖。"""
    cli(jar, url, user, token, ["delete-credentials", STORE, DOMAIN, cred_id])
    result = cli(jar, url, user, token,
                 ["create-credentials-by-xml", STORE, DOMAIN], xml.encode("utf-8"))
    if result.returncode != 0:
        raise SetupError(
            f"创建凭据 {cred_id} 失败：{result.stderr.decode('utf-8', 'replace')}")
    print(f"已写入凭据：{cred_id}")


def write_env_file(url, user, token, ci_job, release_job):
    """写 pre-push 钩子读取的配置，权限 0600。"""
    path = Path.home() / ".config" / "yh-jenkins" / "env"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"警告：无权创建 {path.parent}；请手动写入触发配置（chmod 600）")
        return
    try:
        path.write_text(
            "# yh 本地 Jenkins 触发配置（由 tools/jenkins/setup.py 生成）\n"
            f"JENKINS_URL={url}\n"
            f"JENKINS_USER={user}\n"
            f"JENKINS_TOKEN={token}\n"
            f"JENKINS_CI_JOB={ci_job}\n"
            f"JENKINS_RELEASE_JOB={release_job}\n",
            encoding="utf-8")
        path.chmod(0o600)
        print(f"已写入 {path}（0600）")
    except PermissionError:
        print(f"警告：无权写入 {path}；请保留已有配置或手动写入（chmod 600）")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("JENKINS_URL", DEFAULT_URL))
    parser.add_argument("--user", default=os.environ.get("JENKINS_USER", "jenkins"))
    parser.add_argument("--token", default=os.environ.get("JENKINS_TOKEN", ""))
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument("--github-user", default="lalavender",
                        help="GitHub 账号名（HTTPS clone 凭据的用户名）")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--branch", default=None,
                        help="Jenkinsfile 所在分支（缺省取当前分支）")
    parser.add_argument("--ci-job", default="yh-ci")
    parser.add_argument("--release-job", default="yh-release")
    parser.add_argument("--skip-hook", action="store_true",
                        help="只建 job/凭据，不安装 pre-push 钩子")
    args = parser.parse_args(argv)

    token = args.token.strip()
    github_token = args.github_token.strip()
    if not token:
        print("FAIL 缺少 Jenkins API token：--token 或 JENKINS_TOKEN", file=sys.stderr)
        return 1
    if not github_token:
        print("FAIL 缺少 GitHub token：--github-token 或 GITHUB_TOKEN", file=sys.stderr)
        return 1

    url = args.url.rstrip("/")
    branch = args.branch
    if not branch:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True).stdout.strip()
        if not branch or branch == "HEAD":
            branch = "llvm"
    try:
        check_server(url, args.user, token)
        jar = find_cli_jar(url, args.user, token)
        repo_url = f"https://github.com/{args.repo}.git"

        for cred_id, xml in credential_xmls(github_token, args.github_user):
            ensure_credential(jar, url, args.user, token, cred_id, xml)

        ensure_job(
            jar, url, args.user, token, args.ci_job,
            job_xml(args.ci_job,
                    "yh 分支门：ANTLR + Linux/arm64 + Darwin/arm64",
                    "BRANCH", branch, "要构建的分支（arm64/llvm/main 或 <ver>-rc）",
                    repo_url, branch))
        ensure_job(
            jar, url, args.user, token, args.release_job,
            job_xml(args.release_job,
                    "yh 发布：三端构建 + 打包 + GitHub Release",
                    "TAG", "", "版本 tag（x.y.z；rc tag 暂不触发）",
                    repo_url, branch))

        write_env_file(url, args.user, token, args.ci_job, args.release_job)

        if not args.skip_hook:
            result = subprocess.run(
                [sys.executable, "tools/jenkins/trigger.py", "install-hook"],
                capture_output=True, text=True)
            if result.returncode != 0:
                print(result.stderr, file=sys.stderr)
                raise SetupError("安装 pre-push 钩子失败")
            print(result.stdout.strip())

        print("\n完成。下一步：")
        print(f"  手动试跑分支门：python3 tools/jenkins/trigger.py trigger --branch {branch}")
        print(f"  手动试跑发布：  python3 tools/jenkins/trigger.py trigger --tag 0.0.8-rc.1")
        print(f"  打开 Jenkins：  {url}/job/{args.ci_job}/")
        return 0
    except SetupError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
