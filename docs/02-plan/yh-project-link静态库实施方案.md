# yh project.toml 库文件链接实施方案（v2）

日期：2026-10-21。状态：**普通项目已实施；编译器自举闭包迁移设计已交付，下一轮执行。**

用户确认：`[link]` 中必须写具体库文件路径；相对路径以 `project.toml`
所在目录为基准并规范化为绝对路径。决策摘要见
[ADR-0016](../adr/0016-yh项目静态库分组链接.md)。

## 1. 目标

让 `yh build` / `yh run` 按项目清单自动把平台对应的 `.a`、`.so`、`.dylib`
或 `.tbd` 加入最终链接；`yh check` / `yh list` 只校验配置结构，不要求库文件
已安装。

## 2. 清单格式

### 2.1 `[project].os/arch`

```toml
[project]
name = "app"
source = "."
os = "linux"     # linux | darwin | host
arch = "arm64"   # arm64 | x64 | host
```

- `os` / `arch` **必填**。
- 显式值决定默认输出目标；`--target` 给出时以 `--target` 为准，并据此选择
  `[link-<os>-<arch>]`。
- `host` 表示跟随编译器宿主平台，供跨平台仓库的公共项目和测试夹具使用；
  它不是用户程序选择“任意平台”，而是明确“本机平台”。

### 2.2 `[link]` 命名组

```toml
[link]
core = ["vendor/lib/libcore.a"]
crypto = ["vendor/lib/libcrypto.so"]
```

- 组名是 TOML 裸键：`A-Z`、`a-z`、`0-9`、`_`、`-`，非空、大小写敏感。
- 组值是**字符串数组**，元素必须是具体库文件路径；不能写库名、表项、
  glob 或环境变量。
- 相对路径以声明它的 `project.toml` 为基准；允许绝对路径。读取时用
  `realpath` 得到绝对真实路径；诊断保留清单原始路径。
- 空组 `group = []` 合法。
- 只有根项目的 `[link]` 生效；依赖项目的 `[link]` 忽略。

### 2.3 目标覆盖表

只允许当前四个平台组合：

```toml
[link-linux-arm64]
core = ["vendor/lib/linux-arm64/libcore.so"]
extra = ["vendor/lib/linux-arm64/libextra.a"]

[link-darwin-arm64]
core = ["vendor/lib/darwin-arm64/libcore.dylib"]
```

- 其他 `[link-*]` 节名（包括 `[link-options]`）直接报错，避免拼写错误被忽略。
- 同名组整体替换公共组，并保持公共组位置；新组按目标表声明顺序追加。
- 不同目标的组只按最终目标选择，未选目标的文件不要求存在。

## 3. 链接行为

- 默认链接全部有效组，按合并后的声明顺序；`--link <组名>` 可重复，按命令行
  首次出现顺序只选择点名组。
- 组内文件按数组顺序；同一 `realpath` 只链接一次。
- 链接顺序：
  ```text
  yh 对象 → C 对象 → [link] 库 → [c].libs → -lm / 系统库
  ```
- ELF 目标把所有选中的库放进同一个 `--start-group … --end-group`，保持顺序；
  共享库也放在其中。Darwin 没有等价 group，按声明顺序直接传入。
- `.a` 按普通静态库按需加载（暂不实现 whole）；`.so` / `.dylib` 动态链接；
  `.tbd` 只作为 Darwin 链接期 stub。
- 不自动写 rpath。`yh run` 临时把选中 `.so` / `.dylib` 所在目录加入本次
  子进程的 `LD_LIBRARY_PATH` / `DYLD_LIBRARY_PATH`；不修改二进制。
- 共享库不会“静态链进”二进制，只形成动态依赖。

### 3.1 后缀与格式

- Linux：`.a`、`.so`、`.so.<版本>`
- Darwin：`.a`、`.dylib`、`.tbd`
- 轻量检查：
  - `.a`：普通 `!<arch>\n`，Darwin fat 容器接受；
  - Linux `.so`：ELF64 小端头 + `e_machine`；
  - Darwin `.dylib`：thin/fat Mach-O 头 + 目标 cputype；
  - `.tbd`：非空文本 stub。
- 成员级归档架构和损坏交给链接器。

## 4. CLI 与检查时机

- `yh build` / `yh run` 支持 `--link <组名>`；`check` / `list` / `version`
  收到 `--link` 明确报错并退出 2。
- 库项目（无 `module main`）收到 `--link` 明确报错。
- `yh run` 只允许目标平台与宿主一致；跨目标用 `yh build`。
- 只检查当前目标下最终选中的组；未选组缺文件不报错。
- `check` / `list` 校验 `[project].os/arch` 与 `[link]` schema，不检查库文件。

## 5. 缓存

`.build/.../manifest/link-libs.manifest` 记录每个选中库的：

```text
mtime_sec mtime_nsec size digest realpath
```

后续构建先比较路径与 `mtime/size`，不变就复用摘要；变化才重新读取内容并
计算 FNV-1a 摘要。库顺序、类型和摘要进入最终链接键；`--link` 选择、库内容
或路径变化只触发重链，模块对象继续复用。

## 6. 实施落点

- `compiler/cmd/project_link.yh`：平台字段、`[link]` schema、目标表合并辅助。
- `compiler/cmd/link_inputs.yh`：选择、路径、后缀/格式、摘要 manifest、
  argv 素材、`yh run` 运行库路径。
- `compiler/gen/model.yh`：`PLinkGroup` / `PLinkItem` 与 `PProj` 快照。
- `compiler/cmd/project_index.yh`：项目目标与链接配置装载。
- `compiler/cmd/link_cache.yh`：链接顺序、start-group、链接键。
- `compiler/cmd/module_build.yh` / `driver.yh`：CLI、库项目与跨目标检查。

## 7. 测试

- `tests/modules/projects/linkgroups`：公共组 + 目标组覆盖、`--link` 选择、
  未选/选中缺文件、同路径换内容重链、`check` 不检查库文件。
- `tests/modules/projects/linkshared`：`.so` / `.dylib` 动态链接与
  `yh run` 运行库路径。
- `tests/modules/projects/linkbad|linkmissingtarget|linkbadsuffix`：严格
  节名、必填平台字段、后缀诊断。
- `tests/modules/build-check.py` 接入上述用例。
- 本机 `make test`、`make selfhost-native` 全绿后才滚种子。

## 8. 编译器自举迁移设计（下一轮）

当前 `compiler/` 仍使用 `YH_LLVM_SELFHOST_FLAGS` 注入 bridge / LLVM / lld。
下一轮迁移时：

1. 先把闭包拆成“归档组”和“运行库参数”两部分：归档进入
   `[link-<os>-<arch>]`，`-lc++`、`-lstdc++`、`-lpthread` 等仍由构建机配方
   提供，并排在归档之后。
2. 新 seed 一旦读到 `[link]` 就进入 manifest-only，不再追加旧归档；旧 seed
   引导第一代候选时仍使用旧闭包。
3. `tools/llvm-host.py` / `tools/llvm-darwin-host.py` 核对清单与实际 SDK
   归档闭包一致；`make` 在缺闭包时给出 `make bootstrap` 诊断。
4. 迁移后重新验证固定点、语料、模块门和种子路径检查，再滚两端种子。

本文件所述普通项目能力已实现；第 8 节是下一轮计划，不是当前已交付结果。
