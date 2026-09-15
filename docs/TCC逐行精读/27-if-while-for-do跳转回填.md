# 27 · if / while / for / do 与"跳转回填"

> **一句话**：生成跳转时，你还不知道该跳到哪个地址（代码还没生成到那）。
> TCC 用一条**串在跳转指令位移字段里的链表**记录"这里欠一跳"，
> 等目标地址确定后一起回填。这是全 TCC 最漂亮的一个机制。
>
> 对应源码：`src/core/tccgen.c:1605`（`gvtst`）、`src/targets/x86_64-gen.c:1643`（`gjmp`）、
> `:204`（`gsym_addr`）、`:214`（`gsym`）、`:1661`（`gtst_addr`）、`:1688`（`gtst`）、
> `src/core/tccgen.c:5891`（`if`）、`:5921`（`while`）、`:6029`（`for`）、`:6076`（`do`）。

---

## 第 0 站：问题——跳转目标还不知道

生成 `if (x) A else B` 时，编译器要发一条 `jz B_start`。
但此刻 `B` 的代码**还没生成**，`B_start` 地址未知。

教科书做法：记录"这里有个待填的跳转"，全部生成完再遍历修正。
TCC 的做法更省：**把待填的跳转串成链表，链表指针就存在跳转指令的那 4 字节位移里。**

```c
/* src/targets/x86_64-gen.c:227-240 */
/* 发 1 字节指令 + 4 字节数据，返回"数据字段"的地址 */
static int oad(int c, int s)
{
    int t;
    if (nocode_wanted)
        return s;
    o(c);            /* 发指令字节 */
    t = ind;         /* t = 数据字段在 .text 里的偏移 */
    gen_le32(s);     /* 发 4 字节数据（暂时填 s） */
    return t;
}

/* 生成 jmp 到标签 */
#define gjmp2(instr,lbl) oad(instr,lbl)

/* src/targets/x86_64-gen.c:1642-1646 */
int gjmp(int t)
{
    return gjmp2(0xe9, t);   /* 0xe9 = jmp rel32 */
}
```

- `gjmp(t0)` 发一条 `jmp`，位移字段暂时写 `t0`（**这是上一条待填跳转的地址**），
  返回**本条的位移字段地址** `t1`。
- 于是 `t1 -> t0 -> 上上条 -> ... -> 0` 形成链表。
- **`t1` 就是"这条跳转链的新头"。**

回填时：

```c
/* src/targets/x86_64-gen.c:203-217 */
ST_FUNC void gsym_addr(int t, int a)     /* 把链 t 上所有跳转都指向地址 a */
{
    while (t) {
        unsigned char *ptr = cur_text_section->data + t;
        uint32_t n = read32le(ptr);      /* 读出下一个节点 */
        write32le(ptr, a - t - 4);       /* ★ 回填相对位移 */
        t = n;
    }
}

void gsym(int t)
{
    gsym_addr(t, ind);                   /* 回填到"当前位置" */
}
```

**回填就是遍历链表，把每条跳转的位移改成 `目标 - 本条 - 4`。**

> 12 岁比喻：你要寄信但不知道对方新地址。于是你写信时先填"上一个问过地址的人"，
> 攒成一串。等知道地址了，从最后一个人开始，逐个打电话告诉他。

---

## 第 1 站：把值变成跳转 —— `gvtst`（`tccgen.c:1605`）

`gvtst` = "generate value test"：把栈顶的值当条件，生成一条跳转。

```c
/* src/core/tccgen.c:1602-1620 */
ST_FUNC int gvtst(int inv, int t)
{
    int v = vtop->r & VT_VALMASK;
    if (v != VT_CMP && v != VT_JMP && v != VT_JMPI) {
        vpushi(0);
        gen_op(TOK_NE);        /* ★ 把"任意值"变成"和 0 比较"，得到 VT_CMP */
    }
    if ((vtop->r & (VT_VALMASK | VT_LVAL | VT_SYM)) == VT_CONST) {
        /* 常量条件：编译期就能决定 */
        if ((vtop->c.i != 0) != inv)
            t = gjmp(t);       /* 一定跳：追加一条无条件跳转 */
        vtop--;
        return t;
    }
    return gtst(inv, t);       /* ★ 后端：根据 VT_CMP/VT_JMP 发条件跳转 */
}
```

- `inv` = 是否反转测试（`while` 用 `gvtst(1,...)` 表示"条件为假就跳出循环"）；
- `t` = 已有的跳转链；
- 结果是**新的跳转链**。

后端 `gtst`（`x86_64-gen.c:1688`）处理两类：

```c
/* src/targets/x86_64-gen.c:1687-1734（节选）*/
ST_FUNC int gtst(int inv, int t)
{
    int v = vtop->r & VT_VALMASK;
    if (v == VT_CMP) {
        /* 快路径：CPU 标志位已经设好，直接条件跳转 */
        ...
        t = gjmp2((vtop->c.i - 16) ^ inv, t);   /* 按比较类型发 jcc */
    } else if (v == VT_JMP || v == VT_JMPI) {
        /* && / || 遗留的跳转链：合并到 t 里 */
        ...
    }
    vtop--;
    return t;
}
```

**`VT_CMP` = "值在 CPU 标志位里"**——比如刚做完比较，结果还没落地，
直接发条件跳转最省。这就是 `tcc.h:836` 那个 `VT_CMP` 的用意。

---

## 第 2 站：`if`（`tccgen.c:5891`）

```c
/* src/core/tccgen.c:5891-5920（节选）*/
    if (tok == TOK_IF) {
        int saved_nocode_wanted = nocode_wanted;
        next();
        skip('(');
        gexpr();                    /* 求条件 */
        skip(')');
        cond = condition_3way();    /* 能编译期定真假吗？ */
        if (cond == 1)
            a = 0, vpop();          /* 恒真：不需要跳转 */
        else
            a = gvtst(1, 0);        /* ★ 条件假 → 跳到 else/结尾 */
        if (cond == 0)
            nocode_wanted |= 0x20000000;   /* 恒假：then 分支不生成 */
        block(bsym, csym, 0);       /* then 分支 */
        if (cond != 1)
            nocode_wanted = saved_nocode_wanted;
        c = tok;
        if (c == TOK_ELSE) {
            next();
            d = gjmp(0);            /* then 结束 → 跳出 else */
            gsym(a);                /* ★ 回填条件跳转到这里（else 开始） */
            if (cond == 1)
                nocode_wanted |= 0x20000000;
            block(bsym, csym, 0);   /* else 分支 */
            gsym(d);                /* ★ 回填 else 结束的跳转 */
            if (cond != 0)
                nocode_wanted = saved_nocode_wanted;
        } else
            gsym(a);                /* 没有 else：回填到结尾 */
    }
```

流程：

1. `gvtst(1, 0)`：条件假就跳到尚未知道的 `a`；
2. 生成 then 分支；
3. 有 else：`gjmp(0)` 生成"跳过 else"的跳转 `d`，`gsym(a)` 把 else 起点填上，
   生成 else，`gsym(d)` 填到结尾；
4. 没 else：`gsym(a)` 直接填到结尾。

**`condition_3way` 让 `if (1)`、`if (0)` 只生成一个分支。**

---

## 第 3 站：`while`（`tccgen.c:5921`）

```c
/* src/core/tccgen.c:5921-5939（节选）*/
    } else if (tok == TOK_WHILE) {
        int saved_nocode_wanted;
        nocode_wanted &= ~0x20000000;
        next();
        d = ind;                    /* ★ d = 循环开头（条件前）*/
        vla_sp_restore();
        skip('(');
        gexpr();                    /* 条件 */
        skip(')');
        a = gvtst(1, 0);            /* ★ 条件假 → 跳出循环 */
        b = 0;
        ++local_scope;
        saved_nocode_wanted = nocode_wanted;
        block(&a, &b, 0);           /* 循环体：break 用 &a，continue 用 &b */
        nocode_wanted = saved_nocode_wanted;
        --local_scope;
        gjmp_addr(d);               /* ★ 无条件跳回 d（条件重新判断）*/
        gsym(a);                    /* 回填空条件跳出 */
        gsym_addr(b, d);            /* ★ 回填 continue 到 d */
    }
```

- `d = ind` 记住循环开头；
- `gvtst(1,0)` 造"条件假跳出"链 `a`，也是 `break` 的目标（注意传给 `block` 的是 `&a`）；
- `b` 是 `continue` 链；`gjmp_addr(d)` 循环体末尾跳回开头条件；
- `gsym_addr(b, d)` 让所有 `continue` 跳到 `d`（重新判断条件）。

**`while` 的 `continue` 要回到条件判断**，所以目标是 `d`。

---

## 第 4 站：`for`（`tccgen.c:6029`）

```c
/* src/core/tccgen.c:6029-6073（节选）*/
    } else if (tok == TOK_FOR) {
        int e;
        int saved_nocode_wanted;
        nocode_wanted &= ~0x20000000;
        next();
        skip('(');
        s = local_stack;
        ++local_scope;
        if (tok != ';') {
            if (!decl0(VT_LOCAL, 1, NULL)) {   /* C99: for(int i=0;...) */
                gexpr();                        /* 或普通初始化表达式 */
                vpop();
            }
        }
        skip(';');
        d = ind;                    /* d = 条件判断位置 */
        c = ind;                    /* c = 步进表达式位置（暂时） */
        vla_sp_restore();
        a = 0; b = 0;
        if (tok != ';') {
            gexpr();                /* 条件 */
            a = gvtst(1, 0);        /* 条件假 → 跳出 */
        }
        skip(';');
        if (tok != ')') {
            e = gjmp(0);            /* 先跳过步进表达式 */
            c = ind;                /* ★ c = 步进表达式真正的地址 */
            vla_sp_restore();
            gexpr();                /* 步进表达式 i++ */
            vpop();
            gjmp_addr(d);           /* 步进后跳回条件 */
            gsym(e);                /* 回填"跳过步进"的跳转 */
        }
        skip(')');
        saved_nocode_wanted = nocode_wanted;
        block(&a, &b, 0);           /* 循环体 */
        nocode_wanted = saved_nocode_wanted;
        gjmp_addr(c);               /* ★ 循环体末尾跳回步进表达式 c */
        gsym(a);                    /* 回填条件跳出 */
        gsym_addr(b, c);            /* ★ continue 跳到步进表达式 c */
        --local_scope;
        sym_pop(&local_stack, s, 0); /* 清 for 里定义的变量 */
    }
```

`for` 比 `while` 多一个"步进表达式"，所以有两个位置 `d`（条件）和 `c`（步进）：

```
      ┌──────────────────────┐
      ▼                      │
   d: 条件判断 ──假──► a(跳出) │
      │真                    │
      │   e: jmp ──► body    │
      │            │         │
      │            ▼         │
      │   c: 步进表达式 ──────┘
      └──► body 结束后跳 c
```

**`continue` 目标是 `c`（步进表达式），不是 `d`**——这是 `for` 和 `while` 的区别。

---

## 第 5 站：`do-while`（`tccgen.c:6076`）

```c
/* src/core/tccgen.c:6076-6095（节选）*/
    if (tok == TOK_DO) {
        int saved_nocode_wanted;
        nocode_wanted &= ~0x20000000;
        next();
        a = 0; b = 0;
        d = ind;                    /* d = 循环体开头 */
        vla_sp_restore();
        saved_nocode_wanted = nocode_wanted;
        block(&a, &b, 0);           /* 循环体 */
        skip(TOK_WHILE);
        skip('(');
        gsym(b);                    /* ★ continue 跳到条件判断 */
        gexpr();                    /* 条件 */
        c = gvtst(0, 0);            /* ★ 条件真 → 跳回 d（继续循环）*/
        gsym_addr(c, d);
        nocode_wanted = saved_nocode_wanted;
        skip(')');
        gsym(a);                    /* break 跳出 */
        skip(';');
    }
```

`do-while` 先执行体，再判断：`gvtst(0,0)` = "条件真就继续"，
`gsym_addr(c, d)` 跳回开头。`break` 是 `a`，`continue` 是 `b`（跳到条件处）。

---

## 第 6 站：`gjmp_addr` 和 `gtst_addr`（已知地址的跳转）

有时目标地址已经知道（比如"跳回循环开头 `d`"），就不用链表，直接算相对位移：

```c
/* src/targets/x86_64-gen.c:1648-1659 */
void gjmp_addr(int a)
{
    int r;
    r = a - ind - 2;
    if (r == (char)r) {     /* 位移能用 1 字节（-128..127）？ */
        g(0xeb);            /* 短跳转 jmp rel8 */
        g(r);
    } else {
        oad(0xe9, a - ind - 5);  /* 长跳转 jmp rel32 */
    }
}
```

**TCC 会自动选短跳转或长跳转**，省 4 字节。

`gtst_addr`（`:1661`）是"条件跳转到已知地址"，同理。

---

## 【把 `if (x) y=1; else y=2;` 走一遍】

| 步骤 | 动作 | 生成的代码 |
|---|---|---|
| 1 | `gexpr()` 求 `x` | `mov eax,[x]` |
| 2 | `gvtst(1,0)` | `test eax,eax; je ???`（`a` 指向 `???`） |
| 3 | then 分支 | `mov dword [y],1` |
| 4 | `gjmp(0)` | `jmp ???`（`d`） |
| 5 | `gsym(a)` | 回填 `je` 到此处 |
| 6 | else 分支 | `mov dword [y],2` |
| 7 | `gsym(d)` | 回填 `jmp` 到此处 |
| 8 | 后续代码 | … |

---

## 【动手小实验】

1. 写 `if (a) b=1; else b=2;`，反汇编里找 `test`/`je`/`jmp` 和它们的相对位移。
2. 写 `while (i<10) i++;`，找循环回跳的短跳转（`eb xx`）。
3. 在 `gjmp`/`gsym` 里加 `printf("gjmp t=%d / gsym %d\n", ...)`，看链表怎么串和回填。
4. 写 `if (1) a=1; else a=2;`，看是否只剩一条分支（`condition_3way`）。

## 【通关暗号】

```bash
printf 'int main(void){int i=0,s=0; while(i<5){s+=i; i++;} return s;}\n' > /tmp/w.c
./tcc -run /tmp/w.c; echo $?
# 期望：10（0+1+2+3+4）
```

## 【常见卡点】

- **跳转链是一条串在指令位移字段里的链表**，`gjmp` 返回新链头，`gsym` 回填。
- **`gvtst(inv,t)` 把任意值变成条件跳转链**；`inv` 决定真假方向。
- **`while` 的 `continue` 回条件，`for` 的 `continue` 回步进表达式**。
- **`for` 用两个地址 `d`（条件）和 `c`（步进）**。
- **`gjmp_addr` 自动选短/长跳转**。

**下一篇**：`28-短路与VT_JMP.md`。
