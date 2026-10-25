# yh LLVM 迁移语义与 ABI 契约

2026-10-14。按 LL1 探针和现有语言规则逐项锁定；尚未验证的 LLVM 实现不能冒充已兼容。
语法没有变化，docs/yh.g4 的声明/表达式文法保持原样；这里只修复和明确既有语义。

## 浮点关系（LLVM-SEM-01）

f32/f64 比较遵守 IEEE 的有序关系：任一操作数为 NaN，`==` 为假、`!=` 为真，
`< <= > >=` 均为假。正负零相等；有限值和无穷保持数值次序。NaN 的具体 payload
不作为可观察结果验收，测试只检查比较与类别，不强制硬件产生固定 NaN 位型。

ARM64 FCMP 无序时 NZCV=0011，整数 lt/le 条件码会将无序误判为小于/小于等于，
修复采用 mi/ls。常量折叠与 typed CT 对 `< <=` 增加有序守卫，使旧种子构建的
第一代宿主即正确，不依赖先滚种子修复宿主自身的比较指令。

LLVM lowering 对 `== != < <= > >=` 分别使用 `oeq une olt ole ogt oge`，不得增加
nnan/fast-math。依据：[LLVM fcmp](https://llvm.org/docs/LangRef.html#fcmp-instruction)、
[Arm 浮点条件码](https://developer.arm.com/community/arm-community-blogs/b/architectures-and-processors-blog/posts/condition-codes-4-floating-point-comparisons-using-vfp)。

证据：`tests/yh-run/run/llvm-float-nan-comparisons.yh` 与
`llvm-float-lowering.yh` 覆盖常量折叠、typed CT、动态 f32/f64、左右 NaN 和正常
有序比较。LL6 已用 LLVM O0/O2 门验收这些谓词。

## 浮点转整数（LLVM-SEM-02）

按目标符号性先向零转换到 i64/u64，在该 64 位值域饱和，然后按目标源类型保留
低 N 位并恢复符号性。NaN 得零；有符号正/负越界得到 i64 最大/最小值；无符号
负值得零、正越界得到 u64 最大值。因此 u8(300.0) 得 44，i8(130.0) 得 -126，
u64(2^63) 保留高位。bool 遵循无符号字节转换，2.0 转 bool 得 2，条件另外取真。

原常量折叠和 typed CT 一律先转 i64，造成 u64 高位饱和及负数错误回绕；现共用
sem_fold_fp_to_int。动态路径原先漏掉窄整数规范化，现复用整数转换的大小/符号扩展。
规则由现有动态 64 位转换和目标宽度定义导出，并以三条执行路径校验；不新增运行期错误。

LLVM 必须使用 llvm.fptosi.sat.i64.f32/f64 或 llvm.fptoui.sat.i64.f32/f64，
再 trunc 到目标源宽度；不能直接用窄目标饱和，也不能使用越界产生 poison 的普通
fptosi/fptoui。LL6 已按此路径实现并以 O0/O2 检查 NaN、无穷、负值、窄型回绕和
边界值。依据：[LLVM 饱和转换](https://llvm.org/docs/LangRef.html#saturating-floating-point-to-integer-conversions)。
证据：llvm-float-integer-casts.yh 的高位、负数、窄化、NaN、无穷、f32 与 bool 探针。
长十进制字面量目前由前端逐位 f64 累积解析；本探针用精确整数转浮点构造边界，
LLVM 迁移保留前端给定的位型，不顺带改写十进制解析算法。

## bool 字节值与条件（LLVM-SEM-03）

现行源级 bool 为一字节无符号标量。显式整数转换保留低 8 位：2 转 bool 得 2，
-2 得 254；转回整数保留该字节。true/false 是 1/0；比较按实际值比较，因此
`2.to_type(bool) == true` 为假。if/for 条件按非零为真；&&/||/! 结果才规范为 0/1。
数组/字段与按值传递保存原字节，不因值被用于条件而回写为规范真值。

迁移前项目 SSA 的一位 bool 会把 2 的入参/返回/phi/条件变成 0，违反单文件和编译期
路径已有字节语义。IR bool 因此改为 8 位，参数/返回规范化只截到低字节；条件
消费者显式比较零。逻辑非恢复源级 int 结果类型，bool/整数 CAST 保留位型转换。
序列化版本升为 6、函数 IR 缓存键升为 11，旧一位缓存不兼容。

LLVM 内部使用 i8 保存源 bool，比较及分支谓词临时使用 i1，再按需要 zext 回 i8。
不能用 trunc i8 to i1 表达取真；应使用 icmp ne i8 value, 0。C 的 _Bool 边界
按目标 C ABI 单独处理，不把 yh 字节位型误当成 LLVM i1 的值域保证。

证据：tests/yh-run/run/llvm-bool-memory.yh 与 tests/selfhost/llvm-semantics.py，
对照单文件和实际 SSA 发射的入参、返回、常量、phi、条件、逻辑、转换与字节数组。

扩大 bool CAST 覆盖时还发现两个既有 CFG 缺口：调用记录按线性指令数组追加，而
verifier 原来按块编号枚举调用；合流块可早分配，导致合法的调用被拒绝。校验改按
指令数组，仍拒绝重复和无引用的调用记录。另一个缺口是 if 内局部绑定在另一臂
没有值，不能合并为含 -1 输入的 phi；这些绑定在合流后保持不可见，外层变量仍
按正常双前驱值合流。证据为 llvm-call-block-order.yh 的副作用序列与块内局部探针，
`compiler/ir/zz_tests_verify.yh` 覆盖的一位 bool、重复调用和多余调用记录
拒绝层保持严格（原 irverify 夹具已迁入，见
[YT4-P6](../01-finished/yh-YT4-P6-编译器fixture迁移-2026-10-25.md)）。

## yh-llvm-v1 调用政策

新 LLVM 对象只与同一 ABI 版本的 yh 模块链接，不要求与旧 ARM64 机器 ABI 混链。
签名使用逻辑符号名，由目标机器决定平台符号前缀；所有模块重新生成接口和对象。

| 源级值 | 内部 LLVM 签名表示 | 可观察规则 |
| --- | --- | --- |
| bool / 有符号或无符号整数 | i8 / 对应位宽 iN | bool 保留字节；整数位型按源宽度，符号性参与运算/扩展 |
| f32 / f64 | float / double | 不加 fast-math，转换与舍入按已锁定规则 |
| 指针 / 函数指针 | opaque ptr | 源元素类型、步长和调用 ABI 元信息继续保留 |
| struct / union / 数组 / 切片参数 | 指向调用方独立副本的 ptr | 实参求值时复制；数组/聚合值独立，切片只复制描述符，元素共享 |
| struct / union / 数组 / 切片返回 | 首个隐藏结果缓冲 ptr，LLVM 返回 void | 由调用方提供完整布局缓冲，返回后得到源级值副本 |

参数按源码从左到右求值，按值副本在对应实参求值时固定，不能拖到所有实参求值后
统一复制。缓冲使用源布局的大小/对齐，不将普通结果缓冲自动标为 C sret/noalias，
不添加未经证明的 nonnull/noundef/readonly/inbounds。private/pub 可见性规则保持原样。
普通指针/切片的既有生命周期与越界边界仍生效，不因隐藏缓冲另作所有权承诺。

C ABI 使用独立目标分类器。首期 Linux/x86_64 System V 按 INTEGER/SSE/MEMORY 类、
窄参数/返回扩展、聚合 coercion、C `_Bool`、固定参数和函数指针分别降低；等价 C
声明由 clang 21.1.8 生成 IR/对象作开发核对，并以 yh→C、C→yh 和 callback 实际运行
证明兼容。用户裸 C 变参仍由源语言规则拒绝，不能把 yh 的显式副本指针签名直接标成
extern，也不能混用旧 AAPCS64 分类器。

**实现状态（2026-10-17，LL7 完成）：**YH 内部调用使用 `yh-llvm-v1`：结构体、定长数组、切片参数在各实参
求值时复制到调用方缓冲，聚合返回使用首个隐藏结果缓冲；切片只复制 16 字节描述符，元素仍共享。版本号
进入模块符号、函数/调用 IR 与缓存序列化身份，YH 内部符号带 `$yhllvmv1` 后缀。跨模块结构体、数组、切片
参数和返回的 LLVM O0/O2 链接运行已通过。固定参数 C ABI 标量签名支持定宽整数、`_Bool`、指针、f32/f64；
i8/i16 与 u8/u16 在函数返回、参数和调用点使用 `signext`/`zeroext`，C `_Bool` 使用 `i1 zeroext` 并在边界按
非零值转换。Linux/x86_64 C 结构体/联合按两个八字节分类 INTEGER/SSE，超过 16 字节使用 MEMORY；参数/返回 coercion、`sret` 和 `byval` 由 CPair、CMixed、CWide 三组 oracle 与双向运行验证。函数指针类型保留 ABI、返回/参数类型和变参种类，跨模块 YH callback 与 C scalar/CPair aggregate callback 的传递、返回和间接调用均在 O0/O2 运行通过。YH 类型化变参 `vararg=2` 的尾项按源码顺序打包为末尾切片参数；用户裸 C 变参仍按 FFI 决策拒绝。`@[noreturn]` 随符号和模块接口缓存传播，调用点在该调用返回后执行 `llvm.trap` 并进入 `unreachable`；接口属性移除/恢复会重编调用方。`tests/selfhost/llvm-abi.py` 覆盖 clang oracle、LLVM verifier、优化与双向运行；不支持的源级签名和 ABI 约定明确拒绝，不回退旧后端。Linux/AArch64 的 AAPCS64 标量、HFA2/HFA3、16 字节直接聚合、24 字节 sret/间接参数与双向回调已于 2026-10-20 接入，见 `tests/selfhost/llvm-linux-arm64.py`。

## 定宽整数、移位与除模（LLVM-SEM-04/05）

运行期先由前端选择公共结果类型，再按符号性扩展到 64 位计算，结果按源宽度截断并
恢复符号性。随后扩大转换必须看到已截断的结果：i32 最大值加 1 再转 i64 为
-2147483648；i8(-128) 取负再转 i64 仍为 -128。常量一元运算保持同样的结果类型，
bool 升为 int，其余整数保持原宽度；括号不继承派生常量的原符号绑定。

移位量统一取低 6 位（&63），不是 &31；有符号右移为算术右移，无符号为逻辑右移。
i32(1)<<32 的 64 位中间量在结果位置截断为 0；量 64 等效量 0。
运行期除法向零，余数与被除数同号；除零商为 0、余数为被除数。64 位有符号
最小值/-1 得原最小值、余数 0；窄整数先在 64 位计算再按结果宽度截断。

编译期整数算术继续检查源宽度溢出、除零和非法移位；不因动态环绕规则放宽现有
拒绝层。证据包括 llvm-integer-boundaries.yh、llvm-unary-types.yh，以及现有
73–79 编译期失败语料、61-comptime-u64-fold.yh 与 32-int-narrow.yh。

LLVM 整数操作先扩到 i64，再截回源宽度；移位先掩码。除零/min64/-1 使用安全
操作数或控制流先排除，再执行除模，不能执行 poison 操作后再 select。不添加
nsw/nuw/exact。逻辑非用与操作数同类型的零比较，再恢复源结果宽度。
编译器自身的 32 位规范化掩码显式使用 i64 的 1，避免依赖旧发射遗漏截断。

## f32 舍入、零与无穷（LLVM-SEM-07）

初期浮点契约采用默认最近偶数舍入；每个 f32 运算各自舍入，不能把整条表达式
扩成 f64 后统一窄化。正负零数值相等，但负号和除法保留零的符号；1/+0 和
1/-0 分别产生正负无穷，f32 非正规数保留。NaN 只检查类别和比较，不锁定 payload。

编译期 f32 值以规范化后的 f64 位型保存，运行期引用必须窄化为 s0，不能直接使用
double 的低 32 位。llvm-float-boundaries.yh 对照常量、typed CT 和动态结果，覆盖
两种舍入中点、逐步加法、正负零、无穷和最小 f32 非正规数。LLVM 不加 fast-math，
不合并舍入点，不使用 nnan/nsz 等未经证明的值域属性。

LL6 的浮点 lowering 按此契约发射 `fadd/fsub/fmul/fdiv` 与 `fcmp`，不附加 fast-math
标志；f32 常量从保存的 f64 IEEE 位型重解释后执行 `fptrunc`，保证每个 f32 节点
单独舍入。参数与局部复制采用位保持路径，避免用加零复制时丢失负零。覆盖见
`tests/selfhost/llvm-float.py` 和 `tests/yh-run/run/llvm-float-lowering.yh`。

## 内存、效果与默认初始化（LLVM-SEM-06）

数组/struct/union 按值赋值和参数具有独立对象存储。实参从左到右求值，每个值参数
在本次实参求值时固定副本，不能只保存源地址、等后续实参改变源后再复制。
该规则同样适用于间接函数调用。数组传给指针形参则保留原地址，指针访问共享元素。
切片只复制长度/数据指针描述符，元素仍共享；后续修改原描述符不影响已求值副本。
短路跳过未选择的操作数，不能提前执行含副作用的函数。

无显式初始化的 let 全局/局部声明已有零初始化；聚合按完整大小清零，包括填充，
空切片描述符为零。不读取原始分配内存中的未初始化字节，也不把这类垃圾值写入期望。
证据为 llvm-memory-effects.yh 的数组/结构体复制、切片共享/描述符隔离、指针退化、
间接调用、副作用次序、标量/数组/结构体/联合体与填充零初始化。

LLVM 先提供明确的存储、复制/清零和求值次序；指针仅用可证明对齐，未知对齐为 1。
不增加 inbounds/noalias/nonnull/noundef 等未证明的约束。完整内存 lowering 归 LL5/LL7。

### LL5 静态数据与重叠复制

全局对象、字符串和 CT backing 以独立字节、受检布局与静态重定位记录交给 LLVM；
重定位 addend 是目标对象内的字节偏移，不是编译器宿主地址。切片值由长度和 backing
指针描述，赋值只复制描述符，元素继续共享；CT 返回切片按既有逃逸规则复制可见元素，
静态物化后 backing 不依赖 CT 值池。导入的 `pub const` 聚合在消费模块形成独立副本，
私有对象不进入导出接口。数组/聚合赋值允许同址和部分重叠，LLVM 采用 `memmove`；
显式运行时 `memcpy` 仍要求源/目标不重叠。详细实现与边界见
[LLVM 后端替换设计 §5.2](yh-LLVM后端替换设计.md)及 LL5 完成记录。

## LL1 探针矩阵与后续边界

| 类别 | 已观察规则 | 稳定证据 | LLVM 实现归属 |
| --- | --- | --- | --- |
| 移位 | 扩到 64 位，量 &63，截回源宽度 | llvm-integer-boundaries，23-shifts | LL3 |
| 除模 | 动态除零/min64/-1 有定义结果；CT 拒绝错误 | llvm-integer-boundaries，61，73–79 失败语料 | LL3 |
| 转换 | 定宽截断/扩展；浮点 64 位饱和后窄化 | llvm-float-integer-casts，32-int-narrow，llvm-unary-types | LL3/LL6 |
| bool | 无符号字节，条件非零，逻辑规范 0/1 | llvm-bool-memory | LL3 |
| 浮点 | NaN 有序关系，f32 各节点舍入，零符号/无穷/非正规数 | llvm-float-nan-comparisons，llvm-float-boundaries | LL6 |
| 内存 | 聚合独立复制，切片只复制描述符 | llvm-memory-effects | LL5/LL7 |
| 效果 | 左到右、每个实参固定值、短路跳过 | llvm-call-block-order，llvm-memory-effects | LL4/LL7 |
| 默认初始化 | 声明对象完整清零，不读取未初始化分配内存 | llvm-memory-effects | LL5/LL8 |

LL1 阶段交付时，单文件和项目探针各 8/8；当时的项目 SSA 计数是 bool 8、CFG 2、
整数 11、一元 1、内存纯标量 pair 1，浮点与聚合主体尚走旧路径。后续切片已继续推进：
LL5 完成内存/聚合与模块数据，LL6 完成浮点标量 O0/O2 lowering。当前阶段覆盖和剩余
边界以 [LLVM LL6 完成记录](../01-finished/yh-LLVM-LL6浮点标量-2026-10-17.md)及实施方案为准。
