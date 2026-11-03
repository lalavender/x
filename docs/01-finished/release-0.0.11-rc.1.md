# 0.0.11-rc.1 — 未使用函数直接报错（UF1）

预发布（prerelease）。本版在 0.0.10 基础上加入一条前端硬规则：**没有被使用的私有
函数直接报编译错误**，并用这条规则把编译器与标准库里积下的 24 个死函数清掉。
rc.1 由 0.0.10 正式版种子构建（种子链：0.0.9 → 0.0.10-rc.1 → 0.0.10 → 0.0.11-rc.1）。

## 主要内容

**UF1：未使用函数检查**

- 规则：本模块声明、既没有 `pub` 也没有 `extern` / C ABI 的函数定义，如果整个模块的
  源码里除了它自己的声明名之外没有任何同名标识符，`build` / `run` / `test` 与单文件
  编译（`yh f.yh`、`yh check f.yh`）都报
  `函数未使用（本模块没有任何引用；请删除或改为 pub）`。
- 跳过面：`pub`（导出面；入口 `main` 与 `test` 生成符号也按 pub 登记）、`extern`
  （无正文）、`@[extern]` 带正文的 C ABI 回调目标（按 C 名字导出，可能只被同项目的
  C 源或外部调用方引用，本模块源码里看不到引用）。
- 范围按**模块**而不是按文件：同包跨文件的私有调用是正常用法。
- 时机在 pass1 之后、pass2 之前（符号与顶层声明索引齐备即可判定），所以不受函数级
  check 切片命中与否影响。

**为什么按 token 而不是解析期引用标记**

三条路径都会让「解析时标记引用」在增量构建里漏记，从而把活函数判死：

1. 函数级 check 切片命中时整个正文不重新解析（`parse_decl` 直接 `continue`）；
2. 普通函数体里的 `$f(...)` 编译期调用在语义阶段直接折成常量、不留引用节点；
3. 生产构建按设计不解析 `test` 正文，只在 test 里用到的私有辅助会被误判。

代价是保守判据：只会漏报（同名局部变量/字段遮蔽、递归自引用算作已使用），不会把
合法程序判死。精确化（按解析身份的引用集合）已立项在 `docs/todo.md`。

**实现约束：检查对 GenState 只读**

首版用 `tml_intern_str` + `sym_lookup_off` 把声明名映射到符号，名字池因此变长，连带
改变后续阶段的池布局——`LA3` 函数级缓存矩阵的「插入新函数」从预期的 check 4 命中
1 未命中变成 0 命中 5 未命中。现改为在符号表区间按字节比较直接找符号
（`uf_symbol_for_decl`），不再往名字池/类型表里追加任何东西。

**清掉的死代码（24 个，全部是 LL12 退役旧发射器/历史迭代的遗留）**

- `gen`：`abi_c_signature`、`ty_name_text`、`tg_sym_prefix`、`tg_is_2byte`、
  `tg_is_8byte`、`tg_align_scalar`
- `backend`：`llvm_abi_emit_c_aggregate_call`（旧 C 聚合 ABI 发射，76 行）
- `comptime`：`ct_invoke`；`ast`：`ast_comptime_for_find_binding`、
  `ast_comptime_for_info`；`parse`：`ct_enum_pending_reset`、`ct_enum_pending_count`
- `lower`：`checked_lower_error`、`checked_lower_expr`（薄包装，正文版本才是调用面）
- `build`：`li_kind`、`mb_sub_dir`、`pj_source_cat`
- `libs`：`cli.text_visible_width`、`cli.action_takes_values`、`json.utf8_is_scalar`、
  `toml.p_at_end`、`toml.p_current`、`libc.text_len`、`libc.is_digit`

**语料**

- 新增 `tests/yh-run/fail/168-unused-function.yh`（`fail-contains: 函数未使用`）与
  `tests/yh-run/pass/10-unused-function-scope.yh`（`pub` 未用、函数值引用、只在
  `test` 正文里用到的私有辅助都不算未使用）。
- 新增模块级 fixture `tests/modules/projects/unusedfn`：`ufmath` 模块的私有 `helper`
  只在同包另一个文件里被调用 → 通过；`dead` 项目的孤儿私有函数 → 报错。`build-check.py`
  新增 `uf1-module-scope-use`(42) 与 `uf1-unused-function` 两个用例。
- 既有 fixture 按新规则做最小调整（改 `pub` 或由 `main` 以零净贡献引用）：
  `ytestsem`、`llvmarchitecture/cases/library.yh`、`irfront`、`tokenreplay`、
  `scheduler`/`scheduler-diamond` 生成的 600 个 `private_NNNN` 及「私有正文失败阻止
  链接」探针、`tests/yh-run/pass/06..08`、`run/181`、`LA3` 插入探针（改自递归形态，
  保住 4 命中 1 未命中口径）。

**预算与文档**

- `tools/arch-check.py`：`max_build_lines` 10,807 → 11,015（UF1 新增 222 行、删掉本模块
  3 个死函数 25 行，净 +197）。
- `compiler/README.md`（导出面 + 规模数字）、`docs/todo.md`（UF1 精确化待办 + 基线表）、
  `docs/03-design/yh-Go风格模块与包设计.md`（规则与理由）、
  `docs/03-design/yh-架构图-2026-10-25.md`（节点⑤补 UF1）同步。

## 不兼容变更（升级必读）

含「私有且无任何引用」函数的项目/库，从本版起会**编译失败**。处理方式二选一：

1. 删掉该函数（它是死代码）；
2. 确实要保留就标 `pub`（表示它是模块导出面）。

`@[extern]` 带正文的 C 回调目标不受影响，无需改动。

## 实测（本机 Darwin/arm64）

| 门 | 结果 |
| --- | --- |
| `just test` | 全绿（语法 49/49、运行 362/363 含 1 SKIP、pass 9/9） |
| `just libs-test` | 全绿（122 PASS） |
| `just selfhost-native` | 全绿：cc3/cc4 固定点 39 产物一致、cc4 自解析 120 文件、模块语料 19/19、`build-check` **124/124**、LA3 缓存矩阵 O0/O2、LA0 架构基线 |
| `tools/arch-check.py` + 自测 | 通过（自测 2/2） |

## 三端验证

`release.yml` 由本 tag 触发：darwin-arm64 / linux-arm64 / linux-x86_64 三端各自
`just bootstrap` → 平台专项门 → 语料 → `SKIP_CORPUS=1 selfhost-native`，产物
`yh-0.0.11-rc.1-<platform>.tar.gz` 与 `.sha256` 作为 prerelease 资产发布；结果以 Release
页面与 CI 运行记录为准。

## 已知边界

- UF1 判据按名字：同名局部变量/字段遮蔽会漏报，递归自引用的孤立函数也会漏报
  （`docs/todo.md`「UF1 精确化」）。
- 只检查函数，不检查 `const`/`let`/类型的未使用；不提供 `@[keep]` 一类逃生属性
  （`pub` 已足够）。
- 0.0.10 的已知边界（单函数改动 ≤3 s 需 PC7、check 切片只覆盖约 1/5 函数、
  Linux 裸跑 `yh build` 需 `YH_LINK_RUNTIME_FLAGS`、产物二进制不可位级复现 RB5）
  延续不变。
