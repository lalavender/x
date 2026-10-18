# macOS/ARM64 切换 LLVM 的剩余差距

日期：2026-10-19。依据：当前 `llvm` 分支工作区、根目录 `yh` 与
`bin/yh-darwin-arm64` 的最小探针。本轮只分析，未修改编译器源码、默认后端或种子。

## 当前结论

macOS 的旧后端种子与日常构建已恢复；LLVM 的公共前端、受检快照、模块 IR、
控制流、聚合和浮点实现已有 Linux/x64 验收。macOS/ARM64 的 LLVM 生产路径仍未接通，
缺口覆盖宿主静态 SDK、目标发射、C ABI、运行时、链接、缓存及自举七组。

因此，补一份 Darwin SDK 或直接放开平台判断都不足以完成迁移。
`gen/target_info.yh` 与 `ir/ssa_module_00_model.yh` 已认识
`aarch64-apple-darwin`，目标元数据无需从头设计；Apple ABI 和系统边界仍需单独验收。

## 最小探针结果

宿主为 Darwin/arm64。探针源仅含 `fn main() int { return 0; }`，存于
`tmp/mac-llvm-audit/minimal.yh`；原始结果在 `tmp/mac-llvm-audit/results.json`。

| 命令/路径 | 结果 | 说明 |
| --- | --- | --- |
| `make llvm-host YH_LLVM_HOST=1` | 退出 2：当前种子没有对应的固定 LLVM SDK | require 开关无法给 Darwin 生成宿主配置 |
| `./yh --backend llvm --target aarch64-apple-darwin --emit-asm tmp/mac-llvm-audit/minimal.yh` | 退出 255：完整目标身份不一致或平台尚不支持 | 尚未进入 LLVM C 桥 |
| 上一命令另加 `--emit-llvm` | 同样拒绝、无文本输出 | Darwin 的纯 LLVM 文本发射也被平台门挡住 |
| 改为 `x86_64-unknown-linux-gnu --emit-llvm --emit-asm` | 退出 0，输出 2012 字节 LLVM 文本 | 公共 lowering 在当前 macOS 编译器中可以执行 |
| 改为 `x86_64-unknown-linux-gnu --emit-asm` | 退出 255：内嵌桥拒绝该模块，诊断缓冲为空 | 能走到桥，但命中 Darwin 失败桩 |

根目录 `yh` 与入库 Darwin 种子的上述汇编发射失败一致。纯文本探针仅证明公共
lowering 可用，不证明 Linux 对象、Darwin 对象或可执行程序已生成。
本轮未重跑全量主门，也未在其他平台预跑门禁。

## 七组待解决问题

### 1. Darwin 宿主静态 SDK 与构建流程缺失

- `vendor/llvm/sdk.lock.json`、`tools/llvm-host.py:40` 只有
  `linux-x86_64` / `linux-aarch64`；`Makefile:153` 也只给 Linux 设置 `LLVM_HOST`。
- `compiler/backend/llvm_bind.darwin.yh:17` 返回 `unavailable-on-darwin`，
  发射与链接入口均是失败桩；必须换成真实 C ABI 绑定并实际链入桥归档。
- 不只是补 hosts 表：`tools/llvm-sdk.py:26` 限制 Linux 构建机，工具链固定 GNU GCC，
  链接配置来自 `collect2`；`:336` 使用 GNU archive group 和 libstdc++ 参数，
  `:439` 使用 `os.memfd_create`、`/proc/self/fd`。宿主注入 shim 也围绕 `gcc` 编写，
  Darwin 驱动当前选的是 `clang`。

关闭标准：固定版本、哈希、静态库与许可的 Darwin/arm64 SDK；按 Darwin 工具链
构建并注入真实桥，编译器运行时不依赖动态 libLLVM 或 LLVM 工具旁车。

### 2. 发射链有两个独立目标阻断

- `compiler/backend/llvm_module.yh:169` 要求 `target.os == TARGET_OS_LINUX`，
  连 Darwin 纯文本 IR 都拒绝。
- `compiler/llvm/bridge.c:81` 白名单包含 Linux 两架构、Darwin/x64 和 Windows/x64，
  **遗漏 `aarch64-apple-darwin`**。即使绕过 emitter 的 Linux 限制并接好 SDK，
  仍会在桥中失败。
- 桥的 TargetMachine 目前固定 `LLVMRelocStatic` / small code model
  （`:109–111`）；需明确 macOS 的重定位、PIE 和最低系统版本政策并验证，
  本轮未将其判定为已复现故障。

关闭标准：真实目标身份贯穿 checked → IR → LLVM 文本 → arm64 Mach-O 对象/汇编；
错误目标、优化配置及失败发布继续受检，不通过改成 Linux 身份规避平台门。

### 3. LLVM 的 C ABI lowering 仍仅支持 SysV AMD64

`compiler/backend/llvm_call.yh:140` 对 C 签名要求 `sysv-amd64`；
`llvm_zabi.yh` 的聚合分片、byval/sret、参数映射也是该 ABI 的实现。
这会阻止编译器调用系统 API、LLVM C 桥及 C 回调，并非只影响少见的聚合参数。

需补 Apple ARM64 标量扩展、固定参数/溢出栈参数、HFA、小/大聚合返回、间接调用、
双向回调和裸 C 变参。LLVM 承担机器指令与寄存器分配，但前端仍须给出正确的物理
LLVM 签名和属性。旧 `gen/abi_c.yh` 已有 Apple ARM64 规则，可作资料与测试来源，
不能视为 LLVM 路径已经接入。

Apple 的变参栈传递与 `va_list` 规则不同于通用 ARM64，见
[Apple ARM64 ABI 文档](https://developer.apple.com/documentation/xcode/writing-arm64-code-for-apple-platforms)。
关闭标准：固定 LLVM 版本 oracle 与原生 yh→C、C→yh 在 O0/O2 双向运行通过。

### 4. LLVM 自有运行时写死 Linux/x64

`compiler/backend/llvm_runtime.yh:145` 发射 x86_64 `syscall` 内联汇编；分配器
使用 Linux 的 mmap/munmap 编号，格式化输出依赖 Linux write。`llvm_module.yh:188`
也明确拒绝非 SysV 目标的部分运行时入口。换 triple 不能使这些代码变成 Darwin 实现。

需为分配、释放、输出和变参建立 Darwin 路径，复验 memcpy/memmove/memset/strlen
在 Mach-O 下的弱符号与优化行为，并审计 LLVM 自动引入的 helper/libcall。
现有 `cmd/project_dir.darwin.yh`、`clock.darwin.yh` 与进程桥可复用，仍须用新的
Apple C ABI 运行验收。采用 libSystem OS API 应沿用仓库的显式导入审计政策。

关闭标准：内存、格式化、目录、时钟、进程与标准库原生运行，分配器命名空间和
未定义符号清单合格，不能只凭无运行时调用的 `return 0` 探针关闭。

### 5. Mach-O 生产链接与签名路径未接入

`compiler/cmd/link_cache.yh:317` 的生产内嵌 lld 仅启用 Linux/x64；
`compiler/llvm/lld_bridge.cpp` 虽注册 Mach-O 驱动，当前默认模板仍是 GNU/ELF。
`tests/selfhost/llvm-lld.py:81` 的 Mach-O 探针使用 **x86_64**、人工给定入口与版本，
不链接 libSystem，也未在 macOS 上运行程序。

需补 arm64、SDK/sysroot、最低 macOS 版本、系统库、入口及 ad-hoc 签名的完整参数。
签名不要求自研：固定 LLVM 21.1.8 的 lld 已有 arm64 默认 ad-hoc 签名测试，见
[上游测试](https://github.com/llvm/llvm-project/blob/llvmorg-21.1.8/lld/test/MachO/adhoc-codesign.s)。
本项目仍须验证最终签名和实际执行。

还有入口不一致：单文件 `llvm_emit.yh:393` 无条件传 `-no-pie`，项目路径在 Darwin
省略该参数；本机 clang 对该参数报 unused warning、仍可链接运行。它是待统一的配置
差异，不是本轮确认的致命链接错误。Darwin 目标架构和 SDK 参数也尚未显式传给该驱动。

关闭标准：单文件与项目都能生成、验证签名并运行 arm64 Mach-O；失败保留旧产物，
内嵌 lld 与允许的平台驱动回落具有明确且可验证的契约。

### 6. Darwin SDK 与实际工具链身份未完整进入缓存

`compiler/cmd/link_cache.yh:486` 已哈希 `SDKROOT` 与
`MACOSX_DEPLOYMENT_TARGET` 环境值，不能说目标身份和环境完全没有入键。
但 `:533` 对 Darwin 跳过 GCC 固定查询，后续默认文件仍是 ELF/GCC 清单，库后缀
仍围绕 `.so/.a`；未建立 Darwin SDK、`.tbd`、实际系统链接器和所选开发工具链的
完整输入发现。当前工具哈希本身也不能代替默认 SDK 内容身份。

风险判断：默认 SDK/开发工具链或同路径 SDK 内容变化时，旧链接产物可能被误复用；
本轮未实施真实 SDK 切换复现实验。需收口 SDK 版本/内容摘要、有效部署版本、真实
工具链与链接参数，并验证 SDK/库变化导致失效。对象代码生成会读取的目标版本等
信息也须进入对象层身份，而不只进入最终链接键。

### 7. Darwin LLVM 全门、原生自举与种子尚未建设

- `Makefile:297` 的 `test-llvm` 明确要求 Linux/x64。
- `tests/selfhost/llvm-selfhost.py:19` 固定 Linux ARM64 启动种子、Linux/x64 triple，
  候选验证使用 ELF/readelf；尚无 Darwin LLVM O0/O2 的连续自编和固定点门。
- `tests/selfhost/native-selfhost.py:50` 对非 Linux 种子不注入 LLVM 桥；现有 macOS
  `selfhost-native` 验证旧 ARM64 后端。Darwin CI 也只执行默认构建和该主门。

关闭标准：Darwin LLVM O0/O2 原生语言、模块、项目和实际消费者全覆盖，
连续自编 `.ll/.s.i/.s.ct` 固定点、fallback=0、无动态 LLVM/工具旁车、签名/导入
清单及至少 20 轮性能对照通过；默认本平台 `make test` / `make selfhost-native`
全绿后才按既有规则滚 Darwin 种子。

## 建议实施顺序与已有硬门

1. Darwin 静态 SDK/宿主注入 + 目标支持：验收纯计算 `.yh` 到 arm64 Mach-O 对象。
2. Apple 标量 C ABI + 平台链接：原生运行最小程序并验证签名。
3. 完整 C ABI + Darwin runtime：双向 ABI、标准库、进程和 I/O 全绿。
4. SDK/缓存/失败发布专项：配置切换、损坏缓存和失败保留全绿。
5. Darwin LLVM O0/O2 全量与自举：固定点、覆盖、依赖、性能门完成后再切默认与滚种子。

这是 F2 内部的建议切片，未改变已确认的 Linux/x64 → Linux/AArch64 → macOS/ARM64
平台顺序。公共 LL11 尚有性能、默认切换与种子交付待办；`todo.md` 同日决定还要求
R2b 剩余与 R2c 全部关闭。这些属于正式默认切换硬门，不等同于不能先做 macOS
显式 LLVM 路径。LL12 删除旧后端仍依赖 LL11 与 F1，不能因 Darwin 探针通过提前删除。

## 补充：由 Linux/x86_64 自举编译器交叉引导 macOS

结论：**技术上可行，当前仓库还不能直接执行这条生产链**。Linux/x64 自举提供
可用的启动编译器，Darwin 发射、Apple ABI、运行时与目标依赖仍须完成。交叉构建
成功后可以不再依赖旧 macOS 种子来生成第一代候选，但原生自举验收仍在 Mac 上完成。

### 构建机、编译器运行平台与代码生成目标

设 A 是已在 Linux/x64 自举的 yh；B 是希望产出的 macOS/ARM64 yh。

| 阶段 | 实际执行程序的平台 | 此次输出 | 使用的 LLVM/桥 |
| --- | --- | --- | --- |
| A 编译 `compiler/` | Linux/x64 | B 的 Darwin/ARM64 Mach-O 对象 | A 中的 Linux/x64 LLVM/桥执行 AArch64 代码生成 |
| 为 B 链接 | Linux/x64 | macOS/ARM64 可执行文件 B | Linux 可执行的 Mach-O 链接器，输入 Darwin/ARM64 LLVM/桥静态库及目标 SDK |
| B 编译程序或自身 | macOS/ARM64 | 缺省为 Darwin/ARM64 对象与程序 | 已链接进 B 的 Darwin/ARM64 LLVM/桥 |

LLVM 库的机器码由“编译器在哪里运行”决定；库内支持哪些代码生成目标另由构建配置
决定。Linux ELF 版 LLVM 即使支持 AArch64/Mach-O 发射，也不能作为 Darwin Mach-O
库链接进 B。LLVM 官方的[交叉构建说明](https://llvm.org/docs/HowToCrossCompileLLVM.html)
明确区分 LLVM 运行平台的 `LLVM_HOST_TRIPLE` 与其支持的代码生成目标。

### 目标依赖如何准备

必须准备 Darwin/ARM64 版本的 LLVM 静态组件、桥归档；若 B 要内嵌 lld，还包括对应
lld 静态组件，以及所需 C++/压缩等依赖和 macOS SDK/sysroot。这些产物可以先在 Mac
构建后交给 Linux 使用，也可另建完整的 Linux→Darwin C/C++ 交叉构建流水线。
后者需要独立配置并验证，当前脚本没有实现。yh 只编译 `.yh`，LLVM 与 C/C++ 桥仍由
固定 C/C++ 工具链构建；准备依赖不要求把 LLVM 源码转成 yh。

交叉链的 LLVM 发射仍在 yh 进程内进行；C/C++ 工具仅用于依赖的预构建。
仅准备 Linux 头文件和库不够，参见
[Clang 交叉编译文档](https://clang.llvm.org/docs/CrossCompilation.html)。

### 现有实现能复用与必须补齐的部分

- **已有基础**：`target_select` 与 `c_host_target` 分离；A 运行时仍用 Linux 的
  文件/进程接口，构建 B 时的 `$if`、源后缀筛选和 B 的固化宿主身份按 Darwin
  目标选择。`compiler/cmd/project_index.yh:516` 与 `gen/target_info.yh:41`
  已提供相关机制；桥中也已注册 X86/AArch64 LLVM 目标。
- **前述七组平台缺口仍存在**，尤其是 emitter 平台门、桥 triple 白名单、Apple
  C ABI 和 Darwin runtime。交叉构建不会自动补齐这些能力。
- **B 的桥绑定**：按目标构建 B 会选入 `llvm_bind.darwin.yh`，当前仍是失败桩。
  必须替换成真实绑定并链接 Darwin 归档，否则即使造出可运行 B，其 LLVM 发射也不可用。
- **交叉依赖注入**：`tools/seed-build.py:67` 只接受 Linux LLVM 宿主包；当前
  `YH_LLVM_SELFHOST` 在 `lld_bridge.cpp:153` 追加的是构建时固化的 GNU 链接参数。
  为 B 链接时须选择 B 的 Darwin 库与 Mach-O 参数，不能沿用 A 的 Linux 库。
  Linux 侧也不能依赖执行 macOS 的 `clang`/`xcrun` 等工具来完成链接。
- **B 的默认后端另行配置**：A 的 `--backend llvm` 只控制此次构建所用代码生成器。
  当前 `gen/state.yh:278` 中新编译器的缺省后端仍为 legacy；B 内嵌 LLVM 能力与
  B 缺省选择 LLVM 是两个验收项，切默认继续遵守既有硬门。

### 引导链与验收

建议候选链为：Linux A 交叉产 B → Mac 上 B 原生编 C → C 原生编 D → D 再编 E。
每代均使用同一目标、优化配置及固定 SDK；O0/O2 分别记录覆盖与原生产物。
以原生代的 `.ll/.s.i/.s.ct` 精确固定点及全量语料为主门；交叉代 B 与原生代 C
也保留快照作差分，但不让构建宿主差异掩盖原生固定点问题。未验收 B 留在 `tmp/`，
不能直接覆盖 `bin/yh-darwin-arm64`；本轮未在 Linux 执行交叉构建或在 Mac 运行该候选。

Linux/AArch64 LLVM 自举不是这条 Linux/x64→Darwin/ARM64 技术链的必要中间步骤。
现有 F1 先于 F2 是项目排期，本次分析没有更改该顺序。若只追求尽快得到 Mac LLVM
编译器，现有 Darwin 种子配合 Darwin 静态 SDK 先原生构建候选，所需新增交叉构建
配套更少；Linux 交叉链则适合统一发布与建立独立于旧 Mac 种子的引导来源。
