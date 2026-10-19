# macOS/ARM64 LLVM：联合体 HFA 与模块门回归修复（2026-10-19）

## 结论

F2-5 的 Apple 聚合 ABI 补齐了**联合体 HFA**分类；同时修掉继承 RS3b 改动留下的
按文件切分回归，本机三道门全部转绿，未滚种子。

## 联合体 HFA

- 现象：`union { f64 scalar; [2]f64 values; }` 在 C↔YH 互调中字段错位。
  `autoabi` 项目 C 调 YH 返回 44（= 30 + 第 14 项 `FloatUnion`），YH 侧再返回 16。
- 根因：`llvm_apple_hfa_walk` 只递归 `struct`/`array`，union 落到“≤16 字节整数
  直接聚合”分支，按 `x0/x1` 传参，而 Apple 要求这类全浮点联合体走 `v0/v1`。
- 修复（`compiler/backend/llvm_apple_abi.yh`）：
  - 分类器对 union 递归全部成员，要求同一浮点基型，元素数取**最宽成员**
    （成员内存重叠，不能求和）。
  - 参数恢复、返回值写回、结果还原三条递归路径同步支持 union，均沿最宽成员遍历。
  - 返回值写回失败不再被静默忽略（`out.failed`）。
- 测试：union HFA 并入 `tests/selfhost/llvm-darwin-abi-aggregate.{yh,c}`，
  与既有聚合用例共用 Clang 21.1.8 oracle 与 O0/O2 Mach-O 双向互调；
  oracle 比对把 `%union.X`/`%struct.X` 与字面量聚合归一为 aggregate。

## 继承 RS3b 回归（按文件切分汇编）

- 现象：`.build/asm/<tag>/<source>.s` 以 `29, sp` / `16` 开头，首个函数序言被切掉，
  5 个模块用例（`u1-extern-abs-module`、2 个 attribute 用例、2 个 inline 用例）失败。
- 根因：`ast_ir_shift_rows` 在 pass 1 被覆盖成 `P0(全部) + P1(前缀)`，文件起始偏移
  多推了 pass 0 的总位移。
- 修复（`compiler/ast/ast_ir.yh`）：入口位移与替换定位都改用 `P0(i) + P1(i)`。
  定位若沿用跨遍累计（pass 1 用 `P0 全部 + P1 前缀`），在 inline 函数声明于
  非 inline 函数之后时会把替换位置推过函数头，切掉后续函数序言。
  新增 `tests/modules/projects/inlineorder` 固化该顺序边界。
  模块验收 99/104 → 105/105。

## 模块验收脚本

- `backend_text_files` 改为 `rglob`：RS3b 后产物在 `<tag>/<source>.s` 子目录，
  顶层 `glob` 恒空会把断言误判成“后端未发射”。
- `u2-attribute-interface-invalidates-caller-ir` 的产物定位同时支持 legacy
  目录布局与 LLVM 的 `llvm/<tag>.ll`；控制流断言只取调用方函数体
  （文件尾 weak runtime helper 也含 `unreachable`）。
- Linux x64 syscall 用例在非 Linux 目标下只断言“目标门控拒绝”，不把跨目标的
  预期拒绝当后端缺陷。

## 门禁

| 门 | 结果 |
|---|---|
| `make test-llvm-darwin` | 通过（SDK/host/bridge/object/ABI/runtime/link） |
| `make test` | 通过：语法 78/78、反例 42/42、运行 346/347（1 个 Linux 专属跳过） |
| `make selfhost-native` | 通过：固定点 123 项一致、自解析、语料、模块项目 105/105 |
| LLVM/Darwin 模块验收 | O0 105/105、O2 105/105 |
| legacy 模块验收 | 105/105 |

未执行 `make seed`。
