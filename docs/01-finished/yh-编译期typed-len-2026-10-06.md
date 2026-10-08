# yh 编译期 typed `len`

- typed IR 捕获 `len` 的类型化节点和参数表达式，求值时验证数组/切片描述并读取当前调用帧中的长度；数组使用声明长度，切片视图和空切片使用当前描述长度。
- 普通函数的语义折叠和运行期发码路径沿用既有 `sem_len`，仅编译期 typed IR 新增执行能力。
- 新增 `tests/yh-run/run/87-comptime-len.yh`，期望 322，覆盖整型数组、结构体数组、切片视图和空切片；`comptimelocal` 跨源文件断言值为 320。
- 实现接缝位于 `compiler/parse/parse_expr.yh`，执行位于 `compiler/comptime/ct_ir.yh`。
- 验证：`make test` 语法 71/71、44/44，运行 183/183；`make selfhost-native` 固定点 14/14、自解析 64 个源文件、模块 17/17、项目 82/82 及其余探针通过。`make seed` 后冷编 `make` 成功；种子 SHA-256：`d9675dcded01a675eba65e4c08e274523cbb2f258c076364cf5608332f988501`。
