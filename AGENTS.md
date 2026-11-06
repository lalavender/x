# yh

极简 yh 语言编译器。用户源文件唯一使用 `.yh` 后缀；

## 开发策略（必须遵守）


**写 `.yh` 代码前先读 [docs/03-design/yh-编码规范.md](docs/03-design/yh-编码规范.md)**
——排版、命名、类型与转换（隐式只允许整数加宽）、可见性与模块、控制流、注释、
文件组织、错误处理与资源、字符串、测试、编译期各处细则，以及提交前清单都在那里；
本节只列不可让步的硬要求。


- 结构体和函数都要有详细注释说明
- 修改完代码都要构建验证
- 每次修改代码完成之后都要在tests目录中生成.yh测试用例，并确保测试通过
- 安装ripgrep，使用ripgrep进行搜索
- 用中文回答，如果是代码用中文注释
- 计划的任务记录在docs/todo.md
- 完成的任务记录在docs/finish.md
- 每次修改完代码都要构建验证
- 每个文件尽量保持在500-1000行
- 结构体和函数都要有详细注释说明
- 语法设计文档放在 docs/03-design/
- 计划任务文档放在 docs/02-plan/，任务完成后删除文档
- 完成任务文档放在 docs/01-finished/
- 所有临时文件都放到tmp/目录
- 日常开发运行just dev 和 just test就可以,提交代码前运行just build
- just selfhost-native提交代码用CI验证

## 编译流程：需要时参考 `docs/03-design/yh-编译流程-当前实现.md`

## 修改语法规则

1. 修改docs/yh.g4 分析语法的合理性，不允许存在歧义
2. 制定修改计划
3. tests目录添加测试用例
4. 开发确保测试用例全部通过
5. 刷新docs 下的所有文档

## yh编译器使用

常用命令：

```bash
./yh build                 # 构建当前项目（产物名取 project.name）
./yh build --emit-llvm     # 额外保留每模块 .ll 到 <build>/llvm/
./yh build --emit-asm      # 额外保留每模块 .s 到 <build>/asm/
./yh run                   # 构建并运行 main 模块
./yh version               # 项目名与版本
./yh --version             # 编译器版本（编码进二进制，不读 project.toml）
./yh list [--resolve name] # 列出模块/解释导入绑定
./yh test --list           # 只列出测试身份与文档目标
./yh test                  # 发现、构建并逐例执行测试
./yh test --no-run         # 只构建测试对象与入口，不链接/不执行
./yh test --filter X --timeout 15  # 只跑身份含 X 的用例，单例超时 15 秒
./yh --syntax-check f.yh   # 只做词法/语法检查
./yh --emit-asm f.yh       # 发射汇编
./yh f.yh -o out           # 单文件编译并链接（-o 也可写在文件前，--output 等价）
./yh --help                # 顶层帮助（由 libs/cli 生成）；yh <命令> --help 看单项
```

命令行解析自 CLI-R（2026-10-27）起由 `libs/cli` 承担：声明在
`compiler/cmdline/`（`module cmdline`），`compiler/cmd/` 只做「请求 → 分派」。
帮助文本由库生成（`用法: ` 前缀 + 中文段标题），`-h/--help` 是新增能力。

## 构建与测试

```bash
just test               # 三层回归：ANTLR 语法 + 编译器语法模式 + 运行语义
just bootstrap          # 首次/换机：准备固定 LLVM 闭包后冷编（一条命令，幂等）
just selfhost-native    # 主门：两代固定点 + 自解析 + 全量语料 + 模块/项目验收
just llvm-host          # 只准备本机固定 LLVM 闭包（不编编译器）
just fetch-seed         # 从最新 GitHub Release 取本机平台种子（x64 首次构建前）
just code-stats         # 统计 compiler/ 下 yh 源码规模
just test-libs          # 全部标准库测试（test 块 O0/O2 + 外部 runner + 专项/安装）
just test-llvm-linux-arm64  # F1：Linux/AArch64 LLVM 运行时/C ABI/O0-O2（容器内）
just seed               # 滚种子（仅在全绿后；拒绝带构建机路径的种子）
```


## 缓存
**构建缓存位置**：编译器构建的中间缓存默认在 `compiler/.build`；
设置 `YH_BUILD_CACHE=<目录>`（或 `just BUILD_CACHE=<目录> build`）后整套缓存树
（`targets/...`、`check/` 与 asm/obj/iface/manifest/ir/llvm 六个子目录）迁到该
目录，同一台机器的多个 worktree 各指一处即可互不覆盖；默认可执行文件仍在
`compiler/.build`，缓存位置不改变产物位置。`just test`/`just selfhost-native`
等门禁脚本按项目内 `.build` 布局断言，justfile 对它们统一剥掉该变量，只有
`build`/`dev` 把它显式传给编译器，因此缓存位置不影响门禁结果。该变量由
**正在执行构建的那一代编译器**读取：滚种子前的旧种子不认识它，需等
`just seed` 之后的新种子生效。

**全局内容寻址缓存（C4）**：`YH_CACHE` 指定全局中间产物缓存根（macOS 默认
`~/Library/Caches/yh`，Linux `${XDG_CACHE_HOME:-$HOME/.cache}/yh`），
`YH_CACHE=off` 关闭；`YH_CACHE_MAX_SIZE` 覆盖默认 10 GiB 上限（trim 在 C6）。
布局为 `v1/actions/<ActionID>` + `v1/outputs/<OutputID>` + `tmp/` + `lock`；
模块 obj/.s.i/.s.ct 与函数 `.fchk`/`.fir` 进入全局 store，最终可执行文件仍只留
项目 `.build`。项目 `.build/index/<tag>` 只存 ActionID。缓存读取校验 OutputID，
损坏/版本不符按 miss。C6：同项目构建锁 + 全局写锁（POSIX flock）、
`yh cache info|clean|trim|verify`、按大小/年龄 trim、`YH_CACHE_DEBUG=1`
输出 ActionID 与 miss 原因；Windows 锁后置。测试门禁默认 `YH_CACHE=off`，
C4/C6 专项 `tests/selfhost/llvm-global-cache.py` 使用显式临时目录。



## 版本与发布（单主线 `llvm`）

`llvm` 是唯一开发线与 GitHub 默认分支。

版本号有两处手写来源且**必须与 tag 完全一致**：`compiler/project.toml` 的
`version` 与 `compiler/cmdline/cmdline.yh` 的 `YH_VERSION_TEXT`（`--version` 只读
后者）。rc 期写 rc 号（如 `0.0.13-rc.1`），正式发布前改成正式号并在主线提交。
`release.yml` 的 prepare 校验 tag 形态、tag 与这两处版本号一致，正式 tag 还必须是
`llvm` 的祖先，不一致直接红。

1. 在 `llvm` 上开发；写 `docs/01-finished/release-<tag>.md`（rc 与正式都要写）；
   本地 `just test` + `just selfhost-native` 全绿。
2. 改两处版本号、提交 `llvm`，再打 `git tag -a <ver>` → `release.yml` 四端并行构建、
   cc4 打包、发布 Release（rc tag 发 prerelease，资产同样含四端种子）。
3. **用发布出去的二进制验收**：`rm -rf bin && just fetch-seed` → `just` →
   `just test` → `just selfhost-native`（两代固定点）。
4. 验收不过就在 `llvm` 上修、发下一个 rc（种子自动取上一个 Release）；禁止修改已
   发布 Release 的资产。

**当前状态（2026-11-06）**：tag 发布由 GitHub Actions 的 `release.yml` 承担（四端
并行 + cc4 打包 + `tools/publish-release.py`）；prepare 的三道校验为 tag 形态、
版本号三处一致、正式 tag 在主线上；`workflow_dispatch` 可带 `tag` + `dry_run=true`
演练（四端照常构建、跳过 publish）。仍未落地：GitHub 分支保护的 required status
check 未确认（默认分支已是 `llvm`）。

种子规则：分支与 tag 流水线一律取**最新带资产的 Release（含 rc，排除当前 tag）**，
所以 rc.N 用 rc.N−1、正式版用该版最后一个 rc 编译出来。`release-<tag>.md` 缺失即
发布失败。




## 编码要求

1. 编码前先思考
不要假设。不要隐藏困惑。暴露权衡。

在实现之前： 明确表达你的假设。不确定就问。 如果存在多种解读，展示出来——不要默默选一个。 如果存在更简单的方案，说出来。该反对时就反对。 如果有什么不清楚，停下来。说清楚哪里令人困惑。提问。

2. 简洁优先
解决问题的最少代码。不写投机性代码。

不做超出需求的功能。 一次性代码不做抽象。 没有要求就不加"灵活性"或"可配置性"。 不为不可能的场景做错误处理。 如果你写了 200 行而本来 50 行就够，就重写。 问问自己："一个资深工程师会说这过于复杂吗？"如果是，就简化。

3. 精准修改
只动该动的。只清理自己造成的垃圾。

编辑已有代码时： 不要"顺手改进"相邻的代码、注释或格式。 不要重构没坏的东西。 匹配现有风格，即使你会用不同的方式写。 发现无关的死代码，提一下就好——不要删。

当你的改动产生了孤立代码时： 移除因为你的改动而变得无用的 import/变量/函数。 不要删除改动之前就已存在的死代码，除非被要求。 检验标准：每一行变更都应该能直接追溯到用户的请求。

4. 目标驱动执行
定义成功标准。循环直到验证通过。

将任务转化为可验证的目标：

"添加验证" → "为无效输入编写测试，然后让测试通过" "修复这个 bug" → "编写复现 bug 的测试，然后让测试通过" "重构 X" → "确保重构前后测试都能通过" 对于多步骤任务，写一个简短的计划：

[步骤] → 验证：[检查项]
[步骤] → 验证：[检查项]
[步骤] → 验证：[检查项] 强有力的成功标准让你可以自主循环。模糊的标准（"让它能跑"）需要不断澄清。
准则在起效的表现： diff 中不必要的改动更少，因过度复杂而返工更少，澄清问题出现在实现之前而非犯错之后。
