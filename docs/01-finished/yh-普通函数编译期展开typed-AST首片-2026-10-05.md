# yh 普通函数编译期展开 typed AST 首片

日期：2026-10-05。

## 结果

- 模块 worker 捕获普通函数 `$if/$for` 的选中分支 AST；未选分支继续仅做语法检查，不进入语句树。
- `$for` 每轮循环变量保存独立只读绑定编号；整数常量引用可由 SSA 直接降低为常量值。
- SSA lowering 将 `AST_STMT_COMPTIME` 视作透明的语句序列；诊断节点无子节点，因此不产生运行期指令。
- 捕获路径按实际新增表达式、语句和绑定节点累计 100000 上限。无 AST 捕获的单文件路径仍使用原 token 预算。

## 边界

普通 `$for` 仍逐轮调用 parser，当前 AST 是已选择/展开后的结果，尚未建立可克隆的未展开模板。
单文件函数 AST 捕获、check/build/SSA/旧发射器统一消费及所有入口统一预算仍待完成，CT1/CT2 typed AST
因此继续保持未完成。

## 测试

- 新增 `tests/yh-run/run/79-comptime-expanded-ast.yh`，覆盖 `$for` 常量绑定与嵌套 `$if`。
- 新增 `tests/modules/projects/comptimeexpanded/`，要求普通函数和调用方均进入 SSA，并验证运行结果。
- 新增 `tests/modules/projects/comptimeexpandedfail/`，在 check 路径验证 100000 个实际 AST 节点上限。
- 旧种子对预算用例仍报 token 规模错误；新实现报 AST 节点上限诊断。

## 验收

- `make test`：语法正例 71/71、反例 44/44，运行语义 171/171。
- `make selfhost-native`：cc3→cc4 的 14 个模块产物固定点一致，自解析 63 个源文件；固定点探针通过，模块语法 17/17、项目 82/82。
- `make seed` 后以新种子冷编 `make` 成功；`bin/yh.sha256` 从 `bin/` 目录验证为 `yh: OK`，`git diff --check` 通过。
- 种子 SHA-256：`72c31036fba6e180e9aa4bda0935408055c8740f19e9bf7c1ad29a60bf1fe5ee`。
