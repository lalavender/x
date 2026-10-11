# yh 编译期 CT6 实施方案（表达式选择 → 类型分派/动态字段）

> 状态：**实施中（2026-10-09）**。语法与范围定稿见
> [CT6 语法设计](../03-design/yh-编译期CT6语法设计.md)（用户已确认：
> 表达式选择候选 A、条件导入不做、类型分派候选 A、动态字段与 CT4 合并先只读）。
> 按 AGENTS「修改语法规则」流程（g4 → 方案 → 用例 → 实现 → 文档）推进；
> 首版仅单文件，`.s.ct` 跨模块闭包序列化延后。

## P0 表达式选择 `$if (cond) e1 $else e2`（已实施 2026-10-09）

### 语法（docs/yh.g4）

`expr` 链最上层新增 `comptimeIfExpr`，`$else` 必须书写：

```antlr
expr
    : comptimeIfExpr
    | conditionalExpr
    ;

comptimeIfExpr
    : '$' 'if' '(' expr ')' expr '$' 'else' expr
    ;
```

无歧义论证：语句形态 `$if (…) '{' … '}'` 在 `)` 之后要求块，表达式形态要求
`expr`（不可从 `{` 开始），单 token lookahead 即可区分；`$else` 就近匹配
（与 C 的 else-if 链同理）。`$if` 表达式位于链最上层，作二元操作数需加括号
（`v + ($if …)`），由 g4 结构决定。

### 解析（compiler/parse/parse_expr.yh）

- `parse_expr` 入口对 `$` + `if` 分派到新函数 `parse_ct_if_expr`；capture 模式
  与三元同等处理 `ast_expr_parse_depth` 与语句表达式挂载（子表达式以 depth>0
  解析，不会误挂「语句表达式根边」——首版曾因此让 return 执行器取到条件值）。
- `parse_ct_if_expr` 流程：
  - 条件：普通路径在 `c_fold+1` + `c_ct_target_ctx=1` 下折叠求值，必须为
    编译期常量（非常量由折叠路径报「变量不是编译期常量」，与语句形态一致）；
    typed 路径不要求常量（可用参数/局部值，执行器按编译期值选支）。
  - 分支：普通路径选中分支正常检查与发码，未选分支以 `c_em_suppress` 静默
    发射但**保留完整语义检查**（合流需要两侧类型），且不捕获 AST；typed 路径
    两分支都正常解析并捕获。
  - `$else` 必须书写（缺省报「$if 表达式必须写 $else」）。
  - 合流 `ct_if_merge_type`：两支类型相等 → 该类型；字面量分支经
    `sem_can_assign` 的 is_lit 路径向另一分支类型窄化/加宽；其余报
    「$if 表达式两个分支的类型不一致」。结果类型 = 合流类型。
- 语句位置诊断（parse_comptime.yh）：语句 `$if` 的分支不是 `{` 时给出
  「语句位置的 $if 后需要块；表达式形态的 $if (…) e1 $else e2 只能出现在
  表达式位置」。

### AST 与 typed IR

- 新表达式种类 `AST_EXPR_CTIF = 14`（ast_expr.yh，kind 校验放宽到 14）；
  节点携带 cond/then/else 三个子节点与合流类型。
- ct_ir.yh：`ct_ir_support_code` 放行 kind 14；`ct_ir_eval_expr` 的
  kind 4/14 共用执行（求条件值 → 只求值选中分支），kind 14 分支另做字面量
  类型归一（`out.type_id` 收敛到合流类型）。

### 用例与验收

- tests/yh-run/run/168（普通路径：let/实参/return/嵌套/变量分支/折叠）、
  run/169（typed 路径：cond 用参数、i64 合流、嵌套、未选分支检查）、
  run/170（顶层 const 折叠与全局数组初始化）。
- tests/yh-run/fail/154（缺 `$else`）、155（两分支类型不一致）、
  156（普通路径 cond 非常量）、157（语句位置表达式形态）。
- tests/yh/positive/71-comptime-if-expr.yh（ANTLR + 编译器语法模式正例）、
  tests/yh/rejected/30_comptime_if_expr_missing_else.yh（反例）。
- 门禁：`make test`（三层）、`make selfhost-native`（主门）、
  `tests/modules/build-check.py`。

### 已知边界（首版）

- 仅单文件；`.s.ct` 跨模块闭包正文里的 `$if` 表达式序列化延后（与既有
  `$if` 语句相同的 token 范围处理，正文格式确认后补）。
- 合流按类型相等（D2）：结构相同但类型名不同的聚合值合流不在首版。
- 运行期 SSA lowering（ast_ir_lower_expr）尚不支持 kind 14，遇到含
  `$if` 表达式的普通函数自动回落既有后端（旧后端不受影响）。

## P1a 类型分派谓词 `$is_type` / `$is_int` / `$is_float`（已实施 2026-10-09）

### 语法（docs/yh.g4）

`comptimeCall` 增加独立备选（`$is_type` 的第二实参是类型引用；expr 不能以
类型名开头，与普通调用备选无歧义）：

```antlr
comptimeCall
    : '$' comptimeTarget '(' callArgs? ')'
    | '$' 'is_type' '(' expr ',' typeRef ')'
    ;
```

`$is_int(x)` / `$is_float(x)` 实参是普通表达式，走既有 `callArgs` 形态，
由语义层按内建谓词名拦截。

### 语义（compiler/parse/parse_expr.yh）

- `parse_comptime_call` 在诊断内建分派后按谓词名分派
  （`parse_comptime_pred_kind` → `parse_comptime_pred`，kind 1/2/3）。
- **只看静态类型、不求值实参**：实参以 `c_em_suppress` 静默发射但保留完整
  语义检查；折叠上下文（如 `$if` 条件）下临时把 `c_fold` 清零再解析实参，
  否则实参里的变量引用会误报「变量不是编译期常量」。
- 结果**恒为编译期布尔常量**（`sem_res_const` + 常规发码 + AST PRIMARY
  常量节点）：普通路径直接折叠；typed 路径经 PRIMARY 常量路径返回——
  **无需新增 typed IR kind**。
- 判定：`$is_type(x, T)` = 类型相等；`$is_int` = `ty_is_integer`（含
  bool/char/enum）；`$is_float` = `ty_is_float`（f32/f64）。

### 用例与验收

- run/171（普通路径 let/实参/`$if` 条件 + typed 正文 `$if`/普通 if/**结构体
  字段类型分派** + 顶层 const 聚合实参）、fail/158（未知类型拒绝）、
  语法语料 tests/yh/positive/72。
- 门禁：yh-run 283/283、语法门正例 75/75 + 反例 45/45、modules 门 77/84
  （基线）、自举主门全过。

## P1b `$for f in T.fields` 字段元信息（已实施 2026-10-09）

- **语法**：无需改 g4——`comptimeForStmt` 的 `IDENT '.' IDENT` 形态已覆盖
  （与 `E.values` 同形），解析期按 `.` 之后的固定名分派（`values` → 枚举、
  `fields` → 结构体/联合体）。
- **绑定**：新 `F_FIELD_META`；offset = 字段下标、type_id = **字段类型**
  （可直接作 `$is_type(f, T)`/`$is_int(f)`/`$is_float(f)` 的静态类型引用）、
  cval = 宿主类型 id（`.name` 投影时查字段表）、const_ready = 1。
- **展开**：`parse_comptime_field_for` 按字段声明顺序逐轮绑定；typed 路径把
  每个字段保存为 wrapper（op=0）下的独立块、普通路径逐轮解析发码，与
  `E.values` 完全同构；规模预算复用 `ct_charge_expansion`。
- **投影与限制**：`.name` 经 `sem_field_meta_name` 投影为只读字段名静态
  C 字符串；裸用拒绝（作类型谓词实参经 `c_ct_meta_bare` 放行）；`.value`
  不存在（报「字段元信息迭代变量只支持 .name」）。
- **用例**：run/172、fail/159–161、语法语料 positive/73。

## P1c `$field(x, "name")` 按名取字段（已实施 2026-10-09，只读）

- **语法**：无需改 g4——走既有 `comptimeCall` 的 `callArgs`（字符串字面量是
  普通表达式），语义层按内建名 `field` 拦截。
- **实现**：`parse_comptime_field_access` 解析基底（**正常求值**，走 `.` 同一
  `sem_member` 路径：指针基底自动解引用）+ 字符串字段名（内容区按字段表匹配
  名字解析出字段下标）；typed 捕获 `AST_EXPR_CTFIELD = 15`（op 槽存字段下标）；
  `ct_ir_member_place` 按 op 下标定位（跳过源码 token 名匹配）、
  `ct_ir_eval_expr` kind 9/15 共用读取路径。
- **只读**：`ct_ir_lvalue` 不识别 kind 15 → `$field(x, "name") = v` 按
  「编译期赋值只支持可写局部变量或受支持聚合元素」拒绝。
- **用例**：run/173、fail/162–164。

## 首版边界（三项共同）

- 仅单文件语义完整；`.s.ct` 跨模块闭包正文里的 `$if` 表达式 / fields /
  `$field` 形态序列化延后（正文格式确认后补）。
- 合流按类型相等（D2）；`$field` 第二实参只接受字符串字面量；字段名匹配按
  源文本（无转义处理）。