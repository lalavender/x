# string 标准库专项测试

对应[设计](../../docs/03-design/yh-string标准库设计-2026-10-23.md)与
[ST0–ST6 分期](../../docs/02-plan/yh-string标准库实施方案-2026-10-23.md)。

## 组与 fixture

| 组 | fixture | 覆盖 |
| --- | --- | --- |
| `model` | `tests/modules/projects/stringmodel` | 旧三函数、View 构造/比较/查找/切片/裁剪 |
| `view` | `tests/modules/projects/stringview` | 无分配切分、空片段、多字节/内嵌 NUL 分隔符、迭代器复制 |
| `owned` | `tests/modules/projects/stringowned` | 生命周期、容量、赋值/追加/缩短、自别名、C 边界 |
| `transform` | `tests/modules/projects/stringtransform` | concat/join/替换/ASCII 大小写 |
| `utf8` | `tests/modules/projects/stringutf8` | 严格 UTF-8 校验/遍历/编码 |
| `interop` | `tests/modules/projects/stringinterop` | TOML `Text` 显式适配与所有者释放 |
| `resources` | `tests/modules/projects/stringresources` | 逐分配点失败注入与失败原子性 |

前六组把 fixture 复制到 `tmp/string-test/<组>` 后执行 `yh run`，原 fixture
不会产生 `.build`。`resources` 组把 `libs` 复制到工作目录，逐次改写
`libs/string/00_model.yh` 中的 `STRING_TEST_FAIL_AFTER` 常量，重新构建
fixture 并按场景运行；产品源码常量保持 `-1`。

## 命令

```bash
python3 tests/string/run.py --compiler ./yh --stdlib ./libs \
  --workdir tmp/string-test --group all --opt-level 0
python3 tests/string/run.py --compiler ./yh --stdlib ./libs \
  --workdir tmp/string-test --group resources --opt-level 2
make test-string         # O0 全组 + 参考差分
make test-string-o2      # O2 全组 + 参考差分
make test-string-install # make install 后从仓库外、无 YH_STDLIB 导入 string
make test-string-complexity # 直接匹配耗时探针（只记录，不设固定耗时门）
```

`tests/string/install.py` 检查安装树包含 7 个 string 源码，并把 `stringmodel`
复制到仓库外运行；默认 `../share/yh/libs` 发现失败即报错。

`resources` 组要求每个场景至少出现一次“注入失败且原状态不变”和一次成功；
unknown/空选组、构建失败、超时、缺 fixture、未知输出都记为失败，不记 PASS。

`tests/string/reference.py` 用固定种子生成 92 个用例，把
concat/join/replace/lower_ascii/upper_ascii/utf8_validate/utf8_next/
append_rune 的实际输出与 Python bytes/str 语义逐项比较；生成项目只写
`--workdir`。`make test-string` 先跑七组行为断言，再跑参考差分。

基本组同时登记在 `tests/modules/build-check.py` 的 `stdlib-run` 用例中，
由 `make selfhost-native` 的项目门覆盖；失败注入与参考差分留在专项门。
