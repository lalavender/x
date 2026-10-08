# 编译期过程收尾方案（CT1/CT2 去重解析 + 顶层聚合实参）

日期：2026-10-07。状态：待实施。承接 CT1/CT2「typed AST 收尾」与 `fail/148` 顶层聚合实参。

## 本轮实测到的入口结构（先看事实，别凭印象动手）

单文件入口 `compiler/cmd/compile.yh`：

| 行 | 动作 |
| --- | --- |
| 27–42 | 保存 `c_ast_capture`，置 1，跑 `parse_source_ct_fns()` 捕获编译期函数正文，再恢复 |
| 45 | `parse_source_ct_layout_register()`：登记需要延迟求值的 token 区间 |
| 47–71 | **固定点循环**：每轮重新调 `parse_source_ct_layout_consts()` / `parse_source_ct_layout_exprs()`，按 pending 计数下降收敛；不降则报「卡住」诊断 |
| 72 | `ct_layout_resolve()` |
| 76 | `ct_enum_pending_run()`：延迟的枚举判别值（此时 CT 正文已捕获） |

模块入口 `compiler/cmd/module_worker.yh`：15 行 `c_ast_capture = 0`、55 行置 1、
157 行 `ct_layout_resolve()`、159 行 `ct_enum_pending_run()` —— 与单文件同构。
另见 `compiler/cmd/module_build.yh:1021` 的 `c_ast_capture = 0`。

**「逐轮重解析」就是 47–71 的固定点循环**：每轮把 `ct_layout_*` 里登记的全部表达式重解析一遍，
而不是只处理尚未就绪的那些。第 26 轮夹逼出的「同一段正文被解析两次」就是这套机制的副作用。

## 第 31 轮实测修正（推翻本方案初版的两条判断）

**① 「去重解析」没有可去的东西 —— 初版判断错误，撤销该子项。**

`parse_source_ct_layout_exprs()`（`compiler/parse/parse_ct_layout.yh:337`）**已经**跳过已就绪项：

```yh
for row < comptime.ct_layout_request_count() {
    if (comptime.ct_layout_expr_pending(row) == 0
        || comptime.ct_layout_expr_file(row) != gs.c_active_file) {
        row += 1;
        continue;
    }
    ...
    if (p_ct_layout_expr_runnable(first, after) != 0) { ... 解析并 set_length ... }
}
```

即：不可运行的项每轮只做计数判断（`ct_layout_expr_pending` / `p_ct_layout_expr_runnable`），
可运行的项**一次就会成功**并置为不再 pending。所以固定点循环里**每个请求最多被真正解析一次**，
没有「白跑的重解析」。剩下的 O(轮数 × 请求数) 只是计数扫描，且 `pending == 0` 时函数开头
直接返回（339 行）。**结论：这条不值得改，撤销。**

**② 「统一入口」的三处现状各有差异，不是简单重复。**

`parse_source_ct_fns()` 的三个调用点：

| 调用点 | 流程 |
| --- | --- |
| `compiler/cmd/compile.yh:37` | 单文件完整流程：捕获正文 → `ct_layout_register` → 固定点循环 → `ct_layout_resolve` → `ct_enum_pending_run` |
| `compiler/cmd/module_build.yh:943` | 模块构建侧的捕获（其余在 `module_worker.yh` 157/159） |
| `compiler/parse/iface_ct.yh:1023` | **加载 `.s.ct` 接口**：先 `c_iface_load` 折叠隐藏常量、抑制数据段发射，捕获正文后还要逐个公开 CT 符号校验「公开声明与 `.s.ct` 正文签名一致」 |

第三处不是同一段代码的复制，而是「读接口」这条路独有的预处理与校验。**「统一入口」因此不应
理解为抽一个共用函数**，而是要逐条确认 check-only / build / SSA 各自**缺哪一步**（例如 check-only
是否真的走到了 `ct_layout_resolve`）。这一步需要先做**调用图普查**，不是直接重构。

## 差距（todo 里的原话，注意上面两条修正）

> 剩余工作是移除逐轮重解析并统一单文件、check/build/SSA 所有入口。

拆成两件事，互相独立：

1. **去重解析**：固定点循环只重解析「本轮尚未就绪」的表达式。
2. **统一入口**：让 check-only / build / SSA 三条路径共用同一套捕获 + 求解流程
   （现在 check-only 走 `c_check_only` 分支，模块侧另有 worker）。

## 下一步的真实第一步（已由第 31 轮实测替换）

原「先插桩量化白跑占比」作废（已实测无白跑）。改为：

1. **调用图普查**：列出 check-only（`c_check_only`）、build、SSA 三条路径各自实际执行的
   编译期步骤（捕获正文 / 布局登记 / 固定点 / resolve / enum pending），指出谁缺哪一步 ——
   这是「统一入口」唯一可执行的前置工作。
2. **优先做有用户价值的一项**：顶层聚合常量（CT3 最小切片）。它同时解掉 `fail/148` 的两个
   问题：`const P Point = Point{ x: 1 };` 本身不支持、以及顶层聚合实参没有中转写法。
   范围限定为「字段全是标量的结构体字面量」；第一步是看 CT 执行器的**实参绑定路径**如何取值，
   判断能否把字段字面量折叠成标量序列存进一处「聚合常量池」，供 `$take(P)` 这类符号实参复用。

## 初版第一步（已作废，留档说明为何不这样做）

不要直接动循环控制流 —— 先量化：

1. ~~在 `parse_source_ct_layout_exprs()` 里插桩统计每轮重解析条数~~（**作废**：第 31 轮读代码
   已确认它跳过已就绪项，没有白跑；见上文修正 ①）。
2. 用一个延迟表达式较多的语料（`tests/modules/projects/comptimecross` 加若干
   `pub const X int = $f(延迟值);`）跑一遍，看第二轮起的重解析有多少是白跑。
3. 若白跑占比显著（预期如此），把该函数改成「跳过已就绪项」，用同一语料验证轮数与
   pending 下降曲线不变；否则保持现状并在本文件记录实测数据。

验收标准：语料输出逐字节不变、`make test` 与 `make selfhost-native` 全绿、
固定点（两代自编产物 `.s`/`.s.i` 逐字节相同）保持。

## 顶层聚合实参：第 31 轮的可行性实测（决定它比看上去大）

读代码确认了两条路径的分工：

- **编译期函数体内**的调用：实参由 typed IR 捕获，执行器用 `ct_ir_args_fill`
  （`compiler/comptime/ct_ir.yh:254`）「按源码顺序把实参链求值并写入调用数组」，聚合对象在执行器
  的 arena 里分配 —— 所以正文里能构造聚合。
- **顶层/普通函数里**的调用：实参由**前端直接求值**成 `args [64]gen.Res`
  （`compiler/parse/parse_expr.yh:953`），`Res` 只有 `ival` / `sym` / `is_const` 一类标量字段，
  **没有聚合值的表示**。

所以真修必须先给「常量聚合值」找一处表示（前端 `Res` 携带，或一处独立的聚合常量池），
再让 `ct_ir_args_fill` 在按符号取实参时认出它。**这是跨前端与执行器的改动，约 2–3 轮，
不适合塞进一次收尾**；也解释了为什么 `gen/state.yh:150` 预留下的 `c_arg_agg` 至今没有使用点。

**下轮第一步（明确）**：先给「只含标量字段的结构体字面量」的顶层聚合常量设计最小表示
（首选：独立全局聚合常量池，复用执行器已有的 `CtAggregate` 形状，避免动 `gen.Res` 的布局），
用一个 `const P Point = Point{ x: 1 };` 的最小用例驱动，跑通后再接顶层聚合实参。

## 第 38 轮普查结论：「统一入口」没有功能缺口，撤销该子项

按上一节定下的第一步做了调用图普查，结论与预期相反 —— **不需要统一**：

| 检查项 | 事实 | 位置 |
| --- | --- | --- |
| check-only 是否跳过编译期步骤 | **不跳过**：`c_check_only` 只抑制后端缓冲 | `gen/buffer.yh:245/311/368`、`module_worker.yh:204/224/227` |
| 模块 worker 的步骤顺序 | 与单文件**一致**：pass3 布局登记 → 固定点循环 → `ct_layout_resolve()` → `ct_enum_pending_run()` → pass1 | `module_worker.yh:121-168` |
| 固定点循环是否同构 | 同构：`mb_pass2_file(...,4)` + `parse_source_ct_layout_exprs()` + `ct_layout_advance()`，含同样的 stuck 诊断分派 | `module_worker.yh:128-156` |
| 模块侧的布局常量求值 | 存在 | `module_build.yh:947` |
| `iface_ct.yh:1023` | 读 `.s.ct` 接口的另一条路（多 `c_iface_load` 隐藏常量折叠与公开 CT 签名校验），本就不该合并 | — |

剩下的只有**代码重复**，属纯重构、无功能收益 —— 为此改动主流程不划算，**撤销**。
（第 30 轮把这条写成「同构双份」过于简化，第 31 轮修正过一次，本轮才算查清。）

## 第 38 轮顺带实测：剩下那些条目的真实边界

- **联合体实参不适用**：`union` 不是 yh 关键字，写 `pub union Val { ... }` 直接报「此处需要一个类型」
  —— 源码里根本构造不出联合体字面量，所以「联合体实参」不是待办而是不存在。
- **切片实参的难点已定位**：`ct_registry.yh:472` 要求切片实参是「有效的本地数组或切片视图」
  （`ct_ir_slice_param_valid`），即地址必须落在某个**存活调用帧**的槽区间内；顶层实参临时构造区
  造出的元素区不在任何帧里，且切片是「地址 + 长度」两个量、`CtValue` 单 i64 装不下
  —— 要做必须先设计顶层切片的视图表示。
- **`*dst = *src;` 的已知缺陷表现变了**：从「段错误」变成「静默算错」（实测得 230，应为 0），
  编译链接都成功；编译期路径暂时走不到同一处（`@[comptime]` 不支持结构体指针形参）。

## 顶层聚合实参（`fail/148`）

现状：`const R int = $take(Point{ x: 1 });` 被 `parse_expr.yh`（调用点不在 CT 函数体内、
形参是聚合、实参是聚合字面量）**显式拒绝**。原因是实参必须在 pass1 折叠成常量，而聚合字面量
做不到；`const P Point = Point{ x: 1 };` 也不支持（「const 不支持聚合类型」），所以**没有中转写法**。

本轮已把该诊断改成可操作的表述（明确指出走不通 + 只能在 `@[comptime]` 函数体内构造），
并同步更新 `tests/yh-run/fail/148-comptime-top-aggregate-arg.yh` 的注释。

真修有两条路，按代价排序：

1. **聚合常量（CT3 切片）**：先支持「只含标量字段的结构体字面量」的顶层 `const`。这需要一处
   存放聚合常量值的表示（现有符号只存 `cval i64`）。做成之后 `fail/148` 的中转写法自然可用，
   顶层聚合实参也可以按「先折叠成聚合常量再传符号」处理。
2. **顶层捕获通道**：给顶层编译期调用合成一个 CT 帧。体量接近 CT1/CT2 的「统一入口」，
   不建议单独做。

注意 `gen/state.yh:150` 已有 `c_arg_agg *int`（「每个实参是否为聚合」，256 项）字段，
但全仓只有 `symbols.yh` 的分配与空指针检查引用它 —— 是预留字段，不是可用通道。
按「不删非本轮引入的死代码」原则保留，仅在此记录。

## 影响的既有结论

- 枚举成员在模块模式下的问题（第 26 轮定位、第 29 轮修好）走的是**成员表 + 执行器侧兜底**，
  属于「兼容二次解析」的 workaround；若将来去掉重解析，这层兜底可以保留（无害）或清理。
- 所有编译期行为改动都必须配 `.yh` 用例并跑 `make` / `make selfhost-native`。
