# 0.0.8 — 换行终结语句与全仓去分号

正式版。0.0.8 的语法与工程两条主线都在这个版本收尾：**行尾分号可省略**，
以及**仓库内 yh 源码整体去掉冗余分号**。

## 语法：换行终结语句

- 简单语句、`module`/`import`、类型别名、结构体字段、枚举成员、`case` 分支
  可以省略行尾分号；同一行相邻语句仍用 `;` 分隔。
- 续行规则：运算符必须写在**上一行末尾**；行首运算符会被当成新语句并报错。
- `}` 前与文件末尾的最后一个分号可省略；`return`/`break`/`continue` 后换行
  即结束语句，裸 `return` 不再吞掉下一行表达式。
- 空语句与块后分号仍然拒绝；结构体字面量字段仍用逗号分隔。

设计与实施记录：
[换行终结语句设计](../03-design/yh-换行终结语句设计.md)、
[换行终结完成记录](yh-换行终结语句-2026-10-22.md)。

## 去分号

- `compiler/`：101 个文件删除 24,514 个分号，保留 1,061 个（同一行语句分隔、
  裸块前）。
- `libs/`、`tests/`、`examples/`：503 个文件删除 11,698 个分号；反例语料、
  冻结性能语料、以及被 `build-check.py` 按精确源码字节改写的项目 fixture
  保留显式分号。
- 记录：[分号删除完成记录](yh-分号删除-2026-10-22.md)。

## 验证

- `make test`：ANTLR 正例 80/80、反例 44/44；运行语料 run 209/210
  （1 条平台 SKIP）、fail 133/133、pass 8/8。
- `make selfhost-native`：cc3→cc4 的 27 个模块产物逐字节一致、自解析 101 个
  源文件、modules 19/19、project cases 115/115。
- 种子：本版由 `0.0.8-rc.7` 编译（rc.N 用 rc.N−1）；`make fetch-seed` 取到
  的种子能冷编无分号源码。

## 工程

- CI/发布由仓库内 Gitea Actions 承担：`ci.yml` 四任务并行（antlr、
  darwin-arm64、linux-arm64、linux-x86_64），`release.yml` 三端并行构建 +
  汇总发布；镜像预建复用，打包后对产物做 `--syntax-check` 自检。
- 发布涉及 GitHub 上传的 SSL/EOF 抖动已加退避重试。
- `YH_LLVM_CACHE` 支持自动定位（显式环境变量 → 仓库缓存 → 主 worktree
  缓存），新 worktree 不再需要手工设置。

## 资产

- `yh-0.0.8-darwin-arm64.tar.gz` / `.sha256`
- `yh-0.0.8-linux-arm64.tar.gz` / `.sha256`
- `yh-0.0.8-linux-x86_64.tar.gz` / `.sha256`

x86_64 只在 Apple container 的 amd64 模拟里构建打包：`run/20-bytebuf.yh`
在模拟器下运行崩溃（信号 5），运行证据以真机为准。
