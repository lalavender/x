# yh 运行覆盖缺口矩阵（0.0.2 B0 基线 → B2 补齐后）

> **历史文档**：矩阵全项已补齐（B0→B2 闭合）。文中「Darwin Mach-O + 交叉容器
> 双模式运行口径」随 stage0 删除失效，现行门为 `make selfhost-native`。
建矩阵时间：2026-09-28（B0）；B2 结束时逐项补齐并回写状态。对照两个
维度：`tests/yh/` 的语法语料（编译器**能解析**什么）与 `tests/yh-run/`
的运行用例（编译器**算得对**什么）。语法通过不代表语义正确；补齐一项
就把状态改为「已补 <文件名>」。

运行模式：Darwin Mach-O 本机运行 + 交叉 AArch64 Linux ELF 容器运行，
两种模式必须同批全绿（`make test` 与 `check.py --cross`）。

## 1. 已有运行覆盖（tests/yh-run/run/，B0 基线 15 例）

| 主题 | 用例 | 覆盖内容 |
| --- | --- | --- |
| 基础输出 | 01-hello | printf、字符串、退出码 |
| 整数运算 | 02-arithmetic | 四则、优先级、负数除/模向零截断 |
| 逻辑短路 | 03-short-circuit | &&/|| 短路副作用 |
| 分支 | 04-if-else | if/else if/else |
| 循环 | 05-loop | 无限/条件 for、break、continue |
| switch | 06-switch | 值匹配、default |
| goto | 07-goto-label | 向后跳转成环、向前越过死代码 |
| 递归 | 08-recursion | 阶乘、斐波那契、顶层前向调用 |
| 全局变量 | 09-globals | 全局读写、字符串全局 |
| 字符串 | 10-strings | %d/%s/%c、转义、strlen |
| 指针 | 11-pointers | 取址/解引用读、指针参数 |
| sizeof | 12-sizeof | 标量/指针尺寸 |
| 退出码 | 13-exit-code | main 返回值即退出码 |
| 多参数 | 14-many-args | 12 个整型参数（超 8 寄存器走栈） |
| 复合赋值 | 15-compound-assign | += -= *= /= %= & \| ^ << >> |

## 2. 缺口矩阵（语法可解析、运行无覆盖）

| # | 能力 | 语法语料 | 状态（B2 后） |
| --- | --- | --- | --- |
| G01 | struct：字段读写、嵌套、按值传参/返回 | 08-expr/11、12 | 已补 run/25（含大 struct x8 间接返回） |
| G02 | union：字段共享存储 | 09-types | 已补 run/26 |
| G03 | enum：常量、switch 匹配 | 09-types | 已补 run/26 |
| G04 | 数组按值：实参拷贝、返回拷贝、递归、大数组 | 05-branch 等 | 已补 run/27 + fail/10（长度不匹配拒绝） |
| G05 | 切片 `[]T`：len/下标/数组视图 | 09-types/01 | 已补 run/27 |
| G06 | for-in：数组/切片/区间遍历 | 06-loop/02、03 | 已补 run/27 |
| G07 | 类型化变参 `name ... T` | 10-prelude | 已补 run/28（含零变参） |
| G08 | 函数指针：传递、调用、经参数回调 | 09-types/02 | 已补 run/22（赋值/回调/返回选择） |
| G09 | 浮点 f32/f64：运算、参数、返回、混合提升 | 09-types/03 | 已补 run/28（f64 参数/返回、f32 混合） |
| G10 | u32/u64 位移与符号扩展、无符号环绕 | 08-expr/05 | 已补 run/23 |
| G11 | 互递归 | 无（08 仅自递归） | 已补 run/24 |
| G12 | 链式结构 `struct Node { next *Node; }` | 08-expr/14 | 已补 run/24（malloc 结点+全局指针写） |
| G13 | `.to_type(T)` 显式转换的运行行为 | 08-expr/15 | 已补 run/19（窄化）、run/27（切片视图） |
| G14 | 标准输入 read / close | prelude 未登记 | 已补 run/16-18（分块/短读/NUL/EOF/坏 fd/open-close） |
| G15 | 动态缓冲 malloc/memcpy/free 扩容 | prelude 已有 | 已补 run/20（1 字节/扩容边界/NUL/1 MiB/OOM） |
| G16 | main(argc, argv) | decl 检查仅无参 | 已补 run/21 + fail/09（**int 签名拒绝） |
| G17 | 容量边界：包装类型、switch 分支、大源文件 | 压力探针 | 已补 run/29 + fail/11（switch>512）、fail/12（包装>512） |

## 3. 明确不进运行矩阵的项目

- ANTLR 语法回归（`tests/yh/check.py` ANTLR 模式）与编译器语法模式
  （`--compiler`）继续按现有口径独立运行，不与运行矩阵合并。
- 裸 C 变参的用户侧拒绝已由 `fail/04-bare-varargs.yh` 覆盖；
  prelude 提升规则（printf 各类型组合）由 10-strings/19/23 部分覆盖，
  B2 不再扩充，除非自举工作负载实际触及。
- 浮点严格 IEEE 边界（NaN/Inf/次正规）不在 B2 范围：自举编译器
  工作负载只要求常规双精度运算正确。

## 4. B2 期间实际发现并修复的编译器缺陷（超出原缺口清单）

| 缺陷 | 修复 | 回归用例 |
| --- | --- | --- |
| `true`/`false` 推为 int，bool 初始化被拒 | 字面量类型改为 bool | run/19 |
| 整数字面量无法隐式窄化（`let x u8 = 7` 被拒） | §4.1 可表示字面量允许，全局初始化同步做范围检查 | run/19 + fail/07 |
| 数组左值传 `*void` 参数不退化（坏指针/SIGBUS） | yh_assign_cast_to 先做左值退化 | run/16 |
| 裸变参小整数无 C 提升（i8 打印 254） | i8/i16/u8/u16/bool → int 提升 | run/19、23 |
| 函数名无法赋给 fn 类型（VT_STATIC 拒绝） | 函数→同签名 fn 类型隐式转换（签名结构相等） | run/22 |
| struct/数组按值返回的调用缺隐藏返回指针（ICE/段错误） | 调用方压 sret 临时 + 结果取临时左值 + 浮点返回取 v0 | run/25、27、28 |
| 调用结果（包装 struct）赋回数组变量被拒/块拷贝错误 | 包装→数组同型允许，vstore 走块拷贝 | run/27 |
| switch 分支数组固定 128 且超限静默截断 | 扩到 512 并干净报错 | run/29 + fail/11 |
| 包装类型登记上限 128 留量不足 | 扩到 512（超限本就干净报错） | fail/12 |

## 5. 使用方式

B1/B2 每补一个用例：在 `tests/yh-run/run/` 新增 `.yh`，Darwin 与
`--cross` 双绿后回写矩阵状态。B2 结束时本矩阵不存在「待补」行（§3 除外）。

