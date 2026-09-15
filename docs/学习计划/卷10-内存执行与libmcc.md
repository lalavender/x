# 卷10 · 不存文件也能跑

> **本卷目标**：把卷 2 偷学的"黑魔法"升级成正经功能——`mcc -run`：
> 编译完直接**在内存里**布局、贴邮票、跑起来；再学"向宿主进程借 printf"；
> 最后把 mcc 拆成库（libmcc），让别的程序调用你的编译器。
> **预计**：5 篇，约 1 周。

TCC 最出名的招牌：`tcc -run hello.c`——没有 .o、没有 a.out、没有 ld，
CPU 直接执行刚生成的字节。C 语言从此可以当脚本写。
原理你在卷 2.2 已经摸过一次了，现在把它做扎实、做完整。

---

## 10.1 两遍布局：先问要多大地盘，再摆

- **教什么**：`tcc_relocate(NULL)` 先**空跑一遍**算出所有纸带总长（含对齐、代码和数据
  要分开摆——缓存行友好）；`mmap(len, RW)` 拿地盘；
  第二遍给每条纸带定 `sh_addr` 并贴邮票（9.3 的代码复用！只是基准地址从"文件里的"变成"内存里的"）。
- **你要写出**：`mcc_relocate(void *buf)`：buf=NULL 返回所需大小；
  `mcc -run`：mmap 后把纸带 memcpy 进去。
- **通关暗号**：`./mcc -run t.c`（t.c 里 `return 42;`）→ shell 里 `echo $?` 是 42。
- **TCC 对照**：`src/core/tccrun.c:59` `tcc_relocate()`（两遍协议）、
  `:179` `tcc_relocate_ex()`（:203 起那个 `for k=0..1` 的循环就是"代码区、数据区"两遍布局）。

## 10.2 页要"可执行" + 向宿主借符号

- **教什么**：现代 OS 不许执行随便写的内存 → `mprotect(RX)`（写完代码后改权限；
  ARM 还要 `__clear_cache` 刷指令缓存——TCC 在 tccrun.c:280 全干了）。
  **最妙的一招**：内存模式的"未定义符号"，
  链接器直接 `dlsym(RTLD_DEFAULT, "printf")` **从当前进程自己**身上找地址
  ——mcc 进程本来就链接了 libc，printf 地址现成的！这就是 `tcc -run` 能用 printf 的全部秘密。
- **你要写出**：mprotect + dlsym 兜底解析；崩溃处理先不管（10.3）。
- **通关暗号**：`./mcc -run` 跑一个调用宿主 `printf("hi\n")` 的程序 → 真打印 hi。
  （对，这是**你的编译器+你的链接器+OS 的 mmap**一起完成的。）
- **TCC 对照**：`src/core/tccelf.c:791-799`（relocate_syms 里那个 dlsym）；
  `src/core/tccrun.c:116` `tcc_run()` 全文只有 30 行，读它。

## 10.3 崩了要知道是谁：debug 信息入门

- **教什么**：加 `-g`：给每个函数记 `{名字, .text 起始偏移}`；
  每行代码记 `{行号, 偏移}`。装个信号处理器（SIGSEGV/SIGBUS），
  崩溃时从硬件上下文抠出 RIP → 查表 → 打印"第 N 行, 函数 f"。
  TCC 用 STABS 格式（`src/formats/stab.h`），你用简化表即可——思想一样。
- **通关暗号**：故意写 `int *p=0; *p=1;`，mcc -run 崩溃时打印 `在 main 第 2 行挂了`。
- **TCC 对照**：`src/core/tccrun.c:338` `rt_printline`、`:505` `sig_error`、
  `:571` `rt_get_caller_pc`；写表端 `src/core/tccgen.c` 里 `tcc_debug_*`（STABS）。

## 10.4 libmcc：把你的编译器装进别人口袋

- **教什么**：拆 API：`mcc_new / mcc_compile_string / mcc_relocate / mcc_get_symbol`。
  让宿主程序**运行时现编现用**你写的 C 函数——插件系统的底层全是这个套路。
- **你要写出**：`libmcc.c`（mcc 核心改造成库，main 变薄）+ demo：
  宿主里 `int (*fib)(int) = mcc_get_symbol(...)` 直接当函数指针调。
- **通关暗号**：demo 打印 `嵌入的 fib(30)=832040`。
- **TCC 对照**：`libtcc.h`（就 25 个函数，全用过一遍）+ `tests/libtcc_test.c`
  ——你会 1:1 复刻它，因为它和 tcc 的关系就是你 mcc 和 libmcc 的关系。

## 10.5 本卷毕业考：C 脚本

- **你要写出**：文件头 `#!/path/mcc -run` 的 `.c` 脚本直接 `./fib.c` 运行
  （shebang + 内存执行，卷 2/8/9/10 全链验收）。
- **通关暗号**：写个 30 行脚本：读 argv 个数、算 3n+1 步数、用 printf 输出——全对。

---

## ✅ 本卷通关检查表

- [ ] 能解释两遍 relocate 为什么不能合成一遍
- [ ] dlsym 借符号的原理能给别人画图讲
- [ ] libmcc demo 里你体会到了"编译器即服务"

**下一卷预告**：你已经把每个零件亲手做过一遍。卷 11 不再写 mcc，
而是**回到真 TCC 的源码里"考古"**——对照你自己的实现逐行读，
你会发现：原来你早就写过 TCC 了，只是比它胖一点。
