#!/bin/bash
# yh 自举 cc 包装器（B5 运行语义门用）。
#
# 用途：模拟 stage0 的 `yh <file> -o <out>` 命令行接口——在 yh-build 容器内
# 执行自举编译器 `--emit-asm` 发射 GNU 汇编，再用 gcc 汇编/链接为
# AArch64 Linux 可执行文件。它只做路径映射与编译驱动，不解析、不修改
# yh 源码。
#
# 用法：
#   YH_STAGE=/work/tmp/bootstrap/stage1 tests/yh/container-yh-cc.sh <file> -o <out> \
#       [-Wl,-oformat=elf64-aarch64] [-sysroot <dir>] [-B <dir>]
#
#   * 后三个旗标是 stage0 交叉编译专属参数，本包装器识别后忽略；
#   * 仓库根挂载于容器 /work，参数中的仓库内绝对路径被映射；
#   * 退出码 0 表示编译成功。
set -e

ROOT=$(cd "$(dirname "$0")/../.." && pwd)

if [ -z "$YH_STAGE" ]; then
    echo "yh: cc 包装器需要环境变量 YH_STAGE（容器内 stage 路径，如 /work/tmp/bootstrap/stage1）" >&2
    exit 2
fi

src=""
out=""
extra=()
mode="none"
for a in "$@"; do
    case "$mode" in
        sysroot|B) mode="none"; continue ;;   # 消费旗标参数值（仅 stage0 需要）
    esac
    case "$a" in
        -o) mode="o" ;;
        -Wl,-oformat=elf64-aarch64) ;;
        -sysroot) mode="sysroot" ;;
        -B) mode="B" ;;
        *)
            if [[ "$a" == "$ROOT"/* ]]; then
                a="/work${a#"$ROOT"}"
            fi
            case "$mode" in
                o) out=$a; mode="none" ;;
                *) src=$a ;;
            esac
            ;;
    esac
done

if [ -z "$src" ] || [ -z "$out" ]; then
    echo "yh: cc 包装器需要 <file> -o <out> 参数" >&2
    exit 2
fi

exec docker exec -e YH_SRC="$src" -e YH_OUT="$out" -e YH_STAGE="$YH_STAGE" yh-build \
    sh -c '$YH_STAGE --emit-asm "$YH_SRC" > /tmp/yh-cc-$$.s && gcc -no-pie -o "$YH_OUT" /tmp/yh-cc-$$.s && rm -f /tmp/yh-cc-$$.s'
