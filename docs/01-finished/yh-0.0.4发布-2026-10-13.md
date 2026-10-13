# yh 0.0.4 发布：版本号提升与发布流程种子补代（2026-10-13）

## 背景

CI 首跑的三处阻塞修完后（见
[arm64 目录扫描常量与 CI 首跑修复](yh-Linux目录扫描arm64常量与CI首跑修复-2026-10-13.md)），
准备发 0.0.4。打 tag 前核对发布链路时发现：`release.yml` 的 `darwin-arm64` 作业裸跑
`make`，用的入库 `bin/yh` 是 **2026-10-08（`19e2e3a`）滚的那一代种子**，那一代源码里
「`struct/union/enum` 必须带 pub」门禁还在（`git show '19e2e3a:compiler/parse/parse_decl.yh'`
可查，二进制里也能查到 `必须带 pub`、`字段一律公开` 的字符串），而当前编译器源码已有
12 个模块私有类型——**tag push 后 darwin 作业必失败，`release` 作业（`needs: [linux-arm64,
darwin-arm64]`）不会跑，0.0.4 也就没有 Release 产物**。`ci.yml` 的 darwin 作业早就有
「种子自动补代」，`release.yml` 一直没有。

linux 作业不受影响：`gh release download` 取上一版 Release 的 `yh-*-linux-arm64.tar.gz`
作种子，0.0.3 的 Release 里确实有这个资产（已用只读 API 查过，0.0.1–0.0.3 都有
darwin/linux 两套资产）。

## 改动

1. **版本号**：`compiler/project.toml` `0.0.3` → `0.0.4`；
   `compiler/README.md` 的「version = `0.0.x`」记录同步；
   `tools/compiler-performance.py` 里对 `yh version` 输出的断言 `yh 0.0.3` → `yh 0.0.4`。
   版本号**只在运行时从 `project.toml` 读**（`cmd/project_index.yh` 解析 → `cmd/driver.yh`
   的 `version` 子命令输出），不编进二进制，所以编译器产物与滚种子都不受影响（下面验证里
   有逐字节对照）。
2. **`release.yml` 的 darwin 作业补「必要时补一代 macOS 种子」**：与 `ci.yml` 同一段逻辑，
   探测入库种子是否支持裸 `struct`，落后时把 13 处模块私有类型临时恢复 `pub` → `make` →
   `make seed` → `git checkout -- compiler` 还原源码，再由后续步骤构建 HEAD。
   本作业的检出是一次性的（发布产物就是这一步构建出的 `yh`），所以补代只影响本作业检出内
   的 `bin/yh`，不需要回写仓库；仓库种子追平仍走 `ci.yml` 的 artifact 路径（见 todo）。

## 本地验证（macOS 无法本地执行）

- **YAML 结构**：`yaml.safe_load` 通过；darwin 作业步骤解析为
  `actions/checkout@v4 / 必要时补一代 macOS 种子 / make / 冒烟 / 打包 / actions/upload-artifact@v4`。
- **run 体语法**：从 workflow 抽出该步骤的 run 体（50 行）后 `bash -n` 通过。
- **打桩干跑**：把 `bin/yh` 换成「探针 exit 1」的桩、`make`/`git` 换成记录用的桩，在
  `compiler/` 副本上执行该步骤——输出
  `入库种子落后一代：造「语言规则一代」` → `已临时恢复 13 处类型的 pub` →
  `[stub] make` / `[stub] make seed` / `[stub] git checkout -- compiler` →
  `中间代种子已就位`，退出码 0，事后核对 **13/13 类型都变成 `pub struct`**。
- **不补代路径**：探针成功时该步骤直接 `exit 0`（与 `ci.yml` 一致）。

## 版本号变更后的构建验证

- `make`：`make_rc=0`；**编译器产物逐字节不变**（版本号不编进二进制）——
  变更前 `yh` 的 SHA-256 与变更后相同：
  `33733767fe5f84afd6f14f6662598e8f5615b69d8ca4edf29705991a4ac18a35`
  （与入库 Linux 种子一致，说明这一代二进制就是刚滚过的那一份）。
- `./yh version`（在 `compiler/` 目录下执行，版本号取自该目录的 `project.toml`）：输出
  `yh 0.0.4`。
- `make test`：语法正例 78/78、反例 42/42、运行语料 293/293（`test_rc=0`）。
- `make selfhost-native`：固定点、自解析、语料、modules 与项目验收全绿（`selfhost_rc=0`）。

## 提交与 tag

- 提交：版本号 + workflow + 文档（`asm/`、`link/` 仍不提交）。
- tag：`0.0.4`（annotated，风格与 0.0.1–0.0.3 一致），消息：
  `yh 0.0.4：模块私有类型与 AST 独立模块、导出面收缩；arm64 目录扫描与 CI 首跑修复，发布流程自带种子补代`
- push 触发 `Release` 作业（run `38410260504`）：darwin 作业（含补代）**成功**，linux 作业
  失败，`release` 作业被跳过。

## 首发失败的复盘（run 38410260504）

**darwin 作业：成功，补代真的跑了**（日志实证，11 秒跑完）：

```
入库种子落后一代：造「语言规则一代」（类型临时恢复 pub）
已临时恢复 13 处类型的 pub
宿主平台种子已更新：./bin/yh
中间代种子已就位（本作业检出内的 bin/yh 与 bin/yh.sha256 已更新）
hello, yh!
```

也就是说：不补这一段，darwin 作业必然失败——补代是这次发布能出 macOS 产物的前提。

**linux 作业：失败在容器构建步骤**，原因与编译器无关，是发布工作流自己的两处过时：

```
python3 ./tools/selfhost_snapshot_gate.py --verify-seed "/repo/prevseed/yh"
/bin/sh: 1: python3: not found
make: *** [Makefile:78: verify-seed] Error 127
```

1. 容器里只装了 `build-essential`，**没有 python3**；而 Makefile 的 `verify-seed` 与
   `tools/seed-build.py` 都要 python3（`ci.yml` 的容器一直是 `build-essential python3`，
   所以 CI 从不触发这个坑）。这是 0.0.3 发版之后 Makefile 才引入的依赖，工作流没跟上。
2. 种子取的是**上一版 Release 的 linux 资产**（0.0.3，2026-09-29 构建）——它比
   arm64 `O_DIRECTORY` 那个修复早，仍然带着该 bug；就算补上 python3，它在容器
   （overlayfs）上构建时也会以 `无法打开目录` 失败。仓库现在已入库
   `bin/yh-linux-arm64`（上一代 Linux 种子，已含修复），Makefile 在 aarch64 宿主上本来就
   自动选它，所以下载上一版资产这一步是历史遗留。

**修复**（都在 `release.yml` 的 linux 作业里）：

- 容器安装列表改为 `build-essential python3`；
- 去掉「下载上一版 Release 的 linux-arm64 资产」整步，改为直接用入库
  `bin/yh-linux-arm64`（`make` 不带 `SEED=` 覆盖），与 `ci.yml` 的容器配方一致。

## 边界

- 入库 `bin/yh` 本身**没有**被这次发布追平：darwin 作业只在检出内补代，仓库种子仍是
  2026-10-08 一代；追平路径是下载本版 Release 的 `yh-0.0.4-darwin-arm64.tar.gz`（里面就是
  0.0.4 的 Mach-O `yh`）替换 `bin/yh` 并更新 `bin/yh.sha256`（见 `docs/todo.md`）。
- 补代逻辑已在 macOS 上真实跑通（本版首发 darwin 作业），不再只是打桩干跑。
