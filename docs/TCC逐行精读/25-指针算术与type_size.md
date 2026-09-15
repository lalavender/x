# 25 · 类型大小与指针算术：`type_size` / `pointed_size`

> **一句话**：`sizeof(int)` 是 4、`sizeof(struct S)` 是几、`p+1` 前进几字节，
> 全靠 `type_size` 算出来。指针加减就是"自动乘 `type_size`"。
>
> 对应源码：`src/core/tccgen.c:2659`（`type_size`）、`:2077`（`pointed_size`）、
> `:2748`（`pointed_type`）、`:2754`（`mk_pointer`）、`:2089`（`is_null_pointer`）、
> `:2099`（`is_integer_btype`）、`:3489`（`struct_layout`，第 34 篇）。

---

## 第 0 站：`type_size` 全解（`tccgen.c:2659`）

```c
/* src/core/tccgen.c:2658-2721 */
/* 返回编译期已知的类型大小，并把对齐写进 *a */
ST_FUNC int type_size(CType *type, int *a)
{
    Sym *s;
    int bt;

    bt = type->t & VT_BTYPE;
    if (bt == VT_STRUCT) {
        /* 结构体/联合体：布局时算好的，存在成员链头的 Sym.c/Sym.r */
        s = type->ref;
        *a = s->r;          /* 对齐 */
        return s->c;        /* 大小 */
    } else if (bt == VT_PTR) {
        if (type->t & VT_ARRAY) {
            int ts;
            s = type->ref;
            ts = type_size(&s->type, a);   /* 递归算元素大小 */
            if (ts < 0 && s->c < 0)
                ts = -ts;
            return ts * s->c;              /* ★ 元素大小 × 元素个数 */
        } else {
            *a = PTR_SIZE;                 /* 普通指针 */
            return PTR_SIZE;
        }
    } else if (IS_ENUM(type->t) && type->ref->c == -1) {
        return -1;                         /* 不完整 enum */
    } else if (bt == VT_LDOUBLE) {
        *a = LDOUBLE_ALIGN;
        return LDOUBLE_SIZE;
    } else if (bt == VT_DOUBLE || bt == VT_LLONG) {
#if defined(TCC_TARGET_I386) ...
        *a = ...;                          /* 平台相关：4 或 8 */
        return 8;
    } else if (bt == VT_INT || bt == VT_FLOAT) {
        *a = 4;
        return 4;
    } else if (bt == VT_SHORT) {
        *a = 2;
        return 2;
    } else if (bt == VT_QLONG || bt == VT_QFLOAT) {
        *a = 8;
        return 16;
    } else {
        /* char, void, function, _Bool */
        *a = 1;
        return 1;
    }
}
```

要点：

1. **结构体的大小和对齐在 `struct_layout` 时就算好，存在 `Sym` 里**，
   这里只是取出来（`s->c` 大小、`s->r` 对齐）。
2. **数组大小 = 元素大小 × 个数**（递归算元素）。
3. **`void`/函数的大小是 1**（C 标准规定 `sizeof(void)==1` 是 GCC 扩展）。
4. **对齐也是返回值的一部分**，因为 `vstore`/`load` 需要知道按几字节访问。

---

## 第 1 站：取所指类型 —— `pointed_type`（`:2748`）

```c
/* src/core/tccgen.c:2747-2751 */
static inline CType *pointed_type(CType *type)
{
    return &type->ref->type;   /* ref 指向的 Sym 的 type 就是"里面那层" */
}
```

第 11 篇讲过：`int *` 的 `ref->type` 是 `int`。**指针的类型细节就在这一层 `ref` 里。**

---

## 第 2 站：算元素大小 —— `pointed_size`（`:2077`）

```c
/* src/core/tccgen.c:2077-2081 */
static int pointed_size(CType *type)
{
    int align;
    return type_size(pointed_type(type), &align);   /* 所指类型的大小 */
}
```

`int *p` 的 `pointed_size(p)` = `sizeof(int)` = 4。
**指针算术要乘的就是它。**

---

## 第 3 站：造指针类型 —— `mk_pointer`（`:2754`）

```c
/* src/core/tccgen.c:2753-2760 */
ST_FUNC void mk_pointer(CType *type)
{
    Sym *s;
    s = sym_push(SYM_FIELD, type, 0, -1);   /* 把"原类型"塞进一个 Sym */
    type->t = VT_PTR | (type->t & VT_STORAGE);  /* 外层变指针，保留存储类 */
    type->ref = s;                          /* ref 指向它 */
}
```

`mk_pointer` 是"给类型套一层指针"的唯一入口。`&x`、函数指针、字符串数组都用它。
注意 `type->t & VT_STORAGE` 保留 `static`/`extern` 等（`typedef int *p` 时有用）。

---

## 第 4 站：指针算术怎么用它（回顾第 22 篇）

`gen_op` 的指针分支：

```c
/* 指针 + 整数：p + n → p + n * sizeof(*p) */
u = pointed_size(&vtop[-1].type);
vpushi(u);
gen_op('*');        /* n * sizeof */
gen_opic(op);       /* 地址 + 偏移 */
vtop->type = type1; /* 结果还是指针类型 */
```

```c
/* 指针 - 指针：p1 - p2 → (地址差) / sizeof(*p) */
vpushi(pointed_size(&vtop[-1].type));
vrott(3);
gen_opic(op);              /* 地址差 */
vtop->type.t = ptrdiff_type.t;
vswap();
gen_op(TOK_PDIV);          /* 除以元素大小，得到"元素个数" */
```

所以：

| 表达式 | 结果 |
|---|---|
| `int *p; p+1` | 地址 + 4 |
| `char *p; p+1` | 地址 + 1 |
| `struct S *p; p+1` | 地址 + `sizeof(struct S)` |
| `int *a,*b; a-b` | `(a-b)/4`，单位是 int 个数 |

**乘法和除法都是编译期常量 `sizeof`，实际机器码里是 `lea`/`add` 立即数或移位。**

---

## 第 5 站：几个判断小工具

```c
/* src/core/tccgen.c:2089-2097 */
static inline int is_null_pointer(SValue *p)
{
    if ((p->r & (VT_VALMASK | VT_LVAL | VT_SYM)) != VT_CONST)
        return 0;
    return ((p->type.t & VT_BTYPE) == VT_INT && (uint32_t)p->c.i == 0) ||
           ((p->type.t & VT_BTYPE) == VT_LLONG && p->c.i == 0) ||
           ((p->type.t & VT_BTYPE) == VT_PTR &&
            (PTR_SIZE == 4 ? (uint32_t)p->c.i == 0 : p->c.i == 0));
}
```

`0` 可以当空指针，任何指针类型都能和它比较/赋值——靠这个函数识别
（第 23 篇 `gen_assign_cast` 里就用它）。

```c
/* src/core/tccgen.c:2099-2103 */
static inline int is_integer_btype(int bt)
{
    return (bt == VT_BYTE || bt == VT_SHORT || bt == VT_INT || bt == VT_LLONG);
}
```

---

## 第 6 站：结构体布局在别处（预告第 34 篇）

`type_size` 对结构体只做一件事：**取预先算好的结果**。谁算的？
`struct_layout`（`tccgen.c:3489`）。它遍历 `Sym.next` 成员链，
对每个成员算偏移、考虑对齐/位域/packed，最后把"总大小"写进
成员链头 `Sym` 的 `c`，把"对齐"写进 `r`。

所以 `sizeof(struct S)` 在**第一次用到这个结构体时就算好了**，以后 O(1)。

---

## 【把 `int arr[10]; sizeof(arr)` 和 `p+1` 走一遍】

1. `int arr[10]`：类型 `CType{t = VT_PTR|VT_INT|VT_ARRAY, ref = Sym{type=int, c=10}}`；
2. `sizeof(arr)`：
   - `type_size`：`bt == VT_PTR` 且有 `VT_ARRAY`；
   - `s = ref`，`ts = type_size(int) = 4`；
   - 返回 `4 * 10 = 40`；
3. `int *p = arr; p + 3`：
   - `gen_op('+')` 指针分支：`pointed_size = 4`，`3 * 4 = 12`；
   - 地址 + 12。

---

## 【动手小实验】

1. 写 `struct {char a; int b; char c;}`，用 `sizeof` 验证布局（一般 12）。
2. 写 `int a[10]; printf("%zu\n", sizeof(a)/sizeof(a[0]))` 得到 10。
3. 写 `double *p; printf("%p %p\n", p, p+1)` 看差 8。
4. 写 `char *s="abc"; sizeof("abc")` 得 4（含 `\0`）。

## 【通关暗号】

```bash
printf 'int main(void){return sizeof(struct{char a; int b; char c;});}\n' > /tmp/s.c
./tcc -run /tmp/s.c; echo $?
# 期望：12（1 + 3padding + 4 + 1 + 3padding）
```

## 【常见卡点】

- **结构体大小/对齐是 `struct_layout` 提前算好的**，`type_size` 只是取。
- **数组算大小要递归元素**。
- **`pointed_type` 靠 `ref`**，是"套娃里的那层"。
- **指针算术的乘除都在编译期做**，机器码里是常量或移位。

---

## 【第三部小结 · TCC 的心脏】

| 篇 | 主题 |
|---|---|
| 16 | 单遍编译总入口：`decl`/`gen_function` |
| 17 | 递归下降：优先级=函数套娃 |
| 18/19 | `unary`：从字面量到函数调用 |
| 20 | 值栈操作全套 |
| 21 | `gv`/`get_reg`/`save_reg`：寄存器是临时工位 |
| 22 | `gen_op`/`gen_opic`：常量折叠 + 归约 |
| 23 | `gen_cast`：类型转换 |
| 24 | `vstore`：写进内存 |
| 25 | `type_size`/指针算术 |

**读完这部，你已经看懂了 TCC 最核心的 2000 行。**
接下来第四、五部补上语句、声明、类型系统，第六、七部进入后端，
第八、九部看链接，第十部看内存运行。

**下一篇**：`26-block语句调度室.md`。
