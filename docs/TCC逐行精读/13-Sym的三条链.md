# 13 · Sym：三条链织出作用域、参数和结构体

> **一句话**：`Sym` 是 TCC 里"登记卡"的通用结构。它长了一个 `union` 让它**一人分饰多角**
> （变量/函数/宏/标签/字段/枚举常量），又用**三条链**分别管
> "作用域时间线""结构体成员/函数参数""同名历史"。
>
> 对应源码：`src/core/tcc.h:465`（结构）、`src/core/tcc.h:522-546`（那些标志位和取值）、
> `src/core/tccgen.c:501`（`sym_push2` 造卡）、`src/core/tccgen.c:549`（`sym_push` 登记）、
> `src/core/tccgen.c:600`（`sym_pop` 撤销）、`src/core/tccgen.c:518`（`sym_find2` 查链）。

---

## 第 0 站：结构本体（`tcc.h:465`）

```c
/* src/core/tcc.h:464-489 */
typedef struct Sym {
    int v;                  /* ★ 名字的 token 编号（还带 SYM_FIELD/SYM_STRUCT 标志） */
    unsigned short r;       /* 住哪（含义随身份变） */
    struct SymAttr a;       /* aligned/packed/weak/visibility/dllexport... */

    union {
        struct {
            int c;          /* 数值：全局变量=ELF符号索引；局部变量=栈偏移；标签=跳转链 */
            union {
                int sym_scope;  /* 局部变量：作用域层级 */
                int jnext;      /* 标签：下一条跳转 */
                struct FuncAttr f;  /* 函数：调用约定/是否变参 */
                int auxtype;    /* 位域访问类型 */
            };
        };
        long long enum_val; /* 枚举常量：值 */
        int *d;             /* 宏：本体是一串整数（第 09 篇的录音带） */
    };

    CType type;             /* 我的类型 */
    union {
        struct Sym *next;   /* ★ 链②：结构体成员 / 函数形参的下一个 */
        int asm_label;
    };
    struct Sym *prev;       /* ★ 链①：作用域栈上的上一个 */
    struct Sym *prev_tok;   /* ★ 链③：同名卡的上一个 */
} Sym;
```

**三条链各管一件事**（本篇核心）：

| 链 | 字段 | 管什么 |
|---|---|---|
| 链① | `prev` | 作用域时间线：进 `{` 记起点，出 `}` 沿它弹回 |
| 链② | `next` | 结构体成员链 / 函数形参链 |
| 链③ | `prev_tok` | 同名历史：同一个名字在不同作用域的多张卡 |

那个 `union` 让一张卡能表示不同东西：普通变量用上面那组 `c/sym_scope`，
枚举常量用 `enum_val`，宏用 `d`。**省内存，也省代码。**

---

## 第 1 站：造一张卡 —— `sym_push2`（`tccgen.c:501`）

```c
/* src/core/tccgen.c:500-514 */
/* 压栈，不做抽屉登记（"2" 表示底层版） */
ST_FUNC Sym *sym_push2(Sym **ps, int v, int t, int c)
{
    Sym *s;

    s = sym_malloc();            /* 从内存池拿一张空卡 */
    memset(s, 0, sizeof *s);     /* 清零 */
    s->v = v;
    s->type.t = t;               /* 注意：这里把 t 存在 type.t 里 */
    s->c = c;
    /* 挂到栈顶 */
    s->prev = *ps;               /* ★ 链①：指向原来的栈顶 */
    *ps = s;                     /* 栈顶换成我自己 */
    return s;
}
```

`sym_malloc`（`tccgen.c:475`）很讲究：它从一个 **`Sym` 内存池**里拿，
池空了一次分配 `SYM_POOL_NB` 张（`__sym_malloc`，`:456`），
用 `next` 串成空闲链。**编译过程中 `Sym` 创建销毁极其频繁，必须用池子。**

`sym_push2` 只挂链①，不碰名字抽屉。要进抽屉得用 `sym_push`（第 10 篇），
它内部调 `sym_push2` 后再设置链③。

---

## 第 2 站：链②——结构体成员和函数参数

结构体成员就是一条 `next` 链。`struct_decl`（第 34 篇）里：

```c
s = sym_push(v | SYM_FIELD, &btype, 0, 0);   /* 造一个成员卡 */
*ps = s;                                      /* 挂到成员链尾 */
ps = &s->next;                                /* 移动链尾指针 */
```

之后 `struct_layout`（`tccgen.c:3489`）**遍历这条 `next` 链**，逐个算偏移：

```c
while (s != NULL) {
    ... 根据 s->type 算大小和对齐，累加偏移 ...
    s = s->next;      /* ★ 下一个成员 */
}
```

函数参数链也一样：`type_decl`（第 33 篇）里 `s->next` 串起形参，
后面 `gfunc_call` / `gfunc_prolog` 遍历它。

**同一个 `next` 字段，一会儿是结构体成员，一会儿是函数参数**——
因为这两者不会同时出现，复用没坏处。

---

## 第 3 站：链①——作用域时间线（进出 `{}`）

看一个函数体的编译：

```c
/* 伪代码，示意 sym_pop 的用法 */
Sym *b = local_stack;      /* 进函数时记住当前栈顶 */
    ... 解析函数体，局部变量一层层压到 local_stack ...
sym_pop(&local_stack, b, 0);   /* 出函数时弹回 b */
```

`sym_pop`（第 10 篇贴过）沿 `prev` 链往回走，一路"关抽屉"。
**这就是作用域的实现：一个栈 + 一个保存的栈顶标记。**

块作用域同理：

```c
/* src/core/tccgen.c:5876 block() 里（示意） */
Sym *b = local_stack;
    ... 解析 { ... } 里的语句 ...
sym_pop(&local_stack, b, 0);
```

**所以 TCC 支持任意深度的块作用域，代价只是记住/弹回一个指针。**

---

## 第 4 站：链③——同名历史 `prev_tok`

同一个名字在不同作用域可以是不同变量：

```c
int x = 1;          /* 卡 A：全局 x */
void f(void) {
    int x = 2;      /* 卡 B：局部 x */
    { int x = 3; }  /* 卡 C：更内层 x */
}
```

- 卡 A、B、C 的 `v` 都是 `x` 的编号；
- 卡 B 的 `prev_tok = A`，卡 C 的 `prev_tok = B`；
- `table_ident[x编号]->sym_identifier` 指向**当前最内层**的卡（C）。

出内层 `}` 时 `sym_pop` 把抽屉指针退回 `prev_tok`，于是又指回 B。
**`prev_tok` 就是"同名卡的历史链"，配合作用域栈实现遮蔽。**

`sym_find2`（`tccgen.c:518`）则是在**一条指定的链**上找名字：

```c
/* src/core/tccgen.c:516-528 */
ST_FUNC Sym *sym_find2(Sym *s, int v)
{
    while (s) {
        if (s->v == v)
            return s;
        else if (s->v == -1)     /* -1 是链尾哨兵 */
            return NULL;
        s = s->prev;             /* 沿作用域链往回找 */
    }
    return NULL;
}
```

它用在宏展开（第 07 篇）：在 `args` 形参链、`nested_list` 展开链上找匹配。

---

## 第 5 站：`v` 里的标志位（`tcc.h:522-524`）

```c
#define SYM_STRUCT     0x40000000 /* 类型名（进 sym_struct 抽屉） */
#define SYM_FIELD      0x20000000 /* 字段/参数（不进抽屉） */
#define SYM_FIRST_ANOM 0x10000000 /* 匿名符号（不进抽屉） */
```

`v` 的**低 28 位是名字编号**，高位是标志。所以：

- `v & ~SYM_STRUCT` 得到纯编号；
- `v & SYM_FIELD` 判断"是不是字段/参数"；
- `(v & ~SYM_STRUCT) < SYM_FIRST_ANOM` 判断"是不是正常名字"。

**一个整数同时当编号和标志用**，是 TCC 省结构字段的惯用手法。

---

## 第 6 站：各种身份存在哪些字段

| 身份 | `v` | `r` | `c` / union | `type` | `next` |
|---|---|---|---|---|---|
| 全局变量 | 编号 | `VT_CONST\|VT_SYM` | `c`=ELF 符号索引 | 变量类型 | — |
| 局部变量 | 编号 | `VT_LOCAL\|VT_LVAL` | `c`=栈偏移 | 变量类型 | — |
| 函数 | 编号 | 0 | `f`=调用约定/变参 | `VT_FUNC`+返回类型 | 形参链 |
| 结构体成员 | 编号`\|SYM_FIELD` | 0 | 位域信息在 `type.t`/`c` | 成员类型 | 下一成员 |
| 宏（`#define`） | 编号 | 0 | `d`=token 串 | `MACRO_OBJ`/`MACRO_FUNC` | 形参链 |
| 标签 | 编号 | `LABEL_*` | `jnext`=跳转链 | — | — |
| 枚举常量 | 编号`\|SYM_FIELD` | 0 | `enum_val` | `VT_ENUM_VAL` | — |

**同一张结构，七种身份。** 这就是"一人分饰多角"。

---

## 【把 t.c 的链走一遍】

```c
int add(int a, int b) {
    int t = a + b;
    return t;
}
```

1. 解析 `int add(int a, int b)`：
   - `add` 造卡，`type.t = VT_FUNC`，`ref` 挂返回类型；
   - `a`、`b` 造卡（带 `SYM_FIELD`），用 `next` 串成**形参链**，挂在 `add` 的卡上；
2. 进函数体 `{`：记住 `b = local_stack`；
3. `int t`：`t` 造卡，压 `local_stack`，同时进 `sym_identifier` 抽屉（链③）；
4. 出 `}`：`sym_pop(&local_stack, b, 0)`，`t` 的卡被回收，抽屉指针回退；
5. 函数编译完，`a`、`b` 的卡也随函数局部栈一起弹掉。

`add` 自己留在 `global_stack` 和 `sym_identifier` 抽屉里，供别处调用。

---

## 【动手小实验】

1. 在 `sym_pop` 里加 `printf("pop %s\n", get_tok_str(s->v & ~SYM_FIELD, NULL));`，
   编译一个带嵌套块的小程序，看进出作用域的顺序。
2. 读 `struct_layout` 里遍历 `next` 的循环（`tccgen.c:3489` 起），
   对照结构体成员类型算大小。
3. 搜 `prev_tok`，把"设置"和"回退"的位置列成一张表。

## 【通关暗号】

```bash
printf 'int x=1;\nint main(void){int x=2; {int x=3;} return x;}\n' > /tmp/x.c
./tcc -run /tmp/x.c; echo $?
# 期望：2（内层 x 遮蔽后出了块又恢复）
```

## 【常见卡点】

- **三条链别混**：`prev`=作用域，`next`=成员/参数，`prev_tok`=同名历史。
- **`sym_push2` 不进抽屉，`sym_push` 才进**。
- **`v` 高位是标志**，取编号要 `& ~SYM_FIELD/STRUCT`。
- **`Sym` 从内存池来**，`sym_free` 也是还给池子，不是 `free`。

**下一篇**：`14-Section纸带.md` —— 机器码、数据、符号写在哪，"纸带"怎么长大。
