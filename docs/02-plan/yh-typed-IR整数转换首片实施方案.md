# yh typed IR 整数转换首片实施方案

日期：2026-10-06。状态：**已实现并通过全量自举门**。

## 目标

让受支持的普通整数函数将显式 `.to_type` 转换和混合整数运算降为 typed SSA，
并解除自动 C ABI fixture 对窄整数函数必须进入 SSA 的验收失败。

## 实施范围

- 增加一元 `IR_OP_CAST`，输入为整数 SSA 值，结果类型为定宽整数；verifier 检查
  来源和结果类型并验证操作数定义。
- AST lowering 复用前端 `sem_promote` 得到的公共整数类型，对二元表达式中较窄操作数
  插入 `CAST`；显式整数 `.to_type` 采用相同 IR 指令。
- 常量折叠按目标宽度截断，并按目标符号进行符号扩展或零扩展；ARM64 后端按目标
  类型规范化结果寄存器。
- 本首片只接入定宽整数到定宽整数。布尔、浮点、指针和聚合转换继续走既有后端路径。

## 验收

- 新增 `tests/yh-run/run/81-ssa-integer-cast.yh`，覆盖 i8/u8/u32 加宽、i64 窄化与往返。
- `tests/modules/projects/autoabi/` 现有 `yh_narrow` 用例验证 C ABI 运行结果；项目门额外
  检查至少 3 个函数进入 SSA，且持久 IR 至少含 3 条 `IR_OP_CAST`。
- `make`、`make test`（173/173）和 `make selfhost-native` 全绿；自举固定点 14/14、
  自解析 64 个文件、模块 17/17、项目验收 82/82。

实现记录见[完成报告](../01-finished/yh-typed-IR整数转换首片-2026-10-06.md)。
