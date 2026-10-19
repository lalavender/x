# macOS/ARM64 LLVM F2-5：HFA 与聚合 callback

**日期：**2026-10-19  
**状态：**HFA、聚合 callback 与聚合值路径已通过；prelude `printf` 的 Darwin 变参与 `va_list` 留待 F2-6 联测。

Apple AAPCS64 的 HFA 参数和返回值现在按浮点寄存器类型传递。新增递归分类与字段布局映射，覆盖 `f64` 双元素 HFA、嵌套 `f32` 三元素 HFA，以及七个浮点实参耗尽 SIMD 参数寄存器后 HFA 整体入栈。LLVM 21.1.8 Clang 生成的物理签名作 oracle，Mach-O O0/O2 程序执行验证 C 和 YH 的双向值传递及返回。

聚合函数指针测试新增 HFA 函数指针参数、从 C 返回函数指针并由 YH 间接调用，以及 C 调 YH callback、callback 再调用 C 的嵌套路径。测试比较 Clang 的 LLVM 签名，并检查真实浮点值和字段顺序。用户裸 C 变参继续由现有语义规则拒绝。

HFA 实现期间，测试发现并修复三个发射问题：参数 `extractvalue` 缺指令名、值组装/拆解缺 `insertvalue`/`extractvalue` 前缀、HFA 调用值未进入直接寄存器实参分支。修正均由 O0/O2 C↔YH 探针覆盖。

验证结果：

- `make test-llvm-darwin`：通过，包含 SDK/host/bridge/object、标量与聚合 ABI、HFA、callback、生产链接、运行与失败保留。
- `make test`：通过，语法正例 78/78、反例 42/42；运行语料 346/347，1 个 Linux 专属用例按平台跳过；fail 132/132，pass 8/8。
- `make selfhost-native`：固定点 122 个产物、自解析 103 个源、CLI、全量语料、scratch-isolation、并发扫描和 lex-stats 通过；最终在既有 `tests/selfhost/runtime-memory.py` 因自编译器导入 C runtime `strlen` 失败。
- 未执行 `make seed`，未滚动任何入库种子。

下一步：F2-6 为 Darwin 实现 allocator、格式化输出和 OS 桥，并与 prelude `printf` 的 Darwin 变参/`va_list` 联测；随后处理缓存依赖身份、CI 与原生固定点。
