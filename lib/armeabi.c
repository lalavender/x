/* TCC ARM 运行时 EABI
   Copyright (C) 2013 Thomas Preud'homme

特此免费授予任何获得本软件及相关文档文件（以下称“本软件”）副本的人
不受限制地处置本软件的权利，包括但不限于使用、复制、修改、合并、
发布、分发、再许可和/或销售本软件副本的权利，并允许获得本软件的
人这样做，但须满足以下条件：
上述版权声明和本许可声明应包含在本软件的所有副本或主要部分中。
本软件按“原样”提供，不附任何形式的担保，无论是明示的还是默示的，

包括但不限于对适销性的担保、特定用途适用性的担保
和非侵权的担保。在任何情况下，作者或版权持有人

均不对任何索赔、损害或其他责任负责，无论基于合同、
侵权行为还是其他理由，也无论是否已被告知此类损害的可能性，
由本软件或本软件的使用或其他处置引起的或与之相关的，
均不承担任何责任。
无论是在合同诉讼、侵权行为还是其他方面，
作者或版权持有人均不对任何索赔、损害或其他责任负责。
本软件按“原样”提供，不附任何形式的担保。*/

#ifdef __TINYC__
#define INT_MIN (-2147483647 - 1)
#define INT_MAX 2147483647
#define UINT_MAX 0xffffffff
#define LONG_MIN (-2147483647L - 1)
#define LONG_MAX 2147483647L
#define ULONG_MAX 0xffffffffUL
#define LLONG_MAX 9223372036854775807LL
#define LLONG_MIN (-9223372036854775807LL - 1)
#define ULLONG_MAX 0xffffffffffffffffULL
#else
#include <limits.h>
#endif

/* 我们依赖小端字节序和 EABI 调用约定，本代码才能
   正常工作 */

/*
 * double_unsigned_struct / unsigned_int_struct —— 按“低字/高字”访问 64 位值
 *
 * ARM EABI 下 double 与 long long 用一对寄存器（r0:r1）传递和返回，而结构体
 * 的传递规则与标量不同：把 64 位值包成这两个结构体，就能借用 EABI 的结构体
 * 传参/返回路径，在寄存器与内存之间搬运高低两个 32 位字（配合下面的
 * REGS_RETURN/__aeabi_* 例程实现 __aeabi_dadd、__aeabi_ldivmod 等软浮点与
 * 64 位整数辅助函数）。前提是小端字节序，且低字在前。
 *   double_unsigned_struct 把 double 当作两个无符号 32 位字（位搬运用）；
 *   unsigned_int_struct    把 64 位有符号数当作 low + 有符号
 * high（比较/移位用）。
 */
typedef struct double_unsigned_struct {
  unsigned low;
  unsigned high;
} double_unsigned_struct;

typedef struct unsigned_int_struct {
  unsigned low;
  int high;
} unsigned_int_struct;

#define REGS_RETURN(name, type) \
  void name##_return(type ret) {}

/* 浮点辅助函数 */

#define FLOAT_EXP_BITS 8
#define FLOAT_FRAC_BITS 23

#define DOUBLE_EXP_BITS 11
#define DOUBLE_FRAC_BITS 52

#define ONE_EXP(type) ((1 << (type##_EXP_BITS - 1)) - 1)

REGS_RETURN(unsigned_int_struct, unsigned_int_struct)
REGS_RETURN(double_unsigned_struct, double_unsigned_struct)

/* float -> integer：(符号) 1.尾数 x 2^(指数 - exp_for_one) */

/* float 到 [无符号] long long 转换 */
#define DEFINE__AEABI_F2XLZ(name, with_sign)                        \
  void __aeabi_##name(unsigned val) {                               \
    int exp, high_shift, sign;                                      \
    double_unsigned_struct ret;                                     \
                                                                    \
    /* 计算符号 */                                                  \
    sign = val >> 31;                                               \
                                                                    \
    /* 计算真实指数 */                                              \
    exp = val >> FLOAT_FRAC_BITS;                                   \
    exp &= (1 << FLOAT_EXP_BITS) - 1;                               \
    exp -= ONE_EXP(FLOAT);                                          \
                                                                    \
    /* 若截断后的值无法表示则为未定义行为 */                        \
    if (with_sign) {                                                \
      if (exp > 62) /* |val| 过大，double 无法表示 LLONG_MAX */     \
        return;                                                     \
    } else {                                                        \
      if ((sign && exp >= 0) || exp > 63) /* val < 0 或 val 过大 */ \
        return;                                                     \
    }                                                               \
                                                                    \
    val &= (1 << FLOAT_FRAC_BITS) - 1;                              \
    if (exp >= 32) {                                                \
      ret.high = 1 << (exp - 32);                                   \
      if (exp - 32 >= FLOAT_FRAC_BITS) {                            \
        ret.high |= val << (exp - 32 - FLOAT_FRAC_BITS);            \
        ret.low = 0;                                                \
      } else {                                                      \
        high_shift = FLOAT_FRAC_BITS - (exp - 32);                  \
        ret.high |= val >> high_shift;                              \
        ret.low = val << (32 - high_shift);                         \
      }                                                             \
    } else {                                                        \
      ret.high = 0;                                                 \
      ret.low = 1 << exp;                                           \
      if (exp > FLOAT_FRAC_BITS)                                    \
        ret.low |= val << (exp - FLOAT_FRAC_BITS);                  \
      else                                                          \
        ret.low |= val >> (FLOAT_FRAC_BITS - exp);                  \
    }                                                               \
                                                                    \
    /* 用二进制补码编码负整数 */                                    \
    if (with_sign && sign) {                                        \
      ret.low = ~ret.low;                                           \
      ret.high = ~ret.high;                                         \
      if (ret.low == UINT_MAX) {                                    \
        ret.low = 0;                                                \
        ret.high++;                                                 \
      } else                                                        \
        ret.low++;                                                  \
    }                                                               \
                                                                    \
    double_unsigned_struct_return(ret);                             \
  }

/* float 到无符号 long long 转换 */
DEFINE__AEABI_F2XLZ(f2ulz, 0)

/* float 到 long long 转换 */
DEFINE__AEABI_F2XLZ(f2lz, 1)

/* double 到 [无符号] long long 转换 */
#define DEFINE__AEABI_D2XLZ(name, with_sign)                        \
  void __aeabi_##name(double_unsigned_struct val) {                 \
    int exp, high_shift, sign;                                      \
    double_unsigned_struct ret;                                     \
                                                                    \
    /* 计算符号 */                                                  \
    sign = val.high >> 31;                                          \
                                                                    \
    /* 计算真实指数 */                                              \
    exp = (val.high >> (DOUBLE_FRAC_BITS - 32));                    \
    exp &= (1 << DOUBLE_EXP_BITS) - 1;                              \
    exp -= ONE_EXP(DOUBLE);                                         \
                                                                    \
    /* 若截断后的值无法表示则为未定义行为 */                        \
    if (with_sign) {                                                \
      if (exp > 62) /* |val| 过大，double 无法表示 LLONG_MAX */     \
        return;                                                     \
    } else {                                                        \
      if ((sign && exp >= 0) || exp > 63) /* val < 0 或 val 过大 */ \
        return;                                                     \
    }                                                               \
                                                                    \
    val.high &= (1 << (DOUBLE_FRAC_BITS - 32)) - 1;                 \
    if (exp >= 32) {                                                \
      ret.high = 1 << (exp - 32);                                   \
      if (exp >= DOUBLE_FRAC_BITS) {                                \
        high_shift = exp - DOUBLE_FRAC_BITS;                        \
        ret.high |= val.high << high_shift;                         \
        ret.high |= val.low >> (32 - high_shift);                   \
        ret.low = val.low << high_shift;                            \
      } else {                                                      \
        high_shift = DOUBLE_FRAC_BITS - exp;                        \
        ret.high |= val.high >> high_shift;                         \
        ret.low = val.high << (32 - high_shift);                    \
        ret.low |= val.low >> high_shift;                           \
      }                                                             \
    } else {                                                        \
      ret.high = 0;                                                 \
      ret.low = 1 << exp;                                           \
      if (exp > DOUBLE_FRAC_BITS - 32) {                            \
        high_shift = exp - DOUBLE_FRAC_BITS - 32;                   \
        ret.low |= val.high << high_shift;                          \
        ret.low |= val.low >> (32 - high_shift);                    \
      } else                                                        \
        ret.low |= val.high >> (DOUBLE_FRAC_BITS - 32 - exp);       \
    }                                                               \
                                                                    \
    /* 用二进制补码编码负整数 */                                    \
    if (with_sign && sign) {                                        \
      ret.low = ~ret.low;                                           \
      ret.high = ~ret.high;                                         \
      if (ret.low == UINT_MAX) {                                    \
        ret.low = 0;                                                \
        ret.high++;                                                 \
      } else                                                        \
        ret.low++;                                                  \
    }                                                               \
                                                                    \
    double_unsigned_struct_return(ret);                             \
  }

/* double 到无符号 long long 转换 */
DEFINE__AEABI_D2XLZ(d2ulz, 0)

/* double 到 long long 转换 */
DEFINE__AEABI_D2XLZ(d2lz, 1)

/* long long 到 float 转换 */
#define DEFINE__AEABI_XL2F(name, with_sign)                         \
  unsigned __aeabi_##name(unsigned long long v) {                   \
    int s /* 移位量 */, flb /* 第一个丢失的位 */, sign = 0;         \
    unsigned p = 0 /* 幂 */, ret;                                   \
    double_unsigned_struct val;                                     \
                                                                    \
    /* 负浮点数的尾数用反码编码 */                                  \
    if (with_sign && (v & (1ULL << 63))) {                          \
      sign = 1;                                                     \
      v = ~v + 1;                                                   \
    }                                                               \
    val.low = v;                                                    \
    val.high = v >> 32;                                             \
    /* 填充尾数位 */                                                \
    for (s = 31, p = 1 << 31; p && !(val.high & p); s--, p >>= 1);  \
    if (p) {                                                        \
      ret = val.high & (p - 1);                                     \
      if (s < FLOAT_FRAC_BITS) {                                    \
        ret <<= FLOAT_FRAC_BITS - s;                                \
        ret |= val.low >> (32 - (FLOAT_FRAC_BITS - s));             \
        flb = (val.low >> (32 - (FLOAT_FRAC_BITS - s - 1))) & 1;    \
      } else {                                                      \
        flb = (ret >> (s - FLOAT_FRAC_BITS - 1)) & 1;               \
        ret >>= s - FLOAT_FRAC_BITS;                                \
      }                                                             \
      s += 32;                                                      \
    } else {                                                        \
      for (s = 31, p = 1 << 31; p && !(val.low & p); s--, p >>= 1); \
      if (p) {                                                      \
        ret = val.low & (p - 1);                                    \
        if (s <= FLOAT_FRAC_BITS) {                                 \
          ret <<= FLOAT_FRAC_BITS - s;                              \
          flb = 0;                                                  \
        } else {                                                    \
          flb = (ret >> (s - FLOAT_FRAC_BITS - 1)) & 1;             \
          ret >>= s - FLOAT_FRAC_BITS;                              \
        }                                                           \
      } else                                                        \
        return 0;                                                   \
    }                                                               \
    if (flb) ret++;                                                 \
                                                                    \
    /* 填充指数位 */                                                \
    ret |= (s + ONE_EXP(FLOAT)) << FLOAT_FRAC_BITS;                 \
                                                                    \
    /* 填充符号位 */                                                \
    ret |= sign << 31;                                              \
                                                                    \
    return ret;                                                     \
  }

/* 无符号 long long 到 float 转换 */
DEFINE__AEABI_XL2F(ul2f, 0)

/* long long 到 float 转换 */
DEFINE__AEABI_XL2F(l2f, 1)

/* long long 到 double 转换 */
#define __AEABI_XL2D(name, with_sign)                               \
  void __aeabi_##name(unsigned long long v) {                       \
    int s /* 移位量 */, high_shift, sign = 0;                       \
    unsigned tmp, p = 0;                                            \
    double_unsigned_struct val, ret;                                \
                                                                    \
    /* 负浮点数的尾数用反码编码 */                                  \
    if (with_sign && (v & (1ULL << 63))) {                          \
      sign = 1;                                                     \
      v = ~v + 1;                                                   \
    }                                                               \
    val.low = v;                                                    \
    val.high = v >> 32;                                             \
                                                                    \
    /* 填充尾数位 */                                                \
    for (s = 31, p = 1 << 31; p && !(val.high & p); s--, p >>= 1);  \
    if (p) {                                                        \
      tmp = val.high & (p - 1);                                     \
      if (s < DOUBLE_FRAC_BITS - 32) {                              \
        high_shift = DOUBLE_FRAC_BITS - 32 - s;                     \
        ret.high = tmp << high_shift;                               \
        ret.high |= val.low >> (32 - high_shift);                   \
        ret.low = val.low << high_shift;                            \
      } else {                                                      \
        high_shift = s - (DOUBLE_FRAC_BITS - 32);                   \
        ret.high = tmp >> high_shift;                               \
        ret.low = tmp << (32 - high_shift);                         \
        ret.low |= val.low >> high_shift;                           \
        if ((val.low >> (high_shift - 1)) & 1) {                    \
          if (ret.low == UINT_MAX) {                                \
            ret.high++;                                             \
            ret.low = 0;                                            \
          } else                                                    \
            ret.low++;                                              \
        }                                                           \
      }                                                             \
      s += 32;                                                      \
    } else {                                                        \
      for (s = 31, p = 1 << 31; p && !(val.low & p); s--, p >>= 1); \
      if (p) {                                                      \
        tmp = val.low & (p - 1);                                    \
        if (s <= DOUBLE_FRAC_BITS - 32) {                           \
          high_shift = DOUBLE_FRAC_BITS - 32 - s;                   \
          ret.high = tmp << high_shift;                             \
          ret.low = 0;                                              \
        } else {                                                    \
          high_shift = s - (DOUBLE_FRAC_BITS - 32);                 \
          ret.high = tmp >> high_shift;                             \
          ret.low = tmp << (32 - high_shift);                       \
        }                                                           \
      } else {                                                      \
        ret.high = ret.low = 0;                                     \
        double_unsigned_struct_return(ret);                         \
      }                                                             \
    }                                                               \
                                                                    \
    /* 填充指数位 */                                                \
    ret.high |= (s + ONE_EXP(DOUBLE)) << (DOUBLE_FRAC_BITS - 32);   \
                                                                    \
    /* 填充符号位 */                                                \
    ret.high |= sign << 31;                                         \
                                                                    \
    double_unsigned_struct_return(ret);                             \
  }

/* 无符号 long long 到 double 转换 */
__AEABI_XL2D(ul2d, 0)

/* long long 到 double 转换 */
__AEABI_XL2D(l2d, 1)

/* Long long 辅助函数 */

/* TODO：在 den == 0 时补充错误处理（见 §4.3.1 和 §4.3.2） */

#define define_aeabi_xdivmod_signed_type(basetype, type) \
  typedef struct type {                                  \
    basetype quot;                                       \
    unsigned basetype rem;                               \
  } type

#define define_aeabi_xdivmod_unsigned_type(basetype, type) \
  typedef struct type {                                    \
    basetype quot;                                         \
    basetype rem;                                          \
  } type

#define AEABI_UXDIVMOD(name, type, rettype, typemacro)                         \
  static inline rettype aeabi_##name(type num, type den) {                     \
    rettype ret;                                                               \
    type quot = 0;                                                             \
                                                                               \
    /* 在商小于被除数时不断增大商 */                                           \
    while (num >= den) {                                                       \
      type q = 1;                                                              \
                                                                               \
      /* 寻找最接近的 2 的幂 */                                                \
      while ((q << 1) * den <= num && q * den <= typemacro##_MAX / 2) q <<= 1; \
                                                                               \
      /* 计算当前商与被除数之差 */                                             \
      num -= q * den;                                                          \
      quot += q;                                                               \
    }                                                                          \
    ret.quot = quot;                                                           \
    ret.rem = num;                                                             \
    return ret;                                                                \
  }

#define __AEABI_XDIVMOD(name, type, uiname, rettype, urettype, typemacro) \
  void __aeabi_##name(type numerator, type denominator) {                 \
    unsigned type num, den;                                               \
    urettype uxdiv_ret;                                                   \
    rettype ret;                                                          \
                                                                          \
    if (numerator >= 0)                                                   \
      num = numerator;                                                    \
    else                                                                  \
      num = 0 - numerator;                                                \
    if (denominator >= 0)                                                 \
      den = denominator;                                                  \
    else                                                                  \
      den = 0 - denominator;                                              \
    uxdiv_ret = aeabi_##uiname(num, den);                                 \
    /* 符号不同 */                                                        \
    if ((numerator & typemacro##_MIN) != (denominator & typemacro##_MIN)) \
      ret.quot = 0 - uxdiv_ret.quot;                                      \
    else                                                                  \
      ret.quot = uxdiv_ret.quot;                                          \
    if (numerator < 0)                                                    \
      ret.rem = 0 - uxdiv_ret.rem;                                        \
    else                                                                  \
      ret.rem = uxdiv_ret.rem;                                            \
                                                                          \
    rettype##_return(ret);                                                \
  }

define_aeabi_xdivmod_signed_type(long long, lldiv_t);
define_aeabi_xdivmod_unsigned_type(unsigned long long, ulldiv_t);
define_aeabi_xdivmod_signed_type(int, idiv_t);
define_aeabi_xdivmod_unsigned_type(unsigned, uidiv_t);

REGS_RETURN(lldiv_t, lldiv_t)
REGS_RETURN(ulldiv_t, ulldiv_t)
REGS_RETURN(idiv_t, idiv_t)
REGS_RETURN(uidiv_t, uidiv_t)

AEABI_UXDIVMOD(uldivmod, unsigned long long, ulldiv_t, ULLONG)

__AEABI_XDIVMOD(ldivmod, long long, uldivmod, lldiv_t, ulldiv_t, LLONG)

void __aeabi_uldivmod(unsigned long long num, unsigned long long den) {
  ulldiv_t_return(aeabi_uldivmod(num, den));
}

void __aeabi_llsl(double_unsigned_struct val, int shift) {
  double_unsigned_struct ret;

  if (shift >= 32) {
    val.high = val.low;
    val.low = 0;
    shift -= 32;
  }
  if (shift > 0) {
    ret.low = val.low << shift;
    ret.high = (val.high << shift) | (val.low >> (32 - shift));
    double_unsigned_struct_return(ret);
    return;
  }
  double_unsigned_struct_return(val);
}

#define aeabi_lsr(val, shift, fill, type)                      \
  type##_struct ret;                                           \
                                                               \
  if (shift >= 32) {                                           \
    val.low = val.high;                                        \
    val.high = fill;                                           \
    shift -= 32;                                               \
  }                                                            \
  if (shift > 0) {                                             \
    ret.high = val.high >> shift;                              \
    ret.low = (val.high << (32 - shift)) | (val.low >> shift); \
    type##_struct_return(ret);                                 \
    return;                                                    \
  }                                                            \
  type##_struct_return(val);

void __aeabi_llsr(double_unsigned_struct val, int shift) {
  aeabi_lsr(val, shift, 0, double_unsigned);
}

void __aeabi_lasr(unsigned_int_struct val, int shift) {
  aeabi_lsr(val, shift, val.high >> 31, unsigned_int);
}

/* 整数除法函数 */

AEABI_UXDIVMOD(uidivmod, unsigned, uidiv_t, UINT)

int __aeabi_idiv(int numerator, int denominator) {
  unsigned num, den;
  uidiv_t ret;

  if (numerator >= 0)
    num = numerator;
  else
    num = 0 - numerator;
  if (denominator >= 0)
    den = denominator;
  else
    den = 0 - denominator;
  ret = aeabi_uidivmod(num, den);
  if ((numerator & INT_MIN) != (denominator & INT_MIN)) /* 符号不同 */
    ret.quot *= -1;
  return ret.quot;
}

unsigned __aeabi_uidiv(unsigned num, unsigned den) {
  return aeabi_uidivmod(num, den).quot;
}

__AEABI_XDIVMOD(idivmod, int, uidivmod, idiv_t, uidiv_t, INT)

void __aeabi_uidivmod(unsigned num, unsigned den) {
  uidiv_t_return(aeabi_uidivmod(num, den));
}
