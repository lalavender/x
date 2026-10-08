	.text
	.globl _k
_k:
	svc	#0
	nop
	brk	#1
	hlt	#0
	dsb	sy
	dmb	ish
	isb
	dsb	ishld
	isb
	ret
