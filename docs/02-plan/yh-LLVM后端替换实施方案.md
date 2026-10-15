# yh LLVM 后端替换实施方案

> **执行者说明：**用户已授权制定计划、开始实施并逐阶段提交。使用
> 2026-10-14 用户进一步明确授权多 agent 并行开发；独立源码切片并行实施，
> 完整验收、共享文档与 Git 阶段提交由主 agent 统一执行。
> 只有勾选并附验证证据的阶段已实现；生产默认和种子在完整验收前保持旧路径。

2026-10-14 顺序修订：用户确认 Linux/x86_64 优先，目标为本机 WSL 原生验证；此处 x86 指 64 位 x86。

**Goal：**以 LLVM 替换 yh 的生产代码生成，先完成 Linux/x86_64 的语义、运行时、宿主桥和原生自举闭环，再接六格平台矩阵。

**Architecture：**保留 yh 语义/check、编译期执行和受检 IR；解除旧 ARM64 汇编预发射，
通过模块级 LLVM 文本和编译器内嵌 LLVM 静态库生成对象。过渡期分开构建新旧可执行程序，
LLVM 模式严格拒绝回退，候选完整验收后切换默认并退役旧代码生成。

**Tech Stack：**旧种子可编译的 `.yh`、LLVM 21.1.8 静态 SDK + 薄 C ABI 桥（链接阶段见 LL9L 内嵌 lld）、Python 门禁、Linux/x86_64 ELF；
Windows 宿主在 WSL 原生构建与验证，ARM64 种子和 qemu 仅用于启动/旧基线。

**Spec：**[替换设计](../03-design/yh-LLVM后端替换设计.md)。先读
[问题清单](yh-LLVM后端替换问题清单.md)，与 [ADR-0014](../adr/0014-yh采用LLVM作为正式代码生成后端.md) 一起评审。

## 全局约束

- 用户源码仍只使用 `.yh` 后缀，不新增语言功能作为迁移前提。
- 首期平台为 Linux/x86_64（64 位 x86），目标 triple 为 `x86_64-unknown-linux-gnu`；非 Linux 目标不作为日常改动的回归前置。
- 首期 LLVM 固定为 21.1.8，SDK 下载与静态链接身份入库锁定；正常编译不依赖系统 LLVM，clang/llvm-as/opt 只用于开发差分。
- LLVM 模式禁止自动回退旧后端；不支持的形态给出来源诊断并停止发布产物。
- 开发默认 O0、发布显式 O2；初期禁止 fast-math 和未经证明的语义属性，LTO 后置。
- 普通 AOT 程序不依赖 LLVM 运行；编译依赖与 OS/运行时依赖分别披露。
- 维持现行运行时禁止导入 malloc/free/memcpy/strlen/printf 的门，不用放宽断言完成迁移。
- 所有候选、探针和临时日志放 `tmp/llvm-migration/`，未验收候选不覆盖 bin/ 种子。
- 代码变化先加 `.yh` 用例并运行 `make`；阶段关闭执行 `make test` 和 `make selfhost-native`。
- 默认正式切换不得降低 R2b 已确认的任务私有状态、线程池、缓存/并发/确定性硬门。

## 审查重点

| 容易遗漏的输入/条件 | 必须期待的行为 | 归属任务 |
| --- | --- | --- |
| 源类型为 i32 的移位量 32/64 或最小负数/-1 | 依据提升/计算/截断契约，不套用 LLVM UB | LL1、LL3 |
| 无 LLVM 工具时运行 check；显式写错 triple | check 正常完成语义检查；未知目标明确拒绝 | LL2、LL9 |
| 缓存中夹入另一个后端/目标/ABI 的对象，或工具版本变但路径不变 | 可靠失效，不链接陈旧对象 | LL9 |
| 内存 helper 自身被 O2 改成递归 libcall | 自包含运行时仍运行正确，无未解析或递归入口 | LL8a、LL8b |
| 同项目并发、晚到的私有函数错误、路径含空格/中文 | 不发布失败接口/产物，路径原样传递，诊断顺序确定 | LL9、LL10 / R2b |
| x64 对象遇到 PATH 中的 ARM64 gcc 包装器，或候选 B 仍是 ARM64 | 原生工具不走 crossbin；检查 ELF machine=62，B/C/D 直接原生运行 | LL0、LL3、LL9、LL10 |
| 内嵌 lld 后的全目标初始化、体积与重入 | 按裁剪决策只留 X86/AArch64 或明确接受全量；lld 可重入，失败不发布产物 | LL9L |

## 0. 范围、依赖与文件安排

这份计划详细定义 Linux/x86_64 的实施切片，其他平台在末尾给出有门槛的子项目路线；
不把 Windows OS 桥、完整线程池或 SDK 分发伪装成一个几行的后端任务。
R2b 的既有子项目仍独立推进，其硬门在 LL10 默认正式切换前汇合。

建议执行顺序：

`LL0 → LL0E → LL1 → LL2 → LL3 → LL8a → LL5 → LL4 → LL6 → LL7 → LL8b → LL9 → LL9L → LL10 → LL11 → F1 → LL12`。

从 LL3 起生成的程序就在 WSL x86_64 原生运行；此时启动编译器 A 仍可能经 qemu。
LL10 才要求编译器 B/C/D 自身均为原生 x64。F1 的 Linux/AArch64 回归只阻挡旧后端退役，
不阻挡 LL11 的本机原生默认路径和独立 x64 种子。

LL8 分两片是为了避免“内存测试需要 helper，而 helper 又要等全语言 lowering”的环。
LL8a 用 `.yh` 编写的 LLVM 发射代码提供基本 helper 的 IR；LL8b 在内存/调用覆盖后迁移完整运行时。
不将旧模块汇编塞进 LLVM module asm，也不混合两个版本的 yh ABI 对象。

| 范围 | 创建/修改的主要文件 | 职责 |
| --- | --- | --- |
| 受检阶段 | 修改 `compiler/ast/ast_function.yh`、`ast_ir*.yh`；新建 `ast/checked_module.yh` | 语义快照、所有权与 lowering 输入 |
| 目标模型 | 修改 `compiler/gen/target.yh`、`model.yh`、`state.yh`、`comptime/ct_target.yh` | 宿主/目标、triple/layout/ABI 身份 |
| 首期 x64 OS 桥 | 修改 `compiler/cmd/project_dir.linux.yh`、`clock.linux.yh`、`process.yh`、prelude 和 LLVM runtime | x64 syscall/目录/时钟/内存/进程，旧种子可编译的架构选择 |
| 模块/内存 IR | 新建 `compiler/ir/module.yh`、`ssa_memory.yh`；修改 `ssa.yh`、`ssa_call.yh`、`ssa_serialize.yh` | 模块声明、数据、存储/调用及验证/序列化 |
| LLVM 输出 | 新建 `compiler/backend/llvm_module.yh`、`llvm_scalar.yh`、`llvm_memory.yh`、`llvm_call.yh`、`llvm_runtime.yh` | 文本、来源映射、各类操作与 helper |
| LLVM 链接 | 新建 `compiler/llvm/lld_bridge.cpp`、`compiler/backend/llvm_lld.yh`；修改 `cmd/link_cache.yh`、`driver.yh`、SDK 脚本 | 进程内 lld、CRT/库路径、回落与身份 |
| CLI/对象/缓存 | 新建 `compiler/cmd/llvm_toolchain.yh`；修改 `driver.yh`、`compile.yh`、`module_worker.yh`、`module_build.yh`、`link_cache.yh`、`build_scheduler.yh` | 解析、argv、产物与事务 |
| 语言接口 | 修改 `compiler/parse/iface.yh`、`iface_ct.yh` 及缓存键 | 目标/ABI/布局版本身份，保留后缀 |
| 验收 | 新建下述 `.yh` fixture 和 `tests/selfhost/llvm-*.py`；修改现有 run/modules/selfhost 脚本 | 覆盖、语义、缓存、运行时和自举 |

新文件按完整函数边界和真实职责拆分；不要为了达到行数目标填充代码。
原文件接近 1000 行时只拆本任务需要触及的部分，中文详细注释说明结构和函数契约。
以上新文件名称在实施前检查是否已被其他工作使用；若发生冲突，先更新这份映射。

### 当前并行安排（2026-10-14）

| 执行者 | 可独立推进的工作 | 文件归属与验收边界 |
| --- | --- | --- |
| 主 agent | 前端停止预发旧汇编、模块 worker 接入、最终集成 | `gen/state.yh`、`gen/buffer.yh`、`cmd/`；统一运行完整主门与显式文件提交 |
| target_review | LL2-T 目标模型只读审查；审查后转模块 IR | 审查不修改工作区；后续独占新增 `ir/ssa_module*.yh` 与对应测试 |
| checked_snapshot | CheckedModule 真实受检快照与生命周期测试 | 新增 `ast/checked_module*.yh`、`llvmchecked` fixture、`llvm-checked.py` |
| arm_sdk | ARM64 固定静态 SDK、交叉桥接和无系统 LLVM 验收 | `tools/llvm-sdk.py`、`vendor/llvm/`、SDK 专项测试 |

快照和 SDK 无前后依赖，可以立即并行；模块 IR 的消费接口在快照 API 稳定后汇合。
LLVM lowering、驱动接入与原生自举仍按输入依赖推进，不能用并行完成的元数据或桥接
测试代替全编译链验收。各 agent 在自己的 `tmp/llvm-migration/` 子目录构建隔离候选，
不同时改写根 `yh`、`compiler/.build`、种子或 Git 索引；新增归属外的修改先协调。
模块 IR 新文件按 `ssa_module_00_model/10_build/20_verify.yh` 排在已有 `ssa.yh` 后，
以满足旧种子“类型先声明后使用”的顺序约束，直接保存 typed IRFunction。

## 1. 每个代码切片的共同验收与提交

- [ ] 先新增对应 `.yh` 行为用例，记录旧路径/新路径的预期；新能力的测试先失败再实现。
- [ ] 实现最小变化；已有 bug 先复现再修复，不为未证实风险凭空修改语义。
- [ ] 在 WSL 运行 `make`、对应定向检查；构造后/缓存读回/输出前执行 verifier。
- [ ] 阶段关闭跑现有 `make test`、`make selfhost-native`，另跑该阶段 LLVM 专项门。
- [ ] 更新本计划复选框、问题状态和 docs/finish.md；只提交本切片自己的改动。
  本次启动工作区干净、现有分支为 llvm；显式按文件暂存，禁止把无关差异混入提交。

现行旧后端基线/启动 A 的命令（先确认 crossbin/gcc 存在且指向交叉 gcc，环境仅限这些调用）：

```bash
PATH="$PWD/tmp/boot/crossbin:$PATH" SEED=bin/yh-linux-arm64 make
PATH="$PWD/tmp/boot/crossbin:$PATH" SEED=bin/yh-linux-arm64 make test
PATH="$PWD/tmp/boot/crossbin:$PATH" SEED=bin/yh-linux-arm64 make selfhost-native
```

LLVM 模式的 runner 在 LL9 接入前使用定向 fixture 的独立候选和目录；不能因旧模式全绿
声称新模式全量通过。下文 `--backend`、`--target`、`-O0/-O2` 和新脚本均属于未来实现。
原生 LLVM 阶段明确选择 `x86_64-unknown-linux-gnu`，使用解析后的原生 clang/链接驱动
绝对路径，不能继承 ARM64 gcc 包装器作为最终链接器。x64 种子尚未入库时，启动脚本
显式用 ARM64 种子生成 A，不能假设 `bin/yh-linux-x64` 已存在。

## LL0：冻结基线、依赖与路线（LLVM-03、11、12、13、15）

**文件：**修改 `compiler/cmd/module_build.yh`、`ast/ast_ir.yh`、`backend/arm64.yh`；
新建 `tests/selfhost/llvm-baseline.py`、`tests/modules/projects/llvmcoverage/project.toml`、
`tests/modules/projects/llvmcoverage/main/main.yh`；复用 `tools/compiler-performance.py`。

**接口：**消费现有 --stats；产生 checked/lowered/backend_emitted/fallback 计数与稳定原因目录，
统计 schema 记录在 `tmp/llvm-migration/baseline/coverage.json`，历史字段不悄悄改变含义。

- [x] 核对工具绝对路径/版本、ARM64 种子哈希、当前源码快照、CPU；
  分开记录旧 qemu/交叉工具与原生 x64 LLVM/链接工具。
- [x] 用最小 IR 生成并链接 x86_64 ELF64，检查 machine=62、直接运行退出 0；
  原生工具调用不能经过 crossbin/gcc，这个工具链探针不冒充 yh 支持。
- [x] llvmcoverage fixture 同时含一个受支持整数函数和一个全局赋值函数；
  测试断言 `checked == lowered + rejected`、`emitted <= lowered`，并区分“SSA 成功但未发射”。
- [x] 增加实际发射及拒绝原因计数，重测 compiler/；生成一次基线报告，不重复引用 991/22 作实时值。
- [x] 冻结冷编/无改动/单函数修改负载；采样至少 20 轮，保存原始样本和中位数/p95/RSS。
- [x] 评审 ADR-0014 的 LLVM 正式依赖、旧工具链任务对接和运行时约束，记录设计政策；
  不在本轮文档交付时将其自动标为已采纳。

**验证：**`python3 tests/selfhost/llvm-baseline.py --compiler-path ./yh`；
报告包含环境、实用覆盖/原因和性能；上述计数关系成立，旧后端行为/固定点不变。

2026-10-14 LL0 已验收：运行期受检 923、SSA 验证/实际发射各 22、前端拒绝/回退各 901；
comptime 不计入覆盖分母。每类性能场景 20 个原始样本，报告见
tmp/llvm-migration/ll0-performance.json；R0 语料不再兼容已删除的字段 pub，
本轮另行冻结当前源码到 tmp/llvm-migration/baseline/performance-corpus/，不改历史语料。
采样环境为 WSL/DrvFS + ARM64 qemu，SDK 链接研究同期运行；数据只作为本环境启动基线，
正式性能对照须在 LL11 无其他重负载时重测，不能冒充 ARM64 原生数据。

## LL0E：固定 SDK 与内嵌 LLVM 桥

**文件：**新增 `vendor/llvm/sdk.lock.json`、`vendor/llvm/README.md`、
`compiler/llvm/bridge.h`、`compiler/llvm/bridge.c`、`tools/llvm-sdk.py`、
`tests/selfhost/llvm-embedded.py` 和 `tests/selfhost/llvm-embedded-probe.yh`。
桥放在 compiler/llvm，C 文件不参与旧种子 yh 项目扫描；不恢复 stage0。

**接口：**`yh_llvm_version() *char` 返回内置版本；
`yh_llvm_emit(text *char, length u64, triple *char, opt_level int, kind int,
output *char, diagnostic *char, capacity u64) int` 返回 0/-1；
kind=0 对象、1 汇编，opt_level=0/2，缓冲归调用方所有。
每次调用创建私有 context/module/target machine；诊断失败不发布目标文件。

- [x] 先加内嵌桥验收：无 LLVM 工具 PATH、对象/汇编生成、O0/O2、坏 IR、坏 target、
  verifier 失败、目标输出写失败，正常/失败重复调用；未实现桥时明确失败。
- [x] 固定 Linux/x86_64 SDK 21.1.8 下载地址、SHA-256、静态组件依赖及许可；
  解包到 tmp，不调用系统 llvm-config，不装系统 LLVM，不提交解包临时文件。
- [x] C ABI 桥只调用 LLVM C API；输入验证、前后 verifier、generic CPU、静态重定位，
  目标只初始化 X86/AArch64；诊断有界并释放所有自有对象。
- [x] 使用固定 SDK 静态链接测试宿主，readelf NEEDED 不含 LLVM；在无系统 LLVM 的
  隔离根目录生成对象和汇编。此宿主是桥测试工具，不能声称 yh 已完成嵌入。
- [x] ARM64 启动 SDK 前置片：固定 ARM LLVM/zlib/zstd 包与许可、显式 --host 交叉链，
  qemu O0/O2 两架构对象/汇编及全新 chroot 验收；真实 `.yh` C ABI 调用者静态链接
  桥、生成 x64 对象并在 WSL 原生执行通过。普通编译器 pipeline 尚未接入。
- [x] 运行 make、make test、make selfhost-native，记录桥门与旧门证据并提交。

**验证：**`python3 tests/selfhost/llvm-embedded.py`；独立测试宿主无 LLVM 动态依赖，
对象 ELF machine=62/183，x64 最小 IR 原生运行 exit 0。LL3 接入 yh 调用，
LL10 再把静态桥/SDK 与连续自编链接绑定，LL11 完成最终交付的无系统 LLVM 门。

2026-10-14 LL0E 已验收：固定 SDK 哈希正确，坏哈希拒绝；薄桥独立宿主无 LLVM 动态依赖，
无 LLVM 工具 PATH 的 O0/O2 对象/汇编/原生 x64 运行和 8 类拒绝门通过。
WSL root chroot 仅放测试宿主、输入与 OS 动态库，O2 生成对象退出 0。
链接采用同一 GNU 链接器和匿名 memfd 输入/输出，消除 DrvFS 细碎 IO 的超时，
不增加系统 LLVM/lld 依赖。源码级 `.yh` 桥签名经当前编译器检查通过。
make / make test / make selfhost-native 全绿；普通编译器仍是旧 ARM64 路径。
ARM64 SDK 后续并行片已独立验收，x64 原流程复验通过；两套隔离门均改为每轮新空根。
证据为 ll0e-arm-final-fresh 与 ll0e-x64-final-fresh 日志/退出码 0。

## LL1：锁定边界语义与调用政策（LLVM-01、05）

**文件：**新增 `tests/yh-run/run/llvm-integer-boundaries.yh`、`llvm-bool-memory.yh`、
`llvm-float-boundaries.yh`，按真实发现新增 fail 用例；修改相关语义设计文档。
只有复现 bug 后才修改 `compiler/gen/sem_expr.yh`、`ir/ssa.yh` 或旧后端。

**接口：**产生问题清单 §3 的“输入/源类型/中间宽度/观察值/规则/证据”矩阵；
LL3 与 LL7 只使用已锁定条目。

- [x] 为清单中的移位、除模、转换、bool、浮点、内存、效果和未初始化八类建立可运行 `.yh` 探针。
- [x] 先记录常量/旧动态/SSA 的输出和诊断；探针本身不强行制造失败，不断言栈垃圾具体值。
- [x] 对确实违反现行规则的差异建立红绿回归并修复；语义尚未规定的条目单独评审政策。
- [x] ABI 文档锁定 `yh-llvm-v1` 的副本/结果缓冲规则及 C ABI 核对方法；
  不要求新机器 ABI 与旧对象兼容，统一以独立项目重编迁移。
- [x] 执行定向测试和全量旧门，填写可迁移指令集合；未闭合条目禁止进入生产 LLVM 路径。

**验证：**`python3 tests/yh-run/check.py --compiler ./yh --filter llvm- --workdir tmp/llvm-migration/semantics`；
每个探针有已定义期望或明确的非生产观察状态，所有发现的 bug 单独通过完整门。

2026-10-14 LL1 已验收：SEM-01–07 与扩大覆盖发现的 CFG/AST 问题均有回归；
8 个单文件和项目探针通过，矩阵与 yh-llvm-v1 政策见语义与 ABI 契约。
make test / make selfhost-native 全绿（307/307、24 个固定点产物、71 文件自解析、
模块 18/18、项目 95/95）。实际 SSA 发射 bool 8、CFG 2、整数 11、一元 1、纯标量 1；
浮点与聚合主体仍走旧路径。此阶段锁定语义，不代替后续 LLVM O0/O2 和全覆盖门。

## LL2：受检输入、目标模型与阶段边界（LLVM-02、04、06、08、14、16）

**文件：**按 §0 的受检、目标、模块 IR、接口映射修改；新增
`tests/modules/projects/llvmtarget/project.toml`、`llvmtarget/main/main.yh`、
`tests/selfhost/llvm-front-boundary.py`，复用 irverify 的坏 IR 验收。
首批实现已在工作区落地（**未提交**）：`compiler/gen/front_stage.yh`、
`compiler/ast/checked_module.yh` + `checked_module_verify.yh`、
`compiler/ir/ssa_module_00_model.yh` / `ssa_module_10_build.yh` / `ssa_module_20_verify.yh`、
`tests/selfhost/llvm-front-output.py` / `llvm-checked.py` / `llvm-module.py` 与
fixture `llvmfront` / `llvmchecked` / `llvmmodule`；
`tests/modules/build-check.py` 增加对应三个常规项目用例，`cmd/module_build.yh`
的 `--stats` 增加 `legacy_bytes`。纯快照 lowering `compiler/ast/checked_module_lower.yh`
及其 `llvmlower` fixture、`tests/selfhost/llvm-lower.py` 归 LL3，仍在实现且未通过。

**接口：**实现设计 §3.3 的 TargetInfo、CheckedModule、IRModule 及 capture/release/verify 契约。
TargetInfo 至少保存完整 triple、OS、架构、ABI、指针位宽/字节序、layout 身份；
所有权测试锁定借用源快照和自有 IR 表的生命周期。

- [x] 添加未知 triple 拒绝、check 在 LLVM 工具缺失时成功、模块快照生命周期的失败测试。
  `llvm-front-boundary.py` 以空 PATH 跑 check、六个旧别名与目标源后缀筛选，并断言 check
  不发布后端产物；`llvm-checked.py` 与 `llvmchecked` 在销毁原 arena 后校验快照、
  重复释放、非法捕获清理与旧汇编区间无关。
- [x] 将目标选择从 c_dialect 分离，旧 -target 别名有明确映射；修 $if 和目标源文件筛选。
- [x] 在 qemu 环境验证缺省目标来自编译器构建身份，宿主 OS 桥不因输出 --target 改写；
  不能以 uname=x86_64 将 AArch64 进程的宿主 ABI 误判为 x86_64。
- [x] 定义启动 A 的 ARM64 宿主身份与生成 B 的 x64 构建身份；
  架构选择先用旧种子认识的 `$if arm64` / `$else`，避免新后缀/条件导致两个同名实现一起编入。
- [x] 语义结束时生成受检模块快照，受检前端不进入 em_*/dat_/bss_ 旧机器输出；
  保留旧路径的临时迁移开关，不改变 check 的合法语言集合。
  证据：`gen/front_stage.yh` 的 begin/verify/end 加 `gen/buffer.yh`、`gen/emit_arm64.yh`
  的写入闸门；`cmd/module_worker.yh` 在 check 语义结束处 capture→verify→release；
  `llvm-front-output.py` 断言真实项目 check 的全部 worker `legacy_bytes=0`；
  冻结验收树的语法/运行/模块/项目门全绿，未改变 check 接受的输入集合。
- [ ] 剩余：LLVM 模式仍未常驻——check 侧快照消费完即释放，没有 worker 持有快照直到 IR 交接；
  `lower_module` 已能纯快照降低并在专项门通过，但 em_* 机器输出尚未被 LLVM 后端取代
  （见 `cmd/module_worker.yh` 注释与 LL3/LL9）。
- [x] 建立模块逻辑符号、类型布局、全局初始化目录和来源记录；
  扩充 module verifier 与序列化版本，不把临时 type_id 直接当跨缓存身份。
  已完成：`ir/ssa_module_*` 提供符号/类型/全局初始化目录/来源记录与 `ir_module_verify`，
  `llvm-module.py` 通过（目标键、布局、重定位、函数 verifier、重复释放）；
  `ast/checked_module_lower.yh` 的 `lower_module` 已能把快照降低为 `ir.IRModule`
  （首片整数/布尔闭包），`llvm-lower.py` 通过（scalar `functions=5 phis=2 calls=4`，
  pointer/aggregate 带来源整模块拒绝）。
  仍缺：IRModule 序列化与其版本；`IR_MODULE_VERSION` 目前只是内存内版本，没有
  `ir_module_serialize`，跨缓存身份键未落。
- [x] 运行前端边界和旧固定点门；与 R2b 任务私有上下文契约对齐，记录未闭合的完整版本硬门。
  已完成：当前源码上 `make test selfhost-native` 与七个专项门实际退出 0：
  语法 78/78 与 42/42、运行 307/307、固定点 cc3→cc4 共 24 个产物一致、自解析 82 文件、
  模块 18/18、项目 100/100，另加 `llvm-front-boundary/llvm-front-output/llvm-checked/
  llvm-module/llvm-lower/llvm-semantics/llvm-ir` 全绿（日志 tmp/llvm-migration/ll2-full-*.log/.exit
  与 ll2-gate-*.log/.exit）。
  仍缺：R2b 任务私有上下文契约的对齐记录与未闭合完整版本硬门清单。

**验证：**`python3 tests/selfhost/llvm-front-boundary.py --compiler-path ./yh`；
check 不访问 LLVM 工具，LLVM 前端输出旧汇编计数为 0，目标/接口错配明确拒绝。

2026-10-15 现状：LL2 的四个切片——目标身份（LL2-T，提交 `c0cd89e`）、受检前端闸门、
受检快照与纯快照 lowering——全部在当前源码上验收并提交；`checked_module_lower.yh`
的关键根因是「按 `binding.sym_id` 回查快照符号表」，而 `scope_pop` 会截断参数/局部槽位，
改用绑定自己的快照字段后普通函数才可降低（直接调用仍保留同名同型符号槽防护）。
LL2 仍未关闭：LLVM 模式未常驻（`--backend/--target/-O0/-O2` 与 worker LLVM 分支未接入）、
IRModule 序列化与跨缓存身份未落、首片之外的形态明确拒绝而未补齐、R2b 契约对齐记录缺。
未滚种子。详见 [完成记录](01-finished/yh-LLVM-LL2受检快照与纯快照lowering-2026-10-15.md)。

## LL3：严格整数 LLVM 首片（LLVM-04、08、12）

**文件：**新增 `compiler/backend/llvm_module.yh`、`llvm_scalar.yh`、
`compiler/cmd/llvm_toolchain.yh`、`tests/modules/projects/llvmscalar/project.toml`、
`llvmscalar/main/main.yh`、`tests/selfhost/llvm-ir.py`；修改 driver/compile/module_worker。

**接口：**实现 llvm_emit_module/LLVMOutput/release；cmd 调用内嵌桥、生成对象并定位来源诊断。
实现 --backend、--target、--emit-llvm、-O0/-O2 的首片解析；新选项传至模块 worker。
对象/汇编调用 LL0E 薄桥，禁止调用外部 LLVM 工具；启动 A 的 ARM64 静态 SDK
必须在本片接入前准备并验收，不用 x64 SDK 混链到 ARM64 启动编译器。

- [x] llvmscalar 首片只用整数/布尔、分支/phi/固定调用，main 自校验后返回 0，
  不依赖 printf 或尚未迁移的运行时；旧候选应因新选项未实现而失败。
  证据：`tests/modules/projects/llvmscalar/main/main.yh` 自建模块并逐条校验；
  端到端单文件探针（`scalar.yh`、循环探针 A/B）均只用整数与直接调用。
- [x] 实现 PARAM→签名、CONST/CAST/算术/比较、CFG/phi、直接调用与 ret，
  针对 LL1 边界使用已验收 lowering，不加未经证明的属性。
  证据：`compiler/backend/llvm_scalar.yh`（llvm_promote/llvm_result/llvm_division/
  llvm_compare/llvm_switch 等）与 `ast/checked_module_lower.yh` 的语句/循环 lowering；
  `llvm-ir.py` 的 O0/O2 独立 oracle 通过。
- [x] 声明/定义集中发射、符号正确转义、来源图定位 LLVM 错误；
  unsupported 的 `.yh` 函数必须报位置且不发布对象，绝不调用 arm64_emit_replace。
  证据：`llvm_module.yh` 的 `llvm_emit_module`（llvm_quote/llvm_map/llvm_preflight）与
  `cmd/llvm_emit.yh` 的 `llvm_emit_reason`（按模块来源算行列）；
  `llvm-lower.py` 断言 pointer/aggregate 带来源整模块拒绝且不发布部分产物。
- [x] 增加同一程序经单文件与模块入口的等价检查；`--emit-asm` 用 LLVM 当前目标生成汇编。
  证据：`cmd/llvm_emit.yh` 的 `llvm_emit_single_file` 与 `cmd/module_worker.yh` 的
  `mb_llvm_emit_module` 共用 `lower_module` → `llvm_emit_module` → 桥；
  `scalar.yh` 单文件退出 13 与纯快照 lowering 门的 `functions=5 phis=2 calls=4` 一致；
  `--emit-asm` 发当前目标汇编文本到标准输出。
- [x] 验证 O0/O2 IR 和运行结果；计数 emitted 等于该 fixture 的受检函数数，fallback 为 0。
  证据：`llvm-ir.py` 覆盖 O0/O2 验证/对象/汇编与独立字面量 oracle；
  LLVM 模式下 worker 不进入旧 SSA 替换路径（`c_backend != 0` 分支），
  因此不存在 fallback 计数。
- [x] 首片目标显式为 x86_64-unknown-linux-gnu；检查对象和程序是 ELF64/EM_X86_64，
  测试程序在 WSL 直接运行，从本片开始提供本地原生行为验证。
  证据：`./yh --backend llvm --target x86_64-unknown-linux-gnu -O0 f.yh -o out` 产出的
  `out` 为 `ELF 64-bit LSB executable, x86-64`（readelf `Machine: Advanced Micro Devices X86-64`），
  原生运行退出码 13/3/63 与源码语义一致。

**验证：**`python3 tests/selfhost/llvm-ir.py --compiler-path ./yh --suite scalar`；
脚本分别执行 `llvm-as`、`opt -passes=verify -disable-output` 和候选 O0/O2 编译运行。

2026-10-15 现状：LL3 主体（CLI `--backend/--target/-O0/-O2/--emit-llvm`、内嵌桥绑定与
静态链入、单文件与项目 worker 的 LLVM 发射路径、纯快照 lowering 的块收尾与赋值返回协议
修复）已实现并通过全部门禁（`make`、`make test` 307/307、`llvm-lower.py`、`llvm-ir.py`
及其余 LLVM 专项门退出 0）。**未关闭**：损坏 `.s.ct` 触发 worker SIGSEGV 的回归未定位
（`build-check.py` 99/100，详见 docs/todo.md）、LLVM 模式未常驻、首片之外形态明确拒绝、
未滚种子。详见 [完成记录](01-finished/yh-LLVM-LL3命令行模式与对象发射-2026-10-15.md)。

## LL8a：先提供内存 helper（LLVM-07）

**文件：**新增 `compiler/backend/llvm_runtime.yh`、
`tests/yh-run/run/llvm-runtime-memory.yh`、`tests/selfhost/llvm-runtime.py`。

**接口：**提供目标 C 签名的 memcpy/memset/strlen 入口及独立低优化编译策略；
本片发射 helper 的 LLVM IR，不依赖尚未完成的 yh 聚合 lowering。

- [ ] 用 LLVM IR 验证/对象检查建立 helper 缺失和自递归的失败断言；
  `.yh` fixture 覆盖 0、1、7、8、16、31、32、4096 字节复制/清零及字符串边界。
- [ ] 以 `.yh` 发射代码实现最小 helper IR，源注释说明签名、效果、对齐和重叠契约。
- [ ] 检查 O0/O2 的 helper 对象定义、引用和反汇编；不依赖 freestanding 选项阻止 libcall。
- [ ] 对 runtimebytes 型自包含 fixture 检查 `nm -u` 为空，普通模块仍允许正常导入。
- [ ] 定向运行与旧门通过后，向 LL5 提供已定义的复制/清零实现。

**验证：**`python3 tests/selfhost/llvm-runtime.py --compiler-path ./yh --suite memory`；
边界自校验退出 0，helper 不调用自身、不留下未解析的内存辅助入口。

## LL4：逐切片补齐控制流（LLVM-03）

**文件：**修改 `compiler/ast/ast_ir_build.yh`、`ast_ir_control.yh`、`ast_ir_template.yh`、
`compiler/ir/ssa.yh`、LLVM 输出；新增 `tests/yh-run/run/llvm-control-flow.yh` 和相应负例。

**接口：**消费 CheckedModule；产生 verifier 可接受的 CFG/phi 或显式可变局部存储，
  来源顺序和效果不变；显式存储依赖先完成的 LL5。

- [ ] 按“嵌套循环与 break/continue → 无限循环 → switch → goto/label → for-in”逐行建用例。
- [ ] 每行先用 LLVM 编译触发 unsupported，再实现该行，独立运行/提交；不一次混入所有控制流。
- [ ] 保留短路和不可达检查；验证 goto 形成的图、循环携带值与同一目标的多前驱输入。
- [ ] 检查修改后 verifier、O0/O2 输出和运行一致，覆盖计数按新增函数增长。
- [ ] 对每个实际语义变化更新相应设计文档，阶段关闭完整门。

**验证：**`python3 tests/selfhost/llvm-ir.py --compiler-path ./yh --suite control`；
每个子切片 self-check 退出 0，错误 CFG 被 verifier 拒绝，不产生非法 phi。

## LL5：内存、聚合与模块数据（LLVM-03、04）

**文件：**新增 `compiler/ast/ast_ir_memory.yh`、`compiler/ir/ssa_memory.yh`、
`compiler/backend/llvm_memory.yh`；修改模块 IR、global_init、CT 静态数据物化；
新增 `tests/yh-run/run/llvm-memory-values.yh`、`llvm-global-data.yh` 和
`tests/modules/projects/llvmprivate/{project.toml,main/main.yh,data/data.yh}`。

**接口：**ALLOCA、地址/字段/下标、LOAD/STORE、复制/清零及全局引用的 IR 契约，
复用 LL8a helper；未知对齐为 1，已证明对齐才提高。

- [ ] 新 `.yh` 覆盖局部/全局取址、嵌套字段、数组/union、切片共享及按值副本、静态指针和 CT backing。
- [ ] 建立有类型的 Place/布局描述，优先入口 alloca + 标量 load/store，
  不提前实现聚合 SSA 优化或任意别名分析。
- [ ] 将全局/字符串/零初始化/CT 数据从汇编输出副作用转入模块数据目录。
- [ ] 验证 sizeof/offset/alignment、pub 与 private linkage、别名和重叠复制；
  再验证缓存序列化/读回，不只检查 IR 文字是否出现。
- [ ] 每个地址/聚合切片依次通过 O0/O2 实际运行和旧门，记录剩余 unsupported；
  本片先验收局部数据/副本和跨模块全局，跨函数聚合在 LL7、浮点字段在 LL6 汇合。

**验证：**`python3 tests/selfhost/llvm-ir.py --compiler-path ./yh --suite memory`；
不修改调用方的副本保持独立、切片共享修改可见、跨模块数据正确且私有名不泄漏。

## LL6：浮点与标量转换（LLVM-01、03）

**文件：**修改 AST lowering、IR verifier、LLVM scalar 输出；扩展 llvm-float-boundaries.yh；
新增 `tests/modules/projects/llvmfloat/{project.toml,main/main.yh}`。

**接口：**f32/f64 常量位型、算术、比较、整浮转换和内存访问，遵守 LL1 契约。

- [ ] 添加 NaN、±0、f32 舍入、signed/unsigned 转换和不确定边界的已决期望测试。
- [ ] 实现按 IEEE 位型发常量、正确比较谓词、已定义转换路径；禁用 fast-math。
- [ ] 核对 CT 执行/常量折叠与动态结果，发现旧差异先单列复现，不把 LLVM 改成新定义。
- [ ] 针对不涉及 printf 的标量自校验先跑 O0/O2；格式输出等完整运行时用例在 LL8b 汇合。
- [ ] 更新覆盖/缓存 schema 并跑完整旧门和浮点专项门。

**验证：**`python3 tests/selfhost/llvm-ir.py --compiler-path ./yh --suite float`；
已锁定比较/位型/转换一致，未定义边界不被加上虚构的期望值。

## LL7：完整调用、yh ABI 与 C ABI（LLVM-03、05）

**文件：**新增 `compiler/ast/ast_ir_abi.yh`、`compiler/backend/llvm_call.yh`；
修改 IR 调用/签名、序列化、接口；新增
`tests/modules/projects/llvmabi/{project.toml,main/main.yh,bridge/bridge.yh,c/bridge.c}`、
`tests/yh-run/run/llvm-calls.yh`、`tests/selfhost/llvm-abi.py`。

**接口：**版本化 yh-llvm-v1 显式副本/结果缓冲签名，首期 Linux/x86_64 System V C ABI
签名、间接调用及变参 metadata。旧 AAPCS64 分类器不是首期签名实现。
ABI 必须进入函数指针类型与接口，不能只存在直接 CALL 指令上。

- [ ] 测试窄返回、超过寄存器参数数、交错整浮、x64 INTEGER/SSE/MEMORY 类聚合、
  函数指针、两类变参与切片返回；HFA 的 ARM64 专项放 F1。
- [ ] 固定 yh LLVM ABI 签名，所有模块使用同版重编；不与旧 yh 机器 ABI 对象混链。
- [ ] 对等价 C 声明用 clang 21.1.8 导出 IR/对象，核对 coercion、sret 和扩展属性。
- [ ] 运行 yh→C、C→yh 双向真实互调、callback 与源级拒绝案例；
  `@[noreturn]` 的声明、控制流和违约 trap 分别验证。
- [ ] 验证跨模块接口错配拒绝、缓存版本和源码兼容，关闭调用类 unsupported 后跑门。

**验证：**`python3 tests/selfhost/llvm-abi.py --compiler-path ./yh`；
O0/O2 双向互调、自校验、拒绝层全部通过，函数指针的 ABI 不丢失。

## LL8b：x64 完整运行时与宿主 OS 桥（LLVM-07、14）

**文件：**扩展 `compiler/backend/llvm_runtime.yh`，修改 prelude 与现有运行时登记；
修改 `compiler/cmd/project_dir.linux.yh`、`clock.linux.yh`、`process.yh`；
新增 `tests/yh-run/run/llvm-runtime-complete.yh`、`llvm-linux-x64-host.yh`，
扩展 llvm-runtime.py 与 runtime-memory.py。

**接口：**提供与现行语言行为一致的 malloc/free/printf 和已有内存入口；
Linux/x86_64 syscall/目录/时钟/内存/进程桥作为明确宿主与目标运行时能力，
不复用 ARM64 syscall 编号/常量，不混入通用 LLVM 类型规则。

- [ ] 覆盖 allocator 边界、格式输出、错误路径、直接/间接 runtime 调用和 LLVM helper 插入。
- [ ] 使用 LL5/LL7 可表达的 yh/IR 迁移完整运行时，保留现有允许的 OS API 与导入政策。
- [ ] 依据目标系统接口实现 x64 syscall、目录枚举、时钟、内存和进程；
  保留 A 的 ARM64 启动分支，测试嵌套目录、中文/空格路径、单调时钟和子进程退出。
- [ ] 对程序/候选的 O0/O2 做未定义符号、调用自递归及 LLVM-generated libcall 审计。
- [ ] 保留 runtime-memory.py 原断言，新增 LLVM 口径；禁止以删除禁止列表使测试变绿。
- [ ] 汇合全部当前运行语料与各工具项目所需运行时功能，再进入完整驱动阶段。

**验证：**`python3 tests/selfhost/llvm-runtime.py --compiler-path ./yh --suite complete`；
runtimebytes 自包含门和候选导入门通过，输出、退出和错误语义与已决规则一致。

## LL9：统一入口、缓存与失败发布（LLVM-08、09、12、15、16）

**文件：**修改 cmd 的 driver/compile/module_worker/module_build/link_cache/build_scheduler、
AST cache、语言接口；修改 tests/yh-run/check.py、tests/modules/check.py、build-check.py；
新增 `tests/selfhost/llvm-cache.py`、`tests/selfhost/llvm-driver.py`，复用路径/失败 fixture。

**接口：**--backend/--target/-O0/-O2 在所有入口共享；runner 提供 --backend/--target/--opt-level
并以 argv 注入编译器命令。建立设计 §6 的目标命名空间、键和成功发布协议。
链接驱动的内嵌 lld 方案见 LL9L；本片先完成 gcc 回落路径的目标隔离与缓存键。

- [ ] 先加同名输出切目标、工具路径不变版本变、混旧对象、损坏缓存的失败用例。
- [ ] 将单文件、emit、build/run 与 worker 接入同一受检→IR→LLVM 流程；
  check 无工具仍可用，路径中空格/中文完整保留。
- [ ] 实现完整对象/链接身份，按层保留精确依赖，保持无改动命中与失败恢复正确。
- [ ] 将旧 ARM64 crossbin/gcc 与原生 x64 LLVM/链接器完全隔离；
  缓存与发布检查对象 machine，错误架构输入明确拒绝而不是交给错误工具重试。
- [ ] 复跑早接口就绪、晚私有错误、同项目并发/取消、损坏对象与 manifest 配对检查；
  R2b 真线程池/状态隔离依赖不能以 fork 的通过替代。
- [ ] 让全量 runner 明确选择 LLVM O0/O2 并核对 emitted/checked 数量，禁止后台隐式旧编译器。

**验证：**新 llvm-cache.py / llvm-driver.py 与当前路径/缓存/并发门；
`python3 tests/yh-run/check.py --compiler ./tmp/llvm-migration/bootstrap/A --backend llvm --target x86_64-unknown-linux-gnu --opt-level O0 --workdir tmp/llvm-migration/run-o0`。
runner 新参数在本任务实现；对应 O2、modules 与 build-check 同样注入目标/后端。

## LL9L：内嵌 lld 静态链接器（LLVM-15；2026-10-15 用户要求增补）

**背景：**LL9 只要求链接步避开 ARM64 gcc 包装器，驱动仍是平台 cc。用户进一步要求
把 lld 也静态链接进 yh：链接在进程内完成，不再起 cc/binutils 子进程，链接器版本随
固定 SDK 锁定。2026-10-15 已完成可行性实测：Ubuntu `liblld-21`
（1.96 MB 包，六个静态归档约 13 MB）与固定 SDK 同为 21.1.8；`liblld-21-dev`
提供官方库内入口 `lld::lldMain`（`lld/Common/Driver.h`，可重入、带崩溃恢复）。
实测把 `_start` 对象在进程内链接为 `ELF64 ET_EXEC`（x86-64）并运行退出码 7；
全量静态链 141 MB、strip 后 123 MB，`readelf -d` 无 libLLVM/liblld NEEDED。
复现与依赖闭包见 [完成记录](../01-finished/yh-内嵌lld可行性实测-2026-10-15.md)。

**文件：**新增 `compiler/llvm/lld_bridge.cpp`（C++ shim；lld 无 C API，不能用
`.yh` 重写）、`compiler/backend/llvm_lld.yh`、`tests/selfhost/llvm-lld.py`、
`tests/modules/projects/llvmlink/`；修改 `vendor/llvm/sdk.lock.json`、
`tools/llvm-sdk.py`、`tools/llvm-host.py`、`Makefile`、
`compiler/cmd/link_cache.yh`（`mb_link`）与 `compiler/cmd/driver.yh`。

**接口：**`@[extern] fn yh_lld_link(argv **char, argc int, diagnostic *char, capacity u64) int`；
yh 侧组装 `ld.lld` 风格 argv 与有界诊断缓冲，shim 调 `lld::lldMain` 并捕获 stderr，
返回 0 成功、-1 失败。不使用 lld 的进程退出路径；`canRunAgain=false` 时 worker
明确结束而不是继续复用。链接器版本、目标与输出类型进入对象/链接缓存键。

- [ ] **L9L-1 SDK 固定与裁剪决策**：`sdk.lock.json` 增加 `liblld-21`、`liblld-21-dev`
  （全量方案另加 `libpolly-21-dev`）的 URL/SHA-256 与组件清单；身份记录纳入 lld
  归档哈希。全量实测约 123–141 MB；是否改用源码构建
  `LLVM_TARGETS_TO_BUILD=X86;AArch64` + 关 Polly 的裁剪版在此片一次决定并记录。
- [ ] **L9L-2 shim 与探针**：shim 只做参数转递、输出捕获和 C ABI 边界；
  `tests/selfhost/llvm-lld.py` 在无系统 cc/lld 的 PATH 下链接 `_start` 探针并运行，
  对照 gcc 链接的行为（退出码、ELF machine=62、NEEDED 不含 LLVM/lld）。
- [ ] **L9L-3 驱动接入**：`compiler/cmd/link_cache.yh` 的 `mb_link` 切到进程内 lld，
  yh 侧负责 CRT/libc/动态加载器发现与 argv 组装；过渡先用宿主
  `gcc -print-file-name`/`-print-search-dirs` 取路径，自举阶段改
  `-nostdlib` + 自有 `_start`。保留显式回落开关，缓存键不含绝对工具路径。
- [ ] **L9L-4 交叉链接预研**：同一 lld 包含 MachO/COFF 方言，用
  `-t darwin`/Windows 探针验证 Linux 宿主产 Mach-O/COFF；macOS ad-hoc 签名与
  Windows 导入库不在本片，只记录边界与 F2/F3 接入条件。
- [ ] **L9L-5 政策与文档**：ADR-0014 增补「链接器内嵌」决定（原文「平台链接驱动仍是
  显式依赖」改为「LL9L 前可回落、LL9L 后用内嵌 lld」）；设计 §7、许可与发行说明同步；
  不删除 gcc 回落路径，也不改写 asm/ 冻结与 link/ 暂停的结论。
- [ ] **L9L-6 LL10 汇合**：LL10 连续自编在 L9L-3 验收后显式使用内嵌 lld，
  至少最终一代不再经过 gcc 包装器；核对 lld 版本身份、`readelf -d` 与固定点。

**验证：**`python3 tests/selfhost/llvm-lld.py`（隔离 PATH 链接并运行）、
gcc 产物差分（退出码/stdout/动态依赖）、`make test` 与 `make selfhost-native`
保持全绿；`readelf -d` 无 libLLVM/liblld。

**边界：**本片不做 lld 源码完整裁剪流水线、不做 macOS 签名（TC10 独立）、
不实现 Windows 启动/导入库；不把内嵌 lld 作为 LL3–LL9 的前置，未验收前默认仍走
平台 cc。

## LL10：连续 x64 原生 LLVM 自编与硬门汇合（LLVM-10、12、14、15、16）

**文件：**修改 Makefile、tools/seed-build.py、tools/selfhost_snapshot_gate.py、
tests/selfhost/native-selfhost.py 与专项 runner、`.github/workflows/ci.yml`；
新增 `tests/selfhost/llvm-selfhost.py`、`tests/selfhost/llvm-fixedpoint-probe.yh`。

**接口：**未来 Makefile 的 BACKEND/TARGET/OPT_LEVEL 向构建与全部门禁传递；
新增 `make test-llvm`、`make selfhost-llvm`，首期 TARGET=x86_64-unknown-linux-gnu；
启动种子与候选目标分别记录，输出候选世代及精确产物清单，不滚种子。
链接步在 LL9L 验收后使用内嵌 lld（至少最终一代不经过 gcc 包装器）。

- [ ] 固定点脚本先测试缺 `.ll`、错接口版本、代号/目录变化与后端误用被拒绝。
- [ ] 按设计 §7 用旧 ARM64 种子经 qemu 产 A，A 显式 LLVM x64 产 B，
  B/C/D 检查 ELF machine=62 后直接原生连续自编；O0 与 O2 分别验证相邻候选固定点。
- [ ] 用最终原生 D 自解析、全量语法/运行/模块/项目检查和 runtime/缓存/来源专项门；
  新模式的原生候选和程序不得由 qemu-aarch64 代执行。
- [ ] 核对 compiler/、asm/、link/、libs/ 实际消费能力全部覆盖，LLVM fallback=0；
  与 R2b 任务私有状态、真正线程池、增量/并发/确定性硬门汇合。
- [ ] CI 首期将 Linux/x86_64 原生作为新默认候选验收；已有 Linux/ARM64 和 macOS
  种子保留过渡状态，ARM64 LLVM 迁移在 F1，不在本阶段宣称其他目标已迁移。

**验证：**`make test-llvm`、`make selfhost-llvm` 在任务实现后退出 0；
O0/O2 的 `.ll/.s.i/.s.ct` 候选固定点、实际覆盖、所有运行门有完整日志。

## LL11：性能评估与 x64 默认切换（LLVM-11、13、15）

**文件：**修改默认配置、Makefile/CI/发行文档、AGENTS.md、README、compiler/README.md；
扩展 tools/compiler-performance.py，新增 `tests/yh-run/run/llvm-default-backend.yh`。

**接口：**无 --backend 时默认 LLVM O0，发布显式 O2；默认选择贯穿构建、测试、安装和种子策略。
本机 x86_64 默认选择 x64 种子，ARM64 宿主在 F1 前仍按其过渡路径工作。

- [ ] 用同机冻结负载对照旧模式、LLVM O0/O2，至少 20 轮并记录运行程序性能；qemu 与原生分开。
- [ ] 归因可重复 >10% 的回退，关闭或形成经评审接受的取舍；不悄悄改旧目标数字。
- [ ] 在 LL10/R2b 硬门关闭后切默认，新增用例断言 emitted 使用 LLVM、fallback=0。
- [ ] 同步固定 SDK 构建依赖、运行依赖和许可分发，保留源码 `.yh` 与接口可见性规则。
- [ ] 在没有系统 LLVM 工具/动态库的隔离环境用最终 yh 实际编译、链接、运行 `.yh`
  并冷编自举；readelf NEEDED 不含 LLVM，编译不调用 LLVM 旁车；
  链接使用 LL9L 的内嵌 lld（带显式回落开关）。
- [ ] 原生默认 `make test` / `make selfhost-native` 全绿后，才将验证的 x64 候选滚到
  `bin/yh-linux-x64` 并写 `.sha256`；显式 SEED_DEST=bin/yh-linux-x64，
  确认 seed 输入是原生 D，不从仍为 ARM64 的根目录旧 yh 误复制；ARM64 种子/哈希保留。
- [ ] 用新 x64 种子在不含 crossbin、无需 ARM64 模拟的环境冷编并跑关键探针，
  再验证哈希与本机默认构建；不得仅检查文件名就称为 x64 种子。

**验证：**默认命令全门通过；候选性能/依赖政策有证据；种子未在失败门下被覆盖。

## LL12：退役旧机器代码生成

**依赖：**LL11 的 x64 首期和 F1 的 Linux/AArch64 LLVM 回归都通过后执行。
本任务等待 F1 不阻挡本机 x64 验证或 x64 种子建设。

**文件：**删除已无消费者的 compiler/backend/arm64.yh、arm64_call.yh 和 gen/emit_arm64.yh
机器原语；修改调用点、旧开关和文档。gen 的类型、语义、通用缓冲保持实际需要的实现。

**接口：**终态唯一生产代码生成为 LLVM，版本/帮助/错误消息一致。

- [ ] 用 rg 普查 em_*、arm64_emit_replace、旧输出缓冲和后端选项的消费者，逐个确认无引用。
- [ ] 分切片删除仅因迁移而失去消费者的旧代码，不顺手清理原有无关死代码。
- [ ] 每片新增/保留 `.yh` 验证，无 --backend 的构建通过且旧选项给明确诊断。
- [ ] 再跑默认全部门、自举固定点及 LLVM runtime/ABI/缓存专项检查。
- [ ] 更新 docs/finish.md 和历史路线对接说明，保留 Git 中的旧种子与实现历史。

## 2. 后续平台子项目（本轮只规划，不实施）

| 阶段 | 范围与主要源码落点 | 五层验收重点 |
| --- | --- | --- |
| F1 Linux/AArch64 | 复用首期公共 LLVM 路径，接 AAPCS64/HFA、ARM64 syscall/运行时、接口与现有种子迁移 | ARM64 对象→链接→标准库运行→原生编译器→原生种子/固定点；完成后才退役旧 ARM64 路径 |
| F2 macOS/ARM64 | Apple ABI、SDK/sysroot、目标版本、现有 Darwin OS 桥、链接与签名 | Mach-O 对象、系统库/签名、原生语料与自举；工具版本与 SDK 身份进入缓存 |
| F3 Windows/x86_64 | MSVC ABI/LLP64，新增 Windows OS 文件/目录/Unicode/进程/时间/内存桥、COFF/PE 驱动 | SDK/导入库/启动入口/辅助符号；Windows 原生构建及线程/进程调度，不以 WSL 代替 |
| F4 macOS/x86_64、Windows/ARM64 | 对应 target ABI、目标库、OS 适配和各自原生种子 | 每格单独完成运行/自举；两种 macOS 产物全过后再考虑 universal binary |

每个 F 阶段开始前补一份对应平台的具体切片计划与 `.yh` fixture；遵守当时已确认的
目标版本/SDK/运行时政策，不提前写 32 位、ARM64EC、JIT、LTO 或其他无消费者的扩展。

## 3. 文档同步、阶段关闭与交付状态

代码阶段只刷新实际受影响的语法/语义/ABI/平台文档；如果确实修改语法，先更新并分析
docs/yh.g4 的无歧义性，再按仓库语法流程推进。单纯后端替换不伪造语法变更。
NP3 的受检/解耦与本计划合并跟踪；NP4 的自研机器 IR/分配器不作为 LLVM 路线前置；
NP2/NP5 保留必要语言规范化，通用优化交 LLVM。旧自有汇编/链接任务的产品定位由 ADR 评审记录，
不自动删除 asm/、link/ 项目，也不假称其平台门已完成。

当前状态：**2026-10-14 用户授权实施；已将外部 clang 路线改为内嵌静态 LLVM**。
**2026-10-15：用户要求写入内嵌 lld 链接器，新增 LL9L 阶段；可行性已完成实测。**
逐阶段状态见复选框、docs/todo.md、docs/finish.md 与 tmp/llvm-migration/progress.md。
