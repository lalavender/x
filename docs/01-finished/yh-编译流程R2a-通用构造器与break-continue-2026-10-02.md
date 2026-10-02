# yh 编译流程 R2a：通用构造器与 break/continue 切片报告

日期：2026-10-02。范围：`compiler/ir/ssa.yh`、`compiler/parse/ast_ir_build.yh`
（新文件）、`compiler/parse/ast_ir.yh`、`compiler/parse/ast_ir_control.yh`、
`tests/modules/projects/irfront/`、`tests/modules/build-check.py`。
前置切片见[条件循环报告](yh-编译流程R2a-条件循环-2026-10-02.md)。

## 切片内容

本切片把「固定形态匹配」的受限 lowering 替换为**通用递归构造器**，
使 if/else（任意嵌套与 else-if 链）、条件循环、break/continue、return
与顺序语句可以任意组合进入 typed SSA：

1. **动态块构造器**（`ast_ir_build.yh`）：块表按需增长，块按需分配编号，
   指令区间在进入块时确定——合流块可以先分配、后填充；终结符允许在
   乱序填充下回填（`close_term` 区分当前块与已封存块）。
2. **verifier 覆盖检查**：`ir_verify` 对块指令区间的「按编号连续」检查
   改为「互不重叠且恰好覆盖 [0, inst_count)」的覆盖标记检查；
   块填充顺序不再要求与编号一致，其余校验不变。
3. **递归语句降低**：`ast_ir_b_stmts` 逐语句分派；if/else 在独立值副本
   上降低两臂，双侧贯穿建双前驱 phi 合流，单侧贯穿直接继续，双侧终结
   丢弃不可达后继；else-if 链作为单语句递归。
4. **循环两趟协议**：发现趟直接在主 builder 上降低循环体（哑目标块承接
   break/continue），收集携带绑定、continue/break 站点数与是否贯穿，
   随后回滚指令/phi/块/调用表计数与值映射——发现与真实降低执行同一份
   代码，保证 phi 输入槽布局（入口 + continue×N + 回边）精确一致。
   循环头 phi 的 continue 边输入在站点创建时回填；退出块对「break 站点
   值 ≠ 条件假边值」的携带绑定建合流 phi。嵌套循环、for-in、无限循环、
   switch、goto 仍返回 -2 回退旧发射器。
5. **替换与清理**：`ast_ir_lower_function` 的形状检测与三条特化路径
   （直线/分支合流/固定循环）整体移除，替换为构造器调用；孤立的
   `ast_ir_add_phi`、`ast_ir_straight_scan/emit`、分支辅助与
   `ast_ir_lower_cleanup` 系列删除，`ast_ir_control.yh` 只保留
   let 校验与标量赋值降低两个共用辅助。

## 过程中发现并修复的缺陷

- **臂遍历越界**：if 两臂最初把整条兄弟链交给语句降低，then 臂遍历越过
  块边界把 else 与后续语句一并降入同一块（`branch_local(true)` 得到 39
  而非 37）。修复为只传块内子语句链；else-if 分支传单语句。
- **发现趟值编号冲突**：独立 builder 的发现趟拷贝了主 builder 的值 ID，
  复合赋值的既有值检查 `previous < inst_count` 误判，导致全部含循环的
  函数回退。改为回滚式发现趟后在同一编号空间执行，问题消除。
- **发现趟 local_count 泄漏**：体内 `let` 使遍历计数残留，真实降低时
  绑定编号顺序校验失败（`loop_local_body` 回退）。回滚列表补充该计数。

## 验证

- `make` 零警告；`make test`：语法正例 66/66、反例 29/29、运行 63/63。
- 滚种子前 `make selfhost-native` 通过：12 个模块产物固定点一致、
  49 个源文件自解析、模块 17/17、项目验收 54/54。
- `irfront` 55 个 AST 函数上下文 53 个进入 SSA（仅全局赋值的 call_tick
  与含逻辑或的 unsigned_score 仍回退）：新增守卫 break（break 站点值与
  条件假边在退出块合流，`loop_break_guard(10)=3`、`(2)=1`）与 continue
  跳过迭代（continue 站点回填循环头 phi，`loop_skip_odd(5)=13`、
  `(2)=1`）；既有 51 个函数的形态全部由通用构造器覆盖并保持运行结果。
  汇编断言 `bl log_unit` 三次不变；`yh check` 仍为 0 个 IR 函数。
- 函数 IR 缓存精确失效断言改为按「修改函数 1 + 已知回退数」计期望，
  回退函数从不写缓存、每次构建计入 miss 的语义在断言注释中说明。
- 滚种子后 `make` 与 `make selfhost-native` 再次通过。
  Darwin arm64 种子 SHA-256：`96ef0e6c565de0accdf40b71a1748abb91a7c2e97c4d39d6f2fa9d70718be252`；
  根 `yh` SHA-256：`f02b0eac39467c4c09c37561fa65f84c157adec5c201c876149577d81ff22d82`。

## 性能

Apple M1 冻结 25 文件、13,338 行语料，各场景独立测量 20 轮，计入外部
汇编与链接（新种子 `96ef0e6c…`）。中位数/p95 为：无改动 42.4/48.5ms、
单函数修改 671.7/757.4ms、冷编 1890.7/2132.8ms；与上一轮在噪声范围内
持平，本切片不构成编译提速证明（冻结语料的修改点不含循环/分支函数）。
无改动 50ms 中位数目标保持达标，单函数 200ms 与冷编 1s 目标未达到；
单函数修改仍重建整个所属模块并外部汇编一次，冷编以外部汇编器为主。

## 边界

- `||`/`&&` 逻辑运算、switch、goto/label、for-in、无限循环与嵌套循环
  仍走旧发射路径（unsigned_score 因 `||` 保持回退）。
- 浮点、聚合/内存、间接/变参调用尚未接入 SSA。
- R2a/R2b 整体未完成：函数级 check/IR 缓存、真正线程池与性能目标继续实施。
