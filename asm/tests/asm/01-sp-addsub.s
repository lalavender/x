	.text
	.globl _f
_f:
	sub	sp, sp, x9
	add	sp, sp, x0
	cmp	sp, x0
	cmp	x0, x1
	add	x0, x1, x2
	sub	x0, sp, #16
	mov	x0, sp
	mov	sp, x0
	mov	x0, xzr
	mov	xzr, x0
	add	w0, w1, w2
	cmp	w0, w1
	ret
