// 07-got.s —— GOT 页寻址与低 12 位
//
// 这两条的重定位都要等链接器建好 GOT 项之后才能算，汇编期一律留重定位：
//   adrp x, sym@GOTPAGE      → R_AARCH64_LD64_GOTPAGE_LO21 (311)
//   ldr  x, [x, sym@GOTPAGEOFF] → R_AARCH64_LD64_GOT_LO12_NC (312)
//
// LP64 下 GOT 只有 64 位形态：更窄的访存 llvm-mc 直接拒绝
// （"4 byte unchecked GOT load/store relocation is not supported in LP64"），
// 本工具同样报诊断而不是凑一个近似编码。

	.text
	.globl	_main
_main:
	adrp	x0, _g@GOTPAGE
	ldr	x0, [x0, _g@GOTPAGEOFF]
	adrp	x19, _h@GOTPAGE
	ldr	x19, [x19, _h@GOTPAGEOFF]
	ldr	x2, [x0]
	add	x0, x0, x2
	ret

	.data
	.globl	_g
_g:
	.xword	1
	.globl	_h
_h:
	.xword	2
