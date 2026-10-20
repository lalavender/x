# yh AST check 模块拆分实施方案

日期：2026-10-20。状态：已完成。

范围注记：本方案完成 AST arena 的四项校验迁移；其后扩大的快照一致性校验迁移
单独记录在[CheckedModule 校验迁入方案](yh-CheckedModule校验迁入check方案.md)。

## 复核基线

在 `origin/llvm`（`6eace6f`）上复核后，发现 AST 校验调用点共三处：
`cmd/module_worker.yh` 中 LLVM 模块发布前的通用错误出口、模块 worker 原有四条
分阶段检查，以及 `cmd/llvm_emit.yh` 的单文件 LLVM 文本路径。迁移必须覆盖三处，
并保留各处既有外层错误行为。此前 arm64 工作树中的实现不直接应用于此基线，
因为当前 `GenState` 已把任务字段放入 `gs.task`，且增加了 LLVM 编译路径。

## 实施步骤

1. 在 `tests/modules/projects/astcheck/` 增加 `.yh` 探针，构造合法 AST view；
   分别损坏表达式子引用、语句链、声明函数体、函数上下文范围、绑定和编译期
   `$for` 关联，检查被拒绝。覆盖捕获关闭时跳过检查，以及检查前后视图和节点
   不变。把所需编译器模块复制到 `tmp/`，并接入 `build-check.py`。
2. 将校验所需的 `AstExpr`、`AstStmt`、`AstFunctionContext` 和
   `AST_EXPR_ARG_LIST` 设为公开；现有公开的 `AstDecl`、`AstStmtExpr`、
   `AstBinding`、`AstComptimeFor` 供借用视图字段使用。新增 `AstView` 和
   `ast_view(out *AstView)`，只暴露 arena、计数、解析/根链与函数封存状态。
3. 新增 `compiler/check/verify.yh`，逐字迁移四类校验条件和具体诊断，改为读取
   视图；四个校验器私有，唯一入口按表达式 → 语句 → 声明 → 函数顺序执行。
   捕获关闭时直接成功。非零返回状态区分失败阶段，供旧分阶段调用点保留其
   外层诊断。
4. 更新 `module_worker` 两处及 `llvm_emit` 一处调用，删除旧 AST 校验导出，
   检查 `parse` 无 `check` 依赖，并更新 README、模块依赖设计、todo 与完成记录。
5. 在 Apple Container 的原生 Linux/arm64 环境中运行 `make`、`make test`、
   `make selfhost-native`；检查九模块固定点、自解析、既有项目验收和 `yh check`
   不生成后端产物契约。容器只写 `tmp/`，不覆盖种子。

## 边界

不迁移 `parse/gen` 语义检查，不改变语法、诊断文案、返回成败、AST 构造、
编译期导出、`CheckedModule` 校验或 SSA lowering；不滚种子，也不要求
macOS/Windows 回归。

## 实施与验证结果

- `ast.AstView` 借出校验使用的 arena、计数、解析/根链及函数封存状态；四项
  校验器迁入 `check/verify.yh` 并保持原检查条件和具体诊断，统一入口按表达式、
  语句、声明、函数顺序执行。`module_worker` 的两处与 `llvm_emit` 一处调用均已迁移。
- `tests/modules/projects/astcheck/` 探针接入 `tests/modules/build-check.py`；另将
  同样直接调用旧 AST 校验导出的 `llvmlower` 测试夹具接线到新入口，项目验收为
  106/106。
- Apple Container `debian:stable-slim`（Linux/arm64）中，`make`、`make test`、
  `make selfhost-native` 均退出 0。`make test`：语法正例 78、反例 42，运行语料
  344/349（5 项按 Linux/arm64 跳过）、fail 132/132、pass 8/8、代码统计 6/6。
  自举门：cc3→cc4 固定点 **128 项产物一致**、自解析 106 个源文件、`yh check`
  无后端产物契约通过、模块语料 18/18、项目验收 106/106。
- 当前 LLVM 基线的固定点门按全部发布产物计数为 128 项，取代早期草稿中的
  “27 项”估计。种子哈希
  `8ea2a9acc20438b385ccddd522b50b8dd4749423c8db2695c758296ada343b8c`
  校验通过；未执行 `make seed`，未修改入库种子。
