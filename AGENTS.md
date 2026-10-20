# yh

极简 yh 语言编译器。用户源文件唯一使用 `.yh` 后缀；

## 开发策略（必须遵守）

**0.0.3 起仓库已删除 src/（C 版 stage0）与 bootstrap/，进入滚动自举**：
编译器源码在 `compiler/`（gen/lex/parse/ast/comptime/cmd/ir/backend
多模块的 project.toml 项目），
构建只依赖**宿主平台对应的入库种子**，种子统一按 `yh-<平台>-<架构>` 命名：
macOS/arm64 用 `bin/yh-darwin-arm64`（Mach-O，SHA-256 见
`bin/yh-darwin-arm64.sha256`），Linux/aarch64 用 `bin/yh-linux-arm64`（ELF，
SHA-256 见 `bin/yh-linux-arm64.sha256`）；Makefile 按宿主自动选择。
Linux/AArch64 种子因内嵌 LLVM/lld 超过 GitHub 100 MB 单文件限制，使用 Git LFS
跟踪；克隆后需执行 `git lfs pull`，否则 `bin/yh-linux-arm64` 只是指针文件。

- 日常构建：`make`（= 宿主种子对 `compiler/` 项目 `yh build`，冷编，
  产出根目录 `yh`）；日常验证以 `make selfhost-native` 为主门
  （两代模块固定点 + 自解析 + 全量语法/运行语料 + modules/项目验收）。
- 滚种子：`make test` 与 `make selfhost-native` 全绿后执行 `make seed`
  （把新 yh 覆盖到 `bin/yh-<平台>-<架构>` 并更新哈希）。源码无法在仓库内独立
  重建编译器，正确性由固定点与语料门保证，git 历史保留每一代种子。
- stage0 的差分参照与 `-run`/交叉 ELF 能力随删除终结；Linux/aarch64 ELF
  种子已入库（2026-10-09，`bin/yh-linux-arm64`），Linux 上可直接
  `make`/`make test`/`make selfhost-native`；Linux CI 流程按需重建。
  需要 Linux 环境验证时优先用容器而非虚拟机，见下文
  《Linux 环境验证（容器方案）》。
- 自举侧新增/修改行为时，须在 `tests/yh-run/` 或 `tests/modules/`
  新增 `.yh` 用例并运行 `make`。决策依据见 ADR-0006/0007。
- **模块导出面**：只导出别的模块真的使用的声明（`pub` 同时决定 `.s.i` 接口
  与 `.globl`）；仅模块内使用的 `fn`/`const` 不写 `pub`，入口 `cmd/` 只保留
  `main`。跨模块可变状态经 `pub fn` 访问（`gen.G()` 模式）。
- **模块私有类型**（2026-10-12，ADR-0013）：`struct`/`union`/`enum` 的 `pub`
  可选，不带 `pub` 即模块私有（不进 `.s.i`、跨模块不可命名），且不得出现在
  本模块的 `pub` 签名、`pub` 字段或 `pub` 别名里。
- **平台顺序（2026-10-12 用户决定）：开发与验证以 Linux 平台为先**，
  macOS/Windows 等其他平台后续接入；非 Linux 目标不因日常改动回归验收，
  但 Linux 上的 `make test` / `make selfhost-native` 与滚种子照常执行。
  **2026-10-19（F2-10）**：macOS/ARM64 默认后端已切 LLVM（Darwin 种子
  `bin/yh-darwin-arm64` 含固定桥）。
  **2026-10-20（F1）**：Linux/AArch64 默认后端也已切 LLVM，内嵌 lld 与
  固定桥随种子分发；`make test` / `make selfhost-native` 默认走 LLVM，
  O0/O2 与连续自编固定点通过，种子已滚为 `bin/yh-linux-arm64`。
  性能项（RS2/RS3/R2c、20 轮对照）后置，不据此宣称首个完整 SSA 版本完成。
  **Darwin SDK stub**：`compiler/darwin-sdk/` 随编译器分发（Zig 式，
  SDK 26.4）；链接查找 `SDKROOT` → `YH_DARWIN_SDK` → 可执行文件附近 bundle →
  原生 `xcrun`。C 源/libc++/目标包/frameworks 等遗留见
  `docs/03-design/yh-Darwin交叉编译遗留边界.md`。
- **本地/CI 分工（2026-10-19 用户决定）**：在 Linux 或 macOS 上开发，本地只需
  保证**本平台**门禁绿（`make test` + `make selfhost-native`；运行语料已按
  `// platform:` 头部指令筛选，平台专属门如 `make test-llvm` 在别的宿主会
  明确拒绝而不是要求本地跑通）。**完整多平台回归由 GitHub Actions 承担**
  （见下文 CI 说明）：推送 `arm64`/`llvm`/`main` 自动跑 linux-arm64（主门）
  与 linux-x86_64（YH_LLVM_HOST=1 的 LLVM 全门），
  darwin-arm64 由手动 `workflow_dispatch` 触发。本地不要为其他平台预跑门禁，
  也不要因 CI 平台的红灯阻塞本地迭代——CI 红灯按 todo 立项再修。

## 修改语法规则

1. 修改docs/yh.g4 分析语法的合理性，不允许存在歧义
2. 制定修改计划
3. tests目录添加测试用例
4. 开发确保测试用例全部通过
5. 刷新docs 下的所有文档

## 目录

- `compiler/` —— 编译器源码（gen/lex/parse/ast/comptime/cmd/ir/backend 多模块的项目）
- `bin/yh-darwin-arm64` + `bin/yh-darwin-arm64.sha256` —— 入库种子与哈希（Darwin/arm64）
- `bin/yh-linux-arm64` + `bin/yh-linux-arm64.sha256` —— Linux/aarch64 入库种子与哈希
- `docs/03-design/` 语法设计、`docs/02-plan/` 计划、`docs/01-finished/` 完成、
  `docs/adr/` 决策、`docs/finish.md` 完成流水、`docs/todo.md` 待办
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
3. `make seed` 把验证过的 `yh` 覆盖回宿主平台种子（Linux 上为
   `bin/yh-linux-arm64`），进入下一代。

Darwin/ARM64 与 Linux/AArch64 自举闭包（2026-10-20 起，Zig 式）：
LLVM/lld/桥的归档参数不再烘焙进种子，而由构建机提供 —— 首次执行
`make bootstrap`（= 幂等 `make llvm-host` + 冷编；`make llvm-host` 单独只准备闭包）
生成 `tmp/llvm-migration/llvm-host-<宿主>/selfhost-flags.txt`，
`make`/`make seed` 经 `YH_LLVM_SELFHOST_FLAGS` 传给种子；换机器或 worktree
只需重新 bootstrap/llvm-host。固定 SDK 就绪后 Makefile 自动导出 `SDKROOT`
（显式 SDKROOT 仍优先），`make test`/`make selfhost-native` 不再要求手工导出；
SDK 27 的 `arm64e.x1` TAPI 会被 `tools/llvm-darwin-sdk.py` 在解析期拒绝并提示
用 26.x（内嵌 lld 21 尚不支持）。`YH_LLVM_HOST=0` 只表示不准备固定闭包，
新种子会在链接阶段明确报缺少闭包。`make seed` 会拒绝仍带构建机 `$HOME`
路径的种子。

## 使用

```bash
make
```

常用命令：

```bash
./yh build                 # 构建当前项目（产物名取 project.name）
./yh run                   # 构建并运行 main 模块
./yh version               # 项目名与版本
./yh list [--resolve name] # 列出模块/解释导入绑定
./yh --syntax-check f.yh   # 只做词法/语法检查
./yh --emit-asm f.yh       # 发射汇编
./yh f.yh -o out           # 单文件编译并链接
```

## 构建与测试

```bash
make test               # 三层回归：ANTLR 语法 + 编译器语法模式 + 运行语义
make bootstrap          # 首次/换机：准备固定 LLVM 闭包后冷编（一条命令，幂等）
make selfhost-native    # 主门：两代固定点 + 自解析 + 全量语料 + 模块/项目验收
make llvm-host          # 只准备本机固定 LLVM 闭包（不编编译器）
make code-stats         # 统计 compiler/ 下 yh 源码规模
make test-code-stats    # 运行统计工具边界与 JSON 检查
make test-llvm-linux-arm64  # F1：Linux/AArch64 LLVM 运行时/C ABI/O0-O2（容器内）
make seed               # 滚种子（仅在全绿后；拒绝带构建机路径的种子）
```

`make test` 只跑「共有 + 本平台」的用例：运行语料用头部指令 `// platform: <tag>`
标注平台专属项（`linux`、`linux-x64`、`darwin-arm64` 等，`<os>` 匹配该 OS 的
所有架构），不匹配的记 `SKIP`、不算失败也不影响退出码；没有该指令的是共有用例。
`make test-llvm` 是 Linux/x86_64 专属门，其他宿主会直接拒绝而不是降级运行。

GitHub Actions（`.github/workflows/ci.yml`，手动 `workflow_dispatch` 或推送
`arm64`/`llvm`/`main`）：`linux-arm64` 作业在 arm64 容器里跑第 2/3 层语料与
`make selfhost-native`（第 1 层 ANTLR 需要 Java 与 jar 缓存，不在 CI 跑）；
`linux-x86_64` 作业以 `YH_LLVM_HOST=1` 联网准备固定 LLVM SDK（缓存在
`tmp/llvm-migration`，键随 SDK 锁文件与桥源码变化）后跑 `make test-llvm` /
`make selfhost-llvm`；`darwin-arm64` 作业在 `macos-14` 上跑同一套门禁，入库
`bin/yh-darwin-arm64` 落后时先自动补一代种子（把模块私有类型临时改回 `pub` →
`make` → `make seed` → 还原源码），并把 `bin/yh-darwin-arm64` + `.sha256`
作为 artifact 上传——下载后提交即追平 macOS 种子。


## Linux 环境验证（容器方案）

需要 Linux 环境做测试/验证时（如验证 ELF 产物、预演 Linux CI、
将来用 ELF 种子在 Linux 上自举），**优先使用容器，不搭完整虚拟机**：
容器秒级启停、可直接挂载本仓库，日常验证不需要 VM 的完整内核与桌面。

### 前提事实（先读再动手）

- 入库种子按平台分文件：`bin/yh-darwin-arm64` 是 **darwin/arm64（Mach-O）**，不能
  在 Linux 里运行（`Exec format error`）；`bin/yh-linux-arm64` 是
  **linux/aarch64（ELF）**，2026-10-09 入库，Linux 容器/宿主内可直接跑
  `yh build` 与自举门。
- Makefile 按宿主自动选种子：Linux/arm64 宿主取 `bin/yh-linux-arm64`；
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
make test
make selfhost-native
# x86_64 宿主/CI 的等价形式（配 qemu-user/binfmt 后）：
SEED=bin/yh-linux-arm64 make test
SEED=bin/yh-linux-arm64 make selfhost-native
```

### 容器内验证的约束

- 挂载目录的文件属主是宿主用户：容器内只做构建/测试，不做
  `chown`/权限改写；容器内生成的临时产物一律放 `tmp/`，验证完清理。
- **不要**把容器内编出的 yh 覆盖回 `bin/` 种子；滚种子只在本机
  `make test` 与 `make selfhost-native` 全绿后执行 `make seed`。
- 容器内验证结论（命令、镜像、结果）记入 `docs/finish.md`；
  若发现 Linux 特有问题，先在 `docs/todo.md` 立项再修。

### WSL（Windows 宿主）验证

Windows 宿主按仓库规则在 WSL 内构建/验证（本机为 Ubuntu x86_64 +
qemu-user/binfmt，交叉 gcc 包装在 `tmp/boot/crossbin/gcc`）：

```bash
export PATH="$PWD/tmp/boot/crossbin:$PATH"   # gcc → aarch64-linux-gnu-gcc
export SEED=bin/yh-linux-arm64              # x86_64 宿主没有 x64 种子
make
make test
make selfhost-native
# 滚种子：x86_64 宿主必须显式 SEED_DEST，否则会写到 bin/yh-linux-x64
SEED=bin/yh-linux-arm64 SEED_DEST=bin/yh-linux-arm64 make seed
```

## graphify

仓库支持使用 graphify 做依赖和死代码分析：

```bash
GRAPHIFY_OUT=graphify-out graphify update .
GRAPHIFY_OUT=graphify-out graphify god-nodes
```


代码规范
结构体和函数都要有详细注释说明
每个文件尽量保持在 500-1000 行
修改完代码都要构建验证
每次修改代码完成之后都要在tests目录中生成.yh测试用例，并确保测试通过
Windows平台执行切换到wsl进行运行
安装ripgrep，使用ripgrep进行搜索
必须执行
用中文回答，如果是代码用中文注释
计划的任务记录在docs/todo.md
完成的任务记录在docs/finish.md
每次修改完代码都要构建验证
每个文件尽量保持在500-1000行
结构体和函数都要有详细注释说明
语法设计文档放在 docs/03-design/
计划任务文档放在 docs/02-plan/
完成任务文档放在 docs/01-finished/
所有临时文件都放到tmp/目录
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
