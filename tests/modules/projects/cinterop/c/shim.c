#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

// CPoint 与 yh extern struct 共享字段偏移和总尺寸。
typedef struct CPoint {
    int32_t x;
    int32_t y;
} CPoint;

extern int32_t yh_add(int32_t x, int32_t y);
extern int32_t yh_narrow(uint8_t a, int16_t b, bool c);
extern int32_t yh_sum9(int32_t a, int32_t b, int32_t c, int32_t d,
                       int32_t e, int32_t f, int32_t g, int32_t h, int32_t i);
extern int32_t cdep_round(double value);

typedef int32_t (*yh_callback)(int32_t);

// C 侧通过函数指针回调由 yh 按 C ABI 导出的函数。
int32_t c_apply(yh_callback callback, int32_t value) {
    return callback(value);
}

// 九个固定参数验证 C ABI 的寄存器与栈参数往返。
int32_t c_sum9(int32_t a, int32_t b, int32_t c, int32_t d, int32_t e,
               int32_t f, int32_t g, int32_t h, int32_t i) {
    return a + b + c + d + e + f + g + h + i;
}

// 混合 f32/f64 参数并返回 f64，验证浮点寄存器分类。
double c_float_mix(float a, double b, float c) {
    return (double)a + b + (double)c;
}

// 验证 bool、uint8_t 与 int16_t 的 C 参数宽度和扩展规则。
int32_t c_narrow(uint8_t a, int16_t b, bool c) {
    return (int32_t)a + (int32_t)b + (c ? 1 : 0);
}

// 从 C 调用 yh 导出的窄标量函数。
int32_t c_call_yh_narrow(void) {
    return yh_narrow(250, -3, true);
}

// 从 C 调用 yh 导出的九参数函数。
int32_t c_call_yh_sum9(void) {
    return yh_sum9(1, 2, 3, 4, 5, 6, 7, 8, 9);
}

// 返回共享结构体的大小，供 yh sizeof 结果交叉核对。
int32_t c_point_size(void) {
    return (int32_t)sizeof(CPoint);
}

// 返回共享结构体第二字段偏移，供 yh 字段布局交叉核对。
int32_t c_point_y_offset(void) {
    return (int32_t)offsetof(CPoint, y);
}

// 组合依赖项目 C 代码与 yh 导出的加法函数，返回调用结果。
int32_t c_roundtrip(void) {
    return cdep_round((double)yh_add(19, 23));
}

// 给 yh 分配的 CPoint 写入已知字段值，验证双方字段布局一致。
void c_fill_point(CPoint *point) {
    point->x = 20;
    point->y = 22;
}
