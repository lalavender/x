grammar yh;
/*
 * 玉衡（yh）v0.1 语法参考。
 *
 * 语义、ABI 与构建规则见 docs/玉衡编译器改造方案.md。阶段 0 编译器由
 * TCC 0.9.27（AArch64/ELF）改造而来：C 手写 lexer + 单遍递归下降 parser，
 * 本文件不作为运行时依赖。
 *
 * 玉衡的设计前提：
 *   - 无预处理：没有 `#` 指令、没有宏、没有条件编译；
 *   - 无头文件：没有 `#include`，外部符号由编译器内置 prelude 声明；
 *   - 无 C 兼容：`.yh` 是唯一输入，C 语法分支已移除；
 *   - 简单语句以 `;` 结尾（块结尾的语句不写）；`if` 条件必须带括号，
 *     `for` / `switch` 不带；返回类型后置。
 *
 * 语句边界由显式的 `;` 钉死，因此本参考语法**不存在**「一条语句 vs
 * 两条相邻语句」的歧义。NL 仍放隐藏通道，只用于保留位置信息。
 */

/*
 * ============================================================================
 *  顶层结构
 * ============================================================================
 */

// 源文件：顶层声明列表 + EOF。没有模块声明、没有 import、没有 test 块。
sourceFile
    : topLevelDecl* EOF
    ;

// 顶层声明：可带 `pub` 导出标记；默认仅本文件可见。
topLevelDecl
    : 'pub'? topLevelDeclBody
    ;

topLevelDeclBody
    : letDecl
    | constDecl
    | fnDecl
    | typeDecl
    | structDecl
    | unionDecl
    | enumDecl
    ;

/*
 * ============================================================================
 *  基础规则
 * ============================================================================
 */

/*
 * 语句终结规则：
 *   - **简单语句必须以 `;` 结尾**：let / const / type / return / break /
 *     continue / goto / 表达式语句，以及 struct/union 字段与 enum 成员；
 *   - **以块结尾的语句不写 `;`**：if / for / switch / 裸块，以及 fn /
 *     struct / union / enum 声明；
 *   - **标签 `L:` 不带 `;`**，后面紧跟被标记的语句；
 *   - **空语句不存在**：`;` 只作一次语句终结符，不单独构成语句
 *     （因此没有 semicolonStmt）。
 *
 * 这条设计把「语句边界」从不可见的换行变成可见的 token，从而消除了
 * 「一条语句 vs 两条相邻语句」的全部歧义：`return x;` 与 `return; x;`、
 * `a + b;` 与 `a; +b;`、`f(1);` 与 `f; (1);` 均可区分。
 */

// 注释已走隐藏通道（见词法规则），本规则为「名义规则」，无产生式可达。
commentStmt
    : COMMENT
    ;

/*
 * 已移除的 C 关键字：保留为「保留字」而不是普通标识符。
 *
 * 目的：防止误用时被静默解析成合法程序。例如 `while x < 3 {}` 在
 * `while` 不作保留字时会解析成「表达式语句 while + 表达式语句 x<3 +
 * 块 {}」，错误被吞掉；保留后可得到明确的语法错误。
 *
 * 本规则不被任何产生式引用——它的存在只为把这些词注册进词法表，
 * 使其优先于 IDENT 匹配。手写 parser 应在此处给出可读提示，
 * 例如「while 已移除，请改用 for」。
 */
removedKeyword
    : 'while' | 'do'
    | 'unsigned' | 'signed' | 'short' | 'long' | 'float' | 'double'
    | 'typedef' | 'extern' | 'static' | 'register' | 'auto'
    | 'inline' | 'volatile' | 'restrict'
    ;

/*
 * ============================================================================
 *  声明
 * ============================================================================
 */

// --- let 声明（变量定义）---

// let 定义可变变量：`let a int = 32`。局部与全局同形。
// 每个 binding 必须显式声明类型，因此可写 `let a int = 1, b int = 2`，
// 但 `let a, b int = 1, 2` 不合法（类型不共享）。
letDecl
    : 'let' binding (',' binding)* ';'
    ;

// 变量绑定：名字 + 必需类型 + 可选初值。
// 不允许省略类型；省略初值时零值初始化（`let c int`）。
binding
    : IDENT typeRef ('=' expr)?
    ;

// --- const 声明（编译期常量）---

// const 必须带初值，且类型必须显式写出。
constDecl
    : 'const' IDENT typeRef '=' expr ';'
    ;

// --- fn 声明（函数）---

// 函数：`fn demo() void {}`、`fn add(a int, b int) int {}`。
// 返回类型省略即 void。不支持局部函数（与 TCC 的 "cannot use local functions" 一致）。
fnDecl
    : 'fn' IDENT '(' paramList? ')' typeRef? block
    ;

// 参数表：逗号分隔的参数列表。
paramList
    : param (',' param)*
    ;

// 参数：`name Type`（普通）或 `name ... Type`（类型化变参）。
// 裸 `...` 是仅供内置 prelude（printf 类异质变参）使用的逃生舱，
// 内部走传统 va_list 机制，用户代码不应使用。
param
    : IDENT '...' typeRef      // 类型化变参：`a ... int`，体内为 `[]int`
    | IDENT typeRef            // 普通参数：`a int`
    | '...'                    // 无类型变参（仅 prelude）
    ;

// --- type 声明（类型别名）---

// 类型别名：`type Handle = *void`、`type Callback = fn(int, int) int`。
typeDecl
    : 'type' IDENT '=' typeRef ';'
    ;

// --- struct / union 声明 ---

// struct：字段按「名字 类型」逐行书写，与 let 同形。
// 字段顺序即内存布局顺序；不支持位域、packed、自定义对齐。
structDecl
    : 'struct' IDENT '{' fieldDecl* '}'
    ;

// union：同一块内存的互斥视图。
unionDecl
    : 'union' IDENT '{' fieldDecl* '}'
    ;

fieldDecl
    : IDENT typeRef ';'
    ;

// --- enum 声明 ---

// enum：成员逐个书写，可带显式判别值；未指定时从 0 递增。
enumDecl
    : 'enum' IDENT '{' enumItem* '}'
    ;

enumItem
    : IDENT ('=' expr)? ';'
    ;

/*
 * ============================================================================
 *  语句
 * ============================================================================
 */

// 语句块：花括号包围的语句列表。
block
    : '{' stmt* '}'
    ;

// 语句分发。
stmt
    : block
    | letDecl
    | constDecl
    | ifStmt
    | forStmt
    | switchStmt
    | returnStmt
    | branchStmt
    | gotoStmt
    | labelStmt
    | exprStmt
    ;

// 标签语句：`label:` 用于 goto。标签是前缀，不带 `;`。
labelStmt
    : IDENT ':'
    ;

// goto 语句。
gotoStmt
    : 'goto' IDENT ';'
    ;

// break / continue 语句。
branchStmt
    : ('break' | 'continue') ';'
    ;

// return 语句：可返回单个表达式；无值 return 用于 void 函数。
returnStmt
    : 'return' expr? ';'
    ;

// 表达式语句或赋值语句。
exprStmt
    : exprList (assignOp exprList)? ';'
    ;

/*
 * ============================================================================
 *  分支语句
 * ============================================================================
 */

// if 语句：**条件必须带括号**；`else` 后可直接跟 if 形成 else-if 链。
ifStmt
    : 'if' '(' expr ')' block ('else' (ifStmt | block))?
    ;

// switch 语句：每个 case 自带块；支持多值与 default。
switchStmt
    : 'switch' expr '{' switchCase* '}'
    ;

switchCase
    : 'case' expr (',' expr)* block    // `case 1 { ... }` / `case 2, 3 { ... }`
    | 'default' block                  // `default { ... }`
    ;

/*
 * ============================================================================
 *  循环语句
 * ============================================================================
 */

// for 语句：循环只有 `for` 一个关键字，while / loop 已合并进来。
// 三种形态由 `{` 之前的成分区分。
forStmt
    : 'for' block              // 无限循环：`for { ... }`
    | 'for' expr block         // 条件循环：`for cond { ... }`（原 while）
    | 'for' forInParts block   // 遍历：`for i in 0..n { ... }`
    ;

// 遍历部分：可选下标 + 可选元素 + in + 迭代对象 + 可选排他区间。
//   `for v in arr`        → 元素遍历
//   `for i, v in arr`     → 同时取下标与元素
//   `for i in 0..n`       → 区间遍历（左闭右开）
forInParts
    : IDENT (',' IDENT)? 'in' expr ('..' expr)?
    ;

/*
 * ============================================================================
 *  赋值操作符
 * ============================================================================
 */

assignOp
    : '='      // 普通赋值
    | '+='     // 加赋值
    | '-='     // 减赋值
    | '*='     // 乘赋值
    | '/='     // 除赋值
    | '%='     // 模赋值
    | '&='     // 与赋值
    | '|='     // 或赋值
    | '^='     // 异或赋值
    | '<<='    // 左移赋值
    | '>>='    // 右移赋值
    ;

/*
 * ============================================================================
 *  表达式
 * ============================================================================
 */

// 表达式列表：逗号分隔（用于调用实参、表达式语句）。
exprList
    : expr (',' expr)*
    ;

// 表达式：优先级由低到高逐层展开，沿用 C 的优先级表。
expr
    : conditionalExpr
    ;

// 三元条件：`cond ? a : b`。
conditionalExpr
    : logicalOrExpr ('?' expr ':' expr)?
    ;

logicalOrExpr
    : logicalAndExpr ('||' logicalAndExpr)*
    ;

logicalAndExpr
    : bitOrExpr ('&&' bitOrExpr)*
    ;

bitOrExpr
    : bitXorExpr ('|' bitXorExpr)*
    ;

bitXorExpr
    : bitAndExpr ('^' bitAndExpr)*
    ;

bitAndExpr
    : equalityExpr ('&' equalityExpr)*
    ;

equalityExpr
    : relationalExpr (('==' | '!=') relationalExpr)*
    ;

relationalExpr
    : shiftExpr (('<' | '<=' | '>' | '>=') shiftExpr)*
    ;

shiftExpr
    : additiveExpr (('<<' | '>>') additiveExpr)*
    ;

additiveExpr
    : multiplicativeExpr (('+' | '-') multiplicativeExpr)*
    ;

multiplicativeExpr
    : castExpr (('*' | '/' | '%') castExpr)*
    ;

// 类型转换：`x as T`（替代 C 的 `(T)x`）。可链式书写。
castExpr
    : unaryExpr ('as' typeRef)*
    ;

// 一元运算：算术/逻辑/位取反、取地址 `&x`、解引用 `*p`。
// 注：`*` 与 `&` 在此处是一元，二元形态在更上层。
unaryExpr
    : ('-' | '+' | '!' | '~' | '*' | '&') unaryExpr
    | postfixExpr
    ;

// 后缀链：调用、下标、成员访问。`.` 对指针自动解引用（无 `->`）。
postfixExpr
    : primaryExpr postfixPart*
    ;

postfixPart
    : '(' callArgs? ')'     // 函数调用
    | '[' expr ']'          // 下标
    | '.' IDENT             // 成员访问（指针自动解引用）
    ;

callArgs
    : exprList
    ;

// 基本表达式。
primaryExpr
    : literal
    | IDENT
    | '(' expr ')'
    | structInit
    | sizeofExpr
    | lenExpr
    ;

// 字面量。
literal
    : NUMBER
    | STRING
    | CHAR
    | 'true'
    | 'false'
    ;

// sizeof：`sizeof(T)`，作用于类型。
sizeofExpr
    : 'sizeof' '(' typeRef ')'
    ;

// len：`len(arr)`，取数组/切片元素个数。对类型化变参读前置长度字段。
lenExpr
    : 'len' '(' expr ')'
    ;

/*
 * 结构体字面量：命名式 `Point{ x: 1, y: 2 }`（域顺序无关）或位置式
 * `Point{ 1, 2 }`（按声明顺序）。
 *
 * structInitBody 强制非空：这样 `if flag {}` 不会把 `flag {` 误判成
 * 结构体字面量，而会正确解析为「条件 flag + 块 {}」。空字面量 `Point{}`
 * 不支持，写 `Point{ }` 时请补一个字段。
 *
 * 残余歧义：若条件本身是「具名类型 + 位置式字面量」且紧跟块，仍可能歧义。
 * 消歧规则同 Go——条件中若需字面量请加括号：
 * `if (Point{1,2}.x == 1) {}`。手写 parser 用「首元素是否为 IDENT ':'」
 * 做一次前瞻即可区分命名式与位置式。
 */
structInit
    : IDENT '{' structInitBody '}'
    ;

structInitBody
    : structInitField (',' structInitField)* ','?   // 命名式
    | expr (',' expr)* ','?                          // 位置式
    ;

structInitField
    : IDENT ':' expr
    ;

/*
 * ============================================================================
 *  类型系统
 * ============================================================================
 */

// 类型引用：指针 / 数组 / 切片 / 函数类型 / 内建类型 / 具名类型。
// 玉衡一律「类型后置」：声明里类型写在名字之后，但类型自身的组合仍前缀书写。
typeRef
    : '*' typeRef                // 指针：`*int`、`**void`
    | '[' expr? ']' typeRef      // 数组 `[5]int` / 切片 `[]int`
    | fnType                     // 函数类型
    | builtinType
    | IDENT                      // struct/union/enum/type 引入的名字
    ;

// 函数类型：`fn(int, int) int`；返回类型省略即 void。
fnType
    : 'fn' '(' typeRefList? ')' typeRef?
    ;

typeRefList
    : typeRef (',' typeRef)*
    ;

// 内建类型。定宽命名，避免 C 的 `short/long/unsigned` 组合。
builtinType
    : 'int'     // 32 位有符号（默认整数类型）
    | 'i8' | 'i16' | 'i32' | 'i64'
    | 'u8' | 'u16' | 'u32' | 'u64'
    | 'f32' | 'f64'
    | 'bool'
    | 'char'
    | 'void'
    ;

/*
 * ============================================================================
 *  内置 prelude（替代头文件）
 * ============================================================================
 *
 * 没有 `#include`，也没有模块系统。编译器内置一段玉衡声明，在编译用户
 * 代码前自动编译一次，因此下列符号开箱可用（无需任何 import）：
 *
 *     pub fn printf(fmt *char, ...) int      // 无类型变参，内部走 va_list
 *     pub fn malloc(size u64) *void
 *     pub fn free(p *void) void
 *     pub fn memcpy(dst *void, src *void, n u64) *void
 *     pub fn strlen(s *char) u64
 *     pub fn exit(code int) void
 *
 * 实现位置：src/core/yh_builtin.c 的 builtin_prelude[]，经 tcc_compile_string()
 * 注入。该段文本每行一条声明，避免被 ASI 误伤。
 */

/*
 * ============================================================================
 *  词法规则
 * ============================================================================
 */

// 注释：行注释 `//` 与块注释 `/* ... */`。
// 走隐藏通道（与 NL 一致）：注释对 parser 完全不可见，可出现在任何位置，
// 与真实词法器「注释当空白跳过」的行为一致。
// 副作用：commentStmt 因此成为名义规则（无产生式可达），只为登记而保留。
COMMENT
    : ( '//' ~[\r\n]*
      | '/*' .*? '*/'
      ) -> channel(HIDDEN)
    ;

// 字符串字面量：双引号，支持反斜杠转义。语义为 NUL 结尾的 *char。
STRING
    : '"' ( '\\' . | ~["\\\r\n] )* '"'
    ;

// 字符字面量：单引号，支持转义。
CHAR
    : '\'' ( '\\' . | ~['\\\r\n] ) '\''
    ;

// 数字字面量：十六进制、二进制、八进制、十进制（整数/浮点数）。
NUMBER
    : '0' [xX] [0-9a-fA-F_]+                              // 0xFF
    | '0' [bB] [01_]+                                      // 0b1010
    | '0' [oO] [0-7_]+                                     // 0o17
    | [0-9] [0-9_]* ('.' [0-9_]+)? ([eE] [+-]? [0-9_]+)?   // 42、3.14、1e9
    ;

// 标识符：字母或下划线开头，后跟字母、数字或下划线。
IDENT
    : [A-Za-z_] [A-Za-z0-9_]*
    ;

// 换行符：ANTLR 参考放入隐藏通道；手写 lexer 必须把它交给 parser 执行 ASI。
NL
    : '\r'? '\n' -> channel(HIDDEN)
    ;

// 空白字符（跳过）。
WS
    : [ \t]+ -> skip
    ;
