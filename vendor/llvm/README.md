# yh 内嵌 LLVM SDK

固定 LLVM 21.1.8，Linux/x86_64 与 Linux/AArch64 SDK 分别来自 Ubuntu 发布的
`llvm-21-dev_21.1.8-6ubuntu1_amd64.deb`、`llvm-21-dev_21.1.8-6ubuntu1_arm64.deb`。
下载地址、SHA-256 和静态组件闭包记录在 sdk.lock.json；包不会安装进系统，只将
C API/配置头、静态组件和许可解包到 tmp/llvm-migration/sdk/linux-x64-capi/ 或
linux-arm64-capi/。每次从已校验的包重读所需内容，避免信任坏缓存。

`python3 tools/llvm-sdk.py build` 使用 `/usr/bin/gcc` 编译薄桥，返回精确的静态
归档链接参数；不查找系统 LLVM，不调用 llvm-config/clang/llc。LLVM 全部组件按
`.a` 的绝对路径链接进宿主可执行文件，禁止 libLLVM 动态依赖。

`python3 tools/llvm-sdk.py link --object <调用方对象> --output <宿主>` 完成静态链接。
`--host linux-x86_64` 或 `--host linux-aarch64` 明确选择**运行 LLVM 桥的架构**，
省略时选择构建机架构；这个参数不限制桥可发射的 x64/ARM64 目标。x64 机器交叉
构建 ARM64 使用 `/usr/bin/aarch64-linux-gnu-gcc/g++/ar`，原生机器使用
`/usr/bin/gcc/g++/ar`，不采纳 PATH 中的包装器。ARM 桥配置写入
tmp/llvm-migration/sdk/bridge-linux-arm64/config.json，x64 仍使用 sdk/bridge/config.json。
返回 JSON 记录运行宿主、构建机、工具链、SDK/清单/桥源码/头文件/归档的 SHA-256。

WSL/DrvFS 上 GNU BFD 按归档成员反复 read/lseek 会产生大量 9P RPC，已复现超过
120 秒的链接超时；该入口把固定归档原字节传入匿名 memfd，再调用同一 GNU 链接器。
无需系统 lld，持久产物仍全在 tmp，内存 fd 在链接返回后关闭。

SDK 来自固定发行包，需普通 Linux 构建环境（Python、dpkg-deb、gcc/g++、ar）。
x64 流程仍使用 libc、zlib、zstd、libxml2 的 OS 动态库，C++/gcc 支持库静态链接。
ARM64 将 zlib/zstd 的固定发行包中 `.a` 一同静态链接，包名、SHA-256 与实际提取文件
也入清单；实际 LLVM 组件闭包不需要 XML。ARM64 可执行文件仅动态依赖 libc/libm，
依赖 ARM glibc 2.38 或更新版本；构建使用普通交叉 GCC 15.2。发行时应以最终
`readelf --version-info` 报告确认 glibc 下限，并携带 LLVM/zlib/zstd 许可。
这些是披露的非 LLVM 依赖；“无系统 LLVM”仍需要普通 OS 运行库。

LLVM 采用 Apache-2.0 WITH LLVM-exception。发行包的完整许可/作者信息位于
包内 `usr/share/doc/llvm-21-dev/copyright`，提取到 SDK 的 `share/LICENSE`；
最终编译器发行时必须携带该文件。
ARM64 支持库的许可另存为 SDK 的 share/LICENSE-zlib 与 share/LICENSE-zstd。
来源：[LLVM 21.1.8](https://github.com/llvm/llvm-project/releases/tag/llvmorg-21.1.8)、
[LLVM 许可](https://github.com/llvm/llvm-project/blob/llvmorg-21.1.8/llvm/LICENSE.TXT)、
[Ubuntu 固定发行包](https://archive.ubuntu.com/ubuntu/pool/universe/l/llvm-toolchain-21/)。

当前桥只提供 LLVM 文本验证/O0/O2/对象/汇编及原子发布。独立测试宿主的成功
不代表 yh 前端、运行时和自举已接入。

`python3 tests/selfhost/llvm-embedded-arm64.py --chroot` 在 Linux/ARM64 原生运行，
或在 Linux/x64 使用 qemu-aarch64（测试需要 root 做 chroot）。门禁交叉链接真正的
ARM64 宿主，验证 O0/O2、ARM64/x64 对象与汇编、ARM 目标执行、8 个拒绝案例、
失败保持旧产物、诊断边界与重复调用；随后只复制客户端/qemu/OS 库到隔离根，
复验无系统 LLVM 与空工具 PATH。报告位于 tmp/llvm-migration/arm-sdk/embedded/report.json。
隔离根每轮新建并在结束时回收，历史排查或验收留下的库/工具不能参与结果。
追加 `--compiler-path ./yh` 可编译 `llvm-embedded-arm64-probe.yh`，真实 yh C ABI 调用者
链接 ARM 静态桥并生成 x64 对象；在 x64 WSL 中还将该对象链接并原生执行。
这确认源级调用与运行时可以接入桥，生产编译器的 LLVM pipeline 仍在 LL3/LL10 接入。
