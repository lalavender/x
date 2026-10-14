// Linux/GNU 方言的运行时外部符号桩，供 tests/elf_link_native.py 的链接运行
// 差分门使用：本工具对象与 clang 对象都用同一份桩（各自汇编），所以桩只要求
// 「确定 + 两边一致」；语义按 Linux 系统调用与 C 库语义原样转接。
// 覆盖编译器语料里出现的外部符号：read/write/open/close/_Exit/abs/strtoul。
	.text

	.globl read
read:                       // (fd, buf, n) -> ssize_t    read = 63
	mov	x8, #63
	svc	#0
	ret

	.globl write
write:                      // (fd, buf, n) -> ssize_t    write = 64
	mov	x8, #64
	svc	#0
	ret

	.globl open
open:                       // (path, flags) -> fd；用 openat(AT_FDCWD, …) = 56
	mov	x3, xzr             // mode = 0
	mov	x0, #-100           // AT_FDCWD
	mov	x8, #56
	svc	#0
	ret

	.globl close
close:                      // (fd) -> int                close = 57
	mov	x8, #57
	svc	#0
	ret

	.globl _Exit
_Exit:                      // (code) -> 不返回            exit_group = 94
	mov	x8, #94
	svc	#0
	ret                     // 正常不会到这里；保留返回便于差分比较

	.globl abs
abs:                        // (v int) -> |v|
	mov	x1, x0
	neg	x2, x0
	cmp	x0, #0
	csel	x0, x2, x1, lt
	ret

	.globl strtoul
strtoul:                    // (s, end, base) -> u64；十进制解析（够用语料）
	mov	x4, x0              // 游标
	mov	x5, xzr             // 累加器
strtoul_loop:
	ldrb	w7, [x4]
	cbz	w7, strtoul_done
	sub	w9, w7, #48          // '0' = 48
	cmp	w9, #9
	b.hi	strtoul_done         // 非数字：停下（end 指向这里）
	mov	x10, #10
	mul	x5, x5, x10
	add	x5, x5, x9
	add	x4, x4, #1
	b	strtoul_loop
strtoul_done:
	cbz	x1, strtoul_ret      // end 为 0 时不回写
	str	x4, [x1]
strtoul_ret:
	mov	x0, x5
	ret
