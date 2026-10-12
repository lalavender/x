# yh-link 独立项目与首版汇编子集契约 v2

日期：2026-10-03（2026-10-04 并入标量浮点与 Mach-O 出口章节；
2026-10-12 升 v2：并入 GNU 方言接受面、实测拒绝清单与几处事实修正）。
状态：**稳定化中**——ELF64 与 Mach-O 两个出口都能产出对象；汇编器
**当前不接入编译器**（2026-10-12 断电：仓库根不再产出 `yh_link` 名字，
`make yh-link` 别名与入库副本已删除），编译器逐模块汇编步回落系统 cc。
稳定化的工作包与判据见
[yh-asm 汇编器稳定化实施方案](../02-plan/yh-asm汇编器稳定化实施方案.md)。

上位文档：[yh-asm 与 yh-link 设计](yh-asm与yh-link设计.md)、
[yh-asm 与 yh-link 分期实施方案](../02-plan/yh-asm与yh-link实施方案.md)。

## 1. 与上位计划的结构偏差

上位计划把 obj/asm/link 作为 `compiler/` 下的三个源码模块。用户决定：
`link/` 作为**独立项目**开发（`project.toml` 的 `name = "yh_link"`，源码根
`src/`），不复用编译器源码树。

后果与边界：

- `compiler/` 不 import `link/` 的任何模块。`yh asm` / `yh link` 子命令接线
  （计划 TC5）属于后续任务，届时由驱动以显式依赖或独立二进制分派实现。
- 首轮交付物曾是 `link/.build/yh_link` 一个可执行文件，只提供 `asm` 子命令。
  **2026-10-07 起按职责归位**（[归位记录](../01-finished/yh汇编器与链接器项目归位-2026-10-07.md)）：
  汇编器整体迁到独立项目 `asm/`（`yh_asm`），`link/` 只做「对象 → 可执行映像」。
  本文的助记符/伪指令/重定位契约对 `asm/` 继续有效。
- `asm/` 内部模块依赖方向：`asm → obj`、`main → asm/obj`。
  obj 不依赖 parse/ir/backend/cmd，不引入语言 AST。

## 2. 冻结子集的来源

清单来自仓库语料的实测发射（首版冻结时 `tests/yh-run/run/` +
`tests/yh-run/pass/` 共 61 个文件，`yh --emit-asm`），不是推测。
2026-10-12 起语料由 `tools/yh-toolchain-inventory.py` 重建：单文件语料
161 个（`tests/yh-run/run` 153 + `pass` 8）+ 编译器自身 8 个模块，
共 169 个 `.s`。重新采集命令：

```text
python3 tools/yh-toolchain-inventory.py --compiler ./yh --output tmp/inv
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
sxtb sxth sxtw uxtb uxth uxtw sbfx
```

`uxtw` 在编译器运行时代码里以「扩展别名」形态出现（`uxtw x27, w27` 编码为
UBFM），v1 文档漏列，2026-10-12 盘点实测 95 次后补入。

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
  两者不可互换。`.balign` 的 N 必须是 2 的幂（非 2 的幂报诊断后拒绝）；
  `.p2align` 的指数限定 0..16。
- `.zero/.skip N` 在 `.bss` 只增长内存尺寸，在其他段补零字节。
- `.size` 首版只接受**纯数字**（`.size f, 8`）；符号表达式与「同节两符号之差」
  都不支持——2026-10-12 实测 `.size f, h - f`、`.size f, . - f` 均报
  「此处需要一个纯数字（不支持符号重定位）」，v1 文档里的「支持单个符号 ± 整数
  与同节两符号之差」与实际不符。编译器语料里没有 `.size`（盘点实测只有
  `.globl` 与 `.p2align`），按「不做」处理，出现真实消费者时再单独设计。
- `.type` / `.size` 首版只识别 `%function` 与 `%object`；其他类型值报未支持。

## 5. 表达式与寄存器语法

- 立即数：十进制、`0x` 十六进制、`-` 负号；`#` 前缀可选。
- 表达式只允许：整数、符号、符号 ± 整数；任意算术表达式、多个符号、
  跨节差一律拒绝。（`.size` 的符号表达式在 v2 明确为不支持，见 §4。）
- 寄存器：`x0..x30`、`w0..w30`、`sp`、`wsp`、`xzr`、`wzr`、`s0..s31`、`d0..d31`。
  编码时区分编号 31 的 SP 与 ZR：SP 出现在基址/目的/源位置合法，
  ZR 出现在源位置等价 `x31`，出现在目的位置编码为 31（丢弃结果）。
  写成 `x31`/`w31` 的**不拒绝**（与 LLVM 一致：`mov x31, x0`、`add x31, x0, x1`
  在本工具与 clang 下都成功，按位置解释为 SP 或 ZR）；`cbz sp, ...` 这类
  「SP 出现在 ZR 位置」仍然拒绝。
- 寻址形态：`[Rn]`, `[Rn, #imm]`, `[Rn, Rm]`, `[Rn, Rm, LSL #s]`,
  `[Rn, #imm]!`, `[Rn], #imm`, `[sp, #imm]`。
  未缩放偏移（`-256..255`）与 `[Rn, #neg]` 非法。
- 符号修饰符：`:lo12:` 与 `@PAGEOFF` 等价，`@PAGE` 只跟在 `adrp` 后面
  （两种写法都接受）。
- **GNU 方言的页取址与低 12 位（v2 起接受）**：`adrp Xd, sym` 的裸符号与
  `sym@PAGE` 同义；`add Xd, Xn, :lo12:sym` 与 `sym@PAGEOFF` 同义，访存位置的
  `:lo12:sym` 同理。编译器 Linux 目标发射的正是这一套（实测编译器 8 个模块里
  有 13,680 条裸符号 `adrp` 与等量的 `:lo12:`），v1 只收 `@PAGE/@PAGEOFF` 时
  这些模块一条都汇编不了。裸符号**只在 ELF 目标接受**：`-t darwin` 仍要求
  显式 `@PAGE`，Mach-O 的输入契约不因此放宽。
- 分支目标只接受标签或数字：`b sym@PAGEOFF`、`b.eq sym@PAGE`、`cbz x0, sym@PAGE`
  一律拒绝（v1 曾把它们静默编成 `b #0` 自跳转——修饰符的语义是「取符号地址的
  某一段」，对分支没有意义）。
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
  **未定义的 `.` 开头符号必须报错**（局部符号不允许未定义；clang 对
  `b .Lmissing` 报 "Undefined temporary symbol" 同理）——v1 会把它降级成
  未定义全局符号，链接器于是去别的对象里找同名符号，语义就变了。
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

以下输入必须报诊断，不得生成对象（v2 按 2026-10-12 实测重写；每条都有用例，
内建拒绝层 25 条 + `asm/tests/asm-neg/` 与 `asm/tests/check_neg.py` 10 条）：

未知助记符、未知伪指令、立即数超出编码范围（`movz x0, #0x10000`、
`add x0, x1, #4096`）、逻辑立即数不是合法重复模式、位移未对齐
（`ldr x0, [x1, #3]`）、位宽错配（`mov x0, w1`、`strh x0, [x1]`）、
SP 出现在 ZR 位置（如 `cbz sp, .L`）、分支位移越界
（`b` 超过 ±128 MB、`b.cond`/`cbz`/`cbnz` 超过 ±256 KB）、
分支目标带符号修饰符（`b sym@PAGEOFF`）、`:lo12:` 用在既不是加减低 12 位
也不是访存位移的位置、`.balign` 非 2 的幂（必须带诊断）、`.p2align` 指数
超出 0..16、`.type` 取值不是 `%function`/`%object`、`.size` 用符号表达式、
多符号表达式（`.xword a + b`）、跨节符号差、未定义的 `.` 开头局部符号、
符号重复定义、GOT 窄访问（LP64 下只有 64 位）、块注释未闭合、非法字符、
整数字面量超出范围。

以下**不拒绝**（v2 按实测与生态对齐修正 v1 的写法）：

- `x31`/`w31` 写法（按位置解释为 SP/ZR，clang 同样接受）；
- `.text` 里的 `.zero`（按 §4 规则用 0 填充，代码节里补零属于用户输入语义，
  不是语法错误）；
- 未定义的外部符号（对象阶段记为 undefined，链接期解决）。

注意「未定义的外部符号」与「未定义的 `.` 开头局部符号」是两件事：后者见 §7，
必须拒绝。
