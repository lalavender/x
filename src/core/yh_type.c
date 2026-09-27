/* yh_type.c —— yh 类型语法与类型注册：typeRef、内建类型映射、
 * struct/union/enum 声明与布局、具名类型查找。
 *
 * 对应 docs/yh.g4：typeRef / fnType / builtinType / structDecl /
 * unionDecl / fieldDecl / enumDecl / enumItem。
 *
 * 内建类型映射（方案 §4）：i8→VT_BYTE、i16→VT_SHORT、int/i32→VT_INT、
 * i64→VT_LLONG、u*→对应整型+VT_UNSIGNED、f32/f64→VT_FLOAT/VT_DOUBLE、
 * bool→VT_BOOL、char→8 位无符号字节（与 u8 同型）、void→VT_VOID。
 *
 * 类型注册（编译模式）：struct/union/enum 走 tccgen 的 tag 机制
 * （sym_push(v|SYM_STRUCT)），字段为 SYM_FIELD Sym 链，布局由
 * struct_layout() 计算；type 别名登记到 ts->sym_type。yh 三类类型
 * 共享一个命名空间，查找先查 struct 标签再查别名；类型名要求先声明
 * 后引用（前向调用仅对函数开放，见语义边界文档 §1）。
 */

#include "yh.h"

ST_FUNC void struct_layout(CType *type, AttributeDef *ad);
ST_FUNC Sym *struct_find(int v);
ST_FUNC void indir(void);
static long long yh_expr_const64(void);

/* 内建类型 token → CType 映射；非内建类型返回 0。 */
ST_FUNC int yh_builtin_ctype(int t, CType *type)
{
    switch (t) {
    case TOK_INT:   type->t = VT_INT;                    return 1;
    case TOK_I8:    type->t = VT_BYTE;                   return 1;
    case TOK_I16:   type->t = VT_SHORT;                  return 1;
    case TOK_I32:   type->t = VT_INT;                    return 1;
    case TOK_I64:   type->t = VT_LLONG;                  return 1;
    case TOK_U8:    type->t = VT_BYTE | VT_UNSIGNED;     return 1;
    case TOK_U16:   type->t = VT_SHORT | VT_UNSIGNED;    return 1;
    case TOK_U32:   type->t = VT_INT | VT_UNSIGNED;      return 1;
    case TOK_U64:   type->t = VT_LLONG | VT_UNSIGNED;    return 1;
    case TOK_F32:   type->t = VT_FLOAT;                  return 1;
    case TOK_F64:   type->t = VT_DOUBLE;                 return 1;
    case TOK_YBOOL: type->t = VT_BOOL;                   return 1;
    case TOK_CHAR:  type->t = VT_BYTE | VT_UNSIGNED;     return 1;
    case TOK_VOID:  type->t = VT_VOID;                   return 1;
    default:                                             return 0;
    }
}

/* 成员名判定：IDENT 或任意保留字（专用后缀 to_type 除外）。
 * 注意：所有关键字 token 编号都 >= TOK_IDENT；用户标识符 >= TOK_UIDENT。 */
ST_FUNC int yh_tok_is_member_name(int t)
{
    return t >= TOK_IDENT && t != TOK_TO_TYPE;
}

/* 消费一个成员名（fieldDecl / 字面量字段共用） */
static void yh_parse_member_name(void)
{
    if (!yh_tok_is_member_name(tok))
        expect("成员名");
    next();
}

/* 当前 token 是否能开始一个 typeRef（返回类型省略判定）。 */
ST_FUNC int yh_tok_starts_type_ref(int t)
{
    CType tmp;
    if (t == '*' || t == '[' || t == TOK_FN)
        return 1;
    if (yh_builtin_ctype(t, &tmp))
        return 1;
    return t >= TOK_UIDENT;
}

/* 编译期常量求值（数组长度、枚举判别值）：求出并弹出，返回 64 位值。 */
static long long yh_expr_const64(void)
{
    CValue cval;
    int saved = const_wanted;
    long long n;

    const_wanted = 1;
    expr_const1();
    const_wanted = saved;
    cval.i = vtop->c.i;
    n = cval.i;
    vpop();
    return n;
}

/* fnType：'fn' '(' typeRefList? ')' typeRef?，构造 VT_FUNC 类型。
 * 编译模式下带名参数的 Sym->v 设为「参数名 | SYM_FIELD」，
 * gfunc_prolog 依赖它把寄存器实参绑定到局部槽。 */
static void yh_parse_fn_type(CType *type, int want_names)
{
    CType ret, arg, fake;
    Sym *func_sym, *last = NULL;

    next(); /* 消费 'fn' */
    skip('(');
    fake.t = VT_INT;
    fake.ref = NULL;
    func_sym = sym_push(SYM_FIELD, &fake, 0, 0);
    if (tok != ')') {
        for (;;) {
            int v = 0;
            /* fn 声明中的参数带名字；fn 类型只有类型 */
            if (want_names && tok >= TOK_UIDENT) {
                v = tok;
                next();
                if (tok == TOK_DOTS) {
                    /* 类型化变参 `name ... T` */
                    next();
                }
            }
            arg.t = VT_INT;
            arg.ref = NULL;
            yh_parse_type_ref(&arg);
            if (!yh_syntax_only()) {
                Sym *p = sym_push(SYM_FIELD, &arg, 0, 0);
                if (v)
                    p->v = v | SYM_FIELD;
                if (last)
                    last->next = p;
                else
                    func_sym->next = p;
                last = p;
            }
            if (tok == ',') {
                next();
                continue;
            }
            break;
        }
    }
    skip(')');
    if (yh_tok_starts_type_ref(tok)) {
        yh_parse_type_ref(&ret);
    } else {
        ret.t = VT_VOID;
        ret.ref = NULL;
    }
    func_sym->type.t = ret.t;
    func_sym->type.ref = ret.ref;
    type->t = VT_FUNC;
    type->ref = func_sym;
}

/* 具名类型查找：先 struct/union/enum 标签，再 type 别名
 * （别名登记在标识符命名空间，带 VT_TYPEDEF 标志）。找不到返回 NULL。 */
static Sym *yh_named_type(int v)
{
    Sym *s = struct_find(v);
    if (!s) {
        s = sym_find(v);
        if (s && !(s->type.t & VT_TYPEDEF))
            s = NULL;
    }
    return s;
}

/* typeRef：类型自身的组合（前缀书写），结果写入 *type。 */
ST_FUNC void yh_parse_type_ref(CType *type)
{
    CType elem;
    Sym *s;
    long long n = -1;

    switch (tok) {
    case '*':
        next();
        yh_parse_type_ref(type);
        mk_pointer(type);
        return;
    case '[':
        next();
        if (tok != ']') {
            /* 数组长度：编译期整数常量 */
            if (yh_syntax_only()) {
                yh_parse_expr();
                n = -1;
            } else {
                n = yh_expr_const64();
                if (n <= 0)
                    tcc_error("数组长度必须是正的编译期整数常量");
            }
        }
        skip(']');
        yh_parse_type_ref(&elem);
        if (!yh_syntax_only()) {
            if (n < 0) {
                /* []T 切片：规范化为 struct { u64 len; T *data; } */
                yh_slice_wrap(&elem, type);
            } else {
                /* 数组：匿名 Sym 持元素类型与长度 */
                s = sym_push(SYM_FIELD, &elem, 0, n);
                type->t = VT_ARRAY | VT_PTR;
                type->ref = s;
            }
        } else {
            type->t = VT_ARRAY | VT_PTR;
            type->ref = NULL;
        }
        return;
    case TOK_FN:
        yh_parse_fn_type(type, 0);
        return;
    default:
        if (yh_builtin_ctype(tok, type)) {
            type->ref = NULL;
            next();
            return;
        }
        if (tok >= TOK_UIDENT) {
            int v = tok;
            next();
            if (!yh_syntax_only()) {
                s = yh_named_type(v);
                if (!s)
                    tcc_error("未声明的类型 '%s'", get_tok_str(v, NULL));
                if (s->type.t & (VT_STRUCT | VT_ENUM)) {
                    /* tag：使用处的 ref 指向 tag Sym 本身 */
                    type->t = s->type.t;
                    type->ref = s;
                } else {
                    /* type 别名 */
                    type->t = s->type.t;
                    type->ref = s->type.ref;
                }
            } else {
                /* 纯语法模式：占位 */
                type->t = VT_INT;
                type->ref = NULL;
            }
            return;
        }
        expect("类型");
    }
}

/* fieldDecl：memberName typeRef ';' —— 字段 Sym 链到 *ps。 */
static void yh_parse_field_decl(Sym ***pps)
{
    CType ft;
    Sym *ss;
    int v;

    v = tok;
    yh_parse_member_name();
    ft.t = VT_INT;
    ft.ref = NULL;
    yh_parse_type_ref(&ft);
    if ((ft.t & VT_BTYPE) == VT_FUNC || (ft.t & VT_STORAGE))
        tcc_error("字段 '%s' 类型非法", get_tok_str(v, NULL));
    if (!yh_syntax_only()) {
        ss = sym_push(v | SYM_FIELD, &ft, 0, 0);
        **pps = ss;
        *pps = &ss->next;
    }
    skip(';');
}

/* struct/union 声明：('struct'|'union') IDENT '{' fieldDecl* '}'。
 * 编译模式：登记 tag、构建字段链并计算布局；语法模式：只识别形态。 */
ST_FUNC void yh_parse_struct_decl(int is_union)
{
    int u = is_union ? VT_UNION : VT_STRUCT;
    int v;
    CType type1, stype;
    Sym *s = NULL, *first = NULL, **ps = &first;
    AttributeDef ad;

    next(); /* 消费 'struct' / 'union' */
    if (tok < TOK_UIDENT)
        expect("结构体名");
    v = tok;
    next();

    if (!yh_syntax_only()) {
        s = struct_find(v);
        if (s && tok == '{' && s->c != -1)
            tcc_error("重定义 '%s'", get_tok_str(v, NULL));
        if (!s) {
            type1.t = u;
            type1.ref = NULL;
            s = sym_push(v | SYM_STRUCT, &type1, 0, -1);
            s->r = 0;
        }
    }
    skip('{');
    while (tok != '}') {
        if (tok == TOK_EOF)
            tcc_error("结构体定义缺少 '}'");
        yh_parse_field_decl(&ps);
    }
    skip('}');
    if (!yh_syntax_only()) {
        s->next = first; /* 字段链挂到 tag */
        stype.t = u;
        stype.ref = s;
        memset(&ad, 0, sizeof ad);
        struct_layout(&stype, &ad);
    }
}

/* enumItem：IDENT ('=' expr)? ';'，返回下一个判别值。 */
static long long yh_parse_enum_item(long long cur, Sym ***pps, CType *et)
{
    long long val = cur;
    int v;
    Sym *ss;

    if (tok < TOK_UIDENT)
        expect("枚举成员名");
    v = tok;
    next();
    if (tok == '=') {
        next();
        val = yh_expr_const64();
    }
    if (!yh_syntax_only()) {
        ss = sym_push(v, et, VT_CONST, 0);
        ss->enum_val = val;
        **pps = ss;
        *pps = &ss->next;
    }
    skip(';');
    return val + 1;
}

/* enum 声明：'enum' IDENT '{' enumItem* '}'。成员是 VT_CONST 整型常量。 */
ST_FUNC void yh_parse_enum_decl(void)
{
    int v;
    CType et, stype;
    Sym *s = NULL, *first = NULL, **ps = &first;
    long long cur = 0;

    next(); /* 消费 'enum' */
    if (tok < TOK_UIDENT)
        expect("枚举名");
    v = tok;
    next();

    if (!yh_syntax_only()) {
        s = struct_find(v);
        if (s && tok == '{' && s->c != -1)
            tcc_error("重定义 '%s'", get_tok_str(v, NULL));
        if (!s) {
            stype.t = VT_ENUM | VT_INT;
            stype.ref = NULL;
            s = sym_push(v | SYM_STRUCT, &stype, 0, -1);
            s->r = 0;
        }
        et.t = VT_INT | VT_STATIC | VT_ENUM_VAL;
        et.ref = s;
    }
    skip('{');
    while (tok != '}') {
        if (tok == TOK_EOF)
            tcc_error("枚举定义缺少 '}'");
        cur = yh_parse_enum_item(cur, &ps, &et);
    }
    skip('}');
    if (!yh_syntax_only())
        s->next = first; /* 成员链挂在 tag->next（对齐 tccgen 枚举） */
}


/* ------------------------------------------------------------------ */
/* 数组/切片包装结构体登记表（ADR-0002 机制 a）                          */
/*                                                                    */
/* [N]T 参数/返回/赋值在调用边界降糖为匿名 struct { T a[N]; }，         */
/* []T 降糖为 struct { u64 len; T *data; }。同一 (元素类型, 长度)       */
/* 全局唯一，登记表存活到编译单元结束（方案 §2.3）。                    */
/* ------------------------------------------------------------------ */

struct yh_wrap {
    Sym *tag;        /* 匿名结构体 tag Sym */
    CType arr;       /* 对应的数组类型（VT_ARRAY|VT_PTR，ref=元素 Sym） */
    CType elem;      /* 切片元素类型（仅切片用） */
    int is_slice;
};

/* 包装类型登记上限（B2-3：为自举源码留量；超限干净报错不静默截断） */
#define YH_MAX_WRAPS 512
static struct yh_wrap yh_wraps[YH_MAX_WRAPS];
static int yh_nb_wraps;

/* 数组类型比较：元素类型与长度都相同（包装登记/调用边界还原共用） */
ST_FUNC int yh_arr_same(CType *a, CType *b)
{
    if (!(a->t & VT_ARRAY) || !(b->t & VT_ARRAY))
        return 0;
    if (a->ref->c != b->ref->c)
        return 0;
    return a->ref->type.t == b->ref->type.t
        && a->ref->type.ref == b->ref->type.ref;
}

/* 判断结构体类型是否为登记表中的包装结构体；返回登记项或 NULL。 */
static struct yh_wrap *yh_wrap_find(CType *t)
{
    int i;
    if ((t->t & VT_BTYPE) != VT_STRUCT || !t->ref)
        return NULL;
    for (i = 0; i < yh_nb_wraps; i++)
        if (yh_wraps[i].tag == t->ref)
            return &yh_wraps[i];
    return NULL;
}

/* [N]T → 匿名 struct { T a[N]; }（缓存于登记表） */
ST_FUNC void yh_array_wrap(CType *arr, CType *out)
{
    int i;
    struct yh_wrap *w = NULL;
    CType st, ft;
    Sym *tag, *fs;
    AttributeDef ad;

    for (i = 0; i < yh_nb_wraps; i++)
        if (!yh_wraps[i].is_slice && yh_arr_same(&yh_wraps[i].arr, arr)) {
            w = &yh_wraps[i];
            break;
        }
    if (w) {
        *out = w->tag->type;
        out->ref = w->tag;
        return;
    }
    if (yh_nb_wraps >= YH_MAX_WRAPS)
        tcc_error("数组类型种类过多");
    /* 匿名 tag */
    st.t = VT_STRUCT;
    st.ref = NULL;
    tag = sym_push(anon_sym++ | SYM_STRUCT, &st, 0, -1);
    tag->r = 0;
    /* 唯一字段 a：数组类型 */
    ft = *arr;
    fs = sym_push(anon_sym++ | SYM_FIELD, &ft, 0, 0);
    tag->next = fs;
    /* 布局 */
    st.t = VT_STRUCT;
    st.ref = tag;
    memset(&ad, 0, sizeof ad);
    struct_layout(&st, &ad);

    w = &yh_wraps[yh_nb_wraps++];
    w->tag = tag;
    w->arr = *arr;
    w->is_slice = 0;
    *out = st;
}

/* []T → 匿名 struct { u64 len; T *data; }（按元素类型规范化） */
ST_FUNC void yh_slice_wrap(CType *elem, CType *out)
{
    int i;
    struct yh_wrap *w = NULL;
    CType st, ft;
    Sym *tag, *f1, *f2;
    AttributeDef ad;

    for (i = 0; i < yh_nb_wraps; i++)
        if (yh_wraps[i].is_slice
            && yh_wraps[i].elem.t == elem->t
            && yh_wraps[i].elem.ref == elem->ref) {
            w = &yh_wraps[i];
            break;
        }
    if (w) {
        *out = w->tag->type;
        out->ref = w->tag;
        return;
    }
    if (yh_nb_wraps >= YH_MAX_WRAPS)
        tcc_error("切片类型种类过多");
    st.t = VT_STRUCT;
    st.ref = NULL;
    tag = sym_push(anon_sym++ | SYM_STRUCT, &st, 0, -1);
    tag->r = 0;
    ft.t = VT_LLONG | VT_UNSIGNED;
    ft.ref = NULL;
    f1 = sym_push(anon_sym++ | SYM_FIELD, &ft, 0, 0); /* len */
    ft.t = VT_PTR;
    ft.ref = NULL;
    {
        CType pe = *elem;
        ft.ref = sym_push(SYM_FIELD, &pe, 0, 0); /* data 指向元素的匿名类型 */
    }
    f2 = sym_push(anon_sym++ | SYM_FIELD, &ft, 0, 0); /* data */
    tag->next = f1;
    f1->next = f2;
    st.t = VT_STRUCT;
    st.ref = tag;
    memset(&ad, 0, sizeof ad);
    struct_layout(&st, &ad);

    w = &yh_wraps[yh_nb_wraps++];
    w->tag = tag;
    w->elem = *elem;
    w->is_slice = 1;
    *out = st;
}

/* 数组/切片长度：数组→编译期 N；切片→待 M4-02（运行期读 len 字段） */
ST_FUNC int yh_wrap_len(CType *t, long long *out_n)
{
    struct yh_wrap *w;
    if (t->t & VT_ARRAY) {
        *out_n = t->ref->c;
        return 1;
    }
    w = yh_wrap_find(t);
    if (w && !w->is_slice) {
        *out_n = w->arr.ref->c;
        return 1;
    }
    return 0;
}

/* 包装结构体 → 还原数组类型（下标/len 的透明降糖用） */
ST_FUNC int yh_wrap_array_of(CType *t, CType *out)
{
    struct yh_wrap *w = yh_wrap_find(t);
    if (!w || w->is_slice)
        return 0;
    *out = w->arr;
    return 1;
}

/* 数组实参/返回值的边界转换：数组 → 同布局包装结构体（仅改类型字，
   存储不变；拷贝由 gfunc_call/vstore 的结构体路径完成）。 */
ST_FUNC void yh_array_to_wrap(CType *t)
{
    CType st;
    if ((t->t & VT_ARRAY)) {
        yh_array_wrap(t, &st);
        *t = st;
    }
}


/* 判断类型是否为切片包装结构体；w 返回登记项。 */
ST_FUNC int yh_is_slice(CType *t, struct yh_wrap **pw)
{
    struct yh_wrap *w = yh_wrap_find(t);
    if (w && w->is_slice) {
        if (pw)
            *pw = w;
        return 1;
    }
    return 0;
}

/* 切片 struct 左值 → data 字段值（vtop 变为 T* 右值） */
ST_FUNC void yh_slice_data(CType *slice_t)
{
    struct yh_wrap *w;
    CType pt;

    yh_is_slice(slice_t, &w);
    test_lvalue();
    gaddrof();
    vtop->type.t = VT_BYTE;
    mk_pointer(&vtop->type);
    vpushi(8); /* data 字段偏移 */
    gen_op('+');
    pt.t = VT_PTR;
    pt.ref = sym_push(SYM_FIELD, &w->elem, 0, 0); /* T* */
    vtop->type = pt;
    indir();      /* 载入 data 指针值 */
    vtop->type = pt; /* 恢复 T* 类型（indir 会改成元素类型） */
}

/* 切片 struct 左值 → len 字段（u64 右值） */
ST_FUNC void yh_slice_len(CType *slice_t)
{
    struct yh_wrap *w;
    CType pt, u64t;

    yh_is_slice(slice_t, &w);
    (void)w;
    test_lvalue();
    gaddrof();
    vtop->type.t = VT_BYTE;
    mk_pointer(&vtop->type);
    vpushi(0); /* len 字段偏移 */
    gen_op('+');
    /* len 字段以 u64 存储，读取为 int（yh 的 len 返回 int） */
    u64t.t = VT_INT;
    u64t.ref = NULL;
    pt = u64t;
    mk_pointer(&pt);
    vtop->type = pt;
    indir();     /* 载入 len 低 32 位 */
    vtop->type = u64t;
}

/* [N]T 数组左值 → 切片视图临时（{len:N, data:&arr[0]}），结果为切片左值 */
ST_FUNC void yh_array_view(CType *slice_t, long long n)
{
    int size, align, off;

    size = type_size(slice_t, &align);
    loc = (loc - size) & -align;
    off = loc;
    /* data = &arr[0] */
    test_lvalue();
    gaddrof();
    vtop->type.t = VT_LLONG | VT_UNSIGNED; /* data 字段类型 */
    vset(&vtop->type, VT_LOCAL | VT_LVAL, off + 8);
    vswap();
    gen_assign_cast(&vtop[-1].type);
    vstore();
    vpop();
    /* len = N */
    {
        CValue cval;
        CType t;
        t.t = VT_LLONG | VT_UNSIGNED;
        t.ref = NULL;
        cval.i = n;
        vsetc(&t, VT_CONST, &cval);
    }
    vset(&vtop->type, VT_LOCAL | VT_LVAL, off);
    vswap();
    vstore();
    vpop();
    /* 结果：临时切片左值 */
    vset(slice_t, VT_LOCAL | VT_LVAL, off);
}

/* type 别名登记：'type' IDENT '=' typeRef ';' 的主体（yh_decl 调用） */
ST_FUNC void yh_register_type_alias(int v, CType *type)
{
    CType t = *type;
    t.t |= VT_TYPEDEF;
    sym_push(v, &t, 0, 0);
}
