# todo

只记录**未完成**事项。已完成任务的历史与证据见
[finish.md](finish.md) 与 [01-finished/](01-finished/)；方案文档在
[02-plan/](02-plan/)，取舍见 [adr/](adr/)。

图例：P0 发布质量与主线；P1 标准库与工具链；P2 长期与按需；⏸ 用户暂缓；❓ 待决策。

## 2026-11-03 CI 迁移到 GitHub Actions（已提交，待滚种子后实跑验收）

`.github/workflows/{ci,release,perf}.yml` 已落地（四端 GitHub 托管 runner、无容器），
`.gitea/` 已删除。分支 `ci/github-actions` 上完成了本机与 WSL 证据链；
**GitHub 上的四端 job 按用户要求暂停到「本次滚种子」完成后再跑**。

- [ ] **实跑验收（P0）**：滚种子完成后触发 `ci.yml`，四端 job 全绿；再验证
      `release.yml`（打 rc tag）与 `perf.yml`（workflow_dispatch）首次实跑。
- [ ] **移除过渡期自举桥（P0）**：0.0.11 的 Linux/macOS 种子早于 W2（不认识
      `windows` comptime 标记、15 个 `*.windows.*.yh` 变体与 `[link-windows-x64]`），
      CI 暂用 `just bootstrap-bridge`（`tools/ci-bootstrap.py`，两代冷编）。含 W2
      种子的新 Release 发布后：ci.yml/release.yml 切回 `just bootstrap`、自举门改回
      默认种子，删除 `tools/ci-bootstrap.py`、`just bootstrap-bridge` 与本条。
      桥存活期内 `compiler/`、`libs/` 源码必须保持可被 0.0.11 解析（`$if (windows)`
      由桥改写；相邻字符串字面量拼接等新语法会直接编不过——2026-11-03 已被一次
      相邻字面量拼接打红）。
- [ ] **Windows 种子过渡资产**：`yh-0.0.11-windows-x64.tar.gz`（本机按 HEAD 重编的
      Windows 种子，sha256 `0969209e…`）是追加到已发布 0.0.11 的资产，不是该版正式
      产物；下一版 Release 正常产出 Windows 资产后改用常规取种。
- [ ] **Windows 闭包 CI 冷启动成本（P1）**：Windows 静态 LLVM/lld 闭包由 CI 机器
      源码 MSVC `/MT` 构建（首次约 1 小时、563 MB，actions/cache 命中后秒级）。
      需要降低冷启动时按 C1 做固定 SDK 预编译分发。
- [ ] **Windows testkit 断言位置/提前退出（P0，W2-9 遗留）**：
      `tests/modules/test-check.py` 的 `execute-fail*` 在 Windows 上把断言位置记成
      编码残值、提前退出被归到崩溃分支；需等源码闭包重建后的完整输出再定型修法。

## 2026-10-27 未使用函数检查（UF1）后续

UF1 已生效（`build/unused_function.yh`，见 [finish.md](finish.md) 与
[模块与包设计](03-design/yh-Go风格模块与包设计.md)）。当前实现按「模块内出现过
同名标识符」判使用，方向是保守（宁漏报不误报）。

- [ ] **UF1 精确化**：把「按名字的 token 扫描」升级为「按解析身份的引用集合」，
  覆盖两个已知漏报：同名局部变量/字段遮蔽、递归但无外部引用的孤立函数。
  前置条件是把引用事实随函数级 check 切片携带（`module_snapshot_check_slice.yh`
  的 global 符号表已按名字重绑定，但正文命中时不做解析），否则增量构建会把
  活函数判死；`$f(...)` 编译期调用与生产构建的 `test` 正文也要单独补登记。

## CLI-R 遗留（2026-10-27 方案）

方案见[用 cli 标准库重写 yh 命令行](02-plan/yh-CLI用cli标准库重写实施方案-2026-10-27.md)：
声明与解析已收进 `libs/cli`，`driver.yh` 的手写扫描与逐行 `usage()` 已删除，
argv 形态与旧调用面逐字节等价。只剩下面一条观察项。

- [ ] **CLI-R1d lowering 聚合初始化（常见但不复现，降级观察）**：CLI-R1 期间
  `compiler/cmdline` 的声明代码曾报「首片不支持此聚合初始化形态」（
  `lower/module_snapshot_lower_place.yh` 的 `checked_lower_aggregate_store` 返回非 0），
  当时靠把 `Value`/`Default` 先 hoist 到局部绕过。2026-10-27 复查：用
  `let spec cli.Argument = cli.option(...)` + `spec.default_value =
  cli.suppress_default()`、嵌套 `cli.default_of(cli.value_i64(0))`、以及
  `-o` + `dest` 的原始组合都无法在独立项目或 compiler 项目里复现（代码已改为
  hoist 写法，且 `compiler/.build` 已冷清）。**暂不作为缺陷推进**：保留 hoist 作为
  声明代码的推荐写法，若再次出现再按 lowering 缺陷立项并补最小用例。
  2026-10-28 起聚合存储的来源面已扩大（新增聚合三目与三目结果取址，
  `tests/yh-run/run/210` 覆盖调用/字段/下标/三目来源），复现概率进一步下降；
  如再现先看 `checked_lower_aggregate_store` 的来源分支。

## 编译器性能测试（2026-10-23 方案）

PF0–PF4 已全部落地（**不设硬门**，CI 只出报告与资产），口径见
[性能方案](02-plan/yh-编译器性能测试方案-2026-10-23.md) +
[归因口径](02-plan/yh-编译器性能归因口径-2026-10-26.md)，数字与留证见
[PF1b 基线](01-finished/yh-编译器性能基线PF1b-2026-10-26.md)、
[PF2 归因/失效矩阵](01-finished/yh-编译器性能归因与失效矩阵PF2-2026-10-26.md)、
[PF3 规模/并发](01-finished/yh-编译器规模与并发扩展PF3-2026-10-26.md) 与
[噪声校准与判定规则](03-design/yh-性能回归判定与噪声校准-2026-10-26.md)。
当前基线：冷编 10.1 s / 全量重编 16.8 s / 热编 0.98 s / 单函数改动 3.6 s（O0，20 轮），
O0 冷编 worker 累计 23.5 s 里 lowering 66%、IR 构造 20%、内嵌桥 8%、前端 6%。

注意：各批次语料/二进制 SHA-256 不同（加打点、加 `YH_WORKERS`、期间另有会话改链接层），
报告里都有「批次身份」表——跨批只比段落结构与同批内比值。未完成：

- [ ] **PL1d2b `ir_verify` 内部（便宜的方案已排除）**：函数体 SSA 校验占
  verify_function 的 83%（2.97 ms/函数）。已实现并实测「值→类型表」+「值位置表」把
  两处 O(n²) 扫描降为 O(n)——verify 占 lowering **17.2% → 17.0%，无可测收益**，已回退
  （真实函数 100–500 条指令，扫描 <2%）。只剩两条路：① 换支配性算法
  （Cooper-Harvey-Kennedy / bitset 定点）；② 论证「发布构建关闭模块 verify」的替代门
  （它是 lowering 之后唯一语义兜底）。
- [ ] **PL3b cgroup 峰值**：Linux cgroup v2 `memory.peak`（需要可写 cgroup 层级）。
  **本机不可验证**（Darwin 无 cgroup），留到 Linux 宿主/容器里接；Darwin 侧只能采样。

### 首轮归因发现的优化项（2026-10-25，历史）

[归因分析](02-plan/yh-编译器性能分析-2026-10-25.md)给出冷编 26 s / 热编 2.4 s / 单函数
改动 7 s 的阶段归属：`capture`（函数级 IR 缓存序列化）占冷编 worker CPU 56%，
关闭后冷编 −46%；而增量场景实测命中 0%（IR）/ ≤9%（check）。

**2026-10-26 PF2 复测已改写这张图**：PC3 关掉冷编写缓存后，冷编 worker 累计 23.5 s 里是
lowering 66% / IR 构造 20% / 内嵌桥 8% / 前端 6%（见上面的 PF2 报告），
`capture` 不再是瓶颈。以下保留仍未关闭的项，按收益排序：

- [ ] **PC2d 按模块共享类型表**（取代 PC2c，格式 v3 级）：记录改为引用模块级类型池
  （池带版本/校验），目标把 25.1 KB/条降到 ~5 KB，capture 13.4 → 5–6 ms/条。
  依赖：类型池文件的原子提交与失效规则要一起设计。
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
- [ ] **PC7 函数级目标文件**（单函数改动的 ≤3 s 与 O2 的整模块重优化都只能靠它；
  本轮确认立项）：可行性见
  [函数级目标文件可行性](03-design/yh-函数级目标文件可行性-2026-10-26.md)。
  量化依据（PF2 + PL1）：O0 单函数改动 3.6 s 里，模块级 LLVM 发射（object）≈0.5 s、
  链接 ≈1.3 s，其余是 lowering/缓存合并；**O2 单函数改动 7.55 s，其中内嵌桥 3.59 s**
  （整模块 LLVM 优化被重跑）。方案 A（每函数一个 `.o`）或 B（桥批处理，需改桥 ABI →
  滚种子），工期按天计；落地前单函数改动停在 ~3.5–3.9 s（O0）/ ~7.5 s（O2）。
- [ ] **LC1 Linux 对等**：Linux 宿主的裸跑仍靠 `YH_LINK_RUNTIME_FLAGS`
  （`-lstdc++`/`-lpthread`/`-lxml2`…）。要么给 Linux 闭包生成对应的 `.so` 路径输入，
  要么把运行库参数换成清单键（2026-10-25 试过 `[link-options].runtime`，但当前
  种子不认该键，需先滚一代种子再落地）。验证：Linux 上
  `cd compiler && ../bin/yh-linux-arm64 build` 不设环境变量就能链接。
- [ ] **LC2 闭包清单门扩展到 Linux**：`tools/link-closure.py check --host …` 目前只
  接进 `make test-llvm-darwin`；Linux 的对应门未接（需先有 Linux 宿主记录验证）。
- [ ] **LC3 F2-9 交叉**：Linux→Darwin 交叉仍需目标包自带 `libc++.tbd`
  （见 `03-design/yh-Darwin交叉编译遗留边界.md` §2）。

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
  冒充 Windows 支持。**2026-10-27 已出方案并拆片**，见
  [Windows/x86_64 LLVM 后端接入实施方案](02-plan/yh-Windows-x86_64-LLVM后端接入实施方案-2026-10-27.md)：
  W0 前置（目标标记两代顺序）→ W1 交叉目标（8 片）→ W2 原生宿主（7 片）→ W3 矩阵。
  **D1/D2/D3 已确认（2026-10-27）：MSVC ABI + 零 CRT + W1→W2**；并行编排见方案 §12
  （七条 lane、四个串行热点文件、工作树/缓存隔离规则）。

  **已核实的地基**（勿重复实现）：桥已放行 `x86_64-pc-windows-msvc`
  （`compiler/llvm/bridge.c:119`）；内嵌 lld 已注册 COFF 驱动
  （`lld_bridge.cpp:19–21,191`）且 LL9L 探针已出 PE（`tests/selfhost/llvm-lld.py`）；
  构建目录按 triple 隔离（`module_build.yh:149`）。

  - [x] **W0-1 WSL 编译环境**（2026-10-27 完成）：`Ubuntu-26.04` + **原生
    `linux-x86_64` 种子**（不需 qemu/交叉 gcc）；5 项环境适配：proxy
    `127.0.0.1:7897`、`libxml2.so.2` 兼容软链（种子按 24.04 构建）、`gcc-13`（种子烘焙
    的 crt 路径）、`clang`（runtime-memory 审计）、`XDG_RUNTIME_DIR`（`/run/user`
    noexec 导致 just shebang 配方 EACCES）。数字：llvm-host 99 s、冷编 37 s、
    `selfhost-native` 321 s 全绿。详见 `docs/finish.md`。
  - [x] **W0-1b 并行安全**（2026-10-27 完成）：每条 lane 一个 `git worktree`（`just` 会冷编
    并覆写根 `yh`、`stage-yh` 会覆写 `FAST_DIR`、`.build`/`tmp` 共享）；`YH_LLVM_CACHE`
    共享只读，`FAST_DIR` 每 lane 唯一；W0-2a 滚种子已在干净工作树上完成。
  - [x] **W0-2a 目标标记两代顺序**（2026-10-27 完成并已滚种子）：`TARGET_OS_WINDOWS`、
    `ct_target_symbol` 认 `windows`、`pj_source_target_match` 认 `windows` 后缀；
    用例 `tests/yh/positive/74-*` + `tests/yh-run/run/207-*`；语法 82/82、反例 49/49、
    运行 358/362；arch-check `max_build_lines` 10807→10809（+2，目标表必要分支，已写明理由）。
    种子：`5ef7612e…` → `0757ebcc…`，新种子重跑 `selfhost-native` 360 s 全绿。
    **now 源码可写 `$if (windows)`。**
  - [ ] **W0-3 决策冻结**（2026-10-27 完成）：D1/D2/D3 已写入方案 §3 并记入
    `docs/finish.md`：D1 = `x86_64-pc-windows-msvc`、D2 = 零 CRT（只依赖 KERNEL32）、
    D3 = W1 交叉目标先行 → W2 原生宿主。
  - [x] **W0-4 文档卫生（2026-10-27 复核：误报，无需订正）**：早先看到的「n」是
    `rg -rn "Windows"` 里 `-r n`（replace）把匹配替换成 `n` 的**命令输出**，不是文件内容；
    `03-design/yh-LLVM后端替换设计.md`、`02-plan/yh-LLVM后端替换实施方案.md` 原文均为
    「Windows」。教训：`rg` 的 `-r` 是替换，查匹配不要带 `-r`。
  - [x] **W1-1 目标身份**（2026-10-27 完成）：`TARGET_OS_WINDOWS` + `x86_64-pc-windows-msvc`
    表项（`abi=win64-msvc`、clang oracle 核对的 `data_layout`）、`target_select_os_arch`；
    **同时补 `ir/ssa_module_00_model.yh` 的第二份目标表**（key=5，否则 lowering 静默失败）。
  - [x] **W1-2 Win64 ABI 门**（2026-10-27 完成，W1-2b 另计）：`llvm_target_same` 白名单、
    `llvm_abi_supported` 的 win64 分支（标量/指针放行，按值聚合给目标级诊断）、`printf`
    裸变参放行；clang oracle 结论（i8/i16 无 signext、≤8 字节聚合强转成 i64）已写进注释。
  - [x] **W1-2b Win64 按值聚合**（2026-10-27 完成）：`llvm_abi_classify` 的 win64 分支
    （1/2/4/8 字节 → 单 INTEGER 分片，其余 MEMORY）、MEMORY 参数发普通 `ptr`（SysV 仍 byval）、
    `llvm_abi_supported` 放行 struct/union。新门 `just test-windows-abi` 用 clang 编的 C 桩
    做真实互操作（4/8/12 字节 + 纯浮点，参数与返回），Windows 侧实跑通过。
  - [x] **W1-3 Windows 运行时与入口**（2026-10-27 完成）：新 `backend/llvm_windows_runtime.yh`
    （HeapAlloc/HeapFree、`GetStdHandle`+`WriteFile` 的 printf、write/exit 薄层）、`/entry:main`
    入口、`llvm_runtime.yh` 拆出平台无关 printf emit；另修两处 MSVC ABI 细节：自定
    `@_fltused`、**alloca 全量提升到入口块**（修“聚合实参直接进 printf 崩溃”），并留
    `no-stack-arg-probe` 兜底超大静态帧。
  - [x] **W1-4 导入库与 SDK stub**（2026-10-27 完成，lane B）：`compiler/windows-sdk/`
    （`def/kernel32.def` 9 条最小导出面 + `manifest.json` 带 `def_sha256` + `README.md`）、
    `tools/windows-sdk.py`（generate/check/paths；生成器优先级 `llvm-dlltool` →
    `lld-link /lib` → `lib.exe`，前两者产物逐字节相同）、
    `tests/selfhost/llvm-windows-sdk.py`（清单↔def、两次生成字节相同、符号面
    `X`+`__imp_X`、探针只依赖 KERNEL32 且在 Windows 上实跑）、`just windows-sdk` /
    `just test-windows-sdk`。仓内只放文本 `.def` + manifest，`.lib` 构建期生成
    （根 `.gitignore` 忽略 `*.lib`）。**本机全绿**：`rc=0`，探针 PE 实跑输出
    `windows-sdk-probe` 与退出码 5。**剩余**：编译器侧消费（查找顺序 + 注入
    `kernel32.lib`）归 W1-5；CI 接线归 W1-7。
  - [x] **W1-5 COFF/PE 链接**（2026-10-27 完成）：新 `build/windows_link.yh`（SDK 查找、
    固定模板 `/Brepro /nodefaultlib /subsystem:console /entry:main`、一次性子进程跑内嵌
    lld WinLink 驱动）、`mb_link` + 单文件 `-o` 接入、`mb_object_machine_matches` 加
    COFF/PE 分支；门 `just test-windows-target` + Windows 侧 `tests/windows/run-exe.py` 全绿。
  - [x] **W1-6 清单目标节与库格式**（2026-10-27 完成）：`project.os="windows"` 合法、
    `[link-windows-x64]`/`[link-windows-arm64]` 与 `pl_target_code_current` 接入；
    `link_inputs` 支持 `.lib`（ar 归档，kind=1）与 `.dll`（PE + machine 0x8664 校验）；
    `tests/modules/projects/linkbad` 的非法节名负例改用 `[link-windows-sparc]`；
    门禁 `just test-windows-target` 新增两个库输入断言（合法 `.lib` 可链接、非 PE 的 `.dll` 被拒）。
  - [x] **W1-7 跨机门禁**（2026-10-27 完成主体）：`tests/yh-run/check.py` 加
    `--run-platform` / `--emit-manifest`（只编译 + 写清单），`tests/windows/run-exe.py` 在真
    Windows 执行比对；just 目标 `test-windows-target`（6 例专项）、`test-windows-corpus`
    （编译侧全量）、`run-windows-corpus`（Windows 侧）。实测 **202 例语料在 Windows 全过**，
    Linux/Darwin 主门未回归。**剩余**：CI 接线（windows job 跑这两个目标）、
    `// platform: windows-x64` 这类正向用例（现在靠“无标签 + run-platform 推导”覆盖）。
  - [x] **W1-3b Windows read/argv/exit**（2026-10-27 完成）：`read`（GetStdHandle(-10)+
    ReadFile）、`mainCRTStartup`（GetCommandLineA 解析 argv）+ `/entry:mainCRTStartup`、
    `exit/_Exit` 走链接期 `/alternatename` 映射到 ExitProcess。已解除 `21-main-argv`、
    `16/17/18-read-*`（18 仍因 `/dev/null` 保持标注）、`51-noreturn-exit`、
    `pass/07-noreturn-branches` 的标注；Windows 侧语料 **206/206**。
  - [x] **W1-3d Windows 文件 API**（2026-10-27 完成）：fd 表（`linkonce_odr [64 x i64]`）+
    `open/close/read/write/mkdir/unlink/rename` 的 Win32 映射（POSIX flags → CreateFileA
    的 access/disposition，O_APPEND 用 SetFilePointer 模拟）；门禁新增 `file_api` 往返用例，
    Windows 侧 7/7。**仍缺**：`errno` 语义（当前只返回 -1）、`/dev/null` 类设备名映射、
    目录句柄与管道继承（`18-read-empty-badfd` 因此仍标平台）。
  - [x] **CI 接线**（2026-10-27）：linux-arm64 容器内跑 `test-windows-sdk` /
    `test-windows-target` / `test-windows-corpus`；镜像加 `llvm-18 lld-18` + 工具软链。
    **运行侧**仍只在真 Windows 上跑（`just run-windows-corpus`），待 W2 的 windows runner。
  - [x] **W1-3c（守护片）**（2026-10-27）：实测帧阈值——16 KB 帧可用、**32 KB 必崩**；
    `llvm_frame_guard` 在 win64 下统计每函数 alloca 总量，**>16 KB 编译期拒绝**并给
    「改堆分配」诊断；`just test-windows-target` 加大栈帧负例；`"no-stack-arg-probe"` 保留。
    `29-stress-capacity` 的 `// platform: linux darwin` 现在有明确原因。
  - [x] **W1-3c（真修）**（2026-10-27 完成）：`compiler/windows-sdk/chkstk.c` 的 naked-asm 桩
    经 `just windows-sdk`（clang）编成 `__chkstk.obj` 随 SDK 分发；链接固定带上它，
    `"no-stack-arg-probe"` 与 16 KB 帧上限**均已移除**。`29-stress-capacity`（160 KB 帧）
    解除标注并在 Windows 跑对 → 语料 **207/207**。
  - [ ] **W1-2b-2 CRT extern 互操作决策**（详见下文 W2 段的同名条目）：`@[extern]` 的
    libc 函数（abs/strtoul/_Exit/…）在零 CRT 下没有解析目标。`abs`/`putchar`/`_Exit`/
    `isatty`/`rmdir`/`usleep` 已由 SDK 支撑对象 + `/alternatename` 解决；
    `strtod/cos/pow/lrint/dup2/system` 仍待决策（`build-check.py` 的 `WINDOWS_SKIP`）。
  - [x] **W1-8 设计文档**（2026-10-27 完成）：新增
    `docs/03-design/yh-Windows-LLVM后端设计.md`——目标身份（两份表）、Win64 ABI 边界、
    零 CRT 运行时契约、入口/argv、链接模板与导入库查找、**六个必记坑**（PIC 重定位、
    `_fltused`、`declare`+`define`、alloca 提升、栈帧上限、COFF 必须 COMDAT）、不支持边界与平台差异表、
    门禁两侧分工。`docs/yh.g4` 未动（无语法变化）。
  - [x] **W2-1 宿主身份**（2026-10-28 完成）：`target_host_info` 的 `$if (windows)`；
    新增 `gen.tg_host_windows()`（编译期按目标/宿主身份选择）用于 PATH 分隔符、
    路径分隔符等宿主文件操作；`mb_resolve_self_path` 认反斜杠且按 `;` 切 PATH，
    `mb_load_default_stdlib` 认反斜杠。open 旗标沿用非 Darwin（Linux 位值）分支，
    Windows 运行时按同一套 POSIX 位解释，因此三处二选一无需第三分支。
  - [x] **W2-3a 宿主文件**（2026-10-27）：`build/project_dir.windows.x64.yh`
    （FindFirstFileA + 手写 WIN32_FIND_DATAA 布局）、`build/clock.windows.x64.yh`
    （QueryPerformanceCounter，先秒+余数再换算防溢出）、`backend/llvm_bind.windows.yh`；
    编译器整套源码 `yh check --target x86_64-pc-windows-msvc` 通过。
  - [ ] **W2-0 流程前置（挡合入）**：`$if (windows)` / `*.windows.*.yh` 需要「认识 windows
    标记」的**发布种子**；当前只有本地滚过的种子（W0-2a），Release 0.0.10 不认识 →
    正式合入 W2 改动前必须发 0.0.11-rc（种子来自上一个 Release）。
  - [ ] **W2-2 windows-x86_64 静态 LLVM/lld SDK 分发**（2026-11-02：`just llvm-host`
    已能校验并记录该闭包的身份，但归档本身仍在仓库外）：本机已用 MSVC 构建出
    1.7 GB / 121 个 `.lib` 的静态闭包（`-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded`、
    `LLVM_TARGETS_TO_BUILD=X86;AArch64`、`LLVM_ENABLE_PROJECTS=lld`，关闭 tests/examples/
    benchmarks/docs/zlib/zstd/libxml2）。**剩余**：`vendor/llvm/sdk.lock.json`、
    `tests/selfhost/llvm-host.py` HOSTS、`tools/llvm-host.py` shim 与 Release 资产化
    （闭包不入库，与 Darwin SDK 同处理）。
  - [x] **W2-2c Windows 宿主闭包与 yh.exe**（2026-10-28 完成）：
    - **桥**：`bridge.c` 的 Windows 适配（InitOnceExecuteOnce、`_unlink`/`_write`/`_close`、
      `STDOUT_FILENO`、`ssize_t`、`mkstemp`→`_mktemp_s+_open(O_CREAT|_O_EXCL)`）；
      新增 `compiler/llvm/windows_shim.c`（stat/realpath/setenv/usleep/
      fork/waitpid/kill 垫片 + `CreateProcessA` 的 `yh_win_spawn_wait`）；
      `clang-cl /MT` 编三对象，`lib.exe` 打成 `tmp/winhost/libyh-llvm-bridge.lib`。
    - **清单**：`[link-windows-x64]` = bridge 1 + lld 6 + llvm 114 + support 15
      （libcmt/libcpmt/libvcruntime/libucrt/oldnames/comsuppw + kernel32/ntdll/ole32/
      oleaut32/uuid/advapi32/shell32/user32/psapi）；**去掉 `LLVM-C.lib`**（那是
      DLL 导入库，会把 yh.exe 变成依赖 LLVM-C.dll 的进程，实测崩溃）。
      `[c] sources` 从 project.toml 移除：桥已由清单强定义提供，Windows 上的弱桩
      还会与静态 CRT/桥冲突。
    - **COFF 链接语义**：weak 运行时/`_fltused`/fd 全局都加 `comdat any`（COFF 的
      weak 不能合并同名定义，lld-link 会报 duplicate symbol）；`open` 加
      FILE_FLAG_BACKUP_SEMANTICS（允许 open 目录，`path/.` 探目录可用）；
      fd 表改为扫空槽复用（原来只增不减，>64 次 open 后必失败）。
    - **入口与栈探测**：发射的零 CRT 入口改名为 `__yh_zero_crt_start`，
      `/entry:mainCRTStartup` + `/alternatename:mainCRTStartup=__yh_zero_crt_start`：
      有静态 CRT 时用 CRT 启动（C++ 静态构造/argv/envp/stdio），零 CRT 时才落到自备桩。
      栈探测桩改名 `__yh_chkstk`（导出符号），`/alternatename:__chkstk=__yh_chkstk`，
      静态 CRT 自带 `__chkstk` 时不会重复定义。
    - **无 fork 链接**：`mb_coff_link_worker` 在无 fork 宿主进程内跑 lld；lld 的输出
      句柄活到进程退出（fopen 会 EACCES），因此直接写最终路径，跳过格式复核与
      链接缓存哈希（下轮必重链，产物完整）。
    - **结果**：交叉 yh.exe → 原生自编两代固定点 `0969209e…`；`bin/yh-windows-x64`
      已落盘（W2-6）。
  - [x] **W2-2b Windows 宿主的运行库策略**（2026-10-28 完成）：静态
    `libcmt + libcpmt + libvcruntime + libucrt + oldnames + comsuppw + 系统导入库`；
    实测导入表只有 ADVAPI32/KERNEL32/ntdll/ole32/OLEAUT32/SHELL32，不需 VC++
    可再发行包。`__chkstk`/入口用 alternatename 同时兼容静态 CRT 与零 CRT。
  - [x] **W2-3 宿主 OS 桥**（2026-10-28 完成）：`project_dir.windows.x64.yh`、
    `clock.windows.x64.yh`、`backend/llvm_bind.windows.yh`，宿主 prelude 的
    open/read/write/close/mkdir/unlink/rename/getpid/getppid 由 Windows 运行时发射；
    `open` 目录语义与 fd 表复用在 W2-2c 一并修好。
  - [x] **W2-4a 修复**（2026-10-28 完成）：Windows 模块编译改为**每模块一次性子进程**
    ——`mb_spawn_module_child` 用 `CreateProcessA` 重入 `--emit-module`，父进程等
    退出后按 pid=0 走完成分支；子进程自己装载主项目并重建拓扑序。不再串行复用
    前端状态，W2-4a 的「stage 7 快照污染」从结构上消失。原生两代固定点已验证。
  - [ ] **W2-4b 链接与测试的进程模型（部分完成）**：**lld worker 已改为
    `CreateProcessA` 重入 `yh --lld-link <rsp>`**（2026-11-02 修通：子进程 stdout 必须接
    NUL、stderr 写文件再由父进程回放，见设计文档 §6.8；原生两代固定点已用它产出）。
    **剩余**：`cmd_process_run/capture` 与 testkit 的用例子进程仍走 fork/exec
    （垫片返回 -1），因此 `yh run` 与 Windows 上的 `yh test` 还不能执行用例。
  - [x] **W2-5 just/取种（2026-11-02 完成）**：`host_os == "windows"` 的 `py`/`seed_platform`/
    `PYTHONUTF8`、种子 `bin/yh-windows-x64`、`seed_platform=windows-x64`、
    `llvm_host=windows-x86_64` + `tools/llvm-windows-host.py`（闭包身份记录与失效检测）、
    `seed`/`install` 把 `windows-sdk` 放到 `<exe_dir>/windows-sdk`。
  - [ ] **W2-5b CI 的 `windows-x64` job（2026-11-03 已接线，待实跑）**：
    `.github/workflows/ci.yml` 已加 `windows-x64`（windows-latest）job：取种 →
    `just llvm-host`（MSVC `/MT` 源码构建闭包，actions/cache）→ `just build` →
    `just test` → `SKIP_CORPUS=1 selfhost-native` → `test-windows-target` /
    `test-windows-corpus` / `run-windows-corpus`。实跑验收与剩余 testkit 断言位置
    问题见「2026-11-03 CI 迁移到 GitHub Actions」段；闭包冷启动成本见该段。
  - [x] **W2-6 首个 Windows 种子**（2026-10-28 完成）：`bin/yh-windows-x64`
    SHA-256 `0969209e9b213f4d4998c48c913119fcf3c0cf06db373cbac0722e5d111905a9`；
    先由交叉 yh.exe 引导、再用它自编一次得到逐字节相同的产物。首次手工写入
    `bin/`（just 的 Windows 宿主分支归 W2-5）。
  - [ ] **W2-8 COFF 整库加载（新发现）**：`[link-options-windows-x64] whole` 现在会
    变成 Darwin 的 `-force_load`，lld-link 只告警并忽略。两条路：实现
    `/wholearchive:<path>`（需在 mb_link 里拼单参数 + 新缓冲，函数行数超预算），
    或保持「桥入口均被直接引用、不整库加载」。当前走后者（project.toml 不写该节，
    `pl_options_code_from_section` 已认 windows 项，留作后续）。
  - [x] **W2-7 标准库平台变体（2026-11-02 完成）**：`libs/sys`（errno/常量/文件/内存/
    时间/进程/套接字桩）、`libs/os`（目录/进程）、`libs/time`、`libs/json`、`libs/toml`
    的 `.windows.yh` 全部落地；`os.platform()` 认 windows；SDK 导入面 +14 条；新增
    `tests/modules/projects/osdirswin/`、`tests/yh-run/run/213-windows-fd-errors.yh`
    （`// platform: windows`）与 `build-check.py` 的 `OS_WINDOWS_CASES`（6 个夹具）。
    **`just test` 在 Windows 首次全绿**（语法 82/82、反例 49/49、运行 208/208、
    fail 137/137、pass 9/9、libs 122/122、compiler-tests 4/4、arch-check 通过；
    固定点 `621d03d3…`）。同轮修掉的真缺陷见 finish.md（负 fd、`_fltused` O2 丢弃、
    测试入口单字节用例号、`--scan-file` 误约束标准库、`yh run` 相对路径、
    `YH_TEST_RECORD` 竞态）。
  - [x] **W2-9 Windows 双主门收口（2026-11-03 完成）**：`just test` 与
    `just selfhost-native` 在 Windows 上同时全绿（project cases 128/128，固定点
    `5313b53b…`）。修掉的缺陷：冷/暖标记没传给子进程（`--no-firc`）、`[c].sources`
    用 clang、`-lm` 跳过、安装布局标准库发现的混合分隔符、外部命令的 PATH 启动、
    退出码 8 位语义、`abs`/`putchar` 提供者。细节见 finish.md。
    **门禁按平台分流**：`llvm-function-cache.py` 通过；`link-cache.py` 增加
    `windows_main`（内嵌后端没有外部汇编器，改按 link 计数 + 对象字节验证）；
    `build-check.py` 增加 `WINDOWS_SKIP`（22 例宿主 libc/libm/POSIX 边界）。
  - [ ] **W1-2b-2 零 CRT vs UCRT 决策（当前挡住 22 个 build-check 用例）**：
    现状是零 CRT（只链 kernel32），因此 `strtod/abs/cos/pow/lrint/dup2/system`
    这类 C 库符号在 Windows 用户程序里不存在：`libs/math`（sqrt/sin/cos/pow）、
    `libs/libc`（abs 已由 SDK 支撑对象提供）与 C 互操作夹具都受影响。两条路：
    (a) 保持零 CRT，把需要的符号逐个用 yh 或 SDK 支撑对象实现（math 尤其昂贵）；
    (b) 接 UCRT 导入库（`ucrtbase.dll`），一次解决全部 C 符号，代价是用户程序依赖
    `ucrtbase.dll`（与方案 D2 冲突）。**决定后再删 `build-check.py` 的 `WINDOWS_SKIP`。**
  - [ ] **W2-8 COFF 整库加载**：`/wholearchive:` 未实现（Darwin 的 `-force_load` 会被
    lld-link 忽略）。当前桥入口都被直接引用、不需要整库；若要支持，在 `mb_link` 里把
    `[link-options-*].whole` 拼成单参数 `/wholearchive:<path>`（需新缓冲，函数行数超预算，
    随 B2 的 link 簇拆出一起做）。
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

### cli 标准库复核遗留（2026-10-27）

只读复核覆盖 `libs/cli` 生产代码 12 文件；已完成死代码清理、argparse 对齐批 1
（语义：`set_default` 未声明 dest、位置 `optional` 默认值、槽 token 预留、
`store_const` const 校验、位置参数 `required` 校验、默认值不参与 choices）与
批 2（展示：choices `{a,b}`、`metavars`、槽 `{a,b} ...`/`title`/`description`/
`metavar`、`boolean_optional` usage、`max_help_column`）、批 3（诊断：choices/子命令
候选列表、`suggest_on_error` 覆盖 choices 与子命令、多余 token 全量列出）与
CLI-B（`put_*` 短路契约、溢出 return resource_error）、CLI-D（构造器合并、诊断码
常量、参数文件上限常量、测试助手复用 `libs/string`），见 [finish.md](finish.md)。
以下为剩余项。

- [ ] **CLI-C 文件与函数超规范**（2026-10-27 用户决定：**暂不拆文件**，后续再做）：
  `help.yh` 1,685 行、`schema.yh` 1,067 行
  （规范 500–1000）；>100 行的函数 4 个（`build_help_text`、`parse_layer`、
  `add_argument_internal`、`build_usage_line`）。切分点已在分节注释里：`help.yh`
  的拼接/转义/颜色/模板、`schema.yh` 的 `copy_*`/`check_freeze`；`MAX_HELP` 常量
  应随其余容量常量回到 `cli.yh`。
- [ ] **CLI-G 帮助宽度自动（依赖编译器先行）**：缺省固定 80（argparse 取终端宽度
  −2）。2026-10-27 实测确认 libs 层做不了：Darwin 的 `ioctl` 是 C 变参入口，而
  `@[extern]` 只支持定参，实参被放进寄存器导致 EFAULT（证据见
  [finish.md](finish.md) 同日条目与 `libs/sys/30_file.darwin.yh` 的边界说明）。
  2026-10-27 用户决定：**暂不动编译器，只保留本条记录**。
  落地路径：1) 在 `compiler/backend/llvm_runtime.yh` 追加弱符号
  `yh_terminal_columns()`（内部按正确变参 ABI 调 `ioctl(TIOCGWINSZ)`，两平台各自
  请求号）；2) `libs/os` 加薄封装 `terminal_columns() int`；3) `HelpFormat.width = 0`
  改「自动 = 列数 − 2，取不到回落 80」并补 pty 下的可复现门禁。

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
  `make test` + `make selfhost-native` 全绿后滚种子。
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
- [ ] **J6 产物体积：fmt 闭包不再放大成品**（2026-10-27 立项）：把「输出全部走
  fmt」后的体积回落到 printf 基线上。实测（macOS/arm64，hello 级程序，O0）：
  printf 单文件 50,256 B / `__text` 1,872；fmt 项目 155,872 B / 85,032；
  `-dead_strip` 后 89,632 B（−42.5%）；O2+`-dead_strip` 后 54,616 B（+8.7%）。
  主因不是 fmt 代码规模，而是「模块整对象链接 + 无死代码回收 + O0」。
  L1（Darwin `-dead_strip`）、L3（O2 缺省开优化）、L4（release `-x` 剥离）已落地：
  fmt hello 由 155,888 B 降到 53,424 B，与 printf hello 的比值 **1.063**。
  - [ ] **L2 后续（Linux 端到端）**：在 Linux CI 上量 ELF 的 `--gc-sections`
    实际回收率，并按需调整；本地容器运行时不可用（`container run` 启动即报错）。

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

- **NP 定位（原 ❓1，已决定并已收口）**：**只保留 NP3**（受检契约与 lowering
  解耦），NP0/NP1/NP2/NP4/NP5 关闭——NP0 口径并入现有 `just test` + O0/O2 +
  自举门；NP1/NP2 的对象代码（`ir_simplify`、`ssa_inline`）已删除；NP4 由
  ADR-0014 取代；NP5 交 LLVM 默认管线。ADR-0011 已标注部分被取代，
  [方案](02-plan/yh-Nanopass风格优化架构实施方案.md) 与
  [设计](03-design/yh-Nanopass风格优化架构.md) 已改状态。NP3 已于 2026-10-28
  关闭（覆盖矩阵零被拒，证据见 finish.md 与
  [能力矩阵](03-design/yh-受检到LLVM能力矩阵-2026-10-28.md)），本文件不再列其子项。
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
