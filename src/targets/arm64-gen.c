/*
 *  TCC 的 A64 代码生成器
 *
 *  Copyright (c) 2014-2015 Edmund Grimley Evans
 *
 * 允许以任何介质复制和分发本文件，无论是否修改，
 * 无需版税，前提是保留上述版权声明和本声明。
 * 本文件按原样提供，不附带任何担保。
 *
 */

#ifdef TARGET_DEFS_ONLY

// 可用于分配器的寄存器数量：
#define NB_REGS 28 // x0-x18, x30, v0-v7

#define TREG_R(x) (x) // x = 0..18
#define TREG_R30 19
#define TREG_F(x) (x + 20) // x = 0..7

// 寄存器类，从更通用到更精确排序：
#define RC_INT (1 << 0)
#define RC_FLOAT (1 << 1)
#define RC_R(x) (1 << (2 + (x))) // x = 0..18
#define RC_R30 (1 << 21)
#define RC_F(x) (1 << (22 + (x))) // x = 0..7

#define RC_IRET (RC_R(0)) // int 返回寄存器类
#define RC_FRET (RC_F(0)) // float 返回寄存器类

#define REG_IRET (TREG_R(0)) // int 返回寄存器编号
#define REG_FRET (TREG_F(0)) // float 返回寄存器编号

#define PTR_SIZE 8

#define LDOUBLE_SIZE 16
#define LDOUBLE_ALIGN 16

#define MAX_ALIGN 16

#define CHAR_IS_UNSIGNED

/******************************************************/
#else /* ! TARGET_DEFS_ONLY */
/******************************************************/
#include "tcc.h"
#include <assert.h>

ST_DATA const int reg_classes[NB_REGS] = {
    RC_INT | RC_R(0),
    RC_INT | RC_R(1),
    RC_INT | RC_R(2),
    RC_INT | RC_R(3),
    RC_INT | RC_R(4),
    RC_INT | RC_R(5),
    RC_INT | RC_R(6),
    RC_INT | RC_R(7),
    RC_INT | RC_R(8),
    RC_INT | RC_R(9),
    RC_INT | RC_R(10),
    RC_INT | RC_R(11),
    RC_INT | RC_R(12),
    RC_INT | RC_R(13),
    RC_INT | RC_R(14),
    RC_INT | RC_R(15),
    RC_INT | RC_R(16),
    RC_INT | RC_R(17),
    RC_INT | RC_R(18),
    RC_R30, // 不在 RC_INT 中，因为我们要特殊使用 x30
    RC_FLOAT | RC_F(0),
    RC_FLOAT | RC_F(1),
    RC_FLOAT | RC_F(2),
    RC_FLOAT | RC_F(3),
    RC_FLOAT | RC_F(4),
    RC_FLOAT | RC_F(5),
    RC_FLOAT | RC_F(6),
    RC_FLOAT | RC_F(7)};

#define IS_FREG(x) ((x) >= TREG_F(0))

static uint32_t intr(int r) {
  assert(TREG_R(0) <= r && r <= TREG_R30);
  return r < TREG_R30 ? r : 30;
}

static uint32_t fltr(int r) {
  assert(TREG_F(0) <= r && r <= TREG_F(7));
  return r - TREG_F(0);
}

// 向 text 段添加一条指令：
ST_FUNC void o(unsigned int c) {
  int ind1 = ind + 4;
  if (nocode_wanted)
    return;
  if (ind1 > cur_text_section->data_allocated)
    section_realloc(cur_text_section, ind1);
  write32le(cur_text_section->data + ind, c);
  ind = ind1;
}

static int arm64_encode_bimm64(uint64_t x) {
  int neg = x & 1;
  int rep, pos, len;

  if (neg)
    x = ~x;
  if (!x)
    return -1;

  if (x >> 2 == (x & (((uint64_t)1 << (64 - 2)) - 1)))
    rep = 2, x &= ((uint64_t)1 << 2) - 1;
  else if (x >> 4 == (x & (((uint64_t)1 << (64 - 4)) - 1)))
    rep = 4, x &= ((uint64_t)1 << 4) - 1;
  else if (x >> 8 == (x & (((uint64_t)1 << (64 - 8)) - 1)))
    rep = 8, x &= ((uint64_t)1 << 8) - 1;
  else if (x >> 16 == (x & (((uint64_t)1 << (64 - 16)) - 1)))
    rep = 16, x &= ((uint64_t)1 << 16) - 1;
  else if (x >> 32 == (x & (((uint64_t)1 << (64 - 32)) - 1)))
    rep = 32, x &= ((uint64_t)1 << 32) - 1;
  else
    rep = 64;

  pos = 0;
  if (!(x & (((uint64_t)1 << 32) - 1)))
    x >>= 32, pos += 32;
  if (!(x & (((uint64_t)1 << 16) - 1)))
    x >>= 16, pos += 16;
  if (!(x & (((uint64_t)1 << 8) - 1)))
    x >>= 8, pos += 8;
  if (!(x & (((uint64_t)1 << 4) - 1)))
    x >>= 4, pos += 4;
  if (!(x & (((uint64_t)1 << 2) - 1)))
    x >>= 2, pos += 2;
  if (!(x & (((uint64_t)1 << 1) - 1)))
    x >>= 1, pos += 1;

  len = 0;
  if (!(~x & (((uint64_t)1 << 32) - 1)))
    x >>= 32, len += 32;
  if (!(~x & (((uint64_t)1 << 16) - 1)))
    x >>= 16, len += 16;
  if (!(~x & (((uint64_t)1 << 8) - 1)))
    x >>= 8, len += 8;
  if (!(~x & (((uint64_t)1 << 4) - 1)))
    x >>= 4, len += 4;
  if (!(~x & (((uint64_t)1 << 2) - 1)))
    x >>= 2, len += 2;
  if (!(~x & (((uint64_t)1 << 1) - 1)))
    x >>= 1, len += 1;

  if (x)
    return -1;
  if (neg) {
    pos = (pos + len) & (rep - 1);
    len = rep - len;
  }
  return ((0x1000 & rep << 6) | (((rep - 1) ^ 31) << 1 & 63) |
          ((rep - pos) & (rep - 1)) << 6 | (len - 1));
}

static uint32_t arm64_movi(int r, uint64_t x) {
  uint64_t m = 0xffff;
  int e;
  if (!(x & ~m))
    return 0x52800000 | r | x << 5; // movz w(r),#(x)
  if (!(x & ~(m << 16)))
    return 0x52a00000 | r | x >> 11; // movz w(r),#(x >> 16),lsl #16
  if (!(x & ~(m << 32)))
    return 0xd2c00000 | r | x >> 27; // movz x(r),#(x >> 32),lsl #32
  if (!(x & ~(m << 48)))
    return 0xd2e00000 | r | x >> 43; // movz x(r),#(x >> 48),lsl #48
  if ((x & ~m) == m << 16)
    return (0x12800000 | r | (~x << 5 & 0x1fffe0)); // movn w(r),#(~x)
  if ((x & ~(m << 16)) == m)
    return (0x12a00000 | r |
            (~x >> 11 & 0x1fffe0)); // movn w(r),#(~x >> 16),lsl #16
  if (!~(x | m))
    return (0x92800000 | r | (~x << 5 & 0x1fffe0)); // movn x(r),#(~x)
  if (!~(x | m << 16))
    return (0x92a00000 | r |
            (~x >> 11 & 0x1fffe0)); // movn x(r),#(~x >> 16),lsl #16
  if (!~(x | m << 32))
    return (0x92c00000 | r |
            (~x >> 27 & 0x1fffe0)); // movn x(r),#(~x >> 32),lsl #32
  if (!~(x | m << 48))
    return (0x92e00000 | r |
            (~x >> 43 & 0x1fffe0)); // movn x(r),#(~x >> 32),lsl #32
  if (!(x >> 32) && (e = arm64_encode_bimm64(x | x << 32)) >= 0)
    return 0x320003e0 | r | (uint32_t)e << 10; // movi w(r),#(x)
  if ((e = arm64_encode_bimm64(x)) >= 0)
    return 0xb20003e0 | r | (uint32_t)e << 10; // movi x(r),#(x)
  return 0;
}

static void arm64_movimm(int r, uint64_t x) {
  uint32_t i;
  if ((i = arm64_movi(r, x)))
    o(i); // 单条 MOV
  else {
    // MOVZ/MOVN 加 1-3 条 MOVK
    int z = 0, m = 0;
    uint32_t mov1 = 0xd2800000; // movz
    uint64_t x1 = x;
    for (i = 0; i < 64; i += 16) {
      z += !(x >> i & 0xffff);
      m += !(~x >> i & 0xffff);
    }
    if (m > z) {
      x1 = ~x;
      mov1 = 0x92800000; // movn
    }
    for (i = 0; i < 64; i += 16)
      if (x1 >> i & 0xffff) {
        o(mov1 | r | (x1 >> i & 0xffff) << 5 | i << 17);
        // movz/movn x(r),#(*),lsl #(i)
        break;
      }
    for (i += 16; i < 64; i += 16)
      if (x1 >> i & 0xffff)
        o(0xf2800000 | r | (x >> i & 0xffff) << 5 | i << 17);
    // movk x(r),#(*),lsl #(i)
  }
}

// 把 t 指向的链表中所有分支修补为跳转到 a：
ST_FUNC void gsym_addr(int t_, int a_) {
  uint32_t t = t_;
  uint32_t a = a_;
  while (t) {
    unsigned char *ptr = cur_text_section->data + t;
    uint32_t next = read32le(ptr);
    if (a - t + 0x8000000 >= 0x10000000)
      tcc_error("branch out of range");
    write32le(ptr, (a - t == 4 ? 0xd503201f :                      // nop
                        0x14000000 | ((a - t) >> 2 & 0x3ffffff))); // b
    t = next;
  }
}

// 把 t 指向的链表中所有分支修补为跳转到当前位置：
ST_FUNC void gsym(int t) { gsym_addr(t, ind); }

static int arm64_type_size(int t) {
  switch (t & VT_BTYPE) {
  case VT_INT:
    return 2;
  case VT_BYTE:
    return 0;
  case VT_SHORT:
    return 1;
  case VT_PTR:
    return 3;
  case VT_FUNC:
    return 3;
  case VT_FLOAT:
    return 2;
  case VT_DOUBLE:
    return 3;
  case VT_LDOUBLE:
    return 4;
  case VT_BOOL:
    return 0;
  case VT_LLONG:
    return 3;
  }
  fprintf(stderr, "[yh] type_size assert t=0x%x\n", t);
  assert(0);
  return 0;
}

static void arm64_spoff(int reg, uint64_t off) {
  uint32_t sub = off >> 63;
  if (sub)
    off = -off;
  if (off < 4096)
    o(0x910003e0 | sub << 30 | reg | off << 10);
  // (add|sub) x(reg),sp,#(off)
  else {
    arm64_movimm(30, off);           // 用 x30 存放偏移
    o(0x8b3e63e0 | sub << 30 | reg); // (add|sub) x(reg),sp,x30
  }
}

static void arm64_ldrx(int sg, int sz_, int dst, int bas, uint64_t off) {
  uint32_t sz = sz_;
  if (sz >= 2)
    sg = 0;
  if (!(off & ~((uint32_t)0xfff << sz)))
    o(0x39400000 | dst | bas << 5 | off << (10 - sz) | (uint32_t)!!sg << 23 |
      sz << 30); // ldr(*) x(dst),[x(bas),#(off)]
  else if (off < 256 || -off <= 256)
    o(0x38400000 | dst | bas << 5 | (off & 511) << 12 | (uint32_t)!!sg << 23 |
      sz << 30); // ldur(*) x(dst),[x(bas),#(off)]
  else {
    arm64_movimm(30, off); // 用 x30 存放偏移
    o(0x38206800 | dst | bas << 5 | (uint32_t)30 << 16 |
      (uint32_t)(!!sg + 1) << 22 | sz << 30); // ldr(*) x(dst),[x(bas),x30]
  }
}

static void arm64_ldrv(int sz_, int dst, int bas, uint64_t off) {
  uint32_t sz = sz_;
  if (!(off & ~((uint32_t)0xfff << sz)))
    o(0x3d400000 | dst | bas << 5 | off << (10 - sz) | (sz & 4) << 21 |
      (sz & 3) << 30); // ldr (s|d|q)(dst),[x(bas),#(off)]
  else if (off < 256 || -off <= 256)
    o(0x3c400000 | dst | bas << 5 | (off & 511) << 12 | (sz & 4) << 21 |
      (sz & 3) << 30); // ldur (s|d|q)(dst),[x(bas),#(off)]
  else {
    arm64_movimm(30, off); // 用 x30 存放偏移
    o(0x3c606800 | dst | bas << 5 | (uint32_t)30 << 16 | sz << 30 |
      (sz & 4) << 21); // ldr (s|d|q)(dst),[x(bas),x30]
  }
}

static void arm64_ldrs(int reg_, int size) {
  uint32_t reg = reg_;
  // 某些情况下用 x30 存放中间值。
  switch (size) {
  default:
    assert(0);
    break;
  case 1:
    arm64_ldrx(0, 0, reg, reg, 0);
    break;
  case 2:
    arm64_ldrx(0, 1, reg, reg, 0);
    break;
  case 3:
    arm64_ldrx(0, 1, 30, reg, 0);
    arm64_ldrx(0, 0, reg, reg, 2);
    o(0x2a0043c0 | reg | reg << 16); // orr x(reg),x30,x(reg),lsl #16
    break;
  case 4:
    arm64_ldrx(0, 2, reg, reg, 0);
    break;
  case 5:
    arm64_ldrx(0, 2, 30, reg, 0);
    arm64_ldrx(0, 0, reg, reg, 4);
    o(0xaa0083c0 | reg | reg << 16); // orr x(reg),x30,x(reg),lsl #32
    break;
  case 6:
    arm64_ldrx(0, 2, 30, reg, 0);
    arm64_ldrx(0, 1, reg, reg, 4);
    o(0xaa0083c0 | reg | reg << 16); // orr x(reg),x30,x(reg),lsl #32
    break;
  case 7:
    arm64_ldrx(0, 2, 30, reg, 0);
    arm64_ldrx(0, 2, reg, reg, 3);
    o(0x53087c00 | reg | reg << 5);  // lsr w(reg), w(reg), #8
    o(0xaa0083c0 | reg | reg << 16); // orr x(reg),x30,x(reg),lsl #32
    break;
  case 8:
    arm64_ldrx(0, 3, reg, reg, 0);
    break;
  case 9:
    arm64_ldrx(0, 0, reg + 1, reg, 8);
    arm64_ldrx(0, 3, reg, reg, 0);
    break;
  case 10:
    arm64_ldrx(0, 1, reg + 1, reg, 8);
    arm64_ldrx(0, 3, reg, reg, 0);
    break;
  case 11:
    arm64_ldrx(0, 2, reg + 1, reg, 7);
    o(0x53087c00 | (reg + 1) | (reg + 1) << 5); // lsr w(reg+1), w(reg+1), #8
    arm64_ldrx(0, 3, reg, reg, 0);
    break;
  case 12:
    arm64_ldrx(0, 2, reg + 1, reg, 8);
    arm64_ldrx(0, 3, reg, reg, 0);
    break;
  case 13:
    arm64_ldrx(0, 3, reg + 1, reg, 5);
    o(0xd358fc00 | (reg + 1) | (reg + 1) << 5); // lsr x(reg+1), x(reg+1), #24
    arm64_ldrx(0, 3, reg, reg, 0);
    break;
  case 14:
    arm64_ldrx(0, 3, reg + 1, reg, 6);
    o(0xd350fc00 | (reg + 1) | (reg + 1) << 5); // lsr x(reg+1), x(reg+1), #16
    arm64_ldrx(0, 3, reg, reg, 0);
    break;
  case 15:
    arm64_ldrx(0, 3, reg + 1, reg, 7);
    o(0xd348fc00 | (reg + 1) | (reg + 1) << 5); // lsr x(reg+1), x(reg+1), #8
    arm64_ldrx(0, 3, reg, reg, 0);
    break;
  case 16:
    o(0xa9400000 | reg | (reg + 1) << 10 | reg << 5);
    // ldp x(reg),x(reg+1),[x(reg)]
    break;
  }
}

static void arm64_strx(int sz_, int dst, int bas, uint64_t off) {
  uint32_t sz = sz_;
  if (!(off & ~((uint32_t)0xfff << sz)))
    o(0x39000000 | dst | bas << 5 | off << (10 - sz) | sz << 30);
  // str(*) x(dst),[x(bas],#(off)]
  else if (off < 256 || -off <= 256)
    o(0x38000000 | dst | bas << 5 | (off & 511) << 12 | sz << 30);
  // stur(*) x(dst),[x(bas],#(off)]
  else {
    arm64_movimm(30, off); // 用 x30 存放偏移
    o(0x38206800 | dst | bas << 5 | (uint32_t)30 << 16 | sz << 30);
    // str(*) x(dst),[x(bas),x30]
  }
}

static void arm64_strv(int sz_, int dst, int bas, uint64_t off) {
  uint32_t sz = sz_;
  if (!(off & ~((uint32_t)0xfff << sz)))
    o(0x3d000000 | dst | bas << 5 | off << (10 - sz) | (sz & 4) << 21 |
      (sz & 3) << 30); // str (s|d|q)(dst),[x(bas),#(off)]
  else if (off < 256 || -off <= 256)
    o(0x3c000000 | dst | bas << 5 | (off & 511) << 12 | (sz & 4) << 21 |
      (sz & 3) << 30); // stur (s|d|q)(dst),[x(bas),#(off)]
  else {
    arm64_movimm(30, off); // 用 x30 存放偏移
    o(0x3c206800 | dst | bas << 5 | (uint32_t)30 << 16 | sz << 30 |
      (sz & 4) << 21); // str (s|d|q)(dst),[x(bas),x30]
  }
}

static void arm64_sym(int r, Sym *sym, unsigned long addend) {
  // 目前 TCC 的链接器在 tcc 以 "-run" 调用时不会为
  // STT_OBJECT 生成 COPY 重定位。当程序引用 stdin 时，
  // 这通常会导致 "R_AARCH64_ADR_PREL_PG_HI21 relocation failed"。
  // 解决办法是避开那个重定位，只使用范围无限的
  // 重定位。
  // Mach-O（Darwin 本机输出）：必须用 adrp+add（ld64 不接受
  // movw/movk 上的 UNSIGNED 重定位），由 ADDEND 重定位携带偏移。
  int avoid_adrp =
      tcc_state->output_format != TCC_OUTPUT_FORMAT_MACHO;

  if (avoid_adrp || sym->a.weak) {
    // （GCC 在这种情况下使用 R_AARCH64_ABS64。）
    greloca(cur_text_section, sym, ind, R_AARCH64_MOVW_UABS_G0_NC, addend);
    o(0xd2800000 | r); // mov x(rt),#0,lsl #0
    greloca(cur_text_section, sym, ind, R_AARCH64_MOVW_UABS_G1_NC, addend);
    o(0xf2a00000 | r); // movk x(rt),#0,lsl #16
    greloca(cur_text_section, sym, ind, R_AARCH64_MOVW_UABS_G2_NC, addend);
    o(0xf2c00000 | r); // movk x(rt),#0,lsl #32
    greloca(cur_text_section, sym, ind, R_AARCH64_MOVW_UABS_G3, addend);
    o(0xf2e00000 | r); // movk x(rt),#0,lsl #48
  } else {
    greloca(cur_text_section, sym, ind, R_AARCH64_ADR_PREL_PG_HI21, addend);
    o(0x90000000 | r);
    greloca(cur_text_section, sym, ind, R_AARCH64_ADD_ABS_LO12_NC, addend);
    o(0x91000000 | r | r << 5);
  }
}

ST_FUNC void load(int r, SValue *sv) {
  int svtt = sv->type.t;
  int svr = sv->r & ~VT_LVAL_TYPE;
  int svrv = svr & VT_VALMASK;
  uint64_t svcul = (uint32_t)sv->c.i;
  svcul = svcul >> 31 & 1 ? svcul - ((uint64_t)1 << 32) : svcul;

  if (svr == (VT_LOCAL | VT_LVAL)) {
    if (IS_FREG(r))
      arm64_ldrv(arm64_type_size(svtt), fltr(r), 29, svcul);
    else
      arm64_ldrx(!(svtt & VT_UNSIGNED), arm64_type_size(svtt), intr(r), 29,
                 svcul);
    return;
  }

  if ((svr & ~VT_VALMASK) == VT_LVAL && svrv < VT_CONST) {
    if (IS_FREG(r))
      arm64_ldrv(arm64_type_size(svtt), fltr(r), intr(svrv), 0);
    else
      arm64_ldrx(!(svtt & VT_UNSIGNED), arm64_type_size(svtt), intr(r),
                 intr(svrv), 0);
    return;
  }

  if (svr == (VT_CONST | VT_LVAL | VT_SYM)) {
    arm64_sym(30, sv->sym, svcul); // 用 x30 存放地址
    if (IS_FREG(r))
      arm64_ldrv(arm64_type_size(svtt), fltr(r), 30, 0);
    else
      arm64_ldrx(!(svtt & VT_UNSIGNED), arm64_type_size(svtt), intr(r), 30, 0);
    return;
  }

  if (svr == (VT_CONST | VT_SYM)) {
    arm64_sym(intr(r), sv->sym, svcul);
    return;
  }

  if (svr == VT_CONST) {
    if ((svtt & VT_BTYPE) != VT_VOID)
      arm64_movimm(intr(r),
                   arm64_type_size(svtt) == 3 ? sv->c.i : (uint32_t)svcul);
    return;
  }

  if (svr < VT_CONST) {
    if (IS_FREG(r) && IS_FREG(svr))
      if (svtt == VT_LDOUBLE)
        o(0x4ea01c00 | fltr(r) | fltr(svr) << 5);
      // mov v(r).16b,v(svr).16b
      else
        o(0x1e604000 | fltr(r) | fltr(svr) << 5); // fmov d(r),d(svr)
    else if (!IS_FREG(r) && !IS_FREG(svr))
      o(0xaa0003e0 | intr(r) | intr(svr) << 16); // mov x(r),x(svr)
    else
      assert(0);
    return;
  }

  if (svr == VT_LOCAL) {
    if (-svcul < 0x1000)
      o(0xd10003a0 | intr(r) | -svcul << 10); // sub x(r),x29,#...
    else {
      arm64_movimm(30, -svcul);                     // 用 x30 存放偏移
      o(0xcb0003a0 | intr(r) | (uint32_t)30 << 16); // sub x(r),x29,x30
    }
    return;
  }

  if (svr == VT_JMP || svr == VT_JMPI) {
    int t = (svr == VT_JMPI);
    arm64_movimm(intr(r), t);
    o(0x14000002); // b .+8
    gsym(svcul);
    arm64_movimm(intr(r), t ^ 1);
    return;
  }

  if (svr == (VT_LLOCAL | VT_LVAL)) {
    arm64_ldrx(0, 3, 30, 29, svcul); // 用 x30 存放偏移
    if (IS_FREG(r))
      arm64_ldrv(arm64_type_size(svtt), fltr(r), 30, 0);
    else
      arm64_ldrx(!(svtt & VT_UNSIGNED), arm64_type_size(svtt), intr(r), 30, 0);
    return;
  }

  printf("load(%x, (%x, %x, %llx))\n", r, svtt, sv->r, (long long)svcul);
  assert(0);
}

ST_FUNC void store(int r, SValue *sv) {
  int svtt = sv->type.t;
  int svr = sv->r & ~VT_LVAL_TYPE;
  int svrv = svr & VT_VALMASK;
  uint64_t svcul = (uint32_t)sv->c.i;
  svcul = svcul >> 31 & 1 ? svcul - ((uint64_t)1 << 32) : svcul;

  if (svr == (VT_LOCAL | VT_LVAL)) {
    if (IS_FREG(r))
      arm64_strv(arm64_type_size(svtt), fltr(r), 29, svcul);
    else
      arm64_strx(arm64_type_size(svtt), intr(r), 29, svcul);
    return;
  }

  if ((svr & ~VT_VALMASK) == VT_LVAL && svrv < VT_CONST) {
    if (IS_FREG(r))
      arm64_strv(arm64_type_size(svtt), fltr(r), intr(svrv), 0);
    else
      arm64_strx(arm64_type_size(svtt), intr(r), intr(svrv), 0);
    return;
  }

  if (svr == (VT_CONST | VT_LVAL | VT_SYM)) {
    arm64_sym(30, sv->sym, svcul); // 用 x30 存放地址
    if (IS_FREG(r))
      arm64_strv(arm64_type_size(svtt), fltr(r), 30, 0);
    else
      arm64_strx(arm64_type_size(svtt), intr(r), 30, 0);
    return;
  }

  fprintf(stderr, "store(%x, (%x, %x, %llx))\n", r, svtt, sv->r,
          (long long)svcul);
  assert(0);
}

static void arm64_gen_bl_or_b(int b) {
  if ((vtop->r & (VT_VALMASK | VT_LVAL)) == VT_CONST) {
    assert(!b && (vtop->r & VT_SYM));
    greloca(cur_text_section, vtop->sym, ind, R_AARCH64_CALL26, 0);
    o(0x94000000); // bl .
  } else
    o(0xd61f0000 | (uint32_t)!b << 21 | intr(gv(RC_R30)) << 5); // br/blr
}

static int arm64_hfa_aux(CType *type, int *fsize, int num) {
  if (is_float(type->t)) {
    int a, n = type_size(type, &a);
    if (num >= 4 || (*fsize && *fsize != n))
      return -1;
    *fsize = n;
    return num + 1;
  } else if ((type->t & VT_BTYPE) == VT_STRUCT) {
    int is_struct = 0; // 而不是用 union
    Sym *field;
    for (field = type->ref->next; field; field = field->next)
      if (field->c) {
        is_struct = 1;
        break;
      }
    if (is_struct) {
      int num0 = num;
      for (field = type->ref->next; field; field = field->next) {
        if (field->c != (num - num0) * *fsize)
          return -1;
        num = arm64_hfa_aux(&field->type, fsize, num);
        if (num == -1)
          return -1;
      }
      if (type->ref->c != (num - num0) * *fsize)
        return -1;
      return num;
    } else { // union
      int num0 = num;
      for (field = type->ref->next; field; field = field->next) {
        int num1 = arm64_hfa_aux(&field->type, fsize, num0);
        if (num1 == -1)
          return -1;
        num = num1 < num ? num : num1;
      }
      if (type->ref->c != (num - num0) * *fsize)
        return -1;
      return num;
    }
  } else if (type->t & VT_ARRAY) {
    int num1;
    if (!type->ref->c)
      return num;
    num1 = arm64_hfa_aux(&type->ref->type, fsize, num);
    if (num1 == -1 || (num1 != num && type->ref->c > 4))
      return -1;
    num1 = num + type->ref->c * (num1 - num);
    if (num1 > 4)
      return -1;
    return num1;
  }
  return -1;
}

static int arm64_hfa(CType *type, int *fsize) {
  if ((type->t & VT_BTYPE) == VT_STRUCT || (type->t & VT_ARRAY)) {
    int sz = 0;
    int n = arm64_hfa_aux(type, &sz, 0);
    if (0 < n && n <= 4) {
      if (fsize)
        *fsize = sz;
      return n;
    }
  }
  return 0;
}

static unsigned long arm64_pcs_aux(int n, CType **type, unsigned long *a,
                                   int n_named) {
  int nx = 0;            // 下一个整数寄存器
  int nv = 0;            // 下一个向量寄存器
  unsigned long ns = 32; // 下一个栈偏移
  int i;

  for (i = 0; i < n; i++) {
    int hfa = arm64_hfa(type[i], 0);
    int size, align;

    if ((type[i]->t & VT_ARRAY) || (type[i]->t & VT_BTYPE) == VT_FUNC)
      size = align = 8;
    else
      size = type_size(type[i], &align);

    // Darwin 变参约定：可变参数一律按 8 字节对齐放栈上（AAPCS 变体），
    // 命名参数照常分配寄存器。仅 Mach-O 本机输出启用。
    if (i >= n_named) {
      ns = (ns + 7) & ~7;
      if (align > 8)
        ns = (ns + align - 1) & -align;
      a[i] = ns;
      ns += size < 8 ? 8 : size;
      continue;
    }

    if (hfa)
      // B.2
      ;
    else if (size > 16) {
      // B.3：替换为指针
      if (nx < 8)
        a[i] = nx++ << 1 | 1;
      else {
        ns = (ns + 7) & ~7;
        a[i] = ns | 1;
        ns += 8;
      }
      continue;
    } else if ((type[i]->t & VT_BTYPE) == VT_STRUCT)
      // B.4
      size = (size + 7) & ~7;

    // C.1
    if (is_float(type[i]->t) && nv < 8) {
      a[i] = 16 + (nv++ << 1);
      continue;
    }

    // C.2
    if (hfa && nv + hfa <= 8) {
      a[i] = 16 + (nv << 1);
      nv += hfa;
      continue;
    }

    // C.3
    if (hfa) {
      nv = 8;
      size = (size + 7) & ~7;
    }

    // C.4
    if (hfa || (type[i]->t & VT_BTYPE) == VT_LDOUBLE) {
      ns = (ns + 7) & ~7;
      ns = (ns + align - 1) & -align;
    }

    // C.5
    if ((type[i]->t & VT_BTYPE) == VT_FLOAT)
      size = 8;

    // C.6
    if (hfa || is_float(type[i]->t)) {
      a[i] = ns;
      ns += size;
      continue;
    }

    // C.7
    if ((type[i]->t & VT_BTYPE) != VT_STRUCT && size <= 8 && nx < 8) {
      a[i] = nx++ << 1;
      continue;
    }

    // C.8
    if (align == 16)
      nx = (nx + 1) & ~1;

    // C.9
    if ((type[i]->t & VT_BTYPE) != VT_STRUCT && size == 16 && nx < 7) {
      a[i] = nx << 1;
      nx += 2;
      continue;
    }

    // C.10
    if ((type[i]->t & VT_BTYPE) == VT_STRUCT && size <= (8 - nx) * 8) {
      a[i] = nx << 1;
      nx += (size + 7) >> 3;
      continue;
    }

    // C.11
    nx = 8;

    // C.12
    ns = (ns + 7) & ~7;
    ns = (ns + align - 1) & -align;

    // C.13
    if ((type[i]->t & VT_BTYPE) == VT_STRUCT) {
      a[i] = ns;
      ns += size;
      continue;
    }

    // C.14
    if (size < 8)
      size = 8;

    // C.15
    a[i] = ns;
    ns += size;
  }

  return ns - 32;
}

static unsigned long arm64_pcs(int n, CType **type, unsigned long *a,
                               int n_named) {
  unsigned long stack;

  // 返回类型：
  if ((type[0]->t & VT_BTYPE) == VT_VOID)
    a[0] = -1;
  else {
    arm64_pcs_aux(1, type, a, 1);
    assert(a[0] == 0 || a[0] == 1 || a[0] == 16);
  }

  // 参数类型：
  stack = arm64_pcs_aux(n, type + 1, a + 1, n_named);

  if (0) {
    int i;
    for (i = 0; i <= n; i++) {
      if (!i)
        printf("arm64_pcs return: ");
      else
        printf("arm64_pcs arg %d: ", i);
      if (a[i] == (unsigned long)-1)
        printf("void\n");
      else if (a[i] == 1 && !i)
        printf("X8 pointer\n");
      else if (a[i] < 16)
        printf("X%lu%s\n", a[i] / 2, a[i] & 1 ? " pointer" : "");
      else if (a[i] < 32)
        printf("V%lu\n", a[i] / 2 - 8);
      else
        printf("stack %lu%s\n", (a[i] - 32) & ~1, a[i] & 1 ? " pointer" : "");
    }
  }

  return stack;
}

ST_FUNC void gfunc_call(int nb_args) {
  CType *return_type;
  CType **t;
  unsigned long *a, *a1;
  unsigned long stack;
  int i;

  return_type = &vtop[-nb_args].type.ref->type;
  if ((return_type->t & VT_BTYPE) == VT_STRUCT)
    --nb_args;

  t = tcc_malloc((nb_args + 1) * sizeof(*t));
  a = tcc_malloc((nb_args + 1) * sizeof(*a));
  a1 = tcc_malloc((nb_args + 1) * sizeof(*a1));

  t[0] = return_type;
  for (i = 0; i < nb_args; i++)
    t[nb_args - i] = &vtop[-i].type;

  // 变参函数：Darwin 约定下可变参数放栈上（命名参数个数 = 参数链长度）
  {
    CType *ft = &vtop[-nb_args].type;
    int n_named = nb_args;
    if (tcc_state->output_format == TCC_OUTPUT_FORMAT_MACHO &&
        (ft->t & VT_BTYPE) == VT_FUNC &&
        ft->ref->f.func_type == FUNC_ELLIPSIS) {
      Sym *p;
      n_named = 0;
      for (p = ft->ref->next; p; p = p->next)
        n_named++;
    }
    stack = arm64_pcs(nb_args, t, a, n_named);
  }

  // 为被替换为指针的结构体分配空间：
  for (i = nb_args; i; i--)
    if (a[i] & 1) {
      SValue *arg = &vtop[i - nb_args];
      int align, size = type_size(&arg->type, &align);
      assert((arg->type.t & VT_BTYPE) == VT_STRUCT);
      stack = (stack + align - 1) & -align;
      a1[i] = stack;
      stack += size;
    }

  stack = (stack + 15) >> 4 << 4;

  assert(stack < 0x1000);
  if (stack)
    o(0xd10003ff | stack << 10); // sub sp,sp,#(n)

  // 第一遍：把所有值放到栈上
  for (i = nb_args; i; i--) {
    vpushv(vtop - nb_args + i);

    if (a[i] & 1) {
      // 被替换为指针的结构体
      int r = get_reg(RC_INT);
      arm64_spoff(intr(r), a1[i]);
      vset(&vtop->type, r | VT_LVAL, 0);
      vswap();
      vstore();
      if (a[i] >= 32) {
        // 栈上的指针
        r = get_reg(RC_INT);
        arm64_spoff(intr(r), a1[i]);
        arm64_strx(3, intr(r), 31, (a[i] - 32) >> 1 << 1);
      }
    } else if (a[i] >= 32) {
      // 栈上的值
      if ((vtop->type.t & VT_BTYPE) == VT_STRUCT) {
        int r = get_reg(RC_INT);
        arm64_spoff(intr(r), a[i] - 32);
        vset(&vtop->type, r | VT_LVAL, 0);
        vswap();
        vstore();
      } else if (is_float(vtop->type.t)) {
        gv(RC_FLOAT);
        arm64_strv(arm64_type_size(vtop[0].type.t), fltr(vtop[0].r), 31,
                   a[i] - 32);
      } else {
        gv(RC_INT);
        arm64_strx(arm64_type_size(vtop[0].type.t), intr(vtop[0].r), 31,
                   a[i] - 32);
      }
    }

    --vtop;
  }

  // 第二遍：把值分配到寄存器
  for (i = nb_args; i; i--, vtop--) {
    if (a[i] < 16 && !(a[i] & 1)) {
      // 通用寄存器中的值
      if ((vtop->type.t & VT_BTYPE) == VT_STRUCT) {
        int align, size = type_size(&vtop->type, &align);
        vtop->type.t = VT_PTR;
        gaddrof();
        gv(RC_R(a[i] / 2));
        arm64_ldrs(a[i] / 2, size);
      } else
        gv(RC_R(a[i] / 2));
    } else if (a[i] < 16)
      // 寄存器中被替换为指针的结构体
      arm64_spoff(a[i] / 2, a1[i]);
    else if (a[i] < 32) {
      // 浮点寄存器中的值
      if ((vtop->type.t & VT_BTYPE) == VT_STRUCT) {
        uint32_t j, sz, n = arm64_hfa(&vtop->type, &sz);
        vtop->type.t = VT_PTR;
        gaddrof();
        gv(RC_R30);
        for (j = 0; j < n; j++)
          o(0x3d4003c0 | (sz & 16) << 19 | -(sz & 8) << 27 | (sz & 4) << 29 |
            (a[i] / 2 - 8 + j) | j << 10); // ldr ([sdq])(*),[x30,#(j * sz)]
      } else
        gv(RC_F(a[i] / 2 - 8));
    }
  }

  if ((return_type->t & VT_BTYPE) == VT_STRUCT) {
    if (a[0] == 1) {
      // 间接返回：设置 x8 并丢弃栈上的值
      gv(RC_R(8));
      --vtop;
    } else
      // 寄存器返回：保留该地址供调用之后使用
      vswap();
  }

  save_regs(0);
  arm64_gen_bl_or_b(0);
  --vtop;
  if (stack)
    o(0x910003ff | stack << 10); // add sp,sp,#(n)

  {
    int rt = return_type->t;
    int bt = rt & VT_BTYPE;
    if (bt == VT_BYTE || bt == VT_SHORT)
      // 提升小整数：
      o(0x13001c00 | (bt == VT_SHORT) << 13 |
        (uint32_t)!!(rt & VT_UNSIGNED) << 30); // [su]xt[bh] w0,w0
    else if (bt == VT_STRUCT && !(a[0] & 1)) {
      // 结构体在寄存器中返回，因此把它写出去：
      gv(RC_R(8));
      --vtop;
      if (a[0] == 0) {
        int align, size = type_size(return_type, &align);
        assert(size <= 16);
        if (size > 8)
          o(0xa9000500); // stp x0,x1,[x8]
        else if (size)
          arm64_strx(size > 4 ? 3 : size > 2 ? 2 : size > 1, 0, 8, 0);

      } else if (a[0] == 16) {
        uint32_t j, sz, n = arm64_hfa(return_type, &sz);
        for (j = 0; j < n; j++)
          o(0x3d000100 | (sz & 16) << 19 | -(sz & 8) << 27 | (sz & 4) << 29 |
            (a[i] / 2 - 8 + j) | j << 10); // str ([sdq])(*),[x8,#(j * sz)]
      }
    }
  }

  tcc_free(a1);
  tcc_free(a);
  tcc_free(t);
}

static unsigned long arm64_func_va_list_stack;
static int arm64_func_va_list_gr_offs;
static int arm64_func_va_list_vr_offs;
static int arm64_func_sub_sp_offset;

ST_FUNC void gfunc_prolog(CType *func_type) {
  int n = 0;
  int i = 0;
  Sym *sym;
  CType **t;
  unsigned long *a;

  // 为什么调用方（gen_function）不设置 func_vt？
  func_vt = func_type->ref->type;
  func_vc = 144; // 存放 x8 的位置的偏移

  for (sym = func_type->ref; sym; sym = sym->next)
    ++n;
  t = tcc_malloc(n * sizeof(*t));
  a = tcc_malloc(n * sizeof(*a));

  for (sym = func_type->ref; sym; sym = sym->next)
    t[i++] = &sym->type;

  arm64_func_va_list_stack = arm64_pcs(n - 1, t, a, n - 1);

  o(0xa9b27bfd); // stp x29,x30,[sp,#-224]!
  o(0xad0087e0); // stp q0,q1,[sp,#16]
  o(0xad018fe2); // stp q2,q3,[sp,#48]
  o(0xad0297e4); // stp q4,q5,[sp,#80]
  o(0xad039fe6); // stp q6,q7,[sp,#112]
  o(0xa90923e8); // stp x8,x8,[sp,#144]
  o(0xa90a07e0); // stp x0,x1,[sp,#160]
  o(0xa90b0fe2); // stp x2,x3,[sp,#176]
  o(0xa90c17e4); // stp x4,x5,[sp,#192]
  o(0xa90d1fe6); // stp x6,x7,[sp,#208]

  arm64_func_va_list_gr_offs = -64;
  arm64_func_va_list_vr_offs = -128;

  for (i = 1, sym = func_type->ref->next; sym; i++, sym = sym->next) {
    int off = (a[i] < 16   ? 160 + a[i] / 2 * 8
               : a[i] < 32 ? 16 + (a[i] - 16) / 2 * 16
                           : 224 + ((a[i] - 32) >> 1 << 1));
    sym_push(sym->v & ~SYM_FIELD, &sym->type,
             (a[i] & 1 ? VT_LLOCAL : VT_LOCAL) | lvalue_type(sym->type.t), off);

    if (a[i] < 16) {
      int align, size = type_size(&sym->type, &align);
      arm64_func_va_list_gr_offs =
          (a[i] / 2 - 7 + (!(a[i] & 1) && size > 8)) * 8;
    } else if (a[i] < 32) {
      uint32_t hfa = arm64_hfa(&sym->type, 0);
      arm64_func_va_list_vr_offs = (a[i] / 2 - 16 + (hfa ? hfa : 1)) * 16;
    }

    // float 和 double 的 HFA 需要以不同方式写出：
    if (16 <= a[i] && a[i] < 32 && (sym->type.t & VT_BTYPE) == VT_STRUCT) {
      uint32_t j, sz, k = arm64_hfa(&sym->type, &sz);
      if (sz < 16)
        for (j = 0; j < k; j++) {
          o(0x3d0003e0 | -(sz & 8) << 27 | (sz & 4) << 29 |
            ((a[i] - 16) / 2 + j) | (off / sz + j) << 10);
          // str ([sdq])(*),[sp,#(j * sz)]
        }
    }
  }

  tcc_free(a);
  tcc_free(t);

  o(0x910003fd); // mov x29,sp
  arm64_func_sub_sp_offset = ind;
  // 在 gfunc_epilog 中这些会被替换为递减 SP 的代码：
  o(0xd503201f); // nop
  o(0xd503201f); // nop
  loc = 0;
}

ST_FUNC void gen_va_start(void) {
  int r;
  --vtop; // 我们不需要 "arg"
  gaddrof();
  r = intr(gv(RC_INT));

  if (arm64_func_va_list_stack) {
    // xx 这里可以用 add（立即数）
    arm64_movimm(30, arm64_func_va_list_stack + 224);
    o(0x8b1e03be); // add x30,x29,x30
  } else
    o(0x910383be);        // add x30,x29,#224
  o(0xf900001e | r << 5); // str x30,[x(r)]

  if (arm64_func_va_list_gr_offs) {
    if (arm64_func_va_list_stack)
      o(0x910383be);        // add x30,x29,#224
    o(0xf900041e | r << 5); // str x30,[x(r),#8]
  }

  if (arm64_func_va_list_vr_offs) {
    o(0x910243be);          // add x30,x29,#144
    o(0xf900081e | r << 5); // str x30,[x(r),#16]
  }

  arm64_movimm(30, arm64_func_va_list_gr_offs);
  o(0xb900181e | r << 5); // str w30,[x(r),#24]

  arm64_movimm(30, arm64_func_va_list_vr_offs);
  o(0xb9001c1e | r << 5); // str w30,[x(r),#28]

  --vtop;
}

ST_FUNC void gen_va_arg(CType *t) {
  int align, size = type_size(t, &align);
  int fsize, hfa = arm64_hfa(t, &fsize);
  uint32_t r0, r1;

  if (is_float(t->t)) {
    hfa = 1;
    fsize = size;
  }

  gaddrof();
  r0 = intr(gv(RC_INT));
  r1 = get_reg(RC_INT);
  vtop[0].r = r1 | lvalue_type(t->t);
  r1 = intr(r1);

  if (!hfa) {
    uint32_t n = size > 16 ? 8 : (size + 7) & -8;
    o(0xb940181e | r0 << 5); // ldr w30,[x(r0),#24] // __gr_offs
    if (align == 16) {
      assert(0);     // 这条路径未测试，但 __uint128_t 需要它
      o(0x11003fde); // add w30,w30,#15
      o(0x121c6fde); // and w30,w30,#-16
    }
    o(0x310003c0 | r1 | n << 10);      // adds w(r1),w30,#(n)
    o(0x540000ad);                     // b.le .+20
    o(0xf9400000 | r1 | r0 << 5);      // ldr x(r1),[x(r0)] // __stack
    o(0x9100001e | r1 << 5 | n << 10); // add x30,x(r1),#(n)
    o(0xf900001e | r0 << 5);           // str x30,[x(r0)] // __stack
    o(0x14000004);                     // b .+16
    o(0xb9001800 | r1 | r0 << 5);      // str w(r1),[x(r0),#24] // __gr_offs
    o(0xf9400400 | r1 | r0 << 5);      // ldr x(r1),[x(r0),#8] // __gr_top
    o(0x8b3ec000 | r1 | r1 << 5);      // add x(r1),x(r1),w30,sxtw
    if (size > 16)
      o(0xf9400000 | r1 | r1 << 5); // ldr x(r1),[x(r1)]
  } else {
    uint32_t rsz = hfa << 4;
    uint32_t ssz = (size + 7) & -(uint32_t)8;
    uint32_t b1, b2;
    o(0xb9401c1e | r0 << 5);        // ldr w30,[x(r0),#28] // __vr_offs
    o(0x310003c0 | r1 | rsz << 10); // adds w(r1),w30,#(rsz)
    b1 = ind;
    o(0x5400000d);                // b.le lab1
    o(0xf9400000 | r1 | r0 << 5); // ldr x(r1),[x(r0)] // __stack
    if (fsize == 16) {
      o(0x91003c00 | r1 | r1 << 5); // add x(r1),x(r1),#15
      o(0x927cec00 | r1 | r1 << 5); // and x(r1),x(r1),#-16
    }
    o(0x9100001e | r1 << 5 | ssz << 10); // add x30,x(r1),#(ssz)
    o(0xf900001e | r0 << 5);             // str x30,[x(r0)] // __stack
    b2 = ind;
    o(0x14000000); // b lab2
    // lab1:
    write32le(cur_text_section->data + b1, 0x5400000d | (ind - b1) << 3);
    o(0xb9001c00 | r1 | r0 << 5); // str w(r1),[x(r0),#28] // __vr_offs
    o(0xf9400800 | r1 | r0 << 5); // ldr x(r1),[x(r0),#16] // __vr_top
    if (hfa == 1 || fsize == 16)
      o(0x8b3ec000 | r1 | r1 << 5); // add x(r1),x(r1),w30,sxtw
    else {
      // 我们需要改变这个 HFA 的布局。
      // 用全局变量 "loc" 在栈上获取一些空间：
      loc = (loc - size) & -(uint32_t)align;
      o(0x8b3ec000 | 30 | r1 << 5); // add x30,x(r1),w30,sxtw
      arm64_movimm(r1, loc);
      o(0x8b0003a0 | r1 | r1 << 16); // add x(r1),x29,x(r1)
      o(0x4c402bdc | (uint32_t)fsize << 7 | (uint32_t)(hfa == 2) << 15 |
        (uint32_t)(hfa == 3) << 14); // ld1 {v28.(4s|2d),...},[x30]
      o(0x0d00801c | r1 << 5 | (fsize == 8) << 10 | (uint32_t)(hfa != 2) << 13 |
        (uint32_t)(hfa != 3) << 21); // st(hfa) {v28.(s|d),...}[0],[x(r1)]
    }
    // lab2:
    write32le(cur_text_section->data + b2, 0x14000000 | (ind - b2) >> 2);
  }
}

ST_FUNC int gfunc_sret(CType *vt, int variadic, CType *ret, int *align,
                       int *regsize) {
  return 0;
}

ST_FUNC void gfunc_return(CType *func_type) {
  CType *t = func_type;
  unsigned long a;

  arm64_pcs(0, &t, &a, 0);
  switch (a) {
  case -1:
    break;
  case 0:
    if ((func_type->t & VT_BTYPE) == VT_STRUCT) {
      int align, size = type_size(func_type, &align);
      gaddrof();
      gv(RC_R(0));
      arm64_ldrs(0, size);
    } else
      gv(RC_IRET);
    break;
  case 1: {
    CType type = *func_type;
    mk_pointer(&type);
    vset(&type, VT_LOCAL | VT_LVAL, func_vc);
    indir();
    vswap();
    vstore();
    break;
  }
  case 16:
    if ((func_type->t & VT_BTYPE) == VT_STRUCT) {
      uint32_t j, sz, n = arm64_hfa(&vtop->type, &sz);
      gaddrof();
      gv(RC_R(0));
      for (j = 0; j < n; j++)
        o(0x3d400000 | (sz & 16) << 19 | -(sz & 8) << 27 | (sz & 4) << 29 | j |
          j << 10); // ldr ([sdq])(*),[x0,#(j * sz)]
    } else
      gv(RC_FRET);
    break;
  default:
    assert(0);
  }
  vtop--;
}

ST_FUNC void gfunc_epilog(void) {
  if (loc) {
    // 插入从 SP 中减去栈帧大小的指令。
    unsigned char *ptr = cur_text_section->data + arm64_func_sub_sp_offset;
    uint64_t diff = (-loc + 15) & ~15;
    if (!(diff >> 24)) {
      if (diff & 0xfff) // sub sp,sp,#(diff & 0xfff)
        write32le(ptr, 0xd10003ff | (diff & 0xfff) << 10);
      if (diff >> 12) // sub sp,sp,#(diff >> 12),lsl #12
        write32le(ptr + 4, 0xd14003ff | (diff >> 12) << 10);
    } else {
      // 这种情况下我们可能减去的比需要的多，
      // 但总是少于目标值的 17/16。
      int i = 0;
      int j = 0;
      while (diff >> 20) {
        diff = (diff + 0xffff) >> 16;
        ++i;
      }
      while (diff >> 16) {
        diff = (diff + 1) >> 1;
        ++j;
      }
      write32le(ptr, 0xd2800010 | diff << 5 | i << 21);
      // mov x16,#(diff),lsl #(16 * i)
      write32le(ptr + 4, 0xcb3063ff | j << 10);
      // sub sp,sp,x16,lsl #(j)
    }
  }
  o(0x910003bf); // mov sp,x29
  o(0xa8ce7bfd); // ldp x29,x30,[sp],#224

  o(0xd65f03c0); // ret
}

// 生成到标签的前向分支：
ST_FUNC int gjmp(int t) {
  int r = ind;
  if (nocode_wanted)
    return t;
  o(t);
  return r;
}

// 生成到已知地址的分支：
ST_FUNC void gjmp_addr(int a) {
  assert(a - ind + 0x8000000 < 0x10000000);
  o(0x14000000 | ((a - ind) >> 2 & 0x3ffffff));
}

ST_FUNC int gtst(int inv, int t) {
  int bt = vtop->type.t & VT_BTYPE;
  if (bt == VT_LDOUBLE) {
    uint32_t a, b, f = fltr(gv(RC_FLOAT));
    a = get_reg(RC_INT);
    vpushi(0);
    vtop[0].r = a;
    b = get_reg(RC_INT);
    a = intr(a);
    b = intr(b);
    o(0x4e083c00 | a | f << 5);           // mov x(a),v(f).d[0]
    o(0x4e183c00 | b | f << 5);           // mov x(b),v(f).d[1]
    o(0xaa000400 | a | a << 5 | b << 16); // orr x(a),x(a),x(b),lsl #1
    o(0xb4000040 | a | !!inv << 24);      // cbz/cbnz x(a),.+8
    --vtop;
  } else if (bt == VT_FLOAT || bt == VT_DOUBLE) {
    uint32_t a = fltr(gv(RC_FLOAT));
    o(0x1e202008 | a << 5 | (bt != VT_FLOAT) << 22); // fcmp
    o(0x54000040 | !!inv);                           // b.eq/b.ne .+8
  } else {
    uint32_t ll = (bt == VT_PTR || bt == VT_LLONG);
    uint32_t a = intr(gv(RC_INT));
    o(0x34000040 | a | !!inv << 24 | ll << 31); // cbz/cbnz wA,.+8
  }
  --vtop;
  return gjmp(t);
}

static int arm64_iconst(uint64_t *val, SValue *sv) {
  if ((sv->r & (VT_VALMASK | VT_LVAL | VT_SYM)) != VT_CONST)
    return 0;
  if (val) {
    int t = sv->type.t;
    int bt = t & VT_BTYPE;
    *val = ((bt == VT_LLONG || bt == VT_PTR)
                ? sv->c.i
                : (uint32_t)sv->c.i |
                      (t & VT_UNSIGNED ? 0 : -(sv->c.i & 0x80000000)));
  }
  return 1;
}

static int arm64_gen_opic(int op, uint32_t l, int rev, uint64_t val, uint32_t x,
                          uint32_t a) {
  if (op == '-' && !rev) {
    val = -val;
    op = '+';
  }
  val = l ? val : (uint32_t)val;

  switch (op) {

  case '+': {
    uint32_t s = l ? val >> 63 : val >> 31;
    val = s ? -val : val;
    val = l ? val : (uint32_t)val;
    if (!(val & ~(uint64_t)0xfff))
      o(0x11000000 | l << 31 | s << 30 | x | a << 5 | val << 10);
    else if (!(val & ~(uint64_t)0xfff000))
      o(0x11400000 | l << 31 | s << 30 | x | a << 5 | val >> 12 << 10);
    else {
      arm64_movimm(30, val); // 用 x30
      o(0x0b1e0000 | l << 31 | s << 30 | x | a << 5);
    }
    return 1;
  }

  case '-':
    if (!val)
      o(0x4b0003e0 | l << 31 | x | a << 16); // neg
    else if (val == (l ? (uint64_t)-1 : (uint32_t)-1))
      o(0x2a2003e0 | l << 31 | x | a << 16); // mvn
    else {
      arm64_movimm(30, val);                 // 用 x30
      o(0x4b0003c0 | l << 31 | x | a << 16); // sub
    }
    return 1;

  case '^':
    if (val == -1 || (val == 0xffffffff && !l)) {
      o(0x2a2003e0 | l << 31 | x | a << 16); // mvn
      return 1;
    }
    // 顺序执行
  case '&':
  case '|': {
    int e = arm64_encode_bimm64(l ? val : val | val << 32);
    if (e < 0)
      return 0;
    o((op == '&'   ? 0x12000000
       : op == '|' ? 0x32000000
                   : 0x52000000) |
      l << 31 | x | a << 5 | (uint32_t)e << 10);
    return 1;
  }

  case TOK_SAR:
  case TOK_SHL:
  case TOK_SHR: {
    uint32_t n = 32 << l;
    val = val & (n - 1);
    if (rev)
      return 0;
    if (!val)
      assert(0);
    else if (op == TOK_SHL)
      o(0x53000000 | l << 31 | l << 22 | x | a << 5 | (n - val) << 16 |
        (n - 1 - val) << 10); // lsl
    else
      o(0x13000000 | (op == TOK_SHR) << 30 | l << 31 | l << 22 | x | a << 5 |
        val << 16 | (n - 1) << 10); // lsr/asr
    return 1;
  }
  }
  return 0;
}

static void arm64_gen_opil(int op, uint32_t l) {
  uint32_t x, a, b;

  // 对含常量操作数的运算做特殊处理：
  {
    uint64_t val;
    int rev = 1;

    if (arm64_iconst(0, &vtop[0])) {
      vswap();
      rev = 0;
    }
    if (arm64_iconst(&val, &vtop[-1])) {
      gv(RC_INT);
      a = intr(vtop[0].r);
      --vtop;
      x = get_reg(RC_INT);
      ++vtop;
      if (arm64_gen_opic(op, l, rev, val, intr(x), a)) {
        vtop[0].r = x;
        vswap();
        --vtop;
        return;
      }
    }
    if (!rev)
      vswap();
  }

  gv2(RC_INT, RC_INT);
  assert(vtop[-1].r < VT_CONST && vtop[0].r < VT_CONST);
  a = intr(vtop[-1].r);
  b = intr(vtop[0].r);
  vtop -= 2;
  x = get_reg(RC_INT);
  ++vtop;
  vtop[0].r = x;
  x = intr(x);

  switch (op) {
  case '%':
    // 用 x30 存放商：
    o(0x1ac00c00 | l << 31 | 30 | a << 5 | b << 16);                     // sdiv
    o(0x1b008000 | l << 31 | x | (uint32_t)30 << 5 | b << 16 | a << 10); // msub
    break;
  case '&':
    o(0x0a000000 | l << 31 | x | a << 5 | b << 16); // and
    break;
  case '*':
    o(0x1b007c00 | l << 31 | x | a << 5 | b << 16); // mul
    break;
  case '+':
    o(0x0b000000 | l << 31 | x | a << 5 | b << 16); // add
    break;
  case '-':
    o(0x4b000000 | l << 31 | x | a << 5 | b << 16); // sub
    break;
  case '/':
    o(0x1ac00c00 | l << 31 | x | a << 5 | b << 16); // sdiv
    break;
  case '^':
    o(0x4a000000 | l << 31 | x | a << 5 | b << 16); // eor
    break;
  case '|':
    o(0x2a000000 | l << 31 | x | a << 5 | b << 16); // orr
    break;
  case TOK_EQ:
    o(0x6b00001f | l << 31 | a << 5 | b << 16); // cmp
    o(0x1a9f17e0 | x);                          // cset wA,eq
    break;
  case TOK_GE:
    o(0x6b00001f | l << 31 | a << 5 | b << 16); // cmp
    o(0x1a9fb7e0 | x);                          // cset wA,ge
    break;
  case TOK_GT:
    o(0x6b00001f | l << 31 | a << 5 | b << 16); // cmp
    o(0x1a9fd7e0 | x);                          // cset wA,gt
    break;
  case TOK_LE:
    o(0x6b00001f | l << 31 | a << 5 | b << 16); // cmp
    o(0x1a9fc7e0 | x);                          // cset wA,le
    break;
  case TOK_LT:
    o(0x6b00001f | l << 31 | a << 5 | b << 16); // cmp
    o(0x1a9fa7e0 | x);                          // cset wA,lt
    break;
  case TOK_NE:
    o(0x6b00001f | l << 31 | a << 5 | b << 16); // cmp
    o(0x1a9f07e0 | x);                          // cset wA,ne
    break;
  case TOK_SAR:
    o(0x1ac02800 | l << 31 | x | a << 5 | b << 16); // asr
    break;
  case TOK_SHL:
    o(0x1ac02000 | l << 31 | x | a << 5 | b << 16); // lsl
    break;
  case TOK_SHR:
    o(0x1ac02400 | l << 31 | x | a << 5 | b << 16); // lsr
    break;
  case TOK_UDIV:
  case TOK_PDIV:
    o(0x1ac00800 | l << 31 | x | a << 5 | b << 16); // udiv
    break;
  case TOK_UGE:
    o(0x6b00001f | l << 31 | a << 5 | b << 16); // cmp
    o(0x1a9f37e0 | x);                          // cset wA,cs
    break;
  case TOK_UGT:
    o(0x6b00001f | l << 31 | a << 5 | b << 16); // cmp
    o(0x1a9f97e0 | x);                          // cset wA,hi
    break;
  case TOK_ULT:
    o(0x6b00001f | l << 31 | a << 5 | b << 16); // cmp
    o(0x1a9f27e0 | x);                          // cset wA,cc
    break;
  case TOK_ULE:
    o(0x6b00001f | l << 31 | a << 5 | b << 16); // cmp
    o(0x1a9f87e0 | x);                          // cset wA,ls
    break;
  case TOK_UMOD:
    // 用 x30 存放商：
    o(0x1ac00800 | l << 31 | 30 | a << 5 | b << 16);                     // udiv
    o(0x1b008000 | l << 31 | x | (uint32_t)30 << 5 | b << 16 | a << 10); // msub
    break;
  default:
    assert(0);
  }
}

ST_FUNC void gen_opi(int op) { arm64_gen_opil(op, 0); }

ST_FUNC void gen_opl(int op) { arm64_gen_opil(op, 1); }

ST_FUNC void gen_opf(int op) {
  uint32_t x, a, b, dbl;

  if (vtop[0].type.t == VT_LDOUBLE) {
    CType type = vtop[0].type;
    int func = 0;
    int cond = -1;
    switch (op) {
    case '*':
      func = TOK___multf3;
      break;
    case '+':
      func = TOK___addtf3;
      break;
    case '-':
      func = TOK___subtf3;
      break;
    case '/':
      func = TOK___divtf3;
      break;
    case TOK_EQ:
      func = TOK___eqtf2;
      cond = 1;
      break;
    case TOK_NE:
      func = TOK___netf2;
      cond = 0;
      break;
    case TOK_LT:
      func = TOK___lttf2;
      cond = 10;
      break;
    case TOK_GE:
      func = TOK___getf2;
      cond = 11;
      break;
    case TOK_LE:
      func = TOK___letf2;
      cond = 12;
      break;
    case TOK_GT:
      func = TOK___gttf2;
      cond = 13;
      break;
    default:
      assert(0);
      break;
    }
    vpush_global_sym(&func_old_type, func);
    vrott(3);
    gfunc_call(2);
    vpushi(0);
    vtop->r = cond < 0 ? REG_FRET : REG_IRET;
    if (cond < 0)
      vtop->type = type;
    else {
      o(0x7100001f);                        // cmp w0,#0
      o(0x1a9f07e0 | (uint32_t)cond << 12); // cset w0,(cond)
    }
    return;
  }

  dbl = vtop[0].type.t != VT_FLOAT;
  gv2(RC_FLOAT, RC_FLOAT);
  assert(vtop[-1].r < VT_CONST && vtop[0].r < VT_CONST);
  a = fltr(vtop[-1].r);
  b = fltr(vtop[0].r);
  vtop -= 2;
  switch (op) {
  case TOK_EQ:
  case TOK_NE:
  case TOK_LT:
  case TOK_GE:
  case TOK_LE:
  case TOK_GT:
    x = get_reg(RC_INT);
    ++vtop;
    vtop[0].r = x;
    x = intr(x);
    break;
  default:
    x = get_reg(RC_FLOAT);
    ++vtop;
    vtop[0].r = x;
    x = fltr(x);
    break;
  }

  switch (op) {
  case '*':
    o(0x1e200800 | dbl << 22 | x | a << 5 | b << 16); // fmul
    break;
  case '+':
    o(0x1e202800 | dbl << 22 | x | a << 5 | b << 16); // fadd
    break;
  case '-':
    o(0x1e203800 | dbl << 22 | x | a << 5 | b << 16); // fsub
    break;
  case '/':
    o(0x1e201800 | dbl << 22 | x | a << 5 | b << 16); // fdiv
    break;
  case TOK_EQ:
    o(0x1e202000 | dbl << 22 | a << 5 | b << 16); // fcmp
    o(0x1a9f17e0 | x);                            // cset w(x),eq
    break;
  case TOK_GE:
    o(0x1e202000 | dbl << 22 | a << 5 | b << 16); // fcmp
    o(0x1a9fb7e0 | x);                            // cset w(x),ge
    break;
  case TOK_GT:
    o(0x1e202000 | dbl << 22 | a << 5 | b << 16); // fcmp
    o(0x1a9fd7e0 | x);                            // cset w(x),gt
    break;
  case TOK_LE:
    o(0x1e202000 | dbl << 22 | a << 5 | b << 16); // fcmp
    o(0x1a9f87e0 | x);                            // cset w(x),ls
    break;
  case TOK_LT:
    o(0x1e202000 | dbl << 22 | a << 5 | b << 16); // fcmp
    o(0x1a9f57e0 | x);                            // cset w(x),mi
    break;
  case TOK_NE:
    o(0x1e202000 | dbl << 22 | a << 5 | b << 16); // fcmp
    o(0x1a9f07e0 | x);                            // cset w(x),ne
    break;
  default:
    assert(0);
  }
}

// 生成从 32 位到 64 位的符号扩展：
ST_FUNC void gen_cvt_sxtw(void) {
  uint32_t r = intr(gv(RC_INT));
  o(0x93407c00 | r | r << 5); // sxtw x(r),w(r)
}

ST_FUNC void gen_cvt_itof(int t) {
  if (t == VT_LDOUBLE) {
    int f = vtop->type.t;
    int func = (f & VT_BTYPE) == VT_LLONG
                   ? (f & VT_UNSIGNED ? TOK___floatunditf : TOK___floatditf)
                   : (f & VT_UNSIGNED ? TOK___floatunsitf : TOK___floatsitf);
    vpush_global_sym(&func_old_type, func);
    vrott(2);
    gfunc_call(1);
    vpushi(0);
    vtop->type.t = t;
    vtop->r = REG_FRET;
    return;
  } else {
    int d, n = intr(gv(RC_INT));
    int s = !(vtop->type.t & VT_UNSIGNED);
    uint32_t l = ((vtop->type.t & VT_BTYPE) == VT_LLONG);
    --vtop;
    d = get_reg(RC_FLOAT);
    ++vtop;
    vtop[0].r = d;
    o(0x1e220000 | (uint32_t)!s << 16 | (uint32_t)(t != VT_FLOAT) << 22 |
      fltr(d) | l << 31 | n << 5); // [us]cvtf [sd](d),[wx](n)
  }
}

ST_FUNC void gen_cvt_ftoi(int t) {
  if ((vtop->type.t & VT_BTYPE) == VT_LDOUBLE) {
    int func = (t & VT_BTYPE) == VT_LLONG
                   ? (t & VT_UNSIGNED ? TOK___fixunstfdi : TOK___fixtfdi)
                   : (t & VT_UNSIGNED ? TOK___fixunstfsi : TOK___fixtfsi);
    vpush_global_sym(&func_old_type, func);
    vrott(2);
    gfunc_call(1);
    vpushi(0);
    vtop->type.t = t;
    vtop->r = REG_IRET;
    return;
  } else {
    int d, n = fltr(gv(RC_FLOAT));
    uint32_t l = ((vtop->type.t & VT_BTYPE) != VT_FLOAT);
    --vtop;
    d = get_reg(RC_INT);
    ++vtop;
    vtop[0].r = d;
    o(0x1e380000 | (uint32_t)!!(t & VT_UNSIGNED) << 16 |
      (uint32_t)((t & VT_BTYPE) == VT_LLONG) << 31 | intr(d) | l << 22 |
      n << 5); // fcvtz[su] [wx](d),[sd](n)
  }
}

ST_FUNC void gen_cvt_ftof(int t) {
  int f = vtop[0].type.t;
  assert(t == VT_FLOAT || t == VT_DOUBLE || t == VT_LDOUBLE);
  assert(f == VT_FLOAT || f == VT_DOUBLE || f == VT_LDOUBLE);
  if (t == f)
    return;

  if (t == VT_LDOUBLE || f == VT_LDOUBLE) {
    int func = (t == VT_LDOUBLE)
                   ? (f == VT_FLOAT ? TOK___extendsftf2 : TOK___extenddftf2)
                   : (t == VT_FLOAT ? TOK___trunctfsf2 : TOK___trunctfdf2);
    vpush_global_sym(&func_old_type, func);
    vrott(2);
    gfunc_call(1);
    vpushi(0);
    vtop->type.t = t;
    vtop->r = REG_FRET;
  } else {
    int x, a;
    gv(RC_FLOAT);
    assert(vtop[0].r < VT_CONST);
    a = fltr(vtop[0].r);
    --vtop;
    x = get_reg(RC_FLOAT);
    ++vtop;
    vtop[0].r = x;
    x = fltr(x);

    if (f == VT_FLOAT)
      o(0x1e22c000 | x | a << 5); // fcvt d(x),s(a)
    else
      o(0x1e624000 | x | a << 5); // fcvt s(x),d(a)
  }
}

ST_FUNC void ggoto(void) {
  arm64_gen_bl_or_b(1);
  --vtop;
}

ST_FUNC void gen_clear_cache(void) {
  uint32_t beg, end, dsz, isz, p, lab1, b1;
  gv2(RC_INT, RC_INT);
  vpushi(0);
  vtop->r = get_reg(RC_INT);
  vpushi(0);
  vtop->r = get_reg(RC_INT);
  vpushi(0);
  vtop->r = get_reg(RC_INT);
  beg = intr(vtop[-4].r); // x0
  end = intr(vtop[-3].r); // x1
  dsz = intr(vtop[-2].r); // x2
  isz = intr(vtop[-1].r); // x3
  p = intr(vtop[0].r);    // x4
  vtop -= 5;

  o(0xd53b0020 | isz);                      // mrs x(isz),ctr_el0
  o(0x52800080 | p);                        // mov w(p),#4
  o(0x53104c00 | dsz | isz << 5);           // ubfx w(dsz),w(isz),#16,#4
  o(0x1ac02000 | dsz | p << 5 | dsz << 16); // lsl w(dsz),w(p),w(dsz)
  o(0x12000c00 | isz | isz << 5);           // and w(isz),w(isz),#15
  o(0x1ac02000 | isz | p << 5 | isz << 16); // lsl w(isz),w(p),w(isz)
  o(0x51000400 | p | dsz << 5);             // sub w(p),w(dsz),#1
  o(0x8a240004 | p | beg << 5 | p << 16);   // bic x(p),x(beg),x(p)
  b1 = ind;
  o(0x14000000); // b
  lab1 = ind;
  o(0xd50b7b20 | p);                      // dc cvau,x(p)
  o(0x8b000000 | p | p << 5 | dsz << 16); // add x(p),x(p),x(dsz)
  write32le(cur_text_section->data + b1, 0x14000000 | (ind - b1) >> 2);
  o(0xeb00001f | p << 5 | end << 16);             // cmp x(p),x(end)
  o(0x54ffffa3 | ((lab1 - ind) << 3 & 0xffffe0)); // b.cc lab1
  o(0xd5033b9f);                                  // dsb ish
  o(0x51000400 | p | isz << 5);                   // sub w(p),w(isz),#1
  o(0x8a240004 | p | beg << 5 | p << 16);         // bic x(p),x(beg),x(p)
  b1 = ind;
  o(0x14000000); // b
  lab1 = ind;
  o(0xd50b7520 | p);                      // ic ivau,x(p)
  o(0x8b000000 | p | p << 5 | isz << 16); // add x(p),x(p),x(isz)
  write32le(cur_text_section->data + b1, 0x14000000 | (ind - b1) >> 2);
  o(0xeb00001f | p << 5 | end << 16);             // cmp x(p),x(end)
  o(0x54ffffa3 | ((lab1 - ind) << 3 & 0xffffe0)); // b.cc lab1
  o(0xd5033b9f);                                  // dsb ish
  o(0xd5033fdf);                                  // isb
}

ST_FUNC void gen_vla_sp_save(int addr) {
  uint32_t r = intr(get_reg(RC_INT));
  o(0x910003e0 | r); // mov x(r),sp
  arm64_strx(3, r, 29, addr);
}

ST_FUNC void gen_vla_sp_restore(int addr) {
  // 使用 x30，因为调用这个函数时 x0 中可能有一个
  // 尚未失效的返回值，而值栈上没有什么能阻止
  // get_reg 返回 x0。
  uint32_t r = 30;
  arm64_ldrx(0, 3, r, 29, addr);
  o(0x9100001f | r << 5); // mov sp,x(r)
}

ST_FUNC void gen_vla_alloc(CType *type, int align) {
  uint32_t r = intr(gv(RC_INT));
  o(0x91003c00 | r | r << 5); // add x(r),x(r),#15
  o(0x927cec00 | r | r << 5); // bic x(r),x(r),#15
  o(0xcb2063ff | r << 16);    // sub sp,sp,x(r)
  vpop();
}

/* A64 代码生成器结束 */
/*************************************************************/
#endif
/*************************************************************/
