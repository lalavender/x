# yh 多线程标准库设计

修改时间：2026-11-11

状态：**Darwin 与 Linux 已实现**（pthread），Windows 仍是显式失败的占位实现
（L2）。目标是把多线程做成**纯标准库能力**：不改语言、不改语法、不改
AST/检查器/降级。L0 探针与库内测试已在 Darwin 通过（§0.1、§7.1），
Linux 侧已完成交叉编译与符号核对（§5.5）。

背景：`tools/llvm-sdk.py` 从构建机 GCC 的 `collect2` 参数生成 ELF 链接模板，
其中固定包含 crt1/crti/crtn 与 `-lc`，所以 Linux 目标的用户程序本来就链接
libc；`pthread_*` 可直接使用（glibc ≥ 2.34 已合并 libpthread，musl 同样在
libc 内）。

范围：`libs/sync` 的公开面与实现、平台原语收敛、线程资源与内存模型、
验证方式。不在本文件：编译器自身并行化、LSP/工具链。
相关取舍见 [ADR 目录](../adr/)。

## 0. 结论摘要

| # | 决策 | 理由 |
| --- | --- | --- |
| S1 | 能力全部放 `libs/sync`：**不新增 `go`/`shared`/`lock`/`chan` 任何语法** | yh 无泛型/闭包/方法，语法糖的收益抵不上检查器+降级+缓存的改造风险 |
| S2 | 用户线程入口固定为 `fn(*void) void`（yh ABI），参数自行装箱 | 统一签名消灭「按调用点合成 thunk」，也不需要泛型 |
| S3 | 线程 = OS 线程；`Thread` 句柄支持 join/detach | 与 V 的 `spawn` 底层一致；无 GC，OS 线程最容易验证 |
| S4 | `Mutex`/`Cond`/`WaitGroup`/`Once`/`Chan` 用**不透明定长块** + 平台原语 | 一个结构体覆盖三种平台；不暴露平台类型 |
| S5 | 通道 = 字节容器 + 状态码（`chan_init(elem_size, cap)`） | 无泛型；状态码统一为 `CHAN_*` 常量 |
| S6 | 平台：Darwin / Linux 都用 libc 的 pthread（纯 yh）；Windows 待接 kernel32 | 三平台都零语言改动；Linux 的 libc 由链接模板保证 |
| S7 | 原子操作**不进首版**：核心同步全部用 Mutex/Cond 实现 | 不需要 IR 原子指令，也不需要运行时原子帮助函数 |
| S8 | 不做编译期 `shared` 访问检查 | 那要改布局、检查器与所有退出边；与「纯库」目标冲突（见 §10） |
| S9 | 线程库只用现有语法 → **当前种子就能编译**，不需要等新编译器 | 无自举延迟，也不需要为新语法滚种子 |

### 0.1 L0 探针结论（2026-11-11，Darwin/arm64）

用仓库根 `./yh`（0.0.14）编译并运行，三个探针全部通过，**未改编译器**：

| 探针 | 内容 | 实际输出 |
| --- | --- | --- |
| `pthread.yh` | `@[extern]` 声明 `pthread_create/join`，yh 侧定义 C ABI 入口，传 `&job` | `7`（期望 7） |
| `mutex.yh` | `struct Mutex { words [8]u64 }` + pthread mutex，2 线程 × 100000 次 | `200000`（精确，无丢失更新） |
| `dispatch.yh` | 通用跳板：C 入口收 `*void`，内部调 `*fn(*void) void` | `41`（期望 41） |

探针源码在 `tmp/sync-probe/`（不入门禁）；L1 已把它们升级为 `libs/sync/*.test.yh`（10 例）。
这一条把「标准库方案」的最大不确定性（`@[extern]` + C 函数指针 + 不透明块）
提前消除了。

## 1. 为什么做成库而不是语法

参照 V 官方 `doc/docs.md`（2026-11 抓取）§Concurrency / §Channels /
§Shared Objects / §Atomics / §Race Detector：

| V 机制 | V 的实现依赖 | yh 的库层等价物 | 取舍 |
| --- | --- | --- | --- |
| `spawn f(a, b)` | 语法 + 泛型线程句柄 + 线程池 | `sync.thread_spawn(&t, entry, arg)`，yh 用户自己装箱 | 采用；少一层语法糖，换来零编译器改动 |
| `h.wait()` / 返回值 | 泛型 `thread T` | `sync.thread_join(&t)`，结果写回 arg 结构 | 采用；yh 无泛型，返回值只能走出参 |
| `go f()`（轻量线程） | V 运行时调度器 | 无 | 不做：需要抢占式调度与栈切换 |
| `shared x` + `lock`/`rlock` | 编译器改布局 + 检查器 | `sync.Mutex` / `sync.RwLock`（后续） | **不做**：见 §10，与「纯库」冲突 |
| `chan T{}` / `<-` / `select` | 泛型 + 专属语法 | `sync.Chan` 字节容器 + 状态码 | 首版不做 `select`；通道 API 见 §3.4 |
| `sync.Mutex/WaitGroup/Once` | 标准库 | `sync.*` 同名对应 | 采用 |
| 原子操作（C 包装） | 外部 C 头 | 暂不提供 | 后置；核心同步不需要 |
| `-race`（TSan） | clang TSan 运行时 | 后续预研 | 不阻塞主计划 |

结论：V 的**库层**能力（Mutex/WaitGroup/Chan/句柄）全部保留；V 的**语法层**
能力（`spawn` 糖、`shared` 检查、`chan T`）不引入。代价是调用点更长，
收益是编译器零侵入、当前种子可编译、平台差异收敛在库内。

## 2. 语言现状约束

1. 无泛型/接口/方法/闭包 → 入口签名统一 `fn(*void) void`；类型化封装只能手写。
2. 无 `defer` → 锁必须显式配对；库内部也要自己保证每条失败路径解锁。
3. 无 GC → 派发块、通道缓冲、线程句柄的生命周期要写明「谁分配、谁释放」。
4. 已有的 C 互操作能力足够（均已在本仓库验证）：
   `@[extern] fn` 声明与定义、C 函数指针类型 `@[extern] fn(...)`、
   函数名作实参（`c_apply(yh_increment, v)`）、`&函数名`、指针转换。
5. 无 `align` 语法 → 用 `[8]u64` 之类的数组字段把不透明块强制成 8 字节对齐。
6. 全局对象只有静态初始化，无模块 init → 不存在初始化顺序竞态。
7. `Mutex`/`Chan` 这类含句柄的结构体**按值复制**会复制互斥块/句柄。
   没有编译器检查，只能靠文档 + 运行时哨兵（尽力而为）。

## 3. 公开 API

命名与错误风格沿用 `libs`：snake_case、`out` 出参、`0 = 成功`、失败返回负数。

### 3.1 `Thread`

```yh
pub struct Thread {
    handle u64      // 平台句柄：pthread_t（Darwin/Linux）/ HANDLE（Windows）
    state  int      // 0 空句柄、1 已创建、2 已汇合、3 已分离
}

pub fn thread_spawn(out *Thread, entry *fn(*void) void, arg *void) int
pub fn thread_spawn_detached(entry *fn(*void) void, arg *void) int
pub fn thread_join(t *Thread) int      // 0 成功；-1 空句柄/已汇合/已分离/平台失败
pub fn thread_detach(t *Thread) int
pub fn thread_id() u64                 // 调试/测试；不承诺跨平台数值
```

- `entry` 是普通 yh 函数：参数只有一个 `*void`，返回值 void。
  需要多参数就自己定义结构体，把指针传进来（V 的 `spawn f(a,b)` 由用户展开）。
- 结果回传：写进 `arg` 指向的结构体，`thread_join` 返回后可见（happens-before
  由 join 保证）。
- `thread_spawn` 内部申请派发块（`{entry, arg}`），由线程入口在结束时释放；
  spawn 失败时库自己释放并返回 -1。
- `Thread` 必须按指针传递；`thread_join` 成功后把 `state` 置 2，重复 join 返回 -1。
- 栈大小用平台默认（Darwin 512 KiB、Windows 1 MiB、Linux 8 MiB 虚拟）；
  需要自定义栈时后续加 `thread_spawn_with_stack`（不阻塞首版）。

### 3.2 `Mutex` / `Cond`

```yh
pub struct Mutex { words [8]u64 }   // 64 字节、8 字节对齐：覆盖三种平台
pub struct Cond  { words [6]u64 }   // 48 字节：pthread_cond_t 恰好 48

pub fn mutex_init(m *Mutex) int
pub fn mutex_lock(m *Mutex) void
pub fn mutex_unlock(m *Mutex) void
pub fn mutex_try_lock(m *Mutex) int   // 0 成功、1 未获得（STATUS_BUSY）、-1 参数非法
pub fn mutex_destroy(m *Mutex) void

pub fn cond_init(c *Cond) int
pub fn cond_wait(c *Cond, m *Mutex) void
pub fn cond_signal(c *Cond) void
pub fn cond_broadcast(c *Cond) void
pub fn cond_destroy(c *Cond) void
```

- 不可重入（与 pthread 默认互斥一致）。文档写明「同线程重复 lock 是未定义行为」。
- `cond_wait` 必须持有对应 `Mutex`；返回时已重新持有。
- `words` 是**不透明存储**，用户不要读写。

### 3.3 `WaitGroup` / `Once`

```yh
pub struct WaitGroup { mutex Mutex; cond Cond; count i64 }

pub fn waitgroup_init(wg *WaitGroup) int
pub fn waitgroup_add(wg *WaitGroup, delta int) int   // 0 成功；-1 计数会变负
pub fn waitgroup_done(wg *WaitGroup) int
pub fn waitgroup_wait(wg *WaitGroup) void

pub struct Once { mutex Mutex; cond Cond; state int }
pub fn once_init(o *Once) int
pub fn once_call(o *Once, f *fn(*void) void, arg *void) void
```

- `add` 必须在 spawn 之前；`wait` 之后再加计数是未定义行为（与 Go/V 一致）。
- `once_call` 只执行一次，其余调用者阻塞到完成；`f` 内部抛错/提前返回不影响状态。

### 3.4 `Chan`（字节通道）

```yh
pub struct Chan {
    mutex    Mutex
    cond     Cond
    buffer   *u8
    elem_size u64
    cap      int
    head     u64
    count    u64
    closed   int
}

pub const CHAN_OK int = 0          // 成功
pub const CHAN_CLOSED int = 1      // 已关闭（send）或已关闭且空（recv）
pub const CHAN_NOT_READY int = 2   // 仅 try_*：当下无法完成
pub const CHAN_INVALID int = -1    // 参数/状态无效

pub fn chan_init(ch *Chan, elem_size u64, cap int) int
pub fn chan_release(ch *Chan) void
pub fn chan_send(ch *Chan, value *void) int          // 0/1/-1
pub fn chan_recv(ch *Chan, out *void) int            // 0/1/-1
pub fn chan_try_send(ch *Chan, value *void) int      // 0/1/2/-1
pub fn chan_try_recv(ch *Chan, out *void) int
pub fn chan_close(ch *Chan) int
pub fn chan_len(ch *Chan) u64
pub fn chan_capacity(ch *Chan) int
pub fn chan_closed(ch *Chan) int
```

- 发送复制 `elem_size` 字节；缓冲由库在 `chan_init` 分配、`chan_release` 释放。
- 无缓冲（`cap == 0`）是同步交接：发送方阻塞到有接收方。
- 关闭后：剩余缓冲仍可 `recv`，空后返回 1；`send` 返回 1；重复 `close` 返回 1。
- `Chan` 不可按值复制；`chan_init` 写哨兵，`chan_release` 清哨兵。
- 元素宽度 0、`cap * elem_size` 溢出、分配失败都返回 -1。

### 3.5 原子操作（后置）

首版不提供。`WaitGroup`/`Chan`/`Mutex` 都不需要语言级原子。
需要无锁算法时再加 `atomic_*`（Windows 用 Interlocked，Darwin 用 OSAtomic 或
编译器运行时帮助函数，Linux 用运行时帮助函数），届时单独评估。

## 4. 内存模型

- **happens-before**（只有这些）：
  1. `thread_spawn` 之前的所有写 → 新线程入口；
  2. 线程入口返回 → `thread_join` 返回；
  3. `mutex_unlock` → 后续成功的 `mutex_lock`；
  4. 持锁下的 `cond_signal/broadcast` → 被唤醒并重新获得锁的 `cond_wait` 返回；
  5. `chan_send` → 对应 `chan_recv` 返回；`chan_close` → 观察到关闭的 `recv`。
- 数据竞争（无上述边的并发读写）= **未定义行为**，不是「结果不确定」。
- 通过 `*void` 传入的聚合、指针、切片：参数本身按值传递，**元素/后备存储共享**。
  join 之前的读写在竞争意义下都不安全；要把结果读回来就 join。
- `memory.alloc` 在 Linux 是每次 mmap/munmap、在 Darwin/Windows 是 libc 堆，
  都是线程安全的；这个不变量写进 `memory` 文档。
- 不提供隐式顺序保证：spawn 之后不 join 就读共享数据，等于竞争。

## 5. 实现

### 5.1 分层与文件

| 文件 | 内容 | 平台 |
| --- | --- | --- |
| `libs/sync/api.yh` | 类型、公开函数注释、状态码常量 | 全平台 |
| `libs/sync/thread.yh` | `Thread` 的公共逻辑（spawn 派发块、join 状态机） | 全平台 |
| `libs/sync/waitgroup.yh` / `once.yh` / `chan.yh` | 基于 `Mutex`/`Cond` 的公共实现 | 全平台 |
| `libs/sync/prim.darwin.yh` | pthread 线程/互斥/条件原语 | Darwin |
| `libs/sync/prim.windows.yh` | `CreateThread` / SRW / 条件变量 | Windows |
| `libs/sync/prim.linux.yh` | pthread（libc）线程/互斥/条件原语 | Linux |
| `libs/sync/doc.yh` / `README.md` | API 契约、误用与未定义行为 | — |
| `libs/sync/*.test.yh` | 库内 `test` 块 | — |

平台文件按仓库既有规则生效（`*.darwin.yh` / `*.windows.yh` / `*.linux.yh`），
同名函数在三个文件里各实现一次，公共层只写一份。

### 5.2 通用跳板（已验证）

```yh
// Dispatch：库申请的派发块。线程入口结束时由 tramp 释放。
struct Dispatch {
    entry *fn(*void) void
    arg   *void
}

// tramp：C ABI 线程入口。只做三件事：取派发块、调用户函数、释放。
@[extern]
fn tramp(arg *void) *void {
    let d *Dispatch = arg.to_type(*Dispatch)
    let fp *fn(*void) void = d.entry
    (*fp)(d.arg)
    memory.release(arg)
    return 0.to_type(*void)
}
```

`pthread_create(&t, 0, tramp, &d)` / `CreateThread(..., tramp, &d, ...)`。
因为入口签名固定，**不需要任何按调用点生成的代码**，也不需要泛型。

### 5.3 Darwin（纯 yh）

| 能力 | 声明 | 备注 |
| --- | --- | --- |
| 创建 | `pthread_create(*u64, *void, @[extern] fn(*void) *void, *void) int` | attr 传 0（默认栈） |
| 汇合/分离 | `pthread_join(u64, **void) int` / `pthread_detach(u64) int` | |
| id | `pthread_self() u64` | 返回指针，按 8 字节整数收 |
| 互斥 | `pthread_mutex_init/lock/unlock/trylock/destroy` | 块 64 B |
| 条件 | `pthread_cond_init/wait/signal/broadcast/destroy` | 块 48 B |

`pthread_mutex_t` / `pthread_cond_t` 的实际尺寸由 L0 的 `sizeof` 探针锁定
（当前按 64/48 预留，`sync.test` 里放一条尺寸断言）。

### 5.4 Windows（纯 yh）

| 能力 | 声明 |
| --- | --- |
| 创建 | `CreateThread(*void, u64, @[extern] fn(*void) u32, *void, u32, *u32) *void` |
| 汇合 | `WaitForSingleObject(*void, u32) u32` + `CloseHandle(*void) int` |
| id | `GetCurrentThreadId() u32` |
| 互斥 | `AcquireSRWLockExclusive/ReleaseSRWLockExclusive/TryAcquireSRWLockExclusive` |
| 条件 | `SleepConditionVariableSRW / WakeConditionVariable / WakeAllConditionVariable` |

- Windows 入口返回 `u32`（`DWORD`），所以 `prim.windows.yh` 的 `tramp` 返回 `u32`。
- `SRWLOCK` / `CONDITION_VARIABLE` 零初始化即有效，`mutex_init`/`cond_init` 清零即可。
- 需要往 `vendor/windows-sdk` 的 KERNEL32 导入清单补
  `CreateThread/GetCurrentThreadId/AcquireSRWLockExclusive/...` 等符号，
  并同步 `def_sha256`（`tests/selfhost/llvm-windows-sdk.py` 会校验）。

### 5.5 Linux（libc pthread，已实现）

**结论**：Linux 目标本来就链接 libc，直接使用 `pthread_*`，不需要 clone 垫片。
证据链：

1. `tools/llvm-sdk.py` 用固定 GCC 的 `-###` 输出生成 ELF 链接模板，
   `collect2` 参数里含 `crt1.o`/`crti.o`/`crtn.o` 与 `-lc`，模板编译进桥。
2. `libs/sync/prim.linux.yh` 与 Darwin 同形：`pthread_create/join/detach/self`
   与 `pthread_mutex_*` / `pthread_cond_*`；`tramp` 仍是 C ABI 跳板。
3. 交叉编译到 `aarch64-unknown-linux-gnu` 的 `.s` 里可见
   `bl pthread_create` / `bl pthread_join` / `b pthread_mutex_lock` 等调用。

尺寸：glibc x86_64 的 `pthread_mutex_t` 是 40 B、aarch64 是 48 B，
`pthread_cond_t` 都是 48 B；`Mutex.words` 64 B、`Cond.words` 48 B 覆盖。
`pthread_t` 是 `unsigned long`（8 B），与 `Thread.handle u64` 一致。

版本前提：glibc ≥ 2.34 或 musl（pthread 在 libc 内）。更老的 glibc 需要
在链接模板补 `-lpthread`；本库不做平台版本探测，链接失败会明确报未定义符号。

**运行时验证**：本机（Darwin）无法执行 Linux ELF，也没有容器；已完成的是
`yh check --target` 与 `.s` 符号核对。Linux 容器门里的线程运行用例列为
L2 剩余项（§8），需要在 Linux/aarch64 环境执行 `just test-llvm-linux-arm64`
或新增一条用 libs 的工程用例。

### 5.6 与编译器的边界

主线（Darwin/Linux pthread）**零编译器改动**：不动语法/词法/AST/检查器/
降级/IR/序列化/缓存/后端，也不需要更新种子。若将来出现无 libc 的目标，
再按「运行时移植层」单独立项（不改变本库的公开面）。

## 6. 资源与失败模式

- `thread_spawn` 失败（`EAGAIN`/内存不足）：释放派发块，返回 -1；调用方决定重试/退出。
- `thread_join` 不传 `out` 结果（入口无返回值）；结果一律走 arg 结构体。
- detach 后 `thread_join` 返回 -1；重复 join 返回 -1（不可逆状态）。
- join 之前调用方必须保证 `arg` 指向的对象仍然有效（栈对象要等 join 后再离开作用域）。
- `main` 返回 = 进程退出，未 join 的线程被终止；不跑清理。
- 守卫页/栈溢出、野指针 → 进程被信号终止（不做语言级处理）。
- `go`/`shared` 不存在，因此没有「先 go 再 fork」这类语言级禁忌；
  但 `fork` 之后再用 pthread 仍然是未定义行为（文档写明）。
- 复制 `Mutex`/`Cond`/`WaitGroup`/`Once`/`Chan`/`Thread` 都是未定义行为
  （互斥块、计数、句柄都会被复制）；`chan_init` 的哨兵只做尽力防御。

## 7. 验收与测试

### 7.1 库内测试（`libs/sync/*.test.yh`，已实现 10 例）

| 用例 | 断言 |
| --- | --- |
| 不透明块尺寸与状态码 | `sizeof(Mutex)==64`、`sizeof(Cond)==48`、`sizeof(Thread)==16` |
| 空指针参数被拒绝 | 所有带指针参数的入口返回 `STATUS_INVALID` |
| 互斥计数无丢失更新 | 2 线程 × 10000，精确 20000 |
| 等待组批量汇合 | 4 线程各自写槽位，wait 后 4 个槽位都可见 |
| Once 只执行一次 | 8 线程并发，执行体恰好 1 次 |
| join 建立可见性 | 入口的写在 join 后可见 |
| 线程 id 互不相同 | 两个存活线程 id 非 0 且不同 |
| 分离线程仍能完成工作 | detached 线程用 WaitGroup 报告完成 |
| 句柄状态机 | 已用句柄不能重复 spawn、重复 join/detach 失败 |
| 互斥 try_lock | 同线程第二次 try_lock 返回 `STATUS_BUSY` |

`platform_ready() == 0` 的平台上，需要线程的用例直接返回（不失败），
尺寸/状态码用例在所有平台都跑。

### 7.2 为什么没有 `tests/yh-run` 语料

`tests/yh-run` 的单文件编译不接标准库（没有 `--stdlib` 参数，`import sync`
解析不到符号），所以并发行为测试不能放在那里。L1 的全部行为用例都在
`libs/sync/*.test.yh`，由 `just test`（O0）与 `just test-libs`（O0 + O2）
执行；这也顺带覆盖了「库在真实项目里可编译」的路径（`tmp/sync-probe/proj`
做过一次带 `[dependencies]` 的端到端验证，结果 200000）。

### 7.3 方法与门槛

- `just test-libs`（O0 + O2 两遍）必须全绿；同步用例已 shell 循环 20 次
  （`cd libs && ../yh test --filter sync`，0 失败）。
- `just test` 里的 `yh test`（libs）同样会执行这些用例。
- Linux 运行门：`.github/workflows/stdlib.yml` 的 `linux-x64` / `linux-arm64`
  在原生 runner 上执行 `just test-stdlib-unix`（`test-libs` + 10 次
  `--filter sync` 压力）；Windows 同工作流的 `windows-x64` 任务在
  `prim.windows.yh` 落地前只跑核心测试（并发用例自动跳过）。
- Windows：`test-windows-corpus`（交叉编译 + 清单）+ 真机 `run-windows-corpus`。
- 基准（记录、不做门禁）：mutex lock/unlock、chan send/recv、spawn+join
  ns/op，与同机 C/pthread 对照；噪声校准沿用
  [性能回归判定与噪声校准](yh-性能回归判定与噪声校准.md)。

## 8. 路线图

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| L0 | 探针收尾：cond 尺寸/行为、Linux 链接与 pthread 可用性、Windows 导入清单 | 三条结论回填本文 §5 |
| L1 | Darwin：`Thread` + `Mutex` + `Cond` + `WaitGroup` + `Once` + 测试 | **已交付**：10 例 O0/O2 全过，20 次重复 0 失败 |
| L2 | **Linux 已接 pthread**；Windows 补 KERNEL32 导入与 `prim.windows.yh` | Linux 容器运行门（待环境）+ Windows 编译门 |
| L3 | `Chan`（有/无缓冲、close、try_*） | 库内测试 + 压力测试 |
| L4 | 可选：`RwLock`、`Semaphore`、`Pool`、原子、TSan | 按需求排期 |

## 9. 风险

| # | 风险 | 缓解 |
| --- | --- | --- |
| R1 | Linux 运行期未在本机验证（无容器） | 交叉编译 + 符号核对已完成；容器门执行列为 L2 剩余项 |
| R2 | 不透明块尺寸/对齐靠猜 | L0 用 C `sizeof`/`offsetof` 实测 + 库内尺寸断言 |
| R3 | 无编译器 `shared` 检查，用户漏锁 | API 文档 + 竞争=UB 的显式说明 + 后续 TSan；不假装安全 |
| R4 | 复制含互斥块的结构体 | 文档 + 哨兵；不提供隐式拷贝保护 |
| R5 | Windows 导入表缺失符号 | L0 对照 manifest 补齐并跑 `test-windows-sdk` |
| R6 | 一任务一线程，短任务扩展性差 | 文档写明；L4 的 `Pool`（库层复用）后再优化 |
| R7 | 通道字节宽度写错 | 运行时 `elem_size` 校验 + 文档；等泛型再做类型化封装 |

## 10. 明确不做

- `go`/`spawn` 语法、`chan T` 类型、`<-`/`select` 语法；
- 编译期 `shared`/`lock` 检查（要改布局与检查器，见 §1 对照表）；
- green thread / M:N 调度、GC、线程取消、优先级、语言级 TLS；
- 把 `string`/`list`/`json` 改成线程安全（只保证分配器线程安全）；
- 编译器自身并行化。

**关于 `shared` 的立场**：它不是「多线程支持」的必要条件，而是「编译期防错」
的糖。yh 当前没有借用检查器，单为 `shared` 引入布局包装、访问性检查、
所有退出边的加解锁配对，成本远高于收益。若将来确实需要，按 ADR 单独立项，
不在本方案内。

## 11. 待确认

1. **Linux 是否链 libc**（T0.3）：决定路线 A（纯 pthread、零编译器改动）
   还是路线 B（clone 垫片）。
2. **Windows 导入清单**：`CreateThread`/SRW/条件变量是否全部能从 KERNEL32
   导入库取到（L0 验证后补 `vendor/windows-sdk`）。
3. **Darwin 结构体尺寸**：`pthread_mutex_t`/`pthread_cond_t` 的 `sizeof`
   （L0 实测；当前按 64/48 预留）。
