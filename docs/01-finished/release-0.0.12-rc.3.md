# 0.0.12-rc.3 — 修复发布打包步骤的候选路径失效

预发布候选（prerelease）。相对 0.0.12-rc.2 只改发布流水线的打包 shell，编译器行为不变。

## 为什么有 rc.3

0.0.12-rc.2（release.yml run 41966728220）三端成功，只有 windows-x64 失败，失败点是
job 127045359159 的第 10 步「自举门 → 取出 cc4 → 打包资产」：

```
自举候选：dist/selfhost/cc4
cp: cannot stat 'dist/selfhost/cc4': No such file or directory
##[error]Process completed with exit code 1.
```

自举门本身是全绿的：模块固定点 cc3→cc4 一致（48 个产物）、cc4 自解析 148 个源文件 OK、
固定点探针 OK、`compiler-tests` 4/4、`project cases` 130/130。失败在门之后取产物打包。

根因是打包脚本引用了已被自己删除的路径。windows job 的步骤顺序是：

```bash
cp "$cc4" yh            # 成功（Windows 上实际产出 yh.exe）
rm -rf dist/selfhost    # 在这里把 cc4 所在目录删掉
./yh --syntax-check ... # 静默通过
cp "$cc4" "$stage/yh"   # 再引用 $cc4 → 源已不存在
```

linux-x64 / linux-arm64 / darwin-arm64 三端同一位置写的是 `cp yh "$stage/yh"`
（从仓库根的 yh 打包），只有 windows job 沿用了「先取 cc4 路径」的旧写法，因此只有
windows 红。

日志里 `[ -f dist/selfhost/cc4 ]` 明明命中、`cp` 却报不存在，是 Windows/MSYS 的
`.exe` 后缀魔法：`test -f` 与 `cp` 都会给无扩展名的名字补 `.exe` 去查找，第一次
`cp "$cc4" yh` 因此成功并写出 `yh.exe`，删目录之后第二次 cp 才真正失败。

## 修复

- `release.yml` 的 windows-x64 打包步骤改成 `cp yh "$stage/yh"`，与其余三端一致。
- 版本升到 0.0.12-rc.3：`compiler/project.toml` 的 `project.version` 与
  `compiler/cmdline/cmdline.yh` 的 `YH_VERSION_TEXT` 同步（`tools/arch-check.py`
  一致性断言通过）。

## 验证

- 本机用 Git for Windows 自带 coreutils（8.32）+ 干净 PATH，以假 `cc4.exe` 复现两种写法：
  旧写法逐字复现 CI 报错（`cannot stat 'dist/selfhost/cc4'`，退出 1）；新写法成功，且
  `tar -tzf` 的成员名为 `yh`（`fetch-release-seed.py` 的 `extract_yh` 只认这个名字）。
- rc.2 已证明上一轮的桥接修复有效：本次 run 的 step 8「过渡期自举桥」success、
  step 9「Windows/x64 平台门」success。
- rc.3 发布流水线（run 42062242047，commit ab244e3）：**四端全绿，Release 已产出**。
  各 job 从取种到打包全 success，windows-x64 的步骤 8（自举桥）/9（平台门）/10（自举门 +
  打包）均通过；publish 校验四端资产与发布说明后成功发布 prerelease。
  资产：`yh-0.0.12-rc.3-{darwin-arm64,linux-arm64,linux-x86_64,windows-x64}.tar.gz`
  与各自 `.sha256`（8 个文件）。

## 已知边界

- rc.1 / rc.2 的 tag 保留在 git 历史，均未产出 Release 资产；rc.3 是首个四端可完整
  出包的候选。
- 过渡期自举桥与 `tools/ci-bootstrap.py` 继续保留：rc.3 的种子仍取 0.0.11，需等含 W2
  种子的 Release 发布后再删桥（见 docs/todo.md）。
- Windows ACP 遗留（P1）与 rc.1 相同，见 `release-0.0.12-rc.1.md`。
