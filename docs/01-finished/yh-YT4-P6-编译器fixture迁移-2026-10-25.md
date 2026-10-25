# YT4-P6：编译器 fixture 迁移（2026-10-25）

## 交付

把 `tests/modules/projects/irverify`（747 行、6 个 `check_*`、退出码 0/1–8）
迁入 **`compiler/ir/zz_tests_verify.yh`**：6 个 `test`、51 条 `$assert`，
只调 `ir` 的 pub API；文件名 `zz_` 前缀（`ir` 的类型/常量在 `ssa_*.yh`，
必须排在之后）。旧夹具的编号 `return N` 只表示失败点，统一改成
`$assert(false, "旧断言 N"); return;`，控制流与检查顺序不变。

- 删除 `tests/modules/projects/irverify` 与 `build-check.py` 的
  `r2a-ssa-phi-verifier`；`copy_proj` 的 `irverify` 特判改为
  `("irfront", "llvmmodule")`。
- `tools/compiler-tests.py` 的 `DEFAULT_MODULES` 增加 `ir`。
- 验证：`python3 tools/compiler-tests.py --modules ir` 6/6；
  `make test-compiler-tests` 4/4（gen/lex/parse/ir）。

## 保留与偏差（有据）

| 项 | 处置 | 依据 |
| --- | --- | --- |
| `irfront`（410 行） | 保留外部 fixture | 它不是纯单元断言：`build-check.py` 用它的 56 个函数做「checked == emitted」发射覆盖统计，并检查旧后端符号计数；迁进模块测试会丢掉这条编译流水线契约（D16：编译器产物/发射契约留外部） |
| `llvmlower` + `lower/module_snapshot_lower_selftest.yh` | 保留 pub 探针与 fixture | `arch-check` 的依赖图允许 `lower → {gen, ir, ast}`，不允许 `lower → parse/check`；探针需要真实的 `CheckedModule`，在 lower 内无法构造。强行迁移需新增模块或破坏分层（D5 已允许 llvmlower/llvmchecked 暂留） |
| `astcheck` | **按门槛跳过** | 实测 `make test-compiler-tests`：3 模块冷 36.7s/热约 18s → 4 模块冷 56s/热 33s，增量 > 10s 门槛（D5：超过就停） |
| `llvmchecked` | 保留外部 fixture | 依赖手工 CheckedModule fixture 与真实 AST/语义实现组合 |

## 验证

| 项 | 结果 |
| --- | --- |
| `compiler-tests --modules ir` | 6 passed |
| `make test-compiler-tests` | 4/4（gen 2 / lex 3 / parse 5 / ir 6） |
| `make test` | 75.2s 绿（compiler-tests 增加 ir 模块，约 +15s） |
| `make selfhost-native` | 192.1s，project cases **122/122**（删除 irverify 后 123−1） |
