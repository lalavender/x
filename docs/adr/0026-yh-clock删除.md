# ADR-0026：删除 `support/clock.*`——testkit 超时改用 `libs/time`

日期：2026-11-10。状态：**已批准，实施中**（用户决策：testkit 改用 time）。

关联：[ADR-0024](0024-yh-support再收缩.md)、[ADR-0025](0025-yh-console-argv迁cmd.md)
（support 收缩系列）。

## 背景

`support/clock.{darwin,linux.arm64,linux.x64,windows.x64}.yh` 提供单调纳秒时钟
`clock_ns()`，两类消费者：

1. **lower 四段计时**（`LowerTiming` / `CheckedLowerStats` 的 prep/decl/build/verify
   与 lookup/cache/fn/capture）：原本汇总到 `--stats`，但 `--stats` 已于 2026-11-10
   删除，`llvm_pipeline` 的唯一读点已是空块——**纯死计时**。
2. **testkit 逐例超时**（`yh test --timeout`）：用 `clock_ns` 算 elapsed 并强杀超时
   用例——**活功能**，测试门禁自身依赖。

## 决定

- 删除 4 个 `clock.*.yh`、`support.clock_ns` 包装、`QueryPerformanceCounter/
  QueryPerformanceFrequency` 两个 Win32 extern（仅 clock.windows 使用）。
- **testkit 超时改用 `libs/time.monotonic_ns()`**（`import time`；返回 i64，
  单调非负，`.to_type(u64)` 后沿用原 u64 计时逻辑），保留 `--timeout` 行为。
- **lower 死计时清理**：删 `LowerTiming` 结构、`lower_elapsed` helper、
  `checked_lower_build_functions` 的 `timing` 参数与全部 `clock_ns` 调用、
  `lower_module_impl` 的 t0–t4 分段计时；`CheckedLowerStats` 删 8 个 `*_ns` 字段，
  保留 `hits/misses/lowered` 计数与 `lower_stats` 参数 plumbing（签名不变）。

## 备选与被否决的方案

| 方案 | 结论 | 理由 |
| --- | --- | --- |
| 连 testkit 超时一起删 | 否决 | 去掉超时保护，用例可能挂死，测试门禁退化 |
| 保留 clock | 否决 | 用户决定删除；lower 计时已死，testkit 有 time 可用 |
| lower 计时改 time 保留 | 否决 | --stats 已删，计时无读点，保留即死代码 |

## 后果

- `support` 不再有任何平台变体文件（argv/console 已迁 cmd，clock 删除），
  成为纯平台无关模块。
- `testkit` 新增对 `libs/time` 的依赖（标准库，编译器项目本就依赖 libs）。
- `lower` 不再计时；`CheckedLowerStats` 只剩函数缓存计数。
- 用户程序产物不变；`yh test --timeout` 行为保持。