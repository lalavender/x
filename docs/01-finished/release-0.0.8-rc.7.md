# 0.0.8-rc.7 — 换行终结语句预发布（发布流程修复）（Gitea Actions 发布首次打通）

本 Release 分发支持「换行终结语句」的种子：简单语句、`module`/`import`、
类型别名、结构体字段与枚举成员可以省略行尾分号；同一行相邻语句仍用 `;`
分隔。

rc.3 已修复容器内共享闭包缓存的身份记录（绝对路径挂载后
`relative_to(ROOT)` 抛错）与取种时 GitHub API 连接偶发 SSL/EOF 无重试两处
CI 问题。rc.4 继续修 GNU/Linux x86_64 端：该端只在 Apple container 的 amd64
模拟里构建，`make test-llvm` 的 `run/20-bytebuf.yh` 在模拟器下运行崩溃
（信号 5），因此发布流水线对 x86_64 端只做构建与打包，运行证据以真机为准
（见 `docs/todo.md` D3）；Darwin/ARM64 与 Linux/AArch64 两端的完整门禁照常
执行。

CI 由仓库内的 Gitea Actions 承担：`.gitea/workflows/ci.yml`（分支门）与
`.gitea/workflows/release.yml`（tag 发布，三端构建 + cc4 打包 + 发布
GitHub Release）。
