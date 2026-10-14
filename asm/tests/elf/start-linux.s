// _start（Linux/GNU 方言）：把内核放在栈上的 argc/argv 交给 main，按 main 的
// 返回值退出（exit 93）。与 start.s 的区别只在符号名——start.s 配上 Darwin
// 方言语料用（_main/_write），这份配 Linux 方言语料用（main，运行时原语由
// 编译器发射在同一对象里）。
	.text
	.globl _start
_start:
	ldr	x0, [sp]            // argc
	add	x1, sp, #8          // argv
	bl	main
	mov	x8, #93             // exit
	svc	#0
