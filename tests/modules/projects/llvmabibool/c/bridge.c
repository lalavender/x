// yh_bool：C 侧反向调用 YH 的 _Bool 定义。
extern _Bool yh_bool(_Bool value);
// yh_bool_noncanonical：确认 YH 字节 bool 返回到 C 时按非零值归一。
extern _Bool yh_bool_noncanonical(void);

// c_bool：通过 C _Bool ABI 返回规范布尔值。
_Bool c_bool(_Bool value) { return value; }

// c_check_yh：从 C 调用 YH 定义，检查 i1 zeroext 的反向 ABI。
int c_check_yh(void) {
    if (yh_bool(0) != 0 || yh_bool(1) != 1) return 2;
    if (yh_bool_noncanonical() != 1) return 3;
    return 0;
}
