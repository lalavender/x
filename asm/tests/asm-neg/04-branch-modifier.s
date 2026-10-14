// 分支目标带符号修饰符：语义上无意义，必须拒绝而不是静默编成 b #0。
	.text
target:
	ret
	b	target@PAGEOFF
