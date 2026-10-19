# macOS/ARM64 LLVM：F2-7 SDK 内容身份与失败提交专项（2026-10-19）

## 结论

F2-7 收口完成：链接键覆盖 SDK 重导出 stub 闭包，对象键显式记录 PIC；新增
`llvm-darwin-cache.py` 专项门验证输入变化矩阵、原子发布与并发。本机三道门全绿，
未滚种子。

## 实现

### 链接键：SDK stub reexport 闭包（`compiler/cmd/darwin_link.yh`）

- 问题：链接键只哈希 `libSystem.tbd` 自身，但 `libSystem` 重导出
  `/usr/lib/system/*.tbd`；改这些 stub 不会失效链接键。
- 实现：
  - `mb_macho_tbd_collect`：解析 TAPI 文本，从 `reexported-libraries:` 段抽取
    绝对路径（新顶层键行结束该段），上限 64 条、每条 192 字节。
  - `mb_macho_tbd_hash_stub`：把 `/usr/lib/...dylib` 解析为 SDK 内 `.tbd`
    （先换后缀、再试原名），混入解析路径与内容；缺失与存在以哨兵字节区分。
  - `mb_macho_tbd_closure`：递归处理子 stub，深度上限 2（`libSystem` →
    `libmathCommon` 这类符号链接环不会无限递归）。
- 兼容：`.a` 静态库内容已完整入键，不再做 TAPI 解析；项目 `-l` 不在 SDK 时仍由
  lld 诊断。
- 已验证：改动任一重导出 stub 只失效链接键、不重编对象；恢复内容后键值复现。

### 对象键：显式 PIC（`compiler/cmd/module_build.yh`）

Darwin 目标的对象键在 minOS 之后混入 `PIC` 标记。桥当前按目标强制 PIC
（`llvm/bridge.c` 的 `LLVMRelocPIC`），显式记录避免将来引入非 PIC 变体时误命中。

## 测试

`tests/selfhost/llvm-darwin-cache.py` + `tests/modules/projects/llvmdarwincache/`
（`main/` 与 `helper/` 双模块）。用例使用裁剪 SDK（`SDKSettings.json` +
`libSystem(.B).tbd` + `usr/lib/system/*.tbd`，约 1.8 MB）真实链接。

| 用例 | 断言 |
|---|---|
| cache-hot-hit | 无改动构建不重写对象/产物/manifest |
| cache-deterministic | 对象字节跨副本一致；同路径清空重建全部键一致（可执行文件只验证可运行，因 LC_UUID/ad-hoc 签名每次重算） |
| cache-source-content | 同路径源变化只重编 main、helper 不动、链接触发 |
| cache-deployment-version | minOS 14→15→14 对象与链接键按值复现 |
| cache-sdk-root-switch | 不同 SDK 路径对象键相同、链接键不同 |
| cache-sdk-stub-closure | 重导出 stub 改一个符号名只失效链接键，恢复后复现 |
| cache-failure-preserves | 损坏 TAPI 链接失败时旧可执行文件与旧成功 manifest 不变，修复后直接命中 |
| cache-corruption-rebuild | manifest/对象/接口/可执行文件损坏均重验重建 |
| cache-interrupted-build | 终止构建并留下 `.tmp` 残留后，重建仍正确且结果稳定 |
| cache-concurrent-build | 两次并发构建都成功、结果稳定（之后热构建不再改写） |

`Makefile` 的 `test-llvm-darwin` 已接入该门。

## 门禁

| 门 | 结果 |
|---|---|
| `make test-llvm-darwin` | 通过（新增缓存身份门） |
| `make test` | 通过：语法 78/78、反例 42/42、运行 346/347（1 个 Linux 专属跳过） |
| `make selfhost-native` | 通过：固定点 123 项一致、自解析、语料、模块项目 105/105 |

未执行 `make seed`。
