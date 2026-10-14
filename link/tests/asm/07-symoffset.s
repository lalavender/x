// 07-symoffset.s —— 符号取值（st_value）验收。
//
// 用途：确认符号表里的 value 是「节内偏移」而不是 0。跨对象调用错位的根因
// 就是这里：若 helper 的 value 记成 0，链接器算出来的分支位移会把 bl 指向
// 自己，形成死循环。
	.text
	.globl _start
_start:
	bl	target
	mov	x8, #93
	svc	#0

	.balign 16
	.globl target
target:
	mov	w0, #42
	ret
