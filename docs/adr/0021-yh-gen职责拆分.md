# ADR-0021：`gen` 职责拆分——新增 support/token，语义分析全部归 `check`

日期：2026-11-06。状态：**已实施完成**（GEN0–GEN4 与 F2/F4 全部落地；`gen` 模块已删除，
完成记录见 [finish-F4](../01-finished/finish-F4-comptime纯执行器-2026-11-06.md)）。

关联：[ADR-0007](0007-yh编译器使用源码模块.md)（源码模块）、
[ADR-0009](0009-yh采用check与IR及早期并行.md)（check/IR/并行）、
[ADR-0020](0020-yh对象粒度停在模块级.md)（对象粒度）。
前置方案：[todo](../todo.md) 的 F0–F7（前端两遍化）。
实施计划已随完成归档：[finish-F4](../01-finished/finish-F4-comptime纯执行器-2026-11-06.md)（含 GEN3 逐项核对与 GEN4 字段归属表）。

## 背景

2026-11-06 复测（`python3 tools/arch-check.py`）：

| 事实 | 数值 | 影响 |
| --- | --- | --- |
| 模块 / 文件 / 行 | 17 / 158 / 59,815 | `gen` 一个模块 5,804 行 |
| `gen` 导出面 | 183 `pub fn` + 164 `pub const` + 21 `pub struct` | 外部模块按 `gen.` 直接消费，无窄接口 |
| `gen` 被依赖 | 15/17 模块 `import gen` | 唯一没有 import 的依赖根之一（另一个是 `ir`） |
| `TaskCtx` | 189 字段；427 处 `task()` 调用、63 个文件引用 | 状态与阶段强耦合 |
| 跨模块访问集中度 | `c_pos` 330、`np_data` 281、`t_types` 422、`c_syms` 354、`c_src` 166、`stats()` 132 | 拆状态是主要成本，不是拆文件 |

用户 2026-11-06 明确：**不要为每类职责都新建模块，优先复用现有模块；语义分析
全部归 `check`，不建 `sema`；`token` 从 GEN1 开始；`builtin` 保留内置函数和
内置类型；不新设 `hir` 模块。**

## 决定

### 1. 只新增两个模块

```text
新增：support（L0 基础内核，含共享数据层）  token（L0.5 词法/语法词汇与游标）
复用：lex  parse  ast  check  comptime  lower  ir  backend  link  proj  cache
      builtin  testkit  build  cmdline  cmd
不设：sema  diag  target  state  hir
已删除：gen（GEN4 后由 support/token/check 承接）
```

| 模块 | 职责 | 依赖 |
| --- | --- | --- |
| `support` | 缓冲/写出/分配、名字池、源读取、统计、宿主平台（clock/console/argv）、**诊断**（`fail`/`fail_path`/`err_lc`/`warn_lc`）、**目标身份/数据模型/`TargetCfg`/`ABI_YH`/`ABI_C`** | 无 |
| `token` | `TK_*`/`TOK_*`/`ATTR_*`/`Tok`/`PDecl`、token 数组与游标（`err_tok` 随后续诊断迁移） | `support` |
| `check` | **全部语义分析**：类型/符号/枚举/静态数据/常量折叠/布局/C ABI 分类/名字解析 + `resolve → expand → full` + `CheckedModule`/HIR 契约 | `ast`, `comptime`, `token`, `support`, `proj`（快照键可含 `ir`/`cache`） |
| `comptime` | **纯 CT IR 执行器**：执行 check 构造的 CT IR，不持有类型规则/不 import `check` | `support`, `token`, `proj` |

`diag` 并入 `support`（`fail` 与 `err_lc` 同属基础层，避免 `support↔diag` 环）；
`target` 并入 `support`（目标身份/数据模型是基础数据，`proj` 只存 `TargetCfg`
实例）；`sema` 不设，语义模型/规则/分析全部在 `check`；`state` 不设；`hir` 不设。

### 2. 目标依赖矩阵

```text
support  → （无）
ir       → （无）
token    → support
cache    → support, token, hash
lex      → support, token
cmdline  → support, libs
proj     → support, token
ast      → support, token, proj, comptime
comptime → support, token
check    → support, ir, token, cache, proj, ast, comptime
builtin  → support, check
parse    → support, ir, token, lex, proj, ast, comptime, check
lower    → support, ir, token, cache, proj, ast, check
backend  → support, ir
link     → support, proj, backend, hash
build    → support, ir, token, cache, lex, proj, ast, comptime, check, builtin, parse, lower, backend, link, hash, libs
testkit  → support, token, proj, ast, parse, link, build
main     → support, ir, lex, cmdline, proj, ast, comptime, check, builtin, parse, lower, backend, link, build, testkit
```

### 3. 所有权映射

| `gen` 内容 | 去向 | 判定 |
| --- | --- | --- |
| `TK_*`/`TOK_*`/`ATTR_*`/`Tok`/`PDecl` | `token`（`ATTR_*`/运算符码源头在 `support/model.yh`，`token` 转发） | 词法/语法共享词汇；`PDecl` 放 `token` 避免 `proj↔ast` 环 |
| token 数组/游标（`c_toks`/`c_pos` 等） | `token` | **GEN1 已搬**；`err_tok`/`sem_err` 随 `err_lc`/DiagCtx 迁移 |
| `CType`/`SField`/`TName`/`CSym`/`ModInfo`/`ImportEnt`/`ModNsEnt`/`PubAggDeferred` | **`support`（最终落点）** | 跨 parse/check/comptime 共用；`check` 会与 `comptime` 成环，故以 `support/model`、`support/file_scope` 承接 |
| `TY_*`/`SYM_*`/`F_*`/`CT_DIAG_*`/`Res` | **`support`** | 同上：跨层共享的语义枚举/标志/结果描述符 |
| `symbols.yh` | `support`（名字池）+ `check`（类型/符号/折叠/命名空间） | 名字池是通用 intern 池，`proj/link/build` 也用 |
| `sem_*.yh` | 全部 → `check`（F5 重写后迁） | 语义分析统一入口 |
| `tg_layout_struct` / `abi_c.yh` / `static_data.yh` | `check` | 布局/ABI/静态数据是语义规则 |
| `target.yh`/`target_info.yh` | `support` | 目标身份/数据模型/`TargetCfg`/ABI 常量 |
| `buffer.yh` 追加/写出/分配 | `support` | 纯字节基础设施 |
| `read_source`/`set_source_path`/名字池 | `support` | I/O、路径、intern |
| `fail`/`fail_path`/`err_lc`/`warn_lc` | `support` | 诊断与基础错误同层，避免环 |
| `clock.*`/`console.*`/`argv.*` | `support` | 宿主平台 |
| `front_stage.yh` | `check` | 受检阶段守卫 |
| `builtin` prelude/内置类型登记 | `builtin` 保留，`builtin → check, support` | 内置函数 + 内置类型登记表；`ty_register_builtins` 实现放 `builtin`，调 `check.ty_push` |
| `state.yh` 的 `TaskCtx` | `support.SourceCtx/PoolCtx/CompileStats/DiagCtx`、`token.TokenCtx`、`check.CheckCtx/SemaCtx`、`parse.ParseCtx`、`build.SessionCtx`、`lex.LexCtx` | 不整体搬 `build`/`proj`，不设万能 `state` |
| `GenState` | 删除 | 会话初始化按所有者分发 |

### 4. 关键修正

1. **只新增 2 个模块**：`support`/`token`；`sema` 不建，语义模型/规则/分析
   全部进 `check`；`diag`/`target` 并入 `support`；`state`/`hir` 不建。
2. **`check` 是唯一语义入口**：`CType/CSym/...`、常量折叠、布局、C ABI、
   静态数据、名字/类型检查都在 `check`；`lower`/`builtin` 直接 import `check`。
3. **`comptime` 必须是纯 CT IR 执行器**：只执行 check 构造的 CT IR；若它继续
   调用类型规则/读 `CSym`，就会形成 `check ↔ comptime` 环。F4 的
   “check.expand 构造 CT IR、comptime 执行” 是这条边的前提。
4. **`token` 从 GEN1 开始**：词汇、`PDecl`、token 数组/游标已迁；`err_tok`/
   `sem_err` 随诊断迁移；parse 的 `c_pos` 改写一次完成。
5. **`fail`/`err_lc` 同在 `support`**：基础层自足，不需要 `diag` 模块。
6. **`PDecl` 归 `token`**：`proj.PFile` 持有声明索引，放 `ast` 会形成 `proj↔ast` 环。
7. **`ABI_YH`/`ABI_C` 放 `support`**：`backend` 只需调用约定常量，不需要
   import 整个 `check`；`F_*`/`SYM_*` 等符号标志仍在 `check`。
8. **不建 `hir`**：`HIR` 指 `check` 产出的受检契约，不是新模块；`lower → check`。
9. **跨模块搬家不要求编译器自身 `.s.i` 字节一致**：模块身份/符号后缀会变；
   用固定点 + 全量语料等价，同模块文件搬家才要求字节一致。

### 5. `support` 的作用与所处步骤

`support` 不是流水线阶段，是 **L0 基础层**；所有阶段 import 它，但只在需要时
调用。它在编译流程中的位置：

| 步骤 | support 提供 | 调用方 |
| --- | --- | --- |
| 会话初始化 | `target_defaults`/`bind_cfg`、`source_init`/`stats_init`/`diag_init` | `cmd/common`、`build` worker |
| 读源（lex 前） | `read_source`/`set_source_path`、路径缓冲 | `build`、`proj`、`testkit` |
| 词法/语法/检查 | 名字池、`append_*`、`err_lc`/`fail`、`stats` | `lex`/`parse`/`check`/`comptime` |
| CT 展开 | 源/名字池/诊断/目标标记 | `check.expand`、`comptime` |
| lower/backend | 缓冲/写出、目标身份/ABI、统计 | `lower`、`backend` |
| 链接/构建 | 路径/名字池、`clock_ns`、`fail`、宿主检测 | `link`、`build`、`cache` |
| CLI | `append_*`/`cstr_eq`/`write_all` | `cmdline`、`cmd` |

一句话：**support 是“编译器自己的 libc + 目标描述 + 诊断底座”**，不是语义层；
它不持有类型/符号/分析状态。

### 6. `sema` 与 `HIR` 的去向

- **不建 `sema`**：`check` 就是语义分析模块。类型模型与纯规则放
  `check/base.yh`（含 `CheckedModule`/快照类型）、`check/types.yh`、`check/symbols.yh`、
  `check/fold.yh`、`check/layout.yh`、`check/cabi.yh`、
  `check/static.yh`；分析入口 `check/resolve.yh`、
  `check/expand.yh`、`check/full.yh`。
- **`comptime` 不 import `check`**：它只做 CT IR 执行；CT IR 的类型/布局/
  静态数据事实由 `check.expand` 构造并写入节点。若执行器需要类型规则、
  `CSym`/`static_data_*`/`em_*`/`sym_*`，说明 F4 还没完成。
- **`HIR` 不是模块**：它是 `check` 输出的受检契约（`CheckedModule` + AST 边表 +
  静态数据 + 目标身份），`lower` 消费；只有未来多消费者只要契约时才抽 `hir`。

### 7. 状态原则

- 每个上下文一个所有者；`proj` 保持只读项目模型，`build` 只持 `BuildCtx`，
  `link` 只持 `LinkCtx`。
- 新模块各用一个单例上下文：`g_support`（源/池/统计/诊断/目标）、`g_token`
  （token 数组/游标）；`check` 的 `CheckCtx`/`SemaCtx` 承载类型/符号/动作状态。
- `proj` 持有唯一 `TargetCfg` 存储，`support.bind_cfg()` 在 worker fork 前绑定；
  `support` 的 fallback 只服务单模块测试。
- 会话初始化顺序：`support.source_init → support.stats_init → support.diag_init
  → support.target_defaults → support.bind_cfg(proj.cfg()) → token.init →
  check.init → builtin.front_prepare → comptime.reset`。

### 8. 与前端两遍化、验收

- 本 ADR 只决定模块所有权/依赖边；AST/HIR/`CheckedModule` 字段与
  `check.resolve → expand → full` 契约由 F0 冻结。
- **GEN2 起与 F1–F5 合并**：`parse` 仍驱动 `sem_*` 时不能把语义搬进 `check`
  （会造 `parse → check` 临时环），必须先让 parse 纯语法。
- 同模块文件搬家：`.s`/`.s.i`/`.s.ct` 字节一致；跨模块搬家：固定点 + 全量语料
  等价，不比较编译器自身 `.s.i`。
- 每阶段 `just` + `just test` + `just selfhost-native`；门禁 `YH_CACHE=off`。
- `arch-check` 加单调预算：`gen` 的 `pub fn` 数、`import gen` 模块数、
  `TaskCtx` 字段数只减不增；`max_globals` 176（ast/parse 两个阶段单例）。

## 备选与被否决的方案

| 方案 | 结论 | 理由 |
| --- | --- | --- |
| 新建 `sema` 模块 | 否决 | 用户要求语义分析全部归 `check`；多一个模块只增加 import 面 |
| 新建 `diag`/`target` 模块 | 否决 | 基础层数据并入 `support` 即可 |
| 新建万能 `state` 模块 | 否决 | 只是把 `gen` 改名；字段访问不变 |
| 新建 `hir` 模块 | 暂不 | `check` 已拥有输出契约 |
| `comptime` 继续调用类型规则 | 否决 | 会与 `check` 成环；F4 必须把类型/布局事实放进 CT IR |
| 类型/符号放 `lex` | 否决 | `check`/`comptime` 会反向依赖词法阶段 |
| `TaskCtx` 整体搬 `build`/`proj` | 否决 | `parse → build` 成环；`proj` 只读模型被破坏 |
| `sem_*` 先搬 `check` | 否决 | `parse → check` 临时环；F2/F5 后再迁 |
| 把 `symbols.yh` 按 `pub` 数五拆 | 否决 | 按所有权分文件 |
| `fail` 单独放 `diag` | 否决 | 基础 I/O 需要 `fail`，会成环 |
| `PDecl` 归 `ast` | 否决 | `proj` 持有声明索引，`proj→ast` 与 `ast→proj` 成环 |
| `builtin` 并入 `check` | 否决 | 用户明确保留内置函数/内置类型登记表 |

## 后果

- 模块数 17 → **18**（新增 `support`/`token`，GEN4 删除 `gen`）；`check` 变大，但它是
  唯一语义入口，文件按 `check/base` … `check/full` 分。
- `comptime` 职责收窄为纯 CT IR 执行器；F4 必须完成类型/布局事实的传递。
- `lower`/`builtin` 直接 import `check`；`backend` 只 import `support` 的
  ABI/目标常量，不拉入整个 `check`。
- 过渡期临时边已在 GEN3/GEN4 全部删除：`gen` 模块不再存在，
  `parse/build/testkit/cmd → gen`、`ast/check/comptime → gen` 均已归零。
  现在 `comptime` 只依赖 `support/token`，值内核在 `support/value_kernel.yh`。
- 模块接口/缓存键会变；编译器内部模块不承诺 `.s.i` 跨版本兼容。
- `tests/modules/build-check.py` 的模块拷贝清单、`tools/compiler-tests.py` 的
  模块列表随阶段更新；fixture 的 `import gen` 改新模块。

## 开放问题

1. `check` 变大后是否接受“语义模型 + 语义分析 + CT 展开驱动”同模块？
   （用户已明确语义分析归 check；这是直接结果。）
2. `support` 同时装“基础工具 + 诊断 + 目标/ABI”是否接受？若希望更窄，只能
   重新拆出 `diag`/`target`，模块数会回升。
