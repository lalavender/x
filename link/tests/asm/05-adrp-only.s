// 05-adrp-only.s —— 只做 adrp/add 取址，不做任何访存。
//
// 用途：把「页寻址重定位」与「访存/段映射」两类问题分开。
// 若本用例能跑出 43（42+1），说明 adrp/add 的重定位正确；
// 再挂就说明问题在访存或段映射上。
	.text
	.globl _start
_start:
	adrp	x1, target@PAGE
	add	x1, x1, target@PAGEOFF
	mov	x2, x1              // 只是取址，不访存
	mov	x8, #93
	mov	w0, #43
	svc	#0

	.globl target
target:
	mov	w0, #42
	ret
