grammar yh;

// IMPLICIT：归一化补入的隐式语句终结符（不对应任何源文本）。
// 语料门禁用同一规则生成该 token，参考语法据此区分显式分号。
tokens { IMPLICIT }
/*
 * 玉衡（yh）v0.1 语法参考。
 *
 * 语义、ABI 与构建规则见 docs/玉衡编译器改造方案.md。阶段 0 编译器由
 * TCC 0.9.27（AArch64/ELF）改造而来：C 手写 lexer + 单遍递归下降 parser，
 * 本文件不作为运行时依赖。
 *
 * 玉衡的设计前提：
 *   - 无文本预处理与宏；函数体内支持 `$if/$for` 编译期控制，不提供顶层条件编译；
 *   - 无头文件：没有 `#include`，运行时符号由 prelude 提供，C 函数可用
 *     顶层 `@[extern]` 声明；
 *   - 无 C 兼容：`.yh` 是唯一输入，C 语法分支已移除；
 *   - 简单语句以 `;` 结尾；以块收尾的语句（if / for / switch / 裸块，
 *     以及 fn / struct / union / enum 声明）整体不带尾分号；`if` 条件
 *     必须带括号，`for` / `switch` 不带；返回类型后置；
 *   - 标识符位置严格区分保留字；成员位置（字段声明 / 字面量字段 /
 *     成员访问）放开保留字，见 memberName。
 *
 * 简单语句、模块头、类型别名、字段与枚举成员可以用换行收尾：词法归一化
 *（compiler/lex/layout.yh）按行号、'}' 与 EOF 补入隐式 `;`，解析器只看
 * 归一化后的 token 流。因此本参考语法仍按显式 `;` 描述，且不存在
 *「一条语句 vs 两条相邻语句」的歧义。
 * 括号/方括号内换行不终结语句；括号外的行首运算符属于下一条语句，续行必须
 * 把运算符放在上一行末尾；`return` 在行尾结束（见 returnStmt）。
 */

/*
 * ============================================================================
 *  顶层结构
 * ============================================================================
 */

// 源文件：模块头（可选）+ 顶层声明列表 + EOF。test 声明是顶层声明的一种。
sourceFile
    : topLevelDecl* EOF
    ;

// 顶层声明：`pub` 导出标记。struct/union/enum 的 pub 可选（2026-10-12）：
// 带 pub 的类型进接口、跨模块可命名（struct/union 字段一律公开，enum 成员
// 常量随枚举导出，见 ADR-0013）；不带 pub 的是模块私有类型，只在本模块
// 可见、不进接口。let/const/fn/type 的 pub 同样可选，默认仅本模块可见。
// **let 不支持导出**：`pub let` 非法（见 plainDeclBody 注释）。
// 类型声明不允许嵌套：struct/union/enum/type 只能出现在顶层。
topLevelDecl
    : 'pub' exportedDeclBody
    | plainDeclBody
    | attributeGroup attributedDecl
    | testDecl
    ;

// 单组属性前缀只修饰一个紧随其后的顶层声明；属性名逗号分隔，不允许空组或尾逗号。
attributeGroup
    : '@' '[' attributeName (',' attributeName)* ']'
    ;

// comptime、noreturn 与将来未知属性均保持普通标识符；extern / inline
// 是保留字 token。由语义检查负责识别属性名称及适用范围。
attributeName
    : IDENT | 'extern' | 'inline'
    ;

attributedDecl
    : 'pub'? attributedFnDecl
    | 'pub'? (structDecl | unionDecl | enumDecl)
    ;

exportedDeclBody
    : constDecl
    | fnDecl
    | typeDecl
    | structDecl
    | unionDecl
    | enumDecl
    ;

// 不带 pub 的顶层声明：struct/union/enum 在此为模块私有类型（2026-10-12）。
plainDeclBody
    : letDecl
    | constDecl
    | fnDecl
    | typeDecl
    | structDecl
    | unionDecl
    | enumDecl
    ;

// test 声明（YT0，2026-10-23）：`test "名称" { ... }` 是字符串行为测试；
// `test 声明名 { ... }` 是绑定本模块顶层声明的文档测试（doctest）。
// 只允许顶层且不带 pub/属性；名称的 STRING 与 IDENT token 互斥，块首 token
// 为 '{'，因此与其它顶层声明无歧义。块后不写显式分号（与 fn 声明一致）。
// 语法层只检查声明与块体形态；测试发现/绑定/执行由后续 yh test 实现。
testDecl
    : 'test' testName block
    ;

// 测试名称：非空字符串字面量或单个标识符。空字符串在语义/语法检查拒绝；
// 不接受匿名块、限定名（test math.add）或计算名称。
testName
    : STRING
    | IDENT
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
 *   - **以块收尾的语句整体不写 `;`**：if / for / switch / 裸块，以及 fn /
 *     struct / union / enum 声明（即 `}` 之后不再跟分号）；
 *   - **标签 `L:` 必须后随被标记的语句**，不能悬空到块尾；
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
 *
 * 保留字仅排除「标识符位置」；成员位置（字段声明 / 字面量字段 /
 * 成员访问）允许使用保留字，见 memberName。
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
// 绑定列表为行内列表，不允许尾逗号（见 structInitBody 的列表策略）。
letDecl
    : 'let' binding (',' binding)* stmtEnd
    ;

// 变量绑定：名字 + 必需类型 + 可选初值。
// 不允许省略类型；省略初值时零值初始化（`let c int`）。
binding
    : IDENT typeRef ('=' expr)?
    ;

// --- const 声明（编译期常量）---

// const 必须带初值，且类型必须显式写出。
constDecl
    : 'const' IDENT typeRef '=' expr stmtEnd
    ;

// --- fn 声明（函数）---

// 函数：`fn demo() void {}`、`fn add(a int, b int) int {}`。
// 返回类型省略即 void。不支持局部函数（与 TCC 的 "cannot use local functions" 一致）。
fnDecl
    : fnSignature block
    ;

// 函数签名独立成规则，供普通定义与属性声明共用。
fnSignature
    : 'fn' IDENT '(' paramList? ')' typeRef?
    ;

// 属性函数允许函数体定义，也允许以分号结尾的外部声明；是否允许无体
// 以及属性组合是否合法由语义检查决定。
attributedFnDecl
    : fnSignature (block | stmtEnd)
    ;

// 参数表：逗号分隔的参数列表（行内列表，不允许尾逗号）。
paramList
    : param (',' param)*
    ;

// 参数：`name Type`（普通）或 `name ... Type`（类型化变参）。
// 裸 `...`（ELLIPSIS）是仅供内置 prelude（printf 类异质变参）使用的逃生舱，
// 内部走传统 va_list 机制，用户代码不应使用。
param
    : IDENT ELLIPSIS typeRef   // 类型化变参：`a ... int`，体内为 `[]int`
    | IDENT typeRef            // 普通参数：`a int`
    | ELLIPSIS                 // 无类型变参（仅 prelude）
    ;

// --- type 声明（类型别名）---

// 类型别名：`type Handle = *void`、`type Callback = fn(int, int) int`。
typeDecl
    : 'type' IDENT '=' typeRef stmtEnd
    ;

// --- struct / union 声明 ---

// struct/union 只能以 `pub struct` / `pub union` 形式声明（'pub' 由
// topLevelDecl 消费）：类型必然导出，且**全部字段公开**——字段不再接受
// pub 前缀，也没有私有字段；跨模块可见性只由类型本身的 pub 决定。
// 类型声明禁止嵌套（见 topLevelDecl 注释）。
// struct 字段按「名字 类型」逐行书写，与 let 同形。
// 字段顺序即内存布局顺序；不支持位域、packed、自定义对齐。
// 字段名允许保留字（memberName）——union 的标签域 `type int;` 因此可用。
structDecl
    : 'struct' IDENT '{' fieldDecl* '}' IMPLICIT?
    ;

// union：同一块内存的互斥视图。与 struct 同规则：必须 `pub union`，
// 全部字段公开。
unionDecl
    : 'union' IDENT '{' fieldDecl* '}' IMPLICIT?
    ;

// 字段声明。字段名放开保留字（见 memberName）；不写 pub 前缀
// （`pub struct` 的字段一律公开），`pub` 仅可作为字段名出现。
fieldDecl
    : memberName typeRef stmtEnd
    ;

// --- enum 声明 ---

// enum：必须以 `pub enum` 声明（'pub' 由 topLevelDecl 消费）；成员常量
// 随枚举导出（F_PUB），跨模块以 `模块名.成员` 引用。成员逐个书写，
// 可带显式判别值；未指定时从 0 递增。
enumDecl
    : 'enum' IDENT '{' enumItem* '}' IMPLICIT?
    ;

// enum 成员名是普通标识符（与 let/const 同一命名空间），不允许保留字。
enumItem
    : IDENT ('=' expr)? stmtEnd
    ;

/*
 * ============================================================================
 *  语句
 * ============================================================================
 */

// 语句块：花括号包围的语句列表。
block
    : '{' stmt* '}' IMPLICIT?
    ;

// 语句终结：显式分号，或归一化补入的隐式终结符。显式分号仍代表空语句
// 以外的唯一写法；隐式终结只出现在可省略分号的位置。
stmtEnd
    : ';'
    | IMPLICIT
    ;

// 语句分发。
stmt
    : block
    | letDecl
    | constDecl
    | comptimeIfStmt
    | comptimeForStmt
    | ifStmt
    | forStmt
    | switchStmt
    | returnStmt
    | branchStmt
    | gotoStmt
    | labelStmt
    | exprStmt
    ;

// 编译期分支和整数区间展开只允许出现在函数体语句位置，不提供顶层形式。
comptimeIfStmt
    : '$' 'if' '(' expr ')' block ('$' 'else' (comptimeIfStmt | block))?
    ;

comptimeForStmt
    : '$' 'for' IDENT 'in' ('(' expr '..' expr ')' | IDENT '.' IDENT) block
    ;

// 标签语句：`label:` 用于 goto。标签是前缀，必须后随被标记的语句——
// 悬空标签 `L: }` 非法（同 C 的约束）。标签名属标识符位置，不允许保留字。
// 嵌套书写 `L1: L2: stmt` 合法，解析为标签的嵌套包裹。
labelStmt
    : IDENT ':' stmt
    ;

// goto 语句。
gotoStmt
    : 'goto' IDENT stmtEnd
    ;

// break / continue 语句。
branchStmt
    : ('break' | 'continue') stmtEnd
    ;

// return 语句：可返回单个表达式；无值 return 用于 void 函数。
// `return` 在行尾结束（归一化补隐式 ';'）；跨行返回值必须写成 `return (`
// 或在括号内换行，不再吞掉下一行开头的表达式。
returnStmt
    : 'return' expr? stmtEnd
    ;

// 表达式语句或单目标赋值语句。
// v0.1 不支持元组赋值：`a, b = 1, 2;` 非法；逗号仅用于调用实参（exprList）。
exprStmt
    : expr (assignOp expr)? stmtEnd
    ;

/*
 * ============================================================================
 *  分支语句
 * ============================================================================
 */

// if 语句：**条件必须带括号**（因此不存在 structInit 与块的头部分歧）；
// `else` 后可直接跟 if 形成 else-if 链。
ifStmt
    : 'if' '(' expr ')' block ('else' (ifStmt | block))?
    ;

// switch 语句：每个 case 自带块；支持多值与 default。
switchStmt
    : 'switch' expr '{' switchCase* '}' IMPLICIT?
    ;

// case 块之间无 fallthrough，default 的书写位置因此无语义；
// default 至多出现一次，唯一性由语义检查保证（语法不限制位置）。
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
    : IDENT (',' IDENT)? 'in' expr (RANGE expr)?
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

// 表达式列表：逗号分隔（用于调用实参与函数类型参数表）。
exprList
    : expr (',' expr)*
    ;

// 表达式：优先级由低到高逐层展开，沿用 C 的优先级表。
// `$if (cond) e1 $else e2` 是编译期表达式选择（位于链最上层，条件必须
// 编译期可求值；两个分支都做语法与类型检查，但只求值/发射选中分支）；
// 语句形态 `$if (…) { … }` 见 comptimeIfStmt。
expr
    : comptimeIfExpr
    | conditionalExpr
    ;

// 编译期表达式选择：`$else` 必须书写（表达式没有「原值」）。
// 无歧义论证：语句形态 `$if (…) '{' … '}'` 的 `)` 之后要求块，而表达式
// 形态要求 expr（不可从 '{' 开始），单 token lookahead 即可区分；
// `$else` 就近匹配（与 C 的 else-if 链同理）。
comptimeIfExpr
    : '$' 'if' '(' expr ')' expr '$' 'else' expr
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
    : unaryExpr (('*' | '/' | '%') unaryExpr)*
    ;

// 一元运算：算术/逻辑/位取反、取地址 `&x`、解引用 `*p`。
// 注：`*` 与 `&` 在此处是一元，二元形态在更上层。
unaryExpr
    : ('-' | '+' | '!' | '~' | '*' | '&') unaryExpr
    | postfixExpr
    ;

/*
 * 后缀链：调用、下标、成员访问与类型转换。普通成员访问的 `.` 对指针
 * 自动解引用（无 `->`）；`.to_type(T)` 直接转换当前表达式，不解引用。
 * `x.to_type(T)` 的参数是 typeRef，不是表达式；可链式写为
 * `x.to_type(i64).to_type(int)`，也可直接接下标/成员。
 * 后缀优先于一元：`-x.to_type(int)` 是 `-(x.to_type(int))`；
 * 转换 `-x` 须写 `(-x).to_type(int)`。
 * `to_type` 是专用保留字，不能作为普通成员名；旧 `as` 不能作普通标识符，
 * 但仍可作成员名。
 */
postfixExpr
    : primaryExpr postfixPart*
    ;

postfixPart
    : '(' callArgs? ')'     // 函数调用
    | '[' expr ']'          // 下标
    | '.' 'to_type' '(' typeRef ')'  // 类型转换，目标必须是类型
    | '.' memberName        // 成员访问（指针自动解引用）
    ;

callArgs
    : exprList
    ;

// 基本表达式。
primaryExpr
    : comptimeCall
    | literal
    | IDENT
    | '(' expr ')'
    | structInit
    | sizeofExpr
    | lenExpr
    ;

// 编译期调用支持同模块 $IDENT(...) 与导入模块 $module.IDENT(...)；
// 诊断内建仍使用未限定形式，与普通运行时调用保持词法区分。
// assert/compile_error/compile_warn 由语义检查限制为函数内独立语句，不能作值。
// `$is_type(x, T)` 的第二实参是类型引用（expr 不能以类型名开头，因此与
// 第一条备选无歧义，ANTLR 尝试失败后自动回溯）；`$is_int`/`$is_float`
// 由语义层按内建谓词名拦截（实参是普通表达式）。
comptimeCall
    : '$' comptimeTarget '(' callArgs? ')'
    | '$' 'is_type' '(' expr ',' typeRef ')'
    ;

comptimeTarget
    : IDENT ('.' IDENT)?
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
// `sizeof(x)` 中 x 按类型名解析；表达式形式不支持——取元素个数用 len，
// 取元素大小请改写（如对指针类型 `sizeof(*p)`）。避免 C 的
// 「类型/表达式同名」二义性进入语法。
sizeofExpr
    : 'sizeof' '(' typeRef ')'
    ;

// len：`len(arr)`，取数组/切片元素个数。对类型化变参读前置长度字段。
lenExpr
    : 'len' '(' expr ')'
    ;

/*
 * 结构体字面量：命名式 `Point{ x: 1, y: 2 }`（域顺序无关）或位置式
 * `Point{ 1, 2 }`（按声明顺序）。空字面量不支持：`Point{}` 非法——
 * 这同时保证 `switch flag {}` / `for flag {}` 的 `{}` 永远解析为块
 * （if 因条件强制括号，无此问题）。
 *
 * for/switch 头部 `IDENT {` 的边界消歧（贪心取字面量，与 ANTLR ALL(*)
 * 的判定结果一致）：
 *   对 `{` 做花括号配对——若组内内容能解析为 structInitBody 且配对
 *   `}` 之后紧跟 `{`（块的开始），则取字面量分支；否则该 `{` 一律
 *   视为块/case 体。手写 parser 只需一次花括号扫描，无需回溯。
 *   条件末尾需要位置式字面量时请加括号：`switch (Point{1,2}) { ... }`。
 *
 * 命名式 vs 位置式：首元素第二个 token 为 `:` 即命名式，否则位置式。
 */
structInit
    : IDENT '{' structInitBody IMPLICIT? '}'
    ;

/*
 * structInitBody 强制非空（见 structInit 注释）。
 *
 * 尾逗号策略：逐行列表（本规则，按字段逐行书写）允许尾逗号；
 * 行内列表（调用实参、参数表、let 绑定）不允许。
 */
structInitBody
    : structInitField (',' structInitField)* ','?   // 命名式
    | expr (',' expr)* ','?                          // 位置式
    ;

// 字面量字段名放开保留字（见 memberName）。
structInitField
    : memberName ':' expr
    ;

/*
 * 成员名：仅在「字段声明（fieldDecl）/ 字面量字段（structInitField）/
 * 成员访问（postfixPart 的 `.` 之后）」三处放开保留字，对齐
 * JavaScript 的属性名规则；专用后缀 `to_type` 除外。
 *
 * 动机：union 的标签域 `type int;`、与 JSON/C 交互时的高频字段名
 * `len` / `type` / `default` 若被保留字挡住，数据建模将非常别扭。
 * 局部/全局标识符位置（let / const / fn / enum 成员 / 标签）仍然严格：
 * `let len int = 1;` 非法。
 */
memberName
    : IDENT
    | 'pub' | 'let' | 'const' | 'fn' | 'type' | 'struct' | 'union' | 'enum'
    | 'if' | 'else' | 'switch' | 'case' | 'default' | 'for' | 'in' | 'as'
    | 'return' | 'break' | 'continue' | 'goto'
    | 'true' | 'false' | 'sizeof' | 'len' | 'test'
    | 'int' | 'i8' | 'i16' | 'i32' | 'i64'
    | 'u8' | 'u16' | 'u32' | 'u64'
    | 'f32' | 'f64' | 'bool' | 'char' | 'void'
    | 'while' | 'do'
    | 'unsigned' | 'signed' | 'short' | 'long' | 'float' | 'double'
    | 'typedef' | 'extern' | 'static' | 'register' | 'auto'
    | 'inline' | 'volatile' | 'restrict'
    ;

/*
 * ============================================================================
 *  类型系统
 * ============================================================================
 */

// 类型引用：指针 / 数组 / 切片 / 函数类型 / 内建类型 / 具名类型。
// 玉衡一律「类型后置」：声明里类型写在名字之后，但类型自身的组合仍前缀书写。
typeRef
    : '@' '[' 'extern' ']' fnType  // C 函数类型，独立首 token，无歧义
    | '*' typeRef                // 指针：`*int`、`**void`
    | '[' expr? ']' typeRef      // 数组 `[5]int` / 切片 `[]int`
    | fnType                     // 函数类型
    | builtinType
    | IDENT                      // struct/union/enum/type 引入的名字
    ;

// 函数类型：`fn(int, int) int`；返回类型省略即 void。
// `@[extern] fn(...)` 指定 C ABI；extern 签名与共享数据字段的 fn 默认 C ABI。
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
 * 没有 `#include`，也没有模块系统。编译器为下列符号在每个编译单元开始时
 * 直接登记运行时函数 Sym（不经过 yh 源码解析），因此下列符号开箱可用
 * （无需任何 import）。用户的固定参数 C 函数另用 `@[extern] fn ...;` 声明：
 *
 *     pub fn printf(fmt *char, ...) int      // 无类型变参，内部走 va_list
 *     pub fn malloc(size u64) *void
 *     pub fn free(p *void) void
 *     pub fn memcpy(dst *void, src *void, n u64) *void
 *     pub fn strlen(s *char) u64
 *     pub fn exit(code int) void
 *     pub fn open(path *char, flags int, ...) int   // 无类型变参（mode 可选）
 *     pub fn close(fd int) int
 *     pub fn read(fd int, buf *void, count u64) i64
 *     pub fn write(fd int, buf *void, count u64) i64
 *
 * 实现位置：compiler/gen/symbols.yh 直接登记运行时入口；裸 `...` 仅允许
 * 出现在本 prelude，用户源码书写裸 `...` 报错。
 * 语义细节（提升规则等）见 docs/03-design/00-语义边界-0.0.1.md §7。
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

/*
 * 转义收敛为已知集合：\n \r \t \0 \a \b \f \v \' \" \\ \$，
 * 外加 \xNN 十六进制（两个数字）。未知转义（如 \q）不匹配任何分支，
 * 直接词法报错——不再静默吞掉（旧规则 `'\\' .` 会把 `\q` 当成 `q`）。
 * STRING 与 CHAR 使用同一转义集合。
 */
fragment ESC
    : '\\' [nrt0abfv'"\\$]
    ;

fragment ESC_HEX
    : '\\x' [0-9a-fA-F] [0-9a-fA-F]
    ;

// 字符串字面量：双引号，语义为 NUL 结尾的 *char。
STRING
    : '"' ( ESC | ESC_HEX | ~["\\\r\n] )* '"'
    ;

// 字符串插值（I0–I3）：`${expr[:spec]}` 是 STRING token 内部的编译期细化，
// 参考语法仍把整个字面量视为一个 STRING（`\$` 转义后不启动插值）。表达式
// token 由编译器 lex/interp.yh 在 layout 前展开，因此 ANTLR 不解析 `${...}`
// 内部；v1 禁止内部裸双引号/花括号/顶层三元，保证外层 STRING 可精确匹配。
// 完整语义与限制见 docs/03-design/yh-字符串插值设计.md。

// 字符字面量：单引号，单字符或单转义。
CHAR
    : '\'' ( ESC | ESC_HEX | ~['\\\r\n] ) '\''
    ;

/*
 * 数字字面量：十六进制、二进制、八进制、十进制（整数/浮点数）。
 * 下划线作分组分隔符，但必须夹在两个数字之间：
 *   合法：1_000、0xFF_00、0b1010_1010、1.5、1e9
 *   非法：1_（尾下划线）、1__0（连续下划线）、0b_1（前导下划线）——
 *   这些输入中的下划线段会落回 IDENT，得到明确的语法错误。
 * 注意 `.` 后必须紧跟数字，因此 `0..n` 中的 `0` 不会被误读为浮点数。
 */
NUMBER
    : '0' [xX] [0-9a-fA-F] ([_]? [0-9a-fA-F])*                              // 0xFF
    | '0' [bB] [01] ([_]? [01])*                                            // 0b1010
    | '0' [oO] [0-7] ([_]? [0-7])*                                          // 0o17
    | [0-9] ([_]? [0-9])* ('.' [0-9] ([_]? [0-9])*)? ([eE] [+-]? [0-9] ([_]? [0-9])*)?   // 42、3.14、1e9
    ;

// 区间 `..`（for-in 左闭右开）与变参 `...`：显式成词，
// 手写 lexer 有明确对照；`..` 与 NUMBER 小数点靠「`.` 后必须跟数字」区分。
RANGE    : '..' ;
ELLIPSIS : '...' ;

// 标识符：字母或下划线开头，后跟字母、数字或下划线。
// 保留字（parser 规则中的字符串字面量）优先于本规则匹配。
IDENT
    : [A-Za-z_] [A-Za-z0-9_]*
    ;

// 换行符：保留在隐藏通道仅用于记录行号；语句终结由归一化补入隐式 ';'。
// 归一化规则：括号/方括号外、上一 token 能结束语句时（含 '}' 前与 EOF 前）
// 补 ';'；属性组之后、行首 '{' 之前不补；显式 ';' 优先。测试门禁
//（tests/yh/check.py）用同一规则归一化 token 后再解析。
NL
    : '\r'? '\n' -> channel(HIDDEN)
    ;

// 空白字符（跳过）。吸收 \r \f \v：CR-only、表单符文件不再词法报错；
// CRLF 不受影响——NL 的 '\r'? '\n' 按最长匹配仍整体成词。
WS
    : [ \t\r\f\u000B]+ -> skip
    ;
