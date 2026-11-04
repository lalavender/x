# yh-Windows编译器产物yh-exe-2026-11-05

## 概述

Windows 宿主上编译器产物从根目录无扩展名的 `yh` 改为 **`yh.exe`**  
（用户决定）。原因：PowerShell/cmd 把无扩展名文件按扩展名解析——  
实测 PowerShell 对 `.\yh` 报「无法在管道中间运行文档」（扩展名不在  
PATHEXT），进程根本没启动；Git Bash 的 POSIX exec 不看扩展名所以能跑。

## 变更

`justfile`（全部经变量引用，一处定义三处生效）：

```just
yh := if host_os == "windows" { root + "/yh.exe" } else { root + "/yh" }
yh_ext := if host_os == "windows" { "/yh.exe" } else { "/yh" }
yh_abs := absolute_path(yh)
yh_run := if fast_stage == "1" { absolute_path(fast_dir + yh_ext) } else { yh_abs }
```

`just seed` 不变：滚到 `bin/yh-windows-x64`（种子名不带扩展名，由  
seed-build 以 CreateProcess 调用，与 shell 无关）。旧的无扩展名根目录  
`yh` 已删除。AGENTS.md 使用说明补注。

## 验证

- `just dev` 产出 `yh.exe`；PowerShell 实测 `.\yh.exe --version` →  
  `yh 0.0.11`（exit 0）、裸调用 exit 2（帮助走 stderr 契约不变）；
- `just test` 全量门禁在本机执行（所有门经 `{{ yh_run }}` 自动跟随新名）。

注：PowerShell 控制台若显示中文帮助乱码，是控制台码页（GBK vs UTF-8）  
显示问题，`chcp 65001` 可解；产物与管道行为不受影响。

