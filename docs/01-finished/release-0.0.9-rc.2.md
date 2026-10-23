# 0.0.9-rc.2 — compiler 内嵌测试上线

预发布（prerelease）。rc.1 发布了支持 `test` 语法的种子，本版用该种子把
**编译器自身的单元测试**接进主门（YT3b），并修掉 rc.1 验收后暴露的测试基础设施
问题。

## 主要内容

**compiler 内嵌测试（YT3b）**

- `gen/buffer.yh`（`hexval`、`is_assign_op`）、`lex/layout.yh`（`lex_can_end`）、
  `parse/parse_type.yh`（`is_member_name`、`is_type_start`）新增 `test` 块，
  可直接测试同模块私有函数。
- 新增 `tools/compiler-tests.py`：复用 `tools/llvm-*-host.py shim` 记录准备
  `PATH`/`YH_CC`/`YH_LLVM_SELFHOST_FLAGS`/`SDKROOT`（测试二进制与编译器一样要
  链内嵌 LLVM 闭包），逐模块执行 `yh test <模块> --timeout 120`。
- 新增 `make test-compiler-tests`，并入 `make test` 与 `make selfhost-native`。

**测试构建的缓存与登记隔离（据此修复）**

- 测试构建不读、不写模块 manifest 缓存：生产接口不含 `__yh_test_*`，
  命中生产对象会让测试入口找不到测试函数（先做 `yh build` 再 `yh test` 必挂）。
- 测试构建不装载、不提交函数级 IR 缓存与 check 切片缓存：曾出现
  「表达式 AST 校验失败」的内部错误，来自测试与生产记录串用。
- 测试函数只在**本轮选中的模块/文件**登记：同项目的依赖模块不再登记测试函数，
  避免 `yh test <模块>` 时依赖留下没有函数体的受检声明。
- 自解析清单与种子快照跳过项目 `tmp/`、`.build/`：`yh test` 生成的入口模块
  曾让 cc4 自解析文件数从 114 变成 117。
- `tests/modules/test-check.py` 增至 28 项，新增
  `test-after-production-build`（先生产构建再跑测试）回归。

**CI 首轮失败暴露的构建环境问题（已修）**

- `linux-x86_64`/`linux-aarch64` 的 `compiler-tests` 报
  `ld.lld: error: duplicate symbol: yh_lld_link_driver`：`compiler/` 已迁移
  `[link]` 归档清单，而 `tools/compiler-tests.py` 仍按旧链路注入
  `YH_LLVM_SELFHOST_FLAGS`，桥归档在同一条链接命令里出现两次。
- 修复：`compiler-tests.py` 与 `tests/selfhost/llvm-isolation.py` 改用清单模式
  环境（`YH_LINK_MANIFEST_ONLY=1` + `YH_LINK_RUNTIME_FLAGS`），不再注入旧闭包，
  与 `tools/seed-build.py`、`native-selfhost.py` 的既有约定一致。

## 验证（本机 macOS/arm64，种子 = 0.0.9-rc.1）

- `make`：rc.1 种子冷编含 test 块的 `compiler/` 通过。
- `make test`：ANTLR 与编译器语法正例 81/81、反例 49/49；run 211/212
  （1 条平台 SKIP）、fail 136/136、pass 9/9；`test-check` 28/28；
  string 内建 5/5；`compiler-tests: 通过 3/3`（gen 2、lex 3、parse 3 例）；
  TOML 6/6；代码统计 6/6。
- `make selfhost-native`：30 个模块产物固定点一致、cc4 自解析 114 个源文件、
  modules 19/19、`compiler-tests 3/3`、project cases 121/121。
- 生产隔离：`compiler/.build/.../obj/*.o` 与 `iface/*.s.i` 中
  `__yh_test_` 符号数为 0。

## 种子

- rc.2 由 rc.1 的种子编译；发布出的 rc.2 种子供 rc.3 使用。
- 本版不再包含 rc.1 的“暂缓 compiler 内嵌测试”提交（已 revert 恢复）。

## 已知未完成

- YT2d（并行执行、逐例日志文件、测试缓存键隔离的完整键设计、超长断言消息
  提示）、YT1.1（项目外单文件临时单模块上下文）。
- 发布流程 R1–R4 仍未落地。

## 用发布出的 rc 二进制验收（2026-10-23）

发布资产的 tar.gz 与其 `.sha256` 一致（取自 host 模式 runner 的
`~/yh-release-dist/ci-131`，与 GitHub Release 上传的是同一组文件）：

| 资产 | SHA-256（tar.gz） |
| --- | --- |
| `yh-0.0.9-rc.2-darwin-arm64.tar.gz` | `7e22591b2c2db81c1f4c2ca6d5cce209e321008301531034f7599f952ada5554` |
| `yh-0.0.9-rc.2-linux-arm64.tar.gz` | `c6caace66939076482e203b2618891a2ead2626c58c8eab530f6cafc3aa2bb77` |
| `yh-0.0.9-rc.2-linux-x86_64.tar.gz` | `7d2a89baae86d0e4e70b1eaa9ad30fe10bfb4b0a1b610e09d66eb7feabf77dbd` |

Darwin/arm64 种子（解包后 `yh` sha256 `7cbf2580…cfb1e837`）装入
`bin/yh-darwin-arm64` 后：

- `bin/yh-darwin-arm64 version` → `yh 0.0.9`；
- `make` 冷编通过；
- `make test` 退出码 0：语法 81/81、49/49；run 211/212（1 条平台 SKIP）、
  fail 136/136、pass 9/9；`test-check` 28/28（含缓存隔离回归）；string 内建
  5/5；`compiler-tests: 通过 3/3`；TOML 6/6；代码统计 6/6；
- `make selfhost-native` 退出码 0：30 个模块产物固定点一致、cc4 自解析
  114 个源文件、modules 19/19、`compiler-tests 3/3`、project cases 121/121。

**CI 迭代记录**：首轮 tag 因 GitHub 资产下载 SSL 中断失败（环境网络）；
二轮暴露 `compiler-tests` 重复注入闭包的 duplicate symbol（已修）；
三轮因构建机磁盘只剩 2.3 GiB，Darwin 链接与 x86_64 对象原子写入失败
（清理再生缓存后重跑）；run 57 五作业全部 success 并发布 prerelease。
`ci.yml` 的 `0.0.9-rc` 分支门同轮通过。
