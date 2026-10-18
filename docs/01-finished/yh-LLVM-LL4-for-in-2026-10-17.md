# LLVM LL4 for-in 完成记录

日期：2026-10-17

## 交付内容

- LLVM lowering 支持 `for value in array_or_slice`、`for index, value in ...` 和
  左闭右开整数区间；计数从零开始，元素绑定与可选下标绑定在每次迭代前更新。
- 数组/切片来源或区间端点只在进入循环前求值一次。循环头使用计数 phi；`continue`
  与自然回边均将计数加一后回到循环头，`break` 仍退出最内层循环。
- 标量元素按元素类型加载；结构体等聚合元素复制到独立迭代绑定存储，修改绑定不会
  写回原数组。lowering 复用既有两趟循环发现/发射与嵌套 `CheckedLoop` 状态。
- 新增 `tests/yh-run/run/llvm-for-in.yh`，覆盖数组、切片、双绑定、嵌套、break、
  区间和结构体按值复制；新增 `tests/selfhost/llvm-for-in-continue.yh`，由
  `tests/selfhost/llvm-control.py` 在 LLVM O0/O2 下编译并原生运行。

## 验证

WSL Ubuntu/x86_64，使用 `SEED=bin/yh-linux-arm64`、
`YH_LINK=/nonexistent` 与仓库交叉 gcc 包装器：

- `make all`：通过，生成根目录 `yh`。
- `python3 tests/selfhost/llvm-control.py --compiler-path ./yh`：通过；循环和 for-in
  语料分别在 O0/O2 下由 `opt` 验证、汇编、链接并原生运行。
- `make test`：通过 319/319（运行 180/180、拒绝 131/131、仅编译 8/8）。
- `make selfhost-native`：通过；cc3→cc4 的 24 个固定点产物一致，93 个源文件自解析，
  运行语料 319/319、模块语料 18/18、项目验收 101/101。
- 种子 SHA-256 验证前后为
  `073282e9f1f773f162ccf9674a86f357e3bd6c9b74ccb65fe613968566916ccd`；未执行 `make seed`。
- 共享工作区包含先前在途改动，本次没有创建提交；提交步骤保留在实施方案待办中。

## 范围说明

旧 ARM64 后端在 for-in 中遇到 `continue` 时会直接跳回条件并略过计数递增，导致程序
无法结束。该既有行为不属于本次 LLVM lowering；通用 `make test` 用例使用等价条件分支，
LLVM 专项 `.yh` 探针单独锁住 for-in `continue` 的计数回边行为。

复核曾记录的「未初始化局部聚合缺少零写入」后，确认这不是后端缺陷：LL5 语义约定
未初始化聚合的未写内容保持未定义，不要求隐式清零（见
[LL5 结构体切片记录](yh-LLVM-LL5结构体切片-2026-10-15.md)）。本次空切片循环使用
显式初始化的零长度视图，因为测试需要有定义的长度与数据指针；未初始化读取不作为
语言行为断言，因此已从待办移除。
