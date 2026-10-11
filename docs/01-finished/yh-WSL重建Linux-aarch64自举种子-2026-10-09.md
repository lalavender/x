# WSL 上重建 Linux/aarch64 自举种子链（2026-10-09）

## 背景

本工作区运行在 Windows 上：入库种子 `bin/yh` 是 **darwin/arm64（Mach-O）**，
Windows 与 WSL(x86_64) 都无法执行；0.0.3 删除 `src/`（C 版 stage0）与
`bootstrap/` 之后，仓库内没有可直接运行的 Linux 种子（Linux 版归档尚未发布，
见 AGENTS.md「Linux CI/开发需另行建立」）。

因此先在 WSL 里**沿 git 历史重建一条 Linux/aarch64 种子链**，得到能编译当前
`compiler/` 源码的 AArch64 Linux ELF 种子，作为本机开发与验证的种子。
重建材料全部来自仓库自身的 git 历史，不需要网络下载任何二进制。

## 环境准备（WSL2 Ubuntu，x86_64）

```bash
# 1) 交叉工具链与目标运行时库
apt-get install -y gcc-aarch64-linux-gnu libc6-dev-arm64-cross binutils-aarch64-linux-gnu

# 2) aarch64 ELF 直接执行：qemu-user + binfmt 已具备
cat /proc/sys/fs/binfmt_misc/qemu-aarch64   # enabled，interpreter /usr/bin/qemu-aarch64

# 3) 让 ELF 解释器路径与运行时库可解析（root）
ln -sf /usr/aarch64-linux-gnu/lib/ld-linux-aarch64.so.1 /lib/ld-linux-aarch64.so.1
for f in /usr/aarch64-linux-gnu/lib/*.so*; do ln -sf "$f" /usr/lib/aarch64-linux-gnu/; done

# 4) 交叉 gcc 包装：编译器固定调用 `gcc`（link_cache.yh），本机没有 aarch64 原生 gcc
#    tmp/boot/crossbin/gcc → exec /usr/bin/aarch64-linux-gnu-gcc "$@"
#    链接失败且缺口是 yh 运行时桩 linux_syscall6 时，追加 C 垫片重试（见下）
export PATH=$PWD/tmp/boot/crossbin:$PATH
```

## 重建步骤

### 1. C 版 stage0（0.0.2 时代的 `src/`）

```bash
git archive 21f3edf^ | tar -x -C tmp/boot/stage0     # 21f3edf = 0.0.3 删除 src/ 的提交
cd tmp/boot/stage0
make yh CC=gcc                                       # 宿主编译器：x86_64 上跑，发射 AArch64
make libtcc1.a TARGET_CC=aarch64-linux-gnu-gcc TARGET_AR=/usr/bin/aarch64-linux-gnu-ar
./yh bootstrap/seed/compiler.yh -o ../seed-compiler \
     -sysroot /usr/aarch64-linux-gnu -B ../lib       # 产出 349KB AArch64 ELF 种子
```

`./yh --version` 输出 `yh version 0.0.2 (AArch64 Linux)`。

### 2. 逐代重建（每代用上一代二进制冷编该提交的 `compiler/`）

```
26029c0 → c5eccf0 → ccb243e → dee59f2 → dcfcac1 → 6b0cfd4 → a11b436 → 19e2e3a(HEAD)
```

每步：`git archive <提交> | tar -x -C tmp/boot/chain/<提交>`，然后
`cd tmp/boot/chain/<提交>/compiler && <上一代> build -o ../yh-<提交>`。
单代冷编 6–11 秒（qemu 下），产物为 AArch64 Linux ELF。
（`21f3edf` 与 `8e17bdb` 只改文档，跳过。）

### 3. 过渡补丁（旧种子编不过新源码时的最小放行，均不入仓库）

| 提交 | 新源码依赖 | 种子的过渡处理 |
| --- | --- | --- |
| c5eccf0 | 项目清单已改名 `project.toml` | 0.0.2 种子只认 `mod.toml`，补一份 `entry = "main"` 的过渡清单 |
| ccb243e | 新增 prelude 外部函数（`getpid/rename/usleep/kill/fork/execvp/waitpid/mkdir/clock_gettime/linux_syscall6`） | 在 c5eccf0 源码的 `sem_register_prelude` 里补登记这些符号 |
| ccb243e | 入口签名变为 `(argc, argv, envp)` | 种子的 main 校验放行 `np == 3`（三个参数类型逐项校验） |
| ccb243e | `linux_syscall6` 是 yh 运行时桩（旧种子不发码） | 交叉 gcc 包装在链接失败时追加 C 垫片 `syscall6.c`（`svc #0`）重试 |
| dee59f2 | 字段默认公开，删除了跨模块私有字段检查 | 种子放行该检查 |
| dee59f2 | 类型默认公开（源码不再写 `pub`） | 接口发射不再按 `is_pub` 过滤具名类型 |
| dee59f2 | 接口正文写出跨模块类型的 mangle 名（`IRCall__yh__ir_`） | 依赖接口按**后序**加载：`mb_dep_add_deep` 先登记依赖的依赖，再登记依赖本身 |

最后一条是 dee59f2 之前一直卡住的原因：入口模块 `main` 不直接 `import ir`，
而 `parse` 的接口正文引用了 `ir` 的类型名，加载顺序不对就报
「未知类型（类型必须先定义）」。

### 4. 结果

`tmp/boot/chain/yh-19e2e3a`（1,750,872 字节，AArch64 Linux ELF）= 与 HEAD 源码等价
的编译器；从它开始不再需要任何补丁，后续各代与日常构建都用它作种子。

## 日常使用（本机）

```bash
export PATH=$PWD/tmp/boot/crossbin:$PATH
SEED=$PWD/tmp/boot/chain/yh-19e2e3a
python3 tools/seed-build.py --compiler "$SEED" --project compiler --output ./yh
python3 tests/yh-run/check.py --compiler ./yh
python3 tests/selfhost/native-selfhost.py --seed "$SEED"   # 需要 "$SEED.sha256"
```

`native-selfhost.py` 会用 `verify_seed` 校验种子旁的同名 `.sha256`；
临时种子可自行生成：

```bash
python3 - "$SEED" <<'PY'
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
pathlib.Path(str(p) + ".sha256").write_text(
    f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n")
PY
```

## 入库（同日追加）

最终种子 `yh-19e2e3a` 已入库为 **`bin/yh-linux-arm64`**，并写入
`bin/yh-linux-arm64.sha256`（`137c5fdb…76f2c  yh-linux-arm64`，格式与
`bin/yh.sha256` 一致，`selfhost_snapshot_gate --verify-seed` 通过）。
入库后验证（WSL，x86_64 + qemu-user/binfmt）：

- 用入库种子冷编 `compiler/`：产物与入库前构建**逐字节一致**；
- tests/yh-run **292/292**、语法门正例 **76/76**、反例 **45/45**；
- `make test` / `make selfhost-native`（`SEED=bin/yh-linux-arm64`）：
  结果见 finish.md 同日条目；
- `tools/selfhost_snapshot_gate.py --verify-seed bin/yh-linux-arm64` 通过。

注意：本机 WSL 是 **x86_64**，`uname -m` 使 Makefile 缺省选
`bin/yh-linux-x64`（x64 后端未实施，该种子不存在），因此 x86_64 宿主上
必须显式 `SEED=bin/yh-linux-arm64`；arm64 原生 Linux 宿主/容器缺省即选
`bin/yh-linux-arm64`。

## 边界与注意

- 该链最初是**临时开发种子**；2026-10-09 已把最终种子以 `bin/yh-linux-arm64`
  正式入库。滚种子：Linux 上 `make test` 与 `make selfhost-native` 全绿后
  `make seed`（写入 `bin/yh-linux-arm64` 并更新其哈希）；macOS 上对应
  `bin/yh`。
- `compiler/.build` 缓存由编译器自己维护；跨代重建时每代独立目录，避免缓存串代。
- 入库 Darwin 种子 `bin/yh` 在 Windows/WSL 下仍不可执行（`Exec format
  error`）；x64 后端未实施（`compiler/backend/` 只有 `arm64.yh`）。
  接入 Linux CI（arm64 runner 或容器）时可直接使用 `bin/yh-linux-arm64`，
  本记录的步骤与补丁清单在需要重建/升级 Linux 种子时可复用。
