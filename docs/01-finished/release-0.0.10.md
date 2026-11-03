# 0.0.10 — 编译体验：函数级缓存生效、冷编砍半、just 迁移

正式版。0.0.10-rc.1 已作为预发布验证通过，本版在其基础上带上三处 CI/Linux 修复后发布。
本版由 0.0.10-rc.1 的种子构建（种子链：0.0.9 → 0.0.10-rc.1 → 0.0.10）。

## 主要内容

**函数级缓存（PC1–PC4、PC7a）**

- 键稳定：`checked_cache_layout` 只混「声明面」事实（struct/union/enum 布局与函数签名），
  不再混 interned 类型表下标（它与 check 缓存命中成环）。命中率 `gen` 0/201 → **201/201**、
  `build` → **268/268**。
- IR 类型去重：`ir_module_add_type` 按「名义名 + 布局 + 字段 + 签名」去重，最大模块
  IR 类型 **907 → 118**、结构重复 706 → 0–1。
- check 切片 v3：记录携带本函数字符串登记，并只缓存「不新建类型/静态数据」的函数；
  命中 **38/205**（此前恒 0），`.fchk` 记录 1209 → **373**；旧键按旧索引回收。
- 冷编不写函数缓存（以 `manifest/link.manifest` 作「上轮完成」哨兵）：冷编
  **23.0 s → 11.0 s（−52%）**。
- capture 去掉两处重复校验；编译器指纹与链接工具身份改用 `(size, mtime_ns)`，
  不再每轮重哈希 70 MB 级二进制。

**构建入口与工具链**

- `Makefile` → **`justfile` 唯一真源**；修裸 `just` 只跑私有 `_prepare`、Darwin/ARM64
  守卫拿 `arch()=aarch64` 与 `arm64` 比较这两个迁移 bug；`stage-yh` 打印编译器身份。

**健壮性**

- worker 父死子退：中断构建不再留 `ppid=1` 孤儿（实测 2.2 s 内退出，此前残留 9–17 分钟）。

**性能基线工具（PF0/PF1）**

- `tools/perf-baseline.py`：冻结语料 + 四场景 ≥3 轮 + 阶段/命中/load 记录 + `--ab` 交错。

**相对 rc.1 的三处修复**

- `libs/json/75_files.linux.yh`：`write_file` 的 Linux 分支把 `os.write_fd`（返回 i64）
  当成 `IoResult` 用，Linux 目标编译必然报「类型不匹配」；改为与 darwin 分支一致的
  i64 写法。macOS 门禁不编译 `*.linux.yh`，所以此前未暴露。
- cli 差分门：3 条「未知差异」实测是 **argparse 在 3.13+ 的语义漂移**（同一 argv 在
  3.12 报错、3.14 成功），yh 输出与 3.14 参考一致。改为 `ORACLE_PYTHON=(3,14)` 并把
  版本差异计入「已知差异」，汇总行打印 `cli diff(oracle X.Y)`。
- CI 镜像按 Dockerfile 哈希重建（旧镜像复用导致容器内没有 `just`）、并发 buildkit
  争用、darwin 自举闭包探针穿透 `tmp/llvm-migration` 软链三处修复。

## 实测（load≈4–5）

| 场景 | 0.0.9 | 0.0.10 |
| --- | --- | --- |
| 冷编（清 `.build`） | 23.0 s | **10.3–11.0 s** |
| 全量重编（含写缓存） | 26–28 s | **16.1 s** |
| 热编无改动 | 1.14–1.21 s | **0.98 s** |
| 单函数改动 | 6.7–7.7 s | **3.59 s**（IR 204 / check 38 命中） |

## 三端验证

- 分支门（`ci.yml`，`0.0.10-rc`）：darwin-arm64（122/122）、linux-arm64（133/133）、
  linux-x86_64（133/133）全部 succeeded。
- `release.yml` 三端构建 + 打包 + 发布：0.0.10-rc.1 已作为 prerelease 发布（三端种子）。

## 已知边界

- 单函数改动 ≤3 s 需函数级目标文件（PC7，单独立项；其方案 B 要改桥 ABI）。
- check 切片只覆盖「不新建类型/静态数据」的函数（约 1/5），其余仍全量重查（PC2c）。
- Linux 宿主裸跑 `yh build` 仍需 `YH_LINK_RUNTIME_FLAGS`（LC1）。
- 产物二进制不可位级复现：ad-hoc 签名把临时名/pid 写进 codesign identifier（RB5）。
