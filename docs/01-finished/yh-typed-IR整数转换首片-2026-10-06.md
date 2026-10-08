# yh typed IR 整数转换首片完成

日期：2026-10-06。状态：**完成，所有本机回归与滚动自举主门通过**。

## 改动

- `compiler/ir/ssa.yh` 增加一元整数 `IR_OP_CAST`，verifier 限定输入和输出为定宽整数，
  常量折叠按目标位宽与符号性规范化结果。
- `compiler/parse/ast_ir.yh` 与 `ast_ir_build.yh` 复用 `sem_promote`，在整数混合宽度
  运算中显式转换操作数，并降低整数 `.to_type` 节点。
- `compiler/backend/arm64.yh` 对 cast 结果调用目标类型规范化，正确保留符号扩展和零扩展。
- 自动 C ABI 项目的 `yh_narrow` 从旧发射器回退路径进入 SSA；验收门保持至少 3 个 SSA
  函数，并检查至少 3 条 cast 指令。
- 增加 [run/81](../../tests/yh-run/run/81-ssa-integer-cast.yh)，覆盖 i8、u8、u32 到 i64
  的扩展，以及 i64 到 u8/u32 的窄化和往返。布尔、浮点、指针和聚合转换暂留旧路径。

## 验证

- `make`：通过。
- `make test`：语法正例 71/71、反例 44/44，运行语料 173/173。
- `make selfhost-native`：cc3/cc4 固定点 14/14、自解析 64 个源文件、固定点探针与 CLI
  冒烟通过；运行语料 173/173、模块语料 17/17、项目验收 82/82。
- 自举种子文件未修改；主门使用现有种子完成验证，没有执行 `make seed`。
