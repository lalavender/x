# 0.0.12 — Windows 一等宿主与四端 GitHub Actions 流水线

正式版。0.0.12-rc.3 已作为预发布验证通过（四端流水线全绿、发布资产齐全），本版
在其代码上只增加发布文档与版号，**代码与 rc.3 完全一致**。
种子链：0.0.11 → 0.0.12-rc.1 → 0.0.12-rc.2 → 0.0.12-rc.3 → **0.0.12**。

tag 打在分支 `0.0.12-release`（由 `0.0.12-rc` 合入）；本轮候选开发在 `llvm` 上
直接推进，三个 rc 依次修掉流水线接线问题后转正式版。

## 主要内容

**W2：Windows 成为一等宿主**

- 编译器原生产物 `yh.exe`；入口桩改用宽命令行（`GetCommandLineW`），argv 从源头
  就是 UTF-8，CRT 入口按 UTF-8 重建 argv，根治 GBK/ANSI 字节导致的 filter 等用例
  失败（0b1ba2f / b6fafa7）。
- 控制台启动切 65001 码页，中文输出不再乱码；`--emit-asm` 在 Windows 上改走
  临时目录 + `%TEMP%` 兜底（本机安全策略拒绝不受信 exe 写 `%TEMP%` 的问题在桥
  publish_buffer 路径上加 errno 诊断）。
- 标准库平台变体（W2-7）：`*.windows.*.yh` 15 个文件 + `windows` comptime 标记 +
  `[link-windows-x64]` 清单节；W2-9 双主门收口。
- Windows LLVM 闭包可重定位（Zig 式：闭包与身份记录由构建机提供，CI 缓存复用）。

**VTEST：测试文件后缀 `.test.yh`**

- 测试文件统一 `*.test.yh`，废止 `zz_`/`99_` 排序前缀；模块内按依赖序编译，测试
  文件一律排在非测试文件之后（`compiler/build/project_index.yh` 的
  `pj_name_is_test` / `pj_dir_less`）。生产构建不登记测试符号、不发射测试体。

**命令行与版本**

- cmd P1：`api.yh` 拆成一命令一文件（`cmd_build`/`cmd_single`/`cmd_test`/…），
  模块导出面只剩 `main`。
- 版本编码进二进制：`YH_VERSION_TEXT` 常量 + `yh --version` 不读 `project.toml`，
  `tools/arch-check.py` 加 toml↔常量一致性断言。

**SDK 与分发**

- Darwin/Windows SDK 迁移到 `vendor/`（`darwin-sdk`/`windows-sdk`，git mv），运行时
  查找路径同步；SDK 资产锁 LF 行尾。

**CI：GitHub Actions 四端**

- `ci.yml`（分支门）与 `release.yml`（发布）：linux-x64 / linux-arm64 /
  darwin-arm64 / windows-x64 四端原生 runner 并行，替代 Gitea Actions、本机
  Jenkins 与 CircleCI（三者均已删除）。
- 固定 runner 版本（`ubuntu-24.04`/`ubuntu-24.04-arm`/`macos-15`/`windows-2022`），
  避免 `ubuntu-latest` 滚到 26.04 的 libxml2 SONAME 与 gcc15/gnu23 不兼容。
- 闭包不上传 Release，由 CI 机器自行准备（Linux 用 Ubuntu deb；Darwin/Windows
  源码构建并走 actions/cache）。
- 过渡期自举桥 `just bootstrap-bridge`（`tools/ci-bootstrap.py`）：0.0.11 代种子
  不认识 W2 平台文件与 `.test.yh` 排序，桥先用等价形态编出 yh1，再用 yh1 全量
  冷编 HEAD；staging 给 `*.test.yh` 临时加回 `zz_` 前缀。

## 三个 rc 的收敛过程

| rc | 结果 | 修掉的阻塞 |
|---|---|---|
| rc.1 | windows 端红 | `release.yml` 的 windows job 漏接 `just bootstrap-bridge`，用 0.0.11 种子直接冷编 HEAD → `libs/cli/actions.test.yh` 早于 `cli.yh` 报「未知类型」 |
| rc.2 | windows 端红 | 桥接已生效；打包步骤 `cp "$cc4" "$stage/yh"` 引用了自己刚 `rm -rf` 掉的候选目录 → `cannot stat` |
| rc.3 | **四端全绿** | 打包源改为仓库根 `yh`，与 linux/darwin 同构；publish 成功发布 8 个资产 |

## 验证

- 发布流水线（run 42062242047，commit ab244e3）：四端 job 全 success，publish
  校验四端 tar.gz + sha256 与发布说明后发布 prerelease。
- 分支门（ci.yml run 41966609194，commit a0004fb）：四端全绿。
- **发布二进制验收**：`rm -rf bin && just fetch-seed` 取 0.0.12-rc.3 种子
  （sha256 `d6721853…`）→ `just` 冷编 → `just test` → `just selfhost-native`
  （两代固定点 + 自解析 + 全量语料 + modules/项目验收），结果见下方「验收记录」。

## 验收记录

宿主：Windows/x64 原生；种子：发布出去的 `yh-0.0.12-rc.3`（从 Release 资产取，
`bin/yh-windows-x64`，SHA-256 `d6721853…`）；**代码基线 = tag 0.0.12-rc.3
（ab244e3），本版只在其上加版号与发布文档**。

| 步骤 | 命令 | 结果 |
|---|---|---|
| 取种 | `just fetch-seed` | 0.0.12-rc.3 下载并核对哈希 OK |
| 冷编 | `just build` | 完成，`yh --version` = `yh 0.0.12` |
| 三层回归 | `just test` | 全绿（ANTLR 跳过由 YH_ANTLR=0，其余各层通过；PASS 554 行） |
| 自举主门 | `just selfhost-native` | 全绿 |

自举主门细目：模块固定点 cc3→cc4 共 48 个产物一致；cc4 自解析 148 个源文件 OK；
固定点探针 OK；CLI 冒烟（裸调用/坏参数/`--help`）OK；语法语料反例 49/49；
运行语料 363/372（windows-x64 原生，其余按平台标注跳过）；并发项目扫描 4/4；
modules 19/19；`compiler-tests` 4/4；project cases 130/130。

本机两处环境垫片（不影响结论，CI 四端是平台真值）：`python3` 在本机是 Microsoft
Store 桩，用 `tmp/pyshim/python3.exe` 垫片跑语料；`foreign-fs-build.py` 受本机
安全策略（不受信 exe 不能写 `%TEMP%`）限制，以 `TEMP` 指向仓库内目录等价通过，
真正的跨文件系统证据由 CI 四端承担。

## 已知边界

- **过渡期自举桥仍需保留**：正式版 0.0.12 的种子取 0.0.12-rc.3（rc.1/rc.2 未产
  资产，rc.3 起有），桥在 `ci.yml`/`release.yml` 四端接线；0.0.12 种子发布后，
  下一版的种子已认识 W2 平台文件与 `.test.yh`，可切回 `just build` 并删除
  `tools/ci-bootstrap.py`（docs/todo.md 的过渡期条目）。
- **Windows ACP 遗留（P1）**：CRT 文件路径仍按进程 ACP 解释，非 ASCII 文件名在
  ACP=1252 等环境不支持；CI 已按 `GetACP()` 精确跳过两例目录扫描用例，根治
  （目录枚举改 W API + `_wopen`，或 UTF-8 activeCodePage manifest）列入 todo。
- **标准库目录文件名顺序**：模块内按文件名字节序编译，类型必须先定义；
  `libs/fmt`/`libs/toml` 等仍带数字前缀的包改名时要逐个重算拓扑序。
- x86_64 Linux 资产是容器/模拟环境的兼容性证据，不作原生行为/性能结论。
