// 01-exit42.s —— 最小可执行：只有一个 _start，直接调 exit(42)。
//
// 这是链接器验收的第一层：单对象、无外部符号、无数据。
// 链出来的映像必须能在 Linux/AArch64 上跑起来并把退出码 42 交给 shell——
// 这一条同时证明：ELF 头/程序头/入口地址正确，静默可执行、无解释器，
// 内核能装载并跳到 _start。
	.text
	.globl _start
_start:
	mov	w0, #42          // 退出码
	mov	x8, #93          // Linux aarch64 的 exit 系统调用号
	svc	#0
