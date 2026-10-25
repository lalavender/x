# yh Darwin 交叉编译遗留边界（2026-10-19）

## 范围

F2-10 已把 **Mach-O 链接所需的 libSystem stub** 随编译器分发
（`compiler/darwin-sdk/`），纯 `.yh` 程序可在没有 Xcode/CLT SDK 的
Linux/x64 主机上交叉发射、链接并产出可运行 Mach-O。

本文记录**不在该 stub 范围内、后续再处理**的交叉编译问题，避免把
“能链接纯 yh 程序”误认为“完整 macOS 交叉工具链”。

## 1. 带 `[c] sources` 的项目

- 现状：项目里的 C 源由 `compiler/cmd/link_cache.yh` 调用 `YH_CC`/宿主 C
  编译器编译；`compiler/darwin-sdk` 只提供链接 stub，不含 C 头文件与目标
  C 编译器。
- 影响：Linux 上交叉构建含 C 源的 Darwin 项目会失败或产出错误架构对象。
- 同一条边界也适用于**编译器自身构建**：`compiler/llvm/bridge_stub.c` 由宿主
  C 编译器编译；无 SDK 时 `make`/`selfhost-native` 冷编会失败。bundle 只覆盖
  已构建 yh 的链接期，不替代 C 工具链/头文件。
- 后续方案：目标包提供 Darwin C 头文件（Zig 式 `any-darwin-any`）与
  `clang -target aarch64-apple-darwin -isysroot <bundle>`；或限制为
  “交叉只支持纯 `.yh`，C 源回宿主编译”。需在 F2-9 明确拒绝/诊断。

## 2. 编译器自举的 C++ 依赖

- 现状：编译器自身链接固定 LLVM/lld/桥（C++），自举链接需要 `libc++`；
  `compiler/darwin-sdk/usr/lib/libSystem.tbd` **不含 libc++**。2026-10-25 起
  `tools/llvm-darwin-host.py prepare` 把**宿主 SDK 的 `libc++.tbd` 复制进构建机
  闭包**（`llvm-host-darwin-aarch64/libc++.tbd`，摘要入 `host.json.cxx_tbd`），
  `tools/link-closure.py` 将其写进 `[link-darwin-arm64].cxx`；原生自举因此不再
  依赖 `-lc++` 参数或 `SDKROOT`：`cd compiler && ../bin/yh-darwin-arm64 build`
  即可链接（之前会因缺 `-lc++` 输出三万余条未定义 C++ 符号）。
- 影响：Linux/x64 交叉构建 Darwin 版 yh（F2-9）仍受影响——目标包必须自带
  `usr/lib/libc++.tbd`（闭包里的 `cxx` 组只在 darwin 宿主 prepare 时生成）。
- 后续方案：Darwin 目标包直接附带 `usr/lib/libc++.tbd`（Apple SDK 许可，
  与现闭包同一做法），并把静态库路径纳入 F2-9 的自举链接参数与缓存身份。
- 另：Linux 宿主固定包的 lld 模板是 GNU/ELF；交叉构建 Darwin 版 yh 时
  必须换成 Darwin 目标包（`ld64.lld` 模板 + Darwin LLVM/lld/桥归档），
  不能复用 Linux 的 `-Wl,--start-group` 自举 flags。`compiler/darwin-sdk`
  只解决系统库 stub，不解决目标 lld 模板/静态归档。

## 3. frameworks / Objective-C

- 现状：yh 的 Darwin 链接参数只生成 `-lSystem` 与项目 `-l`，不支持
  `-framework`；bundle 不含 framework TAPI。
- 影响：依赖 AppKit/Foundation/Objective-C 的程序不能交叉。
- 后续方案：扩展 `c_libs`/链接配置到 framework 名称，bundle 增加对应
  `.tbd`（或要求 `SDKROOT`）；Objective-C 还需要 clang ObjC 前端与头文件。

## 4. SDK 版本与 API 面

- bundle 固定 `SDK 26.4`，`LC_BUILD_VERSION sdk 26.4`；晚于该版本的 API
  符号不会出现在 stub 中，链接会报未定义符号。
- 固定 LLVM 21.1.8 的 `ld64.lld` 不能解析 CLT SDK 27 的 `arm64e.x1`
  TAPI 标签；bundle 必须锁在已验证区间（当前 26.x）。
- 后续方案：提供 bundle 版本矩阵/更新工具；`SDKROOT` 覆盖宿主精确 SDK；
  在文档中声明最低/最高验证版本。

## 5. 许可、来源与再分发

- `compiler/darwin-sdk/usr/lib/libSystem.tbd` 源自 Apple macOS SDK（经
  Zig 0.16 的 `libc/darwin` 聚合），受 Apple SDK 许可约束；`SDKSettings.json`
  由 yh 生成。
- 当前按 Zig 式随仓库/发行物分发，发布方需自行确认许可与通知义务；不是
  法律意见。
- 后续可选：构建时从本机 SDK 生成（不入库）、或购买/取得再分发许可后
  固定 bundle；更新时同步 `manifest.json` 与缓存身份。

## 6. 产物验证与运行

- 交叉链接只证明 Mach-O 生成正确；**实际运行必须在 macOS 14+**（minOS
  14.0）。Linux 侧只能做 `file`/`otool`/导入清单与差分，不能执行。
- F2-9 的 Mac 侧作业需检查签名、`LC_BUILD_VERSION`、动态依赖与真实运行；
  CI artifact 只传候选/日志，不传 Apple SDK 之外的受限文件。

## 7. 与默认切换的关系

- 以上边界不阻塞 macOS/ARM64 原生默认 LLVM（F2-10 已完成）。
- F2-9 若要做“Linux 交叉产 Darwin 编译器”，必须先决定第 1/2/4/5 项；
  纯 yh 程序交叉链接已由 `compiler/darwin-sdk/` 解决。
