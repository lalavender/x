# 43 · 返回值与 `varargs`：`printf` 是怎么拿到参数的

> **一句话**：返回值放约定寄存器（整数 `rax`、浮点 `xmm0`、`long double` 在 `st0`）；
> 变参函数靠"把所有寄存器参数保存到栈上 + `va_list` 结构 + `va_arg` 遍历"实现。
>
> 对应源码：`src/core/tccgen.c:5743`（`gfunc_return`）、
> `src/core/tccgen.c:1464/1476`（`rc_fret`/`reg_fret`）、
> `src/targets/x86_64-gen.c:1212`（`gfunc_sret`）、`:1195`（`classify_x86_64_va_arg`）、
> `src/core/tccgen.c:4891-4912`（`__builtin_va_start/va_arg` 在 x86-64 的分支）。

---

## 第 0 站：返回值寄存器

x86-64 SysV 的返回值约定：

| 返回类型 | 寄存器 | TCC 的类别 |
|---|---|---|
| 整数/指针/小整数 | `rax` | `RC_IRET`（`REG_IRET`） |
| 64 位整数 | `rax`（+`rdx`） | `RC_IRET` + `REG_LRET` |
| `float`/`double` | `xmm0` | `RC_FRET` |
| `long double` | `st0` | `RC_ST0` |
| 小结构体（≤16 字节） | `rax`/`rdx` 或 `xmm0`/`xmm1` | 打包 |
| 大结构体 | 调用者给的隐藏指针 | `RET_NREGS = 0` |

辅助函数：

```c
/* src/core/tccgen.c:1462-1484 */
static int rc_fret(int t)      /* 浮点返回用哪个"寄存器类别" */
{
#ifdef TCC_TARGET_X86_64
    if (t == VT_LDOUBLE) return RC_ST0;   /* long double 走 st0 */
#endif
    return RC_FRET;                        /* 其余浮点走 xmm0 */
}

static int reg_fret(int t)     /* 对应的具体寄存器号 */
{
#ifdef TCC_TARGET_X86_64
    if (t == VT_LDOUBLE) return TREG_ST0;
#endif
    return REG_FRET;
}
```

---

## 第 1 站：`gfunc_return`（`tccgen.c:5743`）

```c
/* src/core/tccgen.c:5743-5806（节选）*/
static void gfunc_return(CType *func_type)
{
    if ((func_type->t & VT_BTYPE) == VT_STRUCT) {
        CType type, ret_type;
        int ret_align, ret_nregs, regsize;
        ret_nregs = gfunc_sret(func_type, func_var, &ret_type, &ret_align, &regsize);
        if (0 == ret_nregs) {
            /* 大结构体：写进隐藏指针参数指向的缓冲区 */
            type = *func_type;
            mk_pointer(&type);
            vset(&type, VT_LOCAL | VT_LVAL, func_vc);   /* 隐藏指针（第 42 篇） */
            indir();
            vswap();
            vstore();                                    /* 把返回值拷进去 */
        } else {
            /* 小结构体：打包进若干寄存器 */
            ...
            vtop->type = ret_type;
            if (is_float(ret_type.t)) r = rc_fret(ret_type.t);
            else                      r = RC_IRET;
            if (ret_nregs == 1) gv(r);
            else { ... 逐个寄存器 gv ... }
        }
    } else if (is_float(func_type->t)) {
        gv(rc_fret(func_type->t));   /* ★ 浮点：st0 或 xmm0 */
    } else {
        gv(RC_IRET);                 /* ★ 整数：rax */
    }
    vtop--; /* 不用 vpop，避免 x86 清浮点栈 */
}
```

两条主线：

- **非结构体**：`gv(RC_IRET)` 或 `gv(rc_fret(...))`，把值装进返回值寄存器；
- **结构体**：
  - `gfunc_sret` 返回 0 → 大结构体，**写进 `func_vc` 指向的缓冲区**（隐藏指针）；
  - 返回 1 或 2 → 小结构体，打包进 `rax`/`rdx` 或 `xmm`。

`gfunc_sret`（`x86_64-gen.c:1212`）：

```c
/* src/targets/x86_64-gen.c:1210-1218 */
ST_FUNC int gfunc_sret(CType *vt, int variadic, CType *ret, int *ret_align, int *regsize)
{
    int size, align, reg_count;
    *ret_align = 1;
    *regsize = 8;
    return (classify_x86_64_arg(vt, ret, &size, &align, &reg_count)
            != x86_64_mode_memory);     /* 不是 memory 就能进寄存器 */
}
```

**分类器复用**：传参和返回都用 `classify_x86_64_arg`。

---

## 第 2 站：调用方怎么接返回值

第 19 篇讲过 `unary` 的调用分支：

```c
/* src/core/tccgen.c:5251-5255（重贴）*/
            /* return value */
            for (r = ret.r + ret_nregs + !ret_nregs; r-- > ret.r;) {
                vsetc(&ret.type, r, &ret.c);   /* ★ 把返回值寄存器贴回值栈 */
                vtop->r2 = ret.r2;
            }
```

`ret.r` 在 `unary` 里根据返回类型设成 `REG_IRET` 或 `reg_fret(...)`（`:5213-5232`）。
于是 `f() + 1` 能继续算。

---

## 第 3 站：变参原理（`printf` 怎么工作）

`printf("%d %f", i, d)` 里，调用的函数只有 `(const char*, ...)` 原型，
**不知道后面几个实参是什么类型、多少个数**。变参机制要解决"被调用者怎么找到它们"。

### 3a. prolog 保存所有寄存器（第 42 篇）

变参函数的 prolog（`x86_64-gen.c:1450`）把**所有整数寄存器参数**
和**所有浮点寄存器参数**都存到栈上，并放一个 `va_list` 结构记录"用到哪了"：

```
        rbp-0x10: 已用整数寄存器数 × 8
        rbp-0x0c: 已用浮点寄存器数 × 16 + 48
        rbp-0x08: 已知的栈上参数总大小
        ... 保存的 8 个 xmm 寄存器 ...
        ... 保存的 6 个整数寄存器 ...
```

### 3b. `__builtin_va_start` / `va_arg`

TCC 把 `<stdarg.h>` 里的 `va_start`/`va_arg` 实现成内置函数（`tccgen.c:4891`）：

```c
/* src/core/tccgen.c:4891-4912（节选）*/
#ifdef TCC_TARGET_X86_64
#ifndef TCC_TARGET_PE
    case TOK_builtin_va_arg_types:
        parse_builtin_params(0, "t");
        vpushi(classify_x86_64_va_arg(&vtop->type));   /* ★ 算出这个类型在哪个区 */
        vswap();
        vpop();
        break;
#endif
#endif
```

`classify_x86_64_va_arg`（`x86_64-gen.c:1195`）返回一个整数，
告诉 `va_arg` 宏"这个类型去整数区、浮点区还是栈区取"：

```c
/* src/targets/x86_64-gen.c:1195-1208 */
ST_FUNC int classify_x86_64_va_arg(CType *ty)
{
    /* 这个 enum 必须和 stdarg.h 同步！ */
    enum __va_arg_type {
        __va_gen_reg, __va_float_reg, __va_stack
    };
    int size, align, reg_count;
    X86_64_Mode mode = classify_x86_64_arg(ty, NULL, &size, &align, &reg_count);
    switch (mode) {
    default: return __va_stack;
    case x86_64_mode_integer: return __va_gen_reg;
    case x86_64_mode_sse:     return __va_float_reg;
    }
}
```

`stdarg.h` 里的 `__builtin_va_arg_types(type)` 就调用它，
然后根据返回值走不同分支，从保存的寄存器区或栈区取出参数。

### 3c. 调用方为什么麻烦

变参函数的 prolog 之所以要保存**所有**寄存器，是因为调用者可能传任意数量的参数。
**这是"被调用者不知道、又不要求调用者说明"的代价**——只能全部保存一遍。

---

## 第 4 站：完整链条（`printf("%d", 42)`）

| 步骤 | 说明 |
|---|---|
| 1 | 前端：`gfunc_param_typed` 对 `...` 的实参做默认提升 |
| 2 | 前端：`gfunc_call` 走 SysV 传参 |
| 3 | 后端：`%al` 放浮点寄存器个数 |
| 4 | `printf` prolog：保存所有寄存器到栈 + 初始化 `va_list` |
| 5 | `printf` 内部 `va_arg(ap, int)`：`__builtin_va_arg_types(int)` 返回整数区 |
| 6 | 从保存的整数寄存器区取出 `42` |

---

## 【动手小实验】

1. 自己写一个 `int sum(int n, ...)` 用 `stdarg.h` 累加，验证变参工作。
2. 写 `double f(){return 1.5;}` 调用它，反汇编看 `xmm0`。
3. 写一个返回大结构体的函数，反汇编看隐藏指针参数（`rdi`）和 `rep movs`。
4. `printf("%d\n", 42);` 反汇编 `printf` 的 prolog，数它保存了几个寄存器。

## 【通关暗号】

```bash
printf '#include <stdarg.h>\nint sum(int n,...){va_list ap; va_start(ap,n); int s=0; for(int i=0;i<n;i++)s+=va_arg(ap,int); va_end(ap); return s;}\nint main(void){return sum(3,1,2,3);}\n' > /tmp/v.c
./tcc -run /tmp/v.c; echo $?
# 期望：6
```

## 【常见卡点】

- **返回值寄存器**：整数 `rax`、浮点 `xmm0`、`long double` `st0`。
- **大结构体用隐藏指针**（`func_vc`），小结构体打包进寄存器。
- **变参 prolog 保存所有寄存器**，`va_list` 记录已用情况。
- **`classify_x86_64_va_arg` 的 enum 必须和 `stdarg.h` 同步**。
- **`gfunc_sret` 复用 `classify_x86_64_arg`**。

---

## 【第六部小结】

| 篇 | 主题 |
|---|---|
| 40 | 形参实参配对、默认提升 |
| 41 | `gfunc_call` 装车（SysV ABI） |
| 42 | `prolog`/`epilog` 栈帧 |
| 43 | 返回值与 `varargs` |

**下一步（第七部）**：x86-64 后端——从发字节的原语 `g`/`o`，
到 `load`/`store`、`gen_opi`、跳转、调用、内联汇编。

**下一篇**：`44-后端接口与a-函数指针表.md`。
