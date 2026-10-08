# yh_asm（AArch64 汇编器）README

## 定位

把 yh 后端发射的 AArch64 汇编文本汇编成**可重定位对象**：

- `-t linux`（默认）→ **ELF64** `ET_REL`
- `-t darwin` → **Mach-O** `MH_OBJECT`，arm64

覆盖契约里冻结的子集：整数常量搬运、访存、分支、地址、伪指令，
以及标量浮点（八族，含浮点访存）。
契约见 [yh-link 独立项目与首版汇编子集契约](../docs/03-design/yh-link独立项目与首版汇编子集契约.md)，
分期路线见 [yh-asm 与 yh-link 实施方案](../docs/02-plan/yh-asm与yh-link实施方案.md)。

对应实施方案的 **TC1（二进制模型与上下文）+ TC2（AArch64 编码）+ TC3（ELF 对象出口）+ TC8（Darwin 汇编与 Mach-O 对象出口）**。

本项目是汇编器的**唯一实现**：2026-10-07 目录整理时，原先寄放在
[`link/`](../link/README.md)（链接器项目）里的汇编器实现整体迁到这里，
两者从此按职责分开——本项目只做「汇编文本 → 对象」，
`link/` 只做「对象 → 可执行映像」。两个项目**互不依赖、互不 import**，
只通过标准对象文件交接。

## 与编译器的对接

编译器逐模块汇编时按 `YH_ASM` 环境变量 → `PATH` → 编译器同目录的顺序找
`yh_asm`，找到就用它替代 `clang -c`，找不到才回落系统编译器。仓库根执行
`make yh-asm` 会构建本项目并产出根目录 `yh_asm`。

> 过渡期：编译器侧查找名切换（`yh_link` → `yh_asm`）尚未做，
> `make yh-link` 暂时把同一份产物复制成根目录 `yh_link` 供现役对接使用。
> 切换完成后删除该别名目标，见 [docs/todo.md](../docs/todo.md)。

## 构建

```bash
cd asm
../yh build        # 或 ../bin/yh build；产物 .build/yh_asm
../yh run          # 构建并运行自检
```

> 必须先 `cd asm`。从仓库根执行 `yh build asm/` 不成立，
> 因为 `asm/` 是独立项目，有自己的 `project.toml`。

## 用法

```bash
yh_asm                        # 跑自检（编码器 + 公共层 + 端到端），退出码即门
yh_asm --dump-enc             # 逐条打印编码器用例的期望机器字
yh_asm asm -o out.o in.s      # 汇编单个文件（ELF64）
yh_asm asm -t darwin -o out.o in.s   # 汇编成 Mach-O arm64 对象
```

## 目录

```text
src/obj/10_bytes.yh     缓冲、名称池、小端读写、字符串与整数字面量
src/obj/20_model.yh     TargetSpec / Section / Symbol / Reloc / Ctx 与诊断
src/obj/40_elf.yh       节布局、符号编号、重定位表、elf_write 入口
src/obj/41_elf_emit.yh  节/符号/重定位的实际写入
src/obj/50_macho.yh     Mach-O 常量、重定位类别映射、同节分支规则
src/obj/51_macho_emit.yh  Mach-O 头/段/节/符号表/重定位写出，macho_write 入口
src/asm/10_arm64.yh     位域、寄存器折叠、逻辑立即数、条件码
src/asm/20_scan.yh      扫描器
src/asm/31_enc_int.yh   加减、逻辑、移位、位域、乘除编码
src/asm/32_enc_mem.yh   访存编码
src/asm/33_enc_br.yh    分支、条件分支、adr/adrp
src/asm/34_enc_fp.yh    标量浮点编码（fadd/fcmp/fcvt/fcvtzs/scvtf/ucvtf/fmov）
src/asm/40_parse.yh     Parser 结构、记号助手、表达式、标签、伪指令底座
src/asm/51_parse_alu.yh 算术/逻辑/位域/选择/访存类指令的解析
src/asm/52_parse_ins.yh 分支类、adrp/adr、系统指令的解析
src/asm/53_parse_dir.yh 伪指令与语句循环
src/asm/60_assemble.yh  回填、重定位白名单、汇编入口
src/asm/70_selftest.yh  三层自检
src/main/main.yh        命令行入口
```

文件名的数字前缀就是模块内的**声明顺序**：yh 按文件名排序编译，
一个类型必须先在排序更靠前的文件里定义，所以前缀是硬约束，不是排序美化。

## 测试

```bash
python3 tests/check.py                    # 冷编 + 自检（默认门）
python3 tests/check.py --full             # 再加编码/语料/结构差分（需 llvm-mc）
python3 tests/check.py --full ../tmp/inv  # 指定语料目录

python3 tests/check_enc.py                  # 编码器向量，逐条对 llvm-mc
python3 tests/check_corpus.py tests/asm     # 定向语料，内容与 llvm-mc 逐字节比
python3 tests/check_obj.py                  # 对象结构 + 确定性（连编两次比字节）
python3 tests/elf_link_check.py             # 容器链接门：链成可执行并真跑

python3 tests/macho_obj_check.py a.o b.o    # Mach-O 单对象：打印结构或语义差分
python3 tests/macho_corpus_check.py 目录... # Mach-O 出口：与 clang 逐文件语义差分
python3 tests/macho_link_run.py ../tmp/inv  # Mach-O 端到端：ld 链成可执行后比运行行为
```

后三个门要宿主有 `clang` 与 `ld`（macOS 自带）。`macho_link_run.py` 只对**完整
程序**语料有意义——`tests/asm` 下的指令碎片缺入口点，链不上会被跳过。

`elf_link_check.py` 需要 docker 与镜像 `yh-link-elf:latest`：

```bash
docker build -t yh-link-elf:latest tests/docker
```

宿主是 Darwin，没有 AArch64 的 ELF 链接器也没有 Linux 系统调用环境，链接与
运行只能放容器里做。要挂进容器的中间产物放在仓库内的 `tmp/linkbox/`：
colima 不共享宿主 `/tmp`。

容器链接门是判定最强的一道：同一份汇编分别由本工具与 `llvm-mc` 汇编，
两边都在容器里链成静态可执行并运行，要求退出码与标准输出完全一致。
需要 `tests/elf/{start.s,yhr.s}` 提供 `_start` 与 yh 运行时的三个 OS
原语桩（`_write` / `_mmap` / `_munmap`）。

三层自检都通过 `.build/yh_asm` 的退出码汇报：

| 层 | 数量 | 内容 |
| --- | --- | --- |
| 编码器向量 | 134 | 单条指令 → 期望机器字，参考值取自 llvm-mc（含标量浮点与浮点访存） |
| 公共层 | 36 | 位域、寄存器折叠、逻辑立即数正反例、编码回环、条件码、移位助记符 |
| 端到端 | 25 | 固定源码走完扫描→解析→回填→重定位，核对 16 个机器字与 9 条重定位（GOT 两类、未定义符号、已定义的局部符号三种都出重定位） |

`tests/check_enc.py`、`tests/check_corpus.py` 与 `tests/check_obj.py` 都需要
`/opt/homebrew/opt/llvm/bin/llvm-mc` 作为独立参照。

## 已知边界（首版不支持，遇到即报诊断）

- **浮点**：只支持标量，族与形态见契约 §3。寄存器间 `fmov`、`fabs/fneg`、
  带舍入模式或 `#fbits` 的转换、`fcmp #0.0`、128 位 `q` 寄存器都不支持。
- **GOT**：只有 64 位形态（LP64 的限制，llvm-mc 同样拒绝更窄的 GOT 访存）。
- **Mach-O 目标的差异**：Mach-O 对象只有一个无名段，全部节挂在它下面；
  `PAGEOFF12` 的 length 一律 2（是立即数字段字节数，与访问宽度无关）；
  同节分支（哪怕目标是 global）汇编期就定死、不发重定位，而 ELF 对同节分支
  照发 `CALL26`/`JUMP26`；条件分支只能跳本节局部标签，否则写出阶段报错。
- **指令级负例门缺失**：自检只有编码层负例（逻辑立即数不可编码值），
  越界立即数/偏移、SP 与 ZR 混用、未知助记符、未定义局部标签等拒绝路径
  没有专门用例；已记入 [docs/todo.md](../docs/todo.md)。
- **容器门里 7 个语料跳过**：`__Exit` / `_strtoul` / `_open` / `_close` /
  `_abs` 这些 yh 运行时外部符号在 `tests/elf/yhr.s` 里没有桩，两边同样
  链不上，门按差分语义跳过而不是误判。补桩后这 7 个就能跑起来。
- 可执行文件链接（ELF 的 TC4、Mach-O 的 TC9–TC10）不在本项目范围内，
  属于 [`link/`](../link/README.md) 链接器项目。
