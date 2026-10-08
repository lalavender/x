# yh 编译期函数 typed 区间 for-in 实施方案

日期：2026-10-05。状态：**完成**。

## 范围

扩展 CT3 typed IR 执行器，让 `@[comptime]` 函数可执行普通整数区间 for-in：
`for value in lo..hi` 与 `for index, value in lo..hi`。不改语法，不引入新的表达式求值器；
边界和循环体继续由普通前端解析、绑定和类型检查。数组/切片迭代依赖聚合值表示，留在后续阶段。

## 实施步骤

1. 增加 `tests/yh-run/run/72-comptime-forin-range.yh`，先验证旧执行器在编译期调用路径拒绝 for-in。
2. 在 `compiler/comptime/ct_ir.yh` 从语句表达式边读取两个边界，检查其可赋给 i32，
   通过稳定绑定槽写入元素值和可选的零起始下标。
3. 每次迭代沿用共享 typed IR 步数预算；return 向外传播，break 退出当前 for-in，continue 进入下轮。
4. 扩展 `comptimelocal` 项目以覆盖同模块跨文件 CT 正文调用；更新测试/设计/完成文档。

## 验收

用例覆盖单绑定、双绑定、空范围及 break/continue。运行 `make test` 与 `make selfhost-native`，
确认固定点、模块项目和全部语料通过；门禁全绿后滚动种子、冷编并核对哈希。

## 实际结果

- 旧种子对 run/72 的初始编译期调用报“不支持 for-in”；typed IR 扩展后定向用例通过。
- `make test`：语法 71/71 + 44/44，运行语义 159/159。
- `make selfhost-native`：14 个模块产物固定点一致、62 个源文件自解析、模块 17/17、项目 80/80，其余探针通过。
- `make seed` 后冷编 `make` 和 SHA-256 校验通过。
- 新种子 SHA-256：`eba461e71044ff9a22bdbf7f9c14e4a753d1232decb1969ab25f02ccb0c24d91`。
