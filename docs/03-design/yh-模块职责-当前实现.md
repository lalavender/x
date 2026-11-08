# yh 编译器模块职责（当前实现）

基线：`llvm` 分支（0.0.12 + C0–C6 + GEN1–GEN4 + F4），**18 个模块 / 178 个文件 /
60,717 行**，依赖边 78 条（不含标准库 `hash`/`libs`/`os`）。
实测：2026-11-08（HEAD `532d2c2`，`just code-stats` + `arch-check`；临时诊断
提交已清理）。

本文是「每个模块干什么」的唯一清单；分层理由与历史决策见
`docs/03-design/yh-架构设计.md`，拆分动因见 `docs/adr/0021-yh-gen职责拆分.md`。

## 1. 分层总览

```
L6  cmd（CLI 分派）        testkit（yh test runner）
L5  build（构建编排）      cmdline（参数解析）
L4  link（链接驱动）
L3  backend（LLVM IR 发射）
L2  lower（IR 降低）       parse（语法分析）   builtin（内建登记）
L1  check（语义中心）      comptime（CT 执行器） ast（语法树）  proj（项目模型）
L0  support  token  ir  cache  lex
```

依赖只能**向下**（箭头指向被依赖方），由 `tools/arch-check.py` 的 `ALLOWED` 表强制；
越界即红灯。`support` 与 `ir` 无依赖，是所有模块的公共底座。

## 2. 逐模块职责

### L0 基础层

| 模块 | 规模 | 依赖 | 职责与关键入口 |
| --- | --- | --- | --- |
| **support** | 28 / 3,151 | — | 叶子内核。①基础设施：源缓冲 `src_ctx`、名字池 `pool_ctx`、诊断 `fail`/`err_lc`/`fail_path`、`append_*`/`alloc`、会话开关 `session()`、目标身份 `TargetInfo`/`cfg()`、ABI 常量。②**跨层共享数据层**（GEN4/F2 下沉）：`ModelStore`(`ms()`，类型/签名/具名类型/符号/作用域表)、`FileScope`(`fs()`，模块归属+导入表)、`FrontCtx`(`fc()`，前端瞬时态 85 字段)、`tables`(字符串标签/枚举成员)、`symbols`(纯查询)、`value_rules`(纯值规则)、`value_kernel`(错误码式值内核)、`layout`、`static_data`、`abi_model`、`front_stage`。③平台变体 `argv/clock/console.*` |
| **token** | 3 / 268 | support | 词法/语法共享词汇：`TK_*`/`TOK_*`/`ATTR_*` 常量、`Tok`、`PDecl`、token 数组与游标 `ctx()`、`err_tok`（唯一带位置诊断入口）、`is_assign_op` |
| **ir** | 10 / 5,385 | — | 后端无关 SSA IR：`IRModule`/`IRFunction`/`IRInst`/类型与值模型、构建器、verifier、序列化（`ssa_module_*`）。不依赖任何模块 |
| **cache** | 7 / 1,047 | support, token | 内容寻址缓存原语：ActionID/OutputID、缓存键 schema、全局 store（C4）、跨平台文件锁（C6）。位于 check/lower 之下，避免二者为共享键原语互相 import |
| **cmdline** | 1 / 661 | support | 命令行声明与解析（驱动 `libs/cli`）、中文帮助生成、`YH_VERSION_TEXT`（`--version` 唯一来源） |
| **lex** | 4 / 1,051 | support, token | 词法器：扫描、插值字面量切分、布局（隐式 `;` 插入）、`LexCtx` 行列游标 |

### L1 语义与前端数据

| 模块 | 规模 | 依赖 | 职责与关键入口 |
| --- | --- | --- | --- |
| **proj** | 4 / 1,457 | support, token | 项目模型：`project.toml` 解析、模块/文件表、三层名字解析（本项目 → 标准库 → 依赖）、产物与 `[link]` 配置。前端与构建层共用的数据层 |
| **ast** | 6 / 1,351 | comptime, proj, support, token | 语法树 arena + 只读视图：声明索引、语句/表达式节点、函数上下文、绑定、捕获开关。**纯语法，不 import check**（check 依赖它） |
| **comptime** | 14 / 5,978 | support, token | 编译期执行器：CT IR 模型与求值、布局图、静态数据、函数注册表、枚举/浮点、CT 诊断。语义事实经**零拷贝镜像** `ct_facts` 读（槽绑定，`check.ct_facts_sync` 填入），不 import check。F4 收尾后不再依赖 `proj`（文件表窄口改由 `parse` 传入） |
| **check** | 15 / 6,040 | ast, cache, comptime, ir, proj, support, token | **语义中心**：①类型/符号表操作 `symbols.yh`（F2-K2 自 gen 迁入的 25 个语义动作）②语法→语义两遍（`sem_*`）③C ABI 分类 `abi_c` ④受检快照 `CheckedModule`：捕获/校验/切片/键/视图 ⑤CT 镜像绑定点 `ct_bind` ⑥值内核诊断适配 `value_kernel.yh` |

### L2/L3 前端装配与降低

| 模块 | 规模 | 依赖 | 职责与关键入口 |
| --- | --- | --- | --- |
| **parse** | 14 / 9,626 | ast, check, comptime, ir, lex, proj, support, token | 语法分析：声明/语句/表达式/类型、comptime 语法、全局初始化、模块导入；**接口 `.s.i`/`.s.ct` 的发射与加载**也在这里。历史设计是「边解析边求值」——直接调用 `check` 的语义动作（277 处 `Res` 语义耦合，见 §5） |
| **builtin** | 1 / 171 | check, support | 语言内建：内建函数与内建类型登记、prelude 外部接口（含 Linux AArch64 `syscall6`） |
| **lower** | 16 / 5,991 | ast, cache, check, ir, proj, support, token | `CheckedModule` → `IRModule`：SSA 降低（表达式/调用/控制流/for-in/全局与静态数据）。只吃快照，**不 import parse/build** |

### L4 后端

| 模块 | 规模 | 依赖 | 职责与关键入口 |
| --- | --- | --- | --- |
| **backend** | 14 / 4,149 | ir, support | **唯一 LLVM 后端**：`llvm_emit_module(IRModule, target, out)` 发 LLVM IR 文本。分工见 §4。`llvm_bridge_emit` 调内嵌静态 LLVM 桥把文本编译为目标文件 |

### L5/L6 构建、链接、CLI

| 模块 | 规模 | 依赖 | 职责与关键入口 |
| --- | --- | --- | --- |
| **link** | 7 / 4,296 | backend, proj, support | 链接驱动：Darwin（内嵌 lld / 系统 `ld`）、Windows（`lld-link`）、进程调用与输出捕获、链接键与链接缓存。位于 build 之下（不得 import build） |
| **build** | 22 / 7,992 | ast, backend, builtin, cache, check, comptime, ir, lex, link, lower, parse, proj, support, token | 构建编排：会话初始化、模块图与调度（含 fork worker）、函数级 IR 缓存、LLVM 流水线与产物发布、全局缓存管理（`yh cache` 实现） |
| **testkit** | 1 / 1,606 | ast, build, link, parse, proj, support, token | `yh test` 的发现 / 构建 / 逐例执行 / 报告 |
| **cmd** | 11 / 497 | build, check, cmdline, lex, link, parse, proj, support, testkit | CLI 分派：`build`/`run`/`test`/`cache`/`list`/单文件编译…；只做「请求 → 调 build/check」，不实现业务 |

## 3. 依赖方向（实测 78 条边，2026-11-08）

| 模块 | 允许依赖 |
| --- | --- |
| support / ir | — |
| token | support |
| cache | support, token |
| lex | support, token |
| cmdline | support |
| proj | support, token |
| ast | support, token, proj, comptime |
| comptime | support, token, proj |
| check | support, token, proj, ast, comptime, cache, ir |
| builtin | support, check |
| parse | support, token, lex, proj, ast, comptime, check, ir |
| lower | support, token, proj, ast, check, cache, ir |
| backend | support, ir |
| link | support, proj, backend |
| build | 全部下层（15 个）+ cache |
| testkit | support, token, proj, ast, parse, build, link |
| cmd | support, proj, lex, parse, check, build, link, testkit, cmdline |

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
| `parse` 边解析边求值 | 内联读取 `Res` 语义字段 277 处（`type_id` 104、`ival` 71…），语法决策依赖语义结果 | 方案 `docs/01-finished/yh-F2-核收缩与parse纯语法化结论-2026-11-06.md` §3.5：改为「核收缩」，**已落地**（值内核迁 `support`，`gen` 已删除）；「纯语法 AST」确认属前端重构级，暂缓 |
| ~~`gen` 尚存 3 个 pub fn~~ | **已解决（2026-11-06）**：按「错误码 + 调用层格式化」拆开，值内核下沉 `support/value_kernel.yh`，`gen` 模块删除 | `docs/01-finished/finish-F4-comptime纯执行器-2026-11-06.md` 路线 A 已落地 |
| `support` 内涵膨胀 | 2,740 行里有大量 GEN4/F2 下沉的状态与纯规则 | 有意为之：它是唯一无依赖模块，跨层共享数据的唯一无环落点；若将来拆分，必须保持「叶子」性质 |

## 6. 规模速查

### 6. 规模速查（2026-11-08 实测）

| 模块 | 文件 | 行数 | 模块 | 文件 | 行数 |
| --- | ---: | ---: | --- | ---: | ---: |
| parse | 14 | 9,626 | support | 28 | 3,151 |
| build | 22 | 7,992 | testkit | 1 | 1,606 |
| check | 15 | 6,040 | proj | 4 | 1,457 |
| lower | 16 | 5,991 | ast | 6 | 1,351 |
| comptime | 14 | 5,978 | lex | 4 | 1,051 |
| ir | 10 | 5,385 | cache | 7 | 1,047 |
| link | 7 | 4,296 | cmdline | 1 | 661 |
| backend | 14 | 4,149 | cmd | 11 | 497 |
| token | 3 | 268 | builtin | 1 | 171 |
| **合计** | **178** | **60,717** |
