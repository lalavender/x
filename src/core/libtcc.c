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

/********************************************************/
/* 全局变量 */

/* 使用 GNU C 扩展 */
ST_DATA int gnu_ext = 1;

/* 使用 TinyCC 扩展 */
ST_DATA int tcc_ext = 1;

/* XXX: 尽快去掉这个 */
ST_DATA struct TCCState* tcc_state;

static int nb_states;

/********************************************************/

#if ONE_SOURCE
#include "tccelf.c"
#include "macho-out.c"
#include "tccgen.c"
#include "tccpp.c"
#include "tccrun.c"
#ifdef TCC_TARGET_ARM64
#include "arm64-gen.c"
#include "arm64-link.c"
#endif
/* tccasm.c（CONFIG_TCC_ASM）未启用，不再包含；
   yh 语言解析器（依赖 tccgen/tccpp 的词法与值栈机制） */
#include "yh.h"
#include "yh_builtin.c"
#include "yh_type.c"
#include "yh_expr.c"
#include "yh_stmt.c"
#include "yh_decl.c"
#endif /* ONE_SOURCE */

/********************************************************/
#ifndef CONFIG_TCC_ASM
ST_FUNC void asm_instr(void) { tcc_error("inline asm() not supported"); }
ST_FUNC void asm_global_instr(void) { tcc_error("inline asm() not supported"); }
#endif

/********************************************************/
#ifdef _WIN32
ST_FUNC char* normalize_slashes(char* path) {
  char* p;
  for (p = path; *p; ++p)
    if (*p == '\\') *p = '/';
  return path;
}

static HMODULE tcc_module;

/* 在 win32 上，假定库和头文件位于 'tcc.exe' 所在位置 */
static void tcc_set_lib_path_w32(TCCState* s) {
  char path[1024], *p;
  GetModuleFileNameA(tcc_module, path, sizeof path);
  p = tcc_basename(normalize_slashes(strlwr(path)));
  if (p > path) --p;
  *p = 0;
  tcc_set_lib_path(s, path);
}

#ifdef LIBTCC_AS_DLL
BOOL WINAPI DllMain(HINSTANCE hDll, DWORD dwReason, LPVOID lpReserved) {
  if (DLL_PROCESS_ATTACH == dwReason) tcc_module = hDll;
  return TRUE;
}
#endif
#endif

/********************************************************/
/* 复制字符串并截断。 */
ST_FUNC char* pstrcpy(char* buf, int buf_size, const char* s) {
  char *q, *q_end;
  int c;

  if (buf_size > 0) {
    q = buf;
    q_end = buf + buf_size - 1;
    while (q < q_end) {
      c = *s++;
      if (c == '\0') break;
      *q++ = c;
    }
    *q = '\0';
  }
  return buf;
}

/* 字符串拼接并截断。 */
ST_FUNC char* pstrcat(char* buf, int buf_size, const char* s) {
  int len;
  len = strlen(buf);
  if (len < buf_size) pstrcpy(buf + len, buf_size - len, s);
  return buf;
}

ST_FUNC char* pstrncpy(char* out, const char* in, size_t num) {
  memcpy(out, in, num);
  out[num] = '\0';
  return out;
}

/* 取出文件的基名 */
PUB_FUNC char* tcc_basename(const char* name) {
  char* p = strchr(name, 0);
  while (p > name && !IS_DIRSEP(p[-1])) --p;
  return p;
}

/* 取出文件的扩展名部分
 *
 * （如果没有扩展名，返回指向字符串末尾的指针）
 */
PUB_FUNC char* tcc_fileextension(const char* name) {
  char* b = tcc_basename(name);
  char* e = strrchr(b, '.');
  return e ? e : strchr(b, 0);
}

/********************************************************/
/* 内存管理 */

#undef free
#undef malloc
#undef realloc

#ifndef MEM_DEBUG

PUB_FUNC void tcc_free(void* ptr) { free(ptr); }

PUB_FUNC void* tcc_malloc(unsigned long size) {
  void* ptr;
  ptr = malloc(size);
  if (!ptr && size) tcc_error("memory full (malloc)");
  return ptr;  
}

PUB_FUNC void* tcc_mallocz(unsigned long size) {
  void* ptr;
  ptr = tcc_malloc(size);
  memset(ptr, 0, size);
  return ptr;
}

PUB_FUNC void* tcc_realloc(void* ptr, unsigned long size) {
  void* ptr1;
  ptr1 = realloc(ptr, size);
  if (!ptr1 && size) tcc_error("memory full (realloc)");
  return ptr1;
}

PUB_FUNC char* tcc_strdup(const char* str) {
  char* ptr;
  ptr = tcc_malloc(strlen(str) + 1);
  strcpy(ptr, str);
  return ptr;
}

PUB_FUNC void tcc_memcheck(void) {} 

#else

#define MEM_DEBUG_MAGIC1 0xFEEDDEB1
#define MEM_DEBUG_MAGIC2 0xFEEDDEB2
#define MEM_DEBUG_MAGIC3 0xFEEDDEB3
#define MEM_DEBUG_FILE_LEN 40
#define MEM_DEBUG_CHECK3(header) \
  ((mem_debug_header_t*)((char*)header + header->size))->magic3
#define MEM_USER_PTR(header) \
  ((char*)header + offsetof(mem_debug_header_t, magic3))
#define MEM_HEADER_PTR(ptr) \
  (mem_debug_header_t*)((char*)ptr - offsetof(mem_debug_header_t, magic3))

/*
 * mem_debug_header —— MEM_DEBUG 模式下每块分配的内存头
 *
 * 仅在定义了 MEM_DEBUG 时使用（见 tcc_malloc_debug 等函数）：每次分配的
 * 用户内存前面隐藏一个本结构，用于检测野指针、重复释放、越界写入和内存泄漏。
 *   magic1 / magic2  头部前后哨兵，被改写说明写了越界（释放时校验）；
 *   size             用户可见的字节数；
 *   prev / next      所有活动分配的全局双向链（mem_debug_chain），退出时遍历
 *                    即可报告未释放的块；
 *   line_num/file_name  发起分配的文件与行号，便于定位泄漏来源；
 *   magic3           尾部哨兵，位置由 MEM_DEBUG_CHECK3(header) 按 size 算得。
 * header 的 magic3 字段本身对齐到 16 字节，因此 MEM_USER_PTR()/MEM_HEADER_PTR()
 * 可以在用户指针与头部指针之间互相推算（用 offsetof 做偏移）。
 */
struct mem_debug_header {
  unsigned magic1;
  unsigned size;
  struct mem_debug_header* prev;
  struct mem_debug_header* next;
  int line_num;
  char file_name[MEM_DEBUG_FILE_LEN + 1];
  unsigned magic2;
  ALIGNED(16) unsigned magic3;
};

typedef struct mem_debug_header mem_debug_header_t;

static mem_debug_header_t* mem_debug_chain;
static unsigned mem_cur_size;
static unsigned mem_max_size;

static mem_debug_header_t* malloc_check(void* ptr, const char* msg) {
  mem_debug_header_t* header = MEM_HEADER_PTR(ptr);
  if (header->magic1 != MEM_DEBUG_MAGIC1 ||
      header->magic2 != MEM_DEBUG_MAGIC2 ||
      MEM_DEBUG_CHECK3(header) != MEM_DEBUG_MAGIC3 ||
      header->size == (unsigned)-1) {
    fprintf(stderr, "%s check failed\n", msg);
    if (header->magic1 == MEM_DEBUG_MAGIC1)
      fprintf(stderr, "%s:%u: block allocated here.\n", header->file_name,
              header->line_num);
    exit(1);
  }
  return header;
}

PUB_FUNC void* tcc_malloc_debug(unsigned long size, const char* file,
                                int line) {
  int ofs;
  mem_debug_header_t* header;

  header = malloc(sizeof(mem_debug_header_t) + size);
  if (!header) tcc_error("memory full (malloc)");

  header->magic1 = MEM_DEBUG_MAGIC1;
  header->magic2 = MEM_DEBUG_MAGIC2;
  header->size = size;
  MEM_DEBUG_CHECK3(header) = MEM_DEBUG_MAGIC3;
  header->line_num = line;
  ofs = strlen(file) - MEM_DEBUG_FILE_LEN;
  strncpy(header->file_name, file + (ofs > 0 ? ofs : 0), MEM_DEBUG_FILE_LEN);
  header->file_name[MEM_DEBUG_FILE_LEN] = 0;

  header->next = mem_debug_chain;
  header->prev = NULL;
  if (header->next) header->next->prev = header;
  mem_debug_chain = header;

  mem_cur_size += size;
  if (mem_cur_size > mem_max_size) mem_max_size = mem_cur_size;

  return MEM_USER_PTR(header);
}

PUB_FUNC void tcc_free_debug(void* ptr) {
  mem_debug_header_t* header;
  if (!ptr) return;
  header = malloc_check(ptr, "tcc_free");
  mem_cur_size -= header->size;
  header->size = (unsigned)-1;
  if (header->next) header->next->prev = header->prev;
  if (header->prev) header->prev->next = header->next;
  if (header == mem_debug_chain) mem_debug_chain = header->next;
  free(header);
}

PUB_FUNC void* tcc_mallocz_debug(unsigned long size, const char* file,
                                 int line) {
  void* ptr;
  ptr = tcc_malloc_debug(size, file, line);
  memset(ptr, 0, size);
  return ptr;
}

PUB_FUNC void* tcc_realloc_debug(void* ptr, unsigned long size,
                                 const char* file, int line) {
  mem_debug_header_t* header;
  int mem_debug_chain_update = 0;
  if (!ptr) return tcc_malloc_debug(size, file, line);
  header = malloc_check(ptr, "tcc_realloc");
  mem_cur_size -= header->size;
  mem_debug_chain_update = (header == mem_debug_chain);
  header = realloc(header, sizeof(mem_debug_header_t) + size);
  if (!header) tcc_error("memory full (realloc)");
  header->size = size;
  MEM_DEBUG_CHECK3(header) = MEM_DEBUG_MAGIC3;
  if (header->next) header->next->prev = header;
  if (header->prev) header->prev->next = header;
  if (mem_debug_chain_update) mem_debug_chain = header;
  mem_cur_size += size;
  if (mem_cur_size > mem_max_size) mem_max_size = mem_cur_size;
  return MEM_USER_PTR(header);
}

PUB_FUNC char* tcc_strdup_debug(const char* str, const char* file, int line) {
  char* ptr;
  ptr = tcc_malloc_debug(strlen(str) + 1, file, line);
  strcpy(ptr, str);
  return ptr;
}

PUB_FUNC void tcc_memcheck(void) {
  if (mem_cur_size) {
    mem_debug_header_t* header = mem_debug_chain;
    fprintf(stderr, "MEM_DEBUG: mem_leak= %d bytes, mem_max_size= %d bytes\n",
            mem_cur_size, mem_max_size);
    while (header) {
      fprintf(stderr, "%s:%u: error: %u bytes leaked\n", header->file_name,
              header->line_num, header->size);
      header = header->next;
    }
#if MEM_DEBUG - 0 == 2
    exit(2);
#endif
  }
}
#endif /* MEM_DEBUG */

#define free(p) use_tcc_free(p)
#define malloc(s) use_tcc_malloc(s)
#define realloc(p, s) use_tcc_realloc(p, s)

/********************************************************/
/* 动态数组 */

ST_FUNC void dynarray_add(void* ptab, int* nb_ptr, void* data) {
  int nb, nb_alloc;
  void** pp;

  nb = *nb_ptr;
  pp = *(void***)ptab;
  /* 每当元素个数为 2 的幂时就翻倍数组大小 */
  if ((nb & (nb - 1)) == 0) {
    if (!nb)
      nb_alloc = 1;
    else
      nb_alloc = nb * 2;
    pp = tcc_realloc(pp, nb_alloc * sizeof(void*));
    *(void***)ptab = pp;
  }
  pp[nb++] = data;
  *nb_ptr = nb;
}

ST_FUNC void dynarray_reset(void* pp, int* n) {
  void** p;
  for (p = *(void***)pp; *n; ++p, --*n)
    if (*p) tcc_free(*p);
  tcc_free(*(void**)pp);
  *(void**)pp = NULL;
}

static void tcc_split_path(TCCState* s, void* p_ary, int* p_nb_ary,
                           const char* in) {
  const char* p;
  do {
    int c;
    CString str;

    cstr_new(&str);
    for (p = in; c = *p, c != '\0' && c != PATHSEP[0]; ++p) {
      if (c == '{' && p[1] && p[2] == '}') {
        c = p[1], p += 2;
        if (c == 'B') cstr_cat(&str, s->tcc_lib_path, -1);
      } else {
        cstr_ccat(&str, c);
      }
    }
    if (str.size) {
      cstr_ccat(&str, '\0');
      dynarray_add(p_ary, p_nb_ary, tcc_strdup(str.data));
    }
    cstr_free(&str);
    in = p + 1;
  } while (*p);
}

/********************************************************/

static void strcat_vprintf(char* buf, int buf_size, const char* fmt,
                           va_list ap) {
  int len;
  len = strlen(buf);
  vsnprintf(buf + len, buf_size - len, fmt, ap);
}

static void strcat_printf(char* buf, int buf_size, const char* fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  strcat_vprintf(buf, buf_size, fmt, ap);
  va_end(ap);
}

static void error1(TCCState* s1, int is_warning, const char* fmt, va_list ap) {
  char buf[2048];
  BufferedFile **pf, *f;

  buf[0] = '\0';
  /* 如果是内联 ":asm:" 或词法单元 ":paste:"，则使用上层文件 */
  for (f = file; f && f->filename[0] == ':'; f = f->prev);
  if (f) {
    for (pf = s1->include_stack; pf < s1->include_stack_ptr; pf++)
      strcat_printf(buf, sizeof(buf), "In file included from %s:%d:\n",
                    (*pf)->filename, (*pf)->line_num);
    if (s1->error_set_jmp_enabled) {
      strcat_printf(buf, sizeof(buf), "%s:%d: ", f->filename,
                    f->line_num - !!(tok_flags & TOK_FLAG_BOL));
    } else {
      strcat_printf(buf, sizeof(buf), "%s: ", f->filename);
    }
  } else {
    strcat_printf(buf, sizeof(buf), "tcc: ");
  }
  if (is_warning)
    strcat_printf(buf, sizeof(buf), "warning: ");
  else
    strcat_printf(buf, sizeof(buf), "error: ");
  strcat_vprintf(buf, sizeof(buf), fmt, ap);

  if (!s1->error_func) {
    /* 默认情况：stderr */
    if (s1->output_type == TCC_OUTPUT_PREPROCESS && s1->ppfp == stdout)
      /* 在 tcc -E 期间打印一个换行 */
      printf("\n"), fflush(stdout);
    fflush(stdout); /* 刷新 -v 的输出 */
    fprintf(stderr, "%s\n", buf);
    fflush(stderr); /* 立即打印错误/警告（win32） */
  } else {
    s1->error_func(s1->error_opaque, buf);
  }
  if (!is_warning || s1->warn_error) s1->nb_errors++;
}

LIBTCCAPI void tcc_set_error_func(TCCState* s, void* error_opaque,
                                  void (*error_func)(void* opaque,
                                                     const char* msg)) {
  s->error_opaque = error_opaque;
  s->error_func = error_func;
}

/* 报错但不中止当前编译 */
PUB_FUNC void tcc_error_noabort(const char* fmt, ...) {
  TCCState* s1 = tcc_state;
  va_list ap;

  va_start(ap, fmt);
  error1(s1, 0, fmt, ap);
  va_end(ap);
}

PUB_FUNC void tcc_error(const char* fmt, ...) {
  TCCState* s1 = tcc_state;
  va_list ap;

  va_start(ap, fmt);
  error1(s1, 0, fmt, ap);
  va_end(ap);
  /* 聊胜于无：某些情况下我们接受对错误进行处理 */
  if (s1->error_set_jmp_enabled) {
    longjmp(s1->error_jmp_buf, 1);
  } else {
    /* XXX: 将来去掉这个 */
    exit(1);
  }
}

PUB_FUNC void tcc_warning(const char* fmt, ...) {
  TCCState* s1 = tcc_state;
  va_list ap;

  if (s1->warn_none) return;

  va_start(ap, fmt);
  error1(s1, 1, fmt, ap);
  va_end(ap);
}

/********************************************************/
/* I/O 层 */

ST_FUNC void tcc_open_bf(TCCState* s1, const char* filename, int initlen) {
  BufferedFile* bf;
  int buflen = initlen ? initlen : IO_BUF_SIZE;

  bf = tcc_mallocz(sizeof(BufferedFile) + buflen);
  bf->buf_ptr = bf->buffer;
  bf->buf_end = bf->buffer + initlen;
  bf->buf_end[0] = CH_EOB; /* 放入 eob 符号 */
  pstrcpy(bf->filename, sizeof(bf->filename), filename);
  bf->true_filename = bf->filename;
  bf->line_num = 1;
  bf->ifdef_stack_ptr = s1->ifdef_stack_ptr;
  bf->fd = -1;
  bf->prev = file;
  file = bf;
  tok_flags = TOK_FLAG_BOL | TOK_FLAG_BOF;
}

ST_FUNC void tcc_close(void) {
  BufferedFile* bf = file;
  if (bf->fd > 0) {
    close(bf->fd);
    total_lines += bf->line_num;
  }
  if (bf->true_filename != bf->filename) tcc_free(bf->true_filename);
  file = bf->prev;
  tcc_free(bf);
}

ST_FUNC int tcc_open(TCCState* s1, const char* filename) {
  int fd;
  if (strcmp(filename, "-") == 0)
    fd = 0, filename = "<stdin>";
  else
    fd = open(filename, O_RDONLY | O_BINARY);
  if ((s1->verbose == 2 && fd >= 0) || s1->verbose == 3)
    printf("%s %*s%s\n", fd < 0 ? "nf" : "->",
           (int)(s1->include_stack_ptr - s1->include_stack), "", filename);
  if (fd < 0) return -1;
  tcc_open_bf(s1, filename, 0);
#ifdef _WIN32
  normalize_slashes(file->filename);
#endif
  file->fd = fd;
  return fd;
}

/* 编译在 'file' 中打开的文件。有错误时返回非零。 */
static int tcc_compile(TCCState* s1) {
  Sym* define_start;
  int filetype, is_asm;

  s1->yh_mode = 0; /* C/汇编路径关闭 yh 词法规则 */
  define_start = define_stack;
  filetype = s1->filetype;
  is_asm = filetype == AFF_TYPE_ASM || filetype == AFF_TYPE_ASMPP;
  tccelf_begin_file(s1);

  if (setjmp(s1->error_jmp_buf) == 0) {
    s1->nb_errors = 0;
    s1->error_set_jmp_enabled = 1;

    preprocess_start(s1, is_asm);
    if (s1->output_type == TCC_OUTPUT_PREPROCESS) {
      tcc_preprocess(s1);
    } else if (is_asm) {
#ifdef CONFIG_TCC_ASM
      tcc_assemble(s1, filetype == AFF_TYPE_ASMPP);
#else
      tcc_error_noabort("asm not supported");
#endif
    } else if (s1->yh_mode || filetype == AFF_TYPE_YH) {
      tcc_error_noabort("内部错误：yh 路径不应到达 tccgen_compile");
    } else {
      tcc_error_noabort("yh 编译器不支持 C 源文件（.yh 是唯一输入）");
    }
  }
  s1->error_set_jmp_enabled = 0;

  preprocess_end(s1);
  /* 重置 define 栈，但保留 -D 和内置定义 */
  free_defines(define_start);
  sym_pop(&global_stack, NULL, 0);
  sym_pop(&local_stack, NULL, 0);
  tccelf_end_file(s1);
  return s1->nb_errors != 0 ? -1 : 0;
}

LIBTCCAPI int tcc_compile_string(TCCState* s, const char* str) {
  int len, ret;

  len = strlen(str);
  tcc_open_bf(s, "<string>", len);
  memcpy(file->buffer, str, len);
  ret = tcc_compile(s);
  tcc_close();
  return ret;
}

/* 定义预处理符号。也可以用 '=' 运算符提供一个取值 */
LIBTCCAPI void tcc_define_symbol(TCCState* s1, const char* sym,
                                 const char* value) {
  int len1, len2;
  /* 默认取值 */
  if (!value) value = "1";
  len1 = strlen(sym);
  len2 = strlen(value);

  /* 初始化文件结构体 */
  tcc_open_bf(s1, "<define>", len1 + len2 + 1);
  memcpy(file->buffer, sym, len1);
  file->buffer[len1] = ' ';
  memcpy(file->buffer + len1 + 1, value, len2);

  /* 用 define 解析器解析 */
  next_nomacro();
  parse_define();
  tcc_close();
}

/* 取消一个预处理符号的定义 */
LIBTCCAPI void tcc_undefine_symbol(TCCState* s1, const char* sym) {
  TokenSym* ts;
  Sym* s;
  ts = tok_alloc(sym, strlen(sym));
  s = define_find(ts->tok);
  /* 通过放入一个非法名字来取消符号定义 */
  if (s) define_undef(s);
}

/* 清理编译期间使用的所有静态数据 */
static void tcc_cleanup(void) {
  if (NULL == tcc_state) return;
  while (file) tcc_close();
  tccpp_delete(tcc_state);
  tcc_state = NULL;
  /* 释放 sym_pools */
  dynarray_reset(&sym_pools, &nb_sym_pools);
  /* 重置符号栈 */
  sym_free_first = NULL;
}

LIBTCCAPI TCCState* tcc_new(void) {
  TCCState* s;

  tcc_cleanup();

  s = tcc_mallocz(sizeof(TCCState));
  if (!s) return NULL;
  tcc_state = s;
  ++nb_states;

  s->alacarte_link = 1;
  s->nocommon = 1;
  s->warn_implicit_function_declaration = 1;
  s->ms_extensions = 1;

#ifdef CHAR_IS_UNSIGNED
  s->char_is_unsigned = 1;
#endif
#ifdef _WIN32
  tcc_set_lib_path_w32(s);
#else
  tcc_set_lib_path(s, CONFIG_TCCDIR);
#endif
  tccelf_new(s);
  tccpp_new(s);

  /* 我们为一些特殊宏加入哑定义，以加快判断速度
     并让 defined() 正常工作 */
  define_push(TOK___LINE__, MACRO_OBJ, NULL, NULL);
  define_push(TOK___FILE__, MACRO_OBJ, NULL, NULL);
  define_push(TOK___DATE__, MACRO_OBJ, NULL, NULL);
  define_push(TOK___TIME__, MACRO_OBJ, NULL, NULL);
  define_push(TOK___COUNTER__, MACRO_OBJ, NULL, NULL);
  {
    /* 定义 __TINYC__ 92X  */
    char buffer[32];
    int a, b, c;
    sscanf(TCC_VERSION, "%d.%d.%d", &a, &b, &c);
    sprintf(buffer, "%d", a * 10000 + b * 100 + c);
    tcc_define_symbol(s, "__TINYC__", buffer);
  }

  /* 标准定义 */
  tcc_define_symbol(s, "__STDC__", NULL);
  tcc_define_symbol(s, "__STDC_VERSION__", "199901L");
  tcc_define_symbol(s, "__STDC_HOSTED__", NULL);

  /* 目标平台定义 */
  tcc_define_symbol(s, "__aarch64__", NULL);

  tcc_define_symbol(s, "__unix__", NULL);
  tcc_define_symbol(s, "__unix", NULL);
  tcc_define_symbol(s, "unix", NULL);
#if defined(__linux__)
  tcc_define_symbol(s, "__linux__", NULL);
  tcc_define_symbol(s, "__linux", NULL);
#endif
#if defined(__FreeBSD__)
  tcc_define_symbol(s, "__FreeBSD__", "__FreeBSD__");
  /* 在 FreeBSD 上用 tcc 时没有 'Thread Storage Local' */
  tcc_define_symbol(s, "__NO_TLS", NULL);
#endif
#if defined(__FreeBSD_kernel__)
  tcc_define_symbol(s, "__FreeBSD_kernel__", NULL);
#endif
#if defined(__NetBSD__)
  tcc_define_symbol(s, "__NetBSD__", "__NetBSD__");
#endif
#if defined(__OpenBSD__)
  tcc_define_symbol(s, "__OpenBSD__", "__OpenBSD__");
#endif

  /* TinyCC 与 gcc 的定义 */
#if PTR_SIZE == 4
  /* 32 位系统。 */
  tcc_define_symbol(s, "__SIZE_TYPE__", "unsigned int");
  tcc_define_symbol(s, "__PTRDIFF_TYPE__", "int");
  tcc_define_symbol(s, "__ILP32__", NULL);
#elif LONG_SIZE == 4
  /* 64 位 Windows。 */
  tcc_define_symbol(s, "__SIZE_TYPE__", "unsigned long long");
  tcc_define_symbol(s, "__PTRDIFF_TYPE__", "long long");
  tcc_define_symbol(s, "__LLP64__", NULL);
#else
  /* 其他 64 位系统。 */
  tcc_define_symbol(s, "__SIZE_TYPE__", "unsigned long");
  tcc_define_symbol(s, "__PTRDIFF_TYPE__", "long");
  tcc_define_symbol(s, "__LP64__", NULL);
#endif

  tcc_define_symbol(s, "__WCHAR_TYPE__", "int");
  /* wint_t 默认是 unsigned int，但在 BSD 上是 (signed) int，
     在 windows 上是 unsigned short。其他系统可能还有
     别的约定，唉。  */
#if defined(__FreeBSD__) || defined(__FreeBSD_kernel__) || \
    defined(__NetBSD__) || defined(__OpenBSD__)
  tcc_define_symbol(s, "__WINT_TYPE__", "int");
#ifdef __FreeBSD__
  /* 定义 __GNUC__ 以便从 sys/cdefs.h 得到一些有用的东西，
     它们被 FreeBSD 的其他系统头文件无条件使用 :/ */
  tcc_define_symbol(s, "__GNUC__", "2");
  tcc_define_symbol(s, "__GNUC_MINOR__", "7");
  tcc_define_symbol(s, "__builtin_alloca", "alloca");
#endif
#else
  tcc_define_symbol(s, "__WINT_TYPE__", "unsigned int");
  /* glibc 的定义 */
  tcc_define_symbol(s, "__REDIRECT(name, proto, alias)",
                    "name proto __asm__ (#alias)");
  tcc_define_symbol(s, "__REDIRECT_NTH(name, proto, alias)",
                    "name proto __asm__ (#alias) __THROW");
#endif
#if defined(TCC_MUSL)
  tcc_define_symbol(s, "__DEFINED_va_list", "");
  tcc_define_symbol(s, "__DEFINED___isoc_va_list", "");
  tcc_define_symbol(s, "__isoc_va_list", "void *");
#endif /* TCC_MUSL */
  /* 一些可以简单表示为宏的 GCC 内建函数。  */
  tcc_define_symbol(s, "__builtin_extract_return_addr(x)", "x");
  return s;
}

LIBTCCAPI void tcc_delete(TCCState* s1) {
  tcc_cleanup();

  /* 释放段 */
  tccelf_delete(s1);

  /* 释放库路径 */
  dynarray_reset(&s1->library_paths, &s1->nb_library_paths);
  dynarray_reset(&s1->crt_paths, &s1->nb_crt_paths);

  /* 释放头文件路径 */
  dynarray_reset(&s1->cached_includes, &s1->nb_cached_includes);
  dynarray_reset(&s1->include_paths, &s1->nb_include_paths);
  dynarray_reset(&s1->sysinclude_paths, &s1->nb_sysinclude_paths);
  dynarray_reset(&s1->cmd_include_files, &s1->nb_cmd_include_files);

  tcc_free(s1->tcc_lib_path);
  tcc_free(s1->soname);
  tcc_free(s1->rpath);
  tcc_free(s1->init_symbol);
  tcc_free(s1->fini_symbol);
  tcc_free(s1->outfile);
  tcc_free(s1->deps_outfile);
  dynarray_reset(&s1->files, &s1->nb_files);
  dynarray_reset(&s1->target_deps, &s1->nb_target_deps);
  dynarray_reset(&s1->pragma_libs, &s1->nb_pragma_libs);
  dynarray_reset(&s1->argv, &s1->argc);

#ifdef TCC_IS_NATIVE
  /* 释放运行时内存 */
  tcc_run_free(s1);
#endif

  tcc_free(s1);
  if (0 == --nb_states) tcc_memcheck();
}

LIBTCCAPI int tcc_set_output_type(TCCState* s, int output_type) {
  s->output_type = output_type;

  /* 目标文件格式：Darwin 本机默认 Mach-O（-sysroot 交叉 Linux 时保持 ELF，
     显式 -Wl,-oformat= 时尊重用户选择） */
  if ((output_type == TCC_OUTPUT_EXE || output_type == TCC_OUTPUT_OBJ) &&
      !s->output_format_explicit) {
#ifdef __APPLE__
    if (!s->sysroot)
      s->output_format = TCC_OUTPUT_FORMAT_MACHO;
    else
      s->output_format = TCC_OUTPUT_FORMAT_ELF;
#else
    s->output_format = TCC_OUTPUT_FORMAT_ELF;
#endif
  } else if (output_type == TCC_OUTPUT_OBJ) {
    s->output_format = TCC_OUTPUT_FORMAT_ELF;
  }
  /* Mach-O 符号名带前导下划线（Darwin 惯例），编译期统一生效 */
  if (s->output_format == TCC_OUTPUT_FORMAT_MACHO)
    s->leading_underscore = 1;

  if (s->char_is_unsigned) tcc_define_symbol(s, "__CHAR_UNSIGNED__", NULL);

  if (!s->nostdinc) {
    /* 默认头文件路径；-sysroot 时前缀到 sysroot */
    /* -isystem 路径已经处理过了 */
    if (s->sysroot) {
      char buf[1024];
      snprintf(buf, sizeof buf, "%s/usr/local/include:%s/usr/include",
               s->sysroot, s->sysroot);
      tcc_add_sysinclude_path(s, buf);
    } else {
      tcc_add_sysinclude_path(s, CONFIG_TCC_SYSINCLUDEPATHS);
    }
  }

#ifdef CONFIG_TCC_BCHECK
  if (s->do_bounds_check) {
    /* 如果做边界检查，就加入相应的段 */
    tccelf_bounds_new(s);
    /* 定义符号 */
    tcc_define_symbol(s, "__BOUNDS_CHECKING_ON", NULL);
  }
#endif
  if (s->do_debug) {
    /* 加入调试段 */
    tccelf_stab_new(s);
  }

  if (s->output_format == TCC_OUTPUT_FORMAT_MACHO) {
    /* 本机输出：crt/libc 由 Apple 链接器（cc）负责，这里不找 sysroot */
    return 0;
  }
  if (s->sysroot) {
    char buf[2048];
    /* 兼容通用布局与 Ubuntu 的 multiarch 子目录 */
    snprintf(buf, sizeof buf,
             "%s/usr/lib:%s/lib:%s/usr/lib/aarch64-linux-gnu:"
             "%s/lib/aarch64-linux-gnu",
             s->sysroot, s->sysroot, s->sysroot, s->sysroot);
    tcc_add_library_path(s, buf);
    /* crt 目标文件的路径 */
    tcc_split_path(s, &s->crt_paths, &s->nb_crt_paths, buf);
  } else {
    tcc_add_library_path(s, CONFIG_TCC_LIBPATHS);
    /* crt 目标文件的路径 */
    tcc_split_path(s, &s->crt_paths, &s->nb_crt_paths, CONFIG_TCC_CRTPREFIX);
  }
  /* 加入 libc 的 crt1/crti 目标文件；缺失即致命（链接无法进行） */
  if ((output_type == TCC_OUTPUT_EXE || output_type == TCC_OUTPUT_DLL) &&
      !s->nostdlib) {
    if (output_type != TCC_OUTPUT_DLL && s->nb_crt_paths &&
        tcc_add_crt(s, "crt1.o"))
      return -1;
    if (s->nb_crt_paths && tcc_add_crt(s, "crti.o"))
      return -1;
  }
  return 0;
}

LIBTCCAPI int tcc_add_include_path(TCCState* s, const char* pathname) {
  tcc_split_path(s, &s->include_paths, &s->nb_include_paths, pathname);
  return 0;
}

LIBTCCAPI int tcc_add_sysinclude_path(TCCState* s, const char* pathname) {
  tcc_split_path(s, &s->sysinclude_paths, &s->nb_sysinclude_paths, pathname);
  return 0;
}

ST_FUNC int tcc_add_file_internal(TCCState* s1, const char* filename,
                                  int flags) {
  int ret;

  /* 打开文件 */
  ret = tcc_open(s1, filename);
  if (ret < 0) {
    if (flags & AFF_PRINT_ERROR)
      tcc_error_noabort("file '%s' not found", filename);
    return ret;
  }

  /* 更新目标依赖 */
  dynarray_add(&s1->target_deps, &s1->nb_target_deps, tcc_strdup(filename));

  if (flags & AFF_TYPE_BIN) {
    ElfW(Ehdr) ehdr;
    int fd, obj_type;

    fd = file->fd;
    obj_type = tcc_object_type(fd, &ehdr);
    lseek(fd, 0, SEEK_SET);


    switch (obj_type) {
      case AFF_BINTYPE_REL:
        ret = tcc_load_object_file(s1, fd, 0);
        break;
      case AFF_BINTYPE_DYN:
        if (s1->output_type == TCC_OUTPUT_MEMORY) {
          ret = 0;
#ifdef TCC_IS_NATIVE
          if (NULL == dlopen(filename, RTLD_GLOBAL | RTLD_LAZY)) ret = -1;
#endif
        } else {
          ret =
              tcc_load_dll(s1, fd, filename, (flags & AFF_REFERENCED_DLL) != 0);
        }
        break;
      case AFF_BINTYPE_AR:
        ret = tcc_load_archive(s1, fd);
        break;
      default:
        /* 与 GNU ld 一样，无法识别时就当作 ld 脚本 */
        ret = tcc_load_ldscript(s1);
        if (ret < 0) tcc_error_noabort("unrecognized file type");
        break;
    }
  } else if (s1->filetype == AFF_TYPE_YH) {
    /* yh 用户源文件：进入 yh 解析路径（yh_decl.c 的 yh_compile） */
    ret = yh_compile(s1);
  } else {
    ret = tcc_compile(s1);
  }
  tcc_close();
  return ret;
}

LIBTCCAPI int tcc_add_file(TCCState* s, const char* filename) {
  int filetype = s->filetype;
  int flags = AFF_PRINT_ERROR;
  if (filetype == 0) {
    /* 用文件扩展名判断文件类型 */
    const char* ext = tcc_fileextension(filename);
    if (ext[0]) {
      ext++;
      if (!strcmp(ext, "S"))
        filetype = AFF_TYPE_ASMPP;
      else if (!strcmp(ext, "s"))
        filetype = AFF_TYPE_ASM;
      else if (!PATHCMP(ext, "yh"))
        filetype = AFF_TYPE_YH; /* yh 用户源文件 */
      else if (!PATHCMP(ext, "c") || !PATHCMP(ext, "i"))
        filetype = AFF_TYPE_C;
      else
        flags |= AFF_TYPE_BIN;
    } else {
      filetype = AFF_TYPE_C;
    }
    s->filetype = filetype;
  }
  return tcc_add_file_internal(s, filename, flags);
}

LIBTCCAPI int tcc_add_library_path(TCCState* s, const char* pathname) {
  tcc_split_path(s, &s->library_paths, &s->nb_library_paths, pathname);
  return 0;
}

static int tcc_add_library_internal(TCCState* s, const char* fmt,
                                    const char* filename, int flags,
                                    char** paths, int nb_paths) {
  char buf[1024];
  int i;

  for (i = 0; i < nb_paths; i++) {
    snprintf(buf, sizeof(buf), fmt, paths[i], filename);
    if (tcc_add_file_internal(s, buf, flags | AFF_TYPE_BIN) == 0) return 0;
  }
  return -1;
}

/* 查找并加载 dll。未找到时返回非零 */
/* XXX: 要加 '-rpath' 选项支持吗？ */
ST_FUNC int tcc_add_dll(TCCState* s, const char* filename, int flags) {
  return tcc_add_library_internal(s, "%s/%s", filename, flags, s->library_paths,
                                  s->nb_library_paths);
}

ST_FUNC int tcc_add_crt(TCCState* s, const char* filename) {
  if (-1 == tcc_add_library_internal(s, "%s/%s", filename, 0, s->crt_paths,
                                     s->nb_crt_paths)) {
    tcc_error_noabort("file '%s' not found（-sysroot 指定含 crt 的 sysroot）",
                      filename);
    return -1;
  }
  return 0;
}

/* 库名与 '-l' 选项的参数相同 */
LIBTCCAPI int tcc_add_library(TCCState* s, const char* libraryname) {
  const char* libs[] = {"%s/lib%s.so", "%s/lib%s.a", NULL};
  const char** pp = s->static_link ? libs + 1 : libs;
  while (*pp) {
    if (0 == tcc_add_library_internal(s, *pp, libraryname, 0, s->library_paths,
                                      s->nb_library_paths))
      return 0;
    ++pp;
  }
  return -1;
}

PUB_FUNC int tcc_add_library_err(TCCState* s, const char* libname) {
  int ret = tcc_add_library(s, libname);
  if (ret < 0) tcc_error_noabort("library '%s' not found", libname);
  return ret;
}

/* 处理 #pragma comment(lib,) */
ST_FUNC void tcc_add_pragma_libs(TCCState* s1) {
  int i;
  for (i = 0; i < s1->nb_pragma_libs; i++)
    tcc_add_library_err(s1, s1->pragma_libs[i]);
}

LIBTCCAPI int tcc_add_symbol(TCCState* s, const char* name, const void* val) {
  set_elf_sym(symtab_section, (uintptr_t)val, 0,
              ELFW(ST_INFO)(STB_GLOBAL, STT_NOTYPE), 0, SHN_ABS, name);
  return 0;
}

LIBTCCAPI void tcc_set_lib_path(TCCState* s, const char* path) {
  tcc_free(s->tcc_lib_path);
  s->tcc_lib_path = tcc_strdup(path);
}

#define WD_ALL 0x0001    /* 使用 -Wall 时该警告被激活 */
#define FD_INVERT 0x0002 /* 存储前把取值取反 */

/*
 * FlagDef —— 布尔型选项/警告开关的名字表项
 *
 * 用于把 -Wxxx、-fxxx 这类“只有开/关”的选项映射到 TCCState 的某个 int 字段：
 *   offset 是该字段在 TCCState 中的字节偏移（用 offsetof() 填写），
 *   flags  见上面的 WD_ALL（受 -Wall 影响）与 FD_INVERT（存入前取反），
 *   name   是选项名，表以 name == NULL 结束。
 * 解析时按名字查表，直接改写 s->offset
 * 处的字段，因此新增一个开关只需加一行表项。
 */
typedef struct FlagDef {
  uint16_t offset;
  uint16_t flags;
  const char* name;
} FlagDef;

static int no_flag(const char** pp) {
  const char* p = *pp;
  if (*p != 'n' || *++p != 'o' || *++p != '-') return 0;
  *pp = p + 1;
  return 1;
}

ST_FUNC int set_flag(TCCState* s, const FlagDef* flags, const char* name) {
  int value, ret;
  const FlagDef* p;
  const char* r;

  value = 1;
  r = name;
  if (no_flag(&r)) value = 0;

  for (ret = -1, p = flags; p->name; ++p) {
    if (ret) {
      if (strcmp(r, p->name)) continue;
    } else {
      if (0 == (p->flags & WD_ALL)) continue;
    }
    if (p->offset) {
      *(int*)((char*)s + p->offset) = p->flags & FD_INVERT ? !value : value;
      if (ret) return 0;
    } else {
      ret = 0;
    }
  }
  return ret;
}

static int strstart(const char* val, const char** str) {
  const char *p, *q;
  p = *str;
  q = val;
  while (*q) {
    if (*p != *q) return 0;
    p++;
    q++;
  }
  *str = p;
  return 1;
}

/* 类似 strstart，但自动考虑到 ld 选项可能
 *
 * - 以双短横线或单短横线开头（例如 '--soname' 或 '-soname'）
 * - 参数可以分开给出，也可以写在 '=' 之后（例如 '-Wl,-soname,x.so'
 *   或 '-Wl,-soname=x.so'）
 *
 * 传入的 `val` 始终是 'option[=]' 形式（不带开头的 -）
 */
static int link_option(const char* str, const char* val, const char** ptr) {
  const char *p, *q;
  int ret;

  /* 这里应该有 1 个或 2 个短横线 */
  if (*str++ != '-') return 0;
  if (*str == '-') str++;

  /* 然后 str 与 val 应当匹配（最多到 '=' 处） */
  p = str;
  q = val;

  ret = 1;
  if (q[0] == '?') {
    ++q;
    if (no_flag(&p)) ret = -1;
  }

  while (*q != '\0' && *q != '=') {
    if (*p != *q) return 0;
    p++;
    q++;
  }

  /* '=' 靠近字符串末尾表示 ',' 或 '=' 都可以 */
  if (*q == '=') {
    if (*p == 0) *ptr = p;
    if (*p != ',' && *p != '=') return 0;
    p++;
  } else if (*p) {
    return 0;
  }
  *ptr = p;
  return ret;
}

static const char* skip_linker_arg(const char** str) {
  const char* s1 = *str;
  const char* s2 = strchr(s1, ',');
  *str = s2 ? s2++ : (s2 = s1 + strlen(s1));
  return s2;
}

static void copy_linker_arg(char** pp, const char* s, int sep) {
  const char* q = s;
  char* p = *pp;
  int l = 0;
  if (p && sep) p[l = strlen(p)] = sep, ++l;
  skip_linker_arg(&q);
  pstrncpy(l + (*pp = tcc_realloc(p, q - s + l + 1)), s, q - s);
}

/* 设置链接器选项 */
static int tcc_set_linker(TCCState* s, const char* option) {
  while (*option) {
    const char* p = NULL;
    char* end = NULL;
    int ignoring = 0;
    int ret;

    if (link_option(option, "Bsymbolic", &p)) {
      s->symbolic = 1;
    } else if (link_option(option, "nostdlib", &p)) {
      s->nostdlib = 1;
    } else if (link_option(option, "fini=", &p)) {
      copy_linker_arg(&s->fini_symbol, p, 0);
      ignoring = 1;
    } else if (link_option(option, "image-base=", &p) ||
               link_option(option, "Ttext=", &p)) {
      s->text_addr = strtoull(p, &end, 16);
      s->has_text_addr = 1;
    } else if (link_option(option, "init=", &p)) {
      copy_linker_arg(&s->init_symbol, p, 0);
      ignoring = 1;
    } else if (link_option(option, "oformat=", &p)) {
#if PTR_SIZE == 8
      if (strstart("elf64-", &p)) {
#else
      if (strstart("elf32-", &p)) {
#endif
        s->output_format = TCC_OUTPUT_FORMAT_ELF;
      } else if (!strcmp(p, "binary")) {
        s->output_format = TCC_OUTPUT_FORMAT_BINARY;
      } else if (!strcmp(p, "macho64")) {
        s->output_format = TCC_OUTPUT_FORMAT_MACHO;
      } else
        goto err;
      s->output_format_explicit = 1;

    } else if (link_option(option, "as-needed", &p)) {
      ignoring = 1;
    } else if (link_option(option, "O", &p)) {
      ignoring = 1;
    } else if (link_option(option, "export-all-symbols", &p)) {
      s->rdynamic = 1;
    } else if (link_option(option, "rpath=", &p)) {
      copy_linker_arg(&s->rpath, p, ':');
    } else if (link_option(option, "enable-new-dtags", &p)) {
      s->enable_new_dtags = 1;
    } else if (link_option(option, "section-alignment=", &p)) {
      s->section_align = strtoul(p, &end, 16);
    } else if (link_option(option, "soname=", &p)) {
      copy_linker_arg(&s->soname, p, 0);
    } else if (ret = link_option(option, "?whole-archive", &p), ret) {
      s->alacarte_link = ret < 0;
    } else if (p) {
      return 0;
    } else {
    err:
      tcc_error("unsupported linker option '%s'", option);
    }

    if (ignoring && s->warn_unsupported)
      tcc_warning("unsupported linker option '%s'", option);

    option = skip_linker_arg(&p);
  }
  return 1;
}

/*
 * TCCOption —— 命令行选项表项（tcc_parse_args 用）
 *
 * name  选项名（不含前导 '-'，长选项写成 "Wl," 这种带逗号的形式），
 * index 选项编号，取值是下面 enum 里的 TCC_OPTION_xxx，
 * flags 见 TCC_OPTION_HAS_ARG（需要一个参数）与 TCC_OPTION_NOSEP
 *       （参数必须紧跟选项，中间不能有空格）。
 * 解析时按前缀匹配查表，再在 switch (option->index) 中分派具体处理。
 */
typedef struct TCCOption {
  const char* name;
  uint16_t index;
  uint16_t flags;
} TCCOption;

enum {
  TCC_OPTION_HELP,
  TCC_OPTION_HELP2,
  TCC_OPTION_v,
  TCC_OPTION_I,
  TCC_OPTION_D,
  TCC_OPTION_U,
  TCC_OPTION_P,
  TCC_OPTION_L,
  TCC_OPTION_B,
  TCC_OPTION_l,
  TCC_OPTION_bench,
  TCC_OPTION_bt,
  TCC_OPTION_b,
  TCC_OPTION_g,
  TCC_OPTION_c,
  TCC_OPTION_dumpversion,
  TCC_OPTION_d,
  TCC_OPTION_static,
  TCC_OPTION_std,
  TCC_OPTION_shared,
  TCC_OPTION_soname,
  TCC_OPTION_o,
  TCC_OPTION_r,
  TCC_OPTION_s,
  TCC_OPTION_traditional,
  TCC_OPTION_Wl,
  TCC_OPTION_Wp,
  TCC_OPTION_W,
  TCC_OPTION_O,
  TCC_OPTION_m,
  TCC_OPTION_f,
  TCC_OPTION_isystem,
  TCC_OPTION_iwithprefix,
  TCC_OPTION_include,
  TCC_OPTION_nostdinc,
  TCC_OPTION_nostdlib,
  TCC_OPTION_print_search_dirs,
  TCC_OPTION_rdynamic,
  TCC_OPTION_param,
  TCC_OPTION_pedantic,
  TCC_OPTION_pthread,
  TCC_OPTION_run,
  TCC_OPTION_w,
  TCC_OPTION_pipe,
  TCC_OPTION_E,
  TCC_OPTION_MD,
  TCC_OPTION_MF,
  TCC_OPTION_x,
  TCC_OPTION_ar,
  TCC_OPTION_syntax_check,
  TCC_OPTION_sysroot,
  TCC_OPTION_impdef
};

#define TCC_OPTION_HAS_ARG 0x0001
#define TCC_OPTION_NOSEP 0x0002 /* 选项与参数之间不能有空格 */

static const TCCOption tcc_options[] = {
    {"h", TCC_OPTION_HELP, 0},
    {"-help", TCC_OPTION_HELP, 0},
    {"?", TCC_OPTION_HELP, 0},
    {"hh", TCC_OPTION_HELP2, 0},
    {"v", TCC_OPTION_v, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"I", TCC_OPTION_I, TCC_OPTION_HAS_ARG},
    {"D", TCC_OPTION_D, TCC_OPTION_HAS_ARG},
    {"U", TCC_OPTION_U, TCC_OPTION_HAS_ARG},
    {"P", TCC_OPTION_P, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"L", TCC_OPTION_L, TCC_OPTION_HAS_ARG},
    {"B", TCC_OPTION_B, TCC_OPTION_HAS_ARG},
    {"l", TCC_OPTION_l, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"bench", TCC_OPTION_bench, 0},
#ifdef CONFIG_TCC_BACKTRACE
    {"bt", TCC_OPTION_bt, TCC_OPTION_HAS_ARG},
#endif
#ifdef CONFIG_TCC_BCHECK
    {"b", TCC_OPTION_b, 0},
#endif
    {"g", TCC_OPTION_g, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"c", TCC_OPTION_c, 0},
    {"dumpversion", TCC_OPTION_dumpversion, 0},
    {"d", TCC_OPTION_d, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"static", TCC_OPTION_static, 0},
    {"std", TCC_OPTION_std, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"shared", TCC_OPTION_shared, 0},
    {"soname", TCC_OPTION_soname, TCC_OPTION_HAS_ARG},
    {"o", TCC_OPTION_o, TCC_OPTION_HAS_ARG},
    {"-param", TCC_OPTION_param, TCC_OPTION_HAS_ARG},
    {"pedantic", TCC_OPTION_pedantic, 0},
    {"pthread", TCC_OPTION_pthread, 0},
    {"run", TCC_OPTION_run, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"rdynamic", TCC_OPTION_rdynamic, 0},
    {"r", TCC_OPTION_r, 0},
    {"s", TCC_OPTION_s, 0},
    {"traditional", TCC_OPTION_traditional, 0},
    {"Wl,", TCC_OPTION_Wl, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"Wp,", TCC_OPTION_Wp, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"W", TCC_OPTION_W, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"O", TCC_OPTION_O, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"m", TCC_OPTION_m, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"f", TCC_OPTION_f, TCC_OPTION_HAS_ARG | TCC_OPTION_NOSEP},
    {"isystem", TCC_OPTION_isystem, TCC_OPTION_HAS_ARG},
    {"include", TCC_OPTION_include, TCC_OPTION_HAS_ARG},
    {"nostdinc", TCC_OPTION_nostdinc, 0},
    {"nostdlib", TCC_OPTION_nostdlib, 0},
    {"print-search-dirs", TCC_OPTION_print_search_dirs, 0},
    {"w", TCC_OPTION_w, 0},
    {"pipe", TCC_OPTION_pipe, 0},
    {"E", TCC_OPTION_E, 0},
    {"MD", TCC_OPTION_MD, 0},
    {"MF", TCC_OPTION_MF, TCC_OPTION_HAS_ARG},
    {"x", TCC_OPTION_x, TCC_OPTION_HAS_ARG},
    {"ar", TCC_OPTION_ar, 0},
    {"syntax-check", TCC_OPTION_syntax_check, 0},
    {"sysroot", TCC_OPTION_sysroot, TCC_OPTION_HAS_ARG},
    {NULL, 0, 0},
};

static const FlagDef options_W[] = {
    {0, 0, "all"},
    {offsetof(TCCState, warn_unsupported), 0, "unsupported"},
    {offsetof(TCCState, warn_write_strings), 0, "write-strings"},
    {offsetof(TCCState, warn_error), 0, "error"},
    {offsetof(TCCState, warn_gcc_compat), 0, "gcc-compat"},
    {offsetof(TCCState, warn_implicit_function_declaration), WD_ALL,
     "implicit-function-declaration"},
    {0, 0, NULL}};

static const FlagDef options_f[] = {
    {offsetof(TCCState, char_is_unsigned), 0, "unsigned-char"},
    {offsetof(TCCState, char_is_unsigned), FD_INVERT, "signed-char"},
    {offsetof(TCCState, nocommon), FD_INVERT, "common"},
    {offsetof(TCCState, leading_underscore), 0, "leading-underscore"},
    {offsetof(TCCState, ms_extensions), 0, "ms-extensions"},
    {offsetof(TCCState, dollars_in_identifiers), 0, "dollars-in-identifiers"},
    {0, 0, NULL}};

static const FlagDef options_m[] = {
    {offsetof(TCCState, ms_bitfields), 0, "ms-bitfields"}, {0, 0, NULL}};

static void parse_option_D(TCCState* s1, const char* optarg) {
  char* sym = tcc_strdup(optarg);
  char* value = strchr(sym, '=');
  if (value) *value++ = '\0';
  tcc_define_symbol(s1, sym, value);
  tcc_free(sym);
}

static void args_parser_add_file(TCCState* s, const char* filename,
                                 int filetype) {
  struct filespec* f = tcc_malloc(sizeof *f + strlen(filename));
  f->type = filetype;
  f->alacarte = s->alacarte_link;
  strcpy(f->name, filename);
  dynarray_add(&s->files, &s->nb_files, f);
}

static int args_parser_make_argv(const char* r, int* argc, char*** argv) {
  int ret = 0, q, c;
  CString str;
  for (;;) {
    while (c = (unsigned char)*r, c && c <= ' ') ++r;
    if (c == 0) break;
    q = 0;
    cstr_new(&str);
    while (c = (unsigned char)*r, c) {
      ++r;
      if (c == '\\' && (*r == '"' || *r == '\\')) {
        c = *r++;
      } else if (c == '"') {
        q = !q;
        continue;
      } else if (q == 0 && c <= ' ') {
        break;
      }
      cstr_ccat(&str, c);
    }
    cstr_ccat(&str, 0);
    // printf("<%s>\n", str.data), fflush(stdout);  /* 调试输出 */
    dynarray_add(argv, argc, tcc_strdup(str.data));
    cstr_free(&str);
    ++ret;
  }
  return ret;
}

/* 读取列表文件 */
static void args_parser_listfile(TCCState* s, const char* filename, int optind,
                                 int* pargc, char*** pargv) {
  int fd, i;
  size_t len;
  char* p;
  int argc = 0;
  char** argv = NULL;

  fd = open(filename, O_RDONLY | O_BINARY);
  if (fd < 0) tcc_error("listfile '%s' not found", filename);

  len = lseek(fd, 0, SEEK_END);
  p = tcc_malloc(len + 1), p[len] = 0;
  lseek(fd, 0, SEEK_SET), read(fd, p, len), close(fd);

  for (i = 0; i < *pargc; ++i)
    if (i == optind)
      args_parser_make_argv(p, &argc, &argv);
    else
      dynarray_add(&argv, &argc, tcc_strdup((*pargv)[i]));

  tcc_free(p);
  dynarray_reset(&s->argv, &s->argc);
  *pargc = s->argc = argc, *pargv = s->argv = argv;
}

PUB_FUNC int tcc_parse_args(TCCState* s, int* pargc, char*** pargv,
                            int optind) {
  const TCCOption* popt;
  const char *optarg, *r;
  const char* run = NULL;
  int last_o = -1;
  int x;
  CString linker_arg; /* 收集 -Wl 选项 */
  int tool = 0, arg_start = 0, noaction = optind;
  char** argv = *pargv;
  int argc = *pargc;

  cstr_new(&linker_arg);

  while (optind < argc) {
    r = argv[optind];
    if (r[0] == '@' && r[1] != '\0') {
      args_parser_listfile(s, r + 1, optind, &argc, &argv);
      continue;
    }
    optind++;
    if (tool) {
      if (r[0] == '-' && r[1] == 'v' && r[2] == 0) ++s->verbose;
      continue;
    }
  reparse:
    if (r[0] != '-' || r[1] == '\0') {
      if (r[0] != '@') /* 允许 "tcc file(s) -run @ args ..." */
        args_parser_add_file(s, r, s->filetype);
      if (run) {
        tcc_set_options(s, run);
        arg_start = optind - 1;
        break;
      }
      continue;
    }
    /* 长选项的 '--' 前缀等价于 '-'（"--" 本身除外，仍按选项表报错） */
    if (r[0] == '-' && r[1] == '-' && r[2] != '\0')
      ++r;

    /* 在表中查找选项 */
    for (popt = tcc_options;; ++popt) {
      const char* p1 = popt->name;
      const char* r1 = r + 1;
      if (p1 == NULL) tcc_error("invalid option -- '%s'", r);
      if (!strstart(p1, &r1)) continue;
      optarg = r1;
      if (popt->flags & TCC_OPTION_HAS_ARG) {
        if (*r1 == '\0' && !(popt->flags & TCC_OPTION_NOSEP)) {
          if (optind >= argc)
          arg_err:
            tcc_error("argument to '%s' is missing", r);
          optarg = argv[optind++];
        }
      } else if (*r1 != '\0')
        continue;
      break;
    }

    switch (popt->index) {
      case TCC_OPTION_HELP:
        return OPT_HELP;
      case TCC_OPTION_HELP2:
        return OPT_HELP2;
      case TCC_OPTION_I:
        tcc_add_include_path(s, optarg);
        break;
      case TCC_OPTION_D:
        parse_option_D(s, optarg);
        break;
      case TCC_OPTION_U:
        tcc_undefine_symbol(s, optarg);
        break;
      case TCC_OPTION_L:
        tcc_add_library_path(s, optarg);
        break;
      case TCC_OPTION_B:
        /* 设置 tcc 工具路径（主要用于 tcc 开发） */
        tcc_set_lib_path(s, optarg);
        break;
      case TCC_OPTION_l:
        args_parser_add_file(s, optarg, AFF_TYPE_LIB);
        s->nb_libraries++;
        break;
      case TCC_OPTION_pthread:
        parse_option_D(s, "_REENTRANT");
        s->option_pthread = 1;
        break;
      case TCC_OPTION_bench:
        s->do_bench = 1;
        break;
#ifdef CONFIG_TCC_BACKTRACE
      case TCC_OPTION_bt:
        tcc_set_num_callers(atoi(optarg));
        break;
#endif
#ifdef CONFIG_TCC_BCHECK
      case TCC_OPTION_b:
        s->do_bounds_check = 1;
        s->do_debug = 1;
        break;
#endif
      case TCC_OPTION_g:
        s->do_debug = 1;
        break;
      case TCC_OPTION_c:
        x = TCC_OUTPUT_OBJ;
      set_output_type:
        if (s->output_type)
          tcc_warning("-%s: overriding compiler action already specified",
                      popt->name);
        s->output_type = x;
        break;
      case TCC_OPTION_d:
        if (*optarg == 'D')
          s->dflag = 3;
        else if (*optarg == 'M')
          s->dflag = 7;
        else if (*optarg == 't')
          s->dflag = 16;
        else if (isnum(*optarg))
          g_debug = atoi(optarg);
        else
          goto unsupported_option;
        break;
      case TCC_OPTION_static:
        s->static_link = 1;
        break;
      case TCC_OPTION_std:
        /* 静默忽略，目前的一个目的是：
           允许把 tcc 当作 "make test" 的参考编译器 */
        break;
      case TCC_OPTION_shared:
        x = TCC_OUTPUT_DLL;
        goto set_output_type;
      case TCC_OPTION_soname:
        s->soname = tcc_strdup(optarg);
        break;
      case TCC_OPTION_o:
        if (s->outfile) {
          tcc_warning("multiple -o option");
          tcc_free(s->outfile);
        }
        s->outfile = tcc_strdup(optarg);
        break;
      case TCC_OPTION_r:
        /* 生成一个合并多个输出文件的 .o */
        s->option_r = 1;
        x = TCC_OUTPUT_OBJ;
        goto set_output_type;
      case TCC_OPTION_isystem:
        tcc_add_sysinclude_path(s, optarg);
        break;
      case TCC_OPTION_include:
        dynarray_add(&s->cmd_include_files, &s->nb_cmd_include_files,
                     tcc_strdup(optarg));
        break;
      case TCC_OPTION_nostdinc:
        s->nostdinc = 1;
        break;
      case TCC_OPTION_nostdlib:
        s->nostdlib = 1;
        break;
      case TCC_OPTION_run:
#ifndef TCC_IS_NATIVE
        tcc_error("-run is not available in a cross compiler");
#endif
        run = optarg;
        x = TCC_OUTPUT_MEMORY;
        goto set_output_type;
      case TCC_OPTION_v:
        do ++s->verbose;
        while (*optarg++ == 'v');
        ++noaction;
        break;
      case TCC_OPTION_f:
        if (set_flag(s, options_f, optarg) < 0) goto unsupported_option;
        break;
      case TCC_OPTION_m:
        if (set_flag(s, options_m, optarg) < 0) {
          if (x = atoi(optarg), x != 32 && x != 64) goto unsupported_option;
          if (PTR_SIZE != x / 8) return x;
          ++noaction;
        }
        break;
      case TCC_OPTION_W:
        if (set_flag(s, options_W, optarg) < 0) goto unsupported_option;
        break;
      case TCC_OPTION_w:
        s->warn_none = 1;
        break;
      case TCC_OPTION_rdynamic:
        s->rdynamic = 1;
        break;
      case TCC_OPTION_Wl:
        if (linker_arg.size) --linker_arg.size, cstr_ccat(&linker_arg, ',');
        cstr_cat(&linker_arg, optarg, 0);
        if (tcc_set_linker(s, linker_arg.data)) cstr_free(&linker_arg);
        break;
      case TCC_OPTION_Wp:
        r = optarg;
        goto reparse;
      case TCC_OPTION_E:
        x = TCC_OUTPUT_PREPROCESS;
        goto set_output_type;
      case TCC_OPTION_P:
        s->Pflag = atoi(optarg) + 1;
        break;
      case TCC_OPTION_MD:
        s->gen_deps = 1;
        break;
      case TCC_OPTION_MF:
        s->deps_outfile = tcc_strdup(optarg);
        break;
      case TCC_OPTION_dumpversion:
        printf("%s\n", TCC_VERSION);
        exit(0);
        break;
      case TCC_OPTION_x:
        if (*optarg == 'c')
          s->filetype = AFF_TYPE_C;
        else if (*optarg == 'a')
          s->filetype = AFF_TYPE_ASMPP;
        else if (*optarg == 'n')
          s->filetype = AFF_TYPE_NONE;
        else
          tcc_warning("unsupported language '%s'", optarg);
        break;
      case TCC_OPTION_syntax_check:
        /* 仅词法/语法检查：容许未定义符号、类型错误与缺少 main */
        x = TCC_OUTPUT_SYNTAX;
        goto set_output_type;
      case TCC_OPTION_sysroot:
        /* 链接期 sysroot：crt/lib/头文件均在其下查找 */
        tcc_free(s->sysroot);
        s->sysroot = tcc_strdup(optarg);
        break;
      case TCC_OPTION_O:
        last_o = atoi(optarg);
        break;
      case TCC_OPTION_print_search_dirs:
        x = OPT_PRINT_DIRS;
        goto extra_action;
      case TCC_OPTION_ar:
        x = OPT_AR;
      extra_action:
        arg_start = optind - 1;
        if (arg_start != noaction) tcc_error("cannot parse %s here", r);
        tool = x;
        break;
      case TCC_OPTION_traditional:
      case TCC_OPTION_pedantic:
      case TCC_OPTION_pipe:
      case TCC_OPTION_s:
        /* 忽略 */
        break;
      default:
      unsupported_option:
        if (s->warn_unsupported) tcc_warning("unsupported option '%s'", r);
        break;
    }
  }
  if (last_o > 0) tcc_define_symbol(s, "__OPTIMIZE__", NULL);
  if (linker_arg.size) {
    r = linker_arg.data;
    goto arg_err;
  }
  *pargc = argc - arg_start;
  *pargv = argv + arg_start;
  if (tool) return tool;
  if (optind != noaction) return 0;
  if (s->verbose == 2) return OPT_PRINT_DIRS;
  if (s->verbose) return OPT_V;
  return OPT_HELP;
}

LIBTCCAPI void tcc_set_options(TCCState* s, const char* r) {
  char** argv = NULL;
  int argc = 0;
  args_parser_make_argv(r, &argc, &argv);
  tcc_parse_args(s, &argc, &argv, 0);
  dynarray_reset(&argv, &argc);
}

PUB_FUNC void tcc_print_stats(TCCState* s, unsigned total_time) {
  if (total_time < 1) total_time = 1;
  if (total_bytes < 1) total_bytes = 1;
  fprintf(stderr,
          "* %d idents, %d lines, %d bytes\n"
          "* %0.3f s, %u lines/s, %0.1f MB/s\n",
          tok_ident - TOK_IDENT, total_lines, total_bytes,
          (double)total_time / 1000, (unsigned)total_lines * 1000 / total_time,
          (double)total_bytes / 1000 / total_time);
#ifdef MEM_DEBUG
  fprintf(stderr, "* %d bytes memory used\n", mem_max_size);
#endif
}
