# 0.0.14-rc.1 — 模块身份与路径导入、统计机制删除、list 标准库

预发布候选（prerelease）。相对 0.0.13 正式版，本 RC 完成模块身份重构（同名模块
不再合并 + 路径导入）、`compiler/` 源码归组、编译统计机制删除，并新增 `libs/list`
动态列表标准库；发布前修复了两个会阻塞 rc 的缺陷（跨模块 CT 正文别名解析回归、
release 工作流的版本常量路径失效）。种子链：0.0.13 → 0.0.14-rc.1（rc.1 由 0.0.13
正式版种子构建）。

## 主要内容

**1. 模块身份与路径导入**

- 模块身份从「(项目, 模块名)」改为「(项目, 名字, 目录)」：`proj.PMod` 增
  `dir_off/dir_len`，`proj/table.yh` 增 `module_at_dir`/`module_count_in_project`；
  同名模块不再静默合并。
- 导入解析：裸名导入在本项目内命中多个同名模块时报「模块名歧义」；两段
  `import A.B` 先试依赖键 A，未命中再按本项目目录 `A/B`；三段及以上只按目录；
  路径末段必须等于模块声明名。绑定名仍是末段，`as` 可改。
- 重名模块的产物标签/符号后缀追加目录指纹（FNV-1a 低 32 位 → 8 位十六进制），
  模块 ActionID 混入模块目录；无重名项目的命名与之前逐字节一致。
- `docs/yh.g4` 补 `moduleHead/moduleDecl/importDecl/modulePath`，新增语料
  `tests/yh/01-toplevel/05_module_head.yh` 与 `dupmodseg`/`dupbarenames`/`dupmisname`
  三个项目 fixture。

**2. 源码归组与项目清单**

- `compiler/` 归组为 `build/`、`cmd/`、`proj/`：`cmdline` → `main`（`cmd/yh/`）、
  `cache` → `build/cache/`、`cmd/driver.yh` → `cmd/yh/yh.yh`、
  `proj/proj_0X_*.yh` → `proj/{model,table,path,art}.yh`。
- `project.toml` 新增 `[env]` 环境变量默认值。
- testkit 修复：非 compiler 项目不再无条件生成 `import proj`，`yh test` 在普通
  项目与 `libs/` 恢复可用。

**3. 编译统计机制删除**

- 删除 `--stats` 与 `YH_STATS`、`support.CompileStats`/`stats()`、`build/stats_print.yh`、
  各模块计数与计时字段，以及只服务统计的 `tools/{perf-baseline,perf-invalidation,
  perf-scaling}.py`、`.github/workflows/perf.yml` 与相关门禁用例。
- `tests/modules/build-check.py` 删除 10 个纯统计用例（135 → 125），其余断言改为
  产物字节/运行值判定；裸调用 `yh` 的退出码恢复为 2。

**4. 标准库：`libs/list`**

- 无泛型约束下的动态列表：连续字节块 + 运行期元素宽度（必须来自 `sizeof(T)`），
  元素地址以 `*void` 暴露。`List` 4 个公开字段（data/count/capacity/element_size），
  `Status` 区分 invalid_argument/overflow/out_of_memory/bounds。
- 10 个 `pub` 函数：`make`/`release`/`clear`/`reserve`/`element_at`/`push`/
  `push_all`/`pop`/`insert`/`remove_at`；扩容 = `memory.alloc` + 复制 + 释放，
  起步 16 槽、容量翻倍；插入/删除用模块内重叠安全复制（Windows 零 CRT 上
  `libc` 的 `@[extern] memset/memmove` 与 prelude 重复符号，故不依赖 `libc`）。
- 11 个语言内用例；`just test-libs` 的 O0/O2 均通过。

**5. 工具与构建**

- LLVM 闭包缓存移到项目外（macOS `~/Library/Caches/yh/llvm-migration`，其它平台
  `$XDG_CACHE_HOME|~/.cache/yh/llvm-migration`），并新增「已封装」标记，`just llvm-host`
  与 seed-build 命中标记后不再全量校验 68 个归档。
- 新增 `just codeflow`（`tools/yh-codeflow.py`）：模块依赖/调用强度/文件调用三视图，
  自包含 HTML，自测 4 条进 `just test`。
- 删除 `tools/arch-check.py` 及其门禁；依赖方向、状态/资源预算与版本常量一致性
  改为评审基准。
- 文档统一为 17 模块 / 180 文件 / 76 条依赖边（2026-11-10 实测）。

## 发布前修复（本 RC 阻塞项）

1. **跨模块 CT 正文别名解析回归**：`0e4f59b` 给 `support.ImportEnt` 增加了
   `path_off/path_len`，但 `comptime.CtImportRow` 零拷贝镜像仍是 8 字段，导致
   `ct_import_row` 读取 `alias_off/alias_len` 时整体错位。表现为 `@[comptime]` 函数
   正文里的 `geometry.Type` 报「点号左侧不是导入的模块名」/「引用了未声明的名字」，
   `comptimecross` 的 `ct5b-cross-module-body` 构建失败。修复：`CtImportRow` 补齐
   两个 path 字段，`ct_type_layout_ok` 增加 `sizeof(ImportEnt) ==
   sizeof(CtImportRow)` 校验。
2. **release 工作流版本常量路径失效**：`c7ca83d` 把 `compiler/cmdline/cmdline.yh`
   迁到 `compiler/cmd/yh/cmd_base.yh` 后，`release.yml` 的 prepare 仍读旧路径，
   打任何版本 tag 都会在「版本号一致」检查处红。修复：同步 `.github/workflows/
   release.yml` 与 `AGENTS.md` 的路径。
3. **build-check 的 cinterop fixture 依赖未入库生成物**：`vendor/prebuilt.o` 被
   `.gitignore` 的 `*.o` 排除，干净 checkout 上 `[c] objects` 必然报路径不存在。
   修复：`copy_proj` 把 fixture 交给编译器前按需编译 `vendor/prebuilt.c`。
4. **首轮 CI 暴露的三处环境/依赖问题**（本地 `test-llvm-darwin` 与 Windows 日志定位）：
   - `tools/link-closure.py check` 仍读仓库内 `tmp/llvm-migration`，闭包移到项目外后
     报「缺少宿主记录」；改为跟随 `host_record_path`（缓存根）。
   - `llvm-darwin-default.py` 的 `print` 仍引用已删除的统计变量（`checked`/
     `emitted`/`fallback`），NameError；改为产物/汇编断言描述。
   - `libs/list` 同时 `import memory` 与 `import libc`，Windows 零 CRT 上 libc 的
     `@[extern] memset/memmove` 与 prelude 运行时符号重复（lld-link duplicate
     symbol）；按设计 §12 回退方案改为模块内 `list_copy_overlap`，list 只依赖
     `memory`。

## 验收

- `just test`：语法正例 83/83、反例 49/49；run 372/374（2 例平台跳过）、
  fail 140/140、pass 10/10；libs 测试 151 passed；compiler-tests 8/8；
  build-cache、C4/C6 全局缓存、code-stats 6/6、codeflow 4/4 全绿。
- `just selfhost-native`：模块固定点一致（候选 cc3→cc4，51 个产物）；cc4 自解析
  180 个源文件；project cases **125/125**；LA0 O0/O2、C4/C6、并发项目扫描全绿。
- `just test-libs`：O0/O2 全绿（toml conformance 681/681、string/num/fmt 专项与
  安装验收）。
- 跨模块消费者 `tmp/list-consumer`（`import list` + `list.status_ok` + `libc.qsort`）
  退出码 0。
