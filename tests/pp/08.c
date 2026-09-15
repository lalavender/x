// 测试实参中的宏展开
#define s_pos              s_s.s_pos
#define foo(x) (x)
foo(hej.s_pos)
