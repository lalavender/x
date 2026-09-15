/*
 * 本文件中的信息可能会变更，不应被解释为
 * Digital Equipment Corporation 或 DECUS 的承诺。
 *
 * Digital Equipment Corporation、DECUS 以及作者均不对
 * 本文件或所述软件的使用或可靠性承担任何责任。
 *
 *      Copyright (C) 1980, DECUS
 *
 * 特此授予复制或修改的通用许可（但不得用于盈利），
 * 条件是包含上述版权声明，并说明
 * 复制权限由 DECUS 授予。
 *
 *
 *
 */
#include <stdio.h>
#include <stdlib.h>
#include <ctype.h>	// tolower()

/*
 * grep
 *
 * 运行在 Decus 编译器或 vms 上，在 vms 上定义如下：
 *      grep :== "$disk:[account]grep"      (native)
 *      grep :== "$disk:[account]grep grep" (Decus)
 * 更多信息见下文。
 */

char    *documentation[] = {
   "grep searches a file for a given pattern.  Execute by",
   "   grep [flags] regular_expression file_list\n",
   "Flags are single characters preceded by '-':",
   "   -c      Only a count of matching lines is printed",
   "   -f      Print file name for matching lines switch, see below",
   "   -n      Each line is preceded by its line number",
   "   -v      Only print non-matching lines\n",
   "The file_list is a list of files (wildcards are acceptable on RSX modes).",
   "\nThe file name is normally printed if there is a file given.",
   "The -f flag reverses this action (print name no file, not if more).\n",
   0 };

char    *patdoc[] = {
   "The regular_expression defines the pattern to search for.  Upper- and",
   "lower-case are always ignored.  Blank lines never match.  The expression",
   "should be quoted to prevent file-name translation.",
   "x      An ordinary character (not mentioned below) matches that character.",
   "'\\'    The backslash quotes any character.  \"\\$\" matches a dollar-sign.",
   "'^'    A circumflex at the beginning of an expression matches the",
   "       beginning of a line.",
   "'$'    A dollar-sign at the end of an expression matches the end of a line.",
   "'.'    A period matches any character except \"new-line\".",
   "':a'   A colon matches a class of characters described by the following",
   "':d'     character.  \":a\" matches any alphabetic, \":d\" matches digits,",
   "':n'     \":n\" matches alphanumerics, \": \" matches spaces, tabs, and",
   "': '     other control characters, such as new-line.",
   "'*'    An expression followed by an asterisk matches zero or more",
   "       occurrences of that expression: \"fo*\" matches \"f\", \"fo\"",
   "       \"foo\", etc.",
   "'+'    An expression followed by a plus sign matches one or more",
   "       occurrences of that expression: \"fo+\" matches \"fo\", etc.",
   "'-'    An expression followed by a minus sign optionally matches",
   "       the expression.",
   "'[]'   A string enclosed in square brackets matches any character in",
   "       that string, but no others.  If the first character in the",
   "       string is a circumflex, the expression matches any character",
   "       except \"new-line\" and the characters in the string.  For",
   "       example, \"[xyz]\" matches \"xx\" and \"zyx\", while \"[^xyz]\"",
   "       matches \"abc\" but not \"axb\".  A range of characters may be",
   "       specified by two characters separated by \"-\".  Note that,",
   "       [a-z] matches alphabetics, while [z-a] never matches.",
   "The concatenation of regular expressions is a regular expression.",
   0};

#define LMAX    512
#define PMAX    256

#define CHAR    1
#define BOL     2
#define EOL     3
#define ANY     4
#define CLASS   5
#define NCLASS  6
#define STAR    7
#define PLUS    8
#define MINUS   9
#define ALPHA   10
#define DIGIT   11
#define NALPHA  12
#define PUNCT   13
#define RANGE   14
#define ENDPAT  15

int cflag=0, fflag=0, nflag=0, vflag=0, nfile=0, debug=0;

char *pp, lbuf[LMAX], pbuf[PMAX];

char *cclass();
char *pmatch();
void store(int);
void error(char *);
void badpat(char *, char *, char *);
int match(void);


/*** 显示文件名 ***********************************/
void file(char *s)
{
   printf("File %s:\n", s);
}

/*** 报告无法打开的文件 ***********************/
void cant(char *s)
{
   fprintf(stderr, "%s: cannot open\n", s);
}

/*** 提供良好的帮助 *****************************/
void help(char **hp)
{
   char   **dp;

   for (dp = hp; *dp; ++dp)
      printf("%s\n", *dp);
}

/*** 显示用法摘要 ********************************/
void usage(char *s)
{
   fprintf(stderr, "?GREP-E-%s\n", s);
   fprintf(stderr,
         "Usage: grep [-cfnv] pattern [file ...].  grep ? for help\n");
   exit(1);
}

/*** 把模式编译到全局 pbuf[] 中 ***************/
void compile(char *source)
{
   char  *s;         /* 源字符串指针              */
   char  *lp;        /* 上一个模式指针            */
   int   c;          /* 当前字符                  */
   int            o;          /* 临时变量                  */
   char           *spp;       /* 保存模式的起始位置        */

   s = source;
   if (debug)
      printf("Pattern = \"%s\"\n", s);
   pp = pbuf;
   while (c = *s++) {
      /*
       * STAR、PLUS 和 MINUS 是特殊的。
       */
      if (c == '*' || c == '+' || c == '-') {
         if (pp == pbuf ||
               (o=pp[-1]) == BOL ||
               o == EOL ||
               o == STAR ||
               o == PLUS ||
               o == MINUS)
            badpat("Illegal occurrence op.", source, s);
         store(ENDPAT);
         store(ENDPAT);
         spp = pp;               /* 保存模式末尾         */
         while (--pp > lp)       /* 把模式后移           */
            *pp = pp[-1];        /* 一个字节             */
         *pp =   (c == '*') ? STAR :
            (c == '-') ? MINUS : PLUS;
         pp = spp;               /* 恢复模式末尾         */
         continue;
      }
      /*
       * 其余全部。
       */
      lp = pp;         /* 记住起始位置         */
      switch(c) {

         case '^':
            store(BOL);
            break;

         case '$':
            store(EOL);
            break;

         case '.':
            store(ANY);
            break;

         case '[':
            s = cclass(source, s);
            break;

         case ':':
            if (*s) {
               switch(tolower(c = *s++)) {

                  case 'a':
                  case 'A':
                     store(ALPHA);
                     break;

                  case 'd':
                  case 'D':
                     store(DIGIT);
                     break;

                  case 'n':
                  case 'N':
                     store(NALPHA);
                     break;

                  case ' ':
                     store(PUNCT);
                     break;

                  default:
                     badpat("Unknown : type", source, s);

               }
               break;
            }
            else    badpat("No : type", source, s);

         case '\\':
            if (*s)
               c = *s++;

         default:
            store(CHAR);
            store(tolower(c));
      }
   }
   store(ENDPAT);
   store(0);                /* 终止字符串           */
   if (debug) {
      for (lp = pbuf; lp < pp;) {
         if ((c = (*lp++ & 0377)) < ' ')
            printf("\\%o ", c);
         else    printf("%c ", c);
      }
      printf("\n");
   }
}

/*** 编译一个字符类（在 [] 内） *************/
char *cclass(char *source, char *src)
   /* char       *source;   // 模式起始位置 —— 用于错误信息 */
   /* char       *src;      // 字符类起始位置 */
{
   char   *s;        /* 源指针            */
   char   *cp;       /* 模式起始位置      */
   int    c;         /* 当前字符          */
   int             o;         /* 临时变量          */

   s = src;
   o = CLASS;
   if (*s == '^') {
      ++s;
      o = NCLASS;
   }
   store(o);
   cp = pp;
   store(0);                          /* 字节计数        */
   while ((c = *s++) && c!=']') {
      if (c == '\\') {                /* 存储被引用的字符     */
         if ((c = *s++) == '\0')      /* 必须取到某个字符     */
            badpat("Class terminates badly", source, s);
         else    store(tolower(c));
      }
      else if (c == '-' &&
            (pp - cp) > 1 && *s != ']' && *s != '\0') {
         c = pp[-1];             /* 范围起始        */
         pp[-1] = RANGE;         /* 范围标志        */
         store(c);               /* 重新存储起始    */
         c = *s++;               /* 取结束字符，并   */
         store(tolower(c));      /* 存储它          */
      }
      else {
         store(tolower(c));      /* 存储普通字符      */
      }
   }
   if (c != ']')
      badpat("Unterminated class", source, s);
   if ((c = (pp - cp)) >= 256)
      badpat("Class too large", source, s);
   if (c == 0)
      badpat("Empty class", source, s);
   *cp = c;
   return(s);
}

/*** 在模式缓冲区中存储一个条目 ***********/
void store(int op)
{
   if (pp >= &pbuf[PMAX])
      error("Pattern too complex\n");
   *pp++ = op;
}

/*** 报告错误的模式规格 ***********************/
void badpat(char *message, char *source, char *stop)
   /* char  *message;       // 错误信息 */
   /* char  *source;        // 模式起始位置 */
   /* char  *stop;          // 模式结束位置 */
{
   fprintf(stderr, "-GREP-E-%s, pattern is\"%s\"\n", message, source);
   fprintf(stderr, "-GREP-E-Stopped at byte %ld, '%c'\n",
         stop-source, stop[-1]);
   error("?GREP-E-Bad pattern\n");
}

/*** 在文件中扫描 pbuf[] 里的模式 ************/
void grep(FILE *fp, char *fn)
   /* FILE       *fp;       // 要处理的文件               */
   /* char       *fn;       // 文件名（用于 -f 选项）     */
{
   int lno, count, m;

   lno = 0;
   count = 0;
   while (fgets(lbuf, LMAX, fp)) {
      ++lno;
      m = match();
      if ((m && !vflag) || (!m && vflag)) {
         ++count;
         if (!cflag) {
            if (fflag && fn) {
               file(fn);
               fn = 0;
            }
            if (nflag)
               printf("%d\t", lno);
            printf("%s\n", lbuf);
         }
      }
   }
   if (cflag) {
      if (fflag && fn)
         file(fn);
      printf("%d\n", count);
   }
}

/*** 用模式 (pbuf) 匹配行 (lbuf)，匹配则返回 1 *****/
int match()
{
   char   *l;        /* 行指针             */

   for (l = lbuf; *l; ++l) {
      if (pmatch(l, pbuf))
         return(1);
   }
   return(0);
}

/*** 用模式匹配部分行 **************************/
char *pmatch(char *line, char *pattern)
   /* char               *line;     // 要匹配的（部分）行           */
   /* char               *pattern;  // 要匹配的（部分）模式         */
{
   char   *l;        /* 当前行指针                   */
   char   *p;        /* 当前模式指针                 */
   char   c;         /* 当前字符                     */
   char            *e;        /* STAR 和 PLUS 匹配的结束位置  */
   int             op;        /* 模式操作                      */
   int             n;         /* 字符类计数器                  */
   char            *are;      /* STAR 匹配的起始位置          */

   l = line;
   if (debug > 1)
      printf("pmatch(\"%s\")\n", line);
   p = pattern;
   while ((op = *p++) != ENDPAT) {
      if (debug > 1)
         printf("byte[%ld] = 0%o, '%c', op = 0%o\n",
               l-line, *l, *l, op);
      switch(op) {

         case CHAR:
            if (tolower(*l++) != *p++)
               return(0);
            break;

         case BOL:
            if (l != lbuf)
               return(0);
            break;

         case EOL:
            if (*l != '\0')
               return(0);
            break;

         case ANY:
            if (*l++ == '\0')
               return(0);
            break;

         case DIGIT:
            if ((c = *l++) < '0' || (c > '9'))
               return(0);
            break;

         case ALPHA:
            c = tolower(*l++);
            if (c < 'a' || c > 'z')
               return(0);
            break;

         case NALPHA:
            c = tolower(*l++);
            if (c >= 'a' && c <= 'z')
               break;
            else if (c < '0' || c > '9')
               return(0);
            break;

         case PUNCT:
            c = *l++;
            if (c == 0 || c > ' ')
               return(0);
            break;

         case CLASS:
         case NCLASS:
            c = tolower(*l++);
            n = *p++ & 0377;
            do {
               if (*p == RANGE) {
                  p += 3;
                  n -= 2;
                  if (c >= p[-2] && c <= p[-1])
                     break;
               }
               else if (c == *p++)
                  break;
            } while (--n > 1);
            if ((op == CLASS) == (n <= 1))
               return(0);
            if (op == CLASS)
               p += n - 2;
            break;

         case MINUS:
            e = pmatch(l, p);       /* 寻找匹配             */
            while (*p++ != ENDPAT); /* 跳过模式             */
            if (e)                  /* 匹配上了吗？         */
               l = e;               /* 是，更新字符串       */
            break;                  /* 总是成功             */

         case PLUS:                 /* 一个或多个 ...       */
            if ((l = pmatch(l, p)) == 0)
               return(0);           /* 必须有一个匹配       */
         case STAR:                 /* 零或多个 ...         */
            are = l;                /* 记住行起始位置       */
            while (*l && (e = pmatch(l, p)))
               l = e;               /* 取得最长的匹配       */
            while (*p++ != ENDPAT); /* 跳过模式             */
            while (l >= are) {      /* 尝试匹配剩余部分     */
               if (e = pmatch(l, p))
                  return(e);
               --l;                 /* 否，试更早的位置     */
            }
            return(0);              /* 其他都不行了         */

         default:
            printf("Bad op code %d\n", op);
            error("Cannot happen -- match\n");
      }
   }
   return(l);
}

/*** 报告一个错误 ********************************/
void error(char *s)
{
   fprintf(stderr, "%s", s);
   exit(1);
}

/*** 主程序 —— 解析参数并执行 grep *******/
int main(int argc, char **argv)
{
   char   *p;
   int    c, i;
   int             gotpattern;

   FILE            *f;

   if (argc <= 1)
      usage("No arguments");
   if (argc == 2 && argv[1][0] == '?' && argv[1][1] == 0) {
      help(documentation);
      help(patdoc);
      return 0;
   }
   nfile = argc-1;
   gotpattern = 0;
   for (i=1; i < argc; ++i) {
      p = argv[i];
      if (*p == '-') {
         ++p;
         while (c = *p++) {
            switch(tolower(c)) {

               case '?':
                  help(documentation);
                  break;

               case 'C':
               case 'c':
                  ++cflag;
                  break;

               case 'D':
               case 'd':
                  ++debug;
                  break;

               case 'F':
               case 'f':
                  ++fflag;
                  break;

               case 'n':
               case 'N':
                  ++nflag;
                  break;

               case 'v':
               case 'V':
                  ++vflag;
                  break;

               default:
                  usage("Unknown flag");
            }
         }
         argv[i] = 0;
         --nfile;
      } else if (!gotpattern) {
         compile(p);
         argv[i] = 0;
         ++gotpattern;
         --nfile;
      }
   }
   if (!gotpattern)
      usage("No pattern");
   if (nfile == 0)
      grep(stdin, 0);
   else {
      fflag = fflag ^ (nfile > 0);
      for (i=1; i < argc; ++i) {
         if (p = argv[i]) {
            if ((f=fopen(p, "r")) == NULL)
               cant(p);
            else {
               grep(f, p);
               fclose(f);
            }
         }
      }
   }
   return 0;
}

/* vim: set expandtab ts=4 sw=3 sts=3 tw=80 :*/
