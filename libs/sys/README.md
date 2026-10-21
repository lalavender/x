# sys 标准库：Linux 系统调用封装

日期：2026-10-21。状态：**OS0–OS6 完成；文件/目录/进程/内存/时间 sys 原语
与默认标准库发现已实现**（OS7–OS8 未实施）。

分层与交付顺序见[联合设计](../../docs/03-design/yh-os与sys标准库设计.md)和
[联合实施方案](../../docs/02-plan/yh-os与sys标准库实施方案.md)；底层 ABI 细节见
[系统调用封装设计](../../docs/03-design/yh-sys系统调用封装设计.md)。

## 当前实现

```text
libs/sys/
  00_types.yh                  Timespec、is_error、error_code
  10_constants.linux.arm64.yh  AArch64 调用号、O_*、AT_*、errno
  10_constants.linux.x64.yh    x86_64 调用号、O_*、AT_*、errno
  20_raw.linux.yh              raw6 → linux_syscall6
  30_file.linux.yh             open_at/read_fd/write_fd/close_fd/
                               create_dir_at/remove_at/rename_at/
                               getdents64/get_cwd/change_dir/create_pipe
  40_memory.linux.yh           map_memory/unmap_memory
  50_time.linux.yh             read_clock/sleep_time
  60_process.linux.yh          process_id/fork_process/execute/
                               wait_process/exit_process/send_signal
```

- 每个文件声明 `module sys;`，沿用 `libs/project.toml` 的 `source = "."` 与
  目录模块发现规则；数字前缀保证类型、常量和底层函数先于消费者编译。
- Linux 具名原语返回内核原始成功值或 `-errno`；只有 `[-4095, -1]` 是错误区间。
  `read_fd/write_fd` 各调用一次并允许短读写，`close_fd` 不重试。
- 调用号、`O_*` 与 errno 按 ISA 分开维护；AArch64 的 `O_DIRECTORY` 是 `0x4000`，
  x86_64 是 `0x10000`，不能跨目标复制。
- `getdents64` 返回原始目录记录，记录布局、名称边界与 DT_UNKNOWN 由 os 读取器
  处理；`get_cwd` 成功时包含结尾 NUL，空间不足保留 `-ERANGE`；`change_dir`
  修改进程全局当前目录。
- `create_pipe` 使用 pipe2，输出两个连续 int；`O_NONBLOCK`/`EAGAIN` 供短写与
  进程握手使用。
- `fork_process` 使用 SIGCHLD、空子栈、无 CLONE_VM 的 clone；`execute` 精确
  execve；`wait_process` 返回原始 wait4 状态；`exit_process` 使用 exit_group；
  `send_signal` 使用 kill。os.spawn 的错误管道握手在 os 层。
- `map_memory/unmap_memory` 直接 mmap/munmap；成功值先经 is_error 判定再转指针。
  `read_clock/sleep_time` 填入 Timespec；nanosleep 不自动重试。
- `Timespec` 与 `is_error/error_code` 是跨平台文件；在 Darwin 上只有这部分可用，
  Linux 专属文件不会被选中，也不提供返回伪成功的空桩。

## 使用

```yh
import sys;

let fd i64 = sys.open_at(sys.AT_FDCWD, "/tmp/a",
    sys.O_WRONLY | sys.O_CREAT | sys.O_TRUNC | sys.O_CLOEXEC, 420);
if (sys.is_error(fd) != 0) {
    let code int = sys.error_code(fd);
}
```

普通应用优先使用 `os` 的新文件接口（`open_path/read_some/write_some/...`），
由 os 负责错误分类、打开选项和资源约定；需要原始内核结果时直接导入 sys。

## 未实施

内存映射、时间、Darwin 原生桥与编译器迁移仍按
OS5–OS8 单列；旧 os/io/time 接口保持原契约。当前标准库仍需 `YH_STDLIB`
或显式项目依赖加载。
