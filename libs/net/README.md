# net

yh 标准库的网络模块：地址文本解析 + TCP 连接/监听。设计见
[`docs/03-design/yh-http标准库设计.md`](../../docs/03-design/yh-http标准库设计.md)，
分期见同文件 §14（NET1 已交付）。完整 API 见 [doc.yh](doc.yh)。

- 只做「地址 + TCP」：不含 DNS（NET5）与 TLS（NET6，由 `libs/tls` 接入 http）。
- 字面量地址优先：`parse_endpoint` 不查询 DNS，只解析 `a.b.c.d[:port]` 与 `[v6][:port]`。
- 错误统一用 `os.Error`；`os.ErrorKind` 的网络成员见表末。
- 句柄是薄结构（fd + closed），关闭后 `fd = -1`，重复关闭幂等。

## 模型

```yh
pub enum Family { family_inet4 family_inet6 }
pub struct Endpoint { family Family; address [16]u8; port u16 }  // port 主机序
pub struct TcpStream { fd int; closed bool }
pub struct TcpListener { fd int; closed bool }
```

`Endpoint.address` 是 16 字节网络序地址，IPv4 只用前 4 字节、其余为 0。
`status` 只表达 net 自己发现的参数/地址问题；内核失败一律在 `os.Error` 里。

## 快速开始

```yh
import net;
import os;

pub fn main() int {
    let listening net.ListenerResult = net.listen(
        net.endpoint_ipv4(127, 0, 0, 1, 0), 8);
    if (listening.error.kind != os.error_none) { return 1; }

    // 端口 0 由内核分配，再读回实际端口。
    let local net.EndpointResult = net.listener_local(&listening.listener);
    if (local.status != net.status_ok) { return 2; }

    let dialed net.StreamResult = net.dial(local.value, 1000);
    if (dialed.error.kind != os.error_none) { return 3; }
    let client net.TcpStream = dialed.stream;

    let accepted net.AcceptResult = net.accept(&listening.listener, 1000);
    if (accepted.error.kind != os.error_none) { return 4; }
    let server net.TcpStream = accepted.stream;

    let message [4]u8;
    message[0] = 80;
    message[1] = 73;
    message[2] = 78;
    message[3] = 71;
    net.write_all(&client, message[0..4]);

    let incoming [16]u8;
    let got os.IoResult = net.read_some(&server, incoming[0..16]);
    if (got.count != 4) { return 5; }

    net.close_stream(&client);
    net.close_stream(&server);
    net.close_listener(&listening.listener);
    return 0;
}
```

## 语义要点

- `accept` 的 `timeout_ms`：负数无限等待，0 只探测；超时表现为
  `status == status_ok` + `error.kind == error_timed_out` + `stream.fd == -1`，
  不是 `status` 错误。
- `read_some` 返回 `count == 0` 且无错误表示对端有序关闭（RFC 语义的 EOF）。
- `write_some` 允许短写；整段写入用 `write_all`，失败时 `count` 保留进度。
- `shutdown_write` 只半关闭：对端读到 EOF，本端仍可继续读。
- 超时通过 `SO_RCVTIMEO`/`SO_SNDTIMEO` 落地，内核以 `EAGAIN` 返回；net 把它
  归类为 `os.error_timed_out`（os 层的普通非阻塞 `EAGAIN` 仍是 `error_other`）。

## 平台差异（2026-10-24 实测）

| 能力 | Linux | Darwin |
| --- | --- | --- |
| connect 超时 | ✅ 非阻塞 connect + `poll` + `SO_ERROR` | ❌ 只能阻塞 connect（内核 TCP 超时） |
| 读写超时 | ✅ `SO_RCVTIMEO`/`SO_SNDTIMEO` | ✅ 同左 |
| SIGPIPE 抑制 | `send(MSG_NOSIGNAL)` | `setsockopt(SO_NOSIGPIPE)` |
| 新 fd 的 CLOEXEC | ✅ `accept4` 带 `O_CLOEXEC` | ❌ `accept` 无 flags |

Darwin 的差异来自语言边界：`fcntl`/`ioctl` 是 C 变参，yh 的 `@[extern]` 只能
声明定参，无法切换 `O_NONBLOCK`。这不是实现取舍，是当前 ABI 的硬约束；等 C
变参进入语言后再补齐。

## 错误分类

`os.ErrorKind` 为网络新增了这些成员（追加在末尾，既有取值不变）：

| 成员 | 来源 |
| --- | --- |
| `error_connection_refused` | `ECONNREFUSED` |
| `error_connection_reset` | `ECONNRESET`、`EPIPE` |
| `error_not_connected` | `ENOTCONN`、`ECONNABORTED`，以及句柄已关闭 |
| `error_timed_out` | `ETIMEDOUT`、套接字读写超时的 `EAGAIN`、poll 超时 |
| `error_address_in_use` | `EADDRINUSE` |
| `error_host_unreachable` | `EHOSTUNREACH` |
| `error_network_unreachable` | `ENETUNREACH` |

## 验收

- 内建测试：`cd libs && ../yh test net`（地址解析/格式化矩阵，不联网）。
- 环回闭环：`tests/modules/projects/netecho`（登记为
  `net1-net-tcp-loopback`），覆盖端口 0 回读、accept 超时、双向收发、
  半关闭 EOF 与连接被拒。
- 两个用例都只用 `127.0.0.1`，不访问外部主机、不查询 DNS。
