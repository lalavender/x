# os-demo-explicit

通过 `project.toml` 显式依赖 `../../libs`，使用
`import yh_libs.os as os;`，不依赖 `YH_STDLIB` 环境变量。

```sh
cd examples/os-demo-explicit
../../yh run
```

这是编译器/工具链后续迁移推荐的绑定方式；用户应用仍可继续使用
`YH_STDLIB` 或本地同名模块。
