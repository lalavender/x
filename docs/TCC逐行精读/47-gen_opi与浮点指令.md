# 47 · `gen_opi` / `gen_opf`：发真正的 ALU 与浮点指令

> **一句话**：`gen_opic`（前端，第 22 篇）决定"这两个便利贴怎么算"，
> 在不是全常量时调 `gen_opi`。后端把"运算 + 类型 + 宽度"翻译成具体 x86 指令，
> 比较运算还会把结果变成 `VT_CMP` 便利贴。
>
> 对应源码：`src/targets/x86_64-gen.c:1737`（`gen_opi`）、`:1872`（`gen_opf`）、
> `:2074/2116/2179`（`gen_cvt_itof`/`ftof`/`ftoi`）、`:1643`（`gjmp`）。

---

## 第 1 站：`gen_opi` 的开关（`x86_64-gen.c:1737`）

```c
/* src/targets/x86_64-gen.c:1737-1746 */
void gen_opi(int op)
{
    int r, fr, opc, c;
    int ll, uu, cc;

    ll = is64_type(vtop[-1].type.t);      /* 是不是 64 位 */
    uu = (vtop[-1].type.t & VT_UNSIGNED) != 0;
    cc = (vtop->r & (VT_VALMASK|VT_LVAL|VT_SYM)) == VT_CONST;  /* 右操作数是常量？ */

    switch(op) {
    case '+':
    case TOK_ADDC1:
        opc = 0;
    gen_op8:                              /* ★ 加减与或异的公共代码 */
        ...
```

**核心设计**：`+ - & ^ |` 用同一个 `gen_op8`，只换 `opc`（x86 ModRM 里的 `/digit`）：

| op | opc | x86 操作码高位 |
|---|---|---|
| `+` | 0 | `add` |
| `|` | 1 | `or` |
| `&` | 4 | `and` |
| `-` | 5 | `sub` |
| `^` | 6 | `xor` |
| `TOK_ADDC1` | 0 | `adc`（带进位，64 位加法用） |
| `TOK_SUBC1` | 5 | `sbb` |

### 1a. 常量优化（`:1751`）

```c
/* src/targets/x86_64-gen.c:1751-1765（节选）*/
        if (cc && (!ll || (int)vtop->c.i == vtop->c.i)) {
            /* 右操作数是常量 */
            vswap();
            r = gv(RC_INT);
            vswap();
            c = vtop->c.i;
            if (c == (char)c) {
                /* 常量能放进 1 字节：用 0x83 短格式 */
                orex(ll, r, 0, 0x83);
                o(0xc0 | (opc << 3) | REG_VALUE(r));
                g(c);
            } else {
                orex(ll, r, 0, 0x81);       /* 否则 0x81 + 4 字节立即数 */
                oad(0xc0 | (opc << 3) | REG_VALUE(r), c);
            }
        } else {
            gv2(RC_INT, RC_INT);            /* 两个寄存器 */
            r = vtop[-1].r;
            fr = vtop[0].r;
            orex(ll, r, fr, (opc << 3) | 0x01);
            o(0xc0 + REG_VALUE(r) + REG_VALUE(fr) * 8);
        }
```

**`x = x + 5` 用 `add $5, eax`（0x83）** 比"先把 5 装寄存器再 add"省一条指令。
这是后端做的重要优化（前端只管"加法"，后端选最优编码）。

### 1b. 乘法与移位（`:1798-1832`）

```c
    case '*':
        gv2(RC_INT, RC_INT);
        r = vtop[-1].r; fr = vtop[0].r;
        orex(ll, fr, r, 0xaf0f);            /* imul fr, r */
        o(0xc0 + REG_VALUE(fr) + REG_VALUE(r) * 8);
        vtop--;
        break;
    case TOK_SHL: opc = 4; goto gen_shift;
    case TOK_SHR: opc = 5; goto gen_shift;
    case TOK_SAR: opc = 7;
    gen_shift:
        opc = 0xc0 | (opc << 3);
        if (cc) {                           /* 移位量是常量 */
            vswap(); r = gv(RC_INT); vswap();
            orex(ll, r, 0, 0xc1);           /* shl/shr/sar $imm, r */
            o(opc | REG_VALUE(r));
            g(vtop->c.i & (ll ? 63 : 31));  /* 移位量按宽度取模 */
        } else {
            gv2(RC_INT, RC_RCX);            /* ★ 移位量必须在 cl */
            r = vtop[-1].r;
            orex(ll, r, 0, 0xd3);           /* shl/shr/sar %cl, r */
            o(opc | REG_VALUE(r));
        }
        vtop--;
        break;
```

**x86 的变量移位只能用 `cl`**，所以 `gv2(RC_INT, RC_RCX)` 强制第二个操作数进 `rcx`。

### 1c. 除法（`:1833-1857`）

```c
    case TOK_UDIV: case TOK_UMOD: uu = 1; goto divmod;
    case '/': case '%': case TOK_PDIV: uu = 0;
    divmod:
        /* 被除数必须在 eax，除数在 rcx */
        gv2(RC_RAX, RC_RCX);
        r = vtop[-1].r; fr = vtop[0].r;
        vtop--;
        save_reg(TREG_RDX);                 /* rdx 会被破坏，先保存 */
        orex(ll, 0, 0, uu ? 0xd231 : 0x99); /* xor %edx,%edx 或 cqto */
        orex(ll, fr, 0, 0xf7);              /* div fr */
        o((uu ? 0xf0 : 0xf8) + REG_VALUE(fr));
        if (op == '%' || op == TOK_UMOD) r = TREG_RDX;   /* 余数在 rdx */
        else                             r = TREG_RAX;   /* 商在 rax */
        vtop->r = r;
        break;
```

**x86 除法硬性要求**：被除数在 `rax`（+`rdx`），商/余数也在 `rax`/`rdx`。
所以后端**覆盖前端的寄存器选择**，强制操作数进 `rax`/`rcx`。这是 ABI/ISA 约束的典型。

### 1d. 比较 → `VT_CMP`（`:1774`）

```c
/* src/targets/x86_64-gen.c:1773-1777 */
        vtop--;
        if (op >= TOK_ULT && op <= TOK_GT) {
            vtop->r = VT_CMP;      /* ★ 结果不是 0/1，而是"标志位" */
            vtop->c.i = op;        /* 记下比较类型 */
        }
        break;
```

**减法后不立刻取结果**，而是标记 `VT_CMP`——因为条件跳转可以直接用标志位
（第 28 篇）。这就是 `VT_CMP` 的诞生地。

---

## 第 2 站：`gen_opf`（浮点，`x86_64-gen.c:1872`）

```c
/* src/targets/x86_64-gen.c:1872-1900（节选）*/
void gen_opf(int op)
{
    int a, ft, fc, swapped, r;
    int float_type =
        (vtop->type.t & VT_BTYPE) == VT_LDOUBLE ? RC_ST0 : RC_FLOAT;

    /* 常量转成内存引用（x86 浮点指令可用内存操作数） */
    if ((vtop[-1].r & (VT_VALMASK|VT_LVAL)) == VT_CONST) {
        vswap(); gv(float_type); vswap();
    }
    if ((vtop[0].r & (VT_VALMASK|VT_LVAL)) == VT_CONST)
        gv(float_type);
    ...
    /* 交换顺序，让 t1 是寄存器、t2 是内存 */
    if (vtop[-1].r & VT_LVAL) { vswap(); swapped = 1; }
```

### 2a. `double`/`float` 比较（`:1965-2012`）

```c
        if (op >= TOK_ULT && op <= TOK_GT) {
            ...
            if (op == TOK_EQ || op == TOK_NE)
                o(0x2e0f);            /* ucomisd */
            else
                o(0x2f0f);            /* comisd */
            ...
            vtop--;
            vtop->r = VT_CMP;
            vtop->c.i = op | 0x100;   /* ★ 0x100 标记"浮点比较" */
        }
```

**`| 0x100` 是一个标记位**：第 46 篇 `load` 和 `gtst` 里看到 `fc & 0x100` 就知道
这是浮点比较，要额外处理 `NaN` 的情况（无序时 `parity flag` 置位）。

### 2b. `long double` 用 x87（`:1901-1963`）

`long double` 走 `st0` 寄存器（`fld`/`faddp`/`fcompp`/`fnstsw` 等），
是比较老的 x87 FPU 指令集。这段代码繁琐，但逻辑同前。

### 2c. 四则运算（`:2013-2073`）

`+ - * /` 用 `addsd`/`subsd`/`mulsd`/`divsd`（double）或
`addss`/…（float），根据 `ft` 选。

---

## 第 3 站：类型转换指令（`:2074/2116/2179`）

第 23 篇前端调它们：

```c
/* 整数 → 浮点（概念）*/
void gen_cvt_itof(int t) {   /* cvtsi2sd / cvtsi2ss / fild */
    ...
}
/* 浮点 → 浮点 */
void gen_cvt_ftof(int t) {   /* cvtss2sd / cvtsd2ss */
    ...
}
/* 浮点 → 整数 */
void gen_cvt_ftoi(int t) {   /* cvttsd2si / cvttss2si */
    ...
}
```

它们把 `xmm`/`st0` 和整数寄存器之间搬值并转换。**前端只说"把 vtop 转成 double"，
后端选具体 `cvt*` 指令。**

---

## 【把 `a / b` 走一遍（int）】

| 步骤 | 说明 |
|---|---|
| 1 | 前端 `gen_op('/')` → `std_op` → `gen_opic` |
| 2 | `gen_opic`：不是常量 → `gen_opi('/')` |
| 3 | `gv2(RC_RAX, RC_RCX)`：`a`→`rax`，`b`→`rcx` |
| 4 | `save_reg(TREG_RDX)`（保存 rdx 旧值） |
| 5 | `cqto`（符号扩展 `rax`→`rdx:rax`） |
| 6 | `idiv rcx` |
| 7 | 结果便利贴 `r = TREG_RAX` |

---

## 【动手小实验】

1. `int f(int a){return a/2;}` 反汇编看有没有 `sar`/`shr`（第 22 篇把 `/2` 变移位）。
2. `int f(int a,int b){return a/b;}` 看 `cqto` + `idiv`。
3. `int f(int a){return a&5;}` 看 `and $5, ...`（0x83 短格式）。
4. `double f(double a,double b){return a<b;}` 看 `comisd` + `setb`。
5. `int f(float a){return (int)a;}` 看 `cvttss2si`。

## 【通关暗号】

```bash
printf 'int f(int a,int b){return a/b;}\n' > /tmp/d.c
./tcc -c /tmp/d.c -o /tmp/d.o && objdump -d /tmp/d.o 2>/dev/null | grep -E 'cqto|idiv|cltd'
# 期望：能看到除法序列
```

## 【常见卡点】

- **加减与或异共用 `gen_op8`**，只换 `opc`。
- **常量用 `0x83` 短编码**，这是后端的优化。
- **变量移位必须进 `cl`**；**除法必须用 `rax`/`rdx`**。
- **比较结果变成 `VT_CMP`**，不是 0/1。
- **浮点比较 `| 0x100` 标记**，处理 NaN。

**下一篇**：`48-跳转与测试深入.md`。
