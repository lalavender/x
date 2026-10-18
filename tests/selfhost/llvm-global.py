#!/usr/bin/env python3
"""LL5 全局数据门：真实前端、精确初始化字节、O0/O2 验证与原生 C 驱动。

与 tests/yh-run/run/llvm-global.yh 共用正例，覆盖全局整数/bool/char/enum、
零初始化、NULL 指针字段/元素、数组/嵌套结构体/union、pub/private const、
全局取址与读写、副本、切片基址、全部旧字符串转义/NUL/UTF-8/标签去重。
不支持的全局对象必须在 lowering 带声明来源拒绝，并且不发布 LLVM 或可执行产物。
"""

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/llvm-migration/llvm-global"
TARGET = "x86_64-unknown-linux-gnu"
SOURCE = ROOT / "tests/yh-run/run/llvm-global.yh"
FIXTURES = ROOT / "tests/modules/projects/llvmlower/input"
REJECTS = {
    "globalreject": "rejected_slice",
    "globalrejectfloat": "rejected_float",
    "globalrejectfloatzero": "rejected_float_zero",
    "globalrejectnumericptr": "numeric",
    "globalrejectstringint": "numeric",
    "globalrejectfloatcast": "rejected_float_cast",
    "globalrejectdepth": "rejected_pointer_depth",
}
ACCEPTS = {
    "globalrejectptr": 97,
    "globalrejectfield": 97,
    "globalrejectelement": 97,
    "globalrejectct": 3,
}

DRIVER = r"""/* 手工边界驱动：独立读取导出常量与全局地址，避免只依赖 yh 内部比较。 */
#include <stdint.h>
#include <stdio.h>

extern int32_t global_case(void);
extern int32_t global_value(void);
extern int32_t *global_address(void);
extern const unsigned char *global_padded(void);
extern unsigned char global_const_bool(void);
extern int32_t *global_const_address(void);
extern int64_t global_positive_wide(void);
extern const unsigned char *global_string(void);
extern const unsigned char *global_empty_string(void);
extern const unsigned char *global_utf8_string(void);
extern unsigned char *global_writable_string(void);
extern unsigned char *global_string_alias(void);
extern const int32_t PUBLIC_TABLE[3];
extern const int32_t PUBLIC_POINT[2];

/* main：检查初值、对象身份、独立聚合常量以及包含 NUL 的完整字符串字节。 */
int main(void) {
    if (global_value() != 41) return 101;
    int32_t *address = global_address();
    if (*address != 41 || address != global_address()) return 102;
    const unsigned char *padded = global_padded();
    for (unsigned i = 1; i < 8; i++) if (padded[i] != 0) return 111;
    for (unsigned i = 17; i < 24; i++) if (padded[i] != 0) return 112;
    if (global_const_bool() != 2) return 113;
    if (global_positive_wide() != INT64_C(4294967297)) return 119;
    unsigned char *writable = global_writable_string();
    unsigned char *alias = global_writable_string();
    if (writable != alias || alias[0] != 119) return 114;
    writable[1] = 82;
    if (alias[1] != 82 || global_writable_string()[1] != 82) return 115;
    int32_t *const_address = global_const_address();
    if (*const_address != 41 || const_address != global_const_address()) return 116;
    *const_address = 45;
    if (*global_const_address() != 45) return 117;
    int32_t status = global_case();
    if (status != 0) { printf("global_case=%d\n", status); return status; }
    if (global_value() != 52 || *address != 52) return 103;
    *address = 73;
    if (global_value() != 73) return 104;
    if (PUBLIC_TABLE[0] != 7 || PUBLIC_TABLE[1] != 8 || PUBLIC_TABLE[2] != 9) return 105;
    if (PUBLIC_POINT[0] != 23 || PUBLIC_POINT[1] != 29) return 106;
    static const unsigned char expected[] = {65,10,13,9,7,8,12,11,39,34,92,66,0,67,0};
    const unsigned char *text = global_string();
    if (text != global_string()) return 107;
    for (unsigned i = 0; i < sizeof(expected); i++) {
        if (text[i] != expected[i]) return 108;
    }
    static const unsigned char utf8[] = {233,155,170,0};
    const unsigned char *wide = global_utf8_string();
    for (unsigned i = 0; i < sizeof(utf8); i++) if (wide[i] != utf8[i]) return 109;
    if (global_empty_string()[0] != 0) return 110;
    if (alias[0] != 87 || *const_address != 47) return 118;
    unsigned char *string_alias = global_string_alias();
    static const unsigned char alias_expected[] = {65,108,105,97,115,0};
    if (string_alias != global_string_alias()) return 120;
    for (unsigned i = 0; i < sizeof(alias_expected); i++) {
        if (string_alias[i] != alias_expected[i]) return 121;
    }
    string_alias[1] = 76;
    if (global_string_alias()[1] != 76) return 122;
    puts("global=ok");
    return 0;
}
"""


def run(command):
    """执行真实候选与差分工具，保留诊断并限定单条命令执行时间。"""
    return subprocess.run(command, cwd=WORK, capture_output=True, text=True, timeout=300)


def locate(*names):
    """优先使用宿主工具，避免 PATH 中交叉 gcc 包装器改变 C 驱动架构。"""
    for name in names:
        fallback = Path("/usr/bin") / name
        if fallback.is_file():
            return str(fallback)
        found = shutil.which(name)
        if found:
            return found
    return None


def emit_text(compiler, source, level, output):
    """直接调用候选发射 LLVM，文本不经过桥或旧后端；失败时保留来源诊断。"""
    result = run([compiler, "--emit-asm", "--backend", "llvm", "--target", TARGET,
                  f"-O{level}", "--emit-llvm", str(source)])
    assert result.returncode == 0, (
        f"O{level} 全局 LLVM 发射失败 rc={result.returncode}\n{result.stderr[-1600:]}")
    output.write_text(result.stdout, encoding="utf-8")
    return result.stdout


def decode_bytes(value, size):
    """将 LLVM 字节数组常量还原为真实字节，用独立手工值检查序列化结果。"""
    if value == "zeroinitializer":
        return bytes(size)
    token = value[2:-1]
    result = bytearray()
    i = 0
    while i < len(token):
        if token[i] == "\\":
            result.append(int(token[i + 1:i + 3], 16))
            i += 3
        else:
            result.append(ord(token[i]))
            i += 1
    assert len(result) == size, f"初始化字节数不匹配: {len(result)} != {size}"
    return bytes(result)


def check_text(text, level):
    """检查对象类型/链接/对齐/精确字节，并确保同一字符串标签只登记一次。"""
    globals = {}
    pattern = re.compile(
        r'^@"([^"]+)" = (internal )?(global|constant) \[(\d+) x i8\] '
        r'(zeroinitializer|c"(?:[^"\\]|\\[0-9a-fA-F]{2})*"), align (\d+)$')
    for line in text.splitlines():
        match = pattern.fullmatch(line)
        if match:
            name, linkage, kind, size, value, align = match.groups()
            assert name not in globals, f"O{level} 全局标签重复定义: {name}"
            globals[name] = (linkage or "", kind, int(align), decode_bytes(value, int(size)))
    for name, size in {
        "zero_int": 4, "zero_i8": 1, "zero_u8": 1, "zero_i16": 2, "zero_u16": 2,
        "zero_i32": 4, "zero_u32": 4, "zero_i64": 8, "zero_u64": 8,
        "zero_bool": 1, "zero_char": 1, "zero_mode": 4, "zero_ptr": 8,
        "zero_array": 12, "zero_point": 8, "zero_box": 16, "zero_cell": 8,
        "null_ptr": 8, "nulls": 16,
    }.items():
        assert name in globals, f"O{level} 缺少全局声明: {name}"
        assert globals[name][0:2] == ("internal ", "global"), (name, globals[name])
        assert globals[name][3] == bytes(size), (name, globals[name])
    # 期望值直接列出小端字节，未复用编译器物化算法。
    expected = {
        "mutable_i32": (4, bytes([41, 0, 0, 0])),
        "signed_byte": (1, bytes([130])),
        "unsigned_byte": (1, bytes([250])),
        "signed_half": (2, bytes([255, 255])),
        "unsigned_half": (2, bytes([96, 234])),
        "unsigned_word": (4, bytes([152, 186, 220, 254])),
        "signed_wide": (8, bytes([255, 255, 255, 255, 254, 255, 255, 255])),
        "unsigned_wide": (8, bytes([16, 50, 84, 118, 152, 186, 220, 254])),
        "truth": (1, bytes([1])), "raw_truth": (1, bytes([2])), "letter": (1, bytes([81])),
        "mode": (4, bytes([7, 0, 0, 0])),
        "values": (2, bytes([254, 255, 3, 0, 4, 1])),
        "padded": (8, bytes([5] + [0] * 7 + [247] + [255] * 7 + [1] + [0] * 15)),
        "nested": (4, bytes([2, 0, 0, 0, 11, 0, 0, 0, 13, 0, 0, 0, 252, 255, 0, 0])),
    }
    for name, (align, data) in expected.items():
        assert globals.get(name) == ("internal ", "global", align, data), (name, globals.get(name))
    for name, linkage, data in (
        ("PUBLIC_TABLE", "", bytes([7, 0, 0, 0, 8, 0, 0, 0, 9, 0, 0, 0])),
        ("PRIVATE_TABLE", "internal ", bytes([17, 0, 0, 0, 19, 0, 0, 0])),
        ("PUBLIC_POINT", "", bytes([23, 0, 0, 0, 29, 0, 0, 0])),
        ("PRIVATE_POINT", "internal ", bytes([31, 0, 0, 0, 37, 0, 0, 0])),
        ("WRITABLE_CONST", "internal ", bytes([41, 0, 0, 0, 43, 0, 0, 0])),
    ):
        assert globals.get(name) == (linkage, "global", 4, data), (name, globals.get(name))
    for name in ("ANSWER", "YES", "LETTER", "MODE", "RAW_TRUTH", "TEXT", "ALIAS", "CHAIN"):
        assert name not in globals, f"标量 const 不应分配运行期对象: {name}"
    strings = {name: row for name, row in globals.items() if name.startswith(".LD")}
    assert len(strings) == 6, f"字符串标签数应为 6（按标签去重）: {strings}"
    assert {row[3] for row in strings.values()} == {
        bytes([65, 10, 13, 9, 7, 8, 12, 11, 39, 34, 92, 66, 0, 67, 0]),
        bytes([0]), bytes([233, 155, 170, 0]), bytes([108, 111, 111, 112, 0]),
        bytes([119, 114, 105, 116, 97, 98, 108, 101, 0]),
        bytes([97, 108, 105, 97, 115, 0]),
    }, strings
    assert all(row[0:3] == ("internal ", "global", 1) for row in strings.values()), strings
    for token in ('getelementptr i8, ptr @"', "llvm.memmove", "load i32", "store i32"):
        assert token in text, f"O{level} 缺少全局访问/副本 lowering: {token}"


def check_rejects(compiler):
    """拒绝合法前端输入的未支持全局，检查声明来源并确保没有部分发布。"""
    for name, declaration in REJECTS.items():
        source = FIXTURES / f"{name}.yh"
        for emit in (True, False):
            output = WORK / f"{name}-out"
            command = [compiler, "--backend", "llvm", "--target", TARGET, "-O0"]
            command += ["--emit-asm", "--emit-llvm"] if emit else ["-o", str(output)]
            result = run(command + [str(source)])
            (WORK / f"{name}-{'text' if emit else 'binary'}.log").write_text(
                result.stdout + result.stderr, encoding="utf-8")
            assert result.returncode > 0, f"{name} 未正常拒绝: {result.returncode}"
            assert re.search(rf"{name}\.yh:\d+:\d+:", result.stderr), result.stderr[-1200:]
            assert "LLVM lowering" in result.stderr and declaration in result.stderr, result.stderr[-1200:]
            assert 'target triple' not in result.stdout, f"{name} 拒绝时仍发布部分 LLVM"
            assert not output.exists(), f"{name} 拒绝时仍发布可执行产物"


def check_newly_supported(compiler, tools):
    """运行此前误列为拒绝的全局重定位与 CT 聚合初始化正例。"""
    for name, expected in ACCEPTS.items():
        source = FIXTURES / f"{name}.yh"
        emitted = run([compiler, "--emit-asm", "--backend", "llvm", "--target", TARGET,
                       "-O0", "--emit-llvm", str(source)])
        assert emitted.returncode == 0, f"{name} 应接受全局初始化:\n{emitted.stderr[-1000:]}"
        llfile = WORK / f"{name}.ll"
        llfile.write_text(emitted.stdout, encoding="utf-8")
        verified = run([tools["opt"], "-passes=verify", "-disable-output", str(llfile)])
        assert verified.returncode == 0, f"{name} LLVM verifier 失败:\n{verified.stderr[-1000:]}"
        obj = WORK / f"{name}.o"
        assembled = run([tools["clang"], "-c", str(llfile), "-o", str(obj)])
        assert assembled.returncode == 0, f"{name} LLVM 汇编失败:\n{assembled.stderr[-1000:]}"
        executable = WORK / f"{name}-run"
        linked = run([tools["cc"], "-no-pie", str(obj), "-o", str(executable)])
        assert linked.returncode == 0, f"{name} 链接失败:\n{linked.stderr[-1000:]}"
        result = run([str(executable)])
        assert result.returncode == expected, (
            f"{name} 运行码不符，期望 {expected}: rc={result.returncode}\n{result.stderr[-600:]}")


def main():
    """发射共用源、检查初始化数据、运行 O0/O2 C 驱动并执行严格拒绝门。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    assert Path(compiler).is_file(), f"编译器不存在: {compiler}"
    tools = {name: locate(*candidates) for name, candidates in {
        "clang": ("clang",), "opt": ("opt",), "cc": ("gcc", "cc")}.items()}
    missing = [name for name, path in tools.items() if path is None]
    assert not missing, f"LL5 差分工具缺失: {missing}"
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    source = WORK / "global.yh"
    # 删除共享源的旧后端入口，只让 C 驱动提供 main；所有被测函数和声明原样使用。
    shared = SOURCE.read_text(encoding="utf-8").split("// main：", 1)
    assert len(shared) == 2, "共享源缺少明确的 main 分界"
    source.write_text("module globalcase;\n" + shared[0], encoding="utf-8")
    driver = WORK / "driver.c"
    driver.write_text(DRIVER, encoding="utf-8")
    for level in (0, 2):
        llfile = WORK / f"global-O{level}.ll"
        text = emit_text(compiler, source, level, llfile)
        check_text(text, level)
        result = run([tools["opt"], "-passes=verify", "-S", str(llfile), "-o", os.devnull])
        assert result.returncode == 0, f"O{level} opt 验证失败\n{result.stderr[-1600:]}"
        obj_source = llfile
        if level == 2:
            obj_source = WORK / "global-O2-opt.ll"
            result = run([tools["opt"], "-S", "-passes=default<O2>", str(llfile),
                          "-o", str(obj_source)])
            assert result.returncode == 0, f"O2 管线失败\n{result.stderr[-1600:]}"
        obj = WORK / f"global-O{level}.o"
        result = run([tools["clang"], "-c", str(obj_source), "-o", str(obj)])
        assert result.returncode == 0, f"O{level} clang 汇编失败\n{result.stderr[-1600:]}"
        executable = WORK / f"global-O{level}"
        result = run([tools["cc"], "-std=c11", "-O2", "-no-pie", str(driver), str(obj), "-o", str(executable)])
        assert result.returncode == 0, f"O{level} C 驱动链接失败\n{result.stderr[-1600:]}"
        result = run([str(executable)])
        assert result.returncode == 0 and result.stdout == "global=ok\n", (
            f"O{level} C 驱动失败 rc={result.returncode}\n{result.stdout}\n{result.stderr[-800:]}")
    check_rejects(compiler)
    check_newly_supported(compiler, tools)
    print("LL5 全局数据通过：精确初始化/链接/读写取址/聚合副本/字符串、O0/O2 原生 C 驱动、十一类来源拒绝")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
