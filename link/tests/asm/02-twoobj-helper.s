// 02-twoobj-helper.s —— 多对象验收的被调用对象。
//
// 提供 helper（返回 42）与全局变量 answer（初值 7），两者都在另一个对象里，
// 主对象通过 CALL26 与 adrp/add 引用它们。
	.data
	.globl answer
	.balign 4
answer:
	.word	7

	.text
	.globl helper
helper:
	mov	w0, #42
	ret
