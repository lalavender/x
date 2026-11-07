# F4 完成记录：`comptime` 收窄为纯 CT 执行器（2026-11-06）

合并记录了三份计划文档的落地结果：
`yh-F4-comptime纯执行器实施方案`、`yh-F4收尾-gen消失方案`、
`yh-GEN4-TaskCtx拆分方案`。三份计划文档已按约定从 `docs/02-plan/` 删除。

## 1. 结果一览

| 指标 | F4 起点 | F4 结束 |
| --- | ---: | ---: |
| `comptime → gen` 依赖符号 | 594 处 `gen.` / 19 白名单符号 | **0** |
| `gen` 模块 | 8 文件 / 2,550 行 / 82 pub fn | **已删除** |
| `TaskCtx` 字段 | 189 | **0**（模块本身已删） |
| `gen.task()` 调用点 | 250+ | **0** |
| `import gen` 模块 | 13 | **0** |
| `comptime` 的允许依赖 | `gen, proj, token, support` | **`support, token`** |
| 模块数 / 依赖边 | 19 / 93 | **18 / 78** |
| `arch-check` 自测 | 5/6 | **6/6** |

`comptime` 现在是**纯 CT IR 执行器**：不再有任何语义表所有权的外溢，
读语义事实只经零拷贝镜像（槽绑定），诊断只经 `ct_err`。

## 2. 关键设计决策

### 2.1 零拷贝镜像 + 槽绑定（而不是复制表）

执行器需要类型/符号/字段/静态数据的形状。做法是与 `support` 的结构**逐字段
同序同宽**的镜像结构（`CtTypeRow`/`CtSymRow`/`CtFieldRow`/`CtStaticRow`/
`CtImportRow`），绑定时只传**槽地址**（`&ms().types` 这类 `**T`），读时解引用：

- 表扩容/搬迁后自动跟随（复制会在解析期扩容后立刻过期）
- 绑定一次即可（`check.ct_facts_sync()`），形状漂移由 `check.ct_type_layout_ok()` 断言

### 2.2 语义动作归 `check`，值内核归叶子

`comptime` 需要隐式转换判定与常量折叠，但 `comptime → check` 会成环
（`check → comptime` 已存在）。因此分两类：

- **语义动作**（`ty_*`/`sym_*`/`scope_*`，会写表并发带位置的诊断）→ `check/symbols.yh`
- **值规则**（纯计算）→ `support`；其中三个函数原本靠 `token.err_tok` 报位置，
  改为**返回错误码**（`VK_*`）+ 调用层格式化（`check` 用 `token.err_tok`，
  `comptime` 用 `ct_err`），文案表 `vk_msg()` 放 `support` 保证不漂移

这就是「`gen` 消失」的最后一刀，见 `compiler/support/value_kernel.yh`。

### 2.3 `TaskCtx` 按所有者拆解（GEN4）

| 组 | 字段 | 去向 |
| --- | ---: | --- |
| 模型表（类型/签名/具名类型/归属） | 30 | `support/model_store.yh`（`ms()`） |
| 符号表 + 作用域栈 | 5 | 同上 |
| 模块/导入 | 15 | `support/file_scope.yh`（`fs()`） |
| ABI 分类 | 6 | `support/abi_model.yh` |
| 发射计数 | 7 | 阶段 1 删死字段 + 阶段 6 随临时态迁走 |
| 解析临时态 | 82 | `support/task_ctx.yh`（`fc()`） |

放 `support` 而不是 `parse` 的原因：85 个临时字段里 **61 个被 `check` 读写**，
而 `parse` 依赖 `check`——搬进 `parse` 会让 `check → parse` 成环。`support` 是
唯一对所有消费方都合法的无环落点（它也因此成了「共享数据层」）。

## 3. 排错记录（值得记住的坑）

| 现象 | 原因 | 修法 |
| --- | --- | --- |
| `token -> gen -> token` 环 | `token` 曾 `import gen` 读任务态 | 词法游标改 `lex.LexCtx`；`token` 只依赖 `support` |
| `support -> token -> support` 环 | 值内核需要 `TK_*` 运算符码，而源在 `token` | 运算符码（64..96）源头移到 `support/model.yh`，`token` 转发 |
| `comptime -> check -> ast -> comptime` 环 | 自动导入脚本按注释里的 `check.` 加了 `import check` | 导入判断只看代码（去注释） |
| 越界依赖 `lower -> link` | `lower` 的局部变量名叫 `link`（AST 节点） | 删除误加的 import |
| `arch-check` 预算形同虚设 | 预算值留在 82/13 而上限替换没命中 | 预算与实测齐平（3→0），并纳入 `max_globals` 注释整理 |
| `gen.TargetInfo` 到处引用 | 该类型早已迁 `support` | 统一改 `support.TargetInfo` |

## 4. 门禁现状与遗留

| 门禁 | 结果 |
| --- | --- |
| `cd compiler && YH_CACHE=off ../yh check` | 通过 |
| `python3 tools/arch-check.py` | 通过（18 模块 / 178 文件 / 78 边 / 两条白名单 0） |
| `python3 tests/tools/arch-check/check.py` | 6/6（含「塞回 `gen/` 必须红灯」「`comptime→check` 必须红灯」） |
| `python3 tests/modules/build-check.py` | 88/128（40 例为本地 LLVM 迁移既有失败，与本次无关） |
| fixtures（`support`/`ctfacts`/`llvmlower`/`llvmchecked`/`astcheck`） | 全绿 |

**未验证项**：改动了 23 条折叠/转换诊断的**产生路径**（从 `gen.sem_err` 改为
`support` 错误码 + `check`/`comptime` 格式化）。本地 `./yh` 是预构建种子，`just`
全链路被 LLVM SDK 的 `libSystem.tbd`（`arm64e.x1`）卡住，因此
`tests/yh-run/fail/73..79` 的**位置前缀**尚未在重新构建的编译器上复验。
恢复 `just` 后应第一时间补跑 `just test` 专门确认这 7 例。

## 5. GEN3 收尾（与 F4 同批完成的验收项）

GEN3 的原判据是「清 `gen` 语义残片/空壳 + 调用面切换」。逐项核对：

| GEN3 判据 | 结果 |
| --- | --- |
| `import gen` = 0（除 `gen` 自身） | ✅ 0 |
| `gen` 行数 < 500 | ✅ 模块已删除（0） |
| `lower` / `builtin` 改 import `check` | ✅ |
| `backend` 用 `support.ABI_*` | ✅ |
| `build` / `cmd` 改调 `check` 入口 | ✅（`check.checked_module_capture`/`verify`/`sem_init_tables`） |
| 删除 `gen.front_stage`/`sem_*`/`ty_*`/`sym_*` | ✅ |
| `arch-check` 收紧 `gen` 预算 | ✅ `max_gen_pub_fns`/`max_gen_importers` = 0 |
| 新增 `tests/modules/projects/gen-split/` | ✅ 本轮补上（见下） |

**新增 fixture `gen-split`（`gen3-split-narrow-ports`）**：只 `import
support/token/check`，覆盖拆分出来的六组公开面——会话/语义表初始化、
token 写入与游标、名字池 intern、类型表构造（ptr/array/slice）、目标身份解析、
诊断入口（`err_lc` 计数 / `err_tok` 的 spec 静默）。任何 `gen.` 回归都会
直接编译失败。注册在 `tests/modules/build-check.py`（用例数 128 → 129）。

## 6. 相关文档

- 模块职责清单：`docs/03-design/yh-模块职责-当前实现.md`
- 架构分层与依赖规则：`docs/03-design/yh-架构设计.md`
- 拆分动因：`docs/adr/0021-yh-gen职责拆分.md`
- F2（`parse` 纯语法化）的可行性结论与「核收缩」替代路线：
  `docs/01-finished/yh-F2-核收缩与parse纯语法化结论-2026-11-06.md`
- ADR-0021（gen 职责拆分，含 GEN0–GEN4 判据）：`docs/adr/0021-yh-gen职责拆分.md`
