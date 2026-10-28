# 0.0.11 — 架构收敛（B1/B2 + CLI）与性能、产物体积工程

正式版。0.0.11-rc.2 已作为预发布验证通过（三端流水线全绿 + 发布二进制验收），本版
在其代码上只增加发布文档，**代码与 rc.2 完全一致**。
本版由 0.0.11-rc.2 的种子构建（种子链：0.0.10 → 0.0.11-rc.1 → 0.0.11-rc.2 → **0.0.11**）。
tag 直接打在默认分支 `llvm`（分支已收敛为 `llvm` / `arm64` / `main`，不再保留
`<ver>-rc` / `<ver>-release` 双线）。

## 主要内容

**命令行改用 `libs/cli`（CLI-R）**

- `compiler/cmdline/cmdline.yh` 用 argparse 风格的 `cli.Parser` 声明 17 个选项与 6 个
  子命令（`build/check/run/test/list/version`），全局选项经 `cli.inherit` 在子命令前后
  都可写；帮助/用法/错误文本与退出码由库生成。
- `cmd/driver.yh` 只剩「请求 → 全局状态 → 分派」，`cmd` 合计 318 行（0.6%）。
- 旧行为保留：裸 `yh` 打印完整帮助并退 2、`--backend legacy` 拒绝、已移除目标简写别名
  仍给旧诊断。内部子进程协议 `--emit-module` 明确豁免。
- 等价性由 `tools/cli-golden.py` 与旧二进制做**严格差分**（退出码 + 归一化 stdout/stderr，
  41 条 argv 用例）。

**架构收敛（B1/B2）**

- B1：`gen.G()` 读点 165 → **0**，`GenState` 收成 `gen` 模块私有；统计走
  `gen.CompileStats`，build 会话状态收进 `BuildCtx`。
- B2：`build` 从 10,717 行降到 **6,637**，全仓 **16 模块 / 129 文件 / 55,350 行**；
  `link` / `proj` 独立成模块，`mb_link` 拆成 `LinkPlan` + 六个阶段。

**性能工程（PF1b–PF4 + PL1）**

- 基线口径：四场景 × 20 轮 + 3 轮预热，median/p95/MAD、逐轮 load1、四段阶段归因；
  `perf-invalidation.py` 6 场景失效矩阵（判据是程序输出 + 每模块对象 SHA-256 与清缓存
  构建一致）；`perf-scaling.py` 三轴规模律；`perf-product.py` 产物运行时间与体积；
  `.gitea/workflows/perf.yml` 只出报告（**不设性能硬门**）。
- 归因结论：O0 冷编 worker 累计里 lowering 66%（真 lowering 74.7%、模块 verify 18.8%）、
  IR 构造 20%、内嵌桥 8%、前端 6%；O2 冷编内嵌桥 73%（LLVM 优化）。
- 缓存与校验：记录格式升到 **v2**（payload FNV 校验），命中装载跳过整段语义 verify；
  capture **19.3 → 13.7 ms/函数**；去掉后端对同一模块的第二次全量 verify
  （A/B：冷编 **−10.6%**、单函数改动 **−13.3%**、worker 累计 **−16.5%**）。
- 内存口径：`--mem footprint`（Darwin `proc_pid_rusage` 物理足迹 / Linux `VmHWM`），
  冷编进程树 **418.8 MB**、热编 **230.1 MB**。

**产物体积（I4-7 + J6-L1..L4）**

- I4-7：修「循环内调用期 ALLOCA 泄漏栈」（聚合实参副本、结构体返回槽、变参打包、
  切片后备数组），全函数 ALLOCA 提到入口块只发一次。
- J6-L1 Darwin 缺省 `-dead_strip`（`YH_LINK_DEAD_STRIP=0` 回退）；J6-L2 ELF 每函数/每
  全局独立 section + 链接期 `--gc-sections`；J6-L3 依赖/标准库项目单独 **O2**
  （`YH_DEP_OPT=0` 回退）；J6-L4 `YH_LINK_STRIP=1` 加 `-x`。开关都进链接键/模块键。
- 度量：`just size-report`（fmt 版 hello / printf 版 hello 比值 **1.063**，上限 1.2）。

**其它**

- RB5 位级可复现修复：Mach-O 暂存路径不再被 ELF 的 `<out>.yh-tmp.<pid>` 覆盖，
  ad-hoc 签名的 identifier 只取 basename，同源两次链接产物哈希一致。
- 构建缓存目录可由 `YH_BUILD_CACHE` 指定；`FAST_DIR` 默认按 workspace 隔离；
  `YH_WORKERS`（1..32，默认 4）可调 worker 上限。

## 实测（本机 macOS/arm64，load≈4–5）

| 场景 | 0.0.10 | 0.0.11 |
| --- | --- | --- |
| 冷编（清 `.build`） | 10.3–11.0 s | **10.1 s** |
| 全量重编（含写缓存） | 16.1 s | **16.8 s** |
| 热编无改动 | 0.98 s | **0.98 s** |
| 单函数改动 | 3.59 s | **3.6 s** |

注：0.0.11 的冷编数字含本轮新增的四段打点（纳秒级）与统计字段；场景成组执行、
无 A/B 交错，跨版本只读量级。完整口径与四批复核见
[PF1b 基线](yh-编译器性能基线PF1b-2026-10-26.md) 与
[PF2 归因](yh-编译器性能归因与失效矩阵PF2-2026-10-26.md)。

## 三端验证

- 分支门（`ci.yml`）：darwin-arm64 / linux-arm64 / linux-x86_64 三 job。
- `release.yml`（tag `0.0.11-rc.2`，run 176）三端全绿后发布 prerelease；
  正式版 `0.0.11` 沿用同一份代码重新构建三端资产。
- 本机门禁：`just test` **133 passed / 0 failed**、`just selfhost-native`
  （48 产物固定点、cc4 自解析 129 文件、项目语料 124/124）、`just arch-check`、
  `just test-llvm-darwin`（22 项 PASS）、fmt 专项门（`darwin-dead-strip` 4/4、
  `opt-level` 4/4）、缓存矩阵 O0/O2 六场景全绿。

## 已知边界

- **CLI-R1d**：lowering 在「紧跟聚合 `let` 的结构体字段赋值」上有缺陷，常见输入**不复现**，
  已降级为观察项（属 lowering，不是命令行）。
- **Linux ELF `--gc-sections`** 的字节级体积对照尚未在 Linux 原生 runner 上做；
  tag 流水线里的 linux-arm64 job 已覆盖链接 + 运行 + 自举功能路径。
- **x86_64 资产是容器模拟**，只作兼容性证据，不作原生行为/性能结论。
- **LC1**：Linux 宿主裸跑 `yh build` 仍需 `YH_LINK_RUNTIME_FLAGS`（闭包运行库参数尚未
  进清单键）。
- **PL1d2b**：`ir_verify` 的逐函数指令校验约 1.8 ms/函数，未优化（纯性能项）。
- 单函数改动 ≤3 s 仍需函数级目标文件（PC7，工期按天；O2 下单函数改动 7.55 s，
  其中内嵌桥 3.59 s）。
