# yh_link（静态 ELF 链接器）README

## 定位

yh 自有工具链的**链接器**：把可重定位对象链接成可执行映像。

| 目标 | 形态 | 状态 |
| --- | --- | --- |
| `-t linux`（默认） | 静态 **ELF64** `ET_EXEC`（AArch64，非 PIE） | **已实现** |
| `-t darwin` | **Mach-O** arm64 可执行映像 | 未实现（显式报错，计划 TC9） |

- 设计文档：[yh-link 静态 ELF 链接器设计](../docs/03-design/yh-link静态ELF链接器设计.md)
- 分期与状态：[yh-link 静态 ELF 链接器实施方案](../docs/02-plan/yh-link静态ELF链接器实施方案.md)
- 平台矩阵：[yh-link 平台与架构矩阵方案](../docs/02-plan/yh-link平台与架构矩阵方案.md)

## 现状

**Linux/AArch64 静态链接可用**：能读入 `ELF64 ET_REL` 对象、合并节、解析
跨对象符号、应用 12 种重定位、产出可装载并**真跑**的静态可执行文件。

**尚未接入编译器**（用户要求：等稳定后再接入）。集成的前置条件与任务分解见
实施方案 §6；其中第一步是先把编译器的汇编器查找从 `yh_link` 改成 `yh_asm`，
否则真链接器占用 `yh_link` 这个名字会破坏现有构建。

## 用法

```bash
yh_link                                     # 无参数：跑自检，退出码即门
yh_link --version                           # 打印版本
yh_link link [-o out] [--entry SYM] [--max-page-size N] [--verbose] in1.o ...
```

- 退出码：**0** 成功；**1** 输入/链接失败；**2** 用法错误。
- 诊断写 fd 2；`--verbose` 额外打印各阶段过程输出（读取/符号/布局/重定位的
  中间量）并打印布局报告，不改退出码。
- 入口符号默认 `_start`，必须存在、已定义且落在 `.text`；
  链接器**不内置启动代码**。
- `--max-page-size` 默认 65536，最小 4096，必须 2 的幂；它决定程序头的
  `p_align` 与段起始对齐。
- 产物**一次性写出**：链接成功后才创建输出文件，失败不留半成品。

### 一个完整例子

```bash
asm/.build/yh_asm asm -o hello.o hello.s
link/.build/yh_link link -o hello hello.o
./hello ; echo $?
```

## 与汇编器的关系（解耦）

汇编器是**独立项目** `asm/`（yh_asm）：本项目**不 import** 它的任何模块，
两者只通过标准 ELF64 `ET_REL` 对象交接。验收门也遵守这条边界——它通过
**命令行**调用 `yh_asm` 产出对象（`tests/link_accept.py`），不 import 汇编器
的 Python 模块。

2026-10-07 目录整理：原先寄放在本项目的汇编器实现（`src/obj`、`src/asm`）
整体迁到 `asm/`；本项目的汇编器旧门随之迁到 `asm/tests/`。

## 构建

```bash
cd link
../yh build            # 或 ../bin/yh-linux-arm64 build；产物 .build/yh_link
```

或在仓库根：

```bash
make yh-link-build     # 用刚构建的 ./yh 冷编 link/，产物留在 link/.build/
```

> 必须先 `cd link`。从仓库根执行 `yh build link/` 不成立，因为 `link/` 是
> 独立项目，有自己的 `project.toml`。
>
> `make yh-link-build` **刻意不把产物复制到仓库根**：编译器当前按 `yh_link`
> 这个名字发现**汇编器**，真链接器占用该名字会破坏现有 `make`。

## 测试

```bash
# 构建 + 自检 + CLI 契约（不需要汇编器，也不需要能运行 AArch64 产物）
make yh-link-probe
python3 link/tests/check.py

# 追加端到端验收与 GNU ld 差分（需要 yh_asm 与可运行 AArch64 产物的环境）
make yh-link-probe FULL=1
python3 link/tests/check.py --full

# 单独跑某一层
python3 link/tests/link_accept.py --link link/.build/yh_link --asm asm/.build/yh_asm
python3 link/tests/link_diff_regress.py --link link/.build/yh_link --asm asm/.build/yh_asm
```

三层门各自验什么：

1. **自检**（`yh_link` 无参数，57 项四组）：算子原语与实测错值量级、读取层
   拒绝路径、单对象端到端、多对象合并（含"符号地址必须加节内偏移"这条回归）；
2. **端到端**（`tests/link_accept.py`，7 用例）：汇编 → 链接 → 结构断言 →
   **真跑比对退出码** + 两次链接产物逐字节相同；
3. **差分**（`tests/link_diff_regress.py`，7 用例）：与
   `aarch64-linux-gnu-ld -static -nostdlib` 比行为、比静态性、比"同一节内
   符号间距"（与布局无关的不变量）。

**运行环境**：本机是 Windows + WSL（Ubuntu x86_64），无 AArch64 硬件，产物
经 qemu-user/binfmt **模拟执行**。arm64 原生验证是待办项（实施方案 G7）。

## 目录

```text
src/main/main.yh          命令行入口：参数解析、读入、调用、写出、退出码
src/obj/10_bytes.yh       字节/位原语、缓冲、字符串池、小端读写
src/obj/20_model.yh       常量、数据结构、LinkCtx、全局符号表、诊断
src/elf/30_read.yh        读取与校验输入对象（含全部拒绝路径）
src/elf/40_symtab.yh      符号收集、引用绑定、未定义检查、解析与定址
src/elf/50_layout.yh      节合并、GOT 分配、段布局、入口查找、布局报告
src/elf/60_reloc.yh       12 种重定位 + 指令形态校验 + 重叠检测
src/elf/70_write.yh       输出映像：头、程序头、段、符号表、节头表、自检
src/link/80_link.yh       链接主流程（阶段编排）与阶段名
src/selftest/80_selftest.yh  自检四组
tests/check.py            验收门：构建 + 自检 + CLI 契约（--full 加后两层）
tests/link_accept.py      端到端：汇编 → 链接 → 结构 → 真跑 → 确定性
tests/link_diff_regress.py 与 GNU ld 的差分回归
tests/asm/*.s             验收语料（每个文件头部写明它验证什么）
```
