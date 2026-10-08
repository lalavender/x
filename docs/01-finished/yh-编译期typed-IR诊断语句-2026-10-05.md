# yh 编译期 typed IR 诊断语句

日期：2026-10-05。状态：**typed IR 支持的函数已迁移诊断语句；完整 CT3 仍在实施**。

## 交付内容

- 前端把诊断类别写入编译期语句节点，并将 `$assert` 条件显式关联到已类型检查的表达式边。
- `compiler/comptime/ct_ir.yh` 在执行 `@[comptime]` typed IR 时处理 `$assert`、
  `$compile_error`、`$compile_warn`，从函数 token/源码快照取得调用位置和字符串消息。
  断言读取当前调用帧的局部值；错误和警告只在控制流实际到达语句时发出。
- 新增 `run/69-comptime-typed-diagnostics.yh`、`fail/92-comptime-typed-assert.yh`，
  并在 `comptimelocal` 多文件项目加入 typed 局部值断言。

## 范围边界

完整 typed IR 函数走新诊断执行路径；尚未迁入的 AST 子类仍使整个函数使用兼容 token
执行器。结构化 `$if/$for` typed 节点、for-in、一般左值、聚合值、调用链和跨模块正文
仍未完成。旧执行器会随未迁移形式保留，不把它当作 typed 诊断实现。

## 验证

- `make` 成功；定向 `run/69` 和 `fail/92` 通过 2/2；模块项目验收 80/80。
- `make test`：ANTLR 正例 71/71、反例 44/44；语义语料 151/151。
- `make selfhost-native`：两代模块产物 14 项固定点一致、自解析 62 个源文件、模块语法
  17/17、项目验收 80/80，其他探针全部通过。
- 全绿后滚动 `bin/yh`，再冷编与校验种子哈希。
