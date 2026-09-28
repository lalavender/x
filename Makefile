# --------------------------------------------------------------------------
# yh（玉衡）编译器 —— AArch64/ELF 专用构建
#
# 宿主 C 编译器构建 yh 编译器本体；libtcc1.a 由独立的目标 C 工具链
# （AArch64 Linux）生成，不使用 yh 自身编译 C：
#   * 配置集中在 config.h 与本文件，不需要 ./configure
#   * 只保留 AArch64 后端，源码以 ONE_SOURCE 方式一次编译成可执行文件
#
#   make            构建 yh、libtcc.a、libtcc1.a
#   make test       运行 tests/yh 语法语料与编译器模式回归
#   make bootstrap  自举验证门（G1 语法 + G2 三代闭环 + 全量固定点，需容器）
#   make selfhost-native  本机（Darwin）等价自举差分，无需容器
#   make install    安装到 $(PREFIX)（默认 /usr/local；DESTDIR 用作打包根）
#   make uninstall  卸载
#   make clean      清理
#
# 可在命令行覆盖：CC、AR、TARGET_CC、TARGET_CFLAGS、PREFIX、DESTDIR、
#                 CFLAGS、LIBS、VERSION
# --------------------------------------------------------------------------

ifndef TOP
 TOP = .
 INCLUDED = no
endif
TOPSRC = $(TOP)
SRC = $(TOPSRC)/src

VERSION ?= $(shell cat $(TOPSRC)/VERSION)
ARCH = arm64

CC ?= cc
AR ?= ar
INSTALL ?= install
EXESUF =
LIBSUF = .a
DLLSUF = .so
ifeq ($(shell uname -s),Darwin)
 CONFIG_OSX = yes
 DLLSUF = .dylib
endif

PREFIX ?= /usr/local
BINDIR = $(DESTDIR)$(PREFIX)/bin
LIBDIR = $(DESTDIR)$(PREFIX)/lib

CFLAGS += -Wall -g -O2 -Wdeclaration-after-statement -fno-strict-aliasing \
          -Wno-pointer-sign -Wno-sign-compare -Wno-unused-result
CPPFLAGS += -I$(TOPSRC) -I$(SRC)/core -I$(SRC)/targets -I$(SRC)/formats \
            -DTCC_VERSION="\"$(VERSION)\""
LIBS ?= -lm

# 构建 yh 后可执行 ./yh --syntax-check f.yh 做纯语法检查（不需要目标库）
YH = $(TOP)/yh$(EXESUF)

LIBTCC = libtcc.a
LIBTCC1 = libtcc1.a
NATIVE_DEFINES =

# libtcc1.a 的内容：本后端需要的运行时辅助函数（128 位 long double 软浮点等）。
# 必须由独立的目标 C 工具链产出 AArch64 Linux ELF，禁止用 yh 自举。
LIBTCC1_SRC = $(TOPSRC)/lib/lib-arm64.c

# 目标 C 工具链自动探测：
#   1) aarch64 Linux 交叉/本机 gcc；
#   2) 任意 clang（宿主非 AArch64 Linux 时自动加 -target）；
#   3) AArch64 Linux 本机的 cc。
TARGET_CC ?=
TARGET_CFLAGS ?=
ifeq ($(TARGET_CC),)
 TARGET_CC := $(shell command -v aarch64-linux-gnu-gcc 2>/dev/null || \
                command -v aarch64-none-linux-gnu-gcc 2>/dev/null)
endif
ifeq ($(TARGET_CC),)
 HOST_OS := $(shell uname -s)
 HOST_ARCH := $(shell uname -m)
 ifeq ($(HOST_OS)-$(HOST_ARCH),Linux-aarch64)
  TARGET_CC := cc
 endif
endif
ifeq ($(TARGET_CC),)
 TARGET_CC := $(shell command -v clang 2>/dev/null || \
                command -v /opt/homebrew/opt/llvm/bin/clang 2>/dev/null || \
                command -v /usr/local/opt/llvm/bin/clang 2>/dev/null)
 ifneq ($(TARGET_CC),)
  ifneq ($(HOST_OS)-$(HOST_ARCH),Linux-aarch64)
   TARGET_CFLAGS += -target aarch64-linux-gnu
  endif
 endif
endif

# 归档 AArch64 Linux ELF 成员需要 ELF 归档器：
# macOS 的 BSD ar 会拒绝非 Mach-O 成员，clang 同目录的 llvm-ar 可用。
TARGET_AR ?=
ifeq ($(TARGET_AR),)
 ifeq ($(shell $(TARGET_CC) --version 2>/dev/null | head -1 | grep -ci clang),1)
  TARGET_AR := $(shell command -v $(dir $(TARGET_CC))llvm-ar 2>/dev/null || \
                  command -v llvm-ar 2>/dev/null || command -v ar 2>/dev/null)
 else
  TARGET_AR := $(AR)
 endif
endif

HEADERS = $(wildcard $(SRC)/core/*.h $(SRC)/targets/*.h $(SRC)/formats/*.h) $(TOPSRC)/config.h
SOURCES = $(wildcard $(SRC)/core/*.c $(SRC)/targets/*.c)

ifeq ($(INCLUDED),no)
# --------------------------------------------------------------------------
# 顶层构建规则

all: yh$(EXESUF) $(LIBTCC) $(LIBTCC1)

# 编译器本体：src/core/tcc.c 在 ONE_SOURCE 下把各 .c 汇成一个编译单元，一条命令产出
yh$(EXESUF): $(SOURCES) $(HEADERS)
	$(CC) -o $@ $(SRC)/core/tcc.c $(CPPFLAGS) $(CFLAGS) $(LIBS)

# 供外部程序链接的静态库：同样只编译 libtcc.c 一个文件
$(LIBTCC): libtcc.o
	$(AR) rcs $@ $^
libtcc.o: $(SOURCES) $(HEADERS)
	$(CC) -c -o $@ $(SRC)/core/libtcc.c $(CPPFLAGS) $(CFLAGS)

# 运行时库：用独立目标 C 工具链编译打包（成员必须是 AArch64 Linux ELF）
$(LIBTCC1): $(LIBTCC1_SRC)
ifeq ($(TARGET_CC),)
	$(error 找不到目标 C 工具链：无法产出 AArch64 Linux ELF 的 libtcc1.a。\
请安装 llvm clang 或 aarch64-linux-gnu-gcc，或用 make TARGET_CC=/路径/工具链 指定)
endif
	$(TARGET_CC) $(TARGET_CFLAGS) -c $(LIBTCC1_SRC) -o libtcc1.o
	$(TARGET_AR) rcs $@ libtcc1.o

install: all
	$(INSTALL) -d $(BINDIR) $(LIBDIR)
	$(INSTALL) -m755 yh$(EXESUF) $(BINDIR)
	$(INSTALL) -m644 $(LIBTCC) $(LIBDIR)
	$(INSTALL) -m644 $(LIBTCC1) $(LIBDIR)

uninstall:
	rm -f $(BINDIR)/yh$(EXESUF) $(LIBDIR)/$(LIBTCC) $(LIBDIR)/$(LIBTCC1)

# yh 三层回归：ANTLR 参考语法 + yh 编译器语法模式 + yh 语义/运行测试。
# tests/yh-run 的运行用例在本机（Mach-O）执行；交叉 ELF 用例经 --cross 在
# Linux 容器执行（不可用时其内部打印 SKIP，不计失败）。
test: yh$(EXESUF)
	python3 $(TOPSRC)/tests/yh/check.py
	python3 $(TOPSRC)/tests/yh/check.py --compiler
	python3 $(TOPSRC)/tests/yh-run/check.py

# selfhost-native：本机（Darwin/arm64）自举差分验证，无需 docker。
# 与 make bootstrap 的三代闭环等价（stage1→stage2→stage3、自解析、语法
# 语料、汇编固定点），但把发射的 Linux 汇编改写为 Mach-O 后本机链接。
# 用途：容器不可用或需要快速定位自举缺陷时的日常回归。
selfhost-native: yh$(EXESUF)
	python3 $(TOPSRC)/tests/selfhost/native-selfhost.py

# --------------------------------------------------------------------------
# 自举（docs/02-plan/yh-自举实施方案-v2.md）
#
# compiler/ 下的 .yh 新编译器按显式顺序拼接为 tmp/bootstrap/compiler.yh；
# stage0 交叉编译得到 AArch64 Linux ELF 的 stage1；语法门（G1）经容器
# 包装器在 Linux 容器内执行 stage1 完成自解析与全量语料差分。
# 拼接只连接完整顶层声明、保留换行，不做任何条件替换。
# --------------------------------------------------------------------------

SELFHOST_DIR = $(TOPSRC)/compiler
SELFHOST_SOURCES = $(SELFHOST_DIR)/model.yh \
                   $(SELFHOST_DIR)/buffer.yh \
                   $(SELFHOST_DIR)/lexer.yh \
                   $(SELFHOST_DIR)/target.yh \
                   $(SELFHOST_DIR)/parse_type.yh \
                   $(SELFHOST_DIR)/symbols.yh \
                   $(SELFHOST_DIR)/emit_arm64.yh \
                   $(SELFHOST_DIR)/sem.yh \
                   $(SELFHOST_DIR)/parse_expr.yh \
                   $(SELFHOST_DIR)/parse_stmt.yh \
                   $(SELFHOST_DIR)/parse_decl.yh \
                   $(SELFHOST_DIR)/driver.yh

BOOTSTRAP_DIR = $(TOP)/tmp/bootstrap
BOOTSTRAP_SYSROOT = $(TOP)/tmp/sysroot
# 容器包装器统一入口：YH_STAGE 指向容器内 stage 路径
BOOTSTRAP_WRAPPER = $(TOPSRC)/tests/yh/container-yh.sh
# 运行语义包装器：把 --emit-asm + gcc 伪装成 stage0 的 <file> -o <out> 接口
BOOTSTRAP_CC = $(TOPSRC)/tests/yh/container-yh-cc.sh
# G2 门复验的运行语料：run/ 全量（B7 浮点常量缺陷已修复，见 docs/finish.md）。
BOOTSTRAP_RUN = $(shell for f in $(TOPSRC)/tests/yh-run/run/*.yh; do \
	 basename $$f; done | paste -sd, -)

$(BOOTSTRAP_DIR)/compiler.yh: $(SELFHOST_SOURCES)
	@mkdir -p $(BOOTSTRAP_DIR)
	cat $(SELFHOST_SOURCES) > $@

# stage1：stage0 交叉编译拼接源码（AArch64 Linux ELF），在容器内运行
$(BOOTSTRAP_DIR)/stage1: $(BOOTSTRAP_DIR)/compiler.yh yh$(EXESUF)
	./yh$(EXESUF) $(BOOTSTRAP_DIR)/compiler.yh -o $@ \
	    -Wl,-oformat=elf64-aarch64 -sysroot $(BOOTSTRAP_SYSROOT) -B $(BOOTSTRAP_SYSROOT)

# bootstrap：自举验证门（G1 语法 + G2 三代闭环 + 全量运行语料 + 全量固定点）。
#   1) 拼接确定性：两次拼接逐字节一致（cmp，避开 make 3.81 的变量展开缺陷）；
#   2) 容器前置检查：docker 容器 yh-build 必须可用，缺则直接失败不 SKIP；
#   3) G1：stage1 自解析 + 全部语法正反例差分；
#   4) G2：stage1 编译自身 → stage2；stage2 自解析 + 语法差分 + 全量运行语料；
#   5) G2+：stage2 编译自身 → stage3；stage2.s 与 stage3.s 逐字节比较（固定点），
#      stage3 自解析。
# 每个阶段失败即中止；产出的 .s 保留在 tmp/bootstrap/ 供人工核对。
# 容器不可用时可改用本机等价差分：make selfhost-native。
bootstrap: yh$(EXESUF) $(BOOTSTRAP_DIR)/stage1
	@cat $(SELFHOST_SOURCES) > $(BOOTSTRAP_DIR)/compiler.yh.recheck
	@cmp -s $(BOOTSTRAP_DIR)/compiler.yh $(BOOTSTRAP_DIR)/compiler.yh.recheck || \
	 { echo "自举失败：两次拼接逐字节不一致（拼接不确定）"; exit 1; }
	@rm -f $(BOOTSTRAP_DIR)/compiler.yh.recheck
	@echo "拼接确定性 OK，拼接产物 SHA-256："
	@shasum -a 256 $(BOOTSTRAP_DIR)/compiler.yh
	@docker exec yh-build true 2>/dev/null || \
	 { echo "自举失败：需要运行中的 docker 容器 yh-build（仓库挂载于 /work）"; exit 1; }
	@echo "== G1：stage1 自解析自身拼接源码 =="
	@YH_STAGE=/work/tmp/bootstrap/stage1 $(BOOTSTRAP_WRAPPER) --syntax-check $(CURDIR)/$(BOOTSTRAP_DIR)/compiler.yh \
	 || { echo "自举失败：stage1 未通过自解析"; exit 1; }
	@echo "== G1：stage1 全量语法语料差分（容器内执行） =="
	@YH_STAGE=/work/tmp/bootstrap/stage1 python3 $(TOPSRC)/tests/yh/check.py --compiler --compiler-path $(BOOTSTRAP_WRAPPER) --quiet \
	 || { echo "自举失败：stage1 未通过语法语料差分"; exit 1; }
	@echo "G1 语法自举通过"
	@echo "== G2：stage1 编译自身 → stage2 =="
	@docker exec yh-build sh -c 'cd /work/tmp/bootstrap && ./stage1 --emit-asm compiler.yh > stage2.s' \
	 || { echo "自举失败：stage1 编译自身失败"; exit 1; }
	@docker exec yh-build sh -c 'gcc -no-pie -o /work/tmp/bootstrap/stage2 /work/tmp/bootstrap/stage2.s' \
	 || { echo "自举失败：stage2 链接失败"; exit 1; }
	@docker exec yh-build sh -c 'cd /work/tmp/bootstrap && ./stage2 --syntax-check compiler.yh' \
	 || { echo "自举失败：stage2 未通过自解析"; exit 1; }
	@YH_STAGE=/work/tmp/bootstrap/stage2 python3 $(TOPSRC)/tests/yh/check.py --compiler --compiler-path $(BOOTSTRAP_WRAPPER) --quiet \
	 || { echo "自举失败：stage2 未通过语法语料差分"; exit 1; }
	@echo "== G2：stage2 全量运行语义语料（run/ 全部） =="
	@YH_STAGE=/work/tmp/bootstrap/stage2 python3 $(TOPSRC)/tests/yh-run/check.py \
	 --compiler $(BOOTSTRAP_CC) --cross --workdir $(CURDIR)/$(BOOTSTRAP_DIR)/run --quiet \
	 --filter $(BOOTSTRAP_RUN) \
	 || { echo "自举失败：stage2 未通过全量运行语义语料"; exit 1; }
	@echo "== G2+：stage2 编译自身 → stage3，stage3 自解析 =="
	@docker exec yh-build sh -c 'cd /work/tmp/bootstrap && ./stage2 --emit-asm compiler.yh > stage3.s' \
	 || { echo "自举失败：stage2 编译自身失败"; exit 1; }
	@docker exec yh-build sh -c 'gcc -no-pie -o /work/tmp/bootstrap/stage3 /work/tmp/bootstrap/stage3.s && cd /work/tmp/bootstrap && ./stage3 --syntax-check compiler.yh && ./stage3 --syntax-check /work/tests/yh-run/run/01-hello.yh' \
	 || { echo "自举失败：stage3 构建或自解析失败"; exit 1; }
	@echo "== G2+：汇编固定点比较（stage2/stage3 对自身拼接源码逐字节一致） =="
	@docker exec yh-build sh -c 'cmp /work/tmp/bootstrap/stage2.s /work/tmp/bootstrap/stage3.s' \
	 || { echo "自举失败：stage2.s 与 stage3.s 不逐字节一致（未达固定点）"; exit 1; }
	@echo "自举门通过：G1 语法 + G2 三代闭环 + stage3 自解析 + 全量汇编固定点"

test-all: test

tests.%: ;

clean:
	rm -f yh$(EXESUF) libtcc.o libtcc1.o $(LIBTCC) $(LIBTCC1)
	rm -rf $(TOP)/tmp/bootstrap

help:
	@sed -n '2,20p' $(TOPSRC)/Makefile | sed 's/^# \{0,1\}//'

.PHONY: all install uninstall test test-all bootstrap selfhost-native clean help

endif # ($(INCLUDED),no)
