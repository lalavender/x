# 分号清理实施方案（llvm 分支）

日期：2026-10-21。目标：源码风格统一为「行尾不写分号，同行分隔保留」，
删掉编译器源码中 95.8% 的冗余分号，语言语义与生成物不变。

## 统计基线

基于当前 `llvm`（a60b2fa + 工作区改动），`compiler/` 100 个 `.yh`，
按 token 判定（剔除注释与字面量）：

| 位置 | 数量 | 处理 |
|---|---:|---|
| 换行处（行尾） | 14,357 | 删除 |
| 右花括号前 | 10,105 | 删除 |
| 文件尾 | 4 | 删除 |
| 同一行两条语句之间 | 1,061 | 保留 |
| 合计 | 25,527 | 可删 24,466（95.8%） |

- 保留的 1,061：796 处一行多条赋值/调用，265 处紧凑控制流。
- 其中 3,814 个同行分号紧跟 `}`（如 `if (c) { a(); }`），属于「右花括号前」，
  可删；同一行中间的分隔符保留。
- 其它目录：`libs/` 43 个文件、`examples/` 3 个；`tests/` 739 个不批量清理
  （显式分号的覆盖要留着）。

## 实现改动面

| 文件 | 改动 |
|---|---|
| `compiler/lex/layout.yh`（新增） | 扫描后归一化：按行号、`}`、EOF 插入 `len == 0` 的 `TK_SEMI`；括号/方括号内、属性组后、`{` 前不终结 |
| `compiler/lex/lexer.yh:534` | `lex_all()` 末尾改 `return lex_layout()`；8 个入口都经 `lex_all`，无第二条路径 |
| `compiler/gen/model.yh:156` | `Tok.len` 注释补「隐式终结符为 0」 |
| `compiler/parse/parse_type.yh:40` | `p_expect` 放行字面量尾部；新增 `p_implicit_semi()` / `p_take_block_end()` |
| `compiler/parse/parse_stmt.yh:63`（`parse_block`）、`:572`（`parse_switch`） | 块闭合后消费隐式终结符 |
| `compiler/parse/parse_decl.yh:474`（`parse_top_decl`） | 顶层声明结束后消费隐式终结符 |
| `compiler/parse/parse_comptime.yh:7` | 编译期块范围跨过隐式终结符 |
| `compiler/parse/iface_ct.yh` | 正文重写保留换行位置：调用内部换行放 `$` 后，局部类型换行放 `=` 后 |
| `docs/yh.g4` | `NL` 由隐藏通道改为参与边界；语句/成员规则改「`;` 可选」并写明消歧规则 |

2a9e 工作区里的 `layout.yh` 与解析钩子可作蓝本，但状态字段已迁到
`gs.task.*`（RS1c），需按当前结构改写，不能直接照搬。

## 迁移成本

括号外的行首运算符共 **240 处 / 46 个文件**，严格续行下会被当成新语句，
必须移到上一行末尾。集中区：`ast/module_snapshot_lower.yh` 26、
`ir/ssa_module_30_serialize.yh` 20、`backend/llvm_call.yh` 19、
`cmd/link_cache.yh` 15、`comptime/ct_ir_place.yh` 14。

## 目标风格

- 一条简单语句占一行，行尾不写 `;`。
- 同一行写两条及以上简单语句时用 `;` 分隔；不为消分号强行拆行。
- 字段/枚举成员每行一个不写 `;`；同行多成员才写。
- 以 `}` 收尾的语句与声明之后不写分号。
- 括号外跨行表达式，运算符放上一行末尾；`()`/`[]` 内自由换行。
- 裸 `return` 在行尾结束；跨行返回值写成 `return (` 或放括号内。

## 必须保留分号的场景

1. 同一行两条语句：`if (data == 0) { close(fd); return 0 }`。
2. 同一行多个字段或枚举成员：`struct Pair { left int; right int }`。
3. 生成物：接口 `.s.i` 与编译期正文 `.s.ct` 继续写显式 `;`。
4. 反例与兼容用例：`tests/yh/02-basic/01_semicolon.yh`、
   `tests/yh/rejected/` 中验证「缺分号」「块后多余分号」的项。
5. 普通语句后紧跟裸块 `{ ... }`：`{` 前不自动终结，需保留分号
   （当前 `compiler/` 无此写法）。

## 阶段

### Phase 0 实现与迁移

按上表落代码；先加用例（新写法在旧编译器上报错，红灯成立），再实现；
同时把 240 处行首运算符移到上一行末尾。`make` 后跑
`python3 tests/yh/check.py` 与 `tests/yh-run`。

### Phase 1 全门 + 滚种子 + 发版（硬顺序）

`make`、`make test`、`make selfhost-native` 全绿后 `make seed` 并发布 Release。
**必须先发版再清理**：`bin/` 不入库，新克隆 `make fetch-seed` 与 CircleCI
取的是最新 Release 种子；旧种子不认识无分号源码。

### Phase 2 批量删除

只删「换行处、`}` 前、EOF 前」且上一 token 能结束语句的 `;`（24,466 个），
逐文件要求：删除前后归一化 token 流一致、`--syntax-check` 通过。
按目录分批：`compiler/gen`、`compiler/ast` … 每批单独提交便于回滚。

### Phase 3 验证

- 产物对比：清理前后用同一条编译器冷编，`diff -r compiler/.build` 的
  `.s`/`.s.i` 应逐字节相同；差异若只来自调试位置信息，以 token 等价 + 全门为准。
- 全门：`make test`、`make selfhost-native`（两代固定点 + 自解析 + 语料 +
  模块/项目验收）。

### Phase 4 文档刷新

`docs/yh.g4` 注释与示例、`compiler/README.md`、涉及代码块的现行设计文档；
`docs/finish.md` 与 `docs/01-finished/` 记录结果，收尾后可再滚一次种子。

## 风险

- **顺序**：清理与发版颠倒会让本地与 CI 冷编失败；回滚只需恢复提交。
- **token 下标变化**：AST 快照范围、IR 缓存夹具、模块未改动断言都按 token
  计，插入隐式终结符后需重跑 `tests/modules/build-check.py` 与自举固定点。
- **隐式/显式区分**：块收尾只消费 `len == 0` 的终结符，显式分号仍按旧规则
  拒绝（空语句、块后多余分号保持报错）。
- **生成物**：`.s.i`/`.s.ct` 若改成无分号，会牵动缓存失效与接口重放，明确排除。
