# 生成程序性能语料（产物质量）

`bench-*.yh` 是编译产物的运行基准：每个程序在**运行期**接受一个规模参数，跑完输出
一行 `checksum=<值>`，并自带内部自检（排序有序性、切片与下标一致、哈希 32 位截断等）。
期望值由 `tools/perf-product.py` 里的 Python 参照实现独立算出，不靠"跑一次记下来"。

用途：在 O0/O2 两档下比较 yh 生成程序的运行时间与代码体积（`.text`、只读数据、文件
大小）。编译器自身的编译耗时口径随统计机制（2026-11-10 删除）一并移除。
`docs/02-plan/yh-编译器性能测试方案-2026-10-23.md`。

## 用例与缺省输入

| 用例 | 覆盖点 | 缺省输入 | 期望 checksum |
| --- | --- | --- | --- |
| `bench-loop-sum.yh` | 整数循环：乘法 + 取模 + 累加 | 50000000 | 51634071 |
| `bench-array-scan.yh` | 数组扫描：1024 槽累加与求最大 | 20000 轮 | 140959930 |
| `bench-sort-insertion.yh` | 排序：512 槽插入排序 | 1800 轮 | 759005353 |
| `bench-hash-fnv.yh` | 哈希：FNV-1a 32 位 over LCG 字节流 | 36000000 字节 | 331382977 |
| `bench-struct-slice.yh` | 结构体 + 切片：Vec3 视图传参与 for-in | 16000 轮 | 9354506 |
| `bench-call.yh` | 函数调用：递归 `fib(n)` | 39 | 63245986 |

缺省输入对应本机（Darwin/arm64）约 0.15–0.5 s 单次运行；每个用例在**缺省输入**下会
自校验上表的期望 checksum（不一致直接 `return 5`），换成其他输入时跳过该断言。改输入
时用 `tools/perf-product.py` 的参照实现重算期望值，不要手改表里的常量。

## 语言约束备忘

- `int` 是 **32 位**；累加器、随机种子和 64 位哈希一律显式 `i64`/`u64`，否则会
  溢出成负数（本目录的开发过程中真踩过）。
- 同宽整数之间必须 `.to_type`；窄化只能显式写，隐式窄化会被编译器拒绝。
- 结构体数组不能直接切片，要先 `arr.to_type([]T)` 取视图，再对视图做区间切片也不
  保证支持——自检里避免了对结构体切片再切片。

## 运行

```bash
# 全量：O0/O2 各编译一次，每档 5 轮，写入 tmp/perf/<run-id>/
python3 tools/perf-product.py --outdir tmp/perf/<run-id> --runs 5

# 单个用例手动核对
./yh tests/perf/bench-sort-insertion.yh -O2 -o tmp/bench-sort
./tmp/bench-sort 1800     # 应输出 checksum=759005353
```
