# yh 编译期字符串字面量指针常量只读访问实施方案

日期：2026-10-07。状态：实施中。

## 背景

编译期函数此前可以持有并传递字符串字面量指针常量（跨模块闭包也支持），但
**解引用与下标读取一律被拒绝**：CT 指针解析（`ct_ir_pointer_target`）只认存活调用帧
内的标量槽，字符串字面量指针的值是数据标签号，因此 `let p *char = "abc"; *p`
报「编译期指针必须指向当前存活调用帧的标量局部值」。

## 设计

把字符串字面量的字节在**捕获期**解码成一段只读的 `CtValue` 槽池（每字节一个槽，
末尾补 0 槽），指针值直接指向该池首槽，于是既有的指针机制（解引用、下标、算术）
全部复用，无需在取值路径上区分指针种类：

- `CtPoolSpan`（`ct_00_model.yh`）：登记池区间 `addr`/`count`/`elem`，全局最多 64 段。
- `ct_pool_register`（`ct_ir.yh`）：解码字符串 token（与后端 `.data` 发射相同的转义
  规则：`\n \r \t \0 \a \b \f \v \' \" \\ \xNN`），分配槽数组，登记区间并返回首槽地址。
- `ct_ir_register_string_pool`（`ct_ir.yh`）：在 `ct_ir_import` 里扫描本批表达式，
  对「`is_const` + `*char`/`*u8`/`*i8` + 单个 `TOK_STRING` token + 与当前源文件同批次
  （`token_count == c_tok_n`）」的节点登记池，并把地址写入与 `ct_ir_exprs` 并行的
  `ct_ir_expr_pool` 表（`ct_ir_grow` 新增第 5 类 arena）。
- 取值：`ct_ir_eval_expr` 的 `is_const` 分支优先返回并行表中的池地址。
- 读：`ct_ir_pointer_target` 在存活帧链之后追加池区间查询，元素类型必须与池登记类型一致。
- 写：赋值语句（`AST_STMT_ASSIGN`）在解析出位置后检查 `place.direct` 是否落在池内，
  命中即报「编译期不能写入字符串字面量指针常量」；解引用读取共用 `ct_ir_lvalue`
  解析目标槽，因此写保护必须施加在赋值语句而不是 `ct_ir_lvalue` 内。
- 生命周期：`ct_pool_reset` 随 `ct_reset` 释放池槽与并行表，供下一个编译单元复用。

## 边界

- 顶层/普通函数中的 CT 调用实参（如 `const N int = $f("abc");`）仍不支持字符串
  字面量指针常量：实参由前端直接求值成数据标签号，不经过 typed IR 捕获，没有可解码的
  源区间。函数体内构造再按形参传递是支持路径。
- 跨模块转发的正文在导入方**重新解析**（`iface_ct.yh` 的正文重放），因此导入方持有
  自己的 `c_src`/`c_toks`，`token_count` 判据成立，池登记照常进行；
  `comptimecross` 的 `first_letter` 锁定该行为。
- 全局数组地址等其他指针常量仍未支持；池区间不参与取址（`&p[0]` 沿用既有拒绝路径）。

## 验收

1. `run/141-comptime-string-const-read.yh`：解引用、下标、NUL 结尾、指针算术、转义解码
   与形参传递，结果 304。
2. `fail/147-comptime-string-const-write.yh`：写入池报「编译期不能写入字符串字面量指针常量」。
3. 原 `fail/133`（解引用被拒）语义已变，删除并由 run/141 取代。
4. 既有语料与模块/项目门保持全绿。
