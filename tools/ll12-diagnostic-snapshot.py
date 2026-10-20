#!/usr/bin/env python3
"""LL12-1 诊断快照：冻结「只语义」路径的诊断输出，供语义纯化逐片对照。

背景：`yh check` 走受检前端（`c_check_only`），不写旧汇编；C1 会逐文件剥离
`gen/sem_*`、`parse/*`、`comptime/*` 里的发射段，要求诊断逐条不变。本工具把
全量语法/运行语料的 check 输出（rc + stdout + stderr）做成快照，改代码前后
各跑一次即可定位差异。

用法：
  python3 tools/ll12-diagnostic-snapshot.py --write    # 生成基线
  python3 tools/ll12-diagnostic-snapshot.py            # 与基线比对
  --compiler PATH   指定 yh（默认仓库根 ./yh）
  --baseline PATH   指定快照（默认 tmp/ll12/diag-baseline.json）

退出码：0 一致；1 有差异或缺少基线；2 用法/执行失败。
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CORPORA = [
    "tests/yh/positive",
    "tests/yh/rejected",
    "tests/yh-run/pass",
    "tests/yh-run/run",
    "tests/yh-run/fail",
]


def corpus_files():
    files = []
    for rel in CORPORA:
        base = ROOT / rel
        if base.is_dir():
            files.extend(sorted(base.rglob("*.yh")))
    return files


def normalize(text):
    """把绝对路径/临时目录归一，避免 worktree 位置影响快照。"""
    text = text.replace(str(ROOT), "<ROOT>")
    text = re.sub(r"/tmp/[^\s:]+", "<TMP>", text)
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").splitlines())


def run_check(compiler, path):
    result = subprocess.run([str(compiler), "check", str(path)],
                            capture_output=True, text=True, timeout=120)
    return {
        "rc": result.returncode,
        "out": normalize(result.stdout),
        "err": normalize(result.stderr),
    }


def load_baseline(path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="生成/更新基线")
    parser.add_argument("--compiler", default=str(ROOT / "yh"))
    parser.add_argument("--baseline", default=str(ROOT / "tmp/ll12/diag-baseline.json"))
    args = parser.parse_args()

    compiler = pathlib.Path(args.compiler).resolve()
    if not compiler.is_file():
        print(f"缺少编译器：{compiler}", file=sys.stderr)
        return 2
    current = {}
    for path in corpus_files():
        rel = path.relative_to(ROOT).as_posix()
        current[rel] = run_check(compiler, path)

    baseline_path = pathlib.Path(args.baseline)
    if args.write:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(current, ensure_ascii=False, indent=1,
                                            sort_keys=True) + "\n", encoding="utf-8")
        failed = sum(1 for v in current.values() if v["rc"] != 0)
        print(f"基线已写入 {baseline_path.relative_to(ROOT)}："
              f"{len(current)} 个文件，{failed} 个预期失败")
        return 0

    baseline = load_baseline(baseline_path)
    if baseline is None:
        print(f"缺少基线：{baseline_path}（先跑 --write）", file=sys.stderr)
        return 1

    diffs = []
    for rel in sorted(set(baseline) | set(current)):
        if rel not in baseline:
            diffs.append(f"+ 新增用例 {rel}")
        elif rel not in current:
            diffs.append(f"- 删除用例 {rel}")
        elif baseline[rel] != current[rel]:
            old, new = baseline[rel], current[rel]
            if old["rc"] != new["rc"]:
                diffs.append(f"! {rel}: rc {old['rc']} -> {new['rc']}")
            if old["err"] != new["err"]:
                diffs.append(f"! {rel}: stderr 变化\n  旧: {old['err']!r}\n  新: {new['err']!r}")
            if old["out"] != new["out"]:
                diffs.append(f"! {rel}: stdout 变化\n  旧: {old['out']!r}\n  新: {new['out']!r}")

    if not diffs:
        print(f"诊断一致：{len(current)} 个文件")
        return 0
    print(f"诊断差异 {len(diffs)} 条（前 20）：")
    for item in diffs[:20]:
        print(" ", item)
    return 1


if __name__ == "__main__":
    sys.exit(main())
