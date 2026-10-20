# Linux/AArch64 LLVM F1：运行时、AAPCS64、内嵌 lld 与默认切换

日期：2026-10-20  
范围：Linux/AArch64 的 LLVM 后端、运行时、AAPCS64、内嵌 lld、默认切换、
容器全门与种子滚动。

## 结论

Linux/AArch64 已默认使用 LLVM：目标身份、内嵌桥、AArch64 代码生成、
编译器自带运行时、AAPCS64 C ABI、内嵌 lld、O0/O2、模块/项目验收与连续自举
均通过，种子已滚。旧 ARM64 后端仅保留为其他平台/显式 legacy 的过渡路径。

## 代码改动

- `compiler/backend/llvm_call.yh`
  - 新增 `llvm_abi_is_aapcs64` / `llvm_abi_is_linux_aapcs64`；
  - C ABI 分派接受 Linux `aapcs64`，AAPCS64 聚合/HFA 复用
    `llvm_apple_abi.yh`（固定参数规则同源）；
  - Linux/AArch64 放行 prelude `printf` / `open` 裸变参白名单，用户 C 裸变参仍拒绝；
  - `llvm_abi_attr_kind` 对 Linux/AArch64 返回 0：AAPCS64 只保证窄参数扩展到位宽
    32 位，GCC C 调用方不加寄存器级 `signext/zeroext`；O2 下强加属性会让后端省略
    64 位扩展并读到高位垃圾（cinterop `c_call_yh_narrow` 由 8 复现并修复）。
- `compiler/backend/llvm_module.yh`
  - 预检放行 AArch64 运行时符号；
  - C 聚合签名对 Linux AArch64 走 AAPCS64 分类器。
- `compiler/backend/llvm_scalar.yh`
  - 聚合调用、形参恢复、返回值按 `aapcs64` 分派。
- `compiler/backend/llvm_runtime.yh`
  - AArch64 syscall：`x8` 传号、`x0..x5` 传参、`svc #0`；
  - `mmap=222`、`munmap=215`、`write=64`；
  - Linux/AArch64 `va_list` 按 32 字节结构显式读取：LLVM `va_arg` 指令在
    AArch64 上只按 `__stack` 游标取栈槽，不展开 `gr_top/gr_offs` 寄存器保存区；
    新增 `yh_va_next` 按 AAPCS64 规则取寄存器槽或栈槽，`printf` 全部格式复用；
  - x86_64/Darwin 仍用原 `va_arg` 线性游标，行为不变。
- `tests/yh-run/check.py`：`asm-symbols-safe` 只约束旧 ARM64 发射器；LLVM
  符号由 ABI 后缀/LLVM 合法化处理，GNU as 与 LLVM 集成汇编器均接受。
- `tests/modules/build-check.py`：Linux/AArch64 不要求 `signext/zeroext` 文本。
- `Makefile`：新增 `test-llvm-linux-arm64` 门；`FAST_DIR` 改为 make 原生
  表达式，避免容器 `/bin/sh` 端口差异。

## 新增测试

- `tests/selfhost/llvm-linux-arm64-runtime.yh`：malloc/free/memcpy/memset/strlen、
  `%d/%s/%c/%llu` 与 syscall 输出。
- `tests/selfhost/llvm-linux-arm64-abi.yh` + `.c`：窄型、`_Bool`、混合整浮、
  HFA2/HFA3、16 字节聚合、24 字节 sret/间接参数、C→YH→C 函数指针回调。
- `tests/selfhost/llvm-linux-arm64.py`：O0/O2 运行时、LLVM 文本、AArch64 ELF
  machine=183、运行时导入面与双向 C ABI。

## 验证（Apple Container，Ubuntu 24.04，原生 arm64，6G/6CPU）

宿主闭包：`python3 tools/llvm-host.py prepare --host linux-aarch64` 通过，
静态 LLVM 21.1.8 宿主 machine=183，动态依赖仅 libc/libm/ld。

| 门 | 结果 |
| --- | --- |
| `make test-llvm-linux-arm64` | O0/O2 全 PASS |
| `tests/yh-run/check.py --backend llvm --target aarch64...` | O0 344/349、O2 344/349（5 个 Darwin 用例 SKIP） |
| `tests/modules/check.py` 同上 | O0/O2 各 18/18 |
| `tests/modules/build-check.py` 同上 | O0 105/105、O2 105/105 |
| 旧后端 `tests/yh/check.py --compiler` | 78/78 + 42/42 |
| 旧后端 `tests/yh-run/check.py` | 344/349（同一批 Darwin SKIP） |
| `make selfhost-native`（容器） | 全绿，project 105/105 |
| Darwin `make` + `make test-llvm-darwin` | 全绿（本改动无回归） |

连续自举（容器内，当前编译器 A 以 LLVM 目标冷编 `compiler/`）：

```
A = 由当前 yh 冷编的 AArch64 LLVM 编译器
B = A 自编，C = B 自编
SHA-256 A = B = C = 58859df932e6ddd2b3e6e3606d45d269e55e672c4fe4a17b215d84b0260e992b
```

A/B/C 均为 72,052,424 B AArch64 ELF，`A version` 在 `compiler/` 内输出 `yh 0.0.5`。
该结果证明 LLVM 生成的编译器可自举并达到二进制固定点；正式 O0/O2 全门脚本
（当前 `llvm-selfhost.py` 固定 x64/内嵌 lld）尚未参数化到 ARM64。

## 第一片边界（已由第二批关闭）

- ~~Linux/AArch64 目前走宿主 `gcc` 最终链接~~：第二批已接入内嵌 lld。
- ~~默认后端仍为 legacy~~：第二批已切 Linux/AArch64 默认 LLVM 并滚种子。
- O2 连续自编、`make test` / `make selfhost-native` 与种子已在第二批完成。
- 用户裸 C 变参仍按既有策略拒绝；`printf/open` 是 prelude 白名单。

## 第二批：内嵌 lld、默认切换与种子（同日收尾）

### 固定 SDK / lld

- `vendor/llvm/sdk.lock.json` 的 `linux-aarch64` 增加固定 lld 21.1.8 归档：
  `lldCommon/lldELF/lldMachO/lldCOFF`、Polly 链接组与 226 个 LLVM 组件；
  新增 arm64 的 `liblld-21`、`liblld-21-dev`、`libpolly-21-dev` 包哈希；
  `system_libraries` 增加 `-lxml2`（lld 构建期依赖）。
- `tools/llvm-sdk.py`：
  - 构建 arm64 宿主时用固定 GCC 的 `-###` 生成 ELF 启动文件/库模板；
  - 生成 `selfhost-flags.txt`（每行一个链接参数），自举闭包改为构建机文件；
  - 删除同名 `libyh_llvm.a` 后再 `ar`，避免从 stub 宿主升级 lld 时残留
    `lld_stub.o` 造成重复定义；
  - 新种子的 `lld_link_config.h` 不再烘焙自举归档路径，缺失
    `YH_LLVM_SELFHOST_FLAGS` 时由 `mb_link` 给出明确诊断。
- `tools/llvm-host.py`：宿主身份校验自举闭包文件与 SHA-256；`shim` 输出
  `selfhost_flags` 绝对路径，供 `seed-build.py`/自举门传入。
- `compiler/cmd/link_cache.yh`：`mb_lld_x64_enabled` 泛化为
  `mb_lld_linux_enabled`（x64/AArch64）；Linux 自举链接也校验闭包非空。
- `compiler/cmd/llvm_emit.yh`：单文件 Linux x64/AArch64 共用内嵌 lld。

### 默认后端与自举门

- `compiler/gen/state.yh`：Linux/AArch64 默认 `c_backend = 1`。
- `tests/selfhost/native-selfhost.py`：
  - `auto` 将 Linux/AArch64 纳入 LLVM；
  - 种子能力探针改为「malloc+printf 实际链接并运行」，避免旧种子只发纯标量 IR
    被误判为可完整自举；不能通过时走 legacy 过渡代再 LLVM 连续自编。
- `Makefile` Linux/AArch64 分支：
  - `RUNTIME_TEST` = `tests/selfhost/llvm-linux-arm64.py`；
  - `CACHE_TEST` = 通用 `tests/selfhost/llvm-cache.py --target aarch64...`；
  - `MODCHECK_FLAGS = --backend llvm`。
- `tests/selfhost/llvm-cache.py`：支持 `--target` 与宿主架构自动选择，
  目标隔离/缓存身份/machine 断言按 x64/AArch64 参数化。
- `tests/selfhost/llvm-linux-arm64.py`：新增默认后端 + 空 PATH 内嵌 lld 门，
  以及编译器自身静态桥/lld 符号、无动态 libLLVM/lld 审计。
- `tests/yh-run/check.py`：默认 LLVM 平台（Linux x64/AArch64、Darwin ARM64）
  不再套用旧 ARM64 的寄存器同名符号规则。

### 最终验证（Apple Container，Ubuntu 24.04 原生 arm64，6G/6CPU）

固定宿主：LLVM 21.1.8 + lld 21.1.8，AArch64 machine=183；
动态依赖仅 `libxml2/libm/libc/ld`，lible 无 `libLLVM/liblld`。

| 门 | 结果 |
| --- | --- |
| `make llvm-host` / `tools/llvm-host.py prepare --host linux-aarch64` | 通过，lld 身份 21.1.8 |
| `make`（新种子默认 LLVM） | 通过，产物 AArch64 ELF，0 个构建机闭包路径 |
| `make test`（ANTLR + 编译器语法 + 运行语料） | 全绿：运行 344/349（5 个 Darwin SKIP） |
| `make selfhost-native` | 全绿：cc3→cc4 24 产物固定点、自解析 104、F1 O0/O2 门、缓存门、项目 105/105 |
| `make test-llvm-linux-arm64` | O0/O2 默认 LLVM + 内嵌 lld + 运行时 + C ABI 全 PASS |
| 独立 O2 连续自编 B/C | SHA-256 `dbd418f4…` 完全相同 |
| 默认 LLVM 空 PATH 编译/链接/运行 | 通过（不使用宿主 gcc） |

种子滚动：`bin/yh-linux-arm64` = 新默认 LLVM 编译器，
SHA-256 `4d13e297547bf3616ab75464e34bd8c18d2ca6f758b83dc41703f9322e087b9a`
（141,752,552 B），`.sha256` 已同步。种子内无 `/work/tmp` 或 llvm-migration 构建路径。

### 剩余边界

- 旧后端仍保留为其他平台/显式 `--backend legacy` 的过渡路径；全局删除属 LL12。
- `linux-arm64` CI 已加入固定 arm64 LLVM/lld 宿主缓存、`YH_LLVM_HOST=1` 与
  `libxml2-dev`；`make selfhost-native` 内含 F1 运行时门。
- x64 专用 `tests/selfhost/llvm-selfhost.py` 仍固定 x86_64；Linux/AArch64 的
  正式自举门由 `native-selfhost.py` 覆盖。
