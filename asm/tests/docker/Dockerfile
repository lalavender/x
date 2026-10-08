# yh_link 的 ELF 交叉验证环境。
#
# 宿主（Darwin）没有 AArch64 的 ELF 链接器，也没有 Linux 系统调用环境，
# 所以链接与运行放在容器里做。这一层只装 GNU 交叉 binutils，不装编译器：
# 汇编由 yh_link 负责，容器只当「链接器 + 运行环境」。
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        binutils-aarch64-linux-gnu \
        binutils-x86-64-linux-gnu \
        qemu-user-static \
    && rm -rf /var/lib/apt/lists/*
