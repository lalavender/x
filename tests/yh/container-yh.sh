#!/bin/bash
# yh 自举容器包装器（自举验证门用）。
#
# 用途：宿主（Darwin）侧把仓库内绝对路径映射到容器内 /work 挂载点，
# 然后在 yh-build 容器里执行指定的自举编译器 stage。它只做路径映射与
# 进程执行，不解析、不修改任何 yh 源码。
#
# 用法：
#   YH_STAGE=/work/tmp/bootstrap/stage1 tests/yh/container-yh.sh --syntax-check <file.yh>
#
#   * YH_STAGE：stage 二进制在容器内的路径（仓库根挂载在 /work）；
#   * 命令行参数原样传给 stage，仅当前缀为仓库根的绝对路径被映射为 /work/...；
#   * 退出码即容器内进程退出码（docker exec 原样转发）。
set -e

ROOT=$(cd "$(dirname "$0")/../.." && pwd)

if [ -z "$YH_STAGE" ]; then
    echo "yh: 容器包装器需要环境变量 YH_STAGE（容器内 stage 路径，如 /work/tmp/bootstrap/stage1）" >&2
    exit 2
fi

args=()
for a in "$@"; do
    if [[ "$a" == "$ROOT"/* ]]; then
        args+=("/work${a#"$ROOT"}")
    else
        args+=("$a")
    fi
done

exec docker exec -i yh-build "$YH_STAGE" "${args[@]}"
