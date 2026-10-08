	.text
	.globl _g
_g:
	uxtw	x27, w27
	sxtw	x27, w27
	uxtb	w0, w1
	uxtb	x0, w1
	sxth	x0, w1
	sbfx	x0, x0, #0, #32
	sbfx	x3, x4, #8, #16
	lsl	x0, x1, #5
	asr	w0, w1, #3
	lsr	x0, x1, #63
	csel	x0, x1, x2, ne
	cset	x0, ne
	neg	x0, x1
	mul	x0, x1, x2
	msub	x3, x4, x5, x6
	udiv	x0, x1, x2
	and	x2, x1, #7
	orr	x0, xzr, xzr
	ret
