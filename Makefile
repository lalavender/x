# --------------------------------------------------------------------------
# yh（玉衡）编译器 —— 自举构建
#
# 编译器就是 yh：由入库种子 bin/yh（上一版编译器二进制）对 compiler/
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
#   * make yh-asm     构建 asm/ 汇编器项目，产出根目录 yh_asm（编译器不发现它）
#   * make yh-link-build  构建 link/ 静态链接器项目，产出 link/.build/yh_link
#   * make yh-link-probe  跑链接器验收门（自检 + CLI 契约；FULL=1 加端到端/差分）
#   * make llvm-host  准备内嵌静态 LLVM 宿主（LL3；首次需要联网取固定 SDK）
#   * make clean      清理
#
# 汇编器当前**不接入编译器**：编译器只按 yh_link 名字发现汇编器
# （compiler/cmd/link_cache.yh 的 mb_asm_tool），根目录不再放该名字。
# 需要让编译器临时用汇编器时，显式给 YH_LINK=<asm 产物绝对路径>，
# 或跑 asm/tests/shadow-build.py（影子验收）。见 docs/02-plan/
# yh-asm汇编器稳定化实施方案.md。
#
# 链接器同样**不接入编译器**（2026-10-13 决定，见 docs/02-plan/
# yh-link静态ELF链接器实施方案.md），并且**刻意不产出根目录 yh_link**：
# 编译器当前把根目录的 yh_link 当作汇编器调用（`yh_link asm -t ... -o ...`），
# 真链接器一旦占用该名字，现有 `make`/`make test` 会立刻坏掉。集成是后续任务
# （先把编译器的工具查找改成 yh_asm，再把 yh_link 指向真链接器）。
#
# 可在命令行覆盖：SEED（编译种子路径）。Linux CI 用匹配架构的 ELF 种子。
#
# 内嵌静态 LLVM（LL3，见 docs/02-plan/yh-LLVM后端替换实施方案.md）：
# 根目录 $(YH) 由种子冷编，最终链接发生在编译器内部（compiler/cmd/
# link_cache.yh 的 mb_link），只认 PATH 上的 gcc。因此这里让
# tools/seed-build.py 调 tools/llvm-host.py 生成一个 gcc 链接包装器目录，
# 并**只对种子构建子进程**前置 PATH：编译（gcc -c）原样透传，最终链接
# 改用固定工具链并追加桥归档与静态 LLVM 参数。链接哪个架构由种子文件名
# 决定（x86_64 宿主上用 bin/yh-linux-arm64 时产物仍是 aarch64 ELF）。
#
#   YH_LLVM_HOST=auto（默认）宿主已准备才链入；缺少 SDK/身份失效时打印
#                 明确诊断并按原路径构建，绝不让 LLVM 成为失败点；
#   YH_LLVM_HOST=1 显式要求：必要时联网准备固定 SDK，准备不了则构建失败；
#   YH_LLVM_HOST=0 关闭（完全不介入）。
#
# 旧路径全门（make test / make selfhost-native）在 auto 与 0 下都必须保持绿。
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
ifeq ($(HOST_SYSTEM),Darwin)
 ifeq ($(SEED_ARCH),arm64)
  BIN_SEED = $(REPO_BIN)/yh$(EXESUF)
 else
  BIN_SEED = $(REPO_BIN)/yh-darwin-$(SEED_ARCH)$(EXESUF)
 endif
else ifeq ($(HOST_SYSTEM),Linux)
 BIN_SEED = $(REPO_BIN)/yh-linux-$(SEED_ARCH)$(EXESUF)
else
 BIN_SEED = $(REPO_BIN)/yh-$(HOST_SYSTEM)-$(SEED_ARCH)$(EXESUF)
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
FAST_DIR ?= $(shell printf '%s' "$${TMPDIR:-/tmp}")/yh-fast
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
else
	@:
endif

# 内嵌静态 LLVM：开关（auto/1/0）与宿主架构。宿主只按**种子文件名**判定，
# 因为 SEED_ARCH 随宿主架构而 SEED 可被显式覆盖（x86_64 宿主上默认种子里
# 没有 x64 后端，必须显式用 bin/yh-linux-arm64，此时产物是 aarch64 ELF）。
# macOS 种子没有对应的固定 SDK，非 Linux 宿主一律不接入。
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

all: $(YH)

# llvm-host：准备内嵌静态 LLVM 宿主（桥归档 + 宿主可执行文件 + 身份记录）。
# 首次需要联网取固定 SDK；之后只用 tmp/ 里的缓存包，可离线重跑。
.PHONY: llvm-host
llvm-host:
	@test -n "$(LLVM_HOST)" || { echo "错误: 当前种子 $(SEED) 没有对应的固定 LLVM SDK"; exit 1; }
	python3 $(TOPSRC)/tools/llvm-host.py prepare --host $(LLVM_HOST)

.PHONY: verify-seed
verify-seed:
	python3 $(TOPSRC)/tools/selfhost_snapshot_gate.py --verify-seed "$(abspath $(SEED))"

# 一步链：用入库种子在默认 systemless 配置下冷编 compiler/。
# 清除实际项目缓存 compiler/.build，确保每次都从种子冷编。
# 产物形态随宿主（Darwin → Mach-O，Linux → ELF）。
# LLVM_HOST_FLAGS 决定是否把静态 LLVM 桥链进 $(YH)；宿主不可用时只警告并
# 回退旧路径，绝不让 LLVM 成为构建失败点。
$(YH): $(YH_PREREQ) $(wildcard compiler/*.yh) $(wildcard compiler/*/*.yh) $(TOPSRC)/compiler/project.toml | verify-seed
	rm -rf compiler/.build
	python3 "$(TOPSRC)/tools/seed-build.py" --compiler "$(abspath $(SEED))" --project "$(TOPSRC)/compiler" --output "$(TOPSRC)/yh" $(LLVM_HOST_FLAGS)

# yh-asm：用刚构建出的 $(YH) 冷编 asm/（汇编器项目），产出 yh_asm。
# 刻意不依赖 $(SEED)：asm/ 用到了新语言特性，上一代种子编不了，必须等 $(YH) 就位。
#
# 汇编器**不接入编译器**（2026-10-12 决定，见 docs/02-plan/
# yh-asm汇编器稳定化实施方案.md）：编译器只按 yh_link 名字发现汇编器
# （compiler/cmd/link_cache.yh 的 mb_asm_tool），本目标不再产出该名字，
# 因此 `make yh-asm` 之后 `./yh` 仍走系统 cc。要让编译器临时用汇编器，
# 显式给 YH_LINK=<asm 产物绝对路径>，或跑 asm/tests/shadow-build.py。
YH_ASM = $(TOP)/yh_asm$(EXESUF)

.PHONY: yh-asm
yh-asm: $(YH)
	rm -rf $(TOPSRC)/asm/.build
	cd $(TOPSRC)/asm && "$(abspath $(YH))" build
	cp -f "$(TOPSRC)/asm/.build/yh_asm$(EXESUF)" "$(YH_ASM).tmp"
	mv -f "$(YH_ASM).tmp" "$(YH_ASM)"
ifeq ($(HOST_SYSTEM),Darwin)
	@codesign -s - -f "$(YH_ASM)" 2>/dev/null || true
endif

# yh-link-build：用刚构建出的 $(YH) 冷编 link/（静态链接器项目）。
# 与 yh-asm 一样刻意不依赖 $(SEED)；产物留在 link/.build/，**不复制到仓库根**
# （原因见文件头：根目录 yh_link 目前是编译器眼中的汇编器入口）。
# 需要让编译器临时用链接器时显式给路径，等集成任务落地后再统一。
YH_LINK_OBJ = $(TOPSRC)/link/.build/yh_link$(EXESUF)

.PHONY: yh-link-build
yh-link-build: $(YH)
	rm -rf $(TOPSRC)/link/.build
	cd $(TOPSRC)/link && "$(abspath $(YH))" build
	@test -x "$(YH_LINK_OBJ)" || { echo "错误: 未产出 $(YH_LINK_OBJ)"; exit 1; }
	@echo "链接器已构建：$(YH_LINK_OBJ)（未接入编译器，未放到仓库根）"

# yh-link-probe：链接器验收门。默认只跑构建 + 自检 + CLI 契约
# （不需要汇编器，也不需要在 Linux 上）；FULL=1 追加端到端验收与 GNU ld 差分，
# 这两层需要 yh_asm 与可执行 AArch64 产物的环境（Linux/aarch64 原生或
# x86_64 + qemu-user/binfmt）。
LINK_PROBE_FLAGS =
ifeq ($(FULL),1)
LINK_PROBE_FLAGS = --full
endif

.PHONY: yh-link-probe
yh-link-probe: $(YH)
	cd $(TOPSRC) && python3 $(TOPSRC)/link/tests/check.py \
	    --compiler "$(abspath $(YH))" $(LINK_PROBE_FLAGS)

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

uninstall:
	rm -f $(BINDIR)/yh$(EXESUF)

# yh 三层回归：ANTLR 参考语法 + 编译器语法模式 + 运行语义语料。
# 语料门的编译器一律用暂存副本 $(YH_RUN)（见 stage-yh）；ANTLR 层在单进程内
# 解析，不需要编译器。语料产物默认放快速暂存目录，避免 9p/网络盘上的小文件写。
test: stage-yh
	python3 $(TOPSRC)/tests/yh/check.py
	python3 $(TOPSRC)/tests/yh/check.py --compiler --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/yh-run/check.py --compiler $(YH_RUN) $(RUN_WORK_FLAG)

# quick：日常迭代门。只跑不依赖后端的语法语料（ANTLR + 编译器 --syntax-check），
# 秒级到十几秒，改语法/诊断时够用；运行语义与自举门留给 test/full。
quick: stage-yh
	python3 $(TOPSRC)/tests/yh/check.py
	python3 $(TOPSRC)/tests/yh/check.py --compiler --compiler-path $(YH_RUN)

# selfhost-native：本机全套门（无需容器、无 stage0）。
# 旧种子迁移代 + 候选两代固定点 + 自解析/语法/运行语料 + 项目验收。
# link-cache 探针要按编译器同目录找 yh_link（compiler.parent），因此它继续用
# 仓库根 $(YH)，不能用暂存副本。
selfhost-native: stage-yh
	python3 $(TOPSRC)/tools/selfhost_snapshot_gate.py --verify-seed "$(abspath $(SEED))"
	python3 $(TOPSRC)/tests/selfhost/native-selfhost.py --seed "$(abspath $(SEED))" $(SELFHOST_WORK_FLAG) $(CORPUS_FLAG)
	python3 $(TOPSRC)/tests/selfhost/scratch-isolation.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/lex-stats.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/runtime-memory.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/check-command.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/foreign-fs-build.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/selfhost/link-cache.py --compiler-path $(TOPSRC)/yh$(EXESUF)
	python3 $(TOPSRC)/tests/modules/check.py --compiler-path $(YH_RUN)
	python3 $(TOPSRC)/tests/modules/build-check.py --compiler-path $(YH_RUN) $(MODCHECK_WORK_FLAG)

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
selfhost-llvm: stage-yh
	python3 $(TOPSRC)/tests/selfhost/llvm-selfhost.py --seed "$(abspath $(LLVM_SEED))" --jobs $(LLVM_JOBS)

# full：滚种子前的全量门（三层回归 + 自举全套）。
full: test selfhost-native

test-all: test

# explorer：启动 yh Compiler Explorer（本地浏览器图形界面）。
explorer:
	python3 $(TOPSRC)/tools/yh-explorer.py

tests.%: ;

clean:
	rm -f yh$(EXESUF)
	rm -rf compiler/.build tmp/selfbuild-gate tmp/selfhost tmp/modcheck

help:
	@sed -n '2,34p' $(TOPSRC)/Makefile | sed 's/^# \{0,1\}//'

.PHONY: all install uninstall test test-all quick full explorer seed selfhost-native clean help llvm-host yh-asm yh-link-build yh-link-probe stage-yh

endif # ($(INCLUDED),no)
