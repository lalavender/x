# 0.0.10-rc.1 — 编译体验：函数级缓存真正生效 + just 迁移

预发布（prerelease）。本版把 2026-10-25/26 的性能归因结论全部落地：函数级缓存从
「写得多、命中恒 0」变成「命中稳定」，冷编砍半，并补齐性能基线工具与中断健壮性。
rc.1 用 0.0.9 正式版种子构建。

## 主要内容

**函数级缓存（PC1–PC4、PC7a）**

- **键稳定**：`checked_cache_layout` 只混「声明面」事实（struct/union/enum 布局与
  函数签名），不再混 interned 类型表下标（它与 check 缓存命中成环）。命中率
  `gen` 0/201 → **201/201**、`build` 0/268 → **268/268**。
- **IR 类型去重**：`ir_module_add_type` 按「名义名 + 布局 + 字段 + 签名」去重，
  最大模块的 IR 类型 **907 → 118**、结构重复 706 → 0–1。
- **check 切片 v3**：记录携带本函数的字符串登记（label/length/quoted + 字节），
  并且只缓存「不新建类型/静态数据」的函数（命中因此不改变类型编号）；旧键按旧索引
  回收。命中 **38/205**（此前恒 0），`.fchk` 记录 1209 → **373**。
- **冷编不写函数缓存**：以 `manifest/link.manifest` 作「上一轮完成」哨兵，全冷构建
  只查不写 → 冷编 **23.0 s → 11.0 s**（−52%）。
- **capture 与摘要**：去掉两处重复校验（逐函数 `ir_verify`、迷你模块 `ir_module_verify`）；
  编译器指纹与链接工具身份改用 `(size, mtime_ns)`，不再每轮重哈希 70 MB 级二进制。
- `--stats` 语义保持不变：`ir_functions`/`ir_cache_misses` 仍按「参与缓存判定的函数数」计。

**构建入口与工具链**

- `Makefile` → **`justfile` 唯一真源**：`just`（源新则冷编）、`just build`（强制冷编）、
  `just dev`（增量）、`just test`、`just selfhost-native`、`just seed` 等。
- 修迁移 bug：裸 `just` 只跑 `[private] _prepare`（删掉 `yh` 也不重建）；
  Darwin/ARM64 守卫拿 `arch()` 的 `aarch64` 与 `arm64` 比较导致门禁拒绝执行。
- `stage-yh` 打印编译器身份（路径 / 字节数 / mtime），门禁日志可核对本轮二进制。

**健壮性**

- worker 父死子退：构建被中断（Ctrl-C / 超时 / kill -9）时，worker 在两个检查点比对
  `getppid()` 后退出。实测 `kill -9` 父进程后 **2.2 s 内全部退出**（此前会残留
  9–17 分钟并吃满 CPU）。

**性能基线工具（PF0/PF1）**

- `tools/perf-baseline.py`：把 `compiler/` 复制成冻结语料并记录清单 SHA-256（120 文件 /
  2.27 MB），跑冷编 / 全量重编（含写缓存）/ 热编 / 单函数改动四场景 ≥3 轮，逐轮记录
  墙钟、父进程阶段耗时、`load1`、IR/check 命中与 `.fir` 写入量，输出
  `tmp/perf/<run-id>/{raw.json,report.md}`；`--ab` 提供成对交错与变化率。

## 实测（load≈4–5）

| 场景 | 0.0.9 | 0.0.10-rc.1 |
| --- | --- | --- |
| 冷编（清 `.build`） | 23.0 s | **10.3–11.0 s** |
| 全量重编（含写缓存） | 26–28 s | **16.1 s** |
| 热编无改动 | 1.14–1.21 s | **0.98 s** |
| 单函数改动 | 6.7–7.7 s | **3.59 s**（IR 204 / check 38 命中） |
| `firc/yh-gen` | 1206 记录 / 49 MB | **201 记录 / 8.4 MB** |

## 已知边界

- **单函数改动 ≤3 s 未达成**：模块级 `.o` 决定了每轮要为整模块（205 个函数）重发，
  需要函数级目标文件（PC7，单独立项；其方案 B 要改桥 ABI，须先滚种子）。
- check 切片只覆盖「不新建类型/静态数据」的函数（约 1/5），其余仍全量重查；
  记录按函数带字符串副本，`.fchk` 体积随字符串数增长（PC2c）。
- Linux 宿主裸跑 `yh build` 仍需 `YH_LINK_RUNTIME_FLAGS`（LC1）。
- 产物二进制不可位级复现：ad-hoc 签名把临时名/pid 写进 codesign identifier（RB5）。

## 验收与下一步

- 发布后按流程用 rc 二进制复验：`rm -rf bin && just fetch-seed && just && just test &&
  just selfhost-native`（`fetch-seed` 需要 `GH_TOKEN`/`GITHUB_TOKEN` 访问
  `lalavender/x` 的 Release）。
- 复验通过后 `git merge --no-ff 0.0.10-rc` → `0.0.10-release`，再打正式 tag `0.0.10`。
