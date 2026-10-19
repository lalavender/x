# macOS/ARM64 LLVM：F2 移植、默认切换与 Darwin 种子（2026-10-19）

## 结论

F2 全量移植到 LL11 基线（`origin/llvm` aa6e424），macOS/ARM64 默认后端已切到
LLVM；`bin/yh-darwin-arm64` 滚为 72MB 的 LLVM 默认种子（`fbd0dd19…`），新种子
冷编、默认门、自举门与 Darwin 专项门全部通过。按用户决定，性能项（20 轮对照、
RS2/RS3/R2c）后置，不在本轮宣称 LL11/F2 性能门或“首个完整 SSA 版本”完成。

## 移植方式

- 以 `ff806ab` 为 base、F2 工作树为 ours、`aa6e424` 为 theirs 做**逐文件三方合并**，
  不整树 rebase（F2 工作树含已上游的 RS1c/RS3b 改动）。
- 9 个冲突：
  - `compiler/ast/ast_ir.yh`、`tests/selfhost/native-selfhost.py`、
    `tests/selfhost/link-cache.py`、种子二进制：取上游（上游的 RS3b 位移修正
    与 LL11 自举改动更新）。
  - `compiler/cmd/link_cache.yh`：保留 F2 的 Darwin `-L`/自举闭包注入，合并上游
    对象键改动。
  - `compiler/cmd/module_worker.yh`：注释取上游。
  - `tests/modules/build-check.py`：上游递归产物发现 + F2 的 Darwin 断言。
  - `docs/todo.md`/`docs/finish.md`：合并 LL11 与 F2 两条线。
- 新增 F2 代码/测试/工具 51 个文件（Apple ABI/runtime、`darwin_link`、Darwin
  host/SDK 工具、`llvm-darwin-*` 测试、缓存/链接/默认门、双模块夹具等）。

## 默认切换

- `compiler/gen/state.yh`：`DARWIN + ARM64` 置 `c_backend=1`（与 LL11 的
  `LINUX + X64` 并列，host-gated）。
- `Makefile`：`LLVM_HOST=darwin-aarch64` 时
  `RUNTIME_TEST=llvm-darwin-runtime.py`、`CACHE_TEST=llvm-darwin-cache.py`、
  `MODCHECK_FLAGS=--backend llvm`；`test-llvm-darwin` 增加默认门。
- `tests/selfhost/native-selfhost.py`：
  - 宿主 triple 参数化（`aarch64-apple-darwin`），LLVM 快照取
    `targets/<triple>/llvm/O0`；
  - Darwin 自动 LLVM；旧种子（无 F2 桥）先以 legacy 编过渡代 cc2，cc3/cc4
    再 LLVM 连续自编；滚动后的新种子直接 LLVM；
  - 种子能力探测用 `--emit-llvm --emit-asm`（单独 `--emit-llvm` 只是开关，
    不进入发射入口）。
- `tests/modules/build-check.py`：LLVM 模式下 `--target/--opt-level` 缺省按宿主补齐，
  `make selfhost-native` 不必重复传 triple。
- `tests/yh-run/check.py`：宿主 target 推断区分 Darwin，避免把 macOS 误标成
  `aarch64-unknown-linux-gnu`。
- **关键修复**：Makefile 曾全局 `export YH_LLVM_SELFHOST=1`，导致普通用户程序
  也被 force-load 桥/LLVM（`runtimebytes` 导入 `malloc/free/memmove` 与大量
  C++ 符号）。现收窄为“只对 `compiler/` 项目注入”：`tools/seed-build.py`
  按项目路径设置，自举脚本只在构建编译器时设置；普通项目不继承。

## 默认门（`tests/selfhost/llvm-darwin-default.py`）

无 `--backend` 构建双模块项目，断言：

- `checked_functions > 0`、`backend_emitted_functions == checked`、`fallback=0`；
- 产物在 `.build/targets/aarch64-apple-darwin/llvm/O0`，无 legacy `asm/*.s`；
- 可执行文件可运行；
- 默认 `--emit-llvm` 文本带 `target triple = "aarch64-apple-darwin"`，
  默认 `--emit-asm` 是 ARM64 机器汇编。

## 种子

- `make seed`：`bin/yh-darwin-arm64` 72MB，SHA-256
  `fbd0dd1949bb2eaabf65e65fa4cca7300133795ae760c6d3d771653b1bcbeab1`；
  Mach-O arm64、ad-hoc 签名 `codesign --verify` 通过。
- 删除根 `yh`/`compiler/.build` 后用新种子冷编成功；默认门通过；
  `make test`、`make selfhost-native` 用新种子复验全绿。

## 门禁

| 门 | 结果 |
|---|---|
| `make`（新种子冷编，YH_LLVM_HOST=1） | 通过 |
| `make test`（默认 LLVM） | 347/348（1 个 Linux 专属跳过） |
| `make selfhost-native`（新种子，全部 LLVM） | 固定点 24 产物、自解析 104、项目 105/105 |
| `make test-llvm-darwin` | 19 项 PASS（含默认门） |
| `make selfhost-llvm-darwin` | A→B/C/D、O0/O2 固定点、隔离 PATH、全门通过 |

## 未完成（按用户决定后置/待平台）

- 20 轮性能对照与 >10% 回退归因；RS2（LLVM 函数级缓存）、RS3（文件级对象）、
  R2c（线程池）——性能专项。
- F2-9 Linux/x64→Darwin 交叉引导（独立验收，按 Linux/CI 分工）。
- macos-14 上实跑 F2-8/默认门（CI 已接入，待手动触发记录）。
- Linux/ARM64 的 LLVM runtime/AAPCS64 ABI 未接，继续 legacy。
