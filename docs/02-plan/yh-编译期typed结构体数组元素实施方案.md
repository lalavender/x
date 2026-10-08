# yh 编译期 typed 结构体数组元素实施方案

日期：2026-10-06。状态：**已交付**。

## 目标

扩展 CT3 当前的按值聚合模型，使定长数组可包含已支持的结构体元素。数组字面量、嵌套数组字段、复制、参数传递和嵌套返回都按值深复制；经数组下标读取的结构体成员可以在局部数组副本上读写。

成功标准：单文件与同模块跨源文件 `.yh` 语料分别验证结构体数组构造、结构体字段内的数组复制、数组形参和嵌套数组返回；调用方与被调方、原值与副本互不串改。原有 `make test` 和 `make selfhost-native` 全绿。

## 语义边界

- 数组元素仅扩展为已有执行器支持的结构体；结构体字段仍限整数、受支持的定长数组与嵌套结构体。
- 数组和结构体仍遵守值语义；没有引入 slice/pointer 成员或改变切片别名规则。
- 嵌套 typed 调用的数组返回继续由调用方帧接管深副本；顶层聚合结果仍保持现有限制。

## 实施与验证

1. 新增 `tests/yh-run/run/86-comptime-struct-array-values.yh` 和 `tests/modules/projects/comptimelocal/src/main/aggregate_arrays.yh`，先以现有编译器确认因为结构体数组不在执行器支持范围而失败。
2. 扩展数组支持判定和递归复制：数组元素是数组或结构体时递归克隆，其余仍要求整数叶元素；数组下标成员路径保留根局部绑定，确保写入归属当前副本。
3. 跑定向语料、`make`、`make test`、`make selfhost-native` 与 `git diff --check`；仅在所有门全绿后滚动种子，并冷编和核对 SHA-256。

## 验收结果

- 新增 `run/86-comptime-struct-array-values.yh`，期望输出 1422，覆盖数组字面量中的结构体元素、结构体字段数组复制、数组形参和嵌套返回，以及副本成员写入隔离。
- `tests/modules/projects/comptimelocal/src/main/aggregate_arrays.yh` 通过另一个源文件发起编译期调用，覆盖同模块跨源文件路径。
- `make test`：语法正例 71/71、反例 44/44；运行语料 run 85/85、fail 89/89、pass 8/8，共 182/182。
- `make selfhost-native`：模块产物固定点 14/14、自解析 64 个源文件、语法/运行语料、模块 17/17、项目 82/82 和其余探针全部通过。
- `make seed` 后冷编 `make` 成功；种子 SHA-256：`ccba81ebca3396f674794cac3b3aa30a61f3a7c49463b5da0b51f98d0affdae4`。
