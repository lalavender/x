# todo

只记录**未完成**事项。已完成任务的历史与验证证据见
[finish.md](finish.md) 与 [01-finished/](01-finished/)；方案文档在
[02-plan/](02-plan/)，取舍见 [adr/](adr/)。

## 本轮实施补记（2026-09-30 晚）

项目规划的语法/绑定/缓存/语料四个阶段全部落地并过门后，另清理了
因 0.0.3 遗留的过期引用：README 的 libtcc.a/libtcc1.a 产出说明与
YH_SYSROOT/YH_LIBDIR 环境变量（0.0.3 起链接走系统 gcc/clang，两者
不再需要）、release.yml 的 libtcc1.a 资产转发（stage0 删除后编译
器不再需要运行时库）、AGENTS/README/compiler-README 的 mod.toml →
project.toml 改名、Makefile 尾部失效的开发桥接注释。

## 待办

### MOD-U6：远程获取、版本、锁文件、工作区

本地三层（当前项目/标准库/直接依赖）已交付（MOD-U0–U5，见
[模块与项目管理设计](03-design/yh-模块与项目管理设计.md)）。远程来源、
版本规则、锁文件与工作区**按实际需求另立设计与验收**，不沿用旧 Go
方案承诺（[ADR-0005](adr/0005-yh-mod-toml与按名称导入.md)）。



### 多平台后端（linux/darwin/windows × arm64/x64）

方案见 [多平台架构整理与优化方案](02-plan/yh-多平台架构整理与优化方案.md)。
当前只有 arm64 双方言（GNU/Linux 与 Darwin/Mach-O）；Darwin 方言基础
已在 compiler/target.yh、emit_arm64.yh、driver.yh 就位。x64 后端与
Windows 目标未实施。另：Linux 版含模块系统的 yh-new 发布归档后，才
能重建 Linux 开发/CI 流程（0.0.3 删除 stage0 后失去交叉 ELF 能力）。

### 玉衡 VS Code 扩展

方案见 [VS Code 扩展方案](02-plan/yh-VSCode扩展方案.md)。首发桌面本地；
独立 TypeScript 语言服务器；源码调试待编译器生成调试信息后实施。

- [ ] **VS-U0**：最小扩展、`.yh` 高亮、独立 LSP 进程、构建/运行命令。
- [ ] **VS-U1**：基于现有 `yh-new` CLI 的保存后诊断与进程取消。
- [ ] **VS-U2**：自举编译器分析接口、未保存缓冲区、精确跨文件定义跳转。
- [ ] **VS-U3**：源码调试信息与 DAP 接入。
- [ ] **VS-U4**：扩展集成测试、VSIX、发布与 CI。

### 编译器可选收尾

- [ ] **接口 pub 收缩**：四模块成模时 pub 从宽（顶层与字段全 pub），
  按实际跨模块使用收缩，减小接口文件（ADR-0007 P5 可选项）。
- [ ] **对象缓存键补编译器身份**：compiler/tmp/yh-build 的 manifest
  哈希不含编译器二进制版本；滚动代次下 Makefile 用冷编规避，若要
  启用热缓存需先补键。

## 设计决定不做（非缺口，勿列为任务）

- 裸 C 变参（`...`）在用户源码被显式拒绝（仅编译器内置 prelude 用）。
- 切片越界与生命周期运行时防护（ADR-0001）。
