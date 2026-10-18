// c_returns：故意违反 yh 的 noreturn 声明，运行结果应由调用点 trap 终止。
void c_returns(void) {}

// main：从宿主 C 入口进入 YH 探针。
extern int invoke_bad(void);
int main(void) { return invoke_bad(); }
