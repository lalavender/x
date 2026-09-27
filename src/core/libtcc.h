/*
 * libtcc.h —— Tiny C Compiler 的嵌入式（libtcc）公共 API
 *
 * 通过本头文件，宿主程序可以把 TCC 当作库使用：创建编译上下文、
 * 添加头文件/库搜索路径、定义宏、编译源文件或字符串、设置输出类型，
 * 重定位到内存并调用生成的函数。
 *
 * 典型用法：
 *   TCCState *s = tcc_new();
 *   tcc_set_output_type(s, TCC_OUTPUT_MEMORY);
 *   tcc_add_file(s, "foo.c");
 *   tcc_relocate(s, TCC_RELOCATE_AUTO);
 *   fn = tcc_get_symbol(s, "main");
 *   tcc_delete(s);
 */

#ifndef LIBTCC_H
#define LIBTCC_H

#ifndef LIBTCCAPI
#define LIBTCCAPI
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* TCCState 在 tcc.h 中完整定义，此处仅作前置声明，隐藏内部实现 */
struct TCCState;

typedef struct TCCState TCCState;

/* 创建一个新的 TCC 编译上下文 */
LIBTCCAPI TCCState *tcc_new(void);

/* 释放一个 TCC 编译上下文 */
LIBTCCAPI void tcc_delete(TCCState *s);

/* 运行时设置 CONFIG_TCCDIR（库/头文件安装目录） */
LIBTCCAPI void tcc_set_lib_path(TCCState *s, const char *path);

/* 设置错误/警告的显示回调函数 */
LIBTCCAPI void tcc_set_error_func(TCCState *s, void *error_opaque,
                                  void (*error_func)(void *opaque,
                                                     const char *msg));

/* 像命令行一样设置选项（可多次调用） */
LIBTCCAPI void tcc_set_options(TCCState *s, const char *str);

/*****************************/
/* 预处理器 */

/* 添加头文件搜索路径 */
LIBTCCAPI int tcc_add_include_path(TCCState *s, const char *pathname);

/* 添加系统头文件搜索路径 */
LIBTCCAPI int tcc_add_sysinclude_path(TCCState *s, const char *pathname);

/* 定义预处理符号 'sym'，可选地提供取值 */
LIBTCCAPI void tcc_define_symbol(TCCState *s, const char *sym,
                                 const char *value);

/* 取消预处理符号 'sym' 的定义 */
LIBTCCAPI void tcc_undefine_symbol(TCCState *s, const char *sym);

/*****************************/
/* 编译 */

/* 添加一个文件（C 文件、动态库、目标文件、静态库、链接脚本）。
   出错返回 -1。 */
LIBTCCAPI int tcc_add_file(TCCState *s, const char *filename);

/* 编译一段包含 C 源码的字符串。出错返回 -1。 */
LIBTCCAPI int tcc_compile_string(TCCState *s, const char *buf);

/*****************************/
/* 链接命令 */

/* 设置输出类型。必须在任何编译之前调用 */
LIBTCCAPI int tcc_set_output_type(TCCState *s, int output_type);
#define TCC_OUTPUT_MEMORY 1     /* 输出到内存中直接运行（默认） */
#define TCC_OUTPUT_EXE 2        /* 可执行文件 */
#define TCC_OUTPUT_DLL 3        /* 动态库 */
#define TCC_OUTPUT_OBJ 4        /* 目标文件 */
#define TCC_OUTPUT_PREPROCESS 5 /* 仅预处理（内部使用） */
#define TCC_OUTPUT_SYNTAX 6     /* 仅词法/语法检查（--syntax-check，不生成代码） */

/* 等价于命令行 -Lpath 选项 */
LIBTCCAPI int tcc_add_library_path(TCCState *s, const char *pathname);

/* 库名与 '-l' 选项的参数相同 */
LIBTCCAPI int tcc_add_library(TCCState *s, const char *libraryname);

/* 向编译后的程序添加一个符号（直接把地址传给编译产物） */
LIBTCCAPI int tcc_add_symbol(TCCState *s, const char *name, const void *val);

/* 输出可执行文件、库或目标文件。
   在此之前不要调用 tcc_relocate()。 */
LIBTCCAPI int tcc_output_file(TCCState *s, const char *filename);

/* 链接并运行 main() 函数，返回其返回值。
   在此之前不要调用 tcc_relocate()。 */
LIBTCCAPI int tcc_run(TCCState *s, int argc, char **argv);

/* 执行所有重定位（在使用 tcc_get_symbol() 之前必须调用） */
LIBTCCAPI int tcc_relocate(TCCState *s1, void *ptr);
/* 'ptr' 的可能取值：
   - TCC_RELOCATE_AUTO : 在内部自动分配并管理内存
   - NULL              : 返回下一步所需的内存大小
   - 内存地址          : 把代码复制到调用者提供的内存中
   出错返回 -1。 */
#define TCC_RELOCATE_AUTO (void *)1

/* 返回符号的值，找不到返回 NULL */
LIBTCCAPI void *tcc_get_symbol(TCCState *s, const char *name);

#ifdef __cplusplus
}
#endif

#endif
