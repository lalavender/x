# yh CI 基础镜像（Gitea Actions，Apple container）。
#
# 预装各端构建/测试必需工具，替代每个 job 里的 `apt-get install`：
#   * build-essential / binutils：gcc 链接后端与 `make`
#   * python3：门禁脚本（tests/yh、tests/yh-run、modules）
#   * xz-utils：解包种子与 LLVM SDK 归档
#   * libxml2-dev / zlib1g-dev / libzstd-dev：内嵌 LLVM 静态链接依赖
#   * clang：Linux/x86_64 模拟端与 LLVM 桥的 C/C++ 驱动
#
# 用法（arm64 原生）：
#   container build -t yh-ci:ubuntu24 -f .gitea/ci/Dockerfile .
# 用法（x86_64 模拟）：
#   container build -a amd64 -t yh-ci:ubuntu24-amd64 -f .gitea/ci/Dockerfile .
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
        build-essential binutils python3 xz-utils \
        libxml2-dev zlib1g-dev libzstd-dev clang ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
