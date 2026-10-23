#!/usr/bin/env python3
"""libs/libc 自有验收 runner。

两段验证：
  1. yh 侧：构建 main.yh（import libc），运行全部字符串/内存/转换断言；
  2. C 侧：取构建出的模块对象 yh_libs-libc.o，用宿主 cc 链接 ctest.c 后运行，
     证明导出的是标准 C 符号、参数/返回值符合 C ABI。

fixture 与 runner 都放在 libs/libc/test/，只依赖当前编译器与 libs 目录，
不经过 tests/modules 的用例登记。

用法:
    python3 libs/libc/test/run.py
    python3 libs/libc/test/run.py --compiler ./yh --workdir tmp/libc-test
    python3 libs/libc/test/run.py --quiet --keep

退出码：全部通过 0；有失败 1。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent  # libs/libc/test -> 仓库根


def run(cmd, cwd, env, timeout=300):
    """运行子命令并返回 CompletedProcess。"""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=env)


def find_object(workdir: Path) -> Path:
    """在构建产物里找 libc 模块对象（<triple>/llvm/<opt>/obj/yh_libs-libc.o）。"""
    for path in workdir.rglob("*libc.o"):
        if path.is_file():
            return path
    return workdir / "missing-libc.o"


def main() -> int:
    ap = argparse.ArgumentParser(description="libs/libc 自有验收 runner")
    ap.add_argument("--compiler", default=str(ROOT / "yh"),
                    help="编译器路径（默认仓库根 ./yh）")
    ap.add_argument("--stdlib", default=str(ROOT / "libs"),
                    help="标准库根（默认仓库根 libs/）")
    ap.add_argument("--cc", default=os.environ.get("CC", "cc"),
                    help="C 调用方的编译器命令（默认 $CC 或 cc）")
    ap.add_argument("--workdir", default=str(ROOT / "tmp" / "libc-test"),
                    help="用例工作目录（默认 tmp/libc-test）")
    ap.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    ap.add_argument("--keep", action="store_true", help="保留工作目录")
    args = ap.parse_args()

    compiler = Path(args.compiler).resolve()
    if not compiler.exists():
        print(f"编译器不存在: {compiler}")
        return 1
    stdlib = Path(args.stdlib).resolve()
    if not (stdlib / "libc").is_dir():
        print(f"标准库根缺少 libc 模块: {stdlib}")
        return 1

    work = Path(args.workdir).resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    shutil.copy2(HERE / "project.toml", work / "project.toml")
    shutil.copy2(HERE / "main.yh", work / "main.yh")

    env = dict(os.environ)
    env["YH_STDLIB"] = str(stdlib)
    failed = 0

    # 1. yh 侧断言
    built = run([str(compiler), "build"], work, env)
    binary = work / ".build" / "libccheck"
    if built.returncode != 0 or not binary.exists():
        failed += 1
        print(f"FAIL libc-yh: 构建失败 rc={built.returncode}")
        print((built.stderr or built.stdout)[-600:])
    else:
        shown = run([str(binary)], work, env)
        ok = shown.returncode == 0 and "libc l1 ok" in shown.stdout
        if ok:
            if not args.quiet:
                print("OK   libc-yh")
        else:
            failed += 1
            print(f"FAIL libc-yh: rc={shown.returncode}; "
                  f"stdout={shown.stdout[-200:]!r}; "
                  f"stderr={shown.stderr[-200:]!r}")

    # 2. C ABI 侧
    obj = find_object(work)
    if not obj.is_file():
        failed += 1
        print(f"FAIL libc-c-abi: 未找到模块对象 {obj}")
    else:
        exe = work / "ctest"
        linked = run([args.cc, "-O0", "-o", str(exe), str(HERE / "ctest.c"),
                      str(obj)], work, env)
        if linked.returncode != 0 or not exe.exists():
            failed += 1
            print(f"FAIL libc-c-abi: C 链接失败 rc={linked.returncode}")
            print((linked.stderr or linked.stdout)[-600:])
        else:
            shown = run([str(exe)], work, env)
            ok = shown.returncode == 0 and "c-abi libc ok" in shown.stdout
            if ok:
                if not args.quiet:
                    print("OK   libc-c-abi")
            else:
                failed += 1
                print(f"FAIL libc-c-abi: rc={shown.returncode}; "
                      f"stdout={shown.stdout[-200:]!r}; "
                      f"stderr={shown.stderr[-200:]!r}")

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    print(f"libc: 通过 {2 - failed}/2（编译器 {compiler}）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
