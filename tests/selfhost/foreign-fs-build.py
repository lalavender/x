#!/usr/bin/env python3
"""在系统临时目录（另一文件系统）里冷编并运行 fixture 项目。

这是一道**文件系统维度**的回归门：编译器枚举 Linux 目录时曾经把 arm64 的
O_DIRECT（0x10000）当成 x86_64 的 O_DIRECTORY 传下去，于是「用 O_DIRECT 打开
目录」在 tmpfs/ext4/overlayfs 上一律 EINVAL（`无法打开目录: .`），只有不校验
该标志的 9p（WSL 的 /mnt/c）会侥幸放行——仓库挂在 9p 上时所有门都是绿的，
一进容器（overlayfs）连第一步 just 都过不去。所以这里刻意换一个文件系统构建，
把「宿主文件系统够宽容」这个偶然因素从门里排除掉。
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "modules" / "projects" / "tokenreplay"


def run(command, cwd):
    """运行真实编译器或二进制并保留输出，便于报告失败原因。"""
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                          timeout=120)


def fs_type(path):
    """给出路径所在文件系统的类型（Linux 读 /proc/mounts；其它宿主返回 ?）。"""
    try:
        lines = Path("/proc/mounts").read_text(encoding="utf-8").splitlines()
    except OSError:
        return "?"
    best = ""
    kind = "?"
    for line in lines:
        parts = line.split()
        if (len(parts) >= 3 and str(path).startswith(parts[1])
                and len(parts[1]) > len(best)):
            best = parts[1]
            kind = parts[2]
    return kind


def main():
    """把 fixture 复制到系统临时目录后冷编、运行，并核对退出码。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = str(Path(args.compiler_path).resolve())

    temp_root = Path(tempfile.mkdtemp(prefix="yh-foreign-fs-"))
    try:
        project = temp_root / "project"
        # 不带上游缓存：这道门要的是从零扫描目录的冷编路径
        shutil.copytree(FIXTURE, project,
                        ignore=shutil.ignore_patterns(".build"))
        output = temp_root / "program"
        print(f"外围文件系统构建：{temp_root}（fs: {fs_type(temp_root)}）")
        build = run([compiler, "build", "-o", str(output)], project)
        if build.returncode != 0 or not output.exists():
            print(f"FAIL 在外围文件系统上构建: rc={build.returncode}\n"
                  f"{build.stdout[-1200:]}{build.stderr[-1200:]}")
            return 1
        execution = run([str(output)], temp_root)
        if execution.returncode != 42:
            print(f"FAIL 外围文件系统构建出的程序结果: rc={execution.returncode}\n"
                  f"{execution.stderr[-800:]}")
            return 1
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
