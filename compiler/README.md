# compiler —— yh 自举编译器（.yh 源码）

> 0.0.3 起本目录是**主要开发编译器**（[ADR-0006](../docs/adr/0006-yh自举产物为主要开发编译器.md)、
> [ADR-0007](../docs/adr/0007-yh编译器使用源码模块.md)）：仓库已删除 C 版
> stage0 与 bootstrap，构建只依赖种子 `bin/yh-<平台>-<架构>`（上一版编译器二进制，
> 用 `just fetch-seed` 从 Release 下载，不入库）。
> 自举产物默认目标取编译器构建身份（qemu 下仍为进程架构），日常验证以
> `just selfhost-native` 为主门。

用 yh 语言写成的 yh 编译器。源码是 `project.toml` 项目（name = `yh`，
version = `0.0.11`，source = `.`），按 **gen / builtin / lex / parse / ast /
check / comptime / lower / ir / backend / build / testkit / cmd** 组织。
**2026-10-27 实测（`python3 tools/arch-check.py`）：十三个模块、120 个 `.yh`、
53,545 行**：`gen` 5,621 · `parse` 9,699 · `build` 11,015 · `lower` 5,819 ·
`comptime` 5,517 · `ir` 5,005 · `ast` 3,433 · `backend` 3,264 · `testkit` 1,592 ·
`lex` 1,069 · `check` 958 · `cmd` 381 · `builtin` 172。

各层来历：`ast/` 是 2026-10-12 自 parse 拆出的 AST 阶段，`check/` 承担
AST 与快照的**只读一致性校验**（不是语义分析），`builtin/` 只放内置
（prelude）函数登记表，`ir`（目标隔离 SSA）与其它模块同为根项目普通模块，
`build/` 是 2026-10-24 A2c 自 `cmd/` 拆出的构建引擎（项目模型、调度、
模块发射、缓存、链接、平台适配），`testkit/` 是同一批 A6 抽出的语言内测试
执行器，`lower/` 是 2026-10-25 B3-2 自 `ast/` 拆出的 lowering 阶段
（`CheckedModule → IRModule`，此前 ast 9,041 行里混着 5,815 行变换代码）。
`cmd/` 只剩 CLI 参数映射（`driver`）与调用面（`api`），381 行、占 0.7%。

模块导出面按「只有别的模块真的用到才 `pub`」维护（2026-10-12 两轮：`pub`
声明 1048 → 585，随后 `struct`/`union`/`enum` 的 `pub` 改为可选并私有化 12 个
模块内部类型，接口 `.s.i` 63,160 → 39,990 → 36,633 字节）：仅模块内使用的
`fn`/`const`/类型不写 `pub`（`pub` 同时决定接口导出与 `.globl`）；私有类型
不得出现在本模块的 `pub` 签名、`pub` 字段或 `pub` 别名里；入口模块 `cmd/`
只保留 `main` 为 `pub`。规则见
[导出面收缩设计](../docs/03-design/yh-编译器模块导出面收缩设计.md)与
[模块私有类型设计](../docs/03-design/yh-模块私有类型设计.md)。

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

`just selfhost-native` 由 `tests/selfhost/native-selfhost.py` 执行本机全套
自举门（滚动自举，无 stage0；种子 = `just fetch-seed` 取得的 `bin/yh-<平台>-<架构>`）：

    bin/yh-<平台>-<架构> build compiler/  → cc2（冷编）
    cc2     build compiler/ → cc3（冷编）
    cc3     build compiler/ → cc4（冷编，固定点对比）

门：①固定点——cc3/cc4 全部模块 `.s`/`.s.i` 逐字节一致；②cc4 自解析
compiler/ 全部源文件；③cc4 语法语料（`tests/yh` 正例全过、反例全拒）；
④cc4 运行语料（`tests/yh-run` 全量 run/fail/pass，2026-10-25 实测 360 个
`.yh` 用例文件）；⑤模块语料（`tests/modules/check.py`）；⑥项目验收
（`tests/modules/build-check.py`，2026-10-24 记录 126 例），以及
`tests/selfhost/llvm-function-cache.py` 的函数级缓存矩阵。滚种子前必须全绿。

## 内建测试

`gen/buffer.yh`、`lex/layout.yh`、`parse/parse_type.yh` 含 `test` 块，覆盖
纯函数边界（`hexval`、`is_assign_op`、`lex_can_end`、`is_member_name`、
`is_type_start`）。运行：

```bash
just test-compiler-tests   # tools/compiler-tests.py（需要种子支持 test 语法）
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

**ast** —— AST 阶段与受检快照（2026-10-12 自 parse 拆出）

| 文件 | 职责 |
| --- | --- |
| `ast/ast_decl.yh` | 从 PDecl 索引建立文件级声明节点并关联函数体 |
| `ast/ast_expr.yh` | `yh check` typed 表达式 AST、绑定与常量快照 |
| `ast/ast_stmt.yh` | `yh check` 语句树、绑定关联与编译期 `$for` 模板目录 |
| `ast/ast_function.yh` | 函数在 AST arena 中的范围与绑定身份 |
| `ast/ast_view.yh` | 为外部只读校验借出 arena 视图，不转移所有权 |
| `ast/cache_mix.yh` | 函数缓存键的 FNV-1a 64 原语（check 键与 IR 键共用唯一实现） |
| `ast/module_snapshot.yh` | `CheckedModule`/`CheckedStorage` 快照数据模型、捕获/释放与有界读取 |
| `ast/module_snapshot_view.yh` | 为外部快照校验借出只读视图，不转移所有权 |
| `ast/module_snapshot_check_key.yh` | pass2b 前的函数 check 键（LA3.3 C3） |
| `ast/module_snapshot_check_slice.yh` | 函数级受检 AST 切片捕获/导入、前端复位（`checked_decl_restore`） |

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
| `lower/module_snapshot_lower_cache.yh` | 函数级 IR 缓存键：token 流、布局/签名与非函数声明事实 |
| `lower/module_snapshot_forin.yh` | `for-in` 循环 lowering 辅助 |
| `lower/module_snapshot_global.yh` | 全局对象类型、初始化值与引用 lowering |
| `lower/module_snapshot_static.yh` | 静态数据、字符串与重定位 lowering 辅助 |
| `lower/module_snapshot_template.yh` | 编译期 `$for` 模板 lowering 辅助 |
| `lower/ast_ir.yh` | builder 指令表辅助（LL12：旧 SSA 编排已退役） |
| `lower/ast_ir_build.yh` | 受支持函数的 AST → typed SSA 构造器 |
| `lower/ast_ir_call.yh` | 固定参数直接调用的目标符号、变长实参与 AST 降低 |
| `lower/module_snapshot_lower_selftest.yh` | check 切片与 lowering 的离线等价性探针（唯一调用方是测试项目） |

`lower` 只 import `ast`/`ir`/`gen`，**不得 import parse/check/build**；`ast` 也不得
反向 import `lower`（由 `arch-check` 的 `ALLOWED` 强制）。拆分后 `ast` 从 9,041 行
降到 3,278 行，此后所有 AST 侧改动都在 1/3 规模上进行。

**check** —— AST arena 与独立快照的一致性校验

| 文件 | 职责 |
| --- | --- |
| `check/verify.yh` | 按固定顺序只读校验表达式、语句、声明与函数上下文 arena |
| `check/checked_module.yh` | 只读校验 `CheckedModule` 快照；由调用方在 lowering 前调用 |

**comptime** —— 编译期函数登记与受限求值

| 文件 | 职责 |
| --- | --- |
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

**gen** —— 共享内核：状态、类型/符号表、语义与目标描述

| 文件 | 职责 |
| --- | --- |
| `gen/model.yh` | token 常量、类型/符号常量、Tok/Res/CType/CSym 等结构 |
| `gen/state.yh` | `GenState`（64 字段，进程级）+ `TaskCtx`（188 字段，每编译单元）与 `G()` |
| `gen/front_stage.yh` | 受检前端阶段的进入/校验/退出（LL12 后旧输出缓冲已删除） |
| `gen/buffer.yh` | 源文件整读（open/read/close）、汇编输出缓冲、诊断、字节写出 |
| `gen/symbols.yh` | 名字池、类型表、符号/作用域、类型兼容、常量折叠、prelude 符号表原语 |
| `gen/static_data.yh` | 独占静态数据、64 位指针槽与重定位登记 |
| `gen/target.yh` | 目标数据模型：字长、对齐、结构体布局（**换平台的第一步**） |
| `gen/target_info.yh` | 宿主 triple 严格解析与目标身份选择 |
| `gen/abi_c.yh` | 共享 AArch64 C ABI 分类：值描述、HFA、寄存器与目标栈布局 |
| `gen/sem_value.yh` | 字面量/标识符求值、常量折叠与值类别（LL12：无发射） |
| `gen/sem_expr.yh` | 表达式语义：下标、成员、运算、转换、切片（LL12：无发射） |
| `gen/sem_decl.yh` | 声明语义：符号登记、结构体布局与函数参数/返回事实 |
| `gen/sem_flow.yh` | 控制流语义：类型检查、循环上下文与可达性（LL12：无跳转发射） |
| `gen/sem_call_literal.yh` | 调用点语义：实参检查、变参打包记录与结果形态（LL12：无搬运） |

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

**build** —— 构建引擎（2026-10-24 A2c 自 `cmd/` 抽出）

| 文件 | 职责 |
| --- | --- |
| `build/module_build.yh` | 项目构建管线：扫描/索引/两遍文件处理/不变量/清单/CLI 命令（2,242 行，待拆） |
| `build/build_scheduler.yh` | 有界快照 worker 进程池与 InterfaceReady 调度 |
| `build/module_worker.yh` | fork 继承项目快照后初始化私有语义状态并编译单模块 |
| `build/llvm_emit.yh` | 单文件受检前端与 CLI 形态转换 |
| `build/llvm_pipeline.yh` | 已验证快照 → IRModule → LLVM 文本/对象/汇编的共用驱动与原子发布 |
| `build/function_ir_cache.yh` | 函数级 check 切片与 IR 缓存的命令侧 I/O（`.fchk`/`.fir`/索引） |
| `build/link_cache.yh` | 模块对象与最终程序的内容缓存、内嵌 lld/外部驱动链接、`mb_link` |
| `build/link_inputs.yh` | `--link` 选择、库文件 realpath/格式/摘要检查与 argv 素材 |
| `build/darwin_link.yh` | Darwin 链接驱动、SDK/部署身份与 frameworks 参数 |
| `build/process.yh` | 用 `fork/execvp/waitpid` 按 argv 启动宿主进程，不经 shell |
| `build/project.yh` | 项目扫描的目录项模型（平台无关） |
| `build/project_state.yh` | 项目状态：根发现、源码根扫描、模块索引 |
| `build/project_index.yh` | 清单 schema 校验与字段提取（name/version/author/source/os/arch/dependencies） |
| `build/project_link.yh` | `[project].os/arch` 与 `[link]` / `[link-<os>-<arch>]` 结构校验 |
| `build/project_resolve.yh` | 三层来源解析（当前项目 / 标准库 / 直接依赖）与 import 绑定 |
| `build/toml.yh` | `project.toml` 解析与 schema 诊断（未知字段、必填项、行号） |
| `build/project_dir.darwin.yh` | `getattrlistbulk` 批量目录枚举 |
| `build/project_dir.linux.arm64.yh` / `.linux.x64.yh` | `openat`/`getdents64` 目录枚举 |
| `build/clock.darwin.yh` | Darwin 单调时钟 `clock_gettime` |
| `build/clock.linux.arm64.yh` / `.linux.x64.yh` | Linux 时钟 syscall 封装 |

平台专属文件按**目标标签匹配文件名段**选择（`pj_target_tag_is`），不是
`#ifdef`；新增平台要在 `gen/target.yh` 之后补 `project_dir`/`clock` 两组文件。

**testkit** —— 语言内测试执行器（`yh test` 的实现）

| 文件 | 职责 |
| --- | --- |
| `testkit/test_cmd.yh` | 测试发现、文档目标绑定、模块/文件选择、测试体降低与对象发布（YT1/YT2a） |

模块名不能叫 `test`——`test "..." {}` 是语言关键字。`testkit` 位于 `build`
之上，但当前直接使用了 `mb_link`/`mb_build_dir` 等 28 个 `build` 内部符号，
属待收敛的层间泄漏（见架构复核 A6）。

**cmd** —— CLI 与调用面（A6 后只剩两个文件）

| 文件 | 职责 |
| --- | --- |
| `cmd/driver.yh` | `main(argc, argv, envp)` 与参数 → 请求映射，不做实际执行 |
| `cmd/api.yh` | 调用面：单文件（语法/检查/汇编/LLVM 文本/可执行）与项目（build/run/test/list/version） |

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
（`ast/module_snapshot*.yh`、`lower/module_snapshot_lower*.yh`、`ir/ssa_module_*.yh`）→ LLVM 发射
（`backend/llvm_*.yh` + 内嵌桥）。前端不持有 ISA 状态；换目标 = 目标身份 +
对应 LLVM 目标库。LL12 已删除 `em_*` 抽象机原语与旧 arm64 发射器，
历史架构见[自举后端架构](../docs/03-design/yh-自举后端架构.md)。

依赖方向由 `just arch-check` 强制（`tools/arch-check.py` 的 `ALLOWED`）：
`gen`/`ir` 是依赖根，`parse`/`ast`/`check`/`comptime`/`lower`/`backend` 在其上，
`build` 装配全部下层，`cmd` 在最顶。当前 13 模块 37 条边、无环；实测与
结构性问题见[当前架构重新分析](../docs/03-design/yh-当前架构重新分析-2026-10-25.md)。

## 自编子集与已知边界

编译器自身源码遵守的自举子集：整数/字节/指针、结构体字段、堆缓冲、
全局/局部变量、普通函数、递归、`if` 与条件 `for`（无限循环写
`for 1 { }`）、赋值与位运算、`sizeof(T)`、prelude 的
open/read/write/close/malloc/free/memcpy/strlen/exit。

**已知边界**（详见 [自举后端架构 §7](../docs/03-design/yh-自举后端架构.md)）：

- 切片越界与生命周期运行时防护不做（[ADR-0001](../docs/adr/0001-yh数组按值调用边界.md) 既定）。
- 浮点参数超过 8 个（超出 d0-d7）未实现。
- 裸 C 变参 `...` 在用户源码被显式拒绝，仅编译器内置 prelude 使用。
