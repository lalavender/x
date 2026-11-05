# ADR-0018：yh 网络与 HTTP 标准库的分层与依赖边界

日期：2026-10-24。状态：**接受，未实施**（设计定稿，M0–M7 待办）。

用户已确认六项决策：首期含服务端、TLS 允许链接系统 OpenSSL、DNS 走纯 yh、
并发模型后置、服务端 `Date` 先补 `time`、补本 ADR。本 ADR 固化其中跨模块、
长期有效的五条边界；实施细节见
[HTTP 标准库设计](../03-design/yh-http标准库设计.md)。

## 背景

仓库此前没有任何网络能力：`libs/sys` 只有文件/目录/进程/内存/时间原语，
`libs/os` 的联合设计明确「不在首期扩展网络、DNS、线程」，`libs/` 无
`net`/`http`，`docs/` 无相关设计。因此 HTTP 不是补一个解析器，而是要先解决
「谁来提供 TCP 与地址」。

同时有三条现成约束互相拉扯：

1. 标准库定位是纯 yh、可自举、零外部依赖（`libs/sys` 在 Linux 走原始
   syscall，Darwin 才走 libSystem）。
2. 现实里没有 TLS 的 HTTP 客户端用途有限，而自研 TLS 不是标准库该承担的。
3. 仓库已实现 `[c].sources`/`[c].objects`/`[c].libs` 与 `[link]`，理论上任何
   C 库都能链进来——包括 libcurl，但那会把「零依赖」直接推翻。

## 备选

1. **只做解析器，TCP 交给应用**：改动最小，但应用得自己写 socket，等于没有
   标准库；且 e2e 无法自测。
2. **三级分层：sys socket → net → http**：每级可独立验收，平台差异收敛在
   sys，应用按需只 import `net`。推荐。
3. **直接绑定 libcurl**：能力最全（HTTP/2、代理、cookie、压缩、TLS 全都有），
   但 `curl_easy_setopt` 是 C 变参、数据面全靠回调、依赖形态不可控，与纯 yh
   定位和零拷贝模型冲突（详见设计 §16.2）。
4. **自研 TLS**：可控但要承担密码学正确性，成本与风险都不该压在标准库首期。

## 提议

- **网络分三级，`net` 是独立公开模块**：`sys` 只放 socket/poll 具名原语与
  平台常量（一次内核调用、返回原始结果或 `-errno`）；`net` 提供
  `Endpoint`/`TcpStream`/`TcpListener`、超时与纯 yh DNS；`http` 提供消息模型、
  解析、客户端与服务端。sockaddr 布局不进任何公开签名。
- **HTTP 核心是 1.1 明文，零外部依赖**；TLS 由**可选**的 `libs/tls`（M6）
  链接系统 OpenSSL 提供，`http` 不 import 它，只依赖 `Io`
  （`read`/`write` 两个函数指针 + `handle`）。明文项目不引入任何 C 依赖。
- **DNS 用纯 yh 实现**（UDP 查询 + `/etc/hosts` + `/etc/resolv.conf`），
  不用 libc `getaddrinfo`；M1–M4 只用字面量地址，M5 补齐。
- **服务端首期只做单进程串行 accept**；`serve_fork` 与 poll 事件循环等并发
  标准库落地后再补，本 ADR 不承诺 fork/线程语义，也不提前把这些语义泄进
  `http` 接口。
- **不使用 libcurl 作为 HTTP 实现**；保留「可选 `libs/curl` 互操作模块」的
  余地，它不得进入 `libs/http` 的依赖图。
- 错误词汇复用 `os.Error`：给 `os.ErrorKind` 增量追加网络成员
  （`error_connection_refused`/`error_connection_reset`/`error_not_connected`/
  `error_timed_out`/`error_address_in_use`/`error_host_unreachable`/
  `error_network_unreachable`），http 只额外定义解析类错误
  （`error_parse`/`error_incomplete`/`error_protocol`/`error_too_large`/
  `error_unsupported`/`error_closed`）。`native_code` 语义不变。

## 后果与权衡

- **收益**：明文 HTTP 保持零依赖与可自举；`net` 可被 DNS、UDP、工具复用；
  TLS 成为「用才付出」的可选依赖；错误模型全库一致；解析器可用内存源离线
  测试（不需要 socket，也不需要网络）。
- **代价**：TLS 依赖宿主 OpenSSL（Darwin 系统库是 LibreSSL、Linux 多为
  OpenSSL 3），两平台必须各自验证；串行 accept 有队头阻塞，只适合本地工具、
  示例与低并发内网服务，README 必须写明；头字段借用读缓冲，视图有效期到
  下一次读取，误用是主要使用风险。
- **不做的事**：HTTP/2、HTTP/3、ALPN、gzip、代理、WebSocket、cookie jar、
  客户端证书与会话恢复、路由框架。`docs/yh.g4` 不改，本 ADR 不引入语法。
- **与现有 ADR 的关系**：延续 [ADR-0015](0015-yh-os与sys标准库分层.md) 的
  「sys 原语 / 应用接口分层」；TLS 的链接方式遵循
  [ADR-0016](0016-yh项目静态库分组链接.md)（库文件与系统库由项目声明，不写
  rpath）；不改变 [ADR-0014](0014-yh采用LLVM作为正式代码生成后端.md) 的后端
  路线。

## 验证与关联

设计、12 条解析规则、默认限制、文件布局、M0–M7 分期与测试矩阵见
[HTTP 标准库设计](../03-design/yh-http标准库设计.md)。关闭本 ADR
需要：M0 负例 errno 映射、M1 环回 echo、M2 与 Python 参考字节逐字节一致、
M3/M4 双向 e2e、M5 hosts/resolv.conf、M6 五类 TLS 用例在 Linux 与 Darwin
各跑一遍，以及 `make test` / `make selfhost-native` 全绿。当前状态是**未实施**：
`libs/net`、`libs/http`、`libs/tls` 均未创建，`libs/project.toml` 未注册。
