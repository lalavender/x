/* 探针入口：stage 产物把 C 入口重命名为 yh_main，这里转发并返回退出码。 */
extern int yh_main(int argc, char **argv);
int main(int argc, char **argv) { return yh_main(argc, argv); }
