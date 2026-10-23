# 0.0.9-rc.1 — 语言内测试 `yh test`

预发布（prerelease）。本版主线是 **源码内单元测试**：`.yh` 里写 `test` 块，
用 `yh test` 发现、构建并逐例执行；同时收口标准库 `os`/`sys` 的跨平台拆分并
新增 `libc` 模块。

## 语言内测试（YT0–YT3a）

**语法**（`docs/yh.g4`）：

```yh
fn add(a int, b int) int { return a + b }

test "正数相加" {              // 字符串行为测试
    $assert(add(2, 3) == 5)
}

test add {                     // 文档测试：绑定本模块顶层声明
    $assert(add(41, 1) == 42, "加法结果应为 42")
}
```

- `test` 成为保留字；成员位置（字段名、`obj.test`）继续放行。只允许顶层，
  不接受 `pub`、属性前缀、匿名块与空字符串名称。
- 文档测试可绑定本模块的 `fn`/`const`/`let`/`type`/`struct`/`union`/`enum`，
  支持跨文件、前向与私有声明；不自动调用被测函数。
- 生产构建只检查测试体语法：不登记测试符号、不发射代码，模块对象与 `.s.i`
  中不出现 `__yh_test_`。

**命令**：

```bash
yh test                        # 发现、构建并逐例执行
yh test <模块|源文件>           # 只跑该模块/文件
yh test --list                 # 只列出身份、位置与文档目标
yh test --no-run               # 只构建，不链接/不执行
yh test --emit-llvm            # 另写出 LLVM 文本供审阅
yh test --filter 子串           # 只运行身份含该子串的用例
yh test --timeout 15           # 单例超时秒数（1..3600，缺省 15）
```

- 测试体降低为模块内 `pub` 无参 `void` 函数，走普通 CheckedModule → SSA →
  LLVM 路径；每个模块生成入口模块 `yh_test_<mod>`，链接出测试二进制。
- `$assert(cond[, "消息"])` 在 test 体内是**运行期**检查：为假时向 fd 3 写
  `YHTF + 行 + 列 + 消息` 并 `exit(1)`；正常返回后入口写 `YHTP`；
  `libs/testing` 的 `fail`/`skip` 分别写 `YHTF`/`YHTS`。
- 父进程逐例 fork/exec，按「记录 + 退出码」判定：只有「退出码 0 且有 YHTP」
  算 PASS；提前 `exit(0)`、崩溃、超时、记录缺失或损坏一律 FAIL，且不阻断
  后续用例。失败输出断言位置与消息，汇总
  `结果: N passed; M skipped; K failed`。
- 只在 test 体内使用的 `import` 是测试依赖：生产构建不解析该依赖、也不报
  未使用导入。
- 生成物隔离在项目 `tmp/yh-test/`（含入口模块、对象与测试二进制）。

**标准库内建测试**：`libs/string/99_tests.yh` 5 条用例（视图比较、前后缀与
查找、无分配切分、拥有者增长、UTF-8 校验），入口 `make test-lib-tests`，已接入
`make test` 与 `make selfhost-native`。

## 标准库

- `os`/`sys` 完成跨平台拆分收口：共用文件 + `*.darwin.yh` 专属文件（目录、
  进程、时间、内存、errno/常量）；`os`/`sys` 各自新增 `.yh` 测试项目
  （`libs/os/test/`、`libs/sys/test/`）。
- 新增 `libc` 模块：内存、字符串、转换、排序，附 C 对照测试项目
  （`libs/libc/test/`）。
- `examples/` 清理为单文件示例。

## 其它变化（0.0.8 之后的累积）

- **string 标准库首期（ST0–ST6）**：只读 `View`、可增长 `String`、查找/切分/
  替换与 UTF-8 基础操作；保留旧的三个 NUL 结尾 C 接口。
- **TOML 1.1 reader 标准库**：独立 `Document`/只读 `Value` 模型，覆盖四种
  字符串、点键/引号键、隐式/显式表、数组表、四种日期时间与精确 binary64；
  通过固定 toml-test v2.2.0 的 1.1 清单 681/681。
- **cli 标准库 argparse 差分收尾**：自定义 usage 与模板、`version_text`、
  每层默认值预置、选项 remainder、`Result.warnings` 与 deprecated 警告。
- **LLVM 架构收口（LA0–LA3）**：函数/check 级缓存、受检快照与 lowering
  分层、会话接口就绪调度；`--stats` 覆盖计数。
- **自举链接闭包只强制桥整库加载**（`whole = ["bridge"]`），`yh` 体积
  73.7 MB → 70.6 MB。
- 编译器内置（prelude）函数登记迁入 `builtin` 模块；`examples/ex1` 补
  `return 0` 并登记缺 `return` 诊断缺陷；发布脚本上传后核对远端资产大小。

## 文档与规划

- yh test：设计提案、块执行模型、T0–T3b 分期与 7 份完成记录。
- 标准库：`fmt`、`math`、`memory` 设计与分期，字符串插值设计；
  编译器性能测试方案。
- `AGENTS.md`、`README`、`compiler/README.md` 同步 `yh test` 用法。

## 验证（本机 macOS/arm64）

- `make test`：ANTLR 与编译器语法正例 81/81、反例 49/49；运行语料
  run 211/212（1 条平台 SKIP）、fail 136/136、pass 9/9；
  `tests/modules/test-check.py` 27/27；string 内建测试 5/5；TOML API 6/6；
  代码统计 6/6。
- `make selfhost-native`：候选 cc3→cc4 的 30 个模块产物逐字节一致、
  cc4 自解析 114 个源文件、语法/运行语料、modules 19/19、project cases
  121/121、string 内建测试 5/5。

## 种子与自举顺序

- rc.N 用上一版 Release 的种子编译，因此 **0.0.9-rc.1 的 `compiler/` 不含
  test 块**：0.0.8 一代种子不认识 `test` 语法，若把测试写进编译器源码，
  种子冷编会失败。
- 本版发布出的种子开始支持 `test` 语法，**compiler 内嵌测试
  （`gen`/`lex`/`parse` + `make test-compiler-tests`）随 0.0.9-rc.2 交付**，
  届时 `git revert` 本版中的 “rc.1 暂缓 compiler 内嵌测试” 提交即可。

## 已知未完成

- YT3b（compiler 内嵌测试，随 rc.2）、YT2d（并行执行、逐例日志文件、测试
  缓存键隔离、超长断言消息提示）、YT1.1（项目外单文件临时单模块上下文）。
- 发布流程 R1–R4（分支模型、tag 祖先校验、rc 取种、版本漂移）仍未落地，
  本版按现有 `release.yml` 流程发布。
