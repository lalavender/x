#include <stdio.h>

int main()
{
    /* 不得影响 #pragma ppop_macro 的工作方式 */
    #define pop_macro foobar1

    /* 不得影响 #pragma push_macro 的工作方式 */
    #define push_macro foobar2

    #undef abort
    #define abort "111"
    printf("abort = %s\n", abort);

    #pragma push_macro("abort")
    #undef abort
    #define abort "222"
    printf("abort = %s\n", abort);

    #pragma push_macro("abort")
    #undef abort
    #define abort "333"
    printf("abort = %s\n", abort);

    #pragma pop_macro("abort")
    printf("abort = %s\n", abort);

    #pragma pop_macro("abort")
    printf("abort = %s\n", abort);
}
