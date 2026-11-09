# libs/list —— yh 动态列表（ArrayList）

`import list;` 提供「连续字节块 + 运行期元素宽度」的动态列表。设计见
[`docs/03-design/yh-list标准库设计.md`](../../docs/03-design/yh-list标准库设计.md)，
分期与验收见
[`docs/02-plan/yh-list标准库实施方案-2026-11-10.md`](../../docs/02-plan/yh-list标准库实施方案-2026-11-10.md)。

## 为什么没有泛型

语言当前无泛型、无接口、无方法接收者，且禁止从裸指针构造 `[]T`。因此本模块
选择与 C `qsort(base, count, width, compare)` 相同的路线：元素宽度由
`element_size` 在运行期给出，元素地址以 `*void` 暴露，取用时
`to_type(*T)` 定型。**`element_size` 必须来自 `sizeof(T)`**。

## 模型

```yh
pub struct List {
    data *u8         // 存储块起始地址；capacity == 0 时为 0
    count u64        // 已用元素个数
    capacity u64     // 可容纳元素个数
    element_size u64 // 单个元素字节宽度，必须来自 sizeof(T)
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

| 函数 | 语义 |
| --- | --- |
| `make(element_size u64) List` | 返回空列表，不分配；`element_size == 0` 得到无效列表 |
| `release(value *List) void` | 释放存储并清零 4 个字段；可重复调用 |
| `clear(value *List) void` | `count = 0`，保留 `data` 与 `capacity` |
| `reserve(value *List, capacity u64) Status` | 保证容量至少为 `capacity`，不改 `count` |
| `element_at(value *List, index u64) *void` | 第 `index` 个元素地址；越界返回 `0` |
| `push(value *List, element *void) Status` | 复制 `element_size` 字节到尾部 |
| `push_all(value *List, elements *void, count u64) Status` | 一次追加 `count` 个元素 |
| `pop(value *List, out *void) bool` | 取走尾元素；空列表返回 `false` |
| `insert(value *List, index u64, element *void) Status` | 在 `index` 处插入；`index > count` 为 `status_bounds` |
| `remove_at(value *List, index u64, out *void) bool` | 取走第 `index` 个元素；越界返回 `false` |

`out == 0` 表示只丢弃元素。失败时 `count`、`capacity` 与内容都不变。

## 硬规则（违反即未定义行为）

1. **步长只能来自 `sizeof(T)`**。任意自定宽度可能在严格对齐目标上产生
   错位访问；本模块不保证 `sizeof(T)` 以外宽度的元素对齐。
2. **元素来源不得指向本列表的存储**。`push`/`push_all`/`insert` 扩容时会
   释放旧块，插入/删除的移位会移动源区域；要复用列表内的元素，先复制到
   局部变量，再从局部变量地址传入。
3. **指针失效**：`reserve`/`push`/`push_all`/`insert`/`clear`/`release`
   之后，此前 `element_at` 返回的指针与缓存的 `data` 指针全部失效；
   `pop`/`remove_at` 只使被移动元素之后的指针失效。
4. **不析构**：元素含 `string.String` 句柄等内部资源时，移除/释放前由调用方
   逐个 `string.release` 或 `string.move` 出去，否则泄漏。
5. **越界直读未定义**：`count` 之后的槽位未初始化；扩容后继续用旧 `data`
   也是未定义行为，语言不做检查。
6. **线程安全**：无；同一列表并发写未定义（不同列表可并行）。

## 与 C 互操作

`data` + `count * element_size` 可直接传给 `io.write_fd`/`memory.copy`/
`libc` 系列。排序不额外包装，直接复用 C ABI 的稳定插入排序：

```yh
import libc

@[extern] fn compare_point(left *void, right *void) int { /* ... */ }

libc.qsort(xs.data.to_type(*void), xs.count, xs.element_size, compare_point)
```

回调实参必须带 `@[extern]`（C ABI 函数），签名是 `fn(*void, *void) int`。

## 测试

语言内用例在 [`list.test.yh`](list.test.yh)：

```sh
cd libs && ../yh test --filter list
just test-libs   # O0 与 O2 两份全库门禁
```
