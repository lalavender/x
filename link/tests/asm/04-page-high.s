// 04-page-high.s —— 页差与长距离分支的验收（主对象）。
//
// 与 04-page-helper.s 配对：
//   * bl helper 是跨对象、跨 64 KiB 的长距离调用（CALL26 按最终地址回填）；
//   * adrp/add 取 answer 的地址时页差非零（ADRP 写页差、ADD 写低 12 位）。
//
// 期望退出码 = helper(42) + answer(6) = 48。
	.text
	.globl _start
_start:
	bl	helper
	mov	w19, w0
	adrp	x2, answer@PAGE
	add	x2, x2, answer@PAGEOFF
	ldr	w3, [x2]
	add	w0, w19, w3
	mov	x8, #93
	svc	#0
