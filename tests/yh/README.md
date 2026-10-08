# tests/yh —— yh.g4 语法覆盖语料

本目录按语法文件 `docs/yh.g4` 的规则逐条生成 `.yh` 文件，用于语法覆盖检查。
语料只做**词法 + 语法**层面的验证，不参与类型检查与代码生成，因此文件里可以出现
未定义符号、无 `main`、类型不正确等情形。

2026-10-05 当前 ANTLR 与编译器语法模式各校验正例 71/71、反例 44/44；新增
编译期显式调用、函数体 `$if/$for` 及 `comptime` 普通标识符边界。自动 C ABI 的
语义与运行结果由 `tests/yh-run/` 和 `tests/modules/projects/autoabi/` 验证。

> 当前编译器源码位于 `compiler/`，由 `bin/yh` 滚动自举构建。
> `make test` 同时以 `yh.g4` 的 ANTLR 解析器和编译器语法模式校验语料；
> 两条路径都须接受正例、拒绝反例。

## 目录与命名

按 `yh.g4` 的 11 个章节直接分区，另加一个反例区：

| # | yh.g4 章节 | 目录 | 文件数 |
| --- | --- | --- | --- |
| 1 | 顶层结构 | `01-toplevel/` | 4 |
| 2 | 基础规则 | `02-basic/` | 3 |
| 3 | 声明 | `03-decl/` | 9 |
| 4 | 语句 | `04-stmt/` | 9 |
| 5 | 分支语句 | `05-branch/` | 6 |
| 6 | 循环语句 | `06-loop/` | 4 |
| 7 | 赋值操作符 | `07-assign/` | 1 |
| 8 | 表达式 | `08-expr/` | 15 |
| 9 | 类型系统 | `09-types/` | 5 |
| 10 | 内置 prelude | `10-prelude/` | 2 |
| 11 | 词法规则 | `11-lex/` | 8 |
| 12 | 扩展语法 | `12-exp/` | 1 |
| — | 扩展正例（C 函数类型、编译期语法与标识符） | `positive/` | 4 |
| — | **反例** | `rejected/` | 44 |

合计 **115 个 `.yh` 文件**（正例 71 + 反例 44）。分区文件使用 `NN_<topic>.yh`，
独立新增正例和反例也使用序号加短横线的命名。

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
| 标签 | **不写** | `L:` 包裹被标记的语句（`IDENT ':' stmt`），**不能悬空到块尾** |
| 空语句 | **不存在** | `;` 只作一次语句终结符，不能单独构成语句 |

**括号**：`if` 条件必须带括号（`if (c) { }`）；`for` / `switch` 不带。

**赋值**：`exprStmt` 是单目标赋值 `expr (assignOp expr)? ';'`——
v0.1 无元组赋值（`a, b = 1, 2;` 非法，见 `rejected/24`），逗号仅用于调用实参。

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

语法共 77 条规则（parser 68 + lexer 9），包括由
`comptimeIfStmt`、`comptimeForStmt` 与 `comptimeCall` 覆盖的编译期扩展。

### 顶层结构

| 规则 | 文件 |
| --- | --- |
| `sourceFile` | 01-toplevel/01_toplevel_decls.yh、01-toplevel/03_empty_file.yh |
| `topLevelDecl` | 01-toplevel/01_toplevel_decls.yh、01-toplevel/02_pub_export.yh |
| `topLevelDeclBody` | 01-toplevel/01_toplevel_decls.yh、01-toplevel/02_pub_export.yh |
| `plainDeclBody` | 01-toplevel/01_toplevel_decls.yh |
| `exportedDeclBody` | 01-toplevel/02_pub_export.yh |

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
| `fieldDecl` | 03-decl/07_struct_union.yh、08-expr/14_member_names.yh |
| `enumDecl` | 03-decl/08_enum.yh |
| `enumItem` | 03-decl/08_enum.yh |

### 语句

| 规则 | 文件 |
| --- | --- |
| `block` | 04-stmt/01_block.yh |
| `stmt` | 03-decl/09_local_decl.yh、04-stmt/02_stmt_dispatch.yh、positive/70-comptime-control.yh |
| `comptimeIfStmt` | positive/70-comptime-control.yh |
| `comptimeForStmt` | positive/70-comptime-control.yh |
| `labelStmt` | 04-stmt/03_label_goto.yh、04-stmt/08_label_no_semi.yh、04-stmt/09_label_wraps_stmt.yh |
| `gotoStmt` | 04-stmt/03_label_goto.yh |
| `branchStmt` | 04-stmt/04_branch_return.yh |
| `returnStmt` | 04-stmt/04_branch_return.yh、04-stmt/06_return_forms.yh |
| `exprStmt` | 04-stmt/05_expr_stmt.yh、08-expr/13_stmt_forms.yh、10-prelude/02_prelude_usage.yh |

### 分支语句

| 规则 | 文件 |
| --- | --- |
| `ifStmt` | 05-branch/01_if.yh、05-branch/02_else_if.yh、05-branch/04_structinit_disambig.yh、05-branch/05_if_paren.yh |
| `switchStmt` | 05-branch/03_switch.yh、05-branch/06_switch_structinit.yh |
| `switchCase` | 05-branch/03_switch.yh、05-branch/06_switch_structinit.yh |

### 循环语句

| 规则 | 文件 |
| --- | --- |
| `forStmt` | 06-loop/01_for_infinite_cond.yh、06-loop/02_for_in.yh、06-loop/04_for_structinit_cond.yh |
| `forInParts` | 06-loop/02_for_in.yh、06-loop/03_for_range.yh |

### 赋值操作符

| 规则 | 文件 |
| --- | --- |
| `assignOp` | 07-assign/01_assign_ops.yh |

### 表达式

| 规则 | 文件 |
| --- | --- |
| `exprList` | 08-expr/01_expr_list.yh、11-lex/06_continuation.yh |
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
| `additiveExpr` | 08-expr/02_precedence_chain.yh、08-expr/05_compare_shift_arith.yh、11-lex/06_continuation.yh |
| `multiplicativeExpr` | 08-expr/02_precedence_chain.yh、08-expr/05_compare_shift_arith.yh |
| `unaryExpr` | 08-expr/02_precedence_chain.yh、08-expr/07_unary.yh |
| `postfixExpr` | 08-expr/08_postfix.yh、08-expr/15_to_type_postfix.yh |
| `postfixPart` | 08-expr/01_expr_list.yh、08-expr/06_cast.yh、08-expr/08_postfix.yh、08-expr/14_member_names.yh、08-expr/15_to_type_postfix.yh、10-prelude/02_prelude_usage.yh |
| `callArgs` | 08-expr/01_expr_list.yh、10-prelude/02_prelude_usage.yh |
| `primaryExpr` | 08-expr/09_primary_literal.yh、positive/69-comptime-call.yh |
| `comptimeCall` | positive/69-comptime-call.yh |
| `literal` | 08-expr/09_primary_literal.yh |
| `sizeofExpr` | 08-expr/10_sizeof_len.yh |
| `lenExpr` | 03-decl/05_fn_variadic.yh、08-expr/10_sizeof_len.yh |
| `structInit` | 05-branch/06_switch_structinit.yh、06-loop/04_for_structinit_cond.yh、08-expr/11_struct_init.yh、08-expr/12_struct_init_in_init.yh、08-expr/13_stmt_forms.yh |
| `structInitBody` | 05-branch/04_structinit_disambig.yh、05-branch/06_switch_structinit.yh、06-loop/04_for_structinit_cond.yh、08-expr/11_struct_init.yh |
| `structInitField` | 08-expr/11_struct_init.yh、08-expr/14_member_names.yh |
| `memberName` | 08-expr/14_member_names.yh |

### 类型系统

| 规则 | 文件 |
| --- | --- |
| `typeRef` | 09-types/01_ptr_array_slice.yh、09-types/02_fn_type.yh、09-types/04_named_and_len_expr.yh、09-types/05_array_of_ptr.yh |
| `fnType` | 09-types/02_fn_type.yh |
| `typeRefList` | 09-types/02_fn_type.yh |
| `builtinType` | 09-types/03_builtin.yh |

### 内置 prelude

该章节在 `yh.g4` 中只有说明注释、没有产生式。语料用两个文件覆盖其**声明形态**与**调用形态**：

| 规则 | 文件 |
| --- | --- |
| `fnDecl`、`paramList`、`param`、`ELLIPSIS`（裸 `...` 分支） | 10-prelude/01_prelude_decls.yh |
| `exprStmt`、`postfixPart`、`callArgs` | 10-prelude/02_prelude_usage.yh |

### 词法规则

| 规则 | 文件 |
| --- | --- |
| `COMMENT` | 11-lex/04_comments.yh |
| `STRING` | 11-lex/02_strings_chars.yh、11-lex/07_escapes_hex.yh |
| `CHAR` | 11-lex/02_strings_chars.yh、11-lex/07_escapes_hex.yh |
| `NUMBER` | 11-lex/01_numbers.yh |
| `IDENT` | 11-lex/03_identifiers.yh |
| `NL` | 11-lex/05_ws_nl.yh |
| `WS` | 11-lex/05_ws_nl.yh、11-lex/08_ws_specials.yh |
| `RANGE`（`..`） | 06-loop/03_for_range.yh |
| `ELLIPSIS`（`...`） | 03-decl/05_fn_variadic.yh、10-prelude/01_prelude_decls.yh |

## 语法歧义结论（探针实测）

分析工具：`tmp/probe_ambiguity.py`——用 ANTLR 4.13.2 以 `LL_EXACT_AMBIG_DETECTION`
模式解析探针片段，报告真歧义、全上下文预测与预期外结果；69 个用例覆盖
for/switch 头部边界、memberName、exprStmt、labelStmt、数组类型边界、structInit
细目、词法边界（转义/下划线/`..`）等可疑点。

**结论：修订版语法 0 处真歧义、0 处全上下文预测**——每个决策点都能用有限前瞻解决。
同一批探针在修订前的旧语法上也跑过一次（当时 0 歧义），并发现了旧语法的
1 个实锤问题（悬空标签 `end: }` 被静默接受），该问题已由修订版 `labelStmt: IDENT ':' stmt` 修复。

### 手写 parser 需要处理的决策点（语法无歧义，但需要前瞻策略）

1. **for 头部三形态共用前缀**：`for IDENT …` 时先看 `in`（遍历）、`, IDENT in`（带下标遍历），
   否则按条件表达式处理；`for {` 是无限循环。
2. **for/switch 头部 `IDENT {` 的字面量 vs 块**：贪心取字面量——对 `{` 做花括号配对，
   组内能解析为 `structInitBody` 且配对 `}` 之后紧跟 `{`，则取字面量分支，否则视为块/case 体
   （与 ANTLR ALL(*) 判定一致，零回溯；详见 `yh.g4` structInit 注释）。
   因此 `for S{1} { }` 是「字面量条件 + 空块」，可读性优先时写 `for (S{1}) { }`。
3. **structInitBody 命名式 vs 位置式**：首元素第二个 token 是 `:` 即命名式。
4. **数组长度与元素类型的 `*` 边界**：`[4]*u8` 的长度表达式先闭合，`*` 归元素类型
   （`09-types/05`）。长度是变量时（`[n]*char`）贪心乘法解析会出错，需按「`]` 闭合」处理。
5. **case 值与块**：case/default 是保留字，字面量体内不可能出现它们，token 级可分。
6. **类型转换属于后缀链**：`x.to_type(T).y`、`x.to_type([]T)[i]` 可直接续接；转换 `-x` 须写 `(-x).to_type(T)`。

### 语法放行、语义层需拦截的宽松点

钉在 `08-expr/13_stmt_forms.yh`（防止被误当语法错误，同时提醒语义阶段）：
裸结构体字面量语句 `Point{1,2};`、给比较结果赋值 `a == b = c;`、给调用结果赋值 `f() = 1;`。
另有 `sizeof(int)(3)`（对 sizeof 结果做后缀调用）语法合法。无 `++`/`--` token，
`a+++b` 解析为 `a + (+(+b))`。

## 已知缺口

### 1. 两条「名义规则」没有正例可达

| 规则 | 说明 |
| --- | --- |
| `commentStmt` | `COMMENT` 走隐藏通道后，注释对 parser 不可见，`commentStmt` 无产生式可达。语料在注释头引用它，正文演示「语句位置写注释」。 |
| `removedKeyword` | 该规则**故意没有产生式**，作用是让已移除的 C 关键字（`while`、`do`、`unsigned`、`signed`、`short`、`long`、`float`、`double`、`typedef`、`extern`、`static`、`register`、`auto`、`inline`、`volatile`、`restrict`）优先于 `IDENT` 匹配，从而在误用时产生**明确的语法错误**而不是被静默解析。语料只能在注释头引用它，正文演示替代写法。 |

这两条规则的「拒绝行为」由 `rejected/05_removed_keyword.yh` 验证。

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
| `08_reserved_ident.yh` | `let len int = 1;` | 拒绝：隐式保留字不作标识符（成员位置除外） |
| `09_type_name_as_ident.yh` | `let int int = 1;` | 拒绝：内建类型名是保留字 |
| `10_empty_struct_init.yh` | `Point{}` | 拒绝：字面量体强制非空 |
| `11_mixed_struct_init.yh` | `S{ x: 1, 2 }` | 拒绝：命名式与位置式不混写 |
| `12_prototype_decl.yh` | `fn f() int;` | 拒绝：fn 必须带函数体 |
| `13_multi_return.yh` | `return a, b;` | 拒绝：return 单值 |
| `14_slice_expr.yh` | `a[1:2];` | 拒绝：无切片表达式 |
| `15_increment_op.yh` | `a++;` | 拒绝：无 ++/-- |
| `16_arrow_operator.yh` | `p->x` | 拒绝：无箭头，指针用 `.` |
| `17_empty_stmt.yh` | `;` | 拒绝：空语句不存在 |
| `18_malformed_number.yh` | `0b12` | 拒绝：非法数字词法切分后报错 |
| `19_local_pub.yh` | 函数内 `pub let` | 拒绝：pub 仅顶层 |
| `20_shared_type_binding.yh` | `let a, b int = 1, 2;` | 拒绝：类型不共享 |
| `21_local_fn.yh` | 函数内 `fn` | 拒绝：不支持局部函数 |
| `22_leading_dot_float.yh` | `.5` | 拒绝：NUMBER 须以数字开头 |
| `23_preprocessor.yh` | `#include "stdio.h"` | 拒绝：无预处理 |
| `24_multi_assign.yh` | `a, b = 1, 2;` | 拒绝：exprStmt 单目标赋值 |
| `25_dangling_label.yh` | `end: }` | 拒绝：标签必须后随语句 |
| `26_unknown_escape.yh` | `"a\qb"` | 拒绝：未知转义词法报错 |
| `27_number_underscore.yh` | `1__0` | 拒绝：下划线必须夹在数字之间 |
| `28_legacy_as.yh` | `x as T` | 拒绝：旧类型转换写法已移除 |
| `29_reserved_to_type.yh` | `let to_type int = 1;` | 拒绝：专用后缀关键字不作普通标识符 |

### 3. 参考语法的 `NL` 仍走隐藏通道

`NL` 不参与语法判定，只用于保留位置信息。**语句边界完全由 `;` 决定**，
因此语料里「换行」纯粹是排版，不影响解析结果。
唯一例外是 `return`：`return` 换行 `x;` 即 `return x;`（吞掉下一行开头的表达式，
NL 隐藏通道所致，同 C），见 `yh.g4` returnStmt 注释。


## 与实现的关系

玉衡的 parser 落地后：

1. 把 `check.py` 的校验动作从「ANTLR 生成 + 解析」换成编译器自带的语法检查子命令；
2. 本语料转为该编译器的语法回归集；
3. `src/` 手写 lexer/parser 与修订版语法的逐项同步清单见 `docs/todo.md`；
4. 若届时需要区分「语法已定义但实现未落地」，再引入 `pending/` 一类的二级分区。
