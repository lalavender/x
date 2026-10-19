/* Darwin 无固定 LLVM 包时使用的可选 C ABI 桩；正式桥的强定义会覆盖这些弱符号。 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#if defined(__GNUC__) || defined(__clang__)
#define YH_WEAK __attribute__((weak))
#else
#define YH_WEAK
#endif

/* copy_diagnostic：复制有界错误信息，并在任何非零容量下写入 NUL 终止符。 */
static void copy_diagnostic(char *destination, uint64_t capacity,
                            const char *message) {
    if (destination == NULL || capacity == 0) return;
    size_t length = strlen(message);
    if (length >= capacity) length = (size_t)(capacity - 1);
    memcpy(destination, message, length);
    destination[length] = '\0';
}

/* yh_llvm_version：标识当前编译器只链入未安装 SDK 的弱桩。 */
YH_WEAK const char *yh_llvm_version(void) {
    return "unavailable";
}

/* yh_llvm_emit：保留 v1 Linux ABI，显式报告没有固定 LLVM 桥。 */
YH_WEAK int yh_llvm_emit(const char *text, uint64_t length, const char *triple,
                         int opt_level, int kind, const char *output,
                         char *diagnostic, uint64_t capacity) {
    (void)text; (void)length; (void)triple; (void)opt_level; (void)kind; (void)output;
    copy_diagnostic(diagnostic, capacity, "内嵌 LLVM 桥未链接");
    return -1;
}

/* yh_llvm_emit_v2：Darwin 新 ABI 的可选失败桩；不会创建或替换输出文件。 */
YH_WEAK int yh_llvm_emit_v2(const char *text, uint64_t length, const char *triple,
                            const char *min_os, int opt_level, int kind,
                            const char *output, char *diagnostic,
                            uint64_t capacity) {
    (void)text; (void)length; (void)triple; (void)min_os;
    (void)opt_level; (void)kind; (void)output;
    copy_diagnostic(diagnostic, capacity, "内嵌 LLVM 桥未链接");
    return -1;
}

/* yh_lld_link：原始 argv 接口在没有 lld 的构建中稳定失败。 */
YH_WEAK int yh_lld_link(const char **argv, int argc, char *diagnostic,
                        uint64_t capacity) {
    (void)argv; (void)argc;
    copy_diagnostic(diagnostic, capacity, "当前宿主没有内嵌 lld 链接器");
    return -1;
}

/* yh_lld_link_driver：保留生产驱动绑定并说明 lld 静态 SDK 尚未接入。 */
YH_WEAK int yh_lld_link_driver(const char *output, const char **objects,
                               int object_count, const char **extra_args,
                               int extra_count, char *diagnostic,
                               uint64_t capacity) {
    (void)output; (void)objects; (void)object_count; (void)extra_args; (void)extra_count;
    copy_diagnostic(diagnostic, capacity, "当前宿主没有内嵌 lld 链接器");
    return -1;
}

/* yh_lld_link_identity：空身份表示该编译器未嵌入 lld。 */
YH_WEAK const char *yh_lld_link_identity(void) { return ""; }

/* yh_lld_default_file_count：没有 lld 模板时不注入 CRT 文件。 */
YH_WEAK int yh_lld_default_file_count(void) { return 0; }

/* yh_lld_default_file：无效索引和空模板均返回空指针。 */
YH_WEAK const char *yh_lld_default_file(int index) { (void)index; return NULL; }

/* yh_lld_default_library_count：没有 lld 模板时不注入默认库。 */
YH_WEAK int yh_lld_default_library_count(void) { return 0; }

/* yh_lld_default_library：无效索引和空模板均返回空指针。 */
YH_WEAK const char *yh_lld_default_library(int index) { (void)index; return NULL; }

/* yh_lld_selfhost_flag_count：没有固定闭包时不追加自举链接参数。 */
YH_WEAK int yh_lld_selfhost_flag_count(void) { return 0; }

/* yh_lld_selfhost_flag：无效索引和空闭包均返回空指针。 */
YH_WEAK const char *yh_lld_selfhost_flag(int index) { (void)index; return NULL; }

/* yh_lld_resolve_library：未嵌入 lld 时明确表示库解析失败。 */
YH_WEAK int yh_lld_resolve_library(const char *name, char *path, uint64_t capacity) {
    (void)name; (void)path; (void)capacity;
    return 1;
}
