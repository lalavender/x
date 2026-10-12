# yh_asm 汇编器稳定化实施方案（不接入编译器）

日期：2026-10-12。状态：**实施完成（ASM-0–ASM-8）**——汇编器已稳定到
「可顶替编译器逐模块汇编步」，但**本轮不接入编译器**；接入单列为第 6 节，
待稳定判据 S1–S7 全过后另立。逐项证据见
[完成记录](../01-finished/yh-asm稳定化-2026-10-12.md)。

## 0. 实施结果（2026-10-12 收尾）

| 判据 | 结果 |
| --- | --- |
| S1 默认门 | `python3 tests/check.py` 冷编 + 五层自检 rc=0；`tests/check_neg.py` 10/10 |
| S2 收录式差分 | 编译器 8 模块（8.98 MB）**原文**汇编成功、与 clang 逐节内容 + 逐重定位 **0 不一致 0 跳过**；定向 + GNU 方言语料 10/10 |
| S3 链接运行差分 | `tests/elf_link_native.py`：169 程序语料 **159 一致 / 0 不一致 / 10 跳过**（8 个模块缺入口、2 个寄存器同名两边都拒绝） |
| S4 影子验收 | `tests/shadow-build.py`：16 次汇编调用、两代固定点 **0 不一致**（57.3 s / 52.0 s） |
| S5 稳健性 | 退出码 0/1/2、确定性 0 非确定、LF/CRLF 同字节、交叉目标可写对象；性能基线已记录（见下） |
| S6 Mach-O 不回退 | `tests/darwin-snapshot.txt` 9 个文件字节快照 0 不一致（macOS 原生两门本轮无环境可跑） |
| S7 边界明确 | 契约升 v2、`asm/README.md` 重写用法/退出码/测试/已知边界 |

**实施中的修正与偏差**（都是先实测、再改文档或实现）：

- `uxtw` 补进契约白名单（盘点实测 95 次）；`x31`/`w31` 与 `.text` 里的 `.zero`
  改为**不拒绝**（前者 clang 同样接受，后者按 §4 的填充规则），`.size` 收窄为
  「只接受纯数字」——三条都是 v1 文档与实际不符，按实测改文档。
- 运行时桩写在新的 `tests/elf/yhr-linux.s`（Linux/GNU 方言，供原生门），
  没有改动容器门那份 Darwin 方言的 `tests/elf/yhr.s`。
- 写对象失败时**不删**已写出的半成品：`O_TRUNC` + 非 0 退出码已足够表达
  「产物不可用」，删文件反而可能删掉用户原有的同名文件。
- 性能**不做热路径优化**：WSL 上 yh_asm 是 aarch64 ELF 走 qemu-user，
  自建基准实测模拟因子 2.2–3.0×，同批语料 41.18 s vs clang 5.52 s
  （折算原生 arm64 约 2.5–3.5×）；接入决策前需要原生 arm64 的实测数据。
- macOS 原生 macho 两门本轮未跑（环境只有 Linux），只由字节快照守住不回退。

上位文档：[yh-asm 与 yh-link 设计](../03-design/yh-asm与yh-link设计.md)、
[首版汇编子集契约](../03-design/yh-link独立项目与首版汇编子集契约.md)、
[yh-asm 与 yh-link 分期实施方案](yh-asm与yh-link实施方案.md)（TC0–TC10 总纲，
本文是其中"TC2/TC3/TC8 稳定化"的执行细化）。
工具项目：[asm/README.md](../../asm/README.md)（yh_asm，汇编器）、
[link/README.md](../../link/README.md)（yh_link，链接器，不在本轮范围）。

## 1. 目标与成功标准

**目标**：把 `asm/`（yh_asm）在 **Linux/ELF** 上做到"可顶替编译器逐模块汇编步"
的稳定度。范围只含 `asm/` 与其门禁、契约与文档：**不改 `compiler/**`**。

**成功标准（稳定判据，接入的前置门）**

| 编号 | 判据 | 证据形态 |
| --- | --- | --- |
| S1 | 默认门全绿：冷编 `asm/` + 内建三层自检 + 对象结构/确定性 + 新增拒绝层 | `python3 asm/tests/check.py` 退出 0 |
| S2 | 收录式差分：编译器全部模块 `.s` 与全部单文件语料 `.s` **原文不改写**即可汇编，与 oracle 对象逐节内容 + 重定位三元组全一致，0 跳过 0 例外 | `--full` 门输出 |
| S3 | 链接运行差分：ELF 侧 GNU ld 链成静态可执行、qemu 跑，退出码/stdout 与 clang 对象链出的参照一致 | 原生链接门输出 |
| S4 | 影子验收：显式 `YH_LINK=asm/.build/yh_asm` 冷编出的编译器跑通两代固定点与语料门，汇编调用 0 失败 | 影子报告 |
| S5 | 稳健性：同输入逐字节确定、LF/CRLF 一致、边界输入有诊断、性能与内存基线实测并记录 | 门输出 + 基线表 |
| S6 | Mach-O 不回退：`-t darwin` 输出字节快照不变（macOS 原门有条件时补跑） | 快照门 +（可选）macOS 门 |
| S7 | 边界明确：契约/README 列明支持与拒绝清单，CLI 与退出码冻结（0 成功 / 1 输入错误 / 2 用法错误） | 文档 + 用例 |

## 2. 已核实的事实基线（2026-10-12 在 WSL/Linux 实测）

1. **编译器 8 个模块的 `.s`（8.6 MB，Linux/GNU 方言）当前一条都汇编不了**：
   首条 `adrp x0, sym` 报「adrp 需要 sym@PAGE，adr 需要符号或数字」
   （`asm-asm.s:334`）；只给该行补 `@PAGE` 后，紧接着
   `add x0, x0, :lo12:sym` 报「加减的第三个操作数只能是寄存器、立即数或
   sym@PAGEOFF」（`:335`）。这是**输入方言不接受**，不是覆盖率问题。
2. **能力面够用**：把文本按 GNU→Darwin 等价改写（`adrp sym`→`sym@PAGE`、
   `:lo12:sym`→`sym@PAGEOFF`）后 **8/8 模块全部汇编成功**；最大模块与 clang
   对象**逐节一致**（`.text` 194,964 B 相同、`.data` 6,800 B 相同、
   4,516 条重定位三元组完全一致）。
3. **性能**：1 MB / 19.5 万行级模块 yh_asm **4.07 s** vs clang **0.65 s**；
   编译器 8 模块合计 **~47.8 s** vs clang ~5 s（约 10×）。
4. **退出码**：输入错误当前退出 **255**（`asm_parse` 的 -1 直接当退出码），
   用法错误 2 → 需归一为 0/1/2。
5. **门禁现状**：内建自检（编码 134 + 公共层 36 + 端到端 25）与
   `check_obj.py`（9 对象结构 + 确定性）在 WSL 全绿；`check_enc.py` 支持
   `LLVM_MC` 覆盖但默认写死 macOS 路径，`check_corpus.py` 路径**写死**
   llvm-mc，`elf_link_check.py` 依赖 docker。
6. **WSL 环境**：clang 21（集成汇编器可当 oracle）、
   `aarch64-linux-gnu-{ld,objdump}`、`qemu-aarch64` + binfmt（aarch64 ELF
   可直接执行）、`rg`、`python3.14`；**没有** llvm-mc/llvm-objdump/docker；
   `sudo` 需交互密码。
7. **语料空**：`tmp/inv` 已空（上次冻结是 2026-10-07 的 61 个单文件）；
   现在 `tests/yh-run/run` 153 + `pass` 8，编译器自身 8 个模块 → 语料须重建。
8. **归档负例已丢**：`tmp/removed-2026-10-07/asm-legacy/` 不存在（`tmp/`
   不入库），19 条指令级负例只能**按契约 §8 重写**，不能"迁移"。
9. **运行时桩缺**：`asm/tests/elf/yhr.s` 只有 `_write/_mmap/_munmap`；
   `__Exit/_strtoul/_open/_close/_abs` 缺失导致容器门 7 个语料被跳过。
10. **CRLF 已可处理**：同一 `.s` 的 LF 与 CRLF 版本产出对象字节一致
    （`cmp` rc=0）→ 落成用例即可。
11. **现役链路（本次断电对象）**：根目录 `yh_asm`/`yh_link` 是**入库的同一份
    Mach-O 副本**（sha256 同为 `3675076a…`）；`compiler/cmd/link_cache.yh` 的
    `mb_asm_tool` 按 `YH_LINK` → `PATH` → 编译器同目录找 `yh_link`，命中即以
    `<tool> asm [-t darwin] -o obj src` 调用。`tests/selfhost/link-cache.py`
    对 `yh_link` 是**可选探测**，不存在不影响该门。
12. **代码位点**：`asm/src/asm/52_parse_ins.yh`（adrp 只收 `@PAGE/@GOTPAGE`）、
    `asm/src/asm/51_parse_alu.yh`（add/sub 只收 `EX_PAGEOFF`）、
    `asm/src/asm/40_parse.yh`（`:lo12:` 已能扫成 `MOD_LO12`）。
13. **工作区**：`core.autocrlf=true`，工作区有与本方案无关的在途改动
    （含 `compiler/**`）→ 本方案只动自己范围内的文件，保持 LF。

## 3. 边界："不接入"具体指什么

- **不改** `compiler/**`：`mb_asm_tool` 保持按 `yh_link` 查找，查找分支本轮不动。
- **断电**：删 `Makefile` 的 `yh-link` 过渡目标（含 `YH_LINK` 变量、注释、
  `.PHONY`、help 行），`git rm` 根目录入库的 `yh_asm`/`yh_link` 副本，
  `.gitignore` 收住这两个名字；`make yh-asm` 保留（产物仍在根目录，但编译器
  不再按该名字发现它）。副作用：Linux/WSL 上不再需要 `YH_LINK=/nonexistent`
  绕过；macOS 上汇编步回落 `clang`（`make test`/`make selfhost-native` 必须
  仍全绿）。
- **端到端证明只走影子验收**：显式 `YH_LINK=<asm/.build/yh_asm>`，只由
  `asm/tests/shadow-build.py` 触发，不进 `make`、不进默认门。
- **本轮不做接入**：查找名切换（`yh_link`→`yh_asm`/`YH_ASM`）、默认目标切换、
  安装布局、缓存键版本化（见第 6 节）。

## 4. 工作包

### ASM-0 断电与基线冻结

- 改动：`Makefile`（删 `yh-link` 目标与相关注释/变量/`.PHONY`/help）、
  `.gitignore`（`/yh_asm`、`/yh_link`）、`git rm yh_asm yh_link`、
  `asm/README.md`（"与编译器的对接"改写为"当前不接入 + 显式用法"）、
  `docs/todo.md`（"编译器汇编步查找名切换"改写为"接入：未开工"，注明断电）。
- 验收：WSL 下 `SEED=bin/yh-linux-arm64 make test` 与 `make selfhost-native`
  全绿（断电改变汇编步，必须先确认无回归）；`make yh-asm` 仍产出根 `yh_asm`；
  根 `yh_link` 不再出现在 `git status`；`tests/selfhost/link-cache.py` 仍按
  gcc/clang 计数通过。

### ASM-1 ELF/GNU 方言接受（阻塞项）

- 契约 v2：`-t linux` 接受编译器 GNU 方言
  1. `adrp Xd, sym`（裸符号）→ `R_AARCH64_ADR_PREL_PG_HI21`(275)；
  2. `add Xd, Xn, :lo12:sym` → `R_AARCH64_ADD_ABS_LO12_NC`(277)；
  3. `ldr/str … [Xn, :lo12:sym]` → 278/284/285/286（`EX_LO12` 已支持，
     复核 add 与访存两条路径判定一致）。
- 位点：`52_parse_ins.yh`（adrp 表达式分派接受裸符号/`:lo12:` 并归一为页取址，
  错误文案改"adrp 需要符号、sym@PAGE 或 :pg_hi21:"）、`51_parse_alu.yh`
  （add/sub 第三操作数接受 `EX_LO12`）；Darwin 分支按 `ts_darwin()` 隔离，
  `@PAGE/@PAGEOFF/@GOT*` 行为不变。
- 明确不做：`adrp Xd, :got:sym` / `:got_lo12:`（实测编译器语料 0 条 GOT），
  遇到仍报"未支持"并写进契约"不做"清单。
- 用例：`70_selftest.yh` 增 GNU 形态编码/端到端向量（期望机器字 + 重定位类型
  号）；`asm/tests/asm/10-gnu-dialect.s` 定向语料；拒绝用例：
  `adrp x0, :lo12:sym`、`adrp x0, 123`、`add x0, x0, sym`（裸符号仍拒绝）、
  `b sym@PAGEOFF`。
- 验收：编译器 8 模块 `.s` **原文**全部汇编成功，且与 clang 对象逐节内容 +
  重定位一致。

### ASM-2 语料重建与盘点（TC0 落地）

- 新增 `tools/yh-toolchain-inventory.py`：`--compiler ./yh --output tmp/inv`
  - 单文件语料：`yh --emit-asm` 跑 `tests/yh/**`、`tests/yh-run/run/*`、
    `tests/yh-run/pass/*` → `tmp/inv/<name>.s`；失败记 `tmp/inv/skipped.txt`，
    **不得静默丢**；
  - 模块语料：`yh build` 编译器项目与 `tests/modules/projects/*` →
    `.build/asm/*.s` 收成 `tmp/inv/mod-<name>.s`；
  - 产出 `tmp/inv/inventory.md`：助记符/伪指令/操作数形态/重定位类别直方图 +
    与契约白名单的差异表；头部记编译器哈希与版本，排序稳定保证可重复。
- 验收：两次运行 inventory 逐字节相同（除哈希）；"未支持集合"为空或每条都能
  指到契约条目。

### ASM-3 oracle 可移植

- `check_corpus.py`/`check_enc.py`/`elf_link_check.py`：`LLVM_MC` 改为
  "环境变量 → 平台默认 → clang 回退"；无 llvm-mc 时用
  `clang -c --target=aarch64-linux-gnu` 作 oracle（`check_enc` 改为顺序比对
  `.text` 前 N 个字）；把**实际使用的 oracle**打进输出便于追溯。
- `elf_link_check.py`：docker 不在时明确跳过并打印原因（不算通过），或改走
  ASM-4 的原生门。
- `check.py --full`：按宿主自动选门（Linux 不跑需要 macOS `ld`/`clang` 的门）。
- 验收：WSL 上 `python3 asm/tests/check.py --full ../tmp/inv` 0 不一致、
  0 未解释跳过。

### ASM-4 原生 ELF 链接运行差分门 + 运行时桩

- 新增 `asm/tests/elf_link_native.py`（宿主为 Linux）：
  `aarch64-linux-gnu-ld -static -nostdlib -e _start` 把本工具对象 +
  `tests/elf/{start,yhr}.s` 链成可执行，qemu（或 binfmt 直跑）执行，与 clang
  对象链出的参照比退出码 + stdout；差分语义（两边同样链不上/同样崩 → 计入
  跳过并报名字）。
- 补 `asm/tests/elf/yhr.s` 桩：`__Exit`、`_open`、`_close`、`_strtoul`、
  `_abs`（以实测未定义符号清单为准），把现有 7 个跳过变成真跑。
- 验收：语料全量"一致 N / 不一致 0 / 跳过 0 或有名字与原因"。

### ASM-5 指令级负例门

- `70_selftest.yh` 增第 4 层"拒绝层"（in-process，含源码文本 + 期望错误关键字
  + `path:line:col`），覆盖契约 §8 全表：未知助记符、未知伪指令、非法寄存器
  写法、越界立即数（movz/movk/add/sub/and 各一）、位移未对齐、位宽错配
  （`mov x0, w1`、`ldr x0, [x1, #1]`）、SP/ZR 混用、分支位移越界、`:lo12:`
  用在非 add/非访存、`.zero` 出现在 `.text`、多符号表达式、跨节符号差、
  `.balign` 非 2 的幂、`.p2align` 过大、未定义局部标签、`.type` 不支持值、
  GOT 窄访问。
- 每条要求：退出码非 0 + 诊断含位置 + 关键字匹配；**配正向对照**（同文本改对
  后必须成功），防止"全部拒绝"式假通过。
- 需要多语句的场景放 `asm/tests/asm-neg/*.s` + `asm/tests/check_neg.py`
  （不引入新依赖）。
- 验收：拒绝层条数与契约 §8 条目对齐，少一条视为契约缺项。

### ASM-6 CLI 契约、距离边界、确定性与性能

- CLI：`yh_asm asm [-t linux|darwin] -o out.o in.s`；退出码 0/1/2；`-o` 缺失或
  未知 `-t` → 2；写对象失败时 `unlink` 半成品（`main.yh` 的 `write_all`
  失败路径）。
- 距离：`cbz/cbnz/b.cond`（±1 MB）与 `b/bl`（±128 MB）越界必须报错带位置
  （实测编译器最大 `.text` ≈ 195 KB，无风险）；**不做**长分支单调放宽，作为
  已知边界写进 README/契约。
- 确定性/稳健：同输入两次字节一致（扩到大模块）、LF/CRLF 一致、UTF-8 注释、
  空文件/只注释/无尾换行/超长行/重复标签/跨节同名符号。
- 性能：先做分段计时（扫描/解析/回填/写出）再定预算，目标"编译器 8 模块总
  汇编 ≤ 3× clang"（当前 ~10×），只做低风险优化（token 数组与名称池的重复
  增长、字符串比较）；不达标就如实记录并交给接入决策；同时记录峰值内存。

### ASM-7 影子验收

- 新增 `asm/tests/shadow-build.py`：在 `tmp/shadow/<session>/` 内
  1. 用 `YH_LINK=<abs 路径 asm/.build/yh_asm>` + `tools/seed-build.py` 冷编
     `compiler/`；
  2. 影子编译器跑 `tests/yh/check.py --compiler`、
     `tests/yh-run/check.py --compiler`；
  3. 两代固定点（`.s`/`.s.i` 逐字节）；
  4. 报告汇编调用次数、耗时对比、失败数（必须 0）。
- 这是本轮唯一会用到"编译器找工具"链路的入口，且只由显式环境变量驱动、
  不进默认门。

### ASM-8 Mach-O 不回退守门

- 新增 `check_obj.py --target darwin --snapshot`：对 `tests/asm` 语料 + 合成
  样例记录 `-t darwin` 对象字节快照（sha256），可在 Linux 跑，挡住 ASM-1 类
  改动误伤 Darwin 输出；快照变更必须显式说明。
- macOS 原两门（`macho_corpus_check.py`、`macho_link_run.py`）有条件时补跑，
  跑不了就明确写"未在本轮验证"。

### ASM-9 文档与流程

- 本文（`docs/02-plan/yh-asm汇编器稳定化实施方案.md`）。
- 更新 [契约](../03-design/yh-link独立项目与首版汇编子集契约.md) → v2：
  §3/§5 增补 GNU 方言接受规则、§8 拒绝清单按实测补齐、状态行改
  "稳定化中（未接入编译器）"。
- 更新 `asm/README.md`（能力、已知边界、测试命令、断电与影子验收、退出码）。
- 更新 `docs/todo.md`（汇编器条目重排为 ASM-0…ASM-7，"接入"单列未开工）；
  完成后写 `docs/finish.md` 与 `docs/01-finished/`。

## 5. 顺序、估算与风险

顺序：ASM-0 → ASM-1（阻塞）→ ASM-2 → ASM-3 → ASM-4 → ASM-5 → ASM-6 →
ASM-7 → ASM-8/ASM-9 交叉。每个切片先加用例再改实现，改完跑默认门。

估算：ASM-0 0.5｜ASM-1 1.5｜ASM-2 1｜ASM-3 0.5–1｜ASM-4 1–1.5｜ASM-5 1｜
ASM-6 1–2｜ASM-7 0.5–1｜ASM-8 0.5｜ASM-9 0.5 ≈ **8–11.5 人日**（性能优化不设
上限，只定预算）。

风险：

- **R1 方言改动误伤 Darwin** → 分支隔离（`ts_darwin()` 分派）+ ASM-8 快照门。
- **R2 clang 回退与 llvm-mc 有细微差异** → 只比契约内的 4 个节 + 重定位，
  额外节（如 `.note.GNU-stack`）不参与判定。
- **R3 性能不达标** → 如实报告，交给接入决策权衡（冷编时间）。
- **R4 断电改变 macOS 汇编步** → ASM-0 先跑全门确认无回归。
- **R5 工作区在途改动多** → 只动本方案范围文件，不混提。

## 6. 接入（本轮不做，S1–S7 通过后另立）

- **I1** `mb_asm_tool` 查找名切到 `yh_asm`/`YH_ASM`（argv 契约不变：
  `asm [-t darwin] -o out.o in.s`）。
- **I2** 恢复编译器可见的产物命名与安装布局（`make install` 一并安装）。
- **I3** 缓存键纳入工具身份与版本（现有键已含命令前缀，补版本）。
- **I4** 按 Linux → macOS 顺序切默认 + 全门 + 滚种子。
- **I5** 清理过渡说明与 `tests/selfhost/link-cache.py` 注释。

## 7. 环境需求

- **建议安装**：`sudo apt-get install -y llvm-21`（提供
  `/usr/lib/llvm-21/bin/llvm-mc`、`llvm-objdump`、`llvm-readobj`）。装上即用
  它作主 oracle，并在文档里同时留"llvm-mc + clang 两条 oracle 都绿"的证据；
  不装也能跑（clang 21 集成汇编器回退，功能等价，交叉验证弱一点）。
- **不需要 docker**：原生门用 WSL 已有的 `aarch64-linux-gnu-ld`/`objdump` +
  `qemu-aarch64`（binfmt 已注册）。
- **已有**：`python3.14`、`rg`、`clang`/`gcc`/`aarch64-linux-gnu-gcc`、`make`。
- macOS 侧完整 Mach-O 门沿用宿主的 `llvm-mc`
  （`/opt/homebrew/opt/llvm/bin/llvm-mc`）与 `ld`。

## 8. 验收命令（WSL）

```bash
cd /mnt/c/Users/16904/Desktop/x
export SEED=bin/yh-linux-arm64
make && make test && make selfhost-native          # ASM-0 断电后主门
cd asm && ../yh build && ./.build/yh_asm && python3 tests/check.py
cd .. && python3 tools/yh-toolchain-inventory.py --compiler ./yh --output tmp/inv
cd asm && python3 tests/check.py --full ../tmp/inv
python3 tests/check_obj.py ./.build/yh_asm ../tmp/inv
python3 tests/elf_link_native.py ../tmp/inv
python3 tests/check_neg.py
python3 tests/shadow-build.py --compiler ../yh --project ../compiler --out ../tmp/shadow
```

## 9. 假设

- 开发与验证都在 WSL（Ubuntu x86_64 + qemu binfmt），Windows 侧不直接构建。
- Linux/ELF 优先（2026-10-12 决定），Mach-O 本轮只做"不回退"守门。
- 汇编器不改 yh 语法、不新增语言特性；`asm/` 测试沿用"`.s` 语料 + Python 门 +
  内建自检"三类。
- 文件规模 500–1000 行、中文注释、临时产物进 `tmp/`；计划落 `docs/02-plan/`、
  完成落 `docs/finish.md` 与 `docs/01-finished/`。
- 影子验收若暴露编译器自身缺陷（如已知的 SSA 混合宽度算术），只在
  `docs/todo.md` 记录，不在本轮修。
