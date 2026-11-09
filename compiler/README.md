# compiler —— yh 自举编译器（.yh 源码）

> 0.0.3 起本目录是**主要开发编译器**（[ADR-0006](../docs/adr/0006-yh自举产物为主要开发编译器.md)、
> [ADR-0007](../docs/adr/0007-yh编译器使用源码模块.md)）：仓库已删除 C 版
> stage0 与 bootstrap，构建只依赖种子 `bin/yh-<平台>-<架构>`（上一版编译器二进制，
> 用 `just fetch-seed` 从 Release 下载，不入库）。
> 自举产物默认目标取编译器构建身份（qemu 下仍为进程架构），日常验证以
> `just selfhost-native` 为主门。

用 yh 语言写成的 yh 编译器。源码是 `project.toml` 项目（name = `yh`，
source = `.`；版本号以 [project.toml](project.toml) 的 `version` 与
`cmdline/cmdline.yh` 的 `YH_VERSION_TEXT` 为准，两处必须与发布 tag 一致），按
**support / token / gen / builtin / lex / parse / ast / check / comptime /
lower / ir / backend / link / build / proj / cache / testkit / cmdline / cmd** 组织。
**2026-11-06 GEN1+F1/F3 实测（`python3 tools/arch-check.py`）：十九个模块、
171 个 `.yh`、60,545 行、93 条依赖边**：`parse` 9,776 · `build` 8,062 ·
`lower` 5,998 · `comptime` 5,550 · `ir` 5,385 · `check` 5,224 · `link` 4,329 ·
`backend` 4,149 · `gen` 2,550 · `testkit` 1,619 · `proj` 1,467 · `ast` 1,368 ·
`support` 1,185 · `lex` 1,046 · `cache` 1,032 · `cmdline` 661 · `cmd` 502 ·
`token` 265 · `builtin` 173。

各层来历：`support/` 与 `token/` 是 2026-11-06 GEN1 自 `gen` 拆出的基础层
（缓冲/统计与 token 词汇/游标），`ast/` 是 2026-10-12 自 parse 拆出的 AST 阶段，`check/` 承担
AST 与快照的**只读一致性校验**（不是语义分析），`builtin/` 只放内置
（prelude）函数登记表，`ir`（目标隔离 SSA）与其它模块同为根项目普通模块，
`build/` 是 2026-10-24 A2c 自 `cmd/` 拆出的构建引擎（调度、模块发射、缓存、
LLVM 流水线），`proj/` 是项目模型/扫描/产物路径，`link/` 是工具链调用层，
`testkit/` 是语言内测试执行器，`lower/` 是 2026-10-25 B3-2 自 `ast/` 拆出的
lowering 阶段（`CheckedModule → IRModule`）。`cmd/` 只剩参数映射与调用面，
一命令一文件，469 行、占 0.8%。

**目录职责、依赖规则、阶段契约与迁移路线以
[`docs/03-design/yh-架构设计.md`](../docs/03-design/yh-架构设计.md) 为唯一真源**；
本文只保留构建/验证命令与自举子集说明。模块导出面按「只有别的模块真的用到才
`pub`」维护（2026-10-12 两轮：`pub` 声明 1048 → 585，接口 `.s.i` 63,160 →
36,633 字节）：仅模块内使用的 `fn`/`const`/类型不写 `pub`；私有类型不得出现在
本模块的 `pub` 签名、`pub` 字段或 `pub` 别名里；入口模块 `cmd/` 只保留 `main`
为 `pub`。规则见 [模块私有类型设计](../docs/03-design/yh-模块私有类型设计.md)。

**未使用函数是编译错误（UF1，2026-10-27）**：本模块声明、既没 `pub` 也没
`extern`/C ABI 的函数定义，如果整个模块的源码里除了声明名本身没有任何同名
标识符，`build`/`run`/`test` 与单文件编译都直接报
「函数未使用（本模块没有任何引用；请删除或改为 pub）」。实现是
`build/unused_function.yh` 在 pass1 之后、pass2 之前对模块全部文件做一次
token 扫描（按名字，不按解析期引用标记）：函数级 check 切片命中时正文不会
重新解析、`$f(...)` 编译期调用在普通函数体里直接折成常量、生产构建不解析
`test` 正文，三者都会让「引用标记」在增量构建里缺项，而 token 扫描只会漏报
（同名局部变量遮蔽、递归自引用算作已使用），不会把合法程序判死。`pub`（含
入口 `main` 与 `test` 生成符号）与 `@[extern]` 的 C ABI 回调目标天然跳过。

```
bin/yh-<平台>-<架构>（Release 种子）──yh build──▶ yh ──自编──▶ yh'（固定点：模块 .s/.s.i 逐字节相同）
```

## 构建与验证

```bash
just fetch-seed         # 首次：从 Release 下载本平台种子到 bin/
just                    # 用 bin/yh-<平台>-<架构> 冷编本目录项目，产出仓库根 yh
just test               # 三层回归：ANTLR 语法 + 编译器语法模式 + 运行语义
just selfhost-native    # 本机主门：两代固定点 + 自解析 + 全量语料 + 模块/项目验收
just code-stats         # 统计 compiler/ 下 yh 源码规模
just seed               # 滚种子（仅在 test 与 selfhost-native 全绿后执行）
```

`make` 的产物形态随宿主（Darwin → Mach-O arm64，Linux → ELF）。最终链接
由内嵌 lld/平台驱动完成；编译器自举闭包由 `just bootstrap` 准备。普通项目
可在 `project.toml` 的 `[link]` 中声明平台库文件，由 `yh build` 自动链入。
可直接用于编译 `.yh` 程序与跑语料：

```bash
python3 tests/yh-run/check.py --compiler $PWD/../yh
```

`just selfhost-native` 由 `tests/selfhost/bootstrap/native-selfhost.py` 执行本机全套
自举门（滚动自举，无 stage0；种子 = `just fetch-seed` 取得的 `bin/yh-<平台>-<架构>`）：

    bin/yh-<平台>-<架构> build compiler/  → cc2（冷编）
    cc2     build compiler/ → cc3（冷编）
    cc3     build compiler/ → cc4（冷编，固定点对比）

门：①固定点——cc3/cc4 全部模块 `.s`/`.s.i` 逐字节一致；②cc4 自解析
compiler/ 全部源文件；③cc4 语法语料（`tests/yh` 正例全过、反例全拒）；
④cc4 运行语料（`tests/yh-run` 全量 run/fail/pass，2026-10-25 实测 360 个
`.yh` 用例文件）；⑤模块语料（`tests/modules/check.py`）；⑥项目验收
（`tests/modules/build-check.py`，2026-10-24 记录 126 例），以及
`tests/selfhost/cache/llvm-function-cache.py` 的函数级缓存矩阵。滚种子前必须全绿。

## 内建测试

`support/buffer.yh`、`token/op.yh`、`check/checked_model.yh`、`lex/layout.yh`、
`parse/parse_type.yh` 含
`test` 块，覆盖纯函数边界（`append_int`/`hexval`、`is_assign_op`、`lex_can_end`、
`is_member_name`、`is_type_start`）。运行：

```bash
python3 tools/compiler-tests.py --compiler-path ./yh
```

测试体走与普通函数相同的 CheckedModule→SSA→LLVM 路径，但只在测试模式下登记，
生产构建的模块对象与 `.s.i` 不含 `__yh_test_` 符号。给本目录新增 `test` 块前，
入库种子必须已经支持 test 语法（滚种子之后）。

## 模块与文件职责

**lex** —— 词法

| 文件 | 职责 |
| --- | --- |
| `lex/lexer.yh` | 字节词法器：保留字、数字/转义、注释、运算符最长匹配 |
| `lex/layout.yh` | 布局判定：`lex_can_end` 等语句/字段边界工具，实现与全角宽度相关的前瞻 |
| `lex/interp.yh` | 字符串插值的词法后扩展：把 `${...}` 切成分段而不破坏普通字符串 |

**parse** —— 语法（含顶层声明两遍处理）

| 文件 | 职责 |
| --- | --- |
| `parse/base.yh` | 解析器私有 `ParseCtx`（test 体模式、CT 元信息、表达式块上下文、拒绝阶段） |
| `parse/parse_type.yh` | 类型引用解析 + 解析器共用游标工具 |
| `parse/parse_expr.yh` | 表达式优先级链、后缀链、structInit 与「字面量 vs 块」消解 |
| `parse/parse_stmt.yh` | 语句：块/if/for/switch/return/goto/标签/赋值 |
| `parse/parse_decl.yh` | 顶层声明两遍处理：let/const/fn/type/struct/union/enum |
| `parse/parse_global_init.yh` | 全局聚合变量初始化（命名/位置/嵌套/字符串字面量） |
| `parse/parse_global_static.yh` | 全局静态数据对象登记与接口重放标记 |
| `parse/parse_module.yh` | 模块头解析：`module` 声明、`import NAME (as ALIAS)?;` |
| `parse/parse_comptime.yh` | 函数体 `$if`/`$for` 的解析与作用域接缝 |
| `parse/parse_ct_layout.yh` | 编译期数组长度与布局请求的 token 探测 |
| `parse/parse_interp.yh` | 字符串插值的 parser 降级：合成 fmt 调用树 |
| `parse/iface.yh` | 模块接口（`.s.i` / `.yh.i`）发射与加载：跨模块可见边界 |
| `parse/iface_ct.yh` | 编译期接口（`.s.ct`）发射与加载 |
| `parse/iface_ct_map.yh` | `.s.ct` 正文改写的生成位置与原始位置映射 |

**cache** —— 缓存键 schema 与 ActionID/OutputID（2026-11-06 C0/C1）

| 文件 | 职责 |
| --- | --- |
| `cache/cache_key.yh` | 统一 schema、SHA-256 键前缀、token/整数/文本混入、ActionID 十六进制 |
| `cache/cache_store.yh` | 全局 content store：actions/outputs/tmp、原子 put/get、OutputID 校验 |
| `cache/lock.{darwin,linux,windows}.yh` | 同项目/全局写锁的 flock 平台封装（Windows 后置） |
| `cache/*.test.yh` | 键长度/稳定性/action 隔离与 store 参数测试 |

**ast** —— 纯语法 AST arena（快照已于 GEN1/F1 迁 check）

| 文件 | 职责 |
| --- | --- |
| `ast/ast_decl.yh` | 从 PDecl 索引建立文件级声明节点并关联函数体 |
| `ast/ast_expr.yh` | `yh check` typed 表达式 AST、绑定与常量快照 |
| `ast/ast_stmt.yh` | `yh check` 语句树、绑定关联与编译期 `$for` 模板目录 |
| `ast/ast_function.yh` | 函数在 AST arena 中的范围与绑定身份 |
| `ast/ast_view.yh` | 为外部只读校验借出 arena 视图（含容量/声明索引），不转移所有权 |
| `ast/ast_store.yh` | 受检切片重放用的 5 个 arena 扩容入口；指针/容量仍由 ast 拥有 |

**lower** —— 受检快照到语言 IR（2026-10-25 B3-2 自 `ast` 拆出，5,815 行）

| 文件 | 职责 |
| --- | --- |
| `lower/module_snapshot_lower.yh` | 模块来源/类型/符号准备、签名登记、逐函数构造与模块提交（LA2b） |
| `lower/module_snapshot_ctx.yh` | 纯快照 lowering 的循环、控制流、标签与函数上下文、`CheckedLowerStats` |
| `lower/module_snapshot_lower_expr.yh` | 标量表达式、条件、三元、整数提升与转换 lowering |
| `lower/module_snapshot_lower_call.yh` | 实参、副本、类型化变参、直接/间接调用 lowering |
| `lower/module_snapshot_lower_flow.yh` | if/循环/switch/label-goto 与 phi 合流 lowering |
| `lower/module_snapshot_lower_place.yh` | 绑定赋值、地址、下标与切片位置 lowering |
| `lower/module_snapshot_lower_aggregate.yh` | 数组/结构体字面量、聚合存储与复制 lowering |
| `lower/module_snapshot_lower_cache.yh` | 函数级 IR 缓存键：token 流、逐声明布局与非函数声明事实 |
| `lower/module_snapshot_forin.yh` | `for-in` 循环 lowering 辅助 |
| `lower/module_snapshot_global.yh` | 全局对象类型、初始化值与引用 lowering |
| `lower/module_snapshot_static.yh` | 静态数据、字符串与重定位 lowering 辅助 |
| `lower/module_snapshot_template.yh` | 编译期 `$for` 模板 lowering 辅助 |
| `lower/ast_ir.yh` | builder 指令表辅助（LL12：旧 SSA 编排已退役） |
| `lower/ast_ir_build.yh` | 受支持函数的 AST → typed SSA 构造器 |
| `lower/ast_ir_call.yh` | 固定参数直接调用的目标符号、变长实参与 AST 降低 |
| `lower/module_snapshot_lower_selftest.yh` | check 切片与 lowering 的离线等价性探针（唯一调用方是测试项目） |

`lower` 只 import `check`/`ast`/`ir`/`support`，**不得 import parse/build**；`ast` 也不得
反向 import `lower`/`check`（2026-11-09 起靠评审：`arch-check` 已删除）。F1 把快照迁出后
`ast` 只剩 1,347 行纯 AST arena。

**check** —— 语义入口与受检契约（F1 起拥有 `CheckedModule` 快照）

| 文件 | 职责 |
| --- | --- |
| `check/checked_model.yh` | `CheckedModule`/`CheckedStorage` 数据模型、捕获/释放与有界读取 |
| `check/ct_bind.yh` | CT 事实绑定的唯一入口 `ct_types_sync` + 形状守卫 `ct_type_layout_ok` |
| `check/checked_view.yh` | 借出只读快照视图（`CheckedModuleView`），不转移所有权 |
| `check/checked_key.yh` | pass2b 前的函数 check 键（SHA-256，C0/C1） |
| `check/checked_slice.yh` | 函数级受检 AST 切片捕获/导入、前端复位（`checked_decl_restore`） |
| `check/verify.yh` | 按固定顺序只读校验表达式、语句、声明与函数上下文 arena |
| `check/sem_value.yh` | 字面量/标识符求值、`Res` 构造与值类别 |
| `check/sem_expr.yh` | 表达式语义：下标、成员、运算、转换、切片 |
| `check/sem_decl.yh` | 声明语义：符号登记、参数/返回事实、main 检查 |
| `check/sem_flow.yh` | 控制流语义：赋值、循环、goto/标签与可达性 |
| `check/sem_call_literal.yh` | 调用点语义：实参检查、变参打包记录、结构体字面量 |
| `check/abi_c.yh` | C ABI 位置分类（值/游标模型在 `gen/abi_model.yh`） |
| `check/verify_checked.yh` | 只读校验 `CheckedModule` 快照；由调用方在 lowering 前调用 |

**comptime** —— 编译期函数登记与受限求值

| 文件 | 职责 |
| --- | --- |
| `comptime/ct_facts.yh` | CT 执行器的零拷贝类型镜像（`CtTypeRow`/`CT_TY_*`/谓词）；绑定「槽」，扩容免疫 |
| `comptime/ct_00_model.yh` | 编译期 token、函数、整数值与求值游标模型 |
| `comptime/ct_registry.yh` | 编译期函数正文快照、按符号登记/查询与展开预算 |
| `comptime/ct_enum.yh` | 枚举成员按声明顺序查询，供编译期 `values` 展开 |
| `comptime/ct_diag.yh` | 编译期诊断发出与来源位置 |
| `comptime/ct_ir.yh` | typed IR 表达式与语句执行、调用帧和预算 |
| `comptime/ct_ir_place.yh` | 编译期数组/切片/结构体位置、值复制、视图与别名规则 |
| `comptime/ct_ir_data.yh` | 受支持编译期聚合的目标布局序列化与延迟切片 backing 发射 |
| `comptime/ct_ir_float.yh` | 编译期浮点运算与格式化辅助 |
| `comptime/ct_global_agg.yh` | 全局聚合常量（顶层 const 数组/结构体）的编译期模型 |
| `comptime/ct_layout.yh` | 数组长度与结构体布局的待完成请求、推进与诊断 |
| `comptime/ct_layout_graph.yh` | 混合值/布局依赖边与拓扑推进 |
| `comptime/ct_static_data.yh` | 封存期间值槽到目标对象位置的映射 |
| `comptime/ct_target.yh` | `$target` 标记名匹配，不污染普通词法关键字 |

函数体 `$if/$for` 的解析和作用域接缝位于 `parse/parse_comptime.yh`；
typed 执行器覆盖标量（含浮点）、指针（取址、解引用、算术与下标）、整型/浮点/结构体元素
数组与切片、受支持结构体/联合体值，分支、循环、诊断、整数 `switch`、递归调用及共享执行预算。
早期 token 求值器（`ct_eval_expr.yh`、`ct_eval_bool.yh`）与数组长度 token 探测链已删除：
typed IR 是唯一执行器，正文不在支持子集内的编译期函数直接报
「编译期函数正文不在受支持的 typed IR 子集内」。顶层整数常量与数组长度的编译期调用
统一交给 pass2a 之后的 typed 布局常量依赖调度（早期快路径只在 `ct_is_prepared` 已就绪时生效）。
单文件入口与函数 AST 的统一仍在待办中。

**builtin** —— 内置（prelude）函数登记

| 文件 | 职责 |
| --- | --- |
| `builtin/prelude.yh` | prelude 名字/签名/变参形态与 `F_RUNTIME_*` 标志；只 import gen |

登记顺序沿用历史实现：先 `gen.ty_register_builtins()`、`gen.scope_push()`，再
`builtin.sem_register_prelude()`。符号表与类型表仍归 gen（`gen.prelude_add`
是唯一被导出的原语），运行时函数体在 `backend/llvm_runtime.yh` /
`backend/llvm_apple_runtime.yh` 按需发射。

**support** —— L0 基础内核：缓冲/源/池/统计/诊断/目标

| 文件 | 职责 |
| --- | --- |
| `support/base.yh` | `SourceCtx`/`PoolCtx`/`DiagCtx`/`SessionCtx`/`CompileStats`/`TargetInfo`/`TargetCfg` 与单例 |
| `support/buffer.yh` | `append_*`/`write_all`/`alloc`/`out_grow`/`fail`/`fail_path`/`hexval`/路径缓冲 |
| `support/pool.yh` | 名字池 intern、`np_cstr`、`append_np*` |
| `support/source.yh` | `read_source`/`set_source_path` |
| `support/diag.yh` | `err_lc`/`warn_lc` 与 CT 展开轨迹 |
| `support/target.yh` | `TargetInfo`/`TargetCfg` 解析、`tg_*`、`bind_cfg`、`ABI_*` |

`support` 不是流水线阶段：会话初始化绑定目标/源/统计/诊断，读源前、词法/语法/
检查、lower/backend、link/build 各阶段按需调用。它不持有类型/符号/分析状态。

**token** —— 词法/语法共享词汇与 token 表游标

| 文件 | 职责 |
| --- | --- |
| `token/base.yh` | `TK_*`/`TOK_*`/`ATTR_*`、`Tok`、`PDecl`、`TokenCtx` |
| `token/tokens.yh` | token 数组倍增扩容 `push`、当前游标 `ctx()` |
| `token/op.yh` | `is_assign_op` 纯 token 区间判定 |

`gen/model.yh` 暂时保留 `gen.Tok`/`gen.TK_*` 等别名，调用面逐步改 `token.*`。

**gen** —— 语义内核的残余：类型/符号表、值规则、静态数据与每任务状态

| 文件 | 职责 |
| --- | --- |
| `gen/model.yh` | token/目标别名、类型/符号常量、Res/CType/CSym 等结构 |
| `gen/state.yh` | `GenState`（仅 task）+ `TaskCtx`（150 字段）、`state_init`、`data_str_*`/`em_*` 表 |
| `gen/symbols.yh` | 名字池之外的类型表、符号/作用域、兼容/提升、`mod_*` 命名空间查询 |
| `gen/value_rules.yh` | 浮点位模式、常量折叠、`sem_res_const`、`sem_struct_finish`（comptime 共用） |
| `gen/abi_model.yh` | C ABI 分类的数据模型：`ABIValue`/`ABICursor`/`ABIArg` + `CABI_*` |
| `gen/static_data.yh` | 独占静态数据、64 位指针槽与重定位登记 |
| `gen/target.yh` | 仅 `tg_layout_struct`（读类型/字段表） |
| `gen/front_stage.yh` | 受检前端阶段的进入/校验/退出 |
| `support/clock.*`、`console.*`、`argv.*` | 宿主平台（GEN1 迁出 gen） |

`gen` 不再有 `token_bridge`：token 游标/入表/报错已全部直连 `token.*`。

语义动作（`sem_*`）与 `abi_c` 算法已迁 `check`；`comptime` 仍直接调用
`gen` 的类型/值规则（F4 之前无法解除），因此这些规则必须留在 `gen`。

**ir / backend** —— 受检函数的独立表示与目标发射

| 文件 | 职责 |
| --- | --- |
| `ir/ssa.yh`、`ir/ssa_call.yh` | typed SSA 数据模型、整数转换、CFG/verifier 与直接调用契约 |
| `ir/ssa_serialize.yh` | 含调用目标与实参的稳定函数 IR 编码（`IR_SERIAL_VERSION`） |
| `ir/ssa_module_00_model.yh` | 模块级类型扩展与表结构 |
| `ir/ssa_module_10_build.yh` | 模块构造、复制与表追加 |
| `ir/ssa_module_20_verify.yh` | 模块表一致性与引用校验 |
| `ir/ssa_module_30_serialize.yh` | 模块级序列化/反序列化与身份摘要（`IR_MODULE_SERIAL_VERSION`） |
| `ir/ssa_module_40_function_cache.yh` | 单函数 + 贡献闭包的迷你模块缓存单元（`IR_FUNCTION_CACHE_VERSION`） |
| `ir/ssa_module_50_function_rebind.yh` | 缓存记录的类型/符号/全局重绑定与函数装配 |
| `backend/llvm_module.yh` | IRModule → LLVM 文本的模块级发射与输出缓冲 |
| `backend/llvm_module_data.yh` | 全局数据、静态对象与重定位的 LLVM 发射 |
| `backend/llvm_scalar.yh` | SSA 值编号、临时值与标量指令发射 |
| `backend/llvm_call.yh` | 调用序列与 C ABI 标量分类落点 |
| `backend/llvm_abi_model.yh` | LLVM 文本行区间到模块来源位置的映射 |
| `backend/llvm_apple_abi.yh` | Darwin/ARM64 与 Linux/AArch64 共用的 HFA 与寄存器分类 |
| `backend/llvm_zabi.yh` | SysV MEMORY 属性与字节数组类型 |
| `backend/llvm_runtime.yh` | yh 自有内存与 Linux 运行时的 LLVM IR 发射 |
| `backend/llvm_apple_runtime.yh` | Darwin libSystem OS 入口声明与运行时包装器 |
| `backend/llvm_bridge.yh` | 内嵌 LLVM 静态桥的 yh 侧绑定与诊断读取 |
| `backend/llvm_bind.darwin.yh` / `.linux.yh` | 桥的 C ABI 声明（按目标二选一） |

**build** —— 构建引擎（流水线）

| 文件 | 职责 |
| --- | --- |
| `build/build_ctx.yh` | 会话级构建上下文（BuildCtx） |
| `build/cache_global.yh` | `YH_CACHE` 初始化、模块产物发布/物化、全局 miss 回退、项目锁 |
| `build/cache_admin.yh` | `yh cache info/clean/trim/verify`、trim/verify 与 debug 输出 |
| `build/build_scheduler.yh` | 有界快照 worker 进程池与 InterfaceReady 调度 |
| `build/module_build.yh` | 单模块构建驱动（573 行；扫描/两遍处理/清单/标准库装载） |
| `build/module_worker.yh` | fork 继承项目快照后初始化私有语义状态并编译单模块 |
| `build/module_emit.yh` | 模块产物发射与原子发布 |
| `build/module_cache.yh` | 模块缓存键、依赖表与接口就绪 |
| `build/function_ir_cache.yh` | 函数级 check 切片与 IR 缓存的命令侧 I/O |
| `build/llvm_pipeline.yh` | 已验证快照 → IRModule → LLVM 文本/对象/汇编的共用驱动 |
| `build/llvm_emit.yh` | 单文件受检前端与 LLVM 发射 |
| `build/stats_print.yh` | `--stats` 统计输出 |
| `build/unused_function.yh` | 未用函数裁剪（UF1） |
| `build/project*.yh`、`build/toml.yh`、`build/project_dir.*.yh` | 项目扫描/清单/目录枚举；目标态迁入 `proj/` |

**link** —— 工具链调用层（B2）

| 文件 | 职责 |
| --- | --- |
| `link/context.yh` | argv0 与链接阶段计时 |
| `link/link_cache.yh` | 模块对象与最终程序的内容缓存 |
| `link/link_inputs.yh` | `--link` 选择、库文件检查与 argv 素材 |
| `link/darwin_link.yh` / `link/windows_link.yh` | 平台链接驱动与 SDK/前缀 |
| `link/process.yh` | `fork/execvp/waitpid` 启动宿主进程，不经 shell |

**proj** —— 项目模型/表/产物路径（B1）

| 文件 | 职责 |
| --- | --- |
| `proj/proj_00_model.yh` | 项目/模块/文件三张表与扫描游标 |
| `proj/proj_10_table.yh` | 表访问与写者登记 |
| `proj/proj_20_path.yh` | 路径/模块标记 |
| `proj/proj_40_art.yh` | 产物路径、缓存键与哈希原语 |

**testkit** —— 语言内测试执行器（`yh test` 的实现）

| 文件 | 职责 |
| --- | --- |
| `testkit/test_cmd.yh` | 测试发现、文档目标绑定、模块/文件选择、测试体降低与对象发布（YT1/YT2a） |

模块名不能叫 `test`——`test "..." {}` 是语言关键字。`testkit` 位于 `build`
之上，但当前直接使用了 15 处 `mb_*`/`cmd_*`（8 个符号）等 `build` 内部引用，
属待收敛的层间泄漏（见[架构设计](../docs/03-design/yh-架构设计.md) §5.2 A6）。

**cmd** —— CLI 与调用面（P1 后一命令一文件，10 个文件）

| 文件 | 职责 |
| --- | --- |
| `cmd/driver.yh` | `main(argc, argv, envp)`、内部子进程协议识别与分派，不做实际执行 |
| `cmd/common.yh` | 命令共享前奏、`API_*` 形态常量、退出码契约 |
| `cmd/cmd_build.yh` | `yh build` / `yh check` |
| `cmd/cmd_run.yh` | `yh run` |
| `cmd/cmd_test.yh` | `yh test`（含 `--timeout` 校验） |
| `cmd/cmd_cache.yh` | `yh cache info/clean/trim/verify`（C6） |
| `cmd/cmd_list.yh` | `yh list [--resolve]` |
| `cmd/cmd_version.yh` | `yh version` / `--contracts` |
| `cmd/cmd_single.yh` | 单文件五形态：`--syntax-check` / `--emit-asm` / `--emit-llvm` / `-o` / check-with-src |
| `cmd/cmd_emit_module.yh` | 内部子进程协议 `--emit-module` |
| `cmd/cmd_lld_link.yh` | 内部子进程协议 `--lld-link` |

普通配置默认不登记 `system(cmd)`；`--legacy-system` 为迁移期显式兼容开关。
自举构建使用默认配置。编译器入口接收 `envp`，直接读取 `PATH` 与
`YH_STDLIB`；构建与临时目录使用 `mkdir` OS API。项目目录扫描由 Darwin
`getattrlistbulk` 与 Linux `getdents64` 适配完成，不再调用 `/bin/ls`；Linux
系统调用经 LLVM 运行时入口完成。系统汇编器/链接器与 `malloc`、`free` 等 C
服务由 LLVM 运行时与内嵌 lld 承担；LL12 已删除旧 arm64 内存运行时发射。

**模块与产物流向**

```
cmd/driver ─▶ cmd/api ─▶ build（扫描/索引/绑定/拓扑/调度）
                            ├─ fork worker ─▶ lex ─▶ parse ─▶ gen.sem_* ─▶ ast 捕获
                            │                   ─▶ check 校验 ─▶ lowering ─▶ ir.IRModule
                            │                   ─▶ backend（LLVM 文本）─▶ 内嵌桥 ─▶ .o
                            └─ link_cache（内嵌 lld）─▶ 可执行
testkit ─▶ build（复用调度与产物路径，执行测试体）
```

受检快照统一经 `lower/module_snapshot_lower*.yh` 降低为 `ir.IRModule`，再由
`backend/llvm_*.yh` 发 LLVM 文本，`build/llvm_pipeline.yh` 统一经内嵌桥原子
发布对象/汇编；项目构建按函数复用
`ir/ssa_module_40_function_cache.yh` 的迷你模块记录，
`ssa_module_50_function_rebind.yh` 负责重绑定；旧「函数级 SSA + 汇编替换」链
已删除，`lower/ast_ir*.yh` 只保留 builder 底层与共享调用缓冲。

`compiler/ir/` 是独立的模块 IR 子项目，由 `compiler/project.toml` 以本地 path
依赖引入，也由 `tests/modules/projects/irverify/` 直接依赖并运行验收。

## 已实现的语义

- **聚合按值**：struct/union/数组作参数与返回，调用点拷贝 + 指针传递，
  >16 字节返回经 x8 隐藏缓冲；嵌套结构体字面量。
- **切片**：`[]T` 规范化视图 `{u64 长度, T* 数据}`，`len`、下标、
  `[N]T.to_type([]T)` 视图构造、切片实参与遍历。
- **for-in**：数组、切片、区间 `a..b`（左闭右开）三种迭代源，
  元素/下标绑定为每轮值拷贝。
- **类型化变参**：末尾 `name ... T` 打包为 `[]T` 切片，零变参为空切片。
- **浮点**：f32/f64 经 d0-d7 传参与返回，`+ - * /` 与比较、
  `f32↔f64`、整数↔浮点 `to_type`。
- **structInit 作值**：结构体字面量可用于初始化、实参、返回、嵌套字段。
- **全局聚合初始化**：`parse_global_init.yh`，命名/位置/嵌套/字符串字面量
  （字节镜像 + 节内 `R_DATA_PTR` 重定位）。
- **字符串插值**：`"${expr:spec}"` 端到端（`lex/interp` → `parse_interp` →
  fmt 库），编译期校验 spec 与类型。
- **语言内测试**：`test "..." { }` 与 `--filter`/`--timeout`，由 `testkit` 执行。

## 架构与多平台

后端分三层：前端语义（`gen/symbols.yh` + `gen/sem_*.yh` +
`parse/parse_*.yh` + `ast/ast_*.yh` + `check/verify.yh`）→ 受检快照/模块 IR
（`check/checked_*.yh`、`lower/module_snapshot_lower*.yh`、`ir/ssa_module_*.yh`）→ LLVM 发射
（`backend/llvm_*.yh` + 内嵌桥）。前端不持有 ISA 状态；换目标 = 目标身份 +
对应 LLVM 目标库。LL12 已删除 `em_*` 抽象机原语与旧 arm64 发射器，
系统架构与迁移路线见[架构设计](../docs/03-design/yh-架构设计.md)。
逐阶段当前流程见[编译流程-当前实现](../docs/03-design/yh-编译流程-当前实现.md)。
缓存层次与键/manifest 见[缓存设计](../docs/03-design/yh-缓存设计.md)。

依赖方向见[架构设计 §3.1](../docs/03-design/yh-架构设计.md)（原由 `just arch-check`
强制，该工具 2026-11-09 已删除，现靠评审）：
`gen`/`ir` 是依赖根，`parse`/`ast`/`check`/`comptime`/`lower`/`backend` 在其上，
`proj`/`build` 装配下层，`cmd` 在最顶。当前 17 模块 61 条边、无环；目录职责、
依赖矩阵与结构性问题见[架构设计](../docs/03-design/yh-架构设计.md)。

## 自编子集与已知边界

编译器自身源码遵守的自举子集：整数/字节/指针、结构体字段、堆缓冲、
全局/局部变量、普通函数、递归、`if` 与条件 `for`（无限循环写
`for 1 { }`）、赋值与位运算、`sizeof(T)`、prelude 的
open/read/write/close/malloc/free/memcpy/strlen/exit。

**已知边界**（详见 [架构设计](../docs/03-design/yh-架构设计.md) §5.5）：

- 切片越界与生命周期运行时防护不做（[ADR-0001](../docs/adr/0001-yh数组按值调用边界.md) 既定）。
- 浮点参数超过 8 个（超出 d0-d7）未实现。
- 裸 C 变参 `...` 在用户源码被显式拒绝，仅编译器内置 prelude 使用。
