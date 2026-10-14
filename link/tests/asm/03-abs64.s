// 03-abs64.s —— 绝对地址（R_AARCH64_ABS64）与 .rodata 验收。
//
// 证明：
//   1. .data 里的 .xword 会被写成目标符号的**最终虚拟地址**（8 字节绝对量），
//      链接期才知道值——这条是函数指针/跳转表的基础；
//   2. .rodata 参与合并并被放进只读段；
//   3. 链接期填进去的地址真的能用：blr 到表里的地址，返回值必须是 42。
	.data
	.globl table
	.balign 8
table:
	.xword	target              // 绝对地址，链接期回填

	.section .rodata
	.globl magic
magic:
	.word	0x2a

	.text
	.globl _start
_start:
	adrp	x1, table@PAGE
	add	x1, x1, table@PAGEOFF
	ldr	x2, [x1]            // x2 = target 的绝对地址
	blr	x2                  // 调过去，期望 w0 = 42
	mov	x8, #93
	svc	#0

	.globl target
target:
	mov	w0, #42
	ret
