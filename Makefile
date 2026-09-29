# --------------------------------------------------------------------------
# yh（玉衡）编译器 —— 自举构建
#
# 编译器就是 yh：由入库种子 bin/yh（上一版编译器二进制）对 compiler/
# 四模块项目 yh build 产出，形态随宿主（Darwin → Mach-O，Linux → ELF）。
# 每个版本直接用上一个版本的二进制编译（无 C 编译步骤、无 stage0）：
#   * make            构建 yh（主编译器，项目根目录）
#   * make seed       滚种子：验证过的 yh 覆盖入库种子 bin/yh 并记 SHA-256
#   * make test       运行 tests/yh 语法语料与编译器模式回归
#   * make selfhost-native  本机全套门（两代固定点 + 全量语料，无需容器）
#   * make install    安装到 $(PREFIX)（默认 /usr/local；DESTDIR 用作打包根）
#   * make uninstall  卸载
#   * make explorer   启动 yh Compiler Explorer（本地浏览器图形界面）
#   * make clean      清理
#
# 可在命令行覆盖：SEED（编译种子路径，CI Linux 用上一版 Release 的
#                 linux-arm64 资产解包出的 ELF 种子）
# --------------------------------------------------------------------------

ifndef TOP
 TOP = .
 INCLUDED = no
TOPSRC = $(TOP)

VERSION ?= $(shell cat $(TOPSRC)/VERSION)
EXESUF =
ifeq ($(shell uname -s),Darwin)
 CONFIG_OSX = yes
endif

PREFIX ?= /usr/local
BINDIR = $(DESTDIR)$(PREFIX)/bin

# --------------------------------------------------------------------------
# 顶层构建规则
# --------------------------------------------------------------------------

YH = $(TOP)/yh$(EXESUF)
REPO_BIN = $(TOP)/bin
BIN_SEED = $(REPO_BIN)/yh$(EXESUF)

# 编译种子：缺省用入库 bin/yh（宿主形态）；命令行可覆盖——CI 的 Linux
# 作业传入上一版 Release 的 linux-arm64 资产解包出的 ELF 种子（Mach-O
# 种子无法在 Linux 运行）。种子路径以绝对路径传给 yh build。
SEED ?=
ifeq ($(SEED),)
 SEED = $(BIN_SEED)
 YH_PREREQ = $(BIN_SEED)
endif

all: $(YH)

# 一步链：种子（上一版编译器）对活跃四模块项目 yh build。
# 每次冷编（compiler/tmp/yh-build 缓存键不含编译器身份，滚动代次下
# 冷编才安全）；产物形态随宿主（Darwin → Mach-O，Linux → ELF）。
$(YH): $(YH_PREREQ) $(wildcard compiler/*.yh) $(wildcard compiler/*/*.yh) $(TOPSRC)/compiler/mod.toml
	rm -rf compiler/tmp/yh-build
	cd compiler && $(abspath $(SEED)) build -o ../yh

# seed：滚种子——把刚构建并验证过的 yh 覆盖入库种子。
# 只应在 make test 与 make selfhost-native 全绿后执行（不作为依赖，
# 防止未验证产物污染种子）。
seed:
	@cp -f $(YH) $(BIN_SEED).tmp
	@mv -f $(BIN_SEED).tmp $(BIN_SEED)
	@codesign -s - -f $(BIN_SEED) 2>/dev/null || true
	@shasum -a 256 $(BIN_SEED) > $(REPO_BIN)/yh.sha256
	@echo "种子已更新：$(BIN_SEED)"

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
# 两代固定点 + 自解析 + 全量语法/运行语料 + 模块语料 + 项目验收。
selfhost-native: $(YH)
	python3 $(TOPSRC)/tests/selfhost/native-selfhost.py
	python3 $(TOPSRC)/tests/modules/check.py --compiler-path $(TOPSRC)/yh
	python3 $(TOPSRC)/tests/modules/build-check.py --compiler-path $(TOPSRC)/yh

test-all: test

# explorer：启动 yh Compiler Explorer（本地浏览器图形界面）。
explorer:
	python3 $(TOPSRC)/tools/yh-explorer.py

tests.%: ;

clean:
	rm -f yh$(EXESUF)
	rm -rf compiler/tmp/yh-build tmp/selfbuild-gate tmp/modcheck

help:
	@sed -n '2,26p' $(TOPSRC)/Makefile | sed 's/^# \{0,1\}//'

.PHONY: all install uninstall test test-all explorer seed selfhost-native clean help

endif # ($(INCLUDED),no)
