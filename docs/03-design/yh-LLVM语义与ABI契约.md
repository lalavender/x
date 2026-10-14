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

## 其他边界与 ABI

整数计算位宽、除模/移位、转换、bool、内存副本/切片共享、求值顺序和未初始化规则
正在按 LL1 探针核对；后续更新本文件。未锁定条目禁止进入生产 LLVM lowering。
yh-llvm-v1 的显式副本/结果缓冲和目标 C ABI 规则将在本阶段补齐，实际双向互调归 LL7。
