#
# Tiny C Compiler Makefile for libtcc1.a
#

TOP = ..
include $(TOP)/Makefile
VPATH = $(TOPSRC)/lib
T = $(or $(CROSS_TARGET),$(NATIVE_TARGET),unknown)
X = $(if $(CROSS_TARGET),$(CROSS_TARGET)-)
BIN = $(TOP)/$(X)libtcc1.a

XTCC ?= $(TOP)/$(X)tcc$(EXESUF)
XCC = $(XTCC)
XAR = $(XTCC) -ar
XFLAGS = -B$(TOPSRC)

# in order to use gcc, type: make <target>-libtcc1-usegcc=yes
arm64-libtcc1-usegcc ?= no

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

clean :
	rm -f *.a *.o $(BIN)
