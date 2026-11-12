# yh 当前架构模型 · 证据索引

- 快照：2026-11-10，`llvm` 分支，HEAD `13d3bd4`，**含未提交的 errors 重构工作区改动**
  （`git status`：约 35 个文件修改、`compiler/support/diag.yh` 删除、
  `compiler/errors/render.yh` / `api.test.yh` 新增未跟踪）。模型以**工作区代码**为准。
- 产出技能：`system-modeler`（场景）+ `c4model` / `graphviz`（图源格式）。
- sourceRefs 均为仓库相对路径，可直接解析；行号以快照时刻为准。
- 置信度：high = 代码/配置直接证据；medium = 多处间接证据一致；low = 推断；unknown = 待验证。

## 1. L1/L2 节点（system-model.dsl）

| ID | 节点 | 类型 | 置信度 | sourceRefs |
| --- | --- | --- | --- | --- |
| actor.developer | yh 开发者 | actor | high | README.md:22-56；justfile:9-25 |
| sys.github | GitHub Releases / Actions | external-system | high | .github/workflows/ci.yml:59-186；.github/workflows/release.yml:1-17；tools/fetch-release-seed.py |
| sys.host-sdk | 宿主平台 SDK | external-system | high | justfile:214-224（SDKROOT 回退）；justfile:199-203（Windows 导入库） |
| sys.antlr | ANTLR 参考语法 | external-system | high | justfile:209-212,427；.github/workflows/ci.yml:56-57（YH_ANTLR=0） |
| sys.user-project | 用户 yh 项目 | external-system | high | README.md:58-96；docs/03-design/yh-模块与项目管理设计.md:273 |
| sys.yh | yh 编译器工具链（系统边界） | system | high | docs/03-design/yh-架构设计.md:63-79（复合体边界表） |
| container.compiler | yh 编译器单二进制 | container | high | compiler/project.toml:1-6；compiler/cmd/yh/yh.yh:14-131 |
| container.stdlib | 标准库 yh_libs | container | high | libs/project.toml:1-32；compiler/project.toml:19-20（依赖声明） |
| container.seed | 上一代种子 | container | high | justfile:74-90；bin/yh-darwin-arm64（实物）；docs/03-design/yh-架构设计.md:115-132 |
| container.closure | LLVM/lld 静态闭包 | container | high | compiler/llvm/bridge.h:10-30；compiler/project.toml:26-762（[link-*] 归档清单）；justfile:299-317 |
| container.orchestrator | justfile + tools 编排 | container | high | justfile:1-47（唯一真源声明）；.github/workflows/ci.yml:10-13 |
| container.tests | 测试套件 | container | high | justfile:426-438（test 配方）；tests/ 目录（yh/yh-run/modules/selfhost/…） |
| container.cache-store | 构建缓存 | container(database) | high | compiler/build/cache/api.yh:1-5；AGENTS.md 缓存节（YH_CACHE 布局 v1/actions+outputs）；justfile:128-138 |

## 2. L1/L2 关键边

| 边 | 类型/协议 | 置信度 | sourceRefs |
| --- | --- | --- | --- |
| developer → compiler | CLI 调用 | high | README.md:75-96；compiler/cmd/yh/yh.yh:107-128（分派） |
| developer → orchestrator | just 调用 | high | justfile:263-264（default: dev）；AGENTS.md 构建与测试节 |
| compiler → user-project | 读源码/清单，写 .build | high | docs/03-design/yh-编译流程-当前实现.md:19-43,107-120 |
| compiler → stdlib | 三层来源解析 import | high | docs/03-design/yh-模块与项目管理设计.md:132-134,273；compiler/project.toml:19-20 |
| compiler → closure | 进程内 C ABI | high | compiler/llvm/bridge.h:19-30；compiler/backend/api.yh:1-4 |
| compiler → host-sdk | 平台链接回退 | high | justfile:214-224（Darwin -lc++ 由真实 SDK 解析） |
| compiler → cache-store | 文件读写 | high | compiler/build/cache/api.yh；docs/03-design/yh-编译流程-当前实现.md:30-39 |
| orchestrator → seed | HTTPS 取种 | high | justfile:291-292；tools/fetch-release-seed.py |
| seed → compiler | 种子冷编 compiler/ | high | justfile:277-286；tools/seed-build.py |
| orchestrator → closure | 平台准备器 | high | justfile:299-317（macos/linux/windows 三实现） |
| orchestrator → tests → compiler | 子进程驱动 | high | justfile:426-438,476-491 |
| tests → antlr | 本机参考语法层 | high | justfile:427；ci.yml:56-57（CI 关闭） |
| orchestrator → github | 取种/发布 | high | tools/fetch-release-seed.py；tools/publish-release.py；release.yml:1-9 |
| github → orchestrator | Actions 调 just ci-gate | high | ci.yml:83-84,111-112,143-144,185-186；release.yml:7-9 |

## 3. compiler/ 模块节点与 import 边（compiler-modules.dot）

模块声明均为各目录 `api.yh:1`（`cmd/yh` 声明 `module main`）。边证据为各 api.yh
头部 import 及实现文件补充 import（2026-11-10 工作区逐文件核实）。

| 模块 | 声明证据 | 依赖（代码实测） | 依赖证据 |
| --- | --- | --- | --- |
| errors | compiler/errors/api.yh:1 | ∅（最底层） | errors/api.yh:6-9 注释 + 全文无 import |
| support | compiler/support/api.yh:1 | errors | support/api.yh:3 |
| token | compiler/token/api.yh:1 | errors, support | token/api.yh:3-4 |
| ir | compiler/ir/api.yh:1 | ∅ | ir/api.yh:1-8 无 import |
| lex | compiler/lex/api.yh:1 | errors, support, token | lex/api.yh:3-5 |
| cache | compiler/build/cache/api.yh:1 | token, hash(libs), support | build/cache/api.yh:3-5 |
| proj | compiler/build/proj/api.yh:1 | support, token | build/proj/api.yh:3-4 |
| comptime | compiler/comptime/api.yh:1 | errors, support, token | comptime/api.yh:3-5 |
| ast | compiler/ast/api.yh:1 | token, errors, support, proj, comptime | ast/api.yh:3-7 |
| check | compiler/check/api.yh:1 | errors, support, token, ast, ir, proj, cache, comptime | check/api.yh:3-10 |
| parse | compiler/parse/api.yh:1 | errors, support, token, check, lex, comptime, ast, ir, proj | parse/api.yh:3-11 |
| builtin | compiler/builtin/api.yh:1 | check, support | builtin/api.yh:3-4 |
| lower | compiler/lower/api.yh:1 | ir, check；实现层另 + token, support, ast, proj, cache | lower/api.yh:3-4；lower/module_snapshot_lower.yh:2-8 |
| backend | compiler/backend/api.yh:1 | support, ir | backend/api.yh:3-4 |
| link | compiler/link/api.yh:1 | support, backend, proj, hash(libs) | link/api.yh:3-6 |
| build | compiler/build/api.yh:1 | cache, support, proj, link, hash, ir, token, lex, parse, ast, check, builtin；实现层另 + comptime, lower, backend, libs.os | build/api.yh:3-14；build/module_worker.yh:2-11；build/llvm_pipeline.yh:2-8；build/cache_admin.yh:6 |
| testkit | compiler/testkit/api.yh:1 | token, ast, support, build, parse, proj, link | testkit/api.yh:3-9 |
| main | compiler/cmd/yh/api.yh:1 | libs.cli, support, build, proj, lex, check, parse, testkit, link | cmd/yh/api.yh:3；yh.yh:2-4；common.yh:2-6；cmd_single.yh:7；cmd_test.yh:3；cmd_init.yh:3 |

非 import 边：

| 边 | 类型 | 置信度 | sourceRefs |
| --- | --- | --- | --- |
| backend → llvm 桥 | extern C ABI（进程内静态链接） | high | compiler/llvm/bridge.h:19-30；backend 分工表 docs/03-design/yh-模块职责-当前实现.md:98-112（llvm_bridge.yh 绑定） |
| cache/link/build/main → yh_libs | 跨包 import（三层搜索命中直接依赖 libs） | high | 上表对应行；docs/03-design/yh-模块与项目管理设计.md:132-134 |
| main → build/testkit | 命令分派（进程内调用） | high | compiler/cmd/yh/yh.yh:107-128；cmd_build.yh:13；cmd_test.yh:17 |
| build → fork worker | 进程 spawning（≤4，COW） | high | docs/03-design/yh-架构设计.md:90-91,134-139；yh.yh:30-38（--emit-module/--lld-link 无 fork 回退协议） |

分层基准（L0–L6）与三条不可违反约束：docs/03-design/yh-模块职责-当前实现.md:13-25,92-96。
注意该文档的分层表未含 errors（见 §6 冲突 1）。

## 4. libs/ 模块节点与 import 边（stdlib-modules.dot）

各模块声明为同名 `module`（各 api.yh:1；string/memory/testing 已抽查确认）。
边证据来自 SearchWorkspace 对 api.yh 头部与平台实现文件的核实：

| 模块 | 依赖 | 代表证据 |
| --- | --- | --- |
| sys / memory / num / math / libc / hash / testing | ∅（叶子） | 各 api.yh 无 import |
| string | memory | libs/string/api.yh:3 |
| list | memory | libs/list/api.yh:3 |
| os | sys | libs/os/api.yh:3 |
| time | sys | libs/time/time.linux.yh:3 |
| io | os | libs/io/api.yh:3 |
| net | os, string, sys | libs/net/api.yh:3-4；net/tcp.darwin.yh:4 |
| fmt | string, os, io | libs/fmt/api.yh:3-4；fmt/output.yh:3 |
| cli | os, io | libs/cli/api.yh:3-4 |
| json | num, string, memory, os | libs/json/api.yh:3-4；json/serialize.yh:3；json/stream.darwin.yh:3 |
| toml | os | libs/toml/file.darwin.yh:3 |

注册表：libs/project.toml:18-32 的 [lib] 仅 14 项（os/io/net/math/sys/time/cli/libc/toml/num/json/fmt/hash/list）；
string/memory/testing 未列入（见 §6 待验证 4）。平台差异经 `*.darwin.yh`/`*.linux.yh`/`*.windows.yh`
后缀在构建期选择（知识卡 + net/tcp.darwin.yh 等实物文件）。

## 5. 假设与低置信度项

| 项 | 置信度 | 说明 |
| --- | --- | --- |
| 「开发者」是唯一人类 actor | medium | 仓库证据只有开发者工作流；无其他角色证据 |
| 用户项目作为 external system 建模 | medium | 它是编译器的输入/输出对象而非独立系统；C4 中按外部依赖处理 |
| x86_64-apple-darwin 目标 | unknown | README.md:117：triple 被接受但未验证、CI 不覆盖；未画入确认路径 |

## 6. 证据冲突与待验证项（不是评审发现，不做 remediation）

1. **errors 重构进行中（工作区未提交）**。`compiler/errors/api.yh` 已成为统一诊断基座，
   support/token/lex/parse/check/comptime/ast 均已 import errors；`support/diag.yh` 已删除。
   而 docs/03-design/yh-模块职责-当前实现.md:13-25 仍写「support 与 ir 无依赖」、17 模块不含 errors。
   模型按代码现状建模；errors 节点在 DOT 中标注「工作区新增，未提交」。
   验证：重构提交后刷新模块职责文档与本模型。
2. **版本号来源位置冲突**。YH_VERSION_TEXT 现定义于 compiler/cmd/yh/api.yh:35（"yh 0.0.14"），
   cmd_base.yh:77 只是消费方；但 .github/workflows/release.yml:88 的 sed 仍从 cmd_base.yh 提取，
   AGENTS.md 版本节也写 cmd_base.yh。0.0.14 发布早于 api.yh 迁移 commit 8a398d0。
   验证：下一次 tag（或 workflow_dispatch dry_run）前确认 prepare 能否读到版本号。
3. **AGENTS.md 的 cmdline 模块已过时**。AGENTS.md 写 CLI 声明在 compiler/cmdline/（module cmdline）；
   该目录已不存在，声明并入 main（docs/03-design/yh-模块职责-当前实现.md:6「cmdline 已并入 main」；
   compiler/cmd/yh/api.yh:3 import libs.cli）。
4. **string/memory/testing 未注册 [lib]**。三模块存在且被项目内 import（net→string、json→memory 等），
   但 libs/project.toml:18-32 未列登记。项目内解析与对外暴露是两回事；
   验证：编译器/用户项目能否 `import string`（三层搜索的依赖层是否要求 [lib] 注册）。
5. **README 版本滞后**。README.md:9 写「当前版本 0.0.12」；compiler/project.toml:5 与
   cmd/yh/api.yh:35 均为 0.0.14。
6. **分层规则无机器门禁**。tools/arch-check.py 已于 2026-11-09 删除
   （yh-模块职责-当前实现.md:5,24-25；yh-架构设计.md:17-20），L0–L6 与三条硬约束仅靠评审。
   本模型的模块边是快照实测，不构成持续校验。