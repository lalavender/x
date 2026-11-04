/* LLVM 静态 C ABI 桥：只管理 LLVM 生命周期、目标管线和输出，yh 语义留在 .yh。 */
#define _POSIX_C_SOURCE 200809L
#include "bridge.h"
#include <llvm-c/Analysis.h>
#include <llvm-c/Core.h>
#include <llvm-c/Error.h>
#include <llvm-c/IRReader.h>
#include <llvm-c/Target.h>
#include <llvm-c/TargetMachine.h>
#include <llvm-c/Transforms/PassBuilder.h>
#include <llvm/Config/llvm-config.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

/* 宿主平台适配（W2）：Linux/Darwin 用 pthread_once + unlink；
 * Windows 用 InitOnceExecuteOnce + _unlink。桥只在初始化目标注册表时用一次
 * 「只执行一次」语义，两者等价。
 * 编译 yh 自身时链接静态 CRT（/MT），因此这里可以直接用 Win32 API。 */
static void initialize_targets(void);

/* publish_detail：最近一次 publish_buffer 失败点的可读描述（A2 诊断，2026-11-05）。
 * 只在失败路径写入，供 yh 侧把原因拼进 diagnostic；成功路径保持为空。 */
static char publish_detail[160];

static void set_publish_detail(const char *stage, long code) {
    snprintf(publish_detail, sizeof(publish_detail), "%s 失败(返回=%ld errno=%d)",
             stage, code, errno);
}

#ifdef _WIN32
#include <io.h>
#include <windows.h>
/* POSIX 名称在 MSVC 下是 _ 前缀的旧名；桥只用到 stdout 与 unlink。 */
#ifndef _SSIZE_T_DEFINED
typedef intptr_t ssize_t;
#define _SSIZE_T_DEFINED
#endif
#define STDOUT_FILENO 1
#define write _write
#define close _close
#define yh_unlink _unlink
/* mkstemp 在 MSVC 没有等价物：用 _mktemp_s 生成唯一名 + _open(O_CREAT|O_EXCL)，
 * 语义与 mkstemp 一致（独占创建、失败返回 -1），模板同样要求 6 个 X 结尾。 */
#include <fcntl.h>
#include <sys/stat.h>
static int yh_mkstemp(char *template_path) {
    if (_mktemp_s(template_path, strlen(template_path) + 1) != 0) {
        set_publish_detail("_mktemp_s", -1);
        return -1;
    }
    int fd = _open(template_path, _O_CREAT | _O_EXCL | _O_WRONLY | _O_BINARY,
                   _S_IREAD | _S_IWRITE);
    if (fd < 0) set_publish_detail("_open", (long)fd);
    return fd;
}
/* yh_replace_file：原子发布要用 POSIX rename 的覆盖语义；MSVCRT 的 rename 在
 * 目标已存在时直接失败（增量重建对象必踩），因此 Windows 走 MoveFileExA。 */
static int yh_replace_file(const char *from, const char *to) {
    return MoveFileExA(from, to, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)
               ? 0 : -1;
}
static INIT_ONCE targets_once = INIT_ONCE_STATIC_INIT;
static BOOL CALLBACK initialize_targets_once(PINIT_ONCE once, PVOID parameter, PVOID *context) {
    (void)once;
    (void)parameter;
    (void)context;
    initialize_targets();
    return TRUE;
}
static void initialize_targets_once_call(void) {
    InitOnceExecuteOnce(&targets_once, initialize_targets_once, NULL, NULL);
}
#else
#include <pthread.h>
#include <unistd.h>
#define yh_unlink unlink
#define yh_mkstemp mkstemp
#define yh_replace_file rename
static pthread_once_t targets_once = PTHREAD_ONCE_INIT;
static void initialize_targets_once_call(void) {
    pthread_once(&targets_once, initialize_targets);
}
#endif

/* initialize_targets：一次性登记 LLVM 静态目标，线程间只共享不可变注册表。 */
static void initialize_targets(void) {
    LLVMInitializeX86TargetInfo();
    LLVMInitializeX86Target();
    LLVMInitializeX86TargetMC();
    LLVMInitializeX86AsmPrinter();
    LLVMInitializeX86AsmParser();
    LLVMInitializeAArch64TargetInfo();
    LLVMInitializeAArch64Target();
    LLVMInitializeAArch64TargetMC();
    LLVMInitializeAArch64AsmPrinter();
    LLVMInitializeAArch64AsmParser();
}

/* copy_diagnostic：截断到调用方容量，不暴露 LLVM 分配的消息所有权。 */
static void copy_diagnostic(char *out, uint64_t capacity, const char *message) {
    if (!out || !capacity) return;
    size_t size = strlen(message);
    if (size >= capacity) size = (size_t)(capacity - 1);
    memcpy(out, message, size);
    out[size] = 0;
}

const char *yh_llvm_version(void) {
    return LLVM_VERSION_STRING;
}

/* publish_detail：最近一次 publish_buffer 失败点的可读描述（A2 诊断，2026-11-05）。
 * 只在失败路径写入，供 yh 侧把原因拼进 diagnostic；成功路径保持为空。
 * 定义在 _WIN32 分支的 yh_mkstemp 之前（两个分支共用）。 */

/* publish_buffer：同目录临时写入后 rename；任何失败都不破坏既有有效产物。 */
static int publish_buffer(const char *path, LLVMMemoryBufferRef buffer) {
    size_t path_length = strlen(path);
    if (!strcmp(path, "-")) {
        const char *bytes = LLVMGetBufferStart(buffer);
        size_t length = LLVMGetBufferSize(buffer);
        size_t done = 0;
        while (done < length) {
            ssize_t written = write(STDOUT_FILENO, bytes + done, length - done);
            if (written <= 0) {
                set_publish_detail("stdout write", (long)written);
                return -1;
            }
            done += (size_t)written;
        }
        return 0;
    }
    char *temporary = malloc(path_length + sizeof(".yh-llvm-XXXXXX"));
    if (!temporary) {
        set_publish_detail("malloc", 0);
        return -1;
    }
    memcpy(temporary, path, path_length);
    memcpy(temporary + path_length, ".yh-llvm-XXXXXX", sizeof(".yh-llvm-XXXXXX"));
    int fd = yh_mkstemp(temporary);
    if (fd < 0) {
        set_publish_detail("mkstemp", (long)fd);
        free(temporary);
        return -1;
    }
    const char *bytes = LLVMGetBufferStart(buffer);
    size_t length = LLVMGetBufferSize(buffer);
    size_t done = 0;
    int result = 0;
    while (done < length) {
        ssize_t written = write(fd, bytes + done, length - done);
        if (written <= 0) {
            set_publish_detail("file write", (long)written);
            result = -1;
            break;
        }
        done += (size_t)written;
    }
    if (close(fd)) {
        set_publish_detail("close", -1);
        result = -1;
    }
    if (!result && yh_replace_file(temporary, path)) {
#ifdef _WIN32
        snprintf(publish_detail, sizeof(publish_detail),
                 "MoveFileExA 失败(GetLastError=%lu)", GetLastError());
#else
        set_publish_detail("rename", -1);
#endif
        result = -1;
    }
    if (result) yh_unlink(temporary);
    free(temporary);
    return result;
}

/* valid_min_os：只接受 major.minor.patch 三段正十进制，拒绝溢出和尾随字符。 */
static int valid_min_os(const char *version) {
    if (!version || !*version) return 0;
    unsigned long parts[3] = {0, 0, 0};
    const char *cursor = version;
    for (size_t part = 0; part < 3; ++part) {
        if (*cursor < '0' || *cursor > '9') return 0;
        while (*cursor >= '0' && *cursor <= '9') {
            unsigned digit = (unsigned)(*cursor - '0');
            if (parts[part] > 1000 || parts[part] * 10 + digit > 1000) return 0;
            parts[part] = parts[part] * 10 + digit;
            ++cursor;
        }
        if (part < 2) {
            if (*cursor != '.') return 0;
            ++cursor;
        }
    }
    return *cursor == '\0' && parts[0] > 0;
}

/* llvm_emit：共享 v1/v2 生命周期；v2 为 Darwin 构造带 minOS 的 triple 与 PIC 机器。 */
static int llvm_emit(const char *text, uint64_t length, const char *triple,
                     const char *min_os, int version2, int opt_level, int kind,
                     const char *output, char *diagnostic, uint64_t capacity) {
    if (diagnostic && capacity) diagnostic[0] = 0;
    if (!text || length > SIZE_MAX || !triple || !output || !*output
        || (opt_level != 0 && opt_level != 2) || (kind != 0 && kind != 1)) {
        copy_diagnostic(diagnostic, capacity, "内嵌 LLVM：无效参数或不支持的优化/输出配置");
        return -1;
    }
    int darwin_arm64 = version2 && !strcmp(triple, "aarch64-apple-darwin");
    if (strcmp(triple, "x86_64-unknown-linux-gnu")
        && strcmp(triple, "aarch64-unknown-linux-gnu")
        && strcmp(triple, "x86_64-apple-darwin")
        && !darwin_arm64
        && strcmp(triple, "x86_64-pc-windows-msvc")) {
        copy_diagnostic(diagnostic, capacity, "内嵌 LLVM：不支持的目标 triple");
        return -1;
    }
    char effective_triple[160];
    const char *target_triple = triple;
    if (darwin_arm64) {
        if (!valid_min_os(min_os)) {
            copy_diagnostic(diagnostic, capacity, "内嵌 LLVM：最低 macOS 版本必须是 major.minor.patch");
            return -1;
        }
        int written = snprintf(effective_triple, sizeof(effective_triple),
                               "aarch64-apple-macosx%s", min_os);
        if (written < 0 || (size_t)written >= sizeof(effective_triple)) {
            copy_diagnostic(diagnostic, capacity, "内嵌 LLVM：最低 macOS 版本过长");
            return -1;
        }
        target_triple = effective_triple;
    } else if (version2 && min_os && *min_os) {
        copy_diagnostic(diagnostic, capacity, "内嵌 LLVM：Linux 目标不接受 macOS 部署版本");
        return -1;
    }
    initialize_targets_once_call();
    LLVMContextRef context = LLVMContextCreate();
    LLVMModuleRef module = NULL;
    LLVMTargetMachineRef machine = NULL;
    LLVMMemoryBufferRef object = NULL;
    char *message = NULL;
    int result = -1;
    /* LLVMParseIRInContext 消费输入 buffer，成功/失败都不再由调用方释放。 */
    LLVMMemoryBufferRef input = LLVMCreateMemoryBufferWithMemoryRangeCopy(
        text, (size_t)length, "yh-module.ll");
    if (LLVMParseIRInContext(context, input, &module, &message)) goto llvm_error;
    if (LLVMVerifyModule(module, LLVMReturnStatusAction, &message)) goto llvm_error;
    LLVMDisposeMessage(message);
    message = NULL;
    const char *module_target = LLVMGetTarget(module);
    if (*module_target && strcmp(module_target, triple)
        && strcmp(module_target, target_triple)) {
        copy_diagnostic(diagnostic, capacity, "内嵌 LLVM：模块 triple 与请求目标不一致");
        goto cleanup;
    }
    LLVMTargetRef target = NULL;
    if (LLVMGetTargetFromTriple(target_triple, &target, &message)) goto llvm_error;
    /* PE/COFF 镜像固定加载在 0x140000000：静态重定位模型会产出 ADDR32 绝对地址，
     * 链接期被截断成低 32 位，任何全局数据访问都会崩（2026-10-27 W1 实测：
     * `movl G, %edx` + IMAGE_REL_AMD64_ADDR32 → ACCESS_VIOLATION）。Windows 目标
     * 与 Darwin 一样用 PIC；ELF 继续用 static（-no-pie 下有效）。 */
    int needs_pic = darwin_arm64 || !strcmp(triple, "x86_64-pc-windows-msvc");
    machine = LLVMCreateTargetMachine(target, target_triple, "generic", "",
        opt_level == 0 ? LLVMCodeGenLevelNone : LLVMCodeGenLevelAggressive,
        needs_pic ? LLVMRelocPIC : LLVMRelocStatic, LLVMCodeModelSmall);
    if (!machine) {
        copy_diagnostic(diagnostic, capacity, "内嵌 LLVM：创建目标机器失败");
        goto cleanup;
    }
    LLVMTargetDataRef layout = LLVMCreateTargetDataLayout(machine);
    char *layout_text = LLVMCopyStringRepOfTargetData(layout);
    const char *module_layout = LLVMGetDataLayoutStr(module);
    int mismatch = *module_layout && strcmp(module_layout, layout_text);
    if (!mismatch) LLVMSetModuleDataLayout(module, layout);
    LLVMDisposeMessage(layout_text);
    LLVMDisposeTargetData(layout);
    if (mismatch) {
        copy_diagnostic(diagnostic, capacity, "内嵌 LLVM：模块 data layout 与目标不一致");
        goto cleanup;
    }
    LLVMSetTarget(module, target_triple);
    LLVMPassBuilderOptionsRef options = LLVMCreatePassBuilderOptions();
    LLVMPassBuilderOptionsSetVerifyEach(options, 1);
    LLVMErrorRef pass_error = LLVMRunPasses(module,
        opt_level == 0 ? "default<O0>" : "default<O2>", machine, options);
    LLVMDisposePassBuilderOptions(options);
    if (pass_error) {
        char *error_text = LLVMGetErrorMessage(pass_error);
        copy_diagnostic(diagnostic, capacity, error_text);
        LLVMDisposeErrorMessage(error_text);
        goto cleanup;
    }
    if (LLVMVerifyModule(module, LLVMReturnStatusAction, &message)) goto llvm_error;
    LLVMDisposeMessage(message);
    message = NULL;
    if (LLVMTargetMachineEmitToMemoryBuffer(machine, module,
            kind == 0 ? LLVMObjectFile : LLVMAssemblyFile, &message, &object)) goto llvm_error;
    if (publish_buffer(output, object)) {
        copy_diagnostic(diagnostic, capacity, "内嵌 LLVM：目标文件原子写入失败");
        size_t used = strlen(diagnostic);
        if (publish_detail[0] && used + 1 < capacity) {
            snprintf(diagnostic + used, capacity - used, " [%s]", publish_detail);
        }
        goto cleanup;
    }
    result = 0;
    goto cleanup;
llvm_error:
    copy_diagnostic(diagnostic, capacity, message ? message : "内嵌 LLVM：操作失败");
cleanup:
    if (message) LLVMDisposeMessage(message);
    if (object) LLVMDisposeMemoryBuffer(object);
    if (machine) LLVMDisposeTargetMachine(machine);
    if (module) LLVMDisposeModule(module);
    LLVMContextDispose(context);
    return result;
}

int yh_llvm_emit(const char *text, uint64_t length, const char *triple,
                 int opt_level, int kind, const char *output,
                 char *diagnostic, uint64_t capacity) {
    return llvm_emit(text, length, triple, NULL, 0, opt_level, kind,
                     output, diagnostic, capacity);
}

int yh_llvm_emit_v2(const char *text, uint64_t length, const char *triple,
                    const char *min_os, int opt_level, int kind,
                    const char *output, char *diagnostic, uint64_t capacity) {
    return llvm_emit(text, length, triple, min_os, 1, opt_level, kind,
                     output, diagnostic, capacity);
}
