# ADR-0028：`static_data` 并入 `table`

日期：2026-11-11。状态：**已实施**。

关联：[ADR-0027](0027-yh-table模块.md)（table 集中语义存储）、
[ADR-0024](0024-yh-support再收缩.md)（support 再收缩）。

## 背景

静态数据目录（`StaticDataObject`/`StaticDataReloc` + 8 个 `static_data_*` 操作）
是编译期物化的静态字节目录（字符串 backing、聚合常量、全局初始化数据及重定位）。
拆在 support 两处：存储单例在 `support/static_data.yh`、结构与操作在 `support/api.yh`。
消费方 parse（写）、comptime（写）、check（capture 深拷贝）、lower（读快照）
全在 table 之上，且这些操作**不读 `ms()`**，是干净可搬的存储簇。

## 决定

把静态数据簇整体并入 `table`（与 ADR-0027 的语义存储集中一致）：

- 迁入 `table/api.yh`：`StaticDataObject`/`StaticDataReloc` 结构、8 个
  `static_data_*` 函数、目录单例 `static_objects`/`static_object_n`/`_cap`、
  `STATIC_DATA_LIMIT`、`static_data_drop`（原 `support/static_data.yh` 整体并入后删除）。
- 消费方（parse/comptime/check/lower）改 `support.static_data_* → table.static_data_*`、
  `support.StaticData* → table.StaticData*`，补 `import table`。
- 复位：原 `state_init`/`session_reset` 里的 `static_data_reset()` 改由
  `check.sem_init_tables()` 调 `table.static_data_reset()`（support 不 import table）。
- support 删 `static_data.yh` 与相关孤儿注释，残留仅缓冲/池/源/会话/目标/`FrontCtx`/
  `Res`/`ModuleSym`。

## 后果

- `table`：3 文件 1,278 → **1,316 行**；`support`：1,552 → **1,345 行**，仅剩
  `api`/`base`/`task_ctx` 三文件。
- 依赖边不变（table 已依赖 types/support/errors；parse/comptime/check/lower 已依赖 table）。
- `.s.i`/`.s.ct`/静态数据编码值不变；用户程序产物应逐字节一致。

## 后续（同日收尾）

`support/base.yh`（`let g_support`）与 `support/task_ctx.yh`（`let g_front`）只是
单例占位空壳（结构体早已在 api.yh），已把两个 `let` 并入 `support/api.yh` 的对应
结构体之后并删除文件；support 现为单文件 `api.yh`（1,300 行）。

## 未随迁

`FrontCtx`（74 字段，parse/check/ast/token 跨层共读写）整体搬任一边都成环，
留给 S4 字段拆分；`Res` 是表达式结果描述符而非存储表，留 support。