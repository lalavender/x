# 22 · `gen_op` 与常量折叠：两个便利贴归约成一张

> **一句话**：值栈顶有两张便利贴（操作数），`gen_op(op)` 负责：
> ① 处理类型（指针算术、float 提升、整数提升）；
> ② 如果两个都是常量，**当场算出来**；否则调后端发一条指令。
>
> 对应源码：`src/core/tccgen.c:2154`（`gen_op`）、`:1864`（`gen_opic` 整数常量折叠）、
> `:2014`（`gen_opif` 浮点常量折叠）、`:1624`（`gen_opl`，32 位平台的 64 位运算）。

---

## 第 0 站：`gen_op` 的四层判断（`tccgen.c:2154`）

```c
/* src/core/tccgen.c:2154-2164 */
ST_FUNC void gen_op(int op)
{
    int u, t1, t2, bt1, bt2, t;
    CType type1;

redo:
    t1 = vtop[-1].type.t;    /* 下面那张 */
    t2 = vtop[0].type.t;     /* 上面那张 */
    bt1 = t1 & VT_BTYPE;     /* 基本类型 */
    bt2 = t2 & VT_BTYPE;

    if (bt1 == VT_STRUCT || bt2 == VT_STRUCT) {
        tcc_error("operation on a struct");
    } else if (bt1 == VT_FUNC || bt2 == VT_FUNC) {
        /* 函数名当函数指针用 */
        if (bt2 == VT_FUNC) { mk_pointer(&vtop->type); gaddrof(); }
        if (bt1 == VT_FUNC) { vswap(); mk_pointer(&vtop->type); gaddrof(); vswap(); }
        goto redo;
    } else if (bt1 == VT_PTR || bt2 == VT_PTR) {
        /* ★ 指针算术 */
        ...
    } else if (is_float(bt1) || is_float(bt2)) {
        /* ★ 浮点：取更宽的那个类型 */
        ...
        goto std_op;
    } else {
        /* ★ 整数运算 */
        ...
        goto std_op;
    }
```

四个分支：结构体报错、函数转指针、指针算术、浮点/整数。**`goto redo` 是因为转换后类型变了，要重新判断。**

---

## 第 1 站：指针算术（`tccgen.c:2179-2272`）

这是 C 里最容易出错、也最精妙的地方。

### 1a. 指针比较（`:2182-2190`）

```c
        if (op >= TOK_ULT && op <= TOK_LOR) {       /* < <= > >= == != && || */
            check_comparison_pointer_types(vtop - 1, vtop, op);
            t = VT_LLONG | VT_UNSIGNED;             /* 当无符号整数比 */
            goto std_op;
        }
```

### 1b. 指针减指针（`:2193-2207`）

```c
        if (bt1 == VT_PTR && bt2 == VT_PTR) {
            if (op != '-') tcc_error("cannot use pointers here");
            ...
            vpushi(pointed_size(&vtop[-1].type));   /* 元素大小 */
            vrott(3);
            gen_opic(op);                           /* 先做地址差 */
            vtop->type.t = ptrdiff_type.t;
            vswap();
            gen_op(TOK_PDIV);                       /* ★ 再除以元素大小 */
        }
```

`p1 - p2` 得到的是**元素个数**，所以要除以 `sizeof(*p)`。

### 1c. 指针 ± 整数（`:2208-2272`）

```c
        } else {
            if (op != '-' && op != '+') tcc_error("cannot use pointers here");
            /* 让指针当第一个操作数 */
            if (bt2 == VT_PTR) { vswap(); t = t1, t1 = t2, t2 = t; }
            ...
            type1 = vtop[-1].type;
            type1.t &= ~VT_ARRAY;
            u = pointed_size(&vtop[-1].type);       /* 元素大小 */
            vpushi(u);
            gen_op('*');                            /* ★ 整数先乘元素大小 */
            gen_opic(op);                           /* 再和地址相加/减 */
            vtop->type = type1;                     /* 结果还是指针 */
        }
```

**`p + n` 变成 `p + n*sizeof(*p)`**，乘法的 `sizeof` 由 `pointed_size` 在编译期算好。
这就是为什么 `int *p; p+1` 前进 4 字节。

---

## 第 2 站：浮点与整数的类型提升（`tccgen.c:2273-2311`）

浮点：

```c
    } else if (is_float(bt1) || is_float(bt2)) {
        if (bt1 == VT_LDOUBLE || bt2 == VT_LDOUBLE) t = VT_LDOUBLE;
        else if (bt1 == VT_DOUBLE || bt2 == VT_DOUBLE) t = VT_DOUBLE;
        else t = VT_FLOAT;                       /* 取更宽的 */
        if (op != '+' && op != '-' && op != '*' && op != '/' &&
            (op < TOK_ULT || op > TOK_GT))
            tcc_error("invalid operands for binary operation");
        goto std_op;
    } else if (op == TOK_SHR || op == TOK_SAR || op == TOK_SHL) {
        t = bt1 == VT_LLONG ? VT_LLONG : VT_INT;
        ...
```

整数：取"更宽的类型"（`long long` > `int` > `short` > `char`），
并按 C 规则决定 unsigned。

---

## 第 3 站：`std_op` —— 统一转换后归约（`tccgen.c:2312-2354`）

```c
/* src/core/tccgen.c:2312-2354（节选）*/
    std_op:
        /* 无符号运算的收尾：把 / % < > <= >= 换成无符号版本 */
        if (t & VT_UNSIGNED) {
            if (op == TOK_SAR) op = TOK_SHR;
            else if (op == '/') op = TOK_UDIV;
            else if (op == '%') op = TOK_UMOD;
            else if (op == TOK_LT) op = TOK_ULT;
            ...
        }
        vswap();
        type1.t = t; type1.ref = NULL;
        gen_cast(&type1);           /* 下面那张转成公共类型 */
        vswap();
        if (op == TOK_SHR || op == TOK_SAR || op == TOK_SHL)
            type1.t = VT_INT;       /* 移位量保持 int */
        gen_cast(&type1);           /* 上面那张也转 */
        if (is_float(t))
            gen_opif(op);           /* 浮点归约 */
        else
            gen_opic(op);           /* 整数归约 */
        if (op >= TOK_ULT && op <= TOK_GT)
            vtop->type.t = VT_INT;  /* 比较结果是 int */
        else
            vtop->type.t = t;       /* 运算结果类型 */
```

**流程**：先把两个操作数都 `gen_cast` 到公共类型，再按类型分派给 `gen_opic` / `gen_opif`。
无符号运算通过换 token（`/`→`TOK_UDIV` 等）表达，后端就发无符号指令。

---

## 第 4 站：整数常量折叠 —— `gen_opic`（心跳）（`tccgen.c:1864`）

这是 TCC "全部优化"的主力。**两个都是常量就当场算，否则交给后端。**

```c
/* src/core/tccgen.c:1864-1883 */
static void gen_opic(int op)
{
    SValue *v1 = vtop - 1;
    SValue *v2 = vtop;
    int t1 = v1->type.t & VT_BTYPE;
    int t2 = v2->type.t & VT_BTYPE;
    int c1 = (v1->r & (VT_VALMASK | VT_LVAL | VT_SYM)) == VT_CONST;
    int c2 = (v2->r & (VT_VALMASK | VT_LVAL | VT_SYM)) == VT_CONST;
    uint64_t l1 = c1 ? v1->c.i : 0;
    uint64_t l2 = c2 ? v2->c.i : 0;
    int shm = (t1 == VT_LLONG) ? 63 : 31;
    ...
    if (c1 && c2) {
        switch(op) {
        case '+': l1 += l2; break;
        case '-': l1 -= l2; break;
        case '&': l1 &= l2; break;
        ...
        case '*': l1 *= l2; break;
        case '/': case '%': ...
            if (l2 == 0) {           /* ★ 除零：常量错误 or 让运行时爆掉 */
                if (const_wanted)
                    tcc_error("division by zero in constant");
                goto general_case;
            }
            ...
        case TOK_SHL: l1 <<= (l2 & shm); break;
        ...
        }
        v1->c.i = l1;
        vtop--;                      /* ★ 两个弹成一个 */
    } else {
        ...非全常量...
    }
}
```

同时它还做**代数化简**（`:1937-2000`）：

```c
        /* x*0 → 0，x&0 → 0，x|−1 → −1，x%1 → 0 */
        } else if (c2 && ((l2 == 0 && (op == '&' || op == '*')) ||
                          (op == '|' && (l2 == -1 || ...)) ||
                          (l2 == 1 && (op == '%' || op == TOK_UMOD)))) {
            if (l2 == 1) vtop->c.i = 0;
            vswap(); vtop--;
        }
        /* x*1，x+0，x-0，x|0，x^0，x<<0 ... → 直接扔掉常量 */
        } else if (c2 && (((op=='*'||op=='/'||op=='%'||op==TOK_UDIV) && l2==1) ||
                          ((op=='+'||op=='-'||op=='|'||op=='^'||op==TOK_SHL||...) && l2==0) ||
                          (op=='&' && (l2==-1 || ...)))) {
            vtop--;
        }
        /* 乘/除 2 的幂 → 换成移位 */
        } else if (c2 && (op == '*' || op == TOK_PDIV || op == TOK_UDIV)) {
            if (l2 > 0 && (l2 & (l2 - 1)) == 0) {
                int n = -1;
                while (l2) { l2 >>= 1; n++; }
                vtop->c.i = n;
                op = (op == '*') ? TOK_SHL : (op == TOK_PDIV ? TOK_SAR : TOK_SHR);
            }
            goto general_case;
        }
```

**这就是 TCC 的"优化器"**：常量折叠 + 几条代数恒等式 + `*2^k → <<k`。
没有循环优化、没有内联、没有寄存器图着色。**简单，但有效。**

最后 `general_case`（`:2002-2009`）才是发指令：

```c
        general_case:
            if (t1 == VT_LLONG || t2 == VT_LLONG || (PTR_SIZE==8 && (t1==VT_PTR||t2==VT_PTR)))
                gen_opl(op);      /* 64 位（32 位平台专用） */
            else
                gen_opi(op);      /* ★ 后端发真 ALU 指令（第 47 篇） */
```

---

## 第 5 站：浮点常量折叠 —— `gen_opif`（`tccgen.c:2014`）

```c
/* src/core/tccgen.c:2014-2073（节选）*/
static void gen_opif(int op)
{
    ...
    if (c1 && c2) {
        if (v1->type.t == VT_FLOAT) { f1 = v1->c.f; f2 = v2->c.f; }
        else if (v1->type.t == VT_DOUBLE) { f1 = v1->c.d; f2 = v2->c.d; }
        else { f1 = v1->c.ld; f2 = v2->c.ld; }

        /* ★ 只在有限数上折叠（NaN/Inf 按 ANSI 不折叠） */
        if (!ieee_finite(f1) || !ieee_finite(f2))
            goto general_case;

        switch(op) {
        case '+': f1 += f2; break;
        case '-': f1 -= f2; break;
        case '*': f1 *= f2; break;
        case '/':
            if (f2 == 0.0) { if (const_wanted) tcc_error("division by zero in constant"); goto general_case; }
            f1 /= f2;
            break;
        default: goto general_case;
        }
        ...写回 v1->c... vtop--;
    } else {
    general_case:
        gen_opf(op);       /* 后端发浮点指令 */
    }
}
```

**`ieee_finite`**（`tccgen.c:112`）判断是不是 NaN/Inf——**因为标准规定 `NaN` 不参与常量折叠**。

---

## 第 6 站：`gen_opl` —— 32 位平台的 64 位运算（选读）

在 32 位平台上，`long long` 的加乘除要拆成高低 32 位手动算（`:1624-1860`），
或者调用 `__divdi3` 之类的辅助函数：

```c
    case '/':
        func = TOK___divdi3;      /* 调用运行时库函数做 64 位除法 */
        goto gen_func;
    ...
    gen_func:
        vpush_global_sym(&func_old_type, func);
        vrott(3);
        gfunc_call(2);
```

**x86-64 原生支持 64 位运算，所以这段在 64 位编译时被跳过。**

---

## 【把 t.c 的 `2 * K` 归约一遍】

`K` 展开成 `8`（第 07 篇），栈上两张便利贴：`{VT_CONST, c=2}` 和 `{VT_CONST, c=8}`。

1. `expr_prod` 读到 `*`，调 `gen_op('*')`；
2. `gen_op`：`bt1=bt2=VT_INT`，走整数分支，`goto std_op`；
3. `std_op`：`gen_cast` 到 `int`（已经是），调 `gen_opic('*')`；
4. `gen_opic`：`c1 && c2` 都为真 → `l1 = 2*8 = 16` → `v1->c.i = 16`，`vtop--`；
5. 结果：一张 `{VT_CONST, c=16}`。**机器码里没有 `imul`。**

之后 `int y = 2*K;` 的赋值就是 `mov DWORD [rbp-16], 16`。

---

## 【动手小实验】

1. `int x = 2*8;` 编译到 `.o`，反汇编确认没有乘法。
2. `int f(int a){return a*2;}` —— `a` 不是常量，反汇编应该有 `shl`（因为 `*2` 被换成移位）。
3. `int g(int a){return a*3;}` —— 不是 2 的幂，应该真有 `imul`。
4. 写 `int p[10]; int *q = p + 3;`，反汇编看 `+3` 是否变成 `+12`。

## 【通关暗号】

```bash
printf 'int main(void){return 2*8;}\n' > /tmp/c.c
./tcc -c /tmp/c.c -o /tmp/c.o && objdump -d /tmp/c.o 2>/dev/null | grep -ci imul
# 期望：0（常量折叠掉了）
printf 'int f(int a){return a*2;}\n' > /tmp/s.c
./tcc -c /tmp/s.c -o /tmp/s.o && objdump -d /tmp/s.o 2>/dev/null | grep -ciE 'shl|sal'
# 期望：>=1（*2 变成移位）
```

## 【常见卡点】

- **指针算术的 `*sizeof` 在 `gen_op` 里自动做**。
- **`gen_opic` 是"优化器"**：常量折叠 + 代数化简 + 乘 2 的幂转移位。
- **除零在常量表达式里报错，在运行时留给 CPU**（`goto general_case`）。
- **NaN/Inf 不参与浮点常量折叠**。
- **`gen_opi`/`gen_opl`/`gen_opf` 是后端函数**（第 47 篇）。

**下一篇**：`23-类型转换gen_cast.md` —— `(int)x`、隐式提升都靠它。
