TOP = ../..
include $(TOP)/Makefile
SRC = $(TOPSRC)/tests/tests2
VPATH = $(SRC)

TESTS = $(patsubst %.c,%.test,$(sort $(notdir $(wildcard $(SRC)/*.c))))

# 某些测试并非在所有平台上都通过，暂时移除它们
SKIP = 34_array_assignment.test # 数组赋值不在 C 标准中
ifeq ($(CONFIG_arm_eabi),yes) # 不是 ARM 软浮点
 SKIP += 22_floating_point.test
endif
ifdef CONFIG_OSX
 SKIP += 40_stdio.test 42_function_pointer.test
 FLAGS += -w
endif
ifeq ($(ARCH),x86_64)
 SKIP += 73_arm64.test
endif
ifeq (,$(filter i386,$(ARCH)))
 SKIP += 98_al_ax_extend.test 99_fastcall.test
endif
ifeq (,$(filter i386 x86_64,$(ARCH)))
 SKIP += 85_asm-outside-function.test
endif
ifeq (-$(findstring gcc,$(CC))-,--)
 SKIP += $(patsubst %.expect,%.test,$(GEN-ALWAYS))
endif
ifeq (-$(CONFIG_WIN32)-$(CONFIG_i386)$(CONFIG_arm)-,--yes-)
 SKIP += 95_bitfields%.test # 在 32 位非 Windows 平台上 type_align 不同
endif

# 某些测试可能需要参数
ARGS =
31_args.test : ARGS = arg1 arg2 arg3 arg4 arg5
46_grep.test : ARGS = '[^* ]*[:a:d: ]+\:\*-/: $$' $(SRC)/46_grep.c

# 还有些测试在 -run 下测不到正确的东西
NORUN =
42_function_pointer.test : NORUN = true

# 某些测试可能需要不同的选项
FLAGS =
76_dollars_in_identifiers.test : FLAGS += -fdollars-in-identifiers

# 这些测试会逐个运行同一文件中的多个片段
60_errors_and_warnings.test : FLAGS += -dt
96_nodata_wanted.test : FLAGS += -dt

# 总是生成某些 .expect（不要把它们放进 GIT），
GEN-ALWAYS =
# GEN-ALWAYS += 95_bitfields.expect # 无法工作

# 使用 ms 编译器生成真正兼容 ms 的位域
95_bitfields_ms.test : GEN = $(GEN-MSC)

# 在警告/错误信息中过滤源目录（用于源外构建）
FILTER = 2>&1 | sed 's,$(SRC)/,,g'
# 过滤某些总是出现的警告
ifeq (-$(findstring arm,$(ARCH))-,-arm-)
FILTER += 2>&1 | grep -v 'warning: soft float ABI currently not supported'
endif

all test tests2.all: $(filter-out $(SKIP),$(TESTS)) ;

%.test: %.c %.expect
	@echo Test: $*...
	@$(if $(NORUN),$(T1),$(T2)) $(if $(NODIFF),,$(T3))

T1 = $(TCC) $(FLAGS) $< -o a.exe && ./a.exe $(ARGS)
T2 = $(TCC) $(FLAGS) -run $< $(ARGS)
T3 = $(FILTER) >$*.output 2>&1 || true \
     && diff -Nbu $(filter %.expect,$^) $*.output \
     && rm -f $*.output $(filter $*.expect,$(GEN-ALWAYS))

# 运行单个测试并更新 .expect 文件，例如 "make tests2.37+"
tests2.%+:
	@$(MAKE) $(call F2,$(call F1,$*)) --no-print-directory

# 只运行 tcc 查看输出，例如 "make tests2.37-"
tests2.%-:
	@$(MAKE) $(call F1,$*) NODIFF=true --no-print-directory

# 运行单个测试，例如 "make tests2.37"
tests2.%:
	@$(MAKE) $(call F1,$*) --no-print-directory

F1 = $(or $(filter $1_%,$(TESTS)),$1_???.test)
F2 = $1 UPDATE="$(patsubst %.test,%.expect,$1)"

# 用 gcc 自动生成 .expect 文件：
%.expect :
	@echo Generating: $@
	@$(call GEN,$(SRC)/$*.c) $(FILTER) >$@ 2>&1
	@rm -f *.exe *.obj *.pdb

# 若 FLAGS 中有 -dt，则用 TCC 生成 .expect
GEN = $(if $(filter -dt,$(FLAGS)),$(GEN-TCC),$(GEN-CC))
GEN-CC = $(CC) -w -std=gnu99 $(FLAGS) $1 -o a.exe && ./a.exe $(ARGS)
GEN-TCC = $(TCC) $(FLAGS) -run $1 $(ARGS)
GEN-MSC = $(MS-CC) $1 && ./$(basename $@).exe
MS-CC = cl

# 告诉 make 不要删除
.PRECIOUS: %.expect

# 强制为这些文件生成 .expect
$(sort $(GEN-ALWAYS) $(UPDATE)) : force
force:

clean:
	rm -f fred.txt *.output a.exe $(GEN-ALWAYS)
