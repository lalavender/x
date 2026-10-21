# os-demo

用 yh 标准库演示：

- 打开/创建/截断/读写/关闭文件
- 用 64 字节缓冲复制文件（处理短读写）
- 流式目录枚举，名称借用读取器缓冲
- 从入口 `envp` 查询环境
- 精确路径 `spawn` 自身子模式并 `wait`

## 运行

本示例使用 OS1–OS5 的 Linux 文件/目录/进程 API；Darwin 新接口接入前请在
Linux 上运行。标准库默认发现已接入（仓库 `<root>/libs` 或安装 `share/yh/libs`）；仍可显式
指定 `YH_STDLIB` 覆盖：

```sh
cd examples/os-demo
YH_STDLIB=$PWD/../../libs ../../yh run
```

显式项目依赖的等价写法见 `examples/os-demo-explicit`。默认发现按可执行文件
附近的仓库 `<root>/libs`、`<root>/bin/../libs` 或安装
`<prefix>/share/yh/libs` 查找；显式 YH_STDLIB/项目依赖优先。
