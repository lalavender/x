/*
 * libtcc 的简单测试程序
 *
 * libtcc 可用作代码生成器的“后端”。
 */
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#include "libtcc.h"

/* 此函数由生成的代码调用 */
int add(int a, int b)
{
    return a + b;
}

/* 此字符串被生成的代码引用 */
const char hello[] = "Hello World!";

char my_program[] =
"#include <tcclib.h>\n" /* 包含“TCC 的简单 libc 头文件” */
"extern int add(int a, int b);\n"
"#ifdef _WIN32\n" /* 动态链接的数据需要 'dllimport' */
" __attribute__((dllimport))\n"
"#endif\n"
"extern const char hello[];\n"
"int fib(int n)\n"
"{\n"
"    if (n <= 2)\n"
"        return 1;\n"
"    else\n"
"        return fib(n-1) + fib(n-2);\n"
"}\n"
"\n"
"int foo(int n)\n"
"{\n"
"    printf(\"%s\\n\", hello);\n"
"    printf(\"fib(%d) = %d\\n\", n, fib(n));\n"
"    printf(\"add(%d, %d) = %d\\n\", n, 2 * n, add(n, 2 * n));\n"
"    return 0;\n"
"}\n";

int main(int argc, char **argv)
{
    TCCState *s;
    int i;
    int (*func)(int);

    s = tcc_new();
    if (!s) {
        fprintf(stderr, "Could not create tcc state\n");
        exit(1);
    }

    /* 如果 tcclib.h 和 libtcc1.a 未安装，我们在哪里可以找到它们 */
    for (i = 1; i < argc; ++i) {
        char *a = argv[i];
        if (a[0] == '-') {
            if (a[1] == 'B')
                tcc_set_lib_path(s, a+2);
            else if (a[1] == 'I')
                tcc_add_include_path(s, a+2);
            else if (a[1] == 'L')
                tcc_add_library_path(s, a+2);
        }
    }

    /* 必须在任何编译之前调用 */
    tcc_set_output_type(s, TCC_OUTPUT_MEMORY);

    if (tcc_compile_string(s, my_program) == -1)
        return 1;

    /* 作为测试，我们添加编译后的程序可以使用的符号。
       你也可以用 tcc_add_dll() 打开一个 dll 并使用其中的符号 */
    tcc_add_symbol(s, "add", add);
    tcc_add_symbol(s, "hello", hello);

    /* 重定位代码 */
    if (tcc_relocate(s, TCC_RELOCATE_AUTO) < 0)
        return 1;

    /* 获取入口符号 */
    func = tcc_get_symbol(s, "foo");
    if (!func)
        return 1;

    /* 运行代码 */
    func(32);

    /* 删除状态 */
    tcc_delete(s);

    return 0;
}
