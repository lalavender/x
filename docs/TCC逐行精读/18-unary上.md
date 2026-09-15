# 18 · `unary()` 上：常量、字符串、强制转换、一元运算

> **一句话**：`unary()` 是表达式解析的最底层，也是最长的一个函数（约 690 行）。
> 它负责"最小的一个项"：数字、字符、字符串、`(强制转换)`、`*p`、`&x`、`!x`、`sizeof`…
>
> 对应源码：`src/core/tccgen.c:4594`（函数入口）、`:4611-4647`（各种常量）、
> `:4671-4691`（字符串）、`:4692-4736`（括号/转换）、`:4737-4811`（一元运算符）、
> `:4942-4948`（前置 `++/--`）。

---

## 第 0 站：入口（`tccgen.c:4594`）

```c
/* src/core/tccgen.c:4594-4607 */
ST_FUNC void unary(void)
{
    int n, t, align, size, r, sizeof_caller;
    CType type;
    Sym *s;
    AttributeDef ad;

    sizeof_caller = in_sizeof;   /* 记住"我是不是在 sizeof 里面" */
    in_sizeof = 0;
    type.ref = NULL;
 tok_next:
    switch(tok) {
```

`unary()` 的结构就是"看当前 `tok` 是什么，决定怎么处理"，最后进入后缀循环（第 19 篇）。
`sizeof_caller` 用来处理 `sizeof(int)` 和 `sizeof x` 的区别。

---

## 第 1 站：数字和字符常量（`tccgen.c:4611-4647`）

```c
/* src/core/tccgen.c:4611-4647（节选）*/
    case TOK_LCHAR:
        ...
    case TOK_CINT:
    case TOK_CCHAR:
        t = VT_INT;                 /* 默认类型 int */
     push_tokc:
        type.t = t;
        vsetc(&type, VT_CONST, &tokc);   /* ★ 压一张"常量"便利贴 */
        next();
        break;
    case TOK_CUINT:
        t = VT_INT | VT_UNSIGNED;   goto push_tokc;
    case TOK_CLLONG:
        t = VT_LLONG;               goto push_tokc;
    case TOK_CULLONG:
        t = VT_LLONG | VT_UNSIGNED; goto push_tokc;
    case TOK_CFLOAT:
        t = VT_FLOAT;               goto push_tokc;
    case TOK_CDOUBLE:
        t = VT_DOUBLE;              goto push_tokc;
    case TOK_CLDOUBLE:
        t = VT_LDOUBLE;             goto push_tokc;
    case TOK_CLONG:
        t = (LONG_SIZE == 8 ? VT_LLONG : VT_INT) | VT_LONG;  goto push_tokc;
    case TOK_CULONG:
        t = (LONG_SIZE == 8 ? VT_LLONG : VT_INT) | VT_LONG | VT_UNSIGNED;  goto push_tokc;
```

**这一站只做一件事：把 token 里已经算好的值（第 04 篇 `parse_number` 算的）
贴成一张 `VT_CONST` 便利贴，并打上正确类型。** 不生成任何机器码。

各种 `TOK_C*` 对应第 04 篇选出来的类型。`LONG_SIZE == 8` 判断决定 `long` 是
`VT_LLONG` 还是 `VT_INT`（64 位 Linux/mac 上是前者）。

---

## 第 2 站：`__FUNCTION__` 和字符串（`tccgen.c:4648-4691`）

```c
/* src/core/tccgen.c:4648-4670（节选）*/
    case TOK___FUNCTION__:
        if (!gnu_ext)
            goto tok_identifier;
        /* fall thru */
    case TOK___FUNC__:
        {
            void *ptr;
            int len;
            len = strlen(funcname) + 1;         /* 函数名长度 */
            type.t = VT_BYTE;
            mk_pointer(&type);                  /* char* */
            type.t |= VT_ARRAY;                 /* 但其实是数组 char[] */
            type.ref->c = len;                  /* 数组长度 */
            vpush_ref(&type, data_section, data_section->data_offset, len);
            if (!NODATA_WANTED) {
                ptr = section_ptr_add(data_section, len);   /* 往 .data 要空间 */
                memcpy(ptr, funcname, len);                 /* 把函数名拷进去 */
            }
            next();
        }
        break;
```

`__FUNCTION__` 会被替换成一个 `char[]`，内容就是当前函数名——
它把字符串**直接放进 `.data` 段**，然后压一个"指向它的引用"。

字符串常量 `"abc"` 同理（`:4678-4691`）：

```c
    case TOK_STR:
        t = VT_BYTE;
        if (tcc_state->char_is_unsigned) t = VT_BYTE | VT_UNSIGNED;
    str_init:
        if (tcc_state->warn_write_strings) t |= VT_CONSTANT;
        type.t = t;
        mk_pointer(&type);
        type.t |= VT_ARRAY;
        memset(&ad, 0, sizeof(AttributeDef));
        decl_initializer_alloc(&type, &ad, VT_CONST, 2, 0, 0);  /* 分配并写入 .data */
        break;
```

`decl_initializer_alloc`（第 37 篇）负责"给这串字符分配一段数据空间并填进去"，
然后压一张指向它的便利贴。`goto str_init` 让 `L"..."` 也走这条路（只是元素类型不同）。

---

## 第 3 站：括号 —— 三种身份（`tccgen.c:4692-4736`）

`(` 开头的东西可能是三种：

```c
/* src/core/tccgen.c:4692-4736（节选）*/
    case '(':
        next();
        if (parse_btype(&type, &ad)) {          /* ① 括号里是"类型" */
            type_decl(&type, &ad, &n, TYPE_ABSTRACT);
            skip(')');
            if (tok == '{') {
                /* ①a 复合字面量 (type){...} */
                ...
                decl_initializer_alloc(&type, &ad, r, 1, 0, 0);
            } else {
                if (sizeof_caller) {            /* ①b sizeof(type) */
                    vpush(&type);
                    return;
                }
                unary();
                gen_cast(&type);                /* ①c 强制转换 (type)expr */
            }
        } else if (tok == '{') {
            /* ② GNU 语句表达式 ({ ... }) */
            ...
            block(NULL, NULL, 1);
            ...
            skip(')');
        } else {
            gexpr();                            /* ③ 普通括号表达式 (expr) */
            skip(')');
        }
        break;
```

- **①a 复合字面量** `(struct S){1,2}`：先造类型，再像初始化变量一样分配/填数据。
- **①b `sizeof(type)`**：`sizeof_caller` 告诉它"别生成代码，只要类型"。
- **①c 强制转换**：先解右操作数 `unary()`，再 `gen_cast`（第 23 篇）。
- **② 语句表达式** `({ int x=1; x+1; })`（GNU 扩展）：整块语句求值，最后一项的值。
- **③ 普通括号**：`gexpr()` 递归。

**一个 `(` 三种含义，靠 `parse_btype` 试读类型来区分。**

---

## 第 4 站：一元运算符（`tccgen.c:4737-4787`）

```c
/* src/core/tccgen.c:4737-4787（节选）*/
    case '*':                       /* 解引用 */
        next();
        unary();
        indir();                    /* 第 19 篇讲 */
        break;
    case '&':                       /* 取地址 */
        next();
        unary();
        if ((vtop->type.t & VT_BTYPE) != VT_FUNC &&
            !(vtop->type.t & VT_ARRAY))
            test_lvalue();          /* 必须是"位置"才取地址 */
        mk_pointer(&vtop->type);
        gaddrof();                  /* 第 21 篇讲 */
        break;
    case '!':
        next();
        unary();
        if (vtop 是常量) {
            gen_cast_s(VT_BOOL);
            vtop->c.i = !vtop->c.i;         /* 编译期取反 */
        } else if ((vtop->r & VT_VALMASK) == VT_CMP)
            vtop->c.i ^= 1;                 /* 比较结果取反：改个标志 */
        else {
            save_regs(1);
            vseti(VT_JMP, gvtst(1, 0));     /* 生成"真则跳"的跳转链 */
        }
        break;
    case '~':                       /* 按位取反 = 异或 -1 */
        next();
        unary();
        vpushi(-1);
        gen_op('^');
        break;
    case '+':
        next();
        unary();
        if ((vtop->type.t & VT_BTYPE) == VT_PTR)
            tcc_error("pointer not accepted for unary plus");
        if (!is_float(vtop->type.t)) {  /* 整数：加 0 强制转换 */
            vpushi(0);
            gen_op('+');
        }
        break;
    case '-':                       /* 取负 */
        next();
        unary();
        t = vtop->type.t & VT_BTYPE;
        if (is_float(t)) {
            /* 浮点取负不能是 0-x，要用 -0 - x（IEEE 的符号规则） */
            vpush(&vtop->type);
            ...
        } else
            vpushi(0);
        vswap();
        gen_op('-');                /* 0 - x */
        break;
```

要点：

- `*` 和 `&` 在 TCC 里是"便利贴属性变换"：`*p` 把"指针"变成"所指的位置"，
  `&x` 把"位置"变成"指针"。
- `!` 对常量编译期取反；对 `VT_CMP` 只翻一个标志；否则造跳转链。
- `~x` = `x ^ -1`，**不单独写一个运算**，复用异或。
- 一元 `-x` = `0 - x`（浮点特殊，因为 `-0.0` 的处理）。

---

## 第 5 站：`sizeof` / `Alignof`（`tccgen.c:4788-4811`）

```c
/* src/core/tccgen.c:4788-4811 */
    case TOK_SIZEOF:
    case TOK_ALIGNOF1:
    case TOK_ALIGNOF2:
        t = tok;
        next();
        in_sizeof++;
        expr_type(&type, unary);        /* 解析类型或一个表达式 */
        s = vtop[1].sym;                /* 拿可能的 VLA 信息 */
        size = type_size(&type, &align);/* ★ 算类型大小（第 25 篇） */
        if (s && s->a.aligned)
            align = 1 << (s->a.aligned - 1);
        if (t == TOK_SIZEOF) {
            if (!(type.t & VT_VLA)) {
                if (size < 0)
                    tcc_error("sizeof applied to an incomplete type");
                vpushs(size);           /* 静态大小：压常量 */
            } else {
                vla_runtime_type_size(&type, &align);  /* VLA：运行时算 */
            }
        } else {
            vpushs(align);              /* alignof */
        }
        vtop->type.t |= VT_UNSIGNED;
        break;
```

`sizeof` 的结果在**编译期就算好**（除非是 VLA），压成 `size_t` 常量。
`expr_type`（`:4537`）负责"先试当类型解析，不行就当表达式"。

---

## 第 6 站：前置 `++`/`--`（`tccgen.c:4942-4948`）

```c
/* src/core/tccgen.c:4941-4948 */
    /* pre operations */
    case TOK_INC:
    case TOK_DEC:
        t = tok;
        next();
        unary();          /* 先解出操作数 */
        inc(0, t);        /* 0 = 前置（第 24 篇讲 inc） */
        break;
```

前置 `++x` 和 `--x` 共用 `inc(0, t)`。**后缀 `x++` 在后缀循环里调 `inc(1, t)`**（第 19 篇）。

---

## 第 7 站：内置函数与 GNU 扩展

`unary()` 里还有一大批 `case`：`__builtin_expect`、`__builtin_constant_p`、
`__builtin_choose_expr`、`_Generic`、`__nan__`、`__inf__`……
它们大多直接返回或做简单的常量判断，**不生成特殊机器码**。

例如：

```c
/* src/core/tccgen.c:4813-4817 */
    case TOK_builtin_expect:
        /* __builtin_expect 是 no-op */
        parse_builtin_params(0, "ee");
        vpop();
        break;
```

```c
/* src/core/tccgen.c:4853-4858 */
    case TOK_builtin_constant_p:
        parse_builtin_params(1, "e");
        n = (vtop->r & (VT_VALMASK | VT_LVAL | VT_SYM)) == VT_CONST;
        vtop--;
        vpushi(n);      /* 编译期判断是不是常量，得到 0/1 */
        break;
```

**这些是给系统头文件用的**：glibc 的头文件里到处是 `__builtin_expect`，
TCC 必须能吃掉它们才能编译标准头文件。

---

## 【把 `x = (int)2.9 + -y;` 的左边走一遍】

1. `(` → `parse_btype` 认出 `int` → `type_decl` 得到 `int` → `skip(')')`；
   后面不是 `{` → `unary()` 解 `2.9`（`TOK_CDOUBLE`，压常量）→
   `gen_cast(int)` 把 2.9 编译期变成 2（第 23 篇常量转换）；
2. `+` 由 `expr_sum` 处理；
3. `-y`：`unary` 的 `-` 分支：`unary()` 解 `y`，`vpushi(0)`，`vswap`，
   `gen_op('-')` → `0-y`；
4. `+` 归约两者。

---

## 【动手小实验】

1. 写 `sizeof(int)` 和 `sizeof("abc")`，看结果（4 和 4）。
2. 写 `int x=5; int y = ~x;` 反汇编看是否被编译成 `not`/`xor -1`。
3. 搜 `tok_next` 标签，看 `TOK_EXTENSION` 怎么被"吃掉再重看"。

## 【通关暗号】

```bash
printf 'int main(void){return (int)2.9 + 1;}\n' > /tmp/c.c
./tcc -run /tmp/c.c; echo $?
# 期望：3（2.9 截断成 2，再 +1）
```

## 【常见卡点】

- **常量在 `unary` 里只是"贴便利贴"**，不生成机器码。
- **`(` 有三种含义**：类型/转换、语句表达式、普通括号，靠 `parse_btype` 区分。
- **`~x` 就是 `x ^ -1`**，没有专门的按位取反运算码。
- **`sizeof` 编译期算好**（VLA 除外）。

**下一篇**：`19-unary下.md` —— 标识符、结构体成员、数组下标、函数调用。
