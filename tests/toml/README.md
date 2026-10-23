# tests/toml —— TOML 标准库验收

本目录放 `libs/toml` 的自有验收 runner。fixture 在
`tests/modules/projects/toml*/`，每个项目复制到 `tmp/toml-test/<组>/`
后构建运行，标准库根通过 `YH_STDLIB` 传入。

## API 组（T0–T4）

| 组 | fixture | 覆盖 |
| --- | --- | --- |
| model | tomlmodel | 句柄、空文档、多文档、输入生命周期、释放幂等 |
| strings | tomlstrings | 四种字符串、转义、NUL、UTF-8、多行裁剪、引号/空键 |
| scalars | tomlscalars | i64 边界与进制、binary64 位模式、布尔、四种时间、查询 out 契约 |
| tables | tomltables | 点键/隐式表/内联表/数组表、定义冲突、遍历顺序、CRLF |
| errors | tomlerrors | UTF-8/BOM、参数、输入/嵌套/键/数字上限、查询边界 |
| files | tomlfiles | 真实文件读取、I/O 错误分类、失败无半成品文档 |

```bash
python3 tests/toml/run.py
python3 tests/toml/run.py --group model,strings --quiet
python3 tests/toml/run.py --compiler ./yh --workdir tmp/toml-test --keep
python3 tests/toml/run.py --prepare-corpus     # 首次取固定语料
python3 tests/toml/run.py --conformance        # API 组 + 一致性门
python3 tests/toml/injection.py                # 分配失败注入 + 预算门
python3 tests/toml/install.py                  # make install 后仓库外导入
```

## 一致性语料（T5）

`tests/modules/projects/tomltestdecoder/` 是官方协议要求的 tagged JSON 解码
桥：表输出 JSON 对象、数组输出 JSON 数组、标量输出 `{type,value}`；浮点用
`fmt/` 的 17 位往返十进制，日期时间补秒并截断到 9 位小数。
`tests/toml/conformance.py` 固定 toml-test v2.2.0 的 `files-toml-1.1.0`
清单（有效 214、非法 467），首次 `--prepare` 下载并核对 SHA-256，常规运行
不静默联网。

## 分配失败与预算（T4.1）

`injection.py` 在临时标准库副本中注入运行时失败接缝（产品源码不导出
`test_*` API），`tomlinject` 从 0 开始逐次允许更多池分配，直到文档成功；
每个失败点都要求资源错误、无 `document.handle`、重复解析仍干净失败。当前
覆盖 124 个分配点。随后把副本 `TOML_MAX_BYTES` 降到 2048，`tomlbudget`
强制验证累计预算返回 `error_resource_limit`。文件读取缓冲是池外 `malloc`，
不在注入范围。

## 安装（T5.1）

`install.py` 执行 `make install DESTDIR=<tmp>/root PREFIX=/usr`，确认安装树
包含 toml `.yh` 源（当前 12 个，含 Linux/Darwin 两个文件适配），再把
`tomloutside` 放到仓库外，清除 `YH_STDLIB` 后用安装后的 `yh` 通过默认
`../share/yh/libs` 发现构建运行。三端 Release 资产
当前只含 `yh`，标准库由 `make install` 分发；是否改变发布策略见 todo T5.2。

## 限制

- 组内断言只看最终退出码和固定成功行；失败项的细节由被测程序打印。
- 分配失败门只覆盖文档池分配；文件读取缓冲的 `malloc` 不在注入范围。
- 表查找为按字节线性比较，大表有 O(n²) 级成本（见 libs/toml/README）。
