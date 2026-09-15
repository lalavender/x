/* TCC 编译期配置（AArch64 版）
 *
 * 本文件随源码一起维护，不再由 configure 生成；要改动直接改这里，
 * 或在命令行用 -DCONFIG_TCCDIR=... 覆盖。
 */
#ifndef CONFIG_TCCDIR
/* 存放 libtcc1.a、include 目录下头文件等的目录，可用 tcc 的 -B 选项覆盖 */
# define CONFIG_TCCDIR "/usr/local/lib/tcc"
#endif

/* 版本号：默认由 Makefile 从 VERSION 文件以 -DTCC_VERSION 传入 */
#ifndef TCC_VERSION
# define TCC_VERSION "0.9.27"
#endif

/* 原先由 configure 选择的编译开关，现在直接在这里打开（或 make CFLAGS=-Dxxx）：
 *
 * #define CONFIG_TCC_BCHECK 1  内存/边界检查：tcc -b 可用，需 lib/bcheck.c
 * #define CONFIG_TCC_ASM    1  汇编器（tccasm.c）：asm("...") 与 .byte/.quad 等伪指令
 *                              （AArch64 后端不做指令编码，只支持伪指令/数据）
 * #define CONFIG_TCC_STATIC 1  静态链接 libtcc（不用 dlopen 加载库）
 */
