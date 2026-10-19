# 自带 Darwin SDK stub（Zig 式交叉链接，2026-10-19）

## 结论

`compiler/darwin-sdk/` 随编译器分发聚合 `libSystem.tbd`（SDK 26.4）+
`SDKSettings.json` + `manifest.json`。纯 `.yh` 程序在**没有安装 Xcode/CLT
SDK、PATH 中没有 xcrun/clang/ld** 的环境下可完成 Mach-O 链接并运行；
`SDKROOT`/`YH_DARWIN_SDK` 仍可覆盖。

## 内容与来源

```text
compiler/darwin-sdk/
├── usr/lib/libSystem.tbd   # 334KB 聚合 TAPI（Zig 0.16 libc/darwin，Apple SDK 26.4）
├── SDKSettings.json        # {"Version":"26.4","MinimalDisplayName":"26.4"}
├── manifest.json           # 版本、来源、SHA-256、边界说明
└── README.md               # 用途、许可、查找顺序、重新生成
```

- `libSystem.tbd` SHA-256：`751d8c48…`；`SDKSettings.json`：`44cc2e06…`。
- 许可：源自 Apple macOS SDK，受 Apple SDK 许可约束；按 Zig 式随编译器分发，
  再分发责任由发布方评估。不是完整 SDK。

## 查找顺序（`compiler/cmd/darwin_link.yh`）

1. `SDKROOT`（显式最高）
2. `YH_DARWIN_SDK`
3. 可执行文件附近：`darwin-sdk`、`compiler/darwin-sdk`、
   `../compiler/darwin-sdk`、`../../compiler/darwin-sdk`、
   `../share/yh/darwin-sdk`、`../lib/yh/darwin-sdk`
4. 原生 Darwin：`xcrun --sdk macosx --show-sdk-path`
5. 非 Darwin 交叉：失败并提示提供 `SDKROOT` 或自带 bundle

`make install` 在 Darwin 上把 bundle 安装到
`$(PREFIX)/share/yh/darwin-sdk/`；仓库内 `bin/yh-darwin-arm64` 通过
`bin/../compiler/darwin-sdk` 找到。

## 工具

`tools/llvm-darwin-sdk-bundle.py`：

- `--check`：校验 manifest 与摘要；
- `--from-zig <libc/darwin>`：复制聚合 stub，生成 `SDKSettings.json`/manifest；
- `--from-sdk <sdk> --version 26.5`：复制 `libSystem` + `usr/lib/system/*.tbd`
  闭包；默认拒绝含 `arm64e.x1` 的 SDK27（固定 lld 21.1.8 不兼容）。

## 门禁

`tests/selfhost/llvm-darwin-bundled-sdk.py`（已接入 `make test-llvm-darwin`）：

- 清空 `SDKROOT`/`YH_DARWIN_SDK`，`PATH` 只含“记录并退出 127”的假
  `clang/clang++/ld/ld64.lld/codesign/xcrun/cc/gcc`；
- 编译并运行 `llvm-darwin-fixedpoint.yh`，断言 `LC_BUILD_VERSION`：
  `minos 14.0`、`sdk 26.4`，外部工具日志为空；
- 显式 `SDKROOT` 指向固定宿主 SDK（26.5）时，`sdk` 变为 26.5，证明覆盖优先级。

结果：`make test-llvm-darwin` 20 项 PASS（含原 19 项与 bundle 门）。

## 未解决（后续）

C 源交叉（目标 C 编译器 + Darwin 头文件）、编译器自举的 `libc++`/Darwin
目标包（LLVM/lld/桥）、frameworks/Objective-C、SDK 版本矩阵/API 面、
许可与更新流程，见
[Darwin 交叉编译遗留边界](../03-design/yh-Darwin交叉编译遗留边界.md)。
