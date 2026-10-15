# yh LLVM LL8a：内存运行时 helper（2026-10-15）

**状态：**第一片完成并验收；生产默认仍是旧 ARM64 路径，LLVM 模式需显式
`--backend llvm`。本记录覆盖 `memcpy`/`memset`/`strlen` 三个入口的实现、
发射形态、门禁与边界。

## 1. 目标与范围

LL5 的聚合复制/清零与 LL7 的调用 lowering 都需要字节内存入口；LL8a 先用
`.yh` 发射代码把这些入口的 LLVM IR 补齐，避免「运行时等 lowering、lowering
等运行时」的环。本片**不**实现指针/聚合 lowering，也不调用任何外部 LLVM 工具。

## 2. 实现

**`compiler/backend/llvm_runtime.yh`**（新）在 `llvm_emit_module` 末尾追加：

| 入口 | 签名 | 语义 |
| --- | --- | --- |
| `memcpy` | `ptr (ptr dst, ptr src, i64 n)` | 复制 n 字节并返回 dst；保持 C 的非重叠契约；按未知对齐逐字节 |
| `memset` | `ptr (ptr dst, i32 value, i64 n)` | 用 value 低 8 位填充并返回 dst |
| `strlen` | `i64 (ptr s)` | 返回首个 NUL 前的字节数，不含 NUL |

发射形态与理由：

- **`weak` 定义**：多模块各带一份不产生重复定义；用户同名强定义优先。
- **`@llvm.used`**：阻止 O2 的 GlobalDCE 丢弃未被引用的弱定义，保证 O0/O2
  产物都带入口。
- **`optnone noinline nobuiltin`**：阻止 loop-idiom 把逐字节循环改写为对自身
  `memcpy`/`memset` 的 libcall（自递归），代价是入口保持低优化，LL8b 迁移
  完整运行时后再评估。
- **同名让位**：模块符号表已有同名符号（声明或定义）时不发射该入口，避免 IR
  重名；LL5 若要显式引用，用模块自己的声明/定义接入。

## 3. 门禁与证据

**`tests/selfhost/llvm-runtime.py`**（新）：

- 对 O0/O2 文本：三个 `define weak` + `[3 x ptr]` 的 `llvm.used`；
- `opt -passes=verify` 通过，`opt -passes=default<O2>` 后弱定义仍为 3 个；
- `clang -c` 产对象后：`nm` 三个入口有定义、`nm -u` 不残留内存导入、
  `objdump --disassemble=<name>` 无自我调用；
- C 边界驱动链接真实对象并原生运行：复制/清零覆盖
  0/1/7/8/16/31/32/4096 字节（含返回指针、内容与越界保护、value 低 8 位），
  `strlen` 覆盖空串/1/7/8/15/16/32 与 UTF-8 三字节、4098 字节长串；
- 编译器经内嵌桥产 O0/O2 可执行文件：`nm` 有 weak 定义，运行退出 0。

**`tests/yh-run/run/llvm-runtime-memory.yh`**（新）：旧后端运行语料，锁定
同一尺寸/字符串矩阵的语义基线（清零无 yh prelude，由上面的 C 驱动覆盖）。

**`tests/selfhost/llvm-ir.py`**：define 计数改为只统计用户函数（helper 属于
运行时发射，不计入 `emitted`）。

## 4. 验收结果（WSL，`SEED=bin/yh-linux-arm64`、`YH_LINK=/nonexistent`）

| 门 | 结果 |
| --- | --- |
| `make` | 退出 0 |
| `make test` | 退出 0：语法 78/78 与 42/42、运行 **308/308** |
| `make selfhost-native` | 退出 0：固定点 cc3→cc4 **24 个产物一致**、自解析 **86 文件**、项目 **100/100** |
| `llvm-runtime.py`（新） | 退出 0 |
| `llvm-ir / llvm-lower / llvm-checked / llvm-front-output / llvm-module / llvm-module-cache` | 全部退出 0 |

## 5. 未关闭与后续

- yh prelude 目前只有 `memcpy`/`strlen`，`memset` 暂无源级调用；runtimebytes
  形态的自包含验收要等 LL5/LL8b 接入真实内存 lowering 后补。
- helper 每模块携带（weak）且刻意低优化（optnone）；LL8b 用 yh/IR 迁移完整
  运行时（allocator/printf 等）后重新评估优化、裁剪与对齐。
- LLVM 默认仍未切换，种子未滚动；LL5 的聚合复制/清零应直接复用本片入口。
