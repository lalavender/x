# yh 编译期不受支持正文的具体诊断实施方案

日期：2026-10-07。状态：实施中。

## 背景

`ct_ir_support_code`（原 `ct_ir_is_supported`）在 typed IR 捕获时筛选可执行子集，
只返回 0/1。不在子集内的编译期函数被调用时统一报
「编译期函数正文不在受支持的 typed IR 子集内」，既不说哪个构造、
也不好判断是写法问题还是编译器边界。

## 设计

- `ct_ir_support_code` 改为返回**原因码**：0 受支持，否则为首个不受支持构造的类别
  （100 类型声明、200 goto、300 标签、400 编译期语句、500 其他语句、
  600 未知表达式种类、700 表达式缺少类型）。判定顺序保持原样，只把 `return 0`
  替换为对应类别码。
- `CtFunction` 增加 `ir_unsupported` 原因码字段：捕获时（`ct_ir_import`）与
  `ir_supported` 一起写入，登记时复位。诊断延迟到**实际调用**时才发出，
  避免未被调用的编译期函数误报。
- `ct_invoke_in_frame` 的回退分支改调 `ct_unsupported_diagnostic(code)`，
  按类别给出具体文本（如「编译期函数正文的 goto 语句不在受支持的 typed IR 子集内」），
  未知码保留原统一文本兜底。诊断位置沿用调用处（`file:line:col`），
  已能定位到是哪个编译期调用。

## 为什么不做位置精确到函数体行

`CtExpr.first`/`CtStmt.first` 是**源文件 token 索引**，而 `CtFunction.body` 是独立的
函数体 token 快照，两者索引域不同；跨模块转发（`iface_ct.yh`）时源 token 表也不再是
定义文件。要给出函数体内的行列需要额外维护 token→行映射，收益不足，故本片只到
构造类别 + 调用点定位。

## 验收

1. `fail/145-comptime-unsupported-goto.yh`：诊断包含「goto 语句不在受支持的 typed IR 子集内」。
2. `fail/146-comptime-unsupported-label.yh`：诊断包含「标签语句不在受支持的 typed IR 子集内」。
3. 既有语料与模块/项目门保持全绿。
