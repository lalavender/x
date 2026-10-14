# LLVM LL2 受检快照与纯快照 lowering（2026-10-14/15）

本记录关闭 LL2 的两个前置切片：**受检前端/快照/模块 IR 的落地**与**纯快照 lowering**。
两者都在 `llvm` 业务分支上实现，主门与全部 LL2 专项门通过后一并提交。
LL2 的「LLVM 模式常驻」「IRModule 序列化与跨缓存身份」「R2b 契约对齐记录」仍未完成，
因此 LL2 整体保持未关闭，见 `docs/todo.md`。

## 背景与目标

旧路径的语义遍历与 ARM64 汇编发射叠在同一遍里：`em_*` 直接往 `.text/.data/.bss`
缓冲写机器文本，SSA 降低成功后再按函数替换旧片段。LLVM 后端无法与手写汇编共享
同一个输出缓冲，所以必须先做到：

1. 语义遍历能在一个**不产生任何旧汇编**的阶段里完成（受检前端）；
2. 语义结果能以**自有存储**的快照交出去（受检模块）；
3. 快照能降低成**纯 SSA 模块**（`ir.IRModule`），且不读 `GenState`、不回退旧发射器。

## 实现

### 1. 受检前端阶段（`compiler/gen/front_stage.yh`）

- `front_checked_begin/verify/end` 独立于 `c_check_only`，用 `GenState.c_front_checked`
  作为单一闸门；`em_put`/`dat_put`/`bss_put` 与 `em_copy_body` 在该阶段整体静默。
- 进入时拒绝「已有旧输出」或「阶段重复进入」，退出前核对 text/body/data/bss 四缓冲为零；
  校验失败保留禁发状态，不允许继续旧后端。
- `cmd/driver.yh` 的单文件 check 与 `cmd/module_worker.yh` 的模块 check 成对进出。
  `--stats` 新增 `legacy_bytes`（四缓冲长度之和）作为「零旧输出」的可判据。

### 2. 受检模块快照（`compiler/ast/checked_module.yh`、`checked_module_verify.yh`）

- `CheckedStorage` 深拷贝 AST（表达式/语句/边/绑定/模板/声明）、类型/字段/类型名、
  签名表、符号表、名字池、文件（含源码字节与 token/PDecl）、导入命名空间与字符串标签。
- 原 ID 在快照内继续指向同一行；不持有 `GenState`、旧输出或编译期对象指针；
  重复 release 安全，非法捕获不留部分对象（失败路径不写出参）。
- 类型闭包：`CheckedStorage`/`CheckedString` 在本文件声明，
  `CheckedFlow`/`CheckedLower` 在 `compiler/ast/checked_module_ctx.yh` 声明——
  模块要求「类型先声明后使用」且按文件名字典序编译，`checked_module_ctx.yh`
  必须排在 `checked_module.yh` 之后、`checked_module_lower.yh` 之前。

### 3. 模块级 IR（`compiler/ir/ssa_module_00_model.yh`、`_10_build.yh`、`_20_verify.yh`）

- 模块逻辑符号、类型（结构/联合/数组/切片/函数签名）、全局初始化目录、来源表与位置，
  全部由增建接口深拷贝；从完整 triple 推导目标键并核对指针位宽、字节序与布局。
- `ir_module_verify` 封闭模块：坏来源、未知名字、错 ABI/返回/参数、未闭合签名、
  未定义符号却有实体、重定位槽非零等一律拒绝；函数体内复用函数级 SSA verifier。

### 4. 纯快照 lowering（`compiler/ast/checked_module_lower.yh`）

`lower_module(unit, out)` 把受检快照降低为 `ir.IRModule`：0 成功、1 首片不支持
（带真实来源诊断）、-1 内部错误；失败释放候选且保持 `out` 零初始化。
首片覆盖：顺序 `let`、简单/复合赋值、表达式语句（直接调用）、`return`、
`if/else`（含 else-if 链）、条件循环 `for cond {}`、`break`/`continue`、
短路 `&&`/`||`、一元 `!`/`-`、转换、算术/位/比较、直接调用与常量。
循环沿用旧构造器的两趟协议：发现趟收集携带绑定与 continue/break 站点数，
真实趟据此预留 header/exit phi 输入；嵌套循环明确不支持。

**关键修复（本轮真实复现）**：`checked_lower_binding` 原先按 `binding.sym_id`
回查快照符号表，而 `scope_pop` 会把参数/局部槽位截断（`gen/symbols.yh`），
快照符号表天然不含这些行——`AstBinding.sym_id` 按设计只是「解析时符号槽，仅作诊断」。
改为只使用绑定自己的快照字段后，`inc(x) { return x + 1; }` 这类最普通的函数才可降低。
直接调用则保留符号槽防护：被调目标必须仍解析到**同名同型**的函数符号，
回收槽造成的身份错配一律拒绝，不按陈旧 `sym_id` 静默取名。

## 验收

### 命令与结果（WSL，`SEED=bin/yh-linux-arm64`，`YH_LINK=/nonexistent`）

| 门 | 命令 | 结果 |
| --- | --- | --- |
| 构建 | `make` | 退出 0，`[编译] lex/ir/backend/comptime/gen/ast/parse/main` |
| 完整测试 | `make test` | 退出 0：语法正例 78/78、反例 42/42；运行 307/307 |
| 主门 | `make selfhost-native` | 退出 0：固定点 cc3→cc4 共 24 个产物一致；cc4 自解析 82 文件；运行时/缓存/`check` 等专项门通过 |
| 项目验收 | `python3 tests/modules/build-check.py --compiler-path ./yh` | 退出 0：**100/100** |
| 目标边界 | `tests/selfhost/llvm-front-boundary.py` | 退出 0 |
| 受检前端零输出 | `tests/selfhost/llvm-front-output.py` | 退出 0（text/body/data/bss 为零，污染拒绝，退出后恢复） |
| 快照所有权 | `tests/selfhost/llvm-checked.py` | 退出 0（销毁原 arena 后仍可校验） |
| 模块 IR | `tests/selfhost/llvm-module.py` | 退出 0 |
| 纯快照 lowering | `tests/selfhost/llvm-lower.py` | 退出 0 |
| LLVM 语义探针 | `tests/selfhost/llvm-semantics.py` | 退出 0（8 个探针） |
| LLVM 文本发射 | `tests/selfhost/llvm-ir.py` | 退出 0（真实模块 → 静态桥 → x64 O0/O2 原生运行） |

### 纯快照 lowering 的观察值

`tests/selfhost/llvm-lower.py` 用测试专用前端（`llvmlower/fixture.yh`）把真实 `.yh`
走完前端、捕获快照、销毁原 arena，再执行 `ast.lower_module`：

- `input/scalar.yh`（5 个运行期函数，编译期函数不计入）：
  `lower-snapshot=ok functions=5 phis=2 calls=4`
  ——`arithmetic` 的 if/else 合流与 `loop` 的循环携带各产生一个 phi；4 个直接调用
  全部登记进模块符号表并由 verifier 核对签名。
- `input/pointer.yh`、`input/aggregate.yh`：`ast.lower_module` 返回 1，
  诊断带真实来源与被拒函数名（`.../input/pointer.yh:5:9: LLVM lowering pointer_body: ...`），
  且 `out` 保持零初始化（拒绝时不发布部分产物）。

### 常规项目用例

`tests/modules/build-check.py` 新增 `llvm-snapshot-lowering`（fixture `llvmlower`）：
构建 → scalar 统计断言（`functions=5`、`calls=4`、`phis` 非零）→
pointer/aggregate 拒绝断言（`lower-rejected=ok` + stderr 含 `.yh:` 与函数名），
与前一批 `llvm-front-zero-output`、`llvm-module-ownership`、`llvm-checked-snapshot`
一起进入常规项目验收。

## 未关闭的边界

- **LLVM 模式未常驻**：`--backend llvm`/`--target`/`-O0/-O2` 的 CLI 接入与模块 worker
  的 LLVM 分支未实现；check 侧的受检快照消费完即释放，不参与后续 lowering。
- **IRModule 序列化与缓存身份**：`IR_MODULE_VERSION` 只是内存内版本，
  跨缓存的身份键（目标/ABI/布局/编译器身份）尚未落地。
- **旧路径仍是默认**：`make`/`make test`/`make selfhost-native` 全部走旧 ARM64 发射；
  本片的 lowering 只由专项门与 fixture 消费，未接入生产驱动。
- **首片覆盖边界**：全局对象、聚合/指针/浮点、间接调用、变参、`switch`/`goto`/`for-in`
  一律明确拒绝（返回 1 并带来源），不做静默回退。
- **R2b 契约对齐**：任务私有上下文与真正线程池的硬门仍未汇合。
- 未滚种子；`bin/yh-linux-arm64` 与 `bin/yh` 保持原哈希。

## 相关文档

- [实施方案 LL2 小节](../02-plan/yh-LLVM后端替换实施方案.md)
- [LLVM 替换设计](../03-design/yh-LLVM后端替换设计.md)
- [LLVM 目标身份设计](../03-design/yh-LLVM目标身份设计.md)
- [LLVM 语义与 ABI 契约](../03-design/yh-LLVM语义与ABI契约.md)
