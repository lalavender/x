# 10 · TokenSym：一个名字，四个抽屉

> **一句话**：C 里同一个名字（比如 `foo`）可以同时是宏、变量、类型、标签。
> TCC 给每个名字一个座位 `TokenSym`，座位上挂**四个抽屉**，各装各的。
>
> 对应源码：`src/core/tcc.h:381`（结构）、`src/core/tccgen.c:549`（`sym_push` 往抽屉放）、
> `src/core/tccgen.c:531/540`（`struct_find` / `sym_find` 从抽屉取）、
> `src/core/tccpp.c:1302/1324`（`define_push` / `define_find` 宏抽屉）、
> `src/core/tccpp.c:1357/1365/1384`（标签抽屉 `label_find/push/pop`）。

---

## 第 0 站：结构本体（`tcc.h:381`）

```c
/* src/core/tcc.h:380-390 */
typedef struct TokenSym {
    struct TokenSym *hash_next;   /* 哈希桶链（第 03 篇） */
    struct Sym *sym_define;       /* 抽屉①：#define 出来的宏 */
    struct Sym *sym_label;        /* 抽屉②：goto 标签 */
    struct Sym *sym_struct;       /* 抽屉③：struct/union/enum 的类型名 */
    struct Sym *sym_identifier;   /* 抽屉④：变量/函数/typedef 名 */
    int tok;                      /* 编号（第 03 篇） */
    int len;
    char str[1];                  /* 名字本体 */
} TokenSym;
```

第 03 篇说过：**一个名字在内存里只有一个 `TokenSym`**，
所有地方用一个小整数（编号）代表它。本篇讲那**四个抽屉**怎么用。

---

## 第 1 站：为什么要四个抽屉

看这段合法 C：

```c
#define foo 1              /* foo 是宏 */
int foo;                   /* foo 是变量 */
struct foo { int x; };     /* foo 是类型标签 */
foo:                       /* foo 是标签 */
```

四者互相独立：

- `foo` 出现在表达式里 → 先看是不是宏，再看是不是变量；
- `foo` 出现在 `struct foo` 后 → 看类型抽屉；
- `foo:` → 看标签抽屉。

**如果只有一个抽屉，`#define foo 1` 会把变量 `foo` 也一起吞掉。**
所以 TCC 把它们分开放。每个抽屉是一个 `Sym` 链的头指针（`NULL` 表示没有）。

---

## 第 2 站：往抽屉放东西 —— `sym_push`（`tccgen.c:549`）

变量/函数登记时走 `sym_push`：

```c
/* src/core/tccgen.c:548-578 */
ST_FUNC Sym *sym_push(int v, CType *type, int r, int c)
{
    Sym *s, **ps;
    TokenSym *ts;

    if (local_stack)
        ps = &local_stack;          /* 有局部作用域就压局部栈 */
    else
        ps = &global_stack;         /* 否则压全局栈 */
    s = sym_push2(ps, v, type->t, c);
    s->type.ref = type->ref;
    s->r = r;

    /* 不登记字段和匿名符号 */
    if (!(v & SYM_FIELD) && (v & ~SYM_STRUCT) < SYM_FIRST_ANOM) {
        ts = table_ident[(v & ~SYM_STRUCT) - TOK_IDENT];   /* 找到名字的座位 */
        if (v & SYM_STRUCT)
            ps = &ts->sym_struct;          /* ← 类型抽屉 */
        else
            ps = &ts->sym_identifier;      /* ← 变量抽屉 */
        s->prev_tok = *ps;                 /* 挂在抽屉链头 */
        *ps = s;
        s->sym_scope = local_scope;
        if (s->prev_tok && s->prev_tok->sym_scope == s->sym_scope)
            tcc_error("redeclaration of '%s'",
                get_tok_str(v & ~SYM_STRUCT, NULL));   /* 同一作用域重定义 */
    }
    return s;
}
```

三个要点：

1. **`v` 里编码了三件事**：
   - 低 28 位是名字编号；
   - `SYM_FIELD`（`tcc.h:523`）= `0x20000000`：这是结构体字段/函数参数，**不进抽屉**；
   - `SYM_STRUCT`（`0x40000000`）：这是类型名，进 `sym_struct` 抽屉。
   `v & ~SYM_STRUCT` 就是"把类型标志去掉，得到纯编号"。

2. **`prev_tok` 是"同名链"**：同一个名字的多个 `Sym`（不同作用域）串成一条链，
   新的挂在头部。这就是为什么 `int x; { int x; }` 里内层 `x` 能找到、外层不丢。

3. **`sym_scope == local_scope` 检查**：如果同一个作用域里又定义一个 `x`，
   那是重定义，报错。**作用域就是一个小整数 `local_scope`。**

---

## 第 3 站：从抽屉取 —— 三个 `find`

```c
/* src/core/tccgen.c:530-546 */
ST_INLN Sym *struct_find(int v)          /* 取类型抽屉 */
{
    v -= TOK_IDENT;
    if ((unsigned)v >= (unsigned)(tok_ident - TOK_IDENT))
        return NULL;
    return table_ident[v]->sym_struct;
}

ST_INLN Sym *sym_find(int v)             /* 取变量抽屉 */
{
    v -= TOK_IDENT;
    if ((unsigned)v >= (unsigned)(tok_ident - TOK_IDENT))
        return NULL;
    return table_ident[v]->sym_identifier;
}
```

```c
/* src/core/tccpp.c:1324-1329 */
ST_INLN Sym *define_find(int v)          /* 取宏抽屉 */
{
    v -= TOK_IDENT;
    if ((unsigned)v >= (unsigned)(tok_ident - TOK_IDENT))
        return NULL;
    return table_ident[v]->sym_define;
}
```

三个函数结构一模一样，只是取的抽屉不同。**全是"编号 → 下标 → 取指针"，O(1)。**

标签抽屉稍复杂（`label_push`，`tccpp.c:1365`），因为它还要区分全局/局部标签：

```c
/* src/core/tccpp.c:1365-1380 */
ST_FUNC Sym *label_push(Sym **ptop, int v, int flags)
{
    Sym *s, **ps;
    s = sym_push2(ptop, v, 0, 0);
    s->r = flags;
    ps = &table_ident[v - TOK_IDENT]->sym_label;
    if (ptop == &global_label_stack) {
        /* 全局标签：跳过所有局部同名标签，挂到最外层 */
        while (*ps != NULL)
            ps = &(*ps)->prev_tok;
    }
    s->prev_tok = *ps;
    *ps = s;
    return s;
}
```

`label_pop`（`:1384`）在函数结束时检查：标签定义了没用（警告 `declared but not used`）、
用了没定义（错误 `used but not defined`）。**抽屉链让这些检查很容易做。**

---

## 第 4 站：抽屉的"归还"—— `sym_pop`（`tccgen.c:600`）

出作用域时要"关上抽屉"：

```c
/* src/core/tccgen.c:600-626 */
ST_FUNC void sym_pop(Sym **ptop, Sym *b, int keep)
{
    Sym *s, *ss, **ps;
    TokenSym *ts;
    int v;

    s = *ptop;
    while(s != b) {                     /* 一路弹到标记 b 为止 */
        ss = s->prev;
        v = s->v;
        if (!(v & SYM_FIELD) && (v & ~SYM_STRUCT) < SYM_FIRST_ANOM) {
            ts = table_ident[(v & ~SYM_STRUCT) - TOK_IDENT];
            if (v & SYM_STRUCT)
                ps = &ts->sym_struct;
            else
                ps = &ts->sym_identifier;
            *ps = s->prev_tok;          /* ★ 抽屉链头回退一格 */
        }
        if (!keep)
            sym_free(s);
        s = ss;
    }
    if (!keep)
        *ptop = b;
}
```

**"作用域"在 TCC 里就是一对操作**：

```c
Sym *b = local_stack;    /* 进 { 时记住栈顶 */
... 编译块内代码 ...
sym_pop(&local_stack, b, 0);   /* 出 } 时弹回 b */
```

`sym_pop` 沿 `prev` 链往回走，每退一个就把对应抽屉的头指针退一格。
**一次遍历清干净，不用查表、不用扫描。**

---

## 【给 t.c 的每个名字点名】

```c
#define K 8
int add(int a, int b) { return a + b; }
int main(void) { int x = 3; ... }
```

| 名字 | TokenSym 哪个抽屉指向它 |
|---|---|
| `K` | `sym_define` → 一个 `MACRO_OBJ` 的 `Sym` |
| `add` | `sym_identifier` → 全局 `Sym`（`VT_FUNC`，`ref` 挂 `a/b`） |
| `main` | 同上 |
| `a`、`b` | 参数 `Sym`，且带 `SYM_FIELD`，**不进抽屉**（只在函数内部链上） |
| `x` | `sym_identifier` → 局部 `Sym`（`r=VT_LOCAL`，`c=栈偏移`） |

**关键区别**：`a/b` 是"字段类"符号（`SYM_FIELD`），不在 `table_ident` 的抽屉里，
只在函数局部栈上；函数返回后就 `sym_pop` 掉了。

---

## 【动手小实验】

1. 写 `#define x 1` 和 `int x;` 同时存在，编译看它不冲突——这就是四个抽屉的意义。
2. 搜 `prev_tok`，数数它在哪里被设置、在哪里被回退。
3. 在 `sym_push` 的 `redeclaration` 那行前打个断点（或加 `printf`），
   试 `int x; int x;` 和 `{int x; int x;}` 两个例子，看 `sym_scope` 起什么作用。

## 【通关暗号】

```bash
printf '#define foo 1\nint foo(int x){return x+foo;}\n' > /tmp/d.c
./tcc -run <(printf '#define foo 1\nint main(void){int foo=5; return foo+1;}\n') 2>/dev/null; echo $?
# 期望：6（宏 foo 和局部变量 foo 互不干扰）
```

## 【常见卡点】

- **四个抽屉各是什么**：宏、标签、类型、标识符。**不要混。**
- **`SYM_FIELD` / `SYM_STRUCT` 是 `v` 里的标志位**：靠它们决定进哪个抽屉、进不进。
- **`prev_tok` 是"同名链"**，`prev` 是"作用域栈链"，别搞混。

**下一篇**：`11-CType与类型编码.md` —— 一个 `int` 是怎么装下"C 的全部类型"的。
