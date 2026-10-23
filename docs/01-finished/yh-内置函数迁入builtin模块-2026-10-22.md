# 内置函数迁入 builtin 模块

日期：2026-10-22。状态：**已实施**（`make test` 与 `make selfhost-native` 全绿）。

## 目标

把「哪些名字不导入任何模块就可见」这一层从 `gen` 中拆出来，避免语义/符号表
模块同时维护一张不断增长的内置函数表；不改变任何语言可见行为。

## 边界

- 新模块 `compiler/builtin/`（`module builtin`，只 `import gen`）持有
  `sem_register_prelude()` 与 Linux `linux_syscall6` 的登记辅助。
- `gen/symbols.yh` 只保留符号表原语 `gen.prelude_add`（改为 `pub`），不再认识
  具体内置函数名；`gen` 不 import `builtin`，无环。
- 运行时函数体不在本模块：`printf`/`malloc`/`free`/`memcpy`/`strlen` 仍由
  `backend/llvm_runtime.yh` 按需发射，Darwin 入口辅助在
  `backend/llvm_apple_runtime.yh`；本次不动后端。
- 入口调用顺序不变：`gen.ty_register_builtins()` → `gen.scope_push()` →
  `builtin.sem_register_prelude()`（`cmd/driver.yh`、`cmd/llvm_emit.yh`、
  `cmd/module_worker.yh` 三处）。
- 测试 fixture `tests/modules/projects/llvmlower/fixture.yh` 同步补
  `import core.builtin`；`tests/modules/build-check.py` 的模块拷贝清单加入
  `builtin`。

## 验收

- 新增 `tests/yh-run/run/205-builtin-prelude-registration.yh`：
  `printf`/`malloc`/`memcpy`/`strlen`/`free` 经默认 prelude 编译运行。
- `make test`：run 210/211（跳过 1）、fail 133/133、pass 8/8。
- `make selfhost-native`：模块固定点 30 个产物一致，cc4 自解析 102 个源文件，
  运行语料 351/352，模块语料 19/19，项目验收 115/115。
