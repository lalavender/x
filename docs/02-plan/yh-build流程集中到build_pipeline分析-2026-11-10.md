# yh `build/` 目录分析与 `build_pipeline.yh` 集中方案（2026-11-10）

状态：**分析报告，未改代码**（用户选择「先只出分析报告」）。
基线：`llvm` @ `6f5e355`，`compiler/build/` 实测 28 个 `.yh` / 8,767 行。
用途：回答两件事——①构建流程到底由哪些函数与数据结构组成；②把它们集中到
`compiler/build/build_pipeline.yh` 要动什么、有什么硬约束。

---

## 1. 结论速览

| # | 结论 | 依据 |
| --- | --- | --- |
| 1 | `build/` 全部代码同属**一个** `module build`（`cache/` 子目录是另一个 `module cache`） | 28 文件头 `module build`；`cache/*` 为 `module cache` |
| 2 | 流程主干 = 6 文件 / **2,717 行 / 56 函数**，合并**零 import 变更、零语义变更** | §2、§4 |
| 3 | 加 LLVM 链路 = 9 文件 / **3,695 行 / 90 函数** | §2 |
| 4 | 真正属于 build 的**数据结构只有一个** `BuildCtx`；项目/模块/文件/顺序表在隔壁 `proj.ProjectCtx`，跨模块**不能**随合并搬走 | §3.1、§3.2 |
| 5 | 4 个 `project_dir.*.yh` + 3 个 `cache/lock.*.yh` 是**平台变体**，靠文件名字节序选片，**禁止合并** | §3.5、§5.4 |
| 6 | 合并后单文件 2.7k–3.7k 行，与 AGENTS.md「每文件尽量 500–1000 行」冲突——**需要用户拍板** | §5.5 |
| 7 | 迁移必须先保住两条既有规则：**文件名字节序 = 编译顺序**、**类型先定义后用** | §5.3 |

建议范围：**§5.1 方案 A（主干 6 文件）**，一次一批、每批 `just build` 可验。

---

## 2. `build/` 现状分组

### 组 1 · 构建流程主干（建议合并，2,717 行 / 56 函数）

| 文件 | 行 | 函数 | 职责 |
| --- | --- | --- | --- |
| `build.yh` | 35 | 1 | `BuildCtx` 定义 + 单例 `bc()` |
| `module_build.yh` | 505 | 12 | 命令面 `cmd_build`/`run`/`list`/`version`/`contracts` + 标准库装载 |
| `build_scheduler.yh` | 576 | 13 | 有界 fork worker 池 + InterfaceReady 调度 + `mb_resolve_self_path` |
| `module_worker.yh` | 461 | 6 | worker 进程内单模块入口 `mb_emit_indexed_module` |
| `module_emit.yh` | 696 | 13 | 缓存判定 `mb_compile_start` + 两遍前端 + 接口/对象发布 |
| `module_cache.yh` | 444 | 11 | 缓存键身份、依赖表 `mb_dep_*`、manifest 原子提交 |

### 组 2 · LLVM / IR 链路（可选并入，978 行 / 34 函数）

| 文件 | 行 | 函数 | 职责 |
| --- | --- | --- | --- |
| `llvm_pipeline.yh` | 276 | 12 | 受检快照 → 模块 IR → LLVM 文本 → 桥 → 原子发布 |
| `llvm_emit.yh` | 343 | 5 | 单文件编译面 `yh f.yh`、`--syntax-check` |
| `function_ir_cache.yh` | 359 | 17 | 函数级 `.fchk`/`.fir` 缓存读写与提交 |

### 组 3 · 全局缓存（不建议并入，1,980 行 / 27 函数）

| 文件 | 行 | 函数 | 说明 |
| --- | --- | --- | --- |
| `cache_global.yh` | 365 | 9 | 构建侧接线：`mb_cache_init`、项目锁、模块 publish/lookup |
| `cache_admin.yh` | 568 | 18 | `yh cache info/clean/trim/verify` 工具面 |
| `cache/`（7 文件） | 1,047 | — | **`module cache`**：ActionID/OutputID、store、平台锁 |

组 3 是「缓存」的主题，不是「构建流程」；`cache/` 还属于另一个模块，
合并会推翻 §L0/L5 分层（`check`/`lower` 依赖 `cache`）。

### 组 4 · 项目模型（不建议并入，2,897 行 / 72 函数）

`project_index.yh` 1,066 / `project_resolve.yh` 533 / `project_link.yh` 375 /
`toml.yh` 600 / `project.yh` 51 / `project_dir.*.yh` 272（4 个平台变体）。
它们是「项目是什么」，被 `module_build` 编排使用，也是 `testkit` 的直调面；
混进流程文件会让「流程」与「数据来源」再次糊在一起。

### 组 5 · 其它

`unused_function.yh` 195 / 7 函数 —— `yh build` 的未用函数报告，独立特性。

---

## 3. 数据结构清单

### 3.1 `BuildCtx`（`build.yh:5`）—— 构建流程唯一的自属状态

| 字段组 | 字段 | 用途 |
| --- | --- | --- |
| 身份 | `argv0`、`self_path`、`compiler_identity[32]u8`、`compiler_fingerprint`、`compiler_fingerprint_ready` | 编译器内容身份，参与模块缓存键与环境键 |
| 会话 | `iface_suffix` | 本轮接口后缀（子进程协议 `--iface-suffix`） |
| 缓存 | `cache_store`（`cache.CacheStore`）、`cache_debug` | 全局 content store 句柄 + `YH_CACHE_DEBUG` 开关 |
| 调度 | `sched_limit`、`sched_limit_ready` | worker 并发上限（`YH_WORKERS`，缺省 4） |
| 依赖表 | `dep_bind`/`dep_bindlen`/`dep_ifoff`/`dep_ctoff`/`dep_mod`/`dep_mi`/`dep_n`/`dep_cap`/`dep_base` | 单模块编译前的导入绑定 + `.s.i`/`.s.ct` 路径池 + 接口模块基线 |

`bc()` 是唯一访问口（`build.yh:33`）。这 21 项里没有一项是「项目」数据——
这解释了为什么合并只需搬代码，不需要搬模型。

### 3.2 跨模块的结构（搬不动）

| 结构 | 位置 | 为什么不能进 `build_pipeline.yh` |
| --- | --- | --- |
| `proj.ProjectCtx`（项目表 / 模块表 / 文件表 / `order[]` / `mark[]` / `stdlib`） | `proj` 模块 | `build` 依赖 `proj`，反向合并会破坏分层 |
| `hash`、`cache.Key`/`CacheInputs`/`CacheStore` | `hash` / `cache` 模块 | 同上 |

### 3.3 `build/` 内其它 struct（跟着合并一起搬）

| struct | 位置 | 用途 |
| --- | --- | --- |
| `LLVMEmitResult` | `llvm_emit.yh:13` | 单文件发射结果 |
| `CacheFile`、`IdSet` | `cache_admin.yh:18`/`:25` | `yh cache` 工具面（组 3） |
| `TomlVal`、`TomlArrayItem`、`TomlSec` | `toml.yh:21`/`:34`/`:38` | 清单解析（组 4） |
| `PJDirEntry` | `project.yh:13` | 目录扫描（组 4） |
| `UfCand` | `unused_function.yh:7` | 未用函数候选（组 5） |

### 3.4 运行期态（不是 struct，但在流程里）

`mb_schedule_modules_locked`（`build_scheduler.yh:423`）在栈上 malloc 三条
`count` 长度数组：`states`（0 未启动 / 1 运行中 / 2 接口就绪 / 3 完成 / 4 失败）、
`pids`、`keys`（每个模块 `cache.CACHE_ID_SIZE` 字节 ActionID）。
`mb_worker_parent`（`module_worker.yh:128`）是 worker 侧孤儿自检的进程内标记。

### 3.5 文件系统契约（流程的真实接口，比函数签名更重要）

`mb_mkdir`（`module_emit.yh:25`）一次建 `<build>/` 下 7 个子目录
`asm obj iface manifest ir llvm index`（函数缓存另建 `firc/`）：

| 路径 | 生产者 | 消费者 |
| --- | --- | --- |
| `iface/<tag>.s.i`、`.s.ct` | worker（`mb_iface_write_ready`） | 依赖方 worker、链接器 |
| `iface/<tag>.s.i.ready<suffix>` | worker | 父调度器 `mb_sched_refresh_interfaces` |
| `obj/<tag>.o` | worker（`llvm_emit_publish`） | `link.mb_link` |
| `manifest/<tag>.manifest`（4 × 32 字节 ID） | 父进程 `mb_manifest_commit` | 下一轮 `mb_compile_start` 本地命中 |
| `index/<tag>`（64 hex） | 父进程 | C4/C6 观测与跨 worktree 调试 |
| `llvm/<tag>.ll`、`asm/<tag>/*.s` | worker（按开关） | 用户/调试 |
| `firc/<tag>/.fchk`、`.fir` | worker | 函数级缓存 |

平台变体选片：`pj_scan_is_target`（`project_index.yh:590`）按文件名里的
`.linux/.darwin/.windows`、`.arm64/.x64` 段决定是否编入本目标 —— 所以
`project_dir.*.yh`、`cache/lock.*.yh` 这类同名多实现文件必须保持独立。

---

## 4. 构建流程调用链（带位置）

```text
yh build
  cmd/yh/cmd_build.yh:13            api_build
  build/module_build.yh:219         cmd_build
    :220  mb_resolve_self_path      (build_scheduler.yh:194)
    :228  mb_select_links           → link.li_select_add
    :248  load_stdlib            → mb_try_default_stdlib / mb_load_default_stdlib
    :253  pro_find_root              (project_resolve.yh:493)
    :259  load_project           (project_index.yh:175)  清单+扫描+模块索引
    :263  pj_bind_imports           (project_resolve.yh:25)
    :282  pj_entry_mod              (project_resolve.yh:13)
    :291  pj_topo                   (project_resolve.yh:306) → proj.ctx().order[]
    :303  proj.build_dir            (proj 模块，产物路径)
    :307  mb_mkdir                  (module_emit.yh:25)
    :310  mb_schedule_modules       (build_scheduler.yh:408)
            :423 mb_schedule_modules_locked
                  mb_cache_init       (cache_global.yh:131)
                  mb_sched_set_session        本轮接口后缀
                  循环：mb_sched_refresh_interfaces / mb_sched_deps_ready
                        mb_compile_start         (module_emit.yh:81)
                          本地 manifest 比对 + 全局 store lookup
                          命中 → 返回 1（父进程只记 [缓存]）
                          未命中 → mb_spawn_indexed_module (build_scheduler.yh:134)
                                     fork / --emit-module 子进程
                                     → mb_emit_indexed_module (module_worker.yh:142)
                                         dep 接口装载 → pass1 → 绑定 → pass2
                                         → check.verify_module → CheckedModule
                                         → mb_llvm_emit_module (module_worker.yh:71)
                                             llvm_emit_module_to_cached (llvm_pipeline.yh:199)
                                             → lower → backend → 桥 → .o
                                         → 写 .s.ct → .s.i → .ready
                        父进程 waitpid 成功 → mb_sched_publish_interface (build_scheduler.yh:355)
                                            → mb_manifest_commit (module_cache.yh:418)
    :338  link.mb_link              (link 模块)
```

`yh check` 复用同一条链（`support.session().check_only` 只改收尾与接口清理）；
`yh run` = 同一链 + 链接 + `cmd_process_run`；`yh test` 在
`testkit/test_cmd.yh:834-939` 直接复用 `load_stdlib`/`pj_*`/`mb_schedule_modules`。

外部契约（`cmd/yh` 与 `testkit` 实测调用）：27 个 `build.*` 名字，
模块共 46 个 `pub` 项。合并后这些名字与签名**一个都不能变**。

---

## 5. 集中方案

### 5.1 目标文件与内部分节

`compiler/build/build_pipeline.yh`（新增），按流程阶段排序，防止类型先用后定义：

| 节 | 内容 | 来源 |
| --- | --- | --- |
| 0 | 文件头说明 + `module build` + import 并集 | 6 文件 import 合并去重 |
| 1 | **数据结构** `BuildCtx`、`g_build_ctx`、`bc()` | `build.yh` 全文 |
| 2 | 命令面与标准库装载 | `module_build.yh` |
| 3 | 路径预算常量、`mb_mkdir`、check 接口清理 | `module_emit.yh:25-79` |
| 4 | 单模块发射：`mb_compile_start` + 两遍前端 + 接口发布 | `module_emit.yh:81-` |
| 5 | worker 入口 `mb_emit_indexed_module` + 父进程自检 | `module_worker.yh` |
| 6 | 调度器（状态机 / fork / 接口就绪 / 发布） | `build_scheduler.yh` |
| 7 | 缓存键与 manifest 提交 | `module_cache.yh` |

迁移后原 6 文件删除（`build.yh` 只留 `BuildCtx` 也可能，但那就没达到「集中」目的）。

**方案 B**：再加 `llvm_pipeline.yh` / `llvm_emit.yh` / `function_ir_cache.yh`
成第 8 节（LLVM 链路），单文件 3,695 行。

### 5.2 迁移批次（每批独立可编译）

| 批 | 动作 | 验收 |
| --- | --- | --- |
| 1 | 建空文件骨架 + 搬 `BuildCtx`（`build.yh` 内容），删旧文件 | `just build` |
| 2 | 搬 `module_cache.yh`（无反向依赖，最独立） | `just build` |
| 3 | 搬 `module_worker.yh` | `just build` |
| 4 | 搬 `module_emit.yh` | `just build` |
| 5 | 搬 `build_scheduler.yh` | `just build` |
| 6 | 搬 `module_build.yh`（命令面，最后搬，外部调用点最密集） | `just build` + `just test` |

每批之后跑 `just build`；全部完成后跑 `just test`（三层回归）与
`just selfhost-native`（两代固定点），再按 AGENTS.md 记 `docs/finish.md`、
删本文件、产出 `docs/01-finished/` 记录。

### 5.3 硬约束（踩了就红）

1. **同一模块内私有函数是模块级可见**：`fn`（无 `pub`）可跨文件调用——
   所以合并**不需要**改任何 `pub`。
2. **文件名字节序 = 编译顺序**，且**类型必须先定义后用**：
   `BuildCtx`、`LLVMEmitResult` 等 struct 必须排在合并文件的使用点之前（§5.1 第 1 节）。
3. **平台变体靠文件名选片**（§3.5）：`project_dir.*` 与 `cache/lock.*` 不参与合并；
   `cache/` 属 `module cache`，也不参与。
4. **`--emit-module` 子进程协议**（`build_scheduler.yh:134` 的 argv 列表）与
   `bc().iface_suffix` / `bc().compiler_fingerprint` 的跨进程语义不变；
   fork 与 Windows re-exec 两条路径都要保持可走。

### 5.4 收益与代价（诚实版）

收益：构建流程在**一个文件**里可顺读（当前 `cmd_build` → 调度 → worker →
发射分散在 6 个文件）；新读者不必在 6 个文件间跳。行为零变化、风险低
（纯搬移 + 合并 import）。

代价：单文件 2,717 行（方案 B 3,695 行），是 AGENTS.md 建议上限的 2.7–3.7 倍；
`git blame` 连续性丢失一次；后续在流程里加功能时文件会更大。
另一个代价是**历史决策反转**：`module_emit`/`module_cache` 是 2026-10-26 B2-4
主动从 `module_build` 拆出来的（见
[yh-构建态对象化与build拆分重新规划](yh-构建态对象化与build拆分重新规划-2026-10-25.md)），
本方案把它合回去。若仍要拆，建议在文件内用 `// ---- 节 n ----` 分区，
不靠文件边界。

### 5.5 待用户决定

- 选 **A（2,717 行）** 还是 **B（3,695 行）**；
- 是否接受单文件超 2.5k 行（否则本需求与「500–1000 行」规则二选一）。

---

## 6. 验证清单（实施时）

| 检查 | 命令 | 期望 |
| --- | --- | --- |
| 每批编译 | `just build` | 通过 |
| 全量回归 | `just test` | 三层（ANTLR 语法 / 语法模式 / 运行语义）全绿 |
| 自举 | `just selfhost-native` | 两代固定点 + 自解析 + 全量语料 |
| 规模核对 | `wc -l compiler/build/build_pipeline.yh`、`rg -c '^pub fn' compiler/build/*.yh` | 行数 = 各组之和，`pub` 数量不变（46） |
| 流程自测 | `tests/` 下 `.yh` 用例（按 AGENTS.md 新增一个构建流程用例） | 通过 |

---

## 7. 不做的事

- 不改 `proj` / `cache` / `hash` / `link` 的模块边界与 import 方向；
- 不动 `project_dir.*` / `cache/lock.*` 平台变体机制；
- 不顺手「改进」搬移中的代码（保持逐字搬移，便于 diff 复核）；
- 不把 `cache_admin`（`yh cache` 工具面）与 `unused_function` 拉进流程文件。
