# 65 · ARM 与 ARM64 后端

> **一句话**：ARM/ARM64 后端和 x86-64 后端实现**同一批函数接口**
> （`load`/`store`/`gen_opi`/`gfunc_call`/`gfunc_prolog`…），
> 只是把"指令"换成 ARM 的。前端 `tccgen.c` 一行都不用改。
>
> 对应源码：`src/targets/arm-gen.c`（2151 行）、`arm-link.c`、
> `arm64-gen.c`（1802 行）、`arm64-link.c`、`arm-asm.c`、`i386-asm.h` 对应物。

---

## 第 0 站：和 x86-64 对照（`TARGET_DEFS_ONLY` 段）

每个后端开头都有一段"配置区"（`#ifdef TARGET_DEFS_ONLY`），定义：

| 宏 | x86-64 | ARM | ARM64 |
|---|---|---|---|
| `NB_REGS` | 25 | 若干整数+浮点 | 32+32 |
| `RC_INT` | 0x1 | ARM 整数类 | AArch64 整数类 |
| `PTR_SIZE` | 8 | 4 | 8 |
| `LDOUBLE_SIZE` | 16 | 8/16 | 16 |
| `REG_IRET` | `rax` | `r0` | `x0` |
| `REG_FRET` | `xmm0` | `d0`/`s0` | `d0`/`s0` |
| `ELF_START_ADDR` | `0x400000` | `0x8000`/`0x10000` | `0x400000` |
| `EM_TCC_TARGET` | `EM_X86_64` | `EM_ARM` | `EM_AARCH64` |

**前端读这些宏（通过 `#include` 两次的机制）来适配。**

---

## 第 1 站：ARM 的特点

ARM（32 位）后端：

- **几乎每条指令都能条件执行**（`addeq`、`moveq`…），TCC 会利用这点；
- **`ldr`/`str`** 代替 x86 的 `mov` 访存；
- **寄存器库**：`r0`~`r15`，`r15` 是 PC，`r13` 是 SP，`r14` 是 LR（返回地址）；
- **调用约定**：`r0`~`r3` 传参，浮点走 `s0`/`d0`；
- **函数返回地址在 `lr`**，prolog 常要保存它。

`arm-gen.c` 里的函数名和 x86-64 一样：`load`、`store`、`gen_opi`、
`gfunc_call`、`gfunc_prolog`…**接口一致，实现不同。**

---

## 第 2 站：ARM64 的特点

ARM64（AArch64）后端：

- 固定 4 字节指令（不是 Thumb 变长）；
- **`x0`~`x7` 传参**，`x0` 返回整数，`d0`/`s0` 返回浮点；
- `ldr`/`str`、`mov`、`add`/`sub`、`cmp`/`b.cond`；
- `gen_vla_*` 等接口和 x86-64 类似。

`arm64-gen.c` 里有 `classify_x86_64_arg` 的对应物（但 ARM64 的 ABI 规则不同，
叫 `classify_aarch64_*` 之类），以及 `gfunc_call`/`gfunc_prolog`/`gfunc_epilog`。

---

## 第 3 站：链接端的差异（`arm-link.c` / `arm64-link.c`）

第 53 篇说重定位是后端相关的。ARM 有 ARM 自己的重定位类型
（`R_ARM_ABS32`、`R_ARM_CALL`、`R_ARM_GOT32`…），ARM64 也有
（`R_AARCH64_ABS64`、`R_AARCH64_CALL26`…）。

每个 `*-link.c` 实现：

```c
int code_reloc(int reloc_type);        /* 代码/数据重定位 */
int gotplt_entry_type(int reloc_type); /* 要不要 GOT/PLT */
unsigned create_plt_entry(...);        /* 造 PLT 入口 */
void relocate_init(Section *sr);
void relocate(TCCState *s1, ElfW_Rel *rel, int type,
              unsigned char *ptr, addr_t addr, addr_t val);   /* ★ 回填 */
```

第 53 篇看的 `x86_64-link.c` 就是这个结构。**换架构 = 换 `*-link.c`。**

---

## 第 4 站：TCC 支持哪些目标

配置时（`configure` / `--target`）选择：

| 目标 | 宏 | 后端文件 |
|---|---|---|
| x86-64 | `TCC_TARGET_X86_64` | `x86_64-gen.c`/`x86_64-link.c` |
| i386 | `TCC_TARGET_I386` | `i386-gen.c`/`i386-link.c` |
| ARM | `TCC_TARGET_ARM` | `arm-gen.c`/`arm-link.c` |
| ARM64 | `TCC_TARGET_ARM64` | `arm64-gen.c`/`arm64-link.c` |
| C67（TI DSP） | `TCC_TARGET_C67` | `c67-gen.c`/`c67-link.c` |
| IL（虚拟机） | — | `il-gen.c` |

**一次配置选一个目标**（不是多目标运行时切换）。

---

## 【动手小实验】

1. 对比 `arm-gen.c` 和 `x86_64-gen.c` 里 `load` 的开头，看结构多相似。
2. 搜 `REG_IRET`，看每个后端定义成什么寄存器。
3. 如果能在 ARM 上跑：`tcc -c` 一个程序，`objdump -d` 看 ARM 汇编。
4. 用 `tcc -target` 交叉编译（见 `tcc -h`）。

## 【通关暗号】

```bash
# 在 x86-64 上，验证不同后端文件都被条件包含（不会冲突）
grep -l 'TARGET_DEFS_ONLY' /Users/lavender/Documents/x/src/targets/*-gen.c
# 期望：列出所有 *-gen.c
```

## 【常见卡点】

- **所有后端实现同一批接口**，前端不变。
- **配置宏（`NB_REGS`/`REG_IRET`/`EM_TCC_TARGET`…）由 `TARGET_DEFS_ONLY` 提供**。
- **ARM 指令可条件执行，ARM64 定长指令**。
- **链接端也按架构分文件**。

**下一篇**：`66-IL与C67后端.md`。
