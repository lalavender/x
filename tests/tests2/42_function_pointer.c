#include <stdio.h>

int fred(int p)
{
   printf("yo %d\n", p);
   return 42;
}

int (*f)(int) = &fred;

/* 要测试这里本该测试的内容，目标函数
   （这里是 fprint）就不能在测试中被直接调用。  */
int (*fprintfptr)(FILE *, const char *, ...) = &fprintf;

int main()
{
   fprintfptr(stdout, "%d\n", (*f)(24));

   return 0;
}

/* vim: set expandtab ts=4 sw=3 sts=3 tw=80 :*/
