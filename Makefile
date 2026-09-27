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

test-all: test

tests.%: ;

clean:
	rm -f yh$(EXESUF) libtcc.o libtcc1.o $(LIBTCC) $(LIBTCC1)

help:
	@sed -n '2,20p' $(TOPSRC)/Makefile | sed 's/^# \{0,1\}//'

.PHONY: all install uninstall test test-all clean help

endif # ($(INCLUDED),no)
