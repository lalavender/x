# LLVM LL7 首片：固定参数 C ABI 标量直接调用

日期：2026-10-17

## 范围

在 Linux/x86_64 System V 目标上打通固定参数、直接调用的 C ABI 标量边界：
有符号/无符号整数、指针、f32/f64，以及混合整数/浮点参数。首片未实现 yh-llvm-v1
内部聚合调用约定、函数指针/间接调用、callback、变参、聚合分类和 `@[noreturn]`。
C `_Bool` 也暂不作为此首片的标量类型，后端预检会明确拒绝。

## 实现

- 新增 `compiler/backend/llvm_call.yh`：限定 SysV x86_64 标量签名，并将 i8/i16
  的有符号/无符号扩展映射为 LLVM `signext`/`zeroext`。
- LLVM 函数声明、定义、参数和 call site 使用同一属性规则；调用点属性不能只留在函数声明。
- 调用点首次发现 `@[extern]` 符号时登记外部链接；带 `@[extern]` 的 C ABI 定义也发为外部链接，
  使独立 C 对象可以解析它们。普通私有 yh 函数仍保留 internal linkage。
- 未支持的 C ABI 类型、变参或非 SysV 目标在 LLVM 发射前整体拒绝，不进入旧后端回退。
- 新增 `tests/selfhost/llvm-abi-probe.yh` 与 `llvm-abi-bridge.c`，从两侧交错调用；覆盖
  i8/u8/i16/u16 窄参数与返回、f32/f64、指针、8 个整数栈参数和 8 个混合整数/浮点参数。
  `llvm-abi-unsupported.yh` 固定 C bool 签名拒绝。
- 新增 `tests/selfhost/llvm-abi.py`：用 clang 21.1.8 的 IR 对照扩展属性，以 `opt` 验证 O0/O2，
  再用真实 C 对象链接并双向运行。

## 验证

WSL Ubuntu/x86_64，使用 `SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent` 与仓库交叉 gcc 包装器：

- `make`：通过，冷编产出 Linux/aarch64 候选编译器。
- `python3 tests/selfhost/llvm-abi.py --compiler-path ./yh`：通过；clang oracle、属性、O0/O2 LLVM
  verifier/优化、C 链接和双向运行全绿；不支持的 C bool 签名按预期拒绝。
- `make test`：语法正例 78/78、反例 42/42；编译器语法正例 78/78、反例 42/42；运行/失败/仅编译
  语料 181/181、131/131、8/8，总计 320/320。
- `make selfhost-native`：通过；cc3→cc4 固定点 24 项一致、自解析 94 个源文件、模块 18/18、
  项目 103/103；scratch isolation、命令、运行时内存和链接缓存门均通过。
- `git diff --check`：通过。工作区已有 LL4–LL6 等在途改动，未创建提交。
- 入库 Linux/arm64 种子哈希仍为
  `073282e9f1f773f162ccf9674a86f357e3bd6c9b74ccb65fe613968566916ccd`；未执行 `make seed`。

## 后续边界

下一步继续 LL7：先固定 yh LLVM 内部调用签名，再实现 x86_64 SysV INTEGER/SSE/MEMORY 聚合分类、
函数指针与间接调用、两类变参、切片返回、callback 和 `@[noreturn]`；ABI 元数据须进入函数类型、
模块接口和缓存版本。ARM64 HFA 留在 F1。
