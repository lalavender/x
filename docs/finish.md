# finish

滚动日志：只保留最近三天（当前为 2026-11-06 ～ 2026-11-08）的交付记录，靠前条目为最新状态。
更早条目按批次归档在
[finish 历史归档](01-finished/finish-历史归档-2026-09-27至2026-10-21.md)
（文件名区间是首档范围，内容已含 2026-10-22 ～ 2026-11-03 的两批迁入条目）；新增条目写在最前。
2026-11-06 清理：此前文件里残留 2026-09-27 ～ 2026-10-21 的 381 条归档副本
（2026-10-24 首次归档只复制未从 finish.md 删除），已删除；并补齐 2026-10-22 残留与
2026-10-26 ～ 2026-11-03 批次的迁移，见归档文件的「2026-11-06 迁入」段。

## 2026-11-10：errors 诊断基座模块（叶子基座，修复 CI 四端红）

**结果**：
- CI run 42756269175 四端同挂的根因是 `8a398d0` 新增的 `compiler/errors/api.yh`
  无人 import（孤儿模块 → 按需编译不产出），而 `tools/selfhost_snapshot_gate.py`
  按源码树扫描全部 module 声明计算预期产物 → cc2 缺 `iface/yh-errors.s.{i,ct}`
  与 `llvm/yh-errors.ll`。修复方式按用户决策落成**叶子基座**：`errors` 不 import
  任何模块，持有 `DiagCtx` 单例与 `diag`/`fail`/`fail_path`/`err_lc`/`warn_lc`
  五个诊断入口（渲染逻辑自 support 原样搬迁，输出逐字节不变），全编译器一律
  `import errors` 报错；`support` 退位为通用工具层，迁移期五个临时委托已在
  Task 6 删除，不留双入口。
- 路径槽位用「字段地址」而非路径快照：`state_init`/`session_reset` 调
  `errors.set_path_slot(&g_support.src.path)`，`err_lc`/`warn_lc` 调用时刻读
  `*g_path_slot`，14 处直写 `src_ctx().path` 的换源点自动可见。
- 迁移范围：token/lex/parse/ast/check/comptime（32 文件）→ backend/link（7）→
  build（19，含 proj/project_dir）→ testkit/cmd（6），合计 64 文件；fixture
  `gen-split`、`llvmlower` 的诊断探针同步改走 `errors`。
- 文档归口：`compiler/README.md` 新增 errors 模块表、support 表去掉
  `DiagCtx`/`fail`/`support/diag.yh`；`docs/03-design/yh-编码规范.md` 的
  `gen.fail`/`gen.sem_err` 历史名改为 `errors.fail`/`errors.err_lc`/
  `token.err_tok`。

**验证**（主树当时被并发会话的 `compiler/build` list 重构占用、不可构建，
门禁在 `tmp/task6-tree` 快照树执行：HEAD + 本任务改动，并剔除 `96f252c`
误带入的两行未使用 `import libs.list`）：
- 冷编 `just build` 通过（新 `YH_CACHE`、清空 `.build`）。
- `just test` 全绿（ANTLR 83/83+49/49、run 372/374 跳过 2、modules 全部通过、
  libs、compiler-tests 9/9、fmt、C4/C6、code-stats 6/6、codeflow：模块 18 /
  文件 177 / 函数 1846 / import 边 90）。
- `just selfhost-native`（`SKIP_CORPUS=1`）两代固定点通过。

**附**：迁移排查中发现既有 C4/C5 缓存一致性问题（热全局缓存下改模块内字符串
字面量后，函数级记录/检查切片被错误复用），已在 `docs/todo.md` 记为 P1，
与本次迁移无关。

## 2026-11-10：合并 0.0.14 主线（api.yh 迁移 × 发布修复）

**结果**：
- 把本地 `api.yh` 公开面迁移（含 `proj → build/proj`、移除 `yh list`）与
  `origin/llvm` 的 0.0.14 发布提交（9 个）合并；版本号统一为 `0.0.14`，
  `[env]` 按上游根因修复（`PProj.envs/env_n/env_cap` 在 `add_project` 清零）恢复。
- 冲突处理：`compiler/proj/{path,table}.yh` 保留本地删除，把上游的
  `canon` 反斜杠归一与 `add_project` 的 `[env]` 清零移植到
  `compiler/build/proj/api.yh`；`YH_VERSION_TEXT` 改在 `compiler/cmd/yh/api.yh`；
  `docs/01-finished/release-0.0.14-rc.2.md` 取上游版本（本地旧稿描述的是
  「删除 [env]」的已废弃方案）；`docs/{todo,finish}.md` 两侧条目并存。
- `build_scheduler.yh` 自动合并保留上游三处接口发布修复；`justfile` 的
  Windows tar 相对路径、`tests/modules/build-check.py` 的 Windows 跳过与
  stdout 诊断随合并进入。
- 补齐迁移遗留：`tests/modules/build-check.py` 的 `CORE_DIRS` 增加
  `proj → build/proj`，`llvmtarget/llvmfront` fixture 改用 `core_src("proj")`
  （原先直接切已不存在的 `compiler/proj`）。
- 环境处置：合并后首次冷编在旧全局缓存上触发既有缓存缺陷（见 docs/todo.md
  「函数 IR 缓存缺编译器身份」），`yh cache clean` 后 `just build` 恢复。

**验证**：
- `just build`（清空全局缓存后冷编）通过，`./yh --version` = `yh 0.0.14`。
- `just test` 全绿（ANTLR 语法 83/83+49/49、run 372/374、modules 全部通过、
  libs 171、compiler-tests 8/8、fmt 10、C4/C6、code-stats 6/6、codeflow 自洽）。
- `just selfhost-native` 未在本机跑，按仓库约定交 CI。

## 2026-11-10：编译器 18 个模块公开面迁移到 api.yh

**结果**：
- `compiler/` 18 个模块（ast、backend、build、build/cache、build/proj、builtin、
  check、comptime、errors、ir、lex、link、lower、main、parse、support、
  testkit、token）各自新增 `<模块目录>/api.yh`：模块的 pub 声明（fn/struct/
  union/enum/type/const）与全部 `@[extern]` 声明集中到该文件；其余主题文件只留
  私有实现。`api.yh` 按文件名字节序排在模块最前，公开实现可以调用后续文件的
  私有函数、引用后续私有类型与全局（类型在模块内统一登记）。
- 平台分文件按与标准库相同的办法处理：`backend/llvm_bind.*`、`support/
  {clock,argv,console}.*`、`build/cache/lock.*` 的 pub 函数改成私有
  `<name>_impl`，由 `api.yh` 薄包装转发；平台相关的 extern（LLVM 绑定、
  Find*/flock、Windows 控制台）以共享声明进 `api.yh`（同名同签名合一，
  `yh_llvm_version` 等三平台一致的声明只留一份）。
- 被搬空后删除的源文件 23 个（`ast_store`、`ast_view`、`llvm_abi_model`、
  `llvm_bridge`、`cache_key`、`checked_view`、`ct_bind`、`sem_call_literal`、
  `sem_expr`、`ct_enum`、`ct_layout_sched`、`module_snapshot_lower_selftest`、
  `support/{abi_model,buffer,front_stage,layout,pool,source,symbols,target,
  value_rules}`、`token/{base,op}`）；其中 `support/buffer.yh` 与
  `token/op.yh` 原有的 yh test 块迁到同名 `.test.yh`，测试发现不丢。
- 已知例外：`support/tables.yh` 的 `pub const DATA_STR_CAP` 保留在原文件。
  把它移到 `api.yh` 后，`tables.yh` 里的 `let c_data_str_* [DATA_STR_CAP]int`
  全局长数组会触发「编译期常量尚未就绪」（CT 值调度按声明文件做全局初始化，
  跨文件的数组长度常量请求无法就绪）。
- 文档：`docs/todo.md` 增加编译器模块设计文档文件清单刷新项；编码规范 §7 的
  建议性约定（pub 集中 `api.yh`）同样适用本次迁移。

**验证**：
- `just build`：种子冷编通过（默认全局缓存，含编译器全部模块）。
- `just test`：通过——ANTLR 语法层、编译器语法模式、run corpus、modules
  test-check、build-cache、opt-level、libs 171 例、compiler-tests 8/8、
  fmt 插值、code-stats 6/6、codeflow 自洽。
- `cd compiler && ../yh check --target <triple>`：aarch64-apple-darwin、
  x86_64/aarch64-unknown-linux-gnu、x86_64-pc-windows-msvc 四目标全部通过。
- 本环境 `tests/modules/build-check.py` 仍被在建的 `compiler/proj →
  compiler/build/proj` 迁移挡住（`copy_proj` 引用 `compiler/proj`），未作为
  本轮验收；`just selfhost-native` 未在本机跑（按仓库约定交 CI）。

## 2026-11-10：标准库公开面迁移到各模块 api.yh

**结果**：
- `libs/` 18 个模块全部新增 `<模块>/api.yh`：模块的 pub 声明（fn/struct/
  union/enum/type/const）与全部 `@[extern]` 声明集中到这里；其余主题文件只
  保留私有实现与辅助。模块内 `api.yh` 按文件名字节序排最前，公开实现可调用
  后续文件的私有函数、引用后续私有类型与全局（pass1 统一登记）。
- 被搬空后删除的文件：`memory/memory.yh`、`math/math.yh`、`libc/memory.yh`、
  `io/io.yh`、`io/write.yh`、`fmt/interp.yh`、`cli/entry.yh`、`os/base.yh`、
  `os/os.yh`、`os/sleep.yh`、`sys/base.yh`、`string/string.yh`、
  `string/transform.yh`；公开面由各模块 `api.yh` 承担。
- 平台分文件模块（json/net/os/sys/time/toml）：平台无关公开面进 `api.yh`，
  平台差异保留在 `*.<平台>.yh`，并把原 pub 函数改名为私有 `<name>_impl`，
  由 `api.yh` 的薄包装转发（签名在三个平台上逐一对齐后生成）。
- 已知例外（语言能力限制，保留平台文件）：`os.DirReader`/`os.DirReaderResult`
  各平台定义不同；`os.open_dir`/`next_entry`/`close_dir`、
  `sys.spawn_process`/`raw6`/`read_dir_entries`/`getdents64`/`find_first`/
  `find_next`/`find_close`/`fcntl_fd` 只在部分平台存在；`sys/constants.*`、
  `sys/errno.*` 的 pub const 平台取值不同。
- 文档：`yh-标准库设计.md` 新增迁移说明并修正 io/sys/cli/toml/fmt 文件清单；
  `libs/{cli,os,libc}/README.md` 文件表同步；`docs/todo.md` 记录例外收敛与
  各模块设计文档文件清单两项后续。

**验证**：
- `cd libs && ../compiler/.build/yh check`：通过；`--target` 四目标
  （aarch64-apple-darwin、x86_64/aarch64-unknown-linux-gnu、
  x86_64-pc-windows-msvc）全部通过。
- `yh test`（libs）：171 passed（O0）；`tmp/libs-o2` 的 `-O2 test`：171 passed。
- `cd compiler && ../yh build`：构建完成（编译器以 `libs` 为依赖）。
- 环境限制（与本轮无关）：`just build`/`just dev` 的种子对
  `libs/hash/sha256.yh` 报 `LLVM lowering sha256_rotr` 首片不支持；
  `tests/modules/build-check.py` 被在建的 `compiler/proj → compiler/build/proj`
  迁移挡住（`copy_proj` 仍引用 `compiler/proj`）。

## 2026-11-10：记录 api.yh 布局约定（仅文档）

**结果**：在 [编码规范 §7](03-design/yh-编码规范.md) 记录建议性约定——模块的
pub 声明建议集中到 `api.yh`。编译器不检查、不告警；未改代码与测试
（曾实现的检查/警告已按用户要求回退）。

## 2026-11-10：list 标准库按 V 内建数组方法集补齐（L3）

**结果**：
- `libs/list/list.yh` 新增 `ListResult` 与 26 个方法：首尾访问
  （`first`/`last`）、插入/删除（`prepend`/`pop_left`/`delete_last`/
  `delete_many`）、截断与丢弃（`trim`/`drop`/`reset`）、容量
  （`grow_cap`/`grow_len`）、新列表（`clone`/`repeat`/`slice`/`reverse`/
  `sorted`/`filter`/`map`）、原地变换（`reverse_in_place`/`sort`）与查询
  （`contains`/`index`/`last_index`/`any`/`all`/`count`）；公开面 10 → 36 个
  函数，私有辅助新增 `list_result_ok`/`list_result_error`/`list_swap`/
  `list_zero`/`list_build`。
- 需要元素语义的方法收回调：比较 `fn(*void,*void) int`、谓词
  `fn(*void) bool`、变换 `fn(*void,*void) void`（`map` 回调写满结果槽位）。
  回调是普通 yh 函数、必须非空（语言不支持函数指针与 `0` 比较）。
- 方法名按 V 对齐并作为记录在案的命名例外（编码规范 §2.1 动词表不改）；
  已有 10 个方法签名与语义不变。无法对齐的 `pointers`/`str`/`hex`/`wait`/
  深度复制在 README 映射表逐条说明原因。
- 文档：`libs/list/README.md` 增加完整 API 表、V 映射表与新硬规则；list 设计
  文档刷新状态/目标/D9–D10/§6 契约表/§7 实现要点/§8 规则/§9 用法/§10 用例/
  §11 L3/§12 风险；`yh-标准库设计.md` 的 list 小节同步为 36 函数并修正过期
  描述（移位实际用模块内 `list_copy_overlap`，不是 `libc.memmove`）。

**验证**：
- `cd libs && ../yh test --filter list`：31 passed / 0 failed（O0）。
- `tmp/libs-o2` 的 `-O2 test --filter list`：31 passed / 0 failed。
- `just test-libs`：全库 O0+O2、外部 runner 与专项/安装门全绿（exit 0）。
- 未改 `compiler/`、`docs/yh.g4`、prelude 与 justfile。

## 2026-11-10：移除 `yh list` 命令

**结果**：`yh list` 整条命令删除——`compiler/cmd/yh/cmd_list.yh` 文件、`CLI_LIST`
常量、`cli` 子命令声明与 `cli_is_command` 判定、请求分派分支、`mb_cmd_list`
与 `pj_cmd_list` 一并清除；裸 `yh` 用法只剩
`{build,check,run,test,cache,init,version}`。文档同步 README.md、AGENTS.md、
compiler/README.md 与四份 03-design；`tools/cli-golden.py` 删除 `list` 与
`list-link` 用例；`tests/selfhost/bootstrap/native-selfhost.py` 的用法完整性
断言改用 `cache`。

**验证**：`cd compiler && ../yh build` 通过；`yh --help` 不再列出 list，
`yh list` 以用法错误码 2 退出；`just test` 通过。

## 2026-11-10：0.0.14-rc.1 发布准备（版本号、门禁与两个阻塞修复）

**结果**：
- 版本号两处改为 `0.0.14-rc.1`（`compiler/project.toml` 与
  `compiler/cmd/yh/cmd_base.yh` 的 `YH_VERSION_TEXT`），新增
  [release-0.0.14-rc.1](01-finished/release-0.0.14-rc.1.md)。
- 修复跨模块 CT 正文别名解析回归：`0e4f59b` 给 `support.ImportEnt` 增加
  `path_off/path_len` 后，`comptime.CtImportRow` 零拷贝镜像仍为 8 字段，
  `alias_off/alias_len` 读取错位，`@[comptime]` 正文里的 `alias.Type` 报
  「点号左侧不是导入的模块名」。补齐镜像字段，并在 `ct_type_layout_ok` 增加
  `sizeof(ImportEnt) == sizeof(CtImportRow)` 守卫。
- 修复 release 工作流：`c7ca83d` 归组后 `release.yml` prepare 仍读
  `compiler/cmdline/cmdline.yh`，改为 `compiler/cmd/yh/cmd_base.yh`，AGENTS.md
  同步。
- 修复 build-check：`cinterop` fixture 的 `vendor/prebuilt.o` 被 `.gitignore`
  排除，`copy_proj` 现按需编译 `prebuilt.c`，干净 checkout 不再因 `[c] objects`
  缺失而红。
- 本次门禁前清理了本机 868 MB 全局缓存：旧缓存条目会让冷编
  `link/context.yh` 报 `LLVM lowering set_argv0`，`YH_CACHE=off` 不复现；
  `yh cache verify` 显示无损坏，属缓存键/产物语义层面的待排查项。
- 首轮 tag 的 CI（run 42709901928）：linux 两端成功，darwin/windows 失败，
  publish 跳过。重推 tag 三次（rc.1 未生成 Release）；darwin 已修复，
  **Windows 仍未解决**：`compiler-tests` 的 `--emit-module support` 子进程
  0xC0000005（`6469c32` 起、0.0.13 之后的既有回归；`7089690` 的 Windows
  compiler-tests 仍 8/8，`6469c32` 开始 0/8）。`[env]` 顺序/边界/字面量
  三处加固无效，需在 Windows runner 上抓 dump 定位。修复记录：
  1. `tools/link-closure.py check` 在闭包移到项目外后仍读仓库内路径，改为
     `host_record_path`（缓存根）；本地 `just test-llvm-darwin` 全绿。
  2. `llvm-darwin-default.py` 的 print 引用已删除的统计变量（NameError），
     改为产物/汇编断言描述。
  3. `libs/list` 同时 import memory+libc，Windows 零 CRT 上
     `@[extern] memset/memmove` 与 prelude 重复符号；改为模块内
     `list_copy_overlap`，list 只依赖 memory。
  4. `[env]` 相关构建在 Windows 上 0xC0000005（`link-env-manifest`
     与 `compiler-tests` 的 `--emit-module` 子进程）：`[env]` 快照移到
     `[link]` 之前（`${NAME}` 的默认值来源），`pj_load_env_config`/
     `li_expand_vars` 补节下标、池偏移与长度边界检查，`compiler/project.toml`
     的 `[env]` 值去掉嵌套 `${YH_ROOT}`（改字面量）。

**验证**：
- `just test` 全绿（含 372/374 run、libs 151、compiler-tests 8/8、C4/C6）
- `just selfhost-native` 全绿：固定点一致（51 产物）、cc4 自解析 180 文件、
  project cases **125/125**、LA0 O0/O2
- `just test-libs` O0/O2 全绿；`tmp/list-consumer` 跨模块消费者退出码 0
- 四端 CI：linux-x64/linux-arm64 成功；darwin-arm64 修复后待本轮结果；
  Windows 仍失败（`compiler-tests` 0xC0000005），Release 未发布
- 本地种子已滚：`bin/yh-darwin-arm64` = `yh 0.0.14-rc.1`，
  sha256 `54a5cf1bff3f86d7617719373a07c31c6456e48e84de7d9aaa0662689e7b097b`

## 2026-11-10：0.0.14-rc.2 发布成功 + 0.0.14 正式版

**rc.2 结果**：
- 四端 CI 全绿（run 42744872693）：darwin-arm64 / linux-x64 / linux-arm64 /
  windows-x64 门禁 + `release-asset` 全部成功；Release `0.0.14-rc.2`
  （Pre-release）带 8 个资产（4 端 tar.gz + sha256）。
- 关键修复：`PProj.envs/env_n/env_cap` 未初始化（Windows `[env]` 崩溃根因）；
  无 CT 模块 `.s.ct` 缺失容忍；缓存命中跳过 session `.s.i` 发布；
  `canon` 反斜杠统一；Windows `tar -f` 相对输出名。
- Windows `u8-dup-module-path-import` 仍在 `WINDOWS_SKIP` 暂跳。

**0.0.14 正式版**：
- 版本号 `compiler/project.toml` + `YH_VERSION_TEXT` = `0.0.14`；
  发布说明 [release-0.0.14](01-finished/release-0.0.14.md)。
- 四端 release（run 42748030310）+ publish 成功；Release `0.0.14`
  （Latest）带 8 个资产。
- **发布资产验收**：`rm -rf bin && just fetch-seed` 取到 0.0.14
  （sha256 `020fb7259c2bf3f65896d11015fb8ca86d03449f2d5b598e19fcb2cd705a678e`）
  → `just build` → `yh 0.0.14` → `just test` 全绿 →
  `just selfhost-native`（project cases 125/125）全绿。

## 2026-11-10：list 标准库 L0–L2（动态列表）

**结果**：
- 新增 `libs/list/list.yh`（283 行）：无泛型动态列表 `List`（data/count/
  capacity/element_size，字段顺序即 ABI）与 `Status`（ok/invalid_argument/
  overflow/out_of_memory/bounds），10 个 `pub` 函数 `make`/`release`/`clear`/
  `reserve`/`element_at`/`push`/`push_all`/`pop`/`insert`/`remove_at`；私有
  `list_max_count`/`list_next_capacity`/`list_ensure`/`list_element`。
- 扩容 = `memory.alloc` + 复制 + `memory.release`，起步 16 槽、容量翻倍，上限
  `LIST_MAX_BYTES / element_size`；`insert`/`remove_at` 复用 `libc.memmove`
  （重叠安全）；失败时 count/capacity/内容不变。
- 新增 `libs/list/list.test.yh` 11 个语言内用例（空列表/无效步长、跨 16 槽
  扩容保留旧值、element_at 越界、release 幂等、reserve 上界 overflow 原子性、
  `{u8,i64}` 结构体步长 16、insert 头中尾、remove_at 头中尾、pop、clear、
  push_all）与 `README.md`（含 6 条硬规则）；登记 `libs/project.toml`；
  `yh-标准库设计.md` 增补 list 小节；编码规范动词表补 `pop`/`insert`/`remove`。
- 设计文档状态改为「L0–L2 已实施」，完成记录见
  [yh-list标准库-L0至L2](01-finished/yh-list标准库-L0至L2-2026-11-10.md)，
  `docs/todo.md` 删除本条。

**验证**：
- `cd libs && YH_CACHE=off ../yh test --filter list` → 11 passed / 0 failed（O0）
- `YH_CACHE=off ../../yh -O2 test --filter list`（`tmp/libs-o2`）→ 11 passed / 0 failed
- `just test-libs` 全绿（toml 681/681、string/num/fmt 专项与安装验收）
- `YH_CACHE=off just build` → 构建完成；跨模块消费者 `tmp/list-consumer`
  （`import list` + `list.status_ok` + qsort）退出码 0
- 观察（未修）：不设 `YH_CACHE=off` 的 `just build` 在本机失败于
  `link/context.yh:22 LLVM lowering set_argv0`，疑似全局缓存命中不可用模块
  产物，与本切片无关。

## 2026-11-10：LLVM 闭包缓存移到项目外 + 构建前只检测一次

**结果**：
- 默认缓存根从 `<repo>/tmp/llvm-migration` 改为**项目外**：macOS
  `~/Library/Caches/yh/llvm-migration`，其它平台 `$XDG_CACHE_HOME|~/.cache/yh/llvm-migration`；
  `YH_LLVM_CACHE` 仍可覆盖（`tools/llvm_cache.py` 是唯一解析处）。本机 3.7 GB 闭包已
  `mv` 到新位置，仓库内不再存放缓存数据。
- 删掉 justfile 的 `_prepare`；`just build/dev` 不再每次建软链/校验。`tools/seed-build.py`
  改为“只在缺失时”把仓库 `tmp/llvm-migration` 桥到项目外缓存——当前种子 0.0.13 尚不
  支持清单里的 `${...}` 展开，所以清单仍写仓库相对路径；等种子滚过该特性后再切
  `${YH_LLVM_ROOT}`。
- 新增“已封装”标记 `<cache>/.sealed-<host>.json`（`tools/llvm_recipe.py`）：
  `just llvm-host` 与 seed-build 的 shim 先读标记（键 = SDK 配方 + 宿主配方 + 缓存根，
  值 = `host.json` 摘要），命中即复用、不再校验 68 个归档、也不改写任何记录；只有标记
  缺失/配方变化才做一次全量校验并重新封装。
- `tools/llvm-darwin-sdk.py` 的 WORK 跟随 `cache_root()`（原来写死仓库路径）；
  `tools/link-closure.py` 的宿主记录从缓存根读取，并能把缓存根内的绝对归档路径归一化。
- `compiler/link/link_inputs.yh` 注释里的 2 个真实 NUL 字节改为文本（rg/git 不再当二进制）。

**验证**：
- `env YH_CACHE=off just build` → 冷编 14.8s；缓存记录 mtime 不变；仓库内只有软链
- `just llvm-host`：首次全量 4.7s，之后 0.32s；`just dev` 1.9s，缓存文件未被修改
- `just test` → 全绿

## 2026-11-10：新增代码流程图生成工具（`just codeflow`）

**结果**：`tools/yh-codeflow.py` 扫描当前 `compiler/`，生成自包含 HTML
（`tmp/codeflow/index.html`，约 800 KB，内联 CSS/JS/SVG，断网可开）：

- 三个视图：① 模块依赖（17 模块 / 76 条 import 边，`hash`/`libs`/`os` 画成外部节点）；
  ② 模块调用强度（函数级调用聚合到模块，67 条跨模块对）；③ 模块内文件调用
  （跨模块目标画成 `@模块` 虚线节点）。
- 调用解析：先剥注释与字符串字面量；限定调用 `mod.fn(...)` 按本文件的 import 别名
  解析，非限定调用按「同模块唯一 → 文件 import 的模块唯一 → 全仓唯一」；解析不出
  的如实计 `unresolved`（当前 3 条），`@[extern]` 声明不进索引。
- 布局：Tarjan SCC → 缩点图 Kahn 拓扑分层 → 重心排序（前向/后向各两轮），坐标在
  Python 侧算好、画布按最宽层自适应；JS 只做平移/缩放/悬浮，连续两次生成逐字节一致。
- 交互：滚轮缩放、拖拽平移、双击复位、悬浮详情、侧栏模块下钻；深链
  `#imports` / `#calls` / `#m=build`。
- 接线：`just codeflow`；自测 `tests/tools/yh-codeflow/check.py` 进 `just test`
  （4 条：端点自洽、无 NUL 且单 script、规模与汇总一致、结果可重复）。

**验证**：`just test` 全绿（含新自测）；`just codeflow` 输出 17 模块 / 179 文件 /
1859 函数 / 76 import 边 / 6413 条调用边；Chrome headless 截图三个视图均正常渲染
（模块视图分层清晰，`build` 文件视图可见 `support`/`token`/`proj` 等跨模块流向）。

## 2026-11-10：文档刷新（模块归组 + 统计删除 + DR 归档）

**结果**：
- 模块结构：`compiler/README.md`、`yh-架构设计.md`、`yh-模块职责-当前实现.md`、
  `yh-编译流程-当前实现.md`、`yh-编译流程图.md`、`README.md` 统一为
  **17 模块 / 179 文件 / 60,970 行 / 76 条依赖边**（2026-11-10 实测）；
  `cmdline` → `main`（`cmd/yh/`）、`cache` → `build/cache/`、`cmd/driver.yh` →
  `cmd/yh/yh.yh`、`proj/proj_0X_*.yh` → `proj/{model,table,path,art}.yh`。
- 统计删除：设计/缓存文档里 `--stats`、`stats_print`、`support.stats()` 的用法说明改为
  “已删除”，并在缓存设计里写明“命中只能靠产物字节/时间差间接判断”。
- DR1–DR5：DR1/DR2/DR4/DR5 已处理、DR3 仍未复现；原始记录归档到
  [`01-finished/yh-DR1-DR5-文档刷新发现-2026-11-08.md`](01-finished/yh-DR1-DR5-文档刷新发现-2026-11-08.md)，
  `docs/todo.md` 只留 DR3 一条开放项；`finish.md` 里「遗留 DR1/DR2…待作者确认(DR4)」
  的过时句已改。
- `yh-project.toml-清单设计.md` 的 `proj_00_model.yh` → `proj/model.yh`。

**验证**：README / compiler README / 03-design / todo / finish 里 `cmdline`、
`cmd/driver.yh`、`compiler/cache/`、`proj_0X_*.yh`、`stats_print`、`support.stats()`
均无“当前态”残留（历史章节与日期标注保留）；todo/finish 的 markdown 链接目标全部存在。

## 2026-11-10：删除统计机制（support.stats / stats_print / yh-stats / 相关门禁）

**结果**：
- `support/base.yh`：删除 `CompileStats`（42 字段）与 `stats()` 窄口；只保留三个与统计
  无关的功能位，收进新的 `BuildCtl`（`support.ctl()`）：`front_cache`（worker 源/token
  快照）、`firc_write_off`（冷构建不写函数 IR 缓存）、`ir_cache_salt`。
- 删除 `build/stats_print.yh` 与全部调用点；清掉各模块的计数语句、`enabled` 守卫、
  lowering/链接/前端计时字段（`BuildCtx.*_ns`、`link` 的 `lk_*_ns`/`reset_timings`、
  `sched_peak`/`sched_iface_early`、`SessionCtx.stats_ast_*`）。
- CLI：`--stats` 参数与上一轮引入的 `YH_STATS` 环境变量一并删除（先删参数、再删机制，
  两次提交）。
- 工具与门禁：
  - 删除只服务统计的 `tools/{perf-baseline,perf-invalidation,perf-scaling}.py`、
    `.github/workflows/perf.yml`、`tests/selfhost/gates/lex-stats.py`、
    `tests/selfhost/cache/{llvm-function-cache,llvm-path-cache,link-cache}.py` 及 justfile 接线。
  - `tests/modules/build-check.py` 删除 10 个以统计为唯一判据的用例（firc、checked-lower、
    inline、ir、ir-call、scheduler、scheduler-diamond、mode-cache、comptime-expanded-*），
    其余用例里以统计计数的断言改为产物/运行值判定（如 C 源变化用对象字节 + 运行码）。
  - `tests/yh-run/check.py`、`tests/selfhost/{bootstrap,darwin,gates}` 同步去掉统计断言。
- 顺带修复 `c7ca83d` 引入的 CLI 回归：裸调用 `yh` 由 `return 0` 改回 `return 2`
  （`selfhost-native` 的 CLI 冒烟门依赖它，0.0.13 及之前都是 2）。

**代价（明确记录）**：SSA 降低覆盖、check/IR/链接缓存命中、阶段耗时、worker 并发等
观测全部消失；`build-check` 从 135 例降到 125 例，其中 10 个纯统计用例被删，
另有若干断言降级为“构建成功 + 运行值正确”。

**验证**：
- `env YH_CACHE=off just build` 冷编通过；`yh`（裸调用）rc=2；`YH_STATS=1 yh build`
  不再输出任何 `yh-stats`。
- `just test` → **全绿**（ANTLR 83/83 + 反例 49/49、yh-run 372/374、test-check 38/38、
  build-cache、libs 140、compiler-tests 8/8、C4/C6 全局缓存门、code-stats 6/6）。
- `just selfhost-native` → cc4 自解析与固定点、语法/运行语料、check-command、缓存门
  全过；尾段受 1s 超时用例在满载下的抖动影响，且 `build-check` 仍有 18 条既有失败
  （与本次无关，u3-c-*/ct5b 等，见下条记录）。

## 2026-11-10：删除 CLI 参数 `--stats`，统计改由 `YH_STATS=1` 开启

**结果**：
- `compiler/cmd/yh/cmd_base.yh`：删除 `--stats` 选项与其全局扫描分支；`CliRequest.stats`
  改由 `proj.env_fetch("YH_STATS")` 赋值（非空且非 `"0"` 即为开）。
- `compiler/cmd/yh/cmd_emit_module.yh`：worker 不再解析 argv 里的 `--stats`，改为读同一
  环境变量；`build/build_scheduler.yh` 不再往 worker argv 塞该开关（fork 与
  `--emit-module` 子进程都按环境继承）。
- 工具与门禁同步：`tests/modules/build-check.py` 的 `sh()` 把用例里的 `"--stats"`
  翻译成 `YH_STATS=1`（20+ 处调用不用改）；`tests/yh-run/check.py`、
  `tests/selfhost/*`（bootstrap/cache/darwin/gates）、`tools/{perf-baseline,
  perf-invalidation,perf-scaling,seed-build,cli-golden}.py` 改为环境变量；
  `cli-golden` 的 `build-stats` 用例删除（旧/新二进制对参数的支持不同，无法对齐）。
- 文档：`README.md`、`compiler/README.md`、`yh-编译流程-当前实现.md`、`yh-缓存设计.md`、
  `yh-Windows-LLVM后端设计.md` 里的用法改为 `YH_STATS=1`。

**验证**：
- `yh build --stats` → `yh: 未知选项`；`YH_STATS=1 yh build` → 输出 2 行 `yh-stats`；
  不设变量 → 0 行。
- CI 式暂存二进制下 `tests/modules/build-check.py` → 103/135，**失败集合与改动前逐条一致**
  （`u5-hot-cache-hits` 等 stats 相关用例仍 OK）。
- `tests/yh-run/check.py` → 372/374（2 跳过），rc=0。
- `tests/selfhost/gates/lex-stats.py`（暂存二进制）→ 通过；`check-command.py` → 通过。
- `env YH_CACHE=off just build` → 冷编通过。

**既有问题（未随本次修）**：`tools/perf-baseline.py:344` 仍读已删除的
`compiler/gen/state.yh`（F4 删 gen 后失效），`perf.yml` 这条工作流当前跑不起来；
`lex-stats.py` 等门禁用仓库根 `./yh` 跑会因默认标准库（`<exe_dir>/libs`）污染计数，
必须用 `just stage-yh` 的暂存二进制。

## 2026-11-09：修复 `yh test` 在非 compiler 项目上的回归（testkit 无条件 import proj）

**问题**：`c7ca83d` 让生成的测试入口无条件输出 `import proj; proj.ctx().envp = envp`，
而 `proj` 只是编译器自己的模块：任何用户项目（含 `libs/`）执行 `yh test` 都报
`模块不存在: proj`。`tests/modules/test-check.py` 的 `default-check`、
`execute-fail-early-exit-and-crash` 与 `just test` 里的 `cd libs && yh test` 因此全红。

**结果**：`compiler/testkit/test_cmd.yh:tc_gen_runner` 先在被测项目里查 `proj`
模块，命中才生成 `import proj`、`envp **char` 参数与赋值；普通项目回到原来的
两参数 `main`。编译器自测仍保留环境接线（`proj.env_fetch` 依赖它）。

**验证**：
- `cd libs && YH_CACHE=off yh test --timeout 60` → 140 passed / 0 failed
- `tests/modules/test-check.py` → 38 PASS / 0 FAIL（原 2 条 FAIL 转绿）
- `tools/compiler-tests.py` → 8/8
- `env YH_CACHE=off just build` → 冷编通过

## 2026-11-09：同名模块不再合并 + 路径导入（import a.cache）

**问题**：模块按「(项目, 模块名)」查找/创建，`src/a/cache` 与 `src/b/cache`（都声明
`module cache`）被静默合并成一个模块，与 `PMod` 注释「一个模块（一个目录一份源文件集）」
矛盾，也让「用 as 区分两个同名模块」无从表达。

**结果**：
- 模块身份改为 `(项目, 名字, 目录)`（`proj/model.yh` 的 `PMod.dir_off/len`、
  `proj/table.yh:module_at_dir`）；`build/project_index.yh` 用它查找/创建模块。
- 裸名导入在本项目内命中多个同名模块 → 报「模块名歧义」，提示改用路径导入；
  两段导入仍是「依赖键优先，未命中再按目录」；三段及以上只按目录。
- 路径导入 `import a.cache` 解析到 `<source>/a/cache` 里声明为 `cache` 的模块
  （`pj_import_dir` 用 `proj.canon` 拼源码根，`module_at_dir` 按字节比目录）；
  末段与声明名不符报「路径导入与目录不匹配」。
- 重名模块的产物标签/符号后缀追加目录指纹（`proj/art.yh:mod_tag`、
  `build/project_resolve.yh:pj_mod_suffix`，FNV-1a 低 32 位 → 8 位十六进制）；
  模块 ActionID 混入模块目录。无重名的项目命名与之前逐字节一致。
- 解析器放宽 import 段数为任意（`parse/parse_module.yh`），`ImportEnt` 记完整
  点分原文；`docs/yh.g4` 补 `moduleHead/moduleDecl/importDecl/modulePath` 并纳入
  `sourceFile`，新增语料 `tests/yh/01-toplevel/05_module_head.yh`。

**测试**：新增 `tests/modules/projects/{dupmodseg,dupbarenames,dupmisname}` 与
build-check 的 `u8-dup-module-*` 三条用例（路径导入 + as 运行 rc=30 / 裸名歧义 /
目录与声明名不符）。`tests/modules/build-check.py` 拷真实编译器模块改用
`core_src()` 名字映射（cache 已下沉 build/cache）。

**验证**：`env YH_CACHE=off just build` 冷编通过；`tests/yh/check.py` 83/83 + 49/49
（含 ANTLR 层）；`tests/modules/test-check.py` 通过（2 条 FAIL 为既有问题）；
`tests/build-cache/check.py` 全通过；`tools/compiler-tests.py` 8/8。

**既有问题（未随本次修）**：`tests/modules/build-check.py` 的成败与「二进制位置 →
默认标准库发现」强相关（`mb_load_default_stdlib` 找 `<exe_dir>/libs`）。用仓库根的
`./yh` 跑时，标准库会盖住 fixture 依赖项目的同名模块（`basic` 的 `json` 被
`libs/json` 盖住；把 `libs/json` 移走后该用例 255 通过）；用 CI 式暂存二进制则
没有标准库层。CI 式条件下当前 32 条失败，抽查 `u1-attribute-iface-v2`、
`r2a-ssa-direct-call-abi` 在改动前的 `f9bf6e8` 上同样失败，与模块改造无关。
（该段 2026-11-09 修正：此前“HEAD 35 条”的说法把调用方式差异当成了版本差异。）

## 2026-11-09：删除架构守护 tools/arch-check.py

**结果**：按用户决定移除架构守护，`tools/arch-check.py` 与自测
`tests/tools/arch-check/check.py` 删除；`just test` 里对应的两层与 `just arch-check` 配方
一并去掉。依赖方向、状态/资源预算、版本常量一致性从此**不再有机器校验**：
`docs/03-design/yh-架构设计.md` §3.1 / §6.3 / §10.1 改为“评审基准”，
`yh-模块职责-当前实现.md`、`yh-编译流程-当前实现.md`、`compiler/README.md` 里
“由 arch-check 强制”的措辞同步改写；`compiler/build/stats_print.yh` 注释里对
文件预算的引用一并清理。

**验证**：`env YH_CACHE=off just build` 冷编通过；`just --dry-run test` 配方可展开；
`rg -n 'arch-check' justfile .github tools tests` 为空。

## 2026-11-09：arch-check 版本常量改按内容定位 + 删除休眠的性能脚本

**结果**：

- `tools/arch-check.py` 的 VCONST 检查不再写死 `compiler/cmdline/cmdline.yh`——`cmdline`
  模块已并入 `cmd/yh/`（module main），写死路径让守护在挪文件后直接抛
  `FileNotFoundError`（`just test` 因此自测 0/8）。现在在源码树里按内容搜索
  `YH_VERSION_TEXT` 声明，要求恰好一处，并报出相对路径；`project.toml` 也从被测
  源码根读，使 `--root` 自测与被测树一致。
- 依赖矩阵随之修正：删掉失效的 `cmdline` 条目，`main` 允许依赖 `libs`
  （`libs/cli` 的参数声明与解析现在在 `cmd/yh/cmd_base.yh`）。
- 删除 `tools/compiler-performance.py`：没有 justfile/CI 引用，编译耗时口径已由
  `tools/perf-baseline.py`（`perf.yml` 在用）承担；且它的冻结语料校验自 `2976a3d`
  起恒失败（给 `tests/perf/corpus-r0/compiler/project.toml` 补了 `os`/`arch` 两行，
  却没重生成 `SHA256SUMS`）。`corpus-r0` 保留为历史快照并在 README 标注不可校验。

**验证**：`python3 tools/arch-check.py` → 架构检查通过（17 模块 / 180 文件 / 76 条依赖边）；
`python3 tests/tools/arch-check/check.py` → 9/9（新增「删掉版本常量必须红灯」，TOTAL 8→9）。

## 2026-11-09：CI 去重——门禁与打包收进 justfile

**结果**：`ci.yml`（232 行）与 `release.yml`（545 行）各写一套四端构建，`perf.yml` 再抄一份
Darwin 前置：同一份「种子 → 闭包 → 冷编 → 门禁 → 自举」写了 9 遍，而且已经漂移——release 的
Windows runner 是 `windows-latest`（VS 18 下闭包 CMake 生成器找不到实例），release 的
Linux/Darwin 不跑 `test-libs`，release 的 artifact 路径用 `github.ref_name`（dispatch 演练
上传必然找不到文件）。现在收成两条配方：

- `just ci-gate`：`test`（三层回归 + libs + 工具门）→ `platform_gate`（按宿主分派：
  Linux/x64 → `test-llvm`、Linux/AArch64 → Windows 目标编译侧、Darwin → `test-llvm-darwin`、
  Windows → 语料交叉编译 + 本机执行）→ 自举 `SKIP_CORPUS=1`；`KEEP=1` 保留 cc4。
- `just release-asset <tag> <资产平台名>`：找 cc4 → `--syntax-check` 冒烟 → tar（单成员 `yh`）
  → 校验和（`sha256sum` / `shasum` / Git Bash 的 `*` 归一）。

两个 workflow 的 8 个平台 job 都只调这两条配方：232+545 → 186+424 行，门禁清单与四份
约 29 行的打包脚本各只剩一份；Windows runner pin 与门禁集合不再分叉。

**验证**（本机 darwin-arm64）：`KEEP=1 just ci-gate` 全绿——test 三层、`test-llvm-darwin`、
自举固定点一致、cc4 自解析 180 文件、project cases 129/129；
`just release-asset 0.0.14-test darwin-arm64` 产出 `dist/yh-0.0.14-test-darwin-arm64.tar.gz`
（单成员 `yh`，`shasum -a 256 -c` 通过，解包后 `./yh --version` = `yh 0.0.13`）。
两个 workflow 用 Ruby YAML 解析器校验结构（jobs 齐全）。

**遗留**：四端真 runner 上的行为未验（本机只能验 darwin-arm64），已登记
[todo.md](todo.md) D2：下一次 push 到 `llvm` 的 ci 四端全绿 + `release.yml` 的
`workflow_dispatch` `dry_run=true` 演练。

## 2026-11-09 tests/selfhost 清理与分域

**结果**：`tests/selfhost` 从 91 个平铺文件整理为 54 个（8 个分组目录 + `fixtures/`）：
`bootstrap/`（自举固定点与驱动）、`cache/`（内容寻址/函数/路径/链接缓存）、
`gates/`（check 命令、词法统计、跨文件系统、架构、运行时内存）、`host/`（LLVM 宿主闭包与 lld）、
`darwin/`、`windows/`、`linux-arm64/` 平台专项（脚本与 `.yh`/`.c` 探针同目录）、
`probes/`（共享固定点探针）。删除 37 个已无入口的 LL 时代门（`llvm-abi`、`llvm-baseline`、
`llvm-checked`、`llvm-front-*`、`llvm-ir`、`llvm-module*`、`llvm-runtime`、`llvm-semantics`、
`llvm-embedded*`、`llvm-isolation` 及只被它们引用的探针）；入口以 justfile/CI 与 `tools/` 引用为准。
迁移脚本 `ROOT` 统一由 `parents[2]` 改为 `parents[3]`；justfile、`tools/`、AGENTS、`compiler/README.md`、
`docs/todo.md` 的路径同步。

**验证**：`just dev` 构建通过；`just test` rc=0；`test-llvm-darwin` 的 Darwin 门逐条实跑通过
（sdk/host/bridge/object/abi/cache/default/bundled-sdk/runtime/link/selfhost-flags 与 selfhost `--self-test`）；
`cache/llvm-global-cache.py`、`gates/check-command.py`、`gates/llvm-architecture.py`、
`cache/llvm-function-cache.py`、`cache/llvm-path-cache.py` 通过；全仓 `tests/selfhost/**` 引用存在性
与 Python 编译检查 0 缺失。未跑 `just selfhost-native`（两代自举主门，交 CI）。

**遗留**：`gates/lex-stats.py` 在当前 `./yh`（0.0.12）上失败，HEAD 原脚本同样失败
（POSIX 下 totals=(109,9,107,4,4,4,2) ≠ fork 复用期望），与本次迁移无关，需单独查 worker 复用行为；
`docs/01-finished/` 等历史文档仍引用旧路径，未改动。

## 2026-11-09 CI 日常门、滚种子与自举规划

**结果**：新增
[02-plan/yh-CI日常门与滚种子自举规划-2026-11-09.md](02-plan/yh-CI日常门与滚种子自举规划-2026-11-09.md)，
只做规划与取舍，未改代码/workflow。要点：日常按「`just dev` → `just quick` →
`just build`+`just test` → `just selfhost-native` → 等 CI」分层；CI 不新增 nightly
全量门，门禁统一到 `YH_ANTLR=0 just test`；可分发种子只由 tag Release 产生，本地
`just seed` 只影响本机；自举链已成立，缺 `just bootstrap` 取种与合入门槛两个决定；
建议每完成一个切片发 rc（当前 `0.0.12` 落后 83 个提交）。

**实测依据**：CI run `42507415505`（HEAD `6614864`）四端全绿、总 17m42s；
`gh api .../branches/llvm/protection` 返回 404（未保护）；`just --dry-run bootstrap`
确认顺序是「llvm-host → _ensure_built」，新机无种子会先建闭包再失败。

**验证**：只改文档（规划文档、`docs/todo.md`、本条目），未跑构建/测试——工作区当时
有另一会话的 S3a 后续切片未提交改动，避免并发构建冲突。

**遗留**：P0/P1/P2 见 `docs/todo.md` 同名段；合入门槛与 rc 节奏待用户决策。

## 2026-11-08 二次文档刷新：设计文档改指 S1–S4，实测口径对齐 HEAD

**结果**：按 HEAD `532d2c2` 与已提交的重新分析（`dc4f3bd`/`532d2c2`）刷新设计文档，
未改业务代码。

- `docs/03-design/yh-架构设计.md`：基线改为 18 模块 / 178 文件 / 60,717 行 /
  78 边；「阅读约定」新增前端计划重估段：F0–F7 于 2026-11-08 重估为 S1–S4，
  其余 F0–F7 引用为历史计划快照。§0.3、§0.5、§4.1、§6.10、§6.11、§7 的
  「执行基线 / 迁移方式 / 决策表」改指 S1–S4。
- `docs/03-design/yh-模块职责-当前实现.md`：头部与 §2/§6 的规模按 HEAD 重测
  （60,717 行；`support` 3,151、`ast` 1,351、`check` 6,040、`build` 7,992）。
- `docs/03-design/yh-编译流程-当前实现.md`：用途段改指 S1–S4（附重新分析链接）；
  §12 标题改为「原 F0–F7 / GEN0–GEN4 的历史对照」并加说明。
- `docs/todo.md`：S1 条目补「现状（未提交、`just build` 报 6 处函数未使用）」；
  原 DR1–DR5 状态保持不动。
- `docs/finish.md`：本条目。

**验证**：在独立 worktree `tmp/head-measure`（HEAD `532d2c2`）实测：
`python3 tools/arch-check.py` 通过（18 模块 / 178 文件 / 78 边 / 203 模块级 `let`）；
`python3 tools/yh-code-stats.py` 178 文件 / 60,717 行。
**本轮未在 HEAD 复跑** `just build`/`just test`/`just selfhost-native`：主工作区
有未提交的 S1 施工（23:36 时 `just build` 报 `check/iface_emit.yh` 6 处
「函数未使用」，`just test` 因 `_ensure_built` 失败未启动）；23:52 重跑又与另一
并发构建冲突（`yh-link.s.ct.session-<pid>` 打不开），无稳定结论。
此前同一台机器在 `5fd2e45` 附近记录：冷编通过、`just test` 370/372 全部通过、
`selfhost-native` project cases 129/129、CI 四端全绿（run `42486762530`）；
本条只引用该记录，不当作本次复跑结果。

**影响**：设计文档不再把 F0–F7 当成现行计划；数字与 HEAD 一致。

**遗留**：S1 施工中（见 `docs/todo.md`）；DR3（全局缓存非确定失败）仍未复现。

## 2026-11-08 memory 标准库设计第三版：M0–M6 收敛为 T1–T3

**结果**：重写 `docs/03-design/yh-memory标准库设计.md` 为第三版，未改业务代码。
第二版（2026-10-23）把范围切成 M0–M6 六阶段，自设计至 2026-11-08 **零切片
落地**，判定为范围过大并收敛：

- 必做三片：**T1 `reallocate`**（`data=0` 等价 `alloc`、`new_size=0` 释放、
  按 `min(old,new)` 复制后释放旧块、失败保旧块）、**T2 `FixedBuffer`**
  （调用方缓冲、零系统调用、LIFO resize/free/reset/owns）、**T3 `Arena`**
  （块几何增长 1.5 倍、`reset(free_all/retain)`、`capacity`）。
- 降为按需：`FixedPool`（P4）与 `Allocator` vtable（P5）；两者当前都无消费者
  （`toml`/`cli` 各有私有池，`string`/`toml`/`json` 都不接受分配器参数）。
- 撤掉伪约束：第二版用 `10_`/`20_` 文件名「保证编译顺序」；同模块按两遍解析
  （pass1 签名 / pass2 正文），顺序无关，`libs/string` 的 8 文件无编号即为反证。
  文件布局改为 `memory.yh`/`base.yh`/`fixed_buffer.yh`/`arena.yh`/`memory.test.yh`。
- 新增 §12「如何使用」：三档场景（现在可用的单对象分配、T1 后的重分配、
  T2/T3 后的临时缓冲与批量对象）+ 选择判据表 + 五条配对硬规则。

**设计期实测**（写入文档 §11 验证记录，非实施验收）：
`malloc(0)` 返回非空且 16 字节对齐、超长请求返回 0、`free(0)` 无操作；
同地址二次 `free` 直接 SIGSEGV（退出码 139）；20 万次 64 字节往返 0.87 s
（同规模基线 0.31 s）；`pub struct`/`pub enum`/枚举形参/结构体按值返回/
函数指针字段/栈数组取址在同一 fixture 中编译并运行通过。

**验证**：`python3 tools/arch-check.py` 通过（18 模块 / 78 边 / 未判空 malloc 0）。
文档里每个示例在 `/tmp` fixture 中 `yh build` + 运行验证过语法，并借此修掉三处
错误写法：`while` 不是 yh 语法（循环只有 `for`）、`&expr.to_type(*T)` 不可编译
（右值取址）、`import` 未使用是编译错误。本次只改文档，`just build`/`just test`
未重跑（无代码变更）；T1 落地时才需要 `just test-libs`。

**遗留**：T1–T3 待实施；第二版的
`docs/02-plan/yh-memory标准库实施方案-2026-10-23.md` 仍按 M0–M6 编号，与第三版
不一致，待 T1 落地时同步改写或归档（已记入 `docs/todo.md`）。

## 2026-11-08 文档刷新：架构/模块职责对齐实测，测试红灯入账

**结果**：按 2026-11-08 的代码与实测刷新文档，未改业务代码。

- `docs/03-design/yh-架构设计.md`：基线改为 18 模块 / 178 文件 / 60,737 行 /
  78 条依赖边（`arch-check` 实测）；新增「阅读约定」：`gen` 已于 2026-11-07
  删除，§0.2、§4.1、§5.2、§6.3.1–§6.3.2 中描述 `gen` 的段落为历史快照；
  §0、§1.2、§1.4、§2.1、§2.2、§3.1、§3.2、§4.1、§4.5、§5.2、§6.2、§6.3
  按现行实现改正；§6.3 允许矩阵改为与 `tools/arch-check.py` 的 `ALLOWED`
  逐条一致（`comptime` 不再依赖 `proj`）；§6.3.1 标为历史快照。
- `docs/03-design/yh-模块职责-当前实现.md`：头部改为 178 文件 / 60,737 行 /
  78 条依赖边（2026-11-08）；`comptime` 行的依赖改为 `support, token`；
  §3 边数、§2 与 §6 的逐模块规模同步重测（60,737 含临时诊断 16 行，
  清理后 60,721）。
- `docs/todo.md`：新增「2026-11-08 文档刷新发现」DR1–DR5。
- `docs/finish.md`：本条目与下方四条 11-07/11-08 记录。

**验证**：`python3 tools/arch-check.py` 通过（18 模块 / 178 文件 / 78 边 /
203 模块级可变 `let` / `import gen` 0 / `gen pub fn` 0）；
`python3 tools/yh-code-stats.py` 178 文件 / 60,737 行（含临时诊断 16 行）；
`just build` 通过
（含一次 `YH_CACHE=off`）。**后记（同日）**：DR2 清理与 AST 切片修复落地后，
同一口径实测为 60,717 行（见本条上方的新条目）。`just test` 在最后一门
`tests/selfhost/llvm-global-cache.py` 红（DR1），其前各层通过：语法正例
82/82、反例 49/49，运行语料通过 370/372（跳过 2），modules 与 build-cache、
opt-level 4/4，libs 140，compiler-tests 8/8，fmt 10/10。

**影响**：文档数字与实测对齐；测试红灯和临时诊断代码进入 todo，不再被
「F4 完成」的表述掩盖。

**遗留**：DR1–DR5（见 `docs/todo.md`）。

## 2026-11-07 ~ 11-08 gen 职责拆分收尾：模块删除（19→18）

**结果**（提交 `52b4e66`、`01cec48`、`218d26c`、`979a0c0`）：删除
`compiler/gen/`，值内核（`vk_*` + 消息表）下沉 `support/value_kernel.yh`，
`check/value_kernel.yh` 与 `comptime/ct_diag.yh` 各自适配诊断；切断
`comptime → proj` 边（文件表窄口改由 `parse` 传入）；新增
`docs/03-design/yh-模块职责-当前实现.md` 并刷新架构文档；新增
`tests/modules/projects/gen-split` fixture 覆盖拆分后六组公开面。

**验证**（2026-11-08 复跑）：`python3 tools/arch-check.py` 通过，18 模块 /
178 文件 / 78 边 / `import gen` 0；`just build` 通过。`just test` 后续红灯
见 DR1，且无证据表明与本次拆分直接相关；红灯清除前不宣称整体完成。

**影响**：模块数 19→18，所有 `import gen` 归零；`tools/arch-check.py` 的
`ALLOWED` 删除 `gen` 项。

**遗留（2026-11-10 复核）**：DR1/DR2 已修、DR4 已按提交时间定案（本标题即
2026-11-07）；DR3 仍未复现。详见
[`01-finished/yh-DR1-DR5-文档刷新发现-2026-11-08.md`](01-finished/yh-DR1-DR5-文档刷新发现-2026-11-08.md)。

## 2026-11-08 comptime 镜像两修：写回指针视图 + 标签表直接基址

**结果**（提交 `bf404ab`、`804dc54`）：`comptime/ct_facts.yh` 的镜像行写回
改为指针视图（修复 CI 上编译期数组长度/结构体布局失效）；`check/ct_bind.yh`
的字符串标签/枚举成员表改为直接持有基址（修复编译期字符串实参崩溃：读侧曾把
标签号当二级指针）。`tests/modules/projects/gen-split` 增加对应用例。

**验证**：两笔提交由 CI 失败触发；本地未确认当时的 CI 结论。2026-11-08 本机
复跑 `just build` 通过，`just test` 红在 DR1（函数缓存预热路径）。本条只记
「代码已提交、本机门禁未全绿」，不外推为全量通过。

**影响**：改动编译器自身的 CT 表绑定与镜像写回，属于编译器内部行为；
下游绿灯待 DR1 清除后补记。

**遗留**：DR1（待确认是否与本次镜像改基址相关）。

## 2026-11-08 本机固定 LLVM 闭包重建与门禁实测

**结果**：本机 `tmp/llvm-migration/llvm-host-darwin-aarch64` 缺
`libyh-llvm-bridge.a`，`just build` 报「库文件不存在或无法解析（组 bridge）」。
根因是 Command Line Tools 默认 SDK 27 的 `libSystem.tbd` 含 `arm64e.x1`，固定
LLVM 21.1.8 的 lld 无法解析。用 `SDKROOT=<Xcode>/MacOSX26.5.sdk` 重建 SDK
（3,368 步）后，`just llvm-host` 返回 `reused: true`，`just build` 通过。

**验证**：`just llvm-host`（bridge SHA-256 `52b60731…`，probe 输出 arm64
Mach-O）；`just build` 3 次成功（其中一次 `YH_CACHE=off`）；`just test` 见
DR1。`just code-stats`、`arch-check` 通过。

**影响**：本机恢复可构建/可测试状态；闭包仍在 `tmp/`（不入库）。

**遗留**：`just llvm-host` 不自动在 26.x/27 SDK 间择一，换机仍需手工设
`SDKROOT`（DR5）。

## 2026-11-08 项目级 pi：ste-zh 汇报规范 + docs-sync 模板补句

**结果**：把用户级 `ste` skill 复制进项目 `.pi/skills/ste-zh/`（7 个文件，
48K）；`SKILL.md` 的 `name` 由 `ste` 改为 `ste-zh`、触发词 `/ste` 改为
`/ste-zh`，避免与 `~/.agents/skills/ste` 同名冲突（pi 遇同名只保留先发现者
并告警）。`.pi/prompts/yh-docs-sync.md` 的「事实清单」步骤补「按照 ste-zh
skills 的要求进行」。

**验证**：frontmatter 合法（`name` 小写/连字符、与目录同名、`description` 在
1024 字符内），正文引用的 `references/terminology.md` 存在；未起会话验证加载，
需 `/reload` 或新会话在 project trust 后生效。

**影响**：仅本地 agent 配置。`b6e4578` 已把 `.pi/skills/` 加入 `.gitignore`，
文件不入库；需要团队共享时应改回入库或做成 pi 包。

## 2026-11-06 测试并行试验回退

**结果**：曾把 `test`/`test-libs` 拆成 `[parallel]` + 私有子 recipe，并用
`TEST_JOBS` 控制并发。实测冷缓存 `just test` 121→47 s、`just test-libs`
187→84 s，但热缓存、忙碌机器（load≈9）下提升有限，且引入 `libs` 复制与
install 并发约束、额外 recipe 和调试成本。按用户决定回退为**串行 recipe**：

- `test`、`quick`、`test-libs` 恢复顺序执行，不再使用 `[parallel]`/`TEST_JOBS`；
- 保留 `test-libs` 合并、`tests/fmt/install.py` 清单修复，以及 `just install`
  排除 `libs/tmp`；
- 不保留 `JUST_NO_DEPS`、并行 install 子组和 `_test-*`/`_test-libs-*` 私有层。

**验证**：`just test-libs` 串行通过；`just test` 已恢复原串行 recipe，本轮因当前
宿主固定 LLVM 闭包缺失（`tmp/llvm-migration` 无 `libyh-llvm-bridge.a`，SDK 27
TAPI 不兼容）在 compiler-tests 阶段失败，属环境问题，恢复闭包后需复跑。
`just --list` 仍为 28 个公开目标。

## 2026-11-06 标准库测试合并为 just test-libs

**结果**：删除 `libs-test`、`libs-test-o2`、`test-toml`、
`test-toml-conformance`、`test-toml-injection`、`test-toml-install`、
`test-string`、`test-string-o2`、`test-string-install`、`test-num`，合并为唯一
入口 `just test-libs`。新目标覆盖：

- 全部 `libs/` test 块 O0（缺 `*.test.yh` 提示）；
- cli/os/libc 外部 runner（`libs/cli/test/{run,diff}.py`、`libs/os/test/run.py`、
  `libs/libc/test/run.py`）；
- 全部 test 块 O2（`tmp/libs-o2` 独立项目根）；
- TOML 一致性/注入/安装、string O0/O2 行为与参考差分/安装、num 参考差分、
  fmt 插值负例/安装后导入；
- 所有编译器调用统一 `YH_CACHE=off`，避免测试污染全局缓存。

CI 的 linux-x64、linux-arm64、darwin-arm64 三个 job 改调 `just test-libs`；
TOML 一致性语料准备移入目标内（`--prepare` 幂等）。Windows job 保持
`just test`（其平台专属外部 runner 暂未纳入）。

**顺手修复**：`tests/fmt/install.py` 的必需文件仍写 `tests.test.yh`，实际文件
已改名 `fmt.test.yh`，导致该安装门第一次真正接入时失败；修正清单与
`fmt.test.yh` 文件头。

**文档**：`AGENTS.md`、`README.md`、`libs/{string,toml,cli,fmt,io,json}/README.md`、
`tests/{string,toml}/README.md`、`docs/03-design/yh-{编码规范,test语言内测试设计,
test测试布局与运行约定,io标准库设计,cli标准库设计}.md`、`docs/todo.md`、
`.github/workflows/ci.yml` 同步。

**验证**：`just test-libs` 通过（含 O0/O2 test 块、runner、TOML/string/num/fmt
专项与安装门）；`just test` 通过；`just --list` 现为 28 个公开目标。

## 2026-11-06 just 入口清理：删除 15 个重复/孤儿目标

**结果**：从 `justfile` 删除 A/B 两批 recipe，`just --list` 由 53 个公开目标降到
37 个：

- 纯别名/重复：`all`、`test-all`、`help`、`test-arch-check`、`test-code-stats`、
  `test-lib-tests`；
- 已被主门覆盖或长期不跑：`test-compiler-tests`、`test-fmt-interp`、
  `test-fmt-install`、`size-report`、`test-string-complexity`、`llvm-isolation`、
  `selfhost-llvm`、`selfhost-llvm-darwin`、`llvm-host-status`；
- `stage-yh` 加 `[private]`，从帮助隐藏但保留为内部依赖；删除只服务
  `selfhost-llvm` 的 `LLVM_SEED` 变量。

底层脚本不删：`tools/compiler-tests.py`、`tools/size-report.py`、
`tests/fmt/install.py`、`tests/string/complexity.py`、
`tests/selfhost/llvm-isolation.py`、`tests/selfhost/llvm-selfhost.py`、
`tests/selfhost/llvm-darwin-selfhost.py` 仍可按需直接运行；
`llvm-host-status` 的 Windows 诊断可用 `tools/llvm-windows-host.py status`。

**文档**：`AGENTS.md`、`README.md`、`compiler/README.md`、`libs/{fmt,string,io}/README.md`、
`tests/string/README.md`、`docs/03-design/yh-test{语言内测试设计,测试布局与运行约定}.md`、
`docs/03-design/yh-io标准库设计.md`、`docs/todo.md` 的引用同步改为 `just libs-test` /
`just test` / 直接脚本；`02-plan` 历史方案保留旧名称。

**验证**：`just --list` 37 个目标；`just --dry-run test` 通过；`just test` 通过
（140 + compiler/cache/link + 语料 + arch-check）。

## 2026-11-06 build 产物保留开关：--emit-llvm / --emit-asm

**结果**：`--emit-llvm` 与 `--emit-asm` 归入 `yh build` 子命令，二者使用方式一致，
只在 build 阶段额外保留产物：

- 默认构建：LLVM 文本只在内存中传给内嵌桥，不写 `.ll`，也不写 `.s`；
- `yh build --emit-llvm`：额外写 `<build>/llvm/<project>-<module>.ll`；
- `yh build --emit-asm`：额外写 `<build>/asm/<project>-<module>.s`（对象发布后
  用同一份 LLVM 文本再调用一次桥，只在显式请求时多付一次 codegen）；
- 两者可同时使用；对象、可执行文件与链接行为不变；
- 模块缓存命中时若本次请求的 `.ll`/`.s` 缺失，退回 worker 补写；存在则照常命中。

单文件 `yh --emit-asm/--emit-llvm f.yh` 与 `yh test --emit-llvm` 保持原有
stdout/审阅行为，不做改动。CLI 声明上，build 子命令新增两个开关；测试与单文件
parser 各自显式声明原有 `--emit-llvm`，不再依赖全局 common。

**实现**：`gen.TargetCfg.emit_asm`；`cmdline` 的 build 子命令选项；`driver`
落配置；`build_scheduler` 的 `--emit-module` 协议传递；`module_worker` 计算
`asm/<tag>.s`；`llvm_pipeline` 在对象发布后追加汇编发布；`module_emit` 的缓存
命中条件检查请求产物存在。

**验证**：`just build`；`just test`（140 通过）；`llvm-architecture --case
entries` O0/O2（含默认不落 `.ll/.s`、`--emit-llvm`、`--emit-asm`、删产物后缓存
命中补写、两开关并用、对象/程序仍正常）；`llvm-function-cache` O0/O2；
`yh test --no-run --emit-llvm`；临时项目手工矩阵。`native-selfhost.py` 通过
cc2/cc3/cc4 固定点、自解析与语料；`just selfhost-native` 后续模块门在当前
工作区仍受并行 C4 改动与宿主 SDK 27 TAPI/C interop 环境影响（u5 缓存用例、
`-lm`、`arm64e.x1`），需在稳定树复跑。

**顺手修复**：当前工作区 C4 改动留下的 `mb_mix_compiler_identity` 未定义与
`module_emit` 缺 `hash` import 使自举无法构建；补成 `cache.Key` 混入 32 字节
编译器内容身份，并以 `mb_compiler_identity_ensure` 复用一次哈希。该修复不属于
emit 开关，但不做则当前树无法编译。

## 2026-11-06 撤销文件级对象缓存规划

**结果**：按用户决定，删除 C5 文件级对象（每个 `.yh` 一个 `.o`）与 LA4 的后续
实施规划；对象粒度停在模块级，PC7 函数级 `.o` 暂缓。增量继续由函数 check
切片 + 函数 IR 缓存承担，后端整模块发射与链接复用是接受的成本。新增
[ADR-0020](adr/0020-yh对象粒度停在模块级.md) 记录取舍与量化依据
（O0 单函数 3.6 s 中发射约 0.5 s、链接约 1.3 s、前端/lowering 约 1.8 s；
O2 单函数 7.55 s 中桥约 3.59 s；函数级 `.o` 会使桥调用从 13 次量级升到约
1460 次）。

**文档**：`docs/todo.md` 删除 C5/J2/J3 并加入「设计决定不做」；缓存方案删除
C5 与文件对象键/验收/风险；Go 对比把 §3.6 改为模块级结论；缓存设计、架构
设计、缓存键审计、LLVM 架构方案、极致速度路线与 2026-11-03 盘点同步标注
撤销/暂缓。`cache.ACTION_FILE`/`OUTPUT_SUPPORT` 代码常量保留为 schema 预留，
本次无代码变更。

**验证**：文档一致性检索（`rg` 检查 C5/LA4/文件对象只出现在撤销记录）；
未改代码，不触发构建。

## 2026-11-06 缓存 C6：trim/锁/可观测

**结果**：新增 `compiler/build/cache_admin.yh` 与 `yh cache info|clean|trim|verify`：
info 输出根、actions/outputs 数、总大小与上限；clean 清空 actions/outputs/tmp；
trim 按 mtime 从旧到新删除未被任何 action 引用的 output；verify 全量检查
action 编码、OutputID 内容、缺失/损坏与孤儿 output。新增
`cache/lock.{darwin,linux,windows}.yh`：POSIX `flock` 实现同项目构建锁与
全局 cache 写锁（Windows 占位后置）；`YH_CACHE_DEBUG=1` 输出模块 ActionID、
local/global hit/miss 与函数 action 的 miss 原因。trim/clean 持全局写锁，
读取路径仍按 OutputID 校验；缓存运维失败不把构建判失败。

**测试**：`tests/selfhost/llvm-global-cache.py` 扩展 debug、verify 损坏/孤儿、
trim（`YH_CACHE_MAX_SIZE=1K`）、clean、同项目并发构建；`just test` 通过；
`just selfhost-native` 125/125 通过（固定点 51 产物、cc4 自解析 158 文件）。
宿主种子已滚。

## 2026-11-06 缓存 C4：全局 content store 与 action cache

**结果**：新增 `compiler/cache/cache_store.yh`（v1/actions、outputs、tmp、lock；
SHA-256 OutputID、原子 put/get、读取重算摘要、action entry 二进制编解码、
`YH_CACHE_MAX_SIZE` 解析）与 `compiler/build/cache_global.yh`（YH_CACHE 默认
路径/off、模块产物发布/物化、全局 miss 回退）。模块键改为 SHA-256 ActionID，
本地 manifest 改为 128 字节（ActionID + 三个 OutputID），`.build/index/<tag>`
只存 64 hex ActionID；跨目录无 `.build` 时按 ActionID 命中并物化 obj/.s.i/.s.ct。
函数 check/IR action 通过 `firc_global_publish`/`store_lookup` 接入全局 store，
本地记录缺失时可回退读取并物化。损坏 OutputID 校验失败按 miss，重新发布时
自愈。

**测试**：新增 `tests/selfhost/llvm-global-cache.py`（布局、去重、跨目录命中、
函数 action、损坏回退、`YH_CACHE=off`），接入 `just test` 与
`just selfhost-native`；测试门禁统一 `YH_CACHE=off` 隔离历史缓存断言，仅 C4
专项使用显式缓存目录；更新 Darwin/LLVM 缓存脚本读取 128 字节二进制 manifest。
`just test` 通过；`just selfhost-native` 125/125 通过（固定点 51 产物、cc4
自解析 153 文件）。宿主种子已滚。

## 2026-11-06 缓存 C3：路径与环境规范化

**结果**：函数 check/IR 语义键改用项目相对路径；新增 `proj.file_rel_path` /
`proj.file_locs_path`；check 切片 v5 保存相对路径并按键查找当前文件。新增
`cache.CacheInputs` 白名单（target/ABI/opt/trimpath），SDK/selfhost/工具链在进入
键前先解析成内容身份。新增 `--trimpath`：IR 来源表、LLVM `source_filename` 与
CT 来源映射使用项目相对路径；模块键/函数环境键纳入 trimpath 模式。schema 升到 3，
模块 tag 升到 `yh-iface-cache-5-ct`，函数环境标签 `yh-firc-env-3`。

**验证**：新增 `tests/selfhost/llvm-path-cache.py`（搬目录后 check/IR 全命中、
trimpath 两目录 `.ll` 逐字节一致、未开 trimpath 保留绝对路径、YH_WORKERS 非白名单
不失效、Darwin `YH_LINK_STRIP` 白名单变化重新链接）；`just test` 通过；
`just selfhost-native` 全绿（固定点 51 产物、cc4 自解析 150 文件、项目用例
125/125）。宿主种子已滚。

## 2026-11-06 缓存 C2：工具/闭包内容身份

**结果**：`BuildCtx` 增加 32 字节 `compiler_identity`，每个构建进程只对编译器
二进制做一次 SHA-256；模块键混入完整 32 字节，`compiler_fingerprint` 仍是由
摘要派生的 64 位值，供 worker 环境键使用。`link.mb_mix_file_identity` 从
`(size, mtime_ns)` 改为文件内容 SHA-256，外部链接器/驱动身份随内容变化；
lld/bridge/SDK 继续使用内容身份（lld 身份串为 SHA-256，SDK/默认库按内容摘要）。
新增 `compiler/link/link_inputs.test.yh`：同内容重复读取/重写身份不变，同长度
不同内容身份必变。

**验证**：`just build`；`just test`（compiler-tests 新增 cache/link 模块）；
`just selfhost-native` 全绿（固定点 51 产物、cc4 自解析 150 文件、项目用例
125/125）；编译器 touch/复制后目标项目仍命中 `[缓存]`。宿主种子已滚
（`bin/yh-darwin-arm64`）。

## 2026-11-06 缓存 C0/C1：键审计 + SHA-256

**结果**：新增 `libs/hash/sha256.yh` 纯 yh 流式 SHA-256（NIST 向量、55/56/63/64/65
字节边界、未填满末尾块、百万字节与单字节 update）；新增 `compiler/cache/` 模块
（`CACHE_SCHEMA_VERSION=2`、`ACTION_*`、32 字节/64 hex `ActionID`、`key_init_function`
公共前缀、token/整数/文本长度分帧）。函数 check/IR 键从 FNV 16 hex 迁移到
SHA-256 64 hex；check 保留类型/签名表事实，IR 使用逐声明布局，两者用不同 action
种类。旧函数缓存按长度/版本/tag 拒绝：`IR_FUNCTION_CACHE_VERSION=3`、
`CHECKED_SLICE_VERSION=4`、`yh-firc-env-2`、模块 tag `yh-iface-cache-4-ct`。

**验证**：`just build`；`just test`（含 libs 140 用例、arch-check 17 模块/59 边）；
`tests/selfhost/llvm-function-cache.py` O0/O2 全矩阵；新增 `tests/modules/projects/hashsha`
与 build-check 用例；`cd compiler && ../yh test cache`；65 MB 编译器 SHA-256
约 0.74 s（含进程启动）。宿主种子已滚（`bin/yh-darwin-arm64`）。新增
[缓存键审计](03-design/yh-缓存键审计.md)，同步缓存设计/架构/compiler README/
实施方案/todo。

## 2026-11-06 缓存设计文档

新增 [缓存设计](03-design/yh-缓存设计.md)：记录当前模块对象、函数 check 切片、
函数 IR、链接四层缓存，以及 InterfaceReady/session、键/manifest、失效矩阵、
冷构建/check/test 差异、原子性与并发边界、当前问题与目标 `build/cache/`。
在 [架构设计](03-design/yh-架构设计.md) §4.4 与 `compiler/README.md` 增加入口。
纯文档变更，无代码/门禁影响。

## 2026-11-06 03-design 文档去日期化

**结果**：`docs/03-design/` 的 16 份带 `-YYYY-MM-DD` 后缀的文件改为稳定文件名；
39 份文档在标题下增加 `修改时间：2026-11-06`，并删除旧的 `日期：` 元数据行与标题日期，只保留修改时间。全仓引用（README、compiler/README、
docs/02-plan、docs/01-finished、ADR、libs/tests 注释等）同步替换，链接检查通过。
纯文档变更，无代码/门禁影响。

## 2026-11-06 编译流程参考文档

新增 [编译流程-当前实现](03-design/yh-编译流程-当前实现.md)：从
`yh build` 开始记录 CLI → 项目装载 → 调度 → worker 前端/check/lower/LLVM/对象
→ 链接的当前实现，附缓存、产物、命令变体、当前边界与 F0–F7/S0–S6 调整对照。
同步在 [架构设计](03-design/yh-架构设计.md) §1.2 与 `compiler/README.md` 增加入口。
纯文档变更，无代码/门禁影响。

## 2026-11-06 arch-check 停止按代码行数阻断

**结果**：`tools/arch-check.py` 删除 `max_file_lines`、`max_function_lines`、
`max_module_lines`、`max_testkit_lines`、`max_build_lines`、`max_link_lines`、
`max_proj_lines`、`max_cmd_share_pct` 八个行数预算；报告不再聚合/打印行数。
代码规模统一由 `just code-stats` 单独统计。保留依赖矩阵/环、模块级可变 `let`、
`gen.G()`、未判空 `malloc`、未接线 `pub`、容量安全追加点与版本一致性。

- 自测三路：真实树通过；注入越界 import 报错；追加 4000 空行仍通过（证明不再按
  行数阻断），`tests/tools/arch-check/check.py` 输出 3/3。
- 同步：`docs/03-design/yh-架构设计.md` §5.3/§9.5/§10/附录 B、`justfile` 注释。
- 验证：`just test` 中 arch-check 自测 3/3 + 真实树通过。

## 2026-11-06 架构文档合并为单一真源

**结果**：新增 [架构设计](03-design/yh-架构设计.md)（910 行），合并 26 份架构分析/
目标设计/代码复核/差距分析文档并删除原文件；`docs/03-design` 从 63 份降到 38 份。
新文档覆盖：系统全景、16 模块目录职责、依赖矩阵、阶段/产物/缓存/状态契约、现状
问题、目标架构（support/sema、build/cache、proj、cmd、平台抽象、前端分叉）、关键
决策、Rust/Zig 差距与优先级、迁移路线、架构守护、开放问题，以及被合并文档索引。

- 同步：`AGENTS.md` 目录说明、`compiler/README.md` 模块表（16/148/57,540/55 边）、
  `docs/todo.md`/`docs/finish.md`/ADR/02-plan 的引用、`tools/arch-check.py` 注释、
  `compiler/{cmd,gen}` 中指向旧文档的注释。
- 修正：`compiler/README.md` 的 13 模块/120 文件/53,545 行旧读数；`cmd` 仍写
  `api.yh` 的旧表。
- 未合并：语言语义、标准库、平台 ABI、编码规范、测试语法等领域文档继续保留；
  它们是领域设计/契约，不是架构分析。
- 验证：`just` 冷编、`just test`、`just selfhost-native` 全绿（固定点 + 自解析 +
  语料 + 项目验收 124/124）。

## 2026-11-06 发布线退役：0.0.12-release 回灌 llvm、默认分支改为 llvm、删 rc/release 分支

**结果**：`llvm` 成为唯一主线与 GitHub 默认分支；`<ver>-rc`/`<ver>-release` 两条
分支流程结束（方案保留为历史记录）。0.0.12 是最后一个走分支流程的版本。

- 回灌：`git merge --no-ff origin/0.0.12-release`（`701f5ff`）入 `llvm`，只带入正式
  版号（`compiler/project.toml` + `YH_VERSION_TEXT` = `0.0.12`）与
  `docs/01-finished/release-0.0.12.md`；`docs/finish.md` 取 `llvm` 侧条目（已含完整
  发布记录与 `1927f95` 事故，为 release 线条目的超集），release 线的重复段已删。
- 默认分支：GitHub 上从 `0.0.12-release` 改为 `llvm`（先改默认再删分支，否则 API
  拒绝删除默认分支）。
- 删分支：远端 `0.0.12-release`、`0.0.8-rc`、`0.0.8-release` 已删除；tag（含
  `0.0.12-rc.1/2/3`、`0.0.12`）全部保留，发布历史不受影响。
- 流水线：`ci.yml` 的 `push`/`pull_request` 去掉 `*-rc`/`*-release` 触发；
  `release.yml` 的正式 tag 落点校验从「`<ver>-release` 的祖先」改为「`llvm` 的
  祖先」——分支没了，直接在主线上打 tag。

**已验证**（本机 macOS/ARM64）：`just` 冷编（`yh --version` = `yh 0.0.12`）、
`just test`（语法语料 + 运行语料 + libs/compiler-tests/fmt 负例/code-stats/arch-check）
与 `just selfhost-native`（两代固定点 + 自解析 + 模块/项目验收 124/124）均通过。

## 2026-11-06 四端 CI 首次在 libs 去前缀后全绿；perf 首跑卡在工具缺陷并修复

**CI**：推送 `cc915fa`（含 `51882b1` libs 去前缀、`e5f61e0` 文档、`716a025` 文档
与 CI 口径修正）后，分支门 run `42097604110` 四端全绿：windows-x64 14 min、
darwin-arm64 8 min、linux-arm64 7 min、linux-x64 6 min（均为闭包缓存命中路径）。
这是 libs 全库改名第一次过四端门。

**perf 复跑**：run `42097618792`（`workflow_dispatch`，同 commit）的失败点变了——
「取种子 → 恢复闭包 → 冷编」全 success（冷编 26 s，Darwin 闭包缓存与 ci.yml 互相
命中），红在第 9 步「编译体验基线」：四个场景 20/20 失败、墙钟约 210–285 ms、
无任何 stats，即构建进程立刻退出。

**根因**（从归档的 `raw.json` 反查）：`stage_corpus` 只把 `compiler/` 复制到
`work/<a|b>/compiler`，并把 `../tmp` 软链回仓库；但项目自 CLI-R（2026-10-27）
起把标准库写成显式跨项目依赖：

```toml
[dependencies]
libs = {path = "../libs"}
```

副本里没有 `../libs`，`yh build --stats` 每轮立刻以
`yh: 无法打开文件: ../libs/project.toml` 退出（exit 1，无 `time_*`/`ir_*`/`check_*`
统计行）。这个缺依赖从 CLI-R 起就存在，但一直没被跑到：上一次 perf 实跑
（`41932809252`）在更早的「冷编」就红了。

**修复**（`tools/perf-baseline.py` 的 `stage_corpus`）：副本里同时复制 `libs`
（忽略 `.build`/`tmp`，避免历史产物污染 cold 场景），A/B 两份各自独立。
`corpus_sha256` 仍只描述被测的 `compiler/` 语料（已在 docstring 注明边界）。

**验证**：本机用 `yh.exe` 在 stage 出来的副本里跑 `yh build --stats` → exit 0
并输出完整 stats 行（Windows 无软链权限，`../tmp` 那一层用目录 junction 代替）；
`python -m py_compile` 通过。四端 perf 的真实结果待再 dispatch 一轮确认。

## 2026-11-06 版本与发布流程收口：tag/版本号/落点三道校验 + dry-run 演练入口

`docs/todo.md`「版本与发布流程（P0 前置）」的 R2、R4 关闭，并把三条未登记问题
登记为 V1–V5。改动只涉及 CI 声明、脚本与文档，未动 `.yh` 源码。

| 文件 | 改动 |
| --- | --- |
| `.github/workflows/release.yml` | `prepare` 从「只读 ref 名」改为 `fetch-depth: 0` 检出 + 三道校验：① tag 形态；② tag 与 `compiler/project.toml` 的 `version`、`compiler/cmdline/cmdline.yh` 的 `YH_VERSION_TEXT` **完全一致**（`--version` 只读后者，漏改会产出自报版本错的不可撤销资产）；③ 正式 tag 必须是 `<ver>-release` 的祖先（`git merge-base --is-ancestor`，rc 候选线跳过）。新增 `workflow_dispatch`（`tag` 必填 + `dry_run` 默认 true）；五处 `TAG` 统一取 prepare 解析结果，四个平台 job 与 publish 的检出改为显式 tag，publish 在 `dry_run` 时跳过 |
| `.github/workflows/ci.yml` | `pull_request.branches` 补 `'*-rc'`/`'*-release'`（`push` 侧已由 `cc915fa` 补），发布线与候选线的合并 PR 不再无门 |
| `compiler/README.md` | 删掉写死的 `version = 0.0.11`，改为指向 `project.toml` 并说明两处版本号必须与 tag 一致 |
| `tools/compiler-performance.py` | `verify_function_change` 不再断言 `"yh 0.0.5"`，改为从 `compiler/project.toml` 读版本号再断言输出（该脚本无门引用，此前属一跑就崩的休眠坏账） |
| `AGENTS.md` | 修正「rc 与正式版是同一提交」的错误表述（实际正式版比最后一个 rc 多一个版号提交），并把「祖先校验尚未落地」更新为已落地 + 剩余项 |
| `docs/todo.md` | 删 R2/R4（已收口），新增 V1（发布线不回灌 `llvm`）、V2（版本号两处手写）、V3（release.yml 四端 job 首跑）、V4（残留分支与分支保护）、V5（种子 sha 与发布资产一致性） |

校验（本机，无网络/无 CI 环境下的等价验证）：
- 三个 workflow 通过 `yaml.safe_load`；prepare 的 `run:` 体 `bash -n` 通过；
- 把 prepare 逻辑抽成脚本、在 `0.0.12` 与 `0.0.12-rc.3` 两个 tag 的临时 worktree 上
  实跑：正式 tag 通过（含 `0.0.12-release` 祖先校验）、rc tag 跳过落点校验；
- 反例：worktree 在 `0.0.12-rc.3` 而 tag 传 `0.0.12` → 「版本号不一致」失败；
  把远端 `0.0.12-release` 指到一个不在该分支的提交 → 「不是 0.0.12-release 的
  祖先」失败；
- `tools/compiler-performance.py` 通过 `py_compile`。

## 2026-11-06 CI 口径对齐：`*-release` 触发与 perf 首跑记录

`docs/todo.md` 的「2026-11-03 CI 迁移」段已无待修的工程项，剩下三处文字与
触发面与现状不一致，本次一并收口（只改 CI 声明与文档，不动编译器源码）：

- `.github/workflows/ci.yml` 的 `push.branches` 补上 `'*-release'`：AGENTS 写的是
  `<ver>-rc`/`<ver>-release` 分支同样触发，实际只有 `'*-rc'`，导致 0.0.12 合入
  `0.0.12-release`（`701f5ff`）后没有任何分支门跑过。
- 同文件 windows-x64 的步骤名从「取种子（0.0.11 Release 的 Windows 种子）」改为
  「取种子（最新带 Windows 资产的 Release）」：0.0.12 起该资产由 `release.yml`
  正常产出，不再有追加的过渡资产。
- `docs/todo.md` 的 perf 条目补上失败事实：至今唯一一次运行是 run `41932809252`
  （`schedule`，2026-11-04T23:19Z）的 `darwin-baseline` 第 8 步「冷编」，根因是
  当时 `perf.yml` 未接过渡桥、0.0.11 种子编不动 W2 语法的 HEAD；0.0.12 种子后该
  根因失效，但尚未复跑，仍按未验收处理。

验证：`.github/workflows/ci.yml` 与 `perf.yml`、`release.yml` 均通过 PyYAML 解析
（`yaml.safe_load`）；`git push --dry-run` 确认远端可接收。本轮未改 `.yh` 源码，
因此未重跑 `just test`/`just selfhost-native`；四端的真实门由推送后的 ci.yml 分支
门给出，perf 的验收仍需 `workflow_dispatch`。

## 2026-11-06 todo 平台段重写：B1 拆 4 条、B2 拆 2 条并补两条未登记缺口

`docs/todo.md` 原 `B. 后续平台（原 F3/F4）` 只有 `B1 Windows/x86_64`（含 2 个子项）
与 `B2 macOS/x86_64、Windows/ARM64` 一句「四格分别完成运行/自举/性能验收」，
无法排期。按现状重写为 6 条：

| 条目 | 性质 |
| --- | --- |
| B1a 零 CRT vs UCRT 决策 | P0；22 例 `WINDOWS_SKIP` + `libs/math` 不可用 |
| B1b Winsock 接线 | **新增未登记缺口**；Windows 上 `net`/`http` 全 `-ENOSYS` |
| B1c COFF 整库加载 + Win32 导出面扩展 | P2；无 `/wholearchive`；kernel32 仅 38 条导出、扩面无流程 |
| B1d Windows 工程债 | windows job 漏跑 `test-windows-target`（排除理由已过期）、无性能基线、runner pin |
| B2a macOS/x86_64 原生接入 | P1；目标/SDK 已就绪，缺 `[link-darwin-x64]`、x64 闭包、脚本参数化、种子/CI |
| B2b Windows/ARM64 可行性立项 | P2；目标/ABI/SDK 机器码/目标包/runner 五项都要先证明 |

同时给出四格现状（已交付四格 + 未接入两格）与「交叉任务已撤下，故 B2a 只在原生
runner 验收」的前提，避免再被理解成可交叉验证。

## 2026-11-06 撤下交叉编译任务（A2/A3/LC3/C5），等待重新立项

用户决定：交叉编译相关条目全部从 `docs/todo.md` 删除，后续重新计划。删除项：

| 原条目 | 位置 |
| --- | --- |
| A2 F2-9 Linux/x64 交叉产 Mac 候选 | P0 段 A（整段删除） |
| A3 F1-6 x64 自举脚本参数化 + 跨宿主链接模板 | 同上 |
| LC3 F2-9 交叉（目标包 `libc++.tbd`） | 编译器性能测试段 |
| C5 Darwin 交叉边界 | 分发与工具链体验段 |

P0 段保留一段说明（撤下原因 + 重新计划用的现状取证：Linux 交叉产 Mach-O 对纯
`.yh` 可用但需显式 `SDKROOT`；带 `[c] sources`、交叉产编译器候选、macOS→Linux
均不可用）。设计材料不删：`03-design/yh-Darwin交叉编译遗留边界.md` 加状态行
（并注明 `compiler/darwin-sdk/` 已迁 `vendor/darwin-sdk/`），
`03-design/yh-架构设计.md` §8.3 的「明确不做」不再列
交叉编译任务（已撤下）。todo 的未完成项由 103 条降到 99 条。

## 2026-11-06 todo 清账：删除全部已完成项，只留未完成与待决策

`docs/todo.md` 从 840 行降到 631 行、勾选项清零（原 30 个 `[x]` + 11 个已完成/
失效的未勾条目），按「本文件只保留未完成项，历史看 finish.md / 01-finished」
统一口径：

| 类别 | 处理 |
| --- | --- |
| Windows W 系列已完成片（W0-1/1b/2a/4、W1-1/2/2b/3/3b/3c/3d/4/5/6/7/8、W2-1/2b/2c/3/3a/4a/5/6/7/9、CI 接线） | 删除（证据在 `01-finished/` 与各设计文档） |
| 两个 P0 已修项（`--emit-asm`、Windows 闭包可重定位首建） | 删除 |
| 已被现实取代的条目：W0-3（决策冻结）、W2-0（等 0.0.11 种子）、W2-4b（Windows 进程模型）、W2-5b（CI windows job 实跑）、W2-2（Windows 闭包分发）、R1（分支模型）、R3（取种含 rc）、R5（0.0.8 内容）、D2（Gitea 收尾）、D3（x86_64 模拟崩溃） | 删除 |
| C1（固定 SDK 预编译分发） | 删除条目，移入「设计决定不做」（2026-11-03 闭包不入 Release 的决策） |
| 「实跑验收」 | 收敛为唯一剩余项：`perf.yml` 首次实跑 |
| 去数字前缀段落 | 改写为「已落地」，只留「顺序错误诊断不可读」这一条 |
| 过期叙述 | 删掉「GitHub 四端 job 暂停」「Gitea/CircleCI 在跑」「0.0.11 桥 staging」等已不成立的描述；「三端种子」改「四端种子」 |

保留但按证据改写：`foreign-fs-build`（不是 CI 红，而是本机 Windows `%TEMP%`
安全策略问题，与 `--emit-asm` 同根因）。

不动：所有 `[ ]` 未完成项、`待决策` 与 `设计决定不做` 两节。

## 2026-11-06 根 README 改为 README.md 并按当前口径刷新

`git mv README README.md`（git 保留改名历史），全文按 ste-zh（简化技术中文）重写：
短句、一词一义、状态词固定、情态词只用「必须/不得/可以」。

口径变化（相对旧 README）：

- 版本 `0.0.12-rc.3`；`compiler/` 16 模块表（旧文写 8 个模块）；
- 代码生成唯一后端 LLVM 21、内嵌 lld；四目标 triple 表，`x86_64-apple-darwin`
  标注「未验证，CI 不覆盖」；
- 项目模式默认产物改为 `<项目根>/.build/<name>`；入口模块名必须是 `main`；
- 源文件 `module <名>;` 头与 `import` 约束；标准库 15 模块与三级加载顺序；
- 新增术语、文档索引、种子/构建缓存、CI 与发布口径；删除 C 版 stage0、`-c`/`-run`/
  `-sysroot`、仅 arm64 后端、prelude 八函数等过时内容。
- 独立只读核对后修订 6 处：补 `name` 必填与标识符规则、`--list` 增加声明位置、
  `--no-run` 改为「不生成入口」、模块表 `cmd` 改为 `main`（目录 `cmd/`）、
  四端全绿改用 run `42062242047`、裸变参改为「设计决定不做」。

验证（Windows 本机 `yh.exe`）：

- 已验证：三处 `yh` 代码块 `--syntax-check` 全过；quick-start hello 与语言速览示例
  编译运行，输出 `hello, yh` 与 `1 2 1`/`10`/`6`/`small`。
- 已验证：按 README 的 `[project]` 清单与标准库示例建项目，`yh build` 得
  `.build/demo`；运行写入 `demo.txt`，字节为 `001 002 003`。
- 已验证：README 相对链接全部可达；自检脚本 `tmp/readme-check/check_readme.py`。

未做：`just test` / `just selfhost-native` 未在本机重跑。本次只改文档；且本机沙箱
拒绝 `just` 的 backtick 管道，`just` 默认目标报 os error 5（justfile:104）。
`compiler/README.md` 等子文档仍按旧口径，未一并刷新。

## 2026-11-06 libs 全量去数字前缀：语义名 + 字节序即依赖序

`libs/` 下剩余带数字前缀的 6 个模块（libc、net、os、string、sys、toml）全部改成
语义名；工作区里已改但顺序错误的 fmt 一并修正（`model`→`base`、`spec`→`directive`）。
模块内仍按**文件名字节序**编译、类型与数组长度常量必须先于使用，因此新名字同时
满足「字节序 = 拓扑序」。共享类型/常量的前置文件统一叫 `base.yh`（与 json 一致）：

| 模块 | 旧名 → 新名 |
| --- | --- |
| libc | `10_memory`/`20_string`/`30_convert`/`40_sort` → `memory`/`string`/`convert`/`sort`（彼此无类型依赖，任意顺序可编） |
| net | `00_model`→`base`、`05_error`→`errors`、`10_address`→`text`、`20_tcp.*`→`tcp.*`（`base` 前置；`tcp`/`text` 只依赖 `base`+`errors`，函数前引用不受限） |
| os | `00_model`→`base`、`10_errors`→`errors`、`20_directory.*`→`directory.*`、`30_process.*`→`process.*`、`40_sleep`→`sleep` |
| string | `00_model`→`base`、`10_view`→`view`、`20_owned`→`owned`、`30_transform`→`transform`、`40_utf8`→`utf8` |
| sys | `00_types`→`base`、`05_errno.*`→`errno.*`、`10_constants.*`→`constants.*`、`20_raw.linux`→`raw.linux`、`30_file.*`→`file.*`、`40_memory.*`→`memory.*`、`50_time.*`→`time.*`、`60_process.*`→`process.*`、`70_socket.*`→`socket.*` |
| toml | `00_types`→`base`、`10_storage`→`document`、`20_utf8`→`encoding`、`30_numbers`→`numbers`、`40_datetime`→`datetime`、`45_parser_state`→`lexer`、`46_strings`→`strings`、`50_parse`→`parse`、`60_query`→`query`、`70_files.*`→`file.*`、`90_api`→`surface` |
| fmt | `model`→`base`、`spec`→`directive`（其余 `float`/`interp`/`output`/`render`/`value` 原名合规） |

fmt 的原工作区改名**编译不过**：`float`、`render` 用 `model` 的类型而
`float < model`，`float` 又用 `spec` 的 `format_spec` 而 `spec > float`。
改成 `base`（前置）+ `directive`（格式说明）后，`base` < `directive` <
`float` < `interp` < `output` < `render` < `value`，顺序全部满足。
toml 的 `lexer`（游标/诊断/空白注释）与 `parse` 的关系同理：`parse` 消费
`parser` 类型，必须排在它之后，因此不能直接叫 `state.yh`。

只改名、未搬移任何声明；`git mv` 保留历史。同步更新 `libs/*/README.md`、
各模块 `doc.yh` 与源文件注释里的文件名、`docs/03-design`（编码规范新增
「共享声明放字节序最前的语义名文件（惯例 `base.yh`）」，删掉「存量不改名」
建议；JSON/TOML/os与sys/http 设计里的顺序说明改为按语义名字节序）、
`docs/adr/0017`、`docs/02-plan` 相关文件表、`docs/todo.md`，以及
`tests/fmt/install.py`、`tests/string/{install.py,run.py,README.md}`、
`tests/toml/{install.py,injection.py}` 的必需文件清单。

验收（本机 Windows `yh.exe`；门禁脚本加 `PYTHONUTF8=1`，否则 GBK 默认编码
读不了含中文的源码副本）：
- `cd libs && ../yh.exe test` **134 passed; 0 skipped; 0 failed**；
- `yh test --no-run --target aarch64-unknown-linux-gnu` / `aarch64-apple-darwin`
  各 **134 个用例构建通过**（覆盖 linux/darwin 平台变体）；
- `yh check --target` 四种 triple（linux x64/arm64、darwin x64/arm64）全部
  「检查通过: yh_libs」；`cd compiler && ../yh.exe check`「检查通过: yh」
  （编译器经 `[dependencies] libs` 复用 cli/io/os/sys/string）；
- `tests/toml/injection.py` 通过（124 个池失败点 + 预算强制失败，已指向
  `toml/document.yh`/`toml/base.yh`）；`tests/string/run.py` model/interop/resources
  全 PASS（注入点改写 `string/base.yh`）；`libs/cli/test/run.py` 5/5；
  `libs/cli/test/diff.py` 88/94（6 个已知差异，与改名无关）；
  `libs/os/test/run.py` linux-check 11/11。
未在本机跑的两项：`libs/libc/test/run.py`（需要宿主 `cc` 链接 ctest.c）与
`tests/*/install.py`（打包步骤产出 `yh.exe`，脚本按 `yh` 查找），留给 CI。

## 2026-11-06 清理 `deliverables/`：两份 2026-10-24 产出迁入 docs/03-design

`deliverables/` 是 2026-10-24 一次 AI 会话（gstack 工作流）的交付目录，全仓库无构建、
门禁或文档引用它（旧架构文档提过一句"与本次复核无关"，该文已并入 `docs/03-design/yh-架构设计.md`）。
按 AGENTS.md 的目录约定，把两份 md 迁入 `docs/03-design/` 后删除该目录：

| 原路径 | 新路径 |
| --- | --- |
| `deliverables/gstack/yh-explorer-design-system-spec-2026-10-24.md` | `docs/03-design/yh-Explorer设计系统规范.md` |
| `deliverables/gstack/raw/product-review-arch-2026-10-24.md` | 已合并入 `docs/03-design/yh-架构设计.md` |

设计规范里引用的配套 HTML（`deliverables/gstack/yh-explorer-design-system-2026-10-24.html`）
从未入库、仓库内不存在，迁入时把该行改写为说明，不留断链。纯文档搬迁，无代码与门禁影响。

## 2026-11-06 libs/json 去数字前缀：文件名即编译顺序

`libs/json/` 13 个源文件不再带数字前缀（`base.yh`、`document.yh` …
`surface.yh`），改用语义名并让**文件名字节序仍是拓扑序**（模块内声明必须先于
使用，跨文件提前引用会报「未知类型（类型必须先定义）」）：

| 旧名 | 新名 |
| --- | --- |
| `00_types.yh` | `base.yh`（所有文件的前置：公开类型/枚举/预算常量） |
| `10_storage.yh` | `document.yh` |
| `20_utf8.yh` | `encoding.yh` |
| `30_numbers.yh` | `digits.yh` |
| `40_lex.yh` / `50_parse.yh` / `60_query.yh` | `lex.yh` / `parse.yh` / `query.yh`（原名即合规） |
| `70_write.yh` | `render.yh`（builder 状态机） |
| `75_files.{linux,darwin,windows}.yh` | `stream.{linux,darwin,windows}.yh` |
| `80_encode.yh` | `serialize.yh`（值树递归写出 + `encode`/`encode_owned`） |
| `90_api.yh` | `surface.yh`（`parse`/`parse_text`/`root`/`release` + 诊断） |
| `tests.test.yh` | `json.test.yh`（工作区已有改名，本批保留） |

顺序论证：`base` < `digits` < `document` < `encoding` < `lex` < `parse` <
`query` < `render` < `serialize` < `stream.*` < `surface`，逐级满足类型/常量
依赖；`stream` 调 `surface.parse` 属函数前引用（今天 75_files→surface 同样如此）。
只改名、未搬移任何声明。同步更新 `docs/03-design/yh-JSON标准库设计.md`
（§2 目录树 + §9 实现落点）、`libs/json/README.md`、`docs/03-design/yh-标准库设计.md`、
`docs/todo.md` 与 `tests/modules/build-check.py` 的文件引用。
验收：`cd libs && ../yh.exe test json` **12 passed; 0 skipped; 0 failed**。
冒烟遗留：同工作区的 `libs/fmt` 去前缀（用户已改）仍报 `fmt/float.yh:218:35`
「未知类型」，与本批无关，属包内顺序问题（`float` < `model`）。

## 2026-11-06 删除过渡期自举桥：四端流水线切回 `just build`

**结果**：0.0.12 已发布四端种子（含 Windows 正常资产），种子认识 `windows`
comptime 标记、`*.windows.*.yh` 平台变体、`[link-windows-x64]` 清单节与
`.test.yh` 测试排序，过渡桥的存在前提消失：

- `.github/workflows/ci.yml`、`.github/workflows/release.yml` 四端 job 的
  「过渡期自举桥」步骤全部改回「冷编」`just build`；
- `justfile` 删除 `bootstrap-bridge` 配方与注释；
- 删除 `tools/ci-bootstrap.py`；
- AGENTS.md 的「过渡期（W2 种子）」条目替换为「种子门（不再需要过渡桥）」，
  「种子」条目去掉 0.0.11 Windows 过渡资产说明；docs/todo.md 删除
  「移除过渡期自举桥」与「Windows 种子过渡资产」两条。

本地验证：用 0.0.12 种子（`bin/yh-windows-x64`，sha256 `d6721853…` 同 rc.3 内容，
正式版资产已验证）在独立 worktree 跑 `just build` 冷编 → `yh --version`；
四端 `just build` 的真实门由 ci.yml 分支门确认。

## 2026-11-06 发布 0.0.12 正式版（rc.3 基线 + 发布二进制验收）

**结果**：GitHub Release
[0.0.12](https://github.com/lalavender/x/releases/tag/0.0.12)（正式版，非 prerelease）。
发布流水线 run 42081751704（tag `0.0.12`，commit `701f5ff`）**四端全绿**：
prepare / linux-x64 / linux-arm64 / darwin-arm64 / windows-x64 / publish 全部 success，
产出 8 个资产（四端 `tar.gz` + `sha256`，windows-x64 22.3 MB、darwin-arm64 23.3 MB、
linux 两架构各约 40.7 MB）。本次种子取 0.0.12-rc.3（首个带资产的候选），
所以四端都走「rc.3 种子 → 过渡期自举桥 → HEAD」链路。
分支：`0.0.12-rc`（候选，commit `f87a747`）`--no-ff` 合入 `0.0.12-release`（`701f5ff`），
tag 打在 release 分支上；`0.0.12-rc` 的 ci.yml 分支门同轮四端 success（run 42081736645）。

**发布二进制验收**（发版流程第 3 步，Windows/x64 宿主）：`just fetch-seed` 取 rc.3 种子
（sha256 `d6721853…`）→ `just build`（`yh --version` = `yh 0.0.12`）→ `just test`
（三层回归 + 554 条 PASS + `arch-check`）→ `just selfhost-native`（cc3→cc4 固定点
48 产物一致、自解析 148 文件、探针、CLI 冒烟、语法语料反例 49/49、运行语料
363/372 windows-x64 原生、modules 19/19、compiler-tests 4/4、project cases 130/130）。
本机两处垫片：`python3` 是 Microsoft Store 桩，用 `tmp/pyshim/python3.exe` 跑语料；
`foreign-fs-build.py` 受本机安全策略（不受信 exe 不能写 `%TEMP%`）限制，以 `TEMP`
指向仓库内目录等价通过，跨文件系统真值由 CI 承担。

**过程事故与修复**：`1927f95`（rc.3 结论文档提交）把当时暂存区里另一个任务的
`libs/json` 去前缀改名一并带进提交，导致 `json/api.yh:10` 早于 `types.yh` 引用
`Diagnostic`，llvm 分支门 run 42066720773 红灯。已用 `2281445` 把 `libs/json`
恢复到 `ab244e3`（tag 0.0.12-rc.3）内容，llvm 分支门 run 42075976931 恢复绿。
正式版基线取 tag `0.0.12-rc.3`（`ab244e3`），不含该误提交。

## 2026-11-05 发布打包步骤引用已删除路径：release.yml windows 端 cp 失败

**结果**：[release-0.0.12-rc.3](01-finished/release-0.0.12-rc.3.md)。
0.0.12-rc.2（run 41966728220）三端成功、windows-x64 在第 10 步打包失败：
`cp: cannot stat 'dist/selfhost/cc4': No such file or directory`。自举门本身全绿
（固定点一致 48 个产物、自解析 148 文件 OK、探针 OK、compiler-tests 4/4、
project cases 130/130）。根因是 windows job 的打包 shell 沿用了旧写法：
`cp "$cc4" yh` 之后执行 `rm -rf dist/selfhost`，随后又从 `$cc4` 复制到 stage，
源已不存在；linux/darwin 三端写的是 `cp yh "$stage/yh"`。日志中
`[ -f dist/selfhost/cc4 ]` 命中却 cp 失败，是 MSYS 的 `.exe` 后缀魔法（第一次 cp
实际产出 `yh.exe`）。已用本机 Git coreutils 复现旧写法报错、验证新写法打包成员名
为 `yh`；版本升 0.0.12-rc.3。rc.2 同时证明上一轮桥接修复有效（step 8/9 均 success）。
**rc.3 结果**：run 42062242047 四端全绿（windows-x64 步骤 8/9/10 全 success），
publish 成功，Release `0.0.12-rc.3` 已发布 8 个资产（四端 tar.gz + sha256）。
下一步是用发布出去的 rc.3 种子做 `rm -rf bin && just fetch-seed → just → just test →
just selfhost-native` 验收（见发版流程第 3 步）。

## 2026-11-05 发布流水线 Windows 端红灯：release.yml 漏接自举桥

**结果**：[release-0.0.12-rc.2](01-finished/release-0.0.12-rc.2.md)。
0.0.12-rc.1（run 41957530693）四端仅 windows-x64 失败，job 127015942985 的
「冷编」`just build` 报 `libs/cli/actions.test.yh:14:32: 错误: 未知类型（类型必须
先定义）`。根因是接线遗漏而非编译器缺陷：rc.1 的 `release.yml` 里 linux-x64 /
linux-arm64 / darwin-arm64 已改用 `just bootstrap-bridge`，只有 windows-x64 仍是
`just build`；0.0.11-windows 种子早于 2026-11-05 的 VTEST（`.test.yh` 改名、排序
前缀废止），按字典序把 `actions.test.yh` 排在定义 `pub struct Namespace` 的
`cli.yh` 之前。修法同 `ci.yml`：windows job 改走 `just bootstrap-bridge`
（staging 给 `*.test.yh` 临时加回 `zz_` 前缀），版本升 0.0.12-rc.2 并补发布说明。
同一条修法已在分支门 run 41954793463 四端验证。

## 2026-11-05 CI 二次红灯：Windows ACP 目录扫描（按 ACP 精确跳过）

**结果**：[yh-CI二次红灯-ACP目录扫描](01-finished/yh-CI二次红灯-ACP目录扫描-2026-11-05.md)。
`b6fafa7` 推上后 run 41952142547 的 windows-x64 **第 9 步已 success**（filter
修复在 CI 得到验证），三平台 job 全绿；第 10 步「自举主门」首次跑到（此前
5 次 run 全部 skipped），暴露 `build-check.py` 两个 R3 目录扫描用例在英文
runner（ACP=1252）必然失败：`FindFirstFileA` 把 `雪` 变 `?`、CRT `open()`
按 ACP 打不开。与 VENC-2 无关（本机 936 下修复前后编译器均 rc=0），是已登记
的「CRT 文件路径仍按 ACP」遗留。按用户决策用 `kernel32.GetACP()` 精确跳过：
仅当 ACP 无法编码该字符时 SKIP 两例，936/65001/932 仍照常实测；单测覆盖
四种 ACP + 手工对照。**这是隔离环境差异，不是修复**；根治（目录枚举改 W +
`_wopen`，或嵌入 UTF-8 manifest）升级为 todo.md 的 P1 项。

## 2026-11-05 VENC-2：Windows CRT 入口 argv 重建（CI filter 用例真正根因）

**结果**：[yh-VENC2-Windows-CRT入口argv修复-2026-11-05](01-finished/yh-VENC2-Windows-CRT入口argv修复-2026-11-05.md)。
CI run 41941536106 windows-x64 的 `test-check.py` list-filter/execute-filter
失败，根因不在零 CRT 入口桩（0b1ba2f/VENC 已修）：自举编译器链 libcmt，
入口是 CRT 的 mainCRTStartup，argv 经 `__getmainargs` → `GetCommandLineA`
按 ACP 取得——1252 上中文一步变 `?`，`/alternatename` 兜底只在无 CRT 时
生效（windows_link.yh 双形态入口，本机调试实锤 yh.exe 自身 argv 为 GBK
字节）。修复：新增 `gen/argv.{windows,linux,darwin}.yh`，Windows 在 main
最前用 `GetCommandLineW` + `WideCharToMultiByte(65001)` 原地重建 UTF-8
argc/argv（解析语义与零 CRT 桩一致；零 CRT 入口后为幂等直通；失败保持
原 argv），driver 先重建再消费。验收：test-check.py 38/38 全过（CI 上
36+2 失败），`just test` 除 arch-check 预算外全绿；预算上调
`max_module_lines` 461 → 469（driver +8 行：重建调用与注释）、
`max_globals` 172 → 174（argv.windows.yh 的 argv_line/argv_vec 两个静态
缓冲）。

## 2026-11-05 P0-B1：CI 自举桥适配 VTEST（Windows 纳入桥引导）

**结果**：[yh-CI自举桥VTEST适配-2026-11-05](01-finished/yh-CI自举桥VTEST适配-2026-11-05.md)。
`ci-bootstrap.py` 新增测试文件改名 staging（gen-1 临时 `zz_` 前缀，gen-2
原样 HEAD；纳入备份/恢复/崩溃恢复），Windows 宿主纳入桥引导（跳过变体/
标记/链接节改写）；`ci.yml` windows-x64 job 的 `just build` 切换为
`just bootstrap-bridge`。Windows 本机端到端两代自举 3m54s，产物与已滚
种子逐字节一致。Lane B 剩余：B3 CI 实跑（需推送）→ B4 Release → B5 删桥。

## 2026-11-05 P0-A：`--emit-asm` Windows 失败修复

**结果**：[yh-P0-emit-asm修复-2026-11-05](01-finished/yh-P0-emit-asm修复-2026-11-05.md)。
根因不在 MoveFileExA：探针矩阵定位到本机安全策略拒绝不受信任 exe 在
%TEMP% 创建文件（同旗标仓库目录成功）。修复：`--emit-asm` Windows 临时
目录改 CWD 优先 + TEMP 兜底（llvm_emit.yh）；桥 `publish_buffer` 失败点
带 errno 诊断（bridge.c，长期保留）。验收：llvm-architecture LA0 O0/O2
通过、固定点逐字节相同、种子重滚、`just test` 绿；`max_build_lines`
6976 → 6990。todo.md P0-1 已勾选。

## 2026-11-05 P0 收尾与发布顺序方案立项

**结果**：[yh-P0收尾与发布顺序实施方案](02-plan/yh-P0收尾与发布顺序实施方案-2026-11-05.md)。
取证收窄 `--emit-asm` 失败面（`out="-"` 只走 stdout `_write` 循环，不经过
mkstemp/MoveFileExA，聚焦 /MT 双 CRT 与 errno 诊断）；给出 CI 验收/删桥的
发布顺序线（B1–B6），并把 2026-11-05 `.test.yh` 改名 × 0.0.11 桥解析约束
的冲突解法（gen-1 staging 临时加回排序前缀）纳入。todo.md CI 段已挂方案链接。

## 2026-11-05 Windows 控制台中文显示（切 65001 码页）

**结果**：[yh-Windows控制台UTF8显示-2026-11-05](01-finished/yh-Windows控制台UTF8显示-2026-11-05.md)。
driver 启动时调 `gen.console_utf8_init()`（Windows：`SetConsoleOutputCP/
SetConsoleCP(65001)`，经 kernel32 extern；linux/darwin 空实现），
`chcp` 实测 936 → 65001 且会话保持，PowerShell 中文帮助/诊断不再乱码。
固定点逐字节相同，Windows 种子已重滚；`max_module_lines` 458 → 461。

## 2026-11-05 Windows 编译器产物改为 `yh.exe`

**结果**：[yh-Windows编译器产物yh-exe-2026-11-05](01-finished/yh-Windows编译器产物yh-exe-2026-11-05.md)。
实测 PowerShell 对无扩展名 `yh` 报「无法在管道中间运行文档」（进程未启动）；
justfile 的 `yh`/`yh_run` 在 Windows 宿主改为 `yh.exe`（种子名不变，
`bin/yh-windows-x64` 由 CreateProcess 调用不受影响）。PowerShell 实测
`.\yh.exe --version` 通过。

## 2026-11-05 测试文件统一 `.test.yh` 后缀（废止 zz_/99_ 前缀）

**结果**：[yh-测试文件test后缀-2026-11-05](01-finished/yh-测试文件test后缀-2026-11-05.md)。
编译器新增 `pj_name_is_test` + `pj_dir_less` 测试文件后置排序（VTEST）；
16 个测试文件改为 `<主题>.test.yh` / `tests.test.yh`；约定文档（编码规范、
test 测试布局）与全部引用同步。**两代自举**过渡：中间名 → yh-1 → 最终名 →
yh-2，固定点 yh-2≡yh-3 逐字节相同；Windows 种子已滚。
**⚠️ 跨平台窗口**：Release 旧种子构建本树会报「未知类型」，需协调发版。

## 2026-11-05 `yh --version` 版本编码进二进制

**结果**：[yh-版本编码进二进制-2026-11-05](01-finished/yh-版本编码进二进制-2026-11-05.md)。
`YH_VERSION_TEXT` 常量（cmdline）+ `--version` 参数（inherit 全覆盖，
不读 project.toml）；顺带修复 libs/cli `argument_from_row` 丢
`version_text` 的 bug（inherit 后回退 prog 名）并补回归测试；
arch-check 新增 toml↔常量版本一致性断言。`yh version` 子命令项目语义
不变。libs/cli 测试 55/55。

## 2026-11-05 P1：cmd 一命令一文件

**结果**：[yh-cmd一命令一文件-2026-11-05](01-finished/yh-cmd一命令一文件-2026-11-05.md)。
`cmd/` 重组为 10 文件：`driver.yh` 只剩分派，`api.yh` 删除，新增
`common.yh` + 8 个 `cmd_*.yh`；`api_*` 全部转模块私有，导出面只剩 `main`。
无行为变化（--timeout 校验、rc==2 用法补印、会话前奏次序均原样迁移）。
架构目标见 [架构设计 §6.4](03-design/yh-架构设计.md)。
`max_module_lines` 387 → 458（+71 全为文件头注释，逻辑行不变，边 55 不变）。

## 2026-11-05 SDK 迁移 vendor

**结果**：[yh-SDK迁移vendor-2026-11-05](01-finished/yh-SDK迁移vendor-2026-11-05.md)。
`compiler/{darwin,windows}-sdk` → `vendor/`（git mv 保历史；windows 侧先核对
未跟踪副本逐字节一致后去重）。同步编译器运行时查找（`darwin_link.yh`
suffixes、`windows_link.yh` prefixes）、justfile 5 处、tools 2 个、selfhost
测试 4 个、AGENTS.md。**实测**：清空 `YH_WINDOWS_SDK`/`YH_DARWIN_SDK` 后
仓库根 `yh` 经 exe 相对路径命中 `vendor/windows-sdk/lib` 完成链接并运行成功。
`compiler/` 回归纯 yh 模块目录。

## 2026-11-04 当前架构重新分析（只读取证）

**结果**：架构复核已合并入 [架构设计](03-design/yh-架构设计.md)。
`python tools/arch-check.py` 实测 **16 模块 / 134 文件 / 57,274 行 / 55 边，检查通过**。
对 10-25 基线的核心结论：B1（`proj` 1,396 行）/ B2（`link` 4,272 行）/ B1-4
（`gen.G()` 165 → 0）全部落地；`build` 单体 10,717 → 6,953 行。

- **新增顶格项两处**：`link` 4,272 = `max_link_lines`（W2 Windows 链接 +509 推满）、
  `parse/parse_expr.yh` 2,042 = `max_file_lines`；建议文件级拆分解除。
- **漂移复发**：`compiler/README.md` 10-27 人工同步后再次过期（仍写 13 模块 /
  53,545 行，缺 `proj`/`link`/`cmdline`）；建议把模块表纳入 `arch-check` 断言。
- **未动旧账**：`testkit → build` 仍有 13 处 `mb_*`/`cmd_*` 引用；五处契约常量
  仍分散（期间 `IR_FUNCTION_CACHE_VERSION` 1→2 兑现过一次升级成本）；
  `module_worker.yh:130` 废参数链待 C2。

## 2026-11-06 gen 职责拆分 GEN0–GEN2（首轮）

**结果**：ADR-0021 + 实施方案落地；`gen` 从 5,804 行 / 183 pub / 15 importers
降到 **2,555 行 / 76 pub / 13 importers**，`TaskCtx` 189→155 字段。

- **GEN0**：`arch-check` 递归扫描 + 新模块边 + `gen` 单调预算
  （`pub fn`/importers/`TaskCtx` 字段/全局），自测 5/5。
- **GEN1**：新增 `support`（源/池/统计/诊断/目标/ABI 常量/宿主平台/会话开关）
  与 `token`（词汇/`PDecl`/token 状态/游标/`err_tok`/`is_assign_op`）；
  `PDecl` 归 token 规避 `proj↔ast` 环；`fail` 与 `err_lc` 同置 support 避免环。
- **GEN2/F1**：`CheckedModule`/`CheckedStorage`/视图/check 键/函数切片从 `ast`
  迁 `check`；`ast` 只剩纯语法 arena（3,414→1,364 行）；新增
  `ast/ast_store.yh`（arena 扩容入口）与 `ast/ast_view.yh` 完整视图。
- **GEN2/F3 首片**：`sem_value`/`sem_expr`/`sem_decl`/`sem_flow`/
  `sem_call_literal` 与 C ABI 算法迁 `check`；token 游标/入表/报错直连
  `token.*`（删除 `gen/token_bridge.yh`），后端与 proj/link/cache 的
  目标/ABI 常量改走 `support.*`；常量折叠/浮点/布局收尾集中
  `gen/value_rules.yh`（`comptime` 共用）；C ABI 模型留 `gen/abi_model.yh`。
- **验证**：`yh check` 全绿；arch-check 5/5；fixture 实跑通过
  （support/token/llvmtarget/llvmfront/llvmchecked/llvmlower/astcheck）；
  `just` 全模块编译通过，仅本机 Darwin LLVM host 闭包缺失导致链接失败
  （环境问题，非本次改动）。
- **GEN2 状态收尾片**：`parse.ParseCtx`（4 字段）落地、`TaskCtx` 155→150；
  `check/checked_model.yh` 新增受检表分配的语言内测试；
  `gen/token_bridge.yh` 删除；`import gen` 14→13、`gen` pub 79→76。
- **F4-1（本轮）**：CT 类型镜像改「绑定槽」，类型表扩容/搬迁后无需重绑；
  `comptime` 的 44 处谓词、19 处 `CType` 读、130 处 `TY_*` 常量改镜像
  （`gen.` 引用 594→365）。
- **F4-0（本轮）**：`comptime/ct_facts.yh` 零拷贝类型镜像 + `check/ct_bind.yh`
  绑定点/形状守卫；`tests/modules/projects/ctfacts/` 差分 fixture 实跑通过。
- **未完成**：F2（`parse` 纯语法）与 F4 其余步（`comptime` 纯 CT IR 执行器）未做，
  因此 `CType/CSym/ty_*/sym_*/static_data/value_rules` 仍留 `gen`——`comptime`
  仍直接依赖这些规则，先迁会成 `check ↔ comptime` 环。

## 2026-11-08：CI 全绿修复（GEN/F4 批次遗留回归收口）

背景：GEN0–GEN4 与 F2/F4 大批重构后 CI 连续红灯（在 4 端均复现），本轮用
`gh run view --log` + 临时 printf 诊断定位到 **四个独立根因**，全部修复后
CI run `42463040423` **四端全绿**（linux-x64 / linux-arm64 / windows-x64 / darwin-arm64）。

| # | 根因 | 影响 | 修法 |
| --- | --- | --- | --- |
| 1 | CT 镜像行访问器按值返回，`ct_type_row(tid).size = …` 只改副本 | 编译期数组长度/结构体布局永远无法完成 → 21 例 `run/9x~18x` + 2 例 `fail/` 失败与段错误 | 新增 `ct_type_at`/`ct_sym_at`/`ct_field_at` 指针视图，10 处写回改写；`arch-check` 加 `max_ct_row_field_writes: 0` |
| 2 | `ct_tables_bind` 的 data-str/em 八个槽传的是**数组基址**，读侧按 `**int` 解引用 | 编译期字符串字面量实参必崩（`run/141/145/156/158`） | 槽类型改为直接基址指针（`*int`/`*i64`），`ct_data_str_lookup` 等去掉 `[0]`；类型收紧后错法直接编译失败 |
| 3 | `checked_slice` 切片导入把行数写成 `v.expr_count += n`（`AstView` 是副本） | 函数级 IR 缓存命中的模块构建 `verify_module` 报「函数声明 AST 缺少函数体根」；`llvm-global-cache` 预热失败 | 新增 `ast.ast_view_append_expr/stmt/edge/binding/function`，由 ast 提交回 arena 计数；`arch-check` 加 `max_ast_view_count_writes: 0` |
| 4 | `checked_decl_restore` 在 arena 复位**之前**取视图，复位后仍用旧视图写声明字段 | `check-slice` 往返（`llvmlower` 的 `checkcache.yh`）段错误 | 视图改为复位 + `ast_decl_add_file` 之后重新取 |
| 5 | Windows 侧：`vendor/windows-sdk` 的 kernel32 导出缺 `SetConsoleOutputCP`/`SetConsoleCP`；且引入 `check` 的 fixture 在零 CRT 下缺 VC 运行时（`strtod`） | windows 4 个 fixture 链接失败 | 补 def + manifest（重算 `def_sha256`）；fixture 仅在引入 `check` 时追加编译器自身的 `[link-windows-x64] support` 清单（避免与 yh 自有 `memcpy` 冲突） |

同时把 4 端 project cases 从 88/128 提升到 **140/140（linux）、135/135（windows）、129/129（darwin）**，
`tests/yh-run` 语料 367/372~370/372（其余为平台跳过）。

经验：这类「按值视图/镜像写回」bug 本地 `yh check` 与 fixture 门禁都抓不到，
必须靠 `tests/yh-run`（重建编译器）或 CI；因此新增的两条 arch-check 预算
（`max_ct_row_field_writes`、`max_ast_view_count_writes`）用于静态拦截同一错法。

## 2026-11-08：本地构建环境恢复（LLVM 21 宿主闭包）

> 日期口径：以**提交时间**为准（`gen` 删除提交 `01cec48` 为 2026-11-07 23:41）。

此前 `just` 全链路被两个环境问题卡住：

1. **SDK 目标标签**：`xcrun` 默认指向 Command Line Tools 的 macOS 27 SDK，其
   `usr/lib/libSystem.tbd` 含 `arm64e.x1`，固定 LLVM 21.1.8 的 lld 不认。
   修法：`SDKROOT=/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk`
   （Xcode 26.5 SDK，无该标签）。注意 `justfile` 会用缓存记录里的 `sdk_root` 覆盖
   `SDKROOT`，所以首次准备必须直接调 `tools/llvm-darwin-host.py prepare`。
2. **磁盘门槛**：`tools/llvm-darwin-sdk.py` 在源码**未解包**时要求 8 GiB 空闲
   （`MIN_FREE_BYTES`），解包后只需 5 GiB（`MIN_BUILD_FREE_BYTES`）。先清
   `~/Library/Caches/yh`、`tmp/modcheck`、`tmp/fx-*`、`.codegraph`、`compiler/.build`
   腾到 ≥8 GiB，即通过首轮检查；之后按 5 GiB 门槛继续。

结果：`odd` 闭包就位（`tmp/llvm-migration/llvm-host-darwin-aarch64/libyh-llvm-bridge.a`
+ `lld_bridge.o` + `sdk-darwin-aarch64` + `host.json`，`sdk_version=26.5`）。

本地门禁（此前完全无法运行）现已全绿：

| 命令 | 结果 |
| --- | --- |
| `just fetch-seed`（需 `GITHUB_REPOSITORY=lalavender/x`） | 0.0.12 种子 → `bin/yh-darwin-arm64` |
| `just`（冷编） | 24s，产出 `./yh` |
| `just test` | **370/372（2 跳过），全部通过**；compiler-tests 8/8；arch-check 8/8 |
| `just selfhost-native` | 模块固定点一致（54 产物）、cc4 自解析 178 文件 OK、**project cases 129/129** |

至此「本地 `yh check`/fixture 抓不到按值写回类 bug」的盲区也消除：
`tests/yh-run` 与两代固定点都能在本地跑。

补充（同日）：把「SDK 自动回退」做进工具，`just` 不再需要手工 `SDKROOT`。

- `tools/llvm-darwin-sdk.py::resolve_sdk_root`：显式 `SDKROOT` → `xcrun` 默认 SDK
  → `/Applications/Xcode*.app/**/MacOSX*.sdk`（新→旧），逐个 `load_sdk_version`
  + `reject_incompatible_sdk`；回退时在 stderr 说明原因与实际 SDK。
- `tools/py`：统一挑 ≥3.10 的 Python（macOS 自带 `python3` 可能是 3.9，读不了
  `X | None`），`justfile` 的反引号与配方共用。
- `tools/llvm-darwin-sdk.py` 增加「构建器源码变了但配方/产物没变」时只重写身份记录
  （`verify_artifacts`），`tests/selfhost/llvm-darwin-sdk.py` 同步补齐自测。

验证：`python3 tests/selfhost/llvm-darwin-sdk.py --self-test` → PASS（含产物改写
校验 3/3）；`just llvm-host` → 0.6s `reused: true`；`just` 冷编通过；
`arch-check` 8/8；`just test` 370/372 全部通过。

后续 DX 修补（同日）：

- `tools/fetch-release-seed.py`：`--repo` 缺省时从 `git remote get-url origin`
  推断 `owner/repo`，本地 `just fetch-seed` 不再需要 `GITHUB_REPOSITORY`。
- `tools/llvm-darwin-sdk.py`：磁盘不足的错误信息追加清理建议（`~/Library/Caches/yh`、
  `tmp/modcheck`、`tmp/fx-*`、`compiler/.build`、`.codegraph`，或 `YH_LLVM_CACHE`
  改到别的盘）。
- 复验：`just llvm-host` 0.6–5.5s（`reused: true`，改工具源码也只重写身份记录，
  不重编 LLVM）；`just` 冷编 26s；`just test` 370/372 全部通过；`just selfhost-native`
  固定点一致 + 自解析 178 文件 + project cases 129/129。

踩坑记录：`py_default` 一开始写成 `quote(root + "/tools/py")`，而配方里本来就是
`"{{ py }}"`（自带双引号），重复引号让 shell 把带引号的字符串当命令名，
`test-windows-sdk` 在 linux-arm64 上以 127 失败。改为相对路径 `tools/py` 后
CI 四端全绿（run 42486762530）。

## 2026-11-08：前端两遍化重新分析（结论：不再全量重写，改 S1–S4）

用实测数据复核 2026-11-06 的 F0–F7：

- `parse` 9,626 行 / 21 `pub fn`；`check.*` 190 次、`comptime.*` 118 次调用；
  `Res` 字段读取 **370 处，其中 167 处直接决定语法分支**（`type_id` 52、`ival` 37、
  `is_const` 21、`is_lit` 20、`lit_big` 18…）→ 「纯语法 parse」仍需 AST schema 改造。
- **最大的新发现**：`AstExpr` 22 字段里 11 个是语义字段，而 `lower` 直接读它们
  **257 处**（`comptime` 486、`check` 322 之外）。今天的「AST」就是受检表示，
  纯语法化等于**换掉 lower 的输入契约**，原计划低估了这一项。
- 依赖方向约束更明确：`parse → check` 已成事实，因此任何「搬进 check 但仍要
  重新解析源码」的逻辑都会成环 → `parse_ct_layout`(501 行) 与
  `iface_load`/`iface_ct_load`(392 行) **不能**迁；而**接口发射侧**
  (≈1,900 行，只读 `ms()`/CT registry/AST 区间) 可以。

据此把 F0–F7 换成 S1–S4（详见 `docs/02-plan/yh-前端两遍化-重新分析-2026-11-08.md`）：
S1 接口发射下沉 `check`（≈1,900 行，零环风险）、S2 解析器窄口后迁布局调度、
S3 语义字段改由 `check` 写入（真两遍化核心）、S4 纯语法 AST + 独立 checked IR（一般不做）。
`docs/todo.md` 的 F0–F7 条目已按此替换，并列出 3 个待用户决策的问题。

## 2026-11-08：S1 接口发射下沉（parse 9,626 → 7,640 行）

按 `docs/02-plan/yh-前端两遍化-重新分析-2026-11-08.md` 的 S1 执行：

- 新建 `compiler/check/iface_emit.yh`（2,069 行）：`if_put*` + 接口文本缓冲、
  `if_emit_type`/`iface_emit`/`iface_emit_pub_agg_src`、`iface_ct_emit*` 全套、
  列映射（`IfaceCtColMap`/`iface_ct_col_*`）、`iface_ct_origin_begin/end`、
  `sym_mangle`/`tname_mangle`、头部前缀与 `IFACE_VERSION_*`/`CTIFACE_VERSION`。
- `parse` 只留**加载**侧：`iface_load`、`iface_ct_load`、`iface_ct_header_valid`、
  `iface_ct_export_name`、`mod_ns_add`；`parse/iface_ct_map.yh` 删除。
- 跨模块复用点（14 个文本/头部工具）在 `check` 里 `pub`，`parse` 以 `check.` 前缀调用；
  `build` 的调用点改为 `check.iface_emit` / `check.iface_ct_emit`，
  `IFACE_VERSION_*`/`CTIFACE_VERSION` 改从 `check` 取。
- 为什么必须这样切：`parse → check` 已成事实，`iface_load`/`iface_ct_load` 要
  `parse_source` 重新解析，搬进 `check` 会形成 `check → parse` 环；发射侧只序列化
  受检事实（不重新解析），因此可以下沉。

指标：`parse` **9,626 → 7,640 行（−20.6%）**，文件 14 → 13，`pub fn` 21 → 19，
`parse → comptime` 调用 **118 → 85**；`check` 6,038 → 8,138 行（15 → 16 文件）。

验收（本地全绿）：`just` 冷编通过；`just test` 370/372（2 跳过）+ compiler-tests 8/8 +
arch-check 8/8；`just selfhost-native` 固定点一致（54 产物）、cc4 自解析 178 文件、
project cases 129/129。**等价性**：`comptimecross` 的 8 个 `.s.i`/`.s.ct` 与迁移前
逐字节一致（`cmp` 全通过）。编译器自身 `.s.i` 有差异属预期（`iface_emit` 等符号
从 `parse` 接口移到 `check` 接口），符合 ADR「跨模块搬家不要求编译器自身接口一致」。

## 2026-11-08：S2a 解析器窄口 + 布局策略下沉（并修正 S2 方向）

S2 原计划「把 `parse_ct_layout` 迁 `check`」在实施时被证伪：该文件核心要**重入解析器**
（`parse_expr`），搬进 `check` 会与既有的 `parse → check` 形成双向环。
`parse.eval_token_range` 窄口只能收敛「重入」，不能消除方向约束，因此只执行可行的一半：

- 新增 `parse.eval_token_range(first, after, out *support.Res)`：自管 token 游标、
  AST 捕获开关与 `c_fold`，替换 `parse_ct_layout` 内两处重复样板（数组长度表达式、
  延迟枚举判别值），失败时游标与捕获状态一律恢复。
- 新增 `comptime/ct_layout_sched.yh`：`ct_layout_expr_runnable`（const / CT 函数 /
  `sizeof` 依赖判定）与 `ct_layout_expr_register`（依赖边登记）。二者只读 token 表与
  `support.ms()`、只写 comptime 自己的依赖图，**不重入解析器**，因此下沉合法，且与
  布局请求数据同处一个模块。
- S2b（调度整体下沉 `check`）并入 S3 前置条件：必须先让 `parse` 不再 import `check`。

指标：`parse` 7,640 → **7,580 行**，`comptime` 5,956 → 6,076 行（含新文件头）。
验收：`just` 通过；`just test` 370/372 + compiler-tests 8/8 + arch-check 8/8；
`just selfhost-native` 固定点一致、cc4 自解析 178 文件、project cases 129/129；
`comptimecross` 的 8 个 `.s.i`/`.s.ct` 与 S1 后**逐字节一致**。

## 2026-11-08：S3 spike（语义字段外置的可行切片）

实测 `parse`（7,580 行）里 `check.sem_*` 调用 **50 行**、`Res` 字段读取 **370 处**
（控制流决策 167 处）。按构造归类得出结论：

- **不可延后**（语法决策输入）：`type_id`（字面量定型/运算符结果/元素类型）、
  `sym`（名字解析决定 `.`/调用形态）、`is_lit`/`lit_big`（窄化与类型选择）、
  `sizeof` 布局依赖 → 「全量纯语法 parse」仍不可行。
- **可延后**：隐式转换校验（18 处，纯校验，三元两处除外）、编译期诊断（8 处，
  已设计为语句位置消费）、纯值折叠（11 处，但会被长度/条件位置读取，需先打标记）。

据此提出三个切片 S3a/S3b/S3c（规模、风险、验收方式见 spike 文档），并明确不做
独立 checked IR（S4）。S3 全部完成的收益是 `parse` 不再 import `check`，从而解锁
S2b（布局调度整体下沉）。待用户决策：是否接受诊断顺序变化、是否加
`max_parse_check_calls` 预算。

## 2026-11-08：S3a 首片——`return` 隐式转换校验后移

按 S3 spike 的「首个错误即停、诊断逐字一致」方案落地第一片：

- 新增 `check/convert.yh`：
  - `convert_returns(view)` 遍历每个函数的语句区间，对 `AST_STMT_RETURN` 取表达式边
    → 表达式节点，用 `support.vk_can_assign(返回类型, …)` 判定；
  - `diag_file_at(file_id, line, col, code)`：按 `file_id` 切 `src_ctx().path` 后
    调 `support.err_lc`，多文件模块也报对文件名；
  - 位置取 `AstExpr.after` —— `ast_expr_finish` 写的是「解析结束时的游标」，
    正是 parse 期 `sem_can_assign` 使用的位置，因此诊断**逐字一致**。
- `parse/parse_stmt.yh` 的 `return` 分支不再调 `check.sem_can_assign`
  （聚合返回值规则 `sem_return_value` 仍留在 parse：它要就地修改 `Res`）。
- `build/module_worker.yh` 与 `build/llvm_emit.yh`（单文件路径）在
  `check.verify_module` 之前调用 `check.convert_returns`。

等价性验证：两个探针（`u8` 返回 300、`*char` 返回 1）在改动前后输出**逐字相同**
（`4:15: 字面量超出目标类型可表示范围`、`4:13: 不能把非指针值赋给指针`）。
新增 `tests/yh-run/fail/169-return-conversion.yh`。

门禁：`just` 通过；`just test` **371/373（2 跳过）**、fail 139/139、pass 10/10、
compiler-tests 8/8、arch-check 8/8；`just selfhost-native` 固定点一致 + 自解析
178 文件 + project cases 129/129。`max_parse_check_calls` 142 → **141**。

随后把**赋值语句**一并后移（同日）：`check.convert_assigns(view)` 取 ASSIGN 语句
表达式链上的第 1、2 条边（先左值后右值），判定 `vk_can_assign(lhs.type_id, rhs…)`，
位置同样用 `rhs.after`。四例探针（return 窄化 / return 指针 / 赋值窄化 / 赋值指针）
在改动前后诊断**逐字一致**；新增 `tests/yh-run/fail/170-assign-conversion.yh`；
`just test` **372/374**、fail 140/140；`just selfhost-native` 全绿；
`max_parse_check_calls` 141 → **140**。

## 2026-11-08：前端两遍化任务线收束（转入 0.0.13-rc.1 发布）

按用户决定：架构将重新设计，**当前两遍化任务线到此收束**。已完成并随 0.0.13-rc.1
发布的部分：S1 接口发射下沉（`check/iface_emit.yh`）、S2a 解析器窄口
（`parse.eval_token_range`）与布局策略下沉（`comptime/ct_layout_sched.yh`）、
S3a 的 `return` / 赋值两片（`check/convert.yh`）。未完成的 S3b/S3c 与 S3a 剩余 15 个
站点不再推进，分析归档到 `docs/01-finished/`。

### LLVM 闭包身份：改用「配方摘要」，不再因工具脚本改动重编

`just llvm-host` 之所以动辄 30–40 分钟，是因为身份记录曾包含**构建器脚本自身的文件
摘要**（`tools/llvm-darwin-sdk.py` / `tools/llvm-darwin-host.py`）与**整份锁文件摘要**：
这轮环境修复里只要改一行注释/提示，`host.json` 立刻判为过期，`ensure()` 就走全量
LLVM 重建（3,368 个 ninja 步骤，默认 `--jobs 2`）。此外部署的桥归档确实比当前
`compiler/llvm/bridge.c` 旧（重建后摘要由 `d133e2a5` 变为 `bdb7d4aa`），所以那次等待
并不全是白等。

修法：

- 新增 `tools/llvm_recipe.py`：
  - `sdk_recipe_digest()` = 锁文件里的 `darwin_source.sha256` + `darwin_build` 规格；
  - `host_recipe_digest()` = `bridge.c`/`bridge.h`/`lld_bridge.cpp` 摘要 + 锁文件摘要 +
    `deployment_target` + `sdk_recipe_digest()`。
  两个工具（SDK/宿主）在写入与比较身份时都用这两个摘要，**不再哈希脚本自身**。
- `check()` 的 `manifest_sha256` 比较保留（锁文件变更仍会触发重建——那是真正的配方变化）。
- 结果：`just llvm-host` 由 30+ 分钟降到 **1.0s**（`reused: true`）；桥归档与当前
  `bridge.c` 对齐后，`just` 冷编 65s（含全量重新链接）。

经验：**身份要绑定「决定产物的输入」，不要绑定「产生输入的程序」**；否则任何工具
改动都会让增量缓存失效。

### 0.0.13-rc.1 发布与发布二进制验收（2026-11-09）

- tag `0.0.13-rc.1` → release 工作流 run `42599758790`：prepare / linux-x64 / linux-arm64 /
  darwin-arm64 / windows-x64 / publish **全部成功**；Release 标记为 prerelease，
  8 个资产（四端 tar.gz + sha256），远端大小校验一致。
- 首轮 release 失败过一次：`tests/selfhost/darwin/llvm-darwin-sdk.py` 用
  `runpy.run_path` 加载 `tools/llvm-darwin-sdk.py`，而该文件在定义 `ROOT`/补
  `sys.path` 之前就 `from llvm_recipe import ...` → `ModuleNotFoundError`。
  修法：把 `sys.path.insert` 提到 import 之前（提交 `a95148e`），本地两个 SDK 门禁
  复跑 PASS；随后删除并重推 tag（未生成 Release，允许）。
- **用发布出去的二进制验收**：`rm -rf bin && just fetch-seed` 取到
  `0.0.13-rc.1`（sha256 `8f40a72b…`）→ `just` 冷编 → `./yh --version` = `yh 0.0.13-rc.1`
  → `just test`：run 372/374（2 跳过）、fail 140/140、pass 10/10、compiler-tests 8/8、
  arch-check 8/8 → `just selfhost-native`：固定点一致、自解析 178 文件、
  project cases 129/129。

### 0.0.13 正式版发布与发布二进制验收（2026-11-09）

- 首轮 tag `0.0.13` 失败：`tests/selfhost/fixtures/llvmcachelib` 在上一次提交里被误
  记成了 `tests/selfhost/darwin/llvmcachelib`（重命名），linux-x64 的
  `llvm-cache.py` 找不到 fixture（`FileNotFoundError`），release 的
  linux-arm64「自举门」同样失败 → 未生成 Release（允许重推 tag）。
- 修法：`git mv` 回 `tests/selfhost/fixtures/llvmcachelib`（`b451bc9`）；顺带清掉
  `compiler/link/link_cache.yh` 注释里两个 NUL 字节（git 因此把该文件当二进制，
  `git grep/diff` 看不到内容，`392ec56`）。
- 重推 tag → release run `42610237484`：prepare / 四端 / publish **全成功**；
  Release `0.0.13` **正式版**（`prerelease=false`），8 个资产。
- **发布二进制验收**：`rm -rf bin && just fetch-seed` 取到 `0.0.13`
  （sha256 `299ad509…`）→ `just` → `./yh --version` = `yh 0.0.13` →
  `just test`：run 372/374（2 跳过）、fail 140/140、pass 10/10、compiler-tests 8/8、
  arch-check 8/8 → `just selfhost-native`：固定点一致、自解析 178 文件、
  project cases 129/129、LA3 O0/O2 与 C4/C6 全通过。
