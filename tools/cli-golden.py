#!/usr/bin/env python3
"""yh 命令行等价性金标（CLI-R1）：同一批 argv 分别交给旧/新编译器，比较可观察行为。

用法:
    python3 tools/cli-golden.py --old tmp/cli-migration/yh-old --new ./yh
    python3 tools/cli-golden.py --old A --new B --filter build --keep

设计（见 docs/02-plan/yh-CLI用cli标准库重写实施方案-2026-10-27.md §7）：
- 每个用例在独立的 fixture 副本里运行，保证两个二进制看到相同的冷缓存状态；
- 严格等价：退出码 + 归一化后的 stdout/stderr；
- 归一化：仓库根/工作目录/binary 路径替换为占位符，`--stats` 的 time_*=Ns 置零，
  `[编译]/[缓存]/[检查]/[链接]` 进度行按多重集合比较（并行 worker 顺序不稳定）；
- `strict=False` 的用例只比较退出码与 stdout（已在报告里注明原因）。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 进度行前缀：并行 worker 的输出顺序不稳定，按多重集合比较。
PROGRESS = re.compile(r"^\s*\[(编译|缓存|检查|链接|装配|目标文件)\] ")
TIME_FIELD = re.compile(r"time_[a-z_]+=\d+")

MAIN_SRC = '''module main;

// main 是最小可运行入口。
fn main(argc int, argv **char) int {
    printf("hello cli\\n");
    return 0;
}
'''

BAD_SRC = '''module main;

// main 故意引用不存在的名字，用于错误路径对比。
fn main(argc int, argv **char) int {
    return missing_symbol();
}
'''

GOOD_SRC = '''module main;

// good 只做语法与语义合法的空程序。
fn good() int {
    return 0;
}
'''


def write_fixtures(path: Path) -> None:
    """生成金标用的最小项目；已存在时重建，保证冷状态。"""
    if path.exists():
        shutil.rmtree(path)
    (path / "src/main").mkdir(parents=True)
    (path / "project.toml").write_text(
        '[project]\nos = "host"\narch = "host"\nname = "cli_proj"\nsource = "src"\n',
        encoding="utf-8")
    (path / "src/main/main.yh").write_text(MAIN_SRC, encoding="utf-8")
    (path / "bad.yh").write_text(BAD_SRC, encoding="utf-8")
    (path / "good.yh").write_text(GOOD_SRC, encoding="utf-8")


CASES = [
    # (名字, cwd 占位, argv, strict, 说明)
    ("version", "libs", ["version"], True, ""),
    ("version-contracts", "libs", ["version", "--contracts"], True, ""),
    ("list", "libs", ["list"], True, ""),
    ("list-resolve", "libs", ["list", "--resolve", "string"], True, ""),
    ("test-list", "libs", ["test", "--list"], True, ""),
    ("test-no-run", "libs", ["test", "--no-run", "--filter", "cli0"], True, ""),
    ("check-project", "proj", ["check"], True, ""),
    ("check-file", "proj", ["check", "good.yh"], True, ""),
    ("build", "proj", ["build"], True, ""),
    ("build-stats", "proj", ["--stats", "build"], True, ""),
    ("run", "proj", ["run"], True, ""),
    ("target-before", "proj", ["--target", "aarch64-apple-darwin", "build"], True, ""),
    ("target-after", "proj", ["build", "--target", "aarch64-apple-darwin"], True, ""),
    ("opt2", "proj", ["-O2", "build"], True, ""),
    ("backend-llvm", "proj", ["--backend", "llvm", "test", "--list"], True, ""),
    ("legacy-system", "proj", ["--legacy-system", "build"], True, ""),
    ("syntax-check", "proj", ["--syntax-check", "good.yh"], True, ""),
    ("syntax-check-bad", "proj", ["--syntax-check", "bad.yh"], True, ""),
    ("emit-asm", "proj", ["--emit-asm", "good.yh"], True, ""),
    ("emit-asm-bad", "proj", ["--emit-asm", "bad.yh"], True, ""),
    ("file-then-o", "proj", ["good.yh", "-o", "out1"], True, ""),
    ("o-then-file", "proj", ["-o", "out2", "good.yh"], True, ""),
    ("emit-llvm-file", "proj", ["--emit-llvm", "good.yh"], False, "缺模式时旧实现只打 usage，新实现按 file parser 的 usage 输出"),
    ("asm-and-llvm", "proj", ["--emit-asm", "--emit-llvm", "good.yh"], True, ""),
    ("bare", "proj", [], False, "裸调用帮助改由 cli 生成（含命令列表与单文件形态说明）"),
    ("unknown-option", "proj", ["--unknown"], False, "新实现会多打印一条诊断"),
    ("link-missing-value", "proj", ["build", "--link"], False, "新实现补一条诊断行（旧只有 usage）"),
    ("timeout-zero", "libs", ["test", "--timeout", "0"], False, "usage 文本改由 cli 生成"),
    ("timeout-huge", "libs", ["test", "--timeout", "99999"], False, "usage 文本改由 cli 生成"),
    ("target-alias", "proj", ["--target", "linux", "build"], True, ""),
    ("target-unknown", "proj", ["--target", "mips-unknown", "build"], True, ""),
    ("check-two-files", "proj", ["check", "a.yh", "b.yh"], False, "新实现补一条诊断行（旧只有 usage）"),
    ("list-link", "libs", ["list", "--link", "x"], False, "新实现按未知选项报错并给候选"),
    ("syntax-check-missing", "proj", ["--syntax-check"], False, "新实现补一条诊断行（旧只有 usage）"),
    ("o-missing-file", "proj", ["-o", "out3"], False, "新实现补一条诊断行（旧只有 usage）"),
    ("opt-both", "proj", ["-O0", "-O2", "build"], True, ""),
]


def normalize(text: str, root: Path, work: Path, binary: Path) -> str:
    """归一化输出：路径占位、时间归零、进度行排序。"""
    text = text.replace(str(binary), "<yh>")
    text = text.replace(str(work), "<case>")
    text = text.replace(str(root), "<root>")
    text = TIME_FIELD.sub(lambda m: m.group(0).split("=")[0] + "=0", text)
    # 编译器自身模块数/哈希随实现变化，统计行只保留前缀。
    text = re.sub(r"(?m)^yh-stats .*$", "yh-stats <values-omitted>", text)
    progress = []
    others = []
    for line in text.splitlines():
        stripped = line.rstrip()
        if PROGRESS.match(stripped):
            progress.append(stripped)
        else:
            others.append(stripped)
    progress.sort()
    return "\n".join(others + progress)


def run(binary: Path, cwd: Path, argv: list, env: dict) -> tuple:
    result = subprocess.run([str(binary), *argv], cwd=str(cwd), env=env,
                            capture_output=True, text=True, timeout=600)
    return result.returncode, result.stdout, result.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True)
    parser.add_argument("--new", required=True)
    parser.add_argument("--workdir", default=str(ROOT / "tmp/cli-golden"))
    parser.add_argument("--filter", default="")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    old = Path(args.old).resolve()
    new = Path(args.new).resolve()
    work = Path(args.workdir).resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    env = dict(os.environ)
    env.pop("YH_STDLIB", None)
    fixtures = {}
    for name in ("proj", "old-proj", "new-proj"):
        path = work / name
        write_fixtures(path)
        fixtures[name] = path
    # 两个二进制各自独立的项目副本（缓存与 .build 不共享）。
    fixtures["old"] = fixtures["old-proj"]
    fixtures["new"] = fixtures["new-proj"]

    failures = []
    relaxed = []
    ran = 0
    for name, cwd_key, argv, strict, note in CASES:
        if args.filter and args.filter not in name:
            continue
        ran += 1
        reports = []
        for tag, binary, fixture in (("old", old, "old"), ("new", new, "new")):
            cwd = fixtures[fixture] if cwd_key == "proj" else (
                ROOT / "libs" if cwd_key == "libs" else ROOT)
            rc, out, err = run(binary, cwd, argv, env)
            reports.append((tag, rc, normalize(out, ROOT, cwd, binary),
                            normalize(err, ROOT, cwd, binary)))
        old_rc, new_rc = reports[0][1], reports[1][1]
        old_out, new_out = reports[0][2], reports[1][2]
        old_err, new_err = reports[0][3], reports[1][3]
        same = old_rc == new_rc and old_out == new_out
        if strict:
            same = same and old_err == new_err
        if same:
            label = "OK  " if strict else "OK* "
            print(f"{label} {name}")
            if not strict:
                relaxed.append((name, note))
            continue
        print(f"FAIL {name}  (rc old={old_rc} new={new_rc})" + (f"  [{note}]" if note else ""))
        if old_out != new_out:
            print("  --- stdout old ---")
            print("\n".join("  " + line for line in old_out.splitlines()[:12]))
            print("  --- stdout new ---")
            print("\n".join("  " + line for line in new_out.splitlines()[:12]))
        if strict and old_err != new_err:
            print("  --- stderr old ---")
            print("\n".join("  " + line for line in old_err.splitlines()[:12]))
            print("  --- stderr new ---")
            print("\n".join("  " + line for line in new_err.splitlines()[:12]))
        failures.append(name)

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    print(f"\ncli-golden: 用例 {ran}，失败 {len(failures)}"
          + (f"，宽松 {len(relaxed)}（{', '.join(n for n, _ in relaxed)}）" if relaxed else ""))
    if failures:
        print("失败用例: " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
