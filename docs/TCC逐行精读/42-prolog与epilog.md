# 42 · 盖房与拆房：`gfunc_prolog` 与 `gfunc_epilog`

> **一句话**：函数体开始前要 `push rbp; mov rbp,rsp; sub rsp,N` 并"盖好栈帧"；
> 结束要 `leave; ret`。难点是 **N（局部变量总大小）只有编完函数体才知道**，
> 所以 TCC 先占位、最后回填。
>
> 对应源码：`src/targets/x86_64-gen.c:1435`（`gfunc_prolog`）、
> `:1587`（`gfunc_epilog`）、`:1427`（`FUNC_PROLOG_SIZE`）、
> `src/core/tccgen.c:7054`（`gen_function` 调用它们）。

---

## 第 0 站：栈帧长什么样（x86-64 SysV）

```
   高地址
   ┌─────────────┐
   │  调用者的栈  │
   ├─────────────┤
   │  参数 7+     │ ← addr 从 rbp+16 开始（PTR_SIZE*2）
   ├─────────────┤
   │  返回地址    │ ← rbp+8
   ├─────────────┤
   │  保存的 rbp  │ ← rbp+0（rbp 指向这里）
   ├─────────────┤
   │  局部变量    │ ← rbp-4, rbp-8, ...
   │  ...        │
   └─────────────┘ ← rsp
   低地址
```

- 前 6 个整数参数在 `rdi/rsi/rdx/rcx/r8/r9`，不在栈上；
- 第 7 个起在 `rbp+16`, `rbp+24`, …；
- 局部变量在 `rbp` 往下（负偏移）。

---

## 第 1 站：`gfunc_prolog`（`x86_64-gen.c:1435`）

```c
/* src/targets/x86_64-gen.c:1435-1448（节选）*/
void gfunc_prolog(CType *func_type)
{
    X86_64_Mode mode;
    int i, addr, align, size, reg_count;
    int param_addr = 0, reg_param_index, sse_param_index;
    Sym *sym;
    CType *type;

    sym = func_type->ref;                /* 函数 Sym，next 是形参链 */
    addr = PTR_SIZE * 2;                 /* 栈上参数从 rbp+16 开始 */
    loc = 0;                             /* 局部变量从 0 往下长 */
    ind += FUNC_PROLOG_SIZE;             /* ★ 先"空出"prolog 的字节数 */
    func_sub_sp_offset = ind;            /* 记住"sub rsp,N"的占位位置 */
    func_ret_sub = 0;
    ...
```

**关键技巧**：`ind += FUNC_PROLOG_SIZE`（`:1427` 定义 `FUNC_PROLOG_SIZE 11`）。
此刻还不知道 `N`，所以先往前跳 11 字节，把这段位置留给 prolog，
等 `gfunc_epilog` 时再回填真正的 `push rbp; mov rbp,rsp; sub rsp,N`。

### 1a. 变参函数：保存所有寄存器（`:1450-1506`）

```c
/* src/targets/x86_64-gen.c:1450-1506（节选）*/
    if (sym->f.func_type == FUNC_ELLIPSIS) {
        int seen_reg_num, seen_sse_num, seen_stack_size;
        seen_reg_num = seen_sse_num = 0;
        seen_stack_size = PTR_SIZE * 2;
        /* 数一数已知形参用了多少寄存器和栈空间 */
        while ((sym = sym->next) != NULL) {
            mode = classify_x86_64_arg(&sym->type, ...);
            switch (mode) {
            default: stack_arg:
                seen_stack_size = ((seen_stack_size + align - 1) & -align) + size;
                break;
            case x86_64_mode_integer:
                if (seen_reg_num + reg_count > REGN) goto stack_arg;
                seen_reg_num += reg_count;
                break;
            case x86_64_mode_sse:
                if (seen_sse_num + reg_count > 8) goto stack_arg;
                seen_sse_num += reg_count;
                break;
            }
        }
        /* 把"已用情况"写进栈上的 va_list 结构 */
        loc -= 16;
        o(0xf045c7); gen_le32(seen_reg_num * 8);     /* -0x10(%rbp) */
        o(0xf445c7); gen_le32(seen_sse_num * 16 + 48);
        o(0xf845c7); gen_le32(seen_stack_size);      /* -0x8(%rbp) */
        /* ★ 把所有寄存器参数保存到栈上，供 va_arg 遍历 */
        for (i = 0; i < 8; i++) {
            loc -= 16;
            if (!tcc_state->nosse) {
                o(0xd60f66);                          /* movq xmmN, ... */
                gen_modrm(7 - i, VT_LOCAL, NULL, loc);
            }
            ...
        }
        for (i = 0; i < REGN; i++) {
            push_arg_reg(REGN-1-i);                   /* 保存整数寄存器 */
        }
    }
```

**变参函数的 prolog 特别大**：它要把**所有可能传参的寄存器**都存到栈上，
因为 `va_arg` 不知道调用者实际传了哪些。这段 + `stdarg.h` 里的 `va_list`
结构约定必须一致（`classify_x86_64_va_arg`，第 43 篇）。

### 1b. 结构体返回值：隐藏指针参数（`:1512-1520`）

```c
/* src/targets/x86_64-gen.c:1512-1520 */
    /* 如果返回结构体（放不下寄存器），加一个隐藏指针参数 */
    func_vt = sym->type;
    mode = classify_x86_64_arg(&func_vt, NULL, &size, &align, &reg_count);
    if (mode == x86_64_mode_memory) {
        push_arg_reg(reg_param_index);   /* 第一个整数参数就是返回缓冲区指针 */
        func_vc = loc;                   /* 记下它的栈位置（return 用） */
        reg_param_index++;
    }
```

### 1c. 逐个形参：从寄存器搬到栈（`:1522-1572`）

```c
/* src/targets/x86_64-gen.c:1522-1572（节选）*/
    while ((sym = sym->next) != NULL) {
        type = &sym->type;
        mode = classify_x86_64_arg(type, NULL, &size, &align, &reg_count);
        switch (mode) {
        case x86_64_mode_sse:
            if (sse_param_index + reg_count <= 8) {
                loc -= reg_count * 8;
                param_addr = loc;
                for (i = 0; i < reg_count; ++i) {
                    o(0xd60f66);                 /* movq xmmN, param_addr */
                    gen_modrm(sse_param_index, VT_LOCAL, NULL, param_addr + i*8);
                    ++sse_param_index;
                }
            } else { addr 对齐后放栈 }
            break;
        case x86_64_mode_memory:
        case x86_64_mode_x87:
            addr = (addr + align - 1) & -align;
            param_addr = addr;
            addr += size;
            break;
        case x86_64_mode_integer:
            if (reg_param_index + reg_count <= REGN) {
                loc -= reg_count * 8;
                param_addr = loc;
                for (i = 0; i < reg_count; ++i) {
                    gen_modrm64(0x89, arg_regs[reg_param_index], VT_LOCAL, NULL, param_addr + i*8);
                    ++reg_param_index;
                }
            } else { addr 对齐后放栈 }
            break;
        }
        /* ★ 把形参登记成局部变量（r=VT_LOCAL|VT_LVAL, c=param_addr） */
        sym_push(sym->v & ~SYM_FIELD, type, VT_LOCAL | VT_LVAL, param_addr);
    }
```

**TCC 的做法：把所有寄存器参数都搬到栈上**，然后形参就和普通局部变量一样
（`VT_LOCAL|VT_LVAL`, 有地址）。这样取参数地址、`&a`、`va_arg` 都简单。
代价是多几条 `mov`。

---

## 第 2 站：`gfunc_epilog`（`x86_64-gen.c:1587`）

```c
/* src/targets/x86_64-gen.c:1587-1638（节选）*/
void gfunc_epilog(void)
{
    int v, saved_ind;
    ...
    o(0xc9);             /* ★ leave：mov rsp,rbp; pop rbp */
    if (func_ret_sub == 0) {
        o(0xc3);         /* ret */
    } else {
        o(0xc2);         /* ret n（被调用者清栈，如 stdcall） */
        g(func_ret_sub);
        g(func_ret_sub >> 8);
    }
    /* ★ 现在函数体编完了，知道栈帧大小，回头补 prolog */
    v = (-loc + 15) & -16;               /* 局部大小向上取整到 16 */
    saved_ind = ind;                     /* 记住当前位置 */
    ind = func_sub_sp_offset - FUNC_PROLOG_SIZE;   /* ★ 跳回 prolog 占位处 */
    o(0xe5894855);       /* push %rbp; mov %rsp,%rbp */
    o(0xec8148);         /* sub rsp, stacksize */
    gen_le32(v);
    ind = saved_ind;                     /* ★ 回到函数末尾 */
}
```

这是**"先占位、后回填"**的典范：

1. `gfunc_prolog` 里 `ind += 11` 占位，并记住 `func_sub_sp_offset`；
2. 函数体生成过程中 `loc` 不断变小（局部变量、溢出的临时值）；
3. `gfunc_epilog` 里 `v = (-loc+15) & -16` 算出栈帧大小；
4. `ind = func_sub_sp_offset - FUNC_PROLOG_SIZE` 跳回去，
   写真正的 `push rbp; mov rbp,rsp; sub rsp,v`；
5. `ind = saved_ind` 回到末尾，继续`ret`后面的代码。

**为什么不在 prolog 时就知道大小？** 因为寄存器溢出（第 21 篇）会临时增加栈需求，
直到函数体编完才知道最终 `loc`。

---

## 第 3 站：`leave` 和 `ret`

- `leave` = `mov rsp, rbp; pop rbp`：一条指令拆掉整个栈帧；
- `ret` = 弹出返回地址并跳过去；
- `ret n` 用于调用者不需清栈的约定（`stdcall`）：被调用者额外弹 `n` 字节。

---

## 【把 `int f(){int a,b; ...}` 的 prolog 走一遍】

| 阶段 | 输出 |
|---|---|
| `gfunc_prolog` 开头 | `ind += 11`（占位） |
| `int a` | `loc = -4`，登记 `a` 在 `rbp-4` |
| `int b` | `loc = -8`，登记 `b` 在 `rbp-8` |
| 函数体可能溢出寄存器 | `loc` 更负 |
| `gfunc_epilog` | `v = (-loc+15)&-16`，回填 `push rbp; mov rbp,rsp; sub rsp,v`；然后 `leave; ret` |

最终机器码形如：
```asm
push rbp
mov  rbp, rsp
sub  rsp, 16
...函数体...
leave
ret
```

---

## 【动手小实验】

1. `int f(int a){int b=a+1; return b;}` 反汇编看 prolog/epilog。
2. 写一个需要很多局部变量的函数，看 `sub rsp,N` 的 N 变化。
3. 写变参函数 `int f(int n, ...)`，反汇编看它保存了多少寄存器。
4. 在 `gfunc_epilog` 回填那几行加打印，确认 `loc` 的最终值。

## 【通关暗号】

```bash
printf 'int f(int a){int b=a*2; int c=b+1; return c;}\nint main(void){return f(3);}\n' > /tmp/f.c
./tcc -c /tmp/f.c -o /tmp/f.o && objdump -d /tmp/f.o 2>/dev/null | grep -A8 '<f>:'
# 期望：能看到 push rbp / mov rsp,rbp / sub rsp,N / ... / leave / ret
```

## 【常见卡点】

- **prolog 先占 11 字节，epilog 回填**（`FUNC_PROLOG_SIZE`）。
- **寄存器参数被搬到栈上**，于是形参和局部变量一样有地址。
- **变参 prolog 保存所有寄存器**，和 `va_list` 结构配套。
- **结构体返回值用隐藏指针参数**（`func_vc`）。
- **栈帧大小取 16 字节对齐**（`(-loc+15)&-16`）。

**下一篇**：`43-返回值与varargs.md`。
