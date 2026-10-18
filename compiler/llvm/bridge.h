#ifndef YH_LLVM_BRIDGE_H
#define YH_LLVM_BRIDGE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* yh_llvm_version：返回静态链接的 LLVM 发行版本；字符串由桥持有，不得释放。 */
const char *yh_llvm_version(void);

/* yh_llvm_emit：在私有 LLVM context 中验证/优化文本 IR 并原子发布对象或汇编。
 * opt_level 仅允许 0/2；kind=0 对象、1 汇编；目前接受 Linux x64/AArch64 triple。
 * 返回 0 成功、-1 失败；所有输入及诊断缓冲归调用方，桥不保留其指针。
 * diagnostic 在 capacity>0 时始终 NUL 结尾；失败保留已有 output，清理临时产物。
 * 支持 Linux x64/AArch64，以及预研用的 x64 Darwin/Windows 对象 triple。
 * 该 API 不启动 LLVM 工具、不读取系统 LLVM 配置、不共享 module/target machine。 */
int yh_llvm_emit(const char *text, uint64_t length, const char *triple,
                 int opt_level, int kind, const char *output,
                 char *diagnostic, uint64_t capacity);

#ifdef __cplusplus
}
#endif
#endif
