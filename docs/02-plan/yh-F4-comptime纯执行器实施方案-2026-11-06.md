# F4 实施方案：`comptime` 收窄为纯 CT IR 执行器

日期：2026-11-06。状态：**待实施**。前置：GEN1/F1/F3 首片已完成
（见 [ADR-0021](../adr/0021-yh-gen职责拆分.md)、[finish](../finish.md)）。

## 0. 为什么必须先做 F4

`gen` 现在还剩下**语义模型**（`CType`/`CSym`/`TY_*`/`ty_*`/`sym_*`/
`data_str_*`/`em_*`/`static_data_*`/`value_rules`）。按 ADR-0021 它们应归
`check`，但 `comptime` 直接调用这些规则（实测 183×`sem_err`、81×`task`、
72×`TaskCtx`、约 200×类型规则）。若先把模型搬 `check`，会立刻形成
`check → comptime → check` 环，所以顺序只能是：

```text
F4（comptime 拿事实、不再 import gen 的语义）
  → 语义模型一次性迁 check（gen 只剩 TaskCtx + 别名）
  → F2（parse 纯语法）
  → GEN4（拆 TaskCtx、删 gen）
```

## 1. 目标与验收

**目标**：`comptime` 的 `import` 只剩 `support`（必要时 `proj`），
不再出现 `gen.ty_*`、`gen.sem_*`、`gen.sym_*`、`gen.static_data_*`、
`gen.task()`。

**验收**：

- `rg "gen\." compiler/comptime` 只剩注释（当前 594 处）。
- `arch-check` 的 `comptime` 允许边收紧为 `{support, proj}`。
- 全量语料 + `tests/yh-run` + `modules` 与改动前逐例一致（行为不变）。
- `check`/`lower` 的 CT 相关用例（`llvmlower` fixture 的 `$for`/`$field`）
  全部通过。

## 2. 事实视图：零拷贝镜像（**不用复制**）

新增 `comptime/ct_facts.yh`（**字节序最早**：`ct_facts.yh` < `ct_ir.yh`）。
原计划的「复制平行数组」已被否决：解析期类型表还在增长，复制会立刻过期。
改为**镜像结构 + 指针绑定**，与 `ast`/`comptime` 现有的
`sizeof(AstExpr) == sizeof(comptime.CtExpr)` 守卫同一套路：

```yh
// comptime/ct_facts.yh
pub struct CtTypeRow {   // 与 gen.CType 逐字段同序同宽
    kind int
    size int
    align int
    elem int
    len int
    sub int
}
let ct_type_rows *void = 0   // 指向 gen.task().t_types（不拥有）
let ct_type_n int = 0
pub fn ct_types_bind(rows *void, n int) void
pub fn ct_ty_kind(tid int) int / ct_ty_size / ct_ty_align / ct_ty_elem / ct_ty_len / ct_ty_sub
pub fn ct_ty_is_integer(tid int) int / ct_ty_is_float / ct_ty_is_signed / ct_ty_is_scalar
```

- **谁绑定**：`check` 暴露 `ct_types_sync()`（唯一能看到 `gen.task()` 的地方），
  CT 入口（`comptime.ct_call`、`ct_ir_run`、`ct_layout_*`、`ct_enum`、
  `ct_global_agg`、`ct_static_data`）在进入前调用一次；绑定只是写两个标量，
  不复制表，指针随类型表扩容自然更新。
- **形状守卫**：`check` 提供 `ct_type_layout_ok()`，比较
  `sizeof(gen.CType) == sizeof(comptime.CtTypeRow)` 且字段偏移一致；
  `verify_checked` 与 `comptime` 的首次绑定处断言，漂移即失败。
- **符号/静态数据**同法：`CtSymRow`（`gen.CSym` 镜像）与
  `CtStaticRow`（`gen.StaticDataObject` 镜像），同样「指针 + 行数」绑定。
- 结构体布局：`gen.tg_layout_struct` 已把结果写回 `t_types[tid].size/align`，
  执行器经镜像读到最新值，不需要额外同步。
- 禁项：`ct_facts.yh` 不持有表的所有权，也不 `free` 绑定的指针。

## 3. 诊断与任务态

| 现在 | 改成 |
| --- | --- |
| `gen.sem_err(msg)`（183 处） | `support.err_at(ct_frame_line, ct_frame_col, msg)`；行列由 frame 记录（`ct_diag.yh` 已有来源位置） |
| `gen.task().c_ct_expand_*` | 已在 `support.diag()`（GEN1 迁出），直接读写 `support.diag()` |
| `gen.task()` 的其余 81 处（`c_data_n`、`c_syms`、`c_ct_*`、`c_layout_*`…） | 逐项归类：CT 值/布局 → `CtFrame` 或 `CtTypeView`；全局字符串标签 → `support` 的 `data_str` 视图（见 §4） |

## 4. 字符串标签与常量折叠

- `gen.data_str_lookup` / `gen.data_str_restore`：把标签→字节表的**只读视图**
  放进 `CtStaticView`（`label/off/len/quoted` 平行数组），`comptime` 不再
  调 `gen`；`check` 负责登记。
- `gen.sem_fold_const_binop/unary`、`sem_fold_norm`、`sem_fold_fp_to_int`、
  `sem_res_const`、`fp32_bits`/`fp64_bits`：这些是**值规则**，`comptime`
  与前端共用。F4 的目标是把它们从 `gen` 移到 `check`，`comptime` 改为
  「折叠请求进 CT IR、结果由 check 计算」——即 CT IR 增加
  `CT_OP_FOLD_BINOP/FOLD_UNARY` 两个节点类型，执行器把操作数与 op 写回
  frame，由 `check` 在 expand 循环里求值。
- 若该步工期超预期，可先保留 `gen/value_rules.yh`（当前形态）——它不含
  类型表/符号表，`comptime → gen` 的边仍存在但**只剩 8 个纯值函数**；
  §1 的验收改为「`gen.` 引用只剩 `value_rules` 的 8 个函数」。

## 5. 分步与提交边界

| 步 | 内容 | 验收 |
| --- | --- | --- |
| F4-0 ✅ | `ct_facts.yh` 镜像 + `check.ct_types_sync`/`ct_type_layout_ok` + `ctfacts` fixture 差分 | 已实跑 `ct-facts=ok rows=13` |
| F4-1 | 镜像改绑定槽（扩容免疫）；`check.ct_types_sync`/`ct_type_layout_ok`；`comptime` 的 58 处 `gen.ty_is_*` 与 18 处 `CType` 字段读改镜像 | `rg "gen\.ty_is_|gen\.CType" compiler/comptime` = 0；全语料一致 |
| F4-2 | `CtSymView`；`gen.CSym`/`SYM_*`/`F_*`/`sym_*` 改视图 | 同上 |
| F4-3 | `CtStaticView` + 字符串标签视图；`static_data_*`/`data_str_*` 改视图 | 同上 |
| F4-4 | 诊断改 `support.err_at`；`gen.sem_err`/`gen.task` 清零 | `rg "gen\." compiler/comptime` 只剩注释 |
| F4-5 | 折叠请求进 CT IR（若采用）；否则把 `value_rules` 8 函数留在 gen 并在 ADR 登记 | §1 验收二选一 |

每步都是「纯移动 + 视图替换」，产物应逐字节一致；`just test` +
`just selfhost-native` 全绿后才进下一步。


## 7. 实施进展与剩余边界（2026-11-06 实测）

已完成：F4-0、F4-1、F4-2、F4-3 首片（字段/诊断常量）、F4-4 首片。
`comptime` 的 `gen.` 引用（去注释）从 **594 → 62**。

剩余 62 处分两类，**都不是机械替换**：

### 7.1 读型事实（可镜像，但需新的槽）

| 剩余 | 数量 | 做法 |
| --- | --- | --- |
| `static_data_at` | 1 | 加 `CtStaticRow` 镜像（`sym_id/label/type_id/elem_type/count/size/align/data/relocs`） |
| `em_find_src`/`em_get_val`/`em_get_ready` | 3 | 加 `CtEnumRow` 镜像（名字池偏移 + 值 + 就绪位） |
| `data_str_lookup` | 1 | 加 `CtStringRow` 镜像（`label/off/len/quoted`） |
| `sym_ct_lit_text`/`sym_declared_before` | 2 | 前者是「沿引用链找字面式」的规则，建议随 F4-5 走请求；后者读声明窗口，可镜像 `def_line/def_col` |

### 7.2 写型调用（镜像做不到，必须走「请求/应用」）

CT 执行期会**改写**前端语义表，只读镜像无法表达：

| 剩余 | 数量 | 建议 |
| --- | --- | --- |
| `static_data_add`/`static_data_scalar`/`static_data_reloc`/`static_data_reset` | 5 | CT 把「静态数据请求」写进 `CtStaticRequest` 列表，由 `check` 在 expand 循环末尾统一应用 |
| `ty_push_agg`/`ty_array` | 3 | 同理：CT 记录「需要这个数组/聚合类型」，由 `check` 建型并回填 type_id |
| `sym_declared_before` 之外的 `sem_struct_finish` | 1 | 布局收尾改由 `check` 在 expand 后统一做 |

### 7.3 值规则（F4-5）

`sem_can_assign`(12)、`sem_fold_const_binop`(2)、`sem_fold_const_unary`(1)、
`sem_fold_norm`(5)、`sem_fold_fp_to_int`(1)、`sem_res_const`(4)、
`fp32_bits`/`fp64_bits`(8)、`Res`(3) ≈ **36 处**。

两条路线：

- **A（推荐，代价小）**：保留 `gen/value_rules.yh`（8 个纯值函数 + `Res` 类型），
  在 ADR 登记为「编译期值语义内核，`comptime` 与其唯一允许的 gen 依赖」，
  `arch-check` 把 `comptime → gen` 的允许符号白名单收紧到这 8 个。
- **B（彻底，代价大）**：CT IR 增加 `CT_OP_FOLD_*` 节点，执行器只写操作数，
  由 `check` 求值回填；`Res` 换成 `CtValue`。

**已采用 A 并在 `arch-check` 落地**：`GEN_SYMBOLS_FOR_COMPTIME` 白名单
（只减不增；2026-11-06 由 19 降到 **18**），注入新依赖的副本会被自测抓到。

已摘除的债务（同一白名单只减不增）：

| 符号 | 做法 |
| --- | --- |
| `sym_declared_before` | `ct_sym_declared_before` 直接在 `CtSymRow` 上判 `def_line/def_col`（镜像侧纯读） |

## 6. 风险

| 风险 | 缓解 |
| --- | --- |
| `CtTypeView` 与 `CType` 字段漂移 | 视图由 `check` 唯一填充；`verify_checked` 增加「视图 n == store.type_n」断言 |
| 折叠请求改 IR 后性能下降 | 先做 F4-1..F4-4（不动折叠），单独测量后再决定 F4-5 |
| `comptime` 仍有 594 处 `gen.` | 用脚本按符号分组逐组替换，每步 `yh check` + fixture 实跑 |
| 自举种子不认新文件 | 新增文件只加 `comptime/` 内，不改语法；种子已支持多文件模块 |
