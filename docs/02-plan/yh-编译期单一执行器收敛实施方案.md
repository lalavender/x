# yh 编译期 typed 单一执行器收敛实施方案（删除早期 token 求值器）

日期：2026-10-07。状态：实施中。

## 目标

编译期函数此前有两套执行器：typed IR 执行器（`ct_ir.yh` 等）与早期 token 求值器
（`ct_eval_expr.yh`、`ct_eval_bool.yh`）。后者只在目标函数 `ir_ready == 0`
（尚未捕获 typed IR）时兜底，服务「pass1 期间的顶层整数常量折叠」与
「数组长度 token 探测」两条早期快路径。本片删除第二套执行器，让 typed IR 成为
唯一执行器，并把早期求值交给已有的 typed 布局常量依赖调度。

## 设计要点

- 根因：早期快路径在 **pass1**（`parse_source` 期间）折叠顶层 `const` 与数组长度，
  此时 CT 函数的 typed IR 还没捕获（捕获在 pass2 的 `parse_source_ct_fns`），
  于是回退 token 求值器。
- 收敛点：`parse/parse_global_init.yh` 的 `parse_global_ct_const_probe` 把准入条件从
  「token 探测支持该调用树」改为 **`comptime.ct_is_prepared(sym) != 0`**。
  pass1 期间恒为 0，因此早期折叠让位给 pass2a 之后的
  typed 布局常量依赖调度（`ct_layout_register` / `ct_layout_advance`）；
  捕获完成后若仍有调用，快路径依旧可用。
- 删除：`comptime/ct_eval_expr.yh`、`comptime/ct_eval_bool.yh`、
  registry 内的数组长度 token 探测链（`ct_array_length_probe_*`，
  含 `ct_find_name`）以及 `ct_00_model.yh` 的 `CtReader`/`CtLocal`。
  `ct_invoke_in_frame` 的回退分支改为诊断
  「编译期函数正文不在受支持的 typed IR 子集内」。

## 验收

1. 受影响的 9 个用例（`fail/76`、`fail/79`、`fail/88`、`run/64`、`run/92`、
   `run/111`、`run/113`、`run/115` 等）改由 typed 执行器求值，诊断文本不变。
2. `make test` 242/242、`make selfhost-native` 全绿（自解析源文件数 72 → 70）。
3. 净减约 890 行：`comptime/` 从 5480 行降到 4593 行。

## 教训

本轮第一次删除时只改了回退分支，未同时收敛早期快路径，导致 9 个用例
（`ir_ready == 0`）失败；当时又误删了未提交的 `ct_eval_expr.yh`（557 行版本）
与 `ct_eval_bool.yh`，git 只能恢复到 181 行的旧骨架。最终通过**修根因**
（快路径准入条件）而非恢复遗留代码解决问题。结论：删除执行器前先确认所有
调用路径都能被目标执行器接管，且未提交的工作区文件应先入库或备份。
