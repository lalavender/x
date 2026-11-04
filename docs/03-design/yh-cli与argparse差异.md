# yh cli 与 Python argparse 差异

日期：2026-10-19。参照基线：[Python 3.14 argparse 官方文档](https://docs.python.org/3.14/library/argparse.html)。
本文只记录**可观察差异**与保留理由；逐项能力对应见
[cli 设计](yh-cli标准库设计.md) 第 3 节，实现状态见
[实施方案](../02-plan/yh-cli标准库实施方案.md)。

对照实验用本机 `python3 -V`（3.14 系列）实跑，yh 侧用
`tests/modules/projects/*` 的验收项目实跑；两边都在相同 argv 下比较
「值形状 / 诊断类别 / 退出码」。

## 1. 一致的子集（实跑一致）

| 输入 | argparse 结果 | yh 结果 |
| --- | --- | --- |
| `--output=a in.txt` | `output='a'` | 同名 text 值 |
| `-vvv in.txt` | `verbose=3` | `count` 累加到 3 |
| 空输入（缺必需位置参数） | 退出码 2 | usage_error，退出码 2 |
| `--cache --no-cache` | `cache=False`（最后者胜） | `boolean_optional` 同一语义 |
| `--pair a b`（`nargs=2`） | `pair=['a','b']` | `exactly(2)` 列表 |
| `-12`（位置 `type=int`） | `value=-12` | 负数特判后按位置值转换 |
| `a --level 2 b`（intermixed） | `files=['a','b']` | `parse_intermixed` 同为两元素 |
| `@args.txt`（开启 fromfile 前缀） | 文件展开为 token | `@file` 展开为 token |
| `@args.txt`（未开启 fromfile） | 仍是普通位置值 | 同（不展开） |
| `--tries`（count，默认 3） | `tries=4` | 同（从默认值累计） |
| `--rest a -x -- --help`（option remainder） | 全部为数据 | 同 |
| `--version`，模板 `%(prog)s 1.0` | `diff 1.0` | 同 |
| 自定义 usage `%(prog)s [options] src` | `usage: diff [options] src` | 同 |
| 位置 `nargs='?'` 与后续必需位置同段 | `opt='DEFAULT'`，不计出现 | 同（2026-10-27 对齐：不再写 const） |
| `set_defaults(undeclared=7)` | 结果里有 `undeclared=7` | 同（2026-10-27 对齐） |
| `files='*'` + 子命令，`tool add` | `files=[] cmd='add'` | 同（段内为槽预留 1 个 token） |
| `store_const` 缺 `const` | `ValueError` | config_error（类别顺序不同，都是声明期失败） |
| 位置参数 `required=True` | `ValueError` | config_error |
| 默认值不在 `choices` | 接受（choices 只校验命令行值） | 同（2026-10-27 放宽） |
| `--mode` + `choices` | usage/帮助占位名 `{fast,slow}` | 同（2026-10-27 对齐） |
| `nargs=2` + `metavar=('A','B')` | `--pair A B` | 同（`Argument.metavars`，要求个数 = n） |
| 子命令槽 usage | `{add,list} ...` | 同（无方括号，带省略号） |
| `add_subparsers(title=/description=/metavar=)` | 帮助段标题、说明、占位名 | 同（缺省标题为 `commands`） |
| `BooleanOptionalAction` usage | `[--cache \| --no-cache]` | 同（2026-10-27 对齐） |
| `HelpFormatter(max_help_position=N)` | 说明列起始列 | 同（`HelpFormat.max_help_column=N`；0 用段落默认 22/26） |
| 非法 choices 诊断 | `invalid choice: 'fst', maybe you meant 'fast'? (choose from 'fast', 'slow')` | 「选项 --mode 的值不在候选集合中，是否想用 fast？（可选：fast, slow）」 | 同结构：候选列表 + 建议；措辞中文 |
| 未知子命令诊断 | `invalid choice: 'ad' ... (choose from 'add', 'list')` | 「未知子命令 ad（可选：add, list）」+ 建议 | 同上 |
| 多余 token 诊断 | `unrecognized arguments: b c` | 「多余的位置参数：b c」 | 同上，全量列出 |

## 2. 差异项与保留理由

| 差异 | argparse | yh cli | 理由 |
| --- | --- | --- | --- |
| 长名称缩写缺省 | `allow_abbrev=True` | **false** | 缩写会随注册集变化改变既有脚本语义；显式开启更稳（设计 §5.3） |
| 未知长前缀 `--out=x` | 可缩写命中 | 缺省报「未知选项」，开启 `allow_abbrev` 才唯一匹配 | 同上；多义总是错误，不按注册顺序取候选 |
| 错误消息语言 | 英文（`the following arguments are required: source`） | 中文（`缺少必需的位置参数`） | 面向本仓库工具链；诊断**类别**与退出码与 argparse 对齐 |
| 帮助默认展示 | 显示默认值 | 缺省不显示，`HelpFormat.show_defaults` 打开 | 长默认值（路径/列表）会把帮助撑散；按需展示 |
| 整数范围 | Python 任意精度 | `integer` 为 i64、`natural` 为 u64，越界报 usage_error | 编译目标为定宽整数；不静默截断 |
| 浮点词法 | `float()` 接受 `nan`/`inf` | 只接受十进制与科学计数 | 帮助/结果渲染不引入 `nan`/`inf` 文本；需要时用自定义 converter |
| 解析入口 | `parse_args` 默认读 `sys.argv[1:]` | 显式传 `[]*char`、`parse_main` 或 `parse_main_or_exit` | 结果与输出解耦，便于测试与嵌入（设计 D2） |
| 结果对象 | 动态 `Namespace` | `Result` + 类型化查询，显式 `release` | 无反射与 GC；所有权可审计（设计 D1/D4） |
| `append` + `nargs=2` | 展平为 `['a','b','c','d']` | `append` 保留批次（depth 2），`extend` 才展平 | 「一次出现的多值」与「多次出现的批次」需要可区分 |
| 混合模式的同 dest 混用 | 允许（按内部次序） | 返回 config_error | 位置 action 在选项之后统一提交；拒绝比给出与原始次序不符的结果更安全 |
| 子命令前后全局选项 | 根选项在子命令前有效 | 同；「前后都要」用公共 parent 分别 `inherit` | 复制而非穿透，行为可预测（设计 §10.1） |
| 参数文件注释 | `#` 无特殊含义 | 同；不做 shell 转义 | 逐行语义简单可移植；需要转义时用 `line_converter` |
| 参数文件上限 | 无内置上限 | 深度/字节/token 三个上限，可经 `ParseConfig` 调整 | 展开必须有界，失败可定位（设计 §13） |
| 位置参数与子命令槽共存 | 同段优先给子命令（`PARSER` 至少吃 1 个 token），单文件名的 `files='*'` 声明下 `tool name` 会报 invalid choice | 同段预留给槽 1 个 token，消息为「未知子命令 x（可选：add, list）」 | 对齐分配语义；候选列表在批 3 补齐 |
| 帮助宽度缺省 | 终端宽度 −2 | 固定 80 | 需要更宽就显式 `width`；自动宽度被 C ABI 挡住（Darwin 的 `ioctl` 是变参入口，`@[extern]` 只支持定参），待编译器提供非变参 shim |
| 帮助说明列缺省 | `max(24, 最长名称 + 2)` 动态 | 位置 22、其余 26（`max_help_column` 可覆盖） | 布局稳定；过长的名称按「至少 2 个空格」降级 |
| choices 的说明附录 | 不额外展示 | 帮助说明后追加 ` (choices: a, b)` | 与 usage 的 `{a,b}` 互补，便于阅读 |
| `HelpFormatter` 构造参数 | `prog`/`indent_increment`/`max_help_position`/`width` 都可调 | 只有 `width` 与 `max_help_column`；缩进固定 2 | 缩进 2 与 argparse 默认一致，暂不暴露 |
| `get_default` 未知 dest | 返回 `None` | 返回 -1（并用 `contains` 区分键不存在） | yh 用返回码而非 `None` 表示「没有静态默认值」 |
| `--unknown --help` | 先识别 help，退出 0 | 未知选项优先，usage_error 退出 2 | 设计 §14.3：已识别错误优先于后来的控制请求 |
| known 模式未知短组合 | 应用已知前缀，剩余后缀留在 extras | 整 token 保留，不累计已知前缀 | README §9：避免只生效一半的短组合 |
| deprecated 运行期提示 | 无内置 deprecated 概念 | 显式使用时经 `Result.warnings` 返回一条警告 | 设计 §14.3；不改变退出码 |
| 文本模板范围 | help 可引用任意 action 属性 | 仅 `%(prog)s/%(dest)s/%(default)s/%(type)s/%%` | 静态类型与有限模板，不做任意格式化 |
| remainder 中的 `--` | 终止选项解析，`--` 不进结果 | 作为 remainder 数据保留 | 设计 §9.3：remainder 开始后全部 token 都是数据 |

## 3. 未纳入范围（与 argparse 能力表一致）

- 反射/属性驱动的接口生成、类型注解、`subparsers` 的 `set_defaults` 式回调分派
  （yh 用应用自己的分派表，设计 §8.3）。
- `abbrev` 之外的模糊匹配、`parse_known_args` 之外的部分解析变体、
  `FileType` 这类打开文件的 type 工厂（yh 用 converter/validator 表达）。
- 输出格式的完全一致性：帮助布局按本仓库的字节宽度近似折行，不承诺与
  argparse 逐字符相同；颜色与终端检测策略见设计 §14。
- Python 动态类型语义：`type=` 任意可调用、`choices` 混类型比较、
  `default=argparse.SUPPRESS` 之外的哨兵值等，按 yh 的静态类型与
  `DefaultMode` 表达。

## 4. 差分维护

- 值/诊断类别/退出码的对照由 `libs/cli/*.test.yh`（51 个 test）与
  `libs/cli/test/run.py`（真实 argv/退出码）共同承担；`cliwarnings` 保留在
  runner，`diff.py` 负责 94 条 argv 的 argparse 差分。迁移记录见
  [YT4-P4](../01-finished/yh-YT4-P4-cli迁移-2026-10-25.md)。
- 差异项一旦变化，必须同时更新本文与对应 `.yh` 用例；不接受只改文档不改用例。
