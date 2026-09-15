# 11 · CType：一个 `int` 装下 C 的全部类型

> **一句话**：`CType` 只有两个成员——一个整数 `t` 和一个指针 `ref`。
> `t` 用**位**编码"这是什么类型"，装不下的细节（指向谁、成员有谁）挂到 `ref`。
>
> 对应源码：`src/core/tcc.h:405`（结构）、`src/core/tcc.h:832-904`（所有位定义）、
> `src/core/tccgen.c:2748`（`pointed_type` 取所指类型）、
> `src/core/tccgen.c:2754`（`mk_pointer` 造指针类型）、
> `src/core/tccgen.c:2851`（`type_to_str` 打印类型，调试用）。

---

## 第 0 站：结构本体（`tcc.h:405`）

```c
/* src/core/tcc.h:404-408 */
typedef struct CType {
    int t;            /* ★ 一堆 bit 拼出来的类型 */
    struct Sym *ref;  /* ★ 细节：指针指向的类型 / 结构体成员链 / 函数形参链 */
} CType;
```

就这么小。为什么能装下 `unsigned long long (*)(int, char*)` 这种复杂类型？
靠两层表示：

- **`t` 里的低位**说"最外层是什么"（是指针？是数组？是函数？是 int？）；
- **`ref` 指向一个 `Sym`**，那个 `Sym` 的 `type` 又是下一层类型，可以再套。

**类型就是一串"俄罗斯套娃"**：每个套娃用一个 `CType` 表示，`ref` 指向里面的套娃。

---

## 第 1 站：`t` 的位地图（`tcc.h:832-904`）

### 1a. 低 4 位：基本类型（`VT_BTYPE`）

```c
/* src/core/tcc.h:853-867 */
#define VT_BTYPE       0x000f  /* 低 4 位：基本类型 */
#define VT_VOID             0
#define VT_BYTE             1
#define VT_SHORT            2
#define VT_INT              3
#define VT_LLONG            4
#define VT_PTR              5   /* 指针 */
#define VT_FUNC             6   /* 函数 */
#define VT_STRUCT           7   /* 结构体/联合体 */
#define VT_FLOAT            8
#define VT_DOUBLE           9
#define VT_LDOUBLE         10
#define VT_BOOL            11
#define VT_QLONG           13   /* 128 位整数，x86-64 ABI 用 */
#define VT_QFLOAT          14
```

**`t & VT_BTYPE` 就告诉你"最外层是什么"。** 例如 `t & 0xf == 5` → 它是指针。

### 1b. 其它位：修饰（`tcc.h:869-887`）

```c
#define VT_UNSIGNED    0x0010  /* unsigned */
#define VT_DEFSIGN     0x0020  /* 显式写了 signed/unsigned */
#define VT_ARRAY       0x0040  /* 数组（同时也是指针） */
#define VT_BITFIELD    0x0080  /* 位域 */
#define VT_CONSTANT    0x0100  /* const */
#define VT_VOLATILE    0x0200  /* volatile */
#define VT_VLA         0x0400  /* 变长数组 */
#define VT_LONG        0x0800  /* long（配 VT_INT 或 VT_LLONG） */

#define VT_EXTERN  0x00001000  /* extern */
#define VT_STATIC  0x00002000  /* static */
#define VT_TYPEDEF 0x00004000  /* typedef */
#define VT_INLINE  0x00008000  /* inline */
```

### 1c. 高位：结构体专有信息（`tcc.h:885-896`）

```c
#define VT_STRUCT_SHIFT 20     /* 位域/结构体专用信息从第 20 位起 */
#define VT_STRUCT_MASK (((1 << (6+6)) - 1) << VT_STRUCT_SHIFT | VT_BITFIELD)
#define BIT_POS(t)  (((t) >> VT_STRUCT_SHIFT) & 0x3f)       /* 位域起点 */
#define BIT_SIZE(t) (((t) >> (VT_STRUCT_SHIFT + 6)) & 0x3f) /* 位域宽度 */

#define VT_UNION    (1 << VT_STRUCT_SHIFT | VT_STRUCT)  /* 是 union */
#define VT_ENUM     (2 << VT_STRUCT_SHIFT)              /* 是 enum */
#define VT_ENUM_VAL (3 << VT_STRUCT_SHIFT)              /* 是枚举常量 */
```

注意这几个小工具：

```c
/* src/core/tcc.h:894-896 */
#define IS_ENUM(t)     ((t & VT_STRUCT_MASK) == VT_ENUM)
#define IS_ENUM_VAL(t) ((t & VT_STRUCT_MASK) == VT_ENUM_VAL)
#define IS_UNION(t)    ((t & (VT_STRUCT_MASK|VT_BTYPE)) == VT_UNION)
```

**判断"是不是 union/enum"不用额外字段，位运算一下就够。**

### 1d. 一个大集合运算

```c
/* src/core/tcc.h:899-900 */
#define VT_STORAGE (VT_EXTERN | VT_STATIC | VT_TYPEDEF | VT_INLINE)
#define VT_TYPE (~(VT_STORAGE|VT_STRUCT_MASK))
```

`VT_TYPE` 是"把所有存储类/结构体专有位都挖掉"的掩码，
用来判断"两个类型相不相同"时忽略存储类（`static int` 和 `int` 是同一类型）。

---

## 第 2 站：`ref` 到底指什么（三副面孔）

`CType.ref` 是一个 `Sym*`，含义随 `t & VT_BTYPE` 变化：

| 最外层是 | `ref` 指向的 `Sym` 的 `type` 是 |
|---|---|
| 指针 `VT_PTR` | **所指类型**（`int*` 的 `ref->type` 是 `int`） |
| 数组 `VT_PTR\|VT_ARRAY` | 元素类型 |
| 函数 `VT_FUNC` | 返回值类型；`ref->next` 是形参链 |
| 结构体/联合体 `VT_STRUCT` | 第一个成员；`ref->next` 是成员链 |
| 枚举 | 枚举成员链 |
| int 等基本类型 | `ref == NULL` |

举例：`char *` 的表示

```
CType{ t = VT_PTR | VT_INT(或VT_BYTE), ref = ─┐
                                              ▼
                              Sym{ type = CType{ t = VT_BYTE, ref = NULL } }
```

取所指类型就是 `pointed_type`：

```c
/* src/core/tccgen.c:2747-2751 */
static inline CType *pointed_type(CType *type)
{
    return &type->ref->type;   /* 一句话 */
}
```

造一个指针类型就是 `mk_pointer`：

```c
/* src/core/tccgen.c:2753-2760 */
ST_FUNC void mk_pointer(CType *type)
{
    Sym *s;
    s = sym_push(SYM_FIELD, type, 0, -1);  /* 把"原类型"装进一个 Sym */
    type->t = VT_PTR | (type->t & VT_STORAGE);  /* 外层变成指针 */
    type->ref = s;                          /* ref 指向那个 Sym */
}
```

**注意 `sym_push(SYM_FIELD, ...)`**：这个 `Sym` 只是"类型容器"，带 `SYM_FIELD`
所以**不会进名字抽屉**（第 10 篇）。`-1` 是 `c` 的占位值。

---

## 第 3 站：把类型打印成人话 —— `type_to_str`（`tccgen.c:2851`）

调试时想看清楚 `t` 是什么，用 `type_to_str`：

```c
/* src/core/tccgen.c:2851 起（骨架）*/
static void type_to_str(char *buf, int buf_size,
                        CType *type, const char *varstr)
{
    int bt, v, t;
    Sym *s, *sa;
    ...
    bt = type->t & VT_BTYPE;
    switch(bt) {
    case VT_BOOL:  pstrcat(...  "bool" ...); break;
    case VT_BYTE:  ... "char" ...; break;
    case VT_INT:   ... "int" ...; break;
    case VT_LLONG: ... "long long" ...; break;
    case VT_PTR:
        /* 递归打印所指类型，再加一个 '*' */
        ...
    case VT_FUNC:
        /* 返回值类型 + 参数链 + '(*)' */
        ...
    case VT_STRUCT:
        /* struct/union + 名字 */
        ...
    }
}
```

**它是递归的**：遇到指针就"递归打印里面的类型，再补一个 `*`"。
这正好印证了"类型是套娃"。

---

## 【心算几道题】

| C 类型 | 大致 `t`（十六进制） | 说明 |
|---|---|---|
| `int` | `0x3` | `VT_INT=3` |
| `unsigned int` | `0x13` | `VT_INT \| VT_UNSIGNED` |
| `int *` | `0x5` + ref 指向 int | `VT_PTR=5` |
| `const int` | `0x103` | 加 `VT_CONSTANT` |
| `char[10]` | `0x41` + ref | `VT_ARRAY(0x40) \| VT_BYTE(1)`，**数组也是指针** |
| `int f(int)` | `0x6` + ref（返回类型/参数链） | `VT_FUNC=6` |
| `struct S` | `0x7` + 成员链 | `VT_STRUCT=7` |
| `union U` | `0x100007` | `VT_UNION` |

（具体位值会因 `VT_LONG` 等略有不同，但规律就是"或"起来。）

---

## 【动手小实验】

1. 在 `tccgen.c` 的 `unary()` 里临时加一句
   `printf("type t=%x\n", vtop->type.t);`，编译一个小程序，观察不同类型运算时 `t` 的变化。
2. 读 `type_to_str` 的 `VT_PTR` 分支，理解它怎么递归。
3. 搜 `BIT_POS` / `BIT_SIZE`，看位域信息怎么从 `t` 里抠出来。

## 【通关暗号】

```bash
printf 'struct S{int a; char b;}; int main(void){return sizeof(struct S);}\n' > /tmp/s.c
./tcc -run /tmp/s.c; echo $?
# 期望：8（int 4 字节 + char 1 字节 + 对齐到 8）
# 说明 CType 的位编码 + ref 成员链 + type_size 一起算对了布局
```

## 【常见卡点】

- **`t` 不是"类型编号"**，是**位集合**。判断基本类型要 `t & VT_BTYPE`。
- **`ref` 不是"引用计数"**，是指向类型细节的 `Sym`。
- **数组也是指针**：`VT_ARRAY` 常和 `VT_PTR` 同现（`tcc.h:871` 注释 "also has VT_PTR"）。
- **`VT_STORAGE` 要挖掉**再比较类型，否则 `static int` 不等于 `int`。

**下一篇**：`12-SValue与值栈.md` —— TCC 的"中间表示"就是一张便利贴。
