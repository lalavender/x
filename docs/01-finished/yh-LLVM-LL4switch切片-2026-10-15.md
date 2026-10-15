# yh LLVM LL4 switch 切片（2026-10-15）

**状态：**`switch` 切片完成并验收；LL4 剩余 `goto`/label 与 `for-in`，
LLVM 默认未切换、种子未滚。

## 1. 范围与语义

- `switch value { case c1, c2 { ... } default { ... } }`：
  控制值只求值一次；case 常量按源码顺序比较；命中进入对应体；
  各体之间**无 fallthrough**；`default` 在其位置作为未命中分支；
- `switch` 不推入循环栈：体内 `break`/`continue` 仍作用于外层循环；
- 所有贯穿路径在退出块合流（N 元 phi），体内赋值照常进入外层循环的携带表。

## 2. 实现（`compiler/ast/checked_module_lower.yh`）

- `checked_lower_switch`：先数 `AST_STMT_CASE` 分支、分配「路径 × 绑定」值表与
  路径块表，再调用主体；失败不发布部分结果；
- `checked_lower_switch_body`：控制值求值一次 → 每个 case 生成常量比较链
  （命中跳体块、未命中跳下一比较块或 skip 块）；每个体独立值快照，
  贯穿时记录路径并跳退出块；退出块对每个绑定做 N 元合流：
  任一路径缺值 → -1；全相等 → 直接复用；否则建 `phi`；
- 全部分支终结（无贯穿路径）时退出块只作为合法空不可达块存在，返回 0；
- `checked_lower_stmt` 增加 `AST_STMT_SWITCH` 分派。

case 值仍由语义阶段保证为编译期常量；非常量 case 在语义层带来源拒绝
（本片不再重复实现常量折叠）。

## 3. 门禁与验收

**新增**

- `tests/selfhost/llvm-switch.py`：文本含 case 比较（`icmp eq ≥ 4`）与合流
  `phi ≥ 2`；`opt -passes=verify`；O0 文本与 `default<O2>` 管线对象分别
  clang 汇编、gcc 链接并原生运行（多值 case/default/循环合流/嵌套 switch/
  循环内 break）；非常量 case 带来源拒绝且不发布产物；
- `tests/yh-run/run/llvm-switch.yh`：同源旧后端语义锁（171→172，
  总计 310→311）；
- `llvmlower/input/control.yh` 增加 switch，`llvm-lower` 继续要求降低成功。

**验收（WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）**

| 门 | 结果 |
| --- | --- |
| `make` | 退出 0 |
| `make test` | 退出 0：语法 78/78 与 42/42、运行 **311/311**（并发 8） |
| `make selfhost-native` | 退出 0：固定点 24 产物一致、自解析 86 文件、modules 18/18、项目 100/100 |
| `llvm-switch / llvm-control / llvm-memory / llvm-lower / llvm-ir` | 全部退出 0 |
| `llvm-runtime / llvm-checked / llvm-front-output / llvm-module / llvm-module-cache` | 全部退出 0 |

## 4. 边界与后续

- 剩余 LL4：`goto`/label（当前带来源拒绝）与 `for-in`；
- 聚合与全局数据等 LL5 剩余项不变；LLVM 默认未切换、种子未滚。
