# yh-P0-emit-asm修复-2026-11-05

## 概述

修复 Windows 上 `yh -O0 --emit-asm <file.yh>` 报「内嵌 LLVM：目标文件原子
写入失败」的 P0 缺陷（todo.md CI 段唯一的功能性 P0）。对应实施方案
[yh-P0收尾与发布顺序实施方案](../02-plan/yh-P0收尾与发布顺序实施方案-2026-11-05.md)
的 Lane A（A1–A4 全部完成）。

## 取证与根因（与 todo 原判断的关键差异）

失败点**不在** `MoveFileExA/_open` 的对象发布四个点——那些点服务对象文件
发布，日常增量构建全在成功。`--emit-asm` 走 `out="-"` → `llvm_emit.yh`
先在 `%TEMP%` 拼临时路径 → 桥 `publish_buffer` 对该路径做 `yh_mkstemp`
（`_mktemp_s` + `_open(O_CREAT|O_EXCL)`）。

A2 诊断（bridge.c `publish_buffer` 各失败点带 errno/GetLastError，随
diagnostic 输出）定位：`[mkstemp 失败(返回=-1 errno=13)]`——`_mktemp_s`
成功、`_open` EACCES。

A1 探针矩阵（独立 clang-cl /MT 探针，与桥同旗标）分离变量：

| 目录 | `_open(O_CREAT\|O_EXCL)` |
|------|--------------------------|
| `%TEMP%`（简单名/双扩展名/无 EXCL） | **全部 EACCES (13)** |
| 仓库 `tmp/`（同旗标同 CRT） | 全部成功（fd=3） |

对照组：受信任的 python 写 `%TEMP%` 正常。**根因**：本机安全策略（沙箱层）
拒绝「不受信任的新编译 exe」在 `%TEMP%` 创建文件——目录级、进程信任级，
与文件名/旗标/CRT 无关。todo 中「TEMP 显式指向 AppData 仍失败」与此吻合。

## 修复

1. `compiler/build/llvm_emit.yh`：`--emit-asm` 临时目录顺序调整——
   **Windows 上当前目录优先**（仓库/项目目录始终可写），失败再退
   `TEMP/TMP`；POSIX 保持 `/tmp` 优先、当前目录兜底。文件名仍带 pid
   并发唯一，写完立即删除。
2. `compiler/llvm/bridge.c`：`publish_buffer` 全部失败点（stdout write /
   malloc / mkstemp / file write / close / MoveFileExA+GetLastError /
   rename）写入 `publish_detail`，失败时随 diagnostic 输出——本次根因
   定位即靠它，长期保留。

## 验收（A4）

- `yh -O0 --emit-asm examples/main.yh`：exit=0、**stderr 零字节**、汇编
  输出正常（`--emit-asm` 曾需要 TEMP 重试时 stderr 会有噪音，调整顺序后
  正常路径静默）；
- `tests/selfhost/llvm-architecture.py`：LA0 O0/O2 全部通过；
- yh-8/yh-9 固定点逐字节相同（`cmp`），Windows 种子已重滚；
- `just test` 全量门禁绿（已知例外：code-stats 本机环境问题，与本修复
  无关）；arch-check 2/2（`max_build_lines` 6976 → 6990，+14 行临时目录
  兜底逻辑）。

## 后续（Lane B）

本修复已随本地种子生效；Lane B 的 B4（rc tag → Release）会把含修复的
bridge.c 带进四平台产物。
