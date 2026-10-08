// yh 运行时的三个 OS 原语桩：_write / _mmap / _munmap。
// AArch64 Linux 系统调用号：write=64, mmap=222, munmap=215, exit=93。
	.text

	.globl _write
_write:                      // (fd, buf, n) -> 写入字节数
	mov	x8, #64
	svc	#0
	ret

	.globl _mmap
_mmap:                       // (addr, len, prot, flags, fd, off) -> 地址
	mov	x8, #222
	svc	#0
	ret

	.globl _munmap
_munmap:                     // (addr, len)
	mov	x8, #215
	svc	#0
	ret
