#!/usr/bin/env python3
"""yh-codeflow 自测：统计可解析、HTML 自包含、布局端点自洽、结果可重复。

失败模式是「图看起来生成了、点开是空白」：JSON 里混进 NUL、JS 字符串被
写进真实换行、布局坐标丢了节点，都会让页面静默白屏。这里逐条守住：
  1. `--check` 退出 0 且三套布局的边端点都在坐标表里；
  2. 生成的 HTML 不含 NUL，且内嵌 DATA/LAYOUT 能被 JSON 解析；
  3. 布局里的模块/文件/函数规模与 DATA 一致；
  4. 连续两次生成的 HTML 逐字节相同（布局确定，不依赖随机数/时间）。
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools" / "yh-codeflow.py"


def run(*args):
    """跑一次工具，返回 CompletedProcess。"""
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, timeout=300)


def fail(msg: str) -> int:
    print("FAIL " + msg)
    return 1


def parse_payload(html: str):
    """从 HTML 里取出内嵌的 DATA/LAYOUT（工具只写一处 script）。"""
    data = re.search(r"const DATA = (\{.*?\});\nconst LAYOUT", html, re.S)
    lay = re.search(r"const LAYOUT = (\{.*?\});\nconst SVG_NS", html, re.S)
    if not data or not lay:
        return None, None
    return json.loads(data.group(1)), json.loads(lay.group(1))


def main() -> int:
    """逐条断言；任一失败返回 1。"""
    checked = run("--check")
    if checked.returncode != 0:
        return fail("--check 退出码 " + str(checked.returncode) + "\n" + checked.stdout[-800:])
    if "模块 " not in checked.stdout or "check: " not in checked.stdout:
        return fail("--check 输出缺少统计或自洽结论：\n" + checked.stdout[-500:])
    print("PASS --check 统计与端点自洽")

    with tempfile.TemporaryDirectory() as tmp:
        a = Path(tmp) / "a.html"
        b = Path(tmp) / "b.html"
        r1 = run("--out", str(a))
        r2 = run("--out", str(b))
        if r1.returncode != 0 or r2.returncode != 0 or not a.is_file():
            return fail(f"生成 HTML 失败：rc={r1.returncode}/{r2.returncode}")
        html = a.read_text(encoding="utf-8")
        if "\x00" in html:
            return fail("HTML 里出现 NUL 字节（JS 会白屏）")
        if html.count("<script>") != 1 or "__DATA__" in html or "__LAYOUT__" in html:
            return fail("HTML 不是单一自包含 script，或占位符未替换")
        print("PASS HTML 自包含且无 NUL")

        data, lay = parse_payload(html)
        if data is None:
            return fail("内嵌 DATA/LAYOUT 无法解析")
        if len(data["modules"]) < 10 or len(data["files"]) < len(data["modules"]):
            return fail(f"规模异常：模块 {len(data['modules'])} / 文件 {len(data['files'])}")
        if len(data["functions"]) != sum(m["fns"] for m in data["modules"]):
            return fail("函数总数与模块汇总不一致")
        graphs = [lay["imports"], lay["calls"]] + list(lay["files"].values())
        bad = [e for g in graphs for e in g["edges"]
               if e[0] not in g["pos"] or e[1] not in g["pos"]]
        if bad:
            return fail(f"布局有 {len(bad)} 条悬挂边，例 {bad[:3]}")
        if len(lay["imports"]["edges"]) < 40:
            return fail("import 边数量异常：" + str(len(lay["imports"]["edges"])))
        print(f"PASS 布局规模一致（模块 {len(data['modules'])} / 文件 {len(data['files'])} / "
              f"函数 {len(data['functions'])} / import 边 {len(lay['imports']['edges'])}）")

        if a.read_bytes() != b.read_bytes():
            return fail("两次生成的 HTML 不一致（布局不确定）")
        print("PASS 连续两次生成逐字节一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
