# yh LLVM LL5 全局/字符串数据切片实施方案（2026-10-15）

承接
[yh-LLVM-LL5切片切片-2026-10-15.md](../01-finished/yh-LLVM-LL5切片切片-2026-10-15.md)
§4：受检快照不含全局初始化表达式是 LL5 数据面的唯一缺口。本切片按已确认的
四层方案实施，完成后 LL5 局部+全局数据面收尾（CT backing 与指针重定位按
既定决策单独收敛，不在本片）。

## 1. 范围

**支持（LLVM 路径新能力，旧后端行为不变）**

- 模块级 `let` 全局：整数族/bool/char/enum 标量的零初始化与常量表达式
  初始化；定长数组与结构体的常量字面量初始化（整数标量元素/字段、嵌套
  结构体、指针字段/元素仅 NULL）；union 零初始化；
- 模块级 `const` 聚合（数组/结构体）常量字面量：`pub` → external linkage，
  私有 → internal；标量 `const` 引用在函数体内折叠为 `CONST`（修既有缺口：
  此前 `sym_id >= 0` 的常量引用被绑定解析误拒）；
- 函数体内：全局读/写/取址、全局聚合的下标/字段访问与按值副本、
  `len(全局数组)`（前端已折叠）、字符串字面量表达式 → 匿名 internal
  字节全局（`.LD<label>`，按标签去重）；
- 头部/调用约定不变；无新语法。

**拒绝（带来源诊断，不静默回退）**

- 指针非零初始化（含字符串指针字段/元素）、切片全局、`$` CT 初始化、
  导入的聚合常量副本（extern 副本字节不在快照，属 CT backing）、
  浮点全局（LL6）、union 初始化式（旧后端同样拒绝）、聚合参数（LL7）。

## 2. 四层落点

### 2.1 解析/快照

- `ast/ast_decl.yh`：`AstDecl` 增加 `init_expr int`（默认 -1）；新增
  `ast_decl_attach_init(fi, decl_index, expr_id)`（仿 `ast_decl_attach_body`）；
  `ast_decl_bind_file` 扩展绑定 `TK_LET`/`TK_CONST` 的模块级符号；
  `ast_decl_verify` 校验 init_expr 的归属与范围。
- `parse/parse_global_init.yh`：三条初始化路径在捕获开启时建/挂 AST：
  - 标量/指针：`parse_expr_iso` 的根 `res.ast_id` 直接挂载；
  - 数组/切片字面量：元素根经 `ast_expr_args_append` 链接（与局部字面量
    同构），字符串元素手工建 `AST_EXPR_PRIMARY`（op=TOK_STRING、is_const=1、
    const_bits=标签），最后建 `AST_EXPR_ARRAY` 根；
  - 结构体字面量：`parse_global_struct_body`/`parse_global_field_value`
    线程化 `ast_out` 出参，逐字段建 `AST_EXPR_STRUCT_FIELD` 链、嵌套建
    `AST_EXPR_STRUCT_INIT`（与局部 `parse_struct_init_body` 同构）；
  - `$` CT 形态不捕获（init_expr 保持 -1），lowering 依「非 BSS 且无
    init_expr」拒绝；
  - 捕获只新增记录，旧数据发射路径逐字节不变（固定点门守住）。
- `ast/checked_module_verify.yh`：`checked_verify_functions` 同步校验
  init_expr（可选行号、file_id 一致、范围在声明 token 区间内）。

### 2.2 初始化求值（`ast/checked_module_lower.yh`）

- `lower_module` 的声明扫描由「遇 TK_LET 即拒」改为全局登记：
  - 标量 `const`（SYM_CONST + 标量类型）无运行期实体，跳过；
  - SYM_VAR / 聚合 SYM_CONST → 模块符号（GLOBAL；物理存储 mutable=1，
    const 的直接左值限制仍由前端执行；
    linkage= pub?external:private；defined=1；名字经 `checked_lower_name`，
    后缀规则与旧后端 `sym_suffix_needed` 一致）；
  - 对象类型：标量/指针复用 canonical 模块类型；聚合递归构建
    `IR_MODULE_TY_ARRAY/STRUCT/UNION` 模块类型（`source_type_map` 惰性缓存）；
  - 数据：`init_expr >= 0` → 常量物化器递归写字节（缓冲预清零，字段间隙
    与尾部填充天然为零）；`init_expr < 0` 且在 BSS 清单 → 全零；
    否则拒绝（`$` CT/导入副本）。
- 常量物化器 `checked_lower_global_value`：任何 `is_const=1` 节点直接取
  前端折叠结果 `const_bits`（折叠语义零差分），按目标类型截回写 LE 字节；
  TY_PTR 非零（字符串标签）→ -2；ARRAY 沿 ARG_LIST 逆序链收集元素递归；
  STRUCT 沿 STRUCT_FIELD 链按字段偏移递归；SLICE → -2。
- 字符串字节物化：快照 strings 表是**原样 token 字节**（含引号与转义），
  按旧后端 `em_data_string_body` 同一转义表解码并补 NUL。

### 2.3 IR/后端

- `ir/ssa.yh`：`IR_OP_GLOB_ADDR = 29`（imm=模块符号下标，结果 canonical
  指针，a/b/aux=-1）；`ir_verify_inst` 上界与分支同步。
- `ir/ssa_module_20_verify.yh`：`ir_module_verify_function` 校验 GLOB_ADDR
  imm 指向 defined GLOBAL 符号、结果经 type_map 是指针。
- `ast/checked_module_lower.yh` 表达式面：
  - PRIMARY 全局标量 → `GLOB_ADDR` + `LOAD`；聚合 → `GLOB_ADDR`（地址语义）；
    标量 const → `CONST`（折叠）；字符串字面量 → 匿名全局 + `GLOB_ADDR`；
  - `lvalue_ptr` / `&x` / 赋值 / 聚合副本 / 切片基址补全局分支；
  - `global_map`（快照符号 → 模块符号）由声明扫描填充。
- `backend/llvm_module.yh`：已定义全局统一 `[N x i8]` 发射——全零
  `zeroinitializer`，否则 `c"\XX.."`（复用 `llvm_quote` 转义规则）+
  `, align N`；preflight 放行聚合/指针对象类型、拒绝未定义全局实体；
  GLOB_ADDR → `getelementptr i8, ptr @"name", i64 0`（`llvm_instruction`
  增加 unit 形参）。

### 2.4 跨模块

- `pub const` 聚合在提供方模块内以 external linkage 发射（名字带模块后缀，
  与旧后端一致）；私有 `let` 全局 internal/private；
- 消费方引用导入聚合常量副本（F_EXTERN + cval 标签）本轮拒绝（字节不在
  快照，CT backing 单独收敛）；
- modules 项目验收维持旧后端（不受影响）；LLVM 项目模式的跨模块消费
  在 CT backing 切片一并验收。

## 3. 门禁

1. `llvmlower` 项目：`input/global.yh` 转正向（零初始化/标量/数组/结构体/
   嵌套/const 聚合/字符串/读写/整数切片全局）；新增 `input/globalreject.yh` 浮点切片全局拒绝负例
   （切片全局、指针非零、`$` CT）；`llvm-lower.py` 与 `build-check.py` 同步。
2. 新增 `tests/selfhost/llvm-global.py`：O0/O2 文本断言
   （`[N x i8]`/zeroinitializer/internal global/GETELEMENTPTR 全局取址）
   + `opt -passes=verify` + clang 汇编 + gcc 链接原生运行（多组语义断言）
   + 拒绝负例带函数名与来源。
3. 新增 `tests/yh-run/run/llvm-global.yh`：同源旧后端语义锁。
4. 验收：`make` / `make test` / `make selfhost-native` 全绿；17 个
   `llvm-*` 专项门退出 0（包含本片新增的全局前端门与独立后端门）。

## 4. 风险与对策

- **捕获范围扩大影响旧后端**：捕获仅新增 AST 记录；旧单文件路径在全局
  子遍保持 capture=0（sem_compile 临开临关），无交集；固定点门逐字节守住。
- **常量折叠语义差分**：物化器不重新计算，只读前端已折叠的 const_bits。
- **字符串解码分叉**：解码表与 `em_data_string_body` 逐字一致，语料含
  转义用例差分。
- **BSS 语义**：LLVM 无 .bss 概念，`zeroinitializer` 等价（链接器自行
  归 BSS）；运行语料差分守住。

## 5. 续接执行记录（2026-10-16）

- [x] 恢复 HTML 会话与未提交改动：解析捕获、AstDecl 初始化边、GLOB_ADDR 定义。
- [x] 新增 `checked_module_global.yh`：独占布局/字节物化、BSS 与字符串目录；
  `checked_module_lower.yh` 接入全局读写/取址/副本/数组切片基址。
- [x] LLVM 字节全局与 GLOB_ADDR 发射；独立手建 IR 门红→绿。
- [x] 新增共享 `.yh` 正例、七个独立拒绝用例与 O0/O2 原生 C 驱动。
- [x] 候选重建后完成所有门与最终独立审查，更新完成流水：`make full` 全绿
  （316/316、固定点 24、自解析 87、模块 18/18、项目 100/100），17 个 LLVM 门全绿。

实施裁决：

- 原工作区已有本任务的未提交修改，续接时原地保留，临时日志与探针放
  `tmp/llvm-migration/`；没有搬迁工作区或重做解析层。
- 为读取/写入 `*int` 全局对象，canonical 指针上界从 24 扩到 36，覆盖
  对象存储地址 `**int`；更深类型或地址明确拒绝，不能越界索引。
- `bool` 常量保留低八位，`2.to_type(bool)` 经常量引用仍为 2；只在条件
  判定时比较非零。C 驱动先观察到返回 1（退出 113），再验证修复。
- 宽负整数验收显式用 `i64` 表达式；未定宽 `-4294967297` 在旧前端先按
  int32 折叠为 -1，旧后端汇编证实一致，不借本片更改该规则。
- 填充字节由 C 驱动经导出的对象地址检查，避免为测试扩大指针重解释转换。
- LLVM 项目模式尚未接入，导入常量副本的端到端验收留待该入口与 CT backing
  切片；本片验证提供方 pub/private linkage，不把它记作跨模块消费通过。
- 独立审查修正原方案的只读假设：字符串与源聚合 const 均允许裸指针别名写，
  物理对象的 `mutable` 必须为 1，LLVM 发射 `global`。前端仍拒绝 const 直接
  赋值；手建 IR 的真实只读对象仍可发 `constant`。两项 C 写入均先复现 SIGSEGV。
- 函数体 `is_const` 不保证 CAST 已折叠（`c_fold=0` 时只发运行期转换）；
  因此快捷取位型仅用于常量叶、整数字面量一元式、枚举与已折叠数组长度。
  CAST 逐节点降低，
  数字指针/字符串地址转整数/浮点转换仍明确拒绝；指针标签不能当整数地址。
  链式 i8/u8 截断与全宽 u64/i64 文字量由共享源和 C 驱动分别锁定。
- 全局 AST 捕获只属于当前模块的真实源码声明。接口与 CT 闭包重放期间暂关
  捕获，仍执行常量求值；返回后恢复，不能影响随后 CT 函数正文捕获。
  首次全量门的两项跨模块闭包失败已复现并修复，新增跨文件私有常量闭包回归。
