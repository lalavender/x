# yh 自带 Darwin SDK stub（链接期）

本目录让 yh 在**没有安装 Xcode/CLT SDK** 时也能链接 macOS/ARM64 程序（尤其
Linux/x64 交叉引导）。它只包含 Mach-O 链接所需的 TAPI stub，不是完整 SDK。

## 内容

| 文件 | 作用 |
|---|---|
| `usr/lib/libSystem.tbd` | 聚合 TAPI stub：libSystem 的 install-name、版本、导出符号与 reexport 信息 |
| `SDKSettings.json` | `Version`（`26.4`）与展示名；写入 `LC_BUILD_VERSION sdk` |
| `manifest.json` | 版本、来源、每个文件的 SHA-256，供缓存/审计 |

## 来源与许可

- `libSystem.tbd` 取自 Zig 0.16.0 的 `libc/darwin/libSystem.tbd`（Apple macOS
  SDK 26.4 的 TAPI stub 聚合），`SDKSettings.json` 由 yh 生成。
- 这些文件源自 Apple macOS SDK，**受 Apple SDK 许可约束**；再分发与使用责任由
  发布方自行评估/承担。本仓库按 Zig 式随编译器分发，用于交叉链接。
- 不是 Apple SDK 的完整副本：不含头文件、`libc++.tbd`、frameworks、Objective-C
  SDK、系统 dylib 实现。

## 查找与覆盖

`compiler/cmd/darwin_link.yh` 的优先级：

1. `SDKROOT`（显式，最高）
2. `YH_DARWIN_SDK`
3. 编译器可执行文件附近的 `darwin-sdk` / `compiler/darwin-sdk` /
   `../compiler/darwin-sdk` / `../../compiler/darwin-sdk` /
   `../share/yh/darwin-sdk` / `../lib/yh/darwin-sdk`
4. 原生 Darwin 的 `xcrun --sdk macosx --show-sdk-path`（仅当以上都缺失）
5. 非 Darwin 交叉：失败并提示提供 `SDKROOT` 或自带 bundle

`SDKROOT` 覆盖用于需要宿主精确 SDK/新 API 的场景；bundle 默认版本是 26.4。

**边界**：bundle 只解决**链接期**系统库 stub。`make`/`selfhost-native` 冷编
编译器自身时还要编译 `compiler/llvm/bridge_stub.c`，仍需要宿主 C 编译器与
macOS SDK 头文件；带 `[c] sources` 的项目同理。无 SDK 环境只能运行**已构建**
的 yh 来链接/运行纯 `.yh` 程序。

## 重新生成/校验

```bash
python3 tools/llvm-darwin-sdk-bundle.py --check
python3 tools/llvm-darwin-sdk-bundle.py --from-zig /opt/homebrew/Cellar/zig/0.16.0_1/lib/zig/libc/darwin
python3 tools/llvm-darwin-sdk-bundle.py --from-sdk "$(xcrun --sdk macosx --show-sdk-path)" --version 26.5
```

## 未覆盖（后续考虑）

交叉编译的 C 源、编译器自举的 libc++/静态归档、frameworks/Objective-C、SDK 27
的 `arm64e.x1` 标签等，见
[Darwin 交叉编译遗留边界](../../docs/03-design/yh-Darwin交叉编译遗留边界.md)。
