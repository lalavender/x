# yh 编译器自身模块化方案（v2：按分类拆分多模块）

日期：2026-09-30。状态：历史 13 模块草案，已由按现有目录的方案取代。
依据：[模块与项目管理设计](../03-design/yh-模块与项目管理设计.md)、
[ADR-0006](../adr/0006-yh自举产物为主要开发编译器.md)。
当前执行顺序、真实目录模块与接口/种子验证门见
[编译器模块化详细实施方案](yh-编译器模块化详细方案.md)。
用户已经建立 cmd/gen/lex/parse 四个目录；本文保留此前分类思路和
工作量估计，不作为当前执行清单。`iface.yh` 尚不支持在公开签名
导出别的模块的具名类型，以下 13 模块切分也不能直接作为首步执行。

## 0. 与早期单模块草案的差异

此前讨论希望 compiler/ 按分类拆分为**多个模块**。单模块探针只证明
项目构建入口可行。按此分类继续细拆时，跨模块引用需限定名改写
（估算约 **3800 处**）；公开接口类型、模型状态和种子来源还需验证。
下文列出候选切分，不能把静态函数级解环等同于实际跨模块构建成功。

## 1. 依赖死结与解法（无环切分成立的前提）

早期函数级核查找到两处值得优先检查的跨层环；这不是全库
语义调用图的完备证明，跨模块构建还须验证类型、全局状态和接口：

| 环 | 解法 |
| --- | --- |
| sem（sem_compile 调 parse_source）↔ parser（钩子调 sem_*） | `sem_compile` 迁入 **driver** 模块（编译流水线本就是驱动侧职责）；sem 只留钩子 |
| iface（调 parse_source）↔ parser（调 mod_ns_lookup） | `mod_ns_lookup` 迁入 **sym**（纯表查询，只读 model.c_mods 与名字池） |

另确认：`sem_err`/`sem_can_assign`/`ty_is_float` 本就定义在 symbols.yh。
最终有向图仍须由真实 `yh build` 及接口导出验证；构建器 topo 可以
拒绝导入环，但不会提前证明公开类型均可表示。

## 2. 模块划分（13 模块，目录即分类）

mod.toml 位于 `compiler/`（`name = "yh/compiler"`，`source = "."`），
每模块一个子目录，文件保留序号前缀定模块内声明序：

| # | 模块 | 目录/文件 | 职责（分类） |
| --- | --- | --- | --- |
| 1 | model | model/01-model.yh | 数据模型：常量、结构体、全局状态（**全部 pub**，307 项） |
| 2 | base | base/01-buffer.yh | 诊断与字节 IO：err/fail/append/read_source/输出缓冲 |
| 3 | target | target/01-target.yh | 目标数据模型：布局、对齐、方言 |
| 4 | lexer | lexer/01-lexer.yh | 词法 |
| 5 | toml | toml/01-toml.yh | TOML 清单解析 |
| 6 | sym | sym/01-symbols.yh | 类型/符号/签名表、类型兼容、`mod_ns_lookup`（迁入） |
| 7 | emit | emit/01-emit_arm64.yh | AArch64 指令发射 |
| 8 | parser | parser/01-parse_type … 05-parse_module | 语法与限定名解析（5 文件互递归死结整体成模） |
| 9 | sem | sem/01-sem.yh | 语义钩子（sem_compile 迁出） |
| 10 | project | project/01-project.yh | 项目发现/索引/三层解析 |
| 11 | iface | iface/01-iface.yh | 接口发射与加载 |
| 12 | build | build/01-module_build.yh | 构建管线与对象缓存 |
| 13 | driver | driver/01-driver.yh + 02-compile.yh | CLI + 编译流水线（`sem_compile` 迁入） |

依赖方向（下层 → 上层引用）：model ← base ← {target, lexer, toml} ←
sym ← emit ← sem ← parser；parser ← project/iface；全部 ← build ← driver。
精确边由构建器 topo 校验。

## 3. 限定名改写（主要工作量，脚本化）

跨模块引用一律加模块前缀，实测规模：

| 类别 | 数量 |
| --- | --- |
| model 全局/常量（c_\*/t_\*/o_\*/np_\*/p_\*/mod_\*/lx_\*） | ~3025 |
| emit 原语（em_\*，sem+parser 内） | ~486 |
| sem 钩子（sem_\*，parser 内） | ~162 |
| sym 层（ty_\*/tg_\*/sym_\*/name_\*/scope_\*） | ~132 |

改写方式：按「模块 → 其 pub 符号清单」生成 sed 规则（`\b` 边界，仅
精确符号名，不做裸前缀通配），只施加于**定义模块之外**的文件；
模块内互引不加前缀。改写后逐模块 `yh build` 验证，链接期未定义符号
即漏标 pub 处（迁入期 pub 从宽：跨模块符号一律 pub，收缩留收尾）。

## 4. stage0 种子：旧扁平化器设想（当前不选）

多模块源码本身不能被 stage0 编译（冻结、无模块概念）。此前设想种子
由 `tools/flatten.py` 按序读入全部模块文件后生成：

1. 剥离 `module …;` 与 `import …;` 行；
2. 去限定：`\b(model|base|target|lexer|toml|sym|emit|parser|sem|project|iface|build|driver)\.` → 空
   （仅这 13 个命名空间前缀；yh 无同名局部变量，`p.x` 等成员访问不受影响）；
3. 按固定顺序拼接为 `tmp/compiler.yh` → stage0 → stage1。

该设想尚未证明字符串/注释、同名符号、跨模块私有与限定类型的
语义等价，也不能自然保证当前活跃语法仍由 stage0 支持。现行方案
改用冻结的无模块 seed 快照；此节只保留历史工作量估计。

## 5. 迁移阶段（自底向上，每阶段过四门）

以下 SB1–SB5 是此前草案的阶段分法，当前不作为执行清单。
实际阶段为 [CM-0–CM-5](yh-编译器模块化详细方案.md)，先完成
四模块稳定边界，再决定是否继续分类细拆。

| 阶段 | 内容 | 门 |
| --- | --- | --- |
| SB1 | 骨架：mod.toml + 目录 + 扁平化器 + model/base/target/lexer/toml 五模块拆出与改写 | 四门全绿 |
| SB2 | sym/emit 拆出（mod_ns_lookup 迁 sym） | 四门 |
| SB3 | parser（5 文件成模）+ sem（钩子）+ sem_compile→driver | 四门 |
| SB4 | project/iface/build/driver 成模 | 四门 + selfbuild |
| SB5 | 收尾：`make selfbuild` 默认化、旧清单删除、接口 pub 收缩（可选） | 全量语料 + 项目验收 21 |

若继续分类细拆，每阶段的改写只涉及当阶段拆出的模块，
但还须通过跨模块具名类型导出与实际构建，不以 diff 可审代替验收。

## 6. 收益与代价

收益：分类清晰（13 个目录即 13 类职责）；模块独立编译 + 对象缓存使
selfbuild 增量化；自家模块系统吃自己的狗粮（环/漏 pub/接口遗漏在构建期
暴露）；清单类故障根除。

代价（尚未接受）：约 3800 处机械限定名改写；model 约 307 项 pub
会扩大公开面；每次构建需加载多个接口文件。须在 CM-5 比较实际收益、
接口尺寸与构建耗时后决定是否继续。

## 7. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 改写脚本误伤（字符串/注释内标识符） | 仅精确符号清单 + `\b` 边界；诊断文案若被改写会立即体现在语料 diff，门可拦 |
| 局部变量与符号同名被误改写 | 改写清单逐符号审核；语料全量回归兜底 |
| 环切分错误 | 构建器 topo 拒绝环并报完整链，拆错即显式失败 |
| 扁平化器与模块源漂移 | 扁平化器是唯一种子来源（Makefile 调用），不存在第二份手工清单 |
