# yh LLVM 目标身份与构建身份

2026-10-14，LL2-T 首片。将完整目标从旧 c_dialect 分离，为受检快照与 LLVM 驱动提供
同一身份；本文记录当时的 LL2-T 目标边界，后续 LLVM 发射已在 LL3 及之后接入（Linux/AArch64 于 F1 完成默认切换）。

## 数据契约

gen.TargetInfo 保存 canonical triple、data_layout、OS、架构、C ABI、指针位宽、
字节序和布局版本。字符串借用静态常量，不拥有堆内存。target_resolve 成功返回 0
并填出参，未知目标返回 -1，出参原值不变；解析只查静态表，不初始化或调用 LLVM。

| triple | OS / 架构 | C ABI | 数据模型 |
| --- | --- | --- | --- |
| aarch64-unknown-linux-gnu | Linux / ARM64 | aapcs64 | 64 位指针、小端、layout v1 |
| x86_64-unknown-linux-gnu | Linux / x64 | sysv-amd64 | 同上 |
| aarch64-apple-darwin | Darwin / ARM64 | darwin-aapcs64 | 同上 |
| x86_64-apple-darwin | Darwin / x64 | darwin-amd64 | 同上 |

data_layout 按 LLVM 21.1.8 静态目标机器核对；四个字符串由同版本 clang oracle 的
空 C 输入生成 IR 验证，属于开发核对。正常目标解析与 check 不调用该工具。
布局字符串完整纳入后续后端/缓存身份，不能仅比较指针位宽或 c_dialect。
Windows 在后续平台阶段补齐，不以未知 triple 自动回退 Linux。

## 构建时宿主与输出目标

target_host_info 的函数体通过已有 `$if (darwin)` 与 `$if (arm64)` / `$else`
在编译器构建时选择静态分支。旧种子只需认识现有标记；AArch64 启动编译器生成
x64 候选时，候选的宿主函数选择 x64 分支，不通过 uname 推断。

state_init 初始化 c_host_target 与默认 c_target；target_select 只更新 c_target。
CLI 输出目标、$if 与文件筛选不能改写 c_host_target。WSL x64 上通过 qemu 运行的
ARM64 yh，默认仍是 aarch64-unknown-linux-gnu。本片固化默认输出目标与宿主身份元数据；
现有宿主文件操作仍沿用原平台判断，尚未统一读取 c_host_target。输出 --target 不改变
这些宿主操作；目录/时钟/系统调用桥的统一接入由后续宿主桥阶段完成。

## CLI 与旧路径边界

--target 接收以上完整 triple。-target 也可接完整 triple；旧别名明确映射为：

- gnu / linux / elf → aarch64-unknown-linux-gnu。
- darwin / macos / macho → aarch64-apple-darwin。

未知目标或缺参数为用法错误，退出码 2。过渡期 c_dialect 从 TargetInfo.os 派生，
仅供旧 ARM64 发射器使用。旧后端生成模式明确拒绝 x64，不能发布伪装成 x64 的
ARM64 汇编/程序；check 和 --syntax-check 可以选择已识别 x64 目标。

## 条件与源文件

linux/darwin/arm64/x64 只在 `$if` 条件中按当前 c_target 解析，在该位置不可被同名
局部遮蔽；其他表达式中的同名标识符仍按普通绑定处理。x64 已由 IDENTIFIER 文法
覆盖，没有新增 token 或优先级，因此 docs/yh.g4 不改规则，也没有文法歧义。

项目文件仍只有 .yh 后缀。从 .yh 前向左读取目标段，.linux/.darwin/.arm64/.x64
各段都须匹配，遇到普通名称段结束。例如 main.linux.x64.yh 只参与 Linux x64 项目，
main.linux.arm64.yh 只参与 Linux ARM64；普通 main.yh 不受筛选。函数内条件和文件
筛选共用 TargetInfo，不再把汇编方言等同于 OS/架构。

## 验证与剩余边界

llvm-front-boundary.py 先复现未知目标被接受，再验证严格拒绝、无工具 check、qemu
缺省 ARM64、x64 条件、组合文件筛选、旧后端拒绝 x64，以及跨模块 TargetInfo 消费者。
llvmtarget 还验证解析失败不修改出参、输出目标不修改宿主身份，并加入常规项目门。

本片不宣称 LLVM 代码生成、受检快照、模块 IR 或接口/对象缓存目标身份已经完成；
这些继续由 LL2/LL3/LL9 后续门验收。目标布局元数据也不代替 LL7 的 C 双向互调证明。
