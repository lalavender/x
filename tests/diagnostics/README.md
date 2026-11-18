# tests/diagnostics —— 编译诊断基线扫描与夹具校验

本目录是「V 风格编译诊断」的观测门（D0/D1/D2 交付物）：

- `check.py`：语料扫描（统计有片段/有 caret/列号越界/跨文件）与夹具断言。
- `baseline.md`：由 `check.py` 生成的当前基线快照（**自动生成，不要手改**）。
- `cases/`：诊断夹具。`*.yh` + 同名 `*.expect` 断言头行与 caret 几何；
  `two-file-module/` 是多文件项目夹具，断言「头行文件与片段内容同属一个文件」；
  `multi-file-errors/` 断言索引阶段的多错误上报（`.expect` 的 `heads: 2`）。

## 重新生成基线快照

```bash
# 语料扫描 + 快照（--compiler 指向要观测的编译器）
tools/py tests/diagnostics/check.py --compiler ./yh \
    --snapshot tests/diagnostics/baseline.md

# 只看汇总
tools/py tests/diagnostics/check.py --compiler ./yh --quiet

# 夹具断言（CI 之外的本地检查，失败返回 1）
tools/py tests/diagnostics/check.py --compiler ./yh --cases

# 硬门：列号越出行尾 / 「col == 行宽且末字符是 `)`」的例数上限
tools/py tests/diagnostics/check.py --compiler ./yh --max-line-end 0 --max-tail-paren 3

# 颜色三态（管道无色 / YH_DIAG_COLOR=always 有色 / NO_COLOR 无色）
tools/py tests/diagnostics/check.py --compiler ./yh --color-check
```

脚本输出稳定（无时间戳、按文件名排序），同一语料重复执行结果一致。
中间产物落在 `tmp/diagnostics-work/`（已被 gitignore）。

## 指标口径

- **列号越出行尾（> 行宽）**：硬指标之一。列号是 1 基**字节**列，`col > 行宽`
  表示 caret 落在该行最后一个字节之后，即「指向出错构造之后」。
- **tail_paren**：`col == 行宽` 且该字符是 `)` 的例数——caret 指在调用右括号上通常
  不是理想落点，单独计数并设硬门（其余 `col == 行宽` 多为正确位置）。
- **列号 = 行宽（指向末字符）**：单独列出、**不计入硬指标**。它可能是正确位置
  （出错 token 恰在行尾，如 `let y int = z` 的 `z`），也可能是错位，需要看片段判断。
- **带源码片段 / 带 caret**：应接近全部用例；回退为单行头是给「无源码 / 行号映射 /
  路径与源码不同源」准备的保险，不是常态。

## `.expect` 文件格式

逐行 `键: 值`，`#` 开头为注释：

| 键 | 含义 |
| --- | --- |
| `head` | 头行必须报 `行:列`（1 基字节列） |
| `caret-col` | caret 在「源码行文本」内的 1 基**显示列**（不含行号栏） |
| `caret-width` | 下划线可见宽度（1 是 `^`，其余是 `~`） |
| `snippet-lines` | 片段显示的源码行数 |
| `note-contains` | `说明:` 行里必须出现的文本（D4） |
| `head-file` | （项目夹具）头行文件名，必须是出错的那个文件 |
| `snippet-contains` | （项目夹具）片段里必须出现的源码文本 |
| `command` | （项目夹具）`build`（缺省）或 `test`（验收 `yh test` 的诊断） |
| `heads` | （项目夹具）诊断头行条数；用于多文件错误恢复断言（缺省不断言） |

## 与 `just test` 的关系

本目录**不**接入 `just test` 的阻断链（方案 §6 D0 的要求：先观测、不急上闸）。
渲染器本身的逐字节断言在 `compiler/errors/api.test.yh`，由 `just test` 里的
`tools/compiler-tests.py` 执行；语料位置质量用本脚本人工/夜间观测。
