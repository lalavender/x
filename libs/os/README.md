# os 标准库：应用级 OS 操作

日期：2026-10-21。状态：**OS0–OS6 完成**（Linux 新文件/目录/进程 API；
环境查询跨平台；旧接口兼容保留）。

- 完整 API 清单与契约：[doc.yh](doc.yh)
- 分层与交付顺序：[联合设计](../../docs/03-design/yh-os与sys标准库设计.md)、
  [联合实施方案](../../docs/02-plan/yh-os与sys标准库实施方案.md)
- 底层原语：[sys 标准库](../sys/README.md)

## 加载

```sh
# 1. 显式项目依赖（推荐给编译器/工具链）
#    project.toml:
#      [dependencies]
#      yh_libs = { path = "../libs" }
#    main.yh:
#      import yh_libs.os as os;

# 2. 显式 YH_STDLIB
YH_STDLIB=$PWD/libs ./yh run

# 3. 默认发现（仓库根 yh + libs/，或安装前缀 share/yh/libs）
./yh run
```

## 错误与打开选项

```yh
import os;

let options os.OpenOptions = os.write_options();
options.truncate = true;
let opened os.FdResult = os.open_path("/tmp/yh-os-demo", options);
if (opened.fd < 0 || opened.error.kind != os.error_none) {
    // opened.error.kind: not_found/already_exists/permission_denied/...
    return 1;
}
os.close_file(opened.fd);
```

- `Error.kind` 是稳定分类；`native_code` 是目标平台正错误号。
- 成功时 `kind = os.error_none`，`native_code = 0`；不能只看 native_code。
- `read_options()`：只读、不创建、不截断，mode 0666。
- `write_options()`：只写、创建、不截断，mode 0666。
- `exclusive` 只能与 `create` 一起用；只读 + truncate/append 返回
  `error_invalid_argument`。
- 新 open 默认 `O_CLOEXEC`；成功 fd 所有权归调用方。

## 文件读写

```yh
import os;

let opened os.FdResult = os.open_path("/tmp/yh-os-demo",
    os.write_options());
if (opened.fd >= 0) {
    let data [4]u8 = [65, 66, 67, 10];
    let written os.IoResult = os.write_some(opened.fd, data[0..4]);
    if (written.count != 4 || written.error.kind != os.error_none) {
        // 短写/中断/其他错误
    }
    os.close_file(opened.fd);
}

let read_opened os.FdResult = os.open_path("/tmp/yh-os-demo",
    os.read_options());
if (read_opened.fd >= 0) {
    let buffer [16]u8;
    let read os.IoResult = os.read_some(read_opened.fd, buffer[0..16]);
    // read.count == 4；再次读取 count == 0 表示 EOF
    os.close_file(read_opened.fd);
}
```

- `read_some`/`write_some` 只执行一次，允许短读写；`EINTR` 返回
  `error_interrupted`。
- 需要循环写满并保留进度时用 `io.write_all_result`。
- `close_file` 只调用一次；失败不重试，fd 可能已释放。

其他文件 API：

```yh
os.make_dir("/tmp/yh-dir", 493);            // 0755
os.rename_path("/tmp/yh-a", "/tmp/yh-b");
os.remove_path("/tmp/yh-b");
os.remove_dir_path("/tmp/yh-dir");
```

## 目录流式读取

```yh
import os;

let buffer [256]u8;
let opened os.DirReaderResult = os.open_dir(".", buffer[0..256]);
if (opened.reader.active == 1 && opened.error.kind == os.error_none) {
    for 1 == 1 {
        let item os.DirEntryResult = os.next_entry(&opened.reader);
        if (item.status == os.dir_entry_end) {
            break;
        }
        if (item.status == os.dir_entry_error) {
            break;
        }
        // item.entry.name 借用 buffer，只保证到下一次 next_entry/close_dir
        let name *char = item.entry.name.to_type(*char);
        let length int = item.entry.name_len.to_type(int);
        // io.write_all(1, name, length);
    }
    os.close_dir(&opened.reader);
}
```

- `next_entry` 跳过 `.`/`..`，顺序不保证。
- `DT_UNKNOWN` 保留 `os.dir_unknown`，不得当作普通文件。
- `close_dir` 重复调用幂等；关闭后读取返回 `error_invalid_argument`。

当前目录：

```yh
let cwd [256]u8;
let got os.IoResult = os.get_cwd(cwd[0..256]);
// got.count 不含结尾 NUL；空间不足 error_invalid_argument
os.change_dir("/tmp");
```

## 环境查询

```yh
module main;
import os;

pub fn main(argc int, argv **char, envp **char) int {
    let value os.EnvResult = os.get_env(envp, "PATH");
    if (value.error.kind != os.error_none) {
        return 1;
    }
    if (value.found == true) {
        // value.value 借用 envp，可能是空串
    }
    return 0;
}
```

- 名字不能为空或包含 `=`；按完整键匹配，重复键取首项。
- 缺失返回 `found = false` 且无错误；非法参数返回
  `error_invalid_argument`（native_code 0）。

## 进程

```yh
module main;
import os;

pub fn main(argc int, argv **char, envp **char) int {
    if (argc > 1) {
        os.exit_now(7); // 子模式
    }
    let child_argv [3]*char = [argv[0], "child", 0];
    let spawned os.PidResult = os.spawn(argv[0], &child_argv[0], envp);
    if (spawned.pid <= 0) {
        return spawned.error.kind.to_type(int);
    }
    let waited os.WaitResult = os.wait(spawned.pid);
    if (waited.state == os.wait_exited && waited.exit_code == 7) {
        return 0;
    }
    return 1;
}
```

- `spawn` 使用精确路径，不搜索 PATH、不经过 shell；exec 失败会通过
  close-on-exec 错误管道返回显式错误并回收失败子进程。
- `wait` 遇 EINTR 内部重试；正常退出码与信号号分开。
- `exit_now` 立即 exit_group，不做语言清理。

## 平台范围

| API 组 | Linux | Darwin |
| --- | --- | --- |
| 结果模型、OpenOptions | ✅ | ✅ |
| 环境查询 | ✅ | ✅ |
| 新文件 API | ✅ | 仅 `write_once` 兼容入口 |
| 目录/cwd | ✅ | ❌（OS8） |
| 进程 | ✅ | ❌（OS8） |
| `sleep_us` | nanosleep | usleep |

Darwin 新接口未接入前保留旧 `os.yh` 宿主接口；缺少的新符号在编译期报错，
不提供成功空桩。

## 旧接口兼容

`open_file/open_file_mode/read_fd/write_fd/close_fd/create_dir/remove_dir/
remove_file/rename_file/is_terminal/process_id/terminate/platform/arch`
继续接受宿主 open 标志、失败返回 -1。新代码应优先使用结果结构接口。

## 实现文件

```text
libs/os/
  00_model.yh            Error/FdResult/IoResult/OpenOptions/DirEntry 等
  10_errors.linux.yh     私有错误归一化
  file.linux.yh          Linux 文件 API
  file.darwin.yh         Darwin write_once 兼容入口
  20_directory.linux.yh  DirReader/cwd
  30_process.linux.yh    spawn/wait/exit_now
  environment.yh         envp 查询（跨平台）
  40_sleep.linux.yh      旧 sleep_us（Linux）
  40_sleep.darwin.yh     旧 sleep_us（Darwin）
  os.yh                  旧接口兼容
  doc.yh                 仅注释的完整 API 参考
```
