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

## 编译器性能测试（2026-10-23 方案，待实施）

[性能方案](02-plan/yh-编译器性能测试方案-2026-10-23.md)独立承接性能口径与版本对照，
本轮仅交付方案；先做 PF0/PF1，再据实测瓶颈安排后续。

- [ ] **PF0**：冻结当前 LLVM 自编语料与增量小项目，固定 A/B 二进制、闭包和环境身份。
- [ ] **PF1**：扩展现有性能脚本，解除版本/项目硬编码，补缓存统计、A/B 交错和原始报告；
  O0 无改动/单函数修改/清构建缓存各至少 20 轮。
- [ ] **PF2**：LLVM 阶段归因、并行内存口径、接口/编译期失效矩阵及 O2 对照。
- [ ] **PF3**：规模增长、产物运行基准与代码体积；并发扫描待存在控制入口后再做。
- [ ] **PF4**：Gitea 独立性能报告、资产归档、噪声校准与回退复测。

## 语言内测试（YT0–YT3b、YT2d、YT1.1 已实施；剩余 YT4 迁移与发版）

[设计提案](03-design/yh-test语言内测试设计-2026-10-23.md)与
[实施分期](02-plan/yh-test分阶段实施方案-2026-10-23.md)已整理。
YT0 语法基线、YT1 发现/文档绑定/无运行检查、YT2a（测试体降低 + 运行期
断言）、YT2b（入口模块/逐例进程/结果协议/汇总）、YT2c（执行过滤/超时/
`testing.fail/skip`/断言消息）、YT3a（标准库 string 内建测试与门禁）与
YT3b（compiler 内嵌测试与门禁，随 0.0.9-rc.2 交付）、YT2d（日志/并行/缓存键）
与 YT1.1（项目外单文件）已完成，证据见
[YT0 记录](01-finished/yh-test语法基线-2026-10-23.md)、
[YT1 记录](01-finished/yh-test发现与无运行检查-2026-10-23.md)、
[YT2a 记录](01-finished/yh-test降低与运行期断言-2026-10-23.md)、
[YT2b 记录](01-finished/yh-test执行器与结果协议-2026-10-23.md)、
[YT2c 记录](01-finished/yh-test执行增强-2026-10-23.md)、
[YT3a 记录](01-finished/yh-test标准库内建测试-2026-10-23.md)与
[YT3b 记录](01-finished/yh-test编译器内嵌测试-2026-10-23.md)、
[YT2d-1 记录](01-finished/yh-test逐例日志与截断提示-2026-10-23.md)、
[YT2d-2 记录](01-finished/yh-test测试缓存键-2026-10-23.md)与
[YT1.1 记录](01-finished/yh-test项目外单文件-2026-10-23.md)；
既有测试的迁移候选见
[YT4 分析](02-plan/yh-test语法迁移既有测试分析-2026-10-23.md)；
以下只保留未完成项。

- [x] **YT1.1**：项目外单文件临时单模块上下文（临时项目根在
  `<源文件目录>/tmp/yh-test/single`，只装入该文件，模块名缺失时由文件名派生，
  允许导入标准库）。
- [x] **YT2a**：测试体降低为模块内 `pub` 无参 `void` 函数、`$assert` 降为
  `__yh_test_assert(cond, line, col, msg)` 运行期调用、受检节点与检查身份、
  `--no-run` 发布对象与 `--emit-llvm` 审阅；生产构建零测试符号。
- [x] **YT2b**：`__yh_test_assert` 运行时定义与失败位置记录、测试入口模块、
  逐例 fork/exec、`YHTP`/`YHTF` 结果协议与
  `结果: N passed; M skipped; K failed` 汇总；崩溃、提前退出与记录缺失均判
  失败且不阻断后续用例。
- [x] **YT2c**：执行过滤、`--timeout`（1..3600，缺省 15 秒）、
  `libs/testing` 的 `fail/skip`、断言位置与消息报告、SKIP 汇总。
- [x] **YT2d-1**：逐例独立日志文件（`tmp/yh-test/log/`，失败回显末尾 2 KiB）
  与断言消息截断提示（`0x1e` 标记 + UTF-8 边界回退）。
- [x] **YT2d-2**：测试构建使用独立目录与扩展模块键（测试模式 + 协议标签 +
  本轮选中测试集合摘要）；同选择第二次命中、换选择重编、生产/测试互不相通。
  **剩余**：函数级 IR 与 check 切片缓存仍未用于测试构建（键不覆盖 TK_TEST）。
- [x] **YT2d-3**：并行执行用例（`YH_TEST_JOBS` 缺省 4，每批同时 fork/exec，
  批内按原顺序等待与打印；每例独立超时与日志）。
- [x] **YT3a**：`libs/string/99_tests.yh` 内建测试、`make test-lib-tests`
  入口，接入 `make test` 与 `make selfhost-native`；修复非目标项目 test 声明
  误登记与源码根内 `tmp/`、`.build/` 被当源码扫描两个缺陷。
- [x] **YT3b（0.0.9-rc.2 交付）**：用 rc.1 种子给 `gen`/`lex`/`parse` 加内嵌
  test 块，恢复 `tools/compiler-tests.py` 与 `make test-compiler-tests`，
  并验证生产对象与 `.s.i` 零测试符号。

### YT4 既有测试迁移（2026-10-23 分析完成，待实施）

[分析](02-plan/yh-test语法迁移既有测试分析-2026-10-23.md)按「纯逻辑断言可迁移、
编译器契约不迁移」给出候选、前置缺口与分阶段顺序。结论：收益是失败定位与
粒度，不是门禁变快；迁移前必须先做 YT4a，且每个库保留一个外部消费者 smoke。

- [ ] **YT4a 前置**：测试运行目录/缓存隔离（并入 YT2d：编译器身份 + 目标 +
  优化级 + 运行实例）、`make test-lib-tests` 改无选择器、补 `-O2` 入口；
  连跑两次 + O0/O2 交替验证。
- [ ] **YT4b string**：5 组行为夹具 → `libs/string` 测试，`stringinterop` →
  `libs/toml`；保留 `stringresources` 注入、`reference.py` 差分与安装门。
- [ ] **YT4c toml**：5 组 API 夹具（873 行、146 处 `ok()`）→ `libs/toml`
  测试；保留 `tomlfiles`、conformance、injection、install。
- [ ] **YT4d cli**：5 个 `--selftest` 主体（约 3625 行）→ `libs/cli` 测试；
  保留 argv/退出码/stderr 用例、`cliwarnings`、`clidiff` 差分。
- [ ] **YT4e 编译器 fixture**：`irverify`/`astcheck`/`irfront` 迁入
  `compiler/{ir,ast,check}` 测试并删除 `copy_proj` 特判；`llvmlower`/
  `llvmchecked` 暂留。
- [ ] **YT4f os/sys/time**：纯模型与错误分类断言迁入 `*.linux.yh`/
  `*.darwin.yh` 测试；文件/目录/进程/环境与 Linux 目标类型检查留在外部。
- [ ] **决策**：迁移范围（是否含 YT4e）、旧 runner 双跑周期、OS/FS 是否迁入、
  断言粒度、是否允许测试调用私有 `fn`、消费者 smoke 规模。

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

### FMT fmt 运行时与 V 风格插值（2026-10-23 改版；R0–R3/I0–I5 待实施）

用户决定：字符串格式化采用 V 式插值 `"…${expr:spec}…"`，结果为
`string.String`；首版不实现 Go 的 `%` 格式串与 `Printf` 族（是否保留为
次级 API 待确认）。语言设计见
[字符串插值设计](03-design/yh-字符串插值设计-2026-10-23.md)，运行时见
[fmt 标准库设计](03-design/yh-fmt标准库设计-2026-10-23.md)，
[方案](02-plan/yh-fmt标准库实施方案-2026-10-23.md)列出 R0–R3（fmt）与
I0–I5（语言）；插值需要改词法/解析/检查/降级。fmt 不改 prelude
`printf`（H.I3 的按需扩展仍独立）。

- [ ] **R0 Value 与基础渲染**：Kind/Value/构造器、append_text/append_value
  默认格式；`fmtvalue`/`fmtappend` fixture。
- [ ] **R1 V spec 与整数/文本**：flags/width/precision、`d x X o b s`、
  对齐与非法 spec；`fmtspec` fixture。
- [ ] **R2 浮点**：NaN/±Inf/-0、`f F e E g G`、V 尾零规则；`fmtfloat`
  fixture 与 golden 差额记录。
- [ ] **R3 打印/字符串与收口**：print/sprint/fprint、render、of_string、
  安装导入、surface/`nm -u`、`make test-fmt` O0/O2。
- [ ] **I0 语言探针**：词法后扩展、layout 边界、AST 快照/缓存、降级 ABI、
  缺 import 诊断；决定 append 契约还是 `fmt.interp`。
- [ ] **I1 词法扩展与解析**：`${}` 扫描、内部 token、AST 插值/part、
  转义与错误；`tests/yh/interp` 语法门。
- [ ] **I2 检查与缓存**：`string.String` 类型解析、按静态类型选构造器、
  编译期 spec 校验、跨 worker/缓存/固定点。
- [ ] **I3 降级与端到端**：临时 String + append、失败零句柄、求值顺序、
  `tests/yh-run`/modules O0/O2。
- [ ] **I4 诊断/文档/全量门**：错误表、README/设计/todo/finish、
  `make`/`make test`/`make selfhost-native`/`git diff --check`。
- [ ] **I5 可选扩展**：嵌套插值、运行时 width/precision、`r/R`、
  `string.String`/enum 支持；每项单独立项。

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

- **❓1 Nanopass 定位**：LLVM 已接管通用优化与寄存器分配。建议 NP3 并入受检契约
  与 lowering 解耦，NP0/NP1/NP2/NP4/NP5 关闭（NP4 自研机器 IR 与 ADR-0014
  冲突）；需用户确认后再改
  [Nanopass 方案](02-plan/yh-Nanopass风格优化架构实施方案.md) 与 ADR-0011。
  2026-10-22 [LLVM 分支架构复核](03-design/yh-LLVM分支架构复核-2026-10-22.md)
  进一步建议保留 NP0 的语义/O0-O2/固定点要求，通用优化不重复建设；优先统一
  发射驱动、拆分 lowering，再实施可重绑定的函数 IR 复用。本次未修改旧方案状态。
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
