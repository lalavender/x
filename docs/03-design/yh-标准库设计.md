# yh 标准库设计

本文记录 `libs/` 项目的标准库源码与当前 API 契约。标准库是普通 yh 项目，
使用 `project.toml` 管理；项目模式下仍由编译器的标准库搜索层绑定，而不是
把 prelude 内建声明当成标准库模块。

## 项目与加载

标准库源码位于仓库根目录 `libs/`，清单源码根直接设为 `.`，模块按
`libs/<模块名>/<模块名>.yh` 放置，不再设置 `src/` 子目录。编译器当前通过
`YH_STDLIB` 环境变量加载标准库项目根目录；例如：

```sh
YH_STDLIB=/path/to/yh/libs yh run
```

未设置 `YH_STDLIB` 时不会自动发现该目录。工具链安装时的默认路径与打包布局
尚未确定，属于后续交付工作。应用按普通模块语法导入库模块，例如 `import io;`；
本地同名模块仍按既定搜索顺序遮蔽标准库模块。

## 基础模块

本批模块围绕编译器现有运行时和 Darwin 主机接口，提供小而明确的 yh API。
当前不承诺跨平台一致性；`os` 使用宿主 POSIX 风格接口，`time` 使用 Darwin
已登记的 `clock_gettime`，`math` 使用宿主 C 数学符号。libc 裸变参 `printf`
仍由 yh 自有运行时处理，不进入 FFI。

### `io`

| API | 契约 |
| --- | --- |
| `write_all(fd int, data *char, byte_count int) int` | 写完全部字节返回 0；长度为负、底层写入失败或返回零时返回 -1；循环处理短写，不重试被信号中断的写入 |
| `write_all_result(fd int, data *char, byte_count int) os.IoResult` | 完整写入并保留短写/EINTR/EAGAIN 前的已写进度与显式错误 |
| `print(text *char) int` | 将 NUL 结尾字符串写到标准输出，不追加换行；成功返回 0，失败返回 -1 |
| `println(text *char) int` | 写字符串并追加一个换行；成功返回 0，失败返回 -1 |

`io` 经 `os.write_once` 写入（Linux 映射 sys -errno，Darwin 使用 prelude 兼容入口），
字符串长度仍用 prelude `strlen`。

### `memory`

| API | 契约 |
| --- | --- |
| `alloc(byte_count u64) *void` | 显式申请指定字节数；失败返回空指针 |
| `release(data *void) void` | 释放 `alloc` 返回的内存；空指针可传入 |
| `copy(destination *void, source *void, byte_count u64) *void` | 复制指定字节数并返回目标地址 |

本模块只包装现有 yh 运行时分配与复制入口；所有权由调用方管理，不引入隐式分配。
`alloc` 结果至少 16 字节对齐，`alloc(0)` 返回非空地址，`copy` 不处理重叠区间。

2026-10-23 新增[内存管理标准库设计](yh-memory标准库设计-2026-10-23.md)与
[实施方案](../02-plan/yh-memory标准库实施方案-2026-10-23.md)，按 Zig
`std.mem.Allocator`/`std.heap` 的能力分层规划：保持上述签名不变，补
`reallocate`（显式 `old_size`）、`FixedBuffer`（调用方缓冲区、LIFO
resize/free）、增强 Arena（几何增长、reset 模式、LIFO 回收、capacity）与
基于 Arena + 空闲链的 FixedPool；统一 `Allocator`（函数指针 vtable）为 M5
可选，Debug/ThreadSafe/Page/StackFallback 后置。设计状态是**未实施**：当前
只有上表三个 API；块来源统一为 prelude 堆，不新增 `sys` 依赖，也不替换
`libc` 的 C ABI 分配器。

### `string`（2026-10-23 首期完成）

旧接口保持原签名、返回值与 NUL 截止语义：

| API | 契约 |
| --- | --- |
| `length(text *char) u64` | 返回 NUL 结尾字符串的 UTF-8 字节数 |
| `equals(left *char, right *char) int` | 内容相等返回 1，否则返回 0 |
| `compare(left *char, right *char) int` | 按无符号字节序返回 -1、0 或 1 |

新增按字节存储的 `View`（借用）与 `String`（独占、显式释放），单位统一为
字节（`u64`）。公开面分四组：

| 组 | API |
| --- | --- |
| 视图 | `view_bytes`/`view_cstr`、`view_equal`/`view_compare`、`starts_with`/`ends_with`、`find`/`rfind`/`contains`、`slice`、`trim_ascii`、`split`/`split_next` |
| 拥有者 | `make`、`from_view`、`clone`、`move`、`release`、`as_view`、`byte_length`、`capacity`、`reserve`、`clear`、`truncate`、`assign`、`append`、`append_byte`、`c_str` |
| 变换 | `concat`、`join`、`replace`、`replace_all`、`lower_ascii`、`upper_ascii` |
| UTF-8 | `utf8_validate`、`utf8_next`、`append_rune`（RFC 3629 严格解码，只计标量） |

`String` 始终维护额外结尾 NUL，内容内允许 NUL；成功的可变操作与 `release`
使旧视图/C 指针失效，失败的操作保持原状态。最大内容长度
`0x7ffffffffffffffe`，查找/切分/替换首版最坏 `O(n*m)`。Unicode 大小写折叠、
规范化、字素边界、正则与格式化仍后置。

设计见 [string 标准库设计](yh-string标准库设计-2026-10-23.md)，分期与验收见
[实施方案](../02-plan/yh-string标准库实施方案-2026-10-23.md)，使用说明见
[`libs/string/README.md`](../../libs/string/README.md)。

### `os`

| API | 契约 |
| --- | --- |
| `open_file(path *char, flags int) int` | 不含创建标志时打开路径，返回文件描述符或 -1 |
| `open_file_mode(path *char, flags int, mode int) int` | 含创建标志时打开路径并传权限位 |
| `read_fd(fd int, buffer *void, byte_count u64) i64` | 最多读取指定字节数，返回实际字节数或 -1 |
| `write_fd(fd int, buffer *void, byte_count u64) i64` | 最多写入指定字节数，返回实际字节数或 -1 |
| `close_fd(fd int) int` | 关闭文件描述符，返回宿主结果 |
| `create_dir(path *char, mode int) int` | 创建单层目录，返回宿主结果 |
| `remove_dir(path *char) int` | 删除空目录，返回宿主结果 |
| `remove_file(path *char) int` | 删除文件系统路径，返回宿主结果 |
| `rename_file(old_path *char, new_path *char) int` | 重命名路径，返回宿主结果 |
| `process_id() int` | 返回当前进程号 |
| `sleep_us(duration int) int` | 睡眠微秒数；负值返回 -1，其余返回宿主结果 |
| `terminate(code int) void` | 用指定状态结束当前进程 |
| `platform() *char` | 返回编译目标的平台名称，当前为 linux/darwin 或 unknown |
| `arch() *char` | 返回编译目标架构名称，当前为 arm64/x64 或 unknown |

这些函数沿用宿主接口的返回值和标志，不会把平台常量伪装成跨平台抽象。

2026-10-19 新增 [os/sys 联合设计](yh-os与sys标准库设计.md)，用户选择标准库
可用性优先。2026-10-21 已完成 OS0–OS6：新增 `Error/FdResult/IoResult/
OpenOptions/DirReader/DirEntry/EnvResult/PidResult/WaitResult` 与
`open_path/read_some/write_some/close_file/make_dir/remove_path/remove_dir_path/
rename_path/open_dir/next_entry/close_dir/get_cwd/change_dir/get_env/spawn/wait/
exit_now`（文件/目录/进程为 Linux，环境为跨平台）；上表旧接口保留原名字、
宿主标志与 -1 约定。默认标准库发现与安装布局也已接入。

### `math`

提供 `sqrt_f64(value f64) f64`、`sin_f64(value f64) f64`、
`cos_f64(value f64) f64`、`pow_f64(base f64, exponent f64) f64` 四个函数，
转发到固定参数的宿主 C 数学符号。它不声明 libc 变参，也不保证其他平台存在
相同 ABI。

### `time`

提供 `monotonic_ns() i64`，返回单调时钟纳秒数；底层调用失败返回 -1。
Darwin 使用宿主 `CLOCK_MONOTONIC` 编号与 `clock_gettime`；Linux 走
`sys.read_clock(CLOCK_MONOTONIC)`，不再硬编码 Darwin 编号。

## sys（2026-10-03 规划，2026-10-21 已实现 OS0–OS5 子集）

用户指定系统调用封装放在 `libs/sys/`；模块入口见
[README](../../libs/sys/README.md)，完整契约与分期见
[sys 设计](yh-sys系统调用封装设计.md)和
[实施方案](../02-plan/yh-sys系统调用封装实施方案.md)。

Linux/x64 与 Linux/arm64 按现有后端分别复用 `linux_syscall6`，提供 raw6、
显式错误结果及文件/目录、内存/时间、进程原语；sys 不分配、不自动重试，结果
保留 `-errno`。按[联合实施方案](../02-plan/yh-os与sys标准库实施方案.md)逐个场景
交付 os 新接口，io/time 复用底层并保留旧契约；编译器整体迁移另列后续阶段，
采用显式项目依赖。不把静态 ELF/编译器独立验收作为文件 API 可用的前置。
macOS/arm64 后续适配审核的系统 OS API，披露 dyld/libSystem 依赖。

当前已实现 `00_types.yh`、Linux 两种 ISA 的常量、`20_raw.linux.yh`、文件/目录/
cwd/pipe（`30_file`）、内存（`40_memory`）、时间（`50_time`）与进程
（`60_process`）原语；Darwin 桥仍待实施。未迁移本文已有 API。静态 ELF、
启动入口和连续自编须与自有工具链共同验收。

## cli（2026-10-18 设计；CLI0–CLI5 已实现，2026-10-19）

`libs/cli/` 以 `import cli;` 提供接近 Python argparse 完整能力的命令行解析。
采用参数声明、显式解析结果和类型化查询，覆盖位置/选项、多值与重复参数、子命令、
参数组/互斥组、部分/混合解析、自定义回调、参数文件及自动帮助。

核心返回结果，由入口适配决定输出和退出；声明和结果分别显式释放，不依赖反射、
泛型或新语法。完整接口、差异和生命周期见
[cli 设计](yh-cli标准库设计.md)，与 argparse 的差异见
[对照说明](yh-cli与argparse差异.md)，CLI0–CLI6 分期见
[实施方案](../02-plan/yh-cli标准库实施方案.md)，API 与状态见
[libs/cli/README.md](../../libs/cli/README.md)。

已注册模块并在 `libs/project.toml` 登记；公开面分文件为
`cli.yh`（模型与分配池）、`schema.yh`（注册与冻结）、`values.yh`（命名空间）、
`parse.yh`（解析与数量）、`convert.yh`（类型转换）、`write.yh`（结果写入）、
`commands.yh`（子命令/继承/组）、`layer.yh`（分层解析与模式）、
`extensions.yh`（回调与注册表）、`files.yh`（参数文件）、
`help.yh`（帮助/诊断/输出）、`entry.yh`（argc/argv 与退出码）。
分配点按 API 契约显式声明，不改变现有基础模块的所有权约定；
`os` 增加了 `is_terminal` 以支持帮助的自动颜色策略。

## toml（2026-10-23 设计；T0–T5 reader 已实现）

`libs/toml/` 以 `import toml;` 提供完整 TOML 1.1 reader：内存/文件解析、
`Document` 独占文档存储、`Value` 只读句柄、按字节长度的 `Text`、类型化查询
和结构化诊断；不依赖 compiler/gen，不修改 yh 语法。写入后置。

已注册模块并在 `libs/project.toml` 登记。实际文件按编译顺序：
`00_types.yh`（公开类型/预算）、`10_storage.yh`（私有池/节点/容器）、
`20_utf8.yh`、`30_numbers.yh`（整数与精确 binary64）、`40_datetime.yh`、
`45_parser_state.yh`、`46_strings.yh`、`50_parse.yh`（文档/键/表语义）、
`60_query.yh`、`70_files.linux.yh`/`70_files.darwin.yh`、`90_api.yh`。

固定 toml-test v2.2.0 的 1.1 decoder 清单通过 681/681（有效 214、非法 467），
六组 `.yh` API/所有权/资源/文件用例与 `make test`/`make selfhost-native`
本平台通过；另通过 124 个池分配失败点、低预算强制失败和 `make install`
后仓库外导入。剩余项：编译器清单迁移（T6）、writer（T7），以及发布资产是否
携带标准库（T5.2，另行决定）。现有 `compiler/cmd/toml.yh` 仍是旧清单
子集，尚未迁移。API、限制与生命周期见
[libs/toml/README.md](../../libs/toml/README.md)，取舍见
[ADR-0017](../adr/0017-yh-TOML标准库独立文档模型.md)。

## json（2026-10-24 设计；首期已实现）

规划中的 `libs/json/` 提供 RFC 8259 读写：`parse`/`parse_text`/`read_file` +
`Document`/`Value` 只读句柄（形状与 `toml` 对齐），以及 builder 式写出
（`begin_object`/`key`/`write_string`/`encode`/`encode_owned`）。与 `toml`
的差异：JSON 只有一个 number 类型，因此用单一 `kind_number` 并**原样保存
词素**，由 `as_i64`/`as_f64`/`is_integer` 在取值时显式询问；文档模型两库各自
独立，只把十进制 ↔ binary64 转换抽到 `libs/num` 共用。严格 profile 拒绝
BOM、重复键、孤立代理、尾逗号与尾随内容。设计见
[yh-JSON标准库设计](yh-JSON标准库设计-2026-10-24.md)，分期见
[实施方案](../02-plan/yh-JSON标准库实施方案-2026-10-24.md)，取舍见
[ADR-0019](../adr/0019-yh-JSON标准库独立文档模型与词素保真数字.md)。
状态：**首期已实现**（reader + writer + 查询 + 文件读写），已在
`libs/project.toml` 注册；`tests/json/run.py` 六组断言通过，`make test-json`
可用。未完成项（一致性语料、注入门、安装门）见
[todo](../todo.md)。

## testing（2026-10-23 首期完成）

`libs/testing/` 是 `yh test` 的最小运行时辅助模块，只提供
`fail(message *char) void` 与 `skip(reason *char) void`。两者都向 fd 3 写测试
记录并立即 `exit`，父进程据此判定 FAIL / SKIP；基本断言仍用编译器内建的
`$assert(cond[, msg])`，不需要导入本模块。只依赖 prelude 的 `write`/`exit`，
避免与 `os`/`io` 形成依赖环。见[`libs/testing/README.md`](../../libs/testing/README.md)。

## fmt 与 V 风格字符串插值（2026-10-23 设计；未实施）

`libs/fmt/` 规划为 V 风格字符串插值的运行时：`Value`、构造器、
`append_text`/`append_value`、`render` 与 print/sprint。语言层插值
`"…${expr:spec}…"` 由编译器实现，结果类型为 `string.String`；首版不实现
Go 的 `%` 格式串与 `Printf` 族。语言没有 `any`/接口/反射，插值只支持
整数、`f64`、`bool`、`*char`/`string.View` 等标量文本类型，复合值不自动
格式化。首版限制、spec 子集与错误语义见
[字符串插值设计](yh-字符串插值设计-2026-10-23.md)；运行时 API 见
[fmt 标准库设计](yh-fmt标准库设计-2026-10-23.md)；R0–R3/I0–I5 分期见
[实施方案](../02-plan/yh-fmt标准库实施方案-2026-10-23.md)。当前状态是规划，
`libs/fmt/` 尚未创建，编译器插值尚未实现。

## 当前边界

当前基础层不定义完整文件句柄、错误类型、缓冲策略、Unicode 处理或跨平台 ABI；
通用格式化由上述规划的 V 风格插值与 `fmt` 运行时承接，尚未实现。库源码
跨平台验收不在本阶段范围内；后续 API 按实际需求追加设计和 `.yh` 项目测试。
