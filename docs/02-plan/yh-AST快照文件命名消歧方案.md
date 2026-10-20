# AST 快照文件命名消歧方案

日期：2026-10-20。状态：已完成。

## 目标

将 `compiler/ast/` 中以 `checked_module` 起名的快照所有权与 lowering 文件改用
`module_snapshot` 前缀，避免与新建的 `compiler/check/` 校验模块混淆。此项只改文件名、
源码注释和文档引用，不改公开类型/API 名称与运行行为。

## 文件映射

| 现名 | 新名 | 职责 |
| --- | --- | --- |
| `checked_module.yh` | `module_snapshot.yh` | 快照类型、深拷贝、释放与有界访问 |
| `checked_module_view.yh` | `module_snapshot_view.yh` | 向 `check` 借出快照只读视图 |
| `checked_module_ctx.yh` | `module_snapshot_ctx.yh` | lowering 临时上下文类型 |
| `checked_module_lower.yh` | `module_snapshot_lower.yh` | 快照到 IR 的主体 lowering |
| `checked_module_forin.yh` | `module_snapshot_forin.yh` | `for-in` lowering 辅助 |
| `checked_module_global.yh` | `module_snapshot_global.yh` | 全局对象 lowering 辅助 |
| `checked_module_static.yh` | `module_snapshot_static.yh` | 静态数据与重定位 lowering 辅助 |
| `checked_module_template.yh` | `module_snapshot_template.yh` | 编译期 `$for` 模板 lowering 辅助 |

`compiler/check/checked_module.yh` 是实际校验器，名称保留；`CheckedModule`、
`checked_module_capture`、`check.verify_checked_module` 等 API 名称也保留，因为它们
准确描述数据类型或操作。

## 编译顺序与验证

所有新文件沿用相同的 `module_snapshot` 前缀和后缀排序，保持基础类型、上下文类型、
辅助函数与 lowering 主体的词典序编译关系。同步更新源码注释和当前模块 README，
历史完成记录中的旧文件名保留为当时的名称。

在 Apple Container Linux/arm64 运行 `make`、`make test`、`make selfhost-native`；
确认九模块固定点、`llvmchecked` 与 `llvmlower` 项目用例通过，不覆盖种子。三项
门禁均退出 0；固定点 129 项产物一致，自解析 107 个源文件，模块用例 18/18，项目
用例 106/106。`make test` 语法正例 78/78、反例 42/42，运行语料 344/349（5 项
平台跳过）、fail 132/132、pass 8/8、代码统计 6/6。Linux/arm64 种子哈希保持
`8ea2a9acc20438b385ccddd522b50b8dd4749423c8db2695c758296ada343b8c`，未滚种子。
项目验收脚本临时 fixture 同步使用 `module_snapshot_fixture.yh`，确保快照类型声明
按文件名字典序先行编译。

完成记录：[AST 快照文件命名消歧](../01-finished/yh-AST快照文件命名消歧-2026-10-20.md)。
