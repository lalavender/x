# yh io 标准库设计

修改时间：2026-11-06

状态：**IO0–IO4 已实施**（`libs/io/`，本平台
`cd libs && ../yh test io` 通过）；IO5–IO6 规划。
本文件把 `libs/io` 定义为**字节流的完整读写层**：在 `os` 的单次原语之上提供
读原语、行读取与调用方缓冲的 `Reader`/`Writer`，并保留 2026-10 之前的四个写侧
兼容接口。格式化（数值转文本）不属于本模块，见
[fmt 设计](yh-fmt标准库设计.md)；分期与验收见
[实施方案](../02-plan/yh-io标准库实施方案-2026-10-24.md)。

## 1. 实际基线

- `libs/io/io.yh` 现有 61 行、4 个公开函数：`write_all_result`、
  `write_all`、`print`、`println`。全部是**写侧**，`print`/`println` 只接收
  NUL 结尾 `*char`，无法表达内嵌 NUL 或带长度的字节串。
- 调用点已扩散到 `libs/cli/help.yh`（诊断/帮助输出）、`examples/os-demo`、
  `tests/modules/projects/{libsio,osio,syseintr}` 与 `tests/modules/projects/toml*`
  （`io.print`/`io.println` 是这些验收项目唯一的输出手段）。这些调用只用写侧，
  因此本设计不改变它们的签名与返回值。
- **读取侧完全缺失**：`libs/toml/file.{linux,darwin}.yh` 各自手写了约 100 行
  短读循环（容量倍增、EOF 探测、错误优先级、关闭顺序），是同一缺口的重复实现；
  编译器读源文件走 prelude，不经过 `io`。
- `os` 已提供本层需要的全部原语：`read_some(fd, []u8)`、`write_some`、
  `open_path`、`close_file`、`IoResult{count, error}`、`Error{kind, native_code}`
  与 `read_options`/`write_options`；`sys` 只提供单次内核调用、不循环不重试。
- 语言现状（决定 API 形状）：没有接口、泛型、方法接收者与闭包类型，因此
  Go 的 `io.Reader`/`io.Writer` 接口无法表达；`pub struct` 字段一律公开，
  隐藏内部状态只能靠 `*void` 句柄 + 模块私有状态（`string.String` 的做法）。

## 2. 方案取舍

| 方案 | 结论 |
| --- | --- |
| 只继续加 `*char` 函数 | 无法表达内嵌 NUL 与长度，读取还需要缓冲区参数；不满足已选范围 |
| Go 式 `Reader`/`Writer` 接口 + 具体实现 | 语言无接口/泛型，只能退化为函数指针表，调用点更重；不选 |
| 句柄 + 模块私有状态 + `memory.alloc` | 能隐藏 8 KB 缓冲，但每次使用都要分配/释放并引入 OOM 分支，编译器与测试路径都变复杂 |
| **调用方提供缓冲区 + `Reader`/`Writer` 结构** | 与 `os.open_dir(path, buffer)`、`os.get_cwd(buffer)` 同风格；零分配、无隐藏所有权、可栈上构造；**选它** |
| 增加 `seek`/`tell` | `os`/`sys` 尚无 `lseek`/`fstat`，不做；需要时先在 `os` 立项 |
| 在 `io` 里做格式化（`print(int)` 等） | 与 fmt 重复；`io` 只处理字节，格式化后置给 fmt |

`io` 只依赖 `os`，不依赖 `string`/`memory`/`fmt`，避免与后续插值运行时形成环。

## 3. 分层

```text
应用 / cli / toml / 编译器
        │  字节 + 行
        ▼
io：完整读写（write_all/read_all）、行读取、调用方缓冲的 Reader/Writer
        │  单次原语 + 显式错误
        ▼
os：read_some / write_some / open_path / close_file / IoResult / Error
        │  一次内核调用，-errno
        ▼
sys：read/write/openat/close（Linux 内核调用、Darwin libSystem）
```

每层只做本层的事：`sys` 不循环不重试，`os` 做错误归一化与一次调用，`io` 负责
**循环、缓冲、进度与行语义**。

## 4. 模型

```yh
// Status 是 io 层的结果分类；status_io_error 时 error 携带 os 的稳定分类。
pub enum Status {
    status_ok
    status_eof
    status_truncated
    status_invalid_argument
    status_io_error
}

// ReadResult 是一次读取的结果；count 为写入调用方缓冲的字节数。
// status_ok 表示按契约完成（read_all 到达 EOF、read_line 取到一行或末行），
// status_eof 表示一个字节都没读到就结束，status_truncated 表示输出缓冲不足。
pub struct ReadResult {
    status Status
    count u64
    error os.Error
}

// ByteResult 是单字节读取结果；status_eof 时 value 为 0。
pub struct ByteResult {
    status Status
    value u8
    error os.Error
}

// Reader 是有缓冲的读取器；buffer 借用调用方存储，不复制、不释放。
// begin/end 是本模块解释的游标，调用方只应通过 reader_* 函数操作。
pub struct Reader {
    fd int
    buffer []u8
    begin u64
    end u64
    eof bool
    error os.Error
}

// Writer 是有缓冲的写入器；buffer 借用调用方存储，count 为待写字节数。
pub struct Writer {
    fd int
    buffer []u8
    count u64
    error os.Error
}

// IO_BUFFER_SIZE 是建议的缓冲大小；不是强制值，调用方可用任意非空缓冲。
pub const IO_BUFFER_SIZE u64 = 8192
```

不复用 `string.Status`：io 的失败分类是 eof/truncated/io_error，与字符串的
bounds/utf8 无关。复用 `os.Error` 与 `os.IoResult` 保持错误来源唯一。

## 5. 公开 API

### 5.1 兼容接口（签名不变，2026-10 之前）

`write_all_result`/`write_all` 原样迁入 `write.yh`（与写入层同文件，
`writer_flush` 直接复用），`print`/`println` 留在 `io.yh`；四者的签名、返回值、
注释语义均未改变。

| API | 契约 |
| --- | --- |
| `write_all_result(fd int, data *char, byte_count int) os.IoResult` | 写完全部字节并保留短写/EINTR 前的进度；负长度返回 `error_invalid_argument` |
| `write_all(fd int, data *char, byte_count int) int` | 全写返回 0，否则 -1（长度非法、写入失败、零进度） |
| `print(text *char) int` | NUL 结尾串写 fd 1，不追加换行 |
| `println(text *char) int` | 同上并追加一个 `\n` |

### 5.2 读取（`read.yh`）

| API | 契约 |
| --- | --- |
| `read_all(fd int, out []u8) ReadResult` | 循环读到 EOF 或 `out` 满；EOF 时 `status_ok`，`out` 恰好填满且未确认 EOF 时 `status_truncated` |
| `read_file(path *char, out []u8) ReadResult` | 打开→`read_all`→关闭；fd 由本函数关闭，读取结果优先于关闭错误 |
| `reader_init(reader *Reader, fd int, buffer []u8) os.Error` | 绑定 fd 与调用方缓冲；空缓冲返回 `error_invalid_argument`，此时 `Reader` 不可用 |
| `reader_read(reader *Reader, out []u8) ReadResult` | 返回至少 1 字节（除非 EOF/错误），不超过缓冲容量；`status_eof` 表示流结束 |
| `reader_read_byte(reader *Reader) ByteResult` | 取一个字节；EOF 时 `status_eof` |
| `reader_read_line(reader *Reader, out []u8) ReadResult` | 读到 `\n`（含）或 EOF；行超过 `out` 时返回 `status_truncated` 并丢弃该行剩余字节 |
| `reader_buffered(reader *Reader) u64` | 已预读未消费的字节数（诊断用，不做流控） |

### 5.3 写入（`write.yh`）

| API | 契约 |
| --- | --- |
| `write_bytes(fd int, data []u8) os.IoResult` | 循环写完全部字节，返回已写进度与显式错误；支持内嵌 NUL |
| `write_file(path *char, data []u8) os.IoResult` | 截断创建→`write_bytes`→关闭；fd 由本函数关闭 |
| `writer_init(writer *Writer, fd int, buffer []u8) os.Error` | 绑定 fd 与调用方缓冲；空缓冲返回 `error_invalid_argument` |
| `writer_write(writer *Writer, data []u8) os.IoResult` | 全部接收进缓冲（必要时中途 flush），`count` 为已接收字节数 |
| `writer_write_byte(writer *Writer, value u8) os.IoResult` | 单字节写入缓冲 |
| `writer_flush(writer *Writer) os.IoResult` | 把缓冲写出；`count` 为本次实际写出字节数，未写出字节保留在缓冲 |
| `writer_pending(writer *Writer) u64` | 待写出字节数 |

`io` 不关闭 `Reader`/`Writer` 绑定的 fd：fd 所有权仍属调用方，`reader_*`/
`writer_*` 只使用不关闭。`read_file`/`write_file` 打开自己的 fd，因此负责关闭。

## 6. 语义细节

### 6.1 EOF 与截断

- 单次读取返回 0 字节且无错误就是 EOF（`os.IoResult` 的既有契约）。
- `read_all` 用 `status_ok` 表示**确认到达 EOF**；当 `out` 恰好填满时无法在不
  多读一个字节的前提下确认 EOF，因此返回 `status_truncated`。需要精确判断时
  调用方给 `out` 多留 1 字节。
- `read_line` 在"还没读到任何字节就 EOF"时返回 `status_eof`；读到末行但无换行
  时返回 `status_ok`（`count > 0`），调用方以 `count` 区分末行。
- `status_truncated` 不丢弃已经写入 `out` 的字节；`count` 始终是 `out` 中有效
  字节数。

### 6.2 行语义

- 只按 `\n`（0x0A）切分；`\r\n` **不转换**，`\r` 作为普通字节保留；不做
  Unicode 换行识别、不做行内裁剪。需要 CRLF 处理由调用方在拿到行后自行裁剪。
- 换行符包含在返回内容里（与 `read_line` 名称一致，调用方自行决定是否去掉）。
- 行超过 `out` 容量时：填满 `out`，**丢弃该行剩余字节直到并包含 `\n`**，返回
  `status_truncated`。这样每次调用恰好消费一行，不会让调用方在半个行上循环。
- 空行（只有一个 `\n`）返回 `count == 1`。

### 6.3 短读、短写与 EINTR

- 单次原语（`os.read_some`/`os.write_some`）允许短读写，`io` 的 "all" 系列
  循环直到完成或出错，并**保留已取得进度**。
- 遇 `error_interrupted` 不自动重试，作为错误返回（沿用 `os`/`sys` 的既有策略），
  调用方可据 `count` 续做。
- `Reader` 内部预读失败时把错误记入 `reader.error`，此后所有读操作直接返回该
  错误，不再触碰 fd（粘滞）。
- `Writer` 的写错误同样粘滞：`writer_write`/`writer_write_byte` 立即失败；
  未写出的字节保留在缓冲（flush 失败时把剩余字节前移），`writer_flush` 在
  `error.kind == error_interrupted` 时清除错误并重试剩余字节——这是**调用方的
  显式重试**，不是库内自动重试；其他错误类别保持粘滞并原样返回。

### 6.4 非法参数

- `reader_init`/`writer_init` 的空缓冲返回 `error_invalid_argument`，`native_code`
  为 0（库自身发现，不伪造内核错误号）。
- `read_all`/`read_line` 的零长度 `out`：不读取、按截断语义返回
  `status_truncated`（`count == 0`），与"缓冲不足"一致；`read_line` 此时仍会
  消费一整行。
- `reader_read` 的零长度 `out` 返回 `status_ok`、`count == 0`，不消费字节。

## 7. 所有权与生命周期

- `Reader.buffer`/`Writer.buffer` 是**借用**：调用方保证缓冲在 init 到不再使用
  之间存活且不被改写（`Writer` 例外：缓冲内容由本模块写入）。
- `Reader`/`Writer` 是**状态对象**：结构体赋值只做浅拷贝，两个副本会共享同一
  缓冲与游标，行为未定义。需要复制状态时由调用方重新 `init`。
- 成功初始化后不得移动或替换 `buffer`；fd 关闭后不得再调用任何 `reader_*`/
  `writer_*`（`io` 无法检测，属于调用契约）。
- `read_file`/`write_file` 自持 fd，任何返回路径都关闭；`write_file` 用
  `write_options()` + `truncate = true`，不创建父目录。
- 本模块不分配内存，因此没有 OOM 分支，也没有需要 `release` 的返回值。

## 8. 与 Go / Rust / Zig 的差异

1. 没有 `io.Reader`/`io.Writer` 接口与适配器（`TeeReader`、`LimitReader` 等）：
   语言无接口/泛型，参数一律是具体类型或 `fd int`。
2. 缓冲由调用方提供，不内建 4 KB 默认缓冲，也没有"缓冲池"或隐式分配。
3. `read_line` 需要调用方给输出缓冲；没有"返回新分配的字符串"的重载
   （要分配就得引入 `memory`/`string` 依赖与 OOM 语义）。
4. 没有 `Scanner` 式分词（`ScanWords`/`ScanLines` 回调），没有 `bufio.Split`。
5. 没有 `Seek`/`Peek`/`UnreadByte` 之外的能力：`Reader` 不提供 peek/unread
   公共接口，避免依赖 `lseek` 的"回退"实现。
6. 错误不是接口而是 `os.Error{kind, native_code}`，分类固定为 8 种。
7. 不做隐式重试：EINTR 必须由调用方观察并决定（Go 的 `bufio`/`os.File` 会自动重试）。

## 9. 非目标（明确不做）

- 异步/非阻塞 IO、事件循环、`poll`/`select`/`epoll` 封装；
- 网络 socket、`mmap`、文件锁、`sendfile`；
- `seek`/`tell`/`truncate`/`stat`（需要 `os` 先补原语）；
- 格式化输出（`print(123)`、`%d`）与字符串插值运行时（fmt 承接）；
- 通用编码转换（UTF-8/UTF-16、CRLF 归一化、BOM 处理）；
- 并发安全：`Reader`/`Writer` 不做加锁，跨线程使用由调用方负责；
- 缓冲池、零拷贝 `splice`、`io_uring`。

## 10. 测试与验收

- `libs/io/tests.test.yh` 用语言内 `test` 块覆盖：整文件往返（`write_file` →
  `read_file`）、跨缓冲的大写入、`read_line` 的正常/空行/末行无换行/超长截断、
  `reader_read_byte`、`read_all` 的 EOF 与截断、空缓冲 `init` 的非法参数、
  坏 fd 的错误路径、`writer_flush` 后的 `writer_pending` 归零。
- 门禁：`cd libs && ../yh test io`；已加入 `make test`、`make selfhost-native`
  与 `just test-libs`。
- 既有验收项目 `tests/modules/projects/libsio`、`osio`、`syseintr` 继续覆盖兼容
  接口，不改动其断言。
- `read_file`/`write_file` 的文件用例写入 `/tmp` 下的进程唯一路径并在结束时删除，
  不依赖仓库内临时目录，也不联网。

## 11. 分期

| 切片 | 内容 | 状态 |
| --- | --- | --- |
| IO0 | 现状盘点、调用点普查、语言能力探针（`[]u8` 字段、切片、`memcpy`、`os.Error` 字段） | 完成 |
| IO1 | `base.yh`：`Status`/`ReadResult`/`ByteResult`/`Reader`/`Writer`/`IO_BUFFER_SIZE` | 完成 |
| IO2 | `read.yh`：`reader_init`/`reader_read`/`reader_read_byte`/`reader_read_line`/`reader_buffered`/`read_all`/`read_file` | 完成 |
| IO3 | `write.yh`：`writer_init`/`writer_write`/`writer_write_byte`/`writer_flush`/`writer_pending`/`write_bytes`/`write_file` | 完成 |
| IO4 | `tests.test.yh`、`doc.yh`、`README.md`、门禁接入 | 完成 |
| IO5 | `toml/file.*.yh` 迁移到 `io.read_file`，删除重复读循环 | 规划 |
| IO6 | `os` 补 `lseek`/`fstat` 后评估 `Reader` 的 peek/seek 与 `io.copy` | 规划（依赖 os） |

IO5 是首个真实消费者迁移，用于验证 API 是否够用；未迁移前不宣称"标准库已统一
走 io"。
