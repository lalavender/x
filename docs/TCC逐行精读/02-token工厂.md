# 02 · token 工厂：`next_nomacro1`

> **本步输入**：全局变量 `ch` / `file->buf_ptr` 指向的字符流
> **本步输出**：全局变量 `tok`（当前 token 的编号）和 `tokc`（它的值）
>
> 对应源码：`src/core/tccpp.c:2561-2968`（`next_nomacro1` 全篇，约 400 行）、
> `src/core/tccpp.c:2549`（`PARSE2` 宏）、`src/core/tccpp.c:2972/2990`（两个包装层）。
>
> 这是**整个编译器第一个"真干活"的函数**：它把字符流切成 token 流。
> 逐行读完它，你就懂了"词法分析"的全部秘密——它其实只是一台巨大的 `switch`。

---

## 第 0 站：先搞清"三个 next"的区别（`tccpp.c:2972/2990`）

TCC 里有三个长得像的函数，别搞混：

```c
/* src/core/tccpp.c:2970-2995 */
/* ① 不带宏替换、带空格的版本 */
static void next_nomacro_spc(void)
{
    if (macro_ptr) {                       /* 若正在读"宏录音带" */
        tok = *macro_ptr;
        if (tok) {
            TOK_GET(&tok, &macro_ptr, &tokc);   /* 从 int 数组里取一个 token */
            if (tok == TOK_LINENUM) {           /* 行号标记，跳过 */
                file->line_num = tokc.i;
                goto redo;
            }
        }
    } else {
        next_nomacro1();                   /* 否则从字符流造 token */
    }
}

/* ② 不带宏替换、跳过空格的版本 */
ST_FUNC void next_nomacro(void)
{
    do {
        next_nomacro_spc();
    } while (tok < 256 && (isidnum_table[tok - CH_EOF] & IS_SPC));  /* 空格就再取 */
}

/* ③ 带宏替换的版本（编译器主循环用的就是它） */
ST_FUNC void next(void) { ... }            /* 见第 07 篇 */
```

用一句话记住：

| 函数 | 会不会替换宏 | 会不会返回空格 |
|---|---|---|
| `next_nomacro1` | 不会（只造原始 token） | 会（空格也是一个 token） |
| `next_nomacro_spc` | 不会 | 会 |
| `next_nomacro` | 不会 | **会跳过空格** |
| `next` | **会** | 会 |

**为什么要有"不替换宏"的版本？** 因为 `#define A B` 里的 `A`、`B`
绝不能被替换掉——你正在定义它呢！所以预处理器内部用 `next_nomacro`，
只有正式解析 C 代码时才用 `next`。

---

## 第 1 站：工厂开工前的三块肌肉

### 肌肉一：`isidnum_table` —— 一张 257 格的"字符身份表"

`tccpp.c:48`：

```c
static unsigned char isidnum_table[256 - CH_EOF];
```

注意 `CH_EOF = -1`（`tcc.h:572`），所以 `256 - (-1) = 257`。
为什么要 257 格？因为要能用下标 `c - CH_EOF` 来查**任意字符**，
包括 `CH_EOF = -1`（下标 0）。**这一格就是留给 -1 的。**

每格存一个"身份标签"，定义在 `tcc.h:1218-1220`：

```c
#define IS_SPC 1   /* 空白 */
#define IS_ID  2   /* 可以当标识符的字符（字母、下划线…） */
#define IS_NUM 4   /* 数字字符 */
```

这张表在 `tccpp_new`（`tccpp.c:3634`）里填：

```c
/* src/core/tccpp.c:3643-3652 */
    /* init isid table */
    for(i = CH_EOF; i<128; i++)
        set_idnum(i,
            is_space(i) ? IS_SPC
            : isid(i) ? IS_ID
            : isnum(i) ? IS_NUM
            : 0);

    for(i = 128; i<256; i++)      /* ① ASCII 之外的字节，全当标识符字符 */
        set_idnum(i, IS_ID);
```

`set_idnum`（`tccpp.c:826`）就是把这个字符的格子里写上标签，
并返回它原来的标签（方便临时改、改完还原）。

> **为什么这么设计？** 因为"判断一个字符是不是字母/数字/空白"
> 是词法器里最热门的操作，会被执行几百万次。
> 每次做 `isalpha()` 函数调用太慢，**预先把答案查表存好，用一次数组访问代替一次函数调用**。
> 这是 TCC "用空间换速度"的经典手笔。

### 肌肉二：`tok` 和 `tokc`

- `tok`（全局，`tccpp.c:30`）：当前 token 的**编号**。
  - 小于 `TOK_IDENT` 的编号：都是**关键字或符号**，编号写死在 `tcctok.h` 里（第 03 篇细讲）。
  - `TOK_IDENT` 及以上：**标识符**，编号 = 那个名字在名字表里的座位号。
- `tokc`（全局，`tccpp.c:31`）：当前 token **附带的值**。
  - 数字：`tokc.i` 或 `tokc.d`；
  - 字符串：`tokc.str.data` / `tokc.str.size`；
  - 标识符：`tok` 这个编号本身就能查到名字，`tokc` 不用。

### 肌肉三：`parse_flags` / `tok_flags`

- `parse_flags`（`tccpp.c:27`）：**这次读 token 用什么模式**。`tcc.h:1207-1215`：
  ```c
  #define PARSE_FLAG_PREPROCESS 0x0001 /* 现在在预处理模式 */
  #define PARSE_FLAG_TOK_NUM    0x0002 /* 把 TOK_PPNUM 直接变成数字 */
  #define PARSE_FLAG_LINEFEED   0x0004 /* 换行要作为一个 token 返回 */
  #define PARSE_FLAG_ASM_FILE   0x0008 /* 正在读汇编 */
  #define PARSE_FLAG_SPACES     0x0010 /* 空格也要返回（-E 用） */
  #define PARSE_FLAG_ACCEPT_STRAYS 0x0020 /* 允许游离反斜杠 */
  #define PARSE_FLAG_TOK_STR    0x0040 /* 把 TOK_PPSTR 直接变成字符串 */
  ```
- `tok_flags`（`tccpp.c:26`）：**当前 token 的位置小旗子**。`tcc.h:1202-1205`：
  ```c
  #define TOK_FLAG_BOL   0x0001 /* Beginning Of Line：这个 token 在行首 */
  #define TOK_FLAG_BOF   0x0002 /* Beginning Of File */
  #define TOK_FLAG_ENDIF 0x0004 /* 刚处理完匹配的 #endif */
  #define TOK_FLAG_EOF   0x0008 /* 文件末尾已报告过 */
  ```

`tok_flags` 最关键的作用：**判断 `#` 是不是"行首的预处理指令"**。
`int x; # y` 里的 `#` 不是指令；单独一行的 `#define` 才是。
靠的就是 `TOK_FLAG_BOL`。

---

## 第 2 站：工厂主循环开工（`tccpp.c:2561-2570`）

```c
/* src/core/tccpp.c:2561-2570 */
static inline void next_nomacro1(void)
{
    int t, c, is_long, len;
    TokenSym *ts;
    uint8_t *p, *p1;
    unsigned int h;

    p = file->buf_ptr;      /* ★ 把书签抄进局部指针 p */
 redo_no_start:             /* ★ 回到这里重新看当前字符 */
    c = *p;                 /* ★ c = 当前字符 */
    switch(c) {
```

**关键设计**：它把 `file->buf_ptr` 抄进局部变量 `p`，然后**全程用 `p` 高速扫描**，
最后（`tccpp.c:2964`）才写回 `file->buf_ptr = p`。
这样避免了每次读字符都访问全局变量，也避开了 `ch` 那套慢一点的机制。
只有碰到 `\`（可能是缓冲区墙）时，才把 `p` 同步回 `file->buf_ptr`，
调用 `handle_eob` / `handle_stray1`，再取回来。

`redo_no_start` 是一个标签：`goto redo_no_start` 就是"重新看当前字符"。
跨过空白、跨过文件边界时都会用到。

---

## 第 3 站：跳过空白（`tccpp.c:2571-2585`）

```c
/* src/core/tccpp.c:2571-2585 */
    switch(c) {
    case ' ':
    case '\t':
        tok = c;                        /* 先假设"空格也是一个 token" */
        p++;
        if (parse_flags & PARSE_FLAG_SPACES)
            goto keep_tok_flags;        /* 只有 -E 模式才真返回空格 */
        while (isidnum_table[*p - CH_EOF] & IS_SPC)
            ++p;                        /* 否则一口气把所有空白吃掉 */
        goto redo_no_start;             /* 回去重新看下一个字符 */
    case '\f':
    case '\v':
    case '\r':
        p++;
        goto redo_no_start;             /* 这些直接忽略 */
```

翻译：

- 空格和 Tab：**默认不是 token**。它先把 `tok` 记成空格（万一 `-E` 模式要用），
  再一口气把连续空白全扫掉，然后 `goto redo_no_start` 重新看。
- 换页、垂直制表、回车：直接跨过，不算 token。

> **为什么先把 `p++` 再判断？** 因为 `goto keep_tok_flags` 需要"已经消费掉这个空格"。
> `keep_tok_flags` 在函数末尾，会把 `p` 写回书签。所以顺序不能反。

**注意 `\n`（换行）不在这一组**，它被单独处理（下一站），因为行号要加一。

---

## 第 4 站：反斜杠与文件边界（`tccpp.c:2586-2636`）

这是最绕的一段，但很值得读，因为它藏着 include 的进出。

```c
/* src/core/tccpp.c:2586-2636 */
    case '\\':
        /* first look if it is in fact an end of buffer */
        c = handle_stray1(p);           /* ★ 让专业函数判断：是墙？还是续行？ */
        p = file->buf_ptr;
        if (c == '\\')
            goto parse_simple;          /* 真的是一个反斜杠字符 → 当普通符号返回 */
        if (c != CH_EOF)
            goto redo_no_start;         /* 是 \<换行> 被吃掉了 → 回去看下一个字符 */
        {                               /* 到这里 c == CH_EOF：文件真的读完了 */
            TCCState *s1 = tcc_state;
            if ((parse_flags & PARSE_FLAG_LINEFEED)
                && !(tok_flags & TOK_FLAG_EOF)) {
                tok_flags |= TOK_FLAG_EOF;
                tok = TOK_LINEFEED;     /* 预处理模式：先返回一个换行 */
                goto keep_tok_flags;
            } else if (!(parse_flags & PARSE_FLAG_PREPROCESS)) {
                tok = TOK_EOF;          /* 非预处理模式：直接 EOF */
            } else if (s1->ifdef_stack_ptr != file->ifdef_stack_ptr) {
                tcc_error("missing #endif");    /* #if 没配对的 #endif */
            } else if (s1->include_stack_ptr == s1->include_stack) {
                tok = TOK_EOF;          /* include 栈空：整个文件结束 */
            } else {
                tok_flags &= ~TOK_FLAG_EOF;
                /* pop include file：回到上一层的文件 */
                if (tok_flags & TOK_FLAG_ENDIF) {
                    search_cached_include(s1, file->filename, 1)
                        ->ifndef_macro = file->ifndef_macro_saved;
                    tok_flags &= ~TOK_FLAG_ENDIF;
                }
                if (tcc_state->do_debug)
                    put_stabd(N_EINCL, 0, 0);
                tcc_close();                    /* ★ 关掉当前文件 */
                s1->include_stack_ptr--;        /* ★ 弹出 include 栈 */
                p = file->buf_ptr;
                if (p == file->buffer)
                    tok_flags = TOK_FLAG_BOF|TOK_FLAG_BOL;
                goto redo_no_start;             /* 回到上一层的字符流继续 */
            }
        }
        break;
```

逐层理解：

1. **先问 `handle_stray1`**：它看到 `\`，检查后面是不是换行。
   - 后面是换行 → 吃掉续行，返回换行后的第一个字符（`c != CH_EOF`），于是 `goto redo_no_start`；
   - 后面不是换行 → **这是一个真正的反斜杠字符**，返回 `'\\'`，于是 `goto parse_simple`
     把它当普通符号 token 返回；
   - 缓冲/文件到头 → 返回 `CH_EOF`。
2. **`CH_EOF` 分支**按四种情况处理：
   - 预处理模式且还没报过 EOF → 先吐一个 `TOK_LINEFEED`（让 `#include` 能收尾）；
   - 非预处理模式 → `TOK_EOF`；
   - `#if` 没配对 → 报错 `missing #endif`；
   - 还有 include 层 → `tcc_close()` 关掉当前文件，顺着 `prev` 回到上一层，继续读。
3. **`TOK_FLAG_BOF|TOK_FLAG_BOL`**：回到上一层文件后，如果又站在文件头，
   就重新标记"行首/文件头"。

> **这一站就是 `#include` 的全部实现**——没有单独的"include 函数"。
> 打开头文件发生在 `preprocess()`（第 08 篇），而**关闭头文件、回到上一层，就在这**。
> `tcc_close`（`libtcc.c:553`）里 `file = bf->prev;` 一行，就是"出栈"。

---

## 第 5 站：换行（`tccpp.c:2638-2646`）

```c
/* src/core/tccpp.c:2638-2646 */
    case '\n':
        file->line_num++;               /* 行号 +1 */
        tok_flags |= TOK_FLAG_BOL;      /* 下一 token 在行首 */
        p++;
    maybe_newline:
        if (0 == (parse_flags & PARSE_FLAG_LINEFEED))
            goto redo_no_start;         /* 不需要换行 token → 忽略它 */
        tok = TOK_LINEFEED;
        goto keep_tok_flags;
```

- 默认（不设 `PARSE_FLAG_LINEFEED`）换行被忽略，但**行号加了 1**、行首标记设了。
- 预处理模式需要换行当"语句结束"，才返回 `TOK_LINEFEED`。

`maybe_newline` 是给 `#` 分支共用的标签（下一站）。

---

## 第 6 站：`#` 与预处理指令（`tccpp.c:2648-2670`）

```c
/* src/core/tccpp.c:2648-2670 */
    case '#':
        PEEKC(c, p);                    /* 看下一个字符（会处理续行） */
        if ((tok_flags & TOK_FLAG_BOL) &&         /* ① 在行首？ */
            (parse_flags & PARSE_FLAG_PREPROCESS)) /* ② 在预处理模式？ */
        {
            file->buf_ptr = p;          /* 同步书签 */
            preprocess(tok_flags & TOK_FLAG_BOF);  /* ★ 切进预处理器 */
            p = file->buf_ptr;
            goto maybe_newline;         /* 指令处理完，接着当换行处理 */
        } else {
            if (c == '#') {
                p++;
                tok = TOK_TWOSHARPS;    /* ## 拼接运算符 */
            } else {
                if (parse_flags & PARSE_FLAG_ASM_FILE) {
                    p = parse_line_comment(p - 1);  /* 汇编里 # 是行注释 */
                    goto redo_no_start;
                } else {
                    tok = '#';          /* 否则就是一个普通的 # token */
                }
            }
        }
        break;
```

**判断"这到底是不是预处理指令"只看两点**：`TOK_FLAG_BOL`（行首）和
`PARSE_FLAG_PREPROCESS`（预处理模式）。都满足才调 `preprocess`。

注意 `#` 在行首也可能是 `#define` 的 `#`，在行中间可能是 `##`（宏拼接）。
`##` 会被认成 `TOK_TWOSHARPS`。

---

## 第 7 站：标识符 —— 全厂最快的一段（`tccpp.c:2672-2749`）

```c
/* src/core/tccpp.c:2672-2732 */
    /* 非汇编模式下，$ 也可以开头 */
    case '$':
        if (!(isidnum_table[c - CH_EOF] & IS_ID)
         || (parse_flags & PARSE_FLAG_ASM_FILE))
            goto parse_simple;

    case 'a': case 'b': ... case 'z':   /* 26 个小写 */
    case 'A': case 'B': ... case 'Z':   /* 26 个大写 */
    case '_':
    parse_ident_fast:
        p1 = p;                          /* 记住名字开头 */
        h = TOK_HASH_INIT;               /* 开始算哈希 */
        h = TOK_HASH_FUNC(h, c);
        while (c = *++p, isidnum_table[c - CH_EOF] & (IS_ID|IS_NUM))
            h = TOK_HASH_FUNC(h, c);     /* ★ 边扫边算哈希 */
        len = p - p1;                    /* 名字长度 */
        if (c != '\\') {                 /* 没撞到墙/反斜杠：全程在缓冲区内 */
            TokenSym **pts;
            h &= (TOK_HASH_SIZE - 1);    /* 哈希取模（HASH_SIZE 是 2 的幂） */
            pts = &hash_ident[h];
            for(;;) {                    /* 在哈希桶里找 */
                ts = *pts;
                if (!ts) break;
                if (ts->len == len && !memcmp(ts->str, p1, len))
                    goto token_found;    /* 找到了！ */
                pts = &(ts->hash_next);
            }
            ts = tok_alloc_new(pts, (char *) p1, len);   /* 没找到，新建 */
        token_found: ;
        } else {
            /* 慢路径：名字里夹了个 \（缓冲区边界/续行） */
            cstr_reset(&tokcstr);
            cstr_cat(&tokcstr, (char *) p1, len);
            p--;
            PEEKC(c, p);
        parse_ident_slow:
            while (isidnum_table[c - CH_EOF] & (IS_ID|IS_NUM)) {
                cstr_ccat(&tokcstr, c);
                PEEKC(c, p);
            }
            ts = tok_alloc(tokcstr.data, tokcstr.size);
        }
        tok = ts->tok;                   /* ★ 最终 tok = 名字的编号 */
        break;
```

逐点解释：

1. **26+26+1 个 `case`** 是"快路径"的入口。凡是字母或下划线开头，直接跳 `parse_ident_fast`。
2. **边扫边算哈希** `h = TOK_HASH_FUNC(h, c)`：一边往前走，一边把字符揉进哈希值，
   扫完名字，哈希也算完了，**不用第二遍遍历**。哈希函数在 `tccpp.c:443`：
   ```c
   #define TOK_HASH_INIT 1
   #define TOK_HASH_FUNC(h, c) ((h) + ((h) << 5) + ((h) >> 27) + (c))
   ```
3. **`h &= (TOK_HASH_SIZE - 1)`**：`TOK_HASH_SIZE = 16384`（`tcc.h:376`），
   是 2 的幂，所以"取余"用一次位与就行。桶数组 `hash_ident[16384]` 在 `tccpp.c:43`。
4. **`c != '\\'` 判断**：如果名字扫着扫着撞到 `\`，那可能是缓冲区墙，
   `memcmp` 这种"一次性比较整段内存"就不能用了（因为名字可能跨缓冲区）。
   于是退化成"慢路径"：一个字符一个字符地拷进 `tokcstr`，最后调 `tok_alloc`。
5. **`tok = ts->tok`**：找到/新建的 `TokenSym` 里的编号，就是 token 编号。
   所以往后所有对 `add` 的判断，都是判断这个编号。

> **`L` 开头的特殊情况**（`tccpp.c:2733-2748`）：因为 `L"..."`（宽字符串）、
> `L'x'`（宽字符）也以 `L` 开头，TCC 先看 `L` 后面第二个字符是不是 `'` 或 `"`，
> 是的话走宽字符/字符串路径，不是的话当普通标识符（`L` 可能是个变量名）。
> 这体现了词法分析的一个难点：**"看到的字符"和"该切在哪"有时要往回看/往前看**。

---

## 第 8 站：数字（`tccpp.c:2751-2780`）

词法阶段**只把数字的字符拼成一个字符串**，不真正转成数字：

```c
/* src/core/tccpp.c:2751-2780 */
    case '0': ... case '9':
        t = c;
        PEEKC(c, p);
    parse_num:
        cstr_reset(&tokcstr);
        for(;;) {
            cstr_ccat(&tokcstr, t);
            if (!((isidnum_table[c - CH_EOF] & (IS_ID|IS_NUM))
                  || c == '.'
                  || ((c == '+' || c == '-')
                      && (((t == 'e' || t == 'E') && ... )
                          || t == 'p' || t == 'P'))))
                break;
            t = c;
            PEEKC(c, p);
        }
        cstr_ccat(&tokcstr, '\0');
        tokc.str.size = tokcstr.size;
        tokc.str.data = tokcstr.data;
        tok = TOK_PPNUM;            /* ★ 只是一个"数字文本"token！ */
        break;
```

- 规则：接受数字、字母、`.`；`+`/`-` 只在紧跟 `e/E/p/P` 时才接受（指数符号）。
- 结果：`tok = TOK_PPNUM`，真正的文本在 `tokc.str.data` 里。
- **为什么不在这里转成数字？** 因为预处理器只需要"这是个数字 token"，
  不需要数值；而且 `-D` 传进来的数字、宏里的数字都要原样保留。
  真正的转换推迟到 `next()`（第 07 篇）里根据 `PARSE_FLAG_TOK_NUM` 调 `parse_number`。
  **这是"延迟计算"的一个例子**。

**`.` 开头的特殊情况**（`tccpp.c:2782-2804`）：`.` 既可能是小数点（`.5`），
也可能是结构体成员（`a.b`），也可能是 `...`。TCC 在这里往前看一位来区分。

---

## 第 9 站：字符串与字符（`tccpp.c:2805-2819`）

```c
/* src/core/tccpp.c:2805-2819 */
    case '\'':
    case '\"':
        is_long = 0;
    str_const:
        cstr_reset(&tokcstr);
        if (is_long)
            cstr_ccat(&tokcstr, 'L');
        cstr_ccat(&tokcstr, c);                        /* 把开引号也存进去 */
        p = parse_pp_string(p, c, &tokcstr);           /* 扫到配对引号（不解转义） */
        cstr_ccat(&tokcstr, c);                        /* 存闭引号 */
        cstr_ccat(&tokcstr, '\0');
        tokc.str.size = tokcstr.size;
        tokc.str.data = tokcstr.data;
        tok = TOK_PPSTR;                               /* 只是"字符串文本"token */
        break;
```

和数字一样，这里**只收集原始文本**（连引号一起存），
真正解释转义（`\n` → 换行）留到 `next()` 调 `parse_string` 时才做。
`parse_pp_string` 的逐行讲解见第 05 篇。

---

## 第 10 站：运算符（`tccpp.c:2821-2935`）与 `PARSE2` 宏

这部分是纯粹的"看下一个字符决定是哪个运算符"。举两个例子：

```c
/* src/core/tccpp.c:2821-2837 */
    case '<':
        PEEKC(c, p);
        if (c == '=') { p++; tok = TOK_LE; }        /* <= */
        else if (c == '<') {
            PEEKC(c, p);
            if (c == '=') { p++; tok = TOK_A_SHL; } /* <<= */
            else { tok = TOK_SHL; }                 /* << */
        } else { tok = TOK_LT; }                    /* < */
        break;
```

而那五个"两字符运算符"用宏简化（`tccpp.c:2549`）：

```c
/* src/core/tccpp.c:2549-2558 */
#define PARSE2(c1, tok1, c2, tok2)              \
    case c1:                                    \
        PEEKC(c, p);                            \
        if (c == c2) {                          \
            p++;                                \
            tok = tok2;                         \
        } else {                                \
            tok = tok1;                         \
        }                                       \
        break;
```

于是：

```c
/* src/core/tccpp.c:2911-2915 */
    PARSE2('!', '!', '=', TOK_NE)     /* != 或 ! */
    PARSE2('=', '=', '=', TOK_EQ)     /* == 或 = */
    PARSE2('*', '*', '=', TOK_A_MUL)  /* *= 或 * */
    PARSE2('%', '%', '=', TOK_A_MOD)  /* %= 或 % */
    PARSE2('^', '^', '=', TOK_A_XOR)  /* ^= 或 ^ */
```

**注释的处理**（`tccpp.c:2917-2935`）很妙：注释被替换成**一个空格 token**。

```c
    case '/':
        PEEKC(c, p);
        if (c == '*') {
            p = parse_comment(p);
            tok = ' ';              /* 块注释 → 空格 */
            goto keep_tok_flags;
        } else if (c == '/') {
            p = parse_line_comment(p);   /* 行注释 */
            tok = ' ';
            goto keep_tok_flags;
        } else if (c == '=') { p++; tok = TOK_A_DIV; }
        else { tok = '/'; }
        break;
```

> **为什么注释变空格，而不是直接删掉？**
> 因为 `int/**/x;` 和 `intx;` 必须区分！留下一个空格，
> 词法器就会把 `int` 和 `x` 当成两个 token。**删掉注释会悄悄改变程序语义。**
> 这是 C 标准的要求，TCC 用"变成一个空格"来满足它。

---

## 第 11 站：简单符号与收尾（`tccpp.c:2937-2968`）

```c
/* src/core/tccpp.c:2937-2968 */
    /* simple tokens */
    case '(': case ')': case '[': case ']':
    case '{': case '}': case ',': case ';':
    case ':': case '?': case '~': case '@':
    parse_simple:
        tok = c;                /* ★ 单字符符号：token 编号就是字符的 ASCII 码！ */
        p++;
        break;
    default:
        if (c >= 0x80 && c <= 0xFF)   /* UTF-8 标识符 */
            goto parse_ident_fast;
        if (parse_flags & PARSE_FLAG_ASM_FILE)
            goto parse_simple;
        tcc_error("unrecognized character \\x%02x", c);
        break;
    }
    tok_flags = 0;              /* ★ 走到这里说明拿到了一个真 token：清空位置旗子 */
keep_tok_flags:
    file->buf_ptr = p;          /* ★ 局部指针 p 写回书签 */
#if defined(PARSE_DEBUG)
    printf("token = %d %s\n", tok, get_tok_str(tok, &tokc));
#endif
}
```

两个关键：

1. **单字符符号的 token 编号就是它的 ASCII 码**（`tok = c`）。
   所以后面代码里会看到 `if (tok == '+')`、`if (tok == '{')` 这种写法——
   完全不神秘，就是 ASCII。
2. **`tok_flags = 0` 在 `keep_tok_flags` 之前**：
   正常造出一个 token 就清掉"行首/文件头"旗子；
   但 `goto keep_tok_flags` 的路径（空格、换行、注释、EOF）会**保留**旗子，
   因为它们没有产生"真正的 token"，下一个真 token 的位置属性不能丢。

---

## 【把 t.c 的前几个 token 走一遍】

输入（`t.c` 开头）：

```c
#define K 8
int add(int a, int b) { return a + b; }
```

在预处理模式下，`next_nomacro` 依次产出：

| 步骤 | `tok` | `tokc` | 说明 |
|---|---|---|---|
| 1 | `'#'` | — | 行首 + 预处理模式 → 调 `preprocess()` |
| （preprocess 内部） | `TOK_DEFINE` | — | `#define` 关键字 |
| | `K`（一个 `TOK_IDENT`+编号） | — | 宏名 |
| | `TOK_PPNUM` | `"8"` | 数字文本 |
| | `TOK_LINEFEED` | — | 一行结束 |
| 回到主循环 | `TOK_INT` | — | `int` 关键字 |
| | `add`（`TOK_IDENT`） | — | 函数名 |
| | `'('` | — | ASCII 40 |
| | `TOK_INT` | — | 形参类型 |
| | `a` | — | |
| | `','` | — | |
| … | … | … | |

**注意第 1 步之后，控制权就交给了 `preprocess()`（第 08 篇），
`#define K 8` 整行在 `preprocess` 里被消化掉，根本不会进入 C 语法分析。**

---

## 【动手小实验】

1. 把 `tccpp.c:2963` 的 `keep_tok_flags` 那段注释掉的 `PARSE_DEBUG` 打开，
   重新编译 TCC，然后 `tcc -E t.c`，你会看到**每一个 token 被实时打印出来**。
   （注意：这需要你手上有能编译 TCC 的环境，见仓库 `Makefile`。）
2. 在 `next_nomacro1` 里数一数 `goto redo_no_start` 出现了几次。
   每一次都代表一种"这个字符不算 token，重看下一个"的情况。

## 【通关暗号】

```bash
./tcc -E t.c 2>/dev/null | grep -c 'define'
# 期望输出：0
# 说明：-E 展开后，#define 已经被吃掉，不会再出现在输出里。
```

## 【常见卡点】

- **为什么有些字符直接 `tok = c`**：因为单字符符号的编号就是 ASCII 码，最省事。
- **`TOK_PPNUM` / `TOK_PPSTR` 到底存了什么**：存的是**原始文本**，
  数值解释推迟到 `next()`。
- **注释为什么变空格**：为了不让 `int/**/x` 被粘成 `intx`。
- **`\` 是三种东西**：缓冲区墙、续行符、真反斜杠——靠 `handle_stray1` 区分。

**下一篇**：`03-名字与关键字表.md` —— 名字表 `TokenSym` 是怎么做到
"同一个名字只存一份"的，关键字编号又是从哪来的。
