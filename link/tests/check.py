#!/usr/bin/env python3
"""check.py —— yh_link（link/ 链接器项目）验收门。

当前链接器只有入口骨架，本门验证的是「项目能构建 + 入口行为符合约定」：
  1. 用指定编译器冷编 link/ 项目，产出 .build/yh_link；
  2. `--version` 退出码 0 并打印工具名；
  3. 其余调用（含规划中的 `link` 子命令）退出码 2 且打印「尚未实现」，
     避免骨架被调用方误当成可用链接器。

TC4 落地后本门应扩展为真正的链接验收（对象解析、布局、重定位、可执行运行）。

用法：
    python3 tests/check.py [--compiler /path/to/yh]
"""

import argparse
import os
import shutil
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
LINK_DIR = os.path.dirname(TESTS)
ROOT = os.path.dirname(LINK_DIR)


def main() -> int:
    ap = argparse.ArgumentParser(description="构建并验收 yh_link 链接器项目")
    ap.add_argument("--compiler", default=os.path.join(ROOT, "yh"),
                    help="用于构建 link/ 项目的 yh 编译器路径")
    args = ap.parse_args()

    compiler = args.compiler
    if not os.path.isfile(compiler):
        compiler = os.path.join(ROOT, "bin", "yh")
    if not os.path.isfile(compiler):
        print("错误: 找不到 yh 编译器（用 --compiler 指定）", file=sys.stderr)
        return 2

    env = dict(os.environ)
    env.setdefault("TMPDIR", os.path.join(ROOT, "tmp"))

    # 1) 冷编
    build_dir = os.path.join(LINK_DIR, ".build")
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir)
    r = subprocess.run([compiler, "build"], cwd=LINK_DIR, env=env,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("link/ 项目构建失败：\n" + (r.stdout + r.stderr).strip(),
              file=sys.stderr)
        return 2
    product = os.path.join(build_dir, "yh_link")
    if not os.path.isfile(product):
        print("错误: 构建产物缺失 %s" % product, file=sys.stderr)
        return 2

    # 2) --version
    r = subprocess.run([product, "--version"], capture_output=True, text=True)
    if r.returncode != 0 or "yh_link" not in r.stdout:
        print("--version 行为不符：rc=%d out=%r" % (r.returncode, r.stdout),
              file=sys.stderr)
        return 1

    # 3) 其余调用必须报未实现（退出码 2）
    for argv in ([product], [product, "link", "-o", "out"]):
        r = subprocess.run(argv, capture_output=True, text=True)
        if r.returncode != 2 or "尚未实现" not in r.stderr:
            print("%s 行为不符：rc=%d err=%r" % (argv[1:], r.returncode, r.stderr),
                  file=sys.stderr)
            return 1

    print("yh_link 骨架门通过（构建 + 入口行为）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
