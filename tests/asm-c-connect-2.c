#include <stdio.h>

#if defined _WIN32 && !defined __TINYC__
# define _ "_"
#else
# define _
#endif

int x3(void)
{
    printf(" x3");
    return 3;
}

/* callx4 被定义为全局的（相当于 ".globl callx4"）
   是 TCC 扩展。GCC 并非如此。  */
void callx4(void);
__asm__(_"callx4: call "_"x4; ret;"
#ifndef __TINYC__
    " .global "_"callx4"
#endif
);

extern void x5(void);

void callx5_again(void);
void callx5_again(void)
{
    x5();
    asm("call "_"x6");
}

static void x6()
{
    printf(" x6-2");
}
