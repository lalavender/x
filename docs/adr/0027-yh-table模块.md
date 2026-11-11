# ADR-0027：`table` 模块——集中编译期语义存储（V 风格 ast.Table 对等层）

日期：2026-11-11。状态：**已实施（worktree 验证中）**。

关联：[ADR-0021](0021-yh-gen职责拆分.md)、[ADR-0024](0024-yh-support再收缩.md)、
[ADR-0026](0026-yh-clock删除.md)；方案 [yh-table模块实施方案](../02-plan/yh-table模块实施方案-2026-11-11.md)。

## 背景

`ModelStore`（类型/签名/具名类型/符号/作用域表）+ 表操作 + 值规则散在 `support`，
被 check/parse/ast/comptime/build/builtin 共用（`ms()` 约 1000 处）。用户要求参考
V 语言 `ast.Table` 集中语义存储、消掉分散的 `model_store`。

**不能放 ast**：yh 的 `ast → comptime`（CT 零拷贝镜像，`sizeof(AstExpr)==sizeof(comptime.CtExpr)`
+ `ct_ir_import`），且 support 自身读 `ms()`。放 ast 会同时造成
`comptime→ast→comptime` 与 `support→ast→support` 双环。V 的 ast 在底层、
yh 的 ast 在 comptime 之上，层序相反。

## 决定

新增底层 `compiler/table/`（`module table`），集中语义存储与值规则：

```
types  errors  token  support（基础设施）
   ↑
 table（ModelStore/CSym + 表操作 + 值规则 + 字符串标签/枚举成员表 + SYM_/F_/VK_）
   ↑
 comptime  ast  builtin  check  parse  build（向下依赖 table）
```

- `table → types, support, errors`（token 按需）。**support 不 import table**（无环关键）。
- 搬入：`ModelStore`/`CSym` 结构、`g_model`/`ms()`/`mstore_reset`/`AGGTYPE_LIMIT`、
  32 个读 `ms()` 的表操作（scope/ty_push/model_type_push/sym_lookup/ty_*/sig_add/fn_abi/cabi_*）、
  值规则（value_kernel：vk_fold_*/vk_can_assign/sem_fold_*/fp64_norm_bits/vk_msg）、
  字符串标签表 `data_str_*` 与枚举成员表 `em_*`（含 `tables_reset`）、`SYM_*/F_*/VK_*` 常量、
  私有辅助 `iv_grow`。
- support 残留：缓冲/池/源/会话/目标/`ModuleSym`/`FrontCtx`/`Res`/`static_data`/诊断，
  纯平台无关、不含语义存储。`state_init`/`session_reset` 的表清零改由
  `check.sem_init_tables` 调 `table.tables_reset()`。
- lower/backend 不依赖 table（只读 CheckedStorage 快照），不变。

## 消费方与耦合点

- check/parse/ast/comptime/build/builtin/lower 改限定名 `support.<簇> → table.<簇>`，补 `import table`。
- CT 零拷贝镜像 `comptime/ct_facts` 槽绑定改指 `table.ms()`；`ct_facts_sync` 随之。
- `check.ct_type_layout_ok` 的 `sizeof(CSym)` 改 `table.CSym`。
- `.s.i`/`.s.ct` 编码值逐一保持，用户程序产物应逐字节一致。

## 备选与被否决

| 方案 | 结论 | 理由 |
| --- | --- | --- |
| 放 ast | 否决 | ast→comptime + support 读 ms() 双环 |
| 留 support | 否决 | 用户要求集中；support 应只剩基础设施 |
| 拆片搬（先存储后操作） | 否决 | support 不能 import table，读 ms() 的簇必须原子搬 |

## 后果

- 模块数 19 → 20；新增 `table` 层位于 comptime/ast 之下。
- support 进一步收缩为纯基础设施 + 少量共享态（FrontCtx/Res/ModuleSym/static_data）。
- 搬迁在独立 worktree（tmp/wt-table）进行，避开并行会话对 support/api.yh 的修改；
  验证后合并主树。