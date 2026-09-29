# yh 自举编译器后端架构（多平台接入缝）

> 2026-09-28 按 B5 落地实现记录。本文说明 `compiler/` 下 yh 新编译器的
> 分层、换目标平台需要提供什么，以及当前 AArch64 Linux 目标的实现现状。
> 阶段任务与验证门见 `docs/02-plan/yh-自举实施方案-v2.md`。

## 1. 三层结构

后端拆成三层，边界即多平台接入缝：

```
  前端语义（平台无关）
    symbols.yh   名字池、类型表、符号/作用域、类型兼容、常量折叠
    sem.yh       表达式/语句/声明语义钩子、两遍编译驱动、调用约定检查
    parse_*.yh   递归下降解析，边解析边调 sem_* 钩子（无 AST）
        │   只引用 target.yh 的数据模型常量 + emit 层的 em_* 抽象机原语
        ▼
  目标数据模型
    target.yh    字长、对齐、类型布局规则（换目标第一步）
        ▼
  目标指令发射（每目标一个文件）
    emit_arm64.yh  AArch64 GNU 汇编：寄存器、栈帧、ABI、段与符号发射
```

- **前端**：`symbols.yh` 到 `parse_decl.yh`，不出现任何 ISA/汇编字样；
  类型大小、对齐、参数寄存器个数等全部经 `tg_*` 常量与 `tg_layout_struct`
  获得。
- **数据模型**：`target.yh` 定义 `TG_PTR_SIZE`/`TG_INT_SIZE`/`TG_ARG_REGS`/
  `TG_STACK_ALIGN` 等常量与 `tg_align_scalar`/`tg_layout_struct`。
- **指令发射**：`emit_arm64.yh` 实现全部 `em_*` 原语；前端只调用原语，
  不感知寄存器名与汇编方言。

## 2. 换目标平台需要提供什么（契约）

1. **数据模型**：新建 `target_<isa>.yh`，给出标量大小/对齐、栈对齐、
   参数寄存器个数、结构体布局规则。
2. **指令发射**：新建 `emit_<isa>.yh`，实现下表全部 `em_*` 原语。
3. **构建脚本**：目标汇编/链接命令（当前为 `gcc -no-pie`，经
   `tests/yh/container-yh-cc.sh` 包装）。

### em_* 抽象机原语清单（当前唯一实现：AArch64）

| 类别 | 原语 | 语义约定 |
| --- | --- | --- |
| 值 | （约定） | 所有产生值的结果留在 `x0`（AArch64 目标） |
| 值栈 | `em_push` / `em_pop` | 16 字节槽，保持 sp 16 对齐 |
| 二元 | `em_binop` / `em_compare` | x9 = 左，x0 = 右，结果回 x0 |
| 一元 | `em_unary` | 操作数在 x0 |
| 地址 | `em_lea_local` / `em_lea_global` / `em_load_data_label` | 地址入 x0；局部偏移可为负（调用方栈区参数） |
| 访存 | `em_load_sized` / `em_store_sized` / `em_load_local` / `em_store_local` / `em_load_global` / `em_store_global` | 按类型窄宽度加载并符号/零扩展 |
| 控制流 | `em_new_label` / `em_label` / `em_jmp` / `em_jz` / `em_jnz` / `em_beq` | 局部标签 `.L<n>` |
| 过程 | `em_prologue` / `em_alloc_local` / `em_epilogue` | 静态帧：体先发射到缓冲，帧大小确定后一次减栈 |
| 调用 | `em_call_direct` / `em_call_indirect` / `em_call_arg_to_reg` / `em_call_stack_area` / `em_call_stack_store` / `em_call_cleanup` | 前 8 参进 x0..x7，其余经调用点栈区 |
| 数据 | `em_data_string` / `em_data_scalar` / `em_data_symbol_header` / `em_bss_symbol` | 发射 `.data`/`.bss` 项 |
| 聚合按值 | `em_agg_arg_copy` / `em_copy_block` / `em_save_hidden_ret` / `em_load_hidden_ret` | 调用点拷贝 + 指针传参；>16B 返回经 x8 |
| 浮点 | `em_push_fp` / `em_pop_fp` / `em_fp_binop` / `em_fp_compare` / `em_fp_neg` / `em_int_to_fp` / `em_fp_to_int` / `em_fp_load_local` / `em_fp_store_local` | d0/d1 值约定，s0/s1 为 f32；助记符无 .d/.s 后缀 |

## 3. 当前 AArch64 Linux 目标实现要点

- **栈帧（静态帧）**：函数体先发射进 `o_body` 缓冲，`em_alloc_local` 只
  累计 `c_fp_off` 不发射指令；体发射完毕后 `em_prologue` 用最终帧大小
  一次 `sub sp`，再拷贝体。这样循环体内的局部不会每次迭代压栈。
- **局部访问**：地址 = `fp - off`（off ≥ 0，函数自身帧）或 `fp + |off|`
  （off < 0，第 9 个及以后参数的调用方栈区）；`sub` 偏移超过未缩放立即数
  范围（4095）时经寄存器计算。
- **调用点**：实参先全部压值栈，再按「栈实参（第 9+ 个，低位地址在前）→
  寄存器实参 x7→x0」顺序搬运，`sp` 在 `bl` 时 16 对齐。
- **epilogue**：`mov sp, x29` 必须在返回标签**之后**（显式 `return` 与
  落底路径都汇聚到该标签）。
- **标签命名空间**：代码标签 `.L<n>`（`c_lbl_n`）与数据标签 `.LD<n>`
  （`c_data_n`，从 1 起，0 保留为 NULL 哨兵）分离，避免字符串地址
  与 NULL 冲突。
- **寄存器分工**：x0 值/返回、x9 二元左操作数、x10 地址暂存/间接调用
  目标、x11 取模商（避免与 x10 冲突）。复合赋值经 x10 持目标地址期间，
  取模的商写 x11。
- **main**：无论是否书写 `pub` 都输出 `.globl`（crt1 引用）。

## 4. 前端与后端的分工

- 类型检查、隐式/显式转换、字面量范围、调用实参匹配、常量折叠由前端
  完成；后端只按前端给出的 `type_id` 选择加载/存储宽度与符号性。
- 结构体/联合体裁剪与字段偏移在 pass 1 由 `tg_layout_struct` 计算；
  函数体、全局初始化与数据发射在 pass 2。
- 多值返回（如布局计算的大小与对齐）经专用全局出参
  （`c_layout_size`/`c_layout_align`）传递，避免为一次性二元组引入
  结构体按值返回。

## 5. 聚合按值 ABI（B7 采用机制 b）

ADR-0002 为 TCC 后端选定「包装结构体」（机制 a）；本后端**从零实现**，
采用 **机制 b（调用点拷贝 + 指针传递）**，同样满足 ADR-0001 的全部语言
可观察行为（形参独立、返回独立、递归各层独立、长度参与同型判断）：

- **参数**：调用点把聚合实参拷贝到临时区，参数位传该副本的指针；被调用
  方入口再把指针指向的内容拷进本帧的独立槽（`F_AGGPARAM`），函数体访问
  字段/元素即访问本帧副本。
- **返回**：调用方分配缓冲并把地址放 x8；被调用方在 `return` 时把聚合值
  拷进 x8 缓冲，并把缓冲地址留在 x0；>16B 与 ≤16B 一律走 x8（简化且
  与 ADR-0001 等价）。
- **切片**：`[]T` 视为 16 字节聚合 `{u64 长度, T* 数据}`，走同一套按值
  传递；`[N]T.to_type([]T)` 构造 `{N, &arr[0]}` 视图。

选用机制 b 的理由：新后端不降糖为包装类型，指针传递与既有标量调用路径
一致，实现面小且不依赖 AAPCS64 聚合分类；代价是放弃小数组的寄存器传递
（ADR-0001 未要求该性能特征）。

## 6. 自举缺陷的定位与修复（stage2 浮点常量）

stage1 对全部运行语料与语法语料通过，三代闭环成立；早期 stage2 编译
含浮点字面量的源码时，常量位型被编码为 `0x4160676`（其 `fp64_bits`
函数地址）而非 IEEE754 值。该缺陷**已定位并修复**：

- 现象：stage2 编译**浮点字面量**（run/28、`compiler.yh` 中
  `sem_parse_float_bits` 内的 `10.0`/`1.0` 等）时，常量退回一个代码地址；
- 根因（修复 1）：`sem_push_arg` 无条件 `em_push()`（压 x0），而浮点实参
  的值在 d0。`fp64_bits(mant)` 的调用序列先 `adrp` 装入 callee 地址，
  x0 恰为该地址，于是它被当作实参压栈传入。改用 `sem_push_value`
  （浮点压 d0），调用点的混合搬运路径同步改为按元素类型分别弹 x0/d0。
- 连带暴露（修复 2）：`sem_cast` 缺少「整数 → 整数」窄化转换，窄化到更小
  宽度或改变符号性时未重新扩展 x0，使 `i64` 的 `int` 视图参与运算/比较
  时带上高位残留值。补齐 `sxtw/sxth/sxtb` 与写 w0/`uxth`/`uxtb`。
- 修复后：stage2 浮点常量正确，stage2 与 stage3 对自身拼接源码的发射
  **逐字节一致**（全量固定点），`make bootstrap` 门恢复全量运行语料
  （含 run/28）与全量固定点比较。

**第三处（B8 全量执行时暴露）**：混合整型/浮点形参的寄存器分配。AAPCS64
的整型参数寄存器 x0..x7 与浮点参数寄存器 d0..d7 **各自独立计数**，但
`parse_decl.yh` 曾把形参在参数表中的位置下标当寄存器序号，使
`scale(v f64, k int)` 的 `k` 错读 x1（应为 x0）。修复：参数循环为整型/
浮点各维护独立计数器（`ipos`/`fpos`），按类型递增后传「本类型内序号」。
见 `tests/yh-run/run/35-mixed-args.yh`。

**验收门与探针**：

- 官方门：`make bootstrap`（G1/G2/G2+）与 `make g3`（B8/G3 正式验收，
  见 `docs/01-finished/G3-自举验收报告.md`），需容器 `yh-build`。
- `tests/selfhost/native-selfhost.py`（`make selfhost-native`）：同一套
  源码在本机（Darwin/arm64）跑等价三代闭环，把 GNU/Linux AArch64 汇编
  改写为 Mach-O 形态后本机链接。它不含容器依赖，用于日常回归与缺陷定位；
  注意 macOS 变参 ABI 与 Linux 不同，含 `printf` 的用例在本机不可判
  （脚本只运行并断言不含 printf 的用例）。

## 7. 已知边界

slice/聚合按值与 for-in 已实现；以下仍未实现或无静态检查：切片越界、
切片生命周期证明（ADR-0001 既定，0.0.1 不做防护）、全局聚合变量初始化、
过多的浮点参数（>8 个）与裸变参的浮点实参。

AArch64 后端已按 B8/G3 在真实 Linux 环境验证：三代各自通过全量语料，
stage2 与 stage3 对 `compiler.yh` 与 35 个代表程序的发射逐字节一致。
