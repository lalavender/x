# yh 属性系统与 C 互操作统一实施方案

- 状态：**已实施并通过本机主门；Linux AArch64 原生运行另待环境验收**。
- 日期：2026-10-02。
- 来源：用户确定的单组属性列表、删除 heap 的决定，与
  [C 互操作 FFI 原方案](yh-C互操作FFI实施方案.md)。
- 约束：[AGENTS.md](../../AGENTS.md)、[现役语法](../yh.g4)、
  [ADR-0001](../adr/0001-yh数组按值调用边界.md)、
  [ADR-0002](../adr/0002-yh数组与切片内部ABI机制.md)、
  [Nanopass 优化规划](yh-Nanopass风格优化架构实施方案.md)。

## 1. 已确定规则与实施边界

用户已确定：每个声明最多一个 `@[...]` 属性列表，多个属性以逗号分隔；
删除 heap，内存分配以后通过显式声明另行设计。当前属性集合只有 extern、
inline、noreturn，不预留数据属性或自动分配机制。

本方案实施的语义是：属性描述声明行为，pub 描述 yh 模块可见性。
extern 函数无体为 C 引用、有体为 C ABI 定义，不再新增前置 extern 关键字。
数据类型保持既有值语义、构造行为与 sizeof，不引入引用类型或枚举装箱。

实施分成三个可验收交付：

1. U0–U2：属性语法、extern 函数/类型、模块透传、noreturn 的完整行为。
2. U3：项目级 C 混编、回调、标量目标 ABI 与构建缓存验收。
3. I1：与现有 Nanopass NP5 共用的有限 SSA 内联。

实现不依赖新增内存管理机制或整个优化架构完成。inline 通过受限 SSA pass
落地；不满足候选条件时保留普通调用。
用户补充决定：本轮暂不处理将 `printf` 改为 libc 变参函数；继续使用现有
yh 格式化运行时，不新增用户 C 裸变参声明。其余推荐语义按本实施方案落地。

## 2. 仓库事实与原方案需要修正之处

| 已核实事实 | 对统一方案的影响 |
| --- | --- |
| struct/union/enum 当前必须带 pub | 推荐保留；标准写法为 `@[extern] pub struct Demo {}`，裸类型示例需要补 pub |
| `pub let` 已于 2026-10-02 取消 | 本轮不恢复它；C 全局通过 C 包装函数访问，全局变量属性另行讨论 |
| `F_EXTERN` 同时用于 prelude 和普通模块导入 | 不能用它判断 C ABI；新增独立的 C ABI 元数据 |
| `F_RUNTIME_USED=8192` 已占用 | 不沿用上一方案的 `F_NORETURN=8192`，实现时统一核对并分配标志位 |
| printf/malloc/free 当前是 yh 自有 intrinsic 运行时入口 | 用户 C 声明不能仅凭同名同签名合并，更不能混用 yh 与 C 分配器 |
| 函数值写法为 `fn(int) int`，本身已表达函数指针 | 回调示例使用该形式，不额外写成 `*fn(...)` |
| SSA 目前只覆盖部分整数/布尔、固定参数直接调用 | 指针、浮点、变参和间接调用不能因为登记了属性就视为新后端已支持 |
| `sem_fn_end` 会为普通非 void 函数生成落底返回 0 | noreturn 要新增自己的控制流契约；现状没有可直接放行的通用“缺 return 检查” |
| 接口加载按 yh 正文登记，再改写 pub 名字并加 F_EXTERN | 必须保留 C ABI 和裸名属性；C 类型名仍归属 yh 模块命名空间 |
| TOML 解析器当前不支持数组 | `[c]` 字符串数组需要同时扩充解析器和 project schema |

ABI 还有两个必须修正的假设：

- **大于 16 字节不等于与现有 yh 聚合 ABI 兼容**。例如三个 double 的
  24 字节结构体属于 HFA，适用浮点聚合规则，不能直接按大结构体传指针。
  因此 v1 统一禁止 struct/union 按值跨 C 边界，以指针或 C shim 转换。
  依据：[Arm AAPCS64 的 HFA 与参数分类规则](https://github.com/ARM-software/abi-aa/blob/main/aapcs64/aapcs64.rst)。
- **Darwin 与 Linux 的 C ABI 不能只靠汇编符号前缀区分**。Apple arm64
  对窄整数扩展、栈参数及变参有不同规则，plain char 也是有符号类型。
  yh char 的映射应写作 unsigned char，文本指针另说明字节约定。
  依据：[Apple arm64 ABI 文档](https://developer.apple.com/documentation/xcode/writing-arm64-code-for-apple-platforms)。

## 3. 属性分类、位置和组合

| 类别 | 属性 | 允许的声明 | 推荐语义 |
| --- | --- | --- | --- |
| 公用 | extern | fn / struct / union / enum | 函数选择 C ABI 与外部符号规则；类型声明表达 C 共享布局或不透明类型 |
| 函数 | inline | fn | 优化提示，允许编译器保留普通调用 |
| 函数 | noreturn | fn | 正常控制流不返回调用者，首版要求返回类型为 void |

统一书写：`可选单组属性列表 → 可选 pub → 声明`。一组可有多个属性；
连续多组属性非法，`pub` 后再写属性也非法。属性之间的顺序不改变语义。
属性只附着紧随其后的一个顶层声明，不修饰 module/import、字段、局部
变量、语句、let、const 或 type 别名。空组、尾逗号、属性参数暂不支持。

```yh
// 多个属性统一写在一个列表中。
@[extern, noreturn]
fn c_fatal(code int) void;

// 普通 yh 函数也可以组合函数属性。
@[inline, noreturn]
fn stop() void {
    c_fatal(1);
}
```

组合检查：

- 未知属性、同组重复属性、声明类别错配均报诊断并定位属性 token。
- extern + noreturn 允许用于引用或定义；inline + noreturn 允许用于定义。
- inline 要有函数体；extern + inline 只允许有体定义，并保留 C 可见的实体。
- 删除的 heap 按未知属性拒绝，不登记为保留属性或提供兼容分支。
- 分阶段实现时，noreturn 行为尚未实现就明确报错，不能静默忽略控制流契约。

数据类型只接受 extern；所有包含 inline/noreturn 的数据声明均报错。
函数允许的组合明确如下，避免每个解析分支自行决定：

| 属性列表 | 无体引用 | 有体定义 |
| --- | --- | --- |
| extern | 允许 | 允许 |
| noreturn | 不允许 | 允许，要求 void 且无正常返回路径 |
| inline | 不允许 | 允许 |
| extern, noreturn | 允许，要求 void | 允许，要求 void 且无正常返回路径 |
| extern, inline | 不允许 | 允许，保留 C 可见函数实体 |
| inline, noreturn | 不允许 | 允许，要求 void 且无正常返回路径 |
| extern, inline, noreturn | 不允许 | 允许，保留 C 实体并检查不返回契约 |

## 4. 参考语法及无歧义检查

建议保留现有无属性声明分支，单独增加有属性声明分支；普通 fn 仍必须带体，
避免把现有“普通函数原型非法”测试无意改成合法。

```antlr
topLevelDecl
    : 'pub' exportedDeclBody
    | plainDeclBody
    | attributeGroup attributedDecl
    ;

attributeGroup
    : '@' '[' attributeName (',' attributeName)* ']'
    ;

// extern/inline 已是保留字；noreturn 在列表内按属性名识别，
// 在列表外仍是普通标识符；已删除的 heap 也不新增保留字身份。
attributeName
    : IDENT | 'extern' | 'inline'
    ;

attributedDecl
    : 'pub'? attributedFnDecl
    | 'pub' (structDecl | unionDecl | enumDecl)
    ;

fnSignature
    : 'fn' IDENT '(' paramList? ')' typeRef?
    ;

fnDecl
    : fnSignature block
    ;

attributedFnDecl
    : fnSignature (block | ';')
    ;
```

新增分支以 `@` 开始，与原声明首 token 集不相交；属性列表以逗号和 `]`
确定边界；函数签名结束后 `{` 与 `;` 互斥。因此本次新增分支不引入解析歧义。
此处是规则草案，U0 必须将其代入完整 g4 并运行 ANTLR 门后才能确认。

语法门检查属性形状和声明位置；已知名称、适用类别、重复及“只有 extern
可无体”等由属性/语义检查执行。`@[unknown] fn f() {}` 是语法可解析、
语义非法，应放语义反例，不能要求纯 ANTLR 门判为语法非法。

## 5. extern：统一 FFI 的两种函数形态

```yh
// 引用：由 C 提供定义，yh 不生成函数体。
@[extern]
fn abs(x int) int;

// 定义：编译函数体，按 C ABI 提供符号 yh_add。
// pub 额外允许其他 yh 模块引用，不是 C 导出的前置条件。
@[extern]
pub fn yh_add(x int, y int) int {
    return x + y;
}
```

`@[extern] fn demo() {}` 是合法的 C ABI void 函数定义：函数体正常编译，
不能被忽略。也不需要新增 export 属性；是否有体已经清楚地区分了引用与定义。

`pub` 与 extern 正交：允许 `@[extern] pub fn abs(...) int;`，使某个 yh
模块集中声明并转出 C API；无 pub 时仅本 yh 模块可见，但定义仍可供 C 链接。
所谓裸名是“不加 yh 模块后缀”；Darwin 仍遵守其汇编符号 `_` 前缀。

### 数据类型

```yh
// 非空类型：与 C 两侧手写定义共享字段布局。
@[extern]
pub struct Point {
    x int;
    y int;
}

// 空 struct/union：不透明类型，只允许以指针持有。
@[extern]
pub struct CHandle {}

// enum：首版为固定 i32 表示与常量集合。
@[extern]
pub enum Status {
    success = 0;
    failure = 1;
}
```

- 非空 struct/union 做递归布局合法性检查；首版无 packed、位域、自定义对齐。
  C 侧用固定宽度字段，并通过 sizeof/offsetof/读写往返核验布局。
- 不透明 struct/union 不能 sizeof、按值使用、做字段或构造实例；允许 `*T`。
  空 enum 首版拒绝，不推测一个不完整 C enum 的表示。
- extern enum 对接 C 的 int32_t 与常量；原生 C enum 只有在表示已验证时才对接，
  不承诺任意 C 编译器选项都使用 yh 的有符号 i32。
- C 类型名没有链接符号，不做“类型名裸名导出”；它们仍有正常 yh 模块身份。

### v1 函数边界

最终支持已验收的定宽整数、bool、f32/f64、指针、void 返回；每个目标分别
验证调用和定义两侧。U1 可以先交付较窄的 i32/u32/i64/u64/指针范围，未覆盖
形态显式报“不支持的 C ABI 签名”，到 U3 扩充并验收。

所有 struct/union、数组、切片按值跨边界均拒绝，既检查引用，也检查定义、
回调和取址后使用的签名。指针所指的数据可共享；切片用数据指针加长度表达，
不能拿 yh 切片头冒充 C 数组。enum 按 i32 规则处理。

本轮不新增用户可声明的 C 变参函数，也不把 yh 类型化变参包装成 libc 变参。
内置 `printf` 继续使用 yh runtime intrinsic；它的行为/格式支持沿用现状，
作为本次回归基线，不把它算作 C FFI 验收。libc printf 与其余 C 变参留待
用户单独提出后再设计。

C 全局引用/导出不在此次属性适用范围内；使用 `c_get_counter/c_set_counter`
等包装函数完成同等互操作需求，后续如要支持变量属性，重新评审其与 let
不导出的关系。errno 等平台宏或线程局部接口也通过 C shim 获取。

## 6. noreturn 与 inline

### noreturn：必须检查的控制流契约

首版只接受 void 函数。有体定义不能包含可达 return，也不能正常落到函数尾；
可以由无限循环或另一 noreturn 调用终止。C 引用把此属性作为调用者契约。
控制流支持不足的函数需要扩充分析或明确诊断，不能依靠隐式 return 0 通过。

语义检查仍覆盖完整源代码。构造控制流时，调用后没有正常后继；SSA 使用
CALL + UNREACHABLE，旧后端也实现相同终止行为。若外部函数违约返回，
调用点进入 trap，避免落入相邻代码。

需要覆盖 if/短路表达式、嵌套调用实参的求值顺序及部分分支终止：只终止实际
执行了 noreturn 调用的路径。不把条件调用后的所有路径一概判为不可达。
普通函数指针未保留该效果时，间接调用保守地视为可能返回。

### inline：接入现有优化规划

inline 是提示，不保证每次展开，也不等价于 C 的 inline 链接语义。属性本身
不改变可见性；取址和 C 导出仍需要函数实体。初期接口只传属性和签名，
不传函数体，跨模块调用保持普通调用。

I1 复用 Nanopass NP5 的有限 SSA 内联：从模块内已有 SSA 小函数开始，
先限制为无递归、非变参、无复杂控制流的固定参数整数函数；固定指令预算，
保持实参求值一次和副作用顺序，稳定遍历并验证重映射。
未进入 SSA 或不满足条件则保留调用。内联依赖被调函数体，缓存必须体现该依赖。
不另写 AST 替换内联器。I1 以真实 IR/汇编变化和运行一致性验收；仅登记属性
不算内联优化已经完成。

## 7. 内存分配独立后续设计

本轮删除 heap 及其构造、装箱、分配失败、所有权和生命周期实现任务。
普通 `T{...}`、`let v T`、值拷贝、参数/返回和 sizeof 继续保持现役规则。

内存分配以后以显式声明另立设计与验收，本方案不提前选择关键字、语句
形式、返回类型或自动释放方式，也不为其增加类型标志或运行时入口。
现有显式指针和 malloc/free 继续按现役约定使用；FFI 对象由对应分配器释放，
C 返回的对象通过配套 C 释放函数处理，不合并 yh 与 C 分配器。

## 8. 实现边界与数据流

```text
token 快照 / 顶层声明索引
  → 单组属性列表及精确位置、实际关键字位置、声明名字位置
  → 声明 AST / 属性类别与组合检查
  → 类型属性、函数 C ABI、引用或定义身份、控制流效果
  → 模块接口及缓存键
  → 普通语义发射路径或 SSA lowering
  → 目标 C ABI / noreturn 终止 / 可选有限内联
  → 汇编对象 + C 对象 + 系统库 → 链接
```

建议落点（以职责为准，不创建新的 compiler 子项目）：

| 模块/文件 | 工作 |
| --- | --- |
| lex/lexer.yh、gen/model.yh | TK_AT；声明属性、类型属性、C ABI 身份；统一分配未占用标志 |
| parse/parse_attr.yh（新增） | 单组属性读取与组合校验；固定三属性位掩码，保留 token 位置，供索引和语义共享 |
| parse/parse_decl.yh、ast_decl.yh | 所有遍次和跳过路径识别属性前缀；PDecl 保存实际 keyword/name 位置，AST 不再用 start+1 推算 |
| gen/symbols.yh、sem_decl.yh、sem_call_literal.yh、sem_flow.yh | 原型/定义登记，边界签名检查、C ABI 调用/入口、noreturn 契约 |
| parse/ast_expr.yh、ast_ir_call.yh、ast_ir_build.yh、ir/ssa_call.yh | C ABI 和调用效果进入受检表达式与 IR；缺覆盖的形态保持有说明的旧路径 |
| gen/emit_arm64.yh、backend/arm64_call.yh、arm64.yh | 裸名、平台调用分类、窄整数扩展、栈参数、不可达 trap；覆盖新旧路径 |
| parse/iface.yh、ast_ir_cache.yh、ir/ssa_serialize.yh | 属性与 ABI 透传、稳定序列化、缓存版本和失效 |
| cmd/toml.yh、project.yh、project_state.yh、link_cache.yh | [c] 字符串数组、配置检查、显式 argv 编译与混链 |
| ir/ssa_inline.yh（I1 再新增） | 与 NP5 共用的受限 SSA 内联，不提前引入通用优化框架 |

C ABI 不等于 F_EXTERN。定义与引用使用不同符号身份，二者共享独立的 C ABI
标记；普通 yh 导入虽带 F_EXTERN，仍保留 yh ABI。函数值/回调同样保留并
检查 ABI，不能只在直接调用时查 CSym 标志。

首版回调限于在 extern 参数签名上下文中，直接传入已标注 extern 的函数；
ABI 未表达或丢失的普通 fn 存储/转换路径先拒绝，不能仅因形参类型相似放行。
普通函数指针语法仍存在，完整 C 函数值类型扩展作为后续独立切片。

接口建议：无属性继续输出现有 v1；有属性输出 v2；最多一组列表，按
extern、inline、noreturn 的固定顺序输出已有属性。加载器
支持 v1/v2；普通函数仍使用原有签名占位表示，C 函数可用带 extern 的原型
表示可调用签名。接口不重新发射函数定义，不把 C 名字追加模块后缀。
是否最终采用混合版本在 U0 核对缓存/调度契约后锁定；不承诺“加属性还永久
保留 v1”即可安全兼容。

缓存键纳入类型属性、C ABI、noreturn、优化管线身份和相关调用目标；I1 再
加入被内联函数体依赖。相关 IR/接口格式变更要更新版本，验证热缓存行为
与冷编相同。输出顺序不依赖哈希迭代顺序或运行时间。

## 9. C 构建集成

```toml
[project]
name = "cinterop"
version = "0.1.0"

[c]
sources = ["c/shim.c"]
objects = ["vendor/prebuilt.o"]
libs = ["m"]
```

沿用系统 cc 和现有显式 argv 进程接口，不通过 shell 拼接命令；yh 模块
对象、C 对象/预编译对象在前，系统库在后。路径相对所属 project.toml，
检查文件存在与对象目标匹配；`.c` 仅是 FFI 构建输入，yh 用户源码仍只用 `.yh`。

`yh build/run` 生效，`yh check` 校验配置和 yh 语义，不编译/链接 C。
单文件模式只支持其现有链接环境中的 C 符号，不扩充 C 源文件参数。
可达本地依赖的 [c] 输入参加最终构建，稳定收集，库列表保留消费依赖所需顺序。

U3 当前每次 `build/run` 都重新编译 [c].sources，因此编译器实际读取的头文件
变化会进入新对象；没有持久 C 源对象缓存。新生成的 C 对象内容、预编译对象
内容与库名参与链接缓存键，头文件和对象变化均有重新链接测试。若后续增加
C 对象缓存，再把 cc 身份、目标/SDK 与编译选项纳入该对象缓存键。

与 yh intrinsic 同名的 C API 声明首先明确拒绝，提示使用 C shim 改名。
不增加 link_name 字符串属性来扩大本轮语法。真正的外部 prelude 声明能否
合并，以签名、ABI、来源和运行时属性全部一致为准。

## 10. 分阶段实施与验收

| 阶段 | 交付 | 验证与退出条件 |
| --- | --- | --- |
| **U0** | 单组列表规则；修订 g4/设计文档；起草 ADR-0010；梳理语法与语义反例 | 完整 g4 校验；拒绝连续多组、错误位置、空列表和尾逗号；保留裸类型、pub let、普通原型禁令；确认无歧义 |
| **U1** | 属性框架、extern fn 引用/定义、数据布局/opaque、模块接口、窄范围固定参数 C ABI | libc abs；C 调 yh/结构体指针探针；nm 裸名；模块调用透传；未覆盖签名拒绝；make 与回归门 |
| **U2** | noreturn 的定义检查、调用控制流、新旧后端终止和缓存透传 | 正反例、分支/短路/嵌套实参；外部违约 trap；冷/热缓存一致；主门全绿 |
| **U3** | [c] 混编、依赖项目输入、固定参数回调、窄标量/浮点/栈参数目标验收；正确的 C 缓存失效 | cinterop 往返、回调、sizeof/offsetof、窄参数超 8 个、C 头/对象变更、失败构建与路径含空格；主门全绿 |
| **I1** | inline 属性与 NP5 共用的有限 SSA 内联 | IR/汇编证明至少一个调用展开；递归/变参/取址/导出降级；参数副作用一次；callee 修改使缓存失效；主门全绿 |

U1 使用固定三属性集合和简单位掩码，不引入通用注解注册器、属性参数、
插件钩子或动态优化调度。索引、声明解析及接口加载共用属性前缀处理逻辑，
属性状态由当前声明拥有，不能泄漏到下一条声明。

用户已要求本次开工。libc `printf` 变参改造被明确排除；U3 的 C 变参验证项
删除。本轮只验证固定参数 extern；既有 yh intrinsic `printf` 按回归语料验证。

U0–U3 与 I1 均已完成；实现和验收结果记在 docs/finish.md 及
docs/01-finished/yh-属性系统与C互操作实施完成-2026-10-02.md。Linux AArch64
原生运行仍需相应种子与环境，本机 Darwin 验收不替代该项。未来内存分配设计
不属于本轮实施范围。

U1 的 C 调 yh 探针使用 tests 中的 C fixture 和测试工具显式 cc 链接，
不等待 U3 项目混编完成，也不把手工链接误报为 yh build 已支持 [c]。
U3 的 Darwin 原生与 Linux 原生验收分别记录；没有原生 Linux 种子或运行环境
时，Linux 标为待验收，不使用“同一 arm64”或交叉组装替代运行证据。

每个行为阶段：先新增 `.yh` 正反例 → 实现 → `make` → 定向验证 →
`make test` → `make selfhost-native`。发生失败先定位并修复，不跳过主门。
滚种仅在两门全绿后另行进行，本次计划交付不修改种子。

实现期间 compiler/ 源码不采用旧种子不认识的新属性；固定点比较的是候选
相邻自编代的 .s/.s.i，不要求旧种子生成代与候选代产物相同。
新语法未进入 compiler/ 时，自举固定点不会证明属性行为，必须由新语料补足。

## 11. 测试与文档交付

| 目录 | 覆盖 |
| --- | --- |
| tests/yh/ | 单组列表、位置、extern 原型；连续多组/空组/尾逗号语法反例；保留旧语法反例 |
| tests/yh-run/pass、fail、run/ | 类别/组合/重复/未知属性（含 heap）/重名/ABI 错误、abs 调用、noreturn、inline；编译期拒绝与运行验证分开 |
| tests/modules/projects/externabs/（新增） | 单组属性接口导出/加载、顺序归一化、跨模块 extern/noreturn/inline、属性变化引发调用方 IR 失效 |
| tests/modules/projects/cinterop/（新增） | C 源/对象/库、双向调用、C 回调、共享数据布局、头文件与依赖项目输入 |
| tests/selfhost/ | 普通 yh 导入不被误判为 C；候选固定点和回退路径覆盖证据 |

ABI 负例覆盖小结构体、大结构体、24B HFA、数组、切片、错误回调及不透明值；
正向布局探针核对 `sizeof` 与 `offsetof`。属性测试覆盖组合和错配，验证交换
列表顺序不影响语义，以及两个相邻声明的属性不串用；`heap` 作为未知属性拒绝。
属性元数据变化、C 配置变化与被内联函数体变化均有缓存失效测试。
inline 用例须确认进入实际内联路径，noreturn 用例须确认 CFG/trap 行为，
不能只凭程序返回正确数值把静默忽略属性当作成功。

计划任务记入 docs/todo.md；阶段完成后将验证命令和实测结果记入
docs/finish.md 与 docs/01-finished/。已同步 docs/03-design/ 属性/FFI 设计、
g4、相关现役规范、根 README、测试说明与旧 FFI 草案中的过期描述。
临时 C 探针、编译器产物和诊断 dump 放 tmp/，fixture 源码放 tests/。
新增结构体/函数使用中文注释说明职责和契约，按文件规模拆分必要职责。

## 12. 后续独立扩展

不属于首版闭环：C 全局/TLS 语法、裸 C 变参、小/大聚合与 HFA 按值 ABI、
完整 C 函数值类型、跨模块内联、自动 C 头生成、动态/静态库产品输出、
显式内存分配声明、自动内存管理及新的属性参数。需要时再立方案，不在本轮提前留框架。

实施遵循已确定的单组多属性、删除 heap、extern 无体引用/有体定义、继续要求
pub 数据类型及固定参数函数优先的 FFI 边界。各阶段验收已完成；内存分配没有
待确认选项，也不属于本轮实施范围。
