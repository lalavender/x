	.text
	.globl _i
_i:
	ldr	x0, [sp], #16
	str	x0, [sp, #-16]!
	strb	w10, [x1], #1
	ldrb	w10, [x0], #1
	ldp	x29, x30, [sp], #16
	stp	x29, x30, [sp, #-16]!
	ldr	x30, [x29, #376]
	str	w0, [x29, #-32]
	ldr	x1, [x2, x3]
	strb	w9, [x23, x24]
	ret
	nop
	brk	#1
	svc	#0
	hlt	#0
	dsb	sy
	dmb	ish
	isb
	ret
