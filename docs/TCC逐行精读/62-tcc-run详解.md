# 62 · `tcc -run` 详解：`tcc_relocate` 与内存管理

> **一句话**：第 55 篇看了"布局与执行"，本篇补上内存管理和 `tcc_relocate` 的
> 三种调用方式，以及 SELinux 系统下"一页两映射"的做法。
>
> 对应源码：`src/core/tccrun.c:59`（`tcc_relocate`）、`:96`（`tcc_run_free`）、
> `:116`（`tcc_run`，第 55 篇）、`:179`（`tcc_relocate_ex`，第 55 篇）、
> `src/core/libtcc.c`（`tcc_new`/`tcc_delete` 里的 `runtime_mem` 生命周期）。

---

## 第 0 站：`tcc_relocate` 的三种模式（`tccrun.c:59`）

```c
/* src/core/tccrun.c:59-94 */
LIBTCCAPI int tcc_relocate(TCCState *s1, void *ptr)
{
    int size;
    addr_t ptr_diff = 0;

    if (TCC_RELOCATE_AUTO != ptr)
        return tcc_relocate_ex(s1, ptr, 0);      /* 模式 B/C：调用者给内存 */

    size = tcc_relocate_ex(s1, NULL, 0);          /* 模式 A：先算大小 */
    if (size < 0)
        return -1;
    ...
    ptr = tcc_malloc(size);                        /* 自己分配 */
    tcc_relocate_ex(s1, ptr, ptr_diff);            /* 真正布局 */
    dynarray_add(&s1->runtime_mem, &s1->nb_runtime_mem, ptr);   /* 记住以便释放 */
    return 0;
}
```

`libtcc.h` 里对参数 `ptr` 的说明：

| `ptr` 的值 | 行为 |
|---|---|
| `TCC_RELOCATE_AUTO` (= 1) | TCC 自己分配内存、自己管理 |
| `NULL` | 只返回"需要多少字节"，不做布局 |
| 一个真实地址 | 把代码布局到调用者给的内存 |

**两种典型用法**：

```c
/* 用法一：简单，用 AUTO */
tcc_relocate(s, TCC_RELOCATE_AUTO);
void *p = tcc_get_symbol(s, "f");

/* 用法二：自己控制内存（能知道大小、能放进特殊内存区） */
int size = tcc_relocate(s, NULL);       /* 问大小 */
void *mem = my_alloc(size);             /* 自己分配 */
tcc_relocate(s, mem);                   /* 布局进去 */
```

---

## 第 1 站：内存怎么释放 —— `tcc_run_free`（`:96`）

```c
/* src/core/tccrun.c:96-113 */
ST_FUNC void tcc_run_free(TCCState *s1)
{
    int i;
    for (i = 0; i < s1->nb_runtime_mem; ++i) {
#ifdef HAVE_SELINUX
        unsigned size = (unsigned)(addr_t)s1->runtime_mem[i++];
        munmap(s1->runtime_mem[i++], size);
        munmap(s1->runtime_mem[i], size);
#else
#ifdef _WIN64
        win64_del_function_table(*(void**)s1->runtime_mem[i]);
#endif
        tcc_free(s1->runtime_mem[i]);
#endif
    }
    tcc_free(s1->runtime_mem);
}
```

`runtime_mem` 是一组"TCC 为运行代码分配的内存"，编译结束时统一释放。
`tcc_delete`（`libtcc.c`）会调它。

---

## 第 2 站：SELinux 与"一页两映射"（`:71-87`）

普通系统上，`mprotect(PROT_WRITE|PROT_EXEC)` 可能被安全策略禁止（W^X 政策）。
TCC 在 `HAVE_SELINUX` 时用了一招：

```c
/* src/core/tccrun.c:71-87（节选）*/
#ifdef HAVE_SELINUX
{
    void *prx;
    char tmpfname[] = "/tmp/.tccrunXXXXXX";
    int fd = mkstemp(tmpfname);
    unlink(tmpfname);
    ftruncate(fd, size);

    /* ★ 同一个文件映射两次：一次可写，一次可执行 */
    ptr = mmap(NULL, size, PROT_READ|PROT_WRITE, MAP_SHARED, fd, 0);
    prx = mmap(NULL, size, PROT_READ|PROT_EXEC,  MAP_SHARED, fd, 0);
    ...
    ptr_diff = (char*)prx - (char*)ptr;   /* 两个映射的地址差 */
}
#endif
```

- **`ptr`**：可写映射，TCC 往这里写代码/重定位；
- **`prx`**：可执行映射，执行时用；
- 两者指向同一个临时文件，所以一改都改；
- 代码里凡是"执行地址"都加 `ptr_diff`，于是看到的是可执行映射。

**这是绕过 W^X 的经典做法。** 普通情况直接用 `malloc` + `mprotect`
（第 55 篇 `set_pages_executable`）。

---

## 第 3 站：`tcc_run` 的完整链条（`:116`）

```c
/* src/core/tccrun.c:116-168（节选）*/
LIBTCCAPI int tcc_run(TCCState *s1, int argc, char **argv)
{
    int (*prog_main)(int, char **);

    s1->runtime_main = "main";
    if ((s1->dflag & 16) && !find_elf_sym(s1->symtab, s1->runtime_main))
        return 0;
    if (tcc_relocate(s1, TCC_RELOCATE_AUTO) < 0)   /* ★ 布局到内存 */
        return -1;
    prog_main = tcc_get_symbol_err(s1, s1->runtime_main);   /* 查 main 地址 */

#ifdef CONFIG_TCC_BACKTRACE
    if (s1->do_debug) {
        set_exception_handler();                   /* ★ 装崩溃处理（第 63 篇）*/
        rt_prog_main = prog_main;
    }
#endif

    errno = 0;
    ... -b 边界检查初始化 ...
    return (*prog_main)(argc, argv);               /* ★ 执行 */
}
```

注意：

- `s1->dflag & 16`（`-dt` 调试选项）：如果没有 `main` 就返回 0；
- `do_debug`（`-g`）时 `set_exception_handler` 装信号处理器，崩溃能报源码行（第 63 篇）；
- 边界检查（`-b`）会先初始化运行时。

---

## 第 4 站：`runtime_main` 与 libtcc 自定义入口

`tcc_run` 固定找 `main`。但 libtcc 用户可以：
1. `tcc_relocate` 之后用 `tcc_get_symbol` 拿任意函数指针自己调；
2. 不调 `tcc_run`，完全自己控制。

```c
/* libtcc 用户代码示例 */
tcc_compile_string(s, "int add(int a,int b){return a+b;}");
tcc_relocate(s, TCC_RELOCATE_AUTO);
int (*add)(int,int) = tcc_get_symbol(s, "add");
printf("%d\n", add(3, 4));      /* 7 */
```

**这就是"把编译器当库用"的核心。**

---

## 【内存生命周期全景】

```
tcc_new()
   │
tcc_add_file / tcc_compile_string   ├─ 编译：Section 在 TCCState 里
   │
tcc_relocate(TCC_RELOCATE_AUTO)     ├─ 分配 memory，布局、重定位
   │                                 ├─ runtime_mem[] 记住这块内存
tcc_get_symbol("f")                 ├─ 拿到函数指针
(*f)()                              ├─ 执行
   │
tcc_delete()                        └─ tcc_run_free 释放 runtime_mem
```

---

## 【动手小实验】

1. 用 libtcc 写一个小程序：编译一段字符串、`tcc_relocate`、调函数、`tcc_delete`。
2. 用 `tcc_relocate(s, NULL)` 先问大小，打印出来，再自己 `malloc` 布局。
3. 在 `tcc_run_free` 里加打印，看释放了几块内存。
4. 如果有 SELinux 环境，试 `-run`（可能报 `mprotect failed`，需要配置）。

## 【通关暗号】

```bash
printf 'int main(void){return 42;}\n' > /tmp/r.c
./tcc -run /tmp/r.c; echo $?
# 期望：42
```

## 【常见卡点】

- **`tcc_relocate` 三种模式**：AUTO / NULL / 真实地址。
- **`runtime_mem` 记录要释放的内存**。
- **SELinux 用"一页两映射"绕过 W^X**。
- **`tcc_run` 就是"relocate + 找 main + 调用"**。
- **libtcc 用户可以自己拿函数指针，不必用 `tcc_run`**。

**下一篇**：`63-崩溃回溯.md`。
