# tests/toml —— TOML 外部验收门

TOML 的 **API/所有权/资源/文件断言已迁入 `libs/toml/tests.test.yh`**（11 个
`test`、154 条 `$assert`，由 `yh test toml` / `just test` /
`just selfhost-native` / `just libs-test` 执行）；迁移记录见
[YT4-P2](../01-finished/yh-YT4-P2-toml迁移-2026-10-25.md)。

本目录只保留 `yh test` 表达不了的外部门：

| 门 | 脚本 | 内容 |
| --- | --- | --- |
| 一致性 | `conformance.py` | toml-test v2.2.0 `files-toml-1.1.0` 清单（有效 214、非法 467），逐项比对 |
| 分配失败/预算 | `injection.py` | 临时标准库副本注入失败点（当前 124 个）+ `TOML_MAX_BYTES=2048` 预算门 |
| 安装导入 | `install.py` | `just install` 后从仓库外、无 `YH_STDLIB` 导入 toml |

```bash
python3 tests/toml/conformance.py --prepare    # 首次取固定语料（下载并核对 SHA-256）
just test-toml-conformance
just test-toml-injection
just test-toml-install
# API/文件行为：cd libs && yh test toml（或 just test-toml）
```

## 一致性语料（T5）

`tests/modules/projects/tomltestdecoder/` 是官方协议要求的 tagged JSON 解码
桥：表输出 JSON 对象、数组输出 JSON 数组、标量输出 `{type,value}`；浮点用
`fmt/` 的 17 位往返十进制，日期时间补秒并截断到 9 位小数。
`tests/toml/conformance.py` 固定 toml-test v2.2.0 的 `files-toml-1.1.0`
清单，首次 `--prepare` 下载并核对 SHA-256，常规运行不静默联网。

## 分配失败与预算（T4.1）

`injection.py` 在临时标准库副本中注入运行时失败接缝（产品源码不导出
`test_*` API），`tomlinject` 从 0 开始逐次允许更多池分配，直到文档成功；
每个失败点都要求资源错误、无 `document.handle`、重复解析仍干净失败。当前
覆盖 124 个分配点。随后把副本 `TOML_MAX_BYTES` 降到 2048，`tomlbudget`
强制验证累计预算返回 `error_resource_limit`。文件读取缓冲是池外 `malloc`，
不在注入范围。

## 安装（T5.1）

`install.py` 执行 `just install DESTDIR=<tmp>/root PREFIX=/usr`，确认安装树
包含 toml `.yh` 源（当前 12 个，含 Linux/Darwin 两个文件适配），再把
`tomloutside` 放到仓库外，清除 `YH_STDLIB` 后用安装后的 `yh` 通过默认
`../share/yh/libs` 发现构建运行。三端 Release 资产
当前只含 `yh`，标准库由 `just install` 分发；是否改变发布策略见 todo T5.2。

## 限制

- 一致性/注入/安装门只看退出码与协议输出；行为细节由 `yh test toml` 覆盖。
- 分配失败门只覆盖文档池分配；文件读取缓冲的 `malloc` 不在注入范围。
- 表查找为按字节线性比较，大表有 O(n²) 级成本（见 libs/toml/README）。
