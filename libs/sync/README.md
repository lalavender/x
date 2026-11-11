# sync 标准库：多线程与同步

日期：2026-11-11。状态：**Darwin 与 Linux 已交付**（pthread）；Windows 仍是
显式失败的占位实现（`platform_ready()` 返回 0），待 L2 补齐。

多线程在这里是**纯标准库能力**：没有 `go`/`spawn` 语法，没有编译期 `shared` 检查，
也没有 `chan T` 类型。语言、AST、检查器、IR 都不参与；库只使用既有的
`@[extern]` C 互操作能力，因此当前编译器直接可用，不需要等新种子。

- API 契约与未定义行为：[doc.yh](doc.yh)
- 设计：[yh-多线程标准库设计](../../docs/03-design/yh-多线程标准库设计.md)
- 实施：[yh-多线程标准库实施方案](../../docs/02-plan/yh-多线程标准库实施方案-2026-11-11.md)

## 加载

```sh
# 1. 显式项目依赖（推荐）
#    project.toml:
#      [dependencies]
#      yh_libs = { path = "relative/to/libs" }
#    main.yh:
#      import yh_libs.sync as sync;

# 2. 显式标准库根
YH_STDLIB=$PWD/libs ./yh run

# 3. 默认发现（仓库根 yh + libs/，或安装前缀 share/yh/libs）
./yh run
```

## 快速示例

线程入口固定为 `fn(*void) void`：多参数与返回结果都装进一个结构体，把指针
`to_type(*void)` 后传入；join 返回后读取结果。

```yh
import sync

// Job 是线程参数包：count 次加一，结果写回 total。
struct Job {
    mutex *sync.Mutex
    total *i64
    rounds int
}

fn worker(arg *void) void {
    let job *Job = arg.to_type(*Job)
    let i int = 0
    for i < job.rounds {
        sync.mutex_lock(job.mutex)
        job.total[0] = job.total[0] + 1
        sync.mutex_unlock(job.mutex)
        i += 1
    }
}

fn main() int {
    let mutex sync.Mutex
    if (sync.mutex_init(&mutex) != 0) { return 1 }
    let total [1]i64
    let job Job
    job.mutex = &mutex
    job.total = &total[0]
    job.rounds = 100000
    let first sync.Thread
    let second sync.Thread
    if (sync.thread_spawn(&first, &worker, (&job).to_type(*void)) != 0) { return 2 }
    if (sync.thread_spawn(&second, &worker, (&job).to_type(*void)) != 0) { return 3 }
    if (sync.thread_join(&first) != 0 || sync.thread_join(&second) != 0) { return 4 }
    printf("%lld\n", total[0])
    return 0
}
```

批量等待用 `WaitGroup`（`add` 必须在线程启动前），一次性初始化用 `Once`，
条件等待用 `Mutex` + `Cond`。

## 平台支持

| 目标 | 线程后端 | 状态 |
| --- | --- | --- |
| `aarch64-apple-darwin` / `x86_64-apple-darwin` | pthread（libSystem） | L1，`platform_ready() == 1` |
| `aarch64-unknown-linux-gnu` / `x86_64-unknown-linux-gnu` | pthread（libc；链接模板含 crt1 + `-lc`） | L2 Linux，`platform_ready() == 1` |
| `x86_64-pc-windows-msvc` | 待定：CreateThread + SRW | 占位，`platform_ready() == 0` |

未落地平台的行为是**显式失败**：`thread_spawn`/`mutex_init` 返回 `-1`，
不存在“看起来能跑、实际没有同步”的空实现。

## 未定义行为（必须自己保证）

- `Mutex`/`Cond`/`WaitGroup`/`Once`/`Thread` 不能按值复制；
- 同一线程重复加锁、未初始化就加锁、`wait` 返回后再 `add`；
- 没有 join/锁/通道建立 happens-before 的并发读写（数据竞争）；
- `main` 返回时未 join 的线程被进程退出终止；
- `fork` 之后继续使用本库的线程原语。

## 测试

```sh
cd libs && ../yh test --filter sync      # 本模块 10 例
SYNC_REPEAT=10 just test-sync-stress     # 并发用例重复跑
just test-libs                           # 全部标准库，O0 + O2
```

Linux/Windows 的线程运行验证在 CI：`.github/workflows/stdlib.yml` 的
`linux-x64` / `linux-arm64` 任务跑 `just test-stdlib-unix`（含并发压力），
`windows-x64` 任务在 `prim.windows.yh` 落地前只跑跨平台核心测试。
