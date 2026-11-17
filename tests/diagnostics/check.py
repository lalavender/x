#!/usr/bin/env python3
"""tests/diagnostics —— 编译诊断基线扫描与 V 风格片段夹具校验。

本工具是「V 风格编译诊断」D0/D1/D2 的观测门（方案见
docs/01-finished/yh-V风格诊断-D0-D2-2026-11-15.md）。它只读编译器的 stderr，
不改编译器，也不接入 `just test` 的阻断链（方案 §6 D0 的要求）。

两种模式：

    # 语料基线：遍历 tests/yh-run/fail 全部用例，统计「有源码片段 / 有 caret /
    # 列号落在行尾 / 跨文件」四项指标，可选写出 Markdown 快照。
    python3 tests/diagnostics/check.py --compiler ./yh \\
        --corpus tests/yh-run/fail --snapshot tests/diagnostics/baseline.md

    # 夹具断言：tests/diagnostics/cases/*.yh 必须按同名 .expect 断言
    # 头行行列、caret 起始显示列、下划线宽度与片段行数。
    python3 tests/diagnostics/check.py --compiler ./yh --cases

`.expect` 文件格式（逐行 `键: 值`，`#` 开头为注释；键可只写其中几条）：

    head: 3:17          # 头行必须报第 3 行第 17 列
    caret-col: 17       # caret 在「源行文本」内的 1 基显示列（不含行号栏）
    caret-width: 1      # 下划线可见宽度（1 是 `^`，其余是 `~`）
    snippet-lines: 5    # 片段显示的源码行数

退出码：语料基线恒为 0（除非编译器不可用）；`--max-line-end N` 给定时
超阈值返回 1；`--cases` 有任一夹具不符返回 1。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # tests/diagnostics
ROOT = HERE.parent.parent                       # 仓库根
DEFAULT_COMPILER = ROOT / "yh"
DEFAULT_CORPUS = ROOT / "tests" / "yh-run" / "fail"
DEFAULT_CASES = HERE / "cases"
DEFAULT_WORK = ROOT / "tmp" / "diagnostics-work"

# 头行：path:line:col: 错误|警告: 文案（经典格式，脚本正则沿用不改）
HEAD_RE = re.compile(r"^(?P<path>.+?):(?P<line>\d+):(?P<col>\d+): "
                     r"(?P<kind>错误|警告): (?P<msg>.*)$")
# 片段行：`    3 |     let x int = "s"`（行号栏 + ` | ` 分隔）
GUTTER_RE = re.compile(r"^\s*(?P<num>\d+) \| (?P<text>.*)$")
# caret 行：`      |                 ~~~`（无行号，仅行号栏宽的空格 + `| `）
CARET_RE = re.compile(r"^\s*\| (?P<pad> *)(?P<mark>[\^~]+)\s*$")
# 说明行：`  说明: …`（D4 起；缩进固定 2 空格）
NOTE_RE = re.compile(r"^\s{2}说明: (?P<text>.*)$")
COMPILE_TIMEOUT = 60


def display_width(text):
    """返回一段文本的终端可见宽度（tab=4、CJK/全角=2、组合字符=0）。

    与编译器 errors 渲染器的换算规则一致，用于把 caret-col 断言写成
    「人眼看到的列」，避免测试里手算字节偏移。
    """
    width = 0
    for ch in text:
        if ch == "\t":
            width += 4
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            width += 0
        else:
            width += char_width(ch)
    return width


def char_width(ch):
    """单个字符的可见宽度：组合字符 0、CJK/全角 2、其余 1。"""
    cp = ord(ch)
    if 0x0300 <= cp <= 0x036F or 0x200B <= cp <= 0x200F or 0xFE00 <= cp <= 0xFE0F:
        return 0
    if (0x1100 <= cp <= 0x115F or 0x2E80 <= cp <= 0xA4CF
            or 0xAC00 <= cp <= 0xD7A3 or 0xF900 <= cp <= 0xFAFF
            or 0xFE30 <= cp <= 0xFE6F or 0xFF00 <= cp <= 0xFF60
            or 0xFFE0 <= cp <= 0xFFE6 or 0x20000 <= cp <= 0x3FFFD):
        return 2
    return 1


def compile_file(compiler, src, out):
    """编译一个 .yh 文件（预期失败），返回 stderr 文本；超时返回 None。"""
    cmd = [str(compiler), str(src), "-o", str(out)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              errors="replace", timeout=COMPILE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None
    return proc.stderr


def read_source_line(path, line):
    """读源码的第 line 行（1 基），返回去掉 CR 的文本；越界返回 None。"""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    lines = data.split(b"\n")
    if line < 1 or line > len(lines):
        return None
    return lines[line - 1].rstrip(b"\r").decode("utf-8", "replace")


def parse_diag(stderr):
    """把一段 stderr 解析成 {heads, snippet, carets, notes} 结构。"""
    heads = []
    snippet_lines = []
    carets = []
    notes = []
    for raw in (stderr or "").splitlines():
        m = HEAD_RE.match(raw)
        if m:
            heads.append({"path": m.group("path"), "line": int(m.group("line")),
                          "col": int(m.group("col")), "kind": m.group("kind"),
                          "msg": m.group("msg")})
            continue
        m = GUTTER_RE.match(raw)
        if m:
            snippet_lines.append({"num": int(m.group("num")), "text": m.group("text")})
            continue
        m = CARET_RE.match(raw)
        if m:
            carets.append({"pad": len(m.group("pad")), "width": len(m.group("mark"))})
            continue
        m = NOTE_RE.match(raw)
        if m:
            notes.append(m.group("text"))
    return {"heads": heads, "snippet": snippet_lines, "carets": carets,
            "notes": notes}


def char_at(path, line, col):
    """返回头行列号指向的字符（列号是 1 基字节列）；越界返回空串。"""
    text = read_source_line(path, line)
    if text is None:
        return ""
    data = text.encode("utf-8")
    idx = col - 1
    if idx < 0 or idx >= len(data):
        return ""
    return data[idx:idx + 1].decode("utf-8", "replace")


def analyze_case(compiler, case, out):
    """分析单个 fail 用例：片段/caret/列号是否越过行尾/是否跨文件。

    `past_end` 统计「列号越出行尾」的用例（col > 行宽，即 caret 落在最后一个
    `past_end` 统计「列号越出行尾」的用例（col > 行宽，即 caret 落在最后一个
    字节之后）；`tail_char` 是「列号正好等于行宽」的用例，caret 落在行末字符上；
    `tail_paren` 是其中「末字符是 `)`」的那部分——caret 指在调用右括号上通常
    不是理想落点，单独计数以便收敛（脚本判定，不靠人工数）。
    """
    stderr = compile_file(compiler, case, out)
    info = {"case": case.name, "timeout": stderr is None, "heads": 0,
            "snippet": False, "caret": False, "past_end": False,
            "tail_char": False, "tail_paren": False, "col": "", "line_len": "",
            "at": "", "cross_file": False}
    if stderr is None:
        return info
    diag = parse_diag(stderr)
    info["heads"] = len(diag["heads"])
    info["snippet"] = bool(diag["snippet"])
    info["caret"] = bool(diag["carets"])
    if not diag["heads"]:
        return info
    head = diag["heads"][0]
    info["col"] = head["col"]
    info["cross_file"] = os.path.abspath(head["path"]) != os.path.abspath(case)
    text = read_source_line(head["path"], head["line"])
    if text is None:
        info["at"] = "<行号越界>"
        return info
    byte_len = len(text.encode("utf-8"))
    info["line_len"] = byte_len
    info["past_end"] = head["col"] > byte_len
    info["tail_char"] = head["col"] == byte_len
    info["at"] = char_at(head["path"], head["line"], head["col"]) or "<行尾>"
    info["tail_paren"] = info["tail_char"] and info["at"] == ")"
    return info


def corpus_scan(args):
    """遍历语料目录，打印统计并可选写 Markdown 快照；返回 (结果行, 汇总)。"""
    cases = sorted(DEFAULT_CORPUS.glob("*.yh")) if args.corpus == DEFAULT_CORPUS \
        else sorted(Path(args.corpus).glob("*.yh"))
    if not cases:
        print(f"没有找到用例：{args.corpus}", file=sys.stderr)
        return [], {}
    args.work.mkdir(parents=True, exist_ok=True)
    results = []
    for case in cases:
        results.append(analyze_case(args.compiler, case, args.work / case.stem))
    total = len(results)
    summary = {
        "total": total,
        "snippet": sum(1 for r in results if r["snippet"]),
        "caret": sum(1 for r in results if r["caret"]),
        "past_end": sum(1 for r in results if r["past_end"]),
        "tail_char": sum(1 for r in results if r["tail_char"]),
        "tail_paren": sum(1 for r in results if r["tail_paren"]),
        "cross_file": sum(1 for r in results if r["cross_file"]),
        "no_head": sum(1 for r in results if r["heads"] == 0),
        "timeout": sum(1 for r in results if r["timeout"]),
    }
    return results, summary


def print_corpus(results, summary):
    """打印语料扫描结果（稳定顺序、无时间戳）。"""
    for r in results:
        flags = []
        flags.append("片段" if r["snippet"] else "--")
        flags.append("caret" if r["caret"] else "--")
        if r["past_end"]:
            flags.append("越界")
        elif r["tail_char"]:
            flags.append("末字符")
        print(f"{r['case']:44s} {' '.join(flags):16s} "
              f"col={r['col']} 行宽={r['line_len']} 处={r['at']}")
    total = summary.get("total", 0)
    if not total:
        return
    print("-" * 78)
    print(f"失败语料: {total}")
    print(f"带源码片段: {summary['snippet']}")
    print(f"带 caret: {summary['caret']}")
    print(f"列号越出行尾(>行宽): {summary['past_end']}/{total} "
          f"({summary['past_end'] * 100.0 / total:.1f}%)")
    print(f"列号=行宽(指向末字符): {summary['tail_char']}"
          f"（其中落在 `)` 上: {summary['tail_paren']}）")
    print(f"跨文件头: {summary['cross_file']}")
    print(f"无位置头: {summary['no_head']}  超时: {summary['timeout']}")


def write_snapshot(path, results, summary):
    """把扫描结果写成 Markdown 快照（固定格式，便于 git diff 审阅）。"""
    total = summary["total"]
    lines = [
        "# 编译诊断基线快照",
        "",
        "由 `python3 tests/diagnostics/check.py --snapshot` 生成，请勿手改；",
        "重新生成命令见 [README.md](README.md)。",
        "",
        "## 汇总",
        "",
        f"- 失败语料: {total}",
        f"- 带源码片段: {summary['snippet']}",
        f"- 带 caret: {summary['caret']}",
        f"- 列号越出行尾(>行宽): {summary['past_end']}/{total} "
        f"({summary['past_end'] * 100.0 / total:.1f}%)" if total
        else "- 列号越出行尾(>行宽): 0/0",
        f"- 列号=行宽(指向末字符): {summary['tail_char']}"
        f"（其中落在 `)` 上: {summary['tail_paren']}）",
        f"- 跨文件头: {summary['cross_file']}",
        f"- 无位置头: {summary['no_head']}",
        "",
        "## 逐用例",
        "",
        "| 用例 | 片段 | caret | col | 行宽 | 列号处字符 |",
        "| --- | --- | --- | ---: | ---: | --- |"
    ]
    for r in results:
        lines.append(f"| {r['case']} | {'是' if r['snippet'] else '否'} | "
                     f"{'是' if r['caret'] else '否'} | {r['col']} | "
                     f"{r['line_len']} | {r['at']} |")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def parse_expect(path):
    """解析 .expect 文件为字典（键见模块文档）。"""
    expect = {}
    if not path.is_file():
        return expect
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        expect[key.strip()] = value.strip()
    return expect


def check_case(compiler, case, work):
    """校验一个夹具，返回问题列表（空即通过）。"""
    problems = []
    expect_path = case.with_suffix(".expect")
    expect = parse_expect(expect_path)
    if not expect:
        return [f"{case.name}: 缺少 {expect_path.name} 断言文件"]
    stderr = compile_file(compiler, case, work / case.stem)
    if stderr is None:
        return [f"{case.name}: 编译超时"]
    diag = parse_diag(stderr)
    if not diag["heads"]:
        return [f"{case.name}: 没有诊断头行（输出 {stderr.splitlines()[:1]}）"]
    head = diag["heads"][0]
    if "head" in expect:
        want_line, want_col = (int(x) for x in expect["head"].split(":"))
        if (head["line"], head["col"]) != (want_line, want_col):
            problems.append(f"{case.name}: 头行期望 {want_line}:{want_col}，"
                            f"实际 {head['line']}:{head['col']}")
    if not diag["snippet"]:
        problems.append(f"{case.name}: 没有源码片段")
    if "snippet-lines" in expect:
        want = int(expect["snippet-lines"])
        if len(diag["snippet"]) != want:
            problems.append(f"{case.name}: 片段行数期望 {want}，实际 {len(diag['snippet'])}")
    if not diag["carets"]:
        problems.append(f"{case.name}: 没有 caret 行")
        return problems
    caret = diag["carets"][0]
    source_line = next((s for s in diag["snippet"] if s["num"] == head["line"]), None)
    if source_line is None:
        problems.append(f"{case.name}: 片段里没有出错行 {head['line']}")
        return problems
    prefix_width = display_width(source_line["text"][:caret["pad"]]
                                 if caret["pad"] <= len(source_line["text"])
                                 else source_line["text"])
    if "caret-col" in expect:
        want = int(expect["caret-col"])
        if prefix_width + 1 != want:
            problems.append(f"{case.name}: caret 起始列期望 {want}，"
                            f"实际 {prefix_width + 1}")
    if "caret-width" in expect:
        want = int(expect["caret-width"])
        if caret["width"] != want:
            problems.append(f"{case.name}: 下划线宽度期望 {want}，实际 {caret['width']}")
    if "note-contains" in expect:
        want = expect["note-contains"]
        if not any(want in note for note in diag["notes"]):
            problems.append(f"{case.name}: 说明行应包含 {want!r}，实际 {diag['notes']}")
    return problems


def check_project_case(compiler, case_dir, work):
    """校验一个多文件项目夹具：复制到工作目录后 build，断言诊断头与片段来源。

    复制是为了不在 tests/ 里留下项目构建产物（.build）；断言重点是「头行文件
    与片段内容都属于出错的那个文件」，也就是跨文件时不显示错文件/错行。
    """
    problems = []
    expect = parse_expect(case_dir / ".expect")
    if not expect:
        return [f"{case_dir.name}: 缺少 .expect 断言文件"]
    target = work / case_dir.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(case_dir, target)
    # command 缺省 build；`test` 用于验收 `yh test` 的诊断也带片段
    command = expect.get("command", "build")
    try:
        proc = subprocess.run([str(compiler), command], cwd=str(target),
                              capture_output=True, text=True, errors="replace",
                              timeout=COMPILE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return [f"{case_dir.name}: 构建超时"]
    diag = parse_diag(proc.stderr)
    if not diag["heads"]:
        return [f"{case_dir.name}: 没有诊断头行（输出 {proc.stderr.splitlines()[:1]}）"]
    head = diag["heads"][0]
    want_file = expect.get("head-file")
    if want_file:
        head = next((h for h in diag["heads"]
                     if os.path.basename(h["path"]) == want_file), diag["heads"][0])
        if os.path.basename(head["path"]) != want_file:
            problems.append(f"{case_dir.name}: 头行文件期望 {want_file}，"
                            f"实际 {head['path']}")
    if "head" in expect:
        want_line, want_col = (int(x) for x in expect["head"].split(":"))
        if (head["line"], head["col"]) != (want_line, want_col):
            problems.append(f"{case_dir.name}: 头行期望 {want_line}:{want_col}，"
                            f"实际 {head['line']}:{head['col']}")
    if "snippet-contains" in expect:
        want = expect["snippet-contains"]
        texts = [s["text"] for s in diag["snippet"]]
        if not any(want in text for text in texts):
            problems.append(f"{case_dir.name}: 片段应包含 {want!r}，实际 {texts}")
    if "note-contains" in expect:
        want = expect["note-contains"]
        if not any(want in note for note in diag["notes"]):
            problems.append(f"{case_dir.name}: 说明行应包含 {want!r}，实际 {diag['notes']}")
    if not diag["carets"]:
        problems.append(f"{case_dir.name}: 没有 caret 行")
    return problems



def color_check(compiler, case):
    """颜色开关验收（D5）：管道默认无色、YH_DIAG_COLOR=always 有色、NO_COLOR 无色。"""
    problems = []
    base = dict(os.environ)
    base.pop("YH_DIAG_COLOR", None)
    base.pop("NO_COLOR", None)

    def run(env):
        proc = subprocess.run([str(compiler), str(case), "-o", str(Path("tmp") / "diag-color")],
                              capture_output=True, text=True, errors="replace",
                              timeout=COMPILE_TIMEOUT, env=env)
        return proc.stderr

    piped = run(base)
    if "\x1b[" in piped:
        problems.append("管道输出不应含 ANSI 转义（默认无颜色）")
    forced = dict(base)
    forced["YH_DIAG_COLOR"] = "always"
    if "\x1b[" not in run(forced):
        problems.append("YH_DIAG_COLOR=always 应输出 ANSI 着色")
    # 显式 always 优先于 NO_COLOR（覆盖链：always > NO_COLOR > isatty）
    forced_nc = dict(forced)
    forced_nc["NO_COLOR"] = "1"
    if "\x1b[" not in run(forced_nc):
        problems.append("YH_DIAG_COLOR=always 应优先于 NO_COLOR")
    nocolor = dict(base)
    nocolor["NO_COLOR"] = "1"
    if "\x1b[" in run(nocolor):
        problems.append("NO_COLOR=1 时不应着色")
    return problems
def corpus_expect_check(compiler, work):
    """按 corpus-expect.txt 校验语料里的大用例（不复制文件进 cases/）。

    每行 `用例名 | 键=值 | …`；支持 head-regex / snippet-contains / note-contains。
    """
    path = HERE / "corpus-expect.txt"
    if not path.is_file():
        return []
    work.mkdir(parents=True, exist_ok=True)
    problems = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        case = DEFAULT_CORPUS / parts[0]
        if not case.is_file():
            problems.append(f"语料期望: 找不到用例 {parts[0]}")
            continue
        stderr = compile_file(compiler, case, work / case.stem)
        if stderr is None:
            problems.append(f"{parts[0]}: 编译超时")
            continue
        diag = parse_diag(stderr)
        first_line = stderr.splitlines()[0] if stderr else ""
        for spec in parts[1:]:
            key, _, value = spec.partition("=")
            key = key.strip()
            value = value.strip()
            if key == "head-regex":
                if re.search(value, first_line) is None:
                    problems.append(f"{parts[0]}: 头行不匹配 {value!r}，实际 {first_line!r}")
            elif key == "snippet-contains":
                texts = [s["text"] for s in diag["snippet"]]
                if not any(value in text for text in texts):
                    problems.append(f"{parts[0]}: 片段应包含 {value!r}，实际 {texts}")
            elif key == "note-contains":
                if not any(value in note for note in diag["notes"]):
                    problems.append(f"{parts[0]}: 说明行应包含 {value!r}，实际 {diag['notes']}")
    return problems


def cases_check(args):
    """校验 cases/ 下的单文件夹具与项目夹具，返回问题列表。"""
    root = Path(args.cases)
    cases = sorted(root.glob("*.yh"))
    projects = sorted(d for d in root.iterdir()
                      if d.is_dir() and (d / "project.toml").is_file()) if root.is_dir() else []
    if not cases and not projects:
        print(f"没有找到夹具：{args.cases}", file=sys.stderr)
        return []
    args.work.mkdir(parents=True, exist_ok=True)
    problems = []
    for case in cases:
        problems.extend(check_case(args.compiler, case, args.work))
    for project in projects:
        problems.extend(check_project_case(args.compiler, project, args.work))
    problems.extend(corpus_expect_check(args.compiler, args.work))
    return problems


def main():
    parser = argparse.ArgumentParser(description="编译诊断基线扫描 / 夹具校验")
    parser.add_argument("--compiler", default=str(DEFAULT_COMPILER),
                        help="yh 编译器路径（缺省仓库根 yh）")
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS),
                        help="失败语料目录（缺省 tests/yh-run/fail）")
    parser.add_argument("--cases", nargs="?", const=str(DEFAULT_CASES),
                        help="改为校验夹具目录（缺省 tests/diagnostics/cases）")
    parser.add_argument("--snapshot", help="把语料扫描结果写成 Markdown 快照")
    parser.add_argument("--max-line-end", type=int,
                        help="「列号落在行尾」用例数上限；超出返回 1")
    parser.add_argument("--max-tail-paren", type=int,
                        help="「列号 = 行宽且末字符是 `)`」用例数上限；超出返回 1")
    parser.add_argument("--color-check", action="store_true",
                        help="改为验收颜色开关（管道无色 / always 有色 / NO_COLOR 无色）")
    parser.add_argument("--work", default=str(DEFAULT_WORK), help="中间产物目录")
    parser.add_argument("--quiet", action="store_true", help="只打印汇总")
    args = parser.parse_args()
    # 绝对化：Path("./yh") 会退化成 "yh"，subprocess 走 PATH 查找而找不到
    args.compiler = Path(args.compiler).resolve()
    args.work = Path(args.work).resolve()
    if not args.compiler.exists():
        print(f"编译器不存在：{args.compiler}", file=sys.stderr)
        return 2
    if args.cases is not None:
        problems = cases_check(args)
        for problem in problems:
            print("FAIL " + problem)
        print(f"夹具: {len(sorted(Path(args.cases).glob('*.yh')))} 个，"
              f"问题 {len(problems)} 个")
        return 1 if problems else 0
    if args.color_check:
        case = Path(args.cases or DEFAULT_CASES) / "note-assign.yh"
        problems = color_check(args.compiler, case)
        for problem in problems:
            print("FAIL " + problem)
        print(f"颜色开关: 检查 {case.name}，问题 {len(problems)} 个")
        return 1 if problems else 0
    results, summary = corpus_scan(args)
    if not results:
        return 2
    if not args.quiet:
        print_corpus(results, summary)
    else:
        print(f"失败语料: {summary['total']}  片段: {summary['snippet']}  "
              f"caret: {summary['caret']}  越界: {summary['past_end']}  "
              f"末字符: {summary['tail_char']}  tail_paren: {summary['tail_paren']}  "
              f"跨文件: {summary['cross_file']}")
    if args.snapshot:
        write_snapshot(args.snapshot, results, summary)
        print(f"快照已写入: {args.snapshot}")
    if args.max_line_end is not None and summary["past_end"] > args.max_line_end:
        print(f"FAIL 列号越出行尾 {summary['past_end']} > 上限 {args.max_line_end}")
        return 1
    if args.max_tail_paren is not None and summary["tail_paren"] > args.max_tail_paren:
        print(f"FAIL 末字符 `)` {summary['tail_paren']} > 上限 {args.max_tail_paren}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
