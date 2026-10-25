# YT4-P5：os/sys/time 测试迁移（2026-10-25）

## 范围

把 `tests/modules/projects/sysresult` 的纯模型断言迁入 `libs/sys/99_tests.yh`；
为 `libs/os` 与 `libs/time` 补自己的测试：
`libs/os/99_tests.yh`（结果模型/选项默认值/errno 分类）、
`libs/time/99_tests.yh`（单调时钟可读且不倒退）。

保留：

- `libs/os/test/main.yh` 与 `libs/os/test/run.py`：真实文件/目录/进程 E2E
  与 Linux 目标类型检查（`make libs-test` 调用）。
- `tests/modules/projects/{osmodel,osio}`：公开面/结果模型 smoke。
- Linux 专属 11 个 fixture（sysraw/sysfiles/osfiles/syseintr/sysprocess/
  osprocess/systime/sysmemory/sysdirs/osdirs/osenv）与 `tests/modules` 的
  Linux 用例。

## 断言对照表

| 旧来源 | 覆盖点 | 新位置 |
| --- | --- | --- |
| `sysresult` | `Timespec` 16 字节与字段偏移；`is_error` 区间边界；`error_code` 提取 | `libs/sys/99_tests.yh`（2 test） |
| `libs/os` 公开模型（既有 fixture 间接覆盖） | `no_error`/`make_error`、`fd_ok`/`fd_error`、`io_ok`/`io_error`、`read_options`/`write_options` 默认值、`make_dir_entry` 空/非空视图、`error_from_errno` 分类与原生错误号 | `libs/os/99_tests.yh`（4 test） |
| `libs/time` | `monotonic_ns` 非负且连续读取不倒退 | `libs/time/99_tests.yh`（1 test） |

说明：

- 断言只调 pub API；`libs/os/99_tests.yh` 的 errno 映射用测试专用
  `import sys` 取当前平台常量，避免硬编码 Linux/Darwin 数值。
- `sysresult` fixture 与 `build-check.py` 的 `os0-sys-result-model` 删除；
  `OS_LINUX_CASES` 不变。
- `os` 的文件/目录/进程/环境用例不迁入：需要真实环境与清理顺序，仍由
  `libs/os/test/run.py` 与 `tests/modules` 的 Linux 用例承担。

## 验证

| 项 | 结果 |
| --- | --- |
| `cd libs && yh test sys` / `os` / `time` | 2 / 4 / 1 passed |
| `make libs-test` | **116 passed** + cli 5/5 + os 11/11+1/1 + libc 2/2 |
| `make libs-test-o2` | **116 passed** |
| `make test` | **61.6s** |
| `make selfhost-native` | **148.8s，project cases 123/123**（LA3 已由并发会话收口） |
