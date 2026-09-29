/* 探针入口：stage 产物把 C 入口重命名为 yh_main，这里转发并返回退出码。 */
extern int yh_main(int argc, char **argv);
int main(int argc, char **argv) { return yh_main(argc, argv); }

/* 驱动 -o 兼容层的外部依赖桩：本机差分门只用 --syntax-check /
   --emit-asm，不会真正调用链接器进程。 */
int system(const char *cmd) {
    (void)cmd;
    return 1; /* 非零表示外部命令未执行 */
}
int unlink(const char *path) {
    (void)path;
    return 0;
}
