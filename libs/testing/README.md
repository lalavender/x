# testing

`yh test` 的最小运行时辅助模块。

| 接口 | 行为 |
| --- | --- |
| `fail(message *char) void` | 报告失败原因并结束当前用例，父进程记为 FAIL |
| `skip(reason *char) void` | 报告跳过原因并结束当前用例，父进程记为 SKIP |

基本断言用编译器内建的 `$assert(cond[, "消息"])`，不需要导入本模块。
两函数都向 fd 3 写测试记录并立即退出，因此不会返回；用例内其后的语句不执行。
本模块只依赖 prelude 的 `write` 与 `exit`，不形成 `os → testing → os` 一类依赖环。
