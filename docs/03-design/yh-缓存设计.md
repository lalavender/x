# yh 缓存设计

修改时间：2026-11-06

状态：**当前实现设计（C0–C4 已落地）**，记录 `yh build` 的四层缓存、全局
content store 与接口就绪机制；链接驱动分离等剩余目标见
[架构设计](yh-架构设计.md) §6.5 与 `docs/todo.md` 的 S0–S6。

---

## 0. 范围

本文覆盖：

- 模块接口/对象缓存；
- 函数 check 切片缓存；
- 函数 IR 缓存；
- 链接缓存；
- InterfaceReady/session 调度标记；
- 键、manifest、命中、提交、失效、原子性与当前边界。

不覆盖：CI 缓存、Release 资产、宿主包管理器缓存。

---

## 1. 设计目标与不变量

缓存是**优化**，不是正确性来源。任何缓存 miss、损坏、版本不兼容都必须退化为
完整构建，不能产生错误产物。

硬不变量：

1. **miss 安全**：读不到、校验失败、版本不符、完成标记缺失 → 按 miss 处理。
2. **键只含可复现事实**：源码/接口/目标/ABI/优化级别/工具身份；不混入瞬时
   arena ID、调度顺序、进程地址。
3. **成功后才提交**：模块失败、中断、取消不发布成功 manifest/索引。
4. **manifest + 内容摘要**：只匹配键不够，还要校验对象/接口/产物的内容摘要。
5. **原子发布**：记录、索引、manifest、对象、最终程序都走临时文件 + `rename`。
6. **check/test 隔离**：`yh check` 不读写正式构建缓存；`yh test` 用
   `tmp/yh-test`，不装载/提交函数缓存。
7. **版本可拒绝**：格式变化必须换版本/键，旧记录按 miss 处理。
8. **命中/未命中可观测**：统计输出已于 2026-11-10 随 `support.stats()` 一并删除；
   现在只能从产物字节/时间差间接判断缓存行为。

---

## 2. 总览

```text
模块接口/对象缓存
  → 命中：跳过整个 module worker

函数 check 切片缓存
  → 命中：跳过函数体解析/语义检查/AST 捕获

函数 IR 缓存
  → 命中：跳过 lowering
  → 注意：不跳过整模块 LLVM 文本生成/桥发射

链接缓存
  → 命中：跳过 lld/平台链接器

InterfaceReady
  → 调度标记：提供方接口可提前发布；不是持久内容缓存
```

四层缓存的实现位置不同：

| 层 | 实现 |
| --- | --- |
| 模块接口/对象 | `build/module_cache.yh`、`build/module_emit.yh` |
| 函数 check | `build/function_ir_cache.yh`、`ast/module_snapshot_check_*` |
| 函数 IR | `build/function_ir_cache.yh`、`lower/module_snapshot_lower_cache.yh`、`ir/ssa_module_40/50` |
| 链接 | `link/link_cache.yh` |
| 路径/键原语 | `proj/proj_40_art.yh` |

---

## 3. 目录与路径

```text
<root>/.build/                      # 默认 cache_root；YH_BUILD_CACHE 可迁走
  <project.name>                    # 默认可执行文件（不随 cache_root 移动）
  targets/<triple>/llvm/O<opt>/
    iface/<project>-<module>.s.i
    iface/<project>-<module>.s.ct
    iface/<project>-<module>.ready
    obj/<project>-<module>.o
    llvm/<project>-<module>.ll
    asm/<project>-<module>.s
    manifest/<project>-<module>.manifest
    firc/<project>-<module>/
      index
      index.check
      <key>.fir
      <key>.fchk
    manifest/link.manifest
  check/...                         # yh check
  tmp/yh-test/check/...             # yh test
```

路径规则由 `proj_40_art` 负责：

- `cache_root()`：`YH_BUILD_CACHE` 或 `<root>/.build`；
- `build_dir()`：生产 `targets/<triple>/llvm/O<opt>`；check `check`；test
  `tmp/yh-test/check`；
- `mod_tag()`：`<project>-<module>`，避免不同项目同名模块冲突；
- `module_iface_path()`、`module_ctiface_path()`、`module_obj_row()` 等。

`YH_BUILD_CACHE` 只迁中间缓存树，不改变默认可执行文件位置。

C4 新增全局内容寻址缓存（默认开启，`YH_CACHE=off` 关闭）：

```text
~/.cache/yh/ 或 ~/Library/Caches/yh/ 或 %LOCALAPPDATA%\yh\cache\
  v1/actions/<ActionID>   输出角色 → OutputID 列表（二进制）
  v1/outputs/<OutputID>   实际字节（相同内容只存一份）
  v1/tmp/                 原子提交临时文件
  v1/lock                 全局写锁（C6 flock）
```

模块 obj/.s.i/.s.ct 与函数 `.fchk`/`.fir` 内容进入 outputs；最终可执行文件
仍只写项目 `.build`。读取时重算 OutputID；损坏/缺失按 miss。项目
`.build/index/<tag>` 只存 64 hex ActionID。C6 增加同项目构建锁、全局写锁、
`yh cache info/clean/trim/verify`、按大小/年龄 trim 与 `YH_CACHE_DEBUG`。

---

## 4. 模块接口/对象缓存

### 4.1 缓存内容

一个模块成功后发布：

```text
obj/<tag>.o
iface/<tag>.s.i
iface/<tag>.s.ct
manifest/<tag>.manifest
```

`--emit-llvm`/`--emit-asm` 额外发布的 `llvm/<tag>.ll`、`asm/<tag>.s` 是审阅
产物，不进入 manifest；缓存命中时若本次显式请求的产物缺失，退回 worker 补写。

LLVM 路径下对象是**模块级** `<tag>.o`；`module_obj_row` 的按文件对象路径是旧
路径遗留，`mb_link_objects` 在 `llvm_objects != 0` 时跳过，不参与当前构建。
2026-11-06 决定（[ADR-0020](../adr/0020-yh对象粒度停在模块级.md)）：对象粒度停在
模块级；文件级对象不做，函数级 `.o` 暂缓；该旧路径仅保留兼容，不再扩展。

### 4.2 键

`mb_compile_start` 计算模块键，混入：

- 本模块全部源文件内容；
- 依赖模块 `.s.i` / `.s.ct` 内容（传递闭包）；
- target triple / data layout / ABI；
- `O0/O2` 与 `--trimpath` 模式；
- 编译器自身二进制内容身份；
- LLVM 桥版本与桥 ABI；
- Darwin 部署目标/PIC；
- 模块符号后缀、入口标记、`legacy_system`；
- `yh test` 的测试选择摘要（仅测试模式）。

编译器身份由 `mb_mix_compiler_fingerprint` 计算：C2 起每进程只对编译器二进制
做一次 SHA-256，模块键混入完整 32 字节；`(size, mtime_ns)` 不再参与身份。

### 4.3 manifest

模块 manifest 是 **128 字节**（C4）：

```text
[0..32)   模块 ActionID（SHA-256）
[32..64)  对象 OutputID
[64..96)  .s.i OutputID
[96..128) .s.ct OutputID
```

命中必须同时满足：

1. 四个文件存在；
2. manifest 的 ActionID 等于期望键；
3. 对象 OutputID 与内容摘要匹配；
4. `.s.i` / `.s.ct` 的 OutputID 匹配；
5. 对象机器架构匹配（`mb_object_machine_matches`）；
6. 本次显式请求的 `.ll` / `.s` 存在（只有 `build --emit-llvm/--emit-asm` 检查，
   不参与 manifest）。

命中打印 `[缓存] <module>`，返回 `1`，不启动 worker。

### 4.4 依赖接口闭包

`mb_module_iface_deps`：

1. 收集直接导入；
2. 对依赖的依赖做闭包扩充（导出结构体字段可能引用外模块类型）；
3. 按本轮拓扑序排序；
4. 生成接口路径；优先本轮 `.session-<pid>` 接口，否则持久接口。

### 4.5 提交

父进程 `mb_manifest_commit`：

- 重新校验对象架构与摘要；
- 校验 `.s.i` / `.s.ct` 存在并写摘要；
- 写临时 manifest；
- `rename` 原子提交。

模块失败不提交 manifest。

---

## 5. 函数 check 切片缓存

### 5.1 文件

```text
<build>/firc/<tag>/
  index.check
  <key>.fchk
```

### 5.2 键

`checked_gen_function_key` 在 pass2b 之前计算，混入：

- 统一 schema（`CACHE_SCHEMA_VERSION` + `ACTION_CHECK` + `"function"`）；
- check 环境键（依赖接口、target、ABI、O 级别、编译器身份、桥版本）；
- target key / pointer bits / layout version / ABI；
- 项目相对源路径（绝对路径不进入键）；
- GenState 类型/字段/签名表；
- 源码级 `const` 的常量值/标志（类型只混 ABI 事实）；
- 本模块非函数声明 token 流；
- 本函数 token 流。

注释/空白由词法器剥离，不进入键；其他函数体不进入本函数键。键是 SHA-256
64 位十六进制；target/ABI/opt/trimpath 由 `cache.CacheInputs` 白名单固定，
源文件路径按项目相对路径进入。逐输入审计见[缓存键审计](yh-缓存键审计.md)。

### 5.3 命中与导入

pass2b 解析每个声明时：

- 键命中 → `checked_slice_import` 导入受检 AST 切片；
- 跳过 `sem_fn_begin` / 参数声明 / `parse_block` / `sem_fn_end` / AST 捕获；
- 导入时局部 ID 加 base；
- 类型/符号/文件/声明重新绑定；
- 导入后仍走模块级结构校验。

### 5.4 记录与限制

- 切片版本：`CHECKED_SLICE_VERSION = 5`；切片内文件路径为项目相对路径。
- 单函数切片上限：1 MiB；
- 本轮切片总上限：16 MiB；
- 含 `$for` 模板等不适合切片的函数跳过缓存；
- 模块完整成功后才提交 `.fchk` 与 `index.check`。

---

## 6. 函数 IR 缓存

### 6.1 文件

```text
<build>/firc/<tag>/
  index
  <key>.fir
```

### 6.2 记录格式

`.fir` 是：

```text
40 字节外层头：
  magic
  format version
  env_key
  payload 长度
  payload FNV 校验和

payload：单函数及其类型/符号/全局/来源闭包的迷你 IRModule
```

`IR_FUNCTION_CACHE_VERSION = 3`。

### 6.3 键

`checked_function_key` 混入：

- 统一 schema（`CACHE_SCHEMA_VERSION` + `ACTION_IR` + `"function"`）；
- 模块环境键 `env_key`（标签 `yh-firc-env-3`）；
- target key / pointer bits / layout version / ABI；
- 项目相对源路径（绝对路径不进入键）；
- 声明面的布局与签名事实（只混 struct/union/enum 布局与函数签名，不混整张
  类型表）；
- 源码级 `const` 常量事实（类型只混 ABI 事实）；
- 本模块非函数声明 token 流；
- 本函数 token 流。

键是 SHA-256 64 位十六进制。check 与 IR 使用不同 action 种类，不要求两份键
字节相等。

`env_key` 来自 `firc_env_key`：

- target triple/data layout/ABI；
- O 级别；
- `ir_cache_salt`（编译器指纹）；
- LLVM 桥版本；
- 本模块本轮 `.s.i` / `.s.ct` 内容；
- 依赖模块 `.s.i` / `.s.ct` 内容。

### 6.4 命中与重绑定

`lower_module_cached`：

1. `checked_function_key`；
2. `ir_function_cache_set_find`；
3. `ir_function_cache_merge`：
   - 反序列化迷你模块；
   - 校验目标/环境/函数身份；
   - 类型按结构复用/补建；
   - 符号按名字复用/补建；
   - 全局按符号与内容复用/补建；
   - 函数体模块下标重绑到当前模块；
4. 成功 → `cache_hits += 1`；
5. 失败/损坏 → 按 miss 重新 lowering。

**关键边界**：函数 IR 缓存只跳过 lowering；`backend.llvm_emit_module` 仍对整
模块生成 LLVM 文本。单函数改动仍会重跑整模块 LLVM 发射；对象粒度已固定在
模块级，这是接受的成本（[ADR-0020](../adr/0020-yh对象粒度停在模块级.md)）。

### 6.5 提交

- 只有模块完整成功后才写 `.fir`；
- 每条记录临时文件 + `rename`，最后原子写 `index`；
- `firc_recycle_old` 按旧索引删除本轮不再使用的记录；
- 写失败只报告，不把构建判失败；
- 单记录上限 4 MiB，单集合上限 256 MiB；
- 递归/前向类型闭包不缓存，capture 返回 1 跳过。

---

## 7. 链接缓存

### 7.1 流程

`mb_link` 六段：

```text
prepare → objects → key → args → libs → exec
```

- `prepare`：选链接器、检查自举闭包、装配 C 项目输入；
- `objects`：LLVM 模式下对象已由 worker 发布，这里只登记/校验；
- `key`：计算链接键，查 `manifest/link.manifest`；
- `args`：装配 argv；
- `libs`：`[link]` / `[link-<os>-<arch>]` / `[c].libs` / 运行时；
- `exec`：lld/COFF/Mach-O worker，产物原子发布。

### 7.2 键

`mb_link_key` 混入：

- 链接器/工具身份；
- lld/COFF/Mach-O 身份；
- target triple/data layout/ABI；
- O 级别；
- 链接 flags；
- 输出路径；
- 全部对象内容；
- `--link` 库、运行时、系统库；
- Darwin 部署/签名相关配置。

### 7.3 manifest

`manifest/link.manifest` 是 **32 字节**：

```text
[0..16)   链接键
[16..32)  最终产物内容摘要
```

命中条件：

- 输出文件存在；
- link manifest 存在且内容匹配；
- 最终产物摘要匹配。

命中直接返回，不执行 lld。

### 7.4 发布

`mb_link_exec`：

1. 链接到临时文件；
2. 校验产物架构（ELF/Mach-O/PE）；
3. Darwin 额外校验版本/签名；
4. `rename` 原子发布；
5. 重新哈希最终产物；
6. 写 link manifest。

失败不发布输出，也不写成功 manifest。

---

## 8. InterfaceReady 与 session

不是持久内容缓存，但决定调度：

- `mb_sched_set_session` 生成本轮 `.session-<pid>` 后缀；
- worker 在函数体 pass2b 之前写：

```text
.s.ct
.s.i
.ready
```

- 依赖方 `mb_sched_deps_ready` 只认 ready + 接口存在；
- 父进程在 worker 完整成功后用 `mb_sched_publish_interface` 复制为持久接口；
- 本轮结束 `mb_sched_clear_interfaces` 清理 session 文件。

这允许消费者在提供方私有函数体完成前开始，同时避免把未完成模块的接口当成
最终缓存。

---

## 9. 失效矩阵

| 变化 | 模块缓存 | 函数 check/IR | 链接缓存 |
| --- | --- | --- | --- |
| 注释/空白 | **miss**（模块键含完整源文件内容） | **hit**（函数键只含 token） | 对象不变则 hit |
| 单个函数体 | **miss**（模块键含整模块源） | 其他函数 hit，本函数 miss | 对象变则 miss |
| 非函数声明/常量 | miss | 读取它的函数保守 miss | 视对象 |
| 公开签名/接口 | miss | 依赖接口变化 → 全部 miss | 视对象 |
| target/ABI/O 级别 | miss | 全部 miss | miss |
| 编译器/桥版本 | miss | 全部 miss | 工具身份变化 → miss |
| 测试选择 | 测试模式由测试键决定 | 测试模式不装载/不提交 | 测试构建独立 |

重点：

1. **模块缓存按整模块源内容失效**：改注释也会让模块缓存 miss，worker 仍会跑；
   但函数 check/IR 缓存可以继续 hit。
2. **函数 IR 缓存只省 lowering，不省整模块 LLVM 发射**：单函数改动仍会重跑
   整模块后端；对象粒度固定模块级（ADR-0020），不通过文件/函数对象解决。

---

## 10. 冷构建、check 与 test

### 10.1 冷构建不写函数缓存

`mb_schedule_modules`：

- 若 `<build>/manifest/link.manifest` 不存在（刚清空 `.build` / 冷构建）：
  - `support.ctl().firc_write_off = 1`；
  - worker 不写 `.fchk` / `.fir`；
  - 原因：capture 占冷编约四成时间，写下的记录在下一轮清空后不会被读。

`manifest/link.manifest` 存在后才允许写函数缓存。

### 10.2 `yh check`

- 构建目录 `<cache>/check`；
- 不读取/更新正式模块 manifest/缓存；
- 不装载函数 check/IR 缓存；
- 只做前端 + 结构校验/快照校验；
- 结束后清理 check 接口。

### 10.3 `yh test`

- 构建目录 `<root>/tmp/yh-test/check`；
- 模块键混入测试选择摘要；
- 不装载/提交函数 check/IR 缓存；
- 测试体用 mode 5 解析；
- 与生产构建缓存隔离。

---

## 11. 原子性与并发

当前实现：

- 模块 manifest：临时文件 + `rename`；
- 函数记录：临时文件 + `rename`；
- 函数索引：最后原子写；
- 链接产物：临时文件 + 架构/签名校验 + `rename`；
- link manifest：最后写；
- session 接口后缀隔离本轮接口。

已知边界：

- 同一项目并发构建时，module/link manifest 是“最后写者赢”，没有全局锁；
- 函数缓存数据集不是整体事务：记录逐个 rename，索引最后写；中途失败会留下
  部分记录，但旧索引不会引用它们；
- `firc_recycle_old` 只按旧索引删除，不在索引中的孤儿文件不做目录枚举；
- 模块对象/链接缓存都有“输出文件 + manifest”双文件，读取端同时校验摘要，
  单边损坏按 miss 处理。

---

## 12. 当前实现问题与目标方向

| 问题 | 证据 | 目标方向 |
| --- | --- | --- |
| 三套缓存各自实现 | `module_cache`、`function_ir_cache`、`link_cache` | C4 已抽 `build/cache/cache_store` + `build/cache_global`；link 待 C6 |
| `link_cache` 混了链接驱动 | 1,647 行，含 `mb_link` 六段 | 缓存键/manifest 与 lld 调用分离 |
| 函数缓存不减少 LLVM 代码生成 | `lower` 命中后 `backend.llvm_emit_module` 仍整模块 | 不做文件/函数级对象；接受整模块发射（ADR-0020） |
| 模块对象是模块级 | `obj/<tag>.o` | 最终粒度；单函数改动重发模块对象是接受的成本 |
| ~~编译器指纹用 size/mtime~~ | `mb_mix_compiler_fingerprint` | C2 已改为 SHA-256 内容身份 |
| check/IR 键逻辑重复 | `ast/module_snapshot_check_key` 与 `lower/module_snapshot_lower_cache` | C0 已抽 `cache.Key` 公共前缀/token/长度分帧；声明面事实按阶段保留 |
| 版本常量分散 | 模块缓存 tag、`CACHE_SCHEMA_VERSION=3`、`CHECKED_SLICE_VERSION=5`、`IR_FUNCTION_CACHE_VERSION=3`、link manifest 无显式版本 | 统一 `yh version --contracts`/缓存版本表 |
| 并发协调不足 | module/link manifest 最后写者赢 | C6 已加同项目构建锁 + 全局 cache 写锁 |
| 缓存无限增长 | outputs 只增不减 | C6 `trim` 按大小/年龄回收无引用 output |
| 故障不可见 | 只有读到损坏才知道 | C6 `verify` 全量检查 + `YH_CACHE_DEBUG` |

C0–C6 的键组成、ActionID/OutputID 编码与四类 action 失效矩阵见
[缓存键审计](yh-缓存键审计.md)（`ACTION_FILE` 为预留常量，不启用）；
实现流水见 [finish.md](../finish.md) 的缓存 C0–C6 条目。

目标结构（详见架构设计 §6.5）：

```text
cache/
  cache_key.yh            统一 schema/ActionID/OutputID/公共键原语
  cache_store.yh          全局 content store：actions/outputs/tmp、原子 put/get
build/
  cache_global.yh         YH_CACHE 初始化、模块发布/物化、全局 miss 回退
  module_cache.yh         模块 iface/对象缓存
  function_ir_cache.yh    函数 check/IR 缓存 I/O
  link_cache.yh           链接缓存键/manifest（不含 lld 驱动；C6 再迁 store）
```

`link` 只保留链接驱动/lld/进程/时钟；`proj_40_art` 继续拥有产物路径与哈希原语。

---

## 13. 版本与常量

| 项 | 当前值 | 位置 |
| --- | ---: | --- |
| 模块缓存 tag | `"yh-iface-cache-5-ct"` | `build/module_emit.yh` |
| 缓存键 schema | `CACHE_SCHEMA_VERSION = 3` | `build/cache/cache_key.yh` |
| check 切片 | `CHECKED_SLICE_VERSION = 5` | `ast/module_snapshot_check_slice.yh` |
| 函数 IR 缓存 | `IR_FUNCTION_CACHE_VERSION = 3` | `ir/ssa_module_40_function_cache.yh` |
| 函数缓存记录头 | 40 字节 | `ir/ssa_module_40_function_cache.yh` |
| 模块 manifest | 128 字节（4×SHA-256） | `build/module_cache.yh` |
| link manifest | 32 字节 | `link/link_cache.yh` |
| 接口版本 | `IFACE_VERSION_MIN/MAX` 1–3 | `parse/iface.yh` |
| 编译期接口 | `CTIFACE_VERSION = 1` | `parse/iface.yh` |
| SSA 序列化 | `IR_SERIAL_VERSION = 9` | `ir/ssa_serialize.yh` |
| 模块 IR 序列化 | `IR_MODULE_SERIAL_VERSION = 3` | `ir/ssa_module_30_serialize.yh` |

---

## 14. 代码位置

| 内容 | 文件 |
| --- | --- |
| 缓存键 schema/ActionID | `compiler/build/cache/cache_key.yh` |
| 全局 content store | `compiler/build/cache/cache_store.yh` |
| 全局缓存接线 | `compiler/build/cache_global.yh` |
| 模块缓存键/依赖/manifest | `compiler/build/module_cache.yh` |
| 模块缓存命中判断 | `compiler/build/module_emit.yh::mb_compile_start` |
| 函数缓存 I/O | `compiler/build/function_ir_cache.yh` |
| 函数 check 键 | `compiler/ast/module_snapshot_check_key.yh` |
| check 切片捕获/导入 | `compiler/ast/module_snapshot_check_slice.yh` |
| 函数 IR 键 | `compiler/lower/module_snapshot_lower_cache.yh` |
| 函数 IR 命中/合并 | `compiler/lower/module_snapshot_lower.yh` |
| 迷你 IRModule 序列化 | `compiler/ir/ssa_module_40_function_cache.yh` |
| 函数缓存重绑定 | `compiler/ir/ssa_module_50_function_rebind.yh` |
| 链接缓存/驱动 | `compiler/link/link_cache.yh` |
| 路径/缓存根 | `compiler/proj/proj_40_art.yh` |
| 调度/session/冷构建判定 | `compiler/build/build_scheduler.yh` |
| 构建会话状态 | `compiler/build/build_ctx.yh` |

---

## 15. 设计结论

- 当前缓存是“模块对象 + 函数 check 切片 + 函数 IR + 链接”四层独立缓存。
- 模块级缓存最有效：命中直接跳过整个 worker；对象粒度固定模块级，文件级
  对象不做、函数级 `.o` 暂缓（[ADR-0020](../adr/0020-yh对象粒度停在模块级.md)）。
- 函数级缓存只省前端/lowering，不省整模块 LLVM 发射；这是明确接受的成本，
  不是待补的缺口。
- 当前实现能保证单次构建的原子发布与损坏回退，但缓存实现分散、版本入口分散、
  并发提交没有全局协调。
- 调整缓存时优先保持本文的不变量，再按 `build/cache/` 目标收拢。
