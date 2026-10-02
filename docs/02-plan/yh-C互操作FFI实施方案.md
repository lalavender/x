# yh–C 互操作（FFI）实施方案

- 状态：**草案**（待确认；开工前先落 ADR-0010）
- 日期：2026-10-01
- 关联：[ADR-0001 数组按值调用边界](../adr/0001-yh数组按值调用边界.md)、
  [ADR-0002 数组与切片内部 ABI](../adr/0002-yh数组与切片内部ABI机制.md)、
  [docs/yh.g4](../yh.g4)（prelude 注释段）

## 1. 目标与非目标

**目标（v1）**

1. 用户可在 yh 源码里**声明外部 C 函数与全局变量**并直接调用/引用
   （替换「只有编译器内置 prelude 能登记 extern 符号」的现状）；
2. 用户可把 yh 函数/全局变量**导出为 C 可见的裸名符号**，
   C 代码能按名调用、能拿函数指针当回调；
3. `yh build` 能把 **C 源文件/预编译对象/系统库**一起编进链接命令；
4. yh 与 C 两侧的结构体**共享同一定义**（同一布局，各自声明一次）。

**非目标（v1 明确不做）**

- ≤16 字节结构体（含 HFA）按值跨 C 边界——ABI 不兼容，v1 直接编译报错（§4）；
- 切片 `[]T` 跨边界——yh 内部表示无 C 对应（ADR-0002）；
- 单文件命令 `yh f.yh -o out` 混编 C 源（需要混编时建项目即可）；
- `yh build --lib` 产出 .so/.a（列 R4 可选）；
- 自动解析 C 头文件（永不做；方向是 yh→C 生成头，见 R4）。

## 2. 现状盘点：地基大部分已在

| 已有基础 | 证据 | 对 FFI 的意义 |
| --- | --- | --- |
| extern 符号机制 | `F_EXTERN` 标志；prelude 经 `sym_push_lit(..., F_EXTERN\|F_PUB)` 登记（gen/symbols.yh:932） | 用户 extern 声明复用同一登记路径 |
| 裸变参调用 | prelude `printf(fmt *char, ...)`，调用点走 va_list 发射 | 用户 extern 声明放开裸 `...` 即可用 |
| extern 调用发射 | `em_sym_qualify` 对 F_EXTERN 免加模块后缀（gen/emit_arm64.yh:299） | extern 函数跨模块命名已正确 |
| 结构体布局与 C 一致 | `tg_layout_struct`：声明序 + 标量 align=size + 聚合递归 + 尾填充（gen/target.yh:87） | **零改动**，两侧各写一次定义即天然对上 |
| 大聚合传参 = AAPCS64 | 调用点拷贝 + 指针传递（`F_AGGPARAM`）、聚合返回走 x8 隐藏指针 | >16B 结构体按值跨边界**双向天然兼容** |
| 链接走系统 cc | `.s → gcc/clang -c → .o → gcc/clang 链接`（cmd/module_build.yh `mb_link`） | C 对象/库混链零障碍 |
| 函数即地址 | 裸函数名引用发 `em_lea_global` 且 `c_res_is_addr=1`（gen/sem_value.yh:262）；fn 类型与间接调用已有 | 回调（把 yh 函数指针交给 C）有现成路径 |
| Darwin 符号约定 | 发射器按方言加 `_` 前缀、外部走 GOT（gen/target.yh） | extern 调 libc 已在用，导出同规则 |

**缺口**（本方案要补的）

1. `extern` 是保留字（TK_RESERVED）但无用户语法；`fnDecl` 必须带函数体，
   用户无法声明外部函数/变量（docs/yh.g4 prelude 段写明「用户源码不允许函数原型」）；
2. 无法引用外部 C 全局变量（errno/environ/自定义 C 全局）；
3. 模块模式下非入口模块符号一律加 `__proj__mod` 后缀，C 无法按裸名调用，
   也无「显式导出」标记；
4. `project.toml` 无 C 源/对象/库入口，链接命令拼装固定；
5. ≤16B 结构体按值跨边界无人拦截（会静默产出错误 ABI）。

## 3. 语法设计（v1）

原则：**`extern` 复活为声明关键字**，一个词两种形态——无体/无初值 = 引用 C 侧；
带体/带初值 = 导出到 C 侧。`pub` 语义不变（模块内可见性），与 C 边界正交。

```yh
// —— 形态 1：引用 C 侧（yh 调 C）——
extern fn abs(x int) int;                 // 外部函数声明：无体，; 结尾
extern fn printf(fmt *char, ...) int;     // 裸 ... 变参放开（机制同 prelude）
extern let environ **char;                // 外部全局变量：无初值 = 引用，不分配存储

// —— 形态 2： 导出到 C 侧（C 调 yh）——
pub extern fn yh_from_c(x int) int {      // 带体定义：发射正常代码，
    return x + 1;                         // 但符号免加 __proj__mod 后缀（裸名）
}
pub extern let counter int = 0;           // 带初值定义：正常进 .data，裸名导出
```

语义细则：

- `extern` 声明（形态 1）**不分配存储、不发射定义**，链接期由 C 侧解析
  （函数路径已有，全局变量需给 bss/data 收集补 F_EXTERN 跳过）；
- `extern` 定义（形态 2）正常编译进本模块，新标志 `F_CEXPORT` 只控制
  「免加模块后缀」（em_sym_qualify / dat_ / bss_ 三处各加一个豁免分支）；
- 与 prelude 同名（如用户声明 `extern fn malloc(...)`）：签名一致则幂等通过，
  不一致报重声明错误；
- `extern fn` 带体 + `extern let` 带初值才允许 `pub?` 前缀；纯声明不允许
  `pub`（引用符号本就是全局的，避免无意义组合）；
- 保留字拆分：`extern` 从 TK_RESERVED（41）桶里拆出为新 token `TK_EXTERN`（44，
  模块关键字区之后），不作标识符、不放开成员名；
- `extern` 不可修饰局部声明，仅顶层。

## 4. 类型映射与跨边界 ABI 规则

### 4.1 类型映射表（AArch64，GNU/Linux 与 Darwin 同构）

| yh | C | 大小/对齐 | 说明 |
| --- | --- | --- | --- |
| `void` | `void` | — | 仅返回/指针目标 |
| `bool` | `_Bool` | 1/1 | |
| `char` | `unsigned char` | 1/1 | yh char 常量域 0..255；arm64 上 C plain char 同为无符号 |
| `i8`/`u8` | `int8_t`/`uint8_t` | 1/1 | |
| `i16`/`u16` | `int16_t`/`uint16_t` | 2/2 | |
| `int`/`i32`/`u32` | `int32_t`/`uint32_t` | 4/4 | yh `int` 即 C `int` |
| `i64`/`u64` | `int64_t`/`uint64_t` | 8/8 | `u64` 对 C `size_t` |
| `f32`/`f64` | `float`/`double` | 4/4、8/8 | 参数走 v0..v7，发射器已有 |
| `*T` | `T *` | 8/8 | 含 `*void`、`**char` |
| `[N]T` | `T[N]` | 布局相同 | 按值仅限 yh 函数间（ADR-0001 决定 3） |
| `struct`/`union` | `struct`/`union` | 布局相同 | 见 §4.2 尺寸规则 |
| `enum` | C `enum`（int 底层） | 4/4 | |
| `fn(...) r` | 函数指针 | 8/8 | 回调用，见 §7 |
| `[]T` 切片 | **无对应** | — | 跨边界编译报错 |

### 4.2 结构体/联合体跨边界规则（v1 核心限制）

1. **布局一致性无需任何改动**：`tg_layout_struct` 的「声明序 + 自然对齐 +
   尾填充」就是 AAPCS64 C 的布局规则；yh 无位域/packed/自定义对齐，
   不存在失配面。
2. **按值传递/返回只允许 size > 16 字节且非空的 struct/union**：
   - AAPCS64 对 >16B 合成类型的处理正是「调用方拷贝 + 传指针、返回走 x8
     隐藏指针」，与 yh 现行聚合 ABI（ADR-0002 机制 b）逐位相同；
   - ≤16B 合成类型 C 传寄存器（整数合成拆 x 寄存器、HFA 拆 v 寄存器），
     yh 传指针——**不兼容，编译报错**，提示「传 `*Struct` 或改用 >16B」；
   - 检查点在 extern 边界：extern 声明的签名、以及对 extern 函数的实参/
     返回类型（直接调用即可拦住；函数指针经 fn 类型同样校验）。
3. **数组/切片禁止按值跨边界**（维持 ADR-0001 决定 3）；传 `*T` /
   `*[]T`？——切片指针本身是 `*T`，长度由 C 侧另行传（惯例 `ptr, len` 双参数）。
4. **字符串字面量即 `*char`**（NUL 结尾），直接传给 C，现状已兼容。
5. 裸 `...` 变参仅允许出现在 `extern fn` 声明（va_list 调用发射已验证于
   prelude printf）；类型化变参 `a ... T` 是切片 ABI，禁止出现在 extern 声明。

> 返回 >16B struct 给 extern 函数：yh 调用方需为 x8 隐藏返回分配缓冲并拷入
> 局部槽——与调 yh 聚合返回函数同一路径，R1 实测确认，不兼容再单列修复。

## 5. 符号、导出与模块接口

| 形态 | 符号 | 存储 | 模块模式命名 |
| --- | --- | --- | --- |
| `extern fn f(...);` | `SYM_FN` + `F_EXTERN` | 无 | 裸名（现有豁免） |
| `extern let g T;` | `SYM_VAR` + `F_GLOBAL\|F_EXTERN` | 无（跳过 bss/data 登记） | 裸名（复用 F_EXTERN 豁免，bss 收集补判断） |
| `pub? extern fn f(...) {...}` | `SYM_FN` + `F_CEXPORT` | 正常 .text | 裸名（qualify 三处加 F_CEXPORT 豁免） |
| `pub? extern let g T = v;` | `SYM_VAR` + `F_CEXPORT` | 正常 .data/.bss | 裸名（同上） |

- **接口文件（.s.i）需携带 CEXPORT 标记**：消费者加载接口时的 pub 名字改写
  （iface.yh `sym_mangle`）必须跳过 CEXPORT 符号，否则接口短名与对象裸名失配；
- CEXPORT 与 `pub` 正交：同时是模块可见符号 + C 裸名符号；
- 冲突处理交给链接器（两个模块导出同名 → 重复符号错误，与 C 相同）；
- 单文件模式：一切 `pub`/`fn` 本就是裸名全局符号，`extern` 定义形态行为不变
  （main 由 crt 引用裸名的既有约定不动）。

## 6. 构建集成

`project.toml` 新增可选 `[c]` 段（无段 = 行为完全不变）：

```toml
[project]
name = "demo"
version = "0.1.0"

[c]
sources = ["c/shim.c"]            # 与 yh 模块一起增量编译进 .build/obj/
objects = ["vendor/prebuilt.o"]   # 预编译对象/静态库，直接进链接命令
libs    = ["m", "pthread"]        # 链接追加 -lm -lpthread
```

- C 源用与链接同款 cc（GNU 用 `gcc`、Darwin 用 `clang`）`-c` 编译，
  内容指纹进现有对象缓存（`mb_hash` 体系，CFLAGS 变更参与哈希）；
- 链接顺序：yh 模块 .o → C .o/objects → `-l*`（库在后，符号解析从左到右）；
- `yh run`/`yh build` 全部生效；`yh check` 不编译 C（只查 yh 语义）；
- 单文件模式 v1 不混编 C，但 extern 声明调 libc 立即可用（libc 本来就链）。

## 7. C 调 yh：头文件与回调

v1 头文件**手写**（布局已兼容，照抄字段即可）：

```c
/* demo.h —— 与 yh 侧 struct Point/导出函数逐字段对应 */
typedef struct { long a, b, c; } Big;          /* 24B > 16B，可按值 */
extern int  yh_from_c(int x);
extern int  the_counter;                        /* yh: pub extern let counter int = 0 */
typedef void (*yh_cb)(int);
extern void c_register(yh_cb f);                /* C 侧收 yh 函数指针 */
```

回调（yh 侧）：

```yh
pub extern fn yh_on_event(code int) int { ... }   // 导出
extern fn c_register(f *fn(int) int) void;        // C 函数指针参数
fn main() int {
    c_register(yh_on_event);                      // 裸函数名即地址（现成机制）
    return 0;
}
```

R4 可选：`yh cheader -o out.h` 从 CEXPORT 符号与可达 pub 类型自动生成
上述头文件（枚举字段类型链，生成顺序稳定保证缓存友好）。

## 8. 实施阶段与验证门

| 阶段 | 内容 | 验证 |
| --- | --- | --- |
| **R0** | 落 ADR-0010（extern 边界标记 + >16B 聚合限制 + 切片禁跨边界），更新 docs/yh.g4（§附录 A） | 语法无歧义自查 + ANTLR 校验 |
| **R1** | 引用侧：TK_EXTERN 拆分、extern 声明解析、F_EXTERN 函数/全局登记（bss 跳过）、>16B/切片/数组边界检查与诊断 | `make`；tests/yh-run 新增 libc 调用用例与 reject 用例全绿 |
| **R2** | 导出侧：F_CEXPORT、qualify 三处豁免、接口文件标记、extern 定义形态 | `make test`；cinterop 项目 build + nm 断言裸名；固定点含新语法 |
| **R3** | 构建混编：[c] 段解析（cmd/toml.yh）、C 源编译入缓存、链接拼装、build-check.py 新增 cinterop 用例（run 型端到端往返） | `make selfhost-native` 全绿 |
| **R4** | `yh cheader`（可选）+ 文档刷新（03-design 语法文档、README 用法、yhspec） | 文档与实测逐项对照 |

每阶段按 AGENTS 约定：先 g4/计划 → tests 用例 → 实现 → `make`/`make test`，
R1–R3 完成后各刷一轮 `docs/finish.md`。

## 9. 测试计划

- `tests/yh-run/run/`：`capi-extern-libc.yh`（extern 声明调 `puts`/`atol`/`abs`
  并断言输出）、`capi-variadic.yh`（用户 extern 声明变参调 `printf`）、
  `capi-large-struct.yh`（>16B struct 按值 extern 往返）；
- `tests/yh-run/fail/`：`capi-small-struct-byval.yh`（≤16B 按值报错）、
  `capi-slice-across.yh`（切片跨边界报错）、`capi-array-byval.yh`（数组按值报错）、
  `capi-extern-local.yh`（extern 修饰局部报错）；
- `tests/modules/projects/cinterop/`：完整往返 fixture——C 侧 `shim.c` 提供
  `int the_answer = 42;`、`int c_double(int)`、`Big c_bump(Big)`、
  `c_register(cb)`；yh 侧 extern 引用 + CEXPORT 导出被 C 回调；project.toml
  带 `[c]` 段；`build-check.py` 注册为 run 型用例；
- reject 语料同步进 `tests/yh-run/fail/`（编译期诊断，非运行期）。

## 10. 权衡与风险（明示取舍）

1. **≤16B 结构体按值禁令**：正确性优先于表达力。实现寄存器拆分打包
   （x0/x1、HFA 的 v 寄存器）是 R5 级别工作量，且要同时覆盖调用与返回两侧；
   v1 用「传指针 / >16B」规则换取小改动与零静默错误。
2. **导出靠显式 `extern` 标记而非「入口模块默认裸名」**：显式可读、
   不改变现有模块命名规则与固定点行为；代价是多写一个词。
3. **手写 C 头文件（v1）**：布局兼容所以成本可接受；自动生成（R4）做完前，
   头文件漂移靠 cinterop 往返用例兜底。
4. **Linux CI 依赖**：AGENTS 已注明 Linux 版 yh 待发布归档；本方案全部特性
   在 macOS（clang + libc）即可开发验收，`[c]` 段与 gcc 路径用同一 cc 抽象，
   Linux 落地时零语义差异。
5. **固定点风险**：新语法进入编译器源码后，两代固定点会自然覆盖它
   （新 yh 编译含新语法的自身源码）；种子回滚到不含 FFI 的旧种子时，
   新语法源码不可编译——与所有语法演进同一约束，无需额外机制。

## 附录 A：docs/yh.g4 草案 diff（R0 落地）

```antlr
topLevelDeclBody
    : letDecl
    | constDecl
    | fnDecl
    | externDecl          // 新增
    | typeDecl
    | structDecl
    | unionDecl
    | enumDecl
    ;

// extern：无体/无初值 = 引用 C 侧；带体/带初值 = C 裸名导出。
// 仅顶层；裸 ... 变参仅此处放开（与 prelude 同机制）。
externDecl
    : 'pub'? 'extern' 'fn' IDENT '(' paramList? ')' typeRef?
      (block | ';')       // 带体 = 导出定义，';' = 引用声明
    | 'pub'? 'extern' 'let' IDENT typeRef ('=' expr)? ';'   // 带初值 = 导出定义
    ;
```

`removedKeyword` 桶中移除 `'extern'`；`memberName` 维持不放开 `extern`。

## 附录 B：cinterop fixture 骨架（R3 落地）

```
tests/modules/projects/cinterop/
├── project.toml        # [c] sources=["c/shim.c"]
├── c/shim.c            # the_answer / c_double / c_bump / c_register
├── mod.yh              # extern 引用 + pub extern fn 导出（被 C 回调）
└── main.yh             # 调 c_double/c_bump，注册回调，读 the_answer，printf 断言
```

验收：`yh run` 输出含全部断言值；`nm .build/obj/*.o` 含裸名 `yh_from_c`；
破坏 `shim.c` 再构建触发 C 对象缓存失效并恢复。
