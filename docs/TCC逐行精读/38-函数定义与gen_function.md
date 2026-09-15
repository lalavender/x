# 38 · 函数定义：`gen_function` 的周围

> **一句话**：`gen_function` 本身（第 16 篇讲过骨架）负责"盖房—编体—拆房"。
> 本篇补上它周围的细节：函数符号的发布、`funcname`/`func_vt`/`func_var`/`rsym`
> 这些全局状态、以及"函数声明"和"函数定义"的区别。
>
> 对应源码：`src/core/tccgen.c:7054`（`gen_function`）、`:7239`（`decl0` 看到 `{`）、
> `:5743`（`gfunc_return`）、`:64`（全局状态声明）。

---

## 第 0 站：函数相关的全局状态（`tccgen.c:52-64`）

```c
/* src/core/tccgen.c:52-64（节选）*/
ST_DATA int const_wanted;      /* 是否在常量表达式里 */
ST_DATA int nocode_wanted;     /* 是否禁止生成代码 */
ST_DATA int global_expr;
ST_DATA CType func_vt;         /* ★ 当前函数的返回类型（return 用） */
ST_DATA int func_var;          /* ★ 当前函数是否变参（printf 用） */
ST_DATA int func_vc;
ST_DATA const char *funcname;  /* ★ 当前函数名（__FUNCTION__ 用） */
ST_DATA int last_line_num, last_ind, func_ind;
ST_DATA int g_debug;
ST_DATA CType char_pointer_type, func_old_type, int_type, size_type, ptrdiff_type;
```

这些是"当前正在编译的函数"的状态。**单遍编译一次只编一个函数，所以全局变量够用。**

`ind`（代码当前位置）和 `rsym`（return 跳转链）也在附近：

```c
/* src/core/tccgen.c 附近 */
ST_DATA int ind;    /* 当前 .text 偏移（每发一个字节就 ++） */
ST_DATA int rsym;   /* 收集所有 return 的跳转 */
```

---

## 第 1 站：函数声明 vs 函数定义（`tccgen.c:7208-7286`）

`decl0` 里：

```c
/* src/core/tccgen.c:7208-7217（节选）*/
            if ((type.t & VT_BTYPE) == VT_FUNC) {
                if ((type.t & VT_STATIC) && (l == VT_LOCAL))
                    tcc_error("function without file scope cannot be static");
                sym = type.ref;
                if (sym->f.func_type == FUNC_OLD && l == VT_CONST)
                    decl0(VT_CMP, 0, sym);   /* K&R 老式参数声明 */
            }
```

```c
/* src/core/tccgen.c:7239-7286（节选）*/
            if (tok == '{') {
                if (l != VT_CONST)
                    tcc_error("cannot use local functions");
                if ((type.t & VT_BTYPE) != VT_FUNC)
                    expect("function definition");

                /* 老式参数未写类型 → 补 int */
                sym = type.ref;
                while ((sym = sym->next) != NULL) {
                    if (!(sym->v & ~SYM_FIELD)) expect("identifier");
                    if (sym->type.t == VT_VOID) sym->type = int_type;
                }

                /* extern inline → static inline */
                if ((type.t & (VT_EXTERN | VT_INLINE)) == (VT_EXTERN | VT_INLINE))
                    type.t = (type.t & ~VT_EXTERN) | VT_STATIC;

                /* 发布函数符号 */
                sym = external_global_sym(v, &type, 0);
                type.t &= ~VT_EXTERN;
                patch_storage(sym, &ad, &type);

                if ((type.t & (VT_INLINE | VT_STATIC)) == (VT_INLINE | VT_STATIC)) {
                    ... 存 token 串，延迟编译（第 39 篇）...
                } else {
                    cur_text_section = ad.section ? ad.section : text_section;
                    gen_function(sym);       /* ★ 立刻生成 */
                }
                break;
            }
```

**区分靠"后面是不是 `{`"**：

- `int f(int);`（分号）→ 只是声明，走 `external_sym` 分支，发布一个未定义符号；
- `int f(int){...}` → 定义，先 `external_global_sym` 发布，再 `gen_function`。

`external_global_sym`（`:829`）会复用已有的同名符号（因为声明可能已经出现过）。

---

## 第 2 站：`gen_function` 逐段（再读一遍重点）

第 16 篇贴过全貌，这里只补三处细节。

### 2a. 符号先发布、大小后回填（`:7058/7084`）

```c
/* src/core/tccgen.c:7056-7059 */
    nocode_wanted = 0;
    ind = cur_text_section->data_offset;
    /* NOTE: we patch the symbol size later */
    put_extern_sym(sym, cur_text_section, ind, 0);   /* ★ size 先写 0 */
```

```c
/* src/core/tccgen.c:7083-7084 */
    /* patch symbol size */
    elfsym(sym)->st_size = ind - func_ind;   /* ★ 编完回填函数大小 */
```

**函数大小只有在编完之后才知道**，所以先发布 `size=0`，最后回填。

### 2b. `rsym` 收集 return 跳转（`:7072/7075`）

```c
/* src/core/tccgen.c:7072-7076 */
    rsym = 0;
    block(NULL, NULL, 0);       /* 函数体：每个 return 会 rsym = gjmp(rsym) */
    nocode_wanted = 0;
    gsym(rsym);                 /* ★ 回填所有 return 到"函数末尾" */
    gfunc_epilog();             /* 发 leave; ret */
```

`return`（第 26 篇）生成"跳到函数末尾"，全部挂在 `rsym` 链上，
这里 `gsym(rsym)` 一次回填。**`gfunc_epilog` 发真正的 `ret`。**

### 2c. 局部符号 + 标签清理（`:7078-7081`）

```c
/* src/core/tccgen.c:7078-7081 */
    label_pop(&global_label_stack, NULL, 0);   /* 检查标签 */
    local_scope = 0;
    sym_pop(&local_stack, NULL, 0);            /* ★ 清空本函数所有局部符号 */
```

**函数编完，`local_stack` 整个清空**——这是单遍编译省内存的关键。
（`gen_function` 开头 `sym_push2(&local_stack, SYM_FIELD, 0, 0)` 压了个哑符号当哨兵。）

---

## 第 3 站：`return` 的落地 —— `gfunc_return`（`tccgen.c:5743`）

`return expr;` 里 `expr` 算完后要放进"返回值寄存器"：

```c
/* src/core/tccgen.c:5743-5806（节选）*/
static void gfunc_return(CType *func_type)
{
    if ((func_type->t & VT_BTYPE) == VT_STRUCT) {
        /* 返回结构体：可能写进隐藏指针，或打包进寄存器 */
        ...
    } else if (is_float(func_type->t)) {
        gv(rc_fret(func_type->t));   /* ★ 浮点：放进 xmm0 / st0 */
    } else {
        gv(RC_IRET);                 /* ★ 整数/指针：放进 rax */
    }
    vtop--; /* 不用 vpop，避免 x86 清浮点栈 */
}
```

**`RC_IRET`/`RC_FRET` 是"返回值寄存器类别"**，由后端定义
（x86-64 是 `rax` / `xmm0`）。`gv` 把值装进那个寄存器。

`func_vt`（当前函数返回类型）是 `decl` 里在编函数体前设好的：

```c
/* 概念上（在 block 处理 return 时用到）*/
    gen_assign_cast(&func_vt);   /* 把 return 的值转成函数返回类型 */
    if ((func_vt.t & VT_BTYPE) == VT_VOID)
        vtop--;
    else
        gfunc_return(&func_vt);
```

**`func_vt` 和 `func_var` 在 `gen_function` 前后设置/清零**（`:7089`）。

---

## 第 4 站：完整生命周期

```
decl0 看到 "int f(int){..."
  │
  ├─ external_global_sym 发布符号（st_shndx 待定）
  ├─ gen_function(sym):
  │    ├─ ind = .text 当前偏移
  │    ├─ put_extern_sym(sym, .text, ind, 0)     ← st_value 定，st_size=0
  │    ├─ funcname = "f"; func_vt = 返回类型; func_var = 变参?
  │    ├─ sym_push2(local_stack, 哑符号); local_scope=1
  │    ├─ gfunc_prolog(&sym->type)               ← 盖栈帧、存参数
  │    ├─ block(NULL,NULL,0)                     ← 编函数体
  │    ├─ gsym(rsym); gfunc_epilog()             ← 回填 return、leave;ret
  │    ├─ label_pop; sym_pop(local_stack)        ← 清局部符号、查标签
  │    ├─ elfsym(sym)->st_size = ind - func_ind  ← 回填大小
  │    └─ 清零 funcname/func_vt...
  └─ 返回 decl0 循环
```

---

## 【把 `int add(int a,int b){return a+b;}` 走一遍】

| 步骤 | 动作 |
|---|---|
| 1 | `parse_btype`=int，`type_decl` 得到函数类型 + 名字 `add` |
| 2 | 看到 `{` → `external_global_sym(add, …)` 发布符号 |
| 3 | `gen_function(add)`：`put_extern_sym` 记下 `.text` 偏移 |
| 4 | `gfunc_prolog`：`push rbp; mov rbp,rsp; mov [rbp-4],edi; mov [rbp-8],esi` |
| 5 | `block`：`return a+b` → 取 `a`、`b`，`add`，`gv(RC_IRET)` 放进 `eax`，`gjmp(rsym)` |
| 6 | `gsym(rsym)` 回填到末尾 |
| 7 | `gfunc_epilog`：`leave; ret` |
| 8 | `st_size = 末尾 - 起点` |

---

## 【动手小实验】

1. `int f(){return 1;} int g(){return 2;}` 编译到 `.o`，`nm -S` 看两个函数的大小。
2. 在 `gen_function` 的 `put_extern_sym` 前后打印 `ind`，看两个函数在 `.text` 里紧挨着。
3. 写 `int f(); int f(){return 1;}`（先声明后定义），确认不报重定义。
4. 写 `__FUNCTION__`，看 `funcname` 怎么被用。

## 【通关暗号】

```bash
printf 'int f(int a){return a+1;}\nint main(void){return f(4);}\n' > /tmp/f.c
./tcc -c /tmp/f.c -o /tmp/f.o && nm -S /tmp/f.o 2>/dev/null | grep -E ' f$| main$'
# 期望：f 和 main 都有大小（非 0）
```

## 【常见卡点】

- **函数符号先发布 size=0，编完回填**。
- **`rsym` 收集所有 return 跳转**，末尾统一回填。
- **`func_vt`/`func_var`/`funcname` 是"当前函数"的全局状态**。
- **函数编完 `sym_pop(local_stack)` 清空局部符号**。
- **声明（分号）只发布未定义符号；定义（`{`）才生成代码**。

**下一篇**：`39-inline与延迟编译.md`。
