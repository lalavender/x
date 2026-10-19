# macOS/ARM64 LLVM：F2-8 原生连续自举与全量门（2026-10-19）

## 结论

F2-8 完成：Darwin 显式 LLVM 路径具备完整原生连续自举证据——入库种子 legacy 编 A，
A 以 LLVM 编 B/C/D，O0/O2 均达逐字节固定点；D 上跑完自解析、全量语料与 Darwin
专项门，隔离 PATH 下无系统 LLVM 工具调用。仍未切默认、未滚种子。

## 自举链接注入

- 问题：Darwin 最终链接使用 raw `ld64.lld` argv（yh 侧拼装），而自举闭包只对
  GNU 模板路径生效（`YH_LLVM_SELFHOST_LINK_FLAGS` 为空），A 编出的 B 只链入弱桩，
  无法执行 `--backend llvm`。
- 实现：
  - `tools/llvm-darwin-host.py` 新增 `raw_selfhost_flags`：把 clang 的
    `-Wl,-force_load,<归档>` 折算成 raw `-force_load <归档>`，追加 `-lc++`；
    写入 `lld_link_config.h` 与 host 记录（`selfhost_link_flags`），并纳入
    `lld_identity` 摘要。
  - `compiler/llvm/lld_bridge.cpp` 暴露 `yh_lld_selfhost_flag_count/flag`；
    `compiler/backend/llvm_bridge.yh` 与两份 `llvm_bind.*.yh` 增加绑定；
    `bridge_stub.c` 增加零长度弱定义。
  - `compiler/cmd/link_cache.yh`：Darwin 项目链接在 `YH_LLVM_SELFHOST=1` 时把闭包
    追加到 argv（容量按数量预留），普通程序与探针不注入。
- 验证：B 内嵌 `lld_identity` 字符串，可直接编译并运行探针。

## 自举脚本（`tests/selfhost/llvm-darwin-selfhost.py`）

- 自检：缺 `.ll`、错接口版本/triple/arch、错代号/复用目录、错误 Mach-O CPU
  全部按预期拒绝。
- A：`tools/seed-build.py --llvm-host darwin-aarch64 --llvm-mode require`
  （legacy 代码生成 + 真实桥）。
- B/C/D：`--backend llvm --target aarch64-apple-darwin -O0/-O2 --emit-llvm --stats`，
  每代核验：arm64 Mach-O、`file`/`otool -L`（无 libLLVM/liblld/libclang，仅
  `/usr/lib/*`）、`codesign --verify`、无裸 `malloc/free` 导出、内嵌 lld 身份、
  原生 `version`；快照经 `expected_llvm_artifacts` 与
  `llvm_snapshot_errors` 校验。
- O0 与 O2 各自比较 B→C→D 的 24 个 `.ll/.s.i/.s.ct`；`stats.json` 冻结各代
  checked/emitted/rejected/backend_rejected/fallback（均 fallback=0）。
- D-O2：自解析 104/104；语法语料；运行语料 O0/O2（346/347，1 个 Linux 专属跳过）；
  模块 18/18；项目验收 105/105；Darwin SDK/host/bridge/object/ABI/runtime/link/cache
  八个专项门。
- 隔离 PATH：只有记录调用的假工具（clang/clang++/ld/ld64.lld/codesign/xcrun/cc，
  命中即写日志并退出 127）；探针的发射与内嵌 lld 链接成功且日志为空。

## 门禁

| 门 | 结果 |
|---|---|
| `make selfhost-llvm-darwin` | 通过（A→B/C/D、O0/O2 固定点、全门） |
| `make test-llvm-darwin` | 通过 |
| `make test` | 通过（346/347，1 个 Linux 专属跳过） |
| `make selfhost-native` | 通过（固定点 123 项、模块项目 105/105） |

本机环境：macOS 27.0、CLT SDK 26.5、LLVM 21.1.8 固定静态包。`macos-14` CI 作业已接入
`selfhost-llvm-darwin` 并上传 stats/logs/snapshots，实跑结果待 CI 记录。

未执行 `make seed`。
