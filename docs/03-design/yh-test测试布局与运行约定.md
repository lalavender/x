# yh test 测试布局与运行约定

修改时间：2026-11-06

本文把 `yh test` 的落盘布局、文件命名、平台选择、并发与门禁职责固定下来，
供新增标准库/新增测试时直接照做。迁移背景与阶段见
[YT4 分析与规划](../02-plan/yh-test语法迁移既有测试分析与规划-2026-10-25.md)。

## 1. 测试放在哪里

- 每个标准库的测试放在自己的目录：**文件后缀必须是 `.test.yh`**（VTEST，
  2026-11-05：`.test.yh` 是测试文件的唯一标识，`zz_`/`99_` 排序前缀废止）；
  不集中到统一大套件（2026-10-25 决策 D8）。
- `just test-libs` 的缺测试提示匹配 `*.test.yh`。
- 单文件 `yh test path/to/file.yh` 已支持（YT1.1），用临时单模块项目，
  不装入相邻文件。
- 外部 runner 只承担 `yh test` 表达不了的职责：外部语料一致性、参考实现
  差分、失败注入、安装/仓库外、交叉/平台矩阵、产物与性能（决策 D16）。

## 2. 文件命名与顺序

模块内的声明按文件名字典序处理，但**编译器扫描保证 `*.test.yh` 一律排在
非测试文件之后**（`pj_dir_less`，2026-11-05 起）——测试体引用生产声明不
依赖文件名字典序，文件名只说明内容。

| 库的形态 | 新建测试文件名 |
| --- | --- |
| 任意库（整库一个测试文件） | `tests.test.yh` |
| 按主题拆分（如 cli） | `<主题>.test.yh`（`actions.test.yh`、`basics.test.yh`、`commands.test.yh`…） |

历史命名（`zz_tests*.yh`、`99_tests*.yh`）已于 2026-11-05 全部迁移为
`.test.yh` 后缀并去除排序前缀。

单个测试文件控制在 500–1000 行；超出按主题拆分为 `<主题>.test.yh`。

## 3. 平台差异

- 平台差异只通过**编译期文件选择**表达：`tests.test.linux.yh`、
  `tests.test.darwin.yh`（以及 `*.linux.arm64.yh` 等既有后缀）；扫描器对
  `.test.yh` 前的 `test` 段按普通文件名放行，OS/架构段照常筛选。
- 不给 `test` 块新增 `// platform:` 注释语义，也不在 runner 里写
  `if darwin/linux` 分支。
- 需要 `-target` 的交叉类型检查（例如用 Darwin 编译器检查 Linux 目标源码）
  不属于 `yh test`：留在 Linux job 或独立 target。

## 4. 断言、粒度与可见性

- 断言统一用 `$assert(cond[, "消息"])`；消息用中文、说明“期望是什么”。
- 每例 5–20 条断言：同一段 setup（解析同一份输入、构造同一组对象）放在
  同一个 `test`；用例名写行为，不写编号。
- 迁移阶段只调用 `pub` 名字，保证“迁移不降覆盖、可逐条对照”；
  确需覆盖内部边界时另开 `test "内部: …"` 并注明原因（决策 D7）。
- 测试体不能声明局部函数；`tests.test.yh` 里的 helper 是模块私有普通 `fn`，
  生产构建会编译但不进 `.s.i`，数量要控制。

## 5. 文件类测试的资源约定

- 照 `libs/io/tests.test.yh`：`/tmp` 下按用例名区分的固定路径，逐例自建自清。
- 逐例是独立进程（`YH_TEST_JOBS` 默认 4，最大 8），并行时路径不能撞。
- 沙箱可能拦截建目录/批量删除；失败时给出可操作提示，不静默跳过。
- 宿主没有可写 `/tmp` 时退回项目 `tmp/` 下的用例目录。

## 6. 并发与缓存

- 测试构建目录：`<项目根>/tmp/yh-test/check`；入口源码
  `tmp/yh-test/gen/<入口模块>/entry.yh`；测试二进制 `tmp/yh-test/bin/`；
  逐例日志 `tmp/yh-test/log/`。
- 同一项目的两个 `yh test` 会共享上述路径。自 2026-10-25（YT2d-3）起，
  `yh test` 在 `tmp/yh-test/.lock` 上用 `O_CREAT|O_EXCL` 建锁并写入 pid，
  **同项目运行串行化**；持有者已退出时按 pid + `kill(pid, 0)` 清理陈旧锁，
  等待上限约 30 秒。
- 不同项目、不同项目副本互不影响；O2 重跑使用 `tmp/libs-o2` 项目副本，
  从而拥有独立的 `tmp/yh-test` 缓存与锁，不冲刷 O0 的增量缓存。
- 已知限制：函数级 IR/check 切片缓存仍不用于测试构建（YT2d-2 剩余），
  修改一个 `test` 会重编整个模块。

## 7. 门禁职责

| 门 | 内容 | 平台 |
| --- | --- | --- |
| `just test` | 语法/运行语料 + 模块 test-check + **无选择器** `yh test`（O0）+ 编译器测试 + TOML/JSON/fmt 外部门 | 本平台 |
| `just selfhost-native` | 两代固定点 + 自解析 + 语料 + 项目验收 + 无选择器 `yh test`（O0） | 本平台 |
| `just test-libs` | 全部标准库：缺测试提示 + `yh test`（O0/O2）+ cli/os/libc runner + TOML/string/num/fmt 专项与安装后导入 | Linux/Darwin CI 同一目标 |

- `just test-libs` 是标准库测试唯一入口；旧 `libs-test`/`libs-test-o2`/`test-lib-tests` 已删除。
- 缺 `*.test.yh` 的库只打印提示（决策 D9），不阻断。
- CI 的 darwin-arm64 / linux-arm64 / linux-x86_64 三个 job 各自调用同一个
  `just test-libs`；O2 已包含在目标内，不再按平台追加。
