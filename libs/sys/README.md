# sys 标准库：Linux 系统调用与 Darwin libSystem 封装

日期：2026-10-22。状态：**OS0–OS8 完成**：Linux 走原始 syscall，Darwin 走
libSystem 桥；文件/目录/进程/内存/时间原语与默认标准库发现均已实现
（OS7 编译器迁移仍未实施）。

- 完整 API 清单与契约：[doc.yh](doc.yh)
- 分层与交付顺序：[联合设计](../../docs/03-design/yh-os与sys标准库设计.md)、
  [联合实施方案](../../docs/02-plan/yh-os与sys标准库实施方案.md)
- 底层 ABI 细节：[系统调用封装设计](../../docs/03-design/yh-sys系统调用封装设计.md)

## 加载

三种方式，优先级从高到低：

```sh
# 1. 显式项目依赖（推荐给编译器/工具链）
#    project.toml:
#      [dependencies]
#      yh_libs = { path = "../libs" }
#    main.yh:
#      import yh_libs.sys as sys;

# 2. 显式 YH_STDLIB
YH_STDLIB=$PWD/libs ./yh run

# 3. 默认发现（仓库根 yh + libs/，或安装前缀 share/yh/libs）
./yh run
```

普通应用优先使用 [os 标准库](../os/README.md)；需要原始内核结果、短读写或
自己管理错误号时直接导入 `sys`。

## 错误约定

```yh
import sys;

let result i64 = sys.open_at(sys.AT_FDCWD, "/missing",
    sys.O_RDONLY | sys.O_CLOEXEC, 0);
if (sys.is_error(result) != 0) {
    let code int = sys.error_code(result); // ENOENT=2
}
```

- 成功返回内核原始值；失败返回 `-errno`，不设置全局 errno。
- 只有 `[-4095, -1]` 是错误区间，必须用 `sys.is_error`。
- `read_fd`/`write_fd` 各执行一次，允许短读写；`close_fd` 不重试。
- sys 不分配、不格式化、不遍历目录、不解释 wait 状态。

## 文件

```yh
import sys;

let path *char = "/tmp/yh-sys-demo";
let fd i64 = sys.open_at(sys.AT_FDCWD, path,
    sys.O_WRONLY | sys.O_CREAT | sys.O_TRUNC | sys.O_CLOEXEC, 420);
if (sys.is_error(fd) == 0) {
    let data [4]u8 = [65, 66, 67, 10];
    sys.write_fd(fd.to_type(int), (&data[0]).to_type(*void), 4);
    sys.close_fd(fd.to_type(int));
}

let reader_fd i64 = sys.open_at(sys.AT_FDCWD, path,
    sys.O_RDONLY | sys.O_CLOEXEC, 0);
if (sys.is_error(reader_fd) == 0) {
    let buffer [16]u8;
    let n i64 = sys.read_fd(reader_fd.to_type(int),
        (&buffer[0]).to_type(*void), 16);
    // n == 4；再次读取返回 0（EOF）
    sys.close_fd(reader_fd.to_type(int));
}
```

相关原语：`open_at`、`read_fd`、`write_fd`、`close_fd`、`create_dir_at`、
`remove_at`、`rename_at`（renameat2，flags=0）。

## 目录与 cwd

- `getdents64` 只返回原始 linux_dirent64 记录；记录长度、名称 NUL 与
  `DT_UNKNOWN` 由 [os 目录读取器](../os/README.md) 解析。
- `get_cwd(buffer, capacity)` 成功返回**含 NUL** 的总字节数；空间不足
  `-ERANGE`。
- `change_dir` 修改整个进程的当前目录。

```yh
let cwd [256]u8;
let n i64 = sys.get_cwd((&cwd[0]).to_type(*char), 256);
if (n > 0 && cwd[(n - 1).to_type(int)] == 0) {
    // cwd 以 NUL 结尾；n-1 是有效路径长度
}
```

## 时间

```yh
let stamp sys.Timespec;
if (sys.read_clock(sys.CLOCK_MONOTONIC, &stamp) == 0) {
    let ns i64 = stamp.sec * 1000000000 + stamp.nsec;
}

let request sys.Timespec;
request.sec = 0;
request.nsec = 1000000; // 1ms
sys.sleep_time(&request, 0);
```

- `Timespec` 固定 16 字节，`sec`/`nsec` 为 i64。
- `read_clock` 失败返回 `-errno`；`sleep_time` 被中断返回 `-EINTR`，
  不自动重试。

## 内存映射

```yh
let mapped i64 = sys.map_memory(0, 8192,
    sys.PROT_READ | sys.PROT_WRITE,
    sys.MAP_PRIVATE | sys.MAP_ANONYMOUS, -1, 0);
if (sys.is_error(mapped) == 0) {
    let memory *u8 = mapped.to_type(*u8);
    memory[0] = 65;
    sys.unmap_memory(memory.to_type(*void), 8192);
}
```

必须先用 `is_error` 判断，再把完整 64 位成功值转指针；不能以空指针或任意
负 i64 作为 mmap 失败判定。

## 进程

```yh
let pid i64 = sys.fork_process();
if (pid == 0) {
    sys.exit_process(7); // 子进程
}
if (pid > 0) {
    let status int = 0;
    let waited i64 = sys.wait_process(pid.to_type(int), &status, 0);
    let exit_code int = (status >> 8) & 0xff;
}
```

- `fork_process`：SIGCHLD + 空子栈 + 无 CLONE_VM；父得 PID，子得 0。
  Darwin 直接用 libSystem `fork`。
- `execute`：精确路径 execve，不搜索 PATH、不经过 shell。
- `spawn_process(path, argv, envp, pid)`（Darwin）：`posix_spawn` 一次完成
  fork+exec，成功返回 0 并写 pid，失败返回 `-errno` 且不创建子进程。
- `wait_process`：返回原始 wait4 状态；正常/信号/错误由 os.wait 解码。
- `create_pipe(output, flags)`：Linux 用 pipe2；Darwin 只有无标志 `pipe`，
  带 `O_CLOEXEC`/`O_NONBLOCK` 的请求返回 `-ENOSYS`（见下节限制）。
- `send_signal`：kill。

## 网络（NET0，2026-10-24）

sys 只提供「一次调用、返回内核结果或 `-errno`」的 socket 原语；地址构造、
超时归一化、DNS 与 HTTP 都在 [net](../net/README.md) 与 http 层。

```yh
// 环回监听 + 读回内核分配的端口（完整用例见
// tests/modules/projects/netsys/main.yh）。
let listener i64 = sys.socket_fd(sys.AF_INET, sys.SOCK_STREAM, sys.IPPROTO_TCP);
if (sys.is_error(listener) == 0) {
    let enable int = 1;
    sys.set_socket_option(listener.to_type(int), sys.SOL_SOCKET,
        sys.SO_REUSEADDR, (&enable).to_type(*void), 4);
    // sockaddr 由 net 层按平台布局填写；sys 只接收指针与长度。
    sys.bind_fd(listener.to_type(int), addr, 16);
    sys.listen_fd(listener.to_type(int), 8);
}
```

- 结构：`PollFd`（8 字节）与 `Timeval`（16 字节）在 `base.yh`。
- 原语：`socket_fd`、`connect_fd`、`bind_fd`、`listen_fd`、`accept_fd`、
  `get_socket_name`、`shutdown_fd`、`set_socket_option`、
  `get_socket_option`、`send_fd`、`recv_fd`、`poll_fds`。
- `poll_fds` 的 `timeout_ms`：负数无限等待、0 只探测；Linux 走 ppoll。
- `fcntl_fd` 仅 Linux，用于 net 的非阻塞 connect；Darwin 没有等价入口。
- SIGPIPE：Linux 用 `send_fd` 的 `MSG_NOSIGNAL`，Darwin 用
  `SO_NOSIGPIPE` 选项（net 在连接建立后设置），不安装全局信号处理器。

## 常量与平台

- Linux 调用号、`O_*`、errno 按 ISA 分开维护。AArch64
  `O_DIRECTORY = 0x4000`，x86_64 `O_DIRECTORY = 0x10000`，不能跨目标复制。
- Darwin 常量来自 macOS SDK：`AT_FDCWD = -2`、`O_DIRECTORY = 0x100000`、
  `O_CLOEXEC = 0x1000000`、`CLOCK_MONOTONIC = 6`、`ENOSYS = 78` 等，
  不能与 Linux 数值混用。
- `Timespec`、`is_error`、`error_code` 跨平台。Darwin 桥把 libSystem 的
  “返回 -1 + 线程 errno”归一化为 `-errno`，调用方判断方式不变。

### Darwin 桥的限制（明确失败，不假装成功）

- `open_at` 只支持 `AT_FDCWD`（os 文件的唯一调用形式），其他目录 fd 返回
  `-ENOSYS`。原因是 Darwin 的 `openat` 是 C 变参入口，mode 必须经变参栈
  传递，而 C ABI v1 的 extern 声明只能是固定参数。
- `create_pipe` 的 `flags != 0` 返回 `-ENOSYS`：同一原因，`fcntl` 的第三个
  实参也是变参。os 的 Darwin `spawn` 因此改用 `posix_spawn`，不依赖管道。
- 目录读取走 `getattrlistbulk`：每批返回若干条目组，组内布局由 os 解析；
  缓冲不足一条记录时返回 `-ERANGE`（os 归一化为 `error_invalid_argument`）。
- 网络原语不提供改阻塞模式的入口：Darwin 的 `fcntl`/`ioctl` 同样是 C 变参，
  所以 net 在 Darwin 上只能用阻塞 `connect`（连接阶段超时不生效，读写超时
  仍可用 `SO_RCVTIMEO`/`SO_SNDTIMEO`）；Linux 通过 `fcntl_fd` 支持
  非阻塞 connect + poll + `SO_ERROR`。

## 实现文件

```text
libs/sys/
  base.yh                  Timespec、is_error、error_code
  errno.darwin.yh          __error 读取与 -errno 归一化
  constants.linux.arm64.yh AArch64 调用号、O_*、AT_*、errno
  constants.linux.x64.yh   x86_64 调用号、O_*、AT_*、errno
  constants.darwin.yh      Darwin O_*、AT_*、errno、映射/时钟、attrlist 位
  raw.linux.yh             raw6 → linux_syscall6
  file.linux.yh            文件/目录/cwd/pipe2
  file.darwin.yh           文件/目录/cwd/pipe/getattrlistbulk 桥
  memory.linux.yh          mmap/munmap（系统调用）
  memory.darwin.yh         mmap/munmap（libSystem）
  time.linux.yh            clock_gettime/nanosleep（系统调用）
  time.darwin.yh           clock_gettime/nanosleep（libSystem）
  process.linux.yh         PID/fork/exec/wait/exit/signal（系统调用）
  process.darwin.yh        PID/fork/exec/wait/exit/signal/posix_spawn
  socket.linux.yh          socket/connect/bind/listen/accept/poll（系统调用）
  socket.darwin.yh         同一组原语的 libSystem 桥
  doc.yh                   仅注释的完整 API 参考
```

## 未实施

duplicate_fd/fd_flags 与编译器迁移（OS7）仍待后续；旧 os/io/time 接口
保持原契约。Darwin 的变参入口（openat/fcntl 第三实参）要等 C ABI 支持
变参后再补齐，当前按上面的限制显式报错。网络的上层（net 的
`Endpoint`/TCP 封装、http 的消息模型与两端）按
[HTTP 标准库设计](../../docs/03-design/yh-http标准库设计.md) 的
M1–M7 推进，本层只到 NET0。
