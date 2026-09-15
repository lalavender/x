# 14 · Section：会自己生长的纸带

> **一句话**：编译器的全部输出，都是往几条"纸带"上写字节——
> 机器码写 `.text`、已初始化数据写 `.data`、未初始化数据写 `.bss`、
> 名字写 `.strtab`、符号写 `.symtab`、欠条写 `.rel.text`。
> 每条纸带就是一个 `Section`。
>
> 对应源码：`src/core/tcc.h:492`（结构）、`src/core/tccelf.c:192`（`new_section` 造纸带）、
> `src/core/tccelf.c:257`（`section_realloc` 长个）、`src/core/tccelf.c:275`（`section_add` 申请空间）、
> `src/core/tccelf.c:291`（`section_ptr_add` 拿指针）、`src/core/tccelf.c:55`（`tccelf_new` 造标准纸带）。

---

## 第 0 站：纸带长什么样（`tcc.h:492`）

```c
/* src/core/tcc.h:491-512 */
typedef struct Section {
    unsigned long data_offset;   /* ★ 写到哪了（当前长度） */
    unsigned char *data;         /* ★ 字节数组本体（会 realloc 长大） */
    unsigned long data_allocated;/* 分配了多大 */

    int sh_name;                 /* ELF 节名（写文件时才填） */
    int sh_num;                  /* 节编号 */
    int sh_type;                 /* ELF 类型（PROGBITS/NOBITS/SYMTAB/...） */
    int sh_flags;                /* ELF 标志（ALLOC/WRITE/EXECINSTR...） */
    int sh_info;
    int sh_addralign;            /* 对齐要求 */
    int sh_entsize;              /* 每项大小（表类节用） */
    unsigned long sh_size;
    addr_t sh_addr;              /* 最终地址（链接期才填） */
    unsigned long sh_offset;     /* 文件偏移 */
    int nb_hashed_syms;

    struct Section *link;        /* 配套节：symtab 的 link 是 strtab */
    struct Section *reloc;       /* 我的欠条节：.text 的 reloc 是 .rel.text */
    struct Section *hash;        /* 符号哈希表 */
    struct Section *prev;
    char name[1];                /* 纸带名字（柔性数组，又是 [1] 花招） */
} Section;
```

**`data` + `data_offset` 就是"纸带"本体**：一个会自动 `realloc` 的字节数组。
所有"生成机器码"最终都是"往某条纸带的 `data_offset` 处写几个字节，然后 `data_offset` 前移"。

---

## 第 1 站：造一条纸带 —— `new_section`（`tccelf.c:192`）

```c
/* src/core/tccelf.c:192-225 */
ST_FUNC Section *new_section(TCCState *s1, const char *name, int sh_type, int sh_flags)
{
    Section *sec;

    sec = tcc_mallocz(sizeof(Section) + strlen(name));  /* 分配（含名字空间） */
    strcpy(sec->name, name);
    sec->sh_type = sh_type;
    sec->sh_flags = sh_flags;
    switch(sh_type) {
    case SHT_HASH:
    case SHT_REL:
    case SHT_RELA:
    case SHT_DYNSYM:
    case SHT_SYMTAB:
    case SHT_DYNAMIC:
        sec->sh_addralign = 4;       /* 表类节：4 字节对齐 */
        break;
    case SHT_STRTAB:
        sec->sh_addralign = 1;       /* 字符串表：不用对齐 */
        break;
    default:
        sec->sh_addralign = PTR_SIZE;/* 其它：按指针大小对齐 */
        break;
    }

    if (sh_flags & SHF_PRIVATE) {
        dynarray_add(&s1->priv_sections, &s1->nb_priv_sections, sec);  /* 内部节 */
    } else {
        sec->sh_num = s1->nb_sections;                                 /* ★ 领节号 */
        dynarray_add(&s1->sections, &s1->nb_sections, sec);
    }

    return sec;
}
```

要点：

- **`tcc_mallocz(sizeof(Section) + strlen(name))`**：又一次"结构体 + 柔性数组"一起分配。
- **两种节**：
  - 普通节（`.text`/`.data`）进 `s1->sections`，有节号，会写进 ELF；
  - `SHF_PRIVATE` 节（哈希表等）进 `s1->priv_sections`，只在内存里用。
- `dynarray_add` 是个宏，把指针追加到动态数组，数组满了自动翻倍。

---

## 第 2 站：往纸带上写 —— `section_add` / `section_ptr_add`（`tccelf.c:275/291`）

```c
/* src/core/tccelf.c:273-287 */
/* 在当前偏移处按 align 对齐，预留 size 字节，返回对齐后的偏移 */
ST_FUNC size_t section_add(Section *sec, addr_t size, int align)
{
    size_t offset, offset1;

    offset = (sec->data_offset + align - 1) & -align;  /* ★ 向上取整对齐 */
    offset1 = offset + size;
    if (sec->sh_type != SHT_NOBITS && offset1 > sec->data_allocated)
        section_realloc(sec, offset1);                 /* 不够就长个 */
    sec->data_offset = offset1;
    if (align > sec->sh_addralign)
        sec->sh_addralign = align;                     /* 记录最大对齐 */
    return offset;
}

/* src/core/tccelf.c:289-295 */
ST_FUNC void *section_ptr_add(Section *sec, addr_t size)
{
    size_t offset = section_add(sec, size, 1);
    return sec->data + offset;    /* 返回"要写的地址" */
}
```

**对齐技巧 `(x + align - 1) & -align`**：
当 `align` 是 2 的幂时，这就是"向上取整到 align 的倍数"。
比 `x % align ? ...` 快。**编译器中到处都是这个技巧。**

`section_ptr_add` 是"我要写数据"的入口：它返回一个指针，
调用者 memcpy 或直接写进去。例如追加机器码：

```c
o(0x48); o(0x89); ...      /* 后端逐字节写，实际通过 section_ptr_add */
```

**注意 `SHT_NOBITS`（`.bss`）不分配实际数据**，因为 `#define bss` 就是"只占地址不占文件"。

---

## 第 3 站：纸带怎么长大 —— `section_realloc`（`tccelf.c:257`）

```c
/* src/core/tccelf.c:256-271 */
ST_FUNC void section_realloc(Section *sec, unsigned long new_size)
{
    unsigned long size;
    unsigned char *data;

    size = sec->data_allocated;
    if (size == 0)
        size = 1;
    while (size < new_size)
        size = size * 2;                            /* ★ 容量翻倍 */
    data = tcc_realloc(sec->data, size);
    memset(data + sec->data_allocated, 0, size - sec->data_allocated);  /* 新空间清零 */
    sec->data = data;
    sec->data_allocated = size;
}
```

还是**容量翻倍**。为什么要清零新空间？因为 ELF 里 `.bss` 之外的洞、
对齐产生的空隙都应该是 0，清零最省心。

---

## 第 4 站：找一条已有纸带 —— `find_section`（`tccelf.c:308`）

```c
/* src/core/tccelf.c:308-319 */
ST_FUNC Section *find_section(TCCState *s1, const char *name)
{
    Section *sec;
    int i;
    for(i = 1; i < s1->nb_sections; i++) {     /* 从 1 开始，0 是空 */
        sec = s1->sections[i];
        if (!strcmp(name, sec->name))
            return sec;
    }
    /* 没有就按普通数据节新建 */
    return new_section(s1, name, SHT_PROGBITS, SHF_ALLOC);
}
```

`find_section("...")` 是"我要往 `foo` 节写东西"的入口。线性的 `strcmp` 扫描——
节数量不多，不值得建哈希表。

---

## 第 5 站：标准纸带从哪来 —— `tccelf_new`（`tccelf.c:55`）

编译开始时（`tcc_new` 里调）造好这些：

```c
/* src/core/tccelf.c:55-78 */
ST_FUNC void tccelf_new(TCCState *s)
{
    /* 第 0 节留空 */
    dynarray_add(&s->sections, &s->nb_sections, NULL);

    /* 标准节 */
    text_section   = new_section(s, ".text",   SHT_PROGBITS, SHF_ALLOC | SHF_EXECINSTR);
    data_section   = new_section(s, ".data",   SHT_PROGBITS, SHF_ALLOC | SHF_WRITE);
    bss_section    = new_section(s, ".bss",    SHT_NOBITS,   SHF_ALLOC | SHF_WRITE);
    common_section = new_section(s, ".common", SHT_NOBITS,   SHF_PRIVATE);
    common_section->sh_num = SHN_COMMON;

    /* 符号表永远生成（链接阶段要用） */
    symtab_section = new_symtab(s, ".symtab", SHT_SYMTAB, 0,
                                ".strtab", ".hashtab", SHF_PRIVATE);
    s->symtab = symtab_section;

    /* 动态符号表 */
    s->dynsymtab_section = new_symtab(s, ".dynsymtab", ...);
    get_sym_attr(s, 0, 1);
}
```

对应到 ELF 文件：

| 纸带 | 装什么 | ELF 属性 |
|---|---|---|
| `.text` | 机器码 | 有内容、可读可执行 |
| `.data` | 已初始化全局/静态变量 | 有内容、可读可写 |
| `.bss` | 未初始化全局变量 | 无内容、可读可写（`NOBITS`） |
| `.common` | 暂定公共符号（老式 C 的 `int x;` 多处定义） | 私有 |
| `.symtab` | 符号表 | 表，`sh_entsize` 是每项大小 |
| `.strtab` | 符号名字符串 | 字符串表，不对齐 |

`new_symtab`（`tccelf.c:227`）一次把"符号表 + 字符串表 + 哈希表"三件套造好，
并把它们互相挂钩（`symtab->link = strtab`、`symtab->hash = hash`）。
这是第 52 篇的主角。

---

## 【把 t.c 的输出分配走一遍】

```c
#define K 8
int add(int a, int b) { return a + b; }
int g = 5;
int main(void) { int x = 3; return add(x, g); }
```

| 内容 | 写进哪条纸带 |
|---|---|
| `add`、`main` 的机器码 | `.text` |
| 全局 `g`（初值 5） | `.data` |
| 未初始化全局（如果有） | `.bss` |
| `add`、`main`、`g` 的符号 | `.symtab` |
| 名字 `"add"`、`"main"`、`"g"` | `.strtab` |
| `add`/`main` 里对 `g`、对彼此的地址引用（还没定） | `.rel.text`（欠条） |

**编译 = 往这些纸带上写字节。** 写到最后 `tcc_output_file` 把纸带打包成 ELF。

---

## 【动手小实验】

1. 编译一个小程序到 `.o`，用 `objdump -h` 或 `otool` 看它有哪些 section，
   对照上面的表格。
2. 在 `section_add` 里加一句 `printf("%s add %d align %d -> %d\n", sec->name, (int)size, align, (int)offset);`，
   看 TCC 申请空间的节奏。
3. 搜 `section_ptr_add`，看哪些函数在往纸带写（`put_elf_sym`、`gen_le32` 的最终去处等）。

## 【通关暗号】

```bash
printf 'int g=5; int main(void){return g;}\n' > /tmp/g.c
./tcc -c /tmp/g.c -o /tmp/g.o && objdump -h /tmp/g.o 2>/dev/null | grep -E 'text|data|bss|symtab|strtab'
# 期望：能看到 .text/.data/.symtab/.strtab 等节
```

## 【常见卡点】

- **`Section` 不是"文件段"**，是内存里的字节数组；写 ELF 时才按 ELF 规则拼。
- **`.bss` 是 `SHT_NOBITS`**：有大小、无数据，`section_add` 不为它分配内存。
- **对齐公式 `(x+align-1)&-align` 只对 2 的幂成立**。
- **`name[1]` 又是柔性数组**，分配时多给 `strlen(name)`。

**下一篇**：`15-TCCState大账本.md` —— 整台编译器的状态都挂在一个结构上。
