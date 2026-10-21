#include <signal.h>
#include <unistd.h>

// EINTR 测试辅助：安装不带 SA_RESTART 的 SIGALRM 处理器。
// 这些函数只在测试进程中调用，不进入标准库或编译器产品路径。

static volatile sig_atomic_t alarm_fired = 0;

static void on_alarm(int signum) {
    (void)signum;
    alarm_fired = 1;
}

// test_install_alarm：安装处理器并设置 seconds 秒后的单次 alarm。
// 成功返回 0（无旧 alarm 时 alarm 返回 0），失败返回 -1。
int test_install_alarm(int seconds) {
    struct sigaction action;
    action.sa_handler = on_alarm;
    sigemptyset(&action.sa_mask);
    action.sa_flags = 0;
    if (sigaction(SIGALRM, &action, 0) != 0) {
        return -1;
    }
    return (int)alarm((unsigned int)seconds);
}

// test_alarm_fired：返回处理器是否已经运行，供 yh 侧确认 EINTR 来源。
int test_alarm_fired(void) {
    return (int)alarm_fired;
}

#include <fcntl.h>
#include <sys/socket.h>

// test_socketpair：创建 Unix 流式 socketpair，并把写端设为非阻塞。
// 流式 socket 的发送缓冲小于一次写入时会产生短写，用于稳定覆盖部分写入路径。
// out[0] 为读端、out[1] 为写端；成功返回 0，失败关闭已创建 fd 并返回 -1。
int test_socketpair(int *out) {
    int fds[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, fds) != 0) {
        return -1;
    }
    int flags = fcntl(fds[1], F_GETFL, 0);
    if (flags < 0 || fcntl(fds[1], F_SETFL, flags | O_NONBLOCK) != 0) {
        close(fds[0]);
        close(fds[1]);
        return -1;
    }
    out[0] = fds[0];
    out[1] = fds[1];
    return 0;
}
