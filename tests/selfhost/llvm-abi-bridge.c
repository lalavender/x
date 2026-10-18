#include <stdint.h>

// yh_run_probe：进入 yh 编译的 C ABI 测试入口。
extern int32_t yh_run_probe(void);
// yh_i8：C 侧调用 yh 的有符号 8 位导出函数。
extern int8_t yh_i8(int8_t value);
// yh_u8：C 侧调用 yh 的无符号 8 位导出函数。
extern uint8_t yh_u8(uint8_t value);
// yh_i16：C 侧调用 yh 的有符号 16 位导出函数。
extern int16_t yh_i16(int16_t value);
// yh_u16：C 侧调用 yh 的无符号 16 位导出函数。
extern uint16_t yh_u16(uint16_t value);
// yh_bool：C 调用 YH 的 _Bool 签名，核对 i1 zeroext 的双向边界。
extern _Bool yh_bool(_Bool value);
// yh_bool_noncanonical：测试 YH 的非规范 bool 字节转为 C _Bool。
extern _Bool yh_bool_noncanonical(void);
// yh_f32：C 侧调用 yh 的单精度导出函数。
extern float yh_f32(float value);
// yh_f64：C 侧调用 yh 的双精度导出函数。
extern double yh_f64(double value);
// yh_ptr：C 侧调用 yh 的 opaque 指针导出函数。
extern uint8_t *yh_ptr(uint8_t *value);
// yh_mixed：C 侧调用 yh 的交错整浮多参数导出函数。
extern int64_t yh_mixed(int32_t, double, int64_t, float, uint64_t, int32_t,
                        double, uint32_t);
// yh_many：C 侧调用 yh 的八个整数参数导出函数，覆盖栈上传递。
extern int64_t yh_many(int64_t, int64_t, int64_t, int64_t, int64_t, int64_t,
                       int64_t, int64_t);

// c_i8：由 LLVM 生成的 yh 调用，核对 C 有符号 8 位参数与返回值。
int8_t c_i8(int8_t value) { return value; }

// c_u8：由 LLVM 生成的 yh 调用，核对 C 无符号 8 位参数与返回值。
uint8_t c_u8(uint8_t value) { return value; }

// c_i16：由 LLVM 生成的 yh 调用，核对 C 有符号 16 位参数与返回值。
int16_t c_i16(int16_t value) { return value; }

// c_u16：由 LLVM 生成的 yh 调用，核对 C 无符号 16 位参数与返回值。
uint16_t c_u16(uint16_t value) { return value; }

// c_bool：核对 C _Bool 的参数与返回值使用 i1 zeroext ABI。
_Bool c_bool(_Bool value) { return value; }

// c_f32：核对 C float 形参与返回值。
float c_f32(float value) { return value; }

// c_f64：核对 C double 形参与返回值。
double c_f64(double value) { return value; }

// c_ptr：核对 C 指针实参与返回值没有被当作整数或 yh 闭包处理。
uint8_t *c_ptr(uint8_t *value) { return value; }

// c_mixed：交错消费 GPR/SSE 参数并返回独立加权值，覆盖第六参数之后的位置。
int64_t c_mixed(int32_t a, double b, int64_t c, float d, uint64_t e,
                int32_t f, double g, uint32_t h) {
    return (int64_t)a + (int64_t)(b * 10.0) + c + (int64_t)(d * 100.0f)
        + (int64_t)e + f + (int64_t)(g * 1000.0) + h;
}

// c_many：八个整数参数使后两个参数落在调用栈上，返回和供 yh 调用方核对。
int64_t c_many(int64_t a, int64_t b, int64_t c, int64_t d, int64_t e,
               int64_t f, int64_t g, int64_t h) {
    return a + b + c + d + e + f + g + h;
}

// main：先让 yh 调 C，再由 C 调回 yh，检查同一签名的双向调用结果。
int main(void) {
    if (yh_run_probe() != 0) return 1;
    if (yh_i8(-123) != -123 || yh_u8(250) != 250) return 2;
    if (yh_i16(-30001) != -30001 || yh_u16(60001) != 60001) return 3;
    if (yh_bool(0) != 0 || yh_bool(1) != 1) return 8;
    if (yh_bool_noncanonical() != 1) return 9;
    if (yh_f32(1.5f) != 1.5f || yh_f64(-9.25) != -9.25) return 4;
    uint8_t byte = 37;
    if (yh_ptr(&byte) != &byte) return 5;
    if (yh_mixed(1, 2.0, 3, 4.0f, 5, 6, 7.0, 8) != 7443) return 6;
    if (yh_many(1, 2, 3, 4, 5, 6, 7, 8) != 36) return 7;
    return 0;
}
