#!/usr/bin/env python3
"""string ST6 安装/仓库外导入验收。

执行 `just DESTDIR=<work>/root PREFIX=/usr install`，确认安装树包含 string
全部源码，再把 stringmodel fixture 复制到仓库外，清除 YH_STDLIB 后用安装后的
yh 构建运行。验证默认 `../share/yh/libs` 发现与显式环境覆盖不需要额外的
安装规则。

usage: python3 tests/string/install.py [--workdir tmp/string-install] [--keep]

退出码：通过 0；失败 1。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FIXTURE = ROOT / "tests" / "modules" / "projects" / "stringmodel"
REQUIRED = [
    "base.yh", "view.yh", "owned.yh", "transform.yh",
    "utf8.yh", "doc.yh", "string.yh",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="string 安装/仓库外导入验收")
    parser.add_argument("--workdir", default=str(ROOT / "tmp" / "string-install"),
                        help="安装根目录（默认 tmp/string-install）")
    parser.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    parser.add_argument("--keep", action="store_true", help="保留安装树")
    args = parser.parse_args()

    work = Path(args.workdir).resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    dest = work / "root"
    installed = subprocess.run(
        ["just", f"DESTDIR={dest}", "PREFIX=/usr", "install"],
        cwd=ROOT, capture_output=True, text=True, timeout=1800)
    if installed.returncode != 0:
        print(f"FAIL just install rc={installed.returncode}")
        print((installed.stderr or installed.stdout)[-1000:])
        return 1

    prefix = dest / "usr"
    binary = prefix / "bin" / "yh"
    string_dir = prefix / "share" / "yh" / "libs" / "string"
    if not binary.exists():
        print(f"FAIL 安装树缺少 yh: {binary}")
        return 1
    missing = [name for name in REQUIRED if not (string_dir / name).exists()]
    if missing:
        print(f"FAIL 安装树缺少 string 源码: {missing}")
        return 1
    if not args.quiet:
        print(f"OK   安装树包含 {len(list(string_dir.glob('*.yh')))} 个 string 源码")

    outside = work / "outside"
    shutil.copytree(FIXTURE, outside,
                    ignore=shutil.ignore_patterns(".build"))
    env = dict(os.environ)
    env.pop("YH_STDLIB", None)
    built = subprocess.run([str(binary), "run"], cwd=outside,
                           capture_output=True, text=True, timeout=900,
                           env=env)
    if built.returncode != 0 or not built.stdout.endswith("string model ok\n"):
        print(f"FAIL 仓库外运行 rc={built.returncode}")
        print(f"stdout: {built.stdout[-800:]!r}")
        print(f"stderr: {built.stderr[-800:]!r}")
        return 1
    if not args.quiet:
        print("OK   仓库外默认标准库发现与 string 基本 API")
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    print("string install: 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
