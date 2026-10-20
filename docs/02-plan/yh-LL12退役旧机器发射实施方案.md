# yh LL12：退役旧机器发射实施方案

日期：2026-10-21。状态：**规划完成，尚未开始实施**。
上游决策：[ADR-0014](../adr/0014-yh采用LLVM作为正式代码生成后端.md)；
阶段路线：[LLVM 后端替换实施方案](yh-LLVM后端替换实施方案.md) §LL12；
完成证据见 [finish.md](../finish.md) 与 [01-finished/](../01-finished/)。

## 1. 结论与现状

三个现有目标（linux-x86_64、linux-aarch64、darwin-arm64）都已默认 LLVM，
但**旧机器发射仍在 LLVM 生产路径上执行**，只是输出被抑制：

- 单文件入口 `llvm_emit_single_file` 先调 `mb_llvm_semantics()`，完整跑
  `parse_indexed_decls → parse_source_ct_* → parse_source_globals →
  parse_source_fns → check.verify_module`（`compiler/cmd/llvm_emit.yh`）。
- 模块 worker 在同一条路径上跑两遍 parse/sem 后才捕获受检快照
  （`compiler/cmd/module_worker.yh`）。
- 抑制点是 `em_put/dat_put/bss_put` 对 `c_front_checked` 的短路
  （`compiler/gen/buffer.yh`），所以 `gen/sem_*.yh` 里约 820 处 `em_*`
  调用照常执行、结果丢弃；`llvm-front-output.py` 的 `legacy_bytes=0`
  证明的是「输出为零」，不是「代码不在路径上」。

因此本阶段不是「删死代码」，而是先把语义层与机器发射解耦，再删除发射器。
它与 Nanopass 的 NP3（受检函数/Core 契约与 lowering 解耦）同源，NP3 并入本阶段。

## 2. 目标终态（验收定义）

1. `compiler/` 内不再有生产的 AArch64 指令/汇编文本发射：`gen/emit_arm64.yh`、
   `gen/emit_runtime_memory.yh`、`backend/arm64.yh`、`backend/arm64_call.yh`
   删除；`em_*`/`dat_*`/`bss_*` 原语与四输出缓冲删除。
2. 语义层只做类型规则、编译期求值、诊断、符号/接口与 AST 捕获，不持有
   寄存器/值栈/栈帧等目标状态。
3. `--backend` 只剩一个取值或整体移除；`c_backend` 字段消失；无
   `target_legacy_ready` 与「旧后端仅 AArch64」诊断。
4. LLVM 是唯一生产代码生成；`--emit-asm` 保留为「LLVM 汇编文本」语义。
5. 三平台 `make test`、`make selfhost-native`、LLVM 专项门全绿；新种子可
   冷编下一代源码。

明确不做：不重命名 `.s.i`/`.s.ct` 接口与快照文件、不改 `.build/asm` 到
`.build/targets` 之外的缓存布局、不删除历史种子与 Git 历史、不动
`--legacy-system`（R3 的隐式 system 兼容开关，与后端无关）。

## 3. 分片

每片独立可验收、可暂停；每片结束跑本平台 `make test` 与
`make selfhost-native`，跨平台门交 CI。

### LL12-0 基线冻结与消费者普查（纯文档，2026-10-21 完成）

- 产出 [旧发射消费者普查](yh-LL12旧发射消费者普查-2026-10-21.md)：按文件/函数
  统计 `em_*`、`dat_*`、`bss_put*`、四缓冲、`c_backend`、`arm64_`、`ast_ir_*`
  等 2669 处引用，剔除两类误报（`ast_ir_b_*` 共享 builder、`bss_n/bss_symbols`
  快照字段）。
- 冻结 legacy/LLVM 产物形态：hello 可执行文件 50,672/50,256 B，legacy `.s`
  234 行、LLVM `.s` 584 行（Darwin/arm64）。
- 验收：普查表覆盖全部命中并给出分片修正；本文件 C1/C2/C3 已按普查修订。

### LL12-1 语义纯化（最大片）

- 先把「只语义」变成唯一模式：以 `c_compile == 0` + `c_em_suppress`
  （`gen/sem_expr.yh`、`compiler/parse/parse_decl.yh`）为雏形，逐文件把
  混合函数拆成 `sem_*`（类型/值类别/诊断/CT）与 `emit_*`（发射）两段。
- 按普查（2669 处）排序处理：
  1. `gen/sem_expr`（160）、`sem_flow`（161）、`sem_call_literal`（92）、
     `sem_cabi`（76）、`sem_value`（35）、`sem_decl`（25），合计 549 处；
  2. `parse_global_init`（50）、`parse_stmt`（52）、`parse_expr`（37）等
     合计 143 处——全局/字面量/控制流在解析期直接发射；
  3. `comptime/ct_ir_data`（25）等 36 处——CT 常量经 `em_data_scalar` 写
     `.data`，改为进入受检快照/模块 IR；
  4. `gen/symbols.yh` 的 `em_emit_linux_syscall_stub` 等隐藏入口。
- 值表示替换：`c_res_is_addr`、`c_spill_reg`、值栈、`c_in_body`、
  `tn_lbl_*` 等目标相关状态换成目标无关的「值类别/临时」抽象；LLVM 路径
  继续只消费 AST 快照。
- 每片验收：`python3 tools/ll12-diagnostic-snapshot.py` 与基线零差异
  （400 个语法/运行语料、175 个预期失败；基线 `tmp/ll12/diag-baseline.json`），
  且 `make selfhost-native` 固定点不变。基线在改动前生成，改后重跑比对。

风险：诊断时机改变（现求值与发射同遍）；CT 求值依赖发射顺序；需逐函数
对照，不以整文件重写代替。

### LL12-2 删除发射器与四缓冲

- 删除 `gen/emit_arm64.yh`、`gen/emit_runtime_memory.yh`、`backend/arm64.yh`、
  `backend/arm64_call.yh`；删除 `gen/buffer.yh` 的 `em_*/dat_*/bss_put*` 与
  `flush_output`；清理 `gen/state.yh` 的 `TaskCtx` 旧字段与四缓冲指针。
  注意保留快照字段 `bss_n`/`bss_symbols`，不要按名字误删。
- 入口同步：`cmd/compile.yh` 的 `.bss`/运行期桩段（**2026-10-21 已删**，
  函数只留两遍语义/CT/布局供 `yh check`）、`cmd/module_worker.yh`
  的按文件 `.s` 发射与桩对象、`cmd/module_build.yh` 的 `.build/asm` 分支、
  `cmd/link_cache.yh` 的 `.s` 对象清单与后端位。
- 验收：`rg 'em_|dat_|bss_|o_out|o_body|flush_output' compiler/` 无生产
  消费者；三平台单文件/项目/自举全绿；种子暂不滚。

### LL12-3 删除旧 SSA 替换链

- **先切出共享 builder**：`ast_ir_b_*`（390 处，其中 `module_snapshot_lower`
  用 220 处）是 LLVM 快照 lowering 的 IR 构造层，必须保留（可留在
  `ast_ir_build.yh` 或拆成独立文件），不属于旧链。
- 删除旧编排与缓存：`ast_ir_lower_module`/`ast_ir_lower_function`/
  `ast_ir_expr_supported`、`ast_ir_cache_*`、`ast_ir_inline_*`、
  `ast_ir_template`、`ast_ir_call` 的旧部分（合计约 1.4k 行）；
  `ast_ir_cache` 的缓存键设计在 RS2 定稿前保留只读参考。
- `ir/ssa.yh` 只删旧构建/发射衔接；保留 `IRFunction/IRInst/IRBlock` 数据模型与
  `ir_verify`/`ir_find_value_type`（LLVM 的 `IRModule.body` 与
  `ssa_module_20_verify` 复用）。`ir/ssa_inline`、`ir/ssa_serialize`、
  `ir/ssa_call` 中仅 legacy 的部分删除，删除前确认 RS2 是否复用其缓存包络。
- 验收：无 `ast_ir_lower_*`/`ast_ir_cache_*`/`ast_ir_inline_*` 外部引用；
  `module_snapshot_lower` 仍能构建；LLVM 模块 IR 序列化/校验门不变。

### LL12-4 入口与开关收敛

- **2026-10-21 已完成首片**：`--backend legacy` 在 `cmd/driver.yh` 明确拒绝
  （提示 LL12 已退役，rc 2）；`--backend llvm` 保留为兼容 no-op。
- **2026-10-21 已完成第二片**：删除 driver 的 `run_emit_asm_to`/
  `drv_write_asm` 与临时 `.yh-tmp.s` 路径，`-o` 直接走 `drv_compile_file`
  （LLVM）；`--emit-asm` 只保留 LLVM 分支；usage 去掉「旧后端仅 AArch64」
  （driver 418→322 行）。
- 删除 `c_backend`（`gen/state.yh`、`cmd/driver.yh`、`cmd/module_build.yh`、
  `cmd/link_cache.yh`、`cmd/module_worker.yh`、`cmd/darwin_link.yh` 全部引用）。
- 删除 `target_legacy_ready` 与 `-target linux` 旧别名里的 AArch64 隐含语义；
  目标校验统一走 LLVM 目标身份。
- 更新 `--help`（`cmd/driver.yh` 的「旧后端仅 AArch64」）、
  `compiler/README.md` 模块表与源码注释中的旧后端说明。
- 验收：无 `--backend legacy` 可用路径；错误信息明确指向 LLVM。

### LL12-5 门禁、种子与文档迁移

| 文件 | 迁移 |
| --- | --- |
| `tests/selfhost/runtime-memory.py` | 删除 legacy ARM64 汇编契约段，运行时契约由 `llvm-linux-arm64.py` 承担 |
| `tests/selfhost/native-selfhost.py` | 删除 `transition_legacy`、`expected_artifacts` 与 `--backend legacy` |
| `tests/selfhost/llvm-darwin-selfhost.py` | A 代改为种子直接以 LLVM 编译，不再有 legacy 过渡代 |
| `tests/selfhost/llvm-darwin-target.py` | 删除 `legacy-build`/`legacy-run` 用例 |
| `tests/selfhost/llvm-front-output.py` | `legacy_bytes` 字段消失，改为断言无发射器构建 |
| `tests/bench/run_all.sh` | 删除 7 处 legacy 基线，保留冻结数据引用 |
| `tests/modules/build-check.py` | 移除 `--backend legacy` 分支与 legacy 产物布局断言 |
| `Makefile` | 删除无 LLVM_HOST 宿主的 `else` 分支；`MODCHECK_FLAGS` 不再需要 |
| `tools/seed-build.py` | 删除 `--backend legacy` 入口 |
| `tests/yh-run/check.py` | 删除 `asm-symbols-safe` 指令与检查 |

- 种子：确认入库两代种子（`bin/yh-darwin-arm64`、`bin/yh-linux-arm64`）
  可冷编删除后的源码；`make seed`/`fetch-seed` 对更老的无桥种子给出明确
  「请先升级种子」诊断。滚种子后记录体积与哈希。
- 文档：`AGENTS.md` 的 LL12/退役表述、`docs/03-design/yh-LLVM后端替换设计.md`、
  `docs/02-plan/yh-Nanopass风格优化架构实施方案.md`（NP3 标记并入）、
  `docs/adr/0014-*`（补退役结果）、`docs/todo.md` 与 `docs/finish.md`。
- 验收：`make test`、`make selfhost-native`、三平台 LLVM 专项门全绿；
  `rg 'legacy|旧后端|arm64\.yh' compiler/` 只剩历史注释或零命中。

## 4. 验收矩阵

| 检查 | 命令/证据 |
| --- | --- |
| 无发射器消费者 | `rg` 普查表 + 编译通过 + 固定点 |
| 语义等价 | 「纯语义 vs 语义+发射」诊断逐条对照脚本（LL12-1 新增） |
| 三平台 | Linux/arm64、Linux/x64、Darwin/arm64 的 `make test`/`selfhost-native` |
| 隔离环境 | `make llvm-isolation`（无 LLVM 动态依赖、无旁车） |
| 种子 | 旧一代种子冷编新源码；新种子冷编下一代 |
| 兼容诊断 | `--backend legacy`、老种子、x64 legacy 目标明确报错 |

## 5. 依赖与待决

- 技术前置：无（与 R2b 的 RS2/RS3 并行，互不阻塞）。
- 口径待决：启动条件按本文件与替换方案（x64 首期 + F1 回归已达成），
  还是继续等 LL11 的 R2b/性能硬门；`--backend legacy` 是一刀切还是保留
  一个版本期的明确报错。两项需用户拍板后写入主分支的全局 todo。
