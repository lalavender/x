# yh-Windows控制台UTF8显示-2026-11-05

## 概述

修复 Windows 控制台中文乱码：yh 的诊断/帮助文本是 UTF-8 字节，中文  
Windows 控制台默认码页（GBK/936）会按 GBK 渲染成乱码。现在进程启动时  
（driver `main` 第一行）调用 `gen.console_utf8_init()`，Windows 上把  
控制台输出/输入码页切到 65001（UTF-8），其余平台为空实现。

## 变更

- `compiler/gen/console.windows.yh`（新）：`@[extern] SetConsoleOutputCP/
  SetConsoleCP`（kernel32，经既有 `[link-windows-x64].support` 的  
  kernel32.lib 链接），`pub fn console_utf8_init()` 切 65001。
- `compiler/gen/console.linux.yh`、`console.darwin.yh`（新）：空实现，  
  保证所有平台的符号存在（平台文件约定，与 `clock.*` 同模式）。
- `compiler/cmd/driver.yh`：`main` 首行调用 `gen.console_utf8_init()`。
- `tools/arch-check.py`：`max_module_lines` 458 → 461（driver +3 行调用  
  与注释）。

语义说明：码页切换是**会话级**的（yh 退出后控制台保持 65001，  
Windows Terminal 下无副作用）；管道/重定向不受影响——写出的始终是  
原始 UTF-8 字节，切码页只影响控制台渲染。

## 验证

- `chcp`（936）→ `yh.exe --version` → `chcp`（**65001**）：调用生效且  
  会话保持；
- PowerShell 下 `yh.exe` 帮助中文正常显示（「用法」「构建当前项目」等）；
- yh-3/yh-4 固定点逐字节相同（`cmp`），Windows 种子已重新滚动；
- `tools/arch-check.py` 通过。

