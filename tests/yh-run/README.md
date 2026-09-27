# tests/yh-run 运行语义测试

对 yh 编译器做「编译 → 运行 → 比对输出/退出码」的端到端语义验收。
与 `tests/yh/`（词法/语法语料校验，见其 `check.py`）互补：那里管"能解析"，
这里管"算得对"。

## 目录

| 目录 | 约定 |
| --- | --- |
| `run/`  | 编译并运行，比对标准输出与退出码 |
| `fail/` | 编译必须失败（首行 `// fail: 预期拒绝的原因`） |
| `pass/` | 编译必须成功，不运行 |
| `work/` | 产物目录（已 gitignore，随时可删） |

## 期望注释格式（run/）

```yh
// expect: 第一行输出
// expect-more: 后续每一行输出
// exit: 42        ← 可选，期望退出码，缺省 0
fn main() int {
    printf("第一行输出\n");
    return 42;
}
```

- 期望行内容在标记首个空格之后原样保留（行内空格/制表符参与比对）。
- 比对对象是 stdout 逐行 + 进程退出码；stderr 不参与。
- 运行崩溃（信号）记 FAIL；编译器崩溃（信号/ICE）同样记 FAIL 并保留诊断。

## 用法

```bash
python3 tests/yh-run/check.py            # 本机 Darwin/Mach-O 全量校验
python3 tests/yh-run/check.py --quiet    # 只打印失败项与汇总
python3 tests/yh-run/check.py --cross    # 交叉编译 Linux ELF，容器内运行对比
```

`--cross` 追加 `-Wl,-oformat=elf64-aarch64 -sysroot tmp/sysroot -B tmp/sysroot`
交叉编译为 aarch64 ELF，经 `docker exec yh-build` 在 Linux 容器（仓库根挂载在
容器 `/work`）内运行并做同样的比对；docker 或 sysroot 不可用时全部打印
SKIP，不算失败。汇总全过（SKIP 允许）退出 0，否则退出 1。

## 当前结果（快照）

记录时间：2026-09-27。编译器 `./yh` 正被主会话持续开发中（M4 数组/切片
落地期间），以下只是当日构建上的快照；复跑以上命令即得最新状态。

```
python3 tests/yh-run/check.py
run:  通过 9/15，失败 6
fail: 通过 6/6
pass: 通过 2/3，失败 1
总计：通过 17/24（Darwin Mach-O）
```

`--cross` 结果与本机一致：通过 17/24，失败集合相同（同一 AArch64 后端，
ELF 在容器内运行输出一致）。

### 通过项

- run/01-hello、02-arithmetic（四则优先级、负数除法/取模向零截断）、
  03-short-circuit（&&/|| 短路副作用计数正确）、04-if-else、
  10-strings（%d/%s/%c、\n \t \\ \" \xNN、strlen）、12-sizeof、
  13-exit-code（`// exit: 42`）、14-many-args（12 参，超出 8 寄存器部分走栈）、
  15-compound-assign（+= -= *= /= %= &= |= ^= <<= >>= 全对）
- fail/ 全部 6 项按预期被拒绝（未声明名、跨型初始化、未知类型、裸变参、
  重复 fn、main 带参）
- pass/01-empty-main、02-pub-fn

### 失败项（编译器待修复，均附最小复现）

| 用例 | 现象 | 归类 |
| --- | --- | --- |
| run/05-loop | `break 不在循环或 switch 内`：裸 `for { break; }`、`for cond { if (...) { break; } }` 均误报 | 待修复：循环上下文跟踪未覆盖裸 for 与 if 块 |
| run/06-switch | `internal compiler error: vstack leak (3)`，编译期 ICE；泄漏数 = case 值个数 | 待修复：switch 代码目标值栈失衡 |
| run/07-goto-label | `label 'loop' used but not defined`，同函数内已有 `loop:` 标签 | 待修复：labelStmt 未登记标签 |
| run/08-recursion | `fact(5)`/`fib(10)` 输出 `0 0`，递归调用返回值丢失（非递归调用正常） | 待修复：递归调用返回值传递 |
| run/09-globals | 编译器 SIGABRT：`arm64-gen.c` store 断言，触发于全局普通赋值 `counter = 20;` | 待修复：普通 `=` 赋值的 store 路径 |
| run/11-pointers | 编译器 SIGABRT：同上，触发于解引用写 `*p = 42;`（读 `*p` 正常） | 待修复：同上 |
| pass/03-void-fn | `internal compiler error: vstack leak (-1)`：void 函数调用作表达式语句（`nothing();`）触发 ICE | 待修复：void 调用语句的值栈处理 |

普通 `=` 赋值问题影响面最广（局部 `x = 5;`、全局赋值、`*p = ...` 全部
SIGABRT）；复合赋值（`+=` 等）与指针解引用读均正常，run/03/05/15 因此得以
绕开 `=` 设计。

### 探测中发现的其他问题（未建用例，待定后补）

- `let r bool = false && bump(&c);` 报"类型不匹配：无法把 'int' 用作
  '_Bool'"——`&&`/`||` 结果当前是 int，无法绑定到 bool（if 条件里可用）。
  属语义边界待定项：逻辑运算结果类型应为 bool 或允许到 bool 的隐式转换。

### 未建用例的语法（编译器尚未支持，等 M4 落地后补）

数组 `[N]T`、切片 `[]T`、for-in、类型化变参、struct/union/enum 构造与
成员访问。语义依据 `docs/03-design/00-语义边界-0.0.1.md`。
