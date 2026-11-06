# ADR-0021：`gen` 职责拆分与模块所有权（token/sema/check/support/target）

日期：2026-11-06。状态：**提议（重新分析）；GEN0–GEN2 可在确认后开工，GEN3/GEN4 以 F5 为前置**。

关联：[ADR-0007](0007-yh编译器使用源码模块.md)（源码模块）、
[ADR-0009](0009-yh采用check与IR及早期并行.md)（check/IR/并行）、
[ADR-0020](0020-yh对象粒度停在模块级.md)（对象粒度）。
前置方案：[todo](../todo.md) 的 F0–F7（前端两遍化）。
实施计划：[yh-gen职责拆分实施方案-2026-11-06](../02-plan/yh-gen职责拆分实施方案-2026-11-06.md)。

## 背景

2026-11-06 复测（`python3 tools/arch-check.py`）：

| 事实 | 数值 | 影响 |
| --- | --- | --- |
| 模块 / 文件 / 行 | 17 / 158 / 59,815 | `gen` 一个模块 5,804 行 |
| `gen` 导出面 | 183 `pub fn` + 164 `pub const` + 21 `pub struct` | 外部模块按 `gen.` 直接消费，无窄接口 |
| `gen` 被依赖 | 15/17 模块 `import gen` | 唯一没有 import 的依赖根之一（另一个是 `ir`） |
| `TaskCtx` | 189 字段；427 处 `task()` 调用、63 个文件引用 | 状态与阶段强耦合 |
| 跨模块访问集中度 | `c_pos` 330、`np_data` 281、`t_types` 422、`c_syms` 354、`c_src` 166、`stats()` 132 | 拆状态是主要成本，不是拆文件 |

`gen` 不是“一个模块”，而是六类职责共用一个名字：词法/语法词汇、语义模型、
语义动作、每任务状态、基础设施（缓冲/宿主）、目标与 ABI。它同时是依赖根，
任何模块都能 import 它，导致词法、诊断、项目和目标都被迫穿过同一个名字。
2026-11-06 的前端两遍化决定（`parse` 纯语法、`check` 收语义）进一步要求
`gen` 不再承担语义动作与语义模型的公共入口。

## 决定

### 1. 拆分目标与分层

拆成 `support`/`diag`/`target`/`token`/`sema`/`check` 六条线；**不设 `state`
模块**。状态跟随所有者，以阶段上下文或模块内单例存在：

```text
L0 支撑    support（缓冲/宿主/名字池/统计/源读取）
           diag（带源码位置的诊断）      token（token 词汇/声明索引）
           target（目标身份/数据模型/目标配置）
L1 语义    sema（类型/符号/常量折叠/布局/ABI/静态数据）
L2 前端    lex  parse  ast  check（resolve/expand/full）  comptime（CT 求值）
L1.5 变换  lower（消费 check/HIR → IR）
L1 中端    ir（不依赖任何 yh 模块）
L1 后端    backend（LLVM 描述）  link（工具链调用）
L3 驱动    build  testkit  proj
L4 入口    cmd（一命令一文件，导出面只有 main）
```

目标允许边（每阶段只允许收紧，不允许新增表中没有的边）：

```text
support  → （无）
ir       → （无）
token    → （无）
target   → （无）
diag     → support
cache    → support, token, target, hash
lex      → support, diag, token
proj     → support, target, token
sema     → support, diag, target, token
comptime → sema, support, diag, proj, token
ast      → token, support                       （F1 后；过渡期含 sema/comptime/proj/ir）
check    → ast, sema, comptime, token, target, diag, support, proj
           （快照/切片键仍在 check 时可含 ir/cache）
parse    → token, ast, lex, support, diag
           （F2 后收紧；过渡期含 gen/comptime/ir/sema/proj）
lower    → check/HIR, ast, ir, sema, target, token, support, proj, cache
backend  → ir, sema, target, support
builtin  → sema, target
link     → target, support, proj, backend, hash
build    → 下方全部 + gen（GEN3 前；GEN4 删除）
testkit  → build, parse, link, proj, sema, support, token
cmdline  → support, libs
cmd      → 全部（入口唯一例外）
```

### 2. 所有权映射

| `gen` 内容 | 去向 | 判定 |
| --- | --- | --- |
| `TK_*`/`TOK_*`/`Tok` | `token` | 词法/语法共享词汇；`token` 不依赖任何模块 |
| `PDecl` | `token` | token 区间 + 声明种类；**不放 `ast`**，否则 `proj→ast` 与 `ast→proj` 成环 |
| `is_assign_op`/`hexval` | `token` / `support` | 前者是 token 区间判定；后者是通用字节工具 |
| `CType`/`SField`/`TName`/`CSym`/`ModInfo`/`ImportEnt`/`ModNsEnt`/`PubAggDeferred` | `sema` | 语义模型 |
| `TY_*`/`SYM_*`/`F_*`/`ABI_*`/`CT_DIAG_*` | `sema` | 语义枚举与标志 |
| `symbols.yh` | 拆到 `support`（名字池）+ `sema`（类型/符号/折叠/命名空间） | 名字池是通用 intern 池，`proj/link/build` 也用；不能放 `sema` |
| `Res` | `sema`（过渡）→ 删除/`check` 内部 | `ast`、`comptime` 在 F1/F5 前仍需它 |
| `sem_*.yh` | **纯类型规则** → `sema`；**语义动作** → `check`（F5 后） | 不能整包搬 `check`；`comptime` 依赖类型规则 |
| `CType`/`SField` 布局（`tg_layout_struct`） | `sema` | 布局是类型规则，不是目标身份 |
| `abi_c.yh` | `sema` | C ABI 分类需要 `CType`；`target` 不能反向依赖 `sema` |
| `static_data.yh` | `sema` | 静态数据对象是语义数据；`ast/check/comptime/lower/parse` 消费 |
| `target.yh`/`target_info.yh` | `target`（身份/数据模型/配置） | 布局函数留 `sema` |
| `TargetCfg` | 类型/默认值/绑定点在 `target`；**存储仍在 `proj`** | `proj` 是唯一存储；`target` 只持一个绑定指针 |
| `clock.*`/`console.*`/`argv.*` | `support` | 宿主平台层；后续可换 `libs/os`/`libs/time` |
| `buffer.yh` 的追加/写出/分配 | `support` | 纯字节基础设施 |
| `read_source`/`set_source_path`/`fail`/`fail_path` | `support` | 无源码位置的 I/O 与致命错误 |
| `err_lc`/`warn_lc` | `diag` | 带源码位置的诊断渲染 |
| `err_tok`/`sem_err` | 暂留 `gen` → `check`（parse 用 `diag.err_at`） | 需要“当前 token”游标；`token` 保持纯词汇，不反向依赖 `diag` |
| `front_stage.yh` | `check` | 受检阶段的进入/退出守卫 |
| `builtin` prelude 登记 | `builtin` 保留，改 `builtin → sema` | 不并入 `sema`，保持 prelude 表独立 |
| `state.yh` 的 `TaskCtx` | 按簇拆到 `support.SourceCtx`/`support.PoolCtx`/`support.CompileStats`/`diag.DiagCtx`/`target`/`sema.SemaCtx`/`check.CheckCtx`/`parse.ParseCtx`/`build.SessionCtx` | 不整体搬 `build`/`proj`，不设万能 `state` |
| `GenState` | 删除 | 会话初始化按所有者分发 |

### 3. 三处关键修正（与旧 todo 映射不同）

1. **`fail`/`fail_path` 归 `support`，不归 `diag`**。`support.read_source`/`alloc`
   需要报告 I/O/内存错误；若 `fail` 在 `diag`，则 `support → diag` 与
   `diag → support`（路径/写出）成环。带位置的 `err_lc`/`warn_lc` 才归 `diag`。
2. **`PDecl` 归 `token`，不归 `ast`**。`proj.PFile` 持有声明索引，而 `ast`
   当前依赖 `proj`；`proj → ast` + `ast → proj` 会成环。`token` 是两者共同的下层。
3. **`TaskCtx` 不能等到其他阶段都完成后再一次性五拆**。`support`/`diag`/`sema`
   的函数需要各自的存储，叶子状态（源/池/统计/诊断）必须在相应模块落地时一起
   搬走；剩余的 parse/check 动作状态在 F5 重写后再拆，避免拆完又被删。

### 4. `sema` 的边界

- `sema` 只放**模型 + 纯规则**：类型表、符号/作用域、常量折叠、类型兼容/提升、
  布局、C ABI 分类、静态数据、枚举成员表、模块命名空间查询、字符串标签表。
- `sema` **不得** import `gen`/`proj`/`ast`/`parse`/`check`/`comptime`/`lower`。
  需要当前 token 位置时，由调用方写入 `SemaCtx` 的声明位置或显式传参；
  诊断经 `diag` 发出，不回调 parser。
- `comptime → sema`，`check → comptime`，**不得** `comptime → check`。
- `sem_*` 的语义动作（调用、赋值、控制流、字面量、声明）在 F5 前继续留
  `gen`；F5 后在原文件上重写/迁 `check`，不先做一次“搬家再重写”。

### 5. 状态原则

- 每个上下文只有一个所有者；`proj` 保持只读项目模型，`build` 只持
  `BuildCtx`/会话开关，`link` 只持 `LinkCtx`。
- 新模块用**一个单例上下文**承载自己的状态（`g_support`/`g_diag`/`g_target`/
  `g_sema`），不要每张表加一个模块级 `let`；`arch-check` 的 `max_globals`
  不得因拆分上升。
- 禁止把 189 字段的 `TaskCtx` 整体搬进 `build`/`proj`/新 `state` 模块；
  那只是把依赖根改名，拆分成本不会减少。
- 目标配置：`proj` 持有唯一 `TargetCfg` 存储，`target.bind_cfg()` 在 worker
  fork 前绑定一次；`target` 不保留第二份可写副本（未绑定时的 fallback 只服务
  单模块测试）。
- `state_init`/`sem_init_tables` 按所有者拆成 `support.source_init`、
  `support.stats_init`、`diag.init`、`target.defaults`、`sema.init`、
  `check.init`、`comptime.reset`，由入口按固定顺序调用。

### 6. 与前端两遍化的关系

- 本 ADR 只决定**模块所有权与依赖边**；`AST`/`HIR`/`CheckedModule` 的具体
  字段与 `check.resolve → expand → full` 契约由 F0 ADR 冻结。
- `CheckedModule` 契约默认随 `check` 走（生产者拥有输出契约），不新设
  `hir` 模块；若 F0 发现 `lower → check` 拉入过多依赖，再新 ADR 立 `hir`。
- **GEN3/GEN4 不得早于 F5**：`parse` 还在驱动 `sem_*` 时把 `sem_*` 搬进 `check`
  会制造 `parse → check` 临时环，且这些函数会被 F2–F5 重写，搬家是白做。

### 7. 验收口径

- 同模块内文件搬家：该模块 `.s`/`.s.i`/`.s.ct` 逐字节一致。
- 跨模块搬家：**不要求编译器自身 `.s.i` 逐字节一致**（模块身份/符号后缀会变）；
  以「旧/新编译器编译同一用户语料的产物与行为一致 + cc3/cc4 固定点 + 全量
  `tests/yh`/`tests/yh-run`/`tests/modules`」为准。
- 每阶段：`just` + `just test` + `just selfhost-native`；门禁默认 `YH_CACHE=off`。
- `arch-check` 增加单调预算：`gen` 的 `pub fn` 数、`import gen` 模块数、
  `TaskCtx` 字段数只减不增；新增模块的边必须先在 `ALLOWED` 中登记。

## 备选与被否决的方案

| 方案 | 结论 | 理由 |
| --- | --- | --- |
| 类型/符号放 `lex` | 否决 | `check`/`comptime` 会反向依赖词法阶段；`lex` 是变换不是模型 |
| 新建万能 `state` 模块装 `TaskCtx` | 否决 | 只是把 `gen` 改名成新的依赖根；390 处字段访问不变，最终仍要拆 |
| `TaskCtx` 整体搬 `build`/`proj` | 否决 | `parse → build` 成环；`proj` 只读模型被破坏 |
| `sem_*` 先整体搬 `check` | 否决 | `parse → check` 临时环；F5 会重写，搬家是重复劳动 |
| 把 `symbols.yh` 按 `pub` 数五拆 | 否决 | 类型表/符号表/折叠共享同一语义内核；按所有权分文件，不按导出行数 |
| `fail` 归 `diag` | 否决 | `support` 的 I/O 需要 `fail`，会与 `diag → support` 成环 |
| `PDecl` 归 `ast` | 否决 | `proj` 持有声明索引，`proj→ast` 与 `ast→proj` 成环 |
| 新设 `hir` 模块 | 暂缓 | 默认 `check` 拥有 `CheckedModule`；由 F0 决定是否值得多一层 |

## 后果

- `gen` 在 GEN2 后从“万能底座”缩成前端动作 + 残余 `TaskCtx`；GEN3/GEN4 后删除。
- `support`/`diag`/`target`/`token`/`sema` 成为窄接口；`cmdline`/`cache`/`link`/
  `proj`/`backend`/`lower`/`builtin` 在 GEN1/GEN2 先摆脱 `gen`。
- 过渡期允许并记录以下临时边，GEN3/GEN4 必须消失：
  `gen → sema/support/diag/target/token`、`ast → sema`（`Res`/快照）、
  `parse/lex/build/testkit/cmd → gen`。
- 模块接口与缓存键会变化；编译器内部模块不承诺 `.s.i` 跨版本兼容，构建缓存
  按新模块身份自然失效。
- `tests/modules/build-check.py` 的模块拷贝清单、`tools/compiler-tests.py` 的
  模块列表必须随阶段更新；否则 fixture 会因缺少新模块而失败。

## 开放问题（GEN0 前确认）

1. `CheckedModule` 契约：`check` 直接拥有，还是 F0 另立 `hir`？本 ADR 默认前者。
2. `builtin`：保留薄表（默认）还是并入 `sema`？（两者都不改变依赖方向。）
3. token 状态（`c_toks`/`c_pos`/`err_tok`）：GEN1 随 `token` 一起搬，还是等 F2/GEN4
   与 parse 重写一起搬？本 ADR 默认后者，避免 308 处 `c_pos` 被改两次。
4. `Res` 的最终形态：F5 删除，还是成为 HIR 的表达式结果节点？由 F0/F5 定。
5. `err_tok`/`sem_err` 最终放 `check`（语义动作）还是 `diag`（显式传入 `Tok`）？
   本 ADR 默认 `check`；两者都不让 `token` 反向依赖 `diag`。
