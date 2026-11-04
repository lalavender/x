# yh-CI自举桥VTEST适配-2026-11-05

## 概述

Lane B1：让过渡期自举桥（`tools/ci-bootstrap.py`）兼容 2026-11-05 的
`.test.yh` 测试文件改名（VTEST），并把 Windows 宿主纳入桥的两代自举。

## 背景

0.0.11 代种子（含过渡期 Windows 种子）按**文件名字典序**扫描模块。VTEST
改名后 `actions.test.yh` 等无排序前缀，会排到 `cli.yh` 之前报「未知类型」
——三个 CI job 全会被打红：

- linux-x64 / linux-arm64 / darwin-arm64：`bootstrap-bridge` 的 gen-1
  解析 `libs/cli` 失败；
- windows-x64：`fetch-release-seed` 拉的 0.0.11-windows 过渡种子 + `just
  build` 同样失败。

## 变更（tools/ci-bootstrap.py）

1. **测试文件改名 staging（全宿主）**：新增 `test_rename_pairs()`——所有
   `*.test.yh` 在 staging 里临时加回 `zz_` 前缀（字典序最后），gen-1 可被
   0.0.11 解析；gen-2 用 yh1（HEAD 逻辑，含 test-last 排序规则）构建
   **原样无前缀源码**。改名纳入既有备份/恢复/崩溃恢复机制（新增 "staged"
   条目类型：恢复时删除临时副本）。
2. **Windows 宿主支持**：`HOST_TABLE` 增加 `("Windows","AMD64")`；
   `apply_transform` 按 `windows_host` 条件跳过变体移出/标记改写/链接节
   裁剪（0.0.11-windows 种子认识 W2），只做测试文件改名。`OTHER_MARKER`
   补 Windows 键。`--output` 缺省在 Windows 为 `yh.exe`。

## CI 接线

`ci.yml` windows-x64 job：`冷编 just build` → **`just bootstrap-bridge`**
（与其余三端一致；`just test` 经 `_ensure_built` 的 mtime 检查自动使用桥
产物 `yh.exe`，不会用 Release 种子重编）。头部注释说明四端统一走桥。

## 验证

- Windows 本机端到端两代自举（`python tools/ci-bootstrap.py run`）：
  gen-1（16 个测试文件临时 `zz_` 前缀）108 s + gen-2 全量 HEAD 108 s，
  产物 `yh.exe` sha `2d9693b0…` 与此前滚动的种子**逐字节一致**（确定性
  构建），源码树恢复干净（无 `zz_` 残留），`--version`/`--emit-asm` 冒烟
  正常。
- 说明：本机 bin 里的种子已是 HEAD 产物（今日多次滚种子），gen-0 用它
  验证的是**机制**；0.0.11 种子的真实解析验证在 CI 首跑（B2/B3）完成，
  唯一已知存疑点（空函数体）与兜底见实施方案 §1.4。
- 注意：本机跑 `just bootstrap-bridge` 需带环境前缀（PYTHONPATH 置空等，
  见 2026-11-05 日志），CI 无此问题。

## 后续（Lane B 剩余）

B3：推送触发 `ci.yml` 四端实跑；B4：rc tag → `release.yml` 出四平台种子；
B5：删桥切 `just bootstrap`；B6：清账。
