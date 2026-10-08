# yh_link（链接器）README

## 定位

yh 自有工具链的**链接器**：把汇编器产出的可重定位对象链接成可执行映像。

- `-t linux` → 静态 **ELF64** `ET_EXEC`（TC4）
- `-t darwin` → **Mach-O** arm64 可执行映像（TC9）
- ad-hoc 代码签名（TC10，arm64 macOS 硬要求）

设计见 [yh-asm 与 yh-link 设计](../docs/03-design/yh-asm与yh-link设计.md) 与
[Mach-O 可执行文件链接器设计](../docs/03-design/yh-link%20Mach-O可执行文件链接器设计.md)，
分期路线见 [yh-asm 与 yh-link 实施方案](../docs/02-plan/yh-asm与yh-link实施方案.md)
的 **TC4 / TC9 / TC10 / TC11**。

**现状：链接功能未实现，只有入口骨架。** 入口先固定命令形态与退出码，
后续 TC4 往实现里填，调用方（Makefile、编译器链接步）无需再改：

```bash
yh_link link -o out in1.o in2.o ...   # 规划中的链接子命令，当前返回退出码 2
yh_link --version                     # 打印版本
```

## 与汇编器的关系

汇编器是**独立项目** `asm/`（yh_asm）：本项目既不依赖它，也不包含任何汇编
代码，两者只通过标准对象文件交接（ELF64 `ET_REL` / Mach-O `MH_OBJECT`）。

2026-10-07 目录整理：原先寄放在本项目的汇编器实现（`src/obj`、`src/asm`）
整体迁到 `asm/` 项目；本项目的汇编器旧门（编码/语料/对象差分）随之迁到
`asm/tests/`。

## 构建

```bash
cd link
../yh build        # 或 ../bin/yh build；产物 .build/yh_link
```

> 必须先 `cd link`。从仓库根执行 `yh build link/` 不成立，
> 因为 `link/` 是独立项目，有自己的 `project.toml`。

## 测试

```bash
python3 tests/check.py                 # 构建 + 入口行为门
python3 tests/check.py --compiler ./yh # 指定编译器
```

TC4 落地后本门要扩展为真正的链接验收：对象解析、符号解析、节布局、
重定位、可执行文件运行差分。

## 目录

```text
src/main/main.yh   命令行入口骨架（命令形态、退出码、未实现提示）
tests/check.py     验收门：冷编 + 入口行为
```
