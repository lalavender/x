# 61 · GOT 与 PLT：动态链接的两张表

> **一句话**：程序要调用 `printf`、访问动态库里的全局变量，但地址在链接时不知道。
> ELF 用两张表解决：**GOT**（全局偏移表，存地址）和 **PLT**（过程链接表，
> 函数跳板）。TCC 自己生成这两张表。
>
> 对应源码：`src/core/tccelf.c:911`（`build_got`）、`:926`（`put_got_entry`）、
> `:1018`（`build_got_entries`）、`:1330`（`fill_got`）、`:1359`（`fill_local_got_entries`）、
> `src/targets/x86_64-link.c:101`（`create_plt_entry`）、`:144`（`relocate_plt`）。

---

## 第 0 站：为什么需要 GOT/PLT

编译 `printf("hi")` 时：

- 生成代码想写 `call printf`，但 `printf` 在 `libc.so` 里，**地址链接时未知**；
- 位置无关代码（PIE）也不能硬编码地址。

方案：

- **GOT**：一块数据区，每格存一个符号的地址。代码通过 GOT 间接访问。
- **PLT**：每个外部函数一段小跳板，第一次调用时由 `ld.so` 填 GOT。

---

## 第 1 站：建 GOT 骨架 —— `build_got`（`tccelf.c:911`）

```c
/* src/core/tccelf.c:911-920 */
static void build_got(TCCState *s1)
{
    s1->got = new_section(s1, ".got", SHT_PROGBITS, SHF_ALLOC | SHF_WRITE);
    s1->got->sh_entsize = 4;
    set_elf_sym(symtab_section, 0, 4, ELFW(ST_INFO)(STB_GLOBAL, STT_OBJECT),
                0, s1->got->sh_num, "_GLOBAL_OFFSET_TABLE_");
    /* 留出 _DYNAMIC 指针和两个哑条目 */
    section_ptr_add(s1->got, 3 * PTR_SIZE);
}
```

- 建 `.got` 节（可写）；
- 定义符号 `_GLOBAL_OFFSET_TABLE_`（动态加载器认识它）；
- 开头留 3 个指针：`_DYNAMIC` 指针 + 两个哑条目（GOT0/GOT1）。

---

## 第 2 站：为一个符号建 GOT/PLT —— `put_got_entry`（`tccelf.c:926`）

```c
/* src/core/tccelf.c:926-1015（节选）*/
static struct sym_attr *put_got_entry(TCCState *s1, int dyn_reloc_type,
                                       unsigned long size,
                                       int info, int sym_index)
{
    int need_plt_entry;
    ...
    need_plt_entry = (dyn_reloc_type == R_JMP_SLOT);   /* 函数才要 PLT */
    attr = get_sym_attr(s1, sym_index, 1);             /* 符号的附加属性 */

    if (need_plt_entry ? attr->plt_offset : attr->got_offset)
        return attr;                     /* ★ 已经建过，复用 */

    /* ① 在 GOT 里要一格 */
    got_offset = s1->got->data_offset;
    section_ptr_add(s1->got, PTR_SIZE);

    /* ② 记一条重定位：把符号地址填进这一格 */
    sym = &((ElfW(Sym) *)symtab_section->data)[sym_index];
    if (s1->dynsym) {
        if (ELFW(ST_BIND)(sym->st_info) == STB_LOCAL) {
            /* 局部符号：先占位，fill_local_got_entries 再填 */
            put_elf_reloc(s1->dynsym, s1->got, got_offset, R_RELATIVE, sym_index);
        } else {
            if (0 == attr->dyn_index)
                attr->dyn_index = set_elf_sym(s1->dynsym, ...);   /* 进动态符号表 */
            put_elf_reloc(s1->dynsym, s1->got, got_offset, dyn_reloc_type,
                          attr->dyn_index);
        }
    } else {
        put_elf_reloc(symtab_section, s1->got, got_offset, dyn_reloc_type, sym_index);
    }

    /* ③ 需要 PLT 就再建一个跳板 */
    if (need_plt_entry) {
        if (!s1->plt) {
            s1->plt = new_section(s1, ".plt", SHT_PROGBITS, SHF_ALLOC | SHF_EXECINSTR);
            s1->plt->sh_entsize = 4;
        }
        attr->plt_offset = create_plt_entry(s1, got_offset, attr);
        /* 造一个 `sym@plt` 符号 */
        ...
    } else {
        attr->got_offset = got_offset;
    }
    return attr;
}
```

`struct sym_attr`（`tcc.h:630`）给每个符号挂 GOT/PLT 信息：

```c
struct sym_attr {
    unsigned got_offset;    /* 在 .got 里的偏移 */
    unsigned plt_offset;    /* 在 .plt 里的偏移 */
    int plt_sym;            /* `sym@plt` 符号下标 */
    int dyn_index;          /* 在 .dynsym 里的下标 */
    ...
};
```

**"函数用 PLT，数据用 GOT"**：`dyn_reloc_type == R_JMP_SLOT` 表示函数调用。

---

## 第 3 站：PLT 跳板长什么样 —— `create_plt_entry`（`x86_64-link.c:101`）

```c
/* src/targets/x86_64-link.c:101-140（节选）*/
ST_FUNC unsigned create_plt_entry(TCCState *s1, unsigned got_offset, struct sym_attr *attr)
{
    Section *plt = s1->plt;
    uint8_t *p;
    ...
    /* PLT0：第一条跳板，负责调用 ld.so 的解析例程 */
    if (plt->data_offset == 0) {
        p = section_ptr_add(plt, 16);
        p[0] = 0xff; p[1] = modrm + 0x10;
        write32le(p + 2, PTR_SIZE);       /* push GOT+8 */
        p[6] = 0xff; p[7] = modrm;
        write32le(p + 8, PTR_SIZE * 2);   /* jmp *(GOT+16) */
    }
    plt_offset = plt->data_offset;

    /* 每条 PLT 入口：jmp *(GOT+x)  → 第一次跳到 push+resolve */
    p = section_ptr_add(plt, 16);
    p[0] = 0xff;                          /* jmp *got */
    p[1] = modrm;
    write32le(p + 2, got_offset);
    p[6] = 0x68;                          /* push $reloc_index */
    write32le(p + 7, relofs / sizeof(ElfW_Rel));
    p[11] = 0xe9;                         /* jmp plt_start */
    write32le(p + 12, -(plt->data_offset));
    return plt_offset;
}
```

**PLT 入口的经典结构**：

```asm
printf@plt:
    jmp   *GOT[printf]     ; 第一次 GOT 里指向下一条指令
    push  $index           ; 压重定位下标
    jmp   plt0             ; 跳到解析器
```

第一次调用时，`ld.so` 解析 `printf` 的真实地址写进 GOT；
之后 `jmp *GOT[printf]` 直接跳到 `printf`。这叫**延迟绑定（lazy binding）**。

---

## 第 4 站：谁需要 GOT/PLT —— `build_got_entries`（`tccelf.c:1018`）

```c
/* src/core/tccelf.c:1018-1108（节选）*/
ST_FUNC void build_got_entries(TCCState *s1)
{
    for(i = 1; i < s1->nb_sections; i++) {
        s = s1->sections[i];
        if (s->sh_type != SHT_RELX || s->link != symtab_section) continue;
        for_each_elem(s, 0, rel, ElfW_Rel) {
            type = ELFW(R_TYPE)(rel->r_info);
            gotplt_entry = gotplt_entry_type(type);   /* 第 53 篇的分类 */
            sym_index = ELFW(R_SYM)(rel->r_info);
            sym = ...;
            if (gotplt_entry == NO_GOTPLT_ENTRY) continue;   /* 不需要 */

            if (gotplt_entry == AUTO_GOTPLT_ENTRY) {
                if (sym->st_shndx == SHN_UNDEF) {
                    /* 未定义引用才需要（比如 printf） */
                    ... 看是不是函数 → jmp_slot ...
                } else if (!(sym->st_shndx == SHN_ABS && PTR_SIZE == 8)) {
                    continue;                     /* 已定义符号不需要 GOT */
                }
            }
            if (code_reloc(type)) { jmp_slot: reloc_type = R_JMP_SLOT; }  /* 函数 */
            else                                  reloc_type = R_GLOB_DAT; /* 数据 */

            if (!s1->got) build_got(s1);
            if (gotplt_entry == BUILD_GOT_ONLY) continue;

            attr = put_got_entry(s1, reloc_type, sym->st_size, sym->st_info, sym_index);
            if (reloc_type == R_JMP_SLOT)
                rel->r_info = ELFW(R_INFO)(attr->plt_sym, type);  /* 重定向到 @plt */
        }
    }
}
```

**它扫所有重定位，发现"未定义的外部引用"就建 GOT/PLT**，
并把原重定位的符号改成 `sym@plt`（这样 `call` 跳到 PLT 而不是直接跳）。

---

## 第 5 站：填 GOT（`:1330`/`:1359`）

```c
/* src/core/tccelf.c:1330-1355（节选）*/
ST_FUNC void fill_got(TCCState *s1)
{
    /* 静态链接时：把已定义符号的地址直接写进 GOT */
    ... 遍历 GOT 的重定位，调用 fill_got_entry ...
}

/* src/core/tccelf.c:1359-1379（节选）*/
static void fill_local_got_entries(TCCState *s1)
{
    /* 局部符号的 GOT 格：直接填 st_value */
}
```

对于**静态链接**或**本地符号**，GOT 格在链接时就能填好，不用延迟绑定。

---

## 第 6 站：PLT 的最终修补 —— `relocate_plt`（`x86_64-link.c:144`）

```c
/* src/targets/x86_64-link.c:144-164（节选）*/
ST_FUNC void relocate_plt(TCCState *s1)
{
    ...
    /* PLT 和 GOT 的最终地址已知，回填 PLT 里的相对偏移 */
    int x = s1->got->sh_addr - s1->plt->sh_addr - 6;
    add32le(p + 2, x);
    ...
}
```

地址都定好之后（`layout_sections` 之后），把 PLT 的 `jmp` 目标算对。

---

## 【把 `printf("hi")` 的动态链接走一遍】

| 阶段 | 说明 |
|---|---|
| 编译 | `call printf` → `R_X86_64_PLT32` 重定位 |
| `build_got_entries` | 发现 `printf` 未定义 → 建 GOT 格 + PLT 入口 |
| | 重定位改成指向 `printf@plt` |
| 链接输出 | 写 `.got`、`.plt`、`.dynsym`、`.dynamic`（含 `NEEDED libc.so`） |
| 运行时 | 第一次 `call printf@plt` → 跳到 PLT → `ld.so` 解析 → 填 GOT |
| 之后 | `call printf@plt` → `jmp *GOT` → 直达 `printf` |

---

## 【动手小实验】

1. `objdump -d /tmp/h | grep -A3 '<printf@plt>'` 看 PLT 反汇编。
2. `objdump -R /tmp/h` 看动态重定位（`JUMP_SLOT printf`）。
3. `readelf -r /tmp/h` 看 `.rela.plt`/`.rela.dyn`。
4. `tcc -static` 编译，看还有没有 PLT（应该没有了）。

## 【通关暗号】

```bash
printf '#include <stdio.h>\nint main(void){printf("x\\n"); return 0;}\n' > /tmp/p.c
./tcc /tmp/p.c -o /tmp/p && objdump -d /tmp/p 2>/dev/null | grep -c '@plt'
# 期望：>=1（存在 PLT 跳板）
```

## 【常见卡点】

- **GOT 存地址，PLT 是跳板**。
- **函数用 `R_JMP_SLOT`+PLT，数据用 `R_GLOB_DAT`+GOT**。
- **延迟绑定**：第一次调用才解析地址。
- **`build_got_entries` 扫所有重定位决定给谁建表**。
- **`_GLOBAL_OFFSET_TABLE_` 是动态加载器认识的符号**。

---

## 【第九部小结】

| 篇 | 主题 |
|---|---|
| 58 | 链接总流程 |
| 59 | 符号解析与公共符号 |
| 60 | 段合并与地址分配 |
| 61 | GOT 与 PLT |

**下一步（第十部）**：内存执行与 libtcc 嵌入——`tcc_run` 细节、崩溃回溯、libtcc API。

**下一篇**：`62-tcc-run详解.md`。
