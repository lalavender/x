/*
 *  Tiny C 内存与边界检查器
 * 
 *  Copyright (c) 2002 Fabrice Bellard
 *
 * 本库为自由软件；你可以遵照自由软件基金会发布的 GNU 宽通用公共
 * 许可证（GNU Lesser General Public License）的条款重新分发和/或
 * 修改它，无论是许可证的第 2 版，还是（由你选择的）
 * 任何更新的版本。
 *
 * 分发本库是希望它有用，但不提供任何担保；
 * 甚至不提供对适销性或特定用途适用性的默示担保。
 * 详见 GNU 宽通用公共许可证。
 * 详见 GNU 宽通用公共许可证以了解更多细节。
 *
 * 你应当已经随本库收到一份 GNU 宽通用公共许可证的副本；
 * 如果没有，请写信给自由软件基金会：
 * 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 */
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

#if !defined(__FreeBSD__) \
 && !defined(__FreeBSD_kernel__) \
 && !defined(__DragonFly__) \
 && !defined(__OpenBSD__) \
 && !defined(__NetBSD__)
#include <malloc.h>
#endif

#if !defined(_WIN32)
#include <unistd.h>
#endif

/* #define BOUND_DEBUG */

#ifdef BOUND_DEBUG
 #define dprintf(a...) fprintf(a)
#else
 #define dprintf(a...)
#endif

/* 定义它可使边界数组为静态（更快，但不使用边界检查时
   仍占用内存） */
/* #define BOUND_STATIC */

/* 使用 malloc 钩子。目前若无钩子，本代码无法保证可靠 */
#define CONFIG_TCC_MALLOC_HOOKS
#define HAVE_MEMALIGN

#if defined(__FreeBSD__) \
 || defined(__FreeBSD_kernel__) \
 || defined(__DragonFly__) \
 || defined(__OpenBSD__) \
 || defined(__NetBSD__) \
 || defined(__dietlibc__) \
 || defined(_WIN32)
//#warning 边界检查在此环境中不支持 malloc（等函数）。
#undef CONFIG_TCC_MALLOC_HOOKS
#undef HAVE_MEMALIGN
#endif

#define BOUND_T1_BITS 13
#define BOUND_T2_BITS 11
#define BOUND_T3_BITS (sizeof(size_t)*8 - BOUND_T1_BITS - BOUND_T2_BITS)
#define BOUND_E_BITS  (sizeof(size_t))

#define BOUND_T1_SIZE ((size_t)1 << BOUND_T1_BITS)
#define BOUND_T2_SIZE ((size_t)1 << BOUND_T2_BITS)
#define BOUND_T3_SIZE ((size_t)1 << BOUND_T3_BITS)

#define BOUND_T23_BITS (BOUND_T2_BITS + BOUND_T3_BITS)
#define BOUND_T23_SIZE ((size_t)1 << BOUND_T23_BITS)


/* 当边界检查不正确时生成该指针 */
#define INVALID_POINTER ((void *)(-2))
/* 空区域的大小 */
#define EMPTY_SIZE  ((size_t)(-1))
/* 无效区域的大小 */
#define INVALID_SIZE      0

/*
 * BoundEntry —— 边界检查运行时登记的一块内存区域
 *
 * 编译时带 -b 会把每个指针解引用变成对 __bound_ptr_add/__bound_ptr_indir* 的调用，
 * 这些函数在本文件实现：它们在运行时用本结构的链表记录“哪块内存是合法的”。
 *   start      区域起始地址；
 *   size       区域字节数（EMPTY_SIZE/INVALID_SIZE 表示空区域/无效区域）；
 *   next       按地址排序的区域链表中下一项；
 *   is_invalid 为真表示越出该区域的指针一律视为无效（例如 malloc 返回的块，
 *              越界访问应当报错），而非仅仅是“未登记”。
 */
typedef struct BoundEntry {
    size_t start;
    size_t size;
    struct BoundEntry *next;
    size_t is_invalid; /* 若区域外的指针无效则为真 */
} BoundEntry;

/* 外部接口 */
void __bound_init(void);
void __bound_new_region(void *p, size_t size);
int __bound_delete_region(void *p);

#ifdef __attribute__
  /* 系统头文件中定义了 __attribute__ 宏 */
  #undef __attribute__ 
#endif
#define FASTCALL __attribute__((regparm(3)))

void *__bound_malloc(size_t size, const void *caller);
void *__bound_memalign(size_t size, size_t align, const void *caller);
void __bound_free(void *ptr, const void *caller);
void *__bound_realloc(void *ptr, size_t size, const void *caller);
static void *libc_malloc(size_t size);
static void libc_free(void *ptr);
static void install_malloc_hooks(void);
static void restore_malloc_hooks(void);

#ifdef CONFIG_TCC_MALLOC_HOOKS
static void *saved_malloc_hook;
static void *saved_free_hook;
static void *saved_realloc_hook;
static void *saved_memalign_hook;
#endif

/* TCC 定义 */
extern char __bounds_start; /* 静态边界表的起始位置 */
/* 错误消息，仅供 TCC 使用 */
const char *__bound_error_msg;

/* 运行时错误输出 */
extern void rt_error(size_t pc, const char *fmt, ...);

#ifdef BOUND_STATIC
static BoundEntry *__bound_t1[BOUND_T1_SIZE]; /* 页表 */
#else
static BoundEntry **__bound_t1; /* 页表 */
#endif
static BoundEntry *__bound_empty_t2;   /* 空页，用于未使用的页 */
static BoundEntry *__bound_invalid_t2; /* 无效页，用于无效指针 */

static BoundEntry *__bound_find_region(BoundEntry *e1, void *p)
{
    size_t addr, tmp;
    BoundEntry *e;

    e = e1;
    while (e != NULL) {
        addr = (size_t)p;
        addr -= e->start;
        if (addr <= e->size) {
            /* 把区域放到表头 */
            tmp = e1->start;
            e1->start = e->start;
            e->start = tmp;
            tmp = e1->size;
            e1->size = e->size;
            e->size = tmp;
            return e1;
        }
        e = e->next;
    }
    /* 未找到条目：返回空条目或无效条目 */
    if (e1->is_invalid)
        return __bound_invalid_t2;
    else
        return __bound_empty_t2;
}

/* 打印边界错误消息 */
static void bound_error(const char *fmt, ...)
{
    __bound_error_msg = fmt;
    fprintf(stderr,"%s %s: %s\n", __FILE__, __FUNCTION__, fmt);
    *(void **)0 = 0; /* 强制产生运行时错误 */
}

static void bound_alloc_error(void)
{
    bound_error("not enough memory for bound checking code");
}

/* 用于指针算术时返回 '(p + offset)'（这种情况下指针可以到达
   区域的末尾 */
void * FASTCALL __bound_ptr_add(void *p, size_t offset)
{
    size_t addr = (size_t)p;
    BoundEntry *e;

    dprintf(stderr, "%s %s: %p %x\n",
        __FILE__, __FUNCTION__, p, (unsigned)offset);

    __bound_init();

    e = __bound_t1[addr >> (BOUND_T2_BITS + BOUND_T3_BITS)];
    e = (BoundEntry *)((char *)e + 
                       ((addr >> (BOUND_T3_BITS - BOUND_E_BITS)) & 
                        ((BOUND_T2_SIZE - 1) << BOUND_E_BITS)));
    addr -= e->start;
    if (addr > e->size) {
        e = __bound_find_region(e, p);
        addr = (size_t)p - e->start;
    }
    addr += offset;
    if (addr >= e->size) {
	fprintf(stderr,"%s %s: %p is outside of the region\n",
            __FILE__, __FUNCTION__, p + offset);
        return INVALID_POINTER; /* 返回一个无效指针 */
    }
    return p + offset;
}

/* 用于指针间接访问时返回 '(p + offset)'（结果必须
   严格位于区域内部 */
#define BOUND_PTR_INDIR(dsize)                                          \
void * FASTCALL __bound_ptr_indir ## dsize (void *p, size_t offset)     \
{                                                                       \
    size_t addr = (size_t)p;                                            \
    BoundEntry *e;                                                      \
                                                                        \
    dprintf(stderr, "%s %s: %p %x start\n",                             \
        __FILE__, __FUNCTION__, p, (unsigned)offset);	                \
									\
    __bound_init();							\
    e = __bound_t1[addr >> (BOUND_T2_BITS + BOUND_T3_BITS)];            \
    e = (BoundEntry *)((char *)e +                                      \
                       ((addr >> (BOUND_T3_BITS - BOUND_E_BITS)) &      \
                        ((BOUND_T2_SIZE - 1) << BOUND_E_BITS)));        \
    addr -= e->start;                                                   \
    if (addr > e->size) {                                               \
        e = __bound_find_region(e, p);                                  \
        addr = (size_t)p - e->start;                                    \
    }                                                                   \
    addr += offset + dsize;                                             \
    if (addr > e->size) {                                               \
	fprintf(stderr,"%s %s: %p is outside of the region\n",          \
            __FILE__, __FUNCTION__, p + offset);                        \
        return INVALID_POINTER; /* 返回一个无效指针 */                  \
    }									\
    dprintf(stderr, "%s %s: return p+offset = %p\n",                    \
        __FILE__, __FUNCTION__, p + offset);                            \
    return p + offset;                                                  \
}

BOUND_PTR_INDIR(1)
BOUND_PTR_INDIR(2)
BOUND_PTR_INDIR(4)
BOUND_PTR_INDIR(8)
BOUND_PTR_INDIR(12)
BOUND_PTR_INDIR(16)

#if defined(__GNUC__) && (__GNUC__ >= 6)
/*
 * 至少 gcc 6.2 在使用非零参数的 __builtin_frame_address 时会报错。
 *
 */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wframe-address"
#endif

/* 返回调用者的帧指针 */
#define GET_CALLER_FP(fp)\
{\
    fp = (size_t)__builtin_frame_address(1);\
}

/* 进入函数时调用，用于添加所有局部区域 */
void FASTCALL __bound_local_new(void *p1) 
{
    size_t addr, size, fp, *p = p1;

    dprintf(stderr, "%s, %s start p1=%p\n", __FILE__, __FUNCTION__, p);
    GET_CALLER_FP(fp);
    for(;;) {
        addr = p[0];
        if (addr == 0)
            break;
        addr += fp;
        size = p[1];
        p += 2;
        __bound_new_region((void *)addr, size);
    }
    dprintf(stderr, "%s, %s end\n", __FILE__, __FUNCTION__);
}

/* 离开函数时调用，用于删除所有局部区域 */
void FASTCALL __bound_local_delete(void *p1) 
{
    size_t addr, fp, *p = p1;
    GET_CALLER_FP(fp);
    for(;;) {
        addr = p[0];
        if (addr == 0)
            break;
        addr += fp;
        p += 2;
        __bound_delete_region((void *)addr);
    }
}

#if defined(__GNUC__) && (__GNUC__ >= 6)
#pragma GCC diagnostic pop
#endif

static BoundEntry *__bound_new_page(void)
{
    BoundEntry *page;
    size_t i;

    page = libc_malloc(sizeof(BoundEntry) * BOUND_T2_SIZE);
    if (!page)
        bound_alloc_error();
    for(i=0;i<BOUND_T2_SIZE;i++) {
        /* 放入空条目 */
        page[i].start = 0;
        page[i].size = EMPTY_SIZE;
        page[i].next = NULL;
        page[i].is_invalid = 0;
    }
    return page;
}

/* 目前我们使用 malloc()。应当使用 bound_new_page() */
static BoundEntry *bound_new_entry(void)
{
    BoundEntry *e;
    e = libc_malloc(sizeof(BoundEntry));
    return e;
}

static void bound_free_entry(BoundEntry *e)
{
    libc_free(e);
}

static BoundEntry *get_page(size_t index)
{
    BoundEntry *page;
    page = __bound_t1[index];
    if (!page || page == __bound_empty_t2 || page == __bound_invalid_t2) {
        /* 必要时新建一页 */
        page = __bound_new_page();
        __bound_t1[index] = page;
    }
    return page;
}

/* 把区域标记为无效（只能在初始化期间使用） */
static void mark_invalid(size_t addr, size_t size)
{
    size_t start, end;
    BoundEntry *page;
    size_t t1_start, t1_end, i, j, t2_start, t2_end;

    start = addr;
    end = addr + size;

    t2_start = (start + BOUND_T3_SIZE - 1) >> BOUND_T3_BITS;
    if (end != 0)
        t2_end = end >> BOUND_T3_BITS;
    else
        t2_end = 1 << (BOUND_T1_BITS + BOUND_T2_BITS);

#if 0
    dprintf(stderr, "mark_invalid: start = %x %x\n", t2_start, t2_end);
#endif
    
    /* 先处理整页 */
    t1_start = (t2_start + BOUND_T2_SIZE - 1) >> BOUND_T2_BITS;
    t1_end = t2_end >> BOUND_T2_BITS;

    i = t2_start & (BOUND_T2_SIZE - 1);
    j = t2_end & (BOUND_T2_SIZE - 1);
    
    if (t1_start == t1_end) {
        page = get_page(t2_start >> BOUND_T2_BITS);
        for(; i < j; i++) {
            page[i].size = INVALID_SIZE;
            page[i].is_invalid = 1;
        }
    } else {
        if (i > 0) {
            page = get_page(t2_start >> BOUND_T2_BITS);
            for(; i < BOUND_T2_SIZE; i++) {
                page[i].size = INVALID_SIZE;
                page[i].is_invalid = 1;
            }
        }
        for(i = t1_start; i < t1_end; i++) {
            __bound_t1[i] = __bound_invalid_t2;
        }
        if (j != 0) {
            page = get_page(t1_end);
            for(i = 0; i < j; i++) {
                page[i].size = INVALID_SIZE;
                page[i].is_invalid = 1;
            }
        }
    }
}

void __bound_init(void)
{
    size_t i;
    BoundEntry *page;
    size_t start, size;
    size_t *p;

    static int inited;
    if (inited)
	return;

    inited = 1;

    dprintf(stderr, "%s, %s() start\n", __FILE__, __FUNCTION__);

    /* 保存 malloc 钩子并安装边界检查钩子 */
    install_malloc_hooks();

#ifndef BOUND_STATIC
    __bound_t1 = libc_malloc(BOUND_T1_SIZE * sizeof(BoundEntry *));
    if (!__bound_t1)
        bound_alloc_error();
#endif
    __bound_empty_t2 = __bound_new_page();
    for(i=0;i<BOUND_T1_SIZE;i++) {
        __bound_t1[i] = __bound_empty_t2;
    }

    page = __bound_new_page();
    for(i=0;i<BOUND_T2_SIZE;i++) {
        /* 放入无效条目 */
        page[i].start = 0;
        page[i].size = INVALID_SIZE;
        page[i].next = NULL;
        page[i].is_invalid = 1;
    }
    __bound_invalid_t2 = page;

    /* 无效指针区 */
    start = (size_t)INVALID_POINTER & ~(BOUND_T23_SIZE - 1);
    size = BOUND_T23_SIZE;
    mark_invalid(start, size);

#if defined(CONFIG_TCC_MALLOC_HOOKS)
    /* malloc 区也被标记为无效。只能配合
     * 钩子使用，因为所有库都应使用同一个 malloc。
     * 解决办法是为 tcc 构建一个新的 malloc。
     *
     * 通常堆（= malloc 区）紧跟在 bss 之后，即 _end 之后，但
     * 并不总是如此——无论是运行在 `tcc -b -run` 之下，还是
     * 开启了地址空间随机化(a)，堆起始位置都会与 bss 末尾分开。
     *
     * 所以 sbrk(0) 是 start_brk 的良好近似：
     *
     *   - 如果我们是一个单独编译的程序，__bound_init() 运行得很早，
     *     此时 sbrk(0) 应等于或非常接近 start_brk(b)（若其他
     *     构造函数分配了内存则不然），或者
     *
     *   - 如果我们运行在 `tcc -b -run` 之下，sbrk(0) 将返回
     *     受本程序控制的堆部分的起始位置，而不会把更早分配的
     *     内存标记为无效。
     *
     *
     * (a) Linux 上为 /proc/sys/kernel/randomize_va_space = 2；
     *     通常默认开启。
     *
     * (b) 在 Linux >= v3.3 上，替代做法是从 /proc/self/stat
     *     读取 start_brk
     *
     */
    start = (size_t)sbrk(0);
    size = 128 * 0x100000;
    mark_invalid(start, size);
#endif

    /* 添加所有静态边界检查值 */
    p = (size_t *)&__bounds_start;
    while (p[0] != 0) {
        __bound_new_region((void *)p[0], p[1]);
        p += 2;
    }

    dprintf(stderr, "%s, %s() end\n\n", __FILE__, __FUNCTION__);
}

void __bound_main_arg(void **p)
{
    void *start = p;
    while (*p++);

    dprintf(stderr, "%s, %s calling __bound_new_region(%p %x)\n",
            __FILE__, __FUNCTION__, start, (unsigned)((void *)p - start));

    __bound_new_region(start, (void *) p - start);
}

void __bound_exit(void)
{
    dprintf(stderr, "%s, %s()\n", __FILE__, __FUNCTION__);
    restore_malloc_hooks();
}

static inline void add_region(BoundEntry *e, 
                              size_t start, size_t size)
{
    BoundEntry *e1;
    if (e->start == 0) {
        /* 没有区域：添加它 */
        e->start = start;
        e->size = size;
    } else {
        /* 列表中已有区域：把它加到表头 */
        e1 = bound_new_entry();
        e1->start = e->start;
        e1->size = e->size;
        e1->next = e->next;
        e->start = start;
        e->size = size;
        e->next = e1;
    }
}

/* 新建一个区域。它不应已存在于区域列表中 */
void __bound_new_region(void *p, size_t size)
{
    size_t start, end;
    BoundEntry *page, *e, *e2;
    size_t t1_start, t1_end, i, t2_start, t2_end;

    dprintf(stderr, "%s, %s(%p, %x) start\n",
        __FILE__, __FUNCTION__, p, (unsigned)size);

    __bound_init();

    start = (size_t)p;
    end = start + size;
    t1_start = start >> (BOUND_T2_BITS + BOUND_T3_BITS);
    t1_end = end >> (BOUND_T2_BITS + BOUND_T3_BITS);

    /* 起始 */
    page = get_page(t1_start);
    t2_start = (start >> (BOUND_T3_BITS - BOUND_E_BITS)) & 
        ((BOUND_T2_SIZE - 1) << BOUND_E_BITS);
    t2_end = (end >> (BOUND_T3_BITS - BOUND_E_BITS)) & 
        ((BOUND_T2_SIZE - 1) << BOUND_E_BITS);


    e = (BoundEntry *)((char *)page + t2_start);
    add_region(e, start, size);

    if (t1_end == t1_start) {
        /* 结束页相同 */
        e2 = (BoundEntry *)((char *)page + t2_end);
        if (e2 > e) {
            e++;
            for(;e<e2;e++) {
                e->start = start;
                e->size = size;
            }
            add_region(e, start, size);
        }
    } else {
        /* 标记到页尾 */
        e2 = page + BOUND_T2_SIZE;
        e++;
        for(;e<e2;e++) {
            e->start = start;
            e->size = size;
        }
        /* 标记中间的各页（如果有） */
        for(i=t1_start+1;i<t1_end;i++) {
            page = get_page(i);
            e2 = page + BOUND_T2_SIZE;
            for(e=page;e<e2;e++) {
                e->start = start;
                e->size = size;
            }
        }
        /* 最后一页 */
        page = get_page(t1_end);
        e2 = (BoundEntry *)((char *)page + t2_end);
        for(e=page;e<e2;e++) {
            e->start = start;
            e->size = size;
        }
        add_region(e, start, size);
    }

    dprintf(stderr, "%s, %s end\n", __FILE__, __FUNCTION__);
}

/* 删除一个区域 */
static inline void delete_region(BoundEntry *e, void *p, size_t empty_size)
{
    size_t addr;
    BoundEntry *e1;

    addr = (size_t)p;
    addr -= e->start;
    if (addr <= e->size) {
        /* 找到的区域是第一个 */
        e1 = e->next;
        if (e1 == NULL) {
            /* 没有更多区域：把它标记为空 */
            e->start = 0;
            e->size = empty_size;
        } else {
            /* 把下一个区域复制到表头 */
            e->start = e1->start;
            e->size = e1->size;
            e->next = e1->next;
            bound_free_entry(e1);
        }
    } else {
        /* 查找匹配的区域 */
        for(;;) {
            e1 = e;
            e = e->next;
            /* 未找到区域：什么都不做 */
            if (e == NULL)
                break;
            addr = (size_t)p - e->start;
            if (addr <= e->size) {
                /* 已找到：删除条目 */
                e1->next = e->next;
                bound_free_entry(e);
                break;
            }
        }
    }
}

/* 警告：'p' 必须是该区域的起始位置。 */
/* 出错时返回非零 */
int __bound_delete_region(void *p)
{
    size_t start, end, addr, size, empty_size;
    BoundEntry *page, *e, *e2;
    size_t t1_start, t1_end, t2_start, t2_end, i;

    dprintf(stderr, "%s %s() start\n", __FILE__, __FUNCTION__);

    __bound_init();

    start = (size_t)p;
    t1_start = start >> (BOUND_T2_BITS + BOUND_T3_BITS);
    t2_start = (start >> (BOUND_T3_BITS - BOUND_E_BITS)) & 
        ((BOUND_T2_SIZE - 1) << BOUND_E_BITS);
    
    /* 查找区域大小 */
    page = __bound_t1[t1_start];
    e = (BoundEntry *)((char *)page + t2_start);
    addr = start - e->start;
    if (addr > e->size)
        e = __bound_find_region(e, p);
    /* 测试是否为无效区域 */
    if (e->size == EMPTY_SIZE || (size_t)p != e->start) 
        return -1;
    /* 计算我们填入无效区域的大小 */
    if (e->is_invalid)
        empty_size = INVALID_SIZE;
    else
        empty_size = EMPTY_SIZE;
    size = e->size;
    end = start + size;

    /* 现在可以释放每个条目 */
    t1_end = end >> (BOUND_T2_BITS + BOUND_T3_BITS);
    t2_end = (end >> (BOUND_T3_BITS - BOUND_E_BITS)) & 
        ((BOUND_T2_SIZE - 1) << BOUND_E_BITS);

    delete_region(e, p, empty_size);
    if (t1_end == t1_start) {
        /* 结束页相同 */
        e2 = (BoundEntry *)((char *)page + t2_end);
        if (e2 > e) {
            e++;
            for(;e<e2;e++) {
                e->start = 0;
                e->size = empty_size;
            }
            delete_region(e, p, empty_size);
        }
    } else {
        /* 标记到页尾 */
        e2 = page + BOUND_T2_SIZE;
        e++;
        for(;e<e2;e++) {
            e->start = 0;
            e->size = empty_size;
        }
        /* 标记中间的各页（如果有） */
        /* XXX：应当释放它们 */
        for(i=t1_start+1;i<t1_end;i++) {
            page = get_page(i);
            e2 = page + BOUND_T2_SIZE;
            for(e=page;e<e2;e++) {
                e->start = 0;
                e->size = empty_size;
            }
        }
        /* 最后一页 */
        page = get_page(t1_end);
        e2 = (BoundEntry *)((char *)page + t2_end);
        for(e=page;e<e2;e++) {
            e->start = 0;
            e->size = empty_size;
        }
        delete_region(e, p, empty_size);
    }

    dprintf(stderr, "%s %s() end\n", __FILE__, __FUNCTION__);

    return 0;
}

/* 返回从 p 开始的区域的大小；若区域不存在则返回
   EMPTY_SIZE。 */
static size_t get_region_size(void *p)
{
    size_t addr = (size_t)p;
    BoundEntry *e;

    e = __bound_t1[addr >> (BOUND_T2_BITS + BOUND_T3_BITS)];
    e = (BoundEntry *)((char *)e + 
                       ((addr >> (BOUND_T3_BITS - BOUND_E_BITS)) & 
                        ((BOUND_T2_SIZE - 1) << BOUND_E_BITS)));
    addr -= e->start;
    if (addr > e->size)
        e = __bound_find_region(e, p);
    if (e->start != (size_t)p)
        return EMPTY_SIZE;
    return e->size;
}

/* 被替换的内存函数 */

/* 强制编译器完成到此为止已编码的存储操作 */
#define barrier()   __asm__ __volatile__ ("": : : "memory")

static void install_malloc_hooks(void)
{
#ifdef CONFIG_TCC_MALLOC_HOOKS
    saved_malloc_hook = __malloc_hook;
    saved_free_hook = __free_hook;
    saved_realloc_hook = __realloc_hook;
    saved_memalign_hook = __memalign_hook;
    __malloc_hook = __bound_malloc;
    __free_hook = __bound_free;
    __realloc_hook = __bound_realloc;
    __memalign_hook = __bound_memalign;

    barrier();
#endif
}

static void restore_malloc_hooks(void)
{
#ifdef CONFIG_TCC_MALLOC_HOOKS
    __malloc_hook = saved_malloc_hook;
    __free_hook = saved_free_hook;
    __realloc_hook = saved_realloc_hook;
    __memalign_hook = saved_memalign_hook;

    barrier();
#endif
}

static void *libc_malloc(size_t size)
{
    void *ptr;
    restore_malloc_hooks();
    ptr = malloc(size);
    install_malloc_hooks();
    return ptr;
}

static void libc_free(void *ptr)
{
    restore_malloc_hooks();
    free(ptr);
    install_malloc_hooks();
}

/* XXX：我们应该使用一种 malloc，它能保证在中间有 'free' 发生时，
   两块 malloc 出来的数据不太可能具有相同地址，
   或在中间释放后重新分配时具有相同地址。 */
void *__bound_malloc(size_t size, const void *caller)
{
    void *ptr;
    
    /* 我们多分配一个字节，以确保各区域之间至少相隔
       一个字节。使用 glibc 的 malloc 时，这实际上
       可能并不必要 */
    ptr = libc_malloc(size + 1);
    
    if (!ptr)
        return NULL;

    dprintf(stderr, "%s, %s calling __bound_new_region(%p, %x)\n",
           __FILE__, __FUNCTION__, ptr, (unsigned)size);

    __bound_new_region(ptr, size);
    return ptr;
}

void *__bound_memalign(size_t size, size_t align, const void *caller)
{
    void *ptr;

    restore_malloc_hooks();

#ifndef HAVE_MEMALIGN
    if (align > 4) {
        /* XXX：要处理它吗？ */
        ptr = NULL;
    } else {
        /* 我们假定 malloc 至少按四字节对齐 */
        ptr = malloc(size + 1);
    }
#else
    /* 我们多分配一个字节，以确保各区域之间至少相隔
       一个字节。使用 glibc 的 malloc 时，这实际上
       可能并不必要 */
    ptr = memalign(size + 1, align);
#endif
    
    install_malloc_hooks();
    
    if (!ptr)
        return NULL;

    dprintf(stderr, "%s, %s calling __bound_new_region(%p, %x)\n",
           __FILE__, __FUNCTION__, ptr, (unsigned)size);

    __bound_new_region(ptr, size);
    return ptr;
}

void __bound_free(void *ptr, const void *caller)
{
    if (ptr == NULL)
        return;
    if (__bound_delete_region(ptr) != 0)
        bound_error("freeing invalid region");

    libc_free(ptr);
}

void *__bound_realloc(void *ptr, size_t size, const void *caller)
{
    void *ptr1;
    size_t old_size;

    if (size == 0) {
        __bound_free(ptr, caller);
        return NULL;
    } else {
        ptr1 = __bound_malloc(size, caller);
        if (ptr == NULL || ptr1 == NULL)
            return ptr1;
        old_size = get_region_size(ptr);
        if (old_size == EMPTY_SIZE)
            bound_error("realloc'ing invalid pointer");
        memcpy(ptr1, ptr, old_size);
        __bound_free(ptr, caller);
        return ptr1;
    }
}

#ifndef CONFIG_TCC_MALLOC_HOOKS
void *__bound_calloc(size_t nmemb, size_t size)
{
    void *ptr;
    size = size * nmemb;
    ptr = __bound_malloc(size, NULL);
    if (!ptr)
        return NULL;
    memset(ptr, 0, size);
    return ptr;
}
#endif

#if 0
static void bound_dump(void)
{
    BoundEntry *page, *e;
    size_t i, j;

    fprintf(stderr, "region dump:\n");
    for(i=0;i<BOUND_T1_SIZE;i++) {
        page = __bound_t1[i];
        for(j=0;j<BOUND_T2_SIZE;j++) {
            e = page + j;
            /* 不打印无效或空的条目 */
            if (e->size != EMPTY_SIZE && e->start != 0) {
                fprintf(stderr, "%08x:", 
                       (i << (BOUND_T2_BITS + BOUND_T3_BITS)) + 
                       (j << BOUND_T3_BITS));
                do {
                    fprintf(stderr, " %08lx:%08lx", e->start, e->start + e->size);
                    e = e->next;
                } while (e != NULL);
                fprintf(stderr, "\n");
            }
        }
    }
}
#endif

/* 一些有用的带检查的函数 */

/* 检查 (p ... p + size - 1) 是否位于 'p' 区域内部（若存在） */
static void __bound_check(const void *p, size_t size)
{
    if (size == 0)
        return;
    p = __bound_ptr_add((void *)p, size - 1);
    if (p == INVALID_POINTER)
        bound_error("invalid pointer");
}

void *__bound_memcpy(void *dst, const void *src, size_t size)
{
    void* p;

    dprintf(stderr, "%s %s: start, dst=%p src=%p size=%x\n",
            __FILE__, __FUNCTION__, dst, src, (unsigned)size);

    __bound_check(dst, size);
    __bound_check(src, size);
    /* 还要检查区域重叠 */
    if (src >= dst && src < dst + size)
        bound_error("overlapping regions in memcpy()");

    p = memcpy(dst, src, size);

    dprintf(stderr, "%s %s: end, p=%p\n", __FILE__, __FUNCTION__, p);
    return p;
}

void *__bound_memmove(void *dst, const void *src, size_t size)
{
    __bound_check(dst, size);
    __bound_check(src, size);
    return memmove(dst, src, size);
}

void *__bound_memset(void *dst, int c, size_t size)
{
    __bound_check(dst, size);
    return memset(dst, c, size);
}

/* XXX：可以优化 */
int __bound_strlen(const char *s)
{
    const char *p;
    size_t len;

    len = 0;
    for(;;) {
        p = __bound_ptr_indir1((char *)s, len);
        if (p == INVALID_POINTER)
            bound_error("bad pointer in strlen()");
        if (*p == '\0')
            break;
        len++;
    }
    return len;
}

char *__bound_strcpy(char *dst, const char *src)
{
    size_t len;
    void *p;

    dprintf(stderr, "%s %s: strcpy start, dst=%p src=%p\n",
            __FILE__, __FUNCTION__, dst, src);
    len = __bound_strlen(src);
    p = __bound_memcpy(dst, src, len + 1);
    dprintf(stderr, "%s %s: strcpy end, p = %p\n",
            __FILE__, __FUNCTION__, p);
    return p;
}
