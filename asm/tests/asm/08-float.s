// 08-float.s —— 标量浮点子集
//
// 覆盖契约里冻结的六个族：fadd/fsub/fmul/fdiv、fcmp、fcvt（s↔d）、
// fcvtzs、scvtf、fmov（通用→浮点），以及浮点访存。
//
// 浮点访存的编码跟同宽整数访存一模一样，只多一个 V 位（bit26）；GOT、
// 宽位、舍入模式等本子集不支持的形态一律报诊断。

	.text
	.globl	_main
_main:
	fadd	s0, s1, s2
	fsub	d3, d4, d5
	fmul	s6, s7, s8
	fdiv	d9, d10, d11
	fcmp	s0, s1
	fcmp	d0, d1
	fcvt	s0, d1
	fcvt	d0, s1
	fcvtzs	x0, s0
	fcvtzs	w1, d2
	scvtf	s0, x0
	scvtf	d0, w1
	fmov	s0, w0
	fmov	d0, x0
	str	s0, [x0]
	ldr	d1, [x0]
	str	d2, [x1, #8]
	ldr	s3, [x2, #4]
	fadd	d20, d21, d22
	fmov	d31, x31
	fcvt	s31, d30
	ret