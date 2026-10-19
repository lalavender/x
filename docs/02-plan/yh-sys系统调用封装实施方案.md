# yh sys 系统调用封装实施方案

日期：2026-10-03。状态：**仅交付规划，SYS0–SYS7 尚未实施**。

2026-10-19 修订：用户选择标准库可用性优先，交付排期改由
[os/sys 联合方案](yh-os与sys标准库实施方案.md)安排。SYS 编号保留为底层能力
清单，按应用场景取最小子集，不再等待 SYS5/SYS6 才提供新 os 接口。
平台包含现有 Linux/x64 LLVM 入口与 Linux/arm64 路径；旧自研工具链关联不再
作为库能力前置，编译器迁移按 ADR-0014 单列依赖审计。

> 后续实施使用 `superpowers:executing-plans`，按本方案逐项开发、验证和记录。
> 本次授权为规划及 sys 标准库落点，不代表已经实施任何系统调用封装。

**Goal：** 在 `libs/sys/` 用 yh 实现 Linux/x64、Linux/arm64 直接系统调用层，支撑普通程序及
编译器脱离外部用户态运行时；随后增加 Darwin OS 接口适配。

**Architecture：** 复用已有 linux_syscall6，raw6 与类型化函数均返回原始结果或
-errno，错误判定不使用全局 errno。sys 不分配、不重试；os 新接口提供应用级结果，
os/io/time 旧接口保留原有契约。

**Tech Stack：** `.yh`、Linux LP64 的 x64/ARM64 ABI、现有项目模块/平台文件、内核 UAPI。
Python、系统汇编/链接工具与容器仅可作为开发验证设备，不能进入产品启动路径。

设计和 API 以[设计文档](../03-design/yh-sys系统调用封装设计.md)为准。

## 1. 实施顺序与退出标准

| 阶段 | 可见结果 | 退出标准 |
| --- | --- | --- |
| SYS0 | 真实依赖清单、ABI/环境基线、测试入口 | 每个活跃 OS 引用均有归属和替换策略 |
| SYS1 | 模块、错误/类型、raw6 | 模块发现、错误边界、原始返回和 intrinsic 路径正确 |
| SYS2 | 文件/目录原语 | 文件往返、删除/重命名、错误与目录记录真实运行 |
| SYS3 | 内存/时间原语 | 六参数 mmap、结构布局、睡眠和错误真实运行 |
| SYS4 | 当前 worker 所需进程原语 | fork 双返回、wait、exec 环境、退出/dup 行为正确 |
| SYS5 | 上层库与编译器消费者迁移 | 旧 API 回归、显式依赖、宿主/目标隔离通过 |
| SYS6 | 独立产物与 Linux 自举 | 静态检查、独立环境运行、两代固定点及全门通过 |
| SYS7 | macOS/arm64 OS 桥 | 逐项 ABI/错误归一、Darwin 主门通过并披露系统依赖 |

SYS1–SYS4 不依赖自研链接器，但真实 Linux 运行门不可用语义检查替代。
SYS5/SYS6 是后续编译器阶段，须有对应 Linux 候选编译器；链接与 SDK 依赖按
现行 LLVM/lld 路线审计，不以历史 TC4/TC5/TC6 的全部完成作为 os 可用前置。
SYS7 不阻塞 Linux 直接调用层，也不等同于 Darwin 自有链接器已完成。

## 2. 共用开发与验证规则

每个行为切片按顺序进行：

1. 在下面指定的 tests 项目增加 `.yh` 用例，记录当前缺失或错误的结果。
2. 只实现该切片所需 API；中文注释包含单位、结果、所有权和平台限制。
3. 执行 `make`，再运行该切片针对性检查，确认目标平台的实际行为。
4. 同步设计、模块 README、todo 和完成记录；以完成的能力重新描述阶段状态。
5. 阶段结束运行本平台 `make test`、`make selfhost-native`、适用的专门门与 diff 检查；
   其它平台由 CI 承担，不要求本地预跑。

最终门：

```sh
make
make test
make selfhost-native
python3 tests/selfhost/syscalls.py --compiler-path ./yh
git diff --check
```

`tests/selfhost/syscalls.py` 是本方案拟新增入口，当前不存在，以上命令为后续实施
约定；正常完整运行要求对应 Linux ISA 和匹配的编译器。它把 fixtures 和产物复制
到 `tmp/syscalls/`，逐个执行并检查返回/输出/符号，不在 tests 源目录留下产物。

Darwin 本地不要求预跑 Linux 门；如专项安排交叉语义检查，输出必须明确
“未运行 Linux”，不能据此宣布 Linux 门通过。
临时外部工具/容器单文件探针须检查明确结果，不沿用“两个产物都崩溃也算相同”
作为 syscall 门。完整模块原生验收和独立环境验收仍需另行通过。

用户源码始终 `.yh`，不新增 sys 语法，不修改 docs/yh.g4。发现真实语法需求时，
先另写无歧义设计和语法测试。只删除由本次迁移造成的孤立局部代码。

## 3. SYS0：基线、消费者与 ABI 盘点

**文件：**

- 新增 `tests/selfhost/syscalls.py`（先提供清单/环境/语义检查入口）。
- 新增 `tests/modules/projects/sysresult/{project.toml,src/main.yh}`。
- 读取 compiler/cmd 各平台文件、process/build_scheduler、gen 运行时和 libs。
- 更新本设计的支持矩阵；报告写 `tmp/syscalls/inventory.json`。

**步骤与验收：**

1. 用 rg 和二进制导入/未定义符号盘点，不以 prelude 声明列表代替活跃引用。
   记录内存/文件/目录/进程/时间、宿主和输出目标、现有返回值与所需原语。
2. 固定 Linux v6.12 UAPI 映射事实；记录实际验收内核、页大小、CPU、编译器及
   种子 SHA-256。映射基线不是最低支持内核承诺。
3. 确认文件排序、平台筛选、结构 sizeof/字段偏移、七参数 intrinsic 的函数值和
   SSA/LLVM 调用路径。标记已支持与待验证，不建立新的 libc raw 外部符号。
4. 加 Linux/Darwin HostPlatform × TargetSpec 的检查场景。交叉构建的文件标志
   不能受输出目标改变；如果出现既有阻塞，单独最小修复后再做完整交叉构建。
5. 将每个活跃 OS 引用映射到 sys、已有自有运行时、外部工具兼容路径或后续项目。
   所有“尚未替换”必须显式保留在清单，SYS6 前归零或给出平台允许导入。

验证：清单可重复生成、无缺项；既有 `make` 和主门结果单独记录，不覆盖其它
工作区修改。不滚种子，不把 Linux 候选种子的缺失隐藏成已验证。

## 4. SYS1：模块骨架、结果/类型和 raw6

**文件：**

- 新增 `libs/sys/00_types.yh`、`10_constants.linux.{arm64,x64}.yh`、`20_raw.linux.yh`。
- 新增 `tests/modules/projects/sysraw/{project.toml,src/main.yh}`。
- 扩展 sysresult 和测试入口；按实际测试类型接入 `tests/modules/build-check.py`。
- `libs/project.toml` 已有 sys 预留项；不新增无功能的配置字段或第二份清单。

**步骤与验收：**

1. 先写 sysresult：导入 sys，验证 Timespec 大小 16、两个字段地址差 8；验证
   is_error 的 0、正数、-1、-4095、-4096 与 error_code 的提取/成功归零。
   常量显式写成 i64，避免已知混合宽度语义缺陷影响判定。
2. 旧版本应报 sys 模块/接口缺失；实现类型和结果函数后原生运行退出 0。
3. 写 sysraw：原始 getpid 返回正 PID，原始 write 输出固定字节，坏 fd 保留
   -EBADF，未实现编号在允许的测试环境返回 -ENOSYS。seccomp 策略记入环境。
4. raw6 只转发现有 linux_syscall6，未使用槽明确填零，不生成 syscall(3) 调用。
   编号、标志按目标 ISA 验收；不一次生成 raw0–raw5 或全量 syscall 包装。
5. 验证直接调用与函数值调用均可用；检查旧/SSA/LLVM 后端副作用、参数及返回不丢失。
   比对生成对象：无 libc syscall/errno 引用，真正的运行结果与期望一致。
6. Darwin 上检查 Linux 专属接口不能被误当成 native 实现；新测试类型须明确
   目标限制。sysresult 可两平台运行，sysraw 不允许被静默算作 Darwin 已通过。

示例规格中的分号声明不是实际 yh 实现；本阶段函数须有完整函数体和中文注释。
验证：`make`、sysresult 原生运行、sysraw Linux 运行、模块接口与目标筛选通过。

## 5. SYS2：文件与目录

**文件：**

- 新增 `libs/sys/30_file.linux.yh`。
- 新增 `tests/modules/projects/sysfiles/{project.toml,src/main.yh}`。
- 新增 `tests/modules/projects/sysdirs/{project.toml,src/main.yh}`。
- 扩展 `tests/selfhost/syscalls.py`。

**步骤与验收：**

1. sysfiles 先定义期望：用 O_CREAT|O_EXCL/O_WRONLY 创建相对临时文件，write
   固定字节、close、open_at/read 校验、rename_at 后读取、remove_at 删除。
2. 增加确切错误：不存在路径的 ENOENT、重复创建的 EEXIST、坏 fd 的 EBADF。
   零长度调用仍对有效/无效 fd 验证；sys 不直接把零长度转为成功。
3. 实现 open_at/read_fd/write_fd/close_fd/create_dir_at/remove_at/rename_at。
   mode 为固定 u32 参数，内核入口用机器字；renameat2 的 flags 固定 0。
4. sysdirs 创建含文件/子目录的目录，getdents64 循环到 0。测试消费者校验
   记录长度、名字 NUL 和多批读取，不固定记录顺序。删除空目录用 AT_REMOVEDIR。
5. 补目录解析边界向量与 DT_UNKNOWN 处理；不要把未知类型当成非目录而漏模块。
   需要时使用 O_DIRECTORY 探测，目录遍历/解析仍在消费者层。
6. 验证 sys 不隐式循环短 I/O，不重试 close，不隐藏内核错误；所有资源在成功
   与失败测试收尾释放。测试文件名/目录由 tmp/syscalls/ 每个用例隔离。
7. 按 OS2 补 get_cwd/change_dir，与 os 的字符串长度归一、缓冲不足及 cwd 恢复
   用例一起交付；不为了目录库一次增加完整 stat 布局。

验证：用例在 Linux 退出 0，无残留 fd/子目录；对象无 libc 文件操作引用。

## 6. SYS3：内存映射与时间

**文件：**

- 新增 `libs/sys/40_memory.linux.yh`、`50_time.linux.yh`。
- 新增 `tests/modules/projects/sysmemory/{project.toml,src/main.yh}`。
- 新增 `tests/modules/projects/systime/{project.toml,src/main.yh}`。
- 扩展测试入口的实际页大小/环境记录。

**步骤与验收：**

1. sysmemory 验证匿名映射、跨页写读、解除映射；检查失败返回保留错误后才
   转指针，不使用空指针或任意负数作为 mmap 失败判定。
2. 实现 map_memory/unmap_memory；不在 sys 增加分配头部、free 列表或 allocator。
3. 用文件的非零、实际页对齐偏移做 mmap 往返，内容与偏移匹配，验证六个参数
   的最后一槽；不用只传零的匿名映射代替完整寄存器验收。
4. 无效长度/偏移/标志只选择 ABI 保证的错误场景，校验正确 errno；保留完整
   64 位结果。运行环境页大小从内核传入信息或开发探针获得，不固定 4 KiB。
5. 实现 read_clock/sleep_time。systime 验证单调时钟不倒退、Timespec 输出、
   零时长睡眠、非法 nsec 的 EINVAL，以及坏时钟号的错误。
6. EINTR/remaining 作为专门探针：信号处理由开发参照程序提供并验证原始结果；
   不为了此探针把 sigaction、恢复入口和完整信号运行时加入 sys 首期。测试不能
   把经过 libc 的 -1 返回误当 raw -EINTR。

验证：真实 Linux mmap/clock/sleep 成功与错误均通过；三种页大小支持只能在对应
环境分别验收后声明。默认不把定时误差设置为不稳定的微秒级断言。

## 7. SYS4：进程、执行与退出

**文件：**

- 新增 `libs/sys/60_process.linux.yh`。
- 新增 `tests/modules/projects/sysprocess/{project.toml,src/main.yh}`。
- 新增 `tests/modules/projects/sysexit/{project.toml,src/main.yh}`。
- 扩展测试入口的超时、进程组清理与指定退出码判定。

**步骤与验收：**

1. fork_process 的父/子两条路径写不同结果；子调用 exit_process(7)，父用
   wait_process 接收 PID 和原始状态。反复运行并检查无遗留 worker/僵尸。
2. 实现仅 SIGCHLD、空子栈、无 CLONE_VM 的 raw clone 桥。核对 ARM64 参数
   顺序；不提供新栈/线程版通用 clone API。
3. execute 探针在子进程重新执行测试自身，传指定 argv/envp，子模式检查参数
   与环境后退出。另测缺失路径 ENOENT；避免递归 fork，不依赖 PATH 或 shell。
4. 实现 process_id/wait_process/execute/send_signal；wait4 的 rusage 填空，
   options 与 32 位 status 明确。测试无可等待子进程 ECHILD、WNOHANG 的 0。
5. 实现 duplicate_fd/fd_flags；用重定向后的真实字节验收，并确认同 fd 的
   dup3 返回 EINVAL。旧 dup2 兼容放到消费者阶段，不能在 sys 改写内核语义。
6. exit_thread/exit_process 使用已有 noreturn 属性和不可返回收尾。sysexit
   分别由外部测试器检查指定状态，确认不执行退出后的代码；两者区别按平台
   语义和引用审计验收，不为了区分语义先实现线程库。
7. 按 OS4 增加 create_pipe(output, flags)，使用目标 pipe2/O_CLOEXEC；真实检查
   两个 int 输出和 fd 清理。exec 失败握手在 os 实现，sys 不解释协议或等待子进程。

验证：每个进程都在超时内退出并被收集，父进程资源可重复使用；无 fork/exec/wait/
exit 的 libc 引用。多线程 atfork、pthread/clone 换栈、信号处理另行立项。

## 8. SYS5：标准库和编译器消费者迁移

**文件：**

- 按完整函数边界拆分 `libs/os/os.yh`、`libs/io/io.yh`、`libs/time/time.yh`
  到公共部分和 `.linux.yh/.darwin.yh` 平台部分。
- 修改 `compiler/project.toml`、`compiler/cmd/project_dir.linux.{arm64,x64}.yh`、
  `clock.linux.{arm64,x64}.yh`、`compiler/gen/buffer.yh` 及清单识别的文件/进程/worker 消费者。
- 新增 `tests/modules/projects/syscompat/{project.toml,src/main.yh}`。
- 新增 `tests/modules/projects/sysbinding/` 的显式依赖/遮蔽测试项目。
- 有行为修改则在 tests/modules 或 tests/yh-run 增加对应 `.yh` 回归。

**步骤与验收：**

1. 先冻结现有 os/io/time 返回值、输出和 EINTR 策略；syscompat 对同一内核
   错误分别检查 sys 的 -errno 和旧 os API 的 -1。
   新 os 接口按联合设计另测 Error.kind/native_code，不把旧接口全部改签名。
2. Linux 上替换 os 文件/PID/睡眠/退出调用；time 使用 sys.read_clock 和平台
   CLOCK_MONOTONIC，io 经 os 处理短写且保留已有不重试契约。Darwin 原路径先保留。
3. 核对现有 Linux 测试的平台常量与已具备的 libsbase 平台分支，不能复制 Darwin 数字；
   math 的宿主 C 依赖在审计中单独标记，不凭 sys 迁移宣称完整标准库已独立。
4. 编译器清单显式依赖 yh_libs，消费者用 import yh_libs.sys as sys。测试清空
   YH_STDLIB、指向不同标准库和本地同名 sys，确认编译器的显式绑定不漂移。
5. 一次迁移一个消费者：目录/计时 → 文件/目录创建与原子发布 → fork worker /
   等待/执行/退出。只移除迁移后孤立的结构、局部编号和外部引用。
6. 旧 dup2 的同 fd 路径先通过 sys.fd_flags 验证；sleep_us 由显式微秒转换为
   Timespec；旧 -1 结果不能无检查窄化 raw i64。execvp 的 system 兼容路径保留
   标记，self 路径不执行外部工具。
7. 检查宿主/目标混用，缓存/构建身份应反映源码依赖与运行时提供方变化。不得
   用输出 Linux 常量操作正在 Darwin 运行的编译器宿主文件。
8. 对已迁移项新增功能回归，再做二进制导入清单对比，确认活跃外部 OS 引用
   真实减少；保留 gen 按需运行时的独立审计，不只扫描 libs/sys 源码。
9. 单独核对旧用户 prelude：import sys 不会改写原有 open/read/write 的外部
   调用。sys fixtures 先使用显式导入；旧语料的兼容 OS 桥由 TC6 按实际引用
   发射，保留其原有返回约定并新增 `.yh` 对照，不强行改写无关用户源码。

验证：make、定向项目验收、make test、make selfhost-native 均通过，Linux 门
真实运行；本地只要求本宿主主门，其它平台交 CI。没有对应 Linux 候选编译器
时不得标记该平台阶段完成。

## 9. SYS6：独立产物和自举闭环

**文件：**

- 扩展 `tests/selfhost/syscalls.py` 的产物/进程依赖审计与独立环境测试。
- 对齐现行工具链的启动对象、LLVM/lld/SDK、Linux 种子及固定点门；历史 TC 阶段
  只作为已有成果，不是标准库交付的必经前置。
- 在支持的宿主上把 sys 门接入现有验收入口，不让 Darwin 的跳过替代 Linux 门。
- 完成记录写 docs/01-finished/，更新 todo/finish 和 libs/sys/README。

**步骤与验收：**

1. 对普通 syscall fixtures 检查 PT_INTERP、DT_NEEDED、未解决强引用及 libc/
   syscall/errno 残余依赖；编译器另列嵌入 LLVM/lld/SDK 的实际依赖清单。
   两类产物按各自政策验收，不凭 sys 包装完成宣布编译器已无 libc 依赖。
2. 将产物置于独立 Linux 环境，仅提供实际输入/输出目录和必要设备；没有外部
   编译工具、shell、libc、动态解释器也可运行。开发侧驱动不属于被测进程依赖。
3. 测试 trace 限定被测进程树，允许自身 fork worker，拒绝外部工具 exec。缺少
   trace 设备不能自动降级为“已证明无外部工具”；用等价审计证据或补环境。
4. 验证普通程序文件/目录、内存/时间/进程实际结果，启动 argv/envp/auxv 由
   自有入口提供；确认 exit_process 与语言收尾的调用顺序。
5. yh 连续生成下一代，全部模块 .s/.s.i 固定点、自解析、全量语法/运行语料及
   模块/项目门通过。生产自身不得依赖 make/Python 驱动才能完成单次 yh build。
6. 记录真实 OS/ISA、内核/页大小、源码/种子/产物哈希、导入/进程审计和全门
   结果，区别普通程序独立、编译器独立、平台自举三种能力。

全门通过后才能按仓库规则另执行 make seed；本规划不滚种子，也不新增完整
libc、动态库装载器、GC、异常或线程功能作为闭环前置。

## 10. SYS7：Darwin OS 适配（后续）

**文件：**

- 新增 `libs/sys/10_constants.darwin.yh`、`20_native.darwin.yh` 及逐项实际
  就绪的 `30_file/40_memory/50_time/60_process.darwin.yh`。
- 新增 `tests/modules/projects/sysdarwin/`、对应 Linux/Darwin 契约回归。
- 将 Darwin 上层与编译器消费者逐项迁到审核后的 sys 桥。

**步骤与验收：**

1. 固定部署版本和允许导入的 OS API；核对 __error 的固定参数 C ABI。
2. 对 read/write/close、时钟、映射等先验证成功和失败；失败后立即读取当前
   线程错误号，转为 -errno，不跨调用读取旧错误，不宣称数值与 Linux 相同。
3. 文件创建的 open/openat 变参 mode 必须通过正确 ABI 路径；若现有能力不足，
   明确先补 ABI 及 `.yh` 复现，不能写伪固定参数声明冒充兼容。
4. 目录批量读取用 getattrlistbulk 原生结构，不沿用 getdents64 记录；sys.raw6
   仍是 Linux 专属。按实际支持范围生成接口和文档，不提供假成功函数。
5. 运行本平台原生项目、ABI/错误与 make test/selfhost-native，其它平台回归交 CI；
   披露 dyld/libSystem 的剩余依赖。SDK/外部 codesign 的最终替代仍属于 TC8–TC10。

## 11. 文档交付与变更约束

- docs/todo.md 记录 SYS0–SYS7 实施待办；阶段完成才改勾选。
- 设计记录 API/平台契约，实施方案记录文件/用例/门禁，完成记录只写真实证据。
- libs/sys/README 是标准库入口；docs/03-design/yh-标准库设计.md 区分当前 API
  与规划 API，不把这些具名接口写成已可使用。
- 只增加与 sys 有关的修改；不重构其它模块，不把无关工作区变更纳入本任务。
