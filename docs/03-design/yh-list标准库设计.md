# yh list 标准库设计

修改时间：2026-11-10

状态：**L0–L2 已实施（2026-11-10）**；同日按 **V 语言内建数组方法集**补齐
接口（L3，已实施，见 §11）。本文定义 `libs/list`（堆上连续存储的动态列表，
下称 list 或 ArrayList）的 API 契约、语言约束、误用边界与验收口径。
面向当前编译器设计：**无泛型、无接口、无方法接收者**；不新增语言语法。

## 1. 目标与非目标

目标：

- 一份实现支持任意元素类型：元素宽度在运行期由 `element_size` 给出，
  调用方传 `sizeof(T)`，取元素时 `to_type(*T)` 定型；
- 接口与 V 内建数组（`array`）的方法集对齐（映射表见
  [`libs/list/README.md`](../../libs/list/README.md)）：追加（单个/批量）、
  头尾插入/删除、区间删除、弹出、截断、丢弃、首尾访问、容量增减、
  克隆/重复/切片、倒序、排序、查找、谓词与逐元素变换；
- 分配失败、容量溢出、越界、空指针都返回可判别结果，不静默截断；
- 扩容与搬移全部有语言内用例覆盖，`just test-libs`（O0/O2）通过。

非目标：

- 泛型元素类型与静态类型检查（语言无泛型，见 §3）；
- 返回 `[]T` 切片视图（语言禁止从裸指针构造切片，见 §3）；
- 元素析构与所有权追踪（list 只拥有存储块，不拥有元素内部资源）；
- 线程安全、迭代器对象、字符串化与序列化（`str`/`hex` 归 `string`/`fmt`，
  见 §4 的 V 对齐表）；
- 运算符重载（`arr[i]`、`x in arr`、`arr == arr` 由 `element_at`/`contains`/
  `compare` 循环代替）；
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
| `libc.memmove` 是 `@[extern]` 的 C ABI 函数，但在 Windows 零 CRT 上与 prelude 的运行时符号重复定义 | 插入/删除的移位改为模块内 `list_copy_overlap`（约 20 行，按方向逐字节） | 实测 lld-link `duplicate symbol: memmove/memset`（list 同时 import memory 与 libc） |
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
| D6 | 搬移用模块内 `list_copy_overlap`（重叠安全），增长复制用 `memory.copy`（不重叠） | Windows 零 CRT 上 libc 的 `@[extern] memset/memmove` 与 prelude 重复符号；内置复制让 list 只依赖 memory，接口不变 | 依赖 `libc.memmove`（CI 实测 lld-link duplicate symbol）；给 `memory` 加 `copy_overlap`（第三份重叠逻辑，且 string 仍留旧的） |
| D7 | 失败原子性：`reserve`/`push`/`push_all`/`insert` 失败时 count、capacity、内容都不变 | 先扩容成功再搬移/写入；失败路径不留半成品 | 先改 count 再扩容（失败后状态不一致） |
| D8 | 无分配器参数；`element_size == 0` 视为无效列表 | 语言无 vtable 消费者（memory 设计 P5 无泛型容器）；无效列表让所有操作返回 `status_invalid_argument`，避免除零 | 每函数传分配器函数指针（无消费者） |
| D9 | 接口按 **V 内建数组方法集**对齐；无法对齐的少数方法逐条说明 | 用户指定 V 为参照；V 的数组方法覆盖了动态列表的完整操作面，命名在 V 生态里可预期 | 自拟一套命名（与参照漂移）；Python/Java 命名（与用户参照不符） |
| D10 | 需要元素语义的方法收回调：比较 `fn(*void,*void) int`、谓词 `fn(*void) bool`、变换 `fn(*void,*void) void` | 无泛型无 `Eq`/`Ord`，只能由调用方提供元素语义；`map` 用「写入 out 槽位」而不是返回值，避免回调返回栈地址的生命周期问题 | `map` 返回 `*void`（地址生命周期由调用方保证，易错）；为每种元素类型生成专用函数（无泛型无法生成） |

**命名与 V 对齐的例外（结论，2026-11-10 用户确认）：**

- 新方法沿用 V 的方法名（`first`/`last`/`prepend`/`pop_left`/`delete_last`/
  `delete_many`/`trim`/`drop`/`reset`/`grow_cap`/`grow_len`/`clone`/`repeat`/
  `slice`/`reverse`/`reverse_in_place`/`sort`/`sorted`/`contains`/`index`/
  `last_index`/`any`/`all`/`count`/`filter`/`map`）。这些动词多数不在
  [编码规范 §2.1](yh-编码规范.md) 的动词表里，本模块按「参照 API 对齐」
  作为记录在案的例外，不另造同义词。
- 已有 10 个方法保留原名（`push`/`push_all`/`element_at`/`remove_at` 等），
  不为了字面对齐改名；V 名称的对应关系见 README 映射表。
- 编码规范本身不改：该表是 `compiler/` 与 `libs/` 存量用词的统计，扩充动词表
  不在本次范围内。

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
    status_bounds           // 下标越界（insert、slice）
}

// 返回新列表的方法统一用它：失败时 value 为零值列表，调用方无需清理。
pub struct ListResult {
    status Status
    value List
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

回调类型缩写：

- `compare` = `fn(*void, *void) int`：0 表示相等，小于 0 表示前者在前（语义同
  `libc.qsort`）；用于查找与排序。
- `predicate` = `fn(*void) bool`：判断一个元素。
- `transform` = `fn(*void, *void) void`：从第 1 个参数读源元素，把结果**写满**
  第 2 个参数指向的结果槽位。

回调都是普通 yh 函数（不需要 `@[extern]`），且**必须非空**：语言不支持函数
指针与 `0` 比较，传 `0` 会在调用处崩溃（与 `libc.qsort` 同一约束）。

生命周期：

| 签名 | 语义 | 失败与副作用 |
| --- | --- | --- |
| `make(element_size u64) List` | 返回空列表（`data`/`count`/`capacity` 为 0，`element_size` 原样保存）；不分配 | `element_size == 0` 得到无效列表，后续操作报 `status_invalid_argument` |
| `release(value *List) void` | 释放存储块并把 4 个字段清零 | `value == 0` 或零列表时无操作；可重复调用（`free(0)` 无操作） |
| `clear(value *List) void` | `count = 0`，保留 `capacity` 与 `data`；不改写字节 | `value == 0` 无操作 |

容量与截断：

| 签名 | 语义 | 失败与副作用 |
| --- | --- | --- |
| `reserve(value *List, capacity u64) Status` | 保证容量至少为该值；不改 `count` | 扩容可能搬移元素；失败时列表不变 |
| `grow_cap(value *List, amount u64) Status` | 在当前容量上增加 `amount` 个槽位 | `amount == 0` 返回 ok；越上界为 overflow；失败时列表不变 |
| `grow_len(value *List, amount u64) Status` | `count` 增加 `amount`，新增槽位**不初始化**（与 V 相同） | 越上界为 overflow；失败时 `count` 不变；读新增槽位是未定义行为 |
| `trim(value *List, count u64) void` | 把 `count` 截断到指定值；指定值更大时无操作 | 丢弃尾部元素，不搬移、不改容量 |

追加与插入：

| 签名 | 语义 | 失败与副作用 |
| --- | --- | --- |
| `push(value *List, element *void) Status` | 复制 `element_size` 字节到尾部，`count += 1` | 可能扩容；`element == 0` 或步长 0 为 invalid_argument；失败时 `count` 不变 |
| `push_all(value *List, elements *void, count u64) Status` | 复制 `count` 个元素到尾部 | `count == 0` 返回 ok（不看 `elements`）；`count > 0 && elements == 0` 为 invalid_argument；一次预留 |
| `prepend(value *List, element *void) Status` | 在头部插入，等价 `insert(value, 0, element)` | 状态与 `insert` 相同；可能扩容 |
| `insert(value *List, index u64, element *void) Status` | 在 `index` 处插入，`[index, count)` 后移一个元素 | `index > count` 为 status_bounds；`index == count` 等价 push |

删除、弹出与丢弃：

| 签名 | 语义 | 失败与副作用 |
| --- | --- | --- |
| `pop(value *List, out *void) bool` | 复制尾元素到 `out`，`count -= 1` | 空列表返回 false；`out == 0` 表示只丢弃 |
| `pop_left(value *List, out *void) bool` | 复制首元素到 `out`，后续元素前移；等价 `remove_at(value, 0, out)` | 空列表返回 false；O(n) 搬移 |
| `remove_at(value *List, index u64, out *void) bool` | 复制第 `index` 个元素后移除，`[index+1, count)` 前移 | 越界返回 false；O(n) 搬移 |
| `delete_last(value *List) bool` | 只移除尾元素，不返回内容 | 空列表返回 false；不搬移、不改容量 |
| `delete_many(value *List, index u64, count u64) bool` | 删除从 `index` 起的 `count` 个元素，后续元素前移 | `count == 0` 返回 true（空操作）；越界返回 false；O(n) 搬移 |
| `drop(value *List, count u64) void` | 丢弃前 `count` 个元素，剩余元素前移到存储起始处；超过 `count` 时清空 | 容量不变（V 会同步减 cap）；O(n) 搬移 |

访问与查询：

| 签名 | 语义 | 失败与副作用 |
| --- | --- | --- |
| `element_at(value *List, index u64) *void` | 第 `index` 个元素地址 | `value == 0`、`data == 0`、`index >= count` 时返回 `0` |
| `first(value *List) *void` / `last(value *List) *void` | 首/尾元素地址 | 空列表或 `value == 0` 返回 `0`（V 会 panic） |
| `contains(value *List, key *void, compare) bool` | 是否存在与 `key` 相等的元素 | `key == 0`、无效列表返回 false |
| `index(value *List, key *void, compare) i64` | 第一个相等元素下标 | 没找到返回 `-1`（V 同）；`key == 0` 返回 `-1` |
| `last_index(value *List, key *void, compare) i64` | 最后一个相等元素下标 | 没找到返回 `-1` |
| `any(value *List, predicate) bool` | 是否存在满足谓词的元素 | 空列表返回 false |
| `all(value *List, predicate) bool` | 是否所有元素都满足谓词 | 空列表返回 true（与 V 一致） |
| `count(value *List, predicate) u64` | 满足谓词的元素个数 | 无效列表返回 0；与字段 `count` 不冲突 |

返回新列表（`ListResult`，源不变；失败时 `value` 为零值列表）：

| 签名 | 语义 | 失败与副作用 |
| --- | --- | --- |
| `clone(value *List) ListResult` | 深复制整份内容，与源相互独立 | 无效列表为 invalid_argument |
| `repeat(value *List, count u64) ListResult` | 内容重复 `count` 次；空源或 0 次得到有效空列表 | `count * value.count` 越上界为 overflow |
| `slice(value *List, start u64, end u64) ListResult` | 复制 `[start, end)`；`start == end` 得到有效空列表 | `start > end` 或 `end > count` 为 status_bounds；**返回副本**，不是视图（§3） |
| `reverse(value *List) ListResult` | 元素顺序颠倒的副本 | 无效列表为 invalid_argument |
| `sorted(value *List, compare) ListResult` | 排好序的副本，等价 clone 后 sort | 同上；`compare` 必须非空 |
| `filter(value *List, predicate) ListResult` | 只保留谓词为真的元素（保持原顺序） | 结果容量最多预留源的 `count`；失败时释放半成品并返回失败 |
| `map(value *List, transform, element_size u64) ListResult` | 逐元素变换；`element_size` 是**目标**元素宽度 | 步长 0 为 invalid_argument；回调必须写满结果槽位 |

原地变换：

| 签名 | 语义 | 失败与副作用 |
| --- | --- | --- |
| `reverse_in_place(value *List) void` | 首尾交换，原地倒序 | 元素字节被搬动，旧元素指针失效 |
| `sort(value *List, compare) void` | 稳定插入排序，最坏 O(n²)（与 `libc.qsort` 首版一致） | 元素不足 2 个无操作；`compare` 必须非空 |
| `reset(value *List) void` | 把已用元素 `[0, count)` 的字节清零，保留 `count`/容量 | 只适合标量/字节元素；含指针/句柄时语义由调用方负责（V 同为 unsafe） |

导出面：上表 36 个函数 + `List`/`Status`/`ListResult` 三个类型；无 `pub const`
（测试与实现在同模块，私有常量同样可断言）。字段直接公开读取，
不额外提供 `count()`/`capacity()` 访问函数。与 V 的方法映射、以及
`pointers`/`str`/`hex`/`wait`/深度复制不提供的原因，见
[`libs/list/README.md`](../../libs/list/README.md)。

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

// list_swap：交换两块 width 字节元素存储（排序/倒序用）。
fn list_swap(left *void, right *void, width u64) void

// list_zero：把 destination 起 byte_count 字节写成 0（reset 用）。
fn list_zero(destination *void, byte_count u64) void

// list_build：把 source 起 count 个元素复制成新列表（clone/slice 用）。
// count == 0 返回不分配的有效空列表；步长 0/source 空/分配失败返回失败结果。
fn list_build(element_size u64, source *void, count u64) ListResult

// list_result_ok / list_result_error：ListResult 的两个构造器。
```

搬移与写入：

- `insert`：`list_ensure(count + 1)` → `list_copy_overlap(element_at(index+1),
  element_at(index), (count - index) * element_size)` → 写元素 → `count += 1`；
- `remove_at`：复制到 `out` → `list_copy_overlap(element_at(index),
  element_at(index+1), (count - index - 1) * element_size)` → `count -= 1`；
  `pop_left` 直接复用 `remove_at(value, 0, out)`；
- `push`：`list_ensure(count + 1)` 后 `copy(element_at(count), element,
  element_size)`；`count + 1` 的 u64 回绕由 `list_next_capacity` 的 `max` 检查挡住
  （`needed` 超上界即 overflow）；
- `delete_many`/`drop`：同一套 `list_copy_overlap` 前移，先校验区间再改 `count`；
- `trim`/`delete_last`：只改 `count`，不搬移、不改容量；
- `grow_cap`/`grow_len`：先把 `amount` 与 `list_max_count` 做上界差校验，再
  `list_ensure(count + amount)`，最后改 `capacity`/`count`；
- `clone`/`slice`：`list_build` 一次分配 + 一次 `memory.copy`；
- `repeat`：`list_ensure(count * value.count)` 后按源长度循环 `memory.copy`；
- `reverse_in_place`/`sort`：首尾或相邻元素 `list_swap`；`sort` 是稳定插入排序，
  `sorted` = `clone` + `sort`，`reverse` = `clone` + `reverse_in_place`；
- `filter`/`map`：先 `list_ensure` 到源的 `count`（结果不会更大），逐元素
  `push` 或 `transform`；中途失败时 `release` 半成品并返回失败结果。

文件内顺序按编码规范：模块头 → 常量 → 类型 → 私有辅助 → `pub` 函数 → 测试
（测试在 `list.test.yh`）。

## 8. 误用与未定义行为

必须在 `list.yh` 文件头与 `README.md` 写清的硬规则：

1. **步长只能来自 `sizeof(T)`**。任意自定宽度（如 3）可能在严格对齐目标上
   产生错位访问；不保证除 `sizeof(T)` 以外宽度的对齐。
2. **元素来源不得指向本列表的存储**。`push`/`push_all`/`insert` 在扩容时会
   `free` 旧块，插入时会 `memmove` 移动源区域；要插入「列表里已有的元素」，
   先复制到局部变量，再从局部变量地址传入。
3. **指针失效**：`reserve`/`grow_cap`/`push`/`push_all`/`prepend`/`insert`/
   `clear`/`release` 之后，此前 `element_at`/`first`/`last` 返回的指针与缓存的
   `let items *T = xs.data.to_type(*T)` 全部失效；`pop`/`pop_left`/`remove_at`/
   `delete_many`/`delete_last`/`drop`/`reverse_in_place`/`sort` 只使被搬动元素
   及之后的指针失效（`delete_last`/`pop` 不搬移）。
4. **不析构**：list 只拥有存储块。元素含 `string.String` 句柄时，移除/释放
   之前由调用方决定逐个 `string.release` 还是 `string.move` 出去，否则泄漏。
5. **越界直读未定义**：`count` 之后的槽位未初始化（`grow_len` 新增的槽位同样
   未初始化）；`data` 越界访问、扩容后继续用旧 `data` 都是未定义行为。
6. **回调必须非空**：语言不支持函数指针与 `0` 比较，传 `0` 会在调用处崩溃；
   比较回调对同一对元素必须给出稳定结果，否则排序/查找结果无意义。
7. **`map` 的 `transform` 必须写满结果槽位**：结果槽位在回调写入前未初始化，
   回调没写到的字节是垃圾。
8. **`reset` 只适合标量/字节元素**：含指针或句柄的元素清零后语义由调用方
   负责（V 的 `reset` 同为 unsafe）。
9. **线程安全**：无；同一列表并发写未定义（无全局状态，不同列表可并行）。
10. **空指针**：所有 `*List` 参数在入口检查 `== 0`（返回
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

排序与查找（内置，回调是普通 yh 函数）：

```yh
fn compare_i64(left *void, right *void) int {
    let a *i64 = left.to_type(*i64)
    let b *i64 = right.to_type(*i64)
    if (a[0] < b[0]) { return -1 }
    if (a[0] > b[0]) { return 1 }
    return 0
}

list.sort(&xs, compare_i64)          // 原地稳定排序，最坏 O(n²)
let ordered list.ListResult = list.sorted(&xs, compare_i64)   // 排序副本
let found i64 = list.index(&xs, (&target).to_type(*void), compare_i64)  // -1 = 没有
```

需要 C ABI 排序时仍可对 `data` 直接调 `libc.qsort`，此时回调必须带
`@[extern]`（C ABI 回调，编译器校验），签名同为 `fn(*void, *void) int`。

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
| 首尾访问与头插 | 空列表 `first`/`last` 返回 0；`prepend` 后顺序与 `count` 正确；空元素指针为 invalid_argument |
| `pop_left`/`delete_last`/`delete_many` | 取首元素并前移；`delete_last` 只减 count；区间删除与越界 false；空删除返回 true |
| `trim`/`drop` | 截断/丢弃后的内容与 count；容量不变；`drop` 超过个数时清空 |
| `reset` | 已用元素字节归零、`count` 不变 |
| `grow_cap`/`grow_len` | 容量增量与上界 overflow；`count` 增量且保留旧内容；`grow_len(0)` 无事 |
| `clone`/`repeat`/`slice` | 独立存储（`data` 不同、改副本不影响源）、重复内容顺序、区间副本、越界 bounds |
| `reverse`/`reverse_in_place`/`sort`/`sorted` | 副本与原地语义；排序稳定性（相等元素保持相对顺序） |
| `contains`/`index`/`last_index` | 命中下标；重复值取首个/末个；缺失与 `key == 0` 返回 -1 |
| `any`/`all`/`count`/`filter` | 空列表 any=false、all=true、count=0；过滤结果顺序正确且源不变 |
| `map` | i64 → i64 与 i64 → f64（改变步长）；步长 0 为 invalid_argument |
| 失败路径 | 无效列表的 `clone`/`repeat`/`slice`/`filter`/`map` 返回 invalid_argument |

验收入口（共 31 例）：

- 定向：`cd libs && ../yh test --filter list`（O0 全绿）；
- 全库：`just test-libs`（O0 与 `tmp/libs-o2` 的 O2 两份，已含 `*.test.yh`
  自动发现，不需要改 justfile）；
- 文档：`libs/list/README.md` 的 API 表与 V 映射表；`docs/03-design/yh-标准库设计.md`
  的 list 小节；`docs/finish.md` 记录证据。
- 本方案不动 `compiler/`、`docs/yh.g4`、prelude，因此 `just test` 与
  `just selfhost-native` 不是本切片的针对性门禁；合并前按仓库规则跑
  `just build` 确认编译器仍可构建。

## 11. 分期

| 切片 | 内容 | 验收 |
| --- | --- | --- |
| L0（核心，约 220 行 + 测试） | `List`/`Status`、常量、`make`/`release`/`clear`/`reserve`/`element_at`/`push`，私有 `list_max_count`/`list_next_capacity`/`list_ensure`/`list_element` | 用例 1–3、8、10、11；`yh test list` 通过 |
| L1（搬移，约 80 行 + 测试） | `push_all`/`pop`/`insert`/`remove_at` | 用例 4–7、9；`just test-libs`（O0/O2）通过 |
| L2（文档与登记） | `README.md`、`libs/project.toml` 登记、`yh-标准库设计.md` 总表、`todo`/`finish` | 文档评审；全库门禁仍绿 |
| L3（V 对齐，**2026-11-10 已实施**，约 330 行 + 测试） | `ListResult` 与 26 个新方法：首尾访问、`prepend`/`pop_left`/`delete_last`/`delete_many`、`trim`/`drop`/`reset`、`grow_cap`/`grow_len`、`clone`/`repeat`/`slice`、`reverse`/`reverse_in_place`/`sort`/`sorted`、`contains`/`index`/`last_index`、`any`/`all`/`count`/`filter`/`map`；私有 `list_swap`/`list_zero`/`list_build` | 用例 12–31（29 例新增断言组）；`just test-libs`（O0/O2）通过 |

每片顺序：先写用例（确认失败原因正确）→ 最小实现 → 定向通过 → 更新文档。
L0 就能交付「可增长 + 可访问」的最小可用切片；L1 的搬移正确性单独可测；
L3 不改既有 10 个方法的签名与语义，只在同一模块内扩充。

## 12. 风险与回退

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 无类型容器的类型误用（`to_type` 到错误类型） | 运行期错读，静态无法发现 | README 与文件头写死「element_size 必须来自 sizeof(T)」；结构体步长用例挡偏；上层可按需加薄包装函数（类型在包装层固定） |
| 回调类型与元素不匹配（比较/谓词/变换写错类型） | 运行期错读或比较结果无意义 | 回调形态在 README 与设计里各写一遍；测试覆盖 i64 与 16 字节结构体两种元素 |
| 指针失效与别名（§8.2、§8.3） | 扩容后旧指针读到旧块 | 契约硬规则 + 函数注释逐条标注；不在测试里依赖 UB |
| 搬移实现 | 模块内逐字节复制，元素搬移为 O(count) 且无 SIMD 优化 | 已按 §12 回退方案实现；接口不变，未来可换 `memory.copy_overlap`（若落地） |
| `sort`/`sorted` 的 O(n²) | 大列表排序慢 | 与 `libs/libc` 的 qsort 首版同档；需要时换内省排序，接口不变 |
| V 语义差异（越界 panic → 返回值、`pop` 用 out 参数、`slice` 返回副本） | 按 V 直觉使用会漏判返回码 | README 映射表逐条标注差异；失败路径全部有测试（越界 false / -1 / status_bounds） |
| `memory.reallocate`（T1）将来落地 | 与内部「分配+复制+释放」重复 | 只替换 `list_ensure` 的复制段，API 与语义不变 |
| 与将来泛型容器的重复 | 两套容器并存 | 泛型落地后作为本模块之上的类型化封装，本模块的线性内存契约不变；两者不互相迁移 |
| 整体回退 | 无其他模块依赖 list | 删除 `libs/list/` 与 `[lib]` 登记、文档条目即可，不触及编译器与既有模块 |
