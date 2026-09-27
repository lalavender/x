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

#include "tcc.h"
#if ONE_SOURCE
#include "libtcc.c"
#endif
#include "tcctools.c"

static const char help[] =
    "yh（玉衡）编译器 " TCC_VERSION " - AArch64 Linux\n"
    "Usage: yh [options...] [-o outfile] infile.yh...\n"
    "       yh [options...] -run infile.yh [arguments...]\n"
    "       yh --syntax-check infile.yh      只做词法/语法检查\n"
    "General options:\n"
    "  -c          compile only - generate an object file\n"
    "  -o outfile  set output filename\n"
    "  -run        run compiled source\n"
    "  --syntax-check  only check lexer/parser errors, no codegen\n"
    "  -w          disable all warnings\n"
    "  -v -vv      show version, show search paths or loaded files\n"
    "  -h -hh      show this, show more help\n"
    "  -bench      show compilation statistics\n"
    "  -           use stdin pipe as infile\n"
    "  @listfile   read arguments from listfile\n"
    "Linker options:\n"
    "  -Ldir       add library path 'dir'\n"
    "  -llib       link with dynamic or static library 'lib'\n"
    "  -r          generate (relocatable) object file\n"
    "  -shared     generate a shared library/dll\n"
    "  -static     link to static libraries\n"
    "Misc. options:\n"
    "  -nostdlib   do not link with standard crt and libraries\n"
    "  -Bdir       set yh's private lib dir (libtcc1.a)\n"
    "  -sysrootdir link-time Linux sysroot (crt/libc; or env YH_SYSROOT)\n"
    "Tools:\n"
    "  create library  : yh -ar [rcsv] lib.a files\n"
    ;

static const char help2[] =
    "yh（玉衡）编译器 " TCC_VERSION " - More Options\n"
    "Special options:\n"
    "  -static                     link to static libraries (not recommended)\n"
    "  -dumpversion                print version\n"
    "  -print-search-dirs          print search paths\n"
    "Ignored options:\n"
    "  --param  -pedantic  -pipe  -s  -std  -traditional\n"
    "-Wl,... linker options:\n"
    "  -nostdlib                   do not link with standard crt/libs\n"
    "  -rpath=                     set dynamic library search path\n"
    "  -soname=                    set DT_SONAME elf tag\n"
    "  -oformat=[elf64-* binary]   set executable output format\n"
    "See also the manual for more details.\n";

static const char version[] = "yh version " TCC_VERSION " ("
                              "AArch64"
#if defined(__FreeBSD__) || defined(__FreeBSD_kernel__)
                              " FreeBSD"
#else
                              " Linux"
#endif
                              ")\n";

static void print_dirs(const char *msg, char **paths, int nb_paths) {
  int i;
  printf("%s:\n%s", msg, nb_paths ? "" : "  -\n");
  for (i = 0; i < nb_paths; i++)
    printf("  %s\n", paths[i]);
}

static void print_search_dirs(TCCState *s) {
  printf("install: %s\n", s->tcc_lib_path);
  /* print_dirs("programs", NULL, 0); */  /* 打印程序目录 */
  print_dirs("include", s->sysinclude_paths, s->nb_sysinclude_paths);
  print_dirs("libraries", s->library_paths, s->nb_library_paths);
  printf("libtcc1:\n  %s/" TCC_LIBTCC1 "\n", s->tcc_lib_path);
  print_dirs("crt", s->crt_paths, s->nb_crt_paths);
  printf("elfinterp:\n  %s\n", DEFAULT_ELFINTERP(s));
}

static void set_environment(TCCState *s) {
  char *path;

  path = getenv("C_INCLUDE_PATH");
  if (path != NULL) {
    tcc_add_sysinclude_path(s, path);
  }
  path = getenv("CPATH");
  if (path != NULL) {
    tcc_add_include_path(s, path);
  }
  path = getenv("LIBRARY_PATH");
  if (path != NULL) {
    tcc_add_library_path(s, path);
  }
}

static char *default_outputfile(TCCState *s, const char *first_file) {
  char buf[1024];
  char *ext;
  const char *name = "a";

  if (first_file && strcmp(first_file, "-"))
    name = tcc_basename(first_file);
  snprintf(buf, sizeof(buf), "%s", name);
  ext = tcc_fileextension(buf);
  if (s->output_type == TCC_OUTPUT_OBJ && !s->option_r && *ext)
    strcpy(ext, ".o");
  else
    strcpy(buf, "a.out");
  return tcc_strdup(buf);
}

/* yh 只接受 .yh 用户源文件；对象/库等二进制输入不受限。
   返回 0 通过，否则已打印诊断并返回 -1。 */
static int check_input_files(TCCState *s) {
  int i;
  for (i = 0; i < s->nb_files; i++) {
    struct filespec *f = s->files[i];
    const char *ext;
    if (f->type == AFF_TYPE_LIB || (f->type & AFF_TYPE_BIN))
      continue; /* -l 库与显式二进制输入 */
    ext = tcc_fileextension(f->name);
    if (!strcmp(ext, ".yh"))
      continue;
    if (!strcmp(ext, ".o") || !strcmp(ext, ".a") || !strcmp(ext, ".so"))
      continue; /* 二进制输入由内容探测分派 */
    tcc_error_noabort("'%s': yh 的用户源文件必须是 .yh 后缀", f->name);
    return -1;
  }
  return 0;
}

static unsigned getclock_ms(void) {
#ifdef _WIN32
  return GetTickCount();
#else
  struct timeval tv;
  gettimeofday(&tv, NULL);
  return tv.tv_sec * 1000 + (tv.tv_usec + 500) / 1000;
#endif
}

int main(int argc0, char **argv0) {
  TCCState *s;
  int ret, opt, n = 0, t = 0;
  unsigned start_time = 0;
  const char *first_file;
  int argc;
  char **argv;
  FILE *ppfp = stdout;

redo:
  argc = argc0, argv = argv0;
  s = tcc_new();
  opt = tcc_parse_args(s, &argc, &argv, 1);

  if ((n | t) == 0) {
    if (opt == OPT_HELP)
      return printf(help), 1;
    if (opt == OPT_HELP2)
      return printf(help2), 1;
    if (opt == OPT_M32 || opt == OPT_M64)
      tcc_tool_cross(s, argv, opt); /* 永不返回 */
    if (s->verbose)
      printf(version);
    if (opt == OPT_AR)
      return tcc_tool_ar(s, argc, argv);
    if (opt == OPT_V)
      return 0;
    if (opt == OPT_PRINT_DIRS) {
      /* 初始化搜索目录 */
      set_environment(s);
      tcc_set_output_type(s, TCC_OUTPUT_MEMORY);
      print_search_dirs(s);
      return 0;
    }

    n = s->nb_files;
    if (n == 0)
      tcc_error("no input files\n");
    if (check_input_files(s))
      exit(1);

    if (s->output_type == TCC_OUTPUT_PREPROCESS) {
      if (s->outfile) {
        ppfp = fopen(s->outfile, "w");
        if (!ppfp)
          tcc_error("could not write '%s'", s->outfile);
      }
    } else if (s->output_type == TCC_OUTPUT_SYNTAX) {
      /* --syntax-check：只做词法/语法检查，之后不输出不运行 */
    } else if (s->output_type == TCC_OUTPUT_OBJ && !s->option_r) {
      if (s->nb_libraries)
        tcc_error("cannot specify libraries with -c");
      if (n > 1 && s->outfile)
        tcc_error("cannot specify output file with -c many files");
    } else {
      if (s->option_pthread)
        tcc_set_options(s, "-lpthread");
    }

    if (s->do_bench)
      start_time = getclock_ms();
  }

  /* 环境变量默认值：YH_SYSROOT/-sysroot、YH_LIBDIR/-B（开发期跨系统 -o） */
  {
    const char *e = getenv("YH_SYSROOT");
    const char *b = getenv("YH_LIBDIR");
    /* 空串视为未设置（默认走本机 Mach-O） */
    if (!s->sysroot && e != NULL && e[0] != '\0')
      s->sysroot = tcc_strdup(e);
    if (b != NULL && b[0] != '\0') /* YH_LIBDIR：libtcc1.a 所在目录（等价 -B） */
      tcc_set_lib_path(s, b);
  }
  set_environment(s);
  if (s->output_type == 0)
    s->output_type = TCC_OUTPUT_EXE;
  if (tcc_set_output_type(s, s->output_type) < 0)
    return 1; /* crt 等链接前置缺失：已给出可读诊断 */
  s->ppfp = ppfp;

  if ((s->output_type == TCC_OUTPUT_MEMORY ||
       s->output_type == TCC_OUTPUT_PREPROCESS) &&
      (s->dflag & 16))
    s->dflag |= t ? 32 : 0, s->run_test = ++t, n = s->nb_files;

  /* 逐个编译或添加每个文件/库 */
  for (first_file = NULL, ret = 0;;) {
    struct filespec *f = s->files[s->nb_files - n];
    s->filetype = f->type;
    s->alacarte_link = f->alacarte;
    if (f->type == AFF_TYPE_LIB) {
      if (tcc_add_library_err(s, f->name) < 0)
        ret = 1;
    } else {
      if (1 == s->verbose)
        printf("-> %s\n", f->name);
      if (!first_file)
        first_file = f->name;
      if (tcc_add_file(s, f->name) < 0)
        ret = 1;
    }
    s->filetype = 0;
    s->alacarte_link = 1;
    if (--n == 0 || ret || (s->output_type == TCC_OUTPUT_OBJ && !s->option_r))
      break;
  }

  if (s->run_test) {
    t = 0;
  } else if (s->output_type == TCC_OUTPUT_PREPROCESS) {
    ;
  } else if (s->output_type == TCC_OUTPUT_SYNTAX) {
    ;
  } else if (0 == ret) {
    if (s->output_type == TCC_OUTPUT_MEMORY) {
#ifdef TCC_IS_NATIVE
      ret = tcc_run(s, argc, argv);
#endif
    } else {
      if (!s->outfile)
        s->outfile = default_outputfile(s, first_file);
      if (tcc_output_file(s, s->outfile))
        ret = 1;
      else if (s->gen_deps)
        gen_makedeps(s, s->outfile, s->deps_outfile);
    }
  }

  if (s->do_bench && (n | t | ret) == 0)
    tcc_print_stats(s, getclock_ms() - start_time);
  tcc_delete(s);
  if (ret == 0 && n)
    goto redo; /* 用 -c 继续编译更多文件 */
  if (t)
    goto redo; /* 用 -dt -run 继续运行更多测试 */
  if (ppfp && ppfp != stdout)
    fclose(ppfp);
  return ret;
}
