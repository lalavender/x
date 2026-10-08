	.text
	.globl _h
_h:
	adrp	x0, _g@PAGE
	add	x0, x0, _g@PAGEOFF
	ldr	x0, [x0, _g@PAGEOFF]
	ldrb	w0, [x0, _g@PAGEOFF]
	ldrh	w0, [x0, _g@PAGEOFF]
	ldrsw	x0, [x0, _g@PAGEOFF]
	bl	_g
	b	_g
	beq	_g
	cbz	x0, _g
	cbnz	x0, _g
	ret
	.data
	.xword	_g
	.balign	8
	.byte	1, 2, 3, 4
	.zero	4
	.bss
	.balign	16
	.skip	32
