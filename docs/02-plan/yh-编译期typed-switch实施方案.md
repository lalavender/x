# yh 编译期 typed `switch` 实施方案

日期：2026-10-05。状态：**实现完成；2026-10-06 自举项目门后续阻塞已修复**。

## 目标

让 `@[comptime]` 函数执行普通整数 `switch`，复用 parser 已完成类型检查的控制表达式、case 常量和 case 块，不在 `compiler/comptime/` 重做语法解析。

## 语义边界

- 一个 case 可有多个逗号分隔的整数常量；只执行首个匹配 case，case 间不 fallthrough。
- 无匹配时执行 default；没有 default 时正常继续后续语句。
- case 块中的 `return`、`break`、`continue` 沿现有 typed IR flow 传播。当前 yh 语法只允许循环内的 break/continue，因此 switch 不另行捕获这两种 flow。
- 控制表达式和 case 表达式沿用 parser 的整数类型检查及 comptime 表达式求值；暂不增加字符串/范围 case。

## 实施步骤与验证

1. 新增 `tests/yh-run/run/80-comptime-typed-switch.yh`，确认旧 typed 执行器报出“不支持”的诊断。
2. 在 `compiler/comptime/ct_ir.yh` 将 switch/case 纳入 typed IR 支持范围，执行唯一匹配分支、无匹配 default 与原样 flow 传播。
3. 更新 `docs/todo.md`、`docs/finish.md`、编译期设计文档、`compiler/README.md` 和运行语料说明。
4. 首次专项语料、`make` 与 `make test` 通过；后续为满足 C ABI 项目的 SSA 覆盖断言，实现整数 cast 与公共整数类型提升。当前 `make test` 为 173/173，`make selfhost-native` 固定点、自解析、运行、模块 17/17 和项目 82/82 全绿；没有继续滚种子。

## 成功标准

- `switch` case 匹配、default 与无 fallthrough 的执行结果正确。
- `return` 离开整个编译期函数；`continue` 仍作用于外层编译期循环。
- 非 comptime 普通 switch 语义不变；所有新逻辑位于 `compiler/comptime/`，parser/语法无额外改动。
