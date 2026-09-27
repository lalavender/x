/* yh_decl.c —— yh 顶层/局部声明解析、两遍编译入口与函数框架生成。
 *
 * 对应 docs/yh.g4：sourceFile / topLevelDecl / letDecl / binding /
 * constDecl / fnDecl / param / typeDecl。
 *
 * 两遍编译（语义边界文档 §1）：
 *   第一遍：按源码顺序登记 type/struct/union/enum 完整定义与顶层 fn
 *           签名（external_global_sym；pub→GLOBAL，非 pub→VT_STATIC/
 *           LOCAL），函数体与全局初始化跳过；
 *   第二遍：跳过类型声明，按顺序落地全局 let/const，逐个生成函数体。
 *   约束：类型名先声明后引用；函数可前向调用；全局初始化按声明顺序求值。
 *
 * 局部变量：loc 下移分配槽（VT_LOCAL 左值），初始化走值栈
 * （值 + 目标左值 → gen_assign_cast → vstore）。
 */

#include "yh.h"

ST_FUNC void gfunc_return(CType *func_type);

/* 当前编译状态（仅编译模式使用） */
int yh_pass;                /* 1=扫描登记，2=编译生成 */
static int yh_cur_pub;      /* 当前顶层声明是否 pub */
int yh_bsym;                /* break 跳转链（yh_stmt 使用） */
int yh_csym;                /* continue 跳转链（yh_stmt 使用） */
int yh_break_depth;         /* break 可用深度（for/switch 内 >0） */
int yh_cont_depth;          /* continue 可用深度（循环内 >0） */
int yh_has_init_flag;       /* binding 是否带初值 */
int yh_bind_name;           /* 当前绑定名 token */
int yh_at_global_scope;     /* 当前绑定是否在顶层（全局 let/const） */

/* ---- 前向声明 ---- */
static void yh_parse_fn_decl(void);
static int yh_fn_is_variadic;
ST_FUNC void yh_commit_local_var(CType *type);
ST_FUNC void yh_commit_global_var(CType *type);
ST_FUNC void yh_register_const(int v, CType *type);

/* ------------------------------------------------------------------ */
/* 变量与常量落地                                                       */
/* ------------------------------------------------------------------ */

/* 局部变量落地：分配栈槽、登记 Sym；值栈顶是初始化值（或无）。
 * 由 binding 解析路径调用（编译模式）。 */
ST_FUNC void yh_commit_local_var(CType *type)
{
    int v, size, align, has_init;

    v = yh_bind_name;
    has_init = yh_has_init_flag;
    size = type_size(type, &align);
    loc = (loc - size) & -align;
    sym_push(v, type, VT_LOCAL | lvalue_type(type->t), loc);
    if (has_init) {
        /* 值栈顶：初始化值 → 目标左值 → 存储 */
        yh_assign_cast_to(type, 0);
        vset(type, VT_LOCAL | VT_LVAL, loc);
        vswap();
        vstore();
        vpop(); /* 存储完成后丢弃赋值结果 */
    } else {
        /* 零值初始化：bss 语义，无需生成代码 */
    }
}

/* 顶层变量落地：在 data/bss 节分配并登记 ELF 符号。
 * pub→GLOBAL，非 pub→VT_STATIC（LOCAL）；初始化值为编译期常量
 * （标量直接写字节）或字符串符号引用（写 R_DATA_PTR 重定位）。 */
ST_FUNC void yh_commit_global_var(CType *type)
{
    int v = yh_bind_name, size, align, has_init = yh_has_init_flag;
    Section *sec;
    addr_t addr;
    Sym *s;

    size = type_size(type, &align);
    sec = has_init ? data_section : bss_section;
    addr = section_add(sec, size, align);
    s = sym_push(v, type, VT_CONST | VT_SYM | lvalue_type(type->t), 0);
    s->sym_scope = 0;
    if (!yh_cur_pub)
        s->type.t |= VT_STATIC;
    put_extern_sym(s, sec, addr, size);
    if (has_init) {
        if (vtop->r & VT_SYM) {
            /* 字符串地址：写 8 字节重定位 */
            greloca(sec, vtop->sym, addr, R_DATA_PTR, 0);
            vpop();
        } else {
            /* 标量常量：按类型宽度写入节数据（小端） */
            int bt = type->t & VT_BTYPE;
            unsigned char *p = sec->data + addr;
            if (bt == VT_FLOAT) {
                float f = vtop->c.f;
                memcpy(p, &f, 4);
            } else if (bt == VT_DOUBLE || bt == VT_LDOUBLE) {
                double dd = vtop->c.d;
                memcpy(p, &dd, 8);
            } else {
                unsigned long long u = (unsigned long long)vtop->c.i;
                int n = size < 8 ? size : 8, k;
                for (k = 0; k < n; k++)
                    p[k] = (unsigned char)(u >> (8 * k));
            }
            vpop();
        }
    }
}

/* 编译期常量登记：值栈顶是 expr_const1 的常量值。
 * 64 位值存 Sym.enum_val（Sym.c 只有 32 位）。 */
ST_FUNC void yh_register_const(int v, CType *type)
{
    Sym *s;

    s = sym_push(v, type, VT_CONST, 0);
    s->enum_val = vtop->c.i; /* 常量值存 enum_val（64 位） */
    vpop();
}

/* ------------------------------------------------------------------ */
/* 声明解析                                                            */
/* ------------------------------------------------------------------ */

/* binding：IDENT typeRef ('=' expr)?。类型必写，不允许省略。 */
static void yh_parse_binding(void)
{
    CType type;
    int v, has_init;

    if (tok < TOK_UIDENT) {
        if (tok == TOK_LEN || tok == TOK_TYPE || tok == TOK_IN
            || tok == TOK_SIZEOF || tok == TOK_FOR || tok == TOK_IF)
            tcc_error("'%s' 是保留字，不能作绑定名", get_tok_str(tok, NULL));
        expect("绑定名");
    }
    v = tok;
    next();
    type.t = VT_INT;
    type.ref = NULL;
    yh_parse_type_ref(&type);
    has_init = (tok == '=');
    if (has_init) {
        next();
        if (yh_pass == 1) {
            /* 第一遍只登记名字与类型：初始化器按括号配对跳过
               （skip_or_save_block 停在顶层 ',' 或 ';' 且不消费） */
            skip_or_save_block(NULL);
            return;
        }
        if (yh_at_global_scope && !yh_syntax_only()) {
            if (tok == TOK_STR) {
                /* 字符串字面量：落地为匿名 char 数组，压入符号引用 */
                CType st;
                AttributeDef ad;
                st.t = VT_BYTE | VT_ARRAY;
                mk_pointer(&st);
                st.t |= VT_ARRAY;
                memset(&ad, 0, sizeof ad);
                decl_initializer_alloc(&st, &ad, VT_CONST, 2, 0, 0);
            } else {
                /* 其余全局初始化必须是编译期常量 */
                const_wanted = 1;
                expr_const1();
                const_wanted = 0;
            }
        } else {
            yh_parse_expr();
        }
    }
    if (yh_syntax_only())
        return;
    if (yh_at_global_scope) {
        yh_has_init_flag = has_init;
        yh_bind_name = v;
        yh_commit_global_var(&type);
    } else {
        yh_has_init_flag = has_init;
        yh_bind_name = v;
        yh_commit_local_var(&type);
    }
}

ST_FUNC void yh_parse_let_decl(int local)
{
    next(); /* 消费 'let' */
    if (local)
        yh_at_global_scope = 0;
    for (;;) {
        yh_parse_binding();
        if (tok == ',') {
            next();
            continue;
        }
        break;
    }
    skip(';');
}

ST_FUNC void yh_parse_const_decl(void)
{
    CType type;
    int v;

    next(); /* 消费 'const' */
    if (tok < TOK_UIDENT)
        expect("常量名");
    v = tok;
    next();
    type.t = VT_INT;
    type.ref = NULL;
    yh_parse_type_ref(&type);
    skip('=');
    if (yh_syntax_only()) {
        yh_parse_expr();
    } else if (yh_pass == 1) {
        skip_or_save_block(NULL); /* 第一遍不做常量求值 */
    } else {
        const_wanted = 1;
        expr_const1();
        const_wanted = 0;
        yh_register_const(v, &type);
    }
    skip(';');
}

/* param：IDENT [ELLIPSIS] typeRef | ELLIPSIS。
 * 在 fn 声明头部调用；编译模式把参数挂到 *pps 链上（带名）。 */
static int yh_last_param_variadic;

static void yh_parse_param(Sym ***pps)
{
    CType type;
    int v = 0;
    yh_last_param_variadic = 0;

    if (tok == TOK_DOTS) {
        if (!yh_syntax_only())
            tcc_error("用户源码不允许裸 '...'（仅编译器内置 prelude 可用）");
        next();
        return;
    }
    { int variadic = 0;
    if (tok < TOK_UIDENT)
        expect("参数名");
    v = tok;
    next();
    if (tok == TOK_DOTS) {
        variadic = 1;
        next();
    }
    type.t = VT_INT;
    type.ref = NULL;
    yh_parse_type_ref(&type);
    /* 数组形参在调用边界降糖为包装结构体（ADR-0002），函数体内
       通过下标/len 的透明降糖保持数组语义 */
    if (!yh_syntax_only()) {
        Sym *p;
        if (variadic) {
            /* 类型化变参：形参类型 T → []T（函数体内即切片，CONTEXT.md） */
            CType et = type, sl;
            yh_slice_wrap(&et, &sl);
            type = sl;
            if (tok != ')')
                tcc_error("类型化变参只能在参数表末尾出现一次");
        }
        yh_array_to_wrap(&type);
        p = sym_push(v | SYM_FIELD, &type, 0, 0);
        if (variadic)
            p->a.packed = 1; /* 标记：类型化变参形参（借用 packed 位） */
        **pps = p;
        *pps = &p->next;
    }
    yh_last_param_variadic = variadic;
    }
}

/* fnDecl：'fn' IDENT '(' paramList? ')' typeRef? block */
static void yh_parse_fn_decl(void)
{
    CType ft, ret, fake;
    Sym *first = NULL, **ps = &first;
    int v;

    next(); /* 消费 'fn' */
    if (tok < TOK_UIDENT)
        expect("函数名");
    v = tok;
    next();
    skip('(');
    yh_fn_is_variadic = 0;
    if (tok != ')') {
        for (;;) {
            yh_parse_param(&ps);
            if (yh_last_param_variadic)
                yh_fn_is_variadic = 1;
            if (tok == ',') {
                next();
                continue;
            }
            break;
        }
    }
    skip(')');
    if (yh_tok_starts_type_ref(tok))
        yh_parse_type_ref(&ret);
    else {
        ret.t = VT_VOID;
        ret.ref = NULL;
    }
    /* 数组返回值降糖为包装结构体（函数体内 return arr 处再转换） */
    if (!yh_syntax_only() && yh_pass == 1)
        yh_array_to_wrap(&ret);

    if (yh_pass == 1) {
        /* 登记签名 */
        Sym *fs;
        fake.t = VT_INT;
        fake.ref = NULL;
        fs = sym_push(SYM_FIELD, &fake, 0, 0);
        fs->type = ret;
        fs->next = first;
        fs->f.func_call = FUNC_CDECL;
        fs->f.func_type = yh_fn_is_variadic ? FUNC_ELLIPSIS : FUNC_CDECL;
        ft.t = VT_FUNC;
        ft.ref = fs;
        /* pub→GLOBAL；非 pub→VT_STATIC（ELF LOCAL）；main 恒为 GLOBAL
         * （crt 引用入口，语义边界文档 §2）。ELF 绑定由
         * type.t & VT_STATIC 在 put_extern_sym 时决定。 */
        {
            Sym *fsym;
            const char *nm = get_tok_str(v, NULL);
            fsym = external_global_sym(v, &ft, 0);
            if (!yh_cur_pub && strcmp(nm, "main") != 0)
                fsym->type.t |= VT_STATIC;
        }
        skip_or_save_block(NULL); /* 跳过函数体 */
        return;
    }

    /* 第二遍：纯语法模式只解析形态；编译模式生成函数体 */
    if (yh_syntax_only()) {
        if (tok != '{')
            tcc_error("函数必须带函数体");
        yh_parse_block();
        return;
    }
    cur_text_section = text_section;
    yh_gen_function(v);
}

/* 第一遍跳过类型声明（已在第一遍登记） */
static void yh_skip_type_decl(void)
{
    next(); /* 'type' */
    next(); /* IDENT */
    skip('=');
    while (tok != ';' && tok != TOK_EOF)
        next();
    skip(';');
}

/* typeDecl：'type' IDENT '=' typeRef ';' */
static void yh_parse_type_decl(void)
{
    CType type;
    int v;

    next(); /* 消费 'type' */
    if (tok < TOK_UIDENT)
        expect("类型名");
    v = tok;
    next();
    skip('=');
    type.t = VT_INT;
    type.ref = NULL;
    yh_parse_type_ref(&type);
    skip(';');
    if (!yh_syntax_only())
        yh_register_type_alias(v, &type);
}

/* 顶层/局部声明体分派（不含 pub，pub 由 yh_parse_top_decl 处理） */
static void yh_parse_decl_body(void)
{
    switch (tok) {
    case TOK_LET:
        yh_parse_let_decl(0);
        return;
    case TOK_CONST1:
        yh_parse_const_decl();
        return;
    case TOK_FN:
        yh_parse_fn_decl();
        return;
    case TOK_TYPE:
        if (yh_pass == 2 && !yh_syntax_only()) {
            yh_skip_type_decl(); /* 第一遍已登记 */
            return;
        }
        yh_parse_type_decl();
        return;
    case TOK_STRUCT:
    case TOK_UNION:
        if (yh_pass == 2 && !yh_syntax_only()) {
            /* 第一遍已登记：跳过整个声明 */
            next();
            next();
            if (tok == '{')
                skip_or_save_block(NULL);
            return;
        }
        yh_parse_struct_decl(tok == TOK_UNION);
        return;
    case TOK_ENUM:
        if (yh_pass == 2 && !yh_syntax_only()) {
            next();
            next();
            if (tok == '{')
                skip_or_save_block(NULL);
            return;
        }
        yh_parse_enum_decl();
        return;
    default:
        expect("顶层声明（let/const/fn/type/struct/union/enum）");
    }
}

/* topLevelDecl：'pub'? topLevelDeclBody（pub 仅顶层合法） */
static void yh_parse_top_decl(void)
{
    yh_cur_pub = 0;
    if (tok == TOK_PUB) {
        yh_cur_pub = 1;
        next();
    }
    yh_at_global_scope = 1;
    yh_parse_decl_body();
    yh_at_global_scope = 0;
}

ST_FUNC void yh_parse_translation_unit(void)
{
    while (tok != TOK_EOF) {
        yh_parse_top_decl();
        if (tcc_state->nb_errors)
            return;
    }
}

/* ------------------------------------------------------------------ */
/* 函数框架生成（对齐 tccgen gen_function）                              */
/* ------------------------------------------------------------------ */

/* 生成函数：查第一遍登记的 Sym，prolog → 函数体 → epilog。 */
ST_FUNC void yh_gen_function(int v)
{
    Sym *sym;
    int saved_bsym = yh_bsym, saved_csym = yh_csym;

    sym = sym_find(v);
    if (!sym || (sym->type.t & VT_BTYPE) != VT_FUNC)
        tcc_error("函数 '%s' 未在第一遍登记", get_tok_str(v, NULL));
    if (!strcmp(get_tok_str(v, NULL), "main")) {
        if (sym->type.ref->next)
            tcc_error("main 不能带参数");
        if ((sym->type.ref->type.t & VT_BTYPE) == VT_VOID)
            tcc_warning("main 建议返回 int（void 时退出码恒为 0）");
    }
    if (!(sym->type.t & VT_EXTERN))
        tcc_error("重定义 '%s'", get_tok_str(v, NULL));
    sym->type.t &= ~VT_EXTERN;

    nocode_wanted = 0;
    ind = cur_text_section->data_offset;
    put_extern_sym(sym, cur_text_section, ind, 0);
    funcname = get_tok_str(sym->v, NULL);
    tcc_debug_funcstart(tcc_state, sym);
    sym_push2(&local_stack, SYM_FIELD, 0, 0);
    local_scope = 1;
    gfunc_prolog(&sym->type);
    local_scope = 0;
    rsym = 0;
    yh_bsym = 0;
    yh_csym = 0;

    if (tok != '{')
        tcc_error("函数必须带函数体");
    yh_parse_block();

    /* 函数末尾：void 函数确定性清零 x0（退出码可预期） */
    nocode_wanted = 0;
    gsym(rsym);
    if ((func_vt.t & VT_BTYPE) == VT_VOID)
        o(0x52800000); /* mov w0, #0 */
    gfunc_epilog();
    cur_text_section->data_offset = ind;
    label_pop(&global_label_stack, NULL, 0);
    local_scope = 0;
    sym_pop(&local_stack, NULL, 0);
    elfsym(sym)->st_size = ind - func_ind;
    tcc_debug_funcend(tcc_state, ind - func_ind);
    cur_text_section = NULL;
    funcname = "";
    func_vt.t = VT_VOID;
    ind = 0;
    nocode_wanted = 0x80000000;
    check_vstack();
    yh_bsym = saved_bsym;
    yh_csym = saved_csym;
}

/* ------------------------------------------------------------------ */
/* 编译入口                                                            */
/* ------------------------------------------------------------------ */

/* 第一遍：登记类型与函数签名（在当前已打开的文件上扫描一遍）。 */
static void yh_pass1(void)
{
    yh_pass = 1;
    next();
    yh_parse_translation_unit();
}

ST_FUNC int yh_compile(TCCState *s1)
{
    char *filename;

    s1->yh_mode = 1;

    if (setjmp(s1->error_jmp_buf) == 0) {
        s1->nb_errors = 0;
        s1->error_set_jmp_enabled = 1;

        preprocess_start(s1, 0);
        parse_flags = PARSE_FLAG_TOK_NUM | PARSE_FLAG_TOK_STR;

        /* 对齐 tccgen_compile 的全局初始化（匿名符号、公共类型等） */
        funcname = "";
        anon_sym = SYM_FIRST_ANOM;
        section_sym = 0;
        const_wanted = 0;
        nocode_wanted = 0x80000000;
        int_type.t = VT_INT;
        char_pointer_type.t = VT_BYTE;
        mk_pointer(&char_pointer_type);
        size_type.t = VT_LLONG | VT_UNSIGNED;
        ptrdiff_type.t = VT_LLONG;
        func_old_type.t = VT_FUNC;
        func_old_type.ref = sym_push(SYM_FIELD, &int_type, 0, 0);
        func_old_type.ref->f.func_call = FUNC_CDECL;
        func_old_type.ref->f.func_type = FUNC_OLD;
        tcc_debug_start(s1);

        tccelf_begin_file(s1);
        if (!yh_syntax_only()) {
            /* 两遍：先登记 prelude 与顶层签名，再重读文件编译 */
            yh_register_prelude();
            yh_pass1();
            if (s1->nb_errors == 0) {
                /* 重开文件做第二遍 */
                filename = tcc_strdup(file->filename);
                tcc_close();
                if (tcc_open(s1, filename) < 0)
                    tcc_error("无法重新打开 '%s'", filename);
                tcc_free(filename);
                preprocess_start(s1, 0);
                parse_flags = PARSE_FLAG_TOK_NUM | PARSE_FLAG_TOK_STR;
                yh_pass = 2;
                next();
                yh_parse_translation_unit();
            }
        } else {
            /* 纯语法模式：一遍即可 */
            yh_pass = 2;
            next();
            yh_parse_translation_unit();
        }

        tccelf_end_file(s1); /* 合并本编译单元的符号（含 UNDEF→外部） */
        tcc_debug_end(s1);
        preprocess_end(s1);
        check_vstack();
    }
    s1->error_set_jmp_enabled = 0;
    s1->yh_mode = 0;
    yh_pass = 0;
    return s1->nb_errors != 0 ? -1 : 0;
}
