# yh

极简 yh 语言编译器。用户源文件唯一使用 `.yh` 后缀；

## 开发策略（必须遵守）

**0.0.3 起仓库已删除 src/（C 版 stage0）与 bootstrap/，进入滚动自举**：
编译器源码在 `compiler/`（gen/proj/lex/parse/ast/check/comptime/builtin/ir/
backend/lower/link/build/testkit/cmd 十五个模块的 project.toml 项目；`build` 是
构建引擎，`proj` 是项目模型/目标与产物路径，`link` 是工具链调用层（汇编/链接/
lld/进程/时钟），`lower` 是受检快照 → IR，`testkit` 是语言内测试执行器，
`cmd` 只剩参数映射与调用面），
构建只依赖**宿主平台对应的种子**，种子统一按 `yh-<平台>-<架构>` 命名：
macOS/arm64 用 `bin/yh-darwin-arm64`（Mach-O，SHA-256 见
`bin/yh-darwin-arm64.sha256`），Linux/aarch64 用 `bin/yh-linux-arm64`（ELF，
SHA-256 见 `bin/yh-linux-arm64.sha256`）；Linux/x86_64 用
`bin/yh-linux-x64`。**种子不入库**（2026-10-21 起，仓库不再使用 Git LFS）：
克隆后首次构建前执行 `just fetch-seed`，从最新 GitHub Release 下载到被
gitignore 的 `bin/` 并核对哈希。

- **构建入口是 just**（`justfile` 是唯一真源，仓库已无 `Makefile`；
  `just --list` 列出全部目标与说明）。
  日常构建：`just`（= 宿主种子对 `compiler/` 项目 `yh build`，冷编，
  产出根目录 `yh`）；日常验证以 `just selfhost-native` 为主门
  （两代模块固定点 + 自解析 + 全量语法/运行语料 + modules/项目验收）。
- 滚种子：`just test` 与 `just selfhost-native` 全绿后执行 `just seed`
  （把新 yh 覆盖到 `bin/yh-<平台>-<架构>` 并更新哈希）。源码无法在仓库内独立
  重建编译器，正确性由固定点与语料门保证，git 历史保留每一代种子。
- stage0 的差分参照与 `-run`/交叉 ELF 能力随删除终结；Linux/aarch64 ELF
  种子已入库（2026-10-09，`bin/yh-linux-arm64`），Linux 上可直接
  `just`/`just test`/`just selfhost-native`；Linux CI 流程按需重建。
  需要 Linux 环境验证时优先用容器而非虚拟机，见下文
  《Linux 环境验证（容器方案）》。
- 自举侧新增/修改行为时，须在 `tests/yh-run/` 或 `tests/modules/`
  新增 `.yh` 用例并运行 `just`。决策依据见 ADR-0006/0007。
- **模块导出面**：只导出别的模块真的使用的声明（`pub` 同时决定 `.s.i` 接口
  与 `.globl`）；仅模块内使用的 `fn`/`const` 不写 `pub`，入口 `cmd/` 只保留
  `main`。跨模块可变状态经 `pub fn` 访问（B1 后的窄口：`gen.task()` 每任务状态、
  `gen.stats()` 统计、`proj.ctx()`/`proj.cfg()` 项目与目标；`gen.G()` 已删除）。
- **模块私有类型**（2026-10-12，ADR-0013）：`struct`/`union`/`enum` 的 `pub`
  可选，不带 `pub` 即模块私有（不进 `.s.i`、跨模块不可命名），且不得出现在
  本模块的 `pub` 签名、`pub` 字段或 `pub` 别名里。
- **平台顺序（2026-10-12 用户决定）：开发与验证以 Linux 平台为先**，
  macOS/Windows 等其他平台后续接入；非 Linux 目标不因日常改动回归验收，
  但 Linux 上的 `just test` / `just selfhost-native` 与滚种子照常执行。
  **2026-10-19（F2-10）**：macOS/ARM64 默认后端已切 LLVM（Darwin 种子
  `bin/yh-darwin-arm64` 含固定桥）。
  **2026-10-20（F1）**：Linux/AArch64 默认后端也已切 LLVM，内嵌 lld 与
  固定桥随种子分发；`just test` / `just selfhost-native` 默认走 LLVM，
  O0/O2 与连续自编固定点通过，种子已滚为 `bin/yh-linux-arm64`。
  性能项（RS2/RS3/R2c、20 轮对照）后置，不据此宣称首个完整 SSA 版本完成。
  **2026-10-21（LL12）**：旧机器发射已彻底退役（`emit_arm64`/旧 arm64 后端/
  四缓冲/旧 SSA 替换链/C ABI 发射层删除，`compiler/` 净减 6516 行），
  `--backend legacy` 拒绝执行，LLVM 是唯一代码生成后端；证据见
  `docs/01-finished/yh-LL12退役旧机器发射-2026-10-21.md`。
  **Darwin SDK stub**：`compiler/darwin-sdk/` 随编译器分发（Zig 式，
  SDK 26.4）；链接查找 `SDKROOT` → `YH_DARWIN_SDK` → 可执行文件附近 bundle →
  原生 `xcrun`。C 源/libc++/目标包/frameworks 等遗留见
  `docs/03-design/yh-Darwin交叉编译遗留边界.md`。
  **libc++ 进闭包（2026-10-25）**：`just llvm-host` 会把宿主 SDK 的
  `libc++.tbd` 复制进构建机闭包并经 `tools/link-closure.py` 写进
  `compiler/project.toml` 的 `[link-darwin-arm64].cxx`，因此
  `cd compiler && ../bin/yh-darwin-arm64 build`（不设 `SDKROOT`、不设
  `YH_LINK_RUNTIME_FLAGS`）可以独立链接；标准构建仍走 `just`。
- **本地/CI 分工（2026-10-19 用户决定，2026-10-22 调整）**：在 Linux 或 macOS 上开发，
  本地只需保证**本平台**门禁绿（`just test` + `just selfhost-native`；运行语料已按
  `// platform:` 头部指令筛选，平台专属门如 `just test-llvm` 在别的宿主会
  明确拒绝而不是要求本地跑通）。**完整多平台回归由 Gitea Actions 承担**
  （见下文 CI 说明）：推送 `arm64`/`llvm`/`main` 自动跑
  linux-arm64（主门）与 darwin-arm64；linux-x86_64（LLVM 全门）只在 tag 发布时跑；
  **tag 发布同样由 Gitea Actions 的 `release.yml` 承担**。GitHub Actions 已于
  2026-10-21 移除（`.github/workflows/` 删除，需要时从 git 历史还原）。
  本地不要为其他平台预跑门禁，也不要因 CI 红灯阻塞本地迭代——CI 红灯按
  todo 立项再修。`just libs-test`（libs 全部测试）是 CI 的独立阶段；改到
  标准库时建议本地顺带跑一次，但日常主门仍是 `just test` +
  `just selfhost-native`。

## 修改语法规则

1. 修改docs/yh.g4 分析语法的合理性，不允许存在歧义
2. 制定修改计划
3. tests目录添加测试用例
4. 开发确保测试用例全部通过
5. 刷新docs 下的所有文档

## 目录

- `compiler/` —— 编译器源码（gen/lex/parse/ast/comptime/cmd/ir/backend 多模块的项目）
- `bin/` —— 种子目录（**不入库**，`just fetch-seed` 从最新 Release 下载
  `yh-<平台>-<架构>` 与哈希）
- `docs/03-design/` 语法设计、`docs/02-plan/` 计划、`docs/01-finished/` 完成、
  `docs/adr/` 决策、`docs/finish.md` 完成流水、`docs/todo.md` 待办
  - `docs/finish.md` 只保留最近三天条目（靠前为最新）；更早条目归档到
    `docs/01-finished/finish-历史归档-<起>至<止>.md`，新增条目写在最前。
- `tests/yh/` 语法语料、`tests/yh-run/` 语义运行语料、
  `tests/modules/` 模块语料与项目验收、`tests/selfhost/` 自举探针
- `tools/` 门禁脚本与 yh-explorer
- `tmp/` 全部临时产物（已 gitignore）

## 编译流程

1. 宿主平台种子（macOS/arm64：`bin/yh-darwin-arm64`；Linux/arm64：
   `bin/yh-linux-arm64`）
   对 `compiler/` 执行 `yh build`，冷编产出根 `yh`；x86_64 Linux 宿主无
   x64 后端（`compiler/backend/` 只有 `arm64.yh`），须显式
   `SEED=bin/yh-linux-arm64`（配合 qemu-user/binfmt 模拟 arm64）。
2. 新 `yh` 再自编一次，两次产物的模块 `.s`/`.s.i` 必须逐字节相同（固定点）；
3. `just seed` 把验证过的 `yh` 覆盖回宿主平台种子（Linux 上为
   `bin/yh-linux-arm64`），进入下一代。

Darwin/ARM64 与 Linux/AArch64 自举闭包（2026-10-20 起，Zig 式）：
LLVM/lld/桥的归档参数不再烘焙进种子，而由构建机提供 —— 首次执行
`just bootstrap`（= 幂等 `just llvm-host` + 冷编；`just llvm-host` 单独只准备闭包）
生成 `tmp/llvm-migration/llvm-host-<宿主>/selfhost-flags.txt`，
`just`/`just seed` 经 `YH_LLVM_SELFHOST_FLAGS` 传给种子；换机器或 worktree
只需重新 bootstrap/llvm-host。固定 SDK 就绪后 justfile 自动导出 `SDKROOT`
（显式 SDKROOT 仍优先），`just test`/`just selfhost-native` 不再要求手工导出；
SDK 27 的 `arm64e.x1` TAPI 会被 `tools/llvm-darwin-sdk.py` 在解析期拒绝并提示
用 26.x（内嵌 lld 21 尚不支持）。`YH_LLVM_HOST=0` 只表示不准备固定闭包，
新种子会在链接阶段明确报缺少闭包。`just seed` 会拒绝仍带构建机 `$HOME`
路径的种子。

## 使用

```bash
just
```

常用命令：

```bash
./yh build                 # 构建当前项目（产物名取 project.name）
./yh run                   # 构建并运行 main 模块
./yh version               # 项目名与版本
./yh list [--resolve name] # 列出模块/解释导入绑定
./yh test --list           # 只列出测试身份与文档目标
./yh test                  # 发现、构建并逐例执行测试
./yh test --no-run         # 只构建测试对象与入口，不链接/不执行
./yh test --filter X --timeout 15  # 只跑身份含 X 的用例，单例超时 15 秒
./yh --syntax-check f.yh   # 只做词法/语法检查
./yh --emit-asm f.yh       # 发射汇编
./yh f.yh -o out           # 单文件编译并链接
```

## 构建与测试

```bash
just test               # 三层回归：ANTLR 语法 + 编译器语法模式 + 运行语义
just bootstrap          # 首次/换机：准备固定 LLVM 闭包后冷编（一条命令，幂等）
just selfhost-native    # 主门：两代固定点 + 自解析 + 全量语料 + 模块/项目验收
just llvm-host          # 只准备本机固定 LLVM 闭包（不编编译器）
just fetch-seed         # 从最新 GitHub Release 取本机平台种子（x64 首次构建前）
just code-stats         # 统计 compiler/ 下 yh 源码规模
just test-code-stats    # 运行统计工具边界与 JSON 检查
just test-lib-tests     # 历史别名，等价于 just libs-test
just libs-test          # libs 自有测试（test 块 + cli/os/libc 外部 runner；CI 独立阶段）
just libs-test-o2       # 同一批 test 块在 tmp/libs-o2 副本上以 O2 重跑
just test-compiler-tests # compiler/ 内嵌 yh test 测试（需种子支持 test 语法）
just test-llvm-linux-arm64  # F1：Linux/AArch64 LLVM 运行时/C ABI/O0-O2（容器内）
just seed               # 滚种子（仅在全绿后；拒绝带构建机路径的种子）
```

`just test` 只跑「共有 + 本平台」的用例：运行语料用头部指令 `// platform: <tag>`
标注平台专属项（`linux`、`linux-x64`、`darwin-arm64` 等，`<os>` 匹配该 OS 的
所有架构），不匹配的记 `SKIP`、不算失败也不影响退出码；没有该指令的是共有用例。
`just test-llvm` 是 Linux/x86_64 专属门，其他宿主会直接拒绝而不是降级运行。

CI 由 **Gitea Actions** 承担（2026-10-22 起；替代原 CircleCI 分支门与本机 Jenkins）：

- **仓库与 runner**：`http://localhost:3000/yh/yh`，runner 是 `gitea-runner` 5.2 的
  **host 模式**实例 `yh-local`（labels `macos-arm64` / `linux-arm64`，宿主为
  macOS/arm64）。本机无 docker，workflow 里不用 `container:` 语法；Linux 任务由
  脚本自行调 Apple `container`。
- **`ci.yml`（分支门）**：`arm64`/`llvm`/`main` 与 `<ver>-rc`/`<ver>-release`
  分支 push → 并行跑 Darwin/arm64（宿主原生）、Linux/AArch64（Apple
  container 内原生）、Linux/x86_64（Apple container 内模拟）；每端先取最新
  Release 种子，再 `just bootstrap`、平台专项门、第 2/3 层语料与
  `just SKIP_CORPUS=1 selfhost-native`。**ANTLR 参考语法门只在本地开发跑**
  （`just test` / `just quick`），CI 不为它装 Java + jar，只用编译器的
  `--syntax-check` 模式（2026-10-26 用户决定）。
- **`release.yml`（发布）**：版本 tag（`x.y.z`、`x.y.z-rc.N`）push → 三端顺序
  构建（Darwin 原生 → Linux/AArch64 容器原生 → Linux/x86_64 容器模拟）、cc4 打包、
  `tools/publish-release.py` 发布 GitHub Release；其他 tag（如 `seed-*`）跳过。
- **凭据**：仓库 secret `YH_GITHUB_TOKEN`（取种与发布）。取种脚本必须显式
  `--repo lalavender/x`——Gitea 会把 `GITHUB_REPOSITORY` 覆写成 `yh/yh`。
- **缓存**：host 模式直接复用宿主 `$YH_LLVM_CACHE`（缺省
  `$HOME/Documents/x/tmp/llvm-migration`）并 symlink 进 workspace；**不要删这个
  目录**，只清理 `tmp/` 里其他旧产物，否则首次 `just bootstrap` 会重新准备
  LLVM 闭包。
- **磁盘**：完整三端约需 15–20 GB；x86_64 是容器模拟，不能等同原生 CI 证据。
- **已退役**：GitHub Actions（2026-10-21 删除）、本机 Jenkins（2026-10-22 删除，
  `Jenkinsfile` 与 `tools/jenkins/` 一并移除，发布脚本改为
  `tools/publish-release.py`）；`.circleci/config.yml` 仅留作云端真机参照，不再
  作为门禁。

## 版本与发布（每版本 rc/release 分支）

每个版本两条分支：`<ver>-rc` 是开发与候选线；`<ver>-release` 只收合并、不含直接
提交。`compiler/project.toml` 的 `version` 在 rc 期就写目标正式号，因此最后一个
rc 与正式版是同一提交。完整方案见
[分版本 rc/release 分支发版流程](docs/02-plan/yh-分版本rc与release分支发版流程方案-2026-10-21.md)。

**当前状态（2026-10-22）**：tag 发布已由 Gitea Actions 的 `release.yml` 承担；
rc/prerelease 与正式 tag 的 `<ver>-release` 祖先校验尚未落地（R1–R3/R5 未
关闭），本节描述的是目标流程。

1. 在 `<ver>-rc` 上开发；写 `docs/01-finished/release-<ver>-rc.N.md`；本地
   `just test` + `just selfhost-native` 全绿。
2. 打 `git tag -a <ver>-rc.N` → 三端 tag 流水线构建并发布 prerelease Release
   （带三端种子资产）。非版本号 tag 不触发发布。
3. **用发布出去的 rc 二进制验收**：`rm -rf bin && just fetch-seed` → `just` →
   `just test` → `just selfhost-native`（两代固定点）。
4. 验收不过就回 `<ver>-rc` 修，打下一个 rc（种子自动取上一个 rc）。
5. `git merge --no-ff <ver>-rc` 到 `<ver>-release`，再打 `git tag -a <ver>`
   发正式版；正式 tag 必须落在 `<ver>-release` 上（CI 校验），否则拒绝发布。
6. 发完删 `<ver>-rc`、保留 `<ver>-release`；默认分支为最新 `<ver>-release`。

种子规则：分支与 tag 流水线一律取**最新带资产的 Release（含 rc，排除当前 tag）**，
所以 rc.N 用 rc.N−1、正式版用该版最后一个 rc 编译出来。禁止修改已发布 Release
的资产（要改就发新 rc）；`release-<tag>.md` 缺失即发布失败（rc 与正式都要写）。

迁移完成前（[todo](docs/todo.md) R1–R5 未关闭），分支门仍跑
`arm64`/`llvm`/`main`；`<ver>-rc`/`<ver>-release` 分支同样触发。


## Linux 环境验证（容器方案）

需要 Linux 环境做测试/验证时（如验证 ELF 产物、预演 Linux CI、
将来用 ELF 种子在 Linux 上自举），**优先使用容器，不搭完整虚拟机**：
容器秒级启停、可直接挂载本仓库，日常验证不需要 VM 的完整内核与桌面。

### 前提事实（先读再动手）

- 入库种子按平台分文件：`bin/yh-darwin-arm64` 是 **darwin/arm64（Mach-O）**，不能
  在 Linux 里运行（`Exec format error`）；`bin/yh-linux-arm64` 是
  **linux/aarch64（ELF）**，2026-10-09 入库，Linux 容器/宿主内可直接跑
  `yh build` 与自举门。
- `just`（justfile）按宿主自动选种子：Linux/arm64 宿主取 `bin/yh-linux-arm64`；
  **x86_64 Linux 宿主没有 x64 种子**（x64 后端未实施），须显式
  `SEED=bin/yh-linux-arm64`（arm64 容器原生跑，或 x86_64 上配
  qemu-user/binfmt 执行 arm64 ELF）。产物形态随宿主（Darwin →
  Mach-O，Linux → ELF）。
- 宿主是 Apple Silicon（darwin/arm64），系统 container 默认
  arch=arm64 / os=linux，直接用 alpine/debian 等多架构 OCI 镜像即可，
  原生 arm64 无模拟、性能接近原生；不要切 x86_64 走 Rosetta/qemu。

### 操作方式

容器运行时用 **macOS 系统自带 `container`（Apple Container），
不用 docker**（下述命令已实测通过）：

```bash
# 服务未运行时先启动；若 run 长时间卡在 "Starting container"
# 后报 XPC timeout，先 stop 再 start 重启服务（实测有效）
container system start

# 进入一次性 arm64 Linux 容器，仓库整体挂载到 /work（首次拉取镜像需网络）
container run --rm -it -v "$PWD":/work -w /work alpine:latest sh

# 容器内一次性装齐门禁所需工具（python3 跑门禁脚本，cc/ld 供链接）
apk add python3 build-base libxml2-dev   # alpine；用 debian 镜像则：
apt-get update && apt-get install -y python3 build-essential libxml2-dev
```

故障处理：卡死的容器用 `container ls -a` 查看、
`container rm --force <id>` 清理；服务异常看 `container system logs`。

Linux/arm64 容器内的自举验证（种子已入库；arm64 原生宿主缺省即选
`bin/yh-linux-arm64`，无需覆盖）：

```bash
just test
just selfhost-native
# x86_64 宿主/CI 的等价形式（配 qemu-user/binfmt 后）：
SEED=bin/yh-linux-arm64 just test
SEED=bin/yh-linux-arm64 just selfhost-native
```

### 容器内验证的约束

- 挂载目录的文件属主是宿主用户：容器内只做构建/测试，不做
  `chown`/权限改写；容器内生成的临时产物一律放 `tmp/`，验证完清理。
- **不要**把容器内编出的 yh 覆盖回 `bin/` 种子；滚种子只在本机
  `just test` 与 `just selfhost-native` 全绿后执行 `just seed`。
- 容器内验证结论（命令、镜像、结果）记入 `docs/finish.md`；
  若发现 Linux 特有问题，先在 `docs/todo.md` 立项再修。

### WSL（Windows 宿主）验证

Windows 宿主按仓库规则在 WSL 内构建/验证（本机为 Ubuntu x86_64 +
qemu-user/binfmt，交叉 gcc 包装在 `tmp/boot/crossbin/gcc`）：

```bash
export PATH="$PWD/tmp/boot/crossbin:$PATH"   # gcc → aarch64-linux-gnu-gcc
export SEED=bin/yh-linux-arm64              # x86_64 宿主没有 x64 种子
just
just test
just selfhost-native
# 滚种子：x86_64 宿主必须显式 SEED_DEST，否则会写到 bin/yh-linux-x64
SEED=bin/yh-linux-arm64 SEED_DEST=bin/yh-linux-arm64 just seed
```

## 代码规范

- 结构体和函数都要有详细注释说明
- 每个文件尽量保持在 500-1000 行
- 修改完代码都要构建验证
- 每次修改代码完成之后都要在tests目录中生成.yh测试用例，并确保测试通过
- Windows平台执行切换到wsl进行运行
- 安装ripgrep，使用ripgrep进行搜索
- 必须执行
- 用中文回答，如果是代码用中文注释
- 计划的任务记录在docs/todo.md
- 完成的任务记录在docs/finish.md
- 每次修改完代码都要构建验证
- 每个文件尽量保持在500-1000行
- 结构体和函数都要有详细注释说明
- 语法设计文档放在 docs/03-design/
- 计划任务文档放在 docs/02-plan/
- 完成任务文档放在 docs/01-finished/
- 所有临时文件都放到tmp/目录

## 编码要求

1. 编码前先思考
不要假设。不要隐藏困惑。暴露权衡。

在实现之前： 明确表达你的假设。不确定就问。 如果存在多种解读，展示出来——不要默默选一个。 如果存在更简单的方案，说出来。该反对时就反对。 如果有什么不清楚，停下来。说清楚哪里令人困惑。提问。

2. 简洁优先
解决问题的最少代码。不写投机性代码。

不做超出需求的功能。 一次性代码不做抽象。 没有要求就不加"灵活性"或"可配置性"。 不为不可能的场景做错误处理。 如果你写了 200 行而本来 50 行就够，就重写。 问问自己："一个资深工程师会说这过于复杂吗？"如果是，就简化。

3. 精准修改
只动该动的。只清理自己造成的垃圾。

编辑已有代码时： 不要"顺手改进"相邻的代码、注释或格式。 不要重构没坏的东西。 匹配现有风格，即使你会用不同的方式写。 发现无关的死代码，提一下就好——不要删。

当你的改动产生了孤立代码时： 移除因为你的改动而变得无用的 import/变量/函数。 不要删除改动之前就已存在的死代码，除非被要求。 检验标准：每一行变更都应该能直接追溯到用户的请求。

4. 目标驱动执行
定义成功标准。循环直到验证通过。

将任务转化为可验证的目标：

"添加验证" → "为无效输入编写测试，然后让测试通过" "修复这个 bug" → "编写复现 bug 的测试，然后让测试通过" "重构 X" → "确保重构前后测试都能通过" 对于多步骤任务，写一个简短的计划：

[步骤] → 验证：[检查项]
[步骤] → 验证：[检查项]
[步骤] → 验证：[检查项] 强有力的成功标准让你可以自主循环。模糊的标准（"让它能跑"）需要不断澄清。
准则在起效的表现： diff 中不必要的改动更少，因过度复杂而返工更少，澄清问题出现在实现之前而非犯错之后。
