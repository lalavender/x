# yh os/sys OS5 io 与 time 收敛、内存/时间原语

日期：2026-10-21。状态：**OS5 完成**（Linux/arm64 原生；Linux/x64 由 CI 验收）。

依据：[os/sys 联合设计](../03-design/yh-os与sys标准库设计.md) 第 4/6 节、
[联合实施方案](../02-plan/yh-os与sys标准库实施方案.md) 第 8 节。

## 1. 交付内容

### sys

- `libs/sys/40_memory.linux.yh`：
  `map_memory(address, count, protection, flags, fd, offset) i64`（mmap）、
  `unmap_memory(address, count) i64`（munmap）。成功返回地址位型/0，失败 -errno。
- `libs/sys/50_time.linux.yh`：
  `read_clock(clock_id, output *Timespec) i64`（clock_gettime）、
  `sleep_time(request, remaining) i64`（nanosleep）。
- 常量：`PROT_READ/PROT_WRITE`、`MAP_PRIVATE/MAP_ANONYMOUS`、
  `CLOCK_REALTIME/CLOCK_MONOTONIC` 与两种 ISA 的调用号。

### os / time / io

- `libs/os/file.linux.yh` 新增 `write_once(fd, buffer *void, count u64) IoResult`；
  `write_some` 改为复用它。`libs/os/file.darwin.yh` 用 prelude write 提供同名
  Darwin 兼容入口，供 io 跨平台使用。
- `libs/os/40_sleep.linux.yh`：旧 `sleep_us` 转 sys.nanosleep，负值 -1、
  成功 0、错误 -1，保持旧契约；`40_sleep.darwin.yh` 保留宿主 usleep。
- `libs/time/time.linux.yh`：`monotonic_ns` 走 `sys.read_clock(CLOCK_MONOTONIC)`；
  `time.darwin.yh` 保留原 Darwin clock_gettime(6)。
- `libs/io/io.yh`：
  - 新增 `write_all_result(fd, data *char, byte_count int) os.IoResult`，
    循环处理短写并保留已写进度；遇 EINTR/EAGAIN/坏 fd 立即返回当前 count 与错误。
  - `write_all/print/println` 返回值与 EINTR 不重试契约不变。
  - 不再直接调用 prelude write，统一经 os.write_once。

## 2. 测试

| 用例 | 平台 | 覆盖 |
| --- | --- | --- |
| `tests/modules/projects/sysmemory` | Linux | 匿名 mmap、首尾/跨页写读、munmap、零长度 EINVAL |
| `tests/modules/projects/systime` | Linux | read_clock 两次不倒退、零睡眠、非法 nsec EINVAL、坏时钟号、time.monotonic_ns、sleep_us |
| `tests/modules/projects/osio` | 跨平台 | write_all_result 完整/零长度/坏 fd/负长度、旧 write_all 契约 |
| `tests/modules/projects/syseintr` | Linux | 追加 io.write_all_result 在非阻塞 socket 上保留 EAGAIN 前已写进度 |
| `libsbase/libsio` | 跨平台 | 旧 time/sleep/io/CLI 调用兼容 |

`sysmemory` 用 8192 字节映射覆盖多个常见页边界，不硬编码 4 KiB 页；文件偏移
mmap 仍未纳入首期测试。

## 3. 验证

```sh
make
make test
python3 libs/cli/test/run.py --compiler ./yh --quiet
```

- Darwin/arm64：`make`、`make test` 通过；libsbase/libsio 原生运行通过；
  CLI 9/9 通过（io 改经 os 后输出/退出码不变）。
- Apple Container `debian:trixie`（Linux/arm64，入库种子）：systime、
  sysmemory、osio、syseintr、libsbase 及既有 fixture 均退出 0。
- Linux/x64：systime/sysmemory/syseintr 语义检查通过；原生运行由 CI 承担，
  本轮未宣称。
- 未修改种子、未执行 `make seed`。

## 4. 未实施/后续

- 文件后端的非零页对齐偏移 mmap、页大小探测、分配器合并未进入首期。
- 新的通用 sleep API（time 层）未定义；`os.sleep_us` 旧契约保留。
- OS6 示例已在同日后继切片完成；OS7 编译器迁移、OS8 Darwin 新接口未实施。
- io 的 EINTR 策略保持“不重试”：write_all_result 返回 interrupted 与进度，
  需要重试的调用方自行决定。
