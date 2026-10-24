#!/usr/bin/env python3
"""用固定 yh 夹具验证代码统计工具的词法边界、汇总与命令行输出。"""

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools" / "yh-code-stats.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_tool():
    """加载正在被测试的真实统计脚本，避免引入测试依赖。"""
    spec = importlib.util.spec_from_file_location("yh_code_stats", TOOL)
    if spec is None or spec.loader is None:
        raise AssertionError(f"无法加载统计工具：{TOOL}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_counts(actual, physical, code, comments, blank, mixed, label):
    """核对物理行分类，确保混合行单列且不重复进入行数总和。"""
    expected = {
        "physical_lines": physical,
        "code_lines": code,
        "comment_lines": comments,
        "blank_lines": blank,
        "mixed_lines": mixed,
    }
    assert actual == expected, f"{label}: expected {expected}, got {actual}"
    assert physical == code + comments + blank, f"{label}: 行数恒等式不成立"


def test_fixture_boundaries(stats):
    """yh 字符串中的注释符不应改变词法状态，真实混合注释应单列。"""
    source = (FIXTURES / "boundaries.yh").read_text(encoding="utf-8")
    expect_counts(stats.scan_text(source), 13, 9, 4, 0, 4, "边界夹具")


def test_blank_lines_inside_comments(stats):
    """块注释中的纯空白行仍按空白行统计。"""
    source = (FIXTURES / "block-whitespace.yh").read_text(encoding="utf-8")
    expect_counts(stats.scan_text(source), 3, 0, 2, 1, 0, "块注释空白夹具")
    expect_counts(stats.scan_text("/*\n \t\n*/"), 3, 0, 2, 1, 0, "块注释空白字符")


def test_newlines_and_empty_input(stats):
    """空文件、CRLF、末尾换行和无末尾换行都遵循物理行定义。"""
    expect_counts(stats.scan_text(""), 0, 0, 0, 0, 0, "空文件")
    expect_counts(stats.scan_text("  \t\r\f\v\n"), 1, 0, 0, 1, 0, "空白行")
    expect_counts(stats.scan_text("let x int = 1;\r\n// 注释\r\n"),
                  2, 1, 1, 0, 0, "CRLF")
    expect_counts(stats.scan_text("let x int = 1; // 注释"),
                  1, 1, 0, 0, 1, "无末尾换行")


def test_unclosed_tokens_fail(stats):
    """未闭合块注释、字符串与字符必须报错，防止分类结果静默失真。"""
    invalid_files = ("invalid-block.yh", "invalid-string.yh")
    for name in invalid_files:
        source = (FIXTURES / name).read_text(encoding="utf-8")
        try:
            stats.scan_text(source, name)
        except stats.StatsError:
            continue
        raise AssertionError(f"{name} 应报告未闭合词法边界")
    for source in ("let x *char = 'a;",):
        try:
            stats.scan_text(source, "invalid-char.yh")
        except stats.StatsError:
            continue
        raise AssertionError("未闭合字符字面量应报错")


def test_tree_scope_and_module_totals(stats):
    """只统计源根下的 yh 文件，忽略缓存和符号链接，并自动发现新职责目录。"""
    temp_root = ROOT / "tmp"
    # 仓库 tmp 通常已存在；沙箱对已存在路径的 mkdir 会报 EEXIST，
    # 因此先判断再创建（exist_ok 在该环境下不可靠）。
    if not temp_root.is_dir():
        temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root, prefix="code-stats-",
                                    ignore_cleanup_errors=True) as tmp:
        source_root = Path(tmp)
        (source_root / "ast").mkdir()
        (source_root / "new_module").mkdir()
        (source_root / "tmp").mkdir()
        (source_root / ".build").mkdir()
        (source_root / "ast" / "a.yh").write_text("fn a() {}\n", encoding="utf-8")
        (source_root / "new_module" / "b.yh").write_text("// only comment\n", encoding="utf-8")
        (source_root / "new_module" / "lone-cr.yh").write_bytes(
            b"let one int = 1;\rlet two int = 2;"
        )
        (source_root / "tmp" / "ignored.yh").write_text("ignored\n", encoding="utf-8")
        (source_root / ".build" / "ignored.yh").write_text("ignored\n", encoding="utf-8")
        try:
            (source_root / "linked.yh").symlink_to(source_root / "ast" / "a.yh")
        except (OSError, NotImplementedError):
            pass

        report = stats.analyze_tree(source_root)
        assert report["totals"]["files"] == 3
        assert report["totals"]["physical_lines"] == 3
        assert [item["name"] for item in report["modules"]] == ["ast", "new_module"]
        assert report["modules"][0]["code_lines"] == 1
        assert report["modules"][1]["physical_lines"] == 2
        assert {item["path"] for item in report["files"]} == {
            "compiler/ast/a.yh", "compiler/new_module/b.yh",
            "compiler/new_module/lone-cr.yh",
        }
        output = io.StringIO()
        with redirect_stdout(output):
            stats.print_text(report, 2)
        rendered = output.getvalue()
        assert "大文件排行 Top 2" in rendered
        assert rendered.index("compiler/ast/a.yh") < rendered.index("compiler/new_module/b.yh")
        output = io.StringIO()
        with redirect_stdout(output):
            stats.print_text(report, 0)
        assert "大文件排行" not in output.getvalue()

        comment_root = source_root / "only-comments"
        (comment_root / "src").mkdir(parents=True)
        (comment_root / "src" / "blank.yh").write_text("// comment\n", encoding="utf-8")
        comment_report = stats.analyze_tree(comment_root)
        assert comment_report["totals"]["code_lines"] == 0
        assert comment_report["totals"]["comment_ratio"] == 1.0
        assert comment_report["modules"][0]["code_ratio"] is None

        empty_root = source_root / "empty"
        empty_root.mkdir()
        try:
            stats.analyze_tree(empty_root)
        except stats.StatsError as error:
            assert ".yh" in str(error)
        else:
            raise AssertionError("无 .yh 源文件时应拒绝生成空报告")

        (source_root / "ast" / "bad.yh").write_bytes(b"\xff")
        try:
            stats.analyze_tree(source_root)
        except stats.StatsError as error:
            assert "compiler/ast/bad.yh" in str(error)
        else:
            raise AssertionError("非法 UTF-8 应使整份统计失败")


def test_cli_json_is_deterministic(stats):
    """JSON 输出包含稳定 schema 和全量文件，且不受当前工作目录影响。"""
    command = [sys.executable, str(TOOL), "--format", "json", "--top", "0"]
    first = subprocess.run(command, cwd=ROOT / "docs", capture_output=True, text=True)
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout, "相同源码的 JSON 输出应稳定"
    report = json.loads(first.stdout)
    assert report["schema_version"] == 1
    assert report["totals"]["files"] == len(report["files"]) > 0
    assert sum(row["physical_lines"] for row in report["modules"]) == report["totals"]["physical_lines"]
    bad_top = subprocess.run(
        [sys.executable, str(TOOL), "--top", "-1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert bad_top.returncode == 2
    assert "非负整数" in bad_top.stderr


def main():
    """运行固定用例，首个失败断言会给出对应口径。"""
    stats = load_tool()
    tests = (
        test_fixture_boundaries,
        test_blank_lines_inside_comments,
        test_newlines_and_empty_input,
        test_unclosed_tokens_fail,
        test_tree_scope_and_module_totals,
        test_cli_json_is_deterministic,
    )
    for test in tests:
        test(stats)
        print(f"PASS {test.__name__}")
    print(f"{len(tests)}/{len(tests)} code statistics tests passed")


if __name__ == "__main__":
    main()
