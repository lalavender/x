# yh-asm 与 yh-link 规划交付

日期：2026-10-02。状态：**规划完成，实现未开始**。

用户要求开始规划 yh-asm/yh-link，并确认 Linux/AArch64 优先，随后 macOS/arm64。
本轮细化 ADR-0009 的 R4/R5，保留既有工作区改动，不修改编译器、语言语法、
测试实现或入库种子。

## 交付内容

- [设计文档](../03-design/yh-asm与yh-link设计.md)：目标、当前事实、范围/替代路线、
  命令/API、源码模块、汇编语法/编码/布局、ELF 重定位/链接、启动与 OS 桥、
  归档、Mach-O 装载/绑定/签名、缓存/并发/事务与验证策略。
- [实施方案](../02-plan/yh-asm与yh-link实施方案.md)：TC0–TC10，各阶段文件、
  `.yh` 用例、切片顺序、验收命令、入口/结束条件、估算与首个竖切片。
- `docs/todo.md` 登记未完成实施项，`docs/finish.md` 只登记本轮规划交付；
  编译流程原设计/原实施方案的 R4/R5 增加详细文档入口。

推荐用 yh 所需汇编子集生成标准 ELF/Mach-O，不实现完整 GNU as/ld，不绕开汇编阶段。
独立命令与编译器内调用共用实现。Linux 对象/静态程序/编译器自举分别设门，
有限 C 对象/归档独立分期，完整 libc 和完整 SSA 迁移不全部捆绑为首期前置。

## 事实与临时证据

分析基线 `dcfcac1` 加已有未提交工作区；编译器 52 个 `.yh` 源文件。

| 输入 | 本轮结果 |
| --- | --- |
| `tests/yh-run/run/` + `pass/`，Linux 发射 | 59/59 成功，66 个助记符拼写、9 个伪指令 |
| 同一输入，Darwin 发射 | 59/59 成功，65 个助记符拼写、9 个伪指令 |
| 6 个现有 Darwin 自编模块 `.s` 缓存 | 51 个助记符拼写、8 个伪指令 |
| `file bin/yh yh` | 二者均为 Mach-O arm64，Linux 原生种子未入库 |

盘点只覆盖上述输入，不代表最终子集清单或汇编/链接正确性证明。
本轮仅使用当前编译器发射文本；没有实现 yh-asm/yh-link，也没有用其生成对象或程序。
全部临时文件在 `tmp/yh-toolchain-plan/`，包括两个 inventory JSON 与两平台汇编。

源码审计确认项目和单文件仍用 clang/gcc；`drv_write_asm`/`mb_open_out` 使用
目标方言选择宿主 open flags。TC0 要分开 HostPlatform 与 TargetSpec。
prelude 仍登记文件/进程等外部函数，Linux 自举必须补相应 syscall 桥。
Makefile 已按平台选种子并把 SEED 传给原生门，正确接线应保留而不是重写。

## 验证范围

- `make` 返回 0，入库种子 SHA-256 校验成功；根产物已是最新状态，未冷编。
- 种子：`c4168844db4f8896b50f02ad29a45cc709b90f112e6075fe0a285ed414ec1719`。
- 当前根 yh：`a4220e1f304c6aa1c0c852d9419a0a731af820ca4621509113dc12a3a1ec5c69`。
- 检查 7 份相关文档、143 个相对链接、TC0–TC10 共 11 个阶段，以及代码围栏/
  Markdown 空白，错误数为 0；结果在 `tmp/yh-toolchain-plan/document-check.json`。
- `git diff --check` 通过；新建文档另行检查行尾空格与文件结尾。

未运行 `make test`、`make selfhost-native` 或 `make seed`。
本次没有代码行为变化，不添加虚假的“已实现功能”测试；后续实现每个切片必须新增
`.yh` 测试并执行构建与相应阶段/平台主门。
