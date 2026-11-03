/* Windows 宿主 POSIX 垫片（W2-2c）：补齐 yh 编译器在 Windows 上引用的少量 POSIX API。
 *
 * 这不是零 CRT 用户程序的运行时（那套由 backend/llvm_windows_runtime.yh 发射）；
 * 本文件只链进 yh.exe 自己，且只在原生 Windows 宿主上参与构建。语义选择：
 *
 *   stat      —— 按 x86_64 Linux struct stat 的字段位置填写（lib_stat_file 在非
 *                Darwin 宿主走 Linux 分支：size@48、mtime_sec@88、mtime_nsec@96）。
 *                用 GetFileAttributesExA 取大小与最后写入时间，再换算到 Unix 纪元。
 *   realpath  —— GetFullPathNameA 规范化（不要求文件存在，调用方随后会 stat）。
 *   setenv    —— _putenv_s；overwrite=0 时已存在则不动。
 *   usleep    —— Sleep 毫秒轮转。
 *   fork      —— 返回 -1（Windows 无 fork；模块 worker 走 CreateProcess 重入）。
 *   waitpid/kill —— 供 testkit 的用例进程表使用（见 yh_win_spawn_test）。
 *   yh_win_spawn_wait —— 运行 argv 并等待，返回退出码（yh run / --emit-module）。
 *   yh_win_spawn_test —— 启动一个测试用例：stdout/stderr 重定向到日志、stdin=NUL、
 *                通过环境变量 YH_TEST_RECORD 告诉子进程断言记录写到哪里。
 */
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define YH_WIN_CHILD_MAX 64

/* 测试用例进程表：索引 0..63 对应 waitpid/kill 的 pid 1..64。
 * HANDLE 是 64 位，不能塞进 yh 的 int pid，因此用表索引做 pid。 */
static HANDLE yh_child_handles[YH_WIN_CHILD_MAX];
static int yh_child_used[YH_WIN_CHILD_MAX];

/* stat：Linux 布局垫片；调用方缓冲区是 32 个 u64。 */
int stat(const char *path, uint64_t *buf) {
    WIN32_FILE_ATTRIBUTE_DATA data;
    if (!GetFileAttributesExA(path, GetFileExInfoStandard, &data)) return -1;
    ULARGE_INTEGER size;
    size.HighPart = data.nFileSizeHigh;
    size.LowPart = data.nFileSizeLow;
    ULARGE_INTEGER stamp;
    stamp.HighPart = data.ftLastWriteTime.dwHighDateTime;
    stamp.LowPart = data.ftLastWriteTime.dwLowDateTime;
    const uint64_t epoch = 116444736000000000ULL; /* 1601-01-01 → 1970-01-01（100ns） */
    uint64_t ticks = stamp.QuadPart > epoch ? stamp.QuadPart - epoch : 0;
    memset(buf, 0, 32 * sizeof(uint64_t));
    buf[6] = size.QuadPart;
    buf[11] = ticks / 10000000ULL;
    buf[12] = (ticks % 10000000ULL) * 100ULL;
    return 0;
}

/* realpath：调用方保证 4096 字节缓冲（li_realpath 的 buf 大小）。 */
char *realpath(const char *path, char *resolved) {
    DWORD n = GetFullPathNameA(path, 4096, resolved, NULL);
    if (n == 0 || n >= 4096) return NULL;
    return resolved;
}

int setenv(const char *name, const char *value, int overwrite) {
    if (!overwrite && getenv(name) != NULL) return 0;
    return _putenv_s(name, value);
}

int usleep(unsigned int usec) {
    Sleep((DWORD)((usec + 999U) / 1000U));
    return 0;
}

int fork(void) { return -1; }

/* yh_child_store：登记一个子进程句柄，返回 pid（槽位+1）。 */
static int yh_child_store(HANDLE handle) {
    int i = 0;
    for (i = 0; i < YH_WIN_CHILD_MAX; ++i) {
        if (!yh_child_used[i]) {
            yh_child_used[i] = 1;
            yh_child_handles[i] = handle;
            return i + 1;
        }
    }
    return -1;
}

/* waitpid：options&1 非阻塞；返回 pid（已退出）、0（仍在运行）或 -1。
 * status 按 POSIX 低 8 位信号 + 高 8 位退出码编码，testkit 只读高 8 位。 */
int waitpid(int pid, int *status, int options) {
    if (pid <= 0 || pid > YH_WIN_CHILD_MAX || !yh_child_used[pid - 1]) return -1;
    HANDLE handle = yh_child_handles[pid - 1];
    DWORD wait_ms = (options & 1) != 0 ? 0 : INFINITE;
    DWORD waited = WaitForSingleObject(handle, wait_ms);
    if (waited == WAIT_TIMEOUT) return 0;
    if (waited != WAIT_OBJECT_0) {
        CloseHandle(handle);
        yh_child_used[pid - 1] = 0;
        yh_child_handles[pid - 1] = NULL;
        return -1;
    }
    DWORD code = 1;
    GetExitCodeProcess(handle, &code);
    CloseHandle(handle);
    yh_child_used[pid - 1] = 0;
    yh_child_handles[pid - 1] = NULL;
    if (status != NULL) *status = (int)((code & 0xffU) << 8);
    return pid;
}

/* kill：sig=0 只探测真实 Windows PID（测试锁用）；其他信号终止用例进程。
 * 用例进程的 pid 是上面的表索引，与真实 Windows PID 的命名空间分开：
 * 有表项时优先按表项处理，避免误伤同号真实进程。 */
int kill(int pid, int signal) {
    if (pid > 0 && pid <= YH_WIN_CHILD_MAX && yh_child_used[pid - 1]) {
        if (signal == 0) return 0;
        return TerminateProcess(yh_child_handles[pid - 1], 1) ? 0 : -1;
    }
    if (signal != 0) return -1;
    HANDLE handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, (DWORD)pid);
    if (handle == NULL) return -1;
    CloseHandle(handle);
    return 0;
}

/* yh_app_path：把 argv[0] 的 '/' 规范成 '\'，供 lpApplicationName 使用。
 *
 * CreateProcessA 的 lpApplicationName 必须是 Windows 路径：yh 内部到处用 '/'，
 * 直接把 `.build/foo` 交给 CreateProcessA 会得到 ERROR_FILE_NOT_FOUND（实测
 * `yh run` 在 Windows 上必失败）。命令行本身保持原样（子进程读到的是原字节）。
 * 返回调用方 free 的副本；分配失败返回 NULL（此时退回 lpApplicationName=NULL）。 */
/* yh_is_path_like：argv[0] 是否像路径（含分隔符或盘符）。
 *
 * 只有像路径时才传 lpApplicationName：CreateProcessA 一旦收到 application name
 * 就**不再搜索 PATH**，所以 "clang"/"gcc" 这类裸命令必须保持 NULL（走命令行
 * 首段的 PATH 搜索），否则所有外部工具都会 ERROR_FILE_NOT_FOUND。 */
static int yh_is_path_like(const char *path) {
    if (path == NULL) return 0;
    for (const char *p = path; *p; ++p) {
        if (*p == '/' || *p == (char)92 || *p == ':') return 1;
    }
    return 0;
}

static char *yh_app_path(const char *path) {
    if (path == NULL) return NULL;
    size_t length = strlen(path);
    char *out = (char *)malloc(length + 1);
    if (out == NULL) return NULL;
    for (size_t i = 0; i <= length; ++i) {
        out[i] = path[i] == '/' ? (char)92 : path[i];
    }
    return out;
}

/* yh_build_command：按 Windows 命令行规则给每个参数加双引号并转义。
 * 返回值由调用方 free。 */
static char *yh_build_command(char **argv, int argc) {
    if (argv == NULL || argc <= 0) return NULL;
    size_t cap = 16;
    int i = 0;
    for (i = 0; i < argc; ++i) cap += strlen(argv[i]) * 2 + 4;
    char *command = (char *)malloc(cap);
    if (command == NULL) return NULL;
    size_t used = 0;
    for (i = 0; i < argc; ++i) {
        const char *text = argv[i];
        if (i > 0) command[used++] = ' ';
        command[used++] = '"';
        size_t pending = 0;
        for (const char *p = text; *p; ++p) {
            if (*p == '\\') { pending += 1; continue; }
            if (*p == '"') {
                size_t k = 0;
                for (k = 0; k < pending * 2 + 1; ++k) command[used++] = '\\';
                command[used++] = '"';
            } else {
                size_t k = 0;
                for (k = 0; k < pending; ++k) command[used++] = '\\';
                command[used++] = *p;
            }
            pending = 0;
        }
        size_t k = 0;
        for (k = 0; k < pending * 2; ++k) command[used++] = '\\';
        command[used++] = '"';
    }
    command[used] = 0;
    return command;
}

/* yh_inherit_handle：把父进程标准句柄复制成可继承副本。
 * Python 等父进程用 close_fds=True 建管道时句柄不可继承；直接把不可继承句柄
 * 塞进 STARTUPINFO 会让子进程拿到无效 std 句柄，MSVCRT 启动即失败（实测子进程
 * 静默退出码 1，内嵌 lld 的链接随之失败）。复制一份 inheritable 的即可。 */
static HANDLE yh_inherit_handle(HANDLE handle) {
    if (handle == NULL || handle == INVALID_HANDLE_VALUE) {
        return INVALID_HANDLE_VALUE;
    }
    HANDLE copy = NULL;
    if (!DuplicateHandle(GetCurrentProcess(), handle, GetCurrentProcess(),
                         &copy, 0, TRUE, DUPLICATE_SAME_ACCESS)) {
        return INVALID_HANDLE_VALUE;
    }
    return copy;
}

/* yh_null_handle：NUL 兜底 std 句柄（可继承；父进程句柄不可用时用）。 */
static HANDLE yh_null_handle(DWORD access) {
    SECURITY_ATTRIBUTES inherit;
    inherit.nLength = sizeof(inherit);
    inherit.lpSecurityDescriptor = NULL;
    inherit.bInheritHandle = TRUE;
    return CreateFileA("NUL", access, FILE_SHARE_READ | FILE_SHARE_WRITE,
                       &inherit, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
}

/* yh_spawn_wait_handles：启动 argv 并等待退出（启动失败 -1）。
 * stdout/stderr 用 out_override/err_override（INVALID_HANDLE_VALUE 表示沿用父进程）；
 * stdin 一律经可继承复制/NUL 兜底，保证子进程一定拿到有效 std 句柄。 */
static int yh_spawn_wait_handles(char **argv, int argc, HANDLE out_override,
                                 HANDLE err_override) {
    char *command = yh_build_command(argv, argc);
    if (command == NULL) return -1;
    HANDLE in = yh_inherit_handle(GetStdHandle(STD_INPUT_HANDLE));
    HANDLE out = out_override != INVALID_HANDLE_VALUE
                     ? out_override
                     : yh_inherit_handle(GetStdHandle(STD_OUTPUT_HANDLE));
    HANDLE err = err_override != INVALID_HANDLE_VALUE
                     ? err_override
                     : yh_inherit_handle(GetStdHandle(STD_ERROR_HANDLE));
    int open_in = in == INVALID_HANDLE_VALUE;
    int open_out = out == INVALID_HANDLE_VALUE;
    int open_err = err == INVALID_HANDLE_VALUE;
    if (open_in) in = yh_null_handle(GENERIC_READ);
    if (open_out) out = yh_null_handle(GENERIC_WRITE);
    if (open_err) err = yh_null_handle(GENERIC_WRITE);
    STARTUPINFOA startup;
    PROCESS_INFORMATION process;
    ZeroMemory(&startup, sizeof(startup));
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = in;
    startup.hStdOutput = out;
    startup.hStdError = err;
    ZeroMemory(&process, sizeof(process));
    char *application = yh_is_path_like(argv[0]) ? yh_app_path(argv[0]) : NULL;
    BOOL ok = CreateProcessA(application, command, NULL, NULL, TRUE, 0, NULL,
                             NULL, &startup, &process);
    free(application);
    /* 复制体与 NUL 兜底只在启动期需要；out/err_override 由调用方持有。 */
    if (in != INVALID_HANDLE_VALUE) CloseHandle(in);
    if (out != INVALID_HANDLE_VALUE && out_override == INVALID_HANDLE_VALUE) {
        CloseHandle(out);
    }
    if (err != INVALID_HANDLE_VALUE && err_override == INVALID_HANDLE_VALUE) {
        CloseHandle(err);
    }
    if (!ok) {
        /* 子进程起不来时绝不能静默：调用方只看到「链接失败」，无法定位。
         * GetLastError 的数值比符号名稳定，配合命令首段（可执行文件路径）足够。 */
        fprintf(stderr, "yh: 无法启动子进程（错误码 %lu）：%s\n",
                (unsigned long)GetLastError(), command);
        free(command);
        return -1;
    }
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    /* 子进程以非常规退出码结束（253 = lld 要求结束宿主）时留一行可追踪记录；
     * 子进程自己的诊断走它继承的 stderr，这里只补「谁失败的」。 */
    if (code != 0 && code != 253) {
        fprintf(stderr, "yh: 子进程退出码 %lu：%s\n", (unsigned long)code, command);
    }
    free(command);
    return (int)code;
}

/* yh_win_spawn_wait：运行 argv 并等待退出，返回子进程退出码；启动失败 -1。 */
int yh_win_spawn_wait(char **argv, int argc) {
    return yh_spawn_wait_handles(argv, argc, INVALID_HANDLE_VALUE,
                                 INVALID_HANDLE_VALUE);
}

/* yh_win_spawn_link：跑一次内嵌 lld 的链接子进程，stdout→NUL、stderr→文件。
 *
 * 为什么不用父进程的 stdout/stderr（2026-11-02 实测）：子进程的 stdout 或
 * stderr 继承父进程的管道时，lld 的 FileOutputBuffer::commit()（临时文件经
 * SetFileInformationByHandle 改名到目标）稳定失败并报
 * "failed to write output '...': invalid argument"（ERROR_INVALID_PARAMETER），
 * 链接 0 成功 6 次；把 stdout 接 NUL、stderr 接文件后 100% 成功。
 * 因此这里固定这两条，父进程再把 stderr 文件的内容转发到自己的 stderr，
 * 用户看到的诊断不变。 */
int yh_win_spawn_link(char **argv, int argc, const char *stderr_path) {
    if (stderr_path == NULL || *stderr_path == '\0') return -1;
    SECURITY_ATTRIBUTES inherit;
    inherit.nLength = sizeof(inherit);
    inherit.lpSecurityDescriptor = NULL;
    inherit.bInheritHandle = TRUE;
    HANDLE out = yh_null_handle(GENERIC_WRITE);
    HANDLE err = CreateFileA(stderr_path, GENERIC_WRITE, FILE_SHARE_READ, &inherit,
                             CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (out == INVALID_HANDLE_VALUE || err == INVALID_HANDLE_VALUE) {
        if (out != INVALID_HANDLE_VALUE) CloseHandle(out);
        if (err != INVALID_HANDLE_VALUE) CloseHandle(err);
        return -1;
    }
    int code = yh_spawn_wait_handles(argv, argc, out, err);
    CloseHandle(out);
    CloseHandle(err);
    return code;
}

/* yh_win_spawn_capture：运行 argv 并把 stdout 落到 path（不建管道：父进程只要
 * 完整输出，直接写文件比 CreatePipe + 读线程少一层）。stderr 与 stdin 沿用父进程。
 * 返回退出码；启动失败或无法建立输出文件返回 -1。 */
int yh_win_spawn_capture(char **argv, int argc, const char *path) {
    if (path == NULL) return -1;
    SECURITY_ATTRIBUTES inherit;
    inherit.nLength = sizeof(inherit);
    inherit.lpSecurityDescriptor = NULL;
    inherit.bInheritHandle = TRUE;
    HANDLE out = CreateFileA(path, GENERIC_WRITE,
                             FILE_SHARE_READ | FILE_SHARE_WRITE, &inherit,
                             CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (out == INVALID_HANDLE_VALUE) return -1;
    int code = yh_spawn_wait_handles(argv, argc, out, INVALID_HANDLE_VALUE);
    CloseHandle(out);
    return code;
}

/* yh_env_with：复制父进程环境块并追加/覆盖一项 name=value，返回新块（调用方 free）。
 *
 * 为什么不用 SetEnvironmentVariableA(CreateProcessA(NULL env))：testkit 默认
 * 4 个用例并行，父进程的 setenv 与 CreateProcess 之间存在窗口，两个子进程可能
 * 拿到同一个 YH_TEST_RECORD（表现为随机的「缺少结果记录」，2026-11-02 实测）。
 * 每子进程一份显式环境块把这条路彻底堵死。 */
static char *yh_env_with(const char *name, const char *value) {
    char *parent = GetEnvironmentStringsA();
    if (parent == NULL) return NULL;
    size_t parent_len = 0;
    while (parent[parent_len] != 0 || parent[parent_len + 1] != 0) parent_len++;
    parent_len += 2; /* 含收尾的两个 NUL */
    size_t name_len = strlen(name);
    size_t value_len = strlen(value);
    char *block = (char *)malloc(parent_len + name_len + value_len + 2);
    if (block == NULL) {
        FreeEnvironmentStringsA(parent);
        return NULL;
    }
    memcpy(block, parent, parent_len);
    FreeEnvironmentStringsA(parent);
    /* 覆盖块结束符（parent_len-1），追加 name=value 后再补两个 NUL。 */
    char *cursor = block + parent_len - 1;
    memcpy(cursor, name, name_len);
    cursor += name_len;
    *cursor++ = '=';
    memcpy(cursor, value, value_len);
    cursor += value_len;
    *cursor++ = 0;
    *cursor = 0;
    return block;
}

/* yh_win_spawn_test：启动测试用例（argv = [binary, id]）。
 * stdout/stderr 写 log_path，stdin 接 NUL；记录路径经 YH_TEST_RECORD 传给子进程
 * （Windows 运行时的 fd 3 首次写入时按该变量创建/截断记录文件）。
 * 返回表索引 pid（1..64），失败 -1。 */
int yh_win_spawn_test(char **argv, int argc, const char *record_path,
                      const char *log_path) {
    if (record_path == NULL || log_path == NULL) return -1;
    char *command = yh_build_command(argv, argc);
    if (command == NULL) return -1;
    SECURITY_ATTRIBUTES inherit;
    inherit.nLength = sizeof(inherit);
    inherit.lpSecurityDescriptor = NULL;
    inherit.bInheritHandle = TRUE;
    HANDLE log = CreateFileA(log_path, GENERIC_WRITE,
                             FILE_SHARE_READ | FILE_SHARE_WRITE, &inherit,
                             CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (log == INVALID_HANDLE_VALUE) { free(command); return -1; }
    HANDLE input = CreateFileA("NUL", GENERIC_READ,
                               FILE_SHARE_READ | FILE_SHARE_WRITE, &inherit,
                               OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (input == INVALID_HANDLE_VALUE) {
        CloseHandle(log);
        free(command);
        return -1;
    }
    /* 每个子进程一份显式环境块，记录路径不会与并行用例串台（见 yh_env_with）。 */
    char *environment = yh_env_with("YH_TEST_RECORD", record_path);
    if (environment == NULL) {
        CloseHandle(log);
        CloseHandle(input);
        free(command);
        return -1;
    }
    STARTUPINFOA startup;
    PROCESS_INFORMATION process;
    ZeroMemory(&startup, sizeof(startup));
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = input;
    startup.hStdOutput = log;
    startup.hStdError = log;
    ZeroMemory(&process, sizeof(process));
    char *application = yh_is_path_like(argv[0]) ? yh_app_path(argv[0]) : NULL;
    BOOL ok = CreateProcessA(application, command, NULL, NULL, TRUE, 0,
                             environment, NULL, &startup, &process);
    free(application);
    free(environment);
    CloseHandle(input);
    CloseHandle(log);
    free(command);
    if (!ok) return -1;
    CloseHandle(process.hThread);
    int pid = yh_child_store(process.hProcess);
    if (pid < 0) {
        TerminateProcess(process.hProcess, 1);
        CloseHandle(process.hProcess);
    }
    return pid;
}
