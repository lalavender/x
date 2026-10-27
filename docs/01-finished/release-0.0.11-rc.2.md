# 0.0.11-rc.2 — 架构收敛（B1/B2 + CLI）与性能/产物体积工程

预发布（prerelease）。rc.2 由 **0.0.11-rc.1** 的种子构建
（种子链：0.0.10 → 0.0.11-rc.1 → 0.0.11-rc.2）。它把 rc.1 之后的两条主线合并进
`llvm` 主分支：**架构收敛（B1/B2 + CLI 迁移）** 与 **性能工程（PF1b–PF4 + PL1 系列）
及产物体积收口（I4-7 + J6-L1..L4）**。

## 主要内容

### 一、架构收敛（B1 + B2 + CLI-R）

- **B1 状态收敛**：`gen.G()` 读点从 165 降到 **0**，`GenState` 收成 `gen` 模块私有；
  统计拆成 `gen.CompileStats` 窄口（`gen.stats()`），build 会话状态收进 `BuildCtx`
  （`bc()`），前端读点改走 `gen.task()`。
- **B2 拆分**：`build` 从 10,717 行拆到 **6,637**，新增 16 个模块
  （`proj` / `link` / `parse` / `cmdline` 等）；`mb_link` 拆成 `LinkPlan` + 六个阶段，
  失败路径统一释放；产物路径与缓存键抽进 `proj` 的 art 子簇。
- **CLI-R**：命令行解析与帮助改由 `libs/cli` 生成（R1–R4），新增 `yh` 命令行等价性
  金标（差分 argparse），`cmd` 只剩参数映射（318 行 / 0.6%）。

规模基线（`just arch-check` 守护）：**16 模块 / 129 文件 / 55,206 行**，
`gen.G()`=0，`main` 占比 0.6%。

### 二、性能工程（PF1b–PF4 + PL1）

- **基线口径**：`tools/perf-baseline.py` 四场景（冷编/全量重编/热编/单函数改动）
  × 20 轮 + 3 轮预热，输出 median/p95/MAD、逐轮 load1、四段阶段归因；`--ab` 成对交错；
  失败/超时/**缺统计**一律标 `invalid` 且不出通过结论。
  本机 Darwin/arm64 基线：冷编 **10.1 s**、全量重编 **16.8 s**、热编 **0.98 s**、
  单函数改动 **3.6 s**（O0）。
- **阶段归因（PL1）**：`--stats` 新增 `time_front/lower/irbuild/bridge_ns` 与 lowering
  内部 8 段（prep/decl/build/verify + lookup/cache/fn/capture）。结论：O0 冷编 worker
  累计 23.5 s 中 lowering 66%（其中真 lowering 74.7%、模块 verify 18.8%）、
  IR 构造 20%、内嵌桥 8%、前端 6%；O2 冷编中内嵌桥 73%（LLVM 优化）。
- **缓存与校验提速**：函数缓存记录格式升到 **v2**（外层头加 payload FNV 校验和），
  命中装载跳过整段语义 verify（仍校验结构/规模/规范编码，合并后整模块仍 verify）；
  capture 从 **19.3 → 13.7 ms/函数**（去掉重复的 verify+plan）；
  去掉后端对同一模块的**第二次**全量 verify（A/B：冷编 **−10.6%**、单函数改动
  **−13.3%**、worker 累计 **−16.5%**）；模块 verify 的符号名去重与实体计数改为
  哈希/计数（O(n²)→O(n)）。
- **工具与门**：`tools/perf-scaling.py`（函数数/模块数/依赖深度三轴）、
  `tools/perf-product.py`（O0/O2 产物运行时间 + `.text`/只读/体积）、
  `tools/perf-invalidation.py`（6 场景失效矩阵，判据是程序输出 + 每模块对象
  SHA-256 与清缓存构建一致）、`tools/perf-batch-check.py`；
  `.gitea/workflows/perf.yml`（手动 + 每日，**只出报告不设硬门**）。
  内存口径新增 `--mem {footprint,rss}`：Darwin 用 `proc_pid_rusage` 物理足迹、
  Linux 用 `VmHWM` 高水位（冷编进程树 418.8 MB）。

### 三、产物体积收口（fmt 线：I4-7 + J6-L1..L4）

- **I4-7（缺陷修复）**：循环内调用期 `ALLOCA` 泄漏栈——聚合实参副本、结构体返回值槽、
  变参打包、切片后备数组的 `ALLOCA` 落在循环体，每次迭代再分配且不回收。现在
  `llvm_function_allocas` 把全函数 `ALLOCA` 提到入口块只发一次（跨迭代复用）。
  回归 `tests/yh-run/run/207-call-temp-stack-growth.yh`。
- **J6-L1**：Darwin 链接缺省 `-dead_strip`（`YH_LINK_DEAD_STRIP=0` 回退），开关进链接键。
- **J6-L2**：ELF 每函数发 `section ".text.<mangled>"`、每全局发独立 `.rodata./.data.`
  section，Linux 链接追加 `--gc-sections`（内嵌 lld）/`-Wl,--gc-sections`。
- **J6-L3**：依赖/标准库项目单独 **O2**（`proj.module_opt_level`，`YH_DEP_OPT=0` 回退），
  接入对象发射、模块 manifest 键与函数 IR 环境键；根项目仍走命令行优化级。
- **J6-L4**：`YH_LINK_STRIP=1` 给 Darwin 链接加 `-x`（剥离局部符号表）。
- **度量**：`tests/perf/fmt-size/` + `tools/size-report.py` + `just size-report`；
  fmt 版 hello 与 printf 版比值 **1.063**（上限 1.2）。

## 兼容性与行为变更（请先读）

1. **函数缓存格式 v2**：旧 `.fir`/`.fchk` 视为不兼容，首次构建会重建一次（不影响正确性）。
2. **依赖项目缺省 O2**：引用标准库/第三方项目的产物会明显变小；`YH_DEP_OPT=0` 恢复旧行为。
3. **Darwin 链接缺省 `-dead_strip`**：`YH_LINK_DEAD_STRIP=0` 恢复；开关计入链接键，
   切换会触发一次重链。
4. **ELF section 化 + `--gc-sections`**：Linux 产物布局变化，链接参数追加
   `--gc-sections`/`-Wl,--gc-sections`。
5. **`--stats` 字段扩充**：新增 `time_front_ns` / `time_lower_ns` / `time_irbuild_ns` /
   `time_bridge_ns` 与 8 个 lowering 细分字段；原有字段顺序不变。
6. **环境变量**：新增 `YH_WORKERS`（worker 上限 1..32，默认 4）、`YH_BUILD_CACHE`
   （构建缓存目录）、`YH_DEP_OPT`、`YH_LINK_DEAD_STRIP`、`YH_LINK_STRIP`；
   `FAST_DIR` 默认按 workspace 隔离（`$TMPDIR/yh-fast-<hash>[-run_id]`）。

## 验证（本机 macOS/arm64，llvm 分支 `190bf9c`）

- `just` 构建通过；`just arch-check` 通过（16 模块 / 129 文件 / 55,206 行，预算按实测）。
- `just test`：**133 passed / 0 failed**。
- `just selfhost-native`：模块固定点 cc3→cc4（48 产物）一致、cc4 自解析 **129** 文件、
  固定点探针 OK、项目语料 **124/124**。
- 专项门：`darwin-dead-strip.py` 4/4、`opt-level.py` 4/4、`size-report` 比值 1.063 ≤ 1.2、
  `llvm-function-cache.py` O0/O2 六场景全绿（含损坏记录仍判 miss）。

## 平台与资产

- 三端资产由 `release.yml` 构建：`darwin-arm64`、`linux-arm64`、`linux-x86_64`
  （x86_64 为容器模拟，仅作兼容性证据）。
- **已知未覆盖**：Linux 上 ELF `--gc-sections` 的端到端体积度量只做过本地试跑，
  正式对照待 Linux 原生 runner（`0.0.11` 正式版前补）；`ir_verify` 的逐函数指令校验
  （约 1.8 ms/函数）未优化，记 todo PL1d2b。
