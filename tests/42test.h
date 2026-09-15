/* 本文件用于测试预处理 #include 指令。它的命名以预处理器
   数字开头，而该数字并不是合法的数字（42test.h）。
   包含它必须能正常工作。  */
#ifndef INC42_FIRST
int have_included_42test_h;
#define INC42_FIRST
#elif !defined INC42_SECOND
#define INC42_SECOND
int have_included_42test_h_second;
#else
#define INC42_THIRD
int have_included_42test_h_third;
#endif
