# 30 · `goto`、标签、`break`/`continue`：往一条链上追加跳转

> **一句话**：标签的处理和变量很像——也是登记卡（`Sym`），也用跳转链。
> "向前跳"（目标还没出现）先把跳转挂在标签的链上；"向后跳"（目标已出现）直接发。
>
> 对应源码：`src/core/tccpp.c:1357`（`label_find`）、`:1365`（`label_push`）、
> `:1384`（`label_pop`）、`src/core/tccgen.c:6164`（`goto`）、`:6194`（标签定义）、
> `:5725`（`is_label`）、`src/core/tccpp.c:3571`（`unget_tok`）、
> `src/core/tcc.h:544-546`（标签状态）。

---

## 第 0 站：标签的状态（`tcc.h:543-546`）

```c
/* src/core/tcc.h:543-546 */
#define LABEL_DEFINED  0   /* 标签已经定义（在当前位置） */
#define LABEL_FORWARD  1   /* 标签被用了但还没定义（前向） */
#define LABEL_DECLARED 2   /* 标签声明了但没用（__label__） */
```

一个标签的生命周期：

- `goto L;` 出现在 `L:` 之前 → `L` 先记为 `LABEL_FORWARD`，跳转挂链；
- 遇到 `L:` → 回填链，状态变 `LABEL_DEFINED`；
- 函数结束时 `LABEL_FORWARD` 还没定义 → 报错"used but not defined"。

---

## 第 1 站：标签的登记与查找（`tccpp.c:1357`）

标签用第 10 篇说的 `TokenSym.sym_label` 抽屉：

```c
/* src/core/tccpp.c:1356-1363 */
ST_FUNC Sym *label_find(int v)
{
    v -= TOK_IDENT;
    if ((unsigned)v >= (unsigned)(tok_ident - TOK_IDENT))
        return NULL;
    return table_ident[v]->sym_label;   /* 一行取抽屉 */
}
```

```c
/* src/core/tccpp.c:1365-1380 */
ST_FUNC Sym *label_push(Sym **ptop, int v, int flags)
{
    Sym *s, **ps;
    s = sym_push2(ptop, v, 0, 0);
    s->r = flags;                                  /* 状态存在 r 里 */
    ps = &table_ident[v - TOK_IDENT]->sym_label;
    if (ptop == &global_label_stack) {
        /* 全局标签：跳过同名局部标签，挂到最外层 */
        while (*ps != NULL)
            ps = &(*ps)->prev_tok;
    }
    s->prev_tok = *ps;
    *ps = s;
    return s;
}
```

`Sym.r` 存状态，`Sym.jnext`（union 里的一个成员，`tcc.h:474`）
存"跳转链"。**又是"编号即一切"的复用：标签的链存在 `c` 的位置。**

---

## 第 2 站：`goto`（`tccgen.c:6164`）

```c
/* src/core/tccgen.c:6163-6191（节选）*/
    if (tok == TOK_GOTO) {
        next();
        if (tok == '*' && gnu_ext) {
            /* 计算 goto（GNU）：goto *ptr; */
            next();
            gexpr();
            if ((vtop->type.t & VT_BTYPE) != VT_PTR)
                expect("pointer");
            ggoto();                       /* 后端：间接跳转 */
        } else if (tok >= TOK_UIDENT) {
            s = label_find(tok);
            if (!s) {
                /* ★ 前向：先登记，标记 FORWARD */
                s = label_push(&global_label_stack, tok, LABEL_FORWARD);
            } else {
                if (s->r == LABEL_DECLARED)
                    s->r = LABEL_FORWARD;
            }
            vla_sp_restore_root();
            if (s->r & LABEL_FORWARD)
                s->jnext = gjmp(s->jnext); /* ★ 前向：跳转挂到链上 */
            else
                gjmp_addr(s->jnext);       /* ★ 已知地址：直接发跳转 */
            next();
        } else {
            expect("label identifier");
        }
        skip(';');
    }
```

- **前向**（`LABEL_FORWARD`）：`s->jnext = gjmp(s->jnext)` —— 追加到链，
  等标签定义时回填。
- **后向**（`LABEL_DEFINED`）：`s->jnext` 已经是标签的代码地址，直接跳。

---

## 第 3 站：标签定义（`tccgen.c:6194`）

```c
/* src/core/tccgen.c:6194-6219（节选）*/
    } else {
        b = is_label();          /* 当前是"名字:"吗？ */
        if (b) {
            /* 标签定义 */
            next();
            s = label_find(b);
            if (s) {
                if (s->r == LABEL_DEFINED)
                    tcc_error("duplicate label '%s'", ...);
                gsym(s->jnext);  /* ★ 回填所有前向 goto 到这里 */
                s->r = LABEL_DEFINED;
            } else {
                s = label_push(&global_label_stack, b, LABEL_DEFINED);
            }
            s->jnext = ind;      /* ★ 记住标签的代码地址 */
            vla_sp_restore();
        block_after_label:
            nocode_wanted &= ~0x20000000;   /* 标签处代码可达 */
            if (tok == '}') {
                tcc_warning("deprecated use of label at end of compound statement");
            } else {
                ... block(...) ...   /* 标签后面的语句 */
            }
        } else {
            ... 表达式语句 ...
        }
    }
```

`gsym(s->jnext)` 就是第 27 篇讲的"回填跳转链"。
`s->jnext = ind` 记住标签地址，供后面的 `goto` 用。

**标签定义和 `case` 一样，都会清除 `nocode_wanted`**——
因为它是"从别处跳过来的入口"，代码是可达的。

---

## 第 4 站：`is_label` 与 `unget_tok`（`:5725`）

怎么判断"当前是标签定义"而不是"变量/表达式"？看 `is_label`：

```c
/* src/core/tccgen.c:5725-5741 */
static int is_label(void)
{
    int last_tok;
    /* 快筛：关键字和符号肯定不是标签 */
    if (tok < TOK_UIDENT)
        return 0;
    last_tok = tok;
    next();
    if (tok == ':') {          /* 名字后面跟 ':' → 是标签 */
        return last_tok;
    } else {
        unget_tok(last_tok);   /* ★ 不是标签：把名字"塞回去" */
        return 0;
    }
}
```

**`unget_tok`**（`tccpp.c:3571`）用了一个巧妙的办法：把 `last_tok`
放进一条临时录音带，`begin_macro` 切过去，于是"下一个读到的 token"就是它——
**相当于"推回一个 token"**。

```c
/* src/core/tccpp.c:3569-3579 */
ST_INLN void unget_tok(int last_tok)
{
    TokenString *str = tok_str_alloc();
    tok_str_add2(str, tok, &tokc);   /* 当前 token */
    tok_str_add(str, 0);
    begin_macro(str, 1);             /* 切到这条录音带 */
    tok = last_tok;                  /* 但先把 tok 设成要"退回"的那个 */
}
```

**一个 token 的"回退"用录音带实现，不用单独的栈。**

---

## 第 5 站：`break` / `continue` 与标签的关系

`break`/`continue` 不是标签，但机制一样——**往链上追加跳转**（第 26 篇）：

```c
/* src/core/tccgen.c:6013-6027 */
    } else if (tok == TOK_BREAK) {
        if (!bsym) tcc_error("cannot break");
        *bsym = gjmp(*bsym);       /* 追加到 break 链 */
        ...
    } else if (tok == TOK_CONTINUE) {
        if (!csym) tcc_error("cannot continue");
        vla_sp_restore_root();
        *csym = gjmp(*csym);       /* 追加到 continue 链 */
        ...
    }
```

- **`break` 链 `bsym`**：`switch` 和循环都传自己的链；循环体结束后回填到"跳出"位置。
- **`continue` 链 `csym`**：`while`/`for`/`do` 传自己的；回填到"重新判断/步进"位置。

**同一个 `block` 递归处理嵌套循环时，`bsym`/`csym` 会被内层覆盖为内层的链，
所以 `break` 只跳最内层**——这正是 C 的语义。

---

## 第 6 站：`__label__` 局部标签与函数结束检查

```c
/* src/core/tccgen.c:5951-5965（块内）*/
        if (tok == TOK_LABEL) {       /* __label__ a, b; */
            next();
            for(;;) {
                if (tok < TOK_UIDENT) expect("label identifier");
                label_push(&local_label_stack, tok, LABEL_DECLARED);
                next();
                if (tok == ',') { next(); } else { skip(';'); break; }
            }
        }
```

局部标签压进 `local_label_stack`，出块时 `label_pop` 检查：

```c
/* src/core/tccpp.c:1384-1408（节选）*/
ST_FUNC void label_pop(Sym **ptop, Sym *slast, int keep)
{
    for(s = *ptop; s != slast; s = s1) {
        s1 = s->prev;
        if (s->r == LABEL_DECLARED)
            tcc_warning("label '%s' declared but not used", ...);
        else if (s->r == LABEL_FORWARD)
            tcc_error("label '%s' used but not defined", ...);
        else {
            if (s->c)  /* 若取过标签地址 &&label */
                put_extern_sym(s, cur_text_section, s->jnext, 1);
        }
        /* 从抽屉里摘掉 */
        table_ident[s->v - TOK_IDENT]->sym_label = s->prev_tok;
        if (!keep) sym_free(s);
    }
    if (!keep) *ptop = slast;
}
```

`gen_function`（第 16 篇）在函数结束时调 `label_pop(&global_label_stack, NULL, 0)`，
报告"用了没定义"的标签。

---

## 【把 `goto end; ... end: return 0;` 走一遍】

| 步骤 | 动作 | 结果 |
|---|---|---|
| 1 | `is_label` 判 `end` 后不是 `:`？不，`goto` 分支先处理 | — |
| 2 | `label_find("end")` = NULL | 前向标签 |
| 3 | `label_push(..., LABEL_FORWARD)` | 登记，`jnext=0` |
| 4 | `s->jnext = gjmp(0)` | 发 `jmp ???`，链头存进 `jnext` |
| 5 | 中间代码 | … |
| 6 | 遇到 `end:` | `is_label` 返回 `end` |
| 7 | `label_find("end")` 找到（FORWARD） | |
| 8 | `gsym(s->jnext)` | 回填 `jmp` 到此处 |
| 9 | `s->r = LABEL_DEFINED; s->jnext = ind` | 供后用 |

---

## 【动手小实验】

1. 反汇编一个带 `goto` 的小程序，看前向跳转是否被回填。
2. 写一个"用了但没定义"的标签，看报错。
3. 写嵌套循环里两个 `break`，确认各自跳对层。
4. 在 `label_push`/`label_pop` 里加打印，观察标签进出抽屉。

## 【通关暗号】

```bash
printf 'int main(void){int i=0; loop: i++; if(i<3) goto loop; return i;}\n' > /tmp/g.c
./tcc -run /tmp/g.c; echo $?
# 期望：3
```

## 【常见卡点】

- **标签也是 `Sym`，存在 `sym_label` 抽屉里**，状态在 `r`，链在 `jnext`。
- **前向 `goto` 挂链，标签定义时 `gsym` 回填**。
- **`break`/`continue` 靠 `bsym`/`csym` 传递的链**，内层循环覆盖外层。
- **`is_label` 不是标签时用 `unget_tok` 把 token 塞回去**（录音带实现）。

**下一篇**：`31-三元运算与跳转链机制.md`。
