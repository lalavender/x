# yh 编译期 typed 整型数组/切片 for-in 完成记录

日期：2026-10-05

## 结果

`@[comptime]` 函数的 typed IR 现在可以在本次调用帧内创建并保存整型数组/切片字面量，普通 `for-in` 可读取元素及可选的零起始下标。空切片迭代零次；循环沿用共享执行步数限制和现有 `break/continue/return` 流。聚合存储由创建它的调用帧统一释放。

声明解释会先定位 `=` 对应的初始化表达式，因此固定数组类型中的 `[N]` 长度表达式不会被误当成变量初值。数组参数链以迭代方式计数和填充，避免大型字面量耗尽递归栈。当前边界限于函数帧内整型字面量初始化及只读迭代，不支持聚合参数/返回、索引读写、结构体/联合体或浮点元素。

## 回归与验证

新增 `tests/yh-run/run/73-comptime-forin-array.yh`，覆盖固定数组累加、切片下标/元素绑定与空切片；`tests/modules/projects/comptimelocal/` 增加跨文件固定数组求和，确认模块 worker 的准备和执行路径一致。

验证通过：

- `make test`：ANTLR 正例 71/71、反例 44/44，运行语料 160/160（run 72/72、fail 80/80、pass 8/8）。
- `make selfhost-native`：14 个模块产物固定点一致，自解析 62 个源文件，模块语法 17/17，项目验收 80/80，其余探针全绿。
- `make seed` 后冷编 `make` 通过；`shasum -a 256 -c yh.sha256` 显示 `bin/yh: OK`；`git diff --check` 通过。

新种子 SHA-256：`d5e022bcfdf5db7fd3cba122ece8f2cb74a7d0ec5735a2fbddcccea1561478ce`。

实现位于 `compiler/comptime/ct_00_model.yh` 与 `compiler/comptime/ct_ir.yh`；方案见[typed 整型聚合与 for-in](../02-plan/yh-编译期typed整型聚合与for-in方案.md)。完整 typed 执行器仍有索引读写、其他聚合与一般左值等后续工作。
