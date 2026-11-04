#!/usr/bin/env python3
"""num 标准库的 Python 参考差分（YT4-P7）。

用固定种子生成二进制位模式与十进制文本，生成一个临时 yh 项目，把
`num.parse_f64` 的位模式与 `num.format_f64` 的往返输出打印出来，再与 Python
的 float()/repr() 语义逐项比较。覆盖有限值、负零、次正规、最大有限值与
随机 64 位模式；语法/范围分类由 libs/num/tests.test.yh 覆盖。

usage: python3 tests/num/reference.py [--compiler ./yh] [--stdlib ./libs]
                                      [--workdir tmp/num-reference]
                                      [--opt-level 0|2]

退出码：全部一致 0；构建/运行失败或任一差异 1。
"""

import argparse
import os
import random
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

STATUS_OK = 0
STATUS_RANGE = 2


def bits(value: float) -> int:
    """返回 f64 的 IEEE754 位模式。"""
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def finite(value: float) -> bool:
    """是否为有限值。"""
    return value == value and value not in (float("inf"), float("-inf"))


def make_cases() -> list[str]:
    """返回十进制输入串；期望值由 Python float() 计算。"""
    cases = [
        "0", "-0", "1", "-1", "0.1", "0.2", "0.3",
        "0.30000000000000004", "1.5", "-2.5", "1e2", "1E+2", "1e-2",
        "2.2250738585072014e-308", "5e-324", "1.7976931348623157e308",
        "1.5e300", "-1e300", "1e-300", "123456789012345678901234567890",
        "0.000001", "0.0000001", "999999999999999999999",
    ]
    rng = random.Random(20261025)
    # 随机 64 位模式（过滤 NaN/Inf），用 Python repr 作为十进制输入。
    while len(cases) < 140:
        value = struct.unpack("<d", struct.pack("<Q", rng.getrandbits(64)))[0]
        if not finite(value):
            continue
        text = repr(value)
        if text not in cases:
            cases.append(text)
    # 随机十进制文本（可能上溢）。
    while len(cases) < 220:
        digits = "".join(str(rng.randrange(10)) for _ in range(rng.randrange(1, 18)))
        if digits[0] == "0":
            digits = "1" + digits[1:]
        text = f"{digits}e{rng.randrange(-330, 310):+d}"
        if text not in cases:
            cases.append(text)
    return cases


def generate(cases: list[str]) -> str:
    """生成打印 parse 位模式与 format 往返字节的 yh 程序。"""
    lines = [
        "module main",
        "import num",
        "",
        "fn bits(v f64) u64 {",
        "    let holder *f64 = malloc(8).to_type(*f64)",
        "    holder[0] = v",
        "    let view *u64 = holder.to_type(*u64)",
        "    let out u64 = view[0]",
        "    free(holder.to_type(*void))",
        "    return out",
        "}",
        "",
        "fn text_len(text *char) u64 {",
        "    return strlen(text).to_type(u64)",
        "}",
        "",
        "fn one(id int, text *char) void {",
        "    let value f64 = 0.0",
        "    let parse_status num.NumStatus = num.parse_f64(text.to_type(*u8), text_len(text), &value)",
        '    printf("P %d %d %llu\\n", id, parse_status.to_type(int), bits(value))',
        "    let buffer [64]u8",
        "    let count u64 = 0",
        "    let format_status num.NumStatus = num.format_f64(value, &buffer[0], 64, &count)",
        '    printf("F %d %d %llu", id, format_status.to_type(int), count)',
        "    let i u64 = 0",
        "    for i < count {",
        '        printf(" %d", buffer[i].to_type(int))',
        "        i += 1",
        "    }",
        '    printf("\\n")',
        "}",
        "",
        "fn main() int {",
    ]
    for index, text in enumerate(cases):
        lines.append(f'    one({index}, "{text}")')
    lines += ["    return 0", "}"]
    return "\n".join(lines) + "\n"


def run(cmd, cwd, env):
    """运行子命令并返回 CompletedProcess。"""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=1800, env=env)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="num Python 参考差分")
    parser.add_argument("--compiler", default=str(ROOT / "yh"))
    parser.add_argument("--stdlib", default=str(ROOT / "libs"))
    parser.add_argument("--workdir", default=str(ROOT / "tmp" / "num-reference"))
    parser.add_argument("--opt-level", choices=("0", "2"), default="0")
    args = parser.parse_args(argv)

    compiler = Path(args.compiler).resolve()
    stdlib = Path(args.stdlib).resolve()
    workdir = Path(args.workdir).resolve()
    if not compiler.exists():
        print(f"FAIL 编译器不存在: {compiler}")
        return 1
    if not (stdlib / "num").is_dir():
        print(f"FAIL 标准库缺少 num 模块: {stdlib}")
        return 1

    cases = make_cases()
    project = workdir / "reference"
    if project.exists():
        shutil.rmtree(project)
    (project / "src" / "main").mkdir(parents=True)
    (project / "project.toml").write_text(
        '[project]\nos = "host"\narch = "host"\n'
        'name = "num_reference"\nsource = "src"\n')
    (project / "src" / "main" / "main.yh").write_text(generate(cases))

    env = dict(os.environ)
    env["YH_STDLIB"] = str(stdlib)
    result = run([str(compiler), f"-O{args.opt_level}", "run"], project, env)
    if result.returncode != 0:
        print(f"FAIL reference: build/run rc={result.returncode}\n"
              f"{result.stderr[-800:]}")
        return 1

    parse_lines = {}
    format_lines = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "P":
            parse_lines[int(parts[1])] = (int(parts[2]), int(parts[3]))
        elif parts[0] == "F":
            raw = bytes(int(item) for item in parts[4:])
            format_lines[int(parts[1])] = (int(parts[2]), int(parts[3]), raw)

    mismatches = 0
    for index, text in enumerate(cases):
        expected = float(text)
        want_status = STATUS_OK if finite(expected) else STATUS_RANGE
        want_bits = bits(expected) if finite(expected) else 0
        got = parse_lines.get(index)
        if got != (want_status, want_bits):
            mismatches += 1
            print(f"FAIL parse case {index} {text!r}: want={(want_status, want_bits)} got={got}")
            if mismatches >= 10:
                break
            continue
        if not finite(expected):
            continue
        # 格式化必须成功，且打印出的十进制能被 Python 解析回同一位模式。
        fmt = format_lines.get(index)
        if fmt is None or fmt[0] != STATUS_OK or fmt[1] == 0:
            mismatches += 1
            print(f"FAIL format case {index} {text!r}: 状态/长度异常 {fmt}")
            if mismatches >= 10:
                break
            continue
        _, count, raw = fmt
        if count != len(raw):
            mismatches += 1
            print(f"FAIL format case {index} {text!r}: 长度 {count} != {len(raw)}")
            continue
        try:
            back = float(raw.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            mismatches += 1
            print(f"FAIL format case {index} {text!r}: 输出不是十进制 {raw!r}")
            if mismatches >= 10:
                break
            continue
        if bits(back) != bits(expected):
            mismatches += 1
            print(f"FAIL format case {index} {text!r}: 往返位模式不符 {raw!r}")
            if mismatches >= 10:
                break
    if mismatches:
        return 1
    print(f"PASS reference: {len(cases)} 例与 Python 语义一致")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
