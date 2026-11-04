#!/usr/bin/env python3
"""arch-check：yh 编译器架构守护。

检查三件事，缺一不可：

1. **依赖矩阵**：模块间 import 必须落在允许边内，且无环。
2. **预算**：文件/函数/模块行数、模块级可变全局、`gen.G()` 读点、
   未判空 `malloc`、未接线 `pub fn` 不得越过当前基线（只减不增）。
3. **报告**：当前数值一览，便于在 release 记录里跟踪趋势。

用法：
    python3 tools/arch-check.py            # 报告 + 违规即失败
    python3 tools/arch-check.py --report   # 只报告，恒 0（接入初期用）

预算上调必须改本文件的 BUDGETS 并说明理由——这是刻意的摩擦：
架构约束靠"改一行就放宽"会立刻失效。
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "compiler"

# —— 允许的依赖边（消费者 -> 被依赖）——
# 与 docs/03-design/yh-系统架构与长期演进设计-2026-10-24.md §4.1 对齐。
# 新增边必须同时更新此处与设计文档；`main` 是 CLI/构建驱动，位于最上层。
ALLOWED = {
    "gen": set(),
    "ir": set(),
    "lex": {"gen"},
    # comptime 只有一处窄口读（待定数组长度时的文件下标越界检查），
    # 走 proj.file_count() 而不是自己拿项目表。
    "comptime": {"gen", "proj"},
    "builtin": {"gen"},
    # proj：项目/模块/文件表 + 目标/构建配置（2026-10-26 B1-1 自 gen/build 拆出）。
    # 它是前端与构建层共用的数据层，只允许依赖 gen；一旦反向依赖就成环。
    "proj": {"gen"},
    "ast": {"gen", "comptime", "ir", "proj"},
    # lower：CheckedModule → IRModule（2026-10-25 B3-2 自 ast 拆出）。
    # 只吃受检快照，不得 import parse/check/build；ast 不得反向 import lower。
    "lower": {"gen", "ir", "ast", "proj"},
    "check": {"gen", "ast", "proj"},
    "parse": {"gen", "lex", "comptime", "ast", "ir", "proj"},
    "backend": {"gen", "ir"},
    # link：工具链调用层（汇编、链接驱动、内嵌 lld、进程、时钟）
    # 2026-10-26 B2-2 自 build 拆出。它必须位于 build 之下、proj 之上：
    # 只允许 gen/proj/backend，不得 import build（否则 link ↔ build 成环）。
    "link": {"gen", "proj", "backend"},
    # build 是构建引擎（A2c 后承担项目模型 + 链接 + 调度 + 模块发射），
    # 位于前端/后端之上，可依赖全部下层；main 只剩 CLI 与测试执行器。
    "build": {"gen", "lex", "parse", "comptime", "ast", "check", "ir",
              "backend", "builtin", "lower", "proj", "link"},
    # testkit：语言内测试执行器（yh test 子命令的实现），位于 build 之上。
    # 模块名不能叫 test——`test "..." {}` 是语言关键字。
    "testkit": {"gen", "parse", "build", "proj", "link"},
    # cmdline：命令行声明与解析（CLI-R）。唯一允许依赖标准库 libs/cli 的模块，
    # 这样 `cmd`（module main）自身保持「参数映射 + 调用面」，不直接引标准库。
    "cmdline": {"gen", "libs"},
    "main": {"gen", "lex", "comptime", "ast", "check", "parse", "ir",
             "backend", "builtin", "build", "testkit", "lower", "proj", "link",
             "cmdline"},}

# —— 预算（现状即上限，只减不增）——
# 数值为 2026-10-24 实测；下调请同步改这里，上调需在 finish.md 说明理由。
BUDGETS = {
    "max_file_lines": 2042,        # module_build.yh（A2c 拆分后必须下降）
    "max_function_lines": 360,     # mb_link 674（含前导注释的上界口径）
    "max_module_lines": 461,       # main（P1 一命令一文件：driver 分派 + common 前奏 +
                                   # 8 个 cmd_*.yh；api.yh 删除；+71 全为 9 个新文件头
                                   # 注释，逻辑行数不变；依赖边 55 条不变；见 finish.md
                                   # 2026-11-05 与 docs/03-design 模块架构目标设计 §4；
                                   # +3 VENC：driver 首行 gen.console_utf8_init() 调用，
                                   # Windows 控制台切 65001 码页显示中文）
    "max_testkit_lines": 1632,     # testkit（YT2d-3 +37；B1-1 迁表后 -14；W2-7 无 fork 子进程的
                                   # 十进制用例号/模块内文件序号/--filter UTF-8 规整 +31；
                                   # 合并后 tc_case_start 的 Windows 分支（CreateProcess 重入）+7）
    "max_build_lines": 6990,      # build（B1/B2 拆分口径；+232 UF1；W2 的 windows 目标/宿主文件、
                                  # 模块子进程与 cold 标记 +299，见 finish.md 2026-11-03；
                                  # +4 合入 ci/github-actions 的 Windows 闭包/CI 适配；
                                  # +23 VTEST：pj_name_is_test + pj_dir_less 测试文件后置
                                  # 排序规则，见 finish.md 2026-11-05；
                                  # +14 P0-A：--emit-asm 临时目录 CWD 优先 + TEMP 兜底
                                  # 重试，见 finish.md 2026-11-05）
    "max_link_lines": 4272,      # link（B2-2 新建 + B2-3 阶段化 3,657；W1-5/W2 的 COFF 链接
                                 # （windows_link.yh 前缀/SDK/子进程 worker）与 .lib/.dll 输入校验 +509）
    "max_proj_lines": 1396,        # proj（B1-1 表/路径 + B2-1 产物键 + YH_BUILD_CACHE 缓存根；
                                   # W1-6 windows 目标组 5/6 与盘符绝对路径 +12）
    "max_cmd_share_pct": 1,        # 381 / 51484 ≈ 0.7%
    "max_globals": 172,
    "max_g_call_sites": 0,      # B1-4 起 gen.G() 不再导出：任何新增调用都会被抓到
    "max_unchecked_malloc": 0,
    "max_unwired_pub": 0,
    # 容量安全的下界指标：`append_*_cap` 调用点只增不减（A0c2 进度）。
    "min_cap_appends": 45,
}

# 已知未接线但暂不删除的符号（当前为空；保留位置以便记录豁免）。
UNWIRED_EXEMPT = set()


def module_files():
    mods = {}
    for d in sorted(SRC.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or d.name == "tmp":
            continue
        yh = list(d.glob("*.yh"))
        if yh:
            mods[d.name] = yh
    return mods


def read(p):
    return p.read_text(errors="ignore")


def imports_of(path):
    return re.findall(r"^import ([A-Za-z0-9_]+)", read(path), re.M)


def declared_module(path):
    m = re.search(r"^module ([A-Za-z0-9_]+)", read(path), re.M)
    return m.group(1) if m else path.parent.name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="只报告，不因违规失败")
    ap.add_argument("--root", default=str(ROOT), help="源码根（自测用）")
    args = ap.parse_args()

    global SRC
    SRC = Path(args.root) / "compiler"
    mods = module_files()
    modname = {}
    for m, files in mods.items():
        for f in files:
            modname[f] = declared_module(f)

    problems = []

    # —— 1. 依赖边与环 ——
    edges = set()
    for f, m in modname.items():
        for dep in imports_of(f):
            edges.add((m, dep))
    for m, dep in sorted(edges):
        if m not in ALLOWED:
            problems.append(f"未登记模块 {m}（{m} -> {dep}）")
        elif dep not in ALLOWED[m]:
            problems.append(f"越界依赖 {m} -> {dep}")

    graph = {}
    for m, dep in edges:
        graph.setdefault(m, set()).add(dep)
    color = {}

    def dfs(n, stack):
        color[n] = 1
        stack.append(n)
        for d in graph.get(n, ()):
            if color.get(d) == 1:
                problems.append("依赖环：" + " -> ".join(stack[stack.index(d):] + [d]))
            elif color.get(d, 0) == 0:
                dfs(d, stack)
        stack.pop()
        color[n] = 2

    for m in sorted(ALLOWED):
        if color.get(m, 0) == 0:
            dfs(m, [])

    # —— 2. 预算 ——
    total_lines = 0
    per_module = {}
    max_file = (0, "")
    all_funcs = []
    globals_n = 0
    g_calls = 0
    g_by_mod = {}
    cap_appends = 0
    unchecked = []
    decl_pub = {}

    for f in sorted(modname):
        text = read(f)
        lines = text.splitlines()
        n = len(lines)
        total_lines += n
        m = modname[f]
        per_module[m] = per_module.get(m, 0) + n
        if n > max_file[0]:
            max_file = (n, str(f.relative_to(SRC.parent)))
        starts = [i for i, l in enumerate(lines) if re.match(r"^(pub )?fn ", l)]
        for j, i in enumerate(starts):
            end = starts[j + 1] if j + 1 < len(starts) else len(lines)
            all_funcs.append((end - i, f"{f.relative_to(SRC.parent)}:{i + 1}"))
        globals_n += len(re.findall(r"^let [A-Za-z_]", text, re.M))
        cap_appends += len(re.findall(r"append_[a-z_]+_cap\(", text))
        gm = len(re.findall(r"gen\.G\(\)", text))
        g_calls += gm
        if gm:
            g_by_mod[m] = g_by_mod.get(m, 0) + gm
        for i, l in enumerate(lines):
            if not re.search(r"(?<![A-Za-z0-9_@])malloc\(", l) or l.strip().startswith("//"):
                continue
            # 优先按变量名追踪判空（判空可能与分配相隔十余行）；
            # 取不到变量名时退回窗口扫描。成功路径的内存耗尽由 gen.alloc
            # 统一处理，这里只报告"裸 malloc 且未判空"。
            mvar = re.match(
                r"\s*(?:let\s+)?([A-Za-z_][A-Za-z0-9_]*)"
                r"(?:\s+(?:\*\w+|\w+))?\s*=\s*.*malloc\(", l)
            guarded = False
            if mvar:
                name = re.escape(mvar.group(1))
                guarded = re.search(name + r"\s*==\s*0", "\n".join(lines[i:i + 30])) is not None
            if not guarded:
                guarded = re.search(r"==\s*0|!=\s*0|<\s*0", "\n".join(lines[i:i + 20])) is not None
            if not guarded:
                unchecked.append(f"{f.relative_to(SRC.parent)}:{i + 1}")
        for mm in re.finditer(r"^(?:pub )?fn ([A-Za-z_][A-Za-z0-9_]*)", text, re.M):
            decl_pub.setdefault(mm.group(1), f)

    max_func = max(all_funcs) if all_funcs else (0, "")
    cmd_share = round(per_module.get("main", 0) * 100 / max(total_lines, 1))

    def budget(name, actual, detail=""):
        limit = BUDGETS[name]
        if actual > limit:
            problems.append(f"{name} 超预算：{actual} > {limit} {detail}")

    budget("max_file_lines", max_file[0], max_file[1])
    budget("max_function_lines", max_func[0], max_func[1])
    budget("max_module_lines", per_module.get("main", 0), "main")
    budget("max_build_lines", per_module.get("build", 0), "build")
    budget("max_testkit_lines", per_module.get("testkit", 0), "testkit")
    budget("max_proj_lines", per_module.get("proj", 0), "proj")
    budget("max_link_lines", per_module.get("link", 0), "link")
    budget("max_cmd_share_pct", cmd_share, "%")
    budget("max_globals", globals_n)
    budget("max_g_call_sites", g_calls)
    budget("max_unchecked_malloc", len(unchecked), ",".join(unchecked[:3]))
    unwired = [s for s in UNWIRED_EXEMPT if s]
    budget("max_unwired_pub", len(unwired))
    if cap_appends < BUDGETS["min_cap_appends"]:
        problems.append(
            f"min_cap_appends 低于基线：{cap_appends} < {BUDGETS['min_cap_appends']}")

    # —— 版本一致性（VCONST，2026-11-05）：cmdline 的 YH_VERSION_TEXT
    # 编码进二进制供 `yh --version` 使用，必须与 compiler/project.toml 的
    # project.version 一致，防止滚版本时只改一处。
    toml_text = (ROOT / "compiler" / "project.toml").read_text(encoding="utf-8")
    mtoml = re.search(r'^version\s*=\s*"([^"]+)"', toml_text, re.M)
    mconst = re.search(r'YH_VERSION_TEXT \*char = "yh ([^"]+)"',
                       (SRC / "cmdline" / "cmdline.yh").read_text(encoding="utf-8"))
    if not mtoml or not mconst:
        problems.append("版本一致性：找不到 project.toml version 或 YH_VERSION_TEXT 常量")
    elif mtoml.group(1) != mconst.group(1):
        problems.append(
            f"版本不一致：project.toml={mtoml.group(1)} "
            f"cmdline.YH_VERSION_TEXT={mconst.group(1)}")

    # —— 3. 报告 ——
    print(f"模块 {len(mods)} 个，文件 {len(modname)} 个，代码 {total_lines} 行")
    print("  行数：" + "  ".join(f"{m}={per_module[m]}" for m in sorted(per_module)))
    print(f"  依赖边 {len(edges)} 条；最大文件 {max_file[0]} 行（{max_file[1]}）")
    print(f"  最大函数 {max_func[0]} 行（{max_func[1]}）")
    g_top = "  ".join(f"{k}={v}" for k, v in
                      sorted(g_by_mod.items(), key=lambda x: -x[1])[:4])
    g_detail = f"（{g_top}）" if g_top else ""
    print(f"  main 占比 {cmd_share}%；模块级可变 let {globals_n}；"
          f"gen.G() 调用点 {g_calls}{g_detail}")
    print(f"  未判空 malloc {len(unchecked)}；未接线 pub {len(unwired)}；"
          f"容量安全追加点 {cap_appends}")

    if problems:
        print("\n架构违规:")
        for p in problems:
            print("  - " + p)
        return 0 if args.report else 1
    print("架构检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
