# 0.0.14 — 模块身份与路径导入、统计机制删除、list 标准库

正式版。本版完成模块身份重构（同名模块不再合并 + 路径导入）、
`compiler/` 源码归组、编译统计机制删除，新增 `libs/list` 动态列表，
并修复 rc.1 暴露的跨平台门禁问题。种子链：0.0.13 →
0.0.14-rc.1（未发布）→ 0.0.14-rc.2 → 0.0.14（正式版由 0.0.14-rc.2
的四端种子构建）。

## 主要内容

**1. 模块身份与路径导入**

- 模块身份从「(项目, 模块名)」改为「(项目, 名字, 目录)」，同名模块
  不再静默合并；裸名歧义、`import a.cache` 路径导入、末段与目录不匹配
  都有稳定诊断。
- 重名模块的产物标签/符号后缀追加目录指纹（FNV-1a 低 32 位），模块
  ActionID 混入模块目录；无重名项目的命名与之前逐字节一致。
- `docs/yh.g4` 补 `moduleHead/moduleDecl/importDecl/modulePath`；
  新增 `dupmodseg`/`dupbarenames`/`dupmisname` fixture。

**2. 源码归组与项目清单**

- `compiler/` 归组为 `build/`、`cmd/`、`proj/`：`cmdline` → `main`
  （`cmd/yh/`）、`cache` → `build/cache/`、`proj_0X_*.yh` →
  `proj/{model,table,path,art}.yh`。
- `project.toml` 新增 `[env]` 环境默认值；`yh init` 生成项目骨架。
- testkit 修复：非 compiler 项目不再无条件 import `proj`。

**3. 编译统计机制删除**

删除 `--stats`/`YH_STATS`、`support.CompileStats`、`build/stats_print.yh`、
各模块计数与计时字段、只服务统计的 perf 工具/工作流/门禁用例；
`tests/modules/build-check.py` 135 → 131 例，其余断言改为产物字节/运行值。

**4. 标准库：`libs/list`**

无泛型动态列表：连续字节块 + 运行期元素宽度（`sizeof(T)`）+ `*void`
元素地址；10 个 `pub` 函数与 11 个语言内用例；扩容 = `memory.alloc` +
复制 + 释放，插入/删除用模块内 `list_copy_overlap`（Windows 零 CRT 上
libc 的 `@[extern] memset/memmove` 与 prelude 重复符号，故不依赖 libc）。

**5. 工具与构建**

- LLVM 闭包缓存移到项目外 + 「已封装」标记；`just llvm-host`/seed-build
  命中标记后不再全量校验。
- 新增 `just codeflow`（模块依赖/调用强度/文件调用三视图，自包含 HTML）。
- 删除 `tools/arch-check.py` 及其门禁。

## rc.1 → 正式版的发布修复

- Darwin：`link-closure.py check` 跟随缓存根；`llvm-darwin-default.py`
  清理统计残留变量。
- Windows：`PProj.envs/env_n/env_cap` 未初始化（`[env]` 崩溃根因）；
  无 CT 正文模块的 `.s.ct` 缺失容忍；缓存命中时跳过 session `.s.i`
  发布；`proj.canon` 统一反斜杠为 `/`。
- 发布：`release.yml` 版本常量路径（`cmdline` → `cmd/yh/cmd_base.yh`）；
  Windows 打包 `tar -f` 绝对路径被当远程主机（改用相对输出名）；
  build-check 的 cinterop 按需生成 `prebuilt.o`（Windows 跳过）。

## 已知限制

- Windows 上 `u8-dup-module-path-import`（同名模块+路径导入）仍有对象
  缓存提交遗留，`build-check` 的 `WINDOWS_SKIP` 暂跳该例；见
  `docs/todo.md`，修复后移除跳过。
- 全局内容缓存在个别本地环境下会命中不可用模块产物（`link/context.yh`
  `LLVM lowering set_argv0`），`YH_CACHE=off` 或 `yh cache clean` 可恢复；
  属既有缓存键/产物语义待排查项。

## 验收

- `just test`：语法 83/83 + 49/49；run 372/374（2 跳过）、fail 140/140、
  pass 10/10；libs 测试 151 passed；compiler-tests 8/8；build-cache、
  C4/C6、code-stats、codeflow 全绿。
- `just selfhost-native`：固定点一致（51 产物）、cc4 自解析 180 文件、
  project cases 125/125、LA0 O0/O2。
- `just test-libs` O0/O2、`just test-llvm-darwin` 全绿。
- 四端 CI（0.0.14-rc.2）：darwin-arm64 / linux-x64 / linux-arm64 /
  windows-x64 全绿并产出四端资产；正式版 0.0.14 归档发布验收见
  `docs/finish.md`。
