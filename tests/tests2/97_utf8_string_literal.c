// 本文件包含以 UTF-8 编码的 BMP 字符
#include <stdio.h>
#include <wchar.h>

int main()
{
    wchar_t s[] = L"hello$$你好¢¢世界€€world";
    wchar_t *p;
    for (p = s; *p; p++) printf("%04X ", (unsigned) *p);
    printf("\n");
    return 0;
}
