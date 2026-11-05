# finish

滚动日志：只保留最近三天（当前为 2026-11-04 ～ 2026-11-06）的交付记录，靠前条目为最新状态。
更早条目按批次归档在
[finish 历史归档](01-finished/finish-历史归档-2026-09-27至2026-10-21.md)
（文件名区间是首档范围，内容已含 2026-10-22 ～ 2026-11-03 的两批迁入条目）；新增条目写在最前。
2026-11-06 清理：此前文件里残留 2026-09-27 ～ 2026-10-21 的 381 条归档副本
（2026-10-24 首次归档只复制未从 finish.md 删除），已删除；并补齐 2026-10-22 残留与
2026-10-26 ～ 2026-11-03 批次的迁移，见归档文件的「2026-11-06 迁入」段。

## 2026-11-06 todo 清账：删除全部已完成项，只留未完成与待决策

`docs/todo.md` 从 840 行降到 631 行、勾选项清零（原 30 个 `[x]` + 11 个已完成/
失效的未勾条目），按「本文件只保留未完成项，历史看 finish.md / 01-finished」
统一口径：

| 类别 | 处理 |
| --- | --- |
| Windows W 系列已完成片（W0-1/1b/2a/4、W1-1/2/2b/3/3b/3c/3d/4/5/6/7/8、W2-1/2b/2c/3/3a/4a/5/6/7/9、CI 接线） | 删除（证据在 `01-finished/` 与各设计文档） |
| 两个 P0 已修项（`--emit-asm`、Windows 闭包可重定位首建） | 删除 |
| 已被现实取代的条目：W0-3（决策冻结）、W2-0（等 0.0.11 种子）、W2-4b（Windows 进程模型）、W2-5b（CI windows job 实跑）、W2-2（Windows 闭包分发）、R1（分支模型）、R3（取种含 rc）、R5（0.0.8 内容）、D2（Gitea 收尾）、D3（x86_64 模拟崩溃） | 删除 |
| C1（固定 SDK 预编译分发） | 删除条目，移入「设计决定不做」（2026-11-03 闭包不入 Release 的决策） |
| 「实跑验收」 | 收敛为唯一剩余项：`perf.yml` 首次实跑 |
| 去数字前缀段落 | 改写为「已落地」，只留「顺序错误诊断不可读」这一条 |
| 过期叙述 | 删掉「GitHub 四端 job 暂停」「Gitea/CircleCI 在跑」「0.0.11 桥 staging」等已不成立的描述；「三端种子」改「四端种子」 |

保留但按证据改写：`foreign-fs-build`（不是 CI 红，而是本机 Windows `%TEMP%`
安全策略问题，与 `--emit-asm` 同根因）。

不动：所有 `[ ]` 未完成项、`待决策` 与 `设计决定不做` 两节。

## 2026-11-06 根 README 改为 README.md 并按当前口径刷新

`git mv README README.md`（git 保留改名历史），全文按 ste-zh（简化技术中文）重写：
短句、一词一义、状态词固定、情态词只用「必须/不得/可以」。

口径变化（相对旧 README）：

- 版本 `0.0.12-rc.3`；`compiler/` 16 模块表（旧文写 8 个模块）；
- 代码生成唯一后端 LLVM 21、内嵌 lld；四目标 triple 表，`x86_64-apple-darwin`
  标注「未验证，CI 不覆盖」；
- 项目模式默认产物改为 `<项目根>/.build/<name>`；入口模块名必须是 `main`；
- 源文件 `module <名>;` 头与 `import` 约束；标准库 15 模块与三级加载顺序；
- 新增术语、文档索引、种子/构建缓存、CI 与发布口径；删除 C 版 stage0、`-c`/`-run`/
  `-sysroot`、仅 arm64 后端、prelude 八函数等过时内容。
- 独立只读核对后修订 6 处：补 `name` 必填与标识符规则、`--list` 增加声明位置、
  `--no-run` 改为「不生成入口」、模块表 `cmd` 改为 `main`（目录 `cmd/`）、
  四端全绿改用 run `42062242047`、裸变参改为「设计决定不做」。

验证（Windows 本机 `yh.exe`）：

- 已验证：三处 `yh` 代码块 `--syntax-check` 全过；quick-start hello 与语言速览示例
  编译运行，输出 `hello, yh` 与 `1 2 1`/`10`/`6`/`small`。
- 已验证：按 README 的 `[project]` 清单与标准库示例建项目，`yh build` 得
  `.build/demo`；运行写入 `demo.txt`，字节为 `001 002 003`。
- 已验证：README 相对链接全部可达；自检脚本 `tmp/readme-check/check_readme.py`。

未做：`just test` / `just selfhost-native` 未在本机重跑。本次只改文档；且本机沙箱
拒绝 `just` 的 backtick 管道，`just` 默认目标报 os error 5（justfile:104）。
`compiler/README.md` 等子文档仍按旧口径，未一并刷新。

## 2026-11-06 libs 全量去数字前缀：语义名 + 字节序即依赖序

`libs/` 下剩余带数字前缀的 6 个模块（libc、net、os、string、sys、toml）全部改成
语义名；工作区里已改但顺序错误的 fmt 一并修正（`model`→`base`、`spec`→`directive`）。
模块内仍按**文件名字节序**编译、类型与数组长度常量必须先于使用，因此新名字同时
满足「字节序 = 拓扑序」。共享类型/常量的前置文件统一叫 `base.yh`（与 json 一致）：

| 模块 | 旧名 → 新名 |
| --- | --- |
| libc | `10_memory`/`20_string`/`30_convert`/`40_sort` → `memory`/`string`/`convert`/`sort`（彼此无类型依赖，任意顺序可编） |
| net | `00_model`→`base`、`05_error`→`errors`、`10_address`→`text`、`20_tcp.*`→`tcp.*`（`base` 前置；`tcp`/`text` 只依赖 `base`+`errors`，函数前引用不受限） |
| os | `00_model`→`base`、`10_errors`→`errors`、`20_directory.*`→`directory.*`、`30_process.*`→`process.*`、`40_sleep`→`sleep` |
| string | `00_model`→`base`、`10_view`→`view`、`20_owned`→`owned`、`30_transform`→`transform`、`40_utf8`→`utf8` |
| sys | `00_types`→`base`、`05_errno.*`→`errno.*`、`10_constants.*`→`constants.*`、`20_raw.linux`→`raw.linux`、`30_file.*`→`file.*`、`40_memory.*`→`memory.*`、`50_time.*`→`time.*`、`60_process.*`→`process.*`、`70_socket.*`→`socket.*` |
| toml | `00_types`→`base`、`10_storage`→`document`、`20_utf8`→`encoding`、`30_numbers`→`numbers`、`40_datetime`→`datetime`、`45_parser_state`→`lexer`、`46_strings`→`strings`、`50_parse`→`parse`、`60_query`→`query`、`70_files.*`→`file.*`、`90_api`→`surface` |
| fmt | `model`→`base`、`spec`→`directive`（其余 `float`/`interp`/`output`/`render`/`value` 原名合规） |

fmt 的原工作区改名**编译不过**：`float`、`render` 用 `model` 的类型而
`float < model`，`float` 又用 `spec` 的 `format_spec` 而 `spec > float`。
改成 `base`（前置）+ `directive`（格式说明）后，`base` < `directive` <
`float` < `interp` < `output` < `render` < `value`，顺序全部满足。
toml 的 `lexer`（游标/诊断/空白注释）与 `parse` 的关系同理：`parse` 消费
`parser` 类型，必须排在它之后，因此不能直接叫 `state.yh`。

只改名、未搬移任何声明；`git mv` 保留历史。同步更新 `libs/*/README.md`、
各模块 `doc.yh` 与源文件注释里的文件名、`docs/03-design`（编码规范新增
「共享声明放字节序最前的语义名文件（惯例 `base.yh`）」，删掉「存量不改名」
建议；JSON/TOML/os与sys/http 设计里的顺序说明改为按语义名字节序）、
`docs/adr/0017`、`docs/02-plan` 相关文件表、`docs/todo.md`，以及
`tests/fmt/install.py`、`tests/string/{install.py,run.py,README.md}`、
`tests/toml/{install.py,injection.py}` 的必需文件清单。

验收（本机 Windows `yh.exe`；门禁脚本加 `PYTHONUTF8=1`，否则 GBK 默认编码
读不了含中文的源码副本）：
- `cd libs && ../yh.exe test` **134 passed; 0 skipped; 0 failed**；
- `yh test --no-run --target aarch64-unknown-linux-gnu` / `aarch64-apple-darwin`
  各 **134 个用例构建通过**（覆盖 linux/darwin 平台变体）；
- `yh check --target` 四种 triple（linux x64/arm64、darwin x64/arm64）全部
  「检查通过: yh_libs」；`cd compiler && ../yh.exe check`「检查通过: yh」
  （编译器经 `[dependencies] libs` 复用 cli/io/os/sys/string）；
- `tests/toml/injection.py` 通过（124 个池失败点 + 预算强制失败，已指向
  `toml/document.yh`/`toml/base.yh`）；`tests/string/run.py` model/interop/resources
  全 PASS（注入点改写 `string/base.yh`）；`libs/cli/test/run.py` 5/5；
  `libs/cli/test/diff.py` 88/94（6 个已知差异，与改名无关）；
  `libs/os/test/run.py` linux-check 11/11。
未在本机跑的两项：`libs/libc/test/run.py`（需要宿主 `cc` 链接 ctest.c）与
`tests/*/install.py`（打包步骤产出 `yh.exe`，脚本按 `yh` 查找），留给 CI。

## 2026-11-06 清理 `deliverables/`：两份 2026-10-24 产出迁入 docs/03-design

`deliverables/` 是 2026-10-24 一次 AI 会话（gstack 工作流）的交付目录，全仓库无构建、
门禁或文档引用它（只 `docs/03-design/yh-代码复核-2026-10-24.md` 提过一句"与本次复核无关"）。
按 AGENTS.md 的目录约定，把两份 md 迁入 `docs/03-design/` 后删除该目录：

| 原路径 | 新路径 |
| --- | --- |
| `deliverables/gstack/yh-explorer-design-system-spec-2026-10-24.md` | `docs/03-design/yh-Explorer设计系统规范-2026-10-24.md` |
| `deliverables/gstack/raw/product-review-arch-2026-10-24.md` | `docs/03-design/yh-系统架构与长期演进设计-产品评审-2026-10-24.md` |

设计规范里引用的配套 HTML（`deliverables/gstack/yh-explorer-design-system-2026-10-24.html`）
从未入库、仓库内不存在，迁入时把该行改写为说明，不留断链。纯文档搬迁，无代码与门禁影响。

## 2026-11-06 libs/json 去数字前缀：文件名即编译顺序

`libs/json/` 13 个源文件不再带数字前缀（`base.yh`、`document.yh` …
`surface.yh`），改用语义名并让**文件名字节序仍是拓扑序**（模块内声明必须先于
使用，跨文件提前引用会报「未知类型（类型必须先定义）」）：

| 旧名 | 新名 |
| --- | --- |
| `00_types.yh` | `base.yh`（所有文件的前置：公开类型/枚举/预算常量） |
| `10_storage.yh` | `document.yh` |
| `20_utf8.yh` | `encoding.yh` |
| `30_numbers.yh` | `digits.yh` |
| `40_lex.yh` / `50_parse.yh` / `60_query.yh` | `lex.yh` / `parse.yh` / `query.yh`（原名即合规） |
| `70_write.yh` | `render.yh`（builder 状态机） |
| `75_files.{linux,darwin,windows}.yh` | `stream.{linux,darwin,windows}.yh` |
| `80_encode.yh` | `serialize.yh`（值树递归写出 + `encode`/`encode_owned`） |
| `90_api.yh` | `surface.yh`（`parse`/`parse_text`/`root`/`release` + 诊断） |
| `tests.test.yh` | `json.test.yh`（工作区已有改名，本批保留） |

顺序论证：`base` < `digits` < `document` < `encoding` < `lex` < `parse` <
`query` < `render` < `serialize` < `stream.*` < `surface`，逐级满足类型/常量
依赖；`stream` 调 `surface.parse` 属函数前引用（今天 75_files→surface 同样如此）。
只改名、未搬移任何声明。同步更新 `docs/03-design/yh-JSON标准库设计-2026-10-24.md`
（§2 目录树 + §9 实现落点）、`libs/json/README.md`、`docs/03-design/yh-标准库设计.md`、
`docs/todo.md` 与 `tests/modules/build-check.py` 的文件引用。
验收：`cd libs && ../yh.exe test json` **12 passed; 0 skipped; 0 failed**。
冒烟遗留：同工作区的 `libs/fmt` 去前缀（用户已改）仍报 `fmt/float.yh:218:35`
「未知类型」，与本批无关，属包内顺序问题（`float` < `model`）。

## 2026-11-06 删除过渡期自举桥：四端流水线切回 `just build`

**结果**：0.0.12 已发布四端种子（含 Windows 正常资产），种子认识 `windows`
comptime 标记、`*.windows.*.yh` 平台变体、`[link-windows-x64]` 清单节与
`.test.yh` 测试排序，过渡桥的存在前提消失：

- `.github/workflows/ci.yml`、`.github/workflows/release.yml` 四端 job 的
  「过渡期自举桥」步骤全部改回「冷编」`just build`；
- `justfile` 删除 `bootstrap-bridge` 配方与注释；
- 删除 `tools/ci-bootstrap.py`；
- AGENTS.md 的「过渡期（W2 种子）」条目替换为「种子门（不再需要过渡桥）」，
  「种子」条目去掉 0.0.11 Windows 过渡资产说明；docs/todo.md 删除
  「移除过渡期自举桥」与「Windows 种子过渡资产」两条。

本地验证：用 0.0.12 种子（`bin/yh-windows-x64`，sha256 `d6721853…` 同 rc.3 内容，
正式版资产已验证）在独立 worktree 跑 `just build` 冷编 → `yh --version`；
四端 `just build` 的真实门由 ci.yml 分支门确认。

## 2026-11-06 发布 0.0.12 正式版（rc.3 基线 + 发布二进制验收）

**结果**：GitHub Release
[0.0.12](https://github.com/lalavender/x/releases/tag/0.0.12)（正式版，非 prerelease）。
发布流水线 run 42081751704（tag `0.0.12`，commit `701f5ff`）**四端全绿**：
prepare / linux-x64 / linux-arm64 / darwin-arm64 / windows-x64 / publish 全部 success，
产出 8 个资产（四端 `tar.gz` + `sha256`，windows-x64 22.3 MB、darwin-arm64 23.3 MB、
linux 两架构各约 40.7 MB）。本次种子取 0.0.12-rc.3（首个带资产的候选），
所以四端都走「rc.3 种子 → 过渡期自举桥 → HEAD」链路。
分支：`0.0.12-rc`（候选，commit `f87a747`）`--no-ff` 合入 `0.0.12-release`（`701f5ff`），
tag 打在 release 分支上；`0.0.12-rc` 的 ci.yml 分支门同轮四端 success（run 42081736645）。

**发布二进制验收**（发版流程第 3 步，Windows/x64 宿主）：`just fetch-seed` 取 rc.3 种子
（sha256 `d6721853…`）→ `just build`（`yh --version` = `yh 0.0.12`）→ `just test`
（三层回归 + 554 条 PASS + `arch-check`）→ `just selfhost-native`（cc3→cc4 固定点
48 产物一致、自解析 148 文件、探针、CLI 冒烟、语法语料反例 49/49、运行语料
363/372 windows-x64 原生、modules 19/19、compiler-tests 4/4、project cases 130/130）。
本机两处垫片：`python3` 是 Microsoft Store 桩，用 `tmp/pyshim/python3.exe` 跑语料；
`foreign-fs-build.py` 受本机安全策略（不受信 exe 不能写 `%TEMP%`）限制，以 `TEMP`
指向仓库内目录等价通过，跨文件系统真值由 CI 承担。

**过程事故与修复**：`1927f95`（rc.3 结论文档提交）把当时暂存区里另一个任务的
`libs/json` 去前缀改名一并带进提交，导致 `json/api.yh:10` 早于 `types.yh` 引用
`Diagnostic`，llvm 分支门 run 42066720773 红灯。已用 `2281445` 把 `libs/json`
恢复到 `ab244e3`（tag 0.0.12-rc.3）内容，llvm 分支门 run 42075976931 恢复绿。
正式版基线取 tag `0.0.12-rc.3`（`ab244e3`），不含该误提交。

## 2026-11-05 发布打包步骤引用已删除路径：release.yml windows 端 cp 失败

**结果**：[release-0.0.12-rc.3](01-finished/release-0.0.12-rc.3.md)。
0.0.12-rc.2（run 41966728220）三端成功、windows-x64 在第 10 步打包失败：
`cp: cannot stat 'dist/selfhost/cc4': No such file or directory`。自举门本身全绿
（固定点一致 48 个产物、自解析 148 文件 OK、探针 OK、compiler-tests 4/4、
project cases 130/130）。根因是 windows job 的打包 shell 沿用了旧写法：
`cp "$cc4" yh` 之后执行 `rm -rf dist/selfhost`，随后又从 `$cc4` 复制到 stage，
源已不存在；linux/darwin 三端写的是 `cp yh "$stage/yh"`。日志中
`[ -f dist/selfhost/cc4 ]` 命中却 cp 失败，是 MSYS 的 `.exe` 后缀魔法（第一次 cp
实际产出 `yh.exe`）。已用本机 Git coreutils 复现旧写法报错、验证新写法打包成员名
为 `yh`；版本升 0.0.12-rc.3。rc.2 同时证明上一轮桥接修复有效（step 8/9 均 success）。
**rc.3 结果**：run 42062242047 四端全绿（windows-x64 步骤 8/9/10 全 success），
publish 成功，Release `0.0.12-rc.3` 已发布 8 个资产（四端 tar.gz + sha256）。
下一步是用发布出去的 rc.3 种子做 `rm -rf bin && just fetch-seed → just → just test →
just selfhost-native` 验收（见发版流程第 3 步）。

## 2026-11-05 发布流水线 Windows 端红灯：release.yml 漏接自举桥

**结果**：[release-0.0.12-rc.2](01-finished/release-0.0.12-rc.2.md)。
0.0.12-rc.1（run 41957530693）四端仅 windows-x64 失败，job 127015942985 的
「冷编」`just build` 报 `libs/cli/actions.test.yh:14:32: 错误: 未知类型（类型必须
先定义）`。根因是接线遗漏而非编译器缺陷：rc.1 的 `release.yml` 里 linux-x64 /
linux-arm64 / darwin-arm64 已改用 `just bootstrap-bridge`，只有 windows-x64 仍是
`just build`；0.0.11-windows 种子早于 2026-11-05 的 VTEST（`.test.yh` 改名、排序
前缀废止），按字典序把 `actions.test.yh` 排在定义 `pub struct Namespace` 的
`cli.yh` 之前。修法同 `ci.yml`：windows job 改走 `just bootstrap-bridge`
（staging 给 `*.test.yh` 临时加回 `zz_` 前缀），版本升 0.0.12-rc.2 并补发布说明。
同一条修法已在分支门 run 41954793463 四端验证。

## 2026-11-05 CI 二次红灯：Windows ACP 目录扫描（按 ACP 精确跳过）

**结果**：[yh-CI二次红灯-ACP目录扫描](01-finished/yh-CI二次红灯-ACP目录扫描-2026-11-05.md)。
`b6fafa7` 推上后 run 41952142547 的 windows-x64 **第 9 步已 success**（filter
修复在 CI 得到验证），三平台 job 全绿；第 10 步「自举主门」首次跑到（此前
5 次 run 全部 skipped），暴露 `build-check.py` 两个 R3 目录扫描用例在英文
runner（ACP=1252）必然失败：`FindFirstFileA` 把 `雪` 变 `?`、CRT `open()`
按 ACP 打不开。与 VENC-2 无关（本机 936 下修复前后编译器均 rc=0），是已登记
的「CRT 文件路径仍按 ACP」遗留。按用户决策用 `kernel32.GetACP()` 精确跳过：
仅当 ACP 无法编码该字符时 SKIP 两例，936/65001/932 仍照常实测；单测覆盖
四种 ACP + 手工对照。**这是隔离环境差异，不是修复**；根治（目录枚举改 W +
`_wopen`，或嵌入 UTF-8 manifest）升级为 todo.md 的 P1 项。

## 2026-11-05 VENC-2：Windows CRT 入口 argv 重建（CI filter 用例真正根因）

**结果**：[yh-VENC2-Windows-CRT入口argv修复-2026-11-05](01-finished/yh-VENC2-Windows-CRT入口argv修复-2026-11-05.md)。
CI run 41941536106 windows-x64 的 `test-check.py` list-filter/execute-filter
失败，根因不在零 CRT 入口桩（0b1ba2f/VENC 已修）：自举编译器链 libcmt，
入口是 CRT 的 mainCRTStartup，argv 经 `__getmainargs` → `GetCommandLineA`
按 ACP 取得——1252 上中文一步变 `?`，`/alternatename` 兜底只在无 CRT 时
生效（windows_link.yh 双形态入口，本机调试实锤 yh.exe 自身 argv 为 GBK
字节）。修复：新增 `gen/argv.{windows,linux,darwin}.yh`，Windows 在 main
最前用 `GetCommandLineW` + `WideCharToMultiByte(65001)` 原地重建 UTF-8
argc/argv（解析语义与零 CRT 桩一致；零 CRT 入口后为幂等直通；失败保持
原 argv），driver 先重建再消费。验收：test-check.py 38/38 全过（CI 上
36+2 失败），`just test` 除 arch-check 预算外全绿；预算上调
`max_module_lines` 461 → 469（driver +8 行：重建调用与注释）、
`max_globals` 172 → 174（argv.windows.yh 的 argv_line/argv_vec 两个静态
缓冲）。

## 2026-11-05 P0-B1：CI 自举桥适配 VTEST（Windows 纳入桥引导）

**结果**：[yh-CI自举桥VTEST适配-2026-11-05](01-finished/yh-CI自举桥VTEST适配-2026-11-05.md)。
`ci-bootstrap.py` 新增测试文件改名 staging（gen-1 临时 `zz_` 前缀，gen-2
原样 HEAD；纳入备份/恢复/崩溃恢复），Windows 宿主纳入桥引导（跳过变体/
标记/链接节改写）；`ci.yml` windows-x64 job 的 `just build` 切换为
`just bootstrap-bridge`。Windows 本机端到端两代自举 3m54s，产物与已滚
种子逐字节一致。Lane B 剩余：B3 CI 实跑（需推送）→ B4 Release → B5 删桥。

## 2026-11-05 P0-A：`--emit-asm` Windows 失败修复

**结果**：[yh-P0-emit-asm修复-2026-11-05](01-finished/yh-P0-emit-asm修复-2026-11-05.md)。
根因不在 MoveFileExA：探针矩阵定位到本机安全策略拒绝不受信任 exe 在
%TEMP% 创建文件（同旗标仓库目录成功）。修复：`--emit-asm` Windows 临时
目录改 CWD 优先 + TEMP 兜底（llvm_emit.yh）；桥 `publish_buffer` 失败点
带 errno 诊断（bridge.c，长期保留）。验收：llvm-architecture LA0 O0/O2
通过、固定点逐字节相同、种子重滚、`just test` 绿；`max_build_lines`
6976 → 6990。todo.md P0-1 已勾选。

## 2026-11-05 P0 收尾与发布顺序方案立项

**结果**：[yh-P0收尾与发布顺序实施方案](02-plan/yh-P0收尾与发布顺序实施方案-2026-11-05.md)。
取证收窄 `--emit-asm` 失败面（`out="-"` 只走 stdout `_write` 循环，不经过
mkstemp/MoveFileExA，聚焦 /MT 双 CRT 与 errno 诊断）；给出 CI 验收/删桥的
发布顺序线（B1–B6），并把 2026-11-05 `.test.yh` 改名 × 0.0.11 桥解析约束
的冲突解法（gen-1 staging 临时加回排序前缀）纳入。todo.md CI 段已挂方案链接。

## 2026-11-05 Windows 控制台中文显示（切 65001 码页）

**结果**：[yh-Windows控制台UTF8显示-2026-11-05](01-finished/yh-Windows控制台UTF8显示-2026-11-05.md)。
driver 启动时调 `gen.console_utf8_init()`（Windows：`SetConsoleOutputCP/
SetConsoleCP(65001)`，经 kernel32 extern；linux/darwin 空实现），
`chcp` 实测 936 → 65001 且会话保持，PowerShell 中文帮助/诊断不再乱码。
固定点逐字节相同，Windows 种子已重滚；`max_module_lines` 458 → 461。

## 2026-11-05 Windows 编译器产物改为 `yh.exe`

**结果**：[yh-Windows编译器产物yh-exe-2026-11-05](01-finished/yh-Windows编译器产物yh-exe-2026-11-05.md)。
实测 PowerShell 对无扩展名 `yh` 报「无法在管道中间运行文档」（进程未启动）；
justfile 的 `yh`/`yh_run` 在 Windows 宿主改为 `yh.exe`（种子名不变，
`bin/yh-windows-x64` 由 CreateProcess 调用不受影响）。PowerShell 实测
`.\yh.exe --version` 通过。

## 2026-11-05 测试文件统一 `.test.yh` 后缀（废止 zz_/99_ 前缀）

**结果**：[yh-测试文件test后缀-2026-11-05](01-finished/yh-测试文件test后缀-2026-11-05.md)。
编译器新增 `pj_name_is_test` + `pj_dir_less` 测试文件后置排序（VTEST）；
16 个测试文件改为 `<主题>.test.yh` / `tests.test.yh`；约定文档（编码规范、
test 测试布局）与全部引用同步。**两代自举**过渡：中间名 → yh-1 → 最终名 →
yh-2，固定点 yh-2≡yh-3 逐字节相同；Windows 种子已滚。
**⚠️ 跨平台窗口**：Release 旧种子构建本树会报「未知类型」，需协调发版。

## 2026-11-05 `yh --version` 版本编码进二进制

**结果**：[yh-版本编码进二进制-2026-11-05](01-finished/yh-版本编码进二进制-2026-11-05.md)。
`YH_VERSION_TEXT` 常量（cmdline）+ `--version` 参数（inherit 全覆盖，
不读 project.toml）；顺带修复 libs/cli `argument_from_row` 丢
`version_text` 的 bug（inherit 后回退 prog 名）并补回归测试；
arch-check 新增 toml↔常量版本一致性断言。`yh version` 子命令项目语义
不变。libs/cli 测试 55/55。

## 2026-11-05 P1：cmd 一命令一文件

**结果**：[yh-cmd一命令一文件-2026-11-05](01-finished/yh-cmd一命令一文件-2026-11-05.md)。
`cmd/` 重组为 10 文件：`driver.yh` 只剩分派，`api.yh` 删除，新增
`common.yh` + 8 个 `cmd_*.yh`；`api_*` 全部转模块私有，导出面只剩 `main`。
无行为变化（--timeout 校验、rc==2 用法补印、会话前奏次序均原样迁移）。
架构目标见 [yh-模块架构目标设计-2026-11-05](03-design/yh-模块架构目标设计-2026-11-05.md) §4。
`max_module_lines` 387 → 458（+71 全为文件头注释，逻辑行不变，边 55 不变）。

## 2026-11-05 SDK 迁移 vendor

**结果**：[yh-SDK迁移vendor-2026-11-05](01-finished/yh-SDK迁移vendor-2026-11-05.md)。
`compiler/{darwin,windows}-sdk` → `vendor/`（git mv 保历史；windows 侧先核对
未跟踪副本逐字节一致后去重）。同步编译器运行时查找（`darwin_link.yh`
suffixes、`windows_link.yh` prefixes）、justfile 5 处、tools 2 个、selfhost
测试 4 个、AGENTS.md。**实测**：清空 `YH_WINDOWS_SDK`/`YH_DARWIN_SDK` 后
仓库根 `yh` 经 exe 相对路径命中 `vendor/windows-sdk/lib` 完成链接并运行成功。
`compiler/` 回归纯 yh 模块目录。

## 2026-11-04 当前架构重新分析（只读取证）

**结果**：[yh-当前架构重新分析-2026-11-04](03-design/yh-当前架构重新分析-2026-11-04.md)。
`python tools/arch-check.py` 实测 **16 模块 / 134 文件 / 57,274 行 / 55 边，检查通过**。
对 10-25 基线的核心结论：B1（`proj` 1,396 行）/ B2（`link` 4,272 行）/ B1-4
（`gen.G()` 165 → 0）全部落地；`build` 单体 10,717 → 6,953 行。

- **新增顶格项两处**：`link` 4,272 = `max_link_lines`（W2 Windows 链接 +509 推满）、
  `parse/parse_expr.yh` 2,042 = `max_file_lines`；建议文件级拆分解除。
- **漂移复发**：`compiler/README.md` 10-27 人工同步后再次过期（仍写 13 模块 /
  53,545 行，缺 `proj`/`link`/`cmdline`）；建议把模块表纳入 `arch-check` 断言。
- **未动旧账**：`testkit → build` 仍有 13 处 `mb_*`/`cmd_*` 引用；五处契约常量
  仍分散（期间 `IR_FUNCTION_CACHE_VERSION` 1→2 兑现过一次升级成本）；
  `module_worker.yh:130` 废参数链待 C2。
