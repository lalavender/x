# yh 模块化方案交付报告

日期：2026-09-29。完成的是方案调查和文档交付，编译器重构尚未实施。

范围纠正：用户需要 Go 风格的语言模块与包。本次历史方案因误读撤回
执行清单；当前交付见 [Go 风格方案报告](yh-Go风格模块化方案交付报告.md)。

## 交付物

- [详细方案](../02-plan/yh-编译器模块化详细方案.md)：现状、路线比较、
  目标目录、状态与接口、ABI／输出边界、C 版整理、P0–P9 与测试矩阵。
- [ADR-0003](../adr/0003-yh编译器渐进模块化.md)：渐进模块化、状态归属、
  单一清单和 stage0 有限适配的提议决策。
- `docs/todo.md`：MOD-DOC 完成；MOD-P0–P9 保持待实施。
- `docs/finish.md`：实际工作、验证与未执行范围。

## 实际调查与验证

| 命令／方法 | 结果 | 证据 |
| --- | --- | --- |
| rg、源码与行数调查 | C ONE_SOURCE 的 static 共享；自举状态／生成／ABI 混杂；调查起点自举源码 8,678 行 | 方案 §2；源码 |
| `make` | 成功，当前 all 产物已最新，无新编译 | `tmp/modularization/make.log` |
| `make test` | ANTLR 66/66 + 29/29；编译器语法 66/66 + 29/29；Darwin run 44/44、fail 12/12、pass 3/3 | `tmp/modularization/test.log` |
| `GRAPHIFY_OUT=tmp/modularization/graphify graphify update . --no-cluster` | 1,328 节点、4,283 边；`.yh` 跳过、12 个 C／头文件部分解析异常 | `tmp/modularization/graphify-update.log` |
| `GRAPHIFY_OUT=tmp/modularization/graphify graphify god-nodes --top 8 --json` | TCCState 233、tcc_error 105、CType 86 等候选枢纽 | `tmp/modularization/god-nodes.json` |
| yh 函数调用正则候选调查 | sem→parser，emitter→symbols 等逆向调用；不覆盖全部状态读写 | `tmp/modularization/yh-dependency-candidates.json` |
| 文档链接／围栏检查、`git diff --check` | 新增三份文档的本地链接存在、围栏闭合，无空白错误 | 本次交付校验 |

`tmp/` 下证据被 git 忽略，表中结果记录到本报告用于长期追溯；后续实施
要重新运行，不把本次临时产物当成正式阶段验收档案。

## 工作区变化与限制

调查开始时只有 todo 的既有修改；文档交付期间出现 `compiler/sem.yh`、
`compiler/emit_arm64.yh` 的 ABI 相关改动。本任务未编辑、回退或验收这些
代码，源码规模与调用候选统计采用调查起点口径。

本任务未修改编译器／测试源码，未新增 `.yh` 测试，未执行 `bootstrap`、
`g3` 或 `selfhost-native`，没有重新复现或修复 todo 记录的参数错位。
现有 59/59 本机回归不能证明该自举 ABI 问题已经解决。

方案第一步是 P0：针对参数位置和求值副作用建立能检出错误的测试，
确认修复并冻结可靠基线，再进入清单／状态／ABI 迁移。完整 AST／IR、
扩展平台、默认编译器切换和全面拆分 TCC 未在本次文档交付中完成。
