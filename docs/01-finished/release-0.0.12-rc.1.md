# 0.0.12-rc.1 — Windows 原生宿主与四端 CI 收敛

预发布候选（prerelease）。相对 0.0.11 正式版，本 RC 把 Windows 提升为一等
构建/宿主平台，并完成 CI 从 Gitea/CircleCI 到 GitHub Actions 四端的迁移。

## 主要内容

**W2 Windows 原生宿主**
- Windows 成为一等公民宿主：原生 `yh.exe` 构建、标准库平台变体（W2-7）、
  双主门收口（W2-9）。
- 入口桩改用宽命令行（`GetCommandLineW`），argv 从源头就是 UTF-8；
  CRT 入口重建 UTF-8 argv（0b1ba2f / b6fafa7），根治 GBK/ANSI 字节导致的
  filter 等用例失败。
- Windows 闭包可重定位，自举桥补齐 `_prepare_windows_sdk`（01ddd19）。

**四端 CI（GitHub Actions）**
- 替代 Gitea Actions 与本机 Jenkins：linux-x64 / linux-arm64 / darwin-arm64 /
  windows-x64 四平台原生 runner 并行（ci.yml 分支门 + release.yml 发布）。
- 固定 runner 版本（ubuntu-24.04 / ubuntu-24.04-arm / macos-15 /
  windows-2022），避免 ubuntu-latest 滚到 26.04 的 libxml2 SONAME 与
  gcc15/gnu23 不兼容。
- 过渡期自举桥（bootstrap-bridge）接进四端 job，让 0.0.11 种子能构建含
  W2 平台文件的当前 HEAD。

**性能与产物工程**
- 缓存格式升到 v2（payload FNV 校验），命中装载跳过整段语义 verify；
  失效矩阵（6 场景）、规模律、产物体积度量。
- UF1：未使用函数直接报错，清掉 24 个死函数。
- fmt 移植 I4-7 + J6-L1..L4 到 B1/B2 结构（产物体积收口）。

**其它**
- 版本号编码进二进制（`YH_VERSION_TEXT` 常量，`yh --version` 不读
  project.toml），arch-check 加 toml↔常量一致性断言（d5fca1d）。
- 测试门：Windows ACP 无法表示非 ASCII 文件名时，精确跳过两个 R3 目录
  扫描用例（39f15a3），隔离 CI 环境差异（非缺陷修复）。

## 验证

- 分支门（ci.yml）：四端 job 全绿（run 41954793463，commit 39f15a3）。
- 发布流水线（release.yml）：四端取上一版种子 → 闭包 → 自举桥 → 平台门 →
  自举门 → 滚 cc4 → 打包上传。
- 本 RC 由 0.0.11 种子经过渡期自举桥构建（种子链：0.0.11 → **0.0.12-rc.1**）。

## 已知边界

- **W2 平台文件**：0.0.11 种子不认识 W2 平台文件，必须经 bootstrap-bridge
  过渡；桥脚本到位前不要自行发明包名。
- **Windows ACP 遗留（P1）**：CRT 文件路径仍按 ACP 解释，非 ASCII 文件名在
  ACP=1252 等环境不支持；当前以测试精确跳过隔离，根治（FindFirstFileW +
  _wopen 或 UTF-8 activeCodePage manifest）已列入 todo.md 待修项。
- **CI 红灯按 todo 立项再修**：本地不预跑其他平台门禁。
- x86_64 资产是容器/模拟，只作兼容性证据，不作原生行为/性能结论。
