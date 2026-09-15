# 41 · `gfunc_call`：把实参装车，发 call

> **一句话**：值栈上有函数地址和一堆实参。`gfunc_call` 要按 ABI 把实参
> 分到寄存器或栈上（System V AMD64 ABI：前 6 个整数进 `rdi/rsi/rdx/rcx/r8/r9`，
> 前 8 个浮点进 `xmm0..7`），然后发 `call`。
>
> 对应源码：`src/targets/x86_64-gen.c:1236`（`gfunc_call`，SysV 版）、
> `:1137`（`classify_x86_64_arg`）、`:1225`（`arg_prepare_reg`）、
> `:622`（`gcall_or_jmp`）、`src/core/tccgen.c:5249`（前端调用点）。

---

## 第 0 站：System V AMD64 传参规则（先补常识）

| 类型 | 去哪 |
|---|---|
| 整数/指针（第 1~6 个） | `rdi, rsi, rdx, rcx, r8, r9` |
| 浮点（第 1~8 个） | `xmm0..xmm7` |
| 结构体 ≤16 字节 | 拆成 1~2 个"八字节"进整数/浮点寄存器 |
| 结构体 >16 字节 | 整体放栈上 |
| 第 7 个起的整数 / 第 9 个起的浮点 | 放栈上 |
| 变参函数 | `%al` 放用到的浮点寄存器个数 |

（Windows x64 规则不同：`rcx/rdx/r8/r9`，浮点在对应整数寄存器位置。TCC 用
`#ifdef TCC_TARGET_PE` 区分两套代码。本篇讲的是 macOS/Linux 用的 SysV 版。）

---

## 第 1 站：第一遍——决定每个实参去哪（`x86_64-gen.c:1236`）

```c
/* src/targets/x86_64-gen.c:1236-1269（节选）*/
void gfunc_call(int nb_args)
{
    X86_64_Mode mode;
    ...
    char _onstack[nb_args], *onstack = _onstack;
    int nb_reg_args = 0, nb_sse_args = 0;
    ...
    /* 从右到左扫一遍，决定每个实参怎么传 */
    stack_adjust = 0;
    for(i = nb_args - 1; i >= 0; i--) {
        mode = classify_x86_64_arg(&vtop[-i].type, NULL, &size, &align, &reg_count);
        if (mode == x86_64_mode_sse && nb_sse_args + reg_count <= 8) {
            nb_sse_args += reg_count;
            onstack[i] = 0;              /* 进浮点寄存器 */
        } else if (mode == x86_64_mode_integer && nb_reg_args + reg_count <= REGN) {
            nb_reg_args += reg_count;
            onstack[i] = 0;              /* 进整数寄存器 */
        } else if (mode == x86_64_mode_none) {
            onstack[i] = 0;              /* 空（如 void 参数） */
        } else {
            if (align == 16 && (stack_adjust &= 15)) {
                onstack[i] = 2;          /* 需要 16 字节对齐 */
                stack_adjust = 0;
            } else
                onstack[i] = 1;          /* 放栈上 */
            stack_adjust += size;
        }
    }
```

`classify_x86_64_arg`（`:1137`）返回这个实参是 `integer`/`sse`/`x87`/`memory`/`none`，
并给出大小、对齐、要几个寄存器。`REGN` 在 SysV 版是 6（`:1220`）。

`onstack[i]` 数组记录每个实参的去向。**第一遍只做决定，不发代码。**

---

## 第 2 站：第二遍——先处理"要放栈上"的（`:1281-1351`）

```c
/* src/targets/x86_64-gen.c:1281-1351（节选）*/
    gen_reg = nb_reg_args;
    sse_reg = nb_sse_args;
    args_size = 0;
    for (i = 0; i < nb_args;) {
        mode = classify_x86_64_arg(&vtop[-i].type, NULL, &size, &align, &reg_count);
        if (!onstack[i]) { ++i; continue; }   /* 跳过寄存器实参 */
        ...
        if (stack_adjust) { o(0x50); args_size += 8; stack_adjust = 0; }
        if (onstack[i] == 2) stack_adjust = 1;

        vrotb(i+1);                            /* 把该实参转到栈顶 */
        switch (vtop->type.t & VT_BTYPE) {
            case VT_STRUCT:                    /* 结构体：在栈上拷一份 */
                o(0x48); oad(0xec81, size);    /* sub $size, %rsp */
                r = get_reg(RC_INT);
                orex(1, r, 0, 0x89);           /* mov %rsp, r */
                ...
                vstore();
                break;
            case VT_LDOUBLE:                   /* long double：fstpt (%rsp) */
                gv(RC_ST0);
                ...
                break;
            case VT_FLOAT: case VT_DOUBLE:     /* movq %xmmN, (%rsp) */
                r = gv(RC_FLOAT);
                o(0x50);
                o(0xd60f66);
                o(0x04 + REG_VALUE(r)*8);
                o(0x24);
                break;
            default:                           /* 整数：push */
                r = gv(RC_INT);
                orex(0,r,0,0x50 + REG_VALUE(r));   /* push r */
                break;
        }
        args_size += size;
        vpop();
        --nb_args;
        onstack++;
    }
```

**为什么栈实参要先处理？** 注释说得很清楚：

> for struct arguments, we need to call memcpy and the function call breaks
> register passing arguments we are preparing. So, we process arguments which
> will be passed by stack first.

栈上的结构体拷贝要调用 `memmove`，而调用会破坏寄存器——所以先把栈实参落地，
再装寄存器实参。

---

## 第 3 站：第三遍——装寄存器实参（`:1353-1402`）

```c
/* src/targets/x86_64-gen.c:1353-1402（节选）*/
    save_regs(0);   /* 清空临时寄存器 */

    /* 设置寄存器实参。注意不能直接用 RDX/RCX，
       因为 gv() 可能破坏它们，所以先用 R10/R11 暂存 */
    for(i = 0; i < nb_args; i++) {
        mode = classify_x86_64_arg(&vtop->type, &type, &size, &align, &reg_count);
        vtop->type = type;
        if (mode == x86_64_mode_sse) {
            if (reg_count == 2) {
                sse_reg -= 2;
                gv(RC_FRET);                  /* 装进 xmm0 & xmm1 */
                if (sse_reg) {                /* movaps 到目标 xmmN */
                    o(0x280f); o(0xc0 + (sse_reg << 3));
                    o(0x280f); o(0xc1 + ((sse_reg+1) << 3));
                }
            } else {
                --sse_reg;
                gv(RC_XMM0 << sse_reg);       /* 装进 xmmN */
            }
        } else if (mode == x86_64_mode_integer) {
            int d;
            gen_reg -= reg_count;
            r = gv(RC_INT);
            d = arg_prepare_reg(gen_reg);     /* ★ 目标寄存器 */
            orex(1,d,r,0x89);                 /* mov r, d */
            o(0xc0 + REG_VALUE(r) * 8 + REG_VALUE(d));
            if (reg_count == 2) {             /* 64位对：第二个寄存器 */
                d = arg_prepare_reg(gen_reg+1);
                orex(1,d,vtop->r2,0x89);
                o(0xc0 + REG_VALUE(vtop->r2) * 8 + REG_VALUE(d));
            }
        }
        vtop--;
    }
```

`arg_prepare_reg`（`:1225`）：

```c
/* src/targets/x86_64-gen.c:1225-1231 */
static int arg_prepare_reg(int idx) {
  if (idx == 2 || idx == 3)
      /* idx=2: r10, idx=3: r11 */
      return idx + 8;
  else
      return arg_regs[idx];    /* rdi, rsi, r8, r9 */
}
```

**为什么把 `rdx`/`rcx`（idx 2/3）换成 `r10`/`r11`？**
因为 `gv()` 在装寄存器时可能随手用掉 `rdx`/`rcx`。
先装到 `r10`/`r11`，最后再统一搬到 `rdx`/`rcx`：

```c
/* src/targets/x86_64-gen.c:1410-1416 */
    /* 把 R10/R11 搬到 RDX/RCX */
    if (nb_reg_args > 2) {
        o(0xd2894c); /* mov %r10, %rdx */
        if (nb_reg_args > 3) {
            o(0xd9894c); /* mov %r11, %rcx */
        }
    }
```

**这是 ABI 实现的经典小技巧：用"安全"的临时寄存器中转。**

---

## 第 4 站：发 `call`（`:1418-1423`）

```c
/* src/targets/x86_64-gen.c:1418-1423 */
    if (vtop->type.ref->f.func_type != FUNC_NEW)
        oad(0xb8, nb_sse_args < 8 ? nb_sse_args : 8);  /* mov nb_sse_args, %eax */
    gcall_or_jmp(0);                                   /* ★ 发 call */
    if (args_size)
        gadd_sp(args_size);                            /* 收栈上的实参 */
    vtop--;
```

- **变参函数要传 `%al`**：告诉被调用者用了几个浮点寄存器（`va_arg` 需要）。
- `gcall_or_jmp(0)`（`:622`）：

```c
/* src/targets/x86_64-gen.c:622-649（节选）*/
static void gcall_or_jmp(int is_jmp)
{
    if ((vtop->r & (VT_VALMASK | VT_LVAL)) == VT_CONST &&
        ((vtop->r & VT_SYM) || ...)) {
        /* 直接调用：call 符号，生成重定位 */
        if (vtop->r & VT_SYM)
            greloca(cur_text_section, vtop->sym, ind + 1, R_X86_64_PLT32, ...);
        oad(0xe8 + is_jmp, 0);   /* call rel32（占位，等链接回填） */
    } else {
        /* 函数指针：间接调用 */
        r = TREG_R11;
        load(r, vtop);
        o(0x41); o(0xff); o(0xd0 + REG_VALUE(r) + (is_jmp << 4));  /* call *r11 */
    }
}
```

**直接调用生成 `R_X86_64_PLT32` 重定位**（第 53 篇），地址由链接器填。
函数指针调用则把地址装进 `r11` 再 `call *r11`。

---

## 第 5 站：`classify_x86_64_arg`（`x86_64-gen.c:1137`）

这是 ABI 的"分类器"，决定每个类型怎么传：

```c
/* src/targets/x86_64-gen.c:1137-1193（节选）*/
static X86_64_Mode classify_x86_64_arg(CType *ty, CType *ret, int *psize, int *palign, int *reg_count)
{
    ...
    if (ty->t & (VT_BITFIELD|VT_ARRAY)) {
        *psize = 8; *palign = 8; *reg_count = 1;
        mode = x86_64_mode_integer;
    } else {
        size = type_size(ty, &align);
        *psize = (size + 7) & ~7;
        *palign = (align + 7) & ~7;
        if (size > 16) {
            mode = x86_64_mode_memory;      /* >16 字节：整体进栈 */
        } else {
            mode = classify_x86_64_inner(ty);   /* 递归看成员 */
            switch (mode) {
            case x86_64_mode_integer:
                *reg_count = size > 8 ? 2 : 1;
                ret_t = size > 8 ? VT_QLONG : (size > 4 ? VT_LLONG : VT_INT);
                break;
            case x86_64_mode_sse:
                *reg_count = size > 8 ? 2 : 1;
                ret_t = size > 8 ? VT_QFLOAT : (size > 4 ? VT_DOUBLE : VT_FLOAT);
                break;
            ...
            }
        }
    }
    ...
}
```

`classify_x86_64_inner`（`:1102`）递归判断结构体成员的类别，
`classify_x86_64_merge`（`:1084`）把成员的类别"合并"（有 memory 就 memory，
有 integer 就 integer，等等）。**这就是 SysV ABI 里那个"八字节分类算法"的简化版。**

---

## 【把 `add(3, 4)` 装车走一遍】

| 步骤 | 结果 |
|---|---|
| 1 | 第一遍：`3` integer/1reg，`4` integer/1reg，都能进寄存器 |
| 2 | 第二遍：没有栈实参 |
| 3 | 第三遍：`4`（栈顶）→ `gv` → `arg_prepare_reg(1)` = `rsi` → `mov rsi, r4` |
| 4 | 第三遍：`3` → `arg_prepare_reg(0)` = `rdi` → `mov rdi, r3` |
| 5 | 发 `call add`（带 PLT32 重定位） |
| 6 | 返回值在 `rax`，前端压回值栈 |

---

## 【动手小实验】

1. `int add3(int a,int b,int c){return a+b+c;} add3(1,2,3);`
   反汇编看参数进 `edi/esi/edx`。
2. 写 7 个整数参数，看第 7 个是否被 push 到栈上。
3. `double f(double a){return a;} f(1.5);` 看 `xmm0`。
4. 写 `int (*fp)(int); fp(5);` 看是不是 `call *r11`。
5. 用 `objdump -dr` 看 `call` 后面的重定位类型是不是 `R_X86_64_PLT32`。

## 【通关暗号】

```bash
printf 'int s(int a,int b,int c,int d,int e,int f,int g){return a+b+c+d+e+f+g;}\nint main(void){return s(1,2,3,4,5,6,7);}\n' > /tmp/c.c
./tcc -run /tmp/c.c; echo $?
# 期望：28（验证栈上参数也被正确传递）
```

## 【常见卡点】

- **三遍扫描**：先决定 → 处理栈实参 → 装寄存器实参。
- **栈实参先处理**，因为结构体拷贝会调函数破坏寄存器。
- **`rdx`/`rcx` 用 `r10`/`r11` 中转**，最后搬。
- **变参要把浮点寄存器个数放 `%al`**。
- **直接调用生成 `R_X86_64_PLT32` 重定位**，间接调用 `call *r11`。

**下一篇**：`42-prolog与epilog.md`。
