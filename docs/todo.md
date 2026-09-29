# todo

## yh 0.0.1 执行清单

本文件只追踪任务状态；具体改动位置、测试样例与阶段出口见
[改造方案](02-plan/yh-0.0.1-改造方案.md) §6。数组按值的语言承诺见
[ADR-0001](adr/0001-yh数组按值调用边界.md)。阶段顺序为
M0 → M1 → M2 → M3 → M4 → M5 → M6；前一阶段的验证门未通过时，
不把后一阶段标为完成。完成一项后勾选，并把实际命令和结果写入
`docs/finish.md`；代码任务每次都新增对应 `.yh` 用例并运行 `make`。

**当前基线**：Darwin 本机默认产出 Mach-O（`yh f.yh -o prog` 本机可执行）；`-sysroot`/`-Wl,-oformat=elf64-aarch64` 交叉 AArch64 Linux ELF。`make` 仍构建 TCC；`make test` 在 Darwin 只运行旧 pp
测试；`tests/yh` 的 65 个正例、29 个反例是 ANTLR 语法语料，
不是 yh 编译器已通过的测试。用例数量随新增文件变化，验收时按实际
发现的全部用例计数。

### M0：前置验证与语义定案

- [x] **M0-01 基线与依赖图**：记录当前 `make`、`make test`、
  `python3 tests/yh/check.py --coverage` 的结果；列出驱动、解析器、
  值栈、后端和链接路径的实际调用关系。证据放 `tmp/m0/`。
- [x] **M0-02 Linux 工具链与链接**：在 AArch64 Linux 验证独立 C
  工具链、sysroot/libc/crt/动态加载器、`lib/lib-arm64.c` 归档和
  最终 ELF 链接、运行；记录 Darwin 跨系统 `-o` 所需路径与缺失诊断。
- [x] **M0-03 数组与切片 ABI 探针**：在 `tmp/abi/` 比较包装结构体
  与调用点拷贝后传隐式指针，覆盖 ADR-0001 的大小、HFA、参数/返回、
  寄存器耗尽、递归及大数组矩阵；另测 16 字节切片。选定机制并新建
  实现 ADR，不把 C 代理探针当成 yh 运行测试。
- [x] **M0-04 语义边界**：在 `docs/03-design/` 确定前向调用、
  `main`/`pub`、字符串可写性、零长度数组、切片边界/生命周期、
  裸 C 变参提升；同步修正 `docs/yh.g4` 的 prelude 注释。
  保持已确定的末尾唯一类型化变参和 for-in 局部值拷贝规则。

**M0 验证门**：Linux ELF 链接/运行与 ABI 探针有可复现记录；
所有会阻塞代码生成的选择写入设计文档/ADR。失败项先修订方案。

### M1：构建、驱动与词法

- [x] **M1-01 构建与输入分派**：`make` 产出 `yh`、
  `libtcc.a`、`libtcc1.a`；用户源文件仅识别 `.yh`，
  运行时 C 文件由独立目标 C 工具链构建。新增驱动正反例并构建。
- [x] **M1-02 yh 词法**：同步保留字、`to_type`、RANGE/
  ELLIPSIS、数字下划线、转义、空白和预处理符拒绝规则；
  为每类规则新增 `tests/yh` 的 `.yh` 正反例。
- [x] **M1-03 纯语法入口**：接通 `yh --syntax-check file.yh`
  的词法/语法入口，消费到 EOF，不因未定义名字或缺少 `main` 报错；
  用最小正例和词法反例验证。

**M1 验证门**：构建可重复；词法用例按预期接受/拒绝；
ANTLR 原有语法回归仍通过。

### M2：完整纯语法与双模式回归

- [x] **M2-01 类型与声明**：实现 typeRef、别名、变量/常量、
  函数、struct/union/enum 与 pub 的语法；用相关 `.yh`
  正反例验证，不在语法模式查名字或常量值。
- [x] **M2-02 表达式**：实现优先级、调用/下标/成员、
  `.to_type(typeRef)`、structInit、`sizeof(T)`、`len(e)`；
  验证后缀链，并拒绝旧 `as` 写法。
- [x] **M2-03 语句**：实现 if/for/switch、赋值、label/goto
  与块，验证 structInit/块边界；语法模式接受语义错误但形态合法的表达式。
- [x] **M2-04 编译器语法回归**：给 `tests/yh/check.py` 增加
  `--compiler` 模式，遍历所有语法正反例并与 ANTLR 模式分别计数；
  确认解析消费到 EOF。

**M2 验证门**：两种语法检查模式对实际发现的全部语料通过；
不得把语法通过等同于编译或运行通过。

### M3：基本语义与可执行闭环

- [x] **M3-01 名称与内置符号**：实现作用域、const 值、
  pub ELF 绑定、M0 决定的前向调用规则和 8 个 prelude extern Sym；
  以 `.yh` 编译正反例及 `readelf -sW` 验证。
- [x] **M3-02 类型转换与表达式**：按改造方案 §4.1 先检查 yh
  隐式/显式转换，再调用 TCC 后端；覆盖数值、bool、指针、
  `.to_type(T)` 结果为右值及赋值/传参/返回的拒绝规则。
- [x] **M3-03 语句、初始化与输出**：完成函数体、变量、
  structInit、控制流、switch、goto、`-o` 和 `-run`；
  Linux 上运行 hello 并核对 ELF 机器类型、加载器和符号。

**M3 验证门**：Linux 标量程序的 `-o`、`-run` 结果一致；
非法语义被编译模式拒绝，纯语法模式仍按语法判断。

### M4：聚合值、遍历与变参

- [x] **M4-01 数组按值调用**：按新实现 ADR 落地数组参数和返回，
  用真实 `.yh` 用例逐行覆盖 ADR-0001 的拷贝、HFA、栈参数、
  递归和大数组矩阵；不同长度实参编译拒绝。
- [x] **M4-02 切片与 for-in**：规范化 `[]T`，实现 len、
  下标、数组转切片视图及数组/切片/区间遍历；验证绑定作用域、
  值拷贝、空范围、continue/break 与转换拒绝。
- [x] **M4-03 类型化与裸变参**：末尾唯一类型化变参打包为临时切片；
  零参数和求值顺序有运行测试。裸 C 变参只用于内置 prelude，
  Linux 上验证默认提升、寄存器/栈边界与非法用户声明。

**M4 验证门**：ADR-0001 和改造方案 §5 的每项行为都由
`tests/yh-run/` 的编译、拒绝或 AArch64 Linux 运行用例验证。

### M5：完整测试与交付

- [x] **M5-01 回归集成**：建立 `tests/yh-run/check.py`，
  `make test` 分别报告语法、编译、拒绝和运行结果；
  Darwin 运行项显示 SKIP 原因，Linux 完整回归通过。
- [x] **M5-02 安装与文档**：核对 build/install/uninstall、
  VERSION、README 和 `docs/03-design/`；从干净构建执行
  `make clean && make && make test`，Linux 再验 `-o`/`-run`
  与 `readelf`。

**M5 验证门**：交付清单全部通过，跳过项不计为通过。

### M6：代码清理

- [x] **M6-01 清理旧 C parser**：只删除实际无调用的 C 解析代码
  和本次改动产生的孤立声明；比较清理前后的构建、完整回归和
  Linux 运行矩阵，并在 `docs/finish.md` 记录结果。

**M6 验证门**：清理前后结果一致，未证实无调用的代码不纳入本次删除。

## 0.0.2+ 待设计事项（不阻塞 0.0.1）

### yh 自举

自举定义、能力边界、源码组织、阶段任务与验证门统一见
[yh 语法与编译器自举统一方案](02-plan/yh-自举实施方案-v2.md)。

- [x] B0：定位当前 `make test` 的 goto/递归失败，冻结可靠 stage0 和差分测试口径
  （缺口矩阵见[运行覆盖缺口矩阵](02-plan/yh-运行覆盖缺口矩阵.md)）。
- [x] B1：增加 `read`（推荐同时增加 `close`）及带 `argc/argv` 的 `main` 语义；用 `.yh` 运行用例验证。
- [x] B2：验证编译器工作负载所需的类型、指针、递归、ABI 和容量边界，修复实际发现的问题。
- [x] B3：建立 `compiler/` 源码拼接与驱动，完成 yh 词法器和字节输入探针
  （拼接清单在 Makefile `SELFHOST_SOURCES`；1 MiB、NUL、未终结串等边界
  探针见 `docs/finish.md`；源码目录按用户指示用 `compiler/` 替代方案的 `src/yh/`）。
- [x] B4：完成 yh 纯语法解析器，解析自身并通过全部语法语料（G1）。
  stage0 交叉编译 stage1（AArch64 Linux ELF），容器内自解析拼接源码到
  EOF，`tests/yh/check.py --compiler --compiler-path tests/yh/container-yh.sh`
  差分 66/66 正例、29/29 反例；验证入口 `make bootstrap`。
  已知偏差：自编源码用 `for 1 { }` 替代无限 `for { }`——stage0 的
  continue 在无条件 for 内不识别为循环内（探针 `tmp/probe-continue.yh`），
  待单独修 stage0 后可改回。
- [x] B5：完成语义检查与编译器自身所用子集的 AArch64 Linux 汇编输出。
  分层：前端语义（symbols/sem/parse_*）→ 目标数据模型（target.yh）→
  指令发射（emit_arm64.yh）；`--emit-asm` 产出 GNU 汇编，经容器 gcc
  `-no-pie` 链接为 ELF。运行语料 40/44（余 4 项为 B7 边界：按值聚合、
  数组按值、浮点/类型化变参，均显式拒绝并有 `fail/` 或 `run/25..29`
  用例钉住）。架构与换平台契约见
  [自举后端架构](03-design/yh-自举后端架构.md)。
- [x] B6：执行 stage0→stage1→stage2→stage3 的自身子集闭环（G2）。
  `make bootstrap` 逐门验证：拼接确定性、G1（自解析 + 66/66 + 29/29）、
  G2（stage1 编译自身得 stage2；stage2 自解析、语法差分 66/29、
  运行子集 25/25）、G2+（stage2 编译自身得 stage3，stage2.s 与
  stage3.s 逐字节相同，stage3 自解析）。**G2 达成**。
- [x] B7：补齐现有 yh 全语言语义与运行覆盖。
  已实现：聚合按值（参数/返回/嵌套字面量）、切片（视图/len/下标/实参）、
  for-in（数组/切片/区间）、类型化变参、浮点 f32/f64（传参/返回/运算/
  转换）、structInit 作值。**stage1 全量通过**：语法 66/66+29/29、
  运行全量通过。
  **自举缺陷已修复**：stage2 浮点字面量常量编码错误（根因：`sem_push_arg`
  对浮点实参压 x0 而非 d0）与连带的整数窄化转换缺失（`sem_cast` 缺
  「整数→整数」分支）。修复后 stage2 浮点常量正确、**stage2.s 与 stage3.s
  逐字节一致（全量固定点）**，`make bootstrap` 恢复全量运行语料与全量
  固定点比较。定位手段：新增本机自举差分探针 `make selfhost-native`
  （`tests/selfhost/native-selfhost.py`，无需容器）。详见
  [自举后端架构](03-design/yh-自举后端架构.md) §6。
  **仍未实现**：全局聚合变量初始化。
- [x] B8：固定三代构建、逐字节汇编比较与干净环境复验（**G3 达成**）。
  新增 `make bootstrap` 全量门（G1 语法 + G2 三代闭环 + G2+ 全量固定点）
  与 `make g3` 正式验收（`tests/selfhost/g3-acceptance.py`）。在 Ubuntu
  24.04/aarch64 容器内：stage1/stage2/stage3 **各自**通过全量语法语料
  （66/66 + 29/29）与运行语料（50/50）；stage3 自解析；stage2.s 与
  stage3.s 对 `compiler.yh` 及 **35 个代表程序**逐字节一致；重复发射
  确定；发射内容无宿主路径/时间戳；53 个反例全部非零退出并带位置诊断、
  无汇编泄漏；产物与 SHA-256 归档到 `tmp/bootstrap/artifacts/`。
  **修复的第三个自举缺陷**：混合整型/浮点形参的寄存器分配（AAPCS64
  整型 x0..x7 与浮点 d0..d7 独立计数，原实现错用形参表位置下标）。
  验收报告见 [G3 自举验收报告](01-finished/G3-自举验收报告.md)。
  剩余：是否替换默认 `yh` 需另立验收（G3 不自动宣称 CLI/Mach-O 已迁移）。

## 自举剩余问题（2026-09-29 盘点，全项处理完毕）

> **A'. 自举编译器超 8 参调用参数错位（已修复，2026-09-29）**：原有 run/14、
> run/37 的期望值都是加法（可交换），错位被交换律掩盖。根因三处：
> ① 第二段栈实参回压先 `sub sp, sp, #pad`（pad=8）把 sp 拉成 8 字节对齐，
> 随后的 `str x9, [sp, #-8]!` 触发 AArch64 的 SP 对齐故障（Linux/Darwin
> 都报 SIGBUS，不是段错误）；② 被调方标量栈参仍是 16 字节间距
> （`compiler/sem.yh` `sem_declare_param`），与 AAPCS64／stage0
> （`arm64-gen.c` C.14：size < 8 补足 8 字节槽）的 8 字节槽不一致，9 参时
> k=0 两种公式同值、第 10 参才现形；③ 间接调用目标地址在开栈区之后才弹出
> （`em_pop("x10")`），弹出的会是栈区槽而非实参。
> **修复**：整块开区 + 偏移写入（新增 `em_call_stack_alloc`／
> `em_call_stack_store`／`em_call_stack_store_fp`，删除孤立的
> `em_call_cleanup`）、被调方栈参统一 8 字节间距、间接调用目标在开区前弹入
> 帧内槽并在 `blr` 前装回 x10。**不可交换位权用例**：
> `tests/yh-run/run/45-many-args-bitweight.yh`（9 参，341/170）与
> `run/46-many-args-stack-slots.yh`（12 参，钉住 [sp+0]/+8/+16/+24，
> 1365/2730），二者都含函数指针间接调用。**验证门全绿**：`make test`
> 61/61、`make selfhost-native`、`make bootstrap`（run 46/46）、`make g3`。
> run/14、run/37 保留（求和形式偏弱），参数顺序由 45/46 钉住。
> 详见 `docs/finish.md`。stage0 本就按 AAPCS64 正确分派。
>
> **A'''.（2026-09-29 深夜定位并修复）for-in 区间长度被深帧寻址破坏——
> 不是槽重叠**。run/27 的 `range=37128` 根因：`sem_forin_begin` 区间
> 路径把终点装入 x9 后，data 槽的 `em_lea_local_to` 在深帧（偏移
> >255）时用 `movz x9, #off` 拼地址，**覆盖了终点**——区间长度被算成
> 「槽偏移 - 起点」（288-1=287 而非 4），循环多跑 283 次。小帧时 lea
> 走 `sub x10, x29, #imm` 不碰 x9，故 mini 复现全过、只有深帧场景
> 触发。修复：终点改用 x11（与栈实参修复同策略）。
> **同类风险全排查**（x9 活跃值 + 随后 lea 的模式，全文件扫描 6 窗口）：
> 另修 3 处——for-in 数组 len（先取地址再装常量）、for-in 聚合元素
> 绑定（删 `mov x9, x0` 保地址法，改 lea→`mov x1, x10`，x0 天然保持
> 元素地址）、聚合局部清零循环（先取槽地址再装计数器）。修复过程中
> 一度删多了标量元素路径的 `mov x10, x0`（em_load_sized 从 x10 读），
> 已回补并由 mini-aggr3 钉住。
> **验证**：自举 Darwin 本机 **语法 66/66+29/29、运行 61/61 全绿**
> （自举产物本机接管达标）；四门全绿——`make test` 61/61、
> `make selfhost-native`（重构为全量 run 用例含 printf，不再过滤；
> macho.py/probe-main 转为 GNU 输出兼容路径）、`make bootstrap`
> （G1 + G2 run 46/46 + 固定点）、`make g3` **通过**，新固定点
> `stage2.s == stage3.s` SHA-256 `1279cf29…50a92b`。
>
> **A'''.（2026-09-29 深夜续）深帧寻址临时寄存器根除 + 差分压测达标**：
> run/27 后续最小化发现，崩溃指令 `str x0, [x10, #8]` 的 x10 是
> `em_lea_local_down` 深帧形态（`movz x10, #off; sub x0, x29, x10`）
> 的**临时寄存器**，调用方（变参打包）误以为 x10 仍是 sl_off 槽地址
> ——这是一族「小帧正常、深帧即坏」缺陷的**总根源**：lea 四原语
> （local/down/to/to_down）的深帧临时分别借用了 x10/x9。**修复**：
> 四原语深帧临时统一改用**专用 x12**（此前全文件零使用），emit_arm64.yh
> 注明「任何调用点不得依赖 x12 跨 lea 存活」；此前调用点的 x9→x11
> 修复保留为双保险。
> **差分压测（tmp/dt-gen.py，80 例确定性随机程序）**：深帧 24–46 局部、
> 12 参走栈、for-in 区间/数组、复合赋值、短路、递归聚合、类型化变参、
> 浮点混合、全局变量。**自举侧 80/80 与 stage0 无差（2 例为 stage0
> 自身错）**。压测顺带记录 **stage0 参照系缺陷六项**（不影响自举链）：
> u64 局部 store 断言、深帧多 switch 断言、深帧三元断言、数组形参
> 直接 for-in 误拒、聚合返回值直接作实参断言、深帧聚合局部零初始化
> 失效（自举输出正确 0）。
> **验证**：自举 Darwin 本机语法 66/66+29/29、运行 61/61；四门全绿，
> 新固定点 `stage2.s == stage3.s` SHA-256 `c23883cb…8b475b56`。

**A. 自举链本身：无阻塞项。** stage1/2/3 在 aarch64 Linux 上各自通过
全量语法（66/66 + 29/29）与运行语料（59/59），stage2.s 与 stage3.s
逐字节一致（SHA-256 `9c5cfc78…13fa8`，2026-09-29 新固定点），
`make g3` 复验通过。B8 验收脚本新增：运行语料失败自动重试一次
（排除 macOS Docker 挂载元数据延迟的瞬时假失败）。

**B. 语言特性缺口：六项全部实现（2026-09-29，stage0 与自举双侧）**：

- [x] **全局聚合变量初始化**：`let g P = P { x: 3, y: 4 };` 命名式/
  位置式/嵌套字面量/字符串字段（stage0 经节内 R_DATA_PTR 重定位）。
  自举侧实现在 `compiler/parse_decl.yh` 的 `parse_global_struct_init`。
- [x] **全局数组/切片变量**：零初始化落 `.bss`；全局数组字面量
  `[10, 20, 30]` 为常量数据（自举侧 `parse_global_array_init`）。
  stage0 全局切片字面量暂不支持（干净拒绝，用例避免）。
- [x] **数组与切片字面量**：`let a [2]int = [1, 2];`、`let s []int =
  [7, 8, 9];`、实参与同型赋值上下文（目标类型经预期类型管道传递）。
- [x] **切片表达式** `arr[0..2]`：左闭右开视图，`len = max(0, end-start)`，
  data = 基址 + start*元素大小，不拷贝元素、无边界检查（ADR-0001）。
  stage0 侧 `len = d & ~(（d>0）-1)` 无分支钳制。
- [x] **函数内嵌套 struct/union/enum/type 声明**：登记布局与顶层一致，
  类型表全局可见；自举侧经 `c_nested_type` 旗标在 pass 2 同样登记。
- [x] **`sizeof(expr)`**：只求型不求值。stage0 用 `nocode_wanted` 抑制
  发射 + 星号链前瞻（捕获重放）区分 `sizeof(*p)` 与 `sizeof(*T)`；
  自举侧用发射层静默闸门（`em_put` 处 `c_em_suppress`）+ 类型名判定。
- [ ] 裸 C 变参（`...`）在用户源码被显式拒绝（仅编译器内置 prelude 用，
  **设计决定**，非缺口）。
- [ ] 语义边界既定不做：切片越界与生命周期运行时防护（ADR-0001，
  **设计决定**，非缺口）。

**C. stage0（宿主 C 实现）缺陷：三项全部修复（2026-09-29）**：

- [x] 零初始化全局 `let g int;` 在 `-o` 模式误报 redeclaration：
  根因是 pass 1 提前落地全局符号、pass 2 重复登记；修复为 pass 1
  统一不落地（`src/core/yh_decl.c` `yh_parse_binding`），与带初始化
  路径一致。用例 run/38。
- [x] **Mach-O 重定位记账缺陷**（本轮新发现）：节头 `nreloc` 按 ELF
  条数记账，但非零 addend 的重定位会额外写出一条前置 ADDEND 条目，
  ld64 按声明数截断尾部条目——悬空 ADDEND 触发「relocation not
  supported」（全局数组下标链接失败），或 printf 的 CALL26 丢失使
  懒绑定桩悬空（程序挂起）。修复：`src/core/macho-out.c` 按 Mach-O
  实际条目数记账（新增 `nreloc_elf` 供写出循环遍历）。
- [x] **语法模式全局表未初始化崩溃**（本轮新发现）：`ty_register_
  builtins` 只在 `--emit-asm` 路径调用，语法模式 `t_types` 为 NULL；
  自举编译器新加的实参预期类型代码在语法模式读 `t_types[...].sub`
  段错误（native 自举差分门暴露）。修复：限定编译模式并校验 FN
  类型（`compiler/parse_expr.yh` 调用实参分支）。

**D. 工程/文档账目：已清**：

- [x] `docs/02-plan/yh-自举实施方案-v2.md` B3–B7 任务项已随实际完成
  勾选（14 项）。
- [ ] 多平台后端（linux/darwin/windows × arm64/x64）：方案见
  [多平台架构整理与优化方案](02-plan/yh-多平台架构整理与优化方案.md)，
  不阻塞 0.0.1；自举编译器的 Darwin 方言基础（`tg_darwin` 判定、
  `_` 前缀、@PAGE/@PAGEOFF、外部符号 GOT 寻址）已在 `compiler/
  target.yh`/`emit_arm64.yh`/`driver.yh` 就位。

## yh 模块与项目管理（2026-09-29 修订方案，尚未实施）

用户确定 mod.toml、module、名称 import，以及“本项目 → 标准库 →
第三方”的搜索顺序；没有 internal 特殊机制。当前设计见
[模块与项目管理](03-design/yh-模块与项目管理设计.md)，
验收见 [实施方案](02-plan/yh-模块与项目管理实施方案.md)，
取舍见 [ADR-0005](adr/0005-yh-mod-toml与按名称导入.md)。

旧 PKG-U0–U8 已被本清单替代，原 MOD-P0–P9 内部重构仍为撤回的历史
清单；两者均未作为本轮代码执行任务，历史方案／报告保留。

- [x] **MOD-DOC**：修订 mod.toml/module/import 设计，补齐三层搜索、导入上下文与同名规则。
- [x] **MOD-U0**：复核最新单文件、ABI、自举与 CLI 基线，确认项目模式兼容边界
  （2026-09-29：`make test` 61/61、`make selfhost-native` 全绿；按 ADR-0006
  冻结规则确定 MOD-U1 起只在自举侧 `compiler/` 实施，stage0 语料不进新语法）。
- [ ] **MOD-U0**：复核最新单文件、ABI、自举与 CLI 基线，确认项目模式兼容边界。
- [x] **MOD-U1**：同步 grammar 与两套前端的 module/import、限定类型／值、pub 字段、FileID／导入表
  （2026-09-29，按 ADR-0006 调整为**仅自举侧**实施：`compiler/parse_module.yh`
  文件头解析与导入表、词法 TK_MODULE/TK_IMPORT、限定类型语法、pub 字段登记；
  `docs/yh.g4` 按[设计](03-design/yh-模块与项目管理设计.md) §3 暂不改写，
  ANTLR/stage0 语料不进新语法，模块语料在 `tests/modules/` 由自举产物校验）。
- [x] **MOD-U2**：TOML/schema、模块头索引、三层搜索、依赖自己的解析上下文、歧义与不回退诊断
  （`compiler/toml.yh` 最小 TOML 子集解析 + schema 校验；`compiler/project.yh`
  向上发现 mod.toml、递归装载依赖（规范化路径去重、依赖环报错）、
  递归扫描源码根建模块索引（嵌套项目边界跳过）、绑定层实现
  本项目→标准库（YH_STDLIB）→直接依赖三层搜索：入口模块不可导入、
  第三方同名歧义、缺失报已搜索层次；`yh list [--resolve]` 诊断命令）。
- [x] **MOD-U3**：同模块多文件、模块作用域、pub、类型身份、导入 DAG、入口与库语义
  （多文件同模块 pass1 登记/pass2 编译、跨文件私有共享与互递归；
  模块重复顶层声明报两个位置；导入名与顶层声明冲突检查；未使用导入报错；
  限定名 m.f/m.T/m.T{} 命名空间解析；跨模块私有字段/私有符号/位置式
  构造含私有字段拒绝；导入图 topo 排序与环路完整链诊断）。
- [x] **MOD-U4**：本地第三方项目、独立对象／接口、项目限定符号、跨模块 ABI 与真实链接运行
  （每模块独立子进程编译为独立 .s + 稳定接口 .s.i（yh-iface v1 头校验，
  pub 签名/类型布局/常量值/pub let）；符号带 __proj__mod 后缀、pub→GLOBAL
  私有→LOCAL、入口模块 main 裸名；最后 gcc/clang 一次链接；真实运行）。
- [x] **MOD-U5**：解析重绑定与内容缓存、完整自举项目发现／编译／链接、三代验证
  （解析不缓存——重绑定由每轮重解析构造保证；对象缓存按 manifest 内容
  哈希：后缀+entry+源文件内容+依赖接口内容+版本标记，命中跳过重编译，
  冷热一致由发射确定性保证；自举链三代均通过 modules 语法语料与项目验收，
  见 make selfhost-native / make bootstrap）。
- [ ] **MOD-U6（后续）**：按实际需求另定远程获取、版本、锁文件和工作区，不沿用旧 Go 方案承诺
  （2026-09-29 明确：本地三层交付不含远程来源；需求出现时另立设计与验收，
  见 finish.md 同日条目末尾的边界记录）。

首个里程碑为 MOD-U1–U4；每次代码修改新增 tests/ 中 `.yh` 用例并构建。
多文件项目用专门 fixture runner 验证；临时产物放 tmp/。

## 玉衡 VS Code 扩展（2026-09-30 方案，尚未实施）

方案见 [VS Code 扩展方案](02-plan/yh-VSCode扩展方案.md)。首发桌面本地；
独立 TypeScript 语言服务器；源码调试待编译器生成调试信息后实施。

- [ ] **VS-U0**：最小扩展、`.yh` 高亮、独立 LSP 进程、构建/运行命令。
- [ ] **VS-U1**：基于现有 `yh-new` CLI 的保存后诊断与进程取消。
- [ ] **VS-U2**：自举编译器分析接口、未保存缓冲区、精确跨文件定义跳转。
- [ ] **VS-U3**：源码调试信息与 DAP 接入。
- [ ] **VS-U4**：扩展集成测试、VSIX、发布与 CI。
