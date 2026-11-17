# 编译诊断基线快照

由 `python3 tests/diagnostics/check.py --snapshot` 生成，请勿手改；
重新生成命令见 [README.md](README.md)。

## 汇总

- 失败语料: 147
- 带源码片段: 147
- 带 caret: 147
- 列号越出行尾(>行宽): 0/147 (0.0%)
- 列号=行宽(指向末字符): 6（其中落在 `)` 上: 2）
- 跨文件头: 0
- 无位置头: 0

## 逐用例

| 用例 | 片段 | caret | col | 行宽 | 列号处字符 |
| --- | --- | --- | ---: | ---: | --- |
| 01-undeclared-var.yh | 是 | 是 | 17 | 17 | z |
| 02-bad-assign.yh | 是 | 是 | 17 | 19 | " |
| 03-unknown-type.yh | 是 | 是 | 11 | 13 | F |
| 04-bare-varargs.yh | 是 | 是 | 16 | 22 | ) |
| 05-redeclare.yh | 是 | 是 | 4 | 14 | d |
| 06-main-args.yh | 是 | 是 | 1 | 20 | f |
| 07-literal-out-of-range.yh | 是 | 是 | 16 | 18 | 3 |
| 08-int-to-bool.yh | 是 | 是 | 18 | 18 | 1 |
| 09-main-bad-argv.yh | 是 | 是 | 1 | 35 | f |
| 10-array-size-mismatch.yh | 是 | 是 | 17 | 18 | s |
| 100-comptime-array-index-write-out-of-bounds.yh | 是 | 是 | 19 | 34 | $ |
| 100-expr-nest-depth.yh | 是 | 是 | 10 | 14 | ( |
| 100-logic-float-operand.yh | 是 | 是 | 24 | 27 | t |
| 101-comptime-slice-view-out-of-bounds.yh | 是 | 是 | 19 | 34 | $ |
| 101-len-non-array.yh | 是 | 是 | 12 | 17 | l |
| 102-comptime-struct-noninteger-field.yh | 是 | 是 | 19 | 33 | $ |
| 102-ternary-in-const.yh | 是 | 是 | 26 | 32 | 1 |
| 103-comptime-struct-pointer-array-field.yh | 是 | 是 | 20 | 42 | $ |
| 104-comptime-unsupported-aggregate-param.yh | 是 | 是 | 4 | 35 | u |
| 105-comptime-pointer-slice-return.yh | 是 | 是 | 4 | 25 | u |
| 106-aggregate-lit-out-of-range.yh | 是 | 是 | 22 | 25 | 3 |
| 106-comptime-aggregate-return-top-level.yh | 是 | 是 | 4 | 23 | u |
| 107-comptime-pointer-slice-return.yh | 是 | 是 | 4 | 25 | u |
| 109-comptime-enum-values-non-enum.yh | 是 | 是 | 10 | 31 | i |
| 11-switch-too-many.yh | 是 | 是 | 17 | 53 | , |
| 110-comptime-enum-values-readonly.yh | 是 | 是 | 20 | 22 | = |
| 112-comptime-array-length-call-cycle.yh | 是 | 是 | 24 | 37 | $ |
| 118-comptime-typed-layout-forward-const.yh | 是 | 是 | 12 | 25 | I |
| 119-comptime-sizeof-pending-layout.yh | 是 | 是 | 12 | 25 | I |
| 12-wraps-too-many.yh | 是 | 是 | 20 | 26 | ) |
| 120-comptime-array-length-missing-return-path.yh | 是 | 是 | 24 | 39 | $ |
| 123-comptime-layout-const-dependency-cycle.yh | 是 | 是 | 13 | 34 | A |
| 126-comptime-layout-expression-cycle.yh | 是 | 是 | 13 | 41 | $ |
| 127-comptime-layout-sizeof-expression-cycle.yh | 是 | 是 | 13 | 45 | s |
| 128-comptime-temporary-index-write.yh | 是 | 是 | 19 | 34 | $ |
| 129-comptime-struct-pointer-slice-field.yh | 是 | 是 | 4 | 50 | i |
| 13-attribute-duplicate.yh | 是 | 是 | 11 | 17 | e |
| 130-comptime-pointer-return.yh | 是 | 是 | 4 | 24 | e |
| 131-comptime-null-pointer-deref.yh | 是 | 是 | 17 | 35 | $ |
| 132-comptime-pointer-to-pointer-param.yh | 是 | 是 | 4 | 33 | w |
| 134-comptime-null-pointer-param.yh | 是 | 是 | 17 | 31 | $ |
| 135-comptime-element-address-noninteger.yh | 是 | 是 | 17 | 41 | $ |
| 136-comptime-element-address-temporary.yh | 是 | 是 | 17 | 36 | $ |
| 137-comptime-float-pointer-return.yh | 是 | 是 | 4 | 16 | l |
| 138-comptime-float-pointer-field.yh | 是 | 是 | 20 | 36 | $ |
| 139-float-const-modulo.yh | 是 | 是 | 17 | 25 | 5 |
| 14-attribute-unknown.yh | 是 | 是 | 3 | 7 | h |
| 140-comptime-pointer-arith-out-of-range.yh | 是 | 是 | 20 | 34 | $ |
| 141-comptime-pointer-plus-pointer.yh | 是 | 是 | 30 | 34 | o |
| 142-comptime-union-field-address.yh | 是 | 是 | 20 | 34 | $ |
| 143-comptime-union-float-field.yh | 是 | 是 | 20 | 31 | $ |
| 144-comptime-union-top-data.yh | 是 | 是 | 21 | 33 | $ |
| 145-comptime-unsupported-goto.yh | 是 | 是 | 20 | 28 | $ |
| 146-comptime-unsupported-label.yh | 是 | 是 | 20 | 30 | $ |
| 147-comptime-string-const-write.yh | 是 | 是 | 20 | 32 | $ |
| 149-enum-value-member-access.yh | 是 | 是 | 14 | 17 | n |
| 15-attribute-data-mismatch.yh | 是 | 是 | 1 | 9 | @ |
| 150-const-aggregate-write.yh | 是 | 是 | 7 | 12 | . |
| 153-comptime-global-agg-write.yh | 是 | 是 | 15 | 26 | $ |
| 154-comptime-if-expr-missing-else.yh | 是 | 是 | 17 | 29 | $ |
| 155-comptime-if-expr-type-mismatch.yh | 是 | 是 | 17 | 37 | $ |
| 156-comptime-if-expr-nonconst.yh | 是 | 是 | 17 | 32 | v |
| 157-comptime-if-expr-stmt-position.yh | 是 | 是 | 17 | 25 | 3 |
| 158-comptime-is-type-unknown.yh | 是 | 是 | 30 | 40 | N |
| 158-newline-return-value.yh | 是 | 是 | 5 | 10 | r |
| 159-comptime-fields-non-struct.yh | 是 | 是 | 30 | 32 | { |
| 16-attribute-let-mismatch.yh | 是 | 是 | 1 | 9 | @ |
| 160-comptime-field-meta-bare.yh | 是 | 是 | 14 | 14 | f |
| 161-comptime-field-meta-value.yh | 是 | 是 | 16 | 20 | v |
| 162-comptime-field-unknown-name.yh | 是 | 是 | 22 | 26 | " |
| 163-comptime-field-name-not-string.yh | 是 | 是 | 22 | 23 | n |
| 164-comptime-field-write.yh | 是 | 是 | 15 | 32 | $ |
| 165-test-decl-empty-name.yh | 是 | 是 | 6 | 10 | " |
| 166-test-decl-pub.yh | 是 | 是 | 5 | 20 | t |
| 167-test-decl-attribute.yh | 是 | 是 | 1 | 9 | @ |
| 168-unused-function.yh | 是 | 是 | 4 | 17 | h |
| 169-return-conversion.yh | 是 | 是 | 12 | 14 | 3 |
| 17-attribute-inline-prototype.yh | 是 | 是 | 4 | 23 | c |
| 170-assign-conversion.yh | 是 | 是 | 9 | 11 | 3 |
| 18-cabi-aggregate.yh | 是 | 是 | 4 | 26 | c |
| 19-copaque-sizeof.yh | 是 | 是 | 12 | 26 | s |
| 20-copaque-value.yh | 是 | 是 | 12 | 33 | h |
| 21-cabi-function-pointer-return.yh | 是 | 是 | 17 | 29 | f |
| 214-array-length-not-const-arithmetic.yh | 是 | 是 | 12 | 35 | n |
| 215-array-length-literal-bounds.yh | 是 | 是 | 17 | 26 | ] |
| 216-array-length-literal-overflow.yh | 是 | 是 | 22 | 31 | ] |
| 22-cabi-empty-enum.yh | 是 | 是 | 10 | 18 | C |
| 23-cabi-slice-field.yh | 是 | 是 | 5 | 16 | v |
| 24-noreturn-nonvoid.yh | 是 | 是 | 4 | 18 | i |
| 25-noreturn-fallthrough.yh | 是 | 是 | 4 | 27 | i |
| 26-noreturn-return.yh | 是 | 是 | 4 | 19 | i |
| 27-noreturn-break-loop.yh | 是 | 是 | 4 | 27 | i |
| 28-cabi-callback-needs-extern.yh | 是 | 是 | 34 | 34 | ) |
| 29-cabi-array-parameter.yh | 是 | 是 | 12 | 29 | v |
| 30-cabi-hfa-parameter.yh | 是 | 是 | 13 | 29 | v |
| 31-cabi-slice-parameter.yh | 是 | 是 | 12 | 28 | v |
| 32-cabi-large-aggregate.yh | 是 | 是 | 11 | 29 | v |
| 33-too-many-float-args.yh | 是 | 是 | 63 | 75 | . |
| 34-cabi-to-yh-function.yh | 是 | 是 | 44 | 72 | c |
| 35-yh-to-cabi-function.yh | 是 | 是 | 54 | 80 | v |
| 36-cabi-cast-convention.yh | 是 | 是 | 70 | 91 | ; |
| 37-cabi-field-yh-function.yh | 是 | 是 | 18 | 37 | c |
| 38-cabi-function-type-slice.yh | 是 | 是 | 18 | 40 | @ |
| 56-dollar-requires-comptime.yh | 是 | 是 | 20 | 31 | o |
| 57-comptime-requires-dollar.yh | 是 | 是 | 24 | 27 | ( |
| 58-comptime-argument-must-be-constant.yh | 是 | 是 | 22 | 27 | v |
| 59-comptime-function-value.yh | 是 | 是 | 32 | 43 | c |
| 60-comptime-main.yh | 是 | 是 | 16 | 27 | m |
| 60-user-c-varargs.yh | 是 | 是 | 30 | 34 | ) |
| 61-comptime-for-budget.yh | 是 | 是 | 10 | 25 | i |
| 62-comptime-if-needs-constant.yh | 是 | 是 | 10 | 21 | v |
| 63-comptime-assert-fails.yh | 是 | 是 | 5 | 43 | $ |
| 64-comptime-error.yh | 是 | 是 | 5 | 40 | $ |
| 65-comptime-diag-value.yh | 是 | 是 | 22 | 62 | c |
| 66-comptime-assert-type.yh | 是 | 是 | 6 | 14 | a |
| 67-comptime-assert-constant.yh | 是 | 是 | 13 | 23 | v |
| 68-comptime-diagnostic-name.yh | 是 | 是 | 4 | 26 | a |
| 69-comptime-error-runtime-if.yh | 是 | 是 | 9 | 44 | $ |
| 70-comptime-error-long-message.yh | 是 | 是 | 5 | 747 | $ |
| 71-comptime-forward-global-const.yh | 是 | 是 | 20 | 24 | A |
| 73-comptime-i32-overflow.yh | 是 | 是 | 19 | 32 | 2 |
| 74-comptime-shift-width.yh | 是 | 是 | 19 | 25 | 1 |
| 75-comptime-i32-div-overflow.yh | 是 | 是 | 19 | 34 | - |
| 76-comptime-function-overflow.yh | 是 | 是 | 19 | 37 | $ |
| 77-comptime-u64-overflow.yh | 是 | 是 | 19 | 25 | M |
| 78-comptime-left-shift-overflow.yh | 是 | 是 | 19 | 33 | 1 |
| 79-comptime-function-neg-overflow.yh | 是 | 是 | 19 | 38 | $ |
| 80-comptime-control-depth.yh | 是 | 是 | 133 | 144 | $ |
| 81-comptime-for-control-depth.yh | 是 | 是 | 133 | 144 | $ |
| 82-comptime-for-break-escape.yh | 是 | 是 | 13 | 17 | b |
| 83-comptime-for-continue-escape.yh | 是 | 是 | 13 | 20 | c |
| 84-comptime-for-address.yh | 是 | 是 | 29 | 29 | i |
| 85-comptime-for-assign.yh | 是 | 是 | 11 | 13 | = |
| 86-comptime-expansion-trace.yh | 是 | 是 | 17 | 52 | $ |
| 87-comptime-recursion-budget.yh | 是 | 是 | 20 | 30 | $ |
| 88-comptime-body-call-arity.yh | 是 | 是 | 23 | 23 | ) |
| 89-comptime-body-call-type.yh | 是 | 是 | 20 | 21 | x |
| 90-comptime-function-diagnostic-path.yh | 是 | 是 | 9 | 53 | $ |
| 91-comptime-function-assert-path.yh | 是 | 是 | 5 | 47 | $ |
| 92-comptime-typed-assert.yh | 是 | 是 | 5 | 61 | $ |
| 93-comptime-typed-if-checks-both.yh | 是 | 是 | 16 | 27 | m |
| 94-comptime-typed-for-readonly.yh | 是 | 是 | 15 | 17 | = |
| 95-comptime-typed-for-budget.yh | 是 | 是 | 22 | 31 | $ |
| 96-comptime-typed-expression-statement.yh | 是 | 是 | 5 | 62 | $ |
| 97-comptime-expansion-size-budget.yh | 是 | 是 | 5 | 12 | r |
| 98-comptime-array-index-out-of-bounds.yh | 是 | 是 | 19 | 34 | $ |
| 99-comptime-array-negative-index.yh | 是 | 是 | 19 | 34 | $ |
