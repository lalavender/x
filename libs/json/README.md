# libs/json —— yh JSON 标准库

`import json;` 提供 RFC 8259 的读写：解析内存/文件为只读值树，按真实类型
取值并定位错误；从值树或增量 builder 写出紧凑或缩进文本。

设计见 [docs/03-design/yh-JSON标准库设计-2026-10-24.md](../../docs/03-design/yh-JSON标准库设计-2026-10-24.md)，
分期见 [实施方案](../../docs/02-plan/yh-JSON标准库实施方案-2026-10-24.md)，
取舍见 [ADR-0019](../../docs/adr/0019-yh-JSON标准库独立文档模型与词素保真数字.md)。

## 例子

```yh
import json

fn main() int {
    let result json.ParseResult = json.parse_text("{\"a\": [1, 2.5]}")
    if (result.status != json.parse_ok) {
        return 1
    }
    let root json.Value = json.root(&result.document)
    let a json.LookupResult = json.get(root, "a")
    let count u64 = 0
    json.count(a.value, &count)

    let options json.WriteOptions
    options.indent = 2
    options.escape_non_ascii = 0
    options.sort_keys = 0
    let encoded json.EncodeResult = json.encode_owned(root, options)
    if (encoded.status == json.write_ok) {
        // encoded.text 是 string.String，用完必须 release。
    }
    json.release(&result.document)
    return 0
}
```

增量写出（不建值树）：

```yh
let text string.String = string.make()
let b json.Builder = json.builder_make(&text, options)
json.begin_object(&b)
json.key(&b, json.Text{ data: "n".to_type(*u8), count: 1 })
json.write_i64(&b, 42)
json.end_object(&b)
json.builder_finish(&b)
```

## 公共面

| 组 | API |
| --- | --- |
| 解析 | `parse(data, count)`、`parse_text(text)`、`read_file(path)`、`root(doc)`、`release(doc)` |
| 查询 | `kind`、`value_span`、`object_get`、`get`、`array_get`、`count`、`object_entry`、`as_text`、`as_bool`、`as_i64`、`as_f64`、`number_text`、`is_integer` |
| 写出 | `builder_make`、`begin_object`/`end_object`、`begin_array`/`end_array`、`key`、`write_string`、`write_i64`、`write_f64`、`write_bool`、`write_null`、`write_number_text`、`builder_finish`、`builder_status` |
| 一次性 | `encode`、`encode_owned`、`write_file` |

`Document` 是单一所有者：成功解析后由调用者 `release`，释放后所有 `Value`/
`Text` 视图失效。`encode_owned` 返回的 `string.String` 同样由调用者释放。

## 文件布局

模块内按**文件名字节序**编译，声明必须先于使用，因此文件名就是依赖顺序
（不加数字前缀）：`base`（类型/常量）→ `digits` → `document` → `encoding` →
`lex` → `parse` → `query` → `render` → `serialize` → `stream.*`（平台文件读写）→
`surface`（公开入口）；`json.test.yh` 按 `.test.yh` 规则固定排最后。新增文件
必须让自己的名字落在这条拓扑序里，细节见
[设计文档 §2](../../docs/03-design/yh-JSON标准库设计-2026-10-24.md)。

## 数字语义（与 toml 不同）

JSON 只有一个 number 类型，本库**只校验 grammar 并保存原始词素**：

- `number_text` 返回词素；`parse → encode` 对数字字节级保真（`1.0` 仍是
  `1.0`，`1e400` 仍是 `1e400`）。
- `as_i64` 只接受整数形式且在 i64 范围内，否则 `query_type_error` /
  `query_range_error`。
- `as_f64` 走 `libs/num` 的精确十进制 → binary64；上溢报 `query_range_error`，
  **不返回 ±Inf**；下溢到 0 或次正规是正确舍入结果。
- `is_integer` 是谓词，不是类型：它问「能否无损取成 i64」。

`1e400` 这类超出 binary64 的合法 JSON 数字**解析成功**、取值报范围错误。这是
按 JSON 规范（无界十进制）与 TOML 规范（binary64）各自实现的结果。

## 严格性 profile（与常见实现的差异）

| 项 | 本库 | 说明 |
| --- | --- | --- |
| 重复键 | **拒绝**（`error_duplicate_key`） | ECMAScript `JSON.parse` 是 last-wins；本库避免静默丢字段 |
| BOM | **拒绝**（`error_bom`） | RFC 8259 禁止产生 BOM，允许解析器忽略；本库选择报错 |
| 孤立代理 | **拒绝**（`error_surrogate`） | `\uD800` 单独不构成字符；I-JSON 禁止 |
| 尾逗号 / 注释 / 单引号 | **拒绝** | 不是 JSON（不做 JSON5/JSONC） |
| 顶层标量 | 允许 | RFC 8259 §2 |
| 尾随内容 | 拒绝 | 必须完整消费输入 |

## 预算与复杂度

| 常量 | 值 | 含义 |
| --- | --- | --- |
| `JSON_MAX_INPUT` | 16 MiB | 输入字节上限 |
| `JSON_MAX_DEPTH` | 256 | 容器嵌套上限 |
| `JSON_MAX_BYTES` | 128 MiB | 单文档累计分配上限 |
| `JSON_MAX_SIG_DIGITS` | 4096 | `as_f64` 允许的有效位数 |
| `JSON_MAX_INDENT` | 16 | 缩进空格上限 |

对象键查找与重复键检测都是**按字节线性比较**：大对象是 O(n²) 级。按配置文件与
常见 API 负载的规模取舍；哈希索引列为后置项（`JSON_HASH_THRESHOLD` 预留）。

## 写出细节

- 默认紧凑；`indent` 为 1..16 时按层缩进，空容器仍写 `{}` / `[]`。
- 失败粘滞：首次失败后所有调用变为无操作，并把缓冲回滚到调用前长度。
- `escape_non_ascii=1` 时所有非 ASCII 标量写 `\uXXXX`，BMP 以上写代理对；
  内容必须是合法 UTF-8，否则 `write_invalid_utf8`。
- `write_f64` 输出最短往返十进制且总带小数点或指数（`1.0` 不写成 `1`），
  NaN/±Inf 报 `write_number_range`。
- `sort_keys=1` 只影响输出顺序，不改变文档。

## 验收

```bash
cd libs && yh test json   # 12 个 test：parse/查询/写出/错误/文件
just test-json            # 历史 target 已删除，改用 yh test json / just libs-test
```

行为断言在 `libs/json/json.test.yh`；`jsonmodel` 是
`tests/modules/projects/` 下保留的公开面 smoke（`build-check.py` 的
`j1-json-model`）。迁移记录见
[YT4-P1](../../docs/01-finished/yh-YT4-P1-json迁移-2026-10-25.md)。

## 尚未实现

- JSONTestSuite 一致性语料与 Python 差分（J5）。
- 分配失败注入与低预算门（J4）。
- `just test-json-install` 仓库外导入验收（J7）。
- JCS 规范模式、大对象哈希索引、流式 SAX、JSON Pointer（J8，按需）。
