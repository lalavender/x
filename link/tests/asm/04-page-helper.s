// 04-page-helper.s —— 页差与长距离分支的验收（被引用对象）。
//
// 这个对象把两个「必须按最终地址计算」的量同时推到远处：
//
//   1. 长距离 CALL26：先放一条 nop 再 .balign 65536，helper 的节内偏移因此是
//      0x10000（若 .balign 直接落在节首则不需要填充、偏移仍是 0——必须先有
//      内容，对齐才有实际效果）。链接后 helper 距离 _start 超过 64 KiB，
//      分支位移必须按真实地址算。
//   2. 非零页差 ADRP：answer 在 .data，链接后被放进可写段；主对象从 .text 用
//      adrp/add 取它的地址，页差因此不是 0。ADRP 写的是「页差」，写成节内
//      偏移或 0 时，本用例会取到错误的地址并给出错误的退出码。
	.data
	.globl answer
	.balign 4
answer:
	.word	6

	.text
	.globl helper
	nop
	.balign	65536
helper:
	mov	w0, #42
	ret
