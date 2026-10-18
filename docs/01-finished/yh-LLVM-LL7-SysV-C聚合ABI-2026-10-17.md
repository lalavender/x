# LLVM LL7-S4：SysV C 聚合 ABI

日期：2026-10-17

## 完成内容

- Linux/x86_64 System V 的 C 结构体与联合体按布局递归分类。首期支持两个八字节的 INTEGER/SSE coercion，以及超过 16 字节对象的 MEMORY 传参/返回。
- C 调用点将按值聚合分片加载后传入；寄存器返回被拆回调用方的 IR 聚合缓冲。MEMORY 返回使用隐藏 `sret` 缓冲，MEMORY 参数使用 `byval` 缓冲。
- C ABI 函数定义端将寄存器形参分片写回局部聚合存储，将 MEMORY 形参作为 byval 指针使用；函数返回从 IR 结果缓冲构造 coercion 值或返回 `void`。
- 支持从 YH 调 C、C 调 YH 的聚合参数和返回；YH 内部 `yh-llvm-v1` 显式指针约定保持独立。

## 测试与验证

- `tests/modules/projects/llvmabi` 覆盖 CPair（INTEGER）、CMixed（SSE+INTEGER）与 CWide（MEMORY），包括 C/YH 双向定义与调用。
- `tests/selfhost/llvm-abi.py` 新增 clang 21.1.8 聚合签名 oracle，断言 `i64`、`{double, i32}`、`sret`/`byval` 形态；O0/O2 均通过 LLVM verifier、优化、原生编译、链接和运行。
- WSL x86_64 冷编：`PATH="$PWD/tmp/boot/crossbin:$PATH" SEED=bin/yh-linux-arm64 YH_LINK=/nonexistent make`。
- ABI 门：`python3 tests/selfhost/llvm-abi.py --compiler-path ./yh`。
- 结果：两条命令成功；O0/O2 跨模块项目真实运行通过。`make test` 与 `make selfhost-native` 留待 LL7 全部切片完成后统一执行。
- 未运行 `make seed`；Linux/arm64 种子及哈希未变。

## 范围

该分类器只用于 Linux/x86_64 SysV C ABI。ARM64 HFA 留给 F1；裸 C 变参继续遵守仓库既有延期决定。LL7 剩余函数值/间接调用、callback、变参 metadata 与 `@[noreturn]` 契约继续推进。
