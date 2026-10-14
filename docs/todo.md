# todo

只记录**未完成**事项。已完成任务的历史与验证证据见
[finish.md](finish.md) 与 [01-finished/](01-finished/)；方案文档在
[02-plan/](02-plan/)，取舍见 [adr/](adr/)。

## 待办

### yh-asm 与 yh-link（2026-10-02 规划；2026-10-03 起在 link/ 独立项目实施）

平台与架构矩阵（Linux/macOS × arm64/x64）的顺序、门槛与依赖见
[平台与架构矩阵方案](02-plan/yh-link平台与架构矩阵方案.md)。要点：
Linux/arm64 已在推进；macOS/arm64 要写第二个对象写出器（出口增量，解析与
编码全复用，验收用宿主 Xcode 的 `ld64` 不用容器）；**x64 必须先有编译器后端**
（`compiler/backend/` 目前只有 `arm64.yh`），否则 x64 汇编器是没有输入方的死
代码，这一条待用户确认再动。

用户确认 **Linux/AArch64 优先，随后 macOS/arm64**。完整
[设计](03-design/yh-asm与yh-link设计.md)与
[分期实施方案](02-plan/yh-asm与yh-link实施方案.md)细化现有 R4/R5。
2026-10-03 起按用户决定独立立项，工具链在仓库根分**两个独立项目**：

- **`asm/`（yh_asm，汇编器）**：汇编文本 → 可重定位对象（ELF64 `ET_REL` /
  Mach-O `MH_OBJECT`）。TC1–TC3 + TC8 的实现在这里，见
  [asm/README.md](../asm/README.md)。
- **`link/`（yh_link，链接器）**：对象 → 可执行映像（静态 ELF、Mach-O
  装载、签名）。**TC4（Linux/AArch64 静态 ELF）已于 2026-10-13 完成**，
  见 [link/README.md](../link/README.md) 与
  [设计](03-design/yh-link静态ELF链接器设计.md)；TC9/TC10 未实施。

两者**互不依赖、互不 import**，只通过标准对象文件交接；验收门分别是
`python3 asm/tests/check.py` 与 `python3 link/tests/check.py`。
2026-10-07 目录整理把原先寄放在 `link/` 里的汇编器实现整体迁到 `asm/`，
按职责归位（记录见
[归位记录](01-finished/yh汇编器与链接器项目归位-2026-10-07.md)）。

**2026-10-12：汇编器 `asm/`（yh_asm）稳定化 ASM-0–ASM-8 已完成并断电**（方案
[yh-asm 汇编器稳定化实施方案](02-plan/yh-asm汇编器稳定化实施方案.md)、完成记录
[yh-asm 稳定化](01-finished/yh-asm稳定化-2026-10-12.md)）：`-t linux` 接受
编译器 GNU 方言、8 个模块原文汇编并与 clang 逐节/逐重定位一致、拒绝层与诊断门
就位、链接运行差分 159/0/10、影子验收固定点 0 不一致、Darwin 输出由字节快照守住。
剩余的未完成事项与明确的边界：

- [ ] **接入编译器（未开工，2026-10-12 决定）**：`compiler/cmd/link_cache.yh` 的
  `mb_asm_tool` 仍按 `yh_link`（及 `YH_LINK`）查找、按 `asm` 子命令调用。
  **2026-10-12 已断电**：`make yh-link` 过渡别名与根目录入库的 `yh_asm`/`yh_link`
  副本删除并进 `.gitignore`，编译器因此查不到、回落 `clang`/`gcc`（WSL/Linux 上
  不再需要 `YH_LINK=/nonexistent` 绕过）。重新接入（查找名切到 `yh_asm`/`YH_ASM`、
  产物与安装布局、缓存键纳入工具版本、默认切换、滚种子）待稳定判据 S1–S7
  全过后另立。
- [ ] **长条件分支放宽（明确不做）**：`b.cond`/`cbz`/`cbnz` 距离 ±256 KB，
  越界报诊断；编译器最大模块 `.text` 已 413 KB（8 个模块实测 35–413 KB）但
  没有出现越界的条件分支（本工具与 clang 都能汇编）。真出现时再评估放宽。
- [ ] **`.size` 的符号表达式（明确不做）**：契约 v2 已按实测收窄为「只接受纯
  数字」；编译器语料里没有 `.size`，出现真实消费者时再设计。
- [x] **寄存器同名符号（编译器侧缺陷，2026-10-13 已修）**：用户函数/全局名
  `w12`、`x0`、`lr` 等与寄存器同名时，编译器曾原样发射 `bl w12`（clang 的
  集成汇编器拒绝、GNU as 容忍）。现在这类符号的**最终汇编名**追加 `__yhreg`
  后缀（`.text`/`.data`/`.bss` 与所有引用位置共用判据，模块后缀与 Darwin `_`
  前缀已经避让的不动）。`tests/yh-run/run/182-register-named-symbols.yh` 用
  新增的 `asm-symbols-safe` 指令守住；`14-many-args` 等语料不再依赖放宽。
- [ ] **macOS 原生 macho 两门未验证**：本轮环境只有 Linux，
  `macho_corpus_check.py` / `macho_link_run.py` 未执行；Darwin 输出目前只由
  `asm/tests/darwin-snapshot.txt`（9 个文件的字节快照）守住不回退。
- [ ] **性能（待原生数据）**：同一批编译器模块语料（8.98 MB）clang 5.52 s vs
  yh_asm 41.18 s；WSL 上 yh_asm 走 qemu 模拟（自建基准实测模拟因子 2.2–3.0×），
  折算原生 arm64 约 2.5–3.5×。接入决策前需要原生 arm64 实测，再决定是否做
  热路径优化。
- [ ] **汇编 oracle 补验**：2026-10-14 已核对 WSL 的 llvm-mc/clang 等工具为 21.1.8，
  原工具缺失项关闭；尚需用 llvm-mc 复跑汇编差分门，补“llvm-mc 与 clang 两条
  oracle 都绿”的交叉证据。本轮 LLVM 方案交付没有重跑该门。
- [ ] **TC3 容器链接门剩余：Darwin 方言语料的运行时桩**：容器差分门里 7 个语料
  因 `__Exit`/`_strtoul`/`_open`/`_close`/`_abs` 在 `tests/elf/yhr.s` 没有桩而跳过，
  另有 2 个语料因 `_mmap` 桩不全段错误（参照对象同样崩）。2026-10-12：ASM-4 已用
  `tests/elf/yhr-linux.s` 在**原生门**补齐（159/0/10 全绿），容器门那一份
  （Darwin 方言 `tests/elf/yhr.s`）仍未补。
- [ ] **TC4 的剩余项（主体 2026-10-13 已完成）**：TC4 的静态 ELF 链接主体已
  落地并通过验收（见 [finish.md](finish.md) 的 2026-10-13 记录与
  [设计](03-design/yh-link静态ELF链接器设计.md)）。未完成的是：
  - [ ] **arm64 原生验证**：本机是 Windows + WSL（Ubuntu x86_64），产物经
    qemu-user/binfmt **模拟执行**；需在 arm64 真机或 arm64 容器上复跑
    `make yh-link-probe FULL=1`，把"模拟通过"提升为"真机通过"（并入仓库既有的
    arm64 CI 作业）。
  - [ ] **长调用跳板**：分支超出 `imm19`/`imm26` 范围时首版直接报错，不生成
    跳板；等出现真实需求（编译器大模块 + 远距离调用）再设计。
  - [ ] **接入编译器**：见上一条「接入编译器」待办与
    [实施方案 §6](02-plan/yh-link静态ELF链接器实施方案.md)。**前置第一步**是把
    编译器的汇编器查找从 `yh_link` 改成 `yh_asm`——真链接器占用 `yh_link`
    这个名字会直接破坏现有 `make`，本轮因此刻意只在 `link/.build/` 产出产物。
  - [ ] **Mach-O 目标（TC9/TC10）**：`-t darwin` 目前显式报错；分段布局、
    `LC_MAIN`、绑定流与 ad-hoc 签名未实施。
  - [ ] **首版明确不支持**：TLS / 弱符号 / COMMON / 符号可见性 / 链接脚本 /
    归档库（`.a`）/ 动态链接 / PIE；遇到即报诊断而不是静默算错。
  - [ ] **映射符号（`$x`/`$d`）不进输出符号表**：反汇编器看到的符号名会少
    这些标注；不影响运行，如需保留另立任务。
- [ ] **TC5**：单文件/项目内部调用、yh-asm/yh-link 入口、缓存身份与事务发布。
- [ ] **TC6**：Linux 宿主 OS 桥、原生种子、独立环境与连续自编固定点。
- [ ] **TC7**：有限 C 对象、普通 ar 读写/惰性提取与 libc 静态库交付；不阻挡显式对象闭环。
- [ ] **TC9**：Mach-O 可执行文件链接器——分段布局、符号解析、`LC_MAIN` 入口、
  `LC_LOAD_DYLIB` + 普通绑定流（不用 stub 与惰性绑定）。这是替换编译器**最终
  链接步**（`driver.yh` 的 `clang -o`）的必经之路。
  [设计](03-design/yh-link Mach-O可执行文件链接器设计.md)
- [ ] **TC10**：ad-hoc 代码签名（`LC_CODE_SIGNATURE` + SuperBlob +
  CodeDirectory，SHA-256 页哈希）。arm64 macOS 拒绝未签名的可执行文件，硬要求。
  SHA-256 曾实现于旧 link 项目的 `src/ln/10_sha256.yh`（6 个向量对着
  `shasum -a 256` 核过），但当时无生产调用点；2026-10-07 目录整理随该模块删除，
  归档在 `tmp/removed-2026-10-07/link-src-ln/`，动工时按需取回或重建。
  签名布局已从 `ld` 产物逐字段实测进设计文档 §5。
  TC9 骨架先把签名做掉才能验证（dyld 见未签名直接杀进程），绑定流随后接。
- [ ] **TC11**：`driver.yh` 最终链接步切成 `yh_link link`，`make install` 一并
  安装 `yh_link`，主门验证自举。chained fixups 可选迁移（dyld 仍支持绑定流）。

### 编译器已知缺陷（2026-10-13 全部处理完毕）

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

- [ ] **yh_link 的 ELF64 方言要求 `sym@PAGE`，编译器 GNU 方言发 `:lo12:sym`**：
  模块汇编步一旦命中 `yh_link`（`argv0` 同目录或 PATH 上），绝对寻址的
  `adrp xN, sym` 就报「adrp 需要 sym@PAGE，adr 需要符号或数字」（编译器
  的 GNU 方言按 `adrp xN, sym` + `add xN, xN, :lo12:sym` 发射，GNU as 两者
  都接受，yc_link 的 ELF64 模式不受 `:lo12:`）。macOS 上 yh_link 走 `-t
  darwin` 方言与发射一致，Linux 上从未让 yh_link 参战，故未暴露。
  绕过：`YH_LINK=/nonexistent` 强制回落 gcc（WSL 全套门禁即按此通过）。
  修法二选一：编译器 GNU 方言也发 `@PAGE/@PAGEOFF`（GNU as 接受），或
  yh_link 的 ELF64 模式接受 `:lo12:` 与裸符号。
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

- [ ] **SYS0–SYS6：`libs/sys` 系统调用封装**：Linux/arm64 先实现直接 syscall、
  `-errno` 结果、文件/目录、内存/时间和进程原语，再迁移上层库与编译器消费者、
  验收静态 ELF 和连续自编；**SYS7** 后续增加 Darwin OS 接口适配。
  本轮仅交付规划，API/文件与门禁见
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
明确要求实施 R0–R6。

- [ ] **R1**：文件一次解析、AST、任务私有前端、受检表示与 yh check。
  - [ ] R1 剩余（R2a/R2b 依赖其任务私有上下文契约）：
    语义/check 代码边界与旧遍历分离（check 仍复用旧多遍解析并抑制发射缓冲）→
    任务私有上下文（进程 worker 过渡方案依赖全局语义状态，线程池前置）→
    会话接口就绪（InterfaceReady 由串行/进程执行器驱动）→
    函数级 check 缓存。AST 已同时在 build/check 收集。
- [ ] **R2a**：typed SSA、verifier、默认低成本优化与双 arm64 后端。
  - [ ] R2a 剩余（按建议顺序，均为独立可验收切片）：
    负数字面量实参（一元减号作调用实参，当前 unsigned_score 因此回退）→
    switch 语句（比较链 CFG + case 值常量比较，无 fallthrough）→
    goto/label 与嵌套循环（break/continue 目标栈扩展）→
    for-in 迭代协议与无限循环 `for {}` →
    一元 +/- 与浮点标量（f32/f64 寄存器与比较/转换指令）→
    聚合/内存语义（LOAD/STORE/取地址、数组与 struct 赋值、参数/返回按值拷贝）→
    间接调用（函数指针/签名 fn 类型）与变参调用 →
    单文件与 `--emit-asm` 共用新后端 →
    默认优化覆盖与缓存提交协议复核（与 NP 管线、R2b 缓存键衔接）→
    Linux/macOS arm64 双平台 ABI 验收（含交叉组装对象的宿主运行证据）。
- [ ] **R2b**：首个完整 SSA 版本须具备线程池、接口就绪推进、函数
  check/IR 缓存、文件对象/链接缓存、确定性与失败提交验收。
  - [ ] R2b 剩余（首个完整 SSA 版本的硬门）：
    完整函数级 check/IR 缓存（当前缓存键仅覆盖窄 lowering 子集）→
    文件级对象（同模块跨文件 private 符号）→
    真正线程池（宿主线程桥；fork worker 与固定诊断缓冲是过渡方案）→
    接口调度的线程状态隔离、同项目并发与确定性验收 →
    缓存键纳入自有工具版本与所有目标/运行时输入。
  - [ ] 继续降低增量与冷编时间：短路求值切片后 20 轮测量单函数修改
    743.5/817.8ms、冷编 2203.0/2765.1ms（中位数/p95）；无改动 50ms
    中位数目标已达标，单函数 200ms 与冷编 1s 目标未达。单函数修改仍
    重新汇编整个所属模块且以外部汇编器为主；完整函数级 check/IR、
    文件对象与自有汇编/链接器是主要后续工作。
- [ ] **R3**：自有运行时与显式 OS API；独立配置取消隐式 system，
  旧行为只在过渡兼容配置保留。
  - [ ] R3 剩余（依赖 R2b 的宿主线程桥，可与之交错）：
    Linux arm64 原生构建并运行目录扫描适配（需先有经原生验证的 Linux 种子）→
    printf 按需扩展（宽度、精度、浮点；locale 不支持）→
    线程 API（与 R2b 真正线程池共用宿主桥，Darwin 走审核的 libSystem、
    Linux 走 clone syscall）→
    完整 OS 导入清单审计（`nm -u` 允许清单核对）后再验收 R3。
    汇编器/链接器仍通过显式 argv 调用系统工具。
- [ ] **R4**：Linux arm64 自有汇编子集、静态 ELF 链接与连续自编闭环；
  细化为 [yh-asm/yh-link TC0–TC6](02-plan/yh-asm与yh-link实施方案.md)。
- [ ] **R5**：macOS arm64 自有 Mach-O 工具链，披露 dyld/libSystem 并
  按 OS API 清单验收；细化为同方案 TC8–TC10。
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
- [x] **LL1 已验收语义与调用政策**：除模/移位/转换/bool/浮点/内存/效果/默认初始化探针；
  区分已定义规则、已复现 bug 和未定义政策；每个真 bug 单独红绿回归与完整门。
  - LLVM-SEM-02 已完成：浮点转 u64 的常量/typed CT 用 i64 中间值，高位正数被饱和截断。
    还复现动态浮点转窄整数在表达式内漏截断：u8(300) 为 300 而 CT 为 44，
    i8(130/-129) 为 130/-129 而目标位型应为 -126/127。
    已新增正式红绿回归，修正 unsigned 64 位中间值及动态窄化；单文件/项目定向门通过，
    完整 make test / make selfhost-native 退出 0（303/303、项目 95/95）。
    NaN/无穷与 64 位饱和后窄化已写入契约，LLVM 浮点 lowering 验收仍归 LL6。
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
  - [x] 首片 LL2-T：四个现有 Unix triple 的 TargetInfo、构建时宿主身份、严格目标解析；
    旧 -target 别名明确映射到 AArch64，--target 接收完整 triple。check 可检查 x64，
    旧代码生成在 LLVM 接入前明确拒绝 x64；$if 标记和目标文件筛选共用目标模型。
    成功门为未知目标拒绝、无 LLVM 工具 check、qemu 下默认 AArch64、选择输出目标不改变宿主身份。
    定向门和完整 make test selfhost-native 均通过（307/307、固定点 24、自解析 72、
    模块 18/18、项目 96/96）；独立 agent 的 22 项边界探针通过。宿主操作统一、
    受检快照、模块 IR、完整接口/缓存身份仍待后续，LL2 整体保持未完成。
- [ ] **LL3 严格 x64 LLVM 首片**：文本 IR、整数/布尔、分支/phi/固定调用；
  生成 EM_X86_64 ELF 并在 WSL 直接运行，禁止回退且有来源诊断。
- [ ] **LL8a 内存 helper**：先提供 LLVM memcpy/memset/strlen，检查自包含和自递归。
- [ ] **LL5 内存/数据 → LL4 控制流 → LL6 浮点 → LL7 调用/ABI**：与 R2a/NP3 同源切片合并验收，
  补聚合/全局/切片、复杂控制流、转换、间接/两类变参和 C 双向互调，不另做一套重复迁移。
- [ ] **LL8b x64 完整运行时/宿主桥**：allocator/printf、x64 syscall/目录/时钟/内存/进程；
  保留 ARM64 启动分支与现行导入限制，审计 LLVM libcall。
- [ ] **LL9 驱动/缓存/提交**：单文件与模块统一、完整键、原生 x64 链接器避开 ARM64 gcc 包装器、事务验收。
- [ ] **LL10 x64 原生自举**：ARM64 种子经 qemu 产 A，A 用 LLVM 产原生 B，B/C/D 原生连续自编；
  O0/O2 分别 `.ll/.s.i/.s.ct` 固定点、全量门、实际覆盖，
  与 R2b 任务私有状态/真正线程池/增量/并发/确定性硬门汇合。
- [ ] **LL11 x64 性能与默认切换**：至少 20 轮对照，原生默认全门绿后滚独立 `bin/yh-linux-x64` 与哈希；
  ARM64 种子不被覆盖，工具依赖与发行说明同步。
- [ ] **LL12 退役旧后端**：在 LL11 及 F1 Linux/AArch64 LLVM 回归都通过后，
  分片移除失去消费者的机器发射，不阻挡 x64 首期，也不删除 gen 语义或历史种子。
- [ ] **F1–F4 后续平台**：Linux/AArch64 → macOS/ARM64 → Windows/x86_64 → macOS/x86_64、Windows/ARM64；
  各格分别验收对象、链接、标准库运行、原生编译器、原生自举，不以 WSL 冒充 Windows 支持。

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
对象缓存键已包含编译器二进制内容（见 finish.md 同日项目增强记录），
相关未完成事项归入本轮流程与缓存设计，不再重复列“补编译器身份”。

## 设计决定不做（非缺口，勿列为任务）

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
