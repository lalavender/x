# sys 标准库：Linux 系统调用封装

日期：2026-10-21。状态：**OS0–OS6 完成；文件/目录/进程/内存/时间 sys 原语
与默认标准库发现已实现**（OS7–OS8 未实施）。

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
- `execute`：精确路径 execve，不搜索 PATH、不经过 shell。
- `wait_process`：返回原始 wait4 状态；正常/信号/错误由 os.wait 解码。
- `create_pipe(output, flags)`：pipe2，输出两个连续 int，成功后才可读取。
- `send_signal`：kill。

## 常量与平台

- 调用号、`O_*`、errno 按 ISA 分开维护。AArch64 `O_DIRECTORY = 0x4000`，
  x86_64 `O_DIRECTORY = 0x10000`，不能跨目标复制。
- `Timespec`、`is_error`、`error_code` 跨平台；其余 Linux 专属。
  Darwin 不会选中 Linux 文件，也不提供伪成功空桩。

## 实现文件

```text
libs/sys/
  00_types.yh                  Timespec、is_error、error_code
  10_constants.linux.arm64.yh  AArch64 调用号、O_*、AT_*、errno
  10_constants.linux.x64.yh    x86_64 调用号、O_*、AT_*、errno
  20_raw.linux.yh              raw6 → linux_syscall6
  30_file.linux.yh             文件/目录/cwd/pipe2
  40_memory.linux.yh           mmap/munmap
  50_time.linux.yh             clock_gettime/nanosleep
  60_process.linux.yh          PID/fork/exec/wait/exit/signal
  doc.yh                       仅注释的完整 API 参考
```

## 未实施

Darwin 原生桥、duplicate_fd/fd_flags、编译器迁移（OS7/OS8）仍待后续；
旧 os/io/time 接口保持原契约。
