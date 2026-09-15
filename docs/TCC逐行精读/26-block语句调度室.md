# 26 · `block()`：语句的调度室

> **一句话**：`block()` 是 C 语句的总调度室——它看当前 token 是 `if`/`while`/`{`/`return`…
> 就分派给对应的处理逻辑。函数体、循环体、`if` 体全都是这个函数。
>
> 对应源码：`src/core/tccgen.c:5876`（`block`，约 360 行）、
> `src/core/tccgen.c:7054`（`gen_function` 调用它）、
> `src/core/tccgen.c:7144`（`decl0` 也调 `block`）。

---

## 第 0 站：签名和三个参数（`tccgen.c:5876`）

```c
/* src/core/tccgen.c:5876-5889 */
static void block(int *bsym, int *csym, int is_expr)
{
    int a, b, c, d, cond;
    Sym *s;

    if (tcc_state->do_debug)
        tcc_debug_line(tcc_state);

    if (is_expr) {
        /* 语句表达式 ({ ... }) 的默认返回值是 (void) */
        vpushi(0);
        vtop->type.t = VT_VOID;
    }
```

三个参数：

| 参数 | 含义 |
|---|---|
| `bsym` | **break 的跳转链**（指向外边某个变量，见第 30 篇） |
| `csym` | **continue 的跳转链** |
| `is_expr` | 是不是"语句表达式 `({...})`"（GNU 扩展） |

`break`/`continue` 之所以能工作，是因为循环把"跳转链"的地址（`&a`、`&b`）
传进来，`block` 遇到 `break` 就往里追加一条跳转（第 30 篇）。

---

## 第 1 站：一个巨大的 if-else 链

```c
/* src/core/tccgen.c:5891 起（骨架）*/
    if (tok == TOK_IF) {
        ...
    } else if (tok == TOK_WHILE) {
        ...
    } else if (tok == '{') {
        ... 复合语句 ...
    } else if (tok == TOK_RETURN) {
        ...
    } else if (tok == TOK_BREAK) {
        ...
    } else if (tok == TOK_CONTINUE) {
        ...
    } else if (tok == TOK_FOR) {
        ...
    } else if (tok == TOK_DO) {
        ...
    } else if (tok == TOK_SWITCH) {
        ...
    } else if (tok == TOK_CASE) {
        ...
    } else if (tok == TOK_DEFAULT) {
        ...
    } else if (tok == TOK_GOTO) {
        ...
    } else if (tok == TOK_ASM1 || tok == TOK_ASM2 || tok == TOK_ASM3) {
        asm_instr();
    } else {
        /* 标签 或 表达式语句 */
        b = is_label();
        if (b) { ... 标签 ... }
        else {
            if (tok != ';') {
                if (is_expr) { vpop(); gexpr(); }   /* 语句表达式：保留最后值 */
                else { gexpr(); vpop(); }            /* 普通语句：丢弃值 */
            }
            skip(';');
        }
    }
```

**注意：`block()` 只处理"一条语句"**——一个 `if`、一个 `while`、或一个 `{}` 块。
循环体 `{}` 是递归调 `block()`；`{}` 内部的语句序列在 `{` 那个分支里循环调 `decl`/`block`。

---

## 第 2 站：复合语句 `{}` —— 作用域的实现（`:5940`）

```c
/* src/core/tccgen.c:5940-5997（节选）*/
    } else if (tok == '{') {
        Sym *llabel;
        int block_vla_sp_loc = vla_sp_loc, saved_vlas_in_scope = vlas_in_scope;

        next();
        /* 记住局部栈位置 */
        s = local_stack;
        llabel = local_label_stack;
        ++local_scope;                 /* ★ 作用域层级 +1 */

        /* 局部标签声明 __label__ */
        if (tok == TOK_LABEL) { ... }

        while (tok != '}') {
            if ((a = is_label()))     /* 是标签？ */
                unget_tok(a);          /* 放回去让 block 处理 */
            else
                decl(VT_LOCAL);        /* ★ 局部声明 */
            if (tok != '}') {
                if (is_expr) vpop();
                block(bsym, csym, is_expr);   /* ★ 递归处理下一条语句 */
            }
        }
        label_pop(&local_label_stack, llabel, is_expr);
        --local_scope;                 /* ★ 作用域层级 -1 */
        sym_pop(&local_stack, s, is_expr);   /* ★ 弹回局部符号（第 13 篇） */

        /* VLA 栈帧恢复 */
        ...
        next();                        /* 吃掉 '}' */
    }
```

`{}` 块做五件事：

1. **`s = local_stack`**：记住进入时的符号栈顶；
2. **`++local_scope`**：作用域层级 +1（重定义检查用）；
3. **循环**：`decl(VT_LOCAL)` 处理声明，`block()` 处理语句；
4. **`sym_pop(&local_stack, s, ...)`**：退出时弹出块内定义的所有符号；
5. **`--local_scope`**。

**这就是块作用域的完整实现**：一个保存点 + 一次弹栈。

---

## 第 3 站：`return`（`:5998`）

```c
/* src/core/tccgen.c:5998-6012 */
    } else if (tok == TOK_RETURN) {
        next();
        if (tok != ';') {
            gexpr();                        /* 求返回值 */
            gen_assign_cast(&func_vt);      /* 转成函数返回类型 */
            if ((func_vt.t & VT_BTYPE) == VT_VOID)
                vtop--;
            else
                gfunc_return(&func_vt);     /* ★ 放进返回寄存器（第 43 篇） */
        }
        skip(';');
        /* 除非这是函数体顶层块的最后一条语句，否则跳转到函数末尾 */
        if (tok != '}' || local_scope != 1)
            rsym = gjmp(rsym);              /* ★ 追加一条"跳到函数结尾" */
        nocode_wanted |= 0x20000000;        /* 后面的代码是死的 */
    }
```

- `gfunc_return` 把返回值放进 `rax`/`xmm0` 等约定寄存器；
- **`rsym = gjmp(rsym)`**：返回后要跳到函数末尾（那里有 `epilog`），
  这条跳转链累积在全局 `rsym`，`gen_function` 最后 `gsym(rsym)` 回填（第 16 篇）；
- 优化：如果 `return` 是**顶层块最后一条且即将是 `}`**，不生成跳转（自然落到末尾）。
- `nocode_wanted |= 0x20000000`：`return` 之后的代码不可达，不生成——
  但下一个 `case`/`label` 会清除这个标志（`:6138`/`:6212`）。

---

## 第 4 站：`break` / `continue`（`:6013-6028`）

```c
/* src/core/tccgen.c:6013-6028 */
    } else if (tok == TOK_BREAK) {
        if (!bsym)
            tcc_error("cannot break");
        *bsym = gjmp(*bsym);        /* ★ 往 break 链追加一条跳转 */
        next();
        skip(';');
        nocode_wanted |= 0x20000000;
    } else if (tok == TOK_CONTINUE) {
        if (!csym)
            tcc_error("cannot continue");
        vla_sp_restore_root();
        *csym = gjmp(*csym);        /* ★ 往 continue 链追加一条跳转 */
        next();
        skip(';');
    }
```

**`break` 的本质就是"生成一条无条件的跳转，挂到循环传来的链上"。**
循环结束时统一回填（第 27/30 篇）。

---

## 第 5 站：表达式语句（最后的 `else`）

```c
/* src/core/tccgen.c:6220-6232 */
        } else {
            /* expression case */
            if (tok != ';') {
                if (is_expr) {
                    vpop();      /* 语句表达式：弹掉上一个值 */
                    gexpr();    /* 求表达式，保留值 */
                } else {
                    gexpr();    /* 普通语句：求表达式 */
                    vpop();     /* 丢弃值 */
                }
            }
            skip(';');
        }
```

普通语句 `a + b;` 求完值就 `vpop` 丢掉；语句表达式 `({a; b;})` 则保留最后一个值。

---

## 【把 `main` 的函数体走一遍】

```c
int main(void) {
    int x = 3;        /* ① */
    if (x > 0) x++;   /* ② */
    return x;         /* ③ */
}
```

`gen_function` 调 `block(NULL, NULL, 0)`：

1. 当前 `tok` 是 `{` → 进 `{}` 分支：记 `s`、`local_scope=1`；
2. `while (tok != '}')`：
   - `decl(VT_LOCAL)` 读 `int x = 3;`，压局部符号、发初始化代码；
   - `block()`：`tok == TOK_IF` → 处理 `if`（第 27 篇）；
   - `block()`：`tok == TOK_RETURN` → `gfunc_return` + `gjmp(rsym)`；
   - `tok == '}'` → 退出循环；
3. `sym_pop(&local_stack, s, 0)` 清掉 `x`；
4. `next()` 吃掉 `}`；
5. 回到 `gen_function`，`gsym(rsym)` 回填 `return` 的跳转，`gfunc_epilog()`。

---

## 【动手小实验】

1. 在 `block` 开头加 `printf("block tok=%s\\n", get_tok_str(tok, &tokc));`，
   编译带 `if`/`while`/`return` 的函数，看调度顺序。
2. 写一个 `{ int x; { int x; } }`，在 `sym_pop` 里观察两层 `x` 的进出。
3. 写 `for(;;) { break; }`，看 `break` 怎么通过 `bsym` 跳到循环外。

## 【通关暗号】

```bash
printf 'int main(void){int x=3; if(x>0) x++; return x;}\n' > /tmp/b.c
./tcc -run /tmp/b.c; echo $?
# 期望：4
```

## 【常见卡点】

- **`block` 一次只处理一条语句**，复合语句内部才循环。
- **`bsym`/`csym` 是"跳转链的地址"**，`break`/`continue` 往链上追加。
- **`{}` 靠"保存 local_stack + 弹栈"实现作用域**。
- **`return` 之后的代码用 `nocode_wanted` 标记不可达**，但 `case`/标签会恢复。

**下一篇**：`27-if-while-for-do跳转回填.md`。
