#!/usr/bin/env python3
"""string 变换与 UTF-8 的独立参考差分（ST4/ST5）。

用固定随机种子生成用例，生成一个临时 yh 项目，把 concat/join/replace/
lower_ascii/upper_ascii/utf8_validate/utf8_next/append_rune 的实际输出打印
出来，再与 Python 标准库的 bytes/str 语义逐项比较。生成源码与数据只写入
--workdir，不修改仓库 fixture。

usage: python3 tests/string/reference.py [--compiler ./yh] [--stdlib ./libs]
                                        [--workdir tmp/string-reference]
                                        [--opt-level 0|2]

退出码：全部一致 0；构建/运行失败或任一差异 1。
"""

import argparse
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

STATUS_OK = 0
STATUS_END = 1
STATUS_INVALID_UTF8 = 6

# 覆盖 ASCII、NUL、多字节边界、BOM、最大标量与常见 emoji。
SCALARS = [
    0x00, 0x09, 0x0A, 0x20, 0x41, 0x5A, 0x61, 0x7A, 0x7F,
    0x80, 0xE9, 0x2C3, 0x4E2D, 0xFEFF, 0x1F600, 0x10FFFF,
]

# 偏差字节集合：合法首字节、续字节、过长/越界/非法首字节。
BYTE_ALPHABET = [0x00, 0x41, 0x7F, 0x80, 0xBF, 0xC0, 0xC2, 0xE0, 0xED,
                 0xF0, 0xF4, 0xF5, 0xFF]


def emit_view(lines, name, data):
    """把一段字节写成 yh View；空串使用空指针 + 零长度。"""
    if not data:
        lines.append(f"    let {name}_null *u8 = 0")
        lines.append(f"    let {name}_result string.ViewResult = "
                     f"string.view_bytes({name}_null, 0)")
        lines.append(f"    let {name} string.View = {name}_result.value")
        return
    zeros = ", ".join(["0"] * len(data))
    lines.append(f"    let {name}_buf [{len(data)}]u8 = [{zeros}]")
    for index, byte in enumerate(data):
        lines.append(f"    {name}_buf[{index}] = {byte}")
    lines.append(f"    let {name} string.View = "
                 f"view_of_bytes(&{name}_buf[0], {len(data)})")


def emit_string_result(lines, case_id, result_var):
    """报告 StringResult 的 status 与内容，并释放结果。"""
    lines.append(f"    report_string({case_id}, {result_var}.status, "
                 f"&{result_var}.value)")
    lines.append(f"    string.release(&{result_var}.value)")


def make_cases(rng):
    """生成固定 + 随机用例；每个元素是 (op, payload)。"""
    cases = []

    def random_bytes(max_len):
        length = rng.randrange(0, max_len + 1)
        return bytes(rng.choice(BYTE_ALPHABET) for _ in range(length))

    def random_text(max_len):
        length = rng.randrange(0, max_len + 1)
        out = bytearray()
        for _ in range(length):
            out.extend(chr(rng.choice(SCALARS)).encode("utf-8"))
        return bytes(out)

    # concat：空、NUL、非法字节和高位字节混合。
    for _ in range(8):
        cases.append(("concat", (random_bytes(5), random_bytes(5))))
    # join：零片段、单片段、空分隔符、多字节分隔符。
    for _ in range(8):
        parts = tuple(random_bytes(4) for _ in range(rng.randrange(0, 4)))
        separator = random_bytes(2) if rng.randrange(0, 2) else b""
        cases.append(("join", (parts, separator)))
    # replace：old 必须非空；limit 覆盖 0、有限次数与不限。
    for _ in range(10):
        text = random_bytes(10)
        old = random_bytes(2) or b"a"
        replacement = random_bytes(3)
        limit = rng.choice([0, 1, 2, 3, 0x7FFFFFFF])
        cases.append(("replace", (text, old, replacement, limit)))
    # ASCII 大小写：包含 >=0x80 与 NUL。
    for _ in range(6):
        cases.append(("lower", random_bytes(8)))
        cases.append(("upper", random_bytes(8)))
    # utf8_validate：一半合法标量序列，一半随机/截断/非法字节。
    for _ in range(10):
        cases.append(("validate", random_text(4)))
    invalid_fixed = [
        b"\xC0\x80", b"\xE0\x80\x80", b"\xF0\x80\x80\x80",
        b"\xED\xA0\x80", b"\xF4\x90\x80\x80", b"\xC3", b"\xE4\xB8",
        b"\xF0\x9F\x98", b"\x80", b"\xFF", b"a\xC3\x28b",
    ]
    for data in invalid_fixed:
        cases.append(("validate", data))
    for _ in range(9):
        cases.append(("validate", random_bytes(6)))
    # utf8_next：合法序列，覆盖 U+0000、BOM、最大标量与 emoji。
    for _ in range(10):
        cases.append(("next", random_text(4)))
    # append_rune：合法标量与非法值。
    for _ in range(10):
        cases.append(("append_rune", rng.choice(SCALARS)))
    for rune in [0xD800, 0xDFFF, 0x110000, 0xFFFFFFFF]:
        cases.append(("append_rune", rune))
    return cases


def generate_program(cases):
    """生成 yh 源码；每个用例一个函数，main 顺序调用。"""
    lines = [
        "module main",
        "",
        "import string",
        "",
        "// view_of_bytes 把已知有效的字节区间转成视图。",
        "fn view_of_bytes(data *u8, count u64) string.View {",
        "    let result string.ViewResult = string.view_bytes(data, count)",
        "    return result.value",
        "}",
        "",
        "// report_string 输出带编号的状态与字节内容。",
        "fn report_string(id int, status string.Status, value *string.String) void {",
        "    let view string.View = string.as_view(value)",
        "    printf(\"S %d %d %d\", id, status.to_type(int), view.count.to_type(int))",
        "    let i u64 = 0",
        "    for i < view.count {",
        "        printf(\" %d\", view.data[i].to_type(int))",
        "        i += 1",
        "    }",
        "    printf(\"\\n\")",
        "}",
        "",
    ]
    for case_id, (op, payload) in enumerate(cases):
        lines.append(f"// case {case_id}: {op}")
        lines.append(f"fn c{case_id}() void {{")
        if op == "concat":
            left, right = payload
            emit_view(lines, "left", left)
            emit_view(lines, "right", right)
            lines.append("    let result string.StringResult = "
                         "string.concat(left, right)")
            emit_string_result(lines, case_id, "result")
        elif op == "join":
            parts, separator = payload
            emit_view(lines, "separator", separator)
            for index, part in enumerate(parts):
                emit_view(lines, f"part{index}", part)
            if parts:
                lines.append(f"    let parts [{len(parts)}]string.View")
                for index in range(len(parts)):
                    lines.append(f"    parts[{index}] = part{index}")
                lines.append("    let result string.StringResult = "
                             "string.join(parts.to_type([]string.View), separator)")
            else:
                lines.append("    let parts []string.View")
                lines.append("    let result string.StringResult = "
                             "string.join(parts, separator)")
            emit_string_result(lines, case_id, "result")
        elif op == "replace":
            text, old, replacement, limit = payload
            emit_view(lines, "text", text)
            emit_view(lines, "old", old)
            emit_view(lines, "replacement", replacement)
            lines.append(f"    let result string.StringResult = "
                         f"string.replace(text, old, replacement, {limit})")
            emit_string_result(lines, case_id, "result")
        elif op in ("lower", "upper"):
            data = payload
            emit_view(lines, "text", data)
            function = "lower_ascii" if op == "lower" else "upper_ascii"
            lines.append(f"    let result string.StringResult = "
                         f"string.{function}(text)")
            emit_string_result(lines, case_id, "result")
        elif op == "validate":
            data = payload
            emit_view(lines, "text", data)
            lines.append("    let info string.Utf8Info = "
                         "string.utf8_validate(text)")
            lines.append(f"    printf(\"V {case_id} %d %d %d\\n\", "
                         "info.status.to_type(int), "
                         "info.rune_count.to_type(int), "
                         "info.error_offset.to_type(int))")
        elif op == "next":
            data = payload
            emit_view(lines, "text", data)
            lines.append("    let cursor u64 = 0")
            lines.append("    for 1 {")
            lines.append("        let rune string.RuneResult = "
                         "string.utf8_next(text, &cursor)")
            lines.append(f"        printf(\"N {case_id} %d %d %d %d\\n\", "
                         "rune.status.to_type(int), "
                         "rune.rune.to_type(int), "
                         "rune.width.to_type(int), "
                         "rune.offset.to_type(int))")
            lines.append("        if (rune.status != string.status_ok) { break }")
            lines.append("    }")
        elif op == "append_rune":
            rune = payload
            lines.append("    let value string.String = string.make()")
            lines.append(f"    let status string.Status = "
                         f"string.append_rune(&value, {rune})")
            lines.append(f"    report_string({case_id}, status, &value)")
            lines.append("    string.release(&value)")
        else:
            raise ValueError(op)
        lines.append("}")
        lines.append("")
    lines.append("// main 顺序执行全部参考用例。")
    lines.append("fn main() int {")
    for case_id in range(len(cases)):
        lines.append(f"    c{case_id}()")
    lines.append("    return 0")
    lines.append("}")
    return "\n".join(lines) + "\n"


def expected_line(case_id, op, payload):
    """按 Python bytes/str 语义计算单个用例的期望输出行。"""
    if op == "concat":
        left, right = payload
        return f"S {case_id} {STATUS_OK} {len(left + right)}" + \
            "".join(f" {byte}" for byte in left + right)
    if op == "join":
        parts, separator = payload
        joined = separator.join(parts)
        return f"S {case_id} {STATUS_OK} {len(joined)}" + \
            "".join(f" {byte}" for byte in joined)
    if op == "replace":
        text, old, replacement, limit = payload
        replaced = text.replace(old, replacement, limit)
        return f"S {case_id} {STATUS_OK} {len(replaced)}" + \
            "".join(f" {byte}" for byte in replaced)
    if op == "lower":
        data = payload.lower()
        return f"S {case_id} {STATUS_OK} {len(data)}" + \
            "".join(f" {byte}" for byte in data)
    if op == "upper":
        data = payload.upper()
        return f"S {case_id} {STATUS_OK} {len(data)}" + \
            "".join(f" {byte}" for byte in data)
    if op == "validate":
        try:
            decoded = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            return f"V {case_id} {STATUS_INVALID_UTF8} 0 {error.start}"
        return f"V {case_id} {STATUS_OK} {len(decoded)} 0"
    if op == "next":
        lines = []
        offset = 0
        for character in payload.decode("utf-8"):
            encoded = character.encode("utf-8")
            lines.append(f"N {case_id} {STATUS_OK} {ord(character)} "
                         f"{len(encoded)} {offset}")
            offset += len(encoded)
        lines.append(f"N {case_id} {STATUS_END} 0 0 {len(payload)}")
        return lines
    if op == "append_rune":
        rune = payload
        if rune > 0x10FFFF or 0xD800 <= rune <= 0xDFFF:
            return f"S {case_id} {STATUS_INVALID_UTF8} 0"
        data = chr(rune).encode("utf-8")
        return f"S {case_id} {STATUS_OK} {len(data)}" + \
            "".join(f" {byte}" for byte in data)
    raise ValueError(op)


def run(cmd, cwd, env, timeout):
    """运行命令并返回 CompletedProcess；超时视为失败。"""
    try:
        return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(
            cmd, 124, error.stdout or "", (error.stderr or "") + "\n[timeout]")


def parse_args(argv):
    parser = argparse.ArgumentParser(description="string 参考差分")
    parser.add_argument("--compiler", default="./yh", help="yh 编译器路径")
    parser.add_argument("--stdlib", default=str(ROOT / "libs"),
                        help="标准库根（libs/）")
    parser.add_argument("--workdir", default=str(ROOT / "tmp" / "string-reference"),
                        help="临时工作目录")
    parser.add_argument("--opt-level", default="0", choices=("0", "2"),
                        help="优化级别 0 或 2")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    compiler = Path(args.compiler).resolve()
    stdlib = Path(args.stdlib).resolve()
    workdir = Path(args.workdir).resolve()
    if not compiler.exists():
        print(f"FAIL 编译器不存在: {compiler}")
        return 1
    if not (stdlib / "string").is_dir():
        print(f"FAIL 标准库缺少 string 模块: {stdlib}")
        return 1

    rng = random.Random(20261023)
    cases = make_cases(rng)
    project = workdir / "reference"
    if project.exists():
        shutil.rmtree(project)
    (project / "src" / "main").mkdir(parents=True)
    (project / "project.toml").write_text(
        '[project]\nos = "host"\narch = "host"\n'
        'name = "string_reference"\nsource = "src"\n')
    (project / "src" / "main" / "main.yh").write_text(generate_program(cases))

    env = dict(os.environ)
    env["YH_STDLIB"] = str(stdlib)
    result = run([str(compiler), f"-O{args.opt_level}", "run"], project, env, 1800)
    if result.returncode != 0:
        print(f"FAIL reference: build/run rc={result.returncode}\n"
              f"{result.stderr[-800:]}")
        return 1

    actual = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if not parts or parts[0] not in ("S", "V", "N"):
            continue
        case_id = int(parts[1])
        actual.setdefault(case_id, []).append(" ".join(parts))
    expected = {}
    for case_id, (op, payload) in enumerate(cases):
        line = expected_line(case_id, op, payload)
        expected[case_id] = line if isinstance(line, list) else [line]

    mismatches = 0
    for case_id, (op, payload) in enumerate(cases):
        got = actual.get(case_id, [])
        want = expected[case_id]
        if got != want:
            mismatches += 1
            print(f"FAIL case {case_id} {op} payload={payload!r}")
            print(f"  want={want}")
            print(f"  got ={got}")
            if mismatches >= 10:
                print("... 仅显示前 10 个差异")
                break
    if mismatches:
        return 1
    print(f"PASS reference: {len(cases)} 例与 Python 语义一致")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
