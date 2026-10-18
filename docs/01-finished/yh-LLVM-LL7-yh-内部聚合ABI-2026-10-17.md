# LLVM LL7-S3：yh-llvm-v1 内部聚合 ABI

日期：2026-10-17

## 完成内容

- 给 YH 内部函数调用约定分配 IR ABI id `IR_ABI_YH_LLVM_V1`，并让函数、调用、模块符号及函数类型 verifier 接受该版本。函数级序列化保留 ABI id；模块序列化身份因此包含此 ABI 选择。
- YH 内部链接符号追加 `$yhllvmv1`。模块定义和跨模块调用使用同一命名，避免旧 ABI 命名的机器对象被链接器误解析为当前实现。
- 结构体、定长数组和切片参数在源码从左到右求值时复制到独立缓冲，再以指针传入。callee 将该缓冲作为按值参数的私有存储；callee 对参数的写入不会修改调用方原对象。
- 聚合返回通过调用方提供的首个隐藏结果缓冲实现。缓冲大小和对齐来自受检源类型布局。结构体、数组和切片均复用该规则；切片只复制描述符，元素继续共享。
- 扩展模块 IR verifier，分别检查逻辑签名与隐藏物理参数、聚合指针参数、返回缓冲和调用结果，避免把 YH 内部约定冒充成 C ABI。

## 测试与验证

- `tests/modules/projects/llvmabi/bridge/bridge.yh` 增加跨模块结构体、定长数组和切片的按值参数/返回，以及切片返回后继续访问原数组的断言。
- `tests/selfhost/llvm-abi.py` 检查 YH 内部符号包含 ABI 版本，并对 LLVM O0/O2 分别执行跨模块编译、链接和运行。该门同时保留 clang C ABI oracle 和 S1/S2 C 标量互调检查。
- WSL x86_64 构建命令：`PATH="$PWD/tmp/boot/crossbin:$PATH" SEED=bin/yh-linux-arm64 YH_LINK=/nonexistent make`。
- ABI 回归：`python3 tests/selfhost/llvm-abi.py --compiler-path ./yh`。
- 结果：`make` 成功；ABI 回归成功，clang oracle、LLVM verifier、O0/O2 项目链接运行全部通过。
- 未运行 `make seed`；未更改任何入库种子或哈希。

## 尚未包含

C ABI 的 INTEGER/SSE/MEMORY 聚合分类和 C 侧 coercion/sret/byval、函数指针/间接调用、callback、变参及 `@[noreturn]` 仍按 LL7 计划继续实现。用户裸 C 变参遵循仓库既有 FFI 约束，保持延期。
