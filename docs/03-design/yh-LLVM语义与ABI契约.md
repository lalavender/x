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

证据：tests/yh-run/run/llvm-float-nan-comparisons.yh，覆盖常量折叠、typed CT、
动态 f32/f64、左右 NaN、正常有序比较。LLVM 路径验收仍归 LL6。

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
fptosi/fptoui。依据：[LLVM 饱和转换](https://llvm.org/docs/LangRef.html#saturating-floating-point-to-integer-conversions)。
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
irverify 的一位 bool、重复调用和多余调用记录拒绝层保持严格。

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
窄参数/返回扩展、聚合 coercion、C _Bool、变参和函数指针分别降低；等价 C 声明由
clang 21.1.8 生成 IR/对象作开发核对，必须以 yh→C、C→yh 和回调实际运行证明兼容。
不能把 yh 的显式副本指针签名直接标成 extern 或混用旧 AAPCS64 分类器。
本节锁定政策与验收方法，实际完整调用实现和双向互调仍属于 LL7。

## 其他边界

整数计算位宽、除模/移位、转换、bool、内存副本/切片共享、求值顺序和未初始化规则
正在按 LL1 探针核对；后续更新本文件。未锁定条目禁止进入生产 LLVM lowering。
上述调用政策已锁定，实际双向互调归 LL7。
