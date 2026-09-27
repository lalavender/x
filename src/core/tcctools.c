/* -------------------------------------------------------------- */
/*
 *  TCC - Tiny C Compiler（微型 C 编译器）
 *
 *  tcctools.c - 附带的工具以及 -m32/64 支持
 *
 */

/* -------------------------------------------------------------- */
/*
 * 本程序用于在缺少 ar 的情况下制作 libtcc1.a
 * tiny_libmaker - 极简 ELF 静态库生成器
 * 用法：tiny_libmaker [lib] files...
 * Copyright (c) 2007 Timppa
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
 * 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.
 */

#include "tcc.h"

// #define ARMAG  "!<arch>\n"  /* glibc 中的定义 */
#define ARFMAG "`\n"

/*
 * ArHdr —— ar 归档成员的固定 60 字节文件头
 *
 * 字段全是 ASCII 文本而非二进制（这正是 ar 格式的特点），因此 ar_size 等
 * 需要 strtoul 转换、写回时需要 sprintf 格式化。ar_name 以 '/' 结尾表示名字
 * 结束（GNU 扩展用 "/" 表示后续长名字符串表中的偏移，用 "//"
 * 表示该字符串表本身）； ar_fmag 必须是 ARFMAG（"`\n"）用于校验头部完整性。
 * 相关处理见 tcc_tool_ar()（创建/列出/解包归档）与 tcc_load_archive()。
 */
typedef struct {
  char ar_name[16]; /* 成员名 */
  char ar_date[12]; /* 时间戳（十进制文本） */
  char ar_uid[6];   /* 属主 uid */
  char ar_gid[6];   /* 属主 gid */
  char ar_mode[8];  /* 文件权限（八进制文本） */
  char ar_size[10]; /* 成员数据字节数（十进制文本） */
  char ar_fmag[2];  /* 头部结束标记，固定为 ARFMAG */
} ArHdr;

static unsigned long le2belong(unsigned long ul) {
  return ((ul & 0xFF0000) >> 8) + ((ul & 0xFF000000) >> 24) +
         ((ul & 0xFF) << 24) + ((ul & 0xFF00) << 8);
}

/* 若 s 含有 list 中的任意字符则返回 1，否则返回 0 */
static int contains_any(const char* s, const char* list) {
  const char* l;
  for (; *s; s++) {
    for (l = list; *l; l++) {
      if (*s == *l) return 1;
    }
  }
  return 0;
}

static int ar_usage(int ret) {
  fprintf(stderr, "usage: tcc -ar [rcsv] lib file...\n");
  fprintf(stderr, "create library ([abdioptxN] not supported).\n");
  return ret;
}

ST_FUNC int tcc_tool_ar(TCCState* s1, int argc, char** argv) {
  static ArHdr arhdr = {"/               ", "            ", "0     ", "0     ",
                        "0       ",         "          ",   ARFMAG};

  static ArHdr arhdro = {"                ", "            ", "0     ", "0     ",
                         "0       ",         "          ",   ARFMAG};

  FILE *fi, *fh = NULL, *fo = NULL;
  ElfW(Ehdr) * ehdr;
  ElfW(Shdr) * shdr;
  ElfW(Sym) * sym;
  int i, fsize, i_lib, i_obj;
  char *buf, *shstr, *symtab = NULL, *strtab = NULL;
  int symtabsize = 0;  //, strtabsize = 0;  /* 未使用 */
  char* anames = NULL;
  int* afpos = NULL;
  int istrlen, strpos = 0, fpos = 0, funccnt = 0, funcmax, hofs;
  char tfile[260], stmp[20];
  char *file, *name;
  int ret = 2;
  const char* ops_conflict = "habdioptxN";  // 不支持；若被忽略会破坏结果。
  int verbose = 0;

  i_lib = 0;
  i_obj = 0;  // 保存库文件与第一个目标文件的下标
  for (i = 1; i < argc; i++) {
    const char* a = argv[i];
    if (*a == '-' && strstr(a, "."))
      ret = 1;  // -x.y 始终非法（与 gnu ar 一致）
    if ((*a == '-') || (i == 1 && !strstr(a, "."))) {  // 选项参数
      if (contains_any(a, ops_conflict)) ret = 1;
      if (strstr(a, "v")) verbose = 1;
    } else {       // 库或目标文件：不提前中止，先把所有参数校验完。
      if (!i_lib)  // 第一个文件是库
        i_lib = i;
      else if (!i_obj)  // 第二个文件是第一个目标文件
        i_obj = i;
    }
  }

  if (!i_obj)  // i_obj 存在意味着 i_lib 也存在。二者都必需。
    ret = 1;

  if (ret == 1) return ar_usage(ret);

  if ((fh = fopen(argv[i_lib], "wb")) == NULL) {
    fprintf(stderr, "tcc: ar: can't open file %s \n", argv[i_lib]);
    goto the_end;
  }

  sprintf(tfile, "%s.tmp", argv[i_lib]);
  if ((fo = fopen(tfile, "wb+")) == NULL) {
    fprintf(stderr, "tcc: ar: can't create temporary file %s\n", tfile);
    goto the_end;
  }

  funcmax = 250;
  afpos = tcc_realloc(NULL, funcmax * sizeof *afpos);  // 250 个函数
  memcpy(&arhdro.ar_mode, "100666", 6);

  // i_obj = 第一个输入目标文件
  while (i_obj < argc) {
    if (*argv[i_obj] == '-') {  // 此时所有选项都以 '-' 开头
      i_obj++;
      continue;
    }
    if ((fi = fopen(argv[i_obj], "rb")) == NULL) {
      fprintf(stderr, "tcc: ar: can't open file %s \n", argv[i_obj]);
      goto the_end;
    }
    if (verbose) printf("a - %s\n", argv[i_obj]);

    fseek(fi, 0, SEEK_END);
    fsize = ftell(fi);
    fseek(fi, 0, SEEK_SET);
    buf = tcc_malloc(fsize + 1);
    fread(buf, fsize, 1, fi);
    fclose(fi);

    // elf 文件头
    ehdr = (ElfW(Ehdr)*)buf;
    if (ehdr->e_ident[4] != ELFCLASSW) {
      fprintf(stderr, "tcc: ar: Unsupported Elf Class: %s\n", argv[i_obj]);
      goto the_end;
    }

    shdr = (ElfW(Shdr)*)(buf + ehdr->e_shoff +
                         ehdr->e_shstrndx * ehdr->e_shentsize);
    shstr = (char*)(buf + shdr->sh_offset);
    for (i = 0; i < ehdr->e_shnum; i++) {
      shdr = (ElfW(Shdr)*)(buf + ehdr->e_shoff + i * ehdr->e_shentsize);
      if (!shdr->sh_offset) continue;
      if (shdr->sh_type == SHT_SYMTAB) {
        symtab = (char*)(buf + shdr->sh_offset);
        symtabsize = shdr->sh_size;
      }
      if (shdr->sh_type == SHT_STRTAB) {
        if (!strcmp(shstr + shdr->sh_name, ".strtab")) {
          strtab = (char*)(buf + shdr->sh_offset);
          // strtabsize = shdr->sh_size;  /* 未使用 */
        }
      }
    }

    if (symtab && symtabsize) {
      int nsym = symtabsize / sizeof(ElfW(Sym));
      // printf("符号表: 信息 大小 节索引 名称\n");  /* 调试输出 */
      for (i = 1; i < nsym; i++) {
        sym = (ElfW(Sym)*)(symtab + i * sizeof(ElfW(Sym)));
        if (sym->st_shndx && (sym->st_info == 0x10 || sym->st_info == 0x11 ||
                              sym->st_info == 0x12)) {
          // printf("符号表: %2Xh %4Xh %2Xh %s\n", sym->st_info, sym->st_size,
          // sym->st_shndx, strtab + sym->st_name);
          istrlen = strlen(strtab + sym->st_name) + 1;
          anames = tcc_realloc(anames, strpos + istrlen);
          strcpy(anames + strpos, strtab + sym->st_name);
          strpos += istrlen;
          if (++funccnt >= funcmax) {
            funcmax += 250;
            afpos = tcc_realloc(afpos,
                                funcmax * sizeof *afpos);  // 再增加 250 个函数
          }
          afpos[funccnt] = fpos;
        }
      }
    }

    file = argv[i_obj];
    for (name = strchr(file, 0);
         name > file && name[-1] != '/' && name[-1] != '\\'; --name);
    istrlen = strlen(name);
    if (istrlen >= sizeof(arhdro.ar_name)) istrlen = sizeof(arhdro.ar_name) - 1;
    memset(arhdro.ar_name, ' ', sizeof(arhdro.ar_name));
    memcpy(arhdro.ar_name, name, istrlen);
    arhdro.ar_name[istrlen] = '/';
    sprintf(stmp, "%-10d", fsize);
    memcpy(&arhdro.ar_size, stmp, 10);
    fwrite(&arhdro, sizeof(arhdro), 1, fo);
    fwrite(buf, fsize, 1, fo);
    tcc_free(buf);
    i_obj++;
    fpos += (fsize + sizeof(arhdro));
  }
  hofs = 8 + sizeof(arhdr) + strpos + (funccnt + 1) * sizeof(int);
  fpos = 0;
  if ((hofs & 1))  // 对齐
    hofs++, fpos = 1;
  // 写入归档头
  fwrite("!<arch>\n", 8, 1, fh);
  sprintf(stmp, "%-10d", (int)(strpos + (funccnt + 1) * sizeof(int)));
  memcpy(&arhdr.ar_size, stmp, 10);
  fwrite(&arhdr, sizeof(arhdr), 1, fh);
  afpos[0] = le2belong(funccnt);
  for (i = 1; i <= funccnt; i++) afpos[i] = le2belong(afpos[i] + hofs);
  fwrite(afpos, (funccnt + 1) * sizeof(int), 1, fh);
  fwrite(anames, strpos, 1, fh);
  if (fpos) fwrite("", 1, 1, fh);
  // 写入各目标文件
  fseek(fo, 0, SEEK_END);
  fsize = ftell(fo);
  fseek(fo, 0, SEEK_SET);
  buf = tcc_malloc(fsize + 1);
  fread(buf, fsize, 1, fo);
  fwrite(buf, fsize, 1, fh);
  tcc_free(buf);
  ret = 0;
the_end:
  if (anames) tcc_free(anames);
  if (afpos) tcc_free(afpos);
  if (fh) fclose(fh);
  if (fo) fclose(fo), remove(tfile);
  return ret;
}

/* -------------------------------------------------------------- */
/*
 *  TCC - Tiny C Compiler（微型 C 编译器）
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

ST_FUNC void tcc_tool_cross(TCCState* s, char** argv, int option) {
  tcc_error("-m%d not implemented.", option);
}

/* -------------------------------------------------------------- */
/* 启用命令行通配符展开（tcc -o x.exe *.c） */

#ifdef _WIN32
int _CRT_glob = 1;
#ifndef _CRT_glob
int _dowildcard = 1;
#endif
#endif

/* -------------------------------------------------------------- */
/* 生成 xxx.d 依赖文件 */

ST_FUNC void gen_makedeps(TCCState* s, const char* target,
                          const char* filename) {
  FILE* depout;
  char buf[1024];
  int i;

  if (!filename) {
    /* 自动计算文件名：dir/file.o -> dir/file.d */
    snprintf(buf, sizeof buf, "%.*s.d",
             (int)(tcc_fileextension(target) - target), target);
    filename = buf;
  }

  if (s->verbose) printf("<- %s\n", filename);

  /* XXX 是否应返回错误码而不是调用 error()？ */
  depout = fopen(filename, "w");
  if (!depout) tcc_error("could not open '%s'", filename);

  fprintf(depout, "%s: \\\n", target);
  for (i = 0; i < s->nb_target_deps; ++i)
    fprintf(depout, " %s \\\n", s->target_deps[i]);
  fprintf(depout, "\n");
  fclose(depout);
}

/* -------------------------------------------------------------- */
