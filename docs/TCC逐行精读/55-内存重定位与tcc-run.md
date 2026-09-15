# 55 · 内存重定位与 `tcc -run`：不落盘直接跑

> **一句话**：`-run` 不写 ELF 文件，而是向系统申请一块可执行内存，
> 把节按布局复制进去、把重定位填好、把内存页设成可读可写可执行，
> 然后直接调用 `main` 的函数指针。
>
> 对应源码：`src/core/tccrun.c:116`（`tcc_run`）、`:179`（`tcc_relocate_ex`）、
> `:280`（`set_pages_executable`）、`src/core/tccelf.c:779`（`relocate_syms`）。

---

## 第 0 站：`tcc_run`（`tccrun.c:116`）

```c
/* src/core/tccrun.c:115-125（节选）*/
LIBTCCAPI int tcc_run(TCCState *s1, int argc, char **argv)
{
    int (*prog_main)(int, char **);

    s1->runtime_main = "main";
    ...
    if (tcc_relocate(s1, TCC_RELOCATE_AUTO) < 0)   /* ★ 内存重定位 */
        return -1;
    prog_main = tcc_get_symbol_err(s1, s1->runtime_main);   /* 找到 main 地址 */
    ...
    return (*prog_main)(argc, argv);               /* ★ 直接调用！ */
}
```

**`main` 就是从符号表查出来的一个函数指针**，`(*prog_main)(argc, argv)` 直接调用。
不需要操作系统加载器，也不需要 `exec`。

第 01 篇说的"内存执行"就是这几行。

---

## 第 1 站：内存重定位 —— `tcc_relocate_ex`（`tccrun.c:179`）

它分两趟跑（`ptr == NULL` 时只算大小，非 NULL 时真正布局）：

```c
/* src/core/tccrun.c:179-196（节选）*/
static int tcc_relocate_ex(TCCState *s1, void *ptr, addr_t ptr_diff)
{
    ...
    if (NULL == ptr) {
        /* 第一趟：准备工作 */
        s1->nb_errors = 0;
        tcc_add_runtime(s1);
        resolve_common_syms(s1);
        build_got_entries(s1);
        if (s1->nb_errors) return -1;
    }

    offset = 0, mem = (addr_t)ptr;
    fill = -mem & RUN_SECTION_ALIGNMENT;      /* 对齐填充 */
    for (k = 0; k < 2; ++k) {                 /* ① 先数据节，再代码节 */
        for(i = 1; i < s1->nb_sections; i++) {
            s = s1->sections[i];
            if (0 == (s->sh_flags & SHF_ALLOC)) continue;   /* 不加载的跳过 */
            if (k != !(s->sh_flags & SHF_EXECINSTR)) continue;
            offset += fill;
            if (!mem)
                s->sh_addr = 0;
            else if (s->sh_flags & SHF_EXECINSTR)
                s->sh_addr = mem + offset + ptr_diff;       /* 代码段 */
            else
                s->sh_addr = mem + offset;                   /* 数据段 */
            offset += s->data_offset;
            fill = -(mem + offset) & 15;                     /* 16 字节对齐 */
        }
    }

    /* ② 符号重定位 */
    relocate_syms(s1, s1->symtab, 1);
    if (s1->nb_errors) return -1;

    if (0 == mem)
        return offset + RUN_SECTION_ALIGNMENT;   /* 第一趟：返回需要多少内存 */

    /* ③ 应用节内重定位（第 53 篇） */
    for(i = 1; i < s1->nb_sections; i++) {
        s = s1->sections[i];
        if (s->reloc) relocate_section(s1, s);
    }
    relocate_plt(s1);

    /* ④ 把节数据复制到目标内存 */
    for(i = 1; i < s1->nb_sections; i++) {
        s = s1->sections[i];
        if (0 == (s->sh_flags & SHF_ALLOC)) continue;
        length = s->data_offset;
        ptr = (void*)s->sh_addr;
        if (s->sh_flags & SHF_EXECINSTR)
            ptr = (char*)ptr - ptr_diff;
        if (NULL == s->data || s->sh_type == SHT_NOBITS)
            memset(ptr, 0, length);              /* .bss 清零 */
        else
            memcpy(ptr, s->data, length);        /* 复制数据 */
        /* ⑤ 代码段设为可执行 */
        if (s->sh_flags & SHF_EXECINSTR)
            set_pages_executable((char*)ptr + ptr_diff, length);
    }
    ...
    return 0;
}
```

**关键点**：

1. **"先算大小、再真正布局"两趟**：第一趟 `mem=0` 只计算需要多少内存并返回；
   调用者分配好后再调一次。
2. **节按 `SHF_ALLOC` 过滤**：`.symtab`/`.strtab` 不加载到内存。
3. **`sh_addr` 直接写成真实内存地址**（不是虚拟地址）。
4. **`relocate_syms` 用 `dlsym` 解析外部符号**（下一站）。
5. **代码段要 `set_pages_executable`**，否则调用会段错误。

---

## 第 2 站：`relocate_syms` 对外部符号的处理（`tccelf.c:779`）

```c
/* src/core/tccelf.c:779-821（节选）*/
ST_FUNC void relocate_syms(TCCState *s1, Section *symtab, int do_resolve)
{
    for_each_elem(symtab, 1, sym, ElfW(Sym)) {
        sh_num = sym->st_shndx;
        if (sh_num == SHN_UNDEF) {              /* 未定义符号 */
            name = ...;
            if (do_resolve) {
                void *addr = dlsym(RTLD_DEFAULT, name);   /* ★ 问操作系统 */
                if (addr) { sym->st_value = (addr_t)addr; goto found; }
            } else if (s1->dynsym && find_elf_sym(s1->dynsym, name))
                goto found;
            ...
            if (sym_bind == STB_WEAK) sym->st_value = 0;
            else tcc_error_noabort("undefined symbol '%s'", name);
        } else if (sh_num < SHN_LORESERVE) {
            sym->st_value += s1->sections[sym->sh_indx]->sh_addr;   /* 加节基址 */
        }
    found: ;
    }
}
```

**`dlsym(RTLD_DEFAULT, name)`**：内存执行时，`printf`、`malloc` 这些符号
直接从**当前进程**的动态符号表里找（因为 TCC 自己就是链接了 libc 的程序）。
这比写 ELF 再让加载器解析简单得多。

---

## 第 3 站：把页设成可执行 —— `set_pages_executable`（`tccrun.c:280`）

```c
/* src/core/tccrun.c:280-302（节选）*/
static void set_pages_executable(void *ptr, unsigned long length)
{
#ifdef _WIN32
    VirtualProtect(ptr, length, PAGE_EXECUTE_READWRITE, &old_protect);
#else
    start = (addr_t)ptr & ~(PAGESIZE - 1);       /* 页对齐起点 */
    end = (addr_t)ptr + length;
    end = (end + PAGESIZE - 1) & ~(PAGESIZE - 1);/* 页对齐终点 */
    if (mprotect((void *)start, end - start, PROT_READ | PROT_WRITE | PROT_EXEC))
        tcc_error("mprotect failed: ...");
# if defined TCC_TARGET_ARM || defined TCC_TARGET_ARM64
    __clear_cache(ptr, (char *)ptr + length);    /* ARM 要清指令缓存 */
#endif
#endif
}
```

- Linux/mac：`mprotect(PROT_READ|PROT_WRITE|PROT_EXEC)`；
- Windows：`VirtualProtect(PAGE_EXECUTE_READWRITE)`；
- ARM/ARM64 还要 `__clear_cache`（因为指令/数据缓存分离）。

**注意 `PROT_WRITE | PROT_EXEC` 同时开**：因为重定位可能还要写这段内存。
有些安全加固的系统（SELinux/W^X）不允许，所以 TCC 的 `-run` 需要额外配置。

---

## 第 4 站：内存分配

调用链（`tcc_relocate` 在 `libtcc.c`）：

```c
/* 概念 */
int tcc_relocate(TCCState *s1, void *ptr) {
    if (ptr == TCC_RELOCATE_AUTO) {
        size = tcc_relocate_ex(s1, NULL, 0);          /* 第一趟：算大小 */
        ptr = tcc_malloc(size);                        /* 分配内存 */
        tcc_relocate_ex(s1, ptr, 0);                   /* 第二趟：布局 */
    } else {
        ...
    }
}
```

**一次 `malloc` 一块连续内存，所有节排在里面。** 简单粗暴，但足够
（TCC 编译的程序通常不大）。

---

## 【把 `tcc -run t.c` 走一遍】

| 步骤 | 说明 |
|---|---|
| 1 | `main`（tcc.c）解析到 `-run`，`output_type = TCC_OUTPUT_MEMORY` |
| 2 | `tcc_add_file(t.c)` 编译，机器码进 `.text` |
| 3 | `tcc_run(s, argc, argv)` |
| 4 | `tcc_relocate_ex(NULL)` 算需要多少内存 |
| 5 | `malloc` 一块，`tcc_relocate_ex(ptr)` 布局、重定位、设可执行 |
| 6 | `relocate_syms` 用 `dlsym` 解析 `printf` 等 |
| 7 | `prog_main = tcc_get_symbol_err("main")` |
| 8 | `(*prog_main)(argc, argv)` —— 你的程序跑起来了 |

---

## 【动手小实验】

1. `./tcc -run t.c` 运行，和 `./tcc t.c -o t && ./t` 对比输出。
2. 写一个用 `printf` 的 `-run` 程序，确认 libc 符号被 `dlsym` 解析。
3. 在 `tcc_run` 里加打印，看 `prog_main` 的地址。
4. 在 `set_pages_executable` 里加打印，确认 `mprotect` 生效。

## 【通关暗号】

```bash
printf '#include <stdio.h>\nint main(void){printf("hello from memory\\n"); return 5;}\n' > /tmp/run.c
./tcc -run /tmp/run.c; echo "exit=$?"
# 期望：打印 hello from memory，exit=5
```

## 【常见卡点】

- **`-run` 用 `dlsym` 解析外部符号**，不写 ELF。
- **两趟布局**：先算大小，再复制。
- **代码页要 `mprotect` 设可执行**；ARM 还要清缓存。
- **所有节排在一块连续 `malloc` 内存里**。
- **`main` 就是函数指针**，直接调用。

**下一篇**：`56-读目标文件与库.md`。
