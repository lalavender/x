# yh 编译期全局字符串指针常量与跨模块导出实施方案

日期：2026-10-07。状态：实施中。

## 背景

字符串字面量指针常量的只读字节池此前只在**函数体内的字面量**上登记
（捕获期扫描 typed IR 表达式）。因此：

- `const TEXT *char = "abc";` 这类**全局常量**在编译期函数里引用时，
  `ct_ir_eval_expr` 的 `SYM_CONST` + `F_ADDR` 分支直接报「编译期求值不支持指针常量」；
- `pub const TEXT *char = "..."` **不能跨模块导出**，`iface.yh` 报
  「pub 指针常量（字符串）暂不支持跨模块导出」；
- 顶层/普通函数里的编译期调用实参（`const N int = $f(TEXT);`）由前端直接求值成
  **数据标签号**，形参校验按存活帧槽解析失败。

## 设计

三处都用同一条思路：**把字符串字面量的原样字节登记成只读池，指针值换成池地址**。

1. **符号引用**（`ct_ir.yh` 的 `SYM_CONST` + `F_ADDR` 分支）：常量保存了
   `const_expr_off/len`（intern 池里的原样 token 字节，含引号与转义），
   按 `ct_pool_register(gs.np_data, off, len, elem, key)` 解码登记后返回池地址；
   `const_expr_kind != 2`（非字符串指针常量）保持原诊断。
2. **池段复用**：`CtPoolSpan` 增加来源键 `key`（函数体字面量用源字节起点，
   全局常量用 `-(intern 偏移 + 1)`）。循环里反复引用同一常量时复用既有区间，
   否则 64 段上限会被快速耗尽。
3. **顶层实参归一化**（`ct_pool_adopt_label`，`ct_registry.yh` 的调用入口）：
   实参类型是 `*char`/`*u8`/`*i8` 且值仍是数据标签号时，按 `cval == value && F_ADDR
   && const_expr_kind == 2` 反查常量表，登记池后把实参值换成池地址。
   实参副本在 `call_values[i]` 上修改，不动调用方数组。
4. **接口导出**（`iface.yh`）：`F_ADDR` 且 `const_expr_kind == 2` 时，把声明
   **原样重放**成 `pub const NAME <type> = "原样字节";`，导入方解析这条声明时走
   与用户源码完全相同的登记路径（`parse_global_init` 的 `*char` 单 token 分支）。

## 边界

- 只支持元素为 `char`/`u8`/`i8` 的指针常量；`*u8` 由字符串字面量初始化本身就不合法
  （`*char` 不能隐式转 `*u8`），实际可用形态是 `*char`。
- 直接写字的顶层实参（`$f("abc")`）仍不支持：字面量实参不产生符号，无法按标签号反查。
- 非字符串指针常量（全局数组地址等）仍拒绝，诊断不变。

## 验收

1. `run/144-comptime-global-string-const.yh`：全局常量解引用、按形参传递、
   循环内重复引用（池段复用），结果 388。
2. `comptimecross` 项目：`pub const TEXT *char` 跨模块导出 + 同模块 CT 过程读取 +
   经 API 模块转发，host 断言退出码 0。
3. `build-check.py` 的 `ct5b-pointer-constant-not-evaluable` 语义已变，
   改造为 `ct5b-string-pointer-constant-evaluable`（要求构建成功）。
4. 既有语料与两道主门保持全绿。
