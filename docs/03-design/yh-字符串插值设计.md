# yh 字符串插值设计（V 风格）

修改时间：2026-11-06

状态：**I0–I4 已实施（2026-10-24）；I5 可选扩展未做**。
用户决定：字符串格式化采用 V 语言式的字符串插值；插值表达式的结果类型为
`string.String`。本文只定义插值语言特性；`fmt` 运行时见
[fmt 标准库设计](yh-fmt标准库设计.md)，分期见
[实施方案](../02-plan/yh-fmt标准库实施方案-2026-10-23.md)。

V 参考：`${expr}` 与 `${expr:[flags][width][.precision][type]}`、编译期解析
格式串，见 [V 文档 String interpolation](https://github.com/vlang/v/blob/master/doc/docs.md#string-interpolation)。
本文只对齐该子集，不搬入 V 的 GC、反射或 `str()` 方法体系。

## 1. 语法

```yh
let name *char = "Bob"
let age int = 20

let a string.String = "Hello, ${name}!"          // Hello, Bob!
let b string.String = "age = ${age}"             // age = 20
let c string.String = "next = ${age + 1}"        // next = 21
let d string.String = "hex = ${age:04x}"          // hex = 0014
let e string.String = "pi = ${3.14159:.2}"       // pi = 3.14
```

规则：

- 只有双引号字符串参与插值；普通字符串的语义与现在完全相同。
- `"${"` 开始一个插值，`"}"` 结束；中间必须是表达式，空表达式是错误。
- `$` 后不是 `{` 时是普通字符；`\$` 是字面 `$`，因此 `"\${x}"` 输出
  `${x}`。`\$` 加入现有转义集合（`lex_escape`），未知转义仍然报错。
- 字面文本部分可以为空；`"${x}"`、`"a${x}b${y}c"` 合法。
- 首版不允许跨行：与现有字符串规则一致，`${...}` 内出现裸换行报错。
- 首版不允许嵌套插值字符串（`"${f("${x}")}"` 报错）。
- 首版 `${}` 内不允许**裸双引号**（双引号字符串字面量与 `'"'` 字符字面量
  都不允许）；需要字符串实参时先用变量。这样外层 `STRING` 仍是单个 token，
  `docs/yh.g4` 的参考语法可以继续精确匹配整个字面量。`${}` 外的 `\"`
  文本转义不受此限制。
- 表达式中出现顶层 `:` 视为格式说明符分隔符；三元表达式必须加括号
  （`"${(a ? b : c):d}"`），否则 `:` 会被当作 spec 起点。结构体字面量里的
  `:` 在 `{}` 内，不算顶层。

## 2. 格式说明符（V 子集）

```text
${expr:[flags][width][.precision][type]}
```

| 部分 | 允许值 | 语义 |
| --- | --- | --- |
| flags | `-`、`0`、`+` 任意顺序、可重复 | `-` 左对齐；`0` 用 0 补齐；`+` 对非负有符号数值显示 `+`；`-` 优先于 `0` |
| width | 十进制整数 | 最小字段宽度，默认空格补齐；首版不支持 `(expr)` 运行时宽度 |
| precision | `.` + 十进制整数 | 浮点小数位数；首版不支持 `.(expr)`；整数忽略 |
| type | `d x X o b f F e E g G s` | 见下表；省略时按静态类型取默认 |

- 不支持 V 之外的 `#`、空格 flag、`'` 分组和 `r/R` 重复；出现即编译错误。
- 首版 width/precision 只接受字面量数字；上限 1,048,576，超限编译错误。
- 类型默认：整数 `d`、浮点 `g`、字符串 `s`、bool 为 `true`/`false` 文本。
- 显式 type 必须与静态类型匹配，否则编译错误。
- 大写类型（`X`、`E`、`G`）强制大写十六进制/指数；`F` 等价 `f` 的大写形式。
- 浮点 precision 的 V 语义：`.2` 四舍五入到两位并去掉无意义尾零，
  `.2f` 保留两位尾零；`10.0000:.2` → `10`，`:.2f` → `10.00`。
- 科学计数法指数至少两位（`1.5e+02`），不额外补前导零。
- 宽度按字符/rune 计；首版字符串按 UTF-8 标量计，非法字节每个计 1。
- bool 只允许 width 与 `-`；其他 flag/type 是编译错误。

示例（期望输出作为测试 golden）：

```text
"${123}"        -> 123
"${123:05d}"    -> 00123
"${123:-6d}"    -> "123   "
"${123:+05d}"   -> +0123
"${255:x}"      -> ff
"${255:X}"      -> FF
"${8:b}"        -> 1000
"${64:o}"       -> 100
"${3.14159:.2}" -> 3.14
"${10.0000:.2}" -> 10
"${10.0000:.2f}"-> 10.00
"${1.5:e}"      -> 指数格式；默认精度与尾零以 V 1.x 实测锁定 golden
```

## 3. 类型与求值

首版支持的表达式静态类型：

| 类型 | 默认渲染 | 可用 type |
| --- | --- | --- |
| 有符号整数（int/i8/i16/i32/i64） | 十进制 | `d x X o b` |
| 无符号整数（u8/u16/u32/u64） | 十进制 | `d x X o b` |
| f64 / f32 | V 默认 `g`（f32 先转 f64） | `f F e E g G` |
| bool | `true`/`false` | 仅 width/`-` |
| `*char`（NUL 结尾） | 字节文本 | `s` |
| `string.View` | 字节文本 | `s` |
| `string.String` | 暂不支持（后续用 `as_view`） | — |
| enum | 按有符号整数 | `d x X o b` |
| struct/array/slice/union/函数指针 | 编译错误 | — |

- 每个表达式恰好求值一次，从左到右；文本部分不求值。
- 插值是运行期表达式：不能用于顶层 `const`/全局初始化或 `@[comptime]`
  函数体（首版明确报错），避免把格式化运行时带进编译期执行器。
- 表达式结果是 `string.String`，调用方用 `string.release` 释放。
- 内存不足时返回零句柄（空串），不抛错、不终止；该失败不可观察
  （用户已确认此语义）。文档必须写明；后续若需要可观察失败，另加带
  `TextResult` 的显式 API。
- 插值结果为空时仍是合法零句柄；`"${""}"` 与 `""` 都是零长度。
- `*char` 为 NULL 时按空串处理（不崩溃），与 `fmt.of_cstr` 一致。
- 编译期检查 spec 的语法与类型匹配；运行期 fmt 仍会再解析一次 spec
  （防越界/防御性），两处由同一张表驱动测试。

## 4. 词法与语法实现

### 4.1 词法

普通字符串仍是单个 `TOK_STRING`。插值字符串在**词法后扩展**阶段被重写为
源顺序的内部 token 序列（不修改 `docs/yh.g4` 的用户可见语法）：

```text
TOK_INTERP_BEGIN
TOK_RAW_TEXT       // 字面文本（可为空；不含引号）
TOK_INTERP_EXPR_BEGIN
<expr tokens>
TOK_INTERP_EXPR_END
TOK_RAW_SPEC       // 可选，spec 原文
TOK_RAW_TEXT
...
TOK_INTERP_END     // 闭引号
```

- 新 token kind 只由扩展器产生，用户无法在源码中写出；parser 只在插值
  位置接受它们。
- `TOK_RAW_TEXT`/`TOK_RAW_SPEC` 保存源字节区间，语义阶段复用现有转义解码
  （spec 不需要转义，但仍走同一解码）。
- 扩展器扫描 `${...}` 时平衡 `()[]{}`、跳过字符串/字符字面量与注释；
  顶层 `:` 切出 spec。跨行、空表达式、未闭合、嵌套插值分别报错。
- 扩展后 token 仍在源顺序，AST 的 token 区间、快照与缓存不出现“游离
  token”；`lex_layout` 需要识别插值边界，禁止在 `${...}` 内插入分号。
- 现有 token 预算/位置记录沿用；错误位置指向原始字符串内的字节。

### 4.2 参考语法（docs/yh.g4）

`docs/yh.g4` 保持 `STRING` 为单个 token；插值是该 token 内部的编译期
细化，不新增 ANTLR 规则。ANTLR 只能验证外层字符串，不能验证
`${...}` 内部表达式；编译器语法测试（`--syntax-check` 与
`tests/yh/` 的编译器模式）承担这部分。

这是有意的参考语法边界：ANTLR lexer mode 不能平衡任意 `{}`，硬塞会产生
歧义或与编译器不一致的近似。若后续要求 ANTLR 也精确覆盖，需单独立项
重新设计参考语法，而不是在现有规则里加不精确的模式。

### 4.3 解析与降级（实际实现）

- `TOK_INTERP_BEGIN` 在 primary 位置进入 `parse_interp`。
- 文本块/说明符用 `sem_raw_string` 登记为 `quoted=2` 的字符串体；值 part 由
  `parse_expr` 正常解析，类型已在 `Res.type_id` 中求得。
- parser 直接合成对 fmt 的普通 AST 调用树，不新增 AST kind：
  - 文本叶：`fmt.text(*char)`；
  - 值叶：按静态类型调用 `fmt.of_i64/of_u64/of_f64/of_bool/of_cstr`，再
    `fmt.value(Value)` 或 `fmt.value_spec(Value, *char)`；
  - 折叠：`fmt.concat(String, String)` 二元消费式拼接。
- spec 在 parser 内做编译期语法与类型校验（与 fmt 运行期解析共用测试表）；
  非法 spec 在源码位置报错。
- 结果类型由 fmt 接口给出 `string.String`；调用树进入既有 AST/快照/SSA
  路径，不需要新的 lowering 分支。

## 5. 检查、快照与边界（实际实现）

- 插值不需要新 AST kind；合成调用使用插值字面量的 token 区间，子表达式
  AST 仍在同一区间内，快照/缓存与普通调用一致。
- 首版要求 `import fmt`（默认绑定名，`as` 别名未接通）与 `import string`
  （结果类型/释放）；缺 fmt 报“字符串插值需要 import fmt”，缺 string 由
  普通类型解析报错。
- 支持的值类型：有符号/无符号整数、f64/f32、bool、`*char`、
  `string.View`；enum 按有符号整数；`string.String`、结构体/数组/切片/
  联合体报“该类型不支持字符串插值”。
- spec 编译期校验 flags/width/precision/type 与类型匹配；运行期
  `fmt.value_spec` 仍会校验（防御）。
- 文本块经 `fmt.text` 以 NUL 结尾读取，**块内 NUL 暂不支持**；说明符同样
  不含 NUL。
- 首版限制：单行；`${}` 内不允许裸双引号（外层字符串会先按普通规则终止）、
  花括号与顶层三元 `?:`（三元需加括号）；不允许嵌套插值；`fmt` 不支持
  `as` 别名。跨行/嵌套/别名后续 I5 再评估。

## 6. fmt 运行时契约

编译器降级依赖以下公开 API（名字与签名是编译器契约，改动需同步编译器）：

```yh
pub fn of_int(value int) Value
pub fn of_i64(value i64) Value
pub fn of_u64(value u64) Value
pub fn of_f64(value f64) Value
pub fn of_bool(value bool) Value
pub fn of_str(text string.View) Value
pub fn of_cstr(text *char) Value
pub fn append_text(target *string.String, text string.View) Status
pub fn append_value(target *string.String, value Value, spec string.View) Status
```

- `append_*` 返回 `fmt.Status`；`status_ok` 成功，其余为失败。失败时目标
  `String` 的状态按 `string.append` 契约保留（可能已有前缀）。
- fmt 内部把 `string.Status` 映射为 `fmt.Status`；插值降级只需区分
  成功/失败。
- 若 I0 选择 `fmt.interp(parts ... Part)`，则 Part 的构造器也进入契约，
  并需验证类型化变参在 O0/O2 的 ABI。

## 7. 生命周期与打印

- 插值结果必须显式释放：
  ```yh
  let text string.String = "x=${x}"
  // 使用
  string.release(&text)
  ```
- 打印插值结果：`fmt.of_string(&text)` 后交给 `fmt.print/println`，
  或 `string.as_view` 后交给接受 `string.View` 的接口；首版不引入临时
  自动释放。`io.println` 只接受 `*char`，需要 `string.c_str`（内嵌 NUL
  会被拒绝），不作为推荐路径。
- 插值表达式的零句柄与“分配失败”不可区分；这是用户确认的取舍。

## 8. 错误与限制

| 情况 | 诊断 |
| --- | --- |
| `"${}"` | 空插值表达式 |
| 未闭合 `${` 或 `}` | 插值未终结 |
| 插值内换行 | 插值内不允许换行（首版） |
| 嵌套插值字符串 | 首版不支持嵌套插值 |
| 顶层 `:` 歧义（三元） | 提示给三元表达式加括号 |
| spec 非法 | 非法格式说明符 + 位置 |
| spec 与类型不匹配 | 格式说明符与表达式类型不匹配 |
| 不支持的类型 | 该类型不支持字符串插值 |
| 缺 import | 字符串插值需要 import fmt/string |

首版明确不做：运行时 width/precision `(expr)`、`r/R` 重复、结构体/数组
反射打印、`Stringer`/`Formatter` 自定义、跨行插值、嵌套插值、自动释放。

## 9. 测试与验收

- 语法：`tests/yh/` 增加插值 pass/reject 用例；编译器 `--syntax-check`
  覆盖，ANTLR 层只验证外层字符串仍可解析。
- 运行：`tests/yh-run/run/` 增加插值求值、转义、spec、错误位置用例；
  `tests/modules/` 增加跨模块/缓存用例。
- fmt 运行时：`tests/fmt/` fixture 直接调用 `append_*` 与构造函数，
  再与插值端到端对照。
- O0/O2：插值 AST/降级用例在两种优化级别运行；自举固定点必须通过。
- 不引入 Go 类型名/反射；期望输出手写并锁定，浮点按 V 实测或 golden
  对照；不用 Go 生成插值 golden（Go 无此语法）。

## 10. 分期与待确认

分期见[实施方案](../02-plan/yh-fmt标准库实施方案-2026-10-23.md)的 I0–I4；
运行时 R0–R3 先落地，供 I3 降级使用。

待确认：

1. 插值是否必须 `import fmt`/`import string`（本设计默认必须，不自动导入）。
2. 首版限制（无嵌套插值、无运行时 width/precision、无 `r/R`）是否接受。
3. spec 的浮点细节以 V 1.x 实测为准；若 V 行为不可复现，是否允许 yh 自定
   并在文档标注。
4. 插值结果是否增加显式失败版本（`TextResult`）作为后续 API。
