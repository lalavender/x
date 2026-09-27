/* 关键字
 *
 * yh 的保留字全部位于 TOK_UIDENT（= TOK_DEFINE）边界之前：
 *   - yh 新增关键字（下表前段）：yh 中不可作普通标识符；
 *   - 复用 C 同名关键字的 token：if/else/for/switch/case/default/return/
 *     break/continue/goto/struct/union/enum/sizeof/int/void/char/const；
 *   - 已移除的 C 关键字（while/do/short/…/restrict 与 gcc 变体）：
 *     保留注册为「报错保留字」，yh parser 遇到时给出定向提示，
 *     成员位置（fieldDecl/字面量字段/成员访问）按 memberName 放开。
 *
 * 边界之后的 DEF（define/include/…）不是关键字：这些 token 值 >= TOK_UIDENT，
 * 在 yh 中可作普通标识符使用。
 */
DEF(TOK_LET, "let")
DEF(TOK_FN, "fn")
DEF(TOK_IN, "in")
DEF(TOK_PUB, "pub")
DEF(TOK_TRUE, "true")
DEF(TOK_FALSE, "false")
DEF(TOK_LEN, "len")
DEF(TOK_TO_TYPE, "to_type") /* 类型转换专用后缀关键字 */
DEF(TOK_TYPE, "type")
DEF(TOK_AS, "as")           /* 旧转换写法，yh 中保留报错，仅成员位可用 */
DEF(TOK_I8, "i8")
DEF(TOK_I16, "i16")
DEF(TOK_I32, "i32")
DEF(TOK_I64, "i64")
DEF(TOK_U8, "u8")
DEF(TOK_U16, "u16")
DEF(TOK_U32, "u32")
DEF(TOK_U64, "u64")
DEF(TOK_F32, "f32")
DEF(TOK_F64, "f64")
DEF(TOK_YBOOL, "bool")

DEF(TOK_INT, "int")
DEF(TOK_VOID, "void")
DEF(TOK_CHAR, "char")
DEF(TOK_IF, "if")
DEF(TOK_ELSE, "else")
DEF(TOK_WHILE, "while")
DEF(TOK_BREAK, "break")
DEF(TOK_RETURN, "return")
DEF(TOK_FOR, "for")
DEF(TOK_EXTERN, "extern")
DEF(TOK_STATIC, "static")
DEF(TOK_UNSIGNED, "unsigned")
DEF(TOK_GOTO, "goto")
DEF(TOK_DO, "do")
DEF(TOK_CONTINUE, "continue")
DEF(TOK_SWITCH, "switch")
DEF(TOK_CASE, "case")

DEF(TOK_CONST1, "const")
DEF(TOK_CONST2, "__const")   /* gcc 关键字 */
DEF(TOK_CONST3, "__const__") /* gcc 关键字 */
DEF(TOK_VOLATILE1, "volatile")
DEF(TOK_VOLATILE2, "__volatile")   /* gcc 关键字 */
DEF(TOK_VOLATILE3, "__volatile__") /* gcc 关键字 */
DEF(TOK_LONG, "long")
DEF(TOK_REGISTER, "register")
DEF(TOK_SIGNED1, "signed")
DEF(TOK_SIGNED2, "__signed")   /* gcc 关键字 */
DEF(TOK_SIGNED3, "__signed__") /* gcc 关键字 */
DEF(TOK_AUTO, "auto")
DEF(TOK_INLINE1, "inline")
DEF(TOK_INLINE2, "__inline")   /* gcc 关键字 */
DEF(TOK_INLINE3, "__inline__") /* gcc 关键字 */
DEF(TOK_RESTRICT1, "restrict")
DEF(TOK_RESTRICT2, "__restrict")
DEF(TOK_RESTRICT3, "__restrict__")
DEF(TOK_EXTENSION, "__extension__") /* gcc 关键字 */

DEF(TOK_GENERIC, "_Generic")

DEF(TOK_FLOAT, "float")
DEF(TOK_DOUBLE, "double")
DEF(TOK_BOOL, "_Bool")
DEF(TOK_SHORT, "short")
DEF(TOK_STRUCT, "struct")
DEF(TOK_UNION, "union")
DEF(TOK_TYPEDEF, "typedef")
DEF(TOK_DEFAULT, "default")
DEF(TOK_ENUM, "enum")
DEF(TOK_SIZEOF, "sizeof")
DEF(TOK_ATTRIBUTE1, "__attribute")
DEF(TOK_ATTRIBUTE2, "__attribute__")
DEF(TOK_ALIGNOF1, "__alignof")
DEF(TOK_ALIGNOF2, "__alignof__")
DEF(TOK_TYPEOF1, "typeof")
DEF(TOK_TYPEOF2, "__typeof")
DEF(TOK_TYPEOF3, "__typeof__")
DEF(TOK_LABEL, "__label__")
DEF(TOK_ASM1, "asm")
DEF(TOK_ASM2, "__asm")
DEF(TOK_ASM3, "__asm__")

#ifdef TCC_TARGET_ARM64
DEF(TOK_UINT128, "__uint128_t")
#endif

/*********************************************************************/
/* 以下不是关键字。包含它们是为了便于解析 */
/* 仅预处理器 */
DEF(TOK_DEFINE, "define")
DEF(TOK_INCLUDE, "include")
DEF(TOK_INCLUDE_NEXT, "include_next")
DEF(TOK_IFDEF, "ifdef")
DEF(TOK_IFNDEF, "ifndef")
DEF(TOK_ELIF, "elif")
DEF(TOK_ENDIF, "endif")
DEF(TOK_DEFINED, "defined")
DEF(TOK_UNDEF, "undef")
DEF(TOK_ERROR, "error")
DEF(TOK_WARNING, "warning")
DEF(TOK_LINE, "line")
DEF(TOK_PRAGMA, "pragma")
DEF(TOK___LINE__, "__LINE__")
DEF(TOK___FILE__, "__FILE__")
DEF(TOK___DATE__, "__DATE__")
DEF(TOK___TIME__, "__TIME__")
DEF(TOK___FUNCTION__, "__FUNCTION__")
DEF(TOK___VA_ARGS__, "__VA_ARGS__")
DEF(TOK___COUNTER__, "__COUNTER__")

/* 特殊标识符 */
DEF(TOK___FUNC__, "__func__")

/* 特殊浮点值 */
DEF(TOK___NAN__, "__nan__")
DEF(TOK___SNAN__, "__snan__")
DEF(TOK___INF__, "__inf__")

/* attribute 标识符 */
/* XXX: 通用地处理所有词法单元，因为速度并不关键 */
DEF(TOK_SECTION1, "section")
DEF(TOK_SECTION2, "__section__")
DEF(TOK_ALIGNED1, "aligned")
DEF(TOK_ALIGNED2, "__aligned__")
DEF(TOK_PACKED1, "packed")
DEF(TOK_PACKED2, "__packed__")
DEF(TOK_WEAK1, "weak")
DEF(TOK_WEAK2, "__weak__")
DEF(TOK_ALIAS1, "alias")
DEF(TOK_ALIAS2, "__alias__")
DEF(TOK_UNUSED1, "unused")
DEF(TOK_UNUSED2, "__unused__")
DEF(TOK_CDECL1, "cdecl")
DEF(TOK_CDECL2, "__cdecl")
DEF(TOK_CDECL3, "__cdecl__")
DEF(TOK_STDCALL1, "stdcall")
DEF(TOK_STDCALL2, "__stdcall")
DEF(TOK_STDCALL3, "__stdcall__")
DEF(TOK_FASTCALL1, "fastcall")
DEF(TOK_FASTCALL2, "__fastcall")
DEF(TOK_FASTCALL3, "__fastcall__")
DEF(TOK_REGPARM1, "regparm")
DEF(TOK_REGPARM2, "__regparm__")

DEF(TOK_MODE, "__mode__")
DEF(TOK_MODE_QI, "__QI__")
DEF(TOK_MODE_DI, "__DI__")
DEF(TOK_MODE_HI, "__HI__")
DEF(TOK_MODE_SI, "__SI__")
DEF(TOK_MODE_word, "__word__")

DEF(TOK_DLLEXPORT, "dllexport")
DEF(TOK_DLLIMPORT, "dllimport")
DEF(TOK_NORETURN1, "noreturn")
DEF(TOK_NORETURN2, "__noreturn__")
DEF(TOK_VISIBILITY1, "visibility")
DEF(TOK_VISIBILITY2, "__visibility__")

DEF(TOK_builtin_types_compatible_p, "__builtin_types_compatible_p")
DEF(TOK_builtin_choose_expr, "__builtin_choose_expr")
DEF(TOK_builtin_constant_p, "__builtin_constant_p")
DEF(TOK_builtin_frame_address, "__builtin_frame_address")
DEF(TOK_builtin_return_address, "__builtin_return_address")
DEF(TOK_builtin_expect, "__builtin_expect")
/*DEF(TOK_builtin_va_list, "__builtin_va_list")*/
#ifdef TCC_TARGET_ARM64
DEF(TOK___va_start, "__va_start")
DEF(TOK___va_arg, "__va_arg")
#endif

/* pragma */
DEF(TOK_pack, "pack")
DEF(TOK_ASM_push, "push")
DEF(TOK_ASM_pop, "pop")
DEF(TOK_comment, "comment")
DEF(TOK_lib, "lib")
DEF(TOK_push_macro, "push_macro")
DEF(TOK_pop_macro, "pop_macro")
DEF(TOK_once, "once")
DEF(TOK_option, "option")

/* 内建函数或变量 */
#ifndef TCC_ARM_EABI
DEF(TOK_memcpy, "memcpy")
DEF(TOK_memmove, "memmove")
DEF(TOK_memset, "memset")
DEF(TOK___divdi3, "__divdi3")
DEF(TOK___moddi3, "__moddi3")
DEF(TOK___udivdi3, "__udivdi3")
DEF(TOK___umoddi3, "__umoddi3")
DEF(TOK___ashrdi3, "__ashrdi3")
DEF(TOK___lshrdi3, "__lshrdi3")
DEF(TOK___ashldi3, "__ashldi3")
DEF(TOK___floatundisf, "__floatundisf")
DEF(TOK___floatundidf, "__floatundidf")
#ifndef TCC_ARM_VFP
DEF(TOK___floatundixf, "__floatundixf")
DEF(TOK___fixunsxfdi, "__fixunsxfdi")
#endif
DEF(TOK___fixunssfdi, "__fixunssfdi")
DEF(TOK___fixunsdfdi, "__fixunsdfdi")
#endif




#ifdef TCC_TARGET_ARM64
DEF(TOK___arm64_clear_cache, "__arm64_clear_cache")
DEF(TOK___addtf3, "__addtf3")
DEF(TOK___subtf3, "__subtf3")
DEF(TOK___multf3, "__multf3")
DEF(TOK___divtf3, "__divtf3")
DEF(TOK___extendsftf2, "__extendsftf2")
DEF(TOK___extenddftf2, "__extenddftf2")
DEF(TOK___trunctfsf2, "__trunctfsf2")
DEF(TOK___trunctfdf2, "__trunctfdf2")
DEF(TOK___fixtfsi, "__fixtfsi")
DEF(TOK___fixtfdi, "__fixtfdi")
DEF(TOK___fixunstfsi, "__fixunstfsi")
DEF(TOK___fixunstfdi, "__fixunstfdi")
DEF(TOK___floatsitf, "__floatsitf")
DEF(TOK___floatditf, "__floatditf")
DEF(TOK___floatunsitf, "__floatunsitf")
DEF(TOK___floatunditf, "__floatunditf")
DEF(TOK___eqtf2, "__eqtf2")
DEF(TOK___netf2, "__netf2")
DEF(TOK___lttf2, "__lttf2")
DEF(TOK___letf2, "__letf2")
DEF(TOK___gttf2, "__gttf2")
DEF(TOK___getf2, "__getf2")
#endif

/* 边界检查符号 */
#ifdef CONFIG_TCC_BCHECK
DEF(TOK___bound_ptr_add, "__bound_ptr_add")
DEF(TOK___bound_ptr_indir1, "__bound_ptr_indir1")
DEF(TOK___bound_ptr_indir2, "__bound_ptr_indir2")
DEF(TOK___bound_ptr_indir4, "__bound_ptr_indir4")
DEF(TOK___bound_ptr_indir8, "__bound_ptr_indir8")
DEF(TOK___bound_ptr_indir12, "__bound_ptr_indir12")
DEF(TOK___bound_ptr_indir16, "__bound_ptr_indir16")
DEF(TOK___bound_main_arg, "__bound_main_arg")
DEF(TOK___bound_local_new, "__bound_local_new")
DEF(TOK___bound_local_delete, "__bound_local_delete")
DEF(TOK_strlen, "strlen")
DEF(TOK_strcpy, "strcpy")
#endif

/* 微型汇编器 */
DEF_ASMDIR(byte) /* 必须是首个伪指令 */
DEF_ASMDIR(word)
DEF_ASMDIR(align)
DEF_ASMDIR(balign)
DEF_ASMDIR(p2align)
DEF_ASMDIR(set)
DEF_ASMDIR(skip)
DEF_ASMDIR(space)
DEF_ASMDIR(string)
DEF_ASMDIR(asciz)
DEF_ASMDIR(ascii)
DEF_ASMDIR(file)
DEF_ASMDIR(globl)
DEF_ASMDIR(global)
DEF_ASMDIR(weak)
DEF_ASMDIR(hidden)
DEF_ASMDIR(ident)
DEF_ASMDIR(size)
DEF_ASMDIR(type)
DEF_ASMDIR(text)
DEF_ASMDIR(data)
DEF_ASMDIR(bss)
DEF_ASMDIR(previous)
DEF_ASMDIR(pushsection)
DEF_ASMDIR(popsection)
DEF_ASMDIR(fill)
DEF_ASMDIR(rept)
DEF_ASMDIR(endr)
DEF_ASMDIR(org)
DEF_ASMDIR(quad)
DEF_ASMDIR(short)
DEF_ASMDIR(long)
DEF_ASMDIR(int)
DEF_ASMDIR(section) /* 必须是最后一个伪指令 */

