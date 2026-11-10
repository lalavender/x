# libs/list —— yh 动态列表（ArrayList）

`import list;` 提供「连续字节块 + 运行期元素宽度」的动态列表。接口按 V 语言
内建数组（array）的方法集对齐（映射表见下文），差异集中在回调形态与
「越界返回结果而不是 panic」。设计见
[`docs/03-design/yh-list标准库设计.md`](../../docs/03-design/yh-list标准库设计.md)。

## 为什么没有泛型

语言当前无泛型、无接口、无方法接收者，且禁止从裸指针构造 `[]T`。因此本模块
选择与 C `qsort(base, count, width, compare)` 相同的路线：元素宽度由
`element_size` 在运行期给出，元素地址以 `*void` 暴露，取用时
`to_type(*T)` 定型。**`element_size` 必须来自 `sizeof(T)`**。

无类型容器无法直接比较或变换元素，因此需要元素语义的方法都收回调：

| 回调 | 形态 | 用于 |
| --- | --- | --- |
| 比较 | `fn(*void, *void) int`，0 表示相等，语义同 `libc.qsort` | `contains`/`index`/`last_index`/`sort`/`sorted` |
| 谓词 | `fn(*void) bool` | `any`/`all`/`count`/`filter` |
| 变换 | `fn(*void, *void) void`：从第 1 个参数读，写满第 2 个槽位 | `map` |

回调是普通 yh 函数（不需要 `@[extern]`），**必须非空**：语言不支持函数指针与
`0` 比较，传 `0` 会在调用处崩溃。

## 模型

```yh
pub struct List {
    data *u8         // 存储块起始地址；capacity == 0 时为 0
    count u64        // 已用元素个数
    capacity u64     // 可容纳元素个数
    element_size u64 // 单个元素字节宽度，必须来自 sizeof(T)
}

pub struct ListResult {  // 返回新列表的方法用这个结果
    status Status
    value List       // 失败时为零值列表，调用方无需清理
}
```

不变量：`capacity == 0` ⇔ `data == 0`；`count <= capacity`；
`[count, capacity)` 的槽位未初始化，读取是未定义行为。
`List` 只拥有存储块，不拥有元素内部资源，也不调用任何析构函数。

## 快速开始

```yh
import list

fn main() int {
    let xs list.List = list.make(sizeof(i64).to_type(u64))
    let value i64 = 42
    if (list.push(&xs, (&value).to_type(*void)) != list.status_ok) {
        return 1
    }
    let items *i64 = xs.data.to_type(*i64)
    if (items[0] != 42) { return 2 }
    list.release(&xs)
    return 0
}
```

`Status` 的成员跨模块写成 `list.status_ok`、`list.status_bounds` 等；
结构体元素可把 `data` 定型一次后按下标读写字段：

```yh
let points list.List = list.make(sizeof(Point).to_type(u64))
let cached *Point = points.data.to_type(*Point)
cached[0].x = 3
```

## API

生命周期：

| 函数 | 语义 |
| --- | --- |
| `make(element_size u64) List` | 返回空列表，不分配；`element_size == 0` 得到无效列表 |
| `release(value *List) void` | 释放存储并清零 4 个字段；可重复调用 |
| `clear(value *List) void` | `count = 0`，保留 `data` 与 `capacity` |

容量与截断：

| 函数 | 语义 |
| --- | --- |
| `reserve(value *List, capacity u64) Status` | 保证容量至少为 `capacity`，不改 `count` |
| `grow_cap(value *List, amount u64) Status` | 在当前容量上增加 `amount` 个槽位 |
| `grow_len(value *List, amount u64) Status` | `count` 增加 `amount`，新增槽位不初始化 |
| `trim(value *List, count u64) void` | 把 `count` 截断到指定值；值更大时无操作 |

追加与插入：

| 函数 | 语义 |
| --- | --- |
| `push(value *List, element *void) Status` | 复制一个元素到尾部 |
| `push_all(value *List, elements *void, count u64) Status` | 一次追加 `count` 个元素 |
| `prepend(value *List, element *void) Status` | 在头部插入（等价 `insert(0, element)`） |
| `insert(value *List, index u64, element *void) Status` | 在 `index` 处插入；`index > count` 为 `status_bounds` |

删除与丢弃：

| 函数 | 语义 |
| --- | --- |
| `pop(value *List, out *void) bool` | 取走尾元素；空列表返回 `false` |
| `pop_left(value *List, out *void) bool` | 取走首元素；其余元素前移 |
| `remove_at(value *List, index u64, out *void) bool` | 取走第 `index` 个元素；越界返回 `false` |
| `delete_last(value *List) bool` | 只移除尾元素，不返回内容 |
| `delete_many(value *List, index u64, count u64) bool` | 删除连续区间，后续元素前移 |
| `drop(value *List, count u64) void` | 丢弃前 `count` 个元素，剩余元素前移 |

访问与查询：

| 函数 | 语义 |
| --- | --- |
| `element_at(value *List, index u64) *void` | 第 `index` 个元素地址；越界返回 `0` |
| `first(value *List) *void` / `last(value *List) *void` | 首/尾元素地址；空列表返回 `0` |
| `contains(value *List, key *void, compare) bool` | 是否存在与 `key` 相等的元素 |
| `index(value *List, key *void, compare) i64` | 第一个相等元素下标；没有返回 `-1` |
| `last_index(value *List, key *void, compare) i64` | 最后一个相等元素下标；没有返回 `-1` |
| `any(value *List, predicate) bool` | 是否存在满足谓词的元素；空列表 `false` |
| `all(value *List, predicate) bool` | 是否所有元素都满足谓词；空列表 `true` |
| `count(value *List, predicate) u64` | 满足谓词的元素个数 |

返回新列表（`ListResult`）：

| 函数 | 语义 |
| --- | --- |
| `clone(value *List) ListResult` | 深复制整份内容 |
| `repeat(value *List, count u64) ListResult` | 内容重复 `count` 次 |
| `slice(value *List, start u64, end u64) ListResult` | 复制 `[start, end)`；越界为 `status_bounds` |
| `reverse(value *List) ListResult` | 元素顺序颠倒的副本 |
| `sorted(value *List, compare) ListResult` | 排好序的副本 |
| `filter(value *List, predicate) ListResult` | 只保留谓词为真的元素 |
| `map(value *List, transform, element_size u64) ListResult` | 逐元素变换；`element_size` 是目标宽度 |

原地变换：

| 函数 | 语义 |
| --- | --- |
| `reverse_in_place(value *List) void` | 首尾交换，原地倒序 |
| `sort(value *List, compare) void` | 稳定插入排序，最坏 O(n²) |
| `reset(value *List) void` | 把已用元素的字节清零，保留 `count` |

`out == 0` 表示只丢弃元素；失败时 `count`、`capacity` 与内容都不变。

## 与 V 数组方法对齐

| V 数组操作 | list 对应 | 差异 |
| --- | --- | --- |
| `len` / `cap` | `count` / `capacity` 字段 | 字段而非方法 |
| `arr << x` | `push` | — |
| `arr << arr2` / `push_many` | `push_all` | — |
| `ensure_cap(n)` | `reserve(n)` | — |
| `grow_cap(n)` / `grow_len(n)` | `grow_cap` / `grow_len` | `grow_len` 新增槽位不初始化（与 V 相同） |
| `insert(i, v)` / `prepend(v)` | `insert` / `prepend` | — |
| `delete(i)` / `delete_many(i, n)` / `delete_last()` | `remove_at` / `delete_many` / `delete_last` | `delete` 名字保留为 `remove_at`；越界返回 `false`（V panic） |
| `pop()` / `pop_left()` | `pop` / `pop_left` | 用 `out` 参数 + `bool` 取结果（V 直接返回元素） |
| `first()` / `last()` | `first` / `last` | 空列表返回 `0`（V panic） |
| `clear()` / `reset()` | `clear` / `reset` | — |
| `trim(i)` / `drop(n)` | `trim` / `drop` | `drop` 前移剩余元素（O(n)），V 只前移数据指针；可观察内容相同 |
| `clone()` | `clone` | 返回 `ListResult` |
| `repeat(n)` | `repeat` | 返回 `ListResult` |
| `reverse()` / `reverse_in_place()` | `reverse` / `reverse_in_place` | `reverse` 返回新列表 |
| `contains(v)` / `index(v)` / `last_index(v)` | `contains` / `index` / `last_index` | 收比较回调；未找到返回 `-1` |
| `any(it)` / `all(it)` / `count(it)` | `any` / `all` / `count` | 收谓词回调 |
| `filter(it)` / `map(it)` | `filter` / `map` | 收回调；`map` 需要目标元素宽度 |
| `sort(a < b)` / `sort_with_compare` | `sort` | 只保留比较回调一种形态 |
| `sorted(...)` / `sorted_with_compare` | `sorted` | 同上 |
| `arr[start..end]` | `slice(start, end)` | **返回独立副本**：语言不能从裸指针构造切片视图 |
| `free()` | `release` | — |
| `arr[i]` / `arr[i] = x` | `element_at(i)` + `to_type(*T)` | 语言没有方法/运算符重载 |
| `x in arr` / `arr == arr` | `contains` / 逐个 `compare` | 无运算符重载 |

不提供（附原因）：

| V 方法 | 原因 |
| --- | --- |
| `pointers()` | 需要返回 `[]*void`；语言禁止从裸指针构造切片，等价能力是 `element_at` 循环 |
| `str()`、`[]u8.hex()` | 字符串化归 `string`/`fmt`；无类型容器不知道元素怎么格式化 |
| `wait()` | 标准库还没有线程/并发原语 |
| `clone_to_depth`、`repeat_to_depth` | 字节容器没有元素元数据，无法做深度复制 |

## 硬规则（违反即未定义行为）

1. **步长只能来自 `sizeof(T)`**。任意自定宽度可能在严格对齐目标上产生
   错位访问；本模块不保证 `sizeof(T)` 以外宽度的元素对齐。
2. **元素来源不得指向本列表的存储**。`push`/`push_all`/`insert` 扩容时会
   释放旧块，插入/删除的移位会移动源区域；要复用列表内的元素，先复制到
   局部变量，再从局部变量地址传入。
3. **指针失效**：`reserve`/`grow_cap`/`push`/`push_all`/`prepend`/`insert`/
   `clear`/`release` 之后，此前 `element_at`/`first`/`last` 返回的指针与缓存
   的 `data` 指针全部失效；`pop`/`pop_left`/`remove_at`/`delete_*`/`drop`/
   `reverse_in_place`/`sort` 使被搬动元素之后的指针失效。
4. **不析构**：元素含 `string.String` 句柄等内部资源时，移除/释放前由调用方
   逐个 `string.release` 或 `string.move` 出去，否则泄漏。
5. **越界直读未定义**：`count` 之后的槽位未初始化（`grow_len` 新增的槽位同样
   未初始化）；扩容后继续用旧 `data` 也是未定义行为。
6. **回调必须非空**：语言不支持函数指针与 `0` 比较，传 `0` 会在调用处崩溃；
   `map` 的 `transform` 必须写满 `out` 槽位（写入前内容未初始化）。
7. **`reset` 只适合标量/字节元素**：含指针或句柄的元素清零后语义由调用方
   负责（V 的 `reset` 同样标为 unsafe）。
8. **线程安全**：无；同一列表并发写未定义（不同列表可并行）。

## 与 C 互操作

`data` + `count * element_size` 可直接传给 `io.write_fd`/`memory.copy`/
`libc` 系列。排序已内置（`sort`/`sorted`），需要 C ABI 排序时仍可对
`data` 直接调 `libc.qsort`，此时回调必须带 `@[extern]`：

```yh
import libc

@[extern] fn compare_point(left *void, right *void) int { /* ... */ }

libc.qsort(xs.data.to_type(*void), xs.count, xs.element_size, compare_point)
```

## 测试

语言内用例在 [`list.test.yh`](list.test.yh)：

```sh
cd libs && ../yh test --filter list
just test-libs   # O0 与 O2 两份全库门禁
```
