/* va_list.c - tinycc 在 X86_64 上对 va_list 的支持 */

#if defined __x86_64__

/* 避免包含头文件，交叉编译时它们可能不可用 */
extern void *memset(void *s, int c, __SIZE_TYPE__ n);
extern void abort(void);

/* 这应与我们的 include/stdarg.h 保持同步 */
enum __va_arg_type { __va_gen_reg, __va_float_reg, __va_stack };

/*
 * __va_list_struct —— AArch64（AAPCS64）的 va_list 布局，与 GCC 兼容
 *
 * 变参函数的可变参数分两处：寄存器里的前 8 个整型参数（x0..x7 中的一部分）
 * 和前 8 个浮点参数（v0..v7），以及调用者压栈的“溢出”参数。__va_start() 由
 * 编译器在函数序言后调用，fp 指向寄存器保存区的底部，于是
 *   reg_save_area   = fp - 176 - 16，即保存 x0..x7 与 v0..v7 的连续区域；
 *   overflow_arg_area 由 overflow_offset 初始化，指向栈上的溢出参数。
 * 之后每次 __va_arg() 取参数时递增相应偏移：
 *   gp_offset  已消耗的通用寄存器保存区偏移（字节，达到 48 即用尽）；
 *   fp_offset  已消耗的浮点寄存器保存区偏移（自 128 起算，达到 176 即用尽）。
 * 偏移用尽即从 overflow_arg_area 按对齐从栈上取。
 */
typedef struct {
  unsigned int gp_offset;
  unsigned int fp_offset;
  union {
    unsigned int overflow_offset;
    char *overflow_arg_area;
  };
  char *reg_save_area;
} __va_list_struct;

void __va_start(__va_list_struct *ap, void *fp) {
  memset(ap, 0, sizeof(__va_list_struct));
  *ap = *(__va_list_struct *)((char *)fp - 16);
  ap->overflow_arg_area = (char *)fp + ap->overflow_offset;
  ap->reg_save_area = (char *)fp - 176 - 16;
}

void *__va_arg(__va_list_struct *ap, enum __va_arg_type arg_type, int size,
               int align) {
  size = (size + 7) & ~7;
  align = (align + 7) & ~7;
  switch (arg_type) {
  case __va_gen_reg:
    if (ap->gp_offset + size <= 48) {
      ap->gp_offset += size;
      return ap->reg_save_area + ap->gp_offset - size;
    }
    goto use_overflow_area;

  case __va_float_reg:
    if (ap->fp_offset < 128 + 48) {
      ap->fp_offset += 16;
      return ap->reg_save_area + ap->fp_offset - 16;
    }
    size = 8;
    goto use_overflow_area;

  case __va_stack:
  use_overflow_area:
    ap->overflow_arg_area += size;
    ap->overflow_arg_area =
        (char *)((long long)(ap->overflow_arg_area + align - 1) & -align);
    return ap->overflow_arg_area - size;

  default: /* 不应发生 */
    abort();
  }
}
#endif
