# macOS/ARM64 LLVM：F2-0～4 与 Apple 聚合 ABI 首段

日期：2026-10-19。实施路线按用户确认的顺序推进：先让现有 Mac 种子构建并运行原生
LLVM 后端，再独立验收 Linux/x64 交叉引导。本文记录 Darwin 目标、对象、标量 ABI、生产
链接及 F2-5 的非 HFA 聚合首段；HFA、聚合回调、变参与自举切换仍未完成。

## 实施结果

- 固定 LLVM 21.1.8，并在 CLT SDK 26.5 上构建 Darwin/arm64 静态 host 包。真实 host probe
  能通过静态内嵌 lld 生成 Mach-O；动态依赖清单只含系统 `libc++` 与 `libSystem`。
- 接通 `aarch64-apple-darwin` 的 LLVM IR、PIC Mach-O 对象和汇编输出。`MACOSX_DEPLOYMENT_TARGET`
  进入文本身份与对象缓存键；把版本由 14.0 改成 15.0 后，O0/O2 对象缓存均失效，重发对象的
  `LC_BUILD_VERSION` 使用新版本。
- Darwin 生产链接使用进程内 `ld64.lld`，单文件与项目统一构造 raw 参数，验证 arm64、部署/SDK
  版本、代码签名，并在失败时保留旧可执行文件与旧成功 manifest。
- 新增独立 `compiler/backend/llvm_apple_abi.yh`，不复用 SysV 聚合 coercion。固定 Clang oracle
  与真实 O0/O2 Mach-O 双向 C/YH 测试覆盖 1/3/8/9/16 字节直接聚合、混合整数/浮点 union、
  24 字节间接参数/sret 和按值副本。有效嵌套 HFA 仍明确拒绝。
- 新增 Darwin 平台 `.yh` 运行语料及 C ABI `.yh`/C 桥测试。

## 验收与边界

- `make`：通过，使用现有 Darwin/arm64 种子，未滚种子。
- `make test-llvm-darwin`：通过，包含静态 host、对象、标量 ABI、聚合 ABI、生产链接和失败保留。
- `make test`：通过，语法 78/78 正例与 42/42 反例；运行语料 206/207、1 个 Linux 专属用例跳过；
  失败与 pass 语料 140/140。
- `make selfhost-native`：固定点、自解析、CLI、语料、隔离与 lex-stats 均通过；随后在继承工作树的
  `tests/selfhost/runtime-memory.py` 因自编译器导入 C runtime `strlen` 失败。未修改这项既有基线，
  不将其归因于 Darwin LLVM ABI，也未滚种子。

F2-5 尚需实现 HFA 参数/返回寄存器分类、寄存器耗尽整体上栈、聚合函数指针 callback、C→YH→C
嵌套回调、prelude/runtime 所需 C 变参与 Darwin `va_list`。默认切换、原生固定点、macos-14 CI
和 Linux/x64 交叉路线继续按实施方案后续阶段验收。
