# --------------------------------------------------------------------------
# yh（玉衡）编译器 —— 自举构建
#
# 编译器就是 yh：由种子 bin/yh-<平台>-<架构>（上一版编译器二进制，不入库，
# 首次 make fetch-seed 下载）对 compiler/
# 多模块项目 yh build 产出，形态随宿主（Darwin → Mach-O，Linux → ELF）。
# 每个版本直接用上一个版本的二进制编译（无 C 编译步骤、无 stage0）：
#   * make            构建 yh（主编译器，项目根目录）
#   * make seed       滚种子：写入当前宿主平台种子并记录 SHA-256
#   * make test       运行 tests/yh 语法语料与编译器模式回归
#   * make selfhost-native  本机全套门（候选两代固定点 + 全量语料，无需容器）
#   * make full       滚种子前的全量门（= test + selfhost-native）
#   * make quick      日常迭代门（ANTLR + 编译器语法语料，约 20s）
#   * make install    安装到 $(PREFIX)（默认 /usr/local；DESTDIR 用作打包根）
#   * make uninstall  卸载
#   * make explorer   启动 yh Compiler Explorer（本地浏览器图形界面）
#   * make llvm-host  准备内嵌静态 LLVM 宿主（LL3；首次需要联网取固定 SDK）
#   * make bootstrap  准备固定 LLVM 宿主后冷编（首次/换机的一条命令）
#   * make clean      清理
#
# 可在命令行覆盖：SEED（编译种子路径）。Linux CI 用匹配架构的 ELF 种子。
#
# 内嵌静态 LLVM（LL3，见 docs/02-plan/yh-LLVM后端替换实施方案.md）：
# 根目录 $(YH) 由种子冷编，最终链接发生在编译器内部（compiler/cmd/
# link_cache.yh 的 mb_link），按目标平台使用 clang/gcc。因此这里让
# tools/seed-build.py 调宿主驱动生成链接包装器目录，并**只对种子构建子进程**
# 前置 PATH/YH_CC：编译（clang/gcc -c）原样透传，最终链接
# 改用固定工具链并追加桥归档与静态 LLVM 参数。链接哪个架构由种子文件名
# 决定（x86_64 宿主上用 bin/yh-linux-arm64 时产物仍是 aarch64 ELF）。
#
#   YH_LLVM_HOST=auto（默认）宿主已准备才链入；缺少固定闭包时打印明确诊断；
#                  Darwin 新种子不再内置闭包路径，自举链接会报「缺少 LLVM 闭包」；
#   YH_LLVM_HOST=1 显式要求：必要时联网准备固定 SDK，准备不了则构建失败；
#   YH_LLVM_HOST=0 关闭（不准备固定闭包；种子无内置闭包时链接会明确报错）。
# 自举闭包由构建机提供：tools/llvm-darwin-host.py prepare 生成的
# selfhost-flags.txt 经 YH_LLVM_SELFHOST_FLAGS 传给种子（Zig 式：闭包路径
# 属于构建环境，不烘焙进种子）。
#
# 旧路径全门（make test / make selfhost-native）在 auto 下必须保持绿；
# YH_LLVM_HOST=0 不准备固定闭包：旧种子仍用自身烘焙路径，新种子会在链接阶段
# 明确报缺少闭包，LLVM 专项门随后失败。
# --------------------------------------------------------------------------

ifndef TOP
 TOP = .
 INCLUDED = no
TOPSRC = $(TOP)

EXESUF =
ifeq ($(shell uname -s),Darwin)
 CONFIG_OSX = yes
endif

PREFIX ?= /usr/local
INSTALL ?= install
BINDIR = $(DESTDIR)$(PREFIX)/bin
HOST_SYSTEM ?= $(shell uname -s)
HOST_ARCH ?= $(shell uname -m)

ifeq ($(HOST_ARCH),aarch64)
 SEED_ARCH = arm64
else ifeq ($(HOST_ARCH),arm64)
 SEED_ARCH = arm64
else ifneq ($(filter x86_64 amd64,$(HOST_ARCH)),)
 SEED_ARCH = x64
else
 SEED_ARCH = $(HOST_ARCH)
endif

# --------------------------------------------------------------------------
# 顶层构建规则
# --------------------------------------------------------------------------

YH = $(TOP)/yh$(EXESUF)
REPO_BIN = $(TOP)/bin
# 入库种子统一按「yh-平台-架构」命名，宿主直接取对应文件：
#   Darwin/arm64 → bin/yh-darwin-arm64，Darwin/x64 → bin/yh-darwin-x64，
#   Linux/arm64  → bin/yh-linux-arm64，Linux/x64  → bin/yh-linux-x64。
# 不再有「macOS/arm64 特例用 bin/yh」的分支——平台与架构都写进文件名，
# 一眼能看出种子形态，也避免跨平台误取。
ifeq ($(HOST_SYSTEM),Darwin)
 HOST_TAG = darwin
else ifeq ($(HOST_SYSTEM),Linux)
 HOST_TAG = linux
else
 HOST_TAG = $(shell printf '%s' '$(HOST_SYSTEM)' | tr '[:upper:]' '[:lower:]')
endif
BIN_SEED = $(REPO_BIN)/yh-$(HOST_TAG)-$(SEED_ARCH)$(EXESUF)
# 从最新 GitHub Release 取本机平台种子时使用的平台名；Linux/x86_64 种子
# 默认不入库，开发机先执行 make fetch-seed 或显式设置 SEED。
ifeq ($(HOST_SYSTEM),Darwin)
 SEED_PLATFORM = darwin-arm64
else ifeq ($(SEED_ARCH),arm64)
 SEED_PLATFORM = linux-arm64
else
 SEED_PLATFORM = linux-x86_64
endif

# 编译、验证和滚动使用同一个宿主平台种子；显式 SEED 可用于 CI 的临时种子。
SEED ?= $(BIN_SEED)
SEED_DEST ?= $(BIN_SEED)
YH_PREREQ = $(SEED)

# 快速暂存目录（2026-10-15）：语料门每个用例都要 exec 一遍 70MB 量级的编译器，
# 仓库挂在 9p/网络盘上时每次读二进制要 0.2–0.4s。把编译器与语料产物放到系统
# 临时目录（Linux /tmp 为 ext4/tmpfs、macOS $TMPDIR 为 APFS）后实测单次调用
# 665ms→464ms、整用例 939ms→703ms（约 −25%）。
# FAST_STAGE=0 关闭暂存，改回直接用仓库根 $(YH)。
FAST_STAGE ?= 1
FAST_DIR ?= $(if $(TMPDIR),$(TMPDIR),/tmp)/yh-fast
# 一律用绝对路径：harness 里 subprocess 不带 cwd，相对路径不会走 PATH 查找。
YH_RUN = $(abspath $(YH))
RUN_WORK_FLAG =
SELFHOST_WORK_FLAG =
MODCHECK_WORK_FLAG =
ifeq ($(FAST_STAGE),1)
 YH_RUN = $(abspath $(FAST_DIR)/yh)
 RUN_WORK_FLAG = --workdir $(abspath $(FAST_DIR)/yh-run-work)
 SELFHOST_WORK_FLAG = --workdir $(abspath $(FAST_DIR)/selfhost)
 MODCHECK_WORK_FLAG = --workdir $(abspath $(FAST_DIR)/modcheck)
endif

# SELFHOST_WORKDIR/SELFHOST_KEEP 供 Release CI 保留 cc4 自举候选：
#   make selfhost-native SELFHOST_KEEP=1 SELFHOST_WORKDIR=dist/selfhost
# 默认不保留，保持日常门临时目录/清理行为。
SELFHOST_KEEP ?= 0
SELFHOST_KEEP_FLAG =
ifeq ($(SELFHOST_KEEP),1)
 SELFHOST_KEEP_FLAG = --keep
endif
ifneq ($(SELFHOST_WORKDIR),)
 SELFHOST_WORK_FLAG = --workdir $(abspath $(SELFHOST_WORKDIR))
endif

# SKIP_CORPUS=1：同一轮里 make test 已经跑过等价语料时，省掉自举门里重复的
# 那遍（约 1 分钟）。默认 0——门保持最严，重复跑一遍不省。
SKIP_CORPUS ?= 0
CORPUS_FLAG =
ifeq ($(SKIP_CORPUS),1)
 CORPUS_FLAG = --skip-corpus
endif

# LL10：x86_64 LLVM 语料与原生连续自举门。只在 Linux/x86_64 启动；
# A 由 ARM64 种子经 qemu 交叉生成，B/C/D 均直接原生运行。
LLVM_TARGET ?= x86_64-unknown-linux-gnu
LLVM_SEED ?= $(REPO_BIN)/yh-linux-arm64
LLVM_JOBS ?= 2
LLVM_RUN_FLAGS = --backend llvm --target $(LLVM_TARGET)

# stage-yh：把 $(YH) 复制到 $(YH_RUN)（FAST_STAGE=0 时 YH_RUN 就是 $(YH)，
# 该目标退化为空操作）。先写 .tmp 再 mv，避免并发读到半个 70MB 二进制。
.PHONY: stage-yh
stage-yh: $(YH)
ifeq ($(FAST_STAGE),1)
	@mkdir -p "$(FAST_DIR)"
	@cp -f "$(YH)" "$(YH_RUN).tmp" && mv -f "$(YH_RUN).tmp" "$(YH_RUN)"
ifeq ($(HOST_SYSTEM),Darwin)
	@ln -sfn "$(abspath compiler/darwin-sdk)" "$(FAST_DIR)/darwin-sdk"
endif
else
	@:
endif

# 内嵌静态 LLVM：开关（auto/1/0）与宿主架构。宿主只按**种子文件名**判定，
# 因为 SEED_ARCH 随宿主架构而 SEED 可被显式覆盖（x86_64 宿主上默认种子里
# 没有 x64 后端，必须显式用 bin/yh-linux-arm64，此时产物是 aarch64 ELF）。
# Darwin/ARM64 只在本机有固定源码包/SDK 时自动接入；其他 Darwin 宿主不接入。
# Darwin 测试/自举统一使用随编译器分发的 SDK stub；显式 SDKROOT 仍优先。
ifeq ($(HOST_SYSTEM),Darwin)
 export YH_DARWIN_SDK = $(abspath compiler/darwin-sdk)
 # 固定 SDK 一旦准备好，就用它的 SDKROOT：自举闭包末尾的 -lc++ 只能由宿主
 # 真实 SDK 解析（bundled stub 不含 libc++）。显式 SDKROOT 仍然优先。
 DARWIN_SDK_RECORD = $(TOPSRC)/tmp/llvm-migration/darwin-sdk/sdk-darwin-aarch64/host.json
 ifneq ($(wildcard $(DARWIN_SDK_RECORD)),)
  export SDKROOT ?= $(shell python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["sdk_root"])' '$(DARWIN_SDK_RECORD)')
 endif
endif
YH_LLVM_HOST ?= auto
LLVM_HOST =
ifeq ($(HOST_SYSTEM),Linux)
 ifneq ($(findstring arm64,$(notdir $(SEED))),)
  LLVM_HOST = linux-aarch64
 endif
 ifneq ($(findstring aarch64,$(notdir $(SEED))),)
  LLVM_HOST = linux-aarch64
 endif
 ifneq ($(findstring x64,$(notdir $(SEED))),)
  LLVM_HOST = linux-x86_64
 endif
endif
ifeq ($(HOST_SYSTEM),Darwin)
 ifneq ($(findstring darwin-arm64,$(notdir $(SEED))),)
  LLVM_HOST = darwin-aarch64
 endif
endif
LLVM_HOST_MODE = $(YH_LLVM_HOST)
ifeq ($(YH_LLVM_HOST),1)
 LLVM_HOST_MODE = require
endif
ifeq ($(YH_LLVM_HOST),0)
 LLVM_HOST_MODE = off
endif
LLVM_HOST_FLAGS =
ifneq ($(LLVM_HOST),)
 LLVM_HOST_FLAGS = --llvm-host $(LLVM_HOST) --llvm-mode $(LLVM_HOST_MODE)
endif
ifeq ($(LLVM_HOST),darwin-aarch64)
 # Darwin/ARM64 默认 LLVM：运行时与缓存专项改用 Darwin LLVM 变体；
 # project 验收显式选择 LLVM，避免门禁按 legacy 产物布局断言。
 RUNTIME_TEST = python3 $(TOPSRC)/tests/selfhost/llvm-darwin-runtime.py --compiler-path $(YH_RUN)
 CACHE_TEST = python3 $(TOPSRC)/tests/selfhost/llvm-darwin-cache.py --compiler-path $(TOPSRC)/yh$(EXESUF)
 MODCHECK_FLAGS = --backend llvm
 # 自举闭包门：证明闭包来自构建机的 selfhost-flags.txt，而不是种子内烘焙路径。
 SELFHOST_FLAGS_TEST = python3 $(TOPSRC)/tests/selfhost/llvm-darwin-selfhost-flags.py --compiler-path $(YH_RUN)
else ifeq ($(LLVM_HOST),linux-x86_64)
 # x64 默认 LLVM 后端下，runtime-memory 的内存运行时契约由 LLVM x64 导入审计覆盖；
 # 完整 legacy 形态（含 ARM64 汇编）留给 arm64/Darwin 宿主。
 RUNTIME_TEST = python3 $(TOPSRC)/tests/selfhost/runtime-memory.py --compiler-path $(YH_RUN) --llvm-x64
 # 缓存专项同样改用 LLVM 缓存门（legacy link-cache 期待外部汇编器调用）。
 CACHE_TEST = python3 $(TOPSRC)/tests/selfhost/llvm-cache.py --compiler-path $(TOPSRC)/yh$(EXESUF)
 MODCHECK_FLAGS = --backend llvm
else ifeq ($(LLVM_HOST),linux-aarch64)
 # F1：Linux/AArch64 默认 LLVM；运行时/C ABI 用 F1 门，缓存用通用 LLVM 门。
 RUNTIME_TEST = python3 $(TOPSRC)/tests/selfhost/llvm-linux-arm64.py --compiler-path $(YH_RUN)
 CACHE_TEST = python3 $(TOPSRC)/tests/selfhost/llvm-cache.py --compiler-path $(TOPSRC)/yh$(EXESUF) --target aarch64-unknown-linux-gnu
 MODCHECK_FLAGS = --backend llvm
else
 RUNTIME_TEST = python3 $(TOPSRC)/tests/selfhost/runtime-memory.py --compiler-path $(YH_RUN)
 CACHE_TEST = python3 $(TOPSRC)/tests/selfhost/link-cache.py --compiler-path $(TOPSRC)/yh$(EXESUF)
 MODCHECK_FLAGS =
endif

all: $(YH)

# llvm-host：准备内嵌静态 LLVM 宿主（桥归档 + 宿主可执行文件 + 身份记录）。
# 首次需要联网取固定 SDK；之后只用 tmp/ 里的缓存包，可离线重跑。
.PHONY: llvm-host
llvm-host:
	@test -n "$(LLVM_HOST)" || { echo "错误: 当前种子 $(SEED) 没有对应的固定 LLVM SDK"; exit 1; }
	@if test "$(LLVM_HOST)" = darwin-aarch64; then \
	  python3 $(TOPSRC)/tools/llvm-darwin-host.py prepare --host $(LLVM_HOST) --jobs $(LLVM_JOBS); \
	else \
	  python3 $(TOPSRC)/tools/llvm-host.py prepare --host $(LLVM_HOST); \
	fi

# bootstrap：准备固定 LLVM 宿主（幂等）后冷编，首次/换机的一条命令。
# 顺序由子 make 保证，避免 -j 下 llvm-host 与 all 并发。
.PHONY: bootstrap
bootstrap: llvm-host
	@$(MAKE) all

.PHONY: verify-seed fetch-seed
verify-seed:
	python3 $(TOPSRC)/tools/selfhost_snapshot_gate.py --verify-seed "$(abspath $(SEED))"

# fetch-seed：从最新 GitHub Release 下载当前平台种子（写入 bin/...）。
# 私有仓库需要 GITHUB_REPOSITORY 与 GH_TOKEN/GITHUB_TOKEN；
# 种子不入库（2026-10-21 起不再使用 Git LFS），任何平台首次构建前执行本目标。
fetch-seed:
	python3 $(TOPSRC)/tools/fetch-release-seed.py --platform $(SEED_PLATFORM)

# 一步链：用入库种子在默认 systemless 配置下冷编 compiler/。
# 清除实际项目缓存 compiler/.build，确保每次都从种子冷编。
# 产物形态随宿主（Darwin → Mach-O，Linux → ELF）。
# LLVM_HOST_FLAGS 决定是否把静态 LLVM 桥链进 $(YH)；宿主不可用时只警告并
# 回退旧路径，绝不让 LLVM 成为构建失败点。
$(YH): $(YH_PREREQ) $(wildcard compiler/*.yh) $(wildcard compiler/*/*.yh) \
	$(wildcard compiler/llvm/*) $(TOPSRC)/compiler/project.toml \
	$(TOPSRC)/vendor/llvm/sdk.lock.json $(TOPSRC)/tools/seed-build.py \
	$(TOPSRC)/tools/llvm-host.py $(TOPSRC)/tools/llvm-darwin-host.py \
	$(TOPSRC)/tools/llvm-darwin-sdk.py | verify-seed
	rm -rf compiler/.build
	python3 "$(TOPSRC)/tools/seed-build.py" --compiler "$(abspath $(SEED))" --project "$(TOPSRC)/compiler" --output "$(TOPSRC)/yh" $(LLVM_HOST_FLAGS)

# seed：滚种子——把刚构建并验证过的 yh 覆盖入库种子。
# 只应在 make test 与 make selfhost-native 全绿后执行（不作为依赖，
# 防止未验证产物污染种子）。
seed:
	@cp -f "$(YH)" "$(SEED_DEST).tmp"
	@mv -f "$(SEED_DEST).tmp" "$(SEED_DEST)"
ifeq ($(HOST_SYSTEM),Darwin)
	@codesign -s - -f "$(SEED_DEST)" 2>/dev/null || true
endif
	@python3 $(TOPSRC)/tools/selfhost_snapshot_gate.py --write-seed-hash "$(abspath $(SEED_DEST))"
	@echo "宿主平台种子已更新：$(SEED_DEST)"

install: all
	$(INSTALL) -d $(BINDIR)
	$(INSTALL) -m755 yh$(EXESUF) $(BINDIR)
	@$(INSTALL) -d $(DESTDIR)$(PREFIX)/share/yh/libs
	@cd $(TOPSRC)/libs && find . -path './cli/test' -prune -o -type f \( -name '*.yh' -o -name 'project.toml' \) -print | while read f; do \
	  d="$(DESTDIR)$(PREFIX)/share/yh/libs/$$(dirname "$$f")"; \
	  $(INSTALL) -d "$$d"; \
	  $(INSTALL) -m644 "$$f" "$$d"; \
	done
ifeq ($(HOST_SYSTEM),Darwin)
	$(INSTALL) -d $(DESTDIR)$(PREFIX)/share/yh/darwin-sdk/usr/lib
	$(INSTALL) -m644 compiler/darwin-sdk/usr/lib/libSystem.tbd $(DESTDIR)$(PREFIX)/share/yh/darwin-sdk/usr/lib/
	$(INSTALL) -m644 compiler/darwin-sdk/SDKSettings.json compiler/darwin-sdk/manifest.json compiler/darwin-sdk/README.md $(DESTDIR)$(PREFIX)/share/yh/darwin-sdk/
endif

uninstall:
	rm -f $(BINDIR)/yh$(EXESUF)
	rm -rf $(DESTDIR)$(PREFIX)/share/yh/libs
ifeq ($(HOST_SYSTEM),Darwin)
	rm -rf $(DESTDIR)$(PREFIX)/share/yh/darwin-sdk
endif

# yh 三层回归：ANTLR 参考语法 + 编译器语法模式 + 运行语义语料。
# 语料门的编译器一律用暂存副本 $(YH_RUN)（见 stage-yh）；ANTLR 层在单进程内
# 解析，不需要编译器。语料产物默认放快速暂存目录，避免 9p/网络盘上的小文件写。
test: stage-yh
	python3 $(TOPSRC)/tests/yh/check.py
	python3 $(TOPSRC)/tests/yh/check.py --compiler --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/yh-run/check.py --compiler $(YH_RUN) $(RUN_WORK_FLAG)
	python3 $(TOPSRC)/tests/tools/yh-code-stats/check.py

# quick：日常迭代门。只跑不依赖后端的语法语料（ANTLR + 编译器 --syntax-check），
# 秒级到十几秒，改语法/诊断时够用；运行语义与自举门留给 test/full。
quick: stage-yh
	python3 $(TOPSRC)/tests/yh/check.py
	python3 $(TOPSRC)/tests/yh/check.py --compiler --compiler-path $(YH_RUN)

# selfhost-native：本机全套门（无需容器、无 stage0）。
# 旧种子迁移代 + 候选两代固定点 + 自解析/语法/运行语料 + 项目验收。
# link-cache 探针需要观测编译器调用的外部汇编/链接工具，因此它继续用
# 仓库根 $(YH)，不能用暂存副本。
selfhost-native: stage-yh
	python3 $(TOPSRC)/tools/selfhost_snapshot_gate.py --verify-seed "$(abspath $(SEED))"
	python3 $(TOPSRC)/tests/selfhost/native-selfhost.py --seed "$(abspath $(SEED))" $(SELFHOST_WORK_FLAG) $(CORPUS_FLAG) $(SELFHOST_KEEP_FLAG)
	python3 $(TOPSRC)/tests/selfhost/scratch-isolation.py --compiler-path $(YH_RUN) --jobs 4
	python3 $(TOPSRC)/tests/selfhost/lex-stats.py --compiler-path $(YH_RUN)
	$(RUNTIME_TEST)
	$(SELFHOST_FLAGS_TEST)
	python3 $(TOPSRC)/tests/selfhost/check-command.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/foreign-fs-build.py --compiler-path $(YH_RUN)
	$(CACHE_TEST)
	python3 $(TOPSRC)/tests/modules/check.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/modules/build-check.py --compiler-path $(YH_RUN) $(MODCHECK_FLAGS) $(MODCHECK_WORK_FLAG)

# llvm-isolation：bwrap + 空 PATH 验证最终 yh 不依赖系统 LLVM/lld、无外部旁车。
.PHONY: llvm-isolation
llvm-isolation: $(YH)
	python3 $(TOPSRC)/tests/selfhost/llvm-isolation.py --compiler $(TOPSRC)/bin/yh-linux-x64

# test-llvm：LLVM x64 O0/O2 全量語法/运行/模块/项目语料、统计覆盖与专项门。
.PHONY: test-llvm selfhost-llvm
test-llvm: stage-yh
	@test "$(HOST_SYSTEM)" = Linux || { echo "错误: test-llvm 首期要求 Linux/x86_64"; exit 1; }
	@test "$(HOST_ARCH)" = x86_64 -o "$(HOST_ARCH)" = amd64 || { echo "错误: test-llvm 首期要求 Linux/x86_64"; exit 1; }
	python3 $(TOPSRC)/tests/selfhost/llvm-selfhost.py --self-test
	python3 $(TOPSRC)/tests/yh/check.py --compiler --compiler-path $(YH_RUN) --quiet
	python3 $(TOPSRC)/tests/yh-run/check.py --compiler $(YH_RUN) $(LLVM_RUN_FLAGS) --opt-level 0 --quiet --jobs $(LLVM_JOBS) --workdir $(TOPSRC)/tmp/llvm-test/yh-run-O0
	python3 $(TOPSRC)/tests/yh-run/check.py --compiler $(YH_RUN) $(LLVM_RUN_FLAGS) --opt-level 2 --quiet --jobs $(LLVM_JOBS) --workdir $(TOPSRC)/tmp/llvm-test/yh-run-O2
	python3 $(TOPSRC)/tests/modules/check.py --compiler-path $(YH_RUN) $(LLVM_RUN_FLAGS) --opt-level 0 --quiet --jobs $(LLVM_JOBS)
	python3 $(TOPSRC)/tests/modules/check.py --compiler-path $(YH_RUN) $(LLVM_RUN_FLAGS) --opt-level 2 --quiet --jobs $(LLVM_JOBS)
	python3 $(TOPSRC)/tests/modules/build-check.py --compiler-path $(YH_RUN) $(LLVM_RUN_FLAGS) --opt-level 0 --jobs $(LLVM_JOBS) --workdir $(abspath $(TOPSRC)/tmp/llvm-test/modcheck-O0)
	python3 $(TOPSRC)/tests/modules/build-check.py --compiler-path $(YH_RUN) $(LLVM_RUN_FLAGS) --opt-level 2 --jobs $(LLVM_JOBS) --workdir $(abspath $(TOPSRC)/tmp/llvm-test/modcheck-O2)
	python3 $(TOPSRC)/tests/selfhost/llvm-driver.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/runtime-memory.py --compiler-path $(YH_RUN) --llvm-x64
	python3 $(TOPSRC)/tests/selfhost/llvm-lld.py

# selfhost-llvm：执行 A→B/C/D 的 O0/O2 原生固定点；脚本在最终 D 候选上运行完整语料与专项门。
# 不依赖 stage-yh：x64 交叉种子是 arm64，root $(YH) 会误按宿主种子构建；
# 脚本自行用 seed-build 产 x64 A。
selfhost-llvm:
	python3 $(TOPSRC)/tests/selfhost/llvm-selfhost.py --seed "$(abspath $(LLVM_SEED))" --jobs $(LLVM_JOBS)

# test-llvm-linux-arm64：F1 Linux/AArch64 LLVM 运行时、C ABI、对象架构与 O0/O2。
# 只在 arm64 Linux 容器内原生运行；x64 宿主不预跑本门。
.PHONY: test-llvm-linux-arm64
test-llvm-linux-arm64: stage-yh
	@test "$(HOST_SYSTEM)" = Linux || { echo "错误: test-llvm-linux-arm64 要求 Linux/aarch64"; exit 1; }
	@test "$(HOST_ARCH)" = aarch64 -o "$(HOST_ARCH)" = arm64 || { echo "错误: test-llvm-linux-arm64 要求 Linux/aarch64"; exit 1; }
	python3 $(TOPSRC)/tests/selfhost/llvm-linux-arm64.py --compiler-path $(YH_RUN)

# selfhost-llvm-darwin：F2-8 原生连续自举（种子 → B/C/D LLVM，
# O0/O2 固定点 + 自解析 + 全量语料 + Darwin 专项门 + 隔离 PATH）。
# LL12 后种子即 LLVM 编出的过渡代 A，不再有 legacy 起点。
.PHONY: selfhost-llvm-darwin
selfhost-llvm-darwin:
	@test "$(HOST_SYSTEM)" = Darwin -a "$(HOST_ARCH)" = arm64 || { echo "错误: selfhost-llvm-darwin 要求 Darwin/ARM64"; exit 1; }
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-selfhost.py --seed "$(abspath $(SEED))" --jobs $(LLVM_JOBS)

# test-llvm-darwin：Darwin/ARM64 静态 SDK、弱桩兼容、LLVM 对象与 Apple ABI 探针。
.PHONY: test-llvm-darwin
test-llvm-darwin: stage-yh
	@test "$(HOST_SYSTEM)" = Darwin -a "$(HOST_ARCH)" = arm64 || { echo "错误: test-llvm-darwin 要求 Darwin/ARM64"; exit 1; }
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-sdk.py
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-host.py
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-bridge.py --compiler-path $(YH_RUN) --require-embedded
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-object.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-abi.py --suite full --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-cache.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-default.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-bundled-sdk.py --compiler-path $(TOPSRC)/yh$(EXESUF)
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-selfhost.py --self-test
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-runtime.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-selfhost-flags.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/llvm-darwin-link.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tools/llvm-darwin-host.py status --host darwin-aarch64

# full：滚种子前的全量门（三层回归 + 自举全套）。
# full：全套门。test 已用等价编译器跑过一遍语料，selfhost-native 里重复的
# 那一遍用 SKIP_CORPUS=1 省掉（约 1 分钟）。
full: SKIP_CORPUS = 1
full: test selfhost-native

# dev：开发迭代用增量构建。与 make 的差别是不删除 compiler/.build，
# 让编译器自己的对象/IR 缓存命中未变模块；只用于本地迭代，
# 不用于种子候选与固定点验收（那些必须冷编）。
.PHONY: dev
dev: verify-seed
	python3 "$(TOPSRC)/tools/seed-build.py" --compiler "$(abspath $(SEED))" --project "$(TOPSRC)/compiler" --output "$(TOPSRC)/yh" $(LLVM_HOST_FLAGS)

test-all: test

# explorer：启动 yh Compiler Explorer（本地浏览器图形界面）。
explorer:
	python3 $(TOPSRC)/tools/yh-explorer.py

# 统计编译器 yh 源码规模；独立运行，不依赖编译器构建。
.PHONY: code-stats test-code-stats
code-stats:
	python3 $(TOPSRC)/tools/yh-code-stats.py

test-code-stats:
	python3 $(TOPSRC)/tests/tools/yh-code-stats/check.py

tests.%: ;

clean:
	rm -f yh$(EXESUF)
	rm -rf compiler/.build tmp/selfbuild-gate tmp/selfhost tmp/modcheck

help:
	@sed -n '2,20p' $(TOPSRC)/Makefile | sed 's/^# \{0,1\}//'

.PHONY: all install uninstall test test-all quick full explorer code-stats test-code-stats seed selfhost-native clean help llvm-host bootstrap stage-yh fetch-seed test-llvm-linux-arm64 test-llvm-darwin selfhost-llvm-darwin

endif # ($(INCLUDED),no)
