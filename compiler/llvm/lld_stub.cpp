// yh_lld_stub：为未内嵌 lld 的宿主提供稳定的可选链接 ABI。
// ARM64 当前只内嵌 LLVM 代码生成桥；这些入口让编译器可保留旧链接路径。
#include <algorithm>
#include <cstring>

namespace {

// copy_diagnostic：把不可用原因写入有界缓冲区并保证 NUL 结尾。
void copy_diagnostic(const char *source, char *destination,
                     unsigned long capacity) {
  if (destination == nullptr || capacity == 0)
    return;
  const std::size_t length =
      std::min(std::strlen(source), static_cast<std::size_t>(capacity - 1));
  std::memcpy(destination, source, length);
  destination[length] = '\0';
}

} // namespace

// yh_lld_link：未配置 lld 时明确拒绝直接风格链接请求。
extern "C" int yh_lld_link(const char **, int, char *diagnostic,
                           unsigned long capacity) {
  copy_diagnostic("当前宿主没有内嵌 lld 链接器", diagnostic, capacity);
  return -1;
}

// yh_lld_link_driver：未配置 lld 的宿主不得假装完成内嵌链接。
extern "C" int yh_lld_link_driver(const char *, const char **, int,
                                  const char **, int, char *diagnostic,
                                  unsigned long capacity) {
  copy_diagnostic("当前宿主没有内嵌 lld ELF 驱动", diagnostic, capacity);
  return -1;
}

// yh_lld_link_identity：空字符串表示此宿主没有可用 lld。
extern "C" const char *yh_lld_link_identity(void) { return ""; }

// yh_lld_default_file_count：未内嵌 lld 时没有默认链接输入。
extern "C" int yh_lld_default_file_count(void) { return 0; }

// yh_lld_default_file：未内嵌 lld 时没有默认启动文件。
extern "C" const char *yh_lld_default_file(int) { return nullptr; }

// yh_lld_default_library_count：未内嵌 lld 时没有默认链接库。
extern "C" int yh_lld_default_library_count(void) { return 0; }

// yh_lld_default_library：未内嵌 lld 时没有默认链接库。
extern "C" const char *yh_lld_default_library(int) { return nullptr; }

// yh_lld_resolve_library：未内嵌 lld 的宿主无法按 lld 搜索路径解析库。
extern "C" int yh_lld_resolve_library(const char *, char *, unsigned long) {
  return 1;
}
