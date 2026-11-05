# 0.0.12-rc.2 — 修复发布流水线 Windows 端自举桥接线

预发布候选（prerelease）。相对 0.0.12-rc.1 只做发布流水线接线修复，编译器行为不变。

## 为什么有 rc.2

0.0.12-rc.1（release.yml run 41957530693）四端里只有 windows-x64 失败，失败点是
job 127015942985 的「冷编」步骤：

```
../libs/cli/actions.test.yh:14:32: 错误: 未知类型（类型必须先定义）
yh: 无法启动模块编译 worker
yh: 模块编译失败；已停止最终链接
error: recipe `build` failed on line 245 with exit code 1
```

根因不是编译器缺陷，而是接线遗漏：rc.1 的 `release.yml` 里 linux-x64、
linux-arm64、darwin-arm64 三个 job 已改用 `just bootstrap-bridge`，只有
windows-x64 job 仍是 `just build`。0.0.11-windows 种子（2026-11-03 按当时 HEAD
重编）认识 W2 平台文件，但早于 2026-11-05 的 VTEST（`.test.yh` 改名、`zz_`/`99_`
排序前缀废止、改由编译器 test-last 排序）：旧种子按字典序扫描，把
`libs/cli/actions.test.yh` 排在定义 `pub struct Namespace` 的 `cli.yh` 之前，
于是报「未知类型（类型必须先定义）」。

## 修复

- `release.yml` 的 windows-x64 job 把「冷编」`just build` 改为「过渡期自举桥」
  `just bootstrap-bridge`，与 `ci.yml` 四端口径一致。
- 桥的第 1 代 staging 会给所有 `*.test.yh` 临时加回 `zz_` 前缀
  （`tools/ci-bootstrap.py` 的 `test_rename_pairs`），第 2 代再用 yh1 全量冷编
  HEAD，产物写成 `yh.exe` 并把种子写到 `bin/yh-windows-x64` 供自举门使用。
- 版本升到 0.0.12-rc.2：`compiler/project.toml` 的 `project.version` 与
  `compiler/cmdline/cmdline.yh` 的 `YH_VERSION_TEXT` 同步（`tools/arch-check.py`
  一致性断言）。

## 验证

- 同一条修法已在分支门验证：`ci.yml` run 41954793463（commit 39f15a3）四端全绿，
  windows-x64 的自举桥步骤 success。
- rc.2 发布流水线：四端取上一版种子（rc.1 未产出任何 Release 资产，仍取 0.0.11）
  → 准备本机闭包 → 过渡期自举桥 → 平台门 → 自举门 → 滚 cc4 → 打包上传。
- 种子链：0.0.11 → **0.0.12-rc.2**。

## 已知边界

- 0.0.12-rc.1 的 tag 保留在 git 历史，未产出 Release 资产；本 rc.2 是唯一带四端
  资产的候选。
- 过渡期自举桥与 `tools/ci-bootstrap.py` 继续保留：rc.2 的种子仍取 0.0.11，需等
  含 W2 种子的 Release 发布后再删桥（见 docs/todo.md）。
- Windows ACP 遗留（P1）与 rc.1 相同，见 `release-0.0.12-rc.1.md`。
