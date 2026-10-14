// 02-twoobj-main.s —— 多对象验收的主对象。
//
// 证明三件事：
//   1. 跨对象的 CALL26：bl helper 的目标符号在另一个对象里，必须在链接期
//      解析并回填 26 位位移；
//   2. 跨对象的数据地址：用汇编器实际发射的 adrp + add 取全局变量 answer
//      的地址（编译器发射的就是这一对），链接期按 (页差, 低 12 位) 回填；
//   3. 自己的入口 _start 从初始栈上取 argc/argv，按 ABI 调 helper。
//
// 期望退出码 = answer(7) + helper(42) = 49。
	.text
	.globl _start
_start:
	ldr	x0, [sp]            // argc
	add	x1, sp, #8          // argv
	bl	helper              // 跨对象调用（CALL26）
	mov	w19, w0             // 保存 helper 的返回值

	adrp	x2, answer@PAGE     // 跨对象数据地址：页
	add	x2, x2, answer@PAGEOFF  // 页内偏移
	ldr	w3, [x2]            // answer 的值（应为 7）

	add	w0, w19, w3         // 42 + 7
	mov	x8, #93
	svc	#0
