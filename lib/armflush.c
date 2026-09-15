/* armflush.c - 刷新指令缓存

   __clear_cache 在 tccrun.c 中使用。它是 gcc 的内建
   函数。但 tcc 为了编译
   自身需要这个函数 */

#ifdef __TINYC__

/* 系统调用包装 */
unsigned syscall(unsigned syscall_nr, ...);

/* arm-tcc 目前只支持伪汇编 */
__asm__(
    ".global syscall\n"
    "syscall:\n"
    ".int 0xe92d4080\n"  // push    {r7, lr}
    ".int 0xe1a07000\n"  // mov     r7, r0
    ".int 0xe1a00001\n"  // mov     r0, r1
    ".int 0xe1a01002\n"  // mov     r1, r2
    ".int 0xe1a02003\n"  // mov     r2, r3
    ".int 0xef000000\n"  // svc     0x00000000
    ".int 0xe8bd8080\n"  // pop     {r7, pc}
    );

/* 来自 unistd.h： */
#if defined(__thumb__) || defined(__ARM_EABI__)
# define __NR_SYSCALL_BASE      0x0
#else
# define __NR_SYSCALL_BASE      0x900000
#endif
#define __ARM_NR_BASE           (__NR_SYSCALL_BASE+0x0f0000)
#define __ARM_NR_cacheflush     (__ARM_NR_BASE+2)

#else

#define _GNU_SOURCE
#include <unistd.h>
#include <sys/syscall.h>
#include <stdio.h>

#endif

/* 供 tccrun 使用的刷新 */
void __clear_cache(void *beginning, void *end)
{
/* __ARM_NR_cacheflush 是内核私有的，不应在用户空间使用。
 * 但是 tcc 中没有 ARM 汇编解析器，所以目前我们使用它 */
#if 1
    syscall(__ARM_NR_cacheflush, beginning, end, 0);
#else
    __asm__ ("push {r7}\n\t"
             "mov r7, #0xf0002\n\t"
             "mov r2, #0\n\t"
             "swi 0\n\t"
             "pop {r7}\n\t"
             "ret");
#endif
}
