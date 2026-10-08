# yh 属性系统与 C 互操作设计

本设计约束见[统一实施方案](../02-plan/yh-属性系统与C互操作统一实施方案.md)。
本文记录语言规则和阶段状态；声明属性见 ADR-0010，自动 C ABI 扩展见
[设计](yh-extern自动C-ABI设计.md)与 ADR-0012。

## 属性语法

顶层声明前可写零个或一个属性列表。一个列表以逗号组合多个属性，属性顺序
不影响含义：

```yh
@[extern, noreturn]
fn c_fatal(code int) void;

@[extern]
pub struct CHandle {
}
```

属性列表必须位于可选 `pub` 之前，并只修饰紧随其后的声明。空列表、尾逗号、
连续属性组和 `pub` 后属性均非法。属性不适用于字段、局部声明、let、const
与 type 别名。类型引用另提供精确的 `@[extern] fn(...)` 分支，仅指定函数
类型的 C 调用约定；可出现在别名右侧或字段类型中，不是声明属性列表。

当前属性集合为：

| 属性 | 适用声明 | 含义 |
| --- | --- | --- |
| `extern` | fn / struct / union / enum | 函数选择 C ABI；无体函数引用 C 符号，有体函数以 C ABI 定义；数据类型共享 C 布局或是不透明类型 |
| `inline` | fn | 内联提示；未满足内联条件时保留普通调用 |
| `noreturn` | fn | 声明函数正常执行不会返回；语义和后端须落实终止控制流 |

`heap` 已删除，未知属性报错。yh 的 `printf` 继续使用现有运行时格式化入口；
本阶段不声明 libc `printf` 的裸 C 变参。

## extern 函数

函数有无体区分引用和定义：

```yh
@[extern]
fn abs(value int) int;

@[extern]
pub fn yh_add(a int, b int) int {
    return a + b;
}
```

无体声明必须有 `extern`，以分号结束；普通 yh 函数仍须有函数体。带体的
`extern` 函数生成 C 可见的裸符号；`pub` 继续独立控制 yh 模块可见性。当前
实现用单独的 C ABI 符号标记与模块接口元数据区分 C 符号和 yh 模块导入。

固定参数 C ABI 已支持定宽整数、bool、f32/f64、指针、C 函数指针和非空
extern struct/union 的参数与返回值。编译器共享分类器自动完成入口、调用及
返回转换：小聚合使用整数寄存器片，HFA 使用浮点寄存器，普通大聚合使用副本
地址或 x8 返回缓冲。寄存器耗尽时按目标规则放到栈上；Linux 与 Darwin 的栈
布局分别处理。普通 yh 聚合、切片、顶层按值数组与不透明值仍拒绝。

调用约定属于函数类型。extern 签名和 extern struct/union 字段内的 `fn(...)`
自动采用 C ABI；普通上下文用 `@[extern] fn(int) int` 声明 C 函数指针。
回调变量、函数指针返回、字段与跨模块接口均保留 ABI；C/yh 函数类型不能互赋
或通过函数类型转换改变约定。编译器不推断 C 原型或指针所有权。

## extern 数据类型

非空 `extern struct/union` 用于 yh 与 C 两侧共享字段布局。空 struct/union
表示不透明类型，只能通过指针持有；不允许构造、按值使用或 `sizeof`。extern
enum 使用固定的 i32 表示。类型名仍在 yh 模块命名空间内，不产生 C 链接符号。

## noreturn 与 inline

`noreturn` 是控制流契约：引用侧可据此终止调用点的正常后继；定义侧必须验证
不返回条件。只有 void 返回类型，且不能由普通落底返回满足契约。外部函数违反
契约时，调用点进入 trap。

`inline` 是优化提示，不改变符号可见性或函数值。当前 SSA pass 只内联本模块
私有、单块、无调用、定长整数标量函数，并受指令预算限制；复杂控制流、浮点、
跨模块与不满足候选条件的调用保留普通调用，不做 AST 文本替换。后续可将该
有限 pass 纳入 Nanopass 的固定管线。

## 实施状态

U0、U1、U2、U3 与 I1 均已实施。验证覆盖 Darwin/Mach-O 原生构建与运行，
包含单组属性语法、C 原型/定义、opaque 类型、C 布局、接口 v1/v2、
noreturn 终止、受限 SSA 内联、固定参数回调、窄整数/浮点参数、第九个参数，
以及 C 源/头文件/对象的链接缓存失效。自动 C ABI 的独立双向项目覆盖聚合、
HFA、联合体、栈溢出、窄参数、函数指针返回与字段回调；同一源码在静态
Linux/AArch64 ELF 中运行通过。Linux 编译器原生自举与模块构建仍需 Linux
种子单独验收；本轮不开放用户 C 裸变参，`printf` 继续使用 yh runtime。
