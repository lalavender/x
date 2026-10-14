// GOT 窄访问：LP64 下只有 64 位访存有对应重定位。
	.text
	ldr	w0, [x0, sym@GOTPAGEOFF]
