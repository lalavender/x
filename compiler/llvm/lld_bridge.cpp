// yh_lld_link：把 ELF、Mach-O 与 COFF lld 驱动暴露为有界诊断的 C ABI。
// lld 返回不可重入状态后，本进程不会再调用它；编译器在一次性子进程中运行链接。
#include "lld/Common/Driver.h"
#include "llvm/Support/raw_ostream.h"

#include "lld_link_config.h"

#include <algorithm>
#include <cctype>
#include <cstddef>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <system_error>
#include <vector>

LLD_HAS_DRIVER(elf)
LLD_HAS_DRIVER(macho)
LLD_HAS_DRIVER(coff)

namespace {

bool can_run_again = true;
constexpr const char *kOutputMarker = "@YH_LLD_OUTPUT@";
constexpr const char *kInputsMarker = "@YH_LLD_INPUTS@";

// SelfhostFlags：编译器自举链接闭包的运行时快照。
// 构建机通过 YH_LLVM_SELFHOST_FLAGS 指向「每行一个链接参数」的文件（与 Zig 的
// build 脚本同思路：闭包路径属于构建环境，不编进编译器）。未设置该变量时回退到
// 编译期常量，只用于过渡种子；文件不可读或为空时标记 invalid，由 yh 侧给出
// 可操作诊断，绝不静默把闭包当成空的。
struct SelfhostFlags {
  bool from_file = false;
  bool invalid = false;
  std::vector<std::string> values;
};

// load_selfhost_flags：解析并缓存运行时闭包文件；进程内只读一次。
SelfhostFlags load_selfhost_flags() {
  SelfhostFlags result;
  const char *path = std::getenv("YH_LLVM_SELFHOST_FLAGS");
  if (path == nullptr || *path == '\0')
    return result;
  std::ifstream input(path);
  if (!input) {
    result.invalid = true;
    return result;
  }
  std::string line;
  while (std::getline(input, line)) {
    if (!line.empty() && line.back() == '\r')
      line.pop_back();
    if (!line.empty())
      result.values.push_back(line);
  }
  if (result.values.empty())
    result.invalid = true;
  else
    result.from_file = true;
  return result;
}

// selfhost_flags：返回进程级只读快照（C++11 起静态局部初始化线程安全）。
const SelfhostFlags &selfhost_flags() {
  static const SelfhostFlags snapshot = load_selfhost_flags();
  return snapshot;
}

// selfhost_flag_count_internal：返回自举闭包参数数量；-1 表示运行时文件不可用。
int selfhost_flag_count_internal() {
  const SelfhostFlags &flags = selfhost_flags();
  if (flags.invalid)
    return -1;
  if (flags.from_file)
    return static_cast<int>(flags.values.size());
  return YH_LLVM_SELFHOST_LINK_FLAGS_COUNT;
}

// selfhost_flag_internal：按序返回一个自举闭包参数；越界返回空指针。
const char *selfhost_flag_internal(int index) {
  if (index < 0)
    return nullptr;
  const SelfhostFlags &flags = selfhost_flags();
  if (flags.from_file) {
    const std::size_t position = static_cast<std::size_t>(index);
    if (position >= flags.values.size())
      return nullptr;
    return flags.values[position].c_str();
  }
  if (static_cast<std::size_t>(index) >= YH_LLVM_SELFHOST_LINK_FLAGS_COUNT)
    return nullptr;
  return yh_llvm_selfhost_link_flags[index];
}

// copy_diagnostic：把 lld 错误文本复制到调用方缓冲区，并保证有容量时以 NUL 结尾。
void copy_diagnostic(const std::string &source, char *destination,
                     unsigned long capacity) {
  if (destination == nullptr || capacity == 0)
    return;
  const std::size_t length =
      std::min(source.size(), static_cast<std::size_t>(capacity - 1));
  if (length != 0)
    std::memcpy(destination, source.data(), length);
  destination[length] = '\0';
}

// append_library_path：把运行时 GCC 库搜索环境转换为 lld 的 -L 参数。
void append_library_path(std::vector<const char *> &arguments,
                         std::vector<std::string> &owned_paths) {
  const char *value = std::getenv("LIBRARY_PATH");
  if (value == nullptr || *value == '\0')
    return;
  const char *start = value;
  for (const char *cursor = value;; ++cursor) {
    if (*cursor == ':' || *cursor == '\0') {
      owned_paths.emplace_back(cursor == start ? "." : std::string(start, cursor));
      if (*cursor == '\0')
        break;
      start = cursor + 1;
    }
  }
  for (const std::string &path : owned_paths) {
      arguments.push_back("-L");
      arguments.push_back(path.c_str());
  }
}

// append_run_path：保留 GCC/ld 的 LD_RUN_PATH 运行时搜索路径语义。
void append_run_path(std::vector<const char *> &arguments) {
  const char *value = std::getenv("LD_RUN_PATH");
  if (value != nullptr && *value != '\0') {
    arguments.push_back("-rpath");
    arguments.push_back(value);
  }
}

// link_search_paths：依照最终传给 lld 的顺序收集环境与固定 SDK 的库搜索目录。
std::vector<std::string> link_search_paths() {
  std::vector<std::string> paths;
  const char *environment = std::getenv("LIBRARY_PATH");
  if (environment != nullptr) {
    const char *start = environment;
    for (const char *cursor = environment;; ++cursor) {
      if (*cursor == ':' || *cursor == '\0') {
        paths.emplace_back(cursor == start ? "." : std::string(start, cursor));
        if (*cursor == '\0')
          break;
        start = cursor + 1;
      }
    }
  }
  for (std::size_t i = 0; i < YH_LLD_LINK_TEMPLATE_COUNT; ++i) {
    const char *argument = yh_lld_link_template[i];
    if (std::strncmp(argument, "-L", 2) == 0 && argument[2] != '\0')
      paths.emplace_back(argument + 2);
    else if (std::strcmp(argument, "-L") == 0 &&
             i + 1 < YH_LLD_LINK_TEMPLATE_COUNT)
      paths.emplace_back(yh_lld_link_template[++i]);
  }
  return paths;
}

// invoke_lld：执行一次 lldMain，并在 lld 要求不可重入时封住后续调用。
int invoke_lld(const std::vector<const char *> &arguments, char *diagnostic,
               unsigned long capacity) {
  if (diagnostic != nullptr && capacity != 0)
    diagnostic[0] = '\0';
  if (!can_run_again) {
    copy_diagnostic("lld 进程状态不可重用", diagnostic, capacity);
    return -2;
  }
  if (arguments.empty()) {
    copy_diagnostic("lld 参数无效", diagnostic, capacity);
    return -1;
  }
  for (const char *argument : arguments) {
    if (argument == nullptr) {
      copy_diagnostic("lld argv 包含空参数", diagnostic, capacity);
      return -1;
    }
  }

  std::string errors;
  llvm::raw_string_ostream error_stream(errors);
  const llvm::ArrayRef<const char *> args(arguments.data(), arguments.size());
  const lld::DriverDef drivers[] = {
      {lld::Gnu, &lld::elf::link},
      {lld::Darwin, &lld::macho::link},
      {lld::WinLink, &lld::coff::link},
  };
  // 链接 worker（有 fork 宿主的子进程、无 fork 宿主的 `--lld-link` 子进程）
  // 只跑一次链接：诊断直接进 stderr。原因：lld 的 fatal() 会用 Process::Exit
  // 直接结束进程，此时缓冲区里的诊断还没回传给调用方，链接失败就完全静默
  // （Windows 上实测只看到「链接失败」，没有 lld 给出的原因）。
  const bool direct_stderr = std::getenv("YH_LLD_STDERR") != nullptr;
  llvm::raw_ostream &lld_stderr =
      direct_stderr ? static_cast<llvm::raw_ostream &>(llvm::errs()) :
                      static_cast<llvm::raw_ostream &>(error_stream);
  const lld::Result result = lld::lldMain(args, llvm::outs(), lld_stderr, drivers);
  error_stream.flush();
  if (!direct_stderr)
    copy_diagnostic(errors, diagnostic, capacity);
  if (result.retCode == 0)
    return 0;
  if (!result.canRunAgain) {
    can_run_again = false;
    return -2;
  }
  return -1;
}

// append_lld_inputs：将调用方对象与额外 -l 参数替换进固定 GNU 链接模板。
void append_lld_inputs(std::vector<const char *> &arguments,
                       const char *output, const char **objects,
                       int object_count, const char **extra_args,
                       int extra_count, std::vector<std::string> &owned_paths) {
  arguments.push_back(yh_lld_link_template[0]);
  append_library_path(arguments, owned_paths);
  append_run_path(arguments);
  for (std::size_t i = 1; i < YH_LLD_LINK_TEMPLATE_COUNT; ++i) {
    const char *argument = yh_lld_link_template[i];
    if (std::strcmp(argument, kOutputMarker) == 0) {
      arguments.push_back(output);
    } else if (std::strcmp(argument, kInputsMarker) == 0) {
      for (int j = 0; j < object_count; ++j)
        arguments.push_back(objects[j]);
      for (int j = 0; j < extra_count; ++j)
        arguments.push_back(extra_args[j]);
      const char *selfhost = std::getenv("YH_LLVM_SELFHOST");
      const char *manifest_only = std::getenv("YH_LINK_MANIFEST_ONLY");
      const bool legacy_injection =
          manifest_only == nullptr || std::strcmp(manifest_only, "1") != 0;
      if (legacy_injection && selfhost != nullptr &&
          std::strcmp(selfhost, "1") == 0) {
        const int count = selfhost_flag_count_internal();
        for (int index = 0; index < count; ++index) {
          const char *flag = selfhost_flag_internal(index);
          if (flag != nullptr)
            arguments.push_back(flag);
        }
      }
    } else {
      arguments.push_back(argument);
    }
  }
}

} // namespace

// yh_lld_link：直接接收完整 GNU/ELF argv，供 shim 探针和特殊链接调用使用。
// 返回 0 成功、-1 可恢复失败、-2 lld 要求结束当前 worker。
extern "C" int yh_lld_link(const char **argv, int argc, char *diagnostic,
                           unsigned long capacity) {
  if (argv == nullptr || argc <= 0 ||
      (diagnostic == nullptr && capacity != 0)) {
    copy_diagnostic("lld 参数无效", diagnostic, capacity);
    return -1;
  }
  std::vector<const char *> arguments(argv, argv + argc);
  return invoke_lld(arguments, diagnostic, capacity);
}

// yh_lld_link_driver：用宿主固定的 GNU 默认启动文件/库配置链接 LLVM 对象。
// 输入与输出路径由调用方提供；链接失败只写入临时输出，不替换最终产物。
extern "C" int yh_lld_link_driver(const char *output, const char **objects,
                                  int object_count, const char **extra_args,
                                  int extra_count, char *diagnostic,
                                  unsigned long capacity) {
  if (output == nullptr || *output == '\0' || object_count < 0 || extra_count < 0 ||
      (object_count != 0 && objects == nullptr) ||
      (extra_count != 0 && extra_args == nullptr) ||
      (diagnostic == nullptr && capacity != 0)) {
    copy_diagnostic("lld 链接参数无效", diagnostic, capacity);
    return -1;
  }
  std::vector<const char *> arguments;
  std::vector<std::string> owned_paths;
  arguments.reserve(YH_LLD_LINK_TEMPLATE_COUNT + object_count + extra_count + 8);
  append_lld_inputs(arguments, output, objects, object_count, extra_args,
                    extra_count, owned_paths);
  return invoke_lld(arguments, diagnostic, capacity);
}

// yh_lld_link_identity：返回编译进 shim 的 SDK、源、链接模板与默认系统输入身份。
extern "C" const char *yh_lld_link_identity(void) {
  return yh_lld_identity_value;
}

// yh_lld_default_file_count：返回模板中的 CRT 与动态加载器文件数量。
extern "C" int yh_lld_default_file_count(void) {
  return YH_LLD_DEFAULT_FILES_COUNT;
}

// yh_lld_default_file：按序返回固定链接模板中一个系统启动文件路径。
extern "C" const char *yh_lld_default_file(int index) {
  if (index < 0 || static_cast<std::size_t>(index) >= YH_LLD_DEFAULT_FILES_COUNT)
    return nullptr;
  return yh_lld_default_files[index];
}

// yh_lld_default_library_count：返回固定 GNU 链接模板中默认 -l 库数量。
extern "C" int yh_lld_default_library_count(void) {
  return YH_LLD_DEFAULT_LIBRARIES_COUNT;
}

// yh_lld_default_library：按序返回固定模板中的一个默认库名，不带 -l 前缀。
extern "C" const char *yh_lld_default_library(int index) {
  if (index < 0 || static_cast<std::size_t>(index) >= YH_LLD_DEFAULT_LIBRARIES_COUNT)
    return nullptr;
  return yh_lld_default_libraries[index];
}

// yh_lld_selfhost_flag_count：返回自举链接追加参数的数量。
// 优先使用构建机通过 YH_LLVM_SELFHOST_FLAGS 提供的闭包文件；未提供时回退到
// 编译期常量（过渡种子）。负数表示文件不可读，调用方必须报错而不是当作空闭包。
extern "C" int yh_lld_selfhost_flag_count(void) {
  return selfhost_flag_count_internal();
}

// yh_lld_selfhost_flag：按序返回一个自举链接追加参数。
extern "C" const char *yh_lld_selfhost_flag(int index) {
  return selfhost_flag_internal(index);
}

// yh_lld_resolve_library：按实际 lld 搜索顺序解析 libNAME.so 或 libNAME.a。
// 返回 0 找到、1 未找到、-1 输入或输出缓冲无效。
extern "C" int yh_lld_resolve_library(const char *name, char *output,
                                     unsigned long capacity) {
  if (name == nullptr || *name == '\0' || output == nullptr || capacity == 0)
    return -1;
  for (const char *cursor = name; *cursor != '\0'; ++cursor) {
    const unsigned char value = static_cast<unsigned char>(*cursor);
    if (!(std::isalnum(value) || value == '_' || value == '-'))
      return -1;
  }
  const std::string file = std::string("lib") + name;
  std::error_code error;
  for (const std::string &directory : link_search_paths()) {
    for (const char *suffix : {".so", ".a"}) {
      const std::filesystem::path path = std::filesystem::path(directory) / (file + suffix);
      error.clear();
      if (!std::filesystem::is_regular_file(path, error) || error)
        continue;
      const std::string resolved = path.string();
      if (resolved.size() >= capacity)
        return -1;
      std::memcpy(output, resolved.c_str(), resolved.size() + 1);
      return 0;
    }
  }
  return 1;
}
