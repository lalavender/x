# yh project.toml 清单设计

本文是 `project.toml` 的**参考规范**：每一节、每个字段的取值、默认值、校验时机与
诊断原文，都以当前实现为准。设计背景（为什么这样分节、与模块系统的关系）见
[yh-模块与项目管理设计](yh-模块与项目管理设计.md)，编译期装载细节见
[yh-编译流程-当前实现](yh-编译流程-当前实现.md)。

## 1. 定位

清单是一个项目的**唯一配置入口**：项目名与产物名、源码根、依赖、C 输入、链接闭包
与环境变量默认值都写在里面。编译器读清单的顺序固定（见 §12），读到的内容变成
`proj.PProj` 快照，前端、构建、链接三层都只读这份快照。

三条不可让步的规则：

1. **不接受隐式替代**：没有清单就不是项目模式（只有显式单文件编译例外，见 §3.3）；
   不扫描未列入 `[dependencies]` 的库目录；不为旧清单做兼容推断。
2. **未知配置必须报错**：`[project]`/`[c]`/`[env]` 的未知字段、非法的 `link-*` 节名
   一律按清单行号报错。唯一例外是**完全不属于本 schema 的节**（如 `[tool]`），它们
   不参与装载也不报错——这一点与 `[link-*]` 前缀节不同。
3. **路径相对清单**：清单里的相对路径一律相对声明它的 `project.toml` 所在目录，
   与执行命令的工作目录无关。

## 2. 示例

最小清单（没有依赖、没有 C、没有显式链接库）：

```toml
[project]
os = "host"
arch = "host"
name = "hello"
source = "src"
```

带依赖、C 输入与链接组的完整示例：

```toml
[project]
os = "linux"          # linux | darwin | host
arch = "arm64"        # arm64 | x64 | host
name = "app"          # 标识符，产物名由它派生
version = "0.1.0"     # 可选；yh version 展示用
source = "src"        # 可选，默认 src
author = "someone"    # 可选，仅登记

[dependencies]
util = { path = "../libs/util" }

[c]
sources = ["c/shim.c"]
objects = ["vendor/prebuilt.o"]
libs = ["m"]

[link]
core = ["vendor/lib/libcore.a"]

[link-linux-arm64]
core = ["vendor/lib/linux-arm64/libcore.a"]

[link-options]
whole = ["core"]

[env]
VENDOR_ROOT = "vendor"
```

## 3. 位置与发现

### 3.1 向上查找

`build`/`run`/`test`/`version` 从**当前工作目录**开始，逐级向上找最近的
`project.toml`，最多 32 层；找不到就报
`未找到 project.toml（自当前目录向上 32 层）`（`--quiet` 时只返回失败）。

### 3.2 嵌套项目边界

扫描源码根时，遇到含自己 `project.toml` 的子目录**不进入**：那个目录属于另一个
项目。因此项目可以安全地嵌在多项目仓库里（`libs/`、`compiler/`、测试 fixture 都是
这种形态）。

### 3.3 单文件模式

`yh file.yh`、`yh --syntax-check file.yh`、`yh f.yh -o out` 是单文件模式：不需要
清单，也不装载依赖。项目模式与单文件模式互不混用（单文件下不搜标准库）。

## 4. TOML 子集

清单解析器只实现清单需要的子集，其余形态直接报语法错（报错比静默误读安全）：

| 支持 | 不支持（报语法错） |
| --- | --- |
| 节头 `[name]` | 数组表 `[[name]]` |
| 裸键 `[A-Za-z0-9_-]+` | 点键 `a.b = 1` |
| 基本字符串、字面量字符串 | 多行字符串 |
| 字符串数组、被 `{ path = "..." }` 形态的内联表 | 日期、浮点、布尔、嵌套数组 |
| 注释 `#` 到行尾 | — |

诊断格式 `<清单路径>:<行>: 错误: <msg>`（清单不是 yh 源码，不带列号）。

## 5. `[project]`

| 字段 | 必填 | 取值 | 说明 |
| --- | --- | --- | --- |
| `name` | 是 | 标识符：字母或下划线开头，仅字母、数字、下划线 | 产物名、接口 tag 由它派生，不接受分隔符 |
| `os` | 是 | `linux`、`darwin`、`host` | `host` = 跟随编译器宿主 |
| `arch` | 是 | `arm64`、`x64`、`host` | 同上 |
| `source` | 否 | 目录，相对清单 | 默认 `src`；源码根 |
| `version` | 否 | 字符串 | 仅 `yh version` 展示；未声明时输出 `<name> (未声明 version)` |
| `author` | 否 | 字符串 | 登记用，不参与构建 |

校验与诊断原文：

- 缺节 → `缺少 [project] 节`
- `name` 缺失或为空 → `project.name 必填且非空`
- `name` 首字符非法 → `project.name 必须是标识符（字母或下划线开头）`
- `name` 含其它字符 → `project.name 只能是字母、数字与下划线`
- `os` 缺失/为空 → `project.os 必填（linux|darwin|host）`
- `os` 不在枚举 → `project.os 只能是 linux、darwin 或 host`
- `arch` 缺失/为空 → `project.arch 必填（arm64|x64|host）`
- `arch` 不在枚举 → `project.arch 只能是 arm64、x64 或 host`
- 未知字段 → `project 未知字段: <字段名>`

`os`/`arch` 是**默认输出目标**：命令行给了 `--target` 时以命令行为准，否则用清单的
组合；不被支持的组合报 `project.os/arch 组合不受支持`。

## 6. `[dependencies]`

```toml
[dependencies]
util = { path = "../libs/util" }
```

- 键是**依赖键**，只用于跨项目限定导入 `KEY.MOD`（`import util.string;`）。
- 值是内联表，且必须带 `path`；其它形态报 `依赖必须是 { path = "..." } 表`。
- `path` 相对清单目录解析，递归装载依赖的依赖；检测环（`依赖环：项目正在装载中`）
  并按规范化路径去重。
- 名字解析三层：**本项目 → 标准库 → 直接依赖**。限定导入直接查依赖键；多个直接
  依赖提供同名模块时报 `模块名歧义（多个直接依赖提供）: <名字>`。
- 依赖项目的 `[link]`、`[env]` 只对**它自己**生效，不会渗到根项目的链接参数里；
  依赖项目也不能作为入口。

## 7. `[link]` 与 `[link-<os>-<arch>]`

只写**具体库文件**，不写 `-l` 库名（系统库名走 `[c].libs`）。

```toml
[link]
core = ["vendor/lib/libcore.a"]

[link-darwin-arm64]
core = ["vendor/lib/darwin-arm64/libcore.a"]
extra = ["vendor/lib/darwin-arm64/libextra.a"]
```

规则：

- 组名是裸键，长度 1..128，字符集与 `--link` 组名一致：字母、数字、`_`、`-`。
- 值是字符串数组；每个元素非空、长度 < 1024 字节。
- **只有根项目生效**；依赖项目的 `[link]` 被忽略。
- 目标节同名组**整体替换**公共组，新组名追加到末尾（顺序 = 公共组声明序 → 目标组
  追加序）。
- 相对路径基于清单目录，读入时用 `realpath` 规范化后做格式与架构校验。
- 库后缀必须匹配当前目标：

  | 目标 | 静态 | 动态/stub |
  | --- | --- | --- |
  | 全部 | `.a` | — |
  | linux | `.a` | `.so`、带版本号 `.so.N` |
  | darwin | `.a` | `.dylib`、`.tbd`（链接期文本 stub） |
  | windows | `.lib`（COFF 归档） | `.dll`（PE） |

- 默认链接全部有效组；`build`/`run` 的 `--link <组名>` 可重复，只选点名组，未知组报
  `未知的 --link 组: <名>（可用组: ...）`。
- `check` 只校验 schema，不检查库文件是否存在；`build` 只检查**选中**的组，
  于是「未选组的库缺失」不会误报。
- 链接顺序：对象 → `[link]` 库 → `[c].libs` → 系统库；ELF 把选中库放进同一个
  `--start-group`，Darwin 按声明顺序。
- 库文件路径可写 `${NAME}`（见 §10），展开后再按上面的绝对/相对规则解析。

诊断原文：`非法的链接节名: <节名>`、`[link] 组名长度必须在 1..128 之间`、
`[link] 重复的组名`、`[link] 组值必须是字符串数组`、
`[link] 库文件路径必须非空且小于 1024 字节`、
`库文件不存在或无法解析（组 <组>，文件 <路径>)`、
`库文件后缀不符合当前目标（.a/.so/.dylib/.tbd）`、`无法读取库文件`、
`静态库不是普通 ar 归档`、`DLL 不是 PE 镜像`、`共享库不是 ELF64 小端文件`、
`dylib 架构与当前目标不符`、`库文件架构与当前目标不符`。

## 8. `[link-options]` 与 `[link-options-<os>-<arch>]`

```toml
[link-options]
whole = ["core"]
```

- 只支持 `whole` 一个字段（其它键报 `[link-options] 只支持 whole 字段`）。
- `whole` 是组名数组，把这些组按整库加载（`-all_load`/`--whole-archive` 语义）；
  引用了不存在的组报 `[link-options].whole 引用了不存在的组`。
- 公共 `[link-options]` 对所有组生效；`[link-options-<os>-<arch>]` 只对「公共组」与
  「该目标组」同名组生效（判定条件是 `组.target == 0 || 组.target == 本节目标`）。
- 节名不在上表 7 个目标键里报 `非法的链接选项节名`。

## 9. `[c]`

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `sources` | 字符串数组 | 每次构建编译的 C 源文件，后缀必须 `.c` |
| `objects` | 字符串数组 | 直接交给链接器的预编译对象，后缀必须 `.o` |
| `libs` | 字符串数组 | 按声明顺序传给链接器的系统库名，不带 `-l` |

校验：

- 未知字段 → `[c] 未知字段（仅支持 sources、objects、libs）`
- 值不是字符串数组 → `[c] sources、objects、libs 必须是字符串数组`
- 路径为空或以 `/` 开头 → `[c] 路径必须是非空的项目相对路径`
- 路径含 `..` 段 → `[c] 路径不能含 .. 目录段`
- 后缀不符 → `[c] 路径扩展名不符合 sources/objects 要求`
- 文件不存在 → `[c] 配置路径对应的文件不存在`
- `libs` 元素只能是普通名字（字母、数字、`_`、`-`）→ 否则
  `[c] libs 元素必须是普通系统库名`

Windows 目标上，用到 C 运行时的项目还要在 `[link-windows-x64]`/`[link-windows-arm64]`
里显式带上 VC 运行时归档（零 CRT 链接默认只带 kernel32 与栈探测桩）。

## 10. `[env]`

清单内的**环境变量默认值**（2026-11-09 引入）：

```toml
[env]
YH_LLVM_ROOT = "~/Library/Caches/yh/llvm-migration"

[link]
bridge = ["${YH_LLVM_ROOT}/llvm-host-darwin-aarch64/libyh-llvm-bridge.a"]
```

- 查找顺序：**进程环境 → 本项目 `[env]`**。所以同一份清单在每台机器/每个 CI 上都能
  用真实环境变量覆盖，不必改文件。
- 值必须是字符串 → 否则 `env 值必须是字符串: <键>`。
- 键名必须是合法变量名（字母或下划线开头，其后字母、数字、下划线）→ 否则
  `env 变量名非法: <键>`。
- 值原样保存：不做路径规范化，也不递归展开；绝对/相对语义由引用处决定。
- 目前唯一消费者是 `[link]` 路径里 `${NAME}` 的展开（见 §7）。变量缺失时
  `${NAME}` 原样保留，使「库文件不存在」诊断直接显示该设置哪个变量。
- 依赖项目的 `[env]` 只对它自己的清单生效。

## 11. 源码扫描与模块头

清单的 `source`（默认 `src`）是源码根，扫描规则：

- 只收 `*.yh`；跳过 `tmp/` 与 `.build/`（构建产物、测试入口不是用户源码）。
- 子目录递归，但**含 `project.toml` 的子目录不进入**（嵌套项目边界）。
- 每个文件必须以 `module <名>;` 开头（`项目源码内的文件必须以 module 声明开头`）；
  `module` 之后才是 `import`，且 `module` 只能出现一次。
- 文件名可以带目标后缀：`*.linux.yh` / `*.darwin.yh` / `*.windows.yh` 与
  `*.arm64.yh` / `*.x64.yh`，只把匹配当前目标的文件编进来；新增此类标记必须先登记
  在编译器里，否则会被所有目标编入。
- `*.test.yh` 是测试文件：生产构建跳过，`yh test` 才编译；扫描顺序里排在非测试文件
  之后。
- 同一模块名可以跨文件/跨目录合并为一个模块；模块名为 `main` 的那个是入口
  （`yh build`/`yh run` 的入口），一个项目至多一个 `main` 模块。

## 12. 装载顺序与校验时机

`load_project()` 的步骤固定（顺序本身是契约）：

1. 规范化项目根、依赖环与重复装载检查；
2. 读 `project.toml`，解析 TOML 子集；
3. 校验 `[project]`（必填、标识符、目标枚举、未知字段）；
4. 快照并校验 `[c]`；
5. 快照并校验 `[link]` / `[link-<os>-<arch>]`，再解析 `[link-options]` 的 `whole`；
6. 快照并校验 `[env]`；
7. 快照 `[dependencies]` 后递归装载依赖（子项目会重置 TOML 解析区，所以第 4-6 步
   必须先做快照）；
8. 扫描源码根、索引模块、分类测试专用导入；
9. 标记入口模块，项目状态置为「已装载」。

因此**清单错误在编译任何源码之前就会暴露**，诊断指向清单行号。

## 13. 诊断风格

- 一律 `<清单路径>:<行>: 错误: <中文消息>`，消息里带出具体值（字段名、组名、路径、
  变量名）。
- 不静默降级：类型不对、字段不认识、组名非法、文件不存在都直接失败。
- 链接期诊断额外带「组 + 原始清单路径」，因为同一路径可能来自不同组。

## 14. 与构建、链接、缓存的关系

- 清单解析结果进 `PProj` 快照（名字、源码根、目标、依赖、C 输入、链接组、env），
  后续所有阶段只读快照。
- 清单**不直接**参与缓存键：缓存键由解析结果派生——目标 triple、模块源码内容、
  链接组的「realpath + 文件大小/时间戳 + 内容摘要」等。所以换库路径或换库内容都会
  改变链接键并触发重链（`tests/modules` 的 `linkgroups` 用例覆盖）。
- 链接库只在最终链接阶段读取；`check` 不触碰库文件。

## 15. schema 演进规则

新增字段/节必须同时完成：

1. 在对应 loader 里登记白名单（否则 `[project]`/`[c]` 的未知字段报错会拦下它）；
2. 给出取值校验与诊断原文；
3. 在装载顺序里找对位置，注意 `[dependencies]` 递归会重置 TOML 解析区，必须在它之前
   快照；
4. 加 fixture 用例：`tests/modules/projects/<名字>/` + `tests/modules/build-check.py`
   的 `case(...)`（失败用例走 `kind="fail"` + `msg=`）；
5. 更新本文与 [yh-编译流程-当前实现](yh-编译流程-当前实现.md) 的装载步骤。

另有一条自举约束：清单里的新语法/新语义要能被**上一颗已发布种子**读通，否则
`just build`（用种子冷编）会失败。`[env]` 属"旧种子忽略未知节"的情况，安全；路径里写
`${NAME}` 则不行——旧种子会把它当字面路径（详见 §16 的演进记录）。

## 16. 边界与未实现

- 远程依赖、版本求解、锁文件：未实现，只承诺本地 `{ path = ... }`。
- `[env]` 只用于清单内 `${NAME}` 展开，不导出给子进程（不会被 `cc`/`ar`/链接器继承）。
- `[link]` 的库文件后缀按**当前输出目标**判定，因此同一份清单交叉编译时要保证对应
  目标的归档已存在（`[link-<os>-<arch>]` 就是为此存在的）。
- 单文件模式不读清单，因此不享受依赖、`[c]`、`[link]`、`[env]` 的任何能力。

## 17. 参考实现

| 关注点 | 位置 |
| --- | --- |
| TOML 子集解析 | `compiler/build/toml.yh` |
| 清单 schema、发现、扫描、`[c]`、`[env]` | `compiler/build/project_index.yh` |
| `[link*]` 组与 `whole` | `compiler/build/project_link.yh` |
| 项目模型结构（`PProj`/`PLinkGroup`/`PEnv`…） | `compiler/proj/proj_00_model.yh` |
| 三层名字解析、依赖键 | `compiler/build/project_resolve.yh` |
| 链接路径解析、`${NAME}` 展开、格式校验 | `compiler/link/link_inputs.yh` |
| 验收用例 | `tests/modules/projects/`、`tests/modules/build-check.py` |
