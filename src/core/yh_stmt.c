/* yh_stmt.c —— yh 语句：block、if/for/switch、label/goto、exprStmt，
 * 以及编译模式的控制流代码生成。
 *
 * 对应 docs/yh.g4：block / stmt / ifStmt / forStmt / forInParts /
 * switchStmt / switchCase / returnStmt / branchStmt / gotoStmt /
 * labelStmt / exprStmt。
 *
 * 编译模式（对齐 tccgen block() 的模式）：
 *   - if：gtst(1,0) 取假链 → then → gjmp(0)/gsym → else；
 *   - 条件循环：循环头 ind 记录，条件 gtst 出链，continue 回循环头；
 *   - 无限循环：无出链条件，break 跳出；
 *   - for-in：M4 降糖为下标循环；
 *   - switch：判别值存临时槽，case 值逐个比较，块尾隐式跳到末尾
 *     （无 fallthrough），default 位置自由；
 *   - break/continue：跳转链经 yh_bsym/yh_csym 串接；
 *   - return：值 → gen_assign_cast(func_vt) → gfunc_return，rsym 链；
 *   - goto/label：tccgen 的标签栈（label_find/label_push/label_pop）。
 */

#include "yh.h"

ST_FUNC void gfunc_return(CType *func_type);
ST_FUNC CType *pointed_type(CType *type);
static void gen_cast_s(int t);
static int gvtst(int inv, int t);

/* for-in 编译模式降糖（M4-02）。
 *   for v in arr/slice   → 隐藏切片视图 + 下标循环，绑定值为逐次拷贝
 *   for i, v in arr/slice → 同上并绑定下标
 *   for i in a..b        → 左闭右开区间，空区间执行零次
 * continue 跳到递增点；break 跳出；绑定只在循环体可见（块作用域）。 */
static void yh_parse_for_in_compile(void)
{
    int name1, name2 = 0, has_second = 0;
    int is_range = 0;
    int h_len = 0, h_data = 0, h_idx = 0, h_cur = 0, h_end = 0;
    int b1_off = 0, b2_off = 0;
    CType et, int_t;
    int elem_size, elem_align;
    int saved_bsym = yh_bsym, saved_csym = yh_csym;
    int d, a = 0;
    Sym *scope;

    name1 = tok;
    next();
    if (tok == ',') {
        next();
        name2 = tok;
        has_second = 1;
        next();
    }
    skip(TOK_IN);

    int_t.t = VT_INT;
    int_t.ref = NULL;

    if (yh_syntax_only()) {
        /* 纯语法：按形态消费 */
        yh_parse_expr();
        if (tok == TOK_RANGE) {
            next();
            yh_parse_expr();
        }
        yh_parse_block();
        return;
    }

    nocode_wanted &= ~0x20000000;
    scope = local_stack;
    local_scope++;
    yh_break_depth++;
    yh_cont_depth++;

    /* 先解析首个表达式，再看是否为区间 */
    yh_parse_expr();
    if (tok == TOK_RANGE) {
        is_range = 1;
        next();
    }

    if (is_range) {
        /* 隐藏 cur/end（int） */
        loc = (loc - 4) & -4; h_cur = loc;
        loc = (loc - 4) & -4; h_end = loc;
        /* cur = a（首个表达式已在栈顶） */
        yh_assign_cast_to(&int_t, 0);
        vset(&int_t, VT_LOCAL | VT_LVAL, h_cur);
        vswap();
        vstore();
        vpop();
        /* end = b */
        yh_parse_expr();
        yh_assign_cast_to(&int_t, 0);
        vset(&int_t, VT_LOCAL | VT_LVAL, h_end);
        vswap();
        vstore();
        vpop();
        /* 绑定 i（值拷贝） */
        loc = (loc - 4) & -4;
        b1_off = loc;
        sym_push(name1, &int_t, VT_LOCAL | lvalue_type(int_t.t), b1_off);
    } else {
        /* 数组/切片：求值一次，取 data/len */
        CType it = vtop->type;
        if (it.t & VT_ARRAY) {
            /* 数组：len 编译期常量，data = 数组地址 */
            long long n = it.ref->c;
            et = it.ref->type;
            test_lvalue();
            gaddrof();
            vtop->type.t = VT_LLONG | VT_UNSIGNED; /* 地址位重解释 */
            /* data 存隐藏槽 */
            loc = (loc - 8) & -8; h_data = loc;
            {
                CType p64;
                p64.t = VT_LLONG | VT_UNSIGNED;
                p64.ref = NULL;
                vset(&p64, VT_LOCAL | VT_LVAL, h_data);
                vswap();
                vstore();
                vpop();
            }
            loc = (loc - 4) & -4; h_len = loc;
            {
                CType t = int_t;
                CValue cv;
                cv.i = n;
                vsetc(&t, VT_CONST, &cv);
                vset(&t, VT_LOCAL | VT_LVAL, h_len);
                vswap();
                vstore();
                vpop();
            }
        } else if (yh_is_slice(&it, NULL)) {
            struct yh_wrap *w;
            yh_is_slice(&it, &w);
            et = w->elem;
            /* 切片值拷入隐藏临时（求值一次） */
            loc = (loc - 16) & -8;
            h_data = loc + 8;  /* data 字段 */
            h_len = loc;       /* len 字段 */
            vset(&it, VT_LOCAL | VT_LVAL, loc);
            vswap();
            gen_assign_cast(&it);
            vstore();
            vpop();
        } else {
            tcc_error("for-in 的遍历对象必须是数组或切片");
        }
        elem_size = type_size(&et, &elem_align);
        /* 隐藏下标 */
        loc = (loc - 4) & -4; h_idx = loc;
        /* 绑定 v（元素值拷贝） */
        loc = (loc - elem_size) & -elem_align;
        b1_off = loc;
        sym_push(name1, &et, VT_LOCAL | lvalue_type(et.t), b1_off);
        if (has_second) {
            loc = (loc - 4) & -4;
            b2_off = loc;
            sym_push(name2, &int_t, VT_LOCAL | lvalue_type(int_t.t), b2_off);
        }
        /* idx = 0 */
        {
            CValue cv;
            cv.i = 0;
            vsetc(&int_t, VT_CONST, &cv);
            vset(&int_t, VT_LOCAL | VT_LVAL, h_idx);
            vswap();
            vstore();
            vpop();
        }
    }

    yh_bsym = 0; yh_csym = 0;
    d = ind; /* 循环头 */

    if (is_range) {
        /* cur < end */
        vset(&int_t, VT_LOCAL | VT_LVAL, h_cur);
        vset(&int_t, VT_LOCAL | VT_LVAL, h_end);
        gen_op(TOK_LT);
        a = gvtst(1, 0); /* 假 → 出口 */
        /* i = cur（绑定拷贝） */
        vset(&int_t, VT_LOCAL | VT_LVAL, h_cur);
        vset(&int_t, VT_LOCAL | VT_LVAL, b1_off);
        vswap();
        vstore();
        vpop();
    } else {
        /* idx < len */
        vset(&int_t, VT_LOCAL | VT_LVAL, h_idx);
        vset(&int_t, VT_LOCAL | VT_LVAL, h_len);
        gen_op(TOK_LT);
        a = gvtst(1, 0);
        /* v = data[idx]（元素拷贝） */
        {
            CType pt;
            pt.t = VT_PTR;
            pt.ref = sym_push(SYM_FIELD, &et, 0, 0);
            vset(&pt, VT_LOCAL | VT_LVAL, h_data);
            vset(&int_t, VT_LOCAL | VT_LVAL, h_idx);
            gen_op('+');
            indir();
            yh_assign_cast_to(&et, 0);
            vset(&et, VT_LOCAL | VT_LVAL, b1_off);
            vswap();
            vstore();
            vpop();
        }
        if (has_second) {
            /* i = idx */
            vset(&int_t, VT_LOCAL | VT_LVAL, h_idx);
            vset(&int_t, VT_LOCAL | VT_LVAL, b2_off);
            vswap();
            vstore();
            vpop();
        }
    }

    yh_parse_block();

    if (!yh_syntax_only()) {
        gsym(yh_csym); /* continue → 递增点 */
        yh_csym = 0;
        if (is_range) {
            /* cur += 1 */
            vset(&int_t, VT_LOCAL | VT_LVAL, h_cur);
            vpushi(1);
            gen_op('+');
            vset(&int_t, VT_LOCAL | VT_LVAL, h_cur);
            vswap();
            vstore();
            vpop();
        } else {
            /* idx += 1 */
            vset(&int_t, VT_LOCAL | VT_LVAL, h_idx);
            vpushi(1);
            gen_op('+');
            vset(&int_t, VT_LOCAL | VT_LVAL, h_idx);
            vswap();
            vstore();
            vpop();
        }
        gjmp_addr(d);
        gsym(a);       /* 假 → 出口 */
        gsym(yh_bsym); /* break 出链 */
    }
    yh_break_depth--;
    yh_cont_depth--;
    yh_bsym = saved_bsym; yh_csym = saved_csym;
    sym_pop(&local_stack, scope, 0);
    local_scope--;
}

/* 复合赋值运算符 → 对应二元运算 token */
static int yh_compound_bop(int op, CType *lhs)
{
    switch (op) {
    case TOK_A_ADD: return '+';
    case TOK_A_SUB: return '-';
    case TOK_A_MUL: return '*';
    case TOK_A_DIV: return '/';
    case TOK_A_MOD: return '%';
    case TOK_A_AND: return '&';
    case TOK_A_OR:  return '|';
    case TOK_A_XOR: return '^';
    case TOK_A_SHL: return TOK_SHL;
    default: /* TOK_A_SAR：按目标符号性选算术/逻辑右移 */
        return (lhs->t & VT_UNSIGNED) ? TOK_SHR : TOK_SAR;
    }
}

/* 赋值与表达式语句。 */
static void yh_parse_expr_stmt(void)
{
    SValue *stmt_base = vtop; /* 语句开始时的栈基线 */
    yh_parse_expr();
    switch (tok) {
    case '=': case TOK_A_ADD: case TOK_A_SUB: case TOK_A_MUL:
    case TOK_A_DIV: case TOK_A_MOD: case TOK_A_AND: case TOK_A_OR:
    case TOK_A_XOR: case TOK_A_SHL: case TOK_A_SAR: {
        int op = tok;
        if (!yh_syntax_only())
            test_lvalue(); /* 此时 vtop 正是左侧左值 */
        next();
        /* 数组/切片字面量的目标类型：左值类型 */
        if (!yh_syntax_only()) {
            yh_expect_type = vtop->type;
            yh_expect_valid = 1;
        }
        yh_parse_expr();
        yh_expect_valid = 0;
        if (!yh_syntax_only()) {
            if (op == '=') {
                /* 数组整体赋值：同型 [N]T 转包装结构体走块拷贝 */
                if ((vtop[-1].type.t & VT_ARRAY)
                    && (vtop->type.t & VT_ARRAY)) {
                    yh_array_to_wrap(&vtop[-1].type);
                    yh_array_to_wrap(&vtop->type);
                }
                /* vstore 约定：vtop[-1] = 目标左值，vtop[0] = 值
                   （[lhs, rhs] 天然就是该顺序，不要交换） */
                yh_assign_cast_to(&vtop[-1].type, 0);
                vstore();
            } else {
                /* 复合赋值降糖 a op= b：
                 * [lhs, rhs] → vpushv+vrott(3) → [lhs副本, lhs, rhs]
                 * → gen_op（vtop[-1] 左值自动加载）→ [lhs副本, 结果] → 存回 */
                vpushv(&vtop[-1]);
                vrott(3);
                gen_op(yh_compound_bop(op, &vtop[-1].type));
                gen_assign_cast(&vtop[-1].type);
                vstore();
            }
        }
        break;
    }
    case TOK_AS:
        yh_reserved_hint();
        goto done;
    default:
        break;
    }
done:
    if (!yh_syntax_only() && vtop > stmt_base)
        vpop(); /* 表达式语句丢弃结果（void 调用无值则不弹） */
    skip(';');
}


/* cbz/cbnz 的 imm19 域回填（不走 gsym_addr 的 gjmp 链语义） */
static void yh_patch_cbz(int t, int target)
{
    int off = (target - t) >> 2;
    if (off < -0x40000 || off >= 0x40000)
        tcc_error("switch 分支超出范围");
    write32le(cur_text_section->data + t,
              (read32le(cur_text_section->data + t) & 0xff00001f)
              | ((off & 0x7ffff) << 5));
}

/* b 指令的 imm26 域回填（支持反向，gsym_addr 仅支持正向） */
static void yh_patch_b(int t, int target)
{
    int off = (target - t) >> 2;
    if (off < -0x2000000 || off >= 0x2000000)
        tcc_error("switch b 分支超出范围");
    write32le(cur_text_section->data + t,
              (read32le(cur_text_section->data + t) & 0xfc000000)
              | (off & 0x3ffffff));
}

/* 语句分发。 */
ST_FUNC void yh_parse_stmt(void)
{
    switch (tok) {
    case '{':
        yh_parse_block();
        return;
    case TOK_LET:
        yh_parse_let_decl(1);
        return;
    case TOK_STRUCT:
    case TOK_UNION:
        /* 函数体内嵌套类型声明：登记布局与顶层一致（类型表全局可见） */
        yh_parse_struct_decl(tok == TOK_UNION);
        return;
    case TOK_ENUM:
        yh_parse_enum_decl();
        return;
    case TOK_TYPE:
        yh_parse_type_decl();
        return;
    case TOK_CONST1:
        yh_parse_const_decl();
        return;
    case TOK_IF: {
        int a, b;
        nocode_wanted &= ~0x20000000;
        next();
        skip('(');
        yh_parse_expr();
        skip(')');
        if (yh_syntax_only()) {
            yh_parse_block();
            if (tok == TOK_ELSE) {
                next();
                if (tok == TOK_IF)
                    yh_parse_stmt();
                else
                    yh_parse_block();
            }
            return;
        }
        a = gvtst(1, 0); /* 条件为假的出链 */
        yh_parse_block();
        if (tok == TOK_ELSE) {
            next();
            b = gjmp(0);
            gsym(a);
            if (tok == TOK_IF)
                yh_parse_stmt();
            else
                yh_parse_block();
            gsym(b);
        } else {
            gsym(a);
        }
        return;
    }
    case TOK_FOR: {
        int d, a = 0, saved_bsym, saved_csym;
        nocode_wanted &= ~0x20000000;
        next();
        if (tok == '{') {
            /* 无限循环 */
            saved_bsym = yh_bsym; saved_csym = yh_csym;
            yh_bsym = 0; yh_csym = 0;
            yh_break_depth++;
            d = ind;
            yh_parse_block();
            if (!yh_syntax_only())
                gjmp_addr(d);
            gsym(yh_bsym);
            yh_break_depth--;
            yh_bsym = saved_bsym; yh_csym = saved_csym;
            return;
        }
        if (tok >= TOK_UIDENT) {
            int t1 = yh_peek_next_token();
            if (t1 == TOK_IN || t1 == ',') {
                yh_parse_for_in_compile();
                return;
            }
        }
        /* 条件循环：for cond { body } */
        if (yh_syntax_only()) {
            yh_parse_expr();
            yh_parse_block();
            return;
        }
        saved_bsym = yh_bsym; saved_csym = yh_csym;
        yh_bsym = 0; yh_csym = 0;
        yh_break_depth++;
        yh_cont_depth++;
        d = ind;
        yh_parse_expr();
        a = gvtst(1, 0); /* 条件为假出链 */
        yh_parse_block();
        gsym(yh_csym); /* continue 回循环头 */
        yh_csym = 0;
        gjmp_addr(d);
        gsym(a);
        gsym(yh_bsym); /* break 出链 */
        yh_break_depth--;
        yh_cont_depth--;
        yh_bsym = saved_bsym; yh_csym = saved_csym;
        return;
    }
    case TOK_SWITCH: {
        CType sw_type;
        int sw_slot = 0, pdef = 0, saved_bsym;
        int trues[512], nt = 0;    /* 各 case 比较 cbnz（真→块入口，imm19 回填） */
        int falses[512], nf = 0;   /* 各 case 比较 b（假→下一比较/no-match） */
        int cmp_start[512], ncs = 0; /* 各比较的起始地址（假路径目标） */
        int ends[512], ne = 0;     /* 各块尾跳转（统一到出口） */
        int default_at = 0;        /* default 块入口（出现后记录） */
        nocode_wanted &= ~0x20000000;
        next();
        yh_parse_expr();
        /* 判别值求值一次，存入临时槽（纯语法模式不生成、不求值） */
        if (!yh_syntax_only()) {
            sw_type = vtop->type;
            if ((sw_type.t & VT_BTYPE) == VT_FLOAT
                || (sw_type.t & VT_BTYPE) == VT_DOUBLE)
                tcc_error("switch 判别值暂只支持整数（M3 标量版）");
            loc = (loc - 8) & -8;
            sw_slot = loc;
            vset(&sw_type, VT_LOCAL | VT_LVAL, sw_slot);
            vswap();
            vstore();
            vpop();
        }
        saved_bsym = yh_bsym;
        yh_bsym = 0;
        yh_break_depth++;
        skip('{');
        while (tok != '}') {
            if (tok == TOK_EOF)
                tcc_error("switch 缺少 '}'");
            if (tok == TOK_CASE) {
                next();
                for (;;) {
                    if (!yh_syntax_only()) {
                        /* 超限干净报错而非静默截断（B2-3 容量边界） */
                        if (ncs >= 512 || nt >= 512 || nf >= 512)
                            tcc_error("switch 分支过多"
                                      "（上限 512 个 case 值）");
                        cmp_start[ncs++] = ind; /* 本比较起始（假路径目标） */
                    }
                    yh_parse_expr();
                    if (!yh_syntax_only()) {
                        yh_assign_cast_to(&sw_type, 0);
                        vset(&sw_type, VT_LOCAL | VT_LVAL, sw_slot);
                        vswap();
                        gen_op(TOK_EQ);
                        gv(RC_INT);
                        /* 真 → 块入口（cbnz，块地址稍后回填） */
                        trues[nt++] = ind;
                        o(0x35000000 | intr(vtop->r)); /* cbnz w, #0 */
                        /* 假 → 下一比较 / no-match（b，稍后回填） */
                        falses[nf++] = ind;
                        o(0x14000000); /* b #0 */
                        vpop();
                    }
                    if (tok == ',') {
                        next();
                        continue;
                    }
                    break;
                }
                if (!yh_syntax_only()) {
                    int blk = ind, k;
                    for (k = 0; k < nt; k++)
                        yh_patch_cbz(trues[k], blk);
                    nt = 0;
                }
                yh_parse_block();
                if (!yh_syntax_only()) {
                    if (ne >= 512)
                        tcc_error("switch 分支过多（上限 512 个分支块）");
                    ends[ne++] = gjmp(0); /* 块尾隐式跳出口（无 fallthrough） */
                }
            } else if (tok == TOK_DEFAULT) {
                next();
                if (!yh_syntax_only()) {
                    if (pdef)
                        tcc_error("重复的 default");
                    pdef = 1;
                    default_at = ind;
                }
                yh_parse_block();
                if (!yh_syntax_only()) {
                    if (ne >= 512)
                        tcc_error("switch 分支过多（上限 512 个分支块）");
                    ends[ne++] = gjmp(0);
                }
            } else {
                expect("'case' 或 'default'");
            }
        }
        skip('}');
        if (!yh_syntax_only()) {
            int k;
            int end_ind = ind;
            /* 各比较的假路径：非最后一个 → 下一比较入口（即 +4，转 nop）；
               最后一个 → default 入口或出口 */
            for (k = 0; k < nf; k++)
                yh_patch_b(falses[k],
                           k + 1 < ncs ? cmp_start[k + 1]
                                       : (default_at ? default_at : end_ind));
            for (k = 0; k < ne; k++)
                gsym_addr(ends[k], end_ind);
            gsym(yh_bsym); /* break 出链 */
        }
        yh_break_depth--;
        yh_bsym = saved_bsym;
        return;
    }
    case TOK_RETURN:
        next();
        if (tok != ';') {
            yh_parse_expr();
            if (!yh_syntax_only()) {
                if ((func_vt.t & VT_BTYPE) == VT_VOID)
                    tcc_error("void 函数不能返回值");
                yh_assign_cast_to(&func_vt, 0);
                gfunc_return(&func_vt);
            }
        } else if (!yh_syntax_only()
                   && (func_vt.t & VT_BTYPE) != VT_VOID) {
            tcc_error("非 void 函数必须有返回值");
        }
        skip(';');
        if (!yh_syntax_only()) {
            rsym = gjmp(rsym);
            nocode_wanted |= 0x20000000;
        }
        return;
    case TOK_BREAK:
        next();
        skip(';');
        if (!yh_syntax_only()) {
            if (yh_break_depth == 0)
                tcc_error("break 不在循环或 switch 内");
            yh_bsym = gjmp(yh_bsym);
            nocode_wanted |= 0x20000000;
        }
        return;
    case TOK_CONTINUE:
        next();
        skip(';');
        if (!yh_syntax_only()) {
            if (yh_cont_depth == 0)
                tcc_error("continue 不在循环内");
            yh_csym = gjmp(yh_csym);
            nocode_wanted |= 0x20000000;
        }
        return;
    case TOK_GOTO: {
        int v;
        Sym *s;
        next();
        if (tok < TOK_UIDENT)
            expect("标签名");
        v = tok;
        next();
        skip(';');
        if (!yh_syntax_only()) {
            s = label_find(v);
            if (!s)
                s = label_push(&global_label_stack, v, LABEL_FORWARD);
            if (s->r == LABEL_DECLARED)
                s->r = LABEL_FORWARD;
            /* 前向跳转：gjmp 的结果串到标签链 */
            if (s->r & LABEL_FORWARD)
                s->c = gjmp(s->c);
            else
                gjmp_addr(s->c);
            nocode_wanted |= 0x20000000;
        }
        return;
    }
    default:
        if (tok >= TOK_UIDENT && yh_peek_next_token() == ':') {
            /* 标签：IDENT ':' stmt */
            int v = tok;
            Sym *s;
            next();
            skip(':');
            if (!yh_syntax_only()) {
                s = label_find(v);
                if (!s) {
                    s = label_push(&global_label_stack, v, LABEL_DECLARED);
                    s->c = 0;
                } else {
                    if (!(s->r & LABEL_FORWARD))
                        tcc_error("重复的标签 '%s'", get_tok_str(v, NULL));
                }
                s->r = LABEL_DEFINED;
                gsym_addr(s->c, ind);
                s->c = ind;
                nocode_wanted &= ~0x20000000; /* 标签后代码重新可达 */
            }
            yh_parse_stmt();
            return;
        }
        yh_parse_expr_stmt();
        return;
    }
}

/* block：'{' stmt* '}'。
 * nocode_wanted 的 0x20000000 位（return 后死代码）在块级保存/恢复：
 * 块内 return 之后的语句不再生成代码，块结束后恢复外层状态。 */
ST_FUNC void yh_parse_block(void)
{
    int saved_nocode = nocode_wanted;
    skip('{');
    while (tok != '}') {
        if (tok == TOK_EOF)
            tcc_error("块缺少 '}'");
        yh_parse_stmt();
    }
    skip('}');
    nocode_wanted = saved_nocode;
}
