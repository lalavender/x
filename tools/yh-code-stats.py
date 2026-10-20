#!/usr/bin/env python3
"""统计 yh 编译器各职责目录的 .yh 源码规模。"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler"
IGNORED_DIRS = {".build", ".git", "tmp"}
WHITESPACE = " \t\r\f\v"


class StatsError(Exception):
    """表示扫描范围、源码读取或词法边界错误。"""


def scan_text(text, source="<memory>"):
    """按 yh 注释和字面量边界统计一份源码的物理行分类。"""
    physical = text.split("\n") if text else []
    if physical and physical[-1] == "" and text.endswith("\n"):
        physical.pop()

    code_lines = 0
    comment_lines = 0
    blank_lines = 0
    mixed_lines = 0
    in_block = False
    block_start = 0

    for line_number, line in enumerate(physical, 1):
        has_code = False
        has_comment = False
        index = 0

        while index < len(line):
            if in_block:
                if line.startswith("*/", index):
                    has_comment = True
                    in_block = False
                    index += 2
                else:
                    if line[index] not in WHITESPACE:
                        has_comment = True
                    index += 1
                continue

            char = line[index]
            if char in WHITESPACE:
                index += 1
                continue
            if line.startswith("//", index):
                has_comment = True
                break
            if line.startswith("/*", index):
                has_comment = True
                in_block = True
                block_start = line_number
                index += 2
                continue
            if char in ('"', "'"):
                has_code = True
                quote = char
                index += 1
                while index < len(line):
                    if line[index] == "\\":
                        if index + 1 >= len(line):
                            raise StatsError(
                                f"{source}:{line_number}: 字面量末尾有不完整转义"
                            )
                        index += 2
                    elif line[index] == quote:
                        index += 1
                        break
                    else:
                        index += 1
                else:
                    label = "字符串" if quote == '"' else "字符"
                    raise StatsError(f"{source}:{line_number}: 未闭合{label}字面量")
                continue

            has_code = True
            index += 1

        if has_code:
            code_lines += 1
        elif has_comment:
            comment_lines += 1
        else:
            blank_lines += 1
        if has_code and has_comment:
            mixed_lines += 1

    if in_block:
        raise StatsError(f"{source}:{block_start}: 未闭合块注释")

    result = {
        "physical_lines": len(physical),
        "code_lines": code_lines,
        "comment_lines": comment_lines,
        "blank_lines": blank_lines,
        "mixed_lines": mixed_lines,
    }
    if result["physical_lines"] != code_lines + comment_lines + blank_lines:
        raise AssertionError("源码行分类不满足物理行恒等式")
    return result


def find_sources(source_root):
    """递归发现 .yh 源文件，跳过缓存目录与符号链接。"""
    source_root = Path(source_root)
    if not source_root.is_dir():
        raise StatsError(f"编译器源码目录不存在：{source_root}")

    sources = []

    def fail_walk(error):
        """将目录遍历错误转换为可读的工具诊断。"""
        raise StatsError(f"无法遍历源码目录：{error}")

    for directory, subdirs, filenames in os.walk(
        source_root, topdown=True, followlinks=False, onerror=fail_walk
    ):
        current = Path(directory)
        subdirs[:] = sorted(
            name
            for name in subdirs
            if name not in IGNORED_DIRS
            and not (current / name).is_symlink()
        )
        for filename in filenames:
            path = current / filename
            if path.suffix == ".yh" and not path.is_symlink():
                sources.append(path)

    return sorted(sources, key=lambda path: path.relative_to(source_root).as_posix())


def ratio(numerator, denominator):
    """计算可复现的四位小数比例；分母为零时返回 null。"""
    return None if denominator == 0 else round(numerator / denominator, 4)


def analyze_tree(source_root):
    """扫描源码树并生成可供文本及 JSON 共用的确定性报告。"""
    source_root = Path(source_root)
    sources = find_sources(source_root)
    if not sources:
        raise StatsError(f"没有在 {source_root} 中找到 .yh 源文件")

    file_rows = []
    modules = {}
    totals = {
        "files": 0,
        "physical_lines": 0,
        "code_lines": 0,
        "comment_lines": 0,
        "blank_lines": 0,
        "mixed_lines": 0,
    }

    for path in sources:
        relative = path.relative_to(source_root)
        module = relative.parts[0] if len(relative.parts) > 1 else "(root)"
        display_path = f"compiler/{relative.as_posix()}"
        try:
            with path.open("r", encoding="utf-8", newline="") as source:
                text = source.read()
        except (OSError, UnicodeError) as error:
            raise StatsError(f"{display_path}: 无法读取 UTF-8 源码：{error}") from error
        counts = scan_text(text, display_path)
        row = {"path": display_path, "module": module, **counts}
        file_rows.append(row)

        group = modules.setdefault(
            module,
            {
                "name": module,
                "files": 0,
                "physical_lines": 0,
                "code_lines": 0,
                "comment_lines": 0,
                "blank_lines": 0,
                "mixed_lines": 0,
            },
        )
        group["files"] += 1
        totals["files"] += 1
        for key in ("physical_lines", "code_lines", "comment_lines", "blank_lines", "mixed_lines"):
            group[key] += counts[key]
            totals[key] += counts[key]

    total_code = totals["code_lines"]
    for group in modules.values():
        group["code_ratio"] = ratio(group["code_lines"], total_code)
    totals["comment_ratio"] = ratio(
        totals["comment_lines"] + totals["mixed_lines"],
        totals["physical_lines"] - totals["blank_lines"],
    )

    module_rows = [modules[name] for name in sorted(modules)]
    return {
        "schema_version": 1,
        "scope": "compiler/**/*.yh（包含所有平台变体；按职责目录汇总）",
        "totals": totals,
        "modules": module_rows,
        "files": file_rows,
    }


def percent(value):
    """格式化比例；无定义的比例显示为横线。"""
    return "—" if value is None else f"{value:.1%}"


def print_text(report, top):
    """将统计报告输出为中文终端表格。"""
    totals = report["totals"]
    print("yh 编译器源码统计（compiler/ 下所有平台变体）")
    print(
        f"总计：{totals['files']} 个文件，{totals['physical_lines']} 行，"
        f"代码 {totals['code_lines']} 行，纯注释 {totals['comment_lines']} 行，"
        f"空白 {totals['blank_lines']} 行，混合 {totals['mixed_lines']} 行，"
        f"注释占比 {percent(totals['comment_ratio'])}"
    )
    print("\n职责目录分布（cmd/ 对应 module main）")
    print("目录              文件    代码    注释    空白    混合    总行  代码占比")
    for row in report["modules"]:
        print(
            f"{row['name']:<14} {row['files']:>5} {row['code_lines']:>7} "
            f"{row['comment_lines']:>7} {row['blank_lines']:>7} {row['mixed_lines']:>7} "
            f"{row['physical_lines']:>7} {percent(row['code_ratio']):>9}"
        )

    large_count = sum(row["physical_lines"] > 1000 for row in report["files"])
    print(f"\n超过 1,000 行的文件：{large_count}")
    if top:
        largest = sorted(
            report["files"],
            key=lambda row: (-row["physical_lines"], row["path"]),
        )[:top]
        print(f"\n大文件排行 Top {len(largest)}")
        print("文件                                      总行    代码")
        for row in largest:
            print(f"{row['path']:<42} {row['physical_lines']:>6} {row['code_lines']:>7}")


def nonnegative(value):
    """解析非负排行数量，并让 argparse 负责参数错误退出码。"""
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("必须是非负整数") from error
    if number < 0:
        raise argparse.ArgumentTypeError("必须是非负整数")
    return number


def main(argv=None):
    """解析命令行、执行完整扫描并输出单一格式的报告。"""
    parser = argparse.ArgumentParser(description="统计 yh 编译器 .yh 源码行数")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--top", type=nonnegative, default=10, help="文本报告中的大文件数量，0 隐藏排行")
    args = parser.parse_args(argv)
    try:
        report = analyze_tree(COMPILER)
    except StatsError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
