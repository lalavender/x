# todo

只记录**未完成**事项。已完成任务的历史与证据见
[finish.md](finish.md) 与 [01-finished/](01-finished/)；方案文档在
[02-plan/](02-plan/)，取舍见 [adr/](adr/)。

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
- [x] **C2 Linux/x64 闭包改运行时文件**：`tools/llvm-sdk.py` 生成
  `selfhost-runtime.txt`；0.0.7 三端种子不再带构建机闭包路径。
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

- [x] **E0 OS0–OS6 标准库实现（2026-10-21 恢复并验证）**：`libs/sys` 的
  raw6/文件/目录/内存/时间/进程原语与 `libs/os` 的结果/文件/目录/环境/进程
  API、io/time 平台拆分、默认标准库发现与安装布局已恢复并跑通。验证：
  Linux/arm64 容器 15 个 fixture、CLI 9/9、`make test`、`make selfhost-native`
  （115/115 项目用例）通过。见 `docs/01-finished/yh-os与sys-OS*.md` 与
  `docs/01-finished/yh-标准库默认发现-2026-10-21.md`。
- [ ] **E1 OS7 编译器迁移与独立性审计**：编译器改用 `libs/os`/`libs/sys` 的
  接口，减少对 C runtime 的隐式依赖；见[联合设计](03-design/yh-os与sys标准库设计.md)。
- [ ] **E2 OS8 Darwin 新接口**：Darwin 侧补齐目录/进程/时间等新接口，与 Linux
  契约对齐。
- [ ] **E3 SYS 消费者迁移与独立性**：SYS0–SYS7 中已实现的结果/文件/目录/内存/
  时间/进程原语，剩余消费者迁移与独立验收。
- [ ] **E4 libc L0–L5**：按[分阶段候选方案](02-plan/yh-libc分阶段候选方案.md)
  推进，未授权全部实施。

### F. project.toml 库文件链接（LINK，已随 0.0.7 发布）

普通项目与 F1 自举闭包迁移已落地并发布：`compiler/cmd/project_link.yh`、
`compiler/cmd/link_inputs.yh`、`--link` 解析、`[project].os/arch`、目标覆盖表、
路径/后缀/格式检查、`.build` 摘要缓存及 `linkgroups`/`linkshared`/反例 fixture；
`build-check.py` 111/111 通过。0.0.7 Release 三端种子已回读验证。

- [x] **F1 LINK3**：compiler 清单与自举脚本已迁移到 `[link]`：归档来自
  清单，运行库参数走 `YH_LINK_RUNTIME_FLAGS`，新编译器 manifest-only；
  Darwin/Linux arm64 固定点与自解析通过；Linux x64 清单已由 x64 宿主生成并
  通过 `link-closure.py check`，三端链接冒烟通过。`0.0.7-rc.1` 过渡 Release
  与 `0.0.7` 最终 Release 已发布，CircleCI 三端全绿，0.0.7 种子回读验证通过。

### G. C/C++ 桥迁移到 yh

见[可行性分析](01-finished/yh-C与C++代码重写可行性分析-2026-10-20.md)。

- [ ] **G1** 迁移 `compiler/llvm/bridge.c` 到 yh（LLVM 生命周期、初始化同步、
  有界诊断、原子发布），补正式 `.yh` 对等用例与错误路径。
- [ ] **G2** `lld_bridge.cpp` 的配置/argv/库搜索移到 yh，保留 `lldMain` 最小
  C++ 适配层与不可重入状态处理。
- [ ] **G3** 桩的构建期择一机制；迁移前保留 C 弱桩，避免重复强符号。
- [ ] **G4** SDK 身份、归档成员与自举闭包同步，候选引导后滚种子。

### H. 编译器可选收尾

- [ ] **H1 字符串字面量只读化评估**：字面量放只读段，可写副本走显式复制；
  收益是省一个 16KB 可写段，代价是语义变更（字面量改为不可变），需评估现有
  语料与 `tests/yh-run/` 影响后再决定。
- [ ] **H2 分号清理（SC，0.0.8-rc）**：换行终结已在 `0.0.8-rc` 落地并通过
  `make test` / `make selfhost-native`（201 + 82 处续行迁移，记录见
  [完成记录](01-finished/yh-换行终结语句-2026-10-22.md)）。**剩余**：发版滚种子
  后删除 `compiler/` 的 24,466 个冗余分号（保留 1,061 个同行分隔），再刷新
  文档与二次滚种子；顺序与验收见[方案](02-plan/yh-分号清理实施方案.md)。

## P2 长期与按需

- [ ] **I1 MOD-U6**：远程来源、版本规则、锁文件与工作区，按实际需求另立设计与
  验收（不沿用旧 Go 方案承诺）。
- [ ] **I2 VS Code 扩展**：VS-U0 最小扩展与 LSP → VS-U1 保存后诊断与取消 →
  VS-U2 未保存缓冲与精确跳转 → VS-U3 调试信息与 DAP → VS-U4 集成测试与发布。
  见[方案](02-plan/yh-VSCode扩展方案.md)。
- [ ] **I3 R3 剩余**：printf 按需扩展（宽度/精度/浮点）、完整 OS 导入清单审计
  （`nm -u` 允许清单）；线程 API 已并入「后续任务」。
- [ ] **I4 编译器缺陷清单**：11 项已全部修复或复核为不再复现，无待办；新缺陷按
  「先复现、再红绿回归、后修」入本清单。

## 后续任务：首个完整 SSA 版本（非 LLVM 收尾）

性能测试由**专门任务**承担，本文件不重复 20 轮对照与性能口径。以下为 RS2/RS3/
R2c 与增量能力，排在 LLVM 收尾之后按需启动：

- [ ] **J1 RS2 函数级 check/IR 缓存**（真缺口）：LLVM 模式按函数缓存受检事实与
  IR，worker 统计可见（当前 `ir_cache_hits=0`）；必须在 Linux 宿主实施；目标
  单函数修改 200ms（当前约 743/818ms）。
- [ ] **J2 RS3 文件级对象**：按 [R2 收尾计划](02-plan/yh-R2收尾实施计划.md) 的
  RS3a private 可见性 → RS3b 按文件发射/桩对象/多路写出 → RS3c 文件级键与
  manifest → RS3d 用例测量；设计已定稿，约 40+ 步。
- [ ] **J3 RS5 收口报告**：依赖 J1/J2，复核优化覆盖与缓存提交协议。
- [ ] **J4 R2c 线程池**：宿主线程桥（Linux clone / Darwin 审核 libSystem）→
  libs/sys 线程原语 → 编译器线程池与接口调度隔离；完成前 fork/COW worker 是正式
  过渡执行器，「串行与多 worker 输出一致」继续作为回归门。
- [ ] **J5 增量/冷编时间**：单函数 200ms、冷编 1s 目标未达；仍整模块重新汇编且以
  外部汇编器为主，主要靠 J1/J2 关闭。

## 待决策（❓）

- **❓1 Nanopass 定位**：LLVM 已接管通用优化与寄存器分配。建议 NP3 并入受检契约
  与 lowering 解耦，NP0/NP1/NP2/NP4/NP5 关闭（NP4 自研机器 IR 与 ADR-0014
  冲突）；需用户确认后再改
  [Nanopass 方案](02-plan/yh-Nanopass风格优化架构实施方案.md) 与 ADR-0011。
- **❓3 字面量只读化**：见 H1，属语义变更，需单独决定。

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
