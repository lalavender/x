# yh-link 标量浮点与 GOT 重定位：语料全覆盖

> 后续：2026-10-07 工具链按职责归位后，本文描述的汇编器实现源码路径
> 从 `link/src/...` 变为 `asm/src/...`，验收门从 `link/tests/...` 变为
> `asm/tests/...`；`link/` 改为链接器项目。见
> [归位记录](yh汇编器与链接器项目归位-2026-10-07.md)。

日期：2026-10-03。状态：**完成**。上位方案见
[yh-link 平台与架构矩阵方案](../02-plan/yh-link平台与架构矩阵方案.md) 的 P1-1、P1-2。

## 结果

`link/tests/check_corpus.py` 的 61 个语料**全部汇编成功，逐字节比对 0 不一致，
跳过数 10 → 0**。此前被拒的两类——浮点标量（10 个文件）与 GOT 重定位
（7 个文件）——都已补齐。跳过数与不一致数同时为零，说明契约覆盖已经追上
编译器实际发射的 AArch64 汇编。

## GOT 重定位

只有两种形态，全部由语料实测确定：

| 源码 | 重定位 | 号 |
| --- | --- | --- |
| `adrp x, sym@GOTPAGE` | `R_AARCH64_LD64_GOTPAGE_LO21` | 311 |
| `ldr x, [x, sym@GOTPAGEOFF]` | `R_AARCH64_LD64_GOT_LO12_NC` | 312 |

实现落在既有的三处：`40_parse.yh` 的表达式修饰符多两个 `EX_` 取值，
`52_parse_ins.yh` / `51_parse_alu.yh` 各接一种，`60_assemble.yh` 映射成类型号。

这两类比页寻址还要晚——**GOT 项本身是链接器建的**，汇编期连它的地址都不
存在，所以永远只出重定位，不可能回填。

**宽度限制不是我们偷懒**：LP64 下 GOT 只有 64 位形态，llvm-mc 对
`ldr w, [x, :got_lo12:sym]` 直接报
`4 byte unchecked GOT load/store relocation is not supported in LP64`。
本工具对非 64 位 GOT 访存也报诊断，而不是凑一个近似编码。

## 标量浮点

范围由语料实测反推，不是照手册铺开：

```text
fadd fsub fmul fdiv  Vd, Vn, Vm     三源算术
fcmp                 Vn, Vm
fcvt                 Vd, Vn         s 与 d 互转
fcvtzs               Rd, Vn         浮点 → 整数
scvtf                Vd, Rn         整数 → 浮点
fmov                 Vd, Rn         通用 → 浮点（按位搬移）
```

**位布局全部由 `llvm-mc --show-encoding` 逐条反推**，做法是固定一条指令、
只变一个寄存器，看哪些位跟着变：

| 字段 | 位置 |
| --- | --- |
| Rd | 4:0 |
| Rn | 9:5 |
| Rm | 20:16 |
| 类型（s/d） | 各族的位 22 或 15 |

各族基址：三源算术 `0x1e200800`（位 15:12 是 0=fmul 1=fdiv 2=fadd 3=fsub）、
`fcmp 0x1e202000`、`fcvt 0x1e224000`（源类型在位 22、目的类型在位 15）、
`fcvtzs 0x1e380000`、`scvtf 0x1e220000`、`fmov 0x1e270000`。

### 浮点访存：一行就够

`ldr`/`str` 的数据寄存器可以是 `s`/`d`，编码是**同宽整数访存或上 V 位
（bit26）**：

```text
str x0, [x10] = 0xf9000140    str d0, [x10] = 0xfd000140
ldr w0, [x10] = 0xb9400140    ldr s0, [x10] = 0xbd400140
```

所以没有另写一套访存编码，只在 `p_mem_insn` 里加了一个 `vbit`，宽度由寄存器
类别决定（`s`→32 位、`d`→64 位），在各发射点或上去。这也顺带说明为什么
浮点访存的重定位类型跟整数一样（`LDST64` 等）——位域含义完全相同。

### 不做的形态

寄存器间 `fmov`、`fabs/fneg`、带舍入模式或 `#fbits` 的转换、`fcmp #0.0`、
128 位 `q` 寄存器。语料里没有，遇到即报诊断。

## 验证

| 门 | 命令 | 结果 |
| --- | --- | --- |
| 构建与自检 | `cd link && ../yh run` 后 `./.build/yh_link` | 退出码 0 |
| 编码器向量 | `python3 tests/check_enc.py` | 129 条，不一致 0（新增 22 条浮点） |
| 全量语料 | `python3 tests/check_corpus.py` | 61 个：成功 61，不一致 0，**跳过 0** |
| 定向语料 | `python3 tests/check_corpus.py tests/asm` | 8 个：成功 8，不一致 0 |
| 结构与确定性 | `python3 tests/check_obj.py ./.build/yh_link ../tmp/inv` | 61 个对象，结构 0，非确定 0 |
| 容器链接门 | `python3 tests/elf_link_check.py` | 61 个对象；行为一致 54，不一致 0，7 个两边同样链不上而跳过 |

自检里新增的浮点条目也会被 `check_enc.py` 拿去问 llvm-mc，所以期望值不是
自说自话。端到端自检里加了 GOT 两条，覆盖「GOT / 未定义符号 / 已定义局部
符号」三种都出重定位。

## 顺带修掉的两处

1. **容器门在静态链接阶段的两侧标记互相覆盖**：参照侧的结果写进了本工具侧
   的变量，等于参照链接失败也会被算成本工具的失败。已改成两级各自独立判定，
   并在「两边都失败」时按差分语义跳过而不是误判——门只在**两边结果不同**时
   报错。
2. **`check_obj.py` 的重定位白名单**补上 311/312。

## 新增语料

- `tests/asm/07-got.s` —— 两种 GOT 形态。
- `tests/asm/08-float.s` —— 六族 + 浮点访存，含零寄存器与高位寄存器。

## 已知边界

容器门里 7 个语料跳过，原因是 yh 运行时的外部符号（`__Exit` / `_strtoul` /
`_open` / `_close` / `_abs`）在 `tests/elf/yhr.s` 里没有桩，**两边同样链不上**。
差分门按设计跳过而不是误判。补桩后这 7 个就会进入真正的运行比对；`_strtoul`
需要真实现，其余都是一行系统调用，值得补时再补。
