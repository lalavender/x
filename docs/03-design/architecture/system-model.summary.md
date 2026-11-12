# yh 当前架构全景 · 模型总结

快照：2026-11-10，`llvm` 分支 HEAD `13d3bd4` + 未提交 errors 重构（工作区）。
产出：`system-modeler` 场景技能 + `c4model` / `graphviz` 图源技能。
本文是阅读入口；逐节点/逐边证据见 [system-model.evidence.md](system-model.evidence.md)。

## 系统边界

yh 不是单个编译器目录，而是「语言 + 前端 + SSA IR + LLVM 后端 + 构建系统 + 标准库 +
自举/发布流水线」复合体（docs/03-design/yh-架构设计.md §1.1）。系统边界内六个单元：

1. **yh 编译器**（单二进制）：CLI 分派、受检前端、SSA IR、LLVM IR 发射、构建编排、
   链接驱动全部在一个可执行文件里；因此不能作为库内嵌，IDE/LSP 只能走子进程协议。
2. **标准库 yh_libs**：独立 project.toml 项目，源码形态随编译器分发，经
   「本项目 → 标准库 → 直接依赖」三层搜索接入。
3. **上一代种子**：bin/yh-<平台>-<架构>，不入库，从最新带资产 Release 下载。
4. **LLVM/lld 静态闭包**：compiler/llvm C/C++ 桥 + 固定版静态归档，构建机准备，
   不烘焙进种子、不上传 Release。
5. **构建与门禁编排**：justfile 是唯一真源，tools/*.py 做实际执行；
   两个 GitHub workflow 只调 `just ci-gate`，不各自维护门禁清单。
6. **测试套件**：Python harness 驱动 .yh 语料，覆盖语法/运行/模块/自举固定点/平台专项。

另有一个存储单元：**构建缓存**（项目 .build/ + YH_CACHE 全局内容寻址 store）。

外部：开发者、GitHub Releases/Actions、宿主平台 SDK、ANTLR 参考语法（仅本机）、
用户 yh 项目。

## 关键关系

- **自举闭环**：orchestrator 取种 → 种子冷编 compiler/ 源码 → 新 yh；
  两代固定点（cc3/cc4 模块对象逐字节相同）是滚种子的前置门。
- **一次构建**：main 分派 → build 扫描/解析/拓扑 → fork worker（≤4，COW）
  逐模块 lex→parse→check→lower→backend→桥发射 .o → 父进程 link（内嵌 lld）。
  无 fork 宿主走 --emit-module / --lld-link 子进程协议。
- **编译器 ↔ 标准库**：compiler 自身也消费 libs（build→hash/os、main→libs.cli），
  经依赖三层搜索解析，不是源码直接引用。
- **模块分层**：L6 main/testkit → L5 build → L4 link → L3 backend →
  L2 parse/builtin/lower → L1 check/comptime/ast/proj → L0 support/token/ir/cache/lex/errors。
  依赖只向下；三条硬约束（support 叶子、comptime 不依赖 check、lower 不回依赖 parse）
  目前仅靠评审——arch-check.py 已于 2026-11-09 删除。

## 证据强度与未知

- 模块 import 边全部经工作区代码逐文件核实（high）；L1/L2 关系有 justfile/清单/
  workflow/设计文档多重证据（high）。
- **errors 是进行中的未提交重构**：代码已是统一诊断最底层，但模块职责文档未收录；
  模型按代码建模并在图中标注。
- 主要待验证项：release.yml 版本号提取路径与 api.yh 迁移后的实际位置冲突；
  libs 的 string/memory/testing 未在 [lib] 注册时的对外可导入性；
  x86_64-apple-darwin 目标未验证（未画入确认路径）。完整清单见 evidence §6。

## 阅读顺序与文件

| 顺序 | 文件 | 内容 |
| --- | --- | --- |
| 1 | [system-model.dsl](system-model.dsl) | C4 模型真源：SystemContext（L1）+ Containers（L2）两视图 |
| 2 | [compiler-modules.dot](compiler-modules.dot) | 编译器 18 模块 + C 桥 + libs 的 import 依赖图（省略 →support/errors/token 公共边） |
| 3 | [stdlib-modules.dot](stdlib-modules.dot) | 标准库 17 模块分层图 |
| 4 | [system-model.evidence.md](system-model.evidence.md) | 逐节点/逐边 sourceRefs、置信度、冲突与待验证项 |

可视化查看：用 Qoder 的 Structurizr DSL  viewer 打开 system-model.dsl，
用 DOT viewer 打开两个 .dot（均为 rankdir=TB，适配 Canvas 竖向预览）。
本机未安装 graphviz 命令行，未生成 SVG 导出；图源即真源。

## 维护

- 代码为准：errors 重构提交、版本号来源修复、[lib] 注册变化后，先改证据索引再改图源。
- 模块边可用 `compiler/*/api.yh` 头部 import 快速复核；规模数字以 `just code-stats` 为准。
- 本模型只描述当前状态；目标架构（S1–S4 前端两遍化切片等）以 docs/todo.md 与
  docs/02-plan/ 为准，不混入本模型。