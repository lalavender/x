# CheckedModule 快照校验迁入 check 方案

日期：2026-10-20。状态：已完成。

## 目标

把 `compiler/ast/checked_module_verify.yh` 中独立的快照完整性 verifier 全部迁入
`compiler/check/`。`ast` 继续拥有 `CheckedModule` 的构造、释放、只读访问器与 SSA
lowering。构造过程的分配/复制安全前置条件留在构造函数；IR verifier 仍归 `ir`。

## 边界与依赖

- `ast.CheckedModuleView` 只读借用快照自有表和目标身份；不复制、不分配、不转移所有权，
  生命周期不超过其 `CheckedModule` 所有者。
- `check.verify_checked_module` 只读取该视图；`ast` 不 import `check`。`cmd` 在快照捕获
  后、调用 lowering 前验证，从而保持无环依赖。
- 移除 `ast.checked_module_verify`；`checked_module_capture` 负责安全复制和所有权提交，
  不再调用一致性 verifier。`ast.lower_module` 的调用方须先通过 `check`。
- AST arena 校验器 `check.verify_module` 保持原样；类型/引用/范围这些构造期 guard 以及
  `ir.ir_verify`/`ir.ir_module_verify` 不迁移，它们分别属于捕获安全与 IR 子系统职责。

## 实施步骤

1. 先改 `llvmchecked` `.yh` 测试，让它经 `check` 验证捕获后快照并破坏/恢复表项；
   项目复制脚本加入 `check` 模块。
2. 新增只读 `CheckedModuleView`，迁移 `checked_storage_present` 和全部
   `checked_verify_*` 到 `check`，移除 `ast.checked_module_verify` 及捕获中的快照 verifier。
3. 为 `module_worker`、`llvm_emit` 和 `llvmlower` 所有捕获/lowering 路径显式接入校验；
   保持 capture 失败清理与 lowering 的 IR 检查行为。
4. 更新模块依赖、README、设计、todo 与完成记录；确认 `ast` 和 `parse` 均不依赖 `check`。
5. Apple Container Linux/arm64 执行 `make`、`make test`、`make selfhost-native`，
   验收种子不变及既有 `yh check` 不产出后端物契约。

## 实施结果

- `ast/checked_module_verify.yh` 已迁至 `check/checked_module.yh`，入口为
  `check.verify_checked_module`；原 verifier 不再由 `ast` 导出。`AstView` arena
  校验保持原顺序与规则，现由 `check/verify.yh` 提供 `check.verify_module`。
- 新增 `ast.CheckedModuleView` 借用快照数据；capture 只保留分配、复制、释放所需
  的内存安全 guard，项目 worker、单文件 LLVM 入口和 lowering 项目用例在消费前校验。
- `tests/modules/projects/llvmchecked/` 通过跨模块 API 校验两份独立快照，破坏类型
  闭包后确认拒绝，恢复后再确认通过；释放后句柄失效且另一份快照仍有效。
- Apple Container `debian:stable-slim`（Linux/arm64）：`make`、`make test`、
  `make selfhost-native` 均退出 0。固定点 129 项产物一致，自解析 107 个源文件，
  模块语料 18/18、项目验收 106/106；`yh check` 保持不生成后端产物。
- 种子哈希仍为
  `8ea2a9acc20438b385ccddd522b50b8dd4749423c8db2695c758296ada343b8c`，未执行
  `make seed`。容器未准备 LLVM host 桥/SDK，构建输出提示使用过渡种子内路径。
