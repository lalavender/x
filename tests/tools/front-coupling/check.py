#!/usr/bin/env python3
"""前端耦合守卫：锁定 S4 切片已建立的依赖方向与只减不增预算。

检查项（全部按代码行统计，先剥离注释）：

1. `parse` 对 `check.` / `comptime.` 的引用数不得超过基线（只减不增）。
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
PARSE_CHECK_BUDGET = 161
PARSE_COMPTIME_BUDGET = 77

TYPE_TABLE_LOOKUPS = (
    r"support\.ty_lookup_name",
    r"support\.mod_file_binding",
    r"support\.mod_ns_lookup",
    r"support\.ms\(\)\.types",
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
    """parse 的语义引用只减不增。"""
    check_refs = count_references("parse", r"\bcheck\.\w+")
    comptime_refs = count_references("parse", r"\bcomptime\.\w+")
    assert check_refs <= PARSE_CHECK_BUDGET, (
        f"parse -> check 引用 {check_refs} 超过基线 {PARSE_CHECK_BUDGET}")
    assert comptime_refs <= PARSE_COMPTIME_BUDGET, (
        f"parse -> comptime 引用 {comptime_refs} 超过基线 {PARSE_COMPTIME_BUDGET}")
    print(f"PASS parse 语义引用预算：check={check_refs} comptime={comptime_refs}")


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
    print("PASS 模块依赖方向：ast/support/comptime/lower")


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
