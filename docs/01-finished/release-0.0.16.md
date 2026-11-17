# 0.0.16 — 编译诊断 V 风格化、项目装载身份去重

正式版。种子链：0.0.16-rc.2 → 0.0.16（由 rc.2 候选的种子构建；rc.1 未发布，
无资产可供取种）。

本版在 0.0.15 基础上合并三块工作：编译诊断全面 V 风格化（D0–D5 收尾）、
「项目装载身份与链接对象去重」的四条结构性修复，以及仓库记录清理。

## rc 历程

| tag | 结果 |
| --- | --- |
| 0.0.16-rc.1 | Windows 门红：`gen3-split-narrow-ports` / `f4-ct-facts-mirror` 链接失败（`proj` 引用 libc `realpath`，这两个夹具拷真实模块子集、不链接 yh 的 Windows shim）；`publish` 跳过、未产生 Release |
| 0.0.16-rc.2 | 修复后四端全绿（linux-x64 / linux-arm64 / darwin-arm64 / windows-x64），prerelease 发布、8 资产；发布二进制三门验收通过 |

## 主要内容

**1. 编译诊断 V 风格化（D0–D2 起于 2026-11-15，D3–D5 收尾于 2026-11-17）**

- 头行 `path:line:col: 错误:` 之后输出上下各 2 行源码 + `~~~`/`^` 精确下划线；
  CJK 按显示宽 2、tab 展开 4 空格、CRLF 去 `\r`、长行围绕 caret 开窗。
- 位置审计：`token.err_at`/`err_range`/`index_at_offset`/`real_index`（合成 token
  一律回指真实 token）、`check/diag.file_span`（跨文件片段）、`errors.bind_source_path`
  （路径与源码同源校验）。147 例失败语料全部带片段与 caret，列号越界 0。
- 旁路收编：`errors` 新增 `err_path_pos`（路径级）与 `ice`/`fmt_ice`（内部错误）；
  `testkit`、`build/*`、`check` 接口头的直写诊断全部改走 `errors`，只剩
  `compiler/link/*` 的链接器原文（规范 §6 明确不映射）。
- `说明:` 行与建议：期望/实际类型显示、未声明名字与未知类型的「是否想用」
  （有界编辑距离 ≤2）、18 个高频值内核码的 `vk_help`。
- 颜色只在 TTY：`YH_DIAG_COLOR=always|never` > `NO_COLOR` > `isatty(2)`；
  管道永远无色。`YH_DIAG_PLAIN=1` 可回退到旧单行形态。
- 观测工具：`tests/diagnostics/`（`check.py` + 11 个夹具 + 自动生成 `baseline.md`），
  不接入阻断链。

**2. 项目装载身份与链接对象去重（四条结构性修复）**

- **项目身份 = 真实绝对路径**：`build.pj_root_key`（`link.realpath` → `proj.canon`）
  + `pj_load_root`，`load_project` 入口与 `yh test` 的设根处统一规范化。「同一目录
  两种拼写 = 两个项目」消失——这正是 0.0.15 里 `ld.lld` 报 `duplicate symbol` 的根因。
- **产物标签冲突诊断**：`proj.mod_tag_conflict` + `build.pj_check_mod_tags`，在
  `pj_topo` 首行（早于任何 tag 进缓存键/对象路径）报「模块产物标签冲突」并给出
  两个项目根，不再留给链接器。
- **链接对象去重**：`link.mb_row_dup` 在 argv 装配处跳过重复对象路径，
  `YH_LINK_TRACE` 非空时给「重复链接对象已去重」说明。
- **Linux 目录枚举 `DT_UNKNOWN` 兜底**：`project_dir.linux.{x64,arm64}.yh` 在
  `d_type == 0` 时用 `openat(O_DIRECTORY|O_NOFOLLOW)` 探测（x64 `0x30000`、
  arm64 `0xC000`），与 darwin `getattrlistbulk` 语义对齐。
- 顺带修掉：模块 ActionID 混入模块目录的**绝对**路径，使 C4 全局缓存「同项目换
  目录仍命中」失效；改混项目相对目录后恢复。
- 记录：[项目装载身份与链接对象去重](yh-项目装载身份与链接对象去重-2026-11-17.md)。

**3. 记录清理**

- `docs/todo.md` 删除已交付项、修正失效路径；`docs/02-plan/` 下线 7 份「已完成 +
  有交付记录 + 零引用」的方案文档。交付历史见 `docs/finish.md` 与 `docs/01-finished/`。

## 从 0.0.15 升级的可见变化

- 诊断输出形态改变（带源码片段与 caret）；需要旧形态可设 `YH_DIAG_PLAIN=1`。
- 两个同名项目、或同名模块跨项目撞产物标签时，装载期直接报错（此前留给链接器）。
- 同一目录无论用相对/绝对/含符号链接的哪种拼写，都只装载一次。

## 种子与后续

- 本版四端种子已带上述修复，因此**下一版**可以删除 `justfile` 与
  `tests/selfhost/bootstrap/native-selfhost.py` 里的 `YH_STDLIB=../libs` 过渡补丁，
  并回退 `compiler/argvimpl/` 的 `yh_argv_impl` 拆分（后者需 Linux/Windows 实机验证）。
  两项都记在 `docs/todo.md`。
- `libs/sync`（多线程标准库）仍不随本版发布，恢复条件不变：先发出不含 sync 的种子。

## 本地验收（打 tag 前）

| 门 | 结果 |
| --- | --- |
| `just`（dev） | 通过；`./yh --version` = `yh 0.0.16` |
| `just test` | 通过（三层语料 + libs + 工具门 + C4/C6 缓存门） |
| `just selfhost-native` | 通过；`project cases 127/127` |

## 发布验收（用发布出去的二进制）

- **四端**（`release.yml` run `44116167597`）：`linux-x64` / `linux-arm64` /
  `darwin-arm64` / `windows-x64` 全部 success，`publish` 成功；Release 为正式版
  （非 prerelease），8 个资产（四端 `yh-0.0.16-<平台>.tar.gz` 与对应 `.sha256`），
  GitHub 标记为 Latest。
- **发布二进制验收**（本机 darwin-arm64）：`rm -rf bin && just fetch-seed` 取到
  `0.0.16`（sha256 `bf952c2c…`，`--version` = `yh 0.0.16`）；随后 `just`（dev）/
  `just test` / `just selfhost-native`（两代固定点）三门全绿，
  `project cases 127/127`。

## 已知限制

- Linux `DT_UNKNOWN` 分支只在 CI 的 Linux runner 上真实执行（开发机为 Darwin）。
- 链接对象去重的唯一已知触发（两个同名项目）已被装载期诊断拦住，故只有单测覆盖。
- Windows 的 `realpath` 由 `compiler/llvm/windows_shim.c`（`GetFullPathNameA`）实现，
  不消符号链接。
