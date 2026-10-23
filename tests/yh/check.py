#!/usr/bin/env python3
"""tests/yh 语法语料校验。

默认（ANTLR 模式）：用语法文件 yh.g4 在临时目录生成 ANTLR parser，遍历
tests/yh/ 下全部 .yh 语料，要求每个文件都满足：零词法错误 + 零语法错误 +
解析消费到 EOF。

--compiler 模式：用本仓库构建的 yh 编译器（yh --syntax-check）跑同一批
语料。正例必须被接受，rejected/ 下的反例必须被拒绝。该模式不要求 Java
与 antlr4 运行时。

用法：
    python3 tests/yh/check.py              # ANTLR 模式校验全部语料
    python3 tests/yh/check.py --coverage   # ANTLR 模式 + 规则覆盖自检
    python3 tests/yh/check.py --compiler   # yh 编译器模式（--syntax-check）
    python3 tests/yh/check.py --compiler --compiler-path ./stage1
                                           # 指定编译器路径（自举差分）
    python3 tests/yh/check.py --compiler --jobs 4
                                           # 并发跑语料（缺省 min(8, CPU 核数)）
    python3 tests/yh/check.py --quiet      # 只打印失败项与汇总

ANTLR 模式的 parser 生成目录缺省在仓库 tmp/ 下（用 --workdir 覆盖），
用完即删。

退出码：全部通过 0；有失败或覆盖缺口 1。
"""

import argparse
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent          # tests/yh
ROOT = HERE.parent.parent                        # 仓库根

# 语法文件的候选位置（按顺序取第一个存在的）。仓库根与 docs/ 都支持，
# 这样语法文件挪位置时不必改脚本。
GRAMMAR_CANDIDATES = [ROOT / "yh.g4", ROOT / "docs" / "yh.g4"]


def find_grammar():
    for candidate in GRAMMAR_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


GRAMMAR = find_grammar()

# 装了 antlr4 运行时的解释器（本仓库约定的托管 venv）。
MANAGED_VENV = Path("/Users/lavender/.workbuddy-ai/binaries/python/envs/default")
MANAGED_PY = MANAGED_VENV / "bin/python3"

# antlr4 命令行工具（Python 包装脚本，底层需要 Java）。
ANTLR_CANDIDATES = [
    Path.home() / "Library/Python/3.9/bin/antlr4",
    Path.home() / ".local/bin/antlr4",
    Path("/opt/homebrew/bin/antlr4"),
    Path("/usr/local/bin/antlr4"),
]

# 本地 Maven 缓存里的 ANTLR 工具 jar。
M2_ANTLR = Path.home() / ".m2/repository/org/antlr/antlr4"

# 归一化判定用到的保留字与内建类型（与 compiler/lex/layout.yh 保持一致）。
KEYWORDS = set(
    "pub let const fn type struct union enum if else switch case default for in "
    "goto sizeof len as to_type test while do unsigned signed short long float double "
    "typedef extern static register auto inline volatile restrict module import".split()
)
BUILTIN_TYPES = set(
    "int i8 i16 i32 i64 u8 u16 u32 u64 f32 f64 bool char void".split()
)

HEADER_PREFIX = "// 覆盖规则："
RULE_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# 反例区：该目录下的 .yh 必须【解析失败】才算通过。
REJECTED_DIR = "rejected"
REJECTED_HEADER_PREFIX = "// 期望："


def die(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def ensure_runtime():
    """确保当前解释器能 import antlr4；否则用托管 venv 重新执行自己。

    注意：不能用 sys.executable 比对，因为 venv 的 bin/python3 是指向基础
    解释器的符号链接，resolve() 之后两者是同一个真实路径。用 sys.prefix 判断。
    """
    try:
        import antlr4  # noqa: F401
        return
    except ImportError:
        pass

    if not MANAGED_PY.exists():
        die(
            "缺少 antlr4 运行时。请安装后重试：\n"
            f"  {MANAGED_VENV}/bin/pip install antlr4-python3-runtime==4.13.2"
        )
    if Path(sys.prefix) == MANAGED_VENV:
        die(f"{MANAGED_VENV} 里也找不到 antlr4 运行时。")
    os.execv(str(MANAGED_PY), [str(MANAGED_PY), str(Path(__file__).resolve()), *sys.argv[1:]])


def find_antlr_tool():
    for candidate in ANTLR_CANDIDATES:
        if candidate.exists():
            return candidate
    die("找不到 antlr4 命令。请先安装：pip install antlr4-tools")


def pick_version():
    """挑本地 Maven 缓存里可用的最高版本，避开联网查询。"""
    if not M2_ANTLR.is_dir():
        die(f"找不到本地 ANTLR jar 缓存：{M2_ANTLR}\n先联网跑一次 antlr4 下载工具 jar。")
    versions = []
    for entry in M2_ANTLR.iterdir():
        if not entry.is_dir() or not re.fullmatch(r"\d+\.\d+\.\d+", entry.name):
            continue
        if (entry / f"antlr4-{entry.name}-complete.jar").exists():
            versions.append(entry.name)
    if not versions:
        die(f"{M2_ANTLR} 下没有任何 antlr4-<版本>-complete.jar")
    versions.sort(key=lambda v: tuple(int(p) for p in v.split(".")))
    return versions[-1]


def generate_parser(tool, version, workdir=None):
    """在临时目录生成 Python3 parser，返回该目录。

    workdir 缺省为仓库 tmp/ 下（生成物统一落在 tmp/，结束后删除）。
    """
    base = Path(workdir) if workdir else ROOT / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="yh-g4-", dir=base))
    shutil.copy(GRAMMAR, work / GRAMMAR.name)
    proc = subprocess.run(
        [str(tool), "-v", version, "-Dlanguage=Python3", "-no-listener", GRAMMAR.name],
        cwd=work,
        capture_output=True,
        text=True,
    )
    output = (proc.stdout + proc.stderr).strip()
    if output:
        shutil.rmtree(work, ignore_errors=True)
        die(f"ANTLR 生成 parser 时报告问题（应零警告）：\n{output}")
    for produced in ("yhLexer.py", "yhParser.py"):
        if not (work / produced).exists():
            shutil.rmtree(work, ignore_errors=True)
            die(f"ANTLR 未生成 {produced}，请检查 yh.g4。")
    return work


class ErrorCollector:
    """把词法/语法错误收集成 '行:列 消息' 列表，而不是抛异常。"""

    def __init__(self, sink):
        self.sink = sink

    def syntaxError(self, recognizer, offending, line, column, msg, exc):
        self.sink.append(f"{line}:{column} {msg}")


def load_parser(work):
    """把临时目录里的生成物 import 进来，返回 (lexer 类, parser 类, Token)。"""
    sys.path.insert(0, str(work))
    from antlr4 import Token  # noqa: E402
    from antlr4.Token import CommonToken  # noqa: E402
    from antlr4.ListTokenSource import ListTokenSource  # noqa: E402
    from antlr4 import CommonTokenStream, InputStream  # noqa: E402
    from antlr4.error.ErrorListener import ErrorListener  # noqa: E402
    from yhLexer import yhLexer  # noqa: E402
    from yhParser import yhParser  # noqa: E402

    # ANTLR 生成的监听器接口是鸭子类型，直接把收集器包装成 ErrorListener。
    class Collector(ErrorListener):
        def __init__(self, sink):
            super().__init__()
            self._c = ErrorCollector(sink)

        def syntaxError(self, recognizer, offending, line, column, msg, exc):
            self._c.syntaxError(recognizer, offending, line, column, msg, exc)

    return (InputStream, CommonTokenStream, Token, yhLexer, yhParser,
            Collector, CommonToken, ListTokenSource)


def can_end(text, before_text):
    """该 token 能否结束简单语句、字段或枚举成员（与 lex_can_end 同规则）。"""
    if before_text == ".":
        return True
    if text in BUILTIN_TYPES:
        return True
    if text in (")", "]", "}", "true", "false", "return", "break", "continue"):
        return True
    if text and (text[0].isalnum() or text[0] in "_\"'"):
        return text not in KEYWORDS
    return False


def normalize_tokens(raw, Token, semi_type, CommonToken, ListTokenSource):
    """按 compiler/lex/layout.yh 的规则把换行补成隐式 ';'，返回新的 token 流。

    括号/方括号内、属性组之后、行首 '{' 之前不补；显式 ';' 优先；
    '}' 前与 EOF 前补。行号取自 ANTLR 词法器，块注释里的换行同样生效。
    """
    visible = [t for t in raw
               if t.channel == Token.DEFAULT_CHANNEL and t.type != Token.EOF]
    pos = raw.index(raw[-1]) if raw else 0
    eof = raw[-1] if raw else None
    if eof is None:
        return None
    seq = visible + [eof]
    out = []
    parens = 0
    brackets = 0
    attribute_depth = -1
    closed_attribute = False
    for idx, tok in enumerate(seq):
        if idx:
            prev = seq[idx - 1]
            before = seq[idx - 2] if idx > 1 else None
            before_text = before.text if before is not None else ""
            is_eof = tok is eof
            boundary = is_eof or tok.line > prev.line or tok.text == "}"
            jump_end = (before_text != "." and
                        (prev.text in ("return", "break", "continue")
                         or before_text == "goto"))
            if (boundary and parens == 0 and brackets == 0
                    and not closed_attribute and tok.text != ";"
                    and (tok.text != "{" or jump_end)
                    and can_end(prev.text, before_text)):
                semi = CommonToken(type=semi_type)
                semi.text = ";"
                semi.line = prev.line
                semi.column = prev.column + len(prev.text)
                out.append(semi)
        out.append(tok)
        closed_attribute = False
        if tok.text == "(":
            parens += 1
        elif tok.text == ")" and parens > 0:
            parens -= 1
        elif tok.text == "[":
            brackets += 1
            if idx > 0 and seq[idx - 1].text == "@":
                attribute_depth = brackets
        elif tok.text == "]" and brackets > 0:
            if attribute_depth == brackets:
                closed_attribute = True
                attribute_depth = -1
            brackets -= 1
    return ListTokenSource(out)


def check_file(path, api):
    (InputStream, CommonTokenStream, Token, yhLexer, yhParser, Collector,
     CommonToken, ListTokenSource) = api
    text = path.read_text(encoding="utf-8")

    lex_errors = []
    lexer = yhLexer(InputStream(text))
    lexer.removeErrorListeners()
    lexer.addErrorListener(Collector(lex_errors))

    raw = CommonTokenStream(lexer)
    raw.fill()  # 强制全量词法，暴露文件尾部的词法错误

    semi_type = next((i for i, name in enumerate(yhParser.symbolicNames)
                      if name == "IMPLICIT"), None)
    if semi_type is None:
        die("参考语法缺少 IMPLICIT token，无法归一化换行终结符")
    source = normalize_tokens(raw.tokens, Token, semi_type, CommonToken,
                              ListTokenSource)
    tokens = CommonTokenStream(source)
    tokens.fill()

    parse_errors = []
    parser = yhParser(tokens)
    parser.removeErrorListeners()
    parser.addErrorListener(Collector(parse_errors))
    parser.sourceFile()

    reached_eof = tokens.LA(1) == Token.EOF
    ok = not lex_errors and not parse_errors and reached_eof
    problems = list(lex_errors) + list(parse_errors)
    if not reached_eof:
        problems.append("解析未消费到文件末尾（尾部有未解析内容）")
    return ok, problems


def read_covered_rules(path):
    """从首行注释头读出覆盖的规则名；首行缺失或格式不对则返回 None。"""
    first = path.read_text(encoding="utf-8").split("\n", 1)[0].strip()
    if not first.startswith(HEADER_PREFIX):
        return None
    return RULE_NAME_RE.findall(first[len(HEADER_PREFIX):])


def run_coverage(api, corpus_files):
    _, _, _, yhLexer, yhParser, _ = api
    # symbolicNames 里夹着 EOF 的占位名 '<INVALID>'，不是真实规则，要滤掉。
    declared = {n for n in yhParser.ruleNames if n and not n.startswith("<")}
    lexer_rules = {n for n in yhLexer.symbolicNames if n and not n.startswith("<")}
    all_rules = declared | lexer_rules

    covered, unknown, missing_header = set(), set(), []
    for path in corpus_files:
        names = read_covered_rules(path)
        if names is None:
            missing_header.append(path.relative_to(HERE))
            continue
        covered |= set(names)
        unknown |= set(names) - all_rules

    uncovered = all_rules - covered
    print(f"\n覆盖率：语料共 {len(corpus_files)} 个文件")
    print(f"  yh.g4 规则总数 {len(all_rules)}（parser {len(declared)} + lexer {len(lexer_rules)}）")
    print(f"  已覆盖 {len(covered & all_rules)}")
    if missing_header:
        print(f"  [FAIL] 缺少首行「{HEADER_PREFIX}」注释头：")
        for item in missing_header:
            print(f"         {item}")
    if unknown:
        print(f"  [FAIL] 注释头里出现 yh.g4 中不存在的规则名：{sorted(unknown)}")
    if uncovered:
        print(f"  [FAIL] 未被任何语料覆盖的规则：{sorted(uncovered)}")
    if not (missing_header or unknown or uncovered):
        print("  [OK] 全部规则均有语料覆盖，且无非法规则名")
        return True
    return False


YH_BIN = ROOT / "yh"


def run_compiler_mode(quiet, compiler=None, jobs=1):
    """编译器模式：yh --syntax-check 接受全部正例、拒绝全部反例。

    compiler 可指定编译器路径（自举差分时指向 stage1/stage2），
    缺省用仓库根的 yh。jobs > 1 时并发跑语料（每个文件一个独立进程）。
    传入的相对路径会先解析成绝对路径（subprocess 不带 cwd 时不查 PATH）。
    """
    yh_bin = Path(compiler).resolve() if compiler else YH_BIN
    if not yh_bin.exists():
        die(f"找不到编译器 {yh_bin}，请先 make")
    corpus_dir = HERE
    all_files = sorted(p for p in corpus_dir.rglob("*.yh") if p.is_file())
    rejected_root = corpus_dir / REJECTED_DIR
    positive = [p for p in all_files if rejected_root not in p.parents]
    negative = [p for p in all_files if rejected_root in p.parents]
    if not all_files:
        die(f"{corpus_dir} 下没有任何 .yh 语料。")
    if not quiet:
        print(f"编译器：{yh_bin}（--syntax-check，并发 {jobs}）")
        print(f"语料目录：{corpus_dir}")
        print(f"  正例 {len(positive)} 个 / 反例 {len(negative)} 个\n")

    def run_one(target):
        """跑一个语料，返回 (路径, 是否反例, 相对路径, 是否通过, 诊断)。"""
        path, is_negative = target
        proc = subprocess.run([str(yh_bin), "--syntax-check", str(path)],
                              capture_output=True, text=True)
        accepted = proc.returncode == 0
        ok = (not accepted) if is_negative else accepted
        return path, is_negative, path.relative_to(corpus_dir), ok, \
            (proc.stderr.strip() or proc.stdout.strip())

    targets = ([(p, False) for p in positive]
               + [(p, True) for p in negative])
    if jobs > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            outcomes = list(pool.map(run_one, targets))
    else:
        outcomes = [run_one(target) for target in targets]

    pos_fail, neg_fail = [], []
    for _, is_negative, rel, ok, out in outcomes:
        if is_negative:
            if ok:
                if not quiet:
                    print(f"OK   {rel}（已按预期被拒）")
            else:
                neg_fail.append((rel, "预期被拒绝，实际通过"))
                print(f"FAIL {rel}（预期被拒绝，实际通过）")
        else:
            if ok:
                if not quiet:
                    print(f"OK   {rel}")
            else:
                pos_fail.append((rel, out))
                print(f"FAIL {rel}")

    for rel, out in pos_fail:
        print(f"\n{rel}:")
        for line in out.splitlines()[:3]:
            print(f"    {line}")
    for rel, why in neg_fail:
        print(f"\n{rel}: {why}")

    print(f"\n正例：通过 {len(positive) - len(pos_fail)}/{len(positive)}")
    print(f"反例：通过 {len(negative) - len(neg_fail)}/{len(negative)}")
    return 1 if (pos_fail or neg_fail) else 0


def main():
    parser = argparse.ArgumentParser(description="tests/yh 语法语料校验")
    parser.add_argument("--coverage", action="store_true", help="额外做规则覆盖自检（仅 ANTLR 模式）")
    parser.add_argument("--compiler", action="store_true", help="用 yh --syntax-check 跑语料（编译器模式）")
    parser.add_argument("--compiler-path", default=None,
                        help="编译器模式下指定编译器路径（缺省仓库根 yh）")
    parser.add_argument("--workdir", default=None,
                        help="ANTLR 模式生成 parser 的临时目录位置（缺省仓库 tmp/ 下）")
    parser.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    parser.add_argument("--jobs", type=int, default=0,
                        help="编译器模式下并发语料数（缺省 min(8, CPU 核数)；"
                             "1 为串行；ANTLR 模式在单进程内解析，不受影响）")
    args = parser.parse_args()

    if args.compiler:
        jobs = args.jobs if args.jobs > 0 else max(1, min(8, os.cpu_count() or 1))
        sys.exit(run_compiler_mode(args.quiet, args.compiler_path, jobs))

    ensure_runtime()

    if GRAMMAR is None:
        die("找不到语法文件。已尝试：" + "、".join(str(p) for p in GRAMMAR_CANDIDATES))
    corpus_dir = HERE
    all_files = sorted(p for p in corpus_dir.rglob("*.yh") if p.is_file())
    if not all_files:
        die(f"{corpus_dir} 下没有任何 .yh 语料。")
    rejected_root = corpus_dir / REJECTED_DIR
    positive = [p for p in all_files if rejected_root not in p.parents]
    negative = [p for p in all_files if rejected_root in p.parents]

    tool = find_antlr_tool()
    version = pick_version()
    if not args.quiet:
        print(f"语法文件：{GRAMMAR}")
        print(f"ANTLR：{tool}（版本 {version}，离线）")
        print(f"语料目录：{corpus_dir}")
        print(f"  正例 {len(positive)} 个 / 反例 {len(negative)} 个\n")

    work = generate_parser(tool, version, args.workdir)
    try:
        api = load_parser(work)

        # --- 正例：必须零词法错误 + 零语法错误 + 消费到 EOF ---
        pos_fail = []
        for path in positive:
            ok, problems = check_file(path, api)
            rel = path.relative_to(corpus_dir)
            if ok:
                if not args.quiet:
                    print(f"OK   {rel}")
            else:
                pos_fail.append((rel, problems))
                print(f"FAIL {rel}")

        # --- 反例：必须【有错】才算通过 ---
        neg_fail = []
        for path in negative:
            ok, problems = check_file(path, api)
            rel = path.relative_to(corpus_dir)
            if ok:
                neg_fail.append((rel, "预期被拒绝，实际零错误通过"))
                print(f"FAIL {rel}（预期被拒绝，实际通过）")
            elif not args.quiet:
                print(f"OK   {rel}（已按预期被拒）")

        for rel, problems in pos_fail:
            print(f"\n{rel}:")
            for problem in problems:
                print(f"    {problem}")
        for rel, why in neg_fail:
            print(f"\n{rel}: {why}")

        pos_pass = len(positive) - len(pos_fail)
        neg_pass = len(negative) - len(neg_fail)
        print(f"\n正例：通过 {pos_pass}/{len(positive)}")
        print(f"反例：通过 {neg_pass}/{len(negative)}")

        coverage_ok = True
        if args.coverage:
            coverage_ok = run_coverage(api, positive)

        if pos_fail or neg_fail or not coverage_ok:
            sys.exit(1)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
