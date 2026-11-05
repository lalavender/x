# yh Windows/x86_64（MSVC ABI，零 CRT）后端设计

修改时间：2026-11-06

> 状态：W1 目标面已落地（2026-10-27）。本文是**边界与契约**的唯一真源；实施切片与进度见
> [实施方案](../02-plan/yh-Windows-x86_64-LLVM后端接入实施方案-2026-10-27.md)，
> 完成记录见 [finish.md](../finish.md)。
> 与 Linux/Darwin 的差异一律在本文件显式列出，不在代码注释里「口头约定」。

## 0. 一句话

**不是新后端**：LLVM 出 COFF、内嵌 lld 出 PE；要补的是「目标身份 + Win64 ABI 门 +
零 CRT 运行时 + 导入库 + PE 链接模板 + 宿主 OS 桥（W2）」。

## 1. 目标身份

| 项 | 值 | 说明 |
| --- | --- | --- |
| triple | `x86_64-pc-windows-msvc` | 首版只此一格；`aarch64-pc-windows-msvc` 明确拒绝（§7） |
| abi | `win64-msvc` | 后端/ABI 门/缓存键都读它 |
| data_layout | `e-m:w-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128` | 2026-10-27 用 clang 21.1.8 实测核对 |
| 指针/字节序 | 64 位 / 小端 | LLP64：`long` 仍是 4 字节（yh 的 `int`=i32 天然对齐） |

**目标身份有两份表**（历史遗留）：`gen/target_info.yh`（前端）与
`ir/ssa_module_00_model.yh`（IR key，windows=5）。**新增目标必须两处同改**，否则
lowering 会静默返回 -1（退出码 255、无诊断）。

## 2. Win64 ABI 边界

- **yh 内部 ABI 不变**：`IR_ABI_YH_LLVM_V1` 的聚合按「隐藏指针/内存」传递，与平台无关；
  Windows 只影响 **C ABI（`@[extern]`）** 与运行时入口。
- **C 标量/指针/函数指针**：放行（`llvm_abi_supported` 的 win64 分支）。
- **C 按值聚合**（W1-2b 已落地，与 clang 编的 C 桩互操作验证）：Win64 规则与 SysV 完全不同 ——
  大小 ∈ {1,2,4,8} 的聚合走**整数寄存器** `i8/i16/i32/i64`（纯 float 聚合同样进整数寄存器），
  其余大小按引用：参数是**普通 `ptr`（无 `byval`）**、返回是 `void` + hidden `ptr sret`。
  布局要求与 C 共享：必须写 `@[extern] struct`。
- **用户裸 C 变参**：仍拒绝（prelude 的 `printf`/`open` 走 yh ABI 分支，不受此限）。
- **窄整数属性**：Win64 的 `i8/i16` 参数与返回值**不带** `signext/zeroext`
  （与 SysV 相反，clang oracle 实测）；`llvm_abi_attr_kind` 因此对 win64 返回 0。
- **裸 C 变参**：只放行 prelude 的 `printf`（运行时自己发射），用户裸变参仍拒绝。
- **浮点**：`float`/`double` 走 XMM0..3（Win64 单调用约定）；**必须自定 `@_fltused`**
  （见 §6.2）。

## 3. 零 CRT 运行时（`compiler/backend/llvm_windows_runtime.yh`）

只依赖 `KERNEL32.dll`，不链接 msvcrt/ucrt/libcmt，也不 `/defaultlib` 任何库。

| 入口 | 实现 | 契约 |
| --- | --- | --- |
| `__yh_runtime_malloc(i64) ptr` | `HeapAlloc(GetProcessHeap(),0,size+16)` | 头部 16 字节记录总长，用户指针 16 字节对齐；0 字节按 1；溢出/失败返回 null |
| `__yh_runtime_free(ptr)` | `HeapFree(GetProcessHeap(),0,base-16)` | NULL 无操作 |
| `printf(fmt, ...) i32` | `GetStdHandle(-11)` + `WriteFile` 短写循环 | 与 Linux 版同一格式集合；按字节输出，不做 CRLF 翻译 |
| `write(fd,buf,n) i64` | fd 1→stdout、其余→stderr | yh test 的失败记录（fd 3）落在 stderr（W2 换真管道） |
| `read(fd,buf,n) i64` | 只接受 fd 0（stdin）+ `ReadFile` | 返回字节数、0=EOF、-1=失败；管道注入的二进制（含 NUL）原样返回 |
| `exit` / `_Exit` | **不定义** | 链接期 `/alternatename:exit=ExitProcess`、`/alternatename:_Exit=ExitProcess` |
| `__yh_test_assert` | 复用共享实现 | 经 `write` 薄层输出 |

发射纪律：`weak` 定义 + `llvm.used` + `optnone/noinline/nobuiltin`；Windows 目标额外加
`comdat any`（§6.6）。**运行时函数的 alloca 必须放 entry 块**（否则引 `__chkstk`，见 §6.4）。

## 4. 进程入口与 argv

Win64 的 PE 入口**不传参数**，入口采用双形态：

```
/entry:mainCRTStartup
/alternatename:mainCRTStartup=__yh_zero_crt_start
```

- **闭包里有静态 CRT**（编译器自举）：入口解析到 libcmt 的 `mainCRTStartup`，
  CRT 完成静态构造/argv/envp/stdio 后调用 `main(argc, argv, envp)`，返回码即退出码；
  yh 发射的 `main` 是 Win64 C ABI（RCX/RDX/R8），与 CRT 期望一致。
- **零 CRT 用户程序**：`mainCRTStartup` 未定义 → alternatename 落到运行时发射的
  `__yh_zero_crt_start()`：`GetCommandLineA` → 极简解析（双引号成组、空格分隔）→
  `call main(argc, argv)` → `ExitProcess`。
- 缓冲区是模块内 `internal` 全局（`[8192 x i8]` 命令行 + `[256 x ptr]` argv），不依赖 CRT。
- 解析器**不实现** MSVC 的全套规则（如转义引号、`argv[0]` 去引号特例）；边界见 §7。

## 5. 链接（`compiler/build/windows_link.yh`）

固定模板（可复现）：

```text
lld-link -flavor link /nologo /Brepro /nodefaultlib /subsystem:console
        /entry:mainCRTStartup
        /alternatename:exit=ExitProcess /alternatename:_Exit=ExitProcess
        /alternatename:__chkstk=__yh_chkstk
        /alternatename:mainCRTStartup=__yh_zero_crt_start
        /out:<tmp> <objects...> <project [link-windows-x64] 项...> <kernel32.lib> <yh_chkstk.obj>
```

- `/Brepro`：实测两次链接**逐字节相同**（与 RB5 的「产物可比」方向一致）。
- `/nodefaultlib`：不引入任何 CRT 默认库；自举时 CRT 组由 `[link-windows-x64]` 显式给出。
- 有 fork 的宿主在**一次性子进程**里跑内嵌 lld；Windows 无 fork 时在当前进程跑，
  且 lld 的输出句柄活到进程退出 → 直接写最终路径，跳过临时文件/复核/链接缓存哈希。
- 有 fork 时产物发布前校验：`MZ` → `PE` 头 → `machine=0x8664`；失败不发布半产物。
- 缓存键包含：triple + data_layout + 固定模板 + 导入库内容摘要 + 目标文件摘要。

**导入库与查找顺序**（`compiler/windows-sdk/`）：

1. `$YH_WINDOWS_SDK/lib/kernel32.lib`
2. `<exe 目录>/compiler/windows-sdk/lib`（开发树）
3. `<exe 目录>/tmp/llvm-migration/windows-sdk/lib`（`tools/windows-sdk.py` 默认 `--out`）
4. `<exe 目录>/windows-sdk/lib`（安装形态）

仓库只放**文本** `.def` + `manifest.json`（含 `def_sha256`）；`.lib` 由
`just windows-sdk`（`llvm-dlltool` → `lld-link /lib` → `lib.exe`）生成到缓存目录。
`llvm-dlltool` 与 `lld-link /lib` 的产物实测逐字节相同。

## 6. 九个必须记住的坑（每个都有实测记录）

### 6.1 COFF 必须用 PIC 重定位模型

`compiler/llvm/bridge.c` 原来除 Darwin/ARM64 外都用 `LLVMRelocStatic`。COFF 下它产出
**ADDR32 绝对地址**（`movl G, %edx` + `IMAGE_REL_AMD64_ADDR32`），而 PE 镜像基址是
`0x140000000` → 地址被截断 → **任何全局数据访问都 ACCESS_VIOLATION**。
修法：`needs_pic = darwin_arm64 || windows-msvc`。这类 bug 只有真跑能抓到。

### 6.2 浮点要自定 `_fltused`（COFF 还必须挂 COMDAT）

x86 后端在 COFF 对象里会引用 `_fltused`（CRT 的浮点使用标记）。零 CRT 没人定义它 →
`undefined symbol: _fltused`。修法：win64 模块统一发射
`$_fltused = comdat any` + `@_fltused = linkonce_odr global i32 0, comdat($_fltused)`。
**为什么不是普通 `internal global`**：多模块各带一份会 duplicate；COFF 的 `weak` 是
「带备用符号的弱外部」，也不能合并同名定义。必须用 COMDAT（见 §6.6）。静态 CRT 链接时
CRT 的 `fltused.obj` 不会被拉入（我们的定义已满足引用），因此两边共存。

### 6.3 `declare` 与 `define` 不能同名

LLVM 判 `invalid redefinition of function`。因此：

- 运行时**给出定义**的名字（`write`/`read`/`printf`/`malloc`/`free`）必须在**声明阶段跳过**
  （`llvm_runtime_supplies_symbol`）；
- 运行时**不定义**的名字（`exit`/`_Exit`）反过来：声明照常发射，定义交给链接期
  `/alternatename`。

### 6.4 alloca 必须全部在入口块

非入口块的 `alloca` 被 LLVM 当动态分配：Windows 上调 `__chkstk`，并且实测
「聚合临时值直接作为 printf 实参」会段错误。修法：`llvm_function` 把全部 alloca
提升到入口块（yh 的局部/聚合临时尺寸恒为常量、生命周期为函数级，语义不变）。

### 6.5 大栈帧需要 `__chkstk` 页探测

PE 的栈只在触碰 guard page 时按页增长；没有 `__chkstk` 时一次 `sub rsp, N` 跨过多个
guard page 会让首次访问直接崩（实测：16 KB 帧可用、32 KB 帧必崩）。
**现状（W1-3c 真修）**：SDK 提供 `yh_chkstk.obj`（`compiler/windows-sdk/chkstk.c`，
naked asm：按 4 KB 步长触碰页面、不改 RAX/RSP），**导出符号是 `__yh_chkstk`**；
链接模板固定带该对象并加 `/alternatename:__chkstk=__yh_chkstk`：
静态 CRT 自带 `__chkstk` 时用 CRT 的，零 CRT 用户程序才落到我们的桩。
LLVM 的页探测保持开启，帧大小不再受限（`29-stress-capacity` 的 160 KB 帧实测通过）。
`just windows-sdk` 用 clang 生成该对象并记进 `identity.json`（`check` 校验 COFF machine 与导出符号）。

### 6.6 COFF 的 `weak` 不能合并：运行时/全局要 COMDAT

`llvm_runtime.yh` / `llvm_windows_runtime.yh` 的运行时入口原本是 `define weak`，
ELF/Mach-O 链接器会合并同名弱定义；COFF 的 `weak` 是「带 fallback 的弱外部」，
lld-link 遇到多份会报 `duplicate symbol`（实测：memset/strlen/memcpy/__yh_runtime_malloc、
fd 表全局、`_fltused`）。修法：Windows 目标统一发射
`$<name> = comdat any` + `define weak ... comdat($<name>)`（全局用 `linkonce_odr` +
`comdat($<name>)`）。`llvm_runtime_weak_signature` 收敛了共享运行时的发射点。
代价：COMDAT 与「用户同名强定义」不能共存（实测强定义 + COMDAT 仍 duplicate）；
编译器自身的符号没有这种覆盖需求，用户程序里用同名强定义替换运行时属于不支持边界。

### 6.7 `__chkstk` 桩**必须保持 RAX 不变**

LLVM 的序言是 `mov eax, <帧大小>; call __chkstk; sub rsp, rax`：探测函数返回后由**调用方**
用 RAX 完成分配。因此探测循环只能递减一个临时寄存器（`r11`）。
2026-11-02 实测：桩里直接 `subq $4096, %rax` 时，调用方只 `sub rsp, rax` 掉除不尽的余数
（160 KB 帧只分配 3432 字节），**任何 >4 KB 的帧在第一次访问局部变量时 0xC0000005**。
表现是 `29-stress-capacity`、`148-deep-struct-field-offset`、`llvm-runtime-memory`
三例同时崩、且程序一行输出都没有（崩在函数入口）。
回归护栏：`compiler/windows-sdk/chkstk.c` 的注释 + SDK 门禁；
判据是「源码里除 `movq %rax, %r11` 外不得出现对 `%rax` 的写」。

### 6.8 lld 链接子进程的 stdout/stderr 不能继承父进程管道

无 fork 宿主的链接 worker 是 `yh --lld-link <响应文件>` 子进程。2026-11-02 实测矩阵
（父进程 stdout 是管道时，子进程分别给 inherit/nul/file）：

| stdin | stdout | stderr | 结果 |
| --- | --- | --- | --- |
| inherit | inherit | inherit | 失败 |
| nul | nul | nul | 成功 |
| inherit | nul | nul | 成功 |
| inherit | nul | 文件 | 成功 |
| nul | nul | inherit | 失败 |
| inherit | inherit | 文件 | 失败 |

即**stdout 必须接 NUL、stderr 不能是父进程的管道**，否则 lld 的
`FileOutputBuffer::commit()`（临时文件 `SetFileInformationByHandle` 改名）稳定报
`failed to write output '...': invalid argument`（`ERROR_INVALID_PARAMETER`），
重试 5/5 仍失败（不是偶发）。
修法：`yh_win_spawn_link`（`compiler/llvm/windows_shim.c`）固定 stdout→NUL、
stderr→`<rsp>.err` 文件，父进程链接结束后用 `mb_coff_forward_diag` 回放并删除。
配套：`lld_bridge.cpp` 在 `YH_LLD_STDERR` 下把 lld 诊断直接写 stderr——
lld 的 `fatal()` 走 `Process::Exit`（Windows 上是 `TerminateProcess`），
抓在内存缓冲里的诊断会随进程一起消失。

### 6.9 编译器不能假设 `/tmp` 存在

`--emit-asm` 原先把中间汇编写到硬编码的 `/tmp/yh-llvm-asm-<pid>.s`。Windows 上
`/tmp` 被解释成当前盘符下的 `	mp`，`mkstemp` 直接失败 → 报「内嵌 LLVM：目标文件
原子写入失败」（seed 与新一代编译器都复现）。修法：Windows 宿主取 `TEMP`/`TMP`，
两者都没时退到当前目录（文件名带 pid）。`W1` 的 `test-windows-target` 门禁正是
靠这条路径交叉发射汇编，因此该缺陷会让整道 Windows 目标门在 Windows 宿主上失败。

## 7. 明确不支持的边界

| 项 | 现状 | 归属 |
| --- | --- | --- |
| `aarch64-pc-windows-msvc` | 拒绝（`--target` 退出码 2） | W3 矩阵 |
| 用户裸 C 变参 | 编译期拒绝（§2；printf/open 除外） | W1-2b-2 若需要 |
| `@[extern]` 的 libc 函数（abs/strtoul/_Exit 之类） | 零 CRT 下无解析目标（静态 CRT 自举时有） | CRT 决策（W1-2b-2） |
| 用户程序同名强定义覆盖运行时 | COMDAT 不能与强定义共存（§6.6） | 不支持边界 |
| GUI 子系统、DLL 导出、SEH/异常、PDB | 不做 | — |
| UTF-16 路径、长路径（>260）、UNC | 首版只用 ANSI + `/` 分隔 | 按需 |
| 命令行解析的 MSVC 全套规则 | 只做双引号成组 + 空格分隔 | 按需 |
| `[link-options-windows-x64] whole` | 会被当成 Darwin 的 `-force_load`（lld 忽略）；当前不写该节 | W2-8 |

## 8. 与 Linux/Darwin 的差异表

| 维度 | Linux/x64 | Darwin/ARM64 | Windows/x64 |
| --- | --- | --- | --- |
| 重定位模型 | `LLVMRelocStatic`（-no-pie） | PIC | **PIC**（§6.1） |
| 系统调用 | `linux_syscall6`（asm） | libSystem | **无 syscall**，只走 Win32 API |
| 分配 | `mmap`/`munmap` | `mmap`/`munmap` | **HeapAlloc/HeapFree** |
| 输出 | `write(2)` 系统调用 | `write`（libc） | **WriteFile**（fd 0/1/2 或 fd 表） |
| 输入 | `read(2)` | `read`（libc） | **ReadFile** |
| 退出 | `exit`（libc） | `exit`（libc） | **ExitProcess**（含 `_Exit` 别名） |
| 入口 | `_start`（CRT） | `main`（libSystem 启动） | **CRT 启动优先**；零 CRT 落 `__yh_zero_crt_start`（§11） |
| 浮点标记 | — | — | `_fltused` + COMDAT（§6.2） |
| 运行时同名定义 | `weak` 可合并 | `weak` 可合并 | **必须 COMDAT**（§6.6） |
| 链接 | 内嵌 lld（ELF 模板） | 内嵌 lld（Mach-O） | 内嵌 lld（**COFF**）+ 导入库 |
| 对象校验 | ELF machine 62/183 | Mach-O cpu 16777223/8 | **COFF/PE machine 0x8664** |

## 9. 门禁与验收（两侧分工）

| 侧 | 命令 | 覆盖 |
| --- | --- | --- |
| 编译侧（WSL/Linux/macOS） | `just test-windows-sdk` | `.def`↔manifest、生成确定性、符号面、导入面只有 KERNEL32 |
| 编译侧 | `just test-windows-target` | 8 例 PE + 导入面 + `/Brepro` 可复现 + 拒 aarch64 + **大栈帧正例** + `.lib`/`.dll` 输入 |
| 编译侧 | `just test-windows-abi` | Win64 按值聚合与 clang C 桩互操作 |
| 编译侧 | `just test-windows-corpus` | 整份运行语料的交叉编译 + 写清单（`tmp/windows-corpus/manifest.json`） |
| 运行侧（真 Windows） | `just run-windows-corpus` / `tests/windows/run-exe.py` | 读清单执行并核对 stdout/退出码 |
| 原生（真 Windows） | 自编两代 | `bin/yh-windows-x64` 与自编产物逐字节相同 |

当前基线（2026-10-28）：**target 8/8、ABI 1/1、语料 208/208** 在真 Windows 全过；
原生两代固定点 `0969209e…`；Linux/Darwin 主门未回归。

## 10. 后续（按价值排序）

1. **W2-4b**：lld worker 与 testkit 子进程改 `CreateProcessA` 重入（含 `CreatePipe`）；
   当前 `yh run` / Windows 上的 `yh test` 仍依赖 fork/exec。
2. **W2-5**：just 的 windows 宿主分支（种子选择、`llvm_host=windows-x86_64`、取种/滚种）
   与 Gitea CI 的 `windows-x64` job。
3. **W2-2**：把 121 个 `.lib` + 桥 + CRT/系统库整理成 `tmp/llvm-migration/llvm-host-windows-x86_64/`
   闭包与 `selfhost-flags.txt`，并作为 Release 资产分发（不入库）。
4. **W2-0**：正式合入前发 0.0.11-rc——当前 Release 0.0.10 的种子不认识 `windows` 标记。
5. **W2-8**：COFF 整库加载（`/wholearchive:<path>`）或明确不支持。
6. **W1-2b-2**：CRT extern（abs/strtoul 等）的取舍：最小 UCRT 导入库 vs 自实现同名标量函数。
7. **W3**：Windows/ARM64、macOS/x86_64 四格矩阵。

## 11. Windows 宿主二进制的运行库（W2，静态 CRT）

这里说的是**编译器自己**（`yh.exe`）的运行库，不是它生成的目标程序（§3 的零 CRT 只约束后者）。

| 方案 | 依赖 | 结论 |
| --- | --- | --- |
| 动态 CRT（`/MD`） | `ucrtbase.dll` + `msvcp140.dll`/`vcruntime140.dll`（VC++ 可再发行包） | 不采用：yh.exe 会依赖外部运行库 |
| **静态 CRT（`/MT`）** | 只依赖系统 DLL | **采用**：本机实测 `libcmt + libcpmt + libvcruntime + libucrt + oldnames + comsuppw + kernel32/ntdll/ole32/oleaut32/uuid/advapi32/shell32/user32/psapi` → 54 MB 自包含 yh.exe（含静态 LLVM/lld），导入表只有 ADVAPI32/KERNEL32/ntdll/ole32/OLEAUT32/SHELL32 |

三条配套约束：

1. **LLVM/lld 归档必须同为 `/MT`**（`-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded`），
   否则与静态 CRT 混链会 `LNK2038: RuntimeLibrary mismatch`。
2. **不对 `__chkstk.obj` 做模板分支**：SDK 桩导出 `__yh_chkstk`，链接模板固定带它并加
   `/alternatename:__chkstk=__yh_chkstk`。静态 CRT 存在时用 CRT 的 `__chkstk`，
   零 CRT 用户程序才落到桩——不需要知道当前链接的是谁。
3. **许可边界**：静态 CRT/STL 库可以链进我们的二进制，但 `.lib` 文件本身不入库、不进种子，
   只由持有 VS 的构建机在链接时提供（与 Darwin SDK 同处理）。

对照 Zig：Zig 不打包 MSVC 的 CRT/STL（授权不允许），`-target *-windows-msvc` 时自动探测
用户的 VS；它自带的是 mingw-w64（headers + 导入库），所以 `-target *-windows-gnu` 无需外部
工具链。其发行二进制自包含靠的是「构建期依赖工具链、发布期静态链接」——我们要复制的就是这个实践。

## 12. 为什么 Windows 宿主必须从源码构建 LLVM（2026-10-27 实测）

机器上已装 LLVM 21.1.8（官方 Windows 发行版），但**不能拿它给 yh 自举**，原因是
「我们要的是库，不是命令行工具」：

| 我们需要的 | 官方 Windows 发行版提供 | 结论 |
| --- | --- | --- |
| 静态 `libLLVM*.lib`（`yh_llvm_emit` 走 C API 在进程内发射） | 只有 `LLVM-C.dll` + `LLVM-C.lib`（293 KB 全是 `__imp_` 跳板的**导入库**） | 缺 |
| 静态 `liblldCOFF/ELF/MachO/Common.lib`（`lld::coff::link` 等进程内驱动） | **完全没有**：只有 `lld.exe`/`lld-link.exe`/`ld.lld.exe` 可执行文件 | 缺 |
| `/MT`（静态 CRT）的归档，与我们的自包含链接一致 | 官方 DLL 构建是 `/MD` | 不匹配 |

本机 `D:\scoop\apps\llvm\21.1.8\lib` 的实际内容：
`LLVM-C.lib`、`libclang.lib`、`liblldb.lib`、`libomp.lib`、`LTO.lib`、`Remarks.lib`
（全部导入库）——没有任何 `libLLVM*.lib`/`liblld*.lib` 静态归档。

三条硬约束把「用现成安装」这条路堵死：

1. **自包含种子**（ADR-0014 + LL11）：`bin/yh-*` 是单个可执行文件，运行时不得依赖
   已安装的 LLVM，也不得壳掉外部工具——否则种子在干净机器上就跑不起来；
2. **lld 只能进程内调用**：`lld_bridge.cpp` 直接调 `lld::*::link`，可执行文件不导出这个符号；
3. **ABI/链接一致性**：需要 `/MT` 静态归档与静态 CRT 混链（§11）。

**为什么 Linux 宿主不需要编译源码**：Ubuntu 的 `llvm-21-dev` 与 `liblld-21` 包
**确实分发静态 `libLLVM*.a` 与 `liblld*.a`**（Darwin 则由本机 SDK 源码构建）。
Windows 没有等价的静态包，所以只有两条路：

- **A（采用）**：从源码用 MSVC 构建一次静态 LLVM + lld（Lane E，`/MT`），作为
  Release 资产分发；之后任何机器只下载校验，不再编译；
- **B（仅开发期应急）**：链 `LLVM-C.dll` + 壳 `lld-link.exe`——能快速得到一个 **dev**
  yh.exe，但它有旁车依赖、破坏进程内 lld 与缓存身份，**不能作为种子**。真要用，
  必须显式标记为 dev-only 并在后续替换。

## 13. W2 原生宿主实现（2026-10-28）

**静态闭包注入**：`tmp/winhost/libyh-llvm-bridge.lib` = `bridge.obj` + `lld_bridge.obj` +
`windows_shim.obj`（`clang-cl /MT`，`lib.exe` 打包）；LLVM 组件与 lld 直接用 MSVC
构建出的 `.lib`。清单里的 `LLVM-C.lib` 是 DLL 导入库（会拉 `LLVM-C.dll`），必须移除。

**进程模型**：Windows 无 fork，模块编译改为 `CreateProcessA` 重入 `--emit-module`
（`mb_spawn_module_child`）。子进程自己 `pj_load_project` 主项目并 `pj_topo` 重建拓扑序
（不重建时依赖 rank 会报「依赖模块不在拓扑序中」）；父进程等退出后按 pid=0 走完成分支。
`compiler/llvm/windows_shim.c` 提供 `yh_win_spawn_wait`（Windows 命令行 quoting +
`CreateProcessA` + `WaitForSingleObject`）以及 stat/realpath/setenv/usleep/fork/waitpid/kill 垫片。

**链接**：`mb_coff_link_worker` 无 fork 时在进程内跑内嵌 lld。lld 的输出句柄活到进程退出，
父进程立即读/改名/哈希会 `EACCES`；因此 `/out:` 直接指向最终路径，链接成功后跳过格式复核与
链接缓存 manifest（下一轮重链，但产物完整）。

**运行时细节**：`open` 同时支持文件和目录（`FILE_FLAG_BACKUP_SEMANTICS`）；fd 表 64 槽扫描复用；
`mkdir` 失败后 `path/.` 探测因此可用。多模块运行时/`_fltused`/fd 全局全部 COMDAT（§6.6）。

**验收**：交叉 yh.exe → 原生自编两代固定点 `0969209e…`；`bin/yh-windows-x64` 落盘；
Windows target 8/8、ABI 1/1、语料 208/208；Linux 主门与 `selfhost-native` 未回归。

## 14. 标准库平台变体（W2-7，2026-11-02）

`libs/` 的平台选择靠文件名后缀（`*.windows.yh` 由 `pj_source_target_match` 认 `windows`
标记，W0-2a 已登记）。Windows 侧的后端映射与 Linux/Darwin 的差别集中在**下面四条**，
新增库代码时不要假设 POSIX 语义：

| 能力 | Windows 实现 | 与 POSIX 的差别 |
| --- | --- | --- |
| 文件原语 | 复用编译器运行时的 prelude `open/read/write/close/mkdir/unlink/rename`（同一张 fd 表）+ `GetCurrentDirectoryA/SetCurrentDirectoryA/RemoveDirectoryA` | 没有 `*at`：`dir_fd` 只接受 `AT_FDCWD`，其余 `-ENOSYS`；没有 `getdents64`（改用 `FindFirstFileA/FindNextFileA/FindClose`）；没有 fd 语义的匿名管道（`create_pipe` = `-ENOSYS`） |
| 内存映射 | `VirtualAlloc/VirtualFree` | 只支持匿名可写（`address=0`、`fd<0`）；文件映射与部分解除映射 `-ENOSYS` |
| 时钟 | `GetSystemTimeAsFileTime`（realtime，1601 纪元换算）+ `QueryPerformanceCounter/Frequency`（monotonic）+ `Sleep` | `sleep_time` 不会被信号打断，`remaining` 恒 0 |
| 进程 | `process_id/exit` 直接映射；`CreateProcessA` + 64 槽 pid→HANDLE 表 + `WaitForSingleObject/GetExitCodeProcess` 在 `os` 层 | 没有 fork/exec/wait4/信号：`sys` 的这四类入口如实返回 `-ENOSYS`；失败创建直接在 `CreateProcessA` 的返回值上得到（没有 exec 错误管道握手） |

**errno 契约不变**：对外仍是 POSIX 编号的 `-errno`，Windows 的 `GetLastError()`
（`ERROR_FILE_NOT_FOUND`/`ERROR_ACCESS_DENIED`/`ERROR_DIR_NOT_EMPTY` 等）在
`libs/sys/errno.windows.yh` 里翻译一次，`os`/`net` 的错误分类因此不需要平台分支。

**另外三个只在 Windows 出现、容易被误判为“库写错”的点**：

1. `BOOL` 返回值不是 0/-1：`RemoveDirectoryA`/`FindClose`/`SetCurrentDirectoryA` 成功返回 1，
   直接交给“-1 表示失败”的归一化函数会得到**假的成功值 1**（`sys.remove_at(AT_REMOVEDIR)`
   曾因此完全无效）。
2. 负 fd 必须失败：运行时的 `close` 一度把 `fd < 3` 全当标准描述符，`close(-1)` 静默返回 0。
3. Windows 的 Win32 路径不允许控制字符，且**内嵌 lld 走 ANSI 命令行/响应文件**：
   含中文等工作区路径能编译但不能链接（`lld` 看到的是乱码路径）。因此门禁脚本在
   Windows 上把临时工作区名换成 ASCII（`tests/selfhost/llvm-architecture.py` 的
   `work_name`），源码级 `// platform:` 用例仍覆盖非 ASCII 目录扫描（不经链接）。

**测试入口的两个平台事实**（W2-7 顺带修掉）：用例号必须用十进制文本传递（单字节
`'a'+n` 在 n≥31 时落到 ≥0x80，ANSI 命令行往返会改坏）；测试函数名用**模块内文件序号**
而不是全局文件号（无 fork 宿主的模块子进程会重新索引）。

## 15. 零 CRT 边界：C 库符号与平台门禁（W2-9，2026-11-03）

Windows 目标按方案 D2 走**零 CRT**：用户程序只链 `kernel32.lib` + SDK 支撑对象
（`compiler/windows-sdk/chkstk.c`），没有任何 C 运行库。这条边界决定了两类符号：

**已由 SDK 支撑对象 + `/alternatename` 补齐**（有静态 CRT 时仍用 CRT 的版本）：
`__chkstk`（栈探测）、`usleep`、`isatty`、`rmdir`、`abs`、`putchar`、`_Exit`/`exit`。

**仍未提供**（`build-check.py` 的 `WINDOWS_SKIP` 记录，共 22 例）：

| 符号/能力 | 受影响的用例 | 说明 |
| --- | --- | --- |
| `strtod` | `llvm-target-identity`、`llvm-front-zero-output`、`llvm-checked-snapshot`、`llvm-snapshot-lowering`、`r2b-ast-check-module` | 夹具用宿主 libc 解析十进制浮点 |
| `cos`/`pow`（libm） | `s2-libs-core-modules`、`cabi-automatic-values-and-callbacks` | `libs/math` 现在就是 libm 薄封装（纯 yh 实现是 MATH 任务） |
| `lrint` 等 C 数学 | `u3-c-*`（7 例） | C 互操作夹具的 C 桩需要 libm |
| `dup2` | `r3-dup2-os-api` | POSIX fd 语义，运行时 fd 表没有 dup2 |
| `system()` | `r3-system-compat-*`（3 例） | POSIX shell 语义 |
| Winsock | `net0`/`net1` | `libs/sys/socket.windows.yh` 目前是 `-ENOSYS` 桩 |
| `ar`/`.a` + `--start-group` | `link-static-groups`（4 例） | ELF/Darwin 归档组；COFF 的 `.lib` 由 `test-windows-target` 覆盖 |
| `envp` | `r3-envp-main` | Windows 入口目前只构造 argv（`__yh_build_argv`） |

**决定点（W1-2b-2）**：接 UCRT 导入库（`ucrtbase.dll`）可一次解决上半张表，但用户
程序会依赖 `ucrtbase.dll`，与 D2 冲突；保持零 CRT 则需要逐个提供实现（`libs/math`
的纯 yh 化本来就是计划内工作）。在决定之前，这些用例按 SKIP 记录而不是 FAIL——它们
验证的是宿主 C/POSIX 能力，不是 Windows 后端的正确性。

**门禁的实现约定**（写新用例时照做）：`build-check.py` 的 `WINDOWS_SKIP` /
`WINDOWS_SKIP_PREFIX` 是唯一开关，`report()` 与 `run_case()` 都会查它；
断言退出码一律用 `exit_code()` 归一化到 POSIX 的 8 位语义；`link-cache.py` 这类
“外部工具计数”门在 Windows 上没有意义，改为用 `--stats` 的 link 计数与对象字节身份。
