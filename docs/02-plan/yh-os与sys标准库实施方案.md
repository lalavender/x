# yh os 与 sys 标准库实施方案

日期：2026-10-19；2026-10-21 更新。状态：**OS0–OS6 已完成（含示例与默认发现）；OS7–OS8 未实施**。用户选择标准库可用性优先；sys 原有 SYS0–SYS7 作为底层
能力编号保留，不再要求全部底层与自举阶段结束后才向应用交付 os。

## 1. 阶段与依赖

| 阶段 | 用户可见结果 | 依赖 / 对应底层阶段 | 关闭条件 | 当前状态 |
| --- | --- | --- | --- | --- |
| OS0 | 结果、选项与 ABI 基线 | SYS0、SYS1 的模型部分 | 跨模块模型及切片真实运行，平台矩阵无虚报 | **完成（2026-10-21）** |
| OS1 | 打开、读写、关闭、创建/删除/重命名 | SYS1 + SYS2 最小文件部分 | Linux 文件闭环、详细错误与旧 API 兼容 | **完成（2026-10-21）** |
| OS2 | 流式目录枚举与当前目录 | SYS2 + get_cwd/change_dir | EOF、缓冲边界、名称生命周期与清理 | **已实现（2026-10-21）** |
| OS3 | 从入口 envp 查询环境 | OS0，可独立于 OS2 | 缺失/空值/完整键/非法键及借用契约 | **已实现（2026-10-21）** |
| OS4 | 精确路径 spawn、wait、exit | SYS4 + create_pipe | exec 失败回传、退出/信号区分、无遗留子进程 | **完成（2026-10-21）** |
| OS5 | io/time 复用底层；映射原语可用 | SYS3、OS1 | CLI 输出兼容，时钟/睡眠/映射原生验收 | **完成（2026-10-21）** |
| OS6 | 标准库加载与示例可重复使用 | OS1–OS5 | 显式加载示例可运行；默认发现独立交付 | **完成（2026-10-21）** |
| OS7 | 编译器逐项迁移、独立性审计 | SYS5/SYS6、现行 LLVM 工具链 | 对应平台二进制依赖清单和自举门真实通过 | 未实施 |
| OS8 | Darwin 新 API 对齐 | SYS7、对应宿主 ABI | 逐项原生验收并披露 libSystem/dyld 依赖 | 未实施 |

推荐实际开工顺序为 OS0→OS1，交付后继续 OS2/OS3，再 OS4。
不使用日历估时掩盖 ABI/工具链不确定性；每阶段单独交付、记录证据。
OS6 的默认发现复用已有 todo，不把安装打包变成 OS1 文件能力前置。

## 2. 目录与改动范围

以下为拟新增/已新增文件；未实施的阶段保持空缺，不先搭空模块。

```text
libs/os/
  os.yh                         现有入口与平台信息，兼容导出保留
  00_model.yh                   Error、结果、OpenOptions、DirEntry（OS0/OS1，已实现）
  10_errors.linux.yh            Linux 错误归一化与切片地址帮助（OS1/OS2，私有）
  file.linux.yh                 新文件接口与必要兼容转换（OS1，已实现）
  20_directory.linux.yh         目录读取器与 cwd（OS2，已实现）
  environment.yh               显式 envp 查询（OS3，已实现）
  process.linux.yh              spawn/wait/exit（OS4，已实现）
  compat.linux.yh               Linux 旧接口（迁移时提取）
  compat.darwin.yh              Darwin 旧接口（迁移时提取）
libs/sys/
  00_types.yh                   结果区间、Timespec（已实现）
  10_constants.linux.x64.yh      x64 编号、标志和 ABI 常量（已实现）
  10_constants.linux.arm64.yh    ARM64 编号、标志和 ABI 常量（已实现）
  20_raw.linux.yh               转发现有 linux_syscall6（已实现）
  30_file.linux.yh              文件与目录原语（OS1 子集已实现）
  40_memory.linux.yh            mmap/munmap（已实现）
  50_time.linux.yh              clock/nanosleep（已实现）
  60_process.linux.yh           进程原语（已实现）
```

所有 `.yh` 文件分别声明 module os/sys，不依赖另一份 project.toml。排序能力先在
OS0 验证，不以文件前缀替代跨文件解析测试。只导出真实被使用的函数/类型，
pub 签名不泄漏模块私有类型；中文注释写清单位、所有权、错误和平台范围。

## 3. OS0：基线与模型（2026-10-21 完成）

1. 盘点 os/io/time/cli 的活跃调用，冻结旧返回值、短写和退出行为；记录已有
   工作区改动，不能把其它任务的结果归入本阶段。
2. 新增 `tests/modules/projects/osmodel/`：跨模块返回 Error/FdResult/IoResult、
   OpenOptions、[]u8 形参与借用缓冲、公开目录模型的候选布局。**已实现并运行通过。**
3. 新增 `sysresult/` 验证 -1/-4095/-4096 边界；Timespec 随 SYS3 交付前验布局。
4. 分别列出 Linux/x64 LLVM、Linux/arm64 现有后端、Darwin 旧接口的当前状态。
   运行测试必须记录实际宿主、后端与目标；导出面缺失不可改成假成功桩。

验证：定向模型项目真实运行、本平台 make；不为库 API 新增语法或后端选择政策。

## 4. OS1：第一份可用文件闭环（2026-10-21 完成）

1. 先增加 `sysraw/`、`sysfiles/`、`osfiles/`、`syseintr/` 的 `.yh` 用例与接线；
   旧接口兼容由现有 `libsbase` 覆盖，暂不单建 `oscompat/`。复用
   `build-check.py` 的标准库运行类型，Linux 专属用例只在 Linux 宿主注册。
2. 已实现 raw6、错误分类所需常量、open_at/read/write/close、mkdirat/unlinkat/
   renameat2；编号与 O_* 每个 ISA 独立核对。sys 不重试、不分配。
3. 已实现 os 新文件 API 与 OpenOptions 转换；旧 open_file 仍接受宿主标志。
   旧接口继续留在 os.yh，未因本阶段迁移。
4. 用例覆盖创建→写入→关闭→打开→读取→EOF→重命名→删除，及 ENOENT/
   EEXIST/EBADF、非法选项、零长度、二进制零字节、追加与截断行为。
5. **已完成**：`syseintr` 使用不带 SA_RESTART 的 SIGALRM 中断阻塞 read，
   并用非阻塞 Unix 流式 socket 稳定产生短写；测试专用 C 驱动只存在于 fixture，
   不向公开 API 添加测试开关。为此提前交付 create_pipe/O_NONBLOCK/EAGAIN。
6. 已核对 fd 路径不重复关闭；新增 API 默认 CLOEXEC，旧 API 的继承语义保留。
   真正 exec 继承验证留给 OS4。

关闭条件：新接口显式错误、旧接口 -1 和现有 libsbase/libsio/CLI 验收均通过。
`syseintr`、libsbase/libsio 与 CLI 9/9 通过；CLI 重验暴露的 LLVM fn→ptr cast
缺口已修复并新增 `llvm-fnptr-null-cast` 语料。OS1 阶段关闭；Linux/x64 原生门
由 CI 承担。

## 5. OS2：目录与 cwd（2026-10-21 已实现）

- 已新增 `sysdirs/`、`osdirs/`（cwd 与目录合并在两个 fixture 中）；sys 增加
  getdents64/get_cwd/change_dir，保留原始返回与 `-errno`。
- 已冻结 open_dir/next_entry/close_dir 的读取器与条目结果：调用方供缓冲，
  DirReader 区分未打开/已打开，next_entry 区分条目/结束/失败，name 为
  `*u8 + name_len` 借用视图，在下一次读取或关闭前有效；close_dir 重复调用幂等。
- 用例覆盖多批目录项（64 字节缓冲）、长名称（100 字节）、小缓冲、空目录、
  跳过点项、坏 fd、ENOTDIR、重复关闭、损坏记录与 DT_UNKNOWN；目录顺序不作断言。
- cwd 用例覆盖成功 NUL/长度归一、空间不足 ERANGE、change_dir 后恢复与缺失路径；
  测试进程隔离，不残留目录或 cwd 修改。编译器未知目录类型策略仍随 OS7 迁移补齐。

关闭条件：目录生命周期与所有错误分支可重复运行，tmp/ 外不留文件产物。
Linux/arm64 已满足；Linux/x64 原生门仍由 CI 承担。

## 6. OS3：环境查询（2026-10-21 已实现）

- 已新增 `osenv/`，由驱动注入 `YH_ENV_TEST=present`，不读取开发者私有环境值。
- 已实现 get_env(envp,name)，测试缺失、空值、前缀不匹配、值内等号、重复键首项、
  非法名字与空指针；实现无分配、返回借用指针。
- 三参数 main 直接接收 envp；argv 解析仍交给 cli，不把环境查询做成 syscall。

关闭条件：合成 envp 与真实进程 envp 两类用例通过；没有全局环境初始化依赖。

## 7. OS4：进程（2026-10-21 完成）

- 已扩展 `sysprocess/` 与 `osprocess/`；exit 由子模式覆盖，未单建 `osexit/`。
- create_pipe 已随 OS1 短写/EINTR 收尾交付；本阶段继续 fork/exec/wait/exit，
  再提供精确路径 spawn。子路径不调用 libc、不分配或格式化；按本阶段限定的
  单线程父进程验收。
- 已验证成功执行、缺失路径、无执行权限文件、明确 envp/argv、正常退出和
  信号退出。exec 失败回到父进程错误；测试不把 fork 成功当 spawn 成功。
- 错误管道测试短帧、EINTR、提前关闭与子进程异常退出；所有端点按父/子分工
  关闭，失败子进程必须回收。测试驱动设置超时并清理整个测试进程树。
- 核对执行后继承：标准 fd 保留，新 open 的普通 fd 不泄漏。新增重定向需求时
  再接 duplicate_fd/fd_flags，不预做 shell、PATH、管线或异步任务对象。

关闭条件：重复运行无 fd/子进程残留，WaitResult 不混淆错误、正常退出与信号。
`sysprocess/osprocess` 已覆盖；Linux/arm64 原生通过，Linux/x64 由 CI 承担。

## 8. OS5/OS6：上层收敛与使用体验

OS5（2026-10-21 完成）：io 经 os.write_once 实现完整写入；新增保留进度的
write_all_result，现有 write_all/print/println 返回值不变。time 拆 Linux/Darwin
平台文件，Linux 走 sys.read_clock；旧 os.sleep_us 拆平台文件并保持旧契约。
sys memory/time 按 SYS3 原生验收；memory 分配器与编译器生成桩未合并。
`sysmemory/`、`systime/`、`osio/` 覆盖映射、时钟与完整写入进度；syseintr 追加
io 进度；libsbase/libsio 与 CLI 9/9 保持兼容。

OS6（2026-10-21 完成）：`examples/os-demo` 覆盖文件复制、目录列举、环境查询
与自身 spawn/wait，使用 YH_STDLIB；`examples/os-demo-explicit` 用 project.toml
依赖 `yh_libs` 与 `import yh_libs.os`。默认发现已实现：YH_STDLIB 优先，未设置
时按可执行文件附近 `<exe_dir>/libs`、`<exe_dir>/../libs`、
`<exe_dir>/../share/yh/libs` 查找；`make install` 安装 libs 到
`share/yh/libs`。显式依赖仍优先于默认层，变量覆盖优先于两者。

关闭条件：现有 CLI 帮助/错误/成功输出与 0/1/2 退出码保持；文档准确列出每个
目标已实现 API，所有示例和临时产物分别位于 examples/ 与 tmp/。示例与默认发现
已在仓库/安装布局验证；Linux/x64 原生门由 CI 承担。

## 9. OS7/OS8：后续边界

OS7 按实际引用逐个迁移编译器目录、时钟、文件、worker；更新 compiler 的显式
依赖与缓存身份，区分运行中编译器宿主和输出目标。现行 LLVM/lld 的链接与 SDK
依赖按 ADR-0014 审计，不把已调整的自研 asm/link 路线重新列为必经前置。
普通 syscall 程序独立与嵌入 LLVM 的编译器依赖分别列证据。
新增/扩展 `sysbinding/`、`syscompat/` 及受影响 worker 的 `.yh` 回归，验证显式
绑定不受 YH_STDLIB 遮蔽，迁移不破坏宿主 I/O 与输出目标隔离。

OS8 保留 Darwin 旧接口，逐项增加 sys 系统 API 桥、即时错误捕获和新 os API。
核对 open 变参 ABI、目录结构及 mmap 失败值；不复用 Linux 编号、不宣称去除
libSystem/dyld。此阶段到对应平台时再安排原生门。
对应新增 `sysdarwin/` 与 os 平台契约 `.yh` 用例，不能仅做源文本对照。

## 10. 共用门禁与记录

每次实现先增加 `.yh` 反例/正例，再 make、定向验收；阶段结束运行本平台：

```sh
make
make test
make selfhost-native
git diff --check
```

Linux/x64 的 LLVM 专门门按仓库本平台规则执行；其他宿主不要求运行拒绝该宿主
的门。完整 Linux 多平台回归由 GitHub Actions 承担；CI 红灯按 todo 立项，
不要求本地提前跑其它平台。SKIP 不计为对应平台已验证。

测试产物统一在 tmp/modcheck/ 与 tmp/os-sys/；复用现有项目验收脚本，确有跨
进程/符号审计需要时再扩展原 SYS 方案的专项入口。没有落地的脚本不能写成当前
可运行命令。各实现阶段同步设计、sys README、todo、finish 与 docs/01-finished/
的实测记录；只有本机 make test 与 make selfhost-native 全绿且安排滚种子时
才执行 make seed。

### 2026-10-21 本轮验收记录

```sh
make                                   # Darwin/arm64 冷编通过
make test                              # 语法/运行/统计全绿
python3 libs/cli/test/run.py --compiler ./yh --quiet   # CLI 9/9
python3 tests/modules/build-check.py --compiler-path ./yh --backend llvm --jobs 4
```

- Darwin/arm64：`os0-sys-result-model`、`os0-os-result-model` 通过。
- Apple Container `debian:trixie`（Linux/arm64，入库种子）：`sysresult`、
  `osmodel`、`sysraw`、`sysfiles`、`osfiles`、`syseintr`、`sysprocess`、`osprocess`、`sysmemory`、`systime`、`osio`、`sysdirs`、`osdirs`、`osenv` 全部退出 0；
  使用宿主注入的 `gcc-13` 兼容符号链接才能链接，属于当地验证设备，不是产品依赖。
- `sysdirs/osdirs` 覆盖 getdents64/get_cwd/change_dir 与 os 读取器：多批读取、
  空目录、长名称、小缓冲、坏 fd、ENOTDIR/ERANGE、DT_UNKNOWN、损坏记录、
  重复关闭与 cwd 恢复；`osenv` 覆盖合成/真实 envp 与非法名字。
- `syseintr` 覆盖 -EINTR、短写与 os 部分进度；`libs/cli/test/run.py` 9/9；
  新增 `tests/yh-run/run/llvm-fnptr-null-cast.yh` 并修复 LLVM fn→ptr cast。
- `sysprocess/osprocess` 覆盖 fork 双返回、exit、信号退出、精确路径 spawn、
  缺失/不可执行路径回传与无僵尸检查。
- `sysmemory/systime/osio` 覆盖匿名映射、时钟/睡眠、完整写入进度与旧契约；
  syseintr 追加 io.write_all_result 的 EAGAIN 进度。
- `examples/os-demo`（YH_STDLIB）与 `examples/os-demo-explicit`（项目依赖）
  在 Linux/arm64 与 Darwin/arm64 分别运行通过。
- 默认发现：`os6-default-stdlib` 已在主工作区 `make selfhost-native` 中通过；
  用例复制最小安装布局（bin/yh + share/yh/libs）并以空 YH_STDLIB 运行。
- `yh -target x86_64-unknown-linux-gnu check` 通过文件与目录用例；本轮
  没有 Linux/x64 原生运行环境，未宣称该平台已运行。
- 0.0.7 主工作区恢复后复验：`make`、`make test`、CLI 9/9、
  `make selfhost-native SKIP_CORPUS=1`（项目用例 115/115，含
  `os6-default-stdlib`）通过；Linux/arm64 容器 15 个 fixture 全部退出 0。
- 完整 `build-check --backend llvm` 的 C 互操作项因本机 SDK 27 TAPI 与 `-lm`
  缺失失败，属于环境问题，不计入本阶段结论。
- 本轮未执行 `make selfhost-native` 全部收尾项与 `make seed`；不修改种子。

