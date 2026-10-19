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
| `print(text *char) int` | 将 NUL 结尾字符串写到标准输出，不追加换行；成功返回 0，失败返回 -1 |
| `println(text *char) int` | 写字符串并追加一个换行；成功返回 0，失败返回 -1 |

`io` 通过现有 prelude 的 `write` 与 `strlen` 实现。

### `memory`

| API | 契约 |
| --- | --- |
| `alloc(byte_count u64) *void` | 显式申请指定字节数；失败返回空指针 |
| `release(data *void) void` | 释放 `alloc` 返回的内存；空指针可传入 |
| `copy(destination *void, source *void, byte_count u64) *void` | 复制指定字节数并返回目标地址 |

本模块只包装现有 yh 运行时分配与复制入口；所有权由调用方管理，不引入隐式分配。

### `string`

| API | 契约 |
| --- | --- |
| `length(text *char) u64` | 返回 NUL 结尾字符串的 UTF-8 字节数 |
| `equals(left *char, right *char) int` | 内容相等返回 1，否则返回 0 |
| `compare(left *char, right *char) int` | 按无符号字节序返回 -1、0 或 1 |

字符串 API 操作 NUL 结尾字节串，不做 Unicode 码点解码。

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

这些函数沿用宿主接口的返回值和标志，不会把平台常量伪装成跨平台抽象。

### `math`

提供 `sqrt_f64(value f64) f64`、`sin_f64(value f64) f64`、
`cos_f64(value f64) f64`、`pow_f64(base f64, exponent f64) f64` 四个函数，
转发到固定参数的宿主 C 数学符号。它不声明 libc 变参，也不保证其他平台存在
相同 ABI。

### `time`

提供 `monotonic_ns() i64`，返回单调时钟纳秒数；底层调用失败返回 -1。当前实现
使用 Darwin 的 `CLOCK_MONOTONIC` 编号与 `clock_gettime`。

## sys（2026-10-03 规划，尚未实现）

用户指定系统调用封装放在 `libs/sys/`；模块入口见
[README](../../libs/sys/README.md)，完整契约与分期见
[sys 设计](yh-sys系统调用封装设计.md)和
[实施方案](../02-plan/yh-sys系统调用封装实施方案.md)。

首期 Linux/arm64 复用 `linux_syscall6`，提供 raw6、显式错误结果及文件/目录、
内存/时间、进程原语；sys 不分配、不自动重试，结果保留 `-errno`。后续
os/io/time 消费 sys 并保留既有上层返回约定，编译器采用显式项目依赖。
macOS/arm64 后续适配审核的系统 OS API，披露 dyld/libSystem 依赖。

当前该目录仅有规划 README，清单预留项不代表模块已可使用；未迁移本文已有 API。
静态 ELF、启动入口和连续自编须与自有工具链共同验收。

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

## 当前边界

当前基础层不定义完整文件句柄、错误类型、缓冲策略、Unicode 处理、通用格式化或
跨平台 ABI。库源码跨平台验收不在本阶段范围内；后续 API 按实际需求追加设计和
`.yh` 项目测试。
