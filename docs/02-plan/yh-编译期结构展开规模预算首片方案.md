# yh 编译期结构展开规模预算首片方案

日期：2026-10-05。状态：**保守预算已交付；模块 worker typed AST 捕获与精确节点预算首片已交付；完整 AST 模板迁移仍待实施**。

## 背景

普通函数中的 `$if/$for` 仍由 `parse/parse_comptime.yh` 逐轮解析并发射代码。模块 worker
现在同时捕获实际选中的展开 AST，供 SSA lowering 消费；单文件入口仍关闭函数 AST 捕获。
因此本次只完成 AST 捕获/消费的首片，并未把重复解析改成 AST 模板克隆，也未统一所有入口。

## 本切片

- 在 `comptime/ct_registry.yh` 为当前编译单元维护累计展开规模，复用已有 100000 上限。
- 每次解析循环体前按该体 token 数收费；费用在循环体开始解析前累计，超过上限即诊断拒绝。
- 保留每个区间 1024 轮及全单元 100000 展开轮限制。嵌套展开的外层循环体和内层迭代会分别计费，
  因而这是用于阻止代码膨胀的保守源码规模上界，不等同于精确的 typed AST 节点计数。
- `tests/yh-run/fail/97-comptime-expansion-size-budget.yh` 覆盖 1024 轮、单轮主体 token 成本令累计规模越界；
  现有边界与 typed `$for` 用例锁定兼容行为。

## 验证结果

- 红测阶段旧编译器成功编译该反例；加入预算后定向 97、run/71、fail/61 通过。
- `make test`：语法 71/71 + 44/44，运行语义 158/158。
- `make selfhost-native`：14 个模块产物固定点一致、62 个源文件自解析、模块 17/17、项目 80/80，其余探针通过。
- `make seed`、冷编 `make` 和 `shasum -a 256 -c bin/yh.sha256` 均通过。
- 新种子 SHA-256：`8b2a0fb5215ded91141386d2fb823c424c0cdf510d0bd5e3b1c0d841e3b59850`。

## 后续 typed AST 迁移

2026-10-05 首片：选中 `$if` 分支和 `$for` 每轮体在模块 worker 中留在语句/表达式 AST；
SSA 将 `AST_STMT_COMPTIME` 当作透明序列，循环变量作为独立只读绑定保存。AST arena
构造器按实际新增表达式、语句和绑定节点累计 100000 上限；未选分支不捕获，循环总轮数
限制继续生效。

剩余工作：

1. 给普通函数结构控制建立稳定的未展开 typed 模板，保留绑定身份和源码映射。
2. 在 AST/IR 阶段基于已求值的 `$if/$for` 实例化分支和只读迭代绑定；移除语句体逐轮重解析。
3. 让单文件、模块 check/build、SSA lowering 与旧发射器消费同一展开结果；覆盖错误位置和嵌套来源。
4. 只有所有入口一致且模板路径替代重复解析后，才将 CT1/CT2 typed AST 收尾标为完成。

当前单文件入口继续用 token 规模预算；模块 worker 路径以 AST 节点预算为准。两者统一属于后续工作。

## 本次首片验收

- `tests/yh-run/run/79-comptime-expanded-ast.yh` 覆盖普通函数 `$for` 迭代绑定与嵌套 `$if` 的运行语义。
- `tests/modules/projects/comptimeexpanded/` 要求两个普通函数都实际进入 SSA，并验证运行结果。
- `tests/modules/projects/comptimeexpandedfail/` 的 500 条语句循环在 `check` 路径触发精确 100000 AST 节点上限；旧种子仍报 token 规模错误。
- `make test`：71/71 语法正例、44/44 语法反例、171/171 运行语料；`make selfhost-native`：固定点 14 项一致、自解析 63 个文件、模块 17/17、项目 82/82。
- 滚种子后冷编 `make` 与种子哈希校验通过，SHA-256：`72c31036fba6e180e9aa4bda0935408055c8740f19e9bf7c1ad29a60bf1fe5ee`。

## 验收

先以新增 `.yh` 用例确认旧编译器会通过，再由新预算拒绝；运行边界语料、`make test`、
`make selfhost-native` 和 `git diff --check`。仅所有门全绿后滚动种子并冷编复核。
