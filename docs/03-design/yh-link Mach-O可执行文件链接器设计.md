# yh-link Mach-O 可执行文件链接器设计

日期：2026-10-04。状态：**设计已定，待实施**（TC9/TC10）。

上位文档：[yh-asm 与 yh-link 设计](yh-asm与yh-link设计.md)、
[首版汇编子集契约](yh-link独立项目与首版汇编子集契约.md)（§7bis 已有 Mach-O 对象出口）。

## 1. 目标与边界

**目标**：替掉编译器最终链接步（`compiler/cmd/driver.yh` 的 `clang -o`），
让 `yh` 在 macOS 上不再需要外部工具链就能产出可执行文件。

**边界**：输入只接受本工具自己产的 Mach-O `MH_OBJECT`；只链 libSystem 一个
dylib；不做 C++、不做 weak 符号、不做 `__DATA_CONST`、不产出 dylib。

## 2. 为什么是动态链接，不是静态

先探过静态路线，**走不通**：

- `ld -o out -e _main obj.o`（不带 `-lSystem`）直接报
  `dynamic executables or dylibs must link with libSystem.dylib`。
  ld64 强制任何可执行文件链 libSystem，macOS 也没有静态 libc。
- 自带 OS 层替代 libSystem 也不现实：编译器真正未定义的外部符号有 **18 个**
  ——`_clock_gettime _close _execvp _exit _fork _getattrlistbulk _getpid _kill
  _mkdir _mmap _munmap _open _read _rename _unlink _usleep _waitpid _write`。
  它们来自 yh 的 Darwin OS API 前导声明（`compiler/gen/symbols.yh`），
  其中 `_getattrlistbulk`（`project_dir.darwin.yh` 用它批量读目录）与
  `_execvp`（`cmd/process.yh`）语义复杂，还要自己维护 errno 的 TLS 槽位。

所以必须产出一个**动态**可执行文件：`LC_LOAD_DYLIB` libSystem + 符号绑定。

## 3. 可执行文件布局

照 clang 链出来的最小程序的形态（实测 `ld` 产物）：

| 段 | vmaddr | fileoff | 说明 |
|---|---|---|---|
| `__PAGEZERO` | 0 | 0 | vmsize 固定 `0x100000000`，filesize 0 |
| `__TEXT` | `0x100000000` | 0 | 代码与只读数据，页对齐 |
| `__DATA` | `0x100000000 + text_size` | text 之后 | 可写数据 |
| `__LINKEDIT` | 接 `__DATA` | 页对齐 | 符号表、绑定流、签名 |

load commands（顺序照 clang）：

```
LC_SEGMENT_64 ×4      __PAGEZERO / __TEXT / __DATA / __LINKEDIT
LC_DYLD_INFO_ONLY     重定位与绑定流；导出表也放这里
LC_SYMTAB             nlist 与字符串表
LC_DYSYMTAB           本地/外部/未定义三个区间
LC_LOAD_DYLINKER      /usr/lib/dyld
LC_UUID               16 字节，可随机；决定不了行为，但 otool 与崩溃报告要它
LC_BUILD_VERSION      platform=1(macOS) minos/sdk
LC_SOURCE_VERSION     0
LC_MAIN               entryoff = __TEXT 内 `_main` 的文件偏移，stacksize 0
LC_LOAD_DYLIB         /usr/lib/libSystem.B.dylib
LC_FUNCTION_STARTS    函数起始地址的 ULEB128 增量表（可空）
LC_DATA_IN_CODE       可空
LC_CODE_SIGNATURE     指向 __LINKEDIT 里的签名 blob
```

**入口用 `LC_MAIN` 而不是 `__TEXT,__start`**：不需要 crt1.o，dyld 直接把
`_main` 当入口调用，返回后由 dyld 收尾。这样链接器不必自带启动代码。

## 4. 符号绑定

未定义符号在 libSystem 的导出表里查，然后写成 `LC_DYLD_INFO_ONLY` 的
**普通绑定流**（`bind_off`/`bind_size`），不用惰性绑定：

```
BIND_OPCODE_SET_DYLIB_ORDINAL_IMM   1
BIND_OPCODE_SET_SYMBOL_TRAILING_FLAGS_IMM  + 符号名 + NUL
BIND_OPCODE_SET_TYPE_IMM            BIND_TYPE_POINTER
BIND_OPCODE_SET_SEGMENT_AND_OFFSET_ULEB  目标段 + 段内偏移
BIND_OPCODE_DO_BIND
...
BIND_OPCODE_DONE
```

普通绑定在加载时由 dyld 一次性填好，不需要 `__stubs`/`__la_symbol_ptr`，
也不需要 `dyld_stub_binder`——比自己造 stub 少一大块。

**先不做 chained fixups**：`LC_DYLD_CHAINED_FIXUPS` 是新的推荐格式，但
`LC_DYLD_INFO_ONLY` 的绑定流 dyld 仍然支持，而手写绑定流比构造
`dyld_chained_fixups_header` + 指针链简单得多。等动态链接跑通再迁移。

## 5. ad-hoc 代码签名（arm64 硬要求）

arm64 macOS **拒绝运行未签名的可执行文件**，所以这不是可选项。
`ld` 自己会做（`codesign -dv` 显示 `flags=0x20002(adhoc,linker-signed)`）。

### 5.1 关键：codesign blob 内部是**大端**

`CS_SuperBlob` 与 `CS_CodeDirectory` 里的整数全部是**网络字节序**，与 Mach-O
其余部分（小端）相反。按小端读会把 `0xfade0cc0` 读成 `0xc00cdefa`，
一路错到底。**解析和写出都必须用大端。**

### 5.2 SuperBlob

```
0  magic   0xfade0cc0
4  length  整个 blob 长度（含 12 字节头与索引）
8  count   blob 个数
12 索引[count]：每项 type(u32) + offset(u32，相对 SuperBlob 起点)
```

type 0 = CodeDirectory。linker-signed 只需这一个，不需要 Requirements 与
Entitlements 空洞。

### 5.3 CodeDirectory（version 0x20400，88 字节头）

实测自 `ld` 产物，逐字段核对过：

| 偏移 | 字段 | 实测值 | 说明 |
|---|---|---|---|
| 0 | magic | `0xfade0c02` | |
| 4 | length | 379 | 88 + ident + 32·nCode |
| 8 | version | `0x20400` | |
| 12 | flags | `0x20002` | `CS_ADHOC`(0x2) \| `CS_LINKER_SIGNED`(0x20000) |
| 16 | hashOffset | 91 | 到第一个页哈希 |
| 20 | identOffset | 88 | 到标识串 |
| 24 | nSpecialSlots | 0 | 特殊槽（entitlements 等），本设计不用 |
| 28 | nCodeSlots | 9 | 页数 |
| 32 | codeLimit | 32912 | 被哈希覆盖的字节数 |
| 36 | hashSize | 32 | SHA-256 |
| 37 | hashType | 2 | |
| 38 | platform | 0 | |
| 39 | pageSize | 12 | log2(4096) |
| 40 | spare2 | 0 | |
| 44 | scatterOffset | 0 | |
| 48 | teamOffset | 0 | |
| 52 | spare3 | 0 | |
| 56 | codeLimit64 | 0 | 小于 4 GiB 时留 0 |
| 64 | execSegBase | 0 | |
| 72 | execSegLimit | `__TEXT` 里代码长度 | |
| 80 | execSegFlags | 1 | `CS_EXECSEG_MAIN_BINARY` |
| 88 | identifier | `"<输出名>\0"` | |
| hashOffset | 页哈希 | nCode × 32 | 每 4 KiB 一页，末页不足按实际长度 |

- **`codeLimit` = 签名 blob 的文件偏移**，不是 `__LINKEDIT` 的起点。
  所以末页哈希只覆盖到签名开始处（实测 9 页 × 4096 = 36864 > 32912，
  第 9 页是短的）。
- 页哈希就是 `SHA-256(文件[页起点 .. min(页终点, codeLimit)])`，实测与
  `hashlib` 逐字节一致。
- 签名 blob 后面按需补零，`LC_CODE_SIGNATURE.datasize` 是补零后的长度
  （实测 399 的 blob 配 400 的 datasize）。

### 5.4 SHA-256

链接器自带（`link/src/ln/10_sha256.yh`），向量对 `shasum -a 256`，
覆盖 55/56 字节这个「补齐要不要多开一块」的分界。

## 6. 分期与验收

- **TC9 骨架**：段布局 + 符号解析 + `LC_MAIN` 入口 + 签名，先只链**没有未
  定义符号**的对象。
  验收：`yh_link link -o out probe.o`，`./out` 用 `svc` 直接写 stdout 并
  `_exit(42)`，退出码必须是 42。这一步同时验掉布局与签名——签名不对的话
  dyld 会直接 `Killed: 9`。
- **TC10 绑定**：读 libSystem 导出表 + 绑定流 + `LC_LOAD_DYLIB`。
  验收：编译器自举出的 6 个对象链成可执行文件，`./yh version` 输出与
  clang 链出来的逐字节一致；再把 `make selfhost-native` 的最终链接步切过来。
- **收尾**：`driver.yh` 的 `clang -o` 换成 `yh_link link`；`make install`
  一并安装 `yh_link`。

## 7. 已定的取舍

- **不做静态**：见 §2，ld64 与平台都不允许。
- **先不做 chained fixups**：见 §4，绑定流够用且简单得多。
- **不做 lazy binding**：编译器启动时把 18 个符号一次绑完，惰性绑定省下的
  那点启动时间不值得多一套 stub 机制。
- **不做 `LC_DYLD_EXPORTS_TRIE`**：可执行文件不需要导出符号，导出表留空。
- **签名只做 ad-hoc**：不分发，不需要 Developer ID 与公证。
