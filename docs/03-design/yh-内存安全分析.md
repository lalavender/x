# yh 内存安全分析（安全性评审报告）

修改时间：2026-11-12

状态：**分析（只读评审，本文件不含任何代码改动）**

分析对象：仓库 `compiler/`（自举编译器，yh + LLVM 后端）、`libs/`（标准库）、
以及编译器为每个用户程序生成的运行时（`compiler/backend/llvm_runtime.yh` 发射的
`__yh_runtime_malloc`/`__yh_runtime_free`/`memcpy`/`memset`/`strlen`/`printf`）。

所有"已验证"条目都是在本机用仓库自带的 `./yh`（`yh 0.0.14`，Darwin arm64）
实际编译并运行复现语料得到的结论；每条都给出可重放的源码与命令。
"静态推断"条目只做了代码阅读，未构造复现。

## 1. 范围、威胁模型与假设

威胁模型按两条边界分别评估：

1. **编译器自身**（`./yh` 处理不可信 `.yh`/`project.toml` 输入时，进程内是否
   发生越界读写、空指针解引用、栈耗尽）。这是最接近"可利用漏洞"的一侧：
   输入由攻击者构造，崩溃发生在开发者/CI 机器上。
2. **生成的用户程序**（语言语义是否给用户提供任何内存安全防线，误用后是
   崩溃、静默破坏还是可被利用）。这一侧的语言决定已有多处 ADR 约束，
   本报告只描述现状与可静态加固的空间，**不推翻既有决定**。

假设（若与后续决定不符，请指出）：

- `yh` 版本以 `./yh --version` 为准（本次 `yh 0.0.14`），darwin-arm64 宿主。
- 语言层面"无运行时边界检查/无生命周期运行时防护"是 **ADR-0001 与
  `docs/todo.md`「设计决定不做」已明确接受的决定**；本报告不把它当缺陷，
  只在"编译期本文已经知道的事实"上提出静态加固。
- 不在本次范围内：链接器/CodeSign 逻辑、网络与 HTTP 标准库、TOML/JSON
  语义正确性、构建缓存键审计（`docs/03-design/yh-缓存键审计.md` 已单独覆盖）。

## 2. 结论摘要

| 编号 | 严重度 | 现象 | 证据 |
| --- | --- | --- | --- |
| S1 | 高 | 常量下标越界**无任何诊断**（`let a [4]u8; a[4]=1; a[-1]=2` 编译通过并运行） | 已验证 |
| S2 | 高 | 切片范围不校验（`a[0..16]` 对 `[4]u8` 生效，`len(bad)==16`，`bad[100]` 读出相邻栈字节） | 已验证 |
| S3 | 高 | 栈/堆越界之后无任何检测：栈数组越界 32 字节后程序继续执行；16 字节堆分配越界写 4000 字节**完全静默** | 已验证 |
| S4 | 中高 | 编译器解析语句/类型的递归**无深度守卫**，约 100 KB 源码即可让 `./yh` 栈耗尽 SIGSEGV（无诊断） | 已验证 |
| S5 | 中 | `printf` 格式串与实参不匹配不报错，`%s` 会解引用未初始化槽里的垃圾指针（信息泄露/崩溃） | 已验证 |
| S6 | 中 | 数组长度上限 2^31-1，`let a [1000000000]u8` 编译通过 → 运行时 1 GB `alloca` → SIGSEGV | 已验证 |
| S7 | 中 | 悬垂栈指针（`return &local[0]`、切片逃逸）编译通过且"看起来正常" | 已验证 |
| S8 | 中 | `malloc` 后 `free` 两次 / 使用已释放内存 → 立即 SIGSEGV（无检测、无诊断） | 已验证 |
| S9 | 低 | 近邻无判空的 `malloc` 共 15 处：编译器 3 处复核后是统一判空（假阳性），标准库 12 处 `malloc(8)` 取值器确实不判空；OOM 时崩溃而非诊断 | 静态 |
| S10 | 低 | 尺寸/容量计算用 32 位 `int`，`read_source` 在约 1 GiB 边界 `cap * 2` 回绕 | 静态 |
| S11 | 低 | `free` 只读头部长度、忽略 `munmap` 失败；头部 16 字节仅用 8 字节、无魔数 | 静态 |
| — | 正面 | 算术 UB 基本被消除（除零/`INT64_MIN/-1`/超大移位均有定义行为） | 已验证 |
| — | 正面 | 词法器边界纪律完整（逐函数复核，所有 `data[i]` 都有 `i < length` 前置） | 静态 |
| — | 正面 | 编译期（`$`）指针模型有界（span 校验 + 步数上限），不是裸地址空间 | 静态 |
| — | 正面 | JSON/TOML 解析深度上限、check/lower 循环栈上限、缓存内容寻址校验 | 静态 + 已有用例 |

一句话结论：**"静默内存破坏"的风险集中在语言侧（S1/S2/S3/S7/S8），
"可利用性"风险集中在编译器侧（S4 是唯一由小输入触发的进程级崩溃）**；
运行时分配器与后端算术反而做得比同类玩具编译器严谨。

## 3. 已验证问题

复现语料放在 `tmp/sec-audit/`（`tmp/` 已被 `.gitignore` 忽略，不随提交）。

### S1 常量下标越界无诊断（高）

```yh
module idx

fn main() int {
    let a [4]u8
    a[4] = 1        // 越界写 1 字节
    a[-1] = 2       // 越界写 1 字节（数组之前的栈字节）
    printf("no diagnostic\n")
    return 0
}
```

```sh
./yh idx.yh -o idx && ./idx        # 输出 no diagnostic，退出码 0
```

根因：下标表达式的 lowering 只在
`compiler/lower/ast_ir_build.yh:280`（常量 GEP）与 `:288`（动态 GEP）产生地址，
`compiler/check` 全程没有"常量下标 vs 静态数组长度"的比较。
语言上运行时不检查是既有决定，但**这里的事实是编译期已完全确定**（`len(a)==4`、
下标是字面量常量），与"运行时防护"无关。

影响：一行手误造成静默栈破坏（见 S3 的后果）。这是本项目最容易让使用者
误以为"编译器会拦住"的地方。

### S2 切片范围不校验（高）

```yh
module slice1

fn main() int {
    let a [4]u8
    a[0] = 65
    let bad []u8 = a[0..16]        // 对 [4]u8 取 16 字节视图，无诊断
    printf("len=%d\n", len(bad))   // len=16
    let i int = 100
    printf("%d\n", bad[i].to_type(int))   // 读出相邻栈字节（本次为 232）
    return 0
}
```

根因：`compiler/lower/module_snapshot_lower_place.yh:419/491/552` 生成的切片
描述符直接写入"上界 − 下界"，`compiler/check/full.yh:228`（`full_slice`）只做
类型兼容检查，不比较常量范围与静态长度。

`docs/todo.md`「设计决定不做」列出「切片越界与生命周期运行时防护（ADR-0001）」，
本报告**不主张**加运行时检查；但 `a[0..16]` 中数组长度与两个边界都是常量，
静态拒绝不需要运行时成本，也不改变 ABI。

### S3 越界之后没有任何检测（高）

```yh
module heap_oob

fn main() int {
    let p *u8 = malloc(16).to_type(*u8)
    let i int = 0
    for i < 4000 { p[i] = 65; i += 1 }   // 16 字节分配外写 4000 字节
    printf("wrote %d bytes past a 16-byte allocation, no crash\n", i)
    free(p.to_type(*void))
    return 0
}
```

结果：输出正常，退出码 0。原因在分配器设计本身
（`compiler/backend/llvm_runtime.yh:172`）：每次 `malloc` 都是一次独立
`mmap`，页粒度 4 KiB，16 字节请求实际映射 4 KiB，因此**超出请求长度但仍在
页内的写不会触发任何故障**，也不会与相邻对象交叉（这点是页粒度带来的意外红利：
跨对象串写被削弱，但"本对象内越界"完全静默）。

栈侧同型：

```yh
module stack_oob

fn main() int {
    let a [4]u8
    a[0] = 1
    let i int = 0
    for i < 32 { a[i] = 9; i += 1 }   // 越过 4 字节数组 28 字节
    printf("ok\n")
    return 0
}
```

结果：先打印 `ok`，随后 `Bus error`（退出码 138）——即越界已经改写了当前
栈帧的其他槽位，只是因为落在同一栈页才没有当场触发。

### S4 编译器语句/类型嵌套无深度守卫 → 进程级崩溃（中高）

表达式侧有守卫（`compiler/parse/parse_expr.yh:33` 的 `PX_NEST_MAX = 256`，
`:39` 处报「表达式嵌套层数超过上限 256」）。语句与类型侧没有对应守卫：

```yh
// deep_stmt：n 层 if (1 == 1) { ... }
```

实测（`./yh --syntax-check`）：

| 嵌套形式 | 通过 | 崩溃 |
| --- | --- | --- |
| `if (1 == 1) { … }` | 8000 层 | 16000 层（SIGSEGV；shell 报 `139`、Python 报 `-11`） |
| `let p ************…int` | 7000 层 `*` | 8000 层 `*`（SIGSEGV） |

输入体积：16000 层 `if` 的源码约 200 KB；8000 个 `*` 约 8 KB。**几 KB 的
`.yh` 文件就能让编译器崩溃且不产生任何诊断**。递归入口：

- 语句：`compiler/parse/parse_stmt.yh:163`（`parse_stmt_inner`）→
  `:284`（`parse_stmt`）→ 内部 `parse_stmt_capture`/`parse_stmt` 再入（`:85`、`:230`）。
- 类型：`compiler/parse/parse_type.yh:179`（`parse_type_syntax`），
  `:191`/`:204`/`:298`/`:329`/`:353` 五处自递归。

影响：任何不可信源码/CI 拉取的分支都能让构建机崩溃（可用性），并让
"编译诊断"这条契约在极端输入下失效。因为崩溃点是原生栈耗尽，最坏情况下
（`-fstack-clash-protection` 未开启）存在跨过守护页的风险，但主要是 DoS。

### S5 `printf` 格式串与实参不匹配（中）

```yh
module fmt

fn main() int {
    let a *char = "only-one"
    printf("%s %s %s\n", a)     // 只传 1 个实参，格式串要 3 个
    return 0
}
```

结果：编译无任何提示，运行时第二个/第三个 `%s` 取到未初始化槽里的值并
**解引用它**，输出 `only-one` 后面跟一段无关进程字节（本次为乱码片段）。
`llvm_runtime_write_printf`（`compiler/backend/llvm_runtime.yh:277`）实现里的
变量槽读取在 arm64 上有 ±64 字节的有界性（`yh_va_next`，`:257`），所以
不会读到参数保存区之外，但**解引用垃圾指针**这件事没有任何防线。

`printf` 已在 prelude 里登记（`compiler/builtin/api.yh:44` 起），但没有实参
类型/数量检查（`F_RUNTIME_PRINTF` 只用于 lowering 决策）。

### S6 数组长度上限 2^31-1，栈 alloca 无预算（中）

```yh
module hugearr

fn main() int {
    let a [1000000000]u8    // 编译通过
    a[0] = 1
    printf("%d\n", a[0].to_type(int))
    return 0
}
```

结果：编译成功，运行时 SIGSEGV（入口块 `alloca` 1 GB，无栈探测）。

根因：长度只校验 `len_val > 2147483647`
（`compiler/parse/parse_type.yh:264`/`:285`），没有"栈对象字节预算"概念；
lowering 一律用入口块 `alloca`（`compiler/lower/ast_ir_build.yh:266`、
`compiler/backend/llvm_scalar.yh:260`）。1 GB 栈请求与其说是越界，不如说是
"未诊断的栈耗尽"，但结果同样是没有诊断的崩溃。

### S7 悬垂栈指针/切片逃逸（中）

```yh
module escape

fn dangling() *u8 {
    let buf [16]u8
    buf[0] = 65
    return &buf[0]      // 返回栈地址，编译通过
}

fn main() int {
    let p *u8 = dangling()
    printf("%d\n", p[0].to_type(int))   // 本次输出 65（读到已结束的栈帧）
    return 0
}
```

`&` 只要求左值（编码规范已写明），不区分"局部对象地址"与"可逃逸地址"。
同类形态在编译器自身代码里也存在：`compiler/lower/module_snapshot_lower.yh:733`
把局部 `flow` 的地址存进 `l.flow`，:691 的释放路径又依赖 `l.flow` 有效——
本次复核该指针的全部使用都在同一函数生命周期内（`module_snapshot_lower_flow.yh`
的 `flow` 形参），**当前没有实际 bug**，但这类"栈地址存进长生命周期结构"的
写法没有任何编译期拦截，是后续最可能长出真实 UAF 的模式。

### S8 重复释放与释放后使用（中）

```yh
module dfree

fn main() int {
    let p *u8 = malloc(32).to_type(*u8)
    free(p.to_type(*void))
    free(p.to_type(*void))     // 第二次 free
    printf("survived\n")       // 不会执行
    return 0
}
```

`dfree` → SIGSEGV（139）；`free` 后读 `p[0]` 同样 SIGSEGV（139）。
`docs/03-design/yh-memory标准库设计.md` §9 已把这些列为"未定义行为，不做运行时
检测"，本报告不改变该决定；但注意**第二次 `free` 读的是已解除映射页里的
头部长字节**，即头部魔数校验在"零额外内存"下是可行的（见 §6 M5）。

## 4. 静态推断问题（未构造复现）

- **S9 未判空的分配**：全仓 `malloc(` 调用点 258 处，用"近邻 6 行内是否出现
  `== 0`/`!= 0`"筛出 15 处近邻无判空；逐个复核后，编译器侧 3 处
  （`compiler/ir/api.yh:1057-1061` 实为 :1065 统一判空、
  `compiler/lower/module_snapshot_lower.yh:734` 由 :757 判空，
  `compiler/comptime/api.yh:1659-1690` 由 :1692 统一判空）**都是假阳性**，
  只有标准库 `malloc(8)` 类型取值器（`libs/num/num.yh:311`、`libs/toml/numbers.yh:319` 等
  12 处）确实不判空。编译器侧已有唯一 OOM 出口
  `compiler/support/api.yh:454`（写「内存不足，无法继续」并 `exit(1)`），
  这个收敛是正面设计。
- **S10 32 位 `int` 参与尺寸计算**：`compiler/support/api.yh:763`
  `let ncap int = cap * 2`（`read_source`）。源码文件超过约 1 GiB 时
  `cap` 从 2^30 翻倍到 2^31 会按有符号 32 位回绕成负数，随后一次
  `memcpy(nd, data, blen)` 把约 1 GiB 拷进新分配块——先崩溃而非静默改写，
  但属于"尺寸算术未使用宽类型"这一类应当消灭的隐患。
- **S11 分配器头部**：`compiler/backend/llvm_runtime.yh:180` 写头 8 字节
  （总长度），`:189` 直接 `load i64` 后 `munmap`（`:191`），**头部有 8 字节
  未被使用**（16 字节头只用了 8），且不校验魔数、不检查 `munmap` 返回值
  （`:191` 的 `%ignored`）。指针若不是本分配器产物（例如从 C 侧拿到、或
  来自 `libc.malloc`），`free` 会把"头部"当长度去解除映射任意地址——这正是
  `docs/03-design/yh-memory标准库设计.md` §12.4 第 5 条禁止的跨入口配对。

## 5. 正面结论（已核实，避免后续误改）

1. **算术 UB 已被刻意消除**（`compiler/backend/llvm_scalar.yh:125` `llvm_division`）：
   先用"安全除数 = 1"消掉除零与 `INT64_MIN / -1`，再 `select` 回商 0（余数取原
   被除数）；移位量 `and 63`（`:174`）；`add`/`sub`/`mul` **不加 `nsw`/`nuw`**，
   即定义的回绕。实测 `5/0 → 0`、`1 u64 << 64 → 1`、`INT64_MAX+1 → 回绕`，
   无 SIGFPE、无 poison。这条不能"顺手优化"掉。
2. **词法器边界纪律完整**：逐函数复核 `compiler/lex/lexer.yh`（`lex_ident`
   `:219`、`radix_scan` `:264`、`dec_scan` `:288`、`lex_string` `:380`、
   `lex_char` `:412`、`lex_escape` `:358`、`lex_op` `:444`），所有对
   `src_ctx().data[i]` 的读都有 `i < length` 前置；未终止字符串/未知转义/换行
   都产生诊断（`unterm.yh` 得到「字符串中不允许换行」）。
3. **编译期指针模型有界**（`compiler/comptime/ct_ir_place.yh:226`）：CT 指针是
   合成地址，解析时必须落在已登记的存活 span 内
   （`ct_ir_block_slot_hit` 用 `count` 上界，`:204`），偏移上限 ±100000；
   执行器还有 100000 步预算（`compiler/comptime/ct_ir.yh:182`）。**攻击者无法
   用 `$` 代码构造越过 CT arena 的读写**。
4. **解析深度与容器规模上限**：JSON `JSON_MAX_DEPTH = 256`
   （`libs/json/base.yh:22`，且已有"600 层嵌套报资源错误"的用例
   `libs/json/json.test.yh:473`）；TOML `TOML_MAX_DEPTH = 128`
   （`libs/toml/base.yh:20`）；check 循环栈 64 层拒绝
   （`compiler/support/api.yh:1261`）；lower 循环栈 16 层拒绝
   （`compiler/lower/module_snapshot_ctx.yh:50` + `module_snapshot_lower_flow.yh:528`）。
5. **增长有溢出意识的库**：`libs/string` 有 `STRING_MAX_LENGTH`
   （`libs/string/base.yh:17`）与 `string_grow_capacity` 的
   `STRING_MAX_LENGTH / 2` 预判（`libs/string/owned.yh:88`），扩容走
   "先分配→复制→成功才释放旧块"。
6. **构建缓存内容寻址 + OutputID 校验**（`compiler/build/api.yh:601`、
   `compiler/build/function_ir_cache.yh:79`）：篡改缓存产物会被判 miss，
   不是静默复用。
7. **不受 shell/PATH 影响的外部进程**：prelude 暴露 `system` 仅在
   `legacy_system` 开关下（`compiler/builtin/api.yh:114`），
   `libs/os` 的 `spawn` 走精确路径（`libs/os/doc.yh:265`），Linux 用
   close-on-exec 错误管道（`libs/os/process.linux.yh:7`）。
8. **生成的用户程序不劫持 libc 符号**：`nm -m` 检查产物，`_memcpy`/`_memset`/
   `_strlen`/`_printf` 都是 `non-external (was a private external)`，
   即只服务于本程序引用，不会替换系统库里其他组件用的 `memcpy`。

## 6. 建议的最小修复顺序（按"改动小 + 收益确定"排序）

以下每项都可独立验收，且都不改变语言 ABI、不引入运行时开销（除 M5 明确标注）。

| 项 | 内容 | 落点 | 验收 |
| --- | --- | --- | --- |
| **M1** | 语句/类型解析加深度守卫，复用 `PX_NEST_MAX` 的既有机制（新增独立计数，上限 256，报「语句/类型嵌套层数超过上限」） | `compiler/parse/parse_stmt.yh:163/284`、`compiler/parse/parse_type.yh:179` | `deep_stmt`/`deep_type` 由 SIGSEGV 变为诊断；`just test` 全绿 |
| **M2** | 常量下标静态检查：下标为常量且 `i < 0 或 i >= 静态长度` → 诊断（只覆盖数组/切片的下标表达式，不碰运行时） | `compiler/check/full.yh`（下标表达式）/ `compiler/check/type_syntax.yh` | S1 语料报错；`tests/` 现有越界写法（若有）一并修正 |
| **M3** | 常量切片范围静态检查：`a[lo..hi]` 两端都常量时要求 `0 <= lo <= hi <= 静态长度` | `compiler/check/full.yh:228`（`full_slice`） | S2 语料报错 |
| **M4** | `printf` 字面量格式串的静态检查（数量 + 类型：`%d/%i/%u/%ld/%lu` 需整数、`%s` 需指针或数组退化、`%c` 需整数/char）；非字面量格式串保持现状 | `compiler/check`（按 `F_RUNTIME_PRINTF` 标记的调用点） | S5 语料报错；`libs` 全量调用点通过 |
| **M5** | 分配器头部魔数：把已空闲的 8 字节头高位用作 magic（`0x5948414D`），`free` 先校验再 `munmap`，不匹配时 `errors` 级诊断并 `exit`（**零额外内存**，只有一次比较） | `compiler/backend/llvm_runtime.yh:180/189` | 重复 `free`/野指针 `free` 变为确定性诊断而非 SIGSEGV；`just test-libs` 绿 |
| **M6** | 栈对象字节预算：单个局部/参数对象超过阈值（建议 8 MiB，与 LLVM 默认栈探测阈值同量级）→ 诊断「对象过大，请改为堆分配」（保留 `2147483647` 的长度上限作为第二道） | `compiler/parse/parse_type.yh:264` 或 `compiler/check/type_syntax.yh:162` | S6 语料报错 |
| （不作） | 运行时边界检查、生命周期防护、GC/引用计数、`free` 后置空 | — | **ADR-0001 与 `docs/todo.md`「设计决定不做」已否决，勿列为任务** |

顺序理由：M1 是唯一"小输入 → 进程崩溃"的入口；M2/M3 把"编译期已知"的越界
从静默变诊断；M4 消掉最常见的"看起来能用"的任意指针解引用；M5 用已有空闲字节
换确定性诊断，代价几乎为零；M6 让 1 GB 栈请求提前失败。

## 7. 复现语料与命令

语料在 `tmp/sec-audit/`（不入库）。要点（源码见上文各节）：

| 文件 | 期望现象 |
| --- | --- |
| `idx.yh` | 无诊断，退出码 0（S1） |
| `slice1.yh` | `len=16`、越界读出 232（S2） |
| `heap_oob.yh` | 静默写越界 4000 字节，退出码 0（S3） |
| `stack_oob.yh` | 打印 ok 后 Bus error（S3） |
| `deep_stmt.yh` / `deep_type.yh` | `./yh --syntax-check` SIGSEGV（S4） |
| `fmt.yh` | 乱码输出（S5） |
| `hugearr.yh` | 运行时 SIGSEGV（S6） |
| `escape.yh` | 输出 65（S7） |
| `dfree2.yh` / `uaf.yh` | SIGSEGV（S8） |
| `vla.yh` | 「变量不是编译期常量」（正面：拒绝 VLA） |
| `unterm.yh` | 「字符串中不允许换行」（正面：词法诊断） |
| `deep_expr.yh` | 「表达式嵌套层数超过上限 256」（正面：S4 的对照） |

```sh
cd tmp/sec-audit
../../yh idx.yh -o idx && ./idx
../../yh --syntax-check deep_type.yh; echo "exit=$?"   # 期望 0，实测 139/-11
../../yh heap_oob.yh -o heap_oob && ./heap_oob
```

深度阈值可用脚本重扫（把 `n` 喂给 `deep_stmt`/`deep_type` 模板并观察 `--syntax-check`
退出码，`-11` 即崩溃）。

## 8. 未决 / 需确认

1. **M4 的宽容度**：`printf("%d", ptr)` 这类"故意按整数打印指针"的写法在标准库
   里是否存在？若存在，M4 需要保留整数与指针互通，否则会破现有调用点。
2. **M2/M3 的既有语料豁免**：`tests/` 里是否已有依赖"越界不报错"的反例（例如
   故意写 `a[len]` 测别的行为）？需要先扫一遍再落地，否则会红。
3. **M6 阈值**：8 MiB 只是建议值；是否有大数组局部变量的正当用例（例如
   `libs/json` 的栈缓冲）需要先统计。
4. **`to_type` 任意指针取值的边界**：`(addr).to_type(*u8)` 可构造任意地址访问，
   这是 C 类似的既有能力（`docs/03-design/yh-编码规范.md` §类型与转换），
   本报告不改。若要"可审计的 unsafe 标记"，那是一次语言层决策，需单独 ADR。
