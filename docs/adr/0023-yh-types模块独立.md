# ADR-0023：`types` 模块——语言类型模型独立

日期：2026-11-10。状态：**已实施**。

关联：[ADR-0021](0021-yh-gen职责拆分.md)（support/check 归属）、
[架构 §3.1 允许依赖边](../03-design/yh-架构设计.md)。

## 背景

`support` 是历史沉淀的「共享数据层」：基础设施（缓冲/名字池/诊断/目标）、
语义存储（`ModelStore`）、前端瞬时态（`FrontCtx`）、平台变体全部混在一个模块。
其中语言类型模型是一组**纯数据**：`TY_*` 类型种类常量、`CType`（类型表行）、
`SField`（字段表行）、`TName`（具名类型行）。它们不依赖任何其它模块，
却被 30 个文件以 `support.TY_*` / `support.CType` 的形式消费（约 530 处），
让「support 是叶子」的边界承担了不该承担的语义词汇。

## 决定

新增叶子模块 `compiler/types/`（`module types`），只放语言类型模型：

- `TY_*`（20 个类型种类常量）；
- `CType` / `SField` / `TName` 三个结构体；
- 不持有存储实例，不提供表操作（增删/布局仍在 `support.ModelStore` 与 `check`）。

依赖方向：

```text
types → （无）           新建叶子
support → types          ModelStore 的类型/字段/名字表字段引用 types.*
ast/builtin/check/lower/parse → types   直接使用 TY_* 与结构名
```

- `support` 仍是「只依赖底座」的共享层，但底座从「无」变为 `types`/`errors`；
- `ModelStore`、`CSym`、作用域栈、`Res`、ABI 分类结构（`ABIValue` 等）、
  `TargetInfo` **不迁**：它们是存储机制/语义结果/目标描述，不是语言类型定义；
  整搬 `ModelStore` 会牵动约 480 处 `ms()` 调用并把符号表塞进 `types`，
  属另一次语义存储重设计。
- 消费者统一改限定名（`support.TY_*` → `types.TY_*`），不在 `support` 保留
  转发别名——避免同一常量两个名字。

## 备选与被否决的方案

| 方案 | 结论 | 理由 |
| --- | --- | --- |
| 留在 `support` | 否决 | 类型模型与诊断/缓冲/平台混层，边界继续含混 |
| 连 `ModelStore`/`CSym` 一起迁 | 否决（本次） | 符号表不是类型；约 480 处 `ms()` 调用点属独立的重设计 |
| `support` 转发 `pub const TY_X = types.TY_X` | 否决 | 同一常量两个名字，消费面长期分叉 |
| 把 ABI 分类结构也放进 `types` | 否决 | ABI 分类是目标相关机制（仅 check/abi_c 消费），不是语言类型 |

## 后果

- 模块数 18 → 19；`types` 成为新的零依赖底座，`support → types` 是唯一新增入边。
- 类型模型的唯一真源在 `types`；`.s.i`/`.s.ct` 编码值不变（常量值逐一保持）。
- `tests/modules/build-check.py` 中所有复制 `compiler/support` 的 fixture 同步复制
  `compiler/types`，并在子项目清单补 `types` 依赖。
- `tests/tools/front-coupling/check.py` 的 support 反向依赖守卫不变（`types` 不在
  禁止集合内）；后续可把「support 只允许 types/errors」写进该守卫。