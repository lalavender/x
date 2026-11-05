# fmt（R2）

yh 标准库的格式化运行时。设计见
[`docs/03-design/yh-fmt标准库设计.md`](../../docs/03-design/yh-fmt标准库设计.md)，
分期见
[`docs/02-plan/yh-fmt标准库实施方案-2026-10-23.md`](../../docs/02-plan/yh-fmt标准库实施方案-2026-10-23.md)。

当前是 **R3 + 插值叶 API**：Value/构造器、V 格式说明符、追加、
print/sprint/render，以及编译器降级用的 `text`/`value`/`value_spec`/
`concat`。语言层 `${}` 插值（I0–I5）尚未实现。

## 模型

```yh
pub enum Kind {
    kind_invalid     // 零值 Value，渲染为 <nil>
    kind_int         // i64 存储，有符号
    kind_uint        // u64 存储
    kind_f64         // R2 接通
    kind_bool
    kind_str         // 借用 string.View
}

pub struct Value { ... }  // 字段公开；布局不是接口，只用构造器
```

`Value` 浅拷贝；字符串借用源字节，调用期间源必须存活。`pub struct` 的
字段一律公开（语言规则），直接改写字段属于违约。

## API（R1）

| API | 契约 |
| --- | --- |
| `of_int(int)` / `of_i64(i64)` | 有符号 64 位 |
| `of_u64(u64)` | 无符号 64 位 |
| `of_f64(f64)` | 默认 g；支持 f/F/e/E/g/G |
| `of_bool(bool)` | true/false |
| `of_str(string.View)` | 借用字节文本 |
| `of_cstr(*char)` | NUL 结尾；NULL 视为空串 |
| 零值 `Value` | nil，渲染 `<nil>` |
| `kind_of(Value)` | 读取分类 |
| `append_text(*string.String, string.View) Status` | 追加文本 |
| `append_value(*string.String, Value, string.View) Status` | 按 spec 追加；空 spec 用默认 |
| `of_string(*string.String)` | 借用独占字符串的只读视图 |
| `render(Value, string.View) TextResult` | 按 spec 新建字符串 |
| `sprint([]Value)` / `sprintln([]Value)` | 拼接新建字符串 / 加换行 |
| `fprint(int, []Value)` / `fprintln(int, []Value)` | 写 fd / 加换行 |
| `print([]Value)` / `println([]Value)` | 写标准输出 / 加换行 |
| `text(*char) string.String` | 新建文本 String；NULL 为空 |
| `value(Value) string.String` | 默认格式新建 String |
| `value_spec(Value, *char) string.String` | 指定 spec 新建 String |
| `concat(String, String) String` | 消费两个输入并拼接 |

`Status`：`status_ok`、`status_out_of_memory`、`status_overflow`、
`status_invalid_spec`、`status_unsupported`、`status_other`。

## V 格式说明符（R1 子集）

```text
[flags][width][.precision][type]
```

| 部分 | R1 行为 |
| --- | --- |
| flags | `-` 左对齐、`0` 零补齐、`+` 非负显示正号；`-` 优先于 `0` |
| width | 十进制字面量，最小宽度；上限 1,048,576 |
| precision | 只对浮点有意义（R2）；整数忽略；字符串/bool 传 precision 为非法 |
| type | 整数 `d x X o b`；字符串 `s`；bool 仅默认；浮点 `f F e E g G` |
| 默认 | 整数 `d`、浮点 `g`、字符串 `s` |

整数按 ASCII 数字计宽；字符串按 UTF-8 标量计宽，非法字节每个计 1。
负整数先输出 `-`，再输出绝对值的指定进制。`0` 与 `+` 同时出现时零补齐
放在符号之后。

浮点：默认 `g`（6 位有效数字）；`.N` 视为小数位数并去掉无意义尾零，
`.Nf` 保留尾零；`e/E` 指数至少两位；NaN/±Inf/负零分别输出
`NaN`/`+Inf`/`-Inf`/`-0`。定点路径在 `scaled > 1e18` 或精度 > 17 时返回
`status_unsupported`（实现上限，不是语法错误）。

## 示例

```yh
import fmt
import string

let out string.String = string.make()
let prefix string.ViewResult = string.view_cstr("n=")
let spec string.ViewResult = string.view_cstr("+05d")
let text_status fmt.Status = fmt.append_text(&out, prefix.value)
let value_status fmt.Status = fmt.append_value(&out, fmt.of_int(7), spec.value)
// 两者都应为 status_ok；out 的内容为 "n=+0007"。
string.release(&out)
```

## 字符串插值（I0–I3）

```yh
import fmt
import string

let name *char = "Bob"
let count int = 7
let text string.String = "Hello, ${name}! n=${count} hex=${count:04x} f=${1.5:.2f}"
// 使用后释放。
string.release(&text)
```

- `${expr}` / `${expr:spec}` 由编译器降级为 `fmt.text`/`fmt.value`/
  `fmt.value_spec`/`fmt.concat` 调用；结果类型是 `string.String`。
- 支持整数、`f64`、`bool`、`*char` 表达式；enum 按有符号整数。
  `string.View` 按文本支持；`string.String`、结构体/数组/切片暂不支持。
- 首版限制：单行；`${}` 内不允许裸双引号、花括号与顶层三元（三元需加
  括号）；不允许嵌套插值；`import fmt` 不支持 `as` 别名；文本块内嵌 NUL
  暂不支持。
- `\$` 是字面 `$`；`\${` 输出 `${`。

## 测试

```bash
cd libs && ../yh test fmt --timeout 60
# 或
just test-lib-tests
```

R3 覆盖构造器、整数/浮点默认与 spec、字符串/bool 对齐、rune 宽度、
浮点符号/宽度/特殊值、非法 spec、实现上限、sprint/render/of_string、
fprint 错误路径与插值叶 API。语言层插值按 I0–I5 继续。
