# string

yh 标准库的字节字符串模块。设计见
[`docs/03-design/yh-string标准库设计.md`](../../docs/03-design/yh-string标准库设计.md)，
分期与验收见
[`docs/02-plan/yh-string标准库实施方案-2026-10-23.md`](../../docs/02-plan/yh-string标准库实施方案-2026-10-23.md)。

## 模型

```yh
pub struct View { data *u8; count u64 }   // 借用，不拥有，可含 NUL/非法 UTF-8
pub struct String { handle *void }        // 独占私有存储，零句柄=空串
```

- 所有长度、位置、容量和切片边界单位都是**字节**，不是码点或字素。
- `View.count` 不含额外结尾 NUL；`View` 不保证 UTF-8 合法。
- 已分配 `String` 始终维护 `data[count] == 0`，但内容内允许 NUL。
- `String` 不自动析构；复制内容用 `clone`，转移所有权用 `move`，释放用
  `release`。`release` 允许空指针并对同一变量重复调用安全。
- 所有成功的可变操作和 `release` 都使此前派生的 `View`/C 指针失效；失败
  的可变操作保留内容、长度、容量与既有视图。

## 快速开始

```yh
import string

fn main() int {
    // 借用：不复制，源必须存活且不被改写。
    let view_result string.ViewResult = string.view_cstr("hello")
    let expected string.ViewResult = string.view_cstr("hello")
    if (view_result.status != string.status_ok) { return 1 }
    if (string.view_equal(view_result.value, expected.value)) {
        // ...
    }

    // 构建：零句柄空串，按需增长。
    let text string.String = string.make()
    let part string.ViewResult = string.view_cstr("hé")
    if (part.status != string.status_ok) { return 2 }
    if (string.append(&text, part.value) != string.status_ok) { return 3 }
    if (string.append_rune(&text, 20013) != string.status_ok) { return 4 } // 中

    // 借用结果；下一次成功的可变操作后必须重新获取。
    let built string.View = string.as_view(&text)
    let info string.Utf8Info = string.utf8_validate(built)
    if (info.status != string.status_ok) { return 5 }

    // C 边界：只读借用，内容含 NUL 时拒绝。
    let c_result string.CStrResult = string.c_str(&text)
    if (c_result.status == string.status_ok) {
        // 只交给读取型 C 接口，不要 free 或写入。
    }
    string.release(&text)
    return 0
}
```

## 视图与查找

```yh
let text_result string.ViewResult = string.view_cstr("a,,b,")
let comma_result string.ViewResult = string.view_cstr(",")
let text string.View = text_result.value
let comma string.View = comma_result.value

let found string.IndexResult = string.find(text, comma)
if (found.found) { /* found.index 是字节位置 */ }

let iter string.SplitIter
if (string.split(text, comma, &iter) == string.status_ok) {
    let part string.ViewResult = string.split_next(&iter)
    // "a"、""、"b"、""，最后 status_end
}
```

`find`/`rfind` 的空模式分别匹配位置 `0`/`count`；`slice` 是半开区间
`[start,end)`，不复制也不修复 UTF-8 边界；`trim_ascii` 只裁掉
`0x09–0x0D` 和 `0x20`。

## 拥有者与失败原子性

| 操作 | 契约 |
| --- | --- |
| `from_view` | 独立复制全部字节；空输入可返回零句柄 |
| `clone` | 深复制；失败不改变原值 |
| `move` | 转移句柄并清零源，不分配 |
| `release` | 释放并清零；空指针与重复释放安全 |
| `reserve` | 容量至少为请求值，内容/长度不变；已有容量足够时不分配 |
| `assign`/`append` | 复用容量；支持整体自追加与自身子视图追加 |
| `truncate` | 只缩短，超过原长度报 `status_bounds` |
| `c_str` | 扫描内容，内嵌 NUL 返回 `status_embedded_nul` |

分配失败返回 `status_out_of_memory`，长度溢出返回 `status_overflow`；失败
路径不留下半成品。最大内容长度为 `0x7ffffffffffffffe`，不宣称该大小的内存
可以实际分配。容量按几何增长；连续单字节追加的复制工作摊还线性。

## 变换与 UTF-8

- `concat`/`join` 先算总长再分配；`join` 零片段返回空串，空分隔符允许。
- `replace`/`replace_all` 左到右、非重叠；空 `old` 报参数错误；无匹配时也
  返回独立副本。
- `lower_ascii`/`upper_ascii` 只改变 ASCII 字母，其他字节原样复制。
- `utf8_validate`/`utf8_next` 按 RFC 3629 严格解码：拒绝截断、错误续字节、
  过长编码、代理项和超过 U+10FFFF 的值；U+0000 与 U+FEFF 合法。
- `append_rune` 只接受 Unicode 标量；非法标量不改变目标。
- 只计 Unicode 标量，不承诺字素边界、规范化或 Unicode 大小写折叠。

## 算法与限制

- 查找/切分/替换首版使用直接匹配，最坏 `O(n*m)`（`n` 文本长度，`m` 模式
  长度）；没有 SIMD/KMP 公共接口前置。
- `View` 的地址可读性、悬空指针、伪造长度和外部改写不在库可检测范围内。
- `c_str` 返回的指针只读借用；需要写入的 C 缓冲不在本模块处理。

## 测试

```bash
just test-string       # O0：model/view/owned/transform/utf8/interop/resources
just test-string-o2    # O2 同组
```

`resources` 组把标准库复制到 `tmp/`，逐次改写
`libs/string/base.yh` 的 `STRING_TEST_FAIL_AFTER`，覆盖每个分配点的失败
原子性。基本组同时登记在 `tests/modules/build-check.py` 的 `stdlib-run` 用例中。

## 内建测试

`tests.test.yh` 包含 5 条 `test` 块（视图比较、前后缀与查找、无分配切分、
拥有者增长、UTF-8 校验）。用 `yh test string`（在 `libs/` 目录）或
`just test-lib-tests` 运行；生产构建不会登记或发射这些测试。
