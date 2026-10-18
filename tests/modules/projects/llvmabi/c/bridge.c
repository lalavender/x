#include <stdint.h>

struct CPair { int32_t left; int32_t right; };
struct CMixed { double value; int32_t tag; };
struct CWide { int64_t first; int64_t second; int64_t third; };
typedef int32_t (*CIntCallback)(int32_t);
typedef struct CPair (*CPairCallback)(struct CPair);

// yh_i8：由 C 侧调用跨模块导出的 yh 有符号 8 位函数。
extern int8_t yh_i8(int8_t value);
// yh_u8：由 C 侧调用跨模块导出的 yh 无符号 8 位函数。
extern uint8_t yh_u8(uint8_t value);
// yh_i16：由 C 侧调用跨模块导出的 yh 有符号 16 位函数。
extern int16_t yh_i16(int16_t value);
// yh_u16：由 C 侧调用跨模块导出的 yh 无符号 16 位函数。
extern uint16_t yh_u16(uint16_t value);
// yh_f32：由 C 侧调用跨模块导出的 yh float 函数。
extern float yh_f32(float value);
// yh_f64：由 C 侧调用跨模块导出的 yh double 函数。
extern double yh_f64(double value);
// yh_ptr：由 C 侧调用跨模块导出的 yh opaque 指针函数。
extern uint8_t *yh_ptr(uint8_t *value);
// yh_mixed：由 C 侧调用跨模块导出的八参数交错整数/浮点函数。
extern int64_t yh_mixed(int32_t, double, int64_t, float, uint64_t, int32_t,
                        double, uint32_t);
// yh_many：由 C 侧调用跨模块导出的八个整数参数函数。
extern int64_t yh_many(int64_t, int64_t, int64_t, int64_t, int64_t, int64_t,
                       int64_t, int64_t);
// yh_cpair：C 侧调用 yh 导出的两整数聚合函数。
extern struct CPair yh_cpair(struct CPair value);
// yh_cmixed：C 侧调用 yh 导出的 SSE+INTEGER 聚合函数。
extern struct CMixed yh_cmixed(struct CMixed value);
// yh_cwide：C 侧调用 yh 导出的 MEMORY 聚合函数。
extern struct CWide yh_cwide(struct CWide value);

// c_i8：返回有符号窄值，供 yh 调用方校验符号扩展边界。
int8_t c_i8(int8_t value) { return value; }
// c_u8：返回无符号窄值，供 yh 调用方校验零扩展边界。
uint8_t c_u8(uint8_t value) { return value; }
// c_i16：返回有符号 16 位值。
int16_t c_i16(int16_t value) { return value; }
// c_u16：返回无符号 16 位值。
uint16_t c_u16(uint16_t value) { return value; }
// c_f32：返回 C float 参数，核对 SSE 标量类别。
float c_f32(float value) { return value; }
// c_f64：返回 C double 参数，核对 SSE 标量类别。
double c_f64(double value) { return value; }
// c_ptr：原样返回传入的 C 指针，核对指针寄存器类别。
uint8_t *c_ptr(uint8_t *value) { return value; }

// c_mixed：交错读取 GPR/SSE 参数并计算独立加权和，检测参数顺序与类别。
int64_t c_mixed(int32_t a, double b, int64_t c, float d, uint64_t e,
                int32_t f, double g, uint32_t h) {
    return (int64_t)a + (int64_t)(b * 10.0) + c + (int64_t)(d * 100.0f)
        + (int64_t)e + f + (int64_t)(g * 1000.0) + h;
}

// c_many：求和八个整数实参，末尾两个参数应从 SysV 调用栈读取。
int64_t c_many(int64_t a, int64_t b, int64_t c, int64_t d, int64_t e,
               int64_t f, int64_t g, int64_t h) {
    return a + b + c + d + e + f + g + h;
}

// c_pair：修改 CPair 第二字段，验证两个 INTEGER 八字节的真实互调。
struct CPair c_pair(struct CPair value) { value.right += 5; return value; }

// c_mixed_struct：修改浮点字段，验证 SSE+INTEGER 分片。
struct CMixed c_mixed_struct(struct CMixed value) { value.value += 2.0; return value; }

// c_wide_struct：修改第三字段，验证 MEMORY/byval 与隐藏 sret。
struct CWide c_wide_struct(struct CWide value) { value.third += 5; return value; }

// c_check_yh：从 C 反向调用 yh C ABI 定义，返回首个失败类别编号。
int32_t c_check_yh(void) {
    if (yh_i8(-123) != -123 || yh_u8(250) != 250) return 1;
    if (yh_i16(-30001) != -30001 || yh_u16(60001) != 60001) return 2;
    if (yh_f32(1.5f) != 1.5f || yh_f64(-9.25) != -9.25) return 3;
    uint8_t byte = 37;
    if (yh_ptr(&byte) != &byte) return 4;
    if (yh_mixed(1, 2.0, 3, 4.0f, 5, 6, 7.0, 8) != 7443) return 5;
    if (yh_many(1, 2, 3, 4, 5, 6, 7, 8) != 36) return 6;
    struct CPair pair = yh_cpair((struct CPair){17, -4});
    if (pair.left != 17 || pair.right != -1) return 7;
    struct CMixed mixed = yh_cmixed((struct CMixed){2.5, 7});
    if (mixed.value != 2.5 || mixed.tag != 7) return 8;
    struct CWide wide = yh_cwide((struct CWide){11, 22, 33});
    if (wide.first != 11 || wide.second != 22 || wide.third != 38) return 9;
    return 0;
}

// c_apply_callback：从 C 进入 yh 回调，检查函数值的签名按 C ABI 保留。
int32_t c_apply_callback(CIntCallback callback, int32_t value) {
    return callback(value);
}

// c_double：作为 C 返回的函数地址，供 YH 通过间接 C 调用。
static int32_t c_double(int32_t value) { return value * 2; }

// c_choose_callback：返回一个具有固定 C ABI 签名的函数指针。
CIntCallback c_choose_callback(void) { return c_double; }

// c_apply_pair_callback：通过 C 函数指针传入并返回 SysV INTEGER 聚合值。
struct CPair c_apply_pair_callback(CPairCallback callback, struct CPair value) {
    return callback(value);
}

// c_pair_adjust：作为 C 返回的聚合回调，检查间接调用的参数和返回分类。
static struct CPair c_pair_adjust(struct CPair value) {
    value.left += 4;
    value.right -= 3;
    return value;
}

// c_choose_pair_callback：返回带聚合参数与返回值的 C 函数指针。
CPairCallback c_choose_pair_callback(void) { return c_pair_adjust; }

// c_returns：故意正常返回，跨模块调用点必须在其后执行 trap。
void c_returns(void) {}
