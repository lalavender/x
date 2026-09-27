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

产物目录缺省为仓库 `tmp/yh-run-work/`（gitignore，随时可删）；并发运行
多套校验时用 `--workdir` 各自指定，避免多进程同时读写同一批产物
（Mach-O 链接流程含 rename 暂存步骤，并发共用目录会互相踩踏）。

## 期望注释格式（run/）

```yh
// expect: 第一行输出
// expect-more: 后续每一行输出
// exit: 42        ← 可选，期望退出码，缺省 0
// stdin-hex: 6869 ← 可选，十六进制注入进程标准输入（可含 NUL）
// argv: a b c     ← 可选，附加命令行参数（空格分隔）
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
python3 tests/yh-run/check.py --compiler ./stage1 --workdir tmp/w1
                                         # 指定编译器与产物目录（自举差分）
```

`--cross` 追加 `-Wl,-oformat=elf64-aarch64 -sysroot tmp/sysroot -B tmp/sysroot`
交叉编译为 aarch64 ELF，经 `docker exec yh-build` 在 Linux 容器（仓库根挂载在
容器 `/work`）内运行并做同样的比对；docker 或 sysroot 不可用时全部打印
SKIP，不算失败。汇总全过（SKIP 允许）退出 0，否则退出 1。

## 当前结果（快照）

记录时间：2026-09-28（0.0.2 B2 完成）。以下为当日构建 `./yh` 的结果；
复跑以上命令即得最新状态。

```
python3 tests/yh-run/check.py            → 总计：通过 44/44（Darwin Mach-O）
python3 tests/yh-run/check.py --cross    → 总计：通过 44/44（交叉 ELF）
```

早期快照中记录的 run/05/06/07/08/09/11、pass/03 失败（普通 `=` 赋值
SIGABRT、switch/goto/递归返回值问题等）已在 0.0.1 的 M4/M5 阶段修复。
历史上一次 22/24（07-goto-label「无法暂存目标文件」、08-recursion
信号 9）经 B0 复盘定性为**并发运行共享产物目录导致的 rename 竞态**与
一次未复现的环境性 kill：单进程 150 次压力与交叉路径均全绿；产物目录
按 `--workdir` 隔离后并发 4 实例亦全绿。

B2 补齐了 struct/union/enum、数组按值、切片、for-in、类型化变参、
函数指针、浮点、位移、read/close、main(argc,argv) 与容量边界的运行
覆盖（run/16-29、fail/07-12），并修复了期间发现的编译器缺陷
（清单见 `docs/02-plan/yh-运行覆盖缺口矩阵.md` §4）。

### 未建用例的语法（运行覆盖缺口）

无——缺口矩阵 G01-G17 已全部补齐（同目录 `docs/02-plan/
yh-运行覆盖缺口矩阵.md`）。
