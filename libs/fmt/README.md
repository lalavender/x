# fmt（R0）

yh 标准库的格式化运行时。设计见
[`docs/03-design/yh-fmt标准库设计-2026-10-23.md`](../../docs/03-design/yh-fmt标准库设计-2026-10-23.md)，
分期见
[`docs/02-plan/yh-fmt标准库实施方案-2026-10-23.md`](../../docs/02-plan/yh-fmt标准库实施方案-2026-10-23.md)。

当前是 **R0**：Value/构造器、文本与整数的默认渲染、追加接口。
f64 默认渲染（R2）与非空格式说明符（R1）尚未接通，分别返回
`status_unsupported` 与 `status_invalid_spec`；这不表示最终行为。

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

## API（R0）

| API | 契约 |
| --- | --- |
| `of_int(int)` / `of_i64(i64)` | 有符号 64 位 |
| `of_u64(u64)` | 无符号 64 位 |
| `of_f64(f64)` | 存储；默认渲染待 R2 |
| `of_bool(bool)` | true/false |
| `of_str(string.View)` | 借用字节文本 |
| `of_cstr(*char)` | NUL 结尾；NULL 视为空串 |
| 零值 `Value` | nil，渲染 `<nil>` |
| `kind_of(Value)` | 读取分类 |
| `append_text(*string.String, string.View) Status` | 追加文本 |
| `append_value(*string.String, Value, string.View) Status` | 空 spec 时按默认格式追加 |

`Status`：`status_ok`、`status_out_of_memory`、`status_overflow`、
`status_invalid_spec`、`status_unsupported`、`status_other`。

## 示例

```yh
import fmt
import string

let out string.String = string.make()
let prefix string.ViewResult = string.view_cstr("n=")
let empty string.ViewResult = string.view_cstr("")
let text_status fmt.Status = fmt.append_text(&out, prefix.value)
let value_status fmt.Status = fmt.append_value(&out, fmt.of_int(-7), empty.value)
// text_status 与 value_status 都应为 status_ok；out 的内容为 "n=-7"。
string.release(&out)
```

## 测试

```bash
cd libs && ../yh test fmt --timeout 60
# 或
make test-lib-tests
```

R0 覆盖构造器分类、文本/有符号/无符号整数、i64 最小值、bool/str/nil、
NULL C 字符串与两个明确失败路径。连接器、print/sprint、spec 与插值降级
按 R1–R3/I0–I5 继续。
