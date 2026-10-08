# yh 编译期 typed `len` 实施方案

日期：2026-10-06。状态：**已交付**。

## 目标

让 `@[comptime]` typed IR 求值 `len(value)` 时读取当前调用帧中的数组/切片描述长度。固定数组读取其定长长度，切片读取当前视图长度，空切片结果为 0；不改变普通运行期 `len` 语义。

## 实施步骤

1. 新增单文件及同模块跨源文件 `.yh` 用例，覆盖固定整型数组、空切片、切片视图和结构体数组；先确认现有 typed IR 不能执行 `len`。
2. parse 捕获 `len` 的操作与子表达式，comptime 解释器读取受支持聚合值的 `CtAggregate.count`，返回 i32 长度；其他输入类型仍由 parser 类型检查拒绝。
3. 更新编译期设计、待办、计划及完成记录；运行 `make`、`make test`、`make selfhost-native`，通过后滚种子并冷编核对。

## 验收结果

- 新增 `tests/yh-run/run/87-comptime-len.yh`，期望输出 322，覆盖固定整型数组、结构体数组、共享切片视图和空切片。
- `tests/modules/projects/comptimelocal/src/main/lengths.yh` 和 `prog.yh` 覆盖跨源文件 typed 调用，断言值为 320。
- parser 在 AST 捕获期间保留 `len` 操作与实参节点；typed 求值验证数组/切片描述并读取当前帧长度，输出 i32。
- `make test`：语法正例 71/71、反例 44/44；运行 run 86/86、fail 89/89、pass 8/8，共 183/183。
- `make selfhost-native`：产物固定点 14/14、自解析 64 个源文件、模块 17/17、项目 82/82 及其余探针全部通过。
- `make seed` 后冷编 `make` 成功；种子 SHA-256：`d9675dcded01a675eba65e4c08e274523cbb2f258c076364cf5608332f988501`。
