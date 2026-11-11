# ADR-0024：`support` 再收缩——FileScope→proj、front_stage/ABI 分类→check

日期：2026-11-10。状态：**已实施**。

关联：[ADR-0021](0021-yh-gen职责拆分.md)（support/check 归属）、
[ADR-0023](0023-yh-types模块独立.md)（types 拆分）、
[架构 §3.1 允许依赖边](../03-design/yh-架构设计.md)。

## 背景

`types` 拆出后，`support` 仍持有三簇「support 自己不做、只对外提供」的数据/守卫：
文件作用域（`FileScope/ImportEnt/ModNsEnt/ModInfo` + 名字查找）、受检前端阶段守卫
（`front_checked_*`）、C ABI 分类模型（`ABIValue/ABICursor/ABIArg/CABI_*`）。
判据：**support 自身消费的簇不能上移**（会成环）；只定义不被 support 调用的簇可以
搬到语义/数据层。

## 决定

### 1. 文件作用域整簇 → `proj`（数据层）

- 迁移：`ImportEnt` / `ModNsEnt` / `ModInfo` / `FileScope` 结构（`proj/model.yh`）、
  单例 `g_fscope`、`fs()` / `fscope_reset()` / `mod_file_binding*` /
  `mod_ns_lookup*` / `mod_import_find`。
- 环：support 内 28 处 `fs()` 全部属于该簇；迁出后 support 不再依赖它。
  `proj → support` 已有，消费方（parse/check/build）都已依赖 proj（6 个文件补 import）。
- `FileScope.sym_sfx_off/len` **不随迁**：符号后缀是模块构建态，拆到
  `support.ModuleSym`（`msym()`），由 ModuleJob 写入、接口发射读取。
- `proj.init()` 负责 `fscope_reset()`；测试 fixture 在 `support.session_reset()`
  之后补 `proj.fscope_reset()` 保持原语义。

### 2. 受检前端阶段守卫 → `check`

- `front_checked_begin/verify/end` 迁到 `check/front_stage.yh`；
  `SessionCtx.front_checked` 字段仍由 support 持有（check 读写 it）。
- 调用方只有 `build`（worker 入口与发射路径），build 已依赖 check。

### 3. C ABI 分类模型 → `check/abi_c.yh`

- `ABIValue` / `ABICursor` / `ABIArg` + `CABI_*` 种类常量迁到 `check/abi_c.yh`
  （文件名字节序必须早于 `check/api.yh`，否则类型先用后定义）。
- 消费方只有 check（`abi_c.yh` + `api.yh` 的 `abi_c_cursor_init/abi_c_place`）。
- `FrontCtx.c_cabi_cursor` 是**只写不读**的死字段（实测 2 处），随迁删除；
  入口分类改用局部游标。

## 备选与被否决的方案

| 方案 | 结论 | 理由 |
| --- | --- | --- |
| FileScope 留 support | 否决 | 项目解析数据不属于 L0 基础设施；support 只剩「编译器 libc」 |
| `sym_sfx` 随 FileScope 进 proj | 否决 | 模块构建态不是文件作用域；proj 不应承载 worker 状态 |
| `front_checked_*` 留 support | 否决 | 是语义阶段守卫，ADR-0021 已定归 check |
| ABI 模型随 CABI_* 留 support | 否决 | 只有 check 消费；ABI 分类是语义规则的一部分 |
| 顺带搬 `ModelStore`/`value_kernel` | 否决（本次） | 值规则读 `ms()`，需整体重设计，另立 ADR |

## 后果

- `support`：20 文件 / 3,120 行 → **19 / 2,843**；删除 `support/file_scope.yh`
  （其「gen 会反向依赖 proj」的保留理由随 gen 删除已失效）。
- `proj`：4 文件 / 1,841 行 → **5 / 2,078**（含 FileScope 与查找）。
- `check`：新增 `front_stage.yh`，ABI 模型落在 `abi_c.yh`；模块依赖边**不变**
  （proj→support、check→proj、build→check 都已存在）。
- `.s.i`/`.s.ct`/IR 编码值不变；用户程序产物应与改动前逐字节一致（门禁差分验证）。
- 测试：llvmfront / llvmlower 覆盖 `check.front_checked_*`；support fixture 删除
  front_stage 断言（已迁出 support 公开面）；ctfacts 改用 `proj.fs()`。