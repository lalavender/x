# todo

只记录**未完成**事项。已完成任务的历史与证据见
[finish.md](finish.md) 与 [01-finished/](01-finished/)；方案文档在
[02-plan/](02-plan/)，取舍见 [adr/](adr/)。

图例：P0 发布质量与主线；P1 标准库与工具链；P2 长期与按需；⏸ 用户暂缓；❓ 待决策。
已完成项一律删除（历史与证据见 `finish.md`、`01-finished/`），已表决不做的见文末。

- 添加string类型
- 添加类型推导
- 添加接口功能
- 添加错误，当前错误提示功能太简陋
- project.toml 添加[env]

## 2026-11-10 函数 IR 缓存缺编译器身份（P1，合并后暴露）

合并 0.0.14 后，**冷 `.build` + 旧全局缓存**跑 `just build` 会在
`libs/hash/api.yh:23:1` 报 `LLVM lowering sha256_init: 首片不支持此语句或表达式`
（首次复现时报在 `build/proj/api.yh:193:1` 的 `hash_init`）。实测边界：

- `YH_CACHE=off` 通过；`yh cache clean` 后默认缓存通过；新缓存目录
  两连跑（第二次冷编复用首轮写下的记录）也通过。
- 只删掉全局 outputs 里 8 个含 `sha256_init` 的 `HYFNC1` 记录后，
  报错顺延到 `sha256_update`：旧记录被 `ir_function_cache_merge` 接受后
  污染了模块，后续函数 lowering 才失败（错误信息把缓存问题误报成
  lowering 能力不足）。

根因假设（待确认）：环境键里的编译器身份来自
`support.ctl().ir_cache_salt` ← `bc().compiler_fingerprint`，若某条产出
IR 记录的路径上指纹未算（恒 0），不同编译器写的记录就会撞键。

- [ ] 环境键稳定混入编译器身份：确认 `mb_compiler_identity_ensure` 在所有
      产出/查找函数记录的路径上都已执行，必要时在 `mb_emit_module` 入口补。
- [ ] `ir_function_cache_merge` 把「记录不兼容」与内部失败分开：不兼容按
      miss 重 lower，且报告不要复用「首片不支持此语句或表达式」。
- [ ] 回归门：`just build` 后 `rm -rf compiler/.build` 再 `just build`
      （热全局缓存、冷项目缓存）。

## 2026-11-10 泛型 `$any` 类型变量与单态化（P0，规划中）

方案：[yh-泛型any单态化实施方案](02-plan/yh-泛型any单态化实施方案-2026-11-10.md)。
只支持 `$any`：一个函数内所有 `$any` 是同一类型，由实参推断，编译期展开为具体类型。

- [ ] 决策确认：单变量语义、「展开」= 生成具体函数（非内联）、G2 实例归属、
      struct 级泛型口径；更新架构 §8.3/§8.2 并立 ADR。
- [ ] G0 语法与类型变量地基：`yh.g4` 增 `'$' IDENT`（语义限定 `$any`）、`TY_PARAM`、
      pass1 模板登记、pass2 跳过模板体、误用诊断；门：`just test`。
- [ ] G1 同模块单态化：实参推断与一致性检查、实例符号/命名、合成 AST 函数身份、
      实例驱动、实例缓存跳过；run/fail 用例；门：`just test` + `just selfhost-native` 后滚种子。
- [ ] G2 跨模块与 `pub` 泛型：`.s.i` 模板条目 + 接口版本、复用 `.s.ct` 闭包、
      实例归属；`tests/modules/projects/generic/` 双模块验收。
- [ ] G3/G4 扩展与缓存：显式类型实参、`$any` 绑定 fn 类型、struct 级泛型、实例缓存键含绑定。

## 2026-11-10 Windows 同名模块 + 路径导入（P1，rc.2 暂跳）

`tests/modules/projects/dupmodseg` 的 `u8-dup-module-path-import` 在 Windows
上构建失败（`[编译] cache` 只调度一次，另一个同名模块的对象/接口缓存提交
缺失；macOS/Linux 通过）。rc.2 在 build-check 的 `WINDOWS_SKIP` 暂跳该例，
发布后需在 Windows runner 抓调度/产物日志修复，再移除跳过。

## 2026-11-10 标准库 api.yh 迁移后续（P2）

`libs/` 18 个模块的公开面已迁入各自 `api.yh`（见 finish 记录）；剩两项：

- [ ] 平台例外收敛：`os.DirReader`/`os.DirReaderResult` 各平台字段不同，若要
      进 `api.yh`，需要把平台专属状态藏到 `*void` 句柄后（设计任务，会改 API
      可观察布局）；`os.open_dir`/`next_entry`/`close_dir` 依赖这两个类型，
      随之才能移入。
- [ ] 刷新各模块设计文档（string/JSON/TOML/cli/memory/io/net/os/sys/fmt）
      的文件清单：pub 声明已迁 `api.yh`，旧清单只描述主题职责（文档任务）。

## 2026-11-10 编译器 api.yh 迁移后续（P2）

`compiler/` 18 个模块的公开面已迁入各自 `api.yh`（见 finish 记录）；剩两项：

- [ ] 刷新编译器模块设计文档的文件清单：`yh-架构设计.md`、`yh-模块职责-当前实现.md`
      等仍按旧文件布局描述（pub 声明已迁 `api.yh`，部分文件已删除）。
- [ ] `support/tables.yh` 的 `pub const DATA_STR_CAP` 例外：若要让该常量也进
      `api.yh`，需要让 CT 值调度支持跨文件的数组长度常量请求（编译期机制调整）。

## 2026-11-05 VENC-2 遗留：Windows CRT 层文件路径仍按 ACP（P1，CI 已条件跳过）

> 已完成部分见 [yh-VENC2-Windows-CRT入口argv修复](01-finished/yh-VENC2-Windows-CRT入口argv修复-2026-11-05.md)。
> **2026-11-05 升级 P1**：修好 filter 后 CI 首次跑到 `selfhost-native` 第 10 步
> （此前 5 次 run 全部 `step9=failure/skipped → step10=skipped`），暴露
> `build-check.py` 的 `r3-directory-filenames-are-byte-safe` 与
> `r3-directory-enumeration-grows-past-one-batch` 两例在英文 runner（ACP=1252）
> 必然失败：`FindFirstFileA` 把 `雪` 变 `?`，CRT `open()` 按 ACP 打不开。
> 已按 `GetACP()` 精确跳过（仅 ACP 无法编码该字符时；本机 936 / UTF-8 ACP
> 仍照常实测），**不是修复**，见 [CI 二次红灯处理](01-finished/yh-CI二次红灯-ACP目录扫描-2026-11-05.md)。

`gen/argv.windows.yh` 已把进程内 argv 统一为 UTF-8（`GetCommandLineW` →
65001），`--filter 中文` 等**参数文本**在 CRT 入口下也正确。但 CRT 的文件
API（`open`/`CreateFileA` 等）仍按进程 ACP 解释路径字节：

- 现象：本机（ACP=936）`yh --syntax-check "tmp/中文目录/探针.yh"` 在
  VENC-2 之前能读源文件（argv 是 GBK 字节、CRT 也按 GBK 解释），VENC-2
  之后 argv 是 UTF-8、CRT 仍按 GBK → `无法打开文件`；
- 这不是本次 CI 失败面：CI 全部路径为 ASCII；且修复前中文路径整体也不可用
  （源文件能开，但 `-o` 输出/链接阶段的中文路径必挂，实测
  `LLVM 产物链接失败: tmp/…/old.exe`）；
- 未做的原因：完整修复需要让整个 CRT 进程说 UTF-8（把 SDK 里现成的
  `lib/yh-utf8.manifest` 以 `/MANIFEST:EMBED /MANIFESTINPUT:` 接进 lld 链接，
  涉及项目链接层与固定点/多平台回归），或把所有 Windows 路径 API 逐个改成
  `*W` 版本，改动面与风险都超出「修 CI filter 用例」的范围；
- [ ] 待立项：嵌入 UTF-8 activeCodePage 清单（或等价的 CRT 层方案），补齐
      中文源码路径、`-o` 输出路径与诊断路径的 Windows 端到端验收用例。

## 2026-11-06 标准库去数字前缀（已落地，剩 CI 提示）

`libs/` 全部模块的源文件已改成语义名并保持「文件名字节序 = 编译顺序」：共享类型
文件统一叫 `base.yh`，其余按职责命名（json/fmt/io/toml/sys/os/net/string/libc）。
验收：`cd libs && yh test` 134 例全绿；`yh check --target` 四种 triple 通过；
`cd compiler && yh check` 通过。改名映射与证据见 [finish.md](finish.md)。

- [ ] **命名顺序错误的报错不可读（P2）**：顺序写错时只在用到未定义类型时报
      「未知类型（类型必须先定义）」，且位置落在使用方文件上，容易误判成无关回归。
      需要在 `parse/parse_type.yh` 的该诊断里补一句「模块按文件名字节序编译，
      被依赖类型应放在字节序更早的文件」。

## 2026-10-27 未使用函数检查（UF1）后续

UF1 已生效（`build/unused_function.yh`，见 [finish.md](finish.md) 与
[模块与包设计](03-design/yh-模块与项目管理设计.md)）。当前实现按「模块内出现过
同名标识符」判使用，方向是保守（宁漏报不误报）。

- [ ] **UF1 精确化**：把「按名字的 token 扫描」升级为「按解析身份的引用集合」，
  覆盖两个已知漏报：同名局部变量/字段遮蔽、递归但无外部引用的孤立函数。
  前置条件是把引用事实随函数级 check 切片携带（`check/checked_slice.yh`
  的 global 符号表已按名字重绑定，但正文命中时不做解析），否则增量构建会把
  活函数判死；`$f(...)` 编译期调用与生产构建的 `test` 正文也要单独补登记。

## CLI-R 遗留（2026-10-27 方案）

方案见[用 cli 标准库重写 yh 命令行](02-plan/yh-CLI用cli标准库重写实施方案-2026-10-27.md)：
声明与解析已收进 `libs/cli`，`driver.yh` 的手写扫描与逐行 `usage()` 已删除，
argv 形态与旧调用面逐字节等价。只剩下面一条观察项。

- [ ] **CLI-R1d lowering 聚合初始化（常见但不复现，降级观察）**：CLI-R1 期间
  `compiler/cmdline/`（2026-11-09 并入 `cmd/yh/`）的声明代码曾报「首片不支持此聚合初始化形态」（
  `lower/module_snapshot_lower_place.yh` 的 `checked_lower_aggregate_store` 返回非 0），
  当时靠把 `Value`/`Default` 先 hoist 到局部绕过。2026-10-27 复查：用
  `let spec cli.Argument = cli.option(...)` + `spec.default_value =
  cli.suppress_default()`、嵌套 `cli.default_of(cli.value_i64(0))`、以及
  `-o` + `dest` 的原始组合都无法在独立项目或 compiler 项目里复现（代码已改为
  hoist 写法，且 `compiler/.build` 已冷清）。**暂不作为缺陷推进**：保留 hoist 作为
  声明代码的推荐写法，若再次出现再按 lowering 缺陷立项并补最小用例。
  2026-10-28 起聚合存储的来源面已扩大（新增聚合三目与三目结果取址，
  `tests/yh-run/run/210` 覆盖调用/字段/下标/三目来源），复现概率进一步下降；
  如再现先看 `checked_lower_aggregate_store` 的来源分支。

## 编译器性能测试（2026-10-23 方案）

PF0–PF4 已全部落地（**不设硬门**，CI 只出报告与资产），口径见
[性能方案](02-plan/yh-编译器性能测试方案-2026-10-23.md) +
[归因口径](02-plan/yh-编译器性能归因口径-2026-10-26.md)，数字与留证见
[PF1b 基线](01-finished/yh-编译器性能基线PF1b-2026-10-26.md)、
[PF2 归因/失效矩阵](01-finished/yh-编译器性能归因与失效矩阵PF2-2026-10-26.md)、
[PF3 规模/并发](01-finished/yh-编译器规模与并发扩展PF3-2026-10-26.md) 与
[噪声校准与判定规则](03-design/yh-性能回归判定与噪声校准.md)。
当前基线：冷编 10.1 s / 全量重编 16.8 s / 热编 0.98 s / 单函数改动 3.6 s（O0，20 轮），
O0 冷编 worker 累计 23.5 s 里 lowering 66%、IR 构造 20%、内嵌桥 8%、前端 6%。

注意：各批次语料/二进制 SHA-256 不同（加打点、加 `YH_WORKERS`、期间另有会话改链接层），
报告里都有「批次身份」表——跨批只比段落结构与同批内比值。未完成：

- [ ] **PL1d2b `ir_verify` 内部（便宜的方案已排除）**：函数体 SSA 校验占
  verify_function 的 83%（2.97 ms/函数）。已实现并实测「值→类型表」+「值位置表」把
  两处 O(n²) 扫描降为 O(n)——verify 占 lowering **17.2% → 17.0%，无可测收益**，已回退
  （真实函数 100–500 条指令，扫描 <2%）。只剩两条路：① 换支配性算法
  （Cooper-Harvey-Kennedy / bitset 定点）；② 论证「发布构建关闭模块 verify」的替代门
  （它是 lowering 之后唯一语义兜底）。
- [ ] **PL3b cgroup 峰值**：Linux cgroup v2 `memory.peak`（需要可写 cgroup 层级）。
  **本机不可验证**（Darwin 无 cgroup），留到 Linux 宿主/容器里接；Darwin 侧只能采样。

### 首轮归因发现的优化项（2026-10-25，历史）

[归因分析](02-plan/yh-编译器性能分析-2026-10-25.md)给出冷编 26 s / 热编 2.4 s / 单函数
改动 7 s 的阶段归属：`capture`（函数级 IR 缓存序列化）占冷编 worker CPU 56%，
关闭后冷编 −46%；而增量场景实测命中 0%（IR）/ ≤9%（check）。

**2026-10-26 PF2 复测已改写这张图**：PC3 关掉冷编写缓存后，冷编 worker 累计 23.5 s 里是
lowering 66% / IR 构造 20% / 内嵌桥 8% / 前端 6%（见上面的 PF2 报告），
`capture` 不再是瓶颈。以下保留仍未关闭的项，按收益排序：

- [ ] **PC2d 按模块共享类型表**（取代 PC2c，格式 v3 级）：记录改为引用模块级类型池
  （池带版本/校验），目标把 25.1 KB/条降到 ~5 KB，capture 13.4 → 5–6 ms/条。
  依赖：类型池文件的原子提交与失效规则要一起设计。
- **2026-10-26 低负载复核（load≈4.5–5，见 [分析](02-plan/yh-编译器性能分析-2026-10-25.md) §14）**：
  冷编 11.2 s、全量重编（含写）**17.5 s**、热编 **1.14–1.21 s**、单函数改动中位 **3.9 s**、
  冷编后首次改 4.78 s。**热编 ≤1.5 s 与全量重编 ≤20 s 已达标**；单函数改动 ≤3 s
  受限于「模块级 `.o` + 每轮整模块 LLVM 发射」（模块重编 2.03 s 里大头在此），
  需要**函数级目标文件**才能再降，属结构性改动。PC3c 的实测收益只有 0.5 s
  （4.78 vs 4.27），不建议为它引入冷编后台补写。
- [ ] **PC4c scratch 复用前先查越界**：把 7 张临时表改成按模块复用时，`yh test` 的
  libs 构建会在 lowering 阶段失败（`memory/memory.yh:5:19 alloc`），机制未定位；
  重做前先给 `ir_fc_mark_symbol`/`ir_fc_visit_type` 加边界断言。注意 `reserve` 必须
  在取指针之前（扩容 realloc 会让旧指针失效）。
- [ ] **PC7 函数级目标文件（⏸ 暂缓）**：文件级对象撤销后，函数级 `.o` 是唯一
  更细的对象粒度；但桥调用/链接对象数量代价高，2026-11-06 决定先不推进
  （ADR-0020），单函数 ≤3 s 不再作为当前承诺。可行性见
  [架构设计 §4.6](03-design/yh-架构设计.md)。
  量化依据（PF2 + PL1）：O0 单函数改动 3.6 s 里，模块级 LLVM 发射（object）≈0.5 s、
  链接 ≈1.3 s，其余是 lowering/缓存合并；**O2 单函数改动 7.55 s，其中内嵌桥 3.59 s**
  （整模块 LLVM 优化被重跑）。方案 A（每函数一个 `.o`）或 B（桥批处理，需改桥 ABI →
  滚种子），工期按天计；落地前单函数改动停在 ~3.5–3.9 s（O0）/ ~7.5 s（O2）。
- [ ] **LC1 Linux 对等**：Linux 宿主的裸跑仍靠 `YH_LINK_RUNTIME_FLAGS`
  （`-lstdc++`/`-lpthread`/`-lxml2`…）。要么给 Linux 闭包生成对应的 `.so` 路径输入，
  要么把运行库参数换成清单键（2026-10-25 试过 `[link-options].runtime`，但当前
  种子不认该键，需先滚一代种子再落地）。验证：Linux 上
  `cd compiler && ../bin/yh-linux-arm64 build` 不设环境变量就能链接。
- [ ] **LC2 闭包清单门扩展到 Linux**：`tools/link-closure.py check --host …` 目前只
  接进 `make test-llvm-darwin`；Linux 的对应门未接（需先有 Linux 宿主记录验证）。
## 语言内测试（YT4 迁移与发版）

[设计提案](03-design/yh-test语言内测试设计.md)、
[实施分期](02-plan/yh-test分阶段实施方案-2026-10-23.md)与
[2026-10-25 迁移分析与决策](02-plan/yh-test语法迁移既有测试分析与规划-2026-10-25.md)
（取代 10-23 版）已整理。**YT0–YT3b、YT2d、YT1.1 与 YT4-P0～P7 已全部完成**：
每个标准库都有自己的测试文件（122 例），`just test-libs` 与主门全绿；
证据见 [YT4 收口与门禁验证](01-finished/yh-YT4-收口与门禁验证-2026-10-25.md)
与各阶段 `01-finished/yh-YT4-*.md`。以下只保留延后项。

- [ ] **YT2d-2 剩余**：函数级 IR 与 check 切片缓存仍未用于测试构建
  （缓存键不覆盖 `TK_TEST`），测试构建每次整模块重编。
- [ ] **D11 预期失败/诊断断言能力（另立项）**：为把 `tests/yh-run/fail`、
  `tests/fmt/interp.py` 等负例逐步收敛到 `yh test`，需要新增“编译必须失败且
  包含指定诊断片段”的测试能力；当前负例门继续外部运行。

## 版本与发布流程（P0 前置）

单主线：`llvm` 是唯一开发线与 GitHub 默认分支（2026-11-06 起），tag 直接打在主线上；
rc tag 发 prerelease 并带四端种子，正式 tag 必须落在 `llvm` 上。旧方案
[分版本 rc/release 分支发版流程](02-plan/yh-分版本rc与release分支发版流程方案-2026-10-21.md)
已退役，仅作历史记录。

**2026-11-06 已收口（原 R2/R4）**：`release.yml` 的 prepare 现在做三道校验——tag
形态、tag 与两处版本号（`compiler/project.toml` + `YH_VERSION_TEXT`）一致、正式 tag
必须在主线上；并新增 `workflow_dispatch`（`tag` + `dry_run`）用于演练。版本漂移
两处（`compiler/README.md`、`tools/compiler-performance.py`）已改为读清单。

- [ ] **V2 版本号单一真源（P2）**：`compiler/project.toml` 与
  `compiler/cmd/yh/cmd_base.yh` 的 `YH_VERSION_TEXT` 仍是两处手写（发布前由 CI 校验
  一致）。可选：构建期从 project.toml 生成常量，或反过来让 `--version` 读清单。
- [ ] **V4 分支与保护（P1）**：`<ver>-rc`/`<ver>-release` 已删除（2026-11-06），远端
  仍留遗留分支 `arm64`、`main`、`ci/github-actions`（都不是主线，推送仍触发分支门）；
  GitHub 分支保护是否要求 ci status（默认分支已是 `llvm`）未在仓库设置里确认。
- [ ] **V5 种子与发布资产一致性（P2）**：本机 `bin/` 种子可能停在旧 rc（实测
  `bin/yh-windows-x64` 是 `d6721853…`，官方 0.0.12 资产是 `8db806ab…`），
  "发布二进制验收"记录容易与实际种子对不上；取种后应核对 sha 与 Release 资产并把
  该断言写进验收脚本。

## P0 发布质量：平台、CI 与分发

> **交叉编译任务已撤下（2026-11-06）**：Linux→Darwin 交叉（用户程序与编译器
> 候选）、跨宿主自举与 Darwin 交叉边界相关条目已从本文件删除，等待重新立项。
> 重新计划时的现状取证：Linux 交叉产 Mach-O 对纯 `.yh` 程序可用（需显式 SDKROOT），
> 带 `[c] sources` 报「C 目标文件架构与当前 target 不符」、交叉产编译器候选与
> macOS→Linux 方向均不可用；细节见
> [Darwin 交叉遗留边界](03-design/yh-Darwin交叉编译遗留边界.md)
> 与[架构设计 §8.2](03-design/yh-架构设计.md)。

### B. 平台矩阵（原 F3/F4）

四格现状：Linux/x64、Linux/ARM64、Darwin/ARM64、Windows/x64 已交付（CI 四端绿、
种子随 Release 发布）；Darwin/x64 与 Windows/ARM64 未接入。交叉编译任务已撤下
（见本节前说明），因此 B2a 只在**原生 runner** 上验收。

- [ ] **B1a 零 CRT vs UCRT 决策（P0）**：用户程序现在只链 kernel32，
  `strtod/abs/cos/pow/lrint/dup2/system` 等 C 符号不存在 → `libs/math`
  （sqrt/sin/cos/pow）不可用，`tests/modules/build-check.py:189-211` 有 22 例
  `WINDOWS_SKIP`。两条路：(a) 保持零 CRT，用 yh 或 SDK 支撑对象逐个补（math 昂贵）；
  (b) 接 UCRT 导入库 `ucrtbase.dll`，一次解决但违反方案 D2（用户程序依赖 UCRT）。
  决策后删 `WINDOWS_SKIP`。
- [ ] **B1b Winsock 接线（P0，当前未登记）**：`libs/sys/socket.windows.yh` 与
  `libs/net/tcp.windows.yh` 一律返回 `-ENOSYS`，Windows 上 `net`/`http` 不可用。
  需要 WSAStartup、SOCKET 进 fd 表、`SO_*` 换 Winsock 取值、`ioctlsocket` 的非阻塞
  语义，并补 `// platform: windows` 的 loopback 用例（`net0`/`net1` 现被跳过）。
- [ ] **B1c COFF 整库加载 + Win32 导出面扩展（P2）**：
  `[link-options-windows-x64].whole` 被 lld-link 忽略（未实现 `/wholearchive`），
  当前靠「桥入口均被直接引用」绕过，裁剪清单会静默少符号；
  `vendor/windows-sdk/manifest.json` 只覆盖 KERNEL32 的 38 条导出，扩面需改 `.def`
  → 同步 `exports`/`def_sha256` → 重新生成 `.lib`，目前无成文流程条目。
- [ ] **B1d Windows 工程债（P1/P2）**：① windows job 补跑 `test-windows-target`
  （原排除理由是「`--emit-asm` stdout 在零 CRT 下不支持」，实测已可用，PE 目标门
  目前只有 linux-arm64 交叉侧覆盖）；② 补 Windows 性能基线（`perf.yml` 只有
  macos-15 一端）；③ `windows-2022` pin 的长期方案（闭包 CMake 生成器写死
  「Visual Studio 17 2022」，需改动态检测）。
- [ ] **B2a macOS/x86_64 原生接入（P1）**：目标与 SDK 已就绪（`gen/target_info.yh:24`、
  `ir/ssa_module_00_model.yh:173` 的 key=4、`libSystem.tbd` 的 `targets` 含
  `x86_64-macos`），缺的是接线：`[link-darwin-x64]` 链接组（`compiler/project.toml`
  只有 `link-darwin-arm64`）、x64 Darwin 闭包（`tools/llvm-darwin-host.py` 的
  `HOST`/`SDK_PREFIX` 写死 aarch64）、`tests/selfhost/darwin/llvm-darwin-*.py` 的 arm64 断言
  参数化、种子与取种（`justfile:78` 与 `tools/fetch-release-seed.py` 的 `PLATFORMS`）、
  Intel Mac runner job（`macos-13`，需确认支持窗口）。验收必须在 Intel Mac 原生跑
  + 原生自举，交叉产物不算数。
- [ ] **B2b Windows/ARM64 可行性立项（P2，先证明再动手）**：① 目标身份
  （`aarch64-pc-windows-msvc` 未登记：`target_resolve` 只认 x64、`target_host_info`
  的 windows+arm64 直接 `return -1`、IR 第二份目标表无 key=6）；② ABI（现有 win64
  分类按 x64 规则写死「1/2/4/8 字节→INTEGER，其余 MEMORY」，ARM64 的 HFA/寄存器
  规则不同，需 clang oracle 核对）；③ SDK（`manifest.json` 锁 `machine 34404`、
  `tools/windows-sdk.py` 的 `VALID_MACHINES` 只认 `0x8664`、`chkstk.c` 是 x64 asm）；
  ④ arm64-windows 目标包（LLVM/lld/桥）；⑤ GitHub `windows-11-arm` 托管 runner
  可用性（硬前置，可能直接卡死）。

### C. 分发与工具链体验

- [ ] **C3 SDK 27 兼容**：内嵌 lld 21 解析不了 `arm64e.x1` TAPI；升级固定 LLVM
  或按实际 SDK 裁剪目标列表。
- [ ] **C4 `make dev` 增量**：归档身份目前按路径计，SDK 原地重建需清缓存或补
  内容哈希。

### D. CI 与本地环境

- [ ] **D2 CI 去重后的四端实跑（P1）**：门禁与打包已收进 justfile（`just ci-gate` /
  `just release-asset`，本机 darwin-arm64 已验：全门绿 + 资产可解包执行）。待真 runner 确认：
  下一次 push 到 `llvm` 的 ci 四端全绿；`release.yml` 用 `workflow_dispatch` +
  `dry_run=true` 演练一轮（linux-x64 的 `test-llvm`、linux-arm64 的 Windows 目标门、
  windows-2022 pin、artifact 路径改用 prepare 输出的 tag，这四处只有真 runner 能验）。
- [ ] **D1 本机 ANTLR jar**：`make test` 第 1 层需要本地
  `antlr4-*-complete.jar`；WSL 已配置，macOS 按同一方式补齐或文档化安装。

## P1 标准库与工具链

### E. os/sys 与 libc

- [ ] **E1 OS7 编译器迁移与独立性审计**：编译器改用 `libs/os`/`libs/sys` 的
  接口，减少对 C runtime 的隐式依赖；见[联合设计](03-design/yh-os与sys标准库设计.md)。
- [ ] **E1.1 OS7 第一切片：显式依赖与时钟/目录迁移**：给 `compiler/` 增加
  `yh_libs` 显式依赖；把 `compiler/cmd/clock.linux.{arm64,x64}.yh` 与
  `project_dir.linux.{arm64,x64}.yh` 迁到 `libs/sys`/`libs/os`；验证宿主
  编译器 I/O 与输出目标隔离，更新缓存/种子身份。
- [ ] **E1.2 OS7 第二切片：文件/进程与独立性**：迁移编译器剩余文件、worker、
  fork/exec/wait 调用；审计普通 syscall 程序与嵌入 LLVM 编译器的依赖清单，
  区分宿主与目标，补独立性验收。
- [ ] **E1.3 浮点字面量解析去 libc**：`compiler/gen` 的十进制常量改用宿主
  `strtod`（正确舍入，修复 1 ULP 偏差）；E1 迁移 libs/os 时补纯 yh 等价实现
  或改用 `libs/num`，并保持 `tests/yh-run/run/float-literal-rounding.yh` 全绿。
- [ ] **E2.1 OS8 Darwin 文件 API**：新增 Darwin `file` 平台实现与即时 errno
  桥，覆盖 open/read/write/close/mkdir/remove/rename、CLOEXEC 与错误分类；
  原生用例与 Linux 契约对齐。
- [ ] **E2.2 OS8 Darwin 目录/进程/时间**：目录枚举（getattrlistbulk）、
  cwd、spawn/wait/exit 与时钟/睡眠的 Darwin 适配；逐项原生门并披露
  libSystem/dyld 依赖。
- [ ] **E3 独立产物与消费者审计**：普通 ELF/syscall 程序与编译器分别列出
  运行时依赖，完成 SYS5–SYS6 的消费者迁移、固定点与独立环境验收。
- [ ] **E4 libc L0–L5**：按[分阶段候选方案](02-plan/yh-libc分阶段候选方案.md)
  推进，未授权全部实施。

### cli 标准库复核遗留（2026-10-27）

只读复核覆盖 `libs/cli` 生产代码 12 文件；已完成死代码清理、argparse 对齐批 1
（语义：`set_default` 未声明 dest、位置 `optional` 默认值、槽 token 预留、
`store_const` const 校验、位置参数 `required` 校验、默认值不参与 choices）与
批 2（展示：choices `{a,b}`、`metavars`、槽 `{a,b} ...`/`title`/`description`/
`metavar`、`boolean_optional` usage、`max_help_column`）、批 3（诊断：choices/子命令
候选列表、`suggest_on_error` 覆盖 choices 与子命令、多余 token 全量列出）与
CLI-B（`put_*` 短路契约、溢出 return resource_error）、CLI-D（构造器合并、诊断码
常量、参数文件上限常量、测试助手复用 `libs/string`），见 [finish.md](finish.md)。
以下为剩余项。

- [ ] **CLI-C 文件与函数超规范**（2026-10-27 用户决定：**暂不拆文件**，后续再做）：
  `help.yh` 1,685 行、`schema.yh` 1,067 行
  （规范 500–1000）；>100 行的函数 4 个（`build_help_text`、`parse_layer`、
  `add_argument_internal`、`build_usage_line`）。切分点已在分节注释里：`help.yh`
  的拼接/转义/颜色/模板、`schema.yh` 的 `copy_*`/`check_freeze`；`MAX_HELP` 常量
  应随其余容量常量回到 `cli.yh`。
- [ ] **CLI-G 帮助宽度自动（依赖编译器先行）**：缺省固定 80（argparse 取终端宽度
  −2）。2026-10-27 实测确认 libs 层做不了：Darwin 的 `ioctl` 是 C 变参入口，而
  `@[extern]` 只支持定参，实参被放进寄存器导致 EFAULT（证据见
  [finish.md](finish.md) 同日条目与 `libs/sys/file.darwin.yh` 的边界说明）。
  2026-10-27 用户决定：**暂不动编译器，只保留本条记录**。
  落地路径：1) 在 `compiler/backend/llvm_runtime.yh` 追加弱符号
  `yh_terminal_columns()`（内部按正确变参 ABI 调 `ioctl(TIOCGWINSZ)`，两平台各自
  请求号）；2) `libs/os` 加薄封装 `terminal_columns() int`；3) `HelpFormat.width = 0`
  改「自动 = 列数 − 2，取不到回落 80」并补 pty 下的可复现门禁。

### NET/HTTP 网络与 HTTP 标准库（2026-10-24 决策完成；NET0–NET1 已交付，HTTP2–HTTP7 待实施）

[设计](03-design/yh-http标准库设计.md)与
[ADR-0018](adr/0018-yh网络与HTTP标准库分层.md)已定稿。仓库此前无任何 HTTP
实现，`libs/sys` 无 socket 原语、`libs/os` 明确不承诺网络，故按
「sys socket → net → http」三级推进。已确认：**首期含服务端**、**TLS 走可选
`libs/tls`（系统 OpenSSL）**、**DNS 纯 yh**、**并发后置**、**`Date` 先补
`time`**、**不用 libcurl**。头字段零拷贝借用读缓冲，body 增量读，不提供整块
`read_all`。

NET0/NET1 已完成（`net0-sys-socket-loopback`、`net1-net-tcp-loopback` 与
`yh test net` 全部通过，见 [finish](finish.md)）：`libs/sys` 提供 12 个
socket/poll 原语与两平台常量；`libs/net` 提供 Endpoint 解析/格式化与 TCP
dial/listen/accept/read_some/write_some/write_all/shutdown/close。实测确认
Darwin 无法在 yh 层切非阻塞（`fcntl` 是 C 变参），因此 connect 超时只在
Linux 生效；`read`/`write` 与 prelude 重名，net 用 `read_some`/`write_some`。

- [ ] **HTTP2 模型与解析/序列化**：设计 §7 的 12 条 RFC 规则正反例、chunked
  状态机、`Io` 内存源离线测试；与 Python 参考实现逐字节比对。
- [ ] **HTTP3 客户端**：`Target`（endpoint/host/tls）、keep-alive 复用、body
  增量读、100-continue、可选重定向。
- [ ] **T1 `time` 墙上时钟与 IMF-fixdate**（HTTP4 前置）：`wall_ns()` 走
  `sys.read_clock(CLOCK_REALTIME)`，`format_imf_fixdate()` 含公历换算；
  `monotonic_ns` 契约不变。
- [ ] **HTTP4 服务端**：串行 accept、Responder、内建 400/413/431/501、
  keep-alive、`Date` 头；README 写明单连接队头阻塞与适用范围。
- [ ] **HTTP5 DNS**：纯 yh UDP 解析器 + `/etc/hosts` + `/etc/resolv.conf`；
  poll 精确 deadline。
- [ ] **HTTP6 TLS**：`libs/tls` + 系统 OpenSSL（定参 `@[extern]`）、客户端
  SNI/证书/主机名校验、服务端证书链载入、`io_from_tls`；自签 fixture 五类
  用例在 Linux 与 Darwin 各跑一遍。
- [ ] **HTTP7 文档与门禁**：README/doc.yh/`examples/http-demo`/
  `make test-http`/finish 记录。
- [ ] **后置（不排期）**：`serve_fork`/poll 事件循环等并发标准库落地后再补；
  可选 `libs/curl` 互操作模块（HTTP/2、代理、cookie、压缩场景），不得进入
  `libs/http` 依赖图。

### MEM 内存管理标准库（2026-11-08 设计第三版；T1–T3 待实施）

[设计](03-design/yh-memory标准库设计.md)已改为第三版：第二版（2026-10-23）的
M0–M6 六个阶段自设计至 2026-11-08 **零切片落地**，判定为范围过大；
第三版收敛为 **T1–T3 三个必做切片**，`FixedPool`/`Allocator` 降为「有消费者
才做」的按需层（P4/P5）。保持 `alloc`/`release`/`copy` 签名不变；块统一取自
prelude 堆，不新增 `sys` 依赖，不改 `string`/`toml`/编译器，不替代 `libc`。

- [ ] **T1 `reallocate` + 模块文档**：`memory.yh` 追加 `reallocate`（`data=0`
  等价 `alloc`；`new_size=0` 释放；按 `min(old,new)` 复制后释放旧块；失败保留
  旧块）；新增 `libs/memory/{README.md,doc.yh,memory.test.yh}`，断言覆盖
  `alloc(0)` 非空、16 字节对齐、超长请求返回 0、`release(0)`、增长/缩小/
  `data=0`/`new_size=0`/失败保旧块。验收 `just test-libs`（O0+O2）。
- [ ] **T2 FixedBuffer**：新增 `libs/memory/{base.yh,fixed_buffer.yh}`；
  绝对地址对齐（16/64/256）、空间不足返回 0、最近分配 resize/free、
  非最近缩小 resize=1 但不回收、`reset`/`owns`/`capacity`/`used`、0 长度。
  验收 `just test-libs`。
- [ ] **T3 Arena**：新增 `libs/memory/arena.yh`（`Arena` + `ArenaResetMode`
  + 块映射）；单块/跨块、几何增长（1.5 倍）、64/256 对齐、非法对齐与溢出返回 0、
  最近分配 resize/free、`reset(free_all/retain)`、`capacity`、
  `MEMORY_TEST_FAIL_AFTER` 注入（失败保留旧内容）。验收 `just test-libs`。
- [ ] **P4 FixedPool（按需）**：触发条件为出现固定块大小高频申请/归还的消费者；
  当前 `toml`/`cli` 各有私有池，本设计不迁移。
- [ ] **P5 `Allocator` vtable（按需）**：触发条件为多容器共享接口、
  Arena 用 FixedBuffer 作 child；函数指针字段可用（`libs/cli` 有先例）。
- [ ] **E4 配对**：libc 分配器与 prelude 的配对（见 E4），不得跨入口释放。

注：第二版的 [实施方案](02-plan/yh-memory标准库实施方案-2026-10-23.md) 按 M0–M6
编号，与第三版的 T1–T3 不一致——以设计文档第三版为准，方案文档待 T1 落地时
同步改写或归档。

### IO 字节流标准库（2026-10-24 设计；IO0–IO4 已完成）

[设计](03-design/yh-io标准库设计.md)与
[方案](02-plan/yh-io标准库实施方案-2026-10-24.md)已把 `libs/io` 从"只有四个写侧
接口"扩展为完整读写层：`read_all`/`read_file`/`write_bytes`/`write_file` 与调用方
缓冲的 `Reader`/`Writer`（行读取、显式 flush），保留
`write_all_result`/`write_all`/`print`/`println` 原签名。`libs/io/tests.test.yh`
7 个用例通过，`yh test io` 已接入 `make test`/`make selfhost-native`/
`just test-libs`。以下只留未完成项。

- [ ] **IO5 toml 读文件迁移**：删除 `libs/toml/file.{linux,darwin}.yh` 的手写
  短读循环，改用 `io.read_file`；保留 `TOML_MAX_INPUT` 上限语义与
  `parse_io_error`/`parse_resource_error` 分类映射，先加断言锁定"恰好读满"与
  "还有数据"的现有区分，再迁移。验收 `just test-libs`。
- [ ] **IO6 seek/copy（依赖 os）**：`os` 补 `lseek`/`fstat` 后再评估 `Reader` 的
  peek/seek 与零分配 `io.copy`；先出设计增量，不提前对外承诺。
- [ ] **IO7 消费者迁移审计**：`cli/help.yh`、`examples/os-demo` 与编译器读文件的
  手写循环是否改用 `io`，逐处评估（编译器侧属 OS7 显式依赖，另行安排）。

### MATH math 纯 yh 标准库（2026-10-23 方案；P0 已完成）

[方案](02-plan/yh-math标准库实施方案-2026-10-23.md)按用户决定改为**纯 yh
实现**：不用 `@[extern]`/libm，函数名与 `<math.h>` 一致；算法移植
fdlibm/musl，位级函数正确舍入，f32 复用 f64 内核。P0 探针已确认普通
`pub fn` 的 mangled 符号、私有 const 数组/递归/二进制 stdout、并集位模式，
以及 `pub const f64` 导出损坏与极端十进制字面量偏差。以下只留未完成项。

- [ ] **P1 位级/精确层与谓词**：`00_bits/05_predicates/10_exact/15_round/
  20_fmod` 的 f64+f32；`mathpredicates`/`mathexact` 夹具、`tests/math/run.py`、
  `make test-math`、build-check 登记；0 ULP 差分。
- [ ] **P2 根与 fma**：`01_fma/25_sqrt`；sqrt/sqrtf 位相等，cbrt/hypot ≤1 ULP，
  fma <1 ULP。
- [ ] **P3 指数/对数**：`30_exp/35_log`；上溢/下溢/次正规边界，最大 ULP <1。
- [ ] **P4 幂**：`40_pow`；C 附录 F 特殊值逐条断言，常规区间 <2 ULP。
- [ ] **P5 三角/反三角**：`44_rem_pio2/45_trig/50_inverse_trig`；Cody-Waite
  与 Payne-Hanek，大参数与 `atan2` 象限。
- [ ] **P6 双曲/误差/伽马**：`55_hyper/60_erf/65_gamma`；极点、负半轴、
  溢出边界。
- [ ] **P7 贝塞尔/旧名/收口**：`70_bessel/75_legacy`、`doc.yh`/`README.md`、
  surface 全调用、`nm -u` 无数学符号、O0/O2 与 Linux 容器差分。
- [ ] **P8 公共 f64 常量（后置）**：修 `iface_emit_const_value` 浮点分支并扩展
  `pubconst` 项目，再交付 `INFINITY/HUGE_VAL/NAN/M_*`；不修则常量不交付。

### TOML 标准库（2026-10-23 设计；T0–T5 reader 已完成）

用户已确认**完整 TOML 1.1 reader 优先、写入后置**。`libs/toml/` 已交付完整
reader，T0–T5（含 T4.1 分配失败/预算门与 T5.1 安装导入）已完成并记录在
[finish](finish.md)；固定 toml-test v2.2.0（1.1 清单）681/681、124 个池分配
失败点、低预算门与仓库外导入均已通过。以下只保留未完成项。

- [ ] **T5.2 发布资产是否携带标准库**：三端 Release 资产当前只含 `yh`，
  标准库由 `make install` 分发；是否改发布策略需单独决定，未在 TOML 实现中
  擅自改动。
- [ ] **T6 编译器迁移（独立切片）**：显式标准库依赖、保留清单 schema、递归文档
  生命周期、缓存与种子冷编/两代固定点；全迁移后删除旧解析器。
- [ ] **T7 生成器（后续按需）**：独立构建/编码契约与 encoder 验收；保真编辑另立项。

### JSON 标准库（2026-10-24 设计；J1–J3/J6 已实现，J4/J5/J7 待做）

[设计](03-design/yh-JSON标准库设计.md)、
[方案](02-plan/yh-JSON标准库实施方案-2026-10-24.md)与
[ADR-0019](adr/0019-yh-JSON标准库独立文档模型与词素保真数字.md)已落地首期：
`libs/json/` 12 个源文件（reader + writer + 查询 + 文件读写），
`libs/num/` 提供十进制 ↔ binary64 与最短往返格式化；
六组断言已迁入 `libs/json/tests.test.yh`（12 个 test / 127 条断言，见
[迁移记录](01-finished/yh-YT4-P1-json迁移-2026-10-25.md)），`jsonmodel`
保留为 `build-check.py` 的公开面 smoke；原 `tests/json/run.py` 与
`make test-json` 已删除，由 `yh test json` / `just test-libs` 取代。口径：
RFC 8259 完整语法 + 严格 profile（拒绝 BOM/重复键/孤立代理/尾逗号）；
单一 `kind_number` 且保存原始词素；文档模型与 `toml` 独立。
以下只保留未完成项。

- [ ] **J4 预算与失败原子性**：深度/字节/有效位上限已实现并有断言；缺
  `JSON_TEST_FAIL_AFTER` 池分配失败注入与低预算门（新建
  `tests/json/injection.py` 与 `make test-json-injection`）。
- [ ] **J5 一致性与差分**：`jsontestbridge`（stdin→退出码）、固定 JSONTestSuite
  提交（`y_` 全接受、`n_` 全拒绝、`i_` 逐条登记）、Python 差分（值树 + 浮点
  位模式）、`jsonroundtrip` 组、`make test-json-conformance`。
- [ ] **J7-2 收口剩余**：`tests/json/install.py` 仓库外导入门、
  `make test-json-install`、`docs/finish.md` 流水与 `01-finished/` 交付记录。
- [ ] **J8 后置候选**：JCS 规范模式、大对象哈希索引（`JSON_HASH_THRESHOLD`
  已预留）、流式 SAX、JSON Pointer；均需实测或真实消费者触发。
- [ ] **N1 `libs/num` 反向迁移**：`libs/toml/numbers.yh` 改为调用
  `num.parse_f64`，以 toml-test 681/681 与注入门为阻断条件；当前为不触碰已
  验收语料而暂缓。
- [ ] **N2 后端限制回访**：当前编译器对超长函数体、部分调用语句形态与
  "调用结果直接赋给字段"有限制（种子与 HEAD 均有），JSON 库已按小函数规避；
  修好后可放宽实现风格，不影响公共 API。

### FMT fmt 运行时与 V 风格插值（2026-10-23 改版；I5 可选扩展未做）

用户决定：字符串格式化采用 V 式插值 `"…${expr:spec}…"`，结果为
`string.String`；首版不实现 Go 的 `%` 格式串与 `Printf` 族（是否保留为
次级 API 待确认）。语言设计见
[字符串插值设计](03-design/yh-字符串插值设计.md)，运行时见
[fmt 标准库设计](03-design/yh-fmt标准库设计.md)，
[方案](02-plan/yh-fmt标准库实施方案-2026-10-23.md)列出 R0–R3（fmt）与
I0–I5（语言）；R0–R3 与 I0–I3 已实施，语言插值已端到端可用。fmt 不改
prelude `printf`（H.I3 的按需扩展仍独立）。

- [ ] **I5 可选扩展**：嵌套插值、运行时 width/precision、`r/R`、
  `string.View`/`string.String`/enum 名称、fmt 别名导入；每项单独立项。

### G. C/C++ 桥迁移到 yh

见 `docs/01-finished/` 的 C/C++ 重写历史记录（原独立分析文件已缺失，按需从 git 历史取回）。

- [ ] **G1** 迁移 `compiler/llvm/bridge.c` 到 yh（LLVM 生命周期、初始化同步、
  有界诊断、原子发布），补正式 `.yh` 对等用例与错误路径。
- [ ] **G2** `lld_bridge.cpp` 的配置/argv/库搜索移到 yh，保留 `lldMain` 最小
  C++ 适配层与不可重入状态处理。
- [ ] **G3** 桩的构建期择一机制；迁移前保留 C 弱桩，避免重复强符号。
- [ ] **G4** SDK 身份、归档成员与自举闭包同步，候选引导后滚种子。

### H. 编译器可选收尾

- [ ] **H1 字符串字面量只读化**（2026-10-26 已决定：改语义）：字面量符号发
  `constant` 进只读段（`backend/llvm_module.yh:385` 已按 `mutable` 选
  `global`/`constant`，只需把 `lower/module_snapshot_static.yh` 的字面量登记
  `mutable` 置 0）；能静态判定的写入改为编译期诊断——先覆盖 `"abc"[0] = …` 与
  字面量绑定的局部别名（不经函数边界），与 comptime 的「字面量字节池只读」
  口径统一（`tests/yh-run/fail/147-comptime-string-const-write.yh`），逃逸到
  函数边界后的写入退化为运行期崩溃。
  实测依据（2026-10-26）：运行期现在允许且生效（`let p *char = "abc";
  p[0]='z'` → `zbc`），仓库运行语料无依赖；`__data` 实测 hello-world 14 B、
  `./yh` 93 KB（每进程至少省一个 16 KB 页，字面量页可跨进程共享）。
  验收：`tests/yh-run/fail/` 加直接写用例、`tests/yh-run/run/` 加只读访问用例，
  `make test` + `make selfhost-native` 全绿后滚种子。
- [ ] **H4 LLVM 闭包缓存路径迁移**：缓存里的 `selfhost-flags.txt` 仍存绝对
  路径，整个缓存目录被搬走或换机器时需要重写或重新 `make llvm-host`；
  `YH_LLVM_CACHE` 自动定位已完成，此项只保留路径可迁移性。
- [ ] **I1 MOD-U6**：远程来源、版本规则、锁文件与工作区，按实际需求另立设计与
  验收（不沿用旧 Go 方案承诺）。
- [ ] **I2 VS Code 扩展**：VS-U0 最小扩展与 LSP → VS-U1 保存后诊断与取消 →
  VS-U2 未保存缓冲与精确跳转 → VS-U3 调试信息与 DAP → VS-U4 集成测试与发布。
  见[方案](02-plan/yh-VSCode扩展方案.md)。
- [ ] **I3 R3 剩余**：printf 按需扩展（宽度/精度/浮点）、完整 OS 导入清单审计
  （`nm -u` 允许清单）；线程 API 已并入「后续任务」。
- [ ] **I4 编译器缺陷清单**：11 项已全部修复或复核为不再复现；新缺陷按
  「先复现、再红绿回归、后修」入本清单。
  - [ ] **I4-1 非 void 函数末尾缺少 return 的诊断误导**（2026-10-22 记录）：
    `fn main() int { printf("Hello, World!\n") }` 报
    `LLVM lowering main: 首片不支持此语句或表达式`，位置指向最后一条语句的
    实参 token（使用例的位置看起来像 printf 不支持）。原因：
    `checked_lower_function` 在 `status == 1 && (ret != ir.IR_TY_VOID ||
    aggregate_return != 0)` 时返回 -2，但返回前没有设置 `l.reason` 与
    `l.last_token`（`compiler/ast/module_snapshot_lower.yh` 约 3698 行），
    沿用默认文案。复现：`examples/ex1.yh`（缺 `return 0`；补上即通过）。
    期望：报「非 void 函数末尾缺少 return」并把位置指到函数体收尾；先加
    `tests/yh-run/fail/` 用例（用 `// fail-contains:` 锁新文案），再改文案，
    跑 `make test` + `make selfhost-native`。**附**：`examples/ex1.yh` 是照搬
    C 的 hello world，已补 `return 0`（已提交）。
  - [ ] **I4-2 极端十进制浮点字面量不精确**（2026-10-23 math 探针）：
    `1e300`、`1e-300`、`1.7976931348623157e308` 与正确位型不等，
    `2.2250738585072014e-308` 是 DBL_MIN+2 ULP，`5e-324` 直接变 0；
    π、0.1、1.5 精确。影响所有数值代码，纯 yh math 只能用位模式构造常量。
    修复：前端十进制→f64 改为正确舍入（Eisel-Lemire/strtod 路线），补
    `tests/yh-run/` 极端指数字面量用例，先红后绿。
  - [ ] **I4-3 `pub const f64` 跨模块导出损坏**：`.s.i` 把浮点位型当整数写出，
    导入侧报「浮点与整数之间需要 .to_type 显式转换」。修复：
    `parse_global_init` 保存浮点初始化式文本，`iface_emit_const_value` 增加
    浮点分支；扩展 `tests/modules/projects/pubconst/`。math 的
    `INFINITY/NAN/M_*` 等常量依赖此项。
  - [ ] **I4-4 `!bool` 在 bool 返回位置退化为 i32**：`fn f(b bool) bool {
    return !b }` 报「整数不能隐式转为 bool」；条件位置正常。修复：
    `sem_unary` 对 bool 保留 `TY_BOOL`（或写进语义边界），补 run/fail 用例。
  - [ ] **I4-5 `@[inline]` 无后端效果、IR 内联器未接线**：`F_INLINE` 只在
    parse/iface 使用，`compiler/ir/ssa_inline.yh` 没有调用点，跨模块也无 LTO。
    影响纯 yh math 的小函数与 O0 性能。修复：把 `@[inline]` 降为 LLVM
    `alwaysinline`，或让模块接口携带可内联体；再决定是否启用 IR 内联器。
  - [ ] **I4-6 能力文档漂移**：`compiler/README.md` 的浮点参数边界与
    `compiler/gen/target.yh` 的 emit_arm64 说明仍指旧后端；`libs/libc/README.md`
    称函数指针不支持（LLVM ABI 已支持）；`AGENTS.md` 的 x64 种子说明与
    Makefile 现状不一致。按实际行为刷新或标为历史。

## 后续任务：线程池与性能（LA5）

LA0–LA3 已完成，历史与证据见 [finish.md](finish.md) 与
[01-finished/](01-finished/)；LA4 文件对象已按 ADR-0020 撤销，以下只保留
未完成项。

- [ ] **J4 / LA5 线程池**：按
  [架构设计 §1.4/§4.5](03-design/yh-架构设计.md)
  收口 FrontendTask/AstStore/CtContext/CacheContext/Diagnostics，再接宿主线程桥
  与固定线程池；完成前继续 fork/COW，不宣称线程安全。
- [ ] **J5 增量/冷编时间**：单函数 200ms、冷编 1s 目标未达；当前仍整模块
  lowering 与内嵌 LLVM 对象生成，耗时占比交专门性能任务重测；对象粒度固定
  模块级（ADR-0020）。旧外部汇编器的耗时解释不适用于 LLVM 唯一后端。
- [ ] **J6 产物体积：fmt 闭包不再放大成品**（2026-10-27 立项）：把「输出全部走
  fmt」后的体积回落到 printf 基线上。实测（macOS/arm64，hello 级程序，O0）：
  printf 单文件 50,256 B / `__text` 1,872；fmt 项目 155,872 B / 85,032；
  `-dead_strip` 后 89,632 B（−42.5%）；O2+`-dead_strip` 后 54,616 B（+8.7%）。
  主因不是 fmt 代码规模，而是「模块整对象链接 + 无死代码回收 + O0」。
  L1（Darwin `-dead_strip`）、L3（O2 缺省开优化）、L4（release `-x` 剥离）已落地：
  fmt hello 由 155,888 B 降到 53,424 B，与 printf hello 的比值 **1.063**。
  - [ ] **L2 后续（Linux 端到端）**：在 Linux CI 上量 ELF 的 `--gc-sections`
    实际回收率，并按需调整；本地容器运行时不可用（`container run` 启动即报错）。

## 接口特性（IF1–IF5，方案待评审）

2026-10-24 取向已定：**显式 vtable 语法糖、零运行时魔法**——interface 展开为
`self` + 方法函数指针字段的普通 struct，impl 只做编译期检查，`s.m()` 是
`s.m(s.self)` 的糖。方案见
[接口特性实施方案](02-plan/yh-接口特性实施方案-2026-10-24.md)；按片立项，
实施顺序 IF1 → IF2 → IF3 → IF4/IF5。

- [ ] **IF1**：`interface` 关键字、类型登记（form=4、隐含 `self *void`）、
  方法槽必须是 fn 类型的检查。
- [ ] **IF2**：`s.m(args)` 插接收者糖（旧发射路径与 AST/lower 路径行为一致），
  首版接收者限变量名；comptime 内显式拒绝。
- [ ] **IF3**：`.s.i` v4（interface 发射/加载）与跨模块构造/调用用例。
- [ ] **IF4**：`impl` 纯检查（全方法覆盖、签名严格相等）、缓存与固定点复核、
  `docs/yh.g4` 与语义边界文档刷新、ADR。
- [ ] **IF5**：`tests/yh`、`tests/yh-run/{run,fail}`、`tests/modules` 门禁用例。

## 待决策（❓）

当前无未决项。2026-10-26 用户已决定两项，记录如下。

- **NP 定位（原 ❓1，已决定并已收口）**：**只保留 NP3**（受检契约与 lowering
  解耦），NP0/NP1/NP2/NP4/NP5 关闭——NP0 口径并入现有 `just test` + O0/O2 +
  自举门；NP1/NP2 的对象代码（`ir_simplify`、`ssa_inline`）已删除；NP4 由
  ADR-0014 取代；NP5 交 LLVM 默认管线。ADR-0011 已标注部分被取代，
  [方案](02-plan/yh-Nanopass风格优化架构实施方案.md) 与
  [架构设计 §7](03-design/yh-架构设计.md) 已记录。NP3 已于 2026-10-28
  关闭（覆盖矩阵零被拒，证据见 finish.md 与
  [能力矩阵](03-design/yh-受检到LLVM能力矩阵.md)），本文件不再列其子项。
- **字面量只读化（原 ❓3，已决定：改语义）**：字面量进只读段 + 静态可判定的
  写入改编译期诊断，见 H1。

## 设计决定不做（非缺口，勿列为任务）

- **编译器模块 worker 上限（原 TG-3）**：`active < 4` 保持 ADR-0009 的过渡默认；
  实测放宽到 8 每次冷编只省 5–8s，峰值内存从约 490MB 升到约 800MB，收益不足。
- **批量 `--syntax-check`（原 TG-4）**：并行后只再省十几秒，性价比低。
- **用户裸 C 变参**：不开放 `printf` 等裸变参互操作；yh runtime `printf` 继续使用
  现有规则。
- **切片越界与生命周期运行时防护**（ADR-0001）。
- **`pub const A *char = base.TEXT;`（初始化式为模块限定名）**：名字池无限定名，
  只取尾段会指向本模块同名符号，属错误语义（编译期第 7 条）。
- **经指针写入编译期模型**（`&TABLE[0]` 后 `*p = 5`）：保持只读拒绝（fail/153）。
- **顶层 const 折叠 `$mk()[0]`**：前端折叠路径无法索引裸聚合对象指针；惯用写法
  `const T = $mk(); T[0]` 可用，不为此加特殊形态。
- **恢复 `asm/`、`link/` 独立项目**：2026-10-20 用户决定删除，由 LLVM + 内嵌 lld
  取代，不重建。
- **文件级对象缓存（C5/LA4）**：2026-11-06 用户决定撤销；对象粒度停在模块级，
  增量由函数 check/IR 缓存承担，后端继续整模块发射（ADR-0020）。
- **自研机器 IR / 寄存器分配 / 动态加载 libLLVM**：与 ADR-0014 冲突；JIT、LTO、
  32 位、ARM64EC 等无消费者扩展同样不做。
- **以 WSL 代替 Windows 原生支持**：B1 需 Windows 原生构建与运行。
- **固定 SDK 预编译分发（原 C1）**：2026-11-03 用户决定闭包不上传 Release，
  由构建机经 `just llvm-host` 自行准备；代价是冷启动成本（见「Windows 闭包 CI
  冷启动成本」）。
