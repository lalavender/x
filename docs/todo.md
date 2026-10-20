# todo

只记录**未完成**事项。已完成任务的历史与验证证据见
[finish.md](finish.md) 与 [01-finished/](01-finished/)；方案文档在
[02-plan/](02-plan/)，取舍见 [adr/](adr/)。

## 待办

### 编译器代码规模统计工具（2026-10-20，方案交付，尚未实施）

用户确认首版统计代码行、注释、模块占比与大文件。拟新增
`tools/yh-code-stats.py`，默认扫描 `compiler/**/*.yh`，详细口径见
[工具方案](02-plan/yh-编译器代码统计工具方案.md)。

- [ ] STAT0：在 `tests/tools/yh-code-stats/` 添加 `.yh` 夹具与预期计数检查。
- [ ] STAT1：Python 标准库实现 yh 注释/字面量边界扫描及职责目录汇总。
- [ ] STAT2：文本/JSON、大文件排行与不依赖编译器构建的 `make code-stats`。
- [ ] STAT3：本机实跑、人工抽查与构建/回归门，更新使用文档及完成记录。

### C/C++ 桥迁移到 yh（2026-10-20，可行性建议，未开始实施）

已完成[源码分析与本机探针](01-finished/yh-C与C++代码重写可行性分析-2026-10-20.md)。
以下是候选迁移顺序；本轮只分析，没有修改生产实现。

- [ ] 迁移 `compiler/llvm/bridge.c` 到 yh，保持 LLVM 生命周期、初始化同步、
  有界诊断及原子发布；添加正式 `.yh` 对等用例与错误路径验收。
- [ ] 将 `lld_bridge.cpp` 的配置/argv/库搜索移到 yh，保留 `lldMain` 的最小
  C++ 适配层及不可重入状态处理。
- [ ] 评估桩的构建期择一机制；迁移前保留当前 C 弱桩，避免直接引入重复强符号。
- [ ] 更新 SDK 身份、归档成员与自举闭包，完成候选引导和本机完整门后再滚种子。

### project.toml 静态库分组与 build --link（2026-10-20）

方案已交付，功能未实施。用户已确认：默认链接全部组，显式 `--link <组名>`
仅选择点名组；方案建议重复参数以选择多组。其他细则见
[实施方案](02-plan/yh-project-link静态库实施方案.md)与
[ADR-0016 提议](adr/0016-yh项目静态库分组链接.md)。

- [ ] LINK0：新增 `.yh` 项目与真实归档 fixture，覆盖默认/单组/多组选取。
- [ ] LINK1：清单分组快照、CLI 选择、按目标配置与 whole 规则、完整诊断。
- [ ] LINK2：接入各链接出口与归档内容哈希；组切换仅影响最终链接缓存。
- [ ] LINK3：候选引导后迁移 compiler 清单及自举入口，停用重复归档注入。
- [ ] LINK4：本机 `make` / `make test` / `make selfhost-native` 与相关链接门，
  更新使用/设计文档和完成记录；全绿后才允许滚本机种子。

### 字符串字面量只读化（2026-10-20 性能对比时发现）

yh 产物的 Mach-O 比 clang 多一个 `__DATA` 段（多占 16 KB 页），实测归属：

| 变体 | `__cstring`（只读） | `__data`（可写） |
| --- | ---: | ---: |
| yh（LLVM / legacy 同） | 0 | **12** |
| clang -O2 | 11 | 0 |
| zig ReleaseFast | 12 | 856 |

- **机制**：`compiler/gen/emit_arm64.yh:24-25` 的输出组织只有
  `.text` / `.data` / `.bss` 三个缓冲，「全局初始化与字符串进入 `o_dat`（.data 段）」；
  `em_data_string`（同文件 1074 行）把字面量解码成 `.byte` 写进 `.data`，
  **没有独立的只读数据缓冲**。Mach-O 段按 16 KB 页对齐 → 多占整整一页。
- **语义根因**：yh 的字符串字面量**可写**（实测 `*p = 65` 合法，输出 `Aello`），
  与 C 的 `char[]` 一致；而 clang/Zig/Rust 的字面量不可变，放只读 `__TEXT.__cstring`，
  与代码同段、不额外占段、该页也不 dirty。LLVM 后端与 legacy 布局一致，
  说明这是 **IR 层的建模决定**（字面量按可写全局变量建模），不是后端实现问题。
- [ ] **评估「只读字符串常量」方案**：字面量本身放只读段（`__TEXT.__cstring`），
  需要可写副本时走显式复制（`let s = [N]u8 = "hello";` 这类已有语法）。
  收益：省掉一整个 16 KB 可写段、字符串页只读可与代码页共享。
  代价：**语义变更**（字面量改为不可变），需评估对现有语料与
  `tests/yh-run/` 中字符串相关用例的影响。

### Darwin 自举链接的桥注入阻塞（2026-10-20 性能对比时发现）

拉取 0.0.5（F2-10，macOS/ARM64 默认切 LLVM）后，**`make` 在本工作区自举失败**：

```
ld64.lld: error: library not found for -lc++
ld64.lld: error: undefined symbol: __ZdlPv
>>> referenced by .../llvm-host-darwin-aarch64/libyh-llvm-bridge.a(lld_bridge.o)
```

- **根因**：入库种子 `bin/yh-darwin-arm64` **硬编码了 73 处构建机的绝对路径**
  （`/Users/lavender/.codex/worktrees/macos-llvm/x/tmp/llvm-migration/...`，
  含桥归档与 LLVM 静态库清单）。证据：
  `strings -a bin/yh-darwin-arm64 | grep -c "codex/worktrees"` = 73，
  而 0.0.4 的 legacy 产物为 0。自举时
  `compiler/cmd/link_cache.yh` 的 `mb_darwin_selfhost_enabled()`
  （读 `YH_LLVM_SELFHOST=1`）把这些绝对路径喂给链接器，
  于是在**任何其他路径下**都找不到对应归档；即便找到，那个 SDK 也缺 `-lc++`。
- **已验证**：绕开桥注入后 0.0.5 编译器本体**构建成功**（1,956,384 B）：
  `cd compiler && YH_LLVM_SELFHOST=0 ../bin/yh-darwin-arm64 build -o ../yh-legacy`；
  且该产物跑 `--backend llvm` 明确报「内嵌 LLVM 桥未链接」，
  印证桥是 LLVM 后端的前提。阻塞**只在桥注入路径**。
- **影响**：不影响用已入库种子做编译与性能对比；但**影响在仓库内继续自举
  0.0.5 之后的代**（见 finish.md 2026-10-20 条目）。

- **已修（2026-10-20，Zig 式）**：自举闭包改由构建机提供。
  `tools/llvm-darwin-host.py prepare` 生成
  `tmp/llvm-migration/llvm-host-darwin-aarch64/selfhost-flags.txt`（每行一个参数），
  `seed-build.py` 经 `YH_LLVM_SELFHOST_FLAGS` 传给种子；`lld_bridge.cpp` 优先读
  该文件，桥内常量只在旧种子过渡期回退。新种子不再烘焙绝对路径
  （`strings -a bin/yh-darwin-arm64 | grep -c /Users/` 从 73 → 0），
  换机器/换 worktree 只需重新 `make llvm-host`。
- **已修**：`-lc++` 仍由闭包末尾携带，解析交给宿主 SDK 的 `libc++.tbd`
  （`SDKROOT` 指 26.5 时通过；SDK 27 的 TAPI 超出内嵌 lld 21，见下）。
  stub 不含 libc++ 的交叉边界仍见
  [遗留边界](03-design/yh-Darwin交叉编译遗留边界.md)。
- **已修（门禁）**：`tools/selfhost_snapshot_gate.py` 新增
  `seed_path_warnings()`；`make seed` 拒绝包含 `$HOME` 路径的种子，
  `--verify-seed` 对旧种子只告警（保证上一版 Release 种子仍能引导）。
- [ ] **固定 SDK 预编译分发**：首次 `make llvm-host` 仍要从源码构建 569MB
  LLVM/lld；把产物作为 Release 资产（带锁文件校验）可免掉每台机器的构建。
- [ ] **Linux/x64 同步**：x64 自举仍把闭包参数编进种子（`tools/llvm-sdk.py`），
  按同一机制改到运行时文件。
- [ ] **SDK 27 兼容**：内嵌 lld 21 解析不了 `arm64e.x1` TAPI。2026-10-20 起
  `tools/llvm-darwin-sdk.py` 在解析期直接拒绝并提示 26.x（不再等 LLVM 编完），
  真正兼容仍需升级固定 LLVM 或按实际 SDK 裁剪目标列表。
- **已做（2026-10-20）一条命令构建**：`make bootstrap` = 幂等 prepare + 冷编；
  Darwin 固定 SDK 就绪后 Makefile 自动导出 `SDKROOT`，C 互操作用例不再依赖
  手工环境变量；`lld_identity` 去掉构建机路径，同一份源码/归档在不同
  worktree 得到相同身份。
- [ ] **`make dev` 增量构建**：闭包参数已进 Darwin 链接键，但归档内容仍按路径
  计身份；SDK 原地重建时需清缓存或补内容哈希。



原「编译器已知缺陷（待修复）」清单 11 项已全部修复或复核为现行种子/编译器
不再复现，逐项复现、根因、修法与用例见
[完成记录](01-finished/yh-编译器已知缺陷清单-2026-10-13.md)与
[finish.md](finish.md) 同日条目；本节不再列未完成项。

### Linux 平台缺口（2026-10-09 在 WSL 重建 Linux 种子后首次实测发现）

仓库的语法/运行/模块/自举门此前只在 macOS 上跑过；本次用重建的
Linux/aarch64 种子在 WSL 上跑出一批**既有**缺口（与 HEAD 基线一致，
非本次改动引入）。重建链最终种子已入库为 `bin/yh-linux-arm64`
（2026-10-09）。**2026-10-11：build-check 7 项缺口全部修复**（宿主
open 旗标按宿主平台取值、窄整型返回宽度归一、模块链接 -lm、
clock_gettime 公共登记、libsbase fixture 平台化、CRLF 规范化），
`make test` / `make selfhost-native`（含 build-check **84/84**、
runtime-memory/lex-stats/scratch-isolation）在 WSL 全绿。重建与验证
路径见 [WSL 种子链记录](01-finished/yh-WSL重建Linux-aarch64自举种子-2026-10-09.md)。

- [ ] **本机 ANTLR 参考语法门需要 Java + antlr4 工具 jar**：`tests/yh/check.py`
  默认模式在无 `~/.m2/.../antlr4-*-complete.jar` 时报「找不到本地 ANTLR jar
  缓存」；jar 需从 Maven Central 下载（antlr4-tools 的自动下载走 GitHub
  Release，本机不可达）。已手工放 jar 后 76/76 + 45/45 通过（含 CT6 语法语料）。
  WSL 侧已配置：apt `antlr4`（4.9.2）+ `libantlr4-runtime-java` +
  `libantlr3-runtime-java` + `python3-antlr4`（4.9 runtime）+ `/usr/local/bin/antlr4`
  兼容 wrapper（吞掉 `-v` 并加载全部依赖 jar），本机 `make test` 第 1 层通过。

### Linux/AArch64 libc（2026-10-02，候选方案未实施）

目标已确认：独立链接、兼容 C ABI；[分析报告](01-finished/yh-libc可行性与阻塞点分析-2026-10-02.md)
与[分阶段候选方案](02-plan/yh-libc分阶段候选方案.md)已交付。
以下记录后续建议，不表示已经授权实施全部 libc。

- [ ] **L0**：库对象/归档出口、CRT/静态链接配置、
  运行时提供方与 Linux 种子/原生门。
- [ ] **L1–L2**：静态核心子集、配套 C 头文件，再补 C 裸变参、
  专用 C 数据符号与基本 stdio。
- [ ] **L3–L4**：TP/atomic/上下文原语、TLS/线程/信号，binary128/fenv
  与其余标准接口；按接口清单逐项验收。
- [ ] **L5**：Linux PIC、共享对象、动态 TLS 与自有 ELF 装载器，单独验收。

### 标准库

- [ ] **OS0–OS6：os/sys 标准库可用性优先**（2026-10-19 规划）：结果/选项 ABI →
  文件闭环 → 流式目录/cwd → 显式 envp 查询 → 精确路径 spawn/wait/exit →
  io/time 收敛 → 加载/示例体验；旧 os/io/time 接口保持兼容。
  sys 按场景交付最小子集，Linux/x64 与 ARM64 分别适配，不等待编译器整体迁移。
  **OS7** 编译器迁移/独立性审计、**OS8** Darwin 新接口另列后续。
  当前仅有规划，阶段均未实施；见[联合设计](03-design/yh-os与sys标准库设计.md)、
  [联合实施方案](02-plan/yh-os与sys标准库实施方案.md)与
  [提议 ADR-0015](adr/0015-yh-os与sys标准库分层.md)。
- [ ] **SYS0–SYS7：`libs/sys` 底层能力清单**：保留原始入口、`-errno`、文件/目录、
  内存/时间和进程原语；排期由 OS 阶段按需取子集，消费者迁移/独立性与 Darwin
  桥后续交付。2026-10-19 已修正 x64 入口及 OS/架构后缀的过时描述，尚无实现。
  API/文件与门禁见
  [设计](03-design/yh-sys系统调用封装设计.md)、
  [实施方案](02-plan/yh-sys系统调用封装实施方案.md)与
  [模块入口](../libs/sys/README.md)。
- [ ] 为 `libs/` 增加工具链默认发现与安装打包布局，保留 `YH_STDLIB` 覆盖；
  当前仍需手动指定 `YH_STDLIB` 才能导入运行。
- [ ] 后续按实际 API 需求扩展；当前不承诺跨平台 ABI，不把 libc 裸变参
  `printf` 接入 FFI，也不引入隐式内存分配。

### Nanopass 风格优化架构（2026-10-02，方案待评审）

2026-10-14 已交付 [LLVM 替换方案](02-plan/yh-LLVM后端替换实施方案.md)。
新路线拟合并 NP3 的受检/解耦工作，通用优化/分配交 LLVM；在 ADR-0014 评审前
保留原任务状态，不默认同时启动自研 NP4 和 LLVM 的机器代码生成。

用户选择“优化扩展与自举稳定”为本方案首要目标；沿用 ADR-0009 的增量速度约束。
完整[架构设计](03-design/yh-Nanopass风格优化架构.md)、
[分期实施方案](02-plan/yh-Nanopass风格优化架构实施方案.md)与
[ADR-0011 草案](adr/0011-yh采用Nanopass风格优化阶段契约.md)已交付，尚未实施。

- [ ] **NP0**：锁定优化语义、覆盖统计与同编译器优化开关对照，建立可重复基线。
- [ ] **NP1**：复用现有 SSA，拆分 `ir_simplify`、建立固定 pass 顺序及函数私有分析索引；先保持输出行为。
- [ ] **NP2**：逐项接入低成本 SSA 优化、完整引用重写与 CFG 清理，默认管线通过运行与固定点门。
- [ ] **NP3**：受检函数/Core 阶段契约与 lowering 解耦；逐切片补齐自编覆盖，消除成功 SSA 函数的旧汇编预发射。
- [ ] **NP4**：建立机器 IR，显式处理 ABI、phi 边复制与线性扫描寄存器分配。
- [ ] **NP5**：经测量后加入发布管线 SCCP、局部值编号与有限内联，验证依赖失效及确定性。

### 编译流程重规划（2026-10-01，实施中）

新方向见[ADR-0009](adr/0009-yh采用check与IR及早期并行.md)，
已确认需求与事实见[设计决策树](03-design/yh-编译流程设计决策树.md)。
完整[设计](03-design/yh-编译流程重规划.md)与
[实施方案](02-plan/yh-编译流程重规划实施方案.md)已重写。
上一轮 CF-0–CF-4 已撤回，不代表当前实施清单。用户已确认整体方案并
明确要求实施 R0–R6。**R2 收口按 [R2 收尾实施计划](02-plan/yh-R2收尾实施计划.md)
（2026-10-19，RS0–RS6）执行**：RS0 先对账回填 R2a/R1 剩余项（与 LLVM
LL4–LL7 合并验收的重叠项、真缺口归位），RS1 任务私有上下文 → RS2 函数级
check/IR 缓存 → RS3 文件级对象 → RS4 缓存键收口 → RS5 提交协议复核。

- [ ] **R1**：文件一次解析、AST、任务私有前端、受检表示与 yh check。
  - [ ] R1 剩余（RS0 对账归位，2026-10-19）：
    语义/check 代码边界与旧遍历分离（LL2 受检前端已覆盖部分；剩余差距
    并入 RS1 任务私有上下文）→
    任务私有上下文（= RS1，进程 worker 依赖全局语义状态，函数缓存与 R2c 前置）→
    函数级 check 缓存（= RS2）。AST 已同时在 build/check 收集。
    会话接口就绪：InterfaceReady 调度已在 fork worker 验收（2026-10-01
    调度报告）；会话 API 形态归 VS Code 扩展线 VS-U1，移出 R2 门。
- [ ] **R2a**：typed SSA、verifier、默认低成本优化与双 arm64 后端。
  **RS0 对账回填（2026-10-19）**：剩余 10 项逐项核对，R2a 清单收口——
  - [x] switch、goto/label 与嵌套循环、for-in 与无限循环 —— LLVM LL4
    同源切片合并验收（O0/O2 语料 343/343，见 LL4 完成记录）。
  - [x] 一元 +/- 与浮点标量 —— LL6 浮点 + LL1 一元类型规则（LLVM-SEM-05）。
  - [x] 聚合/内存语义 —— LL5 全量收尾（2026-10-17）。
  - [x] 间接调用与变参 —— LL7（2026-10-17）。
  - [x] 单文件与 `--emit-asm` 共用新后端 —— LL9 统一入口；旧 `--emit-asm`
    保留至 LL12 退役。
  - [x] 负数字面量实参 —— 2026-10-19 RS0 探针实测（darwin 旧后端 rc=0：
    负字面量作 int 实参、u32 形参、一元减号作用于调用结果）+ 既有语料
    `run/04-if-else` 的 `check(-3)` 与 `llvm-integer-boundaries` 的
    `quotient32(-21, 4)`。「unsigned_score 回退」仅指旧 SSA 后端覆盖统计，
    LLVM 路线 fallback=0，旧后端随 LL12 退役，不作为 R2 缺口。
  - [ ] 默认优化覆盖与缓存提交协议复核 → 归 R2 收尾计划 RS5。
  - [x] Linux/AArch64 ABI 已于 2026-10-20 通过 F1；macOS/ARM64 仍归 F2。
- [ ] **R2b**：首个完整 SSA 版本须具备接口就绪推进、函数
  check/IR 缓存、文件对象/链接缓存、确定性与失败提交验收。
  **2026-10-19 用户决定：多模块线程并行（真正线程池）推迟到并发标准库
  完成之后**（顺序：宿主线程桥 → libs/sys 线程原语 → 编译器线程池消费
  自己的标准库）；当前执行模型**维持 fork/COW 进程 worker 现状**
  （fork worker 本就是多模块并行，不退回单模块串行）。
  - [ ] R2b 剩余（首个完整 SSA 版本的硬门，线程载体项已拆出到 R2c；
    按 R2 收尾计划切片执行）：
    ~~RS1 任务私有上下文~~（✅ 2026-10-19：RS1a 域标注 + RS1b 缓冲
    私有化 + RS1c TaskCtx 收敛 199 字段，种子 `5b34a067…`；RS1d 显式
    传参并入 R2c）→
    RS4 缓存键收口（✅ 2026-10-19 核查回填：编译器指纹/汇编器/链接器
    身份、目标/优化级/后端、源文件与依赖接口内容均已在键中，证据
    link_cache.yh:868/991/462、module_build.yh:629-705）→
    RS2 LLVM 模式函数级 check/IR 缓存（真缺口；legacy 已有窄子集缓存，
    worker 子进程统计不可见实测 ir_cache_hits=0；必须 Linux 宿主实施，
    LL11 切默认前完成、单函数 200ms 目标主力）→
    RS3 文件级对象（**设计定稿待实施**，见收尾计划 RS3 节：RS3a private
    hidden 可见性 → RS3b 按文件切发射缓冲/桩对象/多路写出 → RS3c 文件级
    缓存键与 manifest → RS3d 用例测量；40+ 步需专门会话）→
    RS5 收口报告（依赖 RS2/RS3）。
  - [ ] **R2c（2026-10-19 从 R2b 拆出）：并发标准库之后的多模块线程并行**：
    宿主线程桥（Linux clone syscall / Darwin 审核 libSystem）→
    libs/sys 线程原语（线程/mutex/cond/join，SYS 任务的一部分）→
    编译器线程池与接口调度的线程状态隔离、同项目并发与确定性验收
    （消费自己的标准库，狗粮自举）。完成前 fork worker 为正式过渡
    执行器；原 R2b 验收门「串行、多 worker 输出一致」继续作为回归门。
  - [ ] 继续降低增量与冷编时间：短路求值切片后 20 轮测量单函数修改
    743.5/817.8ms、冷编 2203.0/2765.1ms（中位数/p95）；无改动 50ms
    中位数目标已达标，单函数 200ms 与冷编 1s 目标未达。单函数修改仍
    重新汇编整个所属模块且以外部汇编器为主；完整函数级 check/IR、
    文件对象是主要后续工作。
- [ ] **R3**：自有运行时与显式 OS API；独立配置取消隐式 system，
  旧行为只在过渡兼容配置保留。
  - [ ] R3 剩余（依赖宿主线程桥，与 R2c 交错）：
    Linux arm64 原生构建并运行目录扫描适配（需先有经原生验证的 Linux 种子）→
    printf 按需扩展（宽度、精度、浮点；locale 不支持）→
    线程 API（2026-10-19 起是 R2c 的前置：宿主桥先供标准库线程原语使用，
    Darwin 走审核的 libSystem、Linux 走 clone syscall）→
    完整 OS 导入清单审计（`nm -u` 允许清单核对）后再验收 R3。
    汇编器/链接器仍通过显式 argv 调用系统工具。
- [ ] **R6**：扩展 x64 与 Windows，各目标分别完成运行/自举/性能验收。

### MOD-U6：远程获取、版本、锁文件、工作区

本地三层（当前项目/标准库/直接依赖）已交付（MOD-U0–U5，见
[模块与项目管理设计](03-design/yh-模块与项目管理设计.md)）。远程来源、
版本规则、锁文件与工作区**按实际需求另立设计与验收**，不沿用旧 Go
方案承诺（[ADR-0005](adr/0005-yh-mod-toml与按名称导入.md)）。

### 多平台后端（linux/darwin/windows × arm64/x64）

当前实施顺序以编译流程重规划的 R2/R4–R6 为准；
[多平台架构整理与优化方案](02-plan/yh-多平台架构整理与优化方案.md)
作为既有平台调查参照。**2026-10-12 用户决定：开发与验证集中在 Linux 平台，
macOS/Windows 等其他平台后接入**；Linux/aarch64 种子、门禁与滚种子流程优先维护。

当前只有 arm64 双方言（GNU/Linux 与 Darwin/Mach-O）；Darwin 方言基础
已在 compiler/gen/target.yh、emit_arm64.yh 与 cmd/driver.yh 就位。x64 后端与
Windows 目标未实施。Linux/aarch64 自举种子已入库（`bin/yh-linux-arm64`，
2026-10-09），Linux 上可直接构建与跑自举门禁；Linux CI 流程按需重建。
**2026-10-13 关闭两条**：macOS 入库种子 `bin/yh` 换成 macOS 主门验过的中间代种子
（`b123acbe…`，可直接编译当前源码，「种子落后自动补代」降级为保险）；
`linux-arm64` CI 作业实测 **6.4 分钟**（`timeout-minutes: 60` 充裕）。证据见
[finish.md](finish.md) 的 2026-10-13 条目。

### LLVM 后端替换（2026-10-14 已授权分阶段实施）

用户目标为**最终替换自研代码生成，yh 静态嵌入 LLVM，不依赖系统 LLVM，全量用例通过**。
本轮已授权制定计划、开始实施，每个阶段验收后提交代码。固定 SDK + 薄 C ABI 桥
取代原外部 clang 方案，正常编译不能调用 clang/llc/opt/llvm-as 或动态加载 libLLVM。
同日顺序调整：**Linux/x86_64 首期实现，在本机 WSL 原生验证**；ARM64 种子经 qemu
仅作启动桥。LLVM-14/15 的 x64 OS/链接/种子部分已前移为 P0，不能等后续平台再做。
先读 [16 项问题清单](02-plan/yh-LLVM后端替换问题清单.md)，再读
[替换设计](03-design/yh-LLVM后端替换设计.md)、
[实施方案](02-plan/yh-LLVM后端替换实施方案.md) 与
[ADR-0014](adr/0014-yh采用LLVM作为正式代码生成后端.md)。
原 [可行性分析](02-plan/yh-LLVM后端接入可行性与差距分析.md) 保留为背景；其 oracle/第二后端
建议不再是当前目标。991/22 为 2026-10-13 文档基线，LL0 必须重测。

LL0 已完成：真实覆盖/来源、工具身份、原生 ELF oracle 与 3×20 性能样本已记录，
详见 finish.md 的 LL0 条目。923 个运行期函数中 22 个 SSA/后端发射，其余 901 个回退；
这不是 LLVM 覆盖通过，后续全覆盖门仍未完成。
LL0E 已完成固定 SDK/C ABI 桥的独立验收：O0/O2、对象/汇编、拒绝层、无 LLVM 动态依赖
和无系统 LLVM 的 chroot 输出门全绿。yh 前端/编译器接入仍在 LL3/LL10，不能当作替换完成。
ARM64 启动 SDK 前置片也已完成：固定 ARM LLVM/zlib/zstd、qemu 下两架构输出与全新
chroot 门全绿，原 x64 复验全绿；新增 `.yh` 源级桥调用生成 x64 对象并原生执行通过。
静态桥的实际编译器入口接入仍在 LL3，不降低运行时导入限制或覆盖要求。
- [x] **LL1 已验收语义与调用政策**：除模/移位/转换/bool/浮点/内存/效果/默认初始化探针；
  区分已定义规则、已复现 bug 和未定义政策；每个真 bug 单独红绿回归与完整门。
  - LLVM-SEM-02 已完成：浮点转 u64 的常量/typed CT 用 i64 中间值，高位正数被饱和截断。
    还复现动态浮点转窄整数在表达式内漏截断：u8(300) 为 300 而 CT 为 44，
    i8(130/-129) 为 130/-129 而目标位型应为 -126/127。
    已新增正式红绿回归，修正 unsigned 64 位中间值及动态窄化；单文件/项目定向门通过，
    完整 make test / make selfhost-native 退出 0（303/303、项目 95/95）。
    NaN/无穷与 64 位饱和后窄化已写入契约；LLVM 标量浮点 lowering 已由 LL6 验收，
    见 [完成记录](01-finished/yh-LLVM-LL6浮点标量-2026-10-17.md)。
  - LLVM-SEM-04 已修复：定宽整数运算后扩大转换存在路径差异；单文件 `(1 << 32).to_type(i64)`
    为 4294967296，而 SSA 为 0；int 最大值+1 在单文件扩大后为正、SSA 为最小值。
    已按源结果位型规范化；编译器宽位掩码显式用 i64，避免依赖旧遗漏截断。
  - LLVM-SEM-05 已修复：已声明为 i64/i8 的常量经一元运算后均错标 int：
    `const maximum i64 = 9223372036854775807; const minimum i64 = -maximum - 1`
    实测为 0，`sizeof(-maximum)` / `sizeof(-small_i8)` 均为 4。先用 u64 位型显式转换
    隔离浮点验收；正式回归已通过，一元类型与 CT/SSA 逻辑非恢复一致，派生常量清除原符号绑定。
  - LLVM-SEM-06 已修复：数组实参仅压入源地址，后续实参修改源后才在被调入口复制；
    `take_snapshot(shared, change_source())` 实测 92，按左到右值参数求值应为 42。
    已保留数组到指针的退化共享，并覆盖间接调用、切片描述符与结构体。
  - LLVM-SEM-07 已修复：f32 常量引用直接把保存的 f64 位型搬到 d0，没有窄化到 s0；
    1.0 的动态 f32 位型为 1065353216，折叠和 typed CT 常量传参的位型均为 0。
    llvm-float-boundaries.yh 正式红绿回归通过；只修复已定义的 f32 装载，不改舍入政策。
  - LLVM-SEM-03：源 bool 为一字节、显式转换保留低 8 位，SSA 按一位规范化；
    单文件观察 2/2/2/1、项目 SSA 观察 0/0/0/0，已复现入参/返回/phi/条件四条路径差异。
    扩大覆盖又暴露 CALL 按块编号校验的顺序错误、块内局部被合并为含 -1 的 phi；
    已有独立红绿复现，bool 一字节值规则和两条 CFG 修复正在重跑全门。
    项目缓存头测试已同步为真实序列化版本 6，95 项项目验收通过。
    已完成修复和串行完整主门：运行 302/302、固定点、自解析和项目 95/95 全绿；
    候选项目探针实际 SSA 发射 8/2 个函数均通过。一次此前的 301/302 未重现，门禁现已
    补齐失败明细，不以猜测替代原因。完成记录见 docs/01-finished/ 与 docs/finish.md。
  - 最终 LL1 门：8/8 单文件、8/8 项目探针；make test / make selfhost-native 退出 0，
    运行 307/307、固定点 24、自解析 71、项目 95/95。LLVM O0/O2 兼容验收继续由后续各阶段承担。
- [ ] **LL2 前端与目标边界**：受检模块、纯 IR 交接、宿主/目标、triple/layout/ABI、接口身份；LLVM 路径不预发旧汇编。
  - 2026-10-14 已按用户要求启动多 agent：目标模型只读审查、CheckedModule 快照、
    ARM64 静态 SDK 同时推进；审查释放名额后继续模块 IR。主 agent 负责前端边界与集成。
    详细文件归属见实施方案；完整门和阶段提交集中执行，各候选临时产物隔离。
  - 首片 LL2-T 目标身份已完成并提交（`c0cd89e`）：四个现有 Unix triple 的 TargetInfo、
    构建时宿主身份、严格目标解析、旧 -target 别名映射、`$if` 与目标源文件筛选共用目标模型；
    定向门与完整门通过（307/307、固定点 24、自解析 72、模块 18/18、项目 96/96），
    独立 agent 的 22 项边界探针通过。历史过程见 [finish.md](finish.md) 的 2026-10-14 条目与
    [完成记录](01-finished/yh-LLVM-LL2目标身份-2026-10-14.md)，本节只保留未完成项。
  - [x] 受检快照、受检前端闸门、模块 IR 与纯快照 lowering 已完成并提交：
    `gen/front_stage.yh`、`ast/checked_module.yh` + `checked_module_verify.yh` +
    `checked_module_ctx.yh` + `checked_module_lower.yh`、
    `ir/ssa_module_00_model.yh` / `_10_build.yh` / `_20_verify.yh`，门禁
    `tests/selfhost/llvm-front-output.py` / `llvm-checked.py` / `llvm-module.py` /
    `llvm-lower.py` 与 fixture `llvmfront` / `llvmchecked` / `llvmmodule` / `llvmlower`。
    当前源码上完整门重跑通过：307/307、固定点 cc3→cc4 共 24 个产物一致、自解析 82 文件、
    模块 18/18、项目 **100/100**；`scalar.yh` 的纯快照 lowering 实测
    `functions=5 phis=2 calls=4`，pointer/aggregate 带真实来源整模块拒绝。
    历史与证据见 [finish.md](finish.md) 的 2026-10-15 条目与
    [完成记录](01-finished/yh-LLVM-LL2受检快照与纯快照lowering-2026-10-15.md)。
  - [x] **损坏 `.s.ct` 触发 worker SIGSEGV（已定位并修复）**：根因是
    `parse/iface_ct.yh` 的 `iface_ct_load` 读了**悬垂的调用方指针**——调用方
    `cmd/module_worker.yh` 用 `pj_pool_str(...)` 取的是可扩容名字池里的地址，
    而 `iface_ct_load` 内部的 `parse_source*` 会把隐藏正文名/形参名/类型名 intern 进
    同一个池；池增长时 `tml_intern_str` 会 `free` 旧块并换新块，调用方指针随即悬垂，
    解析之后的「正文签名不匹配」诊断读它即 SIGSEGV。
    修复：入口把 `path` 快照进本函数栈缓冲，其后 `read_source`/`header_valid`/诊断
    一律用快照（顺带诊断不再打空路径）。该缺陷在 HEAD 就存在（HEAD 的 freed 块首字节
    恰好为 0，只是打出空路径），本修复保留。
    验证：`bisect-ct5b.py ./yh` 正确拒绝、`build-check.py` **100/100**、
    `make test` **307/307**；回退修复的对照树再次 SIGSEGV（因果闭环）。
  - [x] **LLVM 模式接入（2026-10-15 实现，2026-10-18 核对回填）**：
    `--backend legacy|llvm`、`--target`、`-O0/-O2`、`--emit-llvm` 已在
    `cmd/driver.yh` 的 `drv_scan_target` 解析，未知后端/目标明确拒绝、不静默回退；
    单文件在 `run_emit_asm_to` 走 `llvm_emit_single_file`；模块 worker 在
    `c_backend != 0` 时走 `mb_llvm_emit_module`，由 worker 持有受检快照到 IR 交接，
    不进入旧 SSA 替换与机器发射；产物目录、缓存键与链接 manifest 按后端/目标/优化级别
    隔离（`cmd/module_build.yh` 的 `.build/targets/<triple>/llvm/O<n>`、
    `cmd/link_cache.yh`）。依据 LL3 完成记录与 LL9 验收记录。
    **注意**：这只是"可显式选用"，**默认仍是旧后端**，切默认属 LL11。
  - [x] 首片之外的 lowering 已按后续切片推进：LL4 控制流（循环、`switch`、
    `goto`/`label`、`for-in`）、LL5 内存/聚合/模块数据、LL6 浮点标量及 LL7
    间接调用/变参均已交付；LLVM 生产驱动仍归 LL9。
  - [x] 模块 IR 序列化与稳定身份已实现：`ir_module_verify`、版本化
    `ir_module_serialize`/`deserialize`、确定性身份摘要及函数值/调用 ABI metadata
    均由 `tests/selfhost/llvm-module-cache.py` 覆盖。完整生产缓存键仍归 LL9。
  - [ ] 与 R2b 任务私有上下文契约对齐，并记录未闭合的完整版本硬门。
  - 范围说明：宿主操作统一读取 `c_host_target`（目录/时钟/系统调用桥）按设计归后续宿主桥阶段，
    LLVM 生产驱动和完整生产缓存键归 LL9，均不在 LL2 本片。
- [x] **LL3 严格 x64 LLVM 首片（2026-10-15 完成，2026-10-18 核对回填）**：文本 IR、
  整数/布尔、分支/phi/固定调用已接入；`--backend llvm --target x86_64-unknown-linux-gnu
  [-O0|-O2]` 直接产出 EM_X86_64 ELF 并在 WSL 原生运行，不调用任何外部 LLVM 工具、
  不回退旧后端。见 [LL3 完成记录](01-finished/yh-LLVM-LL3命令行模式与对象发射-2026-10-15.md)；
  其首片边界已被后续 LL4–LL10 覆盖（O0/O2 各 343/343 语料、x64 原生连续自编）。
- [x] **LL8a 内存 helper**（2026-10-15 完成）：LLVM 模块发射 memcpy/memset/strlen
  弱定义 + llvm.used，O0/O2 对象与原生边界驱动全绿；见
  [完成记录](01-finished/yh-LLVM-LL8a内存helper-2026-10-15.md)。
- [x] **LL7 调用/ABI**（2026-10-17 完成；LL4 控制流、LL5 内存/聚合与 LL6 浮点已完成）：与 R2a/NP3
  同源切片合并验收，不另做一套重复迁移。
  - [x] 2026-10-17 首片：Linux/x86_64 SysV 固定参数 C ABI 标量直接调用；窄整数 `signext`/`zeroext`、
    指针、f32/f64、混合参数、栈参数、yh↔C 双向运行及 C bool 拒绝门已通过。
    详见 [LL7 首片记录](01-finished/yh-LLVM-LL7-CABI标量直接调用-2026-10-17.md)。
  - [x] 2026-10-17 S2：固定参数 C `_Bool` 使用 `i1 zeroext`；YH 内部 bool 字节在 ABI 边界按非零归一，
    并覆盖跨模块、双向 C 调用和非规范 bool 返回；clang oracle 与 O0/O2 门通过。
    详见 [LL7-S2 记录](01-finished/yh-LLVM-LL7-CABI-bool-2026-10-17.md)。
  - [x] 2026-10-17 S3：YH 内部 ABI 采用版本化显式副本/结果缓冲；结构体、定长数组、切片参数与返回跨模块 O0/O2 运行通过。ABI id 进入 IR/缓存身份，内部符号带版本后缀。
  - [x] 函数值类型、接口和缓存身份保留 ABI/变参 metadata；YH 与 C 函数指针跨模块传递、返回和间接调用通过。
  - [x] 2026-10-17 SysV INTEGER/SSE/MEMORY C 聚合分类、coercion/sret/byval；CPair、CMixed、CWide 与 clang IR oracle 对照，O0/O2 双向真实运行通过。详见 [LL7-S4 记录](01-finished/yh-LLVM-LL7-SysV-C聚合ABI-2026-10-17.md)。
  - [x] callback 双向闭环：C 调 YH、YH 调 C 返回函数值，覆盖标量与 CPair INTEGER 聚合参数/返回；YH `vararg=2` 按序打包为切片参数。
  - [x] `@[noreturn]` 属性进入模块接口与缓存；合法定义检查、违约调用 trap、移除/恢复接口属性后的调用方重编，以及用户裸 C 变参源码拒绝均有测试。
  - [x] `python3 tests/selfhost/llvm-abi.py --compiler-path ./yh` 的 O0/O2 双向互调、LLVM 验证/优化/链接/运行及拒绝门全过；全仓门与种子状态见 [LL7 完成记录](01-finished/yh-LLVM-LL7-完整调用与ABI-2026-10-17.md)。ARM64 HFA 已于 2026-10-20 由 F1 接入（见 `llvm-linux-arm64.py`）。
  （2026-10-15 LL5 第一切片完成：局部标量 alloca/load/store 与 `&变量`/`*p`；见
  [完成记录](01-finished/yh-LLVM-LL5局部内存首片-2026-10-15.md)。）
  （2026-10-15 LL5 数组切片完成：局部定长数组字面量/下标/取址/复制；见
  [完成记录](01-finished/yh-LLVM-LL5数组切片-2026-10-15.md)。）
  （2026-10-15 LL5 结构体切片完成：字段/嵌套/字面量/复制/联合体；见
  [完成记录](01-finished/yh-LLVM-LL5结构体切片-2026-10-15.md)。）
  （2026-10-15 LL5 切片切片完成：数组切片/切片字面量/共享下标/len；见
  [完成记录](01-finished/yh-LLVM-LL5切片切片-2026-10-15.md)。）
  （2026-10-17 LL5 内存/聚合/模块数据全量完成：CT backing、静态指针重定位、全局
  切片、导入 `pub const` 独立副本、私有隔离与重叠复制均已验收；`make test`
  318/318、固定点 24、自解析 92、模块 18/18、项目 101/101，LL5 memory suite 全绿。
  见 [完成记录](01-finished/yh-LLVM-LL5全量收尾-2026-10-17.md)。）
  （2026-10-15 LL4 首片完成：嵌套循环、break/continue、无限 `for {}`；见
  [完成记录](01-finished/yh-LLVM-LL4循环首片-2026-10-15.md)。）
  （2026-10-15 LL4 switch 切片完成；见
  [完成记录](01-finished/yh-LLVM-LL4switch切片-2026-10-15.md)。）
  （2026-10-15 LL4 goto/label 切片完成；见
  [完成记录](01-finished/yh-LLVM-LL4goto切片-2026-10-15.md)。）
- 2026-10-17 **LL4 for-in 完成**：数组/切片与左闭右开整数区间、元素/可选下标绑定、
  嵌套、break/continue 和聚合元素按值复制；O0/O2 原生门及仓库主门通过。见
  [完成记录](01-finished/yh-LLVM-LL4-for-in-2026-10-17.md)。
- 2026-10-17 **LL6 浮点标量完成**：LLVM f32/f64 常量、算术、IEEE 比较、整浮转换与
  局部内存已通过 O0/O2 专项门和仓库主门；完整记录见
  [完成记录](01-finished/yh-LLVM-LL6浮点标量-2026-10-17.md)。
- [x] **LL8b x64 完整运行时/宿主桥**（2026-10-17）：allocator/printf 与内存 helper、
  x64 syscall、目录/时钟平台拆分及进程 C ABI 通过 O0/O2 原生运行和导入/libcall 审计；
  ARM64 旧分支与 `runtime-memory.py` 原断言保留。`make test` 323/323，
  `make selfhost-native` 固定点 24、自解析 97、模块 18/18、项目 103/103；
  新 Linux/aarch64 种子 SHA-256 `4b2f4a3e111e33eecd5ca48bc712e6b3b6a2f0ddfe68bfd8063f7bd15f4c1d94`。
  详见 [LL8b 完成记录](01-finished/yh-LLVM-LL8b-完整运行时与宿主桥-2026-10-17.md)。
- [x] **LL9 驱动/缓存/提交**：单文件与模块统一、完整键、失败事务、目标检查均完成；
  Linux/x64 LLVM 单文件 `-o` 也统一使用 lld worker 或按目标选择的链接驱动，并以临时文件
  校验后发布。新增 `llvm-single-link-target.yh` 锁定目标选择和失败保留。详见
  [LL9 完成记录](01-finished/yh-LLVM-LL9-统一入口缓存失败发布-2026-10-17.md)。
  2026-10-18 LL9 补充 runner 的 O0/O2 均通过 335/335；LL10 全门增加无限循环返回回归后，
  当前 O0/O2 均通过 343/343，原 LL10 前置覆盖缺口已闭合。
- [x] **LL9L 内嵌 lld 链接器（生产路径、独立探针与 x64 自举汇合完成）**：将 lld 21.1.8
  静态归档（liblldCommon/ELF/MachO/COFF）与 C++ shim 链进 yh，Wasm/MinGW 归档保留在 SDK
  但不进入链接组；链接步在进程内
  由 `lld::lldMain` 完成；切片、裁剪决策与验收见
  [方案 §LL9L](02-plan/yh-LLVM后端替换实施方案.md)，实测证据见
  [可行性实测](01-finished/yh-内嵌lld可行性实测-2026-10-15.md) 和
  [LL9L 验收记录](01-finished/yh-LLVM-LL9L内嵌lld-2026-10-18.md)。SDK 固定采用
  全组件发行包（LLVM 226 组件并含 Polly），本片不建设源码裁剪流水线；当前生产 lld
  目标为 Linux/x86_64，Mach-O/PE 仅有交叉格式探针。此前从 AArch64 种子构建的编译器携带
  lld stub，`llvm-cache.py` 的“x64 最终链接不应 fork cc/ld”断言未能证明 x64 链接路径；
  L9L-6 后续已在 Linux/x86_64 原生候选上闭环：B/C/D 未调用 gcc wrapper，D-O0/O2 内嵌 lld 身份与
  固定 SDK 21.1.8 一致，`readelf -d` 未发现 LLVM/lld 动态依赖，O0/O2 各 24 个产物固定点一致；
  详见 LL9L 验收记录的汇合补录。
- [x] **LL10 x64 原生自举**：ARM64 种子经 qemu 产 A，A 用 LLVM 产原生 B，B/C/D 原生连续自编；
  O0/O2 分别 `.ll/.s.i/.s.ct` 固定点、全量门、实际覆盖，并记录 R2b 任务私有状态/真正线程池/
  增量/并发/确定性硬门状态。LL10 已于 2026-10-18 全门关闭；R2b 未完成项仍独立追踪，
  不由 LLVM 门结果覆盖，LL11 默认切换继续受其阻挡。2026-10-19 起线程并行
  拆为 R2c（并发标准库之后），LL11 切默认随之以 R2b 剩余 + R2c 全部关闭为前提。
  - [x] 2026-10-18 原生链：A/B/C/D 均为 ELF machine=62；O0/O2 的 B→C 与 C→D 各 24 个
    `.ll/.s.i/.s.ct` 逐字节一致；最终 D 自解析 98/98，语言 O0 语料 343/343，模块语法 18/18。
  - [x] 完整门：最终 D 自解析 98/98；LLVM O0/O2 各通过 343/343、模块 18/18、项目 104/104；
    LL9L、缓存、驱动与 runtime-memory 专项通过。`make test-llvm` 与 `make selfhost-llvm` 均退出 0。
    详细日志在 `tmp/ll10/make-test-llvm-after-fix.log`、`tmp/ll10/selfhost-llvm-after-fix.log`。
  - [x] 实际消费覆盖：`libs/` 由 stdlib 项目验收覆盖；独立项目 `asm/`、`link/`
    已于 2026-10-20 删除。R2b 线程池/任务私有状态仍单独记录在编译流程待办中，
    LL11 默认切换不得越过该硬门。
  - [x] LL10 前置 LLVM x64 全量语料差异：runner O0/O2 均通过 335/335；随后新增无限循环返回回归，
    收尾全门当前为 343/343。修复覆盖聚合返回值、编译期边界、切片存储生命周期、数组到切片视图及诊断预期；
    O0/O2 分别验收，详见 LL9 补充与 LL10 完成记录。
- [x] **linux-x86_64 CI 作业首跑验证（2026-10-19 补配置）**：该作业此前从未运行
  （推送触发只监听 `arm64`/`main`，工作都在 `llvm` 分支）。2026-10-19 已补：
  push 触发加入 `llvm` 分支；作业 env 加 `YH_LLVM_HOST: "1"`；新增
  `tmp/llvm-migration` 的 actions/cache。2026-10-20 首跑全绿：固定 SDK 缓存命中、
  qemu 下 A→B/C/D 与 O0/O2 全门通过，退出 0；x64 发布归档见
  [完成记录](finish.md#2026-10-20-005-补档-linuxx86_64-release)。
- [ ] **LL11 x64 性能与默认切换**：至少 20 轮对照，原生默认全门绿后滚独立 `bin/yh-linux-x64` 与哈希；
  ARM64 种子不被覆盖，工具依赖与发行说明同步。
  - [x] **默认切换与 x64 种子（2026-10-19）**：Linux/x86_64 宿主默认 LLVM
    后端（`compiler/gen/state.yh`）；`bin/yh-linux-x64`（`c6733eb2…`）已滚；
    冷编、单文件运行与 `make test` 分段验证通过；Makefile 对 x64 自动
    `YH_LLVM_SELFHOST=1` 并切换缓存/运行时专项门。
  - [x] **隔离环境验证（2026-10-19）**：`make llvm-isolation` 在 bwrap +
    `PATH=/nonexistent` 下通过：无 LLVM/lld 动态依赖、execve 无外部 LLVM 旁车、
    冷编自举 `fallback_functions=0`；见
    [完成记录](01-finished/yh-LLVM-LL11隔离环境验证-2026-10-19.md)。
  - [x] **x64 Release 归档（2026-10-20）**：`release.yml` 增加
    `linux-x86_64` 与 `x64_only` dispatch；`0.0.5` 已补
    `yh-0.0.5-linux-x86_64.tar.gz`（x86_64 ELF，D-O2），arm64/darwin 未重跑。
  - [ ] 20 轮性能对照与回退归因（用户暂缓）；发行/CI 文档同步；
    R2b 硬门（RS2/RS3/R2c）关闭前不宣布 LL11 全量完成。
- [ ] **LL12 退役旧后端**：F1 已通过，LL11 的 R2b/性能硬门关闭后，分片移除
  失去消费者的机器发射；不阻挡 x64 首期，也不删除 gen 语义或历史种子。
- [x] **F1 Linux/AArch64 LLVM 默认后端（2026-10-20 完成）**：AArch64 syscall/runtime、
  `va_list`、AAPCS64 标量/HFA/小聚合/大聚合、C↔YH 双向回调、内嵌 lld、
  默认后端切换、容器全门与种子滚动均已完成。`make test` 全绿（运行 344/349，
  5 个 Darwin SKIP）；`make selfhost-native` cc3→cc4 24 产物固定点、自解析
  104、F1 O0/O2 门、LLVM 缓存门、项目 105/105；O2 连续自编 B/C SHA-256 相同。
  种子 `bin/yh-linux-arm64` = `4d13e297…`，无构建机闭包路径。详见
  [完成记录](01-finished/yh-Linux-ARM64-LLVM-F1-2026-10-20.md)。
  - [x] **F1-2 生产链接**：arm64 lld 21.1.8、固定 GCC ELF 模板、链接缓存身份与
    自举闭包运行时文件。
  - [x] **F1-3 自举门**：`native-selfhost.py` 支持 Linux/AArch64 LLVM（含旧种子
    legacy 过渡）；`make selfhost-native` 覆盖 O0 固定点，O2 连续自编单独验收。
  - [x] **F1-4 默认切换**：Linux/AArch64 默认 LLVM；滚种子与哈希。
  - [x] **F1-5 CI**：`linux-arm64` 作业增加固定 arm64 LLVM/lld 宿主缓存、
    `YH_LLVM_HOST=1` 与 `libxml2-dev`；`make selfhost-native` 内含 F1 运行时门。
  - [ ] **F1-6 可选后续**：x64 专用 `llvm-selfhost.py` 若需 ARM64 变体再参数化；
    跨宿主（x64 上跑 arm64 种子）链接模板策略单独立项。
  - [ ] **CircleCI 首次实跑**：连接 GitHub 仓库后观察 `antlr` 与
    `linux-arm64`，确认 LFS 种子、LLVM 宿主缓存命中与 `SKIP_CORPUS=1`
    的实际耗时；首次需构建固定 arm64 LLVM/lld 宿主。

- [ ] **F2–F4 后续平台**：macOS/ARM64 → Windows/x86_64 → macOS/x86_64、Windows/ARM64；
  各格分别验收对象、链接、标准库运行、原生编译器、原生自举，不以 WSL 冒充 Windows 支持。

- [x] **macOS 入库种子落后于 llvm 分支（2026-10-18 已解决）**：原 `bin/yh`
  （`b123acbe…`，2026-10-13 的中间代种子）冷编当前 `compiler/` 时在
  `gen/target_info.yh` 报「编译期常量尚未就绪」，`make` 与
  `tools/seed-build.py` 均直接失败；而 Linux/aarch64 种子 `8ea2a9ac…`
  （2026-10-18）与源码同代、全门已过。
  **2026-10-18 处理**：按 `b037127` → `8fe3c80` → HEAD 逐代补代（每代 2–9 秒），
  同时把两处 macOS 阻塞点正式化为源码里的平台分支——`backend/llvm_bind.darwin.yh`
  提供桥桩（固定 SDK 只有 Linux 宿主）、`cmd/link_cache.yh` 在 Darwin 目标跳过
  GCC 风格链接查询。新种子滚为 `bin/yh-darwin-arm64`（`9d911d0b…`），
  `tests/yh-run` 语料 **342/343**（唯一失败是 Linux 专用 syscall 语料）。
  详见 [finish.md](finish.md) 同日条目与
  [完成记录](01-finished/yh-macOS种子补代与平台命名-2026-10-18.md)。
- [ ] **macOS 仍不能跑 LLVM 后端与 `test-llvm`**：`Makefile` 只在 Linux 宿主设置
  `LLVM_HOST`，固定 SDK 也只有 `linux-x86_64` / `linux-aarch64`；
  `test-llvm` 在 `Makefile` 里硬性要求 Linux/x86_64。这两条是平台能力边界，
  不是种子问题；要支持需发布 Darwin 版固定 SDK 与对应链接/签名路径（归 F2）。
  2026-10-19 已完成[macOS/ARM64 LLVM 迁移差距分析](02-plan/yh-macOS-LLVM迁移差距分析.md)：
  emitter 仍只接 Linux，C 桥还漏 `aarch64-apple-darwin`；其余待办为 Darwin
  静态 SDK/宿主脚本、Apple C ABI、非 Linux/x64 runtime、Mach-O 生产链接/签名、
  SDK/实际工具链缓存身份与 Darwin LLVM O0/O2 原生全门/自举。按 F2 分片推进，
  未修改既有平台顺序、默认切换与滚种子门槛。
  同日补充 Linux/x64→Darwin/ARM64 交叉引导可行性：F2 还需目标版 LLVM/桥依赖注入、
  Linux 上的 Mach-O 交叉链接配置与 Mac 原生候选固定点；属于可选引导来源，
  尚未实施，不因 Linux 自举完成而自动获得。
- [x] **macOS/ARM64 LLVM 接入方案交付（2026-10-19）**：
  [设计](03-design/yh-macOS-LLVM后端接入设计.md)与
  [实施方案](02-plan/yh-macOS-LLVM后端接入实施方案.md)已整理；用户确认
  **先 Mac 原生 LLVM 自举、再 Linux/x64 交叉引导验收**。以下实施项仍未完成：
  - [x] **F2-0**：冻结 arm64 Darwin 目标、候选部署版本 14.0、SDKROOT/版本解析契约，
    固定 LLVM 21.1.8 官方源码归档 SHA-256，并保留目标布局/拒绝基线报告。
  - [ ] **F2-1（实现已落地，门禁收尾中）**：固定 LLVM 21.1.8 Darwin 静态包按 CLT SDK 26.5
    构建完成；真实桥/host 契约和 `make test-llvm-darwin` 通过，Mac SDK 的 libc++/libSystem
    reexport 和内嵌 lld 探针通过。macos-14 CI 候选尚未单独验收；`make selfhost-native`
    在继承的 `runtime-memory.py` 因自编译器导入 C runtime `strlen` 失败，因此未滚种子。
  - [ ] **F2-2（功能门通过，主门收尾中）**：部署版本/SDKROOT 校验、Darwin IR、PIC Mach-O
    对象/汇编及 LC_BUILD_VERSION 已接通；O0/O2 改 minOS 会失效缓存并生成新版本对象。
    Darwin 定向门和 `make test` 通过，`make selfhost-native` 仍受 F2-1 所述继承失败影响。
  - [x] **F2-3**：Apple 标量 C ABI、窄整数属性、直接/间接回调通过 Clang 21.1.8 oracle，
    LLVM verifier 与 O0/O2 Mach-O 双向互调通过；见 `make test-llvm-darwin`。
  - [x] **F2-4**：Darwin raw `ld64.lld` 一次性 worker，单文件和项目共用
    `-arch arm64`、`-platform_version`、`-syslibroot`、PIE、`libSystem` 与 ad-hoc 签名参数；
    接入 `LIBRARY_PATH`/项目 `-l`，校验 Mach-O CPU、部署/SDK 版本和签名 load command，
    链接失败保留旧产物及旧成功 manifest。内嵌 lld、签名、失败原子性和双模块 O0/O2 门通过。
  - [x] **F2-5**：独立 `llvm_apple_abi.yh` 支持非 HFA
    1/3/8/9/16 字节聚合、24 字节间接参数/sret、嵌套 HFA、HFA 寄存器耗尽，以及
    全部成员同浮点基型的**联合体 HFA**（元素数取最宽成员）；固定 Clang oracle、
    O0/O2 双向 C↔YH、聚合函数指针与 C→YH→C callback 均通过 `make test-llvm-darwin`。
    prelude `printf` 的 Darwin 变参/`va_list` 已随 F2-6 联测通过；用户裸 C 变参仍拒绝。
  - [x] **F2-6**：Darwin `mmap/munmap` allocator、`write` 输出、整数/字符串格式化与
    `va_list` 变参、`memcpy/memset/strlen` 等弱隐藏 helper、`open` 三参变参白名单、
    导入审计（只留 mmap/munmap/write 等 OS 接口）；libs 时间/文件/目录与
    fork/execvp/waitpid 消费者在 O0/O2 原生通过。
  - [x] **F2-7**：Darwin SDK/stub 内容身份、缓存失效与失败提交专项。对象键新增显式
    PIC 标记；链接键新增 `libSystem` 的 `reexported-libraries` 闭包（逐项哈希
    `/usr/lib/system/*.tbd`，深度有界）。`tests/selfhost/llvm-darwin-cache.py`（配
    `tests/modules/projects/llvmdarwincache/`）覆盖：热命中、同路径内容变化只影响
    实际粒度、minOS 14→15→14 键值复现、SDKROOT 切换、stub 内容变化只失效链接键、
    失败保留旧产物、manifest/对象/接口/可执行文件损坏重验、构建中断与临时残留、
    两次并发构建。
  - [x] **F2-8**：Darwin 显式 LLVM 原生连续自举。`tests/selfhost/llvm-darwin-selfhost.py`
    从入库种子 legacy 编 A，A 以 LLVM 编 B/C/D；O0/O2 的 B→C→D `.ll/.s.i/.s.ct`
    逐字节固定点，冻结各代 checked/emitted/rejected/fallback；D 自解析 104/104、
    语法/运行/模块/项目全门与 Darwin 专项门全绿，隔离 PATH 下无 clang/ld/lld/
    codesign/xcrun 调用，候选仅动态依赖 libSystem/libc++。`make selfhost-llvm-darwin`
    已接入 Darwin CI（手动触发，上传 stats/logs/snapshots）；macos-14 实跑待 CI。
  - [ ] **F2-9**：Linux/x64 交叉产 Mac 候选，再在 Mac 原生自举验收。
    - [x] **Darwin SDK bundle（2026-10-19）**：`compiler/darwin-sdk/` 随编译器
      分发聚合 `libSystem.tbd`（SDK 26.4，334KB）、`SDKSettings.json` 与
      `manifest.json`；查找顺序 `SDKROOT` → `YH_DARWIN_SDK` → 可执行文件附近
      bundle → 原生 `xcrun`。`tests/selfhost/llvm-darwin-bundled-sdk.py` 在
      清空 SDKROOT/无 xcrun、假工具 PATH 下链接运行成功，`sdk 26.4`；
      `SDKROOT` 覆盖仍生效。C 源/libc++/目标包/frameworks 等遗留边界见
      [设计文档](03-design/yh-Darwin交叉编译遗留边界.md)。
  - [x] **F2-10**：Darwin/ARM64 默认后端切到 LLVM。`state_init` 对
    `DARWIN+ARM64` 置 `c_backend=1`；Makefile 对 `darwin-aarch64` 选择
    Darwin runtime/cache 门并把 project 验收显式切 LLVM；`native-selfhost.py`
    自动识别 Darwin LLVM，并用“旧种子 legacy 过渡代 → LLVM 连续代”处理滚动前
    自举。新增 `tests/selfhost/llvm-darwin-default.py` 断言无 `--backend` 时
    emitted=checked、fallback=0、产物在 `targets/aarch64-apple-darwin/llvm/O0`。
    默认 `make test`（347/348）、`make selfhost-native`、`make test-llvm-darwin`
    （19 项）与 `make selfhost-llvm-darwin` 全绿；`bin/yh-darwin-arm64` 已滚到
    72MB 的 LLVM 默认种子（`2be836b7…`），新种子冷编与默认门复验通过。
    **2026-10-19 用户决定**：20 轮性能对照与 RS2/RS3/R2c 后置为专门性能工作；
    本轮按正确性切默认，不宣布 LL11/F2 性能门或“首个完整 SSA 版本”完成。
- [x] **语料平台筛选（2026-10-18 完成）**：`tests/yh-run/check.py` 新增
  `// platform: <tag>` 头部指令——无指令为共有用例（所有平台跑），带指令只在匹配
  的运行平台执行、其余记 `SKIP` 不计失败；tag 为 `<os>` 或 `<os>-<arch>`，
  `<os>` 匹配该 OS 的所有架构，`--cross` 按 Linux/aarch64 计。
  `run/llvm-linux-x64-host.yh` 已标 `// platform: linux`（正文对两个架构都有
  syscall 号分支）。`make test` 在 macOS 上因此退出 0（342/343 + 1 跳过），
  不再需要为别的平台准备运行环境。见 [完成记录](01-finished/yh-测试平台筛选-2026-10-18.md)。

16 项代码/架构问题均未关闭；已完成的本轮文档交付记入 finish.md。

### 玉衡 VS Code 扩展

方案见 [VS Code 扩展方案](02-plan/yh-VSCode扩展方案.md)。首发桌面本地；
独立 TypeScript 语言服务器；源码调试待编译器生成调试信息后实施。

- [ ] **VS-U0**：最小扩展、`.yh` 高亮、独立 LSP 进程、构建/运行命令。
- [ ] **VS-U1**：基于现有 `yh` CLI 的保存后诊断与进程取消。
- [ ] **VS-U2**：自举编译器分析接口、未保存缓冲区、精确跨文件定义跳转。
- [ ] **VS-U3**：源码调试信息与 DAP 接入。
- [ ] **VS-U4**：扩展集成测试、VSIX、发布与 CI。

### 编译器可选收尾

- [ ] **旧 ARM64 后端：直接调用返回的聚合指针比较再取逻辑非**（2026-10-16
  全局数据验收时复现）：`if (!(address() == &cell))` / `if (!(address() != 0))`
  在 `address` 返回同一全局对象地址时仍进入错误分支，预期退出 0、实测退出 1。
  已隔离到 `tmp/llvm-migration/llvm-global-source/legacy-bang-pointer.yh`；汇编在
  `cset` 比较后又用 `mov 1` 覆盖结果，疑似运行期比较保留了常量标记，尚待单独
  根因验证。本片用 bool 局部绑定锁住相同指针 EQ/NE，不扩展修复旧后端。
- [ ] **旧 ARM64 后端：读取含非空指针成员的全局结构体后续整数字段**（2026-10-17
  LL5 审计时复现）：`GlobalText{ label: "nested", value: 9 }` 后读取 `text.value`
  应为 9；入库种子与当前候选均可构建，但程序都以 1 退出。LLVM O0/O2 专项读取该字段
  通过，因此这是旧后端基线缺陷，不阻塞 LL5；隔离探针与两代运行结果见本轮
  `tmp/ll5-complete/global-struct-ptr-value.yh` 及构建日志。
- [ ] **旧 ARM64 后端：for-in continue 跳过计数递增**（2026-10-17 LL4 回归时发现）：
  `parse_for` 把 continue 目标设为条件标签，continue 会绕过 `sem_forin_step`，循环可能不结束。
  LLVM 专项探针验证了新后端正确回边；通用旧后端语料暂用等价条件分支覆盖。

对象缓存键已包含编译器二进制内容（见 finish.md 同日项目增强记录），
相关未完成事项归入本轮流程与缓存设计，不再重复列“补编译器身份”。

## 设计决定不做（非缺口，勿列为任务）

- **编译器模块 worker 上限（原 TG-3）**：`compiler/cmd/build_scheduler.yh` 的
  `active < 4` 保持 ADR-0009 的过渡默认。2026-10-15 实测一次冷编 33.7s，阶段
  分解为 project 1.27s / schedule 9.07s / object 14.04s / link 8.59s，
  `workers_peak=4`；把上限放宽到 8 预计每次冷编只省 5–8s（自举门 3 次冷编共
  约 20s，占全量门约 5%），却要改编译器源码、补用例、重编并滚种子，峰值内存
  还会从约 490MB 升到约 800MB。收益不足，不做；将来若有更多核的宿主再议。
- **批量 `--syntax-check`（原 TG-4）**：并行 + 暂存后 L2 只剩约 17s、cc4 自解析
  约 10s，批量模式最多再省十几秒，同样要动编译器源码，性价比更低。
- 本轮 C FFI 不开放用户裸 C 变参，libc `printf` 互操作暂缓；yh runtime
  `printf` 继续使用现有规则。后续需单独设计并验证平台变参与参数提升。
- 切片越界与生命周期运行时防护（ADR-0001）。
- **`pub const A *char = base.TEXT;`（初始化式是模块限定名）**：名字池里没有
  限定名，只取尾段会指向**本模块**同名符号，属错误语义（编译期第 7 条，已决议）。
- **经指针写入编译期模型**（`&TABLE[0]` 后 `*p = 5`）：保持只读拒绝（fail/153），
  与字符串只读池同一策略；如需要「编译期可写全局聚合常量副本」再单独设计。
- **顶层 const 折叠 `$mk()[0]`（对 CT 调用结果直接下标）仍不支持**
  （2026-10-09 已决议）：前端折叠路径无法索引裸聚合对象指针（架构限制），
  惯用写法 `const T = $mk(); T[0]` 经编译期模型可用；如需要可在实参折叠层加
  「调用+下标」特殊形态，暂记现状不作。
