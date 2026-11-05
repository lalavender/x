# VENC-2：Windows CRT 入口 argv 重建（CI filter 用例真正根因）

- 日期：2026-11-05
- 触发：CI run [41941536106](https://github.com/lalavender/x/actions/runs/41941536106)
  windows-x64 job「全量回归」失败：
  `test-check.py` 的 `list-filter`（退出码 0，输出空）与
  `execute-filter`（退出码 1，无匹配报错），filter 均为中文「跨文件」。
  上一次 run（41934812863，修复 0b1ba2f 之前）失败字节完全相同。

## 根因

0b1ba2f（VENC）把**零 CRT 入口桩**改为
`GetCommandLineW` + `WideCharToMultiByte(65001)`，但编译器自身不走那条路：

- 自举编译器链接闭包里的 `libcmt.lib`，`link/windows_link.yh` 固定
  `/entry:mainCRTStartup`——CRT 存在时入口由静态 CRT 提供，argv 经
  `__getmainargs` → `GetCommandLineA` 按 **ANSI 码页（ACP）** 取得；
- `/alternatename:mainCRTStartup=__yh_zero_crt_start` 只是**无 CRT 时**的
  兜底，有 libcmt 时完全不生效；
- 英文 runner（ACP=1252）上 `跨文件` 在 `GetCommandLineA` 一步就变 `???`
  （不可逆），`testkit --filter` 永不匹配；本机（ACP=936/GBK）拿到 GBK
  字节，与源码内 UTF-8 比较同样不匹配。

本机定位证据（0.0.11 种子 → yh1 → gen-2 全链路复刻 CI 后）：
在 `tc_filter_utf8` 临时插桩输出 filter 字节，yh.exe 自身收到的是
`BF E7 CE C4 BC FE`（GBK「跨文件」，6 字节）而非 UTF-8（9 字节）；
同一编译器为单文件程序发射的零 CRT 桩则输出正确 UTF-8——证明桩没病，
病在 CRT 入口。

## 修复

- 新增 `compiler/gen/argv.windows.yh`：`pub fn argv_utf8_rebuild(*int,
  ***char)` 在 main 最前用 `GetCommandLineW` +
  `WideCharToMultiByte(65001)` 把命令行重建为 UTF-8 argc/argv。解析语义与
  零 CRT 桩一致（双引号成组、空格分隔、连续空格忽略、引号不进入参数）；
  转换失败保持传入 argc/argv 不变（ASCII 命令行仍可用，与桩的 conv_fail
  降级一致）。零 CRT 入口之后 argv 已是 UTF-8，重建为幂等直通。
- 新增 `compiler/gen/argv.linux.yh`、`argv.darwin.yh` 空实现（与
  `console.*.yh` 同约定：非 Windows 平台 argv 来自 execve 字节向量，进程内
  约定即 UTF-8）。
- `compiler/cmd/driver.yh`：`main` 在 `console_utf8_init()` 之后、任何
  argv 消费（含 `--emit-module`/`--lld-link` 内部协议识别）之前调用重建，
  此后统一使用 `rargc`/`rargv`。

## 验收

- `tests/modules/test-check.py`：38/38 全过（CI 上为 36 通过 + 2 失败），
  `--list --filter 跨文件` 正确返回唯一用例；
- `just test`：语法语料、运行语料、模块项目、libs 全部通过；arch-check
  按预算规则上调两项——`max_module_lines` 461 → 469（driver 重建调用与
  注释 +8 行）、`max_globals` 172 → 174（argv.windows.yh 的 `argv_line`/
  `argv_vec` 两个模块级静态缓冲）；
- 不影响 Linux/macOS：平台变体文件只编进对应目标；Windows 交叉目标
  （linux-arm64 job 的编译侧门）使用的 `kernel32.def` 已含
  `GetCommandLineW`/`WideCharToMultiByte`（0b1ba2f 增补）。

## 遗留边界（已记入 docs/todo.md）

CRT 的文件 API（`open`/`CreateFileA`）仍按进程 ACP 解释路径字节：本机
（ACP=936）`--syntax-check` 中文路径在 VENC-2 之前能读源文件（argv 与 CRT
同为 GBK），VENC-2 之后 argv 是 UTF-8、CRT 仍按 GBK → 打不开。CI 路径全为
ASCII，不受影响；且修复前中文路径整体也不可用（`-o` 输出/链接阶段必挂）。
完整修法是把 SDK 里现成的 `lib/yh-utf8.manifest` 以
`/MANIFEST:EMBED /MANIFESTINPUT:` 接进 lld 链接（让整个 CRT 进程说 UTF-8），
涉及项目链接层与多平台固定点回归，另立 P2 项，不纳入本次修复。

## 后续

- 推送后观察 CI windows-x64 job 全绿；
- `just test` + `just selfhost-native` 全绿后按流程 `just seed` 滚种子，
  下一代种子（含 W2 + VENC-2）发布后可删除过渡自举桥。
