# yh 多平台架构整理与优化方案

> **待重写（不可直接执行）**：本文「现状」整章基于 C 版 `src/` ONE_SOURCE、`-run`、
> `-sysroot`、libtcc1，这些均已于 0.0.3 随 stage0 删除失效。现行后端事实见
> [自举后端架构](../03-design/yh-自举后端架构.md)，现行决定见
> [ADR-0006](../adr/0006-yh自举产物为主要开发编译器.md)；多平台仍是
> `docs/todo.md` 的未完成项，重写后再执行。
目标：后端支持 **linux / darwin / windows × arm64 / x64** 共 6 个目标组合。
本文整理现状架构与耦合点，给出分阶段优化方案与验证门。编写时基线为
0.0.1 M3 已完成（Darwin arm64 本机 Mach-O、交叉 Linux ELF）。

## 1. 目标矩阵与优先级

| # | 目标三元 | 建议优先级 | 理由 |
|---|---|---|---|
| 1 | linux/arm64 | 已达成（0.0.1 主线） | ELF 自链接 + -run 全通过 |
| 2 | linux/x64 | ★ 第一优先 | 服务器主流；后端可从历史恢复，增量最小 |
| 3 | darwin/arm64 | 已基本达成（macho-out.c） | 差 libtcc1 的 Mach-O 成员 |
| 4 | darwin/x64 | 第二 | Intel Mac 在退坡但 CI 覆盖便宜 |
| 5 | windows/x64 | 第三（最大单项） | 用户基数最大，但缺口也最大（无 PE、无 MS ABI） |
| 6 | windows/arm64 | 最后 | 复用 5 的 PE 层 + arm64 后端增量 |

术语约定：**宿主（host）**= 编译器本体运行的平台；**目标（target）**= 生成代码
运行的平台。0.0.x 阶段只承诺「本机目标」（host == target）+ 现有
`-sysroot`/`-Wl,-oformat=` 交叉路径；任意交叉组合不做验收承诺。

## 2. 现状架构梳理

当前分层（ONE_SOURCE 单编译单元构建）：

```
tcc.c（驱动/选项）
  └─ yh 前端 yh_{decl,type,expr,stmt,builtin}.c + tccpp.c 词法   ← 架构无关
       └─ tccgen.c（类型/表达式/语句 → 值栈 IR）                  ← 架构无关
            └─ src/targets/arm64-gen.c   指令选择/调用约定        ← 架构相关
               src/targets/arm64-link.c  重定位语义/GOT/PLT       ← 架构相关
                 └─ tccelf.c(ELF 全量读写/链接)                   ← 格式层(core 内)
                    macho-out.c(MH_OBJECT 对象) + 系统 cc 终链     ← 格式层(core 内)
                      └─ libtcc1.a（外部目标 C 工具链产出）        ← 运行时，按三元区分
```

耦合点清单（优化要逐条拆掉的点）：

1. **目标架构硬编码**：`src/core/tcc.h:138` 直接 `#define TCC_TARGET_ARM64`；
   `Makefile:27` `ARCH = arm64`。
2. **输出格式判定依赖宿主宏**：`src/core/libtcc.c:805` 用 `#ifdef __APPLE__`
   决定默认 Mach-O 还是 ELF，交叉与显式选择靠 `sysroot`/`output_format_explicit`。
3. **OS 判断散落各文件**：`libtcc.c`/`tccrun.c`/`tcctools.c`/`tccgen.c`/`tcc.c`
   各自 `#ifdef __APPLE__/_WIN32/__linux__`，没有统一的 `TCCOS_*` 词汇层。
4. **`-run` 只认 aarch64 宿主**：`tcc.h:141-147` `TCC_IS_NATIVE` 仅
   `__aarch64__`；x64 宿主无法 -run。
5. **libtcc1 固定 aarch64-linux-gnu**：`Makefile:59-127` 无论宿主是何系统都产
   AArch64 Linux ELF 成员（Darwin 上 Mach-O 目标借用不到它，交叉 ELF 才用得上）。
6. **macho-out.c 只有 ARM64 重定位**：17 处 `ARM64_RELOC_*`、0 处
   `X86_64_RELOC_*`，且格式代码放在 `src/core/`（`src/formats/` 目前只有头文件）。
7. **架构后端内嵌格式分支**：`arm64-gen.c:853` 变参按
   `output_format == MACHO` 走 Darwin `n_named` 约定——OS 差异渗进了后端。
8. **x86_64 后端与 PE 支持已删但可恢复**（git 历史）：
   - `git show 0db9fca^:x86_64-gen.c` / `x86_64-link.c`（i386/arm/c67/il 同批删除）；
   - `git show ef8db88^:src/formats/tccpe.c`（1947 行 PE/COFF 写入器）、
     `tcccoff.c`、`coff.h`，以及 `win32/` 91 个文件（include/、msvcrt 导入库、
     build-tcc.bat）。
9. **lib/ 残留死文件**：`alloca86*.S`、`armeabi.c`、`armflush.c`、`va_list.c`、
   `libtcc1.c`（x86_64 通用版，恢复 x64 时正好用）——现在对 arm64 是死代码。
10. **Windows 差距最大**：无 PE 写入器、无 MS x64/ARM64 调用约定、无 crt、
    无导入库；`_WIN32` 分支只剩宿主兼容零星代码（tccrun/tcctools/tcc.c）。

## 3. 差距矩阵

| 目标 | 代码后端 | 对象格式 | 调用约定增量 | libtcc1 | 最终链接 | -run |
|---|---|---|---|---|---|---|
| linux/arm64 | ✅ arm64-gen | ✅ ELF | — | ✅ Linux ELF | ✅ 自链接 | ✅ |
| darwin/arm64 | ✅ +n_named | ✅ macho-out | Darwin 变参（已做） | ❌（现为 Linux ELF 成员） | ✅ 系统 cc | ✅ MAP_JIT |
| linux/x64 | ❌ 可恢复 | ✅ ELF（架构无关） | SysV | `lib/libtcc1.c`+`alloca86_64.S`（在库中） | ✅ 自链接 | 待恢复 TCC_IS_NATIVE |
| darwin/x64 | ❌ 可恢复 | ⚠️ 缺 x64 重定位 | SysV | 同上（Mach-O 成员） | ✅ 系统 cc | 待恢复 |
| windows/x64 | ❌ 可恢复 | ❌ tccpe.c 可恢复 | MS x64 | 需 COFF 成员 | tccpe 自链接 | ❌ |
| windows/arm64 | ⚠️ arm64 增量 | ❌ | MS ARM64 | 需 COFF 成员 | tccpe 自链接 | ❌ |

## 4. 优化方案

### 4.1 目标平台抽象统一（地基，先做）

- **三元的单一事实源**：引入 `TCCOS_LINUX / TCCOS_DARWIN / TCCOS_WINDOWS` 与
  `TCC_TARGET_ARM64 / TCC_TARGET_X86_64`，由 Makefile 以
  `-DTCC_TARGET_X86_64 -DTCCOS_LINUX` 注入；tcc.h 只保留「未显式指定时按宿主
  推默认值」的兜底。core 代码不再直接写 `__APPLE__/_WIN32/__linux__`
  （现存约 8 处逐一改写），格式判定、路径后缀、ld 解释器等全部换成新词汇。
- **默认格式判定收敛成一个函数**：把 `libtcc.c:805` 的宿主 `#ifdef` 换成
  `default_output_format(target_os, sysroot, explicit)`——「有 sysroot 即交叉
  → ELF；本机 → 按 OS 取默认格式」。
- **目录归位**：`macho-out.c` 从 `src/core/` 移到 `src/formats/`，未来
  `pe-out.c` 同层；`tccelf.c` 暂留 core（与链接器逻辑交织过深，标注为后续
  候选，不做顺手重构）。
- **后端 OS 差异上提**：把 `arm64-gen.c:853` 的 `output_format == MACHO`
  变参分支抽成目标描述符（如 `tcc_target_abi`：`AAPCS64_LINUX /
  AAPCS64_DARWIN / MS_ARM64 / SYSV_X64 / MS_X64`），OS/格式判断不再出现在
  指令生成里。这一步让「加一个 OS」不再等于「在后端里加 if」。

### 4.2 构建系统矩阵化

- `make ARCH=arm64|x86_64`（默认本机架构）；`EXESUF`/`DLLSUF`/输出格式按
  `OS` 参数推导，不再只靠 uname。
- **libtcc1 按目标三元构建**：定义 6 个三元
  `aarch64/x86_64 × linux-gnu/macos/windows-gnu(coff)`，clang `-target` +
  `llvm-ar` 可覆盖全部；修掉「Darwin 宿主也只产 Linux ELF libtcc1」的现状。
  归档器统一优先 `llvm-ar`（BSD ar 拒绝非 Mach-O 成员的问题已验证）。
- 产物命名：发布物 `yh-{os}-{arch}`（如 `yh-darwin-arm64`），CI 产 6 份。
- `lib/` 死文件清理：x64 恢复后归位 `alloca86_64.S` 等；arm 无关的
  `armeabi.c`/`armflush.c` 若仍无引用则列入清单（不顺手删，见 M6 口径）。

### 4.3 阶段一：恢复 x86_64 后端（linux/x64，收益最大）

- 从历史恢复 `x86_64-gen.c`/`x86_64-link.c` 到 `src/targets/`，`TCC_IS_NATIVE`
  放开 `__x86_64__` 宿主。
- **适配本分支已改动的 core 接口**（恢复 ≠ 原样能用）：
  - `n_named` 变参签名与 void main 返回 0 的函数框架约定；
  - ADR-0002 数组按值机制（机制 a：包装结构体 + 隐式指针）在 SysV 下的落点——
    x86_64 对 >16B 聚合一律 MEMORY 类，天然按引用传递，比 AAPCS64 还简单，
    但 HFA 判定、4KB 断言边界要按架构复核；
  - yh 前端对 tccgen 的钩子（gfunc_call 后 vsetc(REG_IRET) 等）核对一遍。
- 变参走寄存器保存区（AL 计数）路径，**不能**复用 arm64 的 n_named 方案。
- `lib/libtcc1.c` + `alloca86_64.S` 接入 Makefile（成员为 x86_64 Linux ELF）。
- 验证门：x64 Linux 容器 `hello.yh -o`/`-run` 通过；`tests/yh-run` 全绿；
  ADR-0001 矩阵用例在 x64 重跑。

### 4.4 阶段二：Mach-O 写入器支持 x64（darwin/x64）

- 重定位翻译按架构拆分：arm64 现有 17 处映射抽到 `macho_reloc_arm64()`；
  新增 `macho_reloc_x86_64()`（`X86_64_RELOC_SIGNED/UNSIGNED/GOT_LOAD/BRANCH`
  等）；MH_OBJECT 头/段/符号表主体保持架构无关。
- x64 上 Darwn 变参=SysV，无 Darwin 变体（与 arm64 不同），目标描述符
  `SYSV_X64` 直接生效。
- 验证门：Intel Mac（或 CI macos-13）本机 `-o`/`-run`；交叉产物用
  `llvm-objdump --reloc` 结构校验。

### 4.5 阶段三：Windows（先 x64 后 arm64，最大单项工程）

- **恢复 `tccpe.c`（自链接 PE）而非委托外部工具链**：与 Darwin「委托系统 cc」
  相反——Windows 用户通常没有 cc，自包含是硬需求。上游实现已含导入表、
  DLL 导入导出、`-run` 所需的内存加载。
- 从历史恢复 `win32/include` + msvcrt 导入库（91 个文件），crt 启动走
  msvcrt.dll 路线（上游已验证），`EXESUF=.exe`。
- ABI 增量（两个后端各一块）：
  - **MS x64**：rcx/rdx/r8/r9 + 32 字节 shadow space；变参实参全部走栈
    （`va_arg` 从保存区读）；f32 **不**提升为 f64——与 SysV/Linux 相反，
    prelude 的 printf 声明要按目标出签名。
  - **MS ARM64**：x0-x7 命名参数、变参全部在栈、无 FP 提升；arm64-gen 现有
    `n_named` 机制扩展出第三种变体。
- libtcc1 成员改为 COFF（clang `-target x86_64-pc-windows-gnu` 可产）。
- 验证门：Windows x64 本机 hello 运行、prelude 变参输出正确、`-run` 可用；
  arm64 Windows 至少 -c 产物 `llvm-readobj` 结构校验（真机验证可放宽）。

### 4.6 贯穿：yh 语义的每架构验证矩阵

- ADR-0001 数组/切片矩阵 × 已实现目标（`tmp/abi` 探针 + `tests/yh-run`）。
- 变参 × 3 OS 约定（prelude 8 函数中 printf/open/write 是变参）。
- `-run` 平台差异：darwin arm64 MAP_JIT/W^X、arm64 清指令缓存、Windows
  可执行内存分配。
- `make test` 分目标报告：语法→编译→拒绝→运行四级，非本机目标显示 SKIP
  原因（沿用 M5-01 口径）。

### 4.7 测试与 CI

- CI 矩阵：ubuntu-24.04（arm64+x64）、macos-14/macos-13、windows-2022 +
  windows-11-arm（GitHub Actions 均有对应 runner）。
- 交叉产物（如 linux 宿主产 windows PE）只做「能产出 + 结构校验」，运行
  验证留在对应本机矩阵，避免交叉/本机验收口径混淆。

## 5. 实施顺序与验证门

| 阶段 | 内容 | 验证门 |
|---|---|---|
| 0 地基 | 4.1 抽象统一 + 4.2 构建矩阵化 | `make` 与参数化构建均零告警；macho-out 迁移后全测试不变 |
| 1 linux/x64 | 4.3 恢复 x86_64 后端 | x64 容器 `-o`/`-run` 全绿 + ADR-0001 矩阵 |
| 2 darwin/x64 | 4.4 Mach-O x64 重定位 | Intel Mac 本机运行或 CI 结构校验 |
| 3 windows/x64 | 4.5 tccpe + MS ABI + win32 头 | Windows 本机 hello/变参/-run |
| 4 windows/arm64 | 4.5 arm64 MS 变体 | 同上（结构校验可放宽） |

每阶段完成更新 `docs/finish.md` 与 `docs/todo.md`，新增 `.yh` 用例并保持
`make` 零告警（沿用 0.0.1 验收规范）。

## 6. 决策点（需要定案后动工）

1. **单二进制多目标 vs 每宿主单目标**：0.0.x 建议后者（现状 `-sysroot`
   交叉已验证，构建简单）；「一个 yh 二进制内嵌全部 6 目标 + 运行时选择」
   留作后续优化（上游 tcc 的 cross 模式）。
2. **Windows 终链**：tccpe 自链接（建议，理由见 4.5）vs 委托 gcc/clang。
3. **libtcc1 政策**：维持「外部目标 C 工具链构建、禁止 yh 自举」至 0.0.x 结束。
4. **tccelf.c 是否迁移 `src/formats/`**：暂不动（与链接逻辑交织），
   待 M6 清理后再评估。

## 7. 工作量粗估（不含 CI 基建）

阶段 0：1–2 天；阶段 1：3–5 天（恢复容易、接口适配是大头）；阶段 2：1–2 天；
阶段 3：1–2 周；阶段 4：3–5 天。
