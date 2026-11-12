#!/usr/bin/env python3
"""前端耦合守卫：锁定 S4 切片已建立的依赖方向与只减不增预算。

检查项（全部按代码行统计，先剥离注释）：

1. `parse` 对 `check.` / `comptime.` 的引用数不得超过基线（只减不增）；
   其中表达式内联语义（A 类，S4-4 改版删除目标）单独按符号集计数。
2. `parse/parse_type.yh` 不得直接查类型/符号表（已迁 check.type_syntax）。
3. `ast` 不得 import `check`；`support` 不得 import 上层模块。
4. `comptime` 不得 import `check`/`ast`/`parse`；`lower` 不得 import `parse`。

基线随切片落地下调；提高基线等于回退 S4 进度，脚本直接失败。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMPILER = ROOT / "compiler"

# 2026-11-10 五片（类型语法/sizeof/纯语法 AST/数组长度/S4-2a-b 影子门）+
# 纯 Res 操作外置（res_reset/res_copy 归 support）后的代码引用数。
# 2026-11-11 S4-3 一片：comptime 引用改走 check 门面（sem_stmt_diag 等），
# 总数暂 +1；S4-4 删 A 类 47 后总数将净降到约 64，届时随片下调。
# S4-3 二片：布局驱动/依赖发现/枚举元信息/签名校验改走 check/ct_gate.yh 门面，
# parse→comptime 75 → 49，临时 +16（S4-4 删 A 类后净降，届时随片下调）。
# S4-3 三片：展开簿记（控制/边界/计费/捕获）改走门面，49 → 31，临时 +15。
# S4-3 四片：全局聚合建模与声明收尾门面下沉，31 → 9（余 parse_expr 的
# $-调用求值，随 S4-4 eval 删），临时 +21。
# S4-3 五片：parse_expr 的 $-调用求值 9 处门面化，comptime → 0；+9。
# S4-4 驱动落地点位：parse_expr 顶层回填 `Res` 调用 check.sem_eval_node（+1）。
# S4-4 第一片（2026-11-11，二元层）：8 个二元层改走统一 eval 入口，A 类 47 → 39，
# parse→check 174 → 167。
# 第二片（一元层）：`- + ! ~`/`*`/`&`，A 类 39 → 36，parse→check → 165。
# 第三片（postfix 层）：下标/切片/`.to_type`/成员×2/元信息×3，A 类 36 → 28。
# 第四片（调用 ABI）：parse_expr 3 + parse_interp 4 + parse_comptime 6，A 类 28 → 15。
# 第五片（字面量/名字/sizeof 层）：A 类 15 → **0**（目标形态达成：parse 只调 eval 入口，
# 语义与诊断全部在 check 内）；parse→check 162（余下为语句/声明/类型级真语义动作）。
# S4-2 语句侧（2026-11-11）：`parse_stmt` 9 处语句语义内核改走 `check.sem_eval_*`
# （break/continue/goto/标签/赋值/return/诊断/局部绑定），直调内核 → **0**；
# parse→check 仍 162（9 处调用改为 eval 入口，净增 0），eval 点位 36 → **45**。
PARSE_CHECK_BUDGET = 162
# 2026-11-11 S4-3 一片：ct_validate_loop_exit/ct_diag_emit 吸收进 check 语句
# 语义动作（sem_break/sem_continue/sem_stmt_diag），77 → 75。
# S4-3 二片：布局/依赖/枚举/签名门面下沉，75 → 49。
# S4-3 三片：展开簿记门面下沉，49 → 31。
# S4-3 四片：全局聚合建模/声明收尾门面下沉，31 → 9。
# S4-3 五片：$-调用求值门面下沉，9 → 0（S4-3 目标形态达成；parse 不再 import
# comptime）。parse→check 随 S4-4 删 A 类 47 后净降约 126。
PARSE_COMPTIME_BUDGET = 0

# S4-4 类别计数（§4e 施工普查）：表达式内联语义是改版要删掉的 A 类——
# postfix 链 sem_*、调用 ABI（sem_call*/sem_push_arg）、字面量/成员元查询。
# 现在锁定只减不增（47 → 39，二元层已迁 eval），改版落地后达标线为 0；语句/
# 声明/类型级的 sem_can_assign、绑定登记不在 A 类（它们永久留在 parse）。
EXPR_SEM_SYMBOLS = (
    "sem_binop", "sem_unary", "sem_cast", "sem_sizeof", "sizeof_type_path",
    "sem_member", "sem_index", "sem_slice", "sem_ident", "sem_ident_val",
    "sem_number", "sem_string", "sem_char", "sem_raw_string",
    "sem_struct_lit_field", "sem_field_meta_name", "sem_enum_meta_name",
    "sem_enum_meta_value", "sem_call_begin", "sem_push_arg", "sem_call",
)
# 表达式语义只发生在这三个文件；parse_type 的 sizeof_type_path 是类型语法，
# 归 B 类（总数预算覆盖）。
EXPR_SEM_FILES = ("parse_expr", "parse_interp", "parse_comptime")
PARSE_CHECK_EXPR_INLINE_BUDGET = 0
# 语句级 eval 点位（§4e 普查原估 ≈20 处；实测见下）：改版前为 0，改版后 parse 只保留
# 这些入口级语义调用。
# 实测点位——按**调用点**计数：
# S4-4（表达式层，36）：二元/一元/postfix 各 1（parse 内共享 helper）、调用 ABI 3 段式
#   各 1（`$assert` 降级 4 个实参、插值 2 处）、字面量/名字/sizeof 按原始书写点各 1。
# S4-2 语句侧（9）：`sem_eval_break`/`sem_eval_continue`/`sem_eval_goto`/
#   `sem_eval_deflabel`/`sem_eval_assign`/`sem_eval_stmt_diag`/`sem_eval_return` 各 1、
#   `sem_eval_local_bind` 2（for-in 元素与索引）。
PARSE_CHECK_EVAL_BUDGET = 45

# 类型/符号表在 table（ADR-0027），项目绑定在 proj（ADR-0024）；旧名
# `support.*` 已随拆分消失，模式必须跟着新模块名，否则守卫形同虚设。
TYPE_TABLE_LOOKUPS = (
    r"table\.ty_lookup_name",
    r"proj\.mod_file_binding",
    r"proj\.mod_ns_lookup",
    r"table\.ms\(\)\.types",
)


def strip_comments(text: str) -> str:
    """剥离块注释与行注释，避免文档里的名字影响预算。"""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def module_sources(name: str):
    """返回某模块目录下全部 .yh 源码（递归）。"""
    return sorted((COMPILER / name).rglob("*.yh"))


def count_references(name: str, pattern: str) -> int:
    """统计模块源码中的正则引用数（已剥离注释）。"""
    matcher = re.compile(pattern)
    return sum(len(matcher.findall(strip_comments(p.read_text(encoding="utf-8"))))
               for p in module_sources(name))


def imports_of(name: str) -> set[str]:
    """收集模块所有文件的 import 目标（只取模块名首段）。"""
    targets: set[str] = set()
    matcher = re.compile(r"^import\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
    for path in module_sources(name):
        targets.update(matcher.findall(path.read_text(encoding="utf-8")))
    return targets


def check_parse_budget() -> None:
    """parse 的语义引用只减不增（总数 + 表达式内联 A 类 + eval 点位）。"""
    check_refs = count_references("parse", r"\bcheck\.\w+")
    comptime_refs = count_references("parse", r"\bcomptime\.\w+")
    assert check_refs <= PARSE_CHECK_BUDGET, (
        f"parse -> check 引用 {check_refs} 超过基线 {PARSE_CHECK_BUDGET}")
    assert comptime_refs <= PARSE_COMPTIME_BUDGET, (
        f"parse -> comptime 引用 {comptime_refs} 超过基线 {PARSE_COMPTIME_BUDGET}")
    expr_inline = 0
    eval_refs = 0
    matcher = re.compile(r"\bcheck\.\w+")
    for path in module_sources("parse"):
        text = strip_comments(path.read_text(encoding="utf-8"))
        if path.stem in EXPR_SEM_FILES:
            expr_inline += sum(len(re.findall(rf"check\.{sym}\b", text))
                               for sym in EXPR_SEM_SYMBOLS)
        # eval 点位按前缀统计：{sem_eval_node, sem_eval_local, sem_eval_bin, …}——
        # 新增的驱动入口不能被正则漏掉（S4-4 曾漏记 `sem_eval_local`，eval=0 假绿）。
        eval_refs += len(re.findall(r"check\.sem_eval_\w+", text))
    assert expr_inline <= PARSE_CHECK_EXPR_INLINE_BUDGET, (
        f"parse 表达式内联语义引用 {expr_inline} 超过基线 "
        f"{PARSE_CHECK_EXPR_INLINE_BUDGET}（S4-4 改版后应为 0）")
    assert eval_refs <= PARSE_CHECK_EVAL_BUDGET, (
        f"parse 语句级 eval 点位 {eval_refs} 超过预算 {PARSE_CHECK_EVAL_BUDGET}")
    print(f"PASS parse 语义引用预算：check={check_refs} comptime={comptime_refs} "
          f"表达式内联={expr_inline} eval={eval_refs}")


def check_parse_type_table_free() -> None:
    """类型解析已外置：parse_type 不再直接读类型/符号表。"""
    path = COMPILER / "parse" / "parse_type.yh"
    text = strip_comments(path.read_text(encoding="utf-8"))
    for pattern in TYPE_TABLE_LOOKUPS:
        assert re.search(pattern, text) is None, (
            f"parse/parse_type.yh 仍直接调用 {pattern}；应走 check.type_* 窄口")
    print("PASS parse_type 不含直接类型/符号表查询")


def check_module_edges() -> None:
    """锁定已完成的模块依赖方向。"""
    types_imports = imports_of("types")
    forbidden = types_imports & {"support", "table", "proj", "parse", "check",
                                 "ast", "comptime", "lower", "build"}
    assert not forbidden, f"types 出现上层依赖：{sorted(forbidden)}"
    table_imports = imports_of("table")
    forbidden = table_imports & {"proj", "parse", "check", "ast", "comptime",
                                 "lower", "build"}
    assert not forbidden, f"table 出现上层依赖：{sorted(forbidden)}"
    ast_imports = imports_of("ast")
    assert "check" not in ast_imports, "ast 不得 import check（AST 必须保持无检查依赖）"
    support_imports = imports_of("support")
    forbidden = support_imports & {"parse", "check", "comptime", "ast", "lower", "build"}
    assert not forbidden, f"support 出现上层反向依赖：{sorted(forbidden)}"
    comptime_imports = imports_of("comptime")
    forbidden = comptime_imports & {"check", "ast", "parse", "lower"}
    assert not forbidden, f"comptime 出现反向依赖：{sorted(forbidden)}"
    lower_imports = imports_of("lower")
    assert "parse" not in lower_imports, "lower 不得 import parse（只消费 check）"
    print("PASS 模块依赖方向：types/table/ast/support/comptime/lower")


def main() -> int:
    """运行全部守卫；任一失败返回 1。"""
    try:
        check_parse_budget()
        check_parse_type_table_free()
        check_module_edges()
    except AssertionError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print("front-coupling: 4/4 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
