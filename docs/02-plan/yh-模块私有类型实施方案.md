# yh 模块私有类型实施方案

日期：2026-10-12。状态：**已实施**（P0–P5 全部完成，见
[完成报告](../01-finished/yh-模块私有类型-2026-10-12.md)）。
设计见[模块私有类型设计](../03-design/yh-模块私有类型设计.md)，
决策见 [ADR-0013](../adr/0013-yh模块私有类型.md)。按 `AGENTS.md`
「修改语法规则」五步执行：yh.g4 无歧义分析 → 计划 → 语料 → 实现全绿 → 刷新文档。

## 1. 目标与成功标准

目标：`struct` / `union` / `enum` 的 `pub` 变为**可选**；不带 `pub` 的是
**模块私有类型**（只在本模块可见、不进接口文件 `.s.i`）。

| # | 成功标准（可验证） | 验证方式 |
| --- | --- | --- |
| 1 | 裸 `struct`/`union`/`enum` 在单文件与项目模式都被接受；同模块可构造、访问字段、`sizeof`、引用 enum 成员 | `tests/yh` 正例 + `tests/yh-run/run` 用例 |
| 2 | 私有类型不进 `.s.i`；其他模块命名它被拒绝 | `tests/modules/projects/modprivtype/host2` + `build-check.py` |
| 3 | 私有类型出现在 `pub fn` 签名 / `pub struct` 字段 / `pub type` 别名体 → 拒绝 | `tests/yh-run/fail` 用例（`fail-contains: pub 接口引用了非 pub 类型`） |
| 4 | ANTLR 参考语法与编译器 `--syntax-check` 对同一批语料口径一致 | `make test` 第 1、2 层 |
| 5 | 自举全绿并滚种子 | `make`、`make test`、`make selfhost-native`、`make seed` + 复跑 |

## 2. 已核实事实（实现面）

| 位置 | 现状 | 本次动作 |
| --- | --- | --- |
| `parse/parse_decl.yh:460-466`、`468-474` | 两处「必须带 pub」门禁（全仓仅此两处） | 删除并改写注释 |
| `docs/yh.g4:58-61`、`73-78`、`36-40`、`72` | `attributedDecl` 要求 struct/union/enum 带 pub；`plainDeclBody` 不含它们 | 按设计 §4 的 diff 修改 + 更新注释 |
| `gen/symbols.yh:456` | `t_names[...].is_pub = c_decl_pub` | 不改（已按 pub 记录可见性） |
| `parse/iface.yh:172-208` | 接口只发射 `is_pub != 0` 的类型 | 不改（私有类型自动不进接口） |
| `parse/iface.yh:156-160` | pub 声明引用非 pub 类型 → 报错 | 不改（私有类型泄漏的守门） |
| `parse/parse_decl.yh:1101-1105` | enum 成员 `F_PUB` 已按 `c_decl_pub` 条件化 | 不改（私有 enum 成员自动不导出） |
| `parse/iface_ct.yh:151` | 跨模块 CT 正文引用私有具名类型 → 报错 | 不改 |
| `parse/parse_decl.yh:500-514` | 属性对 struct/union/enum 已放行（除 inline/noreturn） | 不改；`@[extern] struct` 私有形式随之合法，补语料 |

已完成的可行性 spike（tmp 副本，未入库）：去掉两处门禁后编译器可自举（`yh-relaxed`）；
`ast.AstExpr`、`ast.AstFunctionContext`、`comptime.CtDataSlice` 三个类型私有化后构建成功，
接口总量 39,990 → 38,871 字节；`cmd.TomlVal`、`comptime.CtExpr` 因出现在 pub 声明里被
既有诊断拒绝——证明守门有效、且私有化必须"整簇"处理。

## 3. 阶段与任务

### P0 语法与决策（本次交付）

- [x] 设计文档（规则 / 可见性矩阵 / 边界诊断 / yh.g4 无歧义论证）
- [x] ADR-0013（修订 2026-10-02「类型必须 pub」，其余两条保留）
- [x] 本实施方案
- [x] 评审确认（用户；私有类型不得以指针形式进入 pub API）

### P1 语言规则实现

1. `docs/yh.g4`：`attributedDecl` 第二分支改为 `'pub'? (structDecl | unionDecl | enumDecl)`；
   `plainDeclBody` 增 `structDecl | unionDecl | enumDecl`；更新 36-40 行与 72 行注释。
2. `compiler/parse/parse_decl.yh`：删除两处门禁，注释改为「pub 可选：缺省为模块私有类型」。
3. 不改动接口/符号/enum 成员逻辑（见 §2）。

验证：`make`（此时编译器源码仍全为 `pub` 类型，现役种子可编）；手测
`./yh --syntax-check` 接受裸 `struct`。

### P2 语料（必须与 P1 同批，否则 `make test` 第 1/2 层直接红）

正例（语法层，ANTLR 与编译器都必须接受）：

- 新增 `tests/yh/03-decl/07_private_types.yh`：私有 struct/union/enum 声明 + 模块内构造、
  字段读写、`sizeof`、enum 成员引用。
- 新增 `tests/yh/03-decl/08_private_extern_type.yh`：`@[extern] struct`（私有 C 布局）+
  同模块 `@[extern] fn` 使用它。
- 删除 `tests/yh/rejected/30_bare_struct.yh`、`31_bare_union.yh`、`34_bare_enum.yh`
  （其内容并入上述正例；`rejected/32_nested_type_decl.yh` 等保持不动）。

语义负例（`tests/yh-run/fail/`，首行 `// fail:`，必要时 `// fail-contains:`）：

- 私有类型作 `pub fn` 参数 / 返回值。
- 私有类型作 `pub struct` 字段。
- `pub type` 别名体引用私有类型。
- 私有类型以指针形式出现在 `pub fn` 签名（证明"连指针也不行"）。

模块语料：

- 新增 `tests/modules/accept/08-private-type.yh`：`module` + 私有类型 + 同模块 fn 使用（退出码 0）。
- 新增 `tests/modules/projects/modprivtype/`：
  - `lib/`：私有 `struct Secret`、私有 `enum`，对外只提供 `pub fn` + `*void` 句柄；
  - `host/`：正常使用句柄 API（`run`，退出码非 0 以便校验）；
  - `host2/`：写 `lib.Secret` → `fail`，诊断「模块没有导出该类型」。
- `tests/modules/build-check.py` 增两条：`u3-private-type-in-module`（run）、
  `u3-private-type-not-exported`（fail）。

验证：`make test`（ANTLR 正/反例、编译器语法模式、`yh-run` 全量）。

### P3 落地与滚种子

`make selfhost-native` 全绿后滚种子（x86_64 宿主显式 `SEED_DEST`），并用新种子复跑主门。

### P4 编译器自身类型私有化（分批）

静态估算可干净私有化 **12/66** 个类型：

| 模块 | 类型 |
| --- | --- |
| ast | `AstExpr`、`AstFunctionContext`、`AstIRBuilder`、`AstIRInlineEntry`、`AstStmt` |
| main（cmd） | `CmdTimespec`、`PJDirEntry`、`TomlArrayItem`、`TomlSec` |
| comptime | `CtDataSlice`、`CtGlobalAgg` |
| parse | `IfaceCtColMap` |

实际执行：12 个类型一次落地（13 处声明），`make` 一次通过、无诊断返工；
`make test` 293/293、`make selfhost-native`（固定点 24 产物、自解析 71 文件、
modules 18/18、项目验收 93/93）全绿。收益：接口 39,990 → **36,633** 字节
（−8.4%），比预估更高；编译器二进制不变，故该代种子内容未变。

### P5 文档刷新

[00-语义边界-0.0.1](../03-design/00-语义边界-0.0.1.md) 的 pub 一节、
[架构设计 §3.3](../03-design/yh-架构设计.md)（回到"非 pub 类型 = 模块私有"
的原设计）、`docs/yh.g4` 注释、[compiler/README.md](../../compiler/README.md)、
`AGENTS.md`（导出面规则补类型可见性一句）、`docs/todo.md`、`docs/finish.md` 与
`docs/01-finished/` 完成报告。

## 4. 顺序约束（硬约束，勿合并）

**两段自举**：门禁在**编译器二进制**里。若把 P1 与 P4 合成一步，现役种子（含门禁）
会拒绝"编译器源码里的裸 struct"，构建直接失败。正确顺序：

```
P1+P2（yh.g4 + 门禁 + 语料，用现役种子编）→ P3 滚种子
    → P4 编译器自身类型私有化（用 P3 的新种子编）
```

**跨平台**：macOS 种子 `bin/yh` 目前落后一代。P4 之前它仍能编（源码类型全 `pub`）；
P4 之后每个平台都必须先滚出自己的种子，或先只保留语言规则、暂不私有化编译器自身类型。

## 5. 风险与回滚

| 风险 | 处置 |
| --- | --- |
| ANTLR 与编译器解析器口径不一致 | 第 1、2 层跑同一批语料，立刻暴露 |
| 私有类型被 pub 声明引用而静默泄漏 | 既有诊断直接报错（实测 `cmd.TomlVal`、`comptime.CtExpr` 触发） |
| 跨模块 CT 正文引用私有类型 | 既有诊断拒绝 |
| 语料转正后漏删负例 | `make test` 立即红 |
| 回滚 | 语言规则改动只有 yh.g4 两处 + 2 个 `if` 块，`git revert` 即可；种子可回退到 `a4c66d5b…` |

## 6. 交付物与工作量

- 代码：`docs/yh.g4`（2 处）、`compiler/parse/parse_decl.yh`（2 个 `if` 块）。
- 语料：§3 P2 清单（正例 2、负例 4、模块语料 3 处 + 2 条 build-check 用例）。
- 文档：设计、ADR-0013、本方案 + P5 列表。
- 种子：滚一代。

粗估：P1 ≈ 0.5 天（含构建验证）、P2 ≈ 0.5 天、P3 ≈ 0.5 天、P4 每批 ≈ 0.5 天（2–3 批）、
P5 ≈ 0.5 天，合计 ≈ 3 天；可分两次交付：P1–P3 落语言规则，P4–P5 收口编译器自身。
