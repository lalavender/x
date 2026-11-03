/* yh Windows/x64 栈探测桩：实现 MSVC ABI 的 __chkstk 契约。
 * 调用方把要分配的字节数放在 RAX，调用本函数后自己 sub rsp, rax。
 * 本函数必须：按页触碰 [rsp-size, rsp) 的每个页（触发 guard page 增长栈），
 * 且**除 RAX 外不改变任何寄存器**——包括 r10/r11。
 *
 * 为什么 r10/r11 也要保存：LLVM 把页探测当序言的一部分发射，**不按 call
 * 建模它的寄存器破坏**，寄存器分配器因此会把活值留在 r10/r11 上跨过探测。
 * 实测（2026-11-03，合并后主线）：`__yh_test_assert` 把 i32 %line 暂存在 r10d，
 * 紧接着 `call __chkstk`，桩把 r10 当临时寄存器 → 断言记录的行号变成
 * 0x1F6FFDF8 这类垃圾值（列号在 r8d 里所以正常）。MSVC 的 chkstk.asm 同样
 * 保存 r10/r11，就是为这个契约。
 *
 * 符号不叫 __chkstk：静态 CRT 自带 __chkstk（自举时必须用 CRT 的那份）。
 * 链接模板用 /alternatename:__chkstk=__yh_chkstk，只有零 CRT 时才落到本桩。
 *
 * **RAX 必须保持为调用方传入的帧大小**：LLVM 的序言是
 *   mov eax, <frame>; call __chkstk; sub rsp, rax
 * 所以探测循环只能递减一个临时寄存器（r11）。早先的实现直接递减 RAX，
 * 结果调用方只 `sub rsp, rax` 掉除不尽的余数，帧远小于实际需求，
 * 任何 >4 KB 的帧都会在第一次访问局部变量时 0xC0000005 崩溃
 * （实测：29-stress-capacity / 148-deep-struct / llvm-runtime-memory）。
 *
 * 循环条件必须**先比较再递减**：先 `sub` 再比较会让计数 <4096 回绕成
 * 巨大无符号数，循环永不退出（实测 `$assert(false, "msg")` 触发 0xC00000FD
 * 栈溢出）。这里照 MSVC 的形态：size < 4096 直接走尾段。 */
__attribute__((naked, used)) void __yh_chkstk(void) {
    __asm__ volatile(
        "pushq %r10\n\t"
        "pushq %r11\n\t"
        "movq %rsp, %r10\n\t"
        "movq %rax, %r11\n\t"
        "cmpq $4096, %r11\n\t"
        "jb 2f\n\t"
        "1:\n\t"
        "subq $4096, %r10\n\t"
        "testq %r10, (%r10)\n\t"
        "subq $4096, %r11\n\t"
        "cmpq $4096, %r11\n\t"
        "jae 1b\n\t"
        "2:\n\t"
        "subq %r11, %r10\n\t"
        "testq %r10, (%r10)\n\t"
        "popq %r11\n\t"
        "popq %r10\n\t"
        "ret\n\t");
}

/* __yh_build_envp：把宿主环境块转成 `char *envp[]`（零 CRT 入口给 main 的第三参）。
 *
 * 为什么需要它：Windows 的零 CRT 入口 `__yh_zero_crt_start` 只解析 argv；用户写
 * `fn main(argc int, argv **char, envp **char)` 时第三参就是寄存器里的垃圾值
 * （实测合并后 os.spawn(argv[0], argv, envp) 直接访问违例）。POSIX 的 CRT 一直
 * 会填 envp，这里把同一契约补上：GetEnvironmentStringsA 的块是连续的
 * `K=V + NUL` 项 + 结尾双 NUL，只需要把每项起点收集成指针数组（字符串本身继续
 * 借用宿主块，进程生命周期内有效，因此不释放块）。
 * 分配走 HeapAlloc（与运行时 malloc 同一来源），失败时返回只有结尾 NUL 的空数组。 */
__declspec(dllimport) char *__stdcall GetEnvironmentStringsA(void);
__declspec(dllimport) void *__stdcall GetProcessHeap(void);
__declspec(dllimport) void *__stdcall HeapAlloc(void *heap, unsigned long flags,
                                                unsigned long long bytes);

char **__yh_build_envp(void) {
    char *block = GetEnvironmentStringsA();
    // 两趟扫描：先数条目（块形如 `K=V\0` 重复 + 结尾双 NUL），再按同样顺序填指针。
    // 数组必须多留 1 个位置放结尾空指针——曾经只按条目数分配、再写 envp[count] = 0，
    // 越界一个指针位，子进程随后在堆上崩溃（0xC0000374，表现为 yh test 的
    // 「崩溃或缺少结果记录」与 os.spawn 访问违例，且随时序时好时坏）。
    unsigned long long count = 0;
    if (block != 0 && block[0] != 0) {
        char *cursor = block;
        for (;;) {
            count += 1;
            while (*cursor != 0) {
                cursor += 1;
            }
            cursor += 1;
            if (*cursor == 0) {
                break;
            }
        }
    }
    char **envp = (char **)HeapAlloc(GetProcessHeap(), 0, (count + 1) * sizeof(char *));
    if (envp == 0) {
        return 0;
    }
    unsigned long long index = 0;
    char *cursor = block;
    while (index < count) {
        envp[index] = cursor;
        index += 1;
        while (*cursor != 0) {
            cursor += 1;
        }
        cursor += 1;
    }
    envp[count] = 0;
    return envp;
}

/* __yh_close_handle：关闭内核句柄的零 CRT 入口（os.wait 用）。
 *
 * 为什么不在 yh 里直接 `@[extern] fn CloseHandle(handle *void)`：编译器运行时
 * 已经为文件 API 发射了 `declare i32 @CloseHandle(ptr)`，而 yh 的 extern 声明
 * 带引号（`@"CloseHandle"`），两份声明在同一个模块里会触发 LLVM 的
 * "invalid redefinition of function"。同类冲突以后还会遇到，这里先按需要
 * 提供一个薄包装，符号名与运行时声明不重叠。 */
__declspec(dllimport) int __stdcall CloseHandle(void *handle);

int __yh_close_handle(void *handle) {
    return CloseHandle(handle) ? 0 : -1;
}

/* __yh_abs / __yh_putchar：零 CRT 下的 libc 基础符号（libs/libc 与测试夹具用）。
 *
 * 只做语义完全等价的最小实现：abs 是整数绝对值，putchar 走 stdout 句柄。
 * 链接模板用 /alternatename:abs=__yh_abs、/alternatename:putchar=__yh_putchar，
 * 有 CRT 时仍用 CRT 的版本。strtod/pow/cos 等需要真正数值实现的符号不在其中
 * （见 todo W1-2b-2：零 CRT 与 C 库互操作的决定）。 */
__declspec(dllimport) void *__stdcall GetStdHandle(int which);
__declspec(dllimport) int __stdcall WriteFile(void *handle, const void *buffer,
                                             unsigned long bytes,
                                             unsigned long *written, void *overlapped);
__declspec(dllimport) unsigned long __stdcall GetLastError(void);

int __yh_abs(int value) {
    return value < 0 ? -value : value;
}

int __yh_putchar(int character) {
    unsigned char byte = (unsigned char)character;
    unsigned long written = 0;
    void *out = GetStdHandle(-11 /* STD_OUTPUT_HANDLE */);
    if (out == 0 || WriteFile(out, &byte, 1, &written, 0) == 0 || written != 1) {
        return -1;
    }
    return (int)byte;
}

/* __yh_isatty：isatty 的零 CRT 实现（os.is_terminal 用）。
 *
 * 零 CRT 用户程序没有 UCRT，libs/os 的 `@[extern] fn isatty` 没地方解析；
 * 链接模板用 /alternatename:isatty=__yh_isatty，有 CRT 时仍用 CRT 的实现。
 * 只对 0/1/2 有意义（fd 3 起是运行时 fd 表里的文件句柄，字符设备判定没有
 * 稳定语义），判定方式是 GetFileType 是否为 FILE_TYPE_CHAR。 */
__declspec(dllimport) void *__stdcall GetStdHandle(int which);
__declspec(dllimport) unsigned long __stdcall GetFileType(void *handle);

int __yh_isatty(int fd) {
    int which = 0;
    if (fd == 0) {
        which = -10;
    } else if (fd == 1) {
        which = -11;
    } else if (fd == 2) {
        which = -12;
    } else {
        return 0;
    }
    return GetFileType(GetStdHandle(which)) == 2 /* FILE_TYPE_CHAR */ ? 1 : 0;
}

/* __yh_rmdir：rmdir 的零 CRT 实现（os.remove_dir 用）。
 * 与 isatty 同理：/alternatename:rmdir=__yh_rmdir 只在没有 CRT 时接手。 */
__declspec(dllimport) int __stdcall RemoveDirectoryA(const char *path);

int __yh_rmdir(const char *path) {
    return RemoveDirectoryA(path) ? 0 : -1;
}

/* __yh_usleep：usleep 的零 CRT 实现（Sleep 毫秒轮转）。
 *
 * 为什么在这里而不是在编译器发射的模块 IR 里：预置库把 usleep 登记成 extern，
 * 模块里已经有一条 declare；再发一条 define 会让 LLVM 报
 * "invalid redefinition of function 'usleep'"。做成 SDK 强定义对象 +
 * 链接模板的 /alternatename:usleep=__yh_usleep 更稳：yh.exe 自己由
 * windows_shim.c 提供 usleep，alternatename 只在符号未定义时接手，不会冲突。
 * 向上取整到毫秒：usleep(500) 至少睡 500 微秒，取整成 0 会变成忙等。 */
__declspec(dllimport) void __stdcall Sleep(unsigned long milliseconds);

int __yh_usleep(unsigned int microseconds) {
    unsigned long milliseconds = (microseconds + 999UL) / 1000UL;
    Sleep(milliseconds);
    return 0;
}
