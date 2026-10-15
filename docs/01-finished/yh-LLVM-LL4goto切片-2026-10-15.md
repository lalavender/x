# yh LLVM LL4 goto/label 切片（2026-10-15）

**状态：**`goto`/label 切片完成并验收；LL4 仅剩 `for-in`，LLVM 默认未切换、
种子未滚。

## 1. 范围与策略

支持任意 `goto 标签;` 与 `标签: 语句`：向后跳转成环、前向跳过不可达代码、
多前驱在标签处合流、跳出循环、块内标签。

**策略：含 goto/label 的函数全部绑定内存驻留**（入口 `alloca` + `LOAD`/`STORE`），
任意 CFG 跳转不需要 SSA phi 合流；循环携带表对该类函数自然为空。代价是这类
函数的局部读写走内存，未做按需提升。

## 2. 实现

- `CheckedLabel`（`checked_module_ctx.yh`）：当前函数的标签 → 块表；条目记录
  引用点的 `(file_id, start, length)`，块在函数入口**预分配**；
- `checked_label_same`：**按名字内容**比较两个源码区间。goto 与 label 是同一
  名字的不同出现位置，按区间本身比较必然查不到（实现中实测踩到）；
- `checked_lower_goto`：`goto` 名 token 是 `first + 1`，查/建目标块并以
  无条件分支终结当前路径，返回 0；
- `checked_lower_label`：名 token 是语句首 token；贯穿路径先分支进标签块，
  再降低被标记的单条子语句；
- `checked_lower_stmts`：goto 函数里语句路径终结后不停止，而是开一个不可达
  续块继续降低，保证后续标签总会被访问与进入；
- `checked_lower_function`：扫描函数语句范围判定 `has_goto`；
  为真时全部绑定标记内存驻留，并预分配所有标签块（发现趟回滚不丢块）；
- 循环发现趟回滚：对 `first_inst >= mark_inst` 的标签块恢复「未进入」状态
  （`first_inst=-1`、清终结与后继），真实趟在同一块号上重新进入；否则
  first_inst 会指向已丢弃的指令区间。

## 3. 门禁与验收

**新增**

- `tests/selfhost/llvm-goto.py`：文本含 ≥5 条跨块跳转；`opt -passes=verify`；
  O0 文本与 `default<O2>` 管线对象分别 clang 汇编、gcc 链接并原生运行
  （后向环、前向跳过、多前驱合流、跳出循环、块内标签五组断言）；未定义标签
  带来源拒绝且不发布产物；
- `tests/yh-run/run/llvm-goto.yh`：同源旧后端语义锁（172→173，总计 311→312）；
- `llvmlower/input/goto.yh` + `llvm-lower.py` goto 用例（必须降低成功）。

**更新**

- `tests/selfhost/llvm-control.py`：首片负例从 `goto`（现已支持）换成
  `for-in`，并同步文案。

**验收（WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）**

| 门 | 结果 |
| --- | --- |
| `make` | 退出 0 |
| `make test` | 退出 0：语法 78/78 与 42/42、运行 **312/312**（并发 8） |
| `make selfhost-native` | 退出 0：固定点 24 产物一致、自解析 86 文件、modules 18/18、项目 100/100 |
| 12 个 `llvm-*` 专项门（goto/switch/control/memory/lower/ir/runtime/checked/front-output/module/module-cache 等） | 全部退出 0 |

## 4. 边界与后续

- LL4 剩余：`for-in`（数组/切片迭代，依赖 LL5 聚合切片）；
- goto 函数的全部绑定内存驻留是过渡策略，后续可做按需提升；
- LL5 聚合与全局数据等剩余项不变；LLVM 默认未切换、种子未滚。
