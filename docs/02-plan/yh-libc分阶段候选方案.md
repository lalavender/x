# yh libc 分阶段候选方案

状态：**libc 主体仍为可行性分析后的候选方案，尚未实施**。用户确认的目标是
Linux/AArch64 独立链接、兼容 C ABI 的 libc；此状态不表示已授权全部
实现任务。证据与阻塞矩阵见[分析报告](../01-finished/yh-libc可行性与阻塞点分析-2026-10-02.md)。

L0 的混合实参调用缺陷已按用户单独要求修复并通过主门，见
[完成记录](../01-finished/yh-混合参数调用修复-2026-10-02.md)。2026-10-03
另已实现[自动 C ABI](../03-design/yh-extern自动C-ABI设计.md)，补齐固定参数
的浮点栈溢出、C 聚合/HFA 与函数指针返回；其余 libc 主体任务仍为候选。

## L0：编译器可靠性与交付出口

1. 十个整数/浮点交错实参的调用错误已修复；extern 固定参数的浮点溢出栈参数
   与目标栈布局也已补齐，普通 yh 浮点溢出限制保持现状。
   验证：C/yh 双向、8/9/10/16 个参数、交错与寄存器耗尽形态逐项运行；
   原混合探针已由退出 41 变成 0，正式十参数/十四参数双向回归也已通过。
2. 利用无 main 的模块发射，增加对象/静态归档出口与显式 CRT/libc 链接
   配置；区分宿主工具和目标平台。验证：产出对象与 libc.a，C 程序链接
   自有入口后运行；ELF 没有宿主 libc 导入或动态依赖。
3. 建立 Linux/AArch64 编译器种子和原生回归/固定点门，保留宿主回归。
   验证：Linux 上 make、make test、make selfhost-native 的实际结果。
4. 明确 yh prelude 与独立 libc 的运行时提供方，固定分配器配对契约。
   验证：跨 C/yh 分配、复制、释放时选用同一实现，无重复或意外依赖。

## L1：单线程静态核心子集

1. 实现 memory/string、整数转换、固定参数 read/write/close 等接口。
   验证：C 调用方覆盖边界长度、重叠规则、短读写、错误与原始 syscall
   到 libc 返回值/errno 的转换；逐个声明子集覆盖范围。
2. 实现启动栈解析、argc/argv/envp/auxv、页大小、exit 与初步分配器。
   验证：真实启动入口、不同参数/环境、零长度与溢出分配、收尾顺序。
3. 提供第一批与实现匹配的 C 头文件。单线程 errno 可以先使用全局存储；
   这一阶段不宣称 pthread、应用 TLS 或完整 musl 兼容。

## L2：完整 C 边界与基本 stdio

1. 单独设计 C 裸变参、默认提升与 va_*；实现通用格式化内核。
   验证：寄存器/栈溢出、整数/浮点混合、va_copy、vprintf 与 open mode。
2. C 聚合/HFA/函数指针返回已由自动 C ABI 补齐；专用 C 数据符号仍待实施。
   验证：div 系列、固定参数回调与 signal 返回、公开数据符号、C 侧
   sizeof/offsetof 和真实调用结果。一般 yh pub let 保持现有规则。
3. 补 FILE、缓冲、stdin/stdout/stderr、fflush、错误/EOF 状态。
   验证：C 标准 I/O 调用、重定向、短写与进程退出刷新。

## L3：TLS、原子操作与 POSIX 线程/信号

1. 提供 TP 读写、atomic load/store/CAS/fence 与 IR 副作用契约。
   验证：多线程 errno 隔离、竞争计数、锁的 acquire/release 行为。
2. 接入专用 clone 换栈入口、futex、join/detach、取消点、线程析构。
   验证：线程创建/退出、并发分配和 I/O、阻塞取消、反复 join。
3. 补 setjmp/longjmp、信号入口/恢复与优化器非局部控制流契约。
   验证：恢复寄存器和栈、再次返回、优化开关对照及信号屏蔽行为。
4. 实现 C 应用静态 TLS 初始化及对外线程相关结构/头文件契约。

## L4：完整标准接口与数值能力

1. 补 binary128 C ABI/运算、复数聚合边界与 FPCR/FPSR。
   验证：long double、%Lf/strtold、complex 与 fenv 的 C 调用方。
2. 扩展 allocator、stdio/scanf、数学、时间/时区、locale/wchar/iconv、
   网络/DNS、正则与其他 ISO C/POSIX 接口。
   验证：接口清单、标准一致性语料与 musl 可比场景对照；浮点 NaN/
   infinity/有符号零、舍入与异常单独验收。

## L5：动态 libc

补 Linux PIC/GOT/PLT、ELF 可见性/别名、共享链接与动态装载器，覆盖 TLS
重定位、动态符号与 dlopen/dlsym。验证：先完成共享对象外部链接，再
运行自有 loader；每个 ELF 的依赖、加载与初始化顺序都可审计。

## 仓库实施门

以上是分期建议，不把全部编译器重规划工作加入 libc 前置。
后续语法修改先同步 docs/yh.g4、分析歧义并写设计；行为变更先在
tests/yh-run/ 或 tests/modules/ 加 `.yh` 回归与 C 调用方验收，再运行
make、make test 与 make selfhost-native。全绿后再按独立授权滚种子。
