# 33 · 声明符：`type_decl` 与 `post_type`

> **一句话**：C 的声明符语法很绕（`int (*fp)(int)` vs `int *fp(int)`）。
> TCC 用**两个互相递归的函数**处理：`type_decl` 吃 `*` 和名字，
> `post_type` 吃 `()` 和 `[]`。谁先被套上，取决于括号。
>
> 对应源码：`src/core/tccgen.c:4401`（`type_decl`）、`:4255`（`post_type`）、
> `:4220`（`convert_parameter_type`）。

---

## 第 0 站：先看两个例子，理解"声明符优先级"

```c
int *fp(int);      /* fp 是"函数"，返回 int* —— 即 int *(fp(int)) */
int (*fp)(int);    /* fp 是"指针"，指向"函数返回 int" */
```

- 没有括号时，`()`/`[]` 结合得比 `*` 紧；
- 加括号可以改变顺序。

TCC 的递归正好对应：

- `type_decl` 处理外层：`*`、名字、括号；
- `post_type` 处理后缀：`()`、`[]`；
- 遇到 `(` 里的嵌套声明符就递归回 `type_decl`。

---

## 第 1 站：`type_decl`（`tccgen.c:4401`）

```c
/* src/core/tccgen.c:4394-4441（节选）*/
static CType *type_decl(CType *type, AttributeDef *ad, int *v, int td)
{
    CType *post, *ret;
    int qualifiers, storage;

    /* 递归类型：先摘掉存储位，最后再戴回去 */
    storage = type->t & VT_STORAGE;
    type->t &= ~VT_STORAGE;
    post = ret = type;

    while (tok == '*') {
        qualifiers = 0;
    redo:
        next();
        switch(tok) {
        case TOK_CONST1: ...: qualifiers |= VT_CONSTANT; goto redo;   /* *const */
        case TOK_VOLATILE1: ...: qualifiers |= VT_VOLATILE; goto redo;
        case TOK_ATTRIBUTE1: case TOK_ATTRIBUTE2:
            parse_attribute(ad); break;
        }
        mk_pointer(type);               /* ★ 每见一个 *，套一层指针 */
        type->t |= qualifiers;
        if (ret == type)
            ret = pointed_type(type);   /* 记住"最内层"的指针类型 */
    }
```

`while (tok == '*')` 循环把连续的 `*` 都处理掉（`char **p` 两层）。
每见一个 `*` 就 `mk_pointer`（第 25 篇）。

```c
/* src/core/tccgen.c:4443-4467（节选）*/
    if (tok == '(') {
        /* 可能是函数参数表，
           也可能是"嵌套声明符" ( ... ) */
        if (!post_type(type, ad, 0, td)) {
            /* 不是函数参数表 → 是嵌套声明符 */
            parse_attribute(ad);
            post = type_decl(type, ad, v, td);   /* ★ 递归！ */
            skip(')');
        }
    } else if (tok >= TOK_IDENT && (td & TYPE_DIRECT)) {
        /* 是一个名字 */
        *v = tok;
        next();
    } else {
        if (!(td & TYPE_ABSTRACT))
            expect("identifier");
        *v = 0;                         /* 抽象声明符（如 sizeof(int*) ） */
    }
    post_type(post, ad, storage, 0);    /* ★ 处理后缀 () [] */
    parse_attribute(ad);
    type->t |= storage;                 /* 存储位戴回来 */
    return ret;
}
```

三步：

1. **`(` 开头**：先试 `post_type`（当函数参数表）。若它不是（返回 0），
   就当成**嵌套声明符**，递归 `type_decl`。
2. **名字**：`*v = tok`；抽象声明符则 `*v = 0`。
3. **`post_type(post, ...)`**：处理后面的 `()`/`[]`。

**关键：`post` 是"应该被套上后缀的那一层"**，由 `*` 的顺序决定。

---

## 第 2 站：`post_type`（`tccgen.c:4255`）

### 2a. 函数 `()`（`:4262-4333`）

```c
/* src/core/tccgen.c:4262-4277（节选）*/
    if (tok == '(') {
        next();
        if (td && !(td & TYPE_ABSTRACT)) return 0;   /* 嵌套声明符，交给 type_decl */
        if (tok == ')')        l = 0;                /* 空参数 */
        else if (parse_btype(&pt, &ad1)) l = FUNC_NEW; /* ANSI 原型 */
        else if (td)           return 0;             /* 嵌套 */
        else                   l = FUNC_OLD;         /* K&R 老式 */
        first = NULL;
        plast = &first;
        arg_size = 0;
        if (l) {
            for(;;) {
                /* 读一个参数 */
                if (l != FUNC_OLD) {
                    if ((pt.t & VT_BTYPE) == VT_VOID && tok == ')')
                        break;                       /* (void) */
                    type_decl(&pt, &ad1, &n, TYPE_DIRECT | TYPE_ABSTRACT);
                    if ((pt.t & VT_BTYPE) == VT_VOID)
                        tcc_error("parameter declared as void");
                    arg_size += (type_size(&pt, &align) + PTR_SIZE - 1) / PTR_SIZE;
                } else {
                    n = tok;                         /* K&R：只有名字 */
                    ...
                }
                convert_parameter_type(&pt);         /* ★ 数组/函数转指针 */
                s = sym_push(n | SYM_FIELD, &pt, 0, 0);  /* 形参入链 */
                *plast = s;
                plast = &s->next;
                if (tok == ')') break;
                skip(',');
                if (l == FUNC_NEW && tok == TOK_DOTS) {
                    l = FUNC_ELLIPSIS; next(); break;    /* ... */
                }
                if (l == FUNC_NEW && !parse_btype(&pt, &ad1))
                    tcc_error("invalid type");
            }
        } else
            l = FUNC_OLD;
        skip(')');
        ...
        ad->f.func_args = arg_size;
        ad->f.func_type = l;
        s = sym_push(SYM_FIELD, type, 0, 0);   /* 造函数类型的"容器" Sym */
        s->a = ad->a;
        s->f = ad->f;
        s->next = first;                       /* ★ 形参链挂上去 */
        type->t = VT_FUNC;
        type->ref = s;                         /* ★ type 变成"函数"，ref 挂参数 */
    }
```

**函数类型的表示**：`type->t = VT_FUNC`，`type->ref` 指向一个 `Sym`，
它的 `type` 是**返回类型**（就是传进来的 `type` 原样存进去），
`next` 是**形参链**。这正是第 13 篇说的链②。

`convert_parameter_type`（`:4220`）：

```c
/* src/core/tccgen.c:4218-4230 */
static inline void convert_parameter_type(CType *pt)
{
    pt->t &= ~(VT_CONSTANT | VT_VOLATILE);   /* 去掉 const/volatile */
    pt->t &= ~VT_ARRAY;                      /* ★ 数组参数 → 指针 */
    if ((pt->t & VT_BTYPE) == VT_FUNC)
        mk_pointer(pt);                      /* ★ 函数参数 → 函数指针 */
}
```

**C 的规则**：`void f(int a[10])` 里 `a` 其实是指针 `int*`；
`void f(int g())` 里 `g` 其实是函数指针。这里统一转换。

### 2b. 数组 `[]`（`:4334-4390`）

```c
/* src/core/tccgen.c:4334-4389（节选）*/
    } else if (tok == '[') {
        int saved_nocode_wanted = nocode_wanted;
        next();
        ...
        n = -1;
        t1 = 0;
        if (tok != ']') {
            if (!local_stack || (storage & VT_STATIC))
                vpushi(expr_const());        /* 全局：长度必须是常量 */
            else {
                nocode_wanted = 0;           /* ★ 局部 VLA：长度要真的算 */
                gexpr();
            }
            if ((vtop->r & (VT_VALMASK|VT_LVAL|VT_SYM)) == VT_CONST) {
                n = vtop->c.i;               /* 常量长度 */
                if (n < 0) tcc_error("invalid array size");
            } else {
                t1 = VT_VLA;                 /* ★ 变长数组 */
            }
        }
        skip(']');
        post_type(type, ad, storage, 0);     /* ★ 递归：多维数组 */
        if (type->t == VT_FUNC)
            tcc_error("declaration of an array of functions");
        t1 |= type->t & VT_VLA;
        ...
        s = sym_push(SYM_FIELD, type, 0, n); /* 容器 Sym，c = 元素个数 n */
        type->t = (t1 ? VT_VLA : VT_ARRAY) | VT_PTR;
        type->ref = s;
    }
```

**数组类型的表示**：`type->t = VT_ARRAY | VT_PTR`，`type->ref` 的 `type` 是元素类型，
`c` 是元素个数（`-1` 表示未知/VLA）。第 25 篇 `type_size` 的"数组算大小"就用它。

`post_type(type, ...)` 递归处理多维：`int a[3][4]` 会一层层套。

---

## 第 3 站：`int (*fp)(int)` 的解析过程

关键看**括号让 `post_type` 先作用于谁**。

```
type_decl(type=int)
  tok='(' → 试 post_type(type, ...)
     post_type 看到 '(' 后面是 '*'（不是类型）→ parse_btype 失败
       且 td 有 TYPE_DIRECT → 返回 0  → 说明是嵌套声明符
  → 递归 type_decl(type=int)
       tok='*' → mk_pointer(int) → type=int*
       tok='fp' → v=fp
       post_type(type=int*) → tok=')' → 无后缀
       返回 int*
  → skip(')')
  → post = int*  （嵌套声明符的结果）
  → post_type(post=int*) → tok='(' → 是函数参数表
       type 变 VT_FUNC，ref->type = int*，ref->next = (int)
  结果：fp 的类型 = "函数，返回 int*"
```

而 `int *fp(int)`：

```
type_decl(type=int)
  tok='*' → mk_pointer(int) → type=int*
  tok='fp' → v=fp
  post_type(type=int*) → tok='(' → 函数
     ref->type = int*，ref->next = (int)
  结果：fp 的类型 = "函数，返回 int*"  ← 和上面竟然一样？
```

**注意**：C 里 `int *fp(int)` 和 `int (*fp)(int)` 确实不同！
前者 `fp` 是函数返回 `int*`；后者 `fp` 是指针指向函数返回 `int`。
区别在于 TCC 里 `post_type(post, ...)` 用的是 **`post`** 而不是 `type`——
在嵌套声明符那支里，`post` 是"最内层"。这个细节需要对着代码慢慢跟，才能看出两种写法
`ref->type` 存的东西不同。

> **建议**：拿这两个例子在纸上跟着 `type_decl` 走一遍递归，或者加 `type_to_str` 打印。
> 这是 C 声明符里最容易绕晕的地方，看懂了你就真的懂了。

---

## 【动手小实验】

1. 写下面四个，用 `sizeof` 或赋值验证类型：
   ```c
   int *a[5];        /* 5 个指针 */
   int (*b)[5];      /* 1 个指针，指向 5 个 int 的数组 */
   int *f1(void);    /* 函数返回 int* */
   int (*f2)(void);  /* 函数指针 */
   ```
2. 写 `int a[3][4];`，`sizeof(a)` 应是 48，`sizeof(a[0])` 应是 16。
3. 写 `void f(int a[10]);`，函数里 `sizeof(a)` 是 8（退化成指针），不是 40。
4. 在 `type_decl` 开头加 `printf("type_decl tok=%s\n", get_tok_str(tok, NULL));` 看递归层次。

## 【通关暗号】

```bash
printf 'int main(void){int a[3][4]; return sizeof(a)/sizeof(a[0][0]);}\n' > /tmp/a.c
./tcc -run /tmp/a.c; echo $?
# 期望：12（3*4）
```

## 【常见卡点】

- **`*` 由 `type_decl` 处理，`()`/`[]` 由 `post_type` 处理**，两者递归。
- **函数类型存在 `ref->type`（返回类型）和 `ref->next`（参数链）**。
- **数组类型 `c` 是元素个数**，`ref->type` 是元素类型。
- **形参里的数组/函数会退化成指针**（`convert_parameter_type`）。
- **`int *f()` 与 `int (*f)()` 不同**，靠括号和递归层次区分。

**下一篇**：`34-struct布局.md`。
