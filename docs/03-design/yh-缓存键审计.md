# yh 缓存键审计与 ActionID 编码

修改时间：2026-11-06

状态：C0–C6 实现记录。模块 ActionID 与 `check`/`IR` 函数键均为 SHA-256；
并使用项目相对路径与 `CacheInputs` 白名单；`--trimpath` 可把 IR/CT 来源路径也
裁剪为相对路径。链接键仍使用 FNV 16 位十六进制，但编译器/工具身份已是内容 SHA-256；
C4 已把模块与函数中间产物接入全局 content store。文件级 action 已撤销
（ADR-0020），`ACTION_FILE` 仅保留为 schema 预留常量。实现流水见
[finish.md](../finish.md) 的缓存 C0–C6 条目。

---

## 1. 统一 schema

```text
ActionID = SHA-256(
  "yh-cache-key",
  schema_version,          # cache.CACHE_SCHEMA_VERSION（当前 3）
  action_kind,             # module/check/ir/link（file 预留）
  label,                   # "function" 等稳定动作名
  输入事实（长度分帧）
)
OutputID = SHA-256(输出字节)
```

- 二进制形式 32 字节；文本形式 64 个小写十六进制字符 + 结尾零。
- 所有文本/字节输入先混入 `u64` 长度，再混入内容；整数按小端八字节。
- 键只含可复现事实：源内容/词法 token、依赖接口、目标/ABI、优化级别、
  工具身份、显式环境白名单。瞬时 arena 下标、进程地址、调度顺序不进入键。
- 代码入口：`compiler/cache/cache_key.yh`（`Key`、`key_init*`、`key_mix_*`、
  `key_finish_hex`）；SHA-256 在 `libs/hash/sha256.yh`。

C2（2026-11-06）：编译器身份由 `BuildCtx.compiler_identity[32]` 保存，每进程
只读一次编译器二进制并做 SHA-256；模块键混入完整 32 字节，`compiler_fingerprint`
是由摘要派生的 64 位值（worker 环境键）。外部链接器/驱动身份改为路径 + 内容
SHA-256；`touch`/复制不改变身份，替换内容必变。

C3（2026-11-06）：函数键使用项目相对路径；`cache.CacheInputs` 固定 target/ABI/
优化级别/trimpath 白名单；SDK/selfhost/工具链先解析成内容身份。check 切片 v5
保存相对路径；`--trimpath` 让 IR/CT 来源路径也使用相对路径。白名单外的环境
（如 `YH_WORKERS`）不进入键。

C3 的 `CacheInputs` 白名单与运维环境分界：

| 类别 | 变量/输入 | 是否进语义键 |
| --- | --- | --- |
| 目标/代码生成 | target、ABI、pointer/layout、opt、trimpath | 进（`CacheInputs`） |
| 工具链内容 | 编译器 SHA-256、lld/bridge/SDK 内容身份 | 进（`env_key`/模块键） |
| 链接语义开关 | `YH_LINK_STRIP`、`YH_LINK_DEAD_STRIP` | 进链接受键 |
| 链接输入 | `LIBRARY_PATH`、`LD_RUN_PATH`、`YH_CC` 解析结果 | 进链接键 |
| 运维 | `YH_WORKERS`、`YH_NO_FORK`、`YH_BUILD_CACHE`、`YH_CACHE_DEBUG` | 不进 |
| 宿主环境 | `HOME`、`PWD`、`TMPDIR`、locale | 不进 |

`PATH` 不直接进键：工具先按 `PATH` 解析成绝对路径，再用路径 + 文件内容身份
参与键，避免整条环境串造成无谓失效。

当前 action 种类：

| 常量 | 值 | 用途 |
| --- | ---: | --- |
| `ACTION_MODULE` | 1 | 模块对象/接口 action（已接入） |
| `ACTION_FILE` | 2 | 预留；文件级对象已撤销（ADR-0020），不启用 |
| `ACTION_CHECK` | 3 | 函数 check 切片（`.fchk`） |
| `ACTION_IR` | 4 | 函数 IR 记录（`.fir`） |
| `ACTION_LINK` | 5 | 最终链接 action（C4） |

check 与 IR 使用不同 action 种类，因此同一个函数的两份记录不复用键；它们共享
`key_init_function` 前缀、token 混入与长度分帧，但声明面事实按各自阶段的数据
模型取值（见 §2.3、§2.4）。

---

## 2. 四类 action 的输入审计

### 2.1 module（模块对象/接口）

实现：`build/module_emit.yh::mb_compile_start`、`build/module_cache.yh`。

| 输入 | 说明 |
| --- | --- |
| 模块符号后缀、入口标记、`legacy_system` | 同项目内不同模块的链接身份 |
| 测试选择摘要 | 仅 `yh test`（`c_test_mode`），生产构建不混入 |
| target triple / data layout / ABI | 目标的完整标识 |
| 优化级别与 trimpath | `O0`/`O2`；`--trimpath` 改变来源表/CT 路径 |
| 桥版本 / 桥 ABI | `backend.llvm_bridge_version()` 与固定 ABI 串 |
| Darwin 部署目标 / PIC | 仅 Darwin 目标 |
| 本模块全部源文件内容 | `proj.hash_file` 原始字节；注释变化也会 miss |
| 依赖 `.s.i` / `.s.ct` 内容 | 导入闭包（含传递依赖） |
| 编译器身份 | 编译器二进制内容 SHA-256（32 字节，C2）；模块键混入完整摘要 |
| schema 标签 | `yh-iface-cache-5-ct`（C3 从 4 递增） |
| 本地 manifest | 128 字节：ActionID + obj/.s.i/.s.ct OutputID |
| 全局 action | `v1/actions/<ActionID>` 输出角色表；内容在 `v1/outputs` |

产物：`obj/<tag>.o`、`iface/<tag>.s.i`、`iface/<tag>.s.ct`。
C4 manifest 为 128 字节：模块 ActionID（32）+ 三个 OutputID（各 32）；
`.build/index/<tag>` 只存 64 hex ActionID。

### 2.2 link（最终链接）

实现：`link/link_cache.yh::mb_link_key` 与 `mb_link_exec`。

| 输入 | 说明 |
| --- | --- |
| 链接器/lld/COFF/Mach-O 身份 | 外部工具按解析路径 + 内容 SHA-256；lld 身份串为 SHA-256，SDK/默认库按内容摘要 |
| target triple / data layout | 目标 ABI |
| 优化级别 | 影响对象内容与链接参数 |
| 链接 flags / 输出路径 | `-no-pie`、`--gc-sections`、Darwin 签名等 |
| 全部对象内容 | 逐模块对象文件字节 |
| C 源/对象/库、`[link]` 组 | 项目链接输入 |
| 运行时/系统库与启动文件 | 平台闭包 |
| Darwin 部署/签名配置 | `-dead_strip`、`-x` 等 |

产物：最终可执行文件。manifest 当前 32 字节：链接键 16 + 产物摘要 16（FNV）。
最终可执行文件**不进入**全局缓存（只留项目 `.build`）。

### 2.3 check（函数 check 切片）

实现：`ast/module_snapshot_check_key.yh::checked_gen_function_key`。

| 输入 | 说明 |
| --- | --- |
| action 种类 + label | `ACTION_CHECK` + `"function"` |
| 环境键 `checked_check_cache_env` | `firc_env_key`：target/layout/ABI、指针位宽、`layout_version`、O 级别、编译器 salt、桥版本、本模块与依赖 `.s.i/.s.ct` |
| target key / 指针位宽 / layout version / ABI | 目标 ABI |
| 源文件路径 | 项目相对路径（`proj.file_rel_path`），绝对路径不进入键 |
| GenState 类型表 | `t_type_n` + 每项 kind/size/align/elem/len/sub |
| GenState 字段表 | `t_field_n` + 每项 name_len/type_id/offset |
| GenState 签名表 | `t_sig_n`、每项 abi/ret/np/vararg/first、参数表 |
| 源码级 const 事实 | kind、类型 ABI 事实、flags、cval、ready、expr_kind |
| 非函数声明 token 流 | 全局/常量/类型；函数体不进入其他函数键 |
| 本函数 token 流 | 词法器剥离注释/空白 |

产物：`.fchk` + `index.check`。键为 SHA-256 64 位十六进制。

### 2.4 IR（函数 IR）

实现：`lower/module_snapshot_lower_cache.yh::checked_function_key`。

| 输入 | 说明 |
| --- | --- |
| action 种类 + label | `ACTION_IR` + `"function"` |
| 环境键 `env_key` | 与 check 相同的 `firc_env_key` |
| target key / 指针位宽 / layout version / ABI | 目标 ABI |
| 源文件路径 | 项目相对路径，与 locs 分离 |
| 声明面布局 | 逐声明 kind；aggregate 混类型 ABI 事实；函数混签名事实 |
| 源码级 const 事实 | 同 check |
| 非函数声明 token 流 | 同 check |
| 本函数 token 流 | 同 check |

产物：`.fir` + `index`，记录头版本 `IR_FUNCTION_CACHE_VERSION = 3`。
键为 SHA-256 64 位十六进制。

与 check 的差异：check 在 pass2b 前只能看到 GenState 的整张类型/签名表，IR 在
lowering 时使用逐声明布局。两者 action 种类不同，不要求字节相等的键。

### 2.5 file（文件级对象，已撤销）

已撤销（[ADR-0020](../adr/0020-yh对象粒度停在模块级.md)）：对象粒度停在模块级，
不再规划每个 `.yh` 一个 `.o`。`ACTION_FILE` 常量保留仅为 schema 预留。

---

## 3. 失效矩阵

`hit` 表示该层可以复用，`miss` 表示必须重建。模块键按整模块源内容失效，
因此注释变化也会让模块 miss；函数键只含 token，可继续 hit。对象粒度固定
模块级（ADR-0020），下表不含 file action。

| 变化 | 模块 | check | IR | 链接 |
| --- | --- | --- | --- | --- |
| 注释/空白 | miss | hit | hit | 对象不变则 hit |
| 单函数体 | miss | 该函数 miss | 该函数 miss | 对象变则 miss |
| 单文件非函数声明 | miss | 读取它的函数保守 miss | 同左 | 视对象 |
| 函数签名/公开接口 | miss | 依赖方全部 miss | 依赖方全部 miss | 视对象 |
| struct/union/enum 布局 | miss | 依赖方全部 miss | 依赖方全部 miss | 视对象 |
| 插入同签名函数 | miss | 其他函数 hit（类型/签名表未变） | 整模块保守 miss | 视对象 |
| target/ABI/O 级别 | miss | 全部 miss | 全部 miss | miss |
| 编译器内容 | miss | 全部 miss | 全部 miss | tool 身份变则 miss |
| lld/桥/SDK 内容 | 桥版本变则 miss | 桥版本变则 miss | 桥版本变则 miss | miss |
| 缓存记录损坏/截断 | 按 miss | 按 miss | 按 miss | 按 miss |
| 源码目录搬移 | C3 后 hit | C3 后 hit | C3 后 hit | 输出路径变则 miss |

---

## 4. 旧缓存拒绝

C0–C4 通过版本/长度/键格式让旧缓存**不可命中**；模块与函数键已改用 SHA-256。

| 位置 | 旧 | 新 | 结果 |
| --- | --- | --- | --- |
| cache schema | 无 | `CACHE_SCHEMA_VERSION = 3` | 进入所有新键 |
| 函数 check 键 | FNV 16 hex | SHA-256 64 hex | 旧 `index.check` 行长度不匹配，跳过 |
| 函数 IR 键 | FNV 16 hex | SHA-256 64 hex | 旧 `index` 行长度不匹配，跳过 |
| check 切片记录 | v3 | v5 | 头部版本不匹配，按 miss（v5 起路径为相对路径） |
| IR 记录 | v2 | v3 | 头部版本不匹配，按 miss |
| 函数缓存环境标签 | `yh-firc-env-1` | `yh-firc-env-3` | 旧记录环境键不同 |
| 模块 manifest | 64 字节 FNV | 128 字节 SHA-256 + OutputID | 长度/键不匹配 |
| 全局缓存 | 无 | `v1/actions` + `v1/outputs` | 版本/OutputID 校验失败按 miss |
| 链接键 | FNV 16 hex | C6 迁移 SHA-256 | 当前仍可读，但新键会换格式 |

旧记录不删除、不迁移；`yh cache clean`（C6）统一清理。

---

## 5. C4 已落地布局

```text
YH_CACHE/v1/
  actions/<ActionID>     # 输出角色 → OutputID 列表 + size
  outputs/<OutputID>     # 字节内容（相同内容只存一份）
  tmp/                   # 原子提交临时文件
  lock                   # 全局写锁（C6 flock）
```

模块 action 输出 `object`/`iface`/`ct_iface`；函数 check/IR action 各输出一条
记录。项目 `.build` 保留本地 manifest、`.build/index/<tag>`（只含 ActionID）
与最终可执行文件。读取时重算 OutputID，长度/摘要/版本不符按 miss；重新发布
会覆盖损坏的 output。C6 `yh cache verify` 全量检查 action/output/孤儿，
`trim` 只删除未被 action 引用的 output，`YH_CACHE_DEBUG` 输出 ActionID 与
local/global miss 原因。
