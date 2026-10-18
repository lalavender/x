# LLVM LL9L：内嵌 lld 验收记录

日期：2026-10-18  
范围：固定 LLVM/LLD 21.1.8 SDK、C++ shim、Linux/x86_64 生产链接接入与交叉格式探针。

## 结果

- L9L-1 至 L9L-5 的实现与独立验收完成：固定 SDK 和许可清单、C++ `lld::lldMain` shim、
  lld 一次性 worker、项目与单文件链接接入、链接缓存身份和失败事务、Mach-O/PE 格式探针。
- Linux/x86_64 内嵌 lld 通过独立 `tests/selfhost/llvm-lld.py` 探针：空 PATH 下重复链接、
  诊断截断、失败不发布、ELF machine、Mach-O/PE 文件头、gcc 对照，以及无 libLLVM/liblld
  动态依赖。
- `tests/selfhost/llvm-driver.py` 通过，覆盖无外部 LLVM 工具的 check、语法检查、emit、单文件
  编译、项目 build/run 和空格路径。
- LL9 全量 LLVM x86_64 runner 的 O0/O2 均通过 335/335；滚种子后的 `make test` 与
  `make selfhost-native` 通过。新 Linux/AArch64 种子 SHA-256：
  `dc64daac8b61368634c11e81b94f402fc0e28a98e0d4c12c054d5f520e23db23`。

## L9L-6 x64 原生汇合补录（2026-10-18）

- LL10 自举脚本以 Linux/AArch64 种子经 qemu 生成 A，再完成 x64 原生 B/C/D；O0/O2 两组
  B→C、C→D 固定点各有 24 个 `.ll/.s.i/.s.ct` 文件逐字节一致。
- B/C/D 自编未调用 gcc wrapper。D-O0/O2 均通过嵌入 lld 身份校验，版本为 SDK 锁定的
  21.1.8，身份 SHA-256 为
  `721002cf04413fd64ad9b77002f718eb83516914876c9193901db150152f5b96`；候选通过
  `readelf -d`，无 LLVM/lld 动态依赖。O0/O2 固定点探针通过。
- 因此 L9L-6 的生产链接、lld 身份、动态依赖与固定点要求已闭环。此前 O0 项目 runner 的 PATH
  专项按 `yh` 启动、但候选文件名为 `yh-D-O2`，已通过临时 `yh` 启动链接修复；之后完整复跑
  `make selfhost-llvm`，O0/O2 项目各 104/104，所有最终门通过。早前 WSL 中断记录属于修复前的
  中间状态，不再阻挡 LL10。
- Mach-O/PE 探针不代表对应平台生产链接支持；LL9L 后 Linux/x86_64 启用内嵌 lld，其他
  未接入目标仍走平台 cc 回落。LL10 与后续边界见
  [实施方案 §LL9L/§LL10](../02-plan/yh-LLVM后端替换实施方案.md)。

## LL10 全门闭环补录（2026-10-18）

- `make test-llvm` 与 `make selfhost-llvm` 均退出 0。O0/O2 各通过语料 343/343、模块 18/18、
  项目 104/104；最终 D 自解析 98/98，A/B/C/D 均为 ELF machine=62。
- O0/O2 的 B→C 与 C→D 固定点各 24 个 `.ll/.s.i/.s.ct` 文件逐字节一致。B/C/D 自编均未调用
  gcc wrapper；D-O0/O2 内嵌 lld 身份 SHA-256 为
  `721002cf04413fd64ad9b77002f718eb83516914876c9193901db150152f5b96`，无 LLVM/lld 动态依赖。
- LL9L 链接、LL9 缓存/驱动、runtime-memory 专项均通过。另修复无条件循环内条件返回的 LLVM
  lowering，新增 `tests/yh-run/run/203-llvm-infinite-loop-return.yh` 锁定回归。
- `make test` 与滚种子后的 `make selfhost-native` 通过；新 Linux/AArch64 种子 SHA-256：
  `8ea2a9acc20438b385ccddd522b50b8dd4749423c8db2695c758296ada343b8c`。
- 项目 runner 的 PATH 启动问题已完整复验关闭。R2b 真线程池/任务私有状态仍是独立待办，LL11
  默认切换仍由 R2b 硬门控制。详细代码和消费者证据见
  [LL10 完成记录](yh-LLVM-LL10-x64原生自举-2026-10-18.md)。
