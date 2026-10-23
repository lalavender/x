# fmt（R1）

yh 标准库的格式化运行时。设计见
[`docs/03-design/yh-fmt标准库设计-2026-10-23.md`](../../docs/03-design/yh-fmt标准库设计-2026-10-23.md)，
分期见
[`docs/02-plan/yh-fmt标准库实施方案-2026-10-23.md`](../../docs/02-plan/yh-fmt标准库实施方案-2026-10-23.md)。

当前是 **R1**：Value/构造器、V 格式说明符（整数/字符串/bool）与追加接口。
f64 的数值渲染（R2）尚未接通，返回 `status_unsupported`；print/sprint
（R3）与语言层 `${}` 插值（I0–I5）尚未实现。

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
| `of_f64(f64)` | 存储；数值渲染待 R2 |
| `of_bool(bool)` | true/false |
| `of_str(string.View)` | 借用字节文本 |
| `of_cstr(*char)` | NUL 结尾；NULL 视为空串 |
| 零值 `Value` | nil，渲染 `<nil>` |
| `kind_of(Value)` | 读取分类 |
| `append_text(*string.String, string.View) Status` | 追加文本 |
| `append_value(*string.String, Value, string.View) Status` | 按 spec 追加；空 spec 用默认 |

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
| type | 整数 `d x X o b`；字符串 `s`；bool 仅默认；浮点类型在 R2 |
| 默认 | 整数 `d`、浮点 `g`、字符串 `s` |

整数按 ASCII 数字计宽；字符串按 UTF-8 标量计宽，非法字节每个计 1。
负整数先输出 `-`，再输出绝对值的指定进制。`0` 与 `+` 同时出现时零补齐
放在符号之后。

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

## 测试

```bash
cd libs && ../yh test fmt --timeout 60
# 或
make test-lib-tests
```

R1 覆盖构造器、整数默认与 spec（宽度/符号/进制/i64 最小值）、字符串/bool
对齐、rune 宽度、非法 spec 与 f64 未接通路径。print/sprint、浮点与插值
降级按 R2–R3/I0–I5 继续。
