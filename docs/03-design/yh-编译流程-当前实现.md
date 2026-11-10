# yh 当前编译流程（`yh build` 参考）

修改时间：2026-11-08

状态：**当前实现参考**，不是目标架构。
基线：`llvm` 分支 0.0.12 + C0–C6 + GEN1–GEN4 + F4，18 个 yh 模块（`gen` 已于 2026-11-07 删除），LLVM 唯一后端。
用途：作为调整编译流程时的逐阶段对照表；目标架构见
[架构设计](yh-架构设计.md) 与 `docs/todo.md` 的 S1–S4（前端两遍化切片）/
GEN0–GEN4（`gen` 拆分，已完成）。原 F0–F7 计划已于 2026-11-08 重估，见
[重新分析](../02-plan/yh-前端两遍化-重新分析-2026-11-08.md)。

> 本文只描述 `yh build`（项目构建）。`yh check`、`yh run`、`yh test`、
> 单文件编译的差异见 §10；自举流水线见 §13。

---

## 0. 一屏总览

```text
yh build
  → cmd/yh/yh.yh                  argv → CliRequest → 分派（module main）
  → cmd/yh/cmd_build.yh           yh build / yh check
  → build.cmd_build
      → load_stdlib            加载标准库项目（若存在）
      → pro_find_root              向上找 project.toml
      → load_project           清单 + 依赖 + 源码扫描 + 模块索引
      → pj_bind_imports           本项目 → 标准库 → 直接依赖
      → pj_entry_mod / pj_topo    根模块与依赖序
      → proj.build_dir            构建目录
      → mb_schedule_modules       有界进程池 + InterfaceReady
          → mb_compile_start      模块缓存检查
          → fork/COW worker 或 --emit-module 子进程
              → 受检前端（pass1 / CT / layout / globals / pass2b）
              → check.verify_module（结构校验）
              → CheckedModule 快照
              → lower → IRModule
              → backend → LLVM 文本
              → 内嵌桥 → obj/<tag>.o
          → 父进程发布接口 + 模块 manifest
      → link.mb_link
          → prepare → objects → key → args → libs → exec
      → 输出 .build/<project.name>（或 -o 路径）
```

---

## 1. 调用链速查

| 阶段 | 入口 | 关键产物 |
| --- | --- | --- |
| CLI | `cmd/yh/yh.yh::main` | `main.CliRequest`（`cmd/yh/cmd_base.yh`） |
| 命令 | `cmd/yh/cmd_build.yh::api_build` | `build.cmd_build(...)` 调用 |
| 会话 | `cmd/yh/common.yh::cmd_session_init` | `support.session()`/`proj`/target/argv0/envp |
| 项目 | `build/module_build.yh::cmd_build` | `proj.ProjectCtx` 表 |
| 装载 | `build/project_index.yh::load_project` | 项目/模块/文件/依赖 |
| 导入 | `build/project_resolve.yh::pj_bind_imports` | `imp_mod[]` 绑定 |
| 拓扑 | `pj_topo` / `pj_topo_multi` | `proj.ctx().order[]` |
| 调度 | `build/build_scheduler.yh::mb_schedule_modules` | worker 状态/接口就绪 |
| 单模块 | `build/module_worker.yh::mb_emit_indexed_module` | `.o` / `.s.i` / `.s.ct` / manifest |
| lower | `build/llvm_pipeline.yh::llvm_prepare_module_cached` | `ir.IRModule` |
| 后端 | `backend.llvm_emit_module` | LLVM 文本 |
| 桥 | `llvm_emit_publish` | `obj/<tag>.o` |
| 链接 | `link/link_cache.yh::mb_link` | 可执行文件 + `link.manifest` |

---

## 2. 入口与会话

### 2.1 `cmd/yh/yh.yh`（module main）

`main(argc, argv, envp)`：

1. `support.console_utf8_init()`：Windows 控制台切 UTF-8。
2. `support.argv_utf8_rebuild()`：Windows 用宽命令行重建 UTF-8 argv。
3. `cmd_session_init()`：
   - `support.state_init()` 恢复 `support` 表的非零初始值；
   - `proj.init()` 初始化项目模型；
   - `support.bind_cfg(proj.cfg())` 绑定目标/配置；
   - `build.mb_set_argv0()`；
   - `proj.ctx().envp = envp`。
4. 内部子进程协议：
   - `--emit-module`：无 fork 宿主的模块 worker；
   - `--lld-link`：Windows COFF 链接 worker。
5. `main.parse_request()`（`cmd/yh/cmd_base.yh`）：`argv → CliRequest`。
6. 全局选项落状态：
   - `--target` → `support.target_select()`，并置 `target_explicit`；
   - `--opt` → `proj.cfg().opt_level`；
   - `--emit-llvm` → `proj.cfg().emit_kind = 1`（仅 build；额外保留 `.ll`）；
   - `--emit-asm` → `proj.cfg().emit_asm = 1`（仅 build；额外保留 `.s`）；
   - `--trimpath` → `proj.cfg().trimpath = 1`（IR/CT 来源使用项目相对路径）；
   - 统计输出已于 2026-11-10 删除（`support.stats()`/`--stats` 均不存在）；
   - `--backend legacy` 直接拒绝（LL12 后 LLVM 唯一）。
7. 按命令分派：`build` → `api_build()`，`check` → `api_check_project()`，
   `cache` → `api_cache()`（`info/clean/trim/verify`）。

### 2.2 `cmd/yh/cmd_build.yh`

```text
api_build(req)
  → build.cmd_build(req.out, req.src, req.has_src, req.links[0..])
```

`yh check` 走同一函数，只把 `gs.c_check_only = 1`。

---

## 3. 项目装载

### 3.1 `cmd_build` 的前半段

`compiler/build/module_build.yh`：

1. `mb_resolve_self_path()`：定位自身可执行文件，供编译器指纹使用。
2. `link.li_select_reset()` + `mb_select_links(links)`：登记 `--link` 组名。
3. `yh check` 不允许 `--link`。
4. `load_stdlib()`：按可执行文件附近布局加载标准库：
   - `<exe_dir>/libs`；
   - `<exe_dir>/../libs`；
   - `<exe_dir>/../share/yh/libs`。
5. `pro_find_root(0, &len)`：从当前目录向上找 `project.toml`。
6. `proj.set_root_project(root, len)`。
7. `load_project(root, len)`：递归装载项目。

### 3.2 `load_project`

`compiler/build/project_index.yh`：

1. `proj.find_project_root()`：重复装载/依赖环检测。
2. `proj.add_project()`：登记项目。
3. 读 `<root>/project.toml`，`build/toml.yh` 解析。
4. 校验 `[project]`：
   - `name` 必填且为标识符；
   - `source` 默认 `src`；
   - `os`/`arch` 目标配置；
   - `version`/`author`。
5. 装载 `[dependencies]`：递归 `load_project()`，检测环与重复。
6. 装载 `[link]` / `[link-<os>-<arch>]` / `[c]` / `[env]`（都在 `[dependencies]`
   递归之前快照，子项目会重置 TOML 解析区）。
7. `pj_scan_source()`：扫描源码根：
   - 跳过 `.build`/`tmp`/隐藏目录等；
   - 按目标过滤平台文件；
   - 对每个 `.yh` 调 `lex.lex_all()` + `parse.mod_parse_head()` 读模块头；
   - `module` 名相同的源码合并成同一模块；
   - 文件按文件名序保存（类型必须先声明后使用）。
8. 扫描期保存每个文件的只读源/token/声明快照；fork worker 通过 COW 继承。

### 3.3 `pj_bind_imports`

`compiler/build/project_resolve.yh`：

- 第 0 层：`KEY.MOD` 跨项目限定导入；
- 第 1 层：本项目；
- 第 2 层：标准库；
- 第 3 层：直接依赖（排除入口模块；多个候选 = 歧义）。

检查：

- 依赖键不存在；
- 入口模块不可作为库导入；
- 导入名歧义；
- 导入未使用（后续在函数文件编译后检查）。

### 3.4 根模块与拓扑

```text
显式模块参数 → 本项目模块
否则          → pj_entry_mod(pj)（module main）
都没有        → 库项目（无入口，不链接）
```

- 有入口：`pj_topo(rootmod)`；
- 库项目：`pj_topo_multi(pj)`。

结果写入 `proj.ctx().order[]`，提供方在前。

### 3.5 构建目录

`proj.build_dir(root, len, &len)`：

| 模式 | 目录 |
| --- | --- |
| 生产构建 | `<cache_root>/targets/<triple>/llvm/O<opt>` |
| `yh check` | `<cache_root>/check` |
| `yh test` | `<root>/tmp/yh-test/check` |

`cache_root` 默认 `<root>/.build`；`YH_BUILD_CACHE` 可迁到项目外。
默认可执行文件仍在 `<root>/.build/<project.name>`，不随缓存根移动。

---

## 4. 调度与模块缓存

### 4.1 `mb_schedule_modules`

`compiler/build/build_scheduler.yh`：

- worker 上限默认 4；`YH_WORKERS=1..32` 可覆盖。
- 为本次构建生成 session 后缀 `.session-<pid>`，隔离临时接口。
- 状态数组：
  - `0` 未开始；
  - `1/2` 已启动；
  - `3` 完成；
  - `4` 失败。
- 每轮：
  1. `mb_sched_refresh_interfaces()`：刷新接口就绪；
  2. `waitpid()` 回收 worker；
  3. 成功 worker：
     - `mb_sched_publish_interface()` 发布持久接口；
     - `mb_manifest_commit()` 提交模块 manifest；
     - 打印 `[编译] <module>`；
  4. 未开始模块：
     - `mb_sched_deps_ready()` 检查依赖接口；
     - `mb_compile_start()` 检查缓存/启动 worker；
  5. 任一失败：停止派发、取消运行中 worker、不进入链接。

InterfaceReady 可以在提供方私有函数体完成前发布，消费者提前开始。

### 4.2 `mb_compile_start`：模块缓存

`compiler/build/module_emit.yh`：

键包含：

- 本模块全部源文件内容；
- 依赖 `.s.i` / `.s.ct` 内容；
- target triple / data layout / ABI；
- `O0/O2`；
- 编译器自身二进制的 SHA-256 内容身份（C2，每进程一次）；
- LLVM 桥版本与桥 ABI；
- Darwin 部署目标/PIC；
- `yh test` 的测试选择摘要（仅测试模式）。

检查四个产物：

```text
obj/<tag>.o
iface/<tag>.s.i
iface/<tag>.s.ct
manifest/<tag>.manifest
```

manifest 记录模块键、对象摘要、接口摘要。全部匹配：

```text
[缓存] <module>
```

直接返回 `1`（已完成），不启动 worker。否则返回 `0`，启动 worker。

### 4.3 worker 启动

`mb_spawn_indexed_module()`：

| 宿主 | 行为 |
| --- | --- |
| Linux/macOS | `fork()`，COW 继承父进程只读项目/token 快照；子进程执行 `mb_emit_indexed_module()`，成功后 `exit(0)` |
| Windows/无 fork | `--emit-module` 一次性子进程，重新装载项目并索引 |
| `YH_NO_FORK=1` | 进程内串行测试路径（仅探针） |

worker 会检查父进程存活，避免 Ctrl-C 后留下孤儿。

---

## 5. 单模块 worker

`mb_emit_indexed_module(m, main_off, main_len, out_dir, ir_cache_salt)`
（`compiler/build/module_worker.yh`）。

### 5.1 前端初始化

1. `support.front_checked_begin()`：进入受检前端模式。
2. `comptime.ct_reset()`：清空编译期状态。
3. 设置：
   - `proj.cfg().module_mode = 1`；
   - `proj.cfg().is_entry_mod`；
   - 模块符号后缀 `c_sym_sfx_off/len`。
4. `check.sem_init_tables()`：建立类型/符号/常量表（原 `gen.sem_init_tables`）。
5. `builtin.front_prepare()`：登记 prelude。
6. `mb_module_iface_deps()`：收集依赖 `.s.i` / `.s.ct` 路径。
7. 加载依赖接口：
   - `parse.iface_load()`；
   - `parse.iface_ct_load()`；
   - `parse.pub_agg_deferred_run()`：导入侧延迟的 pub 聚合常量。

### 5.2 文件级声明索引

对模块每个文件：

```text
mb_restore_front_file()   恢复父进程保存的源/token/声明快照
mb_file_head_bind()       绑定 module/import
parse.decl_index_file()   建顶层声明索引
ast.ast_decl_add_file()   把声明挂到 AST
```

### 5.3 pass1：登记声明

```text
mb_pass1_file()
  → mb_restore_front_file
  → mb_file_head_bind
  → parse.parse_indexed_decls(0)
```

pass1 登记：

- 类型/结构体/联合体/枚举；
- 函数签名；
- 全局名字；
- 顶层声明索引。

函数体与全局初始化表达式在 pass1 中整块跳过。

之后：

- `ast.ast_decl_bind_file()`：声明与导入绑定到 AST；
- `mb_check_binding_clash()`：导入名与本模块顶层声明重名；
- 入口模块 `check.sem_check_main()`（测试模式允许无 main）；
- `unused_function_report()`：UF1 未使用私有函数检查。

### 5.4 编译期展开 / 布局 / 全局初始化

**当前不是独立 AST 阶段**，而是在 parse 文件子遍里完成：

1. `mb_pass2_file(..., 2)`：捕获/检查 `@[comptime]` 函数正文。
2. `mb_pass2_file(..., 3)`：登记 CT 布局请求。
3. 循环：
   - `mb_pass2_file(..., 4)`：求值布局 const；
   - `parse.parse_source_ct_layout_exprs()`；
   - `comptime.ct_layout_advance()`；
   - 直到没有 pending；检测 stuck。
4. `comptime.ct_layout_resolve()`。
5. `parse.ct_enum_pending_run()`：延迟枚举判别值。
6. `mb_pass2_file(..., 1)`：全局初始化，登记 ST/CT 数据。

### 5.5 发布模块接口

在函数体 pass2b 之前：

```text
parse.iface_ct_emit()   → .s.ct
parse.iface_emit()      → .s.i
mb_iface_write_ready()  → .ready
```

依赖方可以在此后开始，不必等私有函数体完成。

### 5.6 pass2b：函数体

1. `firc_check_load()`：装载函数级 check 缓存（check-only / test 不装载）。
2. `ast.checked_check_cache_begin()`。
3. 对每个文件：
   - `mb_pass2_file(..., 0)` → `parse.parse_source_fns()`；
   - 解析函数体，同时调用 `check.sem_*`（原 `gen.sem_*`）做类型检查/符号绑定/常量折叠；
   - 写 AST arena；
   - 命中 check 切片的函数跳过重解析。
4. 未使用导入检查。
5. `ast.checked_check_cache_end()`。
6. `yh test` 额外用 mode 5 解析测试体。

### 5.7 结构校验

```text
ast.ast_view(&view)
check.verify_module(&view)
```

当前 `check` 只做结构校验：

- 表达式范围/子节点；
- 语句树；
- 声明；
- 函数上下文。

**它不是类型检查器**；类型检查仍在 `parse` + `check.sem_*`（原 `gen.sem_*`）。

### 5.8 check-only 分支

`yh check` / `--check-only`：

```text
support.front_checked_verify()
ast.checked_module_capture()
mb_verify_checked_snapshot()
ast.checked_module_release()
support.front_checked_end()
```

返回，不 lower、不 LLVM、不链接。

### 5.9 lower → IR

正常构建：

```text
ast.ast_view()
check.verify_module()
support.front_checked_verify()
ast.checked_module_capture()      → CheckedModule 快照
mb_verify_checked_snapshot()
firc_load()                       → 函数级 IR 缓存
firc_env_key()
llvm_emit_module_to_cached()
```

`llvm_emit_module_to_cached()` 内部：

1. `lower.lower_module_cached()`：`CheckedModule → IRModule`，按函数命中 IR 缓存。
2. `backend.llvm_emit_module()`：`IRModule → LLVM 文本`。
3. `llvm_emit_add_deployment_metadata()`。
4. 可选写 `.ll` 文本（`build --emit-llvm` / 审阅）。
5. 可选再调用一次桥写 `.s` 汇编（`build --emit-asm`；对象已发布后追加）。

### 5.10 内嵌桥 → 对象

`llvm_emit_publish()`：

1. 写临时文件 `<out>.tmp.<pid>`。
2. `llvm_emit_with_target()` 调用内嵌 LLVM 桥：
   - 解析 LLVM 文本；
   - O0/O2；
   - 生成目标对象。
3. `link.mb_object_machine_matches()` 校验对象架构。
4. `rename()` 原子发布：

```text
obj/<project>-<module>.o
```

5. 成功后：
   - `firc_check_commit()`；
   - `firc_commit()`；
6. `support.front_checked_end()`。

---

## 6. 父进程提交与链接

### 6.1 模块提交

worker 成功后父进程：

1. `mb_sched_publish_interface()`：持久 `.s.i` / `.s.ct` / `.ready`。
2. `mb_manifest_commit()`：提交模块 manifest。
3. 所有模块成功 → 链接。

### 6.2 输出路径

- `-o <out>`：用户路径；
- 未指定：`<root>/.build/<project.name>`。

### 6.3 `link.mb_link`

`compiler/link/link_cache.yh` 六段：

1. **prepare**
   - 选链接器；
   - 检查自举闭包 `YH_LLVM_SELFHOST_FLAGS`；
   - 装配 C 项目输入；
   - 编译 `[c].sources`；
   - 准备 `--link` 组。
2. **objects**
   - LLVM 模式下 worker 已发 `obj/<tag>.o`，这里只登记/校验；
   - 不再执行汇编。
3. **key**
   - 链接键：链接器/工具身份、target/ABI、优化级别、输出路径、对象内容、
     `--link` 库、lld/COFF 身份等；
   - 命中 `manifest/link.manifest` 且输出摘要一致 → 跳过链接。
4. **args**：统计对象行数，装配 argv。
5. **libs**：`[link]` / `[link-<os>-<arch>]` / `[c].libs` / 运行时/系统库。
6. **exec**
   - 内嵌 lld worker / COFF worker / Mach-O worker；
   - 校验产物架构/Darwin 签名；
   - `rename()` 原子发布；
   - 写 `manifest/link.manifest`。

### 6.4 库项目

没有 `module main`：

- `pj_topo_multi()` 构建全部库模块；
- worker 发对象/接口；
- 不链接；
- 输出：

```text
库构建完成（模块对象与接口在 <build_dir>）
```

---

## 7. 产物与缓存布局

```text
<root>/.build/
  <project.name>                         # 默认可执行文件
  targets/<triple>/llvm/O<opt>/
    iface/<project>-<module>.s.i
    iface/<project>-<module>.s.ct
    iface/<project>-<module>.ready
    obj/<project>-<module>.o
    llvm/<project>-<module>.ll           # build --emit-llvm / 审阅
    asm/<project>-<module>.s             # build --emit-asm / 审阅
    manifest/<project>-<module>.manifest
    firc/<project>-<module>/...          # 函数 check/IR 缓存
    manifest/link.manifest               # 链接缓存键/摘要
  check/...                              # yh check
  tmp/yh-test/check/...                  # yh test
```

`YH_BUILD_CACHE=<dir>` 迁移中间缓存树；默认可执行文件仍在 `.build`。
C4 起 `YH_CACHE` 指向全局 content store（默认平台缓存目录，`off` 关闭），
模块/函数中间产物按 ActionID 发布；本地 `.build/index/<tag>` 只存 ActionID。

---

## 8. 缓存层次

| 层 | 位置 | 键 | 命中效果 |
| --- | --- | --- | --- |
| 模块接口/对象 | `iface/`、`obj/`、`manifest/` | 源文件 + 依赖接口 + target/ABI/opt + 编译器指纹 + 桥版本 | 跳过 worker |
| 函数 check 切片 | `firc/...` `.fchk` + `index.check` | 函数 token 流 + 布局/签名事实 | 跳过函数重解析/重检查 |
| 函数 IR | `firc/...` `.fir` + `index` | 上述 + 环境键 | 跳过 lowering |
| 链接 | `manifest/link.manifest` | 工具/lld 身份 + target + 对象 + 输出 + 库 | 跳过 lld |
| 全局 store | `$YH_CACHE/v1/{actions,outputs}` | ActionID + OutputID（SHA-256） | 跨目录复用中间产物 |
| 测试 | `tmp/yh-test` | 模块键 + 测试选择摘要 | 仅测试构建 |

缓存原则：

- 只有模块完整成功后才提交模块 manifest/接口；
- 函数缓存只在模块成功后提交；
- 失败/中断不发布成功标记；
- 链接输出 `rename` 原子发布；
- `check-only` 不读写正式构建缓存。

---

## 9. 错误与原子性

- `tk.c_errors > 0` 立即停止当前模块。
- worker 失败：父进程停止派发、取消运行中 worker、不进入链接。
- 对象：临时文件 + 架构校验 + `rename`。
- 接口/manifest：临时文件 + `rename`。
- 链接：临时文件 + 架构/签名校验 + `rename`。
- 不发布“部分成功”的模块 manifest 或链接清单。
- worker 定期检查父进程存活，避免孤儿进程。

---

## 10. 命令变体

| 命令 | 与 `yh build` 的差异 |
| --- | --- |
| `yh build` | 完整构建 + 链接；有入口时产可执行文件 |
| `yh build`（库项目） | 无入口；只发模块对象/接口，不链接 |
| `yh check` | `c_check_only=1`；只做前端 + 结构校验/快照校验；不 lower、不 LLVM、不链接；清 check 接口 |
| `yh run` | 与 build 相同；要求 target=host；链接后 `cmd_process_run()` 执行，返回程序退出码 |
| `yh test` | `testkit` 驱动；构建目录 `tmp/yh-test`；模块键含测试选择；不装载/提交函数缓存；测试体 mode 5 |
| 单文件 `yh f.yh -o` | 走 `cmd_single` + `llvm_emit`，不复用项目 module worker |

---

## 11. 当前边界与调整点

| 边界 | 当前事实 | 调整时看这里 |
| --- | --- | --- |
| 前端阶段 | `parse` 边解析边做语义动作并写 AST | `parse_*`、`check.sem_*`（原 `gen.sem_*`）、`ast.ast_expr_set_semantics` |
| `check` | 只读结构 verifier | `check/verify.yh`、`mb_emit_indexed_module` 的 verify 段 |
| CT 展开 | 在 parse 文件子遍中完成 | `parse_comptime`、`parse_ct_layout`、`mb_pass2_file` mode 2–4 |
| `gen` 耦合 | 已消除（2026-11-07 `gen` 删除）：token/类型/状态/基础设施/target 分散到 `support`/`check`；越界靠评审（`arch-check` 2026-11-09 已删除） | `support/*`、`check/symbols`、`check/ct_bind` |
| 状态 | `TaskCtx` 字段 0；会话状态集中在 `support.session()`（`SessionCtx`），模块级可变 `let` 203 | `support/base.yh`、`state_init`、worker 初始化 |
| 接口 | `.s.i`/`.s.ct` 读写仍在 `parse` | `parse/iface*`、`mb_*_emit` |
| 项目模型 | `proj` 只读；`build` 负责装载/扫描 | `build/project_index`、`proj_*` |
| 缓存 | 模块/函数 check/函数 IR/链接分散 | `build/module_cache`、`function_ir_cache`、`link/link_cache` |
| 平台 | 平台文件按后缀复制 | `clock.*`、`project_dir.*`、`argv.*`、`console.*` |

---

## 12. 调整对照表（原 F0–F7 / GEN0–GEN4 的历史对照）

2026-11-08 已把前端两遍化重估为 S1–S4。本表按原计划保留作历史对照；
现行切片、规模与验收见 `docs/todo.md` 与
[重新分析](../02-plan/yh-前端两遍化-重新分析-2026-11-08.md)。

| 调整 | 会动的阶段 | 对应 todo |
| --- | --- | --- |
| parse 只出语法 AST | §5.2–5.6 的 pass1/pass2、AST 写入、`check.sem_*` | F1–F2 |
| check 接全部语义 | §5.7 的 verify、`check.sem_*` 去向、`CheckedModule` | GEN2 / F1–F5 |
| CT 展开独立 | §5.4 的 mode 2–4、`parse_comptime`、`parse_ct_layout` | F4 |
| AST/HIR/CheckedModule 分层 | §5.2、§5.7、§5.9；HIR 留在 `check`，不建模块 | F1/F5/F6 |
| token 词汇/`PDecl`/状态/`err_tok` 归 token | `gen/model` 的 `TK_*`/`Tok`/`PDecl`、`c_pos`/`c_toks`、lex/parse/ast/proj | GEN1 |
| 语义模型/规则归 check | `gen/symbols`、`CType/CSym/TY_*`、`sem_*` | GEN2/F5 |
| TaskCtx 拆分 | §1.1 会话、§5.1 worker 初始化 | GEN1/GEN2/GEN4 |
| support 落地（工具/诊断/目标/ABI 常量） | §2.1、§3、§5、§6 | GEN1 |
| `fail`/`err_lc` 同归 support，不拆 diag | §5 诊断、`buffer.yh` | GEN1 |
| gen 删除 | 全部 import gen 的调用面 | GEN4（已完成 2026-11-07） |
| cache 收拢 | §4.2、§5.6、§5.9、§6.3 | 11-05 目标/后续 |
| iface 移出 parse | §5.1、§5.5、§5.6 | F2/F3 |

---

## 13. 自举流水线（参考）

`just selfhost-native` 不直接复用上面的项目构建命令，而是：

```text
bin/yh-<平台>-<架构> build compiler/ → cc2
cc2 build compiler/ → cc3
cc3 build compiler/ → cc4
门：cc3/cc4 全部模块 .s/.s.i 逐字节相同
    + cc4 自解析全部 compiler/ 源文件
    + 全量语法/运行语料
    + modules/项目验收
```

种子不入库；`just fetch-seed` 从 Release 下载。LLVM/lld 闭包由
`just bootstrap`/`just llvm-host` 准备。

---

## 14. 调整时必须保持的不变量

1. **模块内文件按文件名序编译**，类型先声明后使用。
2. `pub` 同时决定 `.s.i` 接口与 `.globl`；私有类型不得出现在 `pub` 签名。
3. worker 通过 COW 继承只读项目快照；`proj` 不在 worker 中改写。
4. `CheckedModule` capture 后不再修改；lower 前必须 verify。
5. 模块/函数/链接缓存只在完整成功后提交；失败不发布成功标记。
6. 对象/接口/链接产物用临时文件 + `rename` 发布。
7. InterfaceReady 可以早于提供方私有函数体完成，但完整模块失败不得让消费者成功。
8. 每个行为变更补 `tests/yh-run/` 或 `tests/modules/` 用例。
9. 每阶段 `just` + `just test` + `just selfhost-native`；纯移动阶段要求
   `.s`/`.s.i` 逐字节一致。
10. 新增/变更模块依赖必须同步更新 `docs/03-design/yh-架构设计.md` §3.1 的允许边
   （原 `ALLOWED` 表随 `tools/arch-check.py` 于 2026-11-09 删除）。

---

## 15. 关键代码位置

| 内容 | 文件 |
| --- | --- |
| CLI/分派 | `compiler/cmd/yh/`（`yh.yh`、`cmd_base.yh`、`cmd_build.yh`、`common.yh`） |
| 项目装载 | `compiler/build/project_index.yh`、`project_resolve.yh`、`toml.yh`、`proj/` |
| 调度 | `compiler/build/build_scheduler.yh` |
| 模块构建 | `compiler/build/module_build.yh`、`module_emit.yh`、`module_worker.yh` |
| 模块缓存 | `compiler/build/module_cache.yh`、`function_ir_cache.yh` |
| LLVM 流水线 | `compiler/build/llvm_pipeline.yh`、`llvm_emit.yh`、`backend/` |
| 语言 IR | `compiler/ir/`、`compiler/lower/` |
| 结构校验 | `compiler/check/verify.yh` |
| 链接 | `compiler/link/link_cache.yh`、`link_inputs.yh`、`darwin_link.yh`、`windows_link.yh` |
| 测试 | `compiler/testkit/test_cmd.yh` |
| 架构目标 | [yh-架构设计.md](yh-架构设计.md) |
