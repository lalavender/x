# 39 · `inline` 与延迟编译：先存 token，用到再编

> **一句话**：`static inline` 函数在头文件里可能被包含几百次，
> 如果每次都生成代码，可执行文件会爆。TCC 把它的函数体**存成 token 串**，
> 只有某个 `.c` 真正调用了它，才在文件末尾补编译。
>
> 对应源码：`src/core/tccgen.c:7264`（记录 inline 函数）、`:7096`（`gen_inline_functions`）、
> `:7130`（`free_inline_functions`）、`:6241`（`skip_or_save_block`）、
> `src/core/tcc.h:589`（`InlineFunc`）。

---

## 第 0 站：数据结构（`tcc.h:589`）

```c
/* src/core/tcc.h:588-593 */
typedef struct InlineFunc {
    TokenString *func_str;   /* ★ 函数体存成 token 串 */
    Sym *sym;                /* 函数符号；NULL 表示已经编译过 */
    char filename[1];        /* 定义所在的文件（报错用） */
} InlineFunc;
```

`TCCState` 里有个数组存它们（`tcc.h:766`）：

```c
    struct InlineFunc **inline_fns;
    int nb_inline_fns;
```

---

## 第 1 站：记录而不编译（`tccgen.c:7264`）

```c
/* src/core/tccgen.c:7264-7285（节选）*/
                /* static inline 函数先记录成"宏"，用到才编 */
                if ((type.t & (VT_INLINE | VT_STATIC)) ==
                    (VT_INLINE | VT_STATIC)) {
                    struct InlineFunc *fn;
                    const char *filename;

                    filename = file ? file->filename : "";
                    fn = tcc_malloc(sizeof *fn + strlen(filename));
                    strcpy(fn->filename, filename);
                    fn->sym = sym;
                    skip_or_save_block(&fn->func_str);   /* ★ 只存 token */
                    dynarray_add(&tcc_state->inline_fns,
                                 &tcc_state->nb_inline_fns, fn);
                } else {
                    /* 普通函数：立刻生成 */
                    cur_text_section = ad.section ? ad.section : text_section;
                    gen_function(sym);
                }
```

**判断条件是 `(VT_INLINE | VT_STATIC)` 都置位**——只有 `static inline` 才延迟，
普通 `inline`（无 `static`）还是立刻编（因为别的 `.o` 可能需要它）。

---

## 第 2 站：存 token —— `skip_or_save_block`（`tccgen.c:6241`）

```c
/* src/core/tccgen.c:6236-6272 */
/* 跳过一段 token（括号/花括号配平），可顺便存进 *str */
static void skip_or_save_block(TokenString **str)
{
    int braces = tok == '{';    /* 是不是从 '{' 开始 */
    int level = 0;
    if (str)
      *str = tok_str_alloc();

    while ((level > 0 || (tok != '}' && tok != ',' && tok != ';' && tok != ')'))) {
        int t;
        if (tok == TOK_EOF) {
            if (str || level > 0) tcc_error("unexpected end of file");
            else break;
        }
        if (str)
          tok_str_add_tok(*str);   /* ★ 存一个 token（第 09 篇） */
        t = tok;
        next();
        if (t == '{' || t == '(') level++;      /* 进入一层 */
        else if (t == '}' || t == ')') {
            level--;
            if (level == 0 && braces && t == '}') break;   /* 配平结束 */
        }
    }
    if (str) {
        tok_str_add(*str, -1);   /* 结束哨兵 */
        tok_str_add(*str, 0);
    }
}
```

它**不真的编译函数体，只是把 token 一个个记进录音带**。
`begin_macro`/`end_macro`（第 07 篇）之后可以让编译器"回放"这段。

> `skip_or_save_block` 有两个用途：
> ① 存 `static inline` 函数体；
> ② 处理 `int a[]={...}` 的"先算大小"（第 37 篇）。
> `str == NULL` 时就是纯跳过。

---

## 第 3 站：文件末尾补编译 —— `gen_inline_functions`（`tccgen.c:7096`）

```c
/* src/core/tccgen.c:7096-7128 */
static void gen_inline_functions(TCCState *s)
{
    Sym *sym;
    int inline_generated, i, ln;
    struct InlineFunc *fn;

    ln = file->line_num;
    /* 反复扫描，因为补编译一个 inline 可能引用另一个 inline */
    do {
        inline_generated = 0;
        for (i = 0; i < s->nb_inline_fns; ++i) {
            fn = s->inline_fns[i];
            sym = fn->sym;
            if (sym && sym->c) {         /* ★ sym->c 非 0 表示"被引用过" */
                fn->sym = NULL;          /* 标记已处理，防止重复 */
                if (file)
                    pstrcpy(file->filename, sizeof file->filename, fn->filename);
                sym->type.t &= ~VT_INLINE;   /* 代码变普通函数 */

                begin_macro(fn->func_str, 1);   /* ★ 切到存好的 token 串 */
                next();
                cur_text_section = text_section;
                gen_function(sym);               /* ★ 现在真正生成 */
                end_macro();

                inline_generated = 1;
            }
        }
    } while (inline_generated);   /* 有新生成的再扫一遍 */
    file->line_num = ln;
}
```

关键：

- **`sym->c` 非 0**：符号被"发布"过（`put_extern_sym`）。
  什么时候发布？当代码里**调用**这个 inline 函数时，`unary` 的函数调用分支
  会 `external_global_sym`，于是 `sym->c` 被赋值。**这就是"被引用"的判据。**
- **`begin_macro(fn->func_str)`**：把存好的 token 串当输入，`next()` 开始读，
  然后 `gen_function`。**复用第 07 篇的录音带机制。**
- **`do...while(inline_generated)`**：inline A 调用 inline B 时，
  第一遍可能 B 还没被引用；补编 A 后 B 被引用，要再扫一遍。
- **`sym->type.t &= ~VT_INLINE`**：生成后它就是普通函数。

---

## 第 4 站：清理未用的 —— `free_inline_functions`（`tccgen.c:7130`）

```c
/* src/core/tccgen.c:7130-7140 */
ST_FUNC void free_inline_functions(TCCState *s)
{
    int i;
    /* 释放没被用过的 inline 函数 token */
    for (i = 0; i < s->nb_inline_fns; ++i) {
        struct InlineFunc *fn = s->inline_fns[i];
        if (fn->sym)                 /* sym 非 NULL = 没被编译 */
            tok_str_free(fn->func_str);
    }
    dynarray_reset(&s->inline_fns, &s->nb_inline_fns);
}
```

`tcc_compile`（第 01 篇）在文件编完后调它。

---

## 第 5 站：为什么值得这么做

考虑一个典型头文件：

```c
/* mylib.h */
static inline int max(int a, int b) { return a > b ? a : b; }
```

- 如果头文件被 50 个 `.c` 包含，而只有 3 个 `.c` 用了 `max`：
  - **立刻编译**：生成 50 份 `max` 代码（虽然 `static` 不冲突，但白占空间）；
  - **TCC 的做法**：只在用到的那 3 个 `.c` 里各生成一份。
- C99 的 `inline` 语义复杂，TCC 用"延迟 + 引用判据"简单实现了核心目的。

---

## 【把 `static inline int f(){return 1;}` 走一遍】

**情况 A：没用到**
1. `decl0` 看到 `static inline` → `skip_or_save_block` 存 token，`fn->sym = sym`；
2. 文件末尾 `gen_inline_functions`：`sym->c == 0`（没人引用）→ 跳过；
3. `free_inline_functions` 释放 token。**完全没有 `f` 的代码。**

**情况 B：用到了**
1. 同上，先存 token；
2. 某处调用 `f()` → `external_global_sym` 给 `sym->c` 赋值；
3. 文件末尾 `gen_inline_functions`：`sym->c != 0` → `begin_macro`，`gen_function`；
4. 结果 `.text` 里有一份 `f`（局部符号）。

---

## 【动手小实验】

1. 写头文件 `static inline int f(){return 1;}`，主文件 include 但不用，`nm` 看有没有 `f`。
2. 改成调用一次，再看 `nm`（应该有小写 `t f`）。
3. 两个 inline 互相调用，看 `do...while` 是否扫了两遍。
4. 在 `gen_inline_functions` 里加打印，观察哪些被编。

## 【通关暗号】

```bash
printf 'static inline int f(void){return 7;}\nint main(void){return f();}\n' > /tmp/i.c
./tcc -run /tmp/i.c; echo $?
# 期望：7
printf 'static inline int f(void){return 7;}\nint main(void){return 0;}\n' > /tmp/j.c
./tcc -c /tmp/j.c -o /tmp/j.o && nm /tmp/j.o 2>/dev/null | grep -c ' f$'
# 期望：0（没用到的 inline 没生成）
```

## 【常见卡点】

- **只有 `static inline` 延迟编译**，普通 `inline` 立刻编。
- **函数体存成 `TokenString`**，用 `skip_or_save_block`。
- **`sym->c` 非 0 = 被引用**，这是是否补编译的判据。
- **可能扫多遍**（inline 互相引用）。
- **`begin_macro`/`end_macro` 让"回放"可行**。

---

## 【第五部小结】

| 篇 | 主题 |
|---|---|
| 32 | `parse_btype` 基本类型 |
| 33 | `type_decl`/`post_type` 声明符 |
| 34 | `struct_decl`/`struct_layout` 布局 |
| 35 | `typedef` 与存储类 |
| 36 | `decl_initializer` 初始化 |
| 37 | `decl_initializer_alloc` 变量分配与符号发布 |
| 38 | `gen_function` 函数定义 |
| 39 | `inline` 延迟编译 |

**下一步（第六部）**：函数调用与 ABI——形参配对、`gfunc_call`、`prolog/epilog`、
返回值与 `varargs`。

**下一篇**：`40-形参实参配对.md`。
