# ADR-0025：console / argv 平台代码 → `cmd`

日期：2026-11-10。状态：**已实施**。

关联：[ADR-0021](0021-yh-gen职责拆分.md)（support 归属）、
[ADR-0024](0024-yh-support再收缩.md)（support 再收缩）。

## 背景

`support` 持有宿主入口平台代码：控制台 UTF-8 初始化（`console.<平台>.yh`）与
UTF-8 argv 重建（`argv.<平台>.yh`，Windows VENC-2）。实测**唯一消费者是
`cmd/yh/yh.yh`（main 入口）**：`console_utf8_init()` 在任何输出前调用，
`argv_utf8_rebuild()` 在解析命令行前调用。它们不属于「编译器 libc」，而是
进程入口的一次性宿主适配。

## 决定

把 console / argv 整簇迁到 `cmd/yh/`（`module main`）：

- 6 个平台实现：`console.{darwin,linux,windows}.yh`、`argv.{darwin,linux,windows}.yh`；
- 2 个平台无关包装：`console.yh`（`console_utf8_init`）、`argv.yh`（`argv_utf8_rebuild`），
  改为 main 模块私有 `fn`（不再 `pub`，只有 main 用）；
- 4 个 Win32 extern（`SetConsoleOutputCP/SetConsoleCP/GetCommandLineW/WideCharToMultiByte`）
  随 Windows 实现迁入（`console.windows.yh` / `argv.windows.yh`）。
- `main` 入口改裸调用 `console_utf8_init()` / `argv_utf8_rebuild(...)`。

**`clock.*` 不迁**：`clock_ns` 被 build/性能测量消费，留在 support。

## 为什么是 cmd

- 唯一消费者是 main；架构规则「任何模块不得 import main」决定了这段代码只能
  住在顶层入口模块，不能下沉到任何被依赖层。
- 无环：main 本就依赖 support；迁出后 support 不再持有入口宿主代码，
  依赖边不变（不新增任何模块对 main 的依赖）。

## 备选与被否决的方案

| 方案 | 结论 | 理由 |
| --- | --- | --- |
| 留 support | 否决 | 入口宿主适配不是共享基础设施；support 应只剩编译器 libc |
| 新建 `host` 模块 | 否决 | 只有一个消费者（main），多一个模块无收益 |
| 连 clock 一起迁 cmd | 否决 | clock 被 build/性能消费，迁 cmd 会迫使 build→main 成环 |

## 后果

- `support` 平台变体只剩 `clock.*`；删除 `console.*`/`argv.*` 6 文件与 2 个包装、
  4 个 extern。
- `cmd/yh` 新增 8 文件（6 平台 + 2 包装）；`main` 模块依赖边不变。
- 用户程序产物不变（编译器内部入口代码）；Windows 码页/argv 行为逐字保持。