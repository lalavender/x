# 0.0.14-rc.2 — 修复 rc.1 的跨平台门禁失败

预发布候选（prerelease）。rc.1 的发布工作流暴露了四处跨平台门禁失败；
本 RC 只做门禁修复与一处无消费者配置的删除，功能面与 rc.1 相同。
种子链：0.0.13 → 0.0.14-rc.1（未发布）→ 0.0.14-rc.2（由 0.0.13 正式版种子构建）。

## rc.1 → rc.2 修复

**1. Darwin 门禁**

- `tools/link-closure.py check` 仍用仓库内 `tmp/llvm-migration` 拼宿主记录路径，
  闭包移到项目外后报「缺少宿主记录」；改为 `host_record_path`（缓存根）。
- `tests/selfhost/darwin/llvm-darwin-default.py` 的 `print` 引用统计机制删除后
  不存在的 `checked`/`emitted`/`fallback`（NameError）；改为产物/汇编断言描述。
  本地 `just test-llvm-darwin` 全绿。

**2. Windows 门禁：list 与 libc 重复符号**

`libs/list` 同时 `import memory` 与 `import libc`，Windows 零 CRT 上 libc 的
`@[extern] memset/memmove` 与 prelude 运行时符号重复（lld-link duplicate
symbol）。按设计 §12 回退方案改为模块内 `list_copy_overlap`，list 只依赖
`memory`；语义与接口不变。

**3. Windows 门禁：`[env]` 使 `--emit-module` 子进程 0xC0000005（根因修复）**

`6469c32` 引入 `[env]` 时为 `proj.PProj` 增加了 `envs/env_n/env_cap`，但
`proj.add_project` 只初始化到 `link_group_cap`；`PProj` 由 `malloc` 分配，
未初始化字段在 Windows 上是垃圾值。`pj_load_env_config` 首次追加时按垃圾
`env_cap/envs` 走扩容/写入路径，`yh test support` 的 `--emit-module support`
子进程启动即崩溃（退出码 3221225477）；`link-env-manifest` 的构建同样崩。
macOS/Linux 的堆恰好为零页，掩盖了该缺陷。

修复：`add_project` 显式把 `envs/env_n/env_cap` 清零。`compiler/project.toml`
的 `[env]` 保留（加载顺序已改为先于 `[link]` 快照），`link-env-manifest`
覆盖默认值与进程环境覆盖两条路径。

另修复同一路径暴露的第二个问题：无编译期正文的模块不产出 `.s.ct`，
父调度器 `mb_sched_publish_interface` 原先把缺失当失败；Windows 的
`u8-dup-module-path-import` 因此报「无法打开文件 ...s.ct.session-*」。
现在缺失时跳过 CT 提交（与 `mb_iface_ct_same` 的缺失语义一致），`.s.i`
仍必须存在。

第三个问题：模块缓存命中的任务不会重写 session 接口，父调度器
`mb_sched_publish_interface` 仍按 session `.s.i` 发布，Windows 上
`u8-dup-module-path-import` 因此报「无法打开文件 ...s.i.session-*」。
现在 session `.s.i` 缺失时跳过发布（持久接口已由缓存命中保持）。

第四个问题：`proj.canon` 只按 `/` 分段，Windows 的 root/argv 可能带
反斜杠，导致模块目录身份（`(名字, 目录)` 与重名模块的目录指纹）混用
`\\` 与 `/`。`canon` 现在把 base 与 rel 的反斜杠统一成 `/` 再规范化。

**4. build-check 的 cinterop 生成物**

`vendor/prebuilt.o` 被 `.gitignore` 的 `*.o` 排除，干净 checkout 上
`[c] objects` 必然报路径不存在；`copy_proj` 在把 fixture 交给编译器前按需
编译 `prebuilt.c`（Windows 无 gcc，跳过该生成，`u3-c-*` 由 WINDOWS_SKIP 跳过）。

**5. 发布流程路径**

`c7ca83d` 把 `cmdline` 归组到 `cmd/yh` 后，`release.yml` prepare 仍读旧路径，
打版本 tag 会在版本号一致检查处红；同步 `.github/workflows/release.yml` 与
`AGENTS.md`。

## 与 rc.1 相同的功能面

模块身份与路径导入、`compiler/` 源码归组、编译统计机制删除、`libs/list`
动态列表、LLVM 闭包缓存项目外化、`just codeflow`、arch-check 删除。详见
[rc.1 发布说明](release-0.0.14-rc.1.md)。

## 验收

- 本地：`just test`、`just test-libs`（O0/O2）、`just test-llvm-darwin`、
  `just selfhost-native`（固定点一致、cc4 自解析、project cases 125/125）。
- 四端 CI：本 RC 由 `release.yml` 四端并行构建；`[env]` 初始化修复后
  Windows 的 `--emit-module`/`link-env-manifest` 崩溃应消失，仍需观察
  `u8-dup-module-path-import`（rc.1 的实验 tag 在 Windows 上唯一剩余失败）。
- 发布资产验收（CI 完成后）：`rm -rf bin && just fetch-seed` → `just` →
  `just test` → `just selfhost-native`。
