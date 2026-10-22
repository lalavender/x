#!/usr/bin/env python3
"""string 直接匹配的复杂度探针（ST4 补充证据）。

生成一个临时 yh 项目：在重复 'a' 文本上查找 64 个 'a' 加一个结尾 'b'，
对多个输入规模记录 string.find 的耗时。脚本只验证结果正确性并打印耗时，
不设置机器速度敏感的固定耗时门；用于记录首版 O(n*m) 上界的实测趋势。

usage: python3 tests/string/complexity.py [--compiler ./yh] [--stdlib ./libs]
                                          [--workdir tmp/string-complexity]

退出码：构建/运行失败或结果错误 1；否则 0。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SIZES = [1000, 5000, 20000, 50000]

PROGRAM = """module main

import memory
import string
import time

// main 在重复 'a' 文本上查找 64 个 'a' + 'b'，打印每个规模的耗时。
fn main() int {
    let sizes [4]int = [1000, 5000, 20000, 50000]
    let max_size u64 = 50002
    let data *u8 = memory.alloc(max_size).to_type(*u8)
    if (data == 0) { return 1 }
    let i u64 = 0
    for i < max_size { data[i] = 'a'; i += 1 }

    let needle_data *u8 = memory.alloc(65).to_type(*u8)
    if (needle_data == 0) { return 2 }
    i = 0
    for i < 64 { needle_data[i] = 'a'; i += 1 }
    needle_data[64] = 'b'
    let needle_result string.ViewResult = string.view_bytes(needle_data, 65)
    if (needle_result.status != string.status_ok) { return 3 }

    i = 0
    for i < 4 {
        let size int = sizes[i]
        let count u64 = size.to_type(u64) + 1
        data[size.to_type(u64)] = 'b'
        let text_result string.ViewResult = string.view_bytes(data, count)
        if (text_result.status != string.status_ok) { return 4 }
        let start i64 = time.monotonic_ns()
        let found string.IndexResult = string.find(text_result.value, needle_result.value)
        let end i64 = time.monotonic_ns()
        printf("complexity size=%d found=%d index=%d ns=%d\\n",
            size, found.found.to_type(int), found.index.to_type(int),
            (end - start).to_type(int))
        data[size.to_type(u64)] = 'a'
        i += 1
    }
    memory.release(data.to_type(*void))
    memory.release(needle_data.to_type(*void))
    return 0
}
"""


def run(cmd, cwd, env, timeout):
    try:
        return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(
            cmd, 124, error.stdout or "", (error.stderr or "") + "\n[timeout]")


def main(argv):
    parser = argparse.ArgumentParser(description="string 复杂度探针")
    parser.add_argument("--compiler", default="./yh")
    parser.add_argument("--stdlib", default=str(ROOT / "libs"))
    parser.add_argument("--workdir", default=str(ROOT / "tmp" / "string-complexity"))
    args = parser.parse_args(argv)
    compiler = Path(args.compiler).resolve()
    stdlib = Path(args.stdlib).resolve()
    workdir = Path(args.workdir).resolve()
    project = workdir / "probe"
    if project.exists():
        shutil.rmtree(project)
    (project / "src" / "main").mkdir(parents=True)
    (project / "project.toml").write_text(
        '[project]\nos = "host"\narch = "host"\n'
        'name = "string_complexity"\nsource = "src"\n')
    (project / "src" / "main" / "main.yh").write_text(PROGRAM)

    env = dict(os.environ)
    env["YH_STDLIB"] = str(stdlib)
    result = run([str(compiler), "run"], project, env, 1800)
    if result.returncode != 0:
        print(f"FAIL complexity: rc={result.returncode}\n{result.stderr[-800:]}")
        return 1
    lines = [line for line in result.stdout.splitlines()
             if line.startswith("complexity ")]
    if len(lines) != len(SIZES):
        print(f"FAIL complexity: 期望 {len(SIZES)} 行，实际 {len(lines)}")
        return 1
    for size, line in zip(SIZES, lines):
        fields = dict(item.split("=", 1) for item in line.split()[1:])
        if fields.get("found") != "1" or int(fields.get("index", -1)) != size - 64:
            print(f"FAIL complexity: size={size} 结果错误: {line}")
            return 1
        print(line)
    print("PASS complexity: 直接匹配结果正确（未见实用阻塞；耗时仅供记录）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
