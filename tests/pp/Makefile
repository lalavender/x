#
# 致谢：01..13.c 来自 pcc cpp-tests 测试套件
#

TOP = ../..
include $(TOP)/Makefile
SRC = $(TOPSRC)/tests/pp
VPATH = $(SRC)

files = $(patsubst %.$1,%.test,$(notdir $(wildcard $(SRC)/*.$1)))
TESTS = $(call files,c) $(call files,S)

all test : $(sort $(TESTS))

DIFF_OPTS = -Nu -b -B

# 在警告/错误信息中过滤源目录（用于源外构建）
FILTER = 2>&1 | sed 's,$(SRC)/,,g'

%.test: %.c %.expect
	@echo PPTest $* ...
	-@$(TCC) -E -P $< $(FILTER) >$*.output 2>&1 ; \
	    diff $(DIFF_OPTS) $(SRC)/$*.expect $*.output \
	    && rm -f $*.output

%.test: %.S %.expect
	@echo PPTest $* ...
	-@$(TCC) -E -P $< $(FILTER) >$*.output 2>&1 ; \
	    diff $(DIFF_OPTS) $(SRC)/$*.expect $*.output \
	    && rm -f $*.output

# 用 gcc 自动生成 .expect 文件：
%.expect: # %.c
	gcc -E -P $*.[cS] >$*.expect 2>&1

# 告诉 make 不要删除
.PRECIOUS: %.expect

clean:
	rm -f *.output

02.test : DIFF_OPTS += -w
# 15.test : DIFF_OPTS += -I"^XXX:"

# diff 选项：
# -b 忽略空白改动
# -w 忽略所有空白
# -B 忽略空行
# -I <RE> 忽略匹配 RE 的行
