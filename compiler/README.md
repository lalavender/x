# compiler —— yh 自举编译器（.yh 源码）

用 yh 语言写成的 yh 编译器，目标 **AArch64 Linux ELF**（GNU 汇编方言）。
当前完成到实施方案 v2 的 B7：词法、纯语法解析、完整语义与 AArch64 后端
（`--syntax-check` + `--emit-asm`），覆盖聚合按值、切片、for-in、类型化
变参、浮点、structInit 作值；并已跑通**三代闭环**：

```
stage0（C 版 yh）──编译──▶ stage1 ──编译──▶ stage2 ──编译──▶ stage3
                              │                │
                              └─ 自解析 ✓      └─ stage2.s 与 stage3.s 逐字节相同（固定点）
```

## 构建与验证

```bash
make bootstrap   # G1 语法 + G2 三代闭环 + G2+ 全量固定点
make g3          # B8/G3 正式验收（bootstrap + 分代全量复验 + 归档）
```

`make bootstrap` 按 Makefile 中 `SELFHOST_SOURCES` 的显式顺序把本目录
拼接为 `tmp/bootstrap/compiler.yh`（只连接完整顶层声明、保留换行），
然后逐门验证：

1. **拼接确定性**：两次拼接逐字节一致；
2. **G1 语法自举**：stage1 自解析自身拼接源码到 EOF；全量语法语料差分
   66 正例接受 / 29 反例拒绝；
3. **G2 三代闭环**：stage1 编译自身得 stage2；stage2 自解析、语法差分、
   全量运行语义语料（`tests/yh-run/run/` 全部用例）全过；
4. **G2+ 固定点**：stage2 编译自身得 stage3；stage2.s 与 stage3.s
   （对自身拼接源码的完整发射）逐字节相同；stage3 自解析通过。

`make g3` 在 `bootstrap` 之后由 `tests/selfhost/g3-acceptance.py` 完成
**G3 正式验收**：stage1/2/3 三代各自跑全量语法与运行语料、stage3 自解析、
stage2 与 stage3 对 35 个代表程序逐字节一致的汇编、重复发射确定性、
53 个反例的诊断质量，并把源码/汇编/ELF/工具链版本/SHA-256 归档到
`tmp/bootstrap/artifacts/`。验收报告见
`docs/01-finished/G3-自举验收报告.md`。

前置条件：运行中的 docker 容器 `yh-build`（仓库挂载于 `/work`）、
`tmp/sysroot`。任一前置缺失直接失败，不 SKIP。

容器不可用时，可用本机（Darwin/arm64）等价差分：

```bash
make selfhost-native
```

`tests/selfhost/native-selfhost.py` 用同一套源码在本机跑 stage0 → stage1
→ stage2 → stage3，把发射的 GNU/Linux AArch64 汇编改写为 Mach-O 形态后
本机链接；校验三 stage 自解析、全量语法语料、汇编固定点，并运行不含
`printf` 的运行语料（macOS 变参 ABI 与 Linux 不同，含 `printf` 的用例在
本机不可判）。该目标用于日常回归与自举缺陷定位。

## 文件与职责

| 文件 | 职责 |
| --- | --- |
| model.yh | token 常量、类型/符号常量、Tok/Res/CType/CSym 等结构、全部全局状态 |
| buffer.yh | 源文件整读（open/read/close）、汇编输出缓冲、诊断、字节写出 |
| lexer.yh | 字节词法器：保留字、数字/转义、注释、运算符最长匹配 |
| target.yh | 目标数据模型：字长、对齐、结构体布局（**换平台的第一步**） |
| parse_type.yh | 类型引用解析 + 解析器共用游标工具 |
| symbols.yh | 名字池、类型表、符号/作用域、类型兼容、常量折叠、prelude 登记 |
| emit_arm64.yh | AArch64 指令发射：值栈、访存、控制流、调用约定、段与符号 |
| sem.yh | 语义钩子（表达式/语句/声明）、两遍编译驱动、fn/结构体布局 |
| parse_expr.yh | 表达式优先级链、后缀链、structInit 与「字面量 vs 块」消解 |
| parse_stmt.yh | 语句：块/if/for/switch/return/goto/标签/赋值 |
| parse_decl.yh | 顶层声明两遍处理：let/const/fn/type/struct/union/enum |
| driver.yh | `main(argc, argv)`、`--syntax-check` / `--emit-asm` 分派 |

## 已实现的语义（B7）

- **聚合按值**：struct/union/数组作参数与返回，调用点拷贝 + 指针传递，
  >16 字节返回经 x8 隐藏缓冲；嵌套结构体字面量。
- **切片**：`[]T` 规范化视图 `{u64 长度, T* 数据}`，`len`、下标、
  `[N]T.to_type([]T)` 视图构造、切片实参与遍历。
- **for-in**：数组、切片、区间 `a..b`（左闭右开）三种迭代源，
  元素/下标绑定为每轮值拷贝。
- **类型化变参**：末尾 `name ... T` 打包为 `[]T` 切片，零变参为空切片。
- **浮点**：f32/f64 经 d0-d7 传参与返回，`+ - * /` 与比较、
  `f32↔f64`、整数↔浮点 `to_type`。
- **structInit 作值**：结构体字面量可用于初始化、实参、返回、嵌套字段。

拼接顺序即依赖顺序（类型/常量集中声明在前的文件，函数可前向调用）。

## 架构与多平台

后端分三层，边界即多平台接入缝：前端语义（`symbols.yh`/`sem.yh`/
`parse_*.yh`）→ 目标数据模型（`target.yh`）→ 指令发射（`emit_arm64.yh`）。
前端只调用 `em_*` 抽象机原语，不含 ISA 细节；换目标 = 新数据模型 +
新 `emit_<isa>.yh`。原语契约与换平台步骤详见
`docs/03-design/yh-自举后端架构.md`。

## 自编子集与已知边界

编译器自身源码遵守 B5 子集：整数/字节/指针、结构体字段、堆缓冲、
全局/局部变量、普通函数、递归、`if` 与条件 `for`（无限循环写
`for 1 { }`，因 stage0 的无条件 `for` 不识别 continue）、赋值与位运算、
`sizeof(T)`、prelude 的 open/read/write/close/malloc/free/memcpy/
strlen/exit。

B5 曾显式拒绝、B7 已实现的特性：按值聚合参数/返回、切片与数组→切片视图、
类型化变参、for-in、结构体字面量作值、浮点运算。**仍未实现**：全局聚合
变量初始化（`var x T = ...` 之类），以及切片越界/生命周期的运行时防护
（ADR-0001 既定，0.0.1 不做）。
