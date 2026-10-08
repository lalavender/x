# yh 编译期 typed 函数内 `$for` 完成

日期：2026-10-05。状态：**已完成并滚动种子**。

## 交付

`@[comptime]` 函数内的区间 `$for` 现在在准备期进行名字/类型检查并捕获边界、循环绑定与循环体；
`comptime` 执行器读取本次调用帧中的边界，按左闭右开 `[lo..hi)` 逐轮执行。区间变量是只读 `i32`，
可以供嵌套循环和 typed `$if` 使用。空区间不执行循环体；单区间最多 1024 轮，循环树仍共享已有的
100000 步预算。普通函数中的 `$for` 保持常量静态展开，顶层 `$for` 仍拒绝。

解析接缝位于 `compiler/parse/parse_comptime.yh` 与 `parse_stmt.yh`；执行逻辑位于
`compiler/comptime/ct_ir.yh`。模块项目路径复用已有的 pass2a 前 CT 函数准备和 typed IR 捕获。

## 测试与验证

- `tests/yh-run/run/71-comptime-typed-for.yh`：参数和局部边界、累加、空范围、嵌套 `$for`、外层迭代绑定、
  typed `$if`、未选分支诊断和恰好 1024 次的边界。
- `tests/yh-run/fail/94-comptime-typed-for-readonly.yh`：循环变量不可赋值。
- `tests/yh-run/fail/95-comptime-typed-for-budget.yh`：超过 1024 次的区间被拒绝。
- `tests/modules/projects/comptimelocal/`：跨文件编译期函数动态区间调用。
- `make test`：语法正例 71/71、反例 44/44，运行语义 156/156。
- 模块项目验收 80/80；`make selfhost-native` 固定点 14 项一致、自解析 62 个文件、模块语法 17/17、
  项目 80/80，其余探针均通过。
- `make seed`、滚动种子冷编与 SHA-256 检查通过；新种子摘要：
  `13e3505c907bd6077e460e154a243c70fc20d196357bde51256c5aeeb8f0927e`。
