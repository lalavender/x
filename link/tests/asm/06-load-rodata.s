// 06-load-rodata.s —— 跨段访存：从 .rodata 读一个字并作为退出码。
//
// 用途：把「adrp/add 重定位」（05 已证）与「跨段访存」分开。
// 若本用例跑出 44，说明只读段映射与访存正确；再挂就要查间接调用或数据段。
	.section .rodata
	.globl magic
	.balign 4
magic:
	.word	44

	.text
	.globl _start
_start:
	adrp	x1, magic@PAGE
	add	x1, x1, magic@PAGEOFF
	ldr	w0, [x1]
	mov	x8, #93
	svc	#0
