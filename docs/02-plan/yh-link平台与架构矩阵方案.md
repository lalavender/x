# yh-link 平台与架构矩阵方案（Linux/macOS × arm64/x64）

日期：2026-10-03。状态：**规划**。Linux/aarch64 一格已经打通到「链接并运行」，
其余三格的顺序、门槛与依赖如下。

上位文档：[yh-asm 与 yh-link 分期实施方案](yh-asm与yh-link实施方案.md)、
[yh-link 独立项目与首版汇编子集契约](../03-design/yh-link独立项目与首版汇编子集契约.md)。
实施记录：[link/README.md](../../link/README.md)。

## 1. 目标矩阵

| | **arm64** | **x64** |
| --- | --- | --- |
| **Linux / ELF** | 汇编器已完成（61/61 语料逐字节一致）；**自有静态链接器 P1-3 已完成（2026-10-13）** | 待做，先有编译器后端 |
| **macOS / Mach-O** | 待做（对象出口 + 本机装载） | 待做 |

「已完成」对汇编器指：`yh_asm` 产出的 AArch64 ELF 对象与 `llvm-mc` 参照
**逐字节一致**（含重定位全量比对），且在容器里用 GNU `ld` 链成静态可执行后
**运行行为与参照对象完全一致**；对链接器指：`yh_link` 能把这些对象链成静态
`ET_EXEC` 并真跑，行为与 `GNU ld` 一致（见 §4 的 P1-3 结论）。

## 2. 事实基线（实测，不是推测）

**宿主**：Darwin arm64。colima（docker 29.2.1，引擎 linux/aarch64）。

**容器能力**

| 能力 | 结论 |
| --- | --- |
| `docker run --platform linux/arm64` | 原生，无需模拟 |
| `docker run --platform linux/amd64` | 可用，走 binfmt 模拟（实测 `uname -m` = x86_64） |
| `docker build --platform linux/amd64` | **不可靠**：colima 单架构 builder 会静默按宿主架构出镜像，测出来的镜像其实是 arm64 |
| 容器内 `aarch64-linux-gnu-ld` | 可用（Debian bookworm binutils 2.40） |
| 容器内 `x86_64-linux-gnu-ld` + `qemu-x86_64-static` | 可用（qemu-user 7.2） |

镜像：`asm/tests/docker/Dockerfile`，`debian:bookworm-slim` +
`binutils-aarch64-linux-gnu` + `binutils-x86-64-linux-gnu` + `qemu-user-static`。
构建 `docker build -t yh-link-elf:latest asm/tests/docker`。

> 路径说明（2026-10-07 目录整理）：本方案写于 2026-10-03，当时 `link/` 里寄放着
> 汇编器实现与它的门；整理后汇编器整体迁到 `asm/`，因此下文里
> `link/tests/<文件>` 一律指现在的 `asm/tests/<文件>`
> （汇编器对象/链接门），而 `link/tests/` 现在只放**链接器自己的**门
> （`check.py` / `link_accept.py` / `link_diff_regress.py` / `asm/*.s` 语料）。

**注意**：要挂载进容器的目录必须落在工作区内。colima 不共享宿主的
`/tmp` 这类私有路径，`/tmp` 下的文件容器里看不到。门统一用仓库内的
`tmp/linkbox/`。

**宿主的 Mach-O 工具链是齐的**（`ld64`、`otool`、`nm` 随 Xcode 提供），
所以 macOS 那一格**不需要容器**，用宿主的 Apple 链接器验收更直接。

## 3. 容器门（已落地）

`asm/tests/elf_link_check.py`，镜像 `yh-link-elf:latest`：

1. 宿主上 `yh_asm` 汇编语料，同时用 `llvm-mc` 汇编一份参照；
2. 容器里对两边都跑 `ld -r`（结构合法）与 `ld -static -nostdlib`（重定位可解）；
3. 链出来的可执行都真跑一遍，比对退出码与标准输出；
4. 判定是差分的：两边行为一致即通过。

当前结果：**44/44 行为一致**。另有 2 个语料在容器里段错误——两个参照对象
崩得一模一样，原因是本仓库的 `_mmap` 运行时桩不全，不是汇编器问题；
差分门天然容忍这种已知偏差。

链接需要一个 `_start` 与 yh 运行时的三个 OS 原语桩，放在
`asm/tests/elf/{start.s,yhr.s}`。桩不全只会让某些语料崩，不会让门误判——
因为参照对象用的是同一套桩。

> **这个门验的是"我们的对象能被 GNU `ld` 正确链接"，不验"我们的链接器"。**
> 自有链接器（P1-3）的门在 `link/tests/`，见 §4 的 P1-3 结论。

## 4. 阶段划分

每格的门都写死「什么算通过」，避免做完才发现不可验收。

### P1 — Linux/arm64 收尾（唯一在推进的一格）

| 任务 | 内容 | 门 |
| --- | --- | --- |
| P1-1 | 浮点标量编码 | **已完成**：`check_corpus` 61/61、跳过 0、不一致 0 |
| P1-2 | GOT 重定位 `@GOTPAGE`/`@GOTPAGEOFF` | **已完成**：同上，类型号 311/312 |
| P1-3 | 自有静态链接器（TC4） | **已完成（2026-10-13）**：见下方结论 |
| P1-4 | Linux 宿主连编自举（TC6） | `yh_link` 汇编 `yh_link` 自己的输出，两代固定点字节相同 |

**P1-3 完成结论（2026-10-13）**：`link/` 已能把 `ELF64 ET_REL`（AArch64）
链成静态 `ET_EXEC` 并真跑。门的实际形态比原计划更强——原计划只要求"行为与
GNU `ld` 一致"，实际交付了三层门：

1. 自检 57 项（含读取层拒绝路径与多对象合并回归）；
2. 端到端 7 用例：结构断言 + **真跑比对退出码** + 两次链接逐字节相同；
3. **与 GNU `ld` 的差分 7/7**：退出码相同、同为静态 `ET_EXEC`、且
   **同一输出节内符号间距相同**（与布局无关的不变量，比"行为一致"更能定位
   偏移类错误）。

设计见 [yh-link 静态 ELF 链接器设计](../03-design/yh-link静态ELF链接器设计.md)，
任务分解与验证记录见
[实施方案](../02-plan/yh-link静态ELF链接器实施方案.md)。

两点边界必须记住：

- **产物刻意不放到仓库根 `yh_link`**：编译器当前按这个名字发现**汇编器**
  （`compiler/cmd/link_cache.yh` 的 `mb_asm_tool` 会调用
  `yh_link asm -t ... -o ...`）。集成（P1-4 的前置）第一步是把查找名改成
  `yh_asm`，否则现有 `make` 会直接坏掉。
- **本机验证是 qemu 模拟**：本机为 Windows + WSL（Ubuntu x86_64），无 AArch64
  硬件。把"模拟通过"提升为"真机通过"需要在 arm64 容器/真机复跑
  `make yh-link-probe FULL=1`，已记入 [docs/todo.md](../todo.md)。

P1-3 的验收天然可以借容器：**同一组对象分别用自有链接器和 GNU `ld` 链，
比对可执行的行为**。这是自举路线的第一条真链。

### P2 — macOS/arm64（对象出口）

**反对现在就做的理由**：还没有 Mach-O 对象，且 Mach-O 的重定位语义与 ELF
根本不同——ELF 按符号表下标，Mach-O 按**节内偏移差**（`r_extern=0` 配
`r_address`），符号引用还要 `r_extern=1`。等于要写第二个对象写出器。
但**解析器、扫描器、AArch64 编码器全部复用**，增量集中在出口。

| 任务 | 内容 | 门 |
| --- | --- | --- |
| P2-1 | Mach-O 目标模型（`TS_FMT_MACHO64`、节/段布局、重定位表达） | 模型自检通过 |
| P2-2 | Mach-O 对象写出（`__TEXT`/`__DATA`/`__LD` 段、nlist、relocs） | 宿主 `otool -r` 解析正常，`ld64` 能链接 |
| P2-3 | Darwin 方言对齐（`@PAGE`/`@PAGEOFF` 已是本工具输入契约，Mach-O 用同一组记号） | 用编译器 Darwin 目标发射的语料做差分 |
| P2-4 | 本机装载与验收（TC9） | 链出的可执行 `./` 起来行为与 `clang` 链接的参照一致 |

P2 的验收**不用容器**：宿主 Xcode 的 `ld64` 就是最权威的 oracle，
还省掉一层模拟误差。

### P3 — x64

**这是本方案里最该被质疑的一块，先把账摆清楚。**

现在写 x64 汇编器**没有生产者**：`compiler/backend/` 只有 `arm64.yh` 与
`arm64_call.yh`，yh 不会发射任何 x64 汇编。先写 x64 汇编器等于先造一个
没有输入方的组件。

正确的依赖顺序是：`compiler/backend/emit_x86_64.yh` → x64 汇编器 → 自有链接器。
所以 P3 必须拆成两段，而且**编译器后端在前**：

| 任务 | 内容 | 门 |
| --- | --- | --- |
| P3-1 | `TS_ISA_X86_64` 常量与目标选择（结构已就位，`TargetSpec.isa` 已有该字段） | 现有代码零改动 |
| P3-2 | **编译器 x64 后端**（寄存器/栈帧/ABI/指令发射） | 容器里 x64 目标语料编译出对象 |
| P3-3 | x64 编码器（`src/asm/x64/*.yh`），oracle 用容器里的 `x86_64-linux-gnu-as` | 逐条编码与 `as` 一致 |
| P3-4 | x64 扫描/解析（寄存器 `rax/eax/ax/al`、寻址 `(%rax,%rbx,4)`、RIP 相对） | 同上 |
| P3-5 | x64 ELF 出口 | 容器里 `ld` 能链、`qemu-x86_64-static` 能跑，与参照行为一致 |

容器在这两段里都有用：x64 的 linker + qemu 正好补齐宿主没有的部分。
但要注意**跨架构对齐**：x64 对象在容器里跑的是 `qemu-x86_64-static`，
行为差异要能区分「汇编器错」与「qemu 慢/不支持某 syscall」——所以 P3-5 的
差分门要保留参照侧。

### P4 — macOS/x64

P2 与 P3 都完成后自然接上，主要是 Mach-O 输出换 x64 编码器。
宿主本来就是 Apple Silicon，macOS/x64 需要 Rosetta 才能跑；
测试价值低于前两格，**放在最后，可以不做**。

## 5. 每格复用什么

| 组件 | arm64/Linux | arm64/macOS | x64/Linux |
| --- | --- | --- | --- |
| 扫描器 `20_scan.yh` | 复用 | 复用 | 需改（寄存器/寻址记法不同） |
| 表达式/标签/伪指令 | 复用 | 复用 | 需改 |
| 指令编码器 | 复用 | 复用 | 新写 |
| 对象写出 | 复用 | 新写（出口） | 复用 |
| 重定位白名单 | 复用 | 新写（表达方式不同） | 新写（类型号不同） |

**唯一的结构动作**：把 `src/asm/` 下按 ISA 分子目录。yh 按文件名排序编译，
跨目录的导入关系不变，所以这是纯搬运，改动风险低，但**现在不做**——单 ISA
时目录是多余的。

## 6. 已知的坑

- **`docker build --platform linux/amd64` 在 colima 上不可信**（§2）。要 amd64
  镜像就 `docker pull --platform linux/amd64` 官方镜像，或者干脆用 arm64 容器
  + `binutils-x86-64-linux-gnu` 做交叉（当前 `elf_link_check` 用的就是这个）。
- **colima 不共享宿主 `/tmp`**。门的中间产物放仓库内 `tmp/linkbox/`。
- **页寻址/低 12 位/绝对地址不能在汇编期算**。它们取决于节的最终地址；
  链接器把 `.text` 放在非 4KiB 对齐处时，汇编期算出来的值就是错的
  （这条是容器门在 2026-10-03 抓出来的真 bug，见 §3 与
  [完成记录](../01-finished/yh-link容器链接门-2026-10-03.md)）。
- **局部符号才可以在汇编期定分支**。全局符号即使已定义也要留重定位——
  链接器可能把它重定向到别的目标文件。

## 7. 待确认

- x64 是否真的要做？如果只是「万一」，P3-2 的编译器后端成本远大于 P3-3，
  而没有 P3-2 的话 P3-3 之后全是死代码。**建议先确认这件事再动 P3。**
- Linux 连续自举（TC6/P1-4）需要一个 x64 或 arm64 的 Linux 环境；
  colima 的 arm64 容器可以，但需要把 `yh` 与依赖装进去。要不要把这件事
  并进 CI（本仓库目前没有 Linux CI）由用户定。
