#include <stdint.h>

typedef struct { uint8_t value; } AppleByte;
typedef struct { uint8_t first, second, third; } AppleTriple;
typedef struct { uint64_t value; } AppleWord;
typedef struct { uint64_t first, second; } ApplePair16;
typedef struct { uint8_t first, second, third, fourth, fifth, sixth, seventh, eighth, ninth; } AppleNine;
typedef union { uint64_t integer; double floating; } AppleUnion;
typedef struct { float left, right; } AppleFloatPair;
typedef struct { AppleFloatPair inner; float tail; } AppleHfa3;
typedef struct { double left, right; } AppleFloat2;
typedef union { double scalar; double values[2]; } AppleFloatUnion;
typedef struct { uint64_t first, second, third; } AppleWide;

extern AppleByte yh_round_byte(AppleByte);
extern AppleTriple yh_round_triple(AppleTriple);
extern AppleWord yh_round_word(AppleWord);
extern ApplePair16 yh_round_pair16(ApplePair16);
extern AppleNine yh_round_nine(AppleNine);
extern AppleUnion yh_round_union(AppleUnion);
extern AppleFloat2 yh_round_float2(AppleFloat2);
extern AppleFloatUnion yh_round_float_union(AppleFloatUnion);
extern AppleHfa3 yh_round_hfa3(AppleHfa3);
extern int32_t yh_sum_hfa_overflow(double, double, double, double, double, double,
                                   double, AppleFloat2, double);
extern AppleWide yh_round_wide(AppleWide);
extern AppleByte yh_call_byte(AppleByte);
extern AppleTriple yh_call_triple(AppleTriple);
extern AppleWord yh_call_word(AppleWord);
extern ApplePair16 yh_call_pair16(ApplePair16);
extern AppleNine yh_call_nine(AppleNine);
extern AppleUnion yh_call_union(AppleUnion);
extern AppleFloat2 yh_call_float2(AppleFloat2);
extern AppleFloatUnion yh_call_float_union(AppleFloatUnion);
extern AppleHfa3 yh_call_hfa3(AppleHfa3);
extern AppleFloat2 yh_adjust_hfa(AppleFloat2);
extern AppleFloat2 yh_nested_hfa(AppleFloat2);
extern AppleFloat2 yh_call_hfa_callback(AppleFloat2);
extern AppleFloat2 yh_call_returned_hfa_callback(AppleFloat2);
extern int32_t yh_call_hfa_overflow(double, double, double, double, double, double,
                                    double, AppleFloat2, double);
extern AppleWide yh_call_wide(AppleWide);

AppleByte c_round_byte(AppleByte value) { return value; }
AppleTriple c_round_triple(AppleTriple value) { return value; }
AppleWord c_round_word(AppleWord value) { return value; }
ApplePair16 c_round_pair16(ApplePair16 value) { return value; }
AppleNine c_round_nine(AppleNine value) { return value; }
AppleUnion c_round_union(AppleUnion value) { return value; }
AppleFloat2 c_round_float2(AppleFloat2 value) { return value; }
AppleFloatUnion c_round_float_union(AppleFloatUnion value) {
    value.values[1] += 3.0;
    return value;
}
AppleHfa3 c_round_hfa3(AppleHfa3 value) { return value; }
AppleFloat2 c_adjust_hfa(AppleFloat2 value) {
    value.left += 10.0;
    value.right += 20.0;
    return value;
}
AppleFloat2 c_apply_hfa_callback(AppleFloat2 (*callback)(AppleFloat2), AppleFloat2 value) {
    return callback(value);
}
AppleFloat2 (*c_choose_hfa_callback(void))(AppleFloat2) { return c_adjust_hfa; }
int32_t c_sum_hfa_overflow(double a, double b, double c, double d, double e, double f,
                           double g, AppleFloat2 value, double tail) {
    return (int32_t)(a + b + c + d + e + f + g + value.left + value.right + tail);
}
AppleWide c_round_wide(AppleWide value) { value.second += 3; return value; }

int c_test(void) {
    AppleByte byte = {0xa5};
    AppleTriple triple = {0x12, 0x34, 0x56};
    AppleWord word = {UINT64_C(0x123456789abcdef0)};
    ApplePair16 pair16 = {0x1020304050607080, 0x8877665544332211};
    AppleNine nine = {1, 2, 3, 4, 5, 6, 7, 8, 9};
    AppleUnion un = {.integer = UINT64_C(0x1020304050607080)};
    AppleFloatUnion float_union = {.values = {3.0, 5.0}};
    AppleFloat2 hfa2 = {8.0, 9.0};
    AppleHfa3 hfa3 = {{1.5f, -2.0f}, 3.25f};
    AppleWide wide = {11, 22, 33};
    AppleByte rb = yh_round_byte(byte);
    AppleTriple rt = yh_round_triple(triple);
    AppleWord rw = yh_round_word(word);
    ApplePair16 rp = yh_round_pair16(pair16);
    AppleNine rn = yh_round_nine(nine);
    AppleUnion ru = yh_round_union(un);
    AppleFloatUnion rfu = yh_round_float_union(float_union);
    AppleFloat2 rhfa2 = yh_round_float2(hfa2);
    AppleHfa3 rhfa3 = yh_round_hfa3(hfa3);
    AppleFloat2 from_yh_callback = yh_adjust_hfa(hfa2);
    AppleFloat2 nested_direct = yh_nested_hfa(hfa2);
    AppleWide rlarge = yh_round_wide(wide);
    if (rb.value != byte.value || rt.first != triple.first || rt.second != triple.second
        || rt.third != triple.third || rw.value != word.value
        || rp.first != pair16.first || rp.second != pair16.second
        || rn.eighth != 8 || rn.ninth != 9 || ru.integer != un.integer
        || rhfa2.left != 8.0 || rhfa2.right != 9.0
        || rhfa3.inner.left != 1.5f || rhfa3.inner.right != -2.0f
        || rhfa3.tail != 3.25f) return 1;
    if (float_union.values[1] != 5.0 || rfu.values[0] != 3.0
        || rfu.values[1] != 7.0) return 5;
    if (from_yh_callback.left != 9.0 || from_yh_callback.right != 11.0
        || nested_direct.left != 19.0 || nested_direct.right != 31.0) return 4;
    if (rlarge.first != 11 || rlarge.second != 22 || rlarge.third != 38
        || wide.third != 33) return 2;
    rb = yh_call_byte(byte);
    rt = yh_call_triple(triple);
    rw = yh_call_word(word);
    rp = yh_call_pair16(pair16);
    rn = yh_call_nine(nine);
    ru = yh_call_union(un);
    rfu = yh_call_float_union(float_union);
    rhfa2 = yh_call_float2(hfa2);
    rhfa3 = yh_call_hfa3(hfa3);
    AppleFloat2 nested_hfa = yh_call_hfa_callback(hfa2);
    AppleFloat2 returned_callback = yh_call_returned_hfa_callback(hfa2);
    int32_t overflow_yh = yh_sum_hfa_overflow(1, 2, 3, 4, 5, 6, 7, hfa2, 10);
    int32_t overflow_c = yh_call_hfa_overflow(1, 2, 3, 4, 5, 6, 7, hfa2, 10);
    rlarge = yh_call_wide(wide);
    if (rb.value != byte.value || rt.third != triple.third || rw.value != word.value
        || rp.first != pair16.first || rp.second != pair16.second
        || rn.first != 1 || rn.eighth != 8 || rn.ninth != 9
        || ru.integer != un.integer || rhfa2.left != 8.0 || rhfa2.right != 9.0
        || rhfa3.tail != 3.25f || overflow_yh != 55 || overflow_c != 55
        || nested_hfa.left != 19.0 || nested_hfa.right != 31.0
        || returned_callback.left != 18.0 || returned_callback.right != 29.0
        || rlarge.first != 11 || rlarge.second != 25 || rlarge.third != 33
        || wide.second != 22) return 3;
    if (rfu.values[0] != 3.0 || rfu.values[1] != 8.0) return 6;
    return 0;
}
