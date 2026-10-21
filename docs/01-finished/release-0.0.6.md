# 0.0.6 — LL12：旧机器发射彻底退役

本版本完成 LL12：编译器不再包含任何旧 AArch64 机器发射实现，LLVM 是唯一代码生成后端。
`compiler/` 相对上一版净减 **6516 行**（38 个文件，+241 / −6757）。

## 破坏性变更

- **`--backend legacy` 移除**：CLI 只接受 `llvm`（`auto` 在受支持宿主等价于 `llvm`），
  传 `legacy` 直接报错退出（rc 2），不存在回退路径。
- **种子出库**：仓库删除 `bin/` 与 `.gitattributes`，不再使用 Git LFS；
  克隆后首次构建前执行 `make fetch-seed` 从本 Release 下载种子到被忽略的 `bin/`。
- **构建前置**：`make` 不再自带种子，需先 `make fetch-seed`（需要
  `GH_TOKEN`/`GITHUB_TOKEN` 与 `GITHUB_REPOSITORY=lalavender/x`，私有仓库必需）。

## 删除的实现

| 文件 | 行数 |
| --- | ---: |
| `gen/emit_arm64.yh` | 1227 |
| `gen/emit_runtime_memory.yh` | 555 |
| `backend/arm64.yh` | 441 |
| `backend/arm64_call.yh` | 115 |
| `gen/sem_cabi.yh` | 246 |
| `ast/ast_ir_cache.yh` / `inline` / `control` / `template` | 643 |

同时移除 `gen/buffer.yh` 的四缓冲原语（661→365）、`gen/state.yh` 的
`TaskCtx` 缓冲字段与 `c_em_suppress`、`c_backend`/`target_legacy_ready`、
旧 SSA 汇编替换链与运行期桩。

## 语义层剥离（行为不变，仅不再发指令）

`sem_expr` 1050→929、`sem_flow` 545→410、`sem_call_literal` 496→264、
`sem_decl` 314→234、`sem_value` 522→423；`parse_stmt` 768→647、
`parse_global_init` 1085→1004、`parse_expr` 2058→2015；`ct_ir_data` 181→119；
`cmd/driver` 418→322、`compile` 116→105、`module_worker` 544→405。
类型规则、常量折叠、诊断、AST 捕获与可达性判定全部保留。

## C ABI 与控制流

- C 函数参数/返回的寄存器与栈搬运由 LLVM lowering 承担；语义层只登记符号、
  `F_AGGPARAM` 事实与结果形态；C 函数不再受旧浮点参数上限约束（HFA 逐成员分类）。
- `if/for/for-in/switch/return/goto/break/continue` 不再发射标签与跳转；
  循环上下文、break 标记、`goto` 登记与诊断保留。

## 验证

- 静态：全仓机器发射原语调用 **0 处**（`em_frag/em_ins/em_put/em_push/em_lea_/...`）；
- 诊断等价：400 语料 `yh check` 快照逐片零差异；
- 本机 Darwin/ARM64：`make test` 348/349（1 平台跳过）、`make selfhost-native`
  固定点 + 自解析 + project 106/106；
- 干净构建：`rm -rf compiler/.build && make && make test && make selfhost-native` 全绿；
- CI：本 tag 触发 CircleCI 三端（Linux/AArch64、Linux/x86_64、Darwin/ARM64）
  完整测试与自举，资产取自各自 cc4 候选。

## 下载与使用

本 Release 资产：

- `yh-0.0.6-linux-arm64.tar.gz` / `.sha256`
- `yh-0.0.6-linux-x86_64.tar.gz` / `.sha256`
- `yh-0.0.6-darwin-arm64.tar.gz` / `.sha256`

本地取种子：

```bash
export GITHUB_REPOSITORY=lalavender/x
export GH_TOKEN=<有 repo 读权限的 token>
make fetch-seed     # 下载到 bin/（已 gitignore），并写 <seed>.sha256
make                # 冷编编译器
```

## 已知边界

- Linux 两端验证由本 tag 的 CI 承担（本机磁盘不足以准备 Linux LLVM SDK）。
- 种子不再入库；发布新版本请打 tag（CircleCI `release` workflow 会跑三端测试并发布）。
- 旧种子的 `--backend legacy` 语义不再可用；使用本版本前请先 `make fetch-seed` 换种子。
