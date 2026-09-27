/* yh_expr.c —— yh 表达式：优先级链、后缀链、structInit、sizeof/len，
 * 以及编译模式的表达式代码生成（SValue 值栈）。
 *
 * 对应 docs/yh.g4：expr → conditionalExpr → …逐层二元链 → unaryExpr →
 * postfixExpr → primaryExpr。优先级与 C 同表。
 *
 * 编译模式复用 tccgen 机制：
 *   - 二元/一元运算：gen_op / gen_cast_s（值栈上完成）；
 *   - 逻辑与/或：短路跳转（gvtst），模式取自 tccgen expr_land/expr_lor；
 *   - 调用：实参入栈 + gfunc_call；实参按形参类型做 yh 隐式转换检查；
 *   - 成员访问：gaddrof + find_field + 偏移相加（指针自动解引用）；
 *   - 字面量：vsetc；字符串：匿名 char 数组（decl_initializer_alloc）；
 *   - sizeof(T)：type_size 压入；len(e)：M4。
 *
 * structInit 消歧（g4 头部边界算法）：primary 在 IDENT 后看到 '{' 时
 * 一次捕获完成窥探与判定（非空、无 ';'、深度 0 无语句关键字、命名/
 * 位置形态连贯 → 字面量），回灌后由 structInit 解析器精确定位错误。
 */

#include "yh.h"

/* ---- 复用 tccgen 静态机制 ---- */
static void gen_cast_s(int t);
static void vseti(int r, int v);
static int gvtst(int inv, int t);
static Sym *find_field(CType *type, int v);
static void type_to_str(char *buf, int buf_size, CType *type, const char *varstr);
ST_FUNC void test_lvalue(void);
ST_FUNC CType *pointed_type(CType *type);
ST_FUNC void indir(void);

/* ---- yh_decl.c 状态 ---- */
extern int yh_pass;

/* ------------------------------------------------------------------ */
/* token 流捕获与窥探                                                   */
/* ------------------------------------------------------------------ */

/* 窥探当前 token 的下一个 token。
 * 捕获 [当前, 下一] 并以 0 结尾回灌；耗尽后自动弹回真实词法流。 */
ST_FUNC int yh_peek_next_token(void)
{
    TokenString *str = tok_str_alloc();
    int t1;

    tok_str_add_tok(str);
    next();
    t1 = tok;
    tok_str_add_tok(str);
    tok_str_add(str, 0);
    begin_macro(str, 1);
    next();
    return t1;
}

/* 语句关键字：出现在字面量组深度 0 处即判定为块/case 体而非字面量。 */
static int yh_is_stmt_keyword(int t)
{
    switch (t) {
    case TOK_IF: case TOK_ELSE: case TOK_FOR: case TOK_SWITCH:
    case TOK_CASE: case TOK_DEFAULT: case TOK_RETURN: case TOK_BREAK:
    case TOK_CONTINUE: case TOK_GOTO: case TOK_LET: case TOK_CONST1:
    case TOK_FN: case TOK_STRUCT: case TOK_UNION: case TOK_ENUM:
    case TOK_TYPE: case TOK_PUB: case TOK_IN:
    case TOK_WHILE: case TOK_DO: case TOK_TYPEDEF: case TOK_EXTERN:
    case TOK_STATIC: case TOK_UNSIGNED: case TOK_SIGNED1: case TOK_SHORT:
    case TOK_LONG: case TOK_FLOAT: case TOK_DOUBLE: case TOK_REGISTER:
    case TOK_AUTO: case TOK_INLINE1: case TOK_VOLATILE1: case TOK_RESTRICT1:
        return 1;
    default:
        return 0;
    }
}

/* 标识符后的花括号判定：当前 token 必须是标识符。捕获从当前 token 开始：
 * 若下一 token 是 '{' 则捕获到配对 '}'，否则只捕获到下一 token 为止。
 * 返回 1 = 组体可作 structInitBody。回灌以 0 终止，耗尽后自动弹回。 */
ST_FUNC int yh_brace_group_is_literal(void)
{
    TokenString *str;
    int ids[512];
    int n = 0, depth = 0, i, ok = 1, named, started = 0, has_brace = 0;

    str = tok_str_alloc();
    for (;;) {
        if (tok == TOK_EOF)
            tcc_error("未闭合的 '{'");
        if (n < (int)(sizeof(ids)/sizeof(ids[0])))
            ids[n] = tok;
        n++;
        tok_str_add_tok(str);
        if (!started) {
            if (tok == '{') {
                started = 1;
                depth = 1;
                has_brace = 1;
            } else if (n >= 2) {
                break;
            }
        } else if (tok == '{' || tok == '(' || tok == '[') {
            depth++;
        } else if (tok == '}' || tok == ')' || tok == ']') {
            depth--;
            if (depth == 0 && tok == '}')
                break;
        }
        if (tok == ';')
            ok = 0;
        next();
    }
    tok_str_add(str, 0);
    begin_macro(str, 1);
    next(); /* tok = 标识符（重放开始） */

    if (n >= (int)(sizeof(ids)/sizeof(ids[0])))
        ok = 0;
    if (ok && (!has_brace || n < 4))
        ok = 0;
    if (ok) {
        named = yh_tok_is_member_name(ids[2]) && ids[3] == ':';
        depth = 0;
        for (i = 2; i < n - 1 && ok; i++) {
            int t = ids[i];
            if (t == '{' || t == '(' || t == '[') {
                depth++;
                continue;
            }
            if (t == '}' || t == ')' || t == ']') {
                depth--;
                continue;
            }
            if (t == ';') {
                ok = 0;
                break;
            }
            if (depth != 0 || t == ',')
                continue;
            if (named && yh_tok_is_member_name(t) && ids[i + 1] == ':') {
                i++; /* 字段名（允许保留字）：连同 ':' 跳过 */
                continue;
            }
            if (yh_is_stmt_keyword(t)) {
                ok = 0;
                break;
            }
        }
    }
    return ok;
}

/* ------------------------------------------------------------------ */
/* 类型转换检查（方案 §4.1，标量子集）                                  */
/* ------------------------------------------------------------------ */

/* 类型身份比较：同型 = 规范化 BTYPE/符号/位宽一致（不比较指针所指）。 */
static int yh_same_scalar(CType *a, CType *b)
{
    int ba = a->t & VT_BTYPE, bb = b->t & VT_BTYPE;
    int ua = a->t & VT_UNSIGNED, ub = b->t & VT_UNSIGNED;
    static CType ta, tb;
    int sa, sb;

    if (ba == VT_FUNC || bb == VT_FUNC)
        return 0;
    if (ba >= VT_STRUCT && bb >= VT_STRUCT)
        return a->ref == b->ref && (a->t & ~VT_STORAGE) == (b->t & ~VT_STORAGE);
    /* 数组：元素与长度都相同才算同型 */
    if ((a->t & VT_ARRAY) || (b->t & VT_ARRAY)) {
        if (!(a->t & VT_ARRAY) || !(b->t & VT_ARRAY))
            return 0;
        if (a->ref->c != b->ref->c)
            return 0;
        return yh_same_scalar(&a->ref->type, &b->ref->type);
    }
    ta = *a; tb = *b;
    ta.t &= ~VT_STORAGE; tb.t &= ~VT_STORAGE;
    sa = type_size(&ta, &sb);
    sb = type_size(&tb, &sb);
    return ba == bb && ua == ub && sa == sb;
}

static int yh_is_int_bt(int bt)
{
    return bt == VT_BYTE || bt == VT_SHORT || bt == VT_INT || bt == VT_LLONG
        || bt == VT_BOOL;
}

static int yh_is_float_bt(int bt)
{
    return bt == VT_FLOAT || bt == VT_DOUBLE || bt == VT_LDOUBLE;
}

/* fn 签名结构相等：返回类型与参数链逐一比较（同型标量），
 * 变参形态（CDECL/ELLIPSIS）与类型化变参 packed 标志一并比较。 */
static int yh_func_sig_equal(Sym *a, Sym *b)
{
    if (!a || !b)
        return 0;
    if (a->f.func_type != b->f.func_type)
        return 0;
    if (!yh_same_scalar(&a->type, &b->type))
        return 0;
    a = a->next;
    b = b->next;
    while (a && b) {
        if (a->a.packed != b->a.packed)
            return 0;
        if (!yh_same_scalar(&a->type, &b->type))
            return 0;
        a = a->next;
        b = b->next;
    }
    return !a && !b;
}

/* 隐式转换判定（§4.1）：
 *   同型/透明别名 → 1；
 *   函数值 → 同签名 fn 类型 → 1（函数名取值，剥 VT_STATIC）；
 *   整数→更大整数（含符号差异按范围判断：有符号→同宽无符号拒绝）、
 *   f32→f64 → 1；其余 → 0（须显式 to_type）。 */
ST_FUNC int yh_implicit_conv(CType *dst, CType *src)
{
    int bd = dst->t & VT_BTYPE, bs = src->t & VT_BTYPE;
    int ud = dst->t & VT_UNSIGNED, us = src->t & VT_UNSIGNED;
    static CType t1, t2;
    int s1, s2, align;

    if (yh_same_scalar(dst, src))
        return 1;
    /* 函数名 → fn 类型：签名结构相等即同型（yh 的 fn 值即函数地址） */
    if (bd == VT_FUNC && bs == VT_FUNC)
        return yh_func_sig_equal(dst->ref, src->ref);
    /* 指针：*T → *void 隐式；void→数据指针拒绝 */
    if (bd == VT_PTR && bs == VT_PTR) {
        CType *pd = pointed_type(dst);
        if ((pd->t & VT_BTYPE) == VT_VOID)
            return 1;
        return 0;
    }
    /* bool → 整数：拒绝（须 to_type）；整数 → bool：拒绝 */
    if ((bd == VT_BOOL && yh_is_int_bt(bs)) || (bs == VT_BOOL && yh_is_int_bt(bd)))
        return 0;
    if (yh_is_int_bt(bd) && yh_is_int_bt(bs)) {
        t1 = *dst; t2 = *src;
        s1 = type_size(&t1, &align);
        s2 = type_size(&t2, &align);
        if (s1 > s2)
            return 1;              /* 放宽位宽 */
        if (s1 == s2 && ud == us)
            return 1;              /* 同宽同符号（不同 BTYPE 已按同型处理） */
        if (s1 == s2 && us && !ud)
            return 1;              /* u32 → i64 视作放宽的情形已被上一行覆盖 */
        return 0;                  /* 同宽不同符号/缩窄：须 to_type */
    }
    if (yh_is_float_bt(bd) && yh_is_float_bt(bs)) {
        t1 = *dst; t2 = *src;
        return type_size(&t1, &align) >= type_size(&t2, &align); /* f32→f64 */
    }
    /* 整数 0 → 数据指针（空指针）：由调用点（字面量路径）处理 */
    return 0;
}

/* 显式 to_type 判定：允许标量间互转、指针重解释、整数/浮点互转。
 * 数组/切片/结构体/函数类型在 M4 处理；void 目标拒绝。 */
ST_FUNC int yh_explicit_conv(CType *dst, CType *src)
{
    int bd = dst->t & VT_BTYPE, bs = src->t & VT_BTYPE;

    if ((dst->t & VT_BTYPE) == VT_VOID)
        return 0;
    if (yh_implicit_conv(dst, src))
        return 1;
    if (yh_is_int_bt(bd) || yh_is_float_bt(bd) || bd == VT_PTR) {
        if (yh_is_int_bt(bs) || yh_is_float_bt(bs) || bs == VT_PTR
            || bs == VT_BOOL)
            return 1;
    }
    if (bd == VT_BOOL && (yh_is_int_bt(bs) || yh_is_float_bt(bs) || bs == VT_PTR))
        return 1;
    return 0;
}

/* 整数字面量值是否可被目标整型表示（§4.1：可表示时隐式允许）。
 * vt 为目标类型（不含 bool）；v 为折叠负号后的常量值。 */
ST_FUNC int yh_const_fits(long long v, CType *dst)
{
    int sz, al, us = dst->t & VT_UNSIGNED;
    sz = type_size(dst, &al);
    switch (sz) {
    case 1: return us ? (v >= 0 && v <= 255) : (v >= -128 && v <= 127);
    case 2: return us ? (v >= 0 && v <= 65535)
                      : (v >= -32768 && v <= 32767);
    case 4: return us ? (v >= 0 && v <= 4294967295LL)
                      : (v >= -2147483648LL && v <= 2147483647LL);
    default: return us ? v >= 0 : 1; /* 64 位 */
    }
}

/* 赋值/传参/返回的转换：先 yh 检查再 gen_assign_cast。 */
ST_FUNC void yh_assign_cast_to(CType *dst, int explicit_ok)
{
    if (yh_syntax_only())
        return;
    /* 数组 → 数据指针：先做左值退化（同下标路径）；数据指针之间按
       同型标量处理（yh_same_scalar 不区分所指元素类型） */
    if ((dst->t & VT_BTYPE) == VT_PTR && (vtop->type.t & VT_ARRAY)) {
        vtop->type.t &= ~VT_ARRAY;
        if (vtop->r & VT_LVAL)
            gaddrof();
    }
    if (!yh_implicit_conv(dst, &vtop->type)) {
        char b1[120], b2[120];
        /* 整数字面量 0 → 数据指针（空指针） */
        if ((vtop->r & (VT_VALMASK | VT_LVAL | VT_SYM)) == VT_CONST
            && vtop->c.i == 0
            && (dst->t & VT_BTYPE) == VT_PTR
            && yh_is_int_bt(vtop->type.t & VT_BTYPE))
            goto allow;
        /* 整数字面量 → 目标整型可表示（§4.1）；bool 目标仍拒绝
           （整数→bool 一律须 to_type 或 true/false） */
        if ((vtop->r & (VT_VALMASK | VT_LVAL | VT_SYM)) == VT_CONST
            && yh_is_int_bt(vtop->type.t & VT_BTYPE)
            && yh_is_int_bt(dst->t & VT_BTYPE)
            && (dst->t & VT_BTYPE) != VT_BOOL
            && yh_const_fits(vtop->c.i, dst))
            goto allow;
        /* 浮点字面量 → f32/f64（§4.1：f32 目标按 f32 舍入） */
        if ((vtop->r & (VT_VALMASK | VT_LVAL | VT_SYM)) == VT_CONST
            && yh_is_float_bt(vtop->type.t & VT_BTYPE)
            && yh_is_float_bt(dst->t & VT_BTYPE))
            goto allow;
        /* 数组 → 同布局包装结构体（调用/返回边界，仅改类型字） */
        if ((dst->t & VT_BTYPE) == VT_STRUCT
            && (vtop->type.t & VT_ARRAY)) {
            CType st;
            yh_array_wrap(&vtop->type, &st);
            if (st.ref == dst->ref) {
                vtop->type = *dst;
                goto allow;
            }
        }
        /* 包装结构体 → 数组：调用结果/包装形参赋回裸数组变量
           （布局相同）。把目标左值的类型字对齐为包装结构体（仅当前
           语句的栈上类型），vstore 才能走结构体块拷贝而非标量拷贝 */
        if ((dst->t & VT_ARRAY)
            && (vtop->type.t & VT_BTYPE) == VT_STRUCT) {
            CType at;
            if (yh_wrap_array_of(&vtop->type, &at)
                && yh_arr_same(&at, dst)) {
                *dst = vtop->type;
                goto allow;
            }
        }
        if (!(explicit_ok && yh_explicit_conv(dst, &vtop->type))) {
            type_to_str(b1, sizeof b1, &vtop->type, NULL);
            type_to_str(b2, sizeof b2, dst, NULL);
            tcc_error("类型不匹配：无法把 '%s' 用作 '%s'", b1, b2);
        }
    }
allow:
    gen_assign_cast(dst);
}

/* ------------------------------------------------------------------ */
/* 表达式解析                                                           */
/* ------------------------------------------------------------------ */

static void yh_parse_conditional(void);
static void yh_parse_unary(void);
static void yh_parse_postfix(void);
static void yh_parse_primary(void);

#define YH_BIN_LEVEL(name, next_level, ops...)                           \
    static void name(void)                                               \
    {                                                                    \
        int op;                                                          \
        next_level();                                                    \
        for (;;) {                                                       \
            switch (tok) { ops                                           \
            default:                                                     \
                return;                                                  \
            }                                                            \
            op = tok;                                                    \
            next();                                                      \
            next_level();                                                \
            if (!yh_syntax_only()) {                                     \
                gen_op(op); /* SValue 栈上完成运算 */                     \
                /* 比较结果为 bool（yh 语义：if/逻辑要求 bool） */          \
                if (op >= TOK_ULT && op <= TOK_GE)                       \
                    vtop->type.t = (vtop->type.t & ~VT_BTYPE) | VT_BOOL; \
            }                                                            \
        }                                                                \
    }

YH_BIN_LEVEL(yh_parse_multiplicative, yh_parse_unary,
             case '*': case '/': case '%': break;)
YH_BIN_LEVEL(yh_parse_additive, yh_parse_multiplicative,
             case '+': case '-': break;)
YH_BIN_LEVEL(yh_parse_shift, yh_parse_additive,
             case TOK_SHL: case TOK_SAR: case TOK_SHR: break;)
YH_BIN_LEVEL(yh_parse_relational, yh_parse_shift,
             case TOK_LT: case TOK_GT: case TOK_LE: case TOK_GE: break;)
YH_BIN_LEVEL(yh_parse_equality, yh_parse_relational,
             case TOK_EQ: case TOK_NE: break;)
YH_BIN_LEVEL(yh_parse_bit_and, yh_parse_equality, case '&': break;)
YH_BIN_LEVEL(yh_parse_bit_xor, yh_parse_bit_and, case '^': break;)
YH_BIN_LEVEL(yh_parse_bit_or, yh_parse_bit_xor, case '|': break;)

/* 逻辑与：短路求值（模式取自 tccgen expr_land） */
static void yh_parse_logical_and(void)
{
    yh_parse_bit_or();
    if (yh_syntax_only()) {
        while (tok == TOK_LAND) {
            next();
            yh_parse_bit_or();
        }
        return;
    }
    if (tok == TOK_LAND) {
        int t = 0;
        for (;;) {
            if ((vtop->r & (VT_VALMASK | VT_LVAL | VT_SYM)) == VT_CONST) {
                gen_cast_s(VT_BOOL);
                if (vtop->c.i) {
                    vpop();
                } else {
                    nocode_wanted++;
                    while (tok == TOK_LAND) {
                        next();
                        yh_parse_bit_or();
                        vpop();
                    }
                    nocode_wanted--;
                    if (t)
                        gsym(t);
                    gen_cast_s(VT_INT);
                    break;
                }
            } else {
                if (!t)
                    save_regs(1);
                t = gvtst(1, t);
            }
            if (tok != TOK_LAND) {
                if (t)
                    vseti(VT_JMPI, t);
                else
                    vpushi(1);
                if (!yh_syntax_only())
                    vtop->type.t = VT_BOOL;
                break;
            }
            next();
            yh_parse_bit_or();
        }
    }
}

/* 逻辑或：短路求值（模式取自 tccgen expr_lor） */
static void yh_parse_logical_or(void)
{
    yh_parse_logical_and();
    if (yh_syntax_only()) {
        while (tok == TOK_LOR) {
            next();
            yh_parse_logical_and();
        }
        return;
    }
    if (tok == TOK_LOR) {
        int t = 0;
        for (;;) {
            if ((vtop->r & (VT_VALMASK | VT_LVAL | VT_SYM)) == VT_CONST) {
                gen_cast_s(VT_BOOL);
                if (!vtop->c.i) {
                    vpop();
                } else {
                    nocode_wanted++;
                    while (tok == TOK_LOR) {
                        next();
                        yh_parse_logical_and();
                        vpop();
                    }
                    nocode_wanted--;
                    if (t)
                        gsym(t);
                    gen_cast_s(VT_INT);
                    break;
                }
            } else {
                if (!t)
                    save_regs(1);
                t = gvtst(0, t);
            }
            if (tok != TOK_LOR) {
                if (t)
                    vseti(VT_JMP, t);
                else
                    vpushi(0);
                if (!yh_syntax_only())
                    vtop->type.t = VT_BOOL;
                break;
            }
            next();
            yh_parse_logical_and();
        }
    }
}

/* 条件表达式：logicalOr ('?' expr ':' expr)? */
static void yh_parse_conditional(void)
{
    yh_parse_logical_or();
    if (tok == '?') {
        int a;
        next();
        if (!yh_syntax_only())
            a = gvtst(0, 0);
        yh_parse_expr();
        if (!yh_syntax_only()) {
            gjmp(0); /* 假分支跳过：真值结果留栈 */
            gsym(a);
        }
        skip(':');
        yh_parse_conditional();
    }
}

ST_FUNC void yh_parse_expr(void)
{
    yh_parse_conditional();
}

/* structInitBody 纯语法解析 */
static void yh_parse_struct_init_body_pub(void)
{
    int named;

    if (tok == '}')
        tcc_error("结构体字面量不能为空");
    named = yh_tok_is_member_name(tok) && yh_peek_next_token() == ':';
    for (;;) {
        if (named) {
            if (!yh_tok_is_member_name(tok))
                tcc_error("命名式与位置式不能混写");
            next();
            skip(':');
            yh_parse_expr();
        } else {
            yh_parse_expr();
        }
        if (tok == ',') {
            next();
            if (tok == '}')
                break;
            continue;
        }
        break;
    }
}

/* 一元运算。 */
static void yh_parse_unary(void)
{
    int op;
    switch (tok) {
    case '-': case '+': case '!': case '~': case '*': case '&':
        op = tok;
        next();
        yh_parse_unary();
        if (!yh_syntax_only()) {
            switch (op) {
            case '-':
                vpushi(0);
                vswap();
                gen_op('-'); /* gen_op 按常规算术转换提升 */
                break;
            case '+':
                break;
            case '!':
                vpushi(0);
                gen_op(TOK_EQ);
                vtop->type.t = VT_BOOL;
                break;
            case '~':
                vpushi(-1);
                gen_op('^');
                break;
            case '*':
                indir();
                break;
            case '&':
                test_lvalue();
                gaddrof();
                mk_pointer(&vtop->type); /* int 左值 → int* 值 */
                break;
            }
        }
        return;
    default:
        yh_parse_postfix();
    }
}

/* 后缀链：调用、下标、to_type 转换、成员访问。 */
static void yh_parse_postfix(void)
{
    yh_parse_primary();
    for (;;) {
        if (tok == '(') {
            /* 函数调用：被调者在 vtop[-nb_args]，实参按源码顺序入栈 */
            int nb_args = 0, n_named = 0, is_ell = 0;
            int pack_off = 0;
            int n_pack = 0, elem_sz = 0, elem_al = 1;
            int pack_base = 0;
            int sret_loc = 0;
            Sym *fs = NULL;
            Sym *va = NULL;
            CType va_et;
            if (!yh_syntax_only() && (vtop->type.t & VT_BTYPE) == VT_FUNC) {
                fs = vtop->type.ref;
                is_ell = fs->f.func_type == FUNC_ELLIPSIS;
                if (is_ell) {
                    Sym *p;
                    for (p = fs->next; p && p->next; p = p->next)
                        n_named++; /* 末形参是变参本身，不计命名 */
                }
            }
            next();
            /* 结构体（含包装数组）返回：调用方在实参之前压入返回临时
               地址作为隐藏参数（tccgen 同款协议；arm64 gfunc_call 里
               寄存器可返回的结构体也会把 x0/x1 写回该临时） */
            if (!yh_syntax_only() && fs
                && (fs->type.t & VT_BTYPE) == VT_STRUCT) {
                int ralign, rsize = type_size(&fs->type, &ralign);
                /* 小结构体向上取整到 2 的幂，便于 stp 整块写出 */
                if (rsize < 16)
                    while (rsize & (rsize - 1))
                        rsize = (rsize | (rsize - 1)) + 1;
                loc = (loc - rsize) & -ralign;
                vseti(VT_LOCAL, loc);
                nb_args++;
                sret_loc = loc;
            }
            if (tok != ')') {
                Sym *pa = fs ? fs->next : NULL; /* 第一个形参 */
                int in_va = 0;
                if (is_ell) {
                    va = fs->next;
                    while (va && va->next)
                        va = va->next;
                    if (va && !yh_syntax_only() && va->a.packed) {
                        struct yh_wrap *w = NULL;
                        CType slt = va->type;
                        yh_is_slice(&slt, &w);
                        if (!w)
                            tcc_error("变参形参类型异常");
                        va_et = w->elem; /* 元素类型 T（来自登记表） */
                    } else
                        va = NULL; /* 裸 ...（prelude）：走 C 提升路径 */
                }
                for (;;) {
                    in_va = is_ell && va != NULL && pa == va;
                    yh_parse_expr();
                    nb_args++;
                    if (!yh_syntax_only()) {
                        if (pa && !in_va) {
                            yh_assign_cast_to(&pa->type, 0);
                            pa = pa->next;
                        } else if (in_va) {
                            /* 变参实参：值拷入临时连续数组（求值顺序=源码序） */
                            yh_assign_cast_to(&va_et, 0);
                            if (n_pack == 0) {
                                elem_sz = type_size(&va_et, &elem_al);
                                loc = (loc - 16 - 32 * elem_sz) & -elem_al;
                                pack_base = loc; /* 区域整体计入 loc（epilog 恢复） */
                            }
                            pack_off = pack_base + 16 + n_pack * elem_sz;
                            vset(&va_et, VT_LOCAL | VT_LVAL, pack_off);
                            vswap();
                            gen_assign_cast(&vtop[-1].type);
                            vstore();
                            vpop();
                            n_pack++;
                        } else if (is_ell && nb_args > n_named) {
                            int bt = vtop->type.t & VT_BTYPE;
                            if (bt == VT_FLOAT) {
                                CType dt;
                                dt.t = VT_DOUBLE;
                                dt.ref = NULL;
                                gen_cast(&dt);
                            } else if (bt == VT_BYTE || bt == VT_SHORT
                                       || bt == VT_BOOL) {
                                /* C 默认提升（§7）：i8/i16/u8/u16/bool → int，
                                   否则 i8 的符号扩展与寄存器上 32 位读取不一致 */
                                CType it;
                                it.t = VT_INT;
                                it.ref = NULL;
                                gen_cast(&it);
                            }
                        }
                    }
                    if (tok == ',') {
                        next();
                        continue;
                    }
                    break;
                }
            }
            skip(')');
            /* 变参形参查找（零实参时也要做） */
            if (is_ell && !yh_syntax_only()) {
                va = fs->next;
                while (va && va->next)
                    va = va->next;
                if (va && !va->a.packed)
                    va = NULL; /* 裸 ...（prelude）：走 C 提升路径 */
            }
            /* 变参打包完成：构造切片值 {len, data} 压入栈顶。
             * 调用约定：打包后的切片 = 一个实参，替换全部变参实参。
             * 零变参时也要压（data 槽仍需分配）。 */
            if (is_ell && !yh_syntax_only() && va) {
                    /* 变参实参值已拷入临时区（栈中不留） */
                    CType u64t;
                    u64t.t = VT_LLONG | VT_UNSIGNED;
                    u64t.ref = NULL;
                    vset(&u64t, VT_CONST, 0);
                    vtop->c.i = n_pack;              /* len */
                    /* data = 栈地址（64 位值）：VT_LOCAL 以 64 位载入 */
                    vset(&u64t, VT_LOCAL, pack_base + 16); /* data = 元素区起点 */
                    vtop->type = u64t;
                    /* 栈顶现在 [len(data 下方)?] —— 顺序：先 len 后 data 压的，
                       栈顶=data，vtop[-1]=len。合成 16B 临时结构体： */
                    {
                        CType sl = va->type;
                        int sz, al;
                        int tmp;
                        sz = type_size(&sl, &al);
                        loc = (loc - sz) & -al;
                        tmp = loc;
                        /* data → tmp+8 */
                        vset(&u64t, VT_LOCAL | VT_LVAL, tmp + 8);
                        vswap();
                        gen_assign_cast(&vtop[-1].type);
                        vstore();
                        vpop();
                        /* len → tmp */
                        vset(&u64t, VT_LOCAL | VT_LVAL, tmp);
                        vswap();
                        gen_assign_cast(&vtop[-1].type);
                        vstore();
                        vpop();
                        /* 切片左值入栈（作为实参值，gfunc_call 走结构体 16B 拷贝） */
                        vset(&sl, VT_LOCAL | VT_LVAL, tmp);
                    }
                nb_args = n_named + 1; /* 命名实参 + 一个切片 */
            }
            if (!yh_syntax_only()) {
                CType rt;
                CValue cval;
                if ((vtop[-nb_args].type.t & VT_BTYPE) != VT_FUNC)
                    expect("函数调用");
                rt = vtop[-nb_args].type.ref->type; /* 调用返回类型 */
                gfunc_call(nb_args); /* 弹出被调者与实参，结果在返回寄存器 */
                if ((rt.t & VT_BTYPE) == VT_VOID) {
                    /* void 调用无结果值 */
                } else if ((rt.t & VT_BTYPE) == VT_STRUCT) {
                    /* 结构体返回：结果 = 调用方临时（gfunc_call 已把
                       寄存器返回值写回该临时，或被调者经 x8 直写） */
                    vset(&rt, VT_LOCAL | VT_LVAL, sret_loc);
                } else {
                    int ret_reg = REG_IRET;
                    /* 浮点返回值在 v0（REG_FRET），整型在 x0 */
                    if (yh_is_float_bt(rt.t & VT_BTYPE))
                        ret_reg = REG_FRET;
                    memset(&cval, 0, sizeof cval);
                    vsetc(&rt, ret_reg, &cval); /* 结果入值栈 */
                }
            }
        } else if (tok == '[') {
            if (!yh_syntax_only()) {
                CType at;
                /* 切片 → data 指针值 */
                if (yh_is_slice(&vtop->type, NULL))
                    yh_slice_data(&vtop->type);
                /* 包装结构体（数组形参）透明还原为数组类型字：
                   首字段 a 位于偏移 0，左值地址即数组地址 */
                else if (yh_wrap_array_of(&vtop->type, &at))
                    vtop->type = at;
                /* 数组退化：类型转裸指针，左值地址即数组首地址 */
                if (vtop->type.t & VT_ARRAY) {
                    vtop->type.t &= ~VT_ARRAY;
                    if (vtop->r & VT_LVAL)
                        gaddrof();
                }
            }
            next();
            yh_parse_expr();
            skip(']');
            if (!yh_syntax_only()) {
                /* 指针/数组下标：*(p + i) */
                gen_op('+');
                indir();
            }
        } else if (tok == '.') {
            next();
            if (tok == TOK_TO_TYPE) {
                CType target;
                next();
                skip('(');
                yh_parse_type_ref(&target);
                skip(')');
                if (!yh_syntax_only()) {
                    /* [N]T → []T 视图构造先于标量检查 */
                    if (!((target.t & VT_BTYPE) == VT_STRUCT
                          && yh_is_slice(&target, NULL)
                          && (vtop->type.t & VT_ARRAY))
                        && !yh_explicit_conv(&target, &vtop->type)) {
                        char b1[120], b2[120];
                        type_to_str(b1, sizeof b1, &vtop->type, NULL);
                        type_to_str(b2, sizeof b2, &target, NULL);
                        tcc_error("to_type：不允许从 '%s' 转换为 '%s'", b1, b2);
                    }
                    /* [N]T → []T：构造切片视图（len=N, data=&arr[0]） */
                    if ((target.t & VT_BTYPE) == VT_STRUCT
                        && yh_is_slice(&target, NULL)
                        && (vtop->type.t & VT_ARRAY)) {
                        long long n = vtop->type.ref->c; /* 源数组长度 */
                        yh_array_view(&target, n);
                    } else
                    gen_cast(&target);
                    /* 结果一律右值：若仍是左值则载入寄存器
                       （结构体/数组左值除外——拷贝由 vstore 块拷贝完成） */
                    if ((vtop->r & VT_LVAL)
                        && (vtop->type.t & VT_BTYPE) != VT_STRUCT
                        && !(vtop->type.t & VT_ARRAY)) {
                        if ((vtop->type.t & VT_BTYPE) == VT_FLOAT
                            || (vtop->type.t & VT_BTYPE) == VT_DOUBLE
                            || (vtop->type.t & VT_BTYPE) == VT_LDOUBLE)
                            gv(RC_FLOAT);
                        else
                            gv(RC_INT);
                    }
                    vtop->type = target;
                }
            } else {
                int qualifiers;
                Sym *fd;
                if (!yh_tok_is_member_name(tok))
                    expect("成员名");
                if (yh_syntax_only()) {
                    next();
                    continue;
                }
                qualifiers = vtop->type.t & (VT_CONSTANT | VT_VOLATILE);
                /* 指针自动解引用：指针的值即结构体地址 */
                if ((vtop->type.t & VT_BTYPE) == VT_PTR) {
                    if (vtop->r & VT_LVAL)
                        gv(RC_INT);
                    vtop->r &= ~VT_LVAL;
                    vtop->type = *pointed_type(&vtop->type);
                } else {
                    test_lvalue();
                    gaddrof();
                }
                if ((vtop->type.t & VT_BTYPE) != VT_STRUCT)
                    expect("结构体成员");
                fd = find_field(&vtop->type, tok);
                if (!fd)
                    tcc_error("字段未找到：%s", get_tok_str(tok & ~SYM_FIELD, &tokc));
                next();
                vtop->type.t = VT_BYTE;
                mk_pointer(&vtop->type);
                vpushi(fd->c);
                gen_op('+');
                vtop->type = fd->type;
                vtop->type.t |= qualifiers;
                if (!(vtop->type.t & VT_ARRAY))
                    vtop->r |= lvalue_type(vtop->type.t);
            }
        } else {
            break;
        }
    }
}

/* 保留字的定向提示（方案 §7.6）：已移除的 C 关键字与旧转换写法
 * 不能作普通标识符，报错时给出迁移建议。 */
ST_FUNC void yh_reserved_hint(void)
{
    switch (tok) {
    case TOK_WHILE: tcc_error("'while' 已移除，请改用 'for'"); return;
    case TOK_DO: tcc_error("'do' 已移除，请改用 'for'"); return;
    case TOK_AS: tcc_error("旧转换写法 'as' 已移除，请改用 '.to_type(T)'"); return;
    case TOK_TYPEDEF: tcc_error("'typedef' 已移除，请改用 'type'"); return;
    case TOK_EXTERN: case TOK_STATIC: case TOK_REGISTER: case TOK_AUTO:
    case TOK_UNSIGNED: case TOK_SIGNED1: case TOK_SHORT: case TOK_LONG:
    case TOK_FLOAT: case TOK_DOUBLE: case TOK_INLINE1: case TOK_VOLATILE1:
    case TOK_RESTRICT1:
        tcc_error("'%s' 是已移除的 C 关键字", get_tok_str(tok, NULL));
        return;
    default:
        return;
    }
}

/* structInit：IDENT '{' structInitBody '}'。
 * 字面量体为命名式 `memberName ':' expr` 或位置式 `expr`，逗号分隔、
 * 允许尾逗号、强制非空，首元素形态决定整表形态（拒绝混写）。
 * 调用约定：tok=结构体名（primary 的 brace 判定已回灌流）。
 * 匿名对象分配（decl_initializer_alloc）→ 对象地址存隐藏槽 →
 * 逐字段「地址+偏移 = 值」存储 → 结果为对象左值。 */
static void yh_parse_struct_init(void)
{
    int tag_v;
    Sym *s;
    CType type;
    AttributeDef ad;
    int r;
    int ptr_off = 0;
    Sym *f;

    tag_v = tok;
    next();          /* 结构体名 */
    skip('{');

    if (yh_syntax_only()) {
        yh_parse_struct_init_body_pub();
        skip('}');
        return;
    }

    s = struct_find(tag_v);
    if (!s || s->c == -1)
        tcc_error("未声明的结构体 '%s'", get_tok_str(tag_v & ~SYM_STRUCT, NULL));

    type.t = s->type.t;
    type.ref = s;
    if (global_expr || (nocode_wanted & 0x80000000))
        r = VT_CONST;
    else
        r = VT_LOCAL;
    memset(&ad, 0, sizeof ad);
    decl_initializer_alloc(&type, &ad, r, 0, 0, 0); /* 对象引用入栈 */

    /* 对象地址 → 隐藏指针槽（VT_LOCAL 值即地址） */
    {
        CType a64;
        a64.t = VT_LLONG | VT_UNSIGNED;
        a64.ref = NULL;
        loc = (loc - 8) & -8;
        ptr_off = loc;
        vtop->type = a64;
        vset(&a64, VT_LOCAL | VT_LVAL, ptr_off);
        vswap();
        vstore();
        vpop();
    }

    /* 命名式判定：首 token 为成员名且后随 ':' */
    {
        int named = yh_tok_is_member_name(tok) && yh_peek_next_token() == ':';
        f = s->next;
        if (tok != '}') {
            for (;;) {
                if (named) {
                    if (!yh_tok_is_member_name(tok))
                        tcc_error("命名式与位置式不能混写");
                    f = find_field(&type, tok);
                    if (!f)
                        tcc_error("字段未找到：%s",
                                  get_tok_str(tok & ~SYM_FIELD, &tokc));
                    next();
                    skip(':');
                } else if (!f) {
                    tcc_error("初始化值多于字段");
                }
                /* 目标字段左值 = 槽中地址 + f->c */
                {
                    CType a64;
                    a64.t = VT_LLONG | VT_UNSIGNED;
                    a64.ref = NULL;
                    vset(&a64, VT_LOCAL | VT_LVAL, ptr_off);
                    gv(RC_INT);
                    vtop->type.t = VT_BYTE;
                    mk_pointer(&vtop->type);
                    vpushi(f->c);
                    gen_op('+');
                    vtop->type = f->type;
                    if (!(f->type.t & VT_ARRAY))
                        vtop->r |= lvalue_type(f->type.t);
                }
                /* 值 */
                yh_parse_expr();
                yh_assign_cast_to(&vtop[-1].type, 0);
                vstore();
                vpop();
                if (!named)
                    f = f->next;
                if (tok == ',') {
                    next();
                    if (tok == '}')
                        break;
                    continue;
                }
                break;
            }
        }
    }
    skip('}');

    /* 结果：从槽载入对象地址 → 解引用为对象左值 */
    {
        CType pt = type;
        mk_pointer(&pt);
        vset(&pt, VT_LOCAL | VT_LVAL, ptr_off);
        indir();
        vtop->type = type;
    }
}

/* 基本表达式。 */
static void yh_parse_primary(void)
{
    CType t;
    AttributeDef ad;
    int r;
    switch (tok) {
    case TOK_CINT: case TOK_CUINT: case TOK_CLLONG: case TOK_CULLONG:
    case TOK_CFLOAT: case TOK_CDOUBLE: case TOK_CLDOUBLE:
        if (!yh_syntax_only()) {
            t.t = (tok == TOK_CINT) ? VT_INT
                : (tok == TOK_CUINT) ? (VT_INT | VT_UNSIGNED)
                : (tok == TOK_CLLONG) ? VT_LLONG
                : (tok == TOK_CULLONG) ? (VT_LLONG | VT_UNSIGNED)
                : (tok == TOK_CFLOAT) ? VT_FLOAT
                : (tok == TOK_CDOUBLE) ? VT_DOUBLE : VT_LDOUBLE;
            t.ref = NULL;
            vsetc(&t, VT_CONST, &tokc);
        }
        next();
        return;
    case TOK_CCHAR: case TOK_LCHAR:
        if (!yh_syntax_only()) {
            t.t = VT_INT;
            t.ref = NULL;
            vsetc(&t, VT_CONST, &tokc);
        }
        next();
        return;
    case TOK_STR:
        if (yh_syntax_only()) {
            next(); /* 纯语法模式：只消费字符串 token */
        } else {
            /* 匿名 char 数组落地为全局常量并退化为 *char（g4：
               字符串字面量语义为 *char；has_init=2 的
               decl_initializer_alloc 自己消费字符串 token） */
            t.t = VT_BYTE;
            mk_pointer(&t);
            t.t |= VT_ARRAY;
            memset(&ad, 0, sizeof ad);
            decl_initializer_alloc(&t, &ad, VT_CONST, 2, 0, 0);
            vtop->type.t &= ~VT_ARRAY; /* 退化：char[N] → *char */
        }
        return;
    case TOK_TRUE: case TOK_FALSE:
        if (!yh_syntax_only()) {
            /* bool 字面量类型必须是 bool（§4.1）：int 会令
               let b bool = true; 被转换检查拒绝 */
            CType bt;
            CValue cv;
            bt.t = VT_BOOL;
            bt.ref = NULL;
            cv.i = (tok == TOK_TRUE);
            vsetc(&bt, VT_CONST, &cv);
        }
        next();
        return;
    case '(':
        next();
        yh_parse_expr();
        skip(')');
        return;
    case TOK_SIZEOF: {
        int align;
        next();
        skip('(');
        yh_parse_type_ref(&t);
        skip(')');
        if (!yh_syntax_only()) {
            int sz = type_size(&t, &align);
            if (sz < 0)
                tcc_error("sizeof：类型大小未知");
            vpushi(sz);
        }
        return;
    }
    case TOK_LEN:
        /* len(e)：数组/包装结构体 → 编译期常量；切片 → 运行期读 len（M4-02） */
        next();
        skip('(');
        yh_parse_expr();
        skip(')');
        if (!yh_syntax_only()) {
            long long n;
            if (yh_wrap_len(&vtop->type, &n)) {
                vpop();
                vpushi((int)n);
            } else if (yh_is_slice(&vtop->type, NULL)) {
                yh_slice_len(&vtop->type); /* 运行期读 len 字段 */
            } else {
                tcc_error("len 的实参必须是数组或切片");
            }
        }
        return;
    default:
        if (tok >= TOK_UIDENT) {
            int v = tok;
            if (yh_brace_group_is_literal()) {
                yh_parse_struct_init();
                return;
            }
            next();
            if (yh_syntax_only())
                return;
            {
                Sym *s = sym_find(v);
                if (!s)
                    tcc_error("'%s' 未声明", get_tok_str(v, NULL));
                r = s->r;
                if ((r & VT_VALMASK) < VT_CONST)
                    r = (r & ~VT_VALMASK) | VT_LOCAL;
                vset(&s->type, r, s->c);
                vtop->sym = s;
                if (r & VT_SYM)
                    vtop->c.i = 0;
                else if (r == VT_CONST && IS_ENUM_VAL(s->type.t)) {
                    /* 枚举成员与编译期常量 */
                    vtop->c.i = s->enum_val;
                }
            }
            return;
        }
        yh_reserved_hint();
        expect("表达式");
    }
}
