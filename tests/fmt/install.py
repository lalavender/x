#!/usr/bin/env python3
"""fmt R3.2 安装/仓库外导入与 surface 验收。

执行 `just DESTDIR=<work>/root PREFIX=/usr install`，确认安装树包含 fmt
源码，再把 fmtbasic fixture 复制到仓库外，清除 YH_STDLIB 后用安装后的 yh
构建运行。fixture 调用全部公开 API，输出逐字节比对。

usage: python3 tests/fmt/install.py [--workdir tmp/fmt-install] [--keep]
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FIXTURE = ROOT / "tests" / "modules" / "projects" / "fmtbasic"
REQUIRED = ["base.yh", "value.yh", "directive.yh", "render.yh",
            "float.yh", "output.yh", "fmt.test.yh"]
EXPECTED = "1212\n1212\nhi07\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="fmt 安装/仓库外导入验收")
    parser.add_argument("--workdir", default=str(ROOT / "tmp" / "fmt-install"),
                        help="安装根目录（默认 tmp/fmt-install）")
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
    fmt_dir = prefix / "share" / "yh" / "libs" / "fmt"
    if not binary.exists():
        print(f"FAIL 安装树缺少 yh: {binary}")
        return 1
    missing = [name for name in REQUIRED if not (fmt_dir / name).exists()]
    if missing:
        print(f"FAIL 安装树缺少 fmt 源码: {missing}")
        return 1
    if not args.quiet:
        print(f"OK   安装树包含 {len(list(fmt_dir.iterdir()))} 个 fmt 文件")

    outside = work / "outside"
    shutil.copytree(FIXTURE, outside,
                    ignore=shutil.ignore_patterns(".build"))
    env = dict(os.environ)
    env.pop("YH_STDLIB", None)
    built = subprocess.run([str(binary), "run"], cwd=outside,
                           capture_output=True, text=True, timeout=900,
                           env=env)
    if built.returncode != 0 or not built.stdout.endswith(EXPECTED):
        print(f"FAIL 仓库外运行 rc={built.returncode}")
        print(f"stdout: {built.stdout!r} expected: {EXPECTED!r}")
        print(f"stderr: {built.stderr[-800:]!r}")
        return 1
    if not args.quiet:
        print("OK   仓库外默认标准库发现与 fmt 公开 API surface")
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
