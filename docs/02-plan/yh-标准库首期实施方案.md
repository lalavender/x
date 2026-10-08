# yh 标准库首期实施方案

状态：**基础模块扩展已实施**。标准库源码直接放在 `libs/<模块>/`，不设置
`src/` 子目录。本阶段暂不处理跨平台差异，不改造 libc `printf` 变参。
设计契约见[标准库设计](../03-design/yh-标准库设计.md)。

## 目标

建立可由 `YH_STDLIB` 加载的真实 yh 标准库项目，提供 `io`、`os`、`memory`、
`string`、`math`、`time` 基础模块，并通过模块项目验收证明标准库层参与导入
解析、接口生成、链接和运行。

## 实施与验收

1. 将项目源码根改为 `.`，把已有 `io` 移到 `libs/io/io.yh`。验证：从 `libs/`
   直接扫描并能导入 `io`。
2. 新增 `memory`、`string`、`os`、`math`、`time` 模块，API 契约见标准库设计。
   验证：实际调用显式分配/释放、字符串比较、文件描述符、C 数学函数和单调时钟。
3. 扩展 `tests/modules/` 项目验收，覆盖模块导入、返回值、精确输出及错误路径。
4. 同步模块与标准库文档。验证：`make`、`make test`、`make selfhost-native`、
   模块项目验收和 `git diff --check` 全绿。

## 本期不做

- 自动发现/安装时打包标准库路径；当前通过 `YH_STDLIB` 显式指定项目根。
- libc `printf` 裸变参、隐式 heap 属性、完整 Unicode/格式化/错误类型 API。
- 跨平台 API 统一和其他目标平台验收。
