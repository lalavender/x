/*****************************************************************************/
/* 测试 'nodata_wanted' 数据输出抑制 */

#if defined test_static_data_error
void foo() {
    if (1) {
	static short w = (int)&foo; /* 初始化器不可计算 */
    }
}

#elif defined test_static_nodata_error
void foo() {
    if (0) {
	static short w = (int)&foo; /* 初始化器不可计算 */
    }
}

#elif defined test_global_data_error
void foo();
static short w = (int)&foo; /* 初始化器不可计算 */


#elif defined test_local_data_noerror
void foo() {
    short w = &foo; /* 2 个强制转换警告 */
}

#elif defined test_data_suppression_off || defined test_data_suppression_on

#if defined test_data_suppression_on
# define SKIP 1
#else
# define SKIP 0
#endif

#include <stdio.h>
/* 某些 gcc 头文件在非 gcc 下把 __attribute__ 定义为空 */
#undef __attribute__

int main()
{
    __label__ ts0, te0, ts1, te1;
    int tl, dl;

    static char ds0 = 0;
    static char de0 = 0;
    /* 获取空 jmp 的参考大小 */
ts0:;
    if (!SKIP) {}
te0:;
    dl = -(&de0 - &ds0);
    tl = -(&&te0 - &&ts0);

    /* 测试数据与代码抑制 */
    static char ds1 = 0;
ts1:;
    if (!SKIP) {
        static void *p = (void*)&main;
        static char cc[] = "static string";
        static double d = 8.0;

        static struct __attribute__((packed)) {
            unsigned x : 12;
            unsigned char y : 7;
            unsigned z : 28, a: 4, b: 5;
        } s = { 0x333,0x44,0x555555,6,7 };

        printf("data:\n");
        printf("  %d - %.1f - %.1f - %s - %s\n",
            sizeof 8.0, 8.0, d, __FUNCTION__, cc);
        printf("  %x %x %x %x %x\n",
            s.x, s.y, s.z, s.a, s.b);
    }
te1:;
    static char de1 = 0;

    dl += &de1 - &ds1;
    tl += &&te1 - &&ts1;
    printf("size of data/text:\n  %s/%s\n",
        dl ? "non-zero":"zero", tl ? "non-zero":"zero");
    /*printf("# %d/%d\n", dl, tl);*/
}

#endif
