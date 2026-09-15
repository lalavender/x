#
# Tiny C Compiler Makefile - tests
#

TOP = ..
include $(TOP)/Makefile
VPATH = $(TOPSRC)/tests $(TOPSRC) $(TOPSRC)/src/core $(TOP)
CFLAGS := $(filter-out -W% -g% -O%,$(CFLAGS)) -I$(TOPSRC) $(LDFLAGS)

# 要运行哪些测试
TESTS = \
 hello-exe \
 hello-run \
 libtest \
 test3 \
 memtest \
 dlltest \
 abitest \
 asm-c-connect-test \
 vla_test-run \
 cross-test \
 tests2-dir \
 pp-dir

BTESTS = test1b test3b btest

# test4 -- -static 有问题
# asmtest / asmtest2 -- 与 gcc 有微小差异
# btest -- 在 i386 上可用

# 只有 i386 支持边界检查
ifneq ($(ARCH),i386)
 TESTS := $(filter-out $(BTESTS),$(TESTS))
endif
ifdef CONFIG_OSX # 仅 -run
 TESTS := hello-run libtest tests2-dir pp-dir
endif
ifeq (,$(filter arm64 i386 x86_64,$(ARCH)))
 TESTS := $(filter-out vla_test-run,$(TESTS))
endif
ifeq ($(CONFIG_arm_eabi),yes)
 TESTS := $(filter-out test3,$(TESTS))
endif
ifeq (,$(filter i386 x86_64,$(ARCH)))
 TESTS := $(filter-out dlltest asm-c-connect-test,$(TESTS))
endif
ifndef CONFIG_cross
 TESTS := $(filter-out cross-%,$(TESTS))
endif

RUN_TCC = $(NATIVE_DEFINES) -run $(TOPSRC)/src/core/tcc.c $(TCCFLAGS)
DISAS = objdump -d
DUMPTCC = (set -x; $(TOP)/tcc -vv; ldd $(TOP)/tcc; exit 1)

all test : clean-s $(TESTS)

hello-exe: ../examples/ex1.c
	@echo ------------ $@ ------------
	$(TCC) $< -o hello$(EXESUF) && ./hello$(EXESUF) || $(DUMPTCC)

hello-run: ../examples/ex1.c
	@echo ------------ $@ ------------
	$(TCC) -run $< || $(DUMPTCC)

libtest: libtcc_test$(EXESUF)
	@echo ------------ $@ ------------
	./libtcc_test$(EXESUF) $(TCCFLAGS)

libtcc_test$(EXESUF): libtcc_test.c $(LIBTCC)
	$(CC) -o $@ $^ $(CFLAGS) $(LIBS)

%-dir:
	@echo ------------ $@ ------------
	$(MAKE) -k -C $*

# test.ref —— 用 cc 生成
test.ref: tcctest.c
	$(CC) -o tcctest.gcc $< $(NATIVE_DEFINES) $(CFLAGS) -w -O0 -std=gnu99 -fno-omit-frame-pointer
	./tcctest.gcc > $@

# 自动测试
test1 test1b: tcctest.c test.ref
	@echo ------------ $@ ------------
	$(TCC) -run $< > test.out1
	@diff -u test.ref test.out1 && echo "Auto Test OK"

# 迭代测试 2（先编译 tcc，再编译 tcctest.c！）
test2 test2b: tcctest.c test.ref
	@echo ------------ $@ ------------
	$(TCC) $(RUN_TCC) $(RUN_TCC) -run $< > test.out2
	@diff -u test.ref test.out2 && echo "Auto Test2 OK"

# 迭代测试 3（编译 tcc，再编译 tcc，再编译 tcctest.c！）
test3 test3b: tcctest.c test.ref
	@echo ------------ $@ ------------
	$(TCC) $(RUN_TCC) $(RUN_TCC) $(RUN_TCC) -run $< > test.out3
	@diff -u test.ref test.out3 && echo "Auto Test3 OK"

test%b : TCCFLAGS += -b

# 二进制输出测试
test4: tcctest.c test.ref
	@echo ------------ $@ ------------
# 对象文件 + 链接输出
	$(TCC) -c -o tcctest3.o $<
	$(TCC) -o tcctest3 tcctest3.o
	./tcctest3 > test3.out
	@if diff -u test.ref test3.out ; then echo "Object Auto Test OK"; fi
# 动态输出
	$(TCC) -o tcctest1 $<
	./tcctest1 > test1.out
	@if diff -u test.ref test1.out ; then echo "Dynamic Auto Test OK"; fi
# 动态输出 + 边界检查
	$(TCC) -b -o tcctest4 $<
	./tcctest4 > test4.out
	@if diff -u test.ref test4.out ; then echo "BCheck Auto Test OK"; fi
# 静态输出
	$(TCC) -static -o tcctest2 $<
	./tcctest2 > test2.out
	@if diff -u test.ref test2.out ; then echo "Static Auto Test OK"; fi

# 用 tcc 创建 libtcc.so/.dll 和 tcc(.exe) 前端并运行它们
dlltest:
	@echo ------------ $@ ------------
	$(TCC) $(NATIVE_DEFINES) -DLIBTCC_AS_DLL $(TOPSRC)/src/core/libtcc.c $(LIBS) -shared -o libtcc2$(DLLSUF)
	$(TCC) $(NATIVE_DEFINES) -DONE_SOURCE=0 $(TOPSRC)/src/core/tcc.c libtcc2$(DLLSUF) $(LIBS) -Wl,-rpath=. -o tcc2$(EXESUF)
	./tcc2$(EXESUF) $(TCCFLAGS) $(RUN_TCC) -run $(TOPSRC)/examples/ex1.c
	@echo ------------ $@ with PIC ------------
	$(CC) $(CFLAGS) -fPIC $(NATIVE_DEFINES) -DLIBTCC_AS_DLL -c $(TOPSRC)/src/core/libtcc.c
	$(TCC) libtcc.o $(LIBS) -shared -o libtcc2$(DLLSUF)
	$(TCC) $(NATIVE_DEFINES) -DONE_SOURCE=0 $(TOPSRC)/src/core/tcc.c libtcc2$(DLLSUF) $(LIBS) -Wl,-rpath=. -o tcc2$(EXESUF)
	./tcc2$(EXESUF) $(TCCFLAGS) $(RUN_TCC) -run $(TOPSRC)/examples/ex1.c
	@rm tcc2$(EXESUF) libtcc2$(DLLSUF)

memtest:
	@echo ------------ $@ ------------
	$(CC) $(CFLAGS) $(NATIVE_DEFINES) -DMEM_DEBUG=2 $(TOPSRC)/src/core/tcc.c $(LIBS) -o memtest-tcc$(EXESUF)
	./memtest-tcc$(EXESUF) $(TCCFLAGS) $(NATIVE_DEFINES) $(TOPSRC)/src/core/tcc.c $(LIBS)
	./memtest-tcc$(EXESUF) $(TCCFLAGS) $(NATIVE_DEFINES) -run $(TOPSRC)/src/core/tcc.c $(TCCFLAGS) $(TOPSRC)/tests/tcctest.c


# 内存与边界检查自动测试
BOUNDS_OK  = 1 4 8 10 14
BOUNDS_FAIL= 2 5 7 9 11 12 13 15

btest: boundtest.c
	@echo ------------ $@ ------------
	@for i in $(BOUNDS_OK); do \
	   echo ; echo --- boundtest $$i ---; \
	   if $(TCC) -b -run $< $$i ; then \
	       echo succeeded as expected; \
	   else\
	       echo Failed positive test $$i ; exit 1 ; \
	   fi ;\
	done ;\
	for i in $(BOUNDS_FAIL); do \
	   echo ; echo --- boundtest $$i ---; \
	   if $(TCC) -b -run $< $$i ; then \
	       echo Failed negative test $$i ; exit 1 ;\
	   else\
	       echo failed as expected; \
	   fi ;\
	done ;\
	echo; echo Bound test OK

# 速度测试
speedtest: ex2 ex3
	@echo ------------ $@ ------------
	time ./ex2 1238 2 3 4 10 13 4
	time $(TCC) -run $(TOPSRC)/examples/ex2.c 1238 2 3 4 10 13 4
	time ./ex3 35
	time $(TCC) -run $(TOPSRC)/examples/ex3.c 35

weaktest: tcctest.c test.ref
	$(TCC) -c $< -o weaktest.tcc.o
	$(CC) -c $< -o weaktest.gcc.o $(NATIVE_DEFINES) $(CFLAGS) -w -O0 -std=gnu99 -fno-omit-frame-pointer
	objdump -t weaktest.tcc.o | grep ' w ' | sed -e 's/.* \([a-zA-Z0-9_]*\)$$/\1/' | LC_ALL=C sort > weaktest.tcc.o.txt
	objdump -t weaktest.gcc.o | grep ' w ' | sed -e 's/.* \([a-zA-Z0-9_]*\)$$/\1/' | LC_ALL=C sort > weaktest.gcc.o.txt
	diff weaktest.gcc.o.txt weaktest.tcc.o.txt && echo "Weak Auto Test OK"

ex%: $(TOPSRC)/examples/ex%.c
	$(CC) -o $@ $< $(CFLAGS)

# 小型汇编器测试
asmtest.ref: asmtest.S
	$(CC) -Wa,-W -o asmtest.ref.o -c asmtest.S
	objdump -D asmtest.ref.o > asmtest.ref

asmtest asmtest2: asmtest.ref
	@echo ------------ $@ ------------
	$(TCC) $(MAYBE_RUN_TCC) -c asmtest.S
	objdump -D asmtest.o > asmtest.out
	@if diff -u --ignore-matching-lines="file format" asmtest.ref asmtest.out ; then echo "ASM Auto Test OK"; fi

# 用自举编译出的 tcc 测试汇编器
asmtest2: MAYBE_RUN_TCC = $(RUN_TCC)

# 检查 libtcc 生成的代码与
# CC 生成的代码二进制兼容
abitest-cc$(EXESUF): abitest.c $(LIBTCC)
	$(CC) -o $@ $^ $(CFLAGS) $(LIBS) -w

abitest-tcc$(EXESUF): abitest.c libtcc.c
	$(TCC) -o $@ $^ $(NATIVE_DEFINES) $(LIBS)

ABITESTS := abitest-cc$(EXESUF)
ifneq ($(CONFIG_arm_eabi),yes) # 不是 ARM 软浮点
 ABITESTS += abitest-tcc$(EXESUF)
endif

abitest: $(ABITESTS)
	@echo ------------ $@ ------------
	./abitest-cc$(EXESUF) $(TCCFLAGS)
ifneq ($(CONFIG_arm_eabi),yes) # 不是 ARM 软浮点
	./abitest-tcc$(EXESUF) $(TCCFLAGS)
endif

vla_test$(EXESUF): vla_test.c
	$(TCC) -o $@ $^

vla_test-run: vla_test$(EXESUF)
	@echo ------------ $@ ------------
	./vla_test$(EXESUF)

asm-c-connect$(EXESUF): asm-c-connect-1.c asm-c-connect-2.c
	$(TCC) -o $@ $^

asm-c-connect-%.o: asm-c-connect-%.c
	$(TCC) -c -o $@ $<

asm-c-connect-sep$(EXESUF): asm-c-connect-1.o asm-c-connect-2.o
	$(TCC) -o $@ $^

asm-c-connect-test: asm-c-connect$(EXESUF) asm-c-connect-sep$(EXESUF)
	@echo ------------ $@ ------------
	./asm-c-connect$(EXESUF) > asm-c-connect.out1 && cat asm-c-connect.out1
	./asm-c-connect-sep$(EXESUF) > asm-c-connect.out2 && cat asm-c-connect.out2
	@diff -u asm-c-connect.out1 asm-c-connect.out2 && echo "ok"

cross-test :
	@echo ------------ $@ ------------
	$(TOP)/arm64-tcc$(EXESUF) $(TCCFLAGS) -c $(TOPSRC)/examples/ex3.c && echo "ok"

# 开发用目标
%.bin: %.c tcc
	$(TCC) -g -o $@ $<
	$(DISAS) $@

instr: instr.o
	objdump -d instr.o

instr.o: instr.S
	$(CC) -o $@ -c $< -O2 -Wall -g

cache: tcc_g
	cachegrind ./tcc_g -o /tmp/linpack -lm bench/linpack.c
	vg_annotate tcc.c > /tmp/linpack.cache.log

# 清理
clean:
	rm -f *~ *.o *.a *.bin *.i *.ref *.out *.out? *.out?b *.cc *.gcc
	rm -f *-cc *-gcc *-tcc *.exe hello libtcc_test vla_test tcctest[1234]
	rm -f asm-c-connect$(EXESUF)
	rm -f ex? tcc_g weaktest.*.txt *.def
	@$(MAKE) -C tests2 $@
	@$(MAKE) -C pp $@

# 静默清理，在运行测试前使用
clean-s:
	@$(MAKE) -s --no-print-directory clean
