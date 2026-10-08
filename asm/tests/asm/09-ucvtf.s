// ucvtf：无符号整数转标量浮点。编译器发射浮点窄化时用 ucvtf（scvtf 是有符号），
// 目标机器码与 scvtf 只差 bit16。
	.text
	.globl	_main
_main:
	mov	x0, #-1
	ucvtf	d0, x0
	ucvtf	d0, w0
	mov	w1, #7
	ucvtf	s3, w1
	mov	x2, #5
	ucvtf	d5, x2
	ret