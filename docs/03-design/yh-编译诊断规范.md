# yh 编译诊断规范（V 风格片段 + 精确 caret）

- 状态：已实施（D0–D2，2026-11-15）。D3/D4/D5 见 `docs/todo.md`。
- 落地位置：`compiler/errors/{api,render}.yh`、`compiler/token/api.yh`、
  `compiler/check/diag.yh`、`compiler/support/api.yh`。
- 观测工具：`tests/diagnostics/`（`check.py` + `cases/` + `baseline.md`）。

本文是**契约**：渲染器、位置选择、回退条件都以这里为准；改行为先改本文。

## 1. 输出格式

```text
tests/yh-run/fail/02-bad-assign.yh:3:17: 错误: 不能把指针赋给非指针（用 .to_type）
    1 | // fail: 类型不匹配，字符串字面量（*char）不能初始化 int 绑定
    2 | fn main() int {
    3 |     let x int = "s"
      |                 ~~~
    4 |     return 0
    5 | }
```

| 元素 | 规则 |
| --- | --- |
| 头行 | `path:line:col: 错误: 文案` / `path:line:col: 警告: 文案`；与片段无关，脚本正则不变 |
| 头行列号 | 1 基**字节**列（不是字符列、不是显示列）；`line_bias` 叠加在行号上 |
| 上下文 | 出错行前 2 行、后 2 行；文件边界处自动收窄 |
| 行号栏 | `%Ns | `，`N = max(5, 末尾行号位数)`；caret 行用同宽空格 + `| ` |
| 下划线 | 可见宽度 1 → `^`；>1 → `~` 重复该宽度；两端夹到行尾 |
| 缩进 | `\t` 一律展开为 4 个空格（固定，不做 tab stop） |
| CRLF | 行尾 `\r` 不显示，也不参与宽度 |
| 宽度 | ASCII 1 列；CJK/全角 2 列；组合字符 0 列；非法字节 1 列 |
| 长行 | 单行超过 `DIAG_LINE_COLS=160` 显示列时围绕 caret 开窗（左侧留
  `DIAG_OPEN_BEFORE=60` 列），截断侧补 `…`，caret 偏移按窗口重算 |
| 编译期展开 | 头行文案后追加 ` [编译期展开值: …]`（沿用旧行为） |
| 颜色 | **默认无颜色**（D5 才考虑 TTY 颜色） |

## 2. 回退矩阵（何时只输出单行头）

| 条件 | 行为 |
| --- | --- |
| `diag().plain != 0`（`YH_DIAG_PLAIN=1` 或显式 `set_plain(1)`） | 单行头 |
| `diag().line_bias != 0`（`.s.ct` 来源映射） | 单行头 |
| 源槽未登记 / 源码指针为空 / 长度 ≤ 0 | 单行头 |
| **路径槽的当前值与源码归属路径不一致** | 单行头（见 §4） |
| 行号 < 1 或超出文件可定位行数 | 单行头 |
| 片段缓冲写满 | 截断并以 `\n` 结束，绝不越界 |

`YH_DIAG_PLAIN=1` 是内部保险：输出与 D1 之前**逐字节相同**（同一段头行拼装代码，
同一 2047 字节截断点）。它不写进用户文档。

## 3. 位置选择规则（D2）

诊断落在哪，按下面的顺序选，**禁止**新增「解析完再 `err_tok`」的错误点：

1. **当前 token 就是问题** → `token.err_tok(msg)`。
2. **刚解析完的构造是问题** → `token.err_at(first, msg)`（构造首 token）或
   `token.err_range(first, after, msg)`（整段下划线）。
3. **只有源字节偏移**（名字/字面量的 `start,len`）→
   `token.err_at(token.index_at_offset(start), msg)`。
4. **跨文件 / AST 后置校验** → `check.diag.file_span(file_id, first, after, msg)`
   或 `file_span_code(...)`（自动切路径 + 源码，报完恢复）。
5. **值内核错误码**（`vk_*`）→ `check.sem_report`，其位置优先取
   `support.fc().c_expr_first`（`parse_expr_iso` 记录的表达式起点），再退游标。
6. **编译期引擎内部诊断** → `comptime.ct_err`，其位置优先取
   `ct_pos_save/enter/restore` 登记的 `$f(...)` 调用 token。

两条硬规则：

- **合成 token 不可指**：词法器为换行补的隐式 `;` 与 EOF 长度为 0，起点落在
  行尾之后。`token.err_at`/`err_range` 经 `real_index` 回指最近的真实 token，
  因此「caret 落在行尾 +1」的旧病不再出现。
- **不猜位置**：拿不到真实位置就退化为单行头，不拿相邻构造顶替。

## 4. 路径与源码必须同源

片段内容来自 `support.src_ctx().data`，头行路径来自路径槽。路径被**单独**切换
（CT 来源映射、只切 `path` 不留 `source` 的旧调用点）时两者会不一致，片段就会
把 A 文件的源码挂在 B 文件的名字下面。

因此：

- 路径与源码**同时**切换的地方（`support.read_source`、
  `build.mb_restore_front_file`）必须调用 `errors.bind_source_path(path)` 登记；
- 渲染前 `rich_allowed` 用 `source_path_matches()` 逐字节比较路径槽与登记值，
  不一致就退回单行头。

跨文件诊断的正确入口是 `check.diag.file_span`：它切路径 + 源码 + token 表快照，
报完恢复，失败路径也恢复。

## 5. 说明行（D4）

片段之后（无片段时紧跟头行）可以追加**一条**说明行：

```text
  说明: 期望 `int`，得到 `*char`；用 value.to_type(int) 显式转换，或把绑定改成指针类型
```

- 缩进固定 2 空格，前缀 `说明: `，整行一条，不换行（超长按缓冲截断）。
- 内容来源三类：值内核建议（`table.vk_help(code)`）、“期望 X，得到 Y”（`check.ty_display`
  递归渲染 `*T`/`[N]T`/`[]T`/fn/具名聚合）、未声明名字或未知类型的“是否想用 `xxx`？”
  （有界编辑距离 ≤2、名字长度 ≥3、最多 1 个候选）。
- 头行文案**不变**：建议只出现在说明行，`fail-contains` 断言不受影响。
- 空说明（指针为 0 或空串）不输出，等价于没有说明行。

入口：`errors.err_span_note` / `warn_span_note` / `token.err_at_note` / `err_tok_note`。

## 6. 内部错误（ICE）与路径级诊断（D3）

| 形态 | 触发 | 输出 |
| --- | --- | --- |
| 用户源码错误 | 有位置 | `path:line:col: 错误: …` + 片段 + 说明 |
| 路径级错误 | 无可用源码（清单/导入/接口/模块冲突/LLVM 桥） | `path[:line[:col]]: 错误: …`，不画片段 |
| 程序级失败 | IO/分配失败 | `yh: …`（`fail`/`fail_path`） |
| 内部错误 | 编译器不变量被破坏、接口协议不一致 | `yh: 内部错误: …（版本 <编译器版本>，请提交 issue）` |

ICE 由 `errors.ice` 给出（纯渲染在 `fmt_ice`，便于逐字节单测）；版本由驱动入口
`errors.set_version` 登记一次。**链接器原始输出**（`compiler/link/*`）不进 `errors`：
它是 ld/lld 的原文，做源码映射不在本规范范围。

## 7. 颜色（D5，仅 TTY）

- 默认**无颜色**；`isatty(2)` 为真且未设 `NO_COLOR` 时才着色。
- 覆盖链：`YH_DIAG_COLOR=always|never` > `NO_COLOR` > `isatty(2)`。
- 着色范围：头行的 `错误`/`警告` 两个字（红/黄加粗）与 caret 下划线；行号栏、
  源码行、说明行保持原色。
- 测试与管道（非 TTY）永远无色；`YH_DIAG_COLOR=always` 仅供验收脚本使用。

## 8. 观测工具与指标

`tools/py tests/diagnostics/check.py` 提供四个模式与三个硬门：

| 用法 | 作用 |
| --- | --- |
| `--quiet` | 汇总：`失败语料/片段/caret/越界/末字符/tail_paren/跨文件` |
| `--snapshot PATH` | 生成逐用例 Markdown 快照（含 `tail_paren` 汇总） |
| `--cases` | 夹具断言：头行行列、caret 显示列、下划线宽度、片段行数、说明行、跨文件来源 |
| `--color-check` | 颜色三态：管道无色、`always` 有色、`NO_COLOR` 无色 |
| `--max-line-end N` | 硬门：列号越出行尾的例数上限 |
| `--max-tail-paren N` | 硬门：`col == 行宽` 且末字符是 `)` 的例数上限 |

## 9. 基线数字（2026-11-17，`./yh`，含 2026-11-17 的余项收尾）

```text
失败语料: 148
带源码片段: 148
带 caret: 148
列号越出行尾(>行宽): 0/148 (0.0%)     # D2 之前 68
列号=行宽(指向末字符): 5
落在调用右括号 `)`: 0                 # 2026-11-17 前是 2（28 / 88）
跨文件头: 0
无位置头: 0                           # D3 前是 1（12-wraps-too-many 的纯 yh: 行）
```

`列号=行宽` 的 5 例都是「命令行/字符串在行尾收口」的构造，caret 指在行尾字符上
（例如 `module ;` 的 `;`、`fn f(){` 的 `{`），不是落在调用右括号。

## 10. 单元测试与夹具

| 层 | 位置 | 内容 |
| --- | --- | --- |
| 渲染器逐字节 | `compiler/errors/api.test.yh`（`just test` 执行，20 例） | 片段格式、说明行（有/无片段、空说明）、ICE 形式、tab/CJK/CRLF/长行/回退/截断 |
| 位置与几何 | `tests/diagnostics/cases/*.yh` + `.expect` | 头行、caret 显示列、下划线宽度、片段行数、说明行内容 |
| 跨文件 | `tests/diagnostics/cases/two-file-module/` | 头行文件与片段内容同属出错文件 |
| `yh test` | `tests/diagnostics/cases/testkit-fail/`（`command: test`） | 测试体编译错误也带源码片段 |
| 颜色 | `--color-check` | 管道无色 / always 有色 / NO_COLOR 无色 |

## 11. 多行跨度与多错误上报（2026-11-17）

**多行跨度（已实现）**

- 位置接口：跨度用「首 token 行列 + 字节宽度」表达，宽度可以越过首行行尾。
  `token.err_call_span(first, after, msg)` 取 `first..after`（不含）两个 token 的
  源码字节区间；与 `err_range` 的差别是不再把宽度夹到首行行尾。
- 渲染（`errors/render.yh` 的 `fmt_snippet`）：首行下划线夹到行尾；跨度仍未画完时，
  后续每一行补一行下划线（长度取剩余字节与该行显示列的小者），片段窗口自动扩到
  跨度末行。颜色只包下划线本身，与单行一致。
- 触发点：调用实参个数不符（`实参个数少于固定参数` / `实参个数与函数签名不符`）用
  `c_call_lparen`（parse 在调用点记录的 `(` token）到 `)` 的跨度，多行实参列表因此
  逐行下划线。夹具：`tests/yh-run/fail/217-call-arity-multiline.yh`。

**多错误上报（仅有索引阶段）**

- 索引阶段（读模块头）：`project_index.yh` 的 `pj_scan_source` 在单个文件失败后继续
  扫描同目录其它条目，最多 `PJ_SCAN_ERROR_LIMIT = 8` 条，达到上限后停止并写一条
  `yh: 已停止继续扫描：错误数达到上限（8 条）`。夹具：
  `tests/diagnostics/cases/multi-file-errors/`（`.expect` 的 `heads: 2`）。
- 语义检查阶段（`check` 与函数体 lowering）：仍**首错即停**（返回 -1 链），未做错误
  恢复。因此同一模块体内有多处错误时只报第一处。

