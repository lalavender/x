# 工具：代码流程图（`just codeflow`）

`tools/yh-codeflow.py` 扫描当前 `compiler/` 源码，生成一个**自包含**的 HTML
（内联 CSS/JS/SVG，不引 CDN），用来直观看编译器的结构与数据流：

```bash
just codeflow                                  # → tmp/codeflow/index.html
python3 tools/yh-codeflow.py --out /tmp/cf.html
python3 tools/yh-codeflow.py --check           # 只解析并打印统计（门禁用）
```

## 三个视图

| 视图 | 节点 | 边 | 用途 |
| --- | --- | --- | --- |
| ① 模块依赖 | 17 个模块 + 外部依赖（`cli`/`hash`/`os`） | `import`（76 条） | 看分层与越界 |
| ② 模块调用强度 | 模块 | 函数级调用聚合到模块（边宽=调用次数） | 看真实的动态耦合 |
| ③ 模块内文件调用 | 模块内文件 + `@其他模块` | 文件间调用（点=`@` 为跨模块） | 看某个模块内部的数据流 |

交互：滚轮缩放、拖拽平移、双击复位、悬浮看详情、点侧栏模块下钻到文件级。
深链：`index.html#imports`、`#calls`、`#m=build`。

## 数据与精度

- **模块/文件/函数**：正则扫描 `module`/`import`/`fn`/`struct` 声明；规模与
  `just code-stats` 一致（17 模块 / 179 文件 / 1859 函数）。
- **调用边是近似图**：先剥掉注释与字符串字面量，再按「限定调用 `mod.fn(...)`
  用本文件的 import 别名解析 → 非限定调用优先同模块唯一声明 → 文件 import 的
  模块里唯一声明 → 全仓唯一声明」的次序匹配；解析不出的记 `unresolved`
  （目前 3 条）而不猜。`@[extern]` 声明不进索引（它们是平台 API，不是内部流程）。
- **布局**：Tarjan 求强连通分量 → 缩点图 Kahn 拓扑分层（最长路径）→ 重心法
  排序（前向/后向各两轮）→ 输出确定坐标；画布按最宽一层自适应。JS 只做
  平移/缩放/悬浮，不重排，所以刷新不跳图、生成结果可逐字节复现。

## 何时不用它

- 需要精确调用关系（含间接调用、函数指针、回调）时，以 `just code-stats` +
  `rg` 或编译器的 iface 产物为准；本工具的图是结构导览，不是语义证明。
- 超大模块的函数级图不展开：工具按文件聚合，避免几百个函数挤成一团。

## 自测

`tests/tools/yh-codeflow/check.py`（`just test` 内）：

1. `--check` 退出 0，三套布局的边端点都在坐标表里；
2. HTML 单一 `<script>`、无 NUL、内嵌 DATA/LAYOUT 可 JSON 解析；
3. 规模与模块汇总一致、`import` 边数量正常；
4. 连续两次生成逐字节一致（布局确定性）。
