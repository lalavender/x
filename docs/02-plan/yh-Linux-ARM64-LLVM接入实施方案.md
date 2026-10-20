# yh Linux/ARM64 LLVM 接入实施方案（F1）

日期：2026-10-20  
状态：**F1 全部完成（2026-10-20）**。Linux/AArch64 已默认使用 LLVM 后端，
内嵌 lld、固定桥、容器全门、连续自举与种子滚动均已完成。
完成证据见
[F1 完成记录](../01-finished/yh-Linux-ARM64-LLVM-F1-2026-10-20.md)。

## 0. 目标与边界

把 Linux/AArch64 从「旧 ARM64 后端」推进到「内嵌 LLVM 可生产」：

1. `--backend llvm --target aarch64-unknown-linux-gnu` 能发射 AArch64 ELF 对象；
2. 程序能用编译器自带运行时完成内存、格式化输出与 Linux syscall；
3. `@[extern]` C ABI 与固定 LLVM 的 AAPCS64 规则一致，含标量、HFA、小聚合和
   大聚合间接传递；
4. 单文件、模块项目、O0/O2、缓存与对象架构校验在 **Linux/ARM64 容器**内通过；
5. 全量语料、自解析和连续自举通过后，才切 Linux/ARM64 默认 LLVM 并滚种子。

不在本方案内：Linux/x64 已有能力回退、Darwin/Windows 目标、旧后端删除（LL12）、
把 gcc 链接器替换成内嵌 lld 的生产化已在 F1-2 完成。

## 1. 现状与真实缺口（2026-10-20 容器实测）

容器：Apple Container，`ubuntu:24.04`，原生 arm64，挂载仓库到 `/work`；
`bin/yh-linux-arm64` 冷编当前 `compiler/` 后运行探针。

| 探针 | 现状 | 结论 |
| --- | --- | --- |
| 纯计算 `return 0` / 整数循环 / 数组 | 通过，产物为 AArch64 ELF | 目标身份、桥、LLVM 发射主链已通 |
| `printf` / `malloc` / `free` | 预检报「LLVM 自有完整运行时仅支持 Linux x86_64」 | 运行时目标门未放开 |
| `linux_syscall6` | 仍按 x86_64 `syscall` 内联汇编 | AArch64 需 `x8` + `svc #0` 与不同 syscall 号 |
| `printf` 的 `va_list` | 固定按 x86_64 24 字节分配 | AArch64 Linux 的 `va_list` 是 32 字节结构 |
| `@[extern]` C 标量 | `llvm_abi_supported` 只接受 SysV/Darwin | AAPCS64 标量分支缺失 |
| C 聚合/HFA | 只有 Darwin 走 `llvm_apple_abi.yh` | Linux AArch64 未分派，虽规则同源 |
| 链接 | 无内嵌 lld 时回落宿主 `gcc` | arm64 容器原生可用；跨宿主需后续 lld |

`aarch64-unknown-linux-gnu` 的 `TargetInfo`（layout `...-Fn32`）、桥 triple 白名单、
对象 machine=183 校验已存在，不需要重造目标元数据。

## 2. 分片与验收

### F1-0 目标、标量 ABI 与运行时（本片先做）

- `llvm_call.yh` 增加 `aapcs64` ABI 分派：C 标量、窄整数属性、`printf/open`
  的 yh 变参白名单；裸用户 C 变参继续在源码层拒绝。
- `llvm_module.yh` 只对真正缺运行时的目标保留预检拒绝；AArch64 放行
  `linux_syscall6`/`malloc`/`free`/`printf`。
- `llvm_runtime.yh` 增加 AArch64 分支：
  - syscall：`x8` 传号、`x0..x5` 传参、`svc #0`；
  - `write=64`、`mmap=222`、`munmap=215`；
  - `va_list` 按 32 字节分配，其余格式化逻辑复用。
- 新增 `tests/selfhost/llvm-linux-arm64.py` 与 `.yh` 探针：
  - 最小程序、整数/数组/循环；
  - `malloc/free/printf/%d/%s/%c/%llu`；
  - O0/O2 对象 machine=183、运行输出、运行时导入审计。
- 容器命令固定为 `make test-llvm-linux-arm64`（arm64 容器内）。

**关闭标准**：上述探针 O0/O2 全绿；`make test` / `make selfhost-native` 在
arm64 容器内保持既有绿灯（LLVM 仅显式开启）。

**状态（2026-10-20）**：已完成。`make test-llvm-linux-arm64` O0/O2 全绿；
旧后端 `make selfhost-native` 在容器内全绿。

### F1-1 AAPCS64 聚合/HFA 与全量语料

- 复用 `llvm_apple_abi.yh` 的 AAPCS64 分类（HFA ≤4、≤16 直接、>16 间接），
  在 Linux AArch64 上分派；固定 oracle 核对 clang 21.1.8 的签名。
- 新增 `tests/selfhost/llvm-linux-arm64-abi.py`：
  - 标量窄型、`_Bool`、8 参数、混合浮点/整数；
  - HFA 2/3/4 个 float/double、非 HFA 小聚合、24 字节大聚合 sret/间接参数；
  - C→YH、YH→C 双向与函数指针回调；O0/O2 原生运行。
- 在 arm64 容器跑全量 `tests/yh-run`、`tests/modules`、`tests/modules/build-check`
  的 O0/O2，记录覆盖/回退统计。

**关闭标准**：语料 O0/O2 无差异，ABI 双向运行通过，项目验收通过。

**状态（2026-10-20）**：已完成。`tests/yh-run` O0/O2 各 344/349（5 个 Darwin
专属 SKIP），modules 18/18，build-check 105/105；AAPCS64 聚合/HFA 与
C↔YH↔C 回调通过。

### F1-2 生产链接、缓存与自举

- [x] 接入 Linux/AArch64 内嵌 lld（固定 SDK 的 arm64 lld 归档 + 宿主 GCC
  链接模板）；最终链接不经 PATH 上的 gcc/ld，`llvm-cache.py` 用空 PATH/包装器
  日志证明调用面。
- 对象/链接缓存键补目标架构、AAPCS64 与运行时版本；架构校验继续用 machine=183。
- [x] 连续自举 A（旧种子）→ B/C/D（LLVM O0），D 再编 E 固定点；O2 单独一遍。
  `make selfhost-native` 在容器内通过：cc3→cc4 24 个 LLVM/接口产物固定点，
  104 文件自解析，O0/O2 运行时/C ABI 门与项目缓存门全绿。
- [x] 独立 O2 连续自编：B/C 二进制 SHA-256 相同。
- [x] 本平台 `make test` / `make selfhost-native` 全绿后切换 Linux/ARM64 默认
  LLVM，滚 `bin/yh-linux-arm64` 与哈希（`4d13e297…`）。

## 3. 容器验收流程

```bash
container system start
container run -d --name yh-f1 -m 6G -c 6 -v "$PWD":/work -w /work ubuntu:24.04 sleep infinity
container exec yh-f1 sh -c '
  apt-get update -qq &&
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 build-essential binutils xz-utils
'
# 首次准备固定 LLVM 宿主（联网取 arm64 SDK，缓存在 tmp/llvm-migration）
container exec yh-f1 sh -c 'cd /work && make llvm-host'
# 冷编 + F1 门
container exec yh-f1 sh -c 'cd /work && make all && make test-llvm-linux-arm64'
# 主门回归（显式 LLVM 不改变默认路径）
container exec yh-f1 sh -c 'cd /work && make test && make selfhost-native'
```

约束沿用仓库规则：容器内只构建/测试，不 `chown`、不覆盖 `bin/` 种子；
临时产物全部在 `tmp/`。

## 4. 风险与回退

- **AAPCS64 与 Apple ABI 的差异**：固定参数规则同源，变参/栈对齐/系统库不同；
  Linux AArch64 的 C 裸变参仍拒绝，`printf/open` 走 yh 运行时/白名单。
- **链接器**：内嵌 lld 已接入；构建固定 SDK 的 arm64 宿主需要 `libxml2-dev`
  （lld 的 ELF/COFF 驱动依赖）。跨架构（x64 宿主跑 arm64 种子）不在 F1 日常门内，
  目标文件由桥发射、链接模板仍按构建宿主生成。
- **ObjC/va_list 细节**：AArch64 `va_list` 结构大小与 SysV 不同，任何按目标
  写死缓冲的代码都要改成目标分派；本片先覆盖现有 `printf` 格式集。
- **回退**：默认路径已切 LLVM；旧后端仍可在其他平台/显式 `--backend legacy`
  使用，失败时保留旧产物。Linux/AArch64 的 `make test` / `make selfhost-native`
  不再依赖旧后端。

## 5. 事实来源

- `docs/03-design/yh-LLVM后端替换设计.md` §8（F1 范围）
- `docs/03-design/yh-LLVM语义与ABI契约.md`
- `docs/03-design/yh-LLVM目标身份设计.md`
- `compiler/backend/llvm_apple_abi.yh`（AAPCS64 分类实现）
- `compiler/llvm/bridge.c`、`tools/llvm-sdk.py`、`vendor/llvm/sdk.lock.json`
- 容器实测日志：`tmp/f1-linux-arm64-probe.log`（本轮生成）
