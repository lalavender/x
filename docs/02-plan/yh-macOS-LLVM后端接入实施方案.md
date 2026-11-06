# yh macOS/ARM64 LLVM 后端接入实施方案

> 执行状态：用户已确认先完成 macOS 原生引导，再单独验收 Linux/x64 交叉引导；按 F2 分片实施。
> 本文件是实施依据；未勾选项仍待完成，任何自举失败都不得滚动种子。
> 2026-11-06：文件级对象/RS3 已撤销（[ADR-0020](../adr/0020-yh对象粒度停在模块级.md)），
> 文中相关段落仅作历史记录；对象粒度固定模块级。

**目标：**macOS/ARM64 获得内嵌 LLVM/lld 的原生 yh、全量运行与自举固定点，
并提供 Linux/x64 交叉引导的独立验收路线。

**架构：**复用受检快照→模块 IR→LLVM 路径，新增 Apple C ABI、Darwin runtime
及 Mach-O 链接分支。用户已确认先原生引导、再交叉验收，共用 SDK 与目标实现。

**技术：**yh、LLVM/lld 21.1.8 静态 C/C++ 桥、Apple ARM64 ABI、Mach-O、Python 门禁。

**设计依据：**[macOS LLVM 接入设计](../03-design/yh-macOS-LLVM后端接入设计.md)、
[当前差距](yh-macOS-LLVM迁移差距分析.md)、[ADR-0014](../adr/0014-yh采用LLVM作为正式代码生成后端.md)。

## 全局约束

- 首期仅 `aarch64-apple-darwin`；SDK host 键 `darwin-aarch64`，种子命名保持 Darwin/arm64。
- LLVM/lld 固定 21.1.8、静态嵌入；正常发射/链接不调用外部 LLVM 工具或加载动态 LLVM。
- 建议部署版本缺省 14.0，显式读取 MACOSX_DEPLOYMENT_TARGET；SDK 必须实际锁定与验收。
- Darwin PIC/PIE；保留 O0/O2、generic CPU、yh-llvm-v1 和既有源语言/拒绝规则。
- 每个代码切片先加 tests 下的 `.yh` 红例/复现，再最小实现、`make`、定向门。
  片段关闭时跑本平台 `make test` + `make selfhost-native`，Linux 回归由 CI 承担。
- 文档和源码中文注释；只导出真实跨模块接口；新增文件按职责拆分，不重构无关旧代码。
- 临时包、候选、日志均在 tmp；提交只包含该片文件，不带现有未提交的 R2/CI 改动。
- F2 不改 F1/F2 项目排期，不提前关闭 LL11/R2b/R2c，不执行 LL12 删除。
- 本文所有新增命令/文件标为“拟新增”的部分，在相应任务完成前不可当作现有能力。

## 审查重点与负责切片

| 输入/失败场景 | 预期 | 负责 |
| --- | --- | --- |
| 没有固定 SDK，却构建 legacy；显式要求 LLVM | legacy 仍能构建；LLVM 明确失败且不回退 | F2-1 |
| 本机 SDK 27、CI SDK/系统较旧；同路径 SDK 被替换 | 兼容性有实测；内容变化使对象/链接正确失效 | F2-0/1/7 |
| Linux A 生成 Mac B，库和源码后缀按错平台 | B 用 Darwin 归档和 OS 桥，A 仍执行 Linux 宿主操作 | F2-2/9 |
| 第 9/10 个窄参数、HFA 溢出、返回缓冲、C 回调、变参 | O0/O2 双向运行及 oracle 一致 | F2-3/5 |
| 失败链接、lld worker 退出、路径含空格/中文、缓存损坏 | 不发布半产物、不破坏旧可执行文件，重建结果确定 | F2-4/7 |

## 文件职责与接口

| 文件/组 | 变更责任 |
| --- | --- |
| `vendor/llvm/sdk.lock.json`、`vendor/llvm/README.md` | 固定 Darwin 静态包、组件、许可与身份 |
| `tools/llvm-sdk.py`、拟新增 `tools/llvm_darwin_sdk.py`、`tools/llvm-host.py`、`tools/seed-build.py` | 保留 Linux 分支；Darwin 构建/包装器/目标依赖注入 |
| `compiler/llvm/bridge.c/.h`、拟新增 `bridge_stub.c`、已有 `lld_stub.cpp` | emit v2 与有诊断的无 SDK 桩 |
| `compiler/backend/llvm_bind.darwin.yh`、`llvm_bind.linux.yh`、`llvm_bridge.yh` | C 绑定与薄包装，无语言语义 |
| `compiler/backend/llvm_module.yh`、`llvm_call.yh`、`llvm_scalar.yh`、`llvm_zabi.yh` | Apple 目标 dispatch，保留 SysV 路径 |
| 拟新增 `compiler/backend/llvm_apple_abi.yh`、`llvm_apple_runtime.yh` | Apple ABI 与 Darwin LLVM runtime；文件无平台筛选后缀 |
| 拟新增 `compiler/cmd/darwin_link.yh`；已有 `llvm_emit.yh`、`link_cache.yh`、`project_state.yh` | 会话配置、Mach-O argv、缓存与发布 |
| `compiler/llvm/lld_bridge.cpp`、`Makefile` | 复用原始 lld argv；新增 Darwin 专门门 |
| 拟新增 `tests/selfhost/llvm-darwin-*.py`、`.yh/.c` fixture | SDK/目标、ABI、runtime、链接、缓存、自举、交叉专项 |

新 yh 侧桥接口：

```text
backend.llvm_bridge_emit_v2(text *char, length int, triple *char, min_os *char,
    opt_level int, kind int, path *char, reason *char) int
backend.llvm_lld_link_argv(argv **char, argc int, diagnostic *char) int
```

第一项返回 0/-1，诊断缓冲沿用 LLVM_BRIDGE_DIAG；第二项沿用 lld 的 0/-1/-2
和 LLVM_LLD_DIAG 协议。C emit v2 的签名见设计第 4 节。保留 v1 与现有 ELF driver。
`DarwinLinkConfig` 仅 cmd 模块私有，四字段和字符串所有权以设计第 3 节为准。
ABI 内部助手保持私有；`llvm_abi_attr_kind` 增加 `unit *ir.IRModule` 参数以读取目标，
同步全部声明、定义、调用点；不要用正在运行的宿主决定被输出代码的 ABI。

## 任务顺序

```text
F2-0 目标/SDK契约 → F2-1 静态SDK与桥 → F2-2 对象发射 → F2-3 标量C ABI
→ F2-4 Mach-O链接 → F2-5 完整Apple ABI → F2-6 Darwin runtime
→ F2-7 缓存/失败专项 → F2-8 原生全门/自举 → F2-10 默认与种子
                                           └→ F2-9 Linux交叉独立验收
```

交叉路线不代替 F2-8；若用户选择交叉首发，F2-9 在公共切片 F2-0～7 完成后产 B，
再在 Mac 完成 F2-8 的等价原生链。F2-10 仍等待公共正式切换硬门。

### F2-0：冻结目标配置与可重放基线

**修改：**`docs/03-design/yh-macOS-LLVM后端接入设计.md`、`vendor/llvm/README.md`。
**拟新增测试：**`tests/selfhost/llvm-darwin-target.py`、
`tests/yh-run/run/llvm-darwin-target.yh`（platform: darwin-arm64）。
**产出接口：**版本解析结果、SDK 内容身份及会话 DarwinLinkConfig 的记录契约。

- [x] 记录源码树/种子 SHA、系统/SDK/工具路径与版本；最小目标探针保留当前平台拒绝证据，
  报告位于 `tmp/llvm-migration/darwin-target/report.json`。
- [x] 新用例锁定 Darwin/arm64 `$if`、LP64/布局；生产错误版本和缺 SDK 的拒绝在 F2-2
  通过真实 cmd 入口验收，避免用测试副本替代生产逻辑。
- [x] 冻结会话配置解析规则：版本规范化为 major.minor.patch；SDKROOT 优先，仅 Darwin
  原生允许 xcrun 发现；Linux 缺 SDKROOT 明确失败。生产 cmd 解析在 F2-2 接入。
- [x] 冻结源包获取方式及实际 SHA；固定 LLVM 21.1.8 官方源码归档，SHA-256
  `4633a23617fa31a3ea51242586ea7fb1da7140e426bd62fc164261fe036aa142`；Homebrew 安装不作为 SDK 输入。
- [x] 验证目标门的报告/断言自测：`python3 tests/selfhost/llvm-darwin-target.py --self-test`；
  当前拒绝基线与纯语法/语义 check 不需固定 LLVM 包。SDK27 兼容性由 F2-1 实测，
  生产配置有效输入/拒绝矩阵在 F2-2 调用真正 cmd 路径验收，不用测试内重写逻辑代替。

**关闭：**配置契约无歧义，当前平台拒绝基线可重放；未宣称生产解析或对象已可生成。

### F2-1：Darwin 静态 SDK、真实绑定及 legacy 兼容

**依赖：**F2-0。
**修改：**SDK/host/seed-build 工具、lock/README、Makefile、桥绑定。
**拟新增：**`tools/llvm_darwin_sdk.py`、`compiler/llvm/bridge_stub.c`、
`tests/selfhost/llvm-darwin-sdk.py`、`tests/selfhost/llvm-darwin-bridge-probe.yh`。
**产出：**SDK host `darwin-aarch64`、完整 host.json、emit v2/raw lld 绑定。

- [x] SDK 门复现宿主键拒绝；`.yh` 桥探针已在 Darwin 弱桩上覆盖版本、重复调用、诊断截断和失败保留。
- [x] 从校验过的 LLVM 21.1.8 源码构建静态包，目标 X86/AArch64、lld Common/ELF/MachO/COFF
  所需闭包；BUILD_SHARED_LIBS、LLVM_BUILD_LLVM_DYLIB、LLVM_LINK_LLVM_DYLIB 为 OFF。
  非必需 zlib/zstd/XML 为 OFF；oracle clang/opt 21.1.8 作为独立测试工具归档。
  本机在 CLT SDK 26.5 下实际构建并通过静态组件/工具身份门。
- [ ] macos-14 构建部署版本 14.0 的候选包，记录 Apple SDK、工具链与组件/许可摘要；
  本机研究包可单独验收。用固定 lld 真正解析 SDK 的 libSystem/libc++ 及 reexport，
  检查 SDK27 新目标标签兼容性；失败不推进成可发布包。
- [x] Darwin 静态链接不走 memfd/GNU group；生成 clang 包装器并让 seed-build 显式选择。
  只对编译器自举链接追加桥/LLVM；普通程序不追加。
- [x] Darwin `.yh` 改 extern，新增有明确诊断的 C stub；auto/off 无完整 SDK 时 legacy
  仍可构建，require 必失败；`--backend llvm` 命中 stub 时失败而非回退。
- [x] 实现 emit v2；v1 Linux 行为保留。核对 `otool -L` 无 LLVM/lld/libclang，记录
  每项 OS/C++ 动态依赖；桥及所有归档实际为 arm64 Mach-O。
- [ ] 验证拟新增 `python3 tests/selfhost/llvm-darwin-sdk.py`；`make` 与本平台两门通过。
  Darwin SDK、host、`make`、`make test` 与 `make test-llvm-darwin` 已通过；
  `make selfhost-native` 在继承的 `tests/selfhost/runtime-memory.py` 失败：自编译器仍导入
  C runtime `strlen`。macos-14 CI 候选尚待独立验收，未滚种子。

**关闭：**legacy 产生真实内嵌 LLVM 的 Mac A，Darwin 桥可独立发射/验证对象；
源码级 LLVM 目标发射仍由 F2-2 关闭。无固定包的 legacy 兼容门也须绿。

### F2-2：Darwin 纯计算 IR、对象与汇编

**依赖：**F2-1；使用 emit v2 和 F2-0 的有效部署版本。
**修改：**`backend/llvm_module.yh`、`llvm_bridge.yh`、`cmd/llvm_emit.yh`、桥 v2；
**拟新增：**`compiler/cmd/darwin_link.yh`（配置解析部分，F2-4 再补链接）。
**测试：**扩展 llvm-darwin-target.py，新增
`tests/yh-run/run/llvm-darwin-object.yh`（platform: darwin-arm64）。

- [x] 探针复现并解除 emitter 的 Darwin triple 限制；纯整数、分支、取址局部内存与内部
  调用探针已验证 LLVM 文本目标、逻辑符号和无 Linux syscall 模板。
- [x] 实现部署版本/SDKROOT 会话解析；真实命令覆盖默认值、非法版本、显式无效 SDKROOT
  优先拒绝，以及坏环境下 check 不触碰 SDK。
- [x] 显式接受 canonical Darwin/arm64 目标；未知目标、错误布局/ABI 与 Darwin/x64 仍拒绝。
- [x] Darwin `.ll` 已追加规范化 `yh-macos-min-os` 注释，Darwin 模块对象键已包含同一
  min_os；对象门验证改成 15.0 后 O0/O2 缓存失效并重发对应 LC_BUILD_VERSION。
- [x] v2 按 min_os 创建版本化目标配置与 PIC TargetMachine；对象中的 LC_BUILD_VERSION 与
  `.ll`/对象键一致，target/data layout 不匹配立即失败。
- [x] 检查逻辑符号不预加 Darwin `_`；Mach-O 外部符号只由 LLVM 添加一次。
- [x] 验证 O0/O2 纯文本、对象与汇编；用固定 LLVM 工具读 CPU、段、重定位与版本。
  改 min_os 必须使对象键失效；桥失败不发布新对象。
- [x] `make`、Darwin 定向对象门和 `make test-llvm-darwin` 通过，Mach-O 对象/汇编与链接可运行。
- [ ] 默认本平台 `make test` 与 `make selfhost-native` 两门均通过；当前 `make test` 已通过，
  `make selfhost-native` 在继承基线 `runtime-memory.py` 因导入 `strlen` 失败，见 F2-1。

**关闭：**yh 前端→IR→真实 arm64 Mach-O 对象/汇编，fallback=0；不冒称程序已可运行。

### F2-3：Apple 标量 C ABI 与间接调用

**依赖：**F2-2。
**修改：**`llvm_call.yh`、`llvm_scalar.yh`、`llvm_module.yh`、拟新增 llvm_apple_abi.yh。
**拟新增：**`tests/selfhost/llvm-darwin-abi.py`、`llvm-darwin-abi-probe.yh`、
`llvm-darwin-abi-bridge.c`，以及 `tests/modules/projects/llvmdarwinabi/` 的项目/主模块/桥。

- [x] 新增 Darwin C ABI 标量探针，使用现有语言的 `@[extern]` 属性，未新增语法。
- [x] 按模块目标分派 C 标量支持与窄整型属性；同步声明、定义、直接调用及函数指针调用。
  LLVM 21.1.8 Clang oracle 与 bool、i8/u8、i16/u16、i32/i64、指针、f32/f64 和第 9/10 个
  窄参数签名一致，`opt -passes=verify` 与真实 O0/O2 Mach-O 双向运行通过。
- [x] 同步定义/声明/call site/函数指针与 callback；禁止只修直调。
- [x] 由固定 clang21.1.8 生成等价 C 的 IR/对象，使用临时测试链接驱动将 YH 对象与
  C 桥链接并在 Mac 双向运行，O0/O2 检查负数、边界值和回调结果。测试链接不计生产链。
- [x] F2-3 阶段先明确拒绝 Darwin C 聚合与裸 C 变参；非 HFA 聚合后续按 F2-5 独立实现。
- [x] 验证 `python3 tests/selfhost/llvm-darwin-abi.py --suite full --compiler-path ./yh`。

**关闭：**标量 C 双向互调/间调通过；聚合子集与变参按 F2-5 分开验收。

### F2-4：Mach-O 生产链接、签名和原子发布

**依赖：**F2-2/3；使用 F2-0 配置和 F2-1 raw lld 接口。
**修改：**`cmd/darwin_link.yh`、`link_cache.yh`、`llvm_emit.yh`、`llvm_bridge.yh`。
**拟新增：**`tests/selfhost/llvm-darwin-link.py`、
`tests/yh-run/run/llvm-darwin-link.yh`（platform: darwin-arm64）。

- [x] 首先以 return 0/getpid 等无需自有格式化的程序复现生产路径未接入；保留旧输出。
- [x] 单文件/项目构造一致的 raw lld argv：arm64、platform_version、syslibroot、PIE、
  libSystem、ad-hoc 签名。Darwin 不传 -no-pie；按实际输入处理 `-l` 和库搜索。
- [x] 新增 Darwin worker，沿用一次性 fork、0/-1/-2 及父进程发布；ELF 模板维持原职责。
  内嵌失败不偷偷改用 clang，显式 YH_CC 路径仍有独立标记与缓存身份。
- [x] 校验 Mach-O 类型/CPU/有效版本、`LC_CODE_SIGNATURE`、`codesign --verify` 与实际运行，
  不能只看 magic；成功后 rename，失败保留旧文件和旧成功 manifest。
- [x] SDK/libSystem 缺失、错误架构、lld worker 强制失败、带空格中文路径各有失败注入。
- [x] 验证拟新增 `python3 tests/selfhost/llvm-darwin-link.py --compiler-path ./yh`；
  审计正常 LLVM 链接未启动外部 clang/ld/ld64.lld/codesign。

**关闭：**单文件及多模块纯计算/标量 C 程序可原生运行，完整 runtime 仍未关闭。

### F2-5：Apple 聚合 ABI、HFA、返回与既有变参

**依赖：**F2-3/4。
**修改：**llvm_apple_abi.yh、llvm_zabi.yh、llvm_scalar.yh、llvm_module.yh。
**测试：**扩展 Darwin ABI `.yh/.c` 与项目，复用 autoabi 的类型/边界案例。

- [x] 新增 `.yh`/C 聚合探针，覆盖 1/3/8/9/16/24 字节、混合整数/浮点 union、嵌套 HFA、
  HFA 寄存器耗尽、24 字节按值副本及 sret；固定 Clang oracle 与 O0/O2 双向运行通过。
- [x] 按模块布局实现非 HFA Apple 分类：≤8 字节参数用单个 i64、9–16 字节用双 i64、
  更大对象用间接参数和 sret；定义、声明、调用、参数恢复与返回走独立 Apple 路径，
  不复用 SysV 分片/byval。
- [x] 完成嵌套 HFA 参数/返回的浮点寄存器分类与映射，并覆盖 HFA 参数寄存器耗尽后整体上栈；
  LLVM 21.1.8 Clang oracle 与 O0/O2 实际 C↔YH 互调通过。
- [x] 覆盖聚合函数指针 C callback、C→YH→C 嵌套回调及间接返回函数指针；Clang oracle 与 O0/O2 运行通过。
- [x] 为 prelude `printf` 打通 Darwin 变参调用与目标 `va_list`；用户裸 C 变参、
  非法切片/数组等负例保持原拒绝，不借平台迁移扩语言。需与 F2-6 的 Darwin 格式化 runtime 联测。
- [x] 联合体 HFA 分类：`union { f64; [2]f64; }` 这类全部成员同浮点基型的联合体按 HFA
  走 v0/v1（元素数取最宽成员），参数恢复/返回写回/结果还原三条递归路径同步支持 union；
  漏判会退化成整数聚合使 C↔YH 双向读错字段。已并入 aggregate 探针的 Clang oracle 与
  O0/O2 互调（autoabi 项目的 `FloatUnion` 即此形态）。
- [x] 验证 `python3 tests/selfhost/llvm-darwin-abi.py --suite full --compiler-path ./yh`；
  标量、聚合、HFA、callback 的对象签名与固定 oracle 一致，O0/O2 本机运行通过。

**关闭：**现有受支持 C ABI 的 Apple 形态在声明/定义/直调/间调与双向运行均闭环。

### F2-6：Darwin allocator、格式化和 OS 桥运行验收

**依赖：**F2-4/5。
**修改：**拟新增 llvm_apple_runtime.yh，公共 llvm_runtime.yh 仅增加按输出目标分派。
**拟新增：**`tests/selfhost/llvm-darwin-runtime.py`、
`tests/yh-run/run/llvm-darwin-runtime.yh`；复用 runtimebytes、目录/时钟/进程项目。

- [x] 红例复现 x64 syscall 被用于 Darwin/ARM64 的风险；检查对象中无该指令模板。
- [x] 实现 `llvm_apple_runtime_memory_text(unit *ir.IRModule, out *LLVMOutput) void`；
  allocator 调 mmap/munmap、输出调 write；OS 类型/常量由固定 SDK C 探针锁定。
- [x] 保留 16 字节对齐、零大小分配/free(NULL)、长度溢出、MAP_FAILED、UTF-8 字节、
  write 短写/失败和既有 printf 格式。allocator 不导出 libc malloc/free 名称。
- [x] 内存 helpers O0/O2 无自递归 libcall；Mach-O weak 合并与用户强定义优先通过；
  runtimebytes 无禁止 C 服务导入，允许的 mmap/munmap/write 单列。
- [x] 复验 Darwin 目录、单调时钟、open/fork/execvp/waitpid、中文空格路径及 libs 消费者。
- [x] 验证拟新增 `python3 tests/selfhost/llvm-darwin-runtime.py --compiler-path ./yh`；
  普通程序和内嵌 LLVM 编译器分别做依赖清单，不能放宽程序门迁就 C++ 依赖。

**关闭：**现有运行时与标准库行为完整，两个 profile 原生运行、导入与 helper 门通过。

### F2-7：Darwin SDK、缓存键与失败提交专项收口

**依赖：**F2-4/6；对象身份从 F2-2 已生效，不推迟到本片才补。
**修改：**darwin_link.yh、link_cache.yh、module_build.yh、模块/链接 manifest。
**拟新增：**`tests/selfhost/llvm-darwin-cache.py`、
`tests/modules/projects/llvmdarwincache/`（project.toml 与至少双模块 .yh）。

- [x] 以同路径内容变化、部署版本变化、SDKROOT 切换、目标库替换写失效红例；保持
  有效无改动构建命中，普通函数变化只影响现有实际缓存粒度，不承诺 RS2/RS3 新能力。
- [x] 将有效 min_os/PIC/桥身份入对象键；最终键保存完整 argv、SDK 内容清单、
  实际 stub/库/reexport 闭包、工具和自举归档内容；确定排序与路径规范化。
- [x] SDK 身份不能只用路径/版本/mtime；内容清单校验是会话输入，缓存损坏必须重验，
  不以未校验旧索引证明“未改变”。依赖追踪不足以闭合时使用完整链接输入 SDK 内容清单。
- [x] 失败/取消、已有可执行文件、部分对象/接口损坏、两次并发构建逐项检查原子发布，
  复用现有协议，不另造提交框架。
- [x] 验证拟新增 `python3 tests/selfhost/llvm-darwin-cache.py --compiler-path ./yh`；
  两轮相同有效输入 manifest/IR 确定，无旧配置误命中。

**关闭：**设计要求的输入变化与失败矩阵均有实测，不把只哈希 SDKROOT 当作内容验收。

### F2-8：Darwin LLVM 全量门与原生连续自举

**依赖：**F2-5/6/7。
**修改：**Makefile、native-selfhost.py、selfhost_snapshot_gate.py、CI Darwin 作业。
**拟新增：**`tests/selfhost/llvm-darwin-selfhost.py`、
`tests/selfhost/llvm-darwin-fixedpoint.yh`；Make 目标 `test-llvm-darwin`、`selfhost-llvm-darwin`。

- [x] 先写脚本自测：漏 .ll/接口、错目标/版本、错代号、同目录自比较、错 CPU 必失败；
  产物发现服从当前编译器实际 manifest，兼容正在落地的文件级产物布局。
- [x] 从现有 Darwin 种子 legacy 编 A（含真实桥），A 的 LLVM O0/O2 分别编 B，
  B 编 C、C 编 D；冻结配置保存各代 checked/emitted/rejected/fallback。
- [x] 同 profile 的 B/C/D 输出 `.ll/.s.i/.s.ct` 精确固定点；D 自解析与全量语法、
  运行、模块、项目以及 compiler/libs 消费者通过，fallback=0。
- [x] 增加无系统 LLVM 工具/动态库测试：隔离 PATH、审计真实子进程、otool 导入；
  自举所需固定静态归档与 Apple SDK 可作为输入，但不能调用 SDK 的 LLVM 工具。
- [ ] 在 macos-14 原生执行候选，检查实际运行下限；本机 SDK27/系统27 结果单独记录。
  （CI 作业已接入 `make selfhost-llvm-darwin` 与证据上传；本机 macOS 27 + CLT SDK 26.5 已通过。）
  Darwin CI 仍手动触发，缓存键纳入固定包/桥/SDK/部署版本，上传日志/候选，不自动滚种子。
- [x] 验证拟新增 `make test-llvm-darwin`、`make selfhost-llvm-darwin`；
  legacy 本平台两门继续绿，Linux test-llvm 的平台断言保留。

**关闭：**Darwin 显式 LLVM 路径具备完整原生自举证据（F2-10 随后切默认并覆盖种子）。

### F2-9：Linux/x64→Darwin/ARM64 交叉引导独立验收

**依赖：**F2-0～7、已验收 Linux/x64 LLVM A；推荐在 F2-8 原生通过后执行。
**2026-10-19 进展**：`compiler/darwin-sdk/` 已随编译器分发聚合 libSystem stub
（SDK 26.4），纯 `.yh` 程序交叉链接不再要求 Linux 宿主安装 Xcode/CLT SDK；
C 源、libc++/目标包、frameworks 等仍见
[遗留边界](../03-design/yh-Darwin交叉编译遗留边界.md)。
**修改：**seed-build.py、llvm-host.py 的目标包注入、Darwin lld 参数、CI artifact 传递。
**拟新增：**`tests/selfhost/llvm-darwin-cross.py`、
`tests/selfhost/llvm-darwin-cross-host.yh`、Make 目标 `crosshost-llvm-darwin`。

- [ ] 错误 ELF/架构归档、缺 SDKROOT、Linux 主机误执行 xcrun、B 编入失败桩、绝对
  Linux 路径固化分别加拒绝/行为探针；跨平台源码 emitter 无平台文件后缀过滤。
- [ ] 接受 `--llvm-host darwin-aarch64` 的目标包 manifest；Linux native A 执行生成，
  Mach-O 链接时选择 B 的 Darwin LLVM/桥/支持库，普通程序不注入这些库。
- [ ] 目标包可先由 Mac 构建后搬入 Linux；本片不强制另建 LLVM C++ 全量交叉构建体系。
  记录 build host、B runtime host、输出目标、SDK 与依赖摘要，形成可重放包。
- [ ] Linux 作业生成 B 并上传 artifact；Mac 作业检查签名后运行 B，B→C→D→E 连续
  自编，比较原生连续代固定点、全量门、构建身份和覆盖；交叉代快照另作差分。
- [ ] B 搬到 Mac 后普通编译无 Linux 路径依赖，自举重新定位 Mac 的固定归档/SDK。
  `file`/magic 正确而 B 不能 LLVM 编译 `.yh` 时必须判失败。
- [ ] 验证拟新增 `make crosshost-llvm-darwin`（仅 Linux/x64）及 Mac artifact 后续门；
  本地 Mac 不代跑 Linux 任务，按现有分工由 CI 完成。

**关闭：**可摆脱旧 Mac 种子生成首个候选，且 Mac 原生链证明确有 LLVM 编译能力。

### F2-10：性能、默认后端、发行依赖与 Darwin 种子

**依赖：**F2-8。**2026-10-19 用户决定**：性能项（20 轮对照、RS2 函数级缓存、
RS3 文件级对象、R2c 线程池）全部后置为专门性能工作，本轮只按正确性切默认；
LL11 的“性能不达标即不宣布全量完成”边界继续保留，不在本轮声称关闭。
F2-9 单独标识状态。
**修改：**gen/state.yh、Makefile/默认构建与自举入口、发行/CI 文档、种子与哈希。
**拟新增：**`tests/selfhost/llvm-darwin-default.py`，断言无 `--backend` 时默认走 LLVM。

- [ ] 20 轮性能对照与回退归因——**按用户决定后置**，不属于本轮正确性门；
  实施前不得宣称 LL11 性能门/“首个完整 SSA 版本”完成。
- [x] 无 `--backend` 时实际 emitted=checked、fallback=0；`tests/selfhost/llvm-darwin-default.py`
  同时校验 Darwin LLVM 产物路径、默认 `--emit-asm`/`--emit-llvm` 与可运行产物。
- [x] 切 Darwin 默认 LLVM：`state_init` 为 `DARWIN+ARM64` 置 `c_backend=1`；
  Makefile 对 `LLVM_HOST=darwin-aarch64` 选用 Darwin runtime/cache 门；
  `native-selfhost.py` 自动识别 Darwin LLVM，并支持旧种子 `legacy→LLVM` 过渡代。
- [x] 默认 `make test` 与 `make selfhost-native` 全绿；`make seed` 来源是本机原生
  验收候选（72MB，`2be836b7…`），未复制 Linux A 或未验收交叉 B。
- [x] `bin/yh-darwin-arm64` 与 `.sha256` 已更新；新种子冷编、默认门与关键 `.yh`
  探针通过；失败不覆盖旧种子，旧后端删除仍交 LL12。
- [x] 完成记录落 `docs/01-finished/`，逐片更新 todo/finish、总方案、设计与 ADR 状态。

**关闭：**默认后端、本平台两门、固定点与种子来源均有正确性证据；性能证据后置，
待专门性能工作关闭 RS2/RS3/R2c 与 20 轮对照后再宣布 LL11/F2 全量完成。

## 实施命令与交付方式

以下命令仅在对应新增目标已实现后执行：

```bash
YH_LLVM_HOST=1 make llvm-host
make
make test-llvm-darwin
make selfhost-llvm-darwin
# 默认切换及其前置门完成之后：
make test
make selfhost-native
make seed
```

每片关闭前保存红例、修复与绿例日志，审查该片 diff、接口和文档后独立提交；不把
现有工作区其他任务的改动一起提交。阶段报告需区分“计划交付”“实现完成”“本机
门通过”“CI 门通过”“种子已滚”，不得凭本文复选框或源码存在宣称平台可用。

本计划已按七组差距、交叉引导、五个审查输入类逐项映射切片；首次实施从 F2-0 开始。
