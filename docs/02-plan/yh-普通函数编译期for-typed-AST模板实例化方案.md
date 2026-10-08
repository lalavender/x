# yh 普通函数编译期 `$for` typed AST 模板实例化方案

日期：2026-10-05。状态：**受限模板已实现；其后发现的 C ABI 项目门失败已于 2026-10-06 修复**。

## 目标

对可安全复用的普通函数 `$for` 体只捕获一份 typed AST 模板，由 SSA lowering 按编译期区间实例化；继续由 parser 每轮检查语义并向旧后端发码，保持不支持 SSA 形态的回退行为正确。

## 边界与选择

首片只接模块 worker 中启用 AST 捕获的普通函数 `$for`，且要求循环体不含任何 `$` 控制/诊断指令及局部 `const`/类型声明。嵌套编译期语法维持原逐轮捕获路径。普通运行期 `if`、标量 `let`、赋值和返回由 SSA 按同一模板重复降低。迭代变量绑定作为只读编译期绑定留在模板中，lowering 为每一轮提供独立常量值。

所有轮次仍走 parser，所以名字/类型诊断和旧后端汇编保持现状；AST 侧仅保存一份模板，预算侧按逻辑实例化节点数收费。单文件入口和消除所有重复解析不属于本阶段。

## 实施步骤

1. 在 `tests/modules/projects/comptimeexpanded/main/main.yh` 增加无嵌套 `$` 的模板候选，含局部 `let`、运行期 `if` 和迭代变量读取；项目检查要求三函数均进入 SSA。先对当前种子编译，确认运行仍正确但新 SSA 数量断言失败。
2. 在 `compiler/parse/ast_stmt.yh` 增加编译期循环模板元数据及验证/查找/重置函数；元数据记录 wrapper、循环绑定、区间及模板 block。保持 `AstStmt` 布局不变，避免影响 `comptime.CtStmt` 的布局契约。
3. 在 `compiler/parse/parse_comptime.yh` 对首片兼容形态捕获首轮 AST，后续轮关闭 AST 捕获但继续正常解析；记录逻辑模板节点成本，并将不兼容体留在旧的逐轮 AST 捕获路径。
4. 在 `compiler/comptime/ct_registry.yh` 添加批量 AST 实例化预算计费，让模板后续轮按语句/表达式/绑定节点数计费，保留单元预算上限。
5. 在 `compiler/parse/ast_ir_control.yh` 和 `compiler/parse/ast_ir_build.yh` 识别模板元数据；为迭代变量生成各轮常量 SSA 值，并在每轮重复降低模板 block，同时正确复用模板内局部绑定编号。
6. 增加语料覆盖零次/多次、循环体局部绑定、运行期分支及预算边界；更新 `docs/todo.md`、本方案、`docs/finish.md` 和 `docs/01-finished/`；运行定向测试、`make`、`make test`、`make selfhost-native` 与 `git diff --check`。只有所有门全绿才滚种子。

## 验收重点

- 旧种子阶段新增项目的运行结果正确，且 SSA 计数断言失败，证明测试能检出模板 lowering 缺失。
- 新实现中三个候选函数都进入 SSA，且旧后端回退语料和 compile-time 展开预算语料继续通过。
- 全量测试和两代自举固定点通过；不滚种子则不能把该行为记为已交付。

## 本轮结果

- 新增模块项目候选包含循环变量读取、局部 `let` 和运行期 `if`。旧种子可运行但仅有 2 个 SSA 函数；当前编译器有 3 个且运行退出码为 0。
- 当时 `make`、`make test` 通过；`make selfhost-native` 固定点 14/14、自解析 64 个源文件、模块 17/17 和模板用例均通过，但项目门为 81/82。2026-10-06 通过整数 typed-IR `CAST` 和公共整数类型提升补齐自动 C ABI 窄整数函数；当前 `make test` 173/173、项目门 82/82，详见[整数转换完成报告](../01-finished/yh-typed-IR整数转换首片-2026-10-06.md)。
- 主门未全绿时曾误执行 `make seed`，当前 `bin/yh` SHA-256 为 `0e6088ab94183149d84d3683baf01e733dd9ced71f9ed3c3b6d3bafd78609b3e`。任务开始时旧种子 `72c31036fba6e180e9aa4bda0935408055c8740f19e9bf7c1ad29a60bf1fe5ee` 未能恢复；当前种子已通过本轮完整自举主门验证，未再次滚种子。
- parser 仍对每轮做语义检查并为旧后端生成代码；本轮只将兼容体改为 AST 单份捕获和 SSA 模板实例化，不等同于完整移除重解析或接通单文件路径。
