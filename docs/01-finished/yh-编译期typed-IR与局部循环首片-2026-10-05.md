# yh 编译期 typed IR 与局部循环首片

日期：2026-10-05。状态：**首条 typed IR 执行切片完成；CT3 总体仍在实施**。

## 交付内容

- `@[comptime]` 函数在全局初始化前完成一次前端解析与类型检查。单文件入口和模块
  worker 都把表达式、语句、控制流边及稳定局部绑定复制到 `compiler/comptime/` 自有 arena。
- typed 执行器支持整数/布尔表达式、短路、嵌套 `$g(...)`、标量局部声明和直接赋值、
  普通 `if/else`、条件 `for`、`break/continue/return`。调用树共用 100000 步上限，
  递归继续受 64 层调用帧上限保护。
- 新增单文件 `tests/yh-run/run/68-comptime-local-loop.yh`，以及
  `tests/modules/projects/comptimelocal/` 的跨文件局部循环回归。

## 范围边界

这是 typed IR 首片，不代表完整 CT3 完成。诊断执行、结构化 `$if/$for`、for-in、一般
左值、聚合值和剩余 AST 节点仍由兼容 token 执行器处理或暂不支持。后续按
[typed IR 执行器方案](../02-plan/yh-编译期typed-IR与函数执行器实施方案.md)逐类迁移，
并为每种行为补充 `.yh` 正反例。

## 验证

- `make` 成功。
- `make test`：ANTLR 正例 71/71、反例 44/44；运行语料 149/149。
- `python3 tests/modules/build-check.py --compiler-path ./yh`：80/80。
- `make selfhost-native`：两代模块产物 14 项固定点一致；自解析 62 个源文件；运行语料
  149/149；模块语法 17/17；项目验收 80/80；其他自举探针全部通过。
- 全绿后执行 `make seed`，再从滚动种子冷编并核对 `bin/yh.sha256`。
