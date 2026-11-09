# yh list 标准库设计

修改时间：2026-11-10

状态：**L0–L2 已实施（2026-11-10）**。本文定义 `libs/list`（堆上连续存储的动态列表，
下称 list 或 ArrayList）的 API 契约、语言约束、误用边界与验收口径。
面向当前编译器设计：**无泛型、无接口、无方法接收者**；不新增语言语法。

## 1. 目标与非目标

目标：

- 一份实现支持任意元素类型：元素宽度在运行期由 `element_size` 给出，
  调用方传 `sizeof(T)`，取元素时 `to_type(*T)` 定型；
- 追加（单个/批量）、中间插入/删除、尾部弹出、按序取元素地址、容量预留、
  清空与显式释放；
- 分配失败、容量溢出、越界、空指针都返回可判别结果，不静默截断；
- 扩容与搬移全部有语言内用例覆盖，`just test-libs`（O0/O2）通过。

非目标：

- 泛型元素类型与静态类型检查（语言无泛型，见 §3）；
- 返回 `[]T` 切片视图（语言禁止从裸指针构造切片，见 §3）；
- 元素析构与所有权追踪（list 只拥有存储块，不拥有元素内部资源）；
- 线程安全、迭代器对象、排序/查找/序列化（排序可直接对 `data` 调
  `libc.qsort`，见 §9）；
- 迁移 `string`/`json`/`toml`/`cli` 已有的私有容器：它们分别是拥有者、
  文档池与固定上限容器，替换会破坏各自的所有权契约，本次不改。

## 2. 位置与消费者

- 位置：`libs/list/`，模块名 `list`，项目模式下 `import list;` 使用。
- 登记：`libs/project.toml` 的 `[lib]` 追加 `list = {path = "./list"}`。
- 文件：`libs/list/list.yh`（类型、常量、私有辅助、`pub` 函数）、
  `libs/list/list.test.yh`（语言内测试）、`libs/list/README.md`（使用说明）。
- 首个消费者：需要「个数到运行期才知道」的序列的应用代码；以及后续按需
  选用 list 的新标准库模块。现有四个私有容器不迁移（理由见 §1）。

## 3. 语言事实与实测（2026-11-10）

| 事实 | 结论 | 证据 |
| --- | --- | --- |
| 无泛型/接口/方法接收者 | 只能做「运行时元素宽度的无类型字节容器」，调用方 `to_type(*T)` 定型；与 `libc.qsort(base, count, width, compare)` 同款路线 | [io 设计](yh-io标准库设计.md) §语言现状；[memory 设计](yh-memory标准库设计.md) §3 |
| 切片只能从数组或切片构造；`p[0..n]`（`p *T`）被拒 | 不提供 `items() []T`；元素地址只能以 `*void` 暴露 | [`sem_expr.yh`](../../compiler/check/sem_expr.yh) 的 `sem_slice`：`切片表达式需要数组或切片`；实测 `tmp/slice-probe1.yh` |
| `*u8` 不能 `to_type([]u8)` | 上述限制没有转换绕过路径 | 实测 `tmp/slice-probe2.yh`：`该转换不支持（标量之间或指针/整数）` |
| `*T` 支持 `u64` 下标与字段读写 | 推荐使用形态：`let items *T = xs.data.to_type(*T)` 后 `items[i].field` | 实测 `tmp/index-probe.yh` |
| `sizeof(T)` 是按类型对齐补齐的字节宽度（`{u8, i64}` = 16，`{u8, u8}` = 2） | 步长取 `sizeof(T)` 时，`malloc` 的 16 字节对齐 + 补齐后的步长保证每个元素对齐 | 实测 `tmp/sizeof-probe.yh`；布局补齐见 [`symbols.yh`](../../compiler/check/symbols.yh) 的 `rpad` |
| `malloc` 结果 ≥16 字节对齐、`alloc(0)` 非空、`free(0)` 无操作 | 容量为 0 的列表不分配，释放后清零可重复释放 | [memory 设计](yh-memory标准库设计.md) §2 |
| `memory` 只有 `alloc`/`release`/`copy`，无 `realloc`；`memory.reallocate` 仍是设计（T1，未实施） | 扩容 = 新分配 + 复制 + 释放，不依赖未实施 API | [`memory.yh`](../../libs/memory/memory.yh) |
| `libc.memmove` 是 `@[extern]` 的 C ABI 函数，可跨模块 `import libc` 使用，已覆盖重叠搬移 | 插入/删除的移位直接复用，不重复实现搬移 | [`libc/memory.yh`](../../libs/libc/memory.yh)、[`libc/test/main.yh`](../../libs/libc/test/main.yh) |
| 区间 `for i in 0..count` 接受 `u64` 上界 | 元素个数与下标统一 `u64`，与 `string` 的长度口径一致 | 实测 `tmp/range-probe.yh` |

结论：**「同类能力中唯一成立」的实现是「连续字节块 + 运行期元素宽度 +
`*void` 元素地址」**；任何带类型参数的容器形态都需要泛型，不在本方案内。

## 4. 设计决策

| 编号 | 决策 | 理由 | 被否决的替代 |
| --- | --- | --- | --- |
| D1 | 单一无类型容器，`element_size` 在运行期给出 | 无泛型；一份实现覆盖所有元素类型；与 `libc.qsort` 的 width 口径一致 | 每类型手写一份（重复、易漂移）；等泛型（`todo` 无排期，且上层封装可后加而不改本模块契约） |
| D2 | 透明结构体 `List`（4 个公开字段），不做 string 式薄句柄 | 列表本质是描述符（data/count/capacity/stride），调用方要直接读 `count`、遍历与传给 C 缓冲 API；句柄只多一次解引用与私有状态块，并不增加安全性（复制句柄同样会双重释放），失败路径更多 | 薄句柄 + 私有状态（`string` 的形态）：对拥有者字符串合理，对描述符过重 |
| D3 | 不提供切片视图；`element_at` 返回 `*void`，越界返回 `0` | 语言禁止从裸指针起步的切片（§3），没有无 UB 的替代 | 返回 `[]T`（编译期被拒）；返回 {data,count} 自造视图（用户无法当 `[]T` 用，徒增概念） |
| D4 | list 不调用元素析构、不追踪元素所有权 | 无泛型即无析构函数注入点；与 C/`libc` 一致 | `drop` 回调字段（无消费者，且回调拿不到元素类型外的上下文） |
| D5 | 扩容：起步 16 个槽位，容量翻倍；上限 `LIST_MAX_BYTES / element_size` | 与 `string` 的 16 字节起点、几何增长同构；均摊 O(1) | 每次 +1（O(n²)）；固定上限（cli 路线，不满足动态需求） |
| D6 | 搬移用 `libc.memmove`（重叠安全），增长复制用 `memory.copy`（不重叠） | 复用已测 C ABI 原语，不复制 40 行重叠复制逻辑 | 在 list 内重写 `string_copy_overlap`（重复实现）；给 `memory` 加 `copy_overlap`（第三份重叠逻辑，且 string 仍留旧的） |
| D7 | 失败原子性：`reserve`/`push`/`push_all`/`insert` 失败时 count、capacity、内容都不变 | 先扩容成功再搬移/写入；失败路径不留半成品 | 先改 count 再扩容（失败后状态不一致） |
| D8 | 无分配器参数；`element_size == 0` 视为无效列表 | 语言无 vtable 消费者（memory 设计 P5 无泛型容器）；无效列表让所有操作返回 `status_invalid_argument`，避免除零 | 每函数传分配器函数指针（无消费者） |

**待决决策点（建议按推荐值定）：**

1. 动词命名：`push`/`push_all` 在编码规范 §2.1 的动词表内；`pop`/`insert`/
   `remove_at` 不在。建议本次把 `pop`/`insert`/`remove` 三个容器惯用动词补进
   [编码规范 §2.1](yh-编码规范.md)（一次，之后复用），而不是
   硬改成 `take_last`、`shift_in` 之类生造词。
2. 是否给元素提供 `set`（按值写入）：建议不做——`element_at` 返回地址后
   调用方直接写，`set` 只是 `copy` 的又一入口。

## 5. 数据模型

```yh
// 字段顺序是 ABI，不许重排。
pub struct List {
    data *u8         // 元素存储起始地址；capacity == 0 时为 0
    count u64        // 已用元素个数
    capacity u64     // 可容纳元素个数
    element_size u64 // 单个元素字节宽度，必须来自 sizeof(T)
}

// Status 是 list 操作的稳定结果分类；应用应按成员比较，不依赖文本。
pub enum Status {
    status_ok
    status_invalid_argument // 空指针参数，或 element_size == 0 的无效列表
    status_overflow         // 容量或字节数越过上界
    status_out_of_memory    // 分配失败
    status_bounds           // index >= count
}
```

常量（模块私有，测试与实现共用；`LIST_MAX_BYTES` 数值与
`STRING_MAX_LENGTH` 同量级，只宣称「不越界」，不宣称能实际分配）：

```yh
const LIST_MIN_CAPACITY u64 = 16              // 首次扩容的起步槽位数
const LIST_MAX_BYTES u64 = 9223372036854775800 // 单块字节上界
```

不变量：

1. `capacity == 0` ⇔ `data == 0`；
2. `count <= capacity`；
3. `data != 0` 时，元素基址 = `data + index * element_size`，且因
   `malloc` ≥16 字节对齐 + `sizeof(T)` 已按对齐补齐，每个元素地址对齐；
4. `data .. data + capacity * element_size` 是本次分配的全部字节，list 独占；
5. `count` 之后的槽位未初始化（`malloc` 不置零）；只有 `push`/`push_all`/
   `insert` 写过的槽位可读，直接读 `[count, capacity)` 是未定义行为。

## 6. API 契约

| 签名 | 语义 | 失败与副作用 |
| --- | --- | --- |
| `make(element_size u64) List` | 返回空列表（`data`/`count`/`capacity` 为 0，`element_size` 原样保存）；不分配 | `element_size == 0` 得到无效列表，后续操作报 `status_invalid_argument` |
| `release(value *List) void` | 释放存储块并把 4 个字段清零 | `value == 0` 或零列表时无操作；可重复调用（`free(0)` 无操作） |
| `clear(value *List) void` | `count = 0`，保留 `capacity` 与 `data`；不改写字节 | `value == 0` 无操作 |
| `reserve(value *List, capacity u64) Status` | 保证容量至少为该值；不改 `count` | 扩容可能搬移元素；失败（invalid_argument/overflow/out_of_memory）时列表不变 |
| `element_at(value *List, index u64) *void` | 返回第 `index` 个元素的地址 | `value == 0`、`index >= count`、`data == 0` 时返回 `0` |
| `push(value *List, element *void) Status` | 复制 `element_size` 字节到尾部，`count += 1` | 可能扩容；`element == 0` 或 `element_size == 0` 为 invalid_argument；失败时 `count` 不变 |
| `push_all(value *List, elements *void, count u64) Status` | 复制 `count` 个元素（`count * element_size` 字节）到尾部 | `count == 0` 返回 ok（此时不看 `elements`）；`count > 0 && elements == 0` 为 invalid_argument；一次预留，不做逐元素检查 |
| `pop(value *List, out *void) bool` | 复制尾元素到 `out`，`count -= 1` | 空列表返回 false；`out == 0` 表示只丢弃 |
| `insert(value *List, index u64, element *void) Status` | 在 `index` 处插入，`[index, count)` 后移一个元素 | `index > count` 为 `status_bounds`；`index == count` 等价 `push`；可能扩容 |
| `remove_at(value *List, index u64, out *void) bool` | 复制第 `index` 个元素到 `out` 后移除，`[index+1, count)` 前移 | 越界返回 false；`out == 0` 表示只丢弃 |

导出面只有上表 10 个函数 + `List`/`Status` 两个类型；无 `pub const`
（测试与实现在同模块，私有常量同样可断言）。字段直接公开读取，
不额外提供 `count()`/`capacity()` 访问函数。

## 7. 内部实现要点

私有辅助（约 60 行）：

```yh
// list_max_count：本次 element_size 下允许的最大元素个数；0 表示不可用。
fn list_max_count(value *List) u64            // LIST_MAX_BYTES / element_size

// list_next_capacity：算出 >= needed 的新容量；0 表示溢出。
fn list_next_capacity(value *List, needed u64) u64
//   next = max(capacity, LIST_MIN_CAPACITY)
//   next < needed 时：next > max/2 ? needed : 翻倍再补 needed
//   next < needed || next > max 时返回 0

// list_ensure：把容量保证到 needed；成功后 data/capacity 更新，失败不改列表。
fn list_ensure(value *List, needed u64) Status
//   needed <= capacity → ok
//   next = list_next_capacity(...)；0 → overflow
//   data = memory.alloc(next * element_size)；0 → out_of_memory
//   count > 0 时 memory.copy(new, old, count * element_size)
//   memory.release(old)；更新 data/capacity

// list_element：不做边界检查的元素地址（内部调用者有责任）。
fn list_element(value *List, index u64) *void
```

搬移与写入：

- `insert`：`list_ensure(count + 1)` → `libc.memmove(element_at(index+1),
  element_at(index), (count - index) * element_size)` → 写元素 → `count += 1`；
- `remove_at`：复制到 `out` → `libc.memmove(element_at(index),
  element_at(index+1), (count - index - 1) * element_size)` → `count -= 1`；
- `push`：`list_ensure(count + 1)` 后 `memory.copy(element_at(count), element,
  element_size)`；`count + 1` 的 u64 回绕由 `list_next_capacity` 的 `max` 检查挡住
  （`needed` 超上界即 overflow）。

文件内顺序按编码规范：模块头 → 常量 → 类型 → 私有辅助 → `pub` 函数 → 测试
（测试在 `list.test.yh`）。

## 8. 误用与未定义行为

必须在 `list.yh` 文件头与 `README.md` 写清的硬规则：

1. **步长只能来自 `sizeof(T)`**。任意自定宽度（如 3）可能在严格对齐目标上
   产生错位访问；不保证除 `sizeof(T)` 以外宽度的对齐。
2. **元素来源不得指向本列表的存储**。`push`/`push_all`/`insert` 在扩容时会
   `free` 旧块，插入时会 `memmove` 移动源区域；要插入「列表里已有的元素」，
   先复制到局部变量，再从局部变量地址传入。
3. **指针失效**：`reserve`/`push`/`push_all`/`insert`/`clear`/`release` 之后，
   此前 `element_at` 返回的指针与缓存的 `let items *T = xs.data.to_type(*T)`
   全部失效；`pop`/`remove_at` 只使被移动元素之后的指针失效。
4. **不析构**：list 只拥有存储块。元素含 `string.String` 句柄时，移除/释放
   之前由调用方决定逐个 `string.release` 还是 `string.move` 出去，否则泄漏。
5. **越界直读未定义**：`count` 之后的槽位未初始化；`data` 越界访问、扩容
   后继续用旧 `data` 都是未定义行为，语言不做检查。
6. **线程安全**：无；同一列表并发写未定义（无全局状态，不同列表可并行）。
7. **空指针**：所有 `*List` 参数在入口检查 `== 0`（返回
   `status_invalid_argument`/`false`/`void`）；`out` 参数按契约允许 `0`。

## 9. 使用形态

i64 列表：

```yh
import list

let xs list.List = list.make(sizeof(i64).to_type(u64))
let value i64 = 42
if (list.push(&xs, (&value).to_type(*void)) != list.status_ok) {
    // 处理 invalid_argument/overflow/out_of_memory
}
let items *i64 = xs.data.to_type(*i64)
let total i64 = 0
for i in 0..xs.count {
    total += items[i]
}
list.release(&xs)
```

结构体元素（推荐：把 `data` 定型一次，按 `u64` 下标读写）：

```yh
let points list.List = list.make(sizeof(Point).to_type(u64))
let point Point
point.x = 1
point.y = 2
list.push(&points, (&point).to_type(*void))
let cached *Point = points.data.to_type(*Point)
cached[0].x = 3    // 容量未变，缓存指针有效
```

排序（不包装，直接复用 C ABI 排序）：

```yh
import libc

@[extern] fn compare_point(left *void, right *void) int { /* ... */ }

libc.qsort(xs.data.to_type(*void), xs.count, xs.element_size, compare_point)
```

`compare_point` 的签名是 `fn(*void, *void) int`，且实参必须带 `@[extern]`
（C ABI 回调，编译器校验）；`libc.qsort` 首版是稳定插入排序，最坏 O(n²)，
大列表的排序策略不在本模块范围内。

与 C 缓冲互操作：`data` + `count * element_size` 可直接传给
`io.write_fd`/`memory.copy`/`libc` 系列。

## 10. 测试与验收

`libs/list/list.test.yh`（语言内 `test "行为描述" { $assert(...) }`）：

| 用例 | 断言要点 |
| --- | --- |
| `make` 产生空列表且拒绝无效步长 | `make(0)` 的 4 个字段为 0；`make(8)` 保留步长且不分配；无效列表 `push` 返回 `status_invalid_argument` |
| `push` 跨过 16 槽起点触发扩容 | 旧值全部保留；`capacity > 16`；`data` 改变（扩容发生过）；新值在尾部 |
| `element_at` 命中与越界 | 命中地址读回写入值；`index == count`、空列表、`value == 0` 返回 0 |
| `insert` 头/中/尾 | 顺序与 `count` 正确；`insert(count)` 等价 push；`insert(count+1)` 返回 `status_bounds` |
| `remove_at` 头/中/尾 | `out` 得到被删元素；后续元素前移；`count` 减一；越界返回 false |
| `pop` 空列表与非空 | 空列表 false；非空时 `out` 得到尾元素 |
| `clear` | `count == 0`、`capacity` 不变、可继续 push |
| `release` 幂等 | 字段清零；再次 `release` 不崩 |
| `push_all` | 一次追加多个元素，偏移与顺序正确；`count == 0` 返回 ok |
| 容量上界 | `reserve(&xs, LIST_MAX_BYTES)`（`element_size = 8`）返回 `status_overflow`，且列表状态不变 |
| 结构体步长对齐 | `{u8, i64}`（16 字节）元素的字段经 `data.to_type(*T)` 读写正确 |

验收入口：

- 定向：`cd libs && ../yh test --filter list`；
- 全库：`just test-libs`（O0 与 `tmp/libs-o2` 的 O2 两份，已含 `*.test.yh`
  自动发现，不需要改 justfile）；
- 文档：`libs/list/README.md` 新增；`docs/03-design/yh-标准库设计.md` 增补
  list 小节；`docs/todo.md` 删除本条；`docs/finish.md` 记录证据。
- 本方案不动 `compiler/`、`docs/yh.g4`、prelude，因此 `just test` 与
  `just selfhost-native` 不是本切片的针对性门禁；合并前按仓库规则跑
  `just build` 确认编译器仍可构建。

## 11. 分期

| 切片 | 内容 | 验收 |
| --- | --- | --- |
| L0（核心，约 220 行 + 测试） | `List`/`Status`、常量、`make`/`release`/`clear`/`reserve`/`element_at`/`push`，私有 `list_max_count`/`list_next_capacity`/`list_ensure`/`list_element` | 用例 1–3、8、10、11；`yh test list` 通过 |
| L1（搬移，约 80 行 + 测试） | `push_all`/`pop`/`insert`/`remove_at` | 用例 4–7、9；`just test-libs`（O0/O2）通过 |
| L2（文档与登记） | `README.md`、`libs/project.toml` 登记、`yh-标准库设计.md` 总表、`todo`/`finish`、编码规范动词表（若 §4 决策点 1 采纳） | 文档评审；全库门禁仍绿 |

每片顺序：先写用例（确认失败原因正确）→ 最小实现 → 定向通过 → 更新文档。
L0 就能交付「可增长 + 可访问」的最小可用切片；L1 的搬移正确性单独可测。

## 12. 风险与回退

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 无类型容器的类型误用（`to_type` 到错误类型） | 运行期错读，静态无法发现 | README 与文件头写死「element_size 必须来自 sizeof(T)」；结构体步长用例挡偏；上层可按需加薄包装函数（类型在包装层固定） |
| 指针失效与别名（§8.2、§8.3） | 扩容后旧指针读到旧块 | 契约硬规则 + 函数注释逐条标注；不在测试里依赖 UB |
| 依赖 `libc.memmove` | 目标必须带 C 运行时的 `memmove`（yh 已链接 CRT/libSystem）；无 C 运行时的目标不可用 | 真有该目标时改为 list 内部按方向逐字节复制（约 20 行），接口不变；Windows CRT 提供 `memmove`（未在本机实测） |
| `memory.reallocate`（T1）将来落地 | 与内部「分配+复制+释放」重复 | 只替换 `list_ensure` 的复制段，API 与语义不变 |
| 与将来泛型容器的重复 | 两套容器并存 | 泛型落地后作为本模块之上的类型化封装，本模块的线性内存契约不变；两者不互相迁移 |
| 整体回退 | 无其他模块依赖 list | 删除 `libs/list/` 与 `[lib]` 登记、文档条目即可，不触及编译器与既有模块 |
