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

- 值/诊断类别/退出码的对照由 `libs/cli/zz_tests_*.yh`（43 个 test）与
  `libs/cli/test/run.py`（真实 argv/退出码）共同承担；`cliwarnings` 保留在
  runner，`diff.py` 负责 94 条 argv 的 argparse 差分。迁移记录见
  [YT4-P4](../01-finished/yh-YT4-P4-cli迁移-2026-10-25.md)。
- 差异项一旦变化，必须同时更新本文与对应 `.yh` 用例；不接受只改文档不改用例。
