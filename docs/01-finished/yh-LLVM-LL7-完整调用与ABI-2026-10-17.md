# LLVM LL7：完整调用与 ABI 完成记录

日期：2026-10-17  
范围：Linux/x86_64 System V；LL4 控制流、LL5 内存/聚合与 LL6 浮点已先行完成。

## 交付内容

- 固定参数 C ABI 支持定宽整数、指针、f32/f64 与 `_Bool`。窄整数扩展属性写在函数签名和调用点；C `_Bool` 使用 `i1 zeroext`，YH 内部 bool 仍为 i8，并在 ABI 边界按非零值归一。
- YH 函数采用版本化 `yh-llvm-v1` ABI。结构体、定长数组和切片参数在各自求值位置复制；聚合返回使用隐藏结果缓冲，切片只复制描述符。YH 内部链接名带 `$yhllvmv1` 后缀。
- SysV C 结构体/联合体按 INTEGER、SSE、MEMORY 分类。小聚合使用 LLVM coercion；大聚合按 ABI 使用 `sret`/`byval`。clang 21.1.8 生成的 CPair、CMixed、CWide IR 与后端签名对照。
- 函数类型、模块接口与稳定序列化保留 ABI、参数/返回类型和变参 metadata。YH 与 C 函数值可跨模块传递、返回并间接调用；callback 覆盖标量及 CPair 聚合的 C→YH、YH→C 双向路径。
- YH 类型化变参 `vararg=2` 按源码顺序求值并打包为末尾切片 ABI 参数。模块符号与 `.s.i` 保留 `@[noreturn]`；违约返回后发射 `llvm.trap`/`unreachable`，属性变化会使调用方 IR/cache 重建。
- 用户裸 C 变参在源码层继续拒绝，避免 LLVM 猜测 C 默认参数提升。ARM64 AAPCS64/HFA 留给 F1；LLVM 生产驱动仍归 LL9。

## 回归与夹具维护

- `tests/selfhost/llvm-abi.py` 覆盖 clang oracle、LLVM verifier/优化、O0/O2 跨模块链接与双向运行、函数值/callback、类型化变参、`noreturn` 缓存变化和源级拒绝。
- `tests/selfhost/llvm-module-cache.py` 覆盖模块序列化往返、逐字节确定性、稳定身份和 11 类坏输入拒绝。手写 IR 调用记录已补齐新字段；模块符号定长记录和序列化版本断言同步当前格式。
- `tests/modules/projects/irverify` 的损坏输入改为破坏稳定格式 magic，不再依赖随 IR 字段增长而移动的固定字节偏移。全局切片支持后，模块 lowering 拒绝用例改用仍不支持的深指针 fixture。

## 验收

在 WSL x86_64 Ubuntu 使用 Linux/aarch64 入库种子、仓库交叉 gcc 包装和 `YH_LINK=/nonexistent` 完成：

- `make test`：语法 78/78 与 42/42；编译器语法 78/78 与 42/42；运行/拒绝/仅编译语料共 321/321（181/181、132/132、8/8）。
- `make selfhost-native`：24 个模块固定点产物逐字节一致；95 个源文件自解析；运行语料 321/321；模块 18/18；项目 103/103。
- `python3 tests/selfhost/llvm-module-cache.py --compiler-path ./yh`：往返、确定性、11 类坏输入拒绝和身份摘要通过。
- `python3 tests/selfhost/llvm-abi.py --compiler-path ./yh`：clang oracle、C 标量/bool/聚合、YH 聚合/类型化变参、函数指针/C callback、noreturn trap，以及 O0/O2 双向调用全部通过。
- 主门全绿后执行 `make seed`，Linux/aarch64 种子从 `073282e9f1f773f162ccf9674a86f357e3bd6c9b74ccb65fe613968566916ccd` 更新为 `f5c7ab922ae93823242c7b92bbbd7fd8198378e62316997933ae7f24c4743c1c`。新种子再次通过 `make selfhost-native` 与 `make test`，固定点和全量语料计数不变。

## 后续边界

LL7 关闭 Linux/x86_64 SysV 调用与 ABI 切片。用户裸 C 变参仍遵循既有 FFI 拒绝策略；ARM64 HFA/AAPCS64 归 F1；CLI/模块 worker 的 LLVM 正式驱动及完整生产缓存键归 LL9。LL7 未切换生产默认后端。
