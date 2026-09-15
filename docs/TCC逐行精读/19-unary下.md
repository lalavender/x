# 19 · `unary()` 下：标识符、成员、下标、函数调用

> **一句话**：`unary()` 前半段处理"字面量"，后半段处理"一个东西后面跟着的东西"——
> `.`、`->`、`[]`、`()`、`++`。这一半才是真正生成机器码的地方。
>
> 对应源码：`src/core/tccgen.c:5066-5108`（标识符，`unary` 的 `default` 分支）、
> `:5110-5284`（后缀循环，含函数调用）、`src/core/tccgen.c:4488`（`indir`）、
> `src/core/tccgen.c:3459`（`find_field`）。

---

## 第 0 站：读到一个标识符（`tccgen.c:5066`）

这是 `unary()` 的 `default` 分支，也是最重要的一站：

```c
/* src/core/tccgen.c:5066-5107 */
    default:
    tok_identifier:
        t = tok;
        next();                         /* 先吃掉这个名字 */
        if (t < TOK_UIDENT)
            expect("identifier");
        s = sym_find(t);                /* ★ 从标识符抽屉取登记卡（第 10 篇） */
        if (!s || IS_ASM_SYM(s)) {
            const char *name = get_tok_str(t, NULL);
            if (tok != '(')
                tcc_error("'%s' undeclared", name);
            /* 简单函数调用里，容忍未声明的外部函数（默认 int()） */
            if (tcc_state->warn_implicit_function_declaration ...)
                tcc_warning("implicit declaration of function '%s'", name);
            s = external_global_sym(t, &func_old_type, 0);
        }

        r = s->r;
        /* 有寄存器的符号是"寄存器变量"，初始当作 VT_LOCAL */
        if ((r & VT_VALMASK) < VT_CONST)
            r = (r & ~VT_VALMASK) | VT_LOCAL;

        vset(&s->type, r, s->c);        /* ★ 把类型和"住址"抄进便利贴 */
        vtop->sym = s;                  /* 记下是哪个符号（第 12 篇的欠条） */

        if (r & VT_SYM) {
            vtop->c.i = 0;              /* 引用全局符号：地址还没定，欠条 */
        } else if (r == VT_CONST && IS_ENUM_VAL(s->type.t)) {
            vtop->c.i = s->enum_val;    /* 枚举常量：直接是值 */
        }
        break;
```

逐点：

1. **`sym_find(t)`**：用名字编号从 `sym_identifier` 抽屉取 `Sym`（第 10 篇）。
   这就是"查变量表"的全部——O(1)。
2. **未声明函数容忍**：`foo()` 但 `foo` 没声明时，TCC 造一个"返回 int 的旧式函数"，
   只警告不报错（C89 行为）。
3. **`vset(&s->type, r, s->c)`**：把 `Sym` 的类型、住址、偏移抄到栈顶便利贴。
   - 局部变量：`r = VT_LOCAL | VT_LVAL`，`c = 栈偏移`；
   - 全局变量：`r = VT_CONST | VT_SYM`，`sym = s`（欠条）；
   - 枚举常量：`r = VT_CONST`，`c = enum_val`。
4. **`vtop->sym = s`**：把欠条贴上，后面 `gv`/重定位会用到。

**注意：变量被读到只是贴了张便利贴，还没有 load。**

---

## 第 1 站：后缀循环（`tccgen.c:5110`）

读到标识符/字面量之后，`unary()` 进入一个循环，处理"后缀运算"：

```c
/* src/core/tccgen.c:5110-5115 */
    /* post operations */
    while (1) {
        if (tok == TOK_INC || tok == TOK_DEC) {
            inc(1, tok);            /* 后缀 ++/--：1 = 后缀 */
            next();
        } else if (tok == '.' || tok == TOK_ARROW || tok == TOK_CDOUBLE) {
            /* 结构体成员访问 */
        } else if (tok == '[') {
            /* 数组下标 */
        } else if (tok == '(') {
            /* 函数调用 */
        } else {
            break;                  /* 没有更多后缀，unary 结束 */
        }
    }
```

**为什么用循环而不是递归？** 因为 `a.b.c.d` 这种链要一层层处理，
循环最自然。`.`、`[]`、`()` 的优先级相同（后缀高于一元），所以同级循环。

---

## 第 2 站：结构体成员 `.` / `->`（`tccgen.c:5115-5150`）

```c
/* src/core/tccgen.c:5115-5150（节选）*/
        } else if (tok == '.' || tok == TOK_ARROW || tok == TOK_CDOUBLE) {
            int qualifiers;
            if (tok == TOK_ARROW)
                indir();                /* a->b 先对 a 解引用，变成 (*a).b */
            qualifiers = vtop->type.t & (VT_CONSTANT | VT_VOLATILE);
            test_lvalue();
            gaddrof();                  /* 取结构体地址 */
            if ((vtop->type.t & VT_BTYPE) != VT_STRUCT)
                expect("struct or union");
            ...
            next();
            s = find_field(&vtop->type, tok);   /* ★ 在成员链里找这个字段 */
            if (!s)
                tcc_error("field not found: %s", get_tok_str(tok & ~SYM_FIELD, &tokc));
            /* 把字段偏移加到指针上 */
            vtop->type = char_pointer_type;     /* 换成 char* 好做字节加法 */
            vpushi(s->c);                       /* s->c 是字段偏移 */
            gen_op('+');                        /* 指针 + 偏移 */
            /* 换成字段类型，并标记为左值 */
            vtop->type = s->type;
            vtop->type.t |= qualifiers;
            if (!(vtop->type.t & VT_ARRAY)) {
                vtop->r |= lvalue_type(vtop->type.t);   /* 可读可写 */
            }
            next();
        }
```

五步：

1. `->` 先 `indir()` 变成 `(*p).field`；
2. `gaddrof()` 取结构体地址；
3. `find_field`（`tccgen.c:3459`）**沿 `Sym.next` 成员链找名字**（第 13 篇），
   返回的 `Sym.c` 就是偏移；
4. `char*` + 偏移 = 字段地址（`char*` 保证加的是字节数）；
5. 换成字段类型 + 标 `VT_LVAL`。

**偏移量在编译期就算好了**（`struct_layout`，第 34 篇），访问字段就是"基址 + 常量偏移"。

---

## 第 3 站：数组下标 `[]`（`tccgen.c:5151-5156`）

```c
/* src/core/tccgen.c:5151-5156 */
        } else if (tok == '[') {
            next();
            gexpr();           /* 下标表达式 */
            gen_op('+');       /* ★ 指针 + 下标 → 指针算术，自动乘元素大小 */
            indir();           /* 解引用 */
            skip(']');
        }
```

`a[i]` 就是 `*(a + i)`。**指针算术会自动乘元素大小**（`gen_op` 的指针分支，第 22 篇）。
所以 `int a[]; a[2]` = `*(a + 2*4)`——乘法是 `gen_op` 悄悄做的。

---

## 第 4 站：函数调用 `(`（`tccgen.c:5157`）

这是 `unary()` 里最长的一段（约 130 行）。分四步。

### 4a. 确认被调用者（`:5162-5178`）

```c
/* src/core/tccgen.c:5162-5178 */
            if ((vtop->type.t & VT_BTYPE) != VT_FUNC) {
                if ((vtop->type.t & (VT_BTYPE | VT_ARRAY)) == VT_PTR) {
                    vtop->type = *pointed_type(&vtop->type);   /* 函数指针 */
                    if ((vtop->type.t & VT_BTYPE) != VT_FUNC)
                        goto error_func;
                } else {
                error_func:
                    expect("function pointer");
                }
            } else {
                vtop->r &= ~VT_LVAL;     /* 函数名不是左值 */
            }
            s = vtop->type.ref;          /* s 是函数 Sym，next 挂形参链 */
            next();
            sa = s->next;                /* 第一个形参 */
            nb_args = regsize = 0;
```

- 直接函数名：`type.t == VT_FUNC`；
- 函数指针：先 `pointed_type` 得到函数类型。
- `s = vtop->type.ref` 拿到函数 `Sym`；`s->next` 是形参链（第 13 篇）。

### 4b. 返回结构体时预留空间（`:5182-5212`）

```c
/* src/core/tccgen.c:5182-5208（节选）*/
            if ((s->type.t & VT_BTYPE) == VT_STRUCT) {
                ...
                ret_nregs = gfunc_sret(&s->type, variadic, &ret.type,
                                       &ret_align, &regsize);
                if (!ret_nregs) {
                    /* 大结构体：调用者预留一块空间，把指针当隐藏参数传 */
                    size = type_size(&s->type, &align);
                    loc = (loc - size) & -align;
                    vseti(VT_LOCAL, loc);
                    ret.c = vtop->c;
                    nb_args++;      /* 隐藏参数算一个 */
                }
            } else {
                ret_nregs = 1;
                ret.type = s->type;
            }
```

**ABI 细节**：返回大结构体时，调用者分配空间、把地址作为第一个隐藏参数传进去。
返回值约定在哪个寄存器，由 `reg_fret`/`REG_IRET` 决定（`:5213-5232`）。

### 4c. 逐个压实参（`:5234-5245`）

```c
/* src/core/tccgen.c:5234-5245 */
            if (tok != ')') {
                for(;;) {
                    expr_eq();              /* 求一个实参 → 压值栈 */
                    gfunc_param_typed(s, sa);  /* ABI 分类（第 40 篇） */
                    nb_args++;
                    if (sa)
                        sa = sa->next;
                    if (tok == ')')
                        break;
                    skip(',');
                }
            }
            if (sa)
                tcc_error("too few arguments to function");
            skip(')');
            gfunc_call(nb_args);            /* ★ 后端：发 call（第 41 篇） */
```

**实参从左到右求值、依次压栈**，`sa` 沿着形参链走（顺便类型检查）。
最后一个 `gfunc_call` 才是后端"装车 + 发 call"。

### 4d. 返回值贴回值栈（`:5251-5279`）

```c
/* src/core/tccgen.c:5251-5255 */
            /* return value */
            for (r = ret.r + ret_nregs + !ret_nregs; r-- > ret.r;) {
                vsetc(&ret.type, r, &ret.c);   /* ★ 把"寄存器里的返回值"贴回值栈 */
                vtop->r2 = ret.r2;
            }

            /* 处理"打包进寄存器的结构体"返回值 */
            if (((s->type.t & VT_BTYPE) == VT_STRUCT) && ret_nregs) {
                ...
                /* 把寄存器里的结构体逐个字段写回栈上预留的空间 */
                ...
                vset(&s->type, VT_LOCAL | VT_LVAL, addr);
            }
```

调用完成后，`ret.r`（比如 `REG_IRET` = `rax`）上的返回值被贴成一张便利贴，
**于是 `f() + 1` 就能继续算**。

---

## 第 5 站：`indir()`（`tccgen.c:4488`）

`*p`、`a[i]`、`->` 都用到它：

```c
/* src/core/tccgen.c:4488 起（骨架）*/
ST_FUNC void indir(void)
{
    if ((vtop->type.t & VT_BTYPE) != VT_PTR)
        return;
    if (vtop->r & VT_LVAL)
        gv(RC_INT);                 /* 如果它本身是个左值，先取出来 */
    vtop->type = *pointed_type(&vtop->type);   /* 类型变成"所指类型" */
    vtop->r &= ~VT_LVAL;            /* 暂时不是左值 */
    vtop->r |= lvalue_type(vtop->type.t);      /* 除非所指是数组，否则是左值 */
}
```

**`indir` 只是"变换便利贴的类型和左值属性"，本身不发指令。**
真正取数要等到 `gv()`（第 21 篇）或 `vstore()`（第 24 篇）。

---

## 【把 `arr[i].x` 走一遍】

`arr` 是 `struct S arr[10]`，`i` 是 int：

1. `unary` 读 `arr`：`vset`，类型 `struct S[10]`，`r = VT_LOCAL|VT_LVAL`；
2. `[` 后缀循环：`gexpr` 解 `i`，`gen_op('+')`：
   指针 `arr` + `i` → `gen_op` 发现指针，自动 `* sizeof(struct S)`；
   `indir()` → 类型变成 `struct S`，是左值；
3. `.` 后缀：`gaddrof()`，`find_field("x")` 得偏移，`char*` + 偏移，
   换成 `int` 类型 + `VT_LVAL`；
4. 到这里 `arr[i].x` 就是"住在 `arr + i*sizeof + offsetof(x)`，是 int 左值"的便利贴。
   赋值时 `vstore` 会 `store` 进去。

---

## 【动手小实验】

1. 写 `struct S{int a; char b;}; struct S s; s.b=2;`，反汇编看偏移是不是 4。
2. 在 `find_field`（`tccgen.c:3459`）里加 `printf("field %s off %d\n", ..., s->c);`，
   观察成员偏移。
3. 写一个函数指针调用 `int (*fp)(int)=f; fp(3);`，看 `unary` 怎么处理 `VT_PTR→VT_FUNC`。

## 【通关暗号】

```bash
printf 'struct S{int a; int b;}; int main(void){struct S s; s.b=7; return s.b;}\n' > /tmp/s.c
./tcc -run /tmp/s.c; echo $?
# 期望：7
```

## 【常见卡点】

- **成员访问的偏移是编译期常量**，来自 `struct_layout`。
- **`a[i]` 就是 `*(a+i)`**，元素大小乘法在 `gen_op` 里做。
- **函数调用实参从左到右压栈**，`gfunc_call` 从栈顶倒着装。
- **`indir` 本身不发指令**，只改便利贴。

**下一篇**：`20-值栈操作全套.md` —— 便利贴的旋转、复制、交换。
