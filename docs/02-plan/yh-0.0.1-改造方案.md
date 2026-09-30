# yh 编译器 0.0.1 改造方案（C 语言开发，复用 TCC arm64 后端）

> **历史文档（0.0.1，C 版阶段）**：`src/`（C 编译器）、`-run`、`-sysroot`、libtcc1 与
> M0–M6 里程碑均已于 0.0.3 随 stage0 删除终结。0.0.1 已发布的语言语义仍有效，
> 现行设计见 `docs/03-design/`，现行待办见 `docs/todo.md`。
> 基础事实：src/ 是裁剪到 AArch64/ELF 的 TCC 0.9.27（~22k 行）。
> `docs/yh.g4` 是语法基准；tests/yh 有 94 个语法语料（65 正例 + 29 反例）。
> 这些正例允许未定义符号、错误类型或没有 `main`，不能直接当作编译/运行正例。
> 本文件是 0.0.1 的详细实施与验收依据；`docs/todo.md` 只按 §6 的任务编号追踪状态。
> 数组按值的语言边界由 `docs/adr/0001-yh数组按值调用边界.md` 锁定，
> 内部传递机制须在 M0 实测后另作决定。

## 1. 版本目标与非目标

**v0.0.1 = 函数体单遍编译、无优化、能跑通闭环的第一版。**

假设与边界：目标程序是 **AArch64 Linux ELF**；当前开发宿主机是 Darwin arm64。
`-run` 的运行语义以 AArch64 Linux 为准；Darwin 只作为编译器构建和语法检查宿主，
不以其 libc 可变参数调用结果验收。`make` 必须明确依赖可产出 AArch64 Linux ELF
目标文件的 C 工具链，不能依赖改造后的 yh 编译器继续编译 C 运行时。

交付定义：

```sh
make                      # 产出 yh、libtcc.a、libtcc1.a
yh hello.yh -o prog       # 在配好 Linux sysroot/libc 的环境生成 AArch64 Linux ELF
yh -run hello.yh          # 在 AArch64 Linux 内存编译并运行
yh --syntax-check f.yh    # 只检查词法/语法，容许未定义符号和类型错误
```

**在范围内**（与 yh.g4 的可达语法行为一致，不做语法子集；两条名义规则见 §6）：
词法（含 RANGE/ELLIPSIS、转义收敛、数字下划线）、全部声明形态、全部语句形态、
表达式与 `.to_type(T)`、structInit、memberName、`sizeof(T)`、`len()`、
切片 `[]T`、`for-in`（数组/切片/区间/双目标）、类型化变参、裸 `...`、
内置 prelude（printf/malloc/free/memcpy/strlen/exit/open/write）。

**在范围外**（推迟到 0.0.2+）：预处理裁剪成纯词法器、切片表达式 `arr[0..2]`、
数组/切片字面量、嵌套 struct/enum 声明、`sizeof(expr)`、诊断信息打磨、
寄存器分配之外的任何优化，以及非 AArch64 Linux 平台的运行时支持。

**先决条件**：M0 的构建链、数组 ABI、切片 ABI 和测试口径验证通过后，才把
「3~4 周」作为估算基线；未通过时先修正设计，不进入大规模 parser 改写。

## 2. 架构路线与待验证的表示选择

### 2.1 函数体编译保持单遍，不引入 AST

TCC 是「边解析边生成」：解析函数直接操作 SValue 值栈（vpush/vsetc/gv）。
yh 编译模式沿用这个模型：解析时产出 SValue/Sym，复用 gen_cast/gen_op/
gfunc_call 等机制。`--syntax-check` 复用同一套语法产生式，但跳过符号解析、
类型检查和代码生成；它必须接受语法合法而语义错误的 tests/yh 正例。
两种模式共享词法与解析，不引入 AST，也不把“能解析”误写为“能编译”。

### 2.2 新文件承载 yh parser，延后清理 C parser

tccgen.c（7122 行）里的 C 语法解析与值栈/类型操作/初始化器/代码生成互相调用。
先做调用关系清单、移出确实要复用的解析无关机制；yh 全部回归通过后，再删除
已无调用的 C 解析函数。预计净删 2.5k~3k 行只是估算，不能作为删除指标。
yh 新代码按职责切分；词法修补直接放在现有 tccpp.c/tcctok.h/tcc.h：

| 新文件 | 职责 | 预估行数 |
| --- | --- | --- |
| `src/core/yh_type.c` | typeRef 解析、内建类型映射、类型别名、struct/union/enum 声明 | ~700 |
| `src/core/yh_decl.c` | 顶层/局部声明、binding、fn、pub 可见性 | ~600 |
| `src/core/yh_stmt.c` | block、if/for/switch、label/goto、exprStmt、break/continue | ~800 |
| `src/core/yh_expr.c` | 优先级链、to_type 后缀转换、structInit、sizeof/len、memberName | ~900 |
| `src/core/yh_slice.c` | 切片类型规范化、for-in 降糖、变参打包、len() 代码生成 | ~500 |
| `src/core/yh_builtin.c` | 各编译单元的 prelude 外部符号登记 | ~200 |

按实际跨文件调用为共享函数补声明，保持 ONE_SOURCE 构建能编译；不把全部静态函数
暴露到 `tcc.h`。新文件尽量符合行数规范；既有 `tccgen.c` 仅在本次确实需要的范围内
拆分，不能一边要求“只删不拆”，一边要求它在 0.0.1 内降到 1000 行以下。

### 2.3 切片 = 匿名结构体 + 登记表（v0.0.1 不加 VT_SLICE）

`[]T` 暂定降糖为匿名 `struct { u64 len; T *data; }`（16 字节）。
两个字在寄存器足够时可按现有结构体路径传递，寄存器不足时走栈；
“arm64-gen.c 零改动”须由 M0 传参/返回实验证明，不能先当作结论。
同一元素类型的 `[]T` 必须规范化到同一个结构体 Sym；登记表至少存活到当前
编译单元结束，不能随某个函数作用域释放，否则不同声明中的 `[]T` 可能不兼容。
`len(s)` 读 len 字段；`s[i]` 降糖为 `s.data[i]`；`for v in s` 降糖为下标循环。
若规范化与类型相容性无法用少量胶水实现，M0 应重新比较专用类型标记方案；
不得以“匿名结构体零成本”为前提继续排期。

## 3. 词法改造（tccpp.c / tcctok.h / tcc.h 最小触改）

| # | 改动 | 位置 |
| --- | --- | --- |
| 1 | 用 yh 保留字表替换 C 关键字；同时审计原有 C/GNU 专用关键字的处理，不能意外占用 yh 的普通标识符 | tcctok.h |
| 2 | 已移除 C 关键字（while/do/short/…/restrict 共 16 个）仍注册为报错保留字；成员位置按 `memberName` 允许使用 | tcctok.h / yh parser |
| 3 | `case '.'`：两个点 → `TOK_RANGE`，三个点维持 `TOK_DOTS`；先检查整个 token 编号表再分配，**0xc9 已是 `TOK_SHR`** | tcc.h / tccpp.c:2791 |
| 4 | 数字扫描：小数点仅在后跟数字时吞入；拒绝前导点浮点数；下划线须夹在当前进制的两个数字之间 | tccpp.c:2757 |
| 5 | 转义收敛：ESC 集合 `\n \r \t \0 \a \b \f \v \' \" \\` + `\xNN`，未知转义词法报错 | tccpp.c 字符串/字符分支 |
| 6 | yh 编译入口不开 `PARSE_FLAG_PREPROCESS`，并显式拒绝 `#`、`##`；保留构建工具所需的 C 预处理能力直到 C 解析器清理完成 | yh 驱动入口 / tccpp.c |

`WS` 扩充 `[ \t\r\f\u000B]`、NL 保持隐藏处理，与语料 `11-lex/08_ws_specials.yh` 对齐。

## 4. 语法 → TCC 机制映射表

| yh.g4 规则 | 实现方式 | 复用点 |
| --- | --- | --- |
| 内建类型 | 直映射：i8→VT_BYTE、i16→VT_SHORT、int/i32→VT_INT、i64→VT_LLONG、u*→对应整数类型+VT_UNSIGNED、f32/f64→VT_FLOAT/VT_DOUBLE、bool→VT_BOOL、char 作为 u8 字节类型、void→VT_VOID | Type 编码；char/int 的同型规则见 §4.1 |
| `*T` / `[N]T` | VT_PTR / VT_ARRAY；`[N]T` 的 N 必须是编译期整数常量，函数边界另按 M0 确定的按值 ABI 处理 | type_decl、type_size |
| `[]T` | 规范化的匿名结构体 `{u64 len; T *data}` + 按元素类型查找的登记表（决策 2.3） | struct_layout |
| `fn(A,B) R` | VT_FUNC | post_type |
| type 别名 | Sym 间接层 | typedef 机制 |
| `let/const` 声明 | 名字前置；let 走变量落地，const 单独区分数值编译期常量与字符串地址等可重定位值；VT_CONSTANT 只是只读类型修饰，不能独自表示“编译期常量” | decl_initializer_alloc、常量表达式机制 |
| `pub` | 顶层符号才允许导出；非 pub 符号限制在当前编译单元，跨文件可见性须测 ELF 符号表 | 存储类与 ELF 符号绑定 |
| fn 声明 | 用户源码只有定义，无原型；编译器直接登记 prelude extern Sym，不经 yh 源码解析 | 函数类型、external_global_sym |
| struct/union/enum | 字段解析（memberName）→ 布局计算原样复用；enum 判别值走 expr_const | struct_decl、enum 机制 |
| `if (e) block else …` | 强制括号，条件 gen 条件跳转 | gvtst/gjmp |
| `for` 三形态 | 循环头/尾标签 + break/continue 栈；`for-in` 降糖（见 §5） | block 的循环框架 |
| `switch case N { }` | case 值列表（多值=多条目同块）、每 case 块尾隐式跳到 switch 末尾（无 fallthrough）、default 位置自由、default 唯一性语义检查 | switch 的 case 排序与跳转 |
| `labelStmt: IDENT ':' stmt` | 包裹式解析；标签登记 + goto 跳转 | label sym 机制 |
| `exprStmt: expr (assignOp expr)? ';'` | 语法检查模式只识别形态；编译模式先做 yh 的目标类型与可赋值检查，再调用后端，拒绝 `a == b = c` 和对强转结果赋值 | gen_assign_cast、VT_LVAL 检查 |
| 赋值运算符 11 种 | 逐一映射复合赋值降糖 | expr_eq 的复合赋值路径 |
| 优先级链（与 C 同表） | 逐层重写解析，运算全走 gen_op 分派 | gen_opic/gen_opif/... |
| `x.to_type(T)` | 后缀链解析 typeRef，先按 §4.1 检查源/目标类型；仅已批准的标量转换交给 gen_cast，数组/切片走专用降糖；结果一律为右值。与调用、下标、成员访问同级，可写 `x.to_type(T).y` | yh 类型检查 + gen_cast |
| `sizeof(T)` | 仅 typeRef 形态 | sizeof 路径裁剪 |
| `len(e)` | 数组→编译期常量；切片/变参→读 len 字段 | 新增内建 |
| structInit | = C99 复合字面量 + 指定初始化；空体/混写在解析层拒绝 | 复合字面量、decl_initializer、init_putv |
| memberName | Sym 按 token 编码做 key → 关键字 token 直接作字段名；专用后缀 `to_type` 不作普通成员名 | Sym 哈希机制（零成本） |
| 字符串字面量 | 匿名全局 char 数组 + 退化为 `*char` | 现有字符串落地 |
| 裸 `...` | 仅内置 prelude 允许；调用 libc 的可变参数行为以 AArch64 Linux 实测验收 | arm64 va_list 内建 |

### 4.1 类型转换规则与后端边界

0.0.1 保留裸指针，类型转换统一写成 `x.to_type(T)`；不新增 `unsafe`、
只读指针或所有权系统。`to_type` 是专用后缀关键字，旧 `as` 写法报语法错误。
因此显式指针重解释是**未检查的低层操作**，不能承诺内存安全；`pub` 只影响
声明的跨文件可见性，与表达式转换无关。`const` 表示编译期常量绑定，不表示
「指向只读内存」；若以后要求禁止通过指针修改常量内容，必须先设计指针限定符。

先规范化类型别名，再按以下矩阵判断。`int` 与 `i32` 同型；0.0.1 的 `char`
定义为 8 位无符号字节，与 `u8` 同型，不承担 Unicode 字符语义；
字符字面量若不在 0..255 范围内，编译模式报错。这里的
「隐式」只用于赋值、传参、返回和二元运算的类型协调，不交给 TCC 自行采用
C 的通常算术转换；二元运算仅在一个操作数类型能无损转换为另一个类型时
选用后者，否则要求显式 `to_type`。`if`/`for` 条件和逻辑运算要求 `bool`。
比较、条件表达式、复合赋值、`switch` 判别值与 case、类型化变参也须经过
同一套 yh 规则，不能绕过检查直接调用 `gen_op` 或 `gen_assign_cast`。

| 源 → 目标 | 0.0.1 规则 | 实现要点 |
| --- | --- | --- |
| 同型或透明 type 别名 | 隐式允许；`to_type` 允许但仍产生右值 | 比较规范化后的类型身份；不可仅比较大小 |
| 整数字面量 → 整数类型；浮点字面量 → f32/f64 | 在目标类型可表示时隐式允许；f32 字面量按 f32 舍入 | 一元负号先与整数字面量折叠，再按目标类型查范围；整数 `0` 另可表示任意数据空指针 |
| 整数 → 整数，f32 → f64 | 目标能容纳源类型全部取值时隐式允许；其余整数转换须 `to_type` | i/u 混合按取值范围判断，不能只比较位宽；整数缩窄取低 N 位，再按目标符号解释 |
| 整数 ↔ 浮点，f64 → f32 | 须 `to_type`；整数转浮点、f64 转 f32 允许舍入 | 浮点转整数仅在编译期值有限且截断后在目标范围内时允许；动态值在 0.0.1 拒绝，后续再设计运行期检查 |
| 数值/数据指针 → bool；bool → 整数 | 须 `to_type`；转 bool 为是否非零，bool 转整数为 0/1 | 不允许 bool 参与普通算术或转换为指针；浮点 NaN 转 bool 为 true |
| `*T` → `*void` | 隐式允许；`*void` → `*T` 和不同数据指针间转换须 `to_type` | `malloc` 返回值可显式转为目标指针；`to_type` 不验证对象类型、大小、对齐或存活期 |
| 数据指针 ↔ 整数、数据指针 ↔ 函数指针 | 除整数**字面量** `0` → 空数据指针外均拒绝 | 不把整数位模式默认为可用地址；函数指针只接受同型使用 |
| `[N]T` → `[]T` | 须 `to_type` 且源是可取地址的数组左值，生成 `{len:N, data:&array[0]}` 视图；若允许 N=0，则 data=null；元素类型须同型 | 不复制元素；切片不能比原数组活得更久，0.0.1 不做静态生命周期证明 |
| `[]T` → `*T` | 须 `to_type`，取 `data`；会丢失长度 | 空切片的 data 为 null；不得把该转换交给 `gen_cast` |
| `*T` → `[]T`、不同元素类型的切片互转、切片 → 数组 | 拒绝 | 裸指针缺少长度；切片不拥有定长数组值；如需从指针和长度构造切片，另设计显式双参数入口 |
| 结构体/联合体/数组/函数类型/void | 仅允许非 void 值的同型复制及上列数组视图；其余 `to_type` 拒绝 | 不以布局相同作为可转换依据；枚举只允许显式转为 i32，反向转换暂拒绝 |

后缀链中每次 `to_type` 按从左到右单独检查，结果必须清除左值标记；
`x.to_type(int) = y` 即使类型未变也要报错。声明初始化、赋值、调用和返回先执行
yh 的转换判定，再调用 `gen_assign_cast`/`gen_cast`；TCC 对不兼容指针、
丢弃 const、写只读位置等情况只有警告，不能作为 yh 的拒绝机制。
数组转切片须在 TCC 的数组退化为指针之前取得 N 并生成视图，否则长度丢失。
指针重解释后解引用仍可能产生未定义行为，这属于上述低层指针边界；
若目标改为保证内存安全，需另设只读指针和显式不安全操作，不能只收紧 `to_type`。
字符串字面量目前是 `*char`，也无法静态表达只读目标；实现时必须明确其
存储区的可写性，不能仅靠 `const` 绑定或 TCC 的可选警告宣称它不可写。

现有 `tests/yh/08-expr/06_cast.yh` 是**纯语法正例**：其中 `p.to_type([]u8)`
必须在编译模式拒绝，`p.to_type(*Header)` 仅按显式未检查指针转换接受。
M3 增加 `.yh` 语义正反例：同型强转不可赋值、字面量越界、无损提升、
有损数值转换、非法浮点转整数、指针/函数指针隔离；M4 增加数组转切片、
切片取数据指针、裸指针转切片拒绝及局部数组切片逃逸的边界说明。

## 5. 编码前写死的降糖与边界（伪代码级）

**for-in**（`for i, v in X { body }`，`0..n` 同构）：

```
先求值 X 一次；若是 `a..b`，分别求值 a、b 一次并保存
数组/切片：for (k = 0; k < n; k++) {
    单目标 v = p[k]；双目标 i = k, v = p[k]；执行 body
}
区间：for (cur = a, k = 0; cur < b; cur++, k++) {
    单目标 i = cur；双目标 i = k, v = cur；执行 body
}
```

区间为空时执行零次；不用 `b - a` 作循环长度，避免差值溢出。
须规定并测试端点类型、整型提升、`continue` 后递增、`break` 和嵌套循环。

**类型化变参 `fn sum(nums ... int)`**：调用点按源码顺序求值并类型检查所有
变参，在本次调用结束前仍有效的临时连续数组中存放，传入规范化的 `[]int`。
零个变参传 `len=0, data=null`；函数体内 `nums` 即切片。固定参数与变参的
求值顺序也须固定并测试。`printf(fmt *char, ...)` 只在内置 prelude 中允许，
走裸 C 变参路径。

**switch**：case 表达式必须是可转换为判别类型的编译期常量；
`case v1, v2 { B }` 展开为两条跳转到同一块 B 的条目。检查重复 case 值与
重复 default；每块尾跳到 switch 末尾，无 fallthrough。

**prelude**：`yh.g4` 的 fnDecl 必须带函数体，用户源码明确拒绝函数原型；
`tcc_compile_string()` 还会在编译单元结束时清理符号栈。因此按当前编译单元
直接创建 extern 函数 Sym，不构造非法的 yh 文本，也不改动已冻结语法。

## 6. 详细执行计划与验证门

### 6.1 执行规则与阶段依赖

当前基线是 TCC 编译器：`make` 产出 `tcc`，`make test` 在 Darwin 只运行
预处理测试；`docs/yh.g4` 的 ANTLR 语料目前为 65 个正例、29 个反例，
规则标注覆盖 68/68。**这些是起点，不是 yh 编译器已通过的验收结果。**
后续每增加 `.yh` 语料，总数随之增长；验收以脚本发现的全部文件通过为准，
不把 94 写成永久目标。

依赖顺序为 M0 → M1 → M2 → M3 → M4 → M5 → M6；同阶段原则上按任务
编号推进，其中 M0-03 依赖 M0-02 的 Linux 工具链，M0-04 汇总前两项
探针结果，M2-04 在语法各部分接通后执行。M0 只做基线核查、
`tmp/` 中的探针和设计文档决策，不改写 parser；任一前置验证失败，先修订方案或
ADR，再推进下阶段。每个实现任务按同一循环执行：先新增 `tests/` 下的
`.yh` 正例或反例并确认目标行为尚未通过 → 做最小代码修改 → 执行 `make`
和该用例 → 执行当时可用的阶段回归 → 记录结果。一个任务形成一个可审阅
改动，临时源文件、日志和探针只放 `tmp/`。

语法语料与可运行程序分开：`tests/yh/` 只要求词法/语法正确或按预期拒绝；
M3 起建立 `tests/yh-run/{pass,fail,run}/` 及 `tests/yh-run/check.py`，分别
验证编译通过、编译报错和运行结果。`--syntax-check` 必须容许语法合法但
语义错误的正例。Darwin 负责宿主构建和语法回归；Linux AArch64 承担 ELF、
libc、`-run` 和按值 ABI 验收。Darwin 跳过运行测试时必须明确报告跳过，
不能把跳过记作通过。

| 阶段 | 内容 | 验证门 |
| --- | --- | --- |
| M0 前置验证 | 工具链、数组/切片 ABI 探针、未定语义决策 | ADR-0001 的边界可实现；Linux 工具链可完成 ELF 链接；决策写入设计文档 |
| M1 驱动与词法 | `.yh` 输入、独立 C 运行时构建、yh 词法、纯语法入口骨架 | `make` 产出 yh 与运行时库；词法正反例及入口冒烟通过 |
| M2 纯语法 | 同一递归下降 parser 完成类型、表达式、声明、语句；增加编译器模式测试 | 编译器接受全部语法正例、拒绝全部语法反例；ANTLR 基线保持 |
| M3 基本语义 | 名称/类型/常量/可见性、标量表达式、控制流、prelude、`-o`/`-run` | Linux 上独立程序和错误用例通过，ELF 符号表与入口正确 |
| M4 聚合语义 | 内部数组 ABI、切片、for-in、类型化及裸变参 | ADR-0001 的矩阵与聚合/变参运行用例全过 |
| M5 集成 | `make test` 接入 yh 回归、安装与用户文档 | Linux 干净构建和完整测试通过；Darwin 跳过项单独列出 |
| M6 清理 | 只移除已证实无调用的 C 解析代码 | 清理前后 yh 回归一致，构建零警告 |

### 6.2 M0：先验证约束，再选实现

**M0-01 基线与依赖图**。核对 `Makefile`、`src/core/{tcc.c,libtcc.c,tccgen.c,tccpp.c,tccelf.c}`
和 `src/targets/arm64-gen.c` 的构建、调用与链接入口。在 `tmp/m0/` 保存
`make`、当前平台 `make test`、`python3 tests/yh/check.py --coverage`
的结果和关键调用关系；目前的 94 个语料只证明参考语法，不证明 yh 可编译。
若使用 graphify，输出限定在 `tmp/graphify-out/`，不把工具产物混入源码。

**M0-02 Linux 工具链和链接闭环**。在 AArch64 Linux 环境确认宿主 C 编译器、
归档器、libc/sysroot、`crt1.o`、`crti.o` 和动态加载器；在 Darwin 开发时
如需跨系统 `-o`，必须另给 Linux sysroot 和库路径，缺失则给明确错误。
用 `tmp/m0/` 的现有 TCC/C 探针验证 `src/core/tcc.h` 的
`CONFIG_SYSROOT`、`CONFIG_TCC_CRTPREFIX`、`CONFIG_TCC_LIBPATHS`、
`CONFIG_TCC_ELFINTERP` 与 `src/core/libtcc.c` 的链接路径。独立目标 C
工具链编译 `lib/lib-arm64.c`，检查归档成员为 AArch64 Linux ELF，
并解决 `__arm64_clear_cache` 等最终链接符号；后续 M1 才修改 Makefile。
验收命令至少包括 `make`、`readelf -h`、`readelf -l` 和一次 Linux 运行。

**M0-03 数组/切片 ABI 比较**。按 ADR-0001 在 `tmp/abi/` 写两个最小探针：
包装结构体、调用点拷贝后传隐式指针。逐项记录 `[1]int`、`[4]int`、
`[2]f64`、`[4]f32`、多个数组参数、寄存器耗尽、返回局部数组、大数组
的实测结果；同时测规范化的 16 字节切片参数和返回。重点核查
`arm64_pcs_aux()` 把 `VT_ARRAY` 按指针分类、HFA 路径，以及
`gfunc_call()` 的 `stack < 0x1000` 断言。以正确性和改动范围选实现，
结果写入新 ADR；未通过时不进入数组代码生成。

**M0-04 语义边界清单**。在 `docs/03-design/` 写下实现前必须确定的规则：
后定义函数是先扫描顶层签名还是要求定义先于使用；`main` 的参数、返回
和 `pub` 绑定；`pub type/struct/enum/const` 在无 import 语言中的跨文件
含义；字符串字面量是否可写；零长度数组、切片越界与局部数组切片逃逸；
裸 C 变参的窄整数提升。推荐先扫描顶层签名，入口与 `tcc_run()` 的
`int main(int,char**)` 调用约定一致；这些推荐必须由用例和实现约束确认，
不能写成已经完成的行为。同步修正 `docs/yh.g4` 的 prelude 注释：当前
注释仍说经 `tcc_compile_string()` 注入且只列 6 个函数，方案采用当前
编译单元直接登记 8 个 extern Sym。已确定的规则直接引用
`CONTEXT.md`：类型化变参只能在末尾出现一次，for-in 绑定为局部值拷贝。
修改 `docs/yh.g4` 后运行 `python3 tests/yh/check.py --coverage`。

**M0 出口**：Linux 工具链与探针可复现；ADR-0001 的语义边界未被实现方案
破坏；数组机制、新增决策和未解决阻塞项均有明确记录。M0 未通过时只修订
设计，不用猜测填补 parser 细节。

### 6.3 M1：驱动、构建与词法

**M1-01 构建与 `.yh` 输入**。修改 `Makefile`、`src/core/tcc.c`、
`src/core/libtcc.c`：产物改为 yh；用户源文件只识别 `.yh`；
`libtcc1.a` 改由 M0 验证过的目标 C 工具链生成，并把
`lib/lib-arm64.c` 加入归档目标的依赖。先加 `.yh` 驱动用例，
验证 `.yh` 进入 yh 路径、`.c` 不被当作 yh 源码、缺失目标工具链时
诊断明确，再执行 `make`。此步不宣称完整 yh 程序已可编译。

**M1-02 yh 词法**。修改 `src/core/{tcctok.h,tccpp.c,tcc.h}`：保留
`to_type` 和旧 `as` 的拒绝策略、补 RANGE、维持 ELLIPSIS、收敛数字
下划线与转义、拒绝 `#`/`##`，并审计 token 编号与成员位置关键字。
每类词法改动用 `tests/yh/11-lex/` 或 `tests/yh/rejected/` 的 `.yh`
文件复现；`0..n`、`...`、`.5`、`1__0`、`\\q`、CR-only 均须检查。
保留宿主构建工具在清理前需要的 C 预处理路径。

**M1-03 纯语法入口骨架**。在 `src/core/tcc.c` 和新 yh parser 入口
接通 `yh --syntax-check file.yh`：只报告词法/语法错误并消费到 EOF；
此模式不解析符号、不调用 `gen_*`、不要求 `main`。先用最小 `.yh`
文件和一个词法错误文件做红绿验证，完整语法语料留给 M2。

**M1 出口**：`make` 可重复产出目标文件；当前词法正例通过、词法反例被拒；
ANTLR 原模式全部通过；语法入口不会误把语义错误当词法错误。

### 6.4 M2：递归下降语法与双模式解析

**M2-01 类型与声明**。创建 `src/core/yh_type.c`、`yh_decl.c`；
按 `docs/yh.g4` 实现 typeRef、数组长度形态、type 别名、顶层/局部
let/const、函数、struct/union/enum、pub 的语法。先用相应
`tests/yh/01-toplevel/`、`03-decl/`、`09-types/` 用例验证；
纯语法模式不检查名字、常量值或数组长度是否合法。

**M2-02 表达式与后缀转换**。创建 `src/core/yh_expr.c`，逐层实现
优先级、调用/下标/成员、`x.to_type(T)`、structInit、`sizeof(T)`、
`len(e)`。`.to_type(T)` 的括号内必须走 typeRef，不能按函数实参
表达式解析；旧 `x as T` 必须语法拒绝，`to_type` 不作普通成员名。
用 `tests/yh/08-expr/`、`rejected/28_legacy_as.yh` 和
`rejected/29_reserved_to_type.yh` 验证链式转换、后缀优先级与拒绝规则。

**M2-03 语句与歧义边界**。创建 `src/core/yh_stmt.c`：实现 `;`、
if/for/switch、单目标赋值、包裹式标签、goto 和块；按语法文档处理
for/switch 头部 `IDENT {` 的字面量与块边界。以
`tests/yh/04-stmt/`、`05-branch/`、`06-loop/`、`07-assign/` 的
`.yh` 正反例验证；语法模式仍容许 `f() = 1` 等语义错误。

**M2-04 编译器模式语料入口**。扩展 `tests/yh/check.py` 的
`--compiler` 模式调用 `yh --syntax-check`，保留默认 ANTLR 模式。
两种模式都遍历所有发现的正反例；前者不能因为未定义符号、错误类型或
缺少 main 拒绝语法正例。

**M2 出口**：两种模式全部通过、消费到 EOF，并报告实际用例数；
不以起始语料数量代替后续回归。

### 6.5 M3：基本语义、代码生成与程序闭环

**M3-01 名称、声明与内置符号**。在 `yh_decl.c`、`yh_type.c`、
`src/core/tccelf.c` 实现作用域、同名检查、const 编译期值与可重定位
地址的区别、顶层 pub 的 ELF 绑定和 M0 决定的前向函数规则；
`src/core/yh_builtin.c` 直接向当前编译单元登记 8 个 prelude extern
函数 Sym，不编译伪造的 yh 原型文本。先在 `tests/yh-run/{pass,fail}/`
增加名字、const、pub、非法原型、前向调用正反例，检查非 pub 与 pub
的 `readelf -sW` 绑定及入口 `main` 的可查找性。

**M3-02 类型与表达式**。在 `yh_expr.c` 和最小必要的后端桥接代码中
先按 §4.1 验证隐式/显式转换，再调用 `gen_cast`、`gen_op` 或
`gen_assign_cast`。覆盖窄整数、i/u 边界、浮点常量、bool、不同指针、
空指针和 `x.to_type(int) = y`；不把 TCC 的警告当作 yh 的拒绝。
条件、比较、复合赋值、返回和形参都走同一规则。`tests/yh-run/fail/`
须能观察到失败诊断，`pass/` 或 `run/` 验证正确转换结果。

**M3-03 语句、初始化与输出**。在 `yh_stmt.c`、`yh_expr.c`、
`src/core/{tcc.c,libtcc.c,tccrun.c}` 完成变量落地、structInit、
函数体、分支循环、switch 去 fallthrough、goto/label、return，
接通 `-o` 与 `-run`。switch 的 case 必须是可转换的编译期常量，
重复值与重复 default 报错；给调用/比较结果赋值报错。
`tests/yh-run/run/hello.yh` 在 Linux 分别经 `yh hello.yh -o ...`
和 `yh -run hello.yh` 得到相同结果；`readelf -h/-l/-sW` 验证 ELF
机器类型、动态加载器与 pub/非 pub 符号。Darwin 只验收构建和语法，
不以宿主 libc 的 `-run` 结果代替 Linux 验收。

**M3 出口**：独立标量程序可编译、运行；非法语义在编译模式报错；
`--syntax-check` 仍接受语法合法的语义错误文件。M4 的数组/切片
语法可已解析，但其尚未实现的合法语义不能被误报为完成。

### 6.6 M4：数组、切片、遍历与变参

**M4-01 数组按值调用**。依 M0 的实现 ADR 修改 `yh_type.c`、
`yh_decl.c`、必要时 `src/targets/arm64-gen.c`；不得直接把 TCC 的
`VT_ARRAY` 传参路径当成按值。`tests/yh-run/run/` 的 `.yh` 用例逐项
覆盖 ADR-0001 的拷贝独立性、数组返回、嵌套/递归、多参数、浮点 HFA、
寄存器耗尽和大数组；不同长度实参放入 `fail/`。若后端 4096 字节
栈断言仍可触发，先修实现或给出已确定且可诊断的语言限制，不能以
assert 崩溃交付。

**M4-02 切片与 for-in**。在 `src/core/yh_slice.c` 落地按元素类型
规范化的 `[]T`，验证跨函数参数/返回仍是同一类型；`len` 和下标
只求值一次。`[N]T.to_type([]T)` 建视图，裸指针转切片编译拒绝。
for-in 的绑定仅在循环体内可见，每次迭代复制元素值；修改绑定不改变
容器。`tests/yh-run/{run,fail}/` 覆盖数组/切片/区间、空范围、
`continue`/`break`、嵌套循环、别名和切片生命周期已声明的边界。

**M4-03 变参与 prelude 调用**。类型化变参只能在参数表末尾出现一次；
调用点按源码顺序求值并打包为临时 `[]T`，零参数为
`{len:0,data:null}`，函数体内按切片使用。裸 `...` 只允许编译器
内置的 C prelude 函数；在 Linux 验证 `printf` 的 `i8/u8/bool`
默认整型提升、`f32` 到 `f64`、指针，以及 0/多个参数。验证临时数组
活到调用结束，寄存器耗尽时参数布局仍正确；用户自写裸变参声明须报错。

**M4 出口**：ADR-0001 的每一行都有 `.yh` 运行或拒绝用例；切片参数
和返回、数组值拷贝、for-in 和两种变参路径在 AArch64 Linux 全部通过。

### 6.7 M5：测试门与交付文档

**M5-01 测试集成**。建立 `tests/yh-run/check.py`，使编译通过、
编译拒绝、运行结果分别计数；`Makefile` 的 `make test` 在所有宿主
运行 ANTLR 与 yh 编译器语法回归，并在 AArch64 Linux 运行语义/ABI
回归。Darwin 的运行项显示 SKIP 及原因，不得汇总为全部通过。
保留旧 C/pp 回归的最后验证记录，不将旧 C 用例误当作 yh 用例。

**M5-02 安装与说明**。检查 `Makefile` 的 build/install/uninstall、
`VERSION`、用户 README 和 `docs/03-design/`；从干净目录执行
`make clean && make && make test`，确认产物只有计划中的 yh 与库、
所有用户源文件为 `.yh`。在 Linux 再执行 hello 的 `-o`、`-run`，
保存 `readelf` 和运行结果；缺 sysroot 的 Darwin 链接请求给出可读错误。

**M5 出口**：干净构建与完整测试在 Linux 通过；Darwin 的 SKIP 项明确
列出且不计为通过，安装产物和使用文档与实际命令一致。

### 6.8 M6：有证据地清理

**M6-01 移除 C parser**。依据实际调用关系，清理 `src/core/tccgen.c`
及相邻文件中确认无调用的 C 语法解析函数与本次产生的孤立声明；
不因估算的删行数而删除仍在使用的值栈、类型、ELF 或后端机制。
清理前后分别运行 `make && make test` 和 Linux 运行矩阵，比较结果；
用 `GRAPHIFY_OUT=tmp/graphify-out graphify update .` 与
`graphify god-nodes` 辅助检查。最后在 `docs/finish.md` 记录实际完成
事项、命令与未解决边界。

**M6 出口**：清理前后测试结果一致，新代码无无效声明或未引用解析入口；
未达标的清理项保留为待办，不因删行目标强行移除。

### 6.9 估算与测试口径

M0 完成后再估算总工期。原方案的 **3~4 周** 未计入工具链、数组 ABI 和
纯语法模式的工作量，不能作为承诺。代码任务每次修改后执行构建与对应
`.yh` 用例；阶段结束执行当时可用的完整测试门。M0-02 的链接验证必须
覆盖 `lib/lib-arm64.c` 使用的 `__arm64_clear_cache` 等符号，不能只检查
归档文件生成成功。

`tests/yh/check.py --coverage` 目前只统计语料首行标注的规则名；其中
`commentStmt`、`removedKeyword` 本来就无法被正例实际走到。因此 68/68 只能
称为**语料标注覆盖**，不能作为 yh parser 的执行覆盖率。

Linux 真机或 AArch64 Linux 虚拟机是运行验收环境；仅有 qemu-user 仍须同时具备
对应 libc、crt 和动态加载器。Darwin 上 `-run` 的可变参数 libc 调用不作验收门。
旧 `make test` 中的 C/pp 套件在词法与 parser 切换后不再能直接作为 yh 回归。

## 7. 风险与对策

1. **语法检查与代码生成纠缠**：同一解析函数需有纯语法路径，不能在
   `--syntax-check` 中提前查符号、调用 gen_* 或要求 main；用语法合法而语义
   错误的正例专门验证。编译模式仍边解析边生成，不建 AST。
2. **数组值语义未被现有 ABI 覆盖**：`arm64_pcs_aux()` 把 VT_ARRAY 当指针大小
   处理；`[4]int` 参数不能靠“已有聚合路径”保证按值。M0 比较包装结构体与
   调用点拷贝后传指针两种降糖，记录参数、返回和大数组场景的 ABI，再动 parser。
3. **切片类型身份与生命周期**：同一 `[]T` 在参数、返回值、别名、不同函数中
   必须相容；按元素类型规范化，登记表在编译单元结束时释放。
4. **无原型与单遍的前向引用**：当前路线不能无声明地调用后定义函数。
   M0 明确选择“定义先于使用”或“先扫描顶层函数签名再单遍编译函数体”，
   并把选择写入语义设计文档；不得退回 C 的隐式 int 函数声明。
5. **构建自举**：最终 yh 不解析 C，旧规则 `$(TCC) -c lib/lib-arm64.c` 必然失效。
   `libtcc1.a` 改由独立 AArch64 Linux C 工具链生成；`libtcc.a` 仍由宿主 C
   编译器构建，两者的目标平台不可混淆。
6. **诊断可读性**：TCC 的 error() 自带 file:line，v0.0.1 不做错误恢复打磨，
   但 `while` 等保留字应给出「已移除，请改用 for」的定向提示。
7. **缺失的语义设计文档**：ABI、数组/切片/const/前向引用决定先在本方案
   记录；实现前写入 `docs/03-design/`，不要等发版才补。

## 8. 交付清单（Definition of Done）

- [ ] 干净构建的 `make` 产出 `yh`、`libtcc.a`、`libtcc1.a`，零警告；C 运行时构建不调用 yh 编译 C
- [ ] `yh --syntax-check` 的编译器模式与 ANTLR 原模式都通过验收时实际发现的全部正反语料；当前起点为 65 个正例、29 个反例，语料标注覆盖率单独报告
- [ ] Linux 上 `tests/yh-run` 的语义与 ABI 矩阵全绿，含数组/切片参数和返回、变参、区间边界
- [ ] prelude 八函数作为 extern 符号可用，hello.yh 的 `-o` 与 `-run` 闭环
- [ ] `make test` 已切换为 yh 测试，旧 C 测试不被误报为 yh 的通过记录
- [ ] 删除确认为死代码的 C parser，保持新文件尽量 500~1000 行；既有 tccgen.c 的进一步拆分另列任务
- [ ] ABI 与语义决定写入 `docs/03-design/`，docs/finish.md 记录，README 更新为 yh 编译器说明
