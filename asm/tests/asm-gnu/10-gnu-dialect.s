// GNU dialect corpus: the exact forms the yh compiler emits for Linux targets
// (bare symbol after adrp, :lo12:sym on add and on loads/stores).
// Mach-O input contract still requires @PAGE/@PAGEOFF, so this directory is
// compared against the ELF oracle only.
	.text
	.globl	gnu_fn
gnu_fn:
	stp	x29, x30, [sp, #-16]!
	mov	x29, sp
	adrp	x0, gnu_data
	add	x0, x0, :lo12:gnu_data
	ldr	x1, [x0, :lo12:gnu_data]
	ldr	w2, [x0, :lo12:gnu_data]
	ldrsw	x3, [x0, :lo12:gnu_data]
	ldrb	w4, [x0, :lo12:gnu_data]
	ldrh	w5, [x0, :lo12:gnu_data]
	ldrsb	x6, [x0, :lo12:gnu_data]
	ldrsh	x7, [x0, :lo12:gnu_data]
	str	x1, [x0, :lo12:gnu_data]
	strb	w2, [x0, :lo12:gnu_data]
	strh	w5, [x0, :lo12:gnu_data]
	adrp	x9, .Lgnu_loc
	add	x9, x9, :lo12:.Lgnu_loc
	bl	gnu_helper
	ldp	x29, x30, [sp], #16
	ret
.Lgnu_loc:
	ret

	.globl	gnu_helper
gnu_helper:
	mov	x0, #0
	ret

	.data
	.balign	8
	.globl	gnu_data
gnu_data:
	.xword	gnu_helper
	.word	7
	.hword	3
	.byte	1
