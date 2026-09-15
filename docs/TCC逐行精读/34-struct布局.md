# 34 · `struct/union/enum`：成员链与内存布局

> **一句话**：`struct` 的成员是一条 `Sym.next` 链；布局（每个成员在哪个偏移、
> 总大小、对齐）由 `struct_layout` 算好，存进链头 `Sym` 的 `c`（大小）和 `r`（对齐）。
>
> 对应源码：`src/core/tccgen.c:3763`（`struct_decl` 解析）、
> `:3489`（`struct_layout` 算布局）、`:3459`（`find_field` 找成员）、
> `:3477`（`struct_add_offset` 匿名成员偏移调整）。

---

## 第 0 站：`struct_decl` —— 解析声明（`tccgen.c:3763`）

```c
/* src/core/tccgen.c:3762-3800（节选）*/
/* u 是 VT_ENUM / VT_STRUCT / VT_UNION */
static void struct_decl(CType *type, int u)
{
    ...
    next();                       /* 吃掉 struct/union/enum */
    parse_attribute(&ad);
    if (tok != '{') {
        v = tok;                  /* 有名字 */
        next();
        if (v < TOK_IDENT) expect("struct/union/enum name");
        s = struct_find(v);       /* ★ 查"类型抽屉"（第 10 篇） */
        if (s && (s->sym_scope == local_scope || tok != '{')) {
            if (u == s->type.t) goto do_decl;      /* 已定义，直接用 */
            if (u == VT_ENUM && IS_ENUM(s->type.t)) goto do_decl;
            tcc_error("redefinition of '%s'", ...);
        }
    } else {
        v = anon_sym++;           /* 匿名结构体：给个匿名编号 */
    }
    type1.t = u == VT_ENUM ? u | VT_INT | VT_UNSIGNED : u;
    type1.ref = NULL;
    /* ★ 造"容器 Sym"：c = -1 表示大小未知；R 是类型抽屉里的那条链头 */
    s = sym_push(v | SYM_STRUCT, &type1, 0, -1);
    s->r = 0;
do_decl:
    type->t = s->type.t;
    type->ref = s;               /* ★ type 的 ref 指向这个容器 */
```

要点：

- **`struct_find`** 查 `sym_struct` 抽屉（第 10 篇），实现"同名结构体只定义一次"。
- **匿名结构体用 `anon_sym++`**（编号 >= `SYM_FIRST_ANOM`）。
- **容器 `Sym` 的 `next` 将是成员链头，`c` 是大小，`r` 是对齐。**

### 枚举 `enum`（`:3808-3865`）

```c
/* src/core/tccgen.c:3808-3851（节选）*/
        if (u == VT_ENUM) {
            long long ll = 0, pl = 0, nl = 0;
            CType t;
            t.ref = s;
            t.t = VT_INT|VT_STATIC|VT_ENUM_VAL;
            for(;;) {
                v = tok;
                ...
                ss = sym_find(v);
                if (ss && !local_stack)
                    tcc_error("redefinition of enumerator '%s'", ...);
                next();
                if (tok == '=') { next(); ll = expr_const64(); }  /* = 值 */
                ss = sym_push(v, &t, VT_CONST, 0);
                ss->enum_val = ll;      /* ★ 枚举常量值是直接存的 */
                *ps = ss, ps = &ss->next;
                ... 记录最大/最小值 ...
                if (tok != ',') break;
                next();
                ll++;                   /* 没写 = 就递增 */
                if (tok == '}') break;
            }
            skip('}');
            /* 根据值的范围决定枚举的底层整型 */
            t.t = VT_INT;
            if (nl >= 0) { ... unsigned ... }
            else if (pl != (int)pl || nl != (int)nl) t.t = VT_LLONG...;
            s->type.t = type->t = t.t | VT_ENUM;
            s->c = 0;
            ...
```

**枚举成员也进变量抽屉**（`sym_push`），但带 `VT_ENUM_VAL`，
值是 `enum_val`。第 19 篇 `unary` 读到枚举常量就取 `s->enum_val`。

### 结构体成员（`:3866-3968`）

```c
/* src/core/tccgen.c:3866-3970（节选）*/
        } else {
            c = 0; flexible = 0;
            while (tok != '}') {
                if (!parse_btype(&btype, &ad1)) { skip(';'); continue; }
                while (1) {
                    ...
                    type1 = btype;
                    if (tok != ':') {
                        if (tok != ';')
                            type_decl(&type1, &ad1, &v, TYPE_DIRECT);   /* 成员名 */
                        ...
                        if (type_size(&type1, &align) < 0) {
                            if ((u == VT_STRUCT) && (type1.t & VT_ARRAY) && c)
                                flexible = 1;              /* 柔性数组成员 */
                            else
                                tcc_error("field '%s' has incomplete type", ...);
                        }
                        ...
                    }
                    if (tok == ':') {                          /* 位域 */
                        next();
                        bit_size = expr_const();
                        if (bit_size < 0) tcc_error("negative width in bit-field");
                        ...
                        type1.t = (type1.t & ~VT_STRUCT_MASK)
                            | VT_BITFIELD
                            | (bit_size << (VT_STRUCT_SHIFT + 6));   /* ★ 宽度写进 type.t */
                    }
                    ...
                    if (v) {
                        ss = sym_push(v | SYM_FIELD, &type1, 0, 0);  /* ★ 成员入链 */
                        ss->a = ad1.a;
                        *ps = ss;
                        ps = &ss->next;
                    }
                    if (tok == ';' || tok == TOK_EOF) break;
                    skip(',');
                }
                skip(';');
            }
            skip('}');
            parse_attribute(&ad);
            struct_layout(type, &ad);       /* ★ 算布局 */
        }
```

**成员就是带 `SYM_FIELD` 的 `Sym`，串在容器 `Sym.next` 上。**
位域宽度存进 `type.t` 的高 6 位（`VT_STRUCT_SHIFT+6`）。

---

## 第 1 站：`struct_layout` —— 算偏移（`tccgen.c:3489`）

```c
/* src/core/tccgen.c:3489-3512（节选）*/
static void struct_layout(CType *type, AttributeDef *ad)
{
    int size, align, maxalign, offset, c, bit_pos, bit_size;
    int packed, a, bt, prevbt, prev_bit_size;
    int pcc = !tcc_state->ms_bitfields;    /* PCC(GCC) 还是 MS 位域规则 */
    int pragma_pack = *tcc_state->pack_stack_ptr;
    Sym *f;

    maxalign = 1;
    offset = 0;
    c = 0;                                 /* c = 当前大小游标 */
    bit_pos = 0;
    prevbt = VT_STRUCT;
    prev_bit_size = 0;

    for (f = type->ref->next; f; f = f->next) {   /* ★ 遍历成员链 */
        if (f->type.t & VT_BITFIELD)
            bit_size = BIT_SIZE(f->type.t);
        else
            bit_size = -1;
        size = type_size(&f->type, &align);       /* ★ 递归算成员大小/对齐 */
        a = f->a.aligned ? 1 << (f->a.aligned - 1) : 0;
        packed = 0;

        /* 处理 aligned / packed / pragma pack */
        if (pcc && bit_size == 0) {
            /* pcc 模式下零宽位域不受 packing 影响 */
        } else {
            if (pcc && (f->a.packed || ad->a.packed))
                align = packed = 1;
            if (pragma_pack) { packed = 1; if (pragma_pack < align) align = pragma_pack; ... }
        }
        if (a) align = a;
```

### 1a. union：所有成员偏移 0（`:3537`）

```c
        if (type->ref->type.t == VT_UNION) {
            if (pcc && bit_size >= 0) size = (bit_size + 7) >> 3;
            offset = 0;
            if (size > c) c = size;         /* 大小取最大成员 */
        } else if (bit_size < 0) {
```

### 1b. 普通成员：对齐 + 累加（`:3544`）

```c
        } else if (bit_size < 0) {
            if (pcc) c += (bit_pos + 7) >> 3;   /* 收尾前面的位域 */
            c = (c + align - 1) & -align;       /* ★ 对齐 */
            offset = c;                          /* 成员偏移 */
            if (size > 0) c += size;
            bit_pos = 0;
            prevbt = VT_STRUCT;
            prev_bit_size = 0;
        } else {
            /* 位域：PCC 或 MS 规则，很复杂（原文 ~60 行） */
            ...
        }
```

**核心就是 `c = (c + align - 1) & -align`**（第 14 篇那个对齐公式），
然后把成员偏移 `offset` 存进 `f->c`。

### 1c. 位域布局（`:3555-3622`）

位域有两套规则（`pcc` = GCC，否则 MS）：

- **PCC**：位域尽量紧挨前一个位域，除非零宽、显式对齐、或超出容器类型；
- **MS**：按底层类型分组，每组按类型对齐。

这段代码很绕，但目的很简单：**给每个位域算出 `bit_pos`（在存储单元里的位偏移）**，
写回 `type.t` 的高 6 位：

```c
            f->type.t = (f->type.t & ~(0x3f << VT_STRUCT_SHIFT))
                        | (bit_pos << VT_STRUCT_SHIFT);   /* 记录位偏移 */
            bit_pos += bit_size;
```

### 1d. 存结果（`:3638-3692`）

```c
        if (f->v & SYM_FIRST_ANOM && (f->type.t & VT_BTYPE) == VT_STRUCT) {
            /* 匿名结构体/联合体成员：调整其内部成员偏移 */
            struct_add_offset(f->type.ref, offset);
            f->c = 0;
        } else {
            f->c = offset;          /* ★ 成员偏移存这里 */
        }
        f->r = 0;
    }

    if (pcc) c += (bit_pos + 7) >> 3;   /* 收尾位域 */

    /* 存大小和对齐 */
    a = bt = ad->a.aligned ? 1 << (ad->a.aligned - 1) : 1;
    if (a < maxalign) a = maxalign;
    type->ref->r = a;                   /* ★ 对齐存链头 r */
    ...
    c = (c + a - 1) & -a;               /* 总大小按对齐向上取整 */
    type->ref->c = c;                   /* ★ 大小存链头 c */
```

**布局算完，结论就两条**：`type->ref->c` = 大小，`type->ref->r` = 对齐。
第 25 篇 `type_size` 对结构体就是直接取这两个值。

### 1e. 位域访问优化（`:3698-3759`）

后半段（约 60 行）在尝试"**能不能用某个整数类型直接访问这个位域**"
（存 `f->auxtype`），不行就 `VT_STRUCT` 表示"按字节逐字节处理"。
这是性能优化，不影响正确性。

---

## 第 2 站：找成员 —— `find_field`（`:3459`）

```c
/* src/core/tccgen.c:3459-3475 */
static Sym * find_field (CType *type, int v)
{
    Sym *s = type->ref;
    v |= SYM_FIELD;                 /* 补上字段标志 */
    while ((s = s->next) != NULL) {
        if ((s->v & SYM_FIELD) &&
            (s->type.t & VT_BTYPE) == VT_STRUCT &&
            (s->v & ~SYM_FIELD) >= SYM_FIRST_ANOM) {
            /* ★ 匿名结构体成员：递归往里找 */
            Sym *ret = find_field(&s->type, v);
            if (ret) return ret;
        }
        if (s->v == v) break;
    }
    return s;
}
```

第 19 篇的 `.`/`->` 就调它，拿到的 `Sym.c` 就是成员偏移。

---

## 【把 `struct {char a; int b; char c;} s;` 布局一遍】

成员顺序处理，假设 x86-64（int 对齐 4）：

| 成员 | size | align | 对齐后 `c` | offset | 之后 `c` |
|---|---|---|---|---|---|
| `a`(char) | 1 | 1 | 0 | **0** | 1 |
| `b`(int) | 4 | 4 | 4 | **4** | 8 |
| `c`(char) | 1 | 1 | 8 | **8** | 9 |

收尾：`maxalign = 4`，`c = 9` 按 4 向上取整 → **12**。

所以 `sizeof(struct)=12`，`offsetof(b)=4`，`offsetof(c)=8`。

---

## 【动手小实验】

1. `struct {char a; int b; char c;} s;` 用 `sizeof` 验证 12。
2. `struct __attribute__((packed)) {char a; int b; char c;}` 验证 6。
3. `union {int i; char c; double d;}` 验证 8。
4. `struct {unsigned a:3; unsigned b:5; unsigned c:8;} x;` 用 `sizeof` 验证（一般 4）。
5. `struct {int b; struct {int y;};} s; s.y=1;`（匿名成员）看能否访问。

## 【通关暗号】

```bash
printf 'struct S{char a; int b; char c;}; int main(void){return sizeof(struct S);}\n' > /tmp/s.c
./tcc -run /tmp/s.c; echo $?
# 期望：12
```

## 【常见卡点】

- **成员是 `Sym.next` 链**，容器 `Sym.c` 大小、`r` 对齐。
- **布局的核心公式是 `(c + align - 1) & -align`**。
- **位域位置存进 `type.t` 高 6 位**。
- **union 所有成员偏移 0**，大小取最大。
- **匿名成员要递归找、递归调整偏移**。

**下一篇**：`35-typedef与存储类.md`。
