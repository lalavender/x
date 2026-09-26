# tests/yh —— yh.g4 语法覆盖语料

本目录按语法文件 `yh.g4` 的规则逐条生成 `.yh` 文件，用于语法覆盖检查。
语料只做**词法 + 语法**层面的验证，不参与类型检查与代码生成，因此文件里可以出现
未定义符号、无 `main`、类型不正确等情形。

> 玉衡编译器本体（`src/`）目前仍是改造中的 TCC，**尚无 `.yh` 解析实现**。
> 因此本语料当前的校验基准是 `yh.g4` 本身（见「如何校验」），
> 而不是某个编译器二进制。等玉衡的 parser 落地后，改为走编译器自带的语法检查入口即可。

## 目录与命名

按 `yh.g4` 的 11 个章节直接分区，另加一个反例区：

| # | yh.g4 章节 | 目录 | 文件数 |
| --- | --- | --- | --- |
| 1 | 顶层结构 | `01-toplevel/` | 3 |
| 2 | 基础规则 | `02-basic/` | 3 |
| 3 | 声明 | `03-decl/` | 9 |
| 4 | 语句 | `04-stmt/` | 8 |
| 5 | 分支语句 | `05-branch/` | 5 |
| 6 | 循环语句 | `06-loop/` | 3 |
| 7 | 赋值操作符 | `07-assign/` | 1 |
| 8 | 表达式 | `08-expr/` | 12 |
| 9 | 类型系统 | `09-types/` | 4 |
| 10 | 内置 prelude | `10-prelude/` | 2 |
| 11 | 词法规则 | `11-lex/` | 6 |
| — | **反例** | `rejected/` | 7 |

合计 **63 个 `.yh` 文件**（正例 56 + 反例 7）。文件命名格式为 `NN_<topic>.yh`（两位数字 + 下划线 + snake_case）。

**反例区 `rejected/`**：该目录下的文件**必须解析失败**才算通过，用来钉住「哪些写法不许出现」。
首行注释头格式不同，写的是期望与原因：

```yh
// 期望：语法错误。`if` 条件必须带括号，`if flag { }` 缺 `(` `)`。
```

## 语句终结规则（`;` 必写）

玉衡**简单语句必须以 `;` 结尾**。这条设计把「语句边界」从不可见的换行变成可见的 token，
从而消除了「一条语句 vs 两条相邻语句」的全部歧义。

| 情形 | 是否写 `;` | 例子 |
| --- | --- | --- |
| 简单语句 | **必须写** | `let a int = 1;`、`return x;`、`a = 1;`、`f();`、`goto L;`、`break;` |
| struct / union 字段、enum 成员 | **必须写** | `x int;`、`red;` |
| 以块结尾的语句 | **不写** | `if (c) { … }`、`for { … }`、`switch x { … }`、裸块、`fn` / `struct` / `union` / `enum` 声明 |
| 标签 | **不写** | `L:` 后面紧跟被标记的语句 |
| 空语句 | **不存在** | `;` 只作一次语句终结符，不能单独构成语句 |

**括号**：`if` 条件必须带括号（`if (c) { }`）；`for` / `switch` 不带。

**跨行**：行尾是运算符、`,`、`(` 时表达式续行，`;` 才是语句终点：

```yh
let x int = 1 +
    2;              // 一条语句
let r int = f(
    a,
    b
);                  // 一条语句
```


## 注释头格式

**正例**（11 个章节分区）的**首行必须**是单行的覆盖规则注释，便于 grep 与自动覆盖率自检：

```yh
// 覆盖规则：letDecl、binding。
```

规则名用顿号 `、` 分隔，以中文句号 `。` 收尾，**必须写在一行内**（不能折行）。
第 2~3 行可写该文件验证的语义或边界说明。

**反例**（`rejected/`）的首行格式不同，写期望与原因（同样必须单行）：

```yh
// 期望：语法错误。`if` 条件必须带括号，`if flag { }` 缺 `(` `)`。
```


## 如何校验

```sh
python3 tests/yh/check.py              # 校验全部语料
python3 tests/yh/check.py --coverage   # 额外做规则覆盖自检
python3 tests/yh/check.py --quiet      # 只打印失败项与汇总
```

判定口径分两档：

- **正例**（11 个章节分区）必须同时满足：① 零词法错误，② 零语法错误，③ 解析消费到文件末尾（EOF）。
- **反例**（`rejected/`）必须**有错**：解析报出词法或语法错误才算通过；零错误通过则判 `FAIL`。

脚本流程：把 `yh.g4` 拷进临时目录 → 用 `antlr4 -Dlanguage=Python3 -no-listener` 生成
Python parser（产物落临时目录，不污染仓库）→ 遍历 `tests/yh/**/*.yh` 按上述两档判定 →
最后用 `yhParser.ruleNames` + `yhLexer.symbolicNames` 与**正例**文件注释头求差集，报告覆盖缺口。

依赖：

- `antlr4` 命令行工具（Python 包装脚本，底层需要 Java）。本机路径
  `~/Library/Python/3.9/bin/antlr4`，脚本会自动在几个常见位置里找。
- 本地 Maven 缓存 `~/.m2/repository/org/antlr/antlr4/<版本>/antlr4-<版本>-complete.jar`。
  脚本自动挑可用的最高版本，并显式传 `-v <版本>` **跳过联网查版本**。
- Python 运行时 `antlr4-python3-runtime`，已装在
  `/Users/lavender/.workbuddy-ai/binaries/python/envs/default`。
  用别的解释器跑脚本时，它会自动用该 venv 重新执行自己。

退出码：全部通过为 `0`，有解析失败或覆盖缺口为 `1`。

## 覆盖对照表

共 68 条规则（parser 61 + lexer 7），全部有语料覆盖。

### 顶层结构

| 规则 | 文件 |
| --- | --- |
| `sourceFile` | 01-toplevel/01_toplevel_decls.yh、01-toplevel/03_empty_file.yh |
| `topLevelDecl` | 01-toplevel/01_toplevel_decls.yh、01-toplevel/02_pub_export.yh |
| `topLevelDeclBody` | 01-toplevel/01_toplevel_decls.yh、01-toplevel/02_pub_export.yh |

### 基础规则

| 规则 | 文件 |
| --- | --- |
| `commentStmt` | 02-basic/02_comment_stmt.yh ⚠️ 名义规则，见下 |
| `removedKeyword` | 02-basic/03_removed_keyword_alt.yh ⚠️ 名义规则，见下 |

> `terminator` 与 `semicolonStmt` 两条规则**已从 `yh.g4` 删除**：语句终结符改为字面量 `';'`
> 直接写在各产生式里，`;` 只作一次 EOS，不再单独构成空语句。

### 声明

| 规则 | 文件 |
| --- | --- |
| `letDecl` | 03-decl/01_let_basic.yh、03-decl/02_let_multi.yh、03-decl/09_local_decl.yh |
| `binding` | 03-decl/01_let_basic.yh、03-decl/02_let_multi.yh |
| `constDecl` | 03-decl/03_const.yh、03-decl/09_local_decl.yh |
| `fnDecl` | 03-decl/04_fn.yh、03-decl/05_fn_variadic.yh、10-prelude/01_prelude_decls.yh |
| `paramList` | 03-decl/04_fn.yh、10-prelude/01_prelude_decls.yh |
| `param` | 03-decl/04_fn.yh、03-decl/05_fn_variadic.yh、10-prelude/01_prelude_decls.yh |
| `typeDecl` | 03-decl/06_type_alias.yh |
| `structDecl` | 03-decl/07_struct_union.yh |
| `unionDecl` | 03-decl/07_struct_union.yh |
| `fieldDecl` | 03-decl/07_struct_union.yh |
| `enumDecl` | 03-decl/08_enum.yh |
| `enumItem` | 03-decl/08_enum.yh |

### 语句

| 规则 | 文件 |
| --- | --- |
| `block` | 04-stmt/01_block.yh |
| `stmt` | 03-decl/09_local_decl.yh、04-stmt/02_stmt_dispatch.yh |
| `labelStmt` | 04-stmt/03_label_goto.yh |
| `gotoStmt` | 04-stmt/03_label_goto.yh |
| `branchStmt` | 04-stmt/04_branch_return.yh |
| `returnStmt` | 04-stmt/04_branch_return.yh |
| `exprStmt` | 04-stmt/05_expr_stmt.yh、10-prelude/02_prelude_usage.yh |

### 分支语句

| 规则 | 文件 |
| --- | --- |
| `ifStmt` | 05-branch/01_if.yh、05-branch/02_else_if.yh、05-branch/04_structinit_disambig.yh |
| `switchStmt` | 05-branch/03_switch.yh |
| `switchCase` | 05-branch/03_switch.yh |

### 循环语句

| 规则 | 文件 |
| --- | --- |
| `forStmt` | 06-loop/01_for_infinite_cond.yh、06-loop/02_for_in.yh |
| `forInParts` | 06-loop/02_for_in.yh、06-loop/03_for_range.yh |

### 赋值操作符

| 规则 | 文件 |
| --- | --- |
| `assignOp` | 07-assign/01_assign_ops.yh |

### 表达式

| 规则 | 文件 |
| --- | --- |
| `exprList` | 04-stmt/05_expr_stmt.yh、08-expr/01_expr_list.yh |
| `expr` | 08-expr/02_precedence_chain.yh |
| `conditionalExpr` | 08-expr/02_precedence_chain.yh、08-expr/03_conditional.yh |
| `logicalOrExpr` | 08-expr/02_precedence_chain.yh、08-expr/04_logical_bitwise.yh |
| `logicalAndExpr` | 08-expr/02_precedence_chain.yh、08-expr/04_logical_bitwise.yh |
| `bitOrExpr` | 08-expr/02_precedence_chain.yh、08-expr/04_logical_bitwise.yh |
| `bitXorExpr` | 08-expr/02_precedence_chain.yh、08-expr/04_logical_bitwise.yh |
| `bitAndExpr` | 08-expr/02_precedence_chain.yh、08-expr/04_logical_bitwise.yh |
| `equalityExpr` | 08-expr/02_precedence_chain.yh、08-expr/05_compare_shift_arith.yh |
| `relationalExpr` | 08-expr/02_precedence_chain.yh、08-expr/05_compare_shift_arith.yh |
| `shiftExpr` | 08-expr/02_precedence_chain.yh、08-expr/05_compare_shift_arith.yh |
| `additiveExpr` | 08-expr/02_precedence_chain.yh、08-expr/05_compare_shift_arith.yh |
| `multiplicativeExpr` | 08-expr/02_precedence_chain.yh、08-expr/05_compare_shift_arith.yh |
| `castExpr` | 08-expr/02_precedence_chain.yh、08-expr/06_cast.yh |
| `unaryExpr` | 08-expr/02_precedence_chain.yh、08-expr/07_unary.yh |
| `postfixExpr` | 08-expr/08_postfix.yh |
| `postfixPart` | 08-expr/01_expr_list.yh、08-expr/08_postfix.yh、10-prelude/02_prelude_usage.yh |
| `callArgs` | 08-expr/01_expr_list.yh、10-prelude/02_prelude_usage.yh |
| `primaryExpr` | 08-expr/09_primary_literal.yh |
| `literal` | 08-expr/09_primary_literal.yh |
| `sizeofExpr` | 08-expr/10_sizeof_len.yh |
| `lenExpr` | 03-decl/05_fn_variadic.yh、08-expr/10_sizeof_len.yh |
| `structInit` | 05-branch/04_structinit_disambig.yh、08-expr/11_struct_init.yh |
| `structInitBody` | 05-branch/04_structinit_disambig.yh、08-expr/11_struct_init.yh |
| `structInitField` | 08-expr/11_struct_init.yh |

### 类型系统

| 规则 | 文件 |
| --- | --- |
| `typeRef` | 09-types/01_ptr_array_slice.yh、09-types/02_fn_type.yh、09-types/04_named_and_len_expr.yh |
| `fnType` | 09-types/02_fn_type.yh |
| `typeRefList` | 09-types/02_fn_type.yh |
| `builtinType` | 09-types/03_builtin.yh |

### 内置 prelude

该章节在 `yh.g4` 中只有说明注释、没有产生式。语料用两个文件覆盖其**声明形态**与**调用形态**：

| 规则 | 文件 |
| --- | --- |
| `fnDecl`、`paramList`、`param`（裸 `...` 分支） | 10-prelude/01_prelude_decls.yh |
| `exprStmt`、`postfixPart`、`callArgs` | 10-prelude/02_prelude_usage.yh |

### 词法规则

| 规则 | 文件 |
| --- | --- |
| `COMMENT` | 11-lex/04_comments.yh |
| `STRING` | 11-lex/02_strings_chars.yh |
| `CHAR` | 11-lex/02_strings_chars.yh |
| `NUMBER` | 11-lex/01_numbers.yh |
| `IDENT` | 11-lex/03_identifiers.yh |
| `NL` | 11-lex/05_ws_nl.yh |
| `WS` | 11-lex/05_ws_nl.yh |

## 已知缺口

### 1. 两条「名义规则」没有正例可达

| 规则 | 说明 |
| --- | --- |
| `commentStmt` | `COMMENT` 走隐藏通道后，注释对 parser 不可见，`commentStmt` 无产生式可达。语料在注释头引用它，正文演示「语句位置写注释」。 |
| `removedKeyword` | 该规则**故意没有产生式**，作用是让已移除的 C 关键字（`while`、`do`、`unsigned`、`signed`、`short`、`long`、`float`、`double`、`typedef`、`extern`、`static`、`register`、`auto`、`inline`、`volatile`、`restrict`）优先于 `IDENT` 匹配，从而在误用时产生**明确的语法错误**而不是被静默解析。语料只能在注释头引用它，正文演示替代写法。 |

这两条规则要真正验证「拒绝行为」，需要**反例语料**——见下一节。

### 2. 反例区 `rejected/` 覆盖的写法

| 文件 | 输入 | 期望 |
| --- | --- | --- |
| `01_missing_semicolon.yh` | `let x int * y` | 拒绝：`let x int` 后缺 `;` |
| `02_two_stmts_no_sep.yh` | `a = 1 b = 2` | 拒绝：同一行两语句间缺 `;` |
| `03_if_requires_parens.yh` | `if flag { }` | 拒绝：`if` 缺 `(` `)` |
| `04_struct_literal_condition.yh` | `if S{1} { }` | 拒绝：`if` 缺括号 |
| `05_removed_keyword.yh` | `while x < 3 { }` | 拒绝：`while` 是保留字 |
| `06_type_inference.yh` | `let x = 1;` | 拒绝：`let` 类型必写 |
| `07_const_type_inference.yh` | `const M = 5;` | 拒绝：`const` 类型必写 |

### 3. 玉衡刻意不支持的形态

以下写法不属于玉衡语法，**不应**出现在语料里：

- 预处理与头文件：`#define`、`#include`、`#if`、宏
- 局部函数、多返回值
- 切片表达式 `a[1:2]`、前导点浮点 `.5`
- 空结构体字面量 `Point{}`、命名与位置混写 `Point{ x: 1, 2 }`
- 自增自减 `++` / `--`、箭头 `->`（指针统一用 `.`）
- 省略类型的声明 `let a = 1` / `const M = 5`（类型必须显式写出）
- 类型不共享的多绑定 `let a, b int = 1, 2`
- 空语句 `;`（`;` 只作语句终结符，不单独构成语句）
- `if` 条件不带括号（`if flag { }` 非法，必须 `if (flag) { }`）

### 4. `for` / `switch` 的条件不带括号

只有 `if` 要求括号。`for` / `switch` 保持 `for cond { }`、`switch x { … }`。
若条件位置需要写结构体字面量，加括号即可：`for (S{1}) { }`。

### 5. 参考语法的 `NL` 仍走隐藏通道

`NL` 不参与语法判定，只用于保留位置信息。**语句边界完全由 `;` 决定**，
因此语料里「换行」纯粹是排版，不影响解析结果。


## 与实现的关系

玉衡的 parser 落地后：

1. 把 `check.py` 的校验动作从「ANTLR 生成 + 解析」换成编译器自带的语法检查子命令；
2. 本语料转为该编译器的语法回归集；
3. 若届时需要区分「语法已定义但实现未落地」，再引入 `pending/` 一类的二级分区。
