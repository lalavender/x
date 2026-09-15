/*
 *  TCC 的 ELF 文件处理
 *
 *  Copyright (c) 2001-2004 Fabrice Bellard
 *
 * 本库为自由软件；你可以遵照自由软件基金会发布的 GNU 宽通用公共许可证
 * 的条款重新分发和/或修改它，无论是许可证的第 2 版，还是（由你选择的）
 * 任何更新的版本。
 *
 * 分发本库是希望它有用，但不提供任何担保；
 * 甚至不提供对适销性或特定用途适用性的默示担保。
 * 详见 GNU 宽通用公共许可证。
 *
 * 你应当已经随本库收到一份 GNU 宽通用公共许可证的副本；
 * 如果没有，请写信给自由软件基金会：
 * 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 */

#include "tcc.h"

/* 定义它可以在重定位处理期间得到一些调试输出。  */
#undef DEBUG_RELOC

/********************************************************/
/* 全局变量 */

ST_DATA Section *text_section, *data_section, *bss_section; /* 预定义的段 */
ST_DATA Section *common_section;
ST_DATA Section *cur_text_section; /* 生成函数代码的当前段 */
#ifdef CONFIG_TCC_ASM
ST_DATA Section *last_text_section; /* 用于处理 .previous 汇编伪指令 */
#endif
#ifdef CONFIG_TCC_BCHECK
/* 边界检查相关的段 */
ST_DATA Section *bounds_section; /* 包含全局数据的边界描述 */
ST_DATA Section *lbounds_section; /* 包含局部数据的边界描述 */
#endif
/* 符号段 */
ST_DATA Section *symtab_section;
/* 调试段 */
ST_DATA Section *stab_section, *stabstr_section;

/* XXX：避免使用静态变量 */
static int new_undef_sym = 0; /* 自上次调用 new_undef_sym() 以来是否有新的未定义符号 */

/* 特殊标志，表示该段不应与其他段链接在一起 */
#define SHF_PRIVATE 0x80000000
/* 该段是 dynsymtab_section */
#define SHF_DYNSYM 0x40000000

/* ------------------------------------------------------------------------- */

ST_FUNC void tccelf_new(TCCState *s)
{
    /* 没有零号段 */
    dynarray_add(&s->sections, &s->nb_sections, NULL);

    /* 创建标准段 */
    text_section = new_section(s, ".text", SHT_PROGBITS, SHF_ALLOC | SHF_EXECINSTR);
    data_section = new_section(s, ".data", SHT_PROGBITS, SHF_ALLOC | SHF_WRITE);
    bss_section = new_section(s, ".bss", SHT_NOBITS, SHF_ALLOC | SHF_WRITE);
    common_section = new_section(s, ".common", SHT_NOBITS, SHF_PRIVATE);
    common_section->sh_num = SHN_COMMON;

    /* 链接阶段总是生成符号 */
    symtab_section = new_symtab(s, ".symtab", SHT_SYMTAB, 0,
                                ".strtab",
                                ".hashtab", SHF_PRIVATE);
    s->symtab = symtab_section;

    /* 动态符号的私有符号表 */
    s->dynsymtab_section = new_symtab(s, ".dynsymtab", SHT_SYMTAB, SHF_PRIVATE|SHF_DYNSYM,
                                      ".dynstrtab",
                                      ".dynhashtab", SHF_PRIVATE);
    get_sym_attr(s, 0, 1);
}

#ifdef CONFIG_TCC_BCHECK
ST_FUNC void tccelf_bounds_new(TCCState *s)
{
    /* 创建边界检查段 */
    bounds_section = new_section(s, ".bounds",
                                 SHT_PROGBITS, SHF_ALLOC);
    lbounds_section = new_section(s, ".lbounds",
                                  SHT_PROGBITS, SHF_ALLOC);
}
#endif

ST_FUNC void tccelf_stab_new(TCCState *s)
{
    stab_section = new_section(s, ".stab", SHT_PROGBITS, 0);
    stab_section->sh_entsize = sizeof(Stab_Sym);
    stabstr_section = new_section(s, ".stabstr", SHT_STRTAB, 0);
    put_elf_str(stabstr_section, "");
    stab_section->link = stabstr_section;
    /* 放入第一个条目 */
    put_stabs("", 0, 0, 0, 0);
}

static void free_section(Section *s)
{
    tcc_free(s->data);
}

ST_FUNC void tccelf_delete(TCCState *s1)
{
    int i;

    /* 释放所有段 */
    for(i = 1; i < s1->nb_sections; i++)
        free_section(s1->sections[i]);
    dynarray_reset(&s1->sections, &s1->nb_sections);

    for(i = 0; i < s1->nb_priv_sections; i++)
        free_section(s1->priv_sections[i]);
    dynarray_reset(&s1->priv_sections, &s1->nb_priv_sections);

    /* 释放所有已加载的 DLL */
#ifdef TCC_IS_NATIVE
    for ( i = 0; i < s1->nb_loaded_dlls; i++) {
        DLLReference *ref = s1->loaded_dlls[i];
        if ( ref->handle )
# ifdef _WIN32
            FreeLibrary((HMODULE)ref->handle);
# else
            dlclose(ref->handle);
# endif
    }
#endif
    /* 释放已加载 dll 的数组 */
    dynarray_reset(&s1->loaded_dlls, &s1->nb_loaded_dlls);
    tcc_free(s1->sym_attrs);

    symtab_section = NULL; /* 供 tccrun.c:rt_printline() 使用 */
}

/* 保存段数据状态 */
ST_FUNC void tccelf_begin_file(TCCState *s1)
{
    Section *s; int i;
    for (i = 1; i < s1->nb_sections; i++) {
        s = s1->sections[i];
        s->sh_offset = s->data_offset;
    }
    /* 编译期间禁用符号哈希 */
    s = s1->symtab, s->reloc = s->hash, s->hash = NULL;
}

/* 编译结束时，把任何 UNDEF 符号转换为全局符号，并与之前
   已有的符号合并 */
ST_FUNC void tccelf_end_file(TCCState *s1)
{
    Section *s = s1->symtab;
    int first_sym, nb_syms, *tr, i;

    first_sym = s->sh_offset / sizeof (ElfSym);
    nb_syms = s->data_offset / sizeof (ElfSym) - first_sym;
    s->data_offset = s->sh_offset;
    s->link->data_offset = s->link->sh_offset;
    s->hash = s->reloc, s->reloc = NULL;
    tr = tcc_mallocz(nb_syms * sizeof *tr);

    for (i = 0; i < nb_syms; ++i) {
        ElfSym *sym = (ElfSym*)s->data + first_sym + i;
        if (sym->st_shndx == SHN_UNDEF
            && ELFW(ST_BIND)(sym->st_info) == STB_LOCAL)
            sym->st_info = ELFW(ST_INFO)(STB_GLOBAL, ELFW(ST_TYPE)(sym->st_info));
        tr[i] = set_elf_sym(s, sym->st_value, sym->st_size, sym->st_info,
            sym->st_other, sym->st_shndx, s->link->data + sym->st_name);
    }
    /* 现在更新重定位 */
    for (i = 1; i < s1->nb_sections; i++) {
        Section *sr = s1->sections[i];
        if (sr->sh_type == SHT_RELX && sr->link == s) {
            ElfW_Rel *rel = (ElfW_Rel*)(sr->data + sr->sh_offset);
            ElfW_Rel *rel_end = (ElfW_Rel*)(sr->data + sr->data_offset);
            for (; rel < rel_end; ++rel) {
                int n = ELFW(R_SYM)(rel->r_info) - first_sym;
                //if (n < 0) tcc_error("internal: invalid symbol index in relocation");
                rel->r_info = ELFW(R_INFO)(tr[n], ELFW(R_TYPE)(rel->r_info));
            }
        }
    }
    tcc_free(tr);
}

ST_FUNC Section *new_section(TCCState *s1, const char *name, int sh_type, int sh_flags)
{
    Section *sec;

    sec = tcc_mallocz(sizeof(Section) + strlen(name));
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
        sec->sh_addralign = 4;
        break;
    case SHT_STRTAB:
        sec->sh_addralign = 1;
        break;
    default:
        sec->sh_addralign =  PTR_SIZE; /* gcc/pcc 默认对齐 */
        break;
    }

    if (sh_flags & SHF_PRIVATE) {
        dynarray_add(&s1->priv_sections, &s1->nb_priv_sections, sec);
    } else {
        sec->sh_num = s1->nb_sections;
        dynarray_add(&s1->sections, &s1->nb_sections, sec);
    }

    return sec;
}

ST_FUNC Section *new_symtab(TCCState *s1,
                           const char *symtab_name, int sh_type, int sh_flags,
                           const char *strtab_name,
                           const char *hash_name, int hash_sh_flags)
{
    Section *symtab, *strtab, *hash;
    int *ptr, nb_buckets;

    symtab = new_section(s1, symtab_name, sh_type, sh_flags);
    symtab->sh_entsize = sizeof(ElfW(Sym));
    strtab = new_section(s1, strtab_name, SHT_STRTAB, sh_flags);
    put_elf_str(strtab, "");
    symtab->link = strtab;
    put_elf_sym(symtab, 0, 0, 0, 0, 0, NULL);

    nb_buckets = 1;

    hash = new_section(s1, hash_name, SHT_HASH, hash_sh_flags);
    hash->sh_entsize = sizeof(int);
    symtab->hash = hash;
    hash->link = symtab;

    ptr = section_ptr_add(hash, (2 + nb_buckets + 1) * sizeof(int));
    ptr[0] = nb_buckets;
    ptr[1] = 1;
    memset(ptr + 2, 0, (nb_buckets + 1) * sizeof(int));
    return symtab;
}

/* 重新分配段并把其内容置零 */
ST_FUNC void section_realloc(Section *sec, unsigned long new_size)
{
    unsigned long size;
    unsigned char *data;

    size = sec->data_allocated;
    if (size == 0)
        size = 1;
    while (size < new_size)
        size = size * 2;
    data = tcc_realloc(sec->data, size);
    memset(data + sec->data_allocated, 0, size - sec->data_allocated);
    sec->data = data;
    sec->data_allocated = size;
}

/* 在段 'sec' 中从当前偏移开始预留至少 'size' 字节、按 'align'
   对齐的空间，并返回对齐后的偏移 */
ST_FUNC size_t section_add(Section *sec, addr_t size, int align)
{
    size_t offset, offset1;

    offset = (sec->data_offset + align - 1) & -align;
    offset1 = offset + size;
    if (sec->sh_type != SHT_NOBITS && offset1 > sec->data_allocated)
        section_realloc(sec, offset1);
    sec->data_offset = offset1;
    if (align > sec->sh_addralign)
        sec->sh_addralign = align;
    return offset;
}

/* 在段 'sec' 中从 sec->data_offset 开始预留至少
   'size' 字节。 */
ST_FUNC void *section_ptr_add(Section *sec, addr_t size)
{
    size_t offset = section_add(sec, size, 1);
    return sec->data + offset;
}

/* 从段起始位置预留至少 'size' 字节 */
ST_FUNC void section_reserve(Section *sec, unsigned long size)
{
    if (size > sec->data_allocated)
        section_realloc(sec, size);
    if (size > sec->data_offset)
        sec->data_offset = size;
}

/* 返回对某个段的引用，如果它不存在
   就创建它 */
ST_FUNC Section *find_section(TCCState *s1, const char *name)
{
    Section *sec;
    int i;
    for(i = 1; i < s1->nb_sections; i++) {
        sec = s1->sections[i];
        if (!strcmp(name, sec->name))
            return sec;
    }
    /* 段创建为 PROGBITS */
    return new_section(s1, name, SHT_PROGBITS, SHF_ALLOC);
}

/* ------------------------------------------------------------------------- */

ST_FUNC int put_elf_str(Section *s, const char *sym)
{
    int offset, len;
    char *ptr;

    len = strlen(sym) + 1;
    offset = s->data_offset;
    ptr = section_ptr_add(s, len);
    memmove(ptr, sym, len);
    return offset;
}

/* elf 符号哈希函数 */
static unsigned long elf_hash(const unsigned char *name)
{
    unsigned long h = 0, g;

    while (*name) {
        h = (h << 4) + *name++;
        g = h & 0xf0000000;
        if (g)
            h ^= g >> 24;
        h &= ~g;
    }
    return h;
}

/* 重建段 s 的哈希表 */
/* 注意：我们特意把哈希表代码展开以加快速度 */
static void rebuild_hash(Section *s, unsigned int nb_buckets)
{
    ElfW(Sym) *sym;
    int *ptr, *hash, nb_syms, sym_index, h;
    unsigned char *strtab;

    strtab = s->link->data;
    nb_syms = s->data_offset / sizeof(ElfW(Sym));

    if (!nb_buckets)
        nb_buckets = ((int*)s->hash->data)[0];

    s->hash->data_offset = 0;
    ptr = section_ptr_add(s->hash, (2 + nb_buckets + nb_syms) * sizeof(int));
    ptr[0] = nb_buckets;
    ptr[1] = nb_syms;
    ptr += 2;
    hash = ptr;
    memset(hash, 0, (nb_buckets + 1) * sizeof(int));
    ptr += nb_buckets + 1;

    sym = (ElfW(Sym) *)s->data + 1;
    for(sym_index = 1; sym_index < nb_syms; sym_index++) {
        if (ELFW(ST_BIND)(sym->st_info) != STB_LOCAL) {
            h = elf_hash(strtab + sym->st_name) % nb_buckets;
            *ptr = hash[h];
            hash[h] = sym_index;
        } else {
            *ptr = 0;
        }
        ptr++;
        sym++;
    }
}

/* 返回符号编号 */
ST_FUNC int put_elf_sym(Section *s, addr_t value, unsigned long size,
    int info, int other, int shndx, const char *name)
{
    int name_offset, sym_index;
    int nbuckets, h;
    ElfW(Sym) *sym;
    Section *hs;

    sym = section_ptr_add(s, sizeof(ElfW(Sym)));
    if (name && name[0])
        name_offset = put_elf_str(s->link, name);
    else
        name_offset = 0;
    /* XXX：字节序 */
    sym->st_name = name_offset;
    sym->st_value = value;
    sym->st_size = size;
    sym->st_info = info;
    sym->st_other = other;
    sym->st_shndx = shndx;
    sym_index = sym - (ElfW(Sym) *)s->data;
    hs = s->hash;
    if (hs) {
        int *ptr, *base;
        ptr = section_ptr_add(hs, sizeof(int));
        base = (int *)hs->data;
        /* 只添加全局符号或弱符号。 */
        if (ELFW(ST_BIND)(info) != STB_LOCAL) {
            /* 增加另一个哈希条目 */
            nbuckets = base[0];
            h = elf_hash((unsigned char *)s->link->data + name_offset) % nbuckets;
            *ptr = base[2 + h];
            base[2 + h] = sym_index;
            base[1]++;
            /* 我们调整哈希表的大小 */
            hs->nb_hashed_syms++;
            if (hs->nb_hashed_syms > 2 * nbuckets) {
                rebuild_hash(s, 2 * nbuckets);
            }
        } else {
            *ptr = 0;
            base[1]++;
        }
    }
    return sym_index;
}

ST_FUNC int find_elf_sym(Section *s, const char *name)
{
    ElfW(Sym) *sym;
    Section *hs;
    int nbuckets, sym_index, h;
    const char *name1;

    hs = s->hash;
    if (!hs)
        return 0;
    nbuckets = ((int *)hs->data)[0];
    h = elf_hash((unsigned char *) name) % nbuckets;
    sym_index = ((int *)hs->data)[2 + h];
    while (sym_index != 0) {
        sym = &((ElfW(Sym) *)s->data)[sym_index];
        name1 = (char *) s->link->data + sym->st_name;
        if (!strcmp(name, name1))
            return sym_index;
        sym_index = ((int *)hs->data)[2 + nbuckets + sym_index];
    }
    return 0;
}

/* 返回 elf 符号值，'err' 非零时报告错误 */
ST_FUNC addr_t get_elf_sym_addr(TCCState *s, const char *name, int err)
{
    int sym_index;
    ElfW(Sym) *sym;

    sym_index = find_elf_sym(s->symtab, name);
    sym = &((ElfW(Sym) *)s->symtab->data)[sym_index];
    if (!sym_index || sym->st_shndx == SHN_UNDEF) {
        if (err)
            tcc_error("%s not defined", name);
        return 0;
    }
    return sym->st_value;
}

/* 返回 elf 符号值 */
LIBTCCAPI void *tcc_get_symbol(TCCState *s, const char *name)
{
    return (void*)(uintptr_t)get_elf_sym_addr(s, name, 0);
}

#if defined TCC_IS_NATIVE
/* 返回 elf 符号值或错误 */
ST_FUNC void* tcc_get_symbol_err(TCCState *s, const char *name)
{
    return (void*)(uintptr_t)get_elf_sym_addr(s, name, 1);
}
#endif

/* 添加一个 elf 符号：检查它是否已定义并打补丁。
   返回符号索引。注意 sh_num 可以是 SHN_UNDEF。 */
ST_FUNC int set_elf_sym(Section *s, addr_t value, unsigned long size,
                       int info, int other, int shndx, const char *name)
{
    ElfW(Sym) *esym;
    int sym_bind, sym_index, sym_type, esym_bind;
    unsigned char sym_vis, esym_vis, new_vis;

    sym_bind = ELFW(ST_BIND)(info);
    sym_type = ELFW(ST_TYPE)(info);
    sym_vis = ELFW(ST_VISIBILITY)(other);

    if (sym_bind != STB_LOCAL) {
        /* 我们搜索全局符号或弱符号 */
        sym_index = find_elf_sym(s, name);
        if (!sym_index)
            goto do_def;
        esym = &((ElfW(Sym) *)s->data)[sym_index];
        if (esym->st_value == value && esym->st_size == size && esym->st_info == info
            && esym->st_other == other && esym->st_shndx == shndx)
            return sym_index;
        if (esym->st_shndx != SHN_UNDEF) {
            esym_bind = ELFW(ST_BIND)(esym->st_info);
            /* 传播约束最强的可见性 */
            /* STV_DEFAULT(0)<STV_PROTECTED(3)<STV_HIDDEN(2)<STV_INTERNAL(1) */
            esym_vis = ELFW(ST_VISIBILITY)(esym->st_other);
            if (esym_vis == STV_DEFAULT) {
                new_vis = sym_vis;
            } else if (sym_vis == STV_DEFAULT) {
                new_vis = esym_vis;
            } else {
                new_vis = (esym_vis < sym_vis) ? esym_vis : sym_vis;
            }
            esym->st_other = (esym->st_other & ~ELFW(ST_VISIBILITY)(-1))
                             | new_vis;
            other = esym->st_other; /* 以防需要给 esym 打补丁 */
            if (shndx == SHN_UNDEF) {
                /* 如果对应的符号已经定义，则忽略添加
                   未定义符号的操作 */
            } else if (sym_bind == STB_GLOBAL && esym_bind == STB_WEAK) {
                /* 全局符号覆盖弱符号，所以打补丁 */
                goto do_patch;
            } else if (sym_bind == STB_WEAK && esym_bind == STB_GLOBAL) {
                /* 如果已经是全局符号，则忽略弱符号 */
            } else if (sym_bind == STB_WEAK && esym_bind == STB_WEAK) {
                /* 保留最先找到的弱定义，忽略后续的 */
            } else if (sym_vis == STV_HIDDEN || sym_vis == STV_INTERNAL) {
                /* 之后忽略隐藏符号 */
            } else if ((esym->st_shndx == SHN_COMMON
                            || esym->st_shndx == bss_section->sh_num)
                        && (shndx < SHN_LORESERVE
                            && shndx != bss_section->sh_num)) {
                /* 数据符号优先于 common/bss */
                goto do_patch;
            } else if (shndx == SHN_COMMON || shndx == bss_section->sh_num) {
                /* 数据符号保持优先于 common/bss */
            } else if (s->sh_flags & SHF_DYNSYM) {
                /* 我们接受两个 DLL 定义同一个符号 */
	    } else if (esym->st_other & ST_ASM_SET) {
		/* 如果已有的符号来自 asm .set，
		   我们就可以覆盖它。  */
		goto do_patch;
            } else {
#if 0
                printf("new_bind=%x new_shndx=%x new_vis=%x old_bind=%x old_shndx=%x old_vis=%x\n",
                       sym_bind, shndx, new_vis, esym_bind, esym->st_shndx, esym_vis);
#endif
                tcc_error_noabort("'%s' defined twice", name);
            }
        } else {
        do_patch:
            esym->st_info = ELFW(ST_INFO)(sym_bind, sym_type);
            esym->st_shndx = shndx;
            new_undef_sym = 1;
            esym->st_value = value;
            esym->st_size = size;
            esym->st_other = other;
        }
    } else {
    do_def:
        sym_index = put_elf_sym(s, value, size,
                                ELFW(ST_INFO)(sym_bind, sym_type), other,
                                shndx, name);
    }
    return sym_index;
}

/* 放入重定位 */
ST_FUNC void put_elf_reloca(Section *symtab, Section *s, unsigned long offset,
                            int type, int symbol, addr_t addend)
{
    char buf[256];
    Section *sr;
    ElfW_Rel *rel;

    sr = s->reloc;
    if (!sr) {
        /* 如果没有重定位段，就创建它 */
        snprintf(buf, sizeof(buf), REL_SECTION_FMT, s->name);
        /* 如果 symtab 已分配，那么我们认为重定位
           也已分配 */
        sr = new_section(tcc_state, buf, SHT_RELX, symtab->sh_flags);
        sr->sh_entsize = sizeof(ElfW_Rel);
        sr->link = symtab;
        sr->sh_info = s->sh_num;
        s->reloc = sr;
    }
    rel = section_ptr_add(sr, sizeof(ElfW_Rel));
    rel->r_offset = offset;
    rel->r_info = ELFW(R_INFO)(symbol, type);
#if SHT_RELX == SHT_RELA
    rel->r_addend = addend;
#else
    if (addend)
        tcc_error("non-zero addend on REL architecture");
#endif
}

ST_FUNC void put_elf_reloc(Section *symtab, Section *s, unsigned long offset,
                           int type, int symbol)
{
    put_elf_reloca(symtab, s, offset, type, symbol, 0);
}

/* 删除段 S->reloc 中从 oldrelocoffset 开始、指向同一位置的重定位，
   只保留其中最后一个。作为副作用，重定位会被排序。
   这可能会减少重定位的数量。  */
ST_FUNC void squeeze_multi_relocs(Section *s, size_t oldrelocoffset)
{
    Section *sr = s->reloc;
    ElfW_Rel *r, *dest;
    ssize_t a;
    ElfW(Addr) addr;

    if (oldrelocoffset + sizeof(*r) >= sr->data_offset)
      return;
    /* 我们处理的重定位来自初始化器解析。
       所以它们大多是有序的，而且数量不多。
       其次我们需要稳定的排序（qsort 并不稳定）。我们使用
       简单的插入排序。  */
    for (a = oldrelocoffset + sizeof(*r); a < sr->data_offset; a += sizeof(*r)) {
	ssize_t i = a - sizeof(*r);
	addr = ((ElfW_Rel*)(sr->data + a))->r_offset;
	for (; i >= (ssize_t)oldrelocoffset &&
	       ((ElfW_Rel*)(sr->data + i))->r_offset > addr; i -= sizeof(*r)) {
	    ElfW_Rel tmp = *(ElfW_Rel*)(sr->data + a);
	    *(ElfW_Rel*)(sr->data + a) = *(ElfW_Rel*)(sr->data + i);
	    *(ElfW_Rel*)(sr->data + i) = tmp;
	}
    }

    r = (ElfW_Rel*)(sr->data + oldrelocoffset);
    dest = r;
    for (; r < (ElfW_Rel*)(sr->data + sr->data_offset); r++) {
	if (dest->r_offset != r->r_offset)
	  dest++;
	*dest = *r;
    }
    sr->data_offset = (unsigned char*)dest - sr->data + sizeof(*r);
}

/* 放入 stab 调试信息 */

ST_FUNC void put_stabs(const char *str, int type, int other, int desc,
                      unsigned long value)
{
    Stab_Sym *sym;

    sym = section_ptr_add(stab_section, sizeof(Stab_Sym));
    if (str) {
        sym->n_strx = put_elf_str(stabstr_section, str);
    } else {
        sym->n_strx = 0;
    }
    sym->n_type = type;
    sym->n_other = other;
    sym->n_desc = desc;
    sym->n_value = value;
}

ST_FUNC void put_stabs_r(const char *str, int type, int other, int desc,
                        unsigned long value, Section *sec, int sym_index)
{
    put_stabs(str, type, other, desc, value);
    put_elf_reloc(symtab_section, stab_section,
                  stab_section->data_offset - sizeof(unsigned int),
                  R_DATA_32, sym_index);
}

ST_FUNC void put_stabn(int type, int other, int desc, int value)
{
    put_stabs(NULL, type, other, desc, value);
}

ST_FUNC void put_stabd(int type, int other, int desc)
{
    put_stabs(NULL, type, other, desc, 0);
}

ST_FUNC struct sym_attr *get_sym_attr(TCCState *s1, int index, int alloc)
{
    int n;
    struct sym_attr *tab;

    if (index >= s1->nb_sym_attrs) {
        if (!alloc)
            return s1->sym_attrs;
        /* 找到紧接着的更大的 2 的幂并重新分配数组 */
        n = 1;
        while (index >= n)
            n *= 2;
        tab = tcc_realloc(s1->sym_attrs, n * sizeof(*s1->sym_attrs));
        s1->sym_attrs = tab;
        memset(s1->sym_attrs + s1->nb_sym_attrs, 0,
               (n - s1->nb_sym_attrs) * sizeof(*s1->sym_attrs));
        s1->nb_sym_attrs = n;
    }
    return &s1->sym_attrs[index];
}

/* 在段 <sec> 中从元素 <startoff> 开始，用变量 <elem>
   遍历类型为 <type> 的每个元素 */
#define for_each_elem(sec, startoff, elem, type) \
    for (elem = (type *) sec->data + startoff; \
         elem < (type *) (sec->data + sec->data_offset); elem++)

/* 在 ELF 文件符号表中，局部符号必须位于全局符号
   和弱符号之前。由于 TCC 在生成代码时无法排序，我们必须在
   之后做。所有重定位表也要被修改，以考虑符号表
   排序 */
static void sort_syms(TCCState *s1, Section *s)
{
    int *old_to_new_syms;
    ElfW(Sym) *new_syms;
    int nb_syms, i;
    ElfW(Sym) *p, *q;
    ElfW_Rel *rel;
    Section *sr;
    int type, sym_index;

    nb_syms = s->data_offset / sizeof(ElfW(Sym));
    new_syms = tcc_malloc(nb_syms * sizeof(ElfW(Sym)));
    old_to_new_syms = tcc_malloc(nb_syms * sizeof(int));

    /* 局部符号的第一遍 */
    p = (ElfW(Sym) *)s->data;
    q = new_syms;
    for(i = 0; i < nb_syms; i++) {
        if (ELFW(ST_BIND)(p->st_info) == STB_LOCAL) {
            old_to_new_syms[i] = q - new_syms;
            *q++ = *p;
        }
        p++;
    }
    /* 把局部符号的个数保存在段头中 */
    if( s->sh_size )    /* 这个 'if' 让 IDA 满意 */
        s->sh_info = q - new_syms;

    /* 然后是非局部符号的第二遍 */
    p = (ElfW(Sym) *)s->data;
    for(i = 0; i < nb_syms; i++) {
        if (ELFW(ST_BIND)(p->st_info) != STB_LOCAL) {
            old_to_new_syms[i] = q - new_syms;
            *q++ = *p;
        }
        p++;
    }

    /* 我们把新符号复制到旧符号上 */
    memcpy(s->data, new_syms, nb_syms * sizeof(ElfW(Sym)));
    tcc_free(new_syms);

    /* 现在我们修改所有重定位 */
    for(i = 1; i < s1->nb_sections; i++) {
        sr = s1->sections[i];
        if (sr->sh_type == SHT_RELX && sr->link == s) {
            for_each_elem(sr, 0, rel, ElfW_Rel) {
                sym_index = ELFW(R_SYM)(rel->r_info);
                type = ELFW(R_TYPE)(rel->r_info);
                sym_index = old_to_new_syms[sym_index];
                rel->r_info = ELFW(R_INFO)(sym_index, type);
            }
        }
    }

    tcc_free(old_to_new_syms);
}

/* 重定位符号表，如果 do_resolve 为真则解析未定义符号，
   并在符号未定义时输出错误。 */
ST_FUNC void relocate_syms(TCCState *s1, Section *symtab, int do_resolve)
{
    ElfW(Sym) *sym;
    int sym_bind, sh_num;
    const char *name;

    for_each_elem(symtab, 1, sym, ElfW(Sym)) {
        sh_num = sym->st_shndx;
        if (sh_num == SHN_UNDEF) {
            name = (char *) s1->symtab->link->data + sym->st_name;
            /* 用 ld.so 为我们解析符号（用于 tcc -run） */
            if (do_resolve) {
#if defined TCC_IS_NATIVE
                void *addr = dlsym(RTLD_DEFAULT, name);
                if (addr) {
                    sym->st_value = (addr_t) addr;
#ifdef DEBUG_RELOC
		    printf ("relocate_sym: %s -> 0x%lx\n", name, sym->st_value);
#endif
                    goto found;
                }
#endif
            /* 如果存在动态符号，它将在 relocate_section 中使用 */
            } else if (s1->dynsym && find_elf_sym(s1->dynsym, name))
                goto found;
            /* XXX：_fp_hw 似乎是 ABI 的一部分，所以我们忽略
               它 */
            if (!strcmp(name, "_fp_hw"))
                goto found;
            /* 只有弱符号允许未定义。它们的
               值为零 */
            sym_bind = ELFW(ST_BIND)(sym->st_info);
            if (sym_bind == STB_WEAK)
                sym->st_value = 0;
            else
                tcc_error_noabort("undefined symbol '%s'", name);
        } else if (sh_num < SHN_LORESERVE) {
            /* 加上段基址 */
            sym->st_value += s1->sections[sym->st_shndx]->sh_addr;
        }
    found: ;
    }
}

/* 重定位给定段（与 CPU 相关），方式是应用
   关联重定位段中的重定位 */
ST_FUNC void relocate_section(TCCState *s1, Section *s)
{
    Section *sr = s->reloc;
    ElfW_Rel *rel;
    ElfW(Sym) *sym;
    int type, sym_index;
    unsigned char *ptr;
    addr_t tgt, addr;

    relocate_init(sr);

    for_each_elem(sr, 0, rel, ElfW_Rel) {
        ptr = s->data + rel->r_offset;
        sym_index = ELFW(R_SYM)(rel->r_info);
        sym = &((ElfW(Sym) *)symtab_section->data)[sym_index];
        type = ELFW(R_TYPE)(rel->r_info);
        tgt = sym->st_value;
#if SHT_RELX == SHT_RELA
        tgt += rel->r_addend;
#endif
        addr = s->sh_addr + rel->r_offset;
        relocate(s1, rel, type, ptr, addr, tgt);
    }
    /* 如果重定位已分配，我们改变它的符号表 */
    if (sr->sh_flags & SHF_ALLOC)
        sr->link = s1->dynsym;
}

/* 重定位 'sr' 中的重定位表 */
static void relocate_rel(TCCState *s1, Section *sr)
{
    Section *s;
    ElfW_Rel *rel;

    s = s1->sections[sr->sh_info];
    for_each_elem(sr, 0, rel, ElfW_Rel)
        rel->r_offset += s->sh_addr;
}

/* 统计动态重定位的数量，以便为
   它们预留空间 */
static int prepare_dynamic_rel(TCCState *s1, Section *sr)
{
    ElfW_Rel *rel;
    int sym_index, type, count;

    count = 0;
    for_each_elem(sr, 0, rel, ElfW_Rel) {
        sym_index = ELFW(R_SYM)(rel->r_info);
        type = ELFW(R_TYPE)(rel->r_info);
        switch(type) {
            count++;
            break;
            if (get_sym_attr(s1, sym_index, 0)->dyn_index)
                count++;
            break;
        default:
            break;
        }
    }
    if (count) {
        /* 分配该段 */
        sr->sh_flags |= SHF_ALLOC;
        sr->sh_size = count * sizeof(ElfW_Rel);
    }
    return count;
}

static void build_got(TCCState *s1)
{
    /* 如果没有 got，就创建它 */
    s1->got = new_section(s1, ".got", SHT_PROGBITS, SHF_ALLOC | SHF_WRITE);
    s1->got->sh_entsize = 4;
    set_elf_sym(symtab_section, 0, 4, ELFW(ST_INFO)(STB_GLOBAL, STT_OBJECT),
                0, s1->got->sh_num, "_GLOBAL_OFFSET_TABLE_");
    /* 为 _DYNAMIC 指针和两个哑 got 条目保留空间 */
    section_ptr_add(s1->got, 3 * PTR_SIZE);
}

/* 为 s1->symtab 中的某个符号创建 GOT 以及（用于函数调用时）PLT 条目。
   为 GOT 重定位创建动态符号表条目时，用 'size' 和 'info' 作为对应
   符号的元数据。
   返回 GOT 条目的偏移，或者（如果有）PLT 条目的偏移。 */
static struct sym_attr * put_got_entry(TCCState *s1, int dyn_reloc_type,
                                       unsigned long size,
                                       int info, int sym_index)
{
    int need_plt_entry;
    const char *name;
    ElfW(Sym) *sym;
    struct sym_attr *attr;
    unsigned got_offset;
    char plt_name[100];
    int len;

    need_plt_entry = (dyn_reloc_type == R_JMP_SLOT);
    attr = get_sym_attr(s1, sym_index, 1);

    /* 如果一个函数既被调用又取了地址，会创建 2 个 GOT 条目，
       一个用于取地址（GOT），另一个用于 PLT
       条目（PLTGOT）。  */
    if (need_plt_entry ? attr->plt_offset : attr->got_offset)
        return attr;

    /* 创建 GOT 条目 */
    got_offset = s1->got->data_offset;
    section_ptr_add(s1->got, PTR_SIZE);

    /* 创建把目标对象或函数的地址填入 GOT 条目的重定位。
       对内存输出（dlsym 会把符号地址给我们）这是静态重定位，
       否则（可执行文件和 DLL）是动态重定位。对于带
       *_JUMP_SLOT 重定位类型的 GOT 条目（即与 PLT 条目
       关联的那个）本应延迟完成重定位，但出于未知
       原因目前在加载时
       就完成了。 */

    sym = &((ElfW(Sym) *) symtab_section->data)[sym_index];
    name = (char *) symtab_section->link->data + sym->st_name;

    if (s1->dynsym) {
	if (ELFW(ST_BIND)(sym->st_info) == STB_LOCAL) {
	    /* 权宜之计警报。我们不想为 STB_LOCAL 符号生成动态符号
	       和基于符号的重定位，而是想直接解析它们。此时符号
	       值还不是最终值，所以必须推迟。之后我们无论如何都
	       要创建一个 RELATIVE 重定位，所以我们滥用重定位槽
	       来偷偷保存符号引用，直到
	       fill_local_got_entries。
	       注意 sym_index 是相对于 symtab_section 的，
	       不是
	       s1->dynsym！不过我们使用 s1->dyn_sym，这样如果这
	       是第一次调用，got->reloc 会被正确创建。还要注意
	       RELATIVE 重定位通常不会为 .got 创建，
	       所以这里类型充当后续的标记（并且也保留到
	       最终输出中，这没问题，因为那时
	       got 只是普通数据）。  */
	    put_elf_reloc(s1->dynsym, s1->got, got_offset, R_RELATIVE,
			  sym_index);
	} else {
	    if (0 == attr->dyn_index)
                attr->dyn_index = set_elf_sym(s1->dynsym, sym->st_value, size,
					      info, 0, sym->st_shndx, name);
	    put_elf_reloc(s1->dynsym, s1->got, got_offset, dyn_reloc_type,
			  attr->dyn_index);
	}
    } else {
        put_elf_reloc(symtab_section, s1->got, got_offset, dyn_reloc_type,
                      sym_index);
    }

    if (need_plt_entry) {
        if (!s1->plt) {
    	    s1->plt = new_section(s1, ".plt", SHT_PROGBITS,
    			          SHF_ALLOC | SHF_EXECINSTR);
    	    s1->plt->sh_entsize = 4;
        }

        attr->plt_offset = create_plt_entry(s1, got_offset, attr);

        /* 为 PLT 跳转向量创建符号 'sym@plt' */
        len = strlen(name);
        if (len > sizeof plt_name - 5)
            len = sizeof plt_name - 5;
        memcpy(plt_name, name, len);
        strcpy(plt_name + len, "@plt");
        attr->plt_sym = put_elf_sym(s1->symtab, attr->plt_offset, sym->st_size,
            ELFW(ST_INFO)(STB_GLOBAL, STT_FUNC), 0, s1->plt->sh_num, plt_name);

    } else {
        attr->got_offset = got_offset;
    }

    return attr;
}

/* 构建 GOT 和 PLT 条目 */
ST_FUNC void build_got_entries(TCCState *s1)
{
    Section *s;
    ElfW_Rel *rel;
    ElfW(Sym) *sym;
    int i, type, gotplt_entry, reloc_type, sym_index;
    struct sym_attr *attr;

    for(i = 1; i < s1->nb_sections; i++) {
        s = s1->sections[i];
        if (s->sh_type != SHT_RELX)
            continue;
        /* 不需要处理 got 重定位 */
        if (s->link != symtab_section)
            continue;
        for_each_elem(s, 0, rel, ElfW_Rel) {
            type = ELFW(R_TYPE)(rel->r_info);
            gotplt_entry = gotplt_entry_type(type);
            sym_index = ELFW(R_SYM)(rel->r_info);
            sym = &((ElfW(Sym) *)symtab_section->data)[sym_index];

            if (gotplt_entry == NO_GOTPLT_ENTRY) {
                continue;
            }

            /* 如果是未定义引用（在运行时解析），或者符号是
	       绝对的（可能由 tcc_add_symbol 创建，因此在 64 位
	       目标上可能离应用程序代码太远），就自动创建
	       PLT/GOT [条目]。  */
            if (gotplt_entry == AUTO_GOTPLT_ENTRY) {
                if (sym->st_shndx == SHN_UNDEF) {
                    ElfW(Sym) *esym;
		    int dynindex;
                    if (s1->output_type == TCC_OUTPUT_DLL && ! PCRELATIVE_DLLPLT)
                        continue;
		    /* UNDEF 符号的重定位通常需要
		       转移到可执行文件或共享对象中。
		       如果那样做，AUTO_GOTPLT_ENTRY 就不会存在。
		       但 TCC 不这样做（至少对可执行文件不这样），所以我们
		       需要在本地解析所有这类重定位。这
		       意味着为 DLL 中的函数准备 PLT 槽，为
		       数据符号准备 COPY 重定位。COPY 重定位在
		       bind_exe_dynsyms 中生成（并且符号被调整为已定义），
		       而为函数生成的是函数类型的
		       动态符号。  */
		    if (s1->dynsym) {
			/* 对 -run 而言 dynsym 没有设置 :-/  */
			dynindex = get_sym_attr(s1, sym_index, 0)->dyn_index;
			esym = (ElfW(Sym) *)s1->dynsym->data + dynindex;
			if (dynindex
			    && (ELFW(ST_TYPE)(esym->st_info) == STT_FUNC
				|| (ELFW(ST_TYPE)(esym->st_info) == STT_NOTYPE
				    && ELFW(ST_TYPE)(sym->st_info) == STT_FUNC)))
			    goto jmp_slot;
		    }
                } else if (!(sym->st_shndx == SHN_ABS
			&& PTR_SIZE == 8
			))
                    continue;
            }

            if (code_reloc(type)) {
            jmp_slot:
                reloc_type = R_JMP_SLOT;
            } else
                reloc_type = R_GLOB_DAT;

            if (!s1->got)
                build_got(s1);

            if (gotplt_entry == BUILD_GOT_ONLY)
                continue;

            attr = put_got_entry(s1, reloc_type, sym->st_size, sym->st_info,
                                 sym_index);

            if (reloc_type == R_JMP_SLOT)
                rel->r_info = ELFW(R_INFO)(attr->plt_sym, type);
        }
    }
}

/* 放入动态标签 */
static void put_dt(Section *dynamic, int dt, addr_t val)
{
    ElfW(Dyn) *dyn;
    dyn = section_ptr_add(dynamic, sizeof(ElfW(Dyn)));
    dyn->d_tag = dt;
    dyn->d_un.d_val = val;
}

static void add_init_array_defines(TCCState *s1, const char *section_name)
{
    Section *s;
    long end_offset;
    char sym_start[1024];
    char sym_end[1024];

    snprintf(sym_start, sizeof(sym_start), "__%s_start", section_name + 1);
    snprintf(sym_end, sizeof(sym_end), "__%s_end", section_name + 1);

    s = find_section(s1, section_name);
    if (!s) {
        end_offset = 0;
        s = data_section;
    } else {
        end_offset = s->data_offset;
    }

    set_elf_sym(symtab_section,
                0, 0,
                ELFW(ST_INFO)(STB_GLOBAL, STT_NOTYPE), 0,
                s->sh_num, sym_start);
    set_elf_sym(symtab_section,
                end_offset, 0,
                ELFW(ST_INFO)(STB_GLOBAL, STT_NOTYPE), 0,
                s->sh_num, sym_end);
}

static int tcc_add_support(TCCState *s1, const char *filename)
{
    char buf[1024];
    snprintf(buf, sizeof(buf), "%s/%s", s1->tcc_lib_path, filename);
    return tcc_add_file(s1, buf);
}

ST_FUNC void tcc_add_bcheck(TCCState *s1)
{
#ifdef CONFIG_TCC_BCHECK
    addr_t *ptr;
    int sym_index;

    if (0 == s1->do_bounds_check)
        return;
    /* XXX：添加一个目标文件来做这件事 */
    ptr = section_ptr_add(bounds_section, sizeof(*ptr));
    *ptr = 0;
    set_elf_sym(symtab_section, 0, 0,
                ELFW(ST_INFO)(STB_GLOBAL, STT_NOTYPE), 0,
                bounds_section->sh_num, "__bounds_start");
    /* 从 libtcc1.a 中提取 bcheck.o */
    sym_index = set_elf_sym(symtab_section, 0, 0,
                ELFW(ST_INFO)(STB_GLOBAL, STT_NOTYPE), 0,
                SHN_UNDEF, "__bound_init");
    if (s1->output_type != TCC_OUTPUT_MEMORY) {
        /* 在 .init 段中添加 'call __bound_init()' */
        Section *init_section = find_section(s1, ".init");
        unsigned char *pinit = section_ptr_add(init_section, 5);
        pinit[0] = 0xe8;
        write32le(pinit + 1, -4);
        put_elf_reloc(symtab_section, init_section,
            init_section->data_offset - 4, R_386_PC32, sym_index);
            /* R_386_PC32 = R_X86_64_PC32 = 2 */
    }
#endif
}

/* 添加 tcc 运行时库 */
ST_FUNC void tcc_add_runtime(TCCState *s1)
{
    tcc_add_bcheck(s1);
    tcc_add_pragma_libs(s1);
    /* 添加 libc */
    if (!s1->nostdlib) {
        tcc_add_library_err(s1, "c");
#ifdef TCC_LIBGCC
        if (!s1->static_link) {
            if (TCC_LIBGCC[0] == '/')
                tcc_add_file(s1, TCC_LIBGCC);
            else
                tcc_add_dll(s1, TCC_LIBGCC, 0);
        }
#endif
        tcc_add_support(s1, TCC_LIBTCC1);
        /* 如果不是内存输出，则添加 crt end */
        if (s1->output_type != TCC_OUTPUT_MEMORY)
            tcc_add_crt(s1, "crtn.o");
    }
}

/* 添加各种标准链接器符号（必须在各段填入
   之后再做（例如在分配 common
   符号之后）） */
static void tcc_add_linker_symbols(TCCState *s1)
{
    char buf[1024];
    int i;
    Section *s;

    set_elf_sym(symtab_section,
                text_section->data_offset, 0,
                ELFW(ST_INFO)(STB_GLOBAL, STT_NOTYPE), 0,
                text_section->sh_num, "_etext");
    set_elf_sym(symtab_section,
                data_section->data_offset, 0,
                ELFW(ST_INFO)(STB_GLOBAL, STT_NOTYPE), 0,
                data_section->sh_num, "_edata");
    set_elf_sym(symtab_section,
                bss_section->data_offset, 0,
                ELFW(ST_INFO)(STB_GLOBAL, STT_NOTYPE), 0,
                bss_section->sh_num, "_end");
    /* 讨厌的新标准 ldscript 定义 */
    add_init_array_defines(s1, ".preinit_array");
    add_init_array_defines(s1, ".init_array");
    add_init_array_defines(s1, ".fini_array");

    /* 为名字可以用 C 表达的段添加 start 和
       stop 符号 */
    for(i = 1; i < s1->nb_sections; i++) {
        s = s1->sections[i];
        if (s->sh_type == SHT_PROGBITS &&
            (s->sh_flags & SHF_ALLOC)) {
            const char *p;
            int ch;

            /* 检查段名是否可以用 C 表达 */
            p = s->name;
            for(;;) {
                ch = *p;
                if (!ch)
                    break;
                if (!isid(ch) && !isnum(ch))
                    goto next_sec;
                p++;
            }
            snprintf(buf, sizeof(buf), "__start_%s", s->name);
            set_elf_sym(symtab_section,
                        0, 0,
                        ELFW(ST_INFO)(STB_GLOBAL, STT_NOTYPE), 0,
                        s->sh_num, buf);
            snprintf(buf, sizeof(buf), "__stop_%s", s->name);
            set_elf_sym(symtab_section,
                        s->data_offset, 0,
                        ELFW(ST_INFO)(STB_GLOBAL, STT_NOTYPE), 0,
                        s->sh_num, buf);
        }
    next_sec: ;
    }
}

ST_FUNC void resolve_common_syms(TCCState *s1)
{
    ElfW(Sym) *sym;

    /* 在 BSS 中分配 common 符号。  */
    for_each_elem(symtab_section, 1, sym, ElfW(Sym)) {
        if (sym->st_shndx == SHN_COMMON) {
            /* 对 SHN_COMMON 而言符号对齐在 st_value 中 */
	    sym->st_value = section_add(bss_section, sym->st_size,
					sym->st_value);
            sym->st_shndx = bss_section->sh_num;
        }
    }

    /* 现在把值赋给链接器提供的符号。  */
    tcc_add_linker_symbols(s1);
}

static void tcc_output_binary(TCCState *s1, FILE *f,
                              const int *sec_order)
{
    Section *s;
    int i, offset, size;

    offset = 0;
    for(i=1;i<s1->nb_sections;i++) {
        s = s1->sections[sec_order[i]];
        if (s->sh_type != SHT_NOBITS &&
            (s->sh_flags & SHF_ALLOC)) {
            while (offset < s->sh_offset) {
                fputc(0, f);
                offset++;
            }
            size = s->sh_size;
            fwrite(s->data, 1, size, f);
            offset += size;
        }
    }
}

ST_FUNC void fill_got_entry(TCCState *s1, ElfW_Rel *rel)
{
    int sym_index = ELFW(R_SYM) (rel->r_info);
    ElfW(Sym) *sym = &((ElfW(Sym) *) symtab_section->data)[sym_index];
    struct sym_attr *attr = get_sym_attr(s1, sym_index, 0);
    unsigned offset = attr->got_offset;

    if (0 == offset)
        return;
    section_reserve(s1->got, offset + PTR_SIZE);
#if PTR_SIZE == 8
    write64le(s1->got->data + offset, sym->st_value);
#else
    write32le(s1->got->data + offset, sym->st_value);
#endif
}

/* 对 GOT 或 PLT 条目执行重定位 */
ST_FUNC void fill_got(TCCState *s1)
{
    Section *s;
    ElfW_Rel *rel;
    int i;

    for(i = 1; i < s1->nb_sections; i++) {
        s = s1->sections[i];
        if (s->sh_type != SHT_RELX)
            continue;
        /* 不需要处理 got 重定位 */
        if (s->link != symtab_section)
            continue;
        for_each_elem(s, 0, rel, ElfW_Rel) {
            switch (ELFW(R_TYPE) (rel->r_info)) {
                case R_X86_64_GOT32:
                case R_X86_64_GOTPCREL:
		case R_X86_64_GOTPCRELX:
		case R_X86_64_REX_GOTPCRELX:
                case R_X86_64_PLT32:
                    fill_got_entry(s1, rel);
                    break;
            }
        }
    }
}

/* 参见 put_got_entry 中的说明。这是第二阶段，
   在此把对局部已定义符号的 GOT 引用重写。  */
static void fill_local_got_entries(TCCState *s1)
{
    ElfW_Rel *rel;
    for_each_elem(s1->got->reloc, 0, rel, ElfW_Rel) {
	if (ELFW(R_TYPE)(rel->r_info) == R_RELATIVE) {
	    int sym_index = ELFW(R_SYM) (rel->r_info);
	    ElfW(Sym) *sym = &((ElfW(Sym) *) symtab_section->data)[sym_index];
	    struct sym_attr *attr = get_sym_attr(s1, sym_index, 0);
	    unsigned offset = attr->got_offset;
	    if (offset != rel->r_offset - s1->got->sh_addr)
	      tcc_error_noabort("huh");
	    rel->r_info = ELFW(R_INFO)(0, R_RELATIVE);
#if SHT_RELX == SHT_RELA
	    rel->r_addend = sym->st_value;
#else
	    /* 我们所有的 REL 架构碰巧也是 32 位小端。  */
	    write32le(s1->got->data + offset, sym->st_value);
#endif
	}
    }
}

/* 绑定可执行文件的符号：从共享库导出的符号中解析未定义符号，
   如果命令行给出了 -rdynamic 选项，则把非局部的已定义符号
   导出到共享库 */
static void bind_exe_dynsyms(TCCState *s1)
{
    const char *name;
    int sym_index, index;
    ElfW(Sym) *sym, *esym;
    int type;

    /* 从动态符号中解析未定义符号。当匹配时：
       - 如果是 STT_FUNC 或 STT_GNU_IFUNC 符号 -> 加入 PLT
       - 如果是 STT_OBJECT 符号 -> 用合适的重定位加入 .bss 段 */
    for_each_elem(symtab_section, 1, sym, ElfW(Sym)) {
        if (sym->st_shndx == SHN_UNDEF) {
            name = (char *) symtab_section->link->data + sym->st_name;
            sym_index = find_elf_sym(s1->dynsymtab_section, name);
            if (sym_index) {
                esym = &((ElfW(Sym) *)s1->dynsymtab_section->data)[sym_index];
                type = ELFW(ST_TYPE)(esym->st_info);
                if ((type == STT_FUNC) || (type == STT_GNU_IFUNC)) {
                    /* 间接函数在可执行文件的
                     * dynsym 段中应具有 STT_FUNC 类型。确实，懒解析
                     * 之后的 dlsym 调用会从
                     * 可执行文件的 dynsym 条目中取符号值，而那里面
                     * 会包含 dlsym 调用者想要的函数地址，而不是
                     * 会返回该地址的函数
                     * 的地址 */
                    int dynindex
		      = put_elf_sym(s1->dynsym, 0, esym->st_size,
				    ELFW(ST_INFO)(STB_GLOBAL,STT_FUNC), 0, 0,
				    name);
		    int index = sym - (ElfW(Sym) *) symtab_section->data;
		    get_sym_attr(s1, index, 1)->dyn_index = dynindex;
                } else if (type == STT_OBJECT) {
                    unsigned long offset;
                    ElfW(Sym) *dynsym;
                    offset = bss_section->data_offset;
                    /* XXX：用哪种对齐？ */
                    offset = (offset + 16 - 1) & -16;
                    set_elf_sym (s1->symtab, offset, esym->st_size,
                                 esym->st_info, 0, bss_section->sh_num, name);
                    index = put_elf_sym(s1->dynsym, offset, esym->st_size,
                                        esym->st_info, 0, bss_section->sh_num,
                                        name);

                    /* 确保 R_COPY 对弱符号别名有效 */
                    if (ELFW(ST_BIND)(esym->st_info) == STB_WEAK) {
                        for_each_elem(s1->dynsymtab_section, 1, dynsym, ElfW(Sym)) {
                            if ((dynsym->st_value == esym->st_value)
                                && (ELFW(ST_BIND)(dynsym->st_info) == STB_GLOBAL)) {
                                char *dynname = (char *) s1->dynsymtab_section->link->data
                                                + dynsym->st_name;
                                put_elf_sym(s1->dynsym, offset, dynsym->st_size,
                                            dynsym->st_info, 0,
                                            bss_section->sh_num, dynname);
                                break;
                            }
                        }
                    }

                    put_elf_reloc(s1->dynsym, bss_section,
                                  offset, R_COPY, index);
                    offset += esym->st_size;
                    bss_section->data_offset = offset;
                }
            } else {
                /* STB_WEAK 未定义符号是允许的 */
                /* XXX：_fp_hw 似乎是 ABI 的一部分，所以我们忽略它 */
                if (ELFW(ST_BIND)(sym->st_info) == STB_WEAK ||
                    !strcmp(name, "_fp_hw")) {
                } else {
                    tcc_error_noabort("undefined symbol '%s'", name);
                }
            }
        } else if (s1->rdynamic && ELFW(ST_BIND)(sym->st_info) != STB_LOCAL) {
            /* 如果有 -rdynamic 选项，则导出所有非局部符号 */
            name = (char *) symtab_section->link->data + sym->st_name;
            set_elf_sym(s1->dynsym, sym->st_value, sym->st_size, sym->st_info,
                        0, sym->st_shndx, name);
        }
    }
}

/* 绑定库的符号：导出可执行文件中被共享库引用的所有非局部符号。
   原因是动态加载器先在可执行文件中搜索符号，然后在
   库中搜索。因此对某个已由库定义的符号的引用仍然
   可以由可执行文件中的符号
   解析。 */
static void bind_libs_dynsyms(TCCState *s1)
{
    const char *name;
    int sym_index;
    ElfW(Sym) *sym, *esym;

    for_each_elem(s1->dynsymtab_section, 1, esym, ElfW(Sym)) {
        name = (char *) s1->dynsymtab_section->link->data + esym->st_name;
        sym_index = find_elf_sym(symtab_section, name);
        sym = &((ElfW(Sym) *)symtab_section->data)[sym_index];
        if (sym_index && sym->st_shndx != SHN_UNDEF
            && ELFW(ST_BIND)(sym->st_info) != STB_LOCAL) {
            set_elf_sym(s1->dynsym, sym->st_value, sym->st_size,
                sym->st_info, 0, sym->st_shndx, name);
        } else if (esym->st_shndx == SHN_UNDEF) {
            /* 弱符号可以保持未定义 */
            if (ELFW(ST_BIND)(esym->st_info) != STB_WEAK)
                tcc_warning("undefined dynamic symbol '%s'", name);
        }
    }
}

/* 导出所有非局部符号。共享库用它来让它们定义的非局部符号
   能够解析另一个共享库或可执行文件中的引用。相应地，
   它也允许未定义的局部符号由其他共享库或
   可执行文件解析。 */
static void export_global_syms(TCCState *s1)
{
    int dynindex, index;
    const char *name;
    ElfW(Sym) *sym;

    for_each_elem(symtab_section, 1, sym, ElfW(Sym)) {
        if (ELFW(ST_BIND)(sym->st_info) != STB_LOCAL) {
	    name = (char *) symtab_section->link->data + sym->st_name;
	    dynindex = put_elf_sym(s1->dynsym, sym->st_value, sym->st_size,
				   sym->st_info, 0, sym->st_shndx, name);
	    index = sym - (ElfW(Sym) *) symtab_section->data;
            get_sym_attr(s1, index, 1)->dyn_index = dynindex;
        }
    }
}

/* 为段名分配字符串，并判断某个未分配的段
   是否应当输出。
   注意：strsec 段排在最后，所以它的大小也是正确的！ */
static int alloc_sec_names(TCCState *s1, int file_type, Section *strsec)
{
    int i;
    Section *s;
    int textrel = 0;

    /* 为段名分配字符串 */
    for(i = 1; i < s1->nb_sections; i++) {
        s = s1->sections[i];
        /* 生成 DLL 时，我们包含重定位，但可能会
           对它们打补丁 */
        if (file_type == TCC_OUTPUT_DLL &&
            s->sh_type == SHT_RELX &&
            !(s->sh_flags & SHF_ALLOC) &&
            (s1->sections[s->sh_info]->sh_flags & SHF_ALLOC) &&
            prepare_dynamic_rel(s1, s)) {
                if (s1->sections[s->sh_info]->sh_flags & SHF_EXECINSTR)
                    textrel = 1;
        } else if (s1->do_debug ||
            file_type == TCC_OUTPUT_OBJ ||
            (s->sh_flags & SHF_ALLOC) ||
	    i == (s1->nb_sections - 1)) {
            /* 如果是调试或目标文件，我们输出所有段 */
            s->sh_size = s->data_offset;
        }
	if (s->sh_size || (s->sh_flags & SHF_ALLOC))
            s->sh_name = put_elf_str(strsec, s->name);
    }
    strsec->sh_size = strsec->data_offset;
    return textrel;
}

/*
 * dyn_inf —— 输出共享库/可执行文件时，填进 .dynamic 段的信息
 *
 * 由 tcc_output_file() 调用 set_elf_sections()（分配段地址的循环）时逐段累积，
 * 最后交给 fill_dynamic() 生成 DT_* 条目：
 *   dynamic      .dynamic 段本身；
 *   dynstr       .dynstr 段（DT_STRTAB/DT_STRSZ 取自它）；
 *   data_offset  保留字段；
 *   rel_addr/rel_size  重定位表（.rela/.rel 或 PLT 重定位表）的地址与总大小，
 *                用于 DT_RELA/DT_RELASZ、DT_REL/DT_RELSZ、DT_JMPREL/DT_PLTRELSZ；
 *   bss_addr/bss_size  仅 FreeBSD 的 32 位路径使用，充当 DT_REL/DT_RELSZ。
 */
struct dyn_inf {
    Section *dynamic;
    Section *dynstr;
    unsigned long data_offset;
    addr_t rel_addr;
    addr_t rel_size;
#if defined(__FreeBSD__) || defined(__FreeBSD_kernel__)
    addr_t bss_addr;
    addr_t bss_size;
#endif
};

/* 把段分配给内存段（segment），并决定加载到内存时各段如何布局。
   该函数还填充相应的程序头。 */
static int layout_sections(TCCState *s1, ElfW(Phdr) *phdr, int phnum,
                           Section *interp, Section* strsec,
                           struct dyn_inf *dyninf, int *sec_order)
{
    int i, j, k, file_type, sh_order_index, file_offset;
    unsigned long s_align;
    long long tmp;
    addr_t addr;
    ElfW(Phdr) *ph;
    Section *s;

    file_type = s1->output_type;
    sh_order_index = 1;
    file_offset = 0;
    if (s1->output_format == TCC_OUTPUT_FORMAT_ELF)
        file_offset = sizeof(ElfW(Ehdr)) + phnum * sizeof(ElfW(Phdr));
    s_align = ELF_PAGE_SIZE;
    if (s1->section_align)
        s_align = s1->section_align;

    if (phnum > 0) {
        if (s1->has_text_addr) {
            int a_offset, p_offset;
            addr = s1->text_addr;
            /* 我们确保 (addr % ELF_PAGE_SIZE) == file_offset %
               ELF_PAGE_SIZE */
            a_offset = (int) (addr & (s_align - 1));
            p_offset = file_offset & (s_align - 1);
            if (a_offset < p_offset)
                a_offset += s_align;
            file_offset += (a_offset - p_offset);
        } else {
            if (file_type == TCC_OUTPUT_DLL)
                addr = 0;
            else
                addr = ELF_START_ADDR;
            /* 计算各头部之后的地址 */
            addr += (file_offset & (s_align - 1));
        }

        ph = &phdr[0];
        /* 如果需要，为程序解释器和程序头表各留一个
           程序头。这些稍后再做，因为它们要求
           先完成段布局。 */
        if (interp)
            ph += 2;

        /* .dynamic 段的动态重定位表信息 */
        dyninf->rel_addr = dyninf->rel_size = 0;
#if defined(__FreeBSD__) || defined(__FreeBSD_kernel__)
        dyninf->bss_addr = dyninf->bss_size = 0;
#endif

        for(j = 0; j < 2; j++) {
            ph->p_type = PT_LOAD;
            if (j == 0)
                ph->p_flags = PF_R | PF_X;
            else
                ph->p_flags = PF_R | PF_W;
            ph->p_align = s_align;

            /* 决定加载到内存中的段如何布局。这必须在填充程序头
               之前完成，因为程序头包含布局信息。我们按以下
               顺序排列：interp、符号表、重定位、
               progbits、nobits */
            /* XXX：做更快更简单的排序 */
            for(k = 0; k < 5; k++) {
                for(i = 1; i < s1->nb_sections; i++) {
                    s = s1->sections[i];
                    /* 计算是否应包含该段 */
                    if (j == 0) {
                        if ((s->sh_flags & (SHF_ALLOC | SHF_WRITE)) !=
                            SHF_ALLOC)
                            continue;
                    } else {
                        if ((s->sh_flags & (SHF_ALLOC | SHF_WRITE)) !=
                            (SHF_ALLOC | SHF_WRITE))
                            continue;
                    }
                    if (s == interp) {
                        if (k != 0)
                            continue;
                    } else if (s->sh_type == SHT_DYNSYM ||
                               s->sh_type == SHT_STRTAB ||
                               s->sh_type == SHT_HASH) {
                        if (k != 1)
                            continue;
                    } else if (s->sh_type == SHT_RELX) {
                        if (k != 2)
                            continue;
                    } else if (s->sh_type == SHT_NOBITS) {
                        if (k != 4)
                            continue;
                    } else {
                        if (k != 3)
                            continue;
                    }
                    sec_order[sh_order_index++] = i;

                    /* 段匹配：我们对齐它并加上它的大小 */
                    tmp = addr;
                    addr = (addr + s->sh_addralign - 1) &
                        ~(s->sh_addralign - 1);
                    file_offset += (int) ( addr - tmp );
                    s->sh_offset = file_offset;
                    s->sh_addr = addr;

                    /* 更新程序头信息 */
                    if (ph->p_offset == 0) {
                        ph->p_offset = file_offset;
                        ph->p_vaddr = addr;
                        ph->p_paddr = ph->p_vaddr;
                    }
                    /* 更新动态重定位信息 */
                    if (s->sh_type == SHT_RELX) {
#if defined(__FreeBSD__) || defined(__FreeBSD_kernel__)
                        if (!strcmp(strsec->data + s->sh_name, ".rel.got")) {
                            dyninf->rel_addr = addr;
                            dyninf->rel_size += s->sh_size; /* XXX 只算第一个重定位。 */
                        }
                        if (!strcmp(strsec->data + s->sh_name, ".rel.bss")) {
                            dyninf->bss_addr = addr;
                            dyninf->bss_size = s->sh_size; /* XXX 只算第一个重定位。 */
                        }
#else
                        if (dyninf->rel_size == 0)
                            dyninf->rel_addr = addr;
                        dyninf->rel_size += s->sh_size;
#endif
                    }
                    addr += s->sh_size;
                    if (s->sh_type != SHT_NOBITS)
                        file_offset += s->sh_size;
                }
            }
	    if (j == 0) {
		/* 让第一个 PT_LOAD 内存段包含程序头
		   自身（以及 ELF 头），这样内存占用相同，
		   但能让 binutils strip 等各种工具
		   更好地工作。  */
		ph->p_offset &= ~(ph->p_align - 1);
		ph->p_vaddr &= ~(ph->p_align - 1);
		ph->p_paddr &= ~(ph->p_align - 1);
	    }
            ph->p_filesz = file_offset - ph->p_offset;
            ph->p_memsz = addr - ph->p_vaddr;
            ph++;
            if (j == 0) {
                if (s1->output_format == TCC_OUTPUT_FORMAT_ELF) {
                    /* 如果位于页中间，我们会在内存中
                       复制该页，使一份副本是 RX，另一份是 RW */
                    if ((addr & (s_align - 1)) != 0)
                        addr += s_align;
                } else {
                    addr = (addr + s_align - 1) & ~(s_align - 1);
                    file_offset = (file_offset + s_align - 1) & ~(s_align - 1);
                }
            }
        }
    }

    /* 所有其他段排在后面 */
    for(i = 1; i < s1->nb_sections; i++) {
        s = s1->sections[i];
        if (phnum > 0 && (s->sh_flags & SHF_ALLOC))
            continue;
        sec_order[sh_order_index++] = i;

        file_offset = (file_offset + s->sh_addralign - 1) &
            ~(s->sh_addralign - 1);
        s->sh_offset = file_offset;
        if (s->sh_type != SHT_NOBITS)
            file_offset += s->sh_size;
    }

    return file_offset;
}

static void fill_unloadable_phdr(ElfW(Phdr) *phdr, int phnum, Section *interp,
                                 Section *dynamic)
{
    ElfW(Phdr) *ph;

    /* 如果有解释器，则添加相应的程序头 */
    if (interp) {
        ph = &phdr[0];

        ph->p_type = PT_PHDR;
        ph->p_offset = sizeof(ElfW(Ehdr));
        ph->p_filesz = ph->p_memsz = phnum * sizeof(ElfW(Phdr));
        ph->p_vaddr = interp->sh_addr - ph->p_filesz;
        ph->p_paddr = ph->p_vaddr;
        ph->p_flags = PF_R | PF_X;
        ph->p_align = 4; /* interp->sh_addralign; */
        ph++;

        ph->p_type = PT_INTERP;
        ph->p_offset = interp->sh_offset;
        ph->p_vaddr = interp->sh_addr;
        ph->p_paddr = ph->p_vaddr;
        ph->p_filesz = interp->sh_size;
        ph->p_memsz = interp->sh_size;
        ph->p_flags = PF_R;
        ph->p_align = interp->sh_addralign;
    }

    /* 如果有动态段，则添加相应的程序头 */
    if (dynamic) {
        ph = &phdr[phnum - 1];

        ph->p_type = PT_DYNAMIC;
        ph->p_offset = dynamic->sh_offset;
        ph->p_vaddr = dynamic->sh_addr;
        ph->p_paddr = ph->p_vaddr;
        ph->p_filesz = dynamic->sh_size;
        ph->p_memsz = dynamic->sh_size;
        ph->p_flags = PF_R | PF_W;
        ph->p_align = dynamic->sh_addralign;
    }
}

/* 用描述各段地址和大小的标签填充动态段
   */
static void fill_dynamic(TCCState *s1, struct dyn_inf *dyninf)
{
    Section *dynamic = dyninf->dynamic;

    /* 放入动态段条目 */
    put_dt(dynamic, DT_HASH, s1->dynsym->hash->sh_addr);
    put_dt(dynamic, DT_STRTAB, dyninf->dynstr->sh_addr);
    put_dt(dynamic, DT_SYMTAB, s1->dynsym->sh_addr);
    put_dt(dynamic, DT_STRSZ, dyninf->dynstr->data_offset);
    put_dt(dynamic, DT_SYMENT, sizeof(ElfW(Sym)));
#if PTR_SIZE == 8
    put_dt(dynamic, DT_RELA, dyninf->rel_addr);
    put_dt(dynamic, DT_RELASZ, dyninf->rel_size);
    put_dt(dynamic, DT_RELAENT, sizeof(ElfW_Rel));
#else
#if defined(__FreeBSD__) || defined(__FreeBSD_kernel__)
    put_dt(dynamic, DT_PLTGOT, s1->got->sh_addr);
    put_dt(dynamic, DT_PLTRELSZ, dyninf->rel_size);
    put_dt(dynamic, DT_JMPREL, dyninf->rel_addr);
    put_dt(dynamic, DT_PLTREL, DT_REL);
    put_dt(dynamic, DT_REL, dyninf->bss_addr);
    put_dt(dynamic, DT_RELSZ, dyninf->bss_size);
#else
    put_dt(dynamic, DT_REL, dyninf->rel_addr);
    put_dt(dynamic, DT_RELSZ, dyninf->rel_size);
    put_dt(dynamic, DT_RELENT, sizeof(ElfW_Rel));
#endif
#endif
    if (s1->do_debug)
        put_dt(dynamic, DT_DEBUG, 0);
    put_dt(dynamic, DT_NULL, 0);
}

/* 重定位剩余的段和符号（即那些与动态链接
   无关的） */
static int final_sections_reloc(TCCState *s1)
{
    int i;
    Section *s;

    relocate_syms(s1, s1->symtab, 0);

    if (s1->nb_errors != 0)
        return -1;

    /* 重定位各段 */
    /* XXX：忽略带已分配重定位的段？ */
    for(i = 1; i < s1->nb_sections; i++) {
        s = s1->sections[i];
#if defined(TCC_MUSL)
        if (s->reloc && s != s1->got && (s->sh_flags & SHF_ALLOC)) //gr
#else
        if (s->reloc && s != s1->got)
#endif
            relocate_section(s1, s);
    }

    /* 如果重定位表已分配在可执行文件中，
       则重定位重定位条目 */
    for(i = 1; i < s1->nb_sections; i++) {
        s = s1->sections[i];
        if ((s->sh_flags & SHF_ALLOC) &&
            s->sh_type == SHT_RELX) {
            relocate_rel(s1, s);
        }
    }
    return 0;
}

/* 在磁盘上创建 ELF 文件。
   该函数处理 ELF 特有的布局要求 */
static void tcc_output_elf(TCCState *s1, FILE *f, int phnum, ElfW(Phdr) *phdr,
                           int file_offset, int *sec_order)
{
    int i, shnum, offset, size, file_type;
    Section *s;
    ElfW(Ehdr) ehdr;
    ElfW(Shdr) shdr, *sh;

    file_type = s1->output_type;
    shnum = s1->nb_sections;

    memset(&ehdr, 0, sizeof(ehdr));

    if (phnum > 0) {
        ehdr.e_phentsize = sizeof(ElfW(Phdr));
        ehdr.e_phnum = phnum;
        ehdr.e_phoff = sizeof(ElfW(Ehdr));
    }

    /* 对齐到 4 */
    file_offset = (file_offset + 3) & -4;

    /* 填充头部 */
    ehdr.e_ident[0] = ELFMAG0;
    ehdr.e_ident[1] = ELFMAG1;
    ehdr.e_ident[2] = ELFMAG2;
    ehdr.e_ident[3] = ELFMAG3;
    ehdr.e_ident[4] = ELFCLASSW;
    ehdr.e_ident[5] = ELFDATA2LSB;
    ehdr.e_ident[6] = EV_CURRENT;
#if defined(__FreeBSD__) || defined(__FreeBSD_kernel__)
    ehdr.e_ident[EI_OSABI] = ELFOSABI_FREEBSD;
#endif
    switch(file_type) {
    default:
    case TCC_OUTPUT_EXE:
        ehdr.e_type = ET_EXEC;
        ehdr.e_entry = get_elf_sym_addr(s1, "_start", 1);
        break;
    case TCC_OUTPUT_DLL:
        ehdr.e_type = ET_DYN;
        ehdr.e_entry = text_section->sh_addr; /* XXX：这样对吗？ */
        break;
    case TCC_OUTPUT_OBJ:
        ehdr.e_type = ET_REL;
        break;
    }
    ehdr.e_machine = EM_TCC_TARGET;
    ehdr.e_version = EV_CURRENT;
    ehdr.e_shoff = file_offset;
    ehdr.e_ehsize = sizeof(ElfW(Ehdr));
    ehdr.e_shentsize = sizeof(ElfW(Shdr));
    ehdr.e_shnum = shnum;
    ehdr.e_shstrndx = shnum - 1;

    fwrite(&ehdr, 1, sizeof(ElfW(Ehdr)), f);
    fwrite(phdr, 1, phnum * sizeof(ElfW(Phdr)), f);
    offset = sizeof(ElfW(Ehdr)) + phnum * sizeof(ElfW(Phdr));

    sort_syms(s1, symtab_section);
    for(i = 1; i < s1->nb_sections; i++) {
        s = s1->sections[sec_order[i]];
        if (s->sh_type != SHT_NOBITS) {
            while (offset < s->sh_offset) {
                fputc(0, f);
                offset++;
            }
            size = s->sh_size;
            if (size)
                fwrite(s->data, 1, size, f);
            offset += size;
        }
    }

    /* 输出段头 */
    while (offset < ehdr.e_shoff) {
        fputc(0, f);
        offset++;
    }

    for(i = 0; i < s1->nb_sections; i++) {
        sh = &shdr;
        memset(sh, 0, sizeof(ElfW(Shdr)));
        s = s1->sections[i];
        if (s) {
            sh->sh_name = s->sh_name;
            sh->sh_type = s->sh_type;
            sh->sh_flags = s->sh_flags;
            sh->sh_entsize = s->sh_entsize;
            sh->sh_info = s->sh_info;
            if (s->link)
                sh->sh_link = s->link->sh_num;
            sh->sh_addralign = s->sh_addralign;
            sh->sh_addr = s->sh_addr;
            sh->sh_offset = s->sh_offset;
            sh->sh_size = s->sh_size;
        }
        fwrite(sh, 1, sizeof(ElfW(Shdr)), f);
    }
}

/* 写出 elf、coff 或 "binary" 文件 */
static int tcc_write_elf_file(TCCState *s1, const char *filename, int phnum,
                              ElfW(Phdr) *phdr, int file_offset, int *sec_order)
{
    int fd, mode, file_type;
    FILE *f;

    file_type = s1->output_type;
    if (file_type == TCC_OUTPUT_OBJ)
        mode = 0666;
    else
        mode = 0777;
    unlink(filename);
    fd = open(filename, O_WRONLY | O_CREAT | O_TRUNC | O_BINARY, mode);
    if (fd < 0) {
        tcc_error_noabort("could not write '%s'", filename);
        return -1;
    }
    f = fdopen(fd, "wb");
    if (s1->verbose)
        printf("<- %s\n", filename);

    if (s1->output_format == TCC_OUTPUT_FORMAT_ELF)
        tcc_output_elf(s1, f, phnum, phdr, file_offset, sec_order);
    else
        tcc_output_binary(s1, f, sec_order);
    fclose(f);

    return 0;
}

/* 按分配到的 sh_addr 对段头排序，移除我们
   不打算输出的段。  */
static void tidy_section_headers(TCCState *s1, int *sec_order)
{
    int i, nnew, l, *backmap;
    Section **snew, *s;
    ElfW(Sym) *sym;

    snew = tcc_malloc(s1->nb_sections * sizeof(snew[0]));
    backmap = tcc_malloc(s1->nb_sections * sizeof(backmap[0]));
    for (i = 0, nnew = 0, l = s1->nb_sections; i < s1->nb_sections; i++) {
	s = s1->sections[sec_order[i]];
	if (!i || s->sh_name) {
	    backmap[sec_order[i]] = nnew;
	    snew[nnew] = s;
	    ++nnew;
	} else {
	    backmap[sec_order[i]] = 0;
	    snew[--l] = s;
	}
    }
    for (i = 0; i < nnew; i++) {
	s = snew[i];
	if (s) {
	    s->sh_num = i;
            if (s->sh_type == SHT_RELX)
		s->sh_info = backmap[s->sh_info];
	}
    }

    for_each_elem(symtab_section, 1, sym, ElfW(Sym))
	if (sym->st_shndx != SHN_UNDEF && sym->st_shndx < SHN_LORESERVE)
	    sym->st_shndx = backmap[sym->st_shndx];
    if( !s1->static_link ) {
        for_each_elem(s1->dynsym, 1, sym, ElfW(Sym))
	    if (sym->st_shndx != SHN_UNDEF && sym->st_shndx < SHN_LORESERVE)
	        sym->st_shndx = backmap[sym->st_shndx];
    }
    for (i = 0; i < s1->nb_sections; i++)
	sec_order[i] = i;
    tcc_free(s1->sections);
    s1->sections = snew;
    s1->nb_sections = nnew;
    tcc_free(backmap);
}

/* 输出 elf、coff 或 binary 文件 */
/* XXX：去掉不需要的段 */
static int elf_output_file(TCCState *s1, const char *filename)
{
    int i, ret, phnum, shnum, file_type, file_offset, *sec_order;
    struct dyn_inf dyninf = {0};
    ElfW(Phdr) *phdr;
    ElfW(Sym) *sym;
    Section *strsec, *interp, *dynamic, *dynstr;
    int textrel;

    file_type = s1->output_type;
    s1->nb_errors = 0;
    ret = -1;
    phdr = NULL;
    sec_order = NULL;
    interp = dynamic = dynstr = NULL; /* 避免警告 */
    textrel = 0;

    if (file_type != TCC_OUTPUT_OBJ) {
        /* 如果是链接，还要链接运行时库（libc、libgcc 等） */
        tcc_add_runtime(s1);
	resolve_common_syms(s1);

        if (!s1->static_link) {
            if (file_type == TCC_OUTPUT_EXE) {
                char *ptr;
                /* 允许覆盖动态加载器 */
                const char *elfint = getenv("LD_SO");
                if (elfint == NULL)
                    elfint = DEFAULT_ELFINTERP(s1);
                /* 只在可执行文件时添加解释器段 */
                interp = new_section(s1, ".interp", SHT_PROGBITS, SHF_ALLOC);
                interp->sh_addralign = 1;
                ptr = section_ptr_add(interp, 1 + strlen(elfint));
                strcpy(ptr, elfint);
            }

            /* 添加动态符号表 */
            s1->dynsym = new_symtab(s1, ".dynsym", SHT_DYNSYM, SHF_ALLOC,
                                    ".dynstr",
                                    ".hash", SHF_ALLOC);
            dynstr = s1->dynsym->link;

            /* 添加动态段 */
            dynamic = new_section(s1, ".dynamic", SHT_DYNAMIC,
                                  SHF_ALLOC | SHF_WRITE);
            dynamic->link = dynstr;
            dynamic->sh_entsize = sizeof(ElfW(Dyn));

            build_got(s1);

            if (file_type == TCC_OUTPUT_EXE) {
                bind_exe_dynsyms(s1);
                if (s1->nb_errors)
                    goto the_end;
                bind_libs_dynsyms(s1);
            } else {
                /* 共享库情形：直接导出所有全局符号 */
                export_global_syms(s1);
            }
        }
        build_got_entries(s1);
    }

    /* 我们为符号添加一个段 */
    strsec = new_section(s1, ".shstrtab", SHT_STRTAB, 0);
    put_elf_str(strsec, "");

    /* 为段名分配字符串 */
    textrel = alloc_sec_names(s1, file_type, strsec);

    if (dynamic) {
        /* 添加所需 dll 的列表 */
        for(i = 0; i < s1->nb_loaded_dlls; i++) {
            DLLReference *dllref = s1->loaded_dlls[i];
            if (dllref->level == 0)
                put_dt(dynamic, DT_NEEDED, put_elf_str(dynstr, dllref->name));
        }

        if (s1->rpath)
            put_dt(dynamic, s1->enable_new_dtags ? DT_RUNPATH : DT_RPATH,
                   put_elf_str(dynstr, s1->rpath));

        if (file_type == TCC_OUTPUT_DLL) {
            if (s1->soname)
                put_dt(dynamic, DT_SONAME, put_elf_str(dynstr, s1->soname));
            /* XXX：目前由于我们不处理 PIC 代码，
               必须重定位只读内存段 */
            if (textrel)
                put_dt(dynamic, DT_TEXTREL, 0);
        }

        if (s1->symbolic)
            put_dt(dynamic, DT_SYMBOLIC, 0);

        dyninf.dynamic = dynamic;
        dyninf.dynstr = dynstr;
        /* 记住偏移并在下面第二次调用时预留空间 */
        dyninf.data_offset = dynamic->data_offset;
        fill_dynamic(s1, &dyninf);
        dynamic->sh_size = dynamic->data_offset;
        dynstr->sh_size = dynstr->data_offset;
    }

    /* 计算程序头的数量 */
    if (file_type == TCC_OUTPUT_OBJ)
        phnum = 0;
    else if (file_type == TCC_OUTPUT_DLL)
        phnum = 3;
    else if (s1->static_link)
        phnum = 2;
    else
        phnum = 5;

    /* 分配程序内存段（segment）头 */
    phdr = tcc_mallocz(phnum * sizeof(ElfW(Phdr)));

    /* 计算段的数量 */
    shnum = s1->nb_sections;

    /* 该数组用于重排输出文件中的段 */
    sec_order = tcc_malloc(sizeof(int) * shnum);
    sec_order[0] = 0;

    /* 计算段到程序头的映射 */
    file_offset = layout_sections(s1, phdr, phnum, interp, strsec, &dyninf,
                                  sec_order);

    /* 填充剩余的程序头，并完成与动态链接相关的
       重定位。 */
    if (file_type != TCC_OUTPUT_OBJ) {
        fill_unloadable_phdr(phdr, phnum, interp, dynamic);
        if (dynamic) {
            dynamic->data_offset = dyninf.data_offset;
            fill_dynamic(s1, &dyninf);

            /* 把动态段地址放入 GOT 并重定位 PLT */
            write32le(s1->got->data, dynamic->sh_addr);
            if (file_type == TCC_OUTPUT_EXE
                || (RELOCATE_DLLPLT && file_type == TCC_OUTPUT_DLL))
                relocate_plt(s1);

            /* 既然最终地址已知，现在就重定位 .dynsym 中的符号 */
            for_each_elem(s1->dynsym, 1, sym, ElfW(Sym)) {
                if (sym->st_shndx != SHN_UNDEF && sym->st_shndx < SHN_LORESERVE) {
                    /* 做符号重定位 */
                    sym->st_value += s1->sections[sym->st_shndx]->sh_addr;
                }
            }
        }

        /* 如果构建可执行文件或 DLL，则重定位每个段，
           除了已经重定位过的 GOT */
        ret = final_sections_reloc(s1);
        if (ret)
            goto the_end;
	tidy_section_headers(s1, sec_order);

        /* 对 GOT 或 PLT 条目执行重定位 */
        if (file_type == TCC_OUTPUT_EXE && s1->static_link)
            fill_got(s1);
        else if (s1->got)
            fill_local_got_entries(s1);
    }

    /* 创建名为 'filename' 的 ELF 文件 */
    ret = tcc_write_elf_file(s1, filename, phnum, phdr, file_offset, sec_order);
    s1->nb_sections = shnum;
 the_end:
    tcc_free(sec_order);
    tcc_free(phdr);
    return ret;
}

LIBTCCAPI int tcc_output_file(TCCState *s, const char *filename)
{
    return elf_output_file(s, filename);
}

static void *load_data(int fd, unsigned long file_offset, unsigned long size)
{
    void *data;

    data = tcc_malloc(size);
    lseek(fd, file_offset, SEEK_SET);
    read(fd, data, size);
    return data;
}

/*
 * SectionMergeInfo —— 读入目标文件时，记录“源段合并到哪个已有段、落在什么偏移”
 *
 * tcc_load_object_file() 逐段处理 .o：同名段（如都叫 .text）要合并进同一个段，
 * 但各 .o 里符号/重定位记录的下标和偏移都以本文件为基准，因此需要用本结构
 * 记录映射关系，之后再遍历重定位表按映射改写符号下标与偏移：
 *   s           合并到的已有段（NULL 表示本次新建，见 new_section）；
 *   offset      源段数据在已有段中的起始偏移（用于把重定位偏移平移过来）；
 *   new_section 本结构对应的段是否是本次新建的；
 *   link_once   是否为 link-once 段（重复出现时只保留第一份）。
 */
typedef struct SectionMergeInfo {
    Section *s;            /* 对应的已有段 */
    unsigned long offset;  /* 新段在已有段中的偏移 */
    uint8_t new_section;       /* 如果添加了段 's' 则为真 */
    uint8_t link_once;         /* 如果是 link once 段则为真 */
} SectionMergeInfo;

ST_FUNC int tcc_object_type(int fd, ElfW(Ehdr) *h)
{
    int size = read(fd, h, sizeof *h);
    if (size == sizeof *h && 0 == memcmp(h, ELFMAG, 4)) {
        if (h->e_type == ET_REL)
            return AFF_BINTYPE_REL;
        if (h->e_type == ET_DYN)
            return AFF_BINTYPE_DYN;
    } else if (size >= 8) {
        if (0 == memcmp(h, ARMAG, 8))
            return AFF_BINTYPE_AR;
    }
    return 0;
}

/* 加载一个目标文件并与当前文件合并 */
/* XXX：正确处理 stab（调试）信息 */
ST_FUNC int tcc_load_object_file(TCCState *s1,
                                int fd, unsigned long file_offset)
{
    ElfW(Ehdr) ehdr;
    ElfW(Shdr) *shdr, *sh;
    int size, i, j, offset, offseti, nb_syms, sym_index, ret, seencompressed;
    unsigned char *strsec, *strtab;
    int *old_to_new_syms;
    char *sh_name, *name;
    SectionMergeInfo *sm_table, *sm;
    ElfW(Sym) *sym, *symtab;
    ElfW_Rel *rel;
    Section *s;

    int stab_index;
    int stabstr_index;

    stab_index = stabstr_index = 0;

    lseek(fd, file_offset, SEEK_SET);
    if (tcc_object_type(fd, &ehdr) != AFF_BINTYPE_REL)
        goto fail1;
    /* 测试 CPU 相关的东西 */
    if (ehdr.e_ident[5] != ELFDATA2LSB ||
        ehdr.e_machine != EM_TCC_TARGET) {
    fail1:
        tcc_error_noabort("invalid object file");
        return -1;
    }
    /* 读取各段 */
    shdr = load_data(fd, file_offset + ehdr.e_shoff,
                     sizeof(ElfW(Shdr)) * ehdr.e_shnum);
    sm_table = tcc_mallocz(sizeof(SectionMergeInfo) * ehdr.e_shnum);

    /* 加载段名 */
    sh = &shdr[ehdr.e_shstrndx];
    strsec = load_data(fd, file_offset + sh->sh_offset, sh->sh_size);

    /* 加载 symtab 和 strtab */
    old_to_new_syms = NULL;
    symtab = NULL;
    strtab = NULL;
    nb_syms = 0;
    seencompressed = 0;
    for(i = 1; i < ehdr.e_shnum; i++) {
        sh = &shdr[i];
        if (sh->sh_type == SHT_SYMTAB) {
            if (symtab) {
                tcc_error_noabort("object must contain only one symtab");
            fail:
                ret = -1;
                goto the_end;
            }
            nb_syms = sh->sh_size / sizeof(ElfW(Sym));
            symtab = load_data(fd, file_offset + sh->sh_offset, sh->sh_size);
            sm_table[i].s = symtab_section;

            /* 现在加载 strtab */
            sh = &shdr[sh->sh_link];
            strtab = load_data(fd, file_offset + sh->sh_offset, sh->sh_size);
        }
	if (sh->sh_flags & SHF_COMPRESSED)
	    seencompressed = 1;
    }

    /* 现在检查每个段，并尝试把它的内容与内存中的
       内容合并 */
    for(i = 1; i < ehdr.e_shnum; i++) {
        /* 不需要检查段名 strtab */
        if (i == ehdr.e_shstrndx)
            continue;
        sh = &shdr[i];
        sh_name = (char *) strsec + sh->sh_name;
        /* 忽略我们不处理的段类型 */
        if (sh->sh_type != SHT_PROGBITS &&
            sh->sh_type != SHT_RELX &&
#ifdef TCC_ARM_EABI
            sh->sh_type != SHT_ARM_EXIDX &&
#endif
            sh->sh_type != SHT_NOBITS &&
            sh->sh_type != SHT_PREINIT_ARRAY &&
            sh->sh_type != SHT_INIT_ARRAY &&
            sh->sh_type != SHT_FINI_ARRAY &&
            strcmp(sh_name, ".stabstr")
            )
            continue;
	if (seencompressed
	    && (!strncmp(sh_name, ".debug_", sizeof(".debug_")-1)
		|| (sh->sh_type == SHT_RELX
		    && !strncmp((char*)strsec + shdr[sh->sh_info].sh_name,
			        ".debug_", sizeof(".debug_")-1))))
	  continue;
        if (sh->sh_addralign < 1)
            sh->sh_addralign = 1;
        /* 查找对应的段（如果有） */
        for(j = 1; j < s1->nb_sections;j++) {
            s = s1->sections[j];
            if (!strcmp(s->name, sh_name)) {
                if (!strncmp(sh_name, ".gnu.linkonce",
                             sizeof(".gnu.linkonce") - 1)) {
                    /* 如果 'linkonce' 段已经存在，我们
                       就不再添加它。这有点棘手，因为
                       符号仍然可能在其中
                       定义。 */
                    sm_table[i].link_once = 1;
                    goto next;
                } else {
                    goto found;
                }
            }
        }
        /* 没找到：创建新段 */
        s = new_section(s1, sh_name, sh->sh_type, sh->sh_flags & ~SHF_GROUP);
        /* 尽可能多地从该段取信息。sh_link 和
           sh_info 稍后会更新 */
        s->sh_addralign = sh->sh_addralign;
        s->sh_entsize = sh->sh_entsize;
        sm_table[i].new_section = 1;
    found:
        if (sh->sh_type != s->sh_type) {
            tcc_error_noabort("invalid section type");
            goto fail;
        }

        /* 对齐段的起始位置 */
        offset = s->data_offset;

        if (0 == strcmp(sh_name, ".stab")) {
            stab_index = i;
            goto no_align;
        }
        if (0 == strcmp(sh_name, ".stabstr")) {
            stabstr_index = i;
            goto no_align;
        }

        size = sh->sh_addralign - 1;
        offset = (offset + size) & ~size;
        if (sh->sh_addralign > s->sh_addralign)
            s->sh_addralign = sh->sh_addralign;
        s->data_offset = offset;
    no_align:
        sm_table[i].offset = offset;
        sm_table[i].s = s;
        /* 拼接各段 */
        size = sh->sh_size;
        if (sh->sh_type != SHT_NOBITS) {
            unsigned char *ptr;
            lseek(fd, file_offset + sh->sh_offset, SEEK_SET);
            ptr = section_ptr_add(s, size);
            read(fd, ptr, size);
        } else {
            s->data_offset += size;
        }
    next: ;
    }

    /* gr 重定位 stab 字符串 */
    if (stab_index && stabstr_index) {
        Stab_Sym *a, *b;
        unsigned o;
        s = sm_table[stab_index].s;
        a = (Stab_Sym *)(s->data + sm_table[stab_index].offset);
        b = (Stab_Sym *)(s->data + s->data_offset);
        o = sm_table[stabstr_index].offset;
        while (a < b)
            a->n_strx += o, a++;
    }

    /* 第二遍短遍历，更新新段的 sh_link 和 sh_info
       字段 */
    for(i = 1; i < ehdr.e_shnum; i++) {
        s = sm_table[i].s;
        if (!s || !sm_table[i].new_section)
            continue;
        sh = &shdr[i];
        if (sh->sh_link > 0)
            s->link = sm_table[sh->sh_link].s;
        if (sh->sh_type == SHT_RELX) {
            s->sh_info = sm_table[sh->sh_info].s->sh_num;
            /* 更新反向链接 */
            s1->sections[s->sh_info]->reloc = s;
        }
    }
    sm = sm_table;

    /* 解析符号 */
    old_to_new_syms = tcc_mallocz(nb_syms * sizeof(int));

    sym = symtab + 1;
    for(i = 1; i < nb_syms; i++, sym++) {
        if (sym->st_shndx != SHN_UNDEF &&
            sym->st_shndx < SHN_LORESERVE) {
            sm = &sm_table[sym->st_shndx];
            if (sm->link_once) {
                /* 如果某个符号位于 link once 段中，我们使用
                   已经定义的符号。这对得到正确的重定位
                   非常重要 */
                if (ELFW(ST_BIND)(sym->st_info) != STB_LOCAL) {
                    name = (char *) strtab + sym->st_name;
                    sym_index = find_elf_sym(symtab_section, name);
                    if (sym_index)
                        old_to_new_syms[i] = sym_index;
                }
                continue;
            }
            /* 如果没有添加对应的段，就不需要添加符号 */
            if (!sm->s)
                continue;
            /* 转换段编号 */
            sym->st_shndx = sm->s->sh_num;
            /* 偏移值 */
            sym->st_value += sm->offset;
        }
        /* 添加符号 */
        name = (char *) strtab + sym->st_name;
        sym_index = set_elf_sym(symtab_section, sym->st_value, sym->st_size,
                                sym->st_info, sym->st_other,
                                sym->st_shndx, name);
        old_to_new_syms[i] = sym_index;
    }

    /* 第三遍，给重定位条目打补丁 */
    for(i = 1; i < ehdr.e_shnum; i++) {
        s = sm_table[i].s;
        if (!s)
            continue;
        sh = &shdr[i];
        offset = sm_table[i].offset;
        switch(s->sh_type) {
        case SHT_RELX:
            /* 取出重定位偏移信息 */
            offseti = sm_table[sh->sh_info].offset;
            for_each_elem(s, (offset / sizeof(*rel)), rel, ElfW_Rel) {
                int type;
                unsigned sym_index;
                /* 转换符号索引 */
                type = ELFW(R_TYPE)(rel->r_info);
                sym_index = ELFW(R_SYM)(rel->r_info);
                /* 注意：假定只有一个 symtab */
                if (sym_index >= nb_syms)
                    goto invalid_reloc;
                sym_index = old_to_new_syms[sym_index];
                /* 忽略 rel 段中的 link_once。 */
                if (!sym_index && !sm->link_once) {
                invalid_reloc:
                    tcc_error_noabort("Invalid relocation entry [%2d] '%s' @ %.8x",
                        i, strsec + sh->sh_name, rel->r_offset);
                    goto fail;
                }
                rel->r_info = ELFW(R_INFO)(sym_index, type);
                /* 给重定位偏移加上偏移量 */
                rel->r_offset += offseti;
            }
            break;
        default:
            break;
        }
    }

    ret = 0;
 the_end:
    tcc_free(symtab);
    tcc_free(strtab);
    tcc_free(old_to_new_syms);
    tcc_free(sm_table);
    tcc_free(strsec);
    tcc_free(shdr);
    return ret;
}

/*
 * ArchiveHeader —— ar 归档成员的 60 字节文件头（读归档时用）
 *
 * 与 tcctools.c 中写归档用的 ArHdr 是同一格式的两份定义（那里带演示性的初始化
 * 字符串，这里用于读入解析）。字段都是 ASCII 文本：ar_size 需要转换后才知道
 * 成员数据长度，ar_name 以 '/' 结尾表示名字结束（GNU 扩展中用 "/" 表示长名字
 * 符串表内的偏移、用 "//" 表示字符串表本身，见 tcc_load_archive()）。
 */
typedef struct ArchiveHeader {
    char ar_name[16];           /* 该成员的名字 */
    char ar_date[12];           /* 文件修改时间 */
    char ar_uid[6];             /* 属主 uid；以十进制打印 */
    char ar_gid[6];             /* 属主 gid；以十进制打印 */
    char ar_mode[8];            /* 文件模式，以八进制打印   */
    char ar_size[10];           /* 文件大小，以十进制打印 */
    char ar_fmag[2];            /* 应包含 ARFMAG */
} ArchiveHeader;

static int get_be32(const uint8_t *b)
{
    return b[3] | (b[2] << 8) | (b[1] << 16) | (b[0] << 24);
}

static long get_be64(const uint8_t *b)
{
  long long ret = get_be32(b);
  ret = (ret << 32) | (unsigned)get_be32(b+4);
  return (long)ret;
}

/* 只加载能解析未定义符号的那些目标文件 */
static int tcc_load_alacarte(TCCState *s1, int fd, int size, int entrysize)
{
    long i, bound, nsyms, sym_index, off, ret;
    uint8_t *data;
    const char *ar_names, *p;
    const uint8_t *ar_index;
    ElfW(Sym) *sym;

    data = tcc_malloc(size);
    if (read(fd, data, size) != size)
        goto fail;
    nsyms = entrysize == 4 ? get_be32(data) : get_be64(data);
    ar_index = data + entrysize;
    ar_names = (char *) ar_index + nsyms * entrysize;

    do {
        bound = 0;
        for(p = ar_names, i = 0; i < nsyms; i++, p += strlen(p)+1) {
            sym_index = find_elf_sym(symtab_section, p);
            if(sym_index) {
                sym = &((ElfW(Sym) *)symtab_section->data)[sym_index];
                if(sym->st_shndx == SHN_UNDEF) {
                    off = (entrysize == 4
			   ? get_be32(ar_index + i * 4)
			   : get_be64(ar_index + i * 8))
			  + sizeof(ArchiveHeader);
                    ++bound;
                    if(tcc_load_object_file(s1, fd, off) < 0) {
                    fail:
                        ret = -1;
                        goto the_end;
                    }
                }
            }
        }
    } while(bound);
    ret = 0;
 the_end:
    tcc_free(data);
    return ret;
}

/* 加载一个 '.a' 文件 */
ST_FUNC int tcc_load_archive(TCCState *s1, int fd)
{
    ArchiveHeader hdr;
    char ar_size[11];
    char ar_name[17];
    char magic[8];
    int size, len, i;
    unsigned long file_offset;

    /* 跳过已经检查过的魔数 */
    read(fd, magic, sizeof(magic));

    for(;;) {
        len = read(fd, &hdr, sizeof(hdr));
        if (len == 0)
            break;
        if (len != sizeof(hdr)) {
            tcc_error_noabort("invalid archive");
            return -1;
        }
        memcpy(ar_size, hdr.ar_size, sizeof(hdr.ar_size));
        ar_size[sizeof(hdr.ar_size)] = '\0';
        size = strtol(ar_size, NULL, 0);
        memcpy(ar_name, hdr.ar_name, sizeof(hdr.ar_name));
        for(i = sizeof(hdr.ar_name) - 1; i >= 0; i--) {
            if (ar_name[i] != ' ')
                break;
        }
        ar_name[i + 1] = '\0';
        file_offset = lseek(fd, 0, SEEK_CUR);
        /* 对齐到偶数 */
        size = (size + 1) & ~1;
        if (!strcmp(ar_name, "/")) {
            /* coff 符号表：我们处理它 */
            if(s1->alacarte_link)
                return tcc_load_alacarte(s1, fd, size, 4);
	} else if (!strcmp(ar_name, "/SYM64/")) {
            if(s1->alacarte_link)
                return tcc_load_alacarte(s1, fd, size, 8);
        } else {
            ElfW(Ehdr) ehdr;
            if (tcc_object_type(fd, &ehdr) == AFF_BINTYPE_REL) {
                if (tcc_load_object_file(s1, fd, file_offset) < 0)
                    return -1;
            }
        }
        lseek(fd, file_offset + size, SEEK_SET);
    }
    return 0;
}

/* 加载一个 DLL 以及所有被引用的 DLL。'level = 0' 表示该 DLL
   由用户引用（因此应作为 DT_NEEDED 加入
   生成的 ELF 文件） */
ST_FUNC int tcc_load_dll(TCCState *s1, int fd, const char *filename, int level)
{
    ElfW(Ehdr) ehdr;
    ElfW(Shdr) *shdr, *sh, *sh1;
    int i, j, nb_syms, nb_dts, sym_bind, ret;
    ElfW(Sym) *sym, *dynsym;
    ElfW(Dyn) *dt, *dynamic;
    unsigned char *dynstr;
    const char *name, *soname;
    DLLReference *dllref;

    read(fd, &ehdr, sizeof(ehdr));

    /* 测试 CPU 相关的东西 */
    if (ehdr.e_ident[5] != ELFDATA2LSB ||
        ehdr.e_machine != EM_TCC_TARGET) {
        tcc_error_noabort("bad architecture");
        return -1;
    }

    /* 读取各段 */
    shdr = load_data(fd, ehdr.e_shoff, sizeof(ElfW(Shdr)) * ehdr.e_shnum);

    /* 加载动态段和动态符号 */
    nb_syms = 0;
    nb_dts = 0;
    dynamic = NULL;
    dynsym = NULL; /* 避免警告 */
    dynstr = NULL; /* 避免警告 */
    for(i = 0, sh = shdr; i < ehdr.e_shnum; i++, sh++) {
        switch(sh->sh_type) {
        case SHT_DYNAMIC:
            nb_dts = sh->sh_size / sizeof(ElfW(Dyn));
            dynamic = load_data(fd, sh->sh_offset, sh->sh_size);
            break;
        case SHT_DYNSYM:
            nb_syms = sh->sh_size / sizeof(ElfW(Sym));
            dynsym = load_data(fd, sh->sh_offset, sh->sh_size);
            sh1 = &shdr[sh->sh_link];
            dynstr = load_data(fd, sh1->sh_offset, sh1->sh_size);
            break;
        default:
            break;
        }
    }

    /* 计算真实的库名 */
    soname = tcc_basename(filename);

    for(i = 0, dt = dynamic; i < nb_dts; i++, dt++) {
        if (dt->d_tag == DT_SONAME) {
            soname = (char *) dynstr + dt->d_un.d_val;
        }
    }

    /* 如果该 dll 已加载，就不再加载它 */
    for(i = 0; i < s1->nb_loaded_dlls; i++) {
        dllref = s1->loaded_dlls[i];
        if (!strcmp(soname, dllref->name)) {
            /* 但如需要则更新 level */
            if (level < dllref->level)
                dllref->level = level;
            ret = 0;
            goto the_end;
        }
    }

    /* 添加该 dll 及其 level */
    dllref = tcc_mallocz(sizeof(DLLReference) + strlen(soname));
    dllref->level = level;
    strcpy(dllref->name, soname);
    dynarray_add(&s1->loaded_dlls, &s1->nb_loaded_dlls, dllref);

    /* 把动态符号加入 dynsym_section */
    for(i = 1, sym = dynsym + 1; i < nb_syms; i++, sym++) {
        sym_bind = ELFW(ST_BIND)(sym->st_info);
        if (sym_bind == STB_LOCAL)
            continue;
        name = (char *) dynstr + sym->st_name;
        set_elf_sym(s1->dynsymtab_section, sym->st_value, sym->st_size,
                    sym->st_info, sym->st_other, sym->st_shndx, name);
    }

    /* 加载所有被引用的 DLL */
    for(i = 0, dt = dynamic; i < nb_dts; i++, dt++) {
        switch(dt->d_tag) {
        case DT_NEEDED:
            name = (char *) dynstr + dt->d_un.d_val;
            for(j = 0; j < s1->nb_loaded_dlls; j++) {
                dllref = s1->loaded_dlls[j];
                if (!strcmp(name, dllref->name))
                    goto already_loaded;
            }
            if (tcc_add_dll(s1, name, AFF_REFERENCED_DLL) < 0) {
                tcc_error_noabort("referenced dll '%s' not found", name);
                ret = -1;
                goto the_end;
            }
        already_loaded:
            break;
        }
    }
    ret = 0;
 the_end:
    tcc_free(dynstr);
    tcc_free(dynsym);
    tcc_free(dynamic);
    tcc_free(shdr);
    return ret;
}

#define LD_TOK_NAME 256
#define LD_TOK_EOF  (-1)

/* 返回下一个 ld 脚本词法单元 */
static int ld_next(TCCState *s1, char *name, int name_size)
{
    int c;
    char *q;

 redo:
    switch(ch) {
    case ' ':
    case '\t':
    case '\f':
    case '\v':
    case '\r':
    case '\n':
        inp();
        goto redo;
    case '/':
        minp();
        if (ch == '*') {
            file->buf_ptr = parse_comment(file->buf_ptr);
            ch = file->buf_ptr[0];
            goto redo;
        } else {
            q = name;
            *q++ = '/';
            goto parse_name;
        }
        break;
    case '\\':
        ch = handle_eob();
        if (ch != '\\')
            goto redo;
        /* 继续向下执行 */
    /* case 'a' ... 'z'： */
    case 'a':
       case 'b':
       case 'c':
       case 'd':
       case 'e':
       case 'f':
       case 'g':
       case 'h':
       case 'i':
       case 'j':
       case 'k':
       case 'l':
       case 'm':
       case 'n':
       case 'o':
       case 'p':
       case 'q':
       case 'r':
       case 's':
       case 't':
       case 'u':
       case 'v':
       case 'w':
       case 'x':
       case 'y':
       case 'z':
    /* case 'A' ... 'z'： */
    case 'A':
       case 'B':
       case 'C':
       case 'D':
       case 'E':
       case 'F':
       case 'G':
       case 'H':
       case 'I':
       case 'J':
       case 'K':
       case 'L':
       case 'M':
       case 'N':
       case 'O':
       case 'P':
       case 'Q':
       case 'R':
       case 'S':
       case 'T':
       case 'U':
       case 'V':
       case 'W':
       case 'X':
       case 'Y':
       case 'Z':
    case '_':
    case '.':
    case '$':
    case '~':
        q = name;
    parse_name:
        for(;;) {
            if (!((ch >= 'a' && ch <= 'z') ||
                  (ch >= 'A' && ch <= 'Z') ||
                  (ch >= '0' && ch <= '9') ||
                  strchr("/.-_+=$:\\,~", ch)))
                break;
            if ((q - name) < name_size - 1) {
                *q++ = ch;
            }
            minp();
        }
        *q = '\0';
        c = LD_TOK_NAME;
        break;
    case CH_EOF:
        c = LD_TOK_EOF;
        break;
    default:
        c = ch;
        inp();
        break;
    }
    return c;
}

static int ld_add_file(TCCState *s1, const char filename[])
{
    if (filename[0] == '/') {
        if (CONFIG_SYSROOT[0] == '\0'
            && tcc_add_file_internal(s1, filename, AFF_TYPE_BIN) == 0)
            return 0;
        filename = tcc_basename(filename);
    }
    return tcc_add_dll(s1, filename, 0);
}

static inline int new_undef_syms(void)
{
    int ret = 0;
    ret = new_undef_sym;
    new_undef_sym = 0;
    return ret;
}

static int ld_add_file_list(TCCState *s1, const char *cmd, int as_needed)
{
    char filename[1024], libname[1024];
    int t, group, nblibs = 0, ret = 0;
    char **libs = NULL;

    group = !strcmp(cmd, "GROUP");
    if (!as_needed)
        new_undef_syms();
    t = ld_next(s1, filename, sizeof(filename));
    if (t != '(')
        expect("(");
    t = ld_next(s1, filename, sizeof(filename));
    for(;;) {
        libname[0] = '\0';
        if (t == LD_TOK_EOF) {
            tcc_error_noabort("unexpected end of file");
            ret = -1;
            goto lib_parse_error;
        } else if (t == ')') {
            break;
        } else if (t == '-') {
            t = ld_next(s1, filename, sizeof(filename));
            if ((t != LD_TOK_NAME) || (filename[0] != 'l')) {
                tcc_error_noabort("library name expected");
                ret = -1;
                goto lib_parse_error;
            }
            pstrcpy(libname, sizeof libname, &filename[1]);
            if (s1->static_link) {
                snprintf(filename, sizeof filename, "lib%s.a", libname);
            } else {
                snprintf(filename, sizeof filename, "lib%s.so", libname);
            }
        } else if (t != LD_TOK_NAME) {
            tcc_error_noabort("filename expected");
            ret = -1;
            goto lib_parse_error;
        }
        if (!strcmp(filename, "AS_NEEDED")) {
            ret = ld_add_file_list(s1, cmd, 1);
            if (ret)
                goto lib_parse_error;
        } else {
            /* TODO：实现 AS_NEEDED 支持。暂时忽略它 */
            if (!as_needed) {
                ret = ld_add_file(s1, filename);
                if (ret)
                    goto lib_parse_error;
                if (group) {
                    /* 同时添加文件名 *和* 库名，以免将来再做转换 */
                    dynarray_add(&libs, &nblibs, tcc_strdup(filename));
                    if (libname[0] != '\0')
                        dynarray_add(&libs, &nblibs, tcc_strdup(libname));
                }
            }
        }
        t = ld_next(s1, filename, sizeof(filename));
        if (t == ',') {
            t = ld_next(s1, filename, sizeof(filename));
        }
    }
    if (group && !as_needed) {
        while (new_undef_syms()) {
            int i;

            for (i = 0; i < nblibs; i ++)
                ld_add_file(s1, libs[i]);
        }
    }
lib_parse_error:
    dynarray_reset(&libs, &nblibs);
    return ret;
}

/* 解释 GNU ldscripts 的一个子集，以处理哑元 libc.so
   文件 */
ST_FUNC int tcc_load_ldscript(TCCState *s1)
{
    char cmd[64];
    char filename[1024];
    int t, ret;

    ch = handle_eob();
    for(;;) {
        t = ld_next(s1, cmd, sizeof(cmd));
        if (t == LD_TOK_EOF)
            return 0;
        else if (t != LD_TOK_NAME)
            return -1;
        if (!strcmp(cmd, "INPUT") ||
            !strcmp(cmd, "GROUP")) {
            ret = ld_add_file_list(s1, cmd, 0);
            if (ret)
                return ret;
        } else if (!strcmp(cmd, "OUTPUT_FORMAT") ||
                   !strcmp(cmd, "TARGET")) {
            /* 忽略一些命令 */
            t = ld_next(s1, cmd, sizeof(cmd));
            if (t != '(')
                expect("(");
            for(;;) {
                t = ld_next(s1, filename, sizeof(filename));
                if (t == LD_TOK_EOF) {
                    tcc_error_noabort("unexpected end of file");
                    return -1;
                } else if (t == ')') {
                    break;
                }
            }
        } else {
            return -1;
        }
    }
    return 0;
}
