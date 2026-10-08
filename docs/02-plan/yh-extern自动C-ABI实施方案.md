# extern 自动 C ABI 实施方案

状态：2026-10-03 已完成；证据见[完成记录](../01-finished/yh-extern自动C-ABI-2026-10-03.md)。

目标：按 [设计](../03-design/yh-extern自动C-ABI设计.md) 实现固定参数 C ABI 自动转换。

全局约束：源文件使用 .yh；中文注释；精确修改；临时证据放 tmp/auto-cabi/；保留已有工作区修改；不滚动 bin/yh。

## 任务 1：类型与语法

- [x] 新增 .yh 语法、语义正反例，使用旧编译器观察缺失功能。
- [x] docs/yh.g4、parse_type.yh 增加 C 函数类型；state.yh 与 symbols.yh 签名表保存 ABI；parse_decl.yh 将 extern 签名标记为 C 并检查布局。
- [x] iface.yh 显式保存函数类型 ABI；运行 make 与定向用例。

## 任务 2：共享分类与边界发射

- [x] 新增独立 C/yh 双向项目，用旧编译器确认聚合签名被拒绝。
- [x] gen/abi_c.yh 提供 ABI 描述、游标和位置分类；gen/sem_cabi.yh 实现入口/调用/返回装箱与拆箱；旧 yh 调用路径保持。
- [x] sem_decl.yh 在复制前保存寄存器；覆盖 HFA 先于 >16 字节、剩余寄存器不足、Darwin 栈紧凑布局。
- [x] 执行 C 双向项目与静态 Linux 验收。

## 任务 3：IR、回归与文档

- [x] IRCall、IRFunction 保存 ABI，序列化/验证/缓存升级；SSA 整数后端使用共享分类规则。
- [x] 覆盖 C/yh 函数指针不能互赋、显式转换不能抹掉 ABI、跨模块传递及字段回调。
- [x] make test 与 make selfhost-native 全绿；更新属性设计、语法说明、todo/finish 和完成报告。

审查重点：短聚合尾片读写边界；HFA 栈回退不落入整数寄存器；聚合参数独立副本；小于 32 位的 Darwin 参数扩展；函数指针 ABI 在模块接口与缓存中保持。
