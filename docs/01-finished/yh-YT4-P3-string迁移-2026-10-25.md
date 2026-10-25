# YT4-P3：string 测试迁移（2026-10-25）

## 范围

把 `tests/modules/projects/string{view,owned,transform,utf8}` 的断言迁入
`libs/string/99_tests.yh`（在原有 5 个 test 之后追加 10 个）；
`stringmodel` 与 `stringinterop` **保留**为外部公开面/跨库 smoke（决策 D15），
`stringresources`、`reference.py`、`install.py`、`complexity.py` 保留。

## 断言对照表

| 旧夹具 | 旧 `if` 断言点 | 新 `test` |
| --- | --- | --- |
| `stringview` | 56 | `切分：空片段与多字节分隔符`（32）、`切分：NUL、参数错误与迭代器复制`（24） |
| `stringowned` | 72 | `拥有者：构造、增长与 C 边界`（22）、`拥有者：assign、clear、truncate 与 reserve`（23）、`拥有者：clone、move、自别名与溢出`（28） |
| `stringtransform` | 31 | `变换：concat 与 join`（9）、`变换：replace 与 ASCII 大小写`（22） |
| `stringutf8` | 47 | `UTF-8：校验矩阵与错误位置`（15 条静态断言，矩阵循环展开 24 条运行期检查）、`UTF-8：utf8_next 遍历`（10）、`UTF-8：append_rune`（12） |

说明：

- `stringutf8` 的非法序列矩阵用 12×4 的用例表 + 循环表达，静态断言从 12 条
  变成 2 条、运行期检查翻倍（状态 + 错误偏移）；`utf8_next` 的每个旧
  `if (a || b || …)` 保留为一条组合 `$assert`，失败时仍带行号与消息。
- 断言只调 string 的 pub API；helper 统一为 `test_view` / `test_bytes`。
- 迁移时逐项核对了 setup 断言（例如 `grow_sub.status`、`overlap_sub.status`），
  避免把“准备对象成功”的旧检查漏掉。

## 删除/保留

| 项 | 处置 |
| --- | --- |
| `stringview`、`stringowned`、`stringtransform`、`stringutf8` | 删除 |
| `tests/string/run.py` 的 `view/owned/transform/utf8` 组 | 删除（默认组改为 model/interop/resources） |
| `build-check.py` 的 `st2`–`st5` | 删除（保留 `st1-string-model` 与 `st6-string-interop`） |
| `tests/string/README.md` | 重写为“迁移后分工” |
| `libs/string/99_tests.yh` | 15 个 test / 216 条 `$assert` |

## 验证

| 项 | 结果 |
| --- | --- |
| `cd libs && yh test string` | 15 passed / 0 failed |
| `cd libs && yh -O2 test`（全 libs） | 66 passed / 0 failed |
| `make libs-test` | 66 passed + cli 10/10 + os 11/11+1/1 + libc 2/2 |
| `make test-string` | **16.7s**（迁移前 26.6s）；model/interop 4.4s、resources 11.6s、reference 92 例 1.3s |
| `make test` | **56.8s**（YT4-0 后基线 94.9s；json/toml/string 迁移合计 −38s） |
| `make selfhost-native` | **未通过**：停在 `tests/selfhost/llvm-function-cache.py` 的「损坏记录」期望（该脚本与 `compiler/ir/ssa_module_40*`、`module_snapshot_lower_cache*` 正被另一会话改动，属其 PC 工作的 WIP），与本迁移无关，待其完成后复验 |

`make test` 期间还观察到 arch-check 的 `max_build_lines` 因 PC3 落地 +6
（10730 → 10736），已同步预算并在 `tools/arch-check.py` 注释说明。
