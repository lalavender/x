# string 标准库专项测试

对应[设计](../../docs/03-design/yh-string标准库设计-2026-10-23.md)与
[ST0–ST6 分期](../../docs/02-plan/yh-string标准库实施方案-2026-10-23.md)。

## 迁移后的分工

`view`/`owned`/`transform`/`utf8` 的行为断言已迁入
`libs/string/99_tests.yh`（由 `yh test string`、`just test` /
`just selfhost-native`、`just libs-test` 执行）；记录见
[YT4-P3](../01-finished/yh-YT4-P3-string迁移-2026-10-25.md)。

本目录只保留 `yh test` 表达不了的项：

| 组 | fixture / 脚本 | 覆盖 |
| --- | --- | --- |
| `model` | `stringmodel` | 公开面 smoke：旧三函数、View 构造/比较/查找/切片/裁剪 |
| `interop` | `stringinterop` | 跨库 smoke：TOML `Text` 显式适配与所有者释放 |
| `resources` | `stringresources` | 逐分配点失败注入与失败原子性（改写 `STRING_TEST_FAIL_AFTER`） |
| 差分 | `reference.py` | 92 例随机数据与 Python bytes/str 逐项对照 |
| 安装 | `install.py` | `just install` 后从仓库外、无 `YH_STDLIB` 导入 |
| 耗时 | `complexity.py` | 直接匹配耗时探针（只记录） |

`model`/`interop` 把 fixture 复制到 `tmp/string-test/<组>` 后执行 `yh run`；
`resources` 把 `libs` 复制到工作目录，逐次改写
`libs/string/00_model.yh` 中的 `STRING_TEST_FAIL_AFTER` 常量后重建；
产品源码常量保持 `-1`。

## 命令

```bash
python3 tests/string/run.py --compiler ./yh --stdlib ./libs \
  --workdir tmp/string-test --group all --opt-level 0
python3 tests/string/run.py --compiler ./yh --stdlib ./libs \
  --workdir tmp/string-test --group resources --opt-level 2
just test-string         # O0 全组 + 参考差分
just test-string-o2      # O2 全组 + 参考差分
just test-string-install # just install 后从仓库外、无 YH_STDLIB 导入 string
just test-string-complexity # 直接匹配耗时探针（只记录，不设固定耗时门）
```

`tests/string/install.py` 检查安装树包含 7 个 string 源码，并把 `stringmodel`
复制到仓库外运行；默认 `../share/yh/libs` 发现失败即报错。

`resources` 组要求每个场景至少出现一次“注入失败且原状态不变”和一次成功；
unknown/空选组、构建失败、超时、缺 fixture、未知输出都记为失败，不记 PASS。

`tests/string/reference.py` 用固定种子生成 92 个用例，把
concat/join/replace/lower_ascii/upper_ascii/utf8_validate/utf8_next/
append_rune 的实际输出与 Python bytes/str 语义逐项比较；生成项目只写
`--workdir`。`just test-string` 先跑七组行为断言，再跑参考差分。

基本组同时登记在 `tests/modules/build-check.py` 的 `stdlib-run` 用例中，
由 `just selfhost-native` 的项目门覆盖；失败注入与参考差分留在专项门。
