/* 示例来自 http://barnyard.syr.edu/quickies/hanoi.c */

/* hanoi.c：解决汉诺塔问题。（编程练习。） */
/* 作者 Terry R. McConnell (12/2/97) */
/* 编译：cc -o hanoi hanoi.c */

/* 本程序不做错误检查。不过，如果它是对的， 
   它就是对的 …… 对吧 ? */


/* 最初的汉诺塔问题似乎最早由一位 M. Claus 在 1883 年提出。与之相伴的
   一个广为流传的传说被反复复述和改写。它大致是这样的：
   在贝拿勒斯的伟大神庙里有 3 根金色的尖柱。在其中一根上面，
   上帝在时间之初放置了 64 个从下到上依次增大的圆盘。从那时起直到今天，
   值班的祭司不断地搬运圆盘，一次一个，
   并且从不把较大的圆盘放在较小的圆盘上面。当圆盘全部被搬运到
   另一根尖柱上时，
   宇宙将在一阵巨大的霹雳中终结。

   这里转述的是 DeParville 记载的原始传说，见 La Nature, Paris 1884,
   Part I, 285-286。关于此事及更多资料见：
   Mathematical 
   Recreations & Essays, W.W. Rouse Ball, MacMillan, NewYork, 11th Ed. 1967,
   303-305.
 *
 *
 */

#include <stdio.h>
#include <stdlib.h>

#define TRUE 1
#define FALSE 0

/* 这是最初塔 A 上的"圆盘"数量。传说中取 64。
 * 一般所需的移动次数为 2^N - 1。对于 N = 64，
 * 结果就是 18,446,744,073,709,551,615 */
#define N 4

/* 这就是三座塔。例如若 A 的状态为 0,1,3,4，那
 * 就表示 A 上有三个尺寸为 1、3 和 4 的圆盘。（把右侧
 * 看作"向下"的方向。） */
int A[N], B[N], C[N]; 

void Hanoi(int,int*,int*,int*);

/* 把 A、B 和 C 的当前状态打印到屏幕上 */
void PrintAll()
{
   int i;

   printf("A: ");
   for(i=0;i<N;i++)printf(" %d ",A[i]);
   printf("\n");

   printf("B: ");
   for(i=0;i<N;i++)printf(" %d ",B[i]);
   printf("\n");

   printf("C: ");
   for(i=0;i<N;i++)printf(" %d ",C[i]);
   printf("\n");
   printf("------------------------------------------\n");
   return;
}

/* 把 source 中最左边的非零元素移到 dest，原位置留下 0。 */
/* 返回被移动的值（未被使用。） */
int Move(int *source, int *dest)
{
   int i = 0, j = 0;

   while (i<N && (source[i])==0) i++;
   while (j<N && (dest[j])==0) j++;

   dest[j-1] = source[i];
   source[i] = 0;
   PrintAll();       /* 每次移动后打印状态。 */
   return dest[j-1];
}


/* 按汉诺塔规则把 source 中前 n 个非零数字移到 dest。
   递归调用自身。
   */
void Hanoi(int n,int *source, int *dest, int *spare)
{
   int i;
   if(n==1){
      Move(source,dest);
      return;
   }

   Hanoi(n-1,source,spare,dest);
   Move(source,dest);
   Hanoi(n-1,spare,dest,source);	
   return;
}

int main()
{
   int i;

   /* 初始化各塔 */
   for(i=0;i<N;i++)A[i]=i+1;
   for(i=0;i<N;i++)B[i]=0;
   for(i=0;i<N;i++)C[i]=0;

   printf("Solution of Tower of Hanoi Problem with %d Disks\n\n",N);

   /* 打印起始状态 */
   printf("Starting state:\n");
   PrintAll();
   printf("\n\nSubsequent states:\n\n");

   /* 开始吧！用 A = Source，B = Destination，C = Spare */
   Hanoi(N,A,B,C);

   return 0;
}

/* vim: set expandtab ts=4 sw=3 sts=3 tw=80 :*/
