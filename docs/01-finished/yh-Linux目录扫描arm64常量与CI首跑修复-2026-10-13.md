# yh：arm64 目录扫描常量与 CI 首跑三处阻塞（2026-10-13）

## 背景

`1a8b4fa` push 后，`.github/workflows/ci.yml` 的 `linux-arm64` 作业**首次真实运行**
（此前该工作流从未跑过）在 2m13s 失败：容器内 `make` 的第一步就挂——

```
python3 "./tools/seed-build.py" --compiler "/build/bin/yh-linux-arm64" --project "./compiler" --output "./yh"
yh: 无法打开目录: .
make: *** [Makefile:85: yh] Error 1
```

本地（WSL，仓库在 `/mnt/c`）跑同一套门全绿，所以这是个 **CI-only** 的差异。

## 根因一：openat 的 flags 用了 x86_64 的 `O_DIRECTORY`

`compiler/cmd/project_dir.linux.yh` 的目录枚举：

```yh
linux_syscall6(56 /* openat */, AT_FDCWD, dir, 0x10000, 0, 0, 0)
```

`0x10000` 只在 **x86_64（asm-generic）** 上是 `O_DIRECTORY`。**arm64 有自己的
取值**，两者正好错位：

| 标志 | arm64 | x86_64 |
| --- | --- | --- |
| `O_DIRECTORY` | `0o40000` = **0x4000** | `0o200000` = **0x10000** |
| `O_DIRECT` | `0o200000` = **0x10000** | `0o40000` = 0x4000 |
| `O_NOFOLLOW` | `0o100000` = 0x8000 | `0o400000` = 0x40000 |

于是编译器实际在「**用 `O_DIRECT` 打开一个目录**」：

- tmpfs / ext4 / overlayfs 直接 `EINVAL`（这正是 CI 容器 `/build` 的 overlayfs）；
- 只有 **9p**（WSL 的 `/mnt/c`，本仓库所在的文件系统）不校验该标志、放行——
  所以本地 `make` / `make test` / `make selfhost-native` 一直是绿的，一进容器必挂。

### 证据链

1. **CI 日志**：容器内 `make` 首步 `无法打开目录: .`（overlayfs）。
2. **本地复现**：同一份种子、同一份检出，cwd 在 `/tmp`（tmpfs）→
   `yh: 无法打开目录: .`；cwd 在 `/mnt/c`（9p）→ 正常。用 HEAD 的新鲜克隆在
   `/mnt/c` 上跑 CI 的四步全绿（`make`/语法语料/运行语料/主门），证明提交内容本身没问题。
3. **最小探针**（`tmp/dirprobe.c`，arm64 静态、复刻同一 syscall）：
   - 传 `0x10000`：tmpfs 上 `-22 (Invalid argument)`，9p 上 `fd 3`；
   - 传 `0x4000`：两种文件系统都正常；
   - 只传 `0`（无 `O_DIRECTORY`）也正常。
4. **常量对照**：`aarch64-linux-gnu-gcc -dM -E -include fcntl.h` 给出
   `__O_DIRECTORY=040000`、`__O_DIRECT=0200000`；本机 x86_64 gcc 正好相反。
5. **QEMU 侧**：`strace` 显示 glibc 版本（用 arm64 的 `0x4000`）被正确翻译成宿主
   `openat(AT_FDCWD, ".", O_RDONLY|O_DIRECTORY)`；而 `0x10000` 在宿主被翻成 `O_DIRECT`，
   于是内核在 tmpfs/ext4 上按「目录 + O_DIRECT」判 `EINVAL`。

### 修复

`0x10000` → `0x4000`，并把 arm64/x86_64 取值错位这件事写进注释（这个坑在 9p 上
完全看不出来，注释必须留住判据）。

## 根因二：`runtime-memory.py` 硬编码 `/usr/bin/clang`

`make selfhost-native` 的第 5 个门 `tests/selfhost/runtime-memory.py` 在 Linux 宿主
固定调用 `/usr/bin/clang`（为了避开仓库自带的交叉工具链包装），且 `run()` 不捕获
`FileNotFoundError`。CI 容器只装 `build-essential python3`——**没有 clang**，这一步
必然抛异常。本地 WSL 装了 clang-21，所以同样看不出来（修完根因一后它就会浮上来）。

修复：按宿主架构选汇编器——

- 宿主是 aarch64（CI 的 arm64 容器）：系统 `gcc` 原生汇编；
- x86_64 宿主：系统 `clang` + `-target aarch64-linux-gnu`（保持原行为），
  找不到时给明确 FAIL 而不是 traceback；
- Darwin：`clang` + `-target`（不变）。

## 根因三：构建统计的 64 位计时被截成 32 位（复跑门时暴露）

修完前两条复跑 `make selfhost-native`，卡在 `lex-stats.py`：

```
阶段计数错误：进程数=3，总计=(6, 9, 4, 4, 4, 4, 2)，期望=(6, 9, 4, 4, 4, 4, 2)
```

累计计数其实完全相等——真正失败的是计时解析：父进程那行是
`time_total_ns=-2002191199`，`TIMING_RE` 的 `(\d+)` 匹配不到负号，`parent_timing`
为空。数值上完全吻合 **32 位截断**：

```
四次阶段耗时之和 197933909 + 763842032 + 932696240 + 395124716 = 2289596897
加上未计入的 3.18 ms 开销               → time_total_ns = 2292776097 (2.293 s)
2292776097 - 2^32 = -2002191199         ← 打印出来的值
```

根因：yh 的 `int` 是 **32 位**（`parse/parse_type.yh` 的 `TK_INT → TY_I32`），而
`gen.append_int(buf, n, v int)` 的实参就是 `int`（注释也写明「行号/列号规模远小于
2^31」）；`cmd/module_build.yh` 把纳秒计时 `.to_type(int)` 后交给它，于是**构建只要
超过 2.147 s 就翻负**。本地快构建偶尔压在 2.147 s 以下，所以时绿时红。

修复：

- `gen/buffer.yh` 新增 `pub fn append_i64(buf *u8, n int, v i64) int`（64 位十进制，
  含负号；注释写明为什么不能复用 `append_int`）；
- `cmd/module_build.yh` 的五个计时字段（project/schedule/object/link/total）改走
  `append_i64`；
- `tests/selfhost/lex-stats.py` 的 `TIMING_RE` 接受可选负号，并把「负计时」单独报成
  「64 位计时被截断」，不再混进阶段计数诊断。

## 新增回归门：`tests/selfhost/foreign-fs-build.py`

前两条都是「宿主文件系统够宽容就看不见」的缺陷，所以新增一道**文件系统维度**的门，
并接入 `make selfhost-native`：把 fixture 复制到**系统临时目录**（通常是另一个文件
系统：Linux 上是 tmpfs/ext4、容器里是 overlayfs）后冷编 + 运行，核对退出码 42。
日志里同时打印该目录的文件系统类型，便于以后直接看日志定位。

对照实测：**旧编译器在这道门上必失败**（`/tmp` 上 `yh: 无法打开目录: src`），修复后通过。

## 验证

- `make test`：语法正例 78/78、反例 42/42、运行语料 293/293（`test_rc=0`）。
- `make selfhost-native`：种子校验、候选两代固定点（24 个产物一致）、自解析 71 文件、
  固定点探针、CLI 冒烟、`scratch-isolation` 8/8、`lex-stats`、`runtime-memory`、
  `check-command`、**新增 `foreign-fs-build`**、`link-cache`、modules 与项目验收全绿。
- 慢构建实证：编译器自编（9.17 s）打印
  `time_total_ns=9173060069`（修复前这类值会被截断），`lex-stats` 连跑 3 次通过。
- 外围文件系统实证：修复后的编译器在 `/tmp`（tmpfs）上冷编整个 `compiler/` 项目
  `rc=0`；新种子同样在该条件下通过（等价于 CI 容器的 overlayfs 场景）。

## 滚种子

`bin/yh-linux-arm64`：`970cf4ff0d7758f2297d3d3943a5407e2c150a709a9116445b8519b2ac8b9fc3` →
**`33733767fe5f84afd6f14f6662598e8f5615b69d8ca4edf29705991a4ac18a35`**
（`SEED=bin/yh-linux-arm64 SEED_DEST=bin/yh-linux-arm64 make seed`，滚完复跑主门全绿；
新种子在 `/tmp`（tmpfs）上冷编 `compiler/` 项目 `rc=0`）。

## 边界与未做

- **`darwin-arm64` 作业仍未真实跑过**：它只在 `workflow_dispatch` 触发（push 不跑），
  macOS 目录枚举走 `getattrlistbulk`，不涉及这组 open 标志，故本轮不改 Darwin 侧。
- **CI 的 60 分钟上限仍未实测**：容器内所有二进制都在 QEMU 模拟下运行，粗估比本机慢
  数倍；本轮只保证逻辑上不再必挂，真实耗时需下一次 CI 观察。
- **`c_ct_expand_values` 仍是 32 位 `int`**：编译期 for 展开值按设计存 `int`，与本次
  计时截断不同源，未动。
- `asm/`、`link/` 两个项目的改动按用户要求仍不提交。
