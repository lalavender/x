# compiler —— yh 自举编译器（.yh 源码）

> 2026-09-30：源码已按 cmd/gen/lex/parse 目录移动，但 Makefile 与
> 本机自举清单尚未更新，当前构建因此中断；本文件下方描述的是移动前
> 的已验证构建。恢复构建、填充 mod.toml 与文件拆分的现行步骤见
> [按目录模块化实施方案](../docs/02-plan/yh-编译器模块化详细方案.md)。

用 yh 语言写成的 yh 编译器，目标 **AArch64 Linux ELF**（GNU 汇编方言）。
当前完成到实施方案 v2 的 B7：词法、纯语法解析、完整语义与 AArch64 后端
（`--syntax-check` + `--emit-asm`），覆盖聚合按值、切片、for-in、类型化
变参、浮点、structInit 作值；并已跑通**三代闭环**：

```
bin/yh（入库种子）──编译──▶ yh ──自编──▶ yh'（固定点：.s/.s.i 逐字节相同）
```

> **本目录是主要开发编译器（ADR-0006/0007）**：0.0.3 起仓库已删除
> C 版 stage0 与 bootstrap，构建只依赖入库种子 `bin/yh`（上一版编译器
> 二进制）。自举产物可直接本机使用（宿主自动方言探测、
> `yh file -o out` 双形态 CLI），日常验证以
> `make selfhost-native` 为主门。

## 构建与验证

```bash
make             # 产出 yh（本目录源码的本机二进制，主编译器）
make test        # 三层回归
make selfhost-native  # 本机全套门（两代固定点 + 全量语料）
```

`make` 的 `yh` 由入库种子 `bin/yh`（上一版编译器）对本目录 mod.toml
项目 `yh build` 产出，形态随宿主（Darwin → Mach-O，Linux → ELF），
可直接用于编译 .yh 程序与跑语料：
`python3 tests/yh-run/check.py --compiler $PWD/yh`。

`make selfhost-native` 由 `tests/selfhost/native-selfhost.py` 执行
本机全套自举门（0.0.3 滚动自举，无 stage0；种子 = 入库的 `bin/yh`）：

    bin/yh build compiler/  → cc2（冷编）
    cc2     build compiler/     → cc3（冷编）

门：①固定点——cc2/cc3 全部模块 .s/.s.i 逐字节一致；②cc3 自解析
compiler/ 全部源文件；③cc3 语法语料（tests/yh 正例全过、反例全拒）；
④cc3 运行语料（tests/yh-run 全量 run/fail/pass）。该目标用于日常
回归验证；滚种子（`make seed`）前必须全绿。

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
