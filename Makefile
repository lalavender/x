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
#   * make install    安装到 $(PREFIX)（默认 /usr/local；DESTDIR 用作打包根）
#   * make uninstall  卸载
#   * make explorer   启动 yh Compiler Explorer（本地浏览器图形界面）
#   * make yh-asm     构建 asm/ 汇编器项目，产出根目录 yh_asm（编译器不发现它）
#   * make yh-link-build  构建 link/ 静态链接器项目，产出 link/.build/yh_link
#   * make yh-link-probe  跑链接器验收门（自检 + CLI 契约；FULL=1 加端到端/差分）
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

all: $(YH)

.PHONY: verify-seed
verify-seed:
	python3 $(TOPSRC)/tools/selfhost_snapshot_gate.py --verify-seed "$(abspath $(SEED))"

# 一步链：用入库种子在默认 systemless 配置下冷编 compiler/。
# 清除实际项目缓存 compiler/.build，确保每次都从种子冷编。
# 产物形态随宿主（Darwin → Mach-O，Linux → ELF）。
$(YH): $(YH_PREREQ) $(wildcard compiler/*.yh) $(wildcard compiler/*/*.yh) $(TOPSRC)/compiler/project.toml | verify-seed
	rm -rf compiler/.build
	python3 "$(TOPSRC)/tools/seed-build.py" --compiler "$(abspath $(SEED))" --project "$(TOPSRC)/compiler" --output "$(TOPSRC)/yh"

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
test: $(YH)
	python3 $(TOPSRC)/tests/yh/check.py
	python3 $(TOPSRC)/tests/yh/check.py --compiler
	python3 $(TOPSRC)/tests/yh-run/check.py --compiler $(TOPSRC)/yh$(EXESUF)

# selfhost-native：本机全套门（无需容器、无 stage0）。
# 旧种子迁移代 + 候选两代固定点 + 自解析/语法/运行语料 + 项目验收。
selfhost-native: $(YH)
	python3 $(TOPSRC)/tools/selfhost_snapshot_gate.py --verify-seed "$(abspath $(SEED))"
	python3 $(TOPSRC)/tests/selfhost/native-selfhost.py --seed "$(abspath $(SEED))"
	python3 $(TOPSRC)/tests/selfhost/scratch-isolation.py --compiler-path $(TOPSRC)/yh
	python3 $(TOPSRC)/tests/selfhost/lex-stats.py --compiler-path $(TOPSRC)/yh
	python3 $(TOPSRC)/tests/selfhost/runtime-memory.py --compiler-path $(TOPSRC)/yh
	python3 $(TOPSRC)/tests/selfhost/check-command.py --compiler-path $(TOPSRC)/yh
	python3 $(TOPSRC)/tests/selfhost/foreign-fs-build.py --compiler-path $(TOPSRC)/yh
	python3 $(TOPSRC)/tests/selfhost/link-cache.py --compiler-path $(TOPSRC)/yh
	python3 $(TOPSRC)/tests/modules/check.py --compiler-path $(TOPSRC)/yh
	python3 $(TOPSRC)/tests/modules/build-check.py --compiler-path $(TOPSRC)/yh

test-all: test

# explorer：启动 yh Compiler Explorer（本地浏览器图形界面）。
explorer:
	python3 $(TOPSRC)/tools/yh-explorer.py

tests.%: ;

clean:
	rm -f yh$(EXESUF)
	rm -rf compiler/.build tmp/selfbuild-gate tmp/selfhost tmp/modcheck

help:
	@sed -n '2,26p' $(TOPSRC)/Makefile | sed 's/^# \{0,1\}//'

.PHONY: all install uninstall test test-all explorer seed selfhost-native clean help yh-asm yh-link-build yh-link-probe

endif # ($(INCLUDED),no)
