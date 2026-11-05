# yh 受检 → SSA → LLVM 能力矩阵（NP3）

修改时间：2026-11-06

性质：**实测能力登记**，不是设计目标。数据来源：
`tmp/np3/probe/` 下 30 个构造探针 + 5 个变体（共 35 个文件），用仓库根 `./yh`
（2026-10-28 构建）逐个 `./yh f.yh -o out` 编译、成功则运行并核对退出码。
**探针只用于量「哪些形态真的会被拒」，不是门禁**；通过项中值得长期锁定的
已合并进 `tests/yh-run/run/208-lowering-coverage-matrix.yh`。

## 1. 为什么要有这份表

NP3 的验收要求「新路径覆盖自编所需全部能力」。此前只有零散注释判断覆盖，
实测发现两处注释已失真（`ast_ir_build.yh` 与 `module_snapshot_lower_flow.yh`
都写着「不支持嵌套循环」，实际循环栈早已支持）。本表把结论落成可复算的清单：
**每个构造 → 结论 → 拒绝时的诊断出口**，改动 lowering 后重跑探针即可复检。

## 2. 结论总览

实测 35 个探针文件：首轮 **28 通过 / 7 被拒**，归并为 4 个构造缺口（G1–G4）。
2026-10-28 当日**全部修复**：G1（`*fn` 取址 → `alloca ptr`）、G2（聚合三目）、
G3（浮点全局）、G4（bool 控制 switch），另加 G1b（`&函数名`）与 G2b（三目结果
成员访问）。当前**零被拒**：探针矩阵 33 构造 + 5 变体全过（O0/O2）。

| 类别 | 状态 |
| --- | --- |
| 语句/控制流（if、switch 含 bool 控制、for、for-in、goto、label、break、continue） | 全部通过 |
| 聚合（字面量、按值传参/返回、字段/下标/调用/三目来源初始化与赋值、三目结果成员访问） | 全部通过 |
| 切片（字面量、视图、返回、含切片字段的结构体、三目视图） | 全部通过 |
| 指针/内存（`&` 标量/浮点/字段链/函数名、`**`、指针算术、`*fn` 绑定） | 全部通过 |
| 转换（整数窄化、浮点互转、指针） | 全部通过 |
| 调用（9 参数、变参 yh 函数、聚合混合、函数指针字段、`&函数名` 传参） | 全部通过 |
| 全局（`let` 结构体、切片、f32/f64 标量与浮点元素数组；`const` 聚合） | 全部通过 |

## 3. 已通过的构造（回归已锁进 run/208–212）

| 构造 | 探针 | 说明 |
| --- | --- | --- |
| `let p Pair = f()` / `= o.field` / `= arr[i]` | p04–p06 | 聚合初始化来源除三目外都成立 |
| `p = f()` / `= o.field` / `= arr[i]`；`b.p = a`、`arr[0] = a` | p08, p09, p27 | 聚合赋值同样覆盖字段/元素目标 |
| 嵌套 `for-in` + 内层 `break` + 外层 `continue` | p16 | 循环栈按 `CheckedLoop` 逐层 |
| 同一循环多 `break`/`continue` 站点 | p29 | 携带值 phi 正确 |
| 二维数组字面量 `[[1,2],[3,4]]` | p17 | 嵌套聚合字面量 |
| 含切片字段的结构体字面量 | p18 | 切片后备数组在调用点分配 |
| 聚合按值传参 + 聚合返回 + 嵌套调用 | p19 | |
| 9 参数直接调用 | p20 | |
| `&o.inner.a` 字段链取址写回 | p21 | |
| 返回切片字面量（逃逸存储） | p22 | |
| `enum` 作 switch 控制与 case 值 | p23 | |
| 前向 `goto`、后向 `goto` 成环、循环内 `goto` 跳出 | p24, p30 | |
| 转换矩阵（i64→u8 截断、f64↔int、指针转换） | p25 | |
| `union` 字面量与共享存储 | p26 | |
| 短路副作用与全局计数（`&&` 链中调用） | p28, p31, p32 | 求值顺序与可见性正确 |
| 浮点绑定取址、指针变量取址（`**int`） | p01, p03 | |
| 顶层 `let` 结构体/切片全局 | p11, p12 | |
| 用户变参函数（yh ABI vararg） | p14 | |
| 聚合三目（let/赋值/返回/字段/数组元素/切片视图） | p07, p07b, p07c | 两分支写同一目标存储 |
| 聚合三目结果直接取字段/下标 | p33 | 先物化临时槽再取址 |
| `&函数名`、`&函数名` 作实参、先声明后赋 `&函数名` | p32, v2 | 物化 8 字节函数值槽 |
| `switch` 的 bool 控制与 bool case 值（含 default、循环内） | p15, v5, p31 | `icmp eq i8` 相等比较 |
| 浮点全局：f64/f32 初始化、零初始化、复合赋值、位模式、浮点元素数组 | p13, p13b, v4 | 见 §4 G3 |

## 4. 曾经的缺口与修复对照（G1–G4 + G1b/G2b，全部已关闭）

| # | 构造 | 探针 | 诊断 | 出口 |
| --- | --- | --- | --- | --- |
| ~~G1~~ | ~~`let p *fn(int, int) int = &f`~~ | p02 | **已修复**：`alloca void` → `alloca ptr` | `backend/llvm_scalar.yh` 的 `IR_OP_ADDR` 发射 |
| ~~G2~~ | ~~`let p Pair = c ? a : b`（聚合三目初始化）~~ | p07 | **已修复**：两分支各写同一目标存储并建 CFG（不建 phi） | `lower/module_snapshot_lower_aggregate.yh` 的 `checked_lower_aggregate_store` |
| ~~G1b~~ | ~~`let p *fn(...) = &add`（函数名取址）~~ | v2, p32 | **已修复**：物化 8 字节槽写入函数地址再返回槽地址 | `lower/module_snapshot_lower_expr.yh` 的 `checked_lower_address_of` |
| ~~G2b~~ | ~~`(c ? a : b).y`（三目结果成员访问）~~ | p33 | **已修复**：聚合三目先物化到临时槽再取址 | `lower/module_snapshot_lower_place.yh` 的 `checked_lower_lvalue_ptr` |
| ~~G3~~ | ~~`let GF f64 = 1.5` / `let GF f32`~~ | p13, v4 | **2026-10-28 已修复**：浮点全局（含 f32 元素数组）可编译且值正确 | `backend/llvm_module.yh` 的 `llvm_preflight` + `parse/parse_global_static.yh` |
| ~~G4~~ | ~~`switch b { case true { … } }`（控制为 `bool`）~~ | p15, v5, p31 | **已修复**：控制与 case 值都接受 bool，走 `icmp eq i8` 的相等比较 | `lower/module_snapshot_lower_flow.yh` 的控制/case 类型检查 |

### G2 根因与修复（2026-10-28）

聚合没有 SSA 值，`checked_lower_aggregate_store` 原本只认字面量/变量/字段/下标/
解引用/调用六种来源，遇到 `AST_EXPR_TERNARY` 落到 `-2`。修复后两分支各自把
聚合写入同一目标存储，给 cond 建 then/else/join 三块并在 join 继续，**不建 phi、
不复制 `local_values`**（聚合分支不可能赋值外层绑定，没有需要合流的 SSA 值）。
好处是所有调用点自动受益：`let` 初始化、同型赋值、聚合返回、结构体字段/数组元素
初始化、切片视图三目。

**G2b（同日补齐）**：三目结果直接做成员/下标访问（`(c ? a : b).y`）需要先把聚合物化
到临时槽再取址。`checked_lower_lvalue_ptr` 新增 `AST_EXPR_TERNARY`/`AST_EXPR_CTIF`
分支：按聚合大小与对齐发 ALLOCA，把选中分支写进去，再按普通左值走字段/下标偏移。
临时槽由后端统一提到入口块（I4-7），循环内不会随迭代增长（30 万次迭代探针通过）。

### G3 根因与修复（2026-10-28）

两处独立缺陷叠在一起：

1. `backend/llvm_module.yh` 的 `llvm_preflight` 直接按符号类型拒绝 `IR_TY_F32/F64`
   全局（「尚不支持浮点全局」）。全局对象本来就按原始字节发射（`llvm_globals`），
   这条拒绝是多余的；删除后 f64 全局立即可用。
2. f32 全局读回 0：常量浮点在所有折叠路径都以**双精度位模式**保存
   （`gen.fp64_norm_bits`），而 `parse/parse_global_static.yh` 的
   `parse_global_static_scalar` 按目标宽度直接写字节，4 字节对象只截到 f64 低 4
   字节（2.5 → 0）。修复：写静态标量前按目标类型窄化一次（共用新增的
   `gen.fp32_bits`，`comptime/ct_ir_float.yh` 的同一实现改成调用它，避免两份分叉）。
   顺带解除了 `parse_global_init.yh` 里「f32 元素的全局初始化暂不支持」的限制——
   该限制只是同一缺陷的保守守卫。

回归 `tests/yh-run/run/211-float-globals.yh`（f64/f32 初始化、零初始化、复合赋值、
位模式断言、浮点元素数组全局），O0/O2 均通过。

### G1b 根因与修复（2026-10-28）

`&函数名` 曾落到全局对象分支，报出与事实无关的「全局对象缺少受检数据」。
函数值本身已是不透明指针，但 `&f` 的语义要求「一个真实内存对象」：修复后分配
8 字节对齐槽、写入 `FN_ADDR`、返回槽地址。IR verifier 对「元素为 VOID 的指针
存放函数值」本来就有例外规则（`IR_OP_STORE`/`IR_OP_LOAD` 的 FN_PTR 分支），
所以不需要新的 IR 形式。

### G4 根因与修复（2026-10-28）

控制值本来就用 `IR_OP_EQ` 逐个比较，bool 与整数同构；拒绝只是类型检查写成了
`ir_integer_type`。修复后控制与 case 值都接受 `IR_TY_BOOL`（LLVM 侧是
`icmp eq i8`）。回归 `tests/yh-run/run/212-switch-bool-control.yh`。

### G1 根因与修复（2026-10-28）

canonical `IR_TY_PTR`（*void）与函数值共用同一编码，其 `elem` 规范编号是
`IR_TY_VOID`。`checked_lower_pointer_kind` 对 `IR_TY_FN_PTR` 返回 `IR_TY_PTR`，
因此「函数指针绑定的存储地址」是一条 `result_type = IR_TY_PTR` 的 `IR_OP_ADDR`；
`backend/llvm_scalar.yh` 的 ADDR 发射直接照抄元素类型，于是写出
`alloca void, align 1`，被 LLVM 拒绝。

修复：ADDR 发射遇到 `VOID` 元素（不透明指针值的槽）时按指针宽度发
`alloca ptr, align 8`，不再照抄元素种类。回归
`tests/yh-run/run/209-fnptr-address.yh`（含 D1 的 goto 形态）。

`docs/todo.md` 的 **D1** 原本把它记成「含 `goto`/`label` 的函数里函数指针绑定」；
实测 **不需要 goto**（`let p *fn(int, int) int = &f` 即可复现），D1 已随本修复关闭。

`&函数名` 起初落到全局对象分支，报出与事实无关的「全局对象缺少受检数据」；
先改成可操作诊断，随后按 G1b 真正实现（见上表），诊断用例已删除。

## 5. 复算方法

探针源留在 `tmp/np3/probe/`（`./run.sh` 逐个编译 + 运行，3 秒超时）——`tmp/`
不入门禁、可能被清理，需要复检时按 §3/§4 的表格重建同名探针即可。

探针**不入门禁**：通过项已固化进 `tests/yh-run/run/208-lowering-coverage-matrix.yh`；
各修复的回归：`209-fnptr-address.yh`（G1 + G1b）、
`210-ternary-aggregate-lowering.yh`（G2 + G2b）、`211-float-globals.yh`（G3）、
`212-switch-bool-control.yh`（G4）。原先的两个 `fail/` 用例（169/170）在能力补上后
已删除，改为上述 `run/` 用例。

## 6. 与 NP3 范围的对应

- 覆盖项（§6.4 的「嵌套循环、for-in、switch/goto、指针/内存、转换、聚合、
  浮点与各类调用」）**已全部成立**：G1–G4、G1b、G2b 当日修复，矩阵零被拒。
- §6.3 的「预检与构造分离」按现状**不再有价值**：矩阵已经没有可达的
  `UNSUPPORTED` 形态，剩下的 `-2` 出口都是防御性分支（快照行号越界、绑定布局
  不一致、导入聚合缺字节等），属于内部错误而不是「源码形态不支持」。再加一趟
  预检扫查只会产生永不触发的死代码，与「不做投机性代码」冲突；若将来引入新的
  不支持形态，先补探针再决定是否需要预检。
- §6.1/§6.2 的契约独立性：受检事实经 `ast.CheckedStorage` 快照传递，`ir` 不向上
  依赖（无 import）；剩余耦合是共享类型/符号模型仍在 `gen`（`gen` 分层属另一
  议题，2026-10-28 决定不做）。
- §6.5「受支持函数只走一次受检 → SSA → 后端」：旧机器发射已在 LL12 删除，
  `--backend legacy` 直接拒绝，不存在第二条发射路径。
