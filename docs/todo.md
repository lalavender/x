# todo

## yh 0.0.1 执行清单

本文件只追踪任务状态；具体改动位置、测试样例与阶段出口见
[改造方案](02-plan/yh-0.0.1-改造方案.md) §6。数组按值的语言承诺见
[ADR-0001](adr/0001-yh数组按值调用边界.md)。阶段顺序为
M0 → M1 → M2 → M3 → M4 → M5 → M6；前一阶段的验证门未通过时，
不把后一阶段标为完成。完成一项后勾选，并把实际命令和结果写入
`docs/finish.md`；代码任务每次都新增对应 `.yh` 用例并运行 `make`。

**当前基线**：Darwin 本机默认产出 Mach-O（`yh f.yh -o prog` 本机可执行）；`-sysroot`/`-Wl,-oformat=elf64-aarch64` 交叉 AArch64 Linux ELF。`make` 仍构建 TCC；`make test` 在 Darwin 只运行旧 pp
测试；`tests/yh` 的 65 个正例、29 个反例是 ANTLR 语法语料，
不是 yh 编译器已通过的测试。用例数量随新增文件变化，验收时按实际
发现的全部用例计数。

### M0：前置验证与语义定案

- [x] **M0-01 基线与依赖图**：记录当前 `make`、`make test`、
  `python3 tests/yh/check.py --coverage` 的结果；列出驱动、解析器、
  值栈、后端和链接路径的实际调用关系。证据放 `tmp/m0/`。
- [x] **M0-02 Linux 工具链与链接**：在 AArch64 Linux 验证独立 C
  工具链、sysroot/libc/crt/动态加载器、`lib/lib-arm64.c` 归档和
  最终 ELF 链接、运行；记录 Darwin 跨系统 `-o` 所需路径与缺失诊断。
- [x] **M0-03 数组与切片 ABI 探针**：在 `tmp/abi/` 比较包装结构体
  与调用点拷贝后传隐式指针，覆盖 ADR-0001 的大小、HFA、参数/返回、
  寄存器耗尽、递归及大数组矩阵；另测 16 字节切片。选定机制并新建
  实现 ADR，不把 C 代理探针当成 yh 运行测试。
- [x] **M0-04 语义边界**：在 `docs/03-design/` 确定前向调用、
  `main`/`pub`、字符串可写性、零长度数组、切片边界/生命周期、
  裸 C 变参提升；同步修正 `docs/yh.g4` 的 prelude 注释。
  保持已确定的末尾唯一类型化变参和 for-in 局部值拷贝规则。

**M0 验证门**：Linux ELF 链接/运行与 ABI 探针有可复现记录；
所有会阻塞代码生成的选择写入设计文档/ADR。失败项先修订方案。

### M1：构建、驱动与词法

- [x] **M1-01 构建与输入分派**：`make` 产出 `yh`、
  `libtcc.a`、`libtcc1.a`；用户源文件仅识别 `.yh`，
  运行时 C 文件由独立目标 C 工具链构建。新增驱动正反例并构建。
- [x] **M1-02 yh 词法**：同步保留字、`to_type`、RANGE/
  ELLIPSIS、数字下划线、转义、空白和预处理符拒绝规则；
  为每类规则新增 `tests/yh` 的 `.yh` 正反例。
- [x] **M1-03 纯语法入口**：接通 `yh --syntax-check file.yh`
  的词法/语法入口，消费到 EOF，不因未定义名字或缺少 `main` 报错；
  用最小正例和词法反例验证。

**M1 验证门**：构建可重复；词法用例按预期接受/拒绝；
ANTLR 原有语法回归仍通过。

### M2：完整纯语法与双模式回归

- [x] **M2-01 类型与声明**：实现 typeRef、别名、变量/常量、
  函数、struct/union/enum 与 pub 的语法；用相关 `.yh`
  正反例验证，不在语法模式查名字或常量值。
- [x] **M2-02 表达式**：实现优先级、调用/下标/成员、
  `.to_type(typeRef)`、structInit、`sizeof(T)`、`len(e)`；
  验证后缀链，并拒绝旧 `as` 写法。
- [x] **M2-03 语句**：实现 if/for/switch、赋值、label/goto
  与块，验证 structInit/块边界；语法模式接受语义错误但形态合法的表达式。
- [x] **M2-04 编译器语法回归**：给 `tests/yh/check.py` 增加
  `--compiler` 模式，遍历所有语法正反例并与 ANTLR 模式分别计数；
  确认解析消费到 EOF。

**M2 验证门**：两种语法检查模式对实际发现的全部语料通过；
不得把语法通过等同于编译或运行通过。

### M3：基本语义与可执行闭环

- [x] **M3-01 名称与内置符号**：实现作用域、const 值、
  pub ELF 绑定、M0 决定的前向调用规则和 8 个 prelude extern Sym；
  以 `.yh` 编译正反例及 `readelf -sW` 验证。
- [x] **M3-02 类型转换与表达式**：按改造方案 §4.1 先检查 yh
  隐式/显式转换，再调用 TCC 后端；覆盖数值、bool、指针、
  `.to_type(T)` 结果为右值及赋值/传参/返回的拒绝规则。
- [x] **M3-03 语句、初始化与输出**：完成函数体、变量、
  structInit、控制流、switch、goto、`-o` 和 `-run`；
  Linux 上运行 hello 并核对 ELF 机器类型、加载器和符号。

**M3 验证门**：Linux 标量程序的 `-o`、`-run` 结果一致；
非法语义被编译模式拒绝，纯语法模式仍按语法判断。

### M4：聚合值、遍历与变参

- [x] **M4-01 数组按值调用**：按新实现 ADR 落地数组参数和返回，
  用真实 `.yh` 用例逐行覆盖 ADR-0001 的拷贝、HFA、栈参数、
  递归和大数组矩阵；不同长度实参编译拒绝。
- [x] **M4-02 切片与 for-in**：规范化 `[]T`，实现 len、
  下标、数组转切片视图及数组/切片/区间遍历；验证绑定作用域、
  值拷贝、空范围、continue/break 与转换拒绝。
- [x] **M4-03 类型化与裸变参**：末尾唯一类型化变参打包为临时切片；
  零参数和求值顺序有运行测试。裸 C 变参只用于内置 prelude，
  Linux 上验证默认提升、寄存器/栈边界与非法用户声明。

**M4 验证门**：ADR-0001 和改造方案 §5 的每项行为都由
`tests/yh-run/` 的编译、拒绝或 AArch64 Linux 运行用例验证。

### M5：完整测试与交付

- [x] **M5-01 回归集成**：建立 `tests/yh-run/check.py`，
  `make test` 分别报告语法、编译、拒绝和运行结果；
  Darwin 运行项显示 SKIP 原因，Linux 完整回归通过。
- [x] **M5-02 安装与文档**：核对 build/install/uninstall、
  VERSION、README 和 `docs/03-design/`；从干净构建执行
  `make clean && make && make test`，Linux 再验 `-o`/`-run`
  与 `readelf`。

**M5 验证门**：交付清单全部通过，跳过项不计为通过。

### M6：代码清理

- [x] **M6-01 清理旧 C parser**：只删除实际无调用的 C 解析代码
  和本次改动产生的孤立声明；比较清理前后的构建、完整回归和
  Linux 运行矩阵，并在 `docs/finish.md` 记录结果。

**M6 验证门**：清理前后结果一致，未证实无调用的代码不纳入本次删除。

## 0.0.2+ 待设计事项（不阻塞 0.0.1）

### yh 自举

自举定义、能力边界、源码组织、阶段任务与验证门统一见
[yh 语法与编译器自举统一方案](02-plan/yh-自举实施方案-v2.md)。

- [x] B0：定位当前 `make test` 的 goto/递归失败，冻结可靠 stage0 和差分测试口径
  （缺口矩阵见[运行覆盖缺口矩阵](02-plan/yh-运行覆盖缺口矩阵.md)）。
- [x] B1：增加 `read`（推荐同时增加 `close`）及带 `argc/argv` 的 `main` 语义；用 `.yh` 运行用例验证。
- [x] B2：验证编译器工作负载所需的类型、指针、递归、ABI 和容量边界，修复实际发现的问题。
- [x] B3：建立 `compiler/` 源码拼接与驱动，完成 yh 词法器和字节输入探针
  （拼接清单在 Makefile `SELFHOST_SOURCES`；1 MiB、NUL、未终结串等边界
  探针见 `docs/finish.md`；源码目录按用户指示用 `compiler/` 替代方案的 `src/yh/`）。
- [x] B4：完成 yh 纯语法解析器，解析自身并通过全部语法语料（G1）。
  stage0 交叉编译 stage1（AArch64 Linux ELF），容器内自解析拼接源码到
  EOF，`tests/yh/check.py --compiler --compiler-path tests/yh/container-yh.sh`
  差分 66/66 正例、29/29 反例；验证入口 `make bootstrap`。
  已知偏差：自编源码用 `for 1 { }` 替代无限 `for { }`——stage0 的
  continue 在无条件 for 内不识别为循环内（探针 `tmp/probe-continue.yh`），
  待单独修 stage0 后可改回。
- [x] B5：完成语义检查与编译器自身所用子集的 AArch64 Linux 汇编输出。
  分层：前端语义（symbols/sem/parse_*）→ 目标数据模型（target.yh）→
  指令发射（emit_arm64.yh）；`--emit-asm` 产出 GNU 汇编，经容器 gcc
  `-no-pie` 链接为 ELF。运行语料 40/44（余 4 项为 B7 边界：按值聚合、
  数组按值、浮点/类型化变参，均显式拒绝并有 `fail/` 或 `run/25..29`
  用例钉住）。架构与换平台契约见
  [自举后端架构](03-design/yh-自举后端架构.md)。
- [x] B6：执行 stage0→stage1→stage2→stage3 的自身子集闭环（G2）。
  `make bootstrap` 逐门验证：拼接确定性、G1（自解析 + 66/66 + 29/29）、
  G2（stage1 编译自身得 stage2；stage2 自解析、语法差分 66/29、
  运行子集 25/25）、G2+（stage2 编译自身得 stage3，stage2.s 与
  stage3.s 逐字节相同，stage3 自解析）。**G2 达成**。
- [x] B7：补齐现有 yh 全语言语义与运行覆盖。
  已实现：聚合按值（参数/返回/嵌套字面量）、切片（视图/len/下标/实参）、
  for-in（数组/切片/区间）、类型化变参、浮点 f32/f64（传参/返回/运算/
  转换）、structInit 作值。**stage1 全量通过**：语法 66/66+29/29、
  运行全量通过。
  **自举缺陷已修复**：stage2 浮点字面量常量编码错误（根因：`sem_push_arg`
  对浮点实参压 x0 而非 d0）与连带的整数窄化转换缺失（`sem_cast` 缺
  「整数→整数」分支）。修复后 stage2 浮点常量正确、**stage2.s 与 stage3.s
  逐字节一致（全量固定点）**，`make bootstrap` 恢复全量运行语料与全量
  固定点比较。定位手段：新增本机自举差分探针 `make selfhost-native`
  （`tests/selfhost/native-selfhost.py`，无需容器）。详见
  [自举后端架构](03-design/yh-自举后端架构.md) §6。
  **仍未实现**：全局聚合变量初始化。
- [ ] B8：固定三代构建、逐字节汇编比较与干净环境复验（G3）。
  前置条件已达成：stage2.s 与 stage3.s 对自身拼接源码逐字节一致
  （本机探针验证）；`make bootstrap` 的 G2+ 固定点比较已恢复为全量。

- [ ] 多平台后端支持（linux/darwin/windows × arm64/x64，共 6 目标）：
  现状梳理、差距矩阵、分阶段方案与决策点见
  [多平台架构整理与优化方案](02-plan/yh-多平台架构整理与优化方案.md)；
  阶段 0（目标抽象与构建矩阵化）到阶段 4（windows/arm64）均不阻塞 0.0.1。
- [ ] 数组与切片字面量。
- [ ] 切片表达式 `arr[0..2]`。
- [ ] 函数内嵌套 struct/enum 声明。
- [ ] `sizeof(expr)`。
