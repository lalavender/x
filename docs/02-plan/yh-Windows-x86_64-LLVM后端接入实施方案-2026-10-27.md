# yh Windows/x86_64 LLVM 后端接入实施方案

> **2026-11-06 口径更新**：`arch-check` 已取消代码行数预算（`max_file_lines`、`max_function_lines`、`max_*_lines`、`max_cmd_share_pct`）；本文中的行数目标保留为历史设计指标，不再作为门禁。代码规模只由 `just code-stats` 报告。

> 执行状态（2026-10-27）：用户立项「开始规划 Windows x86 后端，本机刚好可以验证」。
> **本文件只做方案与切片划分，尚未修改任何 `compiler/` 源码**；§3 的三个决策未确认前
> 不开工。已确认/否决的决策请直接在本节改写，并把切片勾选进度同步到 `docs/todo.md`。
>
> **本机角色（已实机核对）**：本机是 Windows 11 / x86_64（MSYS2 + Git Bash），带
> LLVM 21.1.8 全套工具（`clang`/`lld-link`/`llvm-dlltool`/`llvm-readobj`）、
> Windows SDK 10.0.22621 导入库、MSVC 14.41、cmake 4.1.2；WSL2 已启用（`DefaultVersion=2`）
> 但**尚未注册发行版**（`wsl -l -v` 报无已安装分发版）。因此：
>
> 1. **现在就能做**：运行 `.exe`、ABI oracle 差分、生成导入库、构建 windows-x86_64
>    静态 LLVM SDK；
> 2. **装完 WSL Ubuntu（§5 W0-1）后就能做**：本机编译侧闭环（`bin/yh-linux-arm64`
>    种子经 qemu 运行 → 交叉产 `.exe` → `/mnt/c` 侧直接跑），W1 不再需要外机；
> 3. 仓库本地无 `bin/` 种子与 `tmp/llvm-migration` 闭包（需 `just fetch-seed` /
>    `just llvm-host`）。

**目标：**让 yh 产出可在 Windows/x86_64 原生运行的可执行文件，并最终让编译器自身在
Windows 上原生构建、自举、滚种子，接入 `just` 与 CI 的四端矩阵。

**架构：**不新增指令选择/寄存器分配——LLVM 已能为 `x86_64-pc-windows-msvc` 出 COFF
对象，内嵌 lld 已带 COFF 驱动。真正要做的是「目标身份 + Win64 ABI 门 + Windows 运行时与
入口 + PE/COFF 链接模板与导入库 + 宿主 OS 桥」。

**技术：**yhw 受检快照 → 模块 IR → 内嵌 LLVM 21.1.8（COFF 目标）→ 内嵌 lld COFF
（`lld::WinLink`）；零 CRT 运行时（kernel32 导入）；Python 门禁与跨机执行。

**设计依据：**[LLVM 后端替换设计](../03-design/yh-LLVM后端替换设计.md)、
[LLVM 目标身份设计](../03-design/yh-LLVM目标身份设计.md)、
[ADR-0014](../adr/0014-yh采用LLVM作为正式代码生成后端.md)、
todo 中既有条目 **B1 Windows/x86_64**。

---

## 0. 结论摘要

Windows/x86_64 **不是「再接一个后端」，而是「补齐一个目标 + 一套宿主桥」**，且必须
分成两个交付面，否则会把「能在 Windows 跑」与「能在 Windows 上编译」混为一件事：

| 面 | 含义 | 本机能否验收 | 切片 |
| --- | --- | --- | --- |
| **T 面（target）** | Linux/macOS 宿主编译出 Windows `.exe`（交叉目标） | ✅ 能运行 `.exe` 核对行为 | W1 |
| **H 面（host）** | 编译器自身在 Windows 原生运行/自举/滚种子 | ✅（需先有 W1 交叉出的 `yh.exe` 当种子） | W2 |

关键判断（依据见 §1）：**W1 的代码量小、风险集中在 ABI 细节与运行时/导入库；W2 的
真正难点不是 Windows API，而是 `fork`**——并行模块 worker、lld 子进程 worker、
`cmd_process_capture` 全部依赖 `fork`/`dup2`/`waitpid`，Windows 没有等价物。

---

## 1. 现状核实（2026-10-27 实机核对，非推测）

### 1.1 已经具备的地基

| 能力 | 证据 |
| --- | --- |
| 桥的目标白名单**已含** `x86_64-pc-windows-msvc` | `compiler/llvm/bridge.c:112–121` |
| 内嵌 lld **已有 COFF 驱动**并注册 | `compiler/llvm/lld_bridge.cpp:19–21`（`LLD_HAS_DRIVER(coff)`）、`:191`（`{lld::WinLink, &lld::coff::link}`） |
| `lldCOFF.a` 已在三端闭包里 | `compiler/project.toml` 的 `lld = [...]` 三个目标节均含 `liblldCOFF.a` |
| **COFF 链接已有通过的门禁探针**：出 `x86_64-pc-windows-msvc` 对象 → `lld-link /entry:main /nodefaultlib` → 断言 PE `machine=0x8664` | `tests/selfhost/llvm-lld.py:95–121, 303–312` |
| 构建目录**按 triple 隔离**，同一工作树里 linux/windows 交叉构建不会互相污染 | `compiler/build/module_build.yh:149`（`.build/targets/<triple>/llvm/O<n>`） |
| 目标身份是可扩展的数据表 | `compiler/gen/model.yh:527–541`（`TargetInfo` + `TARGET_OS_*`/`TARGET_ARCH_*`）、`compiler/gen/target_info.yh` |
| 平台专属源文件按后缀筛选，可加 `.windows.x64.yh` | `compiler/build/project_index.yh:575`（`pj_source_target_match`） |
| 运行语料有「平台标签」机制（不匹配记 SKIP） | `tests/yh-run/check.py:79, 211–236`（`// platform:` / `host_platform_tag`） |
| 链接输入与缓存身份已有成熟钩子（`mb_mix_file_identity`、`li_prepare`、`mb_write_manifest`） | `compiler/build/link_inputs.yh`、`compiler/build/link_cache.yh` |

### 1.2 缺口（按面归类，逐条对应 §6/§7 切片）

| 缺口 | 位置 | 切片 |
| --- | --- | --- |
| 目标表没有 windows triple / `TARGET_OS_WINDOWS` | `gen/target_info.yh`、`gen/model.yh` | W1-1 |
| 目标标记 `$if (windows)` 与文件后缀标签不认识 `windows` | `comptime/ct_target.yh`、`build/project_index.yh` | W0-2 |
| 后端目标白名单只放 Linux 任意 / Darwin-arm64 | `backend/llvm_module.yh:159–166` | W1-2 |
| C ABI 分类器只有 SysV 与 Apple（无 Win64） | `backend/llvm_call.yh:163+`、`llvm_zabi.yh`、`llvm_apple_abi.yh` | W1-2 |
| 运行时只有 Linux syscall 版与 Apple 版（`malloc`→`mmap`、`printf`→`write`） | `backend/llvm_runtime.yh`、`llvm_apple_runtime.yh` | W1-3 |
| 没有 PE 的「入口/子系统」概念 | 链接模板（`lld_bridge.cpp` 的 `YH_LLD_LINK_TEMPLATE`） | W1-3/W1-5 |
| 没有任何导入库（kernel32 等） | 无（`compiler/darwin-sdk` 有 Mach-O 对应物 `libSystem.tbd`） | W1-4 |
| `mb_object_machine_matches` 只认 ELF/Mach-O | `compiler/build/link_cache.yh:47–72` | W1-5 |
| `[link-windows-x64]` 节目前是**非法**节（而且被 linkbad 用例拿来当负例） | `build/project_link.yh:74–98`、`tests/modules/projects/linkbad/project.toml` | W1-6 |
| 库格式校验只认 `.a/.so/.dylib/.tbd` | `build/link_inputs.yh:318–330, 387–420` | W1-6 |
| 宿主身份在 Windows 上会错选 linux（`$if (darwin) … $else`） | `gen/target_info.yh:44–55` | W2-1 |
| 宿主 OS 桥全是 POSIX（`open` 常量 `0x241/0x601`、`fork/execv/waitpid/dup2`、`getpid`、`FindFirst` 缺失） | `build/process.yh:83–160`、`build/llvm_pipeline.yh:136`、`build/module_build.yh:831`、`build/build_scheduler.yh:59` | W2-3/W2-4 |
| 没有 windows-x86_64 宿主的 LLVM/lld 静态 SDK 条目 | `vendor/llvm/sdk.lock.json`、`tests/selfhost/llvm-host.py:43` | W2-2 |
| `just`/取种/CI 不认识 windows 宿主 | `justfile:host_os/seed_platform/llvm_host`、`.gitea/workflows/ci.yml` | W2-5 |

---

## 2. 范围与非目标

**范围**

1. W1：`--target x86_64-pc-windows-msvc` 从 Linux/macOS 交叉产出**可原生运行**的
   `.exe`（对象、链接、运行时、入口、导入库、PE 校验、诊断、门禁）。
2. W2：编译器自身在 Windows/x86_64 原生构建、固定点自举、滚种子 `bin/yh-windows-x64`。
3. W3：CI 四端矩阵、发布资产、Windows/ARM64 预留。

**非目标（本轮明确不做，避免把平台接入伪装成几行改动）**

- mingw 目标（`x86_64-w64-windows-gnu`）、Windows/ARM64、ARM64EC、32 位 x86。
- 依赖 MSVC 运行库（`libcmt`/`msvcrt`/UCRT）与 `/MD` 语义；也**不打包**微软 SDK
  二进制进仓库。
- Windows 上的 Unicode（UTF-16）路径语义、长路径（>260）、盘符/UNC 的完整支持——
  首版只要求 `C:/...` 与相对路径可用，边界写进设计文档。
- GUI 子系统（`/subsystem:windows`）、DLL 导出、SEH/异常、`__try`、调试信息（PDB）。
- 性能优化（W1/W2 只要求 O0/O2 正确与固定点）。

---

## 3. 决策（2026-10-27 用户确认：按推荐执行）

> **状态：已冻结。** 用户 2026-10-27 确认 D1 = `x86_64-pc-windows-msvc`、D2 = 零 CRT、
> D3 = W1 交叉目标先行 → W2 原生宿主。以下保留取舍过程，便于后人对账；
> 若要改 D1 为 mingw，§6/W1-4/W1-5 需重写。

### D1 目标 ABI 方言：`x86_64-pc-windows-msvc`（**已确认**）

| | MSVC（推荐） | MinGW |
| --- | --- | --- |
| 桥白名单 | ✅ 已有（`bridge.c:119`） | ❌ 需加，且 lld 需换 `lld::MinGW` 驱动 |
| 链接器 | ✅ `lld::WinLink` 已注册，且已有通过的门禁探针 | ❌ 需注册 MinGW flavor |
| 与 C/C++ 生态互操作 | ✅ 与 MSVC 编译的 `.lib`/DLL 直通 | 与 MSVC `.lib` 不能互链 |
| 运行库 | 需 UCRT（本项目选择**不用**，见 D2） | `msvcrt.dll` 是系统自带 |
| 导入库来源 | Windows SDK 或自造 `.def`→`.lib`（已实测） | mingw-w64 导入库（可自由分发） |
| 结论 | **首版选 MSVC**；mingw 作为后续「完全离线交叉」选项单独立项 | |

推荐：**`x86_64-pc-windows-msvc`**。理由：地基已经在这条路上（白名单 + COFF 驱动 +
探针），且它是 Windows 上 C/C++ 互操作的事实标准。

### D2 运行库策略：零 CRT（**已确认**）

| | 零 CRT（推荐） | UCRT |
| --- | --- | --- |
| 依赖 | 只依赖 `KERNEL32.dll`（系统组件，无需分发） | 需 `ucrtbase.dll` + 一整套导入库（授权/版本/分发复杂） |
| 入口 | `/entry:main`（**已实测**：`main` 返回 7 → 进程退出码 7） | 由 `mainCRTStartup` 提供 |
| 运行时 | 自发射：`malloc`→`HeapAlloc`/`VirtualAlloc`、`printf`→`GetStdHandle`+`WriteFile`、`exit`→`ExitProcess` | 直接 declare `printf`/`malloc` |
| 风险 | 需自己维护 Win32 调用面（首版只要 6–8 个函数） | 与「无旁车、可复现、闭包自足」原则冲突 |
| 结论 | **首版零 CRT**；等真正需要 C 库互操作（W3+）再评估 UCRT | |

已实测支撑（见附录 A）：`/nodefaultlib /entry:main` 的最小 PE 能运行且退出码正确；
`llvm-dlltool` 从 `.def` 生成的 1.7 KB `kernel32.lib` 能解析 `__declspec(dllimport)` 调用。

### D3 阶段顺序：先 W1 交叉目标、再 W2 原生宿主（**已确认**）

- 先 W1 的理由：本机能立刻验收产物行为；W1 的产物 `yh.exe` **就是 W2 的启动种子**
  （见 §4 顺序约束）；W1 不需要 LLVM Windows SDK（最大件）。
- 直接做 W2 的代价：一次性引入「宿主 OS 桥 + 进程模型重写 + LLVM Windows SDK +
  just/CI」，四个大变量叠加，失败无法定位。

**确认结论**：D1 = MSVC ABI、D2 = 零 CRT、D3 = W1 → W2。并行编排见 §12。

---

## 4. 顺序约束（硬约束，违反会锁死种子）

### 4.1 `$if (windows)` 必须晚于「学会识别 windows 的种子」

`comptime/ct_target.yh` 只识别 `linux/darwin/arm64/x64`（`ct_target_symbol`），而**编译
编译器源码的是种子**。因此：

1. **W0-2a** 先只在 `ct_target.yh` 增加 `windows` 标记解析 + `project_index.yh` 增加
   `windows` 后缀标签，**源码里不出现任何 `$if (windows)` 使用点**；
2. 走正常流程 `just test` + `just selfhost-native` → `just seed`；
3. 之后（W2-1）才允许在 `gen/target_info.yh`、`build/*.windows.*.yh` 使用 `$if (windows)`。

### 4.2 同一个坑：`*.windows.yh` 文件名在 W0-2a 之前会被**所有**目标编入

`pj_source_target_match`（`project_index.yh:575–596`）遇到不认识的后缀段直接返回 1
（接受）。所以在标签白名单扩好之前新增 `xxx.windows.x64.yh`，会同时进入 linux/darwin
构建。**W1 的所有平台专属文件必须先落 W0-2a。**

### 4.3 第一个 Windows 种子只能来自 W1 交叉产物

本机不能执行 Darwin/Linux 种子（无 `bin/`、无 WSL 发行版），所以 `bin/yh-windows-x64`
只能由「Linux/macOS 宿主 + W1 交叉目标」编出的 `yh.exe` 反哺生成（W2-6）。这也意味着
W1 必须能交叉编译**编译器自身**（它用到的 prelude 面比普通程序大得多，见 W1-3）。

### 4.4 接口文件（`.s.i`）头行只有 arch，没有 os

`parse/iface.yh:199, 455, 505` 的头行是 `// yh-iface vN arch=<x64|arm64> suffix=…`。
linux-x64 与 windows-x64 共享 `arch=x64`，理论上可以互相加载接口文件。当前靠
`.build/targets/<triple>/` 目录隔离（`module_build.yh:149`）避免错配；W1 需要**确认**
隔离对所有接口/对象读取路径生效（`li_prepare`、接口缓存、函数 IR 缓存），并在设计文档
里写明「跨目标不复用接口缓存」；真要跨目标共享时另立「头行加 os」的迁移项。

---

## 5. W0 前置（无代码或极小代码，先做完再谈 W1）

- [x] **W0-1 编译环境：WSL —— 已完成（2026-10-27）**。实际落地与最初的
  「arm64 种子 + qemu + 交叉 gcc」计划**不同且更简单**：
  - 发行版 `Ubuntu-26.04`（x86_64，16 核/15 GB）；种子用**原生 `linux-x86_64`**
    （release 0.0.10 自带该资产）→ **无需 qemu、无需交叉 gcc**；
  - 工具：`just 1.45`、`build-essential`(gcc/g++ 15)、`clang 21.1.8`、`gcc-13/g++-13`、
    `python3 3.14`、`git 2.53`、`strace`（诊断用）；
  - **5 项环境适配**（都是「种子/门禁的期望」与 26.04 的差异，**不是仓库代码问题**；
    命令与副作用见 `docs/finish.md` 的 W0-1 条目）：
    1. 网络：Clash fake-IP 绕不进本地 TUN → 用 mixed 端口 `127.0.0.1:7897`
       （`/etc/apt/apt.conf.d/99-yh-proxy` + `/etc/profile.d/99-yh-proxy.sh`）；
    2. `libxml2.so.2` 兼容软链（种子按 24.04 构建，26.04 只有 `.so.16`）——**临时**，
       长期解法是换 24.04 发行版或重发布种子；
    3. `gcc-13`（种子烘焙的 `crtbegin/crtend` 路径 `/usr/lib/gcc/x86_64-linux-gnu/13`）；
    4. `clang`（`tests/selfhost/runtime-memory.py` 的导入审计硬要求 `/usr/bin/clang`）；
    5. `XDG_RUNTIME_DIR` 指向可执行目录（`/run/user/<uid>` 是 `noexec`，just 的
       shebang 配方会写在那里，`execve` 得到 `EACCES`）。
  - **实测数字**：`just llvm-host` 99 s、冷编 `just` 37 s、`selfhost-native` 321 s（首轮）/
    360 s（新种子后），项目用例 133/133。
  - **已知缺口**：ANTLR 参考语法层未跑（需 Java + antlr4 jar + 硬编码 macOS venv），
    与 CI 2026-10-26 的取舍一致；其余全部层已绿。
- [x] **W0-2a 目标标记两代顺序 —— 已完成并滚种子（2026-10-27）**：
  - `gen/model.yh`：`TARGET_OS_WINDOWS = 3`；
  - `comptime/ct_target.yh`：`ct_target_symbol` 认 `windows`；
  - `build/project_index.yh`：`pj_source_target_match` 认 `windows` 后缀标签；
  - 用例：`tests/yh/positive/74-comptime-target-marker.yh`（语法形态）与
    `tests/yh-run/run/207-target-marker-exclusive.yh`（OS/架构标记各恰好命中一个，
    平台无关）；
  - `arch-check`：`max_build_lines` 10807 → 10809（+2，目标表必要分支，已写明理由）；
  - 种子 `5ef7612e…` → `0757ebcc…`；新种子重跑 `just selfhost-native` 360 s 全绿。
  - **从这一步起**：源码可以写 `$if (windows)`、也可以加 `*.windows.*.yh` 平台文件。
- [ ] **W0-3 决策冻结**：D1/D2/D3 已写入 §3（2026-10-27，状态见 §3 首行）。
- [ ] **W0-4 文档卫生（顺手，不阻塞）**：多份既有文档把「Windows」写成了「n」
  （如 `03-design/yh-LLVM后端替换设计.md`「n：MSVC 目标路线」、`02-plan/yh-LLVM后端
  替换实施方案.md:…F3 n/x86_64`）。W1-8 落设计文档时一并订正，避免新文档跟着错。

---

## 6. W1 交叉目标切片（Linux/macOS → Windows/x86_64）

> 每片顺序固定：先加 `tests/` 红例 → 最小实现 → `just` → 定向门；片内不改无关代码。
> 片关闭时本平台 `just test` + `just selfhost-native` 全绿（Windows 相关门按 §9 判定）。

### W1-1 目标身份（`TARGET_OS_WINDOWS` + triple 表）

> **状态：已落地（2026-10-27）**。坑：目标身份在 `ir/ssa_module_00_model.yh` 有第二份
> 静态表（key 1–4），不补会在 lowering 静默返回 -1；已补 key=5。

- `gen/model.yh`：`pub const TARGET_OS_WINDOWS int = 3`（注释写明与 `LINUX/DARWIN` 同为
  「输出目标身份」，宿主身份另存 `c_host_target`）。
- `gen/target_info.yh`：`target_resolve("x86_64-pc-windows-msvc")`：

  ```text
  triple      = "x86_64-pc-windows-msvc"
  os          = TARGET_OS_WINDOWS
  arch        = TARGET_ARCH_X64
  abi         = "win64-msvc"
  data_layout = "e-m:w-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
  pointer_bits = 64, little_endian = 1, layout_version = 1
  ```

  （`data_layout` 是 2026-10-27 用本机 `clang 21.1.8 --target=x86_64-pc-windows-msvc`
  实测核对值，见附录 A-1；不要手抄别处。）
- `target_select_os_arch`：windows×x64 分支；windows×arm64 明确返回 -1（W3 才开）。
- `target_arch_token`（`gen/target.yh:60`）返回 `x64`，无需改；**不要**因为 windows 改动
  接口头格式（见 §4.4）。
- `tg_dialect`：Windows 既非 GNU 也非 Darwin，但 LLVM 路径下方言只剩两处消费者
  （链接缓存键 `'D'/'L'`、`mb_select_linker` 默认 `cc`）。W1 先按「不是 darwin」处理，
  并在 W1-5 把缓存键改成显式目标身份串（避免将来第三种方言误命中）。

**验收**：`yh --target x86_64-pc-windows-msvc --syntax-check t.yh` 通过；
`yh --target x86_64-pc-windows-msvc --emit-asm t.yh` 出 COFF 汇编（`llvm-readobj`
不需要，只看 `.s` 头 `target triple`）；`yh --target aarch64-pc-windows-msvc` 明确拒绝。

### W1-2 Win64 ABI 与后端门

> **状态：已落地（2026-10-27，W1-2b 未做）**。clang oracle：i8/i16 **无** signext/zeroext；
> ≤8 字节按值聚合被强制成 `i64`，故 W1-2b 前明确拒绝聚合。

- `backend/llvm_module.yh:156–167`：目标白名单加 `WINDOWS × X64 × abi=="win64-msvc"`。
- `backend/llvm_call.yh`：
  - 新增 `llvm_abi_is_win64(unit)`；
  - `llvm_abi_supported` 的 `ABI_C` 分支：**首版只放行标量 + 指针 + 函数指针**；
    按值聚合（struct/union/数组/切片）返回 0 → 由既有诊断路径给出
    「Windows 目标的 C 按值聚合暂不支持」；
  - prelude 裸变参白名单：`printf` 放行（运行时由我们自己发射，见 W1-3）；`open`
    在 Windows 上不存在（首版拒绝，W1-3 再决策）；
  - `llvm_abi_attr_kind`：Win64 窄整数是否需要 `signext/zeroext` **用 clang oracle 定**
    （`clang --target=x86_64-pc-windows-msvc -S -emit-llvm` 观察它给 `declare i8/i16`
    写什么属性），不靠猜；结论写进设计文档。
  - **不动** yh 内部 ABI（`IR_ABI_YH_LLVM_V1`）：聚合已有隐藏指针/内存路径，与平台无关。
- **W1-2b（可选，第二波）** Win64 聚合分类器：≤8 字节的 struct/union 走单寄存器
  （INTEGER/SSE），>8 字节一律按引用；实现后放开 C 按值聚合。
- **验收**：新增 `tests/selfhost/llvm-windows-abi.py`——同一批签名分别由 yh 与 clang
  出 `.ll`，比对参数/返回类型、属性、调用约定；再出 `.obj` 用 `llvm-readobj` 比对
  符号名（Win64 x64 **无** `_` 前缀）与 `__imp_` 形式。

### W1-3 Windows 运行时与入口（拟新增 `backend/llvm_windows_runtime.yh`）

> **状态：已落地（2026-10-27）**，含 W1-3b 的 `read`/argv/`exit`：
> 实测三处 MSVC ABI 细节：需自定 `@_fltused`；非入口块 alloca 会引 `__chkstk`
> （并导致聚合实参崩溃，已把全部 alloca 提升到入口块）；`declare`+`define` 同名非法，
> 故运行时提供的 `write`/`read` 在声明阶段跳过、`exit/_Exit` 只声明并由链接期
> `/alternatename` 解析到 ExitProcess。入口为 `/entry:mainCRTStartup`（argv 由
> GetCommandLineA 解析后转发）。

分工照抄 `llvm_apple_runtime.yh`（平台运行时单独成文件，由 `llvm_runtime.yh` 的入口按
目标分派），保持「weak 定义 + `llvm.used` + `optnone/noinline/nobuiltin`」纪律。

| 符号 | Windows 实现 | 备注 |
| --- | --- | --- |
| `__yh_runtime_malloc` / `_free` | `HeapAlloc(GetProcessHeap(),0,n+16)` / `HeapFree` | 头部 16 字节存原尺寸，保持现有 `free` 契约 |
| `printf` | `GetStdHandle(-11)` + `WriteFile` | UTF-8 直写；不做 CRLF 翻译 |
| `write(fd,…)`（prelude） | `fd 1/2` → `GetStdHandle`；其余 fd 首版拒绝 | 与 POSIX fd 语义的差异写进设计文档 |
| `exit(code)` | `ExitProcess(code)` | |
| `__yh_test_assert` | 复用现有实现，输出改走 `WriteFile` | |
| `open/read/close/mkdir/unlink/rename/getpid/fork/execv/waitpid/dup2` | **首版不支持** | 必须在前端/后端给目标诊断（「Windows 目标暂不支持 <name>」），不允许拖到链接期 undefined |

- **入口**：不发射 `mainCRTStartup`——已实测 `/entry:main` 返回即进程退出码（附录 A-2）。
  若后续需要 `argc/argv`（Win64 入口没有参数），再单独做 `GetCommandLineA` 解析。
- **验收**：`tests/yh-run/` 新增 `// platform: windows-x64` 用例（打印、整数、循环、
  字符串、结构体取址、浮点、`assert`），交叉产 `.exe` → 本机执行核对 stdout/退出码；
  未支持入口的负例断言诊断文本。

### W1-4 导入库与 Windows SDK stub（拟新增 `compiler/windows-sdk/` + `tools/windows-sdk.py`）

> **状态：已落地（2026-10-27，lane B）**。产物：`compiler/windows-sdk/{def/kernel32.def,
> manifest.json,README.md}`、`tools/windows-sdk.py`（generate/check/paths）、
> `tests/selfhost/llvm-windows-sdk.py`（四件事：清单↔def、两次生成字节相同、符号面
> `X`+`__imp_X` 且无多余、链接探针只依赖 KERNEL32 且在 Windows 上实跑）。
> `just windows-sdk` / `just test-windows-sdk` 已可用。
> **仍未做**：编译器侧消费（`build/windows_link.yh` 的查找顺序与 `kernel32.lib` 注入 =
> W1-5）、CI 接线（W1-7）。

对齐 `compiler/darwin-sdk/`（文本 `.tbd` + manifest + 查找顺序）的做法，但 Windows 的
导入库是 COFF 归档而非文本，所以：

- 仓库只放**文本** `.def`（`LIBRARY KERNEL32.dll` + `EXPORTS` 最小面）与
  `manifest.json`（版本、来源、每个 `.lib` 的 sha256）；
- `tools/windows-sdk.py`：`llvm-dlltool -m i386:x86-64 -d x.def -l x.lib` 生成到
  `tmp/llvm-migration/windows-sdk/lib/`（已实测：1.7 KB/个，`lld-link` 直接可用）；
  宿主没有 `llvm-dlltool` 时回退仓内已生成并带哈希的 `.lib`，两者哈希不一致即报错；
- 查找顺序（对齐 `build/darwin_link.yh:157–215`）：`YH_WINDOWS_SDK` → 可执行文件旁
  bundle → 原生 Windows SDK（`WindowsSdkDir` / `LIB`）→ 可操作诊断；
- 首版 `.def` 面（按 W1-3 实际引用逐项增加，不做投机性覆盖）：

  ```text
  GetStdHandle WriteFile ExitProcess GetProcessHeap HeapAlloc HeapFree
  GetLastError  CloseHandle  GetCommandLineA  （W1-3b 文件 API 时再加）
  ```

- **不打包**微软 SDK/CRC 二进制；不引入 `ucrt`/`msvcrt` 导入库（D2）。
- **`.gitignore` 坑（已核对）**：仓库根的 `*.lib`、`*.obj`、`*.exe`、`*.dll` 都在
  忽略名单里。所以「仓内回退 `.lib`」要么在本行加白名单
  （`!compiler/windows-sdk/lib/*.lib`），要么**不落二进制**、只靠 `.def` + 构建期生成。
  默认取后者：仓内只放 `.def` + `manifest.json`；生成失败时给可操作诊断，而不是
  默默去读一个永远不会被提交的 `.lib`。若后续实践证明宿主普遍缺 `llvm-dlltool`，
  再加白名单并把哈希入 manifest（那时才动 `.gitignore`）。

**验收**：`tests/selfhost/llvm-windows-sdk.py`——def→lib 幂等且哈希稳定；最小程序链接
成功；`llvm-readobj --coff-imports` 断言**只有** `KERNEL32.dll`（无 msvcrt/ucrt 旁车）；
缺 SDK 时诊断给出下一条可执行命令。

### W1-5 COFF/PE 链接（拟新增 `build/windows_link.yh`，对标 `build/darwin_link.yh`）

> **状态：已落地（2026-10-27）**。`just test-windows-target` + `tests/windows/run-exe.py`
> 两端全绿（PE、只依赖 KERNEL32、`/Brepro` 可复现、Windows 原生运行）。

- `mb_lld_windows_enabled()`：`target.os==WINDOWS && arch==X64` 且桥有 lld 身份。
- COFF argv 模板（固定，可复现）：

  ```text
  lld-link /nologo /Brepro /nodefaultlib /subsystem:console
           /entry:main /out:<out> <objects...> <extra...> <kernel32.lib>
  ```

  `/Brepro` 已实测使两次链接**字节相同**（附录 A-4），与 RB5「产物不可位级复现」的
  方向一致，别省掉。
- `mb_object_machine_matches`（`link_cache.yh:47–72`）加 PE/COFF 分支：
  `.obj` 看 COFF 头 `machine==0x8664`（2 字节 LE，偏移 0）；`.exe` 看 `MZ` →
  `e_lfanew` → `PE\0\0` → `machine==0x8664`。**对象与可执行文件都要校验**（防止
  缓存里拿到 ELF/Mach-O 旧对象）。
- 单文件形态：`build/llvm_emit.yh` 的 link 分派加 coff 分支（对象临时名 `<out>.yh-tmp.o`
  改成 `.obj` 以免 lld 猜测格式；临时产物统一 `.yh-link-tmp`）。
- `mb_select_linker`（`link_cache.yh:745`）：windows 目标 + 无内嵌 lld 时回落 `clang`，
  不接受 `gcc`；`YH_CC` 覆盖规则不变。
- 缓存键：`triple` + 模板哈希 + 导入库内容摘要（`mb_mix_file_identity`）+ 对象摘要。
- 失败语义照旧：**先写临时输出，验机（PE 头/machine）通过后才 rename 发布**；lld
  返回 `-2` 时不发布。
- **验收**：`tests/selfhost/llvm-windows-link.py`——O0/O2 各出 `.exe`；两次构建字节
  相同；`.obj`/`.exe` 头校验；缺 SDK、坏对象、`-2` 三条失败路径都不留半产物。

### W1-6 项目清单的目标节与库格式

> **状态：已完成（2026-10-27）**：`os="windows"`、`[link-windows-x64]`、目标表编码、
> `link_inputs` 的 `.lib`（ar 归档）与 `.dll`（PE + machine 校验）分支；linkbad 负例改用
> `[link-windows-sparc]`；门禁含两个库输入断言（合法 `.lib` 可链接、非 PE `.dll` 被拒）。

- `build/project_link.yh`：`pl_os_from_name` 认 `windows`；
  `pl_target_code_from_section` 认 `link-windows-x64`(5)、`link-windows-arm64`(6，预留)；
  `pl_target_code_current` 加 windows 分支。
- `tests/modules/projects/linkbad/project.toml` 现在用 `[link-windows-x64]` 当「非法节
  名」的负例（`tests/modules/build-check.py:254`）——W1-6 必须**同时**改负例
  （例如换成 `[link-windows-sparc]`），否则负例会变成正例而静默失效。
- `build/link_inputs.yh`：`li_kind_from_path` 认 `.lib`；`li_check_format` 加
  「COFF 归档/PE」分支（`.lib` 是 `!<arch>\n` 归档，但成员是 COFF，不能按 ELF 校验）。
- **验收**：`tests/modules/build-check.py` 增 windows 用例（合法 `[link-windows-x64]`
  与新的非法节名负例）；`just test` 不回归。

### W1-7 门禁与跨机执行（本机验收的落点）

> **状态：主体落地（2026-10-27）**：`check.py --emit-manifest` + `run-exe.py` 两阶段跨机；
> `just test-windows-target` / `test-windows-corpus` / `run-windows-corpus`；
> **202 例运行语料在真 Windows 全过**。剩余：CI 接线、正向 `// platform: windows-x64` 用例。
> 期间抓到并修掉桥的 COFF 重定位模型 bug（`bridge.c` 需对 windows-msvc 用 PIC）。

- 新增 `just test-windows-cross`（Linux/macOS 侧）：`--target x86_64-pc-windows-msvc`
  跑 `tests/yh-run` 里 `// platform: windows-x64` 的用例，产物与期望写进
  `tmp/windows-cross/manifest.json`（用例名、`.exe` 路径、期望 stdout、期望退出码）。
- 新增 `tests/windows/run-exe.py`（Windows 侧）：读 manifest → 逐个执行 `.exe` →
  比对 stdout/退出码；任一不符非 0。两侧可跨机器（CI artifact 或共享目录）。
- `tests/yh-run/check.py`：`host_platform_tag` 增「交叉目标即运行平台」的判定
  （现有 `--cross` 只硬编码 linux-arm64，需要按 `--target` 推导），SKIP 口径不变。
- **验收**：W1-7 门在 CI 的 linux-arm64 job 编、在本机跑；全绿才允许进入 W2。

### W1-8 文档

> **状态：已完成（2026-10-27）**；W1-3d（文件 API + fd 表）与 CI 接线同期落地。
> `docs/03-design/yh-Windows-LLVM后端设计.md` 是契约与
> 边界的唯一真源（含五个必记坑、不支持边界与平台差异表）。W1-3c 的守护片（16 KB 帧上限 +
> 门禁负例）同期落地。


- 新增 `docs/03-design/yh-Windows-LLVM后端设计.md`：目标身份、Win64 ABI 边界、
  零 CRT 运行时、导入库与 SDK 查找、COFF 链接模板、路径/编码边界、与 Linux/Darwin 的
  差异表。
- 订正既有文档里被写成「n」的 Windows（W0-4）。
- `docs/yh.g4` **不动**（无语法变化）；`docs/finish.md` 按片记录（含本机实测输出）。

---

## 7. W2 原生宿主切片（编译器在 Windows 上跑）

> 前置：W1 全绿 + W0-2a 已滚种子。W2 的验收比 W1 严格：**固定点自举**。

### W2-1 宿主身份与 `$if (windows)`

- `gen/target_info.yh`：`target_host_info` 增 `$if (windows)` 分支
  （`$if (windows) { $if (arm64) … $else { x86_64-pc-windows-msvc } }`）；
- `gen/state.yh:551` 的方言赋值、`gen/target.yh:tg_host_darwin` 的宿主探测
  （`tg_host_darwin` 现在靠探测 `/System/Library/...`，Windows 上用等价手段或改为
  `$if` 常量）；
- 所有 `c_host_target.os == DARWIN ? 0x601 : 0x241` 之类的**宿主**判定
  （`llvm_pipeline.yh:136`、`process.yh:108`、`module_build.yh:831`）改用统一的
  `host_open_flags()`，Windows 分支给 `CreateFileA` 需要的 `dwCreationDisposition`。

### W2-2 windows-x86_64 静态 LLVM/lld SDK（本机可做）

- `vendor/llvm/sdk.lock.json` 加 `hosts["windows-x86_64"]`：LLVM 21.1.8、`Release`、
  无 dylib、targets `AArch64;X86`、lld（COFF/ELF/MachO/Wasm/MinGW 至少 COFF+ELF+MachO）、
  包哈希 + 来源（本机构建产物上传 Release，同 Darwin 的处理方式）。
- `tests/selfhost/llvm-host.py`：`HOSTS` 加 `windows-x86_64`（PE machine `0x8664`、
  无 qemu、`nm/readelf` 判定换成 `llvm-readobj`/`dumpbin`）；`tools/llvm-host.py`：
  `HOSTS`、shim（Windows 无 `gcc`，包装器改为 `clang` 或直接编译期注入闭包）。
- 本机用 MSVC 14.41 + cmake 4.1.2 构建（预计数小时、10–20 GB 暂存，放 `tmp/`）；
  **不把 SDK 二进制提交进仓库**。

### W2-3 宿主 OS 桥（文件/目录/时钟/进程号）

拟新增（按后缀筛选，需 W0-2a）：
`build/project_dir.windows.x64.yh`（`FindFirstFileA/FindNextFileA`，处理 `.`/`..`、
目录位、稳定排序）、`build/clock.windows.x64.yh`（`QueryPerformanceCounter` 单调纳秒）。

宿主 prelude 面（Windows 侧的 `open/read/write/close/mkdir/unlink/rename/getpid`）：

| POSIX 用法 | Windows 实现 |
| --- | --- |
| `open(path, 0)`（只读） | `CreateFileA(GENERIC_READ, FILE_SHARE_READ…)` |
| `open(path, 0x241/0x601, 0644)`（写/截断） | `CreateFileA(GENERIC_WRITE, CREATE_ALWAYS)` |
| `read/write` | `ReadFile/WriteFile` |
| `mkdir` | `CreateDirectoryA` |
| `unlink` | `DeleteFileA` |
| `rename` | `MoveFileExA(MOVEFILE_REPLACE_EXISTING)` |
| `getpid` | `GetCurrentProcessId`（会话后缀 `mb_sched_set_session` 要用） |

路径约定：内部一律 `/`（Win32 API 接受 `/`）；盘符与相对路径首版可用；UNC/长路径/UTF-16
后置并写进边界文档。二进制产物读写**必须**走二进制模式（现有 POSIX 调用天然二进制，
Windows 侧不要引入任何 CRLF 翻译）。

> **与既有条目的协调**：todo 的 **E1.2（编译器迁移到 `libs/os` 的文件/进程）** 与
> 本切片是同一块地基。若 E1.2 先落地，W2-3 只需在 `libs/os` 加 Windows 变体，
> `compiler/build/*` 不再各自直写 POSIX 常量；若 W2 先做，则 W2-3 的 Win32 实现
> 应直接放进 `libs/os`/`libs/sys` 的 `.windows.yh`，让 E1.2 迁移时零重复。
> 两者不要各写一套（这是本方案唯一要求跨条目协调的地方）。

### W2-4 进程模型（本方案最大的架构改动）

Windows 没有 `fork/execv/waitpid/dup2`。三个消费者：

| 消费者 | 现状 | W2 策略 |
| --- | --- | --- |
| 模块 worker（并行编译） | `build_scheduler.yh:59` fork + COW 继承只读项目快照 | **W2-4a 串行单进程**（按依赖序直接调 `mb_emit_indexed_module`，每模块前显式重置前端会话）；**W2-4b** 用 `CreateProcessA` 重入自身 `--n`（`cmd/api.yh` 的 `api_emit_module` 已存在）+ `CreatePipe` 代替 `dup2`+临时文件 |
| lld worker | `link_cache.yh:446` fork 子进程跑 lld | Windows 首版同进程直调（lld 在 Windows 上用一次就 `can_run_again=false`，失败直接结束进程） |
| `cmd_process_capture` / `cmd_process_run` | `process.yh:83–160` fork+`dup2`+临时文件 | `CreateProcessA` + `CreatePipe`/临时文件 + `WaitForSingleObject` + `GetExitCodeProcess` |

风险：W2-4a 的「串行 + 显式 reset」若与会话状态不完整，固定点会立刻暴露（模块产物字节
不同）——这正是我们想要的失败信号；不要为了并行先做 4b。

### W2-5 just / 取种 / 种子命名

- `justfile`：`host_os == "windows"` → 种子 `bin/yh-windows-x64`、
  `seed_platform = "windows-x64"`、`llvm_host = "windows-x86_64"`、
  `runtime_test`/`cache_test` 指向 Windows 专项门；`bootstrap` 走
  `tools/llvm-host.py prepare --host windows-x86_64`。
- `tools/fetch-release-seed.py`：平台名 `windows-x64`。
- `.gitea/workflows/ci.yml`：新增 `windows-x64` job（本机 runner，host 模式，
  labels 加 `windows-x64`）；三端 → 四端；`release.yml` 资产同增。

### W2-6 首个 Windows 种子与固定点

1. 用 W1 交叉出的 `yh.exe`（已含 `windows` 标记解析，W0-2a）在 Windows 上 `just`
   冷编 → 得到第二代；
2. 两代模块产物逐字节相同（固定点）+ 自解析 + 全量语料（Windows 侧 `// platform:`
   过滤）；
3. `just seed SEED_DEST=bin/yh-windows-x64`（首次手工指定，之后自动）；
4. 记录到 `docs/finish.md`：种子哈希、门禁输出、耗时。

### W2-7 标准库的平台变体

- `libs/os`：`directory.windows.yh`、`process.windows.yh`；
- `libs/sys`：`errno/constants/raw/file/memory/time/process` 的 windows 变体
  （首版只覆盖 `os`/`io`/`fmt`/`string` 实际用到的面）；
- `libs/libc`：确认无平台强依赖（若有，补 windows 分支）；
- 每加一个平台变体就加对应 `// platform: windows` 用例。

---

## 8. W3 收尾（不在本轮）

- Windows/ARM64（`aarch64-pc-windows-msvc`）与 macOS/x86_64 的矩阵补齐（todo B2）。
- 发布资产：`windows-x64` 种子 + `yh.exe`；安装脚本与 `PREFIX` 语义。
- 性能：Windows 侧 `just` 冷编/增量基线与 RN 口径（对齐 `docs/02-plan/yh-编译器性能测试方案`）。
- C 互操作回到 UCRT/MSVC 生态的评估（D2 的第二波）。

---

## 9. 验证矩阵（本机能验什么、不能验什么）

### 9.1 本机（Windows/x86_64 + WSL）

| 动作 | 是否可行 | 说明 |
| --- | --- | --- |
| 运行交叉产出的 `.exe`（stdout/退出码/参数） | ✅ | 本机主职责 |
| `clang`/`lld-link`/`llvm-dlltool`/`llvm-readobj` oracle 差分 | ✅ | 21.1.8 全套在位 |
| 生成/校验 `kernel32.lib` 导入库 | ✅ | 已实测 1.7 KB、可用 |
| 构建 windows-x86_64 静态 LLVM/lld SDK（W2-2） | ✅ | cmake 4.1.2 + MSVC 14.41；耗时/磁盘见风险 R3 |
| 编译 yh（W1 交叉） | ⚠️ 待 W0-1 | WSL 已启用 WSL2 但**无已注册发行版**；装 Ubuntu + qemu-user-static + 交叉 gcc 后即可本机闭环，否则退回 CI linux-arm64 job |
| 自举固定点 | 仅 W2-6 之后 ✅ | 前置是 W1 产物 `yh.exe` |
| 作为 CI runner（windows-x64） | ✅（W2-5 接入） | 本机是 host 模式 runner 的候选 |

### 9.2 门禁命令（拟）

```bash
# 编译侧（WSL / Linux / macOS，现有种子；产物写 tmp/windows-cross/）
just test-windows-cross                 # 交叉出 .exe + manifest（W1-7）
python3 tests/selfhost/llvm-windows-abi.py
python3 tests/selfhost/llvm-windows-sdk.py
python3 tests/selfhost/llvm-windows-link.py
# 运行侧（Windows 侧，本机 / /mnt/c 同一工作树）
python3 tests/windows/run-exe.py --manifest tmp/windows-cross/manifest.json
```

判定口径：

- **W1 完成** = 上述四个脚本全绿 + `tests/yh-run` 的 windows 用例全绿 +
  Linux/Darwin 本平台 `just test` / `just selfhost-native` 不回归。
- **W2 完成** = Windows 上 `just` 冷编成功 + 两代固定点字节相同 + `just test` 全绿 +
  `bin/yh-windows-x64` 滚种子成功。
- 任一阶段红都不得滚种子；W1 不改变 Linux/Darwin 既有默认目标。

---

## 10. 风险清单

| # | 风险 | 影响 | 处置 |
| --- | --- | --- | --- |
| R1 | `fork` 依赖（模块 worker / lld worker / 捕获子进程） | W2 最大工程量，可能暴露前端会话状态未完全重置 | W2-4a 串行先行；固定点是最强信号；一次只换一个消费者 |
| R2 | 导入库/CRT 授权与可复现 | 不能提交微软二进制 | 自造 `.def`→`.lib` + 哈希入 manifest；只用 kernel32 |
| R3 | windows-x86_64 LLVM/lld 静态 SDK 体积与构建时长 | 磁盘 10–20 GB、数小时，CI 缓存策略要重做 | 只在本机构建一次并上传 Release；CI 只下载校验哈希 |
| R4 | `$if (windows)` 顺序错 | 种子锁死（新源码编不过旧种子） | §4.1 两代顺序；W0-2a 不引用新常量 |
| R5 | 文件名标签在 W0-2a 前生效于所有目标 | 平台专属文件污染其他平台构建 | §4.2；先扩标签再落文件 |
| R6 | ABI 细节（32 字节 shadow space、XMM6–15 callee-saved、变参浮点双写、窄整数扩展、`__m128`/聚合按引用） | 只在跨语言调用面暴露，纯 yh→yh 可能全绿 | W1-2 的 clang oracle 差分 + `tests/selfhost/llvm-windows-abi.py`；首版拒绝 C 按值聚合 |
| R7 | 交叉编译侧与运行侧跨机 | artifact 传递、路径/换行差异 | manifest 用相对路径 + JSON；`run-exe.py` 只读 manifest |
| R8 | 缓存键漏目标身份 | 串用 ELF/Mach-O 对象或接口文件 | 目录已按 triple 隔离 + PE 头校验兜底 + W1-5 显式目标串入键 |
| R9 | 路径/编码（`\` vs `/`、UTF-16、长路径） | 用户项目路径差异下的偶发失败 | 首版边界显式写进设计文档；先 `/` + ANSI/UTF-8 |

---

## 11. 切片与工作量（粗略，人日）

| 阶段 | 切片 | 估算 |
| --- | --- | --- |
| W0 | W0-1/2a/3/4 | 1–1.5 |
| W1 | W1-1 目标身份 0.5；W1-2 ABI 1.5（含 2b 另 1.5）；W1-3 运行时 1.5；W1-4 导入库 1；W1-5 链接 1.5；W1-6 清单 0.5；W1-7 门禁 1；W1-8 文档 0.5 | 8–10 |
| W2 | W2-1 0.5；W2-2 SDK 2–3（含构建等待）；W2-3 OS 桥 2；W2-4 进程模型 2–4；W2-5 just/CI 1；W2-6 种子 0.5；W2-7 libs 2 | 10–13 |
| W3 | 矩阵与发布 | 3–5 |

顺序：`W0 → W1-1 → W1-2 → W1-3/W1-4（可并行）→ W1-5 → W1-6 → W1-7 → W1-8 → W2-1 →
W2-3/W2-2（并行）→ W2-4 → W2-5 → W2-6 → W2-7 → W3`。

---

## 12. 并行开发分析（2026-10-27，决策 D1/D2/D3 冻结后重算）

判据只有两条：**文件级不重叠**（同一文件不同时被两条 lane 改）与**构建环境不互斥**
（同一工作树不能并行跑 `just`，见 §12.4）。满足两条即可并行，不需要“任务类型相似”。

### 12.1 文件所有权矩阵（冲突的唯一依据）

| 文件（现有/拟新增） | 拥有切片 | 结论 |
| --- | --- | --- |
| `comptime/ct_target.yh`、`build/project_index.yh` | W0-2a | 独占（但必须最早完成，见 §4.1/§4.2） |
| `gen/model.yh` | W1-1 | 独占 |
| `gen/target_info.yh` | W1-1 → **W2-1** | **串行**：W2-1 必须等 W1-1 冻结 |
| `gen/state.yh`、`gen/target.yh` | W2-1 | W2 内独占 |
| `backend/llvm_module.yh`、`backend/llvm_call.yh` | W1-2 | 独占（`printf` 的裸变参门由 W1-2 一次做完，不留尾巴给 W1-3） |
| `backend/llvm_runtime.yh` + 拟新增 `llvm_windows_runtime.yh` | W1-3 | 独占 |
| `compiler/windows-sdk/**`、`tools/windows-sdk.py`、拟新增 SDK 门 | W1-4 | 独占，**零依赖**（纯新增） |
| 拟新增 `build/windows_link.yh`、`build/llvm_emit.yh` | W1-5 | 独占 |
| `build/link_cache.yh` | W1-5 → **W2-4** | **串行**：lld worker（`:446`）是 W2-4 的改造点 |
| `build/llvm_pipeline.yh` | W1-5（如需）→ **W2-1** | 串行（open 旗标 `:136`） |
| `build/project_link.yh`、`build/link_inputs.yh`、`tests/modules/**` | W1-6 | 独占（W2 不碰） |
| 拟新增 `build/project_dir.windows.x64.yh`、`clock.windows.x64.yh` | W2-3a | 独占（需 W0-2a 的标签） |
| `build/process.yh`、`build/build_scheduler.yh` | W2-1（旗标）→ **W2-4** | W2 内串行 |
| `libs/sys/**`、`libs/os/**` 的 `.windows.yh` 变体 | W2-7 | 独占（`sys` 先于 `os`；可与 W2-3 并行） |
| `tests/yh-run/check.py`、拟新增 `tests/windows/run-exe.py` | W1-7 | 独占 |
| `justfile` | W1-7 → **W2-5** | **串行**（同一个文件，两次小改） |
| `tests/selfhost/llvm-host.py`、`tools/llvm-host.py`、`vendor/llvm/sdk.lock.json` | W2-2 | 独占，**零依赖** |
| `docs/**` | W0-4/W1-8 | 独占（随时插） |

只有 **4 个文件**是真串行点：`gen/target_info.yh`、`build/link_cache.yh`、
`justfile`、`build/process.yh`；其余全部可并行。

### 12.2 七条 lane

| lane | 内容 | 可开工前置 | 汇合点 |
| --- | --- | --- | --- |
| **A 目标主链（串行）** | W1-1 → W1-2 → W1-3 → W1-5 | W0-1 环境 | 给 W1-7 提供可运行的 `.exe` |
| **B 导入库/SDK stub** | W1-4 | **无需环境**（纯新增 + `llvm-dlltool`，Windows 侧即可） | 把 SDK 查找与 `kernel32.lib` 交给 A 的 W1-5 |
| **C 清单/链接输入** | W1-6 | W1-1 的 `TARGET_OS_WINDOWS` 常量（“节名→码 5/6”部分可更早） | 与 A 的 W1-2/W1-3 全程并行，最后与 W1-5 一起验收 |
| **D 门禁脚手架** | W1-7a | **无需环境**（纯 Python + manifest 格式 + `justfile` 目标） | W1-5 落地后一次转绿 |
| **E Windows 宿主 SDK** | W2-2 | **无需环境**（本机 MSVC + cmake） | W2-6 的前置；墙上时间最长，必须第 0 天开 |
| **F 宿主 OS 桥** | W2-3a（`libs/` 侧 Win32 封装）→ W2-3b（compiler 侧 glue） | W2-3a 第 0 天；W2-3b 需 W0-2a 种子 + W2-1 | W2-7 消费 F 的 `libs/sys` 层 |
| **G 文档** | W1-8 + W0-4 | 无 | 随 A/C 的接口定型逐步填 |

汇合链（串行部分）：

```text
W0-1 环境 ─→ W0-2a ─→ 滚种子 ─┐
W1-1 ──→ W1-2 ──→ W1-5 ────────┴─→ W2-1 ─→ W2-4 ─→ W2-5 ─→ W2-6 ─→ W2-7
  └─→ W1-6（C）                W1-3（A）┘
W1-4（B）────────┴
W1-7a（D）────────────┴─→ W1-7 转绿 ─→ W1 完成
W2-2（E）─────────────────────────────────────┘
```

### 12.3 首日就能动的 6 件事（其中 4 件**不需要编译器**）

1. ~~**W1-4**（导入库/SDK stub）~~ **2026-10-27 已完成**：`.def` + `manifest.json` +
   `tools/windows-sdk.py` + `tests/selfhost/llvm-windows-sdk.py` + 两个 just 目标，
   本机（Windows）实测全绿；不碰 `compiler/*.yh`。
2. **W1-7a**（门禁脚手架）：`tests/windows/run-exe.py`、manifest schema、`justfile` 的
   `test-windows-cross` 目标；可以在没有 `.exe` 时先用“手工造的 PE”自测。
3. **W2-2**（windows-x86_64 静态 LLVM/lld SDK）：本机 cmake + MSVC，构建数小时，越早开越好；
   脚本适配（`HOSTS`、`llvm-readobj` 代替 `readelf`/`nm`）可边构建边写。
4. **W2-3a**（`libs/sys`+`libs/os` 的 Win32 封装）：纯新增 `.windows.yh`，但**要等 W0-2a
   的标签**才能被筛选（否则会被全平台编入，§4.2）——因此它是“首日开写、W0-2a 后合入”。
5. **W1-8 设计文档草稿** + **W0-4 文档卫生**（只改 `docs/`）。
6. **W0-1 WSL 环境**（唯一需要环境动作的一项，见 §5）——它是 A/C 两条 lane 的硬前置。

### 12.4 工作树与缓存隔离（否则并行会互相踩）

`just` 的 `_ensure_built` 会因源码 mtime 冷编并覆盖仓库根 `yh`，`just stage-yh` 会覆写
`FAST_DIR`，`compiler/.build`、`tmp/` 也都在同目录。所以并行 lane 必须：

```bash
git worktree add ../wt-w1-a  <base>      # 每条 lane 一个工作树
# 只读缓存共享，别删：
export YH_LLVM_CACHE=<主工作树>/tmp/llvm-migration
export FAST_DIR=/tmp/yh-fast-w1a        # 每条 lane 唯一（本地手工设，CI 用 GITHUB_RUN_ID）
```

**W0-2a 的滚种子必须在干净工作树上单独成一次提交**（`just test` +
`just selfhost-native` → `just seed`），其它 lane 事后 rebase；否则种子会把半成品一起
固化，而这正是 todo 里 RB2「拿旧副本白跑」那类事故的成因。

### 12.5 收益与风险（并行后的真实预期）

| 阶段 | 串行 | 3–4 lane 并行 | 关键路径 |
| --- | --- | --- | --- |
| W1 | 8–10 人日 | 约 4–5 日历日 | W1-1 → W1-2 → W1-5 → W1-7（W1-3 可插在 W1-2/W1-5 之间） |
| W2 | 10–13 人日 | 约 6–8 日历日 | W0-2a 种子 → W2-1 → W2-4 → W2-6（W2-2 的构建等待与 W2-4 的开发重叠） |

并行带来的两个新风险：

- **R10 合并冲穸**：`gen/target_info.yh` 与 `build/link_cache.yh` 是两个上游热点，W2-1/W2-4
  必须等 W1-1/W1-5 **合入后再开**（不允许“先写后 merge”）。
- **R11 分叉门禁**：每条 lane 各自 `just test` 绿但合并后才红（跨 lane 的 ABI/清单交互）。
  处置：lane A 每片合入前跑一次 `just test` + `just selfhost-native`；W1-5/W1-6 合入后
  立即跑一次「A+C 合并态」的全量门。

---

## 附录 A：本机实测记录（2026-10-27，Windows 11 x86_64 / MSYS2）

A-1 目标数据布局（以本机 clang 21.1.8 为准，勿手抄）

```text
$ clang --target=x86_64-pc-windows-msvc -S -emit-llvm -o - t.c
target datalayout = "e-m:w-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-windows-msvc19.41.34123"     ; 版本后缀由 clang 追加，yh 不加
```

A-2 无 CRT 入口：`/entry:main` 返回即退出码

```text
$ clang --target=x86_64-pc-windows-msvc -O2 -c t.c -o t.obj      # int main(void){return 7;}
$ lld-link /nodefaultlib /subsystem:console /entry:main /out:t.exe t.obj
$ ./t.exe; echo $?
7
```

A-3 自造导入库可用（文本 `.def` → 1.7 KB `.lib` → `lld-link` 解析 `__declspec(dllimport)`）

```text
$ cat kernel32.def
LIBRARY KERNEL32.dll
EXPORTS
    GetStdHandle
    WriteFile
    ExitProcess
$ llvm-dlltool -m i386:x86-64 -d kernel32.def -l kernel32.lib       # 1716 字节
$ lld-link /nodefaultlib /subsystem:console /entry:main /out:w.exe w.obj kernel32.lib
$ ./w.exe            # 程序内 GetStdHandle+WriteFile 打印 "hi-yh"，返回 3
hi-yh
$ echo $?
3
$ llvm-readobj --coff-imports w.exe
Import { Name: KERNEL32.dll  Symbol: GetStdHandle  Symbol: WriteFile }
```

A-4 `/Brepro` 使链接可位级复现

```text
$ lld-link … /Brepro /out:r1.exe … ; lld-link … /Brepro /out:r2.exe …
$ sha256sum r1.exe r2.exe
01f498a5…262b  r1.exe
01f498a5…262b  r2.exe
```

A-5 本机工具与实际缺口

```text
clang 21.1.8 / LLD 21.1.8 / llvm-dlltool / llvm-readobj   （D:\scoop\apps\llvm\21.1.8）
Windows SDK 10.0.22621 import libs（kernel32.lib 等）      （D:\Windows Kits\10\Lib）
MSVC 14.41.34120 / cmake 4.1.2 / python 3.12.5 / just 1.59
缺：bin/ 种子、tmp/llvm-migration 闭包、WSL 发行版 → W1 的编译动作必须在 Linux/macOS 侧
```

A-6 既有 COFF 探针（已通过，说明「出对象 + 链接」不是新能力）

```text
tests/selfhost/llvm-lld.py --cross-coff：emit x86_64-pc-windows-msvc 对象
  → lld-link -flavor link /entry:main /subsystem:console /nodefaultlib
  → 断言 PE machine == 0x8664
```
