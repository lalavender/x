# 29 · `switch` 与 `gcase`：先收集，再二分查找

> **一句话**：`switch` 不能边读边发比较（因为你不知道后面还有哪些 `case`）。
> TCC 先把所有 `case` 值收集成一张表，排好序，再用**二分查找**生成比较跳转。
>
> 对应源码：`src/core/tccgen.c:6097`（`switch`）、`:6134`（`case`）、`:6153`（`default`）、
> `:5809`（`case_cmp` 排序）、`:5816`（`gcase` 二分查找）、`:66`（`switch_t` 结构）。

---

## 第 0 站：数据结构（`tccgen.c:66`）

```c
/* src/core/tccgen.c:66-72 */
ST_DATA struct switch_t {
    struct case_t {
        int64_t v1, v2;   /* case 的值范围（普通 case: v1==v2） */
        int sym;          /* 该 case 代码的位置（.text 偏移） */
    } **p;                /* 动态数组 */
    int n;                /* 有几个 case */
    int def_sym;          /* default 的位置；0 = 没有 */
} *cur_switch;            /* 当前正在处理的 switch */
```

**每个 `case` 记一个范围 `[v1,v2]`**（GNU 的 `case 1 ... 5:` 用得上）和它的代码位置。

---

## 第 1 站：`switch` 主流程（`tccgen.c:6097`）

```c
/* src/core/tccgen.c:6097-6132（节选）*/
    if (tok == TOK_SWITCH) {
        struct switch_t *saved, sw;
        int saved_nocode_wanted = nocode_wanted;
        SValue switchval;
        next();
        skip('(');
        gexpr();                    /* 求 switch 的表达式 */
        skip(')');
        switchval = *vtop--;        /* ★ 值先存起来，后面用 */
        a = 0;
        b = gjmp(0);                /* ★ 先跳到末尾的"比较代码" */
        sw.p = NULL; sw.n = 0; sw.def_sym = 0;
        saved = cur_switch;
        cur_switch = &sw;           /* ★ 开始收集 case */
        block(&a, csym, 0);         /* 生成 switch 体（case 往里登记） */
        nocode_wanted = saved_nocode_wanted;
        a = gjmp(a);                /* ★ 体末尾补一条"跳出 switch"（隐式 break）*/

        /* 现在开始生成"比较代码" */
        gsym(b);                    /* 回填开头那条跳转到这里 */
        qsort(sw.p, sw.n, sizeof(void*), case_cmp);   /* ★ 按 v1 排序 */
        for (b = 1; b < sw.n; b++)
            if (sw.p[b - 1]->v2 >= sw.p[b]->v1)
                tcc_error("duplicate case value");     /* 重复 case */
        ...
        vpushv(&switchval);         /* 把 switch 值压回栈 */
        gcase(sw.p, sw.n, &a);      /* ★ 生成二分查找的比较跳转 */
        vpop();
        if (sw.def_sym)
            gjmp_addr(sw.def_sym);  /* 都不匹配 → default */
        dynarray_reset(&sw.p, &sw.n);
        cur_switch = saved;
        gsym(a);                    /* 回填跳出 switch 的链 */
    }
```

流程非常有特色：

1. **求 `switch` 表达式的值**，存到 `switchval`（先弹出值栈）；
2. **`b = gjmp(0)`**：生成"跳到后面的比较代码"——因为 `case` 代码要先排在前面；
3. **`block(&a, csym, 0)`**：生成 switch 体。每个 `case` 把自己登记进 `cur_switch`。
   同时 `a` 收集所有 `break`；
4. **`a = gjmp(a)`**：体末尾补一条"跳出"，作为隐式 break；
5. **`gsym(b)`**：让开头那条跳转落到这里——**比较代码**；
6. **`qsort` 按 `v1` 排序**，检查重复；
7. **`gcase`**：生成二分查找；
8. **`gjmp_addr(def_sym)`**：都不匹配跳 default；
9. **`gsym(a)`**：跳出 switch 的落点。

**关键**：`case` 代码在前，比较代码在后。执行时先 `jmp` 到后面的比较代码，
比较命中再跳回对应的 `case` 代码。

---

## 第 2 站：登记 `case` / `default`（`:6134`/`:6153`）

```c
/* src/core/tccgen.c:6133-6151（节选）*/
    if (tok == TOK_CASE) {
        struct case_t *cr = tcc_malloc(sizeof(struct case_t));
        if (!cur_switch) expect("switch");
        nocode_wanted &= ~0x20000000;      /* case 处代码可达 */
        next();
        cr->v1 = cr->v2 = expr_const64();  /* ★ case 值必须是常量 */
        if (gnu_ext && tok == TOK_DOTS) {  /* case 1 ... 5: */
            next();
            cr->v2 = expr_const64();
            if (cr->v2 < cr->v1) tcc_warning("empty case range");
        }
        cr->sym = ind;                     /* ★ 记录当前代码位置 */
        dynarray_add(&cur_switch->p, &cur_switch->n, cr);
        skip(':');
        is_expr = 0;
        goto block_after_label;            /* 像标签一样继续 */
    }
```

```c
/* src/core/tccgen.c:6152-6162（节选）*/
    if (tok == TOK_DEFAULT) {
        next();
        skip(':');
        if (!cur_switch) expect("switch");
        if (cur_switch->def_sym) tcc_error("too many 'default'");
        cur_switch->def_sym = ind;         /* 记住 default 位置 */
        is_expr = 0;
        goto block_after_label;
    }
```

**`case` 和 `default` 都只是"在当前位置贴个标签 + 登记"**——
和普通 `label:` 的处理很像（都 `goto block_after_label`）。

---

## 第 3 站：排序 —— `case_cmp`（`:5809`）

```c
/* src/core/tccgen.c:5809-5814 */
static int case_cmp(const void *pa, const void *pb)
{
    int64_t a = (*(struct case_t**) pa)->v1;
    int64_t b = (*(struct case_t**) pb)->v1;
    return a < b ? -1 : a > b;
}
```

标准 `qsort` 比较函数，按 `v1` 升序。**排好序才能二分查找。**

---

## 第 4 站：二分查找生成器 —— `gcase`（`:5816`）

```c
/* src/core/tccgen.c:5816-5874（逐段）*/
static void gcase(struct case_t **base, int len, int *bsym)
{
    struct case_t *p;
    int e;
    int ll = (vtop->type.t & VT_BTYPE) == VT_LLONG;   /* 64 位要特殊处理 */
    gv(RC_INT);                       /* switch 值装进寄存器 */

    while (len > 4) {
        /* ★ 二分查找：取中间那个 case */
        p = base[len/2];
        vdup();
        vpushll/vpushi(p->v2);
        gen_op(TOK_LE);               /* 值 <= p->v2 ? */
        e = gtst(1, 0);               /* 否 → 去右边 */
        vdup();
        vpushll/vpushi(p->v1);
        gen_op(TOK_GE);               /* 值 >= p->v1 ? */
        gtst_addr(0, p->sym);         /* ★ 是 → 跳到这个 case 的代码 */
        /* 值 < v1：查左半边 */
        gcase(base, len/2, bsym);
        if (cur_switch->def_sym)
            gjmp_addr(cur_switch->def_sym);
        else
            *bsym = gjmp(*bsym);
        /* 值 > v2：查右半边 */
        gsym(e);
        e = len/2 + 1;
        base += e; len -= e;
    }
    /* 剩 4 个以内：线性比较 */
    while (len--) {
        p = *base++;
        vdup();
        vpushll/vpushi(p->v2);
        if (p->v1 == p->v2) {
            gen_op(TOK_EQ);
            gtst_addr(0, p->sym);     /* 相等就跳过去 */
        } else {
            gen_op(TOK_LE);
            e = gtst(1, 0);
            vdup();
            vpushll/vpushi(p->v1);
            gen_op(TOK_GE);
            gtst_addr(0, p->sym);
            gsym(e);
        }
    }
}
```

分两段：

- **`len > 4` 时二分**：比较中间 case 的上界/下界，把搜索范围砍一半，
  递归处理左右半边。**每次 `vdup()` 复制 switch 值，因为要多比较几次。**
- **`len <= 4` 时线性**：少量 case 直接一个个比更快（省去递归开销）。

**为什么阈值是 4？** 经验值——对少量 case，二分的额外比较和跳转不划算。
这是编译器里常见的"小规模退化"优化。

> **对比**：很多编译器会生成**跳转表**（`jmp table`）实现 O(1) switch。
> TCC 只做二分，**不生成跳转表**——省事，但 case 极多时会慢一点。
> 对 TCC 的目标（快速编译）来说，够用。

---

## 【把 `switch(x){case 1:...;case 2:...;default:...}` 走一遍】

| 步骤 | 动作 | 结果 |
|---|---|---|
| 1 | `gexpr` 求 `x` | `mov eax,[x]`，存 `switchval` |
| 2 | `gjmp(0)` → `b` | `jmp L_cmp` |
| 3 | `block()` 生成体 | `case 1` 处记 `sym1`，`case 2` 记 `sym2`，default 记 `def` |
| 4 | `gjmp(a)` | 体末尾 `jmp L_end` |
| 5 | `gsym(b)` | `L_cmp:` |
| 6 | `qsort` | 排序（1,2） |
| 7 | `gcase` | `cmp eax,1; je sym1`；`cmp eax,2; je sym2` |
| 8 | `gjmp_addr(def)` | 都不中 → default |
| 9 | `gsym(a)` | `L_end:` |

---

## 【动手小实验】

1. 写 5 个 case 的 switch，反汇编看有几组 `cmp`/`je`。
2. 写 10 个 case 的 switch，看比较次数是不是变少（二分生效）。
3. 写 `case 1 ... 5:`（GNU 范围），看是否为范围生成两次比较。
4. 在 `gcase` 里加 `printf("gcase len=%d\n", len);`，看递归怎么切分。

## 【通关暗号】

```bash
printf 'int main(void){int x=3,r=0; switch(x){case 1:r=10;break;case 3:r=30;break;default:r=99;} return r;}\n' > /tmp/s.c
./tcc -run /tmp/s.c; echo $?
# 期望：30
```

## 【常见卡点】

- **`case` 代码排在前、比较代码排在后**，靠 `gjmp`/`gsym` 连接。
- **`case` 值必须是编译期常量**（`expr_const64`）。
- **排序后二分查找**，`len<=4` 退化成线性。
- **TCC 不生成跳转表**，只有比较跳转。
- **隐式 break**：体末尾自动补一条跳出。

**下一篇**：`30-goto标签与break-continue.md`。
