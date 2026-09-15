# 09 · 一串 token 怎么存：`int` 数组当录音带

> **本步输入**：一串 token（可能是宏本体、`#if` 表达式、实参）
> **本步输出**：一个 `int` 数组，能原样再读出来，还能直接当输入流用
>
> 对应源码：`src/core/tcc.h:575`（`TokenString` 结构）、
> `src/core/tccpp.c:1042-1200`（`tok_str_*` 一族）、
> `src/core/tccpp.c:1218`（`TOK_GET` 解码）、
> `src/core/tcc.h:943-960`（那些特殊 token 编号）。

---

## 第 0 站：为什么不存"结构体数组"？

宏本体、实参、`#if` 表达式都需要"暂存一串 token"。
最直觉的做法是：

```c
struct Token { int type; CValue value; };   /* 每个 token 一个结构体 */
```

但 TCC 不这么做。它用**一个 `int` 数组**，按 token 类型决定"占几个 int"。
为什么？

1. **拷贝快**：`memcpy` 一段连续内存，不用逐个构造结构体。
2. **能直接当输入流**：`macro_ptr` 就是个 `const int*`，
   读一个 token 就是指针往前走（第 07 篇）。
3. **省内存**：多数 token 只占 1 个 int。

这就像"录音带"：你不用知道每段录音内部结构，只要有个指针顺序读下去就行。

---

## 第 1 站：录音带的包装 —— `TokenString`（`tcc.h:575`）

```c
/* src/core/tcc.h:575-586 */
typedef struct TokenString {
    int *str;                    /* ★ 整数数组本体 */
    int len;                     /* 现在有多少个 int */
    int lastlen;                 /* 上一次 add 之前的位置（算空格用） */
    int allocated_len;           /* 分配了多少 int */
    int last_line_num;           /* 上次记录的行号（去重） */
    int save_line_num;
    /* 用 begin/end_macro 把多条录音带串起来 */
    struct TokenString *prev;    /* 上一条录音带 */
    const int *prev_ptr;
    char alloc;                  /* 1=自己释放 2=全局缓冲 3=已结束 */
} TokenString;
```

`str` 是本体，`len` 是"写到哪了"，`allocated_len` 是"分配了多大"。
`prev`/`prev_ptr` 是第 07 篇讲的"录音带链"。

---

## 第 2 站：编码格式 —— 一个 token 占几个 int

看 `tok_str_add2`（往录音带写）和 `TOK_GET`（从录音带读）。
先看**写入**：

```c
/* src/core/tccpp.c:1129-1200（节选）*/
static void tok_str_add2(TokenString *s, int t, CValue *cv)
{
    int len, *str;

    len = s->lastlen = s->len;
    str = s->str;

    /* 先按最坏情况（TOK_MAX_SIZE 个 int）确保够大 */
    if (len + TOK_MAX_SIZE >= s->allocated_len)
        str = tok_str_realloc(s, len + TOK_MAX_SIZE + 1);
    str[len++] = t;                    /* ★ 第 1 个 int：token 编号 */
    switch(t) {
    case TOK_CINT:
    case TOK_CUINT:
    case TOK_CCHAR:
    case TOK_LCHAR:
    case TOK_CFLOAT:
    case TOK_LINENUM:
        str[len++] = cv->tab[0];       /* 这些：1 个 int 负载 */
        break;
    case TOK_PPNUM:
    case TOK_PPSTR:
    case TOK_STR:
    case TOK_LSTR:
        {
            /* 字符串：1 个 int 存长度，然后是字节（按 int 对齐） */
            size_t nb_words = 1 + (cv->str.size + sizeof(int) - 1) / sizeof(int);
            if (len + nb_words >= s->allocated_len)
                str = tok_str_realloc(s, len + nb_words + 1);
            str[len] = cv->str.size;
            memcpy(&str[len + 1], cv->str.data, cv->str.size);
            len += nb_words;
        }
        break;
    case TOK_CDOUBLE:
    case TOK_CLLONG:
    case TOK_CULLONG:
        str[len++] = cv->tab[0];       /* 这些：2 个 int 负载（64 位） */
        str[len++] = cv->tab[1];
        break;
    ...
    case TOK_CLDOUBLE:                 /* long double：4 个 int（16 字节） */
        str[len++] = cv->tab[0];
        str[len++] = cv->tab[1];
        str[len++] = cv->tab[2];
        str[len++] = cv->tab[3];
        break;
    default:
        break;                         /* 其它：只占 1 个 int（就是 t） */
    }
    s->len = len;
}
```

编码规则总结：

| token 类型 | 占几个 int | 内容 |
|---|---|---|
| `TOK_CINT` 等整型常量 | 2 | `[编号, 值]` |
| `TOK_CDOUBLE` / `TOK_CLLONG` | 3 | `[编号, 低32, 高32]` |
| `TOK_CLDOUBLE` | 5 | `[编号, 4个32位]` |
| `TOK_STR` / `TOK_PPNUM` / `TOK_PPSTR` | `2 + 字节数/4` | `[编号, 长度, 字节...]` |
| 其它（符号、标识符、内部标记） | 1 | `[编号]` |

**`TOK_MAX_SIZE = 4`（`tcc.h:378`）就是"一个 token 最多额外占 4 个 int"，
用来预估分配。** 字符串可能更长，所以字符串那条分支里单独再算一次。

> 顺便看一个宝藏：`tccpp.c:1010` 有一段**被 `#if 0` 注释掉的 `tok_size` 函数**，
> 它用代码形式把上面的表格又写了一遍。想复习编码格式时看它最快：
> ```c
> /* src/core/tccpp.c:1010-1038 */
> static inline int tok_size(const int *p)
> {
>     switch(*p) {
>     case TOK_CINT: ... case TOK_LINENUM:
>         return 1 + 1;
>     case TOK_STR: ... case TOK_PPSTR:
>         return 1 + ((sizeof(CString) + ((CString *)(p+1))->size + 3) >> 2);
>     case TOK_CDOUBLE: ... case TOK_CLLONG:
>         return 1 + 2;
>     case TOK_CLDOUBLE:
>         return 1 + LDOUBLE_SIZE / 4;
>     default:
>         return 1 + 0;
>     }
> }
> ```

---

## 第 3 站：读回来 —— `TOK_GET`（`tccpp.c:1218`）

```c
/* src/core/tccpp.c:1216-1279（节选）*/
/* 从整数数组取一个 token，指针前进相应步数。写成内联函数避免别名问题 */
static inline void TOK_GET(int *t, const int **pp, CValue *cv)
{
    const int *p = *pp;
    int n, *tab;

    tab = cv->tab;
    switch(*t = *p++) {                 /* 第一个 int 是编号 */
    case TOK_CINT:
    case TOK_CCHAR:
    case TOK_LCHAR:
    case TOK_LINENUM:
        cv->i = *p++;                   /* 第二个 int 是值 */
        break;
    case TOK_CUINT:
        cv->i = (unsigned)*p++;
        break;
    case TOK_CFLOAT:
        tab[0] = *p++;
        break;
    case TOK_STR:
    case TOK_LSTR:
    case TOK_PPNUM:
    case TOK_PPSTR:
        cv->str.size = *p++;            /* 第二个 int：长度 */
        cv->str.data = p;               /* 数据紧跟其后 */
        p += (cv->str.size + sizeof(int) - 1) / sizeof(int);
        break;
    case TOK_CDOUBLE:
    case TOK_CLLONG:
    case TOK_CULLONG:
        n = 2;
        goto copy;
    case TOK_CLDOUBLE:
        ... n = 4 ...
    copy:
        do *tab++ = *p++;
        while (--n);
        break;
    default:
        break;
    }
    *pp = p;                            /* ★ 更新指针 */
}
```

`TOK_GET` 就是 `tok_str_add2` 的逆运算：**读编号 → 根据编号决定再读几个 int**。
所有"读录音带"的地方（`next_nomacro_spc`、`macro_subst`、`macro_arg_subst`……）
都用它。

**为什么写成函数而不是宏？** 注释说"避免指针别名问题"——
用函数，编译器知道 `p` 和 `cv` 不会互相干扰，能生成更好的代码。

---

## 第 4 站：往录音带加"当前 token" —— `tok_str_add_tok`（`tccpp.c:1203`）

`expr_preprocess`（第 08 篇）要把"当前 token"收进录音带，用的是它：

```c
/* src/core/tccpp.c:1202-1214 */
/* 把当前解析的 token 加进 token string 's' */
ST_FUNC void tok_str_add_tok(TokenString *s)
{
    CValue cval;

    /* 保存行号信息 */
    if (file->line_num != s->last_line_num) {
        s->last_line_num = file->line_num;
        cval.i = s->last_line_num;
        tok_str_add2(s, TOK_LINENUM, &cval);    /* ★ 插一个"行号标记" */
    }
    tok_str_add2(s, tok, &tokc);
}
```

它会在行号变化时插一个 `TOK_LINENUM` 标记。
`next_nomacro_spc`（`tccpp.c:2979`）读到 `TOK_LINENUM` 时会：
```c
if (tok == TOK_LINENUM) {
    file->line_num = tokc.i;   /* 恢复行号 */
    goto redo;                 /* 继续读下一个真 token */
}
```

**这是"录音带也能带行号"的做法**：宏展开跨好几行时，报错仍能指对行。

---

## 第 5 站：录音带的增删查改（`tccpp.c:1042-1104`）

```c
/* src/core/tccpp.c:1042-1048 */
ST_INLN void tok_str_new(TokenString *s)
{
    s->str = NULL;
    s->len = s->lastlen = 0;
    s->allocated_len = 0;
    s->last_line_num = -1;
}

/* src/core/tccpp.c:1050-1055 */
ST_FUNC TokenString *tok_str_alloc(void)
{
    TokenString *str = tal_realloc(tokstr_alloc, 0, sizeof *str);
    tok_str_new(str);
    return str;
}

/* src/core/tccpp.c:1057-1064 */
ST_FUNC int *tok_str_dup(TokenString *s)     /* 复制一份整数数组 */
{
    int *str = tal_realloc(tokstr_alloc, 0, s->len * sizeof(int));
    memcpy(str, s->str, s->len * sizeof(int));
    return str;
}

/* src/core/tccpp.c:1077-1092 */
ST_FUNC int *tok_str_realloc(TokenString *s, int new_size)
{
    int *str, size;
    size = s->allocated_len;
    if (size < 16) size = 16;
    while (size < new_size)
        size = size * 2;             /* 容量翻倍 */
    if (size > s->allocated_len) {
        str = tal_realloc(tokstr_alloc, s->str, size * sizeof(int));
        s->allocated_len = size;
        s->str = str;
    }
    return s->str;
}

/* src/core/tccpp.c:1094-1104 */
ST_FUNC void tok_str_add(TokenString *s, int t)   /* 只加一个 int，没有负载 */
{
    int len = s->len, *str = s->str;
    if (len >= s->allocated_len)
        str = tok_str_realloc(s, len + 1);
    str[len++] = t;
    s->len = len;
}
```

- `tok_str_new`：清空（`str=NULL, len=0`）。
- `tok_str_alloc`：分配一个 `TokenString` 壳子。
- `tok_str_dup`：把 `str` 数组整个复制。第 06 篇 `parse_define` 最后为什么要 `dup`？
  因为 `tokstr_buf` 是全局复用的，不复制会被下一个宏覆盖。
- `tok_str_realloc`：容量翻倍扩容。
- `tok_str_add`：加一个**没有负载**的 int（比如结束哨兵 `0`、`-1`、`TOK_PLCHLDR`）。

**所有录音带内存都从 `tokstr_alloc` 这个"小对象分配器"（`tccpp.c:56`）来**，
第 01 篇提过的 `TinyAlloc`。为什么要专用分配器？因为 `TokenString` 又多又小，
用通用 `malloc` 会碎。第 1 篇没细讲，这里补一句：
`tal_realloc`/`tal_free` 从一个 768KB 的大缓冲里切片，**批量分配、几乎零开销**。

---

## 第 6 站：那些"内部标记" token

录音带里除了真 token，还有几个特殊编号（`tcc.h:943-960`）：

| 编号 | 名字 | 作用 |
|---|---|---|
| `TOK_PPNUM` | 0xbe | 预处理数字（原始文本，第 04 篇解释） |
| `TOK_PPSTR` | 0xbf | 预处理字符串（原始文本，第 05 篇解释） |
| `TOK_LINENUM` | 0xc0 | 行号标记 |
| `TOK_TWOSHARPS` | 0xca | `##`（词法阶段） |
| `TOK_PLCHLDR` | 0xcb | 占位符（空实参用，C99 规定） |
| `TOK_NOSUBST` | 0xcc | "后面这个 token 别再展开" |
| `TOK_PPJOIN` | 0xcd | "这个 `##` 现在该拼了" |

它们在 `next()`（第 07 篇）里会被丢弃/特殊处理：
```c
if (tok == TOK_NOSUBST || tok == TOK_PLCHLDR)
    goto redo;   /* 不给编译器看见 */
```

**这些标记让预处理器能在录音带里"记事"**：占位、防递归、行号、拼接。
没有它们，宏展开会丢掉位置信息、空实参会粘连、递归无法终止。**小小的 int 大有用处。**

---

## 【把 `#define ADD(a,b) a+b` 的本体存一遍】

`#define ADD(a,b) a+b`：

1. `parse_define` 读到形参 `a`、`b`，各造一个 `Sym`（第 06 篇）。
2. 本体循环：
   - `a`（编号）→ `tok_str_add2`：本体变成 `[a编号]`；
   - `+`（ASCII 43）→ `[a编号, 43]`；
   - `b`（编号）→ `[a编号, 43, b编号]`；
3. 补 `0`：`[a编号, 43, b编号, 0]`。

展开 `ADD(1,2)` 时：
- `macro_arg_subst` 用 `TOK_GET` 逐个读出 `a编号`、`43`、`b编号`；
- 把 `a编号` 换成实参 `[1编号...]`，`b编号` 换成 `[2编号...]`；
- 结果录音带 `[1, 43, 2, 0]`；
- `begin_macro` 切过去，`next()` 读出来，交给 `parse_number` 变 `1`、`2`。

**全程没有字符串拼接，只有整数数组的拷贝和搬运。**

---

## 【动手小实验】

1. 打开 `tccpp.c:1007` 那段 `#if 0` 的 `tok_size`，把注释去掉、在某个 `tok_str_add2`
   后面打印 `tok_size(s->str)`，验证你算的占用和它一致。
2. 在 `TOK_GET` 的 `case TOK_STR` 里，想想为什么长度要 `(size + 3) / 4`。
   （答案：按 4 字节对齐，向上取整。）
3. 搜 `TOK_LINENUM`，看它在哪里被写入、在哪里被读出。

## 【通关暗号】

```bash
printf '#define K 8\nint main(void){return K;}\n' > /tmp/t.c
./tcc -E /tmp/t.c 2>/dev/null
# 期望：能正常展开——说明录音带的写(tok_str_add2)、读(TOK_GET)、
#      切换(begin_macro)整条链是通的。
```

## 【常见卡点】

- **为什么用 `int` 数组而不是结构体数组**：拷贝快、能当输入流、省内存。
- **一个 token 占几个 int**：由编号决定，`TOK_GET`/`tok_str_add2` 是互逆的。
- **结束哨兵是 `0`**：`while (*st >= 0)` / `if (t <= 0) break` 都靠它。
- **`tok_str_dup` 的必要性**：全局 `tokstr_buf` 会被复用。

---

## 【第一部小结】

到这里，第一部的九篇走完了。你现在应该能回答：

1. 字节怎么变成 `ch`（01）；
2. `ch` 怎么被 `next_nomacro1` 切成 token（02）；
3. 名字怎么编号、关键字编号从哪来（03）；
4. 数字、字符串怎么变值（04、05）；
5. `#define` 存成什么（06）；
6. `K` 怎么被替换、录音带怎么切换（07）；
7. `#if`/`#include` 怎么工作（08）；
8. 录音带（`int` 数组）怎么读写（09）。

**下一步**：第二部认识六件"零件"（`TokenSym`/`CType`/`SValue`/`Sym`/`Section`/`TCCState`），
然后第三部进入 `tccgen.c` 的心脏——`unary()` 和值栈。
