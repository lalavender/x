# GEN4：`TaskCtx` 按所有者拆分（方案评审稿）

状态：**阶段 1–6 已完成**（2026-11-06）：`TaskCtx` 145 → **0**
上游：ADR-0021（gen 职责拆分）、`yh-F4-comptime纯执行器实施方案-2026-11-06.md`

## 1. 为什么现在做

链 A（F4）与链 B（TaskCtx）已经收敛到同一点：

- 链 A 剩余 13 个 `comptime → gen` 白名单符号里，`ty_push_agg`（写类型表）、
  `sym_ct_lit_text`（查名字池）、`task`/`TaskCtx` 四项都卡在「类型/符号表存储住在
  `TaskCtx`」；剩下 9 个值规则函数要迁 `check`，也同样需要表的所有者先明确。
- 链 B 的 `gen.task()` 调用点：`parse` 149 / `check` 66 / `comptime` 9 / `ast` 6 /
  `gen` 5 / `builtin` 2。`lex`/`link`/`proj`/`testkit`/`cache`/`lower` 已清零。
- `TaskCtx` 仍有 **145 个字段**，是整个仓库最大的单一状态块（`gen/state.yh` 430 行），
  任何模块想加一个前端状态都要往它身上挂。

目标不是「删掉 `TaskCtx`」，而是让它变成**组合根**：字段各自回到所有者模块的
单例 ctx，`gen.TaskCtx` 只保留仍然真的跨模块共享的少数几项，随后自然消失。

## 2. 实测字段归属（145 个）

按「谁写、谁读」分类（脚本对 `compiler/**` 全量扫描 `.字段名` 引用，排除 `gen`
自身后再人工判定）：

| 组 | 字段数 | 代表字段 | 目标所有者 | 判据 |
| --- | --- | --- | --- | --- |
| **M 模型表** | 30 | `t_types/t_type_n/t_type_cap`、`t_fields/*`、`t_sig_*`（14）、`t_names/*`、`t_home/*`、`c_aggtype_n`、`t_cur_enum`、`c_cur_struct`、`c_name_form` | `support`（新建 `support/model_store.yh`） | 纯数据表 + 容量，无解析逻辑；被 `parse`/`check`/`comptime`/`gen`/`lower`(经快照) 共用，放 `check` 会让 `comptime→check` 成环 |
| **S 符号表** | 5 | `c_syms`、`c_sym_n`、`c_sym_cap`、`c_scope_start`、`c_scope_n` | `support`（`support/model_store.yh` 同一文件） | 同上；`sym_push`/`scope_*` 等**操作**留 `check`，这里只搬存储 |
| **D 模块/导入** | 15 | `mod_has_module`、`mod_name_*`、`mod_imports/*`、`c_mods/*`、`c_iface_load`、`c_sym_sfx_*` | `proj`（新建 `proj/file_scope.yh`） | 项目/模块/文件身份是 `proj` 的既有职责（`proj_00_model.yh` 已持项目模型）；`parse`/`build` 经 `proj.*()` 读 |
| **A ABI 分类** | 6 | `c_cabi_cursor`、`c_aggparam_*` | `check`（`check/abi_model.yh` 已存在） | 只有 `check/sem_*` 与 backend 装配用；`ABICursor` 结构体已在 check 侧 |
| **E 发射计数** | 7 | `c_bss_syms/*`、`c_lbl_n`、`c_fn_lbl`、`c_ret_tmp_off`、`c_scratch_base` | `build`（新建 `build/emit_counters.yh`） | 只被装配/发射层读写；语义层不该知道汇编标签号 |
| **P 解析临时态** | 82 | `c_ct_*`(9)、`c_lit_*`(8)、`c_fi_*`(8)、`sc_*`(5)、`tn_*`(5)、`c_loop_*`(4)、`c_spill_*`(4)、`c_call_*`(4)、`c_arg_*`(4)、`c_ret_*`(3)、`c_fn_*`(5)、其余 | `parse`（并入 `parse.ParseCtx`） | 全部是「当前正在解析什么」的瞬时状态：函数体、调用收集、字面量、for-in、短路/三元标签栈、溢出槽、goto 标签 |

合计 30 + 5 + 15 + 6 + 7 + 82 = **145**。

引用面（同一脚本统计，145 个字段的去向）：

| 引用方集合 | 字段数 |
| --- | --- |
| 仅 `check` | 24 |
| 仅 `gen` | 21 |
| `check` + `gen` | 25 |
| 仅 `parse` | 13 |
| `check` + `parse` | 13 |
| `check` + `gen` + `parse` | 9 |
| 其他组合 | 35 |
| 完全无引用 | 5（`c_bss_cap`、`c_lbl_n`、`c_fn_lbl`、`c_ret_tmp_off`、`c_scratch_base`） |

> 「完全无引用」5 项是 LL12 删旧发射器后遗留的计数/临时槽，可在最后一步直接删；
> 先删除它们即可把基数从 145 降到 140，不影响任何行为。

## 3. 迁移顺序（每步都可独立编译、可回滚）

顺序原则：**先搬「只有数据、没有逻辑」的，再搬「有操作函数」的，最后改调用点**。

### 阶段 1：清掉 5 个死字段（145 → 140）✅ 已完成

- 删 `c_bss_cap`、`c_lbl_n`、`c_fn_lbl`、`c_ret_tmp_off`、`c_scratch_base`
- 验证：`yh check` + `arch-check.py` 的 `max_taskctx_fields` 收紧到 140
- 风险：低。若 `arch-check` 报「未使用字段」，说明判定错误，回退该项即可

### 阶段 2：模型/符号表存储下沉 `support`（140 → 101）✅ 已完成

- 新建 `compiler/support/model_store.yh`：`TypeStore`（t_types/t_fields/t_sig*/t_names/t_home）
  + `SymStore`（c_syms/c_scope_start）+ 继承来的 `support.ctx().store`
- 搬迁方式沿用已验证的**「槽 + 窄口函数」**模式（F4-1）：先让 `gen` 侧保留
  `g_state.task.t_types` 等字段的**指针别名**（`t_types` 仍指向同一块堆），再逐模块
  把 `tk.t_types` 换成 `support.store().types`
- 关键点：`TaskCtx.t_types` 这类字段先**保留**、由 `support` 写入，等所有读写点迁完
  再删字段；这样每一步都能编译
- 验证：`yh check`、`ctfacts`/`llvmlower`/`llvmchecked` 三个 fixture、`arch-check` 收紧
- 解锁：`ty_push_agg`、`sym_ct_lit_text`、`task`/`TaskCtx` 的镜像化前提

**实际落地**（比原计划多做两小步，因此是 140 → 101 而非 105）：

1. 新建 `support/model_store.yh`：`ModelStore`（35 个字段，含类型/签名/具名类型/
   符号/作用域，字段名改短：`t_types`→`types`、`c_syms`→`syms`…）+ `ms()` +
   `mstore_reset()` + `model_type_push()` + `model_type_push_agg()`（含 512 上限）。
   1,065 个读写点按「接收者 = `gen.task()`/`g_state.task`/`TaskCtx` 局部」脚本改写到
   `support.ms()`；`TName` 一并下沉到 `support/model.yh`。
2. `gen.ty_push` / `gen.ty_push_agg` 变成 `support.model_type_push*` 的转发，
   `comptime` 直接调 `support.model_type_push_agg` → 白名单去掉 `ty_push_agg`。
3. 四个前端模式位（`c_iface_load`/`c_ct_iface_mode`/`c_ct_origin_active`/
   `c_ct_origin_line`）下沉 `support.session()`。
4. CT 镜像补两块：`CtImportRow` + 导入表三槽（`ct_imports_bind/…`）、
   折叠开关/结果寻址两个标量槽（`ct_mode_bind/ct_fold_mode/ct_res_is_addr_set`）。
   → `comptime` 彻底不再出现 `gen.task()`/`TaskCtx`，**`TaskCtx` 101 字段、
   白名单 10**。

### 阶段 3：模块/导入下沉（101 → 85）✅ 已完成（改落 `support` 而非 `proj`）

- 新建 **`compiler/support/file_scope.yh`**：`FileScope`（module 归属 + 导入表 +
  已加载接口）+ `fs()` + `fscope_reset()`；`ImportEnt`/`ModNsEnt`/`ModInfo`
  三个结构体同批下沉（gen 留同名别名）。
  **改动理由**：`gen/symbols.yh` 的限定名解析也要读写这些字段，放 `proj` 会让
  `gen → proj`，反置「项目数据层在下」的既有分层；放 `support` 与
  `model_store` 一致，零新增依赖边。
- `parse` 的 `p_decl_module` / `mod_import_push` 改成写 `support.fs()`
- 验证：`build-check.py` 里所有多模块项目用例（`u2-*`/`u3-*`/`r2b-*`）必须与基线一致

### 阶段 4：ABI 分类下沉（✅ 已完成，改落 `support`）

- `c_cabi_cursor` + `c_aggparam_*` 并入 `check/abi_model.yh` 的 `ABIContext`
- 验证：`cabi-*` 用例 + `llvmlower`（ABI 快照）

### 阶段 5：发射计数（✅ 已完成：`c_bss_cap`/`c_lbl_n` 等已在阶段 1 删除，剩下 2 个 `c_bss_*` 随阶段 6 一起走）

- `c_bss_*`（.bss 清单）、`c_fn_lbl` 相关并入 `build/emit_counters.yh`
- 验证：`llvmprivate`（bss）、`r2a-*`（符号发射）

### 阶段 6：解析临时态整体下沉 `support/task_ctx.yh`（85 → 0）✅ 已完成

**实际做法（一次性而非分批）**：原计划搬到 `parse.ParseCtx`，实测 85 个字段里
**61 个被 `check` 读或写**，而 `parse` 依赖 `check`——搬进 `parse` 会让
`check → parse` 成环。`ast` 也读 2 个。唯一无环落点是 `support`：
新建 `support/task_ctx.yh`（`FrontCtx` + `fc()`），75 个字段原样搬、684 处
`gen.task().X` / `g_state.task.X` 脚本改写为 `support.fc().X`。
同时把 `ABICursor`/`ABIValue`/`CABI_*`（`gen/abi_model.yh`）与
`PubAggDeferred`/`GLabel` 一并下沉 `support`，`gen/state.yh` 只留
`data_str_*`/`em_*` 两张语义内核表，`TaskCtx`/`GenState`/`task()` 整体删除。
- 每批一个提交；`parse` 内部改 `parse.ctx().xxx`，`check` 侧若仍要读，改用
  `parse.ctx()` 只读窄口（`parse → check` 不允许，故这些字段迁完前不得被 `check` 写）
- 终局：`TaskCtx` 空 → 删 `gen/state.yh` 的 `TaskCtx`/`task()`，`gen` 只剩
  `model.yh`（别名）、`symbols.yh`、`value_rules.yh`、`abi_model.yh`、`target.yh`
- **然后**才把 `gen` 的剩余内容整体迁 `check`（F3 收尾），`import gen` 归零

## 4. 依赖方向约束（不可违反）

现状允许边：`parse → gen`、`check → gen`、`comptime → gen(白名单)`、`ast → gen`、
`builtin → gen`、`build → gen`、`cmd → gen`；`gen → support/token`。

本轮新增边必须是**下沉边**（`X → support/proj`），不得出现：

- `support → 任何上层模块`（`support` 是叶子）
- `comptime → check`（CT 执行器必须在 `check` 之下的白名单内）
- `proj → parse/check/build`

`arch-check.py` 的 `ALLOWED` 表要同步登记新边，`max_taskctx_fields` 每阶段收紧。

## 5. 成功判据

| 判据 | 目标 |
| --- | --- |
| `TaskCtx` 字段 | 145 → 0（分 6 阶段单调下降，每阶段收紧预算） |
| `gen.task()` 调用点 | 232 → 0 |
| `import gen` 模块 | 7 → 0 |
| `comptime→gen` 白名单 | 13 → 0 |
| `build-check.py` project cases | 不低于基线 88/128（既有 40 例为本地 LLVM 迁移环境问题） |
| fixtures（`ctfacts`/`llvmlower`/`llvmchecked`/`astcheck`/`support`） | 全绿 |

## 6. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 表指针在扩容后失效 | 沿用 F4-1 的**槽绑定**（`&store.types` 的地址），不复制表内容 |
| 一轮改太多无法定位回归 | 每阶段独立提交 + 每次只收紧一个 arch-check 预算 |
| `check` 写 `parse` 私有字段造成反向依赖 | 阶段 6 前先确认这些字段无 `check` 写点；有则先改成 `check` 侧自己的状态 |
| 自举种子不认新模块文件 | 新文件只放在既有模块目录内（`support/proj/build/parse`），不改语法 |
| 无法本地跑 `just` | 用 `yh check` + `arch-check.py` + `build-check.py` + 手工 fixture 重建作为门禁（已验证可行） |
