# sys 标准库：系统调用封装规划

日期：2026-10-03。状态：**仅交付规划，尚无 `.yh` 实现**。

源码落点为 `libs/sys/`，每个源文件声明 `module sys;`，沿用 `libs/project.toml`
的 `source = "."` 和目录模块发现规则，不建立第二份项目清单。

首期目标是 Linux/arm64：通过编译器已有 `linux_syscall6` 内建接口直接进入内核，
提供文件/目录、内存映射、时间和进程原语。正常结果或 `-errno` 由调用返回值
直接携带，不依赖 libc、全局 errno、shell 或外部命令；sys 不做隐式分配和重试。

- 完整 API、错误和平台契约：[系统调用封装设计](../../docs/03-design/yh-sys系统调用封装设计.md)。
- 分阶段文件、测试和接线：[实施方案](../../docs/02-plan/yh-sys系统调用封装实施方案.md)。
- 未完成任务：[docs/todo.md](../../docs/todo.md)。

实施顺序：SYS0 基线与 ABI → SYS1 原始入口/类型/错误 → SYS2 文件/目录 →
SYS3 内存/时间 → SYS4 进程 → SYS5 消费者迁移 → SYS6 独立产物与自举。
SYS7 后续增加 macOS/arm64 的系统 OS 接口适配，并披露 dyld/libSystem 依赖。

应用未来可用 `import sys;`；标准库当前仍通过 `YH_STDLIB` 加载。编译器、
自有工具链应采用显式项目依赖，避免构建时被环境变量或本地同名模块改变绑定。

sys 是内核接口层。`os/io/time` 负责原有便利函数和返回值转换，`memory` 负责
分配器，`_start` 和静态 ELF 由工具链任务负责。sys 规划交付不代表这些任务已完成。
