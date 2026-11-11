#!/usr/bin/env python3
"""TOML T5.1 安装/仓库外导入验收。

执行 `just DESTDIR=<work>/root PREFIX=/usr install`，确认安装树包含 toml
源码与 yh，再把 tests/modules/projects/tomloutside 复制到仓库外，清除
YH_STDLIB 后使用安装后的 yh 构建运行。验证默认 `../share/yh/libs` 发现、
`read_file` 与本库查询。

用法:
    python3 tests/toml/install.py
    python3 tests/toml/install.py --workdir tmp/toml-install

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
FIXTURE = ROOT / "tests" / "modules" / "projects" / "tomloutside"


def main() -> int:
    ap = argparse.ArgumentParser(description="TOML 安装/仓库外导入验收")
    ap.add_argument("--workdir", default=str(ROOT / "tmp" / "toml-install"),
                    help="安装根目录（默认 tmp/toml-install）")
    ap.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    ap.add_argument("--keep", action="store_true", help="保留安装树")
    args = ap.parse_args()

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
    toml_dir = prefix / "share" / "yh" / "libs" / "toml"
    if not binary.exists():
        print(f"FAIL 安装树缺少 yh: {binary}")
        return 1
    # 从源目录推导生产源码清单（排除 .test.yh），避免硬编码随文件拆分过期。
    source_dir = ROOT / "libs" / "toml"
    required = sorted(p.name for p in source_dir.glob("*.yh")
                      if not p.name.endswith(".test.yh"))
    missing_yh = [name for name in required if not (toml_dir / name).exists()]
    if missing_yh:
        print(f"FAIL 安装树缺少 toml 源码: {missing_yh}")
        return 1
    if not args.quiet:
        print(f"OK   安装树包含 {len(list(toml_dir.glob('*.yh')))} 个 toml 源码")

    outside = work / "outside"
    shutil.copytree(FIXTURE, outside)
    env = dict(os.environ)
    env.pop("YH_STDLIB", None)
    built = subprocess.run([str(binary), "run"], cwd=outside,
                           capture_output=True, text=True, timeout=900,
                           env=env)
    if built.returncode != 0 or "toml outside ok" not in built.stdout:
        print(f"FAIL 仓库外运行 rc={built.returncode}")
        print(f"stdout: {built.stdout[-800:]!r}")
        print(f"stderr: {built.stderr[-800:]!r}")
        return 1
    if not args.quiet:
        print("OK   仓库外默认标准库发现与 read_file")
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    print("toml install: 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
