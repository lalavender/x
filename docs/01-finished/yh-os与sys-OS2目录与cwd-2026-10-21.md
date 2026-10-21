# yh os/sys OS2 目录与 cwd

日期：2026-10-21。状态：**OS2 完成**（Linux；Darwin 新目录 API 未接入）。

依据：[os/sys 联合设计](../03-design/yh-os与sys标准库设计.md)、
[联合实施方案](../02-plan/yh-os与sys标准库实施方案.md)。

## 1. 交付内容

### sys

`libs/sys/30_file.linux.yh` 新增：

| API | 内核映射 | 语义 |
| --- | --- | --- |
| `getdents64(fd, buffer *void, count u64) i64` | getdents64 61/217 | 返回原始目录记录字节数，0 为结束 |
| `get_cwd(buffer *char, capacity u64) i64` | getcwd 17/79 | 成功返回含 NUL 的总字节数，空间不足 -ERANGE |
| `change_dir(path *char) i64` | chdir 49/80 | 修改进程全局当前目录 |

两种 ISA 的常量文件补齐 `NR_GETDENTS64/NR_GETCWD/NR_CHDIR` 与
`ENOTDIR/ERANGE`；`O_DIRECTORY` 继续按 ISA 分开（AArch64 0x4000，x86_64 0x10000）。

### os

| 文件 | 内容 |
| --- | --- |
| `libs/os/10_errors.linux.yh` | 从 file.linux 提取的私有 error_kind_for/error_from_native/error_from_result/io_from_result/slice_address；补 ERANGE → invalid_argument |
| `libs/os/20_directory.linux.yh` | DirEntryStatus、DirReader、DirReaderResult、DirEntryResult、open_dir、next_entry、close_dir、get_cwd、change_dir |
| `libs/os/00_model.yh` | DirEntry 改为 `name *u8 + name_len u64`，make_dir_entry 由切片构造借用视图 |

契约：

- 目录读取使用调用方字节缓冲；DirReader 保存 fd、缓冲、已用字节与游标，
  不整目录分配。
- next_entry 区分条目/结束/失败，跳过 `.`/`..`，顺序不保证；DT_UNKNOWN 保留
  unknown，不当作普通文件。
- 名称借用读取器缓冲，只保证到下一次 next_entry 或 close_dir。
- 损坏记录（长度越界、缺少 NUL）返回 error_other 且停止解析，避免越界。
- close_dir 重复调用幂等；关闭后 next_entry 返回 invalid_argument。
- get_cwd 成功写入 NUL，IoResult.count 不含 NUL；空缓冲/空间不足返回
  invalid_argument，原生 ERANGE 保留在 native_code；change_dir 修改进程全局 cwd。

### 命名/布局偏差

`DirEntry` 原设计使用 `name []u8`，但当前语言只支持数组→切片和切片取子范围，
不支持从裸指针+长度构造切片；目录名称来自读取器缓冲内部，不能复制到临时数组。
因此改为 `name *u8 + name_len u64`，仍是借用视图；`make_dir_entry(name []u8, ...)`
保留切片入口供调用方测试。

## 2. 测试

| 用例 | 平台 | 覆盖 |
| --- | --- | --- |
| `tests/modules/projects/sysdirs` | Linux | getdents64 多记录解析、名称 NUL、DT 类型、EOF、bad fd、ENOTDIR、get_cwd NUL/ERANGE、change_dir 恢复与 ENOENT |
| `tests/modules/projects/osdirs` | Linux | 64 字节缓冲多批读取、100 字节长名称、空目录、损坏记录、DT_UNKNOWN、重复关闭、零值读取器不误关 stdin、关闭后读取、cwd 往返/空间不足/缺失路径 |

两个用例都接入 `tests/modules/build-check.py` 的 Linux 专属列表；非 Linux 宿主
不注册、不把 SKIP 计为通过。fixture 在开始与结束时清理文件、子目录与目录。

## 3. 验证记录

```sh
make
make test
yh -target x86_64-unknown-linux-gnu check   # sysdirs/osdirs
```

- Darwin/arm64：`make`、`make test` 通过；`osmodel` 在 DirEntry 布局调整后
  原生运行通过。
- Apple Container `debian:trixie`（Linux/arm64，入库种子）：一次运行
  `sysresult/osmodel/sysraw/sysfiles/osfiles/sysdirs/osdirs` 全部退出 0。
  容器内需 `libxml2`、`build-essential` 与 gcc-13 兼容符号链接，仅为本轮
  验证设备。
- Linux/x64：仅完成语义检查，未宣称原生运行；完整回归由 CI 承担。
- 未修改编译器语义、语法、种子或默认后端；未执行 `make seed`。

## 4. 未关闭/后续

- OS1 的强制短写/EINTR、CLI 重验与 Linux/x64 原生门仍待补。
- OS3–OS6 已在本日后续切片完成；OS7 编译器迁移、OS8 Darwin 新接口未实施。
- 目录读取的 DT_UNKNOWN 在编译器目录扫描中的策略仍随 OS7 迁移补齐；本阶段
  的 os 读取器只保留 unknown，不静默当文件。
