# LLVM LL7-S2：SysV C `_Bool` 标量边界

日期：2026-10-17

## 实现

- 固定参数 Linux/x86_64 System V C ABI 支持 `_Bool` 参数和返回值，LLVM 函数签名与调用点发射
  `i1 zeroext`。
- YH 内部 bool 继续使用 i8 字节。YH 调用 C 时以 `icmp ne i8 ..., 0` 规范化为 i1；C 调用 YH 时
  以 `zext i1 ... to i8` 恢复源级字节；YH 返回 C `_Bool` 时也按非零值归一成 i1。
- C 返回的 i1 通过 `zext` 回到 YH bool 字节。新增非规范返回值 `2` 的探针，避免把“非零为真”
  错误实现成截低位。
- 新增 `tests/modules/projects/llvmabibool/`，单独以 LLVM O0/O2 构建；原 `llvmabi` 项目仍由
  常规模块项目门通过默认后端运行，避免把 LLVM 专属 C ABI 预期套到旧后端。

## 验证

WSL Ubuntu/x86_64，使用 `SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent` 和仓库交叉工具路径：

- `make`：通过。
- `python3 tests/selfhost/llvm-abi.py --compiler-path ./yh`：通过；clang 21.1.8 oracle 确认
  `i1 zeroext`，单文件与跨模块项目在 O0/O2 下均通过 LLVM verifier、优化、C 链接和双向运行。
- `make test`：语法正例 78/78、反例 42/42；运行/失败/仅编译语料 181/181、131/131、8/8，
  总计 320/320。
- `make selfhost-native`：通过；cc3→cc4 固定点 24 项一致、自解析 94 个源文件、模块 18/18、
  项目 103/103；scratch isolation、运行时内存、命令、文件系统、链接缓存门均通过。
- 入库 Linux/arm64 种子哈希保持
  `073282e9f1f773f162ccf9674a86f357e3bd6c9b74ccb65fe613968566916ccd`；未执行 `make seed`。

## 后续

LL7 继续处理 yh-llvm-v1 副本/结果缓冲 ABI、聚合分类、函数指针/回调、变参 metadata、切片返回和
`@[noreturn]`。裸 C 变参仍按现有 FFI 范围暂缓；ARM64 HFA 留给 F1。
