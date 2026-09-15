#include <stdio.h>

enum fred
{
   a,
   b,
   c,
   d,
   e = 54,
   f = 73,
   g,
   h
};

/* 以下所有对 enum efoo 的使用都应能编译
   通过而不产生警告。虽然前向枚举不是 ISO C，
   但 GCC 在严格模式下也接受它，仅在使用
   -pedantic 时给出警告。这在实际中确实会发生。  */
/* 严格的 ISO C 不允许这种枚举的前向声明，
   但 GCC 接受它（只给出 pedantic 警告），并且
   这种情况在现实中确实存在。  */
enum efoo;
struct Sforward_use {
    int (*fmember) (enum efoo x);
};

extern enum efoo it_real_fn(void);
enum efoo {
  ONE,
  TWO,
};
struct S2 {
  enum efoo (*f2) (void);
};
void should_compile(struct S2 *s)
{
  s->f2 = it_real_fn;
}

enum efoo it_real_fn(void)
{
  return TWO;
}

static unsigned int deref_uintptr(unsigned int *p)
{
  return *p;
}

enum Epositive {
    epos_one, epos_two
};

int main()
{
   enum fred frod;
   enum Epositive epos = epos_two;

   printf("%d %d %d %d %d %d %d %d\n", a, b, c, d, e, f, g, h);
   /* printf("%d\n", frod); */
   frod = 12;
   printf("%d\n", frod);
   frod = e;
   printf("%d\n", frod);

   /* 以下代码应能编译通过而不产生警告。  */
   printf ("enum to int: %u\n", deref_uintptr(&epos));

   return 0;
}

/* vim: set expandtab ts=4 sw=3 sts=3 tw=80 :*/
