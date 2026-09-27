/* macho-out.c —— Mach-O 64 位目标文件写入器（本地系统支持）。
 *
 *Darwin（macOS arm64）上 `yh -o prog` 的输出路径：
 *   yh 编译出内存中的段/符号/重定位 → 写成 MH_OBJECT（Mach-O 目标文件）
 *   → 调用系统 cc 链接（Apple ld 负责绑定 libSystem、生成 stub 并做
 *   ad-hoc 签名）→ 得到本机可执行文件。
 *
 * 支持的重定位翻译（当前 yh 代码生成的封闭集合）：
 *   R_AARCH64_ABS64            → ARM64_RELOC_UNSIGNED (length=3, 8 字节)
 *   R_AARCH64_MOVW_UABS_G0/G1/G2/G3(_NC) → ARM64_RELOC_UNSIGNED
 *                                 (length=2，ld64 按指令 hw 域选择半字)
 *   R_AARCH64_CALL26           → ARM64_RELOC_BRANCH26 (length=2, pcrel)
 *
 * 符号名遵循 Darwin 惯例带前导下划线（由 TCCState.leading_underscore
 * 在 put_extern_sym2 时统一添加）。
 */

#include "tcc.h"

/* Mach-O 常量（docs: OS X ABI Mach-O File Format Reference） */
#define MH_MAGIC_64      0xfeedfacf
#define MH_OBJECT        1
#define CPU_TYPE_ARM64   0x0100000c
#define LC_SEGMENT_64    0x19
#define LC_SYMTAB        0x2
#define LC_BUILD_VERSION 0x32
#define PLATFORM_MACOS   1
#define S_ZEROFILL       1
#define N_SECT_MACHO     0x0e
#define N_UNDF_MACHO     0x00
#define N_EXT_MACHO      0x01

#define ARM64_RELOC_UNSIGNED 0
#define ARM64_RELOC_BRANCH26 2
#define ARM64_RELOC_PAGE21 3
#define ARM64_RELOC_PAGEOFF12 4
#define ARM64_RELOC_ADDEND 10

/* 64 位头部：28 + 4 = 32 字节（含 reserved） */
struct macho_header {
    uint32_t magic, cputype, cpusubtype, filetype;
    uint32_t ncmds, sizeofcmds, flags, reserved;
};

/* LC_SEGMENT_64：56 字节头 + nsects * 80 */
struct macho_segment {
    uint32_t cmd, cmdsize;
    char segname[16];
    uint64_t vmaddr, vmsize, fileoff, filesize;
    uint32_t maxprot, initprot, nsects, flags;
};

struct macho_section {
    char sectname[16], segname[16];
    uint64_t addr, size;
    uint32_t offset, align, reloff, nreloc, flags;
    uint32_t reserved1, reserved2, reserved3;
};

struct macho_symtab_cmd {
    uint32_t cmd, cmdsize, symoff, nsyms, stroff, strsize;
};

struct macho_nlist {
    uint32_t n_strx;
    uint8_t n_type, n_sect;
    uint16_t n_desc;
    uint64_t n_value;
};

/* 参与 Mach-O 输出的段描述（与 tcc 的 Section 一一映射） */
struct macho_sect {
    Section *sec;        /* tcc 段（text/data/bss） */
    const char *sect;    /* Mach-O 段名（__text/__data/__bss） */
    const char *seg;     /* Mach-O 节组（__TEXT/__DATA） */
    unsigned flags;      /* S_ZEROFILL 等 */
    uint64_t addr;       /* 段内累计地址（clang 约定） */
    uint64_t size;       /* 段大小（bss 为内存大小） */
    unsigned offset;     /* 文件内偏移（bss 为 0） */
    unsigned reloff;     /* 重定位表文件偏移 */
    unsigned nreloc;     /* 重定位条数 */
    int nsect;           /* 1 起算的节序号（n_sect 用） */
    int shndx;           /* tcc 的 ELF 节索引（映射 st_shndx） */
};

/* 收集参与输出的段；返回段数。 */
static int macho_collect_sections(TCCState *s1, struct macho_sect *out)
{
    int n = 0, i, j;
    struct { Section *sec; const char *sect; const char *seg; unsigned flags; } defs[] = {
        { text_section, "__text", "__TEXT", 0 },
        { data_section, "__data", "__DATA", 0 },
        { bss_section,  "__bss",  "__DATA", S_ZEROFILL },
    };
    for (i = 0; i < 3; i++) {
        Section *sec = defs[i].sec;
        if (!sec || sec->data_offset == 0)
            continue; /* 空段不进输出 */
        out[n].sec = sec;
        out[n].sect = defs[i].sect;
        out[n].seg = defs[i].seg;
        out[n].flags = defs[i].flags;
        out[n].nsect = n + 1;
        /* Section* → tcc 的 ELF 节索引（sections 是指针数组，须查下标） */
        for (j = 0; j < s1->nb_sections; j++)
            if (s1->sections[j] == sec)
                break;
        out[n].shndx = j;
        out[n].size = 0;
        out[n].offset = 0;
        out[n].reloff = 0;
        out[n].nreloc = 0;
        n++;
    }
    return n;
}

/* ELF 重定位类型 → Mach-O（type, length, pcrel）；不支持返回 -1。 */
static int macho_map_reloc(int elf_type, int *mtype, int *mlen, int *pcrel)
{
    switch (elf_type) {
    case R_AARCH64_ABS64:
        *mtype = ARM64_RELOC_UNSIGNED; *mlen = 3; *pcrel = 0; return 0;
    case R_AARCH64_MOVW_UABS_G0_NC:
    case R_AARCH64_MOVW_UABS_G1_NC:
    case R_AARCH64_MOVW_UABS_G2_NC:
    case R_AARCH64_MOVW_UABS_G3:
        *mtype = ARM64_RELOC_UNSIGNED; *mlen = 2; *pcrel = 0; return 0;
    case R_AARCH64_CALL26:
        *mtype = ARM64_RELOC_BRANCH26; *mlen = 2; *pcrel = 1; return 0;
    case R_AARCH64_ADR_PREL_PG_HI21:
        *mtype = ARM64_RELOC_PAGE21; *mlen = 2; *pcrel = 1; return 0;
    case R_AARCH64_ADD_ABS_LO12_NC:
        *mtype = ARM64_RELOC_PAGEOFF12; *mlen = 2; *pcrel = 0; return 0;
    default:
        return -1;
    }
}

static void macho_write(FILE *f, const void *buf, size_t len)
{
    if (len && fwrite(buf, 1, len, f) != len)
        tcc_error("写 Mach-O 输出失败");
}

/* ARM64_RELOC_ADDEND：addend 值存放在 24 位 r_symbolnum 字段，
   紧随其后的重定位使用该 addend。 */
static void macho_write_addend(FILE *f, int32_t r_address, long addend)
{
    uint32_t addr32 = (uint32_t)r_address;
    uint32_t packed = ((uint32_t)addend & 0xffffff) | (2u << 25)
                    | (ARM64_RELOC_ADDEND << 28);
    macho_write(f, &addr32, 4);
    macho_write(f, &packed, 4);
}

/* 写 MH_OBJECT：段、符号表、重定位。 */
ST_FUNC int tcc_output_macho(TCCState *s1, const char *filename)
{
    struct macho_sect ms[3];
    int nsects, i, j;
    int nsyms = 0, strsize = 1;
    unsigned cur_off, cmdsize, symoff, stroff;
    unsigned char *strtab;
    int *sym_map;              /* ELF 符号索引 → Mach-O 符号索引（-1 跳过） */
    Section *symsec = s1->symtab;
    int nb_syms_elf;
    FILE *f;
    struct macho_header mh;
    struct macho_segment seg;
    struct macho_symtab_cmd stcmd;
    int is_exe = s1->output_type == TCC_OUTPUT_EXE;
    char objfile[1024];
    uint64_t addr_end = 0; /* 段内地址空间结尾（含 bss） */

    nsects = macho_collect_sections(s1, ms);
    if (nsects == 0)
        tcc_error("没有可输出的代码（源文件缺少 main 或内容为空）");

    /* 统计各节重定位数 */
    for (i = 0; i < nsects; i++) {
        Section *sr = ms[i].sec->reloc;
        ms[i].nreloc = sr ? sr->data_offset / sizeof(ElfW_Rel) : 0;
    }

    /* ELF 符号表概览 */
    nb_syms_elf = symsec->data_offset / sizeof(ElfW(Sym));
    sym_map = tcc_mallocz(nb_syms_elf * sizeof(int));

    /* 文件布局（对齐 clang 产物约定）：
     *   header(32) + LC_BUILD_VERSION(24) + LC_SEGMENT_64 + LC_SYMTAB
     *   + 各节内容（bss 除外，无文件内容）+ 重定位表 + 符号表 + 字符串表
     * 节 addr 沿段内累计；vmsize = 累计结尾（含 bss）；filesize 只含节内容。
     */
    cmdsize = 72 + nsects * 80 + 24;
    cur_off = 32 + cmdsize + 24; /* + LC_BUILD_VERSION(24) */
    {
        uint64_t running_addr = 0;
        unsigned data_start = cur_off;
        for (i = 0; i < nsects; i++) {
            int sa = ms[i].sec->sh_addralign > 0 ? ms[i].sec->sh_addralign : 1;
            ms[i].size = ms[i].sec->data_offset;
            running_addr = (running_addr + sa - 1) & ~(uint64_t)(sa - 1);
            ms[i].addr = running_addr; /* 对齐后的段内起始 */
            running_addr += ms[i].size;
            if (ms[i].flags & S_ZEROFILL) {
                ms[i].offset = data_start; /* ZEROFILL 无文件内容 */
            } else {
                cur_off = (cur_off + 15) & ~15u;
                ms[i].offset = cur_off;
                cur_off += ms[i].sec->data_offset;
            }
        }
        addr_end = running_addr;
    }
    /* 重定位表 */
    for (i = 0; i < nsects; i++) {
        if (ms[i].nreloc) {
            cur_off = (cur_off + 3) & ~3u;
            ms[i].reloff = cur_off;
            cur_off += ms[i].nreloc * 8;
        }
    }
    symoff = cur_off;

    /* 第一遍符号统计：跳过 0 号空符号、节符号与文件符号 */
    {
        ElfW(Sym) *sym;
        for (i = 1; i < nb_syms_elf; i++) {
            sym = &((ElfW(Sym) *)symsec->data)[i];
            if (ELFW(ST_TYPE)(sym->st_info) == STT_SECTION
                || ELFW(ST_TYPE)(sym->st_info) == STT_FILE) {
                sym_map[i] = -1;
                continue;
            }
            sym_map[i] = nsyms++;
            {
                const char *nm = (char *)symsec->link->data + sym->st_name;
                strsize += strlen(nm) + 1;
            }
        }
    }
    stroff = symoff + nsyms * 16;

    f = fopen(filename, "wb");
    if (!f)
        tcc_error("无法写入 '%s'", filename);

    /* header */
    memset(&mh, 0, sizeof mh);
    mh.magic = MH_MAGIC_64;
    mh.cputype = CPU_TYPE_ARM64;
    mh.cpusubtype = 0;
    mh.filetype = MH_OBJECT;
    mh.ncmds = 3;
    mh.sizeofcmds = cmdsize + 24;
    macho_write(f, &mh, sizeof mh);

    /* LC_BUILD_VERSION：声明目标平台（macOS 11.0） */
    {
        uint32_t bv[6] = { LC_BUILD_VERSION, 24, PLATFORM_MACOS, 11 * 10000,
                           11 * 10000, 0 };
        macho_write(f, bv, sizeof bv);
    }

    /* LC_SEGMENT_64 + sections */
    memset(&seg, 0, sizeof seg);
    seg.cmd = LC_SEGMENT_64;
    seg.cmdsize = 72 + nsects * 80;
    pstrcpy(seg.segname, sizeof seg.segname, "");
    seg.vmaddr = 0;
    seg.vmsize = addr_end; /* 累计结尾（含 bss） */
    seg.fileoff = nsects ? ms[0].offset : 0;
    seg.filesize = 0;
    for (i = 0; i < nsects; i++)
        if (!(ms[i].flags & S_ZEROFILL))
            seg.filesize += ms[i].size; /* 只含节内容（clang 约定） */
    seg.maxprot = 7;
    seg.initprot = 7;
    seg.nsects = nsects;
    macho_write(f, &seg, 72);
    for (i = 0; i < nsects; i++) {
        struct macho_section msct;
        memset(&msct, 0, sizeof msct);
        pstrcpy(msct.sectname, sizeof msct.sectname, ms[i].sect);
        pstrcpy(msct.segname, sizeof msct.segname, ms[i].seg);
        msct.addr = ms[i].addr; /* 段内对齐后的起始地址 */
        msct.size = ms[i].size;
        msct.offset = ms[i].offset;
        msct.align = 4;   /* 2^4 = 16 字节对齐 */
        msct.reloff = ms[i].reloff;
        msct.nreloc = ms[i].nreloc;
        msct.flags = ms[i].flags;
        if (i == 0 && !strcmp(ms[i].sect, "__text"))
            msct.flags |= 0x80000400; /* PURE|SOME_INSTRUCTIONS */
        macho_write(f, &msct, 80);
    }

    /* LC_SYMTAB（占位写，回填 stroff/strsize 已知） */
    memset(&stcmd, 0, sizeof stcmd);
    stcmd.cmd = LC_SYMTAB;
    stcmd.cmdsize = 24;
    stcmd.symoff = symoff;
    stcmd.nsyms = nsyms;
    stcmd.stroff = stroff;
    stcmd.strsize = strsize;
    macho_write(f, &stcmd, sizeof stcmd);

    /* 段数据（按布局偏移精确定位，节间对齐间隙留空） */
    for (i = 0; i < nsects; i++) {
        if (!(ms[i].flags & S_ZEROFILL) && ms[i].sec->data_offset) {
            fseek(f, ms[i].offset, SEEK_SET);
            macho_write(f, ms[i].sec->data, ms[i].sec->data_offset);
        }
    }
    /* 重定位表 */
    for (i = 0; i < nsects; i++) {
        Section *sr = ms[i].sec->reloc;
        if (!ms[i].nreloc)
            continue;
        fseek(f, ms[i].reloff, SEEK_SET);
        for (j = 0; j < (int)ms[i].nreloc; j++) {
            ElfW_Rel *rel = &((ElfW_Rel *)sr->data)[j];
            int sym_index = ELFW(R_SYM)(rel->r_info);
            int type = ELFW(R_TYPE)(rel->r_info);
            int mtype, mlen, pcrel, msym;
            uint32_t packed;
            int32_t addr32;
            uint32_t u32;
            if (macho_map_reloc(type, &mtype, &mlen, &pcrel) < 0)
                tcc_error("Mach-O：不支持的重定位类型 %d", type);
            if (sym_index <= 0 || sym_index >= nb_syms_elf ||
                sym_map[sym_index] < 0)
                tcc_error("Mach-O：重定位引用了无法映射的符号");
            msym = sym_map[sym_index];
            addr32 = (int32_t)rel->r_offset;
            u32 = (uint32_t)addr32;
            /* Mach-O 无 addend 字段：对 UNSIGNED/PAGE21/PAGEOFF12 用
               ADDEND 重定位携带（值为 0 时可省略） */
            if (mtype == ARM64_RELOC_UNSIGNED || mtype == ARM64_RELOC_PAGE21
                || mtype == ARM64_RELOC_PAGEOFF12) {
                if (rel->r_addend != 0)
                    macho_write_addend(f, addr32, (long)rel->r_addend);
            }
            packed = (msym & 0xffffff) | (pcrel << 24) | (mlen << 25)
                   | (1u << 27) /* r_extern：符号表索引 */ | (mtype << 28);
            macho_write(f, &u32, 4);
            macho_write(f, &packed, 4);
        }
    }

    /* 符号表 + 字符串表 */
    fseek(f, symoff, SEEK_SET);
    strtab = tcc_mallocz(strsize + 16);
    strtab[0] = 0;
    {
        unsigned strofs = 1;
        ElfW(Sym) *sym;
        for (i = 1; i < nb_syms_elf; i++) {
            struct macho_nlist nl;
            const char *nm;
            if (sym_map[i] < 0)
                continue;
            sym = &((ElfW(Sym) *)symsec->data)[i];
            nm = (char *)symsec->link->data + sym->st_name;
            memset(&nl, 0, sizeof nl);
            nl.n_strx = strofs;
            strcpy((char *)strtab + strofs, nm);
            strofs += strlen(nm) + 1;
            if (sym->st_shndx == SHN_UNDEF) {
                nl.n_type = N_UNDF_MACHO | N_EXT_MACHO; /* 外部导入 */
                nl.n_sect = 0;
                nl.n_value = 0;
            } else {
                int mi;
                nl.n_type = N_SECT_MACHO;
                if (ELFW(ST_BIND)(sym->st_info) == STB_GLOBAL)
                    nl.n_type |= N_EXT_MACHO;
                /* ELF 节索引 → Mach-O 节序号 */
                for (mi = 0; mi < nsects; mi++)
                    if (ms[mi].shndx == (int)sym->st_shndx)
                        break;
                nl.n_sect = mi < nsects ? ms[mi].nsect : 1;
                /* MH_OBJECT 约定：n_value 是段内累计地址空间中的值 */
                nl.n_value = (mi < nsects ? ms[mi].addr : 0) + sym->st_value;
            }
            macho_write(f, &nl, 16);
        }
        fseek(f, stroff, SEEK_SET);
        macho_write(f, strtab, strsize);
        tcc_free(strtab);
    }
    tcc_free(sym_map);
    fclose(f);

    if (!is_exe)
        return 0;

    /* EXE：调用系统 cc 链接 libSystem 并签名（Apple ld 完成动态绑定） */
    {
        char cmd[2100];
        int rc;
        pstrcpy(objfile, sizeof objfile, filename);
        pstrcat(objfile, sizeof objfile, ".yh-macho.o");
        if (rename(filename, objfile) != 0)
            tcc_error("无法暂存目标文件 '%s'", objfile);
        snprintf(cmd, sizeof cmd, "cc \"%s\" -o \"%s\"", objfile, filename);
        rc = system(cmd);
        unlink(objfile);
        if (rc != 0)
            tcc_error("系统链接器调用失败（%s）：需要 Xcode Command Line "
                      "Tools 提供 cc", cmd);
    }
    return 0;
}
