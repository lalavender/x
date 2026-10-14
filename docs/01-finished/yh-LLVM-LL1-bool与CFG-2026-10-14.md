# LLVM LL1：bool 字节与 CFG 回归

源 bool 已有一字节规则：显式转换 2、-2、255 分别保留 2、254、255；条件按非零
取真，逻辑运算才返回规范 0/1。原项目 SSA 的一位值会把 2 变成 0，违反单文件语义。

IR bool 改为 8 位，ARM64 规范化使用 uxtb；条件显式比较零，bool/整数 CAST 开放，
逻辑非恢复源级 int。缓存格式版本 6、函数键 11，旧缓存不能混用。

覆盖扩大后，编译器自编暴露两处既有控制流缺口。调用表按指令数组追加，verifier
却按块编号检查；先分配的合流块可后写入指令，因而误拒合法 CALL。校验移到指令数组，
仍严格拒绝重复索引和多余调用记录。另一个缺口是块内局部在另一臂没有绑定值；这类
绑定在合流后不可见，不生成含 -1 输入的 phi，外层变量仍正常合流。

新增 llvm-bool-memory.yh、llvm-call-block-order.yh。前者覆盖转换、入参、返回、常量、
phi、条件、逻辑和字节数组；后者以副作用历史校验调用顺序及局部/外层变量合流。
llvm-semantics.py 将同一源构造成独立项目、检查输出和实际 SSA 发射计数。

Windows 宿主在 WSL Ubuntu x86_64 执行，crossbin/gcc 指向 aarch64-linux-gnu-gcc，
SEED=bin/yh-linux-arm64、YH_LINK=/nonexistent，旧编译器经 qemu 运行。

- 第四代候选项目门：3 个探针通过，bool 实际发射 8 个函数、CFG 2 个，NaN 尚走旧发射。
- make test selfhost-native 串行退出 0；两层语法各 78/42，运行 302/302，固定点 24 个
  产物一致，自解析 71 文件，模块 18/18、项目 95/95，其他专项门全部通过。
- 一次此前复跑为 301/302，但脚本仅打印总数并删除候选，未留下失败明细。补齐失败
  输出后，保留候选复跑与串行完整门均通过；不猜测未复现失败的原因。

日志：tmp/llvm-migration/ll1-bool-candidate-debug.log、ll1-bool-candidate-semantics.log、
ll1-bool-acceptance.log。种子保持原哈希，LLVM 前端/对象接入仍属后续阶段。
