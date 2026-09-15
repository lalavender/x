# 54 · 写出 ELF 文件：`elf_output_file`

> **一句话**：所有节都在内存里准备好、符号和重定位都处理好之后，
> `elf_output_file` 负责"布局（定地址）→ 重定位 → 写文件头/程序头/节头 → 落盘"。
>
> 对应源码：`src/core/tccelf.c:2233`（`tcc_output_file` 分派）、
> `:2060`（`elf_output_file`）、`:1563`（`layout_sections` 定地址）、
> `:1860`（`tcc_output_elf` 写内容）、`:1977`（`tcc_write_elf_file`）、
> `src/formats/elf.h`（ELF 结构定义）。

---

## 第 0 站：出口分派（`tccelf.c:2233`）

```c
/* src/core/tccelf.c:2233-2243 */
LIBTCCAPI int tcc_output_file(TCCState *s, const char *filename)
{
    int ret;
#ifdef TCC_TARGET_PE
    if (s->output_type != TCC_OUTPUT_OBJ) {
        ret = pe_output_file(s, filename);    /* Windows → PE */
    } else
#endif
        ret = elf_output_file(s, filename);   /* 其它 → ELF */
    return ret;
}
```

第 01 篇的总流水线出口就是这里。

---

## 第 1 站：`elf_output_file` 全景（`tccelf.c:2060`）

```c
/* src/core/tccelf.c:2060-2130（节选）*/
static int elf_output_file(TCCState *s1, const char *filename)
{
    int i, ret, phnum, shnum, file_type, file_offset, *sec_order;
    ...
    file_type = s1->output_type;

    if (file_type != TCC_OUTPUT_OBJ) {
        /* 链接：加入运行时库（libc、libgcc…） */
        tcc_add_runtime(s1);
        resolve_common_syms(s1);             /* ① 解决 common 符号 */

        if (!s1->static_link) {
            if (file_type == TCC_OUTPUT_EXE) {
                /* 可执行文件：加 .interp（指定动态加载器） */
                interp = new_section(s1, ".interp", SHT_PROGBITS, SHF_ALLOC);
                strcpy(section_ptr_add(interp, ...), elfint);
            }
            /* 动态符号表 */
            s1->dynsym = new_symtab(s1, ".dynsym", SHT_DYNSYM, SHF_ALLOC, ...);
            dynamic = new_section(s1, ".dynamic", SHT_DYNAMIC, ...);
            build_got(s1);                   /* 建 GOT 表 */
            bind_exe_dynsyms(s1) / export_global_syms(s1);  /* ② 绑定动态符号 */
        }
        build_got_entries(s1);               /* ③ 为需要的符号建 GOT/PLT */
    }

    /* 节名表 */
    strsec = new_section(s1, ".shstrtab", SHT_STRTAB, 0);
    put_elf_str(strsec, "");

    /* ① 分配节名字符串 */
    textrel = alloc_sec_names(s1, file_type, strsec);

    if (dynamic) {
        /* 记录需要的动态库、rpath、soname */
        for (i = 0; i < s1->nb_loaded_dlls; i++)
            put_dt(dynamic, DT_NEEDED, put_elf_str(dynstr, dllref->name));
        ...
        fill_dynamic(s1, &dyninf);
    }

    /* ② 确定程序头数量 */
    if (file_type == TCC_OUTPUT_OBJ)  phnum = 0;   /* .o 没有程序头 */
    else if (file_type == TCC_OUTPUT_DLL) phnum = 3;
    else if (s1->static_link)         phnum = 2;
    else                              phnum = 5;

    phdr = tcc_mallocz(phnum * sizeof(ElfW(Phdr)));
    shnum = s1->nb_sections;
    sec_order = tcc_malloc(sizeof(int) * shnum);

    /* ③ 布局：给每个节分配虚拟地址和文件偏移 */
    file_offset = layout_sections(s1, phdr, phnum, interp, strsec, &dyninf, sec_order);

    if (file_type != TCC_OUTPUT_OBJ) {
        fill_unloadable_phdr(...);
        if (dynamic) { ... 更新动态节、relocate_plt ... }

        /* ④ 应用所有重定位（第 53 篇） */
        ret = final_sections_reloc(s1);
        ...
        tidy_section_headers(s1, sec_order);
        fill_got(s1);                    /* 填 GOT */
    }

    /* ⑤ 写文件 */
    ret = tcc_write_elf_file(s1, filename, phnum, phdr, file_offset, sec_order);
    ...
}
```

五个阶段：

1. **收集**：链接运行时、解决 `common` 符号、建动态符号表/GOT；
2. **命名**：给节名分配字符串；
3. **布局 `layout_sections`**：给每个节定 `sh_addr`（虚拟地址）和 `sh_offset`（文件偏移），
   并填程序头（Program Header，描述"段"）；
4. **重定位**：`final_sections_reloc` 遍历所有节调 `relocate_section`（第 53 篇）；
5. **写文件**：`tcc_write_elf_file` → `tcc_output_elf`。

---

## 第 2 站：`layout_sections` 干什么（`:1563`）

它的核心任务是"**把内存里的节安排到 ELF 文件地址空间里**"：

- 把 `SHF_ALLOC` 的节归入程序段（segment/PT_LOAD）；
- 给每个节算 `sh_addr`（虚拟地址）和 `sh_offset`（文件偏移）；
- 满足页对齐（如 `0x1000`）；
- 处理 `.interp`、`.dynamic`、`.got`、`.plt` 的位置。

**"节"是链接视角，"段"是加载视角。** 一个 `PT_LOAD` 通常包含多个 `SHF_ALLOC` 节。

---

## 第 3 站：写文件（`:1860`/`:1977`）

```c
/* src/core/tccelf.c:1977 起（概念）*/
static int tcc_write_elf_file(TCCState *s1, const char *filename, int phnum,
                             ElfW(Phdr) *phdr, int file_offset, int *sec_order)
{
    /* 打开文件，写：
       ElfHeader（文件头）
       ProgramHeaders（程序头，可执行/DLL 有，.o 没有）
       各节内容（按顺序，带对齐）
       SectionHeaders（节头表）
       .shstrtab（节名字符串表）
    */
}
```

`tcc_output_elf`（`:1860`）负责把 `ElfHeader`、各节内容、节头表组织成字节流。
`.o` 文件（`TCC_OUTPUT_OBJ`）**没有程序头**，只有节头——
因为它还不是"可加载的程序"，只是"待链接的积木"。

---

## 第 4 站：ELF 文件的骨架（`elf.h`）

```
ELF Header（文件头）
  ├─ e_type（REL/EXEC/DYN）
  ├─ e_machine（EM_X86_64）
  ├─ e_entry（入口地址）
  ├─ e_phoff / e_phnum（程序头位置/数量）
  └─ e_shoff / e_shnum（节头位置/数量）

Program Headers（程序头，可执行文件）/ 无（.o）
  PT_LOAD：+x 段（.text）
  PT_LOAD：+w 段（.data/.bss）
  PT_INTERP：动态加载器路径
  PT_DYNAMIC：动态信息

各节内容（.text/.data/.bss/.symtab/.strtab/.rel.text/...）

Section Headers（节头表，每个节一条）
.shstrtab（节名字符串）
```

**TCC 的 `Section` 结构和 ELF 的 Section Header 字段几乎一一对应**（`tcc.h:492`），
所以写文件时主要是搬运（第 14 篇）。

---

## 【把 `tcc t.c -o t` 的输出走一遍】

| 阶段 | 说明 |
|---|---|
| `tcc_add_runtime` | 链接 `crt1.o`、`libc` 等（非 `-nostdlib`） |
| `resolve_common_syms` | `int x;` 的 common 符号转 `.bss` |
| `build_got_entries` | 为 `printf` 等建 GOT/PLT |
| `layout_sections` | 给 `.text`/`.data` 等定地址 |
| `final_sections_reloc` | 应用所有重定位 |
| `tcc_write_elf_file` | 写出 `t`（可执行） |

然后 OS 加载 `t`，动态加载器按 `.interp` 启动，跳到 `main`。

---

## 【动手小实验】

1. `tcc -c` 和 `tcc`（可执行）分别用 `readelf -h` 看 `e_type`（REL vs EXEC）。
2. `readelf -l` 看程序头，`readelf -S` 看节头。
3. `readelf -d` 看 `.dynamic` 里的 `NEEDED`（依赖哪些库）。
4. 写 `int main(){}` 编译成可执行，看大小（TCC 输出很小）。

## 【通关暗号】

```bash
printf 'int main(void){return 0;}\n' > /tmp/e.c
./tcc /tmp/e.c -o /tmp/e && readelf -h /tmp/e 2>/dev/null | grep -E 'Type|Machine|Entry'
# 期望：Type EXEC/DYN，Machine X86-64，有入口地址
```

## 【常见卡点】

- **`.o` 没有程序头，只有节头**。
- **`layout_sections` 负责定虚拟地址和文件偏移**。
- **重定位在写文件前应用**（`final_sections_reloc`）。
- **节（Section）是链接视角，段（Segment/PT_LOAD）是加载视角**。

**下一篇**：`55-内存重定位与tcc-run.md`。
