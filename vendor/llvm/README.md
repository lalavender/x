# yh 内嵌 LLVM SDK

首期固定 LLVM 21.1.8，Linux/x86_64 宿主 SDK 是 Ubuntu 发布的
`llvm-21-dev_21.1.8-6ubuntu1_amd64.deb`。下载地址、SHA-256 和静态组件闭包
记录在 sdk.lock.json；包不会安装进系统，只将 C API/配置头、静态组件和许可解包到
tmp/llvm-migration/sdk/linux-x64-capi/。每次从已校验的包重读所需内容，避免信任坏缓存。

`python3 tools/llvm-sdk.py build` 使用 `/usr/bin/gcc` 编译薄桥，返回精确的静态
归档链接参数；不查找系统 LLVM，不调用 llvm-config/clang/llc。LLVM 全部组件按
`.a` 的绝对路径链接进宿主可执行文件，禁止 libLLVM 动态依赖。

`python3 tools/llvm-sdk.py link --object <调用方对象> --output <宿主>` 完成静态链接。
WSL/DrvFS 上 GNU BFD 按归档成员反复 read/lseek 会产生大量 9P RPC，已复现超过
120 秒的链接超时；该入口把固定归档原字节传入匿名 memfd，再调用同一 GNU 链接器。
无需系统 lld，持久产物仍全在 tmp，内存 fd 在链接返回后关闭。

SDK 来自固定发行包，需普通 Linux 构建环境（Python、dpkg-deb、gcc/g++、ar）。
这版 SDK 使用 libc、zlib、zstd、libxml2 的 OS 动态库，C++/gcc 支持库静态链接。
这些是披露的非 LLVM 依赖；后续发行包必须同时说明最低 glibc 与 OS 库版本，
不能以“无系统 LLVM”暗示“无 OS 依赖”。首期仅在本机 WSL Ubuntu 验收。

LLVM 采用 Apache-2.0 WITH LLVM-exception。发行包的完整许可/作者信息位于
包内 `usr/share/doc/llvm-21-dev/copyright`，提取到 SDK 的 `share/LICENSE`；
最终编译器发行时必须携带该文件。
来源：[LLVM 21.1.8](https://github.com/llvm/llvm-project/releases/tag/llvmorg-21.1.8)、
[LLVM 许可](https://github.com/llvm/llvm-project/blob/llvmorg-21.1.8/llvm/LICENSE.TXT)、
[Ubuntu 固定发行包](https://archive.ubuntu.com/ubuntu/pool/universe/l/llvm-toolchain-21/)。

当前桥只提供 LLVM 文本验证/O0/O2/对象/汇编及原子发布。独立测试宿主的成功
不代表 yh 前端、运行时和自举已接入。ARM64 启动宿主需要独立架构 SDK，不能混链
x64 归档；对应依赖在 LLVM 实施方案 LL3/LL10/F1 中验收。
