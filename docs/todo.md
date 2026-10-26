# todo

只记录**未完成**事项。已完成任务的历史与证据见
[finish.md](finish.md) 与 [01-finished/](01-finished/)；方案文档在
[02-plan/](02-plan/)，取舍见 [adr/](adr/)。

## 2026-10-24 架构优化（只列未完成）

A0a–A6 已全部完成并通过双门禁（表达式嵌套守卫、`ir/ssa_inline` 删除、A0c 路径预算、
A0d `gen.alloc`、A0e `ir_simplify`、A0c2 缓冲容量化、A1b/A1c 契约版本、A2a–A2c 模块
拆分、A3 `api` 调用面、A4a–A4d 状态收敛、A5 前端装配收敛、A6 `testkit` 抽出），
证据与数字见 [finish.md](finish.md)。当前基线由 `make arch-check` 守护：

| 指标 | 当前（B1-2 后，2026-10-26 实测） |
|---|---|
| 模块 / 文件 / 行数 | **14 / 121 / 53,673**（`proj` 775 + `ast` 3,463 + `lower` 5,835） |
| `cmd` 占比 | 387 行，**0.7%** |
| `gen.G()` 读点 | **98**（build 50、parse 21、testkit 12、main 5） |
| 模块级可变 `let` | 188（含 `gen` 未绑定回退实例） |
| 容量安全追加项 | 45（下界） |
| 最大模块 / 文件 / 函数 | build 10,265 / `module_build` 2,261 / `mb_link` 674 |

顺序按 [构建态对象化与 build 拆分重新规划](02-plan/yh-构建态对象化与build拆分重新规划-2026-10-25.md)
修正为 **B3 → B1 → B2**：B3 与 B1/B2 零文件重叠、可并行，B1+B2 才「是同一件事的
两个面」（改两遍），B3 不是。规模也按该文实测修正（lower 是 15 文件 5,742 行，
不是 10 文件 4,739 行）。B1 的动机是**字段偏移膨胀与读点归属**，不是线程安全——
当前是 `fork` + `waitpid` 的进程池（并发 4，COW 隔离，无锁）。

- [x] **B1-1 `proj` 模块成立**（2026-10-26 完成）：项目/模块/文件三张表 + 导入平行
  数组 + 7 个表类型 + 测试/扫描配置从 `gen.GenState`、`build.PjState` 收进
  `compiler/proj/`（`proj.ctx()` 唯一实例，`proj.add_*` 唯一写者）；前端窄口
  `proj.file()/file_count()/test_file_selected()`。`gen.G()` 165 → 115、
  `build` 10,807 → 10,242、`gen` 5,686 → 5,538。证据见 [finish.md](finish.md)。
- [x] **B1-2 目标/配置与 `canon` 显式化**（2026-10-26 完成）：`gen.TargetCfg`
  类型 + `proj.ProjectCtx.cfg` 实体 + `gen.bind_cfg` 指针绑定（未绑定走宿主默认
  回退实例）；`proj.canon` 改 `(…, out_off, out_len)`，`mb_build_dir`/
  `pj_find_root`/`pj_c_path` 一并出参化。`gen.G()` 115 → 98。证据见
  [finish.md](finish.md)。
- [ ] **B1-3 `BuildCtx` 收 build 进程级状态**：`build` 还有 50 个 `gen.G()` 读点，
  实测分两桶：**31 个函数只读 `gs.task.*`**（改 `gen.task()` 窄口，零语义改动）、
  **18 个函数读统计/会话字段**（`c_stats_*` + `c_front_cache`/`c_ir_cache_salt`/
  `c_firc_write_off`；按 B1-2 的指针绑定模式落成 `gen.CompileStats` + `BuildCtx`
  存储）；`build` 自己的 50 个模块级 `let`（会话 5、计时 5、调度 2、`mb_dep_*` 9、
  toml 11、link_inputs 11、pathstk 2、worker 1）里跨文件共享的部分收进 `BuildCtx`。
- [ ] **B1-4 关闭 `gen.G()`**：testkit 12 / parse 21 / main 5 的残余读点改窄口后把
  `G()` 从 `pub` 撤掉（目标全仓 0 调用点），漏改处由编译器报错兜底。
- [ ] **B2 拆分 `build`**：`build` 已 10,265 行、最大文件 `module_build` 2,261、
  最大函数 `mb_link` 674。前置有两条硬约束：链接簇依赖发射簇的 6 个产物路径/键
  符号（须先抽进 `proj` 的 art 子簇），`project_link` 读 `toml_*` 模块级 globals
  （不能进 `link`，否则 `link → build` 成环）。顺序：art（B2-1）→ `link`（B2-2）→
  `mb_link` 阶段化（B2-3）→ `module_build` 拆 3 文件（B2-4）→ 预算收口（B2-5）。
- [ ] **NP3 受检契约与 lowering 解耦**（2026-10-26 定位决定后唯一保留的 NP 阶段）：
  按[方案 §6](02-plan/yh-Nanopass风格优化架构实施方案.md) 收口——封存
  CheckedFunction 的绑定/类型/符号/调用事实，生命周期由任务持有，不再由 lowering
  查 parser 游标或可复用 gen 槽；按控制流切片做语言规范化，逐项声明移除/新增形式并
  保留源位置与求值顺序；把「源码形态支持预检」与「构造」分离，缓存/后端调用移到
  协调适配层（`ir` 不向上依赖）；补嵌套循环、for-in、switch/goto、指针/内存、转换、
  聚合、浮点与各类调用；受支持函数只走一次受检 → SSA → 后端。验收：新路径覆盖自编
  所需全部能力并达固定点后，才允许移除失去用途的旧入口；R2b 的线程池/文件对象/
  增量验收另外完成。

## 2026-10-21 重规划说明

本轮按「LLVM 收尾完成 → 发布质量 → 标准库与工具链 → 后续任务 → 待决策」重排：

- **LL12 已完成并关闭**：旧机器发射（`emit_arm64`/旧 arm64 后端/四缓冲/旧 SSA
  替换链/C ABI 发射层）全部删除，`--backend legacy` 一刀拒绝，`compiler/`
  净减 6516 行；证据见
  [完成报告](01-finished/yh-LL12退役旧机器发射-2026-10-21.md)。C4/C5 的两个
  小尾巴（`-target` 简写别名、`asm-symbols-safe` 与 `legacy_bytes` 断言）本轮
  一并处理。
- **LL11 性能门移出本文件**：20 轮对照、回退归因与发行性能口径由**专门的性能
  任务**承担，不在 LLVM 收尾内重复。
- **R2b 硬门后置**：RS2/RS3/R2c 与增量/冷编时间移入「后续任务」，不再作为
  LLVM 收尾的前置条件。
- **GitHub Actions 移除**：`.github/workflows/ci.yml` 与 `release.yml` 已删除，
  多平台回归与发布由 CircleCI 承担；需要时从 git 历史还原。
- 已完成的旧条目（LL0–LL10、LL9L、F1、F2-0/3–8/10、三平台默认切换与种子滚动、
  标准库 OS0–OS6、STAT0–STAT3、语料平台筛选、CircleCI 三端与 tag Release 首发、
  编译器已知缺陷 11 项、旧后端 3 个已知缺陷）不再列出。

图例：P0 发布质量与主线；P1 标准库与工具链；P2 长期与按需；⏸ 用户暂缓；❓ 待决策。

## 编译器性能测试（2026-10-23 方案，待实施）

[性能方案](02-plan/yh-编译器性能测试方案-2026-10-23.md)独立承接性能口径与版本对照，
本轮仅交付方案；先做 PF0/PF1，再据实测瓶颈安排后续。

- [x] **PF0/PF1 冻结语料 + 基线工具**（2026-10-26 完成）：新增 `tools/perf-baseline.py`——
  把 `compiler/` 复制成冻结语料并记录清单 SHA-256（本次 `08900669…`，120 文件 / 2.27 MB），
  跑四个场景（冷编 / 全量重编含写 / 热编 / 单函数改动）各 ≥3 轮，逐轮记录墙钟、父进程阶段
  耗时、load1、IR/check 命中与 `.fir` 写入量，输出 `tmp/perf/<run-id>/{raw.json,report.md}`；
  `--ab PATH` 提供 A/B 成对交错与变化率。
  首份基线（load≈4–5）：冷编 **10.3 s**、全量重编 **16.1 s**、热编 **0.98 s**、单函数改动 **3.59 s**
  （IR 204 命中 / check 38 命中）。
- [ ] **PF1b**：把每场景轮数抬到方案要求的 20 轮（本轮 3 轮用于工具校验），并接入 Gitea 性能任务。
- [ ] **PF2–PF4**：LLVM 阶段归因、并行内存口径、失效矩阵与 O2 对照；规模/产物基准；报告归档与回退复测。
- [ ] **PF2**：LLVM 阶段归因、并行内存口径、接口/编译期失效矩阵及 O2 对照。
- [ ] **PF3**：规模增长、产物运行基准与代码体积；并发扫描待存在控制入口后再做。
- [ ] **PF4**：Gitea 独立性能报告、资产归档、噪声校准与回退复测。

### 首轮归因发现的优化项（2026-10-25）

[归因分析](02-plan/yh-编译器性能分析-2026-10-25.md)给出冷编 26 s / 热编 2.4 s / 单函数
改动 7 s 的阶段归属：`capture`（函数级 IR 缓存序列化）占冷编 worker CPU 56%，
关闭后冷编 −46%；而增量场景实测命中 0%（IR）/ ≤9%（check）。按收益排序：

- [ ] **PC2c 缓存记录按函数内存膨胀**：v3 每个可缓存函数都带一份字符串字节副本，
  大模块的 `.fchk` 仍可能偏大；若需要可改为「按模块共享字符串池 + 引用计数」。
- [x] **PC3b 种子滚动**（2026-10-26 完成）：`just seed` 把 `yh` 覆盖到 `bin/yh-darwin-arm64`，
  哈希 `56bf3f56…` → **`ea24f659…`**。滚后 `just build` 冷编（13 模块）**11.04 s**（滚前 23.0 s，
  −52%），冷编 `.fir` 写入 0；滚后 `just test` 0 FAIL、`just selfhost-native` 122/122 + LA3 O0/O2
  + 两代固定点通过。
- **2026-10-26 低负载复核（load≈4.5–5，见 [分析](02-plan/yh-编译器性能分析-2026-10-25.md) §14）**：
  冷编 11.2 s、全量重编（含写）**17.5 s**、热编 **1.14–1.21 s**、单函数改动中位 **3.9 s**、
  冷编后首次改 4.78 s。**热编 ≤1.5 s 与全量重编 ≤20 s 已达标**；单函数改动 ≤3 s
  受限于「模块级 `.o` + 每轮整模块 LLVM 发射」（模块重编 2.03 s 里大头在此），
  需要**函数级目标文件**才能再降，属结构性改动。PC3c 的实测收益只有 0.5 s
  （4.78 vs 4.27），不建议为它引入冷编后台补写。
- [ ] **PC4c scratch 复用前先查越界**：把 7 张临时表改成按模块复用时，`yh test` 的
  libs 构建会在 lowering 阶段失败（`memory/memory.yh:5:19 alloc`），机制未定位；
  重做前先给 `ir_fc_mark_symbol`/`ir_fc_visit_type` 加边界断言。注意 `reserve` 必须
  在取指针之前（扩容 realloc 会让旧指针失效）。
- [ ] **PC7 函数级目标文件**（PC6 的 ≤3 s 只能靠它）：可行性见
  [函数级目标文件可行性](03-design/yh-函数级目标文件可行性-2026-10-26.md)。方案 A（每函数
  一个 `.o`）或 B（桥批处理，需改桥 ABI → 滚种子），工期按天计；落地前单函数改动
  只能停在 ~3.5–3.9 s。
- [ ] **LC1 Linux 对等**：Linux 宿主的裸跑仍靠 `YH_LINK_RUNTIME_FLAGS`
  （`-lstdc++`/`-lpthread`/`-lxml2`…）。要么给 Linux 闭包生成对应的 `.so` 路径输入，
  要么把运行库参数换成清单键（2026-10-25 试过 `[link-options].runtime`，但当前
  种子不认该键，需先滚一代种子再落地）。验证：Linux 上
  `cd compiler && ../bin/yh-linux-arm64 build` 不设环境变量就能链接。
- [ ] **LC2 闭包清单门扩展到 Linux**：`tools/link-closure.py check --host …` 目前只
  接进 `make test-llvm-darwin`；Linux 的对应门未接（需先有 Linux 宿主记录验证）。
- [ ] **LC3 F2-9 交叉**：Linux→Darwin 交叉仍需目标包自带 `libc++.tbd`
  （见 `03-design/yh-Darwin交叉编译遗留边界.md` §2）。

### 工具链健壮性（2026-10-26 踩坑立项）

- [x] **RB1 worker 父死子退**（2026-10-26 完成）：worker 在 fork 后记录父 pid，并在
  函数入口、整模块发射前两处检查 `getppid()`；父进程不在就退出。实测 `kill -9` 构建父进程
  后，4 个在跑的 worker **2.2 s 内全部退出**（此前会残留 9–17 分钟）。
- [x] **RB2 门禁可见编译器身份**（2026-10-26 完成，按最小改动）：`stage-yh` 依赖
  `_ensure_built`（源比 `yh` 新就重编），且每次都 `cp -f` 覆盖，本身不会用旧副本；
  之前「拿旧副本白跑 17 分钟」是**仓库 `yh` 本身来自坏源码状态**，靠时间戳无法发现。
  现在 `stage-yh` 会打印 `编译器: <path> <bytes> mtime=<epoch>`，门禁日志可直接核对
  本轮用的是哪一个二进制（完整内容校验的收益不足以抵消每次 70 MB 哈希的成本）。
- [x] **RB3 Darwin/ARM64 守卫判据**（2026-10-26 修）：`just` 的 `arch()` 在 macOS 返回
  `aarch64`，而 `test-llvm-darwin` / `selfhost-llvm-darwin` 的守卫拿它与 `arm64` 比较 →
  在 Darwin/ARM64 上直接拒绝执行；改用已归一化的 `seed_arch`。
- [x] **RB4 just 迁移后的门禁复核**（2026-10-26）：`just arch-check` 0.4 s ✅、
  `just test` 0 FAIL ✅、`just selfhost-native` 122/122 + LA3 O0/O2 ✅、
  `just test-llvm-darwin` 0 FAIL ✅（修 RB3 后）。用例数 124 → 122 是 YT4 迁移删掉旧夹具所致。
- [ ] **RB5 产物二进制不可位级复现**：同一源码重复构建得到的 `yh` 大小/哈希都不同
  （实测 70,814,352 / 70,814,624 字节），原因是链接后 ad-hoc 签名把**临时文件名/pid**
  写进了 codesign identifier（`Identifier=yh.yh-tmp.<pid>`）。固定点门禁比较的是模块
  产物（`.s`/`.s.i`/`.o`），所以没暴露；但「同源同构」的预期不成立，发行可比性受影响。
  改法：签名前先 rename 到最终名再 `codesign`，或显式给 `-i <稳定identifier>`。

## 语言内测试（YT4 迁移与发版）

[设计提案](03-design/yh-test语言内测试设计-2026-10-23.md)、
[实施分期](02-plan/yh-test分阶段实施方案-2026-10-23.md)与
[2026-10-25 迁移分析与决策](02-plan/yh-test语法迁移既有测试分析与规划-2026-10-25.md)
（取代 10-23 版）已整理。**YT0–YT3b、YT2d、YT1.1 与 YT4-P0～P7 已全部完成**：
每个标准库都有自己的测试文件（122 例），`libs-test`/`libs-test-o2` 与主门全绿；
证据见 [YT4 收口与门禁验证](01-finished/yh-YT4-收口与门禁验证-2026-10-25.md)
与各阶段 `01-finished/yh-YT4-*.md`。以下只保留延后项。

- [ ] **YT2d-2 剩余**：函数级 IR 与 check 切片缓存仍未用于测试构建
  （缓存键不覆盖 `TK_TEST`），测试构建每次整模块重编。
- [ ] **D11 预期失败/诊断断言能力（另立项）**：为把 `tests/yh-run/fail`、
  `tests/fmt/interp.py` 等负例逐步收敛到 `yh test`，需要新增“编译必须失败且
  包含指定诊断片段”的测试能力；当前负例门继续外部运行。

## 版本与发布流程（P0 前置）

每个版本两条分支：`<ver>-rc` 开发与候选、`<ver>-release` 只收合并；rc tag 发
prerelease 并带三端种子，正式 tag 只允许打在对应 release 分支上。方案见
[分版本 rc/release 分支发版流程](02-plan/yh-分版本rc与release分支发版流程方案-2026-10-21.md)。

- [ ] **R1 分支模型落地**：`0.0.7-release`（指向 tag `0.0.7`）＋ `0.0.8-rc` /
  `0.0.8-release`；默认分支切到最新 `<ver>-release`；`llvm` 保留为历史线。
- [ ] **R2 CI 改造**：`release.yml` 已用正则守卫只认 `x.y.z`/`x.y.z-rc.N`（等价
  tag filter），`publish-release.py` 已支持 `--prerelease`；**剩余**正式 tag 的
  「必须落在 `<ver>-release` 上」祖先校验。
- [ ] **R3 取种改造**：`tools/fetch-release-seed.py` 加 `--include-prerelease`
  （默认开启），使 rc.N 能用 rc.N-1、正式版能用最后一个 rc 作种子。
- [ ] **R4 版本漂移修复**：`compiler/README.md` 与
  `tools/compiler-performance.py:208` 写死的 `0.0.5` 改为从清单读取或前缀断言。
- [ ] **R5 0.0.8-rc.1 内容**：当前工作区未提交的 os/sys OS0–OS6 恢复 + R1–R4；
  之后按 A1/C1/C3/D1 分期出 rc.2、rc.3。

## P0 发布质量：平台、CI 与分发

### A. F2 收尾与 F1 可选后续

- [ ] **A2 F2-9 Linux/x64 交叉产 Mac 候选**：目标版 LLVM/桥依赖注入、Linux 上的
  Mach-O 交叉链接配置、Mac 原生候选固定点；SDK bundle 已完成，主项未实施。
- [ ] **A3 F1-6 可选**：x64 专用 `llvm-selfhost.py` 参数化到 ARM64；跨宿主
  （x64 上跑 arm64 种子）链接模板策略单独立项。

### B. 后续平台（原 F3/F4）

- [ ] **B1 Windows/x86_64**：MSVC ABI/LLP64、COFF/PE 链接、Windows OS 桥
  （文件/目录/Unicode/进程/时间/内存/启动入口）；原生构建与运行，不以 WSL
  冒充 Windows 支持。
- [ ] **B2 macOS/x86_64、Windows/ARM64**：对应目标 ABI、库、OS 适配与各自原生
  种子；四格分别完成运行/自举/性能验收。

### C. 分发与工具链体验

- [ ] **C1 固定 SDK 预编译分发**：把 569MB 的 LLVM/lld 构建产物作为 Release
  资产（带锁文件校验），免掉每台机器首次 `make llvm-host` 的源码构建。
- [ ] **C3 SDK 27 兼容**：内嵌 lld 21 解析不了 `arm64e.x1` TAPI；升级固定 LLVM
  或按实际 SDK 裁剪目标列表。
- [ ] **C4 `make dev` 增量**：归档身份目前按路径计，SDK 原地重建需清缓存或补
  内容哈希。
- [ ] **C5 Darwin 交叉边界**：C 源/libc++/目标包/frameworks 的剩余边界，见
  [遗留边界](03-design/yh-Darwin交叉编译遗留边界.md)。

### D. CI 与本地环境

- [ ] **D1 本机 ANTLR jar**：`make test` 第 1 层需要本地
  `antlr4-*-complete.jar`；WSL 已配置，macOS 按同一方式补齐或文档化安装。
- GitHub Actions 已于 2026-10-21 移除（`.github/workflows/` 删除）；CI 与发布
  自 2026-10-22 起由 Gitea Actions 承担（`.gitea/workflows/`），CircleCI 仅留作
  云端真机参照。
- [ ] **D2 Gitea Actions 收尾**：仓库分支保护未要求 status check；Linux/AArch64
  容器门在 8GB 宿主上需把闭包缓存挂到 `/work/tmp/llvm-migration`（symlink 会让
  `llvm-host.py` 的 `relative_to(ROOT)` 失败）；CircleCI 去留待定。
- [ ] **D3 x86_64 模拟下的运行崩溃**：Apple container `-a amd64` 里
  `make test-llvm` 的 `run/20-bytebuf.yh` 运行崩溃（信号 5），编译类用例全过；
  发布流水线因此把 x86_64 端降级为构建+打包，运行证据以 CircleCI 真机为准。

## P1 标准库与工具链

### E. os/sys 与 libc

- [ ] **E1 OS7 编译器迁移与独立性审计**：编译器改用 `libs/os`/`libs/sys` 的
  接口，减少对 C runtime 的隐式依赖；见[联合设计](03-design/yh-os与sys标准库设计.md)。
- [ ] **E1.1 OS7 第一切片：显式依赖与时钟/目录迁移**：给 `compiler/` 增加
  `yh_libs` 显式依赖；把 `compiler/cmd/clock.linux.{arm64,x64}.yh` 与
  `project_dir.linux.{arm64,x64}.yh` 迁到 `libs/sys`/`libs/os`；验证宿主
  编译器 I/O 与输出目标隔离，更新缓存/种子身份。
- [ ] **E1.2 OS7 第二切片：文件/进程与独立性**：迁移编译器剩余文件、worker、
  fork/exec/wait 调用；审计普通 syscall 程序与嵌入 LLVM 编译器的依赖清单，
  区分宿主与目标，补独立性验收。
- [ ] **E1.3 浮点字面量解析去 libc**：`compiler/gen` 的十进制常量改用宿主
  `strtod`（正确舍入，修复 1 ULP 偏差）；E1 迁移 libs/os 时补纯 yh 等价实现
  或改用 `libs/num`，并保持 `tests/yh-run/run/float-literal-rounding.yh` 全绿。
- [ ] **E2.1 OS8 Darwin 文件 API**：新增 Darwin `file` 平台实现与即时 errno
  桥，覆盖 open/read/write/close/mkdir/remove/rename、CLOEXEC 与错误分类；
  原生用例与 Linux 契约对齐。
- [ ] **E2.2 OS8 Darwin 目录/进程/时间**：目录枚举（getattrlistbulk）、
  cwd、spawn/wait/exit 与时钟/睡眠的 Darwin 适配；逐项原生门并披露
  libSystem/dyld 依赖。
- [ ] **E3 独立产物与消费者审计**：普通 ELF/syscall 程序与编译器分别列出
  运行时依赖，完成 SYS5–SYS6 的消费者迁移、固定点与独立环境验收。
- [ ] **E4 libc L0–L5**：按[分阶段候选方案](02-plan/yh-libc分阶段候选方案.md)
  推进，未授权全部实施。

### NET/HTTP 网络与 HTTP 标准库（2026-10-24 决策完成；NET0–NET1 已交付，HTTP2–HTTP7 待实施）

[设计](03-design/yh-http标准库设计-2026-10-24.md)与
[ADR-0018](adr/0018-yh网络与HTTP标准库分层.md)已定稿。仓库此前无任何 HTTP
实现，`libs/sys` 无 socket 原语、`libs/os` 明确不承诺网络，故按
「sys socket → net → http」三级推进。已确认：**首期含服务端**、**TLS 走可选
`libs/tls`（系统 OpenSSL）**、**DNS 纯 yh**、**并发后置**、**`Date` 先补
`time`**、**不用 libcurl**。头字段零拷贝借用读缓冲，body 增量读，不提供整块
`read_all`。

NET0/NET1 已完成（`net0-sys-socket-loopback`、`net1-net-tcp-loopback` 与
`yh test net` 全部通过，见 [finish](finish.md)）：`libs/sys` 提供 12 个
socket/poll 原语与两平台常量；`libs/net` 提供 Endpoint 解析/格式化与 TCP
dial/listen/accept/read_some/write_some/write_all/shutdown/close。实测确认
Darwin 无法在 yh 层切非阻塞（`fcntl` 是 C 变参），因此 connect 超时只在
Linux 生效；`read`/`write` 与 prelude 重名，net 用 `read_some`/`write_some`。

- [ ] **HTTP2 模型与解析/序列化**：设计 §7 的 12 条 RFC 规则正反例、chunked
  状态机、`Io` 内存源离线测试；与 Python 参考实现逐字节比对。
- [ ] **HTTP3 客户端**：`Target`（endpoint/host/tls）、keep-alive 复用、body
  增量读、100-continue、可选重定向。
- [ ] **T1 `time` 墙上时钟与 IMF-fixdate**（HTTP4 前置）：`wall_ns()` 走
  `sys.read_clock(CLOCK_REALTIME)`，`format_imf_fixdate()` 含公历换算；
  `monotonic_ns` 契约不变。
- [ ] **HTTP4 服务端**：串行 accept、Responder、内建 400/413/431/501、
  keep-alive、`Date` 头；README 写明单连接队头阻塞与适用范围。
- [ ] **HTTP5 DNS**：纯 yh UDP 解析器 + `/etc/hosts` + `/etc/resolv.conf`；
  poll 精确 deadline。
- [ ] **HTTP6 TLS**：`libs/tls` + 系统 OpenSSL（定参 `@[extern]`）、客户端
  SNI/证书/主机名校验、服务端证书链载入、`io_from_tls`；自签 fixture 五类
  用例在 Linux 与 Darwin 各跑一遍。
- [ ] **HTTP7 文档与门禁**：README/doc.yh/`examples/http-demo`/
  `make test-http`/finish 记录。
- [ ] **后置（不排期）**：`serve_fork`/poll 事件循环等并发标准库落地后再补；
  可选 `libs/curl` 互操作模块（HTTP/2、代理、cookie、压缩场景），不得进入
  `libs/http` 依赖图。

### MEM 内存管理标准库（2026-10-23 设计第二版；M0–M6 待实施）

[设计](03-design/yh-memory标准库设计-2026-10-23.md)与
[方案](02-plan/yh-memory标准库实施方案-2026-10-23.md)已按 Zig
`std.mem.Allocator`/`std.heap` 的能力分层整理。保持现有
`alloc`/`release`/`copy` 签名；新增 `reallocate`（调用方显式提供 `old_size`）、
`FixedBuffer`（调用方缓冲区、LIFO resize/free）、增强 Arena（几何增长、
reset 模式、LIFO 回收、capacity）与基于 Arena + 空闲链的 FixedPool。
统一 `Allocator`（函数指针 vtable）列为 M5 可选；Debug/ThreadSafe/Page/
StackFallback 后置。块统一取自 prelude 堆，不新增 `sys` 依赖，不改
`string`/`toml`/编译器，也不替代 `libc` 的 C ABI 分配器。

- [ ] **M0 基线固化**：`memoryheap` fixture 覆盖零长度、16 字节对齐、超长请求
  返回 0、`release(0)`；不改源码，确认现状与设计一致。
- [ ] **M1 `reallocate` 与文档**：增长/缩小/失败保留旧块/`new_size=0` 释放；
  README 与 `old_size`、重叠、对齐边界；`libsbase` 不回退。
- [ ] **M2 FixedBuffer**：绝对地址对齐、空间不足返回 0、最近分配
  resize/free、非最近缩小 resize=1 但不回收、reset/owns/容量；新增
  `tests/memory/run.py`、`make test-memory(-o2)` 与 build-check 登记。
- [ ] **M3 Arena**：单块/跨块、几何增长（1.5 倍）、64/256 对齐、非法对齐/
  溢出返回 0、LIFO resize/free、`reset(free_all/retain)`、capacity、
  `MEMORY_TEST_FAIL_AFTER` 注入。
- [ ] **M4 FixedPool**：内部 Arena + 空闲链、`reserve`、复用、reset/release、
  block_size/alignment 校验、映射失败注入；以 `toml`/`cli` 池迁移为可选消费者。
- [ ] **M5 `Allocator` 统一接口（按需）**：函数指针 vtable、heap/arena/
  fixed_buffer/pool/failing 适配器、`allocator_reallocate` 组合；触发条件为
  多容器共享接口、Arena 用 FixedBuffer 作 child 或 StackFallback。
- [ ] **M6 后置候选**：堆对齐分配、简化 DebugAllocator、StackFallback、
  PageAllocator 适配器、统计/上限、ThreadSafe（J4）；无消费者不做。
- [ ] **E4 配对**：libc 分配器与 prelude 的配对（见 E4），不得跨入口释放。

### IO 字节流标准库（2026-10-24 设计；IO0–IO4 已完成）

[设计](03-design/yh-io标准库设计-2026-10-24.md)与
[方案](02-plan/yh-io标准库实施方案-2026-10-24.md)已把 `libs/io` 从"只有四个写侧
接口"扩展为完整读写层：`read_all`/`read_file`/`write_bytes`/`write_file` 与调用方
缓冲的 `Reader`/`Writer`（行读取、显式 flush），保留
`write_all_result`/`write_all`/`print`/`println` 原签名。`libs/io/99_tests.yh`
7 个用例通过，`yh test io` 已接入 `make test`/`make selfhost-native`/
`make test-lib-tests`。以下只留未完成项。

- [ ] **IO5 toml 读文件迁移**：删除 `libs/toml/70_files.{linux,darwin}.yh` 的手写
  短读循环，改用 `io.read_file`；保留 `TOML_MAX_INPUT` 上限语义与
  `parse_io_error`/`parse_resource_error` 分类映射，先加断言锁定"恰好读满"与
  "还有数据"的现有区分，再迁移。验收 `make test-toml` 与
  `make test-toml-conformance`。
- [ ] **IO6 seek/copy（依赖 os）**：`os` 补 `lseek`/`fstat` 后再评估 `Reader` 的
  peek/seek 与零分配 `io.copy`；先出设计增量，不提前对外承诺。
- [ ] **IO7 消费者迁移审计**：`cli/help.yh`、`examples/os-demo` 与编译器读文件的
  手写循环是否改用 `io`，逐处评估（编译器侧属 OS7 显式依赖，另行安排）。

### MATH math 纯 yh 标准库（2026-10-23 方案；P0 已完成）

[方案](02-plan/yh-math标准库实施方案-2026-10-23.md)按用户决定改为**纯 yh
实现**：不用 `@[extern]`/libm，函数名与 `<math.h>` 一致；算法移植
fdlibm/musl，位级函数正确舍入，f32 复用 f64 内核。P0 探针已确认普通
`pub fn` 的 mangled 符号、私有 const 数组/递归/二进制 stdout、并集位模式，
以及 `pub const f64` 导出损坏与极端十进制字面量偏差。以下只留未完成项。

- [ ] **P1 位级/精确层与谓词**：`00_bits/05_predicates/10_exact/15_round/
  20_fmod` 的 f64+f32；`mathpredicates`/`mathexact` 夹具、`tests/math/run.py`、
  `make test-math`、build-check 登记；0 ULP 差分。
- [ ] **P2 根与 fma**：`01_fma/25_sqrt`；sqrt/sqrtf 位相等，cbrt/hypot ≤1 ULP，
  fma <1 ULP。
- [ ] **P3 指数/对数**：`30_exp/35_log`；上溢/下溢/次正规边界，最大 ULP <1。
- [ ] **P4 幂**：`40_pow`；C 附录 F 特殊值逐条断言，常规区间 <2 ULP。
- [ ] **P5 三角/反三角**：`44_rem_pio2/45_trig/50_inverse_trig`；Cody-Waite
  与 Payne-Hanek，大参数与 `atan2` 象限。
- [ ] **P6 双曲/误差/伽马**：`55_hyper/60_erf/65_gamma`；极点、负半轴、
  溢出边界。
- [ ] **P7 贝塞尔/旧名/收口**：`70_bessel/75_legacy`、`doc.yh`/`README.md`、
  surface 全调用、`nm -u` 无数学符号、O0/O2 与 Linux 容器差分。
- [ ] **P8 公共 f64 常量（后置）**：修 `iface_emit_const_value` 浮点分支并扩展
  `pubconst` 项目，再交付 `INFINITY/HUGE_VAL/NAN/M_*`；不修则常量不交付。

### TOML 标准库（2026-10-23 设计；T0–T5 reader 已完成）

用户已确认**完整 TOML 1.1 reader 优先、写入后置**。`libs/toml/` 已交付完整
reader，T0–T5（含 T4.1 分配失败/预算门与 T5.1 安装导入）已完成并记录在
[finish](finish.md)；固定 toml-test v2.2.0（1.1 清单）681/681、124 个池分配
失败点、低预算门与仓库外导入均已通过。以下只保留未完成项。

- [ ] **T5.2 发布资产是否携带标准库**：三端 Release 资产当前只含 `yh`，
  标准库由 `make install` 分发；是否改发布策略需单独决定，未在 TOML 实现中
  擅自改动。
- [ ] **T6 编译器迁移（独立切片）**：显式标准库依赖、保留清单 schema、递归文档
  生命周期、缓存与种子冷编/两代固定点；全迁移后删除旧解析器。
- [ ] **T7 生成器（后续按需）**：独立构建/编码契约与 encoder 验收；保真编辑另立项。

### JSON 标准库（2026-10-24 设计；J1–J3/J6 已实现，J4/J5/J7 待做）

[设计](03-design/yh-JSON标准库设计-2026-10-24.md)、
[方案](02-plan/yh-JSON标准库实施方案-2026-10-24.md)与
[ADR-0019](adr/0019-yh-JSON标准库独立文档模型与词素保真数字.md)已落地首期：
`libs/json/` 12 个源文件（reader + writer + 查询 + 文件读写），
`libs/num/` 提供十进制 ↔ binary64 与最短往返格式化；
六组断言已迁入 `libs/json/99_tests.yh`（12 个 test / 127 条断言，见
[迁移记录](01-finished/yh-YT4-P1-json迁移-2026-10-25.md)），`jsonmodel`
保留为 `build-check.py` 的公开面 smoke；原 `tests/json/run.py` 与
`make test-json` 已删除，由 `yh test json` / `make libs-test` 取代。口径：
RFC 8259 完整语法 + 严格 profile（拒绝 BOM/重复键/孤立代理/尾逗号）；
单一 `kind_number` 且保存原始词素；文档模型与 `toml` 独立。
以下只保留未完成项。

- [ ] **J4 预算与失败原子性**：深度/字节/有效位上限已实现并有断言；缺
  `JSON_TEST_FAIL_AFTER` 池分配失败注入与低预算门（新建
  `tests/json/injection.py` 与 `make test-json-injection`）。
- [ ] **J5 一致性与差分**：`jsontestbridge`（stdin→退出码）、固定 JSONTestSuite
  提交（`y_` 全接受、`n_` 全拒绝、`i_` 逐条登记）、Python 差分（值树 + 浮点
  位模式）、`jsonroundtrip` 组、`make test-json-conformance`。
- [ ] **J7-2 收口剩余**：`tests/json/install.py` 仓库外导入门、
  `make test-json-install`、`docs/finish.md` 流水与 `01-finished/` 交付记录。
- [ ] **J8 后置候选**：JCS 规范模式、大对象哈希索引（`JSON_HASH_THRESHOLD`
  已预留）、流式 SAX、JSON Pointer；均需实测或真实消费者触发。
- [ ] **N1 `libs/num` 反向迁移**：`libs/toml/30_numbers.yh` 改为调用
  `num.parse_f64`，以 toml-test 681/681 与注入门为阻断条件；当前为不触碰已
  验收语料而暂缓。
- [ ] **N2 后端限制回访**：当前编译器对超长函数体、部分调用语句形态与
  "调用结果直接赋给字段"有限制（种子与 HEAD 均有），JSON 库已按小函数规避；
  修好后可放宽实现风格，不影响公共 API。

### FMT fmt 运行时与 V 风格插值（2026-10-23 改版；I5 可选扩展未做）

用户决定：字符串格式化采用 V 式插值 `"…${expr:spec}…"`，结果为
`string.String`；首版不实现 Go 的 `%` 格式串与 `Printf` 族（是否保留为
次级 API 待确认）。语言设计见
[字符串插值设计](03-design/yh-字符串插值设计-2026-10-23.md)，运行时见
[fmt 标准库设计](03-design/yh-fmt标准库设计-2026-10-23.md)，
[方案](02-plan/yh-fmt标准库实施方案-2026-10-23.md)列出 R0–R3（fmt）与
I0–I5（语言）；R0–R3 与 I0–I3 已实施，语言插值已端到端可用。fmt 不改
prelude `printf`（H.I3 的按需扩展仍独立）。

- [ ] **I5 可选扩展**：嵌套插值、运行时 width/precision、`r/R`、
  `string.View`/`string.String`/enum 名称、fmt 别名导入；每项单独立项。

### G. C/C++ 桥迁移到 yh

见[可行性分析](01-finished/yh-C与C++代码重写可行性分析-2026-10-20.md)。

- [ ] **G1** 迁移 `compiler/llvm/bridge.c` 到 yh（LLVM 生命周期、初始化同步、
  有界诊断、原子发布），补正式 `.yh` 对等用例与错误路径。
- [ ] **G2** `lld_bridge.cpp` 的配置/argv/库搜索移到 yh，保留 `lldMain` 最小
  C++ 适配层与不可重入状态处理。
- [ ] **G3** 桩的构建期择一机制；迁移前保留 C 弱桩，避免重复强符号。
- [ ] **G4** SDK 身份、归档成员与自举闭包同步，候选引导后滚种子。

### H. 编译器可选收尾

- [ ] **H1 字符串字面量只读化**（2026-10-26 已决定：改语义）：字面量符号发
  `constant` 进只读段（`backend/llvm_module.yh:385` 已按 `mutable` 选
  `global`/`constant`，只需把 `lower/module_snapshot_static.yh` 的字面量登记
  `mutable` 置 0）；能静态判定的写入改为编译期诊断——先覆盖 `"abc"[0] = …` 与
  字面量绑定的局部别名（不经函数边界），与 comptime 的「字面量字节池只读」
  口径统一（`tests/yh-run/fail/147-comptime-string-const-write.yh`），逃逸到
  函数边界后的写入退化为运行期崩溃。
  实测依据（2026-10-26）：运行期现在允许且生效（`let p *char = "abc";
  p[0]='z'` → `zbc`），仓库运行语料无依赖；`__data` 实测 hello-world 14 B、
  `./yh` 93 KB（每进程至少省一个 16 KB 页，字面量页可跨进程共享）。
  验收：`tests/yh-run/fail/` 加直接写用例、`tests/yh-run/run/` 加只读访问用例，
  `make test` + `make selfhost-native` 全绿后与 PC3b 一起滚种子。
- [ ] **H4 LLVM 闭包缓存路径迁移**：缓存里的 `selfhost-flags.txt` 仍存绝对
  路径，整个缓存目录被搬走或换机器时需要重写或重新 `make llvm-host`；
  `YH_LLVM_CACHE` 自动定位已完成，此项只保留路径可迁移性。
- [ ] **I1 MOD-U6**：远程来源、版本规则、锁文件与工作区，按实际需求另立设计与
  验收（不沿用旧 Go 方案承诺）。
- [ ] **I2 VS Code 扩展**：VS-U0 最小扩展与 LSP → VS-U1 保存后诊断与取消 →
  VS-U2 未保存缓冲与精确跳转 → VS-U3 调试信息与 DAP → VS-U4 集成测试与发布。
  见[方案](02-plan/yh-VSCode扩展方案.md)。
- [ ] **I3 R3 剩余**：printf 按需扩展（宽度/精度/浮点）、完整 OS 导入清单审计
  （`nm -u` 允许清单）；线程 API 已并入「后续任务」。
- [ ] **I4 编译器缺陷清单**：11 项已全部修复或复核为不再复现；新缺陷按
  「先复现、再红绿回归、后修」入本清单。
  - [ ] **I4-1 非 void 函数末尾缺少 return 的诊断误导**（2026-10-22 记录）：
    `fn main() int { printf("Hello, World!\n") }` 报
    `LLVM lowering main: 首片不支持此语句或表达式`，位置指向最后一条语句的
    实参 token（使用例的位置看起来像 printf 不支持）。原因：
    `checked_lower_function` 在 `status == 1 && (ret != ir.IR_TY_VOID ||
    aggregate_return != 0)` 时返回 -2，但返回前没有设置 `l.reason` 与
    `l.last_token`（`compiler/ast/module_snapshot_lower.yh` 约 3698 行），
    沿用默认文案。复现：`examples/ex1.yh`（缺 `return 0`；补上即通过）。
    期望：报「非 void 函数末尾缺少 return」并把位置指到函数体收尾；先加
    `tests/yh-run/fail/` 用例（用 `// fail-contains:` 锁新文案），再改文案，
    跑 `make test` + `make selfhost-native`。**附**：`examples/ex1.yh` 是照搬
    C 的 hello world，已补 `return 0`（已提交）。
  - [ ] **I4-2 极端十进制浮点字面量不精确**（2026-10-23 math 探针）：
    `1e300`、`1e-300`、`1.7976931348623157e308` 与正确位型不等，
    `2.2250738585072014e-308` 是 DBL_MIN+2 ULP，`5e-324` 直接变 0；
    π、0.1、1.5 精确。影响所有数值代码，纯 yh math 只能用位模式构造常量。
    修复：前端十进制→f64 改为正确舍入（Eisel-Lemire/strtod 路线），补
    `tests/yh-run/` 极端指数字面量用例，先红后绿。
  - [ ] **I4-3 `pub const f64` 跨模块导出损坏**：`.s.i` 把浮点位型当整数写出，
    导入侧报「浮点与整数之间需要 .to_type 显式转换」。修复：
    `parse_global_init` 保存浮点初始化式文本，`iface_emit_const_value` 增加
    浮点分支；扩展 `tests/modules/projects/pubconst/`。math 的
    `INFINITY/NAN/M_*` 等常量依赖此项。
  - [ ] **I4-4 `!bool` 在 bool 返回位置退化为 i32**：`fn f(b bool) bool {
    return !b }` 报「整数不能隐式转为 bool」；条件位置正常。修复：
    `sem_unary` 对 bool 保留 `TY_BOOL`（或写进语义边界），补 run/fail 用例。
  - [ ] **I4-5 `@[inline]` 无后端效果、IR 内联器未接线**：`F_INLINE` 只在
    parse/iface 使用，`compiler/ir/ssa_inline.yh` 没有调用点，跨模块也无 LTO。
    影响纯 yh math 的小函数与 O0 性能。修复：把 `@[inline]` 降为 LLVM
    `alwaysinline`，或让模块接口携带可内联体；再决定是否启用 IR 内联器。
  - [ ] **I4-6 能力文档漂移**：`compiler/README.md` 的浮点参数边界与
    `compiler/gen/target.yh` 的 emit_arm64 说明仍指旧后端；`libs/libc/README.md`
    称函数指针不支持（LLVM ABI 已支持）；`AGENTS.md` 的 x64 种子说明与
    Makefile 现状不一致。按实际行为刷新或标为历史。

## 后续任务：文件对象、线程池与性能（LA4/LA5）

LA0–LA3 已完成，历史与证据见 [finish.md](finish.md) 与
[01-finished/](01-finished/)；以下只保留未完成项。

- [ ] **J2 / LA4 文件级对象**：按
  [LLVM 文件对象与提交清单设计](03-design/yh-LLVM文件对象与提交清单设计-2026-10-22.md)
  实施 LA4.1 分区模型 → LA4.2 hidden 跨对象私有身份 → LA4.3 文件对象键/manifest
  /原子提交 → LA4.4 删除/重命名/runtime/损坏/并发回归。完成前默认仍为单模块对象。
- [ ] **J3 RS5 收口报告**：依赖 J2，复核优化覆盖与文件对象缓存提交协议。
- [ ] **J4 / LA5 线程池**：按
  [显式上下文与线程池设计](03-design/yh-LLVM显式上下文与线程池设计-2026-10-22.md)
  收口 FrontendTask/AstStore/CtContext/CacheContext/Diagnostics，再接宿主线程桥
  与固定线程池；完成前继续 fork/COW，不宣称线程安全。
- [ ] **J5 增量/冷编时间**：单函数 200ms、冷编 1s 目标未达；当前仍整模块
  lowering 与内嵌 LLVM 对象生成，耗时占比交专门性能任务重测；J2 缩小对象
  重做范围。旧外部汇编器的耗时解释不适用于 LLVM 唯一后端。

#### 已知缺陷（LA0 复现）

- [ ] **D1 goto 函数中的函数指针绑定**：含 `goto`/`label` 的函数里
  `let f fn(int) int = add_one` 被按内存驻留处理时生成 `alloca void`，
  LLVM 报 `void type only allowed for function results`。最小复现：
  `fn add_one(v int) int { return v + 1 }`
  `fn main() int { goto done; done: let f fn(int) int = add_one; return f(41) == 42 ? 0 : 1 }`
  （`tests/modules/projects/llvmarchitecture/cases/lowering.yh` 暂将 goto 与
  函数指针放在独立函数，未降低断言）。需单独立项修复并补回归。

## 接口特性（IF1–IF5，方案待评审）

2026-10-24 取向已定：**显式 vtable 语法糖、零运行时魔法**——interface 展开为
`self` + 方法函数指针字段的普通 struct，impl 只做编译期检查，`s.m()` 是
`s.m(s.self)` 的糖。方案见
[接口特性实施方案](02-plan/yh-接口特性实施方案-2026-10-24.md)；按片立项，
实施顺序 IF1 → IF2 → IF3 → IF4/IF5。

- [ ] **IF1**：`interface` 关键字、类型登记（form=4、隐含 `self *void`）、
  方法槽必须是 fn 类型的检查。
- [ ] **IF2**：`s.m(args)` 插接收者糖（旧发射路径与 AST/lower 路径行为一致），
  首版接收者限变量名；comptime 内显式拒绝。
- [ ] **IF3**：`.s.i` v4（interface 发射/加载）与跨模块构造/调用用例。
- [ ] **IF4**：`impl` 纯检查（全方法覆盖、签名严格相等）、缓存与固定点复核、
  `docs/yh.g4` 与语义边界文档刷新、ADR。
- [ ] **IF5**：`tests/yh`、`tests/yh-run/{run,fail}`、`tests/modules` 门禁用例。

## 待决策（❓）

当前无未决项。2026-10-26 用户已决定两项，记录如下。

- **NP 定位（原 ❓1，已决定）**：**只保留 NP3**（受检契约与 lowering 解耦），
  NP0/NP1/NP2/NP4/NP5 关闭——NP0 口径并入现有 `make test` + O0/O2 + 自举门；
  NP1/NP2 的对象代码（`ir_simplify`、`ssa_inline`）已删除；NP4 由 ADR-0014
  取代；NP5 交 LLVM 默认管线。ADR-0011 已标注部分被取代，
  [方案](02-plan/yh-Nanopass风格优化架构实施方案.md) 与
  [设计](03-design/yh-Nanopass风格优化架构.md) 已改状态；NP3 作为唯一保留
  阶段记入「2026-10-24 架构优化」小节。
- **字面量只读化（原 ❓3，已决定：改语义）**：字面量进只读段 + 静态可判定的
  写入改编译期诊断，见 H1。

## 设计决定不做（非缺口，勿列为任务）

- **编译器模块 worker 上限（原 TG-3）**：`active < 4` 保持 ADR-0009 的过渡默认；
  实测放宽到 8 每次冷编只省 5–8s，峰值内存从约 490MB 升到约 800MB，收益不足。
- **批量 `--syntax-check`（原 TG-4）**：并行后只再省十几秒，性价比低。
- **用户裸 C 变参**：不开放 `printf` 等裸变参互操作；yh runtime `printf` 继续使用
  现有规则。
- **切片越界与生命周期运行时防护**（ADR-0001）。
- **`pub const A *char = base.TEXT;`（初始化式为模块限定名）**：名字池无限定名，
  只取尾段会指向本模块同名符号，属错误语义（编译期第 7 条）。
- **经指针写入编译期模型**（`&TABLE[0]` 后 `*p = 5`）：保持只读拒绝（fail/153）。
- **顶层 const 折叠 `$mk()[0]`**：前端折叠路径无法索引裸聚合对象指针；惯用写法
  `const T = $mk(); T[0]` 可用，不为此加特殊形态。
- **恢复 `asm/`、`link/` 独立项目**：2026-10-20 用户决定删除，由 LLVM + 内嵌 lld
  取代，不重建。
- **自研机器 IR / 寄存器分配 / 动态加载 libLLVM**：与 ADR-0014 冲突；JIT、LTO、
  32 位、ARM64EC 等无消费者扩展同样不做。
- **以 WSL 代替 Windows 原生支持**：B1 需 Windows 原生构建与运行。
