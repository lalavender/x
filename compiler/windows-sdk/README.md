# compiler/windows-sdk —— Windows 目标的导入库 stub（W1-4）

Windows/x86_64 目标（`x86_64-pc-windows-msvc`）走**零 CRT** 路线（方案 §3 D2）：
yh 自己的运行时只经 `kernel32.dll` 触达系统，不依赖 msvcrt/UCRT，也不打包任何
微软 SDK 二进制。但 PE 链接必须有**导入库**来解释 `GetStdHandle` 这类外部符号，
所以这里放「导入库的源码」：

| 文件 | 作用 |
| --- | --- |
| `def/kernel32.def` | 最小导出面（文本），逐条对应 `backend/llvm_windows_runtime.yh` 的真实消费者 |
| `manifest.json` | DLL 名、导入库文件名、导出列表、`.def` 的 sha256（漂移守卫） |
| `README.md` | 本文件 |

`.lib`（COFF 导入库）**不入库**：仓库根 `.gitignore` 把 `*.lib` 当构建产物，且它是
从 `.def` 可确定重建的派生物（实测同一 `.def` 两次生成的字节完全相同）。

## 生成与校验

```bash
just windows-sdk          # = python3 tools/windows-sdk.py generate（写缓存根）
just test-windows-sdk     # = python3 tests/selfhost/llvm-windows-sdk.py（四件事全查）
```

生成器优先级：`llvm-dlltool -m i386:x86-64` → `lld-link /lib /def:` → `lib.exe`。
实测前两者产物**逐字节相同**（2026-10-27），`identity.json` 仍记录实际用的工具，
以便换工具链时可追溯。

## 查找顺序（编译器 W1-5 必须镜像）

1. `$YH_WINDOWS_SDK` —— 指向含 `lib/` 与 `manifest.json` 的 SDK 根；
2. 仓库 bundle（本目录，本地开发可 `--out compiler/windows-sdk` 就地生成）；
3. 都没有时给出可操作诊断，**不静默回退**到系统 Windows SDK。

## 改动纪律

- 加一条导出：同步改 `def/*.def`、`manifest.json` 的 `exports` 与 `def_sha256`，
  并确认 `backend/llvm_windows_runtime.yh` 里真有消费者（不做投机性覆盖）；
- 门禁会独立检查**三处**：清单哈希、导出面、导入库符号面——只改一处必红；
- 需要换 ABI（如未来接 mingw）时另开目录，不复用本目录。
