# yh 模块私有类型设计（struct/union/enum 的 pub 可选）

日期：2026-10-12。状态：**已实施**（Linux/WSL 上 `make`、`make test`、
`make selfhost-native` 全绿并滚种子，见
[完成报告](../01-finished/yh-模块私有类型-2026-10-12.md)）。
本文取代 2026-10-02「pub struct/union/enum 一等化」中"必须写 pub"的部分，
其余两条（字段一律公开、类型声明禁止嵌套）不变。

## 1. 规则

| 声明形式 | 含义 |
| --- | --- |
| `pub struct` / `pub union` / `pub enum` | 类型进接口文件（`.s.i`），其他模块可 `模块.类型` 引用；enum 成员常量随枚举导出（`F_PUB`） |
| `struct` / `union` / `enum` | **模块私有类型**：只在本模块可见，不进接口，其他模块不可命名；enum 成员常量只在模块内可见 |

- 字段仍然**一律公开**（模块内可见）：字段级 `pub` 前缀继续报错，不因类型私有而复活。
- 类型声明仍然**只能出现在顶层**（禁止嵌套），与 2026-10-02 规则一致。
- `pub` 只影响**可见性**，不影响布局、ABI 或 `sizeof`：私有类型与同名 pub 类型的布局完全相同。

## 2. 可见性矩阵（对齐 [Go 风格模块与包设计](yh-Go风格模块与包设计.md) §5.1）

| 声明 | 同模块其他文件 | 其他模块 |
| --- | --- | --- |
| `fn` / `const` / `type`（无 pub） | 可访问 | 不可访问（**现状**） |
| `struct` / `union` / `enum`（无 pub） | 可访问 | 不可访问（**本次新增**） |
| `pub fn` / `pub const` / `pub type` | 可访问 | 导入后可访问（现状） |
| `pub struct` / `pub union` / `pub enum` | 可访问 | 导入后可命名、可构造、可用字段（现状） |
| `let` | 可访问 | 不可访问，`pub let` 非法（现状） |

## 3. 边界与诊断（全部沿用既有诊断，不新增措辞）

| 情形 | 行为 | 现有诊断位置 |
| --- | --- | --- |
| 私有类型出现在本模块 `pub fn` 签名 / `pub struct` 字段 / `pub type` 别名体 | 报错 | `parse/iface.yh:158`「pub 接口引用了非 pub 类型（请将该类型声明为 pub）」 |
| 其他模块以 `模块.私有类型` 命名 | 报错 | `parse/parse_expr.yh:1854`「模块没有导出该类型」 |
| 跨模块 CT 正文引用模块私有具名类型 | 报错 | `parse/iface_ct.yh:151` |
| 私有类型的字段在本模块内读写 | 允许 | — |
| 私有类型出现在**非 pub** 的 extern / CT 函数签名 | 允许（签名不导出） | — |

推论（需要在文档中明确写出）：**私有类型不能出现在任何公开 API 中，连指针也不行**
——`pub fn open() *Secret` 会泄漏名字。模块要对外提供私有类型的操作，只有两种写法：
返回 `*void` 句柄，或把类型改成 `pub`。（"不透明导出类型"是另一项设计，本文不做。）

## 4. 语法变更与无歧义论证

`docs/yh.g4` 需要两处改动（草案）：

```diff
 attributedDecl
     : 'pub'? attributedFnDecl
-    | 'pub' (structDecl | unionDecl | enumDecl)
+    | 'pub'? (structDecl | unionDecl | enumDecl)
     ;

 plainDeclBody
     : letDecl
     | constDecl
     | fnDecl
     | typeDecl
+    | structDecl
+    | unionDecl
+    | enumDecl
     ;
```

同时更新第 36-40 行与第 72 行的注释（"必须经 pub 声明"/"裸写即语法错误"的表述作废）。

**无歧义论证**（`topLevelDecl : 'pub' exportedDeclBody | plainDeclBody | attributeGroup attributedDecl ;`）：

| 输入 | 唯一可匹配分支 | 说明 |
| --- | --- | --- |
| `pub struct …` | 分支 1 | 首 token 是 `pub`；分支 3 要求先有 `@[...]`；`plainDeclBody` 不含 `pub` |
| `struct …` | 分支 2（本次新增） | 首 token 是 `struct`，分支 1/3 都要求 `pub` 或 `@[...]` 开头 |
| `@[…] pub struct …` | 分支 3 | 首 token 是 `@`，分支 1/2 都不以 `@` 开头 |
| `@[…] struct …` | 分支 3（本次新增，`'pub'?`） | 同上 |
| `pub fn …` / `@[…] pub fn …` / `@[…] fn …` | 分支 1 / 3 / 3 | 与现状一致，未改动 |

各分支的**首 token 集合互不相交**（`pub` / `@` / 其余关键字），因此引入 `'pub'?` 与
`plainDeclBody` 扩展都不会产生新歧义；`struct/union/enum` 的关键字互不相同，`plainDeclBody`
内部也不产生歧义。ANTLR 层语料与编译器 `--syntax-check` 语料共用同一批 `.yh`，两侧口径一致。

## 5. 实现落点（已核，实现面很小）

| 位置 | 现状 | 本次动作 |
| --- | --- | --- |
| `parse/parse_decl.yh:460-466`（struct/union 门禁） | `c_decl_pub == 0` 即报错 | 删除该 `if` 块 |
| `parse/parse_decl.yh:468-474`（enum 门禁） | 同上 | 删除该 `if` 块 |
| `gen/symbols.yh:456` | `t_names[...].is_pub = c_decl_pub` | 不改（已按 pub 记可见性） |
| `parse/iface.yh:172-208` | 接口只发射 `is_pub != 0` 的类型 | 不改（私有类型自动不进 `.s.i`） |
| `parse/iface.yh:156-160` | pub 声明引用非 pub 类型 → 报错 | 不改（这就是私有类型泄漏的守门） |
| `parse/parse_decl.yh:1101-1105` | enum 成员 `F_PUB` 已按 `c_decl_pub` 条件化 | 不改（私有 enum 成员自动不导出） |
| `parse/iface_ct.yh:151` | 跨模块 CT 正文引用私有具名类型 → 报错 | 不改 |
| `cmd/module_build.yh` 接口闭包 | 只按 pub 类型建立依赖闭包 | 不改 |
| `parse/parse_decl.yh:500-514` | 属性对 struct/union/enum 已放行（除 inline/noreturn） | 不改；`@[extern] struct`（私有 + C 布局）随之合法，需语料覆盖 |

**注意（实施顺序的硬约束）**：门禁在**编译器二进制**里，不在被编译的源码里。先用旧种子编出
"门禁已删"的编译器，再让编译器源码使用裸 `struct`——否则旧种子（含门禁）编不过新源码。
实测证据：tmp 副本上造出的 `yh-relaxed` 能构建成功，而直接用现役种子编译含裸 `struct` 的源码会报门禁错误。

## 6. 影响面

- **放宽而非收紧**：裸 `struct` 以前是错误、现在合法，现有正确代码不受影响；只有依赖该错误的
  3 条负例语料（`tests/yh/rejected/30_bare_struct.yh`、`31_bare_union.yh`、`34_bare_enum.yh`）
  必须转正。
- **接口与符号**：私有类型不进 `.s.i`，也不产生跨模块类型名；模块自身 `.s` 不变（类型不发射符号）。
- **编译器自身**：静态估算 66 个类型中 **12 个**可干净私有化（ast 5、main 4、comptime 2、parse 1；
  gen/ir 为 0，消费方直接引用其类型），本次**全部落地**（13 处声明，含 `CmdTimespec`
  的 .darwin/.linux 两份）：接口总量 39,990 → **36,633** 字节（−8.4%），12 个类型在接口中
  出现次数均为 0；编译器二进制与上一代逐字节相同——类型可见性只影响接口产物，
  不改代码生成。
- **文档**：[00-语义边界-0.0.1](00-语义边界-0.0.1.md) 的 pub 一节、
  [Go 风格模块设计](yh-Go风格模块与包设计.md) §5.1（回到"非 pub 类型=模块私有"的原设计）
  与 §5.3（标注不透明导出类型暂不支持）、
  `docs/yh.g4` 注释、[compiler/README.md](../../compiler/README.md)、`AGENTS.md`、todo/finish。

## 7. 明确不做

- **不透明导出类型**（`pub struct` 但隐藏字段/布局）：需要新的接口与布局传递语义，另立设计。
- **类型嵌套**：仍然禁止（2026-10-02 规则保留）。
- **字段级 pub**：仍然报错，字段在模块内一律可见。
- **`pub let`**：仍然非法。
- 私有类型出现在 pub API 的**任何**形式（含指针、数组元素、别名）：仍然报错。
