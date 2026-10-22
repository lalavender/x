#!/usr/bin/env python3
"""cli 标准库与 Python argparse 的差分验收。

把同一份 argv 分别交给 clidiff 探针与 Python argparse，比较 status、
各 dest 的规范化值与 parse_known 的未消费 token。只比较可观察结果，不比较
诊断文案（yh 为中文）。

用法:
    python3 libs/cli/test/diff.py
    python3 libs/cli/test/diff.py --compiler ./yh --workdir tmp/cli-diff --keep

退出码：无未知差异 0；出现新的差异 1。
"""

import argparse
import contextlib
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent  # libs/cli/test -> 仓库根

DESTS = ["output", "verbose", "level", "tag", "force", "cache", "quiet",
         "mode", "pair", "many", "append", "extend", "stamp", "answer",
         "tries", "src", "files"]

# (模式, argv)；模式含义见 clidiff/src/main/main.yh。
CASES = [
    ("n", ["in.txt"]),
    ("n", ["in.txt", "-v", "-v"]),
    ("n", ["-vvv", "in.txt"]),
    ("n", ["a", "--level", "2", "b"]),
    ("n", ["--output=x", "in.txt"]),
    ("n", ["--output=", "in.txt"]),
    ("n", ["-o=file", "in.txt"]),
    ("n", ["-ofile", "in.txt"]),
    ("n", ["-vo", "out.bin", "in.txt"]),
    ("n", ["-vvoout.bin", "in.txt"]),
    ("n", ["in.txt", "--tag"]),
    ("n", ["in.txt", "--tag=x"]),
    ("n", ["in.txt", "--tag="]),
    ("n", ["in.txt", "--many"]),
    ("n", ["in.txt", "--many", "a", "b"]),
    ("n", ["--many", "a", "in.txt"]),
    ("n", ["in.txt", "--append", "a", "--append", "b"]),
    ("n", ["in.txt", "--extend", "a", "b", "--extend", "c"]),
    ("n", ["in.txt", "--stamp", "--stamp"]),
    ("n", ["in.txt", "--answer"]),
    ("n", ["in.txt", "--force", "--cache", "--quiet"]),
    ("n", ["in.txt", "--no-cache"]),
    ("n", ["in.txt", "--cache", "--no-cache"]),
    ("n", ["in.txt", "--mode", "fast"]),
    ("n", ["in.txt", "--mode", "medium"]),
    ("n", ["in.txt", "--pair", "a", "b"]),
    ("n", ["in.txt", "--pair", "a"]),
    ("n", ["in.txt", "--pair", "a", "b", "c"]),
    ("n", ["--level", "-7", "in.txt"]),
    ("n", ["--level=-7", "in.txt"]),
    ("n", ["-l", "-7", "in.txt"]),
    ("n", ["in.txt", "-1"]),
    ("n", ["--", "-x", "in.txt"]),
    ("n", ["in.txt", "--"]),
    ("n", ["--output"]),
    ("n", ["--unknown", "in.txt"]),
    ("n", ["-z", "in.txt"]),
    ("n", ["--out=out.bin", "in.txt"]),
    ("n", ["in.txt", "--out=out.bin"]),
    ("n", ["--force=yes", "in.txt"]),
    ("n", ["--cache=yes", "in.txt"]),
    ("n", ["--mode=fast", "in.txt"]),
    ("n", ["in.txt", "--extend"]),
    ("n", ["--extend", "a", "in.txt", "--level", "3"]),
    ("n", ["in.txt", "--tries"]),
    ("n", ["--tries", "in.txt"]),
    ("n", ["--help"]),
    ("n", ["-h"]),
    ("n", ["--version"]),
    ("n", ["--version", "--help"]),
    ("k", ["in.txt", "--bogus", "x"]),
    ("k", ["--bogus", "in.txt"]),
    ("k", ["in.txt", "-z", "-y"]),
    ("k", ["in.txt", "--level", "abc"]),
    ("i", ["a", "-v", "b"]),
    ("i", ["-v", "a", "b"]),
    ("i", ["a", "--level", "2", "b"]),
    ("i", ["--pair", "a", "b", "c"]),
    ("ki", ["a", "-v", "b", "--bogus"]),
    ("a", ["--out=x", "in.txt"]),
    ("a", ["--o=x", "in.txt"]),
    ("a", ["--pair", "a", "b", "in.txt"]),
    ("o", ["in.txt", "--rest", "a", "b"]),
    ("o", ["in.txt", "--rest"]),
    ("o", ["in.txt", "-r", "a"]),
    ("o", ["in.txt", "--rest", "a", "-x"]),
    ("o", ["in.txt", "--rest", "a", "--", "--help"]),
    ("r", ["in.txt", "a", "b"]),
    ("r", ["in.txt", "a", "-x"]),
    ("n", ["--output", "-x", "in.txt"]),
    ("n", ["--tag", "-x", "in.txt"]),
    ("n", ["-l-7", "in.txt"]),
    ("n", ["-l=-7", "in.txt"]),
    ("n", ["--many", "--", "in.txt"]),
    ("n", ["--many", "--"]),
    ("n", ["-", "x"]),
    ("n", ["in.txt", "--output", "a", "--output", "b"]),
    ("n", ["in.txt", "--pair", "a", "b", "--pair", "c", "d"]),
    ("k", ["in.txt", "--", "-x"]),
    ("n", ["in.txt", "-vx"]),
    ("n", ["in.txt", "-xv"]),
    ("n", ["-1"]),
    ("n", ["-1.5"]),
    ("n", ["--level", "1.5", "in.txt"]),
    ("n", ["in.txt", "--mode", "FAST"]),
    ("n", ["in.txt", "-o", "-x"]),
    ("k", ["-vz", "in.txt"]),
    ("k", ["-vz=1", "in.txt"]),
    ("k", ["in.txt", "--bogus=x"]),
    ("n", ["-vz", "in.txt"]),
    ("n", ["--bogus=x", "in.txt"]),
    ("n", ["in.txt", "--many", "--bogus"]),
    ("n", ["in.txt", "--many", "-1"]),
    ("n", ["in.txt", "--many", "-x"]),
]

# 设计文档明确保留的差异（docs/03-design/yh-cli与argparse差异.md）：
# 不当作失败，但仍逐条打印，防止差异悄悄扩大。
KNOWN_DIFFS = {
    ("n", ("--unknown", "--help")):
        "未知选项优先于帮助请求（设计 §14.3）",
    ("k", ("-vz", "in.txt")):
        "known 模式未知短组合整 token 保留（README §9）",
    ("k", ("-vz=1", "in.txt")):
        "known 模式未知短组合整 token 保留（README §9）",
    ("o", ("in.txt", "--rest", "a", "--", "--help")):
        "remainder 把 -- 当数据（设计 §9.3；argparse 把 -- 当终止符）",
}


def make_parser(abbrev: bool) -> argparse.ArgumentParser:
    """构造与 clidiff 主探针等价的 argparse parser。"""
    ap = argparse.ArgumentParser(prog="diff", description="差分探针",
                                 allow_abbrev=abbrev)
    ap.add_argument("--output", "-o", default="out.bin")
    ap.add_argument("--verbose", "-v", action="count")
    ap.add_argument("--level", "-l", type=int)
    ap.add_argument("--tag", nargs="?", const="none-tag")
    ap.add_argument("--force", "-f", action="store_true")
    ap.add_argument("--cache", action=argparse.BooleanOptionalAction)
    ap.add_argument("--quiet", "-q", action="store_false")
    ap.add_argument("--mode", choices=["fast", "slow"])
    ap.add_argument("--pair", nargs=2)
    ap.add_argument("--many", nargs="*")
    ap.add_argument("--append", action="append")
    ap.add_argument("--extend", action="extend", nargs="+")
    ap.add_argument("--stamp", action="append_const", const="v1")
    ap.add_argument("--answer", action="store_const", const=42)
    ap.add_argument("--version", action="version", version="diff 1.0")
    ap.add_argument("--tries", action="count", default=3)
    ap.add_argument("src")
    ap.add_argument("files", nargs="*")
    return ap


def make_rest_parser(mode: str) -> argparse.ArgumentParser:
    """构造 remainder 参考 parser：o 为选项形态，r 为位置形态。"""
    ap = argparse.ArgumentParser(prog="diff")
    if mode == "o":
        ap.add_argument("--rest", "-r", nargs=argparse.REMAINDER)
        ap.add_argument("src")
    else:
        ap.add_argument("src")
        ap.add_argument("tail", nargs=argparse.REMAINDER)
    return ap


def element(value) -> str:
    """把列表元素渲染成与探针一致的文本。"""
    if value is None:
        return "N"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def fmt(value) -> str:
    """把 Python 值渲染成探针的 kind:value 形式。"""
    if value is None:
        return "N"
    if value is True:
        return "B:true"
    if value is False:
        return "B:false"
    if isinstance(value, int):
        return f"I:{value}"
    if isinstance(value, str):
        return f"T:{value}"
    if isinstance(value, list):
        return "L:" + "|".join(element(item) for item in value)
    return f"?{value!r}"


def oracle(mode: str, argv: list[str]) -> dict:
    """用 argparse 解析并返回与探针同形的结果。"""
    out = {"status": 0, "extras": []}
    ap = make_rest_parser(mode) if mode in ("o", "r") else make_parser(mode == "a")
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            if mode == "k":
                ns, extras = ap.parse_known_args(argv)
                out["extras"] = extras
            elif mode == "ki":
                ns, extras = ap.parse_known_intermixed_args(argv)
                out["extras"] = extras
            elif mode == "i":
                ns = ap.parse_intermixed_args(argv)
            else:
                ns = ap.parse_args(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code == 0:
            out["status"] = 1 if "usage:" in stdout.getvalue() else 2
        else:
            out["status"] = 3
        return out
    dests = ["rest", "src"] if mode == "o" else ["src", "tail"] if mode == "r" else DESTS
    for dest in dests:
        out[dest] = fmt(getattr(ns, dest)) if hasattr(ns, dest) else "absent"
    return out


def probe(binary: Path, mode: str, argv: list[str]) -> dict:
    """运行 clidiff 并解析其规范化输出。"""
    run = subprocess.run([str(binary), mode, *argv], capture_output=True, text=True)
    out = {"status": None, "extras": []}
    for line in run.stdout.splitlines():
        if line.startswith("status="):
            out["status"] = int(line.split("=", 1)[1])
        elif line.startswith("extra="):
            out["extras"].append(line.split("=", 1)[1])
        elif "=" in line:
            key, value = line.split("=", 1)
            out[key] = value
    return out


def compare(got: dict, want: dict) -> list[str]:
    """比较探针与 argparse 的结果，返回差异描述。"""
    diffs = []
    for key, want_value in want.items():
        got_value = got.get(key, "<missing>")
        if got_value != want_value:
            diffs.append(f"{key}: yh={got_value!r} argparse={want_value!r}")
    for key in got:
        if key not in want:
            diffs.append(f"{key}: yh={got[key]!r} argparse=<missing>")
    return diffs


def binary_of(fixture: Path) -> Path:
    """返回探针项目产物路径：.build/<project.name>。"""
    for line in (fixture / "project.toml").read_text().splitlines():
        line = line.strip()
        if line.startswith("name") and "=" in line:
            name = line.split("=", 1)[1].strip().strip('"').strip("'")
            return fixture / ".build" / name
    return fixture / ".build" / fixture.name


def main() -> int:
    ap = argparse.ArgumentParser(description="cli 与 argparse 差分验收")
    ap.add_argument("--compiler", default=str(ROOT / "yh"),
                    help="编译器路径（默认仓库根 ./yh）")
    ap.add_argument("--stdlib", default=str(ROOT / "libs"),
                    help="标准库根（默认仓库根 libs/）")
    ap.add_argument("--workdir", default=str(ROOT / "tmp" / "cli-diff"),
                    help="探针工作目录（默认 tmp/cli-diff）")
    ap.add_argument("--filter", default="", help="只跑名称含该子串的用例")
    ap.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    ap.add_argument("--keep", action="store_true", help="保留工作目录")
    args = ap.parse_args()

    compiler = Path(args.compiler).resolve()
    if not compiler.exists():
        print(f"编译器不存在: {compiler}")
        return 1
    stdlib = Path(args.stdlib).resolve()
    if not (stdlib / "cli").is_dir():
        print(f"标准库根缺少 cli 模块: {stdlib}")
        return 1

    work = Path(args.workdir).resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    fixture = work / "clidiff"
    shutil.copytree(HERE / "clidiff", fixture)
    env = dict(os.environ)
    env["YH_STDLIB"] = str(stdlib)
    built = subprocess.run([str(compiler), "build"], cwd=fixture, env=env,
                           capture_output=True, text=True)
    binary = binary_of(fixture)
    if built.returncode != 0 or not binary.exists():
        print(f"探针构建失败 rc={built.returncode}")
        print((built.stderr or built.stdout)[-800:])
        return 1

    failed = 0
    known = 0
    for mode, argv in CASES:
        name = f"[{mode}] {' '.join(argv)}"
        if args.filter and args.filter not in name:
            continue
        want = oracle(mode, argv)
        got = probe(binary, mode, argv)
        diffs = compare(got, want)
        if not diffs:
            if not args.quiet:
                print(f"OK    {name}")
            continue
        reason = KNOWN_DIFFS.get((mode, tuple(argv)))
        if reason is not None:
            known += 1
            if not args.quiet:
                print(f"KNOWN {name}（{reason}）")
            continue
        failed += 1
        print(f"DIFF  {name}")
        for line in diffs:
            print(f"      {line}")

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    total = len(CASES)
    print(f"cli diff: 一致 {total - failed - known}/{total}，已知差异 {known}，"
          f"未知差异 {failed}（编译器 {compiler}）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
