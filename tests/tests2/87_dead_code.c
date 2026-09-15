/* 这里检查 if 语句内部死代码的各种情形，
   其中存在一些不明显的方式，使得这些代码实际上
   由于可被标签到达而并非死代码。  */
extern int printf (const char *, ...);
static void kb_wait_1(void)
{
  unsigned long timeout = 2;
  do {
      /* 这里的 else 分支是一个应当被抑制的语句表达式。
         while 内部的标签如果处理不当会重新
	 解除代码生成的抑制。而这会严重破坏
	 条件表达式，因为没有发出跳转绕过的代码，
	 整个语句表达式确实需要不生成代码
	 （也许除了无用的前向跳转）。  */
      (1 ? 
       printf("timeout=%ld\n", timeout) :
       ({
	int i = 1;
	while (1)
	  while (i--)
	    some_label:
	      printf("error\n");
	goto some_label;
	})
      );
      timeout--;
  } while (timeout);
}
int main (void)
{
  int i = 1;
  kb_wait_1();

  /* 简单的死代码测试，乍看是死代码，实际并非死代码。 */
  if (0) {
yeah:
      printf ("yeah\n");
  } else {
      printf ("boo\n");
  }
  if (i--)
    goto yeah;

  /* 更多不明显的情形，问题出在循环上，因此即使
     是第一个循环语句实际上也不是死代码。  */
  i = 1;
  if (0) {
      while (i--) {
	  printf ("once\n");
enterloop:
	  printf ("twice\n");
      }
  }
  if (i >= 0)
    goto enterloop;

  /* 语句表达式也有同样的情况。人们可能倾向于
     通过统计语句表达式内部的 if 来特殊处理它们，
     并因此完全不解除循环处的代码抑制。
     参见 kb_wait_1 中硬币的另一面，那样做并不可行。  */
  i = ({
      int j = 1;
      if (0) {
	  while (j--) {
	      printf ("SEonce\n");
    enterexprloop:
	      printf ("SEtwice\n");
	  }
      }
      if (j >= 0)
	goto enterexprloop;
      j; });

  /* 另外两种循环形式： */
  i = 1;
  if (0) {
      for (i = 1; i--;) {
	  printf ("once2\n");
enterloop2:
	  printf ("twice2\n");
      }
  }
  if (i > 0)
    goto enterloop2;

  i = 1;
  if (0) {
      do {
	  printf ("once3\n");
enterloop3:
	  printf ("twice3\n");
      } while (i--);
  }
  if (i > 0)
    goto enterloop3;

  /* 并检查 case 与 default 标签具有相同的
     禁用代码抑制的效果。  */
  i = 41;
  switch (i) {
      if (0) {
	  printf ("error\n");
      case 42:
	  printf ("error2\n");
      case 41:
	  printf ("caseok\n");
      }
  }

  i = 41;
  switch (i) {
      if (0) {
	  printf ("error3\n");
      default:
	  printf ("caseok2\n");
	  break;
      case 42:
	  printf ("error4\n");
      }
  }
  return 0;
}
