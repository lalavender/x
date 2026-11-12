# yh 编译器模块职责（当前实现）

基线：`llvm` 分支（0.0.12 + C0–C6 + GEN1–GEN4 + F4 + 模块归组），
**20 个模块 / 179 个文件 / 64,371 行**（2026-11-11 实测 `just code-stats`，含 `types`/`table` 拆分）。
实测：2026-11-10（`just code-stats`；`arch-check` 已于 2026-11-09 删除，
`cmdline` 已并入 `main`，`cache` 已下沉 `build/cache/`）；依赖边以
[架构设计 §3.1](yh-架构设计.md) 为准。

本文是「每个模块干什么」的唯一清单；分层理由与历史决策见
`docs/03-design/yh-架构设计.md`，拆分动因见 `docs/adr/0021-yh-gen职责拆分.md`。

## 1. 分层总览

```
L6  main（CLI 声明/分派）  testkit（yh test runner）
L5  build（构建编排）
L4  link（链接驱动）
L3  backend（LLVM IR 发射）
L2  lower（IR 降低）       parse（语法分析）   builtin（内建登记）
L1  check（语义中心）      comptime（CT 执行器） ast（语法树）  proj（项目模型）
L0  types  support  table  token  ir  cache  lex
```

依赖只能**向下**（箭头指向被依赖方），以本文表格与
[架构设计 §3.1](yh-架构设计.md) 为准；`tools/arch-check.py` 已于 2026-11-09 删除，
不再有自动门禁，越界靠 code review 发现。`types` 与 `ir` 无依赖；`support` 只依赖
`types`/`errors`，三者（`types`/`support`/`ir`）是所有模块的公共底座。

## 2. 逐模块职责

### L0 基础层

| 模块 | 规模 | 依赖 | 职责与关键入口 |
| --- | --- | --- | --- |
| **types** | 1 / 83 | — | 语言类型模型（叶子）：`TY_*` 类型种类常量、类型表行 `CType`、字段表行 `SField`、具名类型行 `TName`。只有数据形状与种类编码，不持有存储实例；存储与增删在 `support.ModelStore` 与 `check` 的类型规则 |
| **table** | 3 / 1,316 | types, support, errors, token | 编译期语义存储（V `ast.Table` 对等层，ADR-0027）：`ModelStore`/`CSym` + 表操作（`ms()`/`ty_push`/`sym_lookup`/`sig_add`/`fn_abi`/`cabi_*`）+ 值规则（`vk_fold_*`/`sem_fold_*`/`vk_can_assign`/`vk_msg`）+ 字符串标签/枚举成员表（`data_str_*`/`em_*`）+ 静态数据目录（`static_data_*`/`StaticData*`，ADR-0028）+ `SYM_*/F_*/VK_*` |
| **support** | 1 / 1,300 | types, errors | 叶子内核（依赖 `types` 与诊断底座 `errors`），**纯平台无关**。①基础设施：源缓冲 `src_ctx`、名字池 `pool_ctx`、诊断转发、`append_*`/`alloc`、会话开关 `session()`、目标身份 `TargetInfo`/`cfg()`。②跨层共享态：`ModuleSym`(`msym()`)、`FrontCtx`(`fc()`)、`Res`。（语义存储已全部迁 `table`，ADR-0027/0028；`base.yh`/`task_ctx.yh` 的单例已并入本文件）（平台变体已全部迁出：FileScope/ABI/front_stage 见 ADR-0024，console/argv 见 ADR-0025，clock 删除见 ADR-0026） |
| **token** | 3 / 268 | support | 词法/语法共享词汇：`TK_*`/`TOK_*`/`ATTR_*` 常量、`Tok`、`PDecl`、token 数组与游标 `ctx()`、`err_tok`（唯一带位置诊断入口）、`is_assign_op` |
| **ir** | 10 / 5,385 | — | 后端无关 SSA IR：`IRModule`/`IRFunction`/`IRInst`/类型与值模型、构建器、verifier、序列化（`ssa_module_*`）。不依赖任何模块 |
| **cache**（目录 `build/cache/`） | 7 / 1,047 | support, token, hash | 内容寻址缓存原语：ActionID/OutputID、缓存键 schema、全局 store（C4）、跨平台文件锁（C6）。位于 check/lower 之下，避免二者为共享键原语互相 import |
| **lex** | 4 / 1,048 | support, token | 词法器：扫描、插值字面量切分、布局（隐式 `;` 插入）、`LexCtx` 行列游标 |

### L1 语义与前端数据

| 模块 | 规模 | 依赖 | 职责与关键入口 |
| --- | --- | --- | --- |
| **proj**（`model`/`table`/`path`/`art` 四文件） | 5 / 2,078 | support, token | 项目模型：`project.toml` 解析、模块/文件表、三层名字解析（本项目 → 标准库 → 依赖）、产物与 `[link]` 配置；**文件作用域** `FileScope`(`fs()`)：模块归属、导入表、已加载接口缓存与绑定名查找（2026-11-10 自 support 迁入，ADR-0024）。前端与构建层共用的数据层 |
| **ast** | 6 / 1,339 | comptime, proj, support, token | 语法树 arena + 只读视图：声明索引、语句/表达式节点、函数上下文、绑定、捕获开关。**纯语法，不 import check**（check 依赖它） |
| **comptime** | 15 / 6,076 | support, token | 编译期执行器：CT IR 模型与求值、布局图、静态数据、函数注册表、枚举/浮点、CT 诊断。语义事实经**零拷贝镜像** `ct_facts` 读（槽绑定，`check.ct_facts_sync` 填入），不 import check。F4 收尾后不再依赖 `proj`（文件表窄口改由 `parse` 传入） |
| **check** | 21 / 9,852 | ast, cache, comptime, ir, proj, support, token, types | **语义中心**：①类型/符号表操作 `symbols.yh`（F2-K2 自 gen 迁入的语义动作）②语法→语义两遍（`sem_*` 内核）③**表达式/语句驱动入口**：`eval.yh`（表达式 `sem_eval_*`，自 `full.yh` 拆出）与 `stmt_eval.yh`（语句 `sem_eval_*`）；均含节点模式与仅算子模式（2026-11-11）④**影子门** `full.yh`（`YH_AST_FULL_CHECK`：从节点重算并与注解比对）⑤C ABI 分类 `abi_c`（含 `ABIValue/ABICursor/ABIArg/CABI_*`，ADR-0024）⑥受检快照 `CheckedModule`：捕获/校验/切片/键/视图 ⑦CT 镜像绑定点 `ct_bind` ⑧值内核诊断适配 `value_kernel.yh` ⑨受检前端阶段守卫 `front_stage.yh`（`front_checked_*`，ADR-0024） |

### L2/L3 前端装配与降低

| 模块 | 规模 | 依赖 | 职责与关键入口 |
| --- | --- | --- | --- |
| **parse** | 14 / 7,760 | ast, check, errors, ir, lex, proj, support, table, token, types | 语法分析：声明/语句/表达式/类型、comptime 语法、全局初始化、模块导入；**接口 `.s.i`/`.s.ct` 的发射与加载**也在这里。表达式语义自 2026-11-11（S4-4）由 `check` 的分层 eval 入口计算——`check.` 引用 162 处（余下为语句/声明/类型级语义动作 + eval 入口调用，守卫 `front-coupling`） |
| **builtin** | 1 / 181 | check, support | 语言内建：内建函数与内建类型登记、prelude 外部接口（含 Linux AArch64 `syscall6`） |
| **lower** | 16 / 5,927 | ast, cache, check, ir, proj, support, token | `CheckedModule` → `IRModule`：SSA 降低（表达式/调用/控制流/for-in/全局与静态数据）。只吃快照，**不 import parse/build**。（四段计时随 clock 删除清理，ADR-0026；`CheckedLowerStats` 只剩缓存计数） |

### L4 后端

| 模块 | 规模 | 依赖 | 职责与关键入口 |
| --- | --- | --- | --- |
| **backend** | 14 / 4,149 | ir, support | **唯一 LLVM 后端**：`llvm_emit_module(IRModule, target, out)` 发 LLVM IR 文本。分工见 §4。`llvm_bridge_emit` 调内嵌静态 LLVM 桥把文本编译为目标文件 |

### L5/L6 构建、链接、CLI

| 模块 | 规模 | 依赖 | 职责与关键入口 |
| --- | --- | --- | --- |
| **link** | 7 / 4,390 | backend, proj, support | 链接驱动：Darwin（内嵌 lld / 系统 `ld`）、Windows（`lld-link`）、进程调用与输出捕获、链接键与链接缓存。位于 build 之下（不得 import build） |
| **build** | 21 / 7,826 | ast, backend, builtin, cache, check, comptime, ir, lex, link, lower, parse, proj, support, token | 构建编排：会话初始化、模块图与调度（含 fork worker）、函数级 IR 缓存、LLVM 流水线与产物发布、全局缓存管理（`yh cache` 实现） |
| **testkit** | 1 / 1,650 | ast, build, link, parse, proj, support, time, token | `yh test` 的发现 / 构建 / 逐例执行 / 报告；逐例超时用 `time.monotonic_ns`（ADR-0026） |
| **main**（目录 `cmd/yh/`） | 21 / 1,393 | build, check, lex, libs, link, parse, proj, support, testkit | CLI 声明/解析（唯一允许 `libs/cli` 的模块）、中文帮助、`YH_VERSION_TEXT`（`--version` 唯一来源）与分派：`build`/`run`/`test`/`cache`/`list`/单文件编译…；只做「请求 → 调 build/check」，不实现业务。入口宿主适配 `console.*`/`argv.*`（控制台 UTF-8、Windows argv 重建，ADR-0025 自 support 迁入） |

## 3. 依赖方向（实测 76 条边，2026-11-10）

| 模块 | 允许依赖 |
| --- | --- |
| support / ir | — |
| token | support |
| cache | support, token, hash |
| lex | support, token |
| proj | support, token |
| ast | support, token, proj, comptime |
| comptime | support, token |
| check | support, token, proj, ast, comptime, cache, ir |
| builtin | support, check |
| parse | support, token, lex, proj, ast, check, ir, errors, table, types |
| lower | support, token, proj, ast, check, cache, ir |
| backend | support, ir |
| link | support, proj, backend, hash |
| build | 全部下层 + cache, hash, libs |
| testkit | support, token, proj, ast, parse, build, link |
| main（cmd/yh） | support, proj, lex, parse, check, build, link, testkit, libs |

**不可违反的三条**（越界即架构红灯）：

1. `support` 必须是叶子（任何反向依赖都成环）
2. `comptime` 不得依赖 `check`（`check → comptime` 已存在）——值内核必须待在 `support` 这类叶子模块里
3. `lower` 不得依赖 `parse`/`check` 的具体实现之外的东西，且 `ast` 不得反向依赖 `lower`

## 4. `backend` 内部分工

| 文件 | 行数 | 职责 |
| --- | ---: | --- |
| `llvm_apple_abi.yh` | 793 | Darwin AArch64 ABI 分类、实参/返回值布局 |
| `llvm_scalar.yh` | 643 | SSA 值/临时值命名、标量指令与表达式发射 |
| `llvm_windows_runtime.yh` | 601 | Windows x64 运行时入口 |
| `llvm_runtime.yh` | 540 | yh 自有内存运行时 + Linux x64 运行时入口 |
| `llvm_module.yh` | 538 | **模块装配入口** `llvm_emit_module`：头部三元组/datalayout、全局、函数、运行时、source map |
| `llvm_call.yh` | 348 | 调用发射、C ABI 标量/聚合传参、间接调用 |
| `llvm_zabi.yh` | 291 | SysV/Darwin MEMORY 类按字节表示 |
| `llvm_bridge.yh` | 126 | 内嵌 LLVM 静态桥的 yh 侧绑定 |
| `llvm_module_data.yh` | 111 | 全局可达性分析、私有静态对象裁剪 |
| `llvm_apple_runtime.yh` | 57 | Darwin 运行时补充 |
| `llvm_abi_model.yh` / `llvm_bind.*.yh` | 少量 | ABI 常量模型、各平台桥符号绑定 |

## 5. 已知结构债（与本文相关的部分）

| 债 | 现状 | 去向 |
| --- | --- | --- |
| `parse` 边解析边求值 | **表达式侧与语句侧均已完成（2026-11-11）**：表达式内联语义 0、`parse_stmt` 直调语句内核 0；`check.` 引用 162 处，均为声明/类型级语义动作与 eval 入口调用。`Res` 与现场事实仍参与部分语法决策（算子模式） | 方案 `docs/01-finished/yh-F2-核收缩与parse纯语法化结论-2026-11-06.md` §3.5「核收缩」**已落地**；表达式外置见 [S4-2 方案](../02-plan/yh-S4-2-表达式语义外置方案-2026-11-10.md) §4e-3、语句外置见 §4e-4。剩余：严格「只产语法节点」未达成（算子模式清单见方案 §4e-3/§4e-4） |
| ~~`gen` 尚存 3 个 pub fn~~ | **已解决（2026-11-06）**：按「错误码 + 调用层格式化」拆开，值内核下沉 `support/value_kernel.yh`，`gen` 模块删除 | `docs/01-finished/finish-F4-comptime纯执行器-2026-11-06.md` 路线 A 已落地 |
| `support` 内涵膨胀 | 2,740 行里有大量 GEN4/F2 下沉的状态与纯规则 | 有意为之：它是唯一无依赖模块，跨层共享数据的唯一无环落点；若将来拆分，必须保持「叶子」性质 |

## 6. 规模速查

### 6. 规模速查（2026-11-08 实测）
> 2026-11-11 说明：本节表为 2026-11-08 快照，未随 S4-4 重排。最新实测（`just code-stats`，
> 2026-11-11）：总计 **179 文件 / 64,371 行**；`check` 21 / 9,852、`parse` 14 / 7,760、
> `support` 1 / 1,279（`support` 已缩为单文件，表中 28 文件为拆分前数值）。


| 模块 | 文件 | 行数 | 模块 | 文件 | 行数 |
| --- | ---: | ---: | --- | ---: | ---: |
| check | 17 | 8,249 | testkit | 1 | 1,627 |
| build | 21 | 7,826 | proj | 4 | 1,590 |
| parse | 13 | 7,585 | ast | 6 | 1,339 |
| comptime | 15 | 6,076 | main | 12 | 1,101 |
| lower | 16 | 5,991 | lex | 4 | 1,048 |
| ir | 10 | 5,385 | cache | 7 | 1,047 |
| link | 7 | 4,390 | token | 3 | 268 |
| backend | 14 | 4,149 | builtin | 1 | 181 |
| support | 28 | 3,118 | | | |
| **合计** | **179** | **60,970** | | | |
