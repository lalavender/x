/*
 *  TCC 的类 GAS 汇编器
 *
 *  Copyright (c) 2001-2004 Fabrice Bellard
 *
 * 本库为自由软件；你可以遵照自由软件基金会发布的 GNU 宽通用公共许可证
 * 的条款重新分发和/或修改它，无论是许可证的第 2 版，还是（由你选择的）
 * 任何更新的版本。
 *
 * 分发本库是希望它有用，但不提供任何担保；
 * 甚至不提供对适销性或特定用途适用性的默示担保。
 * 详见 GNU 宽通用公共许可证。
 *
 * 你应当已经随本库收到一份 GNU 宽通用公共许可证的副本；
 * 如果没有，请写信给自由软件基金会：
 * 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 */

#include "tcc.h"
#ifdef CONFIG_TCC_ASM

ST_FUNC int asm_get_local_label_name(TCCState *s1, unsigned int n) {
  char buf[64];
  TokenSym *ts;

  snprintf(buf, sizeof(buf), "L..%u", n);
  ts = tok_alloc(buf, strlen(buf));
  return ts->tok;
}

static int tcc_assemble_internal(TCCState *s1, int do_preprocess, int global);
static Sym *asm_new_label(TCCState *s1, int label, int is_local);
static Sym *asm_new_label1(TCCState *s1, int label, int is_local, int sh_num,
                           int value);

static Sym *asm_label_find(int v) {
  Sym *sym = sym_find(v);
  while (sym && sym->sym_scope)
    sym = sym->prev_tok;
  return sym;
}

static Sym *asm_label_push(int v) {
  /* 我们总是加上 VT_EXTERN，对符号定义而言这是暂定定义
     （对 .set 而言如此，真正的定义会去掉它），对单纯的引用来说
     这样本来就正确。  */
  Sym *sym = global_identifier_push(v, VT_ASM | VT_EXTERN | VT_STATIC, 0);
  sym->r = VT_CONST | VT_SYM;
  return sym;
}

/* 返回一个可在汇编器内部使用的符号，名字为 NAME。
   来自 asm 和 C 源码的符号共用同一个命名空间。如果我们生成
   一个 asm 符号，它同时也是一个（文件级的）C 符号，但它
   要么不能按名字访问（如 "L.123"），要么其类型信息
   使得它没有正确的 C 声明就无法使用。

   有时我们需要在 asm 中按名字访问、而在 C 中是匿名的
   符号，这时可以用 CSYM 把该符号的所有信息转移到
   （可能是新建的）asm 符号上。
    */
ST_FUNC Sym *get_asm_sym(int name, Sym *csym) {
  Sym *sym = asm_label_find(name);
  if (!sym) {
    sym = asm_label_push(name);
    if (csym)
      sym->c = csym->c;
  }
  return sym;
}

static Sym *asm_section_sym(TCCState *s1, Section *sec) {
  char buf[100];
  int label = tok_alloc(buf, snprintf(buf, sizeof buf, "L.%s", sec->name))->tok;
  Sym *sym = asm_label_find(label);
  return sym ? sym : asm_new_label1(s1, label, 1, sec->sh_num, 0);
}

/* 我们不用 C 表达式解析器来处理符号。也许可以
   调整 C 表达式解析器让它来做这件事。 */

static void asm_expr_unary(TCCState *s1, ExprValue *pe) {
  Sym *sym;
  int op, label;
  uint64_t n;
  const char *p;

  switch (tok) {
  case TOK_PPNUM:
    p = tokc.str.data;
    n = strtoull(p, (char **)&p, 0);
    if (*p == 'b' || *p == 'f') {
      /* 向后或向前标签 */
      label = asm_get_local_label_name(s1, n);
      sym = asm_label_find(label);
      if (*p == 'b') {
        /* 向后：找到最后一个对应且已定义的标签 */
        if (sym && (!sym->c || elfsym(sym)->st_shndx == SHN_UNDEF))
          sym = sym->prev_tok;
        if (!sym)
          tcc_error("local label '%d' not found backward", n);
      } else {
        /* 向前 */
        if (!sym || (sym->c && elfsym(sym)->st_shndx != SHN_UNDEF)) {
          /* 如果最后一个标签已定义，则定义一个新的 */
          sym = asm_label_push(label);
        }
      }
      pe->v = 0;
      pe->sym = sym;
      pe->pcrel = 0;
    } else if (*p == '\0') {
      pe->v = n;
      pe->sym = NULL;
      pe->pcrel = 0;
    } else {
      tcc_error("invalid number syntax");
    }
    next();
    break;
  case '+':
    next();
    asm_expr_unary(s1, pe);
    break;
  case '-':
  case '~':
    op = tok;
    next();
    asm_expr_unary(s1, pe);
    if (pe->sym)
      tcc_error("invalid operation with label");
    if (op == '-')
      pe->v = -pe->v;
    else
      pe->v = ~pe->v;
    break;
  case TOK_CCHAR:
  case TOK_LCHAR:
    pe->v = tokc.i;
    pe->sym = NULL;
    pe->pcrel = 0;
    next();
    break;
  case '(':
    next();
    asm_expr(s1, pe);
    skip(')');
    break;
  case '.':
    pe->v = ind;
    pe->sym = asm_section_sym(s1, cur_text_section);
    pe->pcrel = 0;
    next();
    break;
  default:
    if (tok >= TOK_IDENT) {
      ElfSym *esym;
      /* 标签情形：如果没找到该标签，就添加一个 */
      sym = get_asm_sym(tok, NULL);
      esym = elfsym(sym);
      if (esym && esym->st_shndx == SHN_ABS) {
        /* 如果是绝对符号，就不需要放入符号值 */
        pe->v = esym->st_value;
        pe->sym = NULL;
        pe->pcrel = 0;
      } else {
        pe->v = 0;
        pe->sym = sym;
        pe->pcrel = 0;
      }
      next();
    } else {
      tcc_error("bad expression syntax [%s]", get_tok_str(tok, &tokc));
    }
    break;
  }
}

static void asm_expr_prod(TCCState *s1, ExprValue *pe) {
  int op;
  ExprValue e2;

  asm_expr_unary(s1, pe);
  for (;;) {
    op = tok;
    if (op != '*' && op != '/' && op != '%' && op != TOK_SHL && op != TOK_SAR)
      break;
    next();
    asm_expr_unary(s1, &e2);
    if (pe->sym || e2.sym)
      tcc_error("invalid operation with label");
    switch (op) {
    case '*':
      pe->v *= e2.v;
      break;
    case '/':
      if (e2.v == 0) {
      div_error:
        tcc_error("division by zero");
      }
      pe->v /= e2.v;
      break;
    case '%':
      if (e2.v == 0)
        goto div_error;
      pe->v %= e2.v;
      break;
    case TOK_SHL:
      pe->v <<= e2.v;
      break;
    default:
    case TOK_SAR:
      pe->v >>= e2.v;
      break;
    }
  }
}

static void asm_expr_logic(TCCState *s1, ExprValue *pe) {
  int op;
  ExprValue e2;

  asm_expr_prod(s1, pe);
  for (;;) {
    op = tok;
    if (op != '&' && op != '|' && op != '^')
      break;
    next();
    asm_expr_prod(s1, &e2);
    if (pe->sym || e2.sym)
      tcc_error("invalid operation with label");
    switch (op) {
    case '&':
      pe->v &= e2.v;
      break;
    case '|':
      pe->v |= e2.v;
      break;
    default:
    case '^':
      pe->v ^= e2.v;
      break;
    }
  }
}

static inline void asm_expr_sum(TCCState *s1, ExprValue *pe) {
  int op;
  ExprValue e2;

  asm_expr_logic(s1, pe);
  for (;;) {
    op = tok;
    if (op != '+' && op != '-')
      break;
    next();
    asm_expr_logic(s1, &e2);
    if (op == '+') {
      if (pe->sym != NULL && e2.sym != NULL)
        goto cannot_relocate;
      pe->v += e2.v;
      if (pe->sym == NULL && e2.sym != NULL)
        pe->sym = e2.sym;
    } else {
      pe->v -= e2.v;
      /* 注意：这种情况下我们不如 gas 强大，
         因为表达式中只保存一个符号 */
      if (!e2.sym) {
        /* 可以 */
      } else if (pe->sym == e2.sym) {
        /* 可以 */
        pe->sym = NULL; /* 相同的符号相减可以得到 NULL */
      } else {
        ElfSym *esym1, *esym2;
        esym1 = elfsym(pe->sym);
        esym2 = elfsym(e2.sym);
        if (esym1 && esym1->st_shndx == esym2->st_shndx &&
            esym1->st_shndx != SHN_UNDEF) {
          /* 我们也接受同一段中已定义的符号 */
          pe->v += esym1->st_value - esym2->st_value;
          pe->sym = NULL;
        } else if (esym2->st_shndx == cur_text_section->sh_num) {
          /* 减去当前段中已定义的符号时，
             这实际上使该值成为 PC 相对值。  */
          pe->v -= esym2->st_value - ind - 4;
          pe->pcrel = 1;
          e2.sym = NULL;
        } else {
        cannot_relocate:
          tcc_error("invalid operation with label");
        }
      }
    }
  }
}

static inline void asm_expr_cmp(TCCState *s1, ExprValue *pe) {
  int op;
  ExprValue e2;

  asm_expr_sum(s1, pe);
  for (;;) {
    op = tok;
    if (op != TOK_EQ && op != TOK_NE && (op > TOK_GT || op < TOK_ULE))
      break;
    next();
    asm_expr_sum(s1, &e2);
    if (pe->sym || e2.sym)
      tcc_error("invalid operation with label");
    switch (op) {
    case TOK_EQ:
      pe->v = pe->v == e2.v;
      break;
    case TOK_NE:
      pe->v = pe->v != e2.v;
      break;
    case TOK_LT:
      pe->v = (int64_t)pe->v < (int64_t)e2.v;
      break;
    case TOK_GE:
      pe->v = (int64_t)pe->v >= (int64_t)e2.v;
      break;
    case TOK_LE:
      pe->v = (int64_t)pe->v <= (int64_t)e2.v;
      break;
    case TOK_GT:
      pe->v = (int64_t)pe->v > (int64_t)e2.v;
      break;
    default:
      break;
    }
    /* GAS 的比较结果是 -1/0 而不是 1/0。  */
    pe->v = -(int64_t)pe->v;
  }
}

ST_FUNC void asm_expr(TCCState *s1, ExprValue *pe) { asm_expr_cmp(s1, pe); }

ST_FUNC int asm_int_expr(TCCState *s1) {
  ExprValue e;
  asm_expr(s1, &e);
  if (e.sym)
    expect("constant");
  return e.v;
}

static Sym *asm_new_label1(TCCState *s1, int label, int is_local, int sh_num,
                           int value) {
  Sym *sym;
  ElfSym *esym;

  sym = asm_label_find(label);
  if (sym) {
    esym = elfsym(sym);
    /* 带 VT_EXTERN 的符号即使有段也被视为
       可覆盖。我们就是这样“定义” .set 目标的。真正的
       定义不会置 VT_EXTERN。  */
    if (esym && esym->st_shndx != SHN_UNDEF) {
      /* 该标签已经定义 */
      if (IS_ASM_SYM(sym) && (is_local == 1 || (sym->type.t & VT_EXTERN)))
        goto new_label;
      if (!(sym->type.t & VT_EXTERN))
        tcc_error("assembler label '%s' already defined",
                  get_tok_str(label, NULL));
    }
  } else {
  new_label:
    sym = asm_label_push(label);
  }
  if (!sym->c)
    put_extern_sym2(sym, SHN_UNDEF, 0, 0, 0);
  esym = elfsym(sym);
  esym->st_shndx = sh_num;
  esym->st_value = value;
  if (is_local != 2)
    sym->type.t &= ~VT_EXTERN;
  return sym;
}

static Sym *asm_new_label(TCCState *s1, int label, int is_local) {
  return asm_new_label1(s1, label, is_local, cur_text_section->sh_num, ind);
}

/* 把 LABEL 的值设为某个表达式（可能涉及其他符号）的值。
   之后仍可以覆盖 LABEL。  */
static Sym *set_symbol(TCCState *s1, int label) {
  long n;
  ExprValue e;
  Sym *sym;
  ElfSym *esym;
  next();
  asm_expr(s1, &e);
  n = e.v;
  esym = elfsym(e.sym);
  if (esym)
    n += esym->st_value;
  sym = asm_new_label1(s1, label, 2, esym ? esym->st_shndx : SHN_ABS, n);
  elfsym(sym)->st_other |= ST_ASM_SET;
  return sym;
}

static void use_section1(TCCState *s1, Section *sec) {
  cur_text_section->data_offset = ind;
  cur_text_section = sec;
  ind = cur_text_section->data_offset;
}

static void use_section(TCCState *s1, const char *name) {
  Section *sec;
  sec = find_section(s1, name);
  use_section1(s1, sec);
}

static void push_section(TCCState *s1, const char *name) {
  Section *sec = find_section(s1, name);
  sec->prev = cur_text_section;
  use_section1(s1, sec);
}

static void pop_section(TCCState *s1) {
  Section *prev = cur_text_section->prev;
  if (!prev)
    tcc_error(".popsection without .pushsection");
  cur_text_section->prev = NULL;
  use_section1(s1, prev);
}

static void asm_parse_directive(TCCState *s1, int global) {
  int n, offset, v, size, tok1;
  Section *sec;
  uint8_t *ptr;

  /* 汇编器伪指令 */
  sec = cur_text_section;
  switch (tok) {
  case TOK_ASMDIR_align:
  case TOK_ASMDIR_balign:
  case TOK_ASMDIR_p2align:
  case TOK_ASMDIR_skip:
  case TOK_ASMDIR_space:
    tok1 = tok;
    next();
    n = asm_int_expr(s1);
    if (tok1 == TOK_ASMDIR_p2align) {
      if (n < 0 || n > 30)
        tcc_error("invalid p2align, must be between 0 and 30");
      n = 1 << n;
      tok1 = TOK_ASMDIR_align;
    }
    if (tok1 == TOK_ASMDIR_align || tok1 == TOK_ASMDIR_balign) {
      if (n < 0 || (n & (n - 1)) != 0)
        tcc_error("alignment must be a positive power of two");
      offset = (ind + n - 1) & -n;
      size = offset - ind;
      /* 该段必须有兼容的对齐 */
      if (sec->sh_addralign < n)
        sec->sh_addralign = n;
    } else {
      if (n < 0)
        n = 0;
      size = n;
    }
    v = 0;
    if (tok == ',') {
      next();
      v = asm_int_expr(s1);
    }
  zero_pad:
    if (sec->sh_type != SHT_NOBITS) {
      sec->data_offset = ind;
      ptr = section_ptr_add(sec, size);
      memset(ptr, v, size);
    }
    ind += size;
    break;
  case TOK_ASMDIR_quad:
    next();
    for (;;) {
      uint64_t vl;
      const char *p;

      p = tokc.str.data;
      if (tok != TOK_PPNUM) {
      error_constant:
        tcc_error("64 bit constant");
      }
      vl = strtoll(p, (char **)&p, 0);
      if (*p != '\0')
        goto error_constant;
      next();
      if (sec->sh_type != SHT_NOBITS) {
        /* XXX：字节序 */
        gen_le32(vl);
        gen_le32(vl >> 32);
      } else {
        ind += 8;
      }
      if (tok != ',')
        break;
      next();
    }
    break;
  case TOK_ASMDIR_byte:
    size = 1;
    goto asm_data;
  case TOK_ASMDIR_word:
  case TOK_ASMDIR_short:
    size = 2;
    goto asm_data;
  case TOK_ASMDIR_long:
  case TOK_ASMDIR_int:
    size = 4;
  asm_data:
    next();
    for (;;) {
      ExprValue e;
      asm_expr(s1, &e);
      if (sec->sh_type != SHT_NOBITS) {
        if (size == 4) {
          gen_expr32(&e);
        } else {
          if (e.sym)
            expect("constant");
          if (size == 1)
            g(e.v);
          else
            gen_le16(e.v);
        }
      } else {
        ind += size;
      }
      if (tok != ',')
        break;
      next();
    }
    break;
  case TOK_ASMDIR_fill: {
    int repeat, size, val, i, j;
    uint8_t repeat_buf[8];
    next();
    repeat = asm_int_expr(s1);
    if (repeat < 0) {
      tcc_error("repeat < 0; .fill ignored");
      break;
    }
    size = 1;
    val = 0;
    if (tok == ',') {
      next();
      size = asm_int_expr(s1);
      if (size < 0) {
        tcc_error("size < 0; .fill ignored");
        break;
      }
      if (size > 8)
        size = 8;
      if (tok == ',') {
        next();
        val = asm_int_expr(s1);
      }
    }
    /* XXX：字节序 */
    repeat_buf[0] = val;
    repeat_buf[1] = val >> 8;
    repeat_buf[2] = val >> 16;
    repeat_buf[3] = val >> 24;
    repeat_buf[4] = 0;
    repeat_buf[5] = 0;
    repeat_buf[6] = 0;
    repeat_buf[7] = 0;
    for (i = 0; i < repeat; i++) {
      for (j = 0; j < size; j++) {
        g(repeat_buf[j]);
      }
    }
  } break;
  case TOK_ASMDIR_rept: {
    int repeat;
    TokenString *init_str;
    next();
    repeat = asm_int_expr(s1);
    init_str = tok_str_alloc();
    while (next(), tok != TOK_ASMDIR_endr) {
      if (tok == CH_EOF)
        tcc_error("we at end of file, .endr not found");
      tok_str_add_tok(init_str);
    }
    tok_str_add(init_str, -1);
    tok_str_add(init_str, 0);
    begin_macro(init_str, 1);
    while (repeat-- > 0) {
      tcc_assemble_internal(s1, (parse_flags & PARSE_FLAG_PREPROCESS), global);
      macro_ptr = init_str->str;
    }
    end_macro();
    next();
    break;
  }
  case TOK_ASMDIR_org: {
    unsigned long n;
    ExprValue e;
    ElfSym *esym;
    next();
    asm_expr(s1, &e);
    n = e.v;
    esym = elfsym(e.sym);
    if (esym) {
      if (esym->st_shndx != cur_text_section->sh_num)
        expect("constant or same-section symbol");
      n += esym->st_value;
    }
    if (n < ind)
      tcc_error("attempt to .org backwards");
    v = 0;
    size = n - ind;
    goto zero_pad;
  } break;
  case TOK_ASMDIR_set:
    next();
    tok1 = tok;
    next();
    /* 也接受 '.set stuff'，但不做任何处理。
       在 GAS 中它用于设置各种特性，如 '.set mips16'。  */
    if (tok == ',')
      set_symbol(s1, tok1);
    break;
  case TOK_ASMDIR_globl:
  case TOK_ASMDIR_global:
  case TOK_ASMDIR_weak:
  case TOK_ASMDIR_hidden:
    tok1 = tok;
    do {
      Sym *sym;
      next();
      sym = get_asm_sym(tok, NULL);
      if (tok1 != TOK_ASMDIR_hidden)
        sym->type.t &= ~VT_STATIC;
      if (tok1 == TOK_ASMDIR_weak)
        sym->a.weak = 1;
      else if (tok1 == TOK_ASMDIR_hidden)
        sym->a.visibility = STV_HIDDEN;
      update_storage(sym);
      next();
    } while (tok == ',');
    break;
  case TOK_ASMDIR_string:
  case TOK_ASMDIR_ascii:
  case TOK_ASMDIR_asciz: {
    const uint8_t *p;
    int i, size, t;

    t = tok;
    next();
    for (;;) {
      if (tok != TOK_STR)
        expect("string constant");
      p = tokc.str.data;
      size = tokc.str.size;
      if (t == TOK_ASMDIR_ascii && size > 0)
        size--;
      for (i = 0; i < size; i++)
        g(p[i]);
      next();
      if (tok == ',') {
        next();
      } else if (tok != TOK_STR) {
        break;
      }
    }
  } break;
  case TOK_ASMDIR_text:
  case TOK_ASMDIR_data:
  case TOK_ASMDIR_bss: {
    char sname[64];
    tok1 = tok;
    n = 0;
    next();
    if (tok != ';' && tok != TOK_LINEFEED) {
      n = asm_int_expr(s1);
      next();
    }
    if (n)
      sprintf(sname, "%s%d", get_tok_str(tok1, NULL), n);
    else
      sprintf(sname, "%s", get_tok_str(tok1, NULL));
    use_section(s1, sname);
  } break;
  case TOK_ASMDIR_file: {
    char filename[512];

    filename[0] = '\0';
    next();

    if (tok == TOK_STR)
      pstrcat(filename, sizeof(filename), tokc.str.data);
    else
      pstrcat(filename, sizeof(filename), get_tok_str(tok, NULL));

    if (s1->warn_unsupported)
      tcc_warning("ignoring .file %s", filename);

    next();
  } break;
  case TOK_ASMDIR_ident: {
    char ident[256];

    ident[0] = '\0';
    next();

    if (tok == TOK_STR)
      pstrcat(ident, sizeof(ident), tokc.str.data);
    else
      pstrcat(ident, sizeof(ident), get_tok_str(tok, NULL));

    if (s1->warn_unsupported)
      tcc_warning("ignoring .ident %s", ident);

    next();
  } break;
  case TOK_ASMDIR_size: {
    Sym *sym;

    next();
    sym = asm_label_find(tok);
    if (!sym) {
      tcc_error("label not found: %s", get_tok_str(tok, NULL));
    }

    /* XXX .size name,label2-label1 */
    if (s1->warn_unsupported)
      tcc_warning("ignoring .size %s,*", get_tok_str(tok, NULL));

    next();
    skip(',');
    while (tok != TOK_LINEFEED && tok != ';' && tok != CH_EOF) {
      next();
    }
  } break;
  case TOK_ASMDIR_type: {
    Sym *sym;
    const char *newtype;

    next();
    sym = get_asm_sym(tok, NULL);
    next();
    skip(',');
    if (tok == TOK_STR) {
      newtype = tokc.str.data;
    } else {
      if (tok == '@' || tok == '%')
        next();
      newtype = get_tok_str(tok, NULL);
    }

    if (!strcmp(newtype, "function") || !strcmp(newtype, "STT_FUNC")) {
      sym->type.t = (sym->type.t & ~VT_BTYPE) | VT_FUNC;
    } else if (s1->warn_unsupported)
      tcc_warning("change type of '%s' from 0x%x to '%s' ignored",
                  get_tok_str(sym->v, NULL), sym->type.t, newtype);

    next();
  } break;
  case TOK_ASMDIR_pushsection:
  case TOK_ASMDIR_section: {
    char sname[256];
    int old_nb_section = s1->nb_sections;

    tok1 = tok;
    /* XXX：支持更多选项 */
    next();
    sname[0] = '\0';
    while (tok != ';' && tok != TOK_LINEFEED && tok != ',') {
      if (tok == TOK_STR)
        pstrcat(sname, sizeof(sname), tokc.str.data);
      else
        pstrcat(sname, sizeof(sname), get_tok_str(tok, NULL));
      next();
    }
    if (tok == ',') {
      /* 跳过段选项 */
      next();
      if (tok != TOK_STR)
        expect("string constant");
      next();
      if (tok == ',') {
        next();
        if (tok == '@' || tok == '%')
          next();
        next();
      }
    }
    last_text_section = cur_text_section;
    if (tok1 == TOK_ASMDIR_section)
      use_section(s1, sname);
    else
      push_section(s1, sname);
    /* 如果刚刚分配了新段，把它的对齐重置为
       1。new_section 通常为了兼容 GCC 而
       把对齐设为 PTR_SIZE。汇编器的行为不同。 */
    if (old_nb_section != s1->nb_sections)
      cur_text_section->sh_addralign = 1;
  } break;
  case TOK_ASMDIR_previous: {
    Section *sec;
    next();
    if (!last_text_section)
      tcc_error("no previous section referenced");
    sec = cur_text_section;
    use_section1(s1, last_text_section);
    last_text_section = sec;
  } break;
  case TOK_ASMDIR_popsection:
    next();
    pop_section(s1);
    break;
  default:
    tcc_error("unknown assembler directive '.%s'", get_tok_str(tok, NULL));
    break;
  }
}

/* 汇编一个文件 */
static int tcc_assemble_internal(TCCState *s1, int do_preprocess, int global) {
  int opcode;
  int saved_parse_flags = parse_flags;

  parse_flags = PARSE_FLAG_ASM_FILE | PARSE_FLAG_TOK_STR;
  if (do_preprocess)
    parse_flags |= PARSE_FLAG_PREPROCESS;
  for (;;) {
    next();
    if (tok == TOK_EOF)
      break;
    /* 生成行号信息 */
    if (global && s1->do_debug)
      tcc_debug_line(s1);
    parse_flags |= PARSE_FLAG_LINEFEED; /* XXX：去掉这个权宜之计 */
  redo:
    if (tok == '#') {
      /* 讨厌的 gas 注释 */
      while (tok != TOK_LINEFEED)
        next();
    } else if (tok >= TOK_ASMDIR_FIRST && tok <= TOK_ASMDIR_LAST) {
      asm_parse_directive(s1, global);
    } else if (tok == TOK_PPNUM) {
      const char *p;
      int n;
      p = tokc.str.data;
      n = strtoul(p, (char **)&p, 10);
      if (*p != '\0')
        expect("':'");
      /* 新的局部标签 */
      asm_new_label(s1, asm_get_local_label_name(s1, n), 1);
      next();
      skip(':');
      goto redo;
    } else if (tok >= TOK_IDENT) {
      /* 指令或标签 */
      opcode = tok;
      next();
      if (tok == ':') {
        /* 新标签 */
        asm_new_label(s1, opcode, 0);
        next();
        goto redo;
      } else if (tok == '=') {
        set_symbol(s1, opcode);
        goto redo;
      } else {
        asm_opcode(s1, opcode);
      }
    }
    /* 行尾 */
    if (tok != ';' && tok != TOK_LINEFEED)
      expect("end of line");
    parse_flags &= ~PARSE_FLAG_LINEFEED; /* XXX：去掉这个权宜之计 */
  }

  parse_flags = saved_parse_flags;
  return 0;
}

/* 汇编当前文件 */
ST_FUNC int tcc_assemble(TCCState *s1, int do_preprocess) {
  int ret;
  tcc_debug_start(s1);
  /* 默认段是代码段 */
  cur_text_section = text_section;
  ind = cur_text_section->data_offset;
  nocode_wanted = 0;
  ret = tcc_assemble_internal(s1, do_preprocess, 1);
  cur_text_section->data_offset = ind;
  tcc_debug_end(s1);
  return ret;
}

/********************************************************************/
/* GCC 内联 asm 支持 */

/* 在当前 C 编译单元中汇编字符串 'str'，不做
   C 预处理。注意：str 会被修改，方式是改动末尾的
   '\0' */
static void tcc_assemble_inline(TCCState *s1, char *str, int len, int global) {
  const int *saved_macro_ptr = macro_ptr;
  int dotid = set_idnum('.', IS_ID);

  tcc_open_bf(s1, ":asm:", len);
  memcpy(file->buffer, str, len);
  macro_ptr = NULL;
  tcc_assemble_internal(s1, 0, global);
  tcc_close();

  set_idnum('.', dotid);
  macro_ptr = saved_macro_ptr;
}

/* 按编号或 id 查找约束（gcc 3 扩展
   语法）。找不到时返回 -1。在 *pp 中返回约束之后的
   字符 */
ST_FUNC int find_constraint(ASMOperand *operands, int nb_operands,
                            const char *name, const char **pp) {
  int index;
  TokenSym *ts;
  const char *p;

  if (isnum(*name)) {
    index = 0;
    while (isnum(*name)) {
      index = (index * 10) + (*name) - '0';
      name++;
    }
    if ((unsigned)index >= nb_operands)
      index = -1;
  } else if (*name == '[') {
    name++;
    p = strchr(name, ']');
    if (p) {
      ts = tok_alloc(name, p - name);
      for (index = 0; index < nb_operands; index++) {
        if (operands[index].id == ts->tok)
          goto found;
      }
      index = -1;
    found:
      name = p + 1;
    } else {
      index = -1;
    }
  } else {
    index = -1;
  }
  if (pp)
    *pp = name;
  return index;
}

static void subst_asm_operands(ASMOperand *operands, int nb_operands,
                               CString *out_str, CString *in_str) {
  int c, index, modifier;
  const char *str;
  ASMOperand *op;
  SValue sv;

  cstr_new(out_str);
  str = in_str->data;
  for (;;) {
    c = *str++;
    if (c == '%') {
      if (*str == '%') {
        str++;
        goto add_char;
      }
      modifier = 0;
      if (*str == 'c' || *str == 'n' || *str == 'b' || *str == 'w' ||
          *str == 'h' || *str == 'k' || *str == 'q' ||
          /* 在 GCC 中 P 会在 PIC 模式下给符号引用加上 "@PLT"，
             并使字面量操作数不带 '$' 修饰。  */
          *str == 'P')
        modifier = *str++;
      index = find_constraint(operands, nb_operands, str, &str);
      if (index < 0)
        tcc_error("invalid operand reference after %%");
      op = &operands[index];
      sv = *op->vt;
      if (op->reg >= 0) {
        sv.r = op->reg;
        if ((op->vt->r & VT_VALMASK) == VT_LLOCAL && op->is_memory)
          sv.r |= VT_LVAL;
      }
      subst_asm_operand(out_str, &sv, modifier);
    } else {
    add_char:
      cstr_ccat(out_str, c);
      if (c == '\0')
        break;
    }
  }
}

static void parse_asm_operands(ASMOperand *operands, int *nb_operands_ptr,
                               int is_output) {
  ASMOperand *op;
  int nb_operands;

  if (tok != ':') {
    nb_operands = *nb_operands_ptr;
    for (;;) {
      CString astr;
      if (nb_operands >= MAX_ASM_OPERANDS)
        tcc_error("too many asm operands");
      op = &operands[nb_operands++];
      op->id = 0;
      if (tok == '[') {
        next();
        if (tok < TOK_IDENT)
          expect("identifier");
        op->id = tok;
        next();
        skip(']');
      }
      parse_mult_str(&astr, "string constant");
      op->constraint = tcc_malloc(astr.size);
      strcpy(op->constraint, astr.data);
      cstr_free(&astr);
      skip('(');
      gexpr();
      if (is_output) {
        if (!(vtop->type.t & VT_ARRAY))
          test_lvalue();
      } else {
        /* 我们希望避免 LLOCAL 情形，除非使用了 'm'
           约束。注意它可能来自寄存器存储，
           所以需要转换 (reg)
           情形 */
        if ((vtop->r & VT_LVAL) &&
            ((vtop->r & VT_VALMASK) == VT_LLOCAL ||
             (vtop->r & VT_VALMASK) < VT_CONST) &&
            !strchr(op->constraint, 'm')) {
          gv(RC_INT);
        }
      }
      op->vt = vtop;
      skip(')');
      if (tok == ',') {
        next();
      } else {
        break;
      }
    }
    *nb_operands_ptr = nb_operands;
  }
}

/* 解析 GCC 的 asm() 指令 */
ST_FUNC void asm_instr(void) {
  CString astr, astr1;
  ASMOperand operands[MAX_ASM_OPERANDS];
  int nb_outputs, nb_operands, i, must_subst, out_reg;
  uint8_t clobber_regs[NB_ASM_REGS];

  next();
  /* 因为我们总是生成 asm() 指令，所以可以忽略
     volatile */
  if (tok == TOK_VOLATILE1 || tok == TOK_VOLATILE2 || tok == TOK_VOLATILE3) {
    next();
  }
  parse_asm_str(&astr);
  nb_operands = 0;
  nb_outputs = 0;
  must_subst = 0;
  memset(clobber_regs, 0, sizeof(clobber_regs));
  if (tok == ':') {
    next();
    must_subst = 1;
    /* 输出参数 */
    parse_asm_operands(operands, &nb_operands, 1);
    nb_outputs = nb_operands;
    if (tok == ':') {
      next();
      if (tok != ')') {
        /* 输入参数 */
        parse_asm_operands(operands, &nb_operands, 0);
        if (tok == ':') {
          /* 破坏列表 */
          /* XXX：处理寄存器 */
          next();
          for (;;) {
            if (tok != TOK_STR)
              expect("string constant");
            asm_clobber(clobber_regs, tokc.str.data);
            next();
            if (tok == ',') {
              next();
            } else {
              break;
            }
          }
        }
      }
    }
  }
  skip(')');
  /* 注意：我们不吃掉 ';'，这样就能在汇编器解析之后
     恢复当前词法单元 */
  if (tok != ';')
    expect("';'");

  /* 把所有值保存到内存中 */
  save_regs(0);

  /* 计算约束 */
  asm_compute_constraints(operands, nb_operands, nb_outputs, clobber_regs,
                          &out_reg);

  /* 在 asm 字符串中替换操作数。如果没有操作数
     就不做替换（GCC 的行为） */
#ifdef ASM_DEBUG
  printf("asm: \"%s\"\n", (char *)astr.data);
#endif
  if (must_subst) {
    subst_asm_operands(operands, nb_operands, &astr1, &astr);
    cstr_free(&astr);
  } else {
    astr1 = astr;
  }
#ifdef ASM_DEBUG
  printf("subst_asm: \"%s\"\n", (char *)astr1.data);
#endif

  /* 生成加载 */
  asm_gen_code(operands, nb_operands, nb_outputs, 0, clobber_regs, out_reg);

  /* 用 tcc 内部汇编器汇编该字符串 */
  tcc_assemble_inline(tcc_state, astr1.data, astr1.size - 1, 0);

  /* 恢复当前 C 词法单元 */
  next();

  /* 如需要则保存输出值 */
  asm_gen_code(operands, nb_operands, nb_outputs, 1, clobber_regs, out_reg);

  /* 释放所有内容 */
  for (i = 0; i < nb_operands; i++) {
    ASMOperand *op;
    op = &operands[i];
    tcc_free(op->constraint);
    vpop();
  }
  cstr_free(&astr1);
}

ST_FUNC void asm_global_instr(void) {
  CString astr;
  int saved_nocode_wanted = nocode_wanted;

  /* 全局 asm 块总是会生成。  */
  nocode_wanted = 0;
  next();
  parse_asm_str(&astr);
  skip(')');
  /* 注意：我们不吃掉 ';'，这样就能在汇编器解析之后
     恢复当前词法单元 */
  if (tok != ';')
    expect("';'");

#ifdef ASM_DEBUG
  printf("asm_global: \"%s\"\n", (char *)astr.data);
#endif
  cur_text_section = text_section;
  ind = cur_text_section->data_offset;

  /* 用 tcc 内部汇编器汇编该字符串 */
  tcc_assemble_inline(tcc_state, astr.data, astr.size - 1, 1);

  cur_text_section->data_offset = ind;

  /* 恢复当前 C 词法单元 */
  next();

  cstr_free(&astr);
  nocode_wanted = saved_nocode_wanted;
}
#endif /* CONFIG_TCC_ASM */
