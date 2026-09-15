# --------------------------------------------------------------------------
# Tiny C Compiler —— AArch64（arm64）专用精简构建
#
# 只用宿主机 C 编译器在 arm64 系统上构建 arm64 版 tcc：
#   * 不再需要 ./configure：配置集中在 config.h 与本文件
#   * 只保留 AArch64 后端，无交叉编译、无 PE/Windows、无文档生成
#   * 源码按 ONE_SOURCE 方式“一次编译成一个可执行文件”，另外编译一份 libtcc.a
#
#   make            构建 tcc、libtcc.a、libtcc1.a
#   make test       运行 tests2 与 pp 测试套件
#   make test-all   运行 tests/ 下的完整测试矩阵（需要 libtcc.a）
#   make install    安装到 $(PREFIX)（默认 /usr/local；DESTDIR 用作打包根）
#   make uninstall  卸载
#   make clean      清理
#
# 可在命令行覆盖：CC、AR、PREFIX、DESTDIR、CFLAGS、LIBS、VERSION
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
TCCDIR = $(DESTDIR)$(PREFIX)/lib/tcc
LIBDIR = $(DESTDIR)$(PREFIX)/lib
INCLUDEDIR = $(DESTDIR)$(PREFIX)/include

CFLAGS += -Wall -g -O2 -Wdeclaration-after-statement -fno-strict-aliasing \
          -Wno-pointer-sign -Wno-sign-compare -Wno-unused-result
CPPFLAGS += -I$(TOPSRC) -I$(SRC)/core -I$(SRC)/targets -I$(SRC)/formats \
            -DTCC_VERSION="\"$(VERSION)\""
LIBS ?= -lm

# 用本目录的 tcc 编译/运行程序时的参数
TCCFLAGS = -B$(TOPSRC) -I$(TOPSRC)/include -I$(TOPSRC) $(if $(CONFIG_OSX),-D_ANSI_SOURCE)
TCC = $(TOP)/tcc$(EXESUF) $(TCCFLAGS)
# tcc 的 -ar（内置归档器）必须是第一个参数，故单独调用
XAR = $(TOP)/tcc$(EXESUF) -ar

LIBTCC = libtcc.a
LIBTCC1 = libtcc1.a
NATIVE_DEFINES =

# libtcc1.a 的内容：本后端需要的运行时辅助函数（128 位 long double 软浮点等）
LIBTCC1_SRC = $(TOPSRC)/lib/lib-arm64.c

HEADERS = $(wildcard $(SRC)/core/*.h $(SRC)/targets/*.h $(SRC)/formats/*.h) $(TOPSRC)/config.h
SOURCES = $(wildcard $(SRC)/core/*.c $(SRC)/targets/*.c)

ifeq ($(INCLUDED),no)
# --------------------------------------------------------------------------
# 顶层构建规则

all: tcc$(EXESUF) $(LIBTCC) $(LIBTCC1)

# 编译器本体：src/core/tcc.c 在 ONE_SOURCE 下把各 .c 汇成一个编译单元，一条命令产出
tcc$(EXESUF): $(SOURCES) $(HEADERS)
	$(CC) -o $@ $(SRC)/core/tcc.c $(CPPFLAGS) $(CFLAGS) $(LIBS)

# 供外部程序链接的静态库：同样只编译 libtcc.c 一个文件
$(LIBTCC): libtcc.o
	$(AR) rcs $@ $^
libtcc.o: $(SOURCES) $(HEADERS)
	$(CC) -c -o $@ $(SRC)/core/libtcc.c $(CPPFLAGS) $(CFLAGS)

# 运行时库：用刚构建出的 tcc 自己编译并打包（-ar 是 tcc 内置的归档器）
$(LIBTCC1): tcc$(EXESUF)
	$(TCC) -c $(LIBTCC1_SRC) -o libtcc1.o
	$(XAR) rcs $@ libtcc1.o

install: all
	$(INSTALL) -d $(BINDIR) $(TCCDIR)/include $(LIBDIR) $(INCLUDEDIR)
	$(INSTALL) -m755 tcc$(EXESUF) $(BINDIR)
	$(INSTALL) -m644 $(LIBTCC1) $(TCCDIR)
	$(INSTALL) -m644 $(TOPSRC)/include/*.h $(TCCDIR)/include
	$(INSTALL) -m644 $(LIBTCC) $(LIBDIR)
	$(INSTALL) -m644 $(SRC)/core/libtcc.h $(INCLUDEDIR)

uninstall:
	rm -f $(BINDIR)/tcc$(EXESUF) $(INCLUDEDIR)/libtcc.h
	rm -f $(LIBDIR)/$(LIBTCC)
	rm -rf $(TCCDIR)

# tests2 用 -run 执行编译结果，需要 arm64 Linux 主机；
# pp（预处理器）测试只用 -E，任何 arm64 主机都能跑。
test: tcc$(EXESUF)
ifdef CONFIG_OSX
	@echo "注意：tests2 需要 arm64 Linux 主机（-run 无法调用 Apple 的可变参数 libc 函数），本机只跑 pp"
else
	$(MAKE) -C $(TOPSRC)/tests/tests2
endif
	$(MAKE) -C $(TOPSRC)/tests/pp

test-all: all
	$(MAKE) -C $(TOPSRC)/tests

tests2.%: tcc$(EXESUF)
	$(MAKE) -C $(TOPSRC)/tests/tests2 $@

clean:
	rm -f tcc$(EXESUF) libtcc.o libtcc1.o $(LIBTCC) $(LIBTCC1)
	-$(MAKE) -C $(TOPSRC)/tests/tests2 clean
	-$(MAKE) -C $(TOPSRC)/tests/pp clean

help:
	@sed -n '2,18p' $(TOPSRC)/Makefile | sed 's/^# \{0,1\}//'

.PHONY: all install uninstall test test-all clean help

endif # ($(INCLUDED),no)
