# yh memory 标准库设计

修改时间：2026-11-08

版本：**第三版**（取代 2026-11-06 第二版）。第二版把范围切成 M0–M6 六个阶段
（`FixedBuffer`/`Arena`/`FixedPool`/`Allocator` vtable/后置候选），
自 2026-10-23 至 2026-11-08 无一切片落地——**范围过大导致零进展**。
本版收敛为「两个必做切片 + 一个可选切片」，每个切片都可独立验收、都有确定消费者。

状态：**设计（未实施）**。本版不含代码改动。

## 1. 修订要点：相比第二版做了什么

| 项 | 第二版 | 第三版 | 理由 |
| --- | --- | --- | --- |
| 阶段数 | M0–M6（6 个，含纯测试的 M0） | T1–T3（3 个），FixedPool/Allocator 降为按需 | 18 个月龄设计零落地，说明切片太大 |
| `reallocate` | M1，排在测试固化之后 | **T1**，第一件事 | 4 行组合逻辑，立即消除 `string_grow_capacity` 的手写增长样板 |
| `FixedBuffer` | M2 | **T2** | 零系统调用，是「栈上临时缓冲」唯一正确解；Arena 也需要它的语义作参照 |
| `Arena` | M3 | **T3** | 批量同生命周期分配；`toml` 的私有池已证明该需求存在 |
| `FixedPool` | M4（排期实施） | **按需**（P4） | 无消费者：`toml` 已有池且本设计不迁移，`cli` 也有自己的池 |
| `Allocator` vtable | M5（排期实施） | **按需**（P5） | 无泛型容器；`string`/`toml`/`json` 都不接受分配器参数 |
| 文件编号 `10_`/`20_` | 用编号「保证编译顺序」 | **不编号** | 伪约束：同模块文件由两遍解析（pass1 签名 / pass2 正文）处理，顺序无关；`libs/string` 的 8 个文件（`base`/`doc`/`owned`/`view`/`transform`/…）无编号即为反证 |
| `MEMORY_TEST_FAIL_AFTER` | 模块级私有常量 | 保留，但只在 T2/T3 需要时引入 | 失败注入的消费者是「映射失败路径」，T1 的 `reallocate` 不需要 |

保留第二版的成果：§4 语言约束、§9 失败与误用语义、§10 模块边界、Zig 对照结论。

## 2. 现状基线（2026-11-08 实测）

| 事实 | 依据 |
| --- | --- |
| `libs/memory` 只有 3 个函数、18 行，无 README/`doc.yh`/`*.test.yh` | `libs/memory/memory.yh` |
| `alloc`/`release`/`copy` 分别薄转发 prelude 的 `malloc`/`free`/`memcpy` | 同上；`compiler/builtin/prelude.yh` 的 `prelude_add("malloc"…)` 段 |
| Linux 每次 `malloc` 一次 `mmap`，前 16 字节记映射长度，用户指针 16 字节对齐；`free` 读头后一次 `munmap` | `compiler/backend/llvm_runtime.yh` 的 `llvm_runtime_write_malloc`/`_free` |
| Darwin 布局相同，底层走 libSystem `mmap`/`munmap` | `compiler/backend/llvm_apple_runtime.yh` |
| `malloc(0)` 返回非空；`size > 2^64-17` 返回 0；`free(0)` 无操作 | 实测（见 §11 验证记录） |
| 重复 `free` 直接 SIGSEGV（无任何检测） | 实测：同地址二次 `free` 后进程退出码 139 |
| 无 `realloc`/`calloc`/对齐分配/容量统计 | `libs/memory` 与 prelude 均无 |
| 消费者：`libs/string/owned.yh`、`libs/string/transform.yh`、`libs/json/serialize.yh` 各 `import memory` | `grep -rn "import memory" libs` |
| `libs/toml` 私有池直接调裸 `malloc`，不经 `memory` | `libs/toml/document.yh` 的 `pool_node` |
| `libs/sys` 有 `map_memory`/`unmap_memory`，`memory` 不使用 | `libs/sys/memory.{linux,darwin}.yh` |

实测补充（本版新增）：

- 20 万次 64 字节 `malloc`+`free` 往返 ≈ 0.87 s（同规模基线循环 0.31 s，
  libc 同操作 0.05 s）——每次分配两次系统调用是主要成本，这是
  `FixedBuffer`/`Arena` 存在的量化理由。
- 编译器自身 `malloc` 调用行 260 处，其中 24 处近邻无判空。

## 3. 语言事实与约束（决定 API 形状）

- 无泛型、无接口、无方法、无反射、无闭包。
- 无析构、无 `defer`：所有权必须显式 `release`/`reset`。
- 结构体按值复制；复制句柄**不增加所有权**（沿用 `string.String` 规则）。
- 模块私有类型不得出现在 `pub` 签名、`pub` 字段或 `pub` 别名（ADR-0013），
  所以公开结构体只能持 `*void` 句柄或标量。
- `sizeof`、`&`、`|`/`&`/移位、指针→`u64`、函数指针字段均可用。
- 无异常、无 error 类型：失败用 0（指针）或 0/1（`resize`/`free`）。
- 同模块多文件按两遍解析（先收签名、再收正文），**文件顺序无关**；
  跨文件不需要 `import`。
- 模块 = 目录；目录内所有 `*.yh` 自动纳入，`*.test.yh` 统一排在后
  （`compiler/build/project_index.yh` 的 `pj_name_is_test` 与扫描排序）。
- 标准库模块经三层搜索（本项目 → 标准库 `YH_STDLIB` → 直接依赖）绑定，
  `libs/memory` 目录即模块，无需在 `project.toml [lib]` 登记。

## 4. 设计决策

| 方案 | 结论 |
| --- | --- |
| 保留现状三函数，什么都不加 | 否决：`string` 继续手写增长、调用方继续逐个 `mmap` |
| 以 `Allocator` vtable 作唯一入口（Zig 路线） | 否决为首版：无泛型容器消费者，只增加间接调用与调用点噪音 |
| `memory` 自带完整堆（size class/bin/合并） | 否决：与 prelude 重复，破坏「同一实现分配/释放」配对 |
| **直接 API + Zig 语义，分三个切片（T1 `reallocate` → T2 `FixedBuffer` → T3 `Arena`）** | **采用** |
| 块来源改走 `sys.map_memory` | 否决：`memory` 会新增 `sys` 依赖，与 `string`/`toml` 的 prelude 来源分叉 |
| 一次性把 `FixedPool`/`Allocator` 也做完 | 否决：两者都无消费者（第二版的教训） |

三条硬约束：

1. **块来源统一 prelude `malloc`/`free`**，不重复实现 mmap 判错与 `munmap` 长度。
2. **不读运行时分配头**：prelude 头部只记映射长度、不记用户请求长度，
   因此所有 `resize`/`free`/`reallocate` 都要求调用方提供旧长度。
3. **不引入 GC、引用计数、自动析构、线程安全**。

## 5. 堆层（T1）：`alloc` / `release` / `copy` / `reallocate`

### 5.1 现有三函数（签名与语义不变）

| API | 契约 |
| --- | --- |
| `alloc(byte_count u64) *void` | 申请指定字节数；失败返回 0；`0` 返回非空地址；结果至少 16 字节对齐；不初始化内容 |
| `release(data *void) void` | 释放 `alloc`/`reallocate` 返回的地址；允许 0；重复释放、释放非本堆地址为未定义行为（实测 SIGSEGV） |
| `copy(destination *void, source *void, byte_count u64) *void` | 复制指定字节数并返回目标；**源与目标不得重叠**（重叠用 `libc.memmove`） |

这三条不改一行，只补 `README`、`doc.yh` 与 `memory.test.yh` 的断言。

### 5.2 新增 `reallocate`（T1 的全部交付物）

```yh
pub fn reallocate(data *void, old_size u64, new_size u64) *void
```

| 情形 | 行为 |
| --- | --- |
| `data == 0` | 等价 `alloc(new_size)`；`old_size` 忽略（**优先于下一行**） |
| `data != 0 && new_size == 0` | 释放 `data`，返回 0 |
| `new_size < old_size` | 分配 `new_size`，只复制前 `new_size` 字节，释放旧块 |
| `new_size > old_size` | 分配 `new_size`，复制 `old_size` 字节，释放旧块 |
| 新分配失败 | 返回 0，**旧块与内容保持不变** |

固定实现顺序：**先分配 → 按 `min(old_size, new_size)` 复制 → 成功后释放旧块**。
传错 `old_size` 是未定义行为（可能少复制，但不越界读）。

为什么需要 `old_size`：prelude 头部不记用户请求长度，标准库无法从 `data`
反推复制多少字节。

### 5.3 堆为什么不提供 `resize`/`remap`/任意对齐分配

- `resize` 依赖原地调整（size class 或子分配器）；prelude 每次独立 `mmap`，
  头部只有一个总长度，无法原地改用户长度，也无法合并两个映射。
- 任意对齐分配需要在前置头保存原始指针 + 专用释放函数，误用普通 `release`
  会读错头部并 `munmap` 错地址。首版不提供这种易误用配对；大于 16 的对齐
  用 T2 `fixed_buffer_alloc_aligned` / T3 `arena_alloc_aligned`。

### 5.4 用法

```yh
import memory

fn grow_example() int {
    let p *u8 = memory.alloc(16).to_type(*u8)
    if (p == 0) { return 1 }
    let i int = 0
    for i < 16 { p[i] = (i + 65).to_type(u8); i += 1 }
    // 扩到 64：旧 16 字节内容保留，新 48 字节未初始化。
    let q *u8 = memory.reallocate(p.to_type(*void), 16, 64).to_type(*u8)
    if (q == 0) {
        // 失败时 p 仍有效可用，必须自己释放。
        memory.release(p.to_type(*void))
        return 2
    }
    if (q[0] != 65 || q[15] != 80) { memory.release(q.to_type(*void)); return 3 }
    memory.release(q.to_type(*void))
    return 0
}
```

要点：`reallocate` **成功会自己释放旧块**，调用方只释放返回值；
**失败不释放**，旧块责任仍在调用方。

## 6. `FixedBuffer`（T2）：调用方缓冲区上的线性分配

### 6.1 模型

```yh
// FixedBuffer 在调用方提供的连续缓冲区上线性分配，零系统调用。
// buffer 由调用方保管，FixedBuffer 不拥有也不释放它。
pub struct FixedBuffer {
    buffer *u8
    capacity u64
    used u64
}
```

零值（`buffer == 0` 或 `capacity == 0`）无效，所有分配返回 0。

### 6.2 API

| API | 契约 |
| --- | --- |
| `fixed_buffer_init(buffer *u8, capacity u64) FixedBuffer` | 绑定缓冲区；空指针或零容量返回零值 |
| `fixed_buffer_alloc(fb *FixedBuffer, byte_count u64) *void` | 16 字节对齐；失败返回 0 |
| `fixed_buffer_alloc_aligned(fb *FixedBuffer, n u64, alignment u64) *void` | 按**绝对地址**对齐；`alignment` 为 0 或非 2 的幂返回 0 |
| `fixed_buffer_resize(fb *FixedBuffer, data *void, old_size u64, new_size u64) int` | `new_size > 0`；**最近分配**可原地扩大/缩小；非最近分配只允许逻辑缩小（返回 1 但不回收）；其余返回 0 |
| `fixed_buffer_free(fb *FixedBuffer, data *void, byte_count u64) int` | 仅最近分配回收；1 = 回收，0 = no-op |
| `fixed_buffer_reset(fb *FixedBuffer) void` | `used = 0`；此前地址全部失效 |
| `fixed_buffer_owns(fb *FixedBuffer, data *void) int` | 地址落在 `[buffer, buffer+capacity)` 返回 1；仅用于断言 |
| `fixed_buffer_capacity(fb *FixedBuffer) u64` | 缓冲区总容量 |
| `fixed_buffer_used(fb *FixedBuffer) u64` | 已用字节数 |

补充语义：

- `byte_count == 0`：返回当前对齐地址，不推进 `used`。
- 空间不足或加法溢出：返回 0，`used` 不变。
- 「最近分配」判定：`data + old_size == buffer + used`。
- 对齐 padding 在 `free` 时保留（与 Zig `FixedBufferAllocator` 一致）。
- `free`/`resize` 不校验 `data` 是否属于本缓冲区（误用是 UB，`owns` 只作辅助断言）。

### 6.3 用法：栈上临时缓冲，全程零系统调用

```yh
import memory

// 把整数拼成字符串，不分配任何堆内存。
fn format_id(id u64, out *u8, cap u64) int {
    let fb memory.FixedBuffer = memory.fixed_buffer_init(out, cap)
    // 预留 8 字节给对齐/分隔，正文最多 cap-8。
    let n u64 = 0
    let digits [24]u8
    if (id == 0) { digits[0] = '0'; n = 1 }
    let v u64 = id
    for v > 0 { digits[n] = ((v % 10) + 48).to_type(u8); n += 1; v = v / 10 }
    let dst *u8 = memory.fixed_buffer_alloc(&fb, n + 1).to_type(*u8)
    if (dst == 0) { return -1 }
    let i u64 = 0
    for i < n { dst[i] = digits[n - 1 - i]; i += 1 }
    dst[n] = 0
    return n.to_type(int)
}

fn main() int {
    let buffer [256]u8
    if (format_id(12345, &buffer[0], 256) != 5) { return 1 }
    printf("%s\n", &buffer[0])
    return 0
}
```

要点：缓冲区在栈上（`let buffer [256]u8`），`fixed_buffer_init(&buffer[0], 256)`
只是记两个字段，**一次系统调用都没有**。函数返回即整体释放，无泄漏路径。

## 7. `Arena`（T3）：批量分配、整批回收

### 7.1 模型

```yh
// Arena 是批量分配器：块按需映射，分配线性推进，reset/release 整批回收。
// 零值等价默认块大小且尚未映射；块大小只由 arena_init 设置。
pub struct Arena {
    head *void       // 最新块；模块私有布局，0 表示无块
    block_size u64   // 0 表示默认；只由 arena_init 设置
}
```

块头为模块私有结构（不出现在 `pub` 签名）：

```yh
// arena_block 是映射块的前置头；payload 从 16 字节对齐偏移开始。
struct arena_block {
    next *arena_block
    size u64
    used u64
}
```

`reset` 模式：

```yh
pub enum ArenaResetMode {
    arena_reset_free_all
    arena_reset_retain
}
```

### 7.2 API

| API | 契约 |
| --- | --- |
| `arena_init(block_size u64) Arena` | 返回空 Arena：0 用默认块大小（64 KiB），非零向上取整到 16；不映射 |
| `arena_alloc(arena *Arena, byte_count u64) *void` | 16 字节对齐；失败 0 |
| `arena_alloc_aligned(arena *Arena, n u64, alignment u64) *void` | 绝对地址对齐；非法对齐返回 0 |
| `arena_resize(arena *Arena, data *void, old_size u64, new_size u64) int` | 仅最近分配可原地调整；非最近只允许逻辑缩小（1，不回收）；`new_size == 0` 返回 0 |
| `arena_free(arena *Arena, data *void, byte_count u64) int` | 仅最近分配回收 |
| `arena_reset(arena *Arena, mode ArenaResetMode) void` | `free_all` 释放全部块并归零；`retain` 保留最新块、释放其余、`used = 0` |
| `arena_release(arena *Arena) void` | 释放全部块，`head = 0`；`block_size` 保留以便复用 |
| `arena_capacity(arena *Arena) u64` | 所有块 payload 容量之和（不含块头） |

补充语义：`arena` 空指针是 UB；对齐余量、块大小、`used + 请求` 均做溢出检查，
失败返回 0 且不破坏已分配内容；块头不进用户可见区域。

### 7.3 几何增长

新块大小取三者最大并向上取整到 16：

1. `block_size`；
2. 当前块 `size + size / 2`（约 1.5 倍）；
3. 块头开销 + 对齐余量 + `byte_count`。

新块挂链头成为当前块。新块映射失败返回 0，旧链与已分配数据不变。

与 Zig 的差异：Zig 的 `createNode` 会把最后一块 `resize` 到总容量「预热」；
prelude 不支持 `resize`，所以 `retain` 只保留最新块的现有容量，**不预扩**。
文档不用「retain_capacity」这个名字，避免误导。

### 7.4 用法：一次请求解析整块结果，一次 reset 全清

```yh
import memory

// 模拟：把逗号分隔文本切成字段，字段存进 arena，返回字段数。
fn split_into_arena(arena *memory.Arena, text *char, count *u64) int {
    let fields u64 = 0
    let i int = 0
    for {
        let start int = i
        for text[i] != 0 && text[i] != ',' { i += 1 }
        let len int = i - start
        if (len > 0) {
            let dst *u8 = memory.arena_alloc(arena, (len + 1).to_type(u64)).to_type(*u8)
            if (dst == 0) { return -1 }
            let k int = 0
            for k <= len { dst[k] = text[start + k].to_type(u8); k += 1 }
            fields += 1
        }
        if (text[i] == 0) { break }
        i += 1
    }
    count[0] = fields
    return 0
}

fn main() int {
    // 块大小 4 KiB：字段总量超过它时自动映射第二块（几何增长）。
    let arena memory.Arena = memory.arena_init(4096)
    let fields u64 = 0
    if (split_into_arena(&arena, "alpha,beta,gamma", &fields) != 0) { return 1 }
    if (fields != 3) { return 2 }
    if (memory.arena_capacity(&arena) < 4096) { return 3 }
    // 整批回收：保留最新块，下次复用。
    memory.arena_reset(&arena, memory.arena_reset_retain)
    let again u64 = 0
    if (split_into_arena(&arena, "x,y", &again) != 0) { return 4 }
    if (again != 2) { return 5 }
    memory.arena_release(&arena)
    return 0
}
```

要点：`arena` 拥有块、不拥有块内对象，**不调用任何析构**；`reset`/`release`
后此前返回的所有地址立即失效。逐字段 `arena_free` 只在「最近分配」上有效，
批量场景一律走 `reset`。

## 8. 按需层（不排期，有消费者才做）

### 8.1 `FixedPool`（P4）

触发条件：出现「固定块大小、高频申请/归还」的消费者。当前 `toml` 已有私有池、
`cli` 也有，本设计不迁移。若触发，形态为「内部 `Arena` + 空闲链」：

```yh
// FixedPool：块从内部 Arena 分配，free 后进入空闲链复用。零值表示未初始化。
pub struct FixedPool {
    arena Arena
    free *void        // 空闲块链；块首 8 字节存 next
    block_size u64    // 对齐后的块大小；0 表示未初始化
    alignment u64     // 块对齐；至少 16，2 的幂
}
```

API 契约（供将来实施参考）：`pool_init`/`pool_init_aligned`/`pool_reserve`/
`pool_alloc`/`pool_free`/`pool_reset`/`pool_release`。差异点：yh 无泛型
`Item`，用 `block_size` 代替；池始终可增长（无 `growable=false`）。

### 8.2 `Allocator` vtable（P5）

触发条件（任一）：多容器需共享同一分配器接口；`Arena` 需用 `FixedBuffer`
作 child（`StackFallback`）；需要「分配恒失败」的测试适配器。

形态只有一种（yh 支持函数指针字段，`libs/cli` 的 `converter`/`validator`
是既有先例）：

```yh
type AllocFn = fn(*void, u64, u64) *void   // context, len, alignment
type FreeFn  = fn(*void, *void, u64, u64) void
// resize/t/remap 同构；组合路径 reallocate 按 resize→remap→copy+free 落档
pub struct Allocator {
    context *void
    alloc_fn AllocFn
    free_fn FreeFn
}
```

**首版不实现**：没有消费者时属于过度设计（第二版 M5 未落地的直接原因）。

## 9. 失败、溢出与误用

| 场景 | 行为 |
| --- | --- |
| 映射/空间不足 | 返回 0；保留已有块/游标与内容 |
| 加法/乘法溢出 | 返回 0；不执行分配 |
| 对齐参数非法（0、非 2 的幂） | 返回 0 |
| 零长度分配 | 返回非空地址（与 prelude 一致），不推进游标 |
| `release(0)`/`arena_free(…,0)`/`fixed_buffer_free(…,0)` | 无操作 |
| 非最近分配 `free` | 返回 0/no-op；空间不回收 |
| 非最近分配 `resize` 扩大 | 返回 0；缩小返回 1（逻辑缩小，不回收） |
| 重复释放、释放非本分配器地址、释放后使用 | **未定义行为，不做运行时检测** |
| 复制句柄后双释放 | 未定义行为 |
| 空指针作为 Arena/FixedBuffer 句柄 | 未定义行为 |
| `free` 的 size/alignment 与分配不一致 | 未定义行为 |

不做运行时检测的理由：语言没有编译期「已释放」状态，也没有类型信息；
魔数校验给每次分配/释放加分支与头部字节，却不改变误用的不可恢复性
（实测重复 `free` 直接 SIGSEGV）。需要排查时用 `fixed_buffer_owns`/
`arena_capacity` 断言 + 测试失败注入。

测试失败注入（仅 T3 需要）：模块内私有常量

```yh
// MEMORY_TEST_FAIL_AFTER：产品构建恒为 -1；测试把标准库副本改成 >=0，
// 允许该次数的映射后下一次返回失败。
const MEMORY_TEST_FAIL_AFTER int = -1
```

注入点在块映射函数内。`FixedBuffer` 不映射，用容量边界测试即可。

## 10. 与现有模块的边界

- **`string`**：`String` 是单对象所有权，增长要复制并释放旧块，不适合
  `Arena`（Arena 无任意单块释放）。保留 `string_alloc`/`string_copy_overlap`，
  **不迁移**；`reallocate` 只提供可选替代，不强制改造。
- **`toml`**：私有池与 `Arena` 同构，可独立切片迁移，但必须保留预算统计、
  失败注入与「失败无半成品」语义。不在 T1–T3 范围。
- **`cli`**：有自己的池，同样按需。
- **编译器 `compiler/`**：直接使用 prelude 堆，生命周期由编译器自己管理；
  **标准库 Arena 不是编译器内部分配器的替代品**，不迁移。
- **`libs/sys`**：`map_memory`/`unmap_memory` 继续服务显式页映射（文件映射、
  页对齐缓冲）；`memory` 不依赖 `sys`，边界是「堆分配」与「页映射」。
- **`libs/libc`**：其 C ABI 分配器与 `alloc`/`release` 是不同入口，
  在 E4 决定最终实现前**禁止跨入口配对释放**。

## 11. 分期、验收与验证记录

| 切片 | 交付 | 验收 |
| --- | --- | --- |
| **T1** | `memory.yh` 追加 `reallocate`；新增 `libs/memory/README.md`、`doc.yh`、`memory.test.yh`（`alloc`/`copy`/`release`/`reallocate` 断言） | `just test-libs` 通过（O0 与 O2 各一次）；现有三函数行为未变 |
| **T2** | 新增 `libs/memory/base.yh`（`FixedBuffer` 类型与常量）、`fixed_buffer.yh`（实现）、`memory.test.yh` 追加对齐/容量/LIFO/reset/owns 用例 | `just test-libs` 通过；`fixed_buffer_owns` 边界断言通过 |
| **T3** | 新增 `arena.yh`（`Arena` + `ArenaResetMode` + 块映射）；`memory.test.yh` 追加同块/跨块/几何增长/对齐/reset 模式/capacity 用例 | `just test-libs` 通过；`MEMORY_TEST_FAIL_AFTER` 注入矩阵覆盖映射失败保留旧内容 |

每个切片：**先加断言（预期失败原因明确）→ 最小实现 → 定向用例通过 →
`just test-libs` → 更新本文与 `docs/finish.md`**。全绿后才允许 `just seed`。

文件布局（不编号，与 `libs/string` 一致）：

| 文件 | 职责 |
| --- | --- |
| `libs/memory/memory.yh` | 模块入口与堆层：`alloc`/`release`/`copy`/`reallocate` |
| `libs/memory/base.yh` | 公开模型：`FixedBuffer`、`Arena`、`ArenaResetMode`、默认常量 |
| `libs/memory/fixed_buffer.yh` | `FixedBuffer` 实现 |
| `libs/memory/arena.yh` | `Arena` 实现与块映射 |
| `libs/memory/memory.test.yh` | `test` 块断言（`*.test.yh` 由扫描排在非测试文件之后） |
| `libs/memory/doc.yh` | 公开 API 速查与失效规则 |
| `libs/memory/README.md` | 使用说明与 Zig 对照 |

验证记录（本版设计期实测，非实施验收）：

- `malloc(0)` 返回非空、`p % 16 == 0`、超长请求返回 0、`free(0)` 无操作：
  探针程序三项全部符合。
- 同地址二次 `free`：进程 SIGSEGV，退出码 139。
- 20 万次 64 字节往返 0.87 s（基线 0.31 s）。
- 语法可用性（每个示例在 `/tmp` fixture 里 `yh build` + 运行通过）：
  `pub struct`、内部 `struct`、`pub enum`、枚举形参、结构体按值返回、
  函数指针 `type` 字段、栈数组取址 `&buffer[0]`、`for cond { }` /
  `for { … break }`、u8 与整数字面量比较。
- 语法**不可用**（已修正文档示例）：`while` 不是 yh 语法（循环只有 `for`，
  见 `docs/03-design/yh-编码规范.md` §循环）；`&expr.to_type(*char)` 不可编译
  （`to_type` 结果是右值，`&` 要求左值）；`import` 未使用是编译错误。

## 12. 如何使用（三档场景）

### 12.1 现在就可用：单对象分配

```yh
import memory
import io

fn main() int {
    let buf *u8 = memory.alloc(128).to_type(*u8)
    if (buf == 0) { return 1 }
    buf[0] = 'h'; buf[1] = 'i'; buf[2] = 0
    io.println(buf.to_type(*char))
    memory.release(buf.to_type(*void))
    return 0
}
```

运行：

```sh
cd /path/to/your/project
YH_STDLIB=/path/to/libs /path/to/yh run
```

`YH_STDLIB` 未设置时编译器不会自动发现 `libs/`（见标准库设计文档）。
安装到 `PREFIX` 后用 `just install` 的布局则无需显式设置。

三条实测约束（示例已在 fixture 里编译运行通过）：

- **循环只有 `for`**：`while`/`do` 不是 yh 语法。条件循环写 `for cond { }`，
  无限循环写 `for { … break }`（见 `docs/03-design/yh-编码规范.md` §循环）。
  本版示例已按此改写。
- `io.println(&buf[0].to_type(*char))` **不可编译**（`to_type` 结果是右值，
  `&` 要求左值）。要传 C 字符串用 `buf.to_type(*char)`；只有真左值
  （如栈数组元素 `&buffer[0]`）才能取址。
- **导入未使用是编译错误**：文件里 `import memory` 却没有 `memory.` 限定名
  引用会报「导入未使用」。示例按整段使用，不要只粘走类型声明。

### 12.2 T1 落地后：需要长大/缩小的单块

```yh
let grown *u8 = memory.reallocate(old.to_type(*void), old_len, new_len).to_type(*u8)
if (grown == 0) {
    // 旧块仍有效，责任仍在调用方
    memory.release(old.to_type(*void))
    return -1
}
old_len = new_len
old = grown
```

### 12.3 T2/T3 落地后：临时缓冲与批量对象

- **栈上临时缓冲**（`T2`）：`let raw [N]u8` + `fixed_buffer_init(&raw[0], N)`，
  零系统调用，函数返回即整体释放。适用于格式化、拼装、单次解析。
- **批量同生命周期**（`T3`）：`arena_init(block_size)` 后连续
  `arena_alloc`，结束时一次 `arena_reset(retain)` 或 `arena_release`。
  适用于「一次请求解析出一整片对象、整片丢」的场景。

选择判据：

| 场景 | 用哪个 |
| --- | --- |
| 单个对象、生命周期跨函数 | `alloc`/`release`（现在可用）；需要重新大小用 `reallocate`（T1） |
| 大小已知、生命周期在一个函数内 | `FixedBuffer`（T2） |
| 数量不定、生命周期一致、可整批丢 | `Arena`（T3） |
| 固定块大小、高频申请归还 | `FixedPool`（P4，需消费者触发） |
| 需要把分配器作为参数传递 | `Allocator`（P5，需消费者触发） |

### 12.4 配对的硬规则

1. 谁分配谁释放；`alloc`/`reallocate` 的返回值只能交给 `release`/`reallocate`。
2. `FixedBuffer` 不拥有缓冲区，`free` 只回收最近分配，`reset` 重置游标。
3. `Arena` 拥有块、不拥有块内对象；`reset`/`release` 后地址全部失效，不调析构。
4. 复制 `Arena`/`FixedBuffer` 句柄只复制字段，**不新增所有者**；两个副本各释放
   一次是 UB。
5. 分配与释放必须配对到**同一实现**：prelude 的块不能交给 `libc.free`。

## 13. 未决问题

1. **`Arena` 默认块大小（64 KiB）与 1.5 倍增长**：保守起点，等真实负载的
   `strace`/`dtruss` 计数再调整，不改变 API。
2. **`FixedPool` 是否落地**：取决于是否出现高频固定块消费者；`toml` 的迁移是
   独立切片，需保留预算与注入语义。
3. **`Allocator` 是否落地**：取决于是否出现「多容器共享接口」或
   「Arena 用 FixedBuffer 作 child」的真实需求。
4. **堆上任意对齐分配**：不提供；大对齐走 `fixed_buffer_alloc_aligned`/
   `arena_alloc_aligned`。若 `Allocator` 落地可在适配器内补过分配。
5. **重复释放检测**：prelude 立即 `munmap`，无法安全保留元数据做检测；
   若要检测需改运行时头部（影响编译器自身），不属本设计范围。
