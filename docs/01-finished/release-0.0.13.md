# 0.0.13 — `gen` 模块删除、接口发射下沉、S3a 转换校验后移

正式版。本版把 2026-11-06 立项的「`gen` 职责拆分」（ADR-0021）整条推进
到收尾：`gen` 模块被删除、每任务上下文 `TaskCtx` 归零、语义状态与纯规则全部下沉
`support`；随后完成前端两遍化的三个切片（接口发射下沉、解析器窄口、`return`/赋值
隐式转换校验后移）。种子链：0.0.12 → 0.0.13-rc.1 → 0.0.13（正式版由 0.0.12 正式版种子构建；rc.1 已按发布资产验收）。

## 主要内容

**1. `gen` 模块删除（GEN0–GEN4 + F4）**

- `support` 成为唯一无依赖底座并承接共享数据层：`ModelStore`（类型/签名/具名类型/
  符号/作用域表）、`FileScope`（模块归属 + 导入表）、`FrontCtx`（原 `TaskCtx` 的 85 个
  前端瞬时字段）、`tables`（字符串标签/枚举成员表）、`value_kernel`（隐式转换判定 +
  两个常量折叠，错误码 + 消息表）、`symbols`/`value_rules`/`layout`/`static_data`/
  `abi_model`/`front_stage`。
- 语义动作（`ty_*`/`sym_*`/`scope_*`/`fold_*`/`prelude_add`）归 `check/symbols.yh`。
- `comptime` 收窄为纯 CT 执行器：只依赖 `support` + `token`；语义事实经零拷贝镜像
  （`ct_facts` 的槽绑定）读取。
- 结果：模块 19 → 18；`gen` pub fn 82 → 0（模块删除）；`import gen` 13 → 0；
  `TaskCtx` 字段 189 → 0；依赖边 93 → 78。

**2. 前端两遍化切片**

- **S1**：接口**发射**（`iface_emit`/`iface_ct_emit`/列映射）迁
  `check/iface_emit.yh`（≈2,069 行）；`iface_load`/`iface_ct_load` 留 `parse`
  （它们要重新解析，迁走会成环）。`parse` 9,626 → 7,640 行。
- **S2a**：新增 `parse.eval_token_range` 窄口（自管 pos/`ast_capture`/`c_fold`），
  布局请求的可运行判定与依赖登记下沉 `comptime/ct_layout_sched.yh`。
- **S3a**：`return` 与赋值语句的隐式转换校验改由 `check/convert.yh` 在 AST 遍历后
  执行；位置用 `AstExpr.after`（= 解析结束游标）复现，诊断与改动前**逐字一致**。
  `parse` 7,640 → 7,577 行，`parse → check.sem_*` 142 → 140。

**3. 修复与守卫**

- 修复四个回归：CT 镜像行按值写回（布局永不完成）、`ct_tables_bind` 槽按数组基址
  传递（编译期字符串实参必崩）、切片导入计数只改视图副本（函数缓存命中后模块构建
  校验失败）、`checked_decl_restore` 复位后仍用旧视图（check-slice 段错误）。
- Windows：`vendor/windows-sdk` 的 kernel32 导出补 `SetConsoleOutputCP`/`SetConsoleCP`；
  引入 `check` 的 fixture 在零 CRT 下补 VC 运行时（避免 `strtod` 未定义）。
- `arch-check` 新增只减不增预算：`max_ct_row_field_writes`、`max_ast_view_count_writes`
  （各为 0）、`max_parse_check_calls`（140），自测 8/8。

**4. 本地构建环境与工具**

- Darwin LLVM 闭包准备不再需要手工 `SDKROOT`：`resolve_sdk_root` 依次尝试显式
  `SDKROOT` → `xcrun` 默认 → `/Applications/Xcode*.app/**/MacOSX*.sdk`（新→旧），
  自动跳过含 `arm64e.x1` 的 SDK 26.5 不兼容项；磁盘不足时给出可清理路径。
- `tools/py`：统一挑 ≥3.10 的解释器；SDK「构建器源码变了但产物没变」时只重写身份
  记录，不重编 LLVM。
- `just fetch-seed` 在本地从 `git remote` 推断 `owner/repo`，不再需要 `GITHUB_REPOSITORY`。

## 验收

- `just test`：371→372/374（2 例平台跳过）；`fail` 140/140；`pass` 10/10；
  compiler-tests 8/8；`arch-check` 8/8。
- `just selfhost-native`：模块固定点一致、cc4 自解析 178 文件、project cases 129/129
  （linux 140/140、windows 135/135）。
- 迁移等价性：`comptimecross` 的 8 个 `.s.i`/`.s.ct` 与迁移前逐字节一致；
  S3a 的 4 个探针（return/赋值 × 窄化/指针）诊断逐字一致。
- CI：`llvm` 分支在本次发布前连续四端全绿。

## 已知限制

- 前端两遍化只做了 S1/S2a/S3a 两片；`parse` 仍 import `check`，因此「布局调度整体
  下沉 `check`」仍不可行。架构将重新设计，分析与 spike 见
  `docs/01-finished/yh-前端两遍化-重新分析-2026-11-08.md` 与
  `docs/01-finished/yh-S3-语义字段外置spike-2026-11-08.md`。
- `support` 体积增大（2,740 → 3,200+ 行）是本次下沉的直接代价，重设计时是首要整理对象。

## 从 rc.1 到正式版

rc.1 已作为预发布发布并用其资产完成四点验收（`rm -rf bin && just fetch-seed` →
`just` → `just test` → `just selfhost-native` 全绿）。正式版内容与 rc.1 一致，
仅版本号去掉 `-rc.1`；本轮新增的唯一修复是发布工具链本身
（`tools/llvm-darwin-sdk.py` 在 `runpy.run_path` 下缺 `sys.path` 引导导致 Darwin 门禁
`ModuleNotFoundError`）与 LLVM 闭包身份改配方摘要（`just llvm-host` 30 分钟 → 1 秒）。
