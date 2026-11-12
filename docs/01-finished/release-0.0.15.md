# 0.0.15 — 多线程标准库 sync、模块拆分、前端 S4 收口

正式版。本版在 0.0.14 基础上加入多线程标准库 `libs/sync`（Darwin/Linux）、
`errors` 叶子模块与 `types`/`table` 拆分、`support` 收缩为单文件，并把前端
S4 切片做完：类型语法/长度语义外置、影子门、CT 展开下沉（`parse→comptime = 0`）、
表达式语义外置（表达式内联 47 → 0）、语句语义外置（`parse_stmt` 直调内核 9 → 0）。
种子链：0.0.14 → 0.0.15（由 0.0.14 正式版种子构建）。

## 主要内容

**1. 多线程标准库 `libs/sync`**

- 纯标准库实现，不改语言/语法/检查器/IR；线程入口固定 `fn(*void) void`。
- Darwin（pthread）与 Linux（libc pthread）已交付：`Thread`/`Mutex`/`Cond`/
  `WaitGroup`/`Once` + 库内测试（O0/O2、重复并发压力 0 失败）。
- 新增标准库专项 CI `stdlib.yml`（四端跑 `test-stdlib-*`），justfile 增加
  `test-sync-stress`、`test-stdlib-unix`、`test-stdlib-windows`。
- 未做：Windows（`CreateThread`/SRW）、`Chan`、`RwLock`/原子/TSan——见 `docs/todo.md`。

**2. 模块拆分：`errors` 叶子、`types`/`table` 从 `support` 拆出**

- 诊断基座迁入 `errors`，`support` 的委托转发删除，驱动层后端链接各模块直连 `errors`。
- 类型模型（`TY_*`/`CType`/`SField`/`TName`）独立为 `types`；语义存储与值规则
  （`ModelStore`/`sym_*`/`vk_*`/`data_str_*`）独立为 `table`（ADR-0027）。
- `support` 收缩为单文件（1,279 行），平台变体迁 `cmd`（console/argv，ADR-0025）。
- 依赖方向守卫随拆分更新（`front-coupling` 锁定 `types` 无依赖、`table` 不依赖上层）。

**3. 前端 S4 收口（parse 纯化）**

- 类型语法外置：`parse_type` 只构造 `ast.AstType`，类型表与数组长度布局归
  `check/type_syntax.yh`；`sizeof` 歧义判定走 `check` 查表。
- 影子门（`YH_AST_FULL_CHECK/FILL`）覆盖字面量/一元/二元/下标/切片/字段/调用/聚合，
  并有回填通道；新增 `YH_AST_FULL_STATS=1` 覆盖度量。
- **S4-3 CT 展开下沉**：`parse→comptime = 0`，全部交互经 `check/ct_gate.yh` 门面
  （布局驱动、依赖发现、枚举元信息、展开簿记、全局聚合建模、`$`-调用求值）。
- **S4-4 表达式语义外置**：8 个二元层、一元层、postfix 链、调用 ABI、字面量/名字/
  `sizeof`、聚合字段共 47 处内联语义改走 `check` 的 `sem_eval_*` 入口；
  守卫 `PARSE_CHECK_EXPR_INLINE_BUDGET = 0`。
- **S4-2 语句侧**：`parse_stmt` 的 9 处语句语义内核（break/continue/goto/标签/赋值/
  return/诊断/局部绑定）改走 `check/stmt_eval.yh`；`parse_stmt` 直调内核 = 0。
- 形态说明：驱动入口分「节点模式」（操作数取子节点注解）与「仅算子模式」
  （输入是现场事实，如 token 文本、`c_args`、循环深度、`ct_diag_*`、`c_ret_agg`）。
  严格「parse 只产语法节点、无算子模式」已决策不做，理由见 `docs/todo.md`
  「设计决定不做」。

**4. 结构整理**

- `check/full.yh` 1,159 → 892 行：驱动入口拆到 `check/eval.yh`（281 行），
  语句入口在 `check/stmt_eval.yh`（81 行）；影子门与重算内核留在 `full.yh`。

**5. 修复**

- 函数/检查切片缓存键未包含数据标签布局，导致字符串标签重排后复用旧切片
  （`fix(cache): 函数/检查切片按数据标签布局失效`）。
- 构建侧移除误带入的 `libs.list` 未使用导入。

## 守卫与门禁

- `front-coupling`：`check=162`、`comptime=0`、`表达式内联=0`、`eval=45`（4/4 通过）。
- `just test`：ANTLR 层 + 语法语料 + 运行语料 + 模块/缓存/CLI/代码统计/代码流 +
  `front-coupling`/`front-syntax`/`front-full` 全通过。
- `just front-shadow`：全语料 + `libs` 全量影子门通过。
- `just selfhost-native`：两代固定点一致、`project cases` 125/125。

具体数字以本文件「发布验收」段为准（发布后按实际二进制回填）。

## 已知限制

- 字符串字面量仍是**可写的私有数据**，多模块各存一份；只读化与去重需要类型级
  `*const`，方案未定。记录见
  [问题记录](../02-plan/yh-字符串字面量只读与去重-2026-11-11.md)。
- `const` 聚合的只读只到绑定层，指针别名可写穿（同根因，同上文档 §10）。
- 编译器 CT 字符串池固定 64 段（单编译单元上限）。
- 前端 S4 的技术债 S4-6…S4-10 见 `docs/todo.md`。

## 发布验收

待填：四端 CI 结果、资产清单、用发布二进制跑的 `just`/`just test`/
`just selfhost-native` 结果。
