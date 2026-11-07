#!/usr/bin/env python3
"""arch-check：yh 编译器架构守护。

检查三件事，缺一不可：

1. **依赖矩阵**：模块间 import 必须落在允许边内，且无环。
2. **状态/资源预算**：模块级可变全局、`gen.G()` 读点、未判空 `malloc`、
   未接线 `pub fn`、容量安全追加点不得越过当前基线（只减不增）。
3. **报告**：依赖边与状态读数一览，便于 release 记录跟踪趋势。

代码行数不在本工具里检查：规模统计由 `just code-stats` 单独报告，
`arch-check` 只守依赖方向与状态/资源纪律。

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
# 与 docs/03-design/yh-架构设计.md §3.1 对齐。
# 新增边必须同时更新此处与设计文档；`main` 是 CLI/构建驱动，位于最上层。
ALLOWED = {
    # GEN1 过渡：gen 的 support 桥只转发基础工具；迁移完成后删除这条边。
    "gen": {"support", "token"},
    "ir": set(),
    # support：L0 基础内核（缓冲/源/池/统计/诊断/目标/ABI 常量）。
    # 无 import，所有模块都可依赖它。
    "support": set(),
    # token：词法/语法共享词汇 + token 数组/游标；只依赖 support。
    "token": {"support"},
    # cache：缓存键 schema / ActionID / OutputID 原语。只依赖 gen 与标准库 hash，
    # 位于前端与构建层之下，避免 check↔lower 为了共用键原语互相 import。
    "cache": {"gen", "hash", "support", "token"},
    "lex": {"gen", "token", "support"},
    # comptime 只有一处窄口读（待定数组长度时的文件下标越界检查），
    # 走 proj.file_count() 而不是自己拿项目表。
    "comptime": {"gen", "proj", "token", "support"},
    "builtin": {"gen", "support"},
    # proj：项目/模块/文件表 + 目标/构建配置（2026-10-26 B1-1 自 gen/build 拆出）。
    # 它是前端与构建层共用的数据层，只允许依赖 gen；一旦反向依赖就成环。
    "proj": {"gen", "support", "token"},
    "ast": {"gen", "comptime", "proj", "support", "token"},
    # lower：CheckedModule → IRModule（2026-10-25 B3-2 自 ast 拆出）。
    # 只吃受检快照，不得 import parse/check/build；ast 不得反向 import lower。
    "lower": {"gen", "ir", "ast", "proj", "cache", "support", "check", "token"},
    "check": {"ast", "gen", "proj", "token", "support", "cache", "ir", "comptime"},
    "parse": {"gen", "lex", "comptime", "ast", "ir", "proj", "token", "support", "check"},
    "backend": {"gen", "ir", "support"},
    # link：工具链调用层（汇编、链接驱动、内嵌 lld、进程、时钟）
    # 2026-10-26 B2-2 自 build 拆出。它必须位于 build 之下、proj 之上：
    # 只允许 gen/proj/backend，不得 import build（否则 link ↔ build 成环）。
    "link": {"gen", "proj", "backend", "hash", "support"},
    # build 是构建引擎（A2c 后承担项目模型 + 链接 + 调度 + 模块发射），
    # 位于前端/后端之上，可依赖全部下层；main 只剩 CLI 与测试执行器。
    "build": {"gen", "lex", "parse", "comptime", "ast", "check", "ir",
              "backend", "builtin", "lower", "proj", "link", "hash", "cache", "libs", "token", "support"},
    # testkit：语言内测试执行器（yh test 子命令的实现），位于 build 之上。
    # 模块名不能叫 test——`test "..." {}` 是语言关键字。
    "testkit": {"gen", "parse", "build", "proj", "link", "token", "support", "ast"},
    # cmdline：命令行声明与解析（CLI-R）。唯一允许依赖标准库 libs/cli 的模块，
    # 这样 `cmd`（module main）自身保持「参数映射 + 调用面」，不直接引标准库。
    "cmdline": {"gen", "libs", "support"},
    "main": {"gen", "lex", "comptime", "ast", "check", "parse", "ir",
             "backend", "builtin", "build", "testkit", "lower", "proj", "link",
             "cmdline", "support"},}

# —— 状态/资源预算（现状即上限，只减不增；不含代码行数）——
# 代码规模由 `just code-stats` 单独报告，本工具不按行数阻断。
BUDGETS = {
    "max_globals": 197,        # + support.SessionCtx.data_label（匿名数据标签计数迁出 TaskCtx）        # + cache.store 绑定（C4 从 TaskCtx.cache_store 迁出）        # + lex.LexCtx（词法游标迁出 TaskCtx）        # CT 读型镜像：字符串标签/枚举成员/静态数据目录各 2-5 个槽        # + comptime 的 CT 事实镜像槽（类型/符号各 2 个，F4-0/2）
    "max_g_call_sites": 0,     # B1-4 起 gen.G() 不再导出：任何新增调用都会被抓到
    "max_unchecked_malloc": 0,
    "max_unwired_pub": 0,
    # 容量安全的下界指标：`append_*_cap` 调用点只增不减（A0c2 进度）。
    "min_cap_appends": 45,
    # GEN0（ADR-0021）：gen 拆分只减不增的三项预算。
    "max_gen_pub_fns": 82,     # gen 内 `pub fn` 文本声明数（平台变体重复）
    "max_gen_importers": 13,    # import gen 的模块数
    "max_taskctx_fields": 145,  # gen/state.yh 的 TaskCtx 字段数（会话开关/声明索引迁出后）
}

# —— comptime → gen 的符号白名单（F4 收口；只减不增）——
# comptime 不得依赖 gen 的语义表；下面每个符号都是待消除的已知债务，
# 新增依赖即红灯。分组理由写在 docs/02-plan/yh-F4-... §7。
GEN_SYMBOLS_FOR_COMPTIME = {
    # 值规则（F4-5 路线 A：编译期值语义内核，阶段内保留）
    "fp32_bits", "fp64_bits", "sem_can_assign", "sem_fold_const_binop",
    "sem_fold_const_unary", "sem_fold_fp_to_int", "sem_fold_norm",
    "sem_res_const", "sem_struct_finish",
    # 写型调用（F4-5 剩余：类型表归 TaskCtx，待「请求/应用」seam）
    "ty_push_agg",
    # 符号引用查询（待 F4-5 或镜像）
    "sym_ct_lit_text",
    # 每任务上下文（GEN4 随 TaskCtx 拆分消除）
    "task", "TaskCtx",
}

# 已知未接线但暂不删除的符号（当前为空；保留位置以便记录豁免）。
UNWIRED_EXEMPT = set()


def source_files():
    """递归列出 compiler/ 下的 .yh，跳过构建缓存与临时目录。"""
    files = []
    for f in sorted(SRC.rglob("*.yh")):
        rel = f.relative_to(SRC)
        if any(part in (".build", "tmp") for part in rel.parts):
            continue
        files.append(f)
    return files


def module_files():
    """按 `module` 声明分组；子目录里的源码不会绕过依赖检查。"""
    mods = {}
    for f in source_files():
        mods.setdefault(declared_module(f), []).append(f)
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

    # —— 2. 状态/资源预算（代码行数不在这里检查）——
    globals_n = 0
    g_calls = 0
    g_by_mod = {}
    cap_appends = 0
    unchecked = []
    decl_pub = {}
    gen_pub_fns = 0
    gen_importers = {m for (m, dep) in edges if dep == "gen"}

    for f in sorted(modname):
        text = read(f)
        lines = text.splitlines()
        m = modname[f]
        globals_n += len(re.findall(r"^let [A-Za-z_]", text, re.M))
        if m == "gen":
            gen_pub_fns += len(re.findall(r"^pub fn ", text, re.M))
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

    def budget(name, actual, detail=""):
        limit = BUDGETS[name]
        if actual > limit:
            problems.append(f"{name} 超预算：{actual} > {limit} {detail}")

    report = {}

    def taskctx_fields():
        """数 TaskCtx 的字段行（去注释/空行；数组字段也计一行）。"""
        text = read(SRC / "gen" / "state.yh")
        m = re.search(r"pub struct TaskCtx \{(.*?)\n\}", text, re.S)
        if not m:
            return 0
        count = 0
        for line in m.group(1).splitlines():
            code = line.split("//")[0].strip()
            if not code:
                continue
            if re.match(r"[A-Za-z_][A-Za-z0-9_]*\s+", code):
                count += 1
        return count

    budget("max_globals", globals_n)
    budget("max_g_call_sites", g_calls)
    # comptime → gen 符号白名单：只允许已知债务，新增即红灯。
    ct_dir = SRC / "comptime"
    if ct_dir.is_dir():
        used = set()
        for f in ct_dir.glob("*.yh"):
            text = read(f)
            for line in text.splitlines():
                code = line.split("//")[0]
                used |= set(re.findall(r"\bgen\.([A-Za-z_][A-Za-z0-9_]*)", code))
        extra = sorted(used - GEN_SYMBOLS_FOR_COMPTIME)
        if extra:
            problems.append("comptime 新增 gen 依赖：" + ", ".join(extra))
        report["comptime_gen"] = len(used)

    budget("max_gen_pub_fns", gen_pub_fns, "gen")
    budget("max_gen_importers", len(gen_importers), "import gen")
    budget("max_taskctx_fields", taskctx_fields(), "TaskCtx")
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

    # —— 3. 报告（代码规模见 `just code-stats`）——
    print(f"模块 {len(mods)} 个，文件 {len(modname)} 个")
    print(f"  依赖边 {len(edges)} 条")
    g_top = "  ".join(f"{k}={v}" for k, v in
                      sorted(g_by_mod.items(), key=lambda x: -x[1])[:4])
    g_detail = f"（{g_top}）" if g_top else ""
    print(f"  模块级可变 let {globals_n}；gen.G() 调用点 {g_calls}{g_detail}")
    print(f"  gen pub fn {gen_pub_fns}；import gen 模块 {len(gen_importers)}；"
          f"TaskCtx 字段 {taskctx_fields()}")
    print(f"  未判空 malloc {len(unchecked)}；未接线 pub {len(unwired)}；"
          f"容量安全追加点 {cap_appends}")
    if "comptime_gen" in report:
        print(f"  comptime→gen 符号 {report['comptime_gen']}"
              f"（白名单 {len(GEN_SYMBOLS_FOR_COMPTIME)}）")

    if problems:
        print("\n架构违规:")
        for p in problems:
            print("  - " + p)
        return 0 if args.report else 1
    print("架构检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
