# 46 · `load` 与 `store`：寄存器和内存之间

> **一句话**：`load(r, sv)` 把便利贴 `sv` 描述的值装进寄存器 `r`；
> `store(r, v)` 把寄存器 `r` 写进 `v` 描述的位置。前端只管"装/存"，
> 后端根据类型（字节/字/双字/四字/浮点）和"住址"选不同指令。
>
> 对应源码：`src/targets/x86_64-gen.c:343`（`load`）、`:540`（`store`）。
> 调用者：`gv`/`save_reg`/`vstore`（第 21、24 篇）。

---

## 第 0 站：`load` 的输入（`x86_64-gen.c:343`）

```c
/* src/targets/x86_64-gen.c:343-359（节选）*/
void load(int r, SValue *sv)
{
    int v, t, ft, fc, fr;
    SValue v1;

    fr = sv->r;                       /* 来源的"住址"（寄存器号或 VT_*） */
    ft = sv->type.t & ~VT_DEFSIGN;    /* 类型 */
    fc = sv->c.i;                     /* 常量值 或 栈偏移 */
    ...
    ft &= ~(VT_VOLATILE | VT_CONSTANT);
```

`fr & VT_LVAL` 决定走哪条大分支：**是"位置"→ 读内存；否则 → 搬/造值。**

---

## 第 1 站：左值——从内存读（`:379-450`）

```c
/* src/targets/x86_64-gen.c:379-402（节选）*/
    if (fr & VT_LVAL) {
        int b, ll;
        if (v == VT_LLOCAL) {
            /* 地址本身在栈上：先把地址读出来 */
            v1.type.t = VT_PTR;
            v1.r = VT_LOCAL | VT_LVAL;
            v1.c.i = fc;
            fr = r;
            if (!(reg_classes[fr] & (RC_INT|RC_R11)))
                fr = get_reg(RC_INT);
            load(fr, &v1);             /* 递归：装载地址 */
        }
        if (fc != sv->c.i) {
            /* 偏移超出 32 位：先用 64 位立即数装载偏移 */
            ...
        }
```

然后按类型选操作码：

```c
/* src/targets/x86_64-gen.c:420-450（节选）*/
        if ((ft & VT_BTYPE) == VT_FLOAT) {
            b = 0x6e0f66; r = REG_VALUE(r);        /* movd (32位浮点) */
        } else if ((ft & VT_BTYPE) == VT_DOUBLE) {
            b = 0x7e0ff3; r = REG_VALUE(r);        /* movq (64位浮点) */
        } else if ((ft & VT_BTYPE) == VT_LDOUBLE) {
            b = 0xdb, r = 5;                       /* fldt */
        } else if ((ft & VT_TYPE) == VT_BYTE || (ft & VT_TYPE) == VT_BOOL) {
            b = 0xbe0f;                            /* ★ movsbl：字节→有符号扩展 */
        } else if ((ft & VT_TYPE) == (VT_BYTE | VT_UNSIGNED)) {
            b = 0xb60f;                            /* ★ movzbl：字节→零扩展 */
        } else if ((ft & VT_TYPE) == VT_SHORT) {
            b = 0xbf0f;                            /* movswl */
        } else if ((ft & VT_TYPE) == (VT_SHORT | VT_UNSIGNED)) {
            b = 0xb70f;                            /* movzwl */
        } else {
            ll = is64_type(ft);                    /* 32 位还是 64 位 */
            b = 0x8b;                              /* mov */
        }
        if (ll) gen_modrm64(b, r, fr, sv->sym, fc);
        else    { orex(ll, fr, r, b); gen_modrm(r, fr, sv->sym, fc); }
```

**这张表就是"类型→指令"的核心**：

| 类型 | 指令 | 说明 |
|---|---|---|
| `char`（有符号） | `movsbl` | 1 字节符号扩展成 32 位 |
| `unsigned char` | `movzbl` | 1 字节零扩展 |
| `short` / `unsigned short` | `movswl`/`movzwl` | 同理 |
| `int`/指针/`long` | `mov` | 直接搬 |
| `long long` | `movq` | 64 位 |
| `float` | `movd`/`movss` | 进 `xmm` |
| `double` | `movq`/`movsd` | 进 `xmm` |
| `long double` | `fldt` | 进 `st0` |

**`char`/`short` 的"符号扩展 vs 零扩展"就靠 `VT_UNSIGNED` 区分**——
这也是第 20 篇 `lvalue_type` 要记 `VT_LVAL_UNSIGNED` 的原因。

---

## 第 2 站：非左值——造值/搬值（`:451-536`）

```c
/* src/targets/x86_64-gen.c:451-504（节选）*/
    } else {
        if (v == VT_CONST) {                      /* 常量 */
            if (fr & VT_SYM) {
                /* 符号地址：static 直接 lea（RIP 相对），否则从 GOT 取 */
                if (sv->sym->type.t & VT_STATIC) {
                    o(0x8d); ... gen_addrpc32(...);      /* lea sym(%rip), r */
                } else {
                    o(0x8b); ... gen_gotpcrel(...);      /* mov GOT(sym), r */
                }
            } else if (is64_type(ft)) {
                o(0xb8 + REG_VALUE(r)); gen_le64(sv->c.i);   /* mov $imm64, r */
            } else {
                o(0xb8 + REG_VALUE(r)); gen_le32(fc);        /* mov $imm32, r */
            }
        } else if (v == VT_LOCAL) {
            gen_modrm(r, VT_LOCAL, sv->sym, fc);             /* lea xxx(%rbp), r */
        } else if (v == VT_CMP) {
            /* ★ 把 CPU 标志位变成 0/1：setcc */
            if ((fc & ~0x100) != TOK_NE) oad(0xb8 + ..., 0);
            else                         oad(0xb8 + ..., 1);
            ... setcc ...
        } else if (v == VT_JMP || v == VT_JMPI) {
            /* ★ 把跳转链变成 0/1：mov $1; jmp over; 回填; mov $0 */
            t = v & 1;
            oad(0xb8 + REG_VALUE(r), t);       /* mov $1, r */
            o(0x05eb);                          /* jmp +5 */
            gsym(fc);                           /* 回填跳转链 */
            oad(0xb8 + REG_VALUE(r), t ^ 1);   /* mov $0, r */
        } else if (v != r) {
            /* 寄存器→寄存器 */
            ...
            orex(1,r,v, 0x89);
            o(0xc0 + REG_VALUE(r) + REG_VALUE(v) * 8);   /* mov v, r */
        }
    }
```

重点看 `VT_CMP` 和 `VT_JMP`：

- **`VT_CMP`**（值在标志位）：用 `setcc` 把条件码变成 0/1。
  `fc` 里存的是比较类型（`TOK_EQ` 等）；`fc & 0x100` 表示浮点比较。
- **`VT_JMP`**（跳转链）：生成 `mov $1; jmp L; L: mov $0`（或反过来），
  并把链回填到中间。**这就是第 28 篇说的"物化"的最终实现。**

---

## 第 3 站：`store`（`x86_64-gen.c:540`）

```c
/* src/targets/x86_64-gen.c:540-596（节选）*/
void store(int r, SValue *v)
{
    int fr, bt, ft, fc;
    ...
    fr = v->r & VT_VALMASK;         /* 目标住址 */
    ft = v->type.t;
    fc = v->c.i;
    ...
    bt = ft & VT_BTYPE;

    if (bt == VT_FLOAT) {
        o(0x66); o(pic); o(0x7e0f); r = REG_VALUE(r);       /* movd */
    } else if (bt == VT_DOUBLE) {
        o(0x66); o(pic); o(0xd60f); r = REG_VALUE(r);       /* movq */
    } else if (bt == VT_LDOUBLE) {
        o(0xc0d9); o(pic); o(0xdb); r = 7;                  /* fstpt */
    } else {
        if (bt == VT_SHORT) o(0x66);                        /* 16 位前缀 */
        if (bt == VT_BYTE || bt == VT_BOOL)
            orex(0, 0, r, 0x88);                            /* movb */
        else if (is64_type(bt)) op64 = 0x89;                /* movq */
        else orex(0, 0, r, 0x89);                           /* mov */
    }
    ...
    if (fr == VT_CONST || fr == VT_LOCAL || (v->r & VT_LVAL)) {
        gen_modrm(r, v->r, v->sym, fc);                     /* 写内存 */
    }
    ...
}
```

**`store` 按目标**：`VT_LOCAL`（`rbp` 相对）、`VT_CONST`（绝对/RIP 相对）、
`VT_LVAL`（寄存器间接）。按类型选字节宽度。

注意 **`store` 不会自动截断**：写 `char` 时用 `movb`（只写 1 字节），
所以第 24 篇 `vstore` 的 `delayed_cast` 不急着截断——`movb` 天然只写低 8 位。

---

## 第 4 站：`load`/`store` 与 GOT（PIC）

非 PE 平台、非 static 的全局符号，`load` 会**通过 GOT 间接访问**（`:361-376`）：

```c
/* src/targets/x86_64-gen.c:361-376（节选）*/
    /* we use indirect access via got */
    if ((fr & VT_VALMASK) == VT_CONST && (fr & VT_SYM) &&
        (fr & VT_LVAL) && !(sv->sym->type.t & VT_STATIC)) {
        int tr = r | TREG_MEM;
        if (is_float(ft)) tr = get_reg(RC_INT) | TREG_MEM;
        gen_modrm64(0x8b, tr, fr, sv->sym, 0);   /* 先从 GOT 取地址 */
        fr = tr | VT_LVAL;                        /* 再用地址读值 */
    }
```

这就是位置无关代码（PIE）的做法：全局变量的地址在 GOT 里，
先 `mov GOT[sym], r` 拿到地址，再 `mov [r], r`。

---

## 【把 `char c = arr[i];` 的存取走一遍】

1. `arr[i]` 求值得到"`char` 左值"便利贴，`r = 寄存器或 VT_LOCAL`；
2. `vstore` 调用 `load(r, vtop)`：`fr & VT_LVAL` 为真，`ft` 是 `VT_BYTE`（有符号）
   → `movsbl [addr], eax`（符号扩展）；
3. 写进 `c`：`store(eax, &c)`，`bt == VT_BYTE` → `movb al, [c]`。

---

## 【动手小实验】

1. `char c=getchar();` 反汇编找 `movsbl`（有符号）或 `movzbl`（无符号，看默认 char）。
2. `unsigned char c; return c;` 看是否用 `movzbl`。
3. `double d=1.5; double e=d;` 看 `movsd`。
4. `int x = arr[i];` 看 `mov [..]`。

## 【通关暗号】

```bash
printf 'int main(void){char a[3]={1,2,3}; char c=a[1]; return c;}\n' > /tmp/l.c
./tcc -c /tmp/l.c -o /tmp/l.o && objdump -d /tmp/l.o 2>/dev/null | grep -E 'movsbl|movzbl|mov +%?[a-z]*0?x?[0-9a-f]*\('
# 期望：能看到带符号扩展的字节读取指令
```

## 【常见卡点】

- **`load` 按类型选指令**：`movsbl`/`movzbl`/`movswl`/`movq`/`movsd`/`fldt`。
- **符号 vs 零扩展靠 `VT_UNSIGNED`**。
- **`VT_CMP` 用 `setcc` 变 0/1；`VT_JMP` 用 mov+jmp+mov 物化**。
- **`store` 只写目标宽度，天然截断**。
- **非 static 全局通过 GOT（PIE）访问**。

**下一篇**：`47-gen_opi与浮点指令.md`。
