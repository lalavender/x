#include <stdbool.h>
#include <stdint.h>

extern int64_t yh_scalar(bool, int8_t, uint8_t, int16_t, uint16_t, int32_t,
                         int64_t, uint8_t *, float, double);
extern int64_t yh_call_c_scalar(bool, int8_t, uint8_t, int16_t, uint16_t,
                                int32_t, int64_t, uint8_t *, float, double);
extern int8_t yh_narrow10(int8_t, int8_t, int8_t, int8_t, int8_t, int8_t,
                          int8_t, int8_t, int8_t, int8_t);
extern double yh_fp9(double, double, double, double, double, double, double,
                     double, double, int64_t);
extern int32_t yh_apply(int32_t (*)(int32_t), int32_t);
extern int32_t yh_call_c_callback(int32_t);
extern uint8_t *yh_pointer(uint8_t *);

// c_scalar：按源声明计算同一结果，验证 YH 对 C 的标量调用约定。
int64_t c_scalar(bool enabled, int8_t signed8, uint8_t unsigned8,
                 int16_t signed16, uint16_t unsigned16, int32_t signed32,
                 int64_t wide, uint8_t *data, float single, double wide_float) {
    (void)data;
    return (enabled ? 1 : 0) + signed8 + unsigned8 + signed16 + unsigned16
        + signed32 + wide + (int64_t)single + (int64_t)wide_float;
}

// c_increment：作为 C 提供的回调，供 YH 通过函数指针间接调用。
static int32_t c_increment(int32_t value) {
    return value + 7;
}

// c_apply：由 YH 调用后，C 再通过函数指针调用 YH 导出的 C ABI 函数。
int32_t c_apply(int32_t (*callback)(int32_t), int32_t value) {
    return callback(value);
}

// c_test：核对固定参数、寄存器溢出、指针和 C/YH 双向回调的真实运行结果。
int c_test(void) {
    uint8_t byte = 19;
    int64_t expected = 1 - 3 + 200 - 500 + 60000 - 12345
        + INT64_C(123456789) + 1 - 2;
    if (yh_scalar(true, -3, 200, -500, 60000, -12345,
                  INT64_C(123456789), &byte, 1.5f, -2.25) != expected) return 1;
    if (yh_call_c_scalar(true, -3, 200, -500, 60000, -12345,
                         INT64_C(123456789), &byte, 1.5f, -2.25) != expected) return 2;
    if (yh_narrow10(1, 2, 3, 4, 5, 6, 7, 8, 9, -77) != -77) return 3;
    if (yh_fp9(1, 2, 3, 4, 5, 6, 7, 8, 9, -2) != 7.0) return 4;
    if (yh_apply(c_increment, 35) != 42) return 5;
    if (yh_call_c_callback(35) != 42) return 6;
    if (yh_pointer(&byte) != &byte) return 7;
    return 0;
}
