// adrp 的符号修饰符用错：:lo12: 是取低 12 位，不能用在页取址上。
	.text
	adrp	x0, :lo12:sym
