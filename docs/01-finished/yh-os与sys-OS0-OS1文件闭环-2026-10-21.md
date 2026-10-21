# yh os/sys OS0 与 OS1 文件闭环首片

日期：2026-10-21。状态：**OS0 完成；OS1 文件闭环首片实现**。
OS1 的短写/EINTR/CLI 收尾见[OS1 收尾记录](yh-os与sys-OS1收尾-2026-10-21.md)；
OS2/OS3 见后续完成记录，OS4–OS8 未实施。

依据：[os/sys 联合设计](../03-design/yh-os与sys标准库设计.md)、
[联合实施方案](../02-plan/yh-os与sys标准库实施方案.md)、
[ADR-0015](../adr/0015-yh-os与sys标准库分层.md)。

## 1. 交付内容

### sys（Linux 直接系统调用层）

| 文件 | 内容 |
| --- | --- |
| `libs/sys/00_types.yh` | `Timespec`（16 字节，sec/nsec 偏移 0/8）、`is_error`、`error_code` |
| `libs/sys/10_constants.linux.arm64.yh` | AArch64 NR_*、O_*、AT_*、errno；`O_DIRECTORY = 0x4000` |
| `libs/sys/10_constants.linux.x64.yh` | x86_64 NR_*、O_*、AT_*、errno；`O_DIRECTORY = 0x10000` |
| `libs/sys/20_raw.linux.yh` | `raw6` 转发现有 `linux_syscall6`，不经过 libc syscall |
| `libs/sys/30_file.linux.yh` | open_at、read_fd、write_fd、close_fd、create_dir_at、remove_at、rename_at |

约定：错误区间仅 `[-4095, -1]`；每次调用一次内核调用，允许短读写，close 不重试；
不改写进程全局 errno；调用号与标志按 ISA 分开维护。

### os（应用层）

| 文件 | 内容 |
| --- | --- |
| `libs/os/00_model.yh` | `ErrorKind`、`Error`、`FdResult`、`IoResult`、`AccessKind`、`OpenOptions`、`DirKind`、`DirEntry` 及初始化函数（DirEntry 在 OS2 改为 `name *u8 + name_len u64`） |
| `libs/os/file.linux.yh` | `open_path`、`read_some`、`write_some`、`close_file`、`make_dir`、`remove_path`、`remove_dir_path`、`rename_path` |

约定：新打开默认 `O_CLOEXEC`；只读与 truncate/append 组合、exclusive 缺少 create
返回 `error_invalid_argument` 且 `native_code = 0`；ENOENT/EEXIST/EACCES/EPERM/
EINTR/EINVAL/ENOSYS 归一化为稳定分类；旧 `open_file/read_fd/write_fd/close_fd/...`
仍返回 -1 与宿主标志。

### 命名偏差

设计图纸中的 `open/read/write/close/mkdir/rmdir/remove/rename` 与编译器 prelude
同名，模块内定义会被判为顶层符号重定义，因此实际使用
`open_path/read_some/write_some/close_file/make_dir/remove_dir_path/remove_path/
rename_path`。语义与所有权不变，旧接口未迁移。

### 测试

| 用例 | 平台 | 覆盖 |
| --- | --- | --- |
| `tests/modules/projects/sysresult` | Darwin + Linux | Timespec 布局、-1/-4095/-4096 边界、error_code |
| `tests/modules/projects/osmodel` | Darwin + Linux | 跨模块 Error/FdResult/IoResult/OpenOptions、[]u8 借用、DirEntry |
| `tests/modules/projects/sysraw` | Linux | raw6 getpid、函数值间接调用、EBADF、ENOSYS |
| `tests/modules/projects/sysfiles` | Linux | 创建/写/读/EOF/EEXIST/ENOENT/EBADF/目录/重命名/删除 |
| `tests/modules/projects/osfiles` | Linux | OpenOptions、错误分类、追加、零字节、目录、旧 API 兼容 |

Linux 专属用例只在 `sys.platform == "linux"` 时注册到 `build-check.py`，非 Linux
宿主不计为通过；测试文件在 fixture 工作目录内创建并在开始/结束清理。

## 2. 验证记录

```sh
make
make test
python3 tests/modules/build-check.py --compiler-path ./yh --backend llvm --jobs 4
```

- Darwin/arm64：`make` 冷编、`make test` 全绿（run 208/209 + 1 跳过，fail 132/132，
  pass 8/8，代码统计 6/6）。
- Darwin/arm64：新增 `os0-sys-result-model`、`os0-os-result-model` 通过。
- Apple Container `debian:trixie`（Linux/arm64，入库种子）：五个 fixture
  `sysresult/osmodel/sysraw/sysfiles/osfiles` 全部退出 0。容器内需要
  `libxml2`、`build-essential`，并用 `gcc-14` 兼容链接到种子内嵌的 gcc-13 路径；
  这些只是本轮验证设备，不进入库或产品依赖。
- `yh -target x86_64-unknown-linux-gnu check`：`sysraw`、`sysfiles`、`osfiles`
  语义检查通过；本轮没有 Linux/x64 原生运行环境，未宣称该平台运行通过。
- 完整 `build-check --backend llvm` 的 C 互操作项因本机 SDK 27 TAPI 与 `-lm`
  缺失失败，属于既有环境问题，与本阶段库改动无关。
- 未运行 `make selfhost-native` 的全部收尾项，未执行 `make seed`，种子未改动。

## 3. 未关闭项

1. OS1：稳定可重复的短写与 EINTR 注入用例（需测试专用驱动，不向公开 API
   添加测试开关）；CLI 重新验收；Linux/x64 原生运行门。
2. OS2：getdents64/open_dir/next_entry/close_dir、get_cwd/change_dir 与
   `DirEntry` 实际读取器。
3. OS3 环境查询已在后续切片完成；OS4–OS8（进程、io/time 收敛、加载体验、
   编译器迁移与 Darwin 桥）仍待实施。
4. 标准库默认发现/安装布局仍是独立待办；当前需 `YH_STDLIB` 或显式项目依赖。

## 4. 影响面

- 未修改语言语法、`docs/yh.g4`、编译器 generate/parse 语义、默认后端或种子。
- `libs/os/os.yh`、`libs/io/io.yh`、`libs/time/time.yh` 未改动；旧行为由现有
  `libsbase/libsio` 用例继续覆盖。
- `libs/sys/README.md`、联合设计/方案、sys 设计/方案、todo、finish 已同步到
  当前实现状态，避免把规划写成已实现。
