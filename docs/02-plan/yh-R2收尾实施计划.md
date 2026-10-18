# yh R2 收尾实施计划（2026-10-19）

依据与背景：LLVM 后端替换 LL1–LL10 已闭环（LL4 控制流、LL5 内存/聚合、
LL6 浮点、LL7 调用/ABI 与 R2a 同源切片合并验收）；2026-10-19 用户决定把
线程并行从 R2b 拆出为 R2c（推迟到并发标准库之后）；本地/CI 分工定策
（本地只保本平台门禁）。本计划只覆盖 **R2 收口**：

- R1 剩余中 R2 依赖的部分（任务私有上下文契约）；
- R2a 剩余 10 项的对账与真缺口归位；
- R2b 收窄后的三项硬门（函数级 check/IR 缓存、文件级对象、缓存键）。

**不在本计划内**（各归其位）：R2c 线程并行（等并发标准库）、LL11 默认
切换（前提 = R2b 剩余 + R2c）、F1/F2 双平台 LLVM ABI 验收、旧 ARM64 后端
三缺陷（已列为不修复的基线缺陷）。原方案见
[编译流程重规划实施方案](yh-编译流程重规划实施方案.md)，冲突处以本计划为准。

## 成功标准（目标驱动）

1. `make test` 与 `make selfhost-native` 在 Darwin/arm64 全绿；Linux/arm64
   由 CI（`linux-arm64` 作业）等效验证（本地/CI 分工）。
2. build-check（tests/modules/build-check.py）保持 100/100。
3. 缓存行为门全绿：失效矩阵（函数体/接口/私有常量/声明遮蔽/全局数据/
   注释/目标切换）与命中矩阵（无关修改全命中、损坏缓存拒建）逐项通过。
4. 性能不回退且披露：tools/compiler-performance.py 各 20 轮，
   单函数修改向 200ms、冷编向 1s 目标推进（当前 743.5/817.8 与
   2203.0/2765.1 ms 中位数/p95），数据写入完成记录。
5. 确定性：同输入两轮构建产物逐字节一致；输出独立于调度顺序。
6. 「首个完整 SSA 版本」具备宣布条件（不含线程并行）——LL11 的 R2b
   阻挡解除（R2c 除外）。

## 切片与顺序

```
RS0 对账回填 → RS1 任务私有上下文 → RS2 函数级 check/IR 缓存
→ RS3 文件级对象 → RS4 缓存键收口 → RS5 提交协议与优化覆盖复核
```

每片独立可验收、可暂停；RS2 依赖 RS1（私有上下文是缓存正确性前提），
RS3 依赖 RS2（文件对象键复用函数缓存身份），RS4/RS5 收口。

### RS0：R2a/R1 对账回填（纯文档，先行）

R2a 剩余 10 项写于 LLVM 决策之前，需逐项核对后回填 todo：

| R2a 剩余项 | 预期归位 | 证据 |
|---|---|---|
| switch / goto / for-in / 无限循环 | 关闭（LLVM 路线 LL4） | LL4 完成记录 + 343/343 语料 |
| 一元 +/- 与浮点标量 | 关闭（LL6；SSA 侧一元类型规则随 LL1 修） | LL1/LL6 记录 |
| 聚合/内存语义 | 关闭（LL5 全量） | LL5 收尾记录 |
| 间接调用与变参 | 关闭（LL7） | LL7 记录 |
| 单文件与 --emit-asm 共用新后端 | 关闭（LL9 统一入口；旧 --emit-asm 保留至 LL12） | LL9 记录 |
| 负数字面量实参（unsigned_score 回退） | **真缺口，归 RS2 前置小切片 RS1.5** | 需新探针确认 LLVM 路径现状 |
| 默认优化覆盖与提交协议复核 | 归 RS5 | — |
| 双平台 arm64 ABI 验收 | 归 F1/F2，本计划移除 | 平台矩阵方案 |
| R1「语义/check 边界与旧遍历分离」 | 复核：LL2 受检前端闸门/快照已部分完成，剩余差距记入 RS1 | LL2 记录 |
| R1「会话接口就绪」 | InterfaceReady 调度已在 fork worker 验收；会话 API 形态归 VS Code 扩展线（VS-U1），从 R2 门移除 | R2b 调度报告 |

**验收**：todo.md 回填（逐项标注证据链接），无代码改动。
**RS1.5（对账产物，若确认）**：负数字面量实参红绿回归
（`tests/yh-run/run/` 新用例，锁 `unsigned_score` 场景），前端一元减号
作实参的折叠/类型规则修复；O0/O2 定向门 + 全量门。

### RS1：任务私有上下文（R1 剩余核心）

**侦察记录（2026-10-19，RS1 第一步已完成）**：

- 语义状态集中在**单个巨型全局** `gen/state.yh` 的 `GenState`（`g_state`，
  约 270 行字段，经 `gen.G()` 被 parse/cmd/backend 全模块访问）：
  - **每任务（每模块编译）字段**：名字池 `np_data`、符号/类型表、发射缓冲
    （`o_text/o_bss/o_body`）、调用/字面量/循环栈（`c_call_* c_lit_* c_loop_*`）、
    模块信息（`mod_* c_mods*`）；
  - **每进程（项目级）字段**：项目索引（`p_projs/p_mods/p_files/p_imp_*`）、
    目标（`c_target/c_host_target`）、CLI 选项（`c_backend/c_opt_level`）。
- 已知结构性限制：注释明示 **GenState 大到让后端单条 add 的字段偏移越界**，
  字符串字面量表（`c_data_str_*`）已被迫拆成独立全局。
- worker 诊断走**固定缓冲**（`cmd/module_worker.yh`），防名字池扩容悬垂，
  受全局状态限制、不能直接复用于线程。
- 另有 `link` 项目的 `parse_source*` 悬垂教训（2026-10-15 修复）：任何
  「上下文快照」必须显式深拷贝生命周期归属。

**实施判断**：整结构显式传参（改所有 `gen.G()` 调用点）规模过大且受字段
偏移限制反噬；采取**拆分式**小步路线——

1. RS1a：把 GenState 按「每任务 / 每进程」两域加**分界注释与字段归属
   标注**（不改字段顺序——字段偏移进入机器码立即数，物理重排必然改
   `.s` 产物；门 = 新旧代固定点 + 语料行为等价，注释不进 token 则
   产物与上一代逐字节一致）；
   **✅ 2026-10-19 完成**：`gen/state.yh` 头部域分类说明 + 四处分界
   （构建配置与统计、解析游标续段、项目索引、目标与后端 CLI 选项；
   `c_module_mode`/`c_is_entry_mod`/`c_front_checked` 逐字段标注）。
   验证：`make` 冷编通过；`env -u PYTHONPATH make selfhost-native`
   全绿（固定点 + 自解析 + 语料 + 模块/项目 104/104，darwin）。
   注：本机 Bash 会话带 WorkBuddy 注入的 `PYTHONPATH`（sitecustomize
   shim 会让 Python 的 `mkdir(exist_ok=True)` 误报 EEXIST），跑门禁
   必须 `env -u PYTHONPATH`。纯注释改动无行为变化，不新增 .yh 用例。
2. RS1b：诊断缓冲从固定改为任务私有可扩容缓冲（行为门：诊断逐字节
   不回退，并发失败注入用例）；
   **✅ 2026-10-19 完成**：`c_path_buffer`/`c_ct_origin_path_buffer` 两个
   固定 `[1024]u8` 改为堆分配倍增扩容（新增 `gen.task_buf_reserve` 统一
   助手，任务生命期持有不释放）；`set_source_path` 不再有 1023 上限
   （超长路径改进实际生效于 Linux，darwin PATH_MAX=1024 无法构造用例）；
   `iface_ct.yh` 的来源映射路径解码/恢复 4 处同步。门：make +
   selfhost-native 全绿。
3. RS1c：每任务字段域**物理收敛**为 `TaskCtx` 子结构（`g_state.task`），
   调用点逐模块迁移（每步全量门；字段偏移变化随子结构化一次承担）；
   **✅ 2026-10-19 完成**：`tmp/rs1c_rewrite.py` 机械重写——199 个任务
   字段收敛进 `pub struct TaskCtx`（GenState 留 52 个进程级字段 +
   `task TaskCtx`），全仓三类访问模式（`g_state.F`/`G().F`/`<gsvar>.F`，
   变量名 gs/gs0/gs_const/gs_type/m_gs）一次迁移，残留 0；三个 LLVM
   fixture（llvmfront/llvmchecked/llvmlower，共 115 处）同步迁移。
   门：make 冷编一次通过 + selfhost-native 全绿（固定点 + 语料 +
   模块 18/18 + 项目 104/104）+ make test 342/343（+1 平台跳过）、
   fail 132/132；种子已滚 `bin/yh-darwin-arm64` `5b34a067…`。
4. RS1d：worker 主路径改持 `*TaskCtx`，消除对全局每任务字段的读写。
   **2026-10-19 修订：并入 R2c**——fork worker 下 `g_state.task` 已是
   任务私有（每进程一份，COW 继承），显式 `*TaskCtx` 传参贯穿数百个
   parse/gen 函数签名在无线程消费者时属投机性大改（违反「简洁优先」）；
   R2c 线程池落地时随宿主线程桥一起实施（第二个任务实例出现才有真实
   需求）。RS2/RS3/RS4 的缓存与对象工作不受影响（缓存按内容键控，
   不依赖显式传参）。

原 RS1 描述（保留备查）：把「单模块编译所需」的语义状态打包为显式上下文
对象，worker 主路径不再读写全局；固定诊断缓冲改为任务私有可扩容缓冲
（消除 iface_ct_load 悬垂类缺陷的结构性根源）。
**用例**：`tests/modules/` 新增并发失败注入用例（两 worker 先后失败、
诊断互不串扰）；既有 42 反例 + 失败注入门保持全绿。
**验收**：make / make test / make selfhost-native 全绿；诊断文本与
位置逐字节不回退。

### RS2：完整函数级 check/IR 缓存

**2026-10-19 开工前核查（含实测探针）**：
- **legacy 路径已有函数级 IR 缓存**（`ast/ast_ir_cache.yh`：键含编译器
  指纹/目标/源码范围/AST 语义事实/绑定类型；`ast_ir_lower_module` 内
  逐函数读写），但仅覆盖「通过 verifier 进入 SSA 子集」的函数；统计在
  worker 子进程内累加，父进程 --stats 不可见（实测 ir_cache_hits=0）。
- **LLVM 模式完全没有函数级缓存**：worker 直接
  `mb_llvm_emit_module`（module_worker.yh:354），不经 `ast_ir_lower_module`；
  增量粒度 = 模块级对象缓存（无改动全命中已实测），单函数修改重做整模块。
- **剩余真缺口 = LLVM 模式的函数级 check/IR 缓存**：需把
  `ast_ir_cache` 的键/读写推广到 LLVM 模式的模块 IR 构建（受检快照 →
  模块 IR 按函数复用序列化 IR）。**必须 Linux 宿主实施与验证**
  （darwin 无固定 SDK，本地/CI 分工）；建议在 LL11 默认切换前完成，
  作为单函数 200ms 增量目标的主力。
- legacy 窄子集缓存在 LL12 退役旧后端时随之处理，不单独投资。
- **用例**：失效矩阵用例（改函数体恰失效 1、改 pub 签名失效消费方、
  改私有常量只失效本模块、注释变化保函数复用、切目标不误用）；命中
  矩阵（无关模块修改全命中）；损坏缓存拒建。放
  `tests/modules/` 项目用例 + `tests/selfhost/` 专项门。
- **验收**：门全绿 + 20 轮性能测量（单函数修改场景应显著低于现状，
  数据披露）。

### RS3：文件级对象

**2026-10-19 代码级设计定稿**（基于 `mb_emit_indexed_module` 通读）：

现状：模块 = 目录（每目录一模块），worker 五遍 pass2（mode 2 检查捕获 /
3 CT 布局 / 4 布局求值 / 1 编译期正文 / 0 **最终发射**），mode 0 把全部
文件的函数/全局发射进**单一 o_text 缓冲**，随后运行时桩（`em_emit_runtime_stubs`）、
bss（`c_bss_syms` 跨文件累积）、**单 `.s`**（`drv_write_asm(out_s)`），
link_cache 按模块键控单对象。

文件级对象需要的改动（RS3a–d，每步独立可验收）：

- **RS3a 跨文件 private 的可见性**：单对象内 private 不发 `.globl`（局部
  符号）；拆文件后跨文件 private 引用必须可跨对象解析。方案：模块内
  private 符号一律发 **hidden 可见性**（GNU `.hidden`+`.globl`，Darwin
  `.private_extern`+`.globl`）——模块后缀（`__proj__mod`）已保证跨模块
  不撞名，hidden 不导出动态符号表，`nm -u` 审计不受影响。改
  `gen` 的符号可见性发射点 + 确认 yh_link 方言兼容（未接入，暂无消费）。
- **RS3b 按文件发射**：mode 0 遍按文件切缓冲——每文件重置
  `o_text/o_data/o_body/c_bss_syms`，发射该文件 decl 后写
  `<build>/asm/<tag>/<file>.s`；运行时桩拆到**每模块独立桩对象**
  （`asm/<tag>.stub.s`，桩符号 hidden）；`drv_write_asm` 改多路写出，
  `out_s` 单路径签名 → 文件清单。bss 符号归属 = 注册时所在文件。
- **RS3c link_cache 对象清单与键**：每模块 N+1 个对象（N 文件 + 1 桩）；
  文件键 = **本文件内容 + 本模块 `.s.i` 哈希 + 导入 `.s.i`/`.s.ct` 哈希 +
  工具身份 + 目标**（不含兄弟文件内容——private 兄弟变更不影响本文件
  代码生成，这是单函数 200ms 增量的来源）；manifest 改文件级清单。
  注意：本模块 `.s.i` 变化（pub 变更）时全文件正确失效。
- **RS3d 验收**：tests/modules 新增跨文件 private 项目用例（含跨文件
  private 调用/全局、单文件改动只重建一个对象的缓存断言）、反例（跨模块
  private 仍拒绝）；单函数 200ms 测量；全量门。

**规模判断**：RS3a–d 触及发射架构、worker 签名与 manifest 格式，约
40+ 步实现与多轮全量门，需要专门会话从头执行（RS1 的「侦察→设计→
下会话执行」模式）；**不宜在本会话剩余上下文中开工**——半成品比不做
更危险（RS1c 的 git checkout 事故已验证这一风险）。

### RS4：缓存键收口

**✅ 2026-10-19 核查关闭（代码已实现，todo 未回填）**：
- 编译器身份：`mb_mix_compiler_fingerprint`（每进程读一次自身二进制混入键）；
- 外部汇编器：`mb_hash_tool_identity(&h, cmd0)`（link_cache.yh:868）——
  解析路径 + 二进制内容入对象缓存键，换工具链必然换键；
- 外部链接器：`mb_hash_tool_identity(&hlink, cc)`（:991）+
  `mb_link_query_identity`（:462）哈希驱动器报告的搜索路径/工具/启动
  文件/库文件（查询结果中的工具路径再哈希内容，:561）；lld 库内容经
  `mb_hash_lld_library`；
- 目标/优化级/后端：triple、data_layout、abi、`c_backend`、`c_opt_level`、
  桥版本均在键中（module_build.yh:629-705）；
- 运行时输入：全部源文件与依赖 `.s.i`/`.s.ct` 内容哈希（:670-688）。
证据门：build-check 的 u5-hot-cache-hits / u5-rebind 系列缓存键用例全绿。

### RS5：优化覆盖与提交协议复核（收口）

- **内容**：默认构建的优化覆盖现状记录（对接 NP 管线去向）；失败事务/
  原子发布协议全链路复核（失败不留下可命中的成功标记、yh run 不运行
  旧程序）；产出 R2 收口报告，声明「首个完整 SSA 版本」达成边界
  （含/不含项逐条列明），解除 LL11 的 R2b 阻挡。
- **验收**：全部门 + 完成记录 + finish.md/todo 回填。

## 每片通用流程（仓库规则）

1. 先在 `tests/`（yh-run/modules/selfhost 相应层）加 `.yh`/项目用例；
2. 实现；每片完成后 `make`、`make test`、`make selfhost-native` 全绿；
3. 涉及缓存/性能的切片跑 tools/compiler-performance.py 20 轮并记录；
4. 刷新相关 docs（本计划状态、03-design 若有语义变化）；
5. finish.md 记录；种子滚制仅在门全绿后按既有规则执行。

## 风险与边界

- RS1 动 worker 状态结构，回归面最大——严格小步提交，每步全量门。
- RS2/RS3 的性能收益依赖外部汇编器仍占大头的事实；若测量不达标，
  收口报告如实披露，不虚标目标达成。
- 本机为 macOS：性能测量与 Linux 门由 CI/WSL 承担（本地/CI 分工），
  本计划所有门在本机以 Darwin 侧为准。
