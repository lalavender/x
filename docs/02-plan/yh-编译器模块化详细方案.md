# yh 编译器按现有目录模块化实施方案

> **已被实施取代**：P0–P5 已完成（2026-09-30）。文中 mod.toml、`entry = "cmd"`、
> 冻结无模块 seed、`bootstrap/`、四代 stage 链与 `make g3` 均已随 0.0.3 终结。
> 现行设计见 [编译器源码模块化设计](../03-design/yh-编译器源码模块化设计.md)。
日期：2026-09-30。状态：设计与执行清单；本轮未修改正式编译器源码。

本方案以用户已经建立的 compiler/cmd、compiler/gen、compiler/lex、
compiler/parse 四个目录为边界。它们是源码分类的既定选择；真正的 yh
模块还需要每个源文件的 module 声明、文件级 import、可导出的接口和
可运行的 compiler/mod.toml。模块语言规则沿用
[现行设计](../03-design/yh-模块与项目管理设计.md)，架构判断见
[源码模块化设计](../03-design/yh-编译器源码模块化设计.md)。

## 1. 当前状态和成功标准

当前 13 个文件已经移动到四个目录，另有 model.yh、buffer.yh、
symbols.yh、iface.yh 仍在 compiler 根目录。17 文件共 13,004 行；
移动后的文件与原 Git 内容逐字节相同。compiler/mod.toml 是空文件，
源文件还没有 module/import 声明。因此“按目录放置”尚未成为 yh 模块。

Makefile 和 tests/selfhost/native-selfhost.py 仍引用原路径；
make -n yh-new 目前报找不到 compiler/lexer.yh。实施的第一门必须先
恢复现有构建，不把目录移动误记为已完成模块化。

成功标准：

1. make 重新通过，旧单文件 CLI 与语料行为不变。
2. 在 compiler 目录执行项目 build，四个目录分别形成 gen、lex、
   parse、cmd 模块，入口为 cmd；每模块独立生成 .s 与 .s.i。
3. 活跃编译器从这个项目构建；stage0 只编译冻结的无模块 seed。
4. 自举链对活跃项目冷编到 stage4，stage2→stage3 与 stage3→stage4
   生成的全部模块 .s/.s.i 相同。
5. 每次正式代码修改新增 tests/ 下的 .yh 用例并运行构建、相关测试。
   容器正式门未执行时必须明示，不以本机结果替代。

## 2. 目录、模块名和依赖方向

目标不再是上一版的 engine/project/build/main，也不是按每个文件
建立 13 个模块。保留用户的四个目录：

~~~text
compiler/
  mod.toml                 [project] source = ".", entry = "cmd"
  gen/                     module gen：数据、符号、语义、目标与发射
    00-model.yh            从根目录移入；类型声明和共享状态先于使用者
    buffer.yh              从根目录移入
    symbols.yh             从根目录移入
    target.yh
    emit_arm64.yh
    sem-*.yh               从现有 sem.yh 按函数边界拆分
  lex/                     module lex：词法扫描
    lexer.yh
  parse/                   module parse：语法、模块头与接口处理
    parse_type.yh
    parse_expr.yh
    parse_stmt.yh
    parse_decl*.yh
    parse_module.yh
    iface.yh               从根目录移入
  cmd/                     module cmd：项目管理、模块编译与 CLI
    toml.yh
    project*.yh
    module_build.yh
    compile.yh             原 sem_compile 的编排入口
    driver.yh
~~~

清单示意：

~~~toml
[project]
name = "yh/compiler"
source = "."
entry = "cmd"
~~~

用户源文件唯一为 .yh；每个文件都显式写 module gen/lex/parse/cmd。
目录名本身不自动赋予模块身份。真正使用别的模块的文件才写 import，
并使用限定名；同模块文件之间不 import。import 仍按“当前项目 →
标准库 → 第三方”查找，编译器本项目内的四个名字先绑定本地模块。

以“被上层依赖”为方向，依赖层级为 gen → lex → parse → cmd。
精确导入边：

| 导入者 | 可导入模块 | 原因 |
| --- | --- | --- |
| gen | 无 | 持有类型、状态、语义和发射，不回调解析/命令 |
| lex | gen | 读取源字节与 token 表，报告词法错误 |
| parse | gen、lex | 解析与接口装载需要模型、语义及重新词法化 |
| cmd | gen、lex、parse | 驱动旧 CLI、项目索引与模块编译 |

cmd 是入口，其他模块不能导入 cmd。四目录真实构建的模块图必须与
上表一致；如果实际 import 出现反边，先调整函数所有权，不循环加
pub 或放宽构建器的环检查。

## 3. 解环所需的最小函数迁移

按当前函数调用扫描，以下三处反向调用是目录成模前的前置工作。
它们只移动函数或更名，并保持行为；不要顺手改语义。

| 现有位置 | 调用关系 | 目标位置 |
| --- | --- | --- |
| gen/sem.yh 尾部 sem_compile | gen 调 parse_source 等三个 parse 入口 | cmd/compile.yh；编排属于 cmd |
| parse/parse_type.yh 的 err_tok | symbols.yh 的 sem_err 等要调用它 | gen/buffer.yh；只读 gen 自有 token 位置 |
| cmd/toml.yh 的 tml_intern_str | parse_decl 与 iface 也调用它 | gen/symbols.yh 的通用名字池辅助函数；cmd/parse 改用新名字 |

另把根目录 iface.yh 放入 parse：它调用 mod_parse_head、parse_source、
lex_all，而 parse 也要使用其中的模块命名空间查询。留在独立 iface
模块会形成互相导入。把 model/buffer/symbols 放进 gen 使 Res、Tok、
类型表、汇编缓冲及使用它们的公开函数同属一个模块。

这是源码调用的近似审查，尚未证明接口均可导出。P2 小项目探针和
P3 实际构建是裁决依据。若出现其他反边，记录具体函数及原因后只移动
那一处，不预先大规模重构。

## 4. 公开接口与状态约束

gen 拥有 Tok、Res、CType、CSym、项目索引结构和现有全局状态。
lex/parse/cmd 现阶段仍会访问这些状态；只给**确实被别的模块使用**
的类型、字段、常量、函数和变量加 pub，并记录谁使用它。不要对
model.yh 全文件机械添加 pub。文件名拆分不改变状态所有权。

现有 iface.yh 只能在公开签名中输出“本模块自有的具名类型”。
四目录方案让 Tok/Res 等归 gen，因此 gen 的公开语义函数可以引用
gen.Res；parse 对 cmd 公开的编排入口尽量使用内建类型和 gen 之外
不暴露的私有辅助函数。若探针发现 parse 的公开签名必须含 gen.Res，
先缩小入口或调整所有权，再决定是否扩展 .s.i 格式；不能让接口加载
依赖消费者项目中的同名模块。

每个模块仍在独立子进程编译一次，当前可变全局状态的生命周期由
子进程限定。暂不引入万能 CompilerContext；在接口真实编译通过后，
再评估 gen 暴露的可变状态是否值得收束为显式请求/结果。

## 5. 其余文件的精确拆分计划

只对明显过长或职责混杂的文件拆分，均在**原目录的同一模块**内进行。
以下行号是当前文件的函数边界参考，不允许按行号直接截断函数；
移动时连同详细中文注释，按模块文件加载顺序检查声明可见性。

| 当前文件 | 建议拆分 | 理由和验收 |
| --- | --- | --- |
| gen/sem.yh，2403 行 | sem_value（原 1–369：字面量/值）、sem_expr（370–1030：运算/索引/转换）、sem_call_literal（1031–1511：调用/返回/字面量）、sem_flow（1512–2084：迭代/赋值/标签）、sem_decl（2085–2359：函数/字段/main）；尾部 sem_compile 移 cmd/compile.yh | 每文件约 275–661 行，按完整函数分段；调用 ABI、聚合、浮点和控制流运行例全过 |
| cmd/project.yh，1390 行 | project_state（原 1–494：路径、项目/模块表）、project_index（495–904：清单装载与源文件索引）、project_resolve（905–1390：导入绑定、拓扑、list 与根发现） | 每文件约 410–486 行；本地/标准库遮蔽、歧义、导入环、list 输出一致 |
| parse/parse_decl.yh，1215 行 | parse_decl（原 1–247 加 798–1215：顶层与本地/类型声明）、parse_global_init（248–797：全局数组/结构体初始化） | 约 665/550 行；正反语法、重复声明、全局初始化结果一致 |
| gen/emit_arm64.yh，1014 行 | 暂保留；超过建议上限仅 14 行。若未来继续增长，再沿 521 行前后完整函数边界分离发射原语与浮点/调用/数据段 | 避免为达行数而产生许多短小的浅文件；汇编逐字节回归 |
| gen/symbols.yh，981 行；parse/parse_expr.yh，913 行；cmd/module_build.yh，868 行 | 本轮不拆 | 长度处于建议范围，跨模块迁移已带来足够风险 |

“尽量 500–1000 行”不是凑行数要求：sem_decl 等较短文件按完整职责
成立即可。项目内文件顺序必须确定；至少 gen 的模型声明先于使用者。
拆分每一个大文件后运行对应 .yh 用例和构建，避免一次性迁移多个热点。

## 6. 自举种子与项目位置

C stage0 冻结，不能直接编译含 module/import 的活跃源码。先从当前
无模块 17 文件制作只读 seed 快照，例如仓库级 bootstrap/seed/，
放在 compiler/source = "." 的扫描范围**之外**。快照保留原有拼接
顺序，Makefile 与 native-selfhost.py 共用一份源清单；所有生成的
拼接文件和缓存只在 tmp/。当前已移动的 13 个文件与旧 Git 内容相同，
因此可从当前目录布局取快照，但须记录文件 hash 和排序。

不采用“正则剥离 module/import/限定名再拼接”的方案作为唯一种子：
它无法可靠保证字符串、注释、同名符号和模块私有语义等价。活跃源码
日后超出 seed 的语言能力时，单独升级 seed，并保留旧版可回退构建链。

正式链：

~~~text
C stage0 → 冻结 seed 编译器 stage1
         → 活跃四模块项目 stage2
         → 同一项目 stage3
         → 同一项目 stage4
~~~

每代冷编或使用独立 tmp/bootstrap/genN 缓存。比较 stage2→stage3
与 stage3→stage4 所产每个模块的 .s 和 .s.i；不能共用当前不含编译器
二进制身份的缓存键，也不能继续用旧单文件 stage2.s == stage3.s
声称新项目达到了固定点。

## 7. 分阶段执行与验证门

| 阶段 | 允许的正式改动 | 阶段出口 |
| --- | --- | --- |
| P0 恢复构建 | 只更新 Makefile、native-selfhost.py、compiler/README.md 的当前 17 路径；保留无 module 的现有源码 | make、make test、make selfhost-native 重新通过；新增 .yh 回归用例 |
| P1 冻结 seed | 制作并校验快照、统一来源；把活跃项目和种子构建路径分开 | stage0→seed 成功，seed 能构建已有模块项目；hash 受控 |
| P2 接口探针 | tests/modules/ 加四目录最小项目：gen 公有 Res/Tok/变量，lex 和 parse 使用它，cmd 为入口 | .s/.s.i 独立生成、链接运行；私有字段和错误接口干净拒绝 |
| P3 真正成模 | 填好 compiler/mod.toml、补 module/import、迁移根目录四文件、移动三处解环函数、必要的限定名改写 | 从 compiler/ 执行 build 成功，模块图无环，旧 CLI 与项目 21 例通过 |
| P4 拆热点文件 | 按 §5 分别拆 sem、project、parse_decl；一次只拆一个文件簇 | 每簇新增 .yh 用例，汇编/行为不变，make 与 native 门通过 |
| P5 自举验收 | 更新 make/bootstrap/g3 的项目代次和归档；日常 yh-new 改由活跃项目生成 | 四代冷编固定点、各代语料与模块项目全绿；正式 G3 实际运行后才勾选 |

P0 是修复用户已移动目录后的当前构建中断；P3 才是真模块迁移。
P2 不通过就先修具体接口限制，不对 17 个源码文件批量改写。
任何阶段引入的临时编译产物只放 tmp/，文档状态写入 docs/todo.md；
实际命令与结果写入 docs/finish.md 和 docs/01-finished/。

## 8. 验收命令与失败处理

- make：主二进制来源明确；P0 后就应恢复通过。
- make test：stage0 种子语料；不能代替自举侧语料。
- make selfhost-native：本机自举、语法、运行、模块与项目用例。
- make g3：容器正式门，环境不可用则记录未运行。
- 从 compiler/ 运行 seed 编译器的 build/list，核对 gen、lex、parse、
  cmd 的提供方、拓扑、缓存冷/热行为与入口。
- git diff --check；检查正式改动没有覆盖用户已有的未提交移动。

所有代码阶段遵循 AGENTS.md：结构体与函数保留详细中文注释；
每次修改新增 tests/ 下 .yh 用例并在构建后验证。若某阶段失败，
保留可工作的 seed/上一代产物，修复同一阶段后重新过门，不把
未通过的后续阶段标完成。

本轮交付的是基于当前目录布局的方案，不把已有目录移动、空清单
或旧探针误记为四模块构建完成。
