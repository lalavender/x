# 0.0.9 — 语言内测试 `yh test`

正式版。本版主线是**源码内单元测试**：`.yh` 里写 `test` 块，用 `yh test` 发现、
构建并逐例执行；同时收口 `os`/`sys` 跨平台拆分、新增 `libc`，并累计交付
`string`/TOML/cli 标准库与 LLVM LA0–LA3 架构收口。

## 语言内测试（YT0–YT3b、YT2d、YT1.1）

**语法**

```yh
fn add(a int, b int) int { return a + b }

test "正数相加" { $assert(add(2, 3) == 5) }   // 字符串行为测试
test add { $assert(add(41, 1) == 42) }        // 文档测试：绑定本模块声明
```

- `test` 为保留字（成员位置继续放行）；只允许顶层，不接受 `pub`、属性、匿名块、
  空名称。
- 文档测试可绑定本模块 `fn`/`const`/`let`/`type`/`struct`/`union`/`enum`，
  支持跨文件、前向与私有声明；不自动调用被测函数。
- 生产构建只检查测试体语法：不登记测试符号、不发射代码，模块对象与 `.s.i` 中
  不出现 `__yh_test_`。

**命令**

```bash
yh test                        # 发现、构建并逐例执行
yh test <模块|源文件>
yh test --list                 # 只列出身份、位置与文档目标
yh test --no-run               # 只构建，不链接/不执行
yh test --emit-llvm            # 另写 LLVM 文本供审阅
yh test --filter 子串           # 只运行身份含子串的用例（也过滤 --list）
yh test --timeout 15           # 单例超时秒数（1..3600，缺省 15）
YH_TEST_JOBS=8 yh test         # 并行度（缺省 4，限制 1..8）
```

- 测试体降低为模块内 `pub` 无参 `void` 函数，走普通 CheckedModule → SSA → LLVM；
  每模块生成入口模块 `yh_test_<mod>` 并链接测试二进制。
- `$assert(cond[, "消息"])` 在 test 体内是**运行期**检查：失败向 fd 3 写
  `YHTF + 行 + 列 + 消息` 并 `exit(1)`；正常返回由入口写 `YHTP`；
  `libs/testing` 的 `fail`/`skip` 分别写 `YHTF`/`YHTS`。
- 父进程逐例 fork/exec，只有「退出码 0 且有 YHTP」判 PASS；提前 `exit(0)`、
  崩溃、超时、记录缺失一律 FAIL 且不阻断后续用例。失败输出断言位置、消息
  （超过 59 字节给出「已截断」提示）与逐例日志尾部。
- 逐例日志在 `tmp/yh-test/log/<模块>-<序号>.log`；汇总为
  `结果: N passed; M skipped; K failed`。
- 只在 test 体内使用的 `import` 是测试依赖：生产构建不解析、也不报未使用。
- 测试构建使用独立目录 `tmp/yh-test/` 与扩展缓存键（测试模式 + 协议标签 +
  本轮选中测试集合摘要），同选择可增量复用、改变选择重新编译，生产/测试互不
  相通。
- **项目外单文件**：`yh test foo.yh`（所在目录无 `project.toml`）建立临时单模块
  项目（根在 `<源文件目录>/tmp/yh-test/single`），只装入该文件、不装入相邻
  `.yh`，可导入标准库；模块名取 `module` 头，缺失时由文件名派生。

**标准库与编译器内建测试**

- `libs/string/99_tests.yh`：5 条内建测试；入口 `make test-lib-tests`。
- `compiler/` 的 `gen`/`lex`/`parse`：8 条内嵌测试；入口
  `make test-compiler-tests`（`tools/compiler-tests.py`，准备自举 LLVM 闭包环境）。
- 两者都已接入 `make test` 与 `make selfhost-native`。

## 标准库

- `os`/`sys` 跨平台拆分收口：共用文件 + `*.darwin.yh` 专属文件（目录/进程/时间/
  内存/errno/常量），各自新增 `.yh` 测试项目。
- 新增 `libc` 模块（内存/字符串/转换/排序）与 C 对照测试项目。
- `string` 标准库首期（ST0–ST6）：只读 `View`、可增长 `String`、查找/切分/替换
  与 UTF-8 基础操作。
- TOML 1.1 reader 标准库：独立 `Document`/只读 `Value`，通过固定 toml-test
  v2.2.0 的 1.1 清单 681/681。
- cli argparse 差分收尾：自定义 usage 与模板、`version_text`、每层默认值预置、
  选项 remainder、`Result.warnings` 与 deprecated 警告。
- `examples/` 清理为单文件示例。

## 编译器 / 工程

- LLVM 架构收口（LA0–LA3）：函数级 IR 与 check 切片缓存、受检快照与 lowering
  分层、会话接口就绪调度、`--stats` 覆盖计数。
- 自举链接闭包只强制桥整库加载，`yh` 体积 73.7 MB → 70.6 MB。
- 内置（prelude）函数登记迁入 `builtin` 模块。
- 修复：源码根内 `tmp/`、`.build/` 被当源码扫描；自解析与种子快照跳过构建产物；
  测试构建与生产缓存的相互污染；Linux 目标测试运行时缺 `@write` 声明。

## 验证（本机 macOS/arm64，种子 = 0.0.9-rc.2）

- `make test`：ANTLR 与编译器语法正例 81/81、反例 49/49；运行语料
  run 211/212（1 条平台 SKIP）、fail 136/136、pass 9/9；
  `tests/modules/test-check.py` 38/38；string 内建 5/5；
  `compiler-tests 3/3`；TOML 6/6；代码统计 6/6。
- `make selfhost-native`：候选 cc3→cc4 的 30 个模块产物逐字节一致、
  cc4 自解析 114 个源文件、modules 19/19、`compiler-tests 3/3`、
  project cases 121/121。
- Gitea `ci.yml`：`0.0.9-rc` 分支门 Darwin 原生与 Linux/AArch64 容器均通过。

## 种子

- 正式版由 `0.0.9-rc.2` 的种子编译；rc.2 由 rc.1 种子编译，rc.1 由 0.0.8 种子
  编译。`make fetch-seed` 取最新带资产的 Release（含 rc）。
- 0.0.9 发布出的种子开始支持 `test` 语法，供 0.0.10 线使用。

## 已知限制

- 测试构建的函数级 IR 缓存与 check 切片缓存仍未启用（键只建模 `TK_FN`）。
- 单文件模式无 `[link]`/`[c]` 配置，只能用默认链接环境；临时项目根固定，
  同目录并发执行会互相覆盖。
- `tests/yh-run`、`tests/modules` 等既有验收尚未迁到语言内测试（YT4 待做）。
- 发布流程 R1–R4（分支模型、tag 祖先校验、rc 取种、版本漂移）仍未落地。
