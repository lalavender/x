# yh 后端接入 LLVM：可行性与差距分析

日期：2026-10-14。状态：**分析稿，未动任何编译器代码**；结论供决策，实施任务在
决策后另立实施方案。
核对基准：工作区当前源码（`git log -1 = e7ed840`，工作区有未提交改动）、
`docs/todo.md`、`docs/03-design/yh-自举后端架构.md`、
`docs/03-design/yh-Nanopass风格优化架构.md`。

后续方向（2026-10-14）：用户已明确目标为最终替换后端，本轮仅授权方案交付。
当前处理入口为 [问题清单](yh-LLVM后端替换问题清单.md) 与
[替换实施方案](yh-LLVM后端替换实施方案.md)。本稿保留盘点时的建议与观察值；
具体 API、语义及 ABI 判断须按新设计和固定工具链核实，不作为未经验证的语言契约。

> 历史注记（2026-10-20）：`asm/`、`link/` 两个独立项目已按用户决定删除；
> 下文提到它们的路径与状态仅记录分析当时的情况。

## 0. 结论摘要

1. **今天"接入 LLVM"最大的成本不在 LLVM，而在 yh 自己还没有可表达全语言的中间表示。**
   现有 `compiler/ir/ssa.yh` 是函数级、纯标量（整数/布尔）的 typed SSA，
   全量自编 991 个函数上下文里只有 22 个进入 SSA（2.2%，
   `compiler/README.md:171`）。直接写一个 LLVM 发射器，能编译的只有这 2.2%。
2. **旧发射器是 arm64 专用的汇编文本发射器，且与 SSA 后端通过「在同一个输出缓冲里
   做文本替换」混合**（`compiler/backend/arm64.yh:371` `arm64_emit_replace`）。
   这意味着：非 arm64 目标**没有回退路径**——x86_64 / Windows 想靠 LLVM 拿到，
   前提取决于 lowering 是否 100% 完成；而 arm64 上又必须解决"一个模块里两套代码生成器"
   的混合问题（LLVM IR 无法与手写汇编文本同缓冲混排）。
3. **工具链依赖与自包含是硬约束冲突点**：当前构建只依赖入库种子 + 系统 cc（`make`），
   运行时（`printf/malloc/free/memcpy/strlen`）由编译器自己发射 arm64 汇编，
   门禁明确断言**对象无未定义符号、自编编译器不导入 C runtime 的这几个符号**
   （`tests/selfhost/runtime-memory.py:114-137`）。走 LLVM 就多一条外部工具链依赖，
   并且 LLVM 合法化阶段会自行插入 `memcpy/memset` 调用——自包含性质需要重新设计。
4. **建议路线：先做"LLVM 当 oracle"（低成本、立刻有用、不动默认路径），
   再决定是否把它升为正式后端。** 这与仓库既有做法一致：
   `asm/tests/*` 早就用 `llvm-mc`/clang 做差分 oracle，发现顺序是
   `LLVM_MC` → Homebrew 默认 → clang 集成汇编器（`asm/tests/check_corpus.py:30-77`）。
5. 若目标只是"多一个 CPU 架构"，**自写 x64 发射器可能比接入 LLVM 更省**；
   若目标是"拿到优化器与寄存器分配"，要同时决定
   [NP4/NP5](../03-design/yh-Nanopass风格优化架构.md)（自家机器 IR + 线性扫描 + SCCP/LVN）
   是否取消——否则是同一件事做两遍。

---

## 1. 现状事实（有据可查）

### 1.1 编译流水线

```
源 .yh
  └─ lex/lexer.yh
       └─ parse/parse_*.yh（边解析边调 gen/sem_*.yh 钩子）
            ├─ ast/ast_*.yh  typed AST 视图（2026-10-12 自 parse 拆出）
            │     └─ ast/ast_ir_build.yh → ir/ssa.yh（受支持函数）
            │           └─ backend/arm64.yh（文本替换进汇编缓冲）
            └─ gen/sem_*.yh + gen/emit_arm64.yh（**其余函数**：直接发 AArch64 汇编）
                    ↓
            每模块一份 .build/asm/<mod>.s
                    ↓ cc -c（gcc/clang）或 yh_link asm      ← cmd/link_cache.yh:395/379
            .build/obj/<mod>.o
                    ↓ gcc -no-pie -o out <objs> -lm（Darwin: clang）  ← link_cache.yh:541
                   可执行文件
```

关键事实：

- **前端与发射耦合**：`gen/emit_arm64.yh` 是前端唯一的目标发射器，
  前端只调用 `em_*` 抽象机原语（`docs/03-design/yh-自举后端架构.md:42-58`）。
  换目标在文档里的契约是"**新 `target_<isa>.yh` + 新 `emit_<isa>.yh`**"，
  即"再写一个汇编发射器"，不是"换成 LLVM"。
- **SSA 是旁路补丁，不是主干**：受支持函数先由旧发射器发射，再用
  `arm64_emit_replace` 把那段汇编**文本替换**成 SSA 后端的文本
  （`compiler/backend/arm64.yh:369-445`）。混排机制建立在"两边都是同一方言的汇编文本"上。
- **工具链发现**：汇编器当前按 `yh_link` 名字查找（`cmd/link_cache.yh:155-201`），
  `make` 刻意不产出该名字，因此实际总是回落系统 cc（`Makefile:19-29`）。

### 1.2 IR 的能力边界（决定 LLVM 能编译什么）

`compiler/ir/ssa.yh`：

| 项 | 现状 | 位置 |
| --- | --- | --- |
| 类型 | `void/bool/i8..u64/f32/f64/ptr` 13 种；`ptr` 的 `elem` 必须指向**本函数类型表**内的类型 | ssa.yh:14-26、61-65、141-164 |
| 指令 | 24 个：CONST/算术/比较/位运算/DIV/REM/PHI/LOAD/STORE/COPY/PARAM/CALL/CAST | ssa.yh:29-52 |
| 终结 | BR / COND_BR / RET / UNREACHABLE | ssa.yh:55-58 |
| 结构 | **只有 `IRFunction`**：没有全局变量、常量池、字符串池、模块级类型池、模块级符号表 | ssa.yh:117-138 |
| 内存 | LOAD/STORE 的类型必须与 `ptr.elem` 精确相等；**没有 alloca、没有取地址指令、没有 GEP** | ssa.yh:254-274 |
| 调用 | 只有**直接符号调用**（`IRCall` 带符号名字节）；ABI 有 `abi=0/1`（yh/C） | ssa.yh:90-103 |
| 浮点 | 有 `f32/f64` 类型，但**没有一条浮点指令**，`CAST` 也只允许整数↔整数 | ssa.yh:241-247 |
| 实际 lowering | `ast/ast_ir.yh:24-39` 只把标量类型映射进 IR；支持判据见 `backend/arm64.yh:10-18、37-77`（只整数/布尔） | — |

`docs/todo.md:206-217` 的 R2a 剩余清单就是这份缺口清单：
负数字面量、switch、goto/label、嵌套循环、for-in、一元 +/− 与浮点、
聚合/内存语义（LOAD/STORE/取地址/按值拷贝）、间接调用与变参、
单文件与 `--emit-asm` 共用新后端、双平台 ABI 验收。

### 1.3 运行时与 OS 层（自包含是既有硬门）

- 编译器**自己发射** `printf / malloc / free / memcpy / strlen` 的 arm64 实现，
  内部直接 `svc #0`（`gen/emit_runtime_memory.yh:9/113/180/524-537`，
  标志位见 `gen/model.yh:230-235`）。
- 门禁断言：fixture 对象 `nm -u` **必须为空**；自编出的编译器二进制
  **不得**从 C runtime 导入 `malloc/free/memcpy/strlen/printf`
  （`tests/selfhost/runtime-memory.py:114-137`）。
- 宿主层也是 arm64/Linux 直写：`linux_syscall6` 内建（`gen/symbols.yh:1101-1106`）、
  `cmd/clock.linux.yh`、`cmd/project_dir.linux.yh`（getdents64）。
- prelude 外部接口清单：`printf/malloc/free/memcpy/strlen/exit/open/close/mkdir/read/write`
  （`gen/symbols.yh:1109-1169`），其中裸变参只在内建里用。

### 1.4 门禁与自举约束

- `make`：种子 `bin/yh-linux-arm64`（Linux/aarch64 ELF，已入库）冷编 `compiler/` → 根 `yh`。
- `make test`：ANTLR 参考语法 + 编译器语法模式 + 运行语料（299 例，2026-10-13）。
- `make selfhost-native`：**候选两代全部模块 `.s`/`.s.i`/`.s.ct` 逐字节固定点**
  （`tests/selfhost/native-selfhost.py:9`）+ 自解析 + 全量语料 + 模块语料 18 例 +
  项目验收 95 例；另含 runtime-memory / link-cache / scratch-isolation 等专项门。
- 对象/链接缓存键 = `.s` 内容哈希 + 工具名字符串 + flags + 编译器二进制指纹
  （`cmd/link_cache.yh:300-330`、`cmd/module_build.yh:43-66`）。

### 1.5 本机环境（今天实测）

WSL（Ubuntu，x86_64）已注册 `qemu-aarch64` binfmt，`bin/yh-linux-arm64` 可直接执行；
LLVM 工具链**齐备**：`clang 21.1.8`、`llc 21.1.8`、`llvm-as`、`opt`、`llvm-config`、
`llvm-mc`（`/usr/lib/llvm-21`）。`docs/todo.md:69-71` 里"llvm-mc 未安装"一条
在本机已不成立（那是当时 WSL 的状态）。

> **版本含义**：LLVM 21 已不支持 typed pointer，`.ll` 只能写 `ptr`；
> 这意味着最低版本选择必须显式写进设计（见 §3 R6）。

---

## 2. 接入 LLVM 还需要什么

按依赖顺序分五层，每层给"完成判据"。**L1 是真正的瓶颈，L2 只是收尾工程。**

### L0 决策（人拍板，先于一切编码）

| # | 决策项 | 选项 | 影响 |
| --- | --- | --- | --- |
| D1 | LLVM 的定位 | ① 验证 oracle；② 第二后端（可选）；③ 正式唯一后端 | 决定 L1 的"完成"定义与工期量级 |
| D2 | 目标平台 | 只要 arm64（Linux/Darwin）／还要 x86_64／还要 Windows | 只要 arm64 时收益最小、风险最大（与自家后端重复） |
| D3 | 是否接受默认构建硬依赖 clang/LLVM | 接受／仅限 `--backend llvm` 时依赖 | 影响种子滚动、CI 矩阵、发行物自包含声明 |
| D4 | NP4/NP5（自家机器 IR + 寄存器分配 + SCCP/LVN）是否保留 | 保留／降级／取消 | 避免同一件事做两遍 |
| D5 | 最低 LLVM 版本与允许的语法子集 | 建议 ≥17 并只用保守子集 | 决定能否用 `c"..."`、`nsw/nuw`、`switch` 等 |

### L1 IR 补齐：把"函数级标量 SSA"升级成"可表达全语言的模块级 IR"

这是**前置条件**，不做完，LLVM 后端只能编译 2.2% 的函数。

| # | 缺口 | 今天的样子 | LLVM 需要什么 | 完成判据 |
| --- | --- | --- | --- | --- |
| L1.1 | 模块级实体 | 只有 `IRFunction`；全局/字符串/`.bss` 由 `parse/parse_global_init.yh` + 发射器直接写 `.data` | `@g = global/constant`、私有字符串全局、对齐、只读 | 与现有 `.data` 镜像等价的差分运行 |
| L1.2 | 聚合类型与布局 | 类型表只有标量 + `ptr`；结构体布局在 `gen/target.yh:100-143` 算 | 模块级 `%T = type {…}`，且 **DataLayout 必须与 `tg_layout_struct` 逐字段一致** | 布局探针：`sizeof/offsetof` 两路对照 |
| L1.3 | 内存/取地址 | 无 alloca/取址/GEP；LOAD/STORE 只能作用于 PARAM/CALL 得到的指针 | `alloca`、`getelementptr`、显式 `align` | run/11、24、27 双路一致 |
| L1.4 | 浮点 | 有类型无指令，`CAST` 禁浮点 | `fadd/fsub/fmul/fdiv/fcmp/fpext/fptrunc/sitofp/…` | run/28、35 双路一致 |
| L1.5 | 间接调用/函数指针 | CALL 只有直接符号；用户裸变参被拒 | 函数指针类型 + 调用签名 + 变参约定 | run/22 双路一致 |
| L1.6 | 控制流补齐 | 无 switch/goto/label/for-in/嵌套循环（`docs/todo.md:206-217`） | 降为 CFG（可用 `switch` 指令） | run/05、06、07、27 双路一致 |
| L1.7 | extern C ABI 边界 | 前端已有 `gen/abi_c.yh` 分类器；SSA 只有整数 | C ABI 用 LLVM 原生类型（HFA、小聚合、x8 sret、Linux/Darwin 栈差异） | 与 clang 编出的 C 程序**双向**互操作差分 |
| L1.8 | 语义锁定 | 除零/移位/未对齐/bool 内存表示/未初始化局部没有书面契约 | 先写进设计文档，再两个后端同时实现 | 新增 run/fail 探针全绿（见 R3） |
| L1.9 | verifier/序列化扩展 | `ir_verify` + `ssa_serialize`（版本 5）只覆盖现有 op | 新 op 的校验规则与版本升级 | `tests/modules/projects/irverify` 扩展并通过 |

### L2 LLVM 发射器（新模块，例如 `compiler/backend/llvm*.yh`）

- **输出形态**：文本 `.ll` + 外部 `clang -c`（推荐）或 `llc`。理由：与仓库既有
  "自有汇编 + 显式 argv 调外部工具"风格一致；`asm/tests/check_corpus.py:30-77`
  的发现顺序（环境变量 → 平台默认 → clang 回退）可直接复用。
  **不推荐**进程内链接 LLVM-C API：无 IRBuilder、API 按版本锁死、把编译器的链接
  变成对 `libLLVM` 的硬依赖，且 Darwin 默认不带该 dylib。
- 需要实现的内容：模块前导（`target triple` / `target datalayout` / 类型池 /
  声明 / 全局）、函数发射、**双 ABI 模式**（yh ABI 建议降级为显式 `i64`/`ptr` 签名，
  C ABI 用 LLVM 原生类型）、符号与 linkage（`internal`/`private`/`dso_local`、
  `.globl` ↔ `external`、寄存器同名符号的 `__yhreg` 后缀、非 ASCII 需引号转义）、
  对齐、trap 语义、移位掩码、bool 表示、确定性输出顺序。
- 完成判据：`llvm-as` 结构校验通过 → `clang -c` 成功 → 差分运行一致 →
  两代 `.ll` 逐字节固定点。

### L3 工具链 / CLI / 缓存

| 项 | 需要什么 | 判据 |
| --- | --- | --- |
| 发现顺序 | `YH_CLANG`/`YH_LLC` → PATH → 编译器同目录（照 `mb_asm_tool` 模式） | 门禁 wrapper 能观测到真实调用 |
| 版本门 | 解析 `clang --version`，低于最低版本给明确诊断 | 负例测试 |
| CLI | `--emit-llvm`、`--backend llvm`（或 `YH_BACKEND`）；`yh build` 默认仍是 arm64 | 现有接口零回归 |
| 编译参数 | `-ffreestanding -fno-builtin -fno-stack-protector -fno-pic -fno-pie` 等**必须显式钉住**，与 `gcc -no-pie` 终链一致 | 终链成功 + 无意外符号 |
| 缓存键 | 后端身份 + LLVM 版本 + flags 进对象/链接键（今天键里只有工具名字符串） | 换 LLVM 版本必冷重建 |
| 门禁 | `tests/selfhost/link-cache.py` 的 assemble/link 计数、`runtime-memory.py` 的未定义符号断言，都需要 LLVM 版口径 | 专项门通过 |

### L4 运行时与目标 OS 层（LLVM **不提供**这部分）

- 自包含运行时：`memcpy/strlen/malloc/free/printf` 今天是手写 arm64 汇编 + `svc`。
  LLVM 路径要么用 yh/LLVM IR 重写一份，要么接受 libc → **与"对象无未定义符号"门冲突**，
  必须显式改门或改设计（见 R9）。
- 目标 OS 层：`linux_syscall6` 内建是 arm64 专用（`x8` + `svc`）。
  x86_64 Linux 是 `syscall` + `rdi/rsi/rdx/r10/r8/r9`；Windows 没有 syscall 语义，
  必须走 Win32 API（可经 `@[extern]` C ABI 声明）——这是**独立于 LLVM 的工作**。
- 宿主层（编译器自己跑在哪）：`cmd/clock.*.yh`、`cmd/project_dir.*.yh`、
  open 旗标等都是按宿主分支的直写实现；换宿主是另一件事，LLVM 帮不上。

---

## 3. 可能存在的问题（按严重度）

### R1 覆盖度与"无回退路径"（阻塞级）

- 现象：SSA 只覆盖 2.2% 函数；旧发射器 arm64-only。
- 后果：**在 x86_64/Windows 上，LLVM 后端一旦启用就没有可回退的路径**，
  任何未 lowering 的语法直接编译失败；在 arm64 上则可以"混着发"，
  但混排机制（文本替换）对 LLVM 不成立。
- 缓解：① 先做 oracle（只对 SSA 子集发 `.ll`，不影响产物）；
  ② 真要混合，只能用 LLVM `module asm "…"` 把旧发射器的文本整块塞进模块，
  但那样 `.ll` 就被钉死在 arm64 方言上，"多平台"收益归零，且 assembler 文本与
  LLVM 的节/符号处理边界容易出错。**建议不要走混合**。

### R2 三套 ABI 并存（高危）

- 并存的三方：旧发射器（yh ABI：8 字节槽 + 聚合按指针 + x8 返回）、
  SSA/arm64 后端（复用 `gen/abi_c.yh` 分类器）、LLVM 后端。
- 只要还有"部分模块/部分函数走旧路径"，三者对**同一符号**的接口必须逐位一致，
  否则错值不报错（历史上已出现过同类缺陷：
  `docs/finish.md` 的混合参数、跨模块单字节指针形参等）。
- 建议：yh ABI 在 LLVM 里**不借用 LLVM 的聚合降级**，而是自己降成显式
  `i64`/`ptr` 签名（yh 的 yh-ABI 本来就是"8 字节槽"模型，
  `backend/arm64_call.yh:54-62`）；C ABI 才用 LLVM 原生类型。
  浮点参数必须用 `float/double` 声明，才能落 d0-d7 并保持
  "整型/浮点各自计数"的既有规则（`docs/03-design/yh-自举后端架构.md:132-137`）。
- 必须新增：**ABI 等价差分门**（同一签名分别经旧发射器 / SSA / LLVM / clang C 四方互调）。

### R3 语义未锁定（高危，跨目标会真的分叉）

| 场景 | 今天 arm64 上的实际行为 | LLVM/x86_64 上的行为 | 建议 |
| --- | --- | --- | --- |
| 整数除零 | `sdiv/udiv`：**AArch64 返回 0，不陷入** | LLVM 里除零是 UB（可任意优化）；x86_64 `idiv` **SIGFPE** | 先写语义契约 + run 探针，再决定是否显式判零 |
| `INT_MIN / -1` | AArch64 SDIV 返回 `INT_MIN` | x86_64 `idiv` **SIGFPE** | 同上 |
| 移位量 ≥ 位宽 | `lslv/lsrv/asrv` 按 **63** 取模（先算 x 再窄化），常量折叠也是 `& 63`（`ir/ssa.yh:961-970`） | LLVM `shl i32, 32` 是 **poison** | 要么显式掩码后发射，要么统一改成按位宽掩码并同步改 arm64 后端 |
| 未对齐访问 | 窄访存 + arm64 硬件容忍 | LLVM 默认按 ABI 对齐推断 → 可能合并成 `ldp`/向量访存 | 反推断：凡来自指针算术的 LOAD/STORE 一律发 `align 1` |
| bool 在内存 | 归一化为 0/1（`arm64_normalize`） | LLVM `i1` 假定内存里就是 0/1，其他值 UB | 内存里用 `i8`、用前 `trunc`，别让 `i1` 落地 |
| 未初始化局部 | 读栈垃圾（无静态检查） | `alloca` 未写即读 = `undef`，`-O2` 可变成任意值 | 写入设计：要么零初始化，要么声明为 UB |

### R4 `unreachable` 不能直接映射（中危）

IR 有 `IR_TERM_UNREACHABLE`，arm64 后端对它有 `brk #0` 分支
（`compiler/backend/arm64.yh:340-341`；但同文件 70-73 的预检目前不接受
UNREACHABLE，实际走不到那条分支）。
LLVM 的 `unreachable` 是"此路不通"的**优化假设**，会让 `-O2` 删代码/编造值。
应发 `call void @llvm.trap()` 再 `unreachable`（或直接调用 abort），并加用例。

### R5 符号与 linkage（中危，但有现成教训）

- 模块限定名、`__proj__mod` 后缀、寄存器同名符号 `__yhreg` 后缀
  （`docs/todo.md:56-61`）都要在 `.ll` 里合法化（必要时用引号标识符）。
- `pub` ↔ `.globl` 的既有约定（`Makefile` 注释与导出面收缩设计）要映射成
  `external`/`internal`/`private`；`pub const` 数据符号要 `constant`。

### R6 LLVM 版本与语法子集（中危）

- 最低版本必须钉住：LLVM ≥17 只支持 opaque pointer（`ptr`），
  `getelementptr` 必须显式给元素类型；`c"..."`、`switch`、`nuw/nsw` 等新语法
  一旦用了就抬高下限。
- 建议：只用保守子集（`ptr`、无 `nsw/nuw`、无 `poison` 依赖），
  门禁里加 `llvm-as -o /dev/null` 结构校验（等价于汇编器的 `llvm-mc` 差分位）。

### R7 确定性与缓存（中危）

- `.ll` 文本必须确定性（稳定遍历顺序，不能写地址/表 ID/时间），否则固定点与缓存全废。
- clang 会在 `.comment` 里写版本串，对象字节随工具链升级而变；
  今天的对象缓存键只含 `.s` 文本 + 工具名字符串，必须补上 LLVM 版本，否则热缓存会复用旧对象。
- 固定点门的口径要从 `.s` 改成 `.ll`（或两者都留）：否则 LLVM 路径根本没有固定点可谈。

### R8 自举与种子滚动（中危）

- 若 LLVM 成为唯一后端：`make`/`make seed` 从此**必须**有 clang/LLVM；
  Linux CI 与 Darwin CI 都要装；`docs/03-design/yh-自举后端架构.md` 里
  "构建失败时的种子链"叙事要重写。
- 编译器源码本身要能被**上一代种子**编译（滚动自举）：新发射器代码必须落在
  种子可编子集内，且默认关闭时完全惰性。
- 反向路线（用 LLVM 编译出的 yh 去滚种子）在 lowering 未完成前不可行。

### R9 自包含运行时与"无未定义符号"门（中危）

- LLVM 会为聚合拷贝/大块清零自动插入 `memcpy/memset`；`-ffreestanding -fno-builtin`
  只能减少、不能保证消除。
- 门禁语义冲突：`tests/selfhost/runtime-memory.py:114-118` 要求对象 `nm -u` 为空。
  选择只有两个：把运行时的 `memcpy/memset/...` 也在同模块里定义（推荐，保持自包含），
  或改动这条门（等于放宽既有产品性质，应走 ADR）。

### R10 链接与代码模型（中危）

- 既有终链是 `gcc -no-pie` + 自有汇编（绝对寻址 `adrp/add :lo12:`）；
  clang 默认产 PIE/PIC。LLVM 路径必须显式 `-fno-pic -fno-pie`（或统一改成 PIC 并同步改
  汇编路径），否则混链/自有 `yh_link` 静态 ELF 路径会对不上。
- `-lm`、`.eh_frame`、`.comment` 等节在自有链接器下的处理需复核
  （`link/src/elf/30_read.yh` 已有无装载语义节的剔除逻辑）。

### R11 与 NP 优化架构重复投入（策略级）

`docs/03-design/yh-Nanopass风格优化架构.md:74-103、219-236` 已经规划了
C/N/S/M/E/R 六阶段、机器 IR、线性扫描寄存器分配、SCCP/LVN。
LLVM 提供的正是这部分。**两者不能都做**：先选一个，另一个降级或取消，
否则同一收益做两遍、两套中间表示互相牵制。

### R12 工作量/收益比（策略级）

| 路线 | 增量工作 | 收益 | 风险 |
| --- | --- | --- | --- |
| A 只做 oracle | 小（SSA 子集发 `.ll` + 差分脚本 + 探针用例） | 立刻发现 SSA/后端/折叠器的错值；为将来铺路 | 无（不动默认路径） |
| B LLVM 作第二后端 | 中（L2+L3 + 混合受限） | arm64 上拿到 `-O2` 与寄存器分配，产物质量提升 | 混合 R1/R2 |
| C LLVM 作唯一后端 | 大（L1 全部 + L4 运行时/OS 层） | x86_64/Windows 有路可走 | 破坏自包含与既有门禁口径 |
| D 自写 x64 发射器（原 R6 计划） | 中（一个 `emit_x64.yh` + 数据模型 + 门禁） | 保持零外部依赖、与自举纯度一致 | 拿不到优化器；ABI/寄存器分配工作量大 |
| E 进程内 LLVM-C API | 大且脆 | 无外部进程 | 硬依赖 libLLVM、版本锁死、无 IRBuilder |

---

## 4. 建议路线（分期，每期可独立验收与回退）

### P0 —— LLVM 当 oracle（建议立即做，不动默认产物）

1. 新增 `backend/llvm*.yh`：只把**当前 SSA 子集**（整数/布尔 + 直接调用）发成 `.ll`。
2. 新增探针入口（例如 `yh --emit-llvm`，或测试脚本侧驱动），
   用 `clang -c` 编出的对象与 arm64 后端产物**同语料差分**：
   复用 `tests/yh-run/run/` 全量用例（比对退出码 + stdout）。
3. 补语义探针用例：除零、`INT_MIN/-1`、移位量 ≥ 位宽、未对齐指针访存、
   bool 内存表示、未初始化局部读（R3 表逐项）。
4. 门：`llvm-as` 结构校验通过；差分全绿；`make test`/`selfhost-native` 零变化。

**这一期就能把 R3 的语义分叉问题暴露出来**，无论最终是否接 LLVM 都值得做。

### P1 —— IR 模块化与 lowering 补齐（真正的工程主体）

按 L1 表推进，顺序建议：L1.1 模块级 IR → L1.2 聚合/布局 → L1.3 内存/取址 →
L1.6 控制流 → L1.4 浮点 → L1.5 间接/变参 → L1.7 C ABI → L1.8 语义锁定。
每切片照仓库规矩：`tests/yh-run` 或 `tests/modules` 加 `.yh` 用例，
Linux 上过 `make test` + `make selfhost-native`，滚种子另立。

### P2 —— LLVM 成为可选第二后端（arm64 Linux/Darwin 先行）

- `--backend llvm` 整模块编译，`.ll` 固定点门 + 全量语料差分 + 自包含运行时（R9）。
- 收敛判据：同一候选编译器、同一语料，两个后端退出码/stdout 全等；
  `.ll` 两代固定点一致；`runtime-memory` 等专项门有 LLVM 口径。
- 回退：默认仍 arm64，`YH_BACKEND` 切换。

### P3 —— x86_64 / Windows

必须先做 L4 的目标 OS 层与运行时；LLVM 只解决指令选择/ABI 那一半。
Windows 还额外需要 PE/COFF 链接链（走 clang/lld 则可绕过 `yh_asm`/`yh_link`）
与 Win32 API 的 FFI 层。

---

## 5. 待决策的问题（需要用户回答）

1. **接入 LLVM 的目标是哪一个**：a) 验证现有后端（oracle）；
   b) 提升 arm64 产物质量（优化器）；c) 打开 x86_64/Windows。
   a/b/c 三条路的工作量与前置条件完全不同。
2. **是否接受默认构建对 clang/LLVM 的硬依赖**（影响种子滚动、CI、发行物自包含叙事）。
3. **NP4/NP5（自家机器 IR + 线性扫描 + SCCP/LVN）保留还是取消**（避免重复投入）。
4. **是否允许"一个模块内两种代码生成器"**（若不允许，则 LLVM 只能整模块启用，
   实际等于要求 lowering 完成度足够高）。
5. **最低 LLVM 版本**（决定可用语法子集与目标平台的 clang 可得性）。

---

## 6. 附：核对坐标

| 主题 | 文件 |
| --- | --- |
| SSA 模型/verifier/简化 | `compiler/ir/ssa.yh:14-58、117-138、141-164、586-731` |
| SSA → arm64（含文本替换） | `compiler/backend/arm64.yh:10-77、369-445`、`compiler/backend/arm64_call.yh:54-115` |
| AST → SSA lowering 范围 | `compiler/ast/ast_ir.yh:24-39、267-307` |
| 数据模型与结构体布局 | `compiler/gen/target.yh:25-35、100-143` |
| 发射器输出组织 | `compiler/gen/emit_arm64.yh:1-26` |
| 自包含运行时 | `compiler/gen/emit_runtime_memory.yh:9、113、180、524-537`、`compiler/gen/model.yh:230-235` |
| prelude/外部符号 | `compiler/gen/symbols.yh:1109-1169` |
| 汇编/链接步与缓存键 | `compiler/cmd/link_cache.yh:155-201、241-329、541-621` |
| 构建/门禁 | `Makefile:82-179`、`tests/selfhost/native-selfhost.py:9`、`tests/selfhost/runtime-memory.py:114-137` |
| 语料驱动与期望注释 | `tests/yh-run/check.py:1-31、55-69` |
| oracle 发现顺序先例 | `asm/tests/check_corpus.py:30-77` |
| 待补 lowering 清单 | `docs/todo.md:206-217` |
| 换目标契约 / NP 阶段规划 | `docs/03-design/yh-自举后端架构.md:33-58`、`docs/03-design/yh-Nanopass风格优化架构.md:74-103、217-236` |
