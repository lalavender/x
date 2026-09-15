/* 示例来自 http://barnyard.syr.edu/quickies/led.c */

/* led.c：像在 7 行 LED 显示器上一样打印数字。也就是说，把命令行上给出的
   整数写成这样：  
      _   _       _  
   |  _|  _| |_| |_  
   | |_   _|   |  _| etc.

   我们假设终端的行为像经典的电传打字机。所以必须先打印所有数字的顶部
   行，再打印所有数字的中间行，依此类推。


   作者 Terry R. McConnell

编译：cc -o led led.c

如果你只想链接完成全部工作的子程序 print_led，就用 -DNO_MAIN 编译，
并在任何用到该调用的源文件中声明如下内容：

extern void print_led(unsigned long x, char *buf);


缺陷：无法重复调用来把多个数字打印到同一行。那需要 curses 或其他允许把
光标移到上一行的终端 API。


*/



#include <stdlib.h>
#include <stdio.h>

#define MAX_DIGITS 32
#define NO_MAIN


/* 把数字 d 的顶部行打印到 buffer 中。 
   不会在 buffer 末尾加空字符终止。 */

void topline(int d, char *p){

   *p++ = ' ';
   switch(d){

      /* 这些数字的顶部行都有 _ */

      case 0:
      case 2:
      case 3:
      case 5:
      case 7:
      case 8:
      case 9:
         *p++ = '_';
         break;
      default:
         *p++=' ';

   }
   *p++=' ';
}

/* 把数字 d 的中间行打印到 buffer 中。 
   不会在末尾加空字符终止。 */

void midline(int d, char *p){

   switch(d){

      /* 中间行开头为 | 的那些数字 */

      case 0:
      case 4:
      case 5:
      case 6:
      case 8:
      case 9:
         *p++='|';
         break;
      default:
         *p++=' ';	
   }
   switch(d){

      /* 中间行有 _ 的那些数字 */

      case 2:
      case 3:
      case 4:
      case 5:
      case 6:
      case 8:
      case 9:
         *p++='_';
         break;
      default:
         *p++=' ';

   }
   switch(d){

      /* 中间行结尾为 | 的那些数字 */

      case 0:
      case 1:
      case 2:
      case 3:
      case 4:
      case 7:
      case 8:
      case 9:
         *p++='|';
         break;
      default:
         *p++=' ';

   }
}

/* 打印数字 d 的底部行。不会在末尾加空字符终止。 */

void botline(int d, char *p){


   switch(d){

      /* 底部行开头为 | 的那些数字 */

      case 0:
      case 2:
      case 6:
      case 8:
         *p++='|';
         break;
      default:
         *p++=' ';	
   }
   switch(d){

      /* 底部行有 _ 的那些数字 */

      case 0:
      case 2:
      case 3:
      case 5:
      case 6:
      case 8:
         *p++='_';
         break;
      default:
         *p++=' ';

   }
   switch(d){

      /* 底部行结尾为 | 的那些数字 */

      case 0:
      case 1:
      case 3:
      case 4:
      case 5:
      case 6:
      case 7:
      case 8:
      case 9:
         *p++='|';
         break;
      default:
         *p++=' ';

   }
}

/* 把整数的 led 表示写入字符串 buffer。 */

void print_led(unsigned long x, char *buf)
{

   int i=0,n;
   static int d[MAX_DIGITS];


   /* 从 x 中取出各位数字 */

   n = ( x == 0L ? 1 : 0 );  /* 0 也是一位数字，因此是特殊情况 */

   while(x){
      d[n++] = (int)(x%10L);
      if(n >= MAX_DIGITS)break;
      x = x/10L;
   }

   /* 打印所有数字的顶部行 */

   for(i=n-1;i>=0;i--){
      topline(d[i],buf);
      buf += 3;
      *buf++=' ';
   }
   *buf++='\n'; /* 把电传打字机移到下一行 */

   /* 打印所有数字的中间行 */

   for(i=n-1;i>=0;i--){
      midline(d[i],buf);
      buf += 3;
      *buf++=' ';
   }
   *buf++='\n';

   /* 打印所有数字的底部行 */

   for(i=n-1;i>=0;i--){
      botline(d[i],buf);
      buf += 3;
      *buf++=' ';
   }
   *buf++='\n';
   *buf='\0';
}

int main()
{
   char buf[5*MAX_DIGITS];
   print_led(1234567, buf);
   printf("%s\n",buf);

   return 0;
}

#ifndef NO_MAIN
int main(int argc, char **argv)
{

   int i=0,n;
   long x;
   static int d[MAX_DIGITS];
   char buf[5*MAX_DIGITS];

   if(argc != 2){
      fprintf(stderr,"led: usage: led integer\n");
      return 1;
   }

   /* 从命令行取得参数 */

   x = atol(argv[1]);

   /* 合理性检查 */

   if(x<0){
      fprintf(stderr,"led: %d must be non-negative\n",x);
      return 1;
   }

   print_led(x,buf);
   printf("%s\n",buf);

   return 0;

}
#endif

/* vim: set expandtab ts=4 sw=3 sts=3 tw=80 :*/
