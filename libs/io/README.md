# libs/io —— yh 字节流标准库

`import io;` 提供字节流的完整读写：整段读写、按行读取、调用方缓冲的
`Reader`/`Writer`，并保留 2026-10 之前的四个写侧兼容接口。设计见
[`docs/03-design/yh-io标准库设计.md`](../../docs/03-design/yh-io标准库设计.md)，
分期与验收见
[`docs/02-plan/yh-io标准库实施方案-2026-10-24.md`](../../docs/02-plan/yh-io标准库实施方案-2026-10-24.md)。

## 分层

```text
应用 → io（循环 / 缓冲 / 行语义） → os（单次调用 + 显式错误） → sys（一次内核调用）
```

`io` 只依赖 `os`：不分配内存、不关闭 fd、不做格式化（数值转文本属于
`fmt`，尚未实现）。所有长度与计数单位都是**字节**（`u64`）。

## 兼容接口（签名不变）

```yh
io.write_all_result(fd, data, byte_count) os.IoResult   // 写完全部，保留进度
io.write_all(fd, data, byte_count) int                  // 0 成功 / -1 失败
io.print(text) int                                      // fd 1，无换行
io.println(text) int                                    // fd 1 + '\n'
```

`*char` + 长度，不能表达内嵌 NUL；新代码优先用 `write_bytes` 或 `Writer`。

## 整段读写

```yh
let payload [64]u8
// … 填内容 …
let written os.IoResult = io.write_file("/tmp/a.bin", payload[0..64])
if (written.error.kind != os.error_none) { /* 失败：written.count 为已写进度 */ }

let buffer [4096]u8
let read io.ReadResult = io.read_file("/tmp/a.bin", buffer[0..4096])
if (read.status == io.Status.status_ok) {
    // read.count 为有效字节数
}
```

- `read_all` 到达 EOF 返回 `status_ok`；输出缓冲**恰好填满**时无法确认 EOF，
  返回 `status_truncated`。需要精确判断时给缓冲多留 1 字节。
- `read_file`/`write_file` 自己打开并关闭 fd；其他 API 不关闭调用方的 fd。

## Reader（有缓冲读取）

```yh
let storage [1024]u8
let reader io.Reader
if (io.reader_init(&reader, fd, storage[0..1024]).kind != os.error_none) {
    // 空缓冲：error_invalid_argument
}
let line [256]u8
let result io.ReadResult = io.reader_read_line(&reader, line[0..256])
```

| API | 行为 |
| --- | --- |
| `reader_read(reader, out)` | 至少 1 字节（除非 EOF/错误），不超过缓冲容量 |
| `reader_read_byte(reader)` | 单字节；EOF 时 `status_eof` |
| `reader_read_line(reader, out)` | 读到 `\n`（含）或末行；超长行填满后丢弃该行剩余字节 |
| `reader_buffered(reader)` | 已预读未消费字节数（诊断用） |

行语义：只按 `\n`（0x0A）切分，`\r` 作为普通字节保留（不做 CRLF 转换），
换行符包含在返回内容里；空行返回 `count == 1`；末行无换行返回
`status_ok` + `count > 0`；一个字节都没读到就 EOF 返回 `status_eof`。

## Writer（有缓冲写入）

```yh
let storage [1024]u8
let writer io.Writer
io.writer_init(&writer, fd, storage[0..1024])
io.writer_write(&writer, payload[0..64])   // 全部接收进缓冲，必要时中途写出
io.writer_write_byte(&writer, '\n')
let flushed os.IoResult = io.writer_flush(&writer)  // count 为本次写出字节数
```

- `writer_pending` 返回待写字节数；`writer_write` 的 `count` 是**已接收**字节数。
- 写错误粘滞：之后的 `writer_write` 立即失败；未写出字节保留在缓冲。
- `writer_flush` 在 `error.kind == error_interrupted` 时允许再次调用以重试剩余
  字节（调用方的显式重试，库内不自动重试）；其他错误类别保持粘滞。

## 错误模型

- 失败一律经 `os.Error{kind, native_code}` 返回，`kind` 是 8 种稳定分类
  （`error_none`/`not_found`/`permission_denied`/`interrupted`/…）。
- `io` 自身发现的非法参数（空缓冲）`native_code` 为 0。
- 不自动重试 EINTR，不吞错误，不引入全局错误状态。

## 生命周期

- `Reader.buffer`/`Writer.buffer` 是**借用**：缓冲必须在 init 之后保持存活；
  成功初始化后不得替换。
- `Reader`/`Writer` 是状态对象，结构体赋值只做浅拷贝，两个副本共享缓冲与游标，
  行为未定义；需要独立状态时重新 `init`。
- fd 关闭后不得再调用 `reader_*`/`writer_*`（`io` 无法检测，属于调用契约）。
- `io` 不分配内存，没有需要释放的返回值。

## 测试

```sh
cd libs && ../yh test io --timeout 60
```

`tests.test.yh` 覆盖整文件往返、缓冲写入、分行/空行/末行/超长截断、单字节读取、
`read_all` 的 EOF 与截断、空缓冲非法参数、坏 fd 与缺失文件。门禁已接入
`just test`、`just selfhost-native` 与 `just test-lib-tests`。
