# extern 自动 C ABI 实施完成

- 日期：2026-10-03
- 状态：固定参数范围已实施并通过本机主门与静态 Linux/AArch64 双向运行
- 设计：[自动 C ABI](../03-design/yh-extern自动C-ABI设计.md)
- 方案：[实施方案](../02-plan/yh-extern自动C-ABI实施方案.md)
- 决策：[ADR-0012](../adr/0012-yh函数类型保存调用约定并自动转换C-ABI.md)

## 交付

`@[extern]` 函数的声明、定义与调用自动采用目标 C ABI。参数和返回值支持
现有 C 标量、C 函数指针以及非空 extern struct/union，无需手写 C 适配层。
普通 yh 函数继续采用既有调用约定。

`gen/abi_c.yh` 提供共享的值描述、目标游标和位置分类器。普通小聚合按整数
寄存器片传递，HFA 按浮点元素传递，普通大聚合传独立副本地址或通过 x8
返回。HFA 先于大聚合分类；聚合装不进剩余寄存器时整体上栈。Linux 使用
至少八字节栈槽，Darwin 使用自然大小与对齐，调用栈最终十六字节对齐。

`gen/sem_cabi.yh` 按计划转换调用、入口和返回；聚合在函数体内继续以地址
表示。参数求值时复制聚合，入口先保存所有参数寄存器，再进行聚合复制。
短聚合尾片精确读取，避免越过对象边界；返回缓冲按已有帧规则分配。

函数类型保存 ABI，参与去重、相容检查、接口、IR 与缓存。extern 签名和
extern struct/union 字段中的函数类型默认 C ABI；普通上下文可以使用：

```yh
@[extern]
struct Pair { quotient int; remainder int; }

@[extern]
fn div(a int, b int) Pair;

type Callback = @[extern] fn(int) int;
@[extern]
fn choose() fn(int) int;
```

回调变量、返回函数指针和字段调用均保留 C ABI。C/yh 函数类型不能互赋或
通过函数类型转换改变调用约定。显式 C 函数类型也检查完整签名，局部变量和
别名无法绕过切片等边界限制。接口仍使用 v1/v2 外壳，函数类型显式输出
`@[extern] fn(...)`。声明索引可正确区分返回函数类型和下一条函数声明。

IRFunction 与 IRCall 保存 ABI；序列化版本从 4 升为 5，前端缓存键升为 10。
SSA 整数后端消费共享参数分类，窄栈参数按目标宽度读取/写入。浮点、聚合和
间接调用尚未降低到 SSA 的形态使用直接发射路径。

## 回归与修复

- `tests/modules/projects/autoabi/`：C 与 yh 两侧独立声明同一接口，双向覆盖
  1/3/8/12/16 字节小聚合、24 字节大聚合、嵌套 HFA、数组字段、联合体、
  整数与浮点寄存器不足、九个 f32 后接 f64、窄栈参数、参数独立副本、
  div_t 形状的正负整数返回、函数指针返回、回调变量与字段、跨模块接口。
  项目门额外确认至少两个窄参数探针进入 SSA，避免回退掩盖后端问题。
- `run/53-cabi-values.yh` 和 `fail/34–38`：聚合运行、两种 ABI 禁止互赋、
  显式转换拒绝、共享字段拒绝普通 yh 回调、独立 C 函数类型拒绝切片。
- 语法正例 68 和反例 40–42：精确的类型前缀与错误属性位置/组合。
- `irverify`：函数/调用 ABI 合法性、序列化往返和损坏数据拒绝。
- C 项目暴露浮点复合赋值临时槽跨函数复用错误，导致当前帧外写入与崩溃。
  函数开始时重置偏移；`run/54-float-temp-functions.yh` 已先复现再验证修复。
- 项目门的旧栈访存指令文本断言不再适用，保留真实第九参数运行验证。
  标准库清单的未支持规划字段保留为注释，使现有标准库模块继续可验收。

## 验证证据

| 验收 | 实测结果 |
| --- | --- |
| `make` | 成功，使用入库种子冷编 |
| `make test` | ANTLR 和编译器语法各 68/68 正例、42/42 反例；运行 54/54、拒绝 38/38、编译通过 8/8，共 100/100 |
| `make selfhost-native` | 退出 0；候选 cc3→cc4 的 12 个模块产物逐字节一致；54 个编译器源文件自解析通过；模块语料 17/17；项目用例 79/79 |
| Darwin/AArch64 C 双向项目 | 原生运行退出 0，包含跨模块和 SSA 路径 |
| Linux/AArch64 C 双向项目 | 发射/链接/容器运行均退出 0，静态 ELF 无 PT_INTERP、DT_NEEDED 或未解析符号 |
| diff 检查 | `git diff --check` 通过 |

Linux 验收复用 `autoabi` 的真实 yh 与 C 源码，将 yh 模块合并为一个编译单元，
由当前编译器 `-target linux --emit-asm` 发射，再用 Zig 0.16.0 的 C 编译器
独立编译 C 侧并以 `-nostdlib -static` 链接自有 `_start`。在 Linux/arm64
容器运行；此证据验证目标 ABI，不等同于已有 Linux 原生编译器种子或模块
构建门。Linux 种子及原生滚动自举仍是独立待办。

临时证据在 `tmp/auto-cabi/`：`make-test-green.log`、`selfhost-green.log`、
`linux-result.json`、`linux-elf-audit.txt` 和 `linux-undefined.txt`。
`bin/yh` 未更新，种子 SHA-256 保持
`c4168844db4f8896b50f02ad29a45cc709b90f112e6075fe0a285ed414ec1719`。

## 保留边界

不支持 C 变参、顶层按值数组、切片、不透明值、普通 yh 聚合及尚未表达的
binary128/向量等 C 类型。C 数据符号、CRT/库归档出口、TLS/线程/信号原语
和 libc 主体仍按[libc 候选方案](../02-plan/yh-libc分阶段候选方案.md)单独推进。
