# yh 编译期 typed 布局请求实施方案

日期：2026-10-06。状态：**首个竖切已完成**。递归调用扩展见[递归布局求值方案](yh-编译期typed递归布局求值方案.md)。

## 目标

让 typed `@[comptime]` 函数初始化的先行整数 `const` 可以作为后续结构体字段和
全局数组长度。pass1 遇到未就绪字段/全局数组长度时登记有限布局请求；typed 函数
捕获完成后，按源码顺序求值合格的全局整数常量，再补齐数组和结构体布局。

## 范围与约束

- 只延迟 pass1 类型中对单个、已声明整数 `const` 名称的引用，覆盖结构体字段和
  文件级变量数组；该常量初始化器须含至少一个非递归 `@[comptime]` 调用，函数可由
  已捕获的 typed 执行器求值。
- 普通字面量/算术 const 仍保持旧 pass1 可见性，不把任意 pass2 const 提升为布局常量。
- 保持全局常量声明顺序：请求只读取其数组字段声明前已就绪的 const；前向 const
  仍报“编译期常量尚未就绪”。
- 不制造长度 0：未就绪数组和结构体使用显式 pending 状态，任何 pending 类型都不得
  进入数据发射或运行期函数编译。
- 本片不接纳任意布局表达式、未声明常量、循环布局依赖、`sizeof` 对 pending 类型的
  查询或跨模块编译期函数正文；这些属于后续 CT5A/CT5B 阶段。
- 首片执行常量预备遍历时只处理调用图无环的未就绪整数 const，按文件/声明顺序解析；
  递归调用由[后续递归布局阶段](yh-编译期typed递归布局求值方案.md)改为按真实路径和执行预算处理。
  常量以外的全局初始化仍由既有 pass2a 完成。

## 架构

`parse_type_ref` 在 pass1 识别 `[NAME]T` 且 `NAME` 是已登记但未就绪的整数 const 时，
为数组创建显式 pending 类型并向 `comptime` 登记名称、类型和来源位置。结构体遇到
包含 pending 类型的字段时先保存字段，不运行 `sem_struct_finish`，并登记待完成的
结构体。单文件与模块编译都在 CT 函数 typed IR 捕获后执行未就绪整数 const 预备遍；
之后 `comptime` 求解器从 READY const 得到数组长度，按元素类型依赖完成数组大小，
再按内到外顺序完成结构体布局。正常全局初始化和函数编译仍在全部请求 READY 后运行。

求值器在捕获期间不执行 CT 函数；CT 函数如查询 pending 类型的 `sizeof` 必须得到
诊断，不能折叠成临时大小。暂不实现通用 UNSEEN/VISITING/READY 值依赖图，所以遇到
未就绪的前向值或本片不支持的布局依赖时安全报错；后续独立增加请求间依赖与环链路
诊断。布局求解只位于 `compiler/comptime/`，parse 层只识别请求并安排阶段调用。

## 实施与验收

1. 新增 run/108、run/114、run/116、run/117：覆盖分支局部值、实际路径返回、局部赋值
   与循环 CT 函数，并把结果用于字段、嵌套结构体、全局/局部数组长度；确认 run/117
   在实现前于字段长度处失败。
2. 新增 fail/118、fail/119、fail/120：保持前向 const、pending `sizeof` 和实际执行
   路径无返回时的拒绝。
3. 在 `compiler/comptime/ct_00_model.yh` 和新增 `ct_layout.yh` 建立 pending 数组/结构体
   状态、登记及布局完成过程；pending 状态使用非 READY 标记，不伪装成 0 长度。
4. 在 `compiler/parse/parse_type.yh` 与 `parse_decl.yh` 接入有限请求捕获；新增 parser
   预备遍历，只重解析尚未就绪且调用树无环的 CT 整数 const。
5. 在 `compiler/cmd/compile.yh` 与 `module_build.yh` 安排“CT 函数捕获 → 未就绪 const
   预备 → 布局求解 → 正常全局初始化”的阶段顺序。CT 求值期间 pending 布局的 `sizeof`
   明确失败。
6. 将旧 fail/108、fail/114、fail/116 按 typed 求值的新语义迁为 run/108、run/114、
   run/116，并保留 fail/112 递归环、fail/118 前向 const 与 fail/120 实际执行路径无返回。
7. 执行 `make test`、`make selfhost-native`、`git diff --check`；两道门全绿后 `make seed`
   并冷编 `make`。
8. 更新 `docs/03-design/` 编译期流程、数组长度方案、`docs/todo.md`、`docs/finish.md`、
   `tests/yh-run/README.md`，并新增本阶段完成记录。

## 成功标准

`run/117` 的布局数值与运行输出正确，typed 函数只在完整捕获后求值；首片暂拒绝递归调用树，
递归限制由[递归布局求值方案](yh-编译期typed递归布局求值方案.md)扩展；`fail/118` 保持前向 const 拒绝；所有 pending 类型在解析失败或求解结束前
不会用于发射；全量语料、自解析、模块/项目验收、固定点和种子冷编全绿。已验收：
运行语料 203/203、自解析 67 个源文件、固定点 14 个产物一致、模块语法 17/17、
项目 82/82；滚种子与冷构建结果见完成记录。
