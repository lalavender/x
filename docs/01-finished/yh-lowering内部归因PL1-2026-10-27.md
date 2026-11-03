# yh lowering 内部归因（PL1/PL2）

日期：2026-10-27。状态：**已完成**。是
[PF2 归因报告](yh-编译器性能归因与失效矩阵PF2-2026-10-26.md) 的下一层：
PF2 把 lowering 定为 worker CPU 的 66%，本报告把 lowering 再拆到函数级，
并顺带定位 PL2「单模块函数数超线性」的来源。

## 1. 结论

**批次身份**：`tmp/perf/20261027-000451`（20 轮 + 3 轮预热，load1 中位 5.85 / 峰值 8.46），
语料 `compiler@dc8b8390…`、编译器 `a90e6f49…`（含本轮 PL1 打点）。
PL2 的数据来自 `tmp/perf/scaling-20261027-002129`（函数数轴 1/2/4/8，各 2 轮 + 1 轮预热）。

**八段分解（累计中位，ms）**：前四段互斥覆盖整个 `time_lower_ns`，后四段覆盖 `build` 内部。

| 场景 | lowering | prep | decl | build | verify | 其中 lookup | 其中 cache 合并 | 其中真 lowering | 其中 capture |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 冷编 | 16420.9 | 196.1 | 181.2 | 12946.8 | 3089.4 | 21.7 | 650.4 | 12270.2 | 0.0 |
| 全量重编（写缓存） | 38618.4 | 236.9 | 199.3 | 35414.1 | 2767.6 | 23.4 | 594.3 | 11255.4 | **23591.2** |
| 单函数改动（读缓存） | 1148.7 | 9.5 | 13.6 | 1001.3 | 124.8 | 1.2 | **998.0** | 0.5 | 1.1 |

**结论一：冷编的 lowering 里，真 lowering 占 74.7%（12270/16421），模块校验占 18.8%
（3089/16421），缓存查表 4.0%，符号查找只有 0.13%。** 也就是说，
「lowering 慢」基本就是「逐函数构造 IR 慢」+「整模块 verify 慢」，不是查找问题。

**结论二：一旦写函数缓存，capture（IR 序列化）成为最大单项**：全量重编里
capture **23591 ms**，占该场景 worker 累计（46671 ms）的 **50.5%**、占 build 的 66.6%；
此时真 lowering 只剩 11255 ms。这与 2026-10-25 首次归因的「capture 占 56%」一致，
但现在是可复现的分段数据，而不是靠关开关得到的差值。

**结论三：增量构建的 lowering 几乎全是「缓存合并」**：单函数改动时 lowering 1148.7 ms，
其中 cache 合并 **998.0 ms（86.9%）**、真 lowering 只有 0.5 ms。204 个缓存函数平均
4.9 ms/函数，这就是单函数改动 3.9 s 里除了整模块 LLVM 发射之外的另一半成本。

**PL2（单模块函数数超线性）的答案**：符号查找不是原因（0.13%），
增长来自**模块校验**与**真 lowering 的每函数成本**：

| 函数数 | verify ms | verify/函数 | 真 lowering ms | 每函数 ms | lower 合计 ms | 每函数 ms |
| --- | --- | --- | --- | --- | --- | --- |
| 64 | 3.5 | 0.055 | 17.4 | 0.272 | 28.7 | 0.448 |
| 128 | 10.9 | 0.085 | 50.3 | 0.393 | 102.4 | 0.800 |
| 256 | 33.5 | 0.131 | 93.4 | 0.365 | 199.8 | 0.780 |
| 512 | 110.5 | **0.216** | 275.6 | **0.538** | 658.2 | **1.286** |

- 单模块 8× 函数时，**verify 的每函数成本涨 3.9×**（0.055 → 0.216 ms），
  真 lowering 每函数涨 2.0×，合起来使 lowering 每函数成本涨 2.9×。
- 因此「把函数堆进一个模块」不只是并行度问题，模块级校验与 IR 构造都会随模块增大变贵。

## 2. 优化顺序（按本报告的量化结果）

| 优先级 | 目标 | 现状成本 | 备注 |
| --- | --- | --- | --- |
| 1 | **capture 序列化**（写缓存路径） | 全量重编 23.6 s（worker 累计的 50.5%） | 已由 [PL1c](yh-capture序列化归因PL1c-2026-10-27.md) 拆开：序列化写缓冲 65.5%、迷你模块 30.4%、闭包标记 1.9%；19.3 ms/函数、2.05 MB/s |
| 2 | **模块 verify** | 冷编 3.1 s（lowering 的 18.8%） | 发布构建可考虑默认关闭或改成增量校验；需要先确认 `--stats`/调试构建仍全量校验 |
| 3 | **缓存合并** | 增量每次 ~1.0 s（204 函数，4.9 ms/函数） | 恢复路径要按函数反序列化 + 合并迷你模块；可与 capture 共享表示 |
| 4 | 真 lowering | 冷编 12.3 s（lowering 的 74.7%） | 需要再拆表达式/类型/聚合，本次未做 |

## 3. 本轮改动

- `compiler/lower/{clock.darwin,clock.linux.arm64,clock.linux.x64}.yh`：lowering 自用的
  单调时钟（lower 不能反向依赖 build，故保留一份十几行的 syscall 包装）。
- `CheckedLowerStats` 增加 8 个 `u64` 字段；`lower_module_impl` 在
  prepare → declare → build（内含 lookup/cache/fn/capture）→ verify 各边界打点，
  时钟失败或逆序时按 0 计（`lower_elapsed`）。
- `build/stats_print.yh`（新）：`--stats` 单行拼装从 `module_build.yh` 整体抽出，
  8 个新字段加在这里；`build_scheduler` 的 worker 重置与 `llvm_pipeline` 的累积同步补齐。
- **架构预算**：8 个计时值放 `GenState`（`c_stats_lower_*_ns`）而不是模块级 `let`，
  这样 `max_globals` 保持 193；`module_build.yh` 因抽出 `mb_print_stats` 从 2296 行
  降到 2181 行；`max_build_lines` 由 10982 上调到 11034（理由写在
  `tools/arch-check.py` 的 BUDGETS 注释与 finish.md：PL1 打点的净增行）。
- `tools/perf-baseline.py` 解析并输出「lowering 细分（PL1）」表；`perf-scaling.py`
  增加「其中 verify / 其中真 lowering」两列。
- `tests/selfhost/llvm-function-cache.py`：断言 8 个字段存在，且
  `prep+decl+build+verify ≤ time_lower_ns`、`lookup+cache+fn+capture ≤ time_lower_build_ns`。

## 4. 复跑

```bash
just
python3 tools/perf-baseline.py --iterations 20 --warmup 3        # 八段分解（时间批次）
python3 tools/perf-scaling.py --axes functions --sizes 1,2,4,8 --rounds 2 --warmup 1
python3 tests/selfhost/llvm-function-cache.py --compiler-path ./yh   # 字段与区间断言
```

## 5. 局限

- **数据取自重排之前**：第 1 节的数字来自 `20261027-000451`（打点值还在 `module_build`
  的模块级 `let` 里）。随后为过架构预算把存储搬到 `GenState`、把输出抽到
  `stats_print.yh`，只是位置变化；重排后补跑 2 轮（`tmp/perf/20261027-003340`）得到同结构：
  冷编 prep 164.1 / build 12571.0 / verify 3154.0 / 真 lowering 11901.7 / capture 0，
  未重跑 20 轮。

- **打点密度**：函数级 4 次 `clock_gettime`/函数（约 20–25 ns 一次），512 函数量级
  约 50 µs，占总时长 <0.01%；未做「关打点/A-B」对照，因为开销远小于噪声。
- **本批 load1 中位 5.85**（远高于 PF2 批次的 4.09），绝对数字比 PF2 批高约 7–10%；
  结论只用同一批内的比例。
- **capture 与 cache 合并的表示没有继续拆**（序列化格式内部：字符串池、类型表、指令编码），
  那是下一步（PL1c）。
- **verify 未做关闭对照**：本报告只给出成本，未验证「关闭后语义是否仍被其他门覆盖」。
