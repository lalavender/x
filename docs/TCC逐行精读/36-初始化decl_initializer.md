# 36 · 初始化：`= {...}` 怎么落进数据

> **一句话**：初始化有两条路——全局变量直接往 `Section.data` 里写字节；
> 局部变量生成一串赋值代码。解析器（`decl_initializer`）按"数组/结构体/标量"
> 递归展开 `{}`，处理字符串、指定初始化（designator）和空隙补零。
>
> 对应源码：`src/core/tccgen.c:6635`（`decl_initializer`）、`:6441`（`init_putv` 写一个值）、
> `:6329`（`decl_designator` 处理 `[i]`/`.field`）、`:6305`（`init_putz` 补零）、
> `:6277`（`parse_init_elem` 读一个初始化元素）。

---

## 第 0 站：入口约定（`tccgen.c:6635`）

```c
/* src/core/tccgen.c:6630-6656（节选）*/
/* type=对象类型；sec=数据段（NULL 表示局部栈）；
   c=对象在段里的偏移；first=是否要读 '{'；size_only=只算大小不写值 */
static void decl_initializer(CType *type, Section *sec, unsigned long c,
                             int first, int size_only)
{
    int len, n, no_oblock, nb, i;
    ...
    /* 如果当前在 '}' 或 ','，说明上层已经读了一个元素 */
    have_elem = tok == '}' || tok == ',';
    if (!have_elem && tok != '{' &&
        tok != TOK_LSTR && tok != TOK_STR &&
        !size_only) {
        parse_init_elem(!sec ? EXPR_ANY : EXPR_CONST);   /* ★ 读一个初始化元素 */
        have_elem = 1;
    }

    if (have_elem &&
        !(type->t & VT_ARRAY) &&
        is_compatible_unqualified_types(type, &vtop->type)) {
        init_putv(type, sec, c);        /* ★ 标量：直接写一个值 */
    } else if (type->t & VT_ARRAY) {
        ... 数组 ...
    } else if ((type->t & VT_BTYPE) == VT_STRUCT) {
        ... 结构体 ...
    } else if (tok == '{') {
        ... 多余的括号 ...
    } else {
        ... 标量兜底 ...
    }
}
```

**核心分岔**：标量一个值、数组多个值、结构体按字段多个值。

`parse_init_elem`（`:6277`）区分常量/任意表达式：

```c
/* src/core/tccgen.c:6277-6301（节选）*/
static void parse_init_elem(int expr_type)
{
    switch(expr_type) {
    case EXPR_CONST:            /* 全局：必须是常量 */
        saved_global_expr = global_expr;
        global_expr = 1;        /* 复合字面量要全局分配 */
        expr_const1();
        global_expr = saved_global_expr;
        if (不是常量) tcc_error("initializer element is not constant");
        break;
    case EXPR_ANY:              /* 局部：任意表达式 */
        expr_eq();
        break;
    }
}
```

---

## 第 1 站：写一个值 —— `init_putv`（`tccgen.c:6441`）

```c
/* src/core/tccgen.c:6441-6488（节选）*/
static void init_putv(CType *type, Section *sec, unsigned long c)
{
    int bt;
    void *ptr;
    CType dtype;

    dtype = *type;
    dtype.t &= ~VT_CONSTANT;

    if (sec) {
        /* ★ 全局/静态数据：直接往 Section 里写 */
        int size, align;
        gen_assign_cast(&dtype);            /* 类型检查+转换 */
        bt = type->t & VT_BTYPE;
        if ((vtop->r & VT_SYM) && bt != VT_PTR && bt != VT_FUNC && ...)
            tcc_error("initializer element is not computable at load time");
        if (NODATA_WANTED) { vtop--; return; }

        size = type_size(type, &align);
        section_reserve(sec, c + size);     /* 确保段够大 */
        ptr = sec->data + c;                /* ★ 要写的地址 */

        if (是复合字面量的匿名符号) {
            /* memcpy + 搬运重定位 */
            ...
        } else {
            if (type->t & VT_BITFIELD) {
                /* 位域：逐位抠出来写入（读改写） */
                ...
            } else
            switch(bt) {
            case VT_BOOL:
                vtop->c.i = vtop->c.i != 0;
            case VT_BYTE:
                *(char *)ptr |= vtop->c.i;      /* ★ 直接写字节 */
                break;
            case VT_SHORT:
                *(short *)ptr |= vtop->c.i;
                break;
            case VT_FLOAT:
                *(float*)ptr = vtop->c.f;
                break;
            case VT_DOUBLE:
                *(double *)ptr = vtop->c.d;
                break;
            ...
            case VT_PTR:
                {
                    addr_t val = vtop->c.i;
                    if (vtop->r & VT_SYM)
                        greloca(sec, vtop->sym, c, R_DATA_PTR, val);  /* ★ 欠条 */
                    else
                        *(addr_t *)ptr |= val;
                    break;
                }
            default:
                ... 整数 ...
            }
        }
        vtop--;
    } else {
        /* ★ 局部数据：生成赋值代码 */
        vset(&dtype, VT_LOCAL|VT_LVAL, c);
        vswap();
        vstore();              /* 第 24 篇 */
        vpop();
    }
}
```

两条路非常清楚：

- **`sec != NULL`（全局）**：这是在"填数据段"，**编译期直接把值写进内存**，
  遇到符号地址就 `greloca` 记一条重定位欠条（第 53 篇）。
- **`sec == NULL`（局部）**：编译期没法预知值，生成 `vstore` 赋值代码。

注意有个有意思的写法：**`*(char *)ptr |= vtop->c.i;` 用的是 `|=` 而不是 `=`**。
因为 `Section` 分配时是清零的，`|=` 在"多字段/多元素写入同一块"时更安全。
（对单个标量，效果等同 `=`。）

---

## 第 2 站：指定初始化与空隙补零 —— `decl_designator`（`:6329`）

```c
/* src/core/tccgen.c:6329-6406（节选）*/
static int decl_designator(CType *type, Section *sec, unsigned long c,
                           Sym **cur_field, int size_only, int al)
{
    ...
    unsigned long corig = c;
    ...
    /* 处理 [i] 和 .field 链 */
    while (nb_elems == 1 && (tok == '[' || tok == '.')) {
        if (tok == '[') {
            next();
            index = index_last = expr_const();       /* [i] */
            if (tok == TOK_DOTS && gnu_ext) {         /* [i ... j] */
                next(); index_last = expr_const();
            }
            skip(']');
            s = type->ref;
            if (index < 0 || ... ) tcc_error("invalid index");
            if (cur_field) (*cur_field)->c = index_last;
            type = pointed_type(type);
            elem_size = type_size(type, &align);
            c += index * elem_size;                  /* ★ 定位到下标 */
            nb_elems = index_last - index + 1;
        } else {
            next();
            l = tok;
        struct_field:
            next();
            if ((type->t & VT_BTYPE) != VT_STRUCT) expect("struct/union type");
            f = find_field(type, l);                 /* ★ 找成员 */
            if (!f) expect("field");
            if (cur_field) *cur_field = f;
            type = &f->type;
            c += f->c;                               /* ★ 加成员偏移 */
        }
        cur_field = NULL;
    }
    if (!cur_field) {
        if (tok == '=') next();                      /* [i]= 或 .f= */
        else if (!gnu_ext) expect("=");
    } else {
        ... 顺序初始化：cur_field 是当前该填的字段/下标 ...
    }
    /* ★ 空隙补零 */
    if (!size_only && c - corig > al)
        init_putz(sec, corig + al, c - corig - al);
    decl_initializer(type, sec, c, 0, size_only);    /* 递归解析这个元素 */
    ...
    return al;
}
```

**指定初始化** `[3] = 5`、`.x = 6` 让初始化不按顺序，所以中间可能出现"没写的空隙"。
`init_putz(sec, corig+al, c-corig-al)` 把这些空隙**补零**。

`init_putz`（`:6305`）：

```c
/* src/core/tccgen.c:6304-6321（节选）*/
static void init_putz(Section *sec, unsigned long c, int size)
{
    if (sec) {
        /* 全局：段本来就清零了，什么都不用做 */
    } else {
        /* 局部：生成 memset(&obj+c, 0, size) 调用 */
        vpush_global_sym(&func_old_type, TOK_memset);
        vseti(VT_LOCAL, c);
        ...
        gfunc_call(3);
    }
}
```

**全局的洞天然是 0，不用补；局部要靠 `memset`。**

---

## 第 3 站：数组初始化（`:6665-6773`）

```c
/* src/core/tccgen.c:6665-6680（节选）*/
    } else if (type->t & VT_ARRAY) {
        s = type->ref;
        n = s->c;                        /* 元素个数 */
        t1 = pointed_type(type);         /* 元素类型 */
        size1 = type_size(t1, &align1);

        no_oblock = 1;
        if ((first && tok != TOK_LSTR && tok != TOK_STR) || tok == '{') {
            if (tok != '{') tcc_error("character array initializer must be a literal...");
            skip('{');
            no_oblock = 0;               /* 有括号 */
        }
```

### 3a. 字符串初始化（`:6683-6735`）

```c
        if ((tok == TOK_STR && (t1->t & VT_BTYPE) == VT_BYTE) || ...) {
            len = 0;
            while (tok == TOK_STR || tok == TOK_LSTR) {
                ...
                if (sec && tok == TOK_STR && size1 == 1) {
                    /* ★ 全局 char 数组：直接 memcpy 最快 */
                    memcpy(sec->data + c + len, tokc.str.data, nb);
                } else {
                    for(i=0;i<nb;i++) {
                        vpushi(ch);
                        init_putv(t1, sec, c + (len+i)*size1);   /* 逐字符写 */
                    }
                }
                len += nb;
                next();
            }
            if (n < 0 || len < n) {        /* 补结尾 '\0' */
                if (!size_only) { vpushi(0); init_putv(t1, sec, c + len*size1); }
                len++;
            }
            len *= size1;
        }
```

**`char s[] = "abc";` 是把字符串复制进数组**，并在末尾补 `\0`。全局直接用 `memcpy`。

### 3b. 普通数组（`:6736-6773`）

```c
          do_init_list:
            len = 0;
            while (tok != '}' || have_elem) {
                len = decl_designator(type, sec, c, &f, size_only, len);
                have_elem = 0;
                if (type->t & VT_ARRAY) {
                    ++indexsym.c;
                    if (no_oblock && len >= n*size1) break;
                } else {
                    ... 结构体用 f = f->next ...
                }
                if (tok == '}') break;
                skip(',');
            }
        }
        /* 末尾补零 */
        if (!size_only && len < n*size1)
            init_putz(sec, c + len, n*size1 - len);
        if (!no_oblock) skip('}');
        /* 大小未知的数组（int a[]={...}）：回填元素个数 */
        if (n < 0)
            s->c = size1 == 1 ? len : ((len + size1 - 1)/size1);
```

**`int a[] = {1,2,3};` 的 `[]` 大小是 `-1`，初始化完回填成 3。**

---

## 第 4 站：结构体初始化（`:6774`）

```c
/* src/core/tccgen.c:6774-6784 */
    } else if ((type->t & VT_BTYPE) == VT_STRUCT) {
        size1 = 1;
        no_oblock = 1;
        if (first || tok == '{') {
            skip('{');
            no_oblock = 0;
        }
        s = type->ref;
        f = s->next;        /* ★ 从第一个成员开始 */
        n = s->c;
        goto do_init_list;  /* 复用数组那套循环 */
    }
```

**结构体初始化和数组共用 `do_init_list` 循环**，只是"下一个元素"是 `f = f->next`
而不是"下标 +1"。**一个循环处理两种容器。**

---

## 【把 `int a[5] = {1, [3]=4};` 走一遍】

| 步骤 | 动作 | 结果 |
|---|---|---|
| 1 | `type=VT_ARRAY`，`n=5`，`size1=4` | |
| 2 | `skip('{')` | |
| 3 | `decl_designator`：`1` | 写 `a[0]=1`，`len=4` |
| 4 | `skip(',')` | |
| 5 | `decl_designator`：`[3]=4` | `c += 3*4`，补零 `a[1..2]`，写 `a[3]=4` |
| 6 | 循环结束，`len` 到 `a[3]` 末尾 | 补零 `a[4]` |
| 7 | `skip('}')` | |

---

## 【动手小实验】

1. 全局 `int a[5]={1};`，`objdump -s -j .data` 看是不是 `01 00 00 00` 后面全 0。
2. 局部同样的代码，反汇编看是不是有 `memset`。
3. `struct S s = {.b=2};` 看 `.a` 是否被补零。
4. `char s[]="hi";` 看 `sizeof(s)` 是 3。

## 【通关暗号】

```bash
printf 'int main(void){int a[5]={1,2,3}; return a[0]+a[1]+a[2];}\n' > /tmp/i.c
./tcc -run /tmp/i.c; echo $?
# 期望：6
```

## 【常见卡点】

- **全局初始化 = 直接写数据段**；局部 = 生成赋值代码。
- **符号地址的初始化记重定位**（`greloca`）。
- **指定初始化的空隙要补零**；全局天然是 0，局部用 `memset`。
- **`[]` 未知大小在初始化后回填**。
- **数组和结构体共用 `do_init_list`**。

**下一篇**：`37-变量分配与符号发布.md`。
