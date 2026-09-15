# 32 · 基本类型：`parse_btype`

> **一句话**：`int`、`unsigned long long`、`struct S`、`const char`、
> `typedef` 名——这堆"类型词"由一个函数 `parse_btype` 吃掉，
> 拼成一个 `CType`，并顺便把存储类（`static`/`extern`…）记进 flags。
>
> 对应源码：`src/core/tccgen.c:4001`（`parse_btype`）、`:3989`（`parse_btype_qualify`）、
> `:3763`（`struct_decl`，第 34 篇）。

---

## 第 0 站：函数契约（`tccgen.c:4001`）

```c
/* src/core/tccgen.c:3998-4014 */
/* 如果当前不是类型声明，返回 0；否则拼出基本类型并返回 1 */
static int parse_btype(CType *type, AttributeDef *ad)
{
    int t, u, bt, st, type_found, typespec_found, g;
    Sym *s;
    CType type1;

    memset(ad, 0, sizeof(AttributeDef));
    type_found = 0;
    typespec_found = 0;
    t = VT_INT;            /* ★ 默认类型：int（C 的老规矩：不写就 int） */
    bt = st = -1;          /* 记录是否见过基本类型 / short/long */
    type->ref = NULL;

    while(1) {
        switch(tok) {
        ...
```

`t` 是**正在拼的 `CType.t`**，默认 `VT_INT`。`typespec_found` 表示"见过类型词了"。

---

## 第 1 站：基本类型词（`tccgen.c:4021-4093`）

```c
/* src/core/tccgen.c:4021-4039（节选）*/
        case TOK_CHAR:
            u = VT_BYTE;
        basic_type:
            next();
        basic_type1:
            if (u == VT_SHORT || u == VT_LONG) {
                if (st != -1 || (bt != -1 && bt != VT_INT))
                    tmbt: tcc_error("too many basic types");
                st = u;                     /* short/long 是修饰 */
            } else {
                if (bt != -1 || (st != -1 && u != VT_INT))
                    goto tmbt;
                bt = u;                     /* 真正的基本类型 */
            }
            if (u != VT_INT)
                t = (t & ~(VT_BTYPE|VT_LONG)) | u;
            typespec_found = 1;
            break;
        case TOK_VOID:  u = VT_VOID;    goto basic_type;
        case TOK_SHORT: u = VT_SHORT;   goto basic_type;
        case TOK_INT:   u = VT_INT;     goto basic_type;
        case TOK_LONG:
            if ((t & VT_BTYPE) == VT_DOUBLE) {
                t = (t & ~(VT_BTYPE|VT_LONG)) | VT_LDOUBLE;   /* long double */
            } else if ((t & (VT_BTYPE|VT_LONG)) == VT_LONG) {
                t = (t & ~(VT_BTYPE|VT_LONG)) | VT_LLONG;     /* long long */
            } else {
                u = VT_LONG; goto basic_type;                  /* long */
            }
            next(); break;
```

关键点：

- **区分"基本类型"和"长度修饰"**：`char`/`void`/`int`/`float`…是基本类型（`bt`），
  `short`/`long` 是修饰（`st`）。所以 `int long` 合法但 `int char` 非法。
- **`long long` 靠第二次看到 `long`** 识别：第一次 `t` 里是 `VT_LONG`，
  第二次发现已是 `VT_LONG` 就升级成 `VT_LLONG`。
- **`long double`**：`long` 看到 `VT_DOUBLE` 就变 `VT_LDOUBLE`。
- `tmbt` 标签报错"too many basic types"（比如 `int char`）。

结构体/联合体/枚举走 `struct_decl`（第 34 篇）：

```c
/* src/core/tccgen.c:4082-4093 */
        case TOK_ENUM:
            struct_decl(&type1, VT_ENUM);
        basic_type2:
            u = type1.t;
            type->ref = type1.ref;      /* ref 挂成员链 */
            goto basic_type1;
        case TOK_STRUCT:
            struct_decl(&type1, VT_STRUCT);
            goto basic_type2;
        case TOK_UNION:
            struct_decl(&type1, VT_UNION);
            goto basic_type2;
```

---

## 第 2 站：修饰符（`tccgen.c:4096-4134`）

```c
/* src/core/tccgen.c:4096-4134（节选）*/
        case TOK_CONST1: ... TOK_CONST3:
            type->t = t;
            parse_btype_qualify(type, VT_CONSTANT);   /* ★ 处理数组内层 */
            t = type->t;
            next(); break;
        case TOK_VOLATILE1: ...:
            ... parse_btype_qualify(type, VT_VOLATILE); ...
        case TOK_SIGNED1: ...:
            if ((t & (VT_DEFSIGN|VT_UNSIGNED)) == (VT_DEFSIGN|VT_UNSIGNED))
                tcc_error("signed and unsigned modifier");
            t |= VT_DEFSIGN;
            ...
        case TOK_UNSIGNED:
            if ((t & (VT_DEFSIGN|VT_UNSIGNED)) == VT_DEFSIGN)
                tcc_error("signed and unsigned modifier");
            t |= VT_DEFSIGN | VT_UNSIGNED;
            ...
        case TOK_REGISTER: case TOK_AUTO: case TOK_RESTRICT1..3:
            next();    /* 直接忽略 */
            break;
```

`parse_btype_qualify` 有个细节：

```c
/* src/core/tccgen.c:3987-3996 */
static void parse_btype_qualify(CType *type, int qualifiers)
{
    while (type->t & VT_ARRAY) {
        /* const 数组 → const 元素（要复制一层，别改到 typedef 的共享 ref） */
        type->ref = sym_push(SYM_FIELD, &type->ref->type, 0, type->ref->c);
        type = &type->ref->type;
    }
    type->t |= qualifiers;
}
```

`const int a[3]` 的 `const` 应加在**元素**上，所以要沿数组往里钻。
**复制 `ref` 是为了不污染 typedef 共享的类型**（第 33 篇会看到同样手法）。

---

## 第 3 站：存储类（`tccgen.c:4136-4157`）

```c
/* src/core/tccgen.c:4136-4157 */
        case TOK_EXTERN:  g = VT_EXTERN;  goto storage;
        case TOK_STATIC:  g = VT_STATIC;  goto storage;
        case TOK_TYPEDEF: g = VT_TYPEDEF; goto storage;
       storage:
            if (t & (VT_EXTERN|VT_STATIC|VT_TYPEDEF) & ~g)
                tcc_error("multiple storage classes");   /* 不能同时 static extern */
            t |= g;
            next();
            break;
        case TOK_INLINE1: case TOK_INLINE2: case TOK_INLINE3:
            t |= VT_INLINE;   /* inline 不是存储类，单独一位 */
            next();
            break;
```

存储类存在 `t` 的高位（`VT_EXTERN/STATIC/TYPEDEF/INLINE`，`tcc.h:879-882`），
后面 `type_decl`/`decl0` 会用到。

---

## 第 4 站：typedef 名字（`tccgen.c:4179-4197`）

```c
/* src/core/tccgen.c:4179-4197（节选）*/
        default:
            if (typespec_found)
                goto the_end;         /* 已经见过类型，这个 token 不是类型词了 */
            s = sym_find(tok);        /* ★ 查变量/typedef 抽屉 */
            if (!s || !(s->type.t & VT_TYPEDEF))
                goto the_end;         /* 不是 typedef：结束 */
            t &= ~(VT_BTYPE|VT_LONG);
            u = t & ~(VT_CONSTANT | VT_VOLATILE), t ^= u;
            type->t = (s->type.t & ~VT_TYPEDEF) | u;
            type->ref = s->type.ref;
            if (t)
                parse_btype_qualify(type, t);   /* 保留 const/volatile */
            t = type->t;
            sym_to_attr(ad, s);       /* 继承 typedef 的 alignment 等属性 */
            next();
            typespec_found = 1;
            st = bt = -2;
            break;
```

**typedef 就是一个 `VT_TYPEDEF` 标志的变量**。这里查到它、把它的类型复制出来、
去掉 `VT_TYPEDEF` 标志，就成了一个普通类型。**typedef 不需要单独的符号空间。**

---

## 第 5 站：收尾（`tccgen.c:4201-4216`）

```c
/* src/core/tccgen.c:4201-4216 */
the_end:
    if (tcc_state->char_is_unsigned) {
        if ((t & (VT_DEFSIGN|VT_BTYPE)) == VT_BYTE)
            t |= VT_UNSIGNED;         /* -funsigned-char */
    }
    /* VT_LONG 只是 int/llong 的修饰 */
    bt = t & (VT_BTYPE|VT_LONG);
    if (bt == VT_LONG)
        t |= LONG_SIZE == 8 ? VT_LLONG : VT_INT;   /* 裸 long */
#ifdef TCC_TARGET_PE
    if (bt == VT_LDOUBLE)
        t = (t & ~(VT_BTYPE|VT_LONG)) | VT_DOUBLE; /* Windows 无 long double */
#endif
    type->t = t;
    return type_found;
}
```

**裸 `long`**（只有 `VT_LONG` 没有 `VT_INT/LLONG`）按平台补成 `long` 的真实类型。
这就是为什么 `long` 在 64 位 Linux 是 8 字节、在 Windows 是 4 字节。

---

## 【把 `unsigned long long *p` 的 `unsigned long long` 走一遍】

| token | 动作 | `t` |
|---|---|---|
| 初始 | — | `VT_INT (3)` |
| `unsigned` | `t \|= VT_DEFSIGN\|VT_UNSIGNED` | `VT_INT\|0x30` |
| `long` | `st=VT_LONG`，`t=t&~BTYPE\|VT_LONG` | `…\|VT_LONG` |
| `long` | 发现已经是 `VT_LONG` → `VT_LLONG` | `VT_LLONG\|UNSIGNED` |
| `*` | 不再走 `parse_btype`，交给 `type_decl` | |

---

## 【动手小实验】

1. 写 `long x;` 用 `sizeof` 验证（mac/Linux 是 8）。
2. 写 `typedef unsigned int uint; uint x;` 看能否通过。
3. 故意写 `int char x;` 看报错。
4. 写 `const int a[3];`，确认 `const` 加在元素上（`a[0]=1` 报错）。

## 【通关暗号】

```bash
printf 'int main(void){return sizeof(unsigned long long);}\n' > /tmp/t.c
./tcc -run /tmp/t.c; echo $?
# 期望：8
```

## 【常见卡点】

- **默认类型是 `int`**（不写类型时）。
- **`short`/`long` 是修饰，可能叠加**（`long long`）；基本类型会冲突。
- **typedef 名字就是一种变量**，查抽屉即可。
- **裸 `long` 在收尾时按平台补类型**。
- **`const` 加在数组元素上**，且要复制 `ref` 避免污染共享类型。

**下一篇**：`33-声明符type_decl与post_type.md`。
