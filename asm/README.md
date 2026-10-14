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

## 与编译器的对接（当前不接入）

**本项目当前不接入编译器**（2026-10-12 决定，见
[稳定化实施方案](../docs/02-plan/yh-asm汇编器稳定化实施方案.md)）。编译器的
逐模块汇编步按 `YH_LINK` 环境变量 → `PATH` → 编译器同目录的顺序找 **`yh_link`**
（`compiler/cmd/link_cache.yh` 的 `mb_asm_tool`），找到就用
`<tool> asm [-t darwin] -o out.o in.s` 顶替 `clang -c` / `gcc -c`。
仓库根**不再产出该名字**：`make yh-link` 过渡别名与入库的根目录
`yh_asm`/`yh_link` 副本已随断电删除，所以 `make && ./yh build` 走系统 cc。

需要让编译器临时用本项目时，走显式、可关的入口（argv 契约与本项目一致）：

```bash
make yh-asm                                  # 产出根目录 yh_asm（编译器不发现它）
YH_LINK="$PWD/yh_asm" ./yh build <项目>       # 显式指定，用汇编器做模块汇编
```

影子验收脚本 `asm/tests/shadow-build.py` 用的就是这条路径，不进 `make`、
不进默认门。把查找名切到 `yh_asm`/`YH_ASM`、切默认目标属于**接入**，
待稳定判据 S1–S7 通过后另立任务。

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
yh_asm                        # 跑自检（公共层 + 编码 + 端到端 + GNU 方言 + 拒绝层）
yh_asm --dump-enc             # 逐条打印编码器用例的期望机器字
yh_asm asm -o out.o in.s      # 汇编单个文件（ELF64）
yh_asm asm -t darwin -o out.o in.s   # 汇编成 Mach-O arm64 对象
```

退出码契约：**0** 成功；**1** 输入/诊断错误；**2** 用法错误。
`-t` 只决定**对象格式**，写文件用的 open 旗标按**宿主**取值（Linux 0x241、
Darwin 0x601），所以交叉目标（Linux 宿主上 `-t darwin`）也能正常出对象。

## 目录

```text
src/obj/10_bytes.yh     缓冲、名称池、小端读写、字符串与整数字面量
src/obj/20_model.yh     TargetSpec / Section / Symbol / Reloc / Ctx 与诊断
src/obj/40_elf.yh       节布局、符号编号、重定位表、elf_write 入口
src/obj/41_elf_emit.yh  节/符号/重定位的实际写入
src/obj/50_macho.yh     Mach-O 常量、重定位类别映射、同节分支规则
src/obj/51_macho_emit.yh  Mach-O 头/段/节/符号表/重定位写出，macho_write 入口
src/asm/10_arm64.yh     位域、寄存器折叠、逻辑立即数、条件码
src/asm/20_scan.yh      扫描器（含词法错误的位置与信息）
src/asm/31_enc_int.yh   加减、逻辑、移位、位域、乘除编码
src/asm/32_enc_mem.yh   访存编码
src/asm/33_enc_br.yh    分支、条件分支、adr/adrp
src/asm/34_enc_fp.yh    标量浮点编码（fadd/fcmp/fcvt/fcvtzs/scvtf/ucvtf/fmov）
src/asm/40_parse.yh     Parser 结构、记号助手、表达式、标签、伪指令底座
src/asm/51_parse_alu.yh 算术/逻辑/位域/选择/访存类指令的解析
src/asm/52_parse_ins.yh 分支类、adrp/adr、系统指令的解析
src/asm/53_parse_dir.yh 伪指令与语句循环
src/asm/60_assemble.yh  回填、重定位白名单、汇编入口
src/asm/70_selftest.yh  五层自检（含 GNU 方言端到端与拒绝层）
src/main/main.yh        命令行入口

tests/check.py          默认门：冷编 + 自检；--full 追加全部差分门
tests/check_neg.py      拒绝路径与诊断质量（位置 + 关键字）
tests/check_enc.py      134 条编码向量：与 oracle 逐条比对
tests/check_corpus.py   语料逐节内容 + 重定位差分（默认 tests/asm）
tests/check_obj.py      ELF 结构/确定性；--target darwin 走字节快照
tests/elf_link_native.py Linux 宿主的链接运行差分门（交叉 ld + qemu）
tests/elf_link_check.py  容器链接运行差分门（macOS 宿主，需要 docker）
tests/shadow-build.py   影子验收：显式 YH_LINK 冷编编译器 + 两代固定点
tests/asm-neg/          拒绝路径语料；tests/asm-gnu/  GNU 方言语料
```

文件名的数字前缀就是模块内的**声明顺序**：yh 按文件名排序编译，
一个类型必须先在排序更靠前的文件里定义，所以前缀是硬约束，不是排序美化。

## 测试

```bash
python3 tests/check.py                    # 冷编 + 自检（默认门）
python3 tests/check.py --full             # + 拒绝路径/编码/语料/结构/快照门
python3 tests/check.py --full ../tmp/inv  # + 程序级语料差分与链接运行门

python3 tests/check_neg.py                  # 拒绝路径：退出码 + 诊断位置 + 关键字
python3 tests/check_enc.py                  # 134 条编码，逐条对 oracle
python3 tests/check_corpus.py tests/asm tests/asm-gnu --bin ./.build/yh_asm
python3 tests/check_obj.py ./.build/yh_asm tests/asm
python3 tests/check_obj.py ./.build/yh_asm tests/asm --target darwin \
    --snapshot tests/darwin-snapshot.txt    # Mach-O 字节快照（可在 Linux 跑）
python3 tests/elf_link_native.py ../tmp/inv --bin ./.build/yh_asm
python3 tests/shadow-build.py --seed bin/yh-linux-arm64 --out tmp/shadow
```

**oracle 解析**：`LLVM_MC` 环境变量 → Homebrew 的
`/opt/homebrew/opt/llvm/bin/llvm-mc` → `clang` 的集成汇编器（同一个 LLVM MC
后端；`clang --target=aarch64-linux-gnu -c`）。所以只有 clang 的宿主（WSL）
也能跑完整差分：`check_enc.py` 在 clang 模式下改为「按顺序逐条比对」，
比文本比对更严。`check_corpus.py` 会把实际使用的 oracle 打进输出。

**语料**：程序级语料由 `tools/yh-toolchain-inventory.py` 重建到 `tmp/inv`
（单文件 `yh --emit-asm` + 模块 `yh build` 的 `.build/asm/*.s`）。

**链接运行门**：Linux 宿主用 `aarch64-linux-gnu-ld` + `qemu-aarch64`
（`tests/elf/start-linux.s` 提供 `_start`，`tests/elf/yhr-linux.s` 提供
`read/write/open/close/_Exit/abs/strtoul` 等运行时符号桩）；macOS 宿主用容器门
`elf_link_check.py`，需要 docker 与镜像：

```bash
docker build -t yh-link-elf:latest tests/docker
```

两边都是**差分式**判定：同一份汇编分别由本工具与 oracle 汇编，各自链接后
运行比对退出码与标准输出；「两边同样链不上」「两边都拒绝汇编」计跳过并记录
名字与原因，只有「一边成功一边失败」或「行为不同」才判失败。

`macho_corpus_check.py`、`macho_link_run.py` 要宿主有 macOS 的 `clang` 与
`ld`，只在 macOS 上跑；Linux 上用 `check_obj.py --target darwin` 的字节快照
守住「Darwin 输出没变」。

五层自检都通过 `.build/yh_asm` 的退出码汇报：

| 层 | 数量 | 内容 |
| --- | --- | --- |
| 编码器向量 | 134 | 单条指令 → 期望机器字，参考值取自 llvm-mc（含标量浮点与浮点访存） |
| 公共层 | 36 | 位域、寄存器折叠、逻辑立即数正反例、编码回环、条件码、移位助记符 |
| 端到端 | 25 | 固定源码走完扫描→解析→回填→重定位，核对 16 个机器字与 9 条重定位（GOT 两类、未定义符号、已定义的局部符号三种都出重定位） |
| GNU 方言端到端 | 18 | 编译器 Linux 目标实际发射的形态：裸符号 `adrp`、`add`/访存的 `:lo12:`，核对 10 个机器字与 8 条重定位（275/277/278/284/285/286/283） |
| 拒绝层 | 25 | 契约 §8 的拒绝清单逐条核对：负例必须被拒绝，紧跟的正向对照必须通过（防「全部拒绝」式假通过）；诊断本身由 `check_neg.py` 在子进程里验 |

## 已知边界（遇到即报诊断）

- **浮点**：只支持标量，族与形态见契约 §3。寄存器间 `fmov`、`fabs/fneg`、
  带舍入模式或 `#fbits` 的转换、`fcmp #0.0`、128 位 `q` 寄存器都不支持。
- **GOT**：只有 64 位形态（LP64 的限制，clang/llvm-mc 同样拒绝更窄的 GOT 访存）。
- **`.size`**：只接受纯数字（`.size f, 8`）；符号表达式与 `. - sym` 不支持
  （契约 §4/§8 已按实测收窄）。编译器语料里没有 `.size`，暂无消费者。
- **分支距离**：`b`/`bl` ±128 MB；`b.cond`/`cbz`/`cbnz` ±256 KB。越界报诊断；
  局部条件远分支的单调放宽**不做**。编译器最大的模块 `.text` 已经约 413 KB
  （`yh-parse`，8 个模块实测 35 KB–413 KB），超过条件分支的上限，但当前没有
  出现越界的条件分支——编译器只在短距离上用条件分支，8 个模块在本工具与
  clang 下都能汇编。真要出现长距离条件分支，两边都会报错。
- **符号名与寄存器同名**：`w12` 这类名字在**标签位置**也被拒绝（clang 接受
  标签定义、但同样拒绝 `bl w12`）。根因在编译器发射（用户符号未避让寄存器
  名），记在 [docs/todo.md](../docs/todo.md)；`tests/yh-run/run/14-many-args.yh`
  与 `37-many-args-noprintf.yh` 属于这一类，两边都汇编不了。
- **Mach-O 目标的差异**：Mach-O 对象只有一个无名段，全部节挂在它下面；
  `PAGEOFF12` 的 length 一律 2（是立即数字段字节数，与访问宽度无关）；
  同节分支（哪怕目标是 global）汇编期就定死、不发重定位，而 ELF 对同节分支
  照发 `CALL26`/`JUMP26`；条件分支只能跳本节局部标签，否则写出阶段报错；
  `adrp` 要求显式 `@PAGE`（GNU 方言的裸符号只在 `-t linux` 接受）。
- 可执行文件链接（ELF 的 TC4、Mach-O 的 TC9–TC10）不在本项目范围内，
  属于 [`link/`](../link/README.md) 链接器项目。

## 下游：`link/` 链接器的进展（2026-10-13）

**Linux/AArch64 的静态 ELF 链接已完成**（`link/` 项目的 TC4）：能把本项目
产出的 `ELF64 ET_REL` 对象链成可装载、可运行的静态 `ET_EXEC` 映像。
两个项目仍然**互不 import**，只通过对象文件交接。

对本项目有两点直接影响：

1. **契约已被下游消费并验证**：链接器实现了契约 §6 白名单里的 12 种重定位
   （257/275/277/278/284/285/286/280/282/283/311/312），并对每种做**指令形态
   校验**（例如 `ADR_PREL_PG_HI21` 的目标必须是 `adrp`）。本项目发射的重定位
   类型若与契约不符，下游会直接报错，不会静默算错。
2. **本项目的一份实现细节被下游依赖并已确认**：`$x`/`$d` 映射符号与本项目的
   节命名（`.text`/`.rodata`/`.data`/`.bss`）都按约定被识别。链接器**不**把
   映射符号当可解析符号（早期把它当普通局部符号会导致跨对象分支跳错）。

验收闭环：`asm/.build/yh_asm` + `link/.build/yh_link` 跑
`python3 link/tests/link_accept.py`（汇编 → 链接 → 结构断言 → 真跑比对退出码）
与 `python3 link/tests/link_diff_regress.py`（与 GNU ld 差分）。当前语料见
`link/tests/asm/`，7 个用例全绿。
