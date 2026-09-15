#
# Tiny C Compiler Makefile for libtcc1.a
#

TOP = ..
include $(TOP)/Makefile
VPATH = $(TOPSRC)/lib $(TOPSRC)/win32/lib
T = $(or $(CROSS_TARGET),$(NATIVE_TARGET),unknown)
X = $(if $(CROSS_TARGET),$(CROSS_TARGET)-)
BIN = $(TOP)/$(X)libtcc1.a

XTCC ?= $(TOP)/$(X)tcc$(EXESUF)
XCC = $(XTCC)
XAR = $(XTCC) -ar
XFLAGS-unx = -B$(TOPSRC)
XFLAGS-win = -B$(TOPSRC)/win32 -I$(TOPSRC)/include
XFLAGS = $(XFLAGS$(XCFG))
XCFG = $(or $(findstring -win,$T),-unx)

# in order to use gcc, tyoe: make <target>-libtcc1-usegcc=yes
arm-libtcc1-usegcc ?= no

ifeq "$($(T)-libtcc1-usegcc)" "yes"
 XCC = $(CC)
 XAR = $(AR)
 XFLAGS = $(CFLAGS) -fPIC
endif

ifdef CONFIG_OSX
 XFLAGS += -D_ANSI_SOURCE
endif

ARM64_O = lib-arm64.o

OBJ-arm64 = $(ARM64_O)

$(BIN) : $(patsubst %.o,$(X)%.o,$(OBJ-$T))
	$(XAR) rcs $@ $^

$(X)%.o : %.c
	$(XCC) -c $< -o $@ $(XFLAGS)

$(X)%.o : %.S
	$(XCC) -c $< -o $@ $(XFLAGS)

$(X)crt1w.o : crt1.c
$(X)wincrt1w.o : wincrt1.c

clean :
	rm -f *.a *.o $(BIN)
