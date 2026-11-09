# yh（玉衡）编译器

yh 是极简的静态类型语言。本仓库提供 yh 编译器与标准库。

- 前端：单遍解析，产出受检快照。
- 代码生成：唯一后端是 LLVM 21。
- 链接：内嵌的 lld。
- 目标平台：Linux/x86_64、Linux/AArch64、macOS/ARM64、Windows/x86_64。
- 当前版本：`0.0.12`。
- 自举：编译器源码用 yh 编写，靠种子编译。

下文中的 `yh` 指仓库根目录的编译器可执行文件。Windows 上该文件名为 `yh.exe`。

## 术语

- **种子**：上一版编译器二进制，文件名 `yh-<平台>-<架构>`。种子不入库。
- **自举**：用种子编译编译器源码，得到新一代编译器。
- **固定点**：两代编译器产出的模块对象与接口逐字节相同。
- **受检快照**：前端检查后的程序快照，交给 lowering 阶段。
- **门禁**：`just` 中的自动化检查目标。例如 `just test`。

## 快速开始

1. 安装 [just](https://just.systems/)。
2. 运行 `just fetch-seed`。该命令把本平台种子下载到 `bin/`。
3. 首次构建或换机时，运行 `just bootstrap`。该命令先准备固定 LLVM 闭包。然后冷编编译器。
4. 运行 `./yh --version`，确认编译器可用。

```sh
just fetch-seed     # 下载本平台种子到 bin/（首次）
just bootstrap      # 准备 LLVM 闭包并冷编（首次/换机）
just                # 日常构建：冷编 compiler/，产出根目录 yh
just --list         # 列出全部目标
./yh --version      # 打印编译器版本
```

编译单文件：

```sh
./yh hello.yh -o hello    # 产物路径由 -o 指定
./hello                   # 运行
```

```yh
pub fn main() int {
    printf("hello, yh\n");   // printf 由内置 prelude 提供
    return 0;
}
```

日常门禁：

```sh
just test              # 三层回归
just selfhost-native   # 自举主门
```

## 项目模式

目录内有 `project.toml` 时，`yh` 按项目构建。

```toml
[project]
os = "host"       # linux / darwin / windows / host
arch = "host"     # arm64 / x64 / host
name = "demo"
source = "src"
```

- `os` 与 `arch` 必填。
- `name` 必填，且必须是标识符（字母或下划线开头，只含字母、数字、下划线）。
- `source` 指定源码目录。
- 入口模块名必须是 `main`。

常用命令：

| 命令 | 作用 |
| --- | --- |
| `./yh build` | 构建项目。默认产物是 `<项目根>/.build/<name>` |
| `./yh build -o out` | 指定产物路径 |
| `./yh build --link core` | 只链接 `[link]` 中的组，可以重复 |
| `./yh build <module>` | 指定构建根模块 |
| `./yh check` | 只做语义检查，不产出后端产物 |
| `./yh run` | 构建后运行入口模块 |
| `./yh test` | 发现、构建并运行测试 |
| `./yh list` | 列出模块。`--resolve NAME` 显示绑定来源 |
| `./yh version` | 显示项目名与版本 |
| `./yh --version` | 显示编译器版本 |

`yh test` 的选项：

| 选项 | 作用 |
| --- | --- |
| `--list` | 只列出测试身份与声明位置 |
| `--no-run` | 只构建测试对象，不生成入口，不链接，不执行 |
| `--filter SUBSTR` | 只运行身份含该子串的用例 |
| `--timeout SECS` | 单例超时秒数，默认 15 |

通用选项：

| 选项 | 作用 |
| --- | --- |
| `--target TRIPLE` | 选择完整输出目标 |
| `-O0` / `-O2` | 优化级别，默认 `-O0` |
| `--emit-llvm` | 只写 LLVM 文本，每模块一个 `.ll` |
| `--legacy-system` | 启用兼容 `system(cmd)` 接口 |
| `--backend llvm` | 代码生成后端，只接受 `llvm` |

目标 triple：

| 平台 | triple |
| --- | --- |
| Linux/x86_64 | `x86_64-unknown-linux-gnu` |
| Linux/AArch64 | `aarch64-unknown-linux-gnu` |
| macOS/ARM64 | `aarch64-apple-darwin` |
| Windows/x86_64 | `x86_64-pc-windows-msvc` |

`--target` 还接受 `x86_64-apple-darwin`。该目标未验证，CI 不覆盖。

链接与 C 互操作：

- `[link]` 组写库文件路径。`.a` 静态按需加载，`.so`/`.dylib` 动态链接。
- `[link-<os>-<arch>]` 中的同名组替换公共组。
- `[c]` 段加入 C 源文件、预编译对象与系统库。
- yh 侧用 `@[extern] fn` 声明 C 函数。

## 标准库

`libs/` 是标准库项目，项目名是 `yh_libs`。

| 模块 | 作用 |
| --- | --- |
| `os` | 文件、目录、进程与错误 |
| `sys` | 系统调用封装 |
| `io` | 字节流读写 |
| `string` | UTF-8 视图与所有权字符串 |
| `fmt` | 字符串插值与格式化 |
| `json` | JSON 文档模型与查询 |
| `toml` | TOML 1.1 解析与文档 |
| `cli` | 命令行声明与解析 |
| `net` | TCP 与地址 |
| `num` | 十进制与 f64 互转 |
| `math` | 数学函数 |
| `memory` | 分配器 |
| `libc` | C 库常用原语 |
| `time` | 时间与时钟 |
| `testing` | 语言内测试辅助 |

加载方式，按优先级：

1. 显式依赖：写 `[dependencies] yh_libs = { path = "../libs" }`，然后 `import yh_libs.os as os;`。
2. 环境变量：设置 `YH_STDLIB=<libs 根>`，然后 `import os;`。
3. 默认发现：编译器在 `<exe>/libs`、`<exe>/../libs`、`<exe>/../share/yh/libs` 查找。

示例：

```yh
module main;

import os;

pub fn main() int {
    let opened os.FdResult = os.open_path("demo.txt", os.write_options());
    if (opened.fd < 0) {
        return 1;
    }
    let data [3]u8 = [1, 2, 3];
    os.write_some(opened.fd, data[0..3]);
    os.close_file(opened.fd);
    return 0;
}
```

## 语言速览

```yh
struct Point { x int; y int; }

fn scale(p Point, k int) int {
    return (p.x + p.y) * k;
}

fn sum(nums ... int) int {       // 类型化变参：体内是 []int 切片
    let acc int = 0;
    for v in nums { acc += v; }  // for-in 遍历数组、切片、区间 0..n
    return acc;
}

pub fn main() int {
    let p Point = Point{ x: 1, y: 2 };   // 命名式；位置式 Point{1, 2}
    let a [4]int = [1, 2, 3, 4];          // 数组字面量不带类型前缀
    let s []int = a.to_type([]int);      // 切片视图：{长度, 数据}
    printf("%d %d %d\n", p.x, p.y, s[0]);
    printf("%d\n", sum(a[0], a[1], a[2], a[3]));
    printf("%d\n", scale(p, 2));
    switch p.x {
    case 1, 2 { printf("small\n"); }
    default { printf("other\n"); }
    }
    return 0;
}
```

示例输出：`1 2 1`、`10`、`6`、`small`。

- 类型后置：`let x int = 1;`。
- 指针写作 `*T`。`.` 对指针自动解引用。
- 内建类型：`int`、`i8`、`i16`、`i32`、`i64`、`u8`、`u16`、`u32`、`u64`、`f32`、`f64`、`bool`、`char`、`void`。
- 数组 `[N]T` 按值传递。切片 `[]T` 是 `{len, data}` 视图。
- 类型化变参写作 `nums ... int`，体内是 `[]int`。
- `for v in xs` 遍历数组、切片与区间 `0..n`。
- `switch` 支持 `case 1, 2` 与 `default`。
- 属性写作 `@[extern, noreturn]`。
- `extern fn` 无函数体时引用 C 符号。
- 显式转换用 `x.to_type(T)`。
- 旧 C 关键字（`while`、`do`、`typedef`）是报错保留字。
- 源文件可以有 `module <名>;` 头。文件含 `import` 时必须先写该头。

## 测试

```sh
just test               # 三层回归
just test-libs          # 全部标准库测试
just selfhost-native    # 自举主门
```

- `just test` 有三层：
  1. `tests/yh/check.py`：ANTLR 参考语法语料。正例接受，反例拒绝。
  2. 同一批语料走编译器 `--syntax-check`。
  3. `tests/yh-run/check.py`：运行语义语料，含 run、fail、pass 三类。
- `just selfhost-native` 覆盖两代固定点、自解析、全量语料、模块与项目验收。
- `just test-libs` 运行全部标准库测试：`libs/` 的 test 块（O0/O2）、cli/os/libc 外部 runner，以及 TOML/string/num/fmt 专项与安装后仓库外导入。

专项门：

| 门 | 范围 |
| --- | --- |
| `just test-llvm` | Linux/x86_64 的 LLVM 全门 |
| `just test-llvm-linux-arm64` | Linux/AArch64 运行时与 C ABI（容器内） |
| `just test-windows-sdk` | Windows 导入库与清单一致 |
| `just test-windows-abi` | Win64 按值聚合的 C 互操作 |

## 构建缓存与种子

- 设置 `YH_BUILD_CACHE=<目录>` 后，缓存树迁到该目录。
- 默认可执行文件仍在 `compiler/.build`。
- 多个 worktree 各指一处缓存目录，互不覆盖。
- C4 起 `YH_CACHE=<目录>` 指定全局中间产物缓存（默认平台缓存目录，
  `YH_CACHE=off` 关闭）；只放 obj/.s.i/.s.ct/.fchk/.fir，最终程序仍在项目
  `.build`。`yh cache info|clean|trim|verify` 做运维，`YH_CACHE_DEBUG=1`
  输出 ActionID 与 miss 原因。
- `just seed` 把已验证的 `yh` 覆盖到 `bin/yh-<平台>-<架构>`，并更新 `.sha256`。
- 种子只在 `just test` 与 `just selfhost-native` 全绿后滚动。
- `just fetch-seed` 从最新 GitHub Release 下载种子。

## 发布与 CI

- 分支门在 `.github/workflows/ci.yml`，四端并行。
- 推送版本 tag（`x.y.z` 或 `x.y.z-rc.N`）触发 `.github/workflows/release.yml`。
- 发布说明 `docs/01-finished/release-<tag>.md` 缺失时，发布失败。
- `.github/workflows/perf.yml` 每日生成性能基线，不设硬门。

## 输出格式与平台

目标 triple 决定产物形态。

| 宿主 | 产物 | 运行环境 |
| --- | --- | --- |
| Linux/x86_64 | ELF x86_64 | 本机 Linux |
| Linux/AArch64 | ELF AArch64 | 本机 Linux |
| macOS/ARM64 | Mach-O arm64 | 本机 macOS |
| Windows/x86_64 | PE/COFF x86_64 | 本机 Windows |

- 内嵌 lld 完成链接。编译器不依赖系统安装的 LLVM。
- Windows 链接需要导入库（`kernel32.lib`）。`just` 自动生成导入库。
- macOS 链接需要 SDK 桩。仓库自带 `vendor/darwin-sdk/`。

## 工具

- `just code-stats`：统计 `compiler/` 下 yh 源码的行数与目录分布。
- `just codeflow`：扫描 `compiler/` 生成自包含 HTML 代码流程图
  （`tmp/codeflow/index.html`，模块依赖 / 模块调用 / 模块内文件调用三视图）。
- `just explorer`：启动本地 Compiler Explorer。

## 目录结构

- `compiler/`：编译器源码，17 个模块。
  - `gen`：全局状态与共享工具
  - `lex`：词法与行尾归一化
  - `parse`：语法分析
  - `ast`：AST
  - `check`：只读一致性校验
  - `comptime`：编译期求值
  - `builtin`：prelude 登记表
  - `lower`：受检快照 → IR
  - `ir`：目标无关 SSA
  - `backend`：LLVM 发射
  - `build`：构建引擎
  - `proj`：项目模型与产物路径
  - `cache`（目录 `build/cache/`）：缓存键 schema 与 ActionID/OutputID
  - `link`：汇编、链接与进程
  - `testkit`：语言内测试执行器
  - `main`（目录 `cmd/yh/`）：CLI 声明/解析（`libs/cli`）、参数映射与分派
- `libs/`：标准库
- `tests/`：语法、运行、模块、自举与专项语料
- `tools/`：门禁脚本与 `yh-explorer`
- `docs/`：设计、计划、完成与 ADR
- `bin/`：平台种子，不入库
- `vendor/darwin-sdk/`：Darwin SDK 桩

## 文档

- [docs/yh.g4](docs/yh.g4)：语法参考
- [docs/03-design/](docs/03-design/)：设计文档
- [docs/02-plan/](docs/02-plan/)：计划文档
- [docs/01-finished/](docs/01-finished/)：完成文档
- [docs/finish.md](docs/finish.md)：交付流水
- [docs/todo.md](docs/todo.md)：待办
- [docs/adr/](docs/adr/)：决策记录

## 当前状态与限制

- 已完成：四个平台的编译、运行与自举。
- 已验证：`0.0.12` 的发布流水线四端全绿（run `42081751704`）。见 [0.0.12 发布说明](docs/01-finished/release-0.0.12.md)。
- 切片越界是未定义行为。见 [语义边界](docs/03-design/00-语义边界-0.0.1.md)。
- 数组转切片不做生命周期证明。
- C 互操作按值只接受标量、函数指针与非空 `extern` struct/union。见 [extern 自动 C ABI](docs/03-design/yh-extern自动C-ABI设计.md)。
- 编译器拒绝切片、顶层按值数组与普通 yh 聚合作为 C ABI 参数。
- 用户 C 裸变参：跳过，设计决定不做。见[设计稿](docs/03-design/yh-用户裸C变参交互设计.md)。
- Windows CRT 的文件 API 按 ACP 解释路径。见 [docs/todo.md](docs/todo.md) 的 VENC-2 遗留。
