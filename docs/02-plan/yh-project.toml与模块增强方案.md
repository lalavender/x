# project.toml 与模块系统增强实施方案

日期：2026-09-30。状态：按用户规划实施（规划原文见 docs/todo.md「项目
规划」节）。基于已交付的模块系统（ADR-0005/0007，MOD-U0–U5）。

## 用户规划 → 设计决策

| 规划原文 | 设计决策 |
| --- | --- |
| 每个文件第一行(注释除外)必须是 module 声明 | 项目模式强制（mod_parse_head 已要求首 token 为 module，即注释/空白后立即声明）；**旧单文件 CLI 不强制**（设计 §11 向后兼容保留） |
| 每个目录有且只有一个模块，否则报错 | 扫描索引期检查：同目录内第二个不同 module 名报错，诊断给出两个文件位置 |
| 循环引用直接报错 | 已有（导入图 topo 拒环 + 完整链诊断），补语料确认 |
| `import os as os1` | import 语法扩展 `import NAME (as IDENT)?;`；查找名与绑定名分离：查找按 NAME，限定调用用别名。同文件同别名重复报错；同模块不同别名合法 |
| mod.toml 改名 project.toml | 清单文件改名，不兼容旧名；依赖键仍为 [dependencies] 表键 |
| `import os` = 同项目 os；`import libs.os` = libs 项目的 os | 跨项目导入：点分两段 `KEY.MOD`，第一段 = [dependencies] 的**依赖键**，第二段 = 模块名；限定导入不走三层搜索，直接解析到键对应项目；多于两段报错。绑定名取最后段（可用 as 改）。依赖键唯一（TOML 键）故无歧义 |
| 缓存 .build/asm、.build/obj、.build/yh | .build/asm/<mod>.s；.build/obj/<mod>.o（链接改两步：先 gcc -c 逐模块汇编为 .o，再链接全部 .o）；接口与 manifest 在 .build/iface/<mod>.s.i、.build/manifest/<mod>.manifest；入口项目默认产物 = .build/yh（-o 显式指定时用用户路径） |
| 模块未修改直接用缓存 | manifest 内容哈希已有；**补编译器身份**（对编译器二进制自身 FNV-1a）入键——滚动代次下热缓存才安全 |

## 实施阶段

| 阶段 | 内容 | 门 |
| --- | --- | --- |
| M1 语法 | ImportEnt 扩展（查找名/别名/项目键）、import as、点分导入解析、绑定按别名 | 四门（编译器自身随改） |
| M2 绑定 | project.toml 改名、依赖键限定解析、目录唯一模块检查 | modules 语料 + 项目验收 |
| M3 缓存 | .build 布局、两步链接（asm→obj→link）、缓存键补编译器哈希、热缓存 | 构建两轮：第二轮全 [缓存] |
| M4 语料与自举 | fixtures 更新、新用例（别名/跨项目/目录冲突/环）、编译器自身 project.toml、Makefile、全门 | make / test / selfhost-native / selfbuild-gate |

## 新语法汇总

```text
importDecl  : 'import' importTarget ( 'as' IDENT )? ';' ;
importTarget: IDENT | IDENT '.' IDENT ;   // NAME | KEY.MOD
```

- `import os;` → 查找 os（本项目→标准库→直接依赖），绑定名 os
- `import os as os1;` → 同上，绑定名 os1
- `import libs.os;` → 依赖键 libs 的项目的 os 模块，绑定名 os
- `import libs.os as l;` → 同上，绑定名 l

同文件绑定名重复报错（含「同项目 os + libs.os 未用 as 区分」的场景——
这正是 as 的用途）。
