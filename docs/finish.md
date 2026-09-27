# finish

## 2026-09-28 tests 目录清理：删除 TCC 上游 C 测试套件（237 个文件）

**判定依据（引用关系全查证）**：
- Makefile 的 `test` 目标只跑 `tests/yh/check.py`（ANTLR + --compiler 两模式）
  与 `tests/yh-run/check.py`，且 `tests.%: ;` 规则已切断上游 tests/Makefile
  体系；
- 两个 check.py 只引用根目录 `yh.g4`/`yh` 二进制与 `tmp/sysroot`，不依赖
  tests 下其他文件；
- `rg` 全查 Makefile/src/config.h/lib/：对 tests2、pp、tcctest、abitest、
  boundtest、libtcc_test、asmtest、vla_test、testfp、42test.h、
  asm-c-connect、gcctestsuite.sh 零引用。

**删除**：tests/ 下除 `yh/`、`yh-run/` 外全部内容——`Makefile`、`pp/`、
`tests2/`、`tcctest.c/.h`、`abitest.c`、`boundtest.c`、`libtcc_test.c`、
`asmtest.S`、`asm-c-connect-1/2.c`、`vla_test.c`、`testfp.c`、`42test.h`、
`gcctestsuite.sh`，共 237 个文件。这些是 TCC 上游 C 测试套件，yh 编译器只
接受 .yh 输入，永远不会被执行。

**验证**：make 构建正常；make test 三层全绿（ANTLR 66/66+29/29、编译器
66/66+29/29、yh-run 24/24）。tests/ 保留 1.4M（yh 416K + yh-run 1.0M）。

## 2026-09-28 ponytail-review 死代码清理：净删 134 行 + 4 个垃圾文件

**审查方法**：按 ponytail-review（仅猎杀复杂度，正确性/性能另审）对当前
全部改动做逐文件审查，用 rg 验证「只写不读」后再删。

**清理动作（均有读写计数证据）**：
- yh_decl.c：删除只写不读的死变量 `yh_saw_param` / `yh_cur_fn`（含无意义的
  保存/恢复）/ `yh_has_const_init` / `func_sym`（恒 NULL）；删除投机机制
  yh_consts 常量侧表整套（`yh_register_const` 只写、`yh_lookup_const` 挂
  `__attribute__((unused))` 自证无人调用，注释自称"保留用于 M4"——M4 需要
  时再加）；删除 `yh_parse_const_decl` 的死参数 `local` 及两处实参；删除
  `yh_gen_function` 中恒真的 `!yh_syntax_only()`（唯一调用点已排除语法模式）
  与 YH_DEBUG 注册调试输出；`(void)s;` 改为不接收 sym_push 返回值。
- yh_stmt.c：删除注释自证"不可达"的 if 块（for-in RANGE 窥探）、range 分支
  死赋值 `b1_off = h_cur - 8`（下一行立即覆盖）与 `et = int_t`、压警告的
  `(void)h_idx...` 行、return 后恒真条件 `if (tok != '}' || 1)`、YH_DEBUG
  switch 调试输出、与 yh.h 重复的 3 个 extern 声明。
- **switch case 解析统一**：删除 `yh_parse_switch_case`（只被语法模式调用，
  编译路径 L533-587 手写了同样的 case/default 解析）；语法模式改走同一条
  内联循环（生成部分本就有 `!yh_syntax_only()` 保护），判别值求值/槽分配块
  包进 `if (!yh_syntax_only())`。两种模式一条路径，-43 行。
- yh_expr.c：删除三元表达式尾部空语句块；删除与 `yh_parse_expr` 逐字相同的
  `yh_parse_expr_pub`（3 个调用点改用 `yh_parse_expr`）；structInit 三段
  重复注释合并为一段。
- macho-out.c：删除空块 `{ unsigned k; (void)k; }`；`macho_write` 定义前移
  替代前向声明。
- tccpp.c：删除多余的 `parse_number` 前向声明（定义在同文件更早位置）。
- arm64-gen.c：删除 gfunc_call 热路径上的 YH_DEBUG 参数类型打印（每次调用
  getenv）。
- yh.h：删除不存在的 yh_slice.c 漂移注释行；yh_builtin.c：修正 params 注释
  （`-2 表示裸 ...` 的编码不存在，实际用 variadic 字段）。
- 仓库垃圾：删除根目录 `hello`、`yh`（Mach-O 构建产物）与 `not`、`tty`
  （空文件）；.gitignore 增加 `/yh`、`/hello`。

**保留项（有行为，非死代码）**：yh_decl.c binding 处 6 个保留字的定向报错
（产出不同错误信息，是功能不是死代码）；arm64-gen.c store()/type_size()
assert(0) 前的 fprintf（错误路径诊断，随 assert 存活）。

**验证**：make 干净构建零警告；make test 三层全绿——ANTLR 语料 66/66+
29/29、编译器模式 66/66+29/29、yh-run 24/24，与清理前完全一致。

**行数**：yh 解析器七文件 3688 → 3554 行（净 -134），另有 4 个垃圾文件出库。

## 2026-09-27 M6 完成：有证据地清理 + 清理后回归对比

**清理动作（均有调用关系证据）**：
- libtcc.c：移除 tccasm.c 的 ONE_SOURCE 条件包含（CONFIG_TCC_ASM 从未定义，
  tccasm.c 1183 行从未编译进产物）；C 源路径改为显式报错「yh 编译器不支持
  C 源文件（.yh 是唯一输入）」（驱动层 M1-01 已拒绝 .c，libtcc API 层同步
  收口）；删除 free_inline_functions 调用。
- tccgen.c：删除 tccgen_compile（C 路径入口，yh 不再引用）、
  free_inline_functions、gen_inline_functions（static inline 机制整体，
  其唯一调用链 tccgen_compile→gen_inline_functions→gen_function 已断）及
  tcc.h 对应声明——干净构建零警告。tccgen.c 7122 → 7034 行。
- 清理过程事故记录：一次自动删除脚本误删 tccgen.c 主体（write 收到 list
  抛 TypeError 时文件已截断），从 git HEAD 完整恢复；随后重做的手工删除
  （decl0/decl/block/gen_function 尝试）因连锁依赖（expr_eq/unary 链被
  decl_initializer 复用）引发链接错误，全部回退。

**M6 结论（依方案 §6.8「不因删行目标强行移除」）**：
- 已删：tccgen_compile、free_inline_functions、gen_inline_functions、
  tccasm 包含、C 源路径入口（tccgen.c 净减 88 行 + tccasm.c 1183 行从未
  编译进产物）。
- 保留（有活引用）：decl0/decl/block/expr_eq/unary 链——yh 的
  decl_initializer_alloc（字符串字面量、structInit）、expr_const1（数组
  长度/枚举/const）、find_field/struct_layout、值栈与 gen_* 机制全部
  复用自 tccgen.c，与其声明 parser 同文件交织，无法在不拆分文件的前提下
  单独移除。「C parser 拆除（净减 2.5k~3k 行）」列为 0.0.2 任务，先做
  tccgen.c 按职责拆分（方案 §2.2 既定顺序）。
- 清理前后回归对比：make test 三层全绿（ANTLR 66+29、编译器 66+29、
  yh-run 24/24）完全一致；构建零警告。

## 2026-09-27 M5 完成：三层测试集成、干净构建、README 重写

## 2026-09-27 M5 完成：三层测试集成、干净构建、README 重写

- **M5-01**：`make test` 现在依序运行三层回归——ANTLR 语法语料、编译器
  语法模式（--syntax-check）、tests/yh-run 语义/运行测试（本机 Mach-O；
  --cross 时附加交叉 ELF + docker 容器运行）。全部通过 rc=0。
- **M5-02**：`make clean && make` 干净构建验证——产出 yh/libtcc.a/libtcc1.a
  零警告（tccpp.c 两处历史 warning 已于此前消除）；干净构建后本机 hello 与
  交叉 ELF（24/24）复验通过。用户源文件唯一后缀 .yh 由驱动强制。
- README 重写为 yh 编译器说明（快速上手/语言速览/测试/输出格式/目录结构/
  状态与限制），替换原 TCC README。
- hello 的 void main 触发「建议返回 int」提示（M3-02 的 main 检查生效）。

## 2026-09-27 M4-02/M4-03 完成：切片、for-in、structInit、类型化变参

## 2026-09-27 M4-02/M4-03 完成：切片、for-in、structInit、类型化变参

**M4-02 切片与 for-in**
- `[]T` 解析时规范化为 `struct { u64 len; T *data; }`（登记表缓存）；
  切片形参按 16B 结构体传递；len() 运行期读 len 字段；下标降糖为 data[i]。
- `[N]T.to_type([]T)` 视图构造：临时 16B 槽写入 {len:N, data:&arr[0]}，
  结果为切片左值。
- for-in 编译降糖：数组（len 编译期）/切片（len 运行期）/区间 `a..b`
  （左闭右开、空区间零次）三形态；单/双目标绑定值拷贝；continue 回递增、
  break 出链；绑定块作用域（sym_pop 恢复）。
- structInit 代码生成：匿名对象分配（局部/全局按上下文）→ 地址存隐藏槽 →
  命名/位置式逐字段「槽地址+偏移 = 值」→ 结果为对象左值；嵌套 structInit、
  作实参、return 均支持；命名/位置混写编译拒绝。

**M4-03 类型化变参**
- 声明：`name ... T` 形参类型降糖为 []T（packed 位标记变参 Sym），
  末尾唯一性检查；函数签名 func_type=FUNC_ELLIPSIS。
- 调用：实参按源码顺序求值并拷入临时连续数组（区域计入 loc）；
  打包为 16B 切片值 {len:n, data:元素区} 压栈作为单个实参；零变参也装配
  （len=0）；裸 `...`（printf/open）保持 C 默认提升路径（f32→f64）。

**调试修复**：捕获流的 TOK_LINENUM 混入（改 tok_str_add2）；嵌套宏层的
token 流混用（structInit 不再自建捕获）；切片临时 data 载入的 32 位截断；
pack 区未计入 loc 导致栈帧外写。

**验收**：make 零错误零警告；make test（ANTLR 66/66 + 29/29 + 编译器模式
66/66 + 29/29）rc=0；tests/yh-run 24/24（本机 + 交叉双路径）；
变参 sum(1,2,3)=6、sum()=0；structInit 命名/位置/嵌套/传参全正确。

## 2026-09-27 M3-02 + M4-01 完成：类型检查/复合赋值/数组按值 + 语义测试框架 24/24

## 2026-09-27 M3-02 + M4-01 完成：类型检查/复合赋值/数组按值 + 语义测试框架 24/24

多 agent 并行产出的测试框架（tests/yh-run/，run 15 + fail 6 + pass 3）暴露的
7 个编译器 bug 全部修复，并完成 M3-02 与 M4-01：

- **M3-02**：复合赋值 10 种运算符降糖（vpushv+vrott(3)+gen_op+vstore）；
  赋值/传参/返回的 yh 类型检查；整数字面量 0→指针；字符串字面量退化
  *char；`&x` 补 mk_pointer；比较/逻辑结果统一 bool 类型；main 签名检查
  （无参强制、void 警告）；块级 nocode_wanted 死代码管理。
- **M4-01（ADR-0002 机制 a）**：yh_type.c 新增数组/切片包装结构体登记表；
  形参/返回值/赋值/初始化的数组在调用边界降糖为匿名
  `struct { T a[N]; }`——≤16B 进寄存器、>16B 调用点拷贝、HFA 浮点，
  全部复用现有结构体路径；函数体内下标/len 透明还原数组语义；
  拷贝独立性经实测验证。
- **控制流重写**：switch 每比较发 cbnz（真→块，imm19 回填）+
  b（假→下一比较/no-match，imm26 反向回填），多值 case OR 语义、
  default 位置自由且唯一性检查、块尾无 fallthrough；break/continue
  用深度计数；label 定义恢复可达性。
- **验收**：tests/yh-run 24/24（本机 Mach-O 与 --cross ELF 双路径一致）；
  make test 双模式 rc=0；数组求和 sum=100（拷贝独立性）、switch 多值/
  default、递归 120/55、goto 循环全正确。

## 2026-09-27 本地系统支持：Darwin 原生 Mach-O 输出 + 系统链接

## 2026-09-27 多平台架构整理与优化方案（文档，无代码改动）

- 新建 [docs/02-plan/yh-多平台架构整理与优化方案.md](02-plan/yh-多平台架构整理与优化方案.md)：
  面向 linux/darwin/windows × arm64/x64 共 6 目标。梳理现状分层与 10 个耦合点
  （架构硬编码 tcc.h:138、宿主宏决定输出格式 libtcc.c:805、macho-out.c 仅
  ARM64 重定位、libtcc1 固定 aarch64-linux-gnu、-run 仅 aarch64 宿主等），
  给出差距矩阵、5 阶段方案（抽象统一→x86_64 恢复→Mach-O x64→Windows PE→
  windows/arm64）与逐阶段验证门。
- 关键事实核对：x86_64 后端可自 `git show 0db9fca^:x86_64-gen.c` 恢复；
  tccpe.c/win32 头与导入库可自 `git show ef8db88^:src/formats/tccpe.c`、
  `ef8db88^ win32/` 恢复；`lib/libtcc1.c`、`alloca86_64.S` 仍在 lib/ 中。
- `docs/todo.md` 0.0.2+ 节加入指向该方案的条目。未修改编译器代码，无需构建验证。

## 2026-09-27 本地系统支持：Darwin 原生 Mach-O 输出 + 系统链接

`yh file.yh -o prog` 在 macOS arm64 上直接产出可运行的本机可执行文件，
不再依赖 sysroot/容器。

- **macho-out.c（新建）**：Mach-O MH_OBJECT 写入器——映射 tcc 的
  text/data/bss 节（clang 布局约定：节 addr 段内累计、vmsize 含 bss、
  filesize 只含节内容）、符号表（跳过 STT_SECTION/STT_FILE；MH_OBJECT
  的 n_value 为段内累计地址）、重定位翻译（ABS64→UNSIGNED len3、
  MOVW_UABS_*→ADRP 方案、CALL26→BRANCH26、ADRP/ADD→PAGE21/PAGEOFF12
  并以 ARM64_RELOC_ADDEND 携带偏移）。EXE 由系统 `cc` 完成 libc 绑定与
  ad-hoc 签名。
- **arm64_sym**：Mach-O 模式改用 adrp+add（ld64 不接受 movk 上的
  UNSIGNED 重定位），ELF 路径保持 movw/movk（-run 的 COPY 重定位约束）。
- **Darwin 变参约定**：arm64_pcs_aux 增加 n_named——变参函数（FUNC_ELLIPSIS）
  在 Mach-O 模式下可变实参按 8 字节对齐放栈上（AAPCS64 变体），命名参数
  照常进寄存器；调用点 f32 实参提升为 f64。Linux ELF 路径不受影响。
- **格式选择**：Darwin 上 EXE/OBJ 默认 Mach-O；`-sysroot`（交叉 Linux）
  或显式 `-Wl,-oformat=elf64-aarch64` 恢复 ELF；`-Wl,-oformat=macho64`
  可显式选择 Mach-O。符号名经 leading_underscore 统一加 `_` 前缀。
- **void 函数确定性返回**：void（含无返回类型的 main）在函数末尾
  `mov w0, #0`，退出码可预期（用户的 `fn main(){ printf(...); }` 退出码 0）。
- **环境变量语义**：YH_SYSROOT/YH_LIBDIR 空串视为未设置（默认本机 Mach-O）。
- **验收**：本机 `./yh native.yh -o native && ./native` 输出
  `n=3 g=42 msg=hi`（printf 变参、全局变量、函数调用、字符串字面量）；
  `make test` 双模式 rc=0（66 正例 + 29 反例）；交叉 ELF 路径经容器复验
  输出一致。

## 2026-09-27 修复 -o 链接路径段错误 + sysroot 链接闭环

## 2026-09-27 修复 -o 链接路径段错误 + sysroot 链接闭环

用户报告 `./yh tests/yh/01-toplevel/01_toplevel_decls.yh -o 11` 段错误。根因
与修复：

- **pass 1 误执行代码生成**（崩溃根因）：`yh_parse_binding`/const 只检查语法
  模式未检查遍数，第一遍求值初始化器触碰未初始化的值栈/段状态。现在第一遍
  用 `skip_or_save_block` 按括号配对跳过初始化器，不做任何求值。
- **顶层 let 被当局部栈槽**：新增 `yh_commit_global_var`——data/bss 节分配、
  `put_extern_sym` 登记；pub→GLOBAL、非 pub→VT_STATIC(LOCAL)；初始化支持
  编译期常量（expr_const1，按宽度写节）与字符串字面量（匿名数组落地 +
  R_DATA_PTR 重定位）。
- **yh_compile 缺 tccgen/ELF 初始化**：补 `anon_sym`/`int_type`/
  `char_pointer_type`/`func_old_type` 等初始化与 `tccelf_begin_file/end_file`
  （symtab 哈希合并缺失导致链接期找不到符号）、`tcc_debug_start/end`。
- **main 的 ELF 绑定**：恒为 GLOBAL（crt 入口引用），其余非 pub 为 LOCAL
  （ADR 语义边界 §2/§3 落地）。
- **-sysroot 选项与环境变量**：`-sysroot dir`（或 `YH_SYSROOT`）在链接期
  提供 crt/libc/include 路径（含 Ubuntu multiarch 子目录）；`YH_LIBDIR`
  （或 `-B`）指定 libtcc1.a。缺 crt 时干净退出（rc=1，可读诊断），不再崩溃。
- **调用结果压栈**：gfunc_call 后按 tccgen 惯例 vsetc(REG_IRET) 回填返回值。
- **字符串实参消费**：has_init=2 的 decl_initializer_alloc 自行消费字符串
  token，移除多余的 next()。
- 零警告：修正 tccpp.c 两处历史 -Wstring-plus-int（用数组下标形式）。

**验收**：`make` 零错误零警告；`make test` 双模式 65/65 + 29/29 rc=0；
`YH_SYSROOT=tmp/sysroot YH_LIBDIR=tmp/sysroot ./yh hello.yh -o hello`
产出 AArch64 Linux ELF，容器内运行输出 "hello from yh"；无 main 的语料
`-o` 给出正确的 `undefined symbol 'main'` 链接诊断。

## 2026-09-27 M3 语义编译器接通：名称/调用/语句代码生成 + 全量语料验收

## 2026-09-27 M3 语义编译器接通：名称/调用/语句代码生成 + 全量语料验收

**目标达成**：`yh` 二进制通过 tests/yh 全部 94 个语料——
`make test` 双模式（ANTLR + `yh --syntax-check`）正例 65/65、反例 29/29，
退出码 0；`make` 零错误零警告。

- **yh_builtin.c（新建）**：prelude 八函数（printf/malloc/free/memcpy/
  strlen/exit/open/write）以 extern Sym 直接登记（FUNC_ELLIPSIS 标注裸变参），
  不注入 yh 文本。
- **两遍编译**（yh_decl.c）：第一遍按序登记 type/struct/union/enum 完整
  定义与顶层 fn 签名（external_global_sym；非 pub 带 VT_STATIC→ELF LOCAL），
  函数体 skip_or_save_block 跳过；第二遍重读文件编译全局初始化与函数体。
  类型先声明后引用、函数可前向调用（语义边界文档 §1 落地）。
- **函数框架**（yh_gen_function）：对齐 tccgen gen_function——put_extern_sym、
  gfunc_prolog/gfunc_epilog、局部栈管理、func_vt、调试钩子；void main 返回 0。
- **表达式代码生成**（yh_expr.c）：二元链 gen_op；逻辑与/或短路跳转
  （gvtst/gsym/vseti，模式同 tccgen expr_land/lor）；调用 gfunc_call 后按
  REG_IRET vsetc 压回结果（tccgen 惯例）；成员访问 gaddrof/find_field/
  偏移相加（`.` 对指针自动解引用）；`to_type` 走 §4.1 检查 + gen_cast 且
  结果强制右值；sizeof(T) 编译期 type_size；字符串字面量经
  decl_initializer_alloc 落地为匿名 char 数组。
- **类型系统**（yh_type.c）：struct/union 用 SYM_STRUCT tag + SYM_FIELD
  字段链 + struct_layout 布局；enum 成员为 VT_ENUM_VAL 常量（enum_val 存值）；
  type 别名带 VT_TYPEDEF 入标识符命名空间；数组长度用 expr_const1 编译期
  求值并拒绝非正值。
- **语句代码生成**（yh_stmt.c）：if/else（gvtst 假链 + gjmp/gsym）、条件与
  无限循环（continue 回循环头、break 链 yh_bsym/yh_csym）、switch（判别值
  存临时槽、case 逐值比较、无 fallthrough、default 位置自由且唯一性检查）、
  return（gen_assign_cast(func_vt) + gfunc_return + rsym 链）、goto/label
  （label_find/label_push 前向链）。
- **调试修复**：vset 重复插入导致 vstack leak 3；vstore 后缺 vpop；
  调用后未压回结果导致 "cannot cast from/to void"；纯语法模式误走
  yh_gen_function 导致 "未在第一遍登记"。
- **运行验证**（容器 gcc -no-pie 链接 yh 产出目标）：add(3,4) 退出码 7、
  局部变量/算术/调用全部正确。

## 2026-09-27 M2 完整语法 parser 与双模式回归（M2-01～M2-04）

## 2026-09-27 M2 完整语法 parser 与双模式回归（M2-01～M2-04）

新建四个 parser 文件（合计约 1100 行），按 docs/yh.g4 实现递归下降语法，
与 `--syntax-check` 纯语法模式共用，M3 在同一位置接通编译行为：

- **yh_type.c**：typeRef（指针/数组/切片/函数类型/内建/具名）、内建类型
  映射（i8→VT_BYTE…bool→VT_BOOL、char=u8）、fnType（VT_FUNC + 匿名参数
  Sym 链）、struct/union/enum 声明形态、`yh_tok_starts_type_ref` 返回类型
  省略判定。
- **yh_decl.c**：pub? 顶层分派（let/const/fn/type/struct/union/enum）、
  binding（类型必写）、param（含 `name ... T` 与裸 `...` 形态）、
  `yh_parse_translation_unit` 消费到 EOF、`yh_compile` 入口（yh_mode、
  无 PARSE_FLAG_PREPROCESS、setjmp 错误恢复）。
- **yh_expr.c**：优先级链（YH_BIN_LEVEL 宏逐层展开，与 C 同表）、一元、
  后缀链（调用/下标/`.to_type(typeRef)`/成员访问）、primary（字面量/
  sizeof(T)/len(e)/标识符）、`yh_peek_next_token` 与
  `yh_brace_group_is_literal`（structInit 头部边界算法：捕获-回灌、
  0 终止符自动弹回、非空 + 无 `;` + 深度 0 无语句关键字 + 命名/位置
  形态连贯；保留字字段名 type/len/default 合法）、保留字定向提示
  （while→for、as→to_type）。
- **yh_stmt.c**：block、if（强制括号）/else-if 链、for 三形态（头部
  peek 分派无限/条件/for-in）、for-in parts（单/双目标 + RANGE 区间）、
  switch（case 多值 + default）、return/break/continue/goto、包裹式
  标签（peek 判定 `IDENT ':'`）、exprStmt（11 种赋值运算符）。

调试修复过程：`<`/`>` 需用 TOK_LT/TOK_GT（非 ASCII）；PEEKC 后 p 指向
当前字符（前瞻应传 p+1）；primary 标识符分支漏 `next()` 造成 57 例回归；
嵌套捕获流的 0 终止符级联弹出避免 token 重复；parse_number 指数符号
校验；保留字字段名先于语句关键字检查。

**M2-04**：`tests/yh/check.py` 新增 `--compiler` 模式（调用
`yh --syntax-check`，正例必须接受、反例必须拒绝，按正反分别计数）；
`make test` 现在依序运行 ANTLR 模式与编译器模式。

**结果**：编译器模式正例 65/65、反例 29/29；ANTLR 模式 65/65、29/29；
规则覆盖 68/68。M2 验证门达成（语法通过不等于编译/运行通过，后者在 M3/M4）。

## 2026-09-27 M1-02 yh 词法改造 + M1-03 纯语法入口骨架

**M1-02（tcctok.h / tcc.h / tccpp.c）**：
- tcctok.h：新增 yh 关键字 let/fn/in/pub/true/false/len/to_type/type/as 与
  i8~u64/f32/f64/bool；全部保留字（含复用的 if/for/struct/… 与已移除的
  while/do/unsigned/…/restrict 及 gcc 变体）位于 TOK_UIDENT 边界之前，
  yh 中不可作普通标识符；边界后的 define/include 等 token 值仍可作标识符。
- tcc.h：新增 `TOK_RANGE 0xd0`（`..`）与 `TCCState.yh_mode` 标志。
- tccpp.c（全部按 yh_mode 分支，C 预处理路径保持原样）：
  - `#`/`##` 在 yh 模式直接报错「yh 无预处理」；
  - `case '.'`：yh 下 `..`→TOK_RANGE、`...`→TOK_DOTS、其余为成员点；
    `.5` 不再进入数字扫描（留给 parser 按语法拒绝，与语料注释一致）；
  - 数字扫描重写（yh_num_char）：0x/0b/0o 前缀定进制、下划线必须夹在本
    进制两数字之间、`.` 只在后跟数字时吞入、e/E 只在合法指数起点吞入、
    无任何整型/浮点后缀；`0b12` 切成 `0b1`+`2` 两个 token；
  - parse_number 增加 yh 分支：剔除下划线后按进制转换，无旧式八进制
    （`017`=17），整数按数量级映射 CINT/CUINT/CLLONG/CULLONG，
    浮点一律 TOK_CDOUBLE；修复 `isnum()` 短路导致的 `0b12` 整吞 bug；
  - 转义收敛：\n \r \t \0 \a \b \f \v \' \" \\ + \xNN（恰两位），
    未知转义报错；多字符字符字面量报错；`L` 前缀不再构成宽字符串。
- 验证：65 个正例语料全部通过词法骨架；rejected 中 18/23/26 在词法层被
  定向拒绝，其余反例留给 M2 parser；ANTLR 回归 65/65、29/29 不变。

**M1-03（yh_decl.c）**：`yh_compile()` 接通 `--syntax-check` 骨架：置
yh_mode、不开 PARSE_FLAG_PREPROCESS、以 TOK_NUM|TOK_STR 消费到 EOF，
setjmp 错误恢复与 tcc_compile 同构；不解析符号、不调用 gen_*、不要求 main。
最小正例与词法错误反例红绿验证通过；完整语法解析在 M2 按 g4 逐层替换。

## 2026-09-27 M1-01 构建与 .yh 输入分派

- `make` 改为产出 `yh`、`libtcc.a`、`libtcc1.a`；新增 VERSION 文件（0.0.1，
  修复此前 `-DTCC_VERSION=""` 的问题）。
- `libtcc1.a` 改由独立目标 C 工具链构建（不再用 yh 自举）：自动探测
  aarch64-linux-gnu-gcc → Linux/aarch64 本机 cc → clang（非 Linux 宿主自动加
  `-target aarch64-linux-gnu`）；macOS BSD ar 拒绝 ELF 成员，归档器自动选用
  clang 同目录的 `llvm-ar`。工具链全缺失时给出明确 $(error) 诊断。
- `lib/lib-arm64.c` 改为 freestanding（自带 typedef 与 memcpy 声明，不再包含
  目标 libc 头文件）；`__clear_cache` 在非 tcc 工具链下改用
  `__builtin___clear_cache`，消除 M0-02 发现的未定义符号。宿主 clang 交叉与
  容器 gcc 双路径均零警告，产物为 AArch64 Linux ELF 归档成员。
- 驱动：`.yh` 后缀进入 `yh_compile()`（AFF_TYPE_YH 分派，yh_decl.c 新建）；
  非 .yh 用户源文件（如 .c）被驱动明确拒绝（exit 1）；`--syntax-check` 选项
  注册（TCC_OUTPUT_SYNTAX 输出类型），yh 解析器本体留给 M1-03/M2。
- yh 骨架：`src/core/yh.h`（共享声明）与 `yh_decl.c`（入口）。
- 驱动行为验证：`.yh` 进入 yh 路径、`.c` 被拒、`yh -v` 报 0.0.1；`make test`
  运行 ANTLR 语料回归（65/65、29/29）。

## 2026-09-27 M0 前置验证完成

- **M0-01**：基线记录于 `tmp/m0/`（make / make test / check.py --coverage 输出与
  调用关系 `tmp/m0/call-graph.md`）。65 正例 / 29 反例 / 68 规则覆盖全过；
  Darwin `make test` 只跑 pp 套件（tests2 需 Linux，符合预期）。
- **M0-02**：Docker 容器（ubuntu:24.04，aarch64 原生）验证 AArch64 Linux
  工具链、crt、动态加载器；`lib/lib-arm64.c` 可由容器 gcc 产出 AArch64 Linux
  ELF 归档（发现 `__arm64_clear_cache` 在 gcc 下是未定义符号，tcc 内建，
  M1 需替换 `__builtin___clear_cache`）。带 `-DCONFIG_SYSROOT/-DCONFIG_TRIPLET`
  的 tcc 在 Darwin 直接产出可运行 Linux ELF；容器内 gcc 构建的原生 tcc
  `-run` 全链路通过。记录 `tmp/m0/m0-02.md`；最小 sysroot 在 `tmp/sysroot/`。
- **M0-03**：`tmp/abi/` 探针实测（tcc/gcc 双编译、输出一致）：机制 a
  （包装结构体）完整覆盖 ADR-0001 矩阵；切片 16B 结构体参数/返回正确；
  实测 `gfunc_call` 断言边界（对齐后 ≥4096B 触发，4080B 通过）。决定采用
  机制 a，4KB 断言在 M4-01 修后端（不设语言上限），见新
  [ADR-0002](adr/0002-yh数组与切片内部ABI机制.md)。
- **M0-04**：语义边界定案写入
  [docs/03-design/00-语义边界-0.0.1.md](03-design/00-语义边界-0.0.1.md)：
  先扫描顶层函数签名、`fn main() int` 无参、pub 的 ELF 绑定语义、字符串
  字面量可写（.data）、零长度数组拒绝、数组同型赋值=值复制、切片不做边界
  检查、裸变参提升规则与 prelude 八函数签名。同步修正 `docs/yh.g4` prelude
  注释（8 函数 + 直接登记 extern Sym）；`check.py --coverage` 复跑全过。

## 2026-09-27 yh 0.0.1 三份文档执行计划整理

- 将 `docs/02-plan/yh-0.0.1-改造方案.md` 展开为 M0～M6、逐任务编号、依赖顺序、验证门和动态语料验收口径；当前 94 个语料只作为基线。
- 将 `docs/todo.md` 收敛为同编号的任务清单，移除重复的早期探索排期；保留 0.0.2+ 待设计事项。
- 将 `docs/adr/0001-yh数组按值调用边界.md` 明确为已接受的语言/互操作边界；M0 用 C 代理探针选择内部机制，M4 用真实 `.yh` 用例验证，不混淆两类证据。
- 本次是文档整理，没有修改编译器代码；构建和运行验收仍属于后续 M0～M6 任务。

## 2026-09-27 类型转换语法改为 `to_type`

- 将 `x as T` 改为后缀语法 `x.to_type(T)`；目标参数仍按 typeRef 解析，允许链式转换及转换后直接取下标/成员。
- `to_type` 是专用后缀关键字，旧 `as` 转换写法报语法错误；同步改造方案、待办和 `.yh` 语法语料。旧版修订记录中的 `as` 示例保留为历史记录。
- `tests/yh` 正例 65/65、反例 29/29，68/68 条规则标注覆盖；69 个歧义探针零真歧义、零预期外结果。`make` 与 `make test` 通过；Darwin 上 `make test` 按现有规则只运行 pp 套件。
- 当前编译器 `src/` 仍未实现 `.yh` 解析；本次验证对象是参考语法和语料，编译模式的 `to_type` 语义检查仍在待办中。

## 2026-09-27 类型转换方案补全

- 在 `docs/02-plan/yh-0.0.1-改造方案.md` 增加转换矩阵：字面量与无损提升、显式数值和指针转换、数组/切片视图、拒绝无长度指针转切片。
- 明确 `as` 先做 yh 语义检查且结果为右值；TCC 的警告和 `gen_cast` 不能代替准入检查。同步 M3/M4 验证门与 `docs/todo.md`。
- 本次只修订计划文档，没有实现编译器转换检查；现有 `tests/yh/08-expr/06_cast.yh` 仍是纯语法用例。

## 2026-09-27 yh 0.0.1 改造方案评审修订

- 核对构建、驱动、语法语料和 AArch64 参数分类；修订 `docs/02-plan/yh-0.0.1-改造方案.md` 的架构假设、降糖、阶段顺序与验证门。
- 将 `.yh` 文件识别、C 运行时构建、数组/切片 ABI、纯语法检查、prelude 符号登记列为实现前置事项，并同步 `docs/todo.md`。
- 本次仅修改文档；编译器实现和运行测试仍列为后续任务。
- 将迁移遗留的测试后缀要求统一为 `.yh`，与唯一用户源文件后缀一致。

## 2026-09-27 语法参考（docs/yh.g4）歧义分析与无歧义修订

### 背景

对 docs/yh.g4 做歧义分析：用本地 ANTLR 4.13.2（`~/.m2/repository/org/antlr/antlr4/4.13.2/antlr4-4.13.2-complete.jar`）生成 parser，31 个探针用例实测。结论：原语法**无真歧义**（同一 token 序列两棵合法语法树的情况不存在），但发现 1 个实锤缺陷、多处注释与语法不符、若干 spec 缺口。分析过程与全部探针保留在 `tmp/antlr-check/`。

### 已落地的修订（全部经 ANTLR 实测验证）

1. **memberName：成员位置放开保留字**（实锤缺陷修复）
   - 原 grammar 中 `in`/`as`/`len`/`sizeof`/`type` 等被隐式关键字化且优先于 IDENT，导致 `p.len` / `p.type` / 字段名 `type` 全部语法错误。
   - 新增 `memberName` 规则，用于 fieldDecl / structInitField / postfixPart 三处；局部/全局标识符位置仍严格。
2. **exprStmt 收紧为单目标赋值**：`expr (assignOp expr)? ';'`，`a, b = 1, 2;` 不再合法（v0.1 无元组赋值）。
3. **labelStmt 必须后随语句**：`IDENT ':' stmt`，悬空标签 `L: }` 报错（同 C）。
4. **转义收敛**：STRING/CHAR 统一转义集合 `\n \r \t \0 \a \b \f \v \' \" \\` + `\xNN`；未知转义（`\q`）词法报错，不再静默吞掉。
5. **NUMBER 下划线规则**：必须夹在数字之间；`1_` / `1__0` / `0b_1` 报语法错误。
6. **显式词法规则 RANGE `..` / ELLIPSIS `...`**：手写 lexer 有明确对照。
7. **WS 扩充** `[ \t\r\f\u000B]+`：CR-only / 表单符文件不再词法报错；CRLF 仍按 NL 整体成词。

### 注释修正（语法行为不变）

- structInit 注释重写：删除失效的 `if flag {}` 例子（if 强制括号，本就非法）；分离「命名式 vs 位置式」与「字面量 vs 块」两个消歧问题；给手写 parser 定下头部边界算法（花括号配对 + 窥探下一个 `{`，贪心取字面量，与 ANTLR ALL(*) 判定一致）。
- castExpr 处新增结合性备忘：`a as b * c` = `(a as b) * c`、`a as *b` 为指针、`(x as T)[i]` 须加括号、`-x as int` = `(-x) as int`、`**` 非幂（`**p` 双重解引用合法，不可封禁）。
- returnStmt 注明会吞掉下一行开头的表达式（NL 隐藏通道，同 C）。
- switchCase 注明 default 位置无语义、至多一次靠语义检查。
- structInitBody 注明尾逗号策略：逐行列表允许、行内列表不允许。
- sizeofExpr 注明只收类型及理由。
- 文件头设计前提补充保留字策略（标识符位置严格 / 成员位置宽松）。

### 验证

- 修订稿生成 / 编译零警告；31 探针：21 个预期通过全过，10 个预期报错全部按设计响亮报错（`tmp/antlr-check/final/` 可复现）。
- 6 个 for/switch 头部边界用例（含 `switch Point{1,2} { case 1 {} }`、关键字字段名场景）`-diagnostics` 歧义检测 0 报告。
- 一次誊写回归（NUMBER 指数组 `?` 丢失导致 11 用例失败）已由探针矩阵当场捕获并修复——探针集同时充当回归测试。

### 后续

编译器实现（src/ 手写 lexer/parser）同步清单见 docs/todo.md。

# 2026-09-28 yh 语法与编译器自举方案（文档）

- 新增 `docs/03-design/yh-自举能力边界.md`：区分语法自举、编译器自举与工具链完全自给；规定最小输入接口、目标平台和三代验收。
- 新增 `docs/02-plan/yh-语法与编译器自举方案.md`：记录现状缺口、推荐路线、B0–B6 阶段和验证门；同步 `docs/todo.md`。本项仅编写方案，未修改编译器代码。

# 2026-09-28 yh 0.0.2 自举 B0–B2（种子冻结、输入接口、工作负载验证）

## B0 定位与修复测试基建

- **22/24 复盘定性**：07-goto-label「无法暂存目标文件」= 多进程并发
  共享产物目录时 `macho-out.c` 的 `rename` 竞态（4 个并发 check.py
  实例复现，20/24）；08-recursion 信号 9 未能复现（150 次编译+运行
  压力、3 次套件全绿），定性为环境性 kill。单进程与交叉路径均无缺陷。
- `macho-out.c` rename 失败信息补充 `strerror(errno)` 并提示并发触发
  场景；新增 `--workdir` 隔离后并发 4 实例全绿。
- `tests/yh-run/check.py` 新增 `--compiler`/`--workdir`（自举差分用），
  产物缺省迁移 `tmp/yh-run-work/`；新增 `stdin-hex:`/`argv:` 注入
  （交叉模式经 `docker exec -i`）。`tests/yh/check.py` 新增
  `--compiler-path`/`--workdir`。旧 `tests/yh-run/work/` 已删除。
- 缺口矩阵：`docs/02-plan/yh-运行覆盖缺口矩阵.md`（G01–G17，B2 后全部补齐）。

## B1 输入接口与语义修复

- prelude 登记 `read(fd int, buf *void, count u64) i64` 与
  `close(fd int) int`（共 10 个），同步 `docs/yh.g4` 与语义边界 §7。
- 放宽 `main` 为 `()` 或 `(argc int, argv **char)`；错误签名仍拒绝。
- 期间发现并修复 4 个语义缺陷（均有语料正例佐证但语法套件测不出）：
  ① `true/false` 推为 int → 改为 bool；② 整数字面量无法窄化
  （§4.1）→ 可表示字面量隐式允许 + 全局初始化范围检查（`let x u8 =
  300` 从静默截断改为报错）；③ 数组左值传 `*void` 不退化（坏指针/
  SIGBUS）→ 转换前左值退化；④ 裸变参小整数缺 C 默认提升
  （i8 打印 254）→ i8/i16/u8/u16/bool → int。
- 用例：run/16-18（read 分块/短读/NUL 计数/EOF/坏 fd/open-close）、
  run/19（bool+字面量窄化+提升）、run/20（字节缓冲：1 字节分配、
  扩容边界、NUL、1 MiB 逐字节一致、2^63 分配干净失败）、fail/07-08。

## B2 工作负载与容量验证

- 新增探针 run/22-29：函数指针（赋值/回调/返回选择）、u32/u64 位移与
  符号扩展、互递归、malloc 链表+全局指针写、struct 按值/大 struct、
  union/enum、数组按值/递归/切片视图/for-in、类型化变参/浮点、容量
  压力（1439 行，200 包装类型+129 case 值+约 200 字符标识符）。
- 期间发现并修复 5 个编译器缺陷：⑤ 函数名无法赋给 fn 类型 → 同签名
  fn 隐式转换（签名结构相等）；⑥ struct/数组按值返回调用缺隐藏返回
  指针（断言/段错误，**M4 数组返回从未真正运行过**）→ 调用方压 sret
  临时+结果取临时左值；⑦ 浮点返回误取 x0 → 取 v0（REG_FRET）；
  ⑧ 调用结果（包装 struct）赋回数组变量被拒/只拷 8 字节 → 包装→数组
  同型允许且 vstore 走块拷贝；⑨ switch 分支数组固定 128 超限静默截断
  → 扩 512+干净报错；包装类型上限 128 → 512（超限本就报错）。
- 用例：fail/10（数组长度不匹配）、fail/11（513 case 值干净报错）、
  fail/12（513 包装类型干净报错）。

## 验证

- `make` 零警告；`make test`：语法 66/66+29/29、运行 44/44
  （run 29/29、fail 12/12、pass 3/3）；`check.py --cross` 44/44。
- 下一步：B3（用 yh 写出能解析自身的前端）。
