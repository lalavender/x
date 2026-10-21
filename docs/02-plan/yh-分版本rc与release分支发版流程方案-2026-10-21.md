# yh 分版本 rc/release 分支发版流程方案（2026-10-21）

## 背景

当前发版是「单条 `llvm` 分支 + tag 即触发」：

- 开发与发布共用 `llvm`，没有候选期，`0.0.5`→`0.0.7` 三天连发；
- `.circleci/config.yml` 的 `release` workflow 匹配**任意** tag
  （`only: /.*/` + `ignore: /.*-rc\..*/`），远端 `seed-llvm-x64-2026-10-19`
  这类非版本 tag 一推也会走三端构建与发布；
- rc tag 被 release workflow 忽略，`0.0.7-rc.1` 的三端种子只能手工构建上传，
  没有 CI 证据；
- 默认分支 `arm64` 落后 `llvm` 137 个提交且不含任何 0.0.5–0.0.7 tag；
- 版本号漂移：`compiler/README.md` 与 `tools/compiler-performance.py:208`
  仍写 `0.0.5`（0.0.6/0.0.7 的 bump 提交没同步这两处）。

本方案给出**每版本两条分支 + rc 先行**的流程：先发多个 rc，用 rc 二进制验收，
再合并到 release 分支发正式版。

## 目标

1. 开发与发布分离：代码只进 `<version>-rc`，`<version>-release` 只收合并。
2. 每个 rc 都是一次可下载、可回读验收的发布（三端种子 + prerelease Release）。
3. 验收对象是**发布出去的 rc 二进制**，不是工作区里本地编出来的那一份。
4. 正式版本由该版本最后一个 rc 二进制编出，与验收对象同源。
5. 非版本 tag 不再触发发布；正式 tag 必须落在对应 release 分支上。

## 分支与 tag 模型

| 对象 | 命名 | 来源 | 生命周期 | 规则 |
| --- | --- | --- | --- | --- |
| 开发/候选分支 | `0.0.8-rc` | 上一个 `<ver>-release` | 该版本发完即删 | 全部提交在这里；`project.toml` 版本写目标正式号 `0.0.8` |
| 稳定分支 | `0.0.8-release` | 上一个 `<ver>-release` | 长期保留，作为下一版基线与默认分支 | 只接受 `git merge --no-ff 0.0.8-rc`，不含直接提交 |
| 候选 tag | `0.0.8-rc.1`、`-rc.2`… | 打在 `0.0.8-rc` 上 | 永久 | 发布 prerelease Release，带三端种子资产 |
| 正式 tag | `0.0.8` | 打在 `0.0.8-release` 的合并提交上 | 永久 | 发布正式 Release；CI 校验祖先关系 |

版本号在 rc 期就冻结为目标正式号，因此**最后一个 rc 与正式版是同一提交**，
正式发布零代码 diff（沿用 `0.0.7-rc.1` 的既有先例：清单写 `0.0.7`，
rc 序号只出现在 tag 与资产名里）。

## 一次版本的完整流程

### 1. 切分支（每版本一次）

```bash
# 上一版稳定分支（0.0.7 当时没有 release 分支，先补一条指向 tag）
git branch 0.0.7-release 0.0.7
git push -u origin 0.0.7-release

git checkout -b 0.0.8-rc 0.0.7-release
git checkout -b 0.0.8-release 0.0.7-release
git push -u origin 0.0.8-rc 0.0.8-release
```

### 2. 开发（只动 `0.0.8-rc`）

- `compiler/project.toml` 的 `version` 写 `0.0.8`；
- 写 `docs/01-finished/release-0.0.8-rc.1.md`（发布说明，rc 与正式各一份）；
- 本地门禁：`make`、`make test`、`make selfhost-native` 全绿。

### 3. 打 rc tag

```bash
git tag -a 0.0.8-rc.1 -m "0.0.8-rc.1：<一句话主题>"
git push origin 0.0.8-rc.1
```

### 4. tag 流水线（自动）

三端（linux-arm64 / linux-x86_64 / darwin-arm64）取**最新已发布 Release** 的种子
→ `make bootstrap` → 平台专项门 → 语法与运行语料 → `make selfhost-native`
→ 取 cc4 → 打包 `yh-0.0.8-rc.1-<platform>.tar.gz` + `.sha256` → 发布
**prerelease** Release。

### 5. 回读验收（关键：用 rc 二进制验证）

```bash
rm -rf bin && make fetch-seed     # 取到刚发布的 0.0.8-rc.1 种子
./bin/yh-darwin-arm64 version      # 或目标平台种子，确认能跑
make                               # 用 rc 种子冷编编译器
make test
make selfhost-native               # 两代产物逐字节一致（固定点）
```

验收不过就回 `0.0.8-rc` 修，打 `0.0.8-rc.2`（种子自动取 rc.1），重复 3–5。

### 6. 合并并发正式版

```bash
git checkout 0.0.8-release
git merge --no-ff 0.0.8-rc
git tag -a 0.0.8 -m "0.0.8：<主题>"
git push origin 0.0.8-release 0.0.8
```

tag 流水线与第 4 步相同，但发布**正式** Release（种子取该版最后一个 rc，
因此正式二进制由验收过的 rc 编出）。

### 7. 收尾

- 删 `0.0.8-rc`（提交已由 tag 永久保存），保留 `0.0.8-release`；
- 默认分支指向最新的 `<ver>-release`；
- `docs/finish.md` 记录：rc 序列、每个 rc 的失败原因与修法、正式版种子回读结果。

## 种子取法规则

| 场景 | 种子来源 | 理由 |
| --- | --- | --- |
| `0.0.8-rc` 分支流水线 | 最新带资产 Release（含 rc） | rc.N 用 rc.N-1 验证，能第一时间暴露自举退化 |
| `0.0.8-rc.N` tag 流水线 | 最新带资产 Release（不含自身） | 同上 |
| `0.0.8` 正式 tag 流水线 | 最新带资产 Release（即最后一个 rc） | 破坏性变更（新清单字段/新语法）只有 rc 种子认识，正式版必须由它编出 |

统一实现：`tools/fetch-release-seed.py` 增加 `--include-prerelease`（默认开启），
保留 `--published-only` 给「严格用正式种子复现」的场合；排序仍按
`published_at` 倒序（现有 `:63`）。**禁止修改已发布 Release 的资产**
（`0.0.5` 曾替换资产，会让「最新 Release」指向旧版本），要改就发新 rc。

## 需要改的文件

| 文件 | 改动 |
| --- | --- |
| `.circleci/config.yml` `release` workflow | tags filter 改 `only: /^\d+\.\d+\.\d+(-rc\.\d+)?$/`，去掉 `ignore: /.*-rc\..*/` |
| `.circleci/config.yml` `publish` 作业 | tag 含 `-rc.` → `gh release create --prerelease`；正式 tag 先 `git fetch origin "${TAG%-rc.*}-release"` 并 `git merge-base --is-ancestor "$CIRCLE_TAG" "origin/$branch"`，不通过直接失败 |
| `.circleci/config.yml` `ci` workflow | 分支 filter 改为 `only: /^\d+\.\d+\.\d+-rc$/`（迁移期可临时保留 `llvm`）；`*-release` 分支不跑分支流水线，由 tag 流水线覆盖 |
| `.circleci/config.yml` `fetch_latest_seed` | 传 `--include-prerelease` |
| `tools/fetch-release-seed.py` | 新增开关（默认包含 rc Release），文档注释同步 |
| `compiler/README.md`、`tools/compiler-performance.py` | 修版本漂移：不写死版本号，从清单读或只断言 `yh ` 前缀 |

## 验收标准

- rc：三端 tag 流水线全绿；`0.0.8-rc.N` 资产三端齐全且可下载；回读后
  `make` / `make test` / `make selfhost-native` 全绿；`release-0.0.8-rc.N.md` 存在。
- 正式：`git merge-base --is-ancestor 0.0.8 origin/0.0.8-release` 成立；
  三端全绿；`release-0.0.8.md` 存在（缺失即发布失败，不用兜底文案）；
  种子回读后 `yh version` 输出 `yh 0.0.8`。

## 明确不做

- 不加 `develop` / `hotfix` 分支：`*-rc` 兼作开发线，严重缺陷回 rc 修、顺延发 rc，
  不引入四段版本号。
- 不为 rc 单独降级门禁：rc 与正式跑同一套三端全门，证据链一致；省时间是次要收益。
- 不追求本地全平台：本地只保证本平台门禁绿，多平台由 CircleCI 承担（沿用现有分工）。
