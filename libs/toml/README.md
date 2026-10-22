# libs/toml —— yh TOML 1.1 reader

`libs/toml/` 是普通 `toml` 模块，提供 TOML 1.1 解析、文档持有的值树、按字节
长度的文本视图、类型化查询和结构化诊断。首期只做 reader；writer、保真编辑、
结构体自动映射和 schema 框架不在本模块内。

设计见 [TOML 标准库设计](../../docs/03-design/yh-TOML标准库设计-2026-10-23.md)，
分期见[实施方案](../../docs/02-plan/yh-TOML标准库实施方案-2026-10-23.md)。

## 加载

```yh
import toml
```

项目模式下由编译器标准库搜索层绑定；也可以显式
`YH_STDLIB=<仓库>/libs`。`libs/project.toml` 已注册 `toml`。

## 最小例子

```yh
import io
import toml

pub fn main() int {
    let result toml.ParseResult = toml.parse_text(
        "title = \"yh\"\n[server]\nport = 8080\n")
    if (result.status != toml.parse_ok) {
        io.println(result.error.message)
        toml.release(&result.document)
        return 1
    }
    let root toml.Value = toml.root(&result.document)
    let server toml.LookupResult = toml.get(root, "server")
    let port toml.LookupResult = toml.get(server.value, "port")
    let number i64 = 0
    if (toml.as_i64(port.value, &number) == toml.query_ok) {
        // number == 8080
    }
    toml.release(&result.document)
    return 0
}
```

文件入口：

```yh
let result toml.ParseResult = toml.read_file("config.toml")
```

## 公开类型

| 类型 | 说明 |
| --- | --- |
| `Text` | `data *u8` + `count u64`，UTF-8 字节视图，可含 NUL；借用文档存储 |
| `Document` | 一次成功解析的所有者；结束后必须 `release` |
| `Value` | 文档内节点的只读句柄；复制结构体不产生新所有者 |
| `Span` | 零基字节偏移/长度 + 一基行号/字节列号 |
| `Diagnostic` | 稳定 `ErrorCode`、静态中文消息、主位置、可选关联位置、I/O 原码 |
| `ParseResult` | `status` + `document` + `error` |
| `LookupResult` | `status` + `value` |
| `EntryResult` | `status` + `key` + `value` + `span` |

枚举：`ValueKind`、`ParseStatus`、`QueryStatus`、`ErrorCode`。跨模块按
`toml.kind_string`、`toml.query_ok` 等形式引用。

## 入口与生命周期

```yh
pub fn parse(data *u8, count u64) ParseResult
pub fn parse_text(text *char) ParseResult
pub fn read_file(path *char) ParseResult
pub fn root(doc *Document) Value
pub fn release(doc *Document) void
```

- `parse(0, 0)` 是合法空文档；非零长度要求有效地址。
- 输入只借用；成功后文档独立持有键、字符串和日期时间原文，输入可立即释放
  或改写。失败时没有任何可查询的半成品文档（`document.handle == 0`）。
- `Value`/`Text` 只保证在所属文档 `release` 之前有效。释放后不得查询。
- `release` 后句柄清零；同一个清零句柄可再次释放。
- 不引入引用计数、隐式析构或全局解析状态；多个文档可同时存活。

## 查询

```yh
pub fn kind(value Value) ValueKind
pub fn value_span(value Value) Span
pub fn table_get(table Value, key Text) LookupResult
pub fn get(table Value, key *char) LookupResult
pub fn array_get(array Value, index u64) LookupResult
pub fn count(container Value, out *u64) QueryStatus
pub fn table_entry(table Value, index u64) EntryResult
pub fn as_text(value Value, out *Text) QueryStatus
pub fn as_i64(value Value, out *i64) QueryStatus
pub fn as_f64(value Value, out *f64) QueryStatus
pub fn as_bool(value Value, out *bool) QueryStatus
pub fn as_temporal(value Value, out *Text) QueryStatus
```

- `get(root, "a.b")` 查询**字面键** `a.b`；嵌套表需要多次查询。首期不提供
  重新解析 TOML 路径语法的字符串路径 API。
- 查找失败返回 `query_missing` 和空 `Value`；容器类型不符返回
  `query_type_error`；数组/表下标越界返回 `query_bounds_error`；空输出参数
  或空键指针返回 `query_argument_error`。
- 取值严格按类型：`as_i64` 不接受浮点或数字字符串，`as_f64` 不提升整数，
  `as_text` 不接受日期时间。失败不修改 out 参数。
- `as_temporal` 接受四种日期时间，返回已验证的原始文本；`kind` 仍区分
  `kind_offset_datetime` / `kind_local_datetime` / `kind_local_date` /
  `kind_local_time`。
- `table_entry` 按首次引入顺序返回条目；这是本库的确定性契约，不是 TOML
  规范要求。
- 查询不分配、不打印、不退出。
- 表条目按插入顺序保存，查找/查重为按字节线性比较；没有额外哈希索引。
  这是按配置文件规模做的取舍，大表会出现 O(n²) 级解析成本。

## 语义与数值

- 完整 TOML 1.1 语法：四种字符串、`\e` / `\xHH`、多行字符串与续行、
  点键、引号键/空键、隐式/显式表、内联表（1.1 多行/注释/尾逗号）、
  数组表、混合数组、四种日期时间、1.1 省略秒写法。
- 字符串和键按解码后的字节比较，不做 Unicode 规范化；`\xE9` 输出 UTF-8
  两字节，解码后的 NUL 保留在 `Text` 中。
- 整数存为 `i64`，超范围报 `error_integer_range`；非十进制不接受符号。
- 浮点存为 binary64，十进制转换是私有精确实现：大整数 + 单次就近舍入、
  平局取偶。保留负零、inf、nan 与次正规数；有限字面量上溢报
  `error_float_range`，不静默变成 inf。
- 日期时间只做语法与日历值验证，保留原文；不做时区推断、Unix 时间转换或
  日历运算。秒允许 `00`–`60`（RFC 3339 闰秒），1.1 允许省略秒。

## 错误与位置

`Diagnostic.code` 区分：UTF-8、语法、重复键、表冲突、整数范围、浮点范围、
日期时间值、资源上限、内存不足、I/O、参数错误。重复定义报告第二处，并用
`related`/`has_related` 关联第一处。行号/列号一基，CRLF 计一行，tab 计一个
字节列。

文件适配按平台分文件：Linux 使用 `os.open_path/read_some/close_file`，保留
errno 与 EINTR；Darwin 在 OS8 新文件 API 落地前使用
`os.open_file/read_fd/close_fd`，`native_code` 为 0 且不区分 interrupted。

只报第一个错误，不做多错误恢复。核心不读取全局 errno、不写
stdout/stderr、不退出进程；`read_file` 的 I/O 错误在 Linux 通过
`native_code` 给出目标平台错误号，Darwin 兼容路径为 0。

## 资源限制

实现限制而非 TOML 规范限制，超限返回 `parse_resource_error`：

| 限制 | 值 |
| --- | --- |
| 输入字节 | 16 MiB（`parse` 长度或文件累计读取） |
| 容器嵌套 | 128 层 |
| 单键段数 | 128 |
| 单个浮点有效数字 | 4096 位 |
| 单文档累计分配 | 128 MiB |

所有长度加法、乘法和扩容先做溢出检查；超限报错，不截断或伪装成语法错误。
不支持无限文档或无限精度。

## 实现文件

按编译顺序（类型必须先定义，文件名数字前缀控制顺序）：

| 文件 | 职责 |
| --- | --- |
| `00_types.yh` | 公开类型/枚举、预算与私有定义状态常量 |
| `10_storage.yh` | 私有池、稳定节点、表条目/数组容器 |
| `20_utf8.yh` | UTF-8 校验、标量编码、十六进制 |
| `30_numbers.yh` | 整数/浮点扫描、精确 binary64 转换、大整数 |
| `40_datetime.yh` | 四种日期时间扫描与值验证 |
| `45_parser_state.yh` | 游标、诊断、空白/注释 |
| `46_strings.yh` | 四种字符串扫描、转义与解码 |
| `50_parse.yh` | 文档、键、值、表语义 |
| `60_query.yh` | 只读查询与类型化取值 |
| `70_files.linux.yh` / `70_files.darwin.yh` | 平台文件读取适配 |
| `90_api.yh` | 解析入口、生命周期、诊断构造 |

私有状态、节点和池不进入 `.s.i`；只导出应用真实消费的 `pub` 声明。

## 验收

```bash
python3 tests/toml/run.py                  # API/所有权/资源/文件 6 组
python3 tests/toml/conformance.py --prepare  # 首次：取固定 toml-test v2.2.0
python3 tests/toml/conformance.py          # 官方 tagged JSON decoder 门
python3 tests/toml/injection.py            # 124 个池分配失败点 + 预算门
python3 tests/toml/install.py              # make install 后仓库外导入
make test-toml
make test-toml-conformance
make test-toml-injection
make test-toml-install
```

固定语料为 toml-test v2.2.0 的 `files-toml-1.1.0` 清单：214 个有效文件比较
值树，467 个非法文件要求拒绝。`--prepare` 下载后核对 SHA-256
`fdab2779b3902eb08030f389a5d53e95c5b49404149ac6f2eda5227a5363c232`；
常规运行不会静默联网。

分配失败门在临时标准库副本中注入测试接缝：产品源码保留默认 `-1` 的私有
常量 `TOML_TEST_FAIL_AFTER` 与池分配计数（不导出 API、恒不生效），测试副本
改写该常量的使用位置为运行时设置。逐次允许更多池分配，验证 124 个失败点的
失败原子性；另把副本预算降到 2048 字节，强制验证累计预算分类。安装门执行
`make install` 并把 fixture 放到仓库外，在无 `YH_STDLIB` 时用默认
`../share/yh/libs` 发现运行。

## 未实现

- writer/encoder、注释与排版保真编辑。
- 结构体自动映射、schema 框架、环境变量展开、include。
- 编译器 `project.toml` 消费者迁移（T6）；迁移前编译器仍使用旧清单解析器。
- Release 资产当前只含 `yh`，标准库由 `make install` 分发；是否把标准库
  打包进 Release 尚未决定（T5.2）。
