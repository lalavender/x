# 24 · 赋值 `vstore` 与 `++/--`：写进内存

> **一句话**：`a = b` 在值栈上是两张便利贴：`a`（位置）在下面、`b`（值）在上面。
> `vstore()` 把上面的值写进下面的位置。结构体赋值靠 `memmove`，位域要"读改写"。
>
> 对应源码：`src/core/tccgen.c:3069`（`vstore`）、`:3241`（`inc` 处理 `++/--`）、
> `:1550`（`gv_dup`）、`:4471`（`lvalue_type`）。

---

## 第 0 站：赋值前先看两张便利贴

调用 `vstore` 时，约定值是：

- `vtop[-1]` = **目标**（左值，"一个位置"）；
- `vtop[0]` = **源**（值）。

`vstore` 就是要"把 `vtop[0]` 写进 `vtop[-1]` 指的地方"。

---

## 第 1 站：`vstore` 开头 —— 类型转换和 char/short 优化（`tccgen.c:3069`）

```c
/* src/core/tccgen.c:3069-3089 */
ST_FUNC void vstore(void)
{
    int sbt, dbt, ft, r, t, size, align, bit_size, bit_pos, rc, delayed_cast;

    ft = vtop[-1].type.t;          /* 目标类型 */
    sbt = vtop->type.t & VT_BTYPE; /* 源基本类型 */
    dbt = ft & VT_BTYPE;           /* 目标基本类型 */
    if ((((sbt == VT_INT || sbt == VT_SHORT) && dbt == VT_BYTE) ||
         (sbt == VT_INT && dbt == VT_SHORT))
        && !(vtop->type.t & VT_BITFIELD)) {
        /* ★ 优化 char/short 转换：只记一个延迟标志，别急着截断 */
        delayed_cast = VT_MUSTCAST;
        vtop->type.t = ft & VT_TYPE;
        if (ft & VT_CONSTANT)
            tcc_warning("assignment of read-only location");
    } else {
        delayed_cast = 0;
        if (!(ft & VT_BITFIELD))
            gen_assign_cast(&vtop[-1].type);   /* 常规：检查+转换 */
    }
```

**为什么要延迟 char/short？** 因为马上要存进 1 字节的 `char`，
截断交给 `store` 的指令宽度做就行，不必先专门截断一次。
`delayed_cast` 会在最后写回便利贴的 `r` 里（`:3236`），等下次取值时才真正转。

---

## 第 2 站：结构体赋值 —— 调用 `memmove`（`tccgen.c:3091`）

```c
/* src/core/tccgen.c:3091-3122（节选）*/
    if (sbt == VT_STRUCT) {
        /* 结构体赋值 → 生成 memmove 调用 */
        size = type_size(&vtop->type, &align);

        /* 目标地址 */
        vswap();
        vtop->type.t = VT_PTR;
        gaddrof();

        /* memmove 的地址（用 memmove 因为源目可能重叠） */
        vpush_global_sym(&func_old_type, TOK_memmove);

        vswap();
        /* 源地址 */
        vpushv(vtop - 2);
        vtop->type.t = VT_PTR;
        gaddrof();
        /* 大小 */
        vpushi(size);
        gfunc_call(3);              /* ★ 调用 memmove(dst, src, size) */

        /* 留下源在栈上（赋值表达式的值） */
    }
```

**结构体不能靠一条 `mov` 拷贝**，TCC 直接生成一次 `memmove(dst, src, size)` 调用。
`size` 是编译期算好的常量。这是 TCC "够用就行"的典型做法——
不做内联展开，直接调库函数。

> 注释里特意写明用 `memmove` 而不是 `memcpy`：
> **"dest and src may be same"**（自己赋值给自己时不能出错）。

---

## 第 3 站：位域赋值 —— 读改写（`tccgen.c:3123-3171`）

位域 `s.b = x` 不能直接写一个字节，得把那一小段位"抠出来换掉"：

```c
/* src/core/tccgen.c:3123-3171（节选）*/
    } else if (ft & VT_BITFIELD) {
        /* 先保住左值作为表达式结果（支持 s.b = s.a = n;） */
        vdup(), vtop[-1] = vtop[-2];

        bit_pos = BIT_POS(ft);
        bit_size = BIT_SIZE(ft);
        vtop[-1].type.t = ft & ~VT_STRUCT_MASK;   /* 去掉位域信息防循环 */

        if (r == VT_STRUCT) {
            gen_cast_s(...); store_packed_bf(bit_pos, bit_size);
        } else {
            unsigned long long mask = (1ULL << bit_size) - 1;
            if ((ft & VT_BTYPE) != VT_BOOL) {
                /* 源值先和掩码与 */
                vpushi((unsigned)mask);
                gen_op('&');
            }
            vpushi(bit_pos);
            gen_op(TOK_SHL);              /* 源值左移到位域位置 */
            vswap();
            vdup();                       /* 复制目标地址 */
            vrott(3);
            /* 读目标，屏蔽掉这一段，再和源或起来 */
            vpushi(~((unsigned)mask << bit_pos));
            gen_op('&');
            gen_op('|');
            vstore();                     /* 写回整个存储单元 */
            vpop();
        }
```

位域赋值 = **(读整个存储单元) & ~(掩码 << 位置) | (源 << 位置)**。经典的位操作。

---

## 第 4 站：普通赋值 —— `store`（`tccgen.c:3172-3237`）

```c
/* src/core/tccgen.c:3172-3237（节选）*/
    } else if (dbt == VT_VOID) {
        --vtop;                       /* void 赋值：直接丢 */
    } else {
        rc = RC_INT;
        if (is_float(ft)) {
            rc = RC_FLOAT;
            ...
        }
        r = gv(rc);                   /* ★ 把源值装进寄存器 */

        /* 如果目标地址被溢出到栈上了，先读回地址 */
        if ((vtop[-1].r & VT_VALMASK) == VT_LLOCAL) {
            SValue sv;
            t = get_reg(RC_INT);
            sv.type.t = VT_PTR;
            sv.r = VT_LOCAL | VT_LVAL;
            sv.c.i = vtop[-1].c.i;
            load(t, &sv);
            vtop[-1].r = t | VT_LVAL;
        }
        /* 64 位：第二个寄存器写到 +8 处 */
        if (64 位类型) {
            vtop[-1].type.t = load_type;
            store(r, vtop - 1);       /* ★ 写低半 */
            ... 调整地址 +8 ...
            store(vtop->r2, vtop - 1);/* 写高半 */
        } else {
            store(r, vtop - 1);       /* ★ 后端：发 mov [目标], 寄存器（第 46 篇） */
        }

        vswap();
        vtop--;                       /* 注意不是 vpop，避免 x86 清浮点栈 */
        vtop->r |= delayed_cast;      /* 把延迟的 char/short 转换记上 */
    }
}
```

**核心就一句 `store(r, vtop - 1)`**：把寄存器 `r` 里的值写进 `vtop[-1]` 描述的地址。
`store` 是后端函数（`x86_64-gen.c:540`，第 46 篇），它会根据左值的
`VT_LVAL_BYTE/SHORT` 选 `movb`/`movw`/`movl`/`movq`。

**赋值表达式的值**：最后 `vswap(); vtop--` 让栈顶留下"赋值结果"，
所以 `a = b = c` 能继续算。

---

## 第 5 站：`inc`（`tccgen.c:3241`）

`++`/`--` 分前置和后置，用同一个 `inc`：

```c
/* src/core/tccgen.c:3240-3256 */
/* post 表示前置(0)/后置(1)；c 是 TOK_INC 或 TOK_DEC */
ST_FUNC void inc(int post, int c)
{
    test_lvalue();          /* 必须可写 */
    vdup();                 /* 复制一份左值（保存） */
    if (post) {
        gv_dup();           /* 后置：再复制一份值（保存旧值） */
        vrotb(3);
        vrotb(3);           /* 旋转，把"旧值"挪到合适位置 */
    }
    /* 加常量 */
    vpushi(c - TOK_MID);    /* ★ TOK_INC - TOK_MID = +1；TOK_DEC 的差是 -1 */
    gen_op('+');            /* 左值 + 1 或 -1 */
    vstore();               /* 写回 */
    if (post)
        vpop();             /* 后置：表达式结果是旧值，把算出的新值弹掉 */
}
```

**`c - TOK_MID` 又是 TCC 的"编号即一切"技巧**：
`TOK_INC` 和 `TOK_DEC` 在 token 编号里关于 `TOK_MID` 对称，
所以两者相减正好得到 `+1` 或 `-1`。**不用写 `if (c==TOK_INC) vpushi(1); else vpushi(-1);`**

前置 `++x`：返回新值；后置 `x++`：返回旧值（先把旧值保存起来，最后弹掉新值）。

---

## 第 6 站：`gv_dup`（`tccgen.c:1550`）

`inc` 和别处用到的 `gv_dup`，作用是"把栈顶值物化后复制一份到栈上"：

```c
/* src/core/tccgen.c:1549-1600 附近（骨架）*/
static void gv_dup(void)
{
    int r, rc;
    CType type;
    SValue sv;
    vdup();
    if ((vtop->r & VT_VALMASK) != VT_LLOCAL) {
        /* 复制后要重新装载第二个，避免两个便利贴共享同一个寄存器 */
        type = vtop->type;
        sv = *vtop;
        set_reg(...);  /* 找一个新寄存器 */
        ...
    }
    rc = ...;
    gv(rc);
    ...
}
```

一句话：**复制值的时候要保证两份各自有独立的寄存器/位置**，否则一个被改另一个也变。
（细节留给需要时再读，理解意图即可。）

---

## 【把 `x = y * 2` 走一遍】

1. `x`：便利贴 `{int, r=VT_LOCAL|VT_LVAL, c=-8}`；
2. 赋值的右结合：`expr_eq` 先 `test_lvalue()`；
3. `y * 2`：读 `y`，读 `2`，`gen_op('*')`：
   - `2` 是常量，`y` 不是 → `gen_opic` 走 `c2 && op=='*' && l2==2` 的"乘 2 的幂"分支，
     把 `*` 换成 `TOK_SHL`，常量改成 1；
   - `gen_opi` 发 `shl`（第 47 篇）；
4. 结果便利贴 `{int, r=寄存器}`；
5. `vstore`：`gv(RC_INT)` 把结果装寄存器，`store(reg, &x)` 发
   `mov [rbp-8], reg`；
6. `vswap(); vtop--`，栈顶留下赋值结果（若外面还要用）。

---

## 【动手小实验】

1. 写 `s.b = 5;`（位域），反汇编看是不是"读-与-或-写"。
2. 写 `struct S a,b; a=b;`，看是否出现 `memmove` 调用。
3. 写 `int i=0; return i++;` 和 `return ++i;`，看结果区别（0 vs 1）。
4. `char c = 300;` 反汇编确认没有单独的截断指令（延迟转换生效）。

## 【通关暗号】

```bash
printf 'int main(void){int i=0; int a=i++; int b=++i; return a*10+b;}\n' > /tmp/i.c
./tcc -run /tmp/i.c; echo $?
# 期望：2（a=0, b=2 → 0*10+2=2）
```

## 【常见卡点】

- **`vstore` 约定 `[-1]` 是目标、`[0]` 是源**。
- **结构体赋值用 `memmove`**，不是逐字段拷贝。
- **位域赋值是"读改写"**。
- **`char/short` 赋值延迟截断**（`delayed_cast`），最后写进便利贴 `r`。
- **`inc` 用 `c - TOK_MID` 得到 ±1**，是编号设计的好处。

**下一篇**：`25-指针算术与type_size.md` —— 类型大小怎么算，指针加减怎么乘。
