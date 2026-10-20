#include <stdint.h>

/* Linux/AArch64 C ABI 探针：实现 YH 调用的 c_*，并反向调用 YH 导出函数。
 * 结构体布局必须与 llvm-linux-arm64-abi.yh 的源布局一致。 */
typedef struct { double a, b; } H2;
typedef struct { double a, b, c; } H3;
typedef struct { uint64_t a, b; } P16;
typedef struct { uint64_t a, b, c; } W24;

extern H2 yh_h2(H2);
extern H3 yh_h3(H3);
extern P16 yh_p16(P16);
extern W24 yh_w24(W24);
extern H2 yh_adjust_hfa(H2);
extern H2 yh_apply_hfa(H2 (*callback)(H2), H2);
extern H2 yh_call_returned_hfa(H2);

/* c_i8：窄有符号参数与返回值。 */
int8_t c_i8(int8_t value) { return value; }

/* c_u16：窄无符号参数与返回值。 */
uint16_t c_u16(uint16_t value) { return value; }

/* c_bool：AAPCS64 _Bool 参数与返回值。 */
_Bool c_bool(_Bool value) { return value; }

/* c_mixed：整数与浮点交错，GPR 与 v 寄存器各自计数。 */
int64_t c_mixed(int32_t a, double b, int64_t c, float d, uint64_t e,
                int32_t f, double g, uint32_t h) {
    return (int64_t)a + (int64_t)(b * 10.0) + c + (int64_t)(d * 100.0f)
        + (int64_t)e + f + (int64_t)(g * 1000.0) + h;
}

/* c_h2：HFA2 直接按值往返。 */
H2 c_h2(H2 value) { return value; }

/* c_h3：HFA3 直接按值往返。 */
H3 c_h3(H3 value) { return value; }

/* c_p16：两个整数组件的 16 字节聚合。 */
P16 c_p16(P16 value) { return value; }

/* c_w24：24 字节聚合经 sret/间接参数。 */
W24 c_w24(W24 value) { value.b += 3; return value; }

/* c_adjust_hfa：修改 HFA 两个成员。 */
H2 c_adjust_hfa(H2 value) {
    value.a += 10.0;
    value.b += 20.0;
    return value;
}

/* c_apply_hfa：调用 YH 传入的 HFA 函数值。 */
H2 c_apply_hfa(H2 (*callback)(H2), H2 value) { return callback(value); }

/* c_choose_hfa：把 C 函数作为 HFA 函数值返回给 YH。 */
H2 (*c_choose_hfa(void))(H2) { return c_adjust_hfa; }

/* c_test：C→YH 方向检查，返回 0 表示全部通过。 */
int c_test(void) {
    H2 h = {1.5, 2.5};
    H2 rh = yh_h2(h);
    if (rh.a != 1.5 || rh.b != 2.5) return 1;

    H3 h3 = {1.0, 2.0, 3.0};
    H3 rh3 = yh_h3(h3);
    if (rh3.a != 1.0 || rh3.b != 2.0 || rh3.c != 3.0) return 2;

    P16 p = {11, 22};
    P16 rp = yh_p16(p);
    if (rp.a != 11 || rp.b != 22) return 3;

    W24 w = {1, 2, 3};
    W24 rw = yh_w24(w);
    if (rw.a != 1 || rw.b != 5 || rw.c != 3) return 4;

    H2 adjusted = yh_adjust_hfa(h);
    if (adjusted.a != 11.5 || adjusted.b != 22.5) return 5;

    H2 applied = yh_apply_hfa(yh_adjust_hfa, h);
    if (applied.a != 11.5 || applied.b != 22.5) return 6;

    H2 returned = yh_call_returned_hfa(h);
    if (returned.a != 11.5 || returned.b != 22.5) return 7;
    return 0;
}
