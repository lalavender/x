/* 独立 C 编译器决定所有传参和返回规则，避免 yh 两侧共享错误约定。 */
typedef long long I64;
typedef unsigned int U32;
typedef struct { unsigned char a, b, c; } Tiny3;
typedef struct { unsigned char a; } Tiny1;
typedef struct { int a, b; } Pair;
typedef struct { I64 a, b; } Two;
typedef struct { int a, b, c; } Three;
typedef struct { I64 a, b, c; } Wide;
typedef struct { double a, b; } Float2;
typedef struct { Float2 pair; double c; } Float3;
typedef struct { float values[4]; } Float4;
typedef union { I64 integer; double floating; } Bits;
typedef union { double scalar; double values[2]; } FloatUnion;
typedef Pair (*Callback)(Pair);
typedef struct { Callback callback; } CallbackBox;

/* 导入 yh 的 C ABI 入口，C 测试同时检查调用方对象未被形参写入。 */
extern Tiny3 yh_tiny(Tiny3);
extern Tiny1 yh_tiny_one(Tiny1);
extern Pair yh_pair(Pair);
extern Pair yh_div(int, int);
extern Two yh_two(Two);
extern Three yh_three(Three);
extern Wide yh_wide(Wide);
extern Float3 yh_float(Float3);
extern Float4 yh_four(Float4);
extern Bits yh_bits(Bits);
extern FloatUnion yh_float_union(FloatUnion);
extern double yh_fp_stack(float, float, float, float, float, float, float, float,
                          float, double, int);
extern signed char yh_i8_args(signed char, signed char, signed char, signed char,
                             signed char, signed char, signed char, signed char,
                             signed char, signed char);
extern signed char yh_i8_call(signed char, signed char, signed char, signed char,
                             signed char, signed char, signed char, signed char,
                             signed char, signed char);
extern double yh_hfa_stack(double, double, double, double, double, double,
                          double, Float3, double, I64);
extern I64 yh_gpr_stack(I64, I64, I64, I64, I64, I64, I64, Two, short, double);
extern I64 yh_narrow(I64, I64, I64, I64, I64, I64, I64, I64,
                     signed char, unsigned char, short, unsigned short, int, U32);
extern Callback yh_choose(void);
extern Pair yh_box(CallbackBox, Pair);

/* C 被调用方与 yh 入口做相同字段变化，分别验证两种生成方向。 */
Tiny3 c_tiny(Tiny3 v) { v.b += 2; return v; }
Tiny1 c_tiny_one(Tiny1 v) { v.a += 1; return v; }
Pair c_pair(Pair v) { v.b += 3; return v; }
Two c_two(Two v) { v.b += 4; return v; }
Three c_three(Three v) { v.c += 5; return v; }
Wide c_wide(Wide v) { v.c += 6; return v; }
Float3 c_float(Float3 v) { v.c += 7; return v; }
Float4 c_four(Float4 v) { v.values[2] += 8; return v; }
Float4 c_make_four(void) { Float4 v = {{1, 2, 3, 4}}; return v; }
Bits c_bits(Bits v) { v.integer += 9; return v; }
FloatUnion c_float_union(FloatUnion v) { v.values[1] += 2; return v; }
double c_fp_stack(float a, float b, float c, float d, float e, float f, float g,
                  float h, float i, double tail, int mark) { return i+tail+mark; }
signed char c_i8_args(signed char a, signed char b, signed char c, signed char d,
                      signed char e, signed char f, signed char g, signed char h,
                      signed char i, signed char j) { return j; }
double c_hfa_stack(double a, double b, double c, double d, double e, double f,
                   double g, Float3 v, double tail, I64 k) {
    return a+b+c+d+e+f+g+v.pair.a+v.pair.b+v.c+tail+k;
}
I64 c_gpr_stack(I64 a, I64 b, I64 c, I64 d, I64 e, I64 f, I64 g,
                Two v, short tail, double fp) {
    return a+b+c+d+e+f+g+v.a+v.b+tail+(I64)fp;
}
I64 c_narrow(I64 a, I64 b, I64 c, I64 d, I64 e, I64 f, I64 g, I64 h,
             signed char i, unsigned char j, short k, unsigned short l,
             int m, U32 n) { return a+b+c+d+e+f+g+h+i+j+k+l+m+n; }
Callback c_choose(void) { return c_pair; }
Pair c_apply(Callback callback, Pair v) { return callback(v); }
Pair c_box(CallbackBox box, Pair v) { return box.callback(v); }

/* 检查每个字段，失败码对应具体 ABI 类别。 */
int c_check(void) {
    Tiny3 t = yh_tiny((Tiny3){11, 22, 33});
    if (t.a != 11 || t.b != 24 || t.c != 33) return 1;
    Pair p = yh_pair((Pair){17, -4});
    if (p.a != 17 || p.b != -1) return 2;
    Two s = yh_two((Two){10000000001LL, -20000000002LL});
    if (s.a != 10000000001LL || s.b != -19999999998LL) return 3;
    Three u = yh_three((Three){11, 22, 33});
    if (u.a != 11 || u.b != 22 || u.c != 38) return 4;
    Wide source = {11, 22, 33}, w = yh_wide(source);
    if (source.c != 33 || w.a != 11 || w.b != 22 || w.c != 39) return 5;
    Float3 v = {{1, 2}, 3}, f = yh_float(v);
    if (v.c != 3 || f.pair.a != 1 || f.pair.b != 2 || f.c != 10) return 6;
    Float4 four = yh_four(c_make_four());
    if (four.values[0] != 1 || four.values[2] != 11 || four.values[3] != 4) return 7;
    Bits b = {.integer = 1234}, r = yh_bits(b);
    if (b.integer != 1234 || r.integer != 1243) return 8;
    if (yh_hfa_stack(1,2,3,4,5,6,7,(Float3){{8,9},10},11,12) != 78) return 9;
    if (yh_gpr_stack(1,2,3,4,5,6,7,(Two){8,9},10,11) != 66) return 10;
    if (yh_narrow(1,2,3,4,5,6,7,8,-1,2,-3,4,-5,6) != 39) return 11;
    Callback cb = yh_choose();
    Pair q = cb((Pair){17, -4});
    if (q.a != 17 || q.b != -1) return 12;
    Tiny1 one = yh_tiny_one((Tiny1){123});
    if (one.a != 124) return 13;
    FloatUnion fu = {.values = {3, 5}}, fr = yh_float_union(fu);
    if (fu.values[1] != 5 || fr.values[0] != 3 || fr.values[1] != 7) return 14;
    if (yh_fp_stack(1,2,3,4,5,6,7,8,9,10,11) != 30) return 15;
    if (yh_i8_args(1,2,3,4,5,6,7,8,-9,-10) != -10) return 16;
    if (yh_i8_call(1,2,3,4,5,6,7,8,-9,-10) != -10) return 17;
    Pair boxed = yh_box((CallbackBox){c_pair}, (Pair){11, 22});
    if (boxed.a != 11 || boxed.b != 25) return 18;
    Pair positive = yh_div(17, 5), negative = yh_div(-17, 5);
    if (positive.a != 3 || positive.b != 2 || negative.a != -3 || negative.b != -2) return 19;
    return 0;
}
