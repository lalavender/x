# finish

滚动日志：只保留最近三天（当前为 2026-10-26 ～ 2026-10-28）的交付记录，靠前条目为最新状态。
更早的 475 条（2026-09-27 ～ 2026-10-25）已归档在
[finish 历史归档](01-finished/finish-历史归档-2026-09-27至2026-10-21.md)（归档文件按批追加，标题保留首批日期区间）。
超出窗口的条目迁入同一个归档文件，新增条目写在最前。

## 2026-10-28 构建缓存目录可指定（YH_BUILD_CACHE）

- **编译器（合入 llvm 的 B1/B2 结构后）**：`compiler/proj/proj_40_art.yh` 新增
  `cache_root()` 并改写 `build_dir()`——`YH_BUILD_CACHE` 非空时整套缓存树
  （`targets/...`、`check/` 与 asm/obj/iface/manifest/ir/llvm 子目录）落在该目录，
  空/未设置时仍是项目内 `.build`；测试模式仍固定 `tmp/yh-test/check`。
  `compiler/build/module_build.yh` 新增 `mb_ensure_binary_dir()`，独立确保项目
  `.build` 存在，默认可执行文件位置不随缓存迁移而变。
- **合入 llvm 分支（同日）**：先提交 llvm 工作区已有的 B2-3（`mb_link` →
  `LinkPlan` + 六阶段、失败路径统一释放，`link` 3,657 行），再把 llvm-2 的 7 个
  提交合入。6 个冲突按「保留 B1/B2 结构、重放 CLI-R」解决：`gen.G()` 改
  `gen.task()`/`gen.stats()`/`proj.cfg()`/`proj.ctx()`，`--link`/`--resolve`/
  `-o`/模块/`--timeout` 等从 argv 扫描改为 `CliRequest` 字段，缓存根落在
  `proj` 的 art 层；预算按实测更新（`max_link_lines` 3,657、`max_proj_lines`
  1,353）。
- **justfile**：`BUILD_CACHE`（环境变量 `YH_BUILD_CACHE`）贯通 `build`/`dev`/
  `clean` 与 `_ensure_built` 的子 `just`；冷编时连同缓存根一起清。门禁脚本按
  项目内 `.build` 断言，`unexport YH_BUILD_CACHE` 让 `test`/`selfhost-native`
  始终在缺省布局下跑，不受用户缓存位置影响。
- **测试**：新增 `tests/build-cache/check.py`（接入 `just test`）：设置
  `YH_BUILD_CACHE` 后对象落在缓存根、项目内无 `.build/targets`，二次构建增量
  命中；不设置时回到缺省 `.build/targets`。
- **验证**：`just test` 全绿（运行语料 360/361、新增 build-cache 4/4、arch-check
  通过）；`just selfhost-native` 全绿（模块固定点 42 产物一致、cc4 自解析 120
  文件、CLI 冒烟含 `--help`、运行语料 360/361、project cases 122/122）。滚种子
  `bin/yh-darwin-arm64`（SHA-256 `1591d13b16140e7ecaa7ad30034ccdf1d05003cc358e843f5462c3b9a8b643fc`）
  后复验：新种子下 `YH_BUILD_CACHE=/tmp/yhbc-real just build` 把 21 个对象写进
  指定目录、`compiler/.build` 不出现；`just dev` 1.4 s 全部 `[缓存]` 命中；
  冷编回缺省布局后再跑 `just selfhost-native` 全绿。带
  `YH_BUILD_CACHE=/tmp/yhbc-gate just test` 也全绿：门禁自身的项目构建仍落在
  各自的 `.build`，没有往该目录写入（只有顶层 `_ensure_built` 的构建会用它）。

**合入后的 llvm 分支复验**（合并提交）：`just test` 全绿（语料 360/361、
build-cache 4/4、arch-check 通过：16 模块 54,456 行、`gen.G()` 0、main 318 行）；
`just selfhost-native` 全绿（候选固定点 48 个产物逐字节一致、cc4 自解析 127 个
源文件、CLI 冒烟含 `--help`、运行语料 360/361、LA3 函数级缓存矩阵、project
cases 122/122）。

## 2026-10-27 修 llvm-host 缓存路径 bug + justfile 暂存目录隔离 + 滚种子

- **`tools/llvm-darwin-host.py` / `tools/llvm-host.py`**：新增 `describe()`，把
  `Path.relative_to(ROOT)` 换成「仓库内显示相对路径、仓库外显示绝对路径」。
  闭包默认落在 `$YH_LLVM_CACHE`（`$HOME/Documents/x/tmp/llvm-migration`，仓库外），
  原实现会在 `just llvm-host` 失败时抛 `ValueError: ... is not in the subpath of ...`，
  把真正的原因（SDK/bridge 摘要不匹配）盖掉。身份记录里的
  `selfhost_flags_file`/`selfhost_runtime_file`/`cxx_tbd` 也一并改用 `describe()`：
  消费方按 `ROOT / value` 读取，绝对路径在 pathlib 下同样成立。
- **`justfile` 暂存目录按 worktree 隔离**：`FAST_DIR` 缺省从 `$TMPDIR/yh-fast` 改为
  `$TMPDIR/yh-fast-<仓库路径 sha256 前 8 位>`。同一台机器的多个 worktree 共享
  `$TMPDIR`，原先会互相覆盖 staged 编译器与 `darwin-sdk` 软链——实测 llvm-2 的
  `just test` 跑在 llvm-3 的二进制上（3 条 `pass/` 用例报「函数未使用」，
  `darwin-sdk` 软链指向 llvm-3），排除后全绿。CI 的 `GITHUB_RUN_ID` 后缀保留。
- **滚种子**：`just bootstrap`（复用本机固定闭包）冷编 → `just test`、`just
  selfhost-native` 全绿（固定点 42 产物、cc4 自解析、CLI 冒烟、运行语料 360/361、
  project cases 122/122）→ `just seed` 更新 `bin/yh-darwin-arm64`
  （SHA-256 `0ac4586a4a8aa9ab8eca0e3bb500ffa7593443a308890c9e177b3d4ceb2e41ba`）。
  随后用**新种子**重新冷编（`rm -rf compiler/.build && just`）并再跑
  `just selfhost-native` 全绿——新种子自带用 `libs/cli` 解析的命令行与
  `yh --help`/`yh <命令> --help`。

## 2026-10-27 CLI-R4：yh 帮助/诊断改由 libs/cli 生成

- **删除手写 `usage()`**：`yh`、`yh <命令>` 的帮助与解析失败的 usage 全部由
  `libs/cli` 的 `format_help`/`format_usage` 生成，`cmdline` 里 `print_bare_help`/
  `print_usage`/`print_control` 三个薄封装负责落 fd。
- **`-h/--help` 成为正式能力**：顶层帮助列全部子命令与单文件形态说明，子命令帮助
  由 `Command.config` 的 `help_format` 决定（中文段标题 `位置参数/选项/命令`，
  usage 前缀 `用法: `），help/version 控制结果写 stdout、退出 0。
- **libs/cli 两处小增强**：`HelpFormat.usage_prefix`（默认 `usage: `）与
  optional 位置参数只套一层方括号（`[module]` 而非 `[[module]]`）；cli 用例 52 → 54。
- **冒烟与金标**：`tests/selfhost/native-selfhost.py` 的 CLI 冒烟补 `--help`
  （退出 0 + 用法 + 命令名）；`tools/cli-golden.py` 的文本类用例改为宽松
  （10 条，均为「usage/help 文本按设计改变」），行为类仍严格 36/36。
- **文档**：`AGENTS.md` 使用段、`README`、`libs/cli/README.md`（配置项）、
  `docs/03-design/yh-cli标准库设计.md`（HelpFormat 配置面）。
- **验证**（种子 `bin/yh-darwin-arm64`）：`just test` 全绿；`just selfhost-native`
  全绿（固定点 42 产物、cc4 自解析、CLI 冒烟含 `--help`、运行语料 360/361）；
  `just libs-test` 全绿；`tools/cli-golden.py` 36/36（10 条宽松为文本变化）。

## 2026-10-27 CLI-R1：yh 命令行改用 libs/cli 解析（入库）

- **新模块 `compiler/cmdline/`**（`module cmdline`，568 行）：`CliRequest` + 两个 parser
  （project：`build/check/run/test/list/version`；file：`--syntax-check`/`--emit-asm`/`-o`），
  全局选项（`--target/-target`、`--backend`、`-O0/-O2`、`--emit-llvm`、`--stats`、
  `--legacy-system`）声明在公共 parent 再 `inherit`，保持「子命令前后都能写」。
- **`cmd` 回到薄壳**：`api_*` 接收请求结构；`mb_cmd_build/run/list`、
  `mb_run_test_command` 删除 argv 扫描、改接收已解析字段；`driver.yh` 只做
  「请求 → 全局状态 → 分派」，`usage()` 移入 cmdline。`main` 307 行（预算 381 内）。
- **依赖与门禁**：`compiler/project.toml` 增 `[dependencies] libs = {path = "../libs"}`，
  `cmdline` 用 `import libs.cli`（绑定名仍 `cli`）；arch-check 登记
  `cmdline -> libs`、`main -> cmdline`。`tools/selfhost_snapshot_gate.py` 增
  `follow_dependencies` 开关与 `dependency_artifacts()`（依赖模块产物「允许出现但
  不要求」），`native-selfhost.py` 只要求本地模块齐全。
- **等价性**：`tools/cli-golden.py` 36 条 argv **36/36 通过**（6 条宽松项为
  「新实现多打印一条诊断」）。
- **踩坑记录**：切换编译器后必须清 `compiler/.build`——混用不同版本的对象/接口会给出
  假诊断（把在用函数报成「函数未使用」、`-target linux` 的别名判定走错分支）。
- **验证**（种子 `bin/yh-darwin-arm64`，`YH_LLVM_HOST=0` + `tmp/llvm-migration` 软链）：
  `just test` 全绿；`just selfhost-native` 全绿（模块固定点 42 个产物一致、cc4 自解析
  120 文件、CLI 冒烟、运行语料 360/361）；`just libs-test` 全绿；
  `python3 tools/cli-golden.py` 36/36。

## 2026-10-27 CLI-R0：cli 段标题可配置 + yh CLI 等价性金标

- **libs/cli**：`HelpFormat` 增 `section_positional`/`section_options`/
  `section_commands`（空指针沿用英文默认），`help.yh` 的 `put_title` 改读字段；
  这样 yh 重写命令行时能保留中文帮助段标题。用例 51 → 52。
- **tools/cli-golden.py**（新）：同一批 argv 分别交给旧/新编译器，比较退出码 +
  归一化输出（路径占位、`time_*` 归零、`yh-stats` 值隐藏、`[编译]/[缓存]…`
  进度行按多重集合）；每个用例在独立 fixture 副本里冷跑。
  当前 36 条用例 **36/36 通过**，其中 6 条是「新实现多打印一条诊断」的宽松项。
- **规划**：新增 `docs/02-plan/yh-CLI用cli标准库重写实施方案-2026-10-27.md`
  （现状盘点 + 目标形态 + 六期切片 + 金标设计 + 风险）；`docs/todo.md` 增 CLI-R0…R5。
- **R1 原型（未入库）**：`cmdline` 模块 + cli 解析 + 分派改造在本机跑通
  （`cli-golden` 36/36、`just test` 全绿、arch-check 通过：main 307 行、新模块
  568 行并登记 `cmdline -> libs`），但 `just selfhost-native` 在「cc2 产物集合」
  处失败：编译器 import 标准库后，种子构建会额外发布 6 个 `yh_libs-*` 模块的
  `iface/.s.i` 与 `llvm/.ll`；同一seed 构建未改动 HEAD 时集合完全一致（0 多余/0 缺失），
  证明差异来自新增的标准库依赖。三条前置问题与收口方式记在方案 §12，
  原型补丁留在 `tmp/cli-migration/cli-r1-prototype.patch`。
- **验证**：`cd libs && yh test` = 131 passed（cli:: 52）；`just test` 全绿
  （含 arch-check 自测与真实树）。

## 2026-10-27 CLI-G 调查：帮助宽度自动被 C ABI 挡住（不改代码）

目标：让 `HelpFormat.width = 0` 表示「取终端宽度 − 2」（argparse 行为）。结论是
**当前编译器能力下无法在 libs 层安全实现**，因此只记录证据并立项，不发布半可用代码。

- **实测链路**：在 `libs/os` 加 `terminal_columns`（`@[extern] fn ioctl(fd int,
  request u64, argument *void) int` + `winsize`），pty（24×40）下运行 yh 产物：
  - `nm -u` 确认导入真实 `_ioctl`；反汇编确认 `w0=1`、`w1=0x40087468`、`x2=栈上缓冲`；
  - 结果仍为 `rc=-1, errno=14`（EFAULT），即内核收到的指针是垃圾；
  - 同一 pty、同一请求号下用 C 调用（`ioctl(1, TIOCGWINSZ, &w)`）得到 `rc=0, 24×40`。
- **根因**：Darwin/arm64 的 C 变参实参必须走栈，而 yh 的 `@[extern]` 只支持定参
  （`libs/sys/30_file.darwin.yh` 开头已记录同一约束，`open/openat/fcntl` 因此只走
  prelude 的变参登记）。`ioctl` 是变参入口，定参声明把第三个实参放进 x2，libSystem
  却从栈上取 → EFAULT。Linux 侧同类声明按 AAPCS64 会读到 x2，但 x86_64 SysV 又要求
  变参调用设置 `al`，同样不能靠 libs 层保证。
- **处理**：删除实验性的 `libs/os/15_terminal.{linux,darwin}.yh`，`cli` 的
  `HelpFormat.width` 语义与默认值（80、0=不折行）保持原样；差异文档维持「帮助宽度
  缺省固定 80」这一条，并补上根因。自动宽度的落地路径记入
  [todo](todo.md) 的 CLI-G（需先在编译器后端提供非变参 shim）。
- **验证**：回退后 `cd libs && yh test` = **130 passed / 0 failed**；
  `--filter cli::` = 51 passed；`run.py` 5/5；`diff.py` 0 未知差异。

## 2026-10-27 cli 标准库去重与常量（复核 CLI-D）

- **构造器合并**：`option()`/`positional()` 两份 31 行逐字段初始化合并为
  `new_argument(name, positional)` + 两个薄包装（后者只差 `alias`、`positional`
  与默认 arity），`cli.yh` 少 ~45 行重复。
- **诊断码常量化**：新增 `cli.CODE_USAGE`/`CODE_CONFIG`/`CODE_RESOURCE`
  （取值 `usage_error`/`config_error`/`resource_error`），替换各文件里 122 处字面量；
  顺带把 8 处写成 `"resource"` 的内存失败诊断统一为 `resource_error`
  （此前 `Diagnostic.code` 在同类失败上取值不一致）。
- **参数文件上限常量化**：`parse_config()` 里的 `16`/`1048576` 改为新增的
  `MAX_FILE_DEPTH`/`MAX_FILE_BYTES`（与 `MAX_FILE_TOKENS`/`MAX_FILE_LINE` 同族）。
- **测试助手去重**：`zz_tests_help.yh` 的 `hp_contains`/`hp_index_of` 改为委托
  `string.contains`/`string.find`（新增 `import string`），删掉手写双循环 ~45 行。
- **用例**：新增「错误：诊断码常量与类别一致」——usage 错误码等于 `CODE_USAGE`、
  配置错误码等于 `CODE_CONFIG`；cli 内嵌测试 50 → **51**。
- **文档**：`libs/cli/README.md`（诊断码常量、容量表补两个上限、公开 API）、
  `docs/03-design/yh-cli标准库设计.md`（§14.3 错误码常量）。
- **验证**（种子 `bin/yh-darwin-arm64`）：`cd libs && yh test` = **130 passed /
  0 failed**；`--filter cli::` = 51 passed；`libs/cli/test/run.py` 5/5；
  `diff.py` = 91/94 一致、3 条已知差异、0 未知差异。

## 2026-10-27 cli 帮助拼接的越界兜底与去重（复核 CLI-B）

- **短路契约**：`help.yh` 的 23 个拼接函数（`put_text`/`put_char`/`put_int`/
  `put_spaces`/`put_hex_byte`/`put_escaped`/`put_color`/`put_color_end`/
  `put_value_text`/`put_choices_metavar`/`put_metavar_at`/`put_value_pattern`/
  `put_template`/`put_template_wrapped`/`put_wrapped`/`put_single_synopsis`/
  `put_mutex_synopsis`/`put_slot_names`/`put_slot_pattern`/`put_row_names`/
  `append_help_row`/`put_title`/`put_break`）开头统一 `if (at < 0) { return -1 }`：
  一旦越界，后续追加全部变成空操作。
- **修掉 3 处潜在越界**（`at=-1` 当下标继续写）：`put_escaped` 内 `put_hex_byte`
  后直接 `continue`；`layer.yh` 的建议文本三段串联；`ctx_add_warning` 的弃用警告前缀。
  现在这三处即使漏判也只会整段失败，不会踩内存。
- **删除 76 处重复判空**：仅保留「返回值参与算术」（`append_help_row` 的名称宽度、
  `build_usage_line` 等）与「用 `at` 写 NUL」（`build_help_text`/`build_usage_text`/
  `build_version_text`/消息构造）的检查；`help.yh` 1,844 → **1,685 行**，
  `if (at < 0)` 由 144 处降到 91 处。
- **溢出行为**：新增用例「帮助：文本溢出返回 resource_error」——`description` 与
  子命令 `help` 超过 `MAX_HELP` 时 `format_help` 返回 `resource_error` 且 `text`
  为空指针（此前该路径只会打印越界写后的垃圾内容）。
- **验证**（种子 `bin/yh-darwin-arm64`）：`cd libs && yh test` = **129 passed /
  0 failed**；`--filter cli::` = 50 passed；`libs/cli/test/run.py` 5/5；
  `diff.py` = 91/94 一致、3 条已知差异、0 未知差异。

## 2026-10-27 cli 库对齐 argparse：批次 3（诊断与建议）

四项诊断缺口对齐（对照 Python 3.14 argparse 的 `error()` 文案）：

- **choices 不匹配列候选**：`parse.yh` 的 `convert_tokens` 增加 `state` 参数，
  改用新增 `choices_message` 构造「选项 --mode 的值不在候选集合中（可选：fast, slow）」。
- **未知子命令列候选**：`layer.yh` 的 `dispatch_command` 改用 `subcommand_message`
  （「未知子命令 ad（可选：add, list）」），替代固定文案。
- **`suggest_on_error` 扩展到 choices 与子命令**：新增 `suggest_choice`/`suggest_command`
  （复用 `edit_distance`，阈值 2、取最优 1 个），文案追加「是否想用 X？」；
  未知选项的建议逻辑不变。
- **多余位置 token 全量列出**：新增 `put_extra_args`/`extra_args_message`
  （「多余的位置参数：b c」），`tail_layer` 与 intermixed 收集路径共用；
  超出 `MAX_HELP` 缓冲时退化为不加列表的短消息。
- **用例**：`zz_tests_help.yh` 新增「choices、子命令与多余 token 的诊断候选」
  （含 `suggest_on_error` 开/关两组断言）；cli 内嵌测试 48 → **49**。
- **文档**：`libs/cli/README.md`（§13 `suggest_on_error`、§14 诊断文案）、
  `docs/03-design/yh-cli标准库设计.md`（§14 诊断实现状态）、
  `docs/03-design/yh-cli与argparse差异.md`（新增 3 条一致项，测试数 49）。
- **验证**（种子 `bin/yh-darwin-arm64`）：`cd libs && yh test` = **128 passed /
  0 failed**；`--filter cli::` = 49 passed；`libs/cli/test/run.py` 5/5；
  `diff.py` = 91/94 一致、3 条已知差异、0 未知差异。

## 2026-10-27 cli 库对齐 argparse：批次 2（帮助/usage 展示）

六项展示缺口全部接通，均与 Python 3.14 argparse 的 `format_usage`/`format_help` 逐字对照：

- **choices 占位名**：`row_metavar` 之外新增 `put_metavar_at`/`put_choices_metavar`，
  缺省渲染 `{fast,slow}`（usage 与帮助列一致），显式 `metavar`/`metavars` 优先；
  real 候选没有格式化器，退回类型名（`FLOAT`）。
- **逐项占位名 `metavars`**：只对 `exactly(n)` 有效，freeze 校验「个数 = n」且不能与
  `metavar` 同时设置；`--pair LEFT RIGHT` 逐项展开。
- **数量模型占位名**：新增 `put_value_pattern`，按 argparse 的 `_format_args` 语义写
  `single` 一个、`exactly(n)` n 个、`*` → `[X [X ...]]`、`+` → `X [X ...]`、
  `remainder` → `...`（旧实现的 `...` 追加逻辑并入该函数）。
- **子命令槽**：`Subparsers.metavar` 新增字段（`slot_metavar` 落库），usage 写成
  `{add,list} ...`（旧为 `[COMMAND]`/`COMMAND`，无省略号）；`title`/`description`
  终于生效：帮助段用自定义标题、说明行、`{add,list}` 占位行，命令行缩进 4 并按
  `help_column` 对齐；显式 `metavar` 覆盖命令名列表。
- **`boolean_optional` usage**：写成 `[--cache | --no-cache]`（旧只写 `[--cache]`）。
- **`HelpFormat.max_help_column` 接通**：`help_column(state, fallback)` 统一取
  「显式值 > 段落默认（位置 22、其余 26）」，位置/选项/用户组/命令段全部改用它。
- **用例**：`zz_tests_help.yh` 新增「choices 占位名与槽标题/说明/占位名」「max_help_column
  与 boolean_optional usage」两组，旧 metavar 用例补 usage 断言；新增 `hp_line_column`
  助手量说明列。cli 内嵌测试 46 → **48**。
- **文档**：`libs/cli/README.md`（§5 metavars/choices、§6 usage 形态、§7 槽
  title/description/metavar 与 usage、§13 max_help_column/boolean_optional）、
  `docs/03-design/yh-cli标准库设计.md`（§10.1 Subparsers、§14.1 实现状态）、
  `docs/03-design/yh-cli与argparse差异.md`（新增 7 条一致项，补充「帮助宽度缺省」
  「说明列缺省」「choices 说明附录」三条保留差异）。
- **验证**（种子 `bin/yh-darwin-arm64`）：`cd libs && yh test` = **127 passed /
  0 failed**；`--filter cli::` = 48 passed；`libs/cli/test/run.py` 5/5；
  `diff.py` = 91/94 一致、3 条已知差异、0 未知差异。
- **未做**：帮助宽度仍固定 80（不读终端宽度）；诊断候选列表与 `suggest_on_error`
  的 choices/子命令覆盖留在批 3（todo CLI-F）。

## 2026-10-27 cli 库对齐 argparse：批次 1（语义正确性）

六项与 Python 3.14 argparse 实测对照后补齐/修正的行为：

- **`set_default` 未声明 dest 现在进结果**（argparse `set_defaults` 语义）：
  `apply_defaults` 新增覆盖项逆回写（`parse.yh`），设计 §8.3/§7 早已承诺「可为尚无
  参数的键设置业务标签」，但旧实现只遍历已声明 `rows`，实测 `contains=0`。
  新值 `provided=false`，不覆盖 `initial`。
- **位置 `optional()` 未取到值时用默认值**（argparse `nargs='?'`）：旧实现写入
  `const_value` 并计 `provided=1`；现不写 const、不计出现，交给默认值层级。
  实测 `opt='DEFAULT'`（对齐），不再是 `CONST`。
- **位置段为子命令槽预留 token**：整段 token ≥「全部位置参数最低需求 + 1」时为槽
  保留 1 个（argparse `PARSER` 语义）；`files='*'` + 槽下 `tool add` 得
  `files=[] cmd=add`（旧行为是 `files=['add']` 且不选命令），最低需求占满时不预留
  （`files='+'` + 槽，`tool go` 仍得 `files=[go]`）。设计 §10.1 早就写「保留槽…最低
  数量」，实现现在与契约一致。
- **`store_const`/`append_const` 缺 `const` 报 config_error**（argparse 在
  `add_argument` 报 ValueError）；`boolean_optional` 等零参数 action 不受影响。
- **位置参数设 `required=true` 报 config_error**（argparse ValueError）；
  必需性仍由 arity 决定。
- **默认值/常量不参与 choices 校验**（argparse 语义，choices 只约束命令行显式值）：
  `declared_value_ok` 只保留 validator；显式值仍受 choices 约束（同一测试覆盖）。
- **用例**：`zz_tests_actions.yh`（位置 `optional` 默认值 + 未声明 dest + choices
  默认值）、`zz_tests_commands.yh`（槽 token 预留，含 `one_or_more` 不预留的反例）、
  `zz_tests_extensions.yh`（缺 const / 位置 `required` / 带 const 正常写入）。
  cli 内嵌测试 43 → **46**。
- **文档**：`libs/cli/README.md`（§3 必需性与常量、§6 分配规则、§7 槽共存、§10 choices、
  §15 `set_default`、契约要点）、`docs/03-design/yh-cli标准库设计.md`（§8.1/8.2/8.3、
  §9.3、§10.1）、`docs/03-design/yh-cli与argparse差异.md`（§1 新增 6 条一致项与
  槽共存的保留差异、测试数 46）。
- **验证**（种子 `bin/yh-darwin-arm64`）：`cd libs && yh test` = **125 passed /
  0 failed**；`--filter cli::` = 46 passed；`libs/cli/test/run.py` 5/5；
  `diff.py` = 91/94 与 argparse 一致、3 条已知差异、0 未知差异；
  `tmp/cli-gap/` 探针对六项逐条与 Python 3.14.6 对照。

## 2026-10-27 cli 标准库死代码清理（复核 P1 项）

- **删除零调用函数**：`libs/cli/help.yh` 的 `text_visible_width`（31 行，帮助宽度已按
  字节近似，无调用者）；`libs/cli/schema.yh` 的 `action_takes_values`（8 行，0 调用，
  且漏了 `store_const`/`append_const`/`count`，与 `action_is_zero_value` 语义冲突）。
- **删除只写不读的私有字段**：`mutex_row.members`/`member_count`（互斥校验实际按
  `result_owner.appeared` 计数）、`child_row.slot`、`parser_state.command_name`
  （连带 `new_state` 的第三个参数与两处调用点）、`parser_state.owned_by_parent`
  （`destroy_state` 无条件递归子节点）、`arg_row.metavars_count`、
  `arg_row.choices_count`（5 个读点改为 `len(row.choices)`，与 `value_in_choices`
  既有写法一致）。
- **净变化**：`libs/cli` 生产代码 6,846 → 6,793 行（`cli.yh` 893→886、
  `help.yh` 1,474→1,443、`schema.yh` 1,057→1,045、`commands.yh` 319→316）；
  `git diff --stat` = 9 插入 / 62 删除。
- **未动**：`Argument.metavars`、`Subparsers.title|description`、
  `HelpFormat.max_help_column` 是「已公开但未接线」的**行为缺口**而非死代码，
  补实现与删 API 需先决策，已记入 [todo](todo.md) 的 CLI-A。
- **验证**（种子 `bin/yh-darwin-arm64`，哈希与 `bin/yh-darwin-arm64.sha256` 一致）：
  `cd libs && yh test` = **122 passed / 0 failed**；`--filter cli::` = 43 passed；
  `libs/cli/test/run.py` = 5/5；`libs/cli/test/diff.py` = 91/94 与 argparse 一致、
  3 条已知差异、0 未知差异。删除 `libs/tmp/yh-test` 后复跑一次，确认 `cli` 模块
  重新编译（而非命中旧缓存）后仍全绿。

## 2026-10-26 B2-3/B2-5：`mb_link` 阶段化（LinkPlan）与预算收口

- **`mb_link` 676 行 → 6 个阶段 + 一个 `LinkPlan`（`compiler/link/link_cache.yh`）**：
  一次链接的可变量全部进 `LinkPlan`（栈上，指针传给阶段）：入参、链接方式、
  链接器与 C 项目输入、计时、链接键、`link_tmp`/`link_manifest` 路径缓冲、
  argv 与三类路径行缓冲、`library_search_*`、`mod_tag` 暂存。
  阶段与行数：`mb_link_prepare` 60、`mb_link_objects` 167、`mb_link_key` 161、
  `mb_link_args` 148、`mb_link_libs` 96、`mb_link_exec` 52，编排函数
  `mb_link` 41 行。**20+ 处「4 连 free」错误分支收敛成一个
  `mb_link_release`**：阶段只返回 0/-1，不释放；`mb_link` 在任一步失败或成功
  收尾统一释放并把指针清零。
- **行为保持**：语句顺序与原函数逐行对应，只做「局部量 → 计划字段」的机械搬移；
  阶段返回码区分「缓存命中(1)/继续(0)/失败(-1)」，其余语义（argv 顺序、
  缓存键、manifest 内容、产物发布与校验）一字未改。
- **验证（在独立 worktree 上做，避免与本机并发会话的合并冲突）**：
  `just build` + `arch-check` 通过（`link` 3,531 → 3,657，新增 `LinkPlan` 结构）；
  `just test` 全绿（ANTLR + 语法 49/49 + 运行语料 122/122 + compiler 内嵌测试 +
  libs）；`tests/modules/build-check.py --backend llvm` **122/122**（暂存副本口径）。
  当时未在**隔离 worktree** 跑 `selfhost-native` 全门：共享 LLVM 闭包缓存已被
  另一分支的 `tools/llvm-darwin-host.py` 重新准备（bridge 哈希 3098a81f →
  a09fc268），隔离副本的闭包自检过不去。**归位后在主 worktree 补跑，双门全绿**：
  `just test` 0 失败；`just selfhost-native` 0 失败——候选两代固定点
  48 个产物逐字节一致、cc4 自解析 127 个源文件、项目验收 122/122、libs 测试全过。
- **B2-5 预算收口**：`max_function_lines` 700 → **360**（实测最大函数已是
  `lower/module_snapshot_lower_expr` 的 360，`mb_link_query_identity` 274、
  阶段函数 ≤167）；`max_link_lines` 3,657、`max_build_lines` 6,308、
  `max_g_call_sites` 0、`max_globals` 172 全部等于实测值。
- **并发提示**：本轮期间同一 worktree 上有另一会话把 B2-3 的工作区提交为
  `a14eb5d` 并合入了 `llvm-2`（`b7476aa`，CLI-R 重写 + `YH_BUILD_CACHE`）。
  本条目记录的 B2-3/B2-5 数字是在该合并后的树上实测的（16 模块 / 127 文件 /
  54,456 行，`main` 318、新增 `cmdline` 605）。

## 2026-10-26 B2-1/B2-2/B2-4：`proj` 收产物键、`link` 成模块、`module_build` 拆三

- **B2-1 产物路径与缓存键 → `proj/proj_40_art.yh`（526 行，16 函数）**：FNV 哈希
  （hash_init/fnv/hash_file/hash_hex）、目录布局（build_dir/sub_dir/
  default_binary_path + 路径预算常量）、模块键与文件名（mod_tag/asm_stem_base/
  asm_stems/module_obj_row）、接口路径（module_iface_*/module_ctiface_*）、open_out。
  这几个符号原本被发射簇与链接簇共用，是 B2-2 的硬前置。保持「纯计算」：
  不建目录、不调外部工具、不读 `BuildCtx`——会话后缀改成显式 `suffix` 参数，
  `default_binary_path` 不再借 build 的 `append_bytes_np`。
- **B2-2 链接簇 → `compiler/link/`（7 文件 3,531 行 + 新增 context.yh）**：
  `link_cache`/`link_inputs`/`darwin_link`/`process`/`clock.*` 从 build 迁出，
  `module build` → `module link`；`arch-check` 新增 `link: {gen, proj, backend}`
  （**不得 import build**，否则成环）。为解掉三处反向依赖，把落点放在下层：
  `pl_target_code_current` → `proj.target_code_current()`、
  `append_bytes_np` → `gen.append_np()`、本层计时从 `BuildCtx` 移进
  `link/context.yh`（`link.object_ns()/link.link_ns()/reset_timings()`，
  argv0 由 `mb_set_argv0` 转交 `link.set_argv0`）。`project_link.yh` 仍留 build
  （读 `toml_*` globals）。顺带修 `llvm_emit_single_file` 的形参 `link int`
  → `do_link`（与模块名冲突）与 testkit 的 `build.realpath` → `link.realpath`。
- **B2-4 `module_build` 拆三**：`module_build`（命令面与标准库装载 690）/
  `module_emit`（单模块发射流水线 711）/ `module_cache`（缓存身份与依赖表 414），
  同模块内搬家，无 import 变化。
- **实测**：模块 14 → **15**、文件 122 → 126、代码 53,714 → 53,854；
  `build` 10,289 → **6,348**（B2 的目标 ≈6,000 基本达成）、`link` 3,531、
  `proj` 775 → 1,318；依赖边 46 → 51；`gen.G()` 保持 0；模块级 `let` 169 → 172
  （`link` 三个会话量）。预算：`max_build_lines` 10,289→6,348、
  新增 `max_link_lines` 3,600、`max_proj_lines` 1,318、`max_globals` 172。
- **验证**（每一步都单独跑过双门）：`just test` 全绿；`just selfhost-native`
  全绿——候选固定点 45 个产物逐字节一致、cc4 自解析 126 个源文件、项目验收 122/122。
- **B2-3（`mb_link` 阶段化）未做**：676 行、20+ 处「4 连 free」错误分支，阶段间
  共享 30+ 局部量，属本轮风险最高的一项，需要单独一轮完整双门与产物逐字节对照；
  已在 [todo.md](todo.md) 立项并写明方案，B2-5（预算收口）随后。

## 2026-10-26 B1-3/B1-4：统计与会话状态独立，`gen.G()` 归零并关闭

- **B1-3 统计独立成 `gen.CompileStats`**：25 个计数（`enabled`/`front_cache`/
  `lex`/`syntax`/`index`/`pass1`/`globals`/`functions`/`ir_*`/`check_*`/
  `backend_*`/`asm`/`link`/`compiler_hashes`/`ir_cache_salt`/`firc_write_off`/
  `workers`）从 `GenState` 物理移出，读点统一 `gen.stats().<字段>`。
  **没有按方案搬进 `build`**：写入方主要在 gen/lex/parse（前端），搬进 build 会
  形成 build↔gen 双向耦合；独立结构 + 窄口已经达成「GenState 瘦身 + 读点归属」。
  `GenState` 因此只剩 `c_cfg` 指针与 `task`。
- **B1-3 `BuildCtx`**：新增 `compiler/build/build_ctx.yh`（按文件名序排最前），
  把编译器路径/指纹/接口后缀（5）、阶段计时（5）、调度观测（2）、`mb_dep_*`
  依赖表（9）共 21 个模块级 `let` 收进 `BuildCtx`，入口 `bc()`。模块级可变 `let`
  188 → **169**；`build` 自己的 `gen.G()` 13 → 0。
- **B1-4 关闭 `gen.G()`**：全仓 40 个「只读 `gs.task.*`」的函数改走 `gen.task()`
  （parse 21、testkit 12、check 3、cmd 5、ast 2、comptime 2、lex 1 …）；
  `parse/iface_ct_map` 的 4 个 helper 与 llvmlower fixture 的三个 helper 形参从
  `*gen.GenState` 收窄成 `*gen.TaskCtx`；`gen/buffer` 内部最后一处 `G()` 改
  `task()`。删除 `pub fn G()`，`GenState` 由 `pub struct` 降为模块私有。
  **跨模块只剩三条窄口**：`gen.task()` / `gen.stats()` / `proj.ctx()`+`proj.cfg()`。
- **门禁同步**：`max_g_call_sites` 49 → **0**（任何新增 `gen.G()` 立即红）、
  `max_globals` 190 → **169**、`max_build_lines` 10,265 → 10,289（`BuildCtx`
  结构体换掉 21 行 let 声明）。`arch-check` 的报告行在没有 `gen.G()` 时不再打印
  空括号。
- **迁移手法**：按「函数体 + 只读 `task`」两个条件做机械替换（有其它 `gs.` 读点的
  函数不动，留给下一刀），每刀后跑 `just build`；`gen.task()` 与 `gen.G().task`
  语义相同（同一个 `&g_state.task`），属零语义改动。
- **验证**：`just test` 全绿；`just selfhost-native` 全绿（cc3→cc4 固定点 42 个
  产物逐字节一致、cc4 自解析 122 个源文件、项目验收 122/122、libs 测试）。

## 2026-10-26 B1-2：目标/配置收进 `proj.Cfg`，`canon` 改显式出参

- **目标/编译期配置的存储归 `proj`，类型仍留在 `gen`**：新增 `gen.TargetCfg`
  （`target`/`host_target`/`target_explicit`/`dialect`/`opt_level`/`emit_kind`/
  `emit_text_path`/`module_mode`/`is_entry_mod`），`GenState` 删掉这 9 个字段只留
  `c_cfg` 指针，实体在 `proj.ProjectCtx.cfg`（`proj.cfg()`）；driver 在
  `proj.init()` 后 `gen.bind_cfg(proj.cfg())` 绑定，`gen` 内部读点改 `cfg().<字段>`。
  **为什么不按方案 §2.3 直接搬给 `proj`**：`gen` 自己也在读这些字段（`gen/target.yh`
  `c_dialect` 3 处、`c_module_mode` 3、`c_host_target` 2、`c_target` 3 等），而 `gen`
  是 `proj` 的下层。指针绑定让「`proj` 唯一持有 + `gen` 只读指针」两全。
- **未绑定调用方的兼容路径**：`compiler/` 的 `test` 块与 `tests/` 的 fixture 直接
  `import gen`，不会走 driver。`gen` 保一个模块私有回退实例，`state_init()` **只在
  未绑定时**重置它（绑定后绝不重置，否则会抹掉 `--target`/`-O2`）；默认值只有一份
  实现 `gen.target_cfg_defaults`，`proj.init()` 也调它。
- **`canon` 取消隐式出参**：`proj.canon(base_off, base_len, rel, out_off, out_len)`，
  `ProjectCtx` 删除 `canon_off`/`canon_len`。原先这对字段既是 `canon` 的结果、又被
  `mb_mod_tag` 当模块标签暂存（两个含义共用一个全局槽，症状是路径串位而不崩）。
  现在每个用到路径暂存的函数持有自己的局部 `c_off`/`c_len`；跨函数返回值改出参：
  `mb_build_dir(..., out_len)`、`pj_find_root(..., out_len)`、
  `pj_c_path(..., out_off, out_len)`。
- **迁移中抓到一处真实的隐式依赖**：`pj_load_c_config` 依赖 `pj_c_path` 写全局游标
  再读它（`let path_off int = c_off`）——改成局部后 C 源路径变空，
  `clang: error: no input files`。按「谁产生谁出参」改成 `pj_c_path` 返回路径（这正是
  B1-2 要消灭的形态），并用脚本扫出「读 `c_off/c_len` 但自己既不调 `canon` 也不调
  `mb_mod_tag`」的函数确认只剩这一处。
- **实测**：`gen.G()` 115 → **98**（build 66 → 50）；`proj` 762 → 775、`gen` 5538 →
  5584（`TargetCfg` + 默认值实现）、`main` 383 → 387（绑定两行）、`testkit` 1578 →
  1585；模块级可变 `let` 187 → 188（回退实例）。预算按实测调整：`max_g_call_sites`
  115→98、`max_build_lines` 10236→10265、`max_file_lines` 2236→2261、
  `max_testkit_lines` 1578→1585、`max_module_lines` 383→387。**这些上浮是显式状态
  的代价，B2 拆 `build` 后必须回落**。
- **测试**：`astcheck`/`llvmfront`/`llvmtarget`/`llvmlower`/`llvmchecked` 五个 fixture
  补 `proj.init()` + `gen.bind_cfg(proj.cfg())` 与 `import proj`；`build-check` 的
  `llvmtarget`/`llvmfront` 拷贝清单加 `proj`。
- **验证**：`just test` 全绿；`just selfhost-native` 全绿（cc3→cc4 固定点 42 个产物
  逐字节一致、cc4 自解析、项目验收 122/122、libs 测试）。

## 2026-10-26 B1-1：项目模型迁入 `proj` 模块（build 拆分第一台阶）

- **按 [构建态对象化与 build 拆分重新规划](../02-plan/yh-构建态对象化与build拆分重新规划-2026-10-25.md)
  §3.1 的 P1 落地**：新增数据层模块 `compiler/proj/`（3 文件 762 行）：
  `proj_00_model.yh`（7 个表类型 `PFile/PMod/PProj/PDep/PInput/PLinkItem/PLinkGroup`
  + `ProjectCtx` + `proj.ctx()`/`proj.init()`）、`proj_10_table.yh`（唯一写者
  `proj.add_project/add_module/add_project_module/add_module_file/add_file/add_import`
  + 只读 `module_in_project`/`find_project_root`）、`proj_20_path.yh`
  （`canon/pool_str/env_fetch/file_exists/set_root_project/is_root_project/diag`
  + 前端窄口 `file/file_count/test_file_selected`）。
- **`gen` 不再拥有项目模型**：`GenState` 删掉 22 个表字段（三张表 + 11 条导入平行
  数组 + `p_stdlib`/`p_state`）与 6 个测试/扫描字段，`p_file/p_file_count/
  test_file_selected` 三个窄口移出（gen 是 proj 的下层，不能反向依赖）；
  `gen/state.yh` 5686 → 5538 行。`build/project_state.yh`（574 行）整文件删除，
  `pj_dir_add` 并入 `build/project.yh`，`build.PjState` 被 `ProjectCtx` 取代。
- **迁移是机械的、可审计的**：一次性脚本按「局部名 `proj` → `pj`（避免遮蔽新模块名）
  → `gs.p_*`/`gen.G().p_*` 读点 → `pj_state()` → 函数前缀 → `gen.P*` 类型前缀 →
  补 `import proj`」七步跑 30 个文件，再删掉 36 处因此变空的
  `let gs *gen.GenState = gen.G()`。**没有留下任何影子字段或转发壳**。
- **实测**（`python3 tools/arch-check.py`）：模块 13 → **14**、文件 119 → 121、
  代码 53,529 → 53,580；`build` 10,807 → **10,242**、`gen` 5,686 → 5,538、
  `proj` 762；`gen.G()` 165 → **115**（build 101 → 66、testkit 27 → 12，
  parse/main 未动）；最大文件 2,241 → 2,236。
- **`arch-check` 口径**：`ALLOWED` 新增 `proj: {gen}`（前端/构建共用数据层，
  反向依赖即成环），`ast/check/parse/lower/build/testkit/main` 各加 `proj` 边；
  `comptime` 也加了 `proj`——唯一读点是 `ct_layout_array_expr` 的文件下标越界检查，
  走 `proj.file_count()` 而不是自己拿表（与方案 §2.2 的 `comptime:{gen}` 差一条边，
  已在 ALLOWED 注释里写明理由）。预算按实测收紧：`max_build_lines` 10,807 →
  10,242、`max_testkit_lines` 1,592 → 1,578、`max_file_lines` 2,242 → 2,236、
  `max_g_call_sites` 165 → 115，新增 `max_proj_lines` 800；`max_module_lines`
  381 → 383（driver 多了 `import proj` 与 `proj.init()` 各一行）。
- **测试**：`tests/modules/projects/astcheck/main/main.yh` 改用 `proj.PFile` +
  `proj.ctx().files`，并新增窄口断言（`proj.file_count()==1 && proj.file(0)==&files[0]`）；
  `tests/modules/build-check.py` 的 `astcheck`/`llvmchecked`/`llvmlower` 三个 fixture
  拷贝清单各加 `proj` 模块；`llvmchecked`/`llvmlower` fixture 的 `gs.p_files`
  改写为 `proj.ctx().files`。
- **验证**：`just test`（ANTLR + 语法 + 运行语料 122/122）全绿；
  `just selfhost-native` 全绿——候选两代模块固定点（cc3→cc4，42 个产物）逐字节一致、
  cc4 自解析 121 个源文件 OK、固定点探针 OK、项目验收 **122/122**、libs 测试全过。
- **环境注意（下次跑门先看）**：本机 `$TMPDIR/yh-fast` 被同机多个 worktree
  （`x`/`ratfish`/`llvm-*`）共用，`stage-yh` 会互相覆写 `yh` 副本，导致自举后续门
  （lex-stats/cache/build-check）读到**别的分支的编译器**。并发时用私有目录：
  `just FAST_DIR="$TMPDIR/yh-fast-b11" selfhost-native`。另：`FAST_STAGE=0` 时
  `lex-stats` 会因仓库根 `yh` 能发现 `libs/` 标准库而多扫 101 个文件（期望 6 的用例
  按「暂存副本」口径写的），该差异在 B1-1 之前的 HEAD 上同样存在，不是本次回归。

## 2026-10-26 CI 去掉 ANTLR：参考语法门只在本地开发跑

- **改动**：`.gitea/workflows/ci.yml` 删除 `antlr` job（原为 Apple container 内
  `apt-get install default-jre-headless` + `tools/run-antlr-ci.sh`，每次 push 起
  一个 ubuntu:24.04 容器装 Java + pip + curl 下载 jar），分支门只剩
  `darwin-arm64` / `linux-arm64` / `linux-x86_64` 三个平台 job；ANTLR 参考语法门
  仅保留在本地 `just test` / `just quick`（`tests/yh/check.py` 默认模式）。
- **连带清理**：删除只为该 job 存在的 `tools/run-antlr-ci.sh`；
  `.circleci/config.yml`（云端真机参照，非门禁）同步删除 `antlr` job 与 workflow
  条目，避免引用已删脚本。
- **文档**：`AGENTS.md` 的 CI 说明改为"三端并行 + ANTLR 只本地跑"；
  `docs/02-plan/yh-基础设施即代码IaC方案-2026-10-24.md` 的 G3 缺口收敛为"只剩
  镜像非内容寻址"（ci.yml job 数 4 → 3）；`docs/03-design/yh-架构图-2026-10-25.md`
  的 CI 节点去掉 ANTLR。
- **理由**（2026-10-26 用户决定）：参考语法门与平台无关，平台 job 本来就只看
  编译器的 `--syntax-check` 模式；为它单独起容器装 Java + 现场 `curl` jar 属
  不可复现的 CI 成本，收回到本地开发更划算。
- **验证**：Ruby `YAML.safe_load` 解析 `ci.yml`（3 job：`darwin-arm64`/
  `linux-arm64`/`linux-x86_64`）与 `.circleci/config.yml`（workflow 只引用现存
  job）通过；除本条记录外，仓库内不再引用 `tools/run-antlr-ci.sh`；本地
  `just test` 路径未改动（`tests/yh/check.py` 默认 ANTLR 模式仍在）。

## 2026-10-26 构建入口迁 just：justfile 成为唯一真源，Makefile 收成转发层

- **改动**：新增仓库根 `justfile`（just 1.59 / 1.21 均解析通过），承载旧
  Makefile 的全部目标，覆盖验证通过后**删除 `Makefile`**（just 成为唯一构建
  入口）。迁移期间用 23 行转发层（`make <目标> [VAR=值]` →
  `just <目标> [VAR=值]`，变量经 `MAKEOVERRIDES` 前置）过渡。
  `.gitea/ci/Dockerfile` 预装 `just`（Ubuntu 24.04 apt 包 1.21.0）；
  `.gitea/workflows/{ci,release}.yml`、`.circleci/config.yml`（云端真机参照）
  与 `tests/{toml,fmt,string}/install.py` 的 `make …` 全部改调 `just`
  （变量覆盖统一写在目标名之前）。
- **覆盖验证**：`git show HEAD:Makefile` 的 43 个目标与 justfile 逐项比对——
  `test-json`（工作区已随 `tests/json/run.py` 删除）与 `tmp/llvm-migration`
  （内部 order-only 目标，由 `_prepare` 承担）不需要；其余全部有等价 recipe，
  `build`/`default`/`libs-test`/`libs-test-o2`/`test-num` 为新增入口。
  selfhost-native、test-llvm-darwin、install、seed、stage-yh、llvm-host 等
  行数不同的目标逐条核对（含 libs 全跑 vs 分库、Darwin SDK 安装、
  `compiler/.build` 过期判定）。
- **等价性**：目标名、变量名（`SEED`/`SEED_DEST`/`SKIP_CORPUS`/
  `SELFHOST_KEEP`/`SELFHOST_WORKDIR`/`FAST_STAGE`/`YH_LLVM_HOST`/
  `YH_LLVM_CACHE`/`LLVM_JOBS`/`LLVM_TARGET`/`LLVM_SEED`/`PREFIX`/`DESTDIR`/
  `INSTALL`）、平台分支（种子/LLVM 宿主/专项门/缓存门）与旧 Makefile 一一
  对应；`just`/`just build`/`just dev` 对应旧默认目标/冷编/增量，默认目标按
  源码 mtime 判断（只看 `compiler/*.yh`、`compiler/*/*.yh`、`compiler/llvm`、
  清单与四个构建脚本，不递归 `compiler/tmp` 与 `compiler/.build`）。
- **迁移中发现并修掉的两处 just 语义坑**：
  1. 命令行变量覆盖必须写在 recipe 名之前（`just SEED=… build`），反序会报
     ``does not contain recipe``；`_ensure_built` 与 Makefile 转发层都按此顺序。
  2. `install` 原本是 `@cd libs && find …` 单行、后续 Darwin SDK 安装仍在仓库
     根执行；just 脚本里 `cd` 会残留，改为子 shell 内切换后 Darwin SDK 路径
     才能解析（`just test-toml-install` 从失败转为通过）。
- **验证**（删除 Makefile 后复跑）：`just build`（冷编，内嵌 LLVM 桥接入）、
  `just test`（三层回归全绿，含 libs 与 arch-check）、
  `just selfhost-native`（主门，项目语料 122/122）、`just quick`、
  `just test-toml-install` / `just test-fmt-install`（install 验收脚本改用
  `just DESTDIR=… PREFIX=/usr install` 后验证安装树与仓库外导入）全部通过；
  CI 三份 YAML 经 ruby 解析无语法错误；just 1.24.0 与 Ubuntu 24.04 的
  1.21.0 均可解析 justfile。
- **已知限制**：同机并行跑两个 make/just 门会共享 `compiler/.build`（自举脚本
  `native-selfhost.py` 的 `build()` 明确用仓库 `compiler/.build`），互相打断
  模块编译；本次验证期间两次与并发会话互踩，最终串行跑通。旧 Makefile 同样
  有此约束。

## 2026-10-26 LA3 构建卡死：check 切片字符串段死循环

- **症状**：工作树 `yh` 对任何项目构建都不返回（hello world 3 行 >120 s、LA3
  fixture >300 s），`tests/selfhost/llvm-function-cache.py` 因此表现为「一直不
  结束」；同机 10-24 种子跑同一构建 0.79 s。
- **根因**：`compiler/ast/module_snapshot_check_slice.yh` 的 v3 字符串段编码
  循环（`// 字符串段（v3）` 之后）没有 `i += 1`，命中前的 `continue` 也不推进
  `i`：`data_str_lookup` 未命中（无字符串字面量的表达式，最常见）走
  `continue`，命中走循环尾，两条路径都不自增 → 每模块首个函数永久自旋。
  插桩实测：单次 capture 为 `fi=0, expr_n=1, store.expression_n=1`，`i` 恒 0、
  `cursor` 恒 601，15 s 内 350 万次迭代；`sample`/`lldb` 显示 worker 时间全部
  落在 `mb_llvm_emit_module → checked_check_cache_capture →
  checked_slice_capture` 的 112 B `AstExpr` 拷贝（`_memmove`）。
- **修复**：两处补 `i += 1`（`continue` 前、循环尾）。回归覆盖沿用既有
  `tests/modules/projects/llvmfunctioncache` + LA3 脚本：该路径挂起即失败。
- **验证**：`rm yh && make` 冷编 96.8 s；fixture 冷编 O0 2.18 s / O2 0.97 s；
  `python3 tests/selfhost/llvm-function-cache.py --compiler-path ./yh` 7.8 s
  （此前无限）；`just test` 依次通过语法语料、运行语料、modules、
  libs、compiler-tests、fmt、code-stats，止于 arch-check。
- **本轮未关闭**：
  1. LA3 `损坏记录` 断言 `check hits/misses/skipped` 期望 `(4,1,4)`、实际
     `(5,0,5)`：种子下 `index` 与 `index.check` 的键**完全相同**，当前 v3 下
     两套键**完全不相交**（各 4 条）。脚本按 `index`（IR 键）写
     `<key>.fchk` 只会造出孤儿文件，真正的 check 记录未被损坏；要么让 check
     键回到与 IR 键一致，要么脚本改从 `index.check` 取受害键。
  2. arch-check 超预算：`build` 10736 > 10730（在飞改动给 build 增加 25 行），
     与本次修复无关。

## 2026-10-26 两项待决策收口（用户决定）

- **NP 定位**：只保留 **NP3**（受检契约与 lowering 解耦），NP0/NP1/NP2/NP4/NP5
  关闭。依据：NP1/NP2 的对象代码（`ir_simplify`、`ssa_inline`）已随 A0b/A0e 从
  `compiler/` 删除，NP4 由 ADR-0014 取代，NP0 的模式/计数口径并入现有
  `just test` + O0/O2 + 自举门，NP5 交 LLVM 默认管线。
  [ADR-0011](adr/0011-yh采用Nanopass风格优化阶段契约.md) 状态改为「部分被
  ADR-0014 取代（2026-10-26），只保留 NP3」并附阶段处置表；
  [方案](02-plan/yh-Nanopass风格优化架构实施方案.md) 与
  [设计](03-design/yh-Nanopass风格优化架构.md) 头注改为只执行 NP3、其余章节
  仅作历史设计；NP3 以单条任务记入 [todo](todo.md) 的架构优化小节。
- **字面量只读化（H1）**：决定改语义——字面量发 `constant` 进只读段，能静态
  判定的写入改编译期诊断（先覆盖字面量直接下标与不经函数边界的局部别名），与
  comptime 的「字面量字节池只读」口径统一；逃逸写入退化为运行期崩溃。
  决策前实测：运行期写入现在**允许且生效**（`let p *char = "abc"; p[0]='z'`
  → `zbc`），`tests/yh-run` 无运行期依赖用例；`backend/llvm_module.yh:385` 已按
  `mutable` 选 `global`/`constant`，字面量登记点在
  `lower/module_snapshot_static.yh`；`__data` 实测 hello-world 14 B、`./yh`
  93 KB。实施项见 todo H1，与 PC3b 一起滚种子。
- 本轮只改文档，未改编译器、未构建、未滚种子。

## 2026-10-26 修复编译器浮点字面量的 1 ULP 偏差

- **根因**：`compiler/gen/sem_value.yh` 的 `sem_parse_float_bits` 用「逐位
  `mant*10 + digit`、`frac_scale*10`、指数累乘」的浮点运算解析十进制字面量，
  大指数（`1.5e300`）经多次舍入后比正确值多 1 ULP（bits …870 vs …869）。
  num 库自己的解析与 Python 都是 …869，此前只有编译器字面量路径错。
- **修复**：字面量去掉 `_` 后交给宿主 libc 的 `strtod`（glibc/macOS 均按
  当前舍入模式正确舍入），保持 `-0.0`、次正规、上溢为 inf 等既有行为；
  `@[extern] fn strtod` 声明在 `gen/sem_value.yh`，并在注释里记录 E1 迁移时
  需替换为纯 yh 实现（已加 todo E1.3）。
- **回归**：新增 `tests/yh-run/run/float-literal-rounding.yh`，覆盖 1.5e300、
  0.1、最大有限数、最小次正规、-0.0、1e309、下划线分隔、下溢到 0、
  2^53+1 等 13 个位模式，期望值与 Python `struct` 一致。
- **验证**：`just build` 23.4s；`just test` exit 0（run 语料含新用例）；
  `just libs-test` 122 + cli/os/libc；`just libs-test-o2` 122；
  `just test-num` 220/220；`just selfhost-native` exit 0（cc3→cc4 固定点、
  cc4 自解析 119 文件、project cases 122/122）；`git diff --check` 通过。
  注：仓库入口此时已完全迁移到 justfile（Makefile 已删除）。

## 2026-10-26 RB1（worker 父死子退）+ PF0/PF1（冻结语料与基线工具）

- **RB1**：`module_worker` 在 fork 后记录父 pid（`mb_worker_parent_set`），并在函数入口与
  整模块发射前检查 `getppid()`（`mb_worker_parent_alive`），父进程不在即退出。
  实测：构建到 0.6 s 时 `kill -9` 父进程，4 个在跑的 worker **2.2 s 内全部退出**；此前
  中断的构建会留下 `ppid=1` 的孤儿继续烧 CPU（曾把 load 推到 195 并连带卡死其它门禁）。
  预算：`max_build_lines` 10786 → 10807（RB1 +19，含 `getppid` extern）。
- **PF0/PF1**：新增 `tools/perf-baseline.py`，把 `compiler/` 复制成冻结语料并记录清单
  SHA-256，跑冷编 / 全量重编（含写缓存）/ 热编 / 单函数改动四个场景，逐轮记录墙钟、
  父进程阶段耗时、load1、IR/check 命中与 `.fir` 写入量，写 `tmp/perf/<run-id>/{raw.json,report.md}`；
  `--ab PATH` 支持 A/B 成对交错与变化率。
  首份基线（load≈4–5，3 轮）：冷编 **10.3 s**（schedule 8.2 + object 0.5 + link 1.1）、
  全量重编 **16.1 s**、热编 **0.98 s**、单函数改动 **3.59 s**（IR 204 / check 38 命中）。
- 均未改编译器语义；`just test` / `just selfhost-native` / `arch-check` 复跑全绿。

## 2026-10-26 PC3b：滚种子（冷编 23.0 s → 11.0 s）

- **前置**：`just arch-check` / `just test`（0 FAIL）/ `just selfhost-native`（122/122、LA3 O0/O2）/
  `just test-llvm-darwin` 全绿；`verify-seed` 通过；`strings yh` 无构建机 `$HOME` 路径。
- **结果**：`bin/yh-darwin-arm64`
  旧 `56bf3f56027fb7609c8f37c384c0f3b8e07314f50618f2cf093274583ca6ceb8`
  → 新 **`ea24f6591abc945584e63adea8e30d72b1ef3185c9de1d2758124c63a95d652b`**（70,402,800 字节），
  哈希文件同步写入。
- **滚后实测（load≈2.9）**：`just build`（新种子冷编 13 模块）**11.04 s**，
  滚前同一操作 23.0 s → **−52%**；冷编写入的函数缓存记录 `.fir` = **0**（PC3 生效）。
- **滚后门禁**：`just test` 0 FAIL；`just selfhost-native` 122/122 + LA3 O0/O2 + 两代固定点（39 产物）
  + 自解析全通过。
- 顺带修（迁移 bug）：`_prepare` 是 `[private]` 且排在文件最前，`just` 的「第一个 recipe」规则
  让**裸 `just` 只跑 `_prepare`（空操作）**——`yh` 不存在时也不重建（实测 0.12 s、0 模块）。
  把 `default` / `all` 移到 `_prepare` 之前后，裸 `just` 恢复「源比 yh 新时冷编」（实测 11.40 s、13 模块）。
- **RB1 之后再次滚动**（同一轮内）：`ea24f659…` → **`e52d208ccd03a96044e4c93d2c74d8913bfdec9fcf10c41ecb12348baa784e70`**，使种子与「带 worker 父存活检查」的当前源码一致；门禁在同一源码上已全绿。
- 说明：种子不入库（`bin/` 由 `just fetch-seed` 获取），本次滚动只影响本机 `bin/`，哈希文件供校验。

## 2026-10-26 just 迁移后的门禁复核（+ 修 Darwin/ARM64 守卫）

构建入口已由并行会话从 Makefile 迁到 **justfile**（`830d1d5`），本轮性能工作的门禁证据
需要在新入口下重跑：

- `just arch-check` 0.42 s ✅（预算 10786，未再增长）
- `just test` **0 FAIL** ✅
- `just selfhost-native` ✅（项目用例 **122/122**、LA3 缓存矩阵 O0/O2、两代固定点、自解析；
  用例数 124 → 122 是同期 YT4 迁移删掉旧夹具所致）
- `just test-llvm-darwin` ✅ —— **先修了迁移 bug**：`just` 的 `arch()` 在 macOS 返回
  `aarch64`，而该门与 `selfhost-llvm-darwin` 的守卫拿它与 `arm64` 比较，在 Darwin/ARM64
  上直接报「要求 Darwin/ARM64」拒绝执行；改用已归一化的 `seed_arch`（2 处）。

同轮把 `docs/finish.md` 本轮条目、`docs/todo.md` 的 PC 条目、分析文档 §14 里的命令从
`make …` 同步为 `just …`（历史条目保持原样），并立项 RB1（worker 父死子退）、
RB2（门禁校验 staged 二进制新鲜度），修掉 RB3、复核 RB4。

## 2026-10-26 PC7a：大二进制改用 (size, mtime_ns) 身份哈希

- **动机**：探针测得每轮构建重哈希 **271 MB**（352–401 次调用），其中大头是几十 MB 级的
  二进制（编译器自身 70 MB、链接器/驱动），而 `link-libs.manifest` 对归档的摘要缓存本来是
  命中的。
- **改动**：新增 `mb_mix_file_identity`（`link_inputs.yh`），把「编译器指纹」与「链接工具身份」
  两处从**内容哈希**改成 **(size, mtime_ns)**（仍混入解析路径）。
- **语义**：这两处只需要「文件换没换」的身份，不需要内容摘要。代价是 make/ninja 级的
  mtime 信任——同内容不同 mtime 只会多失效一次缓存；工具/编译器被替换时 mtime 变化
  必然失效。
- **实测（load≈4.0）**：热编 **1.14–1.21 s → 1.00–1.02 s**（其中 schedule 0.27 → 0.03 s，
  因为不再哈希 70 MB 的编译器自身）；单函数改动 **3.83–4.45（中位 3.9）→ 3.71–3.81
  （中位 3.76）**，object 阶段 0.87 → 0.52 s。
- **未动的部分**：`link-libs.manifest` 的归档摘要缓存本来就有效；剩余 ~0.5 s 是模块级
  `.o` 与 lld 的固定成本，属 PC7（函数级目标文件）范围。
- **预算**：`max_build_lines` 10761 → 10786（PC7a 共享 helper 与两处调用 +25）。
- **门禁**：`just test`、`just selfhost-native`（124/124、LA3 O0/O2）、`just test-llvm-darwin`、
  `arch-check` 全绿。

## 2026-10-26 性能目标收口（A3 + B，滚种子推迟）

- **低负载基线（load≈4.5，`compiler/`）**：冷编 11.2–12.0 s、**全量重编（含写缓存）17.5 s**、
  **热编 1.14–1.21 s**、单函数改动 3.83–4.45 s（中位 3.9）、冷编后首次改动 4.78 s。
- **达标**：全量重编 ≤20 s ✅、热编 ≤1.5 s ✅（PC4b/PC5 按目标数字关闭）。
- **目标重定（A3）**：单函数改动目标由 ≤3 s 改为 **≤4 s（现状满足）**。理由：模块重编
  2.03 s 里 LLVM 每轮要为**整模块 205 个函数**重发 `.o`，链接 1.17 s 因 object 变必须
  重跑；≤3 s 只能靠**函数级目标文件**，已单独立项 PC7（可行性见
  [设计](03-design/yh-函数级目标文件可行性-2026-10-26.md)）。
- **PC3c 按实测关闭**：冷编后首次改动只贵 0.5 s（4.78 vs 4.27），check 切片仍命中
  38/205；为 0.5 s 引入「冷编后台补写」会重新引入孤儿进程/竞态，判定不做。
- **顺带量化（PC7a 立项）**：每轮构建**重哈希 271 MB**（352–401 次调用，含 70 MB 级
  二进制），关掉后热编 1.14 → 0.25 s。按 (size, mtime_ns) 复用摘要可省 ~0.4 s，
  但与 PC7 独立，需先决定是否接受 make/ninja 级 mtime 信任。
- **滚种子（PC3b）推迟**：三套门禁绿，但工作区有并行会话未提交改动
  （libs/json、testkit、.gitea、tests/toml），现在滚会一并烘进种子；等其落地后由用户确认。
- **门禁**：`just test`、`just selfhost-native`（124/124、LA3 O0/O2）、`just test-llvm-darwin`、
  `arch-check` 全绿（本轮仅文档改动，未再动 `compiler/`）。

## 2026-10-26 PC2 v3：check 切片复用恢复（并修掉一个自旋死循环）

- **根因（2026-10-25 定位）**：切片格式 v2 只带 expr/stmt/edge/binding/symbol 行，
  不带 `store.strings`，命中后 lowering 报「字符串缺少受检字节」；且 v2 的记录会
  让类型表随命中变化，编号漂移。
- **v3 设计**：头 +2 字（字符串计数/字节数）+ 尾部字符串段（label/length/quoted +
  字节本体，取自本函数 expr 行的 `const_bits` 数据标签）；pass2b 入口快照
  「类型数/字符串数/静态数据数」，capture **只缓存没有新建类型与静态数据的函数**
  ——命中因此不会改变类型编号，字符串由 `gen.data_str_restore` 按 label 恢复。
  `module_worker` 恢复 `firc_check_load`；`firc_commit_kind` 按旧索引回收旧键记录。
- **实测**：编译器自编增量 `gen` 模块 check 命中 **38/205**（此前恒为 0）；带字符串的
  函数命中后 `yh run` 输出正确；`.fchk` 记录 1209 → **373**（不可缓存的函数不写）。
  `llvm-function-cache.py` O0/O2 矩阵（IR + check 双计数）通过。
- **踩坑（当天修掉）**：字符串段的**计数循环**与**发射循环**用了不同谓词（发射侧漏了
  `soff/slen` 越界判断），越界条目只多写字节 → 堆破坏 → 内层 `for` 拿到垃圾长度 →
  无限自旋。表现是机器上 5 个 `ppid=1` 的 `yh build` 各烧 25–42% CPU、load 195，
  并行会话的门禁（用旧的 staged 二进制）也一起卡死。`sample` 直接指到
  `checked_slice_capture`。修复：两个循环共用同一谓词。教训：同一份数据的「算尺寸」
  与「写字节」必须共用条件，否则先溢出再自旋，日志上什么都看不到。
- **门禁**：`just test`、`just selfhost-native`（项目用例 **124/124**、LA3 O0/O2、
  两代固定点）、`just test-llvm-darwin`、`arch-check` 全绿。
- **预算**：`max_build_lines` 10736 → 10761（PC2 v3 装载 +5、PC2b 回收 +20），
  原因即本条。

## 2026-10-26 PC1b：IR 类型按内容去重

- **定位**：PC1 把「同一 ABI 多个类型编号」归因到 `gen.ty_push`，实测不成立——
  受检类型表结构重复 `cdup=0`（`ty_ptr/ty_array/ty_slice/ty_fn_abi` 已有去重）。
  重复在 IR 层：`ir_module_add_type` 无条件追加，`compiler/build` 的 **907 个 IR 类型
  里 706 个是同内容重复**（数组/指针/切片/函数类型每个函数都再登记一次）。
- **修复**：`ir/ssa_module_10_build.yh` 新增 `ir_module_type_same`（种类/bits/size/
  align/elem/count/字段(type_id,offset)/abi/变参），`ir_module_add_type` 命中既有
  内容时直接返回旧编号（名义名单独比较，保证两个同布局 struct 不合并）。
- **效果**：模块 IR 类型数 907 → **118**（最大模块），结构重复 706 → **0–1**；
  函数缓存合并的结构回退（PC1 的临时绕过）计数 **0**；命中率不变
  （`gen` 201/201、`build` 268/268，`ir_functions` 数随并行改动略变）。
- **测试**：`tests/modules/projects/llvmmodule` 新增三条断言（同内容合并、布局不同
  另起编号、名义名不同不合并），`llvm-module-ownership` 用例通过；
  `llvm-function-cache.py` O0/O2 矩阵通过；`just test` 73 s 绿。
- 说明：IR 层去重是纯收益（类型表更小、编号可比），不改变序列化/合并格式。

