# finish

滚动日志：只保留最近三天（当前为 2026-11-01 ～ 2026-11-03）的交付记录，靠前条目为最新状态。
更早的 384 条（2026-09-27 ～ 2026-10-21）已归档在
[finish 历史归档](01-finished/finish-历史归档-2026-09-27至2026-10-21.md)。
超出窗口的条目迁入同一个归档文件，新增条目写在最前。

## 2026-11-03 W2-9 收口：Windows 上 `just test` 与 `just selfhost-native` 双绿

**结果**：Windows/x86_64 上两道本地主门首次同时全绿——`just test`
（语法 82/82、反例 49/49、运行 209/209、fail 137/137、pass 9/9、libs 122/122、
compiler-tests 4/4、arch-check 通过）与 `just selfhost-native SKIP_CORPUS=1`
（cc2/cc3/cc4 固定点、自解析 124 文件、scratch 隔离、lex-stats、runtime-memory、
check-command、llvm-architecture、modules 19/19、test-check、libs、compiler-tests、
project cases **128/128**）。原生两代固定点 `5313b53bcf49d86a…` 逐字节相同。

### 真缺陷（都不是“门禁太严”）

1. **冷/暖构建标记没有传给无 fork 的子进程**（PC3）：父进程调度器按“链接清单是否
   存在”决定不写函数级 IR 缓存，但 Windows 的模块编译在 `--emit-module` 子进程里，
   子进程看不到父进程的判定 → 冷编也写缓存 → 「首轮重编应全部 miss」变成全 hit。
   修法：`build_scheduler` 在冷构建时给子进程加 `--no-firc`，`api.yh` 解析后置
   `c_firc_write_off`；`--emit-module` 的参数上限 20 → 22。
2. **`[c].sources` 在 Windows 上用 gcc**：`mb_select_linker` 只在 Darwin 选 clang，
   Windows 目标拿到 `gcc` → `CreateProcess` 找不到 → 8 个 C 互操作用例全红。
   修法：Windows 目标选 `clang`（LLVM 自带 COFF 后端，Windows 宿主默认 msvc 目标）。
3. **`[c].libs` 生成 `-lm` 传给 lld-link**：COFF 没有 `-l` 语义。修法：Windows 目标
   跳过并打印一条提示（符号要由 C 源或 SDK 闭包提供）。
4. **安装布局的标准库发现失效**（`os6-default-stdlib`）：`mb_self_path` 是反斜杠路径，
   而 `mb_try_default_stdlib` 直接拼 `/../libs`，`pj_canon` 按 `/` 切段 → 混合分隔符
   让 `..` 解析失败 → `<root>/bin/yh` 找不到 `<root>/share/yh/libs`。
   修法：拼路径前把目录分隔符统一成 `/`（Win32 API 同样接受）。
5. **外部命令用全路径启动的形式回归**：上一轮为修 `yh run` 的 `.build/foo` 加了
   `lpApplicationName` 规范化，但 CreateProcess 一旦收到 application name 就**不再
   搜索 PATH**，"clang"/"gcc" 这类裸命令因此找不到。修法：只有 argv[0] 含分隔符/盘符时
   才传 application name（`yh_is_path_like`）。
6. **测试入口/门禁的 POSIX 假设**：退出码按 POSIX 只暴露低 8 位（`return 1023` 在
   Windows 上可见 1023，POSIX 上是 255）→ 门禁统一按 `& 0xFF` 比较；`platformsource`
   fixture 缺 Windows 目标源 → 补 `main.windows.x64.yh`（真调用 kernel32 并返回 32）。
7. **零 CRT 缺两个 libc 基础符号**：`abs`/`putchar` 由 SDK 支撑对象提供
   （`__yh_abs`/`__yh_putchar` + `/alternatename`），静态 CRT 存在时仍用 CRT 版本。

### 门禁脚本按平台分流（而不是降级）

- `tests/selfhost/llvm-function-cache.py`：Windows 上通过（`--no-firc` 生效）。
- `tests/selfhost/link-cache.py`：新增 `windows_main`。Windows 的 `--stats` 里
  `asm` 统计的是**外部汇编器**调用（内嵌后端恒 0），因此改用 link 计数与对象字节身份
  验证同一组边界：冷编 link=1；热编 link=0 且对象不变；损坏对象被重建回原内容；
  损坏可执行文件重链 1 次。
- `tests/selfhost/native-selfhost.py`：识别 Windows 宿主（`llvm_mode`/`host_triple`/
  种子探针走「项目构建」而不是「单文件 -o」，后者是种子的已知边界）。
- `tests/modules/build-check.py`：新增 `WINDOWS_SKIP` 边界表（22 例）——宿主 libc/libm
  （`strtod`/`cos`/`pow`/`lrint`）、`dup2`、`system()`、Winsock、ELF/Darwin 归档组；
  这些是**决定点 W1-2b-2（零 CRT 还是接 UCRT）**未定前的明确边界，按 SKIP 记录，
  不是隐藏失败。
- `tests/selfhost/llvm-architecture.py`：Windows 上用 ASCII 工作区名（内嵌 lld 只认
  ANSI 路径），并在 `require` 里容忍 `stdout=None`。

### 仍开放（不在本轮）

- **W1-2b-2 决策**：零 CRT（现状，只链 kernel32）还是接 UCRT 导入库。选择后者可一次
  解决 `strtod/abs/cos/pow/lrint/dup2/system` 等全部 C 库符号，代价是用户程序依赖
  `ucrtbase.dll`（与方案 D2 冲突）。当前按 SKIP 明确记录。
- **W2-8 COFF 整库加载**：`/wholearchive:` 未实现；当前桥入口都被直接引用，不需要整库。
- **W2-2 闭包位置**、**W2-5b CI runner**、**W2-0 0.0.11-rc 种子**：同上轮记录。
## 2026-11-02 W2-7 收口：标准库 Windows 平台变体（`just test` 在 Windows 全绿）

**结果**：`libs/sys`、`libs/os`、`libs/time`、`libs/json`、`libs/toml` 全部有 Windows 后端，
`just test` 在 Windows/x86_64 **首次全绿**：语法正例 82/82、反例 49/49、运行语料
**209/209**（9 例按 `// platform:` 跳过）、fail 137/137、pass 9/9、`libs` 语言内测试
**122/122**、compiler-tests 4/4、arch-check 通过；原生两代固定点
`621d03d3dbf183d3…` 逐字节相同。

### 新增的平台变体（后端映射）

| 文件 | Windows 后端 |
| --- | --- |
| `libs/sys/05_errno.windows.yh` | `GetLastError()` → POSIX errno 映射（对外契约与 Linux/Darwin 一致） |
| `libs/sys/10_constants.windows.x64.yh` | 同一套 POSIX errno/O_* /socket 常量；无 syscall 号 |
| `libs/sys/30_file.windows.yh` | 复用编译器运行时的 prelude `open/read/write/close/mkdir/unlink/rename`（同一张 fd 表）+ `GetCurrentDirectoryA/SetCurrentDirectoryA/RemoveDirectoryA`；`*at` 只认 `AT_FDCWD`；目录枚举走 `FindFirstFileA/FindNextFileA/FindClose` |
| `libs/sys/40_memory.windows.yh` | `VirtualAlloc/VirtualFree`（匿名可写子集；文件映射返回 `-ENOSYS`） |
| `libs/sys/50_time.windows.yh` | `GetSystemTimeAsFileTime`（realtime）+ `QueryPerformanceCounter/Frequency`（monotonic）+ `Sleep` |
| `libs/sys/60_process.windows.yh` | `getpid/exit`；fork/exec/wait/signal 如实返回 `-ENOSYS` |
| `libs/sys/70_socket.windows.yh` | 全部 `-ENOSYS`（Winsock 归 NET 系列任务，先保证可编译可链接） |
| `libs/os/20_directory.windows.yh` | 目录读取器（`FindFirstFileA` 句柄 + 模式串 + 320 字节 `FIND_DATA`）；`get_cwd/change_dir` |
| `libs/os/30_process.windows.yh` | `CreateProcessA` + 进程表（pid→HANDLE，64 槽）+ `WaitForSingleObject/GetExitCodeProcess`；`spawn/wait/exit_now` |
| `libs/time/time.windows.yh`、`libs/json/75_files.windows.yh`、`libs/toml/70_files.windows.yh` | 与 Linux 版共用同一套接口（时间走 `sys.read_clock`，文件走 `os` 结果接口） |

配套：`os.platform()` 认 `windows`；SDK 导入面新增 14 条 kernel32 导出
（目录/进程/内存/时钟/`GetFileType`）；`compiler/windows-sdk/chkstk.c` 增加
`__yh_isatty`/`__yh_rmdir`/`__yh_close_handle` 与 `/alternatename`
（`isatty`/`rmdir` 在零 CRT 用户程序里没有 libc 可解析）。

### 这一轮抓到的真缺陷（都是跑门禁暴露的）

1. **负 fd 被当标准描述符**（`backend/llvm_windows_runtime.yh`）：运行时的 `close`
   只判 `fd < 3`，于是 `close(-1)` 返回 0、`os.close_fd(-1)` 静默成功。
   修法：先判 `fd < 0` 走失败分支。
2. **`_fltused` 在 O2 下被丢弃**（`backend/llvm_module.yh`）：`linkonce_odr` 属可丢弃
   定义，GlobalDCE 在“本对象没引用它”时删掉，而引用方是另一个含浮点的模块 →
   `yh -O2 run` 报 `undefined symbol: _fltused`（O0 不复现）。修法：同时登记
   `@llvm.compiler.used`。
3. **测试入口用单字节编码用例号**（`testkit/test_cmd.yh` + 生成入口）：`'a'+n` 在
   n≥31 时字节 ≥0x80，Windows 的 ANSI 命令行往返会改坏它 → 32 号以后的用例一律
   「未被断言捕获的失败退出」（cli 的 43 个用例里 11 个必红）。修法：用例号改十进制文本，
   入口按十进制解析；同时把测试函数名从「全局文件号」改成「模块内文件序号」，否则
   无 fork 的模块子进程重新索引后与父进程编号不一致（`single-file-*` 三例）。
4. **单文件测试的 `--scan-file` 误约束标准库**（`build/project_index.yh`）：子进程里
   `string/memory` 会「模块不存在」。修法：新增 `pj_scan_applies(proj)`，扫描过滤只对
   被测项目（`src` 前缀匹配）生效。
5. **`yh run` 相对路径启动失败**（`llvm/windows_shim.c`）：`CreateProcessA` 的
   `lpApplicationName` 拿到 `.build/foo` 这种前向斜杠路径 → `ERROR_FILE_NOT_FOUND`。
   修法：`yh_app_path` 规范成反斜杠后显式传 application name。
6. **测试子进程的 `YH_TEST_RECORD` 串台**（`windows_shim.c`）：并行 4 个用例时
   `SetEnvironmentVariableA` + `CreateProcess(NULL env)` 有竞态。修法：`yh_env_with`
   为每个子进程拼显式环境块。
7. **门禁自身的平台假设**：`build-check.py` 的默认 target 不认 Windows、`symlink_to`
   需要特权（改副本）、PATH 里 `yh` 的解析差异、含换行的目录名在 Win32 非法；
   `native-selfhost.py` 不认 Windows 宿主（`llvm_mode`/`host_triple`/种子探针）；
   `justfile` 里未加引号的 workdir 会被 bash 吞掉反斜杠（cc2 输出路径变
   `C:Users...`）；`llvm-architecture.py` 的中文工作区名超出 ANSI lld 能力。

### 新增用例

- `tests/modules/projects/osdirswin/`（目录枚举/类型判定/空目录/重复关闭/cwd 往返）。
- `tests/yh-run/run/213-windows-fd-errors.yh`（`// platform: windows`：负 fd 三条 +
  前向斜杠路径的 mkdir/open/rename/unlink/rmdir 往返）。
- `build-check.py` 新增 `OS_WINDOWS_CASES`（sysfiles/osfiles/osdirswin/osprocess/
  systime/sysmemory 六个夹具在 Windows 上跑）。

### 仍然未完成（已写 todo，W2-9）

`just selfhost-native` 在 Windows 上还有三处红的：`llvm-function-cache.py`
（冷编在 Windows 会写函数缓存 ⇒ “首轮重编”命中数与期望相反）、`link-cache.py`
（统计外部汇编器调用次数，COFF 走内嵌 lld 没有这些调用）、`build-check.py`
（42 例，多为 Linux/POSIX 专属或跨目标用例）。

## 2026-11-02 W2-5 收口：Windows 宿主接进 just/取种 + 三个真缺陷修复

**结果**：Windows 宿主的 `just`/`just llvm-host`/`just build`/`just seed` 分支全部接通，
原生两代固定点重新达成（gen2 == gen3 == `33922de9d51aa8dd…`）；同时在这一轮真跑门禁时
抓到并修掉**三个会让 Windows 门禁整体变红的真缺陷**（都不是计划内的项）。

- **W2-5 justfile/取种/驱动**：`llvm_host` 加 `windows-x86_64` 分支；新增
  `tools/llvm-windows-host.py`（`prepare`/`status`/`shim`：读 `[link-windows-x64]` 四组
  归档、校验存在性、把整组内容的聚合 SHA-256 写进
  `$YH_LLVM_CACHE/llvm-host-windows-x86_64/host.json`，`status` 失效退 3）；
  `tools/seed-build.py` 的 `HOST_DRIVERS` 接上该驱动（清单模式下不需要 shim，`shim_dir` 为空）；
  `justfile` 新增 `just llvm-host-status`。**实测价值**：桥归档一重编，`status` 立刻报
  「闭包内容已变化：重新运行 just llvm-host 刷新记录」，不再静默复用旧记录。
  **未完成**：`[link-windows-x64]` 的归档仍在仓库外（`D:/tmp/llvm-win/...` + MSVC CRT 绝对
  路径），搬进缓存根并用 Release 资产分发仍归 W2-2；CI 的 `windows-x64` job 需要 Windows
  runner（当前 runner 只有 `macos-arm64`/`linux-arm64` 两个 label），先不接。

- **缺陷 1（严重，`compiler/windows-sdk/chkstk.c`）**：栈探测桩违反了它自己注释里的契约
  「不改变 RAX」——循环里 `subq $4096, %rax`，而 LLVM 的序言是
  `mov eax,<帧>; call __chkstk; sub rsp, rax`，于是调用方只分配了除不尽的余数
  （160 KB 帧只 `sub rsp,3432`）。**任何 >4 KB 的帧在第一次访问局部变量时 0xC0000005**，
  表现是 `29-stress-capacity`、`148-deep-struct-field-offset`、`llvm-runtime-memory`
  三例同时崩且一行输出都没有。修法：探测计数改放 `r11`，`%rax` 全程不动。
  验证：200 KB 帧的探针程序由崩改为输出 `bigframe=1,2`；运行语料 205 → **208/208**（9 例
  仍按 `// platform:` 跳过）。

- **缺陷 2（严重，`compiler/llvm/windows_shim.c` + `windows_link.yh` + `lld_bridge.cpp`）**：
  无 fork 宿主的链接 worker（`yh --lld-link <rsp>` 子进程）在**父进程 stdout 是管道时
  100% 失败**（6/6），报 `failed to write output '...': invalid argument`，重试 5/5 仍失败。
  用 8 组 std 句柄组合的探针定位（矩阵见设计文档 §6.8）：子进程 stdout 必须接 NUL、stderr
  不能继承管道。修法：新增 `yh_win_spawn_link`（stdout→NUL、stderr→`<rsp>.err` 文件），
  父进程用 `mb_coff_forward_diag` 回放诊断后删除；同时把子进程的启动/退出码失败写进
  stderr（原来完全静默），并让 `lld_bridge.cpp` 在 `YH_LLD_STDERR` 下把 lld 诊断直接写
  stderr——lld 的 `fatal()` 在 Windows 走 `TerminateProcess`，内存缓冲里的诊断会一起消失。

- **缺陷 3（`compiler/build/llvm_emit.yh`）**：`--emit-asm` 把中间汇编写到硬编码
  `/tmp/yh-llvm-asm-<pid>.s`，Windows 上 `/tmp` 被解释成当前盘符下的 `	mp` → mkstemp 失败
  → 「内嵌 LLVM：目标文件原子写入失败」。seed 与新一代编译器都复现，属既有缺陷。
  修法：Windows 宿主取 `TEMP`/`TMP`，都没有时退到当前目录。修好后 `just test-windows-target`
  的交叉汇编用例才可能过。

- **两处门禁自身与实现不一致（顺带修）**：`tests/selfhost/llvm-windows-sdk.py` 的负例仍用
  `Sleep`（它随 usleep 的零 CRT 实现早已进导出面）→ 改用真实但不导出的 `Beep`；
  `tests/selfhost/llvm-windows-target.py` 生成的临时 `project.toml` 直接把 `C:\...`
  拼进基本字符串（非法转义）→ 改用 `json.dumps`。

- **门禁实测（Windows 11 / x86_64 原生）**：语法正例 82/82、反例 49/49、运行
  **208/208**（跳过 9）、fail 137/137、pass 9/9、compiler-tests 4/4、arch-check 通过、
  `test-windows-sdk` 通过、`test-windows-target` 8/8 通过、原生两代固定点
  `33922de9…` 逐字节相同。
  **仍红（阻塞在 W2-7）**：`tests/modules/test-check.py` 的 3 个 `single-file-*`、
  `tests/fmt/interp.py` 的 4 例、`just libs-test`——根因是 `libs/sys` 没有 Windows 平台变体
  （`sys.ENOENT` 等常量不存在），`libs/os` 因此在模块子进程里编译失败。
  这属于 W2-7「标准库平台变体」的未完成项，不是本轮改动的回归。

- **arch-check 预算**：build 11363 → **11553**（本轮链接子进程 stdout/stderr 重定向与诊断
  回放 +50，其余为 W2 既有），module_build 2252 → **2275**，main 381 → **405**，
  testkit 1592 → **1671**，`gen.G()` 168 → **169**。

## 2026-10-28 W2 收口：Windows 原生 yh.exe 与首个 `bin/yh-windows-x64` 种子

**结果**：W2 的核心目标已达成——交叉出的 yh.exe 在真 Windows 上自编两代，产物逐字节相同
（SHA-256 `0969209e…`）；Windows 目标三道门全绿（target 8/8、ABI 1/1、语料 208/208），
本地种子落盘为 `bin/yh-windows-x64`（配套 `.sha256`）。Linux 宿主除 ANTLR 参考层外
各层重跑并重新滚种（`04e7db6b…`）。

- **从上一轮遗留的桥回归开始**：`bridge.c` 的 Windows 适配把非 Windows 分支的
  `initialize_targets_once_call` 改成了自递归（`pthread_once` 调用丢失），Linux 的
  `llvm-host prepare` 直接 `-Werror=infinite-recursion` 失败。恢复为
  `pthread_once(&targets_once, initialize_targets)`；Windows 分支保持 InitOnce。
- **静态 LLVM 闭包**：`[link-windows-x64]` 补 lld 6 + LLVM 114 + 静态 CRT/系统导入库
  （libcmt/libcpmt/libvcruntime/libucrt/oldnames/comsuppw、kernel32/ntdll/ole32/oleaut32/
  uuid/advapi32/shell32/user32/psapi）。**关键坑**：清单里的 `LLVM-C.lib` 是 DLL 导入库，
  链接后 yh.exe 实际从 `LLVM-C.dll` 取 C API（gdb 栈里直接看到该 DLL），移除后才是真静态。
  另移除 `[c] sources=bridge_stub.c`：清单已强定义桥，Windows 上的弱桩会与 CRT/桥冲突。
- **COFF 的 weak 与 COMDAT**：运行时、printf、`_fltused`、fd 全局原本只靠 `weak`/
  `linkonce_odr`；ELF/Mach-O 能合并，COFF 却报 duplicate symbol。Windows 目标统一加
  `comdat any` + 函数 `comdat($name)`；`llvm_runtime_weak_signature` 收敛了 17 处发射点。
- **入口与栈探测的双形态**：零 CRT 用户程序与静态 CRT 自举共用一套链接模板——
  `/entry:mainCRTStartup` + `/alternatename:mainCRTStartup=__yh_zero_crt_start`，
  有 CRT 时用 CRT 启动（C++ 静态构造、argv/envp、stdio 全就位），零 CRT 才落到自备桩；
  `__chkstk` 同理改为 SDK 桩导出 `__yh_chkstk` + `/alternatename`，CRT 自带时不再重复定义。
- **Windows 运行时修复**：`open` 加 `FILE_FLAG_BACKUP_SEMANTICS`（POSIX 允许 open 目录，
  编译器用 `path/.` 探目录）；fd 表从「只增不减」改为扫空槽复用（>64 次 open 后必失败，
  表现为随机的「无法打开文件」）。
- **无 fork 的模块编译**：放弃进程内串行复用（W2-4a 的 stage 7 快照污染），改为
  `mb_spawn_module_child` 用 `CreateProcessA` 重入 `--emit-module`，每模块一个干净进程；
  子进程补「装载主项目 + 重建拓扑序」。附 `compiler/llvm/windows_shim.c`：
  stat（Linux 布局）/realpath/setenv/usleep/fork/waitpid/kill + `yh_win_spawn_wait`。
- **无 fork 的 COFF 链接**：lld 在进程内链接后仍持有输出句柄到进程退出（fopen EACCES），
  因此直接写最终路径，跳过格式复核与链接缓存哈希（下一轮重链，产物完整）。
- **门禁**：Windows target 8/8、ABI 1/1、语料 208/208（真 Windows 执行）；
  Linux 语法 82/82 + 反例 49/49、运行 359/363、modules 全过、libs 122、
  compiler-tests 4/4、fmt 10、arch-check 通过、`selfhost-native` 项目 133/133。
  ANTLR 层在 WSL 缺 `antlr4-python3-runtime`（无 pip），按仓库约定属本地参考层，未跑。
- **剩余**（已写 todo）：W2-5 just 的 windows 宿主分支与 CI；W2-4b 的 lld/测试子进程
  （`yh run`/`yh test` 仍依赖 fork）；W2-2 闭包目录与 Release 资产化；W2-0 发布 0.0.11-rc
  （Release 0.0.10 种子不认识 windows 标记）；W2-8 COFF 整库加载。

## 2026-10-27 W2-4a 接线：无 fork 宿主走串行构建（已接通，待修复）

**结果**：Windows 宿主（无 `fork`）的构建路径已接线，并用**可在 Linux 复现的钩子**首次实测，
把「串行复用索引快照」的隐患直接暴露成一条明确诊断。

- **接线**（4 处，最小外科改动）：
  - `build/process.yh::mb_can_fork()`：Windows → 0；另有 `YH_NO_FORK=1` 测试钩子，
    让 Linux/Darwin 也能强制走串行路径（否则这段代码只有 Windows 机器能覆盖）；
  - `mb_spawn_indexed_module`：无 fork 时在**本进程**同步调 `mb_emit_indexed_module`，
    成功返回 `pid=0`；
  - 等待循环：`pid==0` 视为「已完成」，直接进入发布/提交分支（不调 `waitpid`）；
  - `mb_sched_cancel_workers`：跳过 `pid==0`（`kill(0, sig)` 会打到整个进程组）；
  - Windows 运行时补 `getpid`（GetCurrentProcessId）与 `getppid`（0，串行路径不 fork），
    并加进 `llvm_runtime_supplies_symbol` 的 win64 名单。
- **实测（`YH_NO_FORK=1` 在 Linux 上编编译器）**：
  ```
  yh: 受检模块文件快照校验失败        ← check.verify_checked_module stage 7
  yh: 无法启动模块编译 worker
  ```
  这正是方案里预警的「串行 + 会话 reset 不完整」：fork 路径靠 COW 隔离，串行模式里
  模块编译会改动父进程的索引快照（`gs.p_files[i]` 的 token/decl 数组与 source 视图），
  第二个模块的 `checked_verify_files` 立即不成立。
- **下一步（已写进 todo W2-4a 修复）**：串行模式每模块前后恢复索引快照，或改为
  「每模块重新索引」；验收标准是 `YH_NO_FORK=1` 与并行路径产物**逐字节相同**（固定点）。
- **Linux 侧未回归**：串行分支默认关闭，语法 82/82 + 反例 49/49、运行语料 358/362、
  `just` 冷编正常；`max_build_lines` 11207 → 11241（+34，已注明）。

## 2026-10-27 W2 决策修正：Windows 宿主二进制的运行库——静态 CRT（可自包含）

上一轮把「MSVC 运行库依赖」说得过重：那些 `msvcprt/vcruntime` 是**动态**导入库，
不是唯一选项。本机实测结论：**静态链接完全可行，yh.exe 可以自包含**。

- **实测（本机 VS 14.41 + Windows SDK 10.0.22621）**：
  `clang-cl /MT` 编一个用 `std::vector/std::string/printf` 的 C++ 程序，
  `lld-link /nodefaultlib` 只给 `libcmt.lib + libcpmt.lib + libvcruntime.lib + libucrt.lib + kernel32.lib`
  → 产物 148 KB，**导入表只有 KERNEL32.dll**，运行输出正确、退出码 7。
  即：没有 `msvcp140.dll`/`vcruntime140.dll`/`ucrtbase.dll` 依赖，不需要 VC++ 可再发行包。
- **对 Lane E 的硬约束**：LLVM/lld 必须用 `-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded`
  （`/MT`）构建。否则归档是 `/MD` 产物，与静态 CRT 混链会 `LNK2038 RuntimeLibrary mismatch`。
- **对自举链接的约束**：静态 CRT 自带 `__chkstk`，所以编译 yh 自身时**不能再注入**
  `compiler/windows-sdk/chkstk.c` 的 `__chkstk.obj`（会重复定义）；用户程序（零 CRT）
  仍然需要它。这条要作为 `[link-windows-x64]` 与模板参数的一个开关。
- **许可边界**：静态 CRT/STL 库**可以**链进我们的二进制（这正是它们的用途），
  但 `.lib` 文件本身**不入库、不进种子**——只由持有 VS 的构建机在链接时提供，
  与 Darwin SDK 的处理方式一致。
- **Zig 的做法（对照）**：Zig 不打包 MSVC 的 CRT/STL（授权不允许），
  `-target *-windows-msvc` 时自动探测用户的 VS 安装（与本机做法相同）；
  它自带的是 **mingw-w64**（headers + 导入库，`lib/libc/mingw/`），
  所以 `-target *-windows-gnu` 无需外部工具链。它的发行二进制自包含（不要求 VC++  redist），
  靠的正是「构建期依赖工具链、发布期静态链接」——我们要复制的就是这个实践，而不是打包 CRT。

## 2026-10-27 W2 启动（并行）：宿主身份与 Windows 宿主文件落地，LLVM 宿主闭包开始构建

**结果**：编译器整套源码可以按 `--target x86_64-pc-windows-msvc` 通过前端检查；
Windows 宿主的三个平台文件就位；Lane E（Windows 静态 LLVM/lld 闭包）已在后台取源。

- **Lane F1（W2-1 / W2-3a）**：
  - `gen/target_info.yh`：`target_host_info` 增加 `$if (windows)` 分支（x64 → win64-msvc；
    arm64 明确返回 -1，留给矩阵收尾）；
  - `build/project_dir.windows.x64.yh`：`FindFirstFileA/FindNextFileA/FindClose` 枚举目录，
    手写 `WIN32_FIND_DATAA` 布局（属性 +0、cFileName +44），复用 `pj_dir_add` 的名字池与
    `.` 跳过规则；
  - `build/clock.windows.x64.yh`：`QueryPerformanceCounter/Frequency`，先算秒与余数再换算
    纳秒（避免 `counter*1e9` 在长时间运行后溢出 u64）；
  - `backend/llvm_bind.windows.yh`：内嵌桥的 C ABI 声明（与 linux/darwin 同名同签名）。
  - **验证**：`cd compiler && ../yh check --target x86_64-pc-windows-msvc` → **检查通过**
    （前端全量编译，含新宿主文件）；Linux 侧 `just` 冷编 38 s、语法 49/49、运行 358/362、
    arch-check 通过。
- **Lane E（W2-2，后台）**：`llvm-project-21.1.8.src.tar.xz`（151.5 MB，SHA-256 已按
  `vendor/llvm/sdk.lock.json` 校验）下到 `D:\tmp\llvm-win`（C: 只剩 4.9 GB，必须用 D:），
  随后用 MSVC 14.41 + cmake 4.1.2（VS 生成器，无 ninja）配置
  `Release / targets=X86;AArch64 / projects=lld` 的静态构建。本机实测吞吐约 80 KB/s，
  取源预计 30 分钟，构建预计 40–90 分钟（下一轮继续）。
- **必须记录的流程前置（否则 CI 会红）**：`$if (windows)` 与 `*.windows.*.yh` 后缀都依赖
  「种子认识 windows 标记/标签」，而这只存在于**本地滚过的种子**（W0-2a）；CI 取的是最新
  **Release** 种子（0.0.10，不认识）。所以 W2 这批改动正式合入前，需要先按发版流程把
  0.0.11-rc 发出去（种子自动来自上一个 Release），否则分支门会因旧种子无法识别 `windows`
  而失败。这条已写入 todo 的 W2 章首。
- **下一步**：Lane E 完成闭包 → `compiler/project.toml` 增 `[link-windows-x64]` 组
  （桥 + LLVM/lld 归档 + `__chkstk.obj` + 运行时导入库决策）→ 交叉编出 `yh.exe` →
  W2-4（无 `fork` 的串行构建 + `getpid`）→ 原生固定点与首个 `bin/yh-windows-x64`。

## 2026-10-27 W1-2b 交付：Win64 按值聚合 ABI（与 clang 编的 C 桩互操作）

**结果**：`@[extern] struct` 可以按值传参与返回，形态完全对齐 MSVC ABI；用 clang 编出的
C 桩做**真实互操作**验证（4/8/12 字节 + 纯浮点聚合，参数与返回都覆盖）。

- **规则（clang oracle 实测，不是推测）**：
  | 聚合大小 | 参数 | 返回 |
  | --- | --- | --- |
  | 1/2/4/8 字节 | 整数寄存器 `i8/i16/i32/i64`（**纯 float 聚合也是整数寄存器**） | 同左（RAX） |
  | 其他 | **普通 `ptr`（按引用，无 `byval`）** | `void` + hidden `ptr sret` |
- **实现**：
  - `llvm_abi_classify` 增加 win64 分支（size∈{1,2,4,8} → 单 INTEGER 分片；其余 MEMORY），
    其余 SysV 分片逻辑不动；
  - `llvm_signature` 与 `llvm_abi_emit_c_call` 的 MEMORY 参数在 win64 下发射**普通 ptr**
    （SysV 仍是 `byval`）——这两处是唯一的形态差异；
  - `llvm_abi_supported` 的 win64 分支改为放行标量/指针/struct/union，只继续拒绝用户裸变参
    （prelude 的 printf/open 走 yh ABI 分支）；
  - preflight 诊断改文（不再说“按值聚合待 W1-2b”）。
- **门禁**：新增 `just test-windows-abi`（`tests/selfhost/llvm-windows-abi.py`）——
  clang 编 `shim.c` → `llvm-ar` 打包 `.lib` → yh 项目经 `[link-windows-x64]` 链接 →
  校验 PE/`/Brepro` 可复现 → Windows 侧实跑比对
  `small=2 eight=5 big=9 f4=5 f8=9` / `ms=13 mb=24,4,4`；CI 的 linux-arm64 job 同样加上该门。
- **踩坑**：① 前端要求 C 共享布局必须写 `@[extern] struct`（否则报「C ABI 不支持该参数类型」）；
  ② `f32` 字段赋值需要 `.to_type(f32)`；③ 多行 `||` 链后再接 `? :` 的写法 yh 不接受
  （改成逐条 if 赋值）。
- **验证**：Linux 回归（语法 49/49、运行 358/362、模块/fmt/arch-check）与 `selfhost-native`
  332 s、项目用例 133/133 全绿；Windows 侧三份清单全过（ABI 1/1、target 8/8、语料 207/207）。

## 2026-10-27 W1-3c 真修：`__chkstk` 栈探测桩（大帧解锁，语料 207/207）

**结果**：Windows 目标不再限制栈帧大小。`__chkstk` 由 SDK 里的一个 naked-asm C 桩提供，
LLVM 的页探测保持开启；`29-stress-capacity`（**160 KB 帧**）解除平台标注并在 Windows 上跑对，
语料 **207/207**。

- **桩**（`compiler/windows-sdk/chkstk.c`，唯一新增 C 源）：按 MSVC 契约实现——
  调用方把字节数放 RAX，桩按 4 KB 步长 `sub`+`testq mem,reg` 触碰每一页触发 guard page 增长，
  不改 RAX/RSP，只用 volatile 的 r10/r11。实测：64 KB 帧的 C 程序只加这个 `.obj` 就能链接并运行。
- **生成**：`tools/windows-sdk.py` 新增 `--clang` 与 `generate_object()`，把 `chkstk.c` 编成
  `__chkstk.obj`（696 字节）写进 `<sdk>/lib/`，并把源码/输出/sha256/编译器身份记进
  `identity.json`；`check` 额外核验它是 x86_64 COFF 且导出 `__chkstk`。
  `manifest.json` 新增 `objects` 段声明该桩。
- **链接**：`mb_coff_link_prefix` 现在固定带两个外来输入（`kernel32.lib` + `__chkstk.obj`），
  两者都进缓存身份（`mb_hash_coff_identity`）；`mb_windows_link_inputs` 一次取齐。
- **后端**：移除 `"no-stack-arg-probe"`（探测回来了）与 `llvm_frame_guard`（16 KB 上限取消）。
- **踩坑**：第一版把 SDK 路径解析塞进 `mb_coff_link_prefix` 并返回指向**本函数栈缓冲**的指针，
  链接时路径变成野指针（`lld-link: undefined symbol: GetStdHandle` 其实是导入库路径瞎了）；
  已改回「调用方持有缓冲」，`max_function_lines` 700 → 703（mb_link 703，B2 拆 link 簇时下沉）。
- **门禁**：`test-windows-target` 的「大栈帧负例」改成**正例**（32768 字节数组必须编出并跑对
  `big sum=98301`），共 8 例；Windows 侧 8/8。
- **验证**：语料 run 207/216（0 失败，9 跳过）、fail 137/137、pass 9/9；Windows 侧 207/207；
  Linux 回归（语法 49/49、运行 358/362、模块/fmt）与 `selfhost-native` 328 s、项目用例 133/133 全绿。

## 2026-10-27 W1-3d + CI 接线：Windows 文件 API 落地，Windows 门进 CI

**结果**：`open/read/write/close/mkdir/unlink/rename` 在 Windows 上可用（fd 表 + Win32 映射），
文件往返在真 Windows 上验证通过；Windows 目标的三项门接入 Gitea CI 的 linux-arm64 job。

- **W1-3d 实现**（`backend/llvm_windows_runtime.yh` 的 `llvm_windows_runtime_write_files`）：
  - fd 表：`@__yh_fd_handles = linkonce_odr global [64 x i64]` + `@__yh_fd_next`，
    槽 0..63 对应 fd 3..66，句柄以 i64 存（0=空槽）；0/1/2 是标准流。
  - `open(path, flags, ...)`：flags 按 POSIX 位解释（0x1 O_WRONLY / 0x2 O_RDWR /
    0x40 O_CREAT / 0x200 O_TRUNC / 0x400 O_APPEND）→ `CreateFileA` 的
    GENERIC_READ|WRITE + CREATE_ALWAYS/OPEN_ALWAYS/TRUNCATE_EXISTING/OPEN_EXISTING；
    O_APPEND 用 `SetFilePointer(末尾)` 模拟；成功返回 fd>=3，失败 -1。
  - `read`/`write` 统一支持 0/1/2 与 >=3（write 走短写循环）；`mkdir`/`unlink`/`rename` →
    `CreateDirectoryA`/`DeleteFileA`/`MoveFileExA(替换)`。
  - 导入面新增 5 个 kernel32 导出（CreateFileA / SetFilePointer / MoveFileExA /
    CreateDirectoryA / DeleteFileA），导入库 3934 字节，manifest `def_sha256` 同步。
  - ABI 门放行 prelude 的 `open`（与 `printf` 同为运行时自己发射的裸变参）；
    `llvm_runtime_supplies_symbol` 补 open/close/mkdir/unlink/rename（避免 declare+define 冲突）。
- **踩坑**：write 的短写循环里 phi 挂在 `%advance` 上但实际前驱是 `%step`
  （`PHI node entries do not match predecessors`）——生成器写的 IR 也要过 LLVM verifier。
- **门禁**：`just test-windows-target` 增至 **7 例**（新增 `file_api`：写→读→改名→删除，
  断言 `read=10 ok=1` 与 `rename=0 unlink=0`）；Windows 侧 `run-exe.py` 7/7；
  整份语料仍 **206/206**。
- **CI 接线**（`.gitea/workflows/ci.yml` + `.gitea/ci/Dockerfile`）：
  linux-arm64 容器内新增 `just test-windows-sdk` / `test-windows-target` /
  `test-windows-corpus`（编译侧三项）；镜像加 `llvm-18 lld-18` 并软链
  `llvm-dlltool`/`llvm-readobj`/`llvm-nm`/`lld-link`（编译器自身用内嵌 lld，CLI 只用于
  导入库生成与核对）。**本机无容器运行时**，该改动只做了 YAML 解析与逻辑核对，
  首次 CI 跑需要观察（红灯按 todo 立项）。
- **验证**：语法 49/49、运行 358/362、模块/fmt/arch-check、`selfhost-native` 334 s 与
  项目用例 133/133 全绿；`llvm_windows_runtime.yh` 486 行（仍在 500 行以内）。

## 2026-10-27 W1-3c/W1-8 交付：栈帧上限守护 + Windows 后端设计文档

**结果**：大栈帧从「运行期静默崩溃」变成「编译期可操作拒绝」；Windows 后端有了契约与边界的
唯一真源文档（W1 目标面到此收口，语料仍 206/206）。

- **W1-3c（守护片）**：先实测阈值——`[N]u8` 局部数组在 Windows 上的崩溃点：N=4096/8192/16384
  正常，**N=32768 起必崩**（PE 的栈只在触碰 guard page 时按页增长，没有 `__chkstk` 时一次
  `sub rsp, N` 会跨过多个 guard page）。据此加 `llvm_frame_guard`：win64 下统计每函数
  `IR_OP_ALLOCA` 常量尺寸总量，**>16 KB 直接编译期拒绝**，诊断给出去向（「改成堆分配」）。
  实测：32 KB 帧与 `29-stress-capacity`（160 KB）都被拒；16 KB 帧仍可编。
  `just test-windows-target` 增加该负例（要求诊断含「栈帧超过 16 KB」）。
  语料里帧 >4 KB 的另有 `148-deep-struct-field-offset`(12.3 KB)、`llvm-runtime-memory`(8.3 KB)，
  实测在 Windows 上正常，因此阈值取 16 KB 而不是 MSVC 的 4 KB——**以证据定阈值**，
  避免把能跑的代码拒掉；真修（`__chkstk` 或堆临时）留在 todo。
- **W1-8**：新增 `docs/03-design/yh-Windows-LLVM后端设计.md`：目标身份（含「两份表必须同改」）、
  Win64 ABI 边界（标量-only、无 signext、聚合强转）、零 CRT 运行时契约（malloc/free/printf/
  write/read/exit 别名）、`mainCRTStartup` 与 argv、链接模板与导入库查找顺序、
  **五个必记坑**（PIC 重定位、`_fltused`、`declare`+`define`、alloca 入口块、栈帧上限）、
  不支持边界表、与 Linux/Darwin 的差异表、门禁两侧分工。`docs/yh.g4` 未动。
- **W0-4 复核为误报**：早先看到的「Windows 被写成 n」其实是 `rg -rn "Windows"` 里 `-r` 是
  **replace**，把输出里的匹配替换成了 `n`；仓库文档原文一直是「Windows」。已在 todo 记下，
  不再作为定稿任务。
- **W1-6 收尾**：`link_inputs` 增加 Windows 库输入分支——`.lib` 按 ar 归档（kind=1）接受，
  `.dll` 必须是 `MZ`→`PE\0\0` 且 machine `0x8664`（否则给目标级诊断）；
  `just test-windows-target` 新增两个断言（合法 `.lib` 参与链接、非 PE 的 `.dll` 被拒）。
  `max_build_lines` 11077 → 11101（+24，随 B2 的 link 簇下沉）。
- **验证**：`just test-windows-target` 全绿（6 例 PE + 大栈帧负例 + 库输入两例）；
  `just test-windows-corpus` + Windows 侧 `run-exe.py` → **206/206**；`just test-windows-sdk` 全绿；
  Linux 回归（语法 49/49、运行 358/362、模块/fmt/arch-check）与 **`selfhost-native` 339 s、
  项目用例 133/133** 全绿。

## 2026-10-27 W1-3b 交付：Windows 的 read/argv/exit 落地（语料 206/206）

**结果**：`tests/yh-run` 里 **206 例**在 Windows 上全过（上一轮 205），新增解锁
`16/17-read-*`（stdin 二进制读）、`51-noreturn-exit`、`pass/07-noreturn-branches`、
`21-main-argv`。Linux/Darwin 主门未回归（358/362、selfhost 330 s）。

- **read**：`GetStdHandle(-10)` + `ReadFile`；只接受 fd 0（1/2 读到的是输出句柄 → -1），
  契约与 Linux 版一致（返回字节数、0=EOF、-1=失败）。管道注入的二进制（含 NUL）按字节原样返回。
- **argv（mainCRTStartup）**：Win64 入口不传参数，故链接入口从 `/entry:main` 改为
  `/entry:mainCRTStartup`，由运行时发射的入口调 `GetCommandLineA` → 极简命令行解析
  （双引号成组、空格分隔、连续空格忽略）→ `main(argc, argv)` → `ExitProcess(返回值)`。
  `main` 无参时多余实参在 x64 ABI 下被忽略，所以同一入口对两种签名都成立。
- **exit/_Exit**：零 CRT 没有 libc，改为链接期 `/alternatename:exit=ExitProcess` 与
  `/alternatename:_Exit=ExitProcess`；运行时**不再定义**它们（用户 `@[extern]` 的声明与
  运行时定义同名会被 LLVM 判成“invalid redefinition”）。
- **踩到的三个坑（都已写进代码注释）**：
  1. LLVM 不允许同名 `declare` + `define` → Windows 运行时提供的 `write`/`read` 必须在
     声明阶段跳过（`llvm_runtime_supplies_symbol`）；`exit/_Exit` 则反过来，只声明不定义；
  2. 运行时函数里的 `alloca` 也必须放**入口块**（放在 `read:` 块里照样引 `__chkstk`）；
  3. `llvm_emit.yh` 单文件链接的 `coff_argv` 原来是 12 项，加两条 `/alternatename` 后越界，
     表现为 `lld-link: could not open '<乱码>'`——容量留到 16。
- **导入面**：`kernel32.def` 增 `ReadFile`（导入库 2986 字节），manifest 的 `def_sha256`
  同步更新；`just test-windows-sdk` 仍全绿。
- **实测**：编译侧 run 206/216（0 失败，10 跳过）、fail 137/137、pass 9/9；
  Windows 侧 `run-exe.py` → **206/206 通过**；`just test-windows-target` 6/6；
  Linux 回归与 `selfhost-native`（330 s）全绿；`max_build_lines` 11071 → 11077（+6，已注明）。
- **仍未做**：W1-3c（大栈帧页探测）、W1-3d（`open/close/mkdir/unlink/rename` 与 fd 表，
  与 libs/os 的 Windows 变体 W2-7 一起做）、libc extern（abs/strtoul）的 CRT 决策。

## 2026-10-27 W1-7 交付：整份运行语料在 Windows 上跑通（202/202），并修掉 COFF 绝对寻址崩溃

**结果**：`tests/yh-run` 的 `run/` 语料按 `--target x86_64-pc-windows-msvc` 交叉编译，
**202 例清单全部在真 Windows 上跑对**（stdout + 退出码）；Linux/Darwin 主门未回归。

- **关键 bug（brige.c 重定位模型）**：`compiler/llvm/bridge.c:165` 原来除 Darwin/ARM64
  外都用 `LLVMRelocStatic`，COFF 下它产出 **ADDR32 绝对地址重定位**（`movl G, %edx`），
  PE 镜像基址是 `0x140000000`，链接时被截断 → 任何**全局数据访问**都 `ACCESS_VIOLATION`
  （实测 `let G int = 7` 必崩）。修法：`needs_pic = darwin_arm64 || windows-msvc`；
  重建闭包（`just llvm-host` 30 s）+ 冷编 37 s 后 `g=7` 正确。这类 bug 只有“真跑”能抓到。
- **harness 两阶段（跨机）**：`tests/yh-run/check.py` 新增 `--run-platform` 与
  `--emit-manifest`（run/ 用例只编译、写出 `{exe, expected_stdout, expected_exit, stdin_hex, argv}`
  清单，路径存仓库相对值）；`tests/windows/run-exe.py` 在 Windows 侧执行并按
  `diff_output` 同一口径比对（支持 stdin/argv）。just 目标：`test-windows-corpus`（编译侧）
  与 `run-windows-corpus`（Windows 侧）。
- **实测**：编译侧 202 例清单（run 202/216、fail 137/137、pass 8/9）；Windows 侧
  `run-exe.py` → **202/202 通过**；`just test-windows-target` 6/6；
  Linux 回归：语法 49/49、运行 358/362、模块/fmt/arch-check、`selfhost-native` 316 s 全绿。
- **用例分层（不隐藏缺口）**：
  - `58-comptime-target.yh` **补 windows 分支**（目标标记用例扩到 Windows，而不是跳过）；
  - `21-main-argv` 标 `// platform: linux darwin`：Win64 入口不传 argc/argv，需
    `GetCommandLineA` 解析 → **W1-3b**；
  - `29-stress-capacity` 标同平台：单函数栈帧 > 4KB 在 Windows 需 `__chkstk` 页探测，
    当前用 `"no-stack-arg-probe"` 关探测 → **W1-3c**；
  - `16/17/18-read-*`、`51-noreturn-exit`、`pass/07-noreturn-branches`（libc `_Exit` 与
    POSIX fd）、`49/50-extern-*`（libc abs/strtoul）、`llvm-runtime-complete`
    （Linux syscall 覆盖）→ 均标 `// platform: linux darwin`，缺口指向 W1-3b / CRT 决策。
- **后续（已入 todo）**：W1-3b（Win32 文件 API + argv）、W1-3c（栈探测/大帧）、
  W1-2b（Win64 按值聚合强转）、CRT extern 互操作决策、W1-8 设计文档、
  CI 接线（现在只需在 windows job 里跑两个 just 目标）。

## 2026-10-27 W1-1/2/3/5/6/7 交付：Windows/x64 交叉目标打通（.exe 在本机原生存活）

**结果**：WSL 里的 yh 用 `--target x86_64-pc-windows-msvc` 交叉出 **PE**，在 Windows 侧原生
运行、stdout 与退出码全对：零 CRT、只依赖 KERNEL32、`/Brepro` 可复现。

- **W1-1 目标身份**：`gen/target_info.yh` 加 `x86_64-pc-windows-msvc`（`abi=win64-msvc`，
  `data_layout=e-m:w-…-S128`，本机 clang 21.1.8 核对）+ `target_select_os_arch`。
  **坑**：目标身份在 `ir/ssa_module_00_model.yh` 还有**第二份静态表**（key 1–4）——
  不补它会在 lowering 处**静默**返回 -1（无诊断，退出码 255）；已补 key=5 并写明。
- **W1-2 Win64 ABI 门**：`llvm_target_same` 白名单、`llvm_abi_supported` 的 win64 分支
  （标量/指针/函数指针放行；按值聚合给目标级诊断“待 W1-2b”）、`printf` 裸变参放行。
  **clang oracle 实测（2026-10-27）**：i8/i16 参数/返回值**无** signext/zeroext（与 SysV
  相反）→ `llvm_abi_attr_kind` 自然返 0；≤8 字节按值聚合被强制成 `i64`（需强转，故
  W1-2b 前拒绝）。
- **W1-3 Windows 运行时**：新文件 `backend/llvm_windows_runtime.yh`（HeapAlloc/HeapFree、
  GetStdHandle+WriteFile 的 printf、write/exit 薄层）；入口用 `/entry:main`（实测返回即
  退出码，不需 mainCRTStartup）。`llvm_runtime.yh` 拆出平台无关的 printf emit 复用。
  **两个 MSVC ABI 坑**：① 浮点要自己定义 `@_fltused`（否则 `undefined symbol: _fltused`）；
  ② **非入口块的 alloca** 被 LLVM 当动态分配 → 调 `__chkstk`，且实测“聚合临时值直接当
  printf 实参”会崩 —— 正解已落地：`llvm_function` 把全部 alloca 提升到入口块
  （C 式局部变量语义不变），另留 `no-stack-arg-probe` 只为超大静态帧兜底。
- **W1-5 COFF/PE 链接**：新文件 `build/windows_link.yh`（SDK 查找、固定模板
  `/nologo /Brepro /nodefaultlib /subsystem:console /entry:main`、一次性子进程跑内嵌
  lld 的 WinLink 驱动），`mb_link` 与单文件 `-o` 都接入；`mb_object_machine_matches`
  加 COFF 对象与 PE 可执行文件分支。
- **W1-6（部分）**：`project.os = "windows"` 合法（`pl_os_from_name`）、
  `[link-windows-x64]`/`[link-windows-arm64]` 节名与 `pl_target_code_current` 接入；
  **同时修**：`tests/modules/projects/linkbad` 原本拿 `[link-windows-x64]` 当非法节名，
  现改正后才不会让负例静默失效（改成 `[link-windows-sparc]`）。
- **W1-7（部分）**：新门 `just test-windows-target`（`tests/selfhost/llvm-windows-target.py`：
  6 例 PE、导入面、可复现、负例）+ 运行侧 `tests/windows/run-exe.py`（读清单在真 Windows
  执行）；两端实测全绿。新门依赖 LLVM CLI 工具（WSL 内装了 `llvm-21`/`lld-21` 并软链
  `llvm-dlltool`/`llvm-readobj`/`llvm-nm`/`lld-link`）。
- **预算**：`max_build_lines` 10809 → 11071（新增 `windows_link.yh` +260，随 B2 的 link
  簇拆出下沉）、`max_g_call_sites` 165 → 167（SDK 查找 + COFF 分派）。两处均写明理由。
- **实测**：手测 9 例（退出码 42 透传、sum=4950、结构体实参 pair=42、浮点 z=337、
  `%d|%s|%c|%u` 格式）全部在 Windows 原生正确；门禁 6 例 + 运行侧 6 例全绿；
  回归：语法 49/49、运行语料 358/362、模块/编译器测试、fmt、arch-check 全绿；
  `just selfhost-native` 324 s 全绿（固定点未受 alloca 提升影响）。
- **未做（归后续）**：W1-2b（Win64 按值聚合强转）、W1-3b（Win32 文件 API：open/read）、
  W1-6 剩余（`li_check_format` 的 `.lib`/PE 库校验）、W1-7 剩余（跑 corpus 的
  `// platform: windows-x64` 与 `host_platform_tag` 推导）、W1-8 设计文档、
  `just test` 与 CI 接线（当前是独立 `test-windows-target`）。

## 2026-10-27 W0-2a 交付：`windows` 目标标记 + 后缀标签 + 滚种子

- **为什分两代**（方案 §4.1）：编译编译器源码的是**种子**；种子不认识 `windows` 标记时，
  源码里的 `$if (windows)` 直接编不过。所以先只加「识别能力」，滚种子，之后才允许使用。
- **改动**（3 个源文件 + 2 个用例）：
  - `compiler/gen/model.yh`：`TARGET_OS_WINDOWS = 3`（注释写明“仅身份常量，不代表已有支持”）；
  - `compiler/comptime/ct_target.yh`：`ct_target_symbol` 认 `windows`（7 字符）；
  - `compiler/build/project_index.yh`：`pj_source_target_match` 认 `windows` 后缀标签
    （不先登记的话 `*.windows.yh` 会被所有目标编入，方案 §4.2）；
  - `tests/yh/positive/74-comptime-target-marker.yh`（五个标记的语法形态）；
  - `tests/yh-run/run/207-target-marker-exclusive.yh`（OS/架构标记各恰好命中一个，
    平台无关：linux/darwin/windows × arm64/x64 都能跑）。
- **实测（WSL，linux-x64 原生）**：旧种子 0.0.10 能编含本改动的源码（源码里尚无
  `$if (windows)` 使用点）；新编译器下语法语料 82/82 + 反例 49/49；运行语料
  358/362（4 例平台 SKIP）；新用例 `run/207` PASS；`just selfhost-native` 324 s 全绿。
- **arch-check 预算**：`build` 模块 +2 行（`pj_source_target_match` 的新 OS 分支，属目标表
  必要项）→ 先把注释压回原长度、代码双行压单行，最终 +2；`tools/arch-check.py` 的
  `max_build_lines` 10807 → 10809 并写明理由（方案要求“上调需在 finish 说明”）。
- **滚种子**：`bin/yh-linux-x64` `5ef7612e…` → `0757ebcc…`（本代自产）；用新种子重新跑
  `just selfhost-native`：360 s，模块固定点一致、语料 358/362、项目用例 133/133、全部通过。
- **下一步**：源码现在已可写 `$if (windows)`（W1-1 开工）。

## 2026-10-27 W0-1 交付：WSL(Ubuntu 26.04) 编译与门禁闭环（5 项环境适配）

用户告知已装 WSL。实机核对后打通「编译 → 自举 → 全量门」：

- **发行版/种子**：`Ubuntu-26.04`（x86_64，16 核/15 GB/1 TB）。用**原生 `linux-x86_64`
  种子**（`bin/yh-linux-x64`，release 0.0.10 自带该资产），因此**不需要 qemu/交叉 gcc**
  （周知文档里“x86_64 宿主须用 arm64 种子 + qemu”已随 LLVM 化过时）。种子在 Windows 侧用
  Git Credential Manager 里的 token 跑 `fetch-release-seed.py` 拉取（仓库私有）。
- **网络**：WSL 的 DNS 是宿主 Clash 的 fake-IP（`github.com → 198.18.0.12`），
  `.wslconfig` 已是 mirrored 但 fake-IP 流量绕不进本地 TUN；改用 Clash 的 mixed 端口
  `127.0.0.1:7897`（mirrored 下可从 WSL 直达）。写入
  `/etc/apt/apt.conf.d/99-yh-proxy` 与 `/etc/profile.d/99-yh-proxy.sh`（可删/可改端口）。
- **5 项环境适配**（都是**种子/门禁的期望与 26.04 的差异**，不是仓库代码问题）：
  1. **libxml2 shim**：种子按 Ubuntu 24.04 构建，需要 `libxml2.so.2`；26.04 只有
     `libxml2.so.16` → `/usr/lib/x86_64-linux-gnu/libxml2.so.2` 软链。副作用仅为启动时
     `no version information available` 警告；真编译已验证正常（新 `yh` 用 26.04 包的
     `.so.16`，无警告）。**这是临时兼容，长期解法是换 24.04 发行版或重发布种子。**
  2. **gcc-13**：种子烘焙的链接模板写死 `/usr/lib/gcc/x86_64-linux-gnu/13/{crtbegin,crtend}.o`
     → 装 `gcc-13`/`g++-13`（26.04 仓库有 13.4.0），不造假目录。
  3. **clang**：`tests/selfhost/runtime-memory.py` 硬要求 `/usr/bin/clang`（导入审计）→ 装 `clang`（21.1.8）。
  4. **just 的 shebang 配方**：`/run/user/<uid>` 是 tmpfs `noexec`，just 把脚本写在那里会
     `EACCES`（straced 确认）。解法：`export XDG_RUNTIME_DIR=/tmp/xdg-$(id -u)`（或 remount exec）。
  5. **python3 不能是 Store 占位符**：Windows 侧 `python3` 是占位符（`rc=49`），已在只是
     justfile 里加 `PY` 变量；WSL 内 python3 3.14 正常。
- **实测数字**：`just llvm-host` **99 s**（下载 Ubuntu amd64 LLVM 21.1.8 包 + 编桥，
  `needed` 含 `libxml2.so.16`）；冷编 `just` **37 s**；非 ANTLR 层全绿（语法 49/49、
  运行 357→358/362、模块/编译器测试、fmt、code-stats、arch-check）；
  `just selfhost-native` **321 s** 全绿（cc2/cc3/cc4 固定点一致、自解析 119 文件、项目用例 133/133）。
- **ANTLR 层未跑（已知缺口）**：它要 Java + `antlr4` jar + 硬编码 macOS venv
  （`/Users/lavender/...`），正是 CI 在 2026-10-26 砍掉它的原因；本机其余层已覆盖。

## 2026-10-27 W1-4 交付：Windows 导入库 stub（lane B，本机全绿）

- **为什么先做它**：方案 §12 里它是 4 件「不需编译器就能动」的第一件，且是 PE 链接
  的地基（yhw 零 CRT 路线只依赖 kernel32，但 PE 链接必须有导入库解释外部符号）。
- **新增**：
  - `compiler/windows-sdk/def/kernel32.def`：9 条最小导出面（GetStdHandle/WriteFile/
    ExitProcess/GetProcessHeap/HeapAlloc/HeapFree/GetLastError/CloseHandle/
    GetCommandLineA），每条对应 W1-3 运行时的真实消费者；
  - `compiler/windows-sdk/manifest.json`：DLL/导入库名、`exports`、`def_sha256`（漂移守卫）；
  - `compiler/windows-sdk/README.md`：生成/校验/查找顺序/改动纪律；
  - `tools/windows-sdk.py`：`generate` / `check` / `paths`；生成器优先级
    `llvm-dlltool -m i386:x86-64` → `lld-link /lib /def:` → `lib.exe`，`identity.json`
    记录工具身份与每个 `.lib` 的 sha256；
  - `tests/selfhost/llvm-windows-sdk.py`：四件事全查（清单↔def、生成确定性、
    符号面 `X`+`__imp_X` 且无多余、链接探针只依赖 KERNEL32 + 负例 `Sleep` 必须失败）；
  - `justfile`：`windows-sdk` / `test-windows-sdk` 两个目标，并提交全局 `PY` 变量。
- **实测（本机：Windows 11 / LLVM 21.1.8）**：
  - 同一 `.def` 生成两次 sha256 相同（`e7c27795…f188`，2820 字节）；`llvm-dlltool` 与
    `lld-link /lib` 产物**逐字节相同**，所以换生成器不会让身份漂移；
  - 探针：`clang --target=x86_64-pc-windows-msvc` → `lld-link /nodefaultlib
    /subsystem:console /entry:main /Brepro` → PE 导入只有 `KERNEL32.dll`，**Windows
    上实跑**输出 `windows-sdk-probe`、退出码 5；
  - 负例：def 擅自加 `VirtualAlloc` → 门禁三处独立报错（哈希/导出面/符号面）并 `rc=1`；
    调用未导出 `Sleep` → 链接失败且不产出文件；`--tool` 指向不存在的生成器、
    PATH 里没有任何生成器 → 均给可操作的安装提示而不是 traceback。
- **仓内不落二进制**：根 `.gitignore` 忽略 `*.lib/*.obj/*.exe/*.dll`，所以 `.lib` 只能
  构建期生成（本次把方案 W1-4 里「仓内回退 `.lib`」一句改成「不落二进制」，不做
  永远提交不进去的回退）。
- **顺带发现**：本机 `python3` 是 Microsoft Store 占位符（执行即 `rc=49`、无输出），
  真解释器是 `python`（3.12.5）；因此 justfile 新增 `PY` 变量（默认 `python3`，
  Windows 用 `PY=python` 覆盖）。这是 W2-5（just 的 windows 分支）要正式解决的同类问题。
- **未做（已归后续切片）**：编译器侧消费（查找顺序 + `kernel32.lib` 注入）= W1-5；
  `just test-windows-cross` 接线 = W1-7；`tests/yh-run` 的 `// platform: windows-x64`
  运行用例要等 W1-3/W1-5 能出 `.exe` 才有意义，不提前加不会跑的用例。
- **自检**：新增/修改文件均已 `git status` 核对（`.def`/manifest/README/脚本均未被
  `.gitignore` 命中）；未改 `compiler/*.yh`，故不需跑 `just test` / `selfhost-native`。

## 2026-10-27 Windows/x86_64 后端规划交付（W0–W3、8+7 切片）

- **交付**：[Windows/x86_64 LLVM 后端接入实施方案](02-plan/yh-Windows-x86_64-LLVM后端接入实施方案-2026-10-27.md)；
  `docs/todo.md` 的 B1 从一行条目展开为 W0/W1/W2 全部切片（含每片落点文件与验收）。
- **结论**：Windows 不是「再写一个后端」——LLVM 已能给 `x86_64-pc-windows-msvc` 出
  COFF、内嵌 lld 已注册 COFF 驱动并有过门禁探针（`tests/selfhost/llvm-lld.py`）。缺的是
  目标身份、Win64 ABI 门、零 CRT 运行时与 `/entry:main`、kernel32 导入库、PE 校验，以及
  原生宿主的 OS 桥与**无 `fork` 的进程模型**。据此拆成 T 面（交叉目标，W1）与 H 面
  （原生宿主，W2），不以 WSL 冒充 Windows 支持。
- **本机实测（决定方案取值，不靠猜）**：
  - `x86_64-pc-windows-msvc` 的 `data_layout` 用本机 clang 21.1.8 核对；
  - `/nodefaultlib /entry:main` 的 PE 中 `main` 返回值即进程退出码（实测 7 / 3）——
    因此不需要 `mainCRTStartup`；
  - `llvm-dlltool` 从文本 `.def` 生成 1716 字节 `kernel32.lib`，`lld-link` 可直接解析
    `__declspec(dllimport)`，且 `--coff-imports` 只依赖 KERNEL32.dll；
  - `lld-link /Brepro` 两次链接字节相同（与 RB5 的可复现方向一致）。
- **已确认（2026-10-27）**：D1 = `x86_64-pc-windows-msvc`、D2 = 零 CRT（只依赖
  KERNEL32.dll，自造 `.def`→`.lib`）、D3 = W1 交叉目标 → W2 原生宿主。
- **并行开发分析（方案 §12）**：只 4 个文件是串行热点（`gen/target_info.yh`、
  `build/link_cache.yh`、`justfile`、`build/process.yh`），其余可开 7 条 lane；
  首日不需编译器就能动的 4 件：W1-4 导入库、W1-7a 门禁脚手架、W2-2 Windows 静态
  LLVM SDK、W1-8/W0-4 文档；W1 串行 8–10 人日 → 3–4 lane 约 4–5 日历日。
- **WSL 实况纠正**：用户告知本地有 WSL；实测 `wsl.exe` 可用、WSL2 已启用，但
  **无已注册发行版**（`wsl -l -v` 报无分发版、`HKCU\…\Lxss` 无发行版子键），
  故 W0-1 改为「`wsl --install -d Ubuntu` + 交叉 gcc/qemu/binfmt + 种子 + 闭包」；
  完成后 W1 可在本机闭环（`/mnt/c` 同一工作树编→跑）。
- **顺带发现**：根 `.gitignore` 忽略 `*.lib/*.obj/*.exe/*.dll`，所以 W1-4 不能靠
  「仓内回退 `.lib`」（会静默不提交），只能用 `.def` + 构建期生成。
- **顺序约束（方案 §4）**：`$if (windows)` 必须晚于「种子学会识别 windows 标记」
  的那一代（`ct_target.yh` 先用一个代次学会标记名，才能在新源码里使用）；同理
  `*.windows.yh` 后缀标签必须先扩 `pj_source_target_match`，否则会被所有目标编入；
  第一个 Windows 种子只能由 W1 交叉产物 `yh.exe` 反哺。
- **验证**：本次只动文档（`docs/02-plan` 新增一篇、`docs/todo.md` 展开 B1、本条），
  未修改任何源码，因此不跑门禁；方案中的命令均标注「拟新增」。

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

## 2026-10-25/26 YT4 收口：四道门复验

- YT4-P0～P7 全部完成，测试分布与外部保留清单见
  [YT4 收口与门禁验证](01-finished/yh-YT4-收口与门禁验证-2026-10-25.md)。
- 最终复验（仓库根，入口已迁移 justfile，make 仅转发）：
  `make libs-test` 122 passed + cli 5/5 + os 11/11+1/1 + libc 2/2；
  `make libs-test-o2` 122 passed；`just test` exit 0（compiler-tests 4/4 等）；
  `just selfhost-native` exit 0（cc3→cc4 固定点、cc4 自解析 119 文件、
  project cases 122/122）；`make test-num` 220/220；`git diff --check` 通过。
- 延后项：YT2d-2（函数级 IR/check 缓存未用于测试构建）、D11 预期失败能力、
  astcheck 增量门槛跳过；编译器十进制字面量 1 ULP 偏差已于 2026-10-26 修复
  （见上方条目）。

## 2026-10-25 YT4-P7：num 内建测试与 Python 往返差分

- `libs/num`（958 行、此前零测试）新增 `zz_tests.yh`：6 个 test / 45 条
  `$assert`，覆盖 `parse_f64` 合法值/边界/语法/上下溢/4096 有效位上限与
  `format_f64` 最短往返、-0.0、指数形式、非有限值/容量不足。
- 新增 `tests/num/reference.py`（固定种子 220 例：固定边界 + 随机 64 位模式
  的 Python `repr` + 随机十进制指数文本），比较解析状态/位模式与格式化往返；
  `make test-num` 独立目标，CI 的 darwin-arm64 与 linux-arm64 各加一步，
  不进 `libs-test` 快跑。
- 测试发现（2026-10-26 已修复）：编译器十进制字面量 `1.5e300` 曾比正确值多
  1 ULP（`num.parse_f64`/Python 一致）；修复与回归见上方 2026-10-26 条目。
- 验证：`yh test num` 6/6；`make test-num` 220/220；`make libs-test`
  **122 passed** + cli/os/libc；`make libs-test-o2` 122；`just test`
  **73.0s**；`just selfhost-native` **153.5s / 122/122**。记录见
  [YT4-P7](01-finished/yh-YT4-P7-num迁移-2026-10-25.md)。

## 2026-10-25 YT4-P6：irverify 迁入 `compiler/ir/zz_tests_verify.yh`

- `tests/modules/projects/irverify`（747 行、6 个 `check_*`）→
  `compiler/ir/zz_tests_verify.yh`（6 test / 51 断言，只调 pub API）；
  失败点 `return N` 改为 `$assert(false, "旧断言 N"); return;`，控制流不变。
- 删除夹具与 `build-check.py` 的 `r2a-ssa-phi-verifier`，`copy_proj` 特判
  只剩 `irfront`/`llvmmodule`；`compiler-tests` 增加 `ir` 模块。
- 保留（有据）：`irfront`（发射覆盖统计/符号契约）、`llvmlower` + lower
  探针（lower 不允许依赖 parse/check）、`llvmchecked`；`astcheck` 因
  `test-compiler-tests` 增量 19.7s > 10s 门槛跳过。记录见
  [YT4-P6](01-finished/yh-YT4-P6-编译器fixture迁移-2026-10-25.md)。
- 验证：`compiler-tests` 4/4；`just test` 75.2s；`just selfhost-native`
  192.1s / project cases 122/122。

## 2026-10-25 YT4-P5：os/sys/time 测试与 P0 收尾

- `sysresult` 的纯模型断言 → `libs/sys/99_tests.yh`（2 test：Timespec 布局、
  is_error/error_code 边界）；删 fixture 与 `os0-sys-result-model`。
- 新增 `libs/os/99_tests.yh`（4 test：结果构造函数/选项默认值/目录条目视图/
  errno 分类映射）与 `libs/time/99_tests.yh`（单调时钟非负且不倒退）。
- 保留 `libs/os/test/run.py`（FS/目录/进程 E2E、Linux 目标类型检查）与
  Linux 11 个 fixture；`osmodel`/`osio` smoke 不变。
- P0 收尾：`tests/toml/run.py`、`tests/json/run.py` 与对应 `just test` 行已删；
  `tests/fmt/interp.py` 按 D11 保留为外部负例门。
- 全门复验（LA3 已由并发会话收口）：`just test` **61.6s**；
  `just selfhost-native` **148.8s / project cases 123/123**；
  `make libs-test` **116 passed** + cli/os/libc；`make libs-test-o2` 116。
  记录见 [YT4-P5](01-finished/yh-YT4-P5-os-sys-time迁移-2026-10-25.md)。

## 2026-10-25 YT4-P4：cli 五个 selftest 主体迁入 `libs/cli/zz_tests_*.yh`

- 5 个夹具（clibasics/cliactions/clicommands/cliextensions/clihelp，约 3625 行）
  → 5 个测试文件、**43 个 `test`**：basics 5、actions 12、commands 9、
  extensions 9、help 8。记录见
  [YT4-P4](01-finished/yh-YT4-P4-cli迁移-2026-10-25.md)。
- 删除 cliactions/clicommands/cliextensions/clihelp 四个夹具；clibasics 只留
  `build_pack_parser`/`run_pack`/`main`；`libs/cli/test/run.py` 10 → 5 例
  （climodel、clibasics×3、cliwarnings），`diff.py` 保留。
- 参数文件用例改用 `/tmp/yh-cli-*.txt` 自建自清；测试文件名必须 `zz_` 前缀
  （cli 类型声明在 `cli.yh`）；`make libs-test` 的缺测试提示改为匹配
  `*tests*.yh`。
- 验证：`yh test cli` 43/43；cli runner 5/5；`make libs-test` **109 passed**
  + cli/os/libc 全绿；`make libs-test-o2` 109 passed；`just test` **60.5s**。
  `selfhost-native` 仍停在另一会话的 LA3「损坏记录」期望，待其收口后复验。

## 2026-10-25 YT4-P2/P3：TOML 与 string 测试迁入库内

- **TOML**：`toml{model,strings,scalars,tables,errors,files}` 的 160 个 `ok()`
  （运行时断言点 154）→ `libs/toml/99_tests.yh` 的 11 个 test / **154 条
  `$assert`**（1:1）；删除 6 个纯断言夹具与 `tests/toml/run.py`，
  `make test-toml` 改为 `yh test toml`；conformance（681/681）、injection
  （124 点）、install 保留。记录见
  [YT4-P2](01-finished/yh-YT4-P2-toml迁移-2026-10-25.md)。
- **string**：`string{view,owned,transform,utf8}` 的 206 个 `if` 断言点 →
  `libs/string/99_tests.yh`（15 test / 216 断言）；删除 4 个 fixture 与
  `st2`–`st5`，保留 `stringmodel`/`stringinterop` smoke 与
  resources/reference/install/complexity；`tests/string/run.py` 默认组改为
  model/interop/resources。记录见
  [YT4-P3](01-finished/yh-YT4-P3-string迁移-2026-10-25.md)。
- **门禁**：`just test` **94.9s → 56.8s**（json/toml/string 三批迁移合计
  −38.1s）；`make libs-test` 66 passed + cli/os/libc 全绿；`yh -O2 test`
  66 passed；`make test-string` 26.6s → **16.7s**；`make test-toml`
  4.8s。arch-check 的 `max_build_lines` 因并发会话的 PC3 落地 +6
  （10730 → 10736）同步并注明理由。
- **未复验**：`just selfhost-native` 停在
  `tests/selfhost/llvm-function-cache.py` 的「损坏记录」期望
  （`(4,1,4)` vs 实际 `(5,0,5)`）；该脚本与 `compiler/ir/ssa_module_40*`、
  `module_snapshot_lower_cache*` 正被另一会话改动（PC 工作 WIP），
  与本迁移无关，待其收口后重跑。

## 2026-10-25 YT4-P1：JSON 测试迁入 `libs/json/99_tests.yh`

- **迁移**：`tests/modules/projects/json{model,strings,numbers,containers,errors,files}`
  的 114 个 `ok()` 断言点 → `libs/json/99_tests.yh` 的 12 个 `test` / 127 条
  `$assert`；断言全部走 pub API，文件用例用 `/tmp` 固定路径（照 io 先例）
  并 `unlink` 清理。断言对照表见
  [YT4-P1 迁移记录](01-finished/yh-YT4-P1-json迁移-2026-10-25.md)。
- **删除**：5 个纯断言夹具（jsonstrings/numbers/containers/errors/files）、
  `tests/json/run.py`、`tests/json/` 与 `make test-json` 目标；`just test`
  不再跑 json runner。
- **保留**：`jsonmodel` 作为公开面/链接 smoke，`build-check.py` 新增
  `j1-json-model`（`stdlib-run`，期望 `json model ok`）。
- **验证**：`yh test json` 12/12；`make libs-test` 45 passed
  （33 + 12）+ cli/os/libc 全绿；`just test` **94.9s → 76.9s**；
  `just selfhost-native` 188.7s，project cases **128/128**；`git diff --check`
  通过。

## 2026-10-25 YT4-0：libs 测试统一入口与 `yh test` 并发串行化

- **背景**：YT4 迁移分析确认 `libs/cli`、`libs/os`、`libs/libc` 的 runner
  完全没接门禁，且同一项目的两个 `yh test` 会互相覆盖入口/二进制/日志/缓存
  （实测 4 并发 3/4 轮失败）。决策见
  [YT4 规划 §11](../02-plan/yh-test语法迁移既有测试分析与规划-2026-10-25.md)。
- **并发串行化（YT2d-3）**：`compiler/testkit/test_cmd.yh` 新增
  `tc_test_lock_path`/`tc_lock_pid`/`tc_lock_acquire`：在
  `<项目>/tmp/yh-test/.lock` 用 `O_CREAT|O_EXCL` 建锁并写 pid，同项目运行
  串行化；持有者退出后按 `kill(pid, 0)` 清理陈旧锁，等待上限约 30 秒；
  `--list` 不建锁，`--no-run`/正常结束释放锁。arch-check 的
  `max_testkit_lines` 1515 → 1592（说明：同项目测试锁）。
- **门禁入口**：`just test` 与 `just selfhost-native` 的 4/3 次按模块
  `yh test` 改为一次无选择器 `yh test --timeout 60`（33 例 3.0s）；新增
  `make libs-test`（缺测试提示 + `yh test` + `libs/cli/test/run.py` +
  `cli/test/diff.py` + `libs/os/test/run.py` + `libs/libc/test/run.py`）与
  `make libs-test-o2`（`tmp/libs-o2` 项目副本，独立 `tmp/yh-test` 缓存/锁）；
  `make test-lib-tests` 保留为别名。缺 `99_tests*.yh` 的库只提示不阻断。
- **CI**：`.gitea/workflows/ci.yml` 的 darwin-arm64、linux-arm64、
  linux-x86_64 三个 job 各加 `make libs-test`（同一目标、平台差异交给编译期
  文件选择）；`libs-test-o2` 只在 linux-arm64 追加。
- **文档**：新增
  [yh-test 测试布局与运行约定](03-design/yh-test测试布局与运行约定-2026-10-25.md)
  （文件命名/排序、平台文件、粒度、`/tmp` 资源、并发锁、门禁职责）；
  YT4 规划 §7.2/§8 同步为已交付，`docs/todo.md` 关闭 YT2d-3 与 YT4-0。
- **验证**：`just test` 94.9s 绿；`just selfhost-native` 205s（两代固定点、
  自解析、项目用例 **127/127**）绿；`make libs-test` 36s（cli/diff/os/libc
  全绿）、`make libs-test-o2` 11s（33 例）；`tests/modules/test-check.py`
  34 项通过；`make test-compiler-tests` 3/3；同项目 4 并发 `yh test string`
  全部 5 passed；陈旧锁（pid 不存在）自动清理。


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

## 2026-10-25 PC4：capture 归因与校验去重

- **归因**（1460 次 capture 内嵌探针，CPU 秒）：分配+清零 **0.02**、闭包标记 **0.59**、
  迷你模块构建 **9.97**、`ir_module_verify`+序列化 **24.34**（合计 34.9）。也就是
  「每函数 7 张表的 malloc/free」几乎不花钱，**约七成成本在验证与序列化**。
- **端到端**：13 个模块全量重编时，capture 开 = 26.5 s、关（PC3 冷编路径）= 13.5–15.6 s，
  即 capture 仍占 **11–13 s**。
- **已落地**：去掉两处重复校验——`ir_function_cache_capture` 里逐函数的
  `ir_verify(&function.body)`，与迷你模块的 `ir_module_verify(&mini)`。两者都由
  「capture 之后、提交之前」的模块级 `ir_module_verify(&candidate)` 覆盖，且记录只在
  整模块构建成功后才落盘。实测收益 1–2 s（宿主机 load 40–60，噪声同量级）。
- **已否决**：把 7 张临时表改成按模块复用的 scratch 结构体。第一版把 `reserve` 放在
  取指针之后（扩容 realloc 后局部指针失效）；改成先 `reserve` 后取指针仍会让
  `yh test string` 的 libs 构建在 lowering 阶段报
  `memory/memory.yh:5:19 alloc: 首片不支持此语句或表达式`，机制未定位
  （怀疑 `ir_fc_mark_symbol`/`ir_fc_visit_type` 对越界下标写 scratch），因此整体回退。
- **门禁**：`just test` 100 s、`just selfhost-native` 228 s（项目用例 **128/128**、
  LA3 缓存矩阵 O0/O2）、`just test-llvm-darwin` 42 s 全绿。
- **环境**：门禁期间磁盘被 tmp 副本写满（`No space left on device`）导致一次
  `selfhost-native` 假失败；已清理约 6.5 GB 临时副本（`tmp/pc*`、`tmp/modcheck`、
  `tmp/yh-test`、`tmp/faststage`）。

## 2026-10-25 PC3：全冷构建不写函数级缓存

- **动机**：`just` 每轮 `rm -rf compiler/.build`，冷编里 `capture`（每函数序列化
  迷你 IRModule）是纯成本；PC1 后单模块记录已从 28.7 MB 降到 8.4 MB，但冷编仍要
  为 1459 个函数全部写一遍。
- **判据**：`<build>/manifest/link.manifest` 是「上一轮构建完成」的哨兵。它不存在
  说明 `.build` 刚被清空（或上轮失败）→ `gs.c_firc_write_off = 1`，本轮只查不写。
  注意不能用 `manifest/` 目录存在性：`mb_mkdir` 会预建六个子目录。
- **读写分离**：`lower_module_cached` 的 `cache_enabled` 只看 `cache_in`（能不能查），
  capture/提交由 `cache_out` 是否为空决定——所以关掉写入后 `--stats` 的
  `ir_functions/ir_cache_misses` 语义不变（冷编仍是 1459/1459）。
- **结果**（候选 `./yh` 冷编 `compiler/`）：**23.9 s → 14.8 s（−38%）**，
  `.fir` 写入 1459 → **0**；冷编后首次改一个函数 6.4 s（缓存为空，全 miss 并落盘），
  再次改动 4.7 s（200/201 命中）。热编无改动不变（~2.4 s）。
- **注意**：`just`（种子 `bin/yh-darwin-arm64` 编 `compiler/`）仍是 24.6 s，因为
  种子还是旧编译器；**滚种子后 `just` 才会拿到这 −38%**。本次不滚种子：工作区
  里有并行会话未完成的 `testkit` 改动，滚进去会污染种子。
- **架构预算**：`build` +10 行（PC3 判据与读写分离的判据注释），
  `tools/arch-check.py` 的 `max_build_lines` 10720 → 10730（原因即本条）。
- **门禁**：`just test` 88 s、`just test-llvm-darwin` 36 s、`just selfhost-native`
  206 s（LA3 缓存矩阵 O0/O2、项目用例 **127/127**、新增的 `pc1-function-cache-hits`
  五条断言含 `cold-no-write`）全绿。

## 2026-10-25 PC1/PC2：函数级缓存键稳定与 check 切片安全阀

- **PC1 根因**：`checked_cache_layout` 把整张 interned 类型表（含函数体内局部数组/
  切片产生的 lazy 类型）按下标混进函数键；表顺序取决于「本轮检查了哪些函数」，
  而 check 切片命中会跳过检查 → 键依赖命中、命中依赖键。实测同一份源码连续三次
  构建得到三种类型顺序（`type_n`=166/167/168），IR 命中率恒为 0。另有装载上限
  过小（单记录 1 MiB/单模块 16 MiB）与符号按类型编号比较（`gen` 201 个函数里
  61 个被判不兼容）两处独立缺陷。
- **PC1 修复**：`lower/module_snapshot_lower_cache.yh` 只混声明面事实（struct/union/
  enum 的种类/大小/对齐 + 每个函数的签名事实），不再混类型编号与 `elem`/`sub`；
  `ir/ssa_module_50_function_rebind.yh` 的签名/参数类型改为结构等价比较；
  `build/function_ir_cache.yh` 上限改为 4 MiB/256 MiB。
- **PC2**：check 切片格式 v2 不带 `store.strings`，命中后 lowering 报
  「字符串缺少受检字节」/「表达式 AST 校验失败」。升版 v3 前改为只写不读
  （`module_worker` 传空集合，删掉失效的 `firc_check_load`），`llvm-function-cache.py`
  的 check 期望改为 0 命中并写明原因。
- **结果**：`gen` 等价重编 0/201 → **201/201**、`build` 0/271 → **271/271**；
  单函数改动 6.7–7.7 s → **4.2 s（200/201）**；`firc/yh-gen` 1206 记录/49 MB →
  **201/8.4 MB**；「清 `.build` 保留 `firc`」从内部错误变为 13.6 s 正常完成；
  冷编 23.9 s（`capture` 全量写入属 PC3）。
- **门禁**：`just test` 78 s、`just test-llvm-darwin` 34 s、`just selfhost-native`
  224 s（两代固定点、自解析、LA3 缓存矩阵 O0/O2、项目用例 **127/127**）全绿；
  新增模块用例 `pc1-function-cache-hits`（冷编全 miss / 等价重编全命中 /
  单函数改动只失效该函数）。残留：类型 interning 去重（PC1b）、check 切片 v3。

## 2026-10-25 裸跑 `yh build` 链接失败修复（libc++ 进闭包）

- **现象**：`cd compiler && ../bin/yh-darwin-arm64 build` 编完 13 个模块后链接失败，
  `ld64.lld: undefined symbol: __ZdlPv … referenced 32483 more times`（C++ 符号）。
- **根因**：C++ 运行库参数 `-lc++` 只存在于 `selfhost-runtime.txt`，由
  `tools/seed-build.py` 以 `YH_LINK_RUNTIME_FLAGS` 注入，所以只有 `just` 路径能链接；
  而且即使补上 `-lc++`，随编译器分发的 SDK stub 也不含 libc++（`usr/lib` 只有
  `libSystem.tbd`）。
- **修复**：`tools/llvm-darwin-host.py prepare` 把宿主 SDK 的
  `usr/lib/libc++.tbd` 复制进构建机闭包并记 `host.json.cxx_tbd`/`_sha256`，
  `tools/link-closure.py` 生成 `[link-darwin-arm64].cxx`；闭包已带 stub 时
  prepare 从运行库文件里去掉 `-lc++`，避免重复。`tools/link-closure.py check`
  接进 `just test-llvm-darwin`；`tests/selfhost/llvm-darwin-host.py` 新增
  stub 复制、运行库过滤、无 stub 回退三条契约（用显式目录注入，不动真实闭包）。
- **验证**：`cd compiler && ../bin/yh-darwin-arm64 build`（无 SDKROOT、无
  `YH_LINK_RUNTIME_FLAGS`，清 `.build`）成功，22.0 s；`just` 冷编 25.1 s；
  `just test`（110 s）与 `just test-llvm-darwin`（36 s）全绿。

## 2026-10-25 编译器性能首轮归因

- **测量**：Apple M1/8 GiB，种子与当日候选在 `compiler/` 上冷编/热编/单函数改动三种
  场景。冷编 26 s（`schedule` 22.3 s、link 2.1 s、object 1.0 s），热编 2.4 s
  （link 1.3–1.5 s + object 0.6–0.8 s），单函数改动 6.7–7.7 s。
- **归因**：用 `tmp/perf/analyze/` 下的一次性探针（worker 阶段标记 + lowering 内部
  计时，不入库）测得冷编 worker CPU 72.7 s：lowering 62.1 s，其中函数级 IR 缓存的
  `capture` 40.6 s（56%）、真正的 lowering 16.3 s、模块校验 3.6 s；LLVM 文本 5.9 s、
  内嵌桥代码生成 2.8 s、受检 AST 校验 1.7 s，前端其余 <0.3 s。
- **关键发现**：① 强制关闭 `cache_enabled` 后冷编 29.5 s → 16.1 s（−46%）；
  ② 等价输入（只改注释/改一个函数体）重编实测 `ir_cache_hits=0/201`、
  `check_cache_hits≤18/201`，与 RS2 设计期望不符，`firc` 目录逐轮膨胀（gen 201 个
  函数对应 1206 个 `.fir`）；③ 把等价 `firc/` 放回冷树构建会报
  `内部错误：表达式 AST 校验失败`（两次复现）。
- **产出**：[归因分析](02-plan/yh-编译器性能分析-2026-10-25.md)（含复现命令、阶段表、
  优化候选与顺序）；todo 新增 PC1–PC6。未修改编译器源码，未滚种子。
- **注意**：测量期间宿主上虚拟机持续占用约 3.4 核（load 峰值 18.5），同一二进制
  冷编落点从 26 s 漂到 52 s；阶段占比取自同一次运行内部，正式对照仍需按 PF1
  空载 20 轮。

## 2026-10-25 CI 修复：TOML 语料下载重试 + x64 接口头断言

- **现象**：Gitea `ci.yml` run 142（同样见 run 210）三端红：darwin-arm64 与
  linux-arm64 都停在 `tests/toml/conformance.py --prepare`，linux-x86_64 报
  `FAIL u1-attribute-free-iface-keeps-v1`。
- **根因**：① 语料下载只尝试一次，GitHub 归档连接偶发
  `UNEXPECTED_EOF_WHILE_READING` / `RemoteDisconnected` 就让门禁变红；
  ② 接口头断言写死 `arch=arm64`，而 A0c2 起头行架构随目标写入，x86_64
  目标的合法头行是 `arch=x64`。
- **修复**：`tests/toml/conformance.py` 新增 `download_archive`（`.part` 原子
  改名 + 4 次退避重试，失败转可读诊断）；`tests/modules/build-check.py` 的
  u1 断言改为 `// yh-iface v1 arch=(arm64|x64) suffix=` 正则，不再绑定单一架构。
- **验证**：`conformance.py --prepare` 真实下载通过；本地模拟断连时重试 2 次
  后报错且无 `.part` 残留；`build-check.py` 全量门中 u1 用例通过（同轮其余
  失败是本地未导出 SDKROOT 导致的 `-lm` 链接环境问题）；头行正则对
  arm64/x64/非法版本与架构自测通过。工作区另有并行未提交的 B3 重构，未跑
  完整 `just test` / `just selfhost-native` 以免混入他人改动。

## 2026-10-25 `lower` 独立（B3-1/B3-2）

- **B3-1 解环**：3 个 FNV 混入原语从 `module_snapshot_lower_cache.yh` 下沉到
  `ast/cache_mix.yh`（唯一定义，check 键与 IR 键共用）；`checked_slice_self_test`
  从 `check_slice` 移到 `ast/module_snapshot_lower_selftest.yh`，为随 lowering
  一起搬走做准备。零语义改动。
- **B3-2 搬迁**：16 个文件 `git mv` 到 `compiler/lower/`（15 个 lowering + 探针），
  改 `module lower` 与 `ast.` 前缀（333 处 / 56 个符号）；`ast` 补 3 个 `pub` 与
  新入口 `checked_decl_restore`（探针不再直接读写 ast 模块级数组）。
- **数字**：`ast` 9,041 → **3,278**（−63.7%），`lower` **5,815**，模块 12 → 13，
  依赖边 33 → 37，总行数 52,342 → 52,398，`gen.G()` 仍 165、全局 `let` 仍 183。
- **验证**：`just` / `just test` / `just selfhost-native`（project 126/126、固定点
  逐字节一致）全绿；`make arch-check` 通过。
- **顺带**：`tests/modules/projects/llvmlower/main/main.yh` 改 `import core.lower;`，
  `tests/modules/build-check.py` 与 `tests/selfhost/llvm-lower.py` 的模块拷贝列表
  补 `lower`。

## 2026-10-24 yh 字符串插值 I4 收口

- **实现**：`string.View` 插值、O2 正例、`--syntax-check` 插值语法模式；
  `docs/yh.g4` 记录 STRING 内部细化与 `\$` 转义。
- **验证**：`make test` 356/357；`make selfhost-native` project 122/122；
  `tests/fmt/interp.py` 10/10；`make test-lib-tests` string 5 + fmt 17；
  fmtinterp `nm -u`/`otool -L` 无 printf/LLVM/lld。
- **残余**：旧发射器未统计区分；I5 可选扩展未做；未滚种子。
- **合入**：10 个交付提交（`9100602`…`29dacd8`）经 `--no-ff` 合入 `llvm`
  （`513f6d7`，未推送）；合并把新增的 15 处 `gen.G()` 读点改为
  `gen.task()`，`arch-check` 的 G() 读点维持预算 165；合入后
  `make test` 与 `make selfhost-native`（project 126/126）全绿。
- **记录**：[I4 记录](01-finished/yh-fmt-插值I4-2026-10-24.md)。

## 2026-10-24 yh 字符串插值 I0–I3

- **实现**：词法后扩展 + raw-string body 数据 + parser 合成 fmt 调用树；
  `${expr:spec}` 端到端可用，结果 `string.String`；编译期校验 spec 与类型。
- **测试**：`fmtinterp` modules fixture、`tests/fmt/interp.py` 8 个负例、
  `make test-fmt-interp`、fmt 内建 17 项。
- **边界**：需 import fmt/string；不支持 View/String、结构体、嵌套/花括号/
  裸双引号/顶层三元；旧发射器与 O2 专项待 I4。
- **记录**：[I0–I3 实施记录](01-finished/yh-fmt-插值I0-I3-2026-10-24.md)。

## 2026-10-24 yh fmt 插值叶 API

- **实现**：`60_interp.yh` 增加编译器降级契约 `text`/`value`/`value_spec`/
  `concat`；String 按值传递，`concat` 消费输入并返回合并结果，失败零句柄。
- **测试**：fmt 内建测试增至 17 项；`make test-lib-tests` 全绿。
- **边界**：`text`/`value_spec` 接收 NUL 结尾 `*char`，文本块内嵌 NUL 暂不支持；
  编译器插值尚未接通。

## 2026-10-24 yh fmt R3 API：print/sprint/render

- **实现**：`50_output.yh` 的 print/sprint/fprint/render/of_string；打印族
  渲染进临时 String 后一次写出，值之间不插入隐式分隔符。
- **语言限制**：`pub` 变参函数非法，公开打印族接收 `[]Value`；设计与 README
  已同步。
- **测试**：fmt 内建测试增至 16 项；`make test-lib-tests` 全绿。
- **R3.2**：`make test-fmt-install` 安装后仓库外导入并通过 fmtbasic
  全 API surface；`nm -u` 未做。语言插值未开始。
- **记录**：[R3 实施记录](01-finished/yh-fmt-R3-2026-10-24.md)。

## 2026-10-24 yh fmt R2：浮点渲染

- **实现**：`40_float.yh` 接通 f64：NaN/±Inf/负零、默认 g（6 位有效数字）、
  `f/F`、`e/E`、`g/G`，`.N` 去尾零、`.Nf` 保留，指数至少两位；宽度/符号/
  零补齐复用浮点文本路径。
- **测试**：fmt 内建测试增至 13 项；`make test-lib-tests` 全绿。
- **边界**：定点 `scaled > 1e18` 或 precision > 17 返回
  `status_unsupported`；未做 V 实测差分。
- **记录**：[R2 实施记录](01-finished/yh-fmt-R2-2026-10-24.md)。
- **验证**：`cd libs && ../yh test fmt` 13/13；未跑全量门，未滚种子。

## 2026-10-24 yh fmt R1：V 格式说明符整数/文本子集

- **实现**：`20_spec.yh` 解析 flags/width/precision/type；`30_render.yh`
  接通整数 `d/x/X/o/b`、`+/-/0` 对齐、字符串 rune 宽度与 bool 宽度；
  非法 spec 返回 `status_invalid_spec`。
- **测试**：fmt 内建测试增至 10 项；`make test-lib-tests` 全绿。
- **边界**：f64 渲染仍 `status_unsupported`（R2）；print/sprint 与语言插值未开始。
- **记录**：[R1 实施记录](01-finished/yh-fmt-R1-2026-10-24.md)。
- **验证**：`cd libs && ../yh test fmt` 10/10；未跑全量门，未滚种子。

## 2026-10-24 yh fmt R0：Value 与默认渲染

- **实现**：`libs/fmt/` 落地 R0：`Kind`/`Value`/`Status`/`TextResult`、
  `of_*` 构造器、`append_text`、空 spec 的 `append_value` 默认渲染
  （整数、无符号、bool、字符串、`<nil>`、NULL C 字符串）。
- **测试**：`libs/fmt/99_tests.yh` 7 项；`libs/project.toml` 登记 fmt；
  `make test-lib-tests` 覆盖 string 5 项与 fmt 7 项，全绿。
- **边界**：f64 默认渲染（R2）返回 `status_unsupported`，非空 spec（R1）
  返回 `status_invalid_spec`；print/sprint 与语言层插值未开始。
- **记录**：[R0 实施记录](01-finished/yh-fmt-R0-2026-10-24.md)。
- **验证**：`make` 冷编成功；未改编译器/语法，未跑全量门与自举门，未滚种子。

## 2026-10-24 io 标准库读写层（IO0–IO4）

- **内容**：`libs/io` 从四个写侧接口扩展为完整读写层：`read_all`/`read_file`/
  `write_bytes`/`write_file` 与调用方缓冲的 `Reader`/`Writer`（行读取、显式
  flush、粘滞错误与 `interrupted` 显式重试），`write_all_result`/`write_all`
  原样迁入 `20_write.yh`，`print`/`println` 留在 `io.yh`；新增
  `libs/io/{00_model,10_read,20_write,99_tests,doc}.yh` 与 `README.md`。
  完整记录见 [IO0–IO4 实施记录](01-finished/yh-io标准库读写层-2026-10-24.md)，
  设计见 [io 标准库设计](03-design/yh-io标准库设计-2026-10-24.md)。
- **门禁**：`yh test io` 已接入 `make test`、`make selfhost-native` 与
  `make test-lib-tests`（`yh test` 一次只接受一个模块，故单独一行）。
- **验证**：`yh test io` 7/7；`make test` 全绿（语法 81/81、49/49；run
  211/212；fail 136/136；pass 9/9；test-check 38/38；string 5/5；io 7/7；
  compiler-tests 3/3；TOML 6/6；代码统计 6/6）；`make selfhost-native` 通过
  （两代固定点、自解析 114 文件、project cases 121/121）。
- **分支**：交付提交 `a026dbe`，经 `--no-ff` 合入 `llvm`；合入时
  `docs/finish.md` 已被滚动归档重写，条目按"新增写在最前"手工前移。
- **边界**：IO5（toml 读文件迁移）与 IO6（seek/copy，依赖 `os` 补
  `lseek`/`fstat`）未实施；未滚种子、未推送。

## 2026-10-24 finish 文档滚动归档（只保留最近三天）

- **做法**：`docs/finish.md` 从 7,952 行压到 814 行（含本条），只留
  2026-10-22～2026-10-24 的 47 条；更早的 384 条（2026-09-27～2026-10-21）迁入
  [finish 历史归档](01-finished/finish-历史归档-2026-09-27至2026-10-21.md)，附日期索引表
  （日期、条目数、首个条目标题）。
- **层级统一**：原先 105 条写成一级标题的旧条目统一降为二级标题（条目内子节降为
  三级），保留段按日期倒序重排、同日保持原序，归档段沿用原始顺序以便对照 git。
- **引用同步**：ADR-0006/0007/0014 与 `03-design/yh-LLVM后端替换设计.md` 中指向
  已归档条目的精确引用改指归档文件；`AGENTS.md` 目录说明补上归档规则。
- **校验**：新旧文件非空行多重集合比对零缺失，日期条目 431 = 47 + 384 守恒。
  本次只改文档，未运行构建与门禁。

## 2026-10-24 架构优化 A4b-4 / A5：build 状态收窄与前端装配收敛

### A4b-4：build 的 `gen.G()` 141 → 101

- 同 A4b-1/2/3 的模式：只依赖任务态的函数改 `let tk *gen.TaskCtx = gen.task()`。
- 全仓 `gen.G()` **205 → 165**（build 141 → 101、testkit 27、parse 21、main 5）。
- **到此为止的理由**：build 剩余读点主要落在 `p_projs`(204 次)/`p_mods`(124)/
  `p_files`(69)/`c_target`(56)——build 是项目模型的**所有者**，给它加窄口是
  本末倒置。要继续收敛必须做 `BuildCtx` 对象化，即已推迟的重构。

### A5：`front_prepare` 收敛前端装配

- 原状：`ty_register_builtins → scope_push → sem_register_prelude` 这个三元组在
  `llvm_emit`（单文件）与 `module_worker`（模块）各写一遍，且 **worker 侧漏检了
  `ty_register_builtins` 的返回值**。
- 做法：`builtin.prelude.yh` 新增 `pub fn front_prepare() int`，两处调用点各缩成
  一次判返回。
- **`sem_init_tables` 刻意不并入**：它必须跟在每模块标志
  （`c_module_mode`/`c_is_entry_mod`/符号后缀）之后，前置会改变语义。此约束写进
  助手注释。
- **顺带修正**：worker 现在也检查 `ty_register_builtins`/`scope_push` 的失败。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；project 123/123。

## 2026-10-24 评审记录：A7 不是纯搬迁

- 原判：`ast/module_snapshot_lower*` + `ast_ir*`（10 文件 4,739 行）可整体移出
  `ast`，只要把 `lower_module` 的调用上移到 `build`。
- 复查：`lower_module` 的调用点在 **`ast/module_snapshot_check_slice.yh`**，
  属于 check 流水线内部（产出 CheckedModule 的切片阶段），不是驱动器里的
  一次性调用。也就是说 `check ↔ lower` 是**流程耦合**，不是模块边界问题。
- 结论：A7 要成立，得先把"check 产出 CheckedModule"与"lower 消费它"两段拆开，
  让驱动器在拿到快照后再触发 lowering。这属于流程重构，与 `build` 的 CLI 标准库
  重构同批处理，**不做表面搬迁**（搬了只会把循环依赖变成跨模块循环）。

## 2026-10-24 架构优化 A6：测试执行器抽成 testkit 模块

- **定位修正（先于实施）**：原计划"移出编译器二进制"被否——拆独立二进制不减少
  耦合（仍调 43 个 build/gen 符号），却增加构建目标、安装路径与版本一致性成本。
  改为**抽成独立模块、保留 `yh test` 子命令**，收益是复用（编辑器/CI 可直接调）
  而非缩小二进制。
- **模块名不能叫 `test`**：`test "..." {}` 是语言关键字，`module test` 直接报
  「此处需要一个导入模块名」。取名 **`testkit`**。
- **迁移**：`cmd/test_cmd.yh`（1,520 行）→ `compiler/testkit/test_cmd.yh`，
  `module main` 改 `module testkit`；入口 `mb_run_test_command` 补 `pub`，
  `cmd/api.yh` 加 `import testkit` 并改调用前缀。
- **再解一个反向依赖**：`test_cmd` 有 5 处 `usage()`（CLI 用法文本）。删除这 5 处，
  由 `driver` 在 `api_test` 返回 2 时统一打印——测试执行器不该输出 CLI 帮助。
- **规模**：`main` **1,898 → 381 行**（占全仓 **0.7%**，只剩 `driver` + `api`）；
  新增 `testkit` 1,515 行。模块数 11 → **12**，依赖边 29 → 33，无环。
- **预算**：`max_module_lines` 1898 → 381，新增 `max_testkit_lines = 1515`，
  `max_cmd_share_pct` 4 → 1。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；`yh test` 行为不变
  （compiler-tests 3/3 即经 `yh test` 执行）；project 123/123。

## 2026-10-24 架构优化 A4d：测试选择条件收进 gen，ast 清零 GenState

- **先核实"文件级跳过"是否已经存在**：`tc_discover` 第 516 行已按 `mod_filter`
  跳过不匹配模块，`tc_select` 会把"文件选择器"归约到该文件所属模块
  （`mod_filter = p_files[f].mod`）。所以 `--filter` 在**模块粒度**已经是
  文件级跳过，不会为无关模块做测试发现。
- **不能再细到"模块内跳过兄弟文件"**：yh 的模块是目录，声明可跨文件，
  `tc_index_file` 必须索引同模块的全部文件才能解析标识符。跳过会破坏解析。
- **真正的问题在层次**：`parse_decl` 与 `ast_decl` 各自抄了一份"该文件是否属于
  本轮测试目标"的判断，直接读 `c_test_project`/`c_test_mod_filter`/
  `c_test_file_filter`——前端在替测试执行器做决定。
- **做法**：把判断收进 `gen.test_file_selected(fi)`，前端只问"这个文件要不要
  登记测试声明"。两处调用点从 12 行判断缩成 1 行。
- **效果**：`gen.G()` 207 → 205；**`ast` 模块的 GenState 直接访问清零**
  （9 → 0），parse 22 → 21。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 213/214、
  fail 137/137、project 123/123。
- **剩余**：`build` 侧（`project_resolve`/`module_build`/`module_worker`）还有
  4 处读同一批过滤字段，属构建引擎自身的调度条件，随 build 重构一并处理。

## 2026-10-24 架构优化 A4c：前端窄口访问器（不扩 TaskCtx）

- **先否掉一个方案**：原计划"把 `p_files`/`c_module_mode`/`c_target` 纳入
  `TaskCtx`"。这些是**构建期**状态（文件表、目标、模块模式），`TaskCtx` 是
  **每任务工作状态**——混进去会让 RS1d 的线程模型失去边界。改为给前端一个
  **窄口只读访问**：
  `gen.p_file(i)`、`gen.p_file_count()`、`gen.module_mode()`。
- **效果**：parse/ast 不再直接触碰 `GenState` 字段，`gen.G()` 调用点
  **216 → 207**（parse 25 → 22、ast 9 → 3）。
- **剩余 25 处的真实原因**（记录，避免下次重复试探）：
  * `c_test_project`/`c_test_mod_filter`/`c_test_file_filter`——**测试执行器的
    过滤条件漏进了 parse**，这是层次问题，不是访问器能解决的；应在 `yh test`
    侧先筛文件，parse 不该知道 `--filter`。
  * `c_target`/`c_is_entry_mod`/`p_mods`——需按用途各自设计窄口。
- **语言坑**：`gen.p_file(i)[0]` 不合法（不能对调用结果下标），必须
  `let p *gen.PFile = gen.p_file(i)` 再 `p[0]`。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 213/214、
  fail 137/137、project 123/123。

## 2026-10-24 语言变更：`len` 不再是严格保留字

- **问题**：`len` 在内置函数 `len(x)` 里是关键字（`TK_LEN`），词法阶段一律识别为
  关键字，导致 `let len int = 0`、`fn f(len int)` 这类命名被拒——A0c2 期间写
  `append_np_cap(buf, cap, n, off, len)` 就撞上「此处需要一个参数名」。
- **做法**：`lex/lexer.yh` 的 `lex_ident` 里，`len` **只有后接 `(`（可隔空格/制表）**
  才归为 `TK_LEN`，其余位置退化为普通标识符。其余保留字没有"关键字/标识符"双义，
  保持严格保留。
- **用例**：新增 `tests/yh-run/run/len-as-identifier.yh`（形参 `len`、局部 `len`、
  内置 `len(xs)` 共存）；`tests/yh/rejected/08_reserved_ident.yh` 从 `len` 改为
  `sizeof`——该反例断言的是"保留字不能作标识符"，换一个仍然严格保留的字。
- **验证**：`make test`、`make selfhost-native` 全绿；run 213/214（+1 新用例）、
  fail 137/137、pass 9/9、project 123/123。

## 2026-10-24 架构优化 A0c2-2：诊断拼装继续加固

- 又加固 3 处「小缓冲 + 用户数据」：`project_resolve` 的入口模块导入诊断
  （`[128]`，拼导入名）、`imp_diag`（`[512]`，拼文件路径）、`toml` 的
  `tml_err`（`[512]`，拼清单路径）。
- 容量安全追加点 **29 → 45**，`arch-check` 的 `min_cap_appends` 随之上调到 45。
- 剩余约 40 处经复查多为"只拼字面量"的固定格式缓冲（`iface` 的内嵌测试、
  用法文本等），无溢出风险；真正的用户数据入口已全部走 `_cap`。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；产物逐字节不变。

## 2026-10-24 架构优化 A0c2-1：容量受限追加原语与诊断入口加固

- **先量化再动手**：全仓 **235 个固定栈缓冲、654 处拼接**。静态分析（字面量
  字节 + 非字面量拼接计数）显示：没有"字面量本身就超容量"的确定溢出（两处告警
  都是 `n=0` 复用同一缓冲的误报），但**47 个小缓冲（≤512）拼接了非字面量数据**
  ——路径、导入名、模块名这些长度不可预估的输入才是真实风险。
- **新增原语**（`gen/buffer.yh`）：`append_str_cap`、`append_byte_cap`、
  `append_int_cap`、`append_np_cap`。约定 `cap` 是缓冲总字节数，最多写 `cap-1`，
  写满即止并保持 NUL 结尾——**截断的诊断仍可读，栈破坏不可**。
- **加固的入口**：
  * `gen.fail` / `gen.fail_path`——所有诊断的公共出口，此前用 `[512]` 拼
    「前缀 + 消息 + 路径」，深路径必然越界；
  * `parse/iface.yh` 的 `iface_head_bad`（`[360]` + 路径）；
  * `build/module_build.yh` 的「顶层声明与导入名冲突」诊断（`[192]` + 导入名）。
- **进度指标**：`arch-check` 新增**下界**预算 `min_cap_appends = 29`
  （容量安全追加点只增不减），报告里单独显示。其余预算都是上界，这一条是唯一
  的"必须增长"指标。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 358/359、
  fail 137/137、project 123/123、LA3 O0/O2 通过；产物逐字节不变。
- **剩余**：47 个小缓冲中还有约 43 处未加固（`project_resolve` 9 处、
  `toml` 5 处、`iface` 若干），按同一模式逐个替换，指标随之上调。

## 2026-10-24 架构优化 A4b-3：剩余前端读点收窄

- **做法**：同 A4b-1/2 的模式，对 `lex`/`check`/`builtin`/`parse` 中只依赖任务态
  的函数改写为 `let tk *gen.TaskCtx = gen.task()`。
- **效果**：`gen.G()` 调用点 **233 → 216**。分模块：build 141、cmd 32、parse 25、
  ast 9、comptime 3、check 3、gen 2、lex 1（14→1）、builtin 0（2→0）、
  ir/backend 0。`arch-check` 的 `max_g_call_sites` 随之下调到 216。
- **为什么停在 216**：剩余读点集中在三类不可机械迁移的位置——
  ① 函数内同时用到 `p_files`/`c_module_mode`/`c_target` 等构建期字段；
  ② 把 `gs` 整体传给下游（裸引用）；③ `build`（141）与 `cmd`（32）需要等
  构建态对象化。继续迁移要么扩 `TaskCtx`，要么改下游签名，属独立设计决定。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 358/359、
  fail 137/137、project 123/123、LA3 O0/O2 通过。

## 2026-10-24 架构评审记录：A7（lower 独立）被环阻塞

- 评估结论：`ast/module_snapshot_lower*` + `ast_ir*` 共 10 文件、4,739 行，
  搬出 `ast`（9,041 行）后可形成独立 `lower` 层。**但存在环**：
  `ast/module_snapshot.yh` 仍有 4 处调用 `lower_module`，而 lower 侧依赖
  ast 的 57 个符号（`CheckedModule` 等）。
- 解环唯一干净路径是把这 4 处调用上移到 `build`（构建引擎决定何时 lowering），
  而 `build` 当前冻结（后续改用 CLI 标准库重构）。故 A7 暂缓，待 build 重构时
  一并处理。
- 若强行先搬，只能在 `ast` 留一个转发壳，反而加深耦合，不做。

## 2026-10-24 架构优化 A2c：构建引擎迁入 build

- **迁移**：`link_cache`、`link_inputs`、`module_build`、`build_scheduler`、
  `module_worker`、`function_ir_cache`、`llvm_pipeline`、`llvm_emit`、`darwin_link`
  共 9 文件 → `compiler/build/`；21 个符号补 `pub`，`cmd` 侧调用改 `build.` 前缀。
- **先解一个反向依赖**：`module_build` 会在参数错误时调用 CLI 的 `usage()`，
  搬过去会形成 `build → main` 环。改为返回 2，由 `driver` 在 `rc == 2` 时打印用法
  ——构建层不该输出 CLI 帮助。
- **两个只写全局的受控入口**：`c_argv0`（自身路径）与 `mb_iface_suffix`
  （子进程协议）不能跨模块导出（`pub` 只用于 fn/const/struct/union/enum），
  各给一个 setter（`mb_set_argv0`/`mb_set_iface_suffix`）。
- **`@[extern] fn realpath`** 原先在 `link_inputs.yh` 里未导出，`test_cmd` 单文件
  路径解析要用，补 `pub`（扫描脚本按行首 `fn` 匹配会漏掉 `@[extern]` 前缀）。
- **规模**：`main` **9,119 → 1,898 行**（占全仓 **4%**）；`build` **3,501 → 10,720**。
  `arch-check` 预算改为 `main 1898` + 新增 `build 10720`（构建引擎后续应**拆分**
  而非增长），`max_cmd_share_pct` 18 → 4。
- **依赖矩阵**：`build` 升为构建引擎，允许依赖全部下层
  （gen/lex/parse/comptime/ast/check/ir/backend/builtin）；`main` 只剩
  CLI 与测试执行器。共 29 条边，无环。
- **过程中的四个坑**：① 搬过来的文件在 A2b-2 时被加过 `import build`，成
  `build → build` 自环；② 文件里遗留 `build.` 自引用前缀需剥除；
  ③ setter 插入被执行两次导致重定义；④ 去重脚本误删
  `let mb_compiler_fingerprint u64 = 0`，编译报「引用了未声明的名字」。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 358/359、
  fail 137/137、project 123/123、LA3 O0/O2 通过。

## 2026-10-24 架构优化 A2b-2：项目模型迁入 build

- **迁移**：`project`、`project_state`、`project_index`、`project_resolve`、
  `project_link`、`toml`、`project_dir.{darwin,linux.arm64,linux.x64}` 共 9 个
  文件 → `compiler/build/`，`module main` 改 `module build`；33 个被 main 引用的
  符号补 `pub`，main 侧约 120 处引用改 `build.` 前缀。
- **先解掉一个反向依赖**：`project_index` 调用了 `test_cmd` 里的
  `pj_classify_test_imports`（判定导入是否 test_only）。若直接搬，会形成
  `build → main` 环。已把这组三个函数（`pj_imp_alias_match`/
  `pj_mark_test_tokens`/`pj_classify_test_imports`）移到项目模型侧——它们本就是
  项目导入分类逻辑，只是原先寄居在测试执行器里。
- **依赖矩阵更新**：`build → lex, parse` 是真实边——项目加载要读每个源文件的
  `module` 头（`lex.lex_all`/`parse.mod_parse_head`）。已在 `arch-check` 的
  ALLOWED 中登记并注明理由。
- **规模**：`main` **12,390 → 9,119 行**（−3,271）；`build` **224 → 3,501 行**；
  `main` 占比 **24% → 18%**。预算同步下调（`max_module_lines` 9119、
  `max_cmd_share_pct` 18），只减不增。
- **过程中踩的坑（记录）**：搬 `pj_classify_test_imports` 时切片按"下一个 `fn`
  开头"取界，把中间的 `TCase`/`TDecl` 结构与 9 个 `tc_*` 全局一起带进了
  `build`；这些属于测试执行器状态，又得搬回。搬回时还犯了第二个错——插在
  `tc_reset` 之前，而 `tc_identity` 在第 94 行就用到 `TCase`（yh 要求类型先
  定义），最终从 `git show HEAD:` 取回原块插到文件顶部才通过。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 358/359、
  fail 137/137、project 123/123、LA3 O0/O2 通过。

## 2026-10-24 架构优化 A2b-1：项目模型状态收敛为 PjState

- **为什么先做这一步**：A2b（把 project_* + toml + project_dir 搬进 `build`）
  的阻塞点不是文件，而是 6 个模块级全局被 `module_build`/`link_cache`/
  `build_scheduler`/`test_cmd` 直接读写共 **93 处**，其中还有
  `&pj_canon_off` 这类**取址传参**。先把它们收进结构，搬迁才可能只是"换前缀"。
- **做法**：`cmd/project_state.yh` 新增
  `pub struct PjState { canon_off, canon_len, order, order_n, mark, envp,
  root_off, root_len }` + `pub fn pj_state() *PjState`；删除 8 个旧全局
  （`pj_canon_off/len`、`pj_order(_n)`、`pj_mark`、`pj_envp`、
  `pj_root_project_off/len`），93 处引用改为 `pj_state().<field>`；
  取址写法 `&pj_canon_off` 变 `&pj_state().canon_off`，语义不变。
- **效果**：模块级可变 `let` **190 → 183**（净减 7：8 个全局换 1 个状态实例）。
  `main` 12,374 → 12,390 行（结构定义 +24、删全局 −8），
  `arch-check` 的 `max_module_lines` 随之上调，注释标注"搬迁后必须下降"。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 358/359、
  fail 137/137、project 123/123、LA3 O0/O2 通过。
- **下一步（A2b-2）**：九个文件整体迁入 `build`，此时只需给 ~27 个函数补
  `pub`、并把 main 侧的 `pj_state()`/`pj_*` 换成 `build.` 前缀。

## 2026-10-24 架构优化 A4b-2：comptime/ast 依赖收窄

- **做法**：沿用 A4b-1 的模式（`gen.task()` + `*TaskCtx`），把 comptime 与 ast
  中只依赖任务态的函数改写；`tk` 作为局部名，避免与既有 `t` 冲突。
- **效果**：`gen.G()` 调用点 **335 → 233**。分模块：cmd 173、parse 25、lex 14、
  ast 9（31→9）、check 5、comptime 3（83→3）、gen 2、builtin 2、ir/backend/build 0。
  `arch-check` 的 `max_g_call_sites` 随之下调到 233。
- **三次返工（批量改写的完整教训）**：
  1. 裸 `gs` 检查把**声明行**与 `&gs.task` 也算成裸引用，导致误判"可迁 9/83"；
     修正为排除声明行、且 `gs.` 后缀不算裸引用后，真实可迁面是 81/83。
  2. `DECL.sub(body)` 漏了 `re.M`，声明行没被替换而字段访问已改，编译报
     「引用了未声明的名字」；补 `re.M` 并加自检"出现 `tk.` 必须有 `let tk`"。
  3. 首版用 `str.replace("gs.task.", "tk.")` 做**子串**替换，把 `m_gs.task.`
     改成了 `m_tk.`；改用词边界正则 `(?<![A-Za-z0-9_])gs\.task\.`。
- **顺带修正守护器**：`malloc` 检测原先把「赋值形式 + 判空在 16 行后」误报为
  未判空（`ct_registry`/`module_snapshot_lower` 共 3 处）。改为类型可缺省的
  变量名提取 + 回退窗口 6→20 行，误报归零，仍能抓到真正未判空的分配。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 358/359、
  fail 137/137、project 123/123、LA3 O0/O2 通过。

## 2026-10-24 架构优化 A4b-1：parse 依赖收窄到 TaskCtx

- **问题**：`gen.G()` 返回整个 `GenState`，但前端只用到其中的 `task` 字段。
  parse 的 155 个读点里 **147 个只用 `gs.task.*`**——依赖面本可以更窄。
- **做法**：`gen/state.yh` 新增 `pub fn task() *TaskCtx`；parse 中只依赖
  `task` 的 130 个函数改 `let t *gen.TaskCtx = gen.task()`，字段访问
  `gs.task.X` → `t.X`。仍在用 `p_files`/`c_module_mode`/统计计数/测试过滤的
  函数保留 `gen.G()`（parse 剩 25 个读点）。
- **效果**：全仓 `gen.G()` 调用点 **466 → 335**（main 173、comptime 83、
  ast 31、parse 25）；parse 对 `GenState` 的依赖从"整个单例"降为
  "任务上下文 + 少量构建期字段"。`arch-check` 的 `max_g_call_sites`
  随之下调到 335，并在报告里按模块显示分布。
- **过程中的两次返工（记录以备后鉴）**：
  1. 首版改写按**正序**处理函数块，但每块改写会改变行数，后续块的行号随之
     漂移，`parse_decl.yh`/`parse_global_init.yh` 被写坏（`--syntax-check`
     立即报「此处需要一个表达式」）。恢复后改**自底向上**处理。
  2. 变量名 `t` 与函数内既有的裸 `gs` 传参冲突（如
     `iface_ct_col_parse(gs, ...)`），首版只检查了 `gs.` 未检查裸 `gs`，
     导致「引用了未声明的名字」。已按"裸 `gs` 出现即回滚该函数"修复。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 358/359、
  fail 137/137、project 123/123、LA3 O0/O2 通过。

## 2026-10-24 架构优化 A3：api 调用面

- **问题**：`driver.yh`（337 行）既解析 argv，又直接调用前端、后端、构建实现；
  `--emit-module` 的内部协议也内联在 main 里。命令解析与执行耦合，无法被
  其他调用方（LSP、测试器）复用。
- **做法**：新增 `compiler/cmd/api.yh`（142 行）作为唯一执行面：
  `api_single_file(path, form, out)` 收敛五种单文件形态（语法/检查/汇编/
  LLVM 文本/可执行），共用 `api_open_source` 前奏与同一条受检前端；
  项目命令 `api_build/api_run/api_test/api_list/api_version/api_emit_module`
  各自一个稳定函数。`driver.yh` 337 → 230 行，只做 argv → 请求映射。
- **契约**：返回 0 成功、1 源/语义错误、2 用法错误、-1 内部或桥失败；
  诊断写 fd 2；单文件各形态不得各自重写前奏。
- **过程中发现的门禁盲区**：重构时把 `API_ASM` 与 `API_LLVM_TEXT` 的参数写反，
  `--emit-asm` 输出成 LLVM IR，而 `make test` / `make selfhost-native` 全绿——
  语料只编译+运行，从不看 `--emit-asm` 的文本形态。已补
  `p1-emit-asm-form`：断言输出不含 `source_filename` 且含汇编指令，
  并**直接调用二进制**（不经 `sh()` 注入门禁参数），project cases 122 → 123。
- **预算调整**：`main` 12345 → 12374 行（driver −107、api +142、净 +29）。
  `arch-check` 的 `max_module_lines` 随之上调到 12374，注释标注 A2c 后必须下降。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 358/359、
  fail 137/137、project **123/123**、LA3 O0/O2 通过。

## 2026-10-24 架构守护 arch-check 与 A2b 暂缓

- **A2b 暂缓的技术理由**：项目模型九文件（project_* + toml + project_dir）
  互相咬合，无法拆小：`toml.yh` 的解析区被 `project_index`/`project_link`
  按下标直接读；`pj_canon_off`(41 处)/`pj_canon_len`(30)/`pj_order`(18)/
  `pj_order_n`(2)/`pj_mark`(1)/`pj_envp`(1) 共 **93 处**跨文件读全局，必须
  改 `pub fn` 访问器；而 A4（Session/状态归属）会把这批访问器再改一遍。
  先做守护、再做搬家，避免同一批代码返工两次。
- **新增 `tools/arch-check.py`**：①依赖矩阵与环检测（11 模块、26 条边）；
  ②8 项预算——文件/函数/模块行数、`main` 占比、模块级可变 `let`、
  `gen.G()` 读点、未判空 `malloc`、未接线 `pub`；③数值报告。
  `--report` 只报告不失败，`--root` 供自测指定源码根。预算上调必须改脚本
  并说明理由，这是刻意摩擦。
- **守护自身有测试**：`tests/tools/arch-check/check.py` 覆盖两条路径——真实树
  必须通过、注入 4000 行文件后必须被 `max_file_lines` 抓到。首跑即暴露
  `--root` 下 `relative_to(ROOT)` 崩溃的真实缺陷（已修）。
- **接入**：`make test` 追加两条（自测 + 守护）；新增
  `make arch-check` / `make test-arch-check`。
- **当前基线**：11 模块 / 113 文件 / 51,327 行；`main` 占 24%（12,345 行）；
  模块级可变 `let` 190；`gen.G()` 466 个调用点；未判空 `malloc` 0；
  最大文件 `module_build.yh` 2,242 行；最大函数 `mb_link` 674 行。
- **验证**：`make test`、`make selfhost-native` 全绿；project 122/122。

## 2026-10-24 架构优化 A2a：切出 build 模块（无状态工具层）

- **切分结论（先于代码）**：`cmd` 是一个模块，文件间共享模块私有函数与 66 个
  全局。按"文件大小"切子模块会形成 `main → build → main` 环，因此**必须按
  状态归属切**：先把无状态工具层移出，再随其状态一起搬项目模型。
- **本次迁移**：`cmd/{process,clock.darwin,clock.linux.arm64,clock.linux.x64}.yh`
  → `compiler/build/`，`module main` 改 `module build`；4 个函数补 `pub`
  （`cmd_process_run`/`cmd_process_capture`/`cmd_process_status`/`cmd_mkdirs`/
  `cmd_clock_ns`）。`cmd` 侧 7 个文件加 `import build`，约 30 处调用改
  `build.` 前缀。
- **为什么 `toml.yh` 没跟着搬**：它带 9 个模块级解析区全局（`toml_secs`
  等），`project_index`/`project_link` 直接按下标读字段。跨模块访问全局必须
  经 `pub fn`（AGENTS 的 `gen.G()` 模式），单独搬会先被迫把整张解析表改成
  访问器——属于 A2b"项目模型 + 清单解析一起搬"，不放进纯搬迁切片。
- **规模**：`cmd` 12,502 → 12,345 行；新 `build` 模块 224 行（4 文件）。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 358/359、
  fail 137/137、project 122/122、LA3 O0/O2 通过；产物逐字节相同（固定点）。
- **后续**：A2b 项目模型（project_state/index/resolve/link + toml）→
  A2c 链接/缓存/调度/worker → A2d `cmd` 收为 CLI 薄壳。

## 2026-10-24 架构优化 A1b/A1c：契约版本可查询与 manifest 定策

- **A1b 契约版本命令**：`yh version --contracts` 输出五行 `key=value`——
  `iface-min`/`iface-max`/`ctiface`/`ir-function`/`ir-module`，值直接取自
  `parse.IFACE_VERSION_*`、`parse.CTIFACE_VERSION`、`ir.IR_SERIAL_VERSION`、
  `ir.IR_MODULE_SERIAL_VERSION`，不另存副本。该命令不要求当前目录有项目，
  CI 与外部工具（yh-explorer、VSCode 扩展）可直接协商。
  `module_build.yh` 为此补 `import ir`；`usage()` 增一行。
- **A1c manifest 版本策略（决定：不加显式版本）**：manifest 为 64 字节
  = 模块键 16 + 对象摘要 16 + 每文件接口摘要 16×N；键含编译器二进制指纹与
  全部输入内容，任何格式变更必然换编译器，旧键随即不匹配；长度检查挡住
  布局变更。决策与"改布局必须同时改长度或键组成"的约束写进
  `module_build.yh` 校验处注释，不引入没有消费方的版本字。
- **用例**：`p1-version-cmd` 扩展为同时校验 `version` 与
  `version --contracts` 的五个键（不写死具体数字，版本升级时无需改测试）。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 358/359、
  fail 137/137、project 122/122、LA3 O0/O2 通过。未执行 `make seed`。

## 2026-10-24 架构优化 A1a：接口头行版本化收口

- **问题**：`.s.i` / `.s.ct` 头行用三条硬编码字面量 + 手写长度（33/35）比对；
  新增版本要同时改写入端三处、读取端常量与长度；架构永远写着 `arm64`，
  读取端并不校验目标——接入 x64 后头行会"说谎"。
- **做法**：改为结构化解析 `// yh-<kind> v<N> arch=<arch> suffix=<sfx>`：
  版本按 `[IFACE_VERSION_MIN, IFACE_VERSION_MAX]` 区间校验（`.s.ct` 必须等于
  `CTIFACE_VERSION`），架构与 `gen.target_arch_token()` 比对，长度用
  `gen.cstr_len` 计算。写入端架构改为随目标取值。
- **可测试性**：校验函数拆成纯函数 `iface_head_prefix_len_at(src, n)` /
  `iface_ct_head_prefix_len_at(src, n)`，内嵌测试直接构造字节序列。
- **用例**：`parse/iface.yh` 新增 2 条内嵌测试（版本 0/4 越界、架构不符、
  缺 suffix 截断、空输入、CT 版本必须为 1）；`compiler-tests/parse` 3 → 5。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 358/359、
  fail 137/137、project 122/122、LA3 O0/O2 通过。头行字节与旧版一致
  （`// yh-iface v1 arch=arm64 suffix=__yh__parse_`），固定点不变。
- **未覆盖**：IR 序列化本就有 magic（`YHIRSSA1`/`YHIRMOD1`）+ 版本字；
  manifest 仍是内容键（含编译器指纹）无显式版本；`yh version` 尚未报告
  契约版本集合。后两项已由 A1b/A1c 收口。

## 2026-10-24 架构优化 A0d/A0e：统一分配入口与删除 ir_simplify

- **A0d 统一分配**：新增 `gen.alloc(size u64) *u8`（`gen/buffer.yh`）。分配失败
  时向 stderr 写「yh: 内存不足，无法继续」并 `exit(1)`——编译器在 OOM 下无法
  继续，这比解引用空指针后无声崩溃可诊断。这是编译器里**唯一**的进程级退出点。
  50 处「分配后 4 行内未判空」的 `malloc` 改为 `gen.alloc`/`alloc`；`ir` 模块
  保持零依赖（不能 `import gen`），其 6 处维持 `malloc` + 显式判空。
- **A0e 删除 `ir_simplify`**：`compiler/ir/ssa.yh` 删除 `ir_simplify`、
  `ir_alias_root`、`ir_normalize_int`（1,112 → 859 行）。依据 ADR-0014：通用
  优化归 LLVM，该函数生产路径调用点为 0，只被 `irverify` 用例直接调用。
- **用例同步**：`irverify` 去掉 simplify 断言；round-trip 断言从「化简后的
  CONST 30 / term_value 3」改为「未化简的 `IR_OP_ADD` / term_value 4」，
  更直接验证序列化保真。`ir_const_type`/`ir_scalar_type`/`ir_integer_type`/
  `ir_float_type` 仍被后端与 lowering 使用，保留。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；run 358/359
  （1 平台跳过）、fail 137/137、project cases **122/122**、LA3 O0/O2 缓存矩阵
  通过。未执行 `make seed`。

## 2026-10-24 架构优化 A0c：路径预算

- **问题**：`mb_mod_tag` 把「项目名-模块名」拼进 `[512]u8` 且不检查长度，
  派生的接口/对象路径又写进 600/700/900 字节定长缓冲；`gen.append_str`
  本身不做容量检查，超长名字会写穿栈。
- **做法**：在源头设两个预算——`MB_TAG_MAX = 120`（项目名+模块名）、
  `MB_BUILD_DIR_MAX = 400`（构建目录）。`mb_mod_tag` 先算长度再拒绝，
  `mb_build_dir` 收敛为单出口并校验 `pj_canon_len`。派生路径最长
  400+7+120+5+1 = 533 < 600，最小缓冲也安全。超限报
  「模块名过长：项目名与模块名合计超过 120 字节」/「项目路径过长：…」。
- **用例**：新增 fixture `tests/modules/projects/longname`（130 字节项目名）与
  `case("u7-module-name-too-long", "fail", ...)`，锁诊断文案。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；project cases
  **122/122**（新增 1 例）。未执行 `make seed`。
- **说明**：构建目录预算属防御性检查——项目根通常以相对路径 `"."` 参与
  `pj_canon`，实际触发点是标记预算；保留该检查是为了将来 LSP/绝对路径入口。

## 2026-10-24 架构优化 A0：表达式嵌套守卫与未接线代码删除

- **背景**：[代码复核](03-design/yh-代码复核-2026-10-24.md) 实测表达式递归无深度
  上限（2,000 层通过、4,000 层 SIGSEGV），且 `ir/ssa_inline.yh` 无任何调用点。
- **删除**：`compiler/ir/ssa_inline.yh`（283 行；`ir_inline_one`、
  `ir_inline_candidate_ok` 调用点 0，编译器/库/语料/工具均无引用）。
  `ir` 模块 4,766 → 4,483 行。`ir_simplify` **保留**：`tests/modules/projects/
  irverify` 仍在测它，删除需同步改测试项目，另立切片决定。
- **守卫**：`parse_expr` 拆为入口包装 + `parse_expr_inner`；`PX_NEST_MAX = 256`
  （对齐 Clang `-fbracket-depth` 缺省，且给 1 MB 线程栈留余量）。超限经
  `gen.err_tok` 在当前 token 报「表达式嵌套层数超过上限 256」并返回 1。
  计数成对进出，内层任意 return 路径由包装统一回收。
- **用例**：`tests/yh-run/fail/100-expr-nest-depth.yh`（300 层，`fail-contains`
  锁文案）、`tests/yh-run/run/expr-nest-depth-ok.yh`（200 层，`expect: 1`，
  锁"不误伤合法深度"）。
- **验证**：`make`、`make test`、`make selfhost-native` 全绿；yh-run 358/359
  （1 例平台跳过）、project cases 121/121。未执行 `make seed`。

## 2026-10-23 0.0.9 正式版发布与验收

- **发布**：`0.0.9-rc` 以 `--no-ff` 合入新建的 `0.0.9-release`（起点
  `0.0.8-release`），打正式 tag `0.0.9`；Gitea `release.yml` run 65 五个作业
  全部 success，创建正式 Release 并上传三端资产。`ci.yml` 分支门 run 64 通过。
- **验收**：发布种子（`56bf3f56…ca6ceb8`，`yh 0.0.9`）装入
  `bin/yh-darwin-arm64` 后，`make`、`make test`、`make selfhost-native` 全绿
  （语法 81/81、49/49；run 211/212；fail 136/136；pass 9/9；test-check 38/38；
  string 内建 5/5；compiler-tests 3/3；TOML 6/6；固定点 30 产物、
  自解析 114 文件、project cases 121/121）。
- **分支**：`0.0.9-rc` 已按流程删除，保留 `0.0.9-release`。
- 说明见[release-0.0.9](01-finished/release-0.0.9.md)。

## 2026-10-23 0.0.9 正式版开发

- **版本**：`compiler/project.toml` 保持 `0.0.9`；发布说明见
  [release-0.0.9](01-finished/release-0.0.9.md)。
- **内容**：在 rc.1/rc.2 基础上完成 YT2d（逐例日志与截断提示、并行执行、
  测试构建缓存键）与 YT1.1（项目外单文件临时单模块上下文），
  `test-check.py` 增至 38 项；`ci.yml` 分支门 Darwin 与 Linux/AArch64 均通过。
- **验证**：`make test` 与 `make selfhost-native` 全绿（语法 81/81、49/49；
  run 211/212；fail 136/136；pass 9/9；test-check 38/38；string 内建 5/5；
  compiler-tests 3/3；TOML 6/6；固定点 30 产物、自解析 114 文件、
  project cases 121/121）。

## 2026-10-23 yh test 项目外单文件（YT1.1）

- **实现**：`yh test <项目外文件>` 为单文件建立临时项目
  （`<源文件目录>/tmp/yh-test/single`，`source` 指向源文件目录但扫描只接受
  该文件），相邻 `.yh` 与子目录不装入；模块名取 `module` 头，缺失时由文件名
  派生；允许导入标准库；`--list/--no-run/--filter/--timeout/--emit-llvm`
  全部沿用。完整记录见
  [YT1.1 实施记录](01-finished/yh-test项目外单文件-2026-10-23.md)。
- **语料**：`tests/modules/single/`（无 module 头、导入标准库、故意写坏的相邻
  文件），`test-check.py` 增至 38 项。
- **验证**：`make test` 与 `make selfhost-native` 全绿（语法 81/81、49/49；
  run 211/212；fail 136/136；pass 9/9；test-check 38/38；string 内建 5/5；
  compiler-tests 3/3；TOML 6/6；固定点 30 产物、自解析 114 文件、
  project cases 121/121）。
- **边界**：单文件模式无 `[link]`/`[c]` 配置，只能用默认链接环境；临时项目根
  固定，同目录并发执行会互相覆盖。

## 2026-10-23 yh test 测试构建缓存键（YT2d-2）

- **实现**：`GenState.c_test_key` 记录本轮选中测试集合摘要（模块/文件/声明号/
  种类），模块 manifest 键在既有字段后混入「测试模式 + `yh-test-key-1` +
  摘要」；测试构建目录仍是 `tmp/yh-test/check`，与生产 `.build` 天然隔离。
  `mb_compile_start` 不再对测试模式强制绕过缓存，调度器也提交测试 manifest。
  完整记录见[YT2d-2 实施记录](01-finished/yh-test测试缓存键-2026-10-23.md)。
- **语料**：`test-check.py` 增至 34 项（`test-build-cache-hit`、
  `test-cache-selection-isolated`）。
- **验证**：`make test` 与 `make selfhost-native` 全绿（语法 81/81、49/49；
  run 211/212；fail 136/136；pass 9/9；test-check 34/34；string 内建 5/5；
  compiler-tests 3/3；TOML 6/6；固定点 30 产物、自解析 114 文件、
  project cases 121/121）。
- **边界**：函数级 IR 与 check 切片缓存仍未用于测试构建（键不覆盖 `TK_TEST`
  声明）；测试构建目录不按 target 细分，跨目标交替构建会互相冲刷 manifest。
- **运维提示**：本机门禁偶发失败来自 macOS 清理 `$TMPDIR`，把 `FAST_DIR` 指到
  仓库 `tmp/faststage` 可稳定复现全绿。

## 2026-10-23 yh test 逐例日志与截断提示（YT2d-1）

- **实现**：每个用例的 stdout/stderr 重定向到
  `tmp/yh-test/log/<模块>-<序号>.log`，失败时报告日志路径并回显末尾 2 KiB
  （滚动窗口单遍读取）；断言消息上限 59 字节，记录偏移 71 写 `0x1e`
  截断标记，父进程按 UTF-8 边界回退并追加「…（消息已截断）」。
  修复 `@write` 声明：Darwin 的 printf 支持会声明它、Linux 走 syscall 不会，
  测试运行时按目标补声明（跨目标构建曾报 `use of undefined value '@write'`）。
  完整记录见
  [YT2d-1 实施记录](01-finished/yh-test逐例日志与截断提示-2026-10-23.md)。
- **语料**：`ytestskip` 新增「带输出的长消息失败」；`test-check.py` 增至
  30 项（`per-case-log-and-truncation`、`per-case-log-files`）。
- **验证**：`make test` 与 `make selfhost-native` 全绿（语法 81/81、49/49；
  run 211/212；fail 136/136；pass 9/9；test-check 31/31；string 内建 5/5；
  compiler-tests 3/3；TOML 6/6；固定点 30 产物、自解析 114 文件、
  modules 19/19、project cases 121/121）。
- **并行执行（YT2d-3）**：`YH_TEST_JOBS`（缺省 4，限制 1..8）分批并发
  fork/exec，批内按原顺序等待与打印，输出顺序与 `--list` 一致；每例独立
  超时与日志。新增 `ytestparallel` 与 `parallel-matches-serial` 断言
  （test-check 32/32）。
- **边界**：不同命令并发执行同一项目仍可能覆盖日志（命令级运行目录未隔离）；
  测试构建仍不启用模块/函数级缓存（YT2d-2）。

## 2026-10-23 0.0.9-rc.2 发布与发布版二进制验收

- **发布**：Gitea `release.yml` run 57 五个作业全部 success，创建
  prerelease `0.0.9-rc.2` 并上传三端资产；`ci.yml` 的 `0.0.9-rc` 分支门同轮
  通过。
- **CI 迭代**：① 首轮 tag 因 GitHub 资产 SSL 中断失败（环境网络）；
  ② 次轮暴露 `compiler-tests`/隔离冷编重复注入闭包导致
  `ld.lld: duplicate symbol: yh_lld_link_driver`，改为 `[link]` 清单环境
  （`YH_LINK_MANIFEST_ONLY=1` + `YH_LINK_RUNTIME_FLAGS`）；
  ③ 第三轮构建机磁盘仅剩 2.3 GiB，Darwin 链接与 x86_64 对象原子写入失败，
  清理可再生的缓存与旧产物后重跑成功。
- **验收**：发布种子 `yh 0.0.9`（`7cbf2580…cfb1e837`）装入 `bin/yh-darwin-arm64`
  后，`make`、`make test`、`make selfhost-native` 全绿（语法 81/81、49/49；
  run 211/212；fail 136/136；pass 9/9；test-check 28/28；string 内建 5/5；
  compiler-tests 3/3；TOML 6/6；固定点 30 产物、自解析 114 文件、
  modules 19/19、project cases 121/121）。
- 记录详见[release-0.0.9-rc.2](01-finished/release-0.0.9-rc.2.md)。

## 2026-10-23 linux-x64 发布门 duplicate symbol 修复

- **现象**：Gitea `release.yml` 的 linux-x86_64 job 在 `make selfhost-native`
  的 compiler-tests 处失败：`ld.lld: error: duplicate symbol:
  yh_lld_link_driver`（`lld_bridge.o` 两次出现在同一归档），`通过 0/3`。
- **根因**：compiler/ 已迁移 `[link]` 清单闭包（F1），但
  `tools/compiler-tests.py` 仍按旧链路设置 `YH_LLVM_SELFHOST=1` 与
  `YH_LLVM_SELFHOST_FLAGS`；ELF 驱动在清单之外把整份运行时闭包（含
  `--whole-archive` 桥归档）再追加一次，同一条链接命令里桥归档出现两次。
  `tests/selfhost/llvm-isolation.py` 冷编段同样停留在旧链路。
- **修复**：两处改为清单模式环境（`YH_LINK_MANIFEST_ONLY=1` +
  `YH_LINK_RUNTIME_FLAGS` 指向构建机 runtime 配方），不再注入旧闭包；与
  `tools/seed-build.py`、`tests/selfhost/native-selfhost.py` 的既有约定一致。
- **复现与验证**：amd64 容器（`yh-ci:ubuntu24-amd64`）+ 0.0.9-rc.1 x64 种子，
  旧环境复现上述重复符号；清单模式环境同一条构建链接成功；修复后
  `tools/compiler-tests.py` 在容器内 3/3、本机 macOS 3/3 通过，`make` 冷编正常。

## 2026-10-23 0.0.9-rc.2 开发与本地验收

- **内容**：恢复 compiler 内嵌测试与门禁（YT3b）：`gen/buffer.yh`、
  `lex/layout.yh`、`parse/parse_type.yh` 的 test 块，`tools/compiler-tests.py`
  与 `make test-compiler-tests`，并入 `make test` / `make selfhost-native`。
- **修复**（rc.1 验收后暴露）：
  1. 测试构建不读/不写模块 manifest 缓存（复用生产对象会让测试入口找不到
     `__yh_test_*`）；2. 测试构建不装载/不提交函数级 IR 与 check 切片缓存
     （曾出现「表达式 AST 校验失败」）；3. 测试函数只在本轮选中的模块/文件
     登记（依赖模块曾留下无函数体的受检声明，`yh test <模块>` 直接挂）；
     4. 自解析与种子快照跳过 `tmp/`、`.build/`（自解析曾从 114 变 117）。
- **回归**：`tests/modules/test-check.py` 增至 28 项，新增
  `test-after-production-build`。
- **验证**：种子 = 0.0.9-rc.1；`make`、`make test`、`make selfhost-native`
  全绿（语法 81/81、49/49；run 211/212；fail 136/136；pass 9/9；
  test-check 28/28；string 内建 5/5；compiler-tests 3/3；TOML 6/6；
  固定点 30 产物、自解析 114 文件、modules 19/19、project cases 121/121）。
- 发布说明：[release-0.0.9-rc.2](01-finished/release-0.0.9-rc.2.md)。

## 2026-10-23 0.0.9-rc.1 发布与发布版二进制验收

- **发布**：Gitea `release.yml` 的 `publish` 作业成功（run 142），三端资产
  `yh-0.0.9-rc.1-{darwin-arm64,linux-arm64,linux-x86_64}.tar.gz` 已上传。
- **取种**：本机无 GitHub token，`make fetch-seed` 无法直连私有仓库；改用
  host 模式 runner 的同一批产物 `~/yh-release-dist/ci-126`，tar.gz 与其
  `.sha256` 校验一致，解包后装入 `bin/yh-darwin-arm64`
  （种子 sha256 `21da09ed…7b15e1`）。
- **验收**：种子报告 `yh 0.0.9` 且接受 `test` 语法；`make` 冷编通过；
  `make test` 退出码 0（语法 81/81、49/49；run 211/212、fail 136/136、
  pass 9/9；test-check 27/27；string 内建 5/5；TOML 6/6；代码统计 6/6）；
  `make selfhost-native` 退出码 0（30 产物固定点一致、自解析 114 文件、
  modules 19/19、project cases 121/121）。
- **rc.2 解锁**：用该种子冷编含 YT3b test 块的 `llvm` 线通过，
  `compiler-tests: 通过 3/3`，确认滚动自举顺序成立。
- **Linux 冒烟**：linux-arm64 资产在 Ubuntu 24.04 容器内报告 `yh 0.0.9` 并接受
  test 语法；x86_64 资产为模拟环境，未作为原生证据。
- 记录详见[release-0.0.9-rc.1](01-finished/release-0.0.9-rc.1.md)。

## 2026-10-23 0.0.9-rc.1 开发与本地验收

- **版本**：`compiler/project.toml` 升到 `0.0.9`（rc 期写目标正式号），
  发布说明见[release-0.0.9-rc.1](01-finished/release-0.0.9-rc.1.md)。
- **内容**：语言内测试 YT0–YT3a（语法、`yh test` 发现/降低/逐例执行、
  `--filter`/`--timeout`/`--no-run`/`--emit-llvm`、`libs/testing` 的
  `fail`/`skip`、`libs/string/99_tests.yh` 内建测试）、os/sys 跨平台拆分收口、
  libc 模块、fmt/math/memory/插值/性能测试规划文档。
- **自举顺序**：0.0.9-rc.1 由 0.0.8 种子编译，该种子不认识 `test` 语法，
  因此本版 `compiler/` 暂不含 test 块（`tools/compiler-tests.py` 与
  `make test-compiler-tests` 同步暂缓）；compiler 内嵌测试随 rc.2 恢复，
  届时 revert “rc.1 暂缓 compiler 内嵌测试”提交即可。
- **验证**：`make test` 与 `make selfhost-native` 全绿（语法 81/81、49/49；
  run 211/212；fail 136/136；pass 9/9；test-check 27/27；string 内建 5/5；
  固定点 30 产物一致、自解析 114 文件、modules 19/19、project cases 121/121）。
- **本地预检限制**：用本机备份的上一代种子冷编会在 Darwin 链接阶段因
  lld/libc++ 解析错配失败，且同一闭包下 **0.0.8 源码本身也失败**，说明是本机
  闭包缓存与旧种子不匹配，不是本版源码回归；实际冷编以 tag 流水线为准。
- **未提交**：`compiler/.codegraph/`（本地工具数据库）保持未跟踪，未入提交。

## 2026-10-23 yh test 编译器内嵌测试（YT3b，0.0.9-rc.2 交付）

> 0.0.9-rc.1 由 0.0.8 一代种子编译（不认识 test 语法），当时暂缓了本项；
> rc.1 发布出的种子已具备 test 语法，rc.2 恢复内嵌测试与门禁。

- **滚种子**：在两大主门全绿后执行 `make seed`，把本代 `yh` 写入
  `bin/yh-darwin-arm64`（按规则不入库），使 `compiler/` 可以写 test 块。
- **实现**：`gen/buffer.yh`（`hexval`、`is_assign_op`）、`lex/layout.yh`
  （`lex_can_end`）、`parse/parse_type.yh`（`is_member_name`、`is_type_start`）
  新增内建 test 块，可直接测试同模块私有函数；新增
  `tools/compiler-tests.py`（复用 `tools/llvm-*-host.py shim` 准备
  `PATH`/`YH_CC`/`YH_LLVM_SELFHOST_FLAGS`/`SDKROOT`）与
  `make test-compiler-tests`，并接入 `make test` 与 `make selfhost-native`。
  完整记录见[YT3b 实施记录](01-finished/yh-test编译器内嵌测试-2026-10-23.md)。
- **验证**：`compiler-tests: 通过 3/3`（gen 2、lex 3、parse 3 例）；
  `make test` 与 `make selfhost-native` 全绿（固定点、cc4 自解析 114 个源文件、
  project cases 121/121）；生产对象与 `.s.i` 中 `__yh_test_` 符号数为 0。
- **边界**：种子滚动仅在本机构建环境完成；YT2d（并行/日志/缓存键）与
  YT1.1（项目外单文件）仍未实施。

## 2026-10-23 yh test 标准库内建测试与门禁（YT3a）

- **实现**：新增 `libs/string/99_tests.yh`（5 条内建测试：视图比较、前后缀与
  查找、无分配切分、拥有者增长、UTF-8 校验）；新增 `make test-lib-tests`
  （`cd libs && yh test string`），并接入 `make test` 与 `make selfhost-native`。
  完整记录见[YT3a 实施记录](01-finished/yh-test标准库内建测试-2026-10-23.md)。
- **修复缺陷**：① 非目标项目的 test 声明此前也登记测试函数，导致
  「函数声明 AST 缺少函数体根」——改为按文件所属项目判断
  （`p_test_decl_active` / `ast_decl_test_active`）；② 源码根内的 `tmp/`、
  `.build/` 被当源码扫描，导致第二次 `yh test` 报「顶层符号重定义」——
  新增 `pj_scan_skip_dir` 跳过构建产物目录。
- **验证**：`make test-lib-tests` 连续两次 `5 passed; 0 skipped; 0 failed`；
  `make test` 与 `make selfhost-native` 全绿（固定点、cc4 自解析 114 个源文件、
  project cases 121/121）。
- **边界**：`compiler/` 仍不含 test 块——入库种子不认识 test 语法，
  YT3b 需先 `make seed`；本轮未滚种子。

## 2026-10-23 memory 标准库设计交付（第二版，参考 Zig）

- **交付**：[memory 标准库设计](03-design/yh-memory标准库设计-2026-10-23.md)与
  [实施方案](02-plan/yh-memory标准库实施方案-2026-10-23.md)；同步
  [标准库设计](03-design/yh-标准库设计.md)的 `memory` 节与
  [todo](todo.md) 的 MEM M0–M6。
- **参考**：核对 Zig `std.mem.Allocator` 的 vtable（`alloc`/`resize`/`remap`/
  `free`，`error.OutOfMemory`，free 带长度/对齐，remap 可返回 null 让调用方
  复制）与 `std.heap` 的 Arena/FixedBuffer/Page/MemoryPool/Debug/ThreadSafe/
  StackFallback 实现。
- **设计**：保留 `alloc`/`release`/`copy`；新增 `reallocate`、`FixedBuffer`
  （LIFO resize/free）、增强 Arena（1.5 倍几何增长、`reset(free_all/retain)`、
  LIFO 回收、capacity）与基于 Arena + 空闲链的 FixedPool；统一 `Allocator`
  （函数指针 vtable）列为 M5 可选，Debug/ThreadSafe/Page/StackFallback 后置。
  块统一取自 prelude 堆，不新增 `sys` 依赖，不改 `string`/`toml`/编译器，
  不替代 `libc` 的 C ABI 分配器。
- **核验**：核对 `libs/memory`、prelude、LLVM 运行时（Linux/Darwin 的
  malloc/free 布局、16 字节对齐与零长度行为）、`sys` 内存原语、
  `string`/`toml` 现有分配与 `libs/cli` 的函数指针字段先例；新文档相对链接
  检查通过。
- **状态**：M0–M6 均未实施；本轮只改文档，未构建、未运行门禁、未滚种子。

## 2026-10-23 yh test 执行增强（YT2c）

- **实现**：`yh test --filter` 作用于执行（过滤后零用例报错）；新增
  `--timeout <秒>`（1..3600，缺省 15，`WNOHANG` 轮询 + 单调时钟 + kill 回收）；
  记录扩展为 72 字节（`magic + line + col + 60 字节消息`），失败输出
  「断言位置」与「断言消息」；新增 `libs/testing` 的 `fail/skip`，汇总改为
  `结果: N passed; M skipped; K failed`。完整记录见
  [YT2c 实施记录](01-finished/yh-test执行增强-2026-10-23.md)。
- **语料**：新增 `tests/modules/projects/ytestskip`（fail/skip/断言消息）与
  `ytesttimeout`（死循环 + 超时后继续）；`tests/modules/test-check.py` 增至
  27 条断言。
- **验证**：`ytestskip` 输出 `2 passed; 1 skipped; 2 failed`（含两条断言消息），
  `ytesttimeout --timeout 1` 报「用例超时」并继续执行后续用例；
  `make test` 与 `make selfhost-native` 全绿（固定点一致、cc4 自解析
  114 个源文件、project cases 121/121）。
- **边界**：并行执行、逐例日志文件、测试缓存键隔离与超长消息提示属 YT2d；
  平台自动跳过未提供；未滚种子。

## 2026-10-23 yh test 执行器与结果协议（YT2b）

- **实现**：每个含测试的模块生成入口模块 `yh_test_<mod>`
  （`tmp/yh-test/gen/<mod>/entry.yh`），按 `argv[1]` 首字节选择用例并在测试体
  正常返回后向 fd 3 写 `YHTP`；编译器运行时发射 `__yh_test_assert` 弱定义，
  断言失败时写 `YHTF + line + col` 并 `exit(1)`。父进程逐例 fork/exec，
  只有「退出码 0 且记录 YHTP」判 PASS；提前 `exit(0)`、崩溃、记录缺失一律
  FAIL 且继续后续用例，输出「断言位置: 行:列」与
  `结果: N passed; M failed`。完整记录见
  [YT2b 实施记录](01-finished/yh-test执行器与结果协议-2026-10-23.md)。
- **语料**：新增 `tests/modules/projects/ytestfail`（通过/断言失败/提前退出/
  崩溃/失败后继续），`tests/modules/test-check.py` 增至 23 条断言。
- **验证**：`ytest` 8/8 PASS（rc 0）；`ytestfail` `2 passed; 3 failed`（rc 1，
  含 `断言位置: 12:5`）；`make test` 与 `make selfhost-native` 全绿
  （固定点一致、cc4 自解析 114 个源文件、project cases 121/121）。
- **边界**：执行过滤、`--timeout`、`testing.fail/skip`、断言消息正文、日志文件
  与测试缓存键隔离属 YT2c；未滚种子。

## 2026-10-23 yh test 测试体降低与运行期断言（YT2a）

- **实现**：测试模式下 pass1 为每条 test 登记模块内 `pub` 无参 `void` 函数
  `__yh_test_<file>_<decl>`（符号写回 `PDecl.test_sym`），pass2 用正常函数
  上下文解析并捕获测试体；`$assert(cond[, msg])` 降为
  `__yh_test_assert(cond, line, col, msg)` 运行期调用，条件不再要求编译期
  常量。`TK_TEST` 声明进入 AstDecl/AstFunctionContext/CheckedModule，
  `--no-run` 走完整 CheckedModule→SSA→LLVM→对象发布（不链接），新增
  `--emit-llvm` 审阅。生产构建不登记测试符号、不发射测试体。完整记录见
  [YT2a 实施记录](01-finished/yh-test降低与运行期断言-2026-10-23.md)。
- **语料**：`tests/modules/test-check.py` 增至 19 条断言，新增
  `emit-llvm`、`test-bodies-lowered`（对象含 `__yh_test_*`、LLVM 文本含
  `call void @"__yh_test_assert"`）与 `production-has-no-test-symbols`。
- **验证**：`make test` 通过（语法 81/81、49/49；run 211/212；test-check 19/19；
  TOML 6/6），`make selfhost-native` 通过（固定点一致、cc4 自解析 114 个源文件、
  project cases 121/121）。
- **边界**：`__yh_test_assert` 尚无运行时定义，测试二进制不能链接；测试入口、
  逐例进程、结果协议、`fail`/`skip`、超时与汇总属 YT2b，`yh test` 仍不执行测试。

## 2026-10-23 string 标准库首期实施（ST0–ST6）

- **实现**：`libs/string/` 新增 `00_model.yh`、`10_view.yh`、`20_owned.yh`、
  `30_transform.yh`、`40_utf8.yh`、`doc.yh` 与 README；旧
  `length`/`equals`/`compare` 保留在 `string.yh`，原空 `String` 占位移除。
  交付按字节 `View`、可增长 `String`、查询/切分/替换、ASCII 大小写与严格
  UTF-8；所有权、失效规则、失败原子性、自别名、最大长度与 C 边界按设计落地。
- **测试**：新增 7 个 `tests/modules/projects/string*` fixture、
  `tests/string/run.py`（含 10 场景 × 8 档分配失败注入）、
  `tests/string/reference.py`（固定种子 92 例 Python bytes/str 差分）与
  `tests/string/README.md`；`build-check.py` 登记 6 个基本组。
- **门禁**：新增 `make test-string`（O0）、`make test-string-o2`、
  `make test-string-install` 与 `make test-string-complexity`；Gitea
  Darwin/arm64 与 Linux/AArch64 分支门调用 `make test-string` 与安装门。
- **验证**：`make`、`make test-string`、`make test-string-o2`、
  `make test-string-install`、`make test-string-complexity`、`make test`、
  `make selfhost-native` 全部通过；`make test` 运行 211/212（1 个平台跳过）、
  test-check 16/16、TOML API 6/6；`selfhost-native` project cases 121/121
  （新增 6 例）。完整记录见
  [string 首期实施](01-finished/yh-string标准库首期实施-2026-10-23.md)。
- **边界**：未迁移编译器/CLI/TOML 私有实现；Unicode 大小写/折叠、规范化、
  字素、正则、格式化、优化搜索等后置；未改语法、未滚种子、未推送。

## 2026-10-23 yh test 发现与无运行检查（YT1）实施

- **实现**：新增 `compiler/cmd/test_cmd.yh` 与 `yh test`；`--list` 发现稳定身份
  并绑定文档目标，`--no-run`/默认命令在临时函数上下文检查测试体语义（不执行）。
  跨文件/前向/私有函数、常量、全局变量与类型目标可绑定；同文件同种类重名、
  无效目标与导入模块名被拒绝。测试专用导入按 token 区间分类，生产构建跳过其
  绑定、依赖边、接口加载与未使用诊断。完整记录见
  [YT1 实施记录](01-finished/yh-test发现与无运行检查-2026-10-23.md)。
- **语料**：新增 `tests/modules/test-check.py` 与 `ytest`/`ytestbad`/`ytestdup`/
  `ytestsem`/`ytestempty` fixture，16 个断言；覆盖模块/文件选择、跨文件私有
  目标、平台文件、零用例、测试专用导入不污染生产、测试体错误只在测试模式报错。
- **验证**：`make test` 通过（语法 81/81、49/49；运行 211/212；test-check 16/16），
  `make selfhost-native` 通过（固定点一致、cc4 自解析 114 个源文件、
  project cases 121/121）。
- **边界**：尚无执行器、运行时 `$assert` 失败定位、逐例进程与超时；`--filter`
  只过滤 `--list`；项目外单文件（YT1.1）未实现；未滚种子。

## 2026-10-23 yh test 语法基线（YT0）实施

- **实现**：`docs/yh.g4` 增加 `testDecl`/`testName`，`memberName` 放开 `test`；
  编译器新增 `TK_TEST`、保留字识别、成员名放行、顶层声明索引与
  `parse_test_decl`。生产 `build`/`run`/`check`/`--syntax-check` 只检查
  测试体语法，跳过语义与代码发射；`pub test`、属性前缀、匿名/缺块/空名称
  被拒绝。完整记录见[YT0 实施记录](01-finished/yh-test语法基线-2026-10-23.md)。
- **语料**：`03-decl/12_test_decl.yh`、`pass/09-test-decl.yh`、
  `run/206-test-decl-production-skip.yh`，以及 `rejected/47..51`、
  `fail/165..167`；`tests/yh/README.md` 计数更新为正例 81、反例 49、规则 82。
- **验证**：`make`、`make quick`、`make test`、`make selfhost-native` 全部通过；
  自举固定点一致、cc4 自解析 113 个源文件、project cases 115/115。另用临时
  test 声明项目验证 `yh build`/`yh check` 的索引路径。
- **边界**：`yh test`、测试发现/文档目标绑定、运行时 `$assert`、`testing`
  辅助接口、重复名称与测试体语义检查均未实现；未滚种子。YT1–YT3 继续开放。

## 2026-10-23 TOML 标准库 reader 实施（T0–T5）

- **实现**：新增普通 `toml` 模块并登记 `libs/project.toml`；`Document` 独占
  私有池，`Value` 为只读句柄，`Text` 用字节指针+长度。覆盖完整 TOML 1.1 语法：
  四种字符串（含 `\e`/`\xHH`）、点键/引号键、隐式/显式表、1.1 多行内联表、
  数组表、混合数组、四种日期时间与省略秒、i64 与精确 binary64。
- **浮点**：私有 640-limb 大整数实现十进制→binary64 正确舍入；1437 个随机/
  边界值与 400 个相邻 double 中点（含次正规数、精确十进制展开）和 Python
  `float` 位模式一致；30 个有限上溢样本全部报 `error_float_range`。
- **测试**：新增 `tomlmodel`/`tomlstrings`/`tomlscalars`/`tomltables`/
  `tomlerrors`/`tomlfiles` 六组 `.yh` 项目与 `tests/toml/run.py`；新增官方
  tagged JSON 桥 `tomltestdecoder` 与 `tests/toml/conformance.py`，固定
  toml-test v2.2.0 的 `files-toml-1.1.0` 清单通过 **681/681**（有效 214、
  非法 467，零跳过）。
- **门禁**：`make test`（含新增 API 组）与 `make selfhost-native` 本平台通过；
  新增 `make test-toml`/`make test-toml-conformance` 与
  `tests/toml/run.py --conformance` 入口。语料首次用
  `conformance.py --prepare` 下载并核对 SHA-256，常规运行不静默联网。
  Gitea `ci.yml` 的 Darwin 原生与 Linux/AArch64 容器门已加入 API 组和一致性门；
  本轮未触发 CI 实跑，CI 证据待首次推送。
- **验证**：`python3 tests/toml/run.py --quiet --conformance` 输出 API 6/6、
  一致性 681/681；`make test-toml`、`make test-toml-conformance` 退出 0；
  `make test` 与 `make selfhost-native` 退出 0（后者 project cases 115/115）。
  浮点另做 1437 例随机/边界、400 例相邻 double 中点、3000 例随机 double
  格式化往返差分，全部与 Python 位模式一致。
- **T4.1/T5.1 收口**：`tests/toml/injection.py` 在临时标准库副本注入运行时
  失败接缝，`tomlinject` 逐次允许 0..N 次池分配，覆盖 **124 个失败点**，
  每点均验证资源错误、无半成品文档和重复解析；`tomlbudget` 把副本
  `TOML_MAX_BYTES` 降到 2048，验证累计预算 `error_resource_limit`。
  `tests/toml/install.py` 执行 `make install` 并在仓库外、无 `YH_STDLIB`
  时用默认 `../share/yh/libs` 运行 `tomloutside`。新增
  `make test-toml-injection`/`make test-toml-install`，Gitea CI 同步接入。
- **文档**：设计/分期/ADR/标准库总览/todo/README 同步实施状态；
  `libs/toml/README.md` 记录 API、所有权、错误、预算和未实现项。
- **未完成**：编译器清单消费者迁移（T6）；writer 与保真编辑（T7）；
  三端 Release 资产是否携带标准库（T5.2，现状只含 `yh`，标准库由
  `make install` 分发）。`compiler/cmd/toml.yh` 未改动，本轮未滚种子、
  未触发发布。

## 2026-10-23 string 标准库规划交付

- 用户确认实用完整基础库：只读视图、可增长 String、查找/切分/替换与 UTF-8
  基础操作。交付[设计提案](03-design/yh-string标准库设计-2026-10-23.md)和
  [ST0–ST6 分期](02-plan/yh-string标准库实施方案-2026-10-23.md)，接口仍待评审。
- 建议按字节存储、显式 clone/move/release、无分配 split 和严格 UTF-8；明确
  NUL/C 转换、失败原子性、自别名、视图失效与空模式语义，保留旧三函数。
- 完整 Unicode、格式化、正则、更多编辑操作与编译器迁移后置。todo 登记实施
  阶段，均未实施；[交付报告](01-finished/yh-string标准库规划交付-2026-10-23.md)
  记录证据边界。
- 本轮仅编辑文档，检查新增链接、围栏和本轮空白差异；未执行构建/运行门禁，
  不据此宣称 string 新功能已经实现或验收。保留工作区其他未提交改动。

## 2026-10-23 yh test 语言内测试方案交付

- 补 yh/Zig 同例输出对照：临时样例在 `tmp/yh-test-comparison-2026-10-23/`，
  Zig 0.16.0 实测文档测试通过、故意断言失败、后续通过，汇总 2/0/1、退出码 1；
  yh 明确仅为拟议输出，未运行。结果录入执行模型分析，不视为 yh 门禁证据。
- 补[语法块执行模型分析](03-design/yh-test语法块执行模型-2026-10-23.md)：test
  登记为私有函数，统一经受检快照/SSA/LLVM 编译；明确断言不能沿现有前端
  立即诊断路径消费、生成入口与原 main 链接身份、全部构建后逐例 exec、
  return/exit 区别及结果协议；仅文档分析，尚未实现或运行验证。
- 断言方案根据用户反馈改为统一 `$assert`，移除新增 assert 与必需 expect
  接口的建议；test 内运行时检查与现有普通/编译期函数行为分开约定，明确
  helper 不继承调用者上下文、常量不改变检查时机及断言行定位。仅更新设计。
- 根据用户补充，将 `test 声明名 { ... }` 文档测试纳入首版方案；与字符串
  行为测试并存，明确目标绑定、前向/私有/跨文件声明、种类身份与验收反例。
  同步实施分期和 YT0/YT1；本次同样仅修改文档，未实现语法或运行构建门禁。
- 交付[设计提案](03-design/yh-test语言内测试设计-2026-10-23.md)与
  [分阶段方案](02-plan/yh-test分阶段实施方案-2026-10-23.md)，尚待评审。
- 推荐顶层具名 test、同模块私有访问、testing 最小 API 与逐例进程运行；
  明确测试专用导入、发现范围、失败/跳过/超时、生产缓存隔离和旧种子迁移边界。
- `docs/todo.md` 登记 YT0–YT3，均未实施；现有外部语料与自举主门继续保留。
- 本轮仅编辑文档，未修改语法文件、编译器或测试源码，未运行构建/回归，
  不据此声称 test 功能或拟议语法已经验收。

## 2026-10-23 TOML 标准库规划交付

- **范围确认**：用户选择完整 TOML 1.1 解析为首期目标，写入后置；本轮仅交付规划。
- **交付**：[设计](03-design/yh-TOML标准库设计-2026-10-23.md)、
  [T0–T7 分期](02-plan/yh-TOML标准库实施方案-2026-10-23.md)、
  [提议 ADR-0017](adr/0017-yh-TOML标准库独立文档模型.md)与
  [交付记录](01-finished/yh-TOML标准库规划交付-2026-10-23.md)；同步标准库总设计和 todo。
- **主要建议**：独立 Document/只读 Value、字节长度文本、显式查询错误，先以固定
  toml-test 完成 reader，再单独迁移编译器清单；schema 仍由编译器负责。
- **验证**：已核对源码和官方规范，新增 TOML 文档与索引段落的链接/围栏/空白检查通过。
  没有修改 compiler/libs/tests 实现或种子，未运行构建或功能门；T0–T7 均未实施。

## 2026-10-23 编译器性能测试方案交付

- **交付**：[性能方案](02-plan/yh-编译器性能测试方案-2026-10-23.md)，同步 todo 的
  PF0–PF4；本轮只完成方案，实施与性能实测均未开始。
- **方案**：复用现有 Python 工具，保留 R0 历史语料，新增当前 LLVM 冻结负载；
  首期做无改动、单函数修改、清构建缓存的 A/B 各 20 轮，再补阶段归因、失效矩阵、
  内存、规模与产物运行基准，平台分别建基线。
- **核验**：已读现有性能工具、统计/调度实现与历史记录，核对脚本 `--help`；
  新方案本地链接、PF0–PF4 索引、表格/空白检查及相关文档 diff 空白检查通过。
  本轮仅增补文档，未运行构建、功能全门或性能采样；未得出性能改善或达标结论。

## 2026-10-22 cli argparse 差分收尾（CLIDIFF1–7）

- **实现**：自定义 `usage`（空串抑制）与 `%(prog)s/%(dest)s/%(default)s/%(type)s/%%`
  模板（未知占位符 freeze 报 config_error）；`Argument.version_text` 版本模板；
  每层解析前预置默认值，使 count/append/extend 基于默认值或 initial 累计；
  选项 remainder 吞掉 `-x`、`--help` 与 `--`；新增 `Result.warnings`，
  deprecated 参数/命令显式使用时生成警告，`render` 写 error_fd，
  `parse_main_or_exit` 成功路径输出并清空。
- **测试**：`cliactions` 新增 count/append 基值与选项 remainder 主题；
  `clihelp` 新增 usage/模板/version/坏模板/警告主题；新增 `cliwarnings`
  入口用例；新增 `clidiff` 探针与 `libs/cli/test/diff.py`（94 条 argv，
  91 条一致、3 条设计保留差异、0 条未知差异）。
- **验证**：`python3 libs/cli/test/run.py` 10/10；`python3 libs/cli/test/diff.py`
  未知差异 0。仅改标准库与文档，未跑 `make` 门。
- **文档**：`docs/03-design/yh-cli与argparse差异.md` 补 4 条差异；
  `libs/cli/README.md` 与设计文档同步实现状态；`docs/todo.md` 清空 CLIDIFF。

## 2026-10-22 cli 标准库与 Python argparse 差分复查

- **方法**：`tmp/cli-diff/` 下新增探针项目 `clidiff`（同一 parser 声明打印
  status、各 dest 规范化值与未消费 token）与 `diff.py`（95 条 argv 同时喂给
  yh 与 Python 3.14 argparse）。既有 `python3 libs/cli/test/run.py` 9/9 通过。
- **结果**：89/95 一致。两处是已文档化差异（`--unknown --help` 的优先级、
  known 模式 `-vz` 整 token 保留），两处是真实缺口：count 显式默认被忽略
  （`--tries` 默认 3、出现一次得 1，argparse 为 4，违背设计 §8“基于初始值
  累计”）、选项 remainder 遇到 `-x` 提前结束（设计 §9.3 要求吞掉选项样式
  token）。
- **代码审计另发现**：`ParserConfig.usage` 存入后从未读取（自定义 usage 与
  空串抑制都不生效）、§14.1 的 `%(prog)s` 模板未展开、version 无文本模板字段、
  warnings 通道未实现（README 已披露）、无公开列表值构造函数。
- **去向**：已登记 `docs/todo.md` CLIDIFF1–7；本轮未改库代码，未跑 `make` 门。

## 2026-10-22 自举链接闭包只强制桥整库加载

- **起因**：Darwin 自举链接把 `[link-options-darwin-arm64].whole` 写成桥/lld/llvm/
  support 四组全量 `-force_load`，每个归档再加一个 `-force_load`，72 个归档的全部
  成员都被塞进 `yh`（73,740,160 字节）；归档本身按 `llvm-config --link-static
  --libs` 的组件闭包给出，无法再靠删文件压缩。
- **改动**：`tools/link-closure.py` 的 `whole` 统一为 `["bridge"]`（Linux 原本如此），
  `check` 同步；重生成 `compiler/project.toml`，Darwin 只强制桥，LLVM/lld 归档交回
  符号引用按需取成员。
- **实测**：`yh` 70,645,536 字节（−3,094,624 B，−4.2%），链接参数少 72 个
  `-force_load`；`nm` 符号闭包显示 72 个归档里 71 个真被引用，只有
  `libLLVMExtensions.a` 无引用，故收益来自「少加载成员」而不是「少列文件」。
- **Linux 事实**：`tools/llvm-sdk.py` 用 `glob("libLLVM*.a")` 把 226 个组件全放进
  一个 `--start-group`（桥仍只整库加载，故不胀产物）。`llvm-nm` 闭包显示 58 个
  组件（BOLT*/`*Disassembler`/Exegesis*/FileCheck/Fuzzer*/Orc*/MCJIT/ObjCopy 等）
  完全无引用，可删；但只省链接扫描时间，且要连 `sdk.lock.json` 与 Linux 门一起验，
  本轮不动。
- **验证**：`make`、`make test`（run 210/211、fail 133/133、pass 8/8）、
  `make selfhost-native`（退出码 0，项目段 115/115）全绿；
  `link-closure.py check` 三个宿主 PASS。`otool -L yh` 仍只有 libc++/libSystem。

## 2026-10-22 LLVM 架构分阶段实施方案交付

- 交付[计划方案](02-plan/yh-LLVM架构分阶段实施方案-2026-10-22.md)与
  [交付记录](01-finished/yh-LLVM架构实施方案交付-2026-10-22.md)：第一包 LA0–LA2
  覆盖入口基线、发射/check 收口、lowering 拆分及函数接缝；后续 LA3–LA5 接 J1/J2/J4。
- 明确文件、内部接口、所有权、`.yh` 回归与验收；修订方向包含缓存 ID 重绑定、
  来源刷新和 LLVM 文件对象分区，完整 check 缓存及线程池不提前宣称完成。
- todo 已登记首批未完成事项。本次只交付文档，没有修改编译器/测试/种子/闭包，
  未执行构建、自举、运行或性能门，也未提交已有工作区改动。

## 2026-10-22 LLVM 分支架构复核

- 基于 `llvm` / `895140a`，区分 HEAD 的 9 模块与含 builtin 迁移的 10 模块工作区；
  静态统计 102 个 `.yh`、46,078 物理行，显式 import 无环。
- 交付[完整复核](03-design/yh-LLVM分支架构复核-2026-10-22.md)与
  [交付记录](01-finished/yh-LLVM分支架构复核-2026-10-22.md)：LLVM 接管通用优化和
  机器后端，Nanopass 建议定位为语义/阶段契约；重点是重复驱动、lowering 职责、
  函数缓存重绑定与上下文隔离。更新 todo 的复核入口和 LLVM 增量路径事实。
- 本轮仅静态分析和文档检查，没有修改编译器、测试、种子或闭包，没有执行构建/
  自举/性能门，也未把建议标为实施完成。保留已有 builtin 迁移工作区改动。

## 2026-10-22 内置函数迁入 builtin 模块

- **结构**：新增 `compiler/builtin/`（`module builtin`，只 `import gen`），
  把 `sem_register_prelude` 与 `prelude_add_linux_syscall6` 从
  `gen/symbols.yh` 迁出；`gen` 只保留符号表原语 `gen.prelude_add`（改为 `pub`）。
  入口（`cmd/driver.yh`、`cmd/llvm_emit.yh`、`cmd/module_worker.yh`）改为
  `import builtin` 后调用 `builtin.sem_register_prelude()`，调用顺序不变。
  prelude 名字、签名、登记顺序与 `F_*` 标志均未改；运行时函数体仍在
  `backend/llvm_runtime.yh` / `backend/llvm_apple_runtime.yh`，本次不动后端。
- **测试**：新增 `tests/yh-run/run/205-builtin-prelude-registration.yh`
  （printf/malloc/memcpy/strlen/free）；`llvmlower` fixture 补
  `import core.builtin`，`tests/modules/build-check.py` 拷贝清单加 `builtin`。
- **验证**：`make test`（run 210/211、fail 133/133、pass 8/8）与
  `make selfhost-native`（固定点 30 产物、自解析 102 源文件、run 351/352、
  模块 19/19、项目 115/115）全绿。记录见
  [完成报告](01-finished/yh-内置函数迁入builtin模块-2026-10-22.md)。

## 2026-10-22 修复文档乱码并静音编辑器 Unicode 提示

- **问题**：`docs/01-finished/yh-linkMach-O出口与编译器汇编步替换-2026-10-04.md`
  第 129 行的「注」+ 3 个 U+FFFD + 「说明」，是一个 3 字节汉字（「释」）被逐字节
  替换成 3 个替换字符；同时编辑器对中文全角标点报「模棱两可 / 易混淆 Unicode
  字符」（未信任工作区下 `nonBasicASCII` 会把中文正文也算进来）。
- **实现**：该行复原为 `注释说明`；新增 `.vscode/settings.json`，关闭
  `editor.unicodeHighlight.ambiguousCharacters` 与
  `editor.unicodeHighlight.nonBasicASCII`——中文标点是本仓库正文的正常排版；
  `invisibleCharacters`（零宽、NBSP）保持默认开启。
- **范围与验证**：不改中文标点正文。全仓扫描确认无 BOM、无残留 U+FFFD，
  `.yh`/`.py`/`.sh`/`.yml` 的代码位置（去掉注释与字符串后）无全角字符，
  因此没有隐藏的语法错误；`git diff` 只涉及 1 行文档、1 行记录和 1 个新配置。

## 2026-10-22 换行终结语句（0.0.8-rc）

- **语法**：`\n` 参与语句边界，简单语句、模块头、类型别名、字段与枚举成员可以
  省略行尾分号；同一行仍用 `;` 分隔；严格续行要求括号外运算符放在上一行末尾；
  裸 `return` 行尾结束。设计见
  [03-design/yh-换行终结语句设计.md](03-design/yh-换行终结语句设计.md)。
- **实现**：`compiler/lex/layout.yh` 归一化补零长度 `TK_SEMI`；解析器用
  `p_implicit_semi`/`p_take_block_end` 区分隐式与显式终结符；参考语法用
  `tokens { IMPLICIT }` + `stmtEnd`，语料门禁按同一规则归一化。
- **验证**：`make test` 全绿（正例 80/80、反例 44/44，run 209/210、fail 133/133、
  pass 8/8）；`make selfhost-native` 全绿（cc3→cc4 27 个产物一致、自解析 101
  个源文件、modules 19/19、project cases 121/121）。
- 记录：[01-finished/yh-换行终结语句-2026-10-22.md](01-finished/yh-换行终结语句-2026-10-22.md)。
  未滚种子、未发版、未批量删分号（方案 Phase 1/2）。

## 2026-10-22 CI 迁到 Gitea Actions（Jenkins 退役）

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

## 2026-10-22 分号删除（compiler/，0.0.8-rc）

- **范围**：`compiler/` 101 个 `.yh`，删除 24,514 个可省略行尾分号，保留 1,061 个
  同行分隔/裸块前分号，行数不变。
- **工具适配**：`selfhost_snapshot_gate.py`、`tests/selfhost/link-cache.py` 的
  module 声明正则改为分号可选；`compiler-performance.py` 的模块名提取同步。
- **验证**：`make` 冷编成功，`compiler/.build` 与删除前对比**非 manifest 差异 0**；
  `make test` 全绿；`make selfhost-native` 全绿（27 个产物固定点、自解析 101 文件、
  modules 19/19、project cases 121/121）。
- 记录：[01-finished/yh-分号删除-2026-10-22.md](01-finished/yh-分号删除-2026-10-22.md)。
  未清 `libs/`/`tests/`/`examples/`，未滚种子。

## 2026-10-22 0.0.8-rc.7 发布与种子换代

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

## 2026-10-22 全仓去分号收尾

- **范围**：`libs/`、`examples/`、`tests/` 非反例语料 503 个文件删除 11,698 个
  分号；`compiler/` 此前已删 24,514 个。反例（`rejected/`、`reject/`）、冻结
  语料（`tests/perf/`）、按精确源码字节改写的项目 fixture、显式分号正例保留。
- **验证**：`make test` 全绿（80/80、44/44、run 209/210、fail 133/133）；
  `make selfhost-native` 全绿（27 产物固定点、自解析 101、modules 19/19、
  project 115/115）。
- 记录：[01-finished/yh-分号删除-2026-10-22.md](01-finished/yh-分号删除-2026-10-22.md)。

## 2026-10-22 YH_LLVM_CACHE 自动定位

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

## 2026-10-22 LLVM 架构 LA0–LA2

- **LA0**：新增 `tests/selfhost/llvm-architecture.py` 与
  `tests/modules/projects/llvmarchitecture/`，冻结入口/check/lowering/失败发布/
  O0-O2 外部行为；基线在 `tmp/llvm-architecture/baseline/`，已接入
  `selfhost-native`。oracle 自检（入口改返 41 必须失败）通过。
- **LA1a**：新增 `cmd/llvm_pipeline.yh`，单文件与项目 worker 共用
  prepare/文本/桥/临时文件/machine 校验/rename 发布；重构前后 fixture `.ll`
  逐字节一致。
- **LA1b**：新增 `llvm_check_single_file`，单文件 check/编译共用受检前端；
  `sem_check_main_optional` 允许库文件无 main、但校验已有的 main 签名；
  删除失去消费者的 `cmd/compile.yh`。
- **LA2a/LA2b**：`module_snapshot_lower.yh` 按完整函数边界拆为
  expr/call/flow/place/aggregate 五片；`lower_module` 分离
  prepare/declare/build/release。新增互递归、嵌套同名绑定与中间函数失败 fixture。
- **验证**：`make test` 全绿；`make selfhost-native` 全绿（固定点、自解析、
  run 210/211、fail 133/133、project 115/115）；`check-command.py` 与
  `llvm-architecture.py --case all/--self-test` 通过。未执行 `make seed`。
- **缺陷**：含 goto 的函数里函数指针绑定生成 `alloca void`，已登记
  `docs/todo.md` D1，未在本轮修复。
- 记录：[01-finished/yh-LLVM架构LA0-LA2-2026-10-22.md](01-finished/yh-LLVM架构LA0-LA2-2026-10-22.md)。

## 2026-10-22 LLVM 架构 LA3（函数级 IR 复用，交付 1–2）

- **缓存单元**：新增 `ir/ssa_module_40_function_cache.yh`，把单函数及类型/符号/
  全局/来源贡献闭包打包为迷你 `IRModule`；`ir/ssa_module_50_function_rebind.yh`
  负责按结构/名字/内容重绑定并装配。
- **键与接入**：`ast/module_snapshot_lower_cache.yh` 生成函数键（token 流 +
  布局/签名 + 非函数声明事实）；`cmd/function_ir_cache.yh` 管目录/索引/环境键/
  原子提交；`lower_module_cached` 在 LA2b 函数接缝查/写缓存。
- **统计**：`--stats` 新增 `ir_lowered`，区分 `ir_functions`（命中+未命中）、
  `ir_cache_hits`、`ir_cache_misses` 与实际 lowering。
- **验证**：新增 `llvmfunctioncache` 项目与 `tests/selfhost/llvm-function-cache.py`，
  覆盖冷编 0/4、注释 4/0、单函数 3/1、插入 4/1、损坏单记录重建、接口 0/5；
  O0/O2 命中构建对象与 LLVM 文本和冷编逐字节一致。`make test` 与
  `make selfhost-native` 全绿（固定点、自解析、运行 351/352、项目 115/115）。
- **未完成**：LA3.3 函数级 check 复用未启动；J1/RS2 完整目标仍开放；未执行
  `make seed`。
- 记录：[01-finished/yh-LLVM架构LA3-2026-10-22.md](01-finished/yh-LLVM架构LA3-2026-10-22.md)。

## 2026-10-22 LA3.3 函数受检事实缓存设计

- **范围**：只交付独立设计，不实现跳过函数 check、不改构建行为。
- **设计**：新增
  [docs/03-design/yh-函数受检事实缓存设计-2026-10-22.md](03-design/yh-函数受检事实缓存设计-2026-10-22.md)；
  定义函数级受检 AST 切片、局部 ID 重绑定、token 下标来源、与 IR 缓存共享的
  键、保守安全子集、损坏/失败协议、统计字段与 C0–C4 实施门。
- **结论**：LA3.3 不是简单跳过 `parse_block`，必须先有切片往返与 arena
  重绑定证据；J1/RS2 完整目标继续开放，当前仍每次执行完整前端检查。

## 2026-10-22 LA3.3 C2 受检 AST 切片离线往返

- **实现**：新增 `compiler/ast/module_snapshot_check_slice.yh`，把单函数的
  expr/stmt/edge/binding 行按局部 ID 序列化；清空 AST arena 后导入、重建
  `CheckedModule` 并再次 lowering，比较模块身份与冷编一致。
- **边界**：只用于离线探针，不接入生产 skip；含 `$for` 模板的函数返回跳过。
- **验证**：llvmlower 新增 `checkcache.yh` 与模式 `2`，覆盖标量/字符串/全局/
  切片/聚合/goto；`make test` 与 `make selfhost-native` 全绿（project 115/115）。
- **未完成**：C1 独立测量、C3 生产跳过；J1/RS2 完整目标仍开放。

## 2026-10-22 LA3.3 C3 check 缓存草稿与阻塞

- **实现（默认关闭）**：新增 `ast/module_snapshot_check_key.yh`、check 缓存
  `.fchk` 查询/导入、`index.check` 装载/提交与 `check_cache_*` 统计；
  `module_worker` 当前设 `check_cache_on=0`，parser 跳过路径保持惰性。
- **实测**：启用后 `ct5b-transitive-body-invalidates-importer` 失败——早期接口
  调度可让消费者在依赖 session `.s.ct` 稳定前开始全局 CT 求值，复用旧结果。
  禁用早期接口调度后该用例恢复，确认阻塞在依赖 CT 接口发布/消费顺序。
- **决定**：C3 代码保留但默认关闭；J1/RS2 完整目标仍开放。启用前需修
  依赖 CT 接口时序并重跑注释/单函数/损坏矩阵（设计 §11）。
- **验证**：默认关闭状态下 `make test` 与 `make selfhost-native` 全绿
  （固定点、自解析、运行 351/352、project 115/115，LA3 IR 矩阵通过）。

## 2026-10-22 LA3.3 C3 启用（方案 A）

- **接口时序**：新增 session ready 标记；父调度器只认 ready，消费者只读同一
  session 的 `.s.i/.s.ct`；依赖早期启动前比较 session/plain CT 哈希，CT 变化
  或首次出现 CT 时等待完整提交，无 CT 时允许提前推进。
- **函数键**：源码级 `const` 的 `cval/flags/const_ready` 进入 check/IR 函数键，
  依赖 CT 变化导致的折叠值变化直接失效导入方函数。
- **内存**：单函数切片 >1 MiB 跳过；单模块装载/捕获总预算 16 MiB。
- **启用**：check 缓存正常装载/提交，`check_cache_*` 统计为真实值。
- **验证**：`llvm-function-cache.py` O0/O2 check 矩阵通过；`ct5b-transitive-
  body-invalidates-importer` 通过；`make test` 与 `make selfhost-native` 全绿
  （固定点、自解析、运行 351/352、project 115/115）。未执行 `make seed`。

## 2026-10-22 LA4/LA5 专项设计门

- **LA4 设计**：新增
  [文件对象与提交清单设计](03-design/yh-LLVM文件对象与提交清单设计-2026-10-22.md)，
  定义按文件所有权分区、hidden 跨对象私有身份、文件对象键/manifest、失效矩阵
  与 LA4.1–4.4 切片；默认单模块对象构建不变。
- **LA5 设计**：新增
  [显式上下文与线程池设计](03-design/yh-LLVM显式上下文与线程池设计-2026-10-22.md)，
  定义 FrontendTask/AstStore/CtContext/CacheContext/Diagnostics 边界、线程桥与
  线程池顺序、串行/2/4 worker 一致性验收。
- **状态**：设计门完成，LA4/LA5 代码实现未启动；继续 fork/COW 与单模块对象，
  不宣称文件对象或线程安全完成。

# 2026-10-24 NET0：sys 网络原语与 HTTP 标准库设计定稿

- **设计**：新增 [HTTP 标准库设计](03-design/yh-http标准库设计-2026-10-24.md)
  与 [ADR-0018](adr/0018-yh网络与HTTP标准库分层.md)。核查确认仓库此前无任何
  HTTP 实现、`libs/sys` 无 socket 原语、`libs/os` 明确不承诺网络，故按
  「sys socket → net → http」三级推进。用户确认六项：首期含服务端、TLS 走可选
  `libs/tls`（系统 OpenSSL）、DNS 纯 yh、并发后置、服务端 `Date` 先补 `time`、
  补 ADR-0018。libcurl 评估结论：能链（`[c].libs`/`[c].sources` 已实现）但不
  采用——`curl_easy_setopt` 是 C 变参、数据面靠回调、依赖形态不可控。
- **NET0 实现**：`libs/sys/00_types.yh` 增 `PollFd`（8 字节）与 `Timeval`
  （16 字节）；三份平台常量文件增 `AF_*`/`SOCK_*`/`IPPROTO_*`/`SOL_SOCKET`/
  `SO_*`/`POLL*`/`SHUT_*`/`MSG_NOSIGNAL`/网络 errno（Linux 另加 socket 族
  `NR_*` 与 `F_GETFL`/`F_SETFL`）；新增 `70_socket.linux.yh`（raw6）与
  `70_socket.darwin.yh`（libSystem 桥），共 12 个原语，Linux 另加 `fcntl_fd`。
- **探针实测**（Darwin/arm64，`tmp/probe/`，不入库）：结构体数组字面量、函数
  指针字段、结构体切片、`Io` 经 `*Io` 调用、单进程环回 socket 闭环、
  `ECONNREFUSED=61`、`poll` 超时/就绪语义全部可用。发现并写入设计的约束：
  `len` 是保留字、无 `while` 语句、Darwin 无 fcntl 通道（非阻塞 connect 只在
  Linux 可用）、本机出站连接被环境代理接受（connect 超时无法本地验证）。
- **验证**：新增 `tests/modules/projects/netsys/` 并登记
  `net0-sys-socket-loopback`（结构布局、收发、poll、半关闭 EOF、errno 归一化）；
  `make test` 八个阶段全过（ANTLR、编译器语法 356/357 含 1 跳过、modules
  test-check、string 5/5、compiler-tests 3/3、stats；toml 阶段因会话批量删除
  守卫拦截旧工作目录清理而退出非零，换新目录复跑 6/6 通过）。
  `make selfhost-native` 本轮未跑完：其清理步骤要删 `compiler/.build` 的
  2600+ 文件被同一守卫拦住，改用手工两代构建时第二代链接缺自举闭包参数
  （`-lc++`/SDKROOT 由构建机提供）。两项都是本机环境问题，且 libs 改动不参与
  编译器固定点。未滚种子、未改语法、未改编译器。

# 2026-10-24 NET1：net 模块（地址 + TCP）

- **实现**：新增 `libs/net/`：`00_model.yh`（Family/Status/Endpoint/TcpStream/
  TcpListener 与结果结构）、`05_error.yh`（errno → os.Error，含把套接字超时的
  EAGAIN 改写为 `error_timed_out`）、`10_address.yh`（IPv4/IPv6 解析与 RFC 5952
  压缩格式化，纯函数）、`20_tcp.{linux,darwin}.yh`（dial/listen/accept/
  read_some/write_some/write_all/shutdown_write/close_stream/close_listener/
  listener_local）、`99_tests.yh`、`doc.yh`、`README.md`；`libs/project.toml`
  注册 `net`，Makefile 的 `test`/`test-lib-tests`/`selfhost-native` 增加
  `yh test net`。
- **os 扩展**：`ErrorKind` 末尾追加 7 个网络成员（既有取值不变），
  `error_kind_for` 增加对应映射，新增公开 `os.error_from_errno`。
- **平台差异**：Darwin 用阻塞 connect（`fcntl` 是 C 变参，yh 无法声明）+
  `SO_NOSIGPIPE`；Linux 用 `fcntl(O_NONBLOCK)` + poll + `SO_ERROR` +
  `MSG_NOSIGNAL`，connect 超时生效。
- **命名修正**：`read`/`write` 与编译器 prelude 重名（实测报「顶层符号重定义」），
  改名为 `read_some`/`write_some`，与 os 对齐；设计 §5.2 同步。
- **验收**：`yh test net` 4/4（IPv4、IPv6 压缩、非法输入、容量不足）；
  新增 `tests/modules/projects/netecho/` 并登记 `net1-net-tcp-loopback`
  （端口 0 回读、accept 超时、双向收发、半关闭 EOF、连接被拒、IPv6 `::1`
  环回），在 build-check 中 OK。`make test` 各阶段：ANTLR/语法语料 356/357
  （含 1 跳过）、modules test-check、string 5/5、net 4/4、compiler-tests 3/3
  全过；toml 阶段受会话批量删除守卫影响，用 `--keep` 复跑 6/6；代码统计脚本
  因同环境 mkdir 被拒未运行。未滚种子、未改语法、未改编译器。
