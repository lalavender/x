/* yh.h —— yh（玉衡）解析器各文件共享的声明。
 *
 * yh 解析器按职责拆分（由 libtcc.c 以 ONE_SOURCE 方式包含，合成一个
 * 编译单元）：
 *   yh_type.c    typeRef 解析、内建类型映射、type 别名、struct/union/enum
 *   yh_decl.c    顶层/局部声明、binding、fn、pub、编译入口 yh_compile()
 *   yh_stmt.c    block、if/for/switch、label/goto、exprStmt、break/continue
 *   yh_expr.c    优先级链、to_type 后缀、structInit、sizeof/len、memberName
 *   yh_builtin.c prelude 外部符号（printf/malloc/...）登记
 *
 * 双模式：同一 parser 服务编译与纯语法两种模式。
 *   - 编译模式（-o/-run）：边解析边走 TCC 值栈/符号机制；
 *   - 纯语法模式（--syntax-check，output_type == TCC_OUTPUT_SYNTAX）：
 *     只识别形态，不查符号、不调用 gen_*、不要求 main。
 * 用 yh_syntax_only() 判断当前模式。
 *
 * 注：yh_*.c 在 libtcc.c 中位于 tccgen.c 之后包含，因此 tccgen.c 的
 * static 函数可直接复用；本头文件按实际调用补一致签名的 static 声明。
 */

#ifndef YH_H
#define YH_H

/* 当前是否为纯语法检查模式（--syntax-check） */
#define yh_syntax_only() (tcc_state->output_type == TCC_OUTPUT_SYNTAX)

/* ---- 复用 tccgen.c 内部机制（签名与其定义保持一致） ---- */
ST_FUNC void gen_cast(CType *type);
ST_FUNC void gen_assign_cast(CType *dt);
ST_FUNC void vsetc(CType *type, int r, CValue *vc);
ST_FUNC void vpush_ref(CType *type, Section *sec, unsigned long offset,
                       unsigned long size);
ST_FUNC void vdup(void);
ST_FUNC Sym *external_global_sym(int v, CType *type, int r);
ST_FUNC int lvalue_type(int t);
ST_FUNC void expr_const1(void);
ST_FUNC void skip_or_save_block(TokenString **str);
ST_FUNC Sym *struct_find(int v);
ST_FUNC Sym *find_field(CType *type, int v);
ST_FUNC void decl_initializer_alloc(CType *type, AttributeDef *ad, int r,
                                    int has_init, int v, int scope);

/* ---- yh_builtin.c ---- */
/* 在当前编译单元登记 prelude 的 8 个 extern 函数 Sym */
ST_FUNC void yh_register_prelude(void);

/* ---- yh_decl.c ---- */
extern int yh_pass;   /* 1=扫描登记 2=编译生成（编译模式） */
extern int yh_bsym;   /* break 跳转链 */
extern int yh_csym;   /* continue 跳转链 */
extern int yh_break_depth; /* break 可用深度 */
extern int yh_cont_depth;  /* continue 可用深度 */
extern int yh_has_init_flag;
extern int yh_bind_name;
/* 函数框架生成：查第一遍登记的 Sym 并编译函数体 */
ST_FUNC void yh_gen_function(int v);
/* 编译当前已打开（tcc_open）的 .yh 源文件。
 * 纯语法模式只报告词法/语法错误并消费到 EOF。
 * 返回 0 成功；有错误返回 -1。 */
ST_FUNC int yh_compile(TCCState *s1);
/* let 声明：'let' binding (',' binding)* ';'；local=1 表示块内声明 */
ST_FUNC void yh_parse_let_decl(int local);
/* const 声明：'const' IDENT typeRef '=' expr ';' */
ST_FUNC void yh_parse_const_decl(void);
/* 解析整个翻译单元：topLevelDecl* 直到 EOF */
ST_FUNC void yh_parse_translation_unit(void);

/* ---- yh_type.c ---- */
/* typeRef：指针/数组/切片/函数类型/内建类型/具名类型，结果写入 *type */
ST_FUNC void yh_parse_type_ref(CType *type);
/* struct/union 声明：('struct'|'union') IDENT '{' fieldDecl* '}' */
ST_FUNC void yh_parse_struct_decl(int is_union);
/* enum 声明：'enum' IDENT '{' enumItem* '}' */
ST_FUNC void yh_parse_enum_decl(void);
/* 成员名判定：IDENT 或任意保留字（to_type 除外），见 docs/yh.g4 memberName */
ST_FUNC int yh_tok_is_member_name(int t);
/* token 是否能开始 typeRef（返回类型省略判定用） */
ST_FUNC int yh_tok_starts_type_ref(int t);
/* yh 类型 token → CType；非内建返回 0 */
ST_FUNC int yh_builtin_ctype(int t, CType *type);
/* [N]T → 匿名 struct { T a[N]; }（登记表缓存，ADR-0002 机制 a） */
ST_FUNC void yh_array_wrap(CType *arr, CType *out);
/* []T → 匿名 struct { u64 len; T *data; }（按元素类型规范化） */
ST_FUNC void yh_slice_wrap(CType *elem, CType *out);
/* 数组/切片长度：数组 → 编译期 N 返回 1；否则返回 0 */
ST_FUNC int yh_wrap_len(CType *t, long long *out_n);
/* 包装结构体 → 还原数组类型；非包装返回 0 */
ST_FUNC int yh_wrap_array_of(CType *t, CType *out);
/* 数组类型字 → 同布局包装结构体类型字（存储不变） */
ST_FUNC void yh_array_to_wrap(CType *t);
/* 切片判定/字段访问/数组视图 */
struct yh_wrap;
ST_FUNC int yh_is_slice(CType *t, struct yh_wrap **pw);
ST_FUNC void yh_slice_data(CType *slice_t);
ST_FUNC void yh_slice_len(CType *slice_t);
ST_FUNC void yh_array_view(CType *slice_t, long long n);

/* binding 落地与常量登记（yh_decl.c 实现，yh_expr.c 声明转换检查） */
ST_FUNC void yh_commit_local_var(CType *type);
ST_FUNC void yh_commit_global_var(CType *type);
ST_FUNC void yh_register_const(int v, CType *type);
/* 赋值/传参/返回的转换：先 yh 检查再 gen_assign_cast */
ST_FUNC void yh_assign_cast_to(CType *dst, int explicit_ok);

/* ---- yh_stmt.c ---- */
/* block：'{' stmt* '}' */
ST_FUNC void yh_parse_block(void);
/* 语句分发（block/let/if/for/switch/return/branch/goto/label/exprStmt） */
ST_FUNC void yh_parse_stmt(void);

/* ---- yh_expr.c ---- */
/* 表达式入口（条件表达式层，与 g4 expr 对应） */
ST_FUNC void yh_parse_expr(void);
/* 保留字定向提示：while→for、as→to_type 等（方案 §7.6） */
ST_FUNC void yh_reserved_hint(void);
/* 窥探当前 token 的下一个 token：回灌后 tok 不变、流无缝衔接。 */
ST_FUNC int yh_peek_next_token(void);
/* 花括号组判定：当前 token 为标识符时判定其后 '{' 组是否 structInit。 */
ST_FUNC int yh_brace_group_is_literal(void);
/* yh 类型检查：按方案 §4.1 判定 src 是否可隐式转换到 dst（右值语义）。
 * 返回 1 可隐式；0 不可（须显式 to_type 或直接拒绝）。 */
ST_FUNC int yh_implicit_conv(CType *dst, CType *src);
/* 显式 to_type 检查：返回 1 允许（结果为右值）。 */
ST_FUNC int yh_explicit_conv(CType *dst, CType *src);

#endif /* YH_H */
