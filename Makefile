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
#   * make clean      清理
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

.PHONY: all install uninstall test test-all explorer seed selfhost-native clean help

endif # ($(INCLUDED),no)
