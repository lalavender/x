# yh-SDK迁移vendor-2026-11-05

## 概述

按用户决定，仓库内 SDK 源从 `compiler/` 迁至 `vendor/`（与既有
`vendor/llvm/` 约定对齐）：

- `compiler/darwin-sdk/` → `vendor/darwin-sdk/`（`git mv`，保留历史）
- `compiler/windows-sdk/` → `vendor/windows-sdk/`（`git mv`；迁移前已核对
  vendor 下既有未跟踪副本与 compiler 版逐字节一致，删除重复后移动）

`compiler/` 回归纯 yh 源码模块目录；文本 SDK 源（.def/.tbd/manifest）统一
归 vendor，生成物（.lib）不入库照旧。

## 引用面同步

**编译器运行时查找路径**（影响二进制行为，已重编验证）：

- `compiler/link/darwin_link.yh` `cmd_darwin_bundled_sdk`：suffixes
  `compiler/darwin-sdk` → `vendor/darwin-sdk`（含 `../`、`../../` 两个变体）
- `compiler/link/windows_link.yh` `mb_windows_sdk_lib_dir`：prefixes
  `/compiler/windows-sdk/lib` → `/vendor/windows-sdk/lib`

**构建与测试工具**：

- `justfile`：`darwin_sdk`（YH_DARWIN_SDK 导出）、fast-stage 符号链接、
  安装清单、注释共 5 处
- `tools/windows-sdk.py`：`BUNDLE = ROOT / "vendor/windows-sdk"` 与文档串
- `tools/llvm-darwin-sdk-bundle.py`：`DEFAULT_OUTPUT`
- `tests/selfhost/llvm-darwin-bundled-sdk.py`、`llvm-windows-sdk.py`、
  `native-selfhost.py`、`llvm-windows-target.py`（注释）
- `AGENTS.md`：Darwin SDK stub 条目

不变项：安装前缀 `share/yh/darwin-sdk`、生成缓存根
`tmp/llvm-migration/{windows,darwin}-sdk`、bundle 目录名（`darwin-sdk`/
`windows-sdk`）、`vendor/llvm/`（LLVM 二进制 SDK，本就属 vendor）。

**历史文档**（docs/01-finished、docs/02-plan 的带日期记录）不改——它们
描述当时状态。

## 开发树自足

`vendor/windows-sdk/lib` 现已生成 `kernel32.lib` 与 `yh_chkstk.obj`
（gitignore 的生成物）。已实测：**清除 `YH_WINDOWS_SDK`/`YH_DARWIN_SDK`
环境变量后**，仓库根的 `yh` 通过 exe 相对路径找到
`vendor/windows-sdk/lib` 完成单文件编译链接并正确运行——开发树不再依赖
tmp 缓存根也能链接。

## 验证

- Windows/x64 重编通过（backend/link 重编，含新的查找后缀）。
- 新二进制内确认嵌入 `vendor/windows-sdk`、`vendor/darwin-sdk` 字符串。
- 无 SDK 环境变量的单文件构建冒烟通过。
- `just test` 全量门禁在本机执行。
