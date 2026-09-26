# yh

极简 yh 语言编译器。用户源文件唯一使用 `.yh` 后缀；

## 目录



## 编译流程



目标程序的模块搜索顺序是目标文件目录、`-path` 路径、`~/.ws_module`、`libs/` 和编译器内置模块路径。
`builtin` 与 `libc` 的宿主 `.v` 文件只通过编译器内部路径注入，不是目标语言兼容入口。

## 方法接收器



## 使用

```bash
make
```

常用命令：



## 构建与测试

```bash
make test
```

全量测试中的 `tests/test/*_test.ws` 使用 ws 的测试块运行器；其余历史 `*_test.ws` 主程序回归由
`tests/run_all.sh` 复制到普通临时文件名后直接编译，避免改变原有测试语义。
测试块支持 `test "name" { ... }`、`test name() { ... }` 和匿名 `test { ... }` 三种形式。

## graphify

仓库支持使用 graphify 做依赖和死代码分析：

```bash
GRAPHIFY_OUT=graphify-out graphify update .
GRAPHIFY_OUT=graphify-out graphify god-nodes
```

graphify 的 V 提取器针对宿主 `.v` 编译器源码；`.ws` 用户源文件是否被当前 graphify 版本分类，
应以运行输出为准。图谱输出目录已被忽略，不提交生成物。
