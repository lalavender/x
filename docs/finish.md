# finish

靠前条目记录最近状态；后续条目保留各次交付时的历史状态。

## 2026-10-02 属性系统与 C 互操作统一实施完成

按用户授权完成[统一实施方案](02-plan/yh-属性系统与C互操作统一实施方案.md)：
单组 `@[extern, noreturn]` 属性列表，删除 `heap`，内存分配留待显式语法另行
设计；本轮保留 yh runtime `printf`，未开放用户 C 裸变参。

- `docs/yh.g4` 与词法/解析索引支持单组多属性；语义检查未知、重复、错配与
  不合法原型。`extern` 函数无体时引用 C 符号，有体时定义裸名 C 函数；
  外部数据类型共享布局，opaque struct/union 仅可经指针使用。
- C ABI 与 yh 模块导入标记分离。固定参数边界覆盖布尔、窄/宽整数、指针、
  浮点、外部枚举和受限回调；数组、切片与结构体按值边界拒绝。接口保留无属性
  v1，属性行使用 v2，属性改变会更新接口和调用方 IR。
- `noreturn` 贯通定义检查、SSA unreachable、调用方终止及后端 trap。`inline`
  已接入受限小型标量 SSA 内联；复杂控制流、调用、取址、公开跨模块形态保留
  普通调用，参数副作用保持一次，callee 函数体纳入调用方缓存键。
- `[c]` 项目配置支持依赖项目中的 C 源、预编译对象和系统库；C 源每次构建
  重编，源/头文件变化反映到对象，预编译对象内容变化触发重链接；无效 C 源
  不复用旧对象，路径含空格使用显式 argv。
- 测试包括 C/YH 双向九参数和窄标量调用、浮点、回调、共享 struct 的
  `sizeof/offsetof`、头文件和对象缓存变化，以及 inline/noreturn 的 IR/汇编证据。
- 验证：`make`、`make test`（语法 67/67 正例、39/39 反例；运行/失败/通过
  语料 50/32/8，全计 90/90）、模块项目验收 74/74、`make selfhost-native`
  退出码 0；cc3→cc4 的 12 个模块产物固定点一致、52 个源文件自解析通过，
  模块语法 17/17，其他固定点和自有运行时探针通过。仅在当前 Darwin/Mach-O 主机完成原生运行；
  Linux AArch64 原生验收需对应种子和环境。依照方案，本轮未运行 `make seed`。

## 2026-10-02 属性系统统一方案修订（单组多属性，删除 heap；未实施）

用户确定使用 `@[extern, noreturn] fn c_fatal(code int) void;` 形式，
删除 heap，内存分配后续通过显式声明设计。已修订
[统一实施方案](02-plan/yh-属性系统与C互操作统一实施方案.md)和 todo。

- 每个声明最多一组列表，删除连续多组语法；补充三属性组合矩阵、同组
  重复检查、固定接口输出顺序，以及属性不泄漏到相邻声明的验证。
- 当前只保留 extern、inline、noreturn；撤回 heap 构造/装箱/引用类型
  方案与 H0/H1 阶段，保留现役值语义与 sizeof，未来分配语法独立设计。
- 精简交付边界：U0–U2 为属性/extern/noreturn 核心交付，U3 为项目
  混编，I1 与 NP5 共用实际内联；本条不表示编译器功能已经完成。
- 本次只更新 Markdown 文档，检查本地链接、代码块与 diff 格式；
  没有修改 compiler/、docs/yh.g4、tests/ 或种子，没有运行代码构建/回归。

## 2026-10-02 属性系统与 C 互操作统一方案交付（待评审，未实施）

本条保留初稿交付历史；其中多组语法、heap 与 H0/H1 已被上方修订撤回。

根据用户要求，结合四个属性与旧 FFI 草案，交付
[统一实施方案](02-plan/yh-属性系统与C互操作统一实施方案.md)，同步 todo，
在旧 FFI 草案标记新版参考。本条只记录计划交付，不表示功能已经完成。

- 建议统一使用 `@[...]`；extern 函数无体引用、有体提供 C ABI 定义，
  pub 继续描述 yh 模块可见性；保留 pub 数据类型与 let 不导出的现役规则。
- 修正 F_EXTERN 兼作模块导入、8192 标志已占用、自有 intrinsic 分配器与
  C 同名函数不能幂等合并、>16B HFA 仍有独立 ABI 等假设；引用 Arm/Apple
  官方 ABI 规则。v1 聚合采用指针边界，C 全局通过包装函数访问。
- 规划 U0–U3、H0/H1、I1；heap 指针构造模型待确认，inline 与 NP5 共用
  SSA 内联；每个行为阶段要求新 `.yh` 用例和构建/回归/固定点验证。
- 本次只修改 Markdown 计划与任务记录；核对本地链接及 diff 格式。
  未运行代码构建或回归，未修改 docs/yh.g4、compiler/、tests/ 或种子。

## 2026-10-02 let 不导出：GenState 打包重构 + pub let 废除（两代滚种）

语言规则（用户决策）：let 变量只能是模块变量或函数局部变量，**不支持
导出**（`pub let` 非法）。该规则与编译器自举现实冲突：gen 模块 208 个
跨模块可变全局（c_pos/t_types/p_mods 等）被引用 3054 处。用户在
AskUserQuestion 中选择「GenState 打包（彻底）」路径。

- **方案**：208 个 pub let 收进 `pub struct GenState`（字段一律公开——
  与 struct 一等化规则吻合），gen 私有实例 `g_state` + 导出
  `pub fn G() *GenState { return &g_state; }`（实测 `&全局` + 函数返回
  指针现有机制完全支持，**零新语言特性**；对比 pub const 指针导出方案
  免去「取全局地址作编译期常量 + 数据槽重定位」新机制与接口格式变更）。
- **替换**：gen 内部 1185 处裸引用 → `g_state.x`；跨模块 1869 处
  `gen.x` → `gen.G().x`；cmd/parse 66 个同模块 pub let 直接去 pub；
  9 个非零初始化器迁入 `gen.state_init()`（driver main 入口调用，
  worker fork 继承）；接口发射器停发 SYM_VAR（pub let 行）。
- **暴露既有发射器 bug**：`f().field = v`（函数返回指针接字段写）在
  `sem_member` 的 LVALUE 分支无条件 `ldr x0,[x0]` 多一次间接——该形态
  GenState 之前从未被语言使用，实测最小复现（读写探针 gftest exit=139）
  确认为**既有缺陷**而非重构引入。修复：按进入时的 `c_res_is_addr`
  （基底形态）判据决定是否装载——变量引用/未装载解引用（is_addr=1）
  需 ldr，函数返回的指针（is_addr=0）不得再间接；读路径不变。
- **过渡期源码避让**：v1（旧种子生成）的 cmd 代码含 bug 形态无法运行，
  源码改写为**函数级局部指针**形态（`let gs *gen.GenState = gen.G();`
  + `gs.field`）——186 处函数、覆盖全部原 LVALUE 写与同函数读；脚本
  两次失败（字符字面量 `'{'` 破坏朴素大括号配对、跨行签名插绑定错位）
  后改用「逐行向上找 fn + 感知签名结束行」方案稳定落地。修复后固定点
  通过（源码无 bug 形态，两代产物一致）。
- **语料迁移**：fourdir/fourdirbad 的 `pub let counter` 改为私有
  counter + `pub fn counter_value/set_counter`（跨模块可变状态改函数
  封装的示范）；runtimebytes 的 pub let 仅同模块使用直接去 pub；
  02_pub_export 的 pub let 改 pub const；新增 rejected/35_pub_let；
  g4 重构 topLevelDecl → exportedDeclBody + plainDeclBody（pub 不可修饰
  letDecl）。
- **Gen N-b**：`parse_top_decl` 拒 `pub let`（报错「let 变量不支持
  导出」），接口加载（c_iface_load=1）容忍旧格式 pub let 行以兼容
  持久缓存。
- 验证：每代 `make` + `make test`（正例 66/66、反例 35/35、运行语料
  62/62）+ `make selfhost-native`（固定点、modules 17/17、project
  55/55）全绿后 `make seed`；种子哈希 Gen N-a → eb37868c…、Gen N-b →
  c4168844…。
- 语义边界补充：`&全局` 表达式与函数返回模块内全局地址为现役机制
  （实测 exit=9 验证），GenState 即依赖此实现跨模块状态共享。

## 2026-10-02 enum 同步一等化：pub enum 与成员导出（审计后补齐）

用户要求核查 union/enum 是否与 struct 同步、跨模块 pub 检查是否完备。
审计结论：union 已同步；跨模块 fn/const/struct 检查完备（parse_global_init
置 F_PUB、iface_load 改写符号、引用侧 mod_ns_lookup 校验，实测
`lib.hidden()` 正确拒绝）；**enum 有两处缺口**，本条目补齐：

- **裸 enum 未同步**：struct/union 已强制 pub 而 enum 仍可裸写。
  `parse_top_decl` 补 enum 分支校验（报错「enum 必须带 pub」）；语料
  3 文件裸 enum 迁移为 `pub enum`；新增 rejected/34_bare_enum；
  docs/yh.g4 的 plainDeclBody 移除 enumDecl（enum 只能经 pub 进入）。
- **pub enum 成员不导出**：`parse_enum_decl` 成员常量只登记 F_GLOBAL，
  跨模块 `lib.red` 报「模块没有导出该名字」。成员按枚举的 pub 置 F_PUB
  进入接口名字表；`iface.yh` 常量发射循环跳过 TY_ENUM 常量——成员已随
  pub enum 体导出，否则接口重复登记、加载侧报重定义。
- 新增 `tests/modules/projects/enumexp/` fixture（lib：pub enum Color/
  pub const/pub struct/pub fn；host：跨模块成员引用、判别值断言、字段
  访问），build-check 注册 `u4-enumexp-run`（退出码 10）。临时探针实测
  全链路：`lib.red`/`lib.green`/`lib.PI2`/`b.w` 引用通过，
  `lib.hidden()` 构建期拒绝。
- compiler 源码无 enum 声明、无字段 pub，滚种固定点不受本条目影响。
- 验证：`make` + `make test`（正例 66/66、反例 34/34、运行语料 62/62）
  + `make selfhost-native`（modules 17/17、project cases 55/55 含
  enumexp）全绿后 `make seed`（bin/yh → 964db00a…）。

## 2026-10-02 struct 语法收紧：pub struct 一等化（三代滚种）

规则（用户决策）：① 裸 `struct`/`union` 非法，必须写 `pub struct` /
`pub union`；② `pub struct` 字段一律公开（用户示例 `pub struct IRType {
kind int; ... }` 为唯一正确形式），字段级 `pub` 前缀在用户源码中报错；
③ 类型声明禁止嵌套——fn 体内 struct/union/enum/type 声明特性移除，
`c_nested_type` 机制删除。enum/type 的顶层 pub 可选性不变。

- **接口传递闭包（先行一代）**：`pub struct` 一等化后接口正文首次出现
  「字段引用外模块类型」的 mangle 名（如 AstIRBuilder 字段 `*ir.IRInst`），
  而构建器原先只加载直接 import 的接口，stage1 必卡死。重写
  `cmd/module_build.yh` 的 `mb_module_iface_deps` 为四步：直接导入 →
  传递闭包（绑定名取 mangle 后缀，不与源码别名冲突）→ 按 `pj_order`
  拓扑排序 → 统一构造会话接口路径；抽出 `mb_dep_push` 去重追加。单独
  全绿后滚种（bin/yh → 0b8b85a3…）。
- **语法收紧一代**：`parse_top_decl` 拒裸 struct/union；`parse_stmt`
  拒 fn 内类型声明；`sem_add_field` 去 is_pub 参数（is_pub 恒 1），
  删 `sem_expr`/`sem_call_literal`/`parse_expr` 三处跨模块字段 pub 检查
  与 `sem_struct_lit_begin` 的 named 参数；删 `c_nested_type`；
  docs/yh.g4 重构 topLevelDecl（struct/union 只能经 pub 进入）；compiler
  源码 4 处裸 struct 转 pub struct 并为 ast_ir/ast_ir_build/project/clock
  字段补前缀（旧种子发射器按 is_pub 过滤，前缀是固定点一致的前提）；
  语料 31 文件裸 struct→pub struct、14 文件字段前缀删除；
  run/44-nested-decl 移除并新增 rejected/30_bare_struct、
  31_bare_union、32_nested_type_decl；pubpriv host/host3 由 fail 转 run
  正向用例（u3-pub-field-access=2、u3-positional-pub-construct=1），
  fourdirbad 改验非导出函数（p2-fourdir-nonpub-symbol）。全绿后滚种
  （bin/yh → 0b4212ca…）。
- **前缀移除一代**：`parse_struct_decl` 字段位 TK_PUB 在用户源码报错
  「字段一律公开，不接受 pub 前缀」；接口加载（c_iface_load=1）仍按
  yh-iface v1 格式跳过字段 pub 标记——接口格式零变动，cc3/cc4 产物
  才能逐字节一致；compiler 源码 248 处字段前缀全删；新增
  rejected/33_field_pub_prefix。全绿后滚种（bin/yh → 762d3ce5…）。
- 文档同步：docs/yh.g4（topLevelDecl/plainDeclBody/structDecl/unionDecl/
  fieldDecl）、03-design/模块与项目管理设计 §可见性、03-design/00-语义边界
  §3、compiler/README 无需改动；历史方案文档（02-plan 模块实施方案、
  03-design/Go风格模块与包设计）自带"已被替代"抬头，保留原状。
- 验证：每代 `make` + `make test`（ANTLR 正例 66/66、反例 33/33，
  编译器语法门同，运行语料 62/62）+ `make selfhost-native`（含固定点、
  模块/项目验收 54/54）全绿后 `make seed`；三代种子哈希如上，git 历史
  保留各代产物。

## 2026-10-02 Makefile 清理失效的 VERSION 引用

- VERSION 文件已随清单精简删除（c5eccf0，版本改由 project.toml 提供），
  Makefile 头部 `VERSION ?= $(shell cat $(TOPSRC)/VERSION)` 成为无效
  引用（每次 make 触发一次失败的 cat），已删除该行；全仓库确认
  tools/tests/CI 无其他 VERSION 文件引用。
- 验证：`make` 通过，`make test` 运行语料 63/63。

## 2026-10-02 修复裸调用 SIGBUS：usage() 栈缓冲区溢出

- 缺陷：`cmd/driver.yh` 的 `usage()` 把 10 行用法（566 字节）拼进 512 字节
  栈缓冲，溢出 54 字节砸坏返回地址，函数返回时 PC 未对齐触发 SIGBUS
  （退出码 138）。裸调用、坏参数及全部 4 个 usage 调用点均崩；缺陷已随
  上一版滚入种子 bin/yh，主门从未执行该路径故未发现。
- 修复：`usage()` 改为逐行写入（复用 256 字节缓冲，单行最长约 80 字节），
  消灭"文本总量超过固定缓冲"一类问题，注释标明不可改回整段拼接。
- 回归防护：主门 `native-selfhost.py` 新增 CLI 冒烟探针——裸调用与坏参数
  必须打印完整用法（含末行）并以用法错误码 2 退出。
- 验证：`make` 通过；裸调用/坏参数 exit=2；`make selfhost-native` 通过
  （固定点 12 产物一致、自解析 49 文件、CLI 冒烟 OK、语法反例 29/29、
  运行语料 63/63、modules 17/17、项目用例 54/54）。未滚种子。

## 2026-10-02 IR 并入编译器根项目普通模块

- `compiler/ir/` 取消独立清单：删除 `ir/project.toml`，移除根
  `compiler/project.toml` 的 `[dependencies] ir = { path = "ir" }`；
  `ir` 与 gen/lex/parse/cmd/backend 同为根项目普通模块，`import ir` 由
  本项目层直接解析。原独立项目对「ir 不依赖 gen/parse/backend/cmd」的
  机器强制分层改为约定维持（各设计文档已同步）。
- `tests/modules/build-check.py`：`irverify`/`irfront` fixture 拷入
  `compiler/ir` 源码后合成最小清单（name = `yh_ir`），跨项目依赖解析
  用例保持有效。
- 文档同步：README、compiler/README.md（模块列表与源码规模）、AGENTS.md、
  Makefile 头注释、编译流程重规划（设计/实施方案）、Nanopass 架构。
- 验证：`make` 通过；`make selfhost-native` 通过（cc3→cc4 12 个模块产物
  固定点一致、自解析 49 文件、语法反例 29/29、运行语料 63/63、
  modules 17/17、项目用例 54/54）。未滚种子（bin/yh 保持上一版）。

## 2026-10-02 编译流程重规划 R2a：短路求值切片

- typed SSA 与 arm64 后端接入逻辑或/与/非：`a || b`、`a && b` 降为
  条件块 + 右臂块 + 合流块三段 CFG，短路常量定义在条件块内，合流点
  双前驱 phi；嵌套短路的 phi 第二前驱取降低右臂后的实际汇入块。
  表达式降低（`ast_ir_lower_expr`/`ast_ir_lower_call_expr`/
  `ast_ir_lower_assign_stmt`）改为直接接收 builder，使表达式可以
  创建条件块；新增 `ast_ir_b_cond` 统一条件归一化（整数按非零为真），
  `if`/`for` 条件与短路操作数共用；`!x` 降为与 false 常量的相等比较，
  旧语义层把 bool 结果升为 i32 的差异在 IR 层归一。
- verifier 值编号唯一性检查由前缀扫描改为位图标记：构造器允许块区间
  与编号顺序不同后，前缀扫描在乱序布局下会把当前指令误判为重复。
- 过程中发现并修复三处缺陷（均有语料或自举佐证）：嵌套短路 phi 前驱
  错误（verifier 拒绝 `irfront` 逻辑用例）；循环发现趟 builder 未挂
  类型表导致 fork worker 静默 SIGSEGV（单文件模式不受影响，曾长期
  误导定位）；`b_if` 条件归一化补丁静默未落盘致自举 cc3 的
  `is_hex_digit` 校验失败。另修正语料初版一处测试期望错误
  （`logic_guard(0,1,0)` 应为 100）。
- `irfront` 新增 `logic_guard`（短路/混合优先级/逻辑非 4 组断言）：
  56 个 AST 函数上下文 54 个进入 SSA，仅 call_tick（全局赋值）与
  unsigned_score（负数字面量实参）回退；自举 cc3→cc4 自源函数进入
  SSA 的数量由 5 增至 8 并通过固定点。
- 滚种子前 `make`、`make test`、`make selfhost-native` 通过：语法
  66/66+29/29、运行 63/63、12 个模块产物固定点一致、自解析 49 个
  文件、模块 17/17、项目 54/54。种子后 `make` 与 `make selfhost-native`
  再次通过。种子 SHA-256
  `0a28dd5e89d660bd9b215e78504ff54cb9531c6df6f232a6df1f06503b361864`，
  根 `yh` SHA-256
  `17b5afcdde2cd04da259147d5b6f89fa58e2c412e926a50a514ce3a3dffbbf5c`。
  Linux arm64 汇编交叉组装通过，原生链接/运行尚未验收。
- Apple M1 冻结 25 文件语料各测 20 轮，中位数/p95：无改动 40.8/49.5ms、
  单函数修改 743.5/817.8ms、冷编 2203.0/2765.1ms；汇编/链接调用为
  0/0、1/1、4/1。被修改函数本身进入 SSA（ir=1），冷编进入 SSA 的
  自编函数 5→8；端到端与上一轮噪声范围内持平，未证明提速；无改动
  50ms 中位数目标保持达标，200ms/1s 目标未达到。嵌套循环、for-in、
  switch、goto、负数字面量实参、浮点、聚合与间接调用仍走旧发射路径，
  R2a/R2b 整体未完成。
  详见[短路求值报告](01-finished/yh-编译流程R2a-短路求值-2026-10-02.md)。

## 2026-10-02 Nanopass 风格优化架构方案交付

- 用户确认优化扩展与自举稳定优先；核对当前 SSA、verifier、缓存、lowering 与后端源码，并参考 Nanopass 官方介绍与手册。
- 交付[架构设计](03-design/yh-Nanopass风格优化架构.md)、[分期实施方案](02-plan/yh-Nanopass风格优化架构实施方案.md)及[ADR-0011 草案](adr/0011-yh采用Nanopass风格优化阶段契约.md)；提议复用 typed SSA、建立小 pass/阶段契约，随后迁移 Checked/Core 与机器 IR。
- NP0–NP5 已登记 todo，设计状态为待评审，全部实现任务仍未完成。新增文档的本地链接、代码围栏和空白检查通过。本次只改文档，没有修改编译器、用例或种子，没有执行构建/运行回归。

## 2026-10-02 编译流程重规划 R2a：通用构造器与 break/continue 切片

- 受限的固定形态匹配 lowering 替换为通用递归构造器（新文件
  `compiler/parse/ast_ir_build.yh`）：块表动态增长、合流块先分配后填充、
  `ir_verify` 块指令区间改为「互不重叠且恰好覆盖」的覆盖检查。if/else
  任意嵌套与 else-if 链、条件循环、break/continue、return 与顺序语句
  任意组合进入 typed SSA 并由 arm64 后端发射。
- 循环采用两趟协议：发现趟直接在主 builder 上降低体并回滚指令/phi/块/
  调用计数，收集携带绑定、continue/break 站点数与是否贯穿；真实趟按
  事实预留 header phi 输入（入口 + continue×N + 回边），continue 站点
  回填边输入，break 站点值与条件假边在退出块建合流 phi。发现与真实
  降低执行同一份代码，保证结构精确一致。
- 过程中发现并修复三处缺陷（均有运行语料佐证）：if 臂遍历越界把 else
  与后续语句降入同一块；发现趟独立值编号与主 builder 冲突导致含循环
  函数整体回退；发现趟 local_count 泄漏使体内 let 校验失败。
- `irfront` 新增守卫 break 与 continue 用例：55 个 AST 上下文 53 个进入
  SSA（仅全局赋值 call_tick 与含 `||` 的 unsigned_score 回退），
  `loop_break_guard(10)=3`、`(2)=1`、`loop_skip_odd(5)=13`、`(2)=1` 验证
  break/continue 语义与 phi 合流；函数 IR 缓存精确失效断言改为按
  「修改函数 1 + 已知回退数」计期望。
- 滚种子前 `make`、`make test`、`make selfhost-native` 通过：语法 66/66+29/29、
  运行 63/63、12 个模块产物固定点一致、自解析 49 个文件、模块 17/17、项目 54/54。
  种子后 `make` 与 `make selfhost-native` 再次通过。种子 SHA-256
  `96ef0e6c565de0accdf40b71a1748abb91a7c2e97c4d39d6f2fa9d70718be252`，根 `yh`
  SHA-256 `f02b0eac39467c4c09c37561fa65f84c157adec5c201c876149577d81ff22d82`。
- Apple M1 冻结 25 文件语料各测 20 轮，中位数/p95：无改动 42.4/48.5ms、
  单函数修改 671.7/757.4ms、冷编 1890.7/2132.8ms；与上一轮噪声范围内持平，
  未证明提速；无改动 50ms 中位数目标保持达标，200ms/1s 目标未达到。
  嵌套循环、for-in、switch、goto、`||`/`&&`、浮点、聚合与间接调用仍走旧
  发射路径，R2a/R2b 整体未完成。
  详见[通用构造器报告](01-finished/yh-编译流程R2a-通用构造器与break-continue-2026-10-02.md)。

## 2026-10-02 编译流程重规划 R2a：条件循环切片

- typed SSA 与 arm64 后端接入条件循环 `for cond { 顺序体 }`：四块 CFG
  为「入口→循环头（携带值 phi + 条件）→体（顺序语句 + 回边）→退出」；
  体内被赋值的外部绑定在循环头建双前驱 phi，入口输入创建时填写、回边
  输入在体降低后回填，循环后视角恢复为 header phi 值。体内 `let` 每次迭代
  重新定义不参与携带；携带绑定去重上限 16。顺序语句检查/降低抽取为
  `ast_ir_straight_scan`/`ast_ir_straight_emit` 共享辅助，直线行为逐字保持；
  void 函数的循环（裸 return 或隐式结束）同样受支持。体内嵌套控制流、
  break/continue、for-in 与 `for {}` 仍回退旧发射器。
- `irfront` 新增 5 个循环函数：53 个 AST 上下文 51 个进入 SSA，运行结果
  验证计数累加（10）、体内 let（6）、尾随语句继续使用携带值（108）与
  循环调用驱动（3）；汇编断言 `bl log_unit` 三次，`yh check` 仍为 0 个
  IR 函数。
- 滚种子前 `make`、`make test`、`make selfhost-native` 通过：语法 66/66+29/29、
  运行 63/63、12 个模块产物固定点一致、自解析 48 个文件、模块 17/17、项目 54/54。
  种子后 `make` 与 `make selfhost-native` 再次通过。种子 SHA-256
  `fcd79c9f81ec3478e8f448f5e8f180318f3d54b34ef169f7c05f4ad6e584665a`，根 `yh`
  SHA-256 `77c4f336a025a11d6b91d337d306176f77f87ec9add79d4da07c903c44d53447`。
  Linux arm64 汇编交叉组装通过，原生链接/运行尚未验收。
- Apple M1 冻结 25 文件语料各测 20 轮，中位数/p95：无改动 40.0/47.0ms、
  单函数修改 706.4/760.7ms、冷编 1880.1/2151.9ms；汇编/链接调用为 0/0、1/1、4/1。
  与上一轮在噪声范围内持平，本切片未证明编译提速；无改动 50ms 中位数目标
  保持达标，200ms/1s 目标未达到。循环体内嵌套控制流与 break/continue 需要
  动态块构造器，R2a/R2b 整体未完成。
  详见[条件循环报告](01-finished/yh-编译流程R2a-条件循环-2026-10-02.md)。

## 2026-10-02 编译流程重规划 R2a：void 调用与语句级调用切片

- typed SSA、verifier 与 arm64 后端接入 void 返回调用与语句级调用：表达式语句
  （顺序路径与 if/else 分支块）接受已检查的直接调用，void 返回发射无结果 CALL
  并保留副作用与求值顺序，标量返回可被语句丢弃；verifier 值编号改为允许稀疏
  （定义数不超过上界，逐指令范围与唯一性检查不变）。void 函数本身支持裸
  `return;` 与隐式结束，空函数为单块零指令 CFG，后端允许 void 返回与零指令函数。
- `irfront` 新增 5 个函数：48 个 AST 上下文 46 个进入 SSA，运行结果覆盖裸
  return、隐式结束、丢弃标量结果、顺序双调用与分支块「调用 + 赋值」phi 合流；
  汇编断言 `bl log_unit` 两次、`bl log_noop`/`bl discarded_result` 各一次，
  `yh check` 仍为 0 个 IR 函数。`ircallmodule` 的 api 新增公开 void 函数，
  覆盖跨模块 void 调用（SSA 函数数 3→4）、精确重链接与退出码 41。
- 滚种子前 `make`、`make test`、`make selfhost-native` 通过：语法 66/66+29/29、
  运行 63/63、12 个模块产物固定点一致、自解析 48 个文件、模块 17/17、项目 54/54。
  种子后 `make` 与 `make selfhost-native` 再次通过。种子 SHA-256
  `ab1f229f2395a69c7c9e52f9d517b54e64bd8f65c121e81d1b764a9b4baf0ea7`，根 `yh`
  SHA-256 `d261e9b24bfb33cfac4b1662956d67e6492a5316ea63d084eca72eaf79727911`。
  Linux arm64 汇编交叉组装通过，原生链接/运行尚未验收。
- Apple M1 冻结 25 文件语料各测 20 轮，中位数/p95：无改动 40.3/51.3ms、
  单函数修改 748.5/808.6ms、冷编 1963.9/2135.9ms；汇编/链接调用为 0/0、1/1、4/1。
  与上一轮在噪声范围内持平，本切片未证明编译提速；无改动 50ms 中位数目标保持
  达标，200ms/1s 目标未达到。void 分支合流、循环、switch、goto 与间接/浮点/
  聚合/变参调用仍走旧发射路径，R2a/R2b 整体未完成。
  详见[void 调用报告](01-finished/yh-编译流程R2a-void调用与语句级调用-2026-10-02.md)。

## 2026-10-02 编译流程重规划 R2a：直接调用 SSA 切片

- typed SSA、verifier、稳定序列化及双 arm64 后端接通固定参数整数/布尔直接调用；`irfront` 覆盖嵌套、零/九参和副作用顺序，`ircallmodule` 覆盖跨模块实现修改后的精确汇编/重链接。`irverify` 覆盖错型、支配关系与损坏缓存反例。
- 滚种子前 `make`、`make test`、`make selfhost-native` 通过：语法 66/66+29/29、运行 63/63、12 个模块产物固定点一致、自解析 48 个文件、模块 17/17、项目 54/54。种子后 `make` 与 `make selfhost-native` 再次通过；种子 SHA-256 `2232b0ada585e24967d60416e10e6809464f9a67970e307d9a49f43f2d685892`，根 `yh` SHA-256 `4cf8e26837dc5c8625f83b30e01a9c764bc866e06ea7706454c4d631c9c9b47d`。Linux arm64 汇编交叉组装通过，原生链接/运行尚未验收。
- Apple M1 冻结 25 文件语料各测 20 轮，含汇编/链接，中位数/p95：无改动 37.7/54.4ms、单函数修改 728.3/1112.2ms、冷编 2029.0/2371.4ms。旧种子同轮基线分别为 38.9/46.0ms、636.2/711.9ms、1686.0/1776.4ms，本切片未带来可证实的提速；200ms/1s 目标仍未达到。自编项目 528 个函数 AST 上下文仅 5 个进入 SSA，R2a/R2b 整体仍未完成。详见[直接调用 SSA 报告](01-finished/yh-编译流程R2a直接调用SSA-2026-10-02.md)。

## 2026-10-02 编译流程重规划 R2a：整数二元运算切片

- typed SSA 和 arm64 后端新增同类型整数除法、取模、位与/或/异或、左右移位；按有符号性选择指令，默认简化器仅折叠非异常常量表达式。IR 序列化升至 v3、函数缓存键升至 v7；未支持的函数仍走旧发射器。
- `irfront` `.yh` 项目运行用例覆盖负数除法与余数、无符号边界、左右移位、零除数、常量折叠；`irverify` `.yh` 项目拒绝错型运算。项目验收 53/53，`make test` 语法正例 66/66、反例 29/29、运行 63/63，滚种子前后 `make selfhost-native` 均通过（12 个产物固定点、44 个源码自解析、模块 17/17、项目 53/53）；种子后 `make` 通过。
- Apple M1 冻结 25 文件、13,338 行语料 20 轮中位数/p95：无改动 34.3/42.1ms，单函数修改 640.7/718.8ms，冷编 1,695.9/1,976.5ms。无改动低于 50ms，单函数 200ms 与冷编 1s 目标未达。编译器自编项目的 512 个函数 AST 上下文仅 1 个进入 SSA；这次扩展不构成对编译速度提升的证明。
- Darwin arm64 种子 SHA-256：`d47bfeeba494fb12a447736e945f6e377d490b23ab841158e62ae358bdecf113`；根 `yh` SHA-256：`8d981521a9260302091f49ae63711e665ef1c12f20c5457172780d014945573f`。R2a、R2b 及 R0–R6 总体验收继续进行。详见[整数二元运算报告](01-finished/yh-编译流程R2a整数二元运算-2026-10-02.md)。

## 2026-10-02 编译流程重规划 R1：单文件 yh check

- 新增 `yh check <file.yh>`，执行词法和完整单文件语义检查，允许库文件没有 `main`；未声明标识符返回失败。原有 `yh check [module]` 项目入口保持不变。
- 在 `tests/modules/fixtures/` 增加有效/无效 `.yh` 语料；自举门验证检查不产生文件、也不调用 PATH 中的 gcc/clang。修正初始化顺序，保证单文件入口先读源、分配语义表，再词法分析。
- 验证：`make test`（语法正例 66/66、反例 29/29、运行 63/63）、滚种子前后 `make selfhost-native`（12 个产物固定点、44 个源码自解析、模块 17/17、项目 53/53）、种子后 `make` 与 `git diff --check` 全通过。Darwin arm64 种子 SHA-256：`268513c5cfff1af60a16754e0d957ae0e3aadb99cc3758b686e39d21e2ae2f22`；根 `yh` SHA-256：`2fcffbb90d8be4713796ccdb8da713ee549b3ba343cfcaceb3b1a190bcd61040`。
- 本条记录不代表 R1 完成；完整 AST/CheckedFunction 分离、一次解析与任务私有上下文仍待实现。详见[单文件 check 报告](01-finished/yh-编译流程R1单文件check-2026-10-02.md)。

## 2026-10-01 编译流程重规划 R2a：SSA arm64 比较运算切片

- SSA 指令表新增不等及有符号/无符号顺序比较，序列化格式与函数 IR 缓存键升版；arm64 后端从操作数类型选择条件码，默认简化器折叠整数常量比较。`irfront` 覆盖六种比较真假、`u32` 最大值边界及常量比较折叠；20 个 lowering 函数均由 SSA 后端输出，程序退出码为 230。SSA 值临时各占独立栈槽；不支持的函数回退到旧 emitter。
- 修复 fork worker 诊断路径悬空：路径原指向可扩容名字池，池增长后偶发 SIGSEGV。现在 worker 解析前把路径复制到固定缓冲；模块 `.yh` 回归重复构建 8 次，额外 100 次独立构建均保留预期源位置诊断。
- 验证：`make test` 通过（语法正例 66/66、反例 29/29、运行 63/63）；滚种子前后 `make selfhost-native` 通过（12 个模块产物固定点、44 个源文件自解析、模块 17/17、项目 53/53）；种子后 `make` 通过。
- Apple M1 冻结语料 20 轮（中位数/p95）：无改动 36.2/44.3ms，单函数变化 669.5/708.7ms，冷编 1,851.3/2,107.0ms；汇编/链接调用为 0/0、1/1、4/1。无改动目标 50ms 达标；单函数目标 200ms 和冷编目标 1s 未达标。冷编 378 个函数上下文只有 1 个进入 SSA 子集，单函数变化为 0 个。
- Darwin arm64 种子 SHA-256：`27ed8a4c2168076c3e713bf3cd3cae63a96709748acfb514813ab508dbea84a4`；根 `yh` SHA-256：`6870f27cf8afcb95963220ad7a427d3ecc812a3ff0985c41c8113961d0eb8a2a`。
- R2a 与 R2b 整体仍未完成：当前只接通项目模块的窄 lowering 子集；还需完整受检函数、更多 CFG/调用/内存语义、单文件共用后端、平台 ABI 验收、真正线程池与完整函数级缓存。

## 2026-10-01 编译流程重规划 R3：自有运行时与固定点迁移

- arm64 的 `malloc/free/memcpy/strlen` 使用自有汇编入口；Darwin 映射调用审核后的 `mmap/munmap`，Linux arm64 发射对应 syscall。`printf` 已支持 `%%`、整数、字符串和字符，使用分块缓冲及 OS `write`，尚未支持宽度、精度、浮点和 locale。运行时入口只按模块内调用/取址发射，纯程序不会带入映射或输出 OS API。`.yh` 用例覆盖分配、字节函数值、精确格式化输出、长字符串刷新与无运行时调用的导入裁剪。
- 滚种子前后 `make test`、`make selfhost-native` 通过；语法 66/66、反例 29/29、运行 63/63、自解析 43 个文件、模块 17/17、项目 52/52，候选 cc3→cc4 的 10 项产物固定点一致。`tests/selfhost/runtime-memory.py` 确认普通程序与自编编译器不导入 `malloc/free/memcpy/strlen/printf`；Linux arm64 汇编交叉组装无未定义符号。
- Apple M1 冻结语料 25 文件、13,338 行，20 轮中位数/p95：无改动 32.2/37.9ms、函数修改 610.8/643.4ms、冷编 1,686.0/1,824.0ms；汇编/链接调用为 0/0、1/1、4/1。50ms 无改动目标达到；200ms 函数修改和 1s 冷编目标仍未达到。新编译器 SHA-256 `e7ab60114f66b44208abd0aab1bdc037501df15600cac070466deb0e73ef8afd`。
- Darwin arm64 种子 SHA-256：`6498b7282a0d00115912e573a08823de3371024d25c0496b2260bd27a40ce344`。Linux 原生运行、线程 API 和完整导入验收尚未完成；外部汇编/链接仍未替换，R3 与 R0–R6 总体验收继续进行。详见[自有运行时与性能报告](01-finished/yh-编译流程R3自有分配器与性能-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R2b：缓存指纹分块与阶段计时

- 缓存内容指纹改为固定小端 8 字节块混合并升版本，使旧 manifest 自动失效；改用对齐的原生 64 位读取后，`tokenreplay` 新增尾部余数为 7 的 `.yh` 回归源。`yh build --stats` 增加项目装载、模块调度、对象缓存/汇编、最终链接决策和构建内总耗时。Darwin 计时通过允许清单中的 libSystem `clock_gettime` OS API，Linux arm64 使用 syscall；普通构建输出不变。
- Apple M1 冻结 25 文件语料 20 轮中位数/p95：无改动 32.8/37.3ms、单函数体变化 663.2/753.4ms、冷编 1,734.1/1,900.6ms，含真实汇编/链接。无改动内部阶段合计 27.2ms，已达到 50ms 目标；单函数 200ms 与冷编 1s 目标仍未达到。
- `make test` 全过：语法 66/66、反例 29/29、运行语料 63/63；滚种子前后 `make selfhost-native` 均全过：固定点 10 个模块产物一致、自解析 43 个源文件、模块 17/17、项目 52/52。`make seed` 后再次 `make` 与自举门通过；`git diff --check` 和文档本地链接检查通过。
- 根 `yh` SHA-256：`c2fe874ad0dc324135e1441224e4095e64eb1c1f3a865ed6b0e18dd05bf4450d`；Darwin arm64 种子 SHA-256：`8ac9b924fcad79450b4c2dab8bc003d71b554a866f77ccdb597db9c2c01085ee`。
- 完整阶段数据见[缓存指纹与阶段计时报告](01-finished/yh-编译流程R2b缓存指纹分块与阶段计时-2026-10-01.md)。R2b 线程池/函数级完整 check-IR 缓存、自有汇编链接及 R0–R6 总验收仍在实施。

## 2026-10-01 编译流程重规划 R2b：fork/COW 前端快照复用

- 模块 worker 改为 fork 父进程中已验证的项目与词法快照，通过写时复制隔离可变语义状态；worker 不再 exec 后重载项目和重做全项目词法分析。声明索引延迟至待重建模块，缓存命中构建不再执行声明解析。
- 更新 `.yh` 计数回归：首轮只建立一次项目索引，热缓存构建确认语法/声明索引次数为 0、无 worker；provider/consumer 与菱形 DAG、失败无链接等原有并行语料继续通过。
- 验证：`make`、`make test`、`make selfhost-native` 通过；语法 66/66、反例 29/29、运行 63/63、模块 17/17、项目 52/52、固定点 10 个模块产物、41 个源文件自解析。
- Apple M1 冻结 25 文件语料 20 轮（中位数/p95）：无改动 109.6/140.7ms、函数体变化 757.0/903.1ms、冷编 1,812.6/1,878.1ms；汇编/链接调用 0/0、1/1、4/1。速度目标 50/200/1,000ms 均未达到；函数修改仍捕获 80 个 AST 函数上下文，真正线程池与完整函数级 check/IR 缓存待完成。
- 详见[fork 快照复用报告](01-finished/yh-编译流程R2b-fork快照并行worker-2026-10-01.md)。R0–R6 继续实施。

## 2026-10-01 编译流程重规划 R3：自有 memcpy/strlen

- arm64 后端为 `memcpy` 与 `strlen` 发射本地运行时入口，支持直接及函数值调用；新增 `.yh` 用例覆盖零长、块边界、返回指针、UTF-8 字节长度和非对齐字符串。普通程序与自编编译器均不再导入这两个 C 服务，Linux arm64 对象交叉组装成功且无未定义符号。
- 验证：`make -B`、`make test` 与 `make selfhost-native` 通过；语法 66/66、反例 29/29、运行 63/63、模块 17/17、项目 52/52。根 `yh` SHA-256 `78e36cb3d64d2c81a21ef26ccdb21135fbf164fd22517240d56d980e4cba28c7`；Darwin arm64 种子 SHA-256 `40f4ae0bd8120068deb374d8dde30f90d4b86431210aff5b9be40cb978d47f48`。
- M1 冻结语料 20 轮中位数/p95：无改动 105.9/129.8ms，改单函数 774.5/878.5ms，冷编 1,952.6/2,173.9ms；50/200/1,000ms 目标均未达成。详细数据见[自有字节字符串运行时报告](01-finished/yh-编译流程R3自有字节字符串运行时-2026-10-01.md)。`malloc/free`、格式化/I/O/退出、线程 API、Linux 原生验证与自有汇编/链接仍未完成，R3 和 R0–R6 整体继续实施。

## 2026-10-01 编译流程重规划 R3：项目目录枚举 OS API

- 项目扫描移除 `/bin/ls`。Darwin arm64 通过 `getattrlistbulk` 读取目录项；Linux arm64 通过目标专属 `linux_syscall6` intrinsic 调用 `openat/getdents64/close`，并为函数指针保留本地 syscall stub。公共扫描器复制本轮拥有的文件名与类型、按字节序排序，再递归扫描。
- `.yh` 项目矩阵覆盖空格、引号、非 ASCII 与换行文件名、隐藏项过滤及超过 512 项的目录；并验证 Darwin API 和 Linux syscall 的目标隔离、直接调用与函数值调用。
- 滚种子前后 `make test`（语法正例 66/66、反例 29/29、Darwin 运行 63/63）和 `make selfhost-native` 全通过；相邻两代 10 个模块产物一致、39 个源码自解析、模块 17/17、项目 52/52。`make -B` 与 `git diff --check` 通过。
- Darwin 宿主完成 Linux arm64 目标语义构建；生成汇编经 `clang -target aarch64-linux-gnu` 组装为 ELF，`nm` 确认 syscall 函数符号为本地定义。当前宿主不是 Linux，尚未做 Linux 原生运行验收。
- `make seed` 更新 Darwin arm64 种子 SHA-256 为 `8f4e34b1db3a7922f63a424fa3972011bb352e1a41bc6945dbd5b643879713ea`；滚种子后根 `yh` SHA-256 为 `693d454c7cb6cdd9682b4bd5db52532072a0dd89a28da5cbf8660cdde8b9a1bf`。
- 20 轮 Apple M1 阶段测量（目录 API 完成后、清理无用 helper 前；中位数/p95）：无改动 106.4/117.7 ms、函数体变化 756.1/826.3 ms、冷编 2,051.9/2,287.8 ms。50/200/1,000 ms 目标均未达成，此数据作为阶段基线。
- 详见[目录枚举 OS API 报告](01-finished/yh-编译流程R3目录枚举OSAPI-2026-10-01.md)。Linux 原生运行、线程 API、自有 runtime 与通用 C 导入审计未完成；汇编和链接仍调用系统工具，R3 与 R0–R6 整体仍在实施中。

## 2026-10-01 编译流程重规划 R3：直接从入口读取环境向量

- 编译器入口扩展为 `main(argc, argv, envp)`，并在启动时保存只读的 OS 环境向量；`PATH` 与 `YH_STDLIB` 直接从 `envp` 查找，删除 `/usr/bin/printenv` 子进程。普通 yh 程序的入口语义也接受第三个 `envp **char` 参数。
- 新增 `envp-api` `.yh` 项目用例检查普通程序收到 `YH_ENV_TEST=present`；既有 PATH worker 定位与 YH_STDLIB 回归验证编译器自身读取环境的路径。
- 验证：滚种子前后 `make test` 与 `make selfhost-native` 全通过；语法 66/66、反例 29/29、运行 63/63、模块 17/17、项目 48/48，固定点 10 个模块产物一致、自解析 36 个源文件。`make seed` 后 `make -B` 与滚种子后主门通过。
- Darwin arm64 种子 SHA-256：`a99fceeb2cc4e8483a7871d6b7406f8a62de666d3dfc87d43701da7aac3252ae`；根 `yh` SHA-256：`c588cd670c344d4135080992ab2cf9d8a0f53b21662087ce7b64eb42f14a3609`。
- 当前仍由 `/bin/ls` 枚举项目目录，最终汇编/链接依赖系统工具。`nm -u yh` 仍列出 `_malloc`、`_free`、`_memcpy`、`_strlen` 等通用 C 服务；完整导入清单、R3 自有 runtime 与 Linux arm64 验证仍待完成。本次只在 Darwin arm64 宿主验证。
- 详见[环境向量迁移报告](01-finished/yh-编译流程R3环境向量-2026-10-01.md)。R3 与 R0–R6 整体仍在实施中。

## 2026-10-01 编译流程重规划 R3：输出捕获、目录 OS API 与严格自举

- 项目目录与环境查询从 shell 重定向迁到 `fork/execvp`、`open/dup2` 和 argv；捕获文件标志按宿主 OS 选择，不受 `-target` 影响。项目/临时目录创建改用 `mkdir` OS API 和逐段 `mkdir -p` helper。
- 自举脚本不再主动传 `--legacy-system`，新种子按默认隐藏 `system` 的配置编译；旧种子仍以其旧默认行为构建。
- 新增 `mkdir-api` `.yh` 用例，覆盖首次创建与重复创建；交叉目标项目检查覆盖宿主文件标志。目录枚举与环境查询仍依赖外部 `ls` / `printenv`，系统汇编器、链接器和 runtime 导入审计仍未完成。
- 验证：滚种子前后 `make test`（语法 66/66、反例 29/29、运行 63/63）与 `make selfhost-native` 全通过；固定点 10 个模块产物一致、自解析 36 个源码、模块 17/17、项目 47/47。`make seed` 后 `make -B` 成功；`git diff --check` 通过。
- Apple M1 冻结语料 20 轮（中位数/p95）：无改动 135.1/161.4 ms、函数体变化 790.3/845.6 ms、冷编 2,035.9/2,275.0 ms。50/200/1,000 ms 目标仍未达成；完整计数和旧语料兼容配置说明见[实施方案 §6](02-plan/yh-编译流程重规划实施方案.md)。
- Darwin arm64 种子 SHA-256：`fadc3f00bc57528e1aa9f3ed7aebda34ce0b48636de257a3c362a2c076d0989c`；强制重建根 `yh` SHA-256：`ddbf9823389d66c340819d5bc19377b3e007f99a9de0517133a225fb4dfc4ed8`。
- 详见[输出捕获与 OS 目录 API 报告](01-finished/yh-编译流程R3输出捕获与目录OSAPI-2026-10-01.md)。R3 与 R0–R6 总体仍在实施中。

## 2026-10-01 编译流程重规划 R3：兼容配置与显式进程调用切片

- 默认 prelude 不再隐式登记 `system(cmd)`，`--legacy-system` 显式开放迁移期兼容接口；配置身份加入模块、IR 与链接缓存键。`.yh` 项目覆盖默认拒绝、兼容 build/check/run 和模式切换缓存隔离。
- 编译器调用汇编器、链接器、构建目录创建和运行目标程序改为 `fork/execvp/waitpid` 显式 argv；自举启动器识别新旧种子。目录/环境查询仍依赖 shell，R3 尚未完成。
- 验证：`make`、`make -B`、`make test`（66/66、29/29、63/63）和滚种子后的 `make selfhost-native`（固定点、36 源文件自解析、并发/缓存/check 隔离、模块 17/17、项目 44/44）通过；`git diff --check` 通过。
- Darwin arm64 种子 SHA-256：`853fda71a1b1be87e70590ffc38b5be3bae673d7bcd2e8ff5f02fd6600ca5a78`；根 `yh` SHA-256：`25cd492e39b41662d3ca0bdcd4596500dfe6a725f965b0bbad9d59ce7750ed4f`。
- 详见[兼容配置与显式进程调用报告](01-finished/yh-编译流程R3兼容配置与显式进程调用-2026-10-01.md)。目录枚举、环境 API、自有 runtime、线程服务与自有汇编/链接仍未完成。

## 2026-10-01 编译流程重规划 R2a：分支赋值与 phi 合流

- SSA 新增受限四块分支 lowering：分支前初始化的标量 `let` 可与参数一起在 `if/else` 块内赋值；合流块对变化绑定生成双前驱 phi。原有分支直接 return 路径保留。语句 lowering/phi 缓冲辅助代码拆入 `compiler/parse/ast_ir_control.yh`；函数缓存键升至 v5。
- `.yh` 项目用 `branch_update` 验证一侧修改、一侧沿用参数，用 `branch_local` 验证局部变量两侧写入；缓存中两函数均有四块 CFG 和双输入 phi，运行退出码 219。build/check 函数上下文、IR 缓存命中/精确失效/损坏重建通过。
- 验证：`make test`（66/66、29/29、63/63）、`make selfhost-native`（10 个固定点产物、35 个源文件自解析、模块 17/17、项目 42/42）；滚种子后 `make -B` 与再次 `make selfhost-native` 通过，`git diff --check` 通过。
- Apple M1 冻结 25 文件语料 20 轮：无改动 187.9/233.0 ms、函数变化 903.0/953.1 ms、冷编 2,233.2/2,297.0 ms（中位数/p95）；汇编/链接 0/0、1/1、4/1；峰值 RSS 15.1/51.0/50.9 MiB。50/200/1,000 ms 暂定目标均未达到，详见[分支赋值与 phi 报告](01-finished/yh-编译流程R2a分支赋值phi-2026-10-01.md)。
- 根 `yh` SHA-256：`8f69a0f745cde11076b446c1e97e9732b5a5bcb8948bd11a3c4a951e34b013f7`；Darwin arm64 种子 SHA-256：`778c2b5ef3d91c18a52e4255333b7976b8d6a8b810744e25581fccafed80d36b`。
- 当前 lowering 仍不驱动后端；循环、嵌套控制流、复杂赋值、完整函数级 check、真正线程池、平台后端和自有汇编/链接待实施。

## 2026-10-01 编译流程重规划 R2a：顺序局部定义与赋值

- SSA lowering 新增按声明顺序处理的单绑定、有初值标量 `let` 和同类型 `=`/`+=`/`-=`/`*=`；参数与局部通过函数私有映射读取当前 SSA 值，赋值产生新定义并更新映射。其他复合/聚合赋值、前向引用与复杂局部控制流仍走旧发射器。
- 函数 IR 缓存键升至 v4，包含函数所有表达式节点语义事实与绑定类型/布局。`.yh` 项目验证参数/局部读写、连续复合赋值、局部间读取、同名绑定隔离、局部实现变化只失效一个缓存及损坏缓存重建；生成程序运行结果为 115。
- 验证：`make test`（语法 66/66、反例 29/29、运行 63/63）、模块项目矩阵 42/42、`make selfhost-native`（10 个固定点产物、34 个源文件自解析、模块 17/17、项目 42/42）通过；`make seed` 后 `make -B` 和再次 `make selfhost-native` 通过。
- Apple M1 冻结语料 5 轮测试：无改动、函数体变化、冷编中位数/p95 为 188.1/213.8、873.0/942.3、2,222.9/2,384.1 ms；汇编/链接调用为 0/0、1/1、4/1。样本少于正式 20 轮，不能作为性能目标验收，三项中位数目前均高于暂定目标。
- Darwin arm64 种子 SHA-256：`4fe6932658f0d8279f39491b824acb64a9fd4f661a8f4bcadfd266d4a0b73715`；强制重建后的根 `yh` SHA-256：`1bf1917315604fccc9ccfcb2bff2f991945d0de2dd6bc35013a12bdb36965b35`。
- IR 仍只覆盖受限函数子集且不驱动汇编后端；复合/聚合赋值、分支/循环局部、调用、函数 check 缓存、真正线程池、双 arm64 后端和自有工具链仍未完成。

详见[顺序局部定义与赋值报告](01-finished/yh-编译流程R2a顺序局部SSA定义-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R1：函数 AST 上下文范围切片

- 新增函数级只读 `AstFunctionContext`，保存 AST 四类 arena 范围和源声明身份；模块声明建立文件基址索引，避免上下文构造逐函数线性搜索。
- 上下文 verifier 检查表达式、语句、边和绑定没有跨函数引用。SSA lowering 与参数检查改为消费函数切片，指令临时容量按函数表达式规模计算，IR 缓存语义键版本升到 v3。
- `irfront` `.yh` 项目新增两个同名局部绑定函数，build/check 都捕获 10 个函数上下文；check 保持 `ir_functions=0`，程序结果不变。
- `make`、`make test`（66/66、29/29、63/63）、模块项目矩阵 42/42、`make selfhost-native`（34 个源文件自解析、10 个模块产物固定点）及滚种子后的 `make -B` / 自举门均通过；`git diff --check` 通过。
- 两轮 Apple M1 初测中位数/p95：无改动 199.5/200.8 ms、函数体变化 933.3/935.4 ms、冷编 2,225.6/2,233.4 ms；样本过少，不据此判断速度变化。详见[函数 AST 上下文报告](01-finished/yh-编译流程R1函数AST上下文范围-2026-10-01.md)。
- 根 `yh` SHA-256：`e9a2f94203fe12f04239417e2b6d3166214e337125d1469f7bb0cb3be9a544e4`；Darwin 种子 SHA-256：`504005f98f0666f02d7ced0faa0dcac00bafe77cb8c8f4a0a115a59275208635`。
- 此描述符尚未隔离 parser/semantic 全局，也没有让函数任务线程安全；线程池与完整任务私有状态仍未完成。

## 2026-10-01 编译流程重规划 R2b：接口就绪并行调度过渡切片

- 构建协调器以显式 argv 启动最多四个进程 worker。构建会话接口使用进程专属后缀并原子发布，依赖方可在 provider 私有函数/汇编结束前开工；缓存命中读取已验证的持久接口。
- worker 全部成功后才原子提交持久接口与 manifest；失败停止派发、回收 worker、清理会话文件并跳过最终链接。统计输出 `workers_peak`、`iface_early`。
- 新增 `.yh` scheduler 项目语料，覆盖 provider/consumer 与菱形依赖 DAG、接口提前推进、失败无链接、PATH 启动及含空格/单引号的路径；实测调度峰值分别为 2 与 3，接口提前推进计数分别为 1 与 3。
- 验证：`make`、`make test`（66/66、29/29、63/63）、模块项目门 42/42、`make selfhost-native`、滚种子后的 `make` 和再次自举门、Python 语法检查与 `git diff --check` 通过。
- Apple M1 冻结语料 20 轮（中位数/p95）：无改动 196/354 ms、函数体变化 905/975 ms、冷编 2,278/2,642 ms；汇编/链接调用 0/0、1/1、4/1。50/200/1,000 ms 目标仍未达成。根 `yh` SHA-256：`26a7838a6727492288223bba448ea9a1b03243f07c905d5dca1c51c7a5e19687`；macOS arm64 种子：`51204b7025f7269428c046738d79f344107944006b5c7250a51602eff59b3f36`。
- 这是进程 worker 迁移桥。线程池、完整任务私有状态、函数级 check/IR、文件对象及同项目并发提交仍未完成；系统依赖和自有工具链目标也仍待实施。

详见[接口就绪并行调度报告](01-finished/yh-编译流程R2b接口就绪并行调度-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R2a：标量参数 SSA 定义与读取

- `compiler/ir/ssa.yh` 新增 `IR_OP_PARAM`。函数参数由入口块中 phi 后、其他指令前的连续
  `PARAM` 定义表示，参数序号必须从零连续；verifier 拒绝错序、越出入口前导区及伪造操作数。
  序列化仍使用既有指令字段，无需扩张 IR 文件格式。
- `ast_ir.yh` 现在可将标量参数引用降低为对应 SSA 值，覆盖受限直接 return、`+ - * ==` 表达式
  和既有双臂 if/else return；缓存键版本升级，并加入函数签名参数数量、类型及目标布局事实。
- 新增 `.yh` 参数函数 `from_param`，由入口实际调用并验证返回 58；IR verifier 用例检查有效定义、
  非连续序号和非法操作数字段。项目验收现含 7 个 SSA 缓存函数，覆盖冷写、无关入口修改全命中、
  单函数失效和损坏缓存重建。
- 验证：`make`、`make test`（语法 66/66、反例 29/29、运行 63/63）、
  `make selfhost-native`（10 个模块产物固定点、32 文件自解析、模块 17/17、项目 36/36）通过；
  更新种子后 `make -B` 与再次 `make selfhost-native` 通过。`git diff --check` 和 Python 语法检查通过。
- 根 `yh` SHA-256：`bac264cdd78be400907136cc6fbaa1b0aefdce088930255bcabec8fd08aa4f5f`；
  macOS 种子 SHA-256：`6f03b306a525e86463c8e6eeaa4978632cf5057fbbe961064443f2eeefe96bbf`。
- 当前参数 IR 只供 verifier/缓存迁移验证，尚不驱动目标后端；局部变量赋值、调用 lowering、完整
  check 缓存、线程池、接口就绪调度、自有汇编/链接及最终速度目标仍未完成。

详见[标量参数 SSA 切片报告](01-finished/yh-编译流程R2a标量参数SSA-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R2b：受限函数 SSA IR 缓存

- `ast_ir.yh` 为当前受限 lowering 子集增加持久 IR 缓存。键包含正在运行的编译器二进制指纹、
  目标方言、函数源码和 lowering 读取的表达式类型事实；缓存包络校验键与内容校验值，
  IR 解码再执行 verifier。内部模块 worker 显式继承父构建的 `-target`，交叉目标不会借用宿主默认值。
- `irfront` `.yh` 项目回归覆盖首次缓存写入、修改不进入 IR 的入口函数后六函数全命中、
  修改 `sum` 后只有一个 IR miss、损坏缓存拒绝并重建；`yh check` 仍 `ir_functions=0`，
  不读取或写入常规 IR 缓存。
- 验证：`make`、`make test`（语法 66/66、反例 29/29、运行 63/63）、
  `make selfhost-native`（固定点 10 个产物、32 文件自解析、并发/check/缓存/项目门 36/36）、
  滚种子后的 `make -B` 与再次 `make selfhost-native` 通过。`git diff --check` 与 Python 语法检查通过。
- Apple M1 冻结语料 20 轮：无改动 192/223 ms、单函数体变化 980/1,104 ms、冷编
  2,345/2,507 ms（中位数/p95）；汇编/链接调用 0/0、1/1、4/1。当前冻结语料没有受限
  lowering 可处理的函数（`ir_functions=0`），这些测量不证明函数 IR 缓存提升端到端速度，
  总目标 50/200/1,000 ms 仍未达到。根编译器 SHA-256 为
  `fe9a44ddc9b074f838710a3c2990a9a324a879cc0b6cc877e5b12e0c2bba70f2`，Darwin 种子 SHA-256 为
  `36ab04c1e61c21ef1c8c12ce2be3e79dd56534af72d05c4240de08742c336c1e`。
- 这只是少量函数 lowering 的 IR 缓存，不包含函数 check 结果，也不驱动汇编；完整受检语义键、
  线程池、接口就绪并行、文件级对象、原子提交和自有工具链仍在 R1/R2b–R6 待办。

详见[函数 IR 缓存切片报告](01-finished/yh-编译流程R2b函数IR缓存切片-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R2a：首个分支 CFG 接入 AST→SSA

- 扩展 `compiler/parse/ast_ir.yh`，在已有常量单 return lowering 外接入无参数双臂
  `if/else` 函数：条件表达式进入入口块，then/else 各形成独立返回块，运行 SSA 简化和
  verifier。范围刻意限制为每个分支块只有一个直接 `return`；其他函数仍由旧发射器负责。
- `tests/modules/projects/irfront/main/main.yh` 增加比较条件和 true/false 分支函数，并由
  程序入口实际执行两条路径；项目门要求至少 6 个 lowering 函数、`yh check` 的
  `ir_functions=0`，结果退出码为 50。
- 验证：`make`、`make test`（语法 66/66、反例 29/29、运行 63/63）、
  `make selfhost-native`（10 个模块产物固定点、32 文件自解析、所有模块与项目门 36/36）、
  滚种子后的 `make -B` 与再次 `make selfhost-native` 全通过；`git diff --check` 通过。
- Apple M1 冻结语料 20 轮：无改动 190/225 ms、单函数体变化 985/1,079 ms、冷编
  2,353/2,550 ms（中位数/p95）；对应汇编/链接次数为 0/0、1/1、4/1。目标 50/200/1,000 ms
  尚未达到。详见[分支 CFG 接入报告](01-finished/yh-编译流程R2a分支CFG-2026-10-01.md)。
- 新种子 SHA-256：`3ab21aa7fb74448cfd4f0dcf5563f6ae60643581de01fa6c8c129cac25a6d0e2`；
  当前根 `yh` SHA-256：`7e3f780b89cbe201997032730cff4ebb50ad967ad92a1f6f96c2cf23277e7eb6`。
- 这仍是窄迁移探针：IR 不持久化、不驱动后端，局部变量、循环、合流 phi、调用、线程池、
  函数级缓存与自有汇编/链接仍未实现。

## 2026-10-01 编译流程重规划 R2a：首条 AST→SSA 主路径

- 根 compiler 项目显式依赖独立 `compiler/ir` 子项目。普通 build 与 `yh check` 都在解析
  期间收集并校验表达式/语句/声明 AST；pass1 后绑定函数签名，确保 lowering 使用稳定声明身份。
- 普通 build 在 AST 校验后，将无参数、单个直接 `return` 的常量整数/布尔表达式构造成目标隔离
  的 typed SSA 函数，并运行低成本简化及 verifier。首批 lowering 覆盖整型/布尔/字符常量与
  `+`、`-`、`*`、`==`；不符合该结构的函数仍由旧发射器输出。SSA 暂不持久化，也未驱动平台后端。
- `tests/modules/projects/irfront/` 覆盖四种运算；项目回归要求普通 build 至少校验 4 个 IR 函数、
  `yh check` 的 `ir_functions=0`，最终程序返回 42。快照门现在会把清单声明的本地 path 依赖
  子项目纳入固定点，词法统计与性能脚本兼容新增 stats 字段。
- Apple M1、冻结 25 文件语料、20 轮端到端复测（含汇编/链接）：无改动 185/220 ms、单函数体变化
  957/1,023 ms、冷编 2,317/2,374 ms（中位数/p95）。汇编/链接调用分别为 0/0、1/1、4/1；
  函数修改与冷编较上一 20 轮缓存切片基线略慢，性能目标仍未达到。当前 IR 切片主要验证管线接线，
  还没有函数级缓存或并行带来的收益。完整报告见
  [AST→SSA 主路径报告](01-finished/yh-编译流程R2a首条主路径-2026-10-01.md)。
- 验证：`make -B`、`make test`（语法 66/66、反例 29/29、运行 63/63）、
  `make selfhost-native`（cc2/cc3 的 10 个模块产物固定点、32 文件自解析、全量语料、并发扫描、
  check/cache、模块 17/17、项目 36/36）通过。按门禁滚动种子后 SHA-256 为
  `cb2f690417488225e3916086c3a029ed1df4a7a94765c90e2428af1dbfd99b08`；新种子冷重建与自举门通过。
- R1 独立语义/check、任务私有状态、InterfaceReady 和函数级缓存，以及完整 SSA、线程池、平台后端、
  自有汇编/链接和 R3–R6 仍未完成。

## 2026-10-01 编译流程重规划 R2a 第四个切片：指令字段规范校验

- `ir_verify_inst` 现在检查当前 IR 指令的保留字段：CONST 不得携带 `a/b/aux`；PHI 不得
  携带普通操作数；非 CONST 的 `imm` 必须为零；非 phi 指令的 `aux` 必须为 -1；LOAD
  的 `b` 与 STORE 的附加字段不得伪造输入。IR 结构注释同步说明这些编码约束。
- 扩展 `irverify` `.yh` 反例：CONST 引用先前已定义值、PHI 带 immediate、ADD 带 aux、
  LOAD 携带多余 `b/aux`、STORE 携带多余 `aux/immediate`。首个反例在旧 verifier 下形成
  RED（退出码 16），收紧校验后通过；既有常量简化、phi、序列化与损坏 CFG 测试继续通过。
- 验证：`make`、`make test`（语法 66/66、反例 29/29、运行 63/63）、项目矩阵 33/33、
  `make selfhost-native`（固定点、自解析 31 文件、并发扫描 8/8、check/cache、模块 17/17、
  项目 33/33）通过；`git diff --check` 通过。
- R2a verifier 仍是部分操作集：调用、转换、switch、全局地址等指令和完整 SSA lowering
  尚未实现；独立 IR 也未接入编译主路径。详见
  [指令字段校验报告](01-finished/yh-编译流程R2a指令字段校验-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R2a 第三个切片：稳定 IR 序列化

- 新增 `compiler/ir/ssa_serialize.yh`，采用固定字段顺序的 little-endian 64 位格式；
  包含 magic、格式版本、目标编号、类型/指令/phi/CFG 表和 SSA 值数，不写结构体填充或地址。
- 解码要求调用方提供空输出，检查目标、版本、精确长度与 64 MiB 规模上限；分配后运行
  `ir_verify`，失败释放所有部分数组。`ir_function_release` 释放解码结果。缓存校验和提交
  仍由后续缓存层负责。
- 扩展 `irverify` `.yh` 用例，验证负 immediate、round-trip 逐字节相同、缓冲不足、错目标、
  错版本、截断数据和损坏 terminator；损坏 IR 被 verifier 拒绝并释放分配。
- 验证：`make test`（语法 66/66、反例 29/29、运行 63/63）、`make selfhost-native`
  （固定点、自解析 31 文件、并发扫描 8/8、check/cache、模块 17/17、项目 33/33）通过；
  最后一次变更后又运行 `make`、项目矩阵 33/33 与 `make selfhost-native` 均通过。
  按仓库门禁执行 `make seed` 并冷重建；Darwin 种子 SHA-256 为
  `8d658d975e0501c7fe49ef07fcb6d5a838466ae24f2f73d449688f43e6facb42`。
- IR 仍未接入主编译路径；AST→SSA、完整指令校验、函数级 IR 缓存、线程池和两个 arm64
  后端未完成，R2a/R2b 仍进行中。详情见
  [稳定 IR 序列化报告](01-finished/yh-编译流程R2a稳定IR序列化-2026-10-01.md)。

## 2026-10-01 编译流程重规划 R2a 第二个切片：默认低成本 SSA 简化

- `compiler/ir/` 新增 `IR_OP_COPY` 与独立 `ir_simplify`：对整数/布尔常量做定宽归一化，
  折叠整数加减乘和整数相等比较；把所有非自环 phi 输入相同的 phi 替换为别名/拷贝，
  并重写指令、phi 边和终结值引用。优化前后调用 `ir_verify`。
- 扩展 `irverify` 的 `.yh` 项目：先验收 `10 + 20` 折叠为 30，再验收两分支同值合流的
  phi 消除及 return 值替换；错误 CFG/类型/支配用例继续保留。
- 验证：`make`、`make test`（语法 66/66、反例 29/29、运行 63/63）、
  `make selfhost-native`（固定点、自解析、并发扫描、check、缓存、模块 17/17、项目 33/33）
  通过。`make seed` 已按门禁执行，SHA-256 仍为
  `8d658d975e0501c7fe49ef07fcb6d5a838466ae24f2f73d449688f43e6facb42`；随后冷构建、
  种子核验和项目矩阵 33/33 通过。
- 此优化还未接入主编译路径，IR 没有从 CheckedFunction/AST 构造，也没有持久化或目标后端；
  R2a、R2b 和 R3–R6 均未完成。

## 2026-10-01 编译流程重规划 R1 第七个切片：函数内稳定绑定

- check AST 新增函数内稳定绑定编号与 arena 行，捕获参数、局部变量/常量及 for-in
  隐式变量；表达式叶节点指向具体绑定行，语句节点关联一条或多条声明绑定。旧
  `sym_id` 只保留为解析时符号槽快照，遮蔽块退出并复用槽位后仍能区分变量身份。
- 赋值语句 AST 现在记录真实赋值 token；此前节点把 LHS 首 token 当作 `op`，无法供
  后续 SSA lowering 区分普通赋值与复合赋值。
- 扩展 `tokenreplay` `.yh` 用例覆盖函数参数、多绑定声明、局部常量、同名嵌套遮蔽、
  复合赋值和 for-in 隐式绑定；运行语义保持预期，`yh check --stats` 要求绑定数非零。
- 验证：`make test` 的语法 66/66、反例 29/29、运行 63/63 通过；模块项目矩阵 33/33，
  有效/无效 check、check 产物隔离、无外部工具回归通过。修复 `lex-stats.py` 与性能
  脚本对 `ast_bindings` 字段的解析后，`make selfhost-native` 全绿：两代 8 个模块
  固定点、自解析 30 个源文件、并发扫描 8/8、模块 17/17、项目 33/33。按仓库规则
  执行 `make seed`，新 Darwin 种子 SHA-256 为
  `8d658d975e0501c7fe49ef07fcb6d5a838466ae24f2f73d449688f43e6facb42`；随后冷重建、
  种子校验、`check-command.py` 与 `git diff --check` 通过。
- 这仍是 AST/check 迁移切片，不是独立语义阶段或 SSA lowering；任务私有上下文、
  InterfaceReady 调度与函数级缓存仍待 R1，R2a/R2b 尚未完成。

## 2026-10-01 编译流程重规划 R1 第六个切片：表达式绑定与常量事实

- typed 表达式节点现保存解析到的符号索引、符号类型/类别/标志/偏移，以及整型/指针
  常量位型、浮点位型和整数字面量标记。`ast_refs` 统计可复用的解析符号引用，
  `yh check --stats` 可直接观测。
- 符号索引按 `(file_id, owner_decl, sym_id)` 解释，并在捕获时复制符号元数据。旧
  `scope_pop` 会回收并复用函数局部符号槽，因此 AST verifier 不依赖函数结束后的
  `c_syms`；它验证声明归属、符号快照类型类别，以及标识符叶节点的类型一致性。
- 扩展 token replay `.yh` 用例，覆盖跨文件函数调用、参数/局部变量和私有常量引用；
  `check-command.py` 要求 `ast_refs` 非零。真实运行仍返回 42，项目 check 不生成后端
  产物，也不调用汇编器或链接器。
- 验证：`make`、`make test`（语法 66/66、反例 29/29、运行 63/63）、
  `make selfhost-native`（8 个模块产物固定点、自解析 30 个文件）、
  `python3 tools/selfbuild-gate.py`（两段三代固定点）、模块 17/17、项目 33/33 通过。
  滚动 Darwin 种子 SHA-256：`5c913f74733925f04dc4122d1765f4610d27a8d74934af8bc0ffeddafd9ba0eb`。
- AST 仍由旧语义遍历同步生成，尚未成为独立语法阶段产物；完整 `CheckedFunction`、
  任务私有上下文、接口就绪推进、函数级缓存和 SSA lowering 仍未完成。

## 2026-10-01 编译流程重规划 R1 第五个切片：语句与声明 AST

- 新增 `compiler/parse/ast_stmt.yh`，在 `yh check` worker 的现有解析遍历中记录块、
  声明、类型、if、for、switch/case、return、break/continue、goto/label、赋值与表达式
  语句。节点用文件内 token 半开区间、父/子/兄弟索引和表达式根引用表示，不改变普通
  build 路径的解析行为。
- 新增 `compiler/parse/ast_decl.yh`，复用已生成的 PDecl 范围建立文件级声明节点；函数
  体解析后连接到所属声明。worker 收尾验证语句树、根链、表达式范围、声明范围与函数体
  引用；`--stats` 增加 `stmt_nodes`、`decl_nodes`。
- 扩展 token replay 项目的 `.yh` 回归，执行 if/else、循环、continue、switch、赋值和
  return；`yh check --stats` 同时要求表达式、语句、声明节点非零。运行结果仍为 42，
  有效/无效 check、独立 check 缓存保护和无外部工具检查均通过。
- 本切片仍由旧 parser 的语义遍历同步建立 AST。没有独立 `CheckedFunction`、任务私有
  上下文、接口就绪调度、函数级缓存，也没有把 AST 接入 SSA builder；R1 与 R2a 未完成。
- 固定语料做了 3 轮速度冒烟测量：无改动中位数 209ms、单函数体变化 980ms、冷编 2,343ms；
  对应汇编/链接次数为 0/0、1/1、4/1。该小样本只作当前参考，不能代替 20 轮正式基线；
  50/200/1,000ms 验收目标仍未达到。
- 验证：`make`、`make test`、`make selfhost-native`、
  `python3 tools/selfbuild-gate.py`、check/阶段计数脚本、模块矩阵 17/17、项目矩阵 33/33
  全绿。两代主门固定点为 8 个模块产物一致，自解析 30 个源文件通过。滚动 Darwin 种子
  SHA-256：`af601fdab18b41092b716ec2ecd4835e324ee3b153739115ffbaea96ee9896e8`。

## 2026-10-01 编译流程重规划 R1 第四个切片：check 专用表达式 AST

- 新增 `compiler/parse/ast_expr.yh` 连续节点表，保存节点种类、运算符、语义类型、
  token 半开区间、token 数、项目文件 ID 和最多三个子节点。`Res.ast_id` 让当前解析
  遍历把已有类型结果关联到 AST；只在 `yh check` worker 启用，普通构建没有 AST 分配。
- 同步记录基本表达式、一元/二元/三元运算、调用和实参链、索引/切片、成员、
  `.to_type` 转换及数组字面量。模块 worker 完成函数遍历后校验节点范围、类型、
  后序编号、子节点包含关系和文件归属；`--stats` 增加 `ast_nodes` 计数。
- 扩展 token replay 的 `.yh` 项目函数，包含数组字面量、数组到切片转换、切片与索引、
  短路运算、三元与一元表达式；`tests/selfhost/check-command.py` 要求有效项目实际
  生成非零 AST 节点，并保留非法项目、产物清理和未调用外部工具的检查。
- 这是 R1 的表达式 AST 迁移切片，不是完整 AST：语句/声明节点、独立语义与 check
  遍历、任务私有上下文、InterfaceReady 调度及函数级缓存仍未实现。现有 parser 仍
  会在遍历时运行语义钩子，check 仍靠模式位抑制发射缓冲。
- 验证：`make`、`make test`、`make selfhost-native`、
  `python3 tools/selfbuild-gate.py` 全绿；自举固定点、模块 17/17、项目 33/33，
  compiler 项目的 `yh check --stats` 成功生成 4 个 worker 的 AST 且无汇编/链接。
  按滚动自举规则更新 `bin/yh`，SHA-256 为
  `a7b7fb039923dcb1d216b5ddce010e502d883e11fcbbea0759ca46df47b75905`。

## 2026-10-01 编译流程重规划 R2a 首个切片：typed SSA 模型

- 新增独立 `compiler/ir/` 项目，定义目标编号、函数私有类型表、typed 指令、
  SSA 值编号、基本块终结信息与 phi 前驱输入。数组连续存放，指令操作数只
  使用值/块索引；模块不依赖旧 `gen`、解析器或平台发射器。
- `ir_verify` 检查类型宽度、结果定义唯一性、操作数支配与内存操作类型、
  CFG 终结形式、指令块范围，以及 phi 是否覆盖每个真实前驱且无重复/错型。
- 新增 `tests/modules/projects/irverify/`，构造 if/else 合流的 phi `.yh` 正例，
  并确认重复前驱、错误类型和从另一分支引用未支配值会被拒绝；接入模块项目回归。
- 新 IR 作为 `compiler/` 下的嵌套项目后，固定点产物发现门曾把它误算入主项目；
  已按子目录 `project.toml` 设置边界，并给发现器增加嵌套项目反例自检。
- 验证：`python3 tests/modules/build-check.py --compiler-path ./yh` 通过（33/33 项目用例）。
  `make`、`make test`、`make selfhost-native` 与
  `python3 tools/selfbuild-gate.py` 全绿；滚动 Darwin 种子 SHA-256 为
  `c3e14e957539c6b57cffcb0aae14228c6a76ee25f1f01b570651f36d30924e4e`。
  尚未实现完整 SSA builder、稳定序列化和后端；该 IR 项目也尚未
  接入编译器主流水线，因此 R1 与 R2a 均未完成。源码见
  [ssa.yh](../compiler/ir/ssa.yh)。

## 2026-10-01 编译流程重规划切片：模块对象与链接内容缓存

- 为现有模块汇编增加对象缓存，为每个链接输出增加结果缓存；缓存键使用 64 位
  FNV-1a，并校验对象和最终程序内容。删除/损坏对象会重汇编；最终程序缺失或被
  覆盖会重链。
- `--stats` 增加 `asm` 与 `link` 实际调用次数。新增
  `tests/selfhost/link-cache.py` 覆盖冷/热构建、对象损坏、程序损坏与函数实现变化：
  热构建 0 汇编/0 链接，损坏对象 1/0，损坏程序 0/1，单模块函数变化 1/1。
- 编译器二进制指纹现在每个构建进程只读一次；对象/链接缓存逻辑拆入
  `compiler/cmd/link_cache.yh`，保留四个既有顶层模块。
- M1 冻结语料 20 轮中位数/p95：无改动 186/223 ms、单函数体变化 894/958 ms、
  冷编 2,199/2,287 ms。无改动较前一切片快约 89%，函数体变化快约 52%，冷编快约 0.8%；
  离 50/200/1,000 ms 目标仍有差距。
- 缓存仍按模块汇编，且没有纳入外部工具版本；全局扫描、整模块 check/IR、文件级
  对象、线程池、接口提前推进及自有工具链均未完成。详情见
  [对象与链接缓存测量报告](01-finished/yh-编译流程对象链接缓存-2026-10-01.md)。
- 最终门：`make -B`、`make test`、`make selfhost-native` 与
  `python3 tools/selfbuild-gate.py` 均通过；滚动 Darwin 种子 SHA-256 为
  `c3e14e957539c6b57cffcb0aae14228c6a76ee25f1f01b570651f36d30924e4e`。

## 2026-10-01 编译流程重规划 R1 第三个切片：项目级 yh check

- 新增 `yh check [module]`，对入口模块或显式模块及其依赖执行完整的现有
  语义遍历。合法项目通过；类型不匹配的 `.yh` 项目诊断并失败。
- check-only 子进程跳过汇编写文件，文本/数据段写入缓冲被屏蔽；不运行汇编器
  或链接器。依赖接口写入独立 `.build/check/iface/`，检查结束或失败时清除，
  保留正式 `.build` 缓存。
- 新增 `tests/modules/projects/checkbad/` 与 `tests/selfhost/check-command.py`，
  并接入 `make selfhost-native`。测试递归检查 `.build` 下没有汇编、对象、
  接口或 manifest 文件，并用 PATH 包装器确认没有调用 gcc/clang。
- 该实现是阶段性 CLI 和产物契约：语义仍由旧 parser pass 执行，靠全局模式位
  抑制发射缓冲；完整 AST、独立语义/check 遍历、任务私有状态和函数缓存仍在 R1。

## 2026-10-01 编译流程重规划 R1 第二个切片：顶层声明范围索引

## 2026-10-01 编译流程重规划 R1 第二个切片：顶层声明范围索引

- worker 项目索引为每个源文件记录顶层声明的 token 起止、关键字与源位置。
  声明 pass 按范围跳过函数体，globals/functions pass 跳过无关声明；索引
  没有表达式/语句节点，尚不能作为完整 AST 或独立语义检查结果复用。
- 修复了公开声明边界：相邻声明的 `pub` 原先会被前一声明范围吞掉，导致后续
  函数按私有符号处理。项目矩阵 32/32 通过，覆盖 `pub struct` 后接 `pub fn`。
- 固定语料每场景 20 轮，中位数/p95：无改动 1.717/1.889 秒，单函数体变化
  1.869/1.998 秒，冷编 2.217/2.319 秒。词法次数仍为 25/53/131；函数体
  变化索引 736 个顶层声明，冷编索引 2,944 个。相较 R1 首切片中位数分别
  下降约 14%、11%、7%；各场景仍汇编 4 次、链接 1 次。当前编译器 SHA-256
  `6cc3f94995d148d554d6d3e1e84898452b6ea81480e1179be65e9c51ae5f57b6`。
  详见[声明索引测量报告](01-finished/yh-编译流程R1顶层声明索引-2026-10-01.md)。
- 这一步的建立索引仍是额外顶层 token 遍历；端到端结果来自冻结语料实测，不能
  推广为所有项目加速保证。完整 AST、check 与任务缓存仍未完成。

## 2026-10-01 编译流程重规划 R1 首个切片：worker 词法快照复用

- 模块 worker 在项目索引时为发现的 `.yh` 文件保留只读源字节与 token
  数组；pass1、全局初始化 pass 与函数 pass 从同一 token 快照重放，不再
  对模块文件重复读取和词法分析。父构建器的项目索引与 worker 项目发现
  仍分别发生，完整 AST 和跨构建文件缓存尚未实现。
- 新增显式 `yh build --stats` 诊断计数器和 token replay 多模块 `.yh` 回归：
  覆盖私有跨文件类型、前向函数调用、跨模块导入与运行结果 42；索引 3 个
  文件共词法 3 次，两个 worker 的 pass1/global/function 文件遍历合计各 3 次。
- M1 固定 25 文件语料每种场景测 20 轮：无改动中位数/p95 为
  2.002/2.185 秒，函数体变化 2.099/2.452 秒，冷编 2.378/2.710 秒；词法
  扫描次数分别 25、53、131，四次汇编和一次链接保持不变。函数体变化和
  冷编的旧流程复核数分别为 74、206；耗时尚无稳定改善，50/200/1000 ms
  目标远未达到。测量及边界见
  [R1 切片报告](01-finished/yh-编译流程R1词法快照复用-2026-10-01.md)。
- 验收：`make -B`、`make test`、`make selfhost-native`、
  `python3 tools/selfbuild-gate.py` 通过；滚动 Darwin 种子 SHA-256 为
  `802f47daff273bceaeeb2857ab409f910dc16ab383534bc93f10ca5533cc8a4b`。
  R1 整体仍未完成。

## 2026-10-01 R0 第二个实施切片：宿主种子与扫描临时状态隔离

- Makefile、两套自举门和 `make seed` 统一使用按宿主系统/架构选择的
  种子路径与旁置 SHA-256；显式 `SEED` 也会校验哈希。Linux arm64
  目标解析为 `bin/yh-linux-arm64`，不覆盖 macOS 的 `bin/yh`。
- 项目索引不再把所有编译器进程的目录列表写进固定 `/tmp` 文件，改为
  `tmp/` 下每进程独立的随机路径，读完即删除。新增并发 `.yh` 项目构建
  回归；旧实现 8 路并发时出现崩溃和交叉目录读取，修复后 8/8 通过。
- 验收：`make -B`、`make test`、`make selfhost-native`、
  `python3 tools/selfbuild-gate.py` 通过；Linux arm64 种子路由 dry-run
  与当前 Darwin 种子 SHA-256 校验通过。
- R0 仍待冻结可重复性能语料、阶段计数/工具调用/峰值内存，并记录
  状态归属与就绪事件契约。线程 worker 的临时路径需随任务私有上下文
  落地；本切片完成的是进程间隔离。

## 2026-10-01 R0 完成：冻结性能基线与流水线状态契约

- 固定提交 `8e17bdb` 的 25 文件/13,338 行 compiler 输入，保存每个源文件
  与 project.toml 的 SHA-256。新增可重复测量脚本，函数体变化会实际改变
  编译器运行结果并由脚本验证。
- Apple M1 上每种负载测 20 个独立进程：无改动 1.985 秒中位数、2.403 秒
  p95；单函数体变化 2.075/2.751 秒；热 OS 缓存下冷编 2.455/2.741 秒。
  峰值单进程 RSS 为 50.63/50.83/50.86 MiB。所有场景仍调用 4 次 clang 汇编
  与一次链接。详细阶段访问数和限制见 R0 报告。
- 旧 pass2 将语义与发射混合，无法提供独立阶段计数；已记录实际模块/文件
  访问次数，R1 将引入分开的前端、check 与代码生成计数器。SourceStore、
  ModuleEnv、FunctionContext、TargetContext 及三个就绪事件契约已落设计。
- R0 全部检查通过：`make -B`、`make test`、`make selfhost-native`、
  `python3 tools/selfbuild-gate.py`；滚动种子 SHA-256 为
  `0b3c43a7595288841ca9277cc7084154bc2f8235bff1bc2d017655f48a8d28c8`。

## 2026-10-01 R0 首个实施切片：可信固定点门

- 修复 `native-selfhost.py` 与 `selfbuild-gate.py` 构建下一代前会覆盖
  前代 `.build`，导致延迟快照把同一路径当成各代比较的错误。每代现在
  立即保存到独立的 `tmp/` 快照目录。
- 从 project.toml 项目名与源码 module 声明动态推导应有的 `.s/.s.i`；
  两个自举门拒绝空快照、缺失或多余产物及代间字节差异。新增门自检
  验证固定点通过、空集/漏产物/内容变化被拒绝。
- 新增 `tests/selfhost/fixedpoint-probe.yh`，覆盖前向调用、结构体浮点
  字段、按值调用与循环。两套门都编译并运行该探针。
- Makefile 的冷编和 clean 路径改为实际 `compiler/.build`。
- 验收：`make -B` 成功；`make test` 语法 66/66、反例 29/29、
  运行 63/63；`make selfhost-native` 固定点 8 项、探针和全量门通过；
  `python3 tools/selfbuild-gate.py` 三代固定点两组、modules 17/17 通过。
- R0 仍在进行：各平台种子路径统一、项目索引临时路径隔离与性能
  基线/阶段计数待做。未滚动 `bin/yh`，因为本切片没有修改编译器源码。

## 2026-10-01 编译流程重规划（GrillMe，规划已确认）

- 用户已确认增量优先、完整 check 的逻辑阶段/命令、产品取消外部
  工具/shell/libc/CRT 的边界，以及首批双 arm64、Linux 先闭环。
- 已记录[ADR-0009](adr/0009-yh采用check与IR及早期并行.md)与
  [设计决策树](03-design/yh-编译流程设计决策树.md)，补 glossary，
  标记旧方案撤回并更新 todo。第二轮确认 SSA、线程池、接口就绪
  后提前推进，以及文件解析/函数 check-IR/文件对象的增量粒度。
- 第三、四轮确认 macOS 审核 OS API/libSystem/dyld 边界、Linux 静态
  ELF 自有工具链首版范围、默认低成本优化、目标隔离 check/IR、
  M1 固定语料 50ms/200ms/1s 待达成目标，以及内部模块重组和 system
  仅保留过渡兼容配置的取舍。
- 完成只读事实调查：重复词法路径、串行模块链、提前接口与共享
  状态障碍，以及工具/shell/运行时/OS/开发测试依赖分层。静态计数
  不当作性能结果。另在独立副本测旧流程 3 冷/3 热/3 函数体注释
  修改构建，端到端中位数 3.211/2.420/2.389 秒；9 次构建成功，
  波动明显且注释修改不是新函数级增量负载。
- 已重写[设计](03-design/yh-编译流程重规划.md)与
  [实施方案](02-plan/yh-编译流程重规划实施方案.md)，明确阶段契约、
  SSA、状态归属、就绪调度、缓存/提交、平台运行时与 R0–R6 验收。
- 完整方案已由用户确认，答案为“确认规划，不开始编码”。仅更新
  文档，未修改编译器、测试或种子；git diff --check 与本地链接检查通过。
  本条记录完成的调查与草案，不代表代码或性能目标已经完成。
  详见[规划交付记录](01-finished/yh-编译流程重规划草案交付-2026-10-01.md)。

## 2026-09-30 全仓库文档同步：修正 40 处事实错误，11 份历史文档加抬头

以实测为基准（CLI 选项逐一验证、目录与 Makefile 目标枚举、示例实跑）
核对全部现行文档，详见
[全仓库文档同步报告](01-finished/yh-文档全面同步报告-2026-09-30.md)。本次
**未修改编译器代码与测试**。

- **事实错误修正**：`README`（删除交叉 ELF/`-c`/`-run`/`--cross` 用法，补
  子命令式 CLI，修正并实测通过语言示例）、`compiler/README.md`（整篇重写：
  原文停留在「构建中断」与平铺 12 文件布局，改为四模块 25 文件实际职责）、
  `AGENTS.md`（填充空节目录/编译流程/使用/构建与测试）、`CONTEXT.md`
  （补模块系统术语）、`03-design/` 五份（mod.toml → project.toml、
  `src/core/` stage0 接入点、gen/lex/parse/cmd 路径、门由 `make bootstrap`/
  `make g3` 改为 `make selfhost-native`、「全局聚合初始化」从缺口移除）、
  `00-语义边界-0.0.1.md`（§3 改写为现行模块可见性规则）、`adr/0001/0005/
  0006/0007`（过期引用与状态）、`02-plan/yh-VSCode扩展方案.md`（9 处
  `yh-new` → `yh`）、`docs/todo.md`（VS-U1）。
- **历史文档只加抬头**：finish.md 条目与 `01-finished/` 交付报告记录的是
  当时状态，旧称谓是正确记述，不改写正文；改为加「历史/已被替代/待重写」
  抬头并指向现行文档，共 11 份。
- **验证**：README 示例抽取编译运行通过（输出 `1 2 1` / `small`）；
  CLI 选项逐一实测确认已删除；全仓库 Markdown 内部链接坏链 0；
  `make test` 63/63；`make selfhost-native` 全绿。

## 2026-09-30 编译流程重规划（文档交付）

- 核对现行 token 驱动、三次遍历、模块子进程、`.build` 缓存和滚动
  自举流程，交付[设计](03-design/yh-编译流程重规划.md)、
  [实施方案](02-plan/yh-编译流程重规划实施方案.md)与
  [ADR-0008](adr/0008-yh编译流程分阶段整理.md)建议稿。
- 待实施 CF-0–CF-4 写入 todo；优先修正两个自举脚本延后读取同目录
  快照造成的自比较，再统一编译核心、目标/产物提交与三层缓存。
- 验证：`make -B` 构建成功；`make test` 语法 66+29、运行 63/63；
  `make selfhost-native` 退出 0，自解析 25 文件、modules 17/17、项目
  31/31。原固定点门的证据缺陷仍待修正；本轮另以独立源码副本
  两代冷编、每代立即保存快照，8 个 `.s/.s.i` 逐字节一致。
- 仅修改规划与记录文档，未修改编译器源码或种子。详细命令、边界
  和证据见[交付报告](01-finished/yh-编译流程重规划交付-2026-09-30.md)。

## 2026-09-30 清单精简：name 产物名 + version 命令 + 入口 = main 模块（用户项目规划落地）

按 docs/todo.md「项目规划」（该节实施后按文件约定移出，历史在此）：

- **schema**（`compiler/cmd/project_index.yh`）：`name` 必须是标识符
  （首字符字母/下划线，其余字母数字下划线），否则诊断「project.name
  必须是标识符」/「只能是字母、数字与下划线」；新增放行 `author`
  （只接受不存）；**删除 `entry` 字段**（旧字段会命中未知字段检查）；
  `version` 不再解析后丢弃，存入 `PProj.ver_off/ver_len`。
- **入口 = 模块名 `main`**：pj_load_project 扫描源码根时标记
  `is_entry`；模块名唯一（同名模块跨目录合并），故至多命中一次——
  先写的「多个 main」歧义分支不可达，已删除。模块名与目录名无关
  （编译器自身 `compiler/cmd/*.yh` 即 `module main;`，目录仍叫 cmd）。
  新增 `pj_entry_mod(proj)`（`project_resolve.yh`）供 build/run/query 用；
  `PProj.entry_off/entry_len` 删除。
- **产物名**：`yh build` 无 `-o` 时取 `project.name`（原固定 `.build/yh`）；
  `yh run` 用同名二进制。`name` 合法标识符约束正是为了让文件名无需 sanitize。
- **`yh version`**：打印当前项目 `<name> <version>`（version 缺省时标注
  「未声明 version」）；裸 `yh` 的用法说明后附同一行，不在项目内静默跳过
  （`pj_find_root(quiet)` 加参数，非静默时保持原诊断）。
- **顺带修**：`build` 的库模式完成信息用 `pj_canon_len`（已被后续 canon
  覆写）打印目录，改为 `build_len`。
- **清单批量更新**：26 个 project.toml 删 `entry` 行、name 去斜杠
  （`yh/compiler` → `yh_compiler`、`example/xxx` → `example_xxx`、
  `yh/std` → `yh_std`）；`tests/modules/projects/fourdir{'',bad}/cmd/main.yh`
  改 `module main;`（目录名保留 cmd，覆盖「模块名≠目录名」）。
- **新语料**：`tests/modules/projects/tomlnamebad`（name 含 `/` 必须拒绝）、
  `authorproj`（name/version/author 三字段齐备）；build-check.py 增
  `p1-name-not-identifier`、`p1-version-cmd`、`p1-outname-from-name`、
  `p1-outname-runs`，并把 fourdir 接口名断言改为 `example_fourdir-main.s.i`、
  keyimp/alias 产物路径改为按 name。项目验收 31/31。
- **滚动自举桥**：删 `entry` 后旧种子（按 entry 选入口）不再认识新清单，
  首次 `make` 会把编译器当库项目且不链接。按既有做法桥接——临时给
  compiler/project.toml 加 `entry = "main"` → 旧种子构建出新 `yh` →
  删临时行 → 新编译器自举构建 → `make seed` 滚种子。
- **验证**：`make` ✓（删产物冷编）；`make test` 63/63 ✓；
  `python3 tests/modules/check.py` 17/17 ✓；`make selfhost-native` 全绿
  （两代固定点 8 产物一致、cc3 自解析 25 文件、语法 66/66+29/29、
  run 63/63、项目 31/31）✓；种子已滚动（`bin/yh.sha256` 更新）。
- **设计文档**：`docs/03-design/yh-模块与项目管理设计.md` 的示例清单、
  字段表、入口规则、命令表同步（该文档仍通篇写 mod.toml，属既有欠账，
  本轮未动）。

## 2026-09-30 project.toml 改名 + import as/跨项目导入 + .build 缓存布局（用户项目规划落地）

按 docs/todo.md「项目规划」实施（方案见
[project.toml与模块增强方案](02-plan/yh-project.toml与模块增强方案.md)）：

- **import 语法扩展**：`import NAME (as ALIAS)?;` 与
  `import KEY.MOD (as ALIAS)?;`。ImportEnt 扩展 proj_key/alias 字段
  （model.yh），mod_parse_head 解析别名与两段点分（多于两段拒绝），
  重复绑定名报错（同模块不同来源用 as 区分）。
- **限定调用按别名**：mod_file_binding 改按 alias 匹配（原按查找名）。
- **绑定架构重构**：删除 gen 侧按名匹配的 mod_bind_current_file，改为
  cmd 侧 mb_file_head_bind(fi) 直绑——child 编译时按扫描期 p_imp 记录
  （file+line+col 对应）把解析结果写入 mod_import_mod，天然支持别名与
  跨项目（解析结果与名字解耦）。
- **KEY.MOD 限定解析**（pj_bind_imports）：键在 [dependencies] 查找，
  键缺失/依赖项目无可导入模块显式报错；不走三层搜索。
- **目录唯一模块**：pj_index_file 登记文件时检查同目录是否已有其他
  模块的文件，违反报两个模块名（新增 pj_dir_prefix_len/pj_same_np）。
- **mod.toml → project.toml**：pj_load_project/pj_find_root/pj_proj_diag
  与全部 fixtures（31 个）、编译器自身清单同步改名。
- **.build 缓存布局**：.build/asm（每模块 .s）、.build/obj（每模块 .o）、
  .build/iface（<tag>.s.i）、.build/manifest；产物名用
  `<sanitize(proj)>-<module>` tag（KEY.MOD 下同名模块防冲突）；
  两步链接（gcc -c 逐模块 → 链接全部 .o）；默认产物 = .build/yh。
- **缓存键补编译器身份**：manifest FNV 哈希加入编译器二进制自身内容
  （c_argv0 文件），滚动代次下热缓存安全。
- **修复**：pj_imp_push 重写时漏带 p_imp_mod 数组分配（首写空指针
  段错误，lldb 定位后补 nd9）；mod_skip_head 的 while 语法错误；
  pj_dir_prefix_len 参数用了关键字 len；pj_imp_push 扩容计数 cnt 缺
  类型声明；mod_skip_head/parse_module 的旧式 while 全部改 for 条件式。
- **种子滚动**：因清单改名触发一次 bootstrap bump（旧种子只认
  mod.toml）——临时 mod.toml 副本 + 旧种子构建 → 新编译器
  （支持 project.toml）→ 删副本、滚种子。迭代桥接 asm/*.s.i →
  iface/ 解决新旧 iface 写读路径差异。
- **验证**：make ✓；make test 63/63 ✓；make selfhost-native 全绿
  （两代固定点 8 产物一致、自解析 25 文件、语法 66+29、run 63、
  modules 17、项目验收 26/26 含新增 alias/keyimp/dirconflict）✓；
  tools/selfbuild-gate.py（cc2→cc3→cc4 固定点）✓。
## 2026-09-30 0.0.3 发布：滚动自举首次端到端跑通（CI 以 0.0.2 资产为种子）

- tag `0.0.3` 推送触发新发布流水线，两次失败后全绿：
  ①`gh api "releases?…"` 相对路径 404，错误 JSON 被词法拆分成假标签——
  改完整路径 `repos/$GITHUB_REPOSITORY/releases` + `--jq` + 显式错误
  检查；②容器 root 写出的 `out/` 目录外层步骤无写权限——产物（yh 与
  转发的 libtcc1.a）全部改在容器内写入。
- **运行结果**：[run 36636909702](https://github.com/lalavender/x/actions/runs/36636909702)
  全绿；Release [yh 0.0.3](https://github.com/lalavender/x/releases/tag/0.0.3)
  归档 4 资产（linux 包 yh + libtcc1.a、darwin 包 yh，各带 sha256）。
- **滚动自举链验证**：CI linux 作业下载 0.0.2 Release 资产，取其中
  yh-new（ELF）作种子 `make SEED=…` 构建出当前源码的 yh 并冒烟通过；
  darwin 作业用入库 bin/yh 构建。
- **端到端用户视角验收**：实际下载 Release 资产——linux 包解压后
  `YH_LIBDIR=<目录> ./yh hello.yh -o hello` 在 arm64 容器运行通过；
  darwin 包解压后本机直接运行通过；两包 SHA-256 与 .sha256 资产一致
  （linux 08f1c470…27e8a）。
- 至此逐版滚动闭环：每版 bin/yh（Darwin 种子）+ Release linux 资产
  （Linux 种子）→ 下一版构建。

## 2026-09-30 主编译器二进制更名：yh-new → yh（编译器就是 yh）

- **改名映射**：主编译器二进制 `yh-new` → `yh`（项目根产物与 Release
  资产名）；入库种子 `bin/yh-new` → `bin/yh`（+ `bin/yh.sha256`，已用
  当前源码产物滚种）。stage0 名义上的 `yh` 名额让给主编译器；stage0
  本体已随 0.0.3 删除，无命名冲突。
- **Makefile**：`YHNEW` → `YH`；一步链规则改 `$(YH)`；新增 `SEED`
  覆盖变量（缺省 = `bin/yh`，命令行可指定其他种子路径——CI Linux 用
  上一版 Release 的 ELF 种子；覆盖时免去 bin 种子前置，路径以 abspath
  传给 yh build）；`seed` 目标、install/uninstall、clean、help 同步。
- **脚本与工具**：tests/yh/check.py、tests/yh-run/check.py、
  tests/modules/{check,build-check}.py、tests/selfhost/native-selfhost.py、
  tools/selfbuild-gate.py、tools/yh-explorer.{py,html}（下拉仅剩
  yh 一项）。当前状态文档同步：AGENTS.md、README、compiler/README.md
  （陈旧的 bootstrap/g3 容器门描述替换为 native-selfhost 两代门实况）、
  docs/todo.md（0.0.3 两节合并，D1–D5 由并行工作落地后本节补 CI 项）、
  ADR-0006/0007 更新注记。历史记录（docs/01-finished、02-plan、
  03-design、finish.md 旧条目）保留原名不动。
- **发布流水线滚动自举化**（release.yml 重写）：linux 作业下载上一版
  Release 的 linux-arm64 资产，取其中主编译器作种子（0.0.2 包内叫
  yh-new、之后叫 yh，自动探测）经 `make SEED=…` 构建当前源码，
  libtcc1.a 随包转发（src/ 已删无法重建）；darwin 作业直接用入库
  bin/yh 构建；双平台冒烟后归档 tar.gz + sha256。Release 说明同步。
- 清理：并行工作遗留的根目录 `ex1` 编译产物加入 .gitignore 不入库。
- **验证**：`make`（bin/yh 种子一步链）+ 冒烟 ✓；`make test` 63/63 ✓；
  `make selfhost-native` 全绿（两代固定点 + 语法/运行语料 + modules
  17/17 + 项目验收 23/23）✓；`make seed` 滚种 + bin/yh 冒烟 ✓；
  arm64 ubuntu:24.04 容器以 0.0.2 linux 资产为种子（SEED=/prevseed/
  yh-new + 转发 libtcc1.a）构建出可用 ELF `yh` 并冒烟通过——发布
  配方与滚动自举链兼容。VERSION 0.0.2 → 0.0.3。

## 2026-09-30 脱离 stage0：删除 C 实现与 bootstrap，切换滚动自举（0.0.3）

分析确认 bin/yh-new（入库种子，含完整模块系统）可直接构建当前四模块
源码（产物模块 .s/.s.i 固定点验证 + run 语料 63/63），据此执行删除：

- **删除**：src/（C 版 stage0）、include/、lib/lib-arm64.c、config.h、
  libtcc.a/libtcc1.a 及目标文件、bootstrap/（seed 快照）、
  tools/flatten.py、tests/yh/container-yh*.sh（容器包装）、
  tests/selfhost/g3-acceptance.py 与 probe-main.c/macho.py（stage0
  容器验收链随 stage0 终结）。
- **构建切换**：Makefile 重写——`make` = `bin/yh-new build`（compiler/
  项目，一步链、冷编）产出 yh-new；`make seed` 滚种子（验证全绿后
  覆盖 bin/yh-new + 更新 SHA-256；macOS 下 cp 覆盖会触发 provenance
  拦截 SIGKILL，Makefile 内 tmp+mv+codesign 重签处理）。
- **验证门重组**：`make test` = ANTLR 语法 66/66+29/29 + 编译器语法
  模式 + run 语料 63/63（全部跑 yh-new；tests/yh/check.py 与
  tests/yh-run/check.py 的缺省编译器与相对路径改绝对，修复
  Path('./yh-new') 规范化成裸名后按 PATH 查找的 FileNotFoundError）。
  `make selfhost-native` = 重写后的 native-selfhost.py（bin/yh-new →
  cc2 → cc3 两代冷编，模块固定点一致 + cc3 自解析 25 源文件 + 全量
  语法/运行语料）+ modules 17/17 + 项目验收 23/23。
  tools/selfbuild-gate.py（四代链固定点，stage1=bin/yh-new）保留。
- **种子滚动**：bin/yh-new 已覆盖为当前源码产物
  （6e204dea841d508bf8879bdd895ec41c9055c396e3b369e6c44abb3d7d594fef）。
- **边界**（AGENTS.md/todo 已记）：滚动自举下源码不能在仓库内独立
  重建编译器（git 历史保留每代种子兜底）；stage0 差分参照、-run、
  交叉 ELF、g3 容器门终结；Linux 版含模块系统 yh-new 归档后另立
  Linux 开发/CI 流程。
## 2026-09-30 0.0.2 发布：bin/ 入库编译种子 + tag 触发 Release 归档

- **bin/ 入库副本**：Makefile 新增 `$(BIN_SEED)` 规则（挂进 `all`）——
  每次构建把 yh-new 复制到 `bin/yh-new` 并提交进仓库；clean 不清理
  （仓库内容物，非构建产物）。作为版本间编译种子：0.0.3 起删除
  src/（stage0）与 bootstrap/（seed）后，各版本直接用上一版二进制
  编译（Darwin 用 bin/ 副本，Linux 用上一版 Release 的 linux-arm64
  资产）。AGENTS.md 同步说明。
- **VERSION 0.0.1 → 0.0.2**；tag `0.0.2` 推送触发既有 release.yml
  流水线（双平台构建 + 冒烟 + tar.gz/sha256 归档到 GitHub Release，
  即"服务器保存一份"）。
- 顺手清理：Makefile 重构遗留的重复 `BOOTSTRAP_DIR` 定义去掉一处。
- **0.0.3 计划**（docs/todo.md「0.0.3 脱离 stage0」D1–D5）：删 src/ 与
  bootstrap/、构建链改为种子一步链、CI 改用上一版 Release 资产作
  Linux 种子、验证门重建为两代固定点。
- 本地验证：make（两步链 + bin 副本）幂等、bin/yh-new 冒烟通过；
  arm64 ubuntu:24.04 容器 make -j4 + 双冒烟 + bin/yh-new（ELF）冒烟
  通过——发布配方与新构建链兼容。
- **实际运行结果**：tag `0.0.2` 流水线
  [36630090430](https://github.com/lalavender/x/actions/runs/36630090430)
  一次全绿；Release
  [yh 0.0.2](https://github.com/lalavender/x/releases/tag/0.0.2)
  归档 4 资产（darwin/linux 各 tar.gz+sha256）；端到端验收：下载
  linux 包（内容 yh/yh-new/libtcc1.a）SHA-256 与 .sha256 资产一致
  （e6b8b3ca…381e），darwin 包内容 yh/yh-new。

## 2026-09-30 编译器源码四模块化完成（ADR-0007 P1–P5）：compiler/ 成为 mod.toml 项目，四代自举固定点达成

接上条（P0 恢复构建 / P4 热点拆分）。compiler/ 现在是真实的四模块
yh 项目（[ADR-0007](adr/0007-yh编译器使用源码模块.md)），自举编译器
用自身模块系统构建自身：

- **项目形态**：compiler/mod.toml（name="yh/compiler"，source="."，
  entry="cmd"）；gen（model/buffer/symbols/target/emit_arm64/sem_value/
  sem_expr/sem_call_literal/sem_flow/sem_decl，10 文件）、lex（lexer）、
  parse（parse_type/parse_expr/parse_stmt/parse_decl/parse_global_init/
  parse_module/iface，7 文件）、cmd（toml/project_state/project_index/
  project_resolve/module_build/compile/driver，7 文件）共 25 文件，
  全部 module 声明，依赖单向 gen←lex←parse←cmd（自家 topo 拒环）。
- **解环迁移**（四个函数入 gen）：sem_compile→cmd/compile.yh（P4 已做）、
  err_tok→gen/buffer.yh、tml_intern_str→gen/symbols.yh、
  mod_ns_lookup 与 mod_file_binding→gen/symbols.yh。
- **限定名改写**：约 3800 处脚本化（tools 内联脚本，符号表 723 项，
  状态机跳过注释/字符串/字符字面量，前导非 [.A-Za-z0-9_] 才改写），
  零跨模块同名冲突。pub 从宽（顶层+字段全 pub），收缩留后续。
- **P1 seed**：bootstrap/seed/compiler.yh = tools/flatten.py 扁平化
  产物（剥 module/import、剥字段 pub、去限定前缀——仅代码态），供
  stage0 编出「seed 编译器」。ADR-0007 对剥离式种子的保留意见成立：
  它是派生产物而非手工快照，正确性靠 P5 固定点背书，活跃源升级后
  需重新生成。
- **P2 探针**：fourdir/fourdirbad fixture（gen 公开状态与类型、
  lex/parse 限定调用、cmd 入口；私有字段跨模块拒绝），项目验收
  扩至 23/23。探针暴露 pj_canon 空段返回契约 bug（"." 折叠返回
  偏移被误判失败）——修复。
- **P3 构建迭代修复**：sizeof(m.T) 识别（sizeof_starts_type 限定
  判定）；if_emit_type 具名类型全表查询（pub 签名引用跨模块类型
  原样输出 mangle 名）；未使用导入被自家构建器拒绝后按实际使用
  收敛各文件 import。
- **P5 四代链**：tools/selfbuild-gate.py 固化——stage0→seed 编译器
  →cc2→cc3→cc4（每代冷编），cc2/3/4 两两 gen/lex/parse/cmd 全部
  .s/.s.i 逐字节一致（固定点），cc4 冒烟与 modules 17/17 通过；
  挂进 make selfhost-native。**日常 yh-new 切换为项目构建产出**
  （Makefile 两步链：stage0 编 seed → seed 编译器对活跃项目
  yh build，每次冷编避免缓存键缺编译器身份的问题）。
- **验证**：make（两步链）✓；make test 63/63 ✓；make selfhost-native
  全绿（seed 链三代自举、语法 66/66+29/29 ×3、模块语料 17/17 ×3、
  项目验收 23/23、selfbuild 四代固定点）✓；容器 make bootstrap ✓、
  make g3 通过 ✓；python3 tools/selfbuild-gate.py 全过 ✓。
- **过渡桥说明**：P3 迭代期曾用扁平化源编出一次性过渡编译器
  （yh-trans）打通四模块构建；P5 链建成后已由 seed 链取代，
  tools/flatten.py 保留为 seed 生成器。
## 2026-09-30 编译器源码按四目录布局恢复构建 + 热点文件拆分（ADR-0007 P0/P4）

用户已将 17 个编译器源文件归入 cmd/gen/lex/parse 四目录（另 model/
buffer/symbols/iface 暂留根部），旧路径使 Makefile 构建中断。本轮：

- **P0 恢复构建**：Makefile `SELFHOST_SOURCES` 与
  `tests/selfhost/native-selfhost.py` SOURCES 切到当前布局，并直接
  采用拆分后的文件清单（25 项）。`make`、`make test` 63/63、
  `make selfhost-native` 全绿（三代语法 66/66+29/29 ×3、三代模块语料
  17/17 ×3、项目验收 21/21、s2.s==s3.s 固定点一致）、容器
  `make bootstrap` 通过（G1+G2+固定点）、`make g3` **通过**
  （首次运行遇 B8 已记录的容器挂载瞬时问题，重跑全绿，全量日志
  /tmp/g3.log）。
- **P4 热点拆分**（按[详细方案](02-plan/yh-编译器模块化详细方案.md) §5
  的完整函数边界，纯移动不含语义改动）：
  - gen/sem.yh（2403 行）→ `sem_value`(329)/`sem_expr`(656)/
    `sem_call_literal`(461)/`sem_flow`(539)/`sem_decl`(262)；
    `sem_compile`(50) 迁 cmd/compile.yh（P3 解环预置）；
  - cmd/project.yh（1390 行）→ `project_state`(459)/`project_index`(408)/
    `project_resolve`(471)；
  - parse/parse_decl.yh（1215 行）→ `parse_decl`(640) +
    `parse_global_init`(542)。
  拆分按「前导注释块 + fn 到列 0 `}`」为单元脚本执行；恢复构建时
  发现 project.yh 头部的 `pj_scratch`/`pj_ls_cap` 两个文件级全局随
  头注释丢失，已补回（附边界注释）。所有文件回到 500±行建议带；
  gen/emit_arm64.yh（1014）按方案明确不拆。
- 回归说明：拆分为行为不变移动，回归由既有语料覆盖（run 48 的
  全局初始化/聚合/浮点/变参用例正好压住三簇被移动函数；语法 66+29；
  模块 17；项目 21），未新增语义用例。gen/sem_*.yh 与 cmd/project_*.yh
  等新文件均为原文件内容的逐字节子集（仅新增文件头注释与找回的全局块）。

## 2026-09-30 按用户现有 cmd/gen/lex/parse 目录修订编译器模块化方案

本轮重新核查用户已经移动的 13 个文件：内容与原 Git 版本逐字节
相同；compiler/mod.toml 为空，全部 17 个正式 .yh 文件仍无
module/import 声明。当前 `make -n yh-new` 失败，报旧依赖
`compiler/lexer.yh` 不存在；此前文档记录的构建成功是目录移动
发生**之前**的基线，不能用于当前工作区。

将现行[实施方案](02-plan/yh-编译器模块化详细方案.md)、
[架构设计](03-design/yh-编译器源码模块化设计.md)、
[ADR-0007](adr/0007-yh编译器使用源码模块.md)按既有目录重写；
旧 13 模块分类草案标为历史。具体调查、解环函数、文件拆分与
未运行代码验证的范围见
[本次修订记录](01-finished/yh-编译器按目录模块化方案修订-2026-09-30.md)。
本轮没有修改正式编译器源码或构建脚本。

## 2026-09-30 yh 编译器源码模块化方案与可行性探针

本轮交付[架构设计](03-design/yh-编译器源码模块化设计.md)、
[分阶段实施方案](02-plan/yh-编译器模块化详细方案.md)、
[ADR-0007](adr/0007-yh编译器使用源码模块.md)与
[完成记录](01-finished/yh-编译器模块化方案-2026-09-30.md)。
范围仅为调查、设计及 `tmp/` 探针，未移动正式编译器源码。

- 核对当前 17 个自举源码文件约 13,004 行、Makefile 和
  `tests/selfhost/native-selfhost.py` 双份固定拼接顺序；C stage0
  依 ADR-0006 冻结，不能编译带 `module/import` 的活跃源码。
- 检查 `compiler/iface.yh`：公开签名引用外模块具名类型时无法导出，
  所以旧 13 模块分类草案的批量 `pub` 不能直接成为执行步骤。
- 在 `tmp/compiler-modularization/probe/` 中，按当前顺序复制 17
  源文件并加 `module compiler;`，由现有 `yh-new build` 成功
  产出可执行编译器；该产物再次冷编同一项目，模块汇编 SHA-256
  均为 `4bd4ba108cd7a2b70e9825375ac3f443e40bfe65e13bd3c078ed8ca41d370730`。
  此探针仅证明单模块项目迁移入口可行。
- `GRAPHIFY_OUT=tmp/compiler-modularization/graphify graphify update .`
  得到 1510 节点、4432 边，但跳过 `.yh`，不能据此判定自举源码
  依赖；`graphify god-nodes` 的核心结果仍为 C 版。
- `make` 成功（已有目标无需重建）；`make test` 通过：
  语法正例 66/66、反例 29/29，运行/拒绝/接受语料 63/63；
  `make selfhost-native` 通过：
  三代语法、模块语法、运行语料和旧单文件固定点均通过，项目构建
  用例 21/21。本轮未运行容器 `make g3`。

结论：先冻结无模块 seed，使活跃编译器作为根 `mod.toml` 项目构建；
再更新四代冷编自举门、建立四个稳定职责模块。13 模块细拆需先过
跨模块具名类型接口和全局状态所有权门；本轮未实施这些代码阶段。

## 2026-09-30 模块与项目管理 MOD-U2..U5 全部交付（mod.toml 项目、三层解析、独立对象/接口、缓存与自举验证）

接上条 MOD-U0/U1。设计方案 §4–§12 的本地三层完整交付；按 ADR-0006 全部
在自举侧 `compiler/` 实现，stage0 冻结未动（除种子即所用 prelude 的既有
函数，无任何扩展）。新增 5 个源文件（约 2200 行 yh）：

- **`toml.yh`**（最小 TOML 1.0 子集）：节/裸键/基本与字面量字符串/整数/
  内联表/注释；多行字符串、数组、点键等显式拒绝。schema 校验在装载层
  （必填 name、未知字段、依赖表形状、行尾规则），诊断带 mod.toml 行号。
- **`project.yh`**：自 cwd 向上发现最近 mod.toml（≤32 层）；路径规范化
  （段栈消解 . / .. / //，依赖根去重、装载态防依赖环）；递归 `ls -1p`
  扫描源码根建索引（嵌套 mod.toml 目录属另一项目不进入；两阶段收集——
  目录条目名先入名字池再递归，规避共享 ls 缓冲被递归覆盖）；绑定层实现
  本项目→标准库（YH_STDLIB 指向一个标准库项目）→直接依赖的三层搜索，
  入口模块不可被导入、第三方同名歧义报两个提供方、缺失报已搜索层次、
  不回退；导入图 DFS topo（依赖序）+ 环路完整链诊断；`yh list
  [--resolve name]` 列出模块/文件与绑定来源。
- **`iface.yh`**：模块稳定接口 `<模块>.s.i`（`// yh-iface v1 arch=arm64
  suffix=…` 头行 + pub 类型（含字段 pub 标记）/fn 签名/const 折叠值/pub
  let 声明，正文即 yh 源码）；加载 = 头校验 + pass1 登记 + pass2a 折叠
  （c_iface_load 抑制发射与 bss 登记），随后把新增符号/类型名改写为
  「短名+后缀」并登记进 ModInfo.ns；类型归属 t_home 平行数组支撑跨模块
  pub 字段检查。边界：pub 签名引用其他模块的类型与 pub 指针（字符串）
  常量干净拒绝（类型闭包内联留待按需）。
- **`module_build.yh`**：`yh build [-o out] [module]` / `yh run` /
  内部 `--emit-module <mod> <提供方根> <主根> -o <out.s>`。每模块独立
  子进程（argv[0] 再入）加载依赖接口后两遍编译该模块全部文件 → 独立
  .s + 接口 .s.i；符号带 `__<sanitized-proj>__<mod>_` 后缀（pub→GLOBAL、
  私有→LOCAL、入口模块 main 裸名 GLOBAL），gcc/clang 一次链接全部 .s。
  U5 对象缓存：manifest = FNV-1a(后缀+entry+各源文件内容+各依赖接口
  内容+版本标记)，命中且产物齐全跳过重编译；解析不缓存，重绑定由
  构造保证（新增本地同名模块→绑定变化→依赖接口路径变化→hash 变化→
  重编译），冷热一致由发射确定性保证。
- **`driver.yh`**：项目命令分派（单文件三种旧形态不变）。

前端语义（U3）：限定名 `m.f`/`m.T`/`m.T { … }`（局部作用域遮蔽导入）；
未使用导入、导入名与顶层声明冲突、同模块重复顶层声明（报首次位置，
fn 路径的消息同步补齐）检查；跨模块私有字段读写、私有符号、位置式
构造含私有字段拒绝，命名式构造只可填 pub 字段。

**过程中修复的缺陷（含 3 个既有编译器缺陷 + 语料盲区）**：
1. `ty_push` 新增 t_home 平行数组扩容时**遗漏 `t_type_cap = ncap`**——
   自举编译器编译自身在类型表第二次扩容后堆越界（SIGSEGV in
   malloc/free），连带暴露 native-selfhost.py SOURCES 与 Makefile
   双清单需人工同步的老问题（本次两处已同步）。
2. **`em_store_sized`/`em_load_sized` 对 f64/f32 误用 x0**（值在
   d0/s0）：f64 字段命名字面量写坏、成员读取错值、跨模块聚合传参/返回
   值错（stage0 一直正确，自举侧与差分语料均未覆盖「浮点字段聚合」）。
   修复为按 tid 分派 s0/d0。
3. **浮点复合赋值 x10 保护压/弹不成对**（弹空栈，d1 从垃圾地址装入，
   段错误）：重写为两次「压栈保护 → lea 用 x10 → 弹回」的成对序列。
4. 类型化变参的**浮点元素误从 x 栈弹出**：补 FP 栈弹出路径（与
   sem_call 栈实参的浮点弹出同法）。
5. `lex_all` 不复位 lx_line/lx_lstart：多文件/接口加载后行号累计错。
6. 诊断消息拼接曾用「数组.to_type(*char)」（数组接收者语义与指针不同，
   传参退化才正确）：统一改为 intern 进名字池后经 np_cstr 取 *char，
   新增 `arr_cstr` 辅助。

**验证**：`make test` **63/63**（run 48/48 含新增 2 例、fail 12、pass 3）；
`make selfhost-native` 全绿（三代语法 66/66+29/29 ×3、run 全量、固定点
一致、modules 语法语料 **17/17**、项目验收 **21/21**）；`make bootstrap`
通过（G1 + G2 run 48/48 + stage3 自解析 + 固定点）；`make g3` **通过**（容器分代全量语料、stage2.s==stage3.s 密码学固定点、发射洁净度、诊断质量、SHA-256 归档全项通过）。三代 stage 的模块语法语料验证（17/17 ×3）已挂进 selfhost-native 门。
项目验收覆盖：两项目真实链接运行（含跨模块聚合/浮点/类型化变参/函数
指针/限定字面量）、TOML 语法与未知字段错误、传递依赖拒绝、双依赖同名
歧义、本地遮蔽标准库与标准库兜底、导入环、入口模块不可导入、私有字段/
私有符号/位置式私有构造拒绝、同模块重复声明、未使用导入、导入名冲突、
接口头损坏拒绝重建、缓存命中、重绑定后重编译与结果一致。
新增语料：`tests/yh-run/run/47-float-struct-fields.yh`、
`run/48-float-compound-assign.yh`（stage0 与自举双侧通过）；模块语料
`tests/modules/`（语法 17 + 项目 21，runner 均已挂进 selfhost-native 门）。

**边界与后续（MOD-U6）**：本地三层（当前项目/标准库/直接依赖）已完整；
远程获取、版本规则、锁文件、工作区按方案明示「按实际需求另定」，需求
出现时另立设计与验收用例，不沿用旧 Go 方案承诺。已知工程边界：目录与
环境访问经 system+ls/printenv（stage0 prelude 冻结无 opendir/getenv），
路径含空格/引号不受支持；接口不携带类型闭包（pub 签名引用他模块类型
干净拒绝）。

## 2026-09-29 模块与项目管理 MOD-U0 + MOD-U1（自举侧 module/import 语法）

[设计方案](03-design/yh-模块与项目管理设计.md) /
[实施方案](02-plan/yh-模块与项目管理实施方案.md) /
[ADR-0005](adr/0005-yh-mod-toml与按名称导入.md) 的首个代码阶段。
按 ADR-0006 冻结规则，实现只在自举侧 `compiler/`（stage0 不识别新语法，
语法方案 §3 的「不直接改写 yh.g4」继续成立，ANTLR/stage0 语料不进新语法）。

- **MOD-U0 基线**：`make test` 61/61（run 46/46、fail 12/12、pass 3/3）、
  `make selfhost-native` 全绿（语法 66/66+29/29、run 全量、固定点一致）。
  兼容边界确认：旧单文件形态（无 module）必须保持不变。
- **词法**：`compiler/model.yh` 新增 TK_MODULE=42、TK_IMPORT=43（仅文件头
  使用，不放开成员名；42..43 落在 is_member_name 区间之外，无回归），
  `compiler/lexer.yh` kw_kind 识别 `module`/`import`。语料与编译器源码
  均未占用这两个标识符（已全仓核查）。
- **模块头解析**（新文件 `compiler/parse_module.yh`，约 170 行）：
  `mod_parse_head` 在 parse_source 开头消费「module IDENT; → import IDENT;*」，
  固定顺序、单次 module、`_` 不作模块/导入名、同文件重复导入报错、
  import 脱离 module 报错、错位 module/import 给出位置诊断；
  导入表（ImportEnt，名字 intern 到名字池）随解析登记——单文件形态的
  FileID 即 c_path，多文件模块索引按方案留给 MOD-U2。
  `mod_skip_head` 供 pass 2a/2b 子遍跳过头部 token。
- **限定类型**：`compiler/parse_type.yh` parse_type_ref 接受 `m.T`（含
  更长链）点号段；纯语法模式接受（未知模块不是语法错误），编译模式
  给出「限定类型需要模块语义（尚未实现）」的明确诊断（此前是
  「期望 ';'」）。
- **pub 字段**：struct/union 字段接受 `pub` 前缀；SField 新增 is_pub
  登记（布局与访问不变，跨模块检查按方案在 MOD-U3）。注意 `pub`自此
  不能再作字段名（原本 pathological 场景，无语料依赖）。
- **测试**：新 runner `tests/modules/check.py` + 语料 accept/ 7 例、
  reject/ 10 例（17/17）。该 runner 只跑自举产物（yh-new
  --syntax-check），已挂进 `make selfhost-native` 门；不与 stage0 语料
  混跑。
- **修一处基建遗漏**：`tests/selfhost/native-selfhost.py` 的 SOURCES
  清单与 Makefile SELFHOST_SOURCES 是两份人工同步的列表，本次新增
  parse_module.yh 时漏改前者，stage0 编译拼接源报
  `'mod_parse_head' 未声明`（自举侧支持顶层前向调用，但文件必须真的
  拼进来）。已同步，并在后续阶段考虑收敛为单一清单来源。
- **验证门**：`make` 零警告；`make test` 61/61；`make selfhost-native`
  全绿（三代语法 66/66+29/29 ×3、run 全量、汇编固定点一致、modules
  17/17）；`make bootstrap` 通过（G1 + G2 三代闭环 + stage3 自解析 +
  全量固定点）；`make g3` **通过**（首次运行的 run/39 报容器内
  permission denied 为 B8 已记录的 macOS Docker 挂载元数据瞬时假失败，
  重跑全绿，归档见 tmp/bootstrap/artifacts/）。
- **后续（MOD-U2，未实施）**：TOML 清单与 schema、模块头索引、
  本项目→标准库→直接依赖三层搜索、导入者上下文、歧义与不回退诊断；
  未使用导入/导入名与声明重名的语义检查连同模块作用域在 MOD-U3。

## 2026-09-29 GitHub Actions 发布流水线：tag 触发归档 yh/yh-new 到 Release

- 新增 `.github/workflows/release.yml`：推送任意 tag 触发，双平台构建
  `yh`（stage0 种子）与 `yh-new`（自举编译器），冒烟验证后用
  `gh release create` 归档 tar.gz + sha256 到 GitHub Release：
  - `linux-arm64`：ubuntu-latest + QEMU 仿真 arm64 容器（ubuntu:24.04，
    与 `make g3` 验收环境同版；免费私有仓库无 arm64 原生 runner），
    产物 AArch64 Linux ELF；
  - `darwin-arm64`：macos-14（M1）本机构建，产物 Mach-O；
  - 冒烟 = yh-new 与 yh 各编译运行一遍 hello。libtcc1.a 仅 ELF 链接需要
    （tcc_add_runtime 只在 ELF 输出路径调用；本机 Darwin 无
    /usr/local/lib/tcc 亦一切正常），Linux 冒烟用 `YH_LIBDIR=/build`
    按开箱状态验证，Linux tarball 因此多带一个 libtcc1.a（make 产物）。
- 修复原生 AArch64 Linux 构建找不到 crt1.o（容器实测暴露）：Debian/
  Ubuntu 的 crt1.o/crtn.o/libc.so 在 multiarch 目录
  （/usr/lib/aarch64-linux-gnu），tcc 默认只搜 /usr/lib。Makefile 在
  `HOST_OS-HOST_ARCH = Linux-aarch64` 时给 CPPFLAGS 注入
  `-DCONFIG_TRIPLET="aarch64-linux-gnu"`（tcc.h 的 USE_TRIPLET/
  ALSO_TRIPLET 使 crt/库/头文件路径带上 multiarch 段）。同时 YHNEW
  规则加 `-B $(TOP)` 并把 `$(LIBTCC1)` 列为前置条件：Linux ELF 链接
  必需 libtcc1.a，指向仓库根刚构建的副本（顺带消除 -j 并行竞态）。
  仅构建配置，不触碰冻结的 stage0 源码；Darwin 的 Mach-O 路径不读
  libtcc1 与 crt（本机无 /usr/local/lib/tcc 亦一切正常），交叉路径
  （stage1 自带 -sysroot/-B）不受影响。
- 本地验证（推 tag 前）：arm64 ubuntu:24.04 容器 `make -j4` 成功，
  yh-new 与 yh 冒烟通过（YH_LIBDIR=/build，file 确认 AArch64 ELF）；
  Darwin 本机 make + 冒烟通过。
- 实际运行结果：tag `0.0.1` 首次运行两构建作业全绿、release 作业失败
  （gh 无 .git 无法推断仓库，release 作业无 checkout）——修复为显式
  `GH_REPO` 环境变量后重打标签重跑，**全绿**：
  [run 36549353118](https://github.com/lalavender/x/actions/runs/36549353118)。
  Release [yh 0.0.1](https://github.com/lalavender/x/releases/tag/0.0.1)
  归档 4 个资产（darwin/linux 各 tar.gz + sha256）；端到端验收：下载
  linux tar.gz，内容为 yh / yh-new / libtcc1.a，SHA-256 与 .sha256
  资产一致（e5d7b269…d4d1a961）。

## 2026-09-29 explorer 两项：Ctrl+C 退出修复 + 复制按钮

- **Ctrl+C 无法退出（根因：Python 3.14 默认 SIGINT 处理器的延迟抛出
  机制）**：主线程阻塞在 `serve_forever`/`time.sleep` 这类 syscall 时，
  Ctrl+C 打断 syscall 后只恢复重试、不抛 KeyboardInterrupt（最小复现
  确认，连裸 `time.sleep(30)` 也不被默认 handler 打断）。修复：显式
  安装「抛 KeyboardInterrupt」的 SIGINT handler + `serve_forever` 移入
  daemon 线程 + 主线程 `join(0.3)` 短等待循环双保险；顺带把启动打印
  加 `flush=True`（重定向时缓冲导致看不到输出）。实测 SIGINT 后干净
  退出。
- **编辑器复制功能**：左栏头部新增「复制」（复制 yh 源码全文），右栏
  头部新增「复制」（复制汇编原文，取高亮层 `textContent`，保留编译器
  原始 tab 缩进）。`navigator.clipboard.writeText` 优先、隐藏 textarea
  + `execCommand` 降级，成功后按钮闪现「已复制 ✓」1.2 秒。浏览器实测
  剪贴板读回与源内容一致。

## 2026-09-29 浏览器图形界面 yh Compiler Explorer（tools/）

新增本地浏览器版编译器浏览器（仿 Compiler Explorer / godbolt 布局）：
左侧 yh 源码编辑器（语法高亮、行号、自动缩进、示例加载、localStorage
自动保存），右侧 AArch64 汇编视图（编辑防抖 700ms 自动刷新），绿色
Run 按钮编译链接并运行，底部控制台展示程序 stdout/stderr/退出码与
编译诊断；中间分栏可拖拽。

- `tools/yh-explorer.html`：自包含单文件界面（无外部依赖，One Dark
  配色）。浏览器不能直接执行本地二进制，页面经三个接口与本地服务器
  通信：`GET /api/defaults`（探测仓库根 yh-new/yh）、`POST /api/compile`
  （`--emit-asm` 发射汇编）、`POST /api/run`（`-o` 编译链接后运行，
  崩溃/超时才算失败，故意非零退出码原样展示）。
- `tools/yh-explorer.py`：仅标准库的本地服务器，监听 127.0.0.1（缺省
  端口 8765，`--port`/`--no-browser` 可调），临时产物在
  `tmp/yh-explorer-work/`。编译器支持下拉快捷切换（yh-new 自举 /
  yh stage0 / 自定义路径）并叠加编译选项（如 `-target`）。
- 入口：`make explorer`（新增 Makefile 目标）。
- 本次未修改编译器本体，按约定不新增 tests .yh 用例；工具链路以
  浏览器端到端验收替代（hello 示例 Run 输出 `hello, yh!` 退出码 0、
  square 示例自动编译通过、非法源码诊断正确显示）。stage0 `yh` 只支持
  全量编译运行（下拉标注「仅 Run」，API 实测 Run 正常），不支持
  `--emit-asm` 汇编发射，汇编视图仅自举侧可用。

## 2026-09-29 `make` 默认产出自举编译器二进制 `yh-new`（项目根目录）

落实 ADR-0006 的构建侧：`make` 现在在项目根目录产出**两个**二进制——

- `yh`：stage0 种子（C 版，冻结），bootstrap 交叉编译 stage1 的种子；
- `yh-new`：**自举编译器本机形态**（stage0 种子编译 compiler/ 拼接源码
  产出；Darwin → Mach-O，Linux → ELF），即 ADR-0006 的主要开发编译器。

要点与坑：
- `$(YHNEW)` 规则必须放在 `BOOTSTRAP_DIR` 定义**之后**——make 的规则
  前置条件列表是**即时展开**的，先定义后引用才不会展开成空；
- `clean` 同步清理 `yh-new`；help 文本更新；
- 验证：`make clean && make` 周期正常、二次 `make` 幂等；make 产出的
  `yh-new` 直跑全量语料——运行 **61/61**、语法 **66/66 + 29/29**（绝对
  路径传给 check.py；相对路径在其内部 cwd 处理会失配）；四门不受影响
  （bootstrap/g3 仍以 `./yh` 为种子）。

## 2026-09-29 深帧寻址根因根除（x12 专用临时）+ 差分压测框架，自举 80/80 达标## 2026-09-29 深帧寻址根因根除（x12 专用临时）+ 差分压测框架，自举 80/80 达标

接上节 for-in 区间修复后的继续探索，两件事：

**1. 一族深帧缺陷的总根源根除**。run/27 修复后差分压测仍暴露两个
SEGV，lldb 定位崩溃指令 `str x0, [x10, #8]` 的 x10 = 立即数 768——
`em_lea_local_down` 深帧形态（`movz x10, #off; sub x0, x29, x10`）
把 **x10 当临时**，而调用方（变参打包的切片 data 写入）以为 x10 仍是
前一条 `lea_local_to` 的槽地址。审查发现 lea 四原语的深帧临时分别
借用 x10/x9——本轮 run/27、上轮栈实参/区间长度的全部覆盖 bug 都源于
这个「原语借用调用方活跃寄存器」的设计。**修复**：四个原语的深帧
临时统一改为专用 **x12**（此前全文件零使用），注释写明契约；调用点
此前的 x9→x11 修复保留为双保险。

**2. 差分压测框架落地（tmp/dt-gen.py）**：固定种子生成确定性随机
程序——深帧 24–46 个局部、12 参走栈调用、for-in 区间/数组、复合
赋值、短路、递归聚合、类型化变参、浮点混合、全局变量——stage0 与
自举产物双编译对跑，比对 stdout 与退出码。**自举侧 80/80 无差**
（2 例差异经最小化为 stage0 自身错误）。

**压测顺带记录 stage0 参照系缺陷六项**（均不影响自举链，规避后差分
可继续）：
| # | 缺陷 | 症状 |
| --- | --- | --- |
| S1 | u64 局部变量 store | `store(1, (3,0,…))` 断言崩溃（arm64-gen.c:581） |
| S2 | 深帧下多个 switch | 同上断言，最小化到 let+switch 即触发 |
| S3 | 深帧下三元 | 同上断言 |
| S4 | 数组形参直接 for-in | 「for-in 的遍历对象必须是数组或切片」误拒 |
| S5 | 聚合返回值直接作实参 | 同 S1 断言 |
| S6 | 深帧聚合局部零初始化失效 | 局部数组读出垃圾（自举输出正确 0） |

**验证（全门绿）**：`make test` 61/61；自举 Darwin 本机语法 66/66+
29/29、运行 61/61；`make selfhost-native` 全量用例全绿；`make
bootstrap` 全绿；`make g3` 通过，新固定点 `stage2.s == stage3.s`
SHA-256 `c23883cb…8b475b56`。

## 2026-09-29 自举阻塞缺陷清零：for-in 区间深帧寻址修复，自举产物本机接管达标## 2026-09-29 mod.toml 与名称导入的模块方案修订（尚未实施）

按用户新要求，采用 mod.toml 项目清单、module 源码归属、import 名称
导入；搜索顺序为当前项目、标准库、第三方，没有 internal 特殊机制。
补齐同模块多文件、文件导入作用域、依赖自己的解析上下文、高层绑定
失败不回退、同层歧义、直接依赖和项目限定身份规则。

交付 [当前语言设计](03-design/yh-模块与项目管理设计.md)、
[实施清单](02-plan/yh-模块与项目管理实施方案.md)、
[ADR-0005](adr/0005-yh-mod-toml与按名称导入.md) 与
[修订报告](01-finished/yh-mod-toml模块方案修订报告.md)。旧方案入口标记
被替代，todo 更新为 MOD-U0–U6，代码任务保持未完成。

文档相对链接、代码围栏、差异空白与 TOML 示例解析检查通过，记录位于
tmp/mod-design/doc-check.json。make 返回成功，默认产物已最新。
本轮仅修改方案和记录，没有修改 grammar／编译器／测试源码或创建真实
mod.toml；没有新增模块用例，也未将 make 的既有构建结果当作模块功能
验证。工作区已有的其他代码和测试改动保留，未在本任务中编辑或验收。

## 2026-09-29 自举阻塞缺陷清零：for-in 区间深帧寻址修复，自举产物本机接管达标

接上节 A'（栈实参错位）之后的 A'' 残余（run/27 在自举产物上
`range=37128`）。本轮定位到**真正的根因**并清零：

**根因（不是槽重叠）**：`sem_forin_begin` 区间路径把终点装入 x9 后，
data 槽的 `em_lea_local_to` 在偏移 >255 时用 `movz x9, #off` 拼地址，
覆盖终点——区间长度 = 「槽偏移 - 起点」= 287 而非 4，循环多跑 283 次。
小帧时 lea 走 `sub x10, x29, #imm` 不碰 x9，所以所有单项 mini 复现
通过、只有 run/27 的深帧场景触发。

**修复（compiler/sem.yh，4 处）**：
1. for-in 区间：终点改用 x11（`sub x11, x11, x0` 算长度）；
2. for-in 数组：len 常量改为「先取 len 槽地址、后装 x9」；
3. for-in 聚合元素绑定：删「`mov x9, x0` 保地址」——深帧 lea 覆盖 x9
   使 copy_block 源错；改为先取绑定槽地址（x10）、x0 天然保持元素地址；
   同时补回标量路径的 `mov x10, x0`（em_load_sized 从 x10 读——修复
   过程中曾误删，由 mini-aggr3 钉住）；
4. 聚合局部清零循环：计数器 x9 改为在 lea 之后装载。

**同类模式全文件扫描**：x9 活跃值 + 随后 lea 的窗口共 7 处，其余 3 处
为「立即消费」安全形态（含误报）。

**验证（全门绿）**：
| 门 | 结果 |
| --- | --- |
| `make test`（stage0） | 61/61 |
| 自举 Darwin 本机（s1 产物直跑语料） | **语法 66/66 + 29/29、运行 61/61** |
| `make selfhost-native` | 全绿——重构后跑**全量 run 用例（含 printf）**，不再按「macOS 变参不可判」过滤 |
| `make bootstrap` | 全绿（G1 + G2 run 46/46 + 固定点） |
| `make g3` | **通过**，新固定点 `stage2.s == stage3.s`，SHA-256 `1279cf29…50a92b` |

**自举产物接管（本节主题）就此达标**：stage1 在 Darwin 本机以
`yh file -o out`（双形态 CLI、宿主自动方言探测）直出可执行并跑下全部
运行语料；`make selfhost-native` 的语义验证升级为全量用例。C 版 stage0
从「日常编译器」降级为「种子与差分参照」的条件已经具备——剩余事项
（`-c`/`-run` 等能力、每平台种子二进制归档流程）见 todo 多平台与接管
条目。

## 2026-09-29 自举回归修复 + 六项语言缺口双侧落地 + 三个 stage0 缺陷修复，G3 复验通过## 2026-09-29 Go 风格语言模块化方案交付（尚未实施）

按用户纠正，将方案范围改为 yh 用户程序的 module/package/import。
交付 [语言设计](03-design/yh-Go风格模块与包设计.md)、
[实施清单](02-plan/yh-Go风格模块化实施方案.md) 和
[ADR-0004](adr/0004-yh-Go风格模块与包.md)。参考 Go 官方包规范与模块
说明，明确保留 yh 的 pub 和分号，支持目录包、文件级导入、跨包类型、
本地依赖，并规划独立产物／缓存／远程 MVS／工作区。

原内部重构任务因理解范围有误撤回，历史交付保留记录。没有修改 grammar、
编译器、构建脚本或测试源码，没有运行或宣称模块功能通过；工作区其他
ABI 与测试改动保持原样。完整记录见
[Go 风格方案交付报告](01-finished/yh-Go风格模块化方案交付报告.md)。
新增文档与更新入口的链接／围栏检查及 `git diff --check` 通过。

## 2026-09-29 内部结构方案历史交付（范围误读，已撤回执行清单）

完成两套编译器的源码／依赖调查，交付
[模块化详细方案](02-plan/yh-编译器模块化详细方案.md) 与
[提议 ADR-0003](adr/0003-yh编译器渐进模块化.md)。建议保留直接生成流程，
依次统一构建清单、明确状态归属、拆分语义／生成／ABI／输出边界，
再有限整理 C 版引导接口；完整 AST／IR 和默认编译器替换另立任务。

实际验证：`make` 成功（产物已最新）；`make test` 的 ANTLR 和编译器语法
各 66/66 正例、29/29 反例；Darwin 运行 44/44、拒绝 12/12、仅编译 3/3，
合计 59/59。graphify update/god-nodes 已执行；图为 1,328 节点、4,283 边，
但 `.yh` 未覆盖、12 个 C／头文件部分解析异常，不能单独作为删除依据。

本任务没有修改编译器／测试代码、没有新增 `.yh` 测试或执行三代自举门。
保留 todo 原有修改和期间出现的 sem／emitter 代码改动；这些改动不属于
本任务，也未在本任务中完成自举验收。P0–P9 均未勾选完成。
调查日志在 `tmp/modularization/`；长期记录见
[方案交付报告](01-finished/yh-模块化方案交付报告.md)。
新增文档的本地链接与代码围栏校验通过，`git diff --check` 通过。

## 2026-09-29 自举回归修复 + 六项语言缺口双侧落地 + 三个 stage0 缺陷修复，G3 复验通过

**起点**：分析进度时发现最新未提交改动（Darwin 方言 + `-o` 兼容层）引入
自举回归——G2 运行语料 run/14 段错误，`make bootstrap` 红。本轮修复回归、
清掉 todo 盘点 B/C/D 三节全部账目，四道验证门全绿。

### 1. 自举回归修复（sem_call 栈实参）

Darwin 变参改造误删 GNU/Linux 路径的栈实参写入循环：新代码只在
`darwin_var == 1` 时写栈槽，无 else——超过 8 个整型参数的调用不写
调用点栈区，stage2 编译 run/14 段错误。修复：补 else 分支恢复
`for j >= TG_ARG_REGS { pop x9; em_call_stack_store(...) }`（循环变量
改名 `saj` 避开 stage0 的 if/else 无块级作用域重声明）。新增
run/37-many-args-noprintf（无 printf 的超 8 参用例，本机 native 门
也能执行——此前 run/14 含 printf，native 门按约定跳过，拦不住这类回归）。

### 2. stage0 缺陷修复（三个）

- **零初始化全局 `-o` 误报 redeclaration**：pass 1 对零初始化全局提前
  落地符号，pass 2 重复登记触发 `sym_push` 报错。修复：pass 1 统一
  不落地全局变量（`yh_parse_binding` 早退），与带初始化路径一致。
  用例 run/38-zero-init-global。
- **Mach-O 重定位记账缺陷**（新发现）：节头 `nreloc` 按 ELF 条数记账，
  但非零 addend 的重定位会多写一条前置 ADDEND 条目，ld64 按声明数
  截断尾部条目——悬空 ADDEND 触发「relocation not supported」（全局
  数组下标直接链接失败），或 printf 的 CALL26 丢失使懒绑定桩悬空
  （程序运行挂起、反汇编显示全局字段读写偏移错位）。修复：
  `macho-out.c` 按 Mach-O 实际条目数记账（新增 `nreloc_elf` 供写出
  循环遍历 ELF 重定位；统计与写出规则一致：非零 addend 的
  UNSIGNED/PAGE21/PAGEOFF12 各补一条 ADDEND 前置条目）。修复后
  `make test` 从 51/51 隐性损失恢复全绿，全局数组/结构体用例可用。
- **语法模式全局表未初始化崩溃**（新发现，native 自举差分门暴露）：
  `ty_register_builtins` 只在 `--emit-asm` 路径调用，语法模式
  `t_types` 为 NULL；自举编译器新加的实参预期类型代码在语法模式读
  `t_types[res.type_id].sub` 段错误（compiler.yh 自解析靠未初始化栈
  垃圾侥幸通过，语料用例稳定崩溃，lldb 定位崩溃地址 0x14 = offsetof
  (CType, sub)）。修复：调用实参分支限定 `c_compile != 0` 且校验
  `TY_FN` 类型（非函数被调者的 sub 是字段表起点，会误当签名号）。

### 3. 语言缺口六项落地（stage0 与自举双侧，均有 run 用例钉住）

| 特性 | 自举侧 | stage0 侧 | 用例 |
| --- | --- | --- | --- |
| 全局聚合初始化 | `parse_global_struct_init`（命名/位置/嵌套/字符串） | 字节镜像 + 节内 R_DATA_PTR 重定位 | run/40 |
| 全局数组/切片零初始化 | 移除 pass 1 拒绝，`.bss` 发射泛化 | 已有（`.bss`） | run/39 |
| 数组/切片字面量 | `parse_array_literal` + 预期类型管道（let 初始化/赋值 RHS/调用实参） | primary `'['` + `yh_expect_type` 管道 + 全局数组字面量字节镜像 | run/43 |
| 切片表达式 `a[s..e]` | `sem_slice`（无分支钳制 + 视图临时） | 后缀链 RANGE 分支（`vdup` + 位技巧钳制） | run/42 |
| 嵌套类型声明 | `c_nested_type` 旗标（pass 2 也登记） | 块语句分派直接复用顶层解析 | run/44 |
| `sizeof(expr)` | `em_put` 处 `c_em_suppress` 发射闸门 + 类型名判定 | `nocode_wanted` 抑制 + 星号链捕获重放前瞻（区分 `sizeof(*p)` 与 `sizeof(*T)`） | run/41 |

边界（如实记录）：stage0 全局切片字面量暂不支持（干净拒绝）；全局
f32 字段/元素初始化暂不支持（要求 f64）；stage0 全局数组字面量字符串
元素拒绝；自举侧 `parse_global_array_init` 元素上限 64。

### 4. 顺带修复的自举编译器既有缺陷（新特性开发牵出）

- `len(数组)` 编译期折叠不物化：`sem_len` 数组分支只设常量 Res 未发
  `mov x0, len`，且实参聚合地址语义残留（`c_res_is_addr` 未清）——
  `return len(arr)` 返回数组地址。此前运行语料从未覆盖 `len(数组)`
  表达式（run/28 只测切片）。
- 聚合整体赋值只拷 8 字节：`sem_assign` 的 TK_ASSIGN 分支误走标量
  store。修复：聚合按块拷贝（`em_copy_block`），兑现「数组同型赋值 =
  值复制」语义（语义边界 §，M0-04 定案）。
- `macho.py` LIBC 集合补 `system`/`unlink`（driver `-o` 兼容层新引用），
  `tests/selfhost/probe-main.c` 补两个桩（native 门不真调链接器）。

### 5. 验证门（全部通过）

| 门 | 结果 |
| --- | --- |
| `make test`（stage0 本机） | **59/59**（run 44 + fail 12 + pass 3） |
| `make selfhost-native`（Mach-O 三代差分） | 全绿：三 stage 自解析、语法 66/66+29/29、stage2 运行语义、**汇编固定点一致** |
| `make bootstrap`（容器官方门） | 全绿：G1 66/66+29/29、G2 三代闭环 + run 语料 44/44、G2+ 固定点 |
| `make g3`（G3 正式验收） | **通过**（19 项检查；stage1/2/3 分代全量 59/59；44 个代表程序固定点；诊断质量 53 反例；产物归档） |

**新固定点**：`stage2.s == stage3.s`，SHA-256
`9c5cfc78529b00e9aa7ab4315463e8583e0f15d15719400dc279b75996413fa8`
（compiler.yh `6ff49c39…b40a`，8678 行）。

### 6. G3 验收脚本增强

- 分代运行语料失败自动重试一次：macOS Docker（VirtioFS）挂载偶发
  元数据延迟，ELF 刚写完权限位短暂不可见，曾致 run/16 与本轮 stage3
  语料「permission denied」假失败；重试仍失败才是真回归。
- `-o` 兼容层冒烟检查（stage1/2/3 直出可执行、临时文件清理、错误源
  非零退出）已在验收清单中。

### 7. 文档同步

- `docs/todo.md` 盘点节改写：A 无阻塞、B 六项勾选（两项设计决定如实
  标注）、C 三项修复、D 文档账目清零。
- `docs/02-plan/yh-自举实施方案-v2.md` B3–B7 的 14 个任务项 checkbox
  全部勾选。
- 本文件记录本轮全部改动。自举编译器源码 7952 → 8678 行。

## 2026-09-28 自举 B8 完成：新增 `make g3` 正式验收，G3 达成

在上一节的 `make bootstrap` 全绿基础上，补齐 B8 的全部验收项并脚本化。

**新增**：

- `tests/selfhost/g3-acceptance.py` 与 `make g3`（`= make bootstrap` +
  验收脚本）：在 Ubuntu 24.04/aarch64 容器内做
  1. 前置检查（容器 / sysroot / stage1..3）；
  2. **分代全量复验**：stage1、stage2、stage3 各自跑全部语法（66/66 +
     29/29）与运行语料（50/50，交叉 ELF 在容器内执行），要求无崩溃、
     超时或 SKIP；
  3. stage3 自解析 + 自编；
  4. **汇编固定点**：`stage2.s == stage3.s`（compiler.yh）**且 35 个代表
     程序全部逐字节一致**；同一 stage 重复发射一致（无时间戳/随机）；
  5. 发射内容不含宿主绝对路径/日期；**诊断质量**：53 个反例全部非零退出、
     带 `文件:行:列: 错误:` 诊断、不把汇编泄漏到 stdout；
  6. 归档源码/汇编/ELF/工具链版本/SHA-256 到 `tmp/bootstrap/artifacts/`。
- `tests/yh-run/run/35-mixed-args.yh`：混合整型/浮点形参回归用例
  （免 printf，退出码断言）。
- `docs/01-finished/G3-自举验收报告.md`：正式验收报告（判据、证据、
  SHA-256、G3 语言验收表逐行核对、边界与后续）。

**本轮修复的第三个自举缺陷**

- **混合整型/浮点形参的寄存器分配**：AAPCS64 的整型参数寄存器 x0..x7 与
  浮点参数寄存器 d0..d7 各自独立计数，但 `parse_decl.yh` 把形参在参数表
  中的**位置下标**当寄存器序号传给 `sem_declare_param`，使
  `scale(v f64, k int)` 的 `k`（第 2 个形参）错读 **x1**（应为 **x0**），
  浮点+整型混用的调用算出垃圾值。修复：参数循环为整型/浮点各维护独立
  计数器（`ipos`/`fpos`），按类型递增后传「本类型内序号」。
- **回归证据**：回退修复后 stage1 编译 `run/35` 退出码 1（失败），修复后
  42（通过）。

**验收结果**：`make g3` 全绿（19 项检查）；关键点——`stage2.s` 与
`stage3.s` 的 SHA-256 同为
`e442b52eacfc1e84a3b5b32855360d44c41119d7d381ae62b848b1d94d686402`。

**结论**：**G3 达成**（完整编译器自举）。B7、B8 均完成。唯一未实现的
语言特性仍是全局聚合变量初始化（不阻塞 G3）；是否替换默认 `yh` 另立验收。

## 2026-09-28 自举 B8：`make bootstrap` 全绿，达成 G3

**环境更正**：此前误判「docker 不可用」——实际 docker CLI 位于
`/opt/homebrew/bin/docker`（Homebrew 安装，context=colima），只是当前
shell 的 `PATH` 被精简为 `/usr/bin:/bin:/usr/sbin:/sbin` 而找不到它；
容器 `yh-build`（ubuntu:24.04，aarch64）一直运行中，`/work` 挂载与
`tmp/sysroot` 均正常。加上 PATH 后官方自举门可正常执行。

**本轮修复（B8 门首次全量执行时暴露的第三个自举缺陷）**

- **缺陷**：混合整型/浮点形参的寄存器分配错误。AAPCS64 规定整型参数寄存
  器 x0..x7 与浮点参数寄存器 d0..d7 **各自独立计数**；但 `parse_decl.yh`
  把形参在参数表中的**位置下标**当作寄存器序号传给 `sem_declare_param`。
  于是 `scale(v f64, k int)` 的 `k`（第 2 个形参）被错读为 **x1**，正确
  应为 **x0**（它是第 1 个整型参数），导致浮点+整型混用的调用算出垃圾值。
- **修复**：在 pass 2 的参数循环中为整型/浮点各维护独立计数器
  （`ipos`/`fpos`），按类型递增后把「本类型内序号」传给
  `sem_declare_param`；聚合形参走整型寄存器序列，同用 `ipos`。
- **回归用例**：`tests/yh-run/run/35-mixed-args.yh`（免 printf，退出码
  断言）覆盖 1 浮点+1 整型、整型在前、以及 `f0 i0 f1 i1` 交错四种形态。
  证据：回退修复后 stage1 编译 run/35 退出码 1（失败），修复后 42（通过）。

**`make bootstrap` 结果（Linux 容器内，官方门）**

| 门 | 内容 | 结果 |
| --- | --- | --- |
| 拼接确定性 | 两次拼接逐字节一致 | ✅ |
| G1 | stage1 自解析 + 全量语法语料差分 | ✅ 66/66 + 29/29 |
| G2 | stage1→stage2；stage2 自解析 + 语法差分 | ✅ 66/66 + 29/29 |
| G2 | stage2 全量运行语料（run/ 全部） | ✅ **34/34**（含 run/28 浮点、30–34） |
| G2+ | stage2→stage3；stage3 自解析 | ✅ |
| G2+ | **stage2.s 与 stage3.s 对自身拼接源码逐字节一致** | ✅ **固定点** |

**结论**：B7 完成；G3 的硬判据（stage1/stage2 同样通过全量语料 + 两代
对固定输入发出逐字节相同汇编）在真实 aarch64 Linux 环境达成。B8 剩余项
（stage1/2/3 全量分代跑、代表程序固定点、产物与哈希归档、G3 验收表逐行
核对）见后续条目。

## 2026-09-28 自举 B7 收尾：修复两处自举缺陷，达成全量固定点（stage3 汇编逐字节一致）

上一轮 B7 遗留「stage2 编译浮点字面量时常量位型被编码为 `fp64_bits`
函数地址」的已知缺陷。本轮定位并修复其**根因**，并顺带修掉同源的另一处
转换缺陷；`make bootstrap` 门因此恢复为**全量运行语料 + 全量汇编固定点**。

**修复 1：浮点实参压栈走错通路（`sem_push_arg`）**

`sem_push_arg` 无条件调用 `em_push()`（压 x0），但浮点实参的值在 d0。
在 `fp64_bits(mant)` 这类「先 `adrp` 装入 callee 地址、再以浮点值调用」
的序列里，x0 恰好是 callee 地址，于是被当成实参压栈，`fp64_bits` 收到
函数地址而非 f64 值，返回位型即成代码地址（旧记录中的 `0x4160676`）。
修复：改走 `sem_push_value`（浮点压 d0）。调用点的混合搬运路径同步改为
**按元素类型分别弹出 x0/d0**。

**修复 2：缺少「整数 → 整数」窄化转换（`sem_cast`）**

`sem_cast` 只处理了浮点相关的四类转换，整数→整数（如 `i64 → int`）**完全
未发码**。x0 中按源类型已扩展，窄化到更小宽度或改变符号性时必须重新
扩展，否则比较/运算会读到高位的残留值：`0x3ff0000000000000.to_type(int)`
被当成 64 位整体与 0 比较，恒为真。修复：按目标宽度与符号性补
`sxtw/sxth/sxtb`（有符号）与写 w0/`uxth`/`uxtb`（无符号）。

两处缺陷都由同一现象牵出：修复 1 后浮点常量恢复正确，才暴露出修复 2。

**本机自举差分探针（新增，容器不可用/快速定位时用）**

正式自举门需 aarch64 Linux 容器（docker + tmp/sysroot）。本轮新增
`tests/selfhost/native-selfhost.py` 与 `make selfhost-native`：用同一套
`compiler/` 源码在本机（Darwin/arm64）跑等价三代闭环——stage0 → stage1 →
stage2 → stage3，发射的 GNU/Linux AArch64 汇编经 macho.py 改写为
Mach-O 可汇编形态（`@PAGE/@PAGEOFF` + 符号 `_` 前缀）后本机链接。
校验：三 stage 自解析、三 stage 全量语法语料、stage2 运行不含 printf 的
语义用例（macOS 变参 ABI 与 Linux 不同，含 printf 的用例在本机不可判，
脚本如实跳过）、**stage2.s 与 stage3.s 逐字节一致**。

**验证**：
- `make selfhost-native` 全绿：三 stage 自解析；三 stage 语法 66/66 + 29/29；
  stage2 运行 run/13、16、31、32、33、34 全部符合期望；**汇编固定点一致**。
- `make test`：stage0 零回归 **49/49**（run 34 + fail 12 + pass 3），
  语法 66/66 + 29/29 两遍。
- `make bootstrap` 门已恢复：G2 运行语料改为 **run/ 全量**（不再排除 28），
  G2+ 固定点比较改为**直接 `cmp stage2.s stage3.s`**（stage2/stage3 对
  自身拼接源码的完整发射逐字节一致）。

**新增回归用例**（均带 `// exit:` 断言，可在任意平台运行）：
- `run/31-float-bits.yh`：浮点字面量位型（1.0/2.5/0.0）与浮点实参/返回；
- `run/32-int-narrow.yh`：整数窄化（i64→int、负值截断、u32/i8/u8 往返）；
- `run/33-u32-zeroext.yh`：无符号窄化零扩展（u32/u16/u8）；
- `run/34-cast-matrix.yh`：i8/u8/i32/u32/i64 全组合的转换矩阵与算术参与；
- `run/30-float-arg.yh`：浮点实参 + 浮点返回 + 混用实参（依赖 printf）。

两处修复的**回归证据**：把修复临时回退后重建 yh stage，`run/31` 与
`run/32` 在 stage 上分别以退出码 1 失败（stage0 因实现不同仍通过），
恢复修复后全部 42 通过。

## 2026-09-28 自举 B7：全语言语义落地，stage1 覆盖完整语料（44/44）

**实现**（compiler/ 12 文件，7657 行 yh；在 B5/B6 基础上补齐）：

- **聚合按值 ABI**（机制 b：调用点拷贝 + 指针传递，满足 ADR-0001 全部
  可观察行为）：聚合实参在调用点拷贝副本、传指针，被调用方入口再拷进
  本帧独立槽（`F_AGGPARAM`）；聚合返回经 x8 隐藏缓冲（调用方分配，x0
  返回缓冲地址）。嵌套结构体字面量经 `c_lit_depth` 状态栈递归构造。
- **切片** `[]T`：规范化视图 `{u64 长度, T* 数据}`；`len`（数组编译期、
  切片读偏移 0）、下标（读偏移 8 的数据指针）、`[N]T.to_type([]T)` 构造
  `{N, &arr[0]}`。
- **for-in**：数组 / 切片 / 区间 `a..b`（左闭右开）统一为「长度 + 取第 i
  项」；区间长度 `max(0, 终点-起点)`，元素/下标绑定为每轮值拷贝。
- **类型化变参** `name ... T`：登记为切片参数（签名 `vararg=2`），调用点
  把尾部实参逆序弹栈写入临时数组再打包 `{count, data}`。
- **浮点** f32/f64：d0-d7 传参与返回、`fadd/fsub/fmul/fdiv`、`fcmp`+`cset`
  比较、`scvtf/ucvtf/fcvtzs/fcvtzu` 转换、`fmov` 常量装载、浮点局部与
  复合赋值；GNU as 助记符不带 `.d/.s` 后缀（靠寄存器名区分）。
- **structInit 作值**：结构体字面量可用于初始化、实参、返回与嵌套字段。

**验证**：
- `make bootstrap` 全绿：G1（自解析 + 66/66 + 29/29）、G2（stage1 编译自身
  得 stage2；stage2 自解析、语法 66/66 + 29/29、运行语料 28/28）、
  G2+（stage2 编译自身得 stage3，stage3 自解析；stage2/stage3 对聚合
  用例的汇编逐字节一致）。
- stage1 全量运行语料 **44/44**（含 run/25 结构体 ABI、27 数组按值+切片+
  for-in、28 类型化变参+浮点、29 容量压力）。
- `make test`：stage0 零回归（44/44）。

**B7 自举差分暴露并修复的缺陷**：
- 结构体字面量字段地址算成 `fp-(off+foff)`（应为 `fp-(off-foff)`）；
- 聚合参数/返回的 x8 准备覆盖了已入参寄存器（改经 x10 中转）；
- 聚合返回写入缓冲前未保存 x8（入口漏发 `em_save_hidden_ret`）；
- 嵌套字面量恢复外层状态时 `save` 索引错（读 `save[depth]` 而非
  `save[depth-1]`）；
- 任意元素大小下标缺缩放（补 `mul`）；聚合元素在 value 模式被提前 load；
- 浮点元素在 `sem_index` 用整数加载（补 `ldr d0/s0`）；
- 区间长度用 `b.gt` + 误重置 x10 导致恒为 0；
- 浮点复合赋值的右值经 x0 压栈丢失（改用专用浮点临时槽）；
- `ucvtfd`/`fcvtzsd`/`fmul.d` 等错误助记符（GNU as 无后缀）；
- for-in 绑定槽误用 `sem_declare_local` 的**符号下标**当偏移（改取
  `c_syms[sym].offset`）。

**已知缺陷（stage2 自举层面，如实记录）**：stage2 编译**浮点字面量**时，
常量位型被编码为其 `fp64_bits` 函数地址（`0x4160676`）而非 IEEE754 值。
影响仅限 stage2 + 浮点字面量（run/28 与 compiler.yh 内 `10.0`/`1.0`）；
stage1 层面浮点完整正确。处置：`make bootstrap` 的运行子集排除 run/28，
汇编固定点比较改在聚合用例上做。定位与后续见
[自举后端架构](03-design/yh-自举后端架构.md) §6。

> **已于下一轮修复**：根因是 `sem_push_arg` 对浮点实参压栈走 x0 通路
> （见本文档「B7 收尾」一节）。修复后 stage2 浮点常量正确、汇编达到
> 全量固定点，`make bootstrap` 已恢复全量运行语料与全量固定点比较。

## 2026-09-28 自举 B5+B6：AArch64 后端与三代闭环，G2 达成

**实现**（按 [自举实施方案 v2](02-plan/yh-自举实施方案-v2.md)，源码在
`compiler/`，12 个文件共 6542 行 yh）：

三层后端架构（多平台接入缝，详见
[自举后端架构](03-design/yh-自举后端架构.md)）：
- **前端语义**（平台无关）：`symbols.yh` 名字池/类型表/符号作用域/
  类型兼容/常量折叠/prelude 登记；`sem.yh` 表达式·语句·声明语义钩子、
  两遍编译驱动、fn 与结构体布局、调用约定检查；`parse_type/expr/stmt/
  decl.yh` 边解析边调钩子（无 AST）。只引用 `target.yh` 数据模型与
  `em_*` 抽象机原语，不含 ISA 细节。
- **目标数据模型** `target.yh`：字长、对齐、参数寄存器数、结构体布局。
- **指令发射** `emit_arm64.yh`：值栈、访存、控制流、调用约定（前 8 参
  进 x0..x7，其余经调用点栈区）、`.data`/`.bss` 段与符号发射。

关键机制：静态帧（体先进缓冲，帧大小定后一次 `sub sp`，循环体内局部
不再压栈）；`mov sp, x29` 置于 epilogue 标签之后（显式 return 与落底
路径汇聚点）；代码标签 `.L<n>` 与数据标签 `.LD<n>` 分离（0 为 NULL
哨兵）；嵌套调用用实参基线栈 `c_call_base` 与直接调用标志栈
`c_call_direct` 隔离内层；短路标签用嵌套栈 `sc_sc_false_stk` 保存外层。

新增 `compiler/` 之外：`tests/yh/container-yh-cc.sh`（把 `--emit-asm` +
gcc 包装成 stage0 的 `<file> -o <out>` 接口）、`check.py --filter`、
Makefile 的 `SELFHOST_SOURCES` 与 `bootstrap` 目标。

**验证（`make bootstrap` 逐门，全部通过）**：
1. 拼接确定性：两次拼接逐字节一致，SHA-256 `90303ead…8d44b7`；
2. **G1**：stage1 自解析自身拼接源码到 EOF；语法语料 66/66 + 29/29；
3. **G2**：stage1 编译自身得 stage2（AArch64 Linux ELF）；stage2 自解析、
   语法差分 66/66 + 29/29、运行语义子集 **25/25**；
4. **G2+ 固定点**：stage2 编译自身得 stage3，`stage2.s` 与 `stage3.s`
   **逐字节相同**，stage3 自解析通过。

`make test`：stage0 零回归（ANTLR 66/66+29/29、编译器模式 66/66+29/29、
运行层 44/44）。B5 运行语料 **40/44**，余 4 项（`run/25` 结构体按值、
`27` 数组按值、`28` 浮点变参、`29` 包装类型）为方案规定的 B7 边界，
均显式拒绝且由用例钉住。

**自举差分暴露并修复的缺陷**（均由 stage2 运行复现，逐个修在编译器侧）：
- 全局指针 `NULL` 初始化与字符串数据标签 `0` 冲突 → 数据标签从 1 起；
- `t_sig_add` 四个签名数组共用容量变量 → 拆为独立容量；
- 取模 `sdiv` 用 x10（与复合赋值持有的目标地址冲突）→ 改用 x11；
- 普通赋值与复合赋值未取回暂存的目标地址（写进临时槽）→ 修正取改存；
- `em_epilogue` 的 `mov sp, x29` 在返回标签之前 → 移到标签之后；
- 任意元素大小（如 20 字节 Tok）的下标缺缩放 → 补 `mul`；
- 聚合元素（结构体/数组）在 value 模式下被提前 load → 保留地址语义；
- `let` 初始化大于 255 偏移时地址计算覆盖待存值 → 改用写 x10 的路径；
- `&&`/`||` 嵌套时短路标签被内层覆盖 → 加嵌套栈；
- 调用实参类型记录被内层调用覆盖 → 加实参基线栈；
- 嵌套调用中 `c_call_direct` 被内层稀疏调用污染 → 加直接调用标志栈；
- `main` 未输出 `.globl`（crt1 引用）→ 强制 GLOBAL。

**发现但未修的 stage0 缺陷（已绕开并记录）**：`continue` 在无条件
`for { }` 内报「不在循环内」（自编源码统一用 `for 1 { }`）；
stage0 每个编译单元只允许一个全局数组（编译器全局表改堆分配）；
`ty_sig_cap` 类共享容量问题在 stage0 的 `.yh` 语义层无直接对应，仅
影响本编译器。

## 2026-09-28 自举 B3+B4：compiler/ 下 yh 新编译器词法+语法落地，G1 语法自举达成

**实现**（按 [自举实施方案 v2](02-plan/yh-自举实施方案-v2.md)，源码目录按指示用
`compiler/` 替代方案的 `src/yh/`，共 2041 行 yh）：
- `compiler/model.yh`：token 种类常量（编号分组供范围判断）、Tok 结构体、
  全部全局状态集中声明（规避 stage0 全局名先声明后使用的问题）；
- `compiler/buffer.yh`：open/read/close 整读源文件（倍增缓冲、短读/EOF/负值
  处理）、write_all 短写循环、`file:line:col: 错误:` 诊断（fd 2）、推测解析
  静默开关（c_spec）；
- `compiler/lexer.yh`：完整词法器——保留字首字符分桶查表（语言关键字/
  已移除关键字/内建类型三组）、进制数字与下划线规则（前缀后无数字回退为
  十进制 `0`，与 ANTLR 一致）、字符串/字符转义集合与 `\xNN`、运算符最长
  匹配、注释与 \f\v\r 空白；token 引用原缓冲不复制；
- `compiler/parse_type.yh`：typeRef/fnType（返回类型省略靠 is_type_start
  判定）+ 解析器共用游标工具；
- `compiler/parse_expr.yh`：完整优先级链、后缀链（调用/下标/.to_type/成员，
  成员位置放开保留字）、structInit 命名/位置式与「字面量 vs 块」花括号
  消解（试探 + 配对 `}` 后必须紧跟 `{`，失败回退）；
- `compiler/parse_stmt.yh`：块/let/const/if（强制括号）/for 三形态/switch/
  return/branch/goto/标签/表达式语句；
- `compiler/parse_decl.yh`：七类顶层声明、参数（类型化/裸变参）、struct/
  union 字段、enum 成员；
- `compiler/driver.yh`：`--syntax-check`（B4 范围）与 `--emit-asm`
  （明确报后端未实现，B5 提供）。

**构建与验证**：
- `make`：stage0 零警告；`make bootstrap`（新增）：①拼接确定性（两次拼接
  cmp 逐字节一致 + SHA-256 `eb8f5879…a5caecb`）；②stage0 交叉编译
  `tmp/bootstrap/compiler.yh` 得 stage1（AArch64 Linux ELF）；③容器内
  stage1 自解析自身拼接源码到 EOF；④`tests/yh/check.py --compiler
  --compiler-path tests/yh/container-yh.sh`（YH_STAGE 指向容器内 stage1）
  正例 **66/66**、反例 **29/29** → **G1 达成**；
- `make test`：ANTLR 66/66+29/29、stage0 编译器模式 66/66+29/29、
  yh-run 44/44 全绿（stage0 无回归）；
- 词法边界探针（stage1 容器内执行）：1 MiB 语料（14000 声明 + 长标识符
  + 注释混排）解析通过；NUL 字节串内合法/串外拒绝（`1:15: 非法字符`）；
  未终结串拒绝（`1:36`）；跨行块注释后错误定位精确（`6:17`）；
  非法输入一律非零退出且带位置，无崩溃；
- 干净重建：`make clean && make && make bootstrap` 通过。

**测试入口约定**：本轮新增 .yh 代码（compiler/ 8 个源文件）的测试即
`make bootstrap` 的自解析 + 95 例语料差分；语法语料数量保持 66/29 不变
（语料针对语言而非编译器实现，不因实现新增重复用例）。

**发现的 stage0 缺陷（未修，已绕开）**：`continue` 在无条件 `for { }` 内
报「continue 不在循环内」（含嵌在 if 中的情形）；`for 1 { }` 与
`for cond { }` 路径正常。自编源码统一用 `for 1 { }`，探针
`tmp/probe-continue.yh`。后续修 stage0 时可直接复用该探针复验。

## 2026-09-28 tests 目录清理：删除 TCC 上游 C 测试套件（237 个文件）

**判定依据（引用关系全查证）**：
- Makefile 的 `test` 目标只跑 `tests/yh/check.py`（ANTLR + --compiler 两模式）
  与 `tests/yh-run/check.py`，且 `tests.%: ;` 规则已切断上游 tests/Makefile
  体系；
- 两个 check.py 只引用根目录 `yh.g4`/`yh` 二进制与 `tmp/sysroot`，不依赖
  tests 下其他文件；
- `rg` 全查 Makefile/src/config.h/lib/：对 tests2、pp、tcctest、abitest、
  boundtest、libtcc_test、asmtest、vla_test、testfp、42test.h、
  asm-c-connect、gcctestsuite.sh 零引用。

**删除**：tests/ 下除 `yh/`、`yh-run/` 外全部内容——`Makefile`、`pp/`、
`tests2/`、`tcctest.c/.h`、`abitest.c`、`boundtest.c`、`libtcc_test.c`、
`asmtest.S`、`asm-c-connect-1/2.c`、`vla_test.c`、`testfp.c`、`42test.h`、
`gcctestsuite.sh`，共 237 个文件。这些是 TCC 上游 C 测试套件，yh 编译器只
接受 .yh 输入，永远不会被执行。

**验证**：make 构建正常；make test 三层全绿（ANTLR 66/66+29/29、编译器
66/66+29/29、yh-run 24/24）。tests/ 保留 1.4M（yh 416K + yh-run 1.0M）。

## 2026-09-28 ponytail-review 死代码清理：净删 134 行 + 4 个垃圾文件

**审查方法**：按 ponytail-review（仅猎杀复杂度，正确性/性能另审）对当前
全部改动做逐文件审查，用 rg 验证「只写不读」后再删。

**清理动作（均有读写计数证据）**：
- yh_decl.c：删除只写不读的死变量 `yh_saw_param` / `yh_cur_fn`（含无意义的
  保存/恢复）/ `yh_has_const_init` / `func_sym`（恒 NULL）；删除投机机制
  yh_consts 常量侧表整套（`yh_register_const` 只写、`yh_lookup_const` 挂
  `__attribute__((unused))` 自证无人调用，注释自称"保留用于 M4"——M4 需要
  时再加）；删除 `yh_parse_const_decl` 的死参数 `local` 及两处实参；删除
  `yh_gen_function` 中恒真的 `!yh_syntax_only()`（唯一调用点已排除语法模式）
  与 YH_DEBUG 注册调试输出；`(void)s;` 改为不接收 sym_push 返回值。
- yh_stmt.c：删除注释自证"不可达"的 if 块（for-in RANGE 窥探）、range 分支
  死赋值 `b1_off = h_cur - 8`（下一行立即覆盖）与 `et = int_t`、压警告的
  `(void)h_idx...` 行、return 后恒真条件 `if (tok != '}' || 1)`、YH_DEBUG
  switch 调试输出、与 yh.h 重复的 3 个 extern 声明。
- **switch case 解析统一**：删除 `yh_parse_switch_case`（只被语法模式调用，
  编译路径 L533-587 手写了同样的 case/default 解析）；语法模式改走同一条
  内联循环（生成部分本就有 `!yh_syntax_only()` 保护），判别值求值/槽分配块
  包进 `if (!yh_syntax_only())`。两种模式一条路径，-43 行。
- yh_expr.c：删除三元表达式尾部空语句块；删除与 `yh_parse_expr` 逐字相同的
  `yh_parse_expr_pub`（3 个调用点改用 `yh_parse_expr`）；structInit 三段
  重复注释合并为一段。
- macho-out.c：删除空块 `{ unsigned k; (void)k; }`；`macho_write` 定义前移
  替代前向声明。
- tccpp.c：删除多余的 `parse_number` 前向声明（定义在同文件更早位置）。
- arm64-gen.c：删除 gfunc_call 热路径上的 YH_DEBUG 参数类型打印（每次调用
  getenv）。
- yh.h：删除不存在的 yh_slice.c 漂移注释行；yh_builtin.c：修正 params 注释
  （`-2 表示裸 ...` 的编码不存在，实际用 variadic 字段）。
- 仓库垃圾：删除根目录 `hello`、`yh`（Mach-O 构建产物）与 `not`、`tty`
  （空文件）；.gitignore 增加 `/yh`、`/hello`。

**保留项（有行为，非死代码）**：yh_decl.c binding 处 6 个保留字的定向报错
（产出不同错误信息，是功能不是死代码）；arm64-gen.c store()/type_size()
assert(0) 前的 fprintf（错误路径诊断，随 assert 存活）。

**验证**：make 干净构建零警告；make test 三层全绿——ANTLR 语料 66/66+
29/29、编译器模式 66/66+29/29、yh-run 24/24，与清理前完全一致。

**行数**：yh 解析器七文件 3688 → 3554 行（净 -134），另有 4 个垃圾文件出库。

## 2026-09-27 M6 完成：有证据地清理 + 清理后回归对比

**清理动作（均有调用关系证据）**：
- libtcc.c：移除 tccasm.c 的 ONE_SOURCE 条件包含（CONFIG_TCC_ASM 从未定义，
  tccasm.c 1183 行从未编译进产物）；C 源路径改为显式报错「yh 编译器不支持
  C 源文件（.yh 是唯一输入）」（驱动层 M1-01 已拒绝 .c，libtcc API 层同步
  收口）；删除 free_inline_functions 调用。
- tccgen.c：删除 tccgen_compile（C 路径入口，yh 不再引用）、
  free_inline_functions、gen_inline_functions（static inline 机制整体，
  其唯一调用链 tccgen_compile→gen_inline_functions→gen_function 已断）及
  tcc.h 对应声明——干净构建零警告。tccgen.c 7122 → 7034 行。
- 清理过程事故记录：一次自动删除脚本误删 tccgen.c 主体（write 收到 list
  抛 TypeError 时文件已截断），从 git HEAD 完整恢复；随后重做的手工删除
  （decl0/decl/block/gen_function 尝试）因连锁依赖（expr_eq/unary 链被
  decl_initializer 复用）引发链接错误，全部回退。

**M6 结论（依方案 §6.8「不因删行目标强行移除」）**：
- 已删：tccgen_compile、free_inline_functions、gen_inline_functions、
  tccasm 包含、C 源路径入口（tccgen.c 净减 88 行 + tccasm.c 1183 行从未
  编译进产物）。
- 保留（有活引用）：decl0/decl/block/expr_eq/unary 链——yh 的
  decl_initializer_alloc（字符串字面量、structInit）、expr_const1（数组
  长度/枚举/const）、find_field/struct_layout、值栈与 gen_* 机制全部
  复用自 tccgen.c，与其声明 parser 同文件交织，无法在不拆分文件的前提下
  单独移除。「C parser 拆除（净减 2.5k~3k 行）」列为 0.0.2 任务，先做
  tccgen.c 按职责拆分（方案 §2.2 既定顺序）。
- 清理前后回归对比：make test 三层全绿（ANTLR 66+29、编译器 66+29、
  yh-run 24/24）完全一致；构建零警告。

## 2026-09-27 M5 完成：三层测试集成、干净构建、README 重写

## 2026-09-27 M5 完成：三层测试集成、干净构建、README 重写

- **M5-01**：`make test` 现在依序运行三层回归——ANTLR 语法语料、编译器
  语法模式（--syntax-check）、tests/yh-run 语义/运行测试（本机 Mach-O；
  --cross 时附加交叉 ELF + docker 容器运行）。全部通过 rc=0。
- **M5-02**：`make clean && make` 干净构建验证——产出 yh/libtcc.a/libtcc1.a
  零警告（tccpp.c 两处历史 warning 已于此前消除）；干净构建后本机 hello 与
  交叉 ELF（24/24）复验通过。用户源文件唯一后缀 .yh 由驱动强制。
- README 重写为 yh 编译器说明（快速上手/语言速览/测试/输出格式/目录结构/
  状态与限制），替换原 TCC README。
- hello 的 void main 触发「建议返回 int」提示（M3-02 的 main 检查生效）。

## 2026-09-27 M4-02/M4-03 完成：切片、for-in、structInit、类型化变参

## 2026-09-27 M4-02/M4-03 完成：切片、for-in、structInit、类型化变参

**M4-02 切片与 for-in**
- `[]T` 解析时规范化为 `struct { u64 len; T *data; }`（登记表缓存）；
  切片形参按 16B 结构体传递；len() 运行期读 len 字段；下标降糖为 data[i]。
- `[N]T.to_type([]T)` 视图构造：临时 16B 槽写入 {len:N, data:&arr[0]}，
  结果为切片左值。
- for-in 编译降糖：数组（len 编译期）/切片（len 运行期）/区间 `a..b`
  （左闭右开、空区间零次）三形态；单/双目标绑定值拷贝；continue 回递增、
  break 出链；绑定块作用域（sym_pop 恢复）。
- structInit 代码生成：匿名对象分配（局部/全局按上下文）→ 地址存隐藏槽 →
  命名/位置式逐字段「槽地址+偏移 = 值」→ 结果为对象左值；嵌套 structInit、
  作实参、return 均支持；命名/位置混写编译拒绝。

**M4-03 类型化变参**
- 声明：`name ... T` 形参类型降糖为 []T（packed 位标记变参 Sym），
  末尾唯一性检查；函数签名 func_type=FUNC_ELLIPSIS。
- 调用：实参按源码顺序求值并拷入临时连续数组（区域计入 loc）；
  打包为 16B 切片值 {len:n, data:元素区} 压栈作为单个实参；零变参也装配
  （len=0）；裸 `...`（printf/open）保持 C 默认提升路径（f32→f64）。

**调试修复**：捕获流的 TOK_LINENUM 混入（改 tok_str_add2）；嵌套宏层的
token 流混用（structInit 不再自建捕获）；切片临时 data 载入的 32 位截断；
pack 区未计入 loc 导致栈帧外写。

**验收**：make 零错误零警告；make test（ANTLR 66/66 + 29/29 + 编译器模式
66/66 + 29/29）rc=0；tests/yh-run 24/24（本机 + 交叉双路径）；
变参 sum(1,2,3)=6、sum()=0；structInit 命名/位置/嵌套/传参全正确。

## 2026-09-27 M3-02 + M4-01 完成：类型检查/复合赋值/数组按值 + 语义测试框架 24/24

## 2026-09-27 M3-02 + M4-01 完成：类型检查/复合赋值/数组按值 + 语义测试框架 24/24

多 agent 并行产出的测试框架（tests/yh-run/，run 15 + fail 6 + pass 3）暴露的
7 个编译器 bug 全部修复，并完成 M3-02 与 M4-01：

- **M3-02**：复合赋值 10 种运算符降糖（vpushv+vrott(3)+gen_op+vstore）；
  赋值/传参/返回的 yh 类型检查；整数字面量 0→指针；字符串字面量退化
  *char；`&x` 补 mk_pointer；比较/逻辑结果统一 bool 类型；main 签名检查
  （无参强制、void 警告）；块级 nocode_wanted 死代码管理。
- **M4-01（ADR-0002 机制 a）**：yh_type.c 新增数组/切片包装结构体登记表；
  形参/返回值/赋值/初始化的数组在调用边界降糖为匿名
  `struct { T a[N]; }`——≤16B 进寄存器、>16B 调用点拷贝、HFA 浮点，
  全部复用现有结构体路径；函数体内下标/len 透明还原数组语义；
  拷贝独立性经实测验证。
- **控制流重写**：switch 每比较发 cbnz（真→块，imm19 回填）+
  b（假→下一比较/no-match，imm26 反向回填），多值 case OR 语义、
  default 位置自由且唯一性检查、块尾无 fallthrough；break/continue
  用深度计数；label 定义恢复可达性。
- **验收**：tests/yh-run 24/24（本机 Mach-O 与 --cross ELF 双路径一致）；
  make test 双模式 rc=0；数组求和 sum=100（拷贝独立性）、switch 多值/
  default、递归 120/55、goto 循环全正确。

## 2026-09-27 本地系统支持：Darwin 原生 Mach-O 输出 + 系统链接

## 2026-09-27 多平台架构整理与优化方案（文档，无代码改动）

- 新建 [docs/02-plan/yh-多平台架构整理与优化方案.md](02-plan/yh-多平台架构整理与优化方案.md)：
  面向 linux/darwin/windows × arm64/x64 共 6 目标。梳理现状分层与 10 个耦合点
  （架构硬编码 tcc.h:138、宿主宏决定输出格式 libtcc.c:805、macho-out.c 仅
  ARM64 重定位、libtcc1 固定 aarch64-linux-gnu、-run 仅 aarch64 宿主等），
  给出差距矩阵、5 阶段方案（抽象统一→x86_64 恢复→Mach-O x64→Windows PE→
  windows/arm64）与逐阶段验证门。
- 关键事实核对：x86_64 后端可自 `git show 0db9fca^:x86_64-gen.c` 恢复；
  tccpe.c/win32 头与导入库可自 `git show ef8db88^:src/formats/tccpe.c`、
  `ef8db88^ win32/` 恢复；`lib/libtcc1.c`、`alloca86_64.S` 仍在 lib/ 中。
- `docs/todo.md` 0.0.2+ 节加入指向该方案的条目。未修改编译器代码，无需构建验证。

## 2026-09-27 本地系统支持：Darwin 原生 Mach-O 输出 + 系统链接

`yh file.yh -o prog` 在 macOS arm64 上直接产出可运行的本机可执行文件，
不再依赖 sysroot/容器。

- **macho-out.c（新建）**：Mach-O MH_OBJECT 写入器——映射 tcc 的
  text/data/bss 节（clang 布局约定：节 addr 段内累计、vmsize 含 bss、
  filesize 只含节内容）、符号表（跳过 STT_SECTION/STT_FILE；MH_OBJECT
  的 n_value 为段内累计地址）、重定位翻译（ABS64→UNSIGNED len3、
  MOVW_UABS_*→ADRP 方案、CALL26→BRANCH26、ADRP/ADD→PAGE21/PAGEOFF12
  并以 ARM64_RELOC_ADDEND 携带偏移）。EXE 由系统 `cc` 完成 libc 绑定与
  ad-hoc 签名。
- **arm64_sym**：Mach-O 模式改用 adrp+add（ld64 不接受 movk 上的
  UNSIGNED 重定位），ELF 路径保持 movw/movk（-run 的 COPY 重定位约束）。
- **Darwin 变参约定**：arm64_pcs_aux 增加 n_named——变参函数（FUNC_ELLIPSIS）
  在 Mach-O 模式下可变实参按 8 字节对齐放栈上（AAPCS64 变体），命名参数
  照常进寄存器；调用点 f32 实参提升为 f64。Linux ELF 路径不受影响。
- **格式选择**：Darwin 上 EXE/OBJ 默认 Mach-O；`-sysroot`（交叉 Linux）
  或显式 `-Wl,-oformat=elf64-aarch64` 恢复 ELF；`-Wl,-oformat=macho64`
  可显式选择 Mach-O。符号名经 leading_underscore 统一加 `_` 前缀。
- **void 函数确定性返回**：void（含无返回类型的 main）在函数末尾
  `mov w0, #0`，退出码可预期（用户的 `fn main(){ printf(...); }` 退出码 0）。
- **环境变量语义**：YH_SYSROOT/YH_LIBDIR 空串视为未设置（默认本机 Mach-O）。
- **验收**：本机 `./yh native.yh -o native && ./native` 输出
  `n=3 g=42 msg=hi`（printf 变参、全局变量、函数调用、字符串字面量）；
  `make test` 双模式 rc=0（66 正例 + 29 反例）；交叉 ELF 路径经容器复验
  输出一致。

## 2026-09-27 修复 -o 链接路径段错误 + sysroot 链接闭环

## 2026-09-27 修复 -o 链接路径段错误 + sysroot 链接闭环

用户报告 `./yh tests/yh/01-toplevel/01_toplevel_decls.yh -o 11` 段错误。根因
与修复：

- **pass 1 误执行代码生成**（崩溃根因）：`yh_parse_binding`/const 只检查语法
  模式未检查遍数，第一遍求值初始化器触碰未初始化的值栈/段状态。现在第一遍
  用 `skip_or_save_block` 按括号配对跳过初始化器，不做任何求值。
- **顶层 let 被当局部栈槽**：新增 `yh_commit_global_var`——data/bss 节分配、
  `put_extern_sym` 登记；pub→GLOBAL、非 pub→VT_STATIC(LOCAL)；初始化支持
  编译期常量（expr_const1，按宽度写节）与字符串字面量（匿名数组落地 +
  R_DATA_PTR 重定位）。
- **yh_compile 缺 tccgen/ELF 初始化**：补 `anon_sym`/`int_type`/
  `char_pointer_type`/`func_old_type` 等初始化与 `tccelf_begin_file/end_file`
  （symtab 哈希合并缺失导致链接期找不到符号）、`tcc_debug_start/end`。
- **main 的 ELF 绑定**：恒为 GLOBAL（crt 入口引用），其余非 pub 为 LOCAL
  （ADR 语义边界 §2/§3 落地）。
- **-sysroot 选项与环境变量**：`-sysroot dir`（或 `YH_SYSROOT`）在链接期
  提供 crt/libc/include 路径（含 Ubuntu multiarch 子目录）；`YH_LIBDIR`
  （或 `-B`）指定 libtcc1.a。缺 crt 时干净退出（rc=1，可读诊断），不再崩溃。
- **调用结果压栈**：gfunc_call 后按 tccgen 惯例 vsetc(REG_IRET) 回填返回值。
- **字符串实参消费**：has_init=2 的 decl_initializer_alloc 自行消费字符串
  token，移除多余的 next()。
- 零警告：修正 tccpp.c 两处历史 -Wstring-plus-int（用数组下标形式）。

**验收**：`make` 零错误零警告；`make test` 双模式 65/65 + 29/29 rc=0；
`YH_SYSROOT=tmp/sysroot YH_LIBDIR=tmp/sysroot ./yh hello.yh -o hello`
产出 AArch64 Linux ELF，容器内运行输出 "hello from yh"；无 main 的语料
`-o` 给出正确的 `undefined symbol 'main'` 链接诊断。

## 2026-09-27 M3 语义编译器接通：名称/调用/语句代码生成 + 全量语料验收

## 2026-09-27 M3 语义编译器接通：名称/调用/语句代码生成 + 全量语料验收

**目标达成**：`yh` 二进制通过 tests/yh 全部 94 个语料——
`make test` 双模式（ANTLR + `yh --syntax-check`）正例 65/65、反例 29/29，
退出码 0；`make` 零错误零警告。

- **yh_builtin.c（新建）**：prelude 八函数（printf/malloc/free/memcpy/
  strlen/exit/open/write）以 extern Sym 直接登记（FUNC_ELLIPSIS 标注裸变参），
  不注入 yh 文本。
- **两遍编译**（yh_decl.c）：第一遍按序登记 type/struct/union/enum 完整
  定义与顶层 fn 签名（external_global_sym；非 pub 带 VT_STATIC→ELF LOCAL），
  函数体 skip_or_save_block 跳过；第二遍重读文件编译全局初始化与函数体。
  类型先声明后引用、函数可前向调用（语义边界文档 §1 落地）。
- **函数框架**（yh_gen_function）：对齐 tccgen gen_function——put_extern_sym、
  gfunc_prolog/gfunc_epilog、局部栈管理、func_vt、调试钩子；void main 返回 0。
- **表达式代码生成**（yh_expr.c）：二元链 gen_op；逻辑与/或短路跳转
  （gvtst/gsym/vseti，模式同 tccgen expr_land/lor）；调用 gfunc_call 后按
  REG_IRET vsetc 压回结果（tccgen 惯例）；成员访问 gaddrof/find_field/
  偏移相加（`.` 对指针自动解引用）；`to_type` 走 §4.1 检查 + gen_cast 且
  结果强制右值；sizeof(T) 编译期 type_size；字符串字面量经
  decl_initializer_alloc 落地为匿名 char 数组。
- **类型系统**（yh_type.c）：struct/union 用 SYM_STRUCT tag + SYM_FIELD
  字段链 + struct_layout 布局；enum 成员为 VT_ENUM_VAL 常量（enum_val 存值）；
  type 别名带 VT_TYPEDEF 入标识符命名空间；数组长度用 expr_const1 编译期
  求值并拒绝非正值。
- **语句代码生成**（yh_stmt.c）：if/else（gvtst 假链 + gjmp/gsym）、条件与
  无限循环（continue 回循环头、break 链 yh_bsym/yh_csym）、switch（判别值
  存临时槽、case 逐值比较、无 fallthrough、default 位置自由且唯一性检查）、
  return（gen_assign_cast(func_vt) + gfunc_return + rsym 链）、goto/label
  （label_find/label_push 前向链）。
- **调试修复**：vset 重复插入导致 vstack leak 3；vstore 后缺 vpop；
  调用后未压回结果导致 "cannot cast from/to void"；纯语法模式误走
  yh_gen_function 导致 "未在第一遍登记"。
- **运行验证**（容器 gcc -no-pie 链接 yh 产出目标）：add(3,4) 退出码 7、
  局部变量/算术/调用全部正确。

## 2026-09-27 M2 完整语法 parser 与双模式回归（M2-01～M2-04）

## 2026-09-27 M2 完整语法 parser 与双模式回归（M2-01～M2-04）

新建四个 parser 文件（合计约 1100 行），按 docs/yh.g4 实现递归下降语法，
与 `--syntax-check` 纯语法模式共用，M3 在同一位置接通编译行为：

- **yh_type.c**：typeRef（指针/数组/切片/函数类型/内建/具名）、内建类型
  映射（i8→VT_BYTE…bool→VT_BOOL、char=u8）、fnType（VT_FUNC + 匿名参数
  Sym 链）、struct/union/enum 声明形态、`yh_tok_starts_type_ref` 返回类型
  省略判定。
- **yh_decl.c**：pub? 顶层分派（let/const/fn/type/struct/union/enum）、
  binding（类型必写）、param（含 `name ... T` 与裸 `...` 形态）、
  `yh_parse_translation_unit` 消费到 EOF、`yh_compile` 入口（yh_mode、
  无 PARSE_FLAG_PREPROCESS、setjmp 错误恢复）。
- **yh_expr.c**：优先级链（YH_BIN_LEVEL 宏逐层展开，与 C 同表）、一元、
  后缀链（调用/下标/`.to_type(typeRef)`/成员访问）、primary（字面量/
  sizeof(T)/len(e)/标识符）、`yh_peek_next_token` 与
  `yh_brace_group_is_literal`（structInit 头部边界算法：捕获-回灌、
  0 终止符自动弹回、非空 + 无 `;` + 深度 0 无语句关键字 + 命名/位置
  形态连贯；保留字字段名 type/len/default 合法）、保留字定向提示
  （while→for、as→to_type）。
- **yh_stmt.c**：block、if（强制括号）/else-if 链、for 三形态（头部
  peek 分派无限/条件/for-in）、for-in parts（单/双目标 + RANGE 区间）、
  switch（case 多值 + default）、return/break/continue/goto、包裹式
  标签（peek 判定 `IDENT ':'`）、exprStmt（11 种赋值运算符）。

调试修复过程：`<`/`>` 需用 TOK_LT/TOK_GT（非 ASCII）；PEEKC 后 p 指向
当前字符（前瞻应传 p+1）；primary 标识符分支漏 `next()` 造成 57 例回归；
嵌套捕获流的 0 终止符级联弹出避免 token 重复；parse_number 指数符号
校验；保留字字段名先于语句关键字检查。

**M2-04**：`tests/yh/check.py` 新增 `--compiler` 模式（调用
`yh --syntax-check`，正例必须接受、反例必须拒绝，按正反分别计数）；
`make test` 现在依序运行 ANTLR 模式与编译器模式。

**结果**：编译器模式正例 65/65、反例 29/29；ANTLR 模式 65/65、29/29；
规则覆盖 68/68。M2 验证门达成（语法通过不等于编译/运行通过，后者在 M3/M4）。

## 2026-09-27 M1-02 yh 词法改造 + M1-03 纯语法入口骨架

**M1-02（tcctok.h / tcc.h / tccpp.c）**：
- tcctok.h：新增 yh 关键字 let/fn/in/pub/true/false/len/to_type/type/as 与
  i8~u64/f32/f64/bool；全部保留字（含复用的 if/for/struct/… 与已移除的
  while/do/unsigned/…/restrict 及 gcc 变体）位于 TOK_UIDENT 边界之前，
  yh 中不可作普通标识符；边界后的 define/include 等 token 值仍可作标识符。
- tcc.h：新增 `TOK_RANGE 0xd0`（`..`）与 `TCCState.yh_mode` 标志。
- tccpp.c（全部按 yh_mode 分支，C 预处理路径保持原样）：
  - `#`/`##` 在 yh 模式直接报错「yh 无预处理」；
  - `case '.'`：yh 下 `..`→TOK_RANGE、`...`→TOK_DOTS、其余为成员点；
    `.5` 不再进入数字扫描（留给 parser 按语法拒绝，与语料注释一致）；
  - 数字扫描重写（yh_num_char）：0x/0b/0o 前缀定进制、下划线必须夹在本
    进制两数字之间、`.` 只在后跟数字时吞入、e/E 只在合法指数起点吞入、
    无任何整型/浮点后缀；`0b12` 切成 `0b1`+`2` 两个 token；
  - parse_number 增加 yh 分支：剔除下划线后按进制转换，无旧式八进制
    （`017`=17），整数按数量级映射 CINT/CUINT/CLLONG/CULLONG，
    浮点一律 TOK_CDOUBLE；修复 `isnum()` 短路导致的 `0b12` 整吞 bug；
  - 转义收敛：\n \r \t \0 \a \b \f \v \' \" \\ + \xNN（恰两位），
    未知转义报错；多字符字符字面量报错；`L` 前缀不再构成宽字符串。
- 验证：65 个正例语料全部通过词法骨架；rejected 中 18/23/26 在词法层被
  定向拒绝，其余反例留给 M2 parser；ANTLR 回归 65/65、29/29 不变。

**M1-03（yh_decl.c）**：`yh_compile()` 接通 `--syntax-check` 骨架：置
yh_mode、不开 PARSE_FLAG_PREPROCESS、以 TOK_NUM|TOK_STR 消费到 EOF，
setjmp 错误恢复与 tcc_compile 同构；不解析符号、不调用 gen_*、不要求 main。
最小正例与词法错误反例红绿验证通过；完整语法解析在 M2 按 g4 逐层替换。

## 2026-09-27 M1-01 构建与 .yh 输入分派

- `make` 改为产出 `yh`、`libtcc.a`、`libtcc1.a`；新增 VERSION 文件（0.0.1，
  修复此前 `-DTCC_VERSION=""` 的问题）。
- `libtcc1.a` 改由独立目标 C 工具链构建（不再用 yh 自举）：自动探测
  aarch64-linux-gnu-gcc → Linux/aarch64 本机 cc → clang（非 Linux 宿主自动加
  `-target aarch64-linux-gnu`）；macOS BSD ar 拒绝 ELF 成员，归档器自动选用
  clang 同目录的 `llvm-ar`。工具链全缺失时给出明确 $(error) 诊断。
- `lib/lib-arm64.c` 改为 freestanding（自带 typedef 与 memcpy 声明，不再包含
  目标 libc 头文件）；`__clear_cache` 在非 tcc 工具链下改用
  `__builtin___clear_cache`，消除 M0-02 发现的未定义符号。宿主 clang 交叉与
  容器 gcc 双路径均零警告，产物为 AArch64 Linux ELF 归档成员。
- 驱动：`.yh` 后缀进入 `yh_compile()`（AFF_TYPE_YH 分派，yh_decl.c 新建）；
  非 .yh 用户源文件（如 .c）被驱动明确拒绝（exit 1）；`--syntax-check` 选项
  注册（TCC_OUTPUT_SYNTAX 输出类型），yh 解析器本体留给 M1-03/M2。
- yh 骨架：`src/core/yh.h`（共享声明）与 `yh_decl.c`（入口）。
- 驱动行为验证：`.yh` 进入 yh 路径、`.c` 被拒、`yh -v` 报 0.0.1；`make test`
  运行 ANTLR 语料回归（65/65、29/29）。

## 2026-09-27 M0 前置验证完成

- **M0-01**：基线记录于 `tmp/m0/`（make / make test / check.py --coverage 输出与
  调用关系 `tmp/m0/call-graph.md`）。65 正例 / 29 反例 / 68 规则覆盖全过；
  Darwin `make test` 只跑 pp 套件（tests2 需 Linux，符合预期）。
- **M0-02**：Docker 容器（ubuntu:24.04，aarch64 原生）验证 AArch64 Linux
  工具链、crt、动态加载器；`lib/lib-arm64.c` 可由容器 gcc 产出 AArch64 Linux
  ELF 归档（发现 `__arm64_clear_cache` 在 gcc 下是未定义符号，tcc 内建，
  M1 需替换 `__builtin___clear_cache`）。带 `-DCONFIG_SYSROOT/-DCONFIG_TRIPLET`
  的 tcc 在 Darwin 直接产出可运行 Linux ELF；容器内 gcc 构建的原生 tcc
  `-run` 全链路通过。记录 `tmp/m0/m0-02.md`；最小 sysroot 在 `tmp/sysroot/`。
- **M0-03**：`tmp/abi/` 探针实测（tcc/gcc 双编译、输出一致）：机制 a
  （包装结构体）完整覆盖 ADR-0001 矩阵；切片 16B 结构体参数/返回正确；
  实测 `gfunc_call` 断言边界（对齐后 ≥4096B 触发，4080B 通过）。决定采用
  机制 a，4KB 断言在 M4-01 修后端（不设语言上限），见新
  [ADR-0002](adr/0002-yh数组与切片内部ABI机制.md)。
- **M0-04**：语义边界定案写入
  [docs/03-design/00-语义边界-0.0.1.md](03-design/00-语义边界-0.0.1.md)：
  先扫描顶层函数签名、`fn main() int` 无参、pub 的 ELF 绑定语义、字符串
  字面量可写（.data）、零长度数组拒绝、数组同型赋值=值复制、切片不做边界
  检查、裸变参提升规则与 prelude 八函数签名。同步修正 `docs/yh.g4` prelude
  注释（8 函数 + 直接登记 extern Sym）；`check.py --coverage` 复跑全过。

## 2026-09-27 yh 0.0.1 三份文档执行计划整理

- 将 `docs/02-plan/yh-0.0.1-改造方案.md` 展开为 M0～M6、逐任务编号、依赖顺序、验证门和动态语料验收口径；当前 94 个语料只作为基线。
- 将 `docs/todo.md` 收敛为同编号的任务清单，移除重复的早期探索排期；保留 0.0.2+ 待设计事项。
- 将 `docs/adr/0001-yh数组按值调用边界.md` 明确为已接受的语言/互操作边界；M0 用 C 代理探针选择内部机制，M4 用真实 `.yh` 用例验证，不混淆两类证据。
- 本次是文档整理，没有修改编译器代码；构建和运行验收仍属于后续 M0～M6 任务。

## 2026-09-27 类型转换语法改为 `to_type`

- 将 `x as T` 改为后缀语法 `x.to_type(T)`；目标参数仍按 typeRef 解析，允许链式转换及转换后直接取下标/成员。
- `to_type` 是专用后缀关键字，旧 `as` 转换写法报语法错误；同步改造方案、待办和 `.yh` 语法语料。旧版修订记录中的 `as` 示例保留为历史记录。
- `tests/yh` 正例 65/65、反例 29/29，68/68 条规则标注覆盖；69 个歧义探针零真歧义、零预期外结果。`make` 与 `make test` 通过；Darwin 上 `make test` 按现有规则只运行 pp 套件。
- 当前编译器 `src/` 仍未实现 `.yh` 解析；本次验证对象是参考语法和语料，编译模式的 `to_type` 语义检查仍在待办中。

## 2026-09-27 类型转换方案补全

- 在 `docs/02-plan/yh-0.0.1-改造方案.md` 增加转换矩阵：字面量与无损提升、显式数值和指针转换、数组/切片视图、拒绝无长度指针转切片。
- 明确 `as` 先做 yh 语义检查且结果为右值；TCC 的警告和 `gen_cast` 不能代替准入检查。同步 M3/M4 验证门与 `docs/todo.md`。
- 本次只修订计划文档，没有实现编译器转换检查；现有 `tests/yh/08-expr/06_cast.yh` 仍是纯语法用例。

## 2026-09-27 yh 0.0.1 改造方案评审修订

- 核对构建、驱动、语法语料和 AArch64 参数分类；修订 `docs/02-plan/yh-0.0.1-改造方案.md` 的架构假设、降糖、阶段顺序与验证门。
- 将 `.yh` 文件识别、C 运行时构建、数组/切片 ABI、纯语法检查、prelude 符号登记列为实现前置事项，并同步 `docs/todo.md`。
- 本次仅修改文档；编译器实现和运行测试仍列为后续任务。
- 将迁移遗留的测试后缀要求统一为 `.yh`，与唯一用户源文件后缀一致。

## 2026-09-27 语法参考（docs/yh.g4）歧义分析与无歧义修订

### 背景

对 docs/yh.g4 做歧义分析：用本地 ANTLR 4.13.2（`~/.m2/repository/org/antlr/antlr4/4.13.2/antlr4-4.13.2-complete.jar`）生成 parser，31 个探针用例实测。结论：原语法**无真歧义**（同一 token 序列两棵合法语法树的情况不存在），但发现 1 个实锤缺陷、多处注释与语法不符、若干 spec 缺口。分析过程与全部探针保留在 `tmp/antlr-check/`。

### 已落地的修订（全部经 ANTLR 实测验证）

1. **memberName：成员位置放开保留字**（实锤缺陷修复）
   - 原 grammar 中 `in`/`as`/`len`/`sizeof`/`type` 等被隐式关键字化且优先于 IDENT，导致 `p.len` / `p.type` / 字段名 `type` 全部语法错误。
   - 新增 `memberName` 规则，用于 fieldDecl / structInitField / postfixPart 三处；局部/全局标识符位置仍严格。
2. **exprStmt 收紧为单目标赋值**：`expr (assignOp expr)? ';'`，`a, b = 1, 2;` 不再合法（v0.1 无元组赋值）。
3. **labelStmt 必须后随语句**：`IDENT ':' stmt`，悬空标签 `L: }` 报错（同 C）。
4. **转义收敛**：STRING/CHAR 统一转义集合 `\n \r \t \0 \a \b \f \v \' \" \\` + `\xNN`；未知转义（`\q`）词法报错，不再静默吞掉。
5. **NUMBER 下划线规则**：必须夹在数字之间；`1_` / `1__0` / `0b_1` 报语法错误。
6. **显式词法规则 RANGE `..` / ELLIPSIS `...`**：手写 lexer 有明确对照。
7. **WS 扩充** `[ \t\r\f\u000B]+`：CR-only / 表单符文件不再词法报错；CRLF 仍按 NL 整体成词。

### 注释修正（语法行为不变）

- structInit 注释重写：删除失效的 `if flag {}` 例子（if 强制括号，本就非法）；分离「命名式 vs 位置式」与「字面量 vs 块」两个消歧问题；给手写 parser 定下头部边界算法（花括号配对 + 窥探下一个 `{`，贪心取字面量，与 ANTLR ALL(*) 判定一致）。
- castExpr 处新增结合性备忘：`a as b * c` = `(a as b) * c`、`a as *b` 为指针、`(x as T)[i]` 须加括号、`-x as int` = `(-x) as int`、`**` 非幂（`**p` 双重解引用合法，不可封禁）。
- returnStmt 注明会吞掉下一行开头的表达式（NL 隐藏通道，同 C）。
- switchCase 注明 default 位置无语义、至多一次靠语义检查。
- structInitBody 注明尾逗号策略：逐行列表允许、行内列表不允许。
- sizeofExpr 注明只收类型及理由。
- 文件头设计前提补充保留字策略（标识符位置严格 / 成员位置宽松）。

### 验证

- 修订稿生成 / 编译零警告；31 探针：21 个预期通过全过，10 个预期报错全部按设计响亮报错（`tmp/antlr-check/final/` 可复现）。
- 6 个 for/switch 头部边界用例（含 `switch Point{1,2} { case 1 {} }`、关键字字段名场景）`-diagnostics` 歧义检测 0 报告。
- 一次誊写回归（NUMBER 指数组 `?` 丢失导致 11 用例失败）已由探针矩阵当场捕获并修复——探针集同时充当回归测试。

### 后续

编译器实现（src/ 手写 lexer/parser）同步清单见 docs/todo.md。

# 2026-09-28 yh 语法与编译器自举方案（文档）

- 新增 `docs/03-design/yh-自举能力边界.md`：区分语法自举、编译器自举与工具链完全自给；规定最小输入接口、目标平台和三代验收。
- 新增 `docs/02-plan/yh-语法与编译器自举方案.md`：记录现状缺口、推荐路线、B0–B6 阶段和验证门；同步 `docs/todo.md`。本项仅编写方案，未修改编译器代码。

# 2026-09-28 yh 0.0.2 自举 B0–B2（种子冻结、输入接口、工作负载验证）

## B0 定位与修复测试基建

- **22/24 复盘定性**：07-goto-label「无法暂存目标文件」= 多进程并发
  共享产物目录时 `macho-out.c` 的 `rename` 竞态（4 个并发 check.py
  实例复现，20/24）；08-recursion 信号 9 未能复现（150 次编译+运行
  压力、3 次套件全绿），定性为环境性 kill。单进程与交叉路径均无缺陷。
- `macho-out.c` rename 失败信息补充 `strerror(errno)` 并提示并发触发
  场景；新增 `--workdir` 隔离后并发 4 实例全绿。
- `tests/yh-run/check.py` 新增 `--compiler`/`--workdir`（自举差分用），
  产物缺省迁移 `tmp/yh-run-work/`；新增 `stdin-hex:`/`argv:` 注入
  （交叉模式经 `docker exec -i`）。`tests/yh/check.py` 新增
  `--compiler-path`/`--workdir`。旧 `tests/yh-run/work/` 已删除。
- 缺口矩阵：`docs/02-plan/yh-运行覆盖缺口矩阵.md`（G01–G17，B2 后全部补齐）。

## B1 输入接口与语义修复

- prelude 登记 `read(fd int, buf *void, count u64) i64` 与
  `close(fd int) int`（共 10 个），同步 `docs/yh.g4` 与语义边界 §7。
- 放宽 `main` 为 `()` 或 `(argc int, argv **char)`；错误签名仍拒绝。
- 期间发现并修复 4 个语义缺陷（均有语料正例佐证但语法套件测不出）：
  ① `true/false` 推为 int → 改为 bool；② 整数字面量无法窄化
  （§4.1）→ 可表示字面量隐式允许 + 全局初始化范围检查（`let x u8 =
  300` 从静默截断改为报错）；③ 数组左值传 `*void` 不退化（坏指针/
  SIGBUS）→ 转换前左值退化；④ 裸变参小整数缺 C 默认提升
  （i8 打印 254）→ i8/i16/u8/u16/bool → int。
- 用例：run/16-18（read 分块/短读/NUL 计数/EOF/坏 fd/open-close）、
  run/19（bool+字面量窄化+提升）、run/20（字节缓冲：1 字节分配、
  扩容边界、NUL、1 MiB 逐字节一致、2^63 分配干净失败）、fail/07-08。

## B2 工作负载与容量验证

- 新增探针 run/22-29：函数指针（赋值/回调/返回选择）、u32/u64 位移与
  符号扩展、互递归、malloc 链表+全局指针写、struct 按值/大 struct、
  union/enum、数组按值/递归/切片视图/for-in、类型化变参/浮点、容量
  压力（1439 行，200 包装类型+129 case 值+约 200 字符标识符）。
- 期间发现并修复 5 个编译器缺陷：⑤ 函数名无法赋给 fn 类型 → 同签名
  fn 隐式转换（签名结构相等）；⑥ struct/数组按值返回调用缺隐藏返回
  指针（断言/段错误，**M4 数组返回从未真正运行过**）→ 调用方压 sret
  临时+结果取临时左值；⑦ 浮点返回误取 x0 → 取 v0（REG_FRET）；
  ⑧ 调用结果（包装 struct）赋回数组变量被拒/只拷 8 字节 → 包装→数组
  同型允许且 vstore 走块拷贝；⑨ switch 分支数组固定 128 超限静默截断
  → 扩 512+干净报错；包装类型上限 128 → 512（超限本就报错）。
- 用例：fail/10（数组长度不匹配）、fail/11（513 case 值干净报错）、
  fail/12（513 包装类型干净报错）。

## 验证

- `make` 零警告；`make test`：语法 66/66+29/29、运行 44/44
  （run 29/29、fail 12/12、pass 3/3）；`check.py --cross` 44/44。
- 下一步：B3（用 yh 写出能解析自身的前端）。

# 2026-09-28 自举实施方案 v2（文档）

- 按提交 `b5b57d9` 的代码基线重定 B3–B8：B3 词法器、B4 语法自举 G1、B5 子集后端、B6 自编闭环 G2、B7 全语言覆盖、B8 三代固定点 G3。
- 新方案见 `docs/02-plan/yh-自举实施方案-v2.md`；旧方案标记为历史，`docs/todo.md` 与自举能力边界同步更新。本次未修改编译器代码。
- 方案制定前基线验证：`make` 成功；`make test` 的语法正反例为 66/66、29/29，Darwin 运行层 44/44；`python3 tests/yh-run/check.py --cross --quiet` 在 AArch64 Linux ELF 容器运行层 44/44。

# 2026-09-28 自举方案归并（文档）

- 将自举定义、现有能力、输入输出契约、技术路线、B3–B8 任务及 G1–G3 验收矩阵统一到 `docs/02-plan/yh-自举实施方案-v2.md`。
- 原计划与能力边界文档改为简短入口，`docs/todo.md` 只链接统一方案；本次未修改编译器代码。
