/* yh_builtin.c —— prelude 外部符号登记。
 *
 * yh 没有头文件与 import：libc 的常用函数由编译器在每个编译单元开始时
 * 直接登记为 extern 函数 Sym（docs/yh.g4 的 prelude 注释与
 * docs/03-design/00-语义边界-0.0.1.md §7）。不构造 yh 文本、不走
 * tcc_compile_string()——yh 的 fnDecl 必须带函数体，用户源码不允许原型。
 *
 * 裸 `...`（无类型变参）只允许出现在本表：
 *   printf / open 走 C 可变参数路径，调用点按 C 默认提升整实参。
 */

#include "yh.h"

/* prelude 函数描述：名字、返回类型 token、参数类型 token 列表、是否变参 */
struct yh_prelude_fn {
  const char* name;
  int ret;       /* 返回类型：TOK_* 或 0 表示 *void */
  int ret_ptr;   /* 返回是否为指针 */
  int params[4]; /* 参数类型 token 列表，-1 结尾 */
  int variadic;  /* 1 = 末尾是裸 ...（仅本表允许） */
};

/* 各参数类型说明：
 *   TOK_I8/TOK_U8/... → 内建标量；PTR_CHAR → *char；PTR_VOID → *void */
#define PTR_CHAR 1000
#define PTR_VOID 1001

static const struct yh_prelude_fn yh_prelude[] = {
    {"printf", TOK_INT, 0, {PTR_CHAR, -1}, 1},
    {"malloc", 0, 1, {TOK_U64, -1}, 0},
    {"free", TOK_VOID, 0, {PTR_VOID, -1}, 0},
    {"memcpy", 0, 1, {PTR_VOID, PTR_VOID, TOK_U64, -1}, 0},
    {"strlen", TOK_U64, 0, {PTR_CHAR, -1}, 0},
    {"exit", TOK_VOID, 0, {TOK_INT, -1}, 0},
    {"open", TOK_INT, 0, {PTR_CHAR, TOK_INT, -1}, 1},
    {"close", TOK_INT, 0, {TOK_INT, -1}, 0},
    {"read", TOK_I64, 0, {TOK_INT, PTR_VOID, TOK_U64, -1}, 0},
    {"write", TOK_I64, 0, {TOK_INT, PTR_VOID, TOK_U64, -1}, 0},
    {NULL, 0, 0, {0}, 0}};

/* 由类型说明构造 CType（供参数与返回） */
static void yh_prelude_ctype(int spec, CType* t) {
  if (spec == PTR_CHAR) {
    t->t = VT_BYTE | VT_UNSIGNED;
    mk_pointer(t);
  } else if (spec == PTR_VOID) {
    t->t = VT_VOID;
    mk_pointer(t);
  } else {
    yh_builtin_ctype(spec, t);
    t->ref = NULL;
  }
}

/* 在当前编译单元登记 prelude 的 10 个 extern 函数 Sym。
 * 必须在两遍解析开始前调用一次。 */
ST_FUNC void yh_register_prelude(void) {
  const struct yh_prelude_fn* pf;
  CType ret, arg, func_ctype;
  Sym *func_sym, *last, *p;

  for (pf = yh_prelude; pf->name; pf++) {
    /* 函数 Sym（返回类型挂在 Sym.type 上） */
    if (pf->ret_ptr) {
      ret.t = VT_VOID;
      mk_pointer(&ret);
    } else {
      yh_builtin_ctype(pf->ret, &ret);
      ret.ref = NULL;
    }
    func_ctype.t = VT_INT;
    func_ctype.ref = NULL;
    func_sym = sym_push(SYM_FIELD, &func_ctype, 0, 0);
    func_sym->type = ret;
    func_sym->f.func_call = FUNC_CDECL;
    func_sym->f.func_type = pf->variadic ? FUNC_ELLIPSIS : FUNC_CDECL;

    /* 参数链 */
    last = NULL;
    {
      int i;
      for (i = 0; pf->params[i] != -1; i++) {
        yh_prelude_ctype(pf->params[i], &arg);
        p = sym_push(SYM_FIELD, &arg, 0, 0);
        if (last)
          last->next = p;
        else
          func_sym->next = p;
        last = p;
      }
    }

    /* 登记 extern：绑定到 libc 同名符号 */
    {
      TokenSym* ts = tok_alloc(pf->name, strlen(pf->name));
      CType ft;
      ft.t = VT_FUNC;
      ft.ref = func_sym;
      external_global_sym(ts->tok, &ft, 0);
    }
  }
}
