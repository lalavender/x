#include <stdint.h>

extern double yh_weigh_mixed(float, int32_t, double, int32_t, float,
                            int32_t, double, int32_t, double, int32_t);
extern double yh_weigh_stack(int64_t, double, int64_t, int64_t, int64_t,
                            int64_t, int64_t, int64_t, int64_t, int64_t,
                            float, int64_t, double, int64_t);

// 用非交换的加权结果核对十个实参各自对应的整数或浮点寄存器。
double c_weigh_mixed(float a, int32_t b, double c, int32_t d, float e,
                     int32_t f, double g, int32_t h, double i, int32_t j) {
    return (double)a + (double)b * 2.0 + c * 3.0 + (double)d * 4.0
        + (double)e * 5.0 + (double)f * 6.0 + g * 7.0 + (double)h * 8.0
        + i * 9.0 + (double)j * 10.0;
}

// 三个整数栈参数之间穿插浮点寄存器参数，检测错误的连续后缀假设。
double c_weigh_stack(int64_t a, double b, int64_t c, int64_t d, int64_t e,
                     int64_t f, int64_t g, int64_t h, int64_t i, int64_t j,
                     float k, int64_t l, double m, int64_t n) {
    return (double)a + b * 2.0 + (double)c * 3.0 + (double)d * 4.0
        + (double)e * 5.0 + (double)f * 6.0 + (double)g * 7.0
        + (double)h * 8.0 + (double)i * 9.0 + (double)j * 10.0
        + (double)k * 11.0 + (double)l * 12.0 + m * 13.0 + (double)n * 14.0;
}

// 独立的 C 调用方核对 yh 被调入口，期望为 1²+…+10² 与 1²+…+14²。
int32_t c_check_yh_mixed(void) {
    if (yh_weigh_mixed(1.0f, 2, 3.0, 4, 5.0f, 6, 7.0, 8, 9.0, 10) != 385.0)
        return 1;
    if (yh_weigh_stack(1, 2.0, 3, 4, 5, 6, 7, 8, 9, 10,
                       11.0f, 12, 13.0, 14) != 1015.0)
        return 2;
    return 0;
}
