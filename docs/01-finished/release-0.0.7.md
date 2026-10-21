# 0.0.7 — 项目库文件链接与自举闭包迁移

本版本完成普通项目 `[link]` 库链接，并把编译器自举闭包迁移到同一套清单。

## 新功能

- `[project].os` / `[project].arch` 必填：
  `linux|darwin|host`、`arm64|x64|host`；显式值作为默认目标，`--target` 可覆盖。
- `[link]` 命名组：组值是具体库文件路径数组；相对路径基于 `project.toml`，
  允许绝对路径，读取时 `realpath` 规范化。
- `[link-<os>-<arch>]` 目标覆盖表；同名组替换公共组，新组追加。
- 支持 `.a`、`.so`、`.so.<版本>`、`.dylib`、`.tbd`；按目标检查后缀、
  ELF/Mach-O/ar/TBD 头和架构。
- `yh build` / `yh run` 支持可重复 `--link`；`check`/`list`/`version`
  拒绝；库项目拒绝；跨目标 `run` 拒绝。
- ELF 选中库使用同一个 `--start-group`；链接顺序为对象 → `[link]` 库 →
  `[c].libs` → 系统库。
- 可选 `[link-options] whole` 整库加载；自举 bridge 使用。
- `.build` manifest 缓存库路径、mtime、size 与内容摘要；选择/内容变化只重链。
- F1：编译器自举 bridge/lld/LLVM 归档进入 `[link]`，运行库参数由
  `YH_LINK_RUNTIME_FLAGS` 提供；新编译器 manifest-only，不再重复注入旧归档。

## 破坏性变更

- 所有 `project.toml` 必须写 `[project].os` 与 `[project].arch`。
- 旧 Release 种子不认识这些字段；升级前必须先从本 Release 取得新种子。
- 种子继续不入库；首次构建前执行 `make fetch-seed`。

## 验证

- Darwin/arm64：`make test` 347/348、`make selfhost-native` 全绿、
  build-check 111/111。
- Linux/aarch64：build-check 111/111、yh-run 344/348、manifest 自举固定点与
  自解析通过。
- Linux/x86_64：过渡种子由 x64 容器构建并完成链接冒烟；完整三端门禁由
  CircleCI tag 流水线在发布前执行。

## 下载与使用

```bash
export GITHUB_REPOSITORY=lalavender/x
export GH_TOKEN=<有 repo 读权限的 token>
make fetch-seed
make bootstrap
```
