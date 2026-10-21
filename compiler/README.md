# compiler —— yh 自举编译器（.yh 源码）

> 0.0.3 起本目录是**主要开发编译器**（[ADR-0006](../docs/adr/0006-yh自举产物为主要开发编译器.md)、
> [ADR-0007](../docs/adr/0007-yh编译器使用源码模块.md)）：仓库已删除 C 版
> stage0 与 bootstrap，构建只依赖种子 `bin/yh-<平台>-<架构>`（上一版编译器二进制，
> 用 `make fetch-seed` 从 Release 下载，不入库）。
> 自举产物默认目标取编译器构建身份（qemu 下仍为进程架构），日常验证以
> `make selfhost-native` 为主门。

用 yh 语言写成的 yh 编译器。源码是 `project.toml` 项目（name = `yh`，
version = `0.0.5`，source = `.`），按 **gen / lex / parse / ast / check / comptime / cmd / ir / backend
多模块**组织，2026-10-20 新增 `check` 后共 **九个模块**、107 个 `.yh` 文件；
`ast/` 是 2026-10-12 自 parse 拆出的 AST 阶段，`check/` 承担 AST 一致性校验；
`ir`（目标隔离
SSA）与其它模块同为根项目普通模块，共同进入编译器构建与自举固定点。
校验视图生命周期与模块依赖见[check 拆分设计](../docs/03-design/yh-编译器check模块拆分设计.md)。

模块导出面按「只有别的模块真的用到才 `pub`」维护（2026-10-12 两轮：`pub`
声明 1048 → 585，随后 `struct`/`union`/`enum` 的 `pub` 改为可选并私有化 12 个
模块内部类型，接口 `.s.i` 63,160 → 39,990 → 36,633 字节）：仅模块内使用的
`fn`/`const`/类型不写 `pub`（`pub` 同时决定接口导出与 `.globl`）；私有类型
不得出现在本模块的 `pub` 签名、`pub` 字段或 `pub` 别名里；入口模块 `cmd/`
只保留 `main` 为 `pub`。规则见
[导出面收缩设计](../docs/03-design/yh-编译器模块导出面收缩设计.md)与
[模块私有类型设计](../docs/03-design/yh-模块私有类型设计.md)。

```
bin/yh-<平台>-<架构>（Release 种子）──yh build──▶ yh ──自编──▶ yh'（固定点：模块 .s/.s.i 逐字节相同）
```

## 构建与验证

```bash
make fetch-seed         # 首次：从 Release 下载本平台种子到 bin/
make                    # 用 bin/yh-<平台>-<架构> 冷编本目录项目，产出仓库根 yh
make test               # 三层回归：ANTLR 语法 + 编译器语法模式 + 运行语义
make selfhost-native    # 本机主门：两代固定点 + 自解析 + 全量语料 + 模块/项目验收
make code-stats         # 统计 compiler/ 下 yh 源码规模
make seed               # 滚种子（仅在 test 与 selfhost-native 全绿后执行）
```

`make` 的产物形态随宿主（Darwin → Mach-O arm64，Linux → ELF），链接走
系统 gcc/clang，不需要运行时库或额外环境变量。可直接用于编译 `.yh` 程序
与跑语料：

```bash
python3 tests/yh-run/check.py --compiler $PWD/../yh
```

`make selfhost-native` 由 `tests/selfhost/native-selfhost.py` 执行本机全套
自举门（滚动自举，无 stage0；种子 = `make fetch-seed` 取得的 `bin/yh-<平台>-<架构>`）：

    bin/yh-<平台>-<架构> build compiler/  → cc2（冷编）
    cc2     build compiler/ → cc3（冷编）
    cc3     build compiler/ → cc4（冷编，固定点对比）

门：①固定点——cc3/cc4 全部模块 `.s`/`.s.i` 逐字节一致；②cc4 自解析
compiler/ 全部源文件；③cc4 语法语料（`tests/yh` 正例全过、反例全拒）；
④cc4 运行语料（`tests/yh-run` 全量 run/fail/pass，2026-10-13：299 例）；
⑤模块语料（`tests/modules/check.py` 18 例）；⑥项目验收
（`tests/modules/build-check.py` 106 例）。滚种子前必须全绿。

## 模块与文件职责

**lex** —— 词法

| 文件 | 职责 |
| --- | --- |
| `lex/lexer.yh` | 字节词法器：保留字、数字/转义、注释、运算符最长匹配 |

**parse** —— 语法（含顶层声明两遍处理）

| 文件 | 职责 |
| --- | --- |
| `parse/parse_type.yh` | 类型引用解析 + 解析器共用游标工具 |
| `parse/parse_expr.yh` | 表达式优先级链、后缀链、structInit 与「字面量 vs 块」消解 |
| `parse/parse_stmt.yh` | 语句：块/if/for/switch/return/goto/标签/赋值 |
| `parse/parse_decl.yh` | 顶层声明两遍处理：let/const/fn/type/struct/union/enum |
| `parse/parse_global_init.yh` | 全局聚合变量初始化（命名/位置/嵌套/字符串字面量） |
| `parse/parse_module.yh` | 模块头解析：`module` 声明、`import NAME (as ALIAS)?;` |
| `parse/iface.yh` | 模块接口与私有性：跨模块可见边界 |

**ast** —— AST 阶段（2026-10-12 自 parse 拆出，独立编译单元）

| 文件 | 职责 |
| --- | --- |
| `ast/ast_decl.yh` | 从 PDecl 索引建立文件级声明节点并关联函数体 |
| `ast/ast_expr.yh` | `yh check` typed 表达式 AST、绑定与常量快照 |
| `ast/ast_stmt.yh` | `yh check` 迁移期语句树、绑定关联与编译期 `$for` 模板目录 |
| `ast/ast_function.yh` | 函数在 AST arena 中的范围与绑定身份 |
| `ast/ast_view.yh` | 为外部只读校验借出 arena 视图，不转移所有权 |
| `ast/module_snapshot.yh` | `CheckedModule` 快照数据模型、捕获/释放与有界读取 |
| `ast/module_snapshot_view.yh` | 为外部快照校验借出只读视图，不转移所有权 |
| `ast/module_snapshot_ctx.yh` | 纯快照 lowering 的循环、控制流、标签与函数上下文 |
| `ast/module_snapshot_lower.yh` | 将受检快照转换为模块 IR 的主体 lowering |
| `ast/module_snapshot_forin.yh` | `for-in` 循环 lowering 辅助 |
| `ast/module_snapshot_global.yh` | 全局对象类型、初始化值与引用 lowering |
| `ast/module_snapshot_static.yh` | 静态数据、字符串与重定位 lowering 辅助 |
| `ast/module_snapshot_template.yh` | 编译期 `$for` 模板 lowering 辅助 |
| `ast/ast_ir.yh` | builder 指令表辅助（LL12：旧 SSA 编排已退役） |
| `ast/ast_ir_build.yh` | 受支持函数的 AST → typed SSA 构造器 |
| `ast/ast_ir_call.yh` | 固定参数直接调用的目标符号、变长实参与 AST 降低 |

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

函数体 `$if/$for` 的解析和作用域接缝位于 `parse/parse_comptime.yh`；
typed 执行器覆盖标量（含浮点）、指针（取址、解引用、算术与下标）、整型/浮点/结构体元素
数组与切片、受支持结构体/联合体值，分支、循环、诊断、整数 `switch`、递归调用及共享执行预算。
早期 token 求值器（`ct_eval_expr.yh`、`ct_eval_bool.yh`）与数组长度 token 探测链已删除：
typed IR 是唯一执行器，正文不在支持子集内的编译期函数直接报
「编译期函数正文不在受支持的 typed IR 子集内」。顶层整数常量与数组长度的编译期调用
统一交给 pass2a 之后的 typed 布局常量依赖调度（早期快路径只在 `ct_is_prepared` 已就绪时生效）。
单文件入口与函数 AST 的统一仍在待办中。

**gen** —— 语义与后端

| 文件 | 职责 |
| --- | --- |
| `gen/model.yh` | token 常量、类型/符号常量、Tok/Res/CType/CSym 等结构、全部全局状态 |
| `gen/buffer.yh` | 源文件整读（open/read/close）、汇编输出缓冲、诊断、字节写出 |
| `gen/symbols.yh` | 名字池、类型表、符号/作用域、类型兼容、常量折叠、prelude 登记 |
| `gen/target.yh` | 目标数据模型：字长、对齐、结构体布局（**换平台的第一步**） |
| `gen/sem_value.yh` | 字面量/标识符求值、常量折叠与值类别（LL12：无发射） |
| `gen/sem_expr.yh` | 表达式语义：下标、成员、运算、转换、切片（LL12：无发射） |
| `gen/sem_decl.yh` | 声明语义：符号登记、结构体布局与函数参数/返回事实 |
| `gen/sem_flow.yh` | 控制流语义：类型检查、循环上下文与可达性（LL12：无跳转发射） |
| `gen/sem_call_literal.yh` | 调用点语义：实参检查、变参打包记录与结果形态（LL12：无搬运） |
| `gen/abi_c.yh` | 共享 AArch64 C ABI 分类：值描述、HFA、寄存器与目标栈布局 |

**ir / backend** —— 受检函数的独立表示与目标发射

| 文件 | 职责 |
| --- | --- |
| `ir/ssa.yh`、`ir/ssa_call.yh` | typed SSA、整数转换、CFG/verifier 与直接调用契约 |
| `ir/ssa_serialize.yh` | 含调用目标与实参的稳定 IR 编码 |

**cmd** —— CLI 与项目管理

| 文件 | 职责 |
| --- | --- |
| `cmd/driver.yh` | `main(argc, argv)`、参数分派、`check` / `--syntax-check` / `--emit-asm` |
| `cmd/compile.yh` | 单文件编译模式（`yh -o out file.yh`） |
| `cmd/toml.yh` | `project.toml` 解析与 schema 诊断（未知字段、必填项、行号） |
| `cmd/project_state.yh` | 项目状态：根发现、源码根扫描、模块索引 |
| `cmd/project_index.yh` | 清单 schema 校验与字段提取（name/version/author/source/dependencies） |
| `cmd/project_resolve.yh` | 三层来源解析（当前项目 / 标准库 / 直接依赖）与 import 绑定 |
| `cmd/module_build.yh` | 项目构建编排、模块缓存与过渡期 `check` |
| `cmd/build_scheduler.yh` | 有界 fork worker、继承只读项目快照、接口就绪调度与本轮接口隔离 |
| `cmd/clock.*.yh` | `--stats` 阶段耗时；Darwin 单调时钟 API 与 Linux arm64 clock syscall |
| `cmd/process.yh` | 用 `fork/execvp/waitpid` 按 argv 启动宿主进程，不经 shell |
| `cmd/link_cache.yh` | 模块对象与最终程序的内容缓存、内嵌 lld/外部驱动链接 |

普通配置默认不登记 `system(cmd)`；`--legacy-system` 为迁移期显式兼容开关。
自举构建使用默认配置。编译器入口接收 `envp`，直接读取 `PATH` 与
`YH_STDLIB`；构建与临时目录使用 `mkdir` OS API。项目目录扫描由 Darwin
`getattrlistbulk` 与 Linux arm64 `getdents64` 适配完成，
不再调用 `/bin/ls`；Linux 系统调用经 LLVM 运行时入口完成。系统汇编器/链接器与
`malloc`、`free` 等 C 服务由 LLVM 运行时与内嵌 lld 承担；LL12 已删除旧 arm64
内存运行时发射。

`compiler/ir/` 是独立的模块 IR 子项目，由 `compiler/project.toml` 以本地 path
依赖引入，也由 `tests/modules/projects/irverify/` 直接依赖并运行验收。
LL12 后受检快照统一经 `ast/module_snapshot_lower.yh` 降低为 `ir.IRModule`，
再由 `backend/llvm_*.yh` 发 LLVM 文本；旧「函数级 SSA + 汇编替换」链已删除，
`ast/ast_ir*.yh` 只保留 builder 底层与共享调用缓冲。

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

## 架构与多平台

后端分三层：前端语义（`gen/symbols.yh` + `gen/sem_*.yh` +
`parse/parse_*.yh` + `ast/ast_*.yh` + `check/verify.yh`）→ 受检快照/模块 IR
（`ast/module_snapshot*.yh`、`ir/ssa_module_*.yh`）→ LLVM 发射
（`backend/llvm_*.yh` + 内嵌桥）。前端不持有 ISA 状态；换目标 = 目标身份 +
对应 LLVM 目标库。LL12 已删除 `em_*` 抽象机原语与旧 arm64 发射器，
历史架构见[自举后端架构](../docs/03-design/yh-自举后端架构.md)。

## 自编子集与已知边界

编译器自身源码遵守的自举子集：整数/字节/指针、结构体字段、堆缓冲、
全局/局部变量、普通函数、递归、`if` 与条件 `for`（无限循环写
`for 1 { }`）、赋值与位运算、`sizeof(T)`、prelude 的
open/read/write/close/malloc/free/memcpy/strlen/exit。

**已知边界**（详见 [自举后端架构 §7](../docs/03-design/yh-自举后端架构.md)）：

- 切片越界与生命周期运行时防护不做（[ADR-0001](../docs/adr/0001-yh数组按值调用边界.md) 既定）。
- 浮点参数超过 8 个（超出 d0-d7）未实现。
- 裸 C 变参 `...` 在用户源码被显式拒绝，仅编译器内置 prelude 使用。
