# 0.0.7-rc.1 — 过渡种子 Release

本 Release 用于分发支持新 `project.toml` 与 F1 自举闭包的过渡种子，供
下一版 `0.0.7` 的 CircleCI tag 流水线从“上一版 Release”取种。

## 内容

- 普通项目 `[link]` 库文件链接：`[project].os/arch`、命名组、目标覆盖、
  `.a`/`.so`/`.dylib`/`.tbd`、`--link` 选择与 `.build` 摘要缓存。
- F1 编译器自举闭包迁移：bridge/lld/LLVM 归档进入 `[link]`，
  运行库参数走 `YH_LINK_RUNTIME_FLAGS`；新编译器 manifest-only。
- 本 Release 的种子已支持上述清单字段与链接语义。

## 资产

- `yh-0.0.7-rc.1-darwin-arm64.tar.gz` / `.sha256`
- `yh-0.0.7-rc.1-linux-arm64.tar.gz` / `.sha256`
- `yh-0.0.7-rc.1-linux-x86_64.tar.gz` / `.sha256`

## 说明

这是过渡 Release，不作为最终功能版本；`0.0.7` 将由 tag 流水线从本
Release 种子自举、跑完整三端门禁后发布。
