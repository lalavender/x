# todo

只记录**未完成**事项。已完成任务的历史与验证证据见
[finish.md](finish.md) 与 [01-finished/](01-finished/)；方案文档在
[02-plan/](02-plan/)，取舍见 [adr/](adr/)。

## 待办

### yh-asm 与 yh-link（2026-10-02 规划；2026-10-03 起在 link/ 独立项目实施）

平台与架构矩阵（Linux/macOS × arm64/x64）的顺序、门槛与依赖见
[平台与架构矩阵方案](02-plan/yh-link平台与架构矩阵方案.md)。要点：
Linux/arm64 已在推进；macOS/arm64 要写第二个对象写出器（出口增量，解析与
编码全复用，验收用宿主 Xcode 的 `ld64` 不用容器）；**x64 必须先有编译器后端**
（`compiler/backend/` 目前只有 `arm64.yh`），否则 x64 汇编器是没有输入方的死
代码，这一条待用户确认再动。

用户确认 **Linux/AArch64 优先，随后 macOS/arm64**。完整
[设计](03-design/yh-asm与yh-link设计.md)与
[分期实施方案](02-plan/yh-asm与yh-link实施方案.md)细化现有 R4/R5。
2026-10-03 起按用户决定独立立项，工具链在仓库根分**两个独立项目**：

- **`asm/`（yh_asm，汇编器）**：汇编文本 → 可重定位对象（ELF64 `ET_REL` /
  Mach-O `MH_OBJECT`）。TC1–TC3 + TC8 的实现在这里，见
  [asm/README.md](../asm/README.md)。
- **`link/`（yh_link，链接器）**：对象 → 可执行映像（静态 ELF、Mach-O
  装载、签名）。TC4/TC9/TC10 尚未实施，当前只有入口骨架，见
  [link/README.md](../link/README.md)。

两者**互不依赖、互不 import**，只通过标准对象文件交接；验收门分别是
`python3 asm/tests/check.py` 与 `python3 link/tests/check.py`。
2026-10-07 目录整理把原先寄放在 `link/` 里的汇编器实现整体迁到 `asm/`，
按职责归位（记录见
[归位记录](01-finished/yh汇编器与链接器项目归位-2026-10-07.md)）。

- [ ] **TC0**：冻结汇编/操作数/重定位契约，拆分宿主与目标，盘点 Linux OS 导入与模式矩阵
  （asm/ 现以 134 项 llvm-mc oracle 向量充当首版编码契约，inventory 脚本待补）。
- [ ] **指令级负例门**：`asm/` 自检只有编码层负例（逻辑立即数不可编码值），
  没有指令级负例。上一代 asm 项目的 19 条负例（越界立即数/偏移、SP 与 ZR
  混用、未知助记符、未定义局部标签、`.balign 非 2 的幂` 等）没有随实现迁移，
  归档在 `tmp/removed-2026-10-07/asm-legacy/`；其中浮点类负例在现实现已支持
  浮点后不再适用，其余应按现状重写进 `asm/src/asm/70_selftest.yh` 或 `asm/tests/`。
- [ ] **编译器汇编步查找名切换**：`compiler/cmd/link_cache.yh` 的 `mb_asm_tool`
  仍按 `yh_link`（及 `YH_LINK`）查找、并按 `asm` 子命令调用；实现早已是
  `asm/` 项目。切到 `yh_asm`/`YH_ASM` 后删掉 Makefile 的 `yh-link` 过渡别名
  目标，并跑 `make selfhost-native` 复验。
- [ ] **TC3 容器链接门剩余：yh 运行时外部符号桩**：容器差分门里 7 个语料因
  `__Exit`/`_strtoul`/`_open`/`_close`/`_abs` 在 `tests/elf/yhr.s` 没有桩而跳过
  （两边同样链不上，按差分语义跳过），另有 2 个语料因 `_mmap` 桩不全段错误
  （参照对象同样崩）；补桩后这两类都会变成真正的运行比对。
- [ ] **TC4**：普通对象到静态 ELF，符号/布局/重定位、自有入口与长调用跳板。
  验收可用容器做差分：同一组对象分别用自有链接器与 GNU `ld` 链，比对行为。
- [ ] **TC5**：单文件/项目内部调用、yh-asm/yh-link 入口、缓存身份与事务发布。
- [ ] **TC6**：Linux 宿主 OS 桥、原生种子、独立环境与连续自编固定点。
- [ ] **TC7**：有限 C 对象、普通 ar 读写/惰性提取与 libc 静态库交付；不阻挡显式对象闭环。
- [ ] **TC9**：Mach-O 可执行文件链接器——分段布局、符号解析、`LC_MAIN` 入口、
  `LC_LOAD_DYLIB` + 普通绑定流（不用 stub 与惰性绑定）。这是替换编译器**最终
  链接步**（`driver.yh` 的 `clang -o`）的必经之路。
  [设计](03-design/yh-link Mach-O可执行文件链接器设计.md)
- [ ] **TC10**：ad-hoc 代码签名（`LC_CODE_SIGNATURE` + SuperBlob +
  CodeDirectory，SHA-256 页哈希）。arm64 macOS 拒绝未签名的可执行文件，硬要求。
  SHA-256 曾实现于旧 link 项目的 `src/ln/10_sha256.yh`（6 个向量对着
  `shasum -a 256` 核过），但当时无生产调用点；2026-10-07 目录整理随该模块删除，
  归档在 `tmp/removed-2026-10-07/link-src-ln/`，动工时按需取回或重建。
  签名布局已从 `ld` 产物逐字段实测进设计文档 §5。
  TC9 骨架先把签名做掉才能验证（dyld 见未签名直接杀进程），绑定流随后接。
- [ ] **TC11**：`driver.yh` 最终链接步切成 `yh_link link`，`make install` 一并
  安装 `yh_link`，主门验证自举。chained fixups 可选迁移（dyld 仍支持绑定流）。

### 编译器已知缺陷（待修复）

以下缺陷均已最小复现，现在的 `asm/`（汇编器）与 `link/`（链接器）都按同一
约定规避；修复时应先补 `tests/yh-run` 或 `tests/modules` 用例。
（上一代 asm 项目的复现与规避记录归档在 `tmp/removed-2026-10-07/asm-legacy/`。）

- [ ] **解引用目标整体结构体赋值结果错误**（原描述为「崩溃」）：`*dst = *src;`（赋值两侧都是
  指针解引用、类型为结构体）。**2026-10-07 复测：不再段错误，改为静默算错**
  —— `fn copy(dst *P, src *P) int { *dst = *src; return dst.x; }` 配 `P{ x: 1, y: 2 }` 复制进
  `P{ x: 0, y: 0 }` 后 `copy(&b, &a) - 1` 得到 **230**（应为 0），编译与链接都成功。
  编译期路径暂时走不到同一处：`@[comptime]` 不支持 `*P`（结构体指针）形参，报「comptime 函数形参
  只支持整数、浮点、当前帧标量指针、标量叶定长数组、受支持结构体/联合体、标量元素切片或受支持
  结构体元素切片」。`compiler/comptime/ct_ir_place.yh` 的 `ct_ir_index_read` 仍用逐字段复制规避；
  修后端前先把它变成正式用例（当前是错值，不能直接当 run 用例）。
- [ ] **嵌套数组字面量运行期初始化错值**（2026-10-09 实测；原「目标类型上下文判定没处理
  嵌套层」的编译期限制已放开）：`let a [2][3]int = [[1, 2, 3], [4, 5, 6]];` 与 return/实参
  位置的嵌套数组字面量现已能编译，但**普通函数运行期初始化读出垃圾值**（探针 `a[0][0]` 应为
  1，实际为非预期值；扁平 `[7, 8, 9]` 正常、元素级写入 `mat[1][1] = 5` 也正常），疑似内层
  字面量被降级为切片临时值、外层只拷贝了描述符（推测，未查证）。修复步骤：先补
  `tests/yh-run` 用例锁定错值，再查数组字面量初始化发射路径。
- **`pub const` 的整数字面量按 32 位有符号折叠**：`0xfeedfacf` 折成
  `-17958193`，赋给 `u32` 报「字面量超出目标类型可表示范围」；
  `0x80000000` 折成一个空的负号直接失败。函数体里的字面量不受影响
  （`let x u64 = 0x80000000;` 正常）。`asm/` 侧已用
  `mo_magic()` / `mo_attr_pure_instructions()` 两个函数绕过并注明。
  影响面：任何需要 64 位常量的编译期求值路径。
- **上一代种子编译器编不了汇编器项目**：`bin/yh` 在含 `e`/`E` 的十六进制
  字面量（如 `0x0e`、`0x0E`）上命中浮点指数解析，报「浮点与整数之间需要
  .to_type 显式转换」。`asm/` 用到新语言特性本来也只能由 `$(YH)` 冷编，
  `make yh-asm` 已显式依赖 `$(YH)`，故未单独修。
- **SSA 混合宽度算术**：项目（模块）模式下 64 位值（i64/u64）与 int
  字面量混合 `+ - *`、移位量为 int 变量时触发「内部错误：SSA 函数校验失败」；
  单文件模式正常。复现：跨模块 `pub fn g2(v u64) u64 { return v + 1; }`。
  规避：64 位运算的常量显式 `.to_type(i64/u64)`，移位量用字面量或 64 位变量。
- **结构体指针加法缩放错误**：`ptr + 变量` 对结构体指针按 8 字节缩放而非
  `sizeof(结构体)`（`arr[下标]` 正确）。复现：`struct T{int a; int b; int c;
  i64 d; int e; int f;}` 的 `arr + idx`（sizeof=32，实际偏移 8×idx）。
  规避：结构体元素访问一律用 `[下标]`；`*u8 + 变量`（字节缩放）不受影响。
- **局部数组变量下标取址错位**：`&局部数组[变量]` 取址同样按 8 字节缩放，
  写入串位。规避：先写临时变量再整体拷贝（`arr[i] = tmp;`）。
- **跨模块结构体字段类型不计导入使用**：`m *obj.ObjModel` 字段引用不标记
  导入已使用，触发「导入未使用」误报。规避：该文件需有其他限定名引用。
- **嵌套三元表达式发射重复标签**：种子编译器对嵌套 `?:`（如
  `a ? b : (c ? d : e)`）发射的汇编含重复 `.L<n>` 定义，clang 拒绝
  （yh_asm 构建中实测，改写为 if/else 规避）。
- **与寄存器同名的局部变量发射不可汇编的引用**：变量名如 `w12` 在
  `bl w12` 槽位被 clang 拒绝（`adrp` 槽位 clang 可接受）——编译器发射
  用户符号未考虑与寄存器名冲突；tests/yh-run 的 14-many-args 与
  37-many-args-noprintf 受影响（yh_asm 按槽位语义放宽可汇编）。
- [ ] **别名类型与同长度字面量数组仍非同一 type_id**（2026-10-07 类型别名长度
  冲突修复的遗留）：延迟布局为长度表达式建立的数组类型项与 `gen.ty_array` 的
  规范项 type_id 不同而内容全同，`sem_can_assign` 现对 `TY_ARRAY` 按元素类型与
  长度做结构化兼容判定放行（结构体/联合体仍按名义类型严格比较）；根治需在布局期
  规范化 type_id。

### Linux 平台缺口（2026-10-09 在 WSL 重建 Linux 种子后首次实测发现）

仓库的语法/运行/模块/自举门此前只在 macOS 上跑过；本次用重建的
Linux/aarch64 种子在 WSL 上跑出一批**既有**缺口（与 HEAD 基线一致，
非本次改动引入）。重建链最终种子已入库为 `bin/yh-linux-arm64`
（2026-10-09）。**2026-10-11：build-check 7 项缺口全部修复**（宿主
open 旗标按宿主平台取值、窄整型返回宽度归一、模块链接 -lm、
clock_gettime 公共登记、libsbase fixture 平台化、CRLF 规范化），
`make test` / `make selfhost-native`（含 build-check **84/84**、
runtime-memory/lex-stats/scratch-isolation）在 WSL 全绿。重建与验证
路径见 [WSL 种子链记录](01-finished/yh-WSL重建Linux-aarch64自举种子-2026-10-09.md)。

- [ ] **yh_link 的 ELF64 方言要求 `sym@PAGE`，编译器 GNU 方言发 `:lo12:sym`**：
  模块汇编步一旦命中 `yh_link`（`argv0` 同目录或 PATH 上），绝对寻址的
  `adrp xN, sym` 就报「adrp 需要 sym@PAGE，adr 需要符号或数字」（编译器
  的 GNU 方言按 `adrp xN, sym` + `add xN, xN, :lo12:sym` 发射，GNU as 两者
  都接受，yc_link 的 ELF64 模式不受 `:lo12:`）。macOS 上 yh_link 走 `-t
  darwin` 方言与发射一致，Linux 上从未让 yh_link 参战，故未暴露。
  绕过：`YH_LINK=/nonexistent` 强制回落 gcc（WSL 全套门禁即按此通过）。
  修法二选一：编译器 GNU 方言也发 `@PAGE/@PAGEOFF`（GNU as 接受），或
  yh_link 的 ELF64 模式接受 `:lo12:` 与裸符号。
- [ ] **本机 ANTLR 参考语法门需要 Java + antlr4 工具 jar**：`tests/yh/check.py`
  默认模式在无 `~/.m2/.../antlr4-*-complete.jar` 时报「找不到本地 ANTLR jar
  缓存」；jar 需从 Maven Central 下载（antlr4-tools 的自动下载走 GitHub
  Release，本机不可达）。已手工放 jar 后 76/76 + 45/45 通过（含 CT6 语法语料）。
  WSL 侧已配置：apt `antlr4`（4.9.2）+ `libantlr4-runtime-java` +
  `libantlr3-runtime-java` + `python3-antlr4`（4.9 runtime）+ `/usr/local/bin/antlr4`
  兼容 wrapper（吞掉 `-v` 并加载全部依赖 jar），本机 `make test` 第 1 层通过。

### Linux/AArch64 libc（2026-10-02，候选方案未实施）

目标已确认：独立链接、兼容 C ABI；[分析报告](01-finished/yh-libc可行性与阻塞点分析-2026-10-02.md)
与[分阶段候选方案](02-plan/yh-libc分阶段候选方案.md)已交付。
以下记录后续建议，不表示已经授权实施全部 libc。

- [ ] **L0**：库对象/归档出口、CRT/静态链接配置、
  运行时提供方与 Linux 种子/原生门。
- [ ] **L1–L2**：静态核心子集、配套 C 头文件，再补 C 裸变参、
  专用 C 数据符号与基本 stdio。
- [ ] **L3–L4**：TP/atomic/上下文原语、TLS/线程/信号，binary128/fenv
  与其余标准接口；按接口清单逐项验收。
- [ ] **L5**：Linux PIC、共享对象、动态 TLS 与自有 ELF 装载器，单独验收。

### 标准库

- [ ] **SYS0–SYS6：`libs/sys` 系统调用封装**：Linux/arm64 先实现直接 syscall、
  `-errno` 结果、文件/目录、内存/时间和进程原语，再迁移上层库与编译器消费者、
  验收静态 ELF 和连续自编；**SYS7** 后续增加 Darwin OS 接口适配。
  本轮仅交付规划，API/文件与门禁见
  [设计](03-design/yh-sys系统调用封装设计.md)、
  [实施方案](02-plan/yh-sys系统调用封装实施方案.md)与
  [模块入口](../libs/sys/README.md)。
- [ ] 为 `libs/` 增加工具链默认发现与安装打包布局，保留 `YH_STDLIB` 覆盖；
  当前仍需手动指定 `YH_STDLIB` 才能导入运行。
- [ ] 后续按实际 API 需求扩展；当前不承诺跨平台 ABI，不把 libc 裸变参
  `printf` 接入 FFI，也不引入隐式内存分配。

### Nanopass 风格优化架构（2026-10-02，方案待评审）

用户选择“优化扩展与自举稳定”为本方案首要目标；沿用 ADR-0009 的增量速度约束。
完整[架构设计](03-design/yh-Nanopass风格优化架构.md)、
[分期实施方案](02-plan/yh-Nanopass风格优化架构实施方案.md)与
[ADR-0011 草案](adr/0011-yh采用Nanopass风格优化阶段契约.md)已交付，尚未实施。

- [ ] **NP0**：锁定优化语义、覆盖统计与同编译器优化开关对照，建立可重复基线。
- [ ] **NP1**：复用现有 SSA，拆分 `ir_simplify`、建立固定 pass 顺序及函数私有分析索引；先保持输出行为。
- [ ] **NP2**：逐项接入低成本 SSA 优化、完整引用重写与 CFG 清理，默认管线通过运行与固定点门。
- [ ] **NP3**：受检函数/Core 阶段契约与 lowering 解耦；逐切片补齐自编覆盖，消除成功 SSA 函数的旧汇编预发射。
- [ ] **NP4**：建立机器 IR，显式处理 ABI、phi 边复制与线性扫描寄存器分配。
- [ ] **NP5**：经测量后加入发布管线 SCCP、局部值编号与有限内联，验证依赖失效及确定性。

### 编译流程重规划（2026-10-01，实施中）

新方向见[ADR-0009](adr/0009-yh采用check与IR及早期并行.md)，
已确认需求与事实见[设计决策树](03-design/yh-编译流程设计决策树.md)。
完整[设计](03-design/yh-编译流程重规划.md)与
[实施方案](02-plan/yh-编译流程重规划实施方案.md)已重写。
上一轮 CF-0–CF-4 已撤回，不代表当前实施清单。用户已确认整体方案并
明确要求实施 R0–R6。

- [ ] **R1**：文件一次解析、AST、任务私有前端、受检表示与 yh check。
  - [ ] R1 剩余（R2a/R2b 依赖其任务私有上下文契约）：
    语义/check 代码边界与旧遍历分离（check 仍复用旧多遍解析并抑制发射缓冲）→
    任务私有上下文（进程 worker 过渡方案依赖全局语义状态，线程池前置）→
    会话接口就绪（InterfaceReady 由串行/进程执行器驱动）→
    函数级 check 缓存。AST 已同时在 build/check 收集。
- [ ] **R2a**：typed SSA、verifier、默认低成本优化与双 arm64 后端。
  - [ ] R2a 剩余（按建议顺序，均为独立可验收切片）：
    负数字面量实参（一元减号作调用实参，当前 unsigned_score 因此回退）→
    switch 语句（比较链 CFG + case 值常量比较，无 fallthrough）→
    goto/label 与嵌套循环（break/continue 目标栈扩展）→
    for-in 迭代协议与无限循环 `for {}` →
    一元 +/- 与浮点标量（f32/f64 寄存器与比较/转换指令）→
    聚合/内存语义（LOAD/STORE/取地址、数组与 struct 赋值、参数/返回按值拷贝）→
    间接调用（函数指针/签名 fn 类型）与变参调用 →
    单文件与 `--emit-asm` 共用新后端 →
    默认优化覆盖与缓存提交协议复核（与 NP 管线、R2b 缓存键衔接）→
    Linux/macOS arm64 双平台 ABI 验收（含交叉组装对象的宿主运行证据）。
- [ ] **R2b**：首个完整 SSA 版本须具备线程池、接口就绪推进、函数
  check/IR 缓存、文件对象/链接缓存、确定性与失败提交验收。
  - [ ] R2b 剩余（首个完整 SSA 版本的硬门）：
    完整函数级 check/IR 缓存（当前缓存键仅覆盖窄 lowering 子集）→
    文件级对象（同模块跨文件 private 符号）→
    真正线程池（宿主线程桥；fork worker 与固定诊断缓冲是过渡方案）→
    接口调度的线程状态隔离、同项目并发与确定性验收 →
    缓存键纳入自有工具版本与所有目标/运行时输入。
  - [ ] 继续降低增量与冷编时间：短路求值切片后 20 轮测量单函数修改
    743.5/817.8ms、冷编 2203.0/2765.1ms（中位数/p95）；无改动 50ms
    中位数目标已达标，单函数 200ms 与冷编 1s 目标未达。单函数修改仍
    重新汇编整个所属模块且以外部汇编器为主；完整函数级 check/IR、
    文件对象与自有汇编/链接器是主要后续工作。
- [ ] **R3**：自有运行时与显式 OS API；独立配置取消隐式 system，
  旧行为只在过渡兼容配置保留。
  - [ ] R3 剩余（依赖 R2b 的宿主线程桥，可与之交错）：
    Linux arm64 原生构建并运行目录扫描适配（需先有经原生验证的 Linux 种子）→
    printf 按需扩展（宽度、精度、浮点；locale 不支持）→
    线程 API（与 R2b 真正线程池共用宿主桥，Darwin 走审核的 libSystem、
    Linux 走 clone syscall）→
    完整 OS 导入清单审计（`nm -u` 允许清单核对）后再验收 R3。
    汇编器/链接器仍通过显式 argv 调用系统工具。
- [ ] **R4**：Linux arm64 自有汇编子集、静态 ELF 链接与连续自编闭环；
  细化为 [yh-asm/yh-link TC0–TC6](02-plan/yh-asm与yh-link实施方案.md)。
- [ ] **R5**：macOS arm64 自有 Mach-O 工具链，披露 dyld/libSystem 并
  按 OS API 清单验收；细化为同方案 TC8–TC10。
- [ ] **R6**：扩展 x64 与 Windows，各目标分别完成运行/自举/性能验收。

### MOD-U6：远程获取、版本、锁文件、工作区

本地三层（当前项目/标准库/直接依赖）已交付（MOD-U0–U5，见
[模块与项目管理设计](03-design/yh-模块与项目管理设计.md)）。远程来源、
版本规则、锁文件与工作区**按实际需求另立设计与验收**，不沿用旧 Go
方案承诺（[ADR-0005](adr/0005-yh-mod-toml与按名称导入.md)）。

### 多平台后端（linux/darwin/windows × arm64/x64）

当前实施顺序以编译流程重规划的 R2/R4–R6 为准；
[多平台架构整理与优化方案](02-plan/yh-多平台架构整理与优化方案.md)
作为既有平台调查参照。
当前只有 arm64 双方言（GNU/Linux 与 Darwin/Mach-O）；Darwin 方言基础
已在 compiler/gen/target.yh、emit_arm64.yh 与 cmd/driver.yh 就位。x64 后端与
Windows 目标未实施。Linux/aarch64 自举种子已入库（`bin/yh-linux-arm64`，
2026-10-09），Linux 上可直接构建与跑自举门禁；Linux CI 流程按需重建。

### 玉衡 VS Code 扩展

方案见 [VS Code 扩展方案](02-plan/yh-VSCode扩展方案.md)。首发桌面本地；
独立 TypeScript 语言服务器；源码调试待编译器生成调试信息后实施。

- [ ] **VS-U0**：最小扩展、`.yh` 高亮、独立 LSP 进程、构建/运行命令。
- [ ] **VS-U1**：基于现有 `yh` CLI 的保存后诊断与进程取消。
- [ ] **VS-U2**：自举编译器分析接口、未保存缓冲区、精确跨文件定义跳转。
- [ ] **VS-U3**：源码调试信息与 DAP 接入。
- [ ] **VS-U4**：扩展集成测试、VSIX、发布与 CI。

### 编译器可选收尾

- [ ] **接口 pub 收缩**：四模块成模时 pub 从宽（顶层与字段全 pub），
  按实际跨模块使用收缩，减小接口文件（ADR-0007 P5 可选项）。
对象缓存键已包含编译器二进制内容（见 finish.md 同日项目增强记录），
相关未完成事项归入本轮流程与缓存设计，不再重复列“补编译器身份”。

## 设计决定不做（非缺口，勿列为任务）

- 本轮 C FFI 不开放用户裸 C 变参，libc `printf` 互操作暂缓；yh runtime
  `printf` 继续使用现有规则。后续需单独设计并验证平台变参与参数提升。
- 切片越界与生命周期运行时防护（ADR-0001）。
- **`pub const A *char = base.TEXT;`（初始化式是模块限定名）**：名字池里没有
  限定名，只取尾段会指向**本模块**同名符号，属错误语义（编译期第 7 条，已决议）。
- **经指针写入编译期模型**（`&TABLE[0]` 后 `*p = 5`）：保持只读拒绝（fail/153），
  与字符串只读池同一策略；如需要「编译期可写全局聚合常量副本」再单独设计。
- **顶层 const 折叠 `$mk()[0]`（对 CT 调用结果直接下标）仍不支持**
  （2026-10-09 已决议）：前端折叠路径无法索引裸聚合对象指针（架构限制），
  惯用写法 `const T = $mk(); T[0]` 经编译期模型可用；如需要可在实参折叠层加
  「调用+下标」特殊形态，暂记现状不作。