# 35 · `typedef` 与存储类：`static` / `extern` / `inline`

> **一句话**：`typedef` 不是新东西，它就是一个带 `VT_TYPEDEF` 标志的变量；
> `static`/`extern`/`inline` 是 `CType.t` 里的几个 bit，决定符号怎么登记、代码放哪。
>
> 对应源码：`src/core/tccgen.c:7304`（`decl0` 里的 typedef）、
> `:4179`（`parse_btype` 里识别 typedef）、`:926`（`external_sym`）、
> `:829`（`external_global_sym`）、`:897`（`patch_storage`）、`:305`（`update_storage`）。

---

## 第 0 站：四个 bit（`tcc.h:879-882`）

```c
/* src/core/tcc.h:878-882 */
#define VT_EXTERN  0x00001000  /* extern */
#define VT_STATIC  0x00002000  /* static */
#define VT_TYPEDEF 0x00004000  /* typedef */
#define VT_INLINE  0x00008000  /* inline */
```

`parse_btype`（第 32 篇）看到这些关键字就置位。**存储类不是单独的字段，就是 bit。**

`VT_STORAGE` 是它们的集合：

```c
/* src/core/tcc.h:899 */
#define VT_STORAGE (VT_EXTERN | VT_STATIC | VT_TYPEDEF | VT_INLINE)
```

---

## 第 1 站：`typedef`（`tccgen.c:7304`）

`decl0` 里 `type.t & VT_TYPEDEF` 时：

```c
/* src/core/tccgen.c:7304-7318 */
                } else if (type.t & VT_TYPEDEF) {
                    /* 保存被 typedef 的类型 */
                    sym = sym_find(v);
                    if (sym && sym->sym_scope == local_scope) {
                        /* 同作用域重复 typedef 要兼容 */
                        if (!is_compatible_types(&sym->type, &type)
                            || !(sym->type.t & VT_TYPEDEF))
                            tcc_error("incompatible redefinition of '%s'", ...);
                        sym->type = type;
                    } else {
                        sym = sym_push(v, &type, 0, 0);   /* ★ 就是一个普通变量卡 */
                    }
                    sym->a = ad.a;
                    sym->f = ad.f;
                }
```

**typedef 名 = 一个变量 `Sym`，带 `VT_TYPEDEF` 标志，类型存在 `Sym.type`。**

识别时（`parse_btype:4179`）：

```c
/* src/core/tccgen.c:4182-4191（节选）*/
            s = sym_find(tok);        /* 在变量抽屉找 */
            if (!s || !(s->type.t & VT_TYPEDEF))
                goto the_end;         /* 不是 typedef，结束 */
            t &= ~(VT_BTYPE|VT_LONG);
            u = t & ~(VT_CONSTANT | VT_VOLATILE), t ^= u;
            type->t = (s->type.t & ~VT_TYPEDEF) | u;   /* ★ 去掉 TYPEDEF 标志 */
            type->ref = s->type.ref;
```

**所以 `typedef` 的实现就两句话**：存一个带标志的变量；用的时候查出来去掉标志。

---

## 第 2 站：`extern`（`tccgen.c:7332`）

`decl0` 判断"这是不是外部声明"：

```c
/* src/core/tccgen.c:7332-7341（节选）*/
                    if (((type.t & VT_EXTERN) && (!has_init || l != VT_CONST)) ||
                        ((type.t & VT_BTYPE) == VT_FUNC) ||
                        ((type.t & VT_ARRAY) && (type.t & VT_STATIC) &&
                         !has_init && l == VT_CONST && type.ref->c < 0)) {
                        /* 外部变量或函数 */
                        type.t |= VT_EXTERN;
                        sym = external_sym(v, &type, r, &ad);   /* ★ 登记外部符号 */
                        ...
```

`external_sym`（`:926`）：

```c
/* src/core/tccgen.c:925-945（节选）*/
static Sym *external_sym(int v, CType *type, int r, AttributeDef *ad)
{
    Sym *s;
    s = sym_find(v);
    if (!s) {
        /* 没登记过：造一个"前向引用" */
        s = sym_push(v, type, r | VT_CONST | VT_SYM, 0);
        s->type.t |= VT_EXTERN;
        s->a = ad->a;
        s->sym_scope = 0;
    } else {
        ...
        patch_storage(s, ad, type);       /* 合并属性 */
    }
    return s;
}
```

**`extern int x;` 只登记符号，不分配空间。** 符号的地址（`st_shndx = SHN_UNDEF`）
留给链接器解决（第 59 篇）。

`external_global_sym`（`:829`）是给"函数调用、内置符号"用的版本。

---

## 第 3 站：`static`（`tccgen.c:7355`）

```c
/* src/core/tccgen.c:7354-7364（节选）*/
                    } else {
                        if (type.t & VT_STATIC)
                            r |= VT_CONST;      /* static → 有确定地址 */
                        else
                            r |= l;             /* 普通全局：r = VT_CONST；局部：VT_LOCAL */
                        if (has_init)
                            next();
                        else if (l == VT_CONST)
                            /* 未初始化的全局变量可以覆盖（tentative definition） */
                            type.t |= VT_EXTERN;
                        decl_initializer_alloc(&type, &ad, r, has_init, v, l);
                    }
```

`static` 的作用在符号层面（第 37 篇 `update_storage`）：
`VT_STATIC` → ELF 符号绑定 `STB_LOCAL`（别的 `.o` 看不到）。

**局部 `static`**：`l == VT_LOCAL` 但 `type.t & VT_STATIC`，
于是 `r |= VT_CONST`，即在 `.data`/`.bss` 分配（不是栈），
但作用域仍限于函数内。

---

## 第 4 站：`inline`（`tccgen.c:7264`）

```c
/* src/core/tccgen.c:7264-7285（节选）*/
                /* static inline 函数先记录成"宏"，用到才编 */
                if ((type.t & (VT_INLINE | VT_STATIC)) ==
                    (VT_INLINE | VT_STATIC)) {
                    struct InlineFunc *fn;
                    const char *filename;
                    filename = file ? file->filename : "";
                    fn = tcc_malloc(sizeof *fn + strlen(filename));
                    strcpy(fn->filename, filename);
                    fn->sym = sym;
                    skip_or_save_block(&fn->func_str);   /* ★ 把函数体存成 token 串 */
                    dynarray_add(&tcc_state->inline_fns,
                                 &tcc_state->nb_inline_fns, fn);
                } else {
                    /* 普通函数：立刻生成 */
                    cur_text_section = ad.section ? ad.section : text_section;
                    gen_function(sym);
                }
```

**`static inline` 的函数体不立刻编译**，而是用 `skip_or_save_block`
存成一串 token（第 09 篇的录音带），等文件末尾 `gen_inline_functions`
看它有没有被引用，被引用才编（第 39 篇）。

**为什么？** 头文件里大量 `static inline`，如果每个都生成代码，可执行文件会膨胀；
只有在某个 `.c` 里真正用到了才需要它的代码。

---

## 第 5 站：属性合并 —— `patch_storage`（`:897`）

同一个符号可能被声明多次（`extern int x; int x=5;`），属性要合并：

```c
/* src/core/tccgen.c:896-923（节选）*/
static void patch_storage(Sym *sym, AttributeDef *ad, CType *type)
{
    if (type)
        patch_type(sym, type);          /* 合并类型（取更完整的） */
    ...
    sym->a.weak |= ad->a.weak;
    if (ad->a.visibility) { ... 取更严格的可见性 ... }
    if (ad->a.aligned)
        sym->a.aligned = ad->a.aligned;
    if (ad->asm_label)
        sym->asm_label = ad->asm_label;
    update_storage(sym);                /* ★ 更新 ELF 符号的属性 */
}
```

`update_storage`（`:292`）把 `static`/`weak` 映射成 ELF 的 `STB_LOCAL/WEAK/GLOBAL`：

```c
/* src/core/tccgen.c:305-314（节选）*/
    if (sym->type.t & VT_STATIC)
        sym_bind = STB_LOCAL;
    else if (sym->a.weak)
        sym_bind = STB_WEAK;
    else
        sym_bind = STB_GLOBAL;
    ...
    esym->st_info = ELFW(ST_INFO)(sym_bind, ELFW(ST_TYPE)(esym->st_info));
```

---

## 第 6 站：一张表总结

| 声明 | 空间分配 | 符号可见性 | 特殊处理 |
|---|---|---|---|
| `int x;`（全局） | `.bss`（或 common） | 全局 | tentative definition |
| `int x = 5;` | `.data` | 全局 | |
| `static int x;` | `.bss` | 局部（`STB_LOCAL`） | |
| `extern int x;` | 不分配 | 未定义（链接器解决） | |
| `int x;`（局部） | 栈帧 | — | |
| `static int x;`（局部） | `.bss`/`.data` | 局部 | 但作用域仅函数内 |
| `static inline f(){}` | 用到才生成 | 局部 | 存 token 串，延迟编译 |
| `inline f(){}` | 立刻生成 | 全局 | |
| `typedef int T;` | 不分配 | — | 带 `VT_TYPEDEF` 的变量卡 |

---

## 【动手小实验】

1. 写 `static int x=1; int y=2;`，编译到 `.o`，`nm` 看 `x` 是小写（local）、`y` 是大写（global）。
2. 写 `extern int x; int main(){return x;}`，`nm` 看 `x` 是未定义（`U`）。
3. 写头文件里 `static inline int f(){return 1;}` 但不用它，`nm` 看有没有 `f`（应该没有）。
4. 写 `typedef int T; T x;` 验证工作。

## 【通关暗号】

```bash
printf 'static int x=1; int y=2; int main(void){return x+y;}\n' > /tmp/s.c
./tcc -c /tmp/s.c -o /tmp/s.o && nm /tmp/s.o 2>/dev/null | grep -E ' x| y'
# 期望：x 是小写 t/d（local），y 是大写 D/B（global）
```

## 【常见卡点】

- **typedef 是变量卡 + 标志**，没有独立的符号空间。
- **`extern` 只登记不分配**，地址留给链接器。
- **局部 `static` 存在数据段但作用域在函数内**。
- **`static inline` 延迟编译**（存 token 串）。
- **存储类就是 `CType.t` 的 bit**。

**下一篇**：`36-初始化decl_initializer.md`。
