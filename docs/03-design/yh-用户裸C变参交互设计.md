# yh 用户裸 C 变参交互设计

修改时间：2026-11-06

状态：分析/设计稿（2026-11-05，未实施；不改变仓库现状）
目标平台：Linux/x86_64、Linux/AArch64、macOS/ARM64、Windows/x86_64
相关：[extern 自动 C ABI](yh-extern自动C-ABI设计.md)、
[属性系统与 C 互操作](yh-属性系统与C互操作.md)、
[受检到 LLVM 能力矩阵](yh-受检到LLVM能力矩阵.md)

## 0. 结论摘要

1. **“裸 C 变参”应只作为一个 C ABI 边界能力存在，不与 yh 的类型化变参
   `name ... T` 合并。** yh 内部继续用切片变参（安全、可检查）；`...` 只允许
   出现在 `@[extern]` 的 C ABI 声明/定义上，作为调用/被调用 C 世界的窄口。
2. **建议分两期交付。**
   - **L1（调用侧）**：`@[extern] fn f(fixed, ...) T;`，让 yh 能调用
     `fcntl`/`ioctl`/`execl`/`snprintf` 等 C 变参函数。现有 `vararg==1`
     通道（prelude `printf`/`open` 专用）已经打通了调用、默认提升与四目标
     LLVM 发射的大部分路径，L1 主要是**放开语法闸门、补类型规则、去掉符号
     名白名单**，新增代码量小。
   - **L2（定义侧）**：内建 `va_list` 类型与 `va_start/va_arg/va_end/va_copy`，
     让 yh 能实现 C 变参函数（被 C 调用，或实现自己的日志/格式化封装）。
     这是本设计的主体：四目标 `va_list` 表示不同，`va_arg` 必须逐目标降低。
3. **关键实测结论（clang 21.1.8）**：LLVM 的 `va_arg` IR 指令在
   Linux/x86_64、Darwin/ARM64、Windows/x64 上降低正确；**在 Linux/AArch64
   上只按 `__stack` 游标取栈槽，不展开 `gr_offs/gr_top` 寄存器保存区，对
   AAPCS64 变参是错误降低**（与仓库 `llvm_runtime.yh` 中 printf 手写
   `yh_va_next` 的判断一致）。因此 `va_arg` 不能全目标统一交给 LLVM 指令，
   Linux/AArch64 必须由编译器按 AAPCS64 显式展开。
4. **不建议**在 v1 引入 Rust `VaList`/Swift `withVaList` 式的安全抽象，也不
   建议用 C 桥/生成 C 包装器来“绕过”变参：两者都无法在不具备变参语义的
   前提下转交任意实参序列（详见 §4）。
5. **需要一次显式决策**：`docs/todo.md` 目前把“用户裸 C 变参”列在
   “设计决定不做”。本文是评估与建议；若采纳，需按仓库流程补 ADR（建议
   `ADR-0020-yh用户裸C变参边界`）、todo 与实施计划，再动代码。

## 1. 问题与“优雅”的判据

### 1.1 用户需要它做什么

仓库已有真实缺口记录：

- `ioctl(TIOCGWINSZ)` 取终端宽度（Darwin/Linux）——`docs/todo.md` CLI-G；
- `fcntl(fd, F_SETFL, O_NONBLOCK)` 切非阻塞——`docs/todo.md` NET 条目；
- `execl/execv` 族、`curl_easy_setopt` 一类 C API（后者曾因“C 变参”被
  否决，见 `docs/01-finished/finish-历史归档`）；
- `snprintf`/`vsnprintf` 等格式化接口；
- 用户自己项目里的 C 代码暴露 `log(fmt, ...)`、`sum(int n, ...)`。

这些场景分两类：**yh 调用 C 变参函数**（绝大多数），**C 调用 yh 变参函数**
（实现回调式的可变参日志、或将来重写 libc 的 printf 族）。

### 1.2 这里的“优雅”指什么

对 yh 这种极简、静态、自举的编译器，“优雅”应满足：

1. **语言面最小**：一个语法点（`...`）、一个内建类型（`va_list`）、四个
   内建函数；不引入泛型、反射、装箱或生命周期系统。
2. **ABI 事实只在一处**：四目标 `va_list` 布局与 `va_arg` 展开集中在后端，
   前端/语义层不出现目标条件分支。
3. **能检查的尽量前移**：C 默认提升、`va_arg` 的允许类型、`va_list` 生命周期
   与逃逸，在编译期拒绝常见 UB；不能检查的（格式串与实参不匹配）明确文档化。
4. **不破坏现有语义**：类型化变参、prelude、runtime printf、自举固定点、
   `.s.i` 接口与缓存版本纪律保持不变（必要时升版本）。
5. **可增量交付**：L1 与 L2 各自有独立的门禁与回滚点；L1 不依赖 `va_list`。
6. **不做无法验证的承诺**：不承诺 C 侧格式串正确性，不承诺与未表达的 C 类型
   （binary128、向量、位域、聚合变参）互操作。

## 2. 现状盘点（代码地图）

### 2.1 语言面

- **类型化变参** `name ... T` 已实现：体内是 `[]T`，调用点打包为末尾切片
  （`docs/yh.g4:208-214`、`CONTEXT.md`“类型化变参”）。
- **裸 `...` 由语法接受、由编译模式拒绝**：`parse_decl.yh:797-810` 读到
  `TK_ELLIPSIS` 置 `vararg = 1`，编译模式下立即报
  “用户源码不允许裸变参（仅 prelude）”。
- **extern 函数拒绝变参**：`parse_decl.yh:889-893`，无论裸变参还是类型化
  变参都报 “C ABI v1 不支持 yh 变参”。
- prelude 用 `prelude_add(name, ret, np, vararg)` 直接登记 `printf`（变参
  仅 1 个固定参数，`builtin/prelude.yh:58`）与 `open`（2 个固定参数，
  `builtin/prelude.yh:96`），它们是**编译器运行时自己定义**的弱符号，
  不是 libc 导入。

因此现状是：**语法有位置，后端有通道，唯独“用户能否使用”被语义层按
prelude 白名单封死**。

### 2.2 语义与 lowering 的既有能力

- 调用检查：`gen/sem_call_literal.yh:95-101` 区分 `vararg==2`（类型化）、
  `vararg==1`（裸 C，仅 prelude）与 0；`:149-159` 对裸变参实参逐项检查，
  **浮点被拒绝**（“将在 B7 支持”），聚合/数组/切片被拒绝。
- 默认提升已在 lowering 实现：`lower/module_snapshot_lower_call.yh:21-44`
  把 `bool/i8/u8/i16/u16` 提升到 `i32`，把 `f32` 提升到 `f64`；提升后的
  类型写回 `IRCallArg`。这正对应 C 的默认实参提升。
- 快照/接口/缓存已携带 `sig_vararg`（0/1/2）：`ast/module_snapshot.yh:86`、
  `lower/module_snapshot_lower.yh:105-139` 等；`vararg==1` 目前要求函数带
  `F_EXTERN` 或 `F_INTRINSIC`（`:109-110`），用户 extern 恰好满足。
- 但 `lower/module_snapshot_lower.yh:231,311` 仍有“`vararg==1` 即拒绝”的
  分支（返回槽/函数视图），需要逐一放开并补测试。

### 2.3 后端（LLVM）

- 函数定义/声明类型：`backend/llvm_module.yh:400-403` 在 `variadic==1` 时
  在固定参数后输出 `...`；调用处 `backend/llvm_scalar.yh:437-447` 同样输出
  变参函数类型。说明**变参函数的 IR 形态已经存在**（runtime printf 就是
  `define i32 @printf(ptr, ...)`，见 `backend/llvm_runtime.yh:305-318`）。
- 但 `backend/llvm_call.yh:183-217` 用**符号名白名单**放行裸变参：
  SysV 的任意符号只放行 `printf`；Darwin/Linux-AArch64/Windows 只放行
  `printf`、`open`。`:234,253,256-258` 在 C ABI 分支又按目标拒绝
  `variadic != 0`。用户 extern 变参要在这些位置放开，并改为按目标能力
  （标量/指针可表达）而不是按名字判断。
- runtime `printf` 已经手写了 va_list 读取：`llvm_runtime.yh:282-310` 为
  Linux/AArch64 按 32 字节结构读 `+24` 的 `gr_offs` 与 `+8` 的 `gr_top`，
  其余目标用 `va_arg` 指令取 8 字节槽。这说明**定义侧 + va_list 读取在
  后端是可行的**，但只服务一个已知函数，尚未泛化。
- prelude `open` 在 Darwin 有专门的 3 实参形状检查
  （`llvm_scalar.yh:389-405`），说明变参调用点的目标差异已经出现在代码里。

### 2.4 接口、序列化、缓存

- 变参函数**一律不能导出**：`parse/iface.yh:277-283`“变参函数不能导出为
  pub”。这是 L2 定义侧“被 C 调用”必须动的地方。
- 版本号现状：IR 序列化 9（`ir/ssa_serialize.yh:4`）、模块序列化 3
  （`ir/ssa_module_30_serialize.yh:62`）、函数缓存格式版本
  （`ir/ssa_module_40_function_cache.yh:20` 附近）、接口版本 1–3
  （`parse/iface.yh:429-438`）。新增 `va_list` 类型/新 IR 操作/新接口字段
  都要按仓库纪律升版本，并让旧缓存失效。

### 2.5 测试与文档

- 拒绝用例：`tests/yh-run/fail/60-user-c-varargs.yh`；
  `tests/selfhost/llvm-abi.py` 断言该文件必须失败且包含
  “用户源码不允许裸变参”；`tests/selfhost/llvm-darwin-abi-reject-varargs.yh`。
- 文档：`docs/yh.g4:208-214` 明确“裸 `...` 仅 prelude”；
  `03-design/yh-属性系统与C互操作.md:34-35,91` 明确“本阶段不声明 libc
  printf 的裸 C 变参”“不开放用户 C 裸变参”；`docs/todo.md` 把该能力列在
  “设计决定不做”。
- 这些测试/文档在实施时必须一起改，否则门禁自相矛盾。

## 3. 为什么“只放开语法”不成立

### 3.1 C 默认实参提升

clang 21 对 `sink("%d...", b, c, sc, uc, s, us, f, e)` 的 IR（实测）：

| 源类型 | 传入 `...` 的实际类型 | 转换 |
| --- | --- | --- |
| `_Bool` | i32 | `zext i1` |
| `char` / `signed char` | i32 | `sext i8` |
| `unsigned char` | i32 | `zext i8` |
| `short` | i32 | `sext i16` |
| `unsigned short` | i32 | `zext i16` |
| `float` | double | `fpext` |
| 枚举（i32 表示） | i32 | 不变 |
| 指针 | 指针 | 不变 |
| 8 字节 struct | i64（coerce） | 目标相关 |

**结构体按值传入 `...` 的形态还随目标与类别变化**（clang 实测）：8 字节聚合
被 coerce 成 `i64`；16 字节 HFA 在 Linux/x64 变成两个 `double`，在
Linux/AArch64 与 Darwin 变成 `[2 x double]`，在 Windows/x64 变成 `ptr`；
24 字节聚合在 Linux/x64 用 `byval` 指针，其余目标用 `ptr`。`va_arg` 读取
聚合又受 LLVM 限制（LangRef 明确 `argty` 不能是聚合）。这是 v1 对 `...`
只支持标量/指针、聚合必须显式传指针的直接原因。

若把 yh 的 i8/f32 原样写进变参调用，C 被调方按 int/double 读，结果是未定义
的位型。yh lowering 已有提升逻辑，但 `sem_call_literal.yh` 目前先拒绝 float，
L1 需要把这两处打通并补“提升后类型”的 IR 断言。

### 3.2 调用约定四目标不同

实测 `printf("%d %f %s", 42, 3.5, "hi")` 的汇编：

| 目标 | 固定参数 | 变参 | 特殊点 |
| --- | --- | --- | --- |
| Linux/x86_64 (SysV) | `%rdi` = fmt | `%esi`=42, `%xmm0`=3.5, `%rdx`="hi" | `%al` = 使用的 SSE 寄存器数（示例 `movb $1,%al`） |
| Linux/AArch64 (AAPCS64) | `x0` = fmt | `w1`=42, `d0`=3.5, `x2`="hi" | 变参与固定参数一样走寄存器，溢出才入栈 |
| macOS/ARM64 (Apple) | `x0` = fmt | **全部变参在栈上**：`[sp]`=42、`[sp+8]`=3.5、`[sp+16]`=ptr | 每槽 8 字节；固定参数仍走寄存器 |
| Windows/x64 | `rcx` = fmt | `edx`=42、`xmm0`=3.5 **且** `r8`=3.5 的位型、"hi" 在 `r9`/栈 | 32 字节 shadow store；浮点在 GPR/XMM 各一份 |

LLVM 只要看到“函数类型带 `...` 且实参已是提升后类型”，后端会自动完成上述
差异（runtime printf 的四平台调用就是证据）。所以调用侧的 ABI 风险主要在
**默认提升**与**目标能力闸门**，而不是手写寄存器分类。

### 3.3 `va_list` 四种表示

| 目标 | 大小/对齐 | 实际形态 | `va_start` 后语义 |
| --- | --- | --- | --- |
| Linux/x86_64 | 24 / 8 | `__va_list_tag[1]`：`gp_offset u32`、`fp_offset u32`、`overflow_arg_area ptr`、`reg_save_area ptr` | 两个 offset 指向寄存器保存区，溢出走 `overflow_arg_area` |
| Linux/AArch64 | 32 / 8 | `{ stack ptr, gr_top ptr, vr_top ptr, gr_offs i32, vr_offs i32 }` | `gr_offs/vr_offs` 为负表示还有寄存器槽，否则走 `stack` |
| macOS/ARM64 | 8 / 8 | `char *` | 指向栈上第一个变参槽（8 字节槽） |
| Windows/x64 | 8 / 8 | `char *` | 指向 shadow space 之后第一个 8 字节栈槽 |

同一个 `va_arg(ap, double)` 在四个目标上对应的机器动作完全不同，不能只加
一个类型就交给 LLVM 指令。

### 3.4 `va_arg` 不是一条可移植指令

LLVM IR 仍有 `va_arg` 指令（`%v = va_arg ptr %ap, i64`），clang 21 的
实测结果是：

- **Linux/x86_64**：clang 前端手写 `gp_offset/fp_offset/overflow_arg_area`
  序列；`va_arg` 指令本身降低正确（有 `cmp $48`、`fp_offset` 分支）。
- **Linux/AArch64**：clang 前端手写 `gr_offs/gr_top` 序列；**`va_arg`
  指令降低只读 `[ap]` 的栈指针**（实测汇编：`ldr x8,[x0]; ldr x0,[x8];
  add x8,x8,#8`），完全忽略 `gr_offs` 与寄存器保存区，对寄存器传入的变参
  会读错。
- **macOS/ARM64**：clang 前端直接用 `va_arg` 指令；指令降低为“读指针、
  按 8 字节对齐推进”，与该 ABI 一致。
- **Windows/x64**：clang 前端也用 `va_arg` 指令；指令降低为 8 字节对齐推进，
  与该 ABI 一致（浮点由调用方在栈槽里备好）。

这与仓库 `llvm_runtime.yh:282-285` 的既有判断一致：AArch64 必须显式读取
寄存器保存区。LLVM LangRef 也把 `va_arg` 标为 target-specific，并明说代码
生成在不少目标上并不完整、`argty` 不能是聚合
（<https://llvm.org/docs/LangRef.html#vaarg-instruction>），与实测一致。
L2 的降低策略必须据此分目标，而不能“统一发 `va_arg`”。

### 3.5 其余必须一起改的面

- 函数是否可变参要进入 `.s.i` 接口、IR 序列化、函数缓存键（否则跨模块
  调用方会按定参签名生成调用）；
- `vararg==1` 目前只在 prelude 生命周期里出现，一旦用户可用，所有
  “仅 prelude”隐含假设（白名单、导出限制、错误信息）都要重新审视；
- 测试门禁与文档口径（见 §2.5）。

### 3.6 名字冲突

prelude `printf`/`open` 是编译器运行时自己发射的弱定义（`llvm_runtime.yh`
等）。若用户写 `@[extern] fn printf(...)` 期望链接 libc，实际会绑定到编译器
运行时，行为与 libc 不一致。v1 的处理：**保留名**——用户 extern 声明与
prelude 同名时报错；需要 libc printf 的用户可用 `snprintf`/`vsnprintf`
（P3）或独立方案（重命名 runtime 入口，另立设计）。

## 4. 设计空间与取舍

| 方案 | 表达力 | 实现成本 | 风险 | 结论 |
| --- | --- | --- | --- | --- |
| A. 维持拒绝，用户写 C 包装器 | 任意 C 变参都可经固定签名包装 | 0（现状） | 用户被迫写 C；`ioctl/fcntl` 这类无法包装成定参语义的接口仍不可用 | 仅作兜底 |
| B. 只做调用侧 `...` | 覆盖 95% 的 C 变参 API | 小（复用 `vararg==1` 通道） | 默认提升/四目标调用约定 | **建议第一期** |
| C. 调用侧 + 定义侧 `va_list` | 覆盖 C↔yh 双向 | 中（四目标 va_arg 展开） | ABI 细节多 | **建议目标形态** |
| D. Rust/Swift 式安全抽象（`VaList` 值、`withVaList` 闭包、泛型参数打包） | 类型更安全 | 大（需要泛型/生命周期/闭包） | 与 yh 极简原则冲突 | v1 不做 |
| E. C 桥/固定桥转发 | 看似省事 | 中 | **无法通用**：固定签名转交不了任意实参序列；变参 helper 本身又需要变参调用，循环依赖；只能为每个已知函数写 thunk | 不用 |
| F. 每次调用生成 C 包装源码 | 可工作 | 大（引入 C 编译器/目标 sysroot） | 破坏自举与闭包边界 | 不做 |

先例的关键结论：Rust 定义侧到 1.99.0 才稳定，且必须 `unsafe` + `VaList<'a>`
生命周期；Zig 用 `callconv(.c)` 限定，并在 aarch64 非 Darwin 等目标上直接
Skip；Swift 只消费 `va_list` 形态、不生产 `...`；Go 直接拒绝、靠 C wrapper。
四家都把“调用/定义”拆开，并承认目标 ABI 差异无法用一套表示抹平——yh 的
两期拆分与按目标开关正是这个共识的体现。

说明 E：仓库的“固定桥”是构建期宿主 C 代码（`compiler/llvm/*.shim` 等），
用于编译器自身的宿主调用；目标程序的 ABI 由 LLVM 发射直接决定，不能拿宿主
桥代替。理论上可以写 `long yh_va_arg_i64(va_list *ap)` 这种 C helper 供
目标程序链接，但需要为四个目标预置目标对象、并解决 va_list 表示差异，
收益不如直接在 IR 模板里展开；若只做“格式化”一类固定用途（把 va_list
交给 libc `vsnprintf`），则 L2 的 `va_list` 参数能力更直接。

## 5. 目标设计

### 5.1 总原则

- 裸 `...` 与类型化 `name ... T` **语法不同、ABI 不同、可见性不同**，不允许
  互相替代或混用。
- 只允许 `@[extern]`（含带体定义）使用裸 `...`；普通 yh 函数写 `...` 报错，
  并提示改用 `name ... T`。
- 裸变参只出现在**声明/定义**的末尾；类型位置（函数指针类型）v1 不开放
  `...`（C 变参函数指针极少数场景，后续按需）。
- 所有 ABI 知识集中在 `compiler/backend`；前端只认“C ABI 变参”这个事实。

### 5.2 语法

```yh
// 调用侧：声明 C 变参函数
@[extern]
fn fcntl(fd int, cmd int, ...) int

@[extern]
fn snprintf(buf *char, size u64, fmt *char, ...) int

// 定义侧：实现一个 C 可见的变参函数（P2 起）
@[extern]
pub fn yh_log(fmt *char, ...) void {
    let ap va_list = va_start()
    let code int = va_arg(ap, i32)
    let msg *char = va_arg(ap, *char)
    // ... 使用 code/msg ...
    va_end(ap)
}
```

规则：

1. `...` 至多一个，且必须是参数表最后一项；
2. v1 要求至少一个固定参数（与 C17 一致；C23 的 `fn(...)` 后续再议）；
3. 裸 `...` 与 `name ... T` 互斥；后者仍只允许出现在 yh ABI 函数，且仍在
   模块私有面内；
4. `@[extern]` 无体声明仍须以 `;` 结束；带体定义产生 C 可见裸符号；
5. `va_list` 是内建类型名，`va_start/va_arg/va_end/va_copy` 是内建调用，
   都不是普通标识符，不能被用户声明遮蔽。

### 5.3 类型与语义规则

#### 5.3.1 调用侧实参

允许（按 C 默认提升后传入）：

- 整数：`i8/u8/i16/u16/i32/u32/i64/u64`、`bool`、`char`（`char` 即 u8）；
- 浮点：`f32`（提升为 `f64`）、`f64`；
- 指针：`*T`（`T` 任意，含 `void`）、数组/字符串字面量退化为指针；
- `@[extern] fn(...)` 函数指针。

拒绝并给出明确诊断：

- 聚合（`struct/union`）按值：v1 不做（C 允许，但 ABI 形态在四目标差异大，
  且与 yh 聚合“体内地址表示”相互纠缠）；
- 切片、数组按值、`va_list`、`void`、不透明值。

#### 5.3.2 `va_list` 与四个内建

| 内建 | 签名（语义） | 约束 |
| --- | --- | --- |
| `va_start` | `va_start() va_list` | 只能出现在 C ABI 变参函数体内；为调用帧分配并初始化 |
| `va_arg` | `va_arg(ap, T) T` | `ap` 必须是本函数内的 `va_list` 局部变量（可被改写）；`T` 见下表 |
| `va_end` | `va_end(ap) void` | 同一函数；四目标上为 no-op，v1 允许省略但推荐显式 |
| `va_copy` | `va_copy(ap) va_list` | 返回独立副本；`let b va_list = va_copy(a)` |

`va_arg` 允许的 `T`（**关键安全规则**）：`i32/u32/i64/u64/f64`、指针类型、
C 函数指针；`extern enum` 可按 `i32` 读取（或后续显式允许）。**拒绝**
`i8/u8/i16/u16/bool/f32`，诊断提示“C 默认提升后为 `i32`/`f64`，请按提升后
类型读取”。这一条把 C 里最常见的 `va_arg` 类型不匹配 UB 变成编译错误，
是 yh 相对 C 的实质改进。

`va_list` 的禁止项（v1）：

- 不能赋值给另一个 `va_list`（必须用 `va_copy`）；
- 不能作为返回值、结构体字段、全局变量、数组/切片元素；
- 不能取地址、比较、作为 yh 函数的参数（只能传给内建与 P3 的 extern 参数）；
- 不能离开声明它的函数（逃逸分析只需在检查期做局部规则）。

### 5.4 四目标 ABI 矩阵（实测）

| 目标 | `va_list` | 调用侧 | `va_arg` 读取 |
| --- | --- | --- | --- |
| linux-x64 | 24B，align 8 | 变参走 GP/SSE 寄存器，`%al`=SSE 数，溢出栈 8B 槽 | GP：`gp_offset < 48` 取 `reg_save_area+gp_offset`，否则 `overflow_arg_area`；FP：`fp_offset < 176`，每槽 16B |
| linux-arm64 | 32B，align 8 | 变参走 `x1..x7`/`v0..v7`，溢出 8B 栈槽 | GP：`gr_offs<0` 取 `gr_top+gr_offs`，否则 `stack`；FP：`vr_offs<0` 取 `vr_top+vr_offs`（每槽 16B），否则 `stack` |
| darwin-arm64 | 8B，align 8 | 变参全部在栈，8B 槽；固定参数仍走寄存器 | `char*` 指针按 8B 对齐推进 |
| windows-x64 | 8B，align 8 | shadow store；浮点在 GPR/XMM 各一份；变参槽 8B | `char*` 指针按 8B 对齐推进 |

`va_list` 作为 extern 函数参数（P3，如 `vprintf(const char*, va_list)`）的
传递形态同样分目标（clang 实测四个目标的 IR 参数都是 `ptr`，但含义不同）：

| 目标 | C 原型中的参数实际类型 | yh 传参动作 |
| --- | --- | --- |
| linux-x64 | `__va_list_tag *`（数组退化） | 传 `ap` 存储地址 |
| linux-arm64 | `__va_list *`（数组退化） | 传 `ap` 存储地址 |
| darwin-arm64 | `char *` | 传 `ap` 中保存的指针值 |
| windows-x64 | `char *` | 传 `ap` 中保存的指针值 |

这就是为什么 `va_list` 不能简单建模成普通 extern struct：它需要目标相关的
“参数传递形态”。

### 5.5 Lowering 设计

#### 5.5.1 调用侧

1. 语义层记录 `vararg==1` 与提升后的实参类型（现有结构可复用）；
2. lowering 生成带 `...` 的函数类型调用，实参一律为提升后类型
   （`module_snapshot_lower_call.yh:21-44` 已有，需把“浮点拒绝”移到语义层
   允许之后）；
3. LLVM 后端按 `llvm_scalar.yh:437-447` 的既有形态发射即可；
4. 删除 `llvm_call.yh` 的符号名白名单，改为：
   - prelude 运行时符号（`IR_ABI_YH_LLVM_V1`）保持现状；
   - 用户 C ABI 符号：`variadic==1` 且固定参数/返回值均为 C 标量/指针时放行，
     按目标不再额外拒绝；聚合实参在语义层已拒绝。

#### 5.5.2 定义侧

1. IR 层新增 `va_list` 类型（目标大小/对齐由后端给出）与四个操作的 IR 节点
   （或等价的内部 intrinsic 调用）：`VA_START`、`VA_ARG`（带类型参数）、
   `VA_END`、`VA_COPY`；
2. `va_start` → `call void @llvm.va_start.p0(ptr %ap)`；
   `va_end` → `call void @llvm.va_end.p0(ptr %ap)`；
   `va_copy` → `call void @llvm.va_copy.p0(ptr %dst, ptr %src)`；
3. `va_arg` 分目标：
   - Linux/AArch64：**必须**按 AAPCS64 显式展开（GP 用 `+24` 的 `gr_offs`
     与 `+8` 的 `gr_top`，FP 用 `+28` 的 `vr_offs` 与 `+16` 的 `vr_top`，
     栈用 `+0` 的 `stack` 指针；与 `<...>/sum-aarch64-linux-gnu.ll` 的
     clang IR 等价）；
   - 其余三目标：直接发 `va_arg` IR 指令（实测正确），由 LLVM 降低；
   - 两种路径都以 clang 21 的 IR/汇编为 oracle 做门禁。
4. 函数定义：`define ... (fixed..., ...)`（`llvm_module.yh:400-403` 已有），
   入口把固定参数按既有 C ABI 分类器处理，变参部分由 LLVM 保存区处理。

#### 5.5.3 导出与接口（P2/P3）

- `@[extern] pub fn f(..., ...)` 需要 `.s.i` 能表达“C 变参”；
- 接口版本升到 4，新增“变参”标记的序列化；类型化变参仍保持“不可 pub”；
- 函数缓存键包含变参标记与 `va_list` 相关类型，避免跨模块调用按定参签名
  生成。

#### 5.5.4 版本与缓存

预计要动的版本（以实施时实际代码为准）：

- `ir/ssa_serialize.yh`：`IR_SERIAL_VERSION` 9 → 10（新类型/新操作）；
- `ir/ssa_module_30_serialize.yh`：模块序列化 3 → 4（符号变参/类型表）；
- `ir/ssa_module_40_function_cache.yh`：函数缓存格式版本递增；
- `parse/iface.yh`：接口 3 → 4；
- 前端/受检快照缓存键版本（`module_snapshot_check_key` 等）随类型/签名变化递增。

### 5.6 诊断清单（实施时按此写 fail 用例）

| 场景 | 期望诊断 |
| --- | --- |
| 非 extern 函数写裸 `...` | 裸变参只允许用于 `@[extern]` C ABI 函数；yh 内部请用 `name ... T` |
| `...` 不在末尾/重复 | 裸变参只能出现一次且必须是最后一个参数 |
| `...` 与 `name ... T` 混用 | 同一参数表不能同时使用类型化变参与 C 裸变参 |
| extern 定义参数/返回类型不满足 C ABI | 复用现有 “C ABI 不支持该类型” 诊断 |
| 传聚合/切片/数组给 `...` | C 裸变参暂不支持按值聚合；请改为指针传递 |
| `va_start` 出现在非变参函数 | `va_start` 只能在 C ABI 变参函数体内使用 |
| `va_arg` 类型为窄整数/bool/f32 | C 默认提升后为 i32/f64；请按提升后类型读取 |
| `va_arg` 第一实参不是局部 `va_list` | `va_arg` 需要一个可改写的 `va_list` 局部变量 |
| `va_list` 赋值/返回/存字段/取址 | `va_list` 只能通过 `va_copy` 复制，且不能离开当前函数 |
| 用户 extern 与 prelude 同名 | `printf`/`open` 由编译器运行时提供，用户不能以同名 extern 覆盖 |

### 5.7 安全性

- **能静态保证的**：默认提升、`va_arg` 类型集、`va_list` 生命周期与逃逸、
  调用点固定参数类型。
- **不能保证的**：C 侧格式串与实参是否匹配（`printf("%d", 3.5)`），以及
  C 调用方传给 yh 变参函数的实参类型是否与 yh 读取类型一致。这部分与 C
  的边界等价，文档明确；后续可选做“字面量格式串检查”或 `@[format]` 注解，
  但不属于 L1/L2 门槛。
- 与类型化变参的分工：库内部（`libs/io` 的 `[]Value`、fmt 等）继续用可检查
  的类型化/数组接口；只在 FFI 最外层用裸变参。

## 6. 实施计划

| 阶段 | 目标 | 主要改动 | 验收 |
| --- | --- | --- | --- |
| **P0 调用侧（语法+检查+发射）** | `@[extern] fn f(fixed, ...)` 可调用整数/指针/函数指针；四目标 | `parse_decl`（允许 extern `...`）、`sem_call_literal`（类型规则）、`llvm_call`（去白名单、按目标放行）、prelude 同名保护、诊断与 fail 用例 | 新 C 桥项目：`ioctl/fcntl/execl` 等价用例四端运行；clang IR oracle 对比提升后实参 |
| **P1 调用侧浮点** | `f32→f64`，`snprintf`/`printf` 风格调用 | 去掉 `sem_call_literal` 浮点拒绝；确认 lowering 提升；Windows/AArch64/Darwin 浮点变参门禁 | 四端 C 桥：`snprintf("%d %f %s")`；Apple 栈槽/Win64 双份/X64 `%al` 断言 |
| **P2 定义侧 va_list** | `va_list` + 四内建；C 可调用 yh 变参函数 | 新类型/新 IR 操作/检查规则/后端 `llvm_va.yh`/序列化版本/iface v4 初版（模块内） | C 桥：C 调 yh `sum(int n, ...)`（int/double/ptr）；clang oracle 对比 `va_arg` IR；O0/O2 |
| **P3 va_list 跨边界与导出** | `vprintf/vsnprintf` 形态；`pub` 变参定义跨模块 | extern 参数 `va_list` 的四目标传参；接口 v4 正式；头文件交付约定 | 四端 C↔yh 双向：yh `log(fmt, ...)` 被 C 调用并经 `vsnprintf` 格式化；模块项目验收 |
| **P4 可选增强** | 字面量格式串检查、`@[format]`、C23 零固定参数、变参函数指针类型 | 按需 | 独立设计 |

每阶段的硬要求（仓库规则）：

1. 先改 `docs/yh.g4` 保证无歧义，再改计划与实现；
2. `tests/` 增加 `.yh` 正/反用例；
3. `just` 构建 + `just test` + `just selfhost-native` 全绿（Linux 本地），
   四端由 CI 验收；
4. 更新 `docs/` 所有受影响文档（README、CONTEXT、属性/ABI 设计、能力矩阵、
   todo、finish）；
5. 滚动种子前确认固定点。

## 7. 验收与门禁

### 7.1 新增测试

- `tests/yh-run/`：调用侧正例（需要 C 桥的放 `tests/modules/projects/`）、
  反例（§5.6 每条一个 fail 用例）；
- `tests/modules/projects/cvarargs/`：`project.toml` 带 `[c]` 源与头文件；
  C 侧提供 `sum_i(int n, ...)`、`sum_d(int n, ...)`、`sink(const char*, ...)`
  以及 C 调用 yh 变参函数的入口；
- `tests/selfhost/llvm-cvarargs.py`：clang 21 oracle：
  - 对比 yh 生成的变参调用 IR 与 clang 的默认提升/函数类型；
  - 对比 Linux/AArch64 的 `va_arg` IR 与 clang 的 `gr_offs` 序列；
  - O0/O2、四端交叉（能跑的目标实际运行，不能跑的做 IR/汇编断言）；
- 更新 `tests/selfhost/llvm-abi.py` 的“必须拒绝”断言与
  `llvm-darwin-abi-reject-varargs.yh`（改为“非 extern 裸变参拒绝”）。

### 7.2 门禁命令

```sh
just                     # 构建
just test                # 语法 + 编译器语法 + 运行语义
just selfhost-native     # 两代固定点 + 自解析 + 全量语料 + 项目验收
just test-llvm-linux-arm64   # Linux/AArch64 ABI 专项（容器）
```

P0/P1 的 C 桥用例应可在四端 CI 直接跑；P2 的 `va_arg` 在 Linux/AArch64 上
的展开必须由 `test-llvm-linux-arm64` 覆盖，不能只靠 Linux/x64 本地门。

## 8. 未决问题

1. **聚合按值传 `...`**：C 允许，但四目标 ABI 复杂（coerce/byval/内存类），
   且与 yh 聚合的内部地址表示冲突；建议长期保持“指针传递”约定，若将来
   需要再单独立项。
2. **`va_list` 参数模型**：P3 需要在 ABI 分类器里增加“目标相关参数形态”，
   是放在 `llvm_abi_model` 还是新增 `llvm_va.yh`，实施时定。
3. **预置名与 libc `printf`**：保留名方案可用，但 libc 重写路线最终需要
   区分“编译器 runtime printf”与“C 库 printf”；可能需要 `@[extern "name"]`
   链接名属性或重命名运行时入口，另立设计。
4. **格式串检查**：可选的 `@[format]`/字面量检查是否值得，取决于 libs/fmt
   的演进方向。
5. **C23 零固定参数 `fn(...)`**：ABI 上可行（va_start 无需 last named），
   但 v1 保守要求至少一个固定参数。
6. **类型化变参与 C 变参的关系**：保持两套；是否允许在 `@[extern]` 上用
   `name ... T` 表达“C 变参 + 固定元素类型”暂不考虑（会诱导错误 ABI）。

## 9. 风险与反对意见

- **“破坏极简”**：新增 1 个语法点、1 个类型、4 个内建，且只在 extern 边界
  可见；相比不支持导致的 C 包装器/无法实现 ioctl/fcntl，收益明确。
- **ABI 错误风险**：四目标调用约定与 va_list 差异大；缓解：clang oracle、
  C 桥四端运行、AArch64 专项门、O0/O2。
- **自举影响**：编译器源码本身不使用用户变参（runtime printf 维持现状），
  P2 只新增后端模板；固定点风险主要在序列化/接口版本，按纪律升版本。
- **与既有决策冲突**：`docs/todo.md` 明确“设计决定不做”。本文建议在用户
  确认后更新该条目并补 ADR，否则不应实施。
- **不解决 C 侧 UB**：格式串/类型不匹配仍可能崩溃；这是 C ABI 的固有属性，
  文档与示例需明确。

## 附录 A：实测证据与命令

环境：Windows 宿主，clang 21.1.8（LLVM 21.1.8），`clang -target <triple>
-O0 -S -emit-llvm -ffreestanding -fno-builtin`。

1. `va_list` 布局：`clang -S -emit-llvm` 后读取
   `%struct.__va_list` 定义与 `sizeof(va_list)` 探针：
   Linux/x64 24B、Linux/AArch64 32B、Darwin/ARM64 8B、Win64 8B。
2. `va_arg` 降低：clang 在 Linux/x64 与 Linux/AArch64 手写字段读取；
   Darwin/ARM64 与 Win64 使用 `va_arg` 指令。
3. `va_arg` 指令跨目标验证：手写
   `%v = va_arg ptr %ap, i64` 的 IR，用
   `clang -target <triple> -x ir -S`：
   - Linux/AArch64 汇编只有 `ldr [ap]; ldr [ptr]; add 8`（无 `gr_offs` 分支）；
   - Linux/x64 有 `cmp $48` 与 `fp_offset` 分支；
   - Darwin/ARM64 与 Win64 为 8 字节对齐指针推进。
4. 调用点汇编：`printf("%d %f %s", 42, 3.5, "hi")` 四目标，结论见 §3.2。
5. 默认提升 IR：`_Bool→i32 zext`、`char→i32 sext`、`unsigned char→i32
   zext`、`short→i32 sext`、`unsigned short→i32 zext`、`float→double fpext`。
6. `va_list` 作参数：clang 四目标的 IR 参数均为 `ptr`；Linux/x64 与
   Linux/AArch64 传 `ap` 存储地址，Darwin/ARM64 与 Win64 传 `ap` 中保存的
   指针值。

上述探针属于一次性验证，产物在 `tmp/vararg-analysis/`（gitignore），不入库；
完整矩阵见该目录的 `abi-matrix.md`，语言先例见 `prior-art.md`。
`va_arg` 指令的验证命令示例：
`clang -target aarch64-unknown-linux-gnu -x ir -S vaarg.ll`（IR 里写
`%v = va_arg ptr %ap, i64`），比较四目标汇编即可复现 §3.4 的结论。

## 附录 B：语言先例（摘要）

- **Rust**：调用侧 `extern "C" { fn printf(fmt: *const c_char, ...); }` 长期稳定；
  定义侧 `unsafe extern "C" fn f(mut ap: ...)` 自 1.99.0 起稳定，参数类型是
  `VaList<'_>`（不透明、ABI 与 C `va_list` 一致，`next_arg::<T>()` 读取，
  `Clone`=va_copy、`Drop`=va_end，隐式生命周期禁止逃逸；仅 `"C"`/`"C-unwind"`
  可定义）。调用侧不做隐式提升，读取侧按 C 规则读；格式串不检查。
  <https://doc.rust-lang.org/std/ffi/struct.VaList.html>、
  <https://github.com/rust-lang/rfcs/blob/master/text/2137-variadic.md>
- **Zig**：`extern "c" fn printf(format: [*:0]const u8, ...) c_int;`；
  定义侧 `fn f(count: c_int, ...) callconv(.c)` + `@cVaStart/@cVaArg/@cVaEnd/
  @cVaCopy`，`@cVaArg(&ap, T)` 带编译期类型。行为测试在 aarch64 非 Darwin、
  Windows x64 等目标上直接 Skip（#14096/#16961），说明各目标 ABI 仍需逐个
  兜底。<https://ziglang.org/documentation/master/#C-Variadic-Functions>
- **Swift**：只导入“用 `va_list` 取参”的 C 变参函数，用 `...` 声明的 C 函数
  不被导入；调用侧用 `withVaList` 得到 `CVaListPointer`，不得存储/返回；
  Swift 不能定义 C 变参函数。
  <https://github.com/swiftlang/swift/blob/main/stdlib/public/core/VarArgs.swift>
- **Go/cgo**：明确不支持直接调用 C 变参函数，只能写固定签名 C wrapper；
  每个调用形态一份胶水。<https://pkg.go.dev/cmd/cgo>
- **LLVM/Clang**：`va_arg` 是 target-specific 指令，`argty` 不能是聚合，
  代码生成在不少目标上不完整；`llvm.va_start/va_end/va_copy` 把 `va_list`
  当作目标相关的不透明值，且 `va_list` 不得活过创建它的函数。
  <https://llvm.org/docs/LangRef.html#variable-argument-handling-intrinsics>
- **共同点与 yh 取向**：四家都把“调用”和“定义/读取”拆开，并承认目标 ABI
  无法用一套表示抹平。yh 与 Zig 最接近（显式 `...` + 显式 `va_*` 内建，
  不引入 `callconv` 概念，由 `@[extern]` 决定 C ABI），但比 Zig 更严格地限制
  `va_arg` 的允许类型（禁止未提升的窄型/`f32`），并用局部作用域规则代替
  Rust 的 `unsafe` 与生命周期标注。

## 附录 C：相关代码位置

| 主题 | 位置 |
| --- | --- |
| 参数表语法 | `docs/yh.g4:208-214` |
| 裸变参解析闸门 | `compiler/parse/parse_decl.yh:797-810` |
| extern 变参拒绝 | `compiler/parse/parse_decl.yh:889-893` |
| 调用检查/裸变参实参 | `compiler/gen/sem_call_literal.yh:95-101,149-159` |
| 默认提升 | `compiler/lower/module_snapshot_lower_call.yh:21-44` |
| 快照 vararg 事实 | `compiler/ast/module_snapshot.yh:86`；`compiler/lower/module_snapshot_lower.yh:105-139,231,311` |
| 后端变参类型发射 | `compiler/backend/llvm_module.yh:400-403`；`compiler/backend/llvm_scalar.yh:437-447` |
| 后端变参白名单 | `compiler/backend/llvm_call.yh:183-217,234,253,256-258` |
| runtime printf 的 va_list | `compiler/backend/llvm_runtime.yh:282-310,305-318` |
| prelude 登记 | `compiler/gen/symbols.yh:1063-1072`；`compiler/builtin/prelude.yh:58,96` |
| 变参不可导出 | `compiler/parse/iface.yh:277-283,429-438` |
| 版本号 | `compiler/ir/ssa_serialize.yh:4`；`compiler/ir/ssa_module_30_serialize.yh:62`；`compiler/ir/ssa_module_40_function_cache.yh:20` 附近 |
| 拒绝用例 | `tests/yh-run/fail/60-user-c-varargs.yh`；`tests/selfhost/llvm-abi.py`；`tests/selfhost/llvm-darwin-abi-reject-varargs.yh` |
| 决策现状 | `docs/todo.md`“设计决定不做 · 用户裸 C 变参”；`docs/03-design/yh-属性系统与C互操作.md:34-35,91` |
