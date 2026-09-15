/* 这里检查需要 8 位但只有正值的枚举
   在存入/取自枚举类型的 8 位位域时是否正确地进行
   零扩展（而不是符号扩展）（这本身是
   实现定义的，
   因此未必被所有其他编译器支持）。  */
enum tree_code {
  SOME_CODE = 148, /* 第 7 位被置位，因此后续所有枚举值也都如此 */
  LAST_AND_UNUSED_TREE_CODE
};
typedef union tree_node *tree;
struct tree_common
{
  union tree_node *chain;
  union tree_node *type;
  enum tree_code code : 8;
  unsigned side_effects_flag : 1;
};
union tree_node
{
  struct tree_common common;
 };
enum c_tree_code {
  C_DUMMY_TREE_CODE = LAST_AND_UNUSED_TREE_CODE,
  STMT_EXPR,
  LAST_C_TREE_CODE
};
enum cplus_tree_code {
  CP_DUMMY_TREE_CODE = LAST_C_TREE_CODE,
  AMBIG_CONV,
  LAST_CPLUS_TREE_CODE
};

extern int printf(const char *, ...);
int blah(){return 0;}

int convert_like_real (tree convs)
{
  switch (((enum tree_code) (convs)->common.code))
    {
    case AMBIG_CONV: /* 这里第 7 位被置位，它绝不能是
			tree_common.code 的符号位，即该位域必须
			以某种方式标记为无符号。  */
      return blah();
    default:
      break;
    };
   printf("unsigned enum bit-fields broken\n");
}

int main()
{
  union tree_node convs;

  convs.common.code = AMBIG_CONV;
  convert_like_real (&convs);
  return 0;
}
