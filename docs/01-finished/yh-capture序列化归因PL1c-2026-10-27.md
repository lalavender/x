# yh capture 序列化归因（PL1c）

日期：2026-10-27。状态：**已完成**（含一次受控的一次性实验）。上游是
[PL1 lowering 内部归因](yh-lowering内部归因PL1-2026-10-27.md)：
它指出写缓存构建里 capture（函数 IR 序列化）单项 23.6 s、占 worker 累计 50.5%。

## 1. 结论

**capture 的成本在「序列化写缓冲」，不在「闭包扫描」。**

一次性实验（允许 `ir → gen` 的临时构建，量完已回退；见 §3）在本机全量重编上测得：

| 段 | 累计 | 占比 | 说明 |
| --- | --- | --- | --- |
| 闭包标记（mark） | 0.55 s | **1.9%** | 符号/类型/重定位扫描 |
| 迷你模块构造（mini） | 8.65 s | **30.4%** | `add_type/add_symbol/add_global/add_function`（含名字复制与查重） |
| 序列化写缓冲（write） | 18.62 s | **65.5%** | `ir_module_serialized_size` + `ir_module_serialize` |
| 合计 | 28.42 s / 1476 函数 = **19.3 ms/函数** | 97.9%（差额是分配/释放） | |

**吞吐口径**：这一轮写出 1476 条记录、共 **38.08 MB**（中位 18.0 KB/条、最大 287.3 KB），
序列化段 18.62 s ⇒ **2.05 MB/s**。对一个以 memcpy/定长写入为主的编码器，这个吞吐低两个
数量级，几乎可以肯定是每条记录内存在 O(n²) 的查表/增长拷贝（字符串池或符号表线性查找），
而不是 I/O（写盘在 `firc_commit`，不在 capture 计时内）。

**与合成语料的对照**（`perf-scaling.py --write-cache`，单模块、只含 int，64→512 函数）：

| 函数数 | capture 合计 ms | 每函数 ms |
| --- | --- | --- |
| 64 | 26.9 | 0.83 |
| 128 | 80.3 | 1.24 |
| 256 | 167.7 | 1.30 |
| 512 | 490.9 | **1.91** |

两点：① 每函数 capture 随模块变大涨 2.3×（8× 函数），与 PL1 里 verify/真 lowering
的超线性同向；② 真实语料 19.3 ms/函数是合成语料的 **10 倍**，因为真实函数引用的
类型/符号闭包大得多（记录体积中位 18 KB vs 合成几百字节）——**capture 的成本跟着
「每条记录要编码的闭包」走，而不是跟着函数条数走**。

## 2. 对优化的含义（改写了原先的排序）

| 原先判断 | 现在（PL1c 数据） |
| --- | --- |
| PC2c「按模块共享字符串池 + 引用计数」是 capture 的主要出路 | 只对口 mini 那 30.4%；**主战场是 `ir_module_serialize` 本身**（65.5%，2.05 MB/s） |
| capture 主要是扫描闭包 | 扫描只占 1.9%，可以忽略 |

新的排序：

1. **PL1e `ir_module_serialize` 提速**：先查每条记录内的字符串/符号线性查找与缓冲增长
   （2.05 MB/s → 目标 ≥100 MB/s 量级即够用），这是全量重编 worker 累计里最大的一项。
2. **PL1f 缓存合并（增量路径）**：PL1 已量到单函数改动的 lowering 里 998 ms 是合并
   204 条记录（4.9 ms/条）；与 PL1e 共用同一套编码后可一起降。
3. PC2c 字符串池：作为 PL1e 的实现手段之一，而不是独立目标。

## 3. 实验方法（可复现，但**不进入主线**）

`ir` 不允许依赖 `gen`（`tools/arch-check.py` 的模块依赖表），所以 capture 内部计时不能
常驻。做法：

1. 临时给 `ir_function_cache_capture` 加 `timing *IRFunctionCacheTiming` 出参，
   在 mark/mini/write 三处用 `gen.clock_ns()` 打点，并把值经 `lower` 汇总进
   `--stats`（`time_capture_{mark,mini,write}_ns`）。
2. 构建、跑一次全量重编（删对象不删 `manifest/link.manifest`，保证走写缓存路径），
   取 1476 条记录的三段累计与 `.fir` 体积。
3. **立刻回退**：`ir` 恢复零依赖、`--stats` 恢复 4+8 段字段；`just` 与
   `just arch-check` 重新通过（见 §5 验证）。

因此本报告的三段拆分是「一次性实验」数据，主线工具不输出这三段；主线可复现的是
capture 总量与 `--rss`/归因表里的其他字段。

## 4. 复跑

```bash
# 主线：capture 总量（不含三段拆分）
just
python3 tools/perf-baseline.py --iterations 3 --warmup 1     # 看 lowering 细分表的 capture 列
python3 tools/perf-scaling.py --axes functions --sizes 1,8 --rounds 2 --warmup 1 --write-cache
# 一次性实验：按 §3 临时加回 timing 出参后重跑，量完务必回退并用 arch-check 验证
```

## 5. 验证与局限

- 回退后：`just` 构建通过、`just arch-check` 通过（`ir` 依赖表恢复；`just test` 0 失败、
  `just selfhost-native` 全绿：固定点一致、cc4 自解析 123 个源文件、project cases 122/122）。
- **三段拆分不可从主线复现**（需要改依赖），量级结论（capture≈19 ms/函数、写缓冲主导）
  与 §1 的吞吐计算一致，但具体百分比只代表这一台机器/这一次构建。
- `mini` 段包含名字复制与查重，但未拆到「字符串池 / 符号表 / 类型表」；
  `write` 段未拆到 `serialized_size` 与 `serialize` 各自多少。
- 合成语料只有 `int` 类型，闭包极小，所以它的 0.8–1.9 ms/函数不能代表真实项目；
  两次测量之间 load1 也不同（实验批次未单独记录 load）。
