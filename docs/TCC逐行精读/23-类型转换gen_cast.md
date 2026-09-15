# 23 · 类型转换：`gen_cast` 与 `gen_assign_cast`

> **一句话**：`(int)x`、`a + b` 里的隐式提升、赋值时的类型检查，
> 都汇聚到 `gen_cast(type)`——把栈顶便利贴"改成"另一种类型。
> 常量直接算，非常量调后端发转换指令。
>
> 对应源码：`src/core/tccgen.c:2459`（`gen_cast`）、`:2451`（`gen_cast_s` 包装）、
> `:2974`（`gen_assign_cast` 赋值检查）、`:2417`（`force_charshort_cast`）。

---

## 第 0 站：两个入口，一个核心

| 函数 | 什么时候用 | 做什么 |
|---|---|---|
| `gen_cast(type)` | 显式转换、运算提升 | 只做转换，不检查兼容性 |
| `gen_assign_cast(type)` | 赋值、函数传参 | 先**类型检查/警告**，再 `gen_cast` |
| `gen_cast_s(t)` | 只要一个简单的"基本类型" | `gen_cast` 的薄包装 |

```c
/* src/core/tccgen.c:2450-2457 */
/* 把 vtop 转成 type。不允许转成位域 */
static void gen_cast_s(int t)
{
    CType type;
    type.t = t;
    type.ref = NULL;
    gen_cast(&type);
}
```

---

## 第 1 站：赋值时的检查 —— `gen_assign_cast`（`tccgen.c:2974`）

```c
/* src/core/tccgen.c:2974-3066（节选）*/
static void gen_assign_cast(CType *dt)
{
    CType *st, *type1, *type2;
    ...
    st = &vtop->type;              /* 源类型 */
    dbt = dt->t & VT_BTYPE;        /* 目标基本类型 */
    sbt = st->t & VT_BTYPE;
    if (sbt == VT_VOID || dbt == VT_VOID) {
        if (!(sbt == VT_VOID && dbt == VT_VOID))
            tcc_error("cannot cast from/to void");
    }
    if (dt->t & VT_CONSTANT)
        tcc_warning("assignment of read-only location");

    switch(dbt) {
    case VT_PTR:
        if (is_null_pointer(vtop)) goto type_ok;      /* 0 可以当null指针 */
        if (is_integer_btype(sbt)) {
            tcc_warning("assignment makes pointer from integer without a cast");
            goto type_ok;
        }
        type1 = pointed_type(dt);
        if (sbt == VT_FUNC) { ... goto type_ok; }     /* 函数隐式转函数指针 */
        if (sbt != VT_PTR) goto error;
        type2 = pointed_type(st);
        if ((type1->t & VT_BTYPE) == VT_VOID || (type2->t & VT_BTYPE) == VT_VOID) {
            /* void * 能配任何指针 */
        } else {
            if (!is_compatible_unqualified_types(type1, type2)) {
                /* 目标类型不同就警告（但还是放行） */
                ...
                tcc_warning("assignment from incompatible pointer type");
            }
        }
        /* const/volatile 检查 */
        if ((!(type1->t & VT_CONSTANT) && (type2->t & VT_CONSTANT)) || ...)
            tcc_warning("assignment discards qualifiers from pointer target type");
        break;
    case VT_BYTE: case VT_SHORT: case VT_INT: case VT_LLONG:
        if (sbt == VT_PTR || sbt == VT_FUNC)
            tcc_warning("assignment makes integer from pointer without a cast");
        else if (sbt == VT_STRUCT) goto case_VT_STRUCT;
        break;
    case VT_STRUCT:
    case_VT_STRUCT:
        if (!is_compatible_unqualified_types(dt, st)) {
        error:
            type_to_str(buf1, ...); type_to_str(buf2, ...);
            tcc_error("cannot cast '%s' to '%s'", buf1, buf2);
        }
        break;
    }
 type_ok:
    gen_cast(dt);                  /* ★ 检查完真正转换 */
}
```

**要点**：C 的类型系统很宽松，TCC 大量使用**警告**而不是错误：
`int` 转指针、指针目标类型不兼容都只警告。只有"void 与非 void""不兼容结构体"才是错误。

**检查完就交给 `gen_cast`。**

---

## 第 2 站：`gen_cast` 的四段（`tccgen.c:2459`）

```c
/* src/core/tccgen.c:2459-2478（节选）*/
static void gen_cast(CType *type)
{
    int sbt, dbt, sf, df, c, p;

    /* ① 延迟的 char/short 转换 */
    if (vtop->r & VT_MUSTCAST) {
        vtop->r &= ~VT_MUSTCAST;
        force_charshort_cast(vtop->type.t);
    }

    /* ② 位域先转成 int */
    if (vtop->type.t & VT_BITFIELD) {
        gv(RC_INT);
    }

    dbt = type->t & (VT_BTYPE | VT_UNSIGNED);   /* 目标基本类型+符号 */
    sbt = vtop->type.t & (VT_BTYPE | VT_UNSIGNED);

    if (sbt != dbt) {
        sf = is_float(sbt);
        df = is_float(dbt);
        c = (vtop->r & (VT_VALMASK|VT_LVAL|VT_SYM)) == VT_CONST;   /* 是常量？ */
        p = (vtop->r & (VT_VALMASK|VT_LVAL|VT_SYM)) == (VT_CONST|VT_SYM);
```

然后分两条大路：**③ 常量当场转**、**④ 非常量发指令**。

### 2a. 常量当场转（`:2487-2547`）

```c
        if (c) {
            /* 常量：现在就能转换 */
            if (sbt == VT_FLOAT) vtop->c.ld = vtop->c.f;
            else if (sbt == VT_DOUBLE) vtop->c.ld = vtop->c.d;

            if (df) {                        /* 目标浮点 */
                ... 整数→浮点，注意符号扩展和精度 ...
                if (dbt == VT_FLOAT) vtop->c.f = (float)vtop->c.ld;
                else if (dbt == VT_DOUBLE) vtop->c.d = (double)vtop->c.ld;
            } else if (sf && dbt == (VT_LLONG|VT_UNSIGNED)) {
                vtop->c.i = vtop->c.ld;      /* 浮点→无符号 long long */
            } else if (sf && dbt == VT_BOOL) {
                vtop->c.i = (vtop->c.ld != 0);
            } else {
                ... 整数↔整数：截断到目标宽度、按符号位填充 ...
                else if (dbt != VT_LLONG) {
                    uint32_t m = ((dbt & VT_BTYPE) == VT_BYTE ? 0xff :
                                  (dbt & VT_BTYPE) == VT_SHORT ? 0xffff : 0xffffffff);
                    vtop->c.i &= m;          /* 截断到目标宽度 */
                    if (!(dbt & VT_UNSIGNED))
                        vtop->c.i |= -(vtop->c.i & ((m >> 1) + 1));  /* 符号扩展 */
                }
            }
        } else if (p && dbt == VT_BOOL) {
            vtop->r = VT_CONST;
            vtop->c.i = 1;                   /* 符号地址转 bool：恒为真 */
        }
```

**所有编译期能做的转换都做了**：`(char)300` 在编译期就截成 44，
`(int)3.9` 编译期就截成 3。**这就是为什么常量表达式不需要机器码。**

### 2b. 非常量发指令（`:2551-2648`）

```c
        } else {
            if (sf && df) {
                gen_cvt_ftof(dbt);           /* 浮点→浮点：精度转换 */
            } else if (df) {
                gen_cvt_itof1(dbt);          /* 整数→浮点（第 47 篇后端） */
            } else if (sf) {
                if (dbt == VT_BOOL) {
                    vpushi(0); gen_op(TOK_NE);   /* 浮点→bool：和 0 比 */
                } else {
                    ... gen_cvt_ftoi1(dbt); ...  /* 浮点→整数 */
                }
            } else if ((dbt & VT_BTYPE) == VT_LLONG || (dbt & VT_BTYPE) == VT_PTR) {
                if (sbt 是更窄的类型) {
                    gv(RC_INT);
                    /* x86-64：movslq 符号扩展（第 47 篇） */
                }
            } else if (dbt == VT_BOOL) {
                vpushi(0); gen_op(TOK_NE);       /* 转 bool：和 0 比 */
            } else if ((dbt & VT_BTYPE) == VT_BYTE || (dbt & VT_BTYPE) == VT_SHORT) {
                force_charshort_cast(dbt);       /* char/short 截断 */
            }
        }
    } else if ((dbt & VT_BTYPE) == VT_PTR && !(vtop->r & VT_LVAL)) {
        /* 指针之间转换：更新左值字节宽度 */
        vtop->r = (vtop->r & ~VT_LVAL_TYPE)
                  | (lvalue_type(type->ref->type.t) & VT_LVAL_TYPE);
    }
    vtop->type = *type;              /* ★ 最后统一改类型 */
}
```

**转换指令由后端提供**：`gen_cvt_ftof`、`gen_cvt_itof`、`gen_cvt_ftoi`
（x86-64 在 `src/targets/x86_64-gen.c:2074/2116/2179`，第 47 篇）。

---

## 第 3 站：小类型的"延迟转换"（`VT_MUSTCAST`）

为什么 `char`/`short` 的转换要"延迟"？看这个：

```c
char c = x;      /* 存进 c 时要截断成 1 字节 */
int y = c;       /* 读出来又要从 1 字节扩展成 int */
```

如果每次赋值/读取都插入截断和扩展指令，冗余很多。
TCC 的做法：**当把 int 赋给 char 时，先只记一个 `VT_MUSTCAST` 标志，
等真正需要这个值的时候（`gen_cast` 开头）才 `force_charshort_cast`。**

```c
/* src/core/tccgen.c:2463-2469 */
    /* special delayed cast for char/short */
    if (vtop->r & VT_MUSTCAST) {
        vtop->r &= ~VT_MUSTCAST;
        force_charshort_cast(vtop->type.t);
    }
```

`vstore`（第 24 篇）里会看到："优化 char/short 转换"分支设置 `VT_MUSTCAST`。

---

## 第 4 站：`gen_cast` 里的"符号扩展"是什么意思

C 里 `char` 是有符号的（多数平台）。`char c = 200; int i = c;`
`c` 的值是 `-56`（200 的补码），所以 `i` 应该是 `-56` 而不是 `200`。

`gen_cast` 的整数分支用这条公式做符号扩展：

```c
    uint32_t m = (dbt==VT_BYTE ? 0xff : dbt==VT_SHORT ? 0xffff : 0xffffffff);
    vtop->c.i &= m;                                 /* 先截断 */
    if (!(dbt & VT_UNSIGNED))
        vtop->c.i |= -(vtop->c.i & ((m >> 1) + 1)); /* 若最高位是 1，高位全填 1 */
```

`(m >> 1) + 1` 是那个宽度的"最高位掩码"（8 位是 `0x80`，16 位是 `0x8000`）。
若它非零，就取负（算术上等于把高位全填 1）。

---

## 【把 `int y = (char)(x + 1);` 走一遍】

1. `x` 读入，`x+1` 由 `gen_opic`/`gen_opi` 算；
2. `(char)` → `parse_btype` 认出 `char`，`gen_cast(char类型)`：
   - 若 `x+1` 是常量 → 编译期截断成 1 字节再符号扩展；
   - 若非常量 → `force_charshort_cast(VT_BYTE)`：
     有符号走"左移 24 再算术右移 24"，无符号走"与 0xff"；
3. `int y = ...` → `vstore` 写进 `y`。

---

## 【动手小实验】

1. 写 `char c = 200; return c;` 返回多少？（期望 -56 → 退出码 200）
2. `int i = 3.9;` 反汇编看是不是编译期常量 3。
3. `int i = 3.9; double d = i;` 看有没有 `cvtsi2sd` 之类（第 47 篇）。
4. 写 `void *p = (void*)0; int *q = p;` 不会有警告；写 `int *q = 5;` 会有警告。

## 【通关暗号】

```bash
printf 'int main(void){char c=200; return c;}\n' > /tmp/c.c
./tcc -run /tmp/c.c; echo $?
# 期望：200（退出码取低 8 位；c 内部是 -56，但退出码只取低字节）
printf 'int main(void){return (char)300;}\n' > /tmp/d.c
./tcc -run /tmp/d.c; echo $?
# 期望：44（300 截断成 1 字节）
```

## 【常见卡点】

- **`gen_assign_cast` 先检查后转换**，`gen_cast` 只管转换。
- **常量转换在编译期做完**，不产码。
- **`char`/`short` 转换会延迟**（`VT_MUSTCAST`），避免冗余指令。
- **符号扩展**决定 `char 200` 是 -56 还是 200。
- **后续浮点转换指令由后端提供**。

**下一篇**：`24-赋值vstore.md` —— `a = b` 怎么真正写进内存。
