# finish

滚动日志：只保留最近三天（当前为 2026-11-01 ～ 2026-11-03）的交付记录，靠前条目为最新状态。
更早的 475 条（2026-09-27 ～ 2026-10-25）已归档在
[finish 历史归档](01-finished/finish-历史归档-2026-09-27至2026-10-21.md)（归档文件按批追加，标题保留首批日期区间）。
超出窗口的条目迁入同一个归档文件，新增条目写在最前。

2026-10-28 起同时收录主工作区性能 WIP 分支（`tmp/main-wip-20261028`）的条目；
2026-10-25 及更早的条目仍只在归档文件里。

## 2026-11-03 合入 ci/github-actions（GitHub Actions 四端 CI + Windows 闭包可重定位）

**结果**：`llvm` 合并 `ci/github-actions`（合并提交 `9e00b85`）。换来的是 CI 从
Gitea Actions 迁到 GitHub Actions（`.github/workflows/{ci,release,perf}.yml`，
`.gitea/` 删除）、新增 `tools/llvm-windows-closure.py`（可重定位闭包）与
`tools/ci-bootstrap.py`（过渡期自举桥）。

- **冲突 1 处（`justfile` 的 `tmpdir`）**：两边都修了同一件事（Windows 上
  `absolute_path("/tmp")` 会变成不存在的 `C:\tmp`）；取 CI 线的顺序（Windows 优先
  落仓库 `tmp/`），因为它多了实测理由——Windows 上的编译器只能编仓库内项目，
  workdir 在 `%TEMP%` 会报「无法创建构建目录」。
- **合并后去重**：`cmd/api.yh` 的 `--emit-module` 子进程里 `--emit-llvm` 有两个
  完全相同的分支（两条线各自修过同一处），只保留一个。
- **W2-2 的绝对路径消失**：`compiler/project.toml` 的 `[link-windows-x64]` 改为
  `../tmp/llvm-migration/windows-llvm-closure/{bridge,lld,llvm,support}/…`，
  不再夹本机 `C:/…` 与 `D:/tmp/llvm-win/…`。

### 合流后必须重建闭包（未完成，已记 todo）

新的 4 组布局需要先 `just llvm-host` 产出：本机直接 `just build` 会报
“无法读取库文件（组 bridge/lld/llvm）”（旧布局在 `tmp/winhost/` 与
`D:/tmp/llvm-win/build/Release/lib`，新清单不再读它）。用
`YH_LLVM_WINDOWS_WORK=D:/tmp/llvm-win` 可复用已有 CMake 树，避免重编 LLVM。
**因此 `9e00b85` 本身未在本机做过构建与门禁验证**，验证统一在主工作区完成。

### 随之关闭的 Windows 红门（原写在本条下方的 todo 列表里）

由 `ab87713`（合并期）与 `34ee381`（收口）两笔提交关闭：

| 旧问题 | 关闭依据 |
|---|---|
| testkit 断言行号成为编码残值、崩溃归类错 | `__yh_chkstk` 保存 r10/r11（LLVM 不建模探测的寄存器破坏）；「崩溃」夹具改用 getpid 派生地址 |
| `--emit-asm` 的 stdout 路径在 Windows 失败 | `--emit-asm` 落 TEMP/TMP/当前目录 |
| `libs-test` 的 `net` 模块 `--emit-module --test-mode` worker -1 | 新增 `libs/net/20_tcp.windows.yh`（真的调 `sys.socket_fd`，不伪造成功） |
| `os6-default-stdlib` / `os4-os-process-win` 失败 | 默认标准库双分隔符切分、`__yh_build_envp` 堆越界修复 |
| `runtime-memory.py` 自编超 120s | Windows 跳过外部 `nm` 导入审计 |

## 2026-11-03 合并后收口：envp 堆越界、默认标准库发现、门禁路径引号

**结果**：Windows/x86_64 上双主门同时全绿：`just test` **rc=0**（语法 82/82、反例
49/49、运行 363/372（跳过 9）、fail 138/138、pass 10/10、libs 133/133、
compiler-tests 4/4、arch-check 通过），`SKIP_CORPUS=1 just selfhost-native` **rc=0**
（project cases **130/130**，两代模块固定点 cc3→cc4 共 48 个产物逐字节一致）。

### 3 个真缺陷

1. **`__yh_build_envp` 越界一个指针位**（`compiler/windows-sdk/chkstk.c`）：首版按条目数
   分配 `count` 个槽却写 `envp[count] = 0`。子进程启动即损坏堆（`0xC0000374`），
   而且在 O0 时**不一定当场崩**，于是表现为三类看似无关的随机失败：
   `os.spawn(argv[0], argv, envp)` 访问违例 `3221225477`、`yh test` 大量用例
   「崩溃或缺少结果记录」（记录文件只剩 4 字节魔数、甚至完全不落盘）、
   并行 `build-check` 的冷热构建偶发 `rc=1`。定位手法：用 C 夹具把 `yh test` 的
   子进程改成手工 `CreateProcessA`（自定义环境块）复现——子进程打印完首行即以
   `0xC0000374` 退出。修法：两趟扫描（先数条目、再按序填）并分配 `count + 1`。
2. **默认标准库发现在 Windows 上恒失败**（`compiler/build/module_build.yh`）：
   `mb_load_default_stdlib` 只按 `/` 切可执行文件路径取 exe 目录，但 Windows 的
   `argv[0]` 是 `C:\...\bin\yh` 形式，`cut` 落到 0、`dir` 退化成 `.`，于是
   `<exe>/libs`、`<exe>/../libs`、`<exe>/../share/yh/libs` 三个候选全部落空
   （`install` 布局与 `bin/` 种子旁布局都走不通，只有显式 `YH_STDLIB` 才能用）。
   修法：切分同时认 `'/'` 与 `'\\'`。
3. **justfile 的 `--workdir` 未 `quote()`**：Windows 路径带反斜杠，直接拼进 recipe
   会被 shell 当转义符吃掉，Python 收到 `C:UsersAdministrator...` 这种相对路径，
   于是在仓库根建出 `UsersAdministratorAppDataLocalTempyh-fast-…` 垃圾目录
   （两个 worktree 都有）。修法：`run_work_flag`/`modcheck_work_flag` 走 `quote()`
   （与 `selfhost_work_flag` 一致），并清掉已生成的垃圾目录。

### 门禁侧调整

- `tests/modules/build-check.py`：`default-stdlib-run` 的安装布局在 Windows 上
  额外复制 `<exe>/windows-sdk`（`YH_WINDOWS_SDK` 优先，否则闭包缓存目录），
  否则装好的编译器只报「找不到 Windows 导入库」，默认发现无法验证。
- `tools/arch-check.py`：`max_build_lines` 6946 → 6949（默认标准库分隔符修复）。
- `justfile`：`tmpdir` 在 Windows 缺省落 `<repo>/tmp`——just 的 `absolute_path()`
  会把 `/tmp/yh-fast-x` 折成 `C:\tmp\yh-fast-x`，而该目录不存在，`stage-yh` 的
  `cp` 直接失败（Linux/macOS 不受影响）。

## 2026-11-03 合并 W2（Windows 原生宿主 + 标准库平台变体）到主线 llvm

**结果**：`llvm-2` 的 Windows 工作以合并提交 `ab87713` 合入 `llvm`
（父：`cc5f7dc` W2 分支 + `67c4f6a` 主线 0.0.11/B2/NP3），主工作区 `Desktop/x`
前移到同一点。合并后在 Windows 上 `just test` 重新全绿，两代固定点
`ca4b1aee02a64d58…` 逐字节相同。

### 冲突与语义重对齐（17 个文件）

- **`ct_target.yh`（最关键）**：自动合并把 `windows` 分支并进了 `arm64`，`$if (windows)`
  因此恒为假——主线会静默丢掉全部 Windows 路径，自编出的编译器 `fork()`/spawn 全部
  失效（表现为「无法启动模块编译 worker」且无任何诊断）。恢复分支链后自举立即恢复。
- **`build/link_cache.yh` → `link/link_cache.yh`**：主线把 `mb_link` 阶段化
  （`LinkPlan` + prepare/objects/key/args/libs/exec）。Windows 链接按阶段接入：
  `use_coff` 与 SDK 输入在 prepare、COFF 前缀在 args、身份哈希在 key、
  `mb_coff_link_worker` 在 exec。`windows_link.yh` 从 `build` 迁到 `link`
  （`mb_link` 在 link，反向依赖成环），并新增 `mb_coff_link_single` 给单文件链接用。
- **`module_build` → `module_emit`**：`--emit-module` 子进程自己装载主项目、重建
  拓扑序、标入口模块；`--no-firc` 传冷构建判定；`--target`/`-O0` 在 api 层落
  `proj.cfg()`（子进程不经 cli 解析）。
- **目标/路径**：`gs.c_target` → `proj.cfg().target`；`[link-windows-x64]` 节名 →
  编码 5/6；`.lib/.dll` 输入校验；盘符绝对路径（`proj.canon`、`li_build_path`）。
- **justfile**：Windows 分支接到合并后的配方；反引号里取不到 just 变量（shell 带
  `-u`），`worktree_tag`/`cache_root` 按平台写死解释器名；`stage-yh` 的内联 python
  改走环境变量（反斜杠会打断单引号字符串）。

### 合并引入并修掉的 5 个缺陷

1. **`__yh_chkstk` 破坏 r10/r11**（`compiler/windows-sdk/chkstk.c`）：LLVM 把页探测
   当序言的一部分发射，**不按 call 建模寄存器破坏**，寄存器分配器会把活值留在
   r10/r11 上跨过探测。合并后的断言 lowering 把 `%line` 暂存在 r10d → `$assert`
   记录里的行号变成 `0x1F6FFDF8` 这类垃圾（列号在 r8d 所以正常）。修法：桩内
   `push/pop` 保存 r10/r11（与 MSVC `chkstk.asm` 同契约）。
2. **`--emit-llvm` 没传给模块子进程**（`cmd/api.yh`）：`yh test --emit-llvm` 的子进程
   以 usage(2) 退出，测试构建没有 `.ll` → `emit-llvm` 与 `test-bodies-lowered` 两例
   失败。修法：子进程参数解析接受 `--emit-llvm` 并置 `cfg().emit_kind`。
3. **`libs/net` 缺 Windows 实现**（主线新加的 UF1 未使用函数检查）：Windows 目标上只有
   模型层被编入，`stream_zero/listener_zero/error_from_result` 无人引用被判死代码。
   修法：新增 `libs/net/20_tcp.windows.yh`——真的调用一次 `sys.socket_fd` 并把
   `-ENOSYS` 按统一映射转成 `status_unsupported`（不伪造 native_code=0）。
4. **测试夹具依赖 UB**（`tests/modules/projects/ytestfail`）：「崩溃不算通过」用空指针
   写，而空指针写是 UB，LLVM 在 O0 也会删掉它（实测编译成 `nop`）→ 用例正常返回被
   误判 PASS。修法：地址改为由 `getpid()` 派生（后端无法证明不可写），store 一定发射。
5. **`tc_case_start` 的 Windows 分支在合并中丢失**：主线的 `fork/dup2/execv` 版本覆盖了
   `CreateProcess` 版本，Windows 上 `fork()` 返回 -1 → 所有用例「崩溃或缺少结果记录」。
   修法：恢复 Windows 分支（CreateProcess + 显式环境块 + 十进制用例号），POSIX 分支
   保持主线的 fd 3 复制语义。

### 验证（Windows/x86_64 原生）

| 项 | 结果 |
|---|---|
| 两代固定点 | `ca4b1aee02a64d58…`（A == B） |
| `just test` | **rc=0**：语法 82/82、反例 49/49、运行 363/372（跳过 9）、fail 138/138、pass 10/10、libs **133/133**、compiler-tests 4/4、arch-check 通过 |
| `just selfhost-native` | 合并后重跑（见 todo 的 W2-9 条目） |

**遗留**：`bin/` 种子不入库（主工作区已本地复制 `bin/yh-windows-x64` 与闭包软链）；
CI 构建合并后的代码需要先发一个认识 `windows` 标记的种子（W2-0）；
`[link-windows-x64]` 仍是本机绝对路径（W2-2）。

## 2026-10-28 NP3 能力矩阵实测与裁剪（不新增后端能力）

- **做了什么**：用 35 个单文件探针（`tmp/np3/probe/`，3 秒超时）实测「受检 →
  SSA → LLVM」实际覆盖，回答「NP3 还要补什么」：28 通过 / 7 被拒，归并为
  **4 个真实缺口**。结果落成 [能力矩阵](03-design/yh-受检到LLVM能力矩阵-2026-10-28.md)。
- **结论**：方案 §6.4 列的能力（嵌套循环、for-in、switch/goto、指针/内存、转换、
  聚合、浮点、各类调用）**基本已成立**，无需「补齐覆盖」这一大块工作。
- **新发现（4 项缺口，当日全部修复）**：
  - **G1** `let p *fn(int, int) int = &f` 生成 `alloca void`；根因是
    `checked_lower_pointer_kind` 把不透明指针值映成 `IR_TY_PTR + IR_TY_PTR`
    （元素类型退化 void）。**todo 的 D1（goto 函数里的函数指针）只是同一缺陷的
    一种形态——不需要 goto 就能复现**，D1 条目已按此修正。
  - **G2** 聚合三目初始化 `let p Pair = c ? a : b` 报「首片不支持此聚合初始化形态」
    （`checked_lower_aggregate_store` 缺 TERNARY，与 CLI-R1c/R1d 同族）。
  - **G3** 浮点全局（`let GF f64 = 1.5` / 无初始化）被 `llvm_preflight` 拒绝。
  - **G4** `switch` 控制表达式为 `bool` 被拒（`IR_OP_EQ` 本就支持，只是类型检查写窄了）。
- **注释纠偏**：`ast_ir_build.yh` 与 `module_snapshot_lower_flow.yh` 里「本切片
  不支持嵌套循环」与实际 `CheckedLoop` 循环栈矛盾，已改写（这类失真会直接导致
  重复实现已存在的特性或误判「还有旧发射兜底」）。
- **范围裁剪（用户决定）**：只保留矩阵 + 真实缺口 + 文档收口；**不做**缓存键上移
  与 `gen` 分层。理由已量化写入 todo：前者只是把同一段哈希/查表挪位置（冷编
  lowering 里缓存查表 4.0%，PL1 实测 650.4 ms / 30 s 量级构建），改造点却在单函数
  改动场景占 86.9% 的热路径（PL1：缓存合并 998.0 / 1148.7 ms），且 PL1f3 有
  「无收益按规矩回退」的先例；后者属 `gen` 分层（G2 推迟，`parse` 272 / `ast` 121
  处引用级），收益未测量。
- **回归**：`tests/yh-run/run/208-lowering-coverage-matrix.yh`（聚合初始化/赋值来源、
  嵌套 for-in 与多 break/continue、二维数组字面量、切片字段、聚合调用、9 参数、
  字段取址链、返回切片字面量、enum switch、前后向 goto、转换矩阵、union 字面量、
  短路副作用与全局计数、浮点/指针取址、顶层结构体/切片全局）。
- **G1 修复（当日）**：`*fn(...)` 绑定的存储地址是一条 `result_type = IR_TY_PTR` 的
  `IR_OP_ADDR`，而 canonical `IR_TY_PTR` 的 `elem` 规范编号是 `IR_TY_VOID`，
  ADDR 发射照抄元素类型就写出 `alloca void` 被 LLVM 拒绝。修在
  `backend/llvm_scalar.yh`：元素为 `VOID` 的不透明指针槽按指针宽度发
  `alloca ptr, align 8`。**todo 的 D1（goto 函数里的函数指针绑定）是同一缺陷，
  不需要 goto 即可复现，已随之关闭**。回归 `run/209-fnptr-address.yh`（含 D1 形态）。
- **顺带修诊断再改支持**：`&函数名` 以前落到全局对象分支报「全局对象缺少受检数据」
  （与事实无关）；先改成可操作诊断，随后按 G1b 真正实现（物化 8 字节函数值槽），
  诊断用例 `fail/169` 随之删除。
- **G2 修复（当日）**：`checked_lower_aggregate_store` 新增 `AST_EXPR_TERNARY`——
  聚合没有 SSA 值，两条分支各自写入同一目标存储、建 then/else/join 三块，不建 phi。
  所有调用点自动受益：`let` 初始化、同型赋值、聚合返回、结构体字段/数组元素、
  切片视图三目。回归 `run/210-ternary-aggregate-lowering.yh`（循环体内、if 分支内、
  嵌套三目、切片视图，O0/O2）。
- **G3 修复（当日）**：两处缺陷叠加——① `llvm_preflight` 按符号类型直接拒绝
  f32/f64 全局（全局本就按原始字节发射，拒绝多余）；② f32 全局读回 0：常量浮点在
  所有折叠路径以 f64 位模式保存，而 `parse_global_static_scalar` 按宽度直接写字节，
  4 字节对象只截到低 4 字节。修复：写静态标量前按目标类型窄化（新增
  `gen.fp32_bits`，`ct_ir_float.yh` 的同名实现改为调用它）；顺带解除
  `parse_global_init.yh` 里「f32 元素的全局初始化暂不支持」的保守守卫。
  回归 `run/211-float-globals.yh`。
- **G1b 实现（当日）**：`&函数名` 不再拒绝——函数值本身是不透明指针，但 `&f` 要求
  真实内存对象，故分配 8 字节槽、写入 `FN_ADDR`、返回槽地址（IR verifier 的
  「VOID 元素指针存函数值」例外规则本来就有，无新 IR 形式）。覆盖 `let p = &add`、
  `apply(&add, …)`、先声明后赋值，并入 `run/209-fnptr-address.yh`。
- **G2b 实现（当日）**：`(c ? a : b).y` 这类「聚合三目结果直接取字段/下标」
  在 `checked_lower_lvalue_ptr` 新增 `TERNARY`/`CTIF` 分支——按聚合大小/对齐发
  ALLOCA、把选中分支写进去，再走普通左值偏移。临时槽由后端提到入口块（I4-7），
  30 万次迭代探针确认无栈增长。并入 `run/210-ternary-aggregate-lowering.yh`。
- **G4 实现（当日）**：`switch <bool>` 改为支持——控制值本来就用 `IR_OP_EQ` 逐个
  比较，bool 与整数同构，拒绝只是类型检查写成 `ir_integer_type`。新增
  `run/212-switch-bool-control.yh`（含 default、循环内、表达式控制）。
  原 `fail/169`、`fail/170` 两个「拒绝行为」用例在能力补上后删除。
- **NP3 关闭**：能力矩阵**零被拒**（33 构造 + 5 变体，O0/O2）；方案 §6 逐条对照
  见 [todo](todo.md) 的收口说明——受检快照/函数级缓存早已落地，控制流分片补齐了
  三目与取址，`ir` 无 import，旧发射已在 LL12 删除；「预检分离」因已无可达
  `UNSUPPORTED` 会变成死代码而不做，「缓存键上移」与「`gen` 分层」按 0 收益/未测量
  的裁剪决定不做。
- **验证**：`just test` 133 passed/0 failed；`just selfhost-native` 全绿
  （固定点 cc3→cc4 一致、自解析 OK、124/124 项目用例）；yh-run 368/369
  （1 例平台跳过，run 220 / fail 138）。
- **种子**：全绿后 `just seed` 滚种子，`bin/yh-darwin-arm64` 更新
  （sha256 `2b18995f…79bf7`），新种子冷编 `just` 通过。
- **交付**：代码 10 个文件；能力矩阵文档
  [yh-受检到LLVM能力矩阵-2026-10-28](../03-design/yh-受检到LLVM能力矩阵-2026-10-28.md)；
  回归 `run/208`–`run/212`。

## 2026-10-28 0.0.11 正式版发布完成

- **发布**：tag `0.0.11`（打在默认分支 `llvm`）→ Gitea `release.yml` 三端全绿后 publish 成功：
  <https://github.com/lalavender/x/releases/tag/0.0.11>（正式版，非 prerelease）。
  资产：darwin-arm64 23,680,756 B / linux-arm64 40,680,912 B / linux-x86_64 40,719,466 B
  + 各自 `.sha256`；publish 阶段校验远端大小与本地一致。
- **发布二进制验收**：`rm -rf bin && just fetch-seed` 取到 0.0.11 种子
  （sha256 `5a9735c9…bc69c`，与 rc.2 种子**逐字节相同**）→ `just` 通过 →
  `just test` 133 passed/0 failed → `just selfhost-native` 全绿（48 产物固定点、
  129 文件自解析、124/124）。
- **说明**：正式版代码与已验收的 `0.0.11-rc.2` 完全一致（差异仅发布文档）；
  分支保持 `llvm`（默认）/`arm64`/`main`，未再建 `<ver>-release`。

## 2026-10-28 0.0.11 正式版发布（tag 打在 llvm）

- **发布说明**：`docs/01-finished/release-0.0.11.md`（CLI-R 命令行重写、B1/B2 架构收敛、
  PF1b–PF4 + PL1 性能工程、I4-7 + J6-L1..L4 产物体积、RB5 修复、实测与三端验证、已知边界）。
- **流程调整（用户决定）**：分支收敛为 `llvm`（默认）/`arm64`/`main`，不再保留
  `<ver>-rc` / `<ver>-release` 双线；正式 tag 直接打在 `llvm`。代码与已验收的
  `0.0.11-rc.2` 完全一致（差异仅发布文档）。
- **种子链**：`0.0.10` → `0.0.11-rc.1` → `0.0.11-rc.2` → **`0.0.11`**。
- **发布**：`git tag -a 0.0.11` → Gitea `release.yml` 三端构建 + publish（正式版，
  不带 prerelease）；发布后用 0.0.11 种子复核 `just` / `just test` / `just selfhost-native`。

## 2026-10-28 0.0.11-rc.2 发布完成（含两处既有回归修复）

- **发布**：tag `0.0.11-rc.2` → Gitea `release.yml` run 176 三端全绿后 publish 成功：
  <https://github.com/lalavender/x/releases/tag/0.0.11-rc.2>（prerelease）。
  资产：darwin-arm64 23,680,755 B、linux-arm64 40,680,913 B、linux-x86_64 40,719,472 B
  + 各自 `.sha256`（publish 阶段校验远端大小与本地一致）。
- **首发失败与修复（两处既有回归）**：
  1. `test-llvm-darwin` 的 RB5 位级可复现失败——B2-3 拆 `LinkPlan` 时，Mach-O 的
     暂存子目录（`<dir>/.yh-tmp.<pid>/<basename>`，让 codesign identifier 只取
     basename）随后被 ELF 的 `<out>.yh-tmp.<pid>` 无条件覆盖，pid 重回 identifier。
     修复：该覆盖只在 `use_macho == 0` 时执行。
  2. linux 两个 job 死在 `justfile` 的裸 `unexport YH_BUILD_CACHE`——容器内 Ubuntu
     just 1.21 解析失败；改成 `export YH_BUILD_CACHE := ""`（空值对编译器等价于未设置，
     已在 `yh-ci:ubuntu24` 镜像里 `just --list` 验证）。
- **发布二进制验收**：`rm -rf bin && just fetch-seed` 取回 rc.2 种子
  （sha256 `5a9735c9…bc69c`）→ `just` 构建通过 → `just test` 133 passed/0 failed →
  `just selfhost-native` 全绿（48 产物固定点、129 文件自解析、124/124）。
- **分支**：`llvm`（默认，含本次修复）已推送；`arm64`/`main` 保留；无临时分支。

## 2026-10-28 修复 RB5 回归（Darwin 产物位级可复现）

- **症状**：`just test-llvm-darwin` 在 `llvm-darwin-link.py` 的 RB5 断言失败
  （「同一源码重复链接的 Darwin 可执行文件不可位级复现」），release rc.2 三端全红。
- **根因**：B2-3 把 `mb_link` 拆成 `LinkPlan` 阶段时，`mb_link_prepare` 先按 RB5
  算出 Mach-O 暂存子目录 `p.link_tmp`（`<dir>/.yh-tmp.<pid>/<basename>`，identifier
  只取 basename），紧接着**又无条件**用 ELF 的 `<out>.yh-tmp.<pid>` 覆盖了一次，
  RB5 的子目录方案被冲掉，identifier 重新带上 pid。
- **修复**：把那段覆盖包进 `if (p.use_macho == 0)`（只给 ELF 用），Mach-O 沿用
  `mb_macho_link_stage` 的结果；`arch-check` 预算 link 3758 → 3763。
- **验证**：`llvm-darwin-link.py` 通过（22 项 PASS）、`just test-llvm-darwin` 全绿、
  `just test` 133 passed/0 failed、`just selfhost-native` 全绿（48 产物固定点、
  129 文件自解析、124/124）。

## 2026-10-28 0.0.11-rc.2 准备（发布说明 + 全门复核）

- **发布说明**：新增 `docs/01-finished/release-0.0.11-rc.2.md`，覆盖 rc.1 之后的
  45 个提交：B1（`gen.G()`=0 / `CompileStats` / `BuildCtx`）、B2（16 模块、
  build 6,637、link/proj 拆分）、CLI-R（命令行走 `libs/cli`）、
  PF1b–PF4 + PL1（阶段归因、缓存 v2 与 13.7 ms/函数 capture、去掉重复 verify
  −10.6% 冷编）、I4-7（ALLOCA 栈泄漏）与 J6-L1..L4（dead_strip / ELF gc-sections /
  依赖 O2 / strip，fmt 体积比 1.063）。
- **兼容性**：缓存格式 v2（首次重建）、依赖项目缺省 O2（`YH_DEP_OPT=0` 回退）、
  Darwin 缺省 `-dead_strip`（`YH_LINK_DEAD_STRIP=0` 回退）、`--stats` 新增 12 字段、
  新增 `YH_WORKERS`/`YH_BUILD_CACHE`/`YH_LINK_STRIP`，`FAST_DIR` 按 workspace 隔离。
- **种子链**：`0.0.10` → `0.0.11-rc.1` → `0.0.11-rc.2`；分支收敛为
  `llvm`（默认）/`arm64`/`main`。
- **复核**：`just test` 133 passed/0 failed、`just selfhost-native`（48 产物固定点、
  129 文件自解析、124/124）、`just arch-check`、fmt 专项门与缓存矩阵全绿。

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
- **私有闭包要装齐三端**：私有闭包最初只有 darwin host 目录，容器任务挂载它
  后找不到 `llvm-host-linux-*` → 尝试联网下载 → `LLVM 宿主：HTTP Error 404`
  （run 163 的 linux-arm64 即此）。现在用 `cp -al` 把共享的
  `llvm-host-linux-{aarch64,x86_64}`、`sdk` 与 `.deb` 硬链进私有闭包（同卷零成本，
  容器里是真实文件，不是悬空软链），三端 `status` 均为 ready。
  同时给 `tools/llvm-host.py` 的 `identity()`/错误消息补 `display_path()`，
  仓库外缓存根不再抛 `ValueError`。
- **记录里的 link_flags 必须走 canonical 路径**：私有闭包的 `host.json` 是从共享
  闭包复制的，`link_flags` 里的归档路径带着 `tmp/llvm-migration-llvm-3/` 时，
  `tools/link-closure.py` 的 `tmp/llvm-migration/` 标记匹配不上 → 派生出的
  lld/llvm 组为空 → `[link-darwin-arm64].lld 与宿主记录不一致`（run 164/165）。
  把 `link_flags` 归一回 `.../tmp/llvm-migration/...`（并按 `selfhost_link_flags`
  补齐归档、保留 `-lc++`）后 `link-closure.py check --host darwin-aarch64` PASS。
- **环境**：`just llvm-host` 幂等化后本地/CI 都不再重建闭包；闭包记录里的
  `host_builder_sha256` 每次改 `tools/llvm-darwin-host.py` 需重新基线（本轮改了四次，
  最终记录与磁盘一致，`check(full=True)` 为空、`tools/link-closure.py check
  --host darwin-aarch64` PASS）；`record_path()` 必须把路径写成
  `tmp/llvm-migration/...` 别名，否则 `[link-darwin-arm64]` 的 bridge 会被
  link-closure 误分类到 support 组。
- **发布结果**：tag `0.0.11-rc.1` 推送后 `release.yml`（run **168**）五 job 全绿，
  `publish` 创建 prerelease 并上传三端资产
  （`yh-0.0.11-rc.1-{darwin-arm64,linux-arm64,linux-x86_64}.tar.gz` + `.sha256`）：
  https://github.com/lalavender/x/releases/tag/0.0.11-rc.1 。
  分支门 `ci.yml`（run **167**）三平台同样全绿（darwin-arm64 / linux-arm64 /
  linux-x86_64 各完整跑完语料 + `SKIP_CORPUS=1 selfhost-native`）。
- **rc 二进制验收**（AGENTS 第 3 步）：`rm -rf bin` →
  `GH_TOKEN=… GITHUB_REPOSITORY=lalavender/x just fetch-seed`（取到 rc.1 的
  darwin-arm64 种子，sha256 `c7d230f0…`、自报 `yh 0.0.11`）→ `just`（冷编）→
  `just test`（三层回归全绿）→ `just selfhost-native`（固定点、自解析、语料、
  `build-check` 124/124 全绿）。三项均 EXIT=0。
- **合入主分区 `llvm`**：`merge/llvm-0.0.11` = `gitea/llvm`(8b1e7e1) + `--no-ff`
  `0.0.11-rc`。两处冲突/问题按如下处理：
  1. `tools/llvm-host.py`：另一条线已用 `describe()` 修了同一个「仓库外缓存根
     relative_to 抛错」的问题，取他们的实现（语义等价），丢掉我的 `display_path`；
  2. `tools/link-closure.py`：记录里的归档路径可能是本仓库 / 主 worktree /
     容器挂载点 / 私有闭包（`tmp/llvm-migration-<后缀>/`）四种布局，新增
     `canon_archive()` 统一归一到 `tmp/llvm-migration/...`，并把归档来源扩到
     `selfhost_link_flags`（新世代记录只留这一份）——`llvm` 线原状是
     `[link-darwin-arm64].lld 与宿主记录不一致`，合入后该项 PASS。
- **合入后的门禁**：`just`、`just test` 全绿（TEST=0）；`just test-llvm-darwin`
  21 项 PASS 后停在 RB5「同一源码重复链接的 Darwin 可执行文件不可位级复现」——
  该断言是 `llvm` 线自己新加、尚未完成的 RB5 工作，用他们自己的编译器在
  `gitea/llvm` 独立复现同样失败，与本轮 UF1/rc 无关；`llvm` 分支 CI（run 166）
  本来就红，本轮合入把它从「link-closure 早停」推进到「21 项 PASS + RB5 待收口」。
- **下一步**：RB5 由 `llvm` 线收口后跑绿；随后 `git merge --no-ff 0.0.11-rc` →
  `0.0.11-release`、打正式 tag `0.0.11`（正式 tag 必须落在 release 分支上）；
  发完删 `0.0.11-rc`、保留 `0.0.11-release`。

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

## 2026-10-27 J6 收尾：Linux section 化 + release 剥离 + 体积度量

- **L2（Linux 死代码回收）**：`backend/llvm_module.yh` 新增
  `llvm_elf_sections`（目标 key 1/2 = ELF）与 `llvm_section_name`（`$`→`_S`、
  `.`→`_D`）；ELF 下每个函数发 `section ".text.<mangled>"`、每个全局发
  `.rodata./.data.` 独立 section；`build/link_cache.yh` 对 Linux 目标追加
  `--gc-sections`（内嵌 lld）/`-Wl,--gc-sections`（系统 cc）。Darwin 不变（实测
  Darwin `.ll` 无新增 section，Mach-O 按符号原子回收）。验证：`--target
  aarch64-unknown-linux-gnu --emit-llvm` 的 ELF IR 中 fmt=61 / io=32 条函数
  section，ELF 对象节表出现 `.text.main`/`.text.memcpy`/`.text.memset`。本机无
  Linux 链接环境（`container run` 启动即报错），端到端收益留给 Linux CI。
- **L4（release 剥离与自身度量）**：`YH_LINK_STRIP=1` 给 ld64.lld 加 `-x`
  （缺省关，计入链接键）；fmt hello `53,424 → 52,576 B（−1.6%）`。编译器自身：
  cc2（由种子链接）`70,815,568 B`/93,995 符号 → cc3/cc4（由新编译器链接）
  `65,112,448 B`/79,168 符号，**−8.1%**——`-dead_strip` 对自举产物确实有效
  （之前用 `just build` 对比得到「无变化」是因为那一步由种子链接）。
  拆 fmt 模块仍不做（与「fmt 不扩 API」边界冲突，且已无必要）。
- **度量物**：`tests/perf/fmt-size/{printf-hello,fmt-hello}` 两个最小项目 +
  `tools/size-report.py`（Darwin 读 `size -m`、Linux 读 `size -A`，输出表格或
  JSON；`--budget-ratio` 软门，`--strict` 才失败），入口 `just size-report`。
  当前读数：printf `50,256 B` / fmt `53,424 B`，比值 **1.063**（上限 1.2）。
- **预算**：`tools/arch-check.py` 的 `max_build_lines` 10878 → 10904（L2/L4 +26）。
- **验证**：`just test` 全绿；`SELFHOST_KEEP=1 FAST_DIR=<repo>/tmp/yh-fast just
  selfhost-native` 退出码 0（cc3→cc4 固定点、全量语料、新门、122/122 项目
  用例）。**注意**：共享 `$TMPDIR/yh-fast` 会被并发会话覆盖（曾因一次陈旧
  分期编译器报出不属于本树的 `函数未使用` 诊断），跑主门建议把 `FAST_DIR`
  指到仓库内。
- **滚种子**：`just seed` 已把验证过的 `yh` 写入 `bin/yh-darwin-arm64`
  （70,404,016 B，SHA-256 `34511ff2…`）；新种子已自测：能编出 hello、能
  `build compiler/` 全项目。

## 2026-10-27 依赖项目单独 O2：fmt 版产物降到 71 KB（J6-L3）

- **背景**：L1 的 `-dead_strip` 之后 fmt 版 hello 仍有 89,632 B，`__text` 35,732。
  可达集是真实调用链（`print`→`output_values`→`append_value`→浮点/spec 分支→
  `string`/`io`/`os`/`sys`），大部分代码在 O0 下逐条发射。
- **改动**：新增 `pj_module_opt_level(m)`（`build/project_state.yh`）：依赖/
  标准库项目取 2、根项目沿用命令行值；`YH_DEP_OPT=0` 回退。接入三处，保证
  开↔关不会复用旧产物：
  1. 对象发射：`llvm_pipeline.yh` 的 `llvm_emit_publish` / `llvm_emit_module_to(_cached)`
     新增 `opt_level` 参数，由 `module_worker.yh` 传 `pj_module_opt_level(m)`，
     单文件路径仍传 `gs.c_opt_level`；
  2. 模块 manifest 键与函数 IR 环境键改用同一判定（`module_build.yh`、
     `function_ir_cache.yh`）。
- **效果**（macOS/arm64）：fmt hello 项目 `89,632 → 71,008 B`（`__text`
  35,732 → 12,516）；只用 fmt 少量叶子的项目 53,696 B，已经落回 printf 版
  50,256 B 的同一档（差 3.4 KB，主要是 `__DATA_CONST`/`__DATA` 两页未变）。
  libs 作为根项目跑 `just libs-test` 时仍为 O0，`libs-test-o2` 仍全 O2。
- **新门**：`tests/modules/opt-level.py`（已接 `just test`）：依赖默认比
  `YH_DEP_OPT=0` 小、两种配置行为一致、关闭→缺省不复用旧对象、无依赖项目
  两种配置产物体积一致（证明开关不碰根项目）。
- **顺带修复（工具链）**：`tools/llvm-darwin-host.py` 的记录路径改为
  `recorded_path`/`resolve_recorded`——当 `YH_LLVM_CACHE` 指向仓库外（justfile
  导出外部缓存根）时，`relative_to(ROOT)` 会抛 `ValueError` 使
  `just selfhost-native` 在闭包检测阶段直接失败。现在仓库内仍写相对路径，
  仓库外写绝对路径，读取方统一还原。
- **架构预算**：`max_build_lines` 10846 → 10878（本项 +32），
  `max_g_call_sites` 165 → 166（`pj_module_opt_level` 读模块表 +1）。
- **验证**：`just`（种子冷编）→ `just test` 全层绿（含新门）→
  `just selfhost-native` 退出码 0（cc3→cc4 固定点、全量语料、122/122 项目用例）。
- **后续**：L2（Linux `--gc-sections` + 函数级 section）、L4（`-x`、编译器
  自身 dead_strip、`fmt` 可达面瘦身）仍在 J6 下。

## 2026-10-27 Darwin 链接缺省 -dead_strip：fmt 版产物体积回到 printf 基线（J6-L1）

- **背景**：yh 的链接粒度是「一个模块一个对象」。没有死代码回收时，用 fmt
  打印的程序会把整个 string/os/sys 闭包中未引用的函数与字符串字面量带进
  产物：hello 级程序 O0 实测 155,888 B / `__text` 85,032，而 printf 单文件
  只有 50,256 B / 1,872——这是「输出全部走 fmt」的硬成本。
- **改动**：`compiler/build/darwin_link.yh` 新增
  `mb_darwin_dead_strip_enabled`（缺省开，`YH_LINK_DEAD_STRIP=0/off/no/false`
  关闭）与 `mb_macho_dead_strip_flag`；`mb_macho_link_prefix` 在 `-adhoc_codesign`
  之后追加 `-dead_strip`；`mb_hash_macho_identity` 把开关状态计入链接键，
  避免关→开或开→关命中旧链接缓存（argv 容量 20 已够：14 + 1 + 2 参数）。
- **效果**：fmt 版 hello 155,888 → **89,632 B**（−42.5%），`__text` 85,032 →
  38,432，`__stubs` 504 → 72；未引用的 `utf8_next`/`replace_all`/`change_dir`
  等符号不再进入产物。再叠 O2 可到 54,616 B（接近 printf 的 50,256 B，留作 L3）。
- **新门**：`tests/selfhost/darwin-dead-strip.py`（已接 `just selfhost-native`
  的 `dead_strip_test`）：① 缺省链接回收未引用函数符号；②
  `YH_LINK_DEAD_STRIP=0` 符号重新出现且产物可运行；③ 两种配置 stdout 一致；
  ④ 先构建关闭态再构建缺省态仍为已回收，证明开关进入链接键。
- **架构预算**：`tools/arch-check.py` 的 `max_build_lines` 10807 → 10846
  （本项在 build 模块新增 39 行：判定与取参两个小函数 + 两处接线）。
- **验证**：`just`（种子冷编）→ `just test`（全层绿，含 arch-check 自测 2/2）→
  `just selfhost-native` 退出码 0（cc3→cc4 固定点、全量语料、新门、122/122
  项目用例）。
- **后续**：L2（Linux `--gc-sections` + 函数级 section）、L3（stdlib 单 O2）、
  L4（`-x` / 编译器自身 dead_strip）仍在 `docs/todo.md` J6 下待做。

## 2026-10-27 修循环内调用期 ALLOCA 栈泄漏（I4-7）

- **缺陷**：聚合实参副本、结构体返回值槽、变参打包与切片后备数组的 ALLOCA
  由 lowering 在**调用点所在块**发出。这类调用落在循环体里时，每次迭代都会
  再分配一份栈空间且不回收，累积到 main 线程 8 MB 栈后段错误；与 `-O0/-O2`
  无关，也不是 fmt 的问题。纯 yh 最小复现：
  `for i < 600000 { take([make_big(i), make_big(i)]) }`（56 字节结构体）在旧
  编译器上约 3.7 万次迭代崩溃；同一形态的 `fmt.print([of_int(i), …])` 在 4 万
  次迭代崩溃，恰好是「输出全部走 fmt」迁移的惯用写法，故列为迁移前置缺陷。
- **修复**：`compiler/backend/llvm_scalar.yh` 新增 `llvm_function_allocas`，在
  入口块一次性发射全函数 ALLOCA、原位置跳过（`llvm_instruction` 的 ALLOCA
  分支改为不发射）；槽位跨迭代复用，栈占用变为常量级。`compiler/ir/ssa.yh`
  的 `IR_OP_ALLOCA` 注释补上语义约束：常量大小、按调用期存活，不得表达按
  迭代增长的存储。
- **回归**：新增 `tests/yh-run/run/207-call-temp-stack-growth.yh`（60 万次迭代
  + 聚合实参 + 切片字面量元素，红 → 绿）；`tmp/leak3.yh` 形态直接复现也转绿。
- **验证**：`just`（种子冷编）→ `just test`（run 361/362，1 例平台跳过；fail
  137/137；modules 与 libs 全绿）→ `just selfhost-native` 全绿（cc3→cc4 模块
  固定点、全量语料、122/122 项目用例）。IR 复查：`fmt.print([...])` 主函数的
  四条 ALLOCA 已全部落在 `b0`，循环块 `b3` 不再分配。
- **后续**：产物体积的独立立项见 `docs/todo.md` J6（L1 `-dead_strip` → L2
  Linux section 化 + `--gc-sections` → L3 stdlib O2）；种子未滚（需用户确认）。

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
靠前条目记录最近状态；后续条目保留各次交付时的历史状态。

## 2026-10-21 恢复并验证 os/sys OS0–OS6

- 0.0.7 同步后的主工作区缺少 `libs/os`/`libs/sys` 实现；从备份 stash 选择性
  恢复 OS0–OS6 的库、测试、示例、设计与完成记录，并适配按 0.0.7 的
  `[project].os/arch` 必填字段。
- 恢复编译器 fn→ptr cast 修复与默认标准库发现（`YH_STDLIB` 优先，否则按
  可执行文件附近布局查找）；Makefile 安装 libs 到 `share/yh/libs`。
- 验证：`make`、`make test`、CLI 9/9、`make selfhost-native SKIP_CORPUS=1`
  （固定点 27 产物、自解析 100 文件、项目用例 115/115）通过；Linux/arm64
  容器 15 个 os/sys fixture 与 os-demo 示例全部退出 0。
- 未修改种子、未执行 `make seed`。OS7 编译器迁移与 OS8 Darwin 新接口仍未实施。
  详见 `docs/01-finished/yh-os与sys-OS*.md` 与
  `docs/01-finished/yh-标准库默认发现-2026-10-21.md`。

## 2026-10-21 0.0.7 Release：过渡种子与最终发布

- 创建过渡 Release `0.0.7-rc.1`（正常 Release，非 prerelease），上传
  Darwin/arm64、Linux/aarch64、Linux/x86_64 三端 F1 种子；CircleCI tag
  流水线通过忽略 `-rc.` tag 避免用旧 0.0.6 种子构建。
- 打 `0.0.7` tag 后 CircleCI 三端与 `publish` 全绿；三端从
  `0.0.7-rc.1` 种子自举、跑门禁并发布最终 Release。
- `tools/fetch-release-seed.py` 修复 Release 返回顺序依赖：显式按
  `published_at`/`created_at` 倒序，避免 `0.0.7-rc.1` 排在 `0.0.7` 前面。
- 从 0.0.7 Release 回读三端种子并验证：Darwin `make`、`make selfhost-native`
  （固定点/自解析/项目 111/111）、Linux 种子哈希与 CI 资产一致。
- Release 资产：
  `yh-0.0.7-{darwin-arm64,linux-arm64,linux-x86_64}.tar.gz` 与 `.sha256`。
- `link-latest` 已快进合并到远端 `llvm`（`a81d872..ecca3bc`），并继续推进到
  `c704a48`；默认分支包含 F1、0.0.7 版本号、Release 说明与种子拉取顺序修复。
- 合并后的 `llvm` 分支 CI 全绿：`antlr` 与
  `darwin-arm64` / `linux-arm64` / `linux-x86_64` 四个作业均 success
  （使用 0.0.7 Release 种子）。

## 2026-10-21 F1：编译器自举闭包迁移到 [link]

- `tools/link-closure.py` 从固定宿主记录生成 `compiler/project.toml` 的
  `[link-<os>-<arch>]`：bridge / lld / LLVM / support 归档；Darwin 全量
  whole，Linux 只强制 bridge。
- 新增 `[link-options] whole` 语义；bridge 使用 whole 覆盖弱桩。
- 运行库参数从归档闭包拆出：`selfhost-runtime.txt` 经
  `YH_LINK_RUNTIME_FLAGS` 在链接期追加；`YH_LINK_MANIFEST_ONLY=1` 让 C++ 桥
  停止旧归档注入。
- `seed-build.py` / `native-selfhost.py` / `llvm-selfhost.py` /
  `llvm-darwin-selfhost.py` 根据 compiler 清单自动切换 legacy 引导与
  manifest-only；生成期先走旧注入，清单生效后不再新旧叠加。
- 验证：Darwin 与 Linux/aarch64 均完成 cc3→cc4 固定点、自解析、CLI 冒烟；
  `build-check.py` 两端均 111/111，Linux `yh-run` 344/348（4 个 Darwin
  专属跳过），Darwin `make test` 347/348、`make selfhost-native` 全绿。

## 2026-10-21 project.toml 库文件链接（普通项目，移植到 LL12 基线）

- 在 `origin/llvm`（0.0.6 / LL12 退役后）重新落地 `[link]` 普通项目能力：
  `[project].os/arch`、`[link]` 命名组、`[link-<os>-<arch>]` 覆盖、
  realpath 去重、`.a`/`.so`/`.so.<版本>`/`.dylib`/`.tbd` 检查、
  `.build` 的 mtime/size+摘要缓存、`--link` 选择与 `run` 动态库搜索路径。
- 链接路径收敛到 LLVM 单后端：ELF 选中库统一 `--start-group`，Darwin 按
  声明顺序；链接顺序为对象 → `[link]` 库 → `[c].libs` → 系统库。
- 新增 `compiler/cmd/project_link.yh`、`compiler/cmd/link_inputs.yh`；
  适配 `project_index` / `module_build` / `driver` / `link_cache` 与
  `gen/model|state|target_info`。
- 测试复用 `linkgroups` / `linkshared` / `linkbad` / `linkmissingtarget` /
  `linkbadsuffix`，`build-check.py` 最新基线 111/111（LLVM）。
- 为兼容最新“种子不入库”策略，本工作区只在被忽略的 `bin/` 放置过渡种子；
  未提交种子二进制。普通项目实现已完成；F1（编译器自举闭包迁移）仍未开始。

## 2026-10-21 LL12-0：基线冻结与旧发射消费者普查

- 新建专用 worktree `/Users/lavender/Documents/x-ll12`（分支
  `ll12-retire-legacy`，起点 `e5e81ac`）；`tmp/llvm-migration` 以符号链接复用
  本机闭包，`make` 14s 冷编通过（`yh 0.0.5`）。
- 新增 [LL12 实施方案](02-plan/yh-LL12退役旧机器发射实施方案.md) 与
  [消费者普查](02-plan/yh-LL12旧发射消费者普查-2026-10-21.md)；普查工具
  `tools/ll12-legacy-consumers.py` 入库，共统计 2669 处引用：发射原语 1818、
  四缓冲 81、开关 60、旧链 240、共享 builder 390、目标值状态 80。
- 普查修正三处关键判断：`ast_ir_b_*` 390 处是 LLVM 快照 lowering 共享的 IR
  构造层（C3 保留）；`bss_n/bss_symbols` 是快照字段（C2 只删 `bss_put*`）；
  C1 范围从 `gen/sem_*`（549）扩到 `parse/*`（143）与 `comptime/*`（36），
  CT 常量需改走快照/模块 IR。
- 基线：hello 的 legacy/LLVM 可执行文件 50,672/50,256 B；legacy `.s` 234 行、
  LLVM `.s` 584 行。产物与脚本在 `tmp/ll12/`（未入库）。
- 本轮只新增文档与普查脚本，未改编译器、未滚种子。

## 2026-10-21 LL12-1a：诊断快照基线（语义纯化的回归前提）

- 新增 `tools/ll12-diagnostic-snapshot.py`：对 `tests/yh/{positive,rejected}` 与
  `tests/yh-run/{pass,run,fail}` 共 400 个 `.yh` 跑 `yh check`，记录
  rc/stdout/stderr 并归一化绝对路径；`--write` 生成基线，默认与基线比对，
  有差异退出 1。
- 基线 `tmp/ll12/diag-baseline.json`：400 个文件、175 个预期失败；
  生成与比对各约 4s，二次比对零差异（幂等）。
- 用途：C1 每剥离一处发射段后重跑比对，保证诊断逐条不变；基线不入库，
  换分支/改语料后重新 `--write`。
- 未改编译器、未滚种子。

## 2026-10-21 C4/C5 小尾巴、GitHub Actions 移除与 todo 优化

- **C4 目标简写移除**：`cmd/driver.yh` 不再把 `linux/gnu/elf/darwin/macho/macos`
  映射为隐含 AArch64 的 triple；`-target` 与 `--target` 都只接受完整三元组，
  简写给出来源诊断。`tests/modules/build-check.py` 的 5 个 r3 用例改用
  `aarch64-unknown-linux-gnu` / `aarch64-apple-darwin`。
- **C5 断言清理**：删除 `tests/yh-run/check.py` 的 `asm-symbols-safe` 校验
  （正则、函数与两处调用）与 `182-register-named-symbols.yh` 的指令；
  删除 `cmd/module_build.yh` 的 `legacy_bytes=0` 统计与
  `tests/selfhost/llvm-front-output.py` 的对应断言。
- **GitHub Actions 移除**：删除 `.github/workflows/ci.yml` 与 `release.yml`；
  多平台回归与 tag Release 由 CircleCI 承担，需要时从 git 历史还原。
- **todo 优化**：LL12（C0–C5）关闭；LL11 性能门移出（专门性能任务）；R2b
  （RS2/RS3/R2c）移到「后续任务」，不作为 LLVM 收尾；GA 账单项随移除关闭；
  ❓2/❓3 关闭。
- 验证：`make` 通过；`make test` 退出 0；`make selfhost-native` 退出 0
  （project 106/106）；`-target linux` 拒绝、完整三元组构建运行正常。
- 未滚种子（0.0.6 已发布）。

## 2026-10-21 0.0.6 Release 种子验证

- Release 0.0.6 已发布，三端资产齐全：
  `yh-0.0.6-darwin-arm64.tar.gz`（26.5 MB）、`yh-0.0.6-linux-arm64.tar.gz`
  （42.6 MB）、`yh-0.0.6-linux-x86_64.tar.gz`（42.6 MB）及各自 `.sha256`，
  说明 CircleCI tag release workflow 的三端测试与打包成功。
- 清理本地二进制（`bin/`、根 `yh`、`compiler/.build`）后，
  `make fetch-seed` 从 0.0.6 Release 下载种子：
  `bin/yh-darwin-arm64` sha256=`ce7cdb17…38ba6d`。
- 用新种子复跑：`make` 冷编通过；`make test` 无 FAIL；`make selfhost-native`
  模块固定点一致（27 产物）、cc4 自解析 98 文件 OK、project 106/106；
  `yh version` = `0.0.6`。
- fetch-seed 需要 `GITHUB_TOKEN` + `GITHUB_REPOSITORY=lalavender/x`
  （私有仓库），已在本地用 git 凭证临时提供，环境变量本身未持久化。

## 2026-10-21 推送 llvm 与种子出库

- 把退役分支推送到远端 `llvm`（`e5e81ac..1f2c8ba`），随后提交
  `5ee3779`：删除 `.gitattributes`（唯一 LFS 规则）与 `bin/` 下的
  darwin/linux 种子及哈希，`.gitignore` 改为忽略 `/bin/`，仓库不再依赖
  git-lfs；AGENTS/compiler README/Makefile 的种子说明改为
  `make fetch-seed` 从 Release 获取。
- 本地种子用 git 历史（darwin）与主仓库 LFS 缓存（linux）恢复到被忽略的
  `bin/`，哈希与入库记录一致；`make` 冷编通过，`make test` 退出 0。
- 本机 `make fetch-seed` 因仓库私有且匿名 API 限流失败，需提供
  `GH_TOKEN`/`GITHUB_TOKEN` 与 `GITHUB_REPOSITORY=lalavender/x`。
- CI：推送到 `llvm` 会触发 GitHub Actions（linux-x86_64、darwin-arm64）与
  CircleCI 三端；两者均用 token 从 Release 取种子，不依赖入库 bin。
- 未滚种子。

## 2026-10-21 LL12 完成报告

阶段完成报告：[docs/01-finished/yh-LL12退役旧机器发射-2026-10-21.md](01-finished/yh-LL12退役旧机器发射-2026-10-21.md)。
汇总改动清单、验证证据与本机范围外的边界（Linux/CI、滚种子、合并注意）。

## 2026-10-21 LL12 Linux 验证尝试（本机资源受阻）

- 尝试 Apple Container（Debian trixie/arm64）复跑 Linux 全门：
  - 默认内存下链接 LLVM 桥被 OOM kill（`ld terminated with signal 9`）；
  - 加 `-m 6G -c 6` 后，闭包根经符号链接解析到 `/Users/.../x/tmp`，不在
    `/work` 前缀下，`prepare` 写身份记录时 `relative_to(ROOT)` 失败；
  - 宿主可用磁盘仅 2.6–2.7 GiB，容不下 Linux LLVM SDK（deb 159 MB + 解包
    约 1.5–2 GiB）与构建产物。
- 容器内还发现 `/work/yh` 仍是宿主编译的 Mach-O（`make` 因源未变跳过重编），
  复跑前需 `rm -rf compiler/.build` 强制冷编。
- 结论：Linux/arm64 与 Linux/x64 的退役验证交由 CI（CircleCI 原生 arm64/x64、
  GitHub Actions）；本机 Darwin 门已全绿。换足量磁盘后可复跑：
  `container run --rm -m 6G -c 6 -v "$PWD":/work -v <宿主tmp>:/work/tmp -w /work ...`。
- 未改代码、未滚种子。

## 2026-10-21 LL12 退役验收（本分支静态与门禁证据）

- **代码规模**：`compiler/` 自分支起点 `e5e81ac` 累计 **+241 / -6757 行**
  （净 -6516），涉及 38 个文件。
- **删除的实现**：`gen/emit_arm64.yh`、`gen/emit_runtime_memory.yh`、
  `backend/arm64.yh`、`backend/arm64_call.yh`、`ast/ast_ir_cache.yh`、
  `ast_ir_inline.yh`、`ast_ir_control.yh`、`ast_ir_template.yh`、
  `gen/sem_cabi.yh`；`gen/buffer.yh` 的四缓冲原语、`gen/state.yh` 的
  `TaskCtx` 缓冲字段、`c_backend`/`target_legacy_ready` 等全部移除。
- **剩余 `em_*` 引用**：`parse/parse_decl.yh`（`em_add`）、
  `parse/parse_ct_layout.yh`（`em_update_value`）、`comptime/ct_ir_place.yh`
  与 `gen/sem_expr.yh`（`em_find/em_get_ready/em_get_val`）、`gen/state.yh`
  （枚举成员表定义）——均为语义基础设施，不是机器发射。
- **门禁**：`make test`（348/349，1 平台跳过）、`make selfhost-native`
  （固定点、自解析、project 106/106）全绿；400 语料诊断快照零差异。
- **待办**：Linux/arm64 与 Linux/x64 的 CI 复核（本机 Darwin 无法覆盖）；
  `AGENTS.md` 与替换设计文档的「legacy 过渡」表述收尾；滚种子。
- 未滚种子。

## 2026-10-21 LL12 第二十刀：C5 门禁迁移（首片）

- `tests/selfhost/runtime-memory.py`：删除 Linux/arm64 的 legacy 汇编契约段
  （`--backend legacy --emit-asm`、交叉汇编、符号检查）；保留 LLVM 运行时
  导入审计、编译器自编审计与无运行时项目检查。
- 删除 `tests/selfhost/llvm-darwin-target.py` 与 fixture
  `tests/yh-run/run/llvm-darwin-target.yh`：F2-0 基线验收器断言
  「legacy 成功、LLVM 被拒绝」，与 F2-2 完成后的实际相反，且不在任何门禁中；
  其覆盖由 `llvm-darwin-object/abi/runtime` 门承担。
- `tests/bench/` 在本分支不存在（bench 资产未入库），无需迁移。
- 验证：`python3 -m py_compile` 通过；`make test` 退出 0。
- 未滚种子。

## 2026-10-21 LL12 第十九刀：清理旧发射缓冲字段（C2 第三片）

- `gen/state.yh`：删除 `o_out/o_len/o_cap/o_dat/o_dlen/o_dcap/o_bss/o_blen/
  o_bcap/o_body/o_body_len/o_body_cap/c_in_body` 字段；`gen/front_stage.yh`
  的进入/校验只检查受检阶段标志。
- `parse/parse_decl.yh`、`parse/parse_expr.yh`：删除 `c_em_suppress` 读写；
  `parse/iface_ct.yh` 删除数据长度回滚；`ast/ast_function.yh` 的 asm 区间
  归零；`check/verify.yh` 去掉 `o_len` 上限；`cmd/module_build.yh` 的
  `legacy_bytes` 统计恒 0。
- fixture 迁移：`llvmfront`（受检前端边界）、`astcheck`（删除 `o_len` 赋值）。
- 验证：400 语料诊断快照零差异；`make test` 退出 0；`make selfhost-native`
  退出 0（project 106/106）。
- 未滚种子。

## 2026-10-21 LL12 第十八刀：删除 emit_arm64 与四缓冲（C2 第二片）

- 删除 `compiler/gen/emit_arm64.yh`（1227 行）；`hexval` 迁入
  `compiler/gen/state.yh`（语义层共用）。
- `compiler/gen/buffer.yh` 661→365 行：删除 `em_put/em_puts/em_puti`、
  `dat_put*`、`bss_put*`、`flush_output`、`flush_output_fd`、`flush_asm_ranges`；
  保留 `append_*`/`out_grow`/`read_source`/诊断等通用工具。
- `tests/modules/projects/llvmfront/main/main.yh` 迁移：原用例断言「旧四缓冲
  为零」并调用 `em_puts/dat_puts/em_bss_symbol`；改为只验证受检前端的
  进入/校验/退出/再次进入。
- 验证：400 语料诊断快照零差异；`make test` 退出 0；`make selfhost-native`
  退出 0（project 106/106）。
- 未滚种子。

## 2026-10-21 LL12 第十七刀：删除旧 arm64 后端（C2 首片）

- 删除 `compiler/backend/arm64.yh`（441 行）与 `arm64_call.yh`（115 行）：
  `arm64_emit_replace` 在 `ast_ir_lower_function` 删除后已无消费者。
- 清理最后 5 处残留发射：`comptime/ct_registry.yh` 的 `em_load_data_label`/
  `em_mov_imm`/`em_ins` 与 `cmd/compile.yh` 的 `em_puts`。
- 全仓 `em_*` 消费者只剩 `gen/emit_arm64.yh`、`gen/buffer.yh`、`gen/state.yh`
  与语义表（`em_find/em_get_val` 等）。
- 验证：400 语料诊断快照零差异；`make test` 退出 0；`make selfhost-native`
  退出 0（project 106/106）。
- 未滚种子。

## 2026-10-21 LL12 第十六刀：sem_flow 流程发射剥离（C1 完成）

- `compiler/gen/sem_flow.yh` 545→410 行：删除 `sem_assign` 取改存、`sem_forin_*`、
  `goto`/`label`、`break`/`continue` 的指令发射、槽与标签分配。
- 保留：类型检查、循环上下文与 break/continue 标记、`goto` 登记与诊断、
  for-in 元素/下标绑定事实。
- **C1 完成**：`gen/sem_*`、`parse/*`、`comptime/*` 不再调用任何 `em_*`；
  剩余 `em_*` 定义只存在于发射器自身（下一阶段 C2 删除）。
- 验证：400 语料诊断快照零差异；循环/switch/全局/for-in 用例通过；
  `make test` 退出 0；`make selfhost-native` 退出 0（project 106/106）。
- 未滚种子。

## 2026-10-21 LL12 第十五刀：sem_expr 表达式发射剥离（C1 第九片）

- `compiler/gen/sem_expr.yh` 1050→929 行：删除二元/一元/比较/逻辑短路/三元/
  转换/下标/切片/成员访问的指令发射、标签分配、临时槽与值栈搬运。
- 保留：类型规则与提升、常量折叠、全部诊断、`c_res_is_addr` 形态、枚举成员
  表查询（`em_find/em_get_ready/em_get_val` 是语义表，不是发射）。
- 验证：400 语料诊断快照零差异；算术/短路/分支用例通过；`make test` 退出 0；
  `make selfhost-native` 退出 0（project 106/106）。
- 未滚种子。

## 2026-10-21 LL12 第十四刀：sem_call_literal 调用发射剥离（C1 第八片）

- `compiler/gen/sem_call_literal.yh` 496→264 行：删除实参压栈/弹栈、栈参数
  暂存与回填、寄存器/浮点装载、间接调用目标、`bl/blr`、栈清理、结果恢复、
  聚合返回缓冲与窄化、结构体字面量槽/字段拷贝/取址。
- 保留：实参类型与变参检查、类型化变参的切片化记录、浮点参数上限诊断、
  `noreturn` 可达性、结果类型与 `c_res_is_addr` 形态。
- 验证：`\bem_` 在该文件零命中；400 语料诊断快照零差异；结构体 ABI/深字段/
  解引用赋值用例通过；`make test` 退出 0；`make selfhost-native` 退出 0
  （project 106/106）。
- 未滚种子。

## 2026-10-21 LL12 第十三刀：parse_expr 字面量发射剥离（C1 第七片）

- `compiler/parse/parse_expr.yh` 2058→2015 行：删除数组/切片字面量的临时数组
  逐元素写入、切片描述符构造（`em_alloc_local`/`em_pop`/`em_store_sized`/
  `em_lea_local*`/`em_frag`/`em_ins`）与类型谓词的 `em_mov_imm`。
- 保留元素解析与类型检查、`sem_push_value` 值栈协议（留待 sem_call 片）、
  结果形态（`c_res_is_addr`）与 AST 捕获。
- 验证：`\bem_` 在该文件零命中；400 语料诊断快照零差异；切片/聚合用例通过；
  `make test` 退出 0；`make selfhost-native` 退出 0（project 106/106）。
- 未滚种子。

## 2026-10-21 LL12 第十二刀：C ABI 发射层删除（C1 第六片）

- 删除 `compiler/gen/sem_cabi.yh`（246 行）：GPR/FPR 片搬运、栈参数、
  聚合入口拷贝、C 返回寄存器转换与 `sbfx/ubfx` 窄化全部移除。
- `gen/sem_decl.yh`：`sem_declare_param` 不再分派 `sem_cabi_param`，C 参数
  只登记符号与 `F_AGGPARAM` 事实。
- `gen/sem_call_literal.yh`：`ABI_C` 调用改为记录结果形态（类型/地址事实）
  并保留 `noreturn` 可达性；删除 `sem_cabi_return` 调用。
- 过程中发现并修复两处语义回归：① noreturn 的 C 调用丢失不可达标记，导致
  `07-noreturn-branches` 报「正常落底路径」；② C 函数 HFA 参数被旧浮点
  上限（8）拒绝，改为 C 函数跳过该上限。
- 验证：400 语料诊断快照零差异；`make test` 退出 0；`make selfhost-native`
  退出 0（project 106/106，含 C 双向 ABI/回调用例）。
- 未滚种子。

## 2026-10-21 LL12 第十一刀：parse_stmt 控制流发射剥离（C1 第五片）

- `compiler/parse/parse_stmt.yh` 768→647 行：删除 `em_new_label`/`em_label`/
  `em_jmp`/`em_jz`/`em_beq`/`em_frag`/`em_mov_imm`/`em_alloc_local`/
  `em_lea_local_to`/`em_ins`/`em_push` 在 if/for/switch/return 中的调用。
- 保留：`sem_loop_push/pop` 循环上下文、`c_fn_falls` 可达性、case 常量与
  数量上限诊断、`sem_assign`/`sem_forin_*` 调用（其发射留待后续片）、AST 捕获。
- 验证：`\bem_` 在该文件零命中；400 语料诊断快照零差异；if/loop/switch/
  goto/递归用例通过；`make test` 退出 0；`make selfhost-native` 退出 0
  （project 106/106）。
- 未滚种子。

## 2026-10-21 LL12 第十刀：sem_value 取值/地址剥离（C1 第四片）

- `compiler/gen/sem_value.yh` 522→423 行：删除数字/字符/布尔常量装载、
  字符串与枚举/字段名称的数据发射、标识符取值的 `lea/load` 指令。
- 保留：类型与常量标记、`c_res_is_addr` 语义、字符串标签登记
  （`data_str_add`）、元信息名称标签登记（`data_str_add_pool`）。
- 验证：`em_`/`dat_` 在该文件零命中；400 语料诊断快照零差异；
  字符串/常量/聚合用例通过；`make test` 退出 0；`make selfhost-native`
  退出 0（project 106/106）。
- 未滚种子。

## 2026-10-21 LL12 第九刀：全局初始化发射剥离（C1 第三片）

- `compiler/parse/parse_global_init.yh` 1085→1004 行：删除标量/字符串指针/
  数组/切片/结构体初始化的 `.xword`/`.zero`/`.balign`/`.LD`/`em_data_scalar`/
  `em_data_string_body` 共 50 处文本发射。
- 保留：`parse_global_static_*` 的 static_data 登记、AST 捕获、CT 聚合收集、
  接口加载标签（新增 `parse_global_bind_iface_label`，只写 `cval`/`c_data_n`）。
- 验证：`gen.(dat_|em_data_|bss_)` 在该文件零命中；400 语料诊断快照零差异；
  全局聚合/字符串用例（151/152/161/144）运行通过；`make test` 退出 0；
  `make selfhost-native` 退出 0（project 106/106）。
- 未滚种子。

## 2026-10-21 LL12 第八刀：sem_decl 发射剥离（C1 第二片）

- `compiler/gen/sem_decl.yh` 314→234 行：删除 `em_new_label`、`em_alloc_local`、
  `em_save_hidden_ret`、`em_prologue`、`em_copy_body`、`em_epilogue` 与聚合参数
  入口拷贝；保留不透明 C 类型/浮点参数上限/noreturn 校验、C ABI 分派、
  `sym_push` 登记与 `F_AGGPARAM` 事实。
- 验证：`em_` 在该文件零命中；400 语料诊断快照零差异；`make test` 退出 0；
  `make selfhost-native` 退出 0（project 106/106）；单文件 `-o` 正常。
- 未滚种子。

## 2026-10-21 LL12 第七刀：CT 数据发射剥离（C1 首片）

- `compiler/comptime/ct_ir_data.yh` 181→119 行：删除 `.zero`/`.xword`/`.balign`/
  `.LD` 与 `em_data_scalar` 等文本发射；保留 `ct_static_data_record` 登记与
  标量/数组/结构体/切片的形状校验。
- 接口加载的本地标签语义独立为 `ct_ir_data_bind_iface_label`：只登记 `cval`
  与 `c_data_n`，不写文本（LLVM 快照按 label 命名对象）。
- 首次验证发现导入聚合常量副本的 label 缺失导致 3 个用例报「静态数据对象的
  身份或布局无效」；补上纯登记函数后恢复。
- 验证：400 语料诊断快照零差异；`make test` 退出 0；`make selfhost-native`
  退出 0（project 106/106）；CT 运行用例通过。
- 未滚种子。

## 2026-10-21 LL12 第六刀：C3 收尾（旧 SSA 支持判定清零）

- `ast/ast_ir.yh` 268→60 行：只留 `ast_ir_add_inst`/`ast_ir_add_noresult_inst`；
  删除 `ast_ir_expr_supported`、`ast_ir_call_supported`、`ast_ir_type`、
  `ast_ir_void_type`、`ast_ir_promoted_type`、`ast_ir_bindings_supported`、
  `ast_ir_assign_op`、`ast_ir_assign_binding`。
- `ast/ast_ir_call.yh` 141→59 行：只留 init/release/reserve；删除
  `has_suffix`、`name_supported`、`supported`。
- `ast/ast_ir_build.yh` 415 行：删除 `ast_ir_release_built`。
- 验证：`make` 通过；400 语料诊断快照零差异；`make test` 退出 0；
  `make selfhost-native` 退出 0（project 106/106）；单文件 `-o` 正常。
- C3（旧 SSA 替换链）完成；`ast/` 只余 builder 与共享调用缓冲。
- 未滚种子。

## 2026-10-21 LL12 第五刀：旧 SSA 链与运行期桩删除（C3 首片）

- 删除 `compiler/gen/emit_runtime_memory.yh`（555 行；`em_emit_runtime_stubs`
  已无调用者）与 `emit_arm64.yh` 的 `em_emit_linux_syscall_stub`。
- 删除 `ast/ast_ir_cache.yh`、`ast_ir_inline.yh`、`ast_ir_control.yh`、
  `ast_ir_template.yh`（643 行）；`ast_ir_build.yh` 1473→423 行（只留
  `ast_ir_b_*` builder 底层）、`ast_ir_call.yh` 295→141 行、`ast_ir.yh`
  435→268 行（删除模块编排与位移表）。
- 验证：`make` 通过；400 语料诊断快照零差异；`make test` 退出 0；
  `make selfhost-native` 退出 0（project 106/106）；单文件 `-o` 运行正常。
- 未滚种子。

## 2026-10-21 LL12 第四刀：删除 c_backend 字段与旧目标门

- `compiler/cmd/link_cache.yh`：`mb_lld_linux_enabled`、`mb_select_linker` 去掉后端
  条件，Linux x64 原生绝对路径与 `YH_CC` 覆盖恒定生效；链接键固定混入 `'1'`。
- `compiler/cmd/darwin_link.yh`：4 处 `c_backend == 0` 短路删除。
- `compiler/gen/state.yh`：删除 `c_backend` 字段与三处平台默认赋值。
- `compiler/gen/target_info.yh`：删除 `target_legacy_ready`（「旧后端只能发
  AArch64」的门）；`compiler/cmd/driver.yh` 删除对应 4 处调用。
- `compiler/cmd/driver.yh`：`--backend` 只接受 `llvm`（兼容 no-op），`legacy`
  与其他值明确拒绝。
- 验证：全仓 `rg 'c_backend|target_legacy_ready' compiler/` 零命中；`make` 通过；
  400 语料诊断快照零差异；`make test` 退出 0；`make selfhost-native` 退出 0
  （project 106/106）；`--backend llvm` 成功、`legacy` 与未知值给出明确诊断。
- 未滚种子。

## 2026-10-21 LL12 第三刀：worker 旧发射段

- `compiler/cmd/module_worker.yh`：删除 `ast_ir_lower_module`、按文件 `.s`
  区间标记与写出、`.stub.s` 桩对象、`.bss` 与运行期桩发射（544→405 行）。
  check 分支验证受检快照后直接结束；其余一律走 `mb_llvm_emit_module`，
  `front_checked_end` 与统计保持在两条出口。
- `out_dir`/`ir_cache_salt` 参数暂留（调用链在 `module_build`/`build_scheduler`），
  待 C2 清理。
- 验证：`make` 通过；400 语料诊断快照零差异；`make test` 退出 0；
  `make selfhost-native` 退出 0（1m57s，project 106/106）；单文件 `-o` 与
  `check` 正常。
- 未滚种子。

## 2026-10-21 LL12 第二刀：driver 旧分支与 compile 发射段

- `compiler/cmd/driver.yh`：删除 legacy 的 `run_emit_asm_to`、`drv_write_asm`
  与 `<out>.yh-tmp.s` 临时路径；`-o` 直接走新增的 `drv_compile_file`
  （`llvm_emit_single_file`）；`--emit-asm` 只保留 LLVM 分支；usage 的
  `--target` 文案去掉「旧后端仅 AArch64」。418→322 行。
- `compiler/cmd/compile.yh`：删除 `.bss` 与运行期桩发射段，`sem_compile`
  只保留两遍语义、编译期求值与布局，继续作为 `yh check` 的纯语义路径。
  116→105 行。
- 验证：`make` 通过；400 语料诊断快照零差异；`make test` 退出 0；
  `make selfhost-native` 退出 0（1m48s，project 106/106）；单文件 `-o`、
  `--emit-asm`、`check` 均正常。
- 未滚种子。

## 2026-10-21 LL12 首刀：legacy 入口拒绝与 syscall 桩退役

- `compiler/cmd/driver.yh`：`--backend legacy` 明确拒绝（rc 2，提示「已在
  LL12 退役；LLVM 是唯一代码生成后端」）；`--backend llvm` 保留为兼容 no-op。
- `compiler/gen/symbols.yh`：删除 Linux syscall 旧汇编桩发射，保留
  `prelude_add_linux_syscall6` 的语义登记；Linux 入口由
  `backend/llvm_runtime.yh` 的 `linux_syscall6` 提供。
- 验证：`make` 14s 通过；400 语料诊断快照零差异；`make test` 348/349
  （1 个平台跳过，fail 132/132、pass 8/8、统计 6/6）；`make selfhost-native`
  退出 0（1m43s，project 106/106）；legacy 显式调用报错、LLVM 与默认路径
  编译并运行 `hello` 正常。
- 已知过渡红门（C5 统一迁移，不计入本轮失败）：`tests/bench/run_all.sh` 的
  7 处 legacy 基线、`runtime-memory.py` 的 legacy 段、`llvm-darwin-target.py`
  的 `legacy-build`/`legacy-run`、`llvm-darwin-selfhost.py` 的 A 代、
  `native-selfhost.py --backend legacy`。
- 未滚种子。

## 2026-10-21 CircleCI 三端全绿与 tag Release 验证

- CircleCI 分支流水线在 `9438244` 三端全部 success：Linux/AArch64、
  Linux/x86_64、Darwin/ARM64（`m4pro.medium` + Xcode 26.5）。
- 修正 CircleCI 项目元数据不是 `lalavender/x` 的问题：显式设置
  `GITHUB_REPOSITORY=lalavender/x`；取 Release 种子前拒绝 LFS 指针兜底。
- Darwin 首次宿主构建缺 CMake/Ninja，已加入 job 依赖。
- tag `ci-selftest-20261020b` 验证 `release` workflow：三端 cc4 打包、
  `publish` 创建 Release；资产内二进制名为 `yh`，`fetch-release-seed.py`
  成功回读 x64 种子。测试 tag/release 已清理，正式 Release 0.0.5 保留。
- 最新 Release `0.0.5` 的 Linux x64/arm64 资产已替换为当前自举种子。

## 2026-10-21 os/sys OS0 与 OS1 文件闭环首片

- 新增 `libs/sys/00_types.yh`（Timespec、is_error、error_code）、
  `10_constants.linux.{arm64,x64}.yh`（NR_*、O_*、AT_*、errno）、
  `20_raw.linux.yh`（raw6）与 `30_file.linux.yh`（open_at/read_fd/write_fd/
  close_fd/create_dir_at/remove_at/rename_at）。
- 新增 `libs/os/00_model.yh`（Error/ErrorKind、FdResult、IoResult、
  OpenOptions、DirEntry）与 `file.linux.yh`（open_path/read_some/write_some/
  close_file/make_dir/remove_path/remove_dir_path/rename_path）。旧 os.yh
  接口与 -1、宿主标志语义保持不变。
- 新增 `.yh` 用例：`sysresult`、`osmodel`（跨平台），`sysraw`、`sysfiles`、
  `osfiles`（Linux 专属，非 Linux 宿主不注册）；接入
  `tests/modules/build-check.py`。
- 验证：Darwin/arm64 `make`、`make test` 通过；`build-check --backend llvm`
  中 `os0-sys-result-model`、`os0-os-result-model` 通过。Apple Container
  `debian:trixie`（Linux/arm64，入库种子）运行五个用例全部退出 0；
  `yh -target x86_64-unknown-linux-gnu check` 通过，未宣称 Linux/x64 原生运行。
- 未关闭：OS1 的强制短写/EINTR 注入、CLI 重新验收、Linux/x64 原生门；
  OS2 目录/cwd 起均未实施。未运行 `make selfhost-native` 收尾与 `make seed`，
  种子未改动。
- 设计/方案/README/索引已同步；详见
  [完成记录](01-finished/yh-os与sys-OS0-OS1文件闭环-2026-10-21.md)。

## 2026-10-20 AST 快照文件命名消歧

- 将 `compiler/ast/` 中原 `checked_module*` 快照所有权与 lowering 文件统一改名为
  `module_snapshot*`，避免与实际 AST 校验器 `compiler/check/checked_module.yh` 混淆。
  `CheckedModule`、`checked_module_capture` 与 `check.verify_checked_module` 等
  类型/API 名称保持不变；同步更新源码注释、编译器 README 和项目验收 fixture 名称。
- Apple Container Debian stable-slim（Linux/arm64）验证：`make`、`make test`、
  `make selfhost-native` 均退出 0。固定点 129 项产物一致，自解析 107 个源文件，模块
  用例 18/18、项目验收 106/106；语法正例 78/78、反例 42/42，运行语料 344/349
  （5 项平台跳过），fail 132/132、pass 8/8、代码统计 6/6。
- 种子哈希保持
  `8ea2a9acc20438b385ccddd522b50b8dd4749423c8db2695c758296ada343b8c`，未执行
  `make seed`。方案与映射见[实施方案](02-plan/yh-AST快照文件命名消歧方案.md)，
  验证记录见[完成报告](01-finished/yh-AST快照文件命名消歧-2026-10-20.md)。

## 2026-10-20 AST 一致性检查全部迁入 check

- 在 arena 校验迁移基础上，将原 `ast/checked_module_verify.yh` 快照一致性验证
  迁至 `check/checked_module.yh`，公开统一入口 `check.verify_checked_module`；删除
  `ast.checked_module_verify`，无转发包装。
- 新增 `ast.CheckedModuleView` 借用视图。`checked_module_capture` 只负责安全复制、
  失败清理和所有权提交；`cmd/module_worker`、`cmd/llvm_emit` 在快照消费前调用
  check，`ast` 不反向依赖 `check`。SSA verifier 仍由 `ir` 负责。
- 扩展 `llvmchecked` `.yh` 项目用例：验证空句柄拒绝、两份独立快照、损坏类型闭包
  被拒绝、修复后通过、释放后句柄失效且未影响另一份快照。`llvmlower` 也在 lowering
  前调用快照校验。AST arena 探针仍覆盖四类节点校验、捕获关闭与只读行为。
- Apple Container `debian:stable-slim`（Linux/arm64）验证：`make`、`make test`、
  `make selfhost-native` 全部退出 0。语法正例 78/78、反例 42/42；运行语料
  344/349（5 项平台跳过）、fail 132/132、pass 8/8、代码统计 6/6；自举固定点
  129 项产物一致，自解析 107 个 `.yh` 文件，模块语料 18/18、项目验收 106/106。
  `yh check` 有效/无效项目行为正确，且未生成后端产物或调用汇编器/链接器。
- 容器未准备 LLVM host 桥/SDK；自举日志提示过渡种子路径。种子哈希仍为
  `8ea2a9acc20438b385ccddd522b50b8dd4749423c8db2695c758296ada343b8c`，未执行
  `make seed`。
- 设计与详细验证见 [check 模块设计](03-design/yh-编译器check模块拆分设计.md)、
  [CheckedModule 方案](02-plan/yh-CheckedModule校验迁入check方案.md)和
  [完成报告](01-finished/yh-check模块拆分-2026-10-20.md)。

## 2026-10-20 AST 一致性校验迁入 check 模块

- 新增 `compiler/check/verify.yh`，将表达式、语句、声明和函数上下文四项 AST
  校验迁出 `ast`；`ast.AstView` 只读借用原 arena，不复制或转移所有权。统一入口
  保持检查顺序、具体诊断和调用方的外层失败诊断。
- `cmd/module_worker` 的两处及 `cmd/llvm_emit` 的一处调用迁移；删除旧四个 AST
  校验导出。`check` 仅依赖 `ast/gen`，`parse` 不依赖 `check`。
- 新增 `tests/modules/projects/astcheck/` 验证成功、损坏引用、绑定与编译期 `$for`
  关联、捕获关闭和只读行为；`llvmlower` fixture 同步改用新校验入口。
- Apple Container `debian:stable-slim`（Linux/arm64）验证：`make`、`make test`、
  `make selfhost-native` 全部退出 0。语法 78/42，运行 344/349（5 项跳过）、
  fail 132/132、pass 8/8、统计 6/6；自举固定点 128 项产物一致，自解析 106 文件，
  模块语料 18/18、项目验收 106/106；`yh check` 未生成后端产物。
- 种子哈希校验通过（`8ea2a9acc20438b385ccddd522b50b8dd4749423c8db2695c758296ada343b8c`）；
  未执行 `make seed`。方案和边界见[设计](03-design/yh-编译器check模块拆分设计.md)、
  [实施方案](02-plan/yh-check模块拆分实施方案.md)及
  [完成记录](01-finished/yh-check模块拆分-2026-10-20.md)。

## 2026-10-20 CircleCI 三端与 tag Release 发布

- CircleCI 增加 `linux-x86_64` 与 `darwin-arm64` 作业：前者从最新 Release 取
  x64 种子，后者用 `m4pro.large` + Xcode 26.5、固定 Darwin SDK/桥；三端均跑
  各平台专项门、语法/运行语料和 `make selfhost-native SKIP_CORPUS=1`。
- `bin/yh-linux-x64` 不再入库：其自举二进制已替换最新 Release `0.0.5` 的
  `yh-0.0.5-linux-x86_64.tar.gz`（cc4 SHA-256 `fda39ef3…`），`bin` 中
  x64 二进制与哈希已删除；开发机用 `make fetch-seed` 取最新 Release。
- CircleCI 分支流水线三端每次都从最新 GitHub Release 取种子；tag 流水线取
  上一版 Release（排除当前 tag）。
- 新增 CircleCI `release` workflow：tag push 时三端并行构建，通过
  `SELFHOST_KEEP=1 SELFHOST_WORKDIR=dist/selfhost` 保留 cc4，打包 cc4 为
  `dist/yh-<tag>-<platform>.tar.gz` 与 `.sha256`；`publish` 作业用
  `GITHUB_TOKEN` 创建/更新 GitHub Release。
- `Makefile` 新增 `SELFHOST_KEEP`/`SELFHOST_WORKDIR`，默认行为不变。
- 验证：CircleCI 配置与 GitHub workflows YAML 解析通过；`make quick` 通过。
- **已完成 Release 种子更新**：x86_64 在 Rosetta 容器内从 0.0.5 种子冷编 A，
  A→cc2→cc3→cc4 固定点通过，cc4 在空 `PATH` 下编译/运行 `.yh`；x64 cc4
  SHA-256 `fda39ef3…`，已替换 Release 0.0.5 的 x86_64 tar/sha 资产。
  最新 Release 的 arm64 资产原只有 435KB（不可用），已同步替换为当前
  141,752,552 B 自举种子（SHA-256 `4d13e297…`）。
- `tools/fetch-release-seed.py` 下载资产时核对 API size，并对截断/连接中断
  重试 3 次；两条平台种子均已通过实际 fetch 验证。
- **待办**：首次 tag 发布需在 CircleCI 配置 `GITHUB_TOKEN`（repo 权限），
  并观察三端 cc4 打包与 Release 上传；本地未推送测试 tag。

## 2026-10-20 CI：CircleCI 原生 AArch64 与 GitHub 去重

- 新增 `.circleci/config.yml`：`arm.large` 原生 Ubuntu 24.04 跑 Linux/AArch64
  `make bootstrap`、F1 专项、第 2/3 层语料与 `make selfhost-native SKIP_CORPUS=1`；
  独立 `antlr` 作业跑参考语法门。种子用 Git LFS 拉取，固定 LLVM/lld 宿主缓存
  到 `tmp/llvm-migration`，键覆盖 SDK 锁、构建脚本、宿主验证器与桥源码。
- GitHub Actions 的 `linux-arm64` 改为仅手动 `workflow_dispatch` 的 QEMU 回退，
  日常 arm64 由 CircleCI 原生机器承担；`linux-x86_64`、`darwin-arm64` 与
  Release 在手动语料后改用 `make selfhost-native SKIP_CORPUS=1`，避免重复跑语料。
- Release 的 arm64 作业补 `YH_LLVM_HOST=1`、`libxml2-dev`、`binutils/xz-utils`
  与固定 LLVM/lld 宿主缓存；超时从默认值提高到 240 分钟。
- 验证：两份 workflow 与 CircleCI YAML 均通过 YAML 解析；本地 `make test-code-stats`
  与 `make quick` 通过。
- **CircleCI 首次实跑（commit `9e1dec3`）**：`antlr` 与 `linux-arm64` 均 success；
  arm64 从启动到完成约 4 分钟。首次发现 `antlr` 的 `cimg/base:stable` 仍是
  Ubuntu 20.04 + 旧 pip，不支持 `--break-system-packages`，已改用
  `cimg/python:3.12` 后通过。
- **GitHub Actions 阻塞**：同一提交的 antlr/x64/darwin 作业在启动前失败，
  注解为账号账单/消费限额（`recent account payments have failed or your
  spending limit needs to be increased`），不是工作流代码错误；账单恢复后需复跑。

## 2026-10-20 yh 编译器源码规模统计工具

- 新增 `tools/yh-code-stats.py`，按 yh 的字符串、字符、转义与注释词法边界
  统计 `compiler/**/*.yh`，输出物理行分类、职责目录占比及大文件排行，支持 JSON。
- 新增 `make code-stats` 与 `make test-code-stats`；源码统计用例也并入 `make test`。
- `tests/tools/yh-code-stats/` 新增 `.yh` 固定夹具及 Python 检查，覆盖注释边界、
  行尾/多行混合注释、CRLF、空白行、转义、错误输入、缓存目录排除与稳定 JSON。
- 新 worktree 的已提交基线：104 个 `.yh` 文件、50,415 物理行，代码 44,843 行，
  纯注释 3,897 行，空白 1,675 行，混合 698 行；混合行是代码行子集。
- [实施方案](02-plan/yh-编译器代码统计工具方案.md)记录统计口径和 worktree 基线差异；
- `make code-stats` 报表与上述基线一致；统计脚本用例 6/6 通过。
- 在 Darwin/arm64 上使用固定 SDK 26.5 执行
  `SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk make bootstrap`，冷编通过；
  随后使用同一 `SDKROOT` 执行 `make test` 与 `make selfhost-native` 均全绿。
  `make test`：ANTLR 正向 78/78、反向 42/42、运行语料 348/349（1 个平台跳过）、统计工具 6/6；
  `make selfhost-native`：两代固定点 24 个输出一致、自解析 104 个源码文件、模块 18/18、
  项目构建案例 105/105。未执行 `make seed`，没有改变入库种子。

## 2026-10-20 编译器代码规模统计工具方案交付

- 用户确认首版关注代码行、注释、模块占比与大文件；建议以 Python 标准库
  实现 `tools/yh-code-stats.py`，提供文本/JSON 与独立 `make code-stats`。
- 明确 yh 源码、全平台变体、职责目录及混合注释行的统计口径；按目录汇总时
  说明 `cmd/` 对应 `module main`，不把 C/C++ 桥、SDK 或冻结测试副本计入总数。
- 当前工作区只读盘点为 104 个 `.yh` 文件、50,497 物理行，14 个文件超过
  1,000 行；该盘点未区分代码与注释，不作为有效代码行数。
- [方案](02-plan/yh-编译器代码统计工具方案.md)与 [STAT0–STAT3 待办](todo.md)
  已记录；本轮仅文档设计，未实现工具、未修改编译器、未运行构建或自举门。

## 2026-10-20 C/C++ 代码使用 yh 重写与链接的可行性分析

- 盘点当前工作区 C/C++：生产桥 5 文件 / 747 行；区分 ABI 测试、性能对照、
  旧示例和第三方 SDK，建议保留独立 C 验证程序。
- `bridge.c` 可迁到 yh；lld 桥的大部分配置逻辑可迁，`lldMain` C++ 接口仍需
  最小适配层；弱桩和自举归档迁移不能直接按文件替换。
- `tmp/c-bridge-analysis/` 探针由 yh 编译，直接引用 25 个 LLVM C API，
  排除项目桥与 lld 归档后链接固定 LLVM，O0/O2 对象生成与运行通过；
  无动态 LLVM/lld 依赖。既有 `llvm-darwin-abi.py --suite full` PASS。
- [完整分析](01-finished/yh-C与C++代码重写可行性分析-2026-10-20.md)与
  [候选任务](todo.md)已记录；本轮未修改编译器、构建脚本或种子，未执行
  完整构建/自举门或其他平台门，迁移尚未实施。

## 2026-10-20 project.toml 静态库分组链接方案交付

- 用户确认 `[link]` 自定义组名，`yh build` 默认全部链接；传入
  `--link <组名>` 时仅选择指定组。方案建议重复参数以选择多组。
- 方案包含可选 whole 加载、按输出目标的库配置、只检查选中归档、内容哈希
  与链接缓存、自举候选引导及新旧归档注入互斥；实施任务已记入 todo。
- 详见[实施方案](02-plan/yh-project-link静态库实施方案.md)和
  [ADR-0016 提议](adr/0016-yh项目静态库分组链接.md)。
- 本轮仅文档方案；未修改编译器、未实施功能、未运行构建或自举门。

## 2026-10-20 Linux/AArch64 LLVM F1：运行时、AAPCS64、内嵌 lld 与默认切换

- **范围**：`--backend llvm --target aarch64-unknown-linux-gnu` 的运行时、C ABI、
  O0/O2 与容器门；未切默认后端、未滚种子。
- **运行时**：AArch64 syscall（`x8` + `svc #0`）、`mmap=222`/`munmap=215`/
  `write=64`；Linux `va_list` 是 32 字节结构，LLVM `va_arg` 指令不展开
  `gr_top/gr_offs` 寄存器保存区，改为 `yh_va_next` 按 AAPCS64 显式取寄存器/栈槽，
  `printf` 全部格式复用；x64/Darwin 原路径不变。
- **C ABI**：新增 Linux `aapcs64` 分派，AAPCS64 聚合/HFA 复用 Apple 分类器；
  标量、`_Bool`、混合整浮、HFA2/HFA3、16 字节聚合、24 字节 sret/间接参数与
  C↔YH↔C 函数指针回调通过。Linux/AArch64 不写 `signext/zeroext`（GCC C 调用方
  只保证 32 位扩展；强加属性会让 O2 读到高位垃圾，cinterop 由 8 复现并修复）。
- **门禁**：新增 `make test-llvm-linux-arm64` 与
  `tests/selfhost/llvm-linux-arm64.py`、`.yh`/`.c` 探针；`asm-symbols-safe`
  只约束旧发射器，build-check 的属性断言按目标放宽。
- **验证**（Apple Container，Ubuntu 24.04 原生 arm64，6G/6CPU）：
  `test-llvm-linux-arm64` O0/O2 全绿；`tests/yh-run` O0/O2 各 344/349
  （5 个 Darwin SKIP）；modules 18/18；build-check O0/O2 105/105；
  旧后端 `make test` 编译器层 78/78 + 42/42、运行 344/349、
  `make selfhost-native` 全绿。
- **自举（第一片）**：容器内当前编译器以 LLVM 目标冷编 A，A→B→C，三份二进制
  SHA-256 均为
  `58859df932e6ddd2b3e6e3606d45d269e55e672c4fe4a17b215d84b0260e992b`
  （72,052,424 B AArch64 ELF）；第二阶段已补默认自举与 O2。
- **第一片边界（已由第二批关闭）**：当时最终链接回落宿主 `gcc`，内嵌 lld、
  默认切换与种子滚动未完成；Darwin `make` 与 `make test-llvm-darwin` 复跑全绿。
- **第二批（同日）**：Linux/AArch64 内嵌 lld 21.1.8 接通，固定 SDK 增加 arm64
  lld/Polly 包；自举闭包改为 `selfhost-flags.txt`，新种子不再烘焙构建机路径。
  `state.yh` 将 Linux/AArch64 默认后端切 LLVM；`native-selfhost.py` 支持
  Linux/AArch64 LLVM 与旧种子 legacy 过渡；`llvm-cache.py` 参数化到双架构；
  F1 门新增默认后端 + 空 PATH 内嵌 lld + 编译器静态桥审计。
- **最终验证**：容器内 `make test` 全绿（运行 344/349，5 个 Darwin SKIP）；
  `make selfhost-native` 全绿（cc3→cc4 24 产物固定点、自解析 104、F1 O0/O2、
  LLVM 缓存门、项目 105/105）；O2 连续自编 B/C SHA-256 相同。
- **种子**：`bin/yh-linux-arm64` 已滚为默认 LLVM 编译器，
  SHA-256 `4d13e297547bf3616ab75464e34bd8c18d2ca6f758b83dc41703f9322e087b9a`
  （141,752,552 B），种子内无构建机闭包路径。
- 详见[完成记录](01-finished/yh-Linux-ARM64-LLVM-F1-2026-10-20.md)与
  [实施方案](02-plan/yh-Linux-ARM64-LLVM接入实施方案.md)。

## 2026-10-20 构建简化：一条命令、失败前置、身份去路径

- `make bootstrap`：幂等 `llvm-host` + 冷编，首次/换机只需一条命令；
  `make llvm-host` 保留为“只准备闭包”。
- Darwin 固定 SDK 就绪后 Makefile 自动 `export SDKROOT`（显式值优先），
  `make test` / `make selfhost-native` 不再需要手工导出，C 互操作 9 个
  project case 恢复。
- `tools/llvm-darwin-sdk.py` 在 `resolve_sdk_root` 期间拒绝含 `arm64e.x1`
  的 TAPI（与 `llvm-darwin-sdk-bundle.py` 的 `KNOWN_UNSUPPORTED` 同边界），
  SDK 27 在秒级失败并提示 26.x，不再浪费整轮 LLVM 构建；SDK 契约门补正反例。
- `tools/llvm-darwin-host.py` 的 `lld_identity` 去掉 `sdk_root` 与
  `selfhost_flags` 路径，只保留归档内容与构建参数：同一份源码/归档在不同
  worktree 生成相同身份的编译器（跨机可复现的前提）。
- **验证**（无 `SDKROOT`、默认 PATH）：`make bootstrap`、`make test`（348/349）、
  `make selfhost-native`（固定点、自解析、语法 42/42、运行 348/349、
  modules 18/18、project 105/105、runtime/cache/闭包门全 PASS）、
  `make test-llvm-darwin`、`make selfhost-llvm-darwin` 全绿；滚种子后
  `bin/yh-darwin-arm64`（`c3b0c9b7…`，73,541,840 B）仍 0 处构建机路径，
  复跑 `make test` / `make selfhost-native` 全绿。

## 2026-10-20 Darwin 自举闭包改为构建机提供（Zig 式）

- **背景**：0.0.5 种子把桥与 LLVM/lld 静态闭包的 73 处构建机绝对路径编进 lld
  配置，`make`/`make selfhost-native` 只在种子构建机的路径下可用；换机器/换
  worktree 会链接不存在的归档，`-lc++` 也只能由宿主 SDK 解析。
- **改动**：
  - `compiler/llvm/lld_bridge.cpp`：新增 `YH_LLVM_SELFHOST_FLAGS`（每行一个
    参数）运行时读取；文件不可读返回 -1、空文件视为无效；桥内常量只作过渡回退。
  - `compiler/cmd/link_cache.yh` / `darwin_link.yh`：闭包计数与参数统一走访问器，
    缺失/损坏给出可操作诊断；闭包参数计入 Darwin 链接键（换闭包即重链接）。
  - `tools/llvm-darwin-host.py`：`prepare` 生成 `selfhost-flags.txt` 并把路径与
    摘要写进 `host.json`；`lld_link_config.h` 不再烘焙闭包；`shim` 输出该文件。
  - `tools/seed-build.py`：`--llvm-mode off` 不再注入自举标记；准备成功时导出
    `YH_LLVM_SELFHOST_FLAGS`。
  - 自举脚本：`native-selfhost.py` 第一代经 `YH_CC` 用本机 shim 链接，避免旧种子
    把旧桥带进新编译器；`llvm-darwin-selfhost.py` 从 `host.json` 读取闭包文件。
  - 新门 `tests/selfhost/llvm-darwin-selfhost-flags.py`：普通链接不注入、运行时
    文件优先（坏路径进入诊断）、缺失/空文件有诊断、真实闭包可链接运行且无动态
    LLVM；`make selfhost-native` 与 `make test-llvm-darwin` 均接入。
  - 种子卫生：`tools/selfhost_snapshot_gate.py` 增加 `$HOME` 路径检查，
    `make seed` 拒绝带构建机路径的种子，`--verify-seed` 对旧种子只告警。
- **验证**（Darwin/ARM64，`SDKROOT=.../MacOSX26.5.sdk`）：
  - `make`、`make test`（348/349，1 SKIP）、`make selfhost-native` 全绿：
    固定点、自解析 104 文件、语法 42/42、运行 348/349、modules 18/18、
    project 105/105，runtime/cache/闭包门全 PASS。
  - 滚种子后 `bin/yh-darwin-arm64`（`ad52b36c…`，73,541,840 B）中构建机路径
    0 处；把种子复制到 `tmp/reloc/` 冷编候选编译器仍成功。
- **边界**：首次仍需 `make llvm-host`（569MB 固定 SDK）；SDK 27 的
  `arm64e.x1` TAPI 超出内嵌 lld 21，暂用 26.5；`compiler/darwin-sdk` 仍不含
  libc++（交叉构建边界见遗留边界文档）。

## 2026-10-19 自带 Darwin SDK stub（Zig 式交叉链接）

- `compiler/darwin-sdk/` 增加聚合 `usr/lib/libSystem.tbd`（334KB，Apple SDK
  26.4 TAPI，取自 Zig 0.16 `libc/darwin`）、`SDKSettings.json`（Version 26.4）
  与 `manifest.json`（SHA-256/来源/许可说明）。
- `compiler/cmd/darwin_link.yh` 查找顺序：`SDKROOT` → `YH_DARWIN_SDK` →
  可执行文件附近 `darwin-sdk`/`compiler/darwin-sdk`/上层目录 → 原生 `xcrun`；
  非 Darwin 交叉不再强制宿主 SDK。`tools/llvm-darwin-sdk-bundle.py` 支持
  校验/从 Zig 或本机 SDK 重新生成（拒绝 SDK27 `arm64e.x1`）。
- `tests/selfhost/llvm-darwin-bundled-sdk.py`：清空 SDKROOT、PATH 仅假工具
  （无 xcrun/clang/ld），链接运行成功且 `LC_BUILD_VERSION sdk 26.4`；
  显式 SDKROOT（26.5）覆盖生效；`make test-llvm-darwin` 20 项全绿。
- 纯 `.yh` 程序交叉链接已不再依赖 Xcode/CLT SDK；C 源、libc++/Darwin 目标包、
  frameworks/Objective-C、SDK 版本矩阵/许可仍见
  [遗留边界](03-design/yh-Darwin交叉编译遗留边界.md)。
- 详见[完成记录](01-finished/yh-DarwinSDK-bundle-2026-10-19.md)。

## 2026-10-19 macOS/ARM64 LLVM：F2 移植、默认切换与 Darwin 种子

- **F2 移植**：按文件三方合并到 LL11（aa6e424）；上游已含的 RS1c/RS3b/LL11
  改动不重复搬运，F2 独有代码/测试/工具 51 个文件入库。
- **默认切换**：`DARWIN+ARM64` 默认 LLVM；Makefile 选择 Darwin runtime/cache 门；
  `native-selfhost.py` 支持 Darwin LLVM 与旧种子 legacy→LLVM 过渡代；
  `build-check` 补宿主 triple/opt 缺省；`check.py` 修正 Darwin target 推断。
- **关键修复**：`YH_LLVM_SELFHOST=1` 从全局 Makefile export 收窄为“只构建
  compiler/ 自身”，避免普通程序被 force-load 桥/LLVM（runtimebytes 曾因此
  导入 malloc/free/memmove 与 C++ 符号）。
- **默认门**：`tests/selfhost/llvm-darwin-default.py` 断言无 `--backend` 时
  emitted=checked、fallback=0、产物在 Darwin LLVM 目录、默认 asm/IR 正确。
- **种子**：`bin/yh-darwin-arm64` 72MB（`2be836b7…`），Mach-O arm64、ad-hoc
  签名有效；新种子冷编、默认门、`make test`（347/348）、`make selfhost-native`、
  `test-llvm-darwin`（19 项）、`selfhost-llvm-darwin` 全部通过。
- **后置**：20 轮性能、RS2/RS3/R2c、F2-9 交叉引导、macos-14 实跑。
  详见[完成记录](01-finished/yh-macOS-LLVM-F2-10-默认切换与种子-2026-10-19.md)。

## 2026-10-20 yh 与 C / Zig / Rust 性能对比（LLVM 后端自举版）

- **目的**：用同一段逻辑在四种语言分别实现，量化 yh 的二进制体积、启动速度、
  编译速度与生成代码质量。macOS/arm64（Apple M1）实测，对照 Homebrew clang 23.1.1、
  Zig 0.16.0、rustc 1.93.0。**用 0.0.5 的 LLVM 后端自举种子**（`bin/yh-darwin-arm64`
  73,539,408 B，F2-10 默认切 LLVM）作为 yh 编译器，并用同一份编译器只切
  `--backend legacy|llvm` 做**替换前后归因**。
- **方法学**（`tests/bench/`，`bash tests/bench/run_all.sh` 一键复现）：同时采集
  父进程 wall 与子进程 `wait4` 的 `utime+stime`、max RSS；采样 300 次取中位数；
  设**空程序基线**（`src/empty.*`）把「运行时初始化」与「I/O 成本」拆开；
  设**两个循环基准**——可被 LLVM loop-idiom 折叠的 A1（测优化器强度）与串行依赖链
  的 A2（测真实 codegen 质量）；Zig 冷编译用隔离 `--global-cache-dir` 测，不污染
  用户缓存。四种语言 hello world 动态依赖一致（均只链 libSystem），输出与计算
  基准结果逐位相同；用 Apple clang 21.0.0 复测 A2 复核（26,393 vs 26,392 µs）。
- **代码质量（结论已反转）**：A2 依赖链循环 yh-LLVM **27,934 µs**，与 clang 26,392
  相差 5.9%、Rust 26,893 差 3.9%、Zig 26,241 差 6.5%——**追平 LLVM 阵营**；
  递归 `fib(30)` **3,446 µs**，比 clang 快 39%、Rust 快 43%、Zig 快 39%；
  可折叠循环 974 µs，比 clang 快 2.5×。legacy 后端同基准是 196,451 µs，
  即 **LLVM 后端带来 7.0× 加速**（递归 3.0×、可折叠循环 80.6×）。
  **前一版（legacy）报告的「7.4× 短板」不再成立。**
- **关键洞察**：把 `main` 机器指令数拉出来（`otool -tvV` 统一口径）——yh-LLVM 368 条
  vs legacy 293 条 vs clang -O2 21 条。**LLVM 后端指令数比 legacy 还多 26%，却快 7×**。
  代码质量的关键不是指令数而是**每条指令背后有没有内存往返**：legacy 每个 SSA
  临时值都走「压栈→弹出」，clang 全是寄存器操作。
- **编译速度（四者最快）**：yh-LLVM 稳态 **25.5 ms** / 冷 **76.0 ms**，是 rustc(107.8)
  的 1/4.2、clang(149.7) 的 1/5.9、Zig(134.6) 的 1/5.3。legacy 同项 185.8/561.1 ms。
  原因可归因：`yh --emit-asm`（仅前端+代码生成）只要 **3.3 ms**，比 clang 编译
  hello.c 整条链路（145.1 ms）快 **44 倍**；legacy 时代的 183.7 ms 里 98% 是外部
  `clang` 驱动固定开销（假 clang 包装器抓到真实调用是 `clang -o <out> <out>.yh-tmp.s`），
  切 LLVM 后端后这条外部链路整体消失。
- **体积**：yh-LLVM `__text` 1,892 B（-O2 为 1,392 B）、空程序 264 B；文件 50,224 B
  比 clang 多 17 KB，差异全是 Mach-O 段页对齐（yh 多一个 `__DATA` 页），非代码量。
  Rust 442 KB 主体是链接进来的 `std`（`__text` 216 KB），与调试信息无关。
- **启动**：yh-LLVM CPU 956 µs ≈ clang 940 ≈ Zig 959，Rust 1,247。空程序基线显示
  Rust 慢的 289 µs **全在 std 运行时初始化**；yh 切 LLVM 后初始化 +31 µs（+3.4%，
  桥初始化固定开销），换 7× 运行加速很划算。max RSS yh 1,622,016 B 低于 Rust/Zig。
- **已知阻塞（新发现）**：拉取 0.0.5 后 `make` 在本工作区自举失败——
  `ld64.lld: library not found for -lc++`。根因：**入库种子硬编码了 73 处构建机
  绝对路径**（`/Users/lavender/.codex/worktrees/macos-llvm/x/tmp/llvm-migration/...`，
  `strings -a bin/yh-darwin-arm64 | grep -c codex/worktrees` = 73；0.0.4 legacy 产物
  为 0），自举时 `mb_darwin_selfhost_enabled()` 把这些路径喂给链接器。验证：
  `cd compiler && YH_LLVM_SELFHOST=0 ../bin/yh-darwin-arm64 build -o ../yh-legacy`
  **构建成功**（1,956,384 B）→ 阻塞只在桥注入路径；且用 `YH_LLVM_SELFHOST=0` 的产物
  跑 `--backend llvm` 明确报「内嵌 LLVM 桥未链接」，印证桥是 LLVM 后端前提。
  **不影响用已入库种子做编译与对比**（本轮数据即由此产出），但影响在仓库内继续自举
  0.0.5 之后的代。已记入 `docs/todo.md`。
- **边界**：全部数据为 macOS/arm64，Linux 需重测（dyld vs ld.so、`ru_maxrss` 单位差）；
  相对关系预期成立。未做数组/指针吞吐基准（语义仍在语料阶段）。
  本任务只加基准资产与文档，未改编译器实现、未滚种子。
- **门禁**：`make test` 343/344（1 例平台专属跳过）；`make selfhost-native` 退出 0
  （项目用例 104/104）。新增 `tests/bench/` 不在既有门禁扫描路径内。
  详见[完成记录](01-finished/yh-与C-Zig-Rust性能对比-2026-10-20.md)。

## 2026-10-19 LL11：默认切换、x64 种子与隔离环境验证

- **默认后端**：`compiler/gen/state.yh` 在 Linux/x86_64 宿主默认 `c_backend=1`
  （LLVM），无需 `--backend`；arm64/Darwin 当时仍走 legacy（F2-10 已切，见上方）。
- **x64 种子**：`bin/yh-linux-x64` + `.sha256`（`c6733eb2…`）已滚，冷编、
  单文件编译/运行通过；Makefile 对 `linux-x86_64` 自动 `export
  YH_LLVM_SELFHOST=1`，runtime-memory 走 `--llvm-x64`、缓存专项走
  `llvm-cache`、scratch-isolation 降为 `--jobs 4`。种子 135MB 超过 GitHub
  100MB 限制，**不入库**，由 Release `seed-llvm-x64-2026-10-19` 分发
  （`yh-linux-x64` + `.sha256`）；`.gitignore` 已忽略并留下载说明。
- **测试适配**：`native-selfhost.py` 支持 LLVM 模式快照（`--backend llvm
  --emit-llvm`、`llvm/<tag>.ll` 固定点）；`runtime-memory.py` 的 ARM64 汇编
  契约显式走 legacy；`check.py` 非 AArch64 跳过寄存器同名检查、编译超时
  180s。分段验证：固定点 24 产物、自解析 100/100、语法 42/42、运行 343/343、
  scratch-isolation 4/4、llvm-cache、runtime-memory --llvm-x64、modules 18/18。
- **隔离环境验证**：新增 `tests/selfhost/llvm-isolation.py` 与 `make
  llvm-isolation`：bwrap + `PATH=/nonexistent` 下单文件编译/运行、项目构建、
  冷编自举全过；`readelf -d` 无 LLVM/lld 依赖，`strace execve` 无外部 LLVM
  旁车，自举 `fallback_functions=0`。详见
  [完成记录](01-finished/yh-LLVM-LL11隔离环境验证-2026-10-19.md)。
- **未完成**：20 轮性能对照/回退归因（用户暂缓）、发行/CI 文档同步；
  R2b 硬门（RS2/RS3/R2c）仍开，不宣布 LL11 全量完成。

## 2026-10-19 os/sys 标准库联合规划（可用性优先）

- 用户选择标准库可用性优先；交付[联合设计](03-design/yh-os与sys标准库设计.md)、
  [OS0–OS8 实施方案](02-plan/yh-os与sys标准库实施方案.md)和
  [提议 ADR-0015](adr/0015-yh-os与sys标准库分层.md)。先文件闭环，再目录、环境、
  进程与 io/time 收敛；编译器迁移和 Darwin 新接口另排，尚未实施。
- sys 保留 -errno 与单次调用；os 新接口显式错误/自有选项，旧接口保留兼容。
  明确借用缓冲/envp、exec 失败握手与子进程回收；修正旧 sys 文档对 x64 入口、
  OS/架构后缀和 os.platform/arch 的过时描述，沿用现行 LLVM 与本地/CI 分工。
- 文档链接、围栏、空白与 diff 检查通过；本任务只写文档，未构建、未改实现、
  未滚种子。工作区 CLI 的并行改动保留。详见
  [交付记录](01-finished/yh-os与sys标准库规划交付-2026-10-19.md)。

## 2026-10-19 cli 用例迁入 libs/cli/test（与全局测试解耦）

- 按用户要求把 cli 的 fixture 与用例从 `tests/modules/projects/` 迁到
  `libs/cli/test/`：climodel/clibasics/cliactions/clicommands/cliextensions/clihelp
  六个项目 + 自有 runner `libs/cli/test/run.py`（9 条用例，构建后用显式 argv 运行，
  断言退出码与 stdout/stderr 子串；默认编译器仓库根 `./yh`、标准库根 `libs/`）。
- `tests/modules/build-check.py` 移除 9 条 cli 用例、`stdlib-argv` 分支与
  `case()` 的 argv/stdout_contains/stderr_contains 扩展，恢复原有签名；
  全局 project cases 由 113 变为 **104**，cli 覆盖由自有 runner 承担。
- 运行方式：`python3 libs/cli/test/run.py`（结果 9/9）；
  全局门 `python3 tests/modules/build-check.py` 104/104，
  `make test` 343/344，`make selfhost-native` 全绿。
- 文档同步：README 验收节、CLI0–CLI6 完成文档、计划与 finish 中的路径与用例名。
  未滚种子。

## 2026-10-19 cli README 使用说明与 stderr 换行修复

- `libs/cli/README.md` 增加 16 节使用说明（快速开始、解析五步骤、选项、布尔/计数、
  多值、位置参数、子命令与 inherit、组与互斥、解析模式与 initial、自定义类型与校验、
  自定义 action、参数文件、帮助与输出、退出码、生命周期、常见陷阱），
  每个片段都用临时教程项目实际编译运行验证（toy 项目验证后已删除）。
- 修复 `help.yh` 中把换行误写成字面 `\\n` 的问题：`render` 在错误消息与 usage 之间
  输出一个反斜杠而不是换行。修复后缺参数路径的 stderr 是两行：
  `pack: 错误: ...` 与 `usage: ...`。
- 回归：6 个 cli fixture 的构建与 selftest 全过；`make test` 与
  `make selfhost-native` 见下一条验收记录。

## 2026-10-19 CLI6：cli 标准库统一验收与文档冻结

- 逐项核对设计能力表（第 3/8/9/10/11/12/13/14 节）：已实现项全部有运行用例，
  未实现的 `warnings` 通道与分配入口扩展明确保留理由。
- 差分：新增[与 argparse 差异](../03-design/yh-cli与argparse差异.md)，
  用本机 Python 3.14.6 实跑对照值形状/诊断类别/退出码（`--output=a`、`-vvv`、
  缺位置参数、`--cache/--no-cache`、`nargs=2`、负数位置、intermixed、`@file` 展开），
  差异项（缩写缺省、消息语言、默认值展示、整数范围、浮点词法、append 批次等）逐条写明理由。
- 导出面：`libs/cli` 公开声明 87 项，实现细节保持模块私有；README 列出文件划分、
  API、契约、容量上限与未实现边界；标准库设计的 `cli` 章节同步为已实现。
- 检查项：重复解析隔离、结果独立生命周期、分配失败注入（`test_fail_alloc_after`）
  与「未迁移既有入口」均有断言或明确说明。
- 验收：6 个 cli fixture 的 selftest 全部通过；build-check 的 8 条 cli 用例在内，
  project cases **113/113**；`make test` 343/344；`make selfhost-native` 全绿。
- Linux/arm64 容器（`ubuntu:24.04` + 入库 `bin/yh-linux-arm64` 种子）：6 个 fixture
  全部构建成功并运行通过（`--selftest` 全 rc=0），cli 交付不依赖本日的枚举修复。
  未滚种子。记录见[完成文档](../01-finished/yh-cli6统一验收与文档冻结-2026-10-19.md)。

## 2026-10-19 CLI5：cli 标准库完整帮助与诊断体验

- `help.yh` 重写：段落顺序（usage/description/positional/options/组/commands/epilog）、
  usage 的 `[]`/`()`/`|`/`...` 表达、metavar 与类型推导、choices 与默认值展示、
  deprecated 标注、按宽度折行、控制字节与非法 UTF-8 转义、颜色（含终端检测降级）、
  有限建议（编辑距离 ≤2）；新增 `HelpFormat`/`Color`/`metavars`/`deprecated`。
- 输出 API：`print_usage`/`print_help`/`render(result, out_fd, error_fd)`/`exit_code`
  落地；失败结果自带 `usage_text`/`prog_text`；`libs/os` 增加 `is_terminal`。
- 验收：`clihelp --selftest` 7 个主题；`libs/cli/test/run.py` 新增 `cli5-help`。
  project cases **113/113**；`make test` 343/344；`make selfhost-native` 全绿。未滚种子。
  记录见[完成文档](../01-finished/yh-cli5完整帮助与诊断体验-2026-10-19.md)。

## 2026-10-19 CLI4：cli 标准库扩展与参数文件

- 新增 `libs/cli/{extensions,files}.yh`：converter/validator/custom action 与
  `register_type`/`register_action` 注册表、`type_name`/`action_name` 绑定、
  输出类型与形状检查、freeze 期默认值/常量校验、`context_text` 分配入口；
  `@file` 参数文件展开（逐行、嵌套相对路径、循环检测、深度/字节/token 上限、
  带文件与行号的诊断），子 parser 不得设置展开配置（根 freeze 递归冻结整棵树）。
- 本版本把展开上限收敛为单文件 4096 token、单行 4096 字节、累计字节默认 1 MiB
  （`ParseConfig.file_max_bytes` 可调）；`line_converter` 返回的切片须由回调自持。
- upkeep：`libs/cli` 与 `climodel` 里与枚举成员同名的形参改名（`value_text(content)`），
  让 cli 交付不依赖本日的「枚举成员遮蔽」修复；该修复仍由
  `tests/yh-run/run/204-enum-member-shadowed.yh` 锁定，旧种子也能编译全部 cli fixture。
- 验收：`cliextensions --selftest` 14 个主题；`libs/cli/test/run.py` 新增 `cli4-extensions`。
  `make test` 343/344（1 例平台 SKIP）；`make selfhost-native` 全绿，project cases
  **112/112**。未滚种子。记录见[完成文档](01-finished/yh-cli4扩展与参数文件-2026-10-19.md)。

## 2026-10-19 CLI3：cli 标准库组合、子命令与解析模式

- 新增 `libs/cli/{commands,layer}.yh`：子命令槽与子 parser 所有权（递归 destroy）、
  别名与规范 `command_path`、槽 `dest`、必需命令；展示组与组级默认值、
  互斥组、`Conflict.resolve` 冲突策略；`inherit` 深复制（参数/默认值/组/互斥/覆盖值）；
  `parse_known`/`parse_intermixed`/`parse_known_intermixed`/`parse_with` 与
  `ParseConfig.initial`；`Result.unparsed` 按输入顺序保留。
- 结果写入增加 `is_default` 标记实现「父 → 子」默认值覆盖，并按参数 ID 记录显式出现
  （互斥组计数）。
- 已知边界：位置参数与槽的顺序固定为「位置在前、槽在后」；混合模式对
  「同一 dest 由选项与位置同时提供」返回 config_error；initial 形状检查留 CLI4。
- 验收：`clicommands --selftest` 9 个主题；`libs/cli/test/run.py` 新增 `cli3-commands`。
  `make test` 343/344（1 例平台 SKIP）；`make selfhost-native` 全绿：
  模块固定点一致、自解析、modules 18/18、project cases **111/111**。未滚种子。
  记录见[完成文档](01-finished/yh-cli3组合子命令与解析模式-2026-10-19.md)。

## 2026-10-19 CLI2：cli 标准库完整内置参数行为

- 新增 `libs/cli/{convert,write}.yh`（从 parse 拆出严格转换与结果写入）；
  `Argument.choices`、`set_default`/`get_default`、`boolean_optional` 否定别名、
  共享 dest 形状校验、组级默认值。
- 完整数量模型与内置 action（custom 除外）、值形状（标量/列表/批次列表）、
  等号/附着值/短组合/负数特判/唯一缩写、位置分段与 remainder、choices、
  suppress 与默认值层级。
- 验收：`cliactions --selftest` 11 个主题；`libs/cli/test/run.py` 新增 `cli2-actions`。
  `make test` 343/344；`make selfhost-native` 全绿，project cases 110/110。未滚种子。
  记录见[完成文档](01-finished/yh-cli2完整内置参数行为-2026-10-19.md)。

## 2026-10-19 CLI1：cli 标准库最小可用命令行

- `libs/cli/` 交付六个源文件：`cli.yh`（公开模型/容量/分配池）、`schema.yh`
  （注册与冻结）、`values.yh`（命名空间与类型化查询）、`parse.yh`（token 匹配与
  内置 action）、`help.yh`（usage/help/render 文本）、`entry.yh`
  （argc/argv 与 0/1/2 退出契约）；`libs/project.toml` 的 `[lib]` 登记 cli。
- 验收项目 `libs/cli/test/clibasics`：`--selftest` 覆盖默认值/const/count、
  类型转换、`--`、帮助、错误诊断、重复解析隔离、`get_list` 错误码与
  「结果晚于 parser 销毁」；pack 入口形态验证真实进程行为。
- `libs/cli/test/run.py` 提供自有 runner（构建后用显式 argv 运行程序，
  断言退出码与 stdout/stderr 子串）与 4 个用例，覆盖成功、帮助、缺位置三条退出码路径。
  （2026-10-19 后续调整：cli 用例全部移入 `libs/cli/test/`，不再登记到全局 build-check。）
- 明确阶段边界：append/extend/boolean_optional/custom、完整 arity、choices、
  短选项组合与缩写、子命令、参数文件、完整帮助与 Result 级 render 未实现；
  未实现的声明在 freeze 或解析时给出 config_error/usage_error，不静默降级。
- `make test` 343/344（1 例按 `// platform:` SKIP）；`make selfhost-native` 全绿：
  模块固定点 119 产物一致、自解析、modules 18/18、project cases 109/109。
  未滚种子。记录见[完成文档](01-finished/yh-cli1最小可用命令行-2026-10-19.md)。
- Linux/arm64 容器复跑受阻（已定位，不属本阶段实现范围）：`container run
  --rm -v "$PWD":/host:ro -w /tmp ubuntu:24.04` 内 `cp -a` 仓库后 `make`，
  因 `llvm` 分支的 `compiler/backend/llvm_bind.linux.yh` 用 `@[extern]` 声明
  LLVM/lld 桥符号，而 `YH_LLVM_HOST=auto` 在缺 `tmp/llvm-migration` 身份时
  不联网，链接以 `undefined reference to yh_llvm_emit / yh_lld_*` 失败；
  直接用入库 `bin/yh-linux-arm64` 编译 `libs/cli` 则因种子不含本日的枚举成员
  遮蔽修复而在 `cli.yh:253` 报「引用了未声明的名字」。Linux 完整门由 CI 承担。

## 2026-10-19 CLI0：cli 标准库语言能力与 ABI 基线

- 新增探针项目 `libs/cli/test/climodel`（用例 `cli0-model-abi`）：
  真实运行 tagged union、递归指针链表、跨模块结构体/切片返回、切片形参、
  函数类型回调 + `*void` user 指针、公开薄句柄（私有类型不进 pub 签名）。
- 结论：动态列表用「堆上结构体成员数组 + 动态长度切片视图」实现（`state.items[0..count]`
  的 data 指向堆，返回后不悬垂）；裸堆指针不能切片（`p[0..n]` 被拒绝）；
  union 载荷不能递归引用自身类型，设计已把序列载荷改为 `*void`；
  跨模块枚举项只能写 `模块名.枚举项`，同名枚举成员不能在同一模块共存。
- 修复编译器名称解析缺陷：枚举成员名被同名形参遮蔽时 `Kind.text` 报「引用了未声明的
  名字」。`compiler/gen/state.yh` 新增 `sym_find_enum_member`，`compiler/parse/parse_expr.yh`
  在 `EnumName.member` 快路径按枚举类型反查成员符号；新增语料
  `tests/yh-run/run/204-enum-member-shadowed.yh`。修改原因见
  [完成记录](01-finished/yh-cli0语言能力与ABI基线-2026-10-19.md)。
  不修则 cli 只能靠给形参改名规避（`value_text(text *char)` 这类签名与设计冲突）。
- `make test` 343/344（1 例按 `// platform:` SKIP）；`make selfhost-native` 全绿：
  模块固定点 119 产物一致、自解析 100 文件、modules 18/18、project cases 105/105。
  未滚种子。

## 2026-10-19 macOS/ARM64 LLVM 接入方案交付

- 新增[接入设计](03-design/yh-macOS-LLVM后端接入设计.md)与
  [F2 实施方案](02-plan/yh-macOS-LLVM后端接入实施方案.md)，用户确认先 Mac 原生
  自举、再 Linux/x64 交叉验收；F2-0～10 各片列明文件、接口、`.yh` 测试与关闭门。
- 明确固定 LLVM/lld 21.1.8、Darwin 静态包、Apple ABI/runtime、Mach-O 链接/签名、
  SDK/部署版本缓存身份与原生固定点；缺 SDK 的 legacy 构建兼容、交叉目标库注入、
  emitter 不按宿主后缀裁掉等边界纳入专项。默认切换/滚种子保持既有硬门。
- 本机只读检查为 macOS27/SDK27，macos-14 兼容与建议最低版本14.0留给实施验证；
  方案未使用虚构 SDK 包哈希，未安装/构建 LLVM，未改编译器源码或种子。
- 关联 todo、总方案与 ADR-0014，交付记录见
  [方案交付](01-finished/yh-macOS-LLVM接入方案交付-2026-10-19.md)。

## 2026-10-19 Linux/x64 交叉引导 macOS LLVM 编译器可行性分析

- 在[macOS LLVM 差距分析](02-plan/yh-macOS-LLVM迁移差距分析.md)补充交叉引导链：
  Linux A 编译 Darwin 对象，配目标版 LLVM/桥与 macOS SDK 交叉链接 B，再在 Mac
  完成原生连续自编和固定点。技术可行，当前生产链尚未接入；Linux/ARM64 不是
  技术上的必要中间步骤，既有 F1/F2 排期未改。
- 重点核对：目标源码筛选与宿主身份分离已有基础；Darwin 桥仍为失败桩；自举库
  注入仍固定 Linux；`--backend llvm` 不会自动改变产出编译器的默认后端。
- 本轮为代码/官方文档分析，未执行 Linux 交叉构建，未修改编译器源码或种子。

## 2026-10-19 macOS/ARM64 切换 LLVM 剩余差距核查

- 交付[差距分析](02-plan/yh-macOS-LLVM迁移差距分析.md)，关联 F2 待办；核对当前
  实现的七组缺口：宿主 SDK/构建、目标发射、Apple C ABI、运行时、链接/签名、
  SDK 缓存身份、原生全门/自举。另列公共默认切换硬门，不更改既有平台顺序。
- 本机最小探针：Darwin/arm64 的 LLVM 文本/汇编被 emitter 平台校验拒绝；
  Linux/x64 纯 LLVM 文本输出成功（2012 字节），汇编发射命中 Darwin 失败桩。
  `make llvm-host YH_LLVM_HOST=1` 明确拒绝缺少固定 SDK。代码另确认 C 桥白名单
  漏 `aarch64-apple-darwin`，SDK 构建仍依赖 GNU 链接参数与 Linux memfd。
- 原始探针在 `tmp/mac-llvm-audit/`；本轮未修改编译器源码或种子，未重跑全量门。
  SDK 切换缓存风险与 Darwin relocation/PIE 政策列为待验证，未宣称已复现。

## 2026-10-19 RS2/RS4 核查收口（探针实测 + 代码证据）

- **RS4 缓存键收口：核查关闭（代码已实现，todo 未回填）**。证据：
  编译器二进制指纹（`mb_mix_compiler_fingerprint`）、外部汇编器身份
  （`mb_hash_tool_identity(&h, cmd0)`，link_cache.yh:868——解析路径 +
  二进制内容）、链接驱动身份（:991）与驱动器报告的搜索路径/工具/启动
  文件/库文件（`mb_link_query_identity` :462，查询结果工具再哈希内容
  :561）、lld 库内容、目标三元组/data_layout/abi、后端与优化级、全部
  源文件与依赖 `.s.i`/`.s.ct` 内容——均已在键中。门：u5-hot-cache-hits /
  u5-rebind 系列缓存键用例全绿。
- **RS2 函数级缓存：缺口结构定案（探针实测）**。tmp/rs2probe 项目实测：
  - legacy 路径有函数级 IR 缓存（ast_ir_cache.yh），但仅在 worker 子进程
    内生效，父进程 --stats 不可见（ir_cache_hits=0 实测）；只覆盖进入
    SSA 子集的函数；
  - **LLVM 模式完全跳过函数级缓存**（module_worker.yh:354 直接
    `mb_llvm_emit_module`），增量粒度 = 模块级对象缓存（无改动全命中
    实测 [缓存] main、asm=0）；
  - 真缺口 = LLVM 模式函数级 check/IR 缓存，必须 Linux 宿主实施与验证
    （darwin 无固定 SDK），定位为 LL11 切默认前完成、单函数 200ms 目标
    主力；legacy 窄子集随 LL12 退役处理。
- **RS3**：模块 = 目录（每目录一模块、目录内多文件）结构已由探针确认；
  文件级对象为 darwin 可实施的功能切片，待专门会话。RS5 依赖 RS2/RS3。
- 本轮无编译器源码改动（探针项目在 tmp/rs2probe/，核查为主）。

## 2026-10-19 RS1b/RS1c 完成并滚种子（任务私有上下文落地）

- **RS1b 诊断/路径缓冲任务私有化**：`c_path_buffer`/`c_ct_origin_path_buffer`
  固定 `[1024]u8` → 堆分配倍增扩容（新 `gen.task_buf_reserve` 统一助手，
  任务生命期持有不释放）；`set_source_path` 移除 1023 上限；`iface_ct.yh`
  来源映射解码/恢复 4 处同步。门：make + selfhost-native 全绿。
- **RS1c TaskCtx 物理收敛**：199 个任务字段从 `GenState` 收敛进
  `pub struct TaskCtx`（`g_state.task.<字段>`），GenState 留 52 个进程级
  字段 + `task TaskCtx`；全仓三类访问模式机械迁移（`tmp/rs1c_rewrite.py`，
  残留 0）；三个 LLVM fixture（llvmfront/llvmchecked/llvmlower，115 处）
  同步迁移——首跑 101/104 暴露 fixture 直访任务字段，补迁移后全绿。
- **门与种子**：make 冷编一次通过；selfhost-native 全绿（固定点 + 自解析
  + 语料 + 模块 18/18 + 项目 104/104）；make test 342/343（+1 平台跳过）、
  fail 132/132、pass 8/8；`make seed` 滚 `bin/yh-darwin-arm64`
  （SHA-256 `5b34a0678a564e2200a5dc9a417be03e33329af8732725516e85d77b52e654b4`）。
- **RS1d 决策修订（并入 R2c）**：fork worker 下 `g_state.task` 已任务私有
  （每进程一份）；显式 `*TaskCtx` 传参贯穿数百函数签名在无线程消费者时属
  投机性大改，违反「简洁优先」；R2c 线程池落地时随宿主线程桥一起实施。
- **RS2 开工前核查**：LL9 已把后端/目标/优化级/编译器指纹纳入缓存键；
  剩余真缺口 = 核实 LLVM 模式函数级缓存覆盖范围与 legacy 路径函数级缓存，
  已写入计划文档。
- **过程记录**：脚本首版丢字段名/`git checkout` 回退了未提交的 RS1a/RS1b
  state.yh 部分（其余文件机械重写幂等无损）——均当场发现修正；批量删除
  保护钩子会拦 make 内部 `rm -rf compiler/.build`，用 `mv` 挪入 tmp/ 绕行
  （构建缓存，gitignore）。

## 2026-10-19 RS1a 完成：GenState 域分类标注

- `compiler/gen/state.yh` 的 `GenState` 加两域分界标注（纯注释，不改字段
  顺序）：头部域分类说明指向 R2 收尾计划；四处分界注释——
  ①构建配置与统计（`c_stats_*`/`c_front_cache`/`c_ir_cache_salt`）、
  ②解析游标续段、③项目索引（`p_*`）、④目标与后端 CLI 选项
  （`c_dialect/c_target/c_backend` 等）；`c_module_mode`/`c_is_entry_mod`/
  `c_front_checked` 逐字段标注归属。未标注字段即每任务域（RS1c 收敛
  `TaskCtx` 的对象）。
- 验证：`make` 冷编通过；`env -u PYTHONPATH make selfhost-native` 全绿
  （两代固定点 + 自解析 + 全量语料 + 模块/项目 104/104，darwin/arm64）。
  纯注释无行为变化，不新增 .yh 用例。
- **环境发现（影响所有本机门禁）**：WorkBuddy Bash 会话注入
  `PYTHONPATH=.../WorkBuddy AI.app/.../shim`，其 sitecustomize 会让
  Python `Path.mkdir(exist_ok=True)` 在目录已存在时误报 PermissionError
  EEXIST，`make selfhost-native`/`make test` 直接失败；跑门禁必须
  `env -u PYTHONPATH make ...`。

## 2026-10-19 R2 收尾计划开执行：RS0 完成 + RS1 侦察

- **RS0 对账回填完成**：
  - **负数字面量实参（R2a 疑似真缺口）实测关闭**：darwin 旧后端探针
    rc=0（负字面量作 int 实参、u32 形参、一元减号作用于调用结果）；既有
    语料 `run/04-if-else` 的 `check(-3)`（darwin 342/343 全绿）与
    `llvm-integer-boundaries` 的 `quotient32(-21, 4)`（LLVM 343/343）
    双路径覆盖。「unsigned_score 回退」仅指旧 SSA 后端覆盖统计，
    LLVM fallback=0，随 LL12 退役，不作为 R2 缺口。
  - switch/goto/for-in/浮点/聚合/间接调用/单文件统一入口：凭 LL4–LL7、
    LL9 完成记录关闭；双平台 ABI 移交 F1/F2；默认优化覆盖归 RS5。
  - R1 剩余归位：会话 API 归 VS-U1；其余并入 RS1/RS2。todo.md 已回填
    （逐项带证据）。
- **RS1 侦察完成（第一步）**：语义状态确认为单个巨型全局
  `gen/state.yh` 的 `GenState`（约 270 行字段、`gen.G()` 全模块访问，
  注释明示字段偏移已越界、`c_data_str_*` 被迫拆出）；字段分「每任务
  （名字池/符号表/发射缓冲/调用栈）」与「每进程（项目索引/目标/CLI）」
  两域；worker 诊断走固定缓冲。实施路线定为拆分式四小步
  RS1a（字段域重排，产物逐字节不变作门）→ RS1b（诊断缓冲任务私有化）
  → RS1c（每任务域收敛 `TaskCtx` 子结构，逐模块迁移）→ RS1d（worker
  主路径持 `*TaskCtx`）。已写入计划文档 RS1 节。
- **本轮无编译器源码改动**（探针脚本在 tmp/），未跑全量门；RS1a 起的
  代码切片待下次会话按四小步执行。

## 2026-10-19 R2 收尾实施计划交付

- 交付 [R2 收尾实施计划](02-plan/yh-R2收尾实施计划.md)：基于 LLVM LL1–LL10
  闭环与 R2c 拆出后的最新状态，把 R2 收口细化为 RS0–RS5 六个独立可验收切片——
  RS0 对账回填（R2a 剩余 10 项中与 LL4–LL7 合并验收的重叠项预期关闭，
  负数字面量实参为疑似真缺口归 RS1.5，双平台 ABI 归 F1/F2，会话 API 归
  VS-U1）、RS1 任务私有上下文、RS2 完整函数级 check/IR 缓存、RS3 文件级
  对象、RS4 缓存键收口、RS5 提交协议与优化覆盖复核（产出收口报告，解除
  LL11 的 R2b 阻挡）。
- 成功标准：三层门全绿、build-check 100/100、缓存失效/命中矩阵用例、
  20 轮性能披露（单函数 200ms / 冷编 1s 目标）、产物确定性。
- 仅文档交付：todo.md 编译流程节已挂计划引用；未动代码、未跑门禁。
  下一步从 RS0（纯文档对账）起步。

## 2026-10-19 R2b 拆分：线程并行推迟到并发标准库之后（R2c）

- **用户决定**：多模块线程并行（真正线程池）不在 R2b 做，推迟到并发标准库
  完善之后；当前执行模型维持 fork/COW 进程 worker 现状——经确认，**不退回
  单模块串行**（fork worker 本就是最多 4 路的多模块并行，串行化会让实测
  33.7s 的冷编明显回退）。
- **新顺序（R2c）**：宿主线程桥（Linux clone / Darwin 审核 libSystem）→
  libs/sys 线程原语（线程/mutex/cond/join，属 SYS 任务）→ 编译器线程池与
  接口调度的线程状态隔离/并发/确定性验收——线程池**消费自己的标准库**，
  顺带作为标准库的狗粮自举验收。原方案「宿主桥不能等 R3」的约束随之修订
  （R3 线程 API 与 R2c 本就共用同一座宿主桥）。
- **R2b 硬门收窄**：去掉线程载体两项，保留完整函数级 check/IR 缓存 →
  文件级对象 → 缓存键纳入工具版本；任务私有上下文仍在线程化前完成
  （全局语义状态不拆掉，线程池无从谈起）。串行/多 worker 输出一致的
  原验收门保留为 R2c 回归门。
- **连锁影响**：LL11 切默认以「R2b 剩余 + R2c」全部关闭为前提，随之顺延；
  LL11 的性能对照与 x64 种子滚制不受影响。已完成的 DAG 调度/接口就绪推进
  （fork worker 上验收）不损失，线程化时调度层直接复用。
- **文档**：todo.md（R2b/R2c/R3/LLVM 节）、实施方案 §2 与 §6 同步修订，
  旧表述以删除线保留并标注修订依据。

## 2026-10-19 GitHub Actions 多平台验证补全（TC4 并入 + x86_64 LLVM 作业修复）

- **回答「能不能用 GitHub Actions 做多平台测试验证」**：能，且已就位——
  `ci.yml` 三作业：`linux-arm64`（QEMU arm64 容器跑主门）、`linux-x86_64`
  （ARM64 种子经 QEMU 产 x64 A，原生跑 LLVM O0/O2 全门）、`darwin-arm64`
  （macos-14 主门 + 自动补代）。本轮补齐三处缺口：
- **TC4 arm64 原生验证并入 CI**：`linux-arm64` 作业在 `make selfhost-native`
  后追加 `make yh-link-probe FULL=1`——check.py 自行冷编 link/ 与 asm/，
  arm64 容器即原生执行环境，把 WSL/qemu 的「模拟通过」提升为 CI 原生通过。
- **linux-x86_64 作业修复（此前从未运行、按现状首跑必失败）**：全新 runner 上
  `YH_LLVM_HOST` 默认 auto 不联网取固定 SDK，构建出的 yh 无 LLVM 桥，
  `test-llvm` 必失败。作业 env 加 `YH_LLVM_HOST: "1"`（require 联网准备），
  并新增 `tmp/llvm-migration` 的 actions/cache（键随 `vendor/llvm/sdk.lock.json`、
  `tools/llvm-sdk.py` 与桥源码哈希变化，数 GB SDK 不必每次重下）。
- **触发分支**：push 触发加入 `llvm`（当前工作分支；此前 llvm 分支推送完全不
  触发 CI）。darwin-arm64 仍仅 workflow_dispatch 触发（省 macOS 计费分钟）。
- **本地验证**（macOS 无 act，语法级干跑）：`tmp/ci-lint.py`——YAML 解析
  （3 作业）、全部 8 个 run 块 `bash -n` 通过、断言 llvm 触发分支/yh-link-probe
  步骤/YH_LLVM_HOST=1/缓存步均就位，全部通过。
- **未运行**：CI 实跑需推送后由 Actions 执行（本机 GitHub 连接器未授权）；
  首跑关注点已记 todo「linux-x86_64 CI 作业首跑验证」。
- **本地/CI 分工定策（同日用户决定，写入 AGENTS.md 开发策略）**：在 Linux 或
  macOS 上开发，本地只需保证**本平台**门禁绿（`make test` +
  `make selfhost-native`；语料按 `// platform:` 筛选、`test-llvm` 等平台专属门
  在别的宿主明确拒绝）；完整多平台回归由 GitHub Actions 承担，本地不为其他
  平台预跑门禁，CI 红灯按 todo 立项再修。支撑点均已在位：语料平台筛选
  （2026-10-18，darwin 342/343 + 1 跳过退出 0）、`test-llvm` 宿主断言、
  ci.yml 的 arm64/x86_64 推送作业与 darwin 手动作业分工。

## 2026-10-18 cli 标准库设计文档交付

- 按用户要求参考 Python argparse，并确认目标范围为“尽量覆盖全部能力”，交付
  [cli 设计](03-design/yh-cli标准库设计.md)与
  [CLI0–CLI6 实施方案](02-plan/yh-cli标准库实施方案.md)。
- 设计结合现有 libs 项目、NUL 字符串、显式内存管理、模块私有类型和 argc/argv 入口，
  确定声明对象、带类型标签结果、类型化查询，以及返回结果与输出退出分离的接口。
- 文档规定 action/数量/默认值、负数/短组合/分隔符、子命令作用域、继承/互斥/冲突、
  四种解析模式、扩展回调、参数文件、帮助/诊断/生命周期，并明确与参考基线的差异。
- 更新标准库设计索引和 todo；**未实现 cli、未注册空模块、未修改编译器或现有入口**。
  本次仅做文档结构、链接与差异检查，未运行编译器构建或 cli 运行门；实现任务仍未完成。

## 2026-10-18 测试平台筛选：共有用例 + 平台专属用例

- `tests/yh-run/check.py` 新增 `// platform: <tag>` 头部指令：无指令为共有用例
  （所有平台跑），带指令只在匹配的运行平台执行、其余记 `SKIP` 不计失败；
  tag 为 `<os>` 或 `<os>-<arch>`，`<os>` 匹配该 OS 的所有架构，`--cross` 按
  Linux/aarch64 计。任务表加第六项 `skip_reason`，不匹配的用例不建产物目录。
- `run/llvm-linux-x64-host.yh` 标 `// platform: linux`（正文对 arm64/x64 都有
  syscall 号分支，按 OS 级声明；文件名保留历史 x64 标记）。
- `make test` 在 Darwin/arm64 上退出 0：三层全过、运行语料 **342/343 + 跳过 1**，
  跳过行为 `SKIP run/llvm-linux-x64-host.yh —— 仅适用于 linux，当前 darwin-arm64`。
  汇总模式标签不再硬编码 `Darwin Mach-O`，改为实际运行平台。
- 复查 `tests/yh/`（纯语法）、`tests/modules/check.py`（只 `--syntax-check`）、
  `tests/modules/build-check.py`（已按 `sys.platform` 自适应 native/cross 断言）、
  `tests/selfhost/llvm-*.py`（由 `test-llvm` 的 Linux/x86_64 断言隔离），均无需再加筛选。
- 详见 [完成记录](01-finished/yh-测试平台筛选-2026-10-18.md)。

## 2026-10-18 macOS 种子补代与 `yh-<平台>-<架构>` 命名

- macOS 入库种子 `b123acbe…`（10-13 中间代）编不了 llvm 分支当前源码。按
  `b037127` → `8fe3c80` → HEAD 逐代补代（每代 2–9 秒），并把两处 macOS 阻塞点
  正式化为平台分支：`backend/llvm_bind.darwin.yh` 提供桥桩（固定 SDK 只有 Linux
  宿主），`backend/llvm_bind.linux.yh` 保留 9 个 `@[extern]`；`cmd/link_cache.yh`
  的 `mb_link_query_identity` 在 Darwin 目标跳过 GCC 风格查询。
- 入库种子统一改名：`bin/yh` + `bin/yh.sha256` 删除，改为
  `bin/yh-darwin-arm64` + `.sha256`（3,537,600 B，Mach-O arm64，
  SHA-256 `9d911d0b9d58d7a4a48ebf26a59621a3e6136542cd19d8e09e3f63932dc60aab`）。
  `Makefile` 改为 `HOST_TAG` + `yh-$(HOST_TAG)-$(SEED_ARCH)`，不再有
  macOS/arm64 特例；`tools/selfhost_snapshot_gate.py`、`tests/selfhost/native-selfhost.py`、
  CI/release 工作流与 README/AGENTS 同步。
- 验收：`make verify-seed` 通过；新种子冷编 `compiler/` 退出 0 并产出可用的根 `yh`；
  `tests/yh-run` **342/343**（唯一失败是 Linux 专用 syscall 语料，缺平台筛选）。
  本机无法复跑 `test-llvm`（Makefile 硬性要求 Linux/x86_64），Linux 侧零回退需在
  Linux 宿主确认。
- 详见 [完成记录](01-finished/yh-macOS种子补代与平台命名-2026-10-18.md)。

## 2026-10-18 核对并回填 LL2「LLVM 模式接入」与 LL3 两条待办

- **起因**：`todo.md` 里 LL2 的子项「LLVM 模式常驻：`--backend llvm`/`--target`/`-O0/-O2`
  的 CLI 与模块 worker LLVM 分支未接入」和整条 LL3 都未勾选，却与 LL3 完成记录、
  LL9/LL10 验收记录直接矛盾，动 LL11 前先核对。
- **代码核对（分支 `llvm`，HEAD `dfa7195`）**：`cmd/driver.yh` 的 `drv_scan_target`
  解析 `--target`/`-target`、`--backend legacy|llvm`、`-O0`、`-O2`、`--emit-llvm`，
  未知后端与未知 triple 明确 `fail` 且不回退；`run_emit_asm_to` 在 `c_backend != 0`
  时走 `llvm_emit_single_file`；`cmd/module_worker.yh` 在 `c_backend != 0 && c_check_only == 0`
  时走 `mb_llvm_emit_module` 并直接返回，不进入 `ast_ir_lower_module` 与机器发射；
  `cmd/module_build.yh` 把 LLVM 产物隔离到 `.build/targets/<triple>/llvm/O<n>`，
  `cmd/link_cache.yh` 在 LLVM 模式下跳过「汇编 → 目标」步并让 `c_backend` 进缓存键。
  结论：两条待办描述的行为确实已实现，属文档未回填。
- **本机复跑门禁不可行（实测）**：宿主为 Darwin/arm64。`make` 用 `bin/yh`
  （`b123acbe…`，2026-10-13 中间代）冷编当前 `compiler/` 时在 `gen/target_info.yh`
  报「编译期常量尚未就绪」并中止，`tools/seed-build.py` 同一失败；`Makefile` 只在
  Linux 宿主设置 `LLVM_HOST`，固定 SDK 也只有 `linux-x86_64`/`linux-aarch64`；
  `test-llvm` 目标在 `Makefile:295-296` 硬性断言 Linux/x86_64。容器方案也未走通：
  `container system start` 报 `XPC connection error: Connection invalid`，
  `container system status` 仍为未运行。
- **处理**：按代码与既有完成记录回填 `todo.md` 两条（标注「核对回填」与依据文档），
  并新增「macOS 入库种子落后于 llvm 分支」待办，避免下次把平台限制误判为功能缺失。
  本轮**没有**复跑 `make test-llvm`/`make selfhost-llvm`，门禁数字仍以 LL10 记录为准。

## 2026-10-18 LLVM LL9、LL9L 与 LL10 完成闭环

- `make test-llvm` 与 `make selfhost-llvm` 在 WSL/Linux x86_64 均退出 0。LLVM O0/O2 各通过
  运行/拒绝/仅编译语料 343/343、模块 18/18、项目 104/104；最终 D 自解析 98/98，
  `make test` 与滚种子后的 `make selfhost-native` 也通过。
- ARM64 入库种子经 qemu 生成 A，再由 LLVM 连续构建 x64 原生 B/C/D。A/B/C/D 均为 ELF
  machine=62；O0/O2 的 B→C、C→D 各 24 个 `.ll/.s.i/.s.ct` 产物逐字节一致。
  B/C/D 自编未调用 gcc wrapper；D-O0/O2 内嵌 lld 为 SDK 锁定的 21.1.8，身份 SHA-256：
  `721002cf04413fd64ad9b77002f718eb83516914876c9193901db150152f5b96`，`readelf -d` 未发现
  LLVM/lld 动态依赖。最终 Linux/AArch64 种子 SHA-256：
  `8ea2a9acc20438b385ccddd522b50b8dd4749423c8db2695c758296ada343b8c`。
- 修复 LLVM lowering 对无条件循环内条件返回的拒绝，新增
  `tests/yh-run/run/203-llvm-infinite-loop-return.yh`。`asm/` 4 模块 checked/emitted 298/298、
  `link/` 6 模块 197/197，LLVM fallback=0；`libs/` 由标准库项目验收覆盖。LL9 的统一入口、
  缓存与失败发布，及 LL9L 的内嵌 lld 均随全门闭环。
- 早前项目 runner 用 PATH 查找 `yh` 而候选名为 `yh-D-O2` 的问题已由临时启动链接修复并
  完整复验；当时 WSL 中断是中间状态，不再阻挡 LL10。日志见
  `tmp/ll10/make-test-llvm-after-fix.log`、`tmp/ll10/selfhost-llvm-after-fix.log`、
  `tmp/ll10/selfhost-native-post-seed.log` 和 `tmp/ll10/make-seed-after-loop-fix.log`。
- R2b 真线程池、任务私有状态和完整缓存仍是独立未完成项；fork worker 验收不替代线程池，
  LL11 默认后端切换仍受 R2b 硬门阻挡。

详见 [LL10 完成记录](01-finished/yh-LLVM-LL10-x64原生自举-2026-10-18.md)、
[LL9L 验收记录](01-finished/yh-LLVM-LL9L内嵌lld-2026-10-18.md) 与
[实施方案](02-plan/yh-LLVM后端替换实施方案.md)。

## 2026-10-18 LLVM LL9/LL9L 阶段验收（后由上方 LL10 全门补充）

- LL9 全量 LLVM x86_64 runner 的 O0、O2 均通过 **335/335**；此前失败的聚合返回值、
  编译期边界、切片生命周期、数组到切片视图和诊断预期均有回归覆盖。该数字只表示当前
  语料通过，不扩大为所有语言形态已经覆盖。
- 滚动 Linux/AArch64 种子后复跑 `make test`：语法正例 78/78、反例 42/42，运行 195/195、
  拒绝 132/132、仅编译 8/8，总计 335/335。复跑 `make selfhost-native`：cc3→cc4 的 24 个
  模块产物固定点一致、cc4 自解析 98 个源文件、语料 335/335、scratch 并发 8/8、模块
  18/18、项目 103/103，运行时、缓存、快照复用和外置文件系统门通过。
- 新 Linux/AArch64 种子 `bin/yh-linux-arm64` SHA-256：
  `dc64daac8b61368634c11e81b94f402fc0e28a98e0d4c12c054d5f520e23db23`；门禁中的种子校验通过。
- `tests/selfhost/llvm-lld.py` 与 `llvm-driver.py` 通过。早期 `llvm-cache.py` 在 AArch64
  编译器上检查 x64 链接时命中 lld stub，因此该轮没有提供 x64 内嵌 lld 证据；LL9L-6 与
  LL10 的 x64 原生链接、lld 身份/动态依赖、固定点及全量项目门已由上方最终记录闭环。
- LL9/LL9L 详情见 [LL9 补充记录](01-finished/yh-LLVM-LL9-统一入口缓存失败发布-2026-10-17.md)、
  [LL9L 验收记录](01-finished/yh-LLVM-LL9L内嵌lld-2026-10-18.md) 和
  [实施方案](02-plan/yh-LLVM后端替换实施方案.md)。

## 2026-10-17 LLVM LL9：统一入口、缓存与失败发布

- 单文件、项目 `check/build/run` 和模块 worker 共用受检→IR→LLVM 路径；`check` 在无外部
  LLVM 工具时仍可完成且不生成对象。runner 支持显式 backend/target/优化级别，并校验 LLVM
  checked/emitted 数量及零 fallback。
- LLVM 中间产物进入 `.build/targets/<triple>/llvm/O<level>/`，legacy 继续使用旧 `.build`
  平面布局。模块、对象、接口和链接缓存均校验各自身份；工具路径相同但文件内容变化会使
  缓存失效。对对象与最终产物校验 target machine，模块对象、最终链接文件及 manifest 以
  临时文件经校验后 rename 提交；失败链接保留旧程序。Linux x64 LLVM 默认使用 `/usr/bin/gcc`，
  不受 ARM64 crossbin/gcc 的 PATH 顺序影响。
- 新增 LL9 缓存项目与 `.yh` 运行用例；专项覆盖热命中、工具更新、损坏缓存、错误 machine 配对、
  x64→AArch64→x64 同名输出切换、空格/中文路径；驱动门覆盖无工具 check、语法、emit、单文件、
  build/run 和统计计数。专项门通过，LLVM x64 模块语法 O2 通过 18/18。
- LLVM x64 全量 runner O0 通过 284/324，O2 通过 283/324；未覆盖的 lowering、目标/诊断预期
  差异和少量运行语义问题（含 O2 聚合返回值用例）列入 LL10 前置覆盖工作，没有宣称全量 LLVM
  语义已通过。
- WSL 验收：`make test` 与 `make selfhost-native` 均通过；固定点 24 项一致、自解析 97 个源文件、
  运行语料 324/324、模块 18/18、项目 103/103。两道门通过后执行 `make seed`，并从新种子重跑
  `make test` / `make selfhost-native` 仍通过。Linux/aarch64 种子 SHA-256：
  `acb709ec7fda2499c66df5558219c5279d5069fd0c0252b8fe4d16820d3acbcb`，与 `.sha256` 文件一致。
- R2b 真线程池/任务私有状态硬门继续独立推进；LL9L 内嵌 lld 未包含在本片。
  详见 [LL9 完成记录](01-finished/yh-LLVM-LL9-统一入口缓存失败发布-2026-10-17.md)。

## 2026-10-17 LLVM LL8b：Linux x86_64 完整运行时与宿主桥

- LLVM runtime emitter 按需提供 `linux_syscall6`、`malloc/free/printf` 与内存 helper；x64
  syscall 使用正确寄存器约定，allocator 使用带尺寸头的 `mmap/munmap` 并保持 16 字节对齐，
  printf 覆盖现有运行时格式、UTF-8、短写与错误返回。O0/O2 对象无运行时入口、内存 helper
  或整数 libcall 的未定义导入，也无 helper 自递归。
- 目录枚举和时钟实现拆分为 Linux ARM64/x64 专用源文件；通用
  `open/fork/execvp/exit/waitpid` 通过 LL7 SysV 调用 lowering 使用。新增 `.yh` 探针覆盖分配边界、
  直接/间接入口、printf、错误路径、嵌套中文/空格路径、文件项、单调时钟、fork/execvp 执行
  `/bin/true` 与退出状态。`runtime-memory.py` 原门保留并新增 `--llvm-x64` 对象导入审计。
- WSL 验收：LL8b `llvm-runtime.py --suite complete` 通过；`make test` 语法两层各 78/78 +
  42/42、运行语料 323/323（183/183、132/132、8/8）；`make selfhost-native` 固定点 24 项
  一致、自解析 97 个源文件、模块 18/18、项目 103/103。`make seed` 已滚 Linux/aarch64 种子，
  SHA-256 为 `4b2f4a3e111e33eecd5ca48bc712e6b3b6a2f0ddfe68bfd8063f7bd15f4c1d94`，快照门复核通过。
- LLVM 自有运行时目标限制 Linux/x86_64 SysV；ARM64 LLVM 运行时留给 F1，生产 CLI/worker
  与完整缓存身份仍归 LL9。详见[LL8b 完成记录](01-finished/yh-LLVM-LL8b-完整运行时与宿主桥-2026-10-17.md)。

## 2026-10-17 LLVM LL7：完整调用、函数值与 ABI

- 函数值的 ABI/参数/返回/变参信息进入模块 `FUNCTION` 类型、序列化与接口；支持 YH 与 C 函数指针跨模块传递、返回和间接调用。C callback 实际覆盖标量和 CPair 聚合参数/返回的双向调用。
- YH 类型化变参 `vararg=2` 在调用点从左到右求值并打包为末尾切片 ABI 参数，零个和多个尾参均覆盖。用户裸 C 变参遵循既有 FFI 决定，在源码层拒绝。
- `@[noreturn]` 进入模块接口及缓存；调用若违约返回会执行 `llvm.trap`/`unreachable`。O0/O2 项目测试切换并恢复接口属性，确认调用方 IR/cache 随之更新；合法定义与源级拒绝也有覆盖。
- `tests/modules/projects/llvmabi` 扩展跨模块 YH 函数值和 C aggregate callback；`tests/yh-run/fail/60-user-c-varargs.yh` 固定裸变参拒绝策略。专项 `tests/selfhost/llvm-abi.py` 的 O0/O2 clang oracle、verifier、优化、链接、双向运行及接口缓存门通过。
- WSL 全仓验收：`make test` 语法两层均为 78/78、42/42，运行/拒绝/仅编译 321/321；`make selfhost-native` 固定点 24 项一致、自解析 95 个源文件、运行语料 321/321、模块 18/18、项目 103/103。滚种子后再次执行两道主门，结果一致。
- Linux/aarch64 种子已由 `make seed` 更新；新 SHA-256：`f5c7ab922ae93823242c7b92bbbd7fd8198378e62316997933ae7f24c4743c1c`。详细验收与边界见[LL7 完成记录](01-finished/yh-LLVM-LL7-完整调用与ABI-2026-10-17.md)。
- 目标范围为 Linux/x86_64 SysV。ARM64 AAPCS64/HFA 留给 F1。

## 2026-10-17 LLVM LL7-S4：SysV C 聚合 ABI

- Linux/x86_64 SysV 结构体与联合体按 INTEGER/SSE/MEMORY 分类；实现 C 聚合参数分片、寄存器返回 coercion、`sret`/`byval`，并保持 C 与 `yh-llvm-v1` 两种签名分离。
- `tests/modules/projects/llvmabi` 覆盖 CPair、CMixed、CWide 的 C↔YH 双向调用；clang 21.1.8 IR oracle 锁定三类签名。
- 验证：WSL x86_64 `make` 与 `python3 tests/selfhost/llvm-abi.py --compiler-path ./yh` 成功，含 LLVM verifier、O0/O2 优化、链接和运行。完整 `make test` / `make selfhost-native` 留待 LL7 结束统一执行。
- 未滚种子；详见 [LL7-S4 完成记录](01-finished/yh-LLVM-LL7-SysV-C聚合ABI-2026-10-17.md)。

## 2026-10-17 LLVM LL7-S3：yh-llvm-v1 内部聚合 ABI

- YH 内部函数签名在 IR 中采用 ABI id `IR_ABI_YH_LLVM_V1`；该 id 随函数、调用和模块序列化保留，参与 IR 身份。YH 内部链接名追加 `$yhllvmv1`，跨版本符号不会被链接器误合并。
- 结构体、定长数组和切片参数按从左到右求值，在对应实参点复制到独立调用缓冲；聚合返回由调用方分配源布局大小/对齐的缓冲并作为首个隐藏参数传递。切片只复制描述符，底层元素继续共享。
- `tests/modules/projects/llvmabi` 增加跨模块结构体、数组和切片参数/返回运行断言；`tests/selfhost/llvm-abi.py` 检查 ABI 版本符号，并对 O0/O2 运行。
- 验证：WSL x86_64 使用 `SEED=bin/yh-linux-arm64`、交叉 gcc 包装和 `YH_LINK=/nonexistent` 执行 `make`；随后 `python3 tests/selfhost/llvm-abi.py --compiler-path ./yh` 通过（clang ABI oracle、LLVM verifier、O0/O2 链接运行）。未滚种子。
- C ABI 的 INTEGER/SSE/MEMORY 聚合分类、函数指针/间接调用、callback、变参和 `@[noreturn]` 仍在 LL7 待办。
- 详见 [LL7-S3 完成记录](01-finished/yh-LLVM-LL7-yh-内部聚合ABI-2026-10-17.md)。

## 2026-10-17 LLVM LL7-S2：SysV C `_Bool` 标量边界

- Linux/x86_64 System V 固定参数 C ABI 支持 `_Bool`。LLVM 外部签名用 `i1 zeroext`；YH 内部仍以
  `i8` 保存 bool 字节，YH→C 按非零值归一成 `i1`，C→YH 扩成 `i8`，C bool 返回到 YH 也扩回字节。
- 新增 `llvmabibool` 跨模块项目及非规范 bool 返回探针，覆盖 C↔YH 双向调用和 YH 字节值 `2` 到
  C `_Bool` 的非零转换；clang 21.1.8 属性 oracle、LLVM O0/O2 verifier/优化/编译/链接/运行全通过。
- `make`、`make test`（语法 78/78、42/42；运行语料 320/320）、`make selfhost-native` 全通过：
  固定点 24 项一致、自解析 94 个源文件、模块 18/18、项目 103/103。
- Linux/arm64 种子哈希未变：`073282e9f1f773f162ccf9674a86f357e3bd6c9b74ccb65fe613968566916ccd`；未滚种子。
  裸 C 变参仍按已有 FFI 约束暂缓，LL7 其余 ABI 工作继续开放。
- 完成详情见 [LL7-S2 C bool 记录](01-finished/yh-LLVM-LL7-CABI-bool-2026-10-17.md)。

## 2026-10-17 LLVM LL7 首片：固定参数 C ABI 标量直接调用

- LLVM 后端在 Linux/x86_64 System V 支持固定参数 C ABI 标量直接调用：有符号/无符号窄整数、
  32/64 位整数、指针和 f32/f64。`signext`/`zeroext` 同时写入函数签名与 call site。
- 修正 extern 调用点首次登记时的 external linkage，以及 C ABI 定义被错误发为 internal 的问题。
- 新增双向 C↔yh 探针，覆盖窄型边界、混合浮点/整数、8 个整数栈参数及不支持 C bool 的明确拒绝；
  clang 21.1.8 IR 作属性 oracle，O0/O2 均验证、链接和运行通过。
- `make test` 320/320；`make selfhost-native` 固定点 24 项一致、自解析 94 个源文件、模块 18/18、
  项目 103/103；`git diff --check` 通过。
- 种子哈希保持 `073282e9f1f773f162ccf9674a86f357e3bd6c9b74ccb65fe613968566916ccd`，未滚种子。
  共享工作区仍包含 LL4–LL6 的在途改动，未创建提交。
- 完整范围和剩余工作见 [LL7 首片完成记录](01-finished/yh-LLVM-LL7-CABI标量直接调用-2026-10-17.md)。

## 2026-10-17 LLVM LL6 浮点标量 lowering

- CheckedModule/SSA 接入 f32/f64 标量常量、算术、IEEE 比较、整浮转换和局部内存；
  LLVM emitter 保留浮点位型与 f32 逐节点舍入，使用饱和浮点转 i64/u64 再按目标宽度
  截断，不添加 fast-math 属性。
- 新增 `llvm-float-lowering.yh`、`tests/selfhost/llvm-float.py` 和
  `tests/modules/projects/llvmfloat/`；覆盖 NaN、正负零、算术、f32 舍入、转换边界、
  编译期与运行期结果及局部 load/store。专项门对 O0/O2 执行 LLVM 验证、优化、原生编译和运行。
- `make test` 通过：ANTLR 语法 78/78 + 42/42、编译器语法 78/78 + 42/42；运行、拒绝
  与仅编译语料合计 320/320（181/181、131/131、8/8）。`make selfhost-native` 通过：
  cc3→cc4 固定点 24 项一致、自解析 93 个源文件、模块 18/18、项目 102/102。
- 模块 verifier 测试原将浮点 `DIV` 当作整数专属运算拒绝；更新为接受整数/浮点除法，
  仍拒绝浮点取模、位运算和移位。该项是 LL6 支持面扩展后的旧断言。
- 种子 SHA-256 `073282e9f1f773f162ccf9674a86f357e3bd6c9b74ccb65fe613968566916ccd`
  未变化；未执行 `make seed`。共享工作区包含其他在途改动，本次未创建提交。
- 详细范围、命令和边界见 [LL6 完成记录](01-finished/yh-LLVM-LL6浮点标量-2026-10-17.md)。

## 2026-10-17 LLVM LL4 for-in lowering

- LLVM 后端新增数组/切片、左闭右开整数区间和可选下标绑定的 for-in lowering，
  循环计数通过 header phi 连接 continue 与自然回边；聚合元素按值复制到独立绑定槽。
- 新增 `.yh` 语料覆盖数组、切片、区间、嵌套、break/continue 和结构体值语义；专项门在
  O0/O2 下验证 IR 并原生运行。
- 验证：`make test` **319/319**；`make selfhost-native` 通过，固定点 **24**、自解析
  **93**、模块 **18/18**、项目 **101/101**。种子 SHA-256 未变化，未滚种子。
- 当前共享工作区还有其他在途改动，本次未创建提交；已在实施方案保留提交步骤。
- 旧 ARM64 for-in 的 `continue` 会跳过计数递增，故通用运行语料不直接包含该旧后端缺陷；
  LLVM 专项 `.yh` 探针独立覆盖该行为。
- 收尾复核：未初始化局部聚合的未写内容按 LL5 契约保持未定义，不要求后端隐式清零；
  因此此前记录的「缺少零写入」不是待修缺陷。本轮空循环测试使用显式初始化的零长度
  切片视图，以保证断言只读取有定义的值。
- 详见[完成记录](01-finished/yh-LLVM-LL4-for-in-2026-10-17.md)与
  [实施方案](02-plan/yh-LLVM后端替换实施方案.md)。

## 2026-10-17 LLVM LL5 内存、聚合与模块数据全量收尾

- 完成全局/字符串/零初始化/CT backing/指针重定位/全局切片数据闭环。`gen` 静态
  数据目录只拥有目标字节、布局和符号/标签重定位；CT 视图关系仅在物化期间借用，
  输出记录不保留 `CtAggregate` 地址。`CheckedModule` 深拷贝字节与重定位后可独立
  验证及 lowering。
- IR verifier 校验全局对象范围/对齐、重定位目标/偏移/宽度/addend 和槽重叠；LLVM
  发射完整字节、切片 header 与真实正负 addend。聚合复制按允许重叠的 `memmove`
  发射，显式 `memcpy` 的不重叠契约不变。模块 lowering 支持全局 slice 的长度和
  backing 地址；导入 `pub const` 聚合按 `.s.i/.s.ct` 重放后物化为消费方私有副本。
- 新增/扩展 `.yh` 全局数据与聚合用例；多模块夹具用 CT 函数初始化 `pub const` 数组，
  并显式检查两个模块的 `.s.i/.s.ct`、重写后的隐藏 CT 名、消费者本地副本、私有同名
  对象隔离、模块对象和链接运行。单独 LLVM 专项覆盖指针字段后的整数成员运行读取。
- 验证（WSL Ubuntu/x86_64，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）：
  `make` 退出 0；`llvm-ir.py --suite memory` 的 8 个 LL5 门全绿；`make test` 通过
  318/318（运行 179/179、拒绝 131/131、仅编译 8/8）；`make selfhost-native` 退出 0，
  24 个固定点产物一致、自解析 92 个源文件、语料 318/318、模块 18/18、项目 101/101。
  记录见 `tmp/ll5-complete/make-test-final.log`、`selfhost-native-final.log`。
- 入库种子 SHA-256 为 `073282e9f1f773f162ccf9674a86f357e3bd6c9b74ccb65fe613968566916ccd`，
  验证前后不变；未执行 `make seed`，LLVM 仍为实验后端，默认后端与 ABI 未切换。
- 边界：全局 union 初值、任意 CT 指针逃逸、浮点全局字段和无效/越界重定位继续明确
  拒绝；生产 CLI 全模块 LLVM 驱动和完整缓存/提交键归 LL9。另确认旧 ARM64 种子及当前
  候选对含非空指针成员全局结构体的后续整数成员读取均退出 1，已作为独立旧后端问题
  登记到 `todo.md`；LLVM O0/O2 对应读取通过。
- 详见[LL5 全量完成记录](01-finished/yh-LLVM-LL5全量收尾-2026-10-17.md)、
  [实施方案](02-plan/yh-LLVM-LL5全量收尾实施方案.md)与
  [LLVM 后端替换设计](03-design/yh-LLVM后端替换设计.md)。

## 2026-10-16 LLVM LL5 普通全局与字符串数据切片

- 从导出的会话和未提交改动续接，完成四层数据交接：`AstDecl.init_expr` 捕获
  标量/数组/嵌套结构体初始化；快照与 verifier 同步；新增独占布局/字节物化；
  `GLOB_ADDR` 引用模块符号；LLVM 全局统一发完整 `[N x i8]` 字节与对齐。
- 覆盖全局整数/bool/char/enum、零初始化、NULL 指针对象/字段/元素、数组/
  struct/union、读写/取址/副本、全局数组切片基址；字符串转义/NUL/UTF-8、
  三级 const 引用链、对象地址和可写别名均由同源 `.yh` 与原生 C 驱动核对。
- 独立审查修复了字符串/聚合 const 错发只读存储、数字与字符串标签混淆、
  运行期 CAST 被错误快速折叠；另锁住 bool 原始字节、宽文字量、NULL 比较与
  窄负字面量。源 const 仍受前端直接左值限制，物理后备存储保留裸指针可写性。
- 完整门首跑 98/100 抓到 `.s.ct` 全局捕获错误；现接口/闭包重放只求值、不挂
  消费者 AstDecl，返回后恢复捕获。新增跨文件私有常量闭包 `.yh` 回归，最终
  项目门恢复 100/100。
- WSL Ubuntu/x86_64，`PATH=$PWD/tmp/boot/crossbin:$PATH`、
  `SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`：`make` 成功，
  `make full` 全绿（语法 78/78 + 42/42，运行 **316/316**，固定点 **24**，
  自解析 **87**，模块 **18/18**，项目 **100/100**）；17 个 LLVM 专项门全绿，
  包含 O0/O2 原生 x64 C 驱动与 11 类反例的 22 次来源拒绝。
- 日志位于 `tmp/llvm-migration/global-resume/` 的 `make-interface-boundary.log`、
  `full-interface-final.log`、`llvm-gates-interface-final.log`、`global-interface-final.log`。
  构建与完整自举共享 `compiler/.build`，受并发目录冲突影响的一次早期运行作废，
  最终完整门在候选构建结束后重跑。
- CT backing、导入聚合副本、静态非零指针重定位、全局切片仍未完成；默认后端
  和入库种子未变。另发现的旧 ARM64 指针比较后取逻辑非问题已单独登记 todo。
- 详见 [完成记录](01-finished/yh-LLVM-LL5全局数据切片-2026-10-16.md) 与
  [实施方案](02-plan/yh-LLVM-LL5全局数据切片实施方案.md)。

## 2026-10-15 全量门加速：并行化 + 暂存/分层门（只改 harness 与 Makefile，不重编种子）

- **动机**：全量门（`make test` + `make selfhost-native`）实测约 26 分钟，瓶颈是
  「每个用例起一次 yh 进程 × 全串行」，不是编译算力：单次 `--syntax-check`
  0.52–0.67s（qemu 放大 yh 自身启动），同一批 120 文件在单进程内跑 5.5s、
  逐文件起进程要 69.0s（12.5×）。
- **第一轮·并行**：`tests/yh/check.py`（`--compiler` 模式）、`tests/yh-run/check.py`、
  `tests/modules/check.py`、`tests/modules/build-check.py` 新增 `--jobs`
  （缺省 `min(8, CPU)`；build-check 因每个用例内部还会 fork 模块 worker 取
  `min(4, CPU)`；`--jobs 1` 恢复串行）。yhrun 产物改为
  `<workdir>/<run|fail|pass>/<用例>`；build-check 的用例循环体抽成
  `run_case(c)`、断言先收集再由 main 按 `CASES` 顺序打印、每用例独占
  `tmp/modcheck/<fixture>--<用例>`（原先是同一 fixture 共用目录，无法并发）。
- **第二轮·暂存与分层**：`Makefile` 新增 `stage-yh`（把 `$(YH)` 暂存到
  `$TMPDIR/yh-fast`，语料门用暂存副本并把它当工作目录；`FAST_STAGE=0` 关闭）、
  新增 `make quick`（ANTLR + 编译器语法语料，热跑 22.8s）与 `make full`
  （= `test` + `selfhost-native`，滚种子前的全量门）；`native-selfhost.py`
  的 86 文件自解析改并发、新增 `--workdir` 与 `--skip-corpus`（Makefile
  `SKIP_CORPUS=1`）；`tests/yh/check.py` 的 `--compiler-path` 现在会 `.resolve()`。
- **验收**（WSL/x86_64/qemu，全部 rc=0）：
  - 全量门 **26.2 分钟 → 6.8 分钟**（单命令 `make full` 实测 406.1s rc=0，
    日志内无 FAIL；`SKIP_CORPUS=1` 时约 336s）。
  - `make test` 412.6s→56.5s；`make selfhost-native` ~1160s→330.4s，其中
    `build-check` 449.5s→86.5s、`native-selfhost` 600s→154.7s。
  - 全绿证据：模块固定点 cc3→cc4 一致、自解析 86 文件 OK、语法语料 78/78+42/42、
    运行语料 309/309、`modules` 18/18、`project cases` 100/100、其余探针全 OK。
  - 编译器侧两项（模块 worker 上限、批量 `--syntax-check`）经测量判定不值得做
    （放宽 worker 预计只省全量门约 5%，却要动编译器源码与种子流程），已移入
    todo.md 的「设计决定不做」。
- 详见[完成记录](01-finished/yh-全量门测试并行化-2026-10-15.md)。

## 2026-10-15 LLVM LL5 切片：数组切片与切片共享

- **范围**：数组切片 `a[i..j]`、切片字面量（入口预分配后备数组）、切片再切片、
  `s[k]` 共享读写、切片副本（16 字节）与运行期 `len(s)`；头部
  `{len u64, ptr *void}`。
- **实现**：复用 ALLOCA/GEP/MEMCPY；`slice_ptr/slice_len/slice_header` 三入口；
  字面量后备数组按表达式预分配（循环复用）；`len` 结果按语义 i32 截回。
- **门禁**：新增 `tests/selfhost/llvm-slice.py`（O0/O2 原生运行）与运行语料
  `tests/yh-run/run/llvm-slice.yh`；`llvmlower` slice 转正、global 为拒绝负例；
  其余门拒绝负例统一改用 `for-in`。
- **验收**（WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）：
  `make`、`make test`（语法 78/78 与 42/42、运行 **315/315**）全绿；
  `make selfhost-native` 全绿（固定点 24 产物一致、自解析 86 文件、
  modules 18/18、项目 100/100）；14 个 `llvm-*` 专项门全部退出 0。
- **未完成（已定位阻塞）**：全局/字符串/CT 数据。受检快照不含全局初始化表达式
  （全局解析阶段关 AST 捕获、`AstDecl` 无 init 字段），需先补解析/快照，再作物化、
  全局取址指令与字符串/CT；作为 LL5 收尾的下一切片。
- 详见 [完成记录](01-finished/yh-LLVM-LL5切片切片-2026-10-15.md)。

## 2026-10-15 LLVM LL5 结构体切片：字段、嵌套、字面量与联合体

- **范围**：结构体/联合体绑定 ALLOCA；字段读写与复合赋值、嵌套字段、
  字段取址、结构体指针解引用、结构体字面量（含嵌套/结构体数组）、按值复制、
  联合体共享存储、未初始化 `let`（标量/聚合）。
- **实现**：`AST_EXPR_MEMBER` 不携带字段下标，按成员名内容在快照字段表查找；
  字段地址 = 基址 + `SField.offset` 常量 GEP；结构体字面量逐字段写入；
  未初始化 let 用语句内 `=` token 判断（数组类型会先挂长度表达式边）。
- **门禁**：新增 `tests/selfhost/llvm-struct.py`（O0/O2 原生运行 + 切片来源
  拒绝）与运行语料 `tests/yh-run/run/llvm-struct.yh`；`llvmlower` 新增
  `input/struct.yh` 与 `input/slice.yh`；`aggregate` 负例翻转为成功，
  llvm-array/llvm-memory 负例改用切片。
- **验收**（WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）：
  `make`、`make test`（语法 78/78 与 42/42、运行 **314/314**）全绿；
  `make selfhost-native` 全绿（固定点 24 产物一致、自解析 86 文件、
  modules 18/18、项目 100/100）；13 个 `llvm-*` 专项门全部退出 0。
- **未关闭**：切片、全局/CT 数据、聚合参数与返回（LL7）、`for-in`；
  LLVM 默认未切换、种子未滚。
- 详见 [完成记录](01-finished/yh-LLVM-LL5结构体切片-2026-10-15.md)。

## 2026-10-15 LLVM LL5 数组切片：局部定长数组与按值复制

- **范围**：局部定长数组（标量/嵌套元素）的字面量初始化、下标读写与复合赋值、
  `&a[i]`、`let b = a;`/`b = a;` 按值复制；聚合绑定全部 ALLOCA 字节存储。
- **IR**：新增 `IR_OP_ALLOCA`（size/align）、`IR_OP_GEP`（常量或 u64 动态字节
  偏移）、`IR_OP_MEMCPY`（llvm.memcpy 内建）；verifier 与 LLVM 发射同步。
- **Lowering**：`checked_lower_lvalue_ptr` 统一元素存储地址；数组字面量逐元素
 写入（标量元素 GEP 结果带 canonical 元素类型）；聚合复制用 MEMCPY；剥掉
  PRIMARY 包装；`let` 的类型长度前置边取链尾作为初始化值。
- **门禁**：新增 `tests/selfhost/llvm-array.py`（O0/O2 原生运行 + 结构体来源
  拒绝）与运行语料 `tests/yh-run/run/llvm-array.yh`；`llvmlower` 新增
  `input/array.yh`。
- **验收**（WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）：
  `make`、`make test`（语法 78/78 与 42/42、运行 **313/313**）全绿；
  `make selfhost-native` 全绿（固定点 24 产物一致、自解析 86 文件、
  modules 18/18、项目 100/100）；12 个 `llvm-*` 专项门全部退出 0。
- **未关闭**：结构体/联合体/切片、全局/CT 数据、聚合参数与返回（LL7）、
  对齐证明与 `for-in`；LLVM 默认未切换、种子未滚。
- 详见 [完成记录](01-finished/yh-LLVM-LL5数组切片-2026-10-15.md)。

## 2026-10-15 LLVM LL4 goto/label 切片：任意跳转与标签合流

- **范围**：`goto 标签;`/`标签: stmt` 的前向/后向跳转、多前驱合流、跳出循环；
  含 goto/label 的函数全部绑定内存驻留，跨任意 CFG 不需 SSA phi。
- **实现**：`CheckedLabel` 标签表 + 函数入口预分配块；名字按源码字节内容匹配
  （goto 与 label 是不同位置）；循环发现趟回滚恢复已进入标签块状态；
  路径终结后开不可达续块继续降低，保证标签总被访问。
- **门禁**：新增 `tests/selfhost/llvm-goto.py`（O0/O2 原生运行 + 未定义标签
  来源拒绝）与运行语料 `tests/yh-run/run/llvm-goto.yh`；`llvmlower` 新增
  `input/goto.yh`，`llvm-control.py` 首片负例改为尚未支持的 `for-in`。
- **验收**（WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）：
  `make`、`make test`（语法 78/78 与 42/42、运行 **312/312**）全绿；
  `make selfhost-native` 全绿（固定点 24 产物一致、自解析 86 文件、
  modules 18/18、项目 100/100）；12 个 `llvm-*` 专项门全部退出 0。
- **未关闭**：LL4 的 `for-in`（依赖 LL5 聚合切片）；goto 函数全量内存驻留
  属过渡策略；LLVM 默认未切换、种子未滚。
- 详见 [完成记录](01-finished/yh-LLVM-LL4goto切片-2026-10-15.md)。

## 2026-10-15 LLVM LL4 switch 切片：多值 case/default 与合流

- **范围**：`switch` 控制值一次求值 + case 常量比较链，各体无 fallthrough，
  退出块 N 元 phi 合流；体内 `break`/`continue` 仍作用于外层循环。
- **实现**：`checked_lower_switch/switch_body`（路径表 + 独立体快照），
  全部分支终结时退出块作为合法空不可达块；`AST_STMT_SWITCH` 分派。
- **门禁**：新增 `tests/selfhost/llvm-switch.py`（O0/O2 原生运行 + 非常量 case
  来源拒绝）与运行语料 `tests/yh-run/run/llvm-switch.yh`；`llvmlower` 的
  `input/control.yh` 加入 switch。
- **验收**（WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）：
  `make`、`make test`（语法 78/78 与 42/42、运行 **311/311**）全绿；
  `make selfhost-native` 全绿（固定点 24 产物一致、自解析 86 文件、
  modules 18/18、项目 100/100）；十个 `llvm-*` 专项门全部退出 0。
- **未关闭**：LL4 的 `goto`/label 与 `for-in`；LL5 聚合与全局数据；
  LLVM 默认未切换、种子未滚。
- 详见 [完成记录](01-finished/yh-LLVM-LL4switch切片-2026-10-15.md)。

## 2026-10-15 LLVM LL4 首片：嵌套循环、break/continue 与无限循环

- **范围**：`for {}` 无限循环、嵌套 for 的内层 break/continue、循环体局部绑定
  与跨层携带值；`switch`/`goto`/`for-in` 仍按后续切片。
- **实现**：`CheckedFlow` 的单份循环状态改为按深度共存的 `CheckedLoop` 栈
  （上限 16），`checked_lower_carry_record` 逐层记录；顺带修复三个已有缺陷：
  循环体内声明的绑定误入携带 phi、无限循环 exit phi 多算 header 前驱、
  `break` 携带值站点数从未赋值（break + 携带绑定必失败）；发现趟 continue
  不再访问尚未分配的 header phi。
- **门禁**：新增 `tests/selfhost/llvm-control.py`（O0/O2 原生运行 + goto 来源
  拒绝）与运行语料 `tests/yh-run/run/llvm-control-flow.yh`；`llvmlower` 新增
  `input/control.yh`，`llvm-lower.py` 要求嵌套/无限循环降低成功且 `phis > 0`。
- **验收**（WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）：
  `make`、`make test`（语法 78/78 与 42/42、运行 **310/310**）全绿；
  `make selfhost-native` 全绿（固定点 24 产物一致、自解析 86 文件、
  modules 18/18、项目 100/100）；九个 `llvm-*` 专项门全部退出 0。
- **未关闭**：`switch`/`goto`/`for-in`；LL5 聚合与全局数据；LLVM 默认未切换、
  种子未滚。
- 详见 [完成记录](01-finished/yh-LLVM-LL4循环首片-2026-10-15.md)。

## 2026-10-15 LLVM LL5 第一切片：局部标量内存（alloca/load/store）

- **范围**：`&局部/参数`、指针参数与局部、`*p` 读写与复合赋值进入
  alloca + load/store lowering；聚合/全局/切片/指针算术仍带来源拒绝。
- **IR**：`IR_TY_PTR` 扩展为 canonical 指针族（12..24 = `IR_TY_PTR` + 元素
  kind）；新增 `IR_OP_ADDR`（imm = 绑定 ID）；模块层指针统一 `IR_TY_PTR`，
  元素经 type_map 精确校验；通用 kind 12 保留旧 SSA 编码。
- **Lowering**：预扫描标记取址绑定；入口 ADDR（参数同时 spill），读写走
  LOAD/STORE；循环 carry 与 if 合流跳过内存绑定；`&` 只接受 `&变量`。
- **后端**：opaque ptr、`alloca`、`load/store align 1`；指针 PARAM/COPY 用
  零偏移 GEP、指针 CONST 用 `inttoptr`；预检放行指针但继续拒绝浮点/聚合。
- **门禁**：新增 `tests/selfhost/llvm-memory.py`（O0/O2 对象原生运行 + `&arr[0]`
  带来源拒绝）与运行语料 `tests/yh-run/run/llvm-local-memory.yh`；同步更新
  `llvm-lower.py`、`llvmscalar` 指针探针、`build-check.py` 的 checked-lower
  用例；两个 LLVM 门固定优先宿主 `/usr/bin` 工具并清理 crossbin 包装 PATH。
- **验收**（WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）：
  `make`、`make test`（语法 78/78 与 42/42、运行 309/309）全绿；
  `make selfhost-native` 前序全绿（固定点 24 产物一致、自解析 86 文件、
  modules 18/18），build-check 单独复跑 **100/100**（整轮因宿主时钟超时中断）；
  `llvm-memory/llvm-lower/llvm-ir/llvm-runtime/llvm-checked/llvm-front-output/`
  `llvm-module/llvm-module-cache` 全部退出 0。
- **未关闭**：聚合与嵌套取址、全局/CT 数据、切片、指针算术与对齐证明；
  LLVM 默认未切换、种子未滚。
- 详见 [完成记录](01-finished/yh-LLVM-LL5局部内存首片-2026-10-15.md)。

## 2026-10-15 LLVM LL8a：内存运行时 helper（memcpy/memset/strlen）

- **范围**：LL8a 第一片——用 `.yh` 发射代码为 LLVM 后端提供 C 签名的
  `memcpy`/`memset`/`strlen` 弱定义，供 LL5 的聚合复制/清零与需要字节内存的
  lowering 复用；不依赖尚未完成的指针/聚合 lowering，不切换生产默认。
- **实现**：新增 `compiler/backend/llvm_runtime.yh`，在 `llvm_emit_module`
  末尾追加 `weak` 定义与 `llvm.used` 固定；`optnone + noinline + nobuiltin`
  阻止 loop-idiom 把逐字节循环改写成对自身的 libcall；模块已有同名符号时不
  发射。入口按未知对齐逐字节实现，memcpy 保持 C 的非重叠契约，memset 取
  value 低 8 位，strlen 要求已终止字符串。文本、对象与桥产物三路同源。
- **门禁**：新增 `tests/selfhost/llvm-runtime.py`（文本契约、`opt` 验证、
  O2 管线不丢弱定义、对象定义/未解析导入/反汇编无自递归、C 边界驱动覆盖
  0/1/7/8/16/31/32/4096 字节复制与清零、字符串与 UTF-8 边界、桥产物 O0/O2
  原生运行）与运行语料 `tests/yh-run/run/llvm-runtime-memory.yh`（旧后端语义锁）；
  `llvm-ir.py` 的 define 计数改为只统计用户函数。
- **验收**（WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）：
  `make`、`make test`（语法 78/78 与 42/42、运行 308/308）、
  `make selfhost-native`（固定点 cc3→cc4 24 个产物一致、自解析 86 文件、
  项目 100/100）全绿；`llvm-runtime.py`、`llvm-ir.py`、`llvm-lower.py`、
  `llvm-checked.py`、`llvm-front-output.py`、`llvm-module.py`、
  `llvm-module-cache.py` 全部退出 0。
- **未关闭**：yh prelude 目前只有 `memcpy`/`strlen`，`memset` 的 yh 源级调用
  与 runtimebytes 形态要等 LL5/LL8b；helper 现在每模块携带且刻意低优化，
  LL8b 用 yh/IR 迁移完整运行时后评估优化与裁剪；LLVM 默认仍未切换。
- 详见 [完成记录](01-finished/yh-LLVM-LL8a内存helper-2026-10-15.md)。

## 2026-10-15 内嵌 lld 链接器：可行性实测与方案增补

- **范围**：回答「能否把 lld 静态链接进 yh 编译器」并做端到端实测；产出为
  [方案 §LL9L](02-plan/yh-LLVM后端替换实施方案.md) 与
  [完成记录](01-finished/yh-内嵌lld可行性实测-2026-10-15.md)，
  不改生产路径、不改固定 SDK 清单、不滚种子。
- **实测**（WSL/amd64，Ubuntu resolute universe）：`liblld-21` 与固定 SDK 同为
  21.1.8，直接提供 `liblldCommon/ELF/MachO/COFF/Wasm/MinGW.a`（约 13 MB）；
  `liblld-21-dev` 提供官方库内入口 `lld::lldMain`（可重入 + 崩溃恢复）。
  C++ shim + 全量 LLVM 组件静态链得 141 MB（strip 后 123 MB），在同进程内把
  `_start` 对象链接为 `ELF64 ET_EXEC`（x86-64）并运行退出码 7；
  `readelf -d` 无 libLLVM/liblld NEEDED。
- **依赖闭包**：除现有 62 个组件外还需 LLVMLTO/LLVMOption/LLVMObjCopy/
  LLVMCoverage、全部目标后端（lld 的 LTO/管线引用 `InitializeAllTargets` 系列）
  与 Polly（`libpolly-21-dev`）；裁剪需源码构建 `X86;AArch64` + 关 Polly，
  已列为 L9L-1 决策项。
- **方案落点**：实施顺序插入 `LL9L`（LL9 与 LL10 之间），含 SDK 固定/裁剪、
  shim 与探针、`mb_link` 驱动接入、交叉链接预研、ADR-0014 增补、LL10 汇合
  六个切片；切片说明见 [方案](02-plan/yh-LLVM后端替换实施方案.md) 与 [todo.md](todo.md)。
- **未改变**：默认链接仍走平台 cc；asm/ 冻结、link/ 暂停的既有结论不变，
  内嵌 lld 进一步削弱 yh_link 的必要性但不删除其成果。

## 2026-10-15 LLVM LL3：命令行 LLVM 模式、内嵌桥对象发射（工作区，未提交）

- **范围**：把 LL2 的受检快照/模块 IR/纯快照 lowering 接进 `yh` 自身——
  `--backend llvm --target x86_64-unknown-linux-gnu [-O0|-O2]` 直接产出 x86_64 目标文件
  并原生运行，全程只用内嵌静态 LLVM 桥，不调用 clang/llc/opt，也不回退旧后端。
- **桥绑定**：新增 `compiler/backend/llvm_bridge.yh`，用 `@[extern]` 声明
  `yh_llvm_version` / `yh_llvm_emit`（与 `compiler/llvm/bridge.h` 一一对应），
  `llvm_bridge_emit` 校验 opt(0/2) 与 kind(0 对象/1 汇编) 后交给桥原子发布产物。
- **构建接入**（并行 agent 交付）：新增 `tools/llvm-host.py`（prepare/status/shim/link）
  与 `tests/selfhost/llvm-host.py`；`Makefile` 新增 `YH_LLVM_HOST ?= auto` 与 `make llvm-host`；
  `tools/seed-build.py` 新增 `--llvm-host/--llvm-mode`，把链接包装器目录前置到种子子进程 PATH。
  默认 auto：宿主已准备则 `make` 把 ARM64 静态桥链进 `./yh`（`readelf -d` 无 libLLVM，
  `nm` 有 `yh_llvm_emit` 定义）；未准备则打印诊断并按原路径构建，不失败。
- **CLI 与驱动**：`cmd/driver.yh` 新增 `--backend legacy|llvm`、`-O0`、`-O2`、`--emit-llvm`
  （未知后端/未知 triple 明确拒绝）；`cmd/llvm_emit.yh` 提供单文件受检前端
  （已索引文件形态 + 语义两遍 + 快照捕获）与产物发布，`-o` 先发 `<out>.yh-tmp.o` 再链接，
  `--emit-asm` 发汇编文本到 stdout，`--emit-llvm` 只发文本。
- **项目 worker**：`cmd/module_worker.yh` 在 `c_backend != 0` 时进入受检前端
  （不产生任何 `.text/.data/.bss`），语义后 `checked_module_capture` →
  `ast.lower_module` → `backend.llvm_emit_module` → 桥发 `.build/asm/<tag>.o`，
  `--emit-llvm` 另写 `.build/llvm/<tag>.ll`；**不**进入旧 `ast_ir_lower_module` 替换路径。
  `cmd/link_cache.yh` 在 LLVM 模式跳过「汇编→目标」步、直接收这些对象；
  `cmd/module_build.yh` 新增 `.build/llvm/` 子目录。
- **纯快照 lowering 两处实质修复**（`ast/checked_module_lower.yh`）：
  ① 顺序语句必须显式收尾基本块（新增 `checked_lower_continue_block` /
  `checked_lower_exit_block`），否则块保留默认 `unreachable` 终结符、后继语句成死代码、
  循环/分支退出块不可达；② `checked_lower_assign` 成功时原先返回 0（"路径终结"），
  导致循环体只降低第一条语句、`has_latch` 恒 0、循环没有回边；改为返回 1 后
  `for i < 3 { i += 1; }` 与双语句循环体都能产生 header phi 与回边。
- **自举链接**：`tests/selfhost/native-selfhost.py` 新增 `llvm_shim_for_seed`，
  按种子文件名推导宿主并把链接包装器目录前置到各代 `yh build` 的 PATH——
  否则 cc2/cc3/cc4 编译 `backend/llvm_bridge.yh` 时会 `undefined reference to yh_llvm_emit`。
  未准备 SDK 时只警告并按原路径继续（与 make/seed-build 的 auto 语义一致）。
- **验收**（WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）：
  `make` 退出 0；`make test` 退出 0（语法 78/78 与 42/42、运行 307/307）；
  `llvm-lower.py`、`llvm-ir.py`、`llvm-front-output.py`、`llvm-checked.py`、
  `llvm-module.py`、`llvm-module-cache.py` 全部退出 0；单文件端到端
  `scalar.yh` 退出码 **13**（= arithmetic(5)9 + loop(4)4），探针 A 退出 **3**、
  探针 B 退出 **63**，生成文本经 `opt-21 -passes=verify` 通过。
- **未关闭的边界**：
  ① **损坏 `.s.ct` 触发 worker SIGSEGV（未定位，阻塞 `build-check` 满分）**：
  隐藏正文签名由 `int` 改 `i64` 后构建，worker 段错误而非输出
  「公开 CT 函数与 .s.ct 正文签名不匹配」。用 HEAD 源码构建的编译器正确拒绝，
  `YH_LLVM_HOST=0` 同样崩 → 属当前工作区改动的回归、与桥无关；已排除名字池越界、
  `iface_ct_load` 各阶段、体积与栈上限。复现与排查建议见 docs/todo.md。
  `build-check.py` 因此为 **99/100**。
  ② LLVM 模式未常驻（默认仍旧 ARM64 发射）；③ 首片之外形态（全局对象/聚合/指针/浮点/
  间接调用/变参/`switch`/`goto`/`for-in`）明确拒绝不回退；④ 未滚种子。
- 详见 [完成记录](01-finished/yh-LLVM-LL3命令行模式与对象发射-2026-10-15.md)。

## 2026-10-15 LLVM LL2：纯快照 lowering 打通，受检快照/模块 IR 一并提交

- **范围**：关闭 LL2 的「受检前端 + 受检快照 + 模块 IR + 纯快照 lowering」四个切片，
  并把上一轮记录的「工作区未提交、make 为红」状态结清。生产默认仍是旧 ARM64 发射，
  LLVM 模式常驻、IRModule 序列化、R2b 契约对齐仍未完成，LL2 整体保持未关闭。
- **新增 lowering**：`compiler/ast/checked_module_lower.yh` 的 `lower_module` 把
  `CheckedModule` 降低为 `ir.IRModule`（0 成功 / 1 首片不支持并带来源 / -1 内部错误，
  失败不发布候选且不改变出参）。首片覆盖顺序 `let`、简单与复合赋值、表达式语句（直接调用）、
  `return`、`if/else`（含 else-if 链）、条件循环 `for cond {}`、`break`/`continue`、
  短路 `&&`/`||`、一元 `!`/`-`、转换、算术/位/比较与直接调用。
  循环沿用两趟协议（发现趟收集携带绑定与 break/continue 站点数，真实趟预留 phi 输入）。
- **类型闭包拆分**：`CheckedStorage`/`CheckedString` 留在 `checked_module.yh`，
  `CheckedFlow`/`CheckedLower` 放进新增的 `compiler/ast/checked_module_ctx.yh`——
  模块按文件名字典序编译且要求类型先声明后使用，两个结构体之间不再互相引用
  （lowering 的构造器指针由上下文显式传参）。
- **根因修复（有复现）**：`checked_lower_binding` 原先按 `binding.sym_id` 回查快照符号表，
  但 `gen/symbols.yh` 的 `scope_pop` 会截断参数/局部槽位，快照符号表天然不含这些行
  （`AstBinding.sym_id` 按注释只是「解析时符号槽，仅作诊断，不作持久身份」）；
  改为只使用绑定自己的快照字段后，`inc(x) { return x + 1; }` 这类最普通函数才能降低。
  直接调用保留符号槽防护：被调目标必须仍解析到同名同型的函数符号，回收槽错配一律拒绝。
- **测试夹具**：`tests/modules/projects/llvmlower/fixture.yh` 实现真实单文件前端
  （读源→词法→文件头→顶层声明索引→两遍语义），在 AST 捕获开启状态下交出快照；
  与 `cmd/driver.yh` 的 `run_file_check` 同序，差别只有「语义前就置 `c_ast_capture=1`」
  「采用已索引文件形态」「路径同时进固定缓冲与名字池」三处，且都是让 arena 活到快照生成之后所必需。
- **验收（全部在 WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）**：
  `make` 退出 0；`make test` 退出 0（语法正例 78/78、反例 42/42，运行 307/307）；
  `make selfhost-native` 退出 0（固定点 cc3→cc4 共 24 个产物一致、cc4 自解析 82 文件、
  运行时/缓存/`check` 等专项门通过）；`build-check.py` **100/100**
  （新增 `llvm-snapshot-lowering`）；`llvm-front-boundary.py`、`llvm-front-output.py`、
  `llvm-checked.py`、`llvm-module.py`、`llvm-lower.py`、`llvm-semantics.py`、`llvm-ir.py`
  全部退出 0。日志在 tmp/llvm-migration/ll2-full-*.log/.exit 与 ll2-gate-*.log/.exit。
- **纯快照 lowering 观察值**：`scalar.yh` 得到
  `lower-snapshot=ok functions=5 phis=2 calls=4`（编译期函数不计入；if/else 合流与循环携带各一个 phi）；
  `pointer.yh`/`aggregate.yh` 返回 1，诊断带真实来源与被拒函数名
  （`.../input/pointer.yh:5:9: LLVM lowering pointer_body: ...`）且出参保持零初始化。
- **仍未验收**：LLVM 模式未常驻（`--backend/--target/-O0/-O2` 与 worker LLVM 分支未接入）、
  `IR_MODULE_VERSION` 只是内存内版本、跨缓存身份键未落、首片之外的形态
  （全局对象/聚合/指针/浮点/间接调用/变参/`switch`/`goto`/`for-in`）明确拒绝不做回退；
  未滚种子，`bin/yh` 与 `bin/yh-linux-arm64` 保持原哈希。
- 详见 [完成记录](01-finished/yh-LLVM-LL2受检快照与纯快照lowering-2026-10-15.md)。

## 2026-10-14 LLVM LL2 首片：受检前端闸门、受检快照与模块 IR（工作区，未提交）

- 新增 `compiler/gen/front_stage.yh`：`front_checked_begin/verify/end` 建立独立于 check 的
  受检前端阶段，进入时拒绝已有旧输出或重复进入，退出前必须核对 text/body/data/bss 四缓冲为零，
  失败保留禁发状态。`gen/state.yh` 增加 `c_front_checked`；`gen/buffer.yh` 的
  em_/dat_/bss_ 写入与 `gen/emit_arm64.yh` 的体缓冲拷贝在该阶段整体静默；
  `cmd/driver.yh` 的单文件 check 与 `cmd/module_worker.yh` 的模块 check 成对进出该阶段。
- 新增 `compiler/ast/checked_module.yh` 与 `checked_module_verify.yh`：语义遍历结束后独立复制
  AST、语句/表达式/边、绑定、声明、类型/字段/名称、签名、符号表与源码字节，原 ID 在快照内
  继续指向同一行；原 arena 销毁后仍可校验，重复释放安全，非法捕获不留部分对象。
  `cmd/module_worker.yh` 在 check 的语义结束处 capture→verify→release；`--stats` 新增
  `legacy_bytes`（四个旧缓冲长度之和，见 `cmd/module_build.yh`）。
- 新增 `compiler/ir/ssa_module_00_model.yh`、`ssa_module_10_build.yh`、`ssa_module_20_verify.yh`：
  模块级逻辑符号、类型（结构/联合/数组/切片/函数签名）、全局初始化目录、来源表与位置，
  全部深拷贝；`ir_module_init/add_source/add_type/add_symbol/add_global/add_function/release/verify`
  从完整 triple 推导目标键并核对指针位宽、字节序与布局，拒绝坏来源、未知名字、
  错 ABI/返回/参数与未闭合签名。
- 门禁与 fixture：`tests/selfhost/llvm-front-output.py`（真实项目 check 断言全部 worker
  `legacy_bytes=0`、污染拒绝、退出后旧路径恢复）、`llvm-checked.py`（销毁原 arena 后快照校验、
  重复释放、非法捕获清理、旧汇编区间无关）、`llvm-module.py`（完整模型/深拷贝/目标/布局/
  重定位/函数 verifier/重复释放），以及 `llvmfront`、`llvmchecked`、`llvmmodule` 三个项目 fixture；
  `tests/modules/build-check.py` 增加 `llvm-front-zero-output`、`llvm-module-ownership`、
  `llvm-checked-snapshot` 三个常规项目用例。
- 命令与证据：`python3 tmp/llvm-migration/run-ll2-acceptance.py` 用 ll2-base.tar 加本片 16 个文件
  与 3 个 fixture 冻结验收树（明确排除并行中的 LLVM emitter 与 checked lowering），树内先跑
  `make test selfhost-native`，再依次跑 `llvm-front-boundary.py`、`llvm-front-output.py`、
  `llvm-checked.py`、`llvm-module.py`，实际退出 0；日志 tmp/llvm-migration/ll2-owned-acceptance.log
  与 .exit。
- 观察到的计数（同上日志）：语法正例 78/78、反例 42/42；运行语料 run 168/168、fail 131/131、
  pass 8/8、总计 307/307；模块固定点候选 cc3→cc4 共 24 个产物一致；cc4 自解析 78 个源文件 OK；
  modules 18/18；project cases 99/99，其中 `llvm-target-identity`、`llvm-front-zero-output`、
  `llvm-module-ownership`、`llvm-checked-snapshot` 四项 OK。受检前端 stats 三行记录
  （main 与 gen 模块行、调度行）均为 `legacy_bytes=0`、`asm=0`、`ir_functions=0`
  （tmp/llvm-migration/front-output/check-stats.log）。
- 尚未关闭的边界：纯快照 lowering `compiler/ast/checked_module_lower.yh` 的语句/表达式降低
  仍在实现，`llvmlower` fixture 的 `lower_fixture_capture` 仍是返回 -1 的桩、
  `tests/selfhost/llvm-lower.py` 未通过：该门唯一一次已记录的运行停在构建期
  （tmp/llvm-migration/checked-lower/build.log，23:25，`main/main.yh:11:26`
  报「模块没有导出该名字」），此后未重跑；
  当前工作区源码 make 为红，失败点随实现移动；本轮观察到的三次 make 均退出 2：
  2026-10-14 23:31 报 `ast/checked_module_lower.yh:253:41 错误: 引用了未声明的名字`
  （ll2-resume-make.log/.exit）、2026-10-15 00:28 报
  `ast/checked_module.yh:61:48 错误: 未知类型（类型必须先定义）`、00:33 报
  `ast/checked_module_ctx.yh:2:8 错误: 导入未使用`（后两次共用 ll2-lower-build.log/.exit，
  每次重跑覆盖）。行号只对应当次日志，不是稳定结论。冻结树验收之后未在当前源码上重跑完整门，
  因此本片结论只覆盖那棵树，不覆盖当前工作区。
- 仍未验收项：LLVM emitter（`compiler/backend/llvm_module.yh`、`llvm_scalar.yh`、
  `tests/selfhost/llvm-ir.py`、`llvmscalar`）只有红门日志，无通过证据；IRModule 序列化及其版本
  尚未实现（`IR_MODULE_VERSION` 目前只是内存内版本），跨缓存身份键未落；LLVM 模式未常驻，
  check 侧的受检快照消费完即释放。本片未提交、未滚种子，LL2 整体未关闭。
- 详见 [实施方案 LL2 小节](02-plan/yh-LLVM后端替换实施方案.md) 与
  [LLVM 目标身份设计](03-design/yh-LLVM目标身份设计.md)；完整完成记录待归档到 `docs/01-finished/`。

## 2026-10-14 LLVM ARM64 启动 SDK：静态桥与源级调用验收

- 按用户授权与快照/模块 IR 并行实施 ARM64 固定 SDK，显式 --host 选择 LLVM 桥
  运行架构；原 x64 目录和普通 GNU 工具保持独立。ARM LLVM/zlib/zstd 包、SHA-256
  与许可证锁定，桥源码/头文件/归档/清单身份写入构建配置，未安装系统 LLVM。
- qemu 下 O0/O2、ARM64/x64 对象与汇编、ARM 程序执行、8 类负例、坏包/错架构
  拒绝、失败保留旧产物通过。ARM 直接依赖仅 libc/libm/加载器，无 LLVM、Clang、
  libstdc++ 或 libgcc_s 动态依赖；当前交叉构建实际要求 GLIBC_2.38。
- 独立审查发现隔离门旧根复用可能导致假绿，ARM/x64 均改为每轮新空根；WSL root
  重新执行两套 chroot 门退出 0。记录 ll0e-arm-final-fresh、ll0e-x64-final-fresh。
- 新增 llvm-embedded-arm64-probe.yh：真实 yh 运行时和 C ABI 调用静态 ARM 桥，
  发射 x64 对象，在 WSL 原生链接运行退出 0；ARM 报告 yh_source_probe=true。
- 详见 [完成记录](01-finished/yh-LLVM-ARM64静态SDK-2026-10-14.md)。这完成启动 SDK
  与源级桥前置条件，生产 yh LLVM pipeline 和连续自编尚在后续，不滚种子。

## 2026-10-14 LLVM LL2-T：目标身份与前端解析边界

- 新增 TargetInfo 与四个 Unix canonical triple，布局固定 LLVM 21.1.8；严格解析拒绝
  未知/缺失目标，旧 -target 别名显式映射 AArch64，默认目标来自编译器构建身份。
- 编译期目标条件与 OS/架构组合源后缀共用输出身份；check 可检查 x64，旧机器输出
  在 LLVM 接入前拒绝 x64。选择输出目标不改变宿主身份元数据，宿主操作迁移仍在后续。
- 红绿复现未知目标静默接受及组合后缀重复 main，目标专项门通过；WSL make 与完整
  make test selfhost-native 实际退出 0：语法 78/42、运行 307/307、固定点 24、
  自解析 72、模块 18/18、项目 96/96。日志 ll2-target-acceptance-final.log/.exit。
- 按用户授权启动多 agent；独立只读审查及额外 22 项目标边界探针通过，未发现
  Critical/Important 问题；修正文档中宿主操作已统一的过宽表述。种子未更新。
- 详见 [完成记录](01-finished/yh-LLVM-LL2目标身份-2026-10-14.md)。LL2 快照/模块 IR
  与停止预发旧汇编继续实施，不把目标元数据验收当成 LLVM 替换完成。

## 2026-10-14 LLVM LL1：八类语义与调用政策验收

- 新增整数、一元类型、浮点位型/舍入、内存/效果四个 `.yh` 探针，结合已有四个
  LLVM 探针建立八类矩阵：移位、除模、转换、bool、浮点、内存、效果和默认初始化。
- SEM-04/05 红绿：运算结果先按源宽度规范化再扩大；常量一元保留整数类型，bool 升
  int；typed CT 使用已检查的结果类型，括号不继承原符号。SSA !i64 使用同型零比较。
  编译器自身的宽位掩码显式改为 i64，避免依赖旧 int 运算漏截断。
- SEM-06/07 红绿：聚合实参求值时固定副本，直接/间接数组和切片描述符隔离通过，
  数组到指针仍共享；f32 常量引用从保存的 f64 位型正确窄化，默认最近偶数舍入、
  逐步 f32 算术、零符号、无穷/非正规数与 CT/动态一致。
- 单文件探针 8/8、项目探针 8/8；实际 SSA 发射 bool 8、CFG 2、整数 11、一元 1、
  内存探针中的纯标量 1；其余主体仍走旧发射，未冒充 LLVM 覆盖。
- WSL make、串行 make test selfhost-native 实际退出 0：语法各 78/42、运行 307/307、
  候选固定点 24、自解析 71、模块 18/18、项目 95/95与专项门全绿，种子保持原哈希。
  日志 tmp/llvm-migration/ll1-boundary-acceptance.log/.exit。详见
  [LL1 完成记录](01-finished/yh-LLVM-LL1语义契约-2026-10-14.md)。
- [语义/ABI 契约](03-design/yh-LLVM语义与ABI契约.md) 锁定迁移规则、来源与安全 LLVM
  实现要求。LL1 已完成，进入 LL2；LLVM 对象接入、全语言 lowering、原生自举与默认切换仍待后续。

## 2026-10-14 LLVM LL1 / LLVM-SEM-02：浮点转整数一致性

- 正式回归先退出 1：常量/typed CT 将 2^63 转 u64 得到 i64 最大值；动态窄转换
  在后续扩大表达式中不截断。分别改用目标符号性的完整 64 位转换与目标宽度规范化。
- 常量与 CT 共用 sem_fold_fp_to_int，动态转换共用 em_normalize_int；窄整数按
  64 位饱和后保留低位，不引入新的运行期错误。NaN、无穷、f32、负数、bool 字节均有回归。
- make 与定向单文件/项目门通过；WSL 串行 make test selfhost-native 实际退出 0：
  运行 303/303、两层语法 78/42、固定点 24、自解析 71、模块 18/18、项目 95/95及专项门全绿。
- 首次完整门被观察会话 Hangup 中止，已确认原进程结束后独立运行，退出码写入 tmp；
  不将中断算为通过。日志 ll1-fp-acceptance-final.log 与 .exit。详见
  [完成记录](01-finished/yh-LLVM-LL1-浮点整数转换-2026-10-14.md)。
- 浮点项目当前实际 SSA 发射为 0，仍走旧后端；LLVM 饱和 intrinsic 政策已锁定，
  LL6 再验证 LLVM 路径。种子未更新，整数边界/一元结果类型等 LL1 工作继续。

## 2026-10-14 LLVM LL1 / LLVM-SEM-03：bool 字节与 CFG 回归

- 修复项目 SSA 把源 bool 当作一位值的问题：bool 保留低 8 位，条件/逻辑结果单独
  规范为 0/1；整数与 bool 显式转换、逻辑非结果类型同步。IR 序列化升为 6，缓存键升为 11。
- 扩大覆盖后复现并修复两个 CFG 问题：CALL 编号按线性指令数组校验，块内局部绑定
  不合并为含缺失值的 phi。重复/无引用调用记录和旧一位 bool 仍被 verifier 拒绝。
- 新增两个 `.yh` 回归与项目语义门；第四代候选实测 bool 8 个、控制流 2 个函数实际
  SSA 发射成功。单文件/项目路径的返回、条件、逻辑、副作用顺序、phi 和字节存储一致。
- WSL 串行 `make test selfhost-native` 退出 0：运行 302/302、语法 78/42、24 个固定点
  产物一致、自解析 71 文件、模块 18/18、项目 95/95及全部专项门通过。种子未更新。
- 一次此前复跑仅显示 301/302，失败明细被旧脚本丢失；增加失败输出后保留候选复跑和
  串行完整主门均为 302/302，未推断未证实的根因。详见
  [完成记录](01-finished/yh-LLVM-LL1-bool与CFG-2026-10-14.md)。

## 2026-10-14 LLVM LL1 / LLVM-SEM-01：NaN 顺序比较修复

- 探针复现：NaN < 0 与 NaN <= 0 返回真，新增 llvm-float-nan-comparisons.yh
  在修复前退出 1。根因是 ARM64 FCMP 无序 NZCV=0011 被整数 lt/le 条件码接受。
- 发射改用 mi/ls；常量折叠、typed CT 的 < / <= 增加左右有序守卫，保证旧种子
  编出的第一代候选就正确。四个顺序关系遇 NaN 为假，!= 为真，不规定 NaN payload。
- 验证：make、定向红绿回归、make test、make selfhost-native 通过；运行语料新增为
  300/300，左右 NaN、f32/f64、常量折叠/typed CT/动态及正常有序比较通过。
- 语义和 LLVM 谓词对应写入 [语义与 ABI 契约](03-design/yh-LLVM语义与ABI契约.md)；
  文法没有变化。LL1 其他探针和两个已发现的转换/SSA bool 问题仍未关闭。

## 2026-10-14 LLVM LL0E：固定 SDK 与静态桥独立验收

- 固定 LLVM 21.1.8 SDK 包下载地址、SHA-256、静态组件闭包与桥 ABI；从已校验包
  提取 C API/配置头、实际 `.a` 和许可到 tmp，未向系统安装 LLVM。
  SHA-256 为 aa13e8f4ad91572eaf40e959232d32e07362856e14f22861236017c544ed11d4，
  错哈希明确拒绝。静态桥配置另保存桥源码/归档哈希，供后续缓存接入。
- C API 薄桥独立管理 context/module/target machine，运行前后 verifier、O0/O2、generic
  CPU、静态重定位与对象/汇编输出；C ABI 诊断有界，失败保留既有产物并清理临时文件。
  目标初始化通过 pthread_once，共享登记表，每次调用的模块和目标机器独占。
- 先观察“桥尚未实现”的红门，后真实构建/运行测试宿主：无 LLVM 工具 PATH，
  O0/O2 x64/ARM64 对象 machine=62/183，x64 原生退出 0，汇编输出成功；
  8 类拒绝、重复成功/失败、零/一字节诊断、既有产物保留、写入失败清理全部通过。
- 额外 WSL root chroot：根目录仅含测试宿主、输入和必要 OS 动态库，成功生成 O2
  x64 对象。readelf NEEDED 为 libc/libm/zlib/zstd/加载器，无 libLLVM/libclang；
  libstdc++/libgcc 静态链接。当前 SDK 分发范围为本机 WSL Ubuntu x64。
- 发现 GNU BFD 在 DrvFS 上大量 read/lseek 9P RPC，普通静态链接实测 459.8 秒并
  超过原门超时；修正为同一 GNU 链接器、归档/输出匿名 memfd，最终文件原子发布到 tmp。
  不使用系统 lld，也不产生 tmp 外的持久临时文件。
- 验证：`python3 tests/selfhost/llvm-embedded.py --chroot` 在 WSL root 下退出 0；
  `.yh` 桥签名由当前编译器发射检查通过；make、make test、make selfhost-native 退出 0，
  运行语料 299/299、两代固定点和项目验收 95/95。详见
  [LL0E 记录](01-finished/yh-LLVM-LL0E内嵌桥-2026-10-14.md)。
- 边界：这次是独立桥验收，尚未接入 yh 前端/默认驱动/自举；LLVM 全语言覆盖、
  原生 x64 编译器与最终无系统 LLVM 的 yh 自编门仍待 LL1–LL11，种子未更新。

## 2026-10-14 LLVM LL0：覆盖、来源与启动基线

- 新增 llvmcoverage `.yh` 项目和 llvm-baseline.py；先观察缺覆盖字段的红门，
  实现后确认 fixture 受检 3、SSA/实际发射 1、回退 2。comptime 不计分母，
  每条回退记录文件、行列、函数和稳定阶段原因，脚本排序并检查计数等式。
- compiler/ 实测受检 923、SSA 验证 22、实际后端发射 22、前端拒绝/回退 901；
  现有 ir_functions 语义和统计顺序保留。完整来源目录在
  tmp/llvm-migration/baseline/coverage.json；LLVM 全覆盖仍未实现。
- 固定 LLVM 21.1.8 clang oracle 生成 x64 ELF machine=62，原生 gcc 链接、退出 0；
  CPU、旧种子/工具/源码哈希分别记录，旧 ARM64/qemu 与原生工具分开。
- 性能工具增加冻结快照选择和原始 JSON 样本保存。已复现并修复 CRLF 校验误报，
  独立回归保证 LF/CRLF 等价、真实内容篡改拒绝、临时测量副本为 LF。
  R0 历史语料因字段 pub 语法已删除而无法由当前编译器构建，本轮冻结当前源码，
  不改写历史语料。systemless、每类 20 轮：无改动中位数 4815 ms/p95 5353 ms，
  单函数变化 6700/7372 ms，冷编 10109/10943 ms；峰值 RSS 67.8/68.4/67.9 MiB。
  这是 WSL/DrvFS + ARM64 qemu 数据，SDK 链接研究同期运行，LL11 正式对照另行无干扰复测。
- 验证：make、make test、make selfhost-native 全部退出 0；运行语料 299/299，
  两代固定点通过，项目验收 95/95；LL0 覆盖门、性能输入门和 60 个原始样本验证通过。

## 2026-10-14 LLVM 实施启动与内嵌政策确定

- 用户已授权按现有方案开始实施、逐阶段验收后提交，新增硬要求为 yh 内嵌 LLVM、
  不依赖系统 LLVM。已同步设计、实施方案、ADR-0014、问题清单和 todo。
- 生产路径改为固定 LLVM 21.1.8 静态 SDK + 薄 C ABI 桥；新增 LL0E，正常编译不调用
  系统 clang/llc/llvm-as/opt/llvm-config，不依赖 libLLVM 动态库；保留平台链接驱动。
- 启动基线：WSL Ubuntu x86_64，旧 ARM64 种子经 qemu；make test 退出 0，语法两门
  各 78/78 正例、42/42 反例，运行语料 299/299。make selfhost-native 退出 0，
  两代固定点、自解析与专项门通过，项目验收 95/95。日志在 tmp/llvm-migration/。
- 此条只确认政策与启动基线，不宣称 LLVM 发射、内嵌 yh 或原生 x64 自举已完成。

## 2026-10-14 全部项目改动提交前验证

- **范围**：按用户要求统一提交当前项目改动，包含汇编器稳定化、Linux/AArch64
  静态 ELF 链接器及验收用例、LLVM 后端替换设计和 Linux/x86_64 优先实施方案。
- **行尾**：核对 HEAD、暂存区和工作文件后确认大批状态差异来自 Windows CRLF；
  Git 操作统一使用 `core.autocrlf=input`，暂存内容保持 LF，保留全部实际内容改动。
- **环境**：本机 Ubuntu WSL x86_64，AArch64 产物经 qemu-user/binfmt 运行；
  `PATH` 前置 `tmp/boot/crossbin`，`SEED=bin/yh-linux-arm64`，
  `YH_LINK=/nonexistent`，临时日志位于 `tmp/commit-20261014/`。
- **构建与回归**：`make` 成功（产物已是最新，种子哈希校验通过）；`make test`
  三层通过，ANTLR 与编译器语法模式均为正例 78/78、反例 42/42，运行语料为
  run 160/160、fail 131/131、pass 8/8，合计 299/299。
- **自举主门**：`make selfhost-native` 全部通过，两代模块固定点一致，cc4 自解析
  71 个源文件，模块语料 18/18，项目验收 95/95；并发扫描、前端快照、自有运行时、
  `yh check`、外部文件系统构建和链接缓存检查均通过。
- **汇编器**：`python3 asm/tests/check.py --compiler "$PWD/yh" --full` 成功；
  自检、编码、拒绝路径、对象差分及 Darwin 字节快照通过。全量语料链接运行差分
  169 个中行为一致 159 个、不一致 0 个、跳过 10 个（8 个模块缺入口/运行时符号，
  2 个历史语料被两边汇编器共同拒绝）；参照为 clang-21，运行使用 qemu-aarch64。
- **链接器**：`python3 link/tests/check.py --compiler "$PWD/yh" --full` 成功；
  自检与 CLI 契约通过，端到端验收 7/7、GNU ld 差分回归 7/7。
- **提交检查**：暂存差异检查通过；构建缓存、日志和临时产物按现有忽略规则处理。

## 2026-10-14 LLVM 替换首期改为 Linux/x86_64（方案调整）

- **用户决定**：Linux x86 优先，以便本机验证；按此前架构范围解释为 x86_64。
- **同步**：[设计](03-design/yh-LLVM后端替换设计.md)、
  [实施方案](02-plan/yh-LLVM后端替换实施方案.md)、
  [问题清单](02-plan/yh-LLVM后端替换问题清单.md)、ADR 和 todo。
  首期为 `x86_64-unknown-linux-gnu`，14 个任务、82 个未勾选步骤。
- **前移工作**：System V C ABI、x64 syscall/目录/时钟/内存/进程桥、原生链接、
  原生编译器和独立 x64 种子；LLVM-14/15 的 x64 部分升为 P0。
- **自举**：旧 ARM64 种子经 qemu 产 A，A 经 LLVM 产原生 B，B/C/D 原生连续自编。
  LL3 起测试程序可本机原生运行，LL10 才关闭编译器原生自举；x64 链接避开 crossbin/gcc。
- **种子/退役**：x64 全门通过后滚 `bin/yh-linux-x64`，ARM64 种子/哈希保留；
  F1 改为 Linux/AArch64，回归通过后才执行 LL12 旧后端退役。
- **验证**：本机最小 IR 经 clang-21 产 x64 对象、原生 gcc 链接，ELF machine=62，
  直接运行 exit 0；主文档编号/链接/约束/顺序一致性检查通过。
- **范围**：仅调整文档并做工具链探针，未实现后端、未修改构建默认或种子。
  详见 [顺序调整记录](01-finished/yh-LLVM后端Linux-x86_64优先调整-2026-10-14.md)。

## 2026-10-14 LLVM 后端替换方案与前置问题清单交付（仅文档）

- **用户范围**：最终替换后端为 LLVM；本轮明确选择“先交付方案、问题清单和处理顺序”。
- **交付**：[16 项问题清单](02-plan/yh-LLVM后端替换问题清单.md)、
  [替换设计](03-design/yh-LLVM后端替换设计.md)、
  [实施方案](02-plan/yh-LLVM后端替换实施方案.md)（14 个任务、76 个未勾选步骤）、
  [ADR-0014 草案](adr/0014-yh采用LLVM作为正式代码生成后端.md)。
- **处理顺序**：基线→语义/ABI契约→受检边界/目标→严格LLVM首片→内存helper→
  存储/控制流/浮点/调用→完整运行时→驱动/缓存→自举及R2b硬门→性能/默认切换→退役。
  后续 Linux/x86_64、macOS/ARM64、Windows/x86_64，再补其余两格。
- **关键澄清**：991/22 是已有文档基线，需要重测；runtimebytes 自包含门不能扩大为
  所有模块无导入；qemu 下缺省目标不能只看 uname；LLVM 生成 helper 的依赖需先关闭。
- **文档检查**：问题 ID、任务映射、链接/代码块和全局约束核对通过；工具重新核对为
  LLVM 21.1.8，六格最小 IR 的 verifier/O2/对象生成通过，未验链接、运行或自举。
- **状态**：16 项代码/架构问题未关闭，没有编译器/测试源码改动，没有运行编译器构建门、
  改默认后端或滚种子。详见 [方案交付记录](01-finished/yh-LLVM后端替换方案交付-2026-10-14.md)。

## 2026-10-14 后端接入 LLVM 的可行性与差距分析（只交付分析，未改代码）

- **交付**：[分析稿](02-plan/yh-LLVM后端接入可行性与差距分析.md)（现状事实、五层差距
  L0–L4、12 条风险、分期路线 P0–P3、5 条待决策问题、核对坐标表）。
- **核心结论**：瓶颈不在 LLVM，而在自家 IR 的覆盖率与完备度——全量自编 991 个函数
  上下文只有 22 个进入 typed SSA（2.2%，`compiler/README.md:171`）；旧发射器是
  arm64 专用的汇编文本发射器，且与 SSA 后端靠**在同一输出缓冲里文本替换**混合
  （`compiler/backend/arm64.yh:371`），因此非 arm64 目标没有回退路径，而 arm64 上
  又必须解决"一个模块两条代码生成路径"的混排问题（LLVM IR 无法与手写汇编同缓冲混排）。
- **附带发现（无论是否接 LLVM 都成立）**：语义尚未锁定的几处会在跨目标时真的分叉——
  整数除零（AArch64 返回 0 / x86_64 SIGFPE）、`INT_MIN/-1`、移位量 ≥ 位宽
  （arm64 与常量折叠都按 63 掩码，LLVM 里是 poison）、未对齐访存与 bool 的内存表示
  （`ir/ssa.yh:961-970`、`backend/arm64.yh:110-122`）；建议先补探针用例再谈移植。
- **环境事实**：本机 WSL（Ubuntu x86_64，已注册 qemu-aarch64 binfmt）LLVM 工具链齐备
  （clang/llc/llvm-as/opt/llvm-config/llvm-mc 均为 21.1.8），LLVM 21 只支持 opaque
  pointer，最低版本与可用语法子集须写进设计。
- **未做**：未改任何编译器代码、未改默认后端、未新增用例；待决策项见分析稿 §5，
  P0–P3 任务已记入 [todo.md](todo.md) 的「LLVM 后端接入」小节。

## 2026-10-13 编译器已知缺陷清单全部处理（11 项 + 新发现 3 项）

- **背景**：`docs/todo.md` 的「编译器已知缺陷（待修复）」11 项自 2026-10-07/09 挂起
  （`asm/`、`link/` 两个工具项目一直按同一约定规避）。本轮逐项复现 → 定位 → 修复或
  复核，并补齐 `tests/yh-run`、`tests/modules` 用例；过程中另发现并修掉 3 个缺陷。
- **修复（7 项）**：解引用整体结构体赋值（`sem_unary` 解引用聚合不再按标量装入，
  `run/176`）；聚合元素字面量运行期错值（`em_store_sized` 对聚合整块拷贝，`run/177`）；
  `pub const` 接口值 32 位截断（共用 `iface_emit_const_value`，fixture `pubconst`）；
  结构体指针加法缩放（`em_scale_index` 非 2 的幂改乘法，`run/178`）；嵌套三元重复标签
  （标签改嵌套栈，`run/179`）；寄存器同名符号（发射名追加 `__yhreg`，`run/182` + 新增
  `asm-symbols-safe` 指令）；别名/同长数组 type_id（布局请求按来源去重 + 布局完成
  规范化，`run/180`/`181`）。
- **复核为不复现（4 项）**：旧种子含 `e/E` 的十六进制字面量、SSA 混合宽度算术、局部
  数组下标取址、跨模块结构体字段导入使用（后两项现行实现已正确，分别由 `run/178`
  后半段与 fixture `importfield` 锁定）。
- **新发现并修复**：① SSA 字面量适配两处——二元运算与调用实参把 `0x80000000` 按 i32
  装入再符号扩展成 `0xFFFFFFFF80000000`，静默错值（`ast_ir_build.yh`、`ast_ir_call.yh`）；
  ② const 长度数组在全局/字段/形参/返回位置误报「编译期常量尚未就绪」（布局期按依赖
  求出**声明在前**的普通整数 const，前向引用仍拒绝，`run/180`/`181` + `fail/118`）；
  ③ 数组类型编号不一致的根治（同上一项）。
- **对照证据**：4 个新用例在**未修复的入库种子**上分别复现段错误、垃圾值、缩放错值、
  汇编器拒绝（`symbol .L14 is already defined`），`run/182` 报「发射汇编使用了寄存器
  同名符号：d8, lr, w12, x0」；`clang-21` 实测 `bl w12` 被拒、`adrp x0, w12` 放行。
- **门禁**：`make test` 全绿（run 160/160、fail 131/131、pass 8/8，合计 299/299；
  ANTLR 正例 78/78、反例 42/42）；`make selfhost-native` 全绿（cc4 自解析 71 文件、
  两代固定点、模块语料 18/18、项目验收 95/95）。
- **种子**：Linux 种子滚到本轮产物（`33733767…` → **`073282e9f1f773f162ccf9674a86f357e3bd6c9b74ccb65fe613968566916ccd`**，
  `bin/yh-linux-arm64.sha256` 同步）；滚后用新种子复跑 7 个新用例与 `verify-seed` 全绿。
  macOS 种子 `bin/yh` 由 darwin CI 作业补代（本机无 Mach-O 工具链）。
- **设计文档同步**：[编译期过程设计](../03-design/yh-编译期过程设计.md) §5/§6 记录
  「布局期普通 const」与「数组类型编号规范化」的新判据；todo 的缺陷清单章节改为
  指向本条与完成记录。详见
  [完成记录](01-finished/yh-编译器已知缺陷清单-2026-10-13.md)。

## 2026-10-13 macOS 种子追平（主门验过的中间代种子入库）

- **背景**：0.0.4 发布后，入库 `bin/yh` 仍是带「struct/union/enum 必须带 pub」门禁的旧一代
  （`2e150732…`，2,272,608 B），release/CI 的 darwin 作业都得先跑「种子自动补代」才能构建
  当前源码——这条 todo 挂了多日。
- **做法**：`workflow_dispatch` 触发 `ci.yml` 的 `darwin-arm64` 作业（run `38414283098`，
  commit `a19ffb0`）：先补代（日志 `已临时恢复 13 处类型的 pub` → `make seed`，中间代种子
  `b123acbe…`），再跑**完整主门**——候选两代固定点、cc4 自解析 71 文件、反例 42/42、
  运行语料 293/293、并发项目扫描 8/8、前端快照复用、自有运行时、`yh check`、modules、
  项目验收（含裸 `struct` 的 privtype/modstate fixture）全绿，最后把 `bin/yh` +
  `bin/yh.sha256` 作为 `darwin-arm64-seed` artifact 上传。
- **入库**：提交该 artifact（Mach-O 64-bit arm64，与本地工作树的 `bin/yh` 逐字节相同）：
  `bin/yh` `2e150732…` → **`b123acbe…`**（2,358,688 B），`bin/yh.sha256` 同步。这份种子已被
  macOS 主门验证能编译含裸 `struct` 的当前源码，因此**下一步 release/CI 的 darwin 作业会
  直接跳过补代步骤**（该步骤保留为保险，不删）。
- **CI 超时实测**：`a19ffb0` push 触发的 `linux-arm64` 作业（QEMU 全模拟的 arm64 容器里跑
  `make` + 两层语料 + `make selfhost-native`）**6.4 分钟**，`timeout-minutes: 60` 充裕，
  todo 里「CI 超时上限未实测」随之关闭。
- **判据提醒**：作业日志里 `make verify-seed` 在补代前后分别打印 `2e150732…`（检出里的旧
  种子）与 `b123acbe…`（补代产物），这是「补代确实换了种子」的直接证据；也说明**用二进制
  字符串判断门禁不可靠**——`必须带`/`字段一律公开` 在当前源码里仍有同名诊断与注释。

## 2026-10-13 yh 0.0.4：版本号提升与发布流程种子补代

- **版本**：`compiler/project.toml` `0.0.3` → `0.0.4`，`compiler/README.md` 的版本记录与
  `tools/compiler-performance.py` 的 `yh version` 断言同步。版本号只在运行时从
  `project.toml` 读取（`version` 子命令），**不编进二进制**——变更后重编的 `yh`
  SHA-256 与变更前逐字节相同（`33733767…`）。
- **发布流程补代**：`.github/workflows/release.yml` 的 `darwin-arm64` 作业补上与 `ci.yml`
  同款的「必要时补一代 macOS 种子」（探测裸 `struct` → 临时恢复 13 处 `pub` → `make` →
  `make seed` → `git checkout -- compiler` → 继续构建 HEAD）。不补的话：入库 `bin/yh` 仍是
  2026-10-08 一代、带「`struct/union/enum` 必须带 pub」门禁，编不了当前源码（12 个模块私有
  类型），tag push 后 darwin 作业必失败、`release` 作业（needs 两个作业）不跑，0.0.4 不会
  有 Release 产物；linux 作业不受影响（0.0.3 的 Release 里有 `yh-0.0.3-linux-arm64.tar.gz`
  作种子，已用只读 API 核实）。
- **本地干跑**（macOS 无法本地执行）：YAML 解析通过、抽出的 run 体（50 行）`bash -n` 通过、
  打桩环境（旧种子探针 exit 1）下补代 **13/13 命中**且退出码 0；探针成功时该步骤自动跳过。
- **验证**：`make` / `make test`（语法 78/78、反例 42/42、运行 293/293）/
  `make selfhost-native` 全绿；在 `compiler/` 目录下 `../yh version` 输出 `yh 0.0.4`。
- **首发 Release（run 38410260504）**：darwin 作业**成功**且补代真的执行了（日志
  `已临时恢复 13 处类型的 pub` → `make seed` → 冒烟 `hello, yh!`），证明这段补代是出
  macOS 产物的前提；linux 作业失败在容器构建步骤——容器只装了 `build-essential` 没有
  python3（`make: *** [Makefile:78: verify-seed] Error 127`，该依赖是 0.0.3 之后 Makefile
  才引入的），且它下载的 0.0.3 Release 种子早于 arm64 `O_DIRECTORY` 修复、本身带 bug。
  修复：容器安装 `build-essential python3`，去掉「下载上一版 Release 资产」整步，改用
  入库 `bin/yh-linux-arm64`（与 `ci.yml` 的容器配方一致）。
- **tag**：`0.0.4`（annotated，指向本轮修复后的提交），push 触发 `Release` 作业
  （linux + darwin 构建、归档 tar.gz + sha256）。详情见
  [完成记录](01-finished/yh-0.0.4发布-2026-10-13.md)。

## 2026-10-13 yh_link：静态 ELF 链接器 TC4 主体完成（Linux/AArch64）

- **本轮定位**：只做 `link/`（yh_link）与它的门禁/文档，**不接入编译器**、
  **不与 `asm/` 建立代码依赖**（用户决定：link 与 asm 解耦合，稳定后再接入）。
  编译器源码零改动；`Makefile` 只新增两个不接入主流程的目标。
- **交付**：`link/` 成为可用的静态 ELF 链接器——读入 `ELF64 ET_REL`（AArch64）
  对象、合并节、跨对象解析符号、应用 12 种重定位（含 GOT 类）、产出可装载并
  真跑的静态 `ET_EXEC`。命令形态
  `yh_link link [-o out] [--entry SYM] [--max-page-size N] [--verbose] in1.o ...`，
  退出码 0/1/2 分级；无参数调用 = 自检。设计见
  [设计文档](03-design/yh-link静态ELF链接器设计.md)，任务分解与验证记录见
  [实施方案](02-plan/yh-link静态ELF链接器实施方案.md)。
- **关键实现决定**：链接器的**全部地址计算不依赖 `%`、`&`、`*`**——种子编译器
  这三类运算在大立即数上实测错值（`0x510000 % 0x10000` 得 0、
  `0x90000001 & 0x9f000000` 得 0、`81 * 65536` 偶发差 4096）。改用「除以再乘回」
  的取位原语、累加式缩放与纯算术的指令形态判据，代价换"算出来的地址是对的"。
- **实施中修掉的 10 个缺陷**（每个都配了自检或门的回归，改回去立刻变红）：
  - 符号定址漏了"输入节在输出节内的偏移"，跨对象 `bl` 跳到自己（死循环）；
  - 全局符号表槽位算出负数（u32 哈希按补码落 int 后取余）导致越界段错误；
  - `e_shstrndx` 与 `.symtab.sh_link` 用固定常量，`.got` 缺席时错位
    （`readelf` 报 corrupt string table index、符号名乱码）；
  - 段起始未页对齐，同余条件满足却在 qemu 下一访存就段错误；
  - `ADR_PREL_PG_HI21` 的指令形态校验依赖 `&`（错值导致误报"不是 adrp"）；
  - 分支位移为负时"对齐"判定走 `%` 的向零取整，合法位移被误判未对齐；
  - 诊断消息拼在公用缓冲里导致诊断自己覆盖自己；
  - 某条失败路径不带诊断，只留一个退出码 1（现在会补带阶段名的内部错误）；
  - 输入文件读不进来被判成用法错误（2），改为输入失败（1）；
  - 映射符号 `$x`/`$d` 被当成普通局部符号参与解析（跨对象地址算错的根因）。
- **验收门**（三层，全部机器可判定）：
  - 自检（`yh_link` 无参数）**57 项 / 失败 0**，四组：算子原语与实测错值量级、
    读取层拒绝路径、单对象端到端、多对象合并；
  - 端到端 `link/tests/link_accept.py` **7/7**：汇编 → 链接 → 结构断言
    （ET_EXEC/AArch64/3 个 PT_LOAD/段页对齐且同余/RW 不可执行/节名与
    `e_shstrndx`、`sh_link` 正确）→ **真跑比对退出码** + 两次链接逐字节相同；
  - 差分 `link/tests/link_diff_regress.py` **7/7** 与
    `aarch64-linux-gnu-ld -static -nostdlib`（binutils 2.46）一致：退出码相同、
    同为静态 `ET_EXEC`、**同一输出节内符号间距相同**（与布局无关的不变量）。
  - 语料覆盖：跨对象 `CALL26`、跨对象 `adrp/add` 取数据、非零页差 `ADRP`、
    跨 64 KiB 长距离调用、`.xword` 绝对地址回填 + `blr` 可用、跨段访存、
    节内偏移非 0 的标签。
- **零回归**：`make`、`make test`、`make selfhost-native` 全绿（本轮未改
  `compiler/` 任何文件）。
- **刻意不做**：产物**只在 `link/.build/`**，不复制到仓库根——编译器当前按
  `yh_link` 这个名字发现**汇编器**（`compiler/cmd/link_cache.yh` 的
  `mb_asm_tool` 会调用 `yh_link asm -t ... -o ...`），真链接器占用该名字会直接
  破坏现有 `make`。集成顺序必须先改编译器的工具查找名，见实施方案 §6。
- **未做/边界**：arm64 **原生**验证（本机是 Windows + WSL x86_64，产物经
  qemu-user/binfmt **模拟执行**）；长调用跳板（分支超 ±128 MiB 直接报错）；
  Mach-O 目标（TC9/TC10，`-t darwin` 显式报错）；TLS/弱符号/COMMON/可见性/
  链接脚本/归档库/动态链接/PIE（遇到即报诊断）；映射符号不进输出符号表。
  待办已记入 [docs/todo.md](todo.md)。

## 2026-10-13 yh：arm64 目录扫描常量、CI 首跑两处阻塞与 64 位计时截断

- **背景**：`1a8b4fa` push 后 CI 的 `linux-arm64` 作业**首次真实运行**，2m13s 在容器内
  `make` 首步失败：`yh: 无法打开目录: .`。三条缺陷都是「本地环境够宽容就看不见」型。
- **① arm64 `O_DIRECTORY` 常量错**：`compiler/cmd/project_dir.linux.yh` 的 openat flags
  写的是 x86_64 的 `0x10000`，而 arm64 上 `O_DIRECTORY=0o40000(0x4000)`、`0x10000` 是
  `O_DIRECT`——于是实际在「用 O_DIRECT 打开目录」，tmpfs/ext4/overlayfs 一律 `EINVAL`，
  只有 9p（WSL 的 `/mnt/c`，本仓库所在处）不校验该标志、放行，本地因此全绿。改成
  `0x4000`，并把 arm64/x86_64 取值错位写进注释（这个判据在 9p 上完全看不出来）。
- **② `runtime-memory.py` 硬编码 `/usr/bin/clang`**：CI 容器只装 `build-essential python3`，
  没有 clang，而 `run()` 不捕获 `FileNotFoundError`——修完 ① 后必然在
  `make selfhost-native` 这一步爆。改为按宿主架构选汇编器：aarch64 宿主（CI 的 arm64
  容器）用系统 gcc 原生汇编；x86_64 宿主仍取系统 clang + `-target aarch64-linux-gnu`；
  都没有时给明确 FAIL 而不是 traceback。
- **③ 统计计时 32 位截断**：yh 的 `int` 是 32 位（`TK_INT → TY_I32`），`gen.append_int`
  的实参就是 `int`，纳秒计时超过 2.147 s 即翻负（实证
  `2292776097 - 2^32 = -2002191199`，恰好等于四次阶段耗时之和 + 3.18 ms 开销），
  `lex-stats.py` 的 `TIMING_RE` 因负号匹配不到父进程那行。新增 `gen.append_i64`，
  `cmd/module_build.yh` 的五个计时字段改走它，门里把「负计时」单独报成截断诊断。
- **新增回归门**：`tests/selfhost/foreign-fs-build.py`——把 fixture 复制到**系统临时目录**
  （另一个文件系统：Linux tmpfs/ext4、容器 overlayfs）冷编 + 运行并核对退出码，日志里
  打印该目录的文件系统类型；接入 `make selfhost-native`。旧编译器上必失败
  （`/tmp` 实测 `无法打开目录: src`），修复后通过。
- **验证**：`make test` 语法正例 78/78、反例 42/42、运行语料 293/293；`make selfhost-native`
  全绿（含新增门）；慢构建实证（编译器自编 9.17 s）`time_total_ns=9173060069`；
  修复后的编译器与新种子都能在 `/tmp`（tmpfs）上冷编整个 `compiler/` 项目
  （等价于 CI 容器 overlayfs 场景）。
- **滚种子**：`bin/yh-linux-arm64` `970cf4ff…` → **`33733767…`**（滚完用新种子复跑主门
  全绿；新种子在 `/tmp`（tmpfs）上冷编 `compiler/` 项目 `rc=0`，等价 CI 容器条件）。
- **未做/边界**：`darwin-arm64` 作业仍未真实跑过（只在 `workflow_dispatch` 触发；macOS
  目录枚举走 `getattrlistbulk`，不涉及这组标志）；CI 的 60 分钟上限仍未实测；
  `asm/`、`link/` 两个项目的改动按用户要求仍不提交。详情见
  [完成记录](01-finished/yh-Linux目录扫描arm64常量与CI首跑修复-2026-10-13.md)。

## 2026-10-12 yh_asm 汇编器稳定化（ASM-0–ASM-8：断电、GNU 方言、门禁可移植、拒绝层、影子验收）

- **本轮定位**：只做 `asm/`（yh_asm）与它的门禁/文档，**不接入编译器**；
  接入（查找名切到 `yh_asm`/`YH_ASM`、默认切换、安装布局）留到判据 S1–S7
  通过后另立。方案见
  [yh-asm 汇编器稳定化实施方案](02-plan/yh-asm汇编器稳定化实施方案.md)，
  工作记录见
  [完成记录](01-finished/yh-asm稳定化-2026-10-12.md)。
- **ASM-0 断电**：删 `Makefile` 的 `yh-link` 过渡目标与 `YH_LINK` 变量，
  `git rm` 根目录入库的同一份 Mach-O 副本 `yh_asm`/`yh_link`
  （sha256 `3675076a…`）并进 `.gitignore`；编译器 `mb_asm_tool` 查不到
  `yh_link` 就回落系统 cc，WSL 上不再需要 `YH_LINK=/nonexistent` 绕过。
  断电后主门复验全绿：`make` rc=0、`make test` rc=0（run 153/153、
  fail 132/132、pass 8/8）、`make selfhost-native` rc=0（模块固定点
  cc3→cc4 24 个产物一致、语法反例 42/42、modules 18/18、build-check 93/93）。
- **ASM-1 GNU 方言**：`-t linux` 接受编译器 Linux 目标的实际发射
  （`adrp Xd, sym` 裸符号、`add`/访存的 `:lo12:sym`），Darwin 目标仍要求
  `@PAGE`。修前编译器 **8 个模块一条都汇编不了**（首错 `adrp` 需要
  `sym@PAGE`）；修后 **8/8 原文汇编成功**（8.98 MB、1974 条 `adrp` 的模块
  也不在话下），与 clang 对象**逐节内容 + 逐重定位 0 不一致 0 跳过**。
- **ASM-2 语料盘点**：新增 `tools/yh-toolchain-inventory.py`，重建
  `tmp/inv`（单文件 161 + 编译器模块 8 = 169 个 `.s`）、统计 69 个助记符与
  2 个伪指令，查出契约漏列 `uxtw`（95 次）并补入契约 v2。
- **ASM-3/ASM-4 门禁可移植**：oracle 解析改为
  `LLVM_MC` → Homebrew 默认 → **clang 集成汇编器**（并校验是真 clang，
  避开交叉工具链包装），WSL 上 134 条编码差分 0 不一致；新增
  `tests/elf_link_native.py`（交叉 `aarch64-linux-gnu-ld` + `qemu-aarch64`，
  不需要 docker）与 `tests/elf/start-linux.s`、`tests/elf/yhr-linux.s`
  （运行时符号桩：`read/write/open/close/_Exit/abs/strtoul`）：169 个程序语料
  **159 行为一致 / 0 不一致 / 10 跳过**（补桩前 152/0/17；跳过全部有名单与
  原因：8 个编译器模块缺入口与跨模块运行时符号、2 个与寄存器同名的符号
  语料两边都拒绝）。
- **ASM-5 拒绝层**：内建第 4、5 层自检（GNU 方言端到端 + 拒绝层 25 条，
  每条负例配正向对照），新增 `tests/asm-neg/` 与 `tests/check_neg.py`
  （断言退出码 1、`<path>:<line>:<col>: 错误:` 形态与类别关键字）。顺带修掉
  四个既有缺陷：`.balign` 非 2 的幂只有退出码没有诊断；分支目标带符号修饰符
  被静默编成 `b #0`；未定义的 `.L` 符号被降级成未定义全局符号；未闭合块注释
  报成「无法识别的语句开头」且列号为负。
- **ASM-6/ASM-7/ASM-8**：退出码归一为 0/1/2（此前输入错误退 255）；
  交叉目标（Linux 宿主 `-t darwin`）写对象修复（open 旗标按宿主取，此前按
  目标取，Linux 上 0x601 没有 O_CREAT 直接失败）；影子验收
  `tests/shadow-build.py` 用显式 `YH_LINK` 冷编编译器两代，
  **16 次汇编调用、固定点 16 个产物 0 不一致**；Darwin 输出改由
  `tests/darwin-snapshot.txt` 字节快照守住（9 个文件）。
- **性能如实记录**：同一批编译器模块语料（8.98 MB）clang 5.52 s、
  yh_asm 41.18 s（≈7.5×）；WSL 上 yh_asm 是 aarch64 ELF 走 qemu 模拟，
  自建 CPU 基准实测模拟因子 2.2–3.0×，折算原生 arm64 约 2.5–3.5×。
  本轮**不做热路径优化**，接入决策前需要原生数据。
- **未做/边界**：长条件分支单调放宽（`b.cond`/`cbz` ±256 KB，编译器最大
  模块 `.text` 已 413 KB 但未出现越界条件分支）；`.size` 的符号表达式
  （契约按实测收窄）；GOT 窄访问；与寄存器同名的符号（编译器发射缺陷，
  两边都汇编不了）；macOS 原生 macho 两门本轮未跑（无 macOS 环境），
  只由快照守不回退。

## 2026-10-12 CI：双平台自举门禁工作流（Linux 容器 + macOS 原生，含 macOS 种子自动补代）

- **背景**：macOS 侧此前只在发布 tag 上由 `release.yml` 跑 `make` + 冒烟，没有跑门禁；
  且入库 `bin/yh` 因「类型必须带 pub」门禁被删除而编不了当前源码，需要跨代恢复。
- **新增** `.github/workflows/ci.yml`：
  - 触发：`workflow_dispatch`（可选只跑某一平台，省 macOS 计费分钟）或推送 `arm64`/`main`；
  - `linux-arm64`：`docker run --platform linux/arm64 ubuntu:24.04`，容器内 `make` + 第 2/3 层
    语料 + `make selfhost-native`（第 1 层 ANTLR 需 Java 与 jar 缓存，不在 CI 跑）；
  - `darwin-arm64`：`macos-14`（Apple Silicon）上先探测入库种子是否支持模块私有类型，
    落后则把 13 处类型临时恢复 `pub` → `make` → `make seed` → `git checkout -- compiler`，
    再 `make` + 冒烟 + `make selfhost-native`，最后校验并上传 `bin/yh`、`bin/yh.sha256`。
    种子追平后该步骤自动跳过（探测即 `bin/yh --syntax-check` 一个裸 struct），可整段删除。
- **本地验证**（macOS 无法本地执行，故用 Linux 种子等价干跑同一套逻辑）：YAML 解析、
  各 `run` 脚本 `bash -n`、内嵌 Python 语法均通过；干跑链路——执行 ci.yml 内嵌的恢复脚本
  （13 处命中，裸类型 0）→ 旧种子 `make` → `make seed`（新种子接受裸 struct）→ 还原 13 处
  （等价 `git checkout -- compiler`）→ `make` → `make selfhost-native` **全绿**（固定点 24 产物、
  自解析 71 文件、运行语料 293/293、modules 18/18、项目验收 93/93）→ 还原种子与工作树。
- **注意**：`yh`/`yh_asm`/`yh_link` 是 gitignore 的本地产物，检出里不存在，因此 CI 的汇编/链接
  自然回落系统工具链（Linux 容器内 gcc、macOS 上 clang），不需要 `YH_LINK` 兜底（该兜底只对
  本地工作树有意义，见 AGENTS.md 的 WSL 命令）。
- **未做**：尚未 push 到 GitHub、也没有真实跑过 macOS 作业（本地无 macOS）；该作业跑通后，
  把 artifact 里的 `bin/yh` + `bin/yh.sha256` 提交回仓库即完成 macOS 种子追平。

## 2026-10-12 yh：模块私有类型（struct/union/enum 的 pub 转可选，接口 39,990 → 36,633 字节）

- **背景**：用户要求把不带 `pub` 的 `struct`/`union`/`enum` 标识为模块私有类型，
  并选定「私有类型不得以任何形式（含指针）出现在 pub API」。规划交付[设计](../03-design/yh-模块私有类型设计.md)、
  [实施方案](../02-plan/yh-模块私有类型实施方案.md)与 [ADR-0013](../adr/0013-yh模块私有类型.md)
  （修订 2026-10-02「类型必须带 pub」，保留字段一律公开与禁止嵌套）。
- **语法**：`docs/yh.g4` 的 `attributedDecl` 类型分支改 `'pub'?`、`plainDeclBody`
  增 struct/union/enum（三处注释同步）；无歧义论证：`topLevelDecl` 三个分支首 token
  集合互不相交（`pub` / `@` / 其余关键字）。
- **前端**：删 `parse/parse_decl.yh` 两处「必须带 pub」门禁；接口按 `is_pub` 过滤、
  enum 成员 `F_PUB`、pub 声明引用非 pub 类型的诊断、CT 私有类型诊断等机制原样复用。
- **语料**：删 `rejected/{30_bare_struct,31_bare_union,34_bare_enum}.yh`（转正）；新增
  `tests/yh/03-decl/10_private_types.yh`、`11_private_extern_type.yh`、
  `tests/yh-run/run/175-private-types.yh`、`tests/modules/accept/08-private-type.yh`
  与新 fixture `tests/modules/projects/privtype/`（lib/host/host2/host3 + badpub/badfield/
  badalias/badptr），build-check 增 7 条用例。
- **编译器自身（P4）**：12 个类型去 `pub`（ast 5、cmd 4、comptime 2、parse 1；13 处
  含平台文件两份），接口 `.s.i` 39,990 → **36,633** 字节（−8.4%，自 63,160 起累计 −42%）；
  编译器二进制与上一代逐字节相同——类型可见性只影响接口产物。
- **验证**：`make` 两代各一次冷编通过；`make test` 语法正例 **78/78**、反例 **42/42**、
  运行语料 **293/293**；`make selfhost-native` 固定点 24 产物一致、自解析 71 源文件、
  固定点探针、CLI 冒烟、modules **18/18**、项目验收 **93/93**。
- **滚种子**：`bin/yh-linux-arm64` `a4c66d5b…` → **`970cf4ff…`**（语言规则一代；
  类型私有化一代二进制不变），两代后均复跑主门全绿。
- **文档**：00-语义边界、Go 风格模块设计 §5.3（标注不透明导出类型暂不支持）、
  模块与项目管理设计、CONTEXT.md（新增术语）、`compiler/README.md`、`AGENTS.md`、
  todo（立项条目随完成移除）与本条。
- **过程发现**：`tests/yh-run` 是单文件模式、不发射接口，故模块级语义负例只能放
  `tests/modules/projects`；负例函数名不能撞 prelude 名（`open` 会先报顶层符号重定义）。

## 2026-10-12 yh：模块导出面收缩（`pub` 1048 → 585，接口 −36.7%、`.globl` −57%）

- **背景**：用户要求分析各模块导出范围并收紧，理想形态是「每模块一个结构体 +
  一个函数导出」。原口径是成模时 pub 从宽：1048 处 `pub`，其中 461 处 fn/const
  无人跨模块引用。`pub` 在本编译器同时决定 `.s.i` 接口导出与 `.globl`
  （`gen/emit_arm64.yh` 的 `em_prologue`/数据/`bss`）。
- **收缩**：463 处 `pub` 移除（55 个文件），只针对 `fn`/`const`——lex 16、
  backend 1、main 116、parse 119、ast 9、ir 12、comptime 81、gen 107；
  同名跨平台文件（`clock.darwin|linux`、`project_dir.darwin|linux`）两处一起改写。
  保留：入口 `cmd` 的 `main`（CRT 调用需 `.globl`）；`struct`/`union`/`enum` 按
  2026-10-02「pub 一等化」必须带 pub，语言层面无法私有化；`let` 本就不导出。
- **效果**：导出项 1048 → 585、`pub fn` 747 → 302；接口 `.s.i` 合计
  63,160 → 39,990 字节（−36.7%，lex 681→69、main 6501→721、parse 7027→1190、
  comptime 12621→7524）；模块汇编 `.globl` 776 → 333（−57%）。收缩后
  `lex`/`backend` 已「≤1 函数、0 结构体」，`main` 只剩入口函数。
- **无语言/行为改动**：只删关键字，不引入新用例（既有 292 条运行语料与 86 个
  项目用例即回归门），`ir` 的对外 API 收缩由 `irverify`/`irfront` 依赖用例覆盖。
- **验证**（WSL2 Ubuntu x86_64 + qemu-user/binfmt，`SEED=bin/yh-linux-arm64`、
  `YH_LINK=/nonexistent`）：`make` 冷编一次通过；`make test` 语法正例 76/76、
  反例 45/45、运行语料 **292/292**；`make selfhost-native` 模块固定点 cc3→cc4
  **24 个产物逐字节一致**、cc4 自解析 71 个源文件、并发项目扫描 8/8、前端快照
  复用、自有运行时、`yh check`、modules **17/17**、项目验收 **86/86**。
- **滚种子**：`bin/yh-linux-arm64` `3eeae704…` → `a4c66d5b…`，用新种子复跑
  `make selfhost-native` 仍全绿。
- **文档**：新增[设计](../03-design/yh-编译器模块导出面收缩设计.md)与
  [完成报告](01-finished/yh-编译器导出面收缩-2026-10-12.md)；同步 `compiler/README.md`、
  `AGENTS.md` 与 `docs/todo.md`（原「接口 pub 收缩」条目换成待决策的
  「模块私有类型」）。

## 2026-10-12 yh：AST 阶段拆成独立 `compiler/ast/` 模块（解析与 AST 编译单元分离）

- **背景**：用户决定「开发主要集中在 Linux 平台，其他平台后接入」，并要求优化编译流程、
  把 AST 过程单独提到 `ast` 目录。此前 `compiler/parse/` 同时装语法分析器与 AST 阶段
  （`ast_*.yh` 11 文件），共用一个编译单元：`yh-parse.s` 3.31 MB 为最大单元。
- **改动**：11 个 `ast_*.yh` 迁入 `compiler/ast/` 并改 `module ast;`；parse/cmd 侧 80 处
  `ast_*` 调用、50 处 `AST_*` 常量加 `ast.` 限定；`is_assign_op` 自 `parse_type.yh` 迁入
  `gen/buffer.yh` 解环；AST arena 的 7 个跨模块状态 + 语句 `first_child` 字段改为 12 个
  `pub fn` 访问函数（`let` 不导出），调用点约 33 处；8 个文件补 `import ast;`。
- **产物**（同一编译器、同一源码仅差拆分）：`yh-parse.s` 3,310,028 → 2,174,107 字节
  （−34.3%），新增 `yh-ast.s` 1,132,669 字节；`gen`/`main` 因 `is_assign_op` 与限定调用
  微增；`lex`/`ir`/`backend`/`comptime` 的 `.s` 与 `.s.i` 与拆分前**逐字节一致**。
  模块数 7→8，固定点产物 21→24。
- **用例**：新增 `tests/modules/projects/modstate/`（私有 `let` arena + pub 访问函数），
  `build-check.py` 增 `u3-private-let-accessor`（run，退出码 7）与
  `u3-private-let-access`（fail，诊断「模块没有导出该名字」）。
- **验证**（WSL2 Ubuntu x86_64 + qemu-user/binfmt，`SEED=bin/yh-linux-arm64`、
  `YH_LINK=/nonexistent`、`PATH` 前置 `tmp/boot/crossbin`）：`make` 冷编通过（8 模块）；
  `make test` 语法正例 76/76、反例 45/45（ANTLR 与编译器模式）、运行语料 **292/292**；
  `make selfhost-native` 模块固定点 cc3→cc4 **24 个产物逐字节一致**、cc4 自解析 71 个
  源文件、固定点探针、CLI 冒烟、并发项目扫描 8/8、前端快照复用、自有运行时、`yh check`、
  modules **17/17**、项目验收 **86/86**（含本轮新增 2 例）全绿。
- **滚种子**：`SEED=bin/yh-linux-arm64 SEED_DEST=bin/yh-linux-arm64 make seed`；
  `bin/yh-linux-arm64` 哈希 `137c5fdb…76f2c` → `3eeae704…9aebe`，并用新种子复跑
  `make selfhost-native` 仍全绿。
- **文档**：新增[设计](03-design/yh-编译器ast模块拆分设计.md)与
  [完成报告](01-finished/yh-编译器ast模块拆分-2026-10-12.md)；同步 `compiler/README.md`、
  `README`、`AGENTS.md`（含 WSL 验证命令）与 `docs/todo.md`（Linux 平台优先）。

## 2026-10-11 yh：WSL/Linux 全量门禁修复（build-check 84/84、make test/selfhost-native 全绿）

- **背景**：Linux 种子入库（2026-10-09）后，WSL 上 `make test` /
  `make selfhost-native` 仍有三处卡点（ANTLR 环境缺失、runtime-memory.py
  的 Darwin 断言、build-check 7 项既有缺口）。本轮全部修复：
- **编译器缺陷**：
  - **宿主文件操作按宿主平台取值**：新增 `gen.tg_host_darwin()`（进程运行
    平台探测），`driver/module_build/iface/iface_ct/ast_ir_cache` 的 open
    旗标从「目标方言 tg_darwin」改为宿主——交叉目标（`-target darwin`）
    不再把 Darwin 的 O_CREAT 位值 0x601 发给 Linux 内核（strace 实证：
    Linux 上 0x601 = O_APPEND|O_TRUNC|O_WRONLY、无 O_CREAT → 写接口
    ENOENT），修复 r3-capture-uses-host-file-flags / r3-cross-target-
    source-selection / r3-linux-syscall-is-target-gated /
    r3-getattrlistbulk-darwin-available 四例；
  - **窄整型返回宽度归一**：`sem_call`（yh ABI 调用点）对窄整型返回补
    sbfx/ubfx（与 sem_cabi_call 同一约定）——extern/prelude 实现只保证
    w0 有效，64 位比较/压栈此前读到垃圾高位（反汇编对比 add2〔内部〕
    与 dup2〔glibc〕后定位；`dup2(-1,1) == -1` 恒假、保存局部后正确），
    修复 r3-dup2-os-api；
  - **模块链接追加 -lm**（Linux 宿主；glibc 数学库分离，libs/math 的
    cos/pow 链接失败；Darwin libSystem 已含——按宿主取）；
  - **prelude clock_gettime 公共登记**（原仅 Darwin 目标；libs/time 引用，
    Linux 经 glibc 解析）——修复 s2-libs-core-modules 编译段。
- **测试脚本/语料平台适配**：
  - `runtime-memory.py` 宿主感知：Darwin 断言按 sys.platform 分支，
    Linux/ELF 检查起动辅助符号白名单（gmon_start__/libc_start_main/
    ITM_* 及版本化 GLIBC 符号），交叉组装显式 `/usr/bin/clang`；
  - `build-check.py` 对 Windows 检出（core.autocrlf）规范化 CRLF 后再
    字节匹配与源改写（r2c-ir-cache-fixture / r2c-function-ir-cache-hit
    先前因工作树 CRLF 导致源改写改变缓存键、全量失效）；
  - `libsbase` fixture 的文件创建标志按 CT0 目标常量平台化（0x241 /
    0x601）。
- **WSL 环境**（apt/pip，不入库）：`antlr4`（4.9.2）+ `libantlr4-runtime-
  java` + `libantlr3-runtime-java` + `python3-antlr4` + `antlr4-python3-
  runtime==4.9.2`（pip）；`/usr/local/bin/antlr4` 兼容 wrapper（吞掉
  `-v` 并加载全部依赖 jar）。本机 `make test` 第 1 层（ANTLR 参考语法）
  通过（76/76 + 45/45）。
- **验证**（WSL2 x86_64 + qemu-user/binfmt，`SEED=bin/yh-linux-arm64 make`）：
  `make test` 全绿（ANTLR + 编译器语法 + 运行 292/292）；`make
  selfhost-native` 全绿（native-selfhost 全过、scratch-isolation 8/8、
  lex-stats、runtime-memory、**build-check project cases 84/84**）。
- **提交**：`863c8b0`（12 files，+98/−31）。todo「Linux 平台缺口」区
  的 build-check 条目移除，yh_link 方言与 ANTLR 条目保留并注明现状。

## 2026-10-09 yh：Linux/aarch64 自举种子入库（`bin/yh-linux-arm64`）

- **入库**：WSL 重建链的最终种子 `tmp/boot/chain/yh-19e2e3a` 以
  `bin/yh-linux-arm64` 正式入库（ELF 64-bit ARM aarch64，SHA-256
  `137c5fdb…76f2c`），并写 `bin/yh-linux-arm64.sha256`
  （`selfhost_snapshot_gate --verify-seed` 通过）。Makefile 在
  Linux/arm64 宿主自动选择它；**x86_64 Linux 宿主须显式
  `SEED=bin/yh-linux-arm64`**（x64 后端未实施，`make` 缺省会找
  `bin/yh-linux-x64`）。
- **验证**（WSL，x86_64 + qemu-user/binfmt，`YH_LINK=/nonexistent` 回落 gcc）：
  - 入库种子冷编产物与入库前构建**逐字节一致**；
  - `SEED=bin/yh-linux-arm64 make`：通过；
  - tests/yh-run **292/292**、语法门（编译器模式）正例 **76/76**、反例 **45/45**；
  - `SEED=bin/yh-linux-arm64 make selfhost-native`：native-selfhost 全过
    （固定点 21 产物一致、自解析 71 文件、CLI 冒烟、运行语料 292/292）、
    scratch-isolation 8/8、lex-stats 通过；末尾 `runtime-memory.py` 的
    **Darwin 可执行文件 OS API 核对**在 Linux 上按 ELF 产物（GLIBC 符号）
    判失败——**既有 Linux 平台缺口**（todo「yh_link ELF64 方言」条目已列，
    非本轮引入）；
  - `SEED=bin/yh-linux-arm64 make test`：仅在 **ANTLR 参考语法门**失败
    （WSL 无 Java/antlr4 jar）——**既有缺口**（todo「本机 ANTLR 参考语法门
    需要 Java + antlr4 工具 jar」，macOS 上已放 jar 通过）。
- **文档**：AGENTS.md 更新为双种子说明（开发策略/目录/编译流程/Linux 环境
  章节）；todo 多平台后端区移除「Linux 版待发布归档」表述；WSL 种子链记录
  追加「入库」小节。
- **后续**：macOS 上照旧运行/滚动 Darwin 种子 `bin/yh`；Linux CI 可按需
  用 `bin/yh-linux-arm64` 重建。

## 2026-10-09 yh 编译期：`$` 调用 pub 聚合常量跨模块导出交付 + 编译期过程全部任务完成

- **`$` 调用初始化的 pub 聚合常量跨模块导出**（原 todo 最后一项「小项，暂挂起」）：
  - 解析期守卫放开；提供方在求值后记录初始化式源文本（新 `const_expr_kind = 5`）
    并登记**同模块** `$fn` 调用目标为**闭包附加可达种子**
    （`ct_registry.ct_pub_agg_fn_*`），`mk` 正文随 `.s.ct` 传递；
  - `.s.i` 导出重放调用文本，其中 `$fn` 重写为闭包隐藏名
    （`iface_emit_pub_agg_src`，与闭包正文重写同一约定；`.s.ct` 闭包常量
    重放同步支持 kind 5）；
  - 导入侧**延迟执行**：`.s.i` 先于 `.s.ct` 加载，接口加载阶段只登记
    （`PubAggDeferred`：符号 + 初始化式 token 起点 + 接口路径）并跳过
    token，`.s.ct` 闭包加载完成后由 `module_worker` 调
    `pub_agg_deferred_run()` 重新读源、求值、建模并物化本单元副本；
  - 边界：`$mod.f(...)` 形态的导出重写首版不覆盖（解析期明确诊断）。
- **编译期过程剩余条目收尾**（正式撤销，历史见 01-finished/）：
  - **CT1/CT2 typed AST 收尾**：模板实例化首片已实现并验收（`2026-10-05`），
    两个子项（去重解析、统一入口）已于 2026-10-07 实测撤销，无剩余任务；
  - **CT3 完整 typed 执行器**：2026-10-07 覆盖审计确认表达式/语句种类全支持，
    本轮 CT6 又补齐 `$if` 表达式（kind 14）、字段元信息展开、`$field`
    按下标读取（kind 15）与类型谓词常量折叠；「其他聚合值与一般左值」多轮
    探针（含本轮 CT6 用例矩阵）未发现具体缺口，撤销；
  - **CT5A**：布局请求、依赖调度、长度表达式与混合环诊断均已交付；
    「其他一般 typed CT 请求」多轮探针未发现具体缺口，撤销。
  - **CT6 三项**：表达式选择、类型分派谓词、字段元信息与 `$field`
    已于同日交付（见下方三条记录）；条件导入按用户决议不做。
  **至此编译期过程（CT0–CT6）全部任务完成**，todo 的「编译期过程」区已清空移除。
- **用例**：comptimecross 增 `CT_TBL`（私有 `mk_ct_tbl()` + `pub const
  CT_TBL [3]int = $mk_ct_tbl();`；消费者正文读 31、提供方正文读 16、运行期
  读 0 断言）；新增 run/174（单文件 `$` 初始化聚合常量的编译期/运行期读）。
- **验证**（WSL+qemu，临时种子）：tests/yh-run **292/292**（run 152/152、
  fail 132/132、pass 8/8）；语法门正例 76/76、反例 45/45；modules 门 77/84
  （与基线一致，comptimecross 用例通过）；**native-selfhost 主门全部通过**
  （模块固定点 21 产物一致、cc4 自解析 71 文件、CLI 冒烟、运行语料 292/292）。
- **记录**：[完成记录](01-finished/yh-编译期pub调用聚合常量跨模块导出-2026-10-09.md)。

## 2026-10-09 yh 编译期：CT6 P1b/P1c 字段元信息与按名取字段交付（CT6 完成）

- **P1b `$for f in T.fields` 字段元信息**：
  - 无需改 g4（`IDENT '.' IDENT` 形态已覆盖，按 `.` 后固定名分派 values/fields）；
  - 新 `F_FIELD_META` 绑定：offset = 字段下标、type_id = **字段类型**（可直接作
    `$is_type(f,T)`/`$is_int(f)` 静态类型引用）、cval = 宿主类型（`.name` 投影）；
  - `parse_comptime_field_for` 按声明顺序展开，typed 逐字段块（wrapper op=0）
    与普通逐轮发码，与 `E.values` 同构；`sem_field_meta_name` 投影字段名常量；
    裸用拒绝，谓词实参经新 `c_ct_meta_bare` 计数放行。
- **P1c `$field(x, "name")` 按名取字段（只读）**：
  - 无需改 g4（走既有 callArgs）；基底走 `sem_member` 同一路径（指针自动解引用）；
    字符串名按字段表解析出**字段下标**；
  - typed 捕获 `AST_EXPR_CTFIELD = 15`（op 槽存下标，sym_* 槽受 AST 校验约束）；
    `ct_ir_member_place` 按 op 下标定位（跳过源码 token 名匹配）；
  - **只读**：`ct_ir_lvalue` 不识别 kind 15，赋值自然被拒。
- **用例**：run/172、run/173；fail/159–164；语法语料 positive/73。
- **验证**（WSL+qemu，临时种子）：tests/yh-run **291/291**（run 151/151、
  fail 132/132、pass 8/8）；语法门正例 76/76、反例 45/45；modules 门 77/84
  （基线）；native-selfhost 主门全部通过。
- **CT6 三项全部落地**：表达式选择（P0）、条件导入（决议不做）、类型分派
  （P1a）+ 动态字段（P1b/P1c）；todo 的 CT6 条目可标记完成。

## 2026-10-09 yh 编译期：CT6 P1a 类型分派谓词 `$is_type`/`$is_int`/`$is_float` 交付

- **P1a 交付**（CT6 子项「类型分派」候选 A 首片）：
  - g4：`comptimeCall` 增加 `'$' 'is_type' '(' expr ',' typeRef ')'` 备选
    （typeRef 实参需独立形态；`$is_int`/`$is_float` 走既有 callArgs）；
  - 语义（parse_expr.yh）：`parse_comptime_pred` 谓词**只看静态类型、不求值
    实参**（实参以 `c_em_suppress` 静默做完整语义检查；折叠上下文临时清
    `c_fold`，否则实参变量误报「不是常量」）；结果**恒为编译期布尔常量**，
    typed 路径记入常量节点 —— 无需新增 typed IR kind；
  - 判定：`$is_type(x, T)` = 类型相等；`$is_int`/`$is_float` 复用
    `ty_is_integer`/`ty_is_float`。
- **用例**：run/171（普通路径 + typed 字段类型分派 + 顶层 const 聚合实参）、
  fail/158（未知类型拒绝）、语法语料 positive/72。
- **验证**（WSL+qemu，临时种子）：tests/yh-run **283/283**（run 149/149、
  fail 126/126、pass 8/8）；语法门正例 75/75、反例 45/45；modules 门与
  自举主门结果见同日条目。
- **todo 更新**：CT6 条目改为「P0 表达式选择 + P1a 类型分派谓词已交付，
  P1b `$for f in T.fields` / P1c `$field` 待实施」。

## 2026-10-09 yh 编译期：CT6 P0 表达式选择 `$if (cond) e1 $else e2` 交付

- **决策落地**：用户确认 CT6 三项决策——表达式选择**候选 A**、条件导入
  **不做**（方案已从设计稿删除）、类型分派**候选 A**（`$is_type` 谓词）+
  动态字段与 CT4 合并**先只读**。设计稿定稿
  （[03-design/yh-编译期CT6语法设计.md](03-design/yh-编译期CT6语法设计.md)），
  实施见 [02-plan/yh-编译期CT6实施方案.md](02-plan/yh-编译期CT6实施方案.md)。
- **P0 表达式选择交付**：
  - g4：`expr` 链最上层新增 `comptimeIfExpr`（`$else` 必须书写，单 token
    lookahead 无歧义；作二元操作数需加括号）；
  - 解析（parse_expr.yh）：普通路径 cond 折叠选支，未选分支
    **`c_em_suppress` 静默发射但保留完整语义检查**（合流需要两侧类型）；
    typed 路径两分支全捕获、执行器按编译期值选支；合流按类型相等 +
    字面量 is_lit 路径；语句位置给出专用诊断；
  - `AST_EXPR_CTIF = 14` + ct_ir 执行器 kind 4/14 共用（含字面量类型归一）；
  - 修复首版 bug：子表达式曾在 depth==0 下误挂语句表达式边，return 执行器
    取到条件值（0/1）；改为与三元同等处理 capture depth 与挂载。
- **用例**：run/168–170、fail/154–157；语法语料 positive/71 + rejected/30。
- **验证**（WSL+qemu，临时种子）：tests/yh-run **281/281**（run 148/148、
  fail 125/125、pass 8/8）；语法门正例 74/74、反例 45/45；modules 门与
  主门结果见同日条目。
- **todo 更新**：CT6 条目拆分为「P0 已交付、P1 类型分派/动态字段待实施」。

## 2026-10-09 yh 编译期：return 聚合字面量 + CT 调用结果求值形态（同日追加）

- **发现并修复前端缺口**：`parse_array_literal` 要求「目标类型上下文」的设置点
  漏了 **return** —— `return [1, 2, 3]`（以及嵌套 `[[1,2],[3,4]]`、切片字面量）
  在编译期与普通函数里都被拒。修复：`parse_return` 求值返回表达式时把
  `c_expect_tid` 设为函数返回类型（与 let 初始化/赋值/调用实参一致）；非字面量
  表达式不受影响，`sem_can_assign` 校验不变。
- **随探针一并确认的既有能力**：编译期正文里对调用结果直接求值的下标、成员、
  切片视图、嵌套下标与 `for i, v in $mk()` 循环全部可用（typed IR 路径）。
- **用例**：run/167（编译期直接返回数组/嵌套数组/切片/结构体字面量 + 调用结果
  求值形态 + 普通函数运行时字面量返回）。
- **核实边界**：顶层 const 折叠的 `$mk()[0]`（对 CT 调用结果直接下标）仍不支持
  —— 折叠路径无法索引裸聚合对象指针，惯用写法 `const T = $mk(); T[0]` 经模型
  可用；已记 todo（暂不作，按现状说明）。
- **验证**（WSL+qemu，临时种子 `tmp/boot/chain/yh-19e2e3a`）：tests/yh-run
  **274/274**（run 145/145、fail 121/121、pass 8/8）；tests/modules/check 17/17；
  `native-selfhost.py` **全部通过**（模块固定点 21 产物一致、71 文件自解析、探针、
  CLI、语法 44/44、运行语料 274/274）；comptimecross 构建+运行 0。

## 2026-10-09 yh 编译期：CT6 语法与范围设计稿交付

- **内容**：todo 的 CT6（表达式选择、条件导入、类型分派/动态字段）按过程实施
  方案「先单独设计语法、类型阶段和依赖规则，再实施」的约定交付**设计稿**
  （[03-design/yh-编译期CT6语法设计.md](03-design/yh-编译期CT6语法设计.md)）：
  - **表达式选择**：推荐表达式形态 `$if (cond) e1 $else e2`，复用 `?:` 的
    种类合流检查；g4 无歧义论证（单 token lookahead 区分语句/表达式形态）；
  - **条件导入**：推荐 `@[if(<条件>)] import`，条件限定**目标常量**（CT0 标记
    集），在项目索引/依赖解析阶段求值，条件值并入缓存键（可重现构建 + 并行
    worker 确定性）；与平台后缀文件正交；
  - **类型分派/动态字段**：推荐 `$is_type(x, T)` 谓词 + 快捷谓词，不引入类型
    值/重载/泛型；动态字段定义为**编译期反射元信息消费**（`T.fields` +
    `$field(x, "name")`，先只读），建议与 CT4 合并设计实施；明确不做运行时
    反射与 `@[comptime]` 特化重载。
  - 给出实施顺序（P0 表达式选择 → P1 条件导入 → P2 分派/字段）与每项验收，
    以及 **D1–D6 决策点清单（待用户确认）**。
- **说明**：本项无编译器改动（设计先行，符合 AGENTS「修改语法规则」流程）；
  前几轮的验证结果（273/273、自举主门、comptimecross、ct5b 13 用例全绿）
  继续有效。本轮另确认 `$` 调用初始化的 pub 聚合常量跨模块导出**无任何真实
  使用面**（编译期正文、测试语料均无），维持 todo 的「小项挂起」决议。

## 2026-10-09 yh 编译期：CT5B 收尾核实（闭包契约与缓存失效在 Linux 上全绿）

- **内容**：本轮无编译器改动，对 todo 的 CT5B 条目做**收尾核实**：
  - `tests/modules/build-check.py` 的 **13 个 ct5b 用例全部通过**，包括
    `ct5b-cross-module-body`（`.s.ct` 闭包重写文本契约：隐藏符号 `__yhct_*`、
    局部类型/结构体字面量/限定名内联、字符串闭包与 `.data` 隔离）与
    **`ct5b-transitive-body-invalidates-importer`（缓存失效）**：提供方私有闭包
    常量 `OFFSET 1→2` 后导入方重求值（运行断言退出码按预期变化）；
  - 正文固定点另由 `native-selfhost.py` 的 `.s.ct` 跨代逐字节一致门覆盖
    （cc3→cc4 21 产物一致，自举主门全绿）；
  - 本机 build-check 总体 **77/84**（原 74/84），剩余 7 项是既有 Linux 平台
    缺口（r3-* 交叉目标探针 ×5、r2c-ir-cache-fixture、s2-libs-core-modules），
    与改动前基线一致，见 todo.md「Linux 平台缺口」。
- **todo 更新**：CT5B 标记完成；「未完成」清单收敛为：CT6（新特性设计，待语法
  方案与确认）、CT4 字段反射（按需）、`$` 初始化 pub 聚合常量导出（小项挂起）、
  泛条目（撤销候选项）。
- **验证环境**：WSL2 + qemu（临时种子 `tmp/boot/chain/yh-19e2e3a`），命令与
  前几轮相同；本轮不涉及编译器源码改动，前几轮的 273/273、自举主门与
  comptimecross 结果继续有效。

## 2026-10-09 yh 编译期：pub 聚合常量跨模块导出（同日追加）

- **交付**：
  - 解析期放行模块模式下的 **字面量初始化** pub 聚合常量（结构体/定长数组/切片），
    `$` 调用初始化仍拒绝（没有可重放的源文本，给明确诊断）；
  - `.s.i` 对聚合常量按**初始化式源文本**重放（`const_expr_kind = 4`，与 `.s.ct`
    闭包共用同一份文本）；导入侧重新解析即**编译期建模**；
  - 运行期在**导入方物化本单元副本**：`em_data_symbol_header` 在 `c_iface_load`
    下写本地数据标签（`.LD<n>`）并把标签号记入 `cval`，`sem_ident_val` 对
    `F_EXTERN` 聚合常量按标签装载地址（与字符串指针常量同一路径）——不与提供方
    导出的同名全局符号在链接期重复定义（实测：提供方 `.globl`，消费者只用 `.LD`）。
  - 提供方正文（.s.ct 闭包）、消费者自己正文（.s.i 加载模型）的编译期读都可用。
- **用例**：comptimecross 增 `PUB_TBL`（运行期 4+6、提供方 `pub_tbl_ct()`=20、
  消费者 `pub_model()`=19），host 全断言通过；另核对接口重放文本与两方对象符号
  形态。
- **验证**（WSL+qemu，临时种子 `tmp/boot/chain/yh-19e2e3a`）：tests/yh-run
  **273/273**（run 144/144、fail 121/121、pass 8/8）；tests/modules/check 17/17；
  `native-selfhost.py` **全部通过**（模块固定点 21 产物一致、71 文件自解析、探针、
  CLI、语法 44/44、运行语料 273/273）；comptimecross 构建+运行 0。
- **边界（记入 todo）**：`$` 调用初始化的 pub 聚合常量仍拒绝；CT5B 剩余、CT6/CT4
  仍待后续。

## 2026-10-09 yh 编译期：顶层切片实参（切片常量与切片字面量，同日追加）

- **交付**：
  - **切片字面量实参** `$f([1, 2, 3])`：新增 `p_ct_arg_slice_literal` 把形状折进
    编译期临时构造区 —— backing 聚合按元素个数创建（与切片常量模型同一形状），
    `ct_ir_slice_param_valid` 校验后直接别名，无需「地址 + 长度」的独立视图表示；
    元素支持标量/结构体/定长数组递归折叠，空切片字面量 `[]` 合法；
  - **切片常量实参** `$f(SL)` 随切片常量建模（上一轮）自动可用；
  - 正文内转发保持视图别名语义；聚合字面量实参的形态至此全部覆盖
    （联合体不存在：`union` 不是 yh 关键字）。
- **用例**：run/166（切片常量/字面量实参、下标+len、正文内转发、空切片）新增；
  fail/148（原「切片实参无折叠路径」）按惯例升级为 run/166 并删除；诊断文本
  「切片与联合体…」收窄为「联合体…」。
- **验证**（WSL+qemu，临时种子 `tmp/boot/chain/yh-19e2e3a`）：tests/yh-run
  **273/273**（run 144/144、fail 121/121、pass 8/8）；tests/modules/check 17/17；
  `native-selfhost.py` **全部通过**（模块固定点 21 产物一致、71 文件自解析、探针、
  CLI、语法 44/44、运行语料 273/273）；comptimecross 构建+运行 0。
- **边界（记入 todo）**：pub 聚合常量跨模块导出、CT5B 剩余、CT6/CT4 仍待后续。

## 2026-10-09 yh 全局聚合常量：模型取址只读别名 + 切片常量建模（同日追加）

- **交付**：
  - `&TABLE[0]` / `&P.x`（含嵌套聚合）可在编译期**取址并只读解引用** ——
    `ct_ir_lvalue` 对模型基址的下标/字段分支放行，`ct_ir_pointer_target` 解析链
    追加模型区扫描（覆盖嵌套子对象），指针下标/指针算术/指针形参转发随之可用；
    写入统一按只读拒绝（赋值语句按 `ct_global_agg_hit` 拦截，与字符串只读池
    同一策略）。
  - **切片常量**同样建模（`const SLICE []int = [...]`）：元素个数只有解析完
    字面量才知道，`parse_global_array_init` 的 `ct_obj` 改为出参、切片模型在内部
    按 count 创建；下标/`len`/`for-in`/切片视图表达式/空切片/浮点元素可用；
    `.s.ct` 闭包的 `agg_src` 加入 `TY_SLICE`，跨模块切片常量随闭包重放并建模
    （comptimecross 的 `priv_slice_ct()`，host 断言 29）。
- **用例**：run/164（模型取址只读）、run/165（切片常量 CT 读）新增；fail/153
  （模型写入被拒）新增；fail/152（原「取址一律拒绝」）升级为 run/164 并删除；
  comptimecross 增 `priv_slice_ct()`。
- **验证**（WSL+qemu，临时种子 `tmp/boot/chain/yh-19e2e3a`）：tests/yh-run
  **273/273**（run 143/143、fail 122/122、pass 8/8）；tests/modules/check 17/17；
  `native-selfhost.py` **全部通过**（模块固定点 21 产物一致、71 文件自解析、探针、
  CLI、语法 44/44、运行语料 273/273）；comptimecross 构建+运行 0。
- **边界（记入 todo）**：切片**实参/值传递**（需要顶层视图表示）、pub 聚合常量
  跨模块导出仍待后续。

## 2026-10-09 yh 全局聚合常量在编译期有值（编译期过程剩余任务的实质项）

- **交付**：全局聚合常量（顶层 `const` 数组/结构体）的元素值在**语义阶段**建模成
  `CtAggregate`——新增 `compiler/comptime/ct_global_agg.yh`（独立只增拥有区 +
  按符号登记 + 可建模性谓词；`ct_reset` 清登记表）。编译期正文读下标/字段/嵌套
  字段/`len`/`for-in`/按值传参全部复用既有聚合路径；顶层 `$f(TABLE)`/`$f(P)`
  命名聚合实参；跨模块（`.s.ct` 闭包重放初始化式源文本，导入侧重新解析即建模）
  随之打通（`comptimecross` 的 `priv_tbl_ct()` 用 for-in + 下标读到 9，host
  断言通过）——顺带修复闭包发射对 for-in 绑定的误判（`ct_iface_local_type_target`
  跳过 `in`/`,` 后缀，跨模块 CT 正文首次支持 for-in）。
  见[完成记录](01-finished/yh-全局聚合常量编译期建模-2026-10-09.md)。
- **用例**：run/161–163 新增；fail/151（旧诊断形态）按惯例升级为 run/162 并删除；
  fail/152 锁定「模型元素取址/写入」的只读边界诊断。
- **顺带修复**：`asm/src/main/main.yh` 的写对象 `open` 标志按目标平台取值
  （Linux 0x241 / Darwin 0x601，此前写死 Darwin 数值，Linux 上汇编产物永远写不
  出，「写对象文件失败」）；Linux 上 `asm/tests/check.py` 自检通过。
- **WSL 种子链**：入库种子是 darwin/arm64（Mach-O），Windows/WSL 无法执行；
  本次在 WSL 沿 git 历史重建 Linux/aarch64 自举种子链（C stage0 → 逐代重建到
  HEAD，含三段过渡补丁），临时开发种子 `tmp/boot/chain/yh-19e2e3a`（不入库），
  见[完成记录](01-finished/yh-WSL重建Linux-aarch64自举种子-2026-10-09.md)。
- **验证**（本机 WSL+qemu，等价 `make test` 与 `make selfhost-native`，种子哈希
  校验除外）：
  - `tests/yh/check.py`（ANTLR 参考语法，需 Java + antlr4 jar）：正例 73/73、
    反例 44/44；`--compiler` 模式同 73/73 + 44/44；
  - `tests/yh-run/check.py --compiler ./yh`：run 141/141、fail 122/122、
    pass 8/8，总计 **271/271**；
  - `tests/modules/check.py`：17/17；`build-check.py`：74/84，与未改动的
    HEAD 基线在同一环境完全一致（无回归；剩余 10 项是既有 Linux 缺口，见
    todo.md「Linux 平台缺口」）；
  - `tests/selfhost/native-selfhost.py --seed <临时种子>`：**全部通过**——
    cc2→cc4 三代冷编、模块固定点（21 产物）一致、71 文件自解析、固定点探针、
    CLI 冒烟、语法与运行语料 271/271；
  - 探针：scratch-isolation 8/8、check-command 通过；lex-stats/runtime-memory/
    link-cache 被 yh_link 的 ELF64 方言缺口阻塞（本机 `YH_LINK=/nonexistent`
    回落 gcc 可绕过，已记入 todo.md）。
- 边界（记入 todo.md）：切片常量不建模；`&TABLE[0]` 编译期取址/写入按 fail/152
  拒绝（模型只读）；pub 聚合常量跨模块导出仍未做。

## 2026-10-07 汇编器与链接器项目归位（asm/ 与 link/）

- **两个项目按职责分开**：`asm/`（yh_asm）= 汇编器，`link/`（yh_link）= 链接器。
  整理前 `link/` 里寄放着汇编器实现（`src/obj` 对象模型与出口 + `src/asm`
  编码解析），自己的链接器职责一行未写；`asm/` 里是上一代较弱的实现。
- **汇编器实现整体迁到 `asm/`**：`link/src/{obj,asm,main}` → `asm/src/`，
  `link/tests/*` → `asm/tests/`；工具名与所有引用从 `yh_link` 改 `yh_asm`
  （`main.yh` 用法、脚本默认产物路径、`YH_LINK` → `YH_ASM`、README）。
  现役实现 19 个 `.yh`/7065 行，能力到 TC3+TC8（ELF64 与 Mach-O 对象出口、
  标量浮点、GOT 重定位）。上一代 asm 实现（11 个 `.yh`/5528 行 + 123 项内嵌
  测试）归档到 `tmp/removed-2026-10-07/asm-legacy/`。
- **`link/` 清空为链接器骨架**：保留 `project.toml`，新写 `src/main/main.yh`
  入口（`--version` 返回 0，`link` 子命令与无参调用报「尚未实现」并返回 2），
  新增门 `tests/check.py`（冷编 + 入口行为），README 重写为链接器定位
  （TC4/TC9/TC10/TC11）。
- **恢复上一轮误删的 17 个无调用点函数**：`mul_chk`、`buf_clear`、`buf_align`、
  `rd_u16le`、`rd_u64le`、`is_pow2`、`ts_equal`、`sec_file_size`、`es_shndx_of`、
  `sh_ok`、`cond_alias_len`、`mem_size_bytes`、`lex_tok`、`e_testbr`、
  `p_err_at`、`p_txt_len`、`p_is_imm_start`——项目仍在开发阶段，未接线的能力
  不是冗余。未恢复 `src/ln/` 的 SHA-256（无生产调用点，TC10 再取回）。
- **保留 `e_nop` 符号扩展修复**（`asm/src/asm/33_enc_br.yh`）：
  `0xd503201f.to_type(i64)` 按 i32 折叠成负数再符号扩展，`nop` 写成
  `0xffffffffd503201f` 被越界检查拒绝；改为 `.to_type(u32).to_type(i64)` 后
  自检 rc 103 → 0，语料 `04-ldst-modes.s` / `06-sysops.s` 恢复汇编。
- **Makefile**：新增 `make yh-asm`（冷编 `asm/`，产出根目录 `yh_asm`）；
  `make yh-link` 变成过渡别名（把同一份产物复制成 `yh_link`），因为编译器
  `mb_asm_tool` 仍按 `yh_link` 查找；查找名切换后删除该别名。
- 验证（本机 darwin/arm64）：`python3 asm/tests/check.py --full` 通过——自检
  rc=0、134 编码向量 0 不一致、编译器全量语料 61/61 逐字节一致、61 个对象
  0 问题 0 非确定；Mach-O 全量 61/61 一致；`python3 link/tests/check.py` 通过；
  `make yh-asm` / `make yh-link` 产物 `--dump-enc` 各 134 条；
  编译器汇编步集成门 `tests/selfhost/link-cache.py` 通过。
- 未动 `compiler/` 与 `bin/yh` 种子，不触发滚种子。
- 遗留：编译器汇编步查找名切换、指令级负例门迁移（19 条负例未随实现迁移），
  已记入 [todo.md](todo.md)；链接器实现从 TC4 开始。
  详见[完成记录](01-finished/yh汇编器与链接器项目归位-2026-10-07.md)。

## 2026-10-07 yh 编译期跨模块函数来源精确列映射

- `.s.ct v1` 为每处正文改写序列化 sidecar 生成范围到原函数源码范围的映射。导入解析时临时映射 token
  行列，`ct_register` 捕获映射后恢复原 sidecar token 位置，使两遍解析彼此独立。跨模块调用名、常量名和
  类型名改写后的语义错误与 `$assert/$compile_error/$compile_warn` 诊断均回到定义源码。
- `comptimecross` 在同一行先改写 `OFFSET` 和 `$point_size()`、再触发 `$compile_error`，检查精确原始列；
  同时检查改写常量引用的语义类型错误和损坏列映射拒绝。
- `make -B` 与 `make test` 通过：语法 73/73、44/44；运行语料 217/217。滚种子前后
  `make selfhost-native` 均通过：固定点 21/21、自解析 71 个源文件、模块语法 17/17、项目 84/84，附加探针通过。
- `make seed` 后 SHA-256：`6e413b729407a1a8c7ddc23b6b20eb0d96ac33d3fe959ecb551482c408b1f0ed`。
  详见[完成记录](01-finished/yh-编译期跨模块函数来源精确列映射-2026-10-07.md)与
  [CT5B 实施方案](02-plan/yh-编译期跨模块函数正文传递实施方案.md)。

## 2026-10-07 yh 编译期跨模块字符串指针常量闭包

- `.s.ct v1` 现在为可达私有 `*char` 常量保留直接字符串 token，导入方重新解析后供 CT 正文类型检查。
  其他指针常量表达式、指针求值和解引用仍拒绝；执行路径实际读取指针常量时报“不支持指针常量”。导入 sidecar 会回收解析期间暂存的数据输出，不把闭包
  字符串写入消费者运行期 `.data`。
- `comptimecross` 验收 `.s.ct` 中的隐藏字符串常量、消费者汇编不含该字符串、非字面量指针常量被拒绝，
  以及执行路径读取指针常量时拒绝求值。
  `make -B`、`make test` 全绿（语法 73/73、44/44；运行 217/217）；滚种子前后 `make selfhost-native`
  均通过：固定点 21/21、自解析 70 个源文件、运行语料 217/217、模块语法 17/17、项目 84/84，附加探针通过。
- `make seed` 后 SHA-256：`c05e91ba769ee35fee055684197e3b5483ef464ed41395c79fb57d9923657270`。
  详见[完成记录](01-finished/yh-编译期跨模块字符串指针常量闭包-2026-10-07.md)与
  [CT5B 实施方案](02-plan/yh-编译期跨模块函数正文传递实施方案.md)。

## 2026-10-06 yh 编译期跨模块 CT 函数来源映射

- `.s.ct v1` 为每个隐藏 CT 函数保存定义源码路径和函数体起始行。导入时，函数体语义错误与执行期
  `$assert`、`$compile_error`、`$compile_warn` 诊断映射回定义文件；列映射在 2026-10-07 后续片补齐。
  旧 sidecar 无来源注释时仍报告 sidecar 位置。
- `comptimecross` 增加语义错误与 `$compile_error` 来源映射回归。`make -B`、`make test` 全绿
  （217/217）；滚种子前后 `make selfhost-native` 均通过：固定点 21/21、自解析 70 个源文件、运行
  语料 217/217、模块语法 17/17、项目 84/84，附加自举探针通过。
- `make seed` 后 SHA-256：`3db8d25b73478c1433ea08b12d233a7aef34aa1ae7cc12014e2156540f180e85`。
  在该次交付后，精确列映射及直接字符串字面量指针常量闭包已完成；其他指针常量边界仍待处理。详见
  [完成记录](01-finished/yh-编译期跨模块CT函数来源映射-2026-10-06.md)与
  [CT5B 实施方案](02-plan/yh-编译期跨模块函数正文传递实施方案.md)。

## 2026-10-06 yh 编译期跨模块浮点字面量闭包

- `.s.ct v1` 为可达正文引用的直接浮点全局常量保留原始字面式并导出隐藏 `const`；导入方重新解析，
  仅供 CT 正文类型检查，不开放浮点评估。`comptimecross` 验收隐藏常量和重写引用。
- `make -B` 冷编通过；`make test` 全绿（语法 73/73、44/44；运行 108/108、拒绝 101/101、仅编译 8/8，
  共 217/217）。滚种子前后 `make selfhost-native` 均全绿：固定点 21/21、自解析 70 个源文件、语料
  217/217、模块语法 17/17、项目 84/84；附加自举探针通过。
- `make seed` 后 SHA-256：`82349b80fc77b9cdc2a2e29e0fe7bc2b8c459ffeae4d7158f14999dd9e016791`；
  滚种子后的自举主门复验通过。
- 浮点评估、指针/字符串常量闭包和原始定义位置映射仍待处理。详见
  [完成记录](01-finished/yh-编译期跨模块浮点字面量闭包-2026-10-06.md)与
  [CT5B 实施方案](02-plan/yh-编译期跨模块函数正文传递实施方案.md)。

## 2026-10-06 yh 编译期跨模块公共类型引用

- `@[comptime]` 函数注册时保存定义文件的已绑定导入别名和模块编号。导出 `.s.ct` 时，结构体字面量、
  `.to_type`、`sizeof`（含指针层级）中的 `alias.Type` 被解析为公开接口类型并规范化输出，导入方无需
  继承定义文件的别名。
- `comptimecross` 新增 `types` 模块与第二个 `base` 源文件，分别以 `geometry`、`dimensions` 引用同一
  类型，覆盖不同文件导入别名快照、结构体构造、标量别名 cast、`sizeof` 及私有辅助函数闭包。
- `make test`：语法正例 73/73、反例 44/44；运行 108/108、拒绝 101/101、仅编译 8/8，共 217/217。
  模块项目门 84/84。`make selfhost-native`：21 个固定点产物一致、自解析 70 个源码文件、
  运行语料 217/217、模块语法 17/17、项目 84/84，隔离/缓存/运行时探针通过。
- `make seed` 后 SHA-256：`91168ae5cadd893ffecd44a86dd19c541e4c7004b915024bcb3b17f6437a5b47`；
  滚种子后的 `make selfhost-native` 再次通过。
- CT5B 剩余模块常量闭包只支持整数；原始 `.s.ct` 定义位置映射待实现。
  详见[实施方案](02-plan/yh-编译期跨模块函数正文传递实施方案.md)。

## 2026-10-06 yh 编译期跨模块私有别名复合类型擦除

- `.s.ct` 现在按语义类型发射完整局部类型，覆盖 `[N]Alias` 和 `*Alias`；结构体字面量、
  直接具名 `.to_type(Alias)` 与 `sizeof(Alias)`、`sizeof(*Alias)`、`sizeof(**Alias)` 也会改写为提供方可见的底层类型名。
- `sizeof_starts_type` 现在从跳过的连续星号后查找类型名；运行回归验证 `sizeof(*Type)` 与
  `sizeof(**Type)` 都按类型解析。
- `comptimecross` 使用私有 `Offset`/`Scalar` 别名并在消费者声明同名别名，覆盖结构体数组、指针
  局部值、cast、`sizeof`、别名不泄漏、跨模块执行及依赖变更后的重求值。
- `make test`：语法正例 73/73、反例 44/44；运行 108/108、拒绝 101/101、仅编译 8/8，共 217/217。模块项目门 84/84。
  `make selfhost-native`：21 个固定点产物一致、自解析 70 个源文件、语法 44/44、运行语料 217/217，
  模块 17/17 与 84/84 及附加探针通过；滚种子后复验也通过。
- `make seed` 后 SHA-256：`66d0dc4f614e57ddf2f67e2dd8d566f736ab86b4dc1abb71d040569b3fb83c43`。
  模块限定类型、非整数常量闭包和原始位置映射仍待处理。
  详见[完成记录](01-finished/yh-编译期跨模块私有别名复合类型擦除-2026-10-06.md)。

## 2026-10-06 yh 编译期跨模块整数常量闭包

- `.s.ct v1` 现在导出可达 CT 正文引用的已就绪整数常量：常量值以隐藏 `const` 写入伴随文件，
  函数正文中的标识符同步重写为隐藏名。导入方先解析并折叠隐藏常量，再重新捕获函数 typed IR。
- 修正 `iface_ct_load` 的 pass2 游标：新增全局常量扫描会到达 EOF，捕获 CT 函数正文前现在会
  重新从文件开头遍历；`comptimecross` 覆盖私有 `OFFSET`，并验证常量从 1 改成 2 后消费者重新求值。
- `make test`：语法正例 73/73、反例 44/44；运行、拒绝和仅编译语料共 216/216。
  `make selfhost-native`：cc3→cc4 的 21 个 `.s/.s.i/.s.ct` 产物逐字节一致，自解析 70 个源文件，
  模块语法 17/17、项目 84/84 及附加探针通过。滚种子后再次运行主门也全绿。
- `make seed` 后 SHA-256：`e3ce622f8cd82823d1e27ce1883f72dff034e2877daa5dd1b0a627b7618e5542`。
  私有具名类型、非整数常量和原始定义位置映射仍属 CT5B 后续范围。
  详见[完成记录](01-finished/yh-编译期跨模块整数常量闭包-2026-10-06.md)。

## 2026-10-06 yh 编译期跨模块正文传递：两层闭包首片

- `.s.ct` 的公开正文闭包现在可跨模块调用另一公开 `@[comptime]` 函数。导出器将
  `$alias.function(...)` 重写为提供方隐藏符号；typed IR 导入器把函数节点追加到当前 arena，
  并重定位表达式、语句、边和局部绑定索引，避免不同 sidecar/local AST 从编号 0 开始时冲突。
- `comptimecross` 覆盖 host → math.api → math.base 的调用链：公开 `double_after_bump(20)` 得到
  42，隐藏函数名未进入运行期汇编；修改最底层 `plus_one` 后消费者重建并得到 44（进程退出码 2）。
- `make test` 全绿：ANTLR 与编译器语法各正例 73/73、反例 44/44；运行语料 107/107，拒绝语料
  101/101，仅编译语料 8/8，共 216/216。模块项目验收 84/84。
- `make selfhost-native` 全绿：cc3→cc4 的 21 个 `.s/.s.i/.s.ct` 产物逐字节一致，cc4 自解析
  70 个源码文件，模块语法 17/17、项目 84/84 和附加探针通过。
- `make seed` 后种子 SHA-256 为
  `9c7285a7720429a2307d22e31808ebe5006c0ebe20d78504a3da6b902e949698`。来源映射、模块私有具名类型、
  编译期常量闭包和损坏 `.s.ct` 专项正反例仍属于 CT5B 后续工作。详见[完成记录](01-finished/yh-编译期跨模块正文两层闭包-2026-10-06.md)。

## 2026-10-06 yh 编译期结构体整数切片字段

- typed 执行器支持结构体中的整数切片字段。普通结构体副本复制视图描述并共享 backing elements；嵌套返回递归复制切片可见元素到调用方帧；最外层静态数据物化覆盖切片描述和元素。
- 新增 run/96 覆盖副本/形参别名、返回生命周期和全局初始化；新增 fail/129 锁定浮点切片字段拒绝，并更新 fail/102、fail/103 的诊断断言。
- `make test` 全绿：语法两层各 72/72 正例、44/44 反例，运行 106/106、拒绝 101/101、仅编译 8/8，总计 215/215。
- `make selfhost-native` 全绿：固定点 14/14、自解析 68 个源文件、模块 17/17、项目 83/83 及其余探针。
- `make seed` 后新种子冷编 `make` 成功。种子 SHA-256：`203487af71b909fb06e058c23b9bedecf8da8ef3504df573dda0c642f89e407c`。详见[完成记录](01-finished/yh-编译期结构体整数切片字段-2026-10-06.md)。

## 2026-10-06 yh 编译期复合数组 for-in 值语义

- typed CT `for-in` 遍历受支持定长数组的结构体或嵌套数组元素时按值深复制；循环体写入迭代绑定不会修改源数组。切片元素仍限整数。
- 新增 `tests/yh-run/run/95-comptime-forin-struct-values.yh`，覆盖结构体字段与嵌套数组修改隔离，输出 `comptime-forin-values=14613 rows=1404`。
- `make test` 全绿（语法 72/72 + 44/44，运行 105/105、100/100、pass 8/8，共 213/213）；`make selfhost-native` 全绿（14 个产物固定点、68 个源文件自解析、模块 17/17、项目 83/83）。
- `make seed` 后冷编 `make` 与 `git diff --check` 通过。新种子 SHA-256：`4891cbc4ca8827565b8864042c3ad11a1c290be3d72bef70161aee8f679d3862`。详见[完成记录](01-finished/yh-编译期结构体数组for-in值语义-2026-10-06.md)。

## 2026-10-06 yh 编译期布局常量依赖调度

- typed 布局阶段现在登记整数 CT 常量的未就绪依赖；单文件与同模块多文件按 READY 依赖
  多轮求值，普通全局 const 的顺序初始化保持原规则。
- 依赖无进展时报告常量名闭环；新增 run/122、fail/123 和
  `comptimelayoutdeps`，分别锁定前向依赖求值、环链诊断及跨源文件调度。
- `make test` 全绿：语法 72/72 + 44/44，运行 101/101、拒绝 97/97、通过 8/8，共
  206/206。`make selfhost-native` 全绿：固定点 14 个产物一致、自解析 67 个源文件、
  模块 17/17、项目 83/83 和所有探针通过。
- `git diff --check`、`make seed` 与新种子冷编 `make` 全部通过；种子 SHA-256：
  `2d1ca124e9366244e2907ee59244e9e5eb4e5fd8da291130a99d183cd0663e55`。完成记录：[布局常量依赖调度](01-finished/yh-编译期布局常量依赖调度-2026-10-06.md)。

## 2026-10-06 yh 编译期 typed 递归布局求值

- typed 布局请求现在按实际执行路径处理递归 CT 调用；到达基例的递归可产生数组/字段长度，无限互递归由既有 64 层深度预算拒绝。旧 token 早期探测仍只处理无环调用图。
- 新增 run/121 验证递归结果 4 决定结构体字段和全局数组；更新 fail/112 验证预算诊断。移除 `ct_layout` 中只用于静态递归扫描的调用图代码和状态。
- 主要实现位于 `compiler/parse/parse_ct_layout.yh` 与 `compiler/comptime/ct_layout.yh`；边界见[方案](02-plan/yh-编译期typed递归布局求值方案.md)、[编译期设计](03-design/yh-编译期过程设计.md)和[完成记录](01-finished/yh-编译期typed递归布局求值-2026-10-06.md)。
- `make test`：语法 72/72 + 44/44，运行 100/100、拒绝 96/96、通过 8/8，共 204/204；`make selfhost-native`：固定点 14 个产物一致、自解析 67 个源文件、模块 17/17、项目 82/82 和全部探针通过。
- `git diff --check`、`make seed`、新种子冷编 `make` 全部通过；种子 SHA-256：`2a195f471a7c2ee06898a0c42181dc3827f3f8e2440f5aac7fb296325da72164`。

## 2026-10-06 yh 编译期 typed 布局请求

- pass1 将字段/文件级数组中引用先行未就绪整数 const 的布局记为 pending；首片要求 typed `@[comptime]` 调用图无环，后续递归阶段已放开到达基例的递归。布局常量可补齐数组和嵌套结构体布局，并使用已支持的局部赋值、分支局部值与循环。
- 新增 run/117 和跨源文件 `comptimelocal` 覆盖；旧 fail/108、114、116 改为 run 正例；新增 fail/118–120 锁定前向 const、pending `sizeof` 与无返回路径。
- 主要实现位于 `compiler/comptime/ct_layout.yh`、`ct_00_model.yh`、`ct_registry.yh`、`compiler/parse/parse_ct_layout.yh` 和 pass 调度代码；范围见[方案](02-plan/yh-编译期typed布局请求实施方案.md)、[设计](03-design/yh-编译期过程设计.md)及[完成记录](01-finished/yh-编译期typed布局请求-2026-10-06.md)。
- `make test` 全绿：语法 72/72 + 44/44，运行 99/99、拒绝 96/96、通过 8/8，共 203/203。`make selfhost-native` 全绿：固定点 14 个产物一致、自解析 67 个源文件、模块 17/17、项目 82/82 和全部探针通过。
- `git diff --check`、`make seed`、基于新种子的冷编 `make` 均通过；新种子 SHA-256：`56f709edb6f2dfdeb2b6cab8403d53c167a12e66e7cfbb27114e8b850019fe14`。

## 2026-10-06 yh 编译期数组长度局部值早期探测

- CT5A 早期执行器为每个调用帧保存局部值，安全探测现在允许显式内建整数类型的顶层已初始化 `let`，供后续条件与返回表达式读取；嵌套函数各自拥有独立局部值表。
- 局部声明只允许出现在函数最外层，且不能赋值；分支内声明、循环和其他不支持语句不会提前执行。更新 `fail/108` 锁定分支局部拒绝，新增 run/115、fail/116 覆盖多层调用局部值与赋值拒绝。
- 实现位于 `compiler/comptime/ct_00_model.yh`、`ct_eval_expr.yh`、`ct_registry.yh`；边界见[阶段方案](02-plan/yh-编译期数组长度函数求值实施方案.md)和[设计](03-design/yh-编译期过程设计.md)。
- `make test` 通过：语法 72/72 + 44/44，运行 95/95、拒绝 96/96、通过 8/8，共 199/199。
- `make selfhost-native` 全绿：固定点 14 个产物一致、自解析 65 个源文件、运行语料 199/199、模块 17/17、项目 82/82 和全部探针通过。
- `make seed` 后冷编 `make` 通过；新种子 SHA-256：`26c44323f9cf1ee5083a2db2bba6bf9e821ec6110145e9706bd35cd2bc60f1c7`。

## 2026-10-06 yh 编译期数组长度条件分支早期探测

- CT5A 的全局布局早期安全探测扩展到只含 `if/else` 与 `return` 的整数 CT 函数；支持穷尽分支、后置默认 return 与无环嵌套调用，仍拒绝局部变量、循环及非穷尽路径。
- 新增 `tests/yh-run/run/113-comptime-array-length-conditional-call.yh` 与 `fail/114-comptime-array-length-nonexhaustive.yh`；旧环检测、复杂正文和前向常量失败用例继续通过。
- 主要实现位于 `compiler/comptime/ct_registry.yh`，设计边界及后续 typed 布局请求见[阶段方案](02-plan/yh-编译期数组长度函数求值实施方案.md)与[设计](03-design/yh-编译期过程设计.md)。
- `make test` 通过：语法 72/72 + 44/44，运行 94/94、拒绝 95/95、通过 8/8，共 197/197。
- `make selfhost-native` 全绿：模块固定点 14 个产物一致、自解析 65 个源文件、语法/运行语料全绿、模块 17/17、项目 82/82 与所有自举探针通过。
- `make seed` 后冷编 `make` 通过；新种子 SHA-256：`0e8c74d168f0b10fe6529974d7f1489ab81ff5667b3fd22160d15bd8faa98064`。

## 2026-10-06 yh 编译期数组长度函数求值首片

- pass1 早期折叠以单 return 整数表达式为正文的已登记 CT 函数，支持以该结果初始化全局整数 const，并在后续结构体字段/全局数组长度中读取。
- 新增 run/91–92 与 fail/108；复杂函数、前向布局依赖和环仍保持“编译期常量尚未就绪”，不把占位值作为长度。
- 实现位于 `compiler/comptime/ct_registry.yh` 与 `compiler/parse/parse_global_init.yh`；下一阶段请求/依赖求解见[实施方案](02-plan/yh-编译期数组长度函数求值实施方案.md)和[首片记录](01-finished/yh-编译期数组长度函数求值首片-2026-10-06.md)。
- `make test` 通过（语法 71/71 + 44/44；运行 91/91、拒绝 91/91、通过 8/8，共 190/190）；`make selfhost-native` 通过（固定点 14/14、自解析 64 个源文件、模块 17/17、项目 82/82 与所有探针）。
- 滚种子后冷编 `make` 通过；新种子 SHA-256：`d79dfec88153413ff936cf523a60541b5edf7f45c61da5fde6080cac3384d6b5`。

## 2026-10-06 yh 编译期 typed 顶层聚合结果

- 最外层 `$f(...)` 支持受支持的数组、结构体和整数切片返回：普通运行期路径按类型布局物化为静态数据，编译期外层调用保留 `CtAggregate`；局部和全局可变 `let` 均可初始化。
- 新增 run/89、run/90，并扩展 `comptimelocal` 跨源文件模块项目；拒绝反例继续锁定指针返回和非整数元素切片。
- 实现位于 `compiler/comptime/ct_registry.yh`、`ct_ir_place.yh` 和 `compiler/parse/parse_global_init.yh`；范围与取舍见[方案](02-plan/yh-编译期typed顶层聚合结果实施方案.md)，验收见[完成记录](01-finished/yh-编译期typed顶层聚合结果-2026-10-06.md)。
- `make test` 通过（语法 71/71 + 44/44；运行 89/89、拒绝 90/90、通过 8/8，共 187/187）；`make selfhost-native` 通过（固定点 14/14、自解析 64 个源文件、模块 17/17、项目 82/82 与全部探针）。滚种子后冷编 `make` 通过；SHA-256：`bc994fcdf0a6ee7f5c6c689da7c39a46b4fb0021e4e75a860622adf599879a6d`。

## 2026-10-06 yh 编译期 typed 整数切片返回

- 编译期函数可在嵌套 typed 调用中返回整数切片；被调帧退出前将视图可见元素复制到调用方帧，调用方可安全读写并继续传给嵌套函数。顶层切片结果、非整数切片元素仍拒绝。
- 新增 `run/88` 覆盖局部数组切片返回、后续聚合分配、嵌套切片形参写入；`fail/105` 改为拒绝 `[]Point`，新增 `fail/107` 锁定顶层切片结果拒绝；`comptimelocal` 增加跨源文件用例。
- 执行逻辑位于 `compiler/comptime/ct_ir_place.yh`、`ct_ir.yh` 与 `ct_registry.yh`，签名检查位于 `compiler/parse/parse_decl.yh`；设计范围见[实施方案](02-plan/yh-编译期typed切片返回实施方案.md)。
- `make test` 通过：语法 71/71、44/44，运行 87/87、拒绝 90/90、通过 8/8，共 185/185；`make selfhost-native` 通过，固定点 14/14、自解析 64 个源文件、模块 17/17、项目 82/82 及全部探针。
- `make seed` 后冷编 `make` 成功；新种子 SHA-256：`0993d792fb5f7eea3b64bba81b31e891539d74886ddf95bf4e948b0ac4dcb5ed`。

## 2026-10-06 yh 编译期 typed `len`

- typed IR 捕获并执行 `len`，读取当前调用帧中的定长数组或切片长度；切片使用视图长度，空切片返回 0。普通运行期语义保持原路径。
- 新增 run/87，覆盖整型数组、结构体数组、切片视图和空切片，输出 322；`comptimelocal` 跨文件项目增加 `len` 断言 320。
- 实现接缝位于 `compiler/parse/parse_expr.yh`，执行位于 `compiler/comptime/ct_ir.yh`；详情见[方案](02-plan/yh-编译期typed-len实施方案.md)和[完成记录](01-finished/yh-编译期typed-len-2026-10-06.md)。
- `make test` 通过（语法 71/71 + 44/44，运行 183/183）；`make selfhost-native` 通过（固定点 14/14、自解析 64 个源文件、模块 17/17、项目 82/82 及全部探针）。
- `make seed` 后冷编 `make` 成功。种子 SHA-256：`d9675dcded01a675eba65e4c08e274523cbb2f258c076364cf5608332f988501`。

## 2026-10-06 yh 编译期 typed 结构体数组元素

- CT3 定长数组元素扩展为整型或执行器支持的结构体。数组字面量、结构体内数组字段、数组形参及嵌套返回均递归深复制；数组下标后的结构体成员写入落在局部帧值上。
- 新增 `tests/yh-run/run/86-comptime-struct-array-values.yh` 和 `comptimelocal` 跨源文件项目回归，运行期结果为 1422，验证数组形参、返回、字段副本和成员变更之间互不污染。
- 实现位于 `compiler/comptime/ct_ir_place.yh`、`ct_ir.yh`；方案和范围见[实施方案](02-plan/yh-编译期typed结构体数组元素实施方案.md)，详细证据见[完成记录](01-finished/yh-编译期typed结构体数组元素-2026-10-06.md)。
- `make test`：语法正例 71/71、反例 44/44；运行语料 182/182。`make selfhost-native`：14 个产物固定点、64 个源文件自解析、模块 17/17、项目 82/82 及其余探针通过。
- `make seed` 后冷编 `make` 成功。种子 SHA-256：`ccba81ebca3396f674794cac3b3aa30a61f3a7c49463b5da0b51f98d0affdae4`。

## 2026-10-06 编译期 typed 聚合返回

- 嵌套 typed 调用可返回受支持的定长整数数组/结构体，并在被调帧释放前深复制到调用方帧；顶层 `$` 结果仍限标量，切片返回拒绝。
- 新增 run/85、fail/105–106，扩展 `comptimelocal` 跨源文件验收。
- `make test` 语法 71/71、44/44，运行 84/84、拒绝 89/89、通过 8/8，共 181/181；`make selfhost-native` 固定点 14/14、自解析 64 个源文件、模块 17/17、项目 82/82 与全部探针通过。
- `make seed` 后冷编 `make` 成功。种子 SHA-256：`cf5c272d3a0cb1d96773940c5fe2f0ef354575bb087e8d07de526c3b21be83d1`。详见[完成记录](01-finished/yh-编译期typed聚合返回-2026-10-06.md)。

## 2026-10-06 编译期 typed 聚合形参

- 编译期函数支持受限整数数组/结构体形参按值深复制、整数切片形参共享视图；返回仍限整数。
- 新增 run/84、fail/104，并为 `comptimelocal` 增加跨源文件回归。
- `make test` 语法 71/71、44/44，运行语料 178/178；`make selfhost-native` 固定点 14/14、自解析 64 个源文件、模块 17/17、项目 82/82 和所有探针通过。
- 滚种子并冷编 `make` 成功。SHA-256：`0b2882e28c7d1d45e3fb0ed6ea69114bb2287c070cc02c66f4b465915e99ab4b`。详见[完成记录](01-finished/yh-编译期typed聚合形参-2026-10-06.md)。

## 2026-10-06 编译期 typed 结构体嵌套定长数组字段

- 结构体字段支持最多 32 层、叶元素为整数的定长数组；嵌套初始化、结构体/数组递归按值复制和多级成员下标读写均通过。
- 新增 run/83、fail/103，并扩展 `comptimelocal` 跨源文件项目，验证复制隔离与非整数叶元素拒绝。
- `make test` 通过 176/176；`make selfhost-native` 固定点 14/14、自解析 64 个源文件、模块 17/17、项目 82/82 与所有探针通过。
- `make seed` 后冷编 `make` 成功。新种子 SHA-256：`f66c692a933826f4eb345aa2687deb1bc2af4341f4fde6ff1dbc1b5b5413b243`。详见[完成记录](01-finished/yh-编译期typed结构体嵌套定长数组字段-2026-10-06.md)。

## 2026-10-06 编译期 typed 结构体定长整型数组字段

- `@[comptime]` 本地具名结构体可持有定长整型数组字段；字段初始化、局部数组复制、嵌套结构体复制与成员下标写入均按值隔离。
- 新增 run/82 与 `comptimelocal` 跨源文件用例；修复 typed IR arena 导入对函数 AST 切片必须连续的假设，保留原节点编号并允许合法空洞。
- `make test` 通过 174/174；`make selfhost-native` 固定点 14/14、自解析 64 个源文件、语法/运行语料、模块 17/17、项目 82/82 全通过。种子滚动与冷编结果见[完成记录](01-finished/yh-编译期typed结构体定长数组字段-2026-10-06.md)。

## 2026-10-06 typed SSA 整数转换与 C ABI 项目门修复

- typed SSA 增加整数 `CAST`、常量规范化与 ARM64 发射；混合宽度整数运算按前端 `sem_promote` 插入转换，窄整数 C ABI 函数进入 SSA。
- 新增 run/81，C ABI 项目门检查至少 3 个 SSA 函数和至少 3 条转换指令；不降低原项目门槛。
- `make test` 通过 173/173；`make selfhost-native` 固定点 14/14、自解析 64 个文件、模块 17/17、项目 82/82 全通过。种子未修改，未执行 `make seed`。
- 设计与测试范围见[实施方案](02-plan/yh-typed-IR整数转换首片实施方案.md)和[完成报告](01-finished/yh-typed-IR整数转换首片-2026-10-06.md)。

## 2026-10-05 `@[comptime]` typed `switch` 执行

- typed 执行器复用已绑定 case AST，支持多值 case、default、无匹配时继续执行后续语句；case 块间不 fallthrough，`return/break/continue` 按现有循环 flow 规则传播。
- 新增 run/80 覆盖匹配/default、无 default、return 和外层循环 break/continue；`make` 与 `make test` 通过，语法 71/71 + 44/44，运行语义 172/172。
- `make selfhost-native` 固定点 14/14、自解析 64 个文件、模块 17/17 均通过，项目门 81/82；唯一失败为 C ABI 项目已有 `ir_functions >= 3` 断言实际得到 2。未滚种子。详见[实施方案](02-plan/yh-编译期typed-switch实施方案.md)。

## 2026-10-05 普通函数编译期 `$for` typed AST 模板首片（后续已修复）

- 普通函数中兼容 `$for` 循环体由 SSA 按编译期区间复用单份 typed AST，预算按逻辑实例节点计费；`make`、`make test` 和模板项目通过。`make selfhost-native` 为 81/82，唯一失败是 C ABI 项目原有 `ir_functions >= 3` 断言实际得到 2。
- 曾在主门未全绿时误执行 `make seed`，当前种子哈希为 `0e6088ab94183149d84d3683baf01e733dd9ced71f9ed3c3b6d3bafd78609b3e`；任务开始时 `72c31036fba6e180e9aa4bda0935408055c8740f19e9bf7c1ad29a60bf1fe5ee` 的文件副本未能恢复。此处记录为未完成验收，不声称种子滚动有效。详见[实施记录](01-finished/yh-普通函数编译期for-typed-AST模板首片-2026-10-05.md)与[后续方案](02-plan/yh-普通函数编译期for-typed-AST模板实例化方案.md)。

## 2026-10-05 普通函数编译期展开 typed AST 首片

- 模块 worker 将普通 `$if/$for` 的实际选中展开结果保存在 typed AST；SSA flatten 其编译期包装语句，`$for` 每轮的只读常量获得独立稳定绑定编号。
- AST 捕获路径按新增表达式、语句和绑定节点累计限制 100000；单文件暂时保留 token 预算。此首片仍逐轮重解析，尚未完成 AST 模板克隆与所有入口统一。
- 新增 run/79、`comptimeexpanded` SSA 项目，以及 `comptimeexpandedfail` 精确节点预算检查。`make test` 通过（语法 71/71 + 44/44，运行 171/171）；`make selfhost-native` 通过（14 项固定点一致、自解析 63 个文件、模块 17/17、项目 82/82）。滚种子后冷编与种子校验通过。
- 新种子 SHA-256：`72c31036fba6e180e9aa4bda0935408055c8740f19e9bf7c1ad29a60bf1fe5ee`。完整边界见[首片记录](01-finished/yh-普通函数编译期展开typed-AST首片-2026-10-05.md)。

## 2026-10-05 编译期 typed 嵌套整型结构体字段完成

- 本地结构体字段可再包含具名结构体；typed IR 支持嵌套字面量、链式整型成员读写和递归按值复制，复制后的嵌套修改不会串回原值。
- 新增 run/78，扩展 `comptimelocal` 跨源文件用例；数组/切片、指针和联合体字段仍被拒绝。
- 验证：`make test`（语法正例 71/71、反例 44/44，运行 170/170）；`make selfhost-native`（固定点 14 项一致、自解析 63 个源文件、模块 17/17、项目 80/80）；滚种子、冷编与 SHA-256 校验通过。
- 新种子 SHA-256：`10234e48c8aa64ae727aa9415db96882633ca304701d7509c82c2c9f579c8ac8`。详见[完成记录](01-finished/yh-编译期typed嵌套结构体字段-2026-10-05.md)与[方案](02-plan/yh-编译期typed嵌套结构体字段方案.md)。

## 2026-10-05 编译期 typed 本地整型字段结构体值完成

- typed IR 支持本地具名结构体的命名/位置式字面量初始化、整型成员读取和写入，以及复制后的独立值语义；字段初始化表达式按源码顺序求值。
- 新增 run/77、fail/102，并扩展 `comptimelocal` 跨文件结构体调用；联合体、嵌套聚合、非整数字段、聚合参数/返回及成员取址仍未开放。
- 验证：`make test`（语法正例 71/71、反例 44/44，运行 169/169）；`make selfhost-native`（固定点 14 项一致、自解析 63 个源文件、模块 17/17、项目 80/80）；滚种子、冷编与 SHA-256 校验通过。
- 新种子 SHA-256：`b0284f3481cfeb97e10d6bbcd8db62707d9f81945375cf0edcd457b2f6eb8905`。详见[完成记录](01-finished/yh-编译期typed结构体字段-2026-10-05.md)与[方案](02-plan/yh-编译期typed结构体字段方案.md)。

## 2026-10-05 编译期 typed 数组/切片表达式完成

- typed IR 支持本地整型数组/切片的 `base[start..end]` 共享存储视图，校验两端边界，支持嵌套视图、别名写入、for-in 和反向空范围。
- 新增 run/76、fail/101，并扩展 `comptimelocal` 跨文件切片视图回读；指针、全局聚合和非整型元素仍未开放。
- 验证：`make test`（语法 71/71 + 44/44，运行 167/167）；`make selfhost-native`（固定点 14 项一致、自解析 63 个源文件、模块 17/17、项目 80/80）；滚种子后冷编、SHA-256 和 `git diff --check` 通过。
- 新种子 SHA-256：`f1b30a172396387e59d055d47c2dd960dd71749fc378aaeebfd71610f66ff452`。详见[完成记录](01-finished/yh-编译期typed数组切片表达式-2026-10-05.md)与[方案](02-plan/yh-编译期typed数组切片表达式方案.md)。

## 2026-10-05 编译期 typed 数组/切片下标写入完成

- typed IR 为赋值目标增加局部槽/聚合元素位置；本地整型数组/切片支持下标 `=` 与整数复合赋值，读取和写入共用基址、元素类型及边界检查。
- 新增 run/75、fail/100，并扩展 `comptimelocal` 跨文件数组元素写入回读；不支持指针、切片表达式、聚合参数/返回及其他聚合值。
- 验证：`make test`（语法 71/71 + 44/44，运行 165/165）；`make selfhost-native`（固定点 14 项一致、自解析 63 个源文件、模块 17/17、项目 80/80）；滚种子后冷编、SHA-256 和 `git diff --check` 通过。
- 新种子 SHA-256：`0668cce1cc7708c026e3cace56d43de8979a26769fb75a5d0ce0de13fd3d9220`。详见[完成记录](01-finished/yh-编译期typed数组切片下标写入-2026-10-05.md)与[方案](02-plan/yh-编译期typed数组切片下标写入方案.md)。

## 2026-10-05 编译期 typed 数组/切片下标读取完成

- typed IR 支持从本地整型数组/切片读取元素，可使用局部整数下标；负下标及上下界之外的下标在执行时拒绝，并验证聚合长度和元素类型。
- 新增 run/74、fail/98、fail/99，并扩展 `comptimelocal` 跨文件下标读取回归；下标写入、指针、切片表达式及其他聚合仍未开放。
- 验证：`make test`（语法 71/71 + 44/44，运行 163/163）；`make selfhost-native`（固定点 14 项一致、自解析 62 个源文件、模块 17/17、项目 80/80）；滚种子后冷编、SHA-256 和 `git diff --check` 通过。
- 新种子 SHA-256：`662df8951522bfc6df4e217b6a22003eb76cbe83a7f91ce3d110eab8b63ff4a5`。详见[完成记录](01-finished/yh-编译期typed数组切片下标读取-2026-10-05.md)与[方案](02-plan/yh-编译期typed数组切片下标读取方案.md)。

## 2026-10-05 编译期 typed 整型数组/切片 for-in 完成

- typed IR 在调用帧内存储整型数组/切片字面量，支持普通 for-in 元素与可选下标绑定、空切片和循环跳转，并在帧退出时释放聚合临时值。
- 修正声明解释器选择初始化器的方式：固定数组类型的长度表达式 `[N]` 不会再被误认作局部变量初值；数组元素链改为迭代遍历。
- 新增 run/73 与 `comptimelocal` 跨文件固定数组回归。聚合参数/返回、索引读写、结构体/联合体和浮点元素仍未开放。
- 验证：`make test`（语法正例 71/71、反例 44/44，运行 160/160）；`make selfhost-native`（固定点 14 项一致、自解析 62 个源文件、模块 17/17、项目 80/80）；滚种子后冷编 `make`、SHA-256 和 `git diff --check` 通过。
- 新种子 SHA-256：`d5e022bcfdf5db7fd3cba122ece8f2cb74a7d0ec5735a2fbddcccea1561478ce`。详见[完成记录](01-finished/yh-编译期typed整型聚合for-in-2026-10-05.md)与[方案](02-plan/yh-编译期typed整型聚合与for-in方案.md)。

## 2026-10-05 编译期函数 typed 整数区间 for-in 完成

- typed IR 执行普通整数区间 for-in，支持元素/零起始下标绑定、空范围、break/continue/return，并共用解释器步预算；前端仍负责边界表达式的解析、类型检查和绑定。
- 新增 run/72，扩展 `comptimelocal` 跨文件项目；数组/切片 for-in 和聚合值仍待 CT3 后续阶段。
- 验证：`make test` 语法 71/71 + 44/44、运行 159/159；`make selfhost-native` 固定点 14 项一致、自解析 62 个文件、模块 17/17、项目 80/80 及其余探针通过；滚种子后冷编与哈希校验通过。
- 新种子 SHA-256：`eba461e71044ff9a22bdbf7f9c14e4a753d1232decb1969ab25f02ccb0c24d91`。详见[完成记录](01-finished/yh-编译期函数typed区间for-in-2026-10-05.md)与[实施方案](02-plan/yh-编译期函数typed区间for-in实施方案.md)。

## 2026-10-05 编译期结构展开规模预算首片完成

- 普通函数 `$for` 的展开保护除总轮数外，现在还按每轮主体 token 数累计展开规模；超 100000 时在继续解析/发射该轮前拒绝。单区间 1024 轮及全单元 100000 轮限制保留。
- 新增 fail/97；旧版会错误编译通过，新版按规模预算拒绝。该 token 上界在嵌套循环中可能超计，精确 typed AST 实例节点预算仍待迁移阶段。
- 验证：`make test` 语法 71/71 + 44/44、运行 158/158；`make selfhost-native` 固定点 14 项一致、自解析 62 个文件、模块 17/17、项目 80/80 及其余探针通过；`make seed` 后冷编及哈希校验通过。
- 新种子 SHA-256：`8b2a0fb5215ded91141386d2fb823c424c0cdf510d0bd5e3b1c0d841e3b59850`。详见[结构展开规模预算首片记录](01-finished/yh-编译期结构展开规模预算首片-2026-10-05.md)与[typed AST 后续方案](02-plan/yh-编译期结构展开规模预算首片方案.md)。

## 2026-10-05 编译期 typed 函数调用表达式语句完成

- 修复 typed IR 将 `AST_STMT_EXPR` 当作空操作的问题。现在会求值表达式语句，因此丢弃结果的 `$g(...)` 仍执行被调函数里的 `$assert/$compile_error/$compile_warn`，并遵从当前分支和短路路径。
- 新增 fail/96：`@[comptime]` 函数通过表达式语句调用另一编译期函数，断言失败必须使外层常量求值失败。
- 验证：定向复现从意外成功转为预期诊断；`make test` 语法 71/71 + 44/44、语义 157/157；`make selfhost-native` 通过（14 个模块产物固定点一致、自解析 62 个文件、模块 17/17、项目 80/80）；`make seed` 后冷编 `make` 与 SHA-256 校验通过。
- 新种子 SHA-256：`6cc4db26bfca8d0409d8ca717736b54ade5f119b1456908ee3ff56b5cc8ad894`。
- 详见[typed 函数表达式语句完成记录](01-finished/yh-编译期typed-函数表达式语句-2026-10-05.md)。

## 2026-10-05 编译期 typed 函数内 `$for` 完成

- `@[comptime]` 函数准备期保存两个边界、只读 `i32` 迭代绑定和一次解析的循环体；执行器按当前调用帧
  的边界逐轮执行 `[lo..hi)`，可嵌套 typed `$for`、读取外层迭代绑定并执行循环体中的 typed `$if`。
  空范围不执行循环体，普通函数 `$for` 静态展开规则保持不变。
- 新增 run/71，覆盖参数/局部边界、累加、嵌套区间、空范围、未选诊断和恰好 1024 次；fail/94 验证只读绑定，fail/95
  验证超过单区间 1024 次时拒绝；`comptimelocal` 增加跨文件编译期函数动态区间调用。
- 验证：`make test` 语法 71/71 + 44/44、语义 156/156；模块项目 80/80；`make selfhost-native`
  两代固定点 14 项一致、自解析 62 个文件、模块语法 17/17、项目 80/80 及其余探针全通过。
  随后 `make seed` 与冷编通过，种子 SHA-256 为
  `13e3505c907bd6077e460e154a243c70fc20d196357bde51256c5aeeb8f0927e`。
- 详见[typed 函数内 `$for` 实施方案](02-plan/yh-编译期typed-函数内for实施方案.md)与
  [完成记录](01-finished/yh-编译期typed-函数内for-2026-10-05.md)。

## 2026-10-05 编译期 typed 函数内 `$if` 完成

- `@[comptime]` 函数准备期保存 `$if/$else` 双支 typed 节点，调用时按本次参数或局部值选择；
  两支均做名字/类型检查，未选分支诊断不触发，无 `$else` 时假分支继续执行后续语句。
  普通函数常量 `$if` 与顶层控制规则保持不变。
- 新增 run/70、fail/93 及同模块多文件选支回归，覆盖参数条件、局部条件、无 `$else`、
  未选分支错误和两支名字检查。
- 验证：`make test` 语法 71/71 + 44/44、语义 153/153；`make selfhost-native` 两代固定点
  14 项一致、自解析 62 个文件、模块语法 17/17、项目验收 80/80，其余探针通过；滚动种子
  冷编和 SHA-256 检查通过。
- 详见[typed 函数内 `$if` 记录](01-finished/yh-编译期typed-函数内if-2026-10-05.md)。

## 2026-10-05 编译期 typed IR 诊断语句完成

- typed IR 支持的 `@[comptime]` 函数现在直接执行 `$assert/$compile_error/$compile_warn`；
  `$assert` 条件连到 typed 表达式边并读取局部帧，消息和位置来自函数源码快照，诊断只在
  实际执行路径上触发。前端语句节点登记诊断类别，结构化 `$if/$for` 仍走既有编译规则。
- 新增 run/69、fail/92 和跨文件模块局部值断言；新增用例验证局部循环后成功/失败断言、
  未选分支错误不触发及警告位置。
- 验证：`make test` 语法 71/71 + 44/44、语义 151/151；`make selfhost-native` 两代固定点
  14 项一致、自解析 62 个文件、模块 17/17、项目 80/80，其余探针通过；滚动种子冷编及
  哈希校验通过。
- 详见[typed IR 诊断语句记录](01-finished/yh-编译期typed-IR诊断语句-2026-10-05.md)。

## 2026-10-05 编译期 typed IR 与局部循环首片完成

- 单文件与模块 worker 均在全局初始化前准备 `@[comptime]` 正文，并将前端类型化表达式、
  语句、控制流边和稳定局部绑定复制到 comptime 私有 arena。typed 执行器覆盖局部标量、
  直接赋值、if/条件 for、跳转、返回、嵌套编译期调用和共享执行预算。
- 新增 run/68 局部循环用例和 `comptimelocal` 跨文件模块项目；诊断、结构化 `$if/$for`、
  for-in、一般左值及剩余节点仍待迁入 typed IR，CT3 总体未完成。
- 验证：`make`、`make test`（71/71 + 44/44 语法、149/149 语义）、模块项目 80/80；
  `make selfhost-native` 两代固定点 14 项一致、自解析 62 个源文件、模块 17/17、项目
  80/80 及其余探针全通过。随后 `make seed` 和滚动种子冷编/哈希检查通过。
- 详见[首片完成记录](01-finished/yh-编译期typed-IR与局部循环首片-2026-10-05.md)。

## 2026-10-03 sys 标准库系统调用封装规划交付

- 实现位置指定为 `libs/sys/`，交付
  [模块 README](../libs/sys/README.md)、
  [设计](03-design/yh-sys系统调用封装设计.md)与
  [SYS0–SYS7 实施方案](02-plan/yh-sys系统调用封装实施方案.md)。
  首期 Linux/arm64 直接 syscall，明确 `-errno`、21 个具名原语、
  文件/目录、内存/时间、进程及消费者迁移和独立自举门；Darwin OS 桥后续实施。
- 同步标准库设计与 TC6 工具链方案，todo 记录未实施阶段。旧 prelude、
  自有入口和静态链接的剩余工作单独列明，不把导入 sys 当作已经脱离全部依赖。
- 文档链接/围栏/空白/阶段及 diff 检查通过；源码基线未变更。
  本轮仅文档规划，未新增 `.yh` 实现或测试，未执行构建/运行门，未滚种子。
  详见[规划完成记录](01-finished/yh-sys系统调用封装规划交付-2026-10-03.md)。

## 2026-10-03 extern 自动 C ABI 完成

- `@[extern]` 函数自动分类固定参数、入口和返回，支持现有 C 标量、非空
  extern struct/union、小聚合/HFA、大聚合、浮点/窄参数栈溢出与函数指针返回。
  共享分类器区分 Linux 与 Darwin 栈布局，普通 yh ABI 保持现状。
- 函数类型保存调用约定，新增 `@[extern] fn(...)`；回调变量、共享字段及
  跨模块接口均保持 ABI，C/yh 函数类型互赋与改变约定的函数类型转换拒绝。
  IR 序列化版本升为 5，前端缓存键版本升为 10，SSA 整数路径共用分类器。
- 修复双向探针发现的浮点赋值临时槽跨帧复用崩溃，新增复现用例。标准库
  清单中的未支持规划字段保留为注释，使标准库项目验收恢复通过。
- 验证：`make` 成功；`make test` 语法各 68/68+42/42、语义 100/100；
  `make selfhost-native` 退出 0，12 个模块产物固定点一致、54 个源文件自解析
  通过、模块 17/17、项目 79/79。Darwin 与静态 Linux/AArch64 的独立 C
  双向调用退出 0；ELF 无动态解释器、动态依赖或未解析符号。
- 完成记录：[extern 自动 C ABI](01-finished/yh-extern自动C-ABI-2026-10-03.md)。
  C 变参、C 数据符号、Linux 原生种子与 libc 主体仍按独立方案推进；未滚种子。

## 2026-10-03 yh-asm 独立项目 TC1–TC2 竖切片完成

- 按用户决定，yh-asm/yh-link 工具链在仓库根 `asm/` 独立立项（模块与
  实施方案的 compiler/obj|asm|link 对应）。交付 TC1 obj 二进制模型
  （小端读写/增长缓冲/名字池/节/符号/重定位）与 TC2 竖切片：扫描器、
  解析器、AArch64 整数/访存/分支编码、回填收尾与符号落表；ELF 出口（TC3）
  未实现。详见当时的 asm/README.md（那一代实现在 2026-10-07 项目归位时被
  现役实现取代，副本见 `tmp/removed-2026-10-07/asm-legacy/`）与
  [完成记录](01-finished/yh-asm独立项目TC1-TC2竖切片-2026-10-03.md)。
- 测试：94 正例（期望机器字经 clang aarch64 独立汇编器提取，oracle 证据
  在 tmp/yh-toolchain/oracle/）+ 20 负例 + 1 端到端共 115 项全绿；
  独立验收门 `python3 asm/tests/check.py`（当时的驱动，随之归档）。
- 修复阻塞开发的编译器缺陷：十六进制字面量含 E/e 误判浮点
  （compiler/gen/sem_value.yh），补 tests/yh 与 tests/yh-run/55 语料。
- 发现并登记四项编译器缺陷（项目模式 SSA 混合宽度、结构体指针加法
  缩放、局部数组变量下标取址、跨模块字段类型不计导入使用）于 todo.md，
  asm/ 内按约定规避。
- 门禁：`make` 成功；`make test` 全绿（68+42 语法、99/99 运行）；
  `make selfhost-native` 其余门全绿，模块项目 76/79——3 项失败经对照
  复测确认为工作区既有问题（未跟踪 libs/ 的 TOML `//` 注释 ×2、
  r2a-ssa-direct-call-abi 第九参数进行中工作），与本轮无关。未滚种子。

## 2026-10-02 yh-asm 与 yh-link 详细规划交付

- 用户确认 Linux/AArch64 优先、macOS/arm64 随后。新增
  [设计](03-design/yh-asm与yh-link设计.md)、
  [实施方案](02-plan/yh-asm与yh-link实施方案.md)与
  [规划交付记录](01-finished/yh-asm与yh-link规划交付-2026-10-02.md)，
  TC0–TC10 未实施，已登记 todo；既有 R4/R5 添加详细方案入口。
- 明确标准 `.s → .o → 映像`、内部 API/独立命令共用实现，Linux 静态 ELF、
  OS 桥/原生种子/连续自编门、有限 C 对象与归档分支，以及 Mach-O 装载/导入/签名。
- 59 个运行/通过用例分别在 Linux、Darwin 发射成功，各 59/59；记录当前
  自编汇编缓存与源码审计，并识别宿主 I/O 与目标方言混用的前置问题。
- 本轮只修改规划文档；`make` 成功并校验种子哈希，现有产物已是最新状态，
  未冷编、未重跑 test/selfhost-native、未滚种子。文档检查见规划交付记录。

## 2026-10-02 yh 混合参数调用修复完成

- 修复 libc 分析发现的十个交错参数 yh → C 调用错误，按整数与浮点
  独立寄存器分类；混合实参只弹栈一次，整数溢出栈槽按整数顺序回填。
  实施见[修复方案](02-plan/yh-混合参数调用修复方案.md)与
  [完成记录](01-finished/yh-混合参数调用修复-2026-10-02.md)。
- 新增 `.yh` 回归覆盖十个交错参数、三个非连续整数栈参数、函数指针、
  嵌套调用与浮点类型化变参；第九个浮点实参明确拒绝。C 混编项目补
  十参数/十四参数双向调用，以不同权重验证顺序。
- 原探针和正式 C 回归均交叉静态链接后在 Linux/AArch64 容器原生运行，
  旧编译器返回 41，新编译器返回 0；ELF 无解释器、动态依赖或未定义符号。
- `make` 冷编成功；`make test` 两层语法 67/67、39/39，语义 92/92；
  `make selfhost-native` 返回 0，12 个模块产物固定点、52 个源文件
  自解析、模块语法 17/17、项目验收 78/78 及其他自举探针全部通过。
  本轮未执行 `make seed`。

## 2026-10-02 yh libc 可行性与阻塞点分析完成

- 用户确认目标为 Linux/AArch64 独立链接、兼容 C ABI；交付
  [分析报告](01-finished/yh-libc可行性与阻塞点分析-2026-10-02.md)与
  [分阶段候选方案](02-plan/yh-libc分阶段候选方案.md)，实施项记录在 todo。
- 对照 musl 1.2.6（`9fa28ece75d8a2191de7c5bb53bed224c5947417`）源码，
  区分已具备的固定标量/原始 syscall/自有字节运行时，以及变参、聚合、
  数据符号、TP/原子/上下文、binary128、库交付和动态装载缺口。
- 临时 C 调用方通过 yh 导出的字符串、九整数参数和混合浮点函数；使用
  自编最小汇编入口、Zig cc `-nostdlib -static` 链接，在现有 Linux/AArch64
  Ubuntu 容器中输出 `libc-probe\n`、退出 0。ELF 无解释器、动态依赖和未定义符号。
- 另复现十个交错整数/浮点实参的 yh → C 调用错误：编译/链接成功，C → yh
  通过，反向得到错误结果并返回 41；定位调用点按总实参数计算栈槽，尚未修复。
- 探针确认 C 裸变参、结构体返回、pub let 与 f128 被拒绝；无 main 的库项目
  可生成 `.s/.s.i`。源码镜像和所有临时产物均在 `tmp/libc-analysis/`。
- `make` 成功且种子哈希验证通过，产物已是最新状态；本轮仅新增分析文档，
  未修改编译器/语法/入库种子，未重新冷编或重跑全量自举门。

## 2026-10-02 属性系统与 C 互操作统一实施完成

按用户授权完成[统一实施方案](02-plan/yh-属性系统与C互操作统一实施方案.md)：
单组 `@[extern, noreturn]` 属性列表，删除 `heap`，内存分配留待显式语法另行
设计；本轮保留 yh runtime `printf`，未开放用户 C 裸变参。

- `docs/yh.g4` 与词法/解析索引支持单组多属性；语义检查未知、重复、错配与
  不合法原型。`extern` 函数无体时引用 C 符号，有体时定义裸名 C 函数；
  外部数据类型共享布局，opaque struct/union 仅可经指针使用。
- C ABI 与 yh 模块导入标记分离。固定参数边界覆盖布尔、窄/宽整数、指针、
  浮点、外部枚举和受限回调；数组、切片与结构体按值边界拒绝。接口保留无属性
  v1，属性行使用 v2，属性改变会更新接口和调用方 IR。
- `noreturn` 贯通定义检查、SSA unreachable、调用方终止及后端 trap。`inline`
  已接入受限小型标量 SSA 内联；复杂控制流、调用、取址、公开跨模块形态保留
  普通调用，参数副作用保持一次，callee 函数体纳入调用方缓存键。
- `[c]` 项目配置支持依赖项目中的 C 源、预编译对象和系统库；C 源每次构建
  重编，源/头文件变化反映到对象，预编译对象内容变化触发重链接；无效 C 源
  不复用旧对象，路径含空格使用显式 argv。
- 测试包括 C/YH 双向九参数和窄标量调用、浮点、回调、共享 struct 的
  `sizeof/offsetof`、头文件和对象缓存变化，以及 inline/noreturn 的 IR/汇编证据。
- 验证：`make`、`make test`（语法 67/67 正例、39/39 反例；运行/失败/通过
  语料 50/32/8，全计 90/90）、模块项目验收 74/74、`make selfhost-native`
  退出码 0；cc3→cc4 的 12 个模块产物固定点一致、52 个源文件自解析通过，
  模块语法 17/17，其他固定点和自有运行时探针通过。仅在当前 Darwin/Mach-O 主机完成原生运行；
  Linux AArch64 原生验收需对应种子和环境。依照方案，本轮未运行 `make seed`。

## 2026-10-02 标准库首期 `libs/io` 实施完成

- 在仓库 `libs/` 初始化 `yh_libs` 项目，新增 `io.write_all`、`io.print` 与
  `io.println`。短写会循环推进；负长度、底层失败或零写入返回 -1。
- 新增 `tests/modules/projects/libsio/` 并接入项目验收，通过
  `YH_STDLIB` 加载仓库真实 `libs` 项目。覆盖实际 stdout、坏 fd、零长度与负长度。
- 跨模块公开类型闭包另有 typeclosure 项目用例；标准库首期使用内建类型，无需
  libc 变参。未实现工具链默认发现路径，仍需显式设置 `YH_STDLIB`。
- 验证：`make test`、`make selfhost-native`、模块项目验收 77/77 与
  `git diff --check` 全绿；未运行 `make seed`。

## 2026-10-02 标准库基础模块扩展完成

- 依用户要求移除标准库项目的 `src/` 布局，`libs/project.toml` 使用 `source = "."`；
  六个模块直接位于 `libs/<模块>/<模块>.yh`。
- 在 `io` 之外新增 `memory`（显式分配、释放、复制）、`string`（长度、相等、字节序比较）、
  `os`（文件描述符、路径和进程接口）、`math`（固定参数 C 数学接口）与 `time`
  （单调时钟）。`printf` 继续走 yh runtime，未开放 C 裸变参。
- 新增 `libsbase` 项目验收，检查模块调用、文件系统副作用清理、错误返回及输出。
- 验证：`make test` 通过（语法 67/67、39/39；运行/失败/通过 50/32/8），模块项目
  验收 78/78，`make selfhost-native` 通过（12 个产物固定点、52 个源文件自解析），
  `git diff --check` 通过。暂不验收跨平台行为；未运行 `make seed`。

## 2026-10-02 属性系统统一方案修订（单组多属性，删除 heap；未实施）

用户确定使用 `@[extern, noreturn] fn c_fatal(code int) void;` 形式，
删除 heap，内存分配后续通过显式声明设计。已修订
[统一实施方案](02-plan/yh-属性系统与C互操作统一实施方案.md)和 todo。

- 每个声明最多一组列表，删除连续多组语法；补充三属性组合矩阵、同组
  重复检查、固定接口输出顺序，以及属性不泄漏到相邻声明的验证。
- 当前只保留 extern、inline、noreturn；撤回 heap 构造/装箱/引用类型
  方案与 H0/H1 阶段，保留现役值语义与 sizeof，未来分配语法独立设计。
- 精简交付边界：U0–U2 为属性/extern/noreturn 核心交付，U3 为项目
  混编，I1 与 NP5 共用实际内联；本条不表示编译器功能已经完成。
- 本次只更新 Markdown 文档，检查本地链接、代码块与 diff 格式；
  没有修改 compiler/、docs/yh.g4、tests/ 或种子，没有运行代码构建/回归。

## 2026-10-02 属性系统与 C 互操作统一方案交付（待评审，未实施）

本条保留初稿交付历史；其中多组语法、heap 与 H0/H1 已被上方修订撤回。

根据用户要求，结合四个属性与旧 FFI 草案，交付
[统一实施方案](02-plan/yh-属性系统与C互操作统一实施方案.md)，同步 todo，
在旧 FFI 草案标记新版参考。本条只记录计划交付，不表示功能已经完成。

- 建议统一使用 `@[...]`；extern 函数无体引用、有体提供 C ABI 定义，
  pub 继续描述 yh 模块可见性；保留 pub 数据类型与 let 不导出的现役规则。
- 修正 F_EXTERN 兼作模块导入、8192 标志已占用、自有 intrinsic 分配器与
  C 同名函数不能幂等合并、>16B HFA 仍有独立 ABI 等假设；引用 Arm/Apple
  官方 ABI 规则。v1 聚合采用指针边界，C 全局通过包装函数访问。
- 规划 U0–U3、H0/H1、I1；heap 指针构造模型待确认，inline 与 NP5 共用
  SSA 内联；每个行为阶段要求新 `.yh` 用例和构建/回归/固定点验证。
- 本次只修改 Markdown 计划与任务记录；核对本地链接及 diff 格式。
  未运行代码构建或回归，未修改 docs/yh.g4、compiler/、tests/ 或种子。

## 2026-10-02 let 不导出：GenState 打包重构 + pub let 废除（两代滚种）

语言规则（用户决策）：let 变量只能是模块变量或函数局部变量，**不支持
导出**（`pub let` 非法）。该规则与编译器自举现实冲突：gen 模块 208 个
跨模块可变全局（c_pos/t_types/p_mods 等）被引用 3054 处。用户在
AskUserQuestion 中选择「GenState 打包（彻底）」路径。

- **方案**：208 个 pub let 收进 `pub struct GenState`（字段一律公开——
  与 struct 一等化规则吻合），gen 私有实例 `g_state` + 导出
  `pub fn G() *GenState { return &g_state; }`（实测 `&全局` + 函数返回
  指针现有机制完全支持，**零新语言特性**；对比 pub const 指针导出方案
  免去「取全局地址作编译期常量 + 数据槽重定位」新机制与接口格式变更）。
- **替换**：gen 内部 1185 处裸引用 → `g_state.x`；跨模块 1869 处
  `gen.x` → `gen.G().x`；cmd/parse 66 个同模块 pub let 直接去 pub；
  9 个非零初始化器迁入 `gen.state_init()`（driver main 入口调用，
  worker fork 继承）；接口发射器停发 SYM_VAR（pub let 行）。
- **暴露既有发射器 bug**：`f().field = v`（函数返回指针接字段写）在
  `sem_member` 的 LVALUE 分支无条件 `ldr x0,[x0]` 多一次间接——该形态
  GenState 之前从未被语言使用，实测最小复现（读写探针 gftest exit=139）
  确认为**既有缺陷**而非重构引入。修复：按进入时的 `c_res_is_addr`
  （基底形态）判据决定是否装载——变量引用/未装载解引用（is_addr=1）
  需 ldr，函数返回的指针（is_addr=0）不得再间接；读路径不变。
- **过渡期源码避让**：v1（旧种子生成）的 cmd 代码含 bug 形态无法运行，
  源码改写为**函数级局部指针**形态（`let gs *gen.GenState = gen.G();`
  + `gs.field`）——186 处函数、覆盖全部原 LVALUE 写与同函数读；脚本
  两次失败（字符字面量 `'{'` 破坏朴素大括号配对、跨行签名插绑定错位）
  后改用「逐行向上找 fn + 感知签名结束行」方案稳定落地。修复后固定点
  通过（源码无 bug 形态，两代产物一致）。
- **语料迁移**：fourdir/fourdirbad 的 `pub let counter` 改为私有
  counter + `pub fn counter_value/set_counter`（跨模块可变状态改函数
  封装的示范）；runtimebytes 的 pub let 仅同模块使用直接去 pub；
  02_pub_export 的 pub let 改 pub const；新增 rejected/35_pub_let；
  g4 重构 topLevelDecl → exportedDeclBody + plainDeclBody（pub 不可修饰
  letDecl）。
- **Gen N-b**：`parse_top_decl` 拒 `pub let`（报错「let 变量不支持
  导出」），接口加载（c_iface_load=1）容忍旧格式 pub let 行以兼容
  持久缓存。
- 验证：每代 `make` + `make test`（正例 66/66、反例 35/35、运行语料
  62/62）+ `make selfhost-native`（固定点、modules 17/17、project
  55/55）全绿后 `make seed`；种子哈希 Gen N-a → eb37868c…、Gen N-b →
  c4168844…。
- 语义边界补充：`&全局` 表达式与函数返回模块内全局地址为现役机制
  （实测 exit=9 验证），GenState 即依赖此实现跨模块状态共享。

## 2026-10-02 enum 同步一等化：pub enum 与成员导出（审计后补齐）

用户要求核查 union/enum 是否与 struct 同步、跨模块 pub 检查是否完备。
审计结论：union 已同步；跨模块 fn/const/struct 检查完备（parse_global_init
置 F_PUB、iface_load 改写符号、引用侧 mod_ns_lookup 校验，实测
`lib.hidden()` 正确拒绝）；**enum 有两处缺口**，本条目补齐：

- **裸 enum 未同步**：struct/union 已强制 pub 而 enum 仍可裸写。
  `parse_top_decl` 补 enum 分支校验（报错「enum 必须带 pub」）；语料
  3 文件裸 enum 迁移为 `pub enum`；新增 rejected/34_bare_enum；
  docs/yh.g4 的 plainDeclBody 移除 enumDecl（enum 只能经 pub 进入）。
- **pub enum 成员不导出**：`parse_enum_decl` 成员常量只登记 F_GLOBAL，
  跨模块 `lib.red` 报「模块没有导出该名字」。成员按枚举的 pub 置 F_PUB
  进入接口名字表；`iface.yh` 常量发射循环跳过 TY_ENUM 常量——成员已随
  pub enum 体导出，否则接口重复登记、加载侧报重定义。
- 新增 `tests/modules/projects/enumexp/` fixture（lib：pub enum Color/
  pub const/pub struct/pub fn；host：跨模块成员引用、判别值断言、字段
  访问），build-check 注册 `u4-enumexp-run`（退出码 10）。临时探针实测
  全链路：`lib.red`/`lib.green`/`lib.PI2`/`b.w` 引用通过，
  `lib.hidden()` 构建期拒绝。
- compiler 源码无 enum 声明、无字段 pub，滚种固定点不受本条目影响。
- 验证：`make` + `make test`（正例 66/66、反例 34/34、运行语料 62/62）
  + `make selfhost-native`（modules 17/17、project cases 55/55 含
  enumexp）全绿后 `make seed`（bin/yh → 964db00a…）。

## 2026-10-02 struct 语法收紧：pub struct 一等化（三代滚种）

规则（用户决策）：① 裸 `struct`/`union` 非法，必须写 `pub struct` /
`pub union`；② `pub struct` 字段一律公开（用户示例 `pub struct IRType {
kind int; ... }` 为唯一正确形式），字段级 `pub` 前缀在用户源码中报错；
③ 类型声明禁止嵌套——fn 体内 struct/union/enum/type 声明特性移除，
`c_nested_type` 机制删除。enum/type 的顶层 pub 可选性不变。

- **接口传递闭包（先行一代）**：`pub struct` 一等化后接口正文首次出现
  「字段引用外模块类型」的 mangle 名（如 AstIRBuilder 字段 `*ir.IRInst`），
  而构建器原先只加载直接 import 的接口，stage1 必卡死。重写
  `cmd/module_build.yh` 的 `mb_module_iface_deps` 为四步：直接导入 →
  传递闭包（绑定名取 mangle 后缀，不与源码别名冲突）→ 按 `pj_order`
  拓扑排序 → 统一构造会话接口路径；抽出 `mb_dep_push` 去重追加。单独
  全绿后滚种（bin/yh → 0b8b85a3…）。
- **语法收紧一代**：`parse_top_decl` 拒裸 struct/union；`parse_stmt`
  拒 fn 内类型声明；`sem_add_field` 去 is_pub 参数（is_pub 恒 1），
  删 `sem_expr`/`sem_call_literal`/`parse_expr` 三处跨模块字段 pub 检查
  与 `sem_struct_lit_begin` 的 named 参数；删 `c_nested_type`；
  docs/yh.g4 重构 topLevelDecl（struct/union 只能经 pub 进入）；compiler
  源码 4 处裸 struct 转 pub struct 并为 ast_ir/ast_ir_build/project/clock
  字段补前缀（旧种子发射器按 is_pub 过滤，前缀是固定点一致的前提）；
  语料 31 文件裸 struct→pub struct、14 文件字段前缀删除；
  run/44-nested-decl 移除并新增 rejected/30_bare_struct、
  31_bare_union、32_nested_type_decl；pubpriv host/host3 由 fail 转 run
  正向用例（u3-pub-field-access=2、u3-positional-pub-construct=1），
  fourdirbad 改验非导出函数（p2-fourdir-nonpub-symbol）。全绿后滚种
  （bin/yh → 0b4212ca…）。
- **前缀移除一代**：`parse_struct_decl` 字段位 TK_PUB 在用户源码报错
  「字段一律公开，不接受 pub 前缀」；接口加载（c_iface_load=1）仍按
  yh-iface v1 格式跳过字段 pub 标记——接口格式零变动，cc3/cc4 产物
  才能逐字节一致；compiler 源码 248 处字段前缀全删；新增
  rejected/33_field_pub_prefix。全绿后滚种（bin/yh → 762d3ce5…）。
- 文档同步：docs/yh.g4（topLevelDecl/plainDeclBody/structDecl/unionDecl/
  fieldDecl）、03-design/模块与项目管理设计 §可见性、03-design/00-语义边界
  §3、compiler/README 无需改动；历史方案文档（02-plan 模块实施方案、
  03-design/Go风格模块与包设计）自带"已被替代"抬头，保留原状。
- 验证：每代 `make` + `make test`（ANTLR 正例 66/66、反例 33/33，
  编译器语法门同，运行语料 62/62）+ `make selfhost-native`（含固定点、
  模块/项目验收 54/54）全绿后 `make seed`；三代种子哈希如上，git 历史
  保留各代产物。

## 2026-10-02 Makefile 清理失效的 VERSION 引用

- VERSION 文件已随清单精简删除（c5eccf0，版本改由 project.toml 提供），
  Makefile 头部 `VERSION ?= $(shell cat $(TOPSRC)/VERSION)` 成为无效
  引用（每次 make 触发一次失败的 cat），已删除该行；全仓库确认
  tools/tests/CI 无其他 VERSION 文件引用。
- 验证：`make` 通过，`make test` 运行语料 63/63。

## 2026-10-02 修复裸调用 SIGBUS：usage() 栈缓冲区溢出

- 缺陷：`cmd/driver.yh` 的 `usage()` 把 10 行用法（566 字节）拼进 512 字节
  栈缓冲，溢出 54 字节砸坏返回地址，函数返回时 PC 未对齐触发 SIGBUS
  （退出码 138）。裸调用、坏参数及全部 4 个 usage 调用点均崩；缺陷已随
  上一版滚入种子 bin/yh，主门从未执行该路径故未发现。
- 修复：`usage()` 改为逐行写入（复用 256 字节缓冲，单行最长约 80 字节），
  消灭"文本总量超过固定缓冲"一类问题，注释标明不可改回整段拼接。
- 回归防护：主门 `native-selfhost.py` 新增 CLI 冒烟探针——裸调用与坏参数
  必须打印完整用法（含末行）并以用法错误码 2 退出。
- 验证：`make` 通过；裸调用/坏参数 exit=2；`make selfhost-native` 通过
  （固定点 12 产物一致、自解析 49 文件、CLI 冒烟 OK、语法反例 29/29、
  运行语料 63/63、modules 17/17、项目用例 54/54）。未滚种子。

## 2026-10-02 IR 并入编译器根项目普通模块

- `compiler/ir/` 取消独立清单：删除 `ir/project.toml`，移除根
  `compiler/project.toml` 的 `[dependencies] ir = { path = "ir" }`；
  `ir` 与 gen/lex/parse/cmd/backend 同为根项目普通模块，`import ir` 由
  本项目层直接解析。原独立项目对「ir 不依赖 gen/parse/backend/cmd」的
  机器强制分层改为约定维持（各设计文档已同步）。
- `tests/modules/build-check.py`：`irverify`/`irfront` fixture 拷入
  `compiler/ir` 源码后合成最小清单（name = `yh_ir`），跨项目依赖解析
  用例保持有效。
- 文档同步：README、compiler/README.md（模块列表与源码规模）、AGENTS.md、
  Makefile 头注释、编译流程重规划（设计/实施方案）、Nanopass 架构。
- 验证：`make` 通过；`make selfhost-native` 通过（cc3→cc4 12 个模块产物
  固定点一致、自解析 49 文件、语法反例 29/29、运行语料 63/63、
  modules 17/17、项目用例 54/54）。未滚种子（bin/yh 保持上一版）。

## 2026-10-02 编译流程重规划 R2a：短路求值切片

- typed SSA 与 arm64 后端接入逻辑或/与/非：`a || b`、`a && b` 降为
  条件块 + 右臂块 + 合流块三段 CFG，短路常量定义在条件块内，合流点
  双前驱 phi；嵌套短路的 phi 第二前驱取降低右臂后的实际汇入块。
  表达式降低（`ast_ir_lower_expr`/`ast_ir_lower_call_expr`/
  `ast_ir_lower_assign_stmt`）改为直接接收 builder，使表达式可以
  创建条件块；新增 `ast_ir_b_cond` 统一条件归一化（整数按非零为真），
  `if`/`for` 条件与短路操作数共用；`!x` 降为与 false 常量的相等比较，
  旧语义层把 bool 结果升为 i32 的差异在 IR 层归一。
- verifier 值编号唯一性检查由前缀扫描改为位图标记：构造器允许块区间
  与编号顺序不同后，前缀扫描在乱序布局下会把当前指令误判为重复。
- 过程中发现并修复三处缺陷（均有语料或自举佐证）：嵌套短路 phi 前驱
  错误（verifier 拒绝 `irfront` 逻辑用例）；循环发现趟 builder 未挂
  类型表导致 fork worker 静默 SIGSEGV（单文件模式不受影响，曾长期
  误导定位）；`b_if` 条件归一化补丁静默未落盘致自举 cc3 的
  `is_hex_digit` 校验失败。另修正语料初版一处测试期望错误
  （`logic_guard(0,1,0)` 应为 100）。
- `irfront` 新增 `logic_guard`（短路/混合优先级/逻辑非 4 组断言）：
  56 个 AST 函数上下文 54 个进入 SSA，仅 call_tick（全局赋值）与
  unsigned_score（负数字面量实参）回退；自举 cc3→cc4 自源函数进入
  SSA 的数量由 5 增至 8 并通过固定点。
- 滚种子前 `make`、`make test`、`make selfhost-native` 通过：语法
  66/66+29/29、运行 63/63、12 个模块产物固定点一致、自解析 49 个
  文件、模块 17/17、项目 54/54。种子后 `make` 与 `make selfhost-native`
  再次通过。种子 SHA-256
  `0a28dd5e89d660bd9b215e78504ff54cb9531c6df6f232a6df1f06503b361864`，
  根 `yh` SHA-256
  `17b5afcdde2cd04da259147d5b6f89fa58e2c412e926a50a514ce3a3dffbbf5c`。
  Linux arm64 汇编交叉组装通过，原生链接/运行尚未验收。
- Apple M1 冻结 25 文件语料各测 20 轮，中位数/p95：无改动 40.8/49.5ms、
  单函数修改 743.5/817.8ms、冷编 2203.0/2765.1ms；汇编/链接调用为
  0/0、1/1、4/1。被修改函数本身进入 SSA（ir=1），冷编进入 SSA 的
  自编函数 5→8；端到端与上一轮噪声范围内持平，未证明提速；无改动
  50ms 中位数目标保持达标，200ms/1s 目标未达到。嵌套循环、for-in、
  switch、goto、负数字面量实参、浮点、聚合与间接调用仍走旧发射路径，
  R2a/R2b 整体未完成。
  详见[短路求值报告](01-finished/yh-编译流程R2a-短路求值-2026-10-02.md)。

## 2026-10-02 Nanopass 风格优化架构方案交付

- 用户确认优化扩展与自举稳定优先；核对当前 SSA、verifier、缓存、lowering 与后端源码，并参考 Nanopass 官方介绍与手册。
- 交付[架构设计](03-design/yh-Nanopass风格优化架构.md)、[分期实施方案](02-plan/yh-Nanopass风格优化架构实施方案.md)及[ADR-0011 草案](adr/0011-yh采用Nanopass风格优化阶段契约.md)；提议复用 typed SSA、建立小 pass/阶段契约，随后迁移 Checked/Core 与机器 IR。
- NP0–NP5 已登记 todo，设计状态为待评审，全部实现任务仍未完成。新增文档的本地链接、代码围栏和空白检查通过。本次只改文档，没有修改编译器、用例或种子，没有执行构建/运行回归。

## 2026-10-02 编译流程重规划 R2a：通用构造器与 break/continue 切片

- 受限的固定形态匹配 lowering 替换为通用递归构造器（新文件
  `compiler/parse/ast_ir_build.yh`）：块表动态增长、合流块先分配后填充、
  `ir_verify` 块指令区间改为「互不重叠且恰好覆盖」的覆盖检查。if/else
  任意嵌套与 else-if 链、条件循环、break/continue、return 与顺序语句
  任意组合进入 typed SSA 并由 arm64 后端发射。
- 循环采用两趟协议：发现趟直接在主 builder 上降低体并回滚指令/phi/块/
  调用计数，收集携带绑定、continue/break 站点数与是否贯穿；真实趟按
  事实预留 header phi 输入（入口 + continue×N + 回边），continue 站点
  回填边输入，break 站点值与条件假边在退出块建合流 phi。发现与真实
  降低执行同一份代码，保证结构精确一致。
- 过程中发现并修复三处缺陷（均有运行语料佐证）：if 臂遍历越界把 else
  与后续语句降入同一块；发现趟独立值编号与主 builder 冲突导致含循环
  函数整体回退；发现趟 local_count 泄漏使体内 let 校验失败。
- `irfront` 新增守卫 break 与 continue 用例：55 个 AST 上下文 53 个进入
  SSA（仅全局赋值 call_tick 与含 `||` 的 unsigned_score 回退），
  `loop_break_guard(10)=3`、`(2)=1`、`loop_skip_odd(5)=13`、`(2)=1` 验证
  break/continue 语义与 phi 合流；函数 IR 缓存精确失效断言改为按
  「修改函数 1 + 已知回退数」计期望。
- 滚种子前 `make`、`make test`、`make selfhost-native` 通过：语法 66/66+29/29、
  运行 63/63、12 个模块产物固定点一致、自解析 49 个文件、模块 17/17、项目 54/54。
  种子后 `make` 与 `make selfhost-native` 再次通过。种子 SHA-256
  `96ef0e6c565de0accdf40b71a1748abb91a7c2e97c4d39d6f2fa9d70718be252`，根 `yh`
  SHA-256 `f02b0eac39467c4c09c37561fa65f84c157adec5c201c876149577d81ff22d82`。
- Apple M1 冻结 25 文件语料各测 20 轮，中位数/p95：无改动 42.4/48.5ms、
  单函数修改 671.7/757.4ms、冷编 1890.7/2132.8ms；与上一轮噪声范围内持平，
  未证明提速；无改动 50ms 中位数目标保持达标，200ms/1s 目标未达到。
  嵌套循环、for-in、switch、goto、`||`/`&&`、浮点、聚合与间接调用仍走旧
  发射路径，R2a/R2b 整体未完成。
  详见[通用构造器报告](01-finished/yh-编译流程R2a-通用构造器与break-continue-2026-10-02.md)。

## 2026-10-02 编译流程重规划 R2a：条件循环切片

- typed SSA 与 arm64 后端接入条件循环 `for cond { 顺序体 }`：四块 CFG
  为「入口→循环头（携带值 phi + 条件）→体（顺序语句 + 回边）→退出」；
  体内被赋值的外部绑定在循环头建双前驱 phi，入口输入创建时填写、回边
  输入在体降低后回填，循环后视角恢复为 header phi 值。体内 `let` 每次迭代
  重新定义不参与携带；携带绑定去重上限 16。顺序语句检查/降低抽取为
  `ast_ir_straight_scan`/`ast_ir_straight_emit` 共享辅助，直线行为逐字保持；
  void 函数的循环（裸 return 或隐式结束）同样受支持。体内嵌套控制流、
  break/continue、for-in 与 `for {}` 仍回退旧发射器。
- `irfront` 新增 5 个循环函数：53 个 AST 上下文 51 个进入 SSA，运行结果
  验证计数累加（10）、体内 let（6）、尾随语句继续使用携带值（108）与
  循环调用驱动（3）；汇编断言 `bl log_unit` 三次，`yh check` 仍为 0 个
  IR 函数。
- 滚种子前 `make`、`make test`、`make selfhost-native` 通过：语法 66/66+29/29、
  运行 63/63、12 个模块产物固定点一致、自解析 48 个文件、模块 17/17、项目 54/54。
  种子后 `make` 与 `make selfhost-native` 再次通过。种子 SHA-256
  `fcd79c9f81ec3478e8f448f5e8f180318f3d54b34ef169f7c05f4ad6e584665a`，根 `yh`
  SHA-256 `77c4f336a025a11d6b91d337d306176f77f87ec9add79d4da07c903c44d53447`。
  Linux arm64 汇编交叉组装通过，原生链接/运行尚未验收。
- Apple M1 冻结 25 文件语料各测 20 轮，中位数/p95：无改动 40.0/47.0ms、
  单函数修改 706.4/760.7ms、冷编 1880.1/2151.9ms；汇编/链接调用为 0/0、1/1、4/1。
  与上一轮在噪声范围内持平，本切片未证明编译提速；无改动 50ms 中位数目标
  保持达标，200ms/1s 目标未达到。循环体内嵌套控制流与 break/continue 需要
  动态块构造器，R2a/R2b 整体未完成。
  详见[条件循环报告](01-finished/yh-编译流程R2a-条件循环-2026-10-02.md)。

## 2026-10-02 编译流程重规划 R2a：void 调用与语句级调用切片

- typed SSA、verifier 与 arm64 后端接入 void 返回调用与语句级调用：表达式语句
  （顺序路径与 if/else 分支块）接受已检查的直接调用，void 返回发射无结果 CALL
  并保留副作用与求值顺序，标量返回可被语句丢弃；verifier 值编号改为允许稀疏
  （定义数不超过上界，逐指令范围与唯一性检查不变）。void 函数本身支持裸
  `return;` 与隐式结束，空函数为单块零指令 CFG，后端允许 void 返回与零指令函数。
- `irfront` 新增 5 个函数：48 个 AST 上下文 46 个进入 SSA，运行结果覆盖裸
  return、隐式结束、丢弃标量结果、顺序双调用与分支块「调用 + 赋值」phi 合流；
  汇编断言 `bl log_unit` 两次、`bl log_noop`/`bl discarded_result` 各一次，
  `yh check` 仍为 0 个 IR 函数。`ircallmodule` 的 api 新增公开 void 函数，
  覆盖跨模块 void 调用（SSA 函数数 3→4）、精确重链接与退出码 41。
- 滚种子前 `make`、`make test`、`make selfhost-native` 通过：语法 66/66+29/29、
  运行 63/63、12 个模块产物固定点一致、自解析 48 个文件、模块 17/17、项目 54/54。
  种子后 `make` 与 `make selfhost-native` 再次通过。种子 SHA-256
  `ab1f229f2395a69c7c9e52f9d517b54e64bd8f65c121e81d1b764a9b4baf0ea7`，根 `yh`
  SHA-256 `d261e9b24bfb33cfac4b1662956d67e6492a5316ea63d084eca72eaf79727911`。
  Linux arm64 汇编交叉组装通过，原生链接/运行尚未验收。
- Apple M1 冻结 25 文件语料各测 20 轮，中位数/p95：无改动 40.3/51.3ms、
  单函数修改 748.5/808.6ms、冷编 1963.9/2135.9ms；汇编/链接调用为 0/0、1/1、4/1。
  与上一轮在噪声范围内持平，本切片未证明编译提速；无改动 50ms 中位数目标保持
  达标，200ms/1s 目标未达到。void 分支合流、循环、switch、goto 与间接/浮点/
  聚合/变参调用仍走旧发射路径，R2a/R2b 整体未完成。
  详见[void 调用报告](01-finished/yh-编译流程R2a-void调用与语句级调用-2026-10-02.md)。

## 2026-10-02 编译流程重规划 R2a：直接调用 SSA 切片

- typed SSA、verifier、稳定序列化及双 arm64 后端接通固定参数整数/布尔直接调用；`irfront` 覆盖嵌套、零/九参和副作用顺序，`ircallmodule` 覆盖跨模块实现修改后的精确汇编/重链接。`irverify` 覆盖错型、支配关系与损坏缓存反例。
- 滚种子前 `make`、`make test`、`make selfhost-native` 通过：语法 66/66+29/29、运行 63/63、12 个模块产物固定点一致、自解析 48 个文件、模块 17/17、项目 54/54。种子后 `make` 与 `make selfhost-native` 再次通过；种子 SHA-256 `2232b0ada585e24967d60416e10e6809464f9a67970e307d9a49f43f2d685892`，根 `yh` SHA-256 `4cf8e26837dc5c8625f83b30e01a9c764bc866e06ea7706454c4d631c9c9b47d`。Linux arm64 汇编交叉组装通过，原生链接/运行尚未验收。
- Apple M1 冻结 25 文件语料各测 20 轮，含汇编/链接，中位数/p95：无改动 37.7/54.4ms、单函数修改 728.3/1112.2ms、冷编 2029.0/2371.4ms。旧种子同轮基线分别为 38.9/46.0ms、636.2/711.9ms、1686.0/1776.4ms，本切片未带来可证实的提速；200ms/1s 目标仍未达到。自编项目 528 个函数 AST 上下文仅 5 个进入 SSA，R2a/R2b 整体仍未完成。详见[直接调用 SSA 报告](01-finished/yh-编译流程R2a直接调用SSA-2026-10-02.md)。

## 2026-10-02 编译流程重规划 R2a：整数二元运算切片

- typed SSA 和 arm64 后端新增同类型整数除法、取模、位与/或/异或、左右移位；按有符号性选择指令，默认简化器仅折叠非异常常量表达式。IR 序列化升至 v3、函数缓存键升至 v7；未支持的函数仍走旧发射器。
- `irfront` `.yh` 项目运行用例覆盖负数除法与余数、无符号边界、左右移位、零除数、常量折叠；`irverify` `.yh` 项目拒绝错型运算。项目验收 53/53，`make test` 语法正例 66/66、反例 29/29、运行 63/63，滚种子前后 `make selfhost-native` 均通过（12 个产物固定点、44 个源码自解析、模块 17/17、项目 53/53）；种子后 `make` 通过。
- Apple M1 冻结 25 文件、13,338 行语料 20 轮中位数/p95：无改动 34.3/42.1ms，单函数修改 640.7/718.8ms，冷编 1,695.9/1,976.5ms。无改动低于 50ms，单函数 200ms 与冷编 1s 目标未达。编译器自编项目的 512 个函数 AST 上下文仅 1 个进入 SSA；这次扩展不构成对编译速度提升的证明。
- Darwin arm64 种子 SHA-256：`d47bfeeba494fb12a447736e945f6e377d490b23ab841158e62ae358bdecf113`；根 `yh` SHA-256：`8d981521a9260302091f49ae63711e665ef1c12f20c5457172780d014945573f`。R2a、R2b 及 R0–R6 总体验收继续进行。详见[整数二元运算报告](01-finished/yh-编译流程R2a整数二元运算-2026-10-02.md)。

## 2026-10-02 编译流程重规划 R1：单文件 yh check

- 新增 `yh check <file.yh>`，执行词法和完整单文件语义检查，允许库文件没有 `main`；未声明标识符返回失败。原有 `yh check [module]` 项目入口保持不变。
- 在 `tests/modules/fixtures/` 增加有效/无效 `.yh` 语料；自举门验证检查不产生文件、也不调用 PATH 中的 gcc/clang。修正初始化顺序，保证单文件入口先读源、分配语义表，再词法分析。
- 验证：`make test`（语法正例 66/66、反例 29/29、运行 63/63）、滚种子前后 `make selfhost-native`（12 个产物固定点、44 个源码自解析、模块 17/17、项目 53/53）、种子后 `make` 与 `git diff --check` 全通过。Darwin arm64 种子 SHA-256：`268513c5cfff1af60a16754e0d957ae0e3aadb99cc3758b686e39d21e2ae2f22`；根 `yh` SHA-256：`2fcffbb90d8be4713796ccdb8da713ee549b3ba343cfcaceb3b1a190bcd61040`。
- 本条记录不代表 R1 完成；完整 AST/CheckedFunction 分离、一次解析与任务私有上下文仍待实现。详见[单文件 check 报告](01-finished/yh-编译流程R1单文件check-2026-10-02.md)。

## 2026-10-01 编译流程重规划 R2a：SSA arm64 比较运算切片

- SSA 指令表新增不等及有符号/无符号顺序比较，序列化格式与函数 IR 缓存键升版；arm64 后端从操作数类型选择条件码，默认简化器折叠整数常量比较。`irfront` 覆盖六种比较真假、`u32` 最大值边界及常量比较折叠；20 个 lowering 函数均由 SSA 后端输出，程序退出码为 230。SSA 值临时各占独立栈槽；不支持的函数回退到旧 emitter。
- 修复 fork worker 诊断路径悬空：路径原指向可扩容名字池，池增长后偶发 SIGSEGV。现在 worker 解析前把路径复制到固定缓冲；模块 `.yh` 回归重复构建 8 次，额外 100 次独立构建均保留预期源位置诊断。
- 验证：`make test` 通过（语法正例 66/66、反例 29/29、运行 63/63）；滚种子前后 `make selfhost-native` 通过（12 个模块产物固定点、44 个源文件自解析、模块 17/17、项目 53/53）；种子后 `make` 通过。
- Apple M1 冻结语料 20 轮（中位数/p95）：无改动 36.2/44.3ms，单函数变化 669.5/708.7ms，冷编 1,851.3/2,107.0ms；汇编/链接调用为 0/0、1/1、4/1。无改动目标 50ms 达标；单函数目标 200ms 和冷编目标 1s 未达标。冷编 378 个函数上下文只有 1 个进入 SSA 子集，单函数变化为 0 个。
- Darwin arm64 种子 SHA-256：`27ed8a4c2168076c3e713bf3cd3cae63a96709748acfb514813ab508dbea84a4`；根 `yh` SHA-256：`6870f27cf8afcb95963220ad7a427d3ecc812a3ff0985c41c8113961d0eb8a2a`。
- R2a 与 R2b 整体仍未完成：当前只接通项目模块的窄 lowering 子集；还需完整受检函数、更多 CFG/调用/内存语义、单文件共用后端、平台 ABI 验收、真正线程池与完整函数级缓存。

## 2026-10-01 编译流程重规划 R3：自有运行时与固定点迁移

- arm64 的 `malloc/free/memcpy/strlen` 使用自有汇编入口；Darwin 映射调用审核后的 `mmap/munmap`，Linux arm64 发射对应 syscall。`printf` 已支持 `%%`、整数、字符串和字符，使用分块缓冲及 OS `write`，尚未支持宽度、精度、浮点和 locale。运行时入口只按模块内调用/取址发射，纯程序不会带入映射或输出 OS API。`.yh` 用例覆盖分配、字节函数值、精确格式化输出、长字符串刷新与无运行时调用的导入裁剪。
- 滚种子前后 `make test`、`make selfhost-native` 通过；语法 66/66、反例 29/29、运行 63/63、自解析 43 个文件、模块 17/17、项目 52/52，候选 cc3→cc4 的 10 项产物固定点一致。`tests/selfhost/runtime-memory.py` 确认普通程序与自编编译器不导入 `malloc/free/memcpy/strlen/printf`；Linux arm64 汇编交叉组装无未定义符号。
- Apple M1 冻结语料 25 文件、13,338 行，20 轮中位数/p95：无改动 32.2/37.9ms、函数修改 610.8/643.4ms、冷编 1,686.0/1,824.0ms；汇编/链接调用为 0/0、1/1、4/1。50ms 无改动目标达到；200ms 函数修改和 1s 冷编目标仍未达到。新编译器 SHA-256 `e7ab60114f66b44208abd0aab1bdc037501df15600cac070466deb0e73ef8afd`。
- Darwin arm64 种子 SHA-256：`6498b7282a0d00115912e573a08823de3371024d25c0496b2260bd27a40ce344`。Linux 原生运行、线程 API 和完整导入验收尚未完成；外部汇编/链接仍未替换，R3 与 R0–R6 总体验收继续进行。详见[自有运行时与性能报告](01-finished/yh-编译流程R3自有分配器与性能-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R2b：缓存指纹分块与阶段计时

- 缓存内容指纹改为固定小端 8 字节块混合并升版本，使旧 manifest 自动失效；改用对齐的原生 64 位读取后，`tokenreplay` 新增尾部余数为 7 的 `.yh` 回归源。`yh build --stats` 增加项目装载、模块调度、对象缓存/汇编、最终链接决策和构建内总耗时。Darwin 计时通过允许清单中的 libSystem `clock_gettime` OS API，Linux arm64 使用 syscall；普通构建输出不变。
- Apple M1 冻结 25 文件语料 20 轮中位数/p95：无改动 32.8/37.3ms、单函数体变化 663.2/753.4ms、冷编 1,734.1/1,900.6ms，含真实汇编/链接。无改动内部阶段合计 27.2ms，已达到 50ms 目标；单函数 200ms 与冷编 1s 目标仍未达到。
- `make test` 全过：语法 66/66、反例 29/29、运行语料 63/63；滚种子前后 `make selfhost-native` 均全过：固定点 10 个模块产物一致、自解析 43 个源文件、模块 17/17、项目 52/52。`make seed` 后再次 `make` 与自举门通过；`git diff --check` 和文档本地链接检查通过。
- 根 `yh` SHA-256：`c2fe874ad0dc324135e1441224e4095e64eb1c1f3a865ed6b0e18dd05bf4450d`；Darwin arm64 种子 SHA-256：`8ac9b924fcad79450b4c2dab8bc003d71b554a866f77ccdb597db9c2c01085ee`。
- 完整阶段数据见[缓存指纹与阶段计时报告](01-finished/yh-编译流程R2b缓存指纹分块与阶段计时-2026-10-01.md)。R2b 线程池/函数级完整 check-IR 缓存、自有汇编链接及 R0–R6 总验收仍在实施。

## 2026-10-01 编译流程重规划 R2b：fork/COW 前端快照复用

- 模块 worker 改为 fork 父进程中已验证的项目与词法快照，通过写时复制隔离可变语义状态；worker 不再 exec 后重载项目和重做全项目词法分析。声明索引延迟至待重建模块，缓存命中构建不再执行声明解析。
- 更新 `.yh` 计数回归：首轮只建立一次项目索引，热缓存构建确认语法/声明索引次数为 0、无 worker；provider/consumer 与菱形 DAG、失败无链接等原有并行语料继续通过。
- 验证：`make`、`make test`、`make selfhost-native` 通过；语法 66/66、反例 29/29、运行 63/63、模块 17/17、项目 52/52、固定点 10 个模块产物、41 个源文件自解析。
- Apple M1 冻结 25 文件语料 20 轮（中位数/p95）：无改动 109.6/140.7ms、函数体变化 757.0/903.1ms、冷编 1,812.6/1,878.1ms；汇编/链接调用 0/0、1/1、4/1。速度目标 50/200/1,000ms 均未达到；函数修改仍捕获 80 个 AST 函数上下文，真正线程池与完整函数级 check/IR 缓存待完成。
- 详见[fork 快照复用报告](01-finished/yh-编译流程R2b-fork快照并行worker-2026-10-01.md)。R0–R6 继续实施。

## 2026-10-01 编译流程重规划 R3：自有 memcpy/strlen

- arm64 后端为 `memcpy` 与 `strlen` 发射本地运行时入口，支持直接及函数值调用；新增 `.yh` 用例覆盖零长、块边界、返回指针、UTF-8 字节长度和非对齐字符串。普通程序与自编编译器均不再导入这两个 C 服务，Linux arm64 对象交叉组装成功且无未定义符号。
- 验证：`make -B`、`make test` 与 `make selfhost-native` 通过；语法 66/66、反例 29/29、运行 63/63、模块 17/17、项目 52/52。根 `yh` SHA-256 `78e36cb3d64d2c81a21ef26ccdb21135fbf164fd22517240d56d980e4cba28c7`；Darwin arm64 种子 SHA-256 `40f4ae0bd8120068deb374d8dde30f90d4b86431210aff5b9be40cb978d47f48`。
- M1 冻结语料 20 轮中位数/p95：无改动 105.9/129.8ms，改单函数 774.5/878.5ms，冷编 1,952.6/2,173.9ms；50/200/1,000ms 目标均未达成。详细数据见[自有字节字符串运行时报告](01-finished/yh-编译流程R3自有字节字符串运行时-2026-10-01.md)。`malloc/free`、格式化/I/O/退出、线程 API、Linux 原生验证与自有汇编/链接仍未完成，R3 和 R0–R6 整体继续实施。

## 2026-10-01 编译流程重规划 R3：项目目录枚举 OS API

- 项目扫描移除 `/bin/ls`。Darwin arm64 通过 `getattrlistbulk` 读取目录项；Linux arm64 通过目标专属 `linux_syscall6` intrinsic 调用 `openat/getdents64/close`，并为函数指针保留本地 syscall stub。公共扫描器复制本轮拥有的文件名与类型、按字节序排序，再递归扫描。
- `.yh` 项目矩阵覆盖空格、引号、非 ASCII 与换行文件名、隐藏项过滤及超过 512 项的目录；并验证 Darwin API 和 Linux syscall 的目标隔离、直接调用与函数值调用。
- 滚种子前后 `make test`（语法正例 66/66、反例 29/29、Darwin 运行 63/63）和 `make selfhost-native` 全通过；相邻两代 10 个模块产物一致、39 个源码自解析、模块 17/17、项目 52/52。`make -B` 与 `git diff --check` 通过。
- Darwin 宿主完成 Linux arm64 目标语义构建；生成汇编经 `clang -target aarch64-linux-gnu` 组装为 ELF，`nm` 确认 syscall 函数符号为本地定义。当前宿主不是 Linux，尚未做 Linux 原生运行验收。
- `make seed` 更新 Darwin arm64 种子 SHA-256 为 `8f4e34b1db3a7922f63a424fa3972011bb352e1a41bc6945dbd5b643879713ea`；滚种子后根 `yh` SHA-256 为 `693d454c7cb6cdd9682b4bd5db52532072a0dd89a28da5cbf8660cdde8b9a1bf`。
- 20 轮 Apple M1 阶段测量（目录 API 完成后、清理无用 helper 前；中位数/p95）：无改动 106.4/117.7 ms、函数体变化 756.1/826.3 ms、冷编 2,051.9/2,287.8 ms。50/200/1,000 ms 目标均未达成，此数据作为阶段基线。
- 详见[目录枚举 OS API 报告](01-finished/yh-编译流程R3目录枚举OSAPI-2026-10-01.md)。Linux 原生运行、线程 API、自有 runtime 与通用 C 导入审计未完成；汇编和链接仍调用系统工具，R3 与 R0–R6 整体仍在实施中。

## 2026-10-01 编译流程重规划 R3：直接从入口读取环境向量

- 编译器入口扩展为 `main(argc, argv, envp)`，并在启动时保存只读的 OS 环境向量；`PATH` 与 `YH_STDLIB` 直接从 `envp` 查找，删除 `/usr/bin/printenv` 子进程。普通 yh 程序的入口语义也接受第三个 `envp **char` 参数。
- 新增 `envp-api` `.yh` 项目用例检查普通程序收到 `YH_ENV_TEST=present`；既有 PATH worker 定位与 YH_STDLIB 回归验证编译器自身读取环境的路径。
- 验证：滚种子前后 `make test` 与 `make selfhost-native` 全通过；语法 66/66、反例 29/29、运行 63/63、模块 17/17、项目 48/48，固定点 10 个模块产物一致、自解析 36 个源文件。`make seed` 后 `make -B` 与滚种子后主门通过。
- Darwin arm64 种子 SHA-256：`a99fceeb2cc4e8483a7871d6b7406f8a62de666d3dfc87d43701da7aac3252ae`；根 `yh` SHA-256：`c588cd670c344d4135080992ab2cf9d8a0f53b21662087ce7b64eb42f14a3609`。
- 当前仍由 `/bin/ls` 枚举项目目录，最终汇编/链接依赖系统工具。`nm -u yh` 仍列出 `_malloc`、`_free`、`_memcpy`、`_strlen` 等通用 C 服务；完整导入清单、R3 自有 runtime 与 Linux arm64 验证仍待完成。本次只在 Darwin arm64 宿主验证。
- 详见[环境向量迁移报告](01-finished/yh-编译流程R3环境向量-2026-10-01.md)。R3 与 R0–R6 整体仍在实施中。

## 2026-10-01 编译流程重规划 R3：输出捕获、目录 OS API 与严格自举

- 项目目录与环境查询从 shell 重定向迁到 `fork/execvp`、`open/dup2` 和 argv；捕获文件标志按宿主 OS 选择，不受 `-target` 影响。项目/临时目录创建改用 `mkdir` OS API 和逐段 `mkdir -p` helper。
- 自举脚本不再主动传 `--legacy-system`，新种子按默认隐藏 `system` 的配置编译；旧种子仍以其旧默认行为构建。
- 新增 `mkdir-api` `.yh` 用例，覆盖首次创建与重复创建；交叉目标项目检查覆盖宿主文件标志。目录枚举与环境查询仍依赖外部 `ls` / `printenv`，系统汇编器、链接器和 runtime 导入审计仍未完成。
- 验证：滚种子前后 `make test`（语法 66/66、反例 29/29、运行 63/63）与 `make selfhost-native` 全通过；固定点 10 个模块产物一致、自解析 36 个源码、模块 17/17、项目 47/47。`make seed` 后 `make -B` 成功；`git diff --check` 通过。
- Apple M1 冻结语料 20 轮（中位数/p95）：无改动 135.1/161.4 ms、函数体变化 790.3/845.6 ms、冷编 2,035.9/2,275.0 ms。50/200/1,000 ms 目标仍未达成；完整计数和旧语料兼容配置说明见[实施方案 §6](02-plan/yh-编译流程重规划实施方案.md)。
- Darwin arm64 种子 SHA-256：`fadc3f00bc57528e1aa9f3ed7aebda34ce0b48636de257a3c362a2c076d0989c`；强制重建根 `yh` SHA-256：`ddbf9823389d66c340819d5bc19377b3e007f99a9de0517133a225fb4dfc4ed8`。
- 详见[输出捕获与 OS 目录 API 报告](01-finished/yh-编译流程R3输出捕获与目录OSAPI-2026-10-01.md)。R3 与 R0–R6 总体仍在实施中。

## 2026-10-01 编译流程重规划 R3：兼容配置与显式进程调用切片

- 默认 prelude 不再隐式登记 `system(cmd)`，`--legacy-system` 显式开放迁移期兼容接口；配置身份加入模块、IR 与链接缓存键。`.yh` 项目覆盖默认拒绝、兼容 build/check/run 和模式切换缓存隔离。
- 编译器调用汇编器、链接器、构建目录创建和运行目标程序改为 `fork/execvp/waitpid` 显式 argv；自举启动器识别新旧种子。目录/环境查询仍依赖 shell，R3 尚未完成。
- 验证：`make`、`make -B`、`make test`（66/66、29/29、63/63）和滚种子后的 `make selfhost-native`（固定点、36 源文件自解析、并发/缓存/check 隔离、模块 17/17、项目 44/44）通过；`git diff --check` 通过。
- Darwin arm64 种子 SHA-256：`853fda71a1b1be87e70590ffc38b5be3bae673d7bcd2e8ff5f02fd6600ca5a78`；根 `yh` SHA-256：`25cd492e39b41662d3ca0bdcd4596500dfe6a725f965b0bbad9d59ce7750ed4f`。
- 详见[兼容配置与显式进程调用报告](01-finished/yh-编译流程R3兼容配置与显式进程调用-2026-10-01.md)。目录枚举、环境 API、自有 runtime、线程服务与自有汇编/链接仍未完成。

## 2026-10-01 编译流程重规划 R2a：分支赋值与 phi 合流

- SSA 新增受限四块分支 lowering：分支前初始化的标量 `let` 可与参数一起在 `if/else` 块内赋值；合流块对变化绑定生成双前驱 phi。原有分支直接 return 路径保留。语句 lowering/phi 缓冲辅助代码拆入 `compiler/parse/ast_ir_control.yh`；函数缓存键升至 v5。
- `.yh` 项目用 `branch_update` 验证一侧修改、一侧沿用参数，用 `branch_local` 验证局部变量两侧写入；缓存中两函数均有四块 CFG 和双输入 phi，运行退出码 219。build/check 函数上下文、IR 缓存命中/精确失效/损坏重建通过。
- 验证：`make test`（66/66、29/29、63/63）、`make selfhost-native`（10 个固定点产物、35 个源文件自解析、模块 17/17、项目 42/42）；滚种子后 `make -B` 与再次 `make selfhost-native` 通过，`git diff --check` 通过。
- Apple M1 冻结 25 文件语料 20 轮：无改动 187.9/233.0 ms、函数变化 903.0/953.1 ms、冷编 2,233.2/2,297.0 ms（中位数/p95）；汇编/链接 0/0、1/1、4/1；峰值 RSS 15.1/51.0/50.9 MiB。50/200/1,000 ms 暂定目标均未达到，详见[分支赋值与 phi 报告](01-finished/yh-编译流程R2a分支赋值phi-2026-10-01.md)。
- 根 `yh` SHA-256：`8f69a0f745cde11076b446c1e97e9732b5a5bcb8948bd11a3c4a951e34b013f7`；Darwin arm64 种子 SHA-256：`778c2b5ef3d91c18a52e4255333b7976b8d6a8b810744e25581fccafed80d36b`。
- 当前 lowering 仍不驱动后端；循环、嵌套控制流、复杂赋值、完整函数级 check、真正线程池、平台后端和自有汇编/链接待实施。

## 2026-10-01 编译流程重规划 R2a：顺序局部定义与赋值

- SSA lowering 新增按声明顺序处理的单绑定、有初值标量 `let` 和同类型 `=`/`+=`/`-=`/`*=`；参数与局部通过函数私有映射读取当前 SSA 值，赋值产生新定义并更新映射。其他复合/聚合赋值、前向引用与复杂局部控制流仍走旧发射器。
- 函数 IR 缓存键升至 v4，包含函数所有表达式节点语义事实与绑定类型/布局。`.yh` 项目验证参数/局部读写、连续复合赋值、局部间读取、同名绑定隔离、局部实现变化只失效一个缓存及损坏缓存重建；生成程序运行结果为 115。
- 验证：`make test`（语法 66/66、反例 29/29、运行 63/63）、模块项目矩阵 42/42、`make selfhost-native`（10 个固定点产物、34 个源文件自解析、模块 17/17、项目 42/42）通过；`make seed` 后 `make -B` 和再次 `make selfhost-native` 通过。
- Apple M1 冻结语料 5 轮测试：无改动、函数体变化、冷编中位数/p95 为 188.1/213.8、873.0/942.3、2,222.9/2,384.1 ms；汇编/链接调用为 0/0、1/1、4/1。样本少于正式 20 轮，不能作为性能目标验收，三项中位数目前均高于暂定目标。
- Darwin arm64 种子 SHA-256：`4fe6932658f0d8279f39491b824acb64a9fd4f661a8f4bcadfd266d4a0b73715`；强制重建后的根 `yh` SHA-256：`1bf1917315604fccc9ccfcb2bff2f991945d0de2dd6bc35013a12bdb36965b35`。
- IR 仍只覆盖受限函数子集且不驱动汇编后端；复合/聚合赋值、分支/循环局部、调用、函数 check 缓存、真正线程池、双 arm64 后端和自有工具链仍未完成。

详见[顺序局部定义与赋值报告](01-finished/yh-编译流程R2a顺序局部SSA定义-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R1：函数 AST 上下文范围切片

- 新增函数级只读 `AstFunctionContext`，保存 AST 四类 arena 范围和源声明身份；模块声明建立文件基址索引，避免上下文构造逐函数线性搜索。
- 上下文 verifier 检查表达式、语句、边和绑定没有跨函数引用。SSA lowering 与参数检查改为消费函数切片，指令临时容量按函数表达式规模计算，IR 缓存语义键版本升到 v3。
- `irfront` `.yh` 项目新增两个同名局部绑定函数，build/check 都捕获 10 个函数上下文；check 保持 `ir_functions=0`，程序结果不变。
- `make`、`make test`（66/66、29/29、63/63）、模块项目矩阵 42/42、`make selfhost-native`（34 个源文件自解析、10 个模块产物固定点）及滚种子后的 `make -B` / 自举门均通过；`git diff --check` 通过。
- 两轮 Apple M1 初测中位数/p95：无改动 199.5/200.8 ms、函数体变化 933.3/935.4 ms、冷编 2,225.6/2,233.4 ms；样本过少，不据此判断速度变化。详见[函数 AST 上下文报告](01-finished/yh-编译流程R1函数AST上下文范围-2026-10-01.md)。
- 根 `yh` SHA-256：`e9a2f94203fe12f04239417e2b6d3166214e337125d1469f7bb0cb3be9a544e4`；Darwin 种子 SHA-256：`504005f98f0666f02d7ced0faa0dcac00bafe77cb8c8f4a0a115a59275208635`。
- 此描述符尚未隔离 parser/semantic 全局，也没有让函数任务线程安全；线程池与完整任务私有状态仍未完成。

## 2026-10-01 编译流程重规划 R2b：接口就绪并行调度过渡切片

- 构建协调器以显式 argv 启动最多四个进程 worker。构建会话接口使用进程专属后缀并原子发布，依赖方可在 provider 私有函数/汇编结束前开工；缓存命中读取已验证的持久接口。
- worker 全部成功后才原子提交持久接口与 manifest；失败停止派发、回收 worker、清理会话文件并跳过最终链接。统计输出 `workers_peak`、`iface_early`。
- 新增 `.yh` scheduler 项目语料，覆盖 provider/consumer 与菱形依赖 DAG、接口提前推进、失败无链接、PATH 启动及含空格/单引号的路径；实测调度峰值分别为 2 与 3，接口提前推进计数分别为 1 与 3。
- 验证：`make`、`make test`（66/66、29/29、63/63）、模块项目门 42/42、`make selfhost-native`、滚种子后的 `make` 和再次自举门、Python 语法检查与 `git diff --check` 通过。
- Apple M1 冻结语料 20 轮（中位数/p95）：无改动 196/354 ms、函数体变化 905/975 ms、冷编 2,278/2,642 ms；汇编/链接调用 0/0、1/1、4/1。50/200/1,000 ms 目标仍未达成。根 `yh` SHA-256：`26a7838a6727492288223bba448ea9a1b03243f07c905d5dca1c51c7a5e19687`；macOS arm64 种子：`51204b7025f7269428c046738d79f344107944006b5c7250a51602eff59b3f36`。
- 这是进程 worker 迁移桥。线程池、完整任务私有状态、函数级 check/IR、文件对象及同项目并发提交仍未完成；系统依赖和自有工具链目标也仍待实施。

详见[接口就绪并行调度报告](01-finished/yh-编译流程R2b接口就绪并行调度-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R2a：标量参数 SSA 定义与读取

- `compiler/ir/ssa.yh` 新增 `IR_OP_PARAM`。函数参数由入口块中 phi 后、其他指令前的连续
  `PARAM` 定义表示，参数序号必须从零连续；verifier 拒绝错序、越出入口前导区及伪造操作数。
  序列化仍使用既有指令字段，无需扩张 IR 文件格式。
- `ast_ir.yh` 现在可将标量参数引用降低为对应 SSA 值，覆盖受限直接 return、`+ - * ==` 表达式
  和既有双臂 if/else return；缓存键版本升级，并加入函数签名参数数量、类型及目标布局事实。
- 新增 `.yh` 参数函数 `from_param`，由入口实际调用并验证返回 58；IR verifier 用例检查有效定义、
  非连续序号和非法操作数字段。项目验收现含 7 个 SSA 缓存函数，覆盖冷写、无关入口修改全命中、
  单函数失效和损坏缓存重建。
- 验证：`make`、`make test`（语法 66/66、反例 29/29、运行 63/63）、
  `make selfhost-native`（10 个模块产物固定点、32 文件自解析、模块 17/17、项目 36/36）通过；
  更新种子后 `make -B` 与再次 `make selfhost-native` 通过。`git diff --check` 和 Python 语法检查通过。
- 根 `yh` SHA-256：`bac264cdd78be400907136cc6fbaa1b0aefdce088930255bcabec8fd08aa4f5f`；
  macOS 种子 SHA-256：`6f03b306a525e86463c8e6eeaa4978632cf5057fbbe961064443f2eeefe96bbf`。
- 当前参数 IR 只供 verifier/缓存迁移验证，尚不驱动目标后端；局部变量赋值、调用 lowering、完整
  check 缓存、线程池、接口就绪调度、自有汇编/链接及最终速度目标仍未完成。

详见[标量参数 SSA 切片报告](01-finished/yh-编译流程R2a标量参数SSA-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R2b：受限函数 SSA IR 缓存

- `ast_ir.yh` 为当前受限 lowering 子集增加持久 IR 缓存。键包含正在运行的编译器二进制指纹、
  目标方言、函数源码和 lowering 读取的表达式类型事实；缓存包络校验键与内容校验值，
  IR 解码再执行 verifier。内部模块 worker 显式继承父构建的 `-target`，交叉目标不会借用宿主默认值。
- `irfront` `.yh` 项目回归覆盖首次缓存写入、修改不进入 IR 的入口函数后六函数全命中、
  修改 `sum` 后只有一个 IR miss、损坏缓存拒绝并重建；`yh check` 仍 `ir_functions=0`，
  不读取或写入常规 IR 缓存。
- 验证：`make`、`make test`（语法 66/66、反例 29/29、运行 63/63）、
  `make selfhost-native`（固定点 10 个产物、32 文件自解析、并发/check/缓存/项目门 36/36）、
  滚种子后的 `make -B` 与再次 `make selfhost-native` 通过。`git diff --check` 与 Python 语法检查通过。
- Apple M1 冻结语料 20 轮：无改动 192/223 ms、单函数体变化 980/1,104 ms、冷编
  2,345/2,507 ms（中位数/p95）；汇编/链接调用 0/0、1/1、4/1。当前冻结语料没有受限
  lowering 可处理的函数（`ir_functions=0`），这些测量不证明函数 IR 缓存提升端到端速度，
  总目标 50/200/1,000 ms 仍未达到。根编译器 SHA-256 为
  `fe9a44ddc9b074f838710a3c2990a9a324a879cc0b6cc877e5b12e0c2bba70f2`，Darwin 种子 SHA-256 为
  `36ab04c1e61c21ef1c8c12ce2be3e79dd56534af72d05c4240de08742c336c1e`。
- 这只是少量函数 lowering 的 IR 缓存，不包含函数 check 结果，也不驱动汇编；完整受检语义键、
  线程池、接口就绪并行、文件级对象、原子提交和自有工具链仍在 R1/R2b–R6 待办。

详见[函数 IR 缓存切片报告](01-finished/yh-编译流程R2b函数IR缓存切片-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R2a：首个分支 CFG 接入 AST→SSA

- 扩展 `compiler/parse/ast_ir.yh`，在已有常量单 return lowering 外接入无参数双臂
  `if/else` 函数：条件表达式进入入口块，then/else 各形成独立返回块，运行 SSA 简化和
  verifier。范围刻意限制为每个分支块只有一个直接 `return`；其他函数仍由旧发射器负责。
- `tests/modules/projects/irfront/main/main.yh` 增加比较条件和 true/false 分支函数，并由
  程序入口实际执行两条路径；项目门要求至少 6 个 lowering 函数、`yh check` 的
  `ir_functions=0`，结果退出码为 50。
- 验证：`make`、`make test`（语法 66/66、反例 29/29、运行 63/63）、
  `make selfhost-native`（10 个模块产物固定点、32 文件自解析、所有模块与项目门 36/36）、
  滚种子后的 `make -B` 与再次 `make selfhost-native` 全通过；`git diff --check` 通过。
- Apple M1 冻结语料 20 轮：无改动 190/225 ms、单函数体变化 985/1,079 ms、冷编
  2,353/2,550 ms（中位数/p95）；对应汇编/链接次数为 0/0、1/1、4/1。目标 50/200/1,000 ms
  尚未达到。详见[分支 CFG 接入报告](01-finished/yh-编译流程R2a分支CFG-2026-10-01.md)。
- 新种子 SHA-256：`3ab21aa7fb74448cfd4f0dcf5563f6ae60643581de01fa6c8c129cac25a6d0e2`；
  当前根 `yh` SHA-256：`7e3f780b89cbe201997032730cff4ebb50ad967ad92a1f6f96c2cf23277e7eb6`。
- 这仍是窄迁移探针：IR 不持久化、不驱动后端，局部变量、循环、合流 phi、调用、线程池、
  函数级缓存与自有汇编/链接仍未实现。

## 2026-10-01 编译流程重规划 R2a：首条 AST→SSA 主路径

- 根 compiler 项目显式依赖独立 `compiler/ir` 子项目。普通 build 与 `yh check` 都在解析
  期间收集并校验表达式/语句/声明 AST；pass1 后绑定函数签名，确保 lowering 使用稳定声明身份。
- 普通 build 在 AST 校验后，将无参数、单个直接 `return` 的常量整数/布尔表达式构造成目标隔离
  的 typed SSA 函数，并运行低成本简化及 verifier。首批 lowering 覆盖整型/布尔/字符常量与
  `+`、`-`、`*`、`==`；不符合该结构的函数仍由旧发射器输出。SSA 暂不持久化，也未驱动平台后端。
- `tests/modules/projects/irfront/` 覆盖四种运算；项目回归要求普通 build 至少校验 4 个 IR 函数、
  `yh check` 的 `ir_functions=0`，最终程序返回 42。快照门现在会把清单声明的本地 path 依赖
  子项目纳入固定点，词法统计与性能脚本兼容新增 stats 字段。
- Apple M1、冻结 25 文件语料、20 轮端到端复测（含汇编/链接）：无改动 185/220 ms、单函数体变化
  957/1,023 ms、冷编 2,317/2,374 ms（中位数/p95）。汇编/链接调用分别为 0/0、1/1、4/1；
  函数修改与冷编较上一 20 轮缓存切片基线略慢，性能目标仍未达到。当前 IR 切片主要验证管线接线，
  还没有函数级缓存或并行带来的收益。完整报告见
  [AST→SSA 主路径报告](01-finished/yh-编译流程R2a首条主路径-2026-10-01.md)。
- 验证：`make -B`、`make test`（语法 66/66、反例 29/29、运行 63/63）、
  `make selfhost-native`（cc2/cc3 的 10 个模块产物固定点、32 文件自解析、全量语料、并发扫描、
  check/cache、模块 17/17、项目 36/36）通过。按门禁滚动种子后 SHA-256 为
  `cb2f690417488225e3916086c3a029ed1df4a7a94765c90e2428af1dbfd99b08`；新种子冷重建与自举门通过。
- R1 独立语义/check、任务私有状态、InterfaceReady 和函数级缓存，以及完整 SSA、线程池、平台后端、
  自有汇编/链接和 R3–R6 仍未完成。

## 2026-10-01 编译流程重规划 R2a 第四个切片：指令字段规范校验

- `ir_verify_inst` 现在检查当前 IR 指令的保留字段：CONST 不得携带 `a/b/aux`；PHI 不得
  携带普通操作数；非 CONST 的 `imm` 必须为零；非 phi 指令的 `aux` 必须为 -1；LOAD
  的 `b` 与 STORE 的附加字段不得伪造输入。IR 结构注释同步说明这些编码约束。
- 扩展 `irverify` `.yh` 反例：CONST 引用先前已定义值、PHI 带 immediate、ADD 带 aux、
  LOAD 携带多余 `b/aux`、STORE 携带多余 `aux/immediate`。首个反例在旧 verifier 下形成
  RED（退出码 16），收紧校验后通过；既有常量简化、phi、序列化与损坏 CFG 测试继续通过。
- 验证：`make`、`make test`（语法 66/66、反例 29/29、运行 63/63）、项目矩阵 33/33、
  `make selfhost-native`（固定点、自解析 31 文件、并发扫描 8/8、check/cache、模块 17/17、
  项目 33/33）通过；`git diff --check` 通过。
- R2a verifier 仍是部分操作集：调用、转换、switch、全局地址等指令和完整 SSA lowering
  尚未实现；独立 IR 也未接入编译主路径。详见
  [指令字段校验报告](01-finished/yh-编译流程R2a指令字段校验-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R2a 第三个切片：稳定 IR 序列化

- 新增 `compiler/ir/ssa_serialize.yh`，采用固定字段顺序的 little-endian 64 位格式；
  包含 magic、格式版本、目标编号、类型/指令/phi/CFG 表和 SSA 值数，不写结构体填充或地址。
- 解码要求调用方提供空输出，检查目标、版本、精确长度与 64 MiB 规模上限；分配后运行
  `ir_verify`，失败释放所有部分数组。`ir_function_release` 释放解码结果。缓存校验和提交
  仍由后续缓存层负责。
- 扩展 `irverify` `.yh` 用例，验证负 immediate、round-trip 逐字节相同、缓冲不足、错目标、
  错版本、截断数据和损坏 terminator；损坏 IR 被 verifier 拒绝并释放分配。
- 验证：`make test`（语法 66/66、反例 29/29、运行 63/63）、`make selfhost-native`
  （固定点、自解析 31 文件、并发扫描 8/8、check/cache、模块 17/17、项目 33/33）通过；
  最后一次变更后又运行 `make`、项目矩阵 33/33 与 `make selfhost-native` 均通过。
  按仓库门禁执行 `make seed` 并冷重建；Darwin 种子 SHA-256 为
  `8d658d975e0501c7fe49ef07fcb6d5a838466ae24f2f73d449688f43e6facb42`。
- IR 仍未接入主编译路径；AST→SSA、完整指令校验、函数级 IR 缓存、线程池和两个 arm64
  后端未完成，R2a/R2b 仍进行中。详情见
  [稳定 IR 序列化报告](01-finished/yh-编译流程R2a稳定IR序列化-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R2a 第二个切片：默认低成本 SSA 简化

- `compiler/ir/` 新增 `IR_OP_COPY` 与独立 `ir_simplify`：对整数/布尔常量做定宽归一化，
  折叠整数加减乘和整数相等比较；把所有非自环 phi 输入相同的 phi 替换为别名/拷贝，
  并重写指令、phi 边和终结值引用。优化前后调用 `ir_verify`。
- 扩展 `irverify` 的 `.yh` 项目：先验收 `10 + 20` 折叠为 30，再验收两分支同值合流的
  phi 消除及 return 值替换；错误 CFG/类型/支配用例继续保留。
- 验证：`make`、`make test`（语法 66/66、反例 29/29、运行 63/63）、
  `make selfhost-native`（固定点、自解析、并发扫描、check、缓存、模块 17/17、项目 33/33）
  通过。`make seed` 已按门禁执行，SHA-256 仍为
  `8d658d975e0501c7fe49ef07fcb6d5a838466ae24f2f73d449688f43e6facb42`；随后冷构建、
  种子核验和项目矩阵 33/33 通过。
- 此优化还未接入主编译路径，IR 没有从 CheckedFunction/AST 构造，也没有持久化或目标后端；
  R2a、R2b 和 R3–R6 均未完成。

## 2026-10-01 编译流程重规划 R1 第七个切片：函数内稳定绑定

- check AST 新增函数内稳定绑定编号与 arena 行，捕获参数、局部变量/常量及 for-in
  隐式变量；表达式叶节点指向具体绑定行，语句节点关联一条或多条声明绑定。旧
  `sym_id` 只保留为解析时符号槽快照，遮蔽块退出并复用槽位后仍能区分变量身份。
- 赋值语句 AST 现在记录真实赋值 token；此前节点把 LHS 首 token 当作 `op`，无法供
  后续 SSA lowering 区分普通赋值与复合赋值。
- 扩展 `tokenreplay` `.yh` 用例覆盖函数参数、多绑定声明、局部常量、同名嵌套遮蔽、
  复合赋值和 for-in 隐式绑定；运行语义保持预期，`yh check --stats` 要求绑定数非零。
- 验证：`make test` 的语法 66/66、反例 29/29、运行 63/63 通过；模块项目矩阵 33/33，
  有效/无效 check、check 产物隔离、无外部工具回归通过。修复 `lex-stats.py` 与性能
  脚本对 `ast_bindings` 字段的解析后，`make selfhost-native` 全绿：两代 8 个模块
  固定点、自解析 30 个源文件、并发扫描 8/8、模块 17/17、项目 33/33。按仓库规则
  执行 `make seed`，新 Darwin 种子 SHA-256 为
  `8d658d975e0501c7fe49ef07fcb6d5a838466ae24f2f73d449688f43e6facb42`；随后冷重建、
  种子校验、`check-command.py` 与 `git diff --check` 通过。
- 这仍是 AST/check 迁移切片，不是独立语义阶段或 SSA lowering；任务私有上下文、
  InterfaceReady 调度与函数级缓存仍待 R1，R2a/R2b 尚未完成。

## 2026-10-01 编译流程重规划 R1 第六个切片：表达式绑定与常量事实

- typed 表达式节点现保存解析到的符号索引、符号类型/类别/标志/偏移，以及整型/指针
  常量位型、浮点位型和整数字面量标记。`ast_refs` 统计可复用的解析符号引用，
  `yh check --stats` 可直接观测。
- 符号索引按 `(file_id, owner_decl, sym_id)` 解释，并在捕获时复制符号元数据。旧
  `scope_pop` 会回收并复用函数局部符号槽，因此 AST verifier 不依赖函数结束后的
  `c_syms`；它验证声明归属、符号快照类型类别，以及标识符叶节点的类型一致性。
- 扩展 token replay `.yh` 用例，覆盖跨文件函数调用、参数/局部变量和私有常量引用；
  `check-command.py` 要求 `ast_refs` 非零。真实运行仍返回 42，项目 check 不生成后端
  产物，也不调用汇编器或链接器。
- 验证：`make`、`make test`（语法 66/66、反例 29/29、运行 63/63）、
  `make selfhost-native`（8 个模块产物固定点、自解析 30 个文件）、
  `python3 tools/selfbuild-gate.py`（两段三代固定点）、模块 17/17、项目 33/33 通过。
  滚动 Darwin 种子 SHA-256：`5c913f74733925f04dc4122d1765f4610d27a8d74934af8bc0ffeddafd9ba0eb`。
- AST 仍由旧语义遍历同步生成，尚未成为独立语法阶段产物；完整 `CheckedFunction`、
  任务私有上下文、接口就绪推进、函数级缓存和 SSA lowering 仍未完成。

## 2026-10-01 编译流程重规划 R1 第五个切片：语句与声明 AST

- 新增 `compiler/parse/ast_stmt.yh`，在 `yh check` worker 的现有解析遍历中记录块、
  声明、类型、if、for、switch/case、return、break/continue、goto/label、赋值与表达式
  语句。节点用文件内 token 半开区间、父/子/兄弟索引和表达式根引用表示，不改变普通
  build 路径的解析行为。
- 新增 `compiler/parse/ast_decl.yh`，复用已生成的 PDecl 范围建立文件级声明节点；函数
  体解析后连接到所属声明。worker 收尾验证语句树、根链、表达式范围、声明范围与函数体
  引用；`--stats` 增加 `stmt_nodes`、`decl_nodes`。
- 扩展 token replay 项目的 `.yh` 回归，执行 if/else、循环、continue、switch、赋值和
  return；`yh check --stats` 同时要求表达式、语句、声明节点非零。运行结果仍为 42，
  有效/无效 check、独立 check 缓存保护和无外部工具检查均通过。
- 本切片仍由旧 parser 的语义遍历同步建立 AST。没有独立 `CheckedFunction`、任务私有
  上下文、接口就绪调度、函数级缓存，也没有把 AST 接入 SSA builder；R1 与 R2a 未完成。
- 固定语料做了 3 轮速度冒烟测量：无改动中位数 209ms、单函数体变化 980ms、冷编 2,343ms；
  对应汇编/链接次数为 0/0、1/1、4/1。该小样本只作当前参考，不能代替 20 轮正式基线；
  50/200/1,000ms 验收目标仍未达到。
- 验证：`make`、`make test`、`make selfhost-native`、
  `python3 tools/selfbuild-gate.py`、check/阶段计数脚本、模块矩阵 17/17、项目矩阵 33/33
  全绿。两代主门固定点为 8 个模块产物一致，自解析 30 个源文件通过。滚动 Darwin 种子
  SHA-256：`af601fdab18b41092b716ec2ecd4835e324ee3b153739115ffbaea96ee9896e8`。

## 2026-10-01 编译流程重规划 R1 第四个切片：check 专用表达式 AST

- 新增 `compiler/parse/ast_expr.yh` 连续节点表，保存节点种类、运算符、语义类型、
  token 半开区间、token 数、项目文件 ID 和最多三个子节点。`Res.ast_id` 让当前解析
  遍历把已有类型结果关联到 AST；只在 `yh check` worker 启用，普通构建没有 AST 分配。
- 同步记录基本表达式、一元/二元/三元运算、调用和实参链、索引/切片、成员、
  `.to_type` 转换及数组字面量。模块 worker 完成函数遍历后校验节点范围、类型、
  后序编号、子节点包含关系和文件归属；`--stats` 增加 `ast_nodes` 计数。
- 扩展 token replay 的 `.yh` 项目函数，包含数组字面量、数组到切片转换、切片与索引、
  短路运算、三元与一元表达式；`tests/selfhost/check-command.py` 要求有效项目实际
  生成非零 AST 节点，并保留非法项目、产物清理和未调用外部工具的检查。
- 这是 R1 的表达式 AST 迁移切片，不是完整 AST：语句/声明节点、独立语义与 check
  遍历、任务私有上下文、InterfaceReady 调度及函数级缓存仍未实现。现有 parser 仍
  会在遍历时运行语义钩子，check 仍靠模式位抑制发射缓冲。
- 验证：`make`、`make test`、`make selfhost-native`、
  `python3 tools/selfbuild-gate.py` 全绿；自举固定点、模块 17/17、项目 33/33，
  compiler 项目的 `yh check --stats` 成功生成 4 个 worker 的 AST 且无汇编/链接。
  按滚动自举规则更新 `bin/yh`，SHA-256 为
  `a7b7fb039923dcb1d216b5ddce010e502d883e11fcbbea0759ca46df47b75905`。

## 2026-10-01 编译流程重规划 R2a 首个切片：typed SSA 模型

- 新增独立 `compiler/ir/` 项目，定义目标编号、函数私有类型表、typed 指令、
  SSA 值编号、基本块终结信息与 phi 前驱输入。数组连续存放，指令操作数只
  使用值/块索引；模块不依赖旧 `gen`、解析器或平台发射器。
- `ir_verify` 检查类型宽度、结果定义唯一性、操作数支配与内存操作类型、
  CFG 终结形式、指令块范围，以及 phi 是否覆盖每个真实前驱且无重复/错型。
- 新增 `tests/modules/projects/irverify/`，构造 if/else 合流的 phi `.yh` 正例，
  并确认重复前驱、错误类型和从另一分支引用未支配值会被拒绝；接入模块项目回归。
- 新 IR 作为 `compiler/` 下的嵌套项目后，固定点产物发现门曾把它误算入主项目；
  已按子目录 `project.toml` 设置边界，并给发现器增加嵌套项目反例自检。
- 验证：`python3 tests/modules/build-check.py --compiler-path ./yh` 通过（33/33 项目用例）。
  `make`、`make test`、`make selfhost-native` 与
  `python3 tools/selfbuild-gate.py` 全绿；滚动 Darwin 种子 SHA-256 为
  `c3e14e957539c6b57cffcb0aae14228c6a76ee25f1f01b570651f36d30924e4e`。
  尚未实现完整 SSA builder、稳定序列化和后端；该 IR 项目也尚未
  接入编译器主流水线，因此 R1 与 R2a 均未完成。源码见
  [ssa.yh](../compiler/ir/ssa.yh)。

## 2026-10-01 编译流程重规划切片：模块对象与链接内容缓存

- 为现有模块汇编增加对象缓存，为每个链接输出增加结果缓存；缓存键使用 64 位
  FNV-1a，并校验对象和最终程序内容。删除/损坏对象会重汇编；最终程序缺失或被
  覆盖会重链。
- `--stats` 增加 `asm` 与 `link` 实际调用次数。新增
  `tests/selfhost/link-cache.py` 覆盖冷/热构建、对象损坏、程序损坏与函数实现变化：
  热构建 0 汇编/0 链接，损坏对象 1/0，损坏程序 0/1，单模块函数变化 1/1。
- 编译器二进制指纹现在每个构建进程只读一次；对象/链接缓存逻辑拆入
  `compiler/cmd/link_cache.yh`，保留四个既有顶层模块。
- M1 冻结语料 20 轮中位数/p95：无改动 186/223 ms、单函数体变化 894/958 ms、
  冷编 2,199/2,287 ms。无改动较前一切片快约 89%，函数体变化快约 52%，冷编快约 0.8%；
  离 50/200/1,000 ms 目标仍有差距。
- 缓存仍按模块汇编，且没有纳入外部工具版本；全局扫描、整模块 check/IR、文件级
  对象、线程池、接口提前推进及自有工具链均未完成。详情见
  [对象与链接缓存测量报告](01-finished/yh-编译流程对象链接缓存-2026-10-01.md)。
- 最终门：`make -B`、`make test`、`make selfhost-native` 与
  `python3 tools/selfbuild-gate.py` 均通过；滚动 Darwin 种子 SHA-256 为
  `c3e14e957539c6b57cffcb0aae14228c6a76ee25f1f01b570651f36d30924e4e`。

## 2026-10-01 编译流程重规划 R1 第三个切片：项目级 yh check

- 新增 `yh check [module]`，对入口模块或显式模块及其依赖执行完整的现有
  语义遍历。合法项目通过；类型不匹配的 `.yh` 项目诊断并失败。
- check-only 子进程跳过汇编写文件，文本/数据段写入缓冲被屏蔽；不运行汇编器
  或链接器。依赖接口写入独立 `.build/check/iface/`，检查结束或失败时清除，
  保留正式 `.build` 缓存。
- 新增 `tests/modules/projects/checkbad/` 与 `tests/selfhost/check-command.py`，
  并接入 `make selfhost-native`。测试递归检查 `.build` 下没有汇编、对象、
  接口或 manifest 文件，并用 PATH 包装器确认没有调用 gcc/clang。
- 该实现是阶段性 CLI 和产物契约：语义仍由旧 parser pass 执行，靠全局模式位
  抑制发射缓冲；完整 AST、独立语义/check 遍历、任务私有状态和函数缓存仍在 R1。

## 2026-10-01 编译流程重规划 R1 第二个切片：顶层声明范围索引

## 2026-10-01 编译流程重规划 R1 首个切片：worker 词法快照复用

- 模块 worker 在项目索引时为发现的 `.yh` 文件保留只读源字节与 token
  数组；pass1、全局初始化 pass 与函数 pass 从同一 token 快照重放，不再
  对模块文件重复读取和词法分析。父构建器的项目索引与 worker 项目发现
  仍分别发生，完整 AST 和跨构建文件缓存尚未实现。
- 新增显式 `yh build --stats` 诊断计数器和 token replay 多模块 `.yh` 回归：
  覆盖私有跨文件类型、前向函数调用、跨模块导入与运行结果 42；索引 3 个
  文件共词法 3 次，两个 worker 的 pass1/global/function 文件遍历合计各 3 次。
- M1 固定 25 文件语料每种场景测 20 轮：无改动中位数/p95 为
  2.002/2.185 秒，函数体变化 2.099/2.452 秒，冷编 2.378/2.710 秒；词法
  扫描次数分别 25、53、131，四次汇编和一次链接保持不变。函数体变化和
  冷编的旧流程复核数分别为 74、206；耗时尚无稳定改善，50/200/1000 ms
  目标远未达到。测量及边界见
  [R1 切片报告](01-finished/yh-编译流程R1词法快照复用-2026-10-01.md)。
- 验收：`make -B`、`make test`、`make selfhost-native`、
  `python3 tools/selfbuild-gate.py` 通过；滚动 Darwin 种子 SHA-256 为
  `802f47daff273bceaeeb2857ab409f910dc16ab383534bc93f10ca5533cc8a4b`。
  R1 整体仍未完成。

## 2026-10-01 R0 第二个实施切片：宿主种子与扫描临时状态隔离

- Makefile、两套自举门和 `make seed` 统一使用按宿主系统/架构选择的
  种子路径与旁置 SHA-256；显式 `SEED` 也会校验哈希。Linux arm64
  目标解析为 `bin/yh-linux-arm64`，不覆盖 macOS 的 `bin/yh`。
- 项目索引不再把所有编译器进程的目录列表写进固定 `/tmp` 文件，改为
  `tmp/` 下每进程独立的随机路径，读完即删除。新增并发 `.yh` 项目构建
  回归；旧实现 8 路并发时出现崩溃和交叉目录读取，修复后 8/8 通过。
- 验收：`make -B`、`make test`、`make selfhost-native`、
  `python3 tools/selfbuild-gate.py` 通过；Linux arm64 种子路由 dry-run
  与当前 Darwin 种子 SHA-256 校验通过。
- R0 仍待冻结可重复性能语料、阶段计数/工具调用/峰值内存，并记录
  状态归属与就绪事件契约。线程 worker 的临时路径需随任务私有上下文
  落地；本切片完成的是进程间隔离。

## 2026-10-01 R0 完成：冻结性能基线与流水线状态契约

- 固定提交 `8e17bdb` 的 25 文件/13,338 行 compiler 输入，保存每个源文件
  与 project.toml 的 SHA-256。新增可重复测量脚本，函数体变化会实际改变
  编译器运行结果并由脚本验证。
- Apple M1 上每种负载测 20 个独立进程：无改动 1.985 秒中位数、2.403 秒
  p95；单函数体变化 2.075/2.751 秒；热 OS 缓存下冷编 2.455/2.741 秒。
  峰值单进程 RSS 为 50.63/50.83/50.86 MiB。所有场景仍调用 4 次 clang 汇编
  与一次链接。详细阶段访问数和限制见 R0 报告。
- 旧 pass2 将语义与发射混合，无法提供独立阶段计数；已记录实际模块/文件
  访问次数，R1 将引入分开的前端、check 与代码生成计数器。SourceStore、
  ModuleEnv、FunctionContext、TargetContext 及三个就绪事件契约已落设计。
- R0 全部检查通过：`make -B`、`make test`、`make selfhost-native`、
  `python3 tools/selfbuild-gate.py`；滚动种子 SHA-256 为
  `0b3c43a7595288841ca9277cc7084154bc2f8235bff1bc2d017655f48a8d28c8`。

## 2026-10-01 R0 首个实施切片：可信固定点门

- 修复 `native-selfhost.py` 与 `selfbuild-gate.py` 构建下一代前会覆盖
  前代 `.build`，导致延迟快照把同一路径当成各代比较的错误。每代现在
  立即保存到独立的 `tmp/` 快照目录。
- 从 project.toml 项目名与源码 module 声明动态推导应有的 `.s/.s.i`；
  两个自举门拒绝空快照、缺失或多余产物及代间字节差异。新增门自检
  验证固定点通过、空集/漏产物/内容变化被拒绝。
- 新增 `tests/selfhost/fixedpoint-probe.yh`，覆盖前向调用、结构体浮点
  字段、按值调用与循环。两套门都编译并运行该探针。
- Makefile 的冷编和 clean 路径改为实际 `compiler/.build`。
- 验收：`make -B` 成功；`make test` 语法 66/66、反例 29/29、
  运行 63/63；`make selfhost-native` 固定点 8 项、探针和全量门通过；
  `python3 tools/selfbuild-gate.py` 三代固定点两组、modules 17/17 通过。
- R0 仍在进行：各平台种子路径统一、项目索引临时路径隔离与性能
  基线/阶段计数待做。未滚动 `bin/yh`，因为本切片没有修改编译器源码。

## 2026-10-01 编译流程重规划（GrillMe，规划已确认）

- 用户已确认增量优先、完整 check 的逻辑阶段/命令、产品取消外部
  工具/shell/libc/CRT 的边界，以及首批双 arm64、Linux 先闭环。
- 已记录[ADR-0009](adr/0009-yh采用check与IR及早期并行.md)与
  [设计决策树](03-design/yh-编译流程设计决策树.md)，补 glossary，
  标记旧方案撤回并更新 todo。第二轮确认 SSA、线程池、接口就绪
  后提前推进，以及文件解析/函数 check-IR/文件对象的增量粒度。
- 第三、四轮确认 macOS 审核 OS API/libSystem/dyld 边界、Linux 静态
  ELF 自有工具链首版范围、默认低成本优化、目标隔离 check/IR、
  M1 固定语料 50ms/200ms/1s 待达成目标，以及内部模块重组和 system
  仅保留过渡兼容配置的取舍。
- 完成只读事实调查：重复词法路径、串行模块链、提前接口与共享
  状态障碍，以及工具/shell/运行时/OS/开发测试依赖分层。静态计数
  不当作性能结果。另在独立副本测旧流程 3 冷/3 热/3 函数体注释
  修改构建，端到端中位数 3.211/2.420/2.389 秒；9 次构建成功，
  波动明显且注释修改不是新函数级增量负载。
- 已重写[设计](03-design/yh-编译流程重规划.md)与
  [实施方案](02-plan/yh-编译流程重规划实施方案.md)，明确阶段契约、
  SSA、状态归属、就绪调度、缓存/提交、平台运行时与 R0–R6 验收。
- 完整方案已由用户确认，答案为“确认规划，不开始编码”。仅更新
  文档，未修改编译器、测试或种子；git diff --check 与本地链接检查通过。
  本条记录完成的调查与草案，不代表代码或性能目标已经完成。
  详见[规划交付记录](01-finished/yh-编译流程重规划草案交付-2026-10-01.md)。

## 2026-09-30 全仓库文档同步：修正 40 处事实错误，11 份历史文档加抬头

以实测为基准（CLI 选项逐一验证、目录与 Makefile 目标枚举、示例实跑）
核对全部现行文档，详见
[全仓库文档同步报告](01-finished/yh-文档全面同步报告-2026-09-30.md)。本次
**未修改编译器代码与测试**。

- **事实错误修正**：`README`（删除交叉 ELF/`-c`/`-run`/`--cross` 用法，补
  子命令式 CLI，修正并实测通过语言示例）、`compiler/README.md`（整篇重写：
  原文停留在「构建中断」与平铺 12 文件布局，改为四模块 25 文件实际职责）、
  `AGENTS.md`（填充空节目录/编译流程/使用/构建与测试）、`CONTEXT.md`
  （补模块系统术语）、`03-design/` 五份（mod.toml → project.toml、
  `src/core/` stage0 接入点、gen/lex/parse/cmd 路径、门由 `make bootstrap`/
  `make g3` 改为 `make selfhost-native`、「全局聚合初始化」从缺口移除）、
  `00-语义边界-0.0.1.md`（§3 改写为现行模块可见性规则）、`adr/0001/0005/
  0006/0007`（过期引用与状态）、`02-plan/yh-VSCode扩展方案.md`（9 处
  `yh-new` → `yh`）、`docs/todo.md`（VS-U1）。
- **历史文档只加抬头**：finish.md 条目与 `01-finished/` 交付报告记录的是
  当时状态，旧称谓是正确记述，不改写正文；改为加「历史/已被替代/待重写」
  抬头并指向现行文档，共 11 份。
- **验证**：README 示例抽取编译运行通过（输出 `1 2 1` / `small`）；
  CLI 选项逐一实测确认已删除；全仓库 Markdown 内部链接坏链 0；
  `make test` 63/63；`make selfhost-native` 全绿。

## 2026-09-30 编译流程重规划（文档交付）

- 核对现行 token 驱动、三次遍历、模块子进程、`.build` 缓存和滚动
  自举流程，交付[设计](03-design/yh-编译流程重规划.md)、
  [实施方案](02-plan/yh-编译流程重规划实施方案.md)与
  [ADR-0008](adr/0008-yh编译流程分阶段整理.md)建议稿。
- 待实施 CF-0–CF-4 写入 todo；优先修正两个自举脚本延后读取同目录
  快照造成的自比较，再统一编译核心、目标/产物提交与三层缓存。
- 验证：`make -B` 构建成功；`make test` 语法 66+29、运行 63/63；
  `make selfhost-native` 退出 0，自解析 25 文件、modules 17/17、项目
  31/31。原固定点门的证据缺陷仍待修正；本轮另以独立源码副本
  两代冷编、每代立即保存快照，8 个 `.s/.s.i` 逐字节一致。
- 仅修改规划与记录文档，未修改编译器源码或种子。详细命令、边界
  和证据见[交付报告](01-finished/yh-编译流程重规划交付-2026-09-30.md)。

## 2026-09-30 清单精简：name 产物名 + version 命令 + 入口 = main 模块（用户项目规划落地）

按 docs/todo.md「项目规划」（该节实施后按文件约定移出，历史在此）：

- **schema**（`compiler/cmd/project_index.yh`）：`name` 必须是标识符
  （首字符字母/下划线，其余字母数字下划线），否则诊断「project.name
  必须是标识符」/「只能是字母、数字与下划线」；新增放行 `author`
  （只接受不存）；**删除 `entry` 字段**（旧字段会命中未知字段检查）；
  `version` 不再解析后丢弃，存入 `PProj.ver_off/ver_len`。
- **入口 = 模块名 `main`**：pj_load_project 扫描源码根时标记
  `is_entry`；模块名唯一（同名模块跨目录合并），故至多命中一次——
  先写的「多个 main」歧义分支不可达，已删除。模块名与目录名无关
  （编译器自身 `compiler/cmd/*.yh` 即 `module main;`，目录仍叫 cmd）。
  新增 `pj_entry_mod(proj)`（`project_resolve.yh`）供 build/run/query 用；
  `PProj.entry_off/entry_len` 删除。
- **产物名**：`yh build` 无 `-o` 时取 `project.name`（原固定 `.build/yh`）；
  `yh run` 用同名二进制。`name` 合法标识符约束正是为了让文件名无需 sanitize。
- **`yh version`**：打印当前项目 `<name> <version>`（version 缺省时标注
  「未声明 version」）；裸 `yh` 的用法说明后附同一行，不在项目内静默跳过
  （`pj_find_root(quiet)` 加参数，非静默时保持原诊断）。
- **顺带修**：`build` 的库模式完成信息用 `pj_canon_len`（已被后续 canon
  覆写）打印目录，改为 `build_len`。
- **清单批量更新**：26 个 project.toml 删 `entry` 行、name 去斜杠
  （`yh/compiler` → `yh_compiler`、`example/xxx` → `example_xxx`、
  `yh/std` → `yh_std`）；`tests/modules/projects/fourdir{'',bad}/cmd/main.yh`
  改 `module main;`（目录名保留 cmd，覆盖「模块名≠目录名」）。
- **新语料**：`tests/modules/projects/tomlnamebad`（name 含 `/` 必须拒绝）、
  `authorproj`（name/version/author 三字段齐备）；build-check.py 增
  `p1-name-not-identifier`、`p1-version-cmd`、`p1-outname-from-name`、
  `p1-outname-runs`，并把 fourdir 接口名断言改为 `example_fourdir-main.s.i`、
  keyimp/alias 产物路径改为按 name。项目验收 31/31。
- **滚动自举桥**：删 `entry` 后旧种子（按 entry 选入口）不再认识新清单，
  首次 `make` 会把编译器当库项目且不链接。按既有做法桥接——临时给
  compiler/project.toml 加 `entry = "main"` → 旧种子构建出新 `yh` →
  删临时行 → 新编译器自举构建 → `make seed` 滚种子。
- **验证**：`make` ✓（删产物冷编）；`make test` 63/63 ✓；
  `python3 tests/modules/check.py` 17/17 ✓；`make selfhost-native` 全绿
  （两代固定点 8 产物一致、cc3 自解析 25 文件、语法 66/66+29/29、
  run 63/63、项目 31/31）✓；种子已滚动（`bin/yh.sha256` 更新）。
- **设计文档**：`docs/03-design/yh-模块与项目管理设计.md` 的示例清单、
  字段表、入口规则、命令表同步（该文档仍通篇写 mod.toml，属既有欠账，
  本轮未动）。

## 2026-09-30 project.toml 改名 + import as/跨项目导入 + .build 缓存布局（用户项目规划落地）

按 docs/todo.md「项目规划」实施（方案见
[project.toml与模块增强方案](02-plan/yh-project.toml与模块增强方案.md)）：

- **import 语法扩展**：`import NAME (as ALIAS)?;` 与
  `import KEY.MOD (as ALIAS)?;`。ImportEnt 扩展 proj_key/alias 字段
  （model.yh），mod_parse_head 解析别名与两段点分（多于两段拒绝），
  重复绑定名报错（同模块不同来源用 as 区分）。
- **限定调用按别名**：mod_file_binding 改按 alias 匹配（原按查找名）。
- **绑定架构重构**：删除 gen 侧按名匹配的 mod_bind_current_file，改为
  cmd 侧 mb_file_head_bind(fi) 直绑——child 编译时按扫描期 p_imp 记录
  （file+line+col 对应）把解析结果写入 mod_import_mod，天然支持别名与
  跨项目（解析结果与名字解耦）。
- **KEY.MOD 限定解析**（pj_bind_imports）：键在 [dependencies] 查找，
  键缺失/依赖项目无可导入模块显式报错；不走三层搜索。
- **目录唯一模块**：pj_index_file 登记文件时检查同目录是否已有其他
  模块的文件，违反报两个模块名（新增 pj_dir_prefix_len/pj_same_np）。
- **mod.toml → project.toml**：pj_load_project/pj_find_root/pj_proj_diag
  与全部 fixtures（31 个）、编译器自身清单同步改名。
- **.build 缓存布局**：.build/asm（每模块 .s）、.build/obj（每模块 .o）、
  .build/iface（<tag>.s.i）、.build/manifest；产物名用
  `<sanitize(proj)>-<module>` tag（KEY.MOD 下同名模块防冲突）；
  两步链接（gcc -c 逐模块 → 链接全部 .o）；默认产物 = .build/yh。
- **缓存键补编译器身份**：manifest FNV 哈希加入编译器二进制自身内容
  （c_argv0 文件），滚动代次下热缓存安全。
- **修复**：pj_imp_push 重写时漏带 p_imp_mod 数组分配（首写空指针
  段错误，lldb 定位后补 nd9）；mod_skip_head 的 while 语法错误；
  pj_dir_prefix_len 参数用了关键字 len；pj_imp_push 扩容计数 cnt 缺
  类型声明；mod_skip_head/parse_module 的旧式 while 全部改 for 条件式。
- **种子滚动**：因清单改名触发一次 bootstrap bump（旧种子只认
  mod.toml）——临时 mod.toml 副本 + 旧种子构建 → 新编译器
  （支持 project.toml）→ 删副本、滚种子。迭代桥接 asm/*.s.i →
  iface/ 解决新旧 iface 写读路径差异。
- **验证**：make ✓；make test 63/63 ✓；make selfhost-native 全绿
  （两代固定点 8 产物一致、自解析 25 文件、语法 66+29、run 63、
  modules 17、项目验收 26/26 含新增 alias/keyimp/dirconflict）✓；
  tools/selfbuild-gate.py（cc2→cc3→cc4 固定点）✓。

## 2026-09-30 0.0.3 发布：滚动自举首次端到端跑通（CI 以 0.0.2 资产为种子）

- tag `0.0.3` 推送触发新发布流水线，两次失败后全绿：
  ①`gh api "releases?…"` 相对路径 404，错误 JSON 被词法拆分成假标签——
  改完整路径 `repos/$GITHUB_REPOSITORY/releases` + `--jq` + 显式错误
  检查；②容器 root 写出的 `out/` 目录外层步骤无写权限——产物（yh 与
  转发的 libtcc1.a）全部改在容器内写入。
- **运行结果**：[run 36636909702](https://github.com/lalavender/x/actions/runs/36636909702)
  全绿；Release [yh 0.0.3](https://github.com/lalavender/x/releases/tag/0.0.3)
  归档 4 资产（linux 包 yh + libtcc1.a、darwin 包 yh，各带 sha256）。
- **滚动自举链验证**：CI linux 作业下载 0.0.2 Release 资产，取其中
  yh-new（ELF）作种子 `make SEED=…` 构建出当前源码的 yh 并冒烟通过；
  darwin 作业用入库 bin/yh 构建。
- **端到端用户视角验收**：实际下载 Release 资产——linux 包解压后
  `YH_LIBDIR=<目录> ./yh hello.yh -o hello` 在 arm64 容器运行通过；
  darwin 包解压后本机直接运行通过；两包 SHA-256 与 .sha256 资产一致
  （linux 08f1c470…27e8a）。
- 至此逐版滚动闭环：每版 bin/yh（Darwin 种子）+ Release linux 资产
  （Linux 种子）→ 下一版构建。

## 2026-09-30 主编译器二进制更名：yh-new → yh（编译器就是 yh）

- **改名映射**：主编译器二进制 `yh-new` → `yh`（项目根产物与 Release
  资产名）；入库种子 `bin/yh-new` → `bin/yh`（+ `bin/yh.sha256`，已用
  当前源码产物滚种）。stage0 名义上的 `yh` 名额让给主编译器；stage0
  本体已随 0.0.3 删除，无命名冲突。
- **Makefile**：`YHNEW` → `YH`；一步链规则改 `$(YH)`；新增 `SEED`
  覆盖变量（缺省 = `bin/yh`，命令行可指定其他种子路径——CI Linux 用
  上一版 Release 的 ELF 种子；覆盖时免去 bin 种子前置，路径以 abspath
  传给 yh build）；`seed` 目标、install/uninstall、clean、help 同步。
- **脚本与工具**：tests/yh/check.py、tests/yh-run/check.py、
  tests/modules/{check,build-check}.py、tests/selfhost/native-selfhost.py、
  tools/selfbuild-gate.py、tools/yh-explorer.{py,html}（下拉仅剩
  yh 一项）。当前状态文档同步：AGENTS.md、README、compiler/README.md
  （陈旧的 bootstrap/g3 容器门描述替换为 native-selfhost 两代门实况）、
  docs/todo.md（0.0.3 两节合并，D1–D5 由并行工作落地后本节补 CI 项）、
  ADR-0006/0007 更新注记。历史记录（docs/01-finished、02-plan、
  03-design、finish.md 旧条目）保留原名不动。
- **发布流水线滚动自举化**（release.yml 重写）：linux 作业下载上一版
  Release 的 linux-arm64 资产，取其中主编译器作种子（0.0.2 包内叫
  yh-new、之后叫 yh，自动探测）经 `make SEED=…` 构建当前源码，
  libtcc1.a 随包转发（src/ 已删无法重建）；darwin 作业直接用入库
  bin/yh 构建；双平台冒烟后归档 tar.gz + sha256。Release 说明同步。
- 清理：并行工作遗留的根目录 `ex1` 编译产物加入 .gitignore 不入库。
- **验证**：`make`（bin/yh 种子一步链）+ 冒烟 ✓；`make test` 63/63 ✓；
  `make selfhost-native` 全绿（两代固定点 + 语法/运行语料 + modules
  17/17 + 项目验收 23/23）✓；`make seed` 滚种 + bin/yh 冒烟 ✓；
  arm64 ubuntu:24.04 容器以 0.0.2 linux 资产为种子（SEED=/prevseed/
  yh-new + 转发 libtcc1.a）构建出可用 ELF `yh` 并冒烟通过——发布
  配方与滚动自举链兼容。VERSION 0.0.2 → 0.0.3。

## 2026-09-30 脱离 stage0：删除 C 实现与 bootstrap，切换滚动自举（0.0.3）

分析确认 bin/yh-new（入库种子，含完整模块系统）可直接构建当前四模块
源码（产物模块 .s/.s.i 固定点验证 + run 语料 63/63），据此执行删除：

- **删除**：src/（C 版 stage0）、include/、lib/lib-arm64.c、config.h、
  libtcc.a/libtcc1.a 及目标文件、bootstrap/（seed 快照）、
  tools/flatten.py、tests/yh/container-yh*.sh（容器包装）、
  tests/selfhost/g3-acceptance.py 与 probe-main.c/macho.py（stage0
  容器验收链随 stage0 终结）。
- **构建切换**：Makefile 重写——`make` = `bin/yh-new build`（compiler/
  项目，一步链、冷编）产出 yh-new；`make seed` 滚种子（验证全绿后
  覆盖 bin/yh-new + 更新 SHA-256；macOS 下 cp 覆盖会触发 provenance
  拦截 SIGKILL，Makefile 内 tmp+mv+codesign 重签处理）。
- **验证门重组**：`make test` = ANTLR 语法 66/66+29/29 + 编译器语法
  模式 + run 语料 63/63（全部跑 yh-new；tests/yh/check.py 与
  tests/yh-run/check.py 的缺省编译器与相对路径改绝对，修复
  Path('./yh-new') 规范化成裸名后按 PATH 查找的 FileNotFoundError）。
  `make selfhost-native` = 重写后的 native-selfhost.py（bin/yh-new →
  cc2 → cc3 两代冷编，模块固定点一致 + cc3 自解析 25 源文件 + 全量
  语法/运行语料）+ modules 17/17 + 项目验收 23/23。
  tools/selfbuild-gate.py（四代链固定点，stage1=bin/yh-new）保留。
- **种子滚动**：bin/yh-new 已覆盖为当前源码产物
  （6e204dea841d508bf8879bdd895ec41c9055c396e3b369e6c44abb3d7d594fef）。
- **边界**（AGENTS.md/todo 已记）：滚动自举下源码不能在仓库内独立
  重建编译器（git 历史保留每代种子兜底）；stage0 差分参照、-run、
  交叉 ELF、g3 容器门终结；Linux 版含模块系统 yh-new 归档后另立
  Linux 开发/CI 流程。

## 2026-09-30 0.0.2 发布：bin/ 入库编译种子 + tag 触发 Release 归档

- **bin/ 入库副本**：Makefile 新增 `$(BIN_SEED)` 规则（挂进 `all`）——
  每次构建把 yh-new 复制到 `bin/yh-new` 并提交进仓库；clean 不清理
  （仓库内容物，非构建产物）。作为版本间编译种子：0.0.3 起删除
  src/（stage0）与 bootstrap/（seed）后，各版本直接用上一版二进制
  编译（Darwin 用 bin/ 副本，Linux 用上一版 Release 的 linux-arm64
  资产）。AGENTS.md 同步说明。
- **VERSION 0.0.1 → 0.0.2**；tag `0.0.2` 推送触发既有 release.yml
  流水线（双平台构建 + 冒烟 + tar.gz/sha256 归档到 GitHub Release，
  即"服务器保存一份"）。
- 顺手清理：Makefile 重构遗留的重复 `BOOTSTRAP_DIR` 定义去掉一处。
- **0.0.3 计划**（docs/todo.md「0.0.3 脱离 stage0」D1–D5）：删 src/ 与
  bootstrap/、构建链改为种子一步链、CI 改用上一版 Release 资产作
  Linux 种子、验证门重建为两代固定点。
- 本地验证：make（两步链 + bin 副本）幂等、bin/yh-new 冒烟通过；
  arm64 ubuntu:24.04 容器 make -j4 + 双冒烟 + bin/yh-new（ELF）冒烟
  通过——发布配方与新构建链兼容。
- **实际运行结果**：tag `0.0.2` 流水线
  [36630090430](https://github.com/lalavender/x/actions/runs/36630090430)
  一次全绿；Release
  [yh 0.0.2](https://github.com/lalavender/x/releases/tag/0.0.2)
  归档 4 资产（darwin/linux 各 tar.gz+sha256）；端到端验收：下载
  linux 包（内容 yh/yh-new/libtcc1.a）SHA-256 与 .sha256 资产一致
  （e6b8b3ca…381e），darwin 包内容 yh/yh-new。

## 2026-09-30 编译器源码四模块化完成（ADR-0007 P1–P5）：compiler/ 成为 mod.toml 项目，四代自举固定点达成

接上条（P0 恢复构建 / P4 热点拆分）。compiler/ 现在是真实的四模块
yh 项目（[ADR-0007](adr/0007-yh编译器使用源码模块.md)），自举编译器
用自身模块系统构建自身：

- **项目形态**：compiler/mod.toml（name="yh/compiler"，source="."，
  entry="cmd"）；gen（model/buffer/symbols/target/emit_arm64/sem_value/
  sem_expr/sem_call_literal/sem_flow/sem_decl，10 文件）、lex（lexer）、
  parse（parse_type/parse_expr/parse_stmt/parse_decl/parse_global_init/
  parse_module/iface，7 文件）、cmd（toml/project_state/project_index/
  project_resolve/module_build/compile/driver，7 文件）共 25 文件，
  全部 module 声明，依赖单向 gen←lex←parse←cmd（自家 topo 拒环）。
- **解环迁移**（四个函数入 gen）：sem_compile→cmd/compile.yh（P4 已做）、
  err_tok→gen/buffer.yh、tml_intern_str→gen/symbols.yh、
  mod_ns_lookup 与 mod_file_binding→gen/symbols.yh。
- **限定名改写**：约 3800 处脚本化（tools 内联脚本，符号表 723 项，
  状态机跳过注释/字符串/字符字面量，前导非 [.A-Za-z0-9_] 才改写），
  零跨模块同名冲突。pub 从宽（顶层+字段全 pub），收缩留后续。
- **P1 seed**：bootstrap/seed/compiler.yh = tools/flatten.py 扁平化
  产物（剥 module/import、剥字段 pub、去限定前缀——仅代码态），供
  stage0 编出「seed 编译器」。ADR-0007 对剥离式种子的保留意见成立：
  它是派生产物而非手工快照，正确性靠 P5 固定点背书，活跃源升级后
  需重新生成。
- **P2 探针**：fourdir/fourdirbad fixture（gen 公开状态与类型、
  lex/parse 限定调用、cmd 入口；私有字段跨模块拒绝），项目验收
  扩至 23/23。探针暴露 pj_canon 空段返回契约 bug（"." 折叠返回
  偏移被误判失败）——修复。
- **P3 构建迭代修复**：sizeof(m.T) 识别（sizeof_starts_type 限定
  判定）；if_emit_type 具名类型全表查询（pub 签名引用跨模块类型
  原样输出 mangle 名）；未使用导入被自家构建器拒绝后按实际使用
  收敛各文件 import。
- **P5 四代链**：tools/selfbuild-gate.py 固化——stage0→seed 编译器
  →cc2→cc3→cc4（每代冷编），cc2/3/4 两两 gen/lex/parse/cmd 全部
  .s/.s.i 逐字节一致（固定点），cc4 冒烟与 modules 17/17 通过；
  挂进 make selfhost-native。**日常 yh-new 切换为项目构建产出**
  （Makefile 两步链：stage0 编 seed → seed 编译器对活跃项目
  yh build，每次冷编避免缓存键缺编译器身份的问题）。
- **验证**：make（两步链）✓；make test 63/63 ✓；make selfhost-native
  全绿（seed 链三代自举、语法 66/66+29/29 ×3、模块语料 17/17 ×3、
  项目验收 23/23、selfbuild 四代固定点）✓；容器 make bootstrap ✓、
  make g3 通过 ✓；python3 tools/selfbuild-gate.py 全过 ✓。
- **过渡桥说明**：P3 迭代期曾用扁平化源编出一次性过渡编译器
  （yh-trans）打通四模块构建；P5 链建成后已由 seed 链取代，
  tools/flatten.py 保留为 seed 生成器。

## 2026-09-30 编译器源码按四目录布局恢复构建 + 热点文件拆分（ADR-0007 P0/P4）

用户已将 17 个编译器源文件归入 cmd/gen/lex/parse 四目录（另 model/
buffer/symbols/iface 暂留根部），旧路径使 Makefile 构建中断。本轮：

- **P0 恢复构建**：Makefile `SELFHOST_SOURCES` 与
  `tests/selfhost/native-selfhost.py` SOURCES 切到当前布局，并直接
  采用拆分后的文件清单（25 项）。`make`、`make test` 63/63、
  `make selfhost-native` 全绿（三代语法 66/66+29/29 ×3、三代模块语料
  17/17 ×3、项目验收 21/21、s2.s==s3.s 固定点一致）、容器
  `make bootstrap` 通过（G1+G2+固定点）、`make g3` **通过**
  （首次运行遇 B8 已记录的容器挂载瞬时问题，重跑全绿，全量日志
  /tmp/g3.log）。
- **P4 热点拆分**（按[详细方案](02-plan/yh-编译器模块化详细方案.md) §5
  的完整函数边界，纯移动不含语义改动）：
  - gen/sem.yh（2403 行）→ `sem_value`(329)/`sem_expr`(656)/
    `sem_call_literal`(461)/`sem_flow`(539)/`sem_decl`(262)；
    `sem_compile`(50) 迁 cmd/compile.yh（P3 解环预置）；
  - cmd/project.yh（1390 行）→ `project_state`(459)/`project_index`(408)/
    `project_resolve`(471)；
  - parse/parse_decl.yh（1215 行）→ `parse_decl`(640) +
    `parse_global_init`(542)。
  拆分按「前导注释块 + fn 到列 0 `}`」为单元脚本执行；恢复构建时
  发现 project.yh 头部的 `pj_scratch`/`pj_ls_cap` 两个文件级全局随
  头注释丢失，已补回（附边界注释）。所有文件回到 500±行建议带；
  gen/emit_arm64.yh（1014）按方案明确不拆。
- 回归说明：拆分为行为不变移动，回归由既有语料覆盖（run 48 的
  全局初始化/聚合/浮点/变参用例正好压住三簇被移动函数；语法 66+29；
  模块 17；项目 21），未新增语义用例。gen/sem_*.yh 与 cmd/project_*.yh
  等新文件均为原文件内容的逐字节子集（仅新增文件头注释与找回的全局块）。

## 2026-09-30 按用户现有 cmd/gen/lex/parse 目录修订编译器模块化方案

本轮重新核查用户已经移动的 13 个文件：内容与原 Git 版本逐字节
相同；compiler/mod.toml 为空，全部 17 个正式 .yh 文件仍无
module/import 声明。当前 `make -n yh-new` 失败，报旧依赖
`compiler/lexer.yh` 不存在；此前文档记录的构建成功是目录移动
发生**之前**的基线，不能用于当前工作区。

将现行[实施方案](02-plan/yh-编译器模块化详细方案.md)、
[架构设计](03-design/yh-编译器源码模块化设计.md)、
[ADR-0007](adr/0007-yh编译器使用源码模块.md)按既有目录重写；
旧 13 模块分类草案标为历史。具体调查、解环函数、文件拆分与
未运行代码验证的范围见
[本次修订记录](01-finished/yh-编译器按目录模块化方案修订-2026-09-30.md)。
本轮没有修改正式编译器源码或构建脚本。

## 2026-09-30 yh 编译器源码模块化方案与可行性探针

本轮交付[架构设计](03-design/yh-编译器源码模块化设计.md)、
[分阶段实施方案](02-plan/yh-编译器模块化详细方案.md)、
[ADR-0007](adr/0007-yh编译器使用源码模块.md)与
[完成记录](01-finished/yh-编译器模块化方案-2026-09-30.md)。
范围仅为调查、设计及 `tmp/` 探针，未移动正式编译器源码。

- 核对当前 17 个自举源码文件约 13,004 行、Makefile 和
  `tests/selfhost/native-selfhost.py` 双份固定拼接顺序；C stage0
  依 ADR-0006 冻结，不能编译带 `module/import` 的活跃源码。
- 检查 `compiler/iface.yh`：公开签名引用外模块具名类型时无法导出，
  所以旧 13 模块分类草案的批量 `pub` 不能直接成为执行步骤。
- 在 `tmp/compiler-modularization/probe/` 中，按当前顺序复制 17
  源文件并加 `module compiler;`，由现有 `yh-new build` 成功
  产出可执行编译器；该产物再次冷编同一项目，模块汇编 SHA-256
  均为 `4bd4ba108cd7a2b70e9825375ac3f443e40bfe65e13bd3c078ed8ca41d370730`。
  此探针仅证明单模块项目迁移入口可行。
- `GRAPHIFY_OUT=tmp/compiler-modularization/graphify graphify update .`
  得到 1510 节点、4432 边，但跳过 `.yh`，不能据此判定自举源码
  依赖；`graphify god-nodes` 的核心结果仍为 C 版。
- `make` 成功（已有目标无需重建）；`make test` 通过：
  语法正例 66/66、反例 29/29，运行/拒绝/接受语料 63/63；
  `make selfhost-native` 通过：
  三代语法、模块语法、运行语料和旧单文件固定点均通过，项目构建
  用例 21/21。本轮未运行容器 `make g3`。

结论：先冻结无模块 seed，使活跃编译器作为根 `mod.toml` 项目构建；
再更新四代冷编自举门、建立四个稳定职责模块。13 模块细拆需先过
跨模块具名类型接口和全局状态所有权门；本轮未实施这些代码阶段。

## 2026-09-30 模块与项目管理 MOD-U2..U5 全部交付（mod.toml 项目、三层解析、独立对象/接口、缓存与自举验证）

接上条 MOD-U0/U1。设计方案 §4–§12 的本地三层完整交付；按 ADR-0006 全部
在自举侧 `compiler/` 实现，stage0 冻结未动（除种子即所用 prelude 的既有
函数，无任何扩展）。新增 5 个源文件（约 2200 行 yh）：

- **`toml.yh`**（最小 TOML 1.0 子集）：节/裸键/基本与字面量字符串/整数/
  内联表/注释；多行字符串、数组、点键等显式拒绝。schema 校验在装载层
  （必填 name、未知字段、依赖表形状、行尾规则），诊断带 mod.toml 行号。
- **`project.yh`**：自 cwd 向上发现最近 mod.toml（≤32 层）；路径规范化
  （段栈消解 . / .. / //，依赖根去重、装载态防依赖环）；递归 `ls -1p`
  扫描源码根建索引（嵌套 mod.toml 目录属另一项目不进入；两阶段收集——
  目录条目名先入名字池再递归，规避共享 ls 缓冲被递归覆盖）；绑定层实现
  本项目→标准库（YH_STDLIB 指向一个标准库项目）→直接依赖的三层搜索，
  入口模块不可被导入、第三方同名歧义报两个提供方、缺失报已搜索层次、
  不回退；导入图 DFS topo（依赖序）+ 环路完整链诊断；`yh list
  [--resolve name]` 列出模块/文件与绑定来源。
- **`iface.yh`**：模块稳定接口 `<模块>.s.i`（`// yh-iface v1 arch=arm64
  suffix=…` 头行 + pub 类型（含字段 pub 标记）/fn 签名/const 折叠值/pub
  let 声明，正文即 yh 源码）；加载 = 头校验 + pass1 登记 + pass2a 折叠
  （c_iface_load 抑制发射与 bss 登记），随后把新增符号/类型名改写为
  「短名+后缀」并登记进 ModInfo.ns；类型归属 t_home 平行数组支撑跨模块
  pub 字段检查。边界：pub 签名引用其他模块的类型与 pub 指针（字符串）
  常量干净拒绝（类型闭包内联留待按需）。
- **`module_build.yh`**：`yh build [-o out] [module]` / `yh run` /
  内部 `--emit-module <mod> <提供方根> <主根> -o <out.s>`。每模块独立
  子进程（argv[0] 再入）加载依赖接口后两遍编译该模块全部文件 → 独立
  .s + 接口 .s.i；符号带 `__<sanitized-proj>__<mod>_` 后缀（pub→GLOBAL、
  私有→LOCAL、入口模块 main 裸名 GLOBAL），gcc/clang 一次链接全部 .s。
  U5 对象缓存：manifest = FNV-1a(后缀+entry+各源文件内容+各依赖接口
  内容+版本标记)，命中且产物齐全跳过重编译；解析不缓存，重绑定由
  构造保证（新增本地同名模块→绑定变化→依赖接口路径变化→hash 变化→
  重编译），冷热一致由发射确定性保证。
- **`driver.yh`**：项目命令分派（单文件三种旧形态不变）。

前端语义（U3）：限定名 `m.f`/`m.T`/`m.T { … }`（局部作用域遮蔽导入）；
未使用导入、导入名与顶层声明冲突、同模块重复顶层声明（报首次位置，
fn 路径的消息同步补齐）检查；跨模块私有字段读写、私有符号、位置式
构造含私有字段拒绝，命名式构造只可填 pub 字段。

**过程中修复的缺陷（含 3 个既有编译器缺陷 + 语料盲区）**：
1. `ty_push` 新增 t_home 平行数组扩容时**遗漏 `t_type_cap = ncap`**——
   自举编译器编译自身在类型表第二次扩容后堆越界（SIGSEGV in
   malloc/free），连带暴露 native-selfhost.py SOURCES 与 Makefile
   双清单需人工同步的老问题（本次两处已同步）。
2. **`em_store_sized`/`em_load_sized` 对 f64/f32 误用 x0**（值在
   d0/s0）：f64 字段命名字面量写坏、成员读取错值、跨模块聚合传参/返回
   值错（stage0 一直正确，自举侧与差分语料均未覆盖「浮点字段聚合」）。
   修复为按 tid 分派 s0/d0。
3. **浮点复合赋值 x10 保护压/弹不成对**（弹空栈，d1 从垃圾地址装入，
   段错误）：重写为两次「压栈保护 → lea 用 x10 → 弹回」的成对序列。
4. 类型化变参的**浮点元素误从 x 栈弹出**：补 FP 栈弹出路径（与
   sem_call 栈实参的浮点弹出同法）。
5. `lex_all` 不复位 lx_line/lx_lstart：多文件/接口加载后行号累计错。
6. 诊断消息拼接曾用「数组.to_type(*char)」（数组接收者语义与指针不同，
   传参退化才正确）：统一改为 intern 进名字池后经 np_cstr 取 *char，
   新增 `arr_cstr` 辅助。

**验证**：`make test` **63/63**（run 48/48 含新增 2 例、fail 12、pass 3）；
`make selfhost-native` 全绿（三代语法 66/66+29/29 ×3、run 全量、固定点
一致、modules 语法语料 **17/17**、项目验收 **21/21**）；`make bootstrap`
通过（G1 + G2 run 48/48 + stage3 自解析 + 固定点）；`make g3` **通过**（容器分代全量语料、stage2.s==stage3.s 密码学固定点、发射洁净度、诊断质量、SHA-256 归档全项通过）。三代 stage 的模块语法语料验证（17/17 ×3）已挂进 selfhost-native 门。
项目验收覆盖：两项目真实链接运行（含跨模块聚合/浮点/类型化变参/函数
指针/限定字面量）、TOML 语法与未知字段错误、传递依赖拒绝、双依赖同名
歧义、本地遮蔽标准库与标准库兜底、导入环、入口模块不可导入、私有字段/
私有符号/位置式私有构造拒绝、同模块重复声明、未使用导入、导入名冲突、
接口头损坏拒绝重建、缓存命中、重绑定后重编译与结果一致。
新增语料：`tests/yh-run/run/47-float-struct-fields.yh`、
`run/48-float-compound-assign.yh`（stage0 与自举双侧通过）；模块语料
`tests/modules/`（语法 17 + 项目 21，runner 均已挂进 selfhost-native 门）。

**边界与后续（MOD-U6）**：本地三层（当前项目/标准库/直接依赖）已完整；
远程获取、版本规则、锁文件、工作区按方案明示「按实际需求另定」，需求
出现时另立设计与验收用例，不沿用旧 Go 方案承诺。已知工程边界：目录与
环境访问经 system+ls/printenv（stage0 prelude 冻结无 opendir/getenv），
路径含空格/引号不受支持；接口不携带类型闭包（pub 签名引用他模块类型
干净拒绝）。

## 2026-09-29 模块与项目管理 MOD-U0 + MOD-U1（自举侧 module/import 语法）

[设计方案](03-design/yh-模块与项目管理设计.md) /
[实施方案](02-plan/yh-模块与项目管理实施方案.md) /
[ADR-0005](adr/0005-yh-mod-toml与按名称导入.md) 的首个代码阶段。
按 ADR-0006 冻结规则，实现只在自举侧 `compiler/`（stage0 不识别新语法，
语法方案 §3 的「不直接改写 yh.g4」继续成立，ANTLR/stage0 语料不进新语法）。

- **MOD-U0 基线**：`make test` 61/61（run 46/46、fail 12/12、pass 3/3）、
  `make selfhost-native` 全绿（语法 66/66+29/29、run 全量、固定点一致）。
  兼容边界确认：旧单文件形态（无 module）必须保持不变。
- **词法**：`compiler/model.yh` 新增 TK_MODULE=42、TK_IMPORT=43（仅文件头
  使用，不放开成员名；42..43 落在 is_member_name 区间之外，无回归），
  `compiler/lexer.yh` kw_kind 识别 `module`/`import`。语料与编译器源码
  均未占用这两个标识符（已全仓核查）。
- **模块头解析**（新文件 `compiler/parse_module.yh`，约 170 行）：
  `mod_parse_head` 在 parse_source 开头消费「module IDENT; → import IDENT;*」，
  固定顺序、单次 module、`_` 不作模块/导入名、同文件重复导入报错、
  import 脱离 module 报错、错位 module/import 给出位置诊断；
  导入表（ImportEnt，名字 intern 到名字池）随解析登记——单文件形态的
  FileID 即 c_path，多文件模块索引按方案留给 MOD-U2。
  `mod_skip_head` 供 pass 2a/2b 子遍跳过头部 token。
- **限定类型**：`compiler/parse_type.yh` parse_type_ref 接受 `m.T`（含
  更长链）点号段；纯语法模式接受（未知模块不是语法错误），编译模式
  给出「限定类型需要模块语义（尚未实现）」的明确诊断（此前是
  「期望 ';'」）。
- **pub 字段**：struct/union 字段接受 `pub` 前缀；SField 新增 is_pub
  登记（布局与访问不变，跨模块检查按方案在 MOD-U3）。注意 `pub`自此
  不能再作字段名（原本 pathological 场景，无语料依赖）。
- **测试**：新 runner `tests/modules/check.py` + 语料 accept/ 7 例、
  reject/ 10 例（17/17）。该 runner 只跑自举产物（yh-new
  --syntax-check），已挂进 `make selfhost-native` 门；不与 stage0 语料
  混跑。
- **修一处基建遗漏**：`tests/selfhost/native-selfhost.py` 的 SOURCES
  清单与 Makefile SELFHOST_SOURCES 是两份人工同步的列表，本次新增
  parse_module.yh 时漏改前者，stage0 编译拼接源报
  `'mod_parse_head' 未声明`（自举侧支持顶层前向调用，但文件必须真的
  拼进来）。已同步，并在后续阶段考虑收敛为单一清单来源。
- **验证门**：`make` 零警告；`make test` 61/61；`make selfhost-native`
  全绿（三代语法 66/66+29/29 ×3、run 全量、汇编固定点一致、modules
  17/17）；`make bootstrap` 通过（G1 + G2 三代闭环 + stage3 自解析 +
  全量固定点）；`make g3` **通过**（首次运行的 run/39 报容器内
  permission denied 为 B8 已记录的 macOS Docker 挂载元数据瞬时假失败，
  重跑全绿，归档见 tmp/bootstrap/artifacts/）。
- **后续（MOD-U2，未实施）**：TOML 清单与 schema、模块头索引、
  本项目→标准库→直接依赖三层搜索、导入者上下文、歧义与不回退诊断；
  未使用导入/导入名与声明重名的语义检查连同模块作用域在 MOD-U3。

## 2026-09-29 GitHub Actions 发布流水线：tag 触发归档 yh/yh-new 到 Release

- 新增 `.github/workflows/release.yml`：推送任意 tag 触发，双平台构建
  `yh`（stage0 种子）与 `yh-new`（自举编译器），冒烟验证后用
  `gh release create` 归档 tar.gz + sha256 到 GitHub Release：
  - `linux-arm64`：ubuntu-latest + QEMU 仿真 arm64 容器（ubuntu:24.04，
    与 `make g3` 验收环境同版；免费私有仓库无 arm64 原生 runner），
    产物 AArch64 Linux ELF；
  - `darwin-arm64`：macos-14（M1）本机构建，产物 Mach-O；
  - 冒烟 = yh-new 与 yh 各编译运行一遍 hello。libtcc1.a 仅 ELF 链接需要
    （tcc_add_runtime 只在 ELF 输出路径调用；本机 Darwin 无
    /usr/local/lib/tcc 亦一切正常），Linux 冒烟用 `YH_LIBDIR=/build`
    按开箱状态验证，Linux tarball 因此多带一个 libtcc1.a（make 产物）。
- 修复原生 AArch64 Linux 构建找不到 crt1.o（容器实测暴露）：Debian/
  Ubuntu 的 crt1.o/crtn.o/libc.so 在 multiarch 目录
  （/usr/lib/aarch64-linux-gnu），tcc 默认只搜 /usr/lib。Makefile 在
  `HOST_OS-HOST_ARCH = Linux-aarch64` 时给 CPPFLAGS 注入
  `-DCONFIG_TRIPLET="aarch64-linux-gnu"`（tcc.h 的 USE_TRIPLET/
  ALSO_TRIPLET 使 crt/库/头文件路径带上 multiarch 段）。同时 YHNEW
  规则加 `-B $(TOP)` 并把 `$(LIBTCC1)` 列为前置条件：Linux ELF 链接
  必需 libtcc1.a，指向仓库根刚构建的副本（顺带消除 -j 并行竞态）。
  仅构建配置，不触碰冻结的 stage0 源码；Darwin 的 Mach-O 路径不读
  libtcc1 与 crt（本机无 /usr/local/lib/tcc 亦一切正常），交叉路径
  （stage1 自带 -sysroot/-B）不受影响。
- 本地验证（推 tag 前）：arm64 ubuntu:24.04 容器 `make -j4` 成功，
  yh-new 与 yh 冒烟通过（YH_LIBDIR=/build，file 确认 AArch64 ELF）；
  Darwin 本机 make + 冒烟通过。
- 实际运行结果：tag `0.0.1` 首次运行两构建作业全绿、release 作业失败
  （gh 无 .git 无法推断仓库，release 作业无 checkout）——修复为显式
  `GH_REPO` 环境变量后重打标签重跑，**全绿**：
  [run 36549353118](https://github.com/lalavender/x/actions/runs/36549353118)。
  Release [yh 0.0.1](https://github.com/lalavender/x/releases/tag/0.0.1)
  归档 4 个资产（darwin/linux 各 tar.gz + sha256）；端到端验收：下载
  linux tar.gz，内容为 yh / yh-new / libtcc1.a，SHA-256 与 .sha256
  资产一致（e5d7b269…d4d1a961）。

## 2026-09-29 explorer 两项：Ctrl+C 退出修复 + 复制按钮

- **Ctrl+C 无法退出（根因：Python 3.14 默认 SIGINT 处理器的延迟抛出
  机制）**：主线程阻塞在 `serve_forever`/`time.sleep` 这类 syscall 时，
  Ctrl+C 打断 syscall 后只恢复重试、不抛 KeyboardInterrupt（最小复现
  确认，连裸 `time.sleep(30)` 也不被默认 handler 打断）。修复：显式
  安装「抛 KeyboardInterrupt」的 SIGINT handler + `serve_forever` 移入
  daemon 线程 + 主线程 `join(0.3)` 短等待循环双保险；顺带把启动打印
  加 `flush=True`（重定向时缓冲导致看不到输出）。实测 SIGINT 后干净
  退出。
- **编辑器复制功能**：左栏头部新增「复制」（复制 yh 源码全文），右栏
  头部新增「复制」（复制汇编原文，取高亮层 `textContent`，保留编译器
  原始 tab 缩进）。`navigator.clipboard.writeText` 优先、隐藏 textarea
  + `execCommand` 降级，成功后按钮闪现「已复制 ✓」1.2 秒。浏览器实测
  剪贴板读回与源内容一致。

## 2026-09-29 浏览器图形界面 yh Compiler Explorer（tools/）

新增本地浏览器版编译器浏览器（仿 Compiler Explorer / godbolt 布局）：
左侧 yh 源码编辑器（语法高亮、行号、自动缩进、示例加载、localStorage
自动保存），右侧 AArch64 汇编视图（编辑防抖 700ms 自动刷新），绿色
Run 按钮编译链接并运行，底部控制台展示程序 stdout/stderr/退出码与
编译诊断；中间分栏可拖拽。

- `tools/yh-explorer.html`：自包含单文件界面（无外部依赖，One Dark
  配色）。浏览器不能直接执行本地二进制，页面经三个接口与本地服务器
  通信：`GET /api/defaults`（探测仓库根 yh-new/yh）、`POST /api/compile`
  （`--emit-asm` 发射汇编）、`POST /api/run`（`-o` 编译链接后运行，
  崩溃/超时才算失败，故意非零退出码原样展示）。
- `tools/yh-explorer.py`：仅标准库的本地服务器，监听 127.0.0.1（缺省
  端口 8765，`--port`/`--no-browser` 可调），临时产物在
  `tmp/yh-explorer-work/`。编译器支持下拉快捷切换（yh-new 自举 /
  yh stage0 / 自定义路径）并叠加编译选项（如 `-target`）。
- 入口：`make explorer`（新增 Makefile 目标）。
- 本次未修改编译器本体，按约定不新增 tests .yh 用例；工具链路以
  浏览器端到端验收替代（hello 示例 Run 输出 `hello, yh!` 退出码 0、
  square 示例自动编译通过、非法源码诊断正确显示）。stage0 `yh` 只支持
  全量编译运行（下拉标注「仅 Run」，API 实测 Run 正常），不支持
  `--emit-asm` 汇编发射，汇编视图仅自举侧可用。

## 2026-09-29 `make` 默认产出自举编译器二进制 `yh-new`（项目根目录）

落实 ADR-0006 的构建侧：`make` 现在在项目根目录产出**两个**二进制——

- `yh`：stage0 种子（C 版，冻结），bootstrap 交叉编译 stage1 的种子；
- `yh-new`：**自举编译器本机形态**（stage0 种子编译 compiler/ 拼接源码
  产出；Darwin → Mach-O，Linux → ELF），即 ADR-0006 的主要开发编译器。

要点与坑：
- `$(YHNEW)` 规则必须放在 `BOOTSTRAP_DIR` 定义**之后**——make 的规则
  前置条件列表是**即时展开**的，先定义后引用才不会展开成空；
- `clean` 同步清理 `yh-new`；help 文本更新；
- 验证：`make clean && make` 周期正常、二次 `make` 幂等；make 产出的
  `yh-new` 直跑全量语料——运行 **61/61**、语法 **66/66 + 29/29**（绝对
  路径传给 check.py；相对路径在其内部 cwd 处理会失配）；四门不受影响
  （bootstrap/g3 仍以 `./yh` 为种子）。

## 2026-09-29 深帧寻址根因根除（x12 专用临时）+ 差分压测框架，自举 80/80 达标## 2026-09-29 深帧寻址根因根除（x12 专用临时）+ 差分压测框架，自举 80/80 达标

接上节 for-in 区间修复后的继续探索，两件事：

**1. 一族深帧缺陷的总根源根除**。run/27 修复后差分压测仍暴露两个
SEGV，lldb 定位崩溃指令 `str x0, [x10, #8]` 的 x10 = 立即数 768——
`em_lea_local_down` 深帧形态（`movz x10, #off; sub x0, x29, x10`）
把 **x10 当临时**，而调用方（变参打包的切片 data 写入）以为 x10 仍是
前一条 `lea_local_to` 的槽地址。审查发现 lea 四原语的深帧临时分别
借用 x10/x9——本轮 run/27、上轮栈实参/区间长度的全部覆盖 bug 都源于
这个「原语借用调用方活跃寄存器」的设计。**修复**：四个原语的深帧
临时统一改为专用 **x12**（此前全文件零使用），注释写明契约；调用点
此前的 x9→x11 修复保留为双保险。

**2. 差分压测框架落地（tmp/dt-gen.py）**：固定种子生成确定性随机
程序——深帧 24–46 个局部、12 参走栈调用、for-in 区间/数组、复合
赋值、短路、递归聚合、类型化变参、浮点混合、全局变量——stage0 与
自举产物双编译对跑，比对 stdout 与退出码。**自举侧 80/80 无差**
（2 例差异经最小化为 stage0 自身错误）。

**压测顺带记录 stage0 参照系缺陷六项**（均不影响自举链，规避后差分
可继续）：
| # | 缺陷 | 症状 |
| --- | --- | --- |
| S1 | u64 局部变量 store | `store(1, (3,0,…))` 断言崩溃（arm64-gen.c:581） |
| S2 | 深帧下多个 switch | 同上断言，最小化到 let+switch 即触发 |
| S3 | 深帧下三元 | 同上断言 |
| S4 | 数组形参直接 for-in | 「for-in 的遍历对象必须是数组或切片」误拒 |
| S5 | 聚合返回值直接作实参 | 同 S1 断言 |
| S6 | 深帧聚合局部零初始化失效 | 局部数组读出垃圾（自举输出正确 0） |

**验证（全门绿）**：`make test` 61/61；自举 Darwin 本机语法 66/66+
29/29、运行 61/61；`make selfhost-native` 全量用例全绿；`make
bootstrap` 全绿；`make g3` 通过，新固定点 `stage2.s == stage3.s`
SHA-256 `c23883cb…8b475b56`。

## 2026-09-29 自举阻塞缺陷清零：for-in 区间深帧寻址修复，自举产物本机接管达标## 2026-09-29 mod.toml 与名称导入的模块方案修订（尚未实施）

按用户新要求，采用 mod.toml 项目清单、module 源码归属、import 名称
导入；搜索顺序为当前项目、标准库、第三方，没有 internal 特殊机制。
补齐同模块多文件、文件导入作用域、依赖自己的解析上下文、高层绑定
失败不回退、同层歧义、直接依赖和项目限定身份规则。

交付 [当前语言设计](03-design/yh-模块与项目管理设计.md)、
[实施清单](02-plan/yh-模块与项目管理实施方案.md)、
[ADR-0005](adr/0005-yh-mod-toml与按名称导入.md) 与
[修订报告](01-finished/yh-mod-toml模块方案修订报告.md)。旧方案入口标记
被替代，todo 更新为 MOD-U0–U6，代码任务保持未完成。

文档相对链接、代码围栏、差异空白与 TOML 示例解析检查通过，记录位于
tmp/mod-design/doc-check.json。make 返回成功，默认产物已最新。
本轮仅修改方案和记录，没有修改 grammar／编译器／测试源码或创建真实
mod.toml；没有新增模块用例，也未将 make 的既有构建结果当作模块功能
验证。工作区已有的其他代码和测试改动保留，未在本任务中编辑或验收。

## 2026-09-29 自举阻塞缺陷清零：for-in 区间深帧寻址修复，自举产物本机接管达标

接上节 A'（栈实参错位）之后的 A'' 残余（run/27 在自举产物上
`range=37128`）。本轮定位到**真正的根因**并清零：

**根因（不是槽重叠）**：`sem_forin_begin` 区间路径把终点装入 x9 后，
data 槽的 `em_lea_local_to` 在偏移 >255 时用 `movz x9, #off` 拼地址，
覆盖终点——区间长度 = 「槽偏移 - 起点」= 287 而非 4，循环多跑 283 次。
小帧时 lea 走 `sub x10, x29, #imm` 不碰 x9，所以所有单项 mini 复现
通过、只有 run/27 的深帧场景触发。

**修复（compiler/sem.yh，4 处）**：
1. for-in 区间：终点改用 x11（`sub x11, x11, x0` 算长度）；
2. for-in 数组：len 常量改为「先取 len 槽地址、后装 x9」；
3. for-in 聚合元素绑定：删「`mov x9, x0` 保地址」——深帧 lea 覆盖 x9
   使 copy_block 源错；改为先取绑定槽地址（x10）、x0 天然保持元素地址；
   同时补回标量路径的 `mov x10, x0`（em_load_sized 从 x10 读——修复
   过程中曾误删，由 mini-aggr3 钉住）；
4. 聚合局部清零循环：计数器 x9 改为在 lea 之后装载。

**同类模式全文件扫描**：x9 活跃值 + 随后 lea 的窗口共 7 处，其余 3 处
为「立即消费」安全形态（含误报）。

**验证（全门绿）**：
| 门 | 结果 |
| --- | --- |
| `make test`（stage0） | 61/61 |
| 自举 Darwin 本机（s1 产物直跑语料） | **语法 66/66 + 29/29、运行 61/61** |
| `make selfhost-native` | 全绿——重构后跑**全量 run 用例（含 printf）**，不再按「macOS 变参不可判」过滤 |
| `make bootstrap` | 全绿（G1 + G2 run 46/46 + 固定点） |
| `make g3` | **通过**，新固定点 `stage2.s == stage3.s`，SHA-256 `1279cf29…50a92b` |

**自举产物接管（本节主题）就此达标**：stage1 在 Darwin 本机以
`yh file -o out`（双形态 CLI、宿主自动方言探测）直出可执行并跑下全部
运行语料；`make selfhost-native` 的语义验证升级为全量用例。C 版 stage0
从「日常编译器」降级为「种子与差分参照」的条件已经具备——剩余事项
（`-c`/`-run` 等能力、每平台种子二进制归档流程）见 todo 多平台与接管
条目。

## 2026-09-29 自举回归修复 + 六项语言缺口双侧落地 + 三个 stage0 缺陷修复，G3 复验通过## 2026-09-29 Go 风格语言模块化方案交付（尚未实施）

按用户纠正，将方案范围改为 yh 用户程序的 module/package/import。
交付 [语言设计](03-design/yh-Go风格模块与包设计.md)、
[实施清单](02-plan/yh-Go风格模块化实施方案.md) 和
[ADR-0004](adr/0004-yh-Go风格模块与包.md)。参考 Go 官方包规范与模块
说明，明确保留 yh 的 pub 和分号，支持目录包、文件级导入、跨包类型、
本地依赖，并规划独立产物／缓存／远程 MVS／工作区。

原内部重构任务因理解范围有误撤回，历史交付保留记录。没有修改 grammar、
编译器、构建脚本或测试源码，没有运行或宣称模块功能通过；工作区其他
ABI 与测试改动保持原样。完整记录见
[Go 风格方案交付报告](01-finished/yh-Go风格模块化方案交付报告.md)。
新增文档与更新入口的链接／围栏检查及 `git diff --check` 通过。

## 2026-09-29 内部结构方案历史交付（范围误读，已撤回执行清单）

完成两套编译器的源码／依赖调查，交付
[模块化详细方案](02-plan/yh-编译器模块化详细方案.md) 与
[提议 ADR-0003](adr/0003-yh编译器渐进模块化.md)。建议保留直接生成流程，
依次统一构建清单、明确状态归属、拆分语义／生成／ABI／输出边界，
再有限整理 C 版引导接口；完整 AST／IR 和默认编译器替换另立任务。

实际验证：`make` 成功（产物已最新）；`make test` 的 ANTLR 和编译器语法
各 66/66 正例、29/29 反例；Darwin 运行 44/44、拒绝 12/12、仅编译 3/3，
合计 59/59。graphify update/god-nodes 已执行；图为 1,328 节点、4,283 边，
但 `.yh` 未覆盖、12 个 C／头文件部分解析异常，不能单独作为删除依据。

本任务没有修改编译器／测试代码、没有新增 `.yh` 测试或执行三代自举门。
保留 todo 原有修改和期间出现的 sem／emitter 代码改动；这些改动不属于
本任务，也未在本任务中完成自举验收。P0–P9 均未勾选完成。
调查日志在 `tmp/modularization/`；长期记录见
[方案交付报告](01-finished/yh-模块化方案交付报告.md)。
新增文档的本地链接与代码围栏校验通过，`git diff --check` 通过。

## 2026-09-29 自举回归修复 + 六项语言缺口双侧落地 + 三个 stage0 缺陷修复，G3 复验通过

**起点**：分析进度时发现最新未提交改动（Darwin 方言 + `-o` 兼容层）引入
自举回归——G2 运行语料 run/14 段错误，`make bootstrap` 红。本轮修复回归、
清掉 todo 盘点 B/C/D 三节全部账目，四道验证门全绿。

### 1. 自举回归修复（sem_call 栈实参）

Darwin 变参改造误删 GNU/Linux 路径的栈实参写入循环：新代码只在
`darwin_var == 1` 时写栈槽，无 else——超过 8 个整型参数的调用不写
调用点栈区，stage2 编译 run/14 段错误。修复：补 else 分支恢复
`for j >= TG_ARG_REGS { pop x9; em_call_stack_store(...) }`（循环变量
改名 `saj` 避开 stage0 的 if/else 无块级作用域重声明）。新增
run/37-many-args-noprintf（无 printf 的超 8 参用例，本机 native 门
也能执行——此前 run/14 含 printf，native 门按约定跳过，拦不住这类回归）。

### 2. stage0 缺陷修复（三个）

- **零初始化全局 `-o` 误报 redeclaration**：pass 1 对零初始化全局提前
  落地符号，pass 2 重复登记触发 `sym_push` 报错。修复：pass 1 统一
  不落地全局变量（`yh_parse_binding` 早退），与带初始化路径一致。
  用例 run/38-zero-init-global。
- **Mach-O 重定位记账缺陷**（新发现）：节头 `nreloc` 按 ELF 条数记账，
  但非零 addend 的重定位会多写一条前置 ADDEND 条目，ld64 按声明数
  截断尾部条目——悬空 ADDEND 触发「relocation not supported」（全局
  数组下标直接链接失败），或 printf 的 CALL26 丢失使懒绑定桩悬空
  （程序运行挂起、反汇编显示全局字段读写偏移错位）。修复：
  `macho-out.c` 按 Mach-O 实际条目数记账（新增 `nreloc_elf` 供写出
  循环遍历 ELF 重定位；统计与写出规则一致：非零 addend 的
  UNSIGNED/PAGE21/PAGEOFF12 各补一条 ADDEND 前置条目）。修复后
  `make test` 从 51/51 隐性损失恢复全绿，全局数组/结构体用例可用。
- **语法模式全局表未初始化崩溃**（新发现，native 自举差分门暴露）：
  `ty_register_builtins` 只在 `--emit-asm` 路径调用，语法模式
  `t_types` 为 NULL；自举编译器新加的实参预期类型代码在语法模式读
  `t_types[res.type_id].sub` 段错误（compiler.yh 自解析靠未初始化栈
  垃圾侥幸通过，语料用例稳定崩溃，lldb 定位崩溃地址 0x14 = offsetof
  (CType, sub)）。修复：调用实参分支限定 `c_compile != 0` 且校验
  `TY_FN` 类型（非函数被调者的 sub 是字段表起点，会误当签名号）。

### 3. 语言缺口六项落地（stage0 与自举双侧，均有 run 用例钉住）

| 特性 | 自举侧 | stage0 侧 | 用例 |
| --- | --- | --- | --- |
| 全局聚合初始化 | `parse_global_struct_init`（命名/位置/嵌套/字符串） | 字节镜像 + 节内 R_DATA_PTR 重定位 | run/40 |
| 全局数组/切片零初始化 | 移除 pass 1 拒绝，`.bss` 发射泛化 | 已有（`.bss`） | run/39 |
| 数组/切片字面量 | `parse_array_literal` + 预期类型管道（let 初始化/赋值 RHS/调用实参） | primary `'['` + `yh_expect_type` 管道 + 全局数组字面量字节镜像 | run/43 |
| 切片表达式 `a[s..e]` | `sem_slice`（无分支钳制 + 视图临时） | 后缀链 RANGE 分支（`vdup` + 位技巧钳制） | run/42 |
| 嵌套类型声明 | `c_nested_type` 旗标（pass 2 也登记） | 块语句分派直接复用顶层解析 | run/44 |
| `sizeof(expr)` | `em_put` 处 `c_em_suppress` 发射闸门 + 类型名判定 | `nocode_wanted` 抑制 + 星号链捕获重放前瞻（区分 `sizeof(*p)` 与 `sizeof(*T)`） | run/41 |

边界（如实记录）：stage0 全局切片字面量暂不支持（干净拒绝）；全局
f32 字段/元素初始化暂不支持（要求 f64）；stage0 全局数组字面量字符串
元素拒绝；自举侧 `parse_global_array_init` 元素上限 64。

### 4. 顺带修复的自举编译器既有缺陷（新特性开发牵出）

- `len(数组)` 编译期折叠不物化：`sem_len` 数组分支只设常量 Res 未发
  `mov x0, len`，且实参聚合地址语义残留（`c_res_is_addr` 未清）——
  `return len(arr)` 返回数组地址。此前运行语料从未覆盖 `len(数组)`
  表达式（run/28 只测切片）。
- 聚合整体赋值只拷 8 字节：`sem_assign` 的 TK_ASSIGN 分支误走标量
  store。修复：聚合按块拷贝（`em_copy_block`），兑现「数组同型赋值 =
  值复制」语义（语义边界 §，M0-04 定案）。
- `macho.py` LIBC 集合补 `system`/`unlink`（driver `-o` 兼容层新引用），
  `tests/selfhost/probe-main.c` 补两个桩（native 门不真调链接器）。

### 5. 验证门（全部通过）

| 门 | 结果 |
| --- | --- |
| `make test`（stage0 本机） | **59/59**（run 44 + fail 12 + pass 3） |
| `make selfhost-native`（Mach-O 三代差分） | 全绿：三 stage 自解析、语法 66/66+29/29、stage2 运行语义、**汇编固定点一致** |
| `make bootstrap`（容器官方门） | 全绿：G1 66/66+29/29、G2 三代闭环 + run 语料 44/44、G2+ 固定点 |
| `make g3`（G3 正式验收） | **通过**（19 项检查；stage1/2/3 分代全量 59/59；44 个代表程序固定点；诊断质量 53 反例；产物归档） |

**新固定点**：`stage2.s == stage3.s`，SHA-256
`9c5cfc78529b00e9aa7ab4315463e8583e0f15d15719400dc279b75996413fa8`
（compiler.yh `6ff49c39…b40a`，8678 行）。

### 6. G3 验收脚本增强

- 分代运行语料失败自动重试一次：macOS Docker（VirtioFS）挂载偶发
  元数据延迟，ELF 刚写完权限位短暂不可见，曾致 run/16 与本轮 stage3
  语料「permission denied」假失败；重试仍失败才是真回归。
- `-o` 兼容层冒烟检查（stage1/2/3 直出可执行、临时文件清理、错误源
  非零退出）已在验收清单中。

### 7. 文档同步

- `docs/todo.md` 盘点节改写：A 无阻塞、B 六项勾选（两项设计决定如实
  标注）、C 三项修复、D 文档账目清零。
- `docs/02-plan/yh-自举实施方案-v2.md` B3–B7 的 14 个任务项 checkbox
  全部勾选。
- 本文件记录本轮全部改动。自举编译器源码 7952 → 8678 行。

## 2026-09-28 自举 B8 完成：新增 `make g3` 正式验收，G3 达成

在上一节的 `make bootstrap` 全绿基础上，补齐 B8 的全部验收项并脚本化。

**新增**：

- `tests/selfhost/g3-acceptance.py` 与 `make g3`（`= make bootstrap` +
  验收脚本）：在 Ubuntu 24.04/aarch64 容器内做
  1. 前置检查（容器 / sysroot / stage1..3）；
  2. **分代全量复验**：stage1、stage2、stage3 各自跑全部语法（66/66 +
     29/29）与运行语料（50/50，交叉 ELF 在容器内执行），要求无崩溃、
     超时或 SKIP；
  3. stage3 自解析 + 自编；
  4. **汇编固定点**：`stage2.s == stage3.s`（compiler.yh）**且 35 个代表
     程序全部逐字节一致**；同一 stage 重复发射一致（无时间戳/随机）；
  5. 发射内容不含宿主绝对路径/日期；**诊断质量**：53 个反例全部非零退出、
     带 `文件:行:列: 错误:` 诊断、不把汇编泄漏到 stdout；
  6. 归档源码/汇编/ELF/工具链版本/SHA-256 到 `tmp/bootstrap/artifacts/`。
- `tests/yh-run/run/35-mixed-args.yh`：混合整型/浮点形参回归用例
  （免 printf，退出码断言）。
- `docs/01-finished/G3-自举验收报告.md`：正式验收报告（判据、证据、
  SHA-256、G3 语言验收表逐行核对、边界与后续）。

**本轮修复的第三个自举缺陷**

- **混合整型/浮点形参的寄存器分配**：AAPCS64 的整型参数寄存器 x0..x7 与
  浮点参数寄存器 d0..d7 各自独立计数，但 `parse_decl.yh` 把形参在参数表
  中的**位置下标**当寄存器序号传给 `sem_declare_param`，使
  `scale(v f64, k int)` 的 `k`（第 2 个形参）错读 **x1**（应为 **x0**），
  浮点+整型混用的调用算出垃圾值。修复：参数循环为整型/浮点各维护独立
  计数器（`ipos`/`fpos`），按类型递增后传「本类型内序号」。
- **回归证据**：回退修复后 stage1 编译 `run/35` 退出码 1（失败），修复后
  42（通过）。

**验收结果**：`make g3` 全绿（19 项检查）；关键点——`stage2.s` 与
`stage3.s` 的 SHA-256 同为
`e442b52eacfc1e84a3b5b32855360d44c41119d7d381ae62b848b1d94d686402`。

**结论**：**G3 达成**（完整编译器自举）。B7、B8 均完成。唯一未实现的
语言特性仍是全局聚合变量初始化（不阻塞 G3）；是否替换默认 `yh` 另立验收。

## 2026-09-28 自举 B8：`make bootstrap` 全绿，达成 G3

**环境更正**：此前误判「docker 不可用」——实际 docker CLI 位于
`/opt/homebrew/bin/docker`（Homebrew 安装，context=colima），只是当前
shell 的 `PATH` 被精简为 `/usr/bin:/bin:/usr/sbin:/sbin` 而找不到它；
容器 `yh-build`（ubuntu:24.04，aarch64）一直运行中，`/work` 挂载与
`tmp/sysroot` 均正常。加上 PATH 后官方自举门可正常执行。

**本轮修复（B8 门首次全量执行时暴露的第三个自举缺陷）**

- **缺陷**：混合整型/浮点形参的寄存器分配错误。AAPCS64 规定整型参数寄存
  器 x0..x7 与浮点参数寄存器 d0..d7 **各自独立计数**；但 `parse_decl.yh`
  把形参在参数表中的**位置下标**当作寄存器序号传给 `sem_declare_param`。
  于是 `scale(v f64, k int)` 的 `k`（第 2 个形参）被错读为 **x1**，正确
  应为 **x0**（它是第 1 个整型参数），导致浮点+整型混用的调用算出垃圾值。
- **修复**：在 pass 2 的参数循环中为整型/浮点各维护独立计数器
  （`ipos`/`fpos`），按类型递增后把「本类型内序号」传给
  `sem_declare_param`；聚合形参走整型寄存器序列，同用 `ipos`。
- **回归用例**：`tests/yh-run/run/35-mixed-args.yh`（免 printf，退出码
  断言）覆盖 1 浮点+1 整型、整型在前、以及 `f0 i0 f1 i1` 交错四种形态。
  证据：回退修复后 stage1 编译 run/35 退出码 1（失败），修复后 42（通过）。

**`make bootstrap` 结果（Linux 容器内，官方门）**

| 门 | 内容 | 结果 |
| --- | --- | --- |
| 拼接确定性 | 两次拼接逐字节一致 | ✅ |
| G1 | stage1 自解析 + 全量语法语料差分 | ✅ 66/66 + 29/29 |
| G2 | stage1→stage2；stage2 自解析 + 语法差分 | ✅ 66/66 + 29/29 |
| G2 | stage2 全量运行语料（run/ 全部） | ✅ **34/34**（含 run/28 浮点、30–34） |
| G2+ | stage2→stage3；stage3 自解析 | ✅ |
| G2+ | **stage2.s 与 stage3.s 对自身拼接源码逐字节一致** | ✅ **固定点** |

**结论**：B7 完成；G3 的硬判据（stage1/stage2 同样通过全量语料 + 两代
对固定输入发出逐字节相同汇编）在真实 aarch64 Linux 环境达成。B8 剩余项
（stage1/2/3 全量分代跑、代表程序固定点、产物与哈希归档、G3 验收表逐行
核对）见后续条目。

## 2026-09-28 自举 B7 收尾：修复两处自举缺陷，达成全量固定点（stage3 汇编逐字节一致）

上一轮 B7 遗留「stage2 编译浮点字面量时常量位型被编码为 `fp64_bits`
函数地址」的已知缺陷。本轮定位并修复其**根因**，并顺带修掉同源的另一处
转换缺陷；`make bootstrap` 门因此恢复为**全量运行语料 + 全量汇编固定点**。

**修复 1：浮点实参压栈走错通路（`sem_push_arg`）**

`sem_push_arg` 无条件调用 `em_push()`（压 x0），但浮点实参的值在 d0。
在 `fp64_bits(mant)` 这类「先 `adrp` 装入 callee 地址、再以浮点值调用」
的序列里，x0 恰好是 callee 地址，于是被当成实参压栈，`fp64_bits` 收到
函数地址而非 f64 值，返回位型即成代码地址（旧记录中的 `0x4160676`）。
修复：改走 `sem_push_value`（浮点压 d0）。调用点的混合搬运路径同步改为
**按元素类型分别弹出 x0/d0**。

**修复 2：缺少「整数 → 整数」窄化转换（`sem_cast`）**

`sem_cast` 只处理了浮点相关的四类转换，整数→整数（如 `i64 → int`）**完全
未发码**。x0 中按源类型已扩展，窄化到更小宽度或改变符号性时必须重新
扩展，否则比较/运算会读到高位的残留值：`0x3ff0000000000000.to_type(int)`
被当成 64 位整体与 0 比较，恒为真。修复：按目标宽度与符号性补
`sxtw/sxth/sxtb`（有符号）与写 w0/`uxth`/`uxtb`（无符号）。

两处缺陷都由同一现象牵出：修复 1 后浮点常量恢复正确，才暴露出修复 2。

**本机自举差分探针（新增，容器不可用/快速定位时用）**

正式自举门需 aarch64 Linux 容器（docker + tmp/sysroot）。本轮新增
`tests/selfhost/native-selfhost.py` 与 `make selfhost-native`：用同一套
`compiler/` 源码在本机（Darwin/arm64）跑等价三代闭环——stage0 → stage1 →
stage2 → stage3，发射的 GNU/Linux AArch64 汇编经 macho.py 改写为
Mach-O 可汇编形态（`@PAGE/@PAGEOFF` + 符号 `_` 前缀）后本机链接。
校验：三 stage 自解析、三 stage 全量语法语料、stage2 运行不含 printf 的
语义用例（macOS 变参 ABI 与 Linux 不同，含 printf 的用例在本机不可判，
脚本如实跳过）、**stage2.s 与 stage3.s 逐字节一致**。

**验证**：
- `make selfhost-native` 全绿：三 stage 自解析；三 stage 语法 66/66 + 29/29；
  stage2 运行 run/13、16、31、32、33、34 全部符合期望；**汇编固定点一致**。
- `make test`：stage0 零回归 **49/49**（run 34 + fail 12 + pass 3），
  语法 66/66 + 29/29 两遍。
- `make bootstrap` 门已恢复：G2 运行语料改为 **run/ 全量**（不再排除 28），
  G2+ 固定点比较改为**直接 `cmp stage2.s stage3.s`**（stage2/stage3 对
  自身拼接源码的完整发射逐字节一致）。

**新增回归用例**（均带 `// exit:` 断言，可在任意平台运行）：
- `run/31-float-bits.yh`：浮点字面量位型（1.0/2.5/0.0）与浮点实参/返回；
- `run/32-int-narrow.yh`：整数窄化（i64→int、负值截断、u32/i8/u8 往返）；
- `run/33-u32-zeroext.yh`：无符号窄化零扩展（u32/u16/u8）；
- `run/34-cast-matrix.yh`：i8/u8/i32/u32/i64 全组合的转换矩阵与算术参与；
- `run/30-float-arg.yh`：浮点实参 + 浮点返回 + 混用实参（依赖 printf）。

两处修复的**回归证据**：把修复临时回退后重建 yh stage，`run/31` 与
`run/32` 在 stage 上分别以退出码 1 失败（stage0 因实现不同仍通过），
恢复修复后全部 42 通过。

## 2026-09-28 自举 B7：全语言语义落地，stage1 覆盖完整语料（44/44）

**实现**（compiler/ 12 文件，7657 行 yh；在 B5/B6 基础上补齐）：

- **聚合按值 ABI**（机制 b：调用点拷贝 + 指针传递，满足 ADR-0001 全部
  可观察行为）：聚合实参在调用点拷贝副本、传指针，被调用方入口再拷进
  本帧独立槽（`F_AGGPARAM`）；聚合返回经 x8 隐藏缓冲（调用方分配，x0
  返回缓冲地址）。嵌套结构体字面量经 `c_lit_depth` 状态栈递归构造。
- **切片** `[]T`：规范化视图 `{u64 长度, T* 数据}`；`len`（数组编译期、
  切片读偏移 0）、下标（读偏移 8 的数据指针）、`[N]T.to_type([]T)` 构造
  `{N, &arr[0]}`。
- **for-in**：数组 / 切片 / 区间 `a..b`（左闭右开）统一为「长度 + 取第 i
  项」；区间长度 `max(0, 终点-起点)`，元素/下标绑定为每轮值拷贝。
- **类型化变参** `name ... T`：登记为切片参数（签名 `vararg=2`），调用点
  把尾部实参逆序弹栈写入临时数组再打包 `{count, data}`。
- **浮点** f32/f64：d0-d7 传参与返回、`fadd/fsub/fmul/fdiv`、`fcmp`+`cset`
  比较、`scvtf/ucvtf/fcvtzs/fcvtzu` 转换、`fmov` 常量装载、浮点局部与
  复合赋值；GNU as 助记符不带 `.d/.s` 后缀（靠寄存器名区分）。
- **structInit 作值**：结构体字面量可用于初始化、实参、返回与嵌套字段。

**验证**：
- `make bootstrap` 全绿：G1（自解析 + 66/66 + 29/29）、G2（stage1 编译自身
  得 stage2；stage2 自解析、语法 66/66 + 29/29、运行语料 28/28）、
  G2+（stage2 编译自身得 stage3，stage3 自解析；stage2/stage3 对聚合
  用例的汇编逐字节一致）。
- stage1 全量运行语料 **44/44**（含 run/25 结构体 ABI、27 数组按值+切片+
  for-in、28 类型化变参+浮点、29 容量压力）。
- `make test`：stage0 零回归（44/44）。

**B7 自举差分暴露并修复的缺陷**：
- 结构体字面量字段地址算成 `fp-(off+foff)`（应为 `fp-(off-foff)`）；
- 聚合参数/返回的 x8 准备覆盖了已入参寄存器（改经 x10 中转）；
- 聚合返回写入缓冲前未保存 x8（入口漏发 `em_save_hidden_ret`）；
- 嵌套字面量恢复外层状态时 `save` 索引错（读 `save[depth]` 而非
  `save[depth-1]`）；
- 任意元素大小下标缺缩放（补 `mul`）；聚合元素在 value 模式被提前 load；
- 浮点元素在 `sem_index` 用整数加载（补 `ldr d0/s0`）；
- 区间长度用 `b.gt` + 误重置 x10 导致恒为 0；
- 浮点复合赋值的右值经 x0 压栈丢失（改用专用浮点临时槽）；
- `ucvtfd`/`fcvtzsd`/`fmul.d` 等错误助记符（GNU as 无后缀）；
- for-in 绑定槽误用 `sem_declare_local` 的**符号下标**当偏移（改取
  `c_syms[sym].offset`）。

**已知缺陷（stage2 自举层面，如实记录）**：stage2 编译**浮点字面量**时，
常量位型被编码为其 `fp64_bits` 函数地址（`0x4160676`）而非 IEEE754 值。
影响仅限 stage2 + 浮点字面量（run/28 与 compiler.yh 内 `10.0`/`1.0`）；
stage1 层面浮点完整正确。处置：`make bootstrap` 的运行子集排除 run/28，
汇编固定点比较改在聚合用例上做。定位与后续见
[自举后端架构](03-design/yh-自举后端架构.md) §6。

> **已于下一轮修复**：根因是 `sem_push_arg` 对浮点实参压栈走 x0 通路
> （见本文档「B7 收尾」一节）。修复后 stage2 浮点常量正确、汇编达到
> 全量固定点，`make bootstrap` 已恢复全量运行语料与全量固定点比较。

## 2026-09-28 自举 B5+B6：AArch64 后端与三代闭环，G2 达成

**实现**（按 [自举实施方案 v2](02-plan/yh-自举实施方案-v2.md)，源码在
`compiler/`，12 个文件共 6542 行 yh）：

三层后端架构（多平台接入缝，详见
[自举后端架构](03-design/yh-自举后端架构.md)）：
- **前端语义**（平台无关）：`symbols.yh` 名字池/类型表/符号作用域/
  类型兼容/常量折叠/prelude 登记；`sem.yh` 表达式·语句·声明语义钩子、
  两遍编译驱动、fn 与结构体布局、调用约定检查；`parse_type/expr/stmt/
  decl.yh` 边解析边调钩子（无 AST）。只引用 `target.yh` 数据模型与
  `em_*` 抽象机原语，不含 ISA 细节。
- **目标数据模型** `target.yh`：字长、对齐、参数寄存器数、结构体布局。
- **指令发射** `emit_arm64.yh`：值栈、访存、控制流、调用约定（前 8 参
  进 x0..x7，其余经调用点栈区）、`.data`/`.bss` 段与符号发射。

关键机制：静态帧（体先进缓冲，帧大小定后一次 `sub sp`，循环体内局部
不再压栈）；`mov sp, x29` 置于 epilogue 标签之后（显式 return 与落底
路径汇聚点）；代码标签 `.L<n>` 与数据标签 `.LD<n>` 分离（0 为 NULL
哨兵）；嵌套调用用实参基线栈 `c_call_base` 与直接调用标志栈
`c_call_direct` 隔离内层；短路标签用嵌套栈 `sc_sc_false_stk` 保存外层。

新增 `compiler/` 之外：`tests/yh/container-yh-cc.sh`（把 `--emit-asm` +
gcc 包装成 stage0 的 `<file> -o <out>` 接口）、`check.py --filter`、
Makefile 的 `SELFHOST_SOURCES` 与 `bootstrap` 目标。

**验证（`make bootstrap` 逐门，全部通过）**：
1. 拼接确定性：两次拼接逐字节一致，SHA-256 `90303ead…8d44b7`；
2. **G1**：stage1 自解析自身拼接源码到 EOF；语法语料 66/66 + 29/29；
3. **G2**：stage1 编译自身得 stage2（AArch64 Linux ELF）；stage2 自解析、
   语法差分 66/66 + 29/29、运行语义子集 **25/25**；
4. **G2+ 固定点**：stage2 编译自身得 stage3，`stage2.s` 与 `stage3.s`
   **逐字节相同**，stage3 自解析通过。

`make test`：stage0 零回归（ANTLR 66/66+29/29、编译器模式 66/66+29/29、
运行层 44/44）。B5 运行语料 **40/44**，余 4 项（`run/25` 结构体按值、
`27` 数组按值、`28` 浮点变参、`29` 包装类型）为方案规定的 B7 边界，
均显式拒绝且由用例钉住。

**自举差分暴露并修复的缺陷**（均由 stage2 运行复现，逐个修在编译器侧）：
- 全局指针 `NULL` 初始化与字符串数据标签 `0` 冲突 → 数据标签从 1 起；
- `t_sig_add` 四个签名数组共用容量变量 → 拆为独立容量；
- 取模 `sdiv` 用 x10（与复合赋值持有的目标地址冲突）→ 改用 x11；
- 普通赋值与复合赋值未取回暂存的目标地址（写进临时槽）→ 修正取改存；
- `em_epilogue` 的 `mov sp, x29` 在返回标签之前 → 移到标签之后；
- 任意元素大小（如 20 字节 Tok）的下标缺缩放 → 补 `mul`；
- 聚合元素（结构体/数组）在 value 模式下被提前 load → 保留地址语义；
- `let` 初始化大于 255 偏移时地址计算覆盖待存值 → 改用写 x10 的路径；
- `&&`/`||` 嵌套时短路标签被内层覆盖 → 加嵌套栈；
- 调用实参类型记录被内层调用覆盖 → 加实参基线栈；
- 嵌套调用中 `c_call_direct` 被内层稀疏调用污染 → 加直接调用标志栈；
- `main` 未输出 `.globl`（crt1 引用）→ 强制 GLOBAL。

**发现但未修的 stage0 缺陷（已绕开并记录）**：`continue` 在无条件
`for { }` 内报「不在循环内」（自编源码统一用 `for 1 { }`）；
stage0 每个编译单元只允许一个全局数组（编译器全局表改堆分配）；
`ty_sig_cap` 类共享容量问题在 stage0 的 `.yh` 语义层无直接对应，仅
影响本编译器。

## 2026-09-28 自举 B3+B4：compiler/ 下 yh 新编译器词法+语法落地，G1 语法自举达成

**实现**（按 [自举实施方案 v2](02-plan/yh-自举实施方案-v2.md)，源码目录按指示用
`compiler/` 替代方案的 `src/yh/`，共 2041 行 yh）：
- `compiler/model.yh`：token 种类常量（编号分组供范围判断）、Tok 结构体、
  全部全局状态集中声明（规避 stage0 全局名先声明后使用的问题）；
- `compiler/buffer.yh`：open/read/close 整读源文件（倍增缓冲、短读/EOF/负值
  处理）、write_all 短写循环、`file:line:col: 错误:` 诊断（fd 2）、推测解析
  静默开关（c_spec）；
- `compiler/lexer.yh`：完整词法器——保留字首字符分桶查表（语言关键字/
  已移除关键字/内建类型三组）、进制数字与下划线规则（前缀后无数字回退为
  十进制 `0`，与 ANTLR 一致）、字符串/字符转义集合与 `\xNN`、运算符最长
  匹配、注释与 \f\v\r 空白；token 引用原缓冲不复制；
- `compiler/parse_type.yh`：typeRef/fnType（返回类型省略靠 is_type_start
  判定）+ 解析器共用游标工具；
- `compiler/parse_expr.yh`：完整优先级链、后缀链（调用/下标/.to_type/成员，
  成员位置放开保留字）、structInit 命名/位置式与「字面量 vs 块」花括号
  消解（试探 + 配对 `}` 后必须紧跟 `{`，失败回退）；
- `compiler/parse_stmt.yh`：块/let/const/if（强制括号）/for 三形态/switch/
  return/branch/goto/标签/表达式语句；
- `compiler/parse_decl.yh`：七类顶层声明、参数（类型化/裸变参）、struct/
  union 字段、enum 成员；
- `compiler/driver.yh`：`--syntax-check`（B4 范围）与 `--emit-asm`
  （明确报后端未实现，B5 提供）。

**构建与验证**：
- `make`：stage0 零警告；`make bootstrap`（新增）：①拼接确定性（两次拼接
  cmp 逐字节一致 + SHA-256 `eb8f5879…a5caecb`）；②stage0 交叉编译
  `tmp/bootstrap/compiler.yh` 得 stage1（AArch64 Linux ELF）；③容器内
  stage1 自解析自身拼接源码到 EOF；④`tests/yh/check.py --compiler
  --compiler-path tests/yh/container-yh.sh`（YH_STAGE 指向容器内 stage1）
  正例 **66/66**、反例 **29/29** → **G1 达成**；
- `make test`：ANTLR 66/66+29/29、stage0 编译器模式 66/66+29/29、
  yh-run 44/44 全绿（stage0 无回归）；
- 词法边界探针（stage1 容器内执行）：1 MiB 语料（14000 声明 + 长标识符
  + 注释混排）解析通过；NUL 字节串内合法/串外拒绝（`1:15: 非法字符`）；
  未终结串拒绝（`1:36`）；跨行块注释后错误定位精确（`6:17`）；
  非法输入一律非零退出且带位置，无崩溃；
- 干净重建：`make clean && make && make bootstrap` 通过。

**测试入口约定**：本轮新增 .yh 代码（compiler/ 8 个源文件）的测试即
`make bootstrap` 的自解析 + 95 例语料差分；语法语料数量保持 66/29 不变
（语料针对语言而非编译器实现，不因实现新增重复用例）。

**发现的 stage0 缺陷（未修，已绕开）**：`continue` 在无条件 `for { }` 内
报「continue 不在循环内」（含嵌在 if 中的情形）；`for 1 { }` 与
`for cond { }` 路径正常。自编源码统一用 `for 1 { }`，探针
`tmp/probe-continue.yh`。后续修 stage0 时可直接复用该探针复验。

## 2026-09-28 tests 目录清理：删除 TCC 上游 C 测试套件（237 个文件）

**判定依据（引用关系全查证）**：
- Makefile 的 `test` 目标只跑 `tests/yh/check.py`（ANTLR + --compiler 两模式）
  与 `tests/yh-run/check.py`，且 `tests.%: ;` 规则已切断上游 tests/Makefile
  体系；
- 两个 check.py 只引用根目录 `yh.g4`/`yh` 二进制与 `tmp/sysroot`，不依赖
  tests 下其他文件；
- `rg` 全查 Makefile/src/config.h/lib/：对 tests2、pp、tcctest、abitest、
  boundtest、libtcc_test、asmtest、vla_test、testfp、42test.h、
  asm-c-connect、gcctestsuite.sh 零引用。

**删除**：tests/ 下除 `yh/`、`yh-run/` 外全部内容——`Makefile`、`pp/`、
`tests2/`、`tcctest.c/.h`、`abitest.c`、`boundtest.c`、`libtcc_test.c`、
`asmtest.S`、`asm-c-connect-1/2.c`、`vla_test.c`、`testfp.c`、`42test.h`、
`gcctestsuite.sh`，共 237 个文件。这些是 TCC 上游 C 测试套件，yh 编译器只
接受 .yh 输入，永远不会被执行。

**验证**：make 构建正常；make test 三层全绿（ANTLR 66/66+29/29、编译器
66/66+29/29、yh-run 24/24）。tests/ 保留 1.4M（yh 416K + yh-run 1.0M）。

## 2026-09-28 ponytail-review 死代码清理：净删 134 行 + 4 个垃圾文件

**审查方法**：按 ponytail-review（仅猎杀复杂度，正确性/性能另审）对当前
全部改动做逐文件审查，用 rg 验证「只写不读」后再删。

**清理动作（均有读写计数证据）**：
- yh_decl.c：删除只写不读的死变量 `yh_saw_param` / `yh_cur_fn`（含无意义的
  保存/恢复）/ `yh_has_const_init` / `func_sym`（恒 NULL）；删除投机机制
  yh_consts 常量侧表整套（`yh_register_const` 只写、`yh_lookup_const` 挂
  `__attribute__((unused))` 自证无人调用，注释自称"保留用于 M4"——M4 需要
  时再加）；删除 `yh_parse_const_decl` 的死参数 `local` 及两处实参；删除
  `yh_gen_function` 中恒真的 `!yh_syntax_only()`（唯一调用点已排除语法模式）
  与 YH_DEBUG 注册调试输出；`(void)s;` 改为不接收 sym_push 返回值。
- yh_stmt.c：删除注释自证"不可达"的 if 块（for-in RANGE 窥探）、range 分支
  死赋值 `b1_off = h_cur - 8`（下一行立即覆盖）与 `et = int_t`、压警告的
  `(void)h_idx...` 行、return 后恒真条件 `if (tok != '}' || 1)`、YH_DEBUG
  switch 调试输出、与 yh.h 重复的 3 个 extern 声明。
- **switch case 解析统一**：删除 `yh_parse_switch_case`（只被语法模式调用，
  编译路径 L533-587 手写了同样的 case/default 解析）；语法模式改走同一条
  内联循环（生成部分本就有 `!yh_syntax_only()` 保护），判别值求值/槽分配块
  包进 `if (!yh_syntax_only())`。两种模式一条路径，-43 行。
- yh_expr.c：删除三元表达式尾部空语句块；删除与 `yh_parse_expr` 逐字相同的
  `yh_parse_expr_pub`（3 个调用点改用 `yh_parse_expr`）；structInit 三段
  重复注释合并为一段。
- macho-out.c：删除空块 `{ unsigned k; (void)k; }`；`macho_write` 定义前移
  替代前向声明。
- tccpp.c：删除多余的 `parse_number` 前向声明（定义在同文件更早位置）。
- arm64-gen.c：删除 gfunc_call 热路径上的 YH_DEBUG 参数类型打印（每次调用
  getenv）。
- yh.h：删除不存在的 yh_slice.c 漂移注释行；yh_builtin.c：修正 params 注释
  （`-2 表示裸 ...` 的编码不存在，实际用 variadic 字段）。
- 仓库垃圾：删除根目录 `hello`、`yh`（Mach-O 构建产物）与 `not`、`tty`
  （空文件）；.gitignore 增加 `/yh`、`/hello`。

**保留项（有行为，非死代码）**：yh_decl.c binding 处 6 个保留字的定向报错
（产出不同错误信息，是功能不是死代码）；arm64-gen.c store()/type_size()
assert(0) 前的 fprintf（错误路径诊断，随 assert 存活）。

**验证**：make 干净构建零警告；make test 三层全绿——ANTLR 语料 66/66+
29/29、编译器模式 66/66+29/29、yh-run 24/24，与清理前完全一致。

**行数**：yh 解析器七文件 3688 → 3554 行（净 -134），另有 4 个垃圾文件出库。

## 2026-09-27 M6 完成：有证据地清理 + 清理后回归对比

**清理动作（均有调用关系证据）**：
- libtcc.c：移除 tccasm.c 的 ONE_SOURCE 条件包含（CONFIG_TCC_ASM 从未定义，
  tccasm.c 1183 行从未编译进产物）；C 源路径改为显式报错「yh 编译器不支持
  C 源文件（.yh 是唯一输入）」（驱动层 M1-01 已拒绝 .c，libtcc API 层同步
  收口）；删除 free_inline_functions 调用。
- tccgen.c：删除 tccgen_compile（C 路径入口，yh 不再引用）、
  free_inline_functions、gen_inline_functions（static inline 机制整体，
  其唯一调用链 tccgen_compile→gen_inline_functions→gen_function 已断）及
  tcc.h 对应声明——干净构建零警告。tccgen.c 7122 → 7034 行。
- 清理过程事故记录：一次自动删除脚本误删 tccgen.c 主体（write 收到 list
  抛 TypeError 时文件已截断），从 git HEAD 完整恢复；随后重做的手工删除
  （decl0/decl/block/gen_function 尝试）因连锁依赖（expr_eq/unary 链被
  decl_initializer 复用）引发链接错误，全部回退。

**M6 结论（依方案 §6.8「不因删行目标强行移除」）**：
- 已删：tccgen_compile、free_inline_functions、gen_inline_functions、
  tccasm 包含、C 源路径入口（tccgen.c 净减 88 行 + tccasm.c 1183 行从未
  编译进产物）。
- 保留（有活引用）：decl0/decl/block/expr_eq/unary 链——yh 的
  decl_initializer_alloc（字符串字面量、structInit）、expr_const1（数组
  长度/枚举/const）、find_field/struct_layout、值栈与 gen_* 机制全部
  复用自 tccgen.c，与其声明 parser 同文件交织，无法在不拆分文件的前提下
  单独移除。「C parser 拆除（净减 2.5k~3k 行）」列为 0.0.2 任务，先做
  tccgen.c 按职责拆分（方案 §2.2 既定顺序）。
- 清理前后回归对比：make test 三层全绿（ANTLR 66+29、编译器 66+29、
  yh-run 24/24）完全一致；构建零警告。

## 2026-09-27 M5 完成：三层测试集成、干净构建、README 重写

## 2026-09-27 M4-02/M4-03 完成：切片、for-in、structInit、类型化变参

## 2026-09-27 M3-02 + M4-01 完成：类型检查/复合赋值/数组按值 + 语义测试框架 24/24

## 2026-09-27 本地系统支持：Darwin 原生 Mach-O 输出 + 系统链接

## 2026-09-27 多平台架构整理与优化方案（文档，无代码改动）

- 新建 [docs/02-plan/yh-多平台架构整理与优化方案.md](02-plan/yh-多平台架构整理与优化方案.md)：
  面向 linux/darwin/windows × arm64/x64 共 6 目标。梳理现状分层与 10 个耦合点
  （架构硬编码 tcc.h:138、宿主宏决定输出格式 libtcc.c:805、macho-out.c 仅
  ARM64 重定位、libtcc1 固定 aarch64-linux-gnu、-run 仅 aarch64 宿主等），
  给出差距矩阵、5 阶段方案（抽象统一→x86_64 恢复→Mach-O x64→Windows PE→
  windows/arm64）与逐阶段验证门。
- 关键事实核对：x86_64 后端可自 `git show 0db9fca^:x86_64-gen.c` 恢复；
  tccpe.c/win32 头与导入库可自 `git show ef8db88^:src/formats/tccpe.c`、
  `ef8db88^ win32/` 恢复；`lib/libtcc1.c`、`alloca86_64.S` 仍在 lib/ 中。
- `docs/todo.md` 0.0.2+ 节加入指向该方案的条目。未修改编译器代码，无需构建验证。

## 2026-09-27 修复 -o 链接路径段错误 + sysroot 链接闭环

## 2026-09-27 M3 语义编译器接通：名称/调用/语句代码生成 + 全量语料验收

## 2026-09-27 M2 完整语法 parser 与双模式回归（M2-01～M2-04）

## 2026-09-27 M1-02 yh 词法改造 + M1-03 纯语法入口骨架

**M1-02（tcctok.h / tcc.h / tccpp.c）**：
- tcctok.h：新增 yh 关键字 let/fn/in/pub/true/false/len/to_type/type/as 与
  i8~u64/f32/f64/bool；全部保留字（含复用的 if/for/struct/… 与已移除的
  while/do/unsigned/…/restrict 及 gcc 变体）位于 TOK_UIDENT 边界之前，
  yh 中不可作普通标识符；边界后的 define/include 等 token 值仍可作标识符。
- tcc.h：新增 `TOK_RANGE 0xd0`（`..`）与 `TCCState.yh_mode` 标志。
- tccpp.c（全部按 yh_mode 分支，C 预处理路径保持原样）：
  - `#`/`##` 在 yh 模式直接报错「yh 无预处理」；
  - `case '.'`：yh 下 `..`→TOK_RANGE、`...`→TOK_DOTS、其余为成员点；
    `.5` 不再进入数字扫描（留给 parser 按语法拒绝，与语料注释一致）；
  - 数字扫描重写（yh_num_char）：0x/0b/0o 前缀定进制、下划线必须夹在本
    进制两数字之间、`.` 只在后跟数字时吞入、e/E 只在合法指数起点吞入、
    无任何整型/浮点后缀；`0b12` 切成 `0b1`+`2` 两个 token；
  - parse_number 增加 yh 分支：剔除下划线后按进制转换，无旧式八进制
    （`017`=17），整数按数量级映射 CINT/CUINT/CLLONG/CULLONG，
    浮点一律 TOK_CDOUBLE；修复 `isnum()` 短路导致的 `0b12` 整吞 bug；
  - 转义收敛：\n \r \t \0 \a \b \f \v \' \" \\ + \xNN（恰两位），
    未知转义报错；多字符字符字面量报错；`L` 前缀不再构成宽字符串。
- 验证：65 个正例语料全部通过词法骨架；rejected 中 18/23/26 在词法层被
  定向拒绝，其余反例留给 M2 parser；ANTLR 回归 65/65、29/29 不变。

**M1-03（yh_decl.c）**：`yh_compile()` 接通 `--syntax-check` 骨架：置
yh_mode、不开 PARSE_FLAG_PREPROCESS、以 TOK_NUM|TOK_STR 消费到 EOF，
setjmp 错误恢复与 tcc_compile 同构；不解析符号、不调用 gen_*、不要求 main。
最小正例与词法错误反例红绿验证通过；完整语法解析在 M2 按 g4 逐层替换。

## 2026-09-27 M1-01 构建与 .yh 输入分派

- `make` 改为产出 `yh`、`libtcc.a`、`libtcc1.a`；新增 VERSION 文件（0.0.1，
  修复此前 `-DTCC_VERSION=""` 的问题）。
- `libtcc1.a` 改由独立目标 C 工具链构建（不再用 yh 自举）：自动探测
  aarch64-linux-gnu-gcc → Linux/aarch64 本机 cc → clang（非 Linux 宿主自动加
  `-target aarch64-linux-gnu`）；macOS BSD ar 拒绝 ELF 成员，归档器自动选用
  clang 同目录的 `llvm-ar`。工具链全缺失时给出明确 $(error) 诊断。
- `lib/lib-arm64.c` 改为 freestanding（自带 typedef 与 memcpy 声明，不再包含
  目标 libc 头文件）；`__clear_cache` 在非 tcc 工具链下改用
  `__builtin___clear_cache`，消除 M0-02 发现的未定义符号。宿主 clang 交叉与
  容器 gcc 双路径均零警告，产物为 AArch64 Linux ELF 归档成员。
- 驱动：`.yh` 后缀进入 `yh_compile()`（AFF_TYPE_YH 分派，yh_decl.c 新建）；
  非 .yh 用户源文件（如 .c）被驱动明确拒绝（exit 1）；`--syntax-check` 选项
  注册（TCC_OUTPUT_SYNTAX 输出类型），yh 解析器本体留给 M1-03/M2。
- yh 骨架：`src/core/yh.h`（共享声明）与 `yh_decl.c`（入口）。
- 驱动行为验证：`.yh` 进入 yh 路径、`.c` 被拒、`yh -v` 报 0.0.1；`make test`
  运行 ANTLR 语料回归（65/65、29/29）。

## 2026-09-27 M0 前置验证完成

- **M0-01**：基线记录于 `tmp/m0/`（make / make test / check.py --coverage 输出与
  调用关系 `tmp/m0/call-graph.md`）。65 正例 / 29 反例 / 68 规则覆盖全过；
  Darwin `make test` 只跑 pp 套件（tests2 需 Linux，符合预期）。
- **M0-02**：Docker 容器（ubuntu:24.04，aarch64 原生）验证 AArch64 Linux
  工具链、crt、动态加载器；`lib/lib-arm64.c` 可由容器 gcc 产出 AArch64 Linux
  ELF 归档（发现 `__arm64_clear_cache` 在 gcc 下是未定义符号，tcc 内建，
  M1 需替换 `__builtin___clear_cache`）。带 `-DCONFIG_SYSROOT/-DCONFIG_TRIPLET`
  的 tcc 在 Darwin 直接产出可运行 Linux ELF；容器内 gcc 构建的原生 tcc
  `-run` 全链路通过。记录 `tmp/m0/m0-02.md`；最小 sysroot 在 `tmp/sysroot/`。
- **M0-03**：`tmp/abi/` 探针实测（tcc/gcc 双编译、输出一致）：机制 a
  （包装结构体）完整覆盖 ADR-0001 矩阵；切片 16B 结构体参数/返回正确；
  实测 `gfunc_call` 断言边界（对齐后 ≥4096B 触发，4080B 通过）。决定采用
  机制 a，4KB 断言在 M4-01 修后端（不设语言上限），见新
  [ADR-0002](adr/0002-yh数组与切片内部ABI机制.md)。
- **M0-04**：语义边界定案写入
  [docs/03-design/00-语义边界-0.0.1.md](03-design/00-语义边界-0.0.1.md)：
  先扫描顶层函数签名、`fn main() int` 无参、pub 的 ELF 绑定语义、字符串
  字面量可写（.data）、零长度数组拒绝、数组同型赋值=值复制、切片不做边界
  检查、裸变参提升规则与 prelude 八函数签名。同步修正 `docs/yh.g4` prelude
  注释（8 函数 + 直接登记 extern Sym）；`check.py --coverage` 复跑全过。

## 2026-09-27 yh 0.0.1 三份文档执行计划整理

- 将 `docs/02-plan/yh-0.0.1-改造方案.md` 展开为 M0～M6、逐任务编号、依赖顺序、验证门和动态语料验收口径；当前 94 个语料只作为基线。
- 将 `docs/todo.md` 收敛为同编号的任务清单，移除重复的早期探索排期；保留 0.0.2+ 待设计事项。
- 将 `docs/adr/0001-yh数组按值调用边界.md` 明确为已接受的语言/互操作边界；M0 用 C 代理探针选择内部机制，M4 用真实 `.yh` 用例验证，不混淆两类证据。
- 本次是文档整理，没有修改编译器代码；构建和运行验收仍属于后续 M0～M6 任务。

## 2026-09-27 类型转换语法改为 `to_type`

- 将 `x as T` 改为后缀语法 `x.to_type(T)`；目标参数仍按 typeRef 解析，允许链式转换及转换后直接取下标/成员。
- `to_type` 是专用后缀关键字，旧 `as` 转换写法报语法错误；同步改造方案、待办和 `.yh` 语法语料。旧版修订记录中的 `as` 示例保留为历史记录。
- `tests/yh` 正例 65/65、反例 29/29，68/68 条规则标注覆盖；69 个歧义探针零真歧义、零预期外结果。`make` 与 `make test` 通过；Darwin 上 `make test` 按现有规则只运行 pp 套件。
- 当前编译器 `src/` 仍未实现 `.yh` 解析；本次验证对象是参考语法和语料，编译模式的 `to_type` 语义检查仍在待办中。

## 2026-09-27 类型转换方案补全

- 在 `docs/02-plan/yh-0.0.1-改造方案.md` 增加转换矩阵：字面量与无损提升、显式数值和指针转换、数组/切片视图、拒绝无长度指针转切片。
- 明确 `as` 先做 yh 语义检查且结果为右值；TCC 的警告和 `gen_cast` 不能代替准入检查。同步 M3/M4 验证门与 `docs/todo.md`。
- 本次只修订计划文档，没有实现编译器转换检查；现有 `tests/yh/08-expr/06_cast.yh` 仍是纯语法用例。

## 2026-09-27 yh 0.0.1 改造方案评审修订

- 核对构建、驱动、语法语料和 AArch64 参数分类；修订 `docs/02-plan/yh-0.0.1-改造方案.md` 的架构假设、降糖、阶段顺序与验证门。
- 将 `.yh` 文件识别、C 运行时构建、数组/切片 ABI、纯语法检查、prelude 符号登记列为实现前置事项，并同步 `docs/todo.md`。
- 本次仅修改文档；编译器实现和运行测试仍列为后续任务。
- 将迁移遗留的测试后缀要求统一为 `.yh`，与唯一用户源文件后缀一致。

## 2026-09-27 语法参考（docs/yh.g4）歧义分析与无歧义修订

### 背景

对 docs/yh.g4 做歧义分析：用本地 ANTLR 4.13.2（`~/.m2/repository/org/antlr/antlr4/4.13.2/antlr4-4.13.2-complete.jar`）生成 parser，31 个探针用例实测。结论：原语法**无真歧义**（同一 token 序列两棵合法语法树的情况不存在），但发现 1 个实锤缺陷、多处注释与语法不符、若干 spec 缺口。分析过程与全部探针保留在 `tmp/antlr-check/`。

### 已落地的修订（全部经 ANTLR 实测验证）

1. **memberName：成员位置放开保留字**（实锤缺陷修复）
   - 原 grammar 中 `in`/`as`/`len`/`sizeof`/`type` 等被隐式关键字化且优先于 IDENT，导致 `p.len` / `p.type` / 字段名 `type` 全部语法错误。
   - 新增 `memberName` 规则，用于 fieldDecl / structInitField / postfixPart 三处；局部/全局标识符位置仍严格。
2. **exprStmt 收紧为单目标赋值**：`expr (assignOp expr)? ';'`，`a, b = 1, 2;` 不再合法（v0.1 无元组赋值）。
3. **labelStmt 必须后随语句**：`IDENT ':' stmt`，悬空标签 `L: }` 报错（同 C）。
4. **转义收敛**：STRING/CHAR 统一转义集合 `\n \r \t \0 \a \b \f \v \' \" \\` + `\xNN`；未知转义（`\q`）词法报错，不再静默吞掉。
5. **NUMBER 下划线规则**：必须夹在数字之间；`1_` / `1__0` / `0b_1` 报语法错误。
6. **显式词法规则 RANGE `..` / ELLIPSIS `...`**：手写 lexer 有明确对照。
7. **WS 扩充** `[ \t\r\f\u000B]+`：CR-only / 表单符文件不再词法报错；CRLF 仍按 NL 整体成词。

### 注释修正（语法行为不变）

- structInit 注释重写：删除失效的 `if flag {}` 例子（if 强制括号，本就非法）；分离「命名式 vs 位置式」与「字面量 vs 块」两个消歧问题；给手写 parser 定下头部边界算法（花括号配对 + 窥探下一个 `{`，贪心取字面量，与 ANTLR ALL(*) 判定一致）。
- castExpr 处新增结合性备忘：`a as b * c` = `(a as b) * c`、`a as *b` 为指针、`(x as T)[i]` 须加括号、`-x as int` = `(-x) as int`、`**` 非幂（`**p` 双重解引用合法，不可封禁）。
- returnStmt 注明会吞掉下一行开头的表达式（NL 隐藏通道，同 C）。
- switchCase 注明 default 位置无语义、至多一次靠语义检查。
- structInitBody 注明尾逗号策略：逐行列表允许、行内列表不允许。
- sizeofExpr 注明只收类型及理由。
- 文件头设计前提补充保留字策略（标识符位置严格 / 成员位置宽松）。

### 验证

- 修订稿生成 / 编译零警告；31 探针：21 个预期通过全过，10 个预期报错全部按设计响亮报错（`tmp/antlr-check/final/` 可复现）。
- 6 个 for/switch 头部边界用例（含 `switch Point{1,2} { case 1 {} }`、关键字字段名场景）`-diagnostics` 歧义检测 0 报告。
- 一次誊写回归（NUMBER 指数组 `?` 丢失导致 11 用例失败）已由探针矩阵当场捕获并修复——探针集同时充当回归测试。

### 后续

编译器实现（src/ 手写 lexer/parser）同步清单见 docs/todo.md。

# 2026-09-28 yh 语法与编译器自举方案（文档）

- 新增 `docs/03-design/yh-自举能力边界.md`：区分语法自举、编译器自举与工具链完全自给；规定最小输入接口、目标平台和三代验收。
- 新增 `docs/02-plan/yh-语法与编译器自举方案.md`：记录现状缺口、推荐路线、B0–B6 阶段和验证门；同步 `docs/todo.md`。本项仅编写方案，未修改编译器代码。

# 2026-09-28 yh 0.0.2 自举 B0–B2（种子冻结、输入接口、工作负载验证）

## B0 定位与修复测试基建

- **22/24 复盘定性**：07-goto-label「无法暂存目标文件」= 多进程并发
  共享产物目录时 `macho-out.c` 的 `rename` 竞态（4 个并发 check.py
  实例复现，20/24）；08-recursion 信号 9 未能复现（150 次编译+运行
  压力、3 次套件全绿），定性为环境性 kill。单进程与交叉路径均无缺陷。
- `macho-out.c` rename 失败信息补充 `strerror(errno)` 并提示并发触发
  场景；新增 `--workdir` 隔离后并发 4 实例全绿。
- `tests/yh-run/check.py` 新增 `--compiler`/`--workdir`（自举差分用），
  产物缺省迁移 `tmp/yh-run-work/`；新增 `stdin-hex:`/`argv:` 注入
  （交叉模式经 `docker exec -i`）。`tests/yh/check.py` 新增
  `--compiler-path`/`--workdir`。旧 `tests/yh-run/work/` 已删除。
- 缺口矩阵：`docs/02-plan/yh-运行覆盖缺口矩阵.md`（G01–G17，B2 后全部补齐）。

## B1 输入接口与语义修复

- prelude 登记 `read(fd int, buf *void, count u64) i64` 与
  `close(fd int) int`（共 10 个），同步 `docs/yh.g4` 与语义边界 §7。
- 放宽 `main` 为 `()` 或 `(argc int, argv **char)`；错误签名仍拒绝。
- 期间发现并修复 4 个语义缺陷（均有语料正例佐证但语法套件测不出）：
  ① `true/false` 推为 int → 改为 bool；② 整数字面量无法窄化
  （§4.1）→ 可表示字面量隐式允许 + 全局初始化范围检查（`let x u8 =
  300` 从静默截断改为报错）；③ 数组左值传 `*void` 不退化（坏指针/
  SIGBUS）→ 转换前左值退化；④ 裸变参小整数缺 C 默认提升
  （i8 打印 254）→ i8/i16/u8/u16/bool → int。
- 用例：run/16-18（read 分块/短读/NUL 计数/EOF/坏 fd/open-close）、
  run/19（bool+字面量窄化+提升）、run/20（字节缓冲：1 字节分配、
  扩容边界、NUL、1 MiB 逐字节一致、2^63 分配干净失败）、fail/07-08。

## B2 工作负载与容量验证

- 新增探针 run/22-29：函数指针（赋值/回调/返回选择）、u32/u64 位移与
  符号扩展、互递归、malloc 链表+全局指针写、struct 按值/大 struct、
  union/enum、数组按值/递归/切片视图/for-in、类型化变参/浮点、容量
  压力（1439 行，200 包装类型+129 case 值+约 200 字符标识符）。
- 期间发现并修复 5 个编译器缺陷：⑤ 函数名无法赋给 fn 类型 → 同签名
  fn 隐式转换（签名结构相等）；⑥ struct/数组按值返回调用缺隐藏返回
  指针（断言/段错误，**M4 数组返回从未真正运行过**）→ 调用方压 sret
  临时+结果取临时左值；⑦ 浮点返回误取 x0 → 取 v0（REG_FRET）；
  ⑧ 调用结果（包装 struct）赋回数组变量被拒/只拷 8 字节 → 包装→数组
  同型允许且 vstore 走块拷贝；⑨ switch 分支数组固定 128 超限静默截断
  → 扩 512+干净报错；包装类型上限 128 → 512（超限本就报错）。
- 用例：fail/10（数组长度不匹配）、fail/11（513 case 值干净报错）、
  fail/12（513 包装类型干净报错）。

## 验证

- `make` 零警告；`make test`：语法 66/66+29/29、运行 44/44
  （run 29/29、fail 12/12、pass 3/3）；`check.py --cross` 44/44。
- 下一步：B3（用 yh 写出能解析自身的前端）。

# 2026-09-28 自举实施方案 v2（文档）

- 按提交 `b5b57d9` 的代码基线重定 B3–B8：B3 词法器、B4 语法自举 G1、B5 子集后端、B6 自编闭环 G2、B7 全语言覆盖、B8 三代固定点 G3。
- 新方案见 `docs/02-plan/yh-自举实施方案-v2.md`；旧方案标记为历史，`docs/todo.md` 与自举能力边界同步更新。本次未修改编译器代码。
- 方案制定前基线验证：`make` 成功；`make test` 的语法正反例为 66/66、29/29，Darwin 运行层 44/44；`python3 tests/yh-run/check.py --cross --quiet` 在 AArch64 Linux ELF 容器运行层 44/44。

# 2026-09-28 自举方案归并（文档）

- 将自举定义、现有能力、输入输出契约、技术路线、B3–B8 任务及 G1–G3 验收矩阵统一到 `docs/02-plan/yh-自举实施方案-v2.md`。
- 原计划与能力边界文档改为简短入口，`docs/todo.md` 只链接统一方案；本次未修改编译器代码。

# 2026-10-03 yh-link 独立项目 TC1–TC3：ELF 对象出口贯通

- 按用户要求在仓库根 `link/` 独立立项（`project.toml`，`name = "yh_link"`），
  模块结构对应实施方案的 `compiler/obj|asm|link`。上一轮的 `asm/` 未改动。
- 交付 TC1（二进制模型/上下文）+ TC2（AArch64 整数子集编码）+ TC3（ELF64
  `ET_REL` 出口）：`yh_link asm -o out.o in.s` 可产出结构完整的可重定位对象。
- 关键修正：重定位类型号按 llvm-mc 实测纠正三处（`ADD_ABS_LO12_NC` 277、
  `CONDBR19` 280、`cbz/cbnz` 用 CONDBR19）；补 LDST8/16/32/64 lo12；
  `sp` 参与的 64 位加减改扩展寄存器形式（原先会编成 `sub xzr, xzr, x9`）；
  `adrp` 回填掩码保留 bit31；`uxtw x,w` 改 UBFM 规范编码；点号符号一律局部；
  代码节对齐填 NOP；`memcpy` 返回值误用导致 `.rela.<sec>` 节名退化。
- 验证：`cd link && ../yh run` 通过；`./.build/yh_link` 自检退出码 0
  （编码器 107 + 公共层 36 + 端到端 15）；`tests/check_corpus.py` 61 个语料
  汇编成功 44 个、与 llvm-mc **逐字节不一致 0**、跳过 17（10 个浮点 + 7 个 GOT）；
  `tests/check_obj.py` 44 个对象结构问题 0、非确定 0。
- 自检有变异测试证据：改回 `adrp` 掩码返 19，改回访存 lo12 的 addend 用法返 21。
- 未做：浮点标量编码、GOT 重定位（311/312）、静态链接（本机无 AArch64 ELF
  链接器）。已登记 `docs/todo.md`。

# 2026-10-03 yh-link 容器链接门与平台矩阵规划

- 加了容器链接门 `link/tests/elf_link_check.py`：宿主汇编，容器里用 GNU
  交叉 `ld` 链成静态可执行并真跑，判定是差分的（本工具对象与 llvm-mc 参照
  对象退出码与标准输出必须一致）。镜像 `link/tests/docker/Dockerfile`
  （binutils 双架构 + qemu-user-static），构建 `docker build -t yh-link-elf:latest`。
- **门抓出一个真 bug 并已修**：「目标符号已定义且同节」原本触发汇编期回填，
  但 `adrp`/`@PAGEOFF`/`.xword` 这几类值依赖节的最终地址——GNU `ld` 把
  `.text` 放在 0x400078 这类非 4KiB 对齐处时，汇编期算出的 `(S & 0xFFF)` 就是
  错的，语料里 3 个对象因此段错误或执行非法指令。旧门看不见是因为
  `check_corpus.py` 只比未定义符号的重定位，而局部回填的迷你链接器跟汇编器
  犯了同一个错，自洽通过。
- 修正为只有「局部符号 + 同节 + 分支」能在汇编期定；其余一律出重定位。
  随之删除 `fx_pg_hi21`/`fx_lo12`/`fx_lo12_ldst`/`fx_put64` 与 `ctx_get_sym`。
- 符号绑定改合 GNU as：无 `.globl` 的标签一律局部（原来非点号名字默认全局），
  引用时 `SYM_UNDEF` 占位、定义时定局部；判定看绑定不看节号。
- `check_corpus.py` 改为**重定位全量比对**，目标按（节名 + 符号值 + addend）
  归一化，迷你链接器改用 4KiB 对齐的合成节基址。
- 顺带修系统指令：`nop/brk/svc/hlt/dsb/dmb/isb` 原本用 `p_is_mn` 查已被
  消费的助记符而全部失败；屏障域会吃掉下一条语句；ISB 少 bit6。新增定向语料
  `tests/asm/06-sysops.s`。
- 验证：`./.build/yh_link` 退出 0；`check_enc.py` 107/107；`check_corpus.py`
  44/44 重定位全量一致；`check_obj.py` 44/44 结构+确定性干净；
  `elf_link_check.py` 44/44 行为与参照一致。
- 规划 Linux/macOS × arm64/x64 矩阵：见
  [平台与架构矩阵方案](02-plan/yh-link平台与架构矩阵方案.md)。
  关键结论：macOS/arm64 可增量做（出口增量，解析与编码全复用，验收用宿主
  Xcode 的 `ld64`）；**x64 必须先有编译器 x64 后端**（`compiler/backend/`
  目前只有 arm64），否则 x64 汇编器没有输入方，待确认。
- 环境事实：colima `docker build --platform linux/amd64` 会静默产出 arm64
  镜像；colima 不共享宿主 `/tmp`，容器产物放仓库内 `tmp/linkbox/`。

# 2026-10-03 yh-link 标量浮点与 GOT 重定位：语料全覆盖

- P1-2 GOT 重定位：`@GOTPAGE` → `R_AARCH64_LD64_GOTPAGE_LO21`(311)，
  `@GOTPAGEOFF` → `R_AARCH64_LD64_GOT_LO12_NC`(312)。这两类永远只出重定位，
  因为 GOT 项本身是链接器建的。LP64 下只有 64 位形态——llvm-mc 对更窄的 GOT
  访存直接拒绝，本工具同样报诊断而不是凑近似编码。
- P1-1 标量浮点：`fadd/fsub/fmul/fdiv`、`fcmp`、`fcvt`(s↔d)、`fcvtzs`、
  `scvtf`、`fmov`(通用→浮点)，加 `s`/`d` 寄存器解析。位布局全部由
  `llvm-mc --show-encoding` 固定一个寄存器只变一个的方式逐条反推，
  不凭记忆写手册位域：Rd 在 4:0、Rn 在 9:5、Rm 在 20:16。
- 浮点访存没另写一套编码：`ldr/str` 带 s/d 寄存器 = 同宽整数访存或上
  V 位（bit26），所以在 `p_mem_insn` 加一个 `vbit`、宽度由寄存器类别决定即可。
  这也说明浮点访存的重定位类型跟整数完全一样。
- 结果：`check_corpus.py` 61 个语料**全部汇编成功、逐字节比对 0 不一致、
  跳过数 10 → 0**。契约覆盖追上了编译器实际发射的 AArch64 汇编。
- 修掉容器门自身的缺陷：静态链接阶段两侧的标记写进了同一个变量，参照侧失败
  会被算成本工具失败。改成两级各自独立判定，「两边都失败」按差分语义跳过，
  只在两边结果不同时报错。
- `check_obj.py` 重定位白名单补 311/312。
- 编码器向量 107 → 129（含 22 条浮点）；新增定向语料 `tests/asm/07-got.s`、
  `tests/asm/08-float.s`；端到端自检加了 GOT 两条。
- 验证：`./.build/yh_link` 退出 0；`check_enc.py` 129/129；`check_corpus.py`
  61/61 不一致 0 跳过 0；定向语料 8/8；`check_obj.py` 61 对象结构 0 非确定 0；
  `elf_link_check.py` 行为一致 54、不一致 0、7 个两边同样链不上而跳过。
- 容器门剩余 7 个跳过：yh 运行时外部符号（`__Exit`/`_strtoul`/`_open`/
  `_close`/`_abs`）在 `tests/elf/yhr.s` 里没桩，补桩后可进入运行比对。
- 契约 §3 补标量浮点族与浮点访存规则、§6 补 311/312；
  `link/README.md` 同步范围、目录、测试表与已知边界。
- 记录见 [完成记录](01-finished/yh-link标量浮点与GOT重定位-2026-10-03.md)。

# 2026-10-04 yh-link Mach-O 出口与编译器汇编步替换

- `link/` 新增 Mach-O arm64 `MH_OBJECT` 写出器（`src/obj/50_macho.yh`、
  `src/obj/51_macho_emit.yh`），`yh_link asm -t darwin` 产出 clang 可替代的
  可重定位对象。节映射、重定位映射全部实测自 clang；**PAGEOFF12 的 length
  一律 2**（Mach-O 的 length 是立即数字段字节数，与访问宽度无关）。
- 补子集缺口 `ucvtf`（编译器浮点窄化用无符号版）：新增 `e_ucvtf`、5 条编码器
  向量、定向语料 `tests/asm/09-ucvtf.s`。
- `compiler/cmd/link_cache.yh` 的 `mb_asm_tool` 按 `YH_LINK` → `PATH` →
  编译器同目录的顺序找 `yh_link`，找到就用它做逐模块汇编，找不到回落
  `clang`/`gcc`；命令前缀进对象缓存键。
- 新增 `make yh-link`：用刚构建的 `$(YH)` 冷编 `link/` 并产出根目录
  `yh_link`（macOS 上 codesign）。`yh` 与 `yh_link` 同目录即自动生效。
- `tests/selfhost/link-cache.py` 改为与汇编器无关：wrapper 同时覆盖
  `gcc`/`clang`/`yh_link`，计数按 assemble/link 两类统计。
- 新增门 `tests/macho_corpus_check.py`（对 clang 语义差分）与
  `tests/macho_link_run.py`（链成可执行后比运行行为）。
- 修掉一个致命错误：**同节分支在 Mach-O 里不发重定位，但汇编期必须回填
  偏移**。原先照 ELF 规则留了重定位却没回填立即数，指令字节为 0，链出来
  直接跑飞（结构差分却全对）。判定改为按目标格式分派，与 `mo_reloc_kept`
  共用 `obj.mo_sym_in_sec`。
- 验证：自检退出 0；`check_enc.py` 134 条不一致 0；ELF `check_corpus.py`
  61/61 与 9/9 不一致 0 跳过 0；`macho_corpus_check.py` 70 个一致 69 跳过 1
  不一致 0；`macho_link_run.py ../tmp/inv` 61/61 一致；两代固定点（均用
  yh_link 汇编）`.s`/`.s.i` 逐字节相同；`make selfhost-native` 退出 0 零失败，
  期间 `yh_link` 真实调用 **106 次**。
- 顺带记录未修问题：`pub const` 整数字面量按 32 位有符号折叠
  （`0x80000000` 折不出来）；上一代种子 `bin/yh` 在含 `e`/`E` 的十六进制
  字面量上报浮点/整数转换错，因此 `link/` 只能由 `$(YH)` 冷编。
- **最终链接步仍是 `clang -o`**：替换它需要 Mach-O 可执行文件链接器
  （分段、stub 与惰性绑定、chained fixups、ad-hoc 签名），属 TC8–TC10。
- 详情见 [完成记录](01-finished/yh-linkMach-O出口与编译器汇编步替换-2026-10-04.md)。

# 2026-10-04 yh-link Mach-O 可执行文件链接器调研

- 探明静态路线不可行：`ld -o out -e _main obj.o`（不带 `-lSystem`）直接报
  `dynamic executables or dylibs must link with libSystem.dylib`。macOS 没有
  静态 libc，自带 OS 层也不现实——编译器真正未定义的外部符号有 18 个，含
  `_getattrlistbulk` 与 `_execvp`。
- 解析并实测了 `ld` 产出的最小可执行文件：`__PAGEZERO`/`__TEXT`/`__DATA`/
  `__LINKEDIT` 四段、16 个 load commands、`LC_MAIN` 入口指向 `__text` 内
  `_main` 的文件偏移。
- **实测出 ad-hoc 签名布局并逐字段核对**：SuperBlob + CodeDirectory
  v=0x20400（88 字节头 + identifier + nCode×32 页哈希），`ld` 自动做
  `flags=0x20002(adhoc,linker-signed)`。页哈希与 `hashlib` 逐字节一致；
  `codeLimit` 是**签名 blob 的文件偏移**（不是 `__LINKEDIT` 起点），所以末页是
  短的。
- **关键发现：codesign blob 内部是大端**（`CS_SuperBlob`/`CS_CodeDirectory`
  的整数用网络字节序），与 Mach-O 其余部分相反。按小端读会把 `0xfade0cc0`
  读成 `0xc00cdefa`，一路错到底。解析与写出都要用大端。
- 链接器自带 SHA-256（`link/src/ln/10_sha256.yh`），6 个向量对 `shasum -a 256`
  一致，覆盖 55/56 字节这个补齐分界。
- 修掉一个自造 bug：压缩循环漏了 `t += 1`，轮数靠 `t` 残留值被跳过，摘要
  静默算错而无任何报错（后来加 `t = 0;` 复位反而变成死循环，才暴露出来）。
- 决策文档见 [Mach-O 可执行文件链接器设计](03-design/yh-linkMach-O可执行文件链接器设计.md)，
  TC9/TC10/TC11 已拆入 [todo](todo.md)。本轮只做调研与 SHA-256，**尚未开始
  写链接器**。

# 2026-10-04 yh 编译期过程：V 实现调研与规划交付

- 交付 [设计](03-design/yh-编译期过程设计.md)与
  [实施方案](02-plan/yh-编译期过程实施方案.md)，推荐 `@[comptime] fn` 和受限
  typed AST 求值器；CT0–CT2 为首版，全局类型位置、跨模块正文、条件编译和
  反射分别分期。**本次是规划交付，编译器尚未实现新属性。**
- 核对 V 固定提交的解析器、类型检查和反射展开，区分内建编译期操作、
  条件选择与用户函数求值；方案包含源码诊断、整数边界、共享预算、
  常量就绪、缓存依赖和滚动自举接入。
- 当前探针确认函数 const 调用/未知属性被拒；发现全局数组与前向 const
  读取占位零的既有缺口，记录于设计 §5，本次未修复。
- `make`、`make test` 通过：两套语法门各 68 正例/42 反例，运行语义 100/100。
  完成详情见 [交付记录](01-finished/yh-编译期过程规划交付-2026-10-04.md)；
  未修改源码/活跃语法、未滚种子，未重跑 selfhost-native。

# 2026-10-04 yh 编译期首版语法分析与计划修订

- 按用户选择改为 `$if/$for` 控制形式，保留 `@[comptime]` 函数属性；
  建议首版加入条件选择、区间展开、标量函数求值与 assert/error/warn。
- 新增[首版语法分析](03-design/yh-编译期首版语法分析.md)，同步过程设计、
  实施方案与 todo；首版现行阶段为 CT0–CT3，反射/布局/跨模块与高阶能力后续。
- 临时参考语法：22 个新增 .yh 正反例全部符合预期，正例精确歧义报告 0；
  原有 110 个语法用例保持原判定。未将未实现功能接入默认回归。
- make 退出 0（产物已是最新，复核种子哈希）；本次只交付分析，
  未改编译器/活跃语法、未重跑完整主门、未滚种子。
- 详情见[完成记录](01-finished/yh-编译期首版语法分析-2026-10-04.md)。

# 2026-10-04 yh 编译期语法收敛到函数体

- 按用户要求删除顶层 $if；建议控制与诊断 $... 均限函数内语句，
  @[comptime] 保持函数属性。顶层声明和模块依赖登记沿用现状。
- 删除声明选择预处理与两个顶层参考产生式，统一函数内常量条件契约；
  同步首版语法分析、过程设计、实施方案和 todo。
- 修订参考语法 30/30，新增正例精确歧义报告 0，原语法语料 110/110；
  make 退出 0（复核种子哈希），文档与 diff 检查通过。
- 本次是设计修订，未修改编译器/活跃语法、未重跑完整主门、未滚种子。
  详情见[收敛记录](01-finished/yh-编译期函数内语法收敛-2026-10-04.md)。

# 2026-10-04 yh 编译期函数显式调用分析

- 分析 $函数名(实参) 调用 @[comptime] 函数的可行性，
  推荐 $f 统一用于普通/CT 函数体内及常量值位置；属性定义身份，$ 表示求值请求。
- 新增[显式调用分析](03-design/yh-编译期函数显式调用分析.md)，
  同步首版设计、求值设计、实施方案与 todo；顶层控制仍不加入。
- 实验证实独立诊断语句叠加调用表达式有 4 处精确歧义；
  统一 primaryExpr 入口后为 0，34 个结构判定与原语法语料 110/110 符合预期。
  其中 10 个形态须在正式语义门拒绝，未宣称已实现。
- make 退出 0（种子哈希复核）、本次编译期文档/diff 检查通过；
  未改编译器/活跃语法、未重跑主门、未滚种子。
  详情见[交付记录](01-finished/yh-编译期显式调用分析-2026-10-04.md)。

# 2026-10-04 AGENTS.md 新增 Linux 环境验证（容器方案）

- 按用户要求在 AGENTS.md 增补《Linux 环境验证（容器方案）》章节：
  需要 Linux 测试时优先用容器（docker/podman，arm64 镜像）而非虚拟机；
  写明前提事实（bin/yh 为 darwin/arm64 Mach-O、Linux ELF 种子待入库、
  Makefile 按宿主选种子）、挂载仓库的操作示例、容器内自举的预期用法
  （SEED=bin/yh-linux-arm64）与约束（临时产物放 tmp/、不滚种子、
  结论记 finish.md）。开发策略中"Linux CI/开发需另行建立"一句指向该章节。
- 纯文档变更，未改编译器/语法/测试，未重跑主门、未滚种子。

# 2026-10-04 容器方案改用 macOS 系统 container 并实测验证

- 按用户要求把 AGENTS.md《Linux 环境验证（容器方案）》的运行时从
  docker 改为 macOS 系统自带 `container`（Apple Container 1.5.0）：
  `container run --rm -it -v "$PWD":/work -w /work alpine:latest sh`。
- 实测通过：重启 apiserver 后 1 秒级启动，容器内 `uname -m`=aarch64、
  仓库正确挂载 /work。途中发现本机服务曾卡 "Starting container" 约
  5 分钟后报 `XPC timeout ... containerCreate`，`container system
  stop && start` 重启后恢复——该故障处理已写入 AGENTS.md。
- 编译器/语法/测试未改动，未重跑主门、未滚种子。

# 2026-10-05 yh 编译期过程首个竖切片

- 实现 `@[comptime]` 私有整数函数与 `$f(...)` 显式调用，当前求值范围为单条
  整数 return 表达式；结果能进入全局 const、嵌套调用实参和普通函数运行期初始化。
- 接入函数体 `$if/$for`，无顶层形式；条件分支按常量选择，整数 `[lo..hi)` 区间
  按轮绑定并静态展开；单区间 1024 次、编译单元合计 100000 次预算。
- 编译期求值和登记主要放在 `compiler/comptime/`；语法接缝位于
  `compiler/parse/parse_comptime.yh`。新增运行、失败、语法和同模块多文件验收。
- 验证：`make`、`make test`、`python3 tests/yh/check.py --coverage --quiet`、
  `make selfhost-native` 全绿；语法 71/71+44/44，运行 109/109，固定点 14 个产物，
  自解析 58 源文件，模块 17/17、项目 80/80。
- 主门通过后已执行 `make seed`，新种子 SHA-256 为
  `ac8806b63e7843c3dedd330feb0a02f463db3bf2b858bbb748c174757676e43a`；
  用新种子冷编 `compiler/` 并复核哈希成功。
- 完整语句解释、诊断指令、typed CT IR、跨模块正文、目标标记与全局类型布局求值
  继续列在 `docs/todo.md`。

# 2026-10-05 yh 编译期 `$if` 输出目标标记

- 在 `$if` 条件上下文中将 `linux`、`darwin`、`arm64` 解析为输出目标布尔常量；
  `linux/darwin` 取自 `-target` 设置的输出方言，`arm64` 表示当前受支持后端。
- 目标标记不成为全局保留字；同名局部变量在 `$if` 外照常解析，条件内的内建标记
  不受局部遮蔽。逻辑 `&&/||` 增加编译期常量折叠，以支持组合目标条件。
- 实现位于 `compiler/comptime/ct_target.yh`，解析器只在 `$if` 条件期间打开目标
  标记上下文；新增 `tests/yh-run/run/58-comptime-target.yh` 覆盖目标分支、布尔
  组合及同名局部变量。
- 验证：`make`、`make test`、`make selfhost-native` 与目标 Linux/Darwin 汇编检查通过；
  主门通过后滚动种子并冷编复核。门禁计数、哈希与剩余工作见
  [本轮交付记录](01-finished/yh-编译期目标标记-2026-10-05.md)。

# 2026-10-05 yh 编译期诊断指令

- 普通函数内接入独立语句 `$assert/$compile_error/$compile_warn`：断言验证常量 bool，
  错误/警告接受字符串字面量，诊断限制在语句位置；未选 `$if` 分支不触发。
- 诊断代码主要在 `compiler/comptime/ct_diag.yh`，调用类型检查与语句执行接缝位于
  `compiler/parse/`。增加单文件正反例及模块 AST 路径回归；`@[comptime]` 函数内
  按调用实参触发诊断仍待 CT3 完整求值器。
- 验证：`make test`、`make selfhost-native`、滚种子后的冷编 `make` 均通过；运行语料
  119/119、模块项目 80/80，14 个产物固定点一致。新种子 SHA-256：
  `ce7124a054ab94e35750c8d5ab4ce06504e59302a91895248cca3e2c5d26666f`。详见
  [诊断指令完成记录](01-finished/yh-编译期诊断指令-2026-10-05.md)。

# 2026-10-05 yh 编译期整数边界与常量就绪

- 常量折叠按目标整数宽度和符号执行；检查一元负号、加减乘溢出、除零/模零、
  最小负数除 `-1` 和移位边界，无符号比较/除法/右移按无符号语义执行。
  受限 `@[comptime]` 单条 return 求值器复用同一边界实现。
- 新增 `CSym.const_ready`，禁止前向全局 const 和 pass1 数组长度读取占位零；
  有序全局标量初始化不变。全局数组长度布局求值仍待 CT5A。就绪状态独立于符号
  flags，避免破坏模块 AST 局部绑定快照。
- 增加 `fail-contains` 诊断子串断言及 `tests/yh-run/fail/71–79`、`run/60–61`。
  `make test` 全绿：运行语料 130/130；`make selfhost-native` 全绿：14 个产物固定点、
  60 个源文件自解析、模块 17/17、项目 80/80；滚种子后冷编 `make` 成功。
- 新种子 SHA-256：`5070e9be14e95ee034248ac78d2504595ddccc259e373409ee971c89fa32a07d`。
  详见[整数边界与常量就绪完成记录](01-finished/yh-编译期整数边界与常量就绪-2026-10-05.md)。

# 2026-10-05 yh 编译期结构嵌套深度限制

- `$if` 与 `$for` 共用 32 层结构嵌套计数，超限时在过深控制结构处报告语义诊断；
  解析入口统一进入/退出计数，确保正常返回与解析错误路径恢复状态，模块重置也清零计数。
- 新增 `tests/yh-run/fail/80-comptime-control-depth.yh`、
  `fail/81-comptime-for-control-depth.yh` 与 `run/62-comptime-control-depth-limit.yh`，
  覆盖 33 层拒绝、空 `$for` 与 `$if` 混合计深，以及上限 32 层可运行。
- 实现位于 `compiler/comptime/ct_00_model.yh`、`ct_registry.yh` 和
  `compiler/parse/parse_comptime.yh`。typed AST 展开新增节点 100000 上限尚未实现，
  留待实际 AST 展开模型接入；展开来源诊断和编译期函数内诊断仍属后续 CT1/CT3 工作。
- 验证：`make test` 通过（语法 71/71 + 44/44，运行语义 133/133）；
  `make selfhost-native` 通过（14 个产物固定点、60 个源文件自解析、模块 17/17、
  项目 80/80）；`make seed` 后冷编 `make` 成功。种子 SHA-256：
  `adb00cf2da3698e51ad5dafd6431db685911ec013f2fc8bb7d73187fc393b4a2`。

# 2026-10-05 yh 编译期 for 展开跳转边界

- 修复 `$for` 展开体内的 `break/continue` 错误跳出到外层运行期循环的问题。`comptime`
  记录每层 `$for` 开始时的运行期循环深度；只有展开体内新建的普通循环可以接收跳转。
- 新增 `tests/yh-run/fail/82-comptime-for-break-escape.yh`、
  `fail/83-comptime-for-continue-escape.yh` 作为拒绝反例，及
  `run/63-comptime-for-inner-runtime-loop.yh` 验证展开体内普通循环仍可使用 `break`。
- 实现位于 `compiler/comptime/ct_00_model.yh`、`ct_registry.yh`，以及
  `compiler/parse/parse_comptime.yh`、`parse_stmt.yh`。
- 循环绑定约束已有语义拒绝赋值和取地址；新增 `fail/84–85` 正反映射这两个诊断。
- 验证：`make test` 通过（语法 71/71 + 44/44，运行语义 138/138）；
  `make selfhost-native` 通过（14 个产物固定点、60 个源文件自解析、模块 17/17、
  项目 80/80）；`make seed` 后冷编 `make` 成功。种子 SHA-256：
  `e0ad233806894cf0e752ccfffa42b443a4dce4d13515c8aa819d2743232846c8`。

# 2026-10-05 yh 编译期展开来源诊断

- 嵌套 `$for` 体中的错误和警告现在附带从外层到内层的迭代值链，例如
  `编译期展开值: 2 -> 5`。尚未开始迭代的内层区间不加入来源链。
- 新增 `tests/yh-run/fail/86-comptime-expansion-trace.yh` 锁定双层展开错误来源；
  诊断缓冲区按有界追加处理长路径和消息。
- 实现位于 `compiler/gen/buffer.yh`、`compiler/gen/state.yh` 与
  `compiler/comptime/ct_registry.yh`、`compiler/parse/parse_comptime.yh`。
  CT 函数内诊断按实际调用路径执行仍属于 CT3。
- 定向运行语料 run 1/1、fail 4/4 通过；`make test` 通过（语法 71/71 + 44/44，
  运行语义 139/139）。`make selfhost-native` 通过（14 个产物固定点、60 个源文件
  自解析、模块 17/17、项目 80/80）；`make seed` 后冷编 `make` 成功。
- 新种子 SHA-256：`6eb93755f1af8a4944c7f7921dd3a91ba8daeb315122f93debb28034c333e626`。
  详见[编译期展开来源诊断完成记录](01-finished/yh-编译期展开来源诊断-2026-10-05.md)。

# 2026-10-05 yh 编译期函数调用链首片

- `@[comptime]` 函数的单条整数 `return` 表达式支持显式 `$g(...)`，可前向引用、
  嵌套实参并跨同模块多个源文件执行。定义检查只校验调用签名/参数，不提前执行形参值。
- 统一调用器在实际执行时验证 typed 实参并限制 64 层共享调用帧；无条件递归超限会
  正常报错，不耗尽宿主栈。新增 run/64 与 fail/87–89；扩展 `comptimelocal` 项目用例。
- 实现位于 `compiler/comptime/ct_eval_expr.yh`、`ct_registry.yh` 与
  `compiler/parse/parse_expr.yh`。语句级 CT 执行器、typed AST、局部值、普通控制流、
  短路、共享步数预算和 CT 函数诊断仍未完成。
- 验证：`make test` 通过（语法 71/71 + 44/44，运行语义 143/143）；
  `make selfhost-native` 通过（14 个产物固定点、60 个源文件自解析、模块 17/17、
  项目 80/80）；`make seed` 后冷编 `make` 成功。
- 新种子 SHA-256：`c07078874e874cfa54230d3a0cb9ffd562ee2251dd7d3e11bb781ab713e8dd50`。
  详见[编译期函数调用链首片完成记录](01-finished/yh-编译期函数调用链首片-2026-10-05.md)。

# 2026-10-05 yh 编译期条件递归

- 编译期函数执行器支持整数比较条件、普通 `if/else` 和 `return`；按当前参数值只执行
  选中分支，另一支只在普通函数体检查阶段做语义检查。条件递归沿用共用 64 层调用帧限制。
- 新增 `tests/yh-run/run/65-comptime-conditional-recursion.yh`，阶乘结果为 720，且未选
  分支中的 `$compile_error` 不触发。
- 实现位于 `compiler/comptime/ct_eval_expr.yh`。局部声明、赋值、普通 for、短路、步数
  预算和 CT 函数诊断的实际调用路径仍待后续 CT3。
- 验证：`make test` 通过（语法 71/71 + 44/44，运行语义 144/144）；
  `make selfhost-native` 通过（14 个产物固定点、60 个源文件自解析、模块 17/17、
  项目 80/80）；`make seed` 后冷编 `make` 成功。
- 新种子 SHA-256：`f5c155fc6479ada60022ce8e961ed919401b65bdc90236398fe03ba978757f5e`。
  详见[编译期条件递归完成记录](01-finished/yh-编译期条件递归-2026-10-05.md)。

# 2026-10-05 yh 编译期函数诊断调用路径

- 编译期函数中的 `$assert/$compile_error/$compile_warn` 现在在实际执行到语句时触发；
  `$if` 未选分支中的诊断不触发。断言使用整数比较条件，错误/警告消息要求字符串文字量。
- CT 诊断从登记的函数源码快照解码消息，避免读取后续解析文件的源码缓冲区。新增
  `tests/yh-run/run/66`、`fail/90–91` 覆盖警告路径、未选错误路径、主动错误和失败断言。
- 实现位于 `compiler/comptime/ct_eval_expr.yh` 和 `ct_diag.yh`；局部值、赋值、普通循环、
  短路、typed CT IR 与执行步数预算仍待后续 CT3。
- 验证：`make test` 通过（语法正例 71/71、反例 44/44，运行 run 65/65、fail 74/74、
  pass 8/8，共 147/147）；`make selfhost-native` 通过（14 个产物固定点、60 个源文件
  自解析、模块 17/17、项目 80/80）；`make seed` 后冷编 `make` 成功。警告内容由独立
  编译命令确认输出。
- 新种子 SHA-256：`c38aac40bdeec230fbe36dfe814cd97e335739c1c5c3cd304171d9776f0721fb`。
  详见[编译期函数诊断调用路径完成记录](01-finished/yh-编译期函数诊断调用路径-2026-10-05.md)。

# 2026-10-05 yh 编译期函数布尔短路

- 编译期函数的 `if` 与 `$assert` 条件支持 `&&/||` 短路，`&&` 优先级高于 `||`；被跳过的右侧不执行除法或编译期函数调用。
- 新增 `tests/yh-run/run/67-comptime-short-circuit.yh`，覆盖短路方向、零除保护、分组、优先级、断言及跳过的错误调用。
- 实现位于 `compiler/comptime/ct_eval_bool.yh`、`ct_eval_expr.yh` 和 `ct_00_model.yh`。
- `make test` 通过（语法 71/71 + 44/44，运行 148/148）；`make selfhost-native` 通过（14 个产物固定点、61 个源文件自解析、模块 17/17、项目 80/80）；滚种子后冷编 `make` 成功。
- 新种子 SHA-256：`9b784e530a81678e705e0ab48515d8e2e321b39491d5d9e26078374cf7e65531`。详见[编译期函数短路逻辑完成记录](01-finished/yh-编译期函数短路逻辑-2026-10-05.md)。

# 2026-10-06 yh 编译期枚举 values 首片

- 支持函数体内 `$for item in Enum.values`，按声明顺序展开，提供只读 `item.name` 与 `item.value`；保留重复判别值，空枚举零轮执行。typed `@[comptime]` 函数按展开后的语句块解释执行。
- 新增 run/93、fail/109–110、语法正例 72，并扩展 `comptimelocal` 项目验证模块 AST 路径。
- 实现位于 `compiler/comptime/ct_enum.yh`、`compiler/parse/parse_comptime.yh`，元信息语义/静态名称发射位于 `compiler/gen/sem_value.yh` 与 `emit_arm64.yh`。CT4 的字段反射仍待规划。
- `make test` 全绿（语法 72/72 + 44/44，运行 193/193）；`make selfhost-native` 全绿（14 项固定点、65 个源文件自解析、模块 17/17、项目 82/82）；滚种子后冷编 `make` 成功。
- 新种子 SHA-256：`1257f1b7126819c845e2bd315725993001d63784f2191def8b6e4550c5b9908f`。详见[编译期枚举 values 首片完成记录](01-finished/yh-编译期枚举values-2026-10-06.md)。

# 2026-10-06 yh 编译期全局数组长度嵌套调用

- CT5A 早期安全探测支持无环的简单单 `return` 整数 CT 调用树；全局整数常量可由
  嵌套 `$helper(...)` 求值得到，并用于后续数组和结构体字段长度。互递归图不会进入执行，
  仍报告常量未就绪。typed 函数体和布局请求/依赖环仍待后续阶段。
- 新增 `tests/yh-run/run/111-comptime-array-length-nested-call.yh` 与
  `tests/yh-run/fail/112-comptime-array-length-call-cycle.yh`。
- `make test` 全绿（语法 72/72 + 44/44，运行 93/93、拒绝 94/94、通过 8/8，共 195/195）；
  `make selfhost-native` 全绿（14 项固定点、65 个源文件自解析、模块 17/17、项目 82/82）；
  `make seed` 后冷编 `make` 成功。
- 新种子 SHA-256：`36022fd2fd605cc81de4e31b356efbcc0bcfd8662815a14b031ffebca884a484`。
  详见[编译期全局数组长度嵌套调用完成记录](01-finished/yh-编译期全局数组长度嵌套调用-2026-10-06.md)。

# 2026-10-06 yh 编译期类型表达式依赖求解

- 数组长度支持保存并延迟求值的整数表达式、显式 `$f(...)` 和 pending `sizeof(T)`；
  调度器按 READY 依赖推进数组与结构体布局，pending sizeof 依赖可穿过嵌套 typed CT 调用。
- 新增 run/124–125、更新 fail/119，并扩展 `comptimelayoutdeps` 模块项目覆盖跨文件前向
  const 与表达式长度。普通前向全局 const 仍拒绝；值/布局环诊断报告环类别，完整混合路径
  后续再补。
- `make test` 全绿（语法 72/72 + 44/44，run 103/103、fail 97/97、pass 8/8，共 208/208）；
  `make selfhost-native` 全绿（14 项模块固定点、67 个源文件自解析、模块 17/17、项目 83/83）。
- `git diff --check`、`make seed` 与新种子冷编 `make` 均通过。
- 新种子 SHA-256：`ab66e3385286f312fe9c05999cbd405a3cfe4b05fb20645fce9c1f2142f56175`。
  详见[编译期类型表达式依赖求解完成记录](01-finished/yh-编译期类型表达式依赖求解-2026-10-06.md)。

# 2026-10-06 yh 编译期混合布局依赖环诊断

- CT5A 布局调度现在为编译期整数值和数组/结构体布局建立混合依赖图，并沿 typed CT 函数
  的直接、嵌套调用收集常量读取和 `sizeof` 布局关系。停滞时输出闭合节点路径；纯常量环
  保留原名称链，无法确认闭环时继续给出原未完成依赖诊断。
- fail/119 覆盖 `ITEM_COUNT` 经嵌套 CT `sizeof(PendingLayoutPacket)` 和字段数组长度回到自身；
  fail/126 覆盖数组长度经嵌套 CT 函数读自身 `sizeof`，fail/127 覆盖数组长度直接读自身
  `sizeof`。三例均断言完整闭链。
- `make test` 全绿：ANTLR 语法正例 72/72、反例 44/44；运行正例 103/103、负例 99/99、
  pass 8/8，共 210/210。`make selfhost-native` 全绿：14 个模块产物固定点一致、68 个源文件
  自解析、语料 210/210、模块语法 17/17、项目验收 83/83；并发扫描、前端缓存、运行时内存、
  命令及链接缓存检查通过。
- `git diff --check` 通过；`make seed` 与种子冷编 `make` 通过。
- 新种子 SHA-256：`bc0680ac4aff9d98de9e846d183285f964de4000180aed48816cdfdd928792a1`。
  详见[编译期混合布局依赖环诊断完成记录](01-finished/yh-编译期混合布局依赖环诊断-2026-10-06.md)。

# 2026-10-06 yh 编译期临时聚合下标读取

- typed CT 函数可读取函数返回定长数组的多级下标，以及函数返回结构体中的数组字段下标；下标写入仍限当前帧的可变局部值。
- 新增 `tests/yh-run/run/94-comptime-index-aggregate-expression.yh` 和 `fail/128-comptime-temporary-index-write.yh`，覆盖返回二维数组/结构体数组字段读取及拒绝临时数组写入；结果为 29。
- `make test` 全绿（语法 72/72 + 44/44，运行 104/104、100/100、pass 8/8，共 212/212）；`make selfhost-native` 全绿（14 个产物固定点、68 个源文件自解析、语料 212/212、模块 17/17、项目 83/83）。
- `make seed`、种子冷编 `make` 与 `git diff --check` 通过。新种子 SHA-256：`66d431a0764c69eb21ca59a59aac4bd25441fdd61f2f3173144cd0ffb493b81e`。详见[编译期临时聚合下标读取完成记录](01-finished/yh-编译期临时聚合下标读取-2026-10-06.md)。

# 2026-10-06 yh 编译期结构体元素切片

- typed 编译期执行器支持整数或受支持结构体元素切片的视图、形参别名、成员写入、for-in 按值复制和嵌套返回；顶层结果可用于局部/全局静态物化。切片 backing 延后输出，确保嵌套切片字段不打断父结构或结构体数组布局。
- 新增 `tests/yh-run/run/97-comptime-struct-slice-elements.yh`，扩展 `comptimelocal` 跨源文件项目，并保留浮点、指针和浮点切片字段拒绝用例。
- `make test` 全绿（语法 72/72 + 44/44，运行 107/107、拒绝 101/101、pass 8/8，共 216/216）；`make selfhost-native` 全绿（14 项固定点、69 个源文件自解析、语料 216/216、模块语法 17/17、项目 83/83 和其余自举探针）。
- `git diff --check`、`make seed` 与种子冷编 `make` 通过。新种子 SHA-256：`89cad9428eb4b85395490a8a4425883e866016f4a61246de00608df69428192a`。详见[编译期结构体元素切片完成记录](01-finished/yh-编译期结构体元素切片-2026-10-06.md)。

# 2026-10-07 yh 编译期 typed 局部指针读写

- typed 编译期函数支持当前帧整数局部槽的 `&` 取址、`*` 读取与写回。解释器指针只引用局部槽；指针参数/返回、聚合逃逸、算术、成员/下标取址、全局/字符串指针求值及空指针解引用均拒绝，其中空指针解引用有明确诊断。
- 新增 run/131 正例及 fail/130–131 边界用例。旧入库种子对新行为的定向用例失败，当前实现三例全过。
- `make test` 全绿：语法正例 73/73、反例 44/44；运行 109/109、拒绝 103/103、pass 8/8，共 220/220。`make selfhost-native` 全绿：21 个模块固定点产物、71 个源文件自解析，模块语法 17/17、项目验收 84/84。
- `git diff --check`、`make seed`、新种子冷编 `make` 与滚种子后 `make selfhost-native` 全部通过；后者再次确认 21 个固定点产物、71 个自解析源文件、220/220 语料、17/17 模块语法及 84/84 项目验收。新种子 SHA-256：`a37e309a604d52290b13e413e907da254d041e3b4337bb2f581c3feeb7d11fee`。详见[完成记录](01-finished/yh-编译期typed局部指针读写-2026-10-07.md)。

# 2026-10-07 yh 编译期 typed 指针形参

- typed 编译期函数的 `*T`（整数 `T`）形参可别名调用方帧的整数局部槽：被调方 `*param` 读写该槽，
  也可继续向下传递；`comptimelocal` 新增跨源文件指针形参写回断言。
- 新增存活调用帧链（`CtFrame.live_next` + `ct_live_frames`，统一经 `ct_ir_frame_release` 收缩帧）
  与 `ct_ir_pointer_target`：解引用和指针形参绑定都必须先验证地址落在存活帧局部槽区间内。
  **附带修复**：`let text *char = "abc"; return *text;` 此前让编译器段错误（字符串标签值被当作宿主
  `CtValue` 地址），现在报「编译期指针必须指向当前存活调用帧的整数局部值」。
- 仍拒绝：指向指针/浮点/聚合的指针形参、指针返回与聚合逃逸、指针算术、成员/下标取址、全局与字符串
  指针常量求值；空指针解引用保留专有诊断。`fail/104` 改为指向浮点的指针形参，`fail/129` 诊断片段随声明消息更新。
- 新增 run/132 与 fail/132–134。改动前：正例因形参类型不受支持而失败、fail/133 编译器崩溃（信号 11）、
  fail/134 诊断不符；改动后四例全部按预期通过。
- `make test` 全绿：语法正例 73/73、反例 44/44；运行 110/110、拒绝 106/106、pass 8/8，共 224/224。
  `make selfhost-native` 全绿：21 个模块固定点产物、71 个源文件自解析、语料 224/224、模块语法 17/17、
  项目验收 84/84。
- `git diff --check`、`make seed`、新种子冷编 `make` 与滚种子后 `make selfhost-native` 全部通过。
  新种子 SHA-256：`c572a1e1355f77e0828f1f8913e66b4b2624d5b1c3e70658fdb24adc9ba0be0c`。
  详见[完成记录](01-finished/yh-编译期typed指针形参-2026-10-07.md)。

# 2026-10-07 yh 编译期 typed 聚合元素取址

- typed 编译期函数可对当前帧内的整数聚合元素取址：`&array[i]`、`&slice[i]`（含切片视图元素）
  与 `&struct.field`；所得指针与局部变量指针同权，可解引用读写、可作为整数指针形参传给更深的调用。
- 指针目标校验从局部槽区间扩展到「局部槽 + 存活帧拥有的聚合元素块」（含非拥有视图块），
  按该位置元素的实际类型校验；非整数元素/字段取址、临时值取址、`&*p` 重取址仍拒绝。
- 新增 run/133，反例 fail/135（非整数元素）与 fail/136（临时值）；改动前正例失败、两条反例已按预期拒绝。
- `make test` 全绿：语法正例 73/73、反例 44/44；运行 111/111、拒绝 108/108、pass 8/8，共 227/227。
  `make selfhost-native` 全绿：21 个模块固定点产物、71 个源文件自解析、语料 227/227、模块语法 17/17、
  项目验收 84/84。
- `git diff --check`、`make seed`、新种子冷编 `make` 与滚种子后 `make selfhost-native` 全部通过。
  新种子 SHA-256：`da65b795242c2c446acf9ce3cce046eeeb19bc576594b807655991e9d00c0ef8`。
  详见[完成记录](01-finished/yh-编译期typed聚合元素取址-2026-10-07.md)。

# 2026-10-07 yh 编译期 typed 浮点标量

- typed 编译期执行器支持 f32/f64 标量：字面量、局部值、`+ - * /` 与一元正负号、比较、
  显式转换（整数↔浮点、浮点↔浮点、f32 窄化）以及浮点形参与浮点返回。
- 浮点值以 IEEE754 位模式保存在 `CtValue.value`（类型由 `type_id` 区分），顶层常量物化
  同时写入 `Res.ival`/`Res.fval_bits` 并按浮点寄存器装载；f32 在写入与物化时窄化。
- 新增 `compiler/comptime/ct_ir_float.yh`，接入常量、一元、二元、转换、赋值与局部声明路径。
- 顺带修复三处既有缺口：const 引用从不填 `fval_bits`/不按浮点装载；编译期局部声明初始化
  对 f32 走整数截断损坏位模式；单精度判定误用 `TY_F32` 常量而非类型表 kind。
- 一元负号改符号位翻转、浮点转整数统一有符号截断，避免生成冻结子集外的 `fneg`/`fcvtzu`
  （自编导入审计构建曾因此失败）。
- 新增 run/134、fail/137–138，`comptimelocal` 增加跨源文件浮点形参/返回与整数折算断言。
- `make test` 230/230；`make selfhost-native` 全绿（21 固定点、72 自解析、语料 230/230、
  模块 17/17、项目 84/84，含自编导入审计构建）；滚种子后冷编与主门复核通过。
  新种子 SHA-256：`e47a63fb61c89f1e3f4586342081d7691ebf2890e6add3501ed7bf53721ce423`。
  详见[完成记录](01-finished/yh-编译期typed浮点标量-2026-10-07.md)。

# 2026-10-07 yh 前端浮点常量折叠

- 前端常量折叠支持浮点：算术、比较、一元正负、显式转换（整数↔浮点、浮点↔浮点、f32 窄化），
  普通函数里的 `$assert` 可直接比较浮点常量。
- 浮点常量值统一把 IEEE754 位模式写入 `Res.ival` 与 `Res.fval_bits`（字面量、折叠结果、
  编译期函数物化三处一致）；修复 `const A f64 = 1.5;` 引用读到 0，以及浮点常量一元负号
  落入整数分支并被改写成 `int` 的缺陷。
- 新增 `fp64_from_bits`/`fp64_norm_bits`（gen）、`sem_fold_float_binop`、`sem_fold_float_convert`
  与 `sem_fold_const_unary` 浮点分支；一元负号走符号位翻转、浮点转无符号整数按有符号截断，
  不生成冻结子集外的 `fneg`/`fcvtzu`。
- 新增 run/135、fail/139，`comptimelocal` 增加浮点常量折叠与浮点常量物化断言。
- `make test` 232/232；`make selfhost-native` 全绿（21 固定点、72 自解析、语料 232/232、
  模块 17/17、项目 84/84）；滚种子后冷编与主门复核通过。
  新种子 SHA-256：`5f6f072a7520057716d4975d5e2b91560bb7b24c03b0d919280e54c5cacc08c7`。
  详见[完成记录](01-finished/yh-前端浮点常量折叠-2026-10-07.md)。

# 2026-10-07 yh 编译期 typed 浮点聚合元素

- 浮点聚合元素在编译期可用：定长数组元素、切片元素、结构体浮点字段（含嵌套数组字段）
  可构造、下标读写、切片视图别名写回、for-in 迭代、作为聚合形参/返回值，并可静态物化为
  顶层常量；f64 发位模式，f32 先经 `ct_ir_fp32_bits` 取单精度位模式。
- 支持门从「整数叶」放宽为「整数或浮点叶」；新增 `ct_ir_norm_scalar` 统一元素/字段/局部/
  赋值的标量归一；诊断文本改为「整数、浮点」。
- 新增 run/136；`fail/103`、`fail/105`、`fail/129` 改造为指针元素数组/切片字段与指针元素
  切片返回仍拒绝，`fail/137` 改为浮点元素取址仍拒绝；`comptimelocal` 增加浮点数组形参、
  浮点切片返回与顶层浮点切片物化断言。
- `make test` 233/233；`make selfhost-native` 全绿（21 固定点、72 自解析、语料 233/233、
  模块 17/17、项目 84/84）；滚种子后冷编与主门复核通过。
  新种子 SHA-256：`9f47cde4d02c1f578fec2b727848e65969a11ea545044c8d1ad71ee62747fb83`。
  详见[完成记录](01-finished/yh-编译期typed浮点聚合元素-2026-10-07.md)。

# 2026-10-07 yh 编译期 typed 浮点指针

- 编译期指针目标从整数槽放宽到标量槽：`&` 取址、`*p` 解引用读写与 `*f64`/`*f32`
  形参跨帧写回、二次转发都支持浮点；类型仍须逐类型相等，存活帧校验不变。
- 解引用读写直接搬运 `CtValue`（位模式），无需浮点特判；浮点赋值/复合赋值沿用 STORE
  路径的浮点归一。诊断文本从「整数局部变量/整数聚合元素/整数局部值」改为「标量…」。
- 新增 run/137；`fail/104` 改为指向指针的指针仍拒绝，`fail/137` 改为浮点指针返回仍拒绝，
  `fail/138` 改为结构体浮点指针字段仍拒绝，`fail/135` 更新为「非标量聚合元素取址」；
  `comptimelocal` 增加跨源文件 `*f64` 形参写回断言。
- `make test` 234/234；`make selfhost-native` 全绿（21 固定点、72 自解析、语料 234/234、
  模块 17/17、项目 84/84）；滚种子后冷编与主门复核通过。
  新种子 SHA-256：`55ed0dab8478e6985fe5f10fc5939602129d634cc6531712e115503b3500f280`。
  详见[完成记录](01-finished/yh-编译期typed浮点指针-2026-10-07.md)。

# 2026-10-07 yh 编译期 typed 指针算术与指针下标

- 编译期指针算术可用：`p + i`、`i + p`、`p - i` 按 `CtValue` 槽步进（编译期聚合元素
  即槽，等价语言上按元素下标前进，f32 元素同样只占一槽），`p[i]` 支持读取与写入。
- 解引用与下标写入统一由存活帧校验（`ct_ir_pointer_target`）解析目标槽，越界地址被拒绝；
  步数绝对值超 100000 直接报错；指针之间的算术、乘除与大小比较仍拒绝。
- 顺带修复：前端 `sem_binop` 的「整数 + 指针」分支漏设结果类型（`let q *T = 1 + p;`
  曾报「不能把非指针值赋给指针」）；`ct_ir_index_read` 改用逐字段复制，
  规避「`*dst = *src;` 整体结构体解引用赋值让编译器段错误」的后端缺陷（已记入 todo）。
- 新增 run/138、fail/140–141；`comptimelocal` 增加跨源文件指针下标累加与指针算术断言。
- `make test` 237/237；`make selfhost-native` 全绿（21 固定点、72 自解析、语料 237/237、
  模块 17/17、项目 84/84）；滚种子后冷编与主门复核通过。
  新种子 SHA-256：`43f3301b1a9d53258ad124e222cd17d3c18e64c37d9fc861847ab894cd3f027e`。
  详见[完成记录](01-finished/yh-编译期typed指针算术与下标-2026-10-07.md)。

# 2026-10-07 yh 编译期 typed 联合体

- 编译期支持整数叶联合体：字面量构造（只初始化一个字段）、成员读写、按值复制、
  形参按值传入与返回值复制到调用方帧。
- 共享存储模拟：每个字段各占一个 `CtValue` 槽，写入后按其他字段类型广播重解释
  （小端整数截断/零扩展）——写 `int` 读 `u8` 取低位、写 `u8` 读 `int` 零扩展，
  与运行期一致；未写入字节在编译期固定为 0。
- 明确边界：联合体字段取址（`&v.field`，共享槽无法保持别名语义）、浮点/指针/聚合
  字段、联合体作数组/切片元素或结构体字段、顶层静态物化一律拒绝并给出诊断。
- 顺带修复模块模式缺陷：`parse/ast_expr.yh` 的 `ast_expr_verify` 要求 `STRUCT_INIT`
  节点类型必须是 `TY_STRUCT`，导致模块代码里任何 union 字面量都报
  「内部错误：表达式 AST 校验失败」；现在同时接受 `TY_UNION`。
- 新增 run/139、fail/142–144；`comptimelocal` 增加跨源文件联合体共享存储断言。
- `make test` 241/241；`make selfhost-native` 全绿（21 固定点、72 自解析、语料 241/241、
  模块 17/17、项目 84/84）；滚种子后冷编与主门复核通过。
  新种子 SHA-256：`b7eb33f1f13a93346923d1102679b6555e08a7bf51ee2bc3f3fe5fa2ec813d2c`。
  详见[完成记录](01-finished/yh-编译期typed联合体-2026-10-07.md)。

# 2026-10-07 yh 编译期单一执行器收敛

- typed IR 成为编译期唯一执行器：删除早期 token 求值器 `ct_eval_expr.yh`、
  `ct_eval_bool.yh`、registry 内的数组长度 token 探测链（`ct_array_length_probe_*`、`ct_find_name`）
  以及 `ct_00_model.yh` 的 `CtReader`/`CtLocal`；`ct_invoke_in_frame` 的回退分支改为
  诊断「编译期函数正文不在受支持的 typed IR 子集内」。`comptime/` 由 5480 行降至 4593 行。
- 根因修法：`parse_global_ct_const_probe` 的准入条件从「token 探测支持该调用树」改为
  `comptime.ct_is_prepared(sym) != 0`。pass1 期间的顶层 `const`/数组长度求值因此让位给
  pass2a 之后的 typed 布局常量依赖调度；受影响的 9 个用例（fail/76、79、88，run/64、92、111、113、115）
  改由 typed 执行器求值，诊断文本不变。
- 过程中的失误与纠正：第一次只改回退分支导致 9 个用例失败，并误删了未提交的
  `ct_eval_expr.yh`（557 行）与 `ct_eval_bool.yh`（git 仅能恢复到 181 行旧骨架）；
  最终通过修根因而不是恢复遗留代码解决。教训记入实施方案。
- `make test` 242/242（run 118/118、fail 116/116、pass 8/8）；`make selfhost-native` 全绿（21 固定点、70 个源文件自解析、
  语料 242/242、模块 17/17、项目 84/84）；滚种子后冷编与主门复核通过。
  新种子 SHA-256：`24ae276e652efc4fd97bf53e7fa7f16bd58bb5bccb3ceece3c835fc38bbcd105`。
  详见[完成记录](01-finished/yh-编译期单一执行器收敛-2026-10-07.md)。

# 2026-10-07 yh 编译期不受支持正文的具体诊断

- `ct_ir_is_supported` 改为 `ct_ir_support_code`，返回首个不受支持构造的原因码
  （100 类型声明、200 goto、300 标签、400 编译期语句、500 其他语句、600 未知表达式种类、
  700 表达式缺少类型），`CtFunction` 增加 `ir_unsupported` 字段随捕获记录。
- `ct_invoke_in_frame` 的回退分支改调 `ct_unsupported_diagnostic(code)`：不在 typed IR
  子集内的编译期函数现在报「…的 goto 语句不在受支持的 typed IR 子集内」这类具体文本，
  而不是统一的「编译期函数正文不在受支持的 typed IR 子集内」；诊断仍延迟到实际调用，
  位置沿用调用处 `file:line:col`；函数体内行列留给后续按需补。
- 新增 fail/145（goto）、fail/146（标签）；`make test` 244/244；`make selfhost-native`
  全绿（21 固定点、70 源文件自解析、语料 244/244、模块 17/17、项目 84/84）。
  新种子 SHA-256：`cf1cbe8212a4ba1cf0dca8f5883463580cc4373d64d43d2476d4e94d4213028b`。
- 顺带把 `docs/todo.md` 里 CT5A 的「受限 token 早期探测」描述改为 typed 布局调度
  （该探测链已在[单一执行器收敛](01-finished/yh-编译期单一执行器收敛-2026-10-07.md)中删除）。

# 2026-10-07 yh 编译期字符串字面量指针常量只读访问

- 编译期字符串字面量现在可以解引用与下标读取：捕获期把字面量字节解码成只读
  `CtValue` 槽池（每字节一槽 + 末尾 0 槽），指针直接指向池首槽，既有的解引用、下标、
  指针算术路径全部复用。新增 `CtPoolSpan` 池表、`ct_pool_register`（转义解码与槽分配）、
  `ct_ir_register_string_pool`（随 `ct_ir_import` 登记同批次字面量）与并行地址表
  `ct_ir_expr_pool`（`ct_ir_grow` 第 5 类 arena）。
- 读：`ct_ir_pointer_target` 在存活帧链后追加池区间查询；写：赋值语句拒绝写入池
  （读与写共用 `ct_ir_lvalue`，保护落在赋值处）。`ct_pool_reset` 随 `ct_reset` 释放。
- 新增 run/141（解引用、下标、NUL、指针算术、转义、形参传递，结果 304）与
  fail/147（写入拒绝）；原 fail/133（解引用被拒）语义已变，删除并由 run/141 取代。
- 边界：顶层/普通函数里的 CT 调用实参仍不支持字符串字面量指针常量（不经 typed IR 捕获）；
  跨模块转发正文按 `token_count` 判据跳过；全局数组地址等其他指针常量仍未支持。
- `make test` 245/245；`make selfhost-native` 全绿（21 固定点、70 源文件自解析、
  语料 245/245、模块 17/17、项目 84/84）。
  新种子 SHA-256：`d212909322cf42fc582216c1db0607a4fde352697229f1c275e5c9581227b559`。
  详见[完成记录](01-finished/yh-编译期字符串字面量指针常量只读访问-2026-10-07.md)。

# 2026-10-07 编译期消费者位置收尾与跨模块字符串字面量锁定

- 跨模块正文里的字符串字面量指针常量解引用经实测**已可用**（导入方重新解析正文，
  自己的 `c_src`/`c_toks` 满足池登记的同批次判据），上一轮文档中「跨模块转发正文不登记池」
  的边界描述已更正；`tests/modules/projects/comptimecross` 新增
  `math.first_letter` 与 host 断言锁定该行为（项目门 84/84）。
- 新增 `tests/yh-run/run/142-comptime-consumer-positions.yh`：编译期调用作为常量的
  各消费者位置（切片范围上界、类型别名长度、结构体字段长度、函数返回数组长度、
  全局数组长度、结构体字面量字段值）统一锁定，结果 29。
- 消费者位置探针结论：数组/切片/结构体字段/返回类型/全局数组长度与聚合字面量字段值
  均支持 CT 调用；`case` 值位置语法上不接受 `$`（语言限制），枚举判别值用 CT 调用
  仍不支持（调度重放未覆盖 `enum`，需求弱未立项）。
- 新发现两个缺陷并立项到 `docs/todo.md`：类型别名长度用 CT 调用与同文件函数返回同长度
  定长数组冲突（最小复现 8 行，边界已探明）；`sizeof` 对定长数组返回 `长度 × 4`（既存行为）。
- `make test` 246/246（run 120/120、fail 118/118、pass 8/8）；`make selfhost-native` 全绿。
  本轮未改编译器源码，种子保持
  `d212909322cf42fc582216c1db0607a4fde352697229f1c275e5c9581227b559`。

# 2026-10-07 编译期延迟数组类型的结构性兼容修复

- 修上一轮立项的缺陷：`type Pair = [$f()]int;`（长度来自编译期调用）与同文件同长度
  定长数组（返回类型、局部变量、形参）冲突，`return v;` 报「聚合类型不匹配」。
- 根因：长度表达式走 `ct_layout_array_expr` 建立延迟布局的独立数组类型项 A，pass1 里
  `let v [2]int` 只能建立规范项 B，别名布局完成后 pass2 的返回类型命中 A，
  两侧 type_id 不同但 `kind`/`size`/`align`/`elem`/`len`/`sub` 全同。
  定位手段：在 `sem_can_assign` 聚合分支临时分段比较各字段。
- 修复：`compiler/gen/symbols.yh` 的 `sem_can_assign` 聚合分支对 `TY_ARRAY` 增加
  按内容（元素类型 + 长度）的兼容判定；结构体/联合体保持名义类型严格比较。
  选择内容判定而非合并类型项，避免让 pass1 的类型项预知后续延迟布局结果。
- 新增 `tests/yh-run/run/143-comptime-alias-length-array.yh`（结果 18）；负例保持拒绝：
  长度不同、元素不同、同字段结构体互赋。
- `make test` 247/247（run 121/121、fail 118/118、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 247/247、模块 17/17、项目 84/84）。
  新种子 SHA-256：`8d7fbbe0ed542a15f88aa8367982d67e11b3a69d6177efe56a1b5b65aef9e1da`。
  详见[完成记录](01-finished/yh-编译期延迟数组类型结构兼容修复-2026-10-07.md)。

# 2026-10-07 编译期全局字符串指针常量与跨模块导出

- 全局字符串字面量指针常量现在可在编译期求值：`ct_ir.yh` 的 `SYM_CONST` + `F_ADDR`
  分支按常量保存的 `const_expr_off/len` 原样字节登记只读池并返回池地址；
  `CtPoolSpan` 增加来源键 `key`，`ct_pool_register` 按键复用池段（循环内反复引用
  同一常量不会耗尽 64 段上限）。
- 顶层/普通函数里的编译期调用实参：新增 `ct_pool_adopt_label`，在调用入口按
  `cval == value && F_ADDR && const_expr_kind == 2` 反查常量表，把仍是数据标签号的
  字符串指针实参换成池地址（改的是实参副本，不动调用方数组）。
- `pub const NAME *char = "..."` 可跨模块导出：`iface.yh` 原样重放声明，导入方解析时
  走与用户源码相同的登记路径；`comptimecross` 项目新增 `TEXT`/`base.letter`/
  `api.exported_letter` 覆盖整条链路。
- 新增 `tests/yh-run/run/144-comptime-global-string-const.yh`（结果 388）；
  `build-check.py` 的 `ct5b-pointer-constant-not-evaluable` 语义已变，改造为
  `ct5b-string-pointer-constant-evaluable`。
- 边界：只支持 `char`/`u8`/`i8` 元素（实际形态 `*char`）；直接写字的顶层实参
  `$f("abc")` 仍不支持（字面量实参不产生符号）；非字符串指针常量仍拒绝。
- `make test` 248/248（run 122/122、fail 118/118、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 248/248、模块 17/17、项目 84/84）。
  新种子 SHA-256：`35dbee3c1031c3c70eea9ea1b9f87d7f42ae0b3c82912b06840870105e89477e`。
  详见[完成记录](01-finished/yh-编译期全局字符串指针常量与跨模块导出-2026-10-07.md)。

# 2026-10-07 编译期调用实参里的直接字符串字面量

- 直接写在编译期调用实参里的字面量（`const A int = $f("A");`）此前无法使用：实参由前端
  直接求值成数据标签号，不经过 typed IR 捕获，也没有符号可反查。
- 修复：`gen/state.yh` 新增独立全局映射表 `c_data_str_lbl/off/len`（上限 128）与
  `data_str_add`/`data_str_lookup`，`sem_string` 求值时登记标签 → intern 原样字节；
  `ct_pool_adopt_label` 在符号反查失败后按标签号查表，命中即登记只读池并换成池地址。
- 映射表**不放 `GenState`**：`GenState` 已大到让后端单条 `add` 的字段偏移越界
  （`add x0, x0, #6528` 超出 12 位立即数范围，汇编失败），加 3 个数组立刻踩坑。
- 新增 `tests/yh-run/run/145-comptime-literal-arg-positions.yh`：顶层 const、全局变量
  初始化、普通函数体三处字面量实参（含多实参混合标量），结果 713。
- 边界：映射上限 128 项（超出静默降级）；跨模块的直接字面量实参仍拒绝（用导出常量）；
  非字符串指针常量仍拒绝。
- `make test` 249/249（run 123/123、fail 118/118、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 249/249、模块 17/17、项目 84/84）。
  新种子 SHA-256：`55013f50022512263e42b97f84595a6198bd5db0770acc8bdd59f6ddf28c54c2`。
  详见[完成记录](01-finished/yh-编译期直接字面量实参-2026-10-07.md)。

# 2026-10-07 编译期成员名字段修复与表达式/语句覆盖审计

- 修缺陷：结构体字段名使用被语言用作关键字的文本（如 `in`）时，编译期成员访问报
  「内部错误：编译期成员名 token 无效」。根因是编译期路径额外要求 `member.kind ==
  TOK_IDENT`，而字段匹配本来就按源文本进行；删掉类别校验后即可用。
- 覆盖审计：用探针过了一遍编译期表达式与语句种类，结论是当前**全部支持**
  （算术/位/比较/逻辑/一元/三元/成员/下标/取址与解引用写回/sizeof/转换/len/切片视图/
  浮点/字面量；if-else、区间 for-in、条件 for、continue/break、switch、for-in 双绑定、
  嵌套块、$if/$for、诊断语句）。仍在拒绝路径的是 goto/标签、正文内类型声明、
  `case` 值位置的 `$`（语法不接受）与枚举判别值用编译期调用。
- 撤销上一轮的误判立项：`sizeof(int) == 4`（`int` 即 4 字节），`[3]int`=12、
  `struct { [3]int; int }`=16 都是正确值。
- 新增 `tests/yh-run/run/146-comptime-expression-matrix.yh`（815，含关键字文本字段名）
  与 `run/147-comptime-statement-matrix.yh`（47）。
- `make test` 251/251（run 125/125、fail 118/118、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 251/251、模块 17/17、项目 84/84）。
  新种子 SHA-256：`1c2939f7080072cb46eca9aa7a9403fb0cef5e4ed94aa3d8f8a8443dc448e786`。
  详见[完成记录](01-finished/yh-编译期成员名与覆盖审计-2026-10-07.md)。

# 2026-10-07 深结构体字段偏移越界修复

- 修缺陷：`sem_expr.yh` 的成员访问无条件发 `add x0, x0, #off`，字段偏移超过 4095
  （AArch64 `add` 立即数 12 位无符号上限）时汇编失败；标量字段走 `ldr/str [xN, #imm]`
  所以只有聚合字段（数组/结构体/切片）的地址计算会踩到。
- 修法：偏移 > 4095 时借 `x12` 装载偏移再 `add x0, x0, x12`，与 `em_lea_local*` 的
  深帧约定一致。
- 新增 `tests/yh-run/run/148-deep-struct-field-offset.yh`（4096/4112/8192/8208 四种深度，
  结果 5678）；修复前汇编失败，修复后通过。
- 附带确认：编译器自身 `GenState` 的字段偏移已越过 4095 —— 往 `GenState` 追加 512 个
  `int` 后，用修复前的种子构建编译器会报 634 处 `add x0, x0, #47xx`；滚种子后用新种子
  重做同一实验构建成功，阻塞解除（探针字段已撤销）。
- `make test` 252/252（run 126/126、fail 118/118、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 252/252、模块 17/17、项目 84/84）。
  新种子 SHA-256：`498543a7e5b9483e0ca6877accf54854926fdc6b91b72a3856fc07e42c164cf1`。
  详见[完成记录](01-finished/yh-深结构体字段偏移越界修复-2026-10-07.md)。

# 2026-10-07 跨模块编译期调用直接字面量实参的静默错值修复

- 缺陷：`$math.head_of("Z")` 不报错但返回 104（'h'）—— 跨模块调用的实参在提供方
  编译单元求值，拿到那边的数据标签号，编译期侧按标签号在本地只读池映射里反查时
  命中本地无关字面量。上一轮为直接字面量实参加的标签反查没有区分标签号来源编译单元。
- 修复（保守）：`parse_expr.yh` 在解析编译期调用实参时，若调用是模块限定形式、
  实参是字符串字面量、对应形参是单字节指针，直接报
  「跨模块编译期调用不支持直接字符串字面量实参，请改用模块导出的 pub const 指针常量」。
- `comptimecross` 新增 `math/api.yh` 的 `pub fn head_of(text *char) int`；
  `build-check.py` 新增 `ct5b-crossmodule-literal-arg-rejected`（注入字面量实参后必须
  构建失败并带该诊断）。
- 遗留：支持该写法需把字面量字节来源跨编译单元传递，已记入 `docs/todo.md` CT5B。
- `make test` 252/252（run 126/126、fail 118/118、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 252/252、模块 17/17、项目 84/84）。
  新种子 SHA-256：`c0e13a4bf63d147a1d7f9a4f26acaf9029fada0909f4615b92b832a5c7fc2791`。
  详见[完成记录](01-finished/yh-跨模块字面量实参静默错值修复-2026-10-07.md)。

# 2026-10-07 跨模块编译期单字节指针形参的错值修复

- 上一条修复只按「字面量实参」拒绝，本轮实测发现同一根因还影响非字面量写法：
  `const MINE *char = "AB"; $math.head_of(MINE)` 同样返回 104105（`"hi"` 的字节）。
  实测三种写法（`head_of("Z")`→104、`head_of("AB")`→104105、`head_of(MINE)`→104105）
  都读到同一段无关字节；同项目 `*int` 形参的跨模块写回正常，因为整数指针不走字节池。
- 修法：拒绝范围按**形参类型**判定 —— 编译期调用为模块限定形式且形参是单字节指针
  （`char`/`u8`/`i8`）时直接报「跨模块编译期调用不支持单字节指针形参（char/u8/i8）：
  实参的字符串来源无法跨编译单元解析，请改用模块导出的 pub const 指针常量」。
- `build-check.py` 拆成 `ct5b-crossmodule-literal-arg-rejected` 与
  `ct5b-crossmodule-pointer-arg-rejected` 两个检查，两种写法都要求被拒绝。
- 遗留：支持该写法需让实参字节来源随调用跨编译单元传递，已记入 `docs/todo.md` CT5B。
- `make test` 252/252（run 126/126、fail 118/118、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 252/252、模块 17/17、项目 84/84）。
  新种子 SHA-256：`7943d6f4418278254cb27c2884dacdacc5cf763e609aadf5fa462f427ffe81f4`。
  详见[完成记录](01-finished/yh-跨模块单字节指针形参错值修复-2026-10-07.md)。

# 2026-10-07 跨模块编译期调用直接字面量实参支持

- 排查结论：临时把本地字面量编号后移（host 顶部加 `const PAD *char = "PAD";`）后
  `head_of("AB")` 从 104 变成 65，证明实参值是**提供方编译单元分配的标签号**，
  被调用方 worker 用自己的编号解释 → 按标签号反查本地表这条路不可靠。
  但直接写在实参位置的字符串字面量不受影响：字节就在调用方源码里，可就地登记只读池。
- 实现：`parse_expr.yh` 在解析实参前记下是否为字符串字面量，解析后按形参类型处理 ——
  字面量就地登记池并覆盖实参值为池地址；非字面量的跨模块调用保持拒绝；同模块调用放行
  （继续走 `ct_pool_adopt_label`）。新增 `ct_pool_register_src` 标量参数包装。
- 实现细节：覆盖放在 `parse_expr_iso` 之后、不改控制流；早先用 `continue` 跳过解析的写法
  会让编译器报出「模块没有导出该名字」这种与代码无关的诊断（行号落在 `gen.TOK_COMMA`）。
- 验证：`comptimecross` host 新增 `const HEAD int = $math.head_of("AB");` + `HEAD - 65` 断言；
  `build-check.py` 保留 `ct5b-crossmodule-pointer-arg-rejected`（非字面量跨模块实参必须被拒）。
- `make test` 252/252（run 126/126、fail 118/118、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 252/252、模块 17/17、项目 84/84）。
  新种子 SHA-256：`2adc5b5d79ffd6a58241304d3b99a269e14b5cefee2aeaa1c4dd283b89e90d2b`。
  详见[完成记录](01-finished/yh-跨模块字面量实参支持-2026-10-07.md)。

# 2026-10-07 编译期顶层聚合实参诊断与聚合能力探针

- 探针结论：编译期聚合值/左值常见形态**全部支持** —— 结构体与定长数组按值复制后改写
  保持隔离、结构体数组字段的切片视图别名写回、`for-in` 遍历结构体数组字段与切片字段。
  前几轮记的「CT3 剩余：其他聚合值与一般左值」在常见形态上已无缺口。
- 探针发现的缺口：顶层/普通函数里的编译期调用不能写聚合字面量实参
  （`$take(Point{ x: 1 })`），因为顶层实参必须在 pass1 折叠成常量。
- 改动：`parse_expr.yh` 对「聚合形参 + 聚合字面量实参 + 非编译期函数正文」给出可读诊断
  「编译期调用实参里的聚合值需要在编译期函数体内构造（顶层实参必须是编译期常量）」，
  替代原先的「结构体字面量不是编译期常量」。
- 新增 `tests/yh-run/fail/148-comptime-top-aggregate-arg.yh`。
- `make test` 253/253（run 126/126、fail 119/119、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 253/253、模块 17/17、项目 84/84）。
  新种子 SHA-256：`ee3c396a1d204811eeb5dc305075356f92a8c2d0c0df7e7de430ebb5a1f834a4`。
  详见[完成记录](01-finished/yh-编译期顶层聚合实参诊断与聚合探针-2026-10-07.md)。

# 2026-10-07 枚举判别值里编译期调用的可读诊断

- 缺陷（诊断质量）：`pub enum Palette { red = $two() + 1; green; }` 报
  「编译期函数正文不在受支持的 typed IR 子集内」，但 `two` 的正文完全在子集内 ——
  真实原因是求值时机（判别值在 pass1 折叠，typed 正文要 pass2 才捕获），
  该措辞会让用户去检查函数体，方向完全错。
- 改动：`parse_decl.yh` 的枚举成员判别值解析在求值前扫描判别值 token 区间
  （到 `;` 或 `}` 为止），出现 `$` 即报
  「枚举判别值里的编译期调用暂不支持（需要延迟到正文捕获之后求值），请改用纯常量表达式」。
- 新增 `tests/yh-run/fail/149-comptime-enum-discriminant.yh`。
- 边界确认：隐式递增枚举在编译期函数体内引用成员正常（run/93：green:7、blue:8）；
  顶层 `const V int = Palette.green.to_type(int);` 报「引用了未声明的名字」，
  是另一个缺口（已立项）。
- `make test` 254/254（run 126/126、fail 120/120、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 254/254、模块 17/17、项目 84/84）。
  新种子 SHA-256：`62c2eb2857e1fbbac6d89b05c3dd7a050c10fe3835ca5bbbaa3efdf605878aea`。
  详见[完成记录](01-finished/yh-枚举判别值编译期调用诊断-2026-10-07.md)。

# 2026-10-07 枚举成员限定引用 EnumName.member

- 缺口：枚举成员只能裸名引用；`Palette.green` 在顶层、普通函数体、编译期函数体内
  都报「引用了未声明的名字」，因为 `Palette` 是类型名、符号表里没有对应值符号。
- 实现：`parse_expr.yh` 的标识符解析在模块限定名分支之前加枚举成员分支 —— 基名不是
  任何符号时用 `ty_lookup_name` 查类型，命中 `TY_ENUM` 再查成员符号，要求
  `F_ENUM_MEMBER` + `const_ready` + `type_id` 等于该枚举，命中即消费三个 token 走
  `sem_ident_val`，与裸名引用同路径。
- 新增 `tests/yh-run/run/149-enum-member-qualified.yh`：顶层、普通函数体、编译期函数体
  三处限定引用，结果 22。
- `make test` 255/255（run 127/127、fail 120/120、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 255/255、模块 17/17、项目 84/84）。
  新种子 SHA-256：`584b8b406b5cbb9b2f3f373a22fb7c96821e78cf13fb13d4e405581175b851a8`。
  详见[完成记录](01-finished/yh-枚举成员限定引用-2026-10-07.md)。

# 2026-10-07 枚举判别值里的编译期调用（延迟求值）

- 实现：枚举判别值含 `$` 时 pass1 不解析表达式，只登记 token 区间（该成员及其后所有成员
  含隐式都待回填）；`parse_ct_layout.yh` 新增延迟表（上限 64，独立全局数组），
  `ct_enum_pending_run` 在 `ct_layout_resolve()` 之后、pass2a 之前按序回填 —— 显式成员
  重解析表达式（正文此时已捕获），隐式成员取前一成员 `cval + 1`。
- 配套：`parse_expr.yh` 的枚举成员限定引用不再要求 `const_ready != 0`，未就绪交给
  `sem_ident_val` 报「编译期常量尚未就绪」。
- 新增 `tests/yh-run/run/150-comptime-deferred-enum.yh`（a=3 b=4 c=20 d=21 v=21）；
  原 fail/149 语义已变（现在成功）按既有做法删除。
- 边界：模块模式里编译期正文引用延迟枚举成员仍不可用（模块模式标识符解析走另一条路径，
  `Level.mid` 落到字段访问）；已记入 todo。
- `make test` 255/255（run 128/128、fail 119/119、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 255/255、模块 17/17、项目 84/84）。
  新种子 SHA-256：`545378b49a159c8b7415a8816c3d833bff5d42ede50da9569db9143b58c651bd`。
  详见[完成记录](01-finished/yh-枚举判别值延迟求值-2026-10-07.md)。

# 2026-10-07 模块模式枚举成员引用的边界定位与锁定

- 上一轮记的模块模式边界过宽，本轮测准：模块模式下**顶层常量**引用延迟判别值的枚举成员
  是可用的（`pub const MID int = Level.mid;` 得到 `low=4`→`mid=5`），编译期函数读该常量、
  跨模块转发也都正常；真正不可用的只有「编译期函数**正文里直接**引用枚举成员」
  （报「『.』的左侧不是结构体或结构体指针」，准备期的表达式解析没走到新增的枚举成员分支）。
- 本轮只改测试与文档：`comptimecross` 新增 `Level`（判别值来自编译期调用）、
  `MID = Level.mid`、`mid_ct`、api 的 `level_mid` 转发与 host 的 `+ MID - 5` 断言。
- `make test` 255/255（run 128/128、fail 119/119、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 255/255、模块 17/17、项目 84/84）。
- 未改 `compiler/` 源码，种子未滚动。详见[完成记录](01-finished/yh-模块模式枚举成员边界定位-2026-10-07.md)。

# 2026-10-07 模块模式枚举成员限定引用：失败路径定位（排除假说）

- 尝试修「模块模式编译期正文直接引用枚举成员」，两条放宽假设都被实验否定，**不做改动、已回退**：
  1) 在标识符入口加阶段化诊断，准备期打印结果只有一次 `DBG enum-qual: MATCH`（`Level`），
     但同一次编译仍在 `.mid` 处报「『.』的左侧不是结构体或结构体指针」→ 该写法还被**另一条**
     解析路径处理，且不经过 `parse_expr` 的标识符入口分支；
  2) 依次去掉 `sym_lookup(...) < 0` 与类型可见性要求，结果**都不变** → 问题不在分支条件。
- 两条放宽都无收益却各带一点误判风险，按「只动该动的」全部回退，`parse_expr.yh` 恢复第 22 轮状态。
- 推荐写法（模块模式下可用，`comptimecross` 已锁定）：顶层常量中转 ——
  `pub const MID int = Level.mid;` + 编译期函数读 `MID`。
- 回退后 `make test` 255/255（run 128/128、fail 119/119、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 255/255、模块 17/17、项目 84/84）。未改 `compiler/` 源码，种子未滚动。
  详见[完成记录](01-finished/yh-模块模式枚举成员失败路径定位-2026-10-07.md)。

# 2026-10-07 模块模式枚举成员：根因定位到「成员符号在第二次解析不可见」

- 三次插桩夹逼：① `sem_member` 失败分支分档 → `prepare + base TY_ENUM`（枚举类型名走了
  **值路径**，基底求值成功再落到字段访问）；② `parse_ident_primary` 基名符号分档 → 同一行
  `Level.mid` 在一次编译里被解析**两次**：第一次 `base has no symbol`（枚举成员分支命中），
  第二次 `base symbol is CONST`（被 `sym_lookup(...) < 0` 挡住 → 值路径）；
  ③ 加「`SYM_CONST` 且 `type_id` 是 `TY_ENUM`」第二形态判据仍失败（该常量符号的 type_id
  不是枚举），改在 `sem_member` 兜底 → `DBG enum-base: member symbol not found`：
  **第二次解析时枚举成员符号在名字表里查不到**。
- 根因：模块 worker 第二次解析 CT 正文时枚举成员符号不可见；`parse_expr` 分支（那时基名已有
  符号）与 `sem_member` 兜底（成员符号查不到）都救不了。真正支持需让第二次解析带上枚举成员
  符号，或让枚举类型项自带成员表（`ty_push(TY_ENUM, ...)` 当前不存成员）。
- 本轮交付：`sem_member` 新增枚举基底分支，给出准确可操作诊断（模块模式提示用顶层常量中转，
  替代误导性的「『.』的左侧不是结构体或结构体指针」）；新增 `fail/149-enum-value-member-access.yh`
  锁定该分支；`parse_expr.yh` 保持第 22 轮单形态（第二形态判据无收益，不留）。
- `make test` 256/256（run 128/128、fail 120/120、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 256/256、模块 17/17、项目 84/84）。
  新种子 SHA-256：`1393ec390f8becd4b3573ada8a0096699f5d4790166a6d5df94c38dc4f8b981d`。
  详见[完成记录](01-finished/yh-模块模式枚举成员根因定位-2026-10-07.md)。

# 2026-10-07 枚举成员表尝试（回退）与 data_str 返回值约定修复

- 尝试方向 ②「枚举自带成员表」实现模块模式编译期正文引用枚举成员：新增独立全局登记表
  （快照名字池偏移与值，不依赖符号表），逐步排除了「类型 id 反查」「符号下标」「登记早于
  const_ready」三个问题 —— 成员能命中，但**期间误删的 `data_str_*` 先报错**，且其重写版
  返回值约定写反，故整体回退 `em_*`（四个文件还原到第 26 轮状态）。
- 回归与修复：文本切片删 `em_*` 时误删 `state.yh` 的 `c_data_str_lbl/off/len` 与
  `data_str_add`/`data_str_lookup`；重写时把「命中返回非零」写成「命中返回 0」，而消费侧
  `ct_ir.yh` 用 `if (data_str_lookup(...) != 0)` 判命中 → 未命中分支照样进入、`off/slen` 全 0
  →「编译期字符串字面量为空」（`comptimecross` 的 `$math.head_of("AB")` 编译失败，门红 82/84）。
  改为命中返回 1、未命中返回 0 后门恢复 84/84。
- 教训写入 todo：删代码先确认切片边界覆盖范围；重写被误删函数前先读消费侧调用约定。
- `make test` 256/256（run 128/128、fail 120/120、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 256/256、模块 17/17、项目 84/84）。
  种子因重写 `data_str_*` 而变化（行为等价，双门+固定点全绿）：`4002ff202018232db3e1bddccddc92963646b113d70bc2489f87963b29570bb7`。
  详见[完成记录](01-finished/yh-枚举成员表尝试与data_str约定修复-2026-10-07.md)。

# 2026-10-07 枚举成员表重做（解析期已通，执行器侧待补）

- 按第 27 轮总结的两个坑重做成员表：`state.yh` 独立全局表在登记时**快照名字池偏移与值**
  （避开「符号下标在二次解析后失效」）；`parse_decl.yh` 的 `em_add` 放在 `cval`/`const_ready`
  赋值**之后**（避开「快照到 ready = 0」）；`parse_ct_layout.yh` 延迟回填同步表内快照；
  `sem_expr.yh` 的 `sem_member` 在 `sym_lookup` 失败后按名字反查登记表。
- 实测：插桩确认兜底**命中**（`DBG em: hit` 两次），但编译仍失败 —— 报错来自另一条路径
  `comptime/ct_ir_place.yh:819` 的 `ct_ir_member_place`（「编译期成员访问只支持本地结构体或
  联合体值」）：同一正文的第二次解析把 `EnumName.member` 当成员访问表达式送进执行器。
- 因此本轮**无用户可见行为变化**（模块模式仍报第 26 轮的可操作诊断），也**没有新增用例**
  （无行为变化即无可锁定场景）；门全绿无回归。
- 下一步（已写 todo，勿重复走）：在 `ct_ir_member_place` 加枚举基底分支，用已有的
  `member_rel` 取成员名 token + `gen.em_find`/`em_get_ready`/`em_get_val` 取值。
- `make test` 256/256（run 128/128、fail 120/120、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 256/256、模块 17/17、项目 84/84）。
  新种子 SHA-256：`34a6832e96662cb43bba35367fb524c732eb8da795e549da9015edce1d771379`。详见[完成记录](01-finished/yh-枚举成员表重做-2026-10-07.md)。

# 2026-10-07 模块模式编译期正文直接引用枚举成员（打通）

- 承接第 26 轮根因（同一段编译期正文被解析两次，第二次 `EnumName` 已求值成常量符号、
  成员符号又查不到 → 被当成员访问表达式送进执行器，在 `ct_ir_member_place` 报「编译期成员
  访问只支持本地结构体或联合体值」）、第 27 轮回退、第 28 轮重做，本轮补上执行器侧：
  `comptime/ct_ir_place.yh` 的 `ct_ir_member_read` 在结构体路径之前先判基底类型，`TY_ENUM`
  时用该表达式已有的成员名 token 位置（`expr.after - frame.target.body_token_first - 1`）
  经新增的 `gen.em_find_src(frame.target.src, ...)` 查枚举成员表，命中且就绪即返回成员常量值。
- `gen/state.yh` 把成员名比较泛化为可接受任意源码缓冲（编译期目标另有一份 `frame.target.src`，
  与前端 `c_src` 不一定是同一个缓冲），`em_find` 成为它的薄封装。
- 改动规模：1 个新函数 + 1 个分支；不动前端解析路径，也不影响结构体字段访问（只有基底本来
  就是 `TY_ENUM` 这条此前必然报错的路径才走新分支）。
- 用例：`tests/modules/projects/comptimecross` 新增 `pub enum Simple { one = 1; two; }`、
  `simple_ct()`（普通成员）、`low_ct()`（延迟判别值成员）与 api 侧转发、host 侧断言
  （`PS = 2`、`PL = 4`）。**反向验证**：把期望改成 `PS - 99` 后报
  `FAIL ct5b-cross-module-body ... run=159`、83/84；还原后 84/84 —— 证明断言确实覆盖这两条路径。
- 效果：模块模式下枚举成员三种写法全通（顶层常量中转、跨模块转发、编译期正文**直接**引用）；
  单文件模式无变化。
- `make test` 256/256（run 128/128、fail 120/120、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 256/256、模块 17/17、项目 84/84）。
  新种子 SHA-256：`bbc5456053566db8fcb84ee41bd9dd8ff5ed5a2da70047cc584cf195e4e70e84`。详见[完成记录](01-finished/yh-模块模式编译期正文枚举成员-2026-10-07.md)。

# 2026-10-07 编译期顶层聚合实参诊断与 CT1/CT2 收尾定位

- 顶层聚合实参：旧诊断给的是走不通的出路（「顶层实参必须是编译期常量」），而实测
  `const P Point = Point{ x: 1 };` 直接报「const 不支持聚合类型」，即没有任何中转写法。
  本轮把 `parse_expr.yh` 的拒绝诊断改成可操作表述（写明缺少捕获通道、无法在 pass1 折叠、
  `const` 也不支持聚合类型），并同步 `fail/148` 的 `fail:`/`fail-contains:` 注释。
- CT1/CT2 收尾定位：实测两条入口结构 —— 单文件 `compile.yh` 27–42 捕获正文、45 登记延迟区间、
  **47–71 固定点循环**、72 `ct_layout_resolve`、76 `ct_enum_pending_run`；模块
  `module_worker.yh` 15/55/157/159 同构。**「逐轮重解析」= 47–71 的固定点循环**（每轮重解析
  `ct_layout_*` 登记的全部表达式），第 26 轮那个「同一段正文被解析两次」就是它的副作用。
- 产出[收尾方案](02-plan/yh-编译期收尾方案.md)：拆成互相独立的「去重解析」与「统一入口」两件，
  第一步定为**先插桩量化白跑占比**再改循环，验收看语料与两代自编产物逐字节不变；并记录
  `gen/state.yh:150` 的 `c_arg_agg` 是预留字段（无使用点），不能当现成通道。
- `docs/todo.md` 两条相关条目已按上述结论改写。
- `make test` 256/256（run 128/128、fail 120/120、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 256/256、模块 17/17、项目 84/84）。
  新种子 SHA-256：`9140521337d9c5348698da561447e49c8a6369fec9fc819af3037729ef2affd5`。详见[完成记录](01-finished/yh-编译期顶层聚合实参诊断与收尾定位-2026-10-07.md)。

# 2026-10-07 编译期收尾方案实测修正（撤销「去重解析」、修正「统一入口」）

- **实测撤销方案①**：`parse_source_ct_layout_exprs()`（`parse_ct_layout.yh:337`）第 345–349 行
  **已经**跳过已就绪项，可运行项一次即成功并置回非 pending，所以固定点循环里**每个请求最多被
  真正解析一次**，不存在「白跑的重解析」；剩余的 O(轮数 × 请求数) 只是计数扫描，且 `pending == 0`
  时函数开头直接返回。结论：不值得改，方案与 todo 均已标注撤销（避免后续做无用功）。
- **修正方案②**：`parse_source_ct_fns()` 三个调用点不是同一段代码的复制 —— `compile.yh:37`
  是单文件完整流程（捕获 → 布局登记 → 固定点 → `ct_layout_resolve` → `ct_enum_pending_run`）、
  `module_build.yh:943` 是构建侧捕获、`iface_ct.yh:1023` 是**加载 `.s.ct` 接口**（多出
  `c_iface_load` 隐藏常量折叠、数据段抑制与公开 CT 符号签名校验）。「统一入口」因此先要做**调用图
  普查**（check-only / build / SSA 各缺哪一步），不能直接抽共用函数。
- **顶层聚合实参可行性**：编译期函数体内的实参走 typed IR（`ct_ir_args_fill`）在执行器 arena 里
  构造聚合；顶层/普通函数里的实参由前端直接求值成 `args [64]gen.Res`，而 `Res` 没有聚合值表示 ——
  所以真修要先给常量聚合值找一处表示（首选独立聚合常量池，避免动 `gen.Res` 布局），约 2–3 轮。
  这也解释了 `gen/state.yh:150` 的 `c_arg_agg` 为何一直没有使用点。
- 本轮**无源码改动**，故未滚种子（`bin/yh.sha256` 不变）；`git diff --check` 干净，
  `find compiler -name "*.yh" -newer bin/yh` 为空。
  详见[收尾方案](02-plan/yh-编译期收尾方案.md)与[上轮完成记录](01-finished/yh-编译期顶层聚合实参诊断与收尾定位-2026-10-07.md)。

# 2026-10-07 顶层 const 结构体聚合常量（CT3 最小切片）

- `const P Point = Point{ x: 1 };` 此前报「const 不支持聚合类型」（`fail/148` 的上游障碍）。
  实测两条替代路都不通：`const` 报该错、全局 `let` 变量报「变量不是编译期常量」。
- 改动两处（约 15 行）：① `parse_global_init.yh` 的 `TY_STRUCT` 分支只在**模块模式**保留拒绝
  （接口导出未覆盖聚合常量），单文件走与全局变量同一条 `parse_global_struct_init` 发射路径，
  并在发射后标记符号已就绪；② `sem_value.yh` 的 `sem_ident_val` 把**类型是聚合**的 `SYM_CONST`
  降级为变量语义（这类常量没有可用标量 `cval`，必须按符号地址访问 —— 不加这步运行期段错误，
  会把 `cval = 0` 当地址用）。
- 用例 `tests/yh-run/run/151-const-aggregate-global.yh`（`// exit: 0`）：标量字段 const、
  嵌套结构体字段 const、全局 `let` 变量对照，三者字段求和减 23 得 0。
- 边界：模块模式仍拒绝；数组/切片 `const` 仍拒绝（本轮只放宽结构体）；`const` 聚合的只读性
  未强制（可写入不报错），是本轮接受的简化。
- `make test` 257/257（run 129/129、fail 120/120、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 257/257、模块 17/17、项目 84/84）。
  新种子 SHA-256：`4db4301fe8426591f2becafc7016fa86ab191066f520f6e59b44e74368574f06`。详见[完成记录](01-finished/yh-顶层const结构体聚合常量-2026-10-07.md)。

# 2026-10-07 顶层 const 数组/切片聚合常量

- 承接上一轮的结构体切片：`parse_global_init.yh` 的 `TY_ARRAY || TY_SLICE` 分支把 `const` 拒绝
  **只在模块模式保留**，单文件走与全局变量同一条 `parse_global_array_init` 发射路径并在发射后
  标记符号已就绪；`sem_value.yh` 的降级判据上一轮已覆盖 `TY_ARRAY`/`TY_SLICE`，无需再改。
- 用例 `tests/yh-run/run/152-const-array-global.yh`（`// exit: 0`）：`const TABLE [4]int` 循环索引
  读取 + 全局 `let NUMS` 对照，求和减 106 得 0。
- 顺带实测到**既有前端限制**（非本轮引入）：嵌套数组字面量 `[[1,2],[3,4]]` 对 const 与变量都报
  「数组/切片字面量需要目标类型上下文（let 初始化或同型赋值）」，已记入 todo。
- 已知缺口：`const` 聚合的只读性仍未强制（降级为变量语义后写入路径不再拦截），已记 todo。
- `make test` 258/258（run 130/130、fail 120/120、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 258/258、模块 17/17、项目 84/84）。
  新种子 SHA-256：`9e2f92d6d2d5c04bec5e4ed90dd689f5b2f98e595afae02c85af19ada71dc232`。详见[完成记录](01-finished/yh-顶层const数组聚合常量-2026-10-07.md)。

# 2026-10-07 const 聚合常量只读性（补第 32/33 轮缺口）

- 实测确认缺口：第 32 轮把聚合 `SYM_CONST` 在取值路径降级为变量语义后，写入路径不再拦截，
  `P0.x = 6;`（`const P0 P = P{ x: 5 };`）**编译通过且真的改了值**（返回 0）；对照的标量 const
  本来就被拦（`C = 6;` 报「赋值目标必须是可寻址的表达式」），两种 const 的只读语义不一致。
- 改动一处 5 行：`gen/sem_value.yh` 的 `sem_ident_val` 在聚合 `SYM_CONST` 降级分支前加
  `if (g_state.c_lvalue != 0) { return sem_err("不能给 const 聚合常量赋值或取地址"); }`
  —— 降级只为按符号地址读取，不放开可写性；取地址同样被拒。
- 用例 `tests/yh-run/fail/150-const-aggregate-write.yh`（`fail-contains: 不能给 const 聚合常量赋值或取地址`）。
- 回归：标量 const 诊断不变；`run/151`、`run/152` 读取路径均 `rc=0`。
- `make test` 259/259（run 130/130、fail 121/121、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 259/259、模块 17/17、项目 84/84）。
  新种子 SHA-256：`6c3c34fe7e9d5cd200559d8619f2b27ea1cfab090534edce54a076f4747be1d5`。详见[完成记录](01-finished/yh-const聚合常量只读性-2026-10-07.md)。

# 2026-10-07 顶层编译期调用的聚合实参（CT3 主体）

- 关键观察：执行器本来就把**聚合实参的 `CtValue.value` 当对象指针**用，`ct_call` 也无条件把
  `args[i].ival` 写进 `values[i].value` —— 所以只要前端能给出一个「字段值区」对象指针并写进
  `Res.ival`（`is_const = 1`），聚合与标量就走同一条赋值，**`ct_call` 一行都不用改**。
- 改动：① `comptime/ct_ir.yh` 新增顶层聚合实参**临时构造区**（独立全局 `CtFrame` +
  `ct_arg_pool_reset` + `ct_arg_pool_struct`，参数用扁平标量数组 —— 第一版传 `CtValue` 数组时
  报「模块没有导出该类型」，因为调用方在 parse 侧拿不到 comptime 私有类型；区只增不减，
  借用对象可能被结果池 keep，主动释放有悬空风险，总量由 100000 元素上限兜住）；
  ② `parse/parse_expr.yh` 新增 `p_ct_arg_struct_literal` 折叠字面量（字段按声明顺序填位、
  可乱序、逐字段 `sem_can_assign`、`c_fold += 1` 折叠），并让实参循环在折叠成功后**跳过**
  `parse_expr_iso`（不跳过会报「此处需要一个表达式」）；剩余形态保留拒绝但诊断改为可操作表述。
- 用例：新增 `run/153-comptime-top-aggregate-arg.yh`（基本 34、字段乱序 25、标量与聚合混排 19、
  字段值常量表达式 54）；`fail/148` 改成仍不支持的数组实参形态并同步 `fail-contains`。
- 边界：数组/切片/联合体实参与嵌套聚合字段仍拒绝；**模块模式未验证**（本轮只在单文件模式实测）。
- `make test` 260/260（run 131/131、fail 121/121、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 260/260、模块 17/17、项目 84/84）。
  新种子 SHA-256：`3df40c9b588bf7c80a2ee9709bce239234bc5e5894819429b09ab7c02b6fd3a3`。详见[完成记录](01-finished/yh-顶层聚合实参-2026-10-07.md)。

# 2026-10-07 顶层聚合实参：嵌套结构体字段 + 模块模式验证

- **嵌套结构体字段**：把 `p_ct_arg_struct_literal` 里「聚合字段直接返回 1」的分支改成**递归**
  （`Box{ lo: Point{...} }`），没有新增任何 comptime 接口 —— `ct_arg_pool_struct` 造出的对象指针
  本身就能当聚合字段的值，与执行器对聚合字段的表示一致。用例 `run/154`（嵌套 + 字段乱序 = 23；
  标量与嵌套聚合混排 = 121）。
- **模块模式验证**（补第 35 轮未验证项）：在既有 84 用例项目 `comptimecross` 里加自包含验收 ——
  `extra.yh` 的 `pub struct Pair` + `weigh` + `pub const TOP int = $weigh(Pair{ x: 3, y: 4 });`
  + `top_ct()`，`api.yh` 的 `probe_top()` 转发，`host` 顶层 `const PT int = $math.probe_top();`
  并断言 `PT - 34`。结果**模块模式可用**，项目门 84/84。踩坑：`struct` 必须写 `pub struct`。
- **删死代码**：第 35 轮加的 `ct_arg_pool_reset()` 没有任何调用点（全局结构体落 BSS，
  静态零初始化即够，每次编译是一个进程），本轮删除。
- `make test` 261/261（run 132/132、fail 121/121、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 261/261、模块 17/17、项目 84/84）。
  新种子 SHA-256：`a3eddad0f1992eb6406defb0bc2dba6e9e67d4ed8f3cd6489e5866396eb593d2`。详见[完成记录](01-finished/yh-顶层聚合实参嵌套与模块验证-2026-10-07.md)。

# 2026-10-07 顶层聚合实参：数组与嵌套数组

- **泛化而非新增**：数组与结构体在 `ct_ir_aggregate_new` 里只差一个参数（结构体传自身类型、
  数组传元素类型），所以把 `ct_arg_pool_struct` 改名为 `ct_arg_pool_agg(elem_type, ...)`，
  没有加第二个同形函数。
- **新增 `p_ct_arg_array_literal`**（`parse/parse_expr.yh`，约 45 行）：标量元素 `c_fold` 折常量 +
  `sem_can_assign`；数组元素递归（顺带让**嵌套数组** `[[1,2],[3,4]]` 可用 —— 折叠路径自己解析，
  绕开了前端「嵌套数组字面量需要目标类型上下文」的既有判定）；结构体元素递归；
  切片/联合体元素返回 1。接线两处：结构体的 `TY_ARRAY` 字段、顶层实参的 `pk == TY_ARRAY`。
- **诊断措辞更新**：原措辞说数组与嵌套聚合仍需在函数体内构造，现已支持；改为
  「暂时只支持结构体与数组字面量（字段/元素可递归嵌套标量、结构体、数组）；切片与联合体仍需…」。
  `fail/148` 从数组实参改为**切片实参**并同步 `fail-contains`。
- 用例 `run/155`（数组实参 60、结构体数组字段 10、嵌套数组 4）。
- `make test` 262/262（run 133/133、fail 121/121、pass 8/8）；`make selfhost-native` 全绿
  （自解析 70 文件、语料 262/262、模块 17/17、项目 84/84）。
  新种子 SHA-256：`58387b3faa99ee3b34eea81fb139a62d8be93a1effaa584142a878db64cd3d4c`。详见[完成记录](01-finished/yh-顶层聚合实参数组-2026-10-07.md)。

# 2026-10-07 编译期收尾：调用图普查结论（撤销「统一入口」）+ 三条边界实测

本轮无源码改动（`find compiler -name "*.yh" -newer bin/yh` 为空），故未滚种子、未重跑门。

- **「统一入口」撤销**：普查确认编译期步骤在单文件与模块两条路径上**已经对齐**，没有功能缺口 ——
  `c_check_only` 只抑制后端缓冲、不跳过任何编译期步骤；`module_worker.yh:121-168` 的顺序
  （布局登记 → 固定点循环 → `ct_layout_resolve` → `ct_enum_pending_run` → pass1）与单文件同构；
  模块侧 `parse_source_ct_layout_consts()` 在 `module_build.yh:947`；`iface_ct.yh:1023` 是读 `.s.ct`
  接口的另一条路，本就不该合并。剩下的只有代码重复 ⇒ 纯重构、无功能收益 ⇒ 撤销。
  至此 **CT1/CT2 两个子项（去重解析、统一入口）都已撤销**，条目关闭。
- **联合体实参不适用**：`union` 不是 yh 关键字（`pub union Val { ... }` 报「此处需要一个类型」），
  源码无法构造联合体字面量 —— 从 todo 里去掉，而不是留着。
- **切片实参的难点定位**：`ct_registry.yh:472` 要求切片实参是「有效的本地数组或切片视图」
  （地址须落在存活调用帧槽区间内），且切片是「地址 + 长度」、`CtValue` 单 i64 装不下
  ⇒ 需要先设计顶层切片的视图表示。
- **`*dst = *src;` 缺陷表现变化**：不再段错误，改为**静默算错**（最小复现得 230，应为 0），
  编译链接均成功；todo 条目描述已按实测更新，并注明编译期路径走不到（`@[comptime]` 不支持结构体
  指针形参）。
- 文档：更新 `docs/todo.md`（关闭 CT1/CT2、修正两条过时描述）、
  [收尾方案](02-plan/yh-编译期收尾方案.md)（补普查结论表与三条边界实测）。

# 2026-10-07 跨模块非字面量指针实参：根因链定位与诊断修正

- **根因链实测**：① 单文件 `$first(TEXT)`（`*char` 形参 + 指针常量实参）本来就 `rc=0`，
  问题只在 `qualified != 0` 的跨模块分支；② `.s.ct` 确实用**源字面式**重放 `*char` 常量
  （`iface_ct.yh:722-730`），导入侧重新解析后有**本地**标签号，所以拒绝条件看着过度保守 ——
  按 `SYM_CONST + F_ADDR + is_const` 放宽后，却**构造不出用例**：`math.TEXT` 报「模块没有导出
  该名字」，改用 `pub const TEXT_PTR *char = base.TEXT;` 转发报 **「pub 指针常量（字符串）暂不支持
  跨模块导出」**（`iface.yh:339`）。③ 即提供方根本导不出字符串指针常量，`.s.ct` 重放又只覆盖
  「可达 CT 正文引用的常量」，实参位置不触发 ⇒ 整条路要先扩展闭包收集范围。**放宽已回退**。
- **本轮交付诊断修正**：原诊断让用户「改用模块导出的 pub const 指针常量」——实测该写法本身不被支持，
  属误导。新诊断指出「非字面量的跨模块指针实参需要让字节来源随调用跨编译单元传递，尚未支持
  （`pub const *char` 常量本身也不能跨模块导出…）」，`build-check.py:337` 的期望字符串同步更新。
- `make test` 262/262；`make selfhost-native` 全绿（自解析 70 文件、语料 262/262、模块 17/17、
  项目 84/84）。新种子 SHA-256：`6ddea04f8c46524654431ba598c3109f0c36bc52e83b014e0baaf44843ea8012`。
  详见[完成记录](01-finished/yh-跨模块非字面量指针实参根因与诊断修正-2026-10-07.md)。

# 2026-10-07 跨模块编译期调用的单字节指针常量实参（CT5B 切片）

- **先纠正上一轮的误判**：第 39 轮判定「前置切片 = 扩展 CT 闭包收集」，但两次失败都不是真正的
  阻塞 —— `iface.yh:334-348` 的 `SYM_CONST + F_ADDR` 分支**本来就支持**字符串字面量指针常量导出，
  唯一条件是初始化式必须是**直接字符串字面量**（`const_expr_kind == 2`），接口「原样重放」后导入方
  按同样规则重新登记只读字节池。`base.TEXT` 转发失败只是因为初始化式是引用而非字面量。
  换成 `pub const TEXT_PTR *char = "AB";` 即通。**闭包收集不需要扩。**
- **改动一处放宽**：`parse/parse_expr.yh` 的单字节指针形参实参检查，除直接字面量外，
  也接受 `SYM_CONST + F_ADDR + is_const` 的指针常量（其标签号是**本地**的，与直接字面量同路径）；
  诊断同步为「只接受直接字符串字面量实参，或导入模块里以字符串字面量初始化的 pub const 指针常量」。
- **用例**：新增 `run/156`（直接字面量 90、公开常量 65、私有常量 67）；`comptimecross` 加
  `api.yh` 的 `pub const TEXT_PTR *char = "AB";` + host 顶层 `$math.head_of(math.TEXT_PTR)`
  断言 65（跨模块 + 导入常量的最强覆盖，值错则 main 非零）；`build-check.py` 的
  `ct5b-crossmodule-pointer-arg-rejected`（旧行为：`head_of(MINE)` 读到 104105 = `"hi"`）
  改为 `ct5b-crossmodule-pointer-arg-accepted`。
- `make test` 263/263（run 134/134、fail 121/121、pass 8/8）；`build-check.py` 84/84；
  `make selfhost-native` 全绿（自解析 70 文件、语料 263/263、模块 17/17、项目 84/84）。
  新种子 SHA-256：`263a10549c56628ea7b5ee01fe8a3dca8d2cb5c9fe3efb8c13b625df7df4c02f`。详见[完成记录](01-finished/yh-跨模块指针常量实参-2026-10-07.md)。

# 2026-10-07 const 聚合常量取地址：修掉第 34 轮引入的误拒

- **发现方式**：三个探针摸编译期边界 —— A `$first(&TABLE[0])` 报「不能给 const 聚合常量赋值
  **或取地址**」；B `pub const ALIAS *char = TEXT;`（引用式常量，单文件）`rc=0` 可用；
  C 正文里读全局指针常量 `rc=0` 可用。
- **根因**：第 34 轮用 `c_lvalue != 0` 判「在写 const」，但 `c_lvalue` 同时表示"赋值目标"
  与"取地址" —— 赋值（`parse_stmt.yh:238`）和取地址（`parse_expr.yh:602`）都是 `+= 1`（0→1），
  值域相同无法区分，于是 `&const_agg.field`、`&const_arr[i]` 这类**只读引用**被误拒。
- **改动**：取地址处改 `+= 2`（其余 `!= 0` 判断语义不变），只读检查改判 `c_lvalue == 1`，
  诊断去掉「或取地址」。效果：赋值仍拒；`&const_agg.f` / `let p *int = &const_arr[0]` 由**误拒**变可用。
  探针 A 的诊断变成「变量不是编译期常量」—— 这是正确边界（运行期地址本就不能作编译期实参），
  与只读性无关。
- **用例**：新增 `run/157`（`&TABLE[0]`、`&TABLE[2]`、`&ORIGIN.y` 取地址后读取）；
  `fail/150` 的 `fail-contains` 同步为新诊断。
- `make test` 264/264（run 135/135、fail 121/121、pass 8/8）；`make selfhost-native` 全绿。
  新种子 SHA-256：`a9db7ad6a1c12fe8f55a68286a75a41bb57ff95b2bf80356969f502c2405fa64`。详见[完成记录](01-finished/yh-const聚合取地址误拒修复-2026-10-07.md)。

# 2026-10-07 跨模块引用式指针常量实参（接口追链重放）

- **探针先行**：D `$weigh($make(1,2))`、E `Point{ y: $two() }`、F `const P Point = $make(3,4)`、
  G CT 正文 `len(a)` 与 `a[0..3]` 视图 —— 四个探针全 `rc=0`，这些能力都已在。（切片语法是
  `[start..end]`。）
- **本轮交付 `pub const A *char = B;` 跨模块可用**：`parse_global_init.yh` 新增与 `TOK_STRING`
  （kind 2）对称的 **kind 3** —— 初始化式是单个 `TOK_IDENT` 时记下该标识符；`iface.yh` 的
  `F_ADDR` 分支按 kind 3 用 `sym_lookup_off` 追**一层**到最终字面式常量并重放**那个**字面式
  （消费者看不到提供方的私有常量名，重放引用本身会在导入侧解析失败）。
- **用例**：`comptimecross` 的 `api.yh` 私有 `const TEXT_ALIAS_BASE *char = "hi";` +
  `pub const TEXT_ALIAS *char = TEXT_ALIAS_BASE;`，host 顶层 `$math.head_of(math.TEXT_ALIAS)`
  断言 104；新增单文件回归 `run/158`。
- **边界**：只追一层（`A = B = 字面量` 两级链、`= base.TEXT` 跨子模块限定名仍拒绝）；
  `iface_ct.yh:695` 的 `string_ptr` 判断仍只认 kind 2，故 `.s.ct` **正文闭包**侧不认引用式常量
  （已记 todo，与实参侧同构的独立小项）。
- `make test` 265/265（run 136/136、fail 121/121、pass 8/8）；`build-check.py` 84/84；
  `make selfhost-native` 全绿（自解析 70 文件、语料 265/265、模块 17/17、项目 84/84）。
  新种子 SHA-256：`10cefe083ad281afb17e492fe2368c4bf8840b04672f08e47633af95e560129e`。详见[完成记录](01-finished/yh-跨模块引用式指针常量实参-2026-10-07.md)。

# 2026-10-07 `.s.ct` 正文闭包认引用式指针常量（提取共用追链函数）

- **交付**：`iface_ct_emit_const` 的 `string_ptr` 不再要求 `const_expr_kind == 2`，改用新的 pub
  函数 **`iface_ct_lit_text(sym_id, out_off, out_len)`** 取字面文本 —— 该函数就是第 42 轮内联在
  `iface.yh` 里的追链，提出来给 `.s.i` 导出与 `.s.ct` 发射**两处共用**（不写第二份拷贝）；
  `iface.yh` 的 30 行内联缩成 4 行调用。诊断改为「跨模块 CT 闭包暂只支持**直接或引用式**的字符串
  字面量指针常量」，`build-check.py:303` 的断言同步。
- **用例**：`comptimecross` 的 `api.yh` 增 `@[comptime] pub fn alias_head() int { return (*TEXT_ALIAS).to_type(int); }`
  （**正文里**引用引用式常量），host 顶层 `const ALIAS_BODY int = $math.alias_head();` 断言 104。
- **边界（试出来的）**：单文件一侧做不了同类用例 —— `const ALIAS *char = BASE;` 在**单文件** CT
  正文里引用会报「编译期求值不支持指针常量」（字面式 `pub const T *char = "hi"` 可用）。原打算加的
  `run/159` 因此删除，本项只有跨模块覆盖。
- **踩坑**：`len` 是 yh 内置名不能作参数名，首版签名 `off *int, len *int` 报「此处需要一个参数名」，
  改名 `out_off`/`out_len`。
- `make test` 265/265（run 136/136、fail 121/121、pass 8/8）；`build-check.py` 84/84；
  `make selfhost-native` 全绿（自解析 70 文件、语料 265/265、模块 17/17、项目 84/84）。
  新种子 SHA-256：`7a47c3ab8095e0c80a34f8872207f168fe818202b4e2d95dc44f27a5b6a56644`。详见[完成记录](01-finished/yh-正文闭包引用式指针常量-2026-10-07.md)。

# 2026-10-07 单文件 CT 正文也认引用式指针常量（追链函数下沉到 gen）

- **约束驱动的重构**：`comptime/ct_ir.yh` **只** `import gen;`，不能调 `parse` 里的
  `iface_ct_lit_text` —— 所以第 43 轮的「共用函数」不能留在 `parse/`，下沉到公共底层：
  `compiler/gen/symbols.yh` 的 **`gen.sym_ct_lit_text`**（同模块直接用 `g_state`）。
  三个调用侧共用一份实现：`.s.i` 导出（`iface.yh`）、`.s.ct` 发射（`iface_ct.yh`）、
  单文件 CT 求值（`ct_ir.yh`）。
- **单文件侧改动**：`ct_ir.yh:313` 的只读池登记由「要求 `const_expr_kind == 2`」改为
  `gen.sym_ct_lit_text` 追链取文本；`ct_pool_register` 的去重键跟着改用**追链后**的偏移，
  否则 `ALIAS` 与 `BASE` 会因不同偏移重复登记同一份字节。
- **用例**：恢复 `tests/yh-run/run/159-comptime-body-pointer-const-alias.yh`
  （第 43 轮曾因单文件不支持而删除，本轮真正支持）；`comptimecross` 的 `ALIAS_BODY` 继续覆盖跨模块。
  第 43 轮文档里「单文件做不了」的说法已就地更正。
- `make test` 266/266（run 137/137、fail 121/121、pass 8/8）；`build-check.py` 84/84；
  `make selfhost-native` 全绿（自解析 70 文件、语料 266/266、模块 17/17、项目 84/84）。
  新种子 SHA-256：`120d737157fca21b948b43cb58008cb3b5fd5b163bb8f75190d753bba3a13e72`。详见[完成记录](01-finished/yh-单文件正文引用式指针常量-2026-10-07.md)。

# 2026-10-07 多级引用链的指针常量（追链由一层改为循环）

- **实测先行的两个发现**：① **单文件**侧多级链本来就可用（前端折叠后 `cval` 直接可用，
  `F_ADDR` 路径不一定被走到），所以 todo 里「两级链仍拒绝」只对**跨模块**成立；
  ② **跨模块**三级链确实失败：`api.yh:86: 错误: pub 指针常量（字符串）暂不支持跨模块导出`
  —— `gen/sym_ct_lit_text` 只追一层，`CHAIN_3 → CHAIN_2` 追到了但后者也是 kind 3。
- **改动**：该函数由「一层」改为**逐跳循环**，16 跳上限兼作**环**（`A -> B -> A` 不会死循环）
  与超深链兜底；每跳仍要求被引用者是 `SYM_CONST + F_ADDR`。`.s.i` 导出、`.s.ct` 发射、单文件 CT
  求值三处同时受益。
- **用例**：`comptimecross` 加三级链（`CHAIN_1/2/3`）断言 104；新增单文件回归 `run/160`
  （一级/二级/三级链）。
- **仍拒绝**：`= base.TEXT` 这类**模块限定名**（名字池里查不到限定名，追链只能跟裸标识符）。
- `make test` 267/267（run 138/138、fail 121/121、pass 8/8）；`build-check.py` 84/84；
  `make selfhost-native` 全绿（自解析 70 文件、语料 267/267、模块 17/17、项目 84/84）。
  新种子 SHA-256：`714b5b9d7ca8a360d05e11e167f60a592883e6a2d4e2c2562ec4024ebad1876b`。详见[完成记录](01-finished/yh-多级引用链指针常量-2026-10-07.md)。

# 2026-10-07 全局聚合常量的编译期下标：内部错误改为明确诊断

- **发现**：编译期正文里 `TABLE[0]` 或 `&TABLE[0]`（TABLE 是全局 `const` 数组）报
  **「内部错误：编译期数组/切片存储无效」** —— 用户能写出的代码不该报内部错误。
- **根因**：`comptime/ct_ir_place.yh:64` 把下标的基础值当作 `CtAggregate` 对象指针校验；局部
  `const` 聚合在编译期确实被建模成 `CtAggregate`，而**全局** `const` 聚合的 `cval` 是**数据段
  标签**，于是 `aggregate == 0` 落进内部一致性检查。
- **改动**：内部检查前先判 `aggregate == 0` 给明确诊断「编译期不支持下标访问全局聚合常量
  （其存储尚未在编译期建模）」，其余情况保留内部错误语义（那才是真的不该发生）。
- **用例**：新增 `fail/151-comptime-global-aggregate-index.yh`，`fail-contains` 锁定新诊断。
- **留下的**：诊断只说清「不支持」，没说「做到」—— 全局 `const` 聚合的值在前端已知，
  理论上可建模成 `CtAggregate`（局部已可用），属独立中等切片，已记 todo。
- `make test` 268/268（run 138/138、fail 122/122、pass 8/8）；`build-check.py` 84/84；
  `make selfhost-native` 全绿（自解析 70 文件、语料 268/268、模块 17/17、项目 84/84）。
  新种子 SHA-256：`794f6ced0d95616dbfc37823ee81d72d911ef6c8d37a60fa0d1fddd3fb6b5ad1`。详见[完成记录](01-finished/yh-全局聚合常量下标诊断-2026-10-07.md)。

# 2026-10-07 模块模式的私有聚合常量（补单文件/模块一致性缺口）

- **探针先行**：递归 `$fact`、`switch`+`enum`、结构体数组 for-in 双绑定三个探针全 `rc=0`
  —— 编译期能力已相当完整，转向 todo 里的真实缺口。
- **缺口**：第 34–37 轮只让**单文件**支持全局 `const` 聚合常量，模块模式**一律拒绝**
  （`const 不支持聚合类型`）。但拒绝理由「接口导出尚未覆盖聚合」只对 **pub** 成立 ——
  接口把标量 `cval` 打成字面量，聚合的 `cval` 是数据段标签；**私有**常量不走接口。
- **改动**：`parse_global_init.yh` 的两处守卫改为「模块模式**且 pub** 才拒绝」，诊断改为
  「pub const 聚合常量暂不支持跨模块导出」。
- **三层实测**：① 私有聚合 + CT 正文引用 → `const 不支持聚合类型`（守卫太宽）；
  ② 放宽后 → `跨模块 CT 正文引用了不支持的模块常量类型`（`.s.ct` 闭包不携带聚合常量）；
  ③ 私有聚合 + **运行期**读 → **通过**。
- **用例**：`comptimecross` 的 `api.yh` 加私有 `PRIV_TBL [3]int = [1,2,3]` 与
  `priv_tbl_sum()`，host 的 main 加 `math.priv_tbl_sum() - 6`（跨模块运行期调用）。
- `make test` 268/268（run 138/138、fail 122/122、pass 8/8）；`build-check.py` 84/84；
  `make selfhost-native` 全绿。新种子 SHA-256：`dce204c12728f42af0cfca3848a62fa6d5b6a33505657f9fa455e018cfde9ca2`。
  详见[完成记录](01-finished/yh-模块模式私有聚合常量-2026-10-07.md)。

# 2026-10-07 `.s.ct` 携带聚合常量源文本（并暴露真正的阻塞点）

- **探针**：编译期除零 / 下标越界 / 传运行期变量 / 递归过深 —— 四个诊断都清晰，无可修。
- **交付**：新增 `const_expr_kind = 4`（聚合常量初始化式源文本）。`parse_global_init.yh` 用
  `record_aggregate_const_src` 记录（结构体与数组两分支），`iface_ct_emit_const` 新增 `agg_src`
  分支把它重放进 `.s.ct`。**传输这一步是通的**，跨模块不再报「不支持的模块常量类型」。
- **暴露的真阻塞点**：导入侧 CT 执行报「内部错误：编译期定长数组源值无效」—— 与第 46 轮同根因：
  全局聚合常量的 `cval` 是**数据段标签**，数据在发射阶段才写出，而 CT 执行在语义阶段。
  `.s.ct` 能否重放源文本不是关键，关键是让全局聚合常量在编译期有值。已改为明确诊断
  （`ct_ir_place.yh` 的 `ct_ir_array_clone_mode`）。
- **两次撞同一根因**：第 46 轮（单文件下标）与第 48 轮（跨模块闭包）指向同一条：语义阶段把全局
  聚合常量建模成 `CtAggregate`。已记 todo。
- `make test` 268/268；`build-check.py` 84/84；`make selfhost-native` 全绿。
  新种子 SHA-256：`2e15073268de58c2371c13d1c413b681fa315185f13070c816b4f42dd38fbd8a`。详见[完成记录](01-finished/yh-跨模块CT聚合常量源文本重放-2026-10-07.md)。
# 2026-10-19 macOS/ARM64 LLVM 接入 F2-0 目标与拒绝基线

- 冻结首期目标为 `aarch64-apple-darwin`、候选最低版本 macOS 14.0；版本采用
  `MACOSX_DEPLOYMENT_TARGET`（缺省 `14.0.0`），SDKROOT 优先，原生宿主才允许 xcrun
  发现 SDK，SDK 版本从 `SDKSettings.json` 读取。生产解析及拒绝用例仍待 F2-2。
- 锁定 LLVM 21.1.8 官方源码归档，SHA-256：
  `4633a23617fa31a3ea51242586ea7fb1da7140e426bd62fc164261fe036aa142`。
  发行包源码通过摘要校验；Homebrew 本机版本不作为 SDK 构建输入。
- 新增 `llvm-darwin-target.yh`，通过 Darwin/ARM64 comptime 条件、LP64 大小及 64 位
  指针布局检查；`make test` 343/344，另有 1 个 Linux 专属用例按平台规则跳过。
  Darwin LLVM 当前拒绝 LLVM 文本、汇编和链接的基线可重放；目标门自测 1 个正例、5 个
  错误报告拒绝案例通过。系统/SDK/clang/ld 路径与版本、种子/源码 SHA 保存在
  `tmp/llvm-migration/darwin-target/report.json`。
- `make selfhost-native` 完成固定点、自解析与运行语料后，在继承的 link-cache 专项门失败：
  当前工作树冷构建记录 6 次 clang 汇编调用，断言期望 2 次。该文件和实现改动早于本切片；
  保留原状且不滚种子，后续在相关切片处理。

# 2026-10-19 macOS/ARM64 LLVM F2-0～4 与 Apple 聚合 ABI 首段

- F2-0～4 已完成目标/SDK契约、Darwin 静态 host、IR/Mach-O 对象、标量 C ABI、生产链接与签名。
  minOS 14.0→15.0 的 O0/O2 对象键失效和 `LC_BUILD_VERSION` 更新均有真实测试。
- F2-5 首段新增独立 Apple ABI 分类器：非 HFA 聚合按模块布局分为 ≤8 字节单 i64、9–16 字节双
  i64、>16 字节 indirect+sret；覆盖 1/3/8/9/16/24 字节、混合 union、按值副本和间接结果。
  固定 Clang oracle 及本机 O0/O2 C↔YH 运行通过。嵌套 HFA 仍明确拒绝，HFA 分配、聚合 callback
  和 Darwin 变参还未完成。
- `make test-llvm-darwin` 通过；`make test` 通过（运行语料 206/207，1 个 Linux 专属跳过）。
  `make selfhost-native` 完成固定点、自解析、CLI、全量语料、scratch-isolation 与 lex-stats，随后
  在继承的 `runtime-memory.py` 因自编译器仍导入 C runtime `strlen` 失败。未滚 Darwin 种子。
- 详细交付与后续边界见[完成记录](01-finished/yh-macOS-LLVM-F2-0至4与聚合ABI首段-2026-10-19.md)。

# 2026-10-19 macOS/ARM64 LLVM F2-5：HFA 与聚合 callback

- Apple ABI 分类器新增嵌套 HFA 参数/返回映射，并验证 7 个浮点参数耗尽 SIMD 参数寄存器后，
  双精度 HFA 整体按栈参数传递；Clang LLVM IR oracle 与 O0/O2 Mach-O C↔YH 运行均通过。
- 新增 HFA 函数指针传递、C 返回 HFA 函数指针、C 调 YH HFA callback 且 callback 再调 C 的嵌套测试，
  覆盖签名、值顺序和返回值；Darwin 专项全门通过。
- `make test` 通过（78/78 语法正例、42/42 反例、346/347 运行用例，1 个 Linux 专属用例跳过）。
  `make selfhost-native` 固定点/自解析/语料/并发检查通过，最终仍在既有 `runtime-memory.py` 导入
  `strlen` 检查失败；没有滚动种子。prelude `printf` 的 Darwin 变参与 `va_list` 留待 F2-6 联测。
- 详见[完成记录](01-finished/yh-macOS-LLVM-F2-5-HFA与callback-2026-10-19.md)。

# 2026-10-19 macOS/ARM64 LLVM F2-5 联合体 HFA 与模块门回归修复

- **联合体 HFA**：`llvm_apple_hfa_walk` 原先只递归 struct/array，`union { f64; [2]f64; }`
  被判成 16 字节整数聚合，走 x0/x1 而非 v0/v1，C↔YH 双向都读到错误字段
  （autoabi 项目 C 调 YH 的第 14 项断言、YH 侧 `values[1]` 检查）。现按 Apple 规则
  让 union 参与 HFA 分类（成员内存重叠，元素数取最宽成员），参数恢复、返回值写回与
  结果还原三条递归路径同步支持 union，并让返回值写回失败不再被静默忽略。
  union HFA 已并入 `tests/selfhost/llvm-darwin-abi-aggregate.{yh,c}`，走同一套
  Clang 21.1.8 oracle 与 O0/O2 Mach-O 双向互调。oracle 比对函数把 `%union.X`/`%struct.X`
  与字面量聚合归一为 aggregate，避免同形签名被误判不一致。
- **RS3b 按文件切分回归（继承改动）**：`ast_ir_shift_rows` 在 pass 1 被覆盖成
  `P0(全部)+P1(前缀)`，文件起始偏移被多推 pass 0 总位移，切掉文件首个函数序言
  （`.s` 以 `29, sp` / `16` 开头），5 个模块用例失败。改为入口位移 = `P0(i)+P1(i)`；
  替换定位同样改用该值（沿用跨遍累计会在 inline 函数声明于非 inline 之后时
  推过函数头），模块验收从 99/104 恢复到 105/105。
- **模块验收脚本**：`backend_text_files` 由顶层 `glob` 改为 `rglob`（RS3b 后产物在
  `<tag>/<source>.s` 子目录）；`u2-attribute-interface-invalidates-caller-ir` 的产物
  定位同时支持 legacy 目录布局与 LLVM 的 `llvm/<tag>.ll`，并只检查调用方函数体
  （文件尾的 weak runtime helper 也含 `unreachable`）。Linux x64 syscall 用例在非
  Linux 目标下改为只断言目标门控拒绝。
- **门禁**：`make test-llvm-darwin` 通过；`make test` 通过（语法 78/78、反例 42/42、
  运行 346/347，1 个 Linux 专属跳过）；`make selfhost-native` 全部通过（固定点 123 项
  一致、自解析、语料、模块项目 105/105），本轮未滚种子。
- 新增 `tests/modules/projects/inlineorder`（非 inline 在前、inline 在后）固化该边界。
- LLVM/Darwin 模块验收 O0 与 O2 各 105/105；legacy 105/105。
- 详见[完成记录](01-finished/yh-macOS-LLVM-F2-5联合体HFA与模块门修复-2026-10-19.md)。

# 2026-10-19 macOS/ARM64 LLVM F2-7：SDK 内容身份与失败提交专项

- **SDK stub reexport 闭包入链接键**（`compiler/cmd/darwin_link.yh`）：此前链接键只哈希
  `libSystem.tbd` 自身，而 `libSystem` 的符号实际来自 `/usr/lib/system/*.tbd` 重导出。
  新增 TAPI 解析：抽取 `reexported-libraries` 段的绝对路径，逐项解析到 SDK 内
  `.tbd`（`.dylib`→`.tbd`，其次原名），混入路径与内容；缺失与存在用哨兵字节区分，
  深度上限 2 防环。实测改动任一重导出 stub 只失效链接键、不重编对象。
- **对象键显式 PIC**（`compiler/cmd/module_build.yh`）：Darwin LLVM 对象的键新增
  `PIC` 标记，避免将来引入非 PIC 变体时旧对象误命中（此前仅靠 triple/桥版本间接覆盖）。
- **新增缓存身份门** `tests/selfhost/llvm-darwin-cache.py` 与双模块夹具
  `tests/modules/projects/llvmdarwincache/`，覆盖：无改动热命中；同路径源内容变化只重编
  main、helper 对象与链接键按实际粒度更新；minOS 14→15→14 对象与链接键按值复现；
  两份 SDKROOT 切换对象键相同、链接键不同；重导出 stub 内容变化只失效链接键；
  链接失败保留旧可执行文件与旧成功 manifest、修复后直接命中；manifest/对象/接口/
  可执行文件损坏均重验重建；构建被终止且留下 `.tmp` 残留时不产生虚假命中；
  两次并发构建都成功且热构建不再改写。门禁用裁剪 SDK
  （SDKSettings + libSystem + 系统 stub 子集）真实链接，不依赖完整 SDK 复制。
- `test-llvm-darwin` 增加该专项门；`make test-llvm-darwin`、`make test`（346/347，1 个
  Linux 专属跳过）、`make selfhost-native`（固定点 123 项、模块项目 105/105）全部通过。
  未滚种子。
- 详见[完成记录](01-finished/yh-macOS-LLVM-F2-7-SDK身份与缓存-2026-10-19.md)。

# 2026-10-19 macOS/ARM64 LLVM F2-8：原生连续自举与全量门

- **自举链接注入**：Darwin 的 raw `ld64.lld` argv 由 yh 侧拼装，此前
  `YH_LLVM_SELFHOST` 闭包为空，A 编出的 B 只带弱桩、不能 LLVM 编译。现由
  `tools/llvm-darwin-host.py` 生成 raw `-force_load` 闭包（桥、lld 与 LLVM 静态归档
  + `-lc++`）写入 `lld_link_config.h`；`lld_bridge.cpp` 暴露计数/取值访问器，
  `link_cache.yh` 在 `YH_LLVM_SELFHOST=1` 时追加，普通程序不注入。闭包并入
  `lld_identity`，换归档即失效缓存。
- **新增 `tests/selfhost/llvm-darwin-selfhost.py`** 与固定点探针
  `llvm-darwin-fixedpoint.yh`：入库种子 legacy 编 A（真实桥），A 以 LLVM 编 B/C/D；
  O0 与 O2 各自验证 B→C→D 的 24 个 `.ll/.s.i/.s.ct` 逐字节一致，并冻结各代
  checked/emitted/rejected/fallback 到 `stats.json`。
- D-O2 上：自解析 104/104；语法、运行（346/347，1 个 Linux 专属跳过）、模块 18/18、
  项目验收 105/105（O0/O2）；Darwin SDK/host/bridge/object/ABI/runtime/link/cache
  八个专项门全通过；隔离 PATH 下确认发射与链接全程无 clang/ld/lld/codesign/xcrun
  调用，候选仅动态依赖 libSystem/libc++、内嵌固定 lld 身份与有效 ad-hoc 签名。
- **CI**：Darwin 作业新增 `make selfhost-llvm-darwin` 与 stats/logs/snapshots
  artifact 上传，超时调到 120 分钟；仍为手动触发，不自动滚种子。
- `make selfhost-llvm-darwin`、`make test-llvm-darwin`、`make test`（346/347）、
  `make selfhost-native`（固定点 123 项、模块 105/105）全部通过。未滚种子。
- 详见[完成记录](01-finished/yh-macOS-LLVM-F2-8-原生连续自举-2026-10-19.md)。

# 2026-10-20 删除 asm/、link/ 独立工具链项目

- **背景**：LLVM 后端（Linux/x86_64、Darwin/ARM64 默认）由内嵌桥生成对象、
  内嵌 lld 或平台链接驱动完成最终链接；`asm/`、`link/` 不参与任何编译链路。
  用户决定完全删除，不再作为独立产品维护。
- **删除**：`asm/`、`link/` 两个项目（源码、测试、构建产物）；
  `bin/yh_link_wrap.sh`；`tools/yh-toolchain-inventory.py`；
  `docs/02-plan/` 下 4 个专属方案文档与 `docs/03-design/` 下 4 个专属
  设计/契约文档。
- **同步**：Makefile 删除 `yh-asm`/`yh-link-build`/`yh-link-probe` 目标及相关
  变量与注释；`ci.yml` 删除 linux-arm64 的 `make yh-link-probe FULL=1`；
  `AGENTS.md` 更新 CI 与平台说明；`.gitignore` 删除 `/yh_asm`、`/yh_link`；
  `compiler/cmd/link_cache.yh` 的 `mb_asm_tool` 注释改为通用外部汇编器
  （`YH_LINK` 扩展点保留）；`tests/selfhost/link-cache.py` 删除同目录
  `yh_link` 探测；`docs/todo.md` 删除 asm/link 待办与 R4/R5；ADR-0014 追加
  删除决定。历史完成记录（`docs/01-finished/`）保留当时事实，其中指向已删除
  方案/设计文档的链接不再解析。
- **验证**：`make -n` 解析通过；legacy 冷编成功
  （`python3 tools/seed-build.py --compiler bin/yh-darwin-arm64 --project compiler
  --output yh --backend legacy`）；`tests/yh/check.py --compiler` 78/78 正例、
  42/42 反例；`tests/yh-run/check.py --backend legacy` 通过 348/349（1 个
  Linux 专属跳过）；`tests/modules/check.py --backend legacy` 18/18；
  `tests/selfhost/link-cache.py` 经 legacy 包装器通过（对象/链接缓存边界正常）。
  默认 LLVM 构建仍受种子硬编码
  `/Users/lavender/.codex/worktrees/...` 与缺 `-lc++` 阻塞，属既有 todo 项，
  与本次删除无关。

# 2026-10-20 0.0.5 补档 Linux/x86_64 Release

- **Release CI**：`release.yml` 新增 `linux-x86_64` 作业；新增
  `workflow_dispatch` 输入 `tag` 与 `x64_only`。`x64_only=true` 时
  `linux-arm64`/`darwin-arm64` 直接 skipped，只构建 x64，并把
  `yh-<tag>-linux-x86_64.tar.gz`/`.sha256` 上传到已有 Release。
- **x64 种子兼容性**：`seed-llvm-x64-2026-10-19` 的 `yh-linux-x64`
  （SHA-256 `c6733eb2…`）动态依赖 `libxml2.so.16`，Ubuntu 24.04 只有
  `libxml2.so.2`，不能直接在发布 runner 上执行。发布作业沿用 CI 已验证的
  AArch64 种子 + QEMU 路径，`tests/selfhost/llvm-selfhost.py` 产出
  x86_64 D-O2；该候选在 Ubuntu 原生运行，且不依赖 x64 种子的 libxml2。
- **验证**：dispatch run `39315997430` 中 x64 构建成功、arm64/darwin skipped、
  Release 作业成功；x64 构建内 D-O2 的 O0/O2 语料各 344/349（其余为平台
  跳过）、模块 18/18、项目 105/105、自解析 104/104，冒烟通过。
  `0.0.5` 现有资产增加 `yh-0.0.5-linux-x86_64.tar.gz`
  （42,565,227 B）及 `.sha256`，原 darwin-arm64/linux-arm64 资产保留。
- Release 因多次移动 tag 一度变成 untagged/draft；已通过 API 重新关联
  `0.0.5` tag 并发布（`https://github.com/lalavender/x/releases/tag/0.0.5`）。
  tag 保持 `0.0.5 -> 968de29`，发布工作流修复在 `llvm` 分支，避免再触发
  arm64/darwin 全量构建。

# 2026-10-22 换行终结语句（0.0.8-rc）

- **语法**：`\n` 参与语句边界，简单语句、模块头、类型别名、字段与枚举成员可以
  省略行尾分号；同一行仍用 `;` 分隔；严格续行要求括号外运算符放在上一行末尾；
  裸 `return` 行尾结束。设计见
  [03-design/yh-换行终结语句设计.md](03-design/yh-换行终结语句设计.md)。
- **实现**：`compiler/lex/layout.yh` 归一化补零长度 `TK_SEMI`；解析器用
  `p_implicit_semi`/`p_take_block_end` 区分隐式与显式终结符；参考语法用
  `tokens { IMPLICIT }` + `stmtEnd`，语料门禁按同一规则归一化。
- **验证**：`make test` 全绿（正例 80/80、反例 44/44，run 209/210、fail 133/133、
  pass 8/8）；`make selfhost-native` 全绿（cc3→cc4 27 个产物一致、自解析 101
  个源文件、modules 19/19、project cases 115/115）。
- 记录：[01-finished/yh-换行终结语句-2026-10-22.md](01-finished/yh-换行终结语句-2026-10-22.md)。
  未滚种子、未发版、未批量删分号（方案 Phase 1/2）。

# 2026-10-22 CI 迁到 Gitea Actions（Jenkins 退役）

- **背景**：原 CI 分两套（CircleCI 分支门 + 本机 Jenkins 发布），Jenkins 靠本地
  `pre-push` 钩子触发，`--no-verify`、换机器、网页操作与 PR 都覆盖不到。
- **落地**：
  - Gitea 1.26.1 开 `[actions] ENABLED=true`；装 `gitea-runner` 5.2（brew
    formula 名 `gitea-runner`），host 模式实例 `yh-local`，labels
    `macos-arm64` / `linux-arm64`，capacity 1。
  - `.gitea/workflows/ci.yml`（分支门：ANTLR + Darwin/arm64 + Linux/AArch64）与
    `.gitea/workflows/release.yml`（版本 tag：三端构建、cc4 打包、发 GitHub Release）。
  - 删除 `Jenkinsfile` 与 `tools/jenkins/`（trigger/setup 随触发链移除），发布脚本
    迁到 `tools/publish-release.py`；恢复被串联的 git-lfs `pre-push` 钩子。
- **调试结论（已写进 workflow 注释与 todo D2/D3）**：
  - Gitea 会把 `GITHUB_REPOSITORY` 覆写成 `yh/yh`，取种必须 `--repo lalavender/x`；
  - Apple container 内 GitHub API 不可达（DNS 失败），取种改在宿主 step 完成；
  - `tests/selfhost/llvm-host.py` 用 `relative_to(ROOT)` 写身份记录，容器内闭包
    缓存必须挂到 `/work/tmp/llvm-migration`，symlink 到宿主绝对路径会断言失败；
  - 8GB 宿主并发两个构建会触发 OOM（LLVM 静态链接被 kill），capacity 降到 1、
    容器内存提到 3G；宿主磁盘一度只剩 2.5Gi，清掉闲置镜像 13.5GB 后恢复；
  - x86_64 端在 amd64 模拟下 `run/20-bytebuf.yh` 崩溃（信号 5），发布流水线对该
    端只做构建+打包，运行证据以真机为准。
- **验证**：`0.0.8-rc.4` tag 全流程成功，GitHub Release 三端资产齐全
  （darwin-arm64 26.5MB、linux-arm64 42.6MB、linux-x86_64 42.6MB，各带
  `.sha256`），见 <https://github.com/lalavender/x/releases/tag/0.0.8-rc.4>。

# 2026-10-22 分号删除（compiler/，0.0.8-rc）

- **范围**：`compiler/` 101 个 `.yh`，删除 24,514 个可省略行尾分号，保留 1,061 个
  同行分隔/裸块前分号，行数不变。
- **工具适配**：`selfhost_snapshot_gate.py`、`tests/selfhost/link-cache.py` 的
  module 声明正则改为分号可选；`compiler-performance.py` 的模块名提取同步。
- **验证**：`make` 冷编成功，`compiler/.build` 与删除前对比**非 manifest 差异 0**；
  `make test` 全绿；`make selfhost-native` 全绿（27 个产物固定点、自解析 101 文件、
  modules 19/19、project cases 115/115）。
- 记录：[01-finished/yh-分号删除-2026-10-22.md](01-finished/yh-分号删除-2026-10-22.md)。
  未清 `libs/`/`tests/`/`examples/`，未滚种子。

# 2026-10-22 0.0.8-rc.7 发布与种子换代

- **发布流程改造**：`release.yml` 拆成 `prepare`（预建 arm64/amd64 镜像）→
  `darwin-arm64`/`linux-arm64`/`linux-x86_64` 三端**并行** → `publish` 汇总；
  产物写 `$HOME/yh-release-dist/ci-<run_id>`；打包后追加 `./yh --syntax-check`
  无分号用例自检。`ci.yml` 增加 `linux-x86_64` 并行任务。
- **失败与修复**：rc.5 两个 Linux job 漏 `GH_TOKEN`（取种 403）；rc.6 publish
  发现容器内写的宿主绝对路径宿主看不到（改为容器内 `/work/dist`、宿主搬运）；
  rc.7 publish 上传遇 SSL/EOF，`publish-release.py` 加退避重试与同名资产幂等。
- **结果**：`0.0.8-rc.7` 三端资产发布成功：
  <https://github.com/lalavender/x/releases/tag/0.0.8-rc.7>；darwin 资产字节
  含 `换行终结符分配失败`、对 `tests/yh/02-basic/04_newline_terminator.yh`
  通过。
- **种子换代**：`make fetch-seed` 取 rc.7 官方种子（`624ffc50…`），`make` 冷编
  无分号源码成功、`--compiler` 语料 80/80 + 44/44；`make seed` 已是新一代
  （`e96eca03…`）。

# 2026-10-22 全仓去分号收尾

- **范围**：`libs/`、`examples/`、`tests/` 非反例语料 503 个文件删除 11,698 个
  分号；`compiler/` 此前已删 24,514 个。反例（`rejected/`、`reject/`）、冻结
  语料（`tests/perf/`）、按精确源码字节改写的项目 fixture、显式分号正例保留。
- **验证**：`make test` 全绿（80/80、44/44、run 209/210、fail 133/133）；
  `make selfhost-native` 全绿（27 产物固定点、自解析 101、modules 19/19、
  project 115/115）。
- 记录：[01-finished/yh-分号删除-2026-10-22.md](01-finished/yh-分号删除-2026-10-22.md)。

# 2026-10-22 YH_LLVM_CACHE 自动定位

- **问题**：换 worktree/机器后要手工 `YH_LLVM_CACHE=...`，否则 Makefile 与
  `tools/llvm-*.py` 各自回落到空目录，`make llvm-host` 重新准备闭包。
- **实现**：新增 [tools/llvm_cache.py](tools/llvm_cache.py)：显式 `YH_LLVM_CACHE`
  → 仓库 `tmp/llvm-migration` → 主 worktree 的 `tmp/llvm-migration`
  （`git rev-parse --git-common-dir`）。Makefile 以它为默认值并 `export`，
  `DARWIN_SDK_RECORD` 跟随；`llvm-darwin-host`/`llvm-host`/`llvm-sdk` 与
  selfhost 探针统一 `cache_root()`；`make` 前置目标把仓库内
  `tmp/llvm-migration` 软链到缓存根（`compiler/project.toml` 的桥库路径是
  仓库相对）。
- **验证**：在 `/tmp/yh-cachetest` 新建 worktree（无缓存、不设环境变量）→
  `make llvm-host` 复用主仓库缓存、`make` 构建成功、产物对
  `tests/yh/02-basic/04_newline_terminator.yh` 返回 0；主仓库 `make` 回归正常。

# 2026-10-22 0.0.8 正式发布

- **发布**：`0.0.8` tag 三端发布成功，GitHub Release（非 prerelease）资产齐全：
  <https://github.com/lalavender/x/releases/tag/0.0.8>。darwin 资产实测含
  「换行终结语句」并对无分号源码返回 0。
- **runner 优化**（打 tag 不再起三组 runner）：
  - `ci.yml` 去掉了 `<ver>-release` 分支触发（release 分支内容等同 rc 末提交，
    由 tag 发布覆盖），打 tag 时只起一组；
  - `FAST_DIR` 追加 `$GITHUB_RUN_ID`：同机并发多个 run 时不再共用
    `/tmp/yh-fast`，否则 `stage-yh` / `--workdir` 互相覆盖，release 的
    Darwin 任务曾因此误报 `empty 缺少可操作诊断`。
- 记录：[release-0.0.8.md](01-finished/release-0.0.8.md)。
