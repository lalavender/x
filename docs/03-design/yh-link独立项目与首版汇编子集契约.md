# yh-link 独立项目与首版汇编子集契约 v1

日期：2026-10-03（2026-10-04 并入标量浮点与 Mach-O 出口章节）。
状态：**首版已实施**——ELF64 与 Mach-O 两个出口都能产出对象，编译器逐模块
汇编步已切换过来。

上位文档：[yh-asm 与 yh-link 设计](yh-asm与yh-link设计.md)、
[yh-asm 与 yh-link 分期实施方案](../02-plan/yh-asm与yh-link实施方案.md)。

## 1. 与上位计划的结构偏差

上位计划把 obj/asm/link 作为 `compiler/` 下的三个源码模块。用户决定：
`link/` 作为**独立项目**开发（`project.toml` 的 `name = "yh_link"`，源码根
`src/`），不复用编译器源码树。

后果与边界：

- `compiler/` 不 import `link/` 的任何模块。`yh asm` / `yh link` 子命令接线
  （计划 TC5）属于后续任务，届时由驱动以显式依赖或独立二进制分派实现。
- 首轮交付物是 `link/.build/yh_link` 一个可执行文件，先只提供 `asm` 子命令。
- `link/` 内部模块依赖方向：`asm → obj`、`main → asm/obj`。
  obj 不依赖 parse/ir/backend/cmd，不引入语言 AST。

## 2. 冻结子集的来源

清单来自仓库语料的实测发射（`tests/yh-run/run/` + `tests/yh-run/pass/` 共
61 个文件，`yh --emit-asm`），不是推测。重新采集命令：

```text
./yh --emit-asm tests/yh-run/run/<file>.yh > tmp/yh-toolchain/tc0/<file>.s
```

首版覆盖整数、访存、分支与地址四类，此后并入标量浮点
（`fadd/fsub/fmul/fdiv/fcmp/fcvt/fcvtzs/scvtf/ucvtf/fmov`，见 §3）。
`cset/csel` 的浮点形态仍未支持；遇到未支持形态必须报"未支持"而不是静默跳过。

## 3. 助记符白名单（v1）

整数与常量搬运：

```text
add adds sub subs cmp tst neg mov movz movk mvn
and ands orr eor bic mul msub sdiv udiv
lsl lslv lsrv asrv
sxtb sxth sxtw uxtb uxth sbfx
```

访存（含 SP 基准、后索引写回、缩放与非缩放偏移）：

```text
ldr ldrb ldrh ldrsb ldrsw ldrsh str strb strh stp ldp
```

控制流与选择：

```text
b bl br blr ret cbz cbnz b.cond beq bne blt ble bgt bge bcc bcs bcs(别名)
csel cset
```

地址与内核接口：

```text
adrp nop brk svc hlt dsb dmb isb
```

标量浮点（v1 补入，全部由语料实测覆盖）：

```text
fadd fsub fmul fdiv  Vd, Vn, Vm     三源算术，三个寄存器必须同宽度
fcmp                 Vn, Vm
fcvt                 Vd, Vn         s 与 d 互转，两个寄存器必须异宽度
fcvtzs               Rd, Vn         浮点转整数（向零取整）
scvtf                Vd, Rn         整数转浮点（源寄存器有无符号之分时用下一行）
ucvtf                Vd, Rn         无符号整数转浮点，机器码与 scvtf 差 bit16
fmov                 Vd, Rn         通用寄存器按位搬到浮点寄存器
```

`ldr`/`str` 的数据寄存器可以是 `s`/`d` 浮点寄存器：编码与同宽整数访存
完全一致，只多一个 V 位（bit26）。浮点子集**不支持**寄存器间 `fmov`、
`fabs/fneg`、带舍入模式或 `#fbits` 的转换、`fcmp #0.0`、128 位的 `q`
寄存器，遇到即报诊断。

字段位置在各族里一致：Rd 在 4:0、Rn 在 9:5、Rm 在 20:16。

`b.cond` 完整条件码：`eq ne cs cc mi pl vs vc hi ls ge lt gt le al nv`。

## 4. 伪指令白名单（v1）

```text
.text .data .bss .section（仅 .rodata）
.globl .global .local
.balign .p2align
.byte .hword .word .xword .quad .zero .skip
.type .size（仅 %function / %object / %function）
```

规则：

- `.balign N` 是字节对齐，代码段用 `nop` 填充；`.p2align N` 是二的幂指数。
  两者不可互换。
- `.zero/.skip N` 在 `.bss` 只增长内存尺寸，在其他段补零字节。
- `.size` 的表达式只接受「单个符号 ± 整数」和「同节两符号之差」。
- `.type` / `.size` 首版只识别 `%function` 与 `%object`；其他类型值报未支持。

## 5. 表达式与寄存器语法

- 立即数：十进制、`0x` 十六进制、`-` 负号；`#` 前缀可选。
- 表达式只允许：整数、符号、符号 ± 整数、同节符号之差（`.size` 用）。
  任意算术表达式、多个符号、跨节差一律拒绝。
- 寄存器：`x0..x30`、`w0..w30`、`sp`、`wsp`、`xzr`、`wzr`、`s0..s31`、`d0..d31`。
  编码时区分编号 31 的 SP 与 ZR：SP 出现在基址/目的/源位置合法，
  ZR 出现在源位置等价 `x31`，出现在目的位置编码为 31（丢弃结果）。
- 寻址形态：`[Rn]`, `[Rn, #imm]`, `[Rn, Rm]`, `[Rn, Rm, LSL #s]`,
  `[Rn, #imm]!`, `[Rn], #imm`, `[sp, #imm]`。
  未缩放偏移（`-256..255`）与 `[Rn, #neg]` 非法。
- 符号修饰符：`:lo12:` 与 `@PAGEOFF` 等价，`@PAGE` 只跟在 `adrp` 后面
  （两种写法都接受）。仓库语料的 `yh --emit-asm` 输出用的是 `@PAGE/@PAGEOFF`，
  所以它是首版的输入契约；`:lo12:` 是为 GNU 风格手写汇编留的等价入口。
- 条件码别名 `hs`=`cs`、`lo`=`cc`，`b.hs`/`b.lo` 与 `b.cs`/`b.cc` 同码。

## 6. 重定位白名单（v1）

类型号以 llvm-mc 实测为准（`tests/check_corpus.py` 会逐条比对类型号，
两边不一致即判失败）。

| 类型 | 号 | 产生条件 |
| --- | --- | --- |
| `R_AARCH64_ABS64` | 257 | 数据中 8 字节绝对符号地址（`.xword sym`） |
| `R_AARCH64_ADR_PREL_PG_HI21` | 275 | `adrp sym@PAGE` |
| `R_AARCH64_ADD_ABS_LO12_NC` | 277 | `add Xd, Xn, sym@PAGEOFF` |
| `R_AARCH64_LDST8_ABS_LO12_NC` | 278 | `sym@PAGEOFF` 作 1 字节访存位移 |
| `R_AARCH64_CONDBR19` | 280 | `b.cond sym`、`cbz/cbnz sym` |
| `R_AARCH64_JUMP26` | 282 | `b sym` |
| `R_AARCH64_CALL26` | 283 | `bl sym` |
| `R_AARCH64_LDST16_ABS_LO12_NC` | 284 | `sym@PAGEOFF` 作 2 字节访存位移 |
| `R_AARCH64_LDST32_ABS_LO12_NC` | 285 | `sym@PAGEOFF` 作 4 字节访存位移 |
| `R_AARCH64_LDST64_ABS_LO12_NC` | 286 | `sym@PAGEOFF` 作 8 字节访存位移 |
| `R_AARCH64_LD64_GOTPAGE_LO21` | 311 | `adrp x, sym@GOTPAGE` |
| `R_AARCH64_LD64_GOT_LO12_NC` | 312 | `ldr x, [x, sym@GOTPAGEOFF]` |

`cbz/cbnz` 用 `CONDBR19`（与 llvm-mc 一致），不用 `TSTBR14`（那是 `tbz/tbnz` 的）。
访存位移按访问宽度取 LDST\* 系列，imm12 里存的是「字节偏移 ÷ 访问宽度」。

**只有「局部符号 + 同节 + 分支」能在汇编阶段直接修正**：位移只跟节内两个
偏移有关，与节最终放在哪里无关。GOT 两类比这更晚——GOT 项要等链接器建立。

页寻址（`adrp`）、低 12 位（`@PAGEOFF`）、绝对地址（`.xword`）**即使目标
符号已定义也必须留重定位**——它们的值取决于节的最终地址。链接器把 `.text`
放在非 4KiB 对齐处时，汇编期算出的 `S & 0xFFF` 就是错的。全局符号的分支同理：
链接器可能把它重定向到别的目标文件里的同名符号。

符号地址为 S、addend 为 A、重定位位置为 P：PC 相对用 `S+A−P`；
页寻址先对 S 和 P 分别取 4KiB 页再求差；访存低 12 位还要按访问宽度右移。

符号绑定按 GNU as 的约定：没有 `.globl` 的标签一律是局部符号，
没有定义的外部引用一律是全局符号（ELF 不允许未定义的局部符号）。

## 7. 输出契约

ELF64、小端、`EM_AARCH64`(183)、`ET_REL`(1)。节集合与顺序：

1. 内容节，固定次序 `.text`、`.rodata`、`.data`、`.bss`(NOBITS)，空节不出现；
2. 每个需要重定位的节的 `.rela.<sec>`；
3. 收尾三节 `.symtab`、`.strtab`、`.shstrtab`。

- 符号表：local 在前、global 在后，`sh_info` = 第一个 global 的下标。
- `.` 开头的符号（`.L1`、`.LD1`）一律记为 local，前向引用时也如此。
- AArch64 mapping symbols（`$x`/`$d`）按节内容布局自动生成。
- 对象字节可重复：相同输入产出逐字节相同的 `.o`。
- 代码节的对齐填充用 NOP（`0xd503201f`），数据节填 0。

## 7bis. Mach-O 出口契约（`-t darwin`）

同一份汇编文本可以出两种对象，助记符与伪指令白名单完全共用；差别只在容器。
`-t darwin` 产出 Mach-O 64 位 `MH_OBJECT`，`cputype`/`cpusubtype` 为
`CPU_TYPE_ARM64`/`CPU_SUBTYPE_ARM64_ALL`。

节映射：

| 上下文节 | Mach-O 节 | flags |
|---|---|---|
| `.text` | `__TEXT,__text` | `S_ATTR_PURE_INSTRUCTIONS \| S_ATTR_SOME_INSTRUCTIONS` |
| `.rodata` | `__TEXT,__const` | 0 |
| `.data` | `__DATA,__data` | 0 |
| `.bss` | `__DATA,__bss` | `S_ZEROFILL` |

布局（与 clang 的形态一致）：头(32) → `LC_SEGMENT_64` → `LC_BUILD_VERSION`
→ `LC_SYMTAB` → `LC_DYSYMTAB`(80) → 节数据 → 重定位 → 符号表 → 字符串表。

- **只有一个段，且 segname 全 0**；链接时各节去哪个段由节自己的 `segname`
  记录。这与可执行文件里的 `__TEXT`/`__DATA` 是两个层次。
- 节的 `addr` 取「从 0 起的累计偏移」，符号 `n_value` = 所在节 `addr` +
  节内偏移。
- 节对齐：上下文的 `Section.align` 是**字节**对齐，`section_64.align` 写的是
  2 的幂次数。节大小取 `data.len`，不取 `memsz`（PROGBITS 节不维护 memsz）；
  ZEROFILL 节反过来只取 `memsz`。
- 符号顺序：local → 已定义 global → 未定义 global。`LC_DYSYMTAB` 的
  `ilocalsym`/`iextdefsym`/`iundefsym` 三个区间靠这个顺序表达。
- 重定位按节分组，**节内按地址降序**。

重定位映射（实测自 clang，非手册）：

| 汇编层类别 | Mach-O 类型 | pcrel | length |
|---|---|---|---|
| ABS64 (257) | `UNSIGNED` (0) | 0 | 3 |
| `ADR_PREL_PG_HI21` (275) | `PAGE21` (3) | 1 | 2 |
| `ADD_ABS_LO12_NC` (277) | `PAGEOFF12` (4) | 0 | 2 |
| `LDST8/16/32/64` (278/284/285/286) | `PAGEOFF12` (4) | 0 | 2 |
| `JUMP26`/`CALL26` (282/283) | `BRANCH26` (2) | 1 | 2 |
| `LD64_GOTPAGE_LO21` (311) | `GOT_LOAD_PAGE21` (5) | 1 | 2 |
| `LD64_GOT_LO12_NC` (312) | `GOT_LOAD_PAGEOFF12` (6) | 0 | 2 |
| `CONDBR19` (280) | 无对应类型 | — | — |

- `PAGEOFF12` 的 length **一律 2**：Mach-O 的 length 是立即数字段占几个字节，
  与访问宽度无关，所以整数访存与浮点访存同值，不需要像 ELF 的 `LDST*` 那样
  按 1/2/4/8 分派。
- 重定位字：`(type << 28) | (1 << 27) | (length << 25) | (pcrel << 24) |
  (symbolnum & 0xffffff)`。

**同节分支的规则与 ELF 相反。** ELF 对同节分支照发 `CALL26`/`JUMP26`（符号可能
被链接器预置到别的目标文件）；Mach-O 只对**外部与跨节**符号发 `BRANCH26`，
同节分支——哪怕目标是 global——汇编期就把偏移定死，不发重定位。所以：

- 汇编阶段的「同节可定死」判定要按目标格式分派：ELF 额外要求符号是 LOCAL，
  Mach-O 只要求符号在本节有定义；
- 写出阶段的过滤必须用同一条判定（`obj.mo_sym_in_sec`），否则会出现
  「不发重定位、也没回填立即数」的零偏移分支。

`PAGE21` / `PAGEOFF12` / `UNSIGNED` / `GOT_*` 不受影响，一律照发。

条件分支在 Mach-O 里只能跳本节局部标签（clang 报
`conditional branch requires assembler-local label`），`-t darwin` 在写出
阶段拒绝，不产出非法对象。

## 8. 明确的拒绝清单

以下输入首版必须报诊断，不得生成对象：

未知助记符、未知伪指令、非法寄存器编号（`x31`、`w31` 之外的非 SP/ZR 写法）、
立即数超出编码范围、位移未对齐、位宽错配（`mov x0, w1`）、
SP 出现在 ZR 位置（如 `cbz sp, .L`）、分支位移越界、
`:lo12:` 修饰符用在非 `add` 指令、`.zero` 出现在 `.text`、
多符号表达式、跨节符号差、未定义符号（对象阶段记为 undefined，不算错误）。
