// _start：把内核放在栈上的 argc/argv 转成 yh 运行时的调用约定，调 _main 后
// 按它的返回值退出。链接时需要 _main（来自被测对象）与 yhr_* 桩。
	.text
	.globl _start
_start:
	ldr	x19, [sp]          // argc
	add	x20, sp, #8         // argv
	mov	x0, x19
	mov	x1, x20
	bl	_main
	mov	x8, #93             // exit
	svc	#0
