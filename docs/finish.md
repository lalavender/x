# finish

滚动日志：只保留最近三天（当前为 2026-10-26 ～ 2026-10-28）的交付记录，靠前条目为最新状态。
更早的 475 条（2026-09-27 ～ 2026-10-25）已归档在
[finish 历史归档](01-finished/finish-历史归档-2026-09-27至2026-10-21.md)（归档文件按批追加，标题保留首批日期区间）。
超出窗口的条目迁入同一个归档文件，新增条目写在最前。

2026-10-28 起同时收录主工作区性能 WIP 分支（`tmp/main-wip-20261028`）的条目；
2026-10-25 及更早的条目仍只在归档文件里。

## 2026-10-28 合并性能 WIP（PF2/PL1/RB5/YH_WORKERS）到 B1/B2 树

把主工作区的临时分支 `tmp/main-wip-20261028`（性能基线 PF1b–PF3、PL1 缓存优化、
RB5 Mach-O 链接暂存、`YH_WORKERS`、`stats_print.yh`）合到 B1/B2 之后的 `llvm` 树。
两个方向都改过同一批文件，逐项对齐如下（**以 B1/B2 的分层为准，把性能改动搬进新结构**）：

- **时钟统一到 `gen.clock_ns`**：性能分支把 `cmd_clock_ns` 从 build 移到 `gen`
  （`lower`/`ir` 也要计时，它们只能依赖 `gen`），B1/B2 侧则把它移到了 `link`。
  合并保留 `compiler/gen/clock.*.yh` 作为唯一实现，删除 `compiler/link/clock.*.yh`，
  `link`/`build`/`testkit` 的调用改 `gen.clock_ns()`。
- **PF2 四段归因 → `BuildCtx`**：`mb_stats_{front,lower,irbuild,bridge}_ns` 是构建会话量，
  改为 `bc().front_ns/lower_ns/irbuild_ns/bridge_ns`（原为模块级 `let`）。
- **PL1 lowering 细分 → `gen.CompileStats`**：8 个 `c_stats_lower_*_ns` 与其它统计同源，
  落成 `gen.stats().lower_*_ns`（写入点在 `llvm_pipeline`，读取点在 `stats_print`）。
- **`stats_print.yh` 适配新 API**：`gs.c_stats_*` → `gen.stats().*`、`gs.task.c_stats_*` →
  `gen.task().c_stats_*`、`mb_stats_*` → `bc()`/`link.object_ns()`/`link.link_ns()`、
  `mb_sched_*` → `bc().sched_*`；同时删掉 `module_build.yh` 里重复的 `mb_print_stats`
  （B2-4 拆分时留在那边的那份）。
- **RB5 Mach-O 链接暂存搬进 `LinkPlan`**：新增 `link_dir[1000]`/`macho_stage`，暂存位置在
  `mb_link_args` 里决定（Mach-O 用 `.yh-tmp.<pid>/<basename>` 让 codesign identifier
  只取决于产物名），`link_tmp` 放大到 1000；丢弃统一由 `mb_link_release` 调
  `mb_macho_tmp_discard`（B2-3 的「单一释放口」正好承接这件事）。
- **`YH_WORKERS` → `BuildCtx`**：`bc().sched_limit/sched_limit_ready`；读取走
  `proj.env_fetch` 而不是 libc `getenv`（`getenv` 的 extern 声明随 `link_inputs` 变成了
  `link` 私有，`build` 不应再依赖它）。
- **预算按合并后实测重置**：`max_build_lines` 6,415、`max_link_lines` 3,711
  （性能打点 + `stats_print` 抽出 + RB5 暂存），其余不变。
- **验证**：`just build` 通过；`just test` 0 失败；`just selfhost-native` 全绿——
  候选两代固定点 **48 个产物逐字节一致**、cc4 自解析 **128 个源文件**、项目验收
  **122/122**；`arch-check` 通过（16 模块 / 128 文件 / 55,148 行、`gen.G()` 0、
  `let` 172）。RB5 的价值也在这次自举里体现：同一源码两次构建的 `yh` 二进制一致。

## 2026-10-28 性能：PL1d2b 探路并证伪（保持代码精简）

- **问题**：`ir_verify` 占 lowering 17%、2.97 ms/函数。静态看有两处逐指令/逐 use 的
  线性扫描（`ir_find_value_type`、`ir_find_value_position`），理论上让校验退化成 O(n²)。
- **做法**：实现「值→类型表」+「值位置表」并把 verifier 内部（`ir_verify` 的
  `value_types`、`ir_use_dominates` 的 `pos_block/pos_inst`）改为查表；
  用 `--stats` 的 `time_lower_verify_ns` 前后对比（同一过程、各 2 轮）。
- **结果：无可测收益** —— verify 占 lowering **17.2% → 17.0%**（绝对值下降来自机器变安静）。
  真实函数只有 100–500 条指令，扫描量 <2%，verify 的时间在真正的逐指令类型/操作数校验
  与支配性定点计算上。**按「不做无收益的投机优化」回退**，`ssa.yh`/`ssa_call.yh`
  恢复原状（`git diff` 为空）。
- **保留**：同日的 PL1d2 首片（去掉每模块第二次全量 verify、新增 `ir_module_sealed`）
  仍是净收益（A/B 冷编 −10.6%、单函数 −13.3%）。
- **后续（PL1d2b 只剩两条路）**：① 换支配性算法（Cooper-Harvey-Kennedy 或 bitset 定点）；
  ② 论证「发布构建关闭模块 verify」的替代门（它是 lowering 之后唯一语义兜底）。
- **门禁**：`just test` 0 失败、`just selfhost-native` 全绿（固定点一致、自解析 123 文件、
  project cases 122/122）、`just arch-check` 通过、`llvm-function-cache.py` 六场景全绿。

## 2026-10-28 构建缓存目录可指定（YH_BUILD_CACHE）

- **编译器（合入 llvm 的 B1/B2 结构后）**：`compiler/proj/proj_40_art.yh` 新增
  `cache_root()` 并改写 `build_dir()`——`YH_BUILD_CACHE` 非空时整套缓存树
  （`targets/...`、`check/` 与 asm/obj/iface/manifest/ir/llvm 子目录）落在该目录，
  空/未设置时仍是项目内 `.build`；测试模式仍固定 `tmp/yh-test/check`。
  `compiler/build/module_build.yh` 新增 `mb_ensure_binary_dir()`，独立确保项目
  `.build` 存在，默认可执行文件位置不随缓存迁移而变。
- **合入 llvm 分支（同日）**：先提交 llvm 工作区已有的 B2-3（`mb_link` →
  `LinkPlan` + 六阶段、失败路径统一释放，`link` 3,657 行），再把 llvm-2 的 7 个
  提交合入。6 个冲突按「保留 B1/B2 结构、重放 CLI-R」解决：`gen.G()` 改
  `gen.task()`/`gen.stats()`/`proj.cfg()`/`proj.ctx()`，`--link`/`--resolve`/
  `-o`/模块/`--timeout` 等从 argv 扫描改为 `CliRequest` 字段，缓存根落在
  `proj` 的 art 层；预算按实测更新（`max_link_lines` 3,657、`max_proj_lines`
  1,353）。
- **justfile**：`BUILD_CACHE`（环境变量 `YH_BUILD_CACHE`）贯通 `build`/`dev`/
  `clean` 与 `_ensure_built` 的子 `just`；冷编时连同缓存根一起清。门禁脚本按
  项目内 `.build` 断言，`unexport YH_BUILD_CACHE` 让 `test`/`selfhost-native`
  始终在缺省布局下跑，不受用户缓存位置影响。
- **测试**：新增 `tests/build-cache/check.py`（接入 `just test`）：设置
  `YH_BUILD_CACHE` 后对象落在缓存根、项目内无 `.build/targets`，二次构建增量
  命中；不设置时回到缺省 `.build/targets`。
- **验证**：`just test` 全绿（运行语料 360/361、新增 build-cache 4/4、arch-check
  通过）；`just selfhost-native` 全绿（模块固定点 42 产物一致、cc4 自解析 120
  文件、CLI 冒烟含 `--help`、运行语料 360/361、project cases 122/122）。滚种子
  `bin/yh-darwin-arm64`（SHA-256 `1591d13b16140e7ecaa7ad30034ccdf1d05003cc358e843f5462c3b9a8b643fc`）
  后复验：新种子下 `YH_BUILD_CACHE=/tmp/yhbc-real just build` 把 21 个对象写进
  指定目录、`compiler/.build` 不出现；`just dev` 1.4 s 全部 `[缓存]` 命中；
  冷编回缺省布局后再跑 `just selfhost-native` 全绿。带
  `YH_BUILD_CACHE=/tmp/yhbc-gate just test` 也全绿：门禁自身的项目构建仍落在
  各自的 `.build`，没有往该目录写入（只有顶层 `_ensure_built` 的构建会用它）。

**合入后的 llvm 分支复验**（合并提交）：`just test` 全绿（语料 360/361、
build-cache 4/4、arch-check 通过：16 模块 54,456 行、`gen.G()` 0、main 318 行）；
`just selfhost-native` 全绿（候选固定点 48 个产物逐字节一致、cc4 自解析 127 个
源文件、CLI 冒烟含 `--help`、运行语料 360/361、LA3 函数级缓存矩阵、project
cases 122/122）。

## 2026-10-27/28 性能收口：PL1f3 回退、PL1d2 首片、PC2c 改判

- **PL1f3 回退（有结论）**：机器安静后 5 对 A/B 显示 `cache 合并` 785.3 vs 777.3 ms、
  单函数墙钟反而 +5% —— 增建路径几乎没有命中机会，**无收益**，按规矩回退
  `ir_module_append_symbol`/`append_type`，merge 恢复走带查重的 `add_*`。
- **PL1d2 首片（已完成）**：一次性实验（临时允许 `ir→gen` 计时，量完回退）测到
  `ir_module_verify_function` 累计 **5.33 s**，而 lowering 侧只记 **2.72 s** —— 每模块
  被完整 verify 两次；定位到后端 `llvm_emit_module` 的防御性重复。改为廉价谓词
  `ir_module_sealed`（只查非空+版本），语义校验仍由生产者负责。A/B：冷编 **−10.6%**、
  单函数改动 **−13.3%**、worker 累计 **−16.5%**。函数体 `ir_verify` 占
  verify_function 的 83%（2.97 ms/函数），记 PL1d2b。
- **PC2c 改判**：纯计数探针（不涉及时钟）显示每条记录 payload 25.1 KB 中名字字节只占
  **0.7%**，真正占体积的是**每条 75 个类型条目**（capture 吞吐 1.91 MB/s）。字符串池
  改造收益可忽略；改为立 **PC2d 按模块共享类型表**（格式 v3 级，目标 25 KB→~5 KB/
  条，capture 13.4→5–6 ms/条）。
- **门禁**：`just test` 0 失败、`just selfhost-native` 全绿、`just arch-check` 通过、
  `llvm-function-cache.py` O0/O2 六场景全绿（用 F1 的 workspace 隔离 `FAST_DIR`）。

## 2026-10-27 性能 PL1d/e/f + PL3：缓存序列化提速与精确内存

- **PL1e（capture 提速，已完成）**：`ir_module_serialize_alloc` 一次 prepare
  （verify+plan）后直接分配写出，替掉「serialized_size + serialize」的**两次**
  verify+plan；capture 再走 `ir_module_serialize_alloc_trusted`（mini 模块是本进程
  忠实重编号，记录只在整模块 verify+emit 成功后才 `firc_commit` 落盘）。capture
  从 **19.3 → 13.7 ms/函数**（同过程单机），成对 A/B capture 累计 **−13.2%**；
  编码字节不变。
- **PL1d（verify 去 O(n²)，已完成两处）**：符号名唯一性改开放寻址哈希（碰撞仍比
  字符串）、「每个定义恰一实体」改计数数组（越界显式拒绝）。verify 2.88 → **2.68 s
  （−7%）**；小模块是白赚，大模块正是 PL2「每函数 verify 成本涨 3.9×」的元凶。
  逐函数指令校验（≈1.8 ms/函数）未优化，已立 PL1d2。
- **PL1f（命中跳过语义 verify，部分完成）**：记录头 32→40 字节加 payload FNV-1a、
  格式版本 1→2；校验和通过后走 `ir_module_deserialize_trusted`（仍解析 + 规模 +
  规范编码校验；合并后整模块仍完整 verify）。单函数改动场景 `cache 合并` 段
  **−8.0%**（A/B）。merge 剩余成本在类型/符号线性查找，已立 PL1f2。
- **PL3（精确内存口径，已完成）**：`perf-baseline.py --mem {footprint,rss}`——Darwin
  用 `proc_pid_rusage` 的 `ri_phys_footprint`（不重复计入共享干净页），Linux 用
  `VmHWM` 高水位；`--rss` 保留旧名。冷编进程树 **418.8 MB**、热编 **230.1 MB**；
  同一进程 footprint 12.5 MB vs RSS 24.4 MB。cgroup `memory.peak` 未接（PL3b）。
- **测量环境**：本轮后半程另一会话在 `llvm-3` worktree 自举（3×`yh` 各 ~100% CPU），
  load1 7–38；结论只采信**成对 A/B**与**load 不敏感**的内存数据，详见报告。
- **PL1f2（合并查找索引）**：merge 内为每条记录建一次目标模块索引（名字→符号、
  结构键→类型；键覆盖 `ir_fc_type_equiv` 的全部字段，哈希只缩候选、命中仍用原比较
  函数；依赖未映射时退化线性；模块 ≤64 规模时关闭）。单函数改动的 `cache 合并` 段
  **940.1 vs 1029.3 ms（−8.7%）**（3 对 A/B）。剩余：`ir_module_add_symbol`/`add_type`
  的线性查重（PL1f3）。
- **PL1f3（增建绕过线性查重）**：新增 `ir_module_append_symbol` / `ir_module_append_type`
  （调用方保证不存在同名/等价项），merge 在索引确认未命中后改走它们，每次 add 从
  O(S)/O(T) 降到 O(1)。**收益未验证**（复测 load≈16，A/B 抖动 13–26%），若安静环境
  确认无收益即回退（调用点仅 merge 两处）。
- **F1（FAST_DIR 隔离）**：`justfile` 默认快速目录改为
  `$TMPDIR/yh-fast-<workspace 哈希>[-run_id]`，修掉同机多 worktree 互相覆盖 `yh_run`
  导致的探针假失败；`FAST_DIR` 仍可显式覆盖。
- **门禁假失败（已由 F1 修复，值得记住）**：`FAST_DIR` 默认 `$TMPDIR/yh-fast` 曾是**跨 worktree 共享**的，
  同机另一个会话的 `just test` 会把 `yh_run` 换掉，探针于是报「stats 缺少阶段归因字段」。
  用私有 `FAST_DIR` 重跑：`just test` 122 passed/0 failed、`just selfhost-native` 全绿
  （固定点一致、自解析 123 文件、project cases 122/122）。已记 todo F1：默认路径应带
  workspace 标识。
- **验证**：`llvm-function-cache.py` 六场景 O0/O2 全绿（含损坏记录仍判 miss）；
  `just`、`just arch-check` 通过。

## 2026-10-27 性能 PL1c：capture 成本定位到序列化（2.05 MB/s）

- **结论**：[capture 序列化归因](01-finished/yh-capture序列化归因PL1c-2026-10-27.md)。
  写缓存构建的 capture 共 28.42 s / 1476 函数 = **19.3 ms/函数**，三段为
  闭包标记 1.9% / 迷你模块构造 30.4% / **序列化写缓冲 65.5%**；写出 38.08 MB ⇒
  **2.05 MB/s**，指向 `ir_module_serialize` 内部的线性查表/增长拷贝，而不是闭包扫描。
  合成语料（仅 int）0.83–1.91 ms/函数，真实语料贵 10 倍——成本跟「每条记录要编码的
  闭包体积」走。
- **方法**：`ir` 不允许依赖 `gen`（架构门），所以三段计时只在**一次性实验**里临时加
  `timing` 出参 + `gen.clock_ns()`；量完立即回退，`just`、`just arch-check` 重新通过。
  主线工具仍只输出 capture 总量（`--stats` 的 4+8 段字段不变）。
- **优化改写**：原计划让 PC2c（共享字符串池）扛 capture，现在改为
  **PL1e `ir_module_serialize` 提速**（最高优先，2.05 MB/s → ≥100 MB/s 量级）+
  PL1f 缓存合并（增量 4.9 ms/条）；PC2c 降级成 PL1e 的实现手段。已写入 todo。
- **顺带**：`perf-scaling.py` 增加 `--write-cache`（删对象不删 `link.manifest`），
  可复现「写缓存路径」的 capture 与每函数成本；`gen/clock.*.yh` 成为 build/lower
  共用的单调时钟（lower 不再自留一份）。

## 2026-10-27 性能 PL1：lowering 拆到函数级（含 PL2 超线性归因）

- **交付**：[lowering 内部归因](01-finished/yh-lowering内部归因PL1-2026-10-27.md)。
  `--stats` 在既有四段后再追加 8 段：`time_lower_{prep,decl,build,verify}_ns` 与
  build 内的 `{lookup,cache,fn,capture}_ns`；`perf-baseline.py` 出「lowering 细分」表，
  `perf-scaling.py` 增加「其中 verify / 其中真 lowering」两列；门禁
  （`tests/selfhost/llvm-function-cache.py`）断言 8 字段存在且子区间之和不超过父区间。
- **结论**（`tmp/perf/20261027-000451`，20 轮，load1 中位 5.85）：冷编 lowering
  16420.9 ms = 真 lowering **12270.2（74.7%）** + verify **3089.4（18.8%）** +
  缓存查表 650.4（4.0%）+ prep 196.1 + decl 181.2，符号查找只有 21.7 ms（0.13%）。
  全量重编（写缓存）的 lowering 里 **capture 23591.2 ms**，占该场景 worker 累计
  46671.4 ms 的 **50.5%**；单函数改动的 lowering 1148.7 ms 里 **缓存合并 998.0 ms
  （86.9%）**、真 lowering 只有 0.5 ms（204 个缓存函数 ≈ 4.9 ms/个）。
- **PL2 答案**：单模块函数数超线性不是符号查找，而是 verify 的每函数成本
  0.055→0.216 ms（3.9×，64→512 函数）叠加真 lowering 2.0×，合计每函数 2.9×。
- **新优化顺序**（写入 todo）：capture 序列化 → verify 成本（需先确认关闭后仍有门）
  → 缓存合并 → 真 lowering 内部再拆。
- **架构预算**：8 个计时值放 `GenState`（`c_stats_lower_*_ns`）而非模块级 `let`
  （`max_globals` 保持 193）；`mb_print_stats` 整体抽到新文件 `build/stats_print.yh`，
  `module_build.yh` 2296 → 2181 行。`max_build_lines` 按「只减不增，上调须说明」的规矩
  从 10982 上调到 11034，理由写进 `tools/arch-check.py` 的 BUDGETS 注释。
- **门禁**：`just test`、`just selfhost-native` 全绿；`just arch-check` 通过。

滚动日志：只保留最近三天（当前为 2026-10-24 ～ 2026-10-27）的交付记录，靠前条目为最新状态。
更早的 384 条（2026-09-27 ～ 2026-10-21）已归档在
[finish 历史归档](01-finished/finish-历史归档-2026-09-27至2026-10-21.md)。
超出窗口的条目迁入同一个归档文件，新增条目写在最前。

## 2026-10-27/28 0.0.11-rc.1 发布准备 + 三处 CI 闭包缓存修复

- **滚种子**：`just seed` 覆盖 `bin/yh-darwin-arm64`（未入库），当前种子即 0.0.11
  编译器（sha256 `3d1f1c9e…`），后续本地构建直接跑 UF1 检查。
- **发版分支**：`0.0.11-rc` 从 `0.0.10-release` 切出（0.0.10 已正式发布，补上
  落在 release 分支的发布说明），cherry-pick UF1 提交；`compiler/project.toml` 版本
  0.0.10 → **0.0.11**（rc 期即写目标正式号）；新增
  `docs/01-finished/release-0.0.11-rc.1.md`（含「不兼容变更：私有且无引用的函数
  会编译失败」与升级指引）；打 annotated tag `0.0.11-rc.1` 推 Gitea。
- **CI 首次推送（run 156/157）darwin 任务 30 s 内失败，三个独立根因**：
  1. `ci.yml`/`release.yml` 用 `${YH_LLVM_CACHE:-$HOME/Documents/x/tmp/llvm-migration}`
     拼缓存根，而 runner（host 模式）会把 HOME 覆写成 `.cache/act/<id>/tmp/<uuid>`，
     `-d` 永远为假 → 走 `just llvm-host` 现场重建；重建时没有 `SDKROOT`，宿主默认
     SDK 已是 27.x（`libSystem.tbd` 含 `arm64e.x1`），内嵌 lld 21 直接拒收。
     改为顶层 `env: YH_LLVM_CACHE` 钉死宿主缓存绝对路径 +
     `cache="$(python3 tools/llvm_cache.py)"`（显式 env → 本仓库 tmp → 主 worktree）。
  2. `llvm-darwin-host.py prepare` 无条件 `build_host()`，与 AGENTS「幂等
     `just llvm-host`」不符 → 现在先 `check(full=True)`，一致就打印
     `"reused": true` 复用。
  3. `build_host`/`write_selfhost_flags`/`write_cxx_stub`/`check` 用
     `path.relative_to(ROOT)` 记录路径，缓存根在仓库外（CI executor、直接指向主
     worktree 缓存）时抛 `ValueError`，把「build-sdk 失败」变成 traceback
     （run 518）。新增 `record_path()`（仓库内相对、仓库外绝对；消费者
     `ROOT / record[...]` 两种形态都成立）与 `display_path()`。
- **并发会话踩坑**：本机另一个会话（`~/Documents/x`、`cichlid` worktree）在同一
  `TMPDIR/yh-fast` 与同一 LLVM 闭包缓存上跑门禁，会覆盖暂存编译器（`yh-fast/yh`）
  和闭包记录——我这边一度出现「同一提交 build-check 124/124」与「123/124 + 假红」
  交替、以及 `host.json` 摘要与磁盘不一致。定位后改用私有
  `FAST_DIR=$PWD/tmp/yh-fast` 跑门禁，并重新基线闭包记录（`bridge_sha256` 等按磁盘
  现值重算）；CI 侧则用固定 `YH_LLVM_CACHE` 避开 HOME 覆写。
- **环境**：`just llvm-host` 幂等化后本地/CI 都不再重建闭包；闭包记录里的
  `host_builder_sha256` 每次改 `tools/llvm-darwin-host.py` 需重新基线（本轮改了三次，
  最终记录与磁盘一致，`check(full=True)` 为空）。
- **本 workspace 私有闭包**：并发会话反复重建共享闭包的 `libyh-llvm-bridge.a`
  并改写 `host.json`，身份记录几分钟就被打花（`check` 报「构建器已变化」，CI 于是
  试图重建 SDK）。因此建了同源私有闭包
  `~/Documents/x/tmp/llvm-migration-llvm-3`（`darwin-sdk` 软链共享的只读 SDK，
  host 目录为 232 KB 的实体副本，记录重新基线为 `tmp/llvm-migration/...` 别名路径），
  两个 workflow 的缓存步骤改为按候选顺序选目录：
  显式 `YH_LLVM_CACHE` → 私有闭包 → 共享闭包，命中即 `ln -sfn` 到 `tmp/llvm-migration`。
- **环境**：`just llvm-host` 幂等化后本地/CI 都不再重建闭包；闭包记录里的
  `host_builder_sha256` 每次改 `tools/llvm-darwin-host.py` 需重新基线（本轮改了四次，
  最终记录与磁盘一致，`check(full=True)` 为空、`tools/link-closure.py check
  --host darwin-aarch64` PASS）；`record_path()` 必须把路径写成
  `tmp/llvm-migration/...` 别名，否则 `[link-darwin-arm64]` 的 bridge 会被
  link-closure 误分类到 support 组。
- **待办**：tag 推送后由 `release.yml` 三端构建 + `publish-release.py` 发布
  prerelease；结果以 Release 与 CI 记录为准。发布后用 rc 二进制做
  `rm -rf bin && just fetch-seed → just → just test → just selfhost-native` 验收，
  再合并到 `0.0.11-release` 打正式 tag。

## 2026-10-27 未使用函数直接报错（UF1）：检查进 pass1，清掉 24 个死函数

- **需求**（用户）：分析当前编译器后，让「没有被使用的函数」直接报错，并顺手把这批
  死代码清掉。
- **规则**：本模块声明、既没 `pub` 也没 `extern`/C ABI 的函数定义，如果整个模块的
  源码里除了它自己的声明名之外没有任何同名标识符，`build`/`run`/`test` 与单文件
  编译都报 `函数未使用（本模块没有任何引用；请删除或改为 pub）`。`pub`（含入口
  `main` 与 `test` 生成符号）、`extern`（无正文）、`@[extern]` 带正文的 C ABI 回调
  目标（按 C 名字导出，可能只被同项目 C 源调用）一律跳过。
- **实现**：新增 `compiler/build/unused_function.yh`（222 行），在 pass1 之后、pass2
  之前对模块全部文件做一遍 token 扫描：候选来自顶层声明索引（`PDecl.keyword + 1`
  是名字 token）与符号表（`SYM_FN` + `F_GLOBAL` − `F_PUB`/`F_EXTERN`/`F_CABI`），
  命中用首字节过滤 + 名字字节比较，跳过声明自身的名字 token。调用点两处：
  `module_worker.yh`（模块路径，传 `p_mods[m].files` 与 `sym_base`）与
  `llvm_emit.yh`（单文件路径把该文件当整个模块）。
- **为什么按 token 而不是解析期引用标记**：三条路径都会让「引用标记」在增量构建里
  漏记——函数级 check 切片命中时正文不重新解析（`parse_decl` 直接 `continue`）；
  普通函数体里的 `$f(...)` 编译期调用折成常量、不留引用节点；生产构建按设计不解析
  `test` 正文（只在 test 里用到的私有辅助会被误判）。token 扫描对这三条都成立，
  方向是保守的：只会漏报（同名局部变量遮蔽、递归自引用算作已使用），不会把合法
  程序判死。代价与后续精确化已立项在 `docs/todo.md`（UF1 精确化）。
- **清掉的死代码（24 个，全部是 LL12 退役旧发射器/历史迭代的遗留）**：
  `gen`：`abi_c_signature`、`ty_name_text`、`tg_sym_prefix`、`tg_is_2byte`、
  `tg_is_8byte`、`tg_align_scalar`；`backend`：`llvm_abi_emit_c_aggregate_call`（旧
  C 聚合 ABI 发射，76 行）；`comptime`：`ct_invoke`；`ast`：
  `ast_comptime_for_find_binding`、`ast_comptime_for_info`；`parse`：
  `ct_enum_pending_reset`、`ct_enum_pending_count`；`lower`：`checked_lower_error`、
  `checked_lower_expr`（薄包装，正文版本才是调用面）；`build`：`li_kind`、
  `mb_sub_dir`、`pj_source_cat`；`libs`：`cli.text_visible_width`、
  `cli.action_takes_values`、`json.utf8_is_scalar`、`toml.p_at_end`、
  `toml.p_current`、`libc.text_len`、`libc.is_digit`。
- **语料**：新增 `tests/yh-run/fail/168-unused-function.yh`（`fail-contains:
  函数未使用`）与 `tests/yh-run/pass/10-unused-function-scope.yh`（`pub` 未用、
  函数值引用、只在 `test` 正文里用到的私有辅助都不算未使用）；新增模块级 fixture
  `tests/modules/projects/unusedfn`（依赖项目里的 `ufmath` 模块，`helper` 只在同包
  另一个文件里被调用 → 通过；`dead` 项目的孤儿私有函数 → 报错），并在
  `build-check.py` 加 `uf1-module-scope-use`(42) 与 `uf1-unused-function`。
  依赖模块特意叫 `ufmath`：`json`/`math` 这类名字已被标准库 `libs/` 占用，
  `import math` 会解析到标准库而不是 fixture 的依赖项目（旧的 `basic`/`u5-rebind`
  探针正是因为 `libs/json` 上线而偶尔解析到标准库，与本轮无关）。
- **fixture 因新规则做的调整**（都不是功能变更）：`ytestsem` 库项目里那个不叫入口的
  `main` 改 `pub`；`llvmarchitecture/cases/library.yh` 的 `product`/`layout_bytes`
  改 `pub`；`irfront`、`tokenreplay` 里只为 IR/形状检查存在的私有函数由 `main`
  以零净贡献引用；`scheduler`/`scheduler-diamond` 生成的 600 个 `private_NNNN` 改
  `pub`，且「私有正文失败阻止链接」那条探针改用 `pub broken_entry` 引用
  `broken_private`，避免被 UF1 先拦下来、让断言仍然验证正文检查失败；
  `tests/yh-run/pass/06..08`、`run/181` 则让 `main` 真正引用原本悬空的声明。
- **预算**：`tools/arch-check.py` 的 `max_build_lines` 10,807 → 11,015（UF1 新增
  222 行、删掉本模块 3 个死函数共 25 行，故本模块净 +197；本文件即理由）；`compiler/README.md` 的规模数字与 `docs/todo.md` 的基线表同步到
  2026-10-27 实测（13 模块 / 120 文件 / 53,545 行）。
- **验证（本机 Darwin/arm64）**：`just`（种子冷编）→ `./yh` 自编 `compiler/`（新检查
  生效后先报 17 个、逐个清到 0）；`just test` 全绿（语法 49/49、运行 362/363 含 1
  SKIP、pass 9/9）；`just libs-test` 全绿（122 PASS）；`just selfhost-native` 全绿：
  cc3/cc4 固定点 39 产物一致、cc4 自解析 120 文件、运行语料 362/363、模块语料
  19/19、`build-check` **124/124**（含新增 `uf1-module-scope-use` 与
  `uf1-unused-function`）、LA3 函数级 IR 缓存矩阵 O0/O2 全通过、LA0 架构基线通过；
  `python3 tools/arch-check.py` 与 `tests/tools/arch-check/check.py`（自测 2/2）通过。
- **实现细节：检查不能改名字池**。首版用 `tml_intern_str` + `sym_lookup_off` 把
  声明名映射到符号，名字池因此变长，连带改变了后续阶段的池布局：`LA3` 函数级
  缓存矩阵的「插入新函数」从预期的 check 4 命中 1 未命中变成 0 命中 5 未命中。
  现在改为在 `[sym_base, c_sym_n)` 里按字节比较直接找符号（`uf_symbol_for_decl`），
  检查对 GenState 只读，缓存键恢复稳定。**教训：pass1/pass2 之间的任何检查都不要
  往名字池/类型表里追加东西。**
- **环境提示**：直接执行 `python3 tests/modules/build-check.py` 而不是走 `just`
  会缺 `SDKROOT`（justfile 从固定 SDK 记录导出），于是 cinterop 的 `-lm`、
  `os6-default-stdlib` 的 `_nanosleep`/`_getpid`、`r2b-fork-worker-space-paths` 的
  `arm64e.x1` TAPI 都会链接失败；这 14 例不是回归。走 `just selfhost-native`
  才是门禁口径。`LA3` 的插入探针也改成自递归形态（`fn extra() int { return
  extra(); }`）：新函数没有外部调用方，不改签名表，名字扫描又算已使用，正好保住
  矩阵原本的 4 命中 1 未命中口径。另外本轮共享 LLVM 闭包缓存
  （`~/Documents/x/tmp/llvm-migration/llvm-host-darwin-aarch64/host.json`）里的
  `host_builder_sha256` 是旧脚本身份（与当前 `tools/llvm-darwin-host.py`
  `ae9e23b5…` 不符），导致 `auto` 模式试图重建闭包并在 `relative_to` 上报错；
  按当前脚本摘要修正该字段（原件备份在 `tmp/host.json.bak`）后闭包被正常复用，
  未重建任何 LLVM 产物。
- **未做**：不加 `@[keep]`/`@[allow(unused)]` 一类逃生属性（`pub` 已足够，符合
  极简原则）；不检查 `const`/`let`/类型的未使用（本轮需求只到函数）。

## 2026-10-27 修 llvm-host 缓存路径 bug + justfile 暂存目录隔离 + 滚种子

- **`tools/llvm-darwin-host.py` / `tools/llvm-host.py`**：新增 `describe()`，把
  `Path.relative_to(ROOT)` 换成「仓库内显示相对路径、仓库外显示绝对路径」。
  闭包默认落在 `$YH_LLVM_CACHE`（`$HOME/Documents/x/tmp/llvm-migration`，仓库外），
  原实现会在 `just llvm-host` 失败时抛 `ValueError: ... is not in the subpath of ...`，
  把真正的原因（SDK/bridge 摘要不匹配）盖掉。身份记录里的
  `selfhost_flags_file`/`selfhost_runtime_file`/`cxx_tbd` 也一并改用 `describe()`：
  消费方按 `ROOT / value` 读取，绝对路径在 pathlib 下同样成立。
- **`justfile` 暂存目录按 worktree 隔离**：`FAST_DIR` 缺省从 `$TMPDIR/yh-fast` 改为
  `$TMPDIR/yh-fast-<仓库路径 sha256 前 8 位>`。同一台机器的多个 worktree 共享
  `$TMPDIR`，原先会互相覆盖 staged 编译器与 `darwin-sdk` 软链——实测 llvm-2 的
  `just test` 跑在 llvm-3 的二进制上（3 条 `pass/` 用例报「函数未使用」，
  `darwin-sdk` 软链指向 llvm-3），排除后全绿。CI 的 `GITHUB_RUN_ID` 后缀保留。
- **滚种子**：`just bootstrap`（复用本机固定闭包）冷编 → `just test`、`just
  selfhost-native` 全绿（固定点 42 产物、cc4 自解析、CLI 冒烟、运行语料 360/361、
  project cases 122/122）→ `just seed` 更新 `bin/yh-darwin-arm64`
  （SHA-256 `0ac4586a4a8aa9ab8eca0e3bb500ffa7593443a308890c9e177b3d4ceb2e41ba`）。
  随后用**新种子**重新冷编（`rm -rf compiler/.build && just`）并再跑
  `just selfhost-native` 全绿——新种子自带用 `libs/cli` 解析的命令行与
  `yh --help`/`yh <命令> --help`。

## 2026-10-27 CLI-R4：yh 帮助/诊断改由 libs/cli 生成

- **删除手写 `usage()`**：`yh`、`yh <命令>` 的帮助与解析失败的 usage 全部由
  `libs/cli` 的 `format_help`/`format_usage` 生成，`cmdline` 里 `print_bare_help`/
  `print_usage`/`print_control` 三个薄封装负责落 fd。
- **`-h/--help` 成为正式能力**：顶层帮助列全部子命令与单文件形态说明，子命令帮助
  由 `Command.config` 的 `help_format` 决定（中文段标题 `位置参数/选项/命令`，
  usage 前缀 `用法: `），help/version 控制结果写 stdout、退出 0。
- **libs/cli 两处小增强**：`HelpFormat.usage_prefix`（默认 `usage: `）与
  optional 位置参数只套一层方括号（`[module]` 而非 `[[module]]`）；cli 用例 52 → 54。
- **冒烟与金标**：`tests/selfhost/native-selfhost.py` 的 CLI 冒烟补 `--help`
  （退出 0 + 用法 + 命令名）；`tools/cli-golden.py` 的文本类用例改为宽松
  （10 条，均为「usage/help 文本按设计改变」），行为类仍严格 36/36。
- **文档**：`AGENTS.md` 使用段、`README`、`libs/cli/README.md`（配置项）、
  `docs/03-design/yh-cli标准库设计.md`（HelpFormat 配置面）。
- **验证**（种子 `bin/yh-darwin-arm64`）：`just test` 全绿；`just selfhost-native`
  全绿（固定点 42 产物、cc4 自解析、CLI 冒烟含 `--help`、运行语料 360/361）；
  `just libs-test` 全绿；`tools/cli-golden.py` 36/36（10 条宽松为文本变化）。

## 2026-10-27 CLI-R1：yh 命令行改用 libs/cli 解析（入库）

- **新模块 `compiler/cmdline/`**（`module cmdline`，568 行）：`CliRequest` + 两个 parser
  （project：`build/check/run/test/list/version`；file：`--syntax-check`/`--emit-asm`/`-o`），
  全局选项（`--target/-target`、`--backend`、`-O0/-O2`、`--emit-llvm`、`--stats`、
  `--legacy-system`）声明在公共 parent 再 `inherit`，保持「子命令前后都能写」。
- **`cmd` 回到薄壳**：`api_*` 接收请求结构；`mb_cmd_build/run/list`、
  `mb_run_test_command` 删除 argv 扫描、改接收已解析字段；`driver.yh` 只做
  「请求 → 全局状态 → 分派」，`usage()` 移入 cmdline。`main` 307 行（预算 381 内）。
- **依赖与门禁**：`compiler/project.toml` 增 `[dependencies] libs = {path = "../libs"}`，
  `cmdline` 用 `import libs.cli`（绑定名仍 `cli`）；arch-check 登记
  `cmdline -> libs`、`main -> cmdline`。`tools/selfhost_snapshot_gate.py` 增
  `follow_dependencies` 开关与 `dependency_artifacts()`（依赖模块产物「允许出现但
  不要求」），`native-selfhost.py` 只要求本地模块齐全。
- **等价性**：`tools/cli-golden.py` 36 条 argv **36/36 通过**（6 条宽松项为
  「新实现多打印一条诊断」）。
- **踩坑记录**：切换编译器后必须清 `compiler/.build`——混用不同版本的对象/接口会给出
  假诊断（把在用函数报成「函数未使用」、`-target linux` 的别名判定走错分支）。
- **验证**（种子 `bin/yh-darwin-arm64`，`YH_LLVM_HOST=0` + `tmp/llvm-migration` 软链）：
  `just test` 全绿；`just selfhost-native` 全绿（模块固定点 42 个产物一致、cc4 自解析
  120 文件、CLI 冒烟、运行语料 360/361）；`just libs-test` 全绿；
  `python3 tools/cli-golden.py` 36/36。

## 2026-10-27 CLI-R0：cli 段标题可配置 + yh CLI 等价性金标

- **libs/cli**：`HelpFormat` 增 `section_positional`/`section_options`/
  `section_commands`（空指针沿用英文默认），`help.yh` 的 `put_title` 改读字段；
  这样 yh 重写命令行时能保留中文帮助段标题。用例 51 → 52。
- **tools/cli-golden.py**（新）：同一批 argv 分别交给旧/新编译器，比较退出码 +
  归一化输出（路径占位、`time_*` 归零、`yh-stats` 值隐藏、`[编译]/[缓存]…`
  进度行按多重集合）；每个用例在独立 fixture 副本里冷跑。
  当前 36 条用例 **36/36 通过**，其中 6 条是「新实现多打印一条诊断」的宽松项。
- **规划**：新增 `docs/02-plan/yh-CLI用cli标准库重写实施方案-2026-10-27.md`
  （现状盘点 + 目标形态 + 六期切片 + 金标设计 + 风险）；`docs/todo.md` 增 CLI-R0…R5。
- **R1 原型（未入库）**：`cmdline` 模块 + cli 解析 + 分派改造在本机跑通
  （`cli-golden` 36/36、`just test` 全绿、arch-check 通过：main 307 行、新模块
  568 行并登记 `cmdline -> libs`），但 `just selfhost-native` 在「cc2 产物集合」
  处失败：编译器 import 标准库后，种子构建会额外发布 6 个 `yh_libs-*` 模块的
  `iface/.s.i` 与 `llvm/.ll`；同一seed 构建未改动 HEAD 时集合完全一致（0 多余/0 缺失），
  证明差异来自新增的标准库依赖。三条前置问题与收口方式记在方案 §12，
  原型补丁留在 `tmp/cli-migration/cli-r1-prototype.patch`。
- **验证**：`cd libs && yh test` = 131 passed（cli:: 52）；`just test` 全绿
  （含 arch-check 自测与真实树）。

## 2026-10-27 CLI-G 调查：帮助宽度自动被 C ABI 挡住（不改代码）

目标：让 `HelpFormat.width = 0` 表示「取终端宽度 − 2」（argparse 行为）。结论是
**当前编译器能力下无法在 libs 层安全实现**，因此只记录证据并立项，不发布半可用代码。

- **实测链路**：在 `libs/os` 加 `terminal_columns`（`@[extern] fn ioctl(fd int,
  request u64, argument *void) int` + `winsize`），pty（24×40）下运行 yh 产物：
  - `nm -u` 确认导入真实 `_ioctl`；反汇编确认 `w0=1`、`w1=0x40087468`、`x2=栈上缓冲`；
  - 结果仍为 `rc=-1, errno=14`（EFAULT），即内核收到的指针是垃圾；
  - 同一 pty、同一请求号下用 C 调用（`ioctl(1, TIOCGWINSZ, &w)`）得到 `rc=0, 24×40`。
- **根因**：Darwin/arm64 的 C 变参实参必须走栈，而 yh 的 `@[extern]` 只支持定参
  （`libs/sys/30_file.darwin.yh` 开头已记录同一约束，`open/openat/fcntl` 因此只走
  prelude 的变参登记）。`ioctl` 是变参入口，定参声明把第三个实参放进 x2，libSystem
  却从栈上取 → EFAULT。Linux 侧同类声明按 AAPCS64 会读到 x2，但 x86_64 SysV 又要求
  变参调用设置 `al`，同样不能靠 libs 层保证。
- **处理**：删除实验性的 `libs/os/15_terminal.{linux,darwin}.yh`，`cli` 的
  `HelpFormat.width` 语义与默认值（80、0=不折行）保持原样；差异文档维持「帮助宽度
  缺省固定 80」这一条，并补上根因。自动宽度的落地路径记入
  [todo](todo.md) 的 CLI-G（需先在编译器后端提供非变参 shim）。
- **验证**：回退后 `cd libs && yh test` = **130 passed / 0 failed**；
  `--filter cli::` = 51 passed；`run.py` 5/5；`diff.py` 0 未知差异。

## 2026-10-27 cli 标准库去重与常量（复核 CLI-D）

- **构造器合并**：`option()`/`positional()` 两份 31 行逐字段初始化合并为
  `new_argument(name, positional)` + 两个薄包装（后者只差 `alias`、`positional`
  与默认 arity），`cli.yh` 少 ~45 行重复。
- **诊断码常量化**：新增 `cli.CODE_USAGE`/`CODE_CONFIG`/`CODE_RESOURCE`
  （取值 `usage_error`/`config_error`/`resource_error`），替换各文件里 122 处字面量；
  顺带把 8 处写成 `"resource"` 的内存失败诊断统一为 `resource_error`
  （此前 `Diagnostic.code` 在同类失败上取值不一致）。
- **参数文件上限常量化**：`parse_config()` 里的 `16`/`1048576` 改为新增的
  `MAX_FILE_DEPTH`/`MAX_FILE_BYTES`（与 `MAX_FILE_TOKENS`/`MAX_FILE_LINE` 同族）。
- **测试助手去重**：`zz_tests_help.yh` 的 `hp_contains`/`hp_index_of` 改为委托
  `string.contains`/`string.find`（新增 `import string`），删掉手写双循环 ~45 行。
- **用例**：新增「错误：诊断码常量与类别一致」——usage 错误码等于 `CODE_USAGE`、
  配置错误码等于 `CODE_CONFIG`；cli 内嵌测试 50 → **51**。
- **文档**：`libs/cli/README.md`（诊断码常量、容量表补两个上限、公开 API）、
  `docs/03-design/yh-cli标准库设计.md`（§14.3 错误码常量）。
- **验证**（种子 `bin/yh-darwin-arm64`）：`cd libs && yh test` = **130 passed /
  0 failed**；`--filter cli::` = 51 passed；`libs/cli/test/run.py` 5/5；
  `diff.py` = 91/94 一致、3 条已知差异、0 未知差异。

## 2026-10-27 cli 帮助拼接的越界兜底与去重（复核 CLI-B）

- **短路契约**：`help.yh` 的 23 个拼接函数（`put_text`/`put_char`/`put_int`/
  `put_spaces`/`put_hex_byte`/`put_escaped`/`put_color`/`put_color_end`/
  `put_value_text`/`put_choices_metavar`/`put_metavar_at`/`put_value_pattern`/
  `put_template`/`put_template_wrapped`/`put_wrapped`/`put_single_synopsis`/
  `put_mutex_synopsis`/`put_slot_names`/`put_slot_pattern`/`put_row_names`/
  `append_help_row`/`put_title`/`put_break`）开头统一 `if (at < 0) { return -1 }`：
  一旦越界，后续追加全部变成空操作。
- **修掉 3 处潜在越界**（`at=-1` 当下标继续写）：`put_escaped` 内 `put_hex_byte`
  后直接 `continue`；`layer.yh` 的建议文本三段串联；`ctx_add_warning` 的弃用警告前缀。
  现在这三处即使漏判也只会整段失败，不会踩内存。
- **删除 76 处重复判空**：仅保留「返回值参与算术」（`append_help_row` 的名称宽度、
  `build_usage_line` 等）与「用 `at` 写 NUL」（`build_help_text`/`build_usage_text`/
  `build_version_text`/消息构造）的检查；`help.yh` 1,844 → **1,685 行**，
  `if (at < 0)` 由 144 处降到 91 处。
- **溢出行为**：新增用例「帮助：文本溢出返回 resource_error」——`description` 与
  子命令 `help` 超过 `MAX_HELP` 时 `format_help` 返回 `resource_error` 且 `text`
  为空指针（此前该路径只会打印越界写后的垃圾内容）。
- **验证**（种子 `bin/yh-darwin-arm64`）：`cd libs && yh test` = **129 passed /
  0 failed**；`--filter cli::` = 50 passed；`libs/cli/test/run.py` 5/5；
  `diff.py` = 91/94 一致、3 条已知差异、0 未知差异。

## 2026-10-27 cli 库对齐 argparse：批次 3（诊断与建议）

四项诊断缺口对齐（对照 Python 3.14 argparse 的 `error()` 文案）：

- **choices 不匹配列候选**：`parse.yh` 的 `convert_tokens` 增加 `state` 参数，
  改用新增 `choices_message` 构造「选项 --mode 的值不在候选集合中（可选：fast, slow）」。
- **未知子命令列候选**：`layer.yh` 的 `dispatch_command` 改用 `subcommand_message`
  （「未知子命令 ad（可选：add, list）」），替代固定文案。
- **`suggest_on_error` 扩展到 choices 与子命令**：新增 `suggest_choice`/`suggest_command`
  （复用 `edit_distance`，阈值 2、取最优 1 个），文案追加「是否想用 X？」；
  未知选项的建议逻辑不变。
- **多余位置 token 全量列出**：新增 `put_extra_args`/`extra_args_message`
  （「多余的位置参数：b c」），`tail_layer` 与 intermixed 收集路径共用；
  超出 `MAX_HELP` 缓冲时退化为不加列表的短消息。
- **用例**：`zz_tests_help.yh` 新增「choices、子命令与多余 token 的诊断候选」
  （含 `suggest_on_error` 开/关两组断言）；cli 内嵌测试 48 → **49**。
- **文档**：`libs/cli/README.md`（§13 `suggest_on_error`、§14 诊断文案）、
  `docs/03-design/yh-cli标准库设计.md`（§14 诊断实现状态）、
  `docs/03-design/yh-cli与argparse差异.md`（新增 3 条一致项，测试数 49）。
- **验证**（种子 `bin/yh-darwin-arm64`）：`cd libs && yh test` = **128 passed /
  0 failed**；`--filter cli::` = 49 passed；`libs/cli/test/run.py` 5/5；
  `diff.py` = 91/94 一致、3 条已知差异、0 未知差异。

## 2026-10-27 cli 库对齐 argparse：批次 2（帮助/usage 展示）

六项展示缺口全部接通，均与 Python 3.14 argparse 的 `format_usage`/`format_help` 逐字对照：

- **choices 占位名**：`row_metavar` 之外新增 `put_metavar_at`/`put_choices_metavar`，
  缺省渲染 `{fast,slow}`（usage 与帮助列一致），显式 `metavar`/`metavars` 优先；
  real 候选没有格式化器，退回类型名（`FLOAT`）。
- **逐项占位名 `metavars`**：只对 `exactly(n)` 有效，freeze 校验「个数 = n」且不能与
  `metavar` 同时设置；`--pair LEFT RIGHT` 逐项展开。
- **数量模型占位名**：新增 `put_value_pattern`，按 argparse 的 `_format_args` 语义写
  `single` 一个、`exactly(n)` n 个、`*` → `[X [X ...]]`、`+` → `X [X ...]`、
  `remainder` → `...`（旧实现的 `...` 追加逻辑并入该函数）。
- **子命令槽**：`Subparsers.metavar` 新增字段（`slot_metavar` 落库），usage 写成
  `{add,list} ...`（旧为 `[COMMAND]`/`COMMAND`，无省略号）；`title`/`description`
  终于生效：帮助段用自定义标题、说明行、`{add,list}` 占位行，命令行缩进 4 并按
  `help_column` 对齐；显式 `metavar` 覆盖命令名列表。
- **`boolean_optional` usage**：写成 `[--cache | --no-cache]`（旧只写 `[--cache]`）。
- **`HelpFormat.max_help_column` 接通**：`help_column(state, fallback)` 统一取
  「显式值 > 段落默认（位置 22、其余 26）」，位置/选项/用户组/命令段全部改用它。
- **用例**：`zz_tests_help.yh` 新增「choices 占位名与槽标题/说明/占位名」「max_help_column
  与 boolean_optional usage」两组，旧 metavar 用例补 usage 断言；新增 `hp_line_column`
  助手量说明列。cli 内嵌测试 46 → **48**。
- **文档**：`libs/cli/README.md`（§5 metavars/choices、§6 usage 形态、§7 槽
  title/description/metavar 与 usage、§13 max_help_column/boolean_optional）、
  `docs/03-design/yh-cli标准库设计.md`（§10.1 Subparsers、§14.1 实现状态）、
  `docs/03-design/yh-cli与argparse差异.md`（新增 7 条一致项，补充「帮助宽度缺省」
  「说明列缺省」「choices 说明附录」三条保留差异）。
- **验证**（种子 `bin/yh-darwin-arm64`）：`cd libs && yh test` = **127 passed /
  0 failed**；`--filter cli::` = 48 passed；`libs/cli/test/run.py` 5/5；
  `diff.py` = 91/94 一致、3 条已知差异、0 未知差异。
- **未做**：帮助宽度仍固定 80（不读终端宽度）；诊断候选列表与 `suggest_on_error`
  的 choices/子命令覆盖留在批 3（todo CLI-F）。

## 2026-10-27 cli 库对齐 argparse：批次 1（语义正确性）

六项与 Python 3.14 argparse 实测对照后补齐/修正的行为：

- **`set_default` 未声明 dest 现在进结果**（argparse `set_defaults` 语义）：
  `apply_defaults` 新增覆盖项逆回写（`parse.yh`），设计 §8.3/§7 早已承诺「可为尚无
  参数的键设置业务标签」，但旧实现只遍历已声明 `rows`，实测 `contains=0`。
  新值 `provided=false`，不覆盖 `initial`。
- **位置 `optional()` 未取到值时用默认值**（argparse `nargs='?'`）：旧实现写入
  `const_value` 并计 `provided=1`；现不写 const、不计出现，交给默认值层级。
  实测 `opt='DEFAULT'`（对齐），不再是 `CONST`。
- **位置段为子命令槽预留 token**：整段 token ≥「全部位置参数最低需求 + 1」时为槽
  保留 1 个（argparse `PARSER` 语义）；`files='*'` + 槽下 `tool add` 得
  `files=[] cmd=add`（旧行为是 `files=['add']` 且不选命令），最低需求占满时不预留
  （`files='+'` + 槽，`tool go` 仍得 `files=[go]`）。设计 §10.1 早就写「保留槽…最低
  数量」，实现现在与契约一致。
- **`store_const`/`append_const` 缺 `const` 报 config_error**（argparse 在
  `add_argument` 报 ValueError）；`boolean_optional` 等零参数 action 不受影响。
- **位置参数设 `required=true` 报 config_error**（argparse ValueError）；
  必需性仍由 arity 决定。
- **默认值/常量不参与 choices 校验**（argparse 语义，choices 只约束命令行显式值）：
  `declared_value_ok` 只保留 validator；显式值仍受 choices 约束（同一测试覆盖）。
- **用例**：`zz_tests_actions.yh`（位置 `optional` 默认值 + 未声明 dest + choices
  默认值）、`zz_tests_commands.yh`（槽 token 预留，含 `one_or_more` 不预留的反例）、
  `zz_tests_extensions.yh`（缺 const / 位置 `required` / 带 const 正常写入）。
  cli 内嵌测试 43 → **46**。
- **文档**：`libs/cli/README.md`（§3 必需性与常量、§6 分配规则、§7 槽共存、§10 choices、
  §15 `set_default`、契约要点）、`docs/03-design/yh-cli标准库设计.md`（§8.1/8.2/8.3、
  §9.3、§10.1）、`docs/03-design/yh-cli与argparse差异.md`（§1 新增 6 条一致项与
  槽共存的保留差异、测试数 46）。
- **验证**（种子 `bin/yh-darwin-arm64`）：`cd libs && yh test` = **125 passed /
  0 failed**；`--filter cli::` = 46 passed；`libs/cli/test/run.py` 5/5；
  `diff.py` = 91/94 与 argparse 一致、3 条已知差异、0 未知差异；
  `tmp/cli-gap/` 探针对六项逐条与 Python 3.14.6 对照。

## 2026-10-27 cli 标准库死代码清理（复核 P1 项）

- **删除零调用函数**：`libs/cli/help.yh` 的 `text_visible_width`（31 行，帮助宽度已按
  字节近似，无调用者）；`libs/cli/schema.yh` 的 `action_takes_values`（8 行，0 调用，
  且漏了 `store_const`/`append_const`/`count`，与 `action_is_zero_value` 语义冲突）。
- **删除只写不读的私有字段**：`mutex_row.members`/`member_count`（互斥校验实际按
  `result_owner.appeared` 计数）、`child_row.slot`、`parser_state.command_name`
  （连带 `new_state` 的第三个参数与两处调用点）、`parser_state.owned_by_parent`
  （`destroy_state` 无条件递归子节点）、`arg_row.metavars_count`、
  `arg_row.choices_count`（5 个读点改为 `len(row.choices)`，与 `value_in_choices`
  既有写法一致）。
- **净变化**：`libs/cli` 生产代码 6,846 → 6,793 行（`cli.yh` 893→886、
  `help.yh` 1,474→1,443、`schema.yh` 1,057→1,045、`commands.yh` 319→316）；
  `git diff --stat` = 9 插入 / 62 删除。
- **未动**：`Argument.metavars`、`Subparsers.title|description`、
  `HelpFormat.max_help_column` 是「已公开但未接线」的**行为缺口**而非死代码，
  补实现与删 API 需先决策，已记入 [todo](todo.md) 的 CLI-A。
- **验证**（种子 `bin/yh-darwin-arm64`，哈希与 `bin/yh-darwin-arm64.sha256` 一致）：
  `cd libs && yh test` = **122 passed / 0 failed**；`--filter cli::` = 43 passed；
  `libs/cli/test/run.py` = 5/5；`libs/cli/test/diff.py` = 91/94 与 argparse 一致、
  3 条已知差异、0 未知差异。删除 `libs/tmp/yh-test` 后复跑一次，确认 `cli` 模块
  重新编译（而非命中旧缓存）后仍全绿。

## 2026-10-26 性能测试 PF2–PF4：阶段归因、失效矩阵、规模/并发与性能任务

- **PF2 归因**（[报告](01-finished/yh-编译器性能归因与失效矩阵PF2-2026-10-26.md) +
  [口径](02-plan/yh-编译器性能归因口径-2026-10-26.md)）：`--stats` 行尾新增
  `time_front_ns/time_lower_ns/time_irbuild_ns/time_bridge_ns`（worker 内四段互斥累计），
  `perf-baseline.py` 出归因表并加 `--rss`/`--opt`。O0 冷编 worker 累计 23.5 s：
  lowering **66%**、IR 构造 20%、内嵌桥 8%、前端 6%；O2 冷编 30.7 s 中内嵌桥 **73%**
  （LLVM 优化），单函数改动 7.55 s（桥 3.59 s）⇒ 落 PC7 函数级目标文件。
- **PF2 失效矩阵**：新增 `tools/perf-invalidation.py`，三模块工程 × 6 场景全通过
  （仅注释 3/0 命中、私有体 2/1、公有接口 0/5、编译期常量 0/5、缺对象复用 3/0、
  缺缓存 0/3 且不假命中），判据是程序输出 + 每模块对象 SHA-256 与清缓存构建一致。
- **PF2 内存**：`--rss` 进程树采样（200 ms，默认关，单独跑）：冷编 405–434 MB、
  热编 138–254 MB、单函数改动 398–447 MB（采样峰值，共享页重复计入）。
- **PF3 规模/并发**（[报告](01-finished/yh-编译器规模与并发扩展PF3-2026-10-26.md)）：
  `tools/perf-scaling.py` 三轴合成工程；函数数 8× → 8.0× 墙钟但 schedule 14.9×
  （单模块每函数成本翻倍），模块数 8× → 3.5×，依赖深度 8× → 8.1×。
  `YH_WORKERS`（1..32，默认 4）成为并发入口：1/2/4/8 → 27.1/17.3/11.7/11.1 s
  （1.00/1.56/2.32/2.43×），8 worker 只多 5% 却把总工作量抬 58%。
- **PF4 性能任务**：`.gitea/workflows/perf.yml`（手动 + 每日 02:00，出报告并归档
  30 天，**只有测量无效才变红**）、`tools/perf-batch-check.py` 一句话结论、
  [噪声校准与判定规则](03-design/yh-性能回归判定与噪声校准-2026-10-26.md)
  （五批同条件定出噪声下限 ±2.2%；5% 标记 → 复测 → bootstrap CI 下界 >1.05 且两批
  复现 → 立 todo）。未设硬门。
- **门禁**：`tests/selfhost/llvm-function-cache.py` 新增「四段字段存在且非负、冷编全为正」
  断言；`just test` 与 `just selfhost-native` 全绿（project cases 122/122）。
- **已知缺陷修正**：priming 不能删 `manifest/link.manifest`（它是「本轮可写函数缓存」
  开关，删了会让 priming 退化成冷编、写不出 `.fir`，之后「0 命中」全是假象）。

## 2026-10-26 RB5：Darwin 产物位级可复现（链接暂存目录）

- **根因**：`ld64.lld` 的 `-adhoc_codesign` 把**输出文件 basename** 写进 codesign
  identifier。项目链接先把产物链到 `<out>.yh-tmp.<pid>` 再 rename 发布，pid 因此进了
  签名——同源两次构建的产物哈希不同（改前 `just build` 两次：`f051d37a…` / `00627e3e…`，
  同为 70,815,456 字节，`Identifier=yh.yh-tmp.54072`）。固定点门禁比较的是模块产物
  （`.s`/`.s.i`/`.o`），所以一直没暴露；受影响的是「同源同构」与发行可比性。
- **改动**（只动 Darwin/ARM64 项目链接的暂存位置）：
  - `compiler/build/darwin_link.yh` 新增 `mb_macho_tmp_split`（把暂存位置拆成
    `<out 目录>/.yh-tmp.<pid>/<basename>`：与产物同文件系统保证 rename 仍是原子的，
    子目录按 pid 隔离并发构建，basename 与最终产物一致 → identifier 只取决于产物名）、
    `mb_macho_link_stage`（建目录；pid 复用留下同名残骸时先清残留再重试，避免把崩溃
    残骸当成链接错误）、`mb_macho_tmp_discard`（删残余产物 + `rmdir`），并声明
    `@[extern] fn rmdir`。
  - `compiler/build/link_cache.yh` 的 `mb_link`：非 Mach-O 路径（Linux lld / cc）保持
    `<out>.yh-tmp.<pid>` 不变；Mach-O 路径改用暂存子目录，`mb_link` 的 5 条失败路径与
    成功发布后统一走 `mb_macho_tmp_discard`（失败不再留空目录，`mb_link` 674 → 688 行）。
  - **范围**：单文件 `-o` 形态的临时名 `<out>.yh-link-tmp` 不含 pid、本就位级可复现
    （`Identifier=abc.yh-link-tmp` 恒定），未改；ELF 产物不含文件名，未改。
- **证据**：
  - 同一 fixture 项目反复链接：改前（旧种子）`c6b2f66…` → `7ff4cdb…`、
    `Identifier=llvmdarwinlink.yh-tmp.29628`；改后两次均 **`b1c4a60f…`**、
    `Identifier=llvmdarwinlink`，`.build/` 无 `*.yh-tmp.*` 残留。
  - 编译器本体：用带 RB5 的编译器两次构建 compiler（输出各自的 `yh`）→ 均
    **`c24ee9be…`**、`Identifier=yh`。
  - 滚种子后（种子 `dadcad16…`）两次冷编 `just build` → 均 **`5a73120f…`**、
    `Identifier=yh`，端到端「同源同构」成立。
- **回归**：`tests/selfhost/llvm-darwin-link.py` 的 O2 项目段新增三条断言——删产物后
  重链必须位级一致、`codesign` identifier 必须**整行等于**产物名（旧形态
  `Identifier=<产物>.yh-tmp.<pid>` 只是以产物名开头，子串判定会漏掉 pid 后缀）、
  成功链接后 `.build` 不得残留 `*.yh-tmp.*`。该文件是进程级链接门（需真实 lld/签名），
  故用 Python 门而非 `.yh` 语料。
- **预算**：`max_build_lines` 10807 → 10982（RB5 +110：darwin_link +86、link_cache
  +29/−11，含 pid 复用重试；同批并入并行 PF 失效统计的 +65）、`max_file_lines`
  2242 → 2262、`max_globals` 190 → 193（后两项来自 PF 失效矩阵统计，非 RB5）；
  `max_function_lines` 上限不动（mb_link 688）。
- **门禁**（同一源码、滚种子前后各一轮）：`just arch-check` ✅、`just test` 0 FAIL ✅、
  `just selfhost-native` 122/122 + LA3 O0/O2 ✅、`just test-llvm-darwin` ✅。
- **文档**：`03-design/yh-macOS-LLVM后端接入设计.md` §6 补「暂存路径契约」；`docs/todo.md`
  的 RB5 关闭。
- **注意**：种子滚动把并行会话尚未提交的 PF 统计改动一并固化；这些改动已在同一棵树
  上通过全部门禁。

## 2026-10-26 新增 yh 编码规范

- **交付**：[yh 编码规范](03-design/yh-编码规范.md)（386 行）。把散落在
  `docs/yh.g4`、`docs/03-design/00-语义边界-0.0.1.md`、ADR-0013、`AGENTS.md`
  与 `compiler/`、`libs/` 既有写法里的编码约定收敛成一份可执行规范：排版
  （换行终结语句、括号外续行运算符必须在行尾、`} else {`、单行守卫）、命名
  （snake_case / PascalCase / UPPER_SNAKE、编译器前缀属历史遗留）、类型与转换
  （隐式只允许整数加宽）、可见性与模块（导出面收缩、私有类型）、控制流（只有
  `for`、无 fallthrough、不用 `goto`）、注释、文件组织（500–1000 行、banner、
  测试文件命名）、错误处理与资源、字符串插值、测试、编译期，附提交前清单与
  「规则 → 依据」对照表。**§2 命名**拆成 2.1 函数 / 2.2 变量两节并全部落到实测数据
  （动词频次表、概念词表 `count`/`len`/`cap`/`off`/`id`/`kind`/`status`、输出参数
  `out` 201 处、缩写分档 `i`/`j`/`k`/`n`/`gs`/`tk`、字段单位后缀 `_count`/`_len`/
  `_cap`/`_off`/`_size`/`_id`、谓词 `is_*`/`*_ok` 按模块返回 `int` 或 `bool`）；初稿
  「缩写只准 `i`/`n`」「谓词一律 bool」两条与现状不符，已按实测改正
  （`j` 125、`k` 80、`is_*` 18 处 int vs 2 处 bool）。
- **§7 文件命名（2026-10-26 用户决定）**：**文件名就是内容名，不用数字排序前缀**
  （`reader.yh`、`ssa_module_model.yh`，不写 `10_view.yh`/`00_types.yh`）。顺序不靠
  编号：模块内按文件名字节序处理、声明必须先于使用，所以被依赖的声明放语义名靠前
  的文件（`base.yh`/`defs.yh`/`types.yh`），拿不到就合并进使用者；测试文件统一
  `zz_tests*.yh`。实测依据：同模块 `api.yh` 用 `types.yh` 的 `Point` 报
  「未知类型（类型必须先定义）」（`pj_dir_less` 按文件名字节序，见
  `compiler/build/project_index.yh:429`）。**存量 `00_`/`10_`/`99_` 文件不改名**——
  改名会改模块内处理顺序，属独立任务；数字前缀字节序在字母之前，新老共存不冲突。
  同步把 [yh test 测试布局与运行约定](03-design/yh-test测试布局与运行约定-2026-10-25.md)
  §1/§2 的推荐名改成 `zz_tests*.yh`，避免两处说法打架。
- **负面验证（写文档时自证，不是新代码）**：`./yh check` 实测确认了三条容易写错的
  规则——隐式转换矩阵（整数加宽可以，窄化/同宽异号/整数↔bool/浮点互转必须
  `.to_type`，诊断文案原样引用）；`-1` 隐式加宽到 `u64` 得 `18446744073709551615`；
  括号外行首运算符被拆成两条语句（`a` 得 `1` 而非 `3`，编译无警告）。另核实
  `let a = 1` 报「此处需要一个类型」、`[0]int` 报「数组长度必须为正」、`while`
  报错、`goto` 在 `compiler/`+`libs/` 中 0 处使用、`${}` 需 `import fmt` 且仅在
  项目模式可用。文档内全部相对链接已逐条校验可解析。
- **接入 `AGENTS.md`**：`## 代码规范` 开头加一句指向本规范（只做入口，不抄细则），
  原有硬要求条目原样保留——细则改动只改规范一处，避免两处说法漂移。
- **边界**：纯文档，不改语法、不改代码、不动种子，故不新增 `tests/` 用例（无行为
  变更）；规范里标 **[建议]** 的项（行长 ≤100、缩写表、TODO 写法）不进任何门禁，
  门禁仍是 `just test` / `just selfhost-native`。

## 2026-10-26 性能测试 PF1b：20 轮正式基线 + 产物质量

- **交付**：[基线报告](01-finished/yh-编译器性能基线PF1b-2026-10-26.md)。本机
  Darwin/arm64（8 核，load1 峰值 7.47/告警线 8.0）四场景各 20 轮（3 轮不计分预热）：冷编
  **10.07 s**、全量重编 **16.78 s**、热编 **0.98 s**、单函数改动 **3.58 s**（IR 204 命中 /
  check 38 命中）；产物 6 个用例 × O0/O2，O2 运行时间快 1.8–8.9×、`.text` 小 1.77–2.39×。
- **工具**：`tools/perf-baseline.py` 新增 `--warmup`/`--timeout`、MAD 与 load1 峰值、
  `corpus_version`、整批 `validity`（失败/超时/**缺统计行**/缺编译器即 `invalid` 且明说
  不得下结论）；`run_build()` 先查 `time_*_ns`/`ir_*`/`check_*` 是否存在，缺失写
  `error=缺统计：…` 而不是静默归零（方案 §6）；run-id 撞秒自动加 `-2` 后缀，避免同秒
  两次运行互相覆盖。**修掉 A/B 污染**——旧实现两侧共用一份语料，交错 probe 让 hot 报
  18.9 s（真值 1.05 s），现两侧各用独立副本并校验哈希一致。新增 `tools/perf-product.py`
  （O0/O2 运行时间 + `.text`/只读/文件大小，checksum 由 Python 参照实现独立算出，
  `--append-to` 并入同 run-id 报告）与 `tests/perf/bench-*.yh` 六个用例（循环/数组/排序/
  FNV 哈希/结构体切片/递归调用，均带内部自检，并在缺省输入下自校验冻结的期望 checksum）。
- **语言事实**（写进 `tests/perf/README.md`）：`int` 是 32 位，种子与累加器须显式
  `i64`/`u64`（否则溢出成负数，本轮真踩到）；结构体数组不能直接切片，先 `to_type([]T)`。
- **验证**：正式批 `tmp/perf/20261026-204539/`（raw.json + report.md + product.json/md +
  bin/；四场景各 20 样本，validity ok，report.md 含逐轮 load1/墙钟与 O0/O2 产物表）；
  另三批复核 `193043`/`195432`/`202140`，四批中位差 −0.0%~+2.2%（批间噪声 ≤2.2%，与
  load1 上升同向）。负向路径留证：`204512`（假编译器退出 0 无统计行 → 全记缺统计、
  invalid、表格 `—`）、`204530`（编译器路径不存在 → invalid，exit 1）、`204530-2`
  （`--timeout 1` → 四场景全超时 invalid）。手工 `otool -l` 核对 `.text` 与 `size -m`
  一致（bench-call-O2 = 1752 B）；`just test` 0 FAIL、`just selfhost-native` 全绿
  （固定点一致、自解析 119 文件 OK、project cases 122/122）。
- **边界**：不设硬门、不接 CI（PF4）；未测 Linux/x86_64；未采内存（单进程 RSS 不等于
  并行总内存）；场景成组执行而非 A/B 交错（本轮无对照二进制）。

## 2026-10-26 B2-3/B2-5：`mb_link` 阶段化（LinkPlan）与预算收口

- **`mb_link` 676 行 → 6 个阶段 + 一个 `LinkPlan`（`compiler/link/link_cache.yh`）**：
  一次链接的可变量全部进 `LinkPlan`（栈上，指针传给阶段）：入参、链接方式、
  链接器与 C 项目输入、计时、链接键、`link_tmp`/`link_manifest` 路径缓冲、
  argv 与三类路径行缓冲、`library_search_*`、`mod_tag` 暂存。
  阶段与行数：`mb_link_prepare` 60、`mb_link_objects` 167、`mb_link_key` 161、
  `mb_link_args` 148、`mb_link_libs` 96、`mb_link_exec` 52，编排函数
  `mb_link` 41 行。**20+ 处「4 连 free」错误分支收敛成一个
  `mb_link_release`**：阶段只返回 0/-1，不释放；`mb_link` 在任一步失败或成功
  收尾统一释放并把指针清零。
- **行为保持**：语句顺序与原函数逐行对应，只做「局部量 → 计划字段」的机械搬移；
  阶段返回码区分「缓存命中(1)/继续(0)/失败(-1)」，其余语义（argv 顺序、
  缓存键、manifest 内容、产物发布与校验）一字未改。
- **验证（在独立 worktree 上做，避免与本机并发会话的合并冲突）**：
  `just build` + `arch-check` 通过（`link` 3,531 → 3,657，新增 `LinkPlan` 结构）；
  `just test` 全绿（ANTLR + 语法 49/49 + 运行语料 122/122 + compiler 内嵌测试 +
  libs）；`tests/modules/build-check.py --backend llvm` **122/122**（暂存副本口径）。
  当时未在**隔离 worktree** 跑 `selfhost-native` 全门：共享 LLVM 闭包缓存已被
  另一分支的 `tools/llvm-darwin-host.py` 重新准备（bridge 哈希 3098a81f →
  a09fc268），隔离副本的闭包自检过不去。**归位后在主 worktree 补跑，双门全绿**：
  `just test` 0 失败；`just selfhost-native` 0 失败——候选两代固定点
  48 个产物逐字节一致、cc4 自解析 127 个源文件、项目验收 122/122、libs 测试全过。
- **B2-5 预算收口**：`max_function_lines` 700 → **360**（实测最大函数已是
  `lower/module_snapshot_lower_expr` 的 360，`mb_link_query_identity` 274、
  阶段函数 ≤167）；`max_link_lines` 3,657、`max_build_lines` 6,308、
  `max_g_call_sites` 0、`max_globals` 172 全部等于实测值。
- **并发提示**：本轮期间同一 worktree 上有另一会话把 B2-3 的工作区提交为
  `a14eb5d` 并合入了 `llvm-2`（`b7476aa`，CLI-R 重写 + `YH_BUILD_CACHE`）。
  本条目记录的 B2-3/B2-5 数字是在该合并后的树上实测的（16 模块 / 127 文件 /
  54,456 行，`main` 318、新增 `cmdline` 605）。

## 2026-10-26 B2-1/B2-2/B2-4：`proj` 收产物键、`link` 成模块、`module_build` 拆三

- **B2-1 产物路径与缓存键 → `proj/proj_40_art.yh`（526 行，16 函数）**：FNV 哈希
  （hash_init/fnv/hash_file/hash_hex）、目录布局（build_dir/sub_dir/
  default_binary_path + 路径预算常量）、模块键与文件名（mod_tag/asm_stem_base/
  asm_stems/module_obj_row）、接口路径（module_iface_*/module_ctiface_*）、open_out。
  这几个符号原本被发射簇与链接簇共用，是 B2-2 的硬前置。保持「纯计算」：
  不建目录、不调外部工具、不读 `BuildCtx`——会话后缀改成显式 `suffix` 参数，
  `default_binary_path` 不再借 build 的 `append_bytes_np`。
- **B2-2 链接簇 → `compiler/link/`（7 文件 3,531 行 + 新增 context.yh）**：
  `link_cache`/`link_inputs`/`darwin_link`/`process`/`clock.*` 从 build 迁出，
  `module build` → `module link`；`arch-check` 新增 `link: {gen, proj, backend}`
  （**不得 import build**，否则成环）。为解掉三处反向依赖，把落点放在下层：
  `pl_target_code_current` → `proj.target_code_current()`、
  `append_bytes_np` → `gen.append_np()`、本层计时从 `BuildCtx` 移进
  `link/context.yh`（`link.object_ns()/link.link_ns()/reset_timings()`，
  argv0 由 `mb_set_argv0` 转交 `link.set_argv0`）。`project_link.yh` 仍留 build
  （读 `toml_*` globals）。顺带修 `llvm_emit_single_file` 的形参 `link int`
  → `do_link`（与模块名冲突）与 testkit 的 `build.realpath` → `link.realpath`。
- **B2-4 `module_build` 拆三**：`module_build`（命令面与标准库装载 690）/
  `module_emit`（单模块发射流水线 711）/ `module_cache`（缓存身份与依赖表 414），
  同模块内搬家，无 import 变化。
- **实测**：模块 14 → **15**、文件 122 → 126、代码 53,714 → 53,854；
  `build` 10,289 → **6,348**（B2 的目标 ≈6,000 基本达成）、`link` 3,531、
  `proj` 775 → 1,318；依赖边 46 → 51；`gen.G()` 保持 0；模块级 `let` 169 → 172
  （`link` 三个会话量）。预算：`max_build_lines` 10,289→6,348、
  新增 `max_link_lines` 3,600、`max_proj_lines` 1,318、`max_globals` 172。
- **验证**（每一步都单独跑过双门）：`just test` 全绿；`just selfhost-native`
  全绿——候选固定点 45 个产物逐字节一致、cc4 自解析 126 个源文件、项目验收 122/122。
- **B2-3（`mb_link` 阶段化）未做**：676 行、20+ 处「4 连 free」错误分支，阶段间
  共享 30+ 局部量，属本轮风险最高的一项，需要单独一轮完整双门与产物逐字节对照；
  已在 [todo.md](todo.md) 立项并写明方案，B2-5（预算收口）随后。

## 2026-10-26 B1-3/B1-4：统计与会话状态独立，`gen.G()` 归零并关闭

- **B1-3 统计独立成 `gen.CompileStats`**：25 个计数（`enabled`/`front_cache`/
  `lex`/`syntax`/`index`/`pass1`/`globals`/`functions`/`ir_*`/`check_*`/
  `backend_*`/`asm`/`link`/`compiler_hashes`/`ir_cache_salt`/`firc_write_off`/
  `workers`）从 `GenState` 物理移出，读点统一 `gen.stats().<字段>`。
  **没有按方案搬进 `build`**：写入方主要在 gen/lex/parse（前端），搬进 build 会
  形成 build↔gen 双向耦合；独立结构 + 窄口已经达成「GenState 瘦身 + 读点归属」。
  `GenState` 因此只剩 `c_cfg` 指针与 `task`。
- **B1-3 `BuildCtx`**：新增 `compiler/build/build_ctx.yh`（按文件名序排最前），
  把编译器路径/指纹/接口后缀（5）、阶段计时（5）、调度观测（2）、`mb_dep_*`
  依赖表（9）共 21 个模块级 `let` 收进 `BuildCtx`，入口 `bc()`。模块级可变 `let`
  188 → **169**；`build` 自己的 `gen.G()` 13 → 0。
- **B1-4 关闭 `gen.G()`**：全仓 40 个「只读 `gs.task.*`」的函数改走 `gen.task()`
  （parse 21、testkit 12、check 3、cmd 5、ast 2、comptime 2、lex 1 …）；
  `parse/iface_ct_map` 的 4 个 helper 与 llvmlower fixture 的三个 helper 形参从
  `*gen.GenState` 收窄成 `*gen.TaskCtx`；`gen/buffer` 内部最后一处 `G()` 改
  `task()`。删除 `pub fn G()`，`GenState` 由 `pub struct` 降为模块私有。
  **跨模块只剩三条窄口**：`gen.task()` / `gen.stats()` / `proj.ctx()`+`proj.cfg()`。
- **门禁同步**：`max_g_call_sites` 49 → **0**（任何新增 `gen.G()` 立即红）、
  `max_globals` 190 → **169**、`max_build_lines` 10,265 → 10,289（`BuildCtx`
  结构体换掉 21 行 let 声明）。`arch-check` 的报告行在没有 `gen.G()` 时不再打印
  空括号。
- **迁移手法**：按「函数体 + 只读 `task`」两个条件做机械替换（有其它 `gs.` 读点的
  函数不动，留给下一刀），每刀后跑 `just build`；`gen.task()` 与 `gen.G().task`
  语义相同（同一个 `&g_state.task`），属零语义改动。
- **验证**：`just test` 全绿；`just selfhost-native` 全绿（cc3→cc4 固定点 42 个
  产物逐字节一致、cc4 自解析 122 个源文件、项目验收 122/122、libs 测试）。

## 2026-10-26 B1-2：目标/配置收进 `proj.Cfg`，`canon` 改显式出参

- **目标/编译期配置的存储归 `proj`，类型仍留在 `gen`**：新增 `gen.TargetCfg`
  （`target`/`host_target`/`target_explicit`/`dialect`/`opt_level`/`emit_kind`/
  `emit_text_path`/`module_mode`/`is_entry_mod`），`GenState` 删掉这 9 个字段只留
  `c_cfg` 指针，实体在 `proj.ProjectCtx.cfg`（`proj.cfg()`）；driver 在
  `proj.init()` 后 `gen.bind_cfg(proj.cfg())` 绑定，`gen` 内部读点改 `cfg().<字段>`。
  **为什么不按方案 §2.3 直接搬给 `proj`**：`gen` 自己也在读这些字段（`gen/target.yh`
  `c_dialect` 3 处、`c_module_mode` 3、`c_host_target` 2、`c_target` 3 等），而 `gen`
  是 `proj` 的下层。指针绑定让「`proj` 唯一持有 + `gen` 只读指针」两全。
- **未绑定调用方的兼容路径**：`compiler/` 的 `test` 块与 `tests/` 的 fixture 直接
  `import gen`，不会走 driver。`gen` 保一个模块私有回退实例，`state_init()` **只在
  未绑定时**重置它（绑定后绝不重置，否则会抹掉 `--target`/`-O2`）；默认值只有一份
  实现 `gen.target_cfg_defaults`，`proj.init()` 也调它。
- **`canon` 取消隐式出参**：`proj.canon(base_off, base_len, rel, out_off, out_len)`，
  `ProjectCtx` 删除 `canon_off`/`canon_len`。原先这对字段既是 `canon` 的结果、又被
  `mb_mod_tag` 当模块标签暂存（两个含义共用一个全局槽，症状是路径串位而不崩）。
  现在每个用到路径暂存的函数持有自己的局部 `c_off`/`c_len`；跨函数返回值改出参：
  `mb_build_dir(..., out_len)`、`pj_find_root(..., out_len)`、
  `pj_c_path(..., out_off, out_len)`。
- **迁移中抓到一处真实的隐式依赖**：`pj_load_c_config` 依赖 `pj_c_path` 写全局游标
  再读它（`let path_off int = c_off`）——改成局部后 C 源路径变空，
  `clang: error: no input files`。按「谁产生谁出参」改成 `pj_c_path` 返回路径（这正是
  B1-2 要消灭的形态），并用脚本扫出「读 `c_off/c_len` 但自己既不调 `canon` 也不调
  `mb_mod_tag`」的函数确认只剩这一处。
- **实测**：`gen.G()` 115 → **98**（build 66 → 50）；`proj` 762 → 775、`gen` 5538 →
  5584（`TargetCfg` + 默认值实现）、`main` 383 → 387（绑定两行）、`testkit` 1578 →
  1585；模块级可变 `let` 187 → 188（回退实例）。预算按实测调整：`max_g_call_sites`
  115→98、`max_build_lines` 10236→10265、`max_file_lines` 2236→2261、
  `max_testkit_lines` 1578→1585、`max_module_lines` 383→387。**这些上浮是显式状态
  的代价，B2 拆 `build` 后必须回落**。
- **测试**：`astcheck`/`llvmfront`/`llvmtarget`/`llvmlower`/`llvmchecked` 五个 fixture
  补 `proj.init()` + `gen.bind_cfg(proj.cfg())` 与 `import proj`；`build-check` 的
  `llvmtarget`/`llvmfront` 拷贝清单加 `proj`。
- **验证**：`just test` 全绿；`just selfhost-native` 全绿（cc3→cc4 固定点 42 个产物
  逐字节一致、cc4 自解析、项目验收 122/122、libs 测试）。

## 2026-10-26 B1-1：项目模型迁入 `proj` 模块（build 拆分第一台阶）

- **按 [构建态对象化与 build 拆分重新规划](../02-plan/yh-构建态对象化与build拆分重新规划-2026-10-25.md)
  §3.1 的 P1 落地**：新增数据层模块 `compiler/proj/`（3 文件 762 行）：
  `proj_00_model.yh`（7 个表类型 `PFile/PMod/PProj/PDep/PInput/PLinkItem/PLinkGroup`
  + `ProjectCtx` + `proj.ctx()`/`proj.init()`）、`proj_10_table.yh`（唯一写者
  `proj.add_project/add_module/add_project_module/add_module_file/add_file/add_import`
  + 只读 `module_in_project`/`find_project_root`）、`proj_20_path.yh`
  （`canon/pool_str/env_fetch/file_exists/set_root_project/is_root_project/diag`
  + 前端窄口 `file/file_count/test_file_selected`）。
- **`gen` 不再拥有项目模型**：`GenState` 删掉 22 个表字段（三张表 + 11 条导入平行
  数组 + `p_stdlib`/`p_state`）与 6 个测试/扫描字段，`p_file/p_file_count/
  test_file_selected` 三个窄口移出（gen 是 proj 的下层，不能反向依赖）；
  `gen/state.yh` 5686 → 5538 行。`build/project_state.yh`（574 行）整文件删除，
  `pj_dir_add` 并入 `build/project.yh`，`build.PjState` 被 `ProjectCtx` 取代。
- **迁移是机械的、可审计的**：一次性脚本按「局部名 `proj` → `pj`（避免遮蔽新模块名）
  → `gs.p_*`/`gen.G().p_*` 读点 → `pj_state()` → 函数前缀 → `gen.P*` 类型前缀 →
  补 `import proj`」七步跑 30 个文件，再删掉 36 处因此变空的
  `let gs *gen.GenState = gen.G()`。**没有留下任何影子字段或转发壳**。
- **实测**（`python3 tools/arch-check.py`）：模块 13 → **14**、文件 119 → 121、
  代码 53,529 → 53,580；`build` 10,807 → **10,242**、`gen` 5,686 → 5,538、
  `proj` 762；`gen.G()` 165 → **115**（build 101 → 66、testkit 27 → 12，
  parse/main 未动）；最大文件 2,241 → 2,236。
- **`arch-check` 口径**：`ALLOWED` 新增 `proj: {gen}`（前端/构建共用数据层，
  反向依赖即成环），`ast/check/parse/lower/build/testkit/main` 各加 `proj` 边；
  `comptime` 也加了 `proj`——唯一读点是 `ct_layout_array_expr` 的文件下标越界检查，
  走 `proj.file_count()` 而不是自己拿表（与方案 §2.2 的 `comptime:{gen}` 差一条边，
  已在 ALLOWED 注释里写明理由）。预算按实测收紧：`max_build_lines` 10,807 →
  10,242、`max_testkit_lines` 1,592 → 1,578、`max_file_lines` 2,242 → 2,236、
  `max_g_call_sites` 165 → 115，新增 `max_proj_lines` 800；`max_module_lines`
  381 → 383（driver 多了 `import proj` 与 `proj.init()` 各一行）。
- **测试**：`tests/modules/projects/astcheck/main/main.yh` 改用 `proj.PFile` +
  `proj.ctx().files`，并新增窄口断言（`proj.file_count()==1 && proj.file(0)==&files[0]`）；
  `tests/modules/build-check.py` 的 `astcheck`/`llvmchecked`/`llvmlower` 三个 fixture
  拷贝清单各加 `proj` 模块；`llvmchecked`/`llvmlower` fixture 的 `gs.p_files`
  改写为 `proj.ctx().files`。
- **验证**：`just test`（ANTLR + 语法 + 运行语料 122/122）全绿；
  `just selfhost-native` 全绿——候选两代模块固定点（cc3→cc4，42 个产物）逐字节一致、
  cc4 自解析 121 个源文件 OK、固定点探针 OK、项目验收 **122/122**、libs 测试全过。
- **环境注意（下次跑门先看）**：本机 `$TMPDIR/yh-fast` 被同机多个 worktree
  （`x`/`ratfish`/`llvm-*`）共用，`stage-yh` 会互相覆写 `yh` 副本，导致自举后续门
  （lex-stats/cache/build-check）读到**别的分支的编译器**。并发时用私有目录：
  `just FAST_DIR="$TMPDIR/yh-fast-b11" selfhost-native`。另：`FAST_STAGE=0` 时
  `lex-stats` 会因仓库根 `yh` 能发现 `libs/` 标准库而多扫 101 个文件（期望 6 的用例
  按「暂存副本」口径写的），该差异在 B1-1 之前的 HEAD 上同样存在，不是本次回归。

## 2026-10-26 CI 去掉 ANTLR：参考语法门只在本地开发跑

- **改动**：`.gitea/workflows/ci.yml` 删除 `antlr` job（原为 Apple container 内
  `apt-get install default-jre-headless` + `tools/run-antlr-ci.sh`，每次 push 起
  一个 ubuntu:24.04 容器装 Java + pip + curl 下载 jar），分支门只剩
  `darwin-arm64` / `linux-arm64` / `linux-x86_64` 三个平台 job；ANTLR 参考语法门
  仅保留在本地 `just test` / `just quick`（`tests/yh/check.py` 默认模式）。
- **连带清理**：删除只为该 job 存在的 `tools/run-antlr-ci.sh`；
  `.circleci/config.yml`（云端真机参照，非门禁）同步删除 `antlr` job 与 workflow
  条目，避免引用已删脚本。
- **文档**：`AGENTS.md` 的 CI 说明改为"三端并行 + ANTLR 只本地跑"；
  `docs/02-plan/yh-基础设施即代码IaC方案-2026-10-24.md` 的 G3 缺口收敛为"只剩
  镜像非内容寻址"（ci.yml job 数 4 → 3）；`docs/03-design/yh-架构图-2026-10-25.md`
  的 CI 节点去掉 ANTLR。
- **理由**（2026-10-26 用户决定）：参考语法门与平台无关，平台 job 本来就只看
  编译器的 `--syntax-check` 模式；为它单独起容器装 Java + 现场 `curl` jar 属
  不可复现的 CI 成本，收回到本地开发更划算。
- **验证**：Ruby `YAML.safe_load` 解析 `ci.yml`（3 job：`darwin-arm64`/
  `linux-arm64`/`linux-x86_64`）与 `.circleci/config.yml`（workflow 只引用现存
  job）通过；除本条记录外，仓库内不再引用 `tools/run-antlr-ci.sh`；本地
  `just test` 路径未改动（`tests/yh/check.py` 默认 ANTLR 模式仍在）。

## 2026-10-26 构建入口迁 just：justfile 成为唯一真源，Makefile 收成转发层

- **改动**：新增仓库根 `justfile`（just 1.59 / 1.21 均解析通过），承载旧
  Makefile 的全部目标，覆盖验证通过后**删除 `Makefile`**（just 成为唯一构建
  入口）。迁移期间用 23 行转发层（`make <目标> [VAR=值]` →
  `just <目标> [VAR=值]`，变量经 `MAKEOVERRIDES` 前置）过渡。
  `.gitea/ci/Dockerfile` 预装 `just`（Ubuntu 24.04 apt 包 1.21.0）；
  `.gitea/workflows/{ci,release}.yml`、`.circleci/config.yml`（云端真机参照）
  与 `tests/{toml,fmt,string}/install.py` 的 `make …` 全部改调 `just`
  （变量覆盖统一写在目标名之前）。
- **覆盖验证**：`git show HEAD:Makefile` 的 43 个目标与 justfile 逐项比对——
  `test-json`（工作区已随 `tests/json/run.py` 删除）与 `tmp/llvm-migration`
  （内部 order-only 目标，由 `_prepare` 承担）不需要；其余全部有等价 recipe，
  `build`/`default`/`libs-test`/`libs-test-o2`/`test-num` 为新增入口。
  selfhost-native、test-llvm-darwin、install、seed、stage-yh、llvm-host 等
  行数不同的目标逐条核对（含 libs 全跑 vs 分库、Darwin SDK 安装、
  `compiler/.build` 过期判定）。
- **等价性**：目标名、变量名（`SEED`/`SEED_DEST`/`SKIP_CORPUS`/
  `SELFHOST_KEEP`/`SELFHOST_WORKDIR`/`FAST_STAGE`/`YH_LLVM_HOST`/
  `YH_LLVM_CACHE`/`LLVM_JOBS`/`LLVM_TARGET`/`LLVM_SEED`/`PREFIX`/`DESTDIR`/
  `INSTALL`）、平台分支（种子/LLVM 宿主/专项门/缓存门）与旧 Makefile 一一
  对应；`just`/`just build`/`just dev` 对应旧默认目标/冷编/增量，默认目标按
  源码 mtime 判断（只看 `compiler/*.yh`、`compiler/*/*.yh`、`compiler/llvm`、
  清单与四个构建脚本，不递归 `compiler/tmp` 与 `compiler/.build`）。
- **迁移中发现并修掉的两处 just 语义坑**：
  1. 命令行变量覆盖必须写在 recipe 名之前（`just SEED=… build`），反序会报
     ``does not contain recipe``；`_ensure_built` 与 Makefile 转发层都按此顺序。
  2. `install` 原本是 `@cd libs && find …` 单行、后续 Darwin SDK 安装仍在仓库
     根执行；just 脚本里 `cd` 会残留，改为子 shell 内切换后 Darwin SDK 路径
     才能解析（`just test-toml-install` 从失败转为通过）。
- **验证**（删除 Makefile 后复跑）：`just build`（冷编，内嵌 LLVM 桥接入）、
  `just test`（三层回归全绿，含 libs 与 arch-check）、
  `just selfhost-native`（主门，项目语料 122/122）、`just quick`、
  `just test-toml-install` / `just test-fmt-install`（install 验收脚本改用
  `just DESTDIR=… PREFIX=/usr install` 后验证安装树与仓库外导入）全部通过；
  CI 三份 YAML 经 ruby 解析无语法错误；just 1.24.0 与 Ubuntu 24.04 的
  1.21.0 均可解析 justfile。
- **已知限制**：同机并行跑两个 make/just 门会共享 `compiler/.build`（自举脚本
  `native-selfhost.py` 的 `build()` 明确用仓库 `compiler/.build`），互相打断
  模块编译；本次验证期间两次与并发会话互踩，最终串行跑通。旧 Makefile 同样
  有此约束。

## 2026-10-26 LA3 构建卡死：check 切片字符串段死循环

- **症状**：工作树 `yh` 对任何项目构建都不返回（hello world 3 行 >120 s、LA3
  fixture >300 s），`tests/selfhost/llvm-function-cache.py` 因此表现为「一直不
  结束」；同机 10-24 种子跑同一构建 0.79 s。
- **根因**：`compiler/ast/module_snapshot_check_slice.yh` 的 v3 字符串段编码
  循环（`// 字符串段（v3）` 之后）没有 `i += 1`，命中前的 `continue` 也不推进
  `i`：`data_str_lookup` 未命中（无字符串字面量的表达式，最常见）走
  `continue`，命中走循环尾，两条路径都不自增 → 每模块首个函数永久自旋。
  插桩实测：单次 capture 为 `fi=0, expr_n=1, store.expression_n=1`，`i` 恒 0、
  `cursor` 恒 601，15 s 内 350 万次迭代；`sample`/`lldb` 显示 worker 时间全部
  落在 `mb_llvm_emit_module → checked_check_cache_capture →
  checked_slice_capture` 的 112 B `AstExpr` 拷贝（`_memmove`）。
- **修复**：两处补 `i += 1`（`continue` 前、循环尾）。回归覆盖沿用既有
  `tests/modules/projects/llvmfunctioncache` + LA3 脚本：该路径挂起即失败。
- **验证**：`rm yh && make` 冷编 96.8 s；fixture 冷编 O0 2.18 s / O2 0.97 s；
  `python3 tests/selfhost/llvm-function-cache.py --compiler-path ./yh` 7.8 s
  （此前无限）；`just test` 依次通过语法语料、运行语料、modules、
  libs、compiler-tests、fmt、code-stats，止于 arch-check。
- **本轮未关闭**：
  1. LA3 `损坏记录` 断言 `check hits/misses/skipped` 期望 `(4,1,4)`、实际
     `(5,0,5)`：种子下 `index` 与 `index.check` 的键**完全相同**，当前 v3 下
     两套键**完全不相交**（各 4 条）。脚本按 `index`（IR 键）写
     `<key>.fchk` 只会造出孤儿文件，真正的 check 记录未被损坏；要么让 check
     键回到与 IR 键一致，要么脚本改从 `index.check` 取受害键。
  2. arch-check 超预算：`build` 10736 > 10730（在飞改动给 build 增加 25 行），
     与本次修复无关。

## 2026-10-26 两项待决策收口（用户决定）

- **NP 定位**：只保留 **NP3**（受检契约与 lowering 解耦），NP0/NP1/NP2/NP4/NP5
  关闭。依据：NP1/NP2 的对象代码（`ir_simplify`、`ssa_inline`）已随 A0b/A0e 从
  `compiler/` 删除，NP4 由 ADR-0014 取代，NP0 的模式/计数口径并入现有
  `just test` + O0/O2 + 自举门，NP5 交 LLVM 默认管线。
  [ADR-0011](adr/0011-yh采用Nanopass风格优化阶段契约.md) 状态改为「部分被
  ADR-0014 取代（2026-10-26），只保留 NP3」并附阶段处置表；
  [方案](02-plan/yh-Nanopass风格优化架构实施方案.md) 与
  [设计](03-design/yh-Nanopass风格优化架构.md) 头注改为只执行 NP3、其余章节
  仅作历史设计；NP3 以单条任务记入 [todo](todo.md) 的架构优化小节。
- **字面量只读化（H1）**：决定改语义——字面量发 `constant` 进只读段，能静态
  判定的写入改编译期诊断（先覆盖字面量直接下标与不经函数边界的局部别名），与
  comptime 的「字面量字节池只读」口径统一；逃逸写入退化为运行期崩溃。
  决策前实测：运行期写入现在**允许且生效**（`let p *char = "abc"; p[0]='z'`
  → `zbc`），`tests/yh-run` 无运行期依赖用例；`backend/llvm_module.yh:385` 已按
  `mutable` 选 `global`/`constant`，字面量登记点在
  `lower/module_snapshot_static.yh`；`__data` 实测 hello-world 14 B、`./yh`
  93 KB。实施项见 todo H1，与 PC3b 一起滚种子。
- 本轮只改文档，未改编译器、未构建、未滚种子。

## 2026-10-26 修复编译器浮点字面量的 1 ULP 偏差

- **根因**：`compiler/gen/sem_value.yh` 的 `sem_parse_float_bits` 用「逐位
  `mant*10 + digit`、`frac_scale*10`、指数累乘」的浮点运算解析十进制字面量，
  大指数（`1.5e300`）经多次舍入后比正确值多 1 ULP（bits …870 vs …869）。
  num 库自己的解析与 Python 都是 …869，此前只有编译器字面量路径错。
- **修复**：字面量去掉 `_` 后交给宿主 libc 的 `strtod`（glibc/macOS 均按
  当前舍入模式正确舍入），保持 `-0.0`、次正规、上溢为 inf 等既有行为；
  `@[extern] fn strtod` 声明在 `gen/sem_value.yh`，并在注释里记录 E1 迁移时
  需替换为纯 yh 实现（已加 todo E1.3）。
- **回归**：新增 `tests/yh-run/run/float-literal-rounding.yh`，覆盖 1.5e300、
  0.1、最大有限数、最小次正规、-0.0、1e309、下划线分隔、下溢到 0、
  2^53+1 等 13 个位模式，期望值与 Python `struct` 一致。
- **验证**：`just build` 23.4s；`just test` exit 0（run 语料含新用例）；
  `just libs-test` 122 + cli/os/libc；`just libs-test-o2` 122；
  `just test-num` 220/220；`just selfhost-native` exit 0（cc3→cc4 固定点、
  cc4 自解析 119 文件、project cases 122/122）；`git diff --check` 通过。
  注：仓库入口此时已完全迁移到 justfile（Makefile 已删除）。

## 2026-10-26 RB1（worker 父死子退）+ PF0/PF1（冻结语料与基线工具）

- **RB1**：`module_worker` 在 fork 后记录父 pid（`mb_worker_parent_set`），并在函数入口与
  整模块发射前检查 `getppid()`（`mb_worker_parent_alive`），父进程不在即退出。
  实测：构建到 0.6 s 时 `kill -9` 父进程，4 个在跑的 worker **2.2 s 内全部退出**；此前
  中断的构建会留下 `ppid=1` 的孤儿继续烧 CPU（曾把 load 推到 195 并连带卡死其它门禁）。
  预算：`max_build_lines` 10786 → 10807（RB1 +19，含 `getppid` extern）。
- **PF0/PF1**：新增 `tools/perf-baseline.py`，把 `compiler/` 复制成冻结语料并记录清单
  SHA-256，跑冷编 / 全量重编（含写缓存）/ 热编 / 单函数改动四个场景，逐轮记录墙钟、
  父进程阶段耗时、load1、IR/check 命中与 `.fir` 写入量，写 `tmp/perf/<run-id>/{raw.json,report.md}`；
  `--ab PATH` 支持 A/B 成对交错与变化率。
  首份基线（load≈4–5，3 轮）：冷编 **10.3 s**（schedule 8.2 + object 0.5 + link 1.1）、
  全量重编 **16.1 s**、热编 **0.98 s**、单函数改动 **3.59 s**（IR 204 / check 38 命中）。
- 均未改编译器语义；`just test` / `just selfhost-native` / `arch-check` 复跑全绿。

## 2026-10-26 PC3b：滚种子（冷编 23.0 s → 11.0 s）

- **前置**：`just arch-check` / `just test`（0 FAIL）/ `just selfhost-native`（122/122、LA3 O0/O2）/
  `just test-llvm-darwin` 全绿；`verify-seed` 通过；`strings yh` 无构建机 `$HOME` 路径。
- **结果**：`bin/yh-darwin-arm64`
  旧 `56bf3f56027fb7609c8f37c384c0f3b8e07314f50618f2cf093274583ca6ceb8`
  → 新 **`ea24f6591abc945584e63adea8e30d72b1ef3185c9de1d2758124c63a95d652b`**（70,402,800 字节），
  哈希文件同步写入。
- **滚后实测（load≈2.9）**：`just build`（新种子冷编 13 模块）**11.04 s**，
  滚前同一操作 23.0 s → **−52%**；冷编写入的函数缓存记录 `.fir` = **0**（PC3 生效）。
- **滚后门禁**：`just test` 0 FAIL；`just selfhost-native` 122/122 + LA3 O0/O2 + 两代固定点（39 产物）
  + 自解析全通过。
- 顺带修（迁移 bug）：`_prepare` 是 `[private]` 且排在文件最前，`just` 的「第一个 recipe」规则
  让**裸 `just` 只跑 `_prepare`（空操作）**——`yh` 不存在时也不重建（实测 0.12 s、0 模块）。
  把 `default` / `all` 移到 `_prepare` 之前后，裸 `just` 恢复「源比 yh 新时冷编」（实测 11.40 s、13 模块）。
- **RB1 之后再次滚动**（同一轮内）：`ea24f659…` → **`e52d208ccd03a96044e4c93d2c74d8913bfdec9fcf10c41ecb12348baa784e70`**，使种子与「带 worker 父存活检查」的当前源码一致；门禁在同一源码上已全绿。
- 说明：种子不入库（`bin/` 由 `just fetch-seed` 获取），本次滚动只影响本机 `bin/`，哈希文件供校验。

## 2026-10-26 just 迁移后的门禁复核（+ 修 Darwin/ARM64 守卫）

构建入口已由并行会话从 Makefile 迁到 **justfile**（`830d1d5`），本轮性能工作的门禁证据
需要在新入口下重跑：

- `just arch-check` 0.42 s ✅（预算 10786，未再增长）
- `just test` **0 FAIL** ✅
- `just selfhost-native` ✅（项目用例 **122/122**、LA3 缓存矩阵 O0/O2、两代固定点、自解析；
  用例数 124 → 122 是同期 YT4 迁移删掉旧夹具所致）
- `just test-llvm-darwin` ✅ —— **先修了迁移 bug**：`just` 的 `arch()` 在 macOS 返回
  `aarch64`，而该门与 `selfhost-llvm-darwin` 的守卫拿它与 `arm64` 比较，在 Darwin/ARM64
  上直接报「要求 Darwin/ARM64」拒绝执行；改用已归一化的 `seed_arch`（2 处）。

同轮把 `docs/finish.md` 本轮条目、`docs/todo.md` 的 PC 条目、分析文档 §14 里的命令从
`make …` 同步为 `just …`（历史条目保持原样），并立项 RB1（worker 父死子退）、
RB2（门禁校验 staged 二进制新鲜度），修掉 RB3、复核 RB4。

## 2026-10-26 PC7a：大二进制改用 (size, mtime_ns) 身份哈希

- **动机**：探针测得每轮构建重哈希 **271 MB**（352–401 次调用），其中大头是几十 MB 级的
  二进制（编译器自身 70 MB、链接器/驱动），而 `link-libs.manifest` 对归档的摘要缓存本来是
  命中的。
- **改动**：新增 `mb_mix_file_identity`（`link_inputs.yh`），把「编译器指纹」与「链接工具身份」
  两处从**内容哈希**改成 **(size, mtime_ns)**（仍混入解析路径）。
- **语义**：这两处只需要「文件换没换」的身份，不需要内容摘要。代价是 make/ninja 级的
  mtime 信任——同内容不同 mtime 只会多失效一次缓存；工具/编译器被替换时 mtime 变化
  必然失效。
- **实测（load≈4.0）**：热编 **1.14–1.21 s → 1.00–1.02 s**（其中 schedule 0.27 → 0.03 s，
  因为不再哈希 70 MB 的编译器自身）；单函数改动 **3.83–4.45（中位 3.9）→ 3.71–3.81
  （中位 3.76）**，object 阶段 0.87 → 0.52 s。
- **未动的部分**：`link-libs.manifest` 的归档摘要缓存本来就有效；剩余 ~0.5 s 是模块级
  `.o` 与 lld 的固定成本，属 PC7（函数级目标文件）范围。
- **预算**：`max_build_lines` 10761 → 10786（PC7a 共享 helper 与两处调用 +25）。
- **门禁**：`just test`、`just selfhost-native`（124/124、LA3 O0/O2）、`just test-llvm-darwin`、
  `arch-check` 全绿。

## 2026-10-26 性能目标收口（A3 + B，滚种子推迟）

- **低负载基线（load≈4.5，`compiler/`）**：冷编 11.2–12.0 s、**全量重编（含写缓存）17.5 s**、
  **热编 1.14–1.21 s**、单函数改动 3.83–4.45 s（中位 3.9）、冷编后首次改动 4.78 s。
- **达标**：全量重编 ≤20 s ✅、热编 ≤1.5 s ✅（PC4b/PC5 按目标数字关闭）。
- **目标重定（A3）**：单函数改动目标由 ≤3 s 改为 **≤4 s（现状满足）**。理由：模块重编
  2.03 s 里 LLVM 每轮要为**整模块 205 个函数**重发 `.o`，链接 1.17 s 因 object 变必须
  重跑；≤3 s 只能靠**函数级目标文件**，已单独立项 PC7（可行性见
  [设计](03-design/yh-函数级目标文件可行性-2026-10-26.md)）。
- **PC3c 按实测关闭**：冷编后首次改动只贵 0.5 s（4.78 vs 4.27），check 切片仍命中
  38/205；为 0.5 s 引入「冷编后台补写」会重新引入孤儿进程/竞态，判定不做。
- **顺带量化（PC7a 立项）**：每轮构建**重哈希 271 MB**（352–401 次调用，含 70 MB 级
  二进制），关掉后热编 1.14 → 0.25 s。按 (size, mtime_ns) 复用摘要可省 ~0.4 s，
  但与 PC7 独立，需先决定是否接受 make/ninja 级 mtime 信任。
- **滚种子（PC3b）推迟**：三套门禁绿，但工作区有并行会话未提交改动
  （libs/json、testkit、.gitea、tests/toml），现在滚会一并烘进种子；等其落地后由用户确认。
- **门禁**：`just test`、`just selfhost-native`（124/124、LA3 O0/O2）、`just test-llvm-darwin`、
  `arch-check` 全绿（本轮仅文档改动，未再动 `compiler/`）。

## 2026-10-26 PC2 v3：check 切片复用恢复（并修掉一个自旋死循环）

- **根因（2026-10-25 定位）**：切片格式 v2 只带 expr/stmt/edge/binding/symbol 行，
  不带 `store.strings`，命中后 lowering 报「字符串缺少受检字节」；且 v2 的记录会
  让类型表随命中变化，编号漂移。
- **v3 设计**：头 +2 字（字符串计数/字节数）+ 尾部字符串段（label/length/quoted +
  字节本体，取自本函数 expr 行的 `const_bits` 数据标签）；pass2b 入口快照
  「类型数/字符串数/静态数据数」，capture **只缓存没有新建类型与静态数据的函数**
  ——命中因此不会改变类型编号，字符串由 `gen.data_str_restore` 按 label 恢复。
  `module_worker` 恢复 `firc_check_load`；`firc_commit_kind` 按旧索引回收旧键记录。
- **实测**：编译器自编增量 `gen` 模块 check 命中 **38/205**（此前恒为 0）；带字符串的
  函数命中后 `yh run` 输出正确；`.fchk` 记录 1209 → **373**（不可缓存的函数不写）。
  `llvm-function-cache.py` O0/O2 矩阵（IR + check 双计数）通过。
- **踩坑（当天修掉）**：字符串段的**计数循环**与**发射循环**用了不同谓词（发射侧漏了
  `soff/slen` 越界判断），越界条目只多写字节 → 堆破坏 → 内层 `for` 拿到垃圾长度 →
  无限自旋。表现是机器上 5 个 `ppid=1` 的 `yh build` 各烧 25–42% CPU、load 195，
  并行会话的门禁（用旧的 staged 二进制）也一起卡死。`sample` 直接指到
  `checked_slice_capture`。修复：两个循环共用同一谓词。教训：同一份数据的「算尺寸」
  与「写字节」必须共用条件，否则先溢出再自旋，日志上什么都看不到。
- **门禁**：`just test`、`just selfhost-native`（项目用例 **124/124**、LA3 O0/O2、
  两代固定点）、`just test-llvm-darwin`、`arch-check` 全绿。
- **预算**：`max_build_lines` 10736 → 10761（PC2 v3 装载 +5、PC2b 回收 +20），
  原因即本条。

## 2026-10-26 PC1b：IR 类型按内容去重

- **定位**：PC1 把「同一 ABI 多个类型编号」归因到 `gen.ty_push`，实测不成立——
  受检类型表结构重复 `cdup=0`（`ty_ptr/ty_array/ty_slice/ty_fn_abi` 已有去重）。
  重复在 IR 层：`ir_module_add_type` 无条件追加，`compiler/build` 的 **907 个 IR 类型
  里 706 个是同内容重复**（数组/指针/切片/函数类型每个函数都再登记一次）。
- **修复**：`ir/ssa_module_10_build.yh` 新增 `ir_module_type_same`（种类/bits/size/
  align/elem/count/字段(type_id,offset)/abi/变参），`ir_module_add_type` 命中既有
  内容时直接返回旧编号（名义名单独比较，保证两个同布局 struct 不合并）。
- **效果**：模块 IR 类型数 907 → **118**（最大模块），结构重复 706 → **0–1**；
  函数缓存合并的结构回退（PC1 的临时绕过）计数 **0**；命中率不变
  （`gen` 201/201、`build` 268/268，`ir_functions` 数随并行改动略变）。
- **测试**：`tests/modules/projects/llvmmodule` 新增三条断言（同内容合并、布局不同
  另起编号、名义名不同不合并），`llvm-module-ownership` 用例通过；
  `llvm-function-cache.py` O0/O2 矩阵通过；`just test` 73 s 绿。
- 说明：IR 层去重是纯收益（类型表更小、编号可比），不改变序列化/合并格式。
