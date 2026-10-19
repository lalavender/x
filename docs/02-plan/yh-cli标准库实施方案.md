# yh cli 标准库实施方案

日期：2026-10-18。状态：**CLI0–CLI6 已完成（2026-10-19）**。
CLI0 的探针与结论见[完成记录](../01-finished/yh-cli0语言能力与ABI基线-2026-10-19.md)。

目标：在 `libs/cli/` 实现接近 argparse 完整能力的命令行标准库。
API、默认值、歧义和生命周期以[设计文档](../03-design/yh-cli标准库设计.md)为准。
本次不修改编译器、不添加空模块、不迁移既有命令行入口、不滚种子。

## 1. 共用规则

1. 每个行为切片先在 `tests/` 添加 `.yh` 用例，明确输入、值形状、诊断和退出期望。
2. 实现所需最小改动，公开结构体和函数使用中文注释说明单位、结果和所有权。
3. 修改代码后执行 `make` 及针对性用例；临时产物放 `tmp/cli/`。
4. 每阶段完成后同步设计、标准库 API、todo 和 finish，不能以设计表代替实测状态。
5. 以 Linux 运行验证为先，沿用仓库当前种子、构建和容器规则；不依赖 macOS 种子补齐。

开发前重新检查工作区和当前分支的构建规则。2026-10-18 已有 finish 记录指出 Darwin
种子与 LLVM 分支存在差距，不能假设在 macOS 执行 make 就能验证当前编译器。
遇到既有环境阻塞应单独记录，不扩大 cli 的实现范围。

## 2. 阶段任务

### CLI0：语言能力和 ABI 基线（已完成，2026-10-19）

- 增加 `libs/cli/test/climodel/`，用普通 `.yh` 验证 tagged union、递归列表、
  跨模块结构体和切片返回、函数类型回调、user 指针和公开薄句柄。
- 真实运行回调和结果读写，不以仅通过语法检查作为 ABI 证据。
- 检查已登记标准库模块与实际导入路径，确定分配和 I/O 的当前可用依赖。
- 如果需要修编译器，先登记最小缺陷与复现，独立修复后再继续，不为 cli 直接引入新语法。

验证：Linux 真实执行探针通过；无未声明的语言前置条件。

结果：探针在 darwin-arm64 与 Linux 门禁（build-check）上通过；
修复「枚举成员名被同名形参遮蔽」的名称解析缺陷（`compiler/gen/state.yh`、
`compiler/parse/parse_expr.yh`），语料 `tests/yh-run/run/204-enum-member-shadowed.yh`；
结论与语言边界（裸堆指针不可切片、union 载荷不可递归、跨模块枚举项写法）
见完成记录。

### CLI1：最小可用命令行（已完成，2026-10-19）

- 创建 `libs/cli/`，在 `libs/project.toml` 登记模块，保持实现类型私有。
- 实现 config/argument 构造、注册、冻结、原子失败、destroy、基础 Value 与 Namespace。
- 实现长短名称、别名、单值位置/选项、store/const/bool/help/version 和严格 parse。
- 实现 Result、类型化查询、release、基础 usage/help、render 和 argc/argv 适配。
- 实现 parse_main_or_exit 的输出、释放和 0/1/2 退出契约。
- 新增 clibasics 项目并接入 `tests/modules/build-check.py` 的标准库验收。

验证：设计中的 pack 示例可运行；空输入、帮助、缺值、未知选项、文本所有权均有断言。

结果（2026-10-19）：`libs/cli/{cli,schema,values,parse,help,entry}.yh` 交付并登记；
`libs/cli/test/clibasics` 的 `--selftest` 覆盖默认值、const、count、
类型转换、`--`、帮助、错误诊断、重复解析隔离与「结果晚于 parser 销毁」；
`libs/cli/test/run.py` 与 4 个进程级断言（成功/帮助/缺位置的三条
退出码路径）。CLI2 的范围（完整 arity、append/extend、choices、短组合与缩写）
在 freeze 或解析时明确拒绝，见
[完成记录](../01-finished/yh-cli1最小可用命令行-2026-10-19.md)。

### CLI2：完整内置参数行为（已完成，2026-10-19）

- 实现完整 arity、多值分配、后续最低数量保留、remainder 和普通模式位置分段。
- 实现 append/append_const/extend/count/boolean_optional 和 count 溢出。
- 实现 i64/u64/f64/bool 转换、choices、默认值/const、suppress 和类型查询错误。
- 实现等号、附着值、短组合、负数特判、可选缩写和多义错误。
- 实现显式出现记录、共享 dest 类型检查、重复解析隔离；新增 cliactions 项目。

验证：设计第 8/9 节矩阵全通过，exactly(1) 与 single 的值形状明确不同。

结果（2026-10-19）：`libs/cli/{convert,write}.yh` 从 parse 拆出；`cliactions`
的 11 个主题覆盖形状、位置多值、分段、remainder、append 家族与批次列表、
boolean_optional、choices、短组合/负数、缩写、默认值与查询错误码、共享 dest 校验。
`custom`、converter/validator、组与子命令、解析模式、参数文件、完整帮助
按 CLI3–CLI5 继续，见[完成记录](../01-finished/yh-cli2完整内置参数行为-2026-10-19.md)。

### CLI3：组合、子命令与解析模式（已完成，2026-10-19）

- 实现子命令槽、嵌套/别名/必需命令和规范 command_path。
- 实现 inherit 深复制、组内默认值/冲突策略、展示组与互斥组。
- 实现 resolve 的部分名称保留、停用声明和稳定 ID。
- 实现 parse_known、intermixed 及两者组合，拒绝不支持的声明组合。
- 实现独立 Namespace、initial 快照、父子默认值合成与事件顺序归并。
- 新增 clicommands 项目，包含“根显式值 + 子默认值”和全局 parent 的真实组合。

验证：子命令作用域、四模式行为、互斥显式出现、未知短组合原子性及快照隔离全部通过。

结果（2026-10-19）：新增 `libs/cli/{commands,layer}.yh`；`clicommands` 的 9 个主题覆盖
子命令/别名/命令路径、父子默认值、必需命令、inherit 深复制、展示组与组级 resolve、
互斥组、known、intermixed 与 initial。已知边界（槽位置固定、混合模式同 dest 拒绝、
initial 形状检查留 CLI4）见
[完成记录](../01-finished/yh-cli3组合子命令与解析模式-2026-10-19.md)。

### CLI4：扩展与参数文件（已完成，2026-10-19）

- 实现 converter/validator/custom action、上下文分配、结果类型检查及命名注册表。
- 实现自定义前缀和参数文件展开、逐行回调、嵌套相对路径、来源和包含链。
- 实现文件深度/累计字节/token 数限制，所有成功失败路径关闭文件并释放存储。
- 新增 cliextensions 项目和分配失败注入；注入设施限测试使用，不成为产品配置项。

验证：自定义类型和 action 实际执行；坏回调形状被拒绝；参数文件循环、超限和 I/O 失败可定位。

结果（2026-10-19）：新增 `libs/cli/{extensions,files}.yh`；`cliextensions` 的 14 个主题
覆盖 converter/validator/custom action、命名注册表、坏声明拒绝与参数文件
（展开、嵌套、循环、I/O 失败、深度与 token 上限、逐行回调、子 parser 限制）。
本版本把展开上限收敛为 4096 token / 单行 4096 字节 / 默认 1 MiB，
分配入口先提供 `context_text`；见
[完成记录](../01-finished/yh-cli4扩展与参数文件-2026-10-19.md)。

### CLI5：完整帮助与诊断体验（已完成，2026-10-19）

- 实现 HelpFormat 配置组合、默认值、metavar 列表、模板和隐藏参数。
- 实现 deprecated、有限建议、颜色及终端检测失败时的无色降级。
- 实现超长帮助、控制字节转义、非法 UTF-8 展示和输出失败行为。
- 新增 clihelp 项目及稳定无色快照；检查 stdout/stderr 和帮助前后错误的优先级。

验证：语义输出、颜色策略与退出码均有实际进程断言；不通过全局字符串删除来隐藏快照差异。

结果（2026-10-19）：`help.yh` 重写并新增 `HelpFormat`/`Color`/`metavars`/`deprecated`；
`render(result, out_fd, error_fd)`、`exit_code`、`print_usage`/`print_help` 落地；
`libs/os` 增加 `is_terminal` 供自动颜色检测；`clihelp` 的 7 个主题覆盖布局、默认值/
deprecated、metavar 与互斥 usage、颜色与降级、建议、转义与输出 API。`warnings`
通道与逐字段着色留待后续；见
[完成记录](../01-finished/yh-cli5完整帮助与诊断体验-2026-10-19.md)。

### CLI6：统一验收和文档冻结（已完成，2026-10-19）

- 逐项核对设计能力表；已实现项有运行用例，明确替代项保留理由。
- 对与 Python 3.14 一致的子集做值/诊断类别/退出码差分；差异项使用 yh 专属期望。
- 执行 Linux 全门，检查公开导出面、重复解析、分配失败和结果独立生命周期。
- 将已实现 API 同步到标准库主文档，新增 `libs/cli/README.md` 和完成报告。
- 保留工具链现有参数行为，不在本阶段自动迁移 compiler/cmd、asm 或 link。

验证：CLI0–CLI5 用例与全门通过，todo 只移除实际完成项。

结果（2026-10-19）：能力表逐项核对、argparse 差分文档、导出面清单、README 与
标准库主文档同步完成；6 个验收项目由 `libs/cli/test/run.py` 的 9 条用例覆盖
（用例已从全局 build-check 迁出，不与其耦合），`make selfhost-native` 全绿、
全局 project cases 104/104；既有 compiler/cmd、asm、link 参数行为未动。
见[完成记录](../01-finished/yh-cli6统一验收与文档冻结-2026-10-19.md)。

## 3. 门禁和证据

代码阶段按仓库现有入口执行：

```sh
make
make test
make selfhost-native
git diff --check
```

若触及 LLVM 实现，按当前分支追加 `make test-llvm`、`make selfhost-llvm` 等已有要求。
针对性项目用例接入已有 runner，不在文档中伪造尚不存在的独立测试命令。
Python 只作开发期对照，库运行不需要 Python。

使用 Linux 容器时，遵守 AGENTS 的 Apple container 方案和挂载约束；
在 `docs/finish.md` 记录镜像、架构、命令、通过数量及未验证项。
容器中不覆盖入库种子；滚种子仍须单独满足仓库全绿要求，不属于本方案默认步骤。

## 4. 本次文档交付的验证范围

本次仅检查 Markdown 结构、链接、差异和设计一致性，不宣称已运行 cli 编译或语义测试。
不添加依赖未实现 cli 模块的失败 `.yh` 用例；源码和运行测试随对应实施切片一起加入。
