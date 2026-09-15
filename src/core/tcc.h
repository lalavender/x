/*
 *  TCC - Tiny C Compiler（微型 C 编译器）
 *
 *  Copyright (c) 2001-2004 Fabrice Bellard
 *
 * 本库为自由软件；你可以遵照自由软件基金会发布的 GNU 宽通用公共许可证
 * （GNU Lesser General Public License）的条款重新分发和/或修改它，
 * 无论是许可证的第 2 版，还是（由你选择的）任何更新的版本。
 *
 * 分发本库是希望它有用，但不提供任何担保；
 * 甚至不提供对适销性或特定用途适用性的默示担保。
 * 详见 GNU 宽通用公共许可证。
 *
 * 你应当已经随本库收到一份 GNU 宽通用公共许可证的副本；
 * 如果没有，请写信给自由软件基金会：
 * 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 */

/*
 * 本文件是 TCC 的“总头文件”，汇集了几乎所有内部数据结构的定义、
 * 全局变量声明以及各编译阶段的函数声明。
 *
 * 阅读建议（对照编译流水线）：
 *   1. 配置与平台适配（路径、目标选择）
 *   2. 词法/语义相关结构：TokenSym、CString、CValue、CType、SValue、Sym
 *   3. 段（Section）与 ELF 输出相关结构
 *   4. 预处理/文件读取结构：BufferedFile、TokenString、CachedInclude
 *   5. 编译器状态总账本：TCCState
 *   6. 类型编码（VT_xxx）与记号编码（TOK_xxx）
 *   7. 各 .c 文件的函数声明
 */

#ifndef _TCC_H
#define _TCC_H

#define _GNU_SOURCE
#include "config.h"

#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
#include <math.h>
#include <fcntl.h>
#include <setjmp.h>
#include <time.h>

#ifndef _WIN32
# include <unistd.h>
# include <sys/time.h>
# ifndef CONFIG_TCC_STATIC
#  include <dlfcn.h>
# endif
/* XXX：在非 ISOC99 环境下需要显式声明这两个函数才能使用 */
extern float strtof (const char *__nptr, char **__endptr);
extern long double strtold (const char *__nptr, char **__endptr);
#endif

#ifdef _WIN32
# include <windows.h>
# include <io.h> /* open、close 等 */
# include <direct.h> /* getcwd */
# ifdef __GNUC__
#  include <stdint.h>
# endif
# define inline __inline
# define snprintf _snprintf
# define vsnprintf _vsnprintf
# ifndef __GNUC__
#  define strtold (long double)strtod
#  define strtof (float)strtod
#  define strtoll _strtoi64
#  define strtoull _strtoui64
# endif
# ifdef LIBTCC_AS_DLL
#  define LIBTCCAPI __declspec(dllexport)
#  define PUB_FUNC LIBTCCAPI
# endif
# define inp next_inp /* inp 在 msvc/mingw 中是内建标识符，故改名 */
# ifdef _MSC_VER
#  pragma warning (disable : 4244)  // 从 uint64_t 到 int 的转换可能丢失数据
#  pragma warning (disable : 4267)  // 从 size_t 到 int 的转换可能丢失数据
#  pragma warning (disable : 4996)  // 该 POSIX 名称已废弃，应改用 ISO C/C++ 兼容名称
#  pragma warning (disable : 4018)  // 有符号/无符号不匹配
#  pragma warning (disable : 4146)  // 对无符号类型使用一元负号，结果仍为无符号
#  define ssize_t intptr_t
# endif
# undef CONFIG_TCC_STATIC
#endif

#ifndef O_BINARY
# define O_BINARY 0
#endif

#ifndef offsetof
#define offsetof(type, field) ((size_t) &((type *)0)->field)
#endif

#ifndef countof
#define countof(tab) (sizeof(tab) / sizeof((tab)[0]))
#endif

#ifdef _MSC_VER
# define NORETURN __declspec(noreturn)
# define ALIGNED(x) __declspec(align(x))
#else
# define NORETURN __attribute__((noreturn))
# define ALIGNED(x) __attribute__((aligned(x)))
#endif

#ifdef _WIN32
# define IS_DIRSEP(c) (c == '/' || c == '\\')
# define IS_ABSPATH(p) (IS_DIRSEP(p[0]) || (p[0] && p[1] == ':' && IS_DIRSEP(p[2])))
# define PATHCMP stricmp
# define PATHSEP ";"
#else
# define IS_DIRSEP(c) (c == '/')
# define IS_ABSPATH(p) IS_DIRSEP(p[0])
# define PATHCMP strcmp
# define PATHSEP ":"
#endif

/* -------------------------------------------- */

/* 语法分析器调试开关 */
/* #define PARSE_DEBUG */
/* 预处理器调试开关 */
/* #define PP_DEBUG */
/* 头文件包含调试开关 */
/* #define INC_DEBUG */
/* 内存泄漏调试开关 */
/* #define MEM_DEBUG */
/* 汇编器调试开关 */
/* #define ASM_DEBUG */

/* 目标选择：本分支只保留 ARMv8（AArch64）后端 */
#define TCC_TARGET_ARM64

/* 只有本机（原生）编译器才支持 -run */
#if !defined _WIN32
# if defined __aarch64__
#  define TCC_IS_NATIVE
# endif
#endif

#if defined TCC_IS_NATIVE && !defined CONFIG_TCCBOOT
# define CONFIG_TCC_BACKTRACE
#endif

/* ------------ 路径配置 ------------ */

#ifndef CONFIG_SYSROOT
# define CONFIG_SYSROOT ""
#endif
#ifndef CONFIG_TCCDIR
# define CONFIG_TCCDIR "/usr/local/lib/tcc"
#endif
#ifndef CONFIG_LDDIR
# define CONFIG_LDDIR "lib"
#endif
#ifdef CONFIG_TRIPLET
# define USE_TRIPLET(s) s "/" CONFIG_TRIPLET
# define ALSO_TRIPLET(s) USE_TRIPLET(s) ":" s
#else
# define USE_TRIPLET(s) s
# define ALSO_TRIPLET(s) s
#endif

/* 用于查找 crt1.o、crti.o、crtn.o 的路径 */
#ifndef CONFIG_TCC_CRTPREFIX
# define CONFIG_TCC_CRTPREFIX USE_TRIPLET(CONFIG_SYSROOT "/usr/" CONFIG_LDDIR)
#endif

/* 下文中的 {B} 会被 CONFIG_TCCDIR（或 -B 选项）替换 */

/* 系统头文件搜索路径 */
#ifndef CONFIG_TCC_SYSINCLUDEPATHS
#  define CONFIG_TCC_SYSINCLUDEPATHS \
        "{B}/include" \
    ":" ALSO_TRIPLET(CONFIG_SYSROOT "/usr/local/include") \
    ":" ALSO_TRIPLET(CONFIG_SYSROOT "/usr/include")
#endif

/* 库文件搜索路径 */
#ifndef CONFIG_TCC_LIBPATHS
#  define CONFIG_TCC_LIBPATHS \
        ALSO_TRIPLET(CONFIG_SYSROOT "/usr/" CONFIG_LDDIR) \
    ":" ALSO_TRIPLET(CONFIG_SYSROOT "/" CONFIG_LDDIR) \
    ":" ALSO_TRIPLET(CONFIG_SYSROOT "/usr/local/" CONFIG_LDDIR)
#endif

/* ELF 解释器（动态链接器）的名称 */
#ifndef CONFIG_TCC_ELFINTERP
# if defined __FreeBSD__
#  define CONFIG_TCC_ELFINTERP "/libexec/ld-elf.so.1"
# elif defined __FreeBSD_kernel__
#  define CONFIG_TCC_ELFINTERP "/lib/ld.so.1"
# elif defined __DragonFly__
#  define CONFIG_TCC_ELFINTERP "/usr/libexec/ld-elf.so.2"
# elif defined __NetBSD__
#  define CONFIG_TCC_ELFINTERP "/usr/libexec/ld.elf_so"
# elif defined __GNU__
#  define CONFIG_TCC_ELFINTERP "/lib/ld.so"
# elif defined(TCC_UCLIBC)
#  define CONFIG_TCC_ELFINTERP "/lib/ld-uClibc.so.0"
# elif defined(TCC_MUSL)
#  define CONFIG_TCC_ELFINTERP "/lib/ld-musl-aarch64.so.1"
# else
#  define CONFIG_TCC_ELFINTERP "/lib/ld-linux-aarch64.so.1"
# endif
#endif

/* elf_interp 变量定义在 *-gen.c 中 */
#ifdef CONFIG_TCC_ELFINTERP
# define DEFAULT_ELFINTERP(s) CONFIG_TCC_ELFINTERP
#else
# define DEFAULT_ELFINTERP(s) default_elfinterp(s)
#endif

/* （与目标相关的）libtcc1.a 文件名 */
#ifndef TCC_LIBTCC1
# define TCC_LIBTCC1 "libtcc1.a"
#endif

/* 当定义 CONFIG_USE_LIBGCC 时，用它替代 libtcc1.a */
#if defined CONFIG_USE_LIBGCC && !defined TCC_LIBGCC
#define TCC_LIBGCC USE_TRIPLET(CONFIG_SYSROOT "/" CONFIG_LDDIR) "/libgcc_s.so.1"
#endif

/* -------------------------------------------- */

#include "libtcc.h"
#include "elf.h"
#include "stab.h"

/* -------------------------------------------- */

#ifndef PUB_FUNC /* tcc.c 使用但未在 libtcc.h 中声明的函数 */
# define PUB_FUNC
#endif

#ifndef ONE_SOURCE
# define ONE_SOURCE 1
#endif

#if ONE_SOURCE
#define ST_INLN static inline
#define ST_FUNC static
#define ST_DATA static
#else
#define ST_INLN
#define ST_FUNC
#define ST_DATA extern
#endif

#ifdef TCC_PROFILE /* 对所有函数进行性能分析 */
# define static
#endif

/* -------------------------------------------- */
/* 包含与目标相关的定义 */

#define TARGET_DEFS_ONLY
#ifdef TCC_TARGET_ARM64
# include "arm64-gen.c"
# include "arm64-link.c"
#endif
#undef TARGET_DEFS_ONLY

/* -------------------------------------------- */

/* 根据指针宽度选择 32/64 位 ELF 结构及宏 */
#if PTR_SIZE == 8
# define ELFCLASSW ELFCLASS64
# define ElfW(type) Elf##64##_##type
# define ELFW(type) ELF##64##_##type
# define ElfW_Rel ElfW(Rela)
# define SHT_RELX SHT_RELA
# define REL_SECTION_FMT ".rela%s"
#else
# define ELFCLASSW ELFCLASS32
# define ElfW(type) Elf##32##_##type
# define ELFW(type) ELF##32##_##type
# define ElfW_Rel ElfW(Rel)
# define SHT_RELX SHT_REL
# define REL_SECTION_FMT ".rel%s"
#endif
/* 目标地址类型 */
#define addr_t ElfW(Addr)
#define ElfSym ElfW(Sym)

#if PTR_SIZE == 8
# define LONG_SIZE 8
#else
# define LONG_SIZE 4
#endif

/* -------------------------------------------- */

#define INCLUDE_STACK_SIZE  32   /* 头文件包含栈的深度 */
#define IFDEF_STACK_SIZE    64   /* #ifdef 嵌套栈的深度 */
#define VSTACK_SIZE         256  /* 值栈（表达式求值栈）容量 */
#define STRING_MAX_SIZE     1024 /* 字符串记号缓冲区上限 */
#define TOKSTR_MAX_SIZE     256  /* 记号串缓冲区上限 */
#define PACK_STACK_SIZE     8    /* #pragma pack 栈的深度 */

#define TOK_HASH_SIZE       16384 /* 记号哈希表大小，必须是 2 的幂 */
#define TOK_ALLOC_INCR      512  /* 记号批量分配增量，必须是 2 的幂 */
#define TOK_MAX_SIZE        4 /* 以 int 为单位存储字符串时的记号最大尺寸 */

/*
 * TokenSym —— 记号符号（token symbol）
 *
 * 每个出现过的标识符/关键字/字符串在编译器中只保存一份字符串，
 * 用一个非负整数 tok（>= 256）作为它的“身份编号”，后续所有操作都用
 * 这个整数代替原字符串，避免反复比较字符串。
 *
 * 由 tccpp.c 的 tok_alloc() 创建：先在 TOK_HASH_SIZE 个桶的哈希表
 * （hash_ident，桶内用 hash_next 串链）中查找，找不到才新建；
 * 记号编号由全局计数器 tok_ident 递增分配，同时登记到
 * table_ident[tok - TOK_IDENT]，因此由编号可 O(1) 反查字符串
 * （get_tok_str()）。这些结构在一次编译中只增不减，直到
 * tccpp_delete() 才统一释放。
 *
 * sym_* 四个指针是四个独立的命名空间（由同一个 TokenSym 复用）：
 *   - sym_define     ：同名宏定义（预处理阶段）
 *   - sym_label      ：同名标号（汇编/标签）
 *   - sym_struct     ：同名结构体/联合体/枚举标签
 *   - sym_identifier ：同名普通标识符（变量、函数等）
 */
typedef struct TokenSym {
    struct TokenSym *hash_next;   /* 哈希桶中的下一个记号 */
    struct Sym *sym_define;       /* 指向宏定义的直接指针 */
    struct Sym *sym_label;        /* 指向标号的直接指针 */
    struct Sym *sym_struct;       /* 指向结构体的直接指针 */
    struct Sym *sym_identifier;   /* 指向标识符的直接指针 */
    int tok;                      /* 记号编号 */
    int len;                      /* 字符串长度 */
    char str[1];                  /* 字符串内容（柔性数组） */
} TokenSym;

typedef int nwchar_t;             /* 宽字符类型（非 Windows 下为 int） */

/*
 * CString —— 可增长字符串缓冲区
 *
 * data 指向实际数据：普通字符串时为 char*，宽字符串时为 nwchar_t*。
 */
typedef struct CString {
    int size;            /* 当前字节数 */
    void *data;          /* 'char *' 或 'nwchar_t *' */
    int size_allocated;  /* 已分配的字节数 */
} CString;

/*
 * CType —— C 类型描述
 *
 * t   是类型编码（由 VT_xxx 位标志组合而成，见下文“类型”一节）：
 *     低 4 位（VT_BTYPE）是基本类型（VT_INT / VT_PTR / VT_STRUCT / VT_FLOAT ...），
 *     其余位是修饰信息（VT_UNSIGNED、VT_ARRAY、VT_BITFIELD、VT_STATIC 等）；
 *     位域还把位偏移与位宽编码进高位（见 VT_STRUCT_SHIFT、BIT_POS、BIT_SIZE）。
 * ref 指向类型引用符号：
 *   - 结构体/联合体/枚举：指向定义它们的 Sym（该 Sym 的 c 是大小、r 是对齐，
 *     字段链挂在它的 next 上）
 *   - 数组：指向一个 Sym，其 type 是元素类型，c 是元素个数（-1 表示不完整数组）
 *   - 函数：指向一个 Sym，其 type 是返回类型，next 链是参数表
 *   - 指针：指向被引用类型的 Sym
 * 因此 CType 本身很小，复杂类型信息都挂在 Sym 上，便于共享与伪装（如把数组
 * 转成元素指针只需改 t 的位标志）。
 */
typedef struct CType {
    int t;                /* 类型编码 */
    struct Sym *ref;      /* 类型引用 */
} CType;

/*
 * CValue —— 常量的值（联合体）
 *
 * 根据当前类型从对应的成员读取常量值；各成员共用同一块存储，实际写入哪个
 * 成员由常量记号（TOK_CINT / TOK_CDOUBLE / TOK_STR / ...）决定。
 * tab 是按 int 逐字访问这块存储的视图，用于把常量值原样复制进记号串
 * （见 tccpp.c 的 get_tok_str()），从而不必按具体类型逐一分派。
 */
typedef union CValue {
    long double ld;       /* long double 常量 */
    double d;             /* double 常量 */
    float f;              /* float 常量 */
    uint64_t i;           /* 整型常量 */
    struct {
        int size;         /* 字符串/结构体初始化数据的字节数 */
        const void *data; /* 数据指针 */
    } str;
    int tab[LDOUBLE_SIZE/4]; /* 与 long double 对齐的原始整数视图 */
} CValue;

/*
 * SValue —— 值栈（value stack）上的一个值
 *
 * 表达式求值采用“值栈”模型：每个中间结果用 SValue 表示。
 * 一个值可能位于寄存器中，也可能位于内存（栈帧）中，或者是一个常量。
 *
 * 值栈本体是全局数组 vstack（即 __vstack + 1，下标 0 作为哨兵，方便越界检测），
 * vtop 指向栈顶元素，pvtop 记录“当前表达式开始处”的栈顶位置：
 * 表达式求值结束后若 vtop != pvtop，说明有值未弹出，check_vstack() 会报
 * 内部编译器错误（值栈泄漏）。
 * 使用流程：入栈用 vpushi()/vpushsym() 等；取操作数时用 gv() 把它装入寄存器
 * （需要时生成 load 指令，或把其它寄存器换出到栈上）；写回内存用 vstore()。
 */
typedef struct SValue {
    CType type;      /* 该值的类型 */
    unsigned short r;      /* 寄存器编号 + 标志位（低 6 位为寄存器，高位为 VT_xxx 标志） */
    unsigned short r2;     /* 第二个寄存器，用于 'long long' 类型；
                              若不使用则置为 VT_CONST */
    CValue c;              /* 当 r 为 VT_CONST 时，这里是常量值 */
    struct Sym *sym;       /* 符号：当 (VT_SYM | VT_CONST) 时有效，
                              或表示 unary() 对标识符的求值结果 */
} SValue;

/*
 * SymAttr —— 符号属性（紧凑位域）
 */
struct SymAttr {
    unsigned short
    aligned     : 5, /* 对齐要求，log2+1（0 表示未指定） */
    packed      : 1, /* 是否为 packed（取消对齐填充） */
    weak        : 1, /* 是否为弱符号 */
    visibility  : 2, /* 可见性（STV_xxx） */
    dllexport   : 1, /* 是否 dllexport（保留字段） */
    dllimport   : 1, /* 是否 dllimport（保留字段） */
    unused      : 5;
};

/*
 * FuncAttr —— 函数属性，或在解析阶段充当临时属性
 */
struct FuncAttr {
    unsigned
    func_call   : 3, /* 调用约定（0..5），见下文 FUNC_xxx */
    func_type   : 2, /* FUNC_OLD / FUNC_NEW / FUNC_ELLIPSIS */
    func_args   : 8; /* PE __stdcall 参数个数（保留字段） */
};

/*
 * AttributeDef —— GNUC 扩展属性定义（__attribute__ 解析结果）
 */
typedef struct AttributeDef {
    struct SymAttr a;      /* 符号级属性（aligned、packed、weak 等） */
    struct FuncAttr f;     /* 函数级属性（调用约定、参数等） */
    struct Section *section; /* __attribute__((section(...))) 指定的段 */
    int alias_target;      /* alias 目标的记号 */
    int asm_label;         /* 关联的汇编标签 */
    char attr_mode;        /* __attribute__((__mode__(...))) 指定的模式 */
} AttributeDef;

/*
 * Sym —— 符号（symbol）
 *
 * Sym 是 TCC 中最重要的结构：变量、函数、类型、宏、标号等都表示为 Sym。
 * 符号通过 v（记号编号）标识，并链接成若干栈/链：
 *   - next/prev        ：同一作用域内的兄弟符号链
 *   - prev_tok         ：同一记号的所有符号链
 *   - struct/union 成员：next 指向下一个字段
 *
 * 通过 v 的高位区分不同命名空间（见 SYM_STRUCT / SYM_FIELD / SYM_FIRST_ANOM）：
 * 同一个 TokenSym 可以同时挂有宏、标号、结构体标签和普通标识符四个不同的 Sym，
 * 它们互不干扰。
 *
 * 内存管理：Sym 从不单独 malloc，而是由 tccgen.c 的 sym_malloc() 按
 * SYM_POOL_NB 个一块从 sym_pools 成批分配，释放的符号挂在 sym_free_first
 * 空闲链上循环复用，因此符号的创建/销毁开销极低。
 * 作用域由符号栈体现：全局符号在 global_stack、局部符号在 local_stack、
 * 宏在 define_stack；离开作用域时 sym_pop() 整段弹出即可（局部符号无须逐个回收）。
 *
 * 字段用法随符号种类而异：
 *   - 变量/函数：type 是类型，c 是 ELF 符号表下标（输出阶段使用），r 是寄存器/存储信息
 *   - 结构体/联合体：type.ref 指向字段链，c 是大小，r 是对齐
 *   - 枚举：若为 IS_ENUM_VAL，enum_val 是枚举常量值
 *   - 宏：d 指向宏体记号流，type.t 为 MACRO_OBJ / MACRO_FUNC
 *   - 标号：jnext 串联待回填的跳转，r 为 LABEL_xxx 状态
 */
typedef struct Sym {
    int v; /* 符号记号 */
    unsigned short r; /* 关联寄存器，或 VT_CONST/VT_LOCAL 及 LVAL 类型 */
    struct SymAttr a; /* 符号属性 */
    union {
        struct {
            int c; /* 关联数值，或 ELF 符号表下标 */
            union {
                int sym_scope; /* 局部符号的作用域层级 */
                int jnext; /* 下一个跳转标号 */
                struct FuncAttr f; /* 函数属性 */
                int auxtype; /* 位域访问类型 */
            };
        };
        long long enum_val; /* 若为 IS_ENUM_VAL，则为枚举常量值 */
        int *d; /* 宏定义：记号流 */
    };
    CType type; /* 关联类型 */
    union {
        struct Sym *next; /* 下一个相关符号（字段、匿名符号等） */
        int asm_label; /* 关联的汇编标签 */
    };
    struct Sym *prev; /* 符号栈中的前一个符号 */
    struct Sym *prev_tok; /* 同一记号的上一个符号 */
} Sym;

/*
 * Section —— 段（section）
 *
 * 编译器先把代码/数据累积到内存中的段，最后再统一写出为目标文件的
 * ELF 段。data 是段的字节缓冲区，随写入不断增长。
 *
 * 典型用法：new_section() 创建并登记段 -> section_ptr_add()/section_add()
 * 增长缓冲区并取得可写指针（容量不足时由 section_realloc() 扩容）->
 * 输出阶段由 tccelf.c 补齐 sh_offset/sh_size 后写入文件。
 *
 * 两类段：普通段登记在 TCCState::sections 中并分配 sh_num（ELF 段号）；
 * 带 SHF_PRIVATE 标志的内部段只登记在 TCCState::priv_sections 中，不写出到
 * 目标文件（例如调试与边界检查用的临时段）。
 *
 * link/reloc/hash 等指针描述段之间的关联（如重定位段指向被重定位的段、
 * 符号表段指向配套的字符串表段与哈希表段），主要在输出与链接阶段建立和使用。
 */
typedef struct Section {
    unsigned long data_offset; /* 当前数据偏移 */
    unsigned char *data;       /* 段数据 */
    unsigned long data_allocated; /* 已分配的容量（用于 realloc） */
    int sh_name;             /* ELF 段名（仅在输出时使用） */
    int sh_num;              /* ELF 段号 */
    int sh_type;             /* ELF 段类型（SHT_xxx） */
    int sh_flags;            /* ELF 段标志（SHF_xxx） */
    int sh_info;             /* ELF 段的额外信息 */
    int sh_addralign;        /* ELF 段对齐 */
    int sh_entsize;          /* 段内条目大小 */
    unsigned long sh_size;   /* 段大小（仅在输出时使用） */
    addr_t sh_addr;          /* 段被重定位后的地址 */
    unsigned long sh_offset; /* 文件偏移 */
    int nb_hashed_syms;      /* 用于调整哈希表大小 */
    struct Section *link;    /* 链接到的另一个段 */
    struct Section *reloc;   /* 对应的重定位段（若有） */
    struct Section *hash;    /* 符号哈希表段 */
    struct Section *prev;    /* 段栈中的前一个段 */
    char name[1];           /* 段名（柔性数组） */
} Section;

/*
 * DLLReference —— 已加载的动态库引用
 */
typedef struct DLLReference {
    int level;        /* 引用层级（0 表示用户直接请求） */
    void *handle;     /* dlopen 返回的句柄 */
    char name[1];     /* 库名 */
} DLLReference;

/* -------------------------------------------------- */

/* v 的高位用于区分不同的符号命名空间 */
#define SYM_STRUCT     0x40000000 /* struct/union/enum 符号空间 */
#define SYM_FIELD      0x20000000 /* struct/union 字段符号空间 */
#define SYM_FIRST_ANOM 0x10000000 /* 第一个匿名符号 */

/* 存放在 'Sym->f.func_type' 中 */
#define FUNC_NEW       1 /* ANSI 函数原型 */
#define FUNC_OLD       2 /* 旧式函数 */
#define FUNC_ELLIPSIS  3 /* 带 ... 的 ANSI 函数原型 */

/* 存放在 'Sym->f.func_call' 中 */
#define FUNC_CDECL     0 /* 标准 C 调用约定 */
#define FUNC_STDCALL   1 /* pascal 调用约定 */
#define FUNC_FASTCALL1 2 /* 第一个参数放入 %eax */
#define FUNC_FASTCALL2 3 /* 前两个参数放入 %eax、%edx */
#define FUNC_FASTCALL3 4 /* 前三个参数放入 %eax、%edx、%ecx */
#define FUNC_FASTCALLW 5 /* 第一个参数放入 %ecx、%edx */

/* 'Sym.t' 用于宏 */
#define MACRO_OBJ      0 /* 对象式宏 */
#define MACRO_FUNC     1 /* 函数式宏 */

/* 'Sym.r' 用于 C 标号 */
#define LABEL_DEFINED  0 /* 标号已定义 */
#define LABEL_FORWARD  1 /* 标号前向定义 */
#define LABEL_DECLARED 2 /* 标号已声明但从未使用 */

/* type_decl() 的类型 */
#define TYPE_ABSTRACT  1 /* 无变量名的类型 */
#define TYPE_DIRECT    2 /* 带变量的类型 */

#define IO_BUF_SIZE 8192

/*
 * BufferedFile —— 带缓冲的输入文件
 *
 * 每打开一个源文件（或 <string>/<define> 等虚拟文件）就创建一个本结构，
 * 多个文件通过 prev 串成栈，从而支持 #include 嵌套。
 * buffer 之后紧跟实际读入的字节（柔性数组）。
 */
typedef struct BufferedFile {
    uint8_t *buf_ptr;        /* 当前读取位置 */
    uint8_t *buf_end;        /* 缓冲区结束位置 */
    int fd;                  /* 文件描述符 */
    struct BufferedFile *prev; /* 上一层文件（#include 栈） */
    int line_num;    /* 当前行号（放在这里便于处理） */
    int line_ref;    /* tcc -E：上一次输出的行号 */
    int ifndef_macro;  /* #ifndef MACRO / #endif 的配对搜索状态 */
    int ifndef_macro_saved; /* 保存的 ifndef_macro */
    int *ifdef_stack_ptr; /* 文件开始处的 ifdef_stack 指针 */
    int include_next_index; /* 下一个搜索路径下标 */
    char filename[1024];    /* 文件名 */
    char *true_filename; /* 未受 #line 指令修改的文件名 */
    unsigned char unget[4];  /* 回退字符缓冲 */
    unsigned char buffer[1]; /* 实际数据（额外预留 CH_EOB 字符的空间） */
} BufferedFile;

#define CH_EOB   '\\'       /* 缓冲区结尾，或文件中的 '\0' */
#define CH_EOF   (-1)   /* 文件结束 */

/*
 * TokenString —— 记号串（用于记录宏展开后的记号序列）
 */
typedef struct TokenString {
    int *str;                /* 记号数组 */
    int len;                 /* 当前长度 */
    int lastlen;             /* 上一次的长度（回退用） */
    int allocated_len;       /* 已分配的容量 */
    int last_line_num;       /* 上一行号 */
    int save_line_num;       /* 保存的行号 */
    /* 通过 begin/end_macro() 把多个记号串串联起来 */
    struct TokenString *prev;
    const int *prev_ptr;
    char alloc;              /* 是否由本结构负责释放 str */
} TokenString;

/*
 * InlineFunc —— 内联函数
 *
 * 内联函数以记号串形式保存，只有被引用时才真正编译。
 */
typedef struct InlineFunc {
    TokenString *func_str;   /* 函数体记号串 */
    Sym *sym;                /* 函数符号 */
    char filename[1];        /* 定义所在文件名 */
} InlineFunc;

/*
 * CachedInclude —— 头文件包含缓存
 *
 * 用于加快查找，并在头文件被 #ifndef ... #endif 保护时避免重复包含。
 */
typedef struct CachedInclude {
    int ifndef_macro;        /* 该文件受哪个 #ifndef 宏保护 */
    int once;                /* 是否带 #pragma once */
    int hash_next;           /* 哈希链下一项，-1 表示结束 */
    char filename[1];        /* #include 中指定的路径 */
} CachedInclude;

#define CACHED_INCLUDES_HASH_SIZE 32

#ifdef CONFIG_TCC_ASM
/*
 * ExprValue —— 汇编表达式求值结果
 */
typedef struct ExprValue {
    uint64_t v;              /* 数值 */
    Sym *sym;                /* 关联符号 */
    int pcrel;               /* 是否为 PC 相对 */
} ExprValue;

#define MAX_ASM_OPERANDS 30
/*
 * ASMOperand —— 内联汇编的一个操作数（GCC 扩展语法）
 */
typedef struct ASMOperand {
    int id; /* GCC 3 的可选标识符（为 0 表示仅支持编号） */
    char *constraint;  /* 约束字符串 */
    char asm_str[16];  /* 为该操作数生成的汇编字符串 */
    SValue *vt;        /* 表达式的 C 值 */
    int ref_index;     /* 若 >= 0，表示引用某个输出约束 */
    int input_index;   /* 若 >= 0，表示引用某个输入约束 */
    int priority;      /* 优先级，用于分配寄存器 */
    int reg;           /* 若 >= 0，表示该操作数使用的寄存器号 */
    int is_llong;      /* 是否为双寄存器（long long）值 */
    int is_memory;     /* 是否为内存操作数 */
    int is_rw;         /* 是否为 '+' 修饰符（读写） */
} ASMOperand;
#endif

/*
 * sym_attr —— 符号的额外属性（不写入符号表）
 *
 * 与 ELF 符号表一一对应（下标相同），用于存放 GOT/PLT 相关的中转信息。
 */
struct sym_attr {
    unsigned got_offset;     /* 该符号在 GOT 中的偏移 */
    unsigned plt_offset;     /* 该符号在 PLT 中的偏移 */
    int plt_sym;             /* PLT 中重定向到的符号下标 */
    int dyn_index;           /* 动态符号表下标 */
};

/*
 * TCCState —— 编译器状态总账本
 *
 * 一次编译（或一个 libtcc 实例）的所有配置、路径、符号表、段表、
 * 预处理栈、错误处理等信息都集中在这里。
 *
 * 生命周期（对应 libtcc.h 中的公开 API）：
 *   tcc_new()      分配实例并置零，同时设置全局变量 tcc_state 指向它
 *   tcc_set_*()    设置搜索路径、输出类型、方言选项等
 *   tcc_add_*()    喂入源文件、目标文件、库
 *   tcc_relocate() / tcc_run() / tcc_output_file()  产出结果
 *   tcc_delete()   释放实例（各段的 data、符号池等一并回收）
 * 同一进程可以存在多个实例，但编译器主体代码经由全局 tcc_state 取“当前实例”，
 * 因此一次只应有一个实例处于活动状态。
 *
 * 字段按用途分组索引：
 *   - 编译开关：verbose / nostdinc / nostdlib / static_link / ...
 *   - C 方言与警告：char_is_unsigned、ms_bitfields、warn_* 等
 *   - 输出控制：output_type、output_format、text_addr、section_align
 *   - 搜索路径：include_paths / sysinclude_paths / library_paths / crt_paths
 *   - 预处理状态：include_stack（#include 栈）、ifdef_stack（#if 嵌套栈）、
 *     pack_stack（#pragma pack 栈），各自用对应的 *_stack_ptr 指向栈顶，
 *     从而支持任意层数的嵌套
 *   - 段与符号：sections（下标 0 是占位项，真正的段从下标 1 开始）、
 *     priv_sections（带 SHF_PRIVATE 的内部段，不写出到目标文件）、
 *     got / plt / symtab / dynsym，以及符号属性数组 sym_attrs
 *   - 错误处理：error_func / error_jmp_buf / nb_errors，
 *     tcc_error() 通过 longjmp(错误跳转缓冲) 返回到调用者而不是直接退出
 *   - 仅命令行前端使用的成员：files / nb_files / outfile / 各种选项标志
 */
struct TCCState {

    int verbose; /* 若为真，编译过程中打印详细信息 */
    int nostdinc; /* 若为真，不加入标准头文件搜索路径 */
    int nostdlib; /* 若为真，不链接标准库 */
    int nocommon; /* 若为真，不为 .bss 数据使用 common 符号 */
    int static_link; /* 若为真，执行静态链接 */
    int rdynamic; /* 若为真，导出所有符号 */
    int symbolic; /* 若为真，优先解析当前模块内的符号 */
    int alacarte_link; /* 若为真，仅链接归档中被实际引用的对象 */

    char *tcc_lib_path; /* CONFIG_TCCDIR 或 -B 选项指定的路径 */
    char *soname; /* 命令行指定的 -soname */
    char *rpath; /* 命令行指定的 -Wl,-rpath= */
    int enable_new_dtags; /* 同上，(-Wl,--enable-new-dtags) */

    /* 输出类型，见 TCC_OUTPUT_XXX */
    int output_type;
    /* 输出格式，见 TCC_OUTPUT_FORMAT_xxx */
    int output_format;

    /* C 语言相关选项 */
    int char_is_unsigned;             /* 默认 char 是否为无符号 */
    int leading_underscore;           /* 是否为外部符号添加前导下划线 */
    int ms_extensions;	/* 允许无标识符的嵌套具名结构体表现得像匿名结构体 */
    int dollars_in_identifiers;	/* 允许标识符中出现 '$' 字符 */
    int ms_bitfields; /* 若为真，采用 MS 的位域对齐算法 */

    /* 警告开关 */
    int warn_write_strings;
    int warn_unsupported;
    int warn_error;
    int warn_none;
    int warn_implicit_function_declaration;
    int warn_gcc_compat;

    /* 带调试符号编译（并在执行出错时使用这些符号） */
    int do_debug;
#ifdef CONFIG_TCC_BCHECK
    /* 带内建的内存与边界检查器编译 */
    int do_bounds_check;
#endif
    int run_test; /* -dt -run 时指定运行第几个测试 */

    addr_t text_addr; /* 代码段地址 */
    int has_text_addr;

    unsigned section_align; /* 段对齐 */

    char *init_symbol; /* 加载时调用的符号（当前未使用） */
    char *fini_symbol; /* 卸载时调用的符号（当前未使用） */

    /* 所有已加载动态库的数组（含被其它库引用的库） */
    DLLReference **loaded_dlls;
    int nb_loaded_dlls;

    /* 头文件搜索路径 */
    char **include_paths;
    int nb_include_paths;

    /* 系统头文件搜索路径 */
    char **sysinclude_paths;
    int nb_sysinclude_paths;

    /* 库文件搜索路径 */
    char **library_paths;
    int nb_library_paths;

    /* crt?.o 目标文件路径 */
    char **crt_paths;
    int nb_crt_paths;

    /* -include 指定的文件 */
    char **cmd_include_files;
    int nb_cmd_include_files;

    /* 错误处理 */
    void *error_opaque;
    void (*error_func)(void *opaque, const char *msg);
    int error_set_jmp_enabled;
    jmp_buf error_jmp_buf;
    int nb_errors;

    /* 预处理（-E）的输出文件 */
    FILE *ppfp;
    enum {
	LINE_MACRO_OUTPUT_FORMAT_GCC,
	LINE_MACRO_OUTPUT_FORMAT_NONE,
	LINE_MACRO_OUTPUT_FORMAT_STD,
    LINE_MACRO_OUTPUT_FORMAT_P10 = 11
    } Pflag; /* -P 开关 */
    char dflag; /* -dX 的值 */

    /* 用于 -MD/-MF：本次编译收集到的依赖 */
    char **target_deps;
    int nb_target_deps;

    /* 编译过程 */
    BufferedFile *include_stack[INCLUDE_STACK_SIZE];  /* #include 文件栈 */
    BufferedFile **include_stack_ptr;

    int ifdef_stack[IFDEF_STACK_SIZE];                /* #ifdef 状态栈 */
    int *ifdef_stack_ptr;

    /* 受 #ifndef MACRO 保护的头文件 */
    int cached_includes_hash[CACHED_INCLUDES_HASH_SIZE];
    CachedInclude **cached_includes;
    int nb_cached_includes;

    /* #pragma pack 栈 */
    int pack_stack[PACK_STACK_SIZE];
    int *pack_stack_ptr;
    char **pragma_libs;
    int nb_pragma_libs;

    /* 内联函数以记号列表形式保存，仅在被引用时最后编译 */
    struct InlineFunc **inline_fns;
    int nb_inline_fns;

    /* 段表 */
    Section **sections;
    int nb_sections; /* 段的数量，包含第一个占位段 */

    Section **priv_sections;
    int nb_priv_sections; /* 私有段的数量 */

    /* GOT 与 PLT 的处理 */
    Section *got;
    Section *plt;

    /* 临时动态符号段（用于加载动态库时） */
    Section *dynsymtab_section;
    /* 导出的动态符号段 */
    Section *dynsym;
    /* 全局 symtab_section 的副本 */
    Section *symtab;
    /* 符号表中各符号的额外属性（如 GOT/PLT 值） */
    struct sym_attr *sym_attrs;
    int nb_sym_attrs;

#ifdef TCC_IS_NATIVE
    const char *runtime_main;   /* -run 时程序的入口符号 */
    void **runtime_mem;         /* 运行时分配的内存块 */
    int nb_runtime_mem;
#endif

    /* 仅由 main 和 tcc_parse_args 使用 */
    struct filespec **files; /* 命令行上看到的文件 */
    int nb_files; /* 文件数量 */
    int nb_libraries; /* 其中库的数量 */
    int filetype;
    char *outfile; /* 输出文件名 */
    int option_r; /* -r 选项 */
    int do_bench; /* -bench 选项 */
    int gen_deps; /* -MD 选项 */
    char *deps_outfile; /* -MF 选项 */
    int option_pthread; /* -pthread 选项 */
    int argc;
    char **argv;
};

/*
 * filespec —— 命令行上的一个输入文件
 */
struct filespec {
    char type;      /* 文件类型（AFF_TYPE_xxx） */
    char alacarte;  /* 是否按需从归档中链接 */
    char name[1];   /* 文件名 */
};

/* 值栈中 r 字段可能取的值： */
#define VT_VALMASK   0x003f  /* 值存放位置的掩码：寄存器编号或： */
#define VT_CONST     0x0030  /* 常量，值在 vc 中（必须是第一个非寄存器值） */
#define VT_LLOCAL    0x0031  /* 左值，位于栈上（带偏移） */
#define VT_LOCAL     0x0032  /* 栈上（带偏移） */
#define VT_CMP       0x0033  /* 值存放在处理器标志位中（在 vc 中） */
#define VT_JMP       0x0034  /* 值为“跳转为真”的结果（偶数） */
#define VT_JMPI      0x0035  /* 值为“跳转为假”的结果（奇数） */
#define VT_LVAL      0x0100  /* 该值是左值 */
#define VT_SYM       0x0200  /* 需要叠加一个符号值 */
#define VT_MUSTCAST  0x0400  /* 值必须转换才能保证正确（用于存放在整型寄存器中的
                                char/short） */
#define VT_MUSTBOUND 0x0800  /* 解引用该值前必须先做边界检查 */
#define VT_BOUNDED   0x8000  /* 该值已受边界保护，边界函数调用点地址在 vc 中 */
#define VT_LVAL_BYTE     0x1000  /* 左值是字节 */
#define VT_LVAL_SHORT    0x2000  /* 左值是 short */
#define VT_LVAL_UNSIGNED 0x4000  /* 左值是无符号 */
#define VT_LVAL_TYPE     (VT_LVAL_BYTE | VT_LVAL_SHORT | VT_LVAL_UNSIGNED)

/* 类型 */
#define VT_BTYPE       0x000f  /* 基本类型掩码 */
#define VT_VOID             0  /* void 类型 */
#define VT_BYTE             1  /* 有符号字节 */
#define VT_SHORT            2  /* short */
#define VT_INT              3  /* int */
#define VT_LLONG            4  /* 64 位整数 */
#define VT_PTR              5  /* 指针 */
#define VT_FUNC             6  /* 函数类型 */
#define VT_STRUCT           7  /* struct/union 定义 */
#define VT_FLOAT            8  /* IEEE float */
#define VT_DOUBLE           9  /* IEEE double */
#define VT_LDOUBLE         10  /* IEEE long double */
#define VT_BOOL            11  /* ISOC99 布尔类型 */
#define VT_QLONG           13  /* 128 位整数，仅用于 x86-64 ABI */
#define VT_QFLOAT          14  /* 128 位浮点，仅用于 x86-64 ABI */

#define VT_UNSIGNED    0x0010  /* 无符号类型 */
#define VT_DEFSIGN     0x0020  /* 显式 signed 或 unsigned */
#define VT_ARRAY       0x0040  /* 数组类型（同时带有 VT_PTR） */
#define VT_BITFIELD    0x0080  /* 位域修饰 */
#define VT_CONSTANT    0x0100  /* const 修饰 */
#define VT_VOLATILE    0x0200  /* volatile 修饰 */
#define VT_VLA         0x0400  /* 变长数组类型（同时带有 VT_PTR 和 VT_ARRAY） */
#define VT_LONG        0x0800  /* long 类型（同时带有 VT_INT 或 VT_LLONG） */

/* 存储类 */
#define VT_EXTERN  0x00001000  /* extern 定义 */
#define VT_STATIC  0x00002000  /* static 变量 */
#define VT_TYPEDEF 0x00004000  /* typedef 定义 */
#define VT_INLINE  0x00008000  /* inline 定义 */
/* 目前未使用：0x000[1248]0000 */

#define VT_STRUCT_SHIFT 20     /* 位域位移值的移位量（32 - 2*6） */
#define VT_STRUCT_MASK (((1 << (6+6)) - 1) << VT_STRUCT_SHIFT | VT_BITFIELD)
#define BIT_POS(t) (((t) >> VT_STRUCT_SHIFT) & 0x3f)
#define BIT_SIZE(t) (((t) >> (VT_STRUCT_SHIFT + 6)) & 0x3f)

#define VT_UNION    (1 << VT_STRUCT_SHIFT | VT_STRUCT)
#define VT_ENUM     (2 << VT_STRUCT_SHIFT) /* 本质上是枚举的整型 */
#define VT_ENUM_VAL (3 << VT_STRUCT_SHIFT) /* 本质上是枚举常量的整型 */

#define IS_ENUM(t) ((t & VT_STRUCT_MASK) == VT_ENUM)
#define IS_ENUM_VAL(t) ((t & VT_STRUCT_MASK) == VT_ENUM_VAL)
#define IS_UNION(t) ((t & (VT_STRUCT_MASK|VT_BTYPE)) == VT_UNION)

/* 类型掩码（不含存储类） */
#define VT_STORAGE (VT_EXTERN | VT_STATIC | VT_TYPEDEF | VT_INLINE)
#define VT_TYPE (~(VT_STORAGE|VT_STRUCT_MASK))

/* 由 tccasm.c 首先创建的符号 */
#define VT_ASM (VT_VOID | VT_UNSIGNED)
#define IS_ASM_SYM(sym) (((sym)->type.t & (VT_BTYPE | VT_ASM)) == VT_ASM)

/* 记号值 */

/* 注意：以下比较类记号的取值依赖 i386 汇编代码 */
#define TOK_ULT 0x92
#define TOK_UGE 0x93
#define TOK_EQ  0x94
#define TOK_NE  0x95
#define TOK_ULE 0x96
#define TOK_UGT 0x97
#define TOK_Nset 0x98
#define TOK_Nclear 0x99
#define TOK_LT  0x9c
#define TOK_GE  0x9d
#define TOK_LE  0x9e
#define TOK_GT  0x9f

#define TOK_LAND  0xa0
#define TOK_LOR   0xa1
#define TOK_DEC   0xa2
#define TOK_MID   0xa3 /* 自增/自减，用于产生 void 常量 */
#define TOK_INC   0xa4
#define TOK_UDIV  0xb0 /* 无符号除法 */
#define TOK_UMOD  0xb1 /* 无符号取模 */
#define TOK_PDIV  0xb2 /* 快速除法，指针舍入未定义 */

/* 携带值的记号（数值存放在附加记号串空间 / tokc 中） --> */
#define TOK_CCHAR   0xb3 /* 字符常量，值在 tokc 中 */
#define TOK_LCHAR   0xb4 /* 宽字符常量 */
#define TOK_CINT    0xb5 /* 整数，值在 tokc 中 */
#define TOK_CUINT   0xb6 /* 无符号整数常量 */
#define TOK_CLLONG  0xb7 /* long long 常量 */
#define TOK_CULLONG 0xb8 /* unsigned long long 常量 */
#define TOK_STR     0xb9 /* 字符串指针，值在 tokc 中 */
#define TOK_LSTR    0xba /* 宽字符串 */
#define TOK_CFLOAT  0xbb /* float 常量 */
#define TOK_CDOUBLE 0xbc /* double 常量 */
#define TOK_CLDOUBLE 0xbd /* long double 常量 */
#define TOK_PPNUM   0xbe /* 预处理阶段的数字 */
#define TOK_PPSTR   0xbf /* 预处理阶段的字符串 */
#define TOK_LINENUM 0xc0 /* 行号信息 */
#define TOK_TWODOTS 0xa8 /* C++ 的 "::" 记号？ */
/* <-- */

#define TOK_UMULL    0xc2 /* 无符号 32x32 -> 64 乘法 */
#define TOK_ADDC1    0xc3 /* 带进位加法，产生进位 */
#define TOK_ADDC2    0xc4 /* 带进位加法，使用进位 */
#define TOK_SUBC1    0xc5 /* 带借位减法，产生借位 */
#define TOK_SUBC2    0xc6 /* 带借位减法，使用借位 */
#define TOK_ARROW    0xc7 /* "->" */
#define TOK_DOTS     0xc8 /* "..." 三个点 */
#define TOK_SHR      0xc9 /* 无符号右移 */
#define TOK_TWOSHARPS 0xca /* 预处理中的 "##" */
#define TOK_PLCHLDR  0xcb /* C99 定义的占位符记号 */
#define TOK_NOSUBST  0xcc /* 表示后面的记号已经过预处理 */
#define TOK_PPJOIN   0xcd /* 处于可拼接位置的 '##' */
#define TOK_CLONG    0xce /* long 常量 */
#define TOK_CULONG   0xcf /* unsigned long 常量 */

#define TOK_SHL   0x01 /* 左移 */
#define TOK_SAR   0x02 /* 算术（有符号）右移 */

/* 赋值运算符：普通运算符或 0x80 */
#define TOK_A_MOD 0xa5
#define TOK_A_AND 0xa6
#define TOK_A_MUL 0xaa
#define TOK_A_ADD 0xab
#define TOK_A_SUB 0xad
#define TOK_A_DIV 0xaf
#define TOK_A_XOR 0xde
#define TOK_A_OR  0xfc
#define TOK_A_SHL 0x81
#define TOK_A_SAR 0x82

#define TOK_EOF       (-1)  /* 文件结束 */
#define TOK_LINEFEED  10    /* 换行 */

/* 所有标识符和字符串的记号值都大于此值 */
#define TOK_IDENT 256

#define DEF_ASM(x) DEF(TOK_ASM_ ## x, #x)
#define TOK_ASM_int TOK_INT
#define DEF_ASMDIR(x) DEF(TOK_ASMDIR_ ## x, "." #x)
#define TOK_ASMDIR_FIRST TOK_ASMDIR_byte
#define TOK_ASMDIR_LAST TOK_ASMDIR_section

/* 由 tcctok.h 中的 DEF() 列表展开出全部记号枚举 */
enum tcc_token {
    TOK_LAST = TOK_IDENT - 1
#define DEF(id, str) ,id
#include "tcctok.h"
#undef DEF
};

/* 关键字：tok >= TOK_IDENT && tok < TOK_UIDENT */
#define TOK_UIDENT TOK_DEFINE

/* ------------ libtcc.c ------------ */

/* 是否启用 GNU C 扩展 */
ST_DATA int gnu_ext;
/* 是否启用 Tiny C 扩展 */
ST_DATA int tcc_ext;
/* XXX：应尽快去掉这个全局变量 */
ST_DATA struct TCCState *tcc_state;

/* tcc 主函数当前使用的公共函数 */
ST_FUNC char *pstrcpy(char *buf, int buf_size, const char *s);
ST_FUNC char *pstrcat(char *buf, int buf_size, const char *s);
ST_FUNC char *pstrncpy(char *out, const char *in, size_t num);
PUB_FUNC char *tcc_basename(const char *name);
PUB_FUNC char *tcc_fileextension (const char *name);

#ifndef MEM_DEBUG
PUB_FUNC void tcc_free(void *ptr);
PUB_FUNC void *tcc_malloc(unsigned long size);
PUB_FUNC void *tcc_mallocz(unsigned long size);
PUB_FUNC void *tcc_realloc(void *ptr, unsigned long size);
PUB_FUNC char *tcc_strdup(const char *str);
#else
#define tcc_free(ptr)           tcc_free_debug(ptr)
#define tcc_malloc(size)        tcc_malloc_debug(size, __FILE__, __LINE__)
#define tcc_mallocz(size)       tcc_mallocz_debug(size, __FILE__, __LINE__)
#define tcc_realloc(ptr,size)   tcc_realloc_debug(ptr, size, __FILE__, __LINE__)
#define tcc_strdup(str)         tcc_strdup_debug(str, __FILE__, __LINE__)
PUB_FUNC void tcc_free_debug(void *ptr);
PUB_FUNC void *tcc_malloc_debug(unsigned long size, const char *file, int line);
PUB_FUNC void *tcc_mallocz_debug(unsigned long size, const char *file, int line);
PUB_FUNC void *tcc_realloc_debug(void *ptr, unsigned long size, const char *file, int line);
PUB_FUNC char *tcc_strdup_debug(const char *str, const char *file, int line);
#endif

/* 禁用标准库的内存函数，强制使用 tcc_* 版本 */
#define free(p) use_tcc_free(p)
#define malloc(s) use_tcc_malloc(s)
#define realloc(p, s) use_tcc_realloc(p, s)
#undef strdup
#define strdup(s) use_tcc_strdup(s)
PUB_FUNC void tcc_memcheck(void);
PUB_FUNC void tcc_error_noabort(const char *fmt, ...);
PUB_FUNC NORETURN void tcc_error(const char *fmt, ...);
PUB_FUNC void tcc_warning(const char *fmt, ...);

/* 其它工具函数 */
ST_FUNC void dynarray_add(void *ptab, int *nb_ptr, void *data);
ST_FUNC void dynarray_reset(void *pp, int *n);
ST_INLN void cstr_ccat(CString *cstr, int ch);
ST_FUNC void cstr_cat(CString *cstr, const char *str, int len);
ST_FUNC void cstr_wccat(CString *cstr, int ch);
ST_FUNC void cstr_new(CString *cstr);
ST_FUNC void cstr_free(CString *cstr);
ST_FUNC void cstr_reset(CString *cstr);

ST_INLN void sym_free(Sym *sym);
ST_FUNC Sym *sym_push2(Sym **ps, int v, int t, int c);
ST_FUNC Sym *sym_find2(Sym *s, int v);
ST_FUNC Sym *sym_push(int v, CType *type, int r, int c);
ST_FUNC void sym_pop(Sym **ptop, Sym *b, int keep);
ST_INLN Sym *struct_find(int v);
ST_INLN Sym *sym_find(int v);
ST_FUNC Sym *global_identifier_push(int v, int t, int c);

ST_FUNC void tcc_open_bf(TCCState *s1, const char *filename, int initlen);
ST_FUNC int tcc_open(TCCState *s1, const char *filename);
ST_FUNC void tcc_close(void);

ST_FUNC int tcc_add_file_internal(TCCState *s1, const char *filename, int flags);
/* flags： */
#define AFF_PRINT_ERROR     0x10 /* 文件找不到时打印错误 */
#define AFF_REFERENCED_DLL  0x20 /* 从另一个 dll 中加载被引用的 dll */
#define AFF_TYPE_BIN        0x40 /* 要添加的文件是二进制文件 */
/* s->filetype： */
#define AFF_TYPE_NONE   0
#define AFF_TYPE_C      1
#define AFF_TYPE_ASM    2
#define AFF_TYPE_ASMPP  3
#define AFF_TYPE_LIB    4
/* tcc_object_type(...) 的返回值 */
#define AFF_BINTYPE_REL 1
#define AFF_BINTYPE_DYN 2
#define AFF_BINTYPE_AR  3


ST_FUNC int tcc_add_crt(TCCState *s, const char *filename);
ST_FUNC int tcc_add_dll(TCCState *s, const char *filename, int flags);
ST_FUNC void tcc_add_pragma_libs(TCCState *s1);
PUB_FUNC int tcc_add_library_err(TCCState *s, const char *f);
PUB_FUNC void tcc_print_stats(TCCState *s, unsigned total_time);
PUB_FUNC int tcc_parse_args(TCCState *s, int *argc, char ***argv, int optind);
#ifdef _WIN32
ST_FUNC char *normalize_slashes(char *path);
#endif

/* tcc_parse_args 的返回码： */
#define OPT_HELP 1
#define OPT_HELP2 2
#define OPT_V 3
#define OPT_PRINT_DIRS 4
#define OPT_AR 5
#define OPT_M32 32
#define OPT_M64 64

/* ------------ tccpp.c ------------ */

ST_DATA struct BufferedFile *file; /* 当前输入文件 */
ST_DATA int ch, tok;               /* 当前字符、当前记号 */
ST_DATA CValue tokc;               /* 当前记号的附加值 */
ST_DATA const int *macro_ptr;      /* 宏展开时的记号流指针 */
ST_DATA int parse_flags;           /* 解析标志（PARSE_FLAG_xxx） */
ST_DATA int tok_flags;             /* 记号标志（TOK_FLAG_xxx） */
ST_DATA CString tokcstr; /* 当前解析出的字符串（若有） */

/* 用于显示性能统计信息 */
ST_DATA int total_lines;
ST_DATA int total_bytes;
ST_DATA int tok_ident;             /* 已分配的记号总数 */
ST_DATA TokenSym **table_ident;    /* 标识符哈希表 */

#define TOK_FLAG_BOL   0x0001 /* 之前是行首 */
#define TOK_FLAG_BOF   0x0002 /* 之前是文件开头 */
#define TOK_FLAG_ENDIF 0x0004 /* 找到了与起始 #ifdef 配对的 #endif */
#define TOK_FLAG_EOF   0x0008 /* 文件结束 */

#define PARSE_FLAG_PREPROCESS 0x0001 /* 启用预处理 */
#define PARSE_FLAG_TOK_NUM    0x0002 /* 返回数字而非 TOK_PPNUM */
#define PARSE_FLAG_LINEFEED   0x0004 /* 把换行作为记号返回；
                                        在 EOF 处也返回换行 */
#define PARSE_FLAG_ASM_FILE 0x0008 /* 正在处理汇编文件：'#' 可用作行注释等 */
#define PARSE_FLAG_SPACES     0x0010 /* next() 返回空白记号（用于 -E） */
#define PARSE_FLAG_ACCEPT_STRAYS 0x0020 /* next() 返回 '\\' 记号 */
#define PARSE_FLAG_TOK_STR    0x0040 /* 返回解析后的字符串而非 TOK_PPSTR */

/* isidnum_table 的标志位： */
#define IS_SPC 1
#define IS_ID  2
#define IS_NUM 4

ST_FUNC TokenSym *tok_alloc(const char *str, int len);
ST_FUNC const char *get_tok_str(int v, CValue *cv);
ST_FUNC void begin_macro(TokenString *str, int alloc);
ST_FUNC void end_macro(void);
ST_FUNC int set_idnum(int c, int val);
ST_INLN void tok_str_new(TokenString *s);
ST_FUNC TokenString *tok_str_alloc(void);
ST_FUNC void tok_str_free(TokenString *s);
ST_FUNC void tok_str_free_str(int *str);
ST_FUNC void tok_str_add(TokenString *s, int t);
ST_FUNC void tok_str_add_tok(TokenString *s);
ST_INLN void define_push(int v, int macro_type, int *str, Sym *first_arg);
ST_FUNC void define_undef(Sym *s);
ST_INLN Sym *define_find(int v);
ST_FUNC void free_defines(Sym *b);
ST_FUNC Sym *label_find(int v);
ST_FUNC Sym *label_push(Sym **ptop, int v, int flags);
ST_FUNC void label_pop(Sym **ptop, Sym *slast, int keep);
ST_FUNC void parse_define(void);
ST_FUNC void preprocess(int is_bof);
ST_FUNC void next_nomacro(void);
ST_FUNC void next(void);
ST_INLN void unget_tok(int last_tok);
ST_FUNC void preprocess_start(TCCState *s1, int is_asm);
ST_FUNC void preprocess_end(TCCState *s1);
ST_FUNC void tccpp_new(TCCState *s);
ST_FUNC void tccpp_delete(TCCState *s);
ST_FUNC int tcc_preprocess(TCCState *s1);
ST_FUNC void skip(int c);
ST_FUNC NORETURN void expect(const char *msg);

/* 空白字符（不含换行） */
static inline int is_space(int ch) {
    return ch == ' ' || ch == '\t' || ch == '\v' || ch == '\f' || ch == '\r';
}
static inline int isid(int c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_';
}
static inline int isnum(int c) {
    return c >= '0' && c <= '9';
}
static inline int isoct(int c) {
    return c >= '0' && c <= '7';
}
static inline int toup(int c) {
    return (c >= 'a' && c <= 'z') ? c - 'a' + 'A' : c;
}

/* ------------ tccgen.c ------------ */

#define SYM_POOL_NB (8192 / sizeof(Sym))
ST_DATA Sym *sym_free_first;      /* 空闲符号链表 */
ST_DATA void **sym_pools;         /* 符号内存池数组 */
ST_DATA int nb_sym_pools;         /* 内存池数量 */

ST_DATA Sym *global_stack;        /* 全局符号栈 */
ST_DATA Sym *local_stack;         /* 局部符号栈 */
ST_DATA Sym *local_label_stack;   /* 局部标号栈 */
ST_DATA Sym *global_label_stack;  /* 全局标号栈 */
ST_DATA Sym *define_stack;        /* 宏定义栈 */
ST_DATA CType char_pointer_type, func_old_type, int_type, size_type;
ST_DATA SValue __vstack[1+/*让 bcheck 满意*/ VSTACK_SIZE], *vtop, *pvtop;
#define vstack  (__vstack + 1)    /* vstack 从下标 1 开始，下标 0 作为哨兵 */
ST_DATA int rsym, anon_sym, ind, loc; /* 结果符号、匿名符号计数、缩进、局部栈偏移 */

ST_DATA int const_wanted; /* 为真表示当前要求常量表达式 */
ST_DATA int nocode_wanted; /* 为真表示该表达式不需要生成代码 */
ST_DATA int global_expr;  /* 为真表示复合字面量必须分配在全局（解析初始化器时使用） */
ST_DATA CType func_vt; /* 当前函数返回类型（return 语句使用） */
ST_DATA int func_var; /* 为真表示当前函数是变参函数 */
ST_DATA int func_vc;
ST_DATA int last_line_num, last_ind, func_ind; /* 调试用的上一行号与 pc */
ST_DATA const char *funcname;
ST_DATA int g_debug;

ST_FUNC void tcc_debug_start(TCCState *s1);
ST_FUNC void tcc_debug_end(TCCState *s1);
ST_FUNC void tcc_debug_funcstart(TCCState *s1, Sym *sym);
ST_FUNC void tcc_debug_funcend(TCCState *s1, int size);
ST_FUNC void tcc_debug_line(TCCState *s1);

ST_FUNC int tccgen_compile(TCCState *s1);
ST_FUNC void free_inline_functions(TCCState *s);
ST_FUNC void check_vstack(void);

ST_INLN int is_float(int t);
ST_FUNC int ieee_finite(double d);
ST_FUNC void test_lvalue(void);
ST_FUNC void vpushi(int v);
ST_FUNC ElfSym *elfsym(Sym *);
ST_FUNC void update_storage(Sym *sym);
ST_FUNC Sym *external_global_sym(int v, CType *type, int r);
ST_FUNC void vset(CType *type, int r, int v);
ST_FUNC void vswap(void);
ST_FUNC void vpush_global_sym(CType *type, int v);
ST_FUNC void vrote(SValue *e, int n);
ST_FUNC void vrott(int n);
ST_FUNC void vrotb(int n);
ST_FUNC void vpushv(SValue *v);
ST_FUNC void save_reg(int r);
ST_FUNC void save_reg_upstack(int r, int n);
ST_FUNC int get_reg(int rc);
ST_FUNC void save_regs(int n);
ST_FUNC void gaddrof(void);
ST_FUNC int gv(int rc);
ST_FUNC void gv2(int rc1, int rc2);
ST_FUNC void vpop(void);
ST_FUNC void gen_op(int op);
ST_FUNC int type_size(CType *type, int *a);
ST_FUNC void mk_pointer(CType *type);
ST_FUNC void vstore(void);
ST_FUNC void inc(int post, int c);
ST_FUNC void parse_mult_str (CString *astr, const char *msg);
ST_FUNC void parse_asm_str(CString *astr);
ST_FUNC int lvalue_type(int t);
ST_FUNC void indir(void);
ST_FUNC void unary(void);
ST_FUNC void expr_prod(void);
ST_FUNC void expr_sum(void);
ST_FUNC void gexpr(void);
ST_FUNC int expr_const(void);

/* ------------ tccelf.c ------------ */

#define TCC_OUTPUT_FORMAT_ELF    0 /* 默认输出格式：ELF */
#define TCC_OUTPUT_FORMAT_BINARY 1 /* 纯二进制镜像输出 */

#define ARMAG  "!<arch>\012"    /* COFF 与 a.out 归档文件的魔数 */

/*
 * Stab_Sym —— stab 调试符号表条目
 */
typedef struct {
    unsigned int n_strx;         /* 名称在字符串表中的下标 */
    unsigned char n_type;         /* 符号类型 */
    unsigned char n_other;        /* 杂项信息（通常为空） */
    unsigned short n_desc;        /* 描述字段 */
    unsigned int n_value;        /* 符号值 */
} Stab_Sym;

ST_DATA Section *text_section, *data_section, *bss_section; /* 预定义段 */
ST_DATA Section *common_section;
ST_DATA Section *cur_text_section; /* 当前生成函数代码所在的段 */
#ifdef CONFIG_TCC_ASM
ST_DATA Section *last_text_section; /* 用于处理汇编 .previous 指令 */
#endif
#ifdef CONFIG_TCC_BCHECK
/* 边界检查相关段 */
ST_DATA Section *bounds_section; /* 存放全局数据的边界描述 */
ST_DATA Section *lbounds_section; /* 存放局部数据的边界描述 */
ST_FUNC void tccelf_bounds_new(TCCState *s);
#endif
/* 符号表段 */
ST_DATA Section *symtab_section;
/* 调试段 */
ST_DATA Section *stab_section, *stabstr_section;

ST_FUNC void tccelf_new(TCCState *s);
ST_FUNC void tccelf_delete(TCCState *s);
ST_FUNC void tccelf_stab_new(TCCState *s);
ST_FUNC void tccelf_begin_file(TCCState *s1);
ST_FUNC void tccelf_end_file(TCCState *s1);

ST_FUNC Section *new_section(TCCState *s1, const char *name, int sh_type, int sh_flags);
ST_FUNC void section_realloc(Section *sec, unsigned long new_size);
ST_FUNC size_t section_add(Section *sec, addr_t size, int align);
ST_FUNC void *section_ptr_add(Section *sec, addr_t size);
ST_FUNC void section_reserve(Section *sec, unsigned long size);
ST_FUNC Section *find_section(TCCState *s1, const char *name);
ST_FUNC Section *new_symtab(TCCState *s1, const char *symtab_name, int sh_type, int sh_flags, const char *strtab_name, const char *hash_name, int hash_sh_flags);

ST_FUNC void put_extern_sym2(Sym *sym, int sh_num, addr_t value, unsigned long size, int can_add_underscore);
ST_FUNC void put_extern_sym(Sym *sym, Section *section, addr_t value, unsigned long size);
#if PTR_SIZE == 4
ST_FUNC void greloc(Section *s, Sym *sym, unsigned long offset, int type);
#endif
ST_FUNC void greloca(Section *s, Sym *sym, unsigned long offset, int type, addr_t addend);

ST_FUNC int put_elf_str(Section *s, const char *sym);
ST_FUNC int put_elf_sym(Section *s, addr_t value, unsigned long size, int info, int other, int shndx, const char *name);
ST_FUNC int set_elf_sym(Section *s, addr_t value, unsigned long size, int info, int other, int shndx, const char *name);
ST_FUNC int find_elf_sym(Section *s, const char *name);
ST_FUNC void put_elf_reloc(Section *symtab, Section *s, unsigned long offset, int type, int symbol);
ST_FUNC void put_elf_reloca(Section *symtab, Section *s, unsigned long offset, int type, int symbol, addr_t addend);

ST_FUNC void put_stabs(const char *str, int type, int other, int desc, unsigned long value);
ST_FUNC void put_stabs_r(const char *str, int type, int other, int desc, unsigned long value, Section *sec, int sym_index);
ST_FUNC void put_stabn(int type, int other, int desc, int value);
ST_FUNC void put_stabd(int type, int other, int desc);

ST_FUNC void resolve_common_syms(TCCState *s1);
ST_FUNC void relocate_syms(TCCState *s1, Section *symtab, int do_resolve);
ST_FUNC void relocate_section(TCCState *s1, Section *s);

ST_FUNC int tcc_object_type(int fd, ElfW(Ehdr) *h);
ST_FUNC int tcc_load_object_file(TCCState *s1, int fd, unsigned long file_offset);
ST_FUNC int tcc_load_archive(TCCState *s1, int fd);
ST_FUNC void tcc_add_bcheck(TCCState *s1);
ST_FUNC void tcc_add_runtime(TCCState *s1);

ST_FUNC void build_got_entries(TCCState *s1);
ST_FUNC struct sym_attr *get_sym_attr(TCCState *s1, int index, int alloc);
ST_FUNC void squeeze_multi_relocs(Section *sec, size_t oldrelocoffset);

ST_FUNC addr_t get_elf_sym_addr(TCCState *s, const char *name, int err);
#if defined TCC_IS_NATIVE
ST_FUNC void *tcc_get_symbol_err(TCCState *s, const char *name);
#endif

ST_FUNC int tcc_load_dll(TCCState *s1, int fd, const char *filename, int level);
ST_FUNC int tcc_load_ldscript(TCCState *s1);
ST_FUNC uint8_t *parse_comment(uint8_t *p);
ST_FUNC void minp(void);
ST_INLN void inp(void);
ST_FUNC int handle_eob(void);

/* ------------ xxx-link.c ------------ */

/* 是否以及何时生成 GOT/PLT 条目。NO_GOTPLT_ENTRY 放在最前，
   这样未知重定位不会创建 GOT 或 PLT 条目 */
enum gotplt_entry {
    NO_GOTPLT_ENTRY,	/* 从不生成（例如 GLOB_DAT 与 JMP_SLOT 重定位） */
    BUILD_GOT_ONLY,	/* 只构建 GOT（例如 TPOFF 重定位） */
    AUTO_GOTPLT_ENTRY,	/* 当符号未定义（UNDEF）时生成 */
    ALWAYS_GOTPLT_ENTRY	/* 总是生成（例如 PLTOFF 重定位） */
};

ST_FUNC int code_reloc (int reloc_type);
ST_FUNC int gotplt_entry_type (int reloc_type);
ST_FUNC unsigned create_plt_entry(TCCState *s1, unsigned got_offset, struct sym_attr *attr);
ST_FUNC void relocate_init(Section *sr);
ST_FUNC void relocate(TCCState *s1, ElfW_Rel *rel, int type, unsigned char *ptr, addr_t addr, addr_t val);
ST_FUNC void relocate_plt(TCCState *s1);

/* ------------ xxx-gen.c（代码生成后端接口）------------ */

ST_DATA const int reg_classes[NB_REGS]; /* 各寄存器的类别位掩码 */

ST_FUNC void gsym_addr(int t, int a);   /* 回填跳转地址 */
ST_FUNC void gsym(int t);
ST_FUNC void load(int r, SValue *sv);   /* 把值装入寄存器 */
ST_FUNC void store(int r, SValue *v);   /* 把寄存器值写回内存 */
ST_FUNC int gfunc_sret(CType *vt, int variadic, CType *ret, int *align, int *regsize);
ST_FUNC void gfunc_call(int nb_args);   /* 生成函数调用代码 */
ST_FUNC void gfunc_prolog(CType *func_type); /* 生成函数序言 */
ST_FUNC void gfunc_epilog(void);        /* 生成函数尾声 */
ST_FUNC int gjmp(int t);                /* 生成无条件跳转 */
ST_FUNC void gjmp_addr(int a);
ST_FUNC int gtst(int inv, int t);       /* 生成条件跳转 */
#define gtst_addr(inv, a) gsym_addr(gtst(inv, 0), a)
ST_FUNC void gen_opi(int op);           /* 生成整型运算 */
ST_FUNC void gen_opf(int op);           /* 生成浮点运算 */
ST_FUNC void gen_cvt_ftoi(int t);       /* 浮点 -> 整型转换 */
ST_FUNC void gen_cvt_ftof(int t);       /* 浮点 -> 浮点转换 */
ST_FUNC void ggoto(void);
ST_FUNC void o(unsigned int c);         /* 发射一条指令 */
ST_FUNC void gen_cvt_itof(int t);       /* 整型 -> 浮点转换 */
ST_FUNC void gen_vla_sp_save(int addr); /* 变长数组：保存栈指针 */
ST_FUNC void gen_vla_sp_restore(int addr); /* 变长数组：恢复栈指针 */
ST_FUNC void gen_vla_alloc(CType *type, int align); /* 变长数组：分配空间 */

/* 小端字节序读写工具 */
static inline uint16_t read16le(unsigned char *p) {
    return p[0] | (uint16_t)p[1] << 8;
}
static inline void write16le(unsigned char *p, uint16_t x) {
    p[0] = x & 255;  p[1] = x >> 8 & 255;
}
static inline uint32_t read32le(unsigned char *p) {
  return read16le(p) | (uint32_t)read16le(p + 2) << 16;
}
static inline void write32le(unsigned char *p, uint32_t x) {
    write16le(p, x);  write16le(p + 2, x >> 16);
}
static inline void add32le(unsigned char *p, int32_t x) {
    write32le(p, read32le(p) + x);
}
static inline uint64_t read64le(unsigned char *p) {
  return read32le(p) | (uint64_t)read32le(p + 4) << 32;
}
static inline void write64le(unsigned char *p, uint64_t x) {
    write32le(p, x);  write32le(p + 4, x >> 32);
}
static inline void add64le(unsigned char *p, int64_t x) {
    write64le(p, read64le(p) + x);
}

#ifdef CONFIG_TCC_BCHECK
ST_FUNC void gen_bounded_ptr_add(void);
ST_FUNC void gen_bounded_ptr_deref(void);
#endif

/* ------------ arm64-gen.c ------------ */
#ifdef TCC_TARGET_ARM64
ST_FUNC void gen_cvt_sxtw(void);        /* 32 位到 64 位有符号扩展 */
ST_FUNC void gen_opl(int op);           /* 64 位整数运算 */
ST_FUNC void gfunc_return(CType *func_type); /* 生成函数返回代码 */
ST_FUNC void gen_va_start(void);        /* 生成变参起始地址计算 */
ST_FUNC void gen_va_arg(CType *t);      /* 生成取变参代码 */
ST_FUNC void gen_clear_cache(void);     /* 清空指令缓存 */
#endif

/* ------------ tccasm.c ------------ */
ST_FUNC void asm_instr(void);
ST_FUNC void asm_global_instr(void);
#ifdef CONFIG_TCC_ASM
ST_FUNC int find_constraint(ASMOperand *operands, int nb_operands, const char *name, const char **pp);
ST_FUNC Sym* get_asm_sym(int name, Sym *csym);
ST_FUNC void asm_expr(TCCState *s1, ExprValue *pe);
ST_FUNC int asm_int_expr(TCCState *s1);
ST_FUNC int tcc_assemble(TCCState *s1, int do_preprocess);
/* ------------ i386-asm.c ------------ */
ST_FUNC void gen_expr32(ExprValue *pe);
ST_FUNC void asm_opcode(TCCState *s1, int opcode);
ST_FUNC int asm_parse_regvar(int t);
ST_FUNC void asm_compute_constraints(ASMOperand *operands, int nb_operands, int nb_outputs, const uint8_t *clobber_regs, int *pout_reg);
ST_FUNC void subst_asm_operand(CString *add_str, SValue *sv, int modifier);
ST_FUNC void asm_gen_code(ASMOperand *operands, int nb_operands, int nb_outputs, int is_output, uint8_t *clobber_regs, int out_reg);
ST_FUNC void asm_clobber(uint8_t *clobber_regs, const char *str);
#endif

#define ST_ASM_SET 0x04

/* ------------ tccrun.c ----------------- */
#ifdef TCC_IS_NATIVE
#ifdef CONFIG_TCC_STATIC
#define RTLD_LAZY       0x001
#define RTLD_NOW        0x002
#define RTLD_GLOBAL     0x100
#define RTLD_DEFAULT    NULL
/* 供性能分析使用的桩函数 */
ST_FUNC void *dlopen(const char *filename, int flag);
ST_FUNC void dlclose(void *p);
ST_FUNC const char *dlerror(void);
ST_FUNC void *dlsym(void *handle, const char *symbol);
#endif
#ifdef CONFIG_TCC_BACKTRACE
ST_DATA int rt_num_callers;
ST_DATA const char **rt_bound_error_msg;
ST_DATA void *rt_prog_main;
ST_FUNC void tcc_set_num_callers(int n);
#endif
ST_FUNC void tcc_run_free(TCCState *s1);
#endif

/* ------------ tcctools.c ----------------- */
#if 0 /* 由 tcc.c 包含 */
ST_FUNC int tcc_tool_ar(TCCState *s, int argc, char **argv);
ST_FUNC void tcc_tool_cross(TCCState *s, char **argv, int option);
ST_FUNC void gen_makedeps(TCCState *s, const char *target, const char *filename);
#endif

/********************************************************/
#undef ST_DATA
#if ONE_SOURCE
#define ST_DATA static
#else
#define ST_DATA
#endif
/********************************************************/
#endif /* _TCC_H */
