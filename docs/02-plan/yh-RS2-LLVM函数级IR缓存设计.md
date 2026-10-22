# yh RS2：LLVM 模式函数级 check/IR 缓存设计（2026-10-19 侦察，2026-10-22 实施修订）

> 2026-10-22：LA3 交付 1–2 已按本文修订版落地（见
> [LA3 完成报告](../01-finished/yh-LLVM架构LA3-2026-10-22.md)）。旧侦察记录
> 保留在文末“历史记录”，不再作为实现依据。函数级 check 复用（交付 3）未启动。

## 2026-10-22 实施版

### 1. 缓存单元

每个函数缓存记录是一个**只含单函数及其贡献闭包的迷你 IRModule**，不是
`IRModuleFunction + type_map` 的裸拷贝：

- 函数体沿用 `ir_serialize` 稳定编码；
- 类型闭包按依赖后序保存（自引用/前向类型返回 miss，不缓存）；
- 符号闭包含函数自身、`GLOB_ADDR`/`FN_ADDR` 目标与直接调用名；
  其他函数一律降为外部声明，避免迷你模块出现无 body 的定义；
- 全局实体闭包含函数产生的字符串/静态数据及重定位目标；
- 来源闭包含函数 locs 与符号声明位置，命中时按当前模块路径重建。

迷你模块先通过 `ir_module_verify`，再序列化为 `IRModule` 字节流；外层 32 字节
头保存 magic/版本/环境键/payload 长度。

### 2. 键与失效

函数键 = schema + 模块环境键 + 目标/指针位宽/布局/ABI + 源路径 +
类型/字段/签名布局哈希 + 本模块非函数声明 token 流 + 本函数 token 流。
词法器不保留注释/空白，因此注释、空行、缩进变化不改变函数键。

模块环境键由 `cmd/function_ir_cache.yh` 计算：目标/优化级别/编译器指纹/
桥版本 + 本模块 `.s.i`/`.s.ct` + 依赖模块接口。它**不含本模块函数体源码**，
所以单函数修改不会让其他函数失效；接口、CT、目标或布局变化保守地让全部
函数失效。

### 3. 生产接入

- `cmd/function_ir_cache.yh`：目录 `<build>/firc/<tag>/`、`index` 与
  `<key>.fir`；装载失败按空缓存，模块完整成功后才原子提交记录与索引。
- `ast.lower_module_cached`：在 `checked_lower_build_functions` 逐函数查/写；
  命中调用 `ir_function_cache_merge` 重绑定，未命中走原 lowering 并 capture。
- `cmd/module_worker.yh` / `llvm_pipeline.yh`：项目 worker 接入缓存；
  单文件入口暂不接缓存。整模块前端检查保留，本阶段只缓存已受检函数的 IR。
- `--stats`：`ir_cache_hits`、`ir_cache_misses`、`ir_lowered` 与
  `ir_functions` 区分命中、未命中与实际 lowering。

### 4. 验收

`tests/selfhost/llvm-function-cache.py` + `llvmfunctioncache` 项目：
冷编 0/4、注释变化 4/0、单函数修改 3/1、插入第 5 个函数 4/1、损坏一条记录
只重建该记录、接口变化 0/5；O0/O2 均通过，命中构建的对象与 LLVM 文本和
冷编逐字节一致。递归/前向类型闭包暂不缓存；函数级 check 复用仍未实现。

---

## 历史记录（2026-10-19 侦察，保留）


本文件是 RS2（R2 收尾实施计划 §RS2）的侦察与实施设计，不改变代码。
完整 R2 收尾见 `yh-R2收尾实施计划.md`。

## 1. 现状

- LLVM 路径：`compiler/cmd/module_worker.yh::mb_llvm_emit_module` 直接调用
  `ast.checked_module_capture` → `ast.lower_module` → `backend.llvm_emit_module` →
  内嵌桥发布对象。**不经** `ast.ast_ir_lower_module`，因此没有函数级 IR 缓存，
  统计 `c_stats_ir_cache_hits/misses` 在 LLVM 路径上不会增长。
- 旧 SSA 路径：`ast.ast_ir_lower_module` 对通过 verifier 的函数计算
  `ast_ir_cache_key`，读写 `.ir` 文件，命中时直接发射并计数。粒度 = 单函数，
  但仅覆盖 SSA 子集；worker 子进程统计不可见（实测 hits=0）。
- `ir.IRModule` 已具备 `ir_module_serialize/deserialize/verify` 与
  `ir_module_identity`（整模块 32 字符摘要），可作为缓存载体。

## 2. 真缺口

LLVM 模式下，单个函数体变化仍导致整个模块重新 lowering + LLVM 文本生成 +
内嵌桥编译。R2 收尾目标：函数体变化只失效该函数的 IR，其余函数复用已序列化的
`IRModuleFunction`（含 `type_map`），再装配成模块送入 backend。

## 3. 设计约束

1. `checked_module_lower` 当前是单遍：先建表/全局，再两轮函数（签名登记、函数体）。
   函数级缓存要求把「函数体 lowering」与「模块装配」解耦，但表/全局仍需先完成。
2. `IRModuleFunction` 含 `body IRFunction` + `type_map *int` + `locs`，缓存时必须
   连同私有类型映射一起序列化；反序列化后需重新挂到模块 `functions` 表。
3. 缓存键必须包含：编译器指纹、目标 triple/data_layout/abi、函数源码字节、
   受检类型事实（签名 ABI/参数/返回）、inline 依赖源码、模块内符号身份。
   整模块级的源/依赖 `.s.i`/`.s.ct` 内容哈希也必须纳入（RS4 已有工具）。
4. 失效矩阵（与 build-check 既有 SSA 用例对齐）：
   - 改函数体 → 仅该函数 miss，其余 hit；
   - 改 pub 签名 → 消费方模块 miss；
   - 改私有常量/全局 → 仅本模块 miss；
   - 注释变化 → 函数复用（源码哈希含注释，需明确策略：注释变化不改变 IR，
     但源码哈希会变；需把缓存键改为 AST/语义事实而非原始源字节，或接受 miss）；
   - 切目标 → 全 miss。
5. corrupted cache → 拒绝并重建，hits=0。

## 4. 子切片（建议顺序）

### RS2.1：整模块 IR 缓存先行（plumbing）
- 在 `mb_llvm_emit_module` 中，`lower_module` 前后接入整模块 `IRModule` 的
  序列化缓存（键 = 模块内容哈希 + 依赖接口 + 目标 + 编译器指纹）。
- 命中时反序列化直接进入 backend，跳过 lowering；统计 hits/misses。
- 价值有限（模块未变时对象缓存已跳过整模块），但建立文件 I/O、键、统计的
  基础设施，为函数级切分做准备。

### RS2.2：函数级切分（核心）
- 将 `lower_module` 重构为：
  1. 表/全局/来源一次完成（不变）；
  2. 签名登记（不变）；
  3. 每函数 lowering 独立，结果写入 `IRModuleFunction` 缓存；
  4. 装配：未命中函数重新 lowering 并写缓存，命中函数反序列化并追加。
- 需要 per-function cache key（复用 `ast_ir_cache_key` 思路，但面向 `IRModuleFunction`）。
- 需要 per-function 序列化格式（当前 `ir_module_serialize` 是整模块；可先整模块
  但按函数拆分缓存目录，或新增 `ir_function_serialize`）。

### RS2.3：回归与性能
- build-check 新增 LLVM 模式失效/命中/corrupt 矩阵（对齐 SSA 用例）。
- 20 轮测量，披露单函数修改耗时。

## 5. 风险

- `lower_module` 是 1200+ 行单函数，重构函数级切分侵入性高，必须小步提交、
  每步全量门。
- `IRModule` 所有权与释放：缓存命中路径必须避免 double-free；建议命中时
  反序列化到新模块，未命中函数 lowering 后合并。
- 字段偏移：RS1 已收敛 TaskCtx，但 IR 缓存不涉及 GenState 字段重排。

## 6. 建议下一步

先实施 RS2.1（整模块 IR 缓存 plumbing），验证文件 I/O、键、统计与 corrupted
拒绝；再进入 RS2.2。RS2.1 不改善单函数性能，但为 RS2.2 提供基础且可独立验收。
