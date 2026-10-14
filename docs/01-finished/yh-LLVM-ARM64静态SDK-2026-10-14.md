# LLVM ARM64 启动 SDK 与源级桥完成

用户授权多 agent 后，SDK 独立切片与 CheckedModule、IRModule 同时实施。
LLVM 桥的运行架构以 --host 明确选择，不与 LLVM 发射目标混淆；Linux/x64 上
用固定 /usr/bin/aarch64-linux-gnu-gcc/g++/ar 构建 ARM 桥。系统只增加普通交叉
C++ 编译器，LLVM 和普通 zlib/zstd 静态归档按固定发行包提取到仓库 tmp。

ARM LLVM 21.1.8 包 SHA-256 为
8210ff444cdf2d17881946f1e102ff598c2dec53eb267a346c5ddb216cd94d5b；zlib 为
615f56af8d2f5d273c08eeb7bc95f491ccef52ce1562522567a11e58b60bb2e3；zstd 为
1470defbf4b00adb8ad815dfac33a97d82dc2659ec05ce4e6d7425aec409efeb。
包实际提供的归档与三份许可证逐次确认，配置记录包、清单、桥源码/头文件/归档身份。

真实最终门（WSL root）：

```bash
python3 tests/selfhost/llvm-embedded-arm64.py --chroot --compiler-path ./yh
python3 tests/selfhost/llvm-embedded.py --chroot
```

两者退出 0；ARM 验收 O0/O2、EM_AARCH64/EM_X86_64 对象及汇编、ARM 目标执行、
8 类拒绝、原子失败与原有产物保护、错误架构链接和损坏缓存包拒绝。ARM ELF 仅
动态依赖 libm.so.6、libc.so.6、ld-linux-aarch64.so.1，最高要求 GLIBC_2.38；没有
LLVM/Clang/C++/gcc 支持库动态依赖。SDK 并非全 OS 静态，发行仍需披露普通 OS 依赖。

新增 .yh 调用者在 ARM 旧后端编译后静态链接 LLVM，八个参数按现行 C ABI 调用桥，
成功发射 x64 对象并在 WSL 原生执行。该结果验证源级入口与 yh 运行时，不能代替
生产编译器的前端 lowering、LLVM 全覆盖和自举门。

独立 reviewer 找到旧 chroot 根复用的潜在假绿机制，未发现旧实际根受到污染；
两架构测试均修为每次 TemporaryDirectory 空根再复制明确依赖，修复后重新通过。
机器报告位于 tmp/llvm-migration/arm-sdk/embedded/report.json；最终日志为
ll0e-arm-final-fresh.log/.exit 与 ll0e-x64-final-fresh.log/.exit。
普通编译器基线已在 LL2-T 完整 make/test/selfhost 验收，本片专注桥/SDK，不修改种子。
