#!/usr/bin/env python3
"""固定 toml-test v2.2.0（TOML 1.1）decoder 一致性门。

构建 tests/modules/projects/tomltestdecoder 后，对 files-toml-1.1.0 清单中的
每个有效文件比较 tagged JSON 值树，对非法文件要求解码器返回非零。语料不
随仓库分发；首次运行用 --prepare 下载固定版本到 tmp/toml，并核对 SHA-256。

用法:
    python3 tests/toml/conformance.py --prepare
    python3 tests/toml/conformance.py
    python3 tests/toml/conformance.py --corpus tmp/toml/toml-test-2.2.0/tests
    python3 tests/toml/conformance.py --compiler ./yh --workdir tmp/toml-conf

退出码：全部通过 0；失败或缺语料 1。
"""

import argparse
import datetime
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CORPUS_VERSION = "2.2.0"
CORPUS_SHA256 = "fdab2779b3902eb08030f389a5d53e95c5b49404149ac6f2eda5227a5363c232"
CORPUS_URL = ("https://github.com/toml-lang/toml-test/archive/refs/tags/"
              f"v{CORPUS_VERSION}.tar.gz")
DEFAULT_CORPUS = ROOT / "tmp" / "toml" / f"toml-test-{CORPUS_VERSION}" / "tests"
FIXTURE = ROOT / "tests" / "modules" / "projects" / "tomltestdecoder"


def prepare() -> int:
    """下载并解压固定 toml-test 语料，校验 SHA-256。"""
    work = ROOT / "tmp" / "toml"
    work.mkdir(parents=True, exist_ok=True)
    archive = work / f"toml-test-v{CORPUS_VERSION}.tar.gz"
    if not archive.exists():
        print(f"下载 {CORPUS_URL}")
        with urllib.request.urlopen(CORPUS_URL, timeout=120) as response:
            archive.write_bytes(response.read())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != CORPUS_SHA256:
        print(f"语料 SHA-256 不匹配: {digest}")
        return 1
    target = work / f"toml-test-{CORPUS_VERSION}"
    if not (target / "tests" / "files-toml-1.1.0").exists():
        with tarfile.open(archive) as tar:
            tar.extractall(work)
    if not (target / "tests" / "files-toml-1.1.0").exists():
        print("解压后缺少 files-toml-1.1.0")
        return 1
    print(f"语料就绪: {target / 'tests'}")
    return 0


def is_value(node) -> bool:
    """与 toml-test json.go 一致：恰好 type/value 两个键才是值。"""
    return (isinstance(node, dict) and len(node) == 2
            and "type" in node and "value" in node)


def parse_datetime(text: str, kind: str):
    """把 tagged JSON 的日期时间字符串解析为可比较对象。"""
    value = text.replace(" ", "T").replace("t", "T").replace("z", "Z")
    if kind == "date-local":
        return datetime.date.fromisoformat(value)
    if kind == "time-local":
        if value.count(":") == 1:
            value += ":00"
        return datetime.time.fromisoformat(value)
    # datetime / datetime-local：补秒后再解析。
    date, _, rest = value.partition("T")
    if rest.count(":") == 1:
        cut = len(rest)
        for mark in ("Z", "+", "-"):
            index = rest.find(mark, 1)
            if index > 0:
                cut = index
                break
        rest = rest[:cut] + ":00" + rest[cut:]
    value = date + "T" + rest
    return datetime.datetime.fromisoformat(value)


def compare(expected, actual, path: str):
    """返回第一处差异描述；相等返回 None。"""
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return f"{path}: 期望数组，得到 {type(actual).__name__}"
        if len(expected) != len(actual):
            return f"{path}: 数组长度 {len(actual)} != {len(expected)}"
        for index, (want, got) in enumerate(zip(expected, actual)):
            diff = compare(want, got, f"{path}[{index}]")
            if diff:
                return diff
        return None
    if isinstance(expected, dict) and not is_value(expected):
        if not isinstance(actual, dict) or is_value(actual):
            return f"{path}: 期望表"
        if set(expected) != set(actual):
            return (f"{path}: 键集合不同 "
                    f"期望={sorted(expected)} 实际={sorted(actual)}")
        for key in expected:
            diff = compare(expected[key], actual[key], f"{path}/{key}")
            if diff:
                return diff
        return None
    if not is_value(expected):
        return f"{path}: 非法期望值 {expected!r}"
    if not is_value(actual):
        return f"{path}: 期望标量 {expected['type']}，实际不是 tagged 值"
    want_type = expected["type"]
    got_type = actual["type"]
    if want_type != got_type:
        return f"{path}: 类型 {got_type} != {want_type}"
    want = expected["value"]
    got = actual["value"]
    if want_type == "string":
        return None if got == want else f"{path}: 字符串不同"
    if want_type == "integer":
        return None if int(got) == int(want) else f"{path}: 整数 {got} != {want}"
    if want_type == "bool":
        return None if got == want else f"{path}: 布尔 {got} != {want}"
    if want_type == "float":
        if want.strip().lower().endswith("nan"):
            return None if math.isnan(float(got)) else f"{path}: 期望 nan"
        want_value = float(want)
        got_value = float(got)
        want_bits = int.from_bytes(struct.pack("<d", want_value), "little")
        got_bits = int.from_bytes(struct.pack("<d", got_value), "little")
        if want_bits != got_bits:
            return f"{path}: 浮点 {got!r} != {want!r}"
        return None
    if want_type in ("datetime", "datetime-local", "date-local", "time-local"):
        try:
            want_value = parse_datetime(want, want_type)
            got_value = parse_datetime(got, want_type)
        except Exception as error:  # noqa: BLE001 - 报告解析失败
            return f"{path}: 日期时间解析失败 {error}: {want!r} / {got!r}"
        if want_value != got_value:
            return f"{path}: 日期时间 {got!r} != {want!r}"
        return None
    return f"{path}: 未知类型 {want_type}"


def build_decoder(compiler: Path, stdlib: Path, work: Path) -> Path | None:
    """复制并构建 tagged JSON 解码器，返回二进制路径。"""
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(FIXTURE, work)
    env = dict(os.environ)
    env["YH_STDLIB"] = str(stdlib)
    built = subprocess.run([str(compiler), "build"], cwd=work,
                           capture_output=True, text=True, timeout=900,
                           env=env)
    binary = work / ".build" / "tomltestdecoder"
    if built.returncode != 0 or not binary.exists():
        print("解码器构建失败")
        print((built.stderr or built.stdout)[-1000:])
        return None
    return binary


def main() -> int:
    ap = argparse.ArgumentParser(description="toml-test v2.2.0 一致性门")
    ap.add_argument("--prepare", action="store_true",
                    help="下载并校验固定语料后退出")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS),
                    help="toml-test tests 目录（含 files-toml-1.1.0）")
    ap.add_argument("--compiler", default=str(ROOT / "yh"),
                    help="编译器路径（默认仓库根 ./yh）")
    ap.add_argument("--stdlib", default=str(ROOT / "libs"),
                    help="标准库根（默认仓库根 libs/）")
    ap.add_argument("--workdir", default=str(ROOT / "tmp" / "toml-conformance"),
                    help="解码器工作目录（默认 tmp/toml-conformance）")
    ap.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    ap.add_argument("--keep", action="store_true", help="保留工作目录")
    args = ap.parse_args()

    if args.prepare:
        return prepare()
    corpus = Path(args.corpus).resolve()
    manifest = corpus / "files-toml-1.1.0"
    if not manifest.exists():
        print(f"缺少语料清单: {manifest}")
        print("先运行: python3 tests/toml/conformance.py --prepare")
        return 1
    compiler = Path(args.compiler).resolve()
    stdlib = Path(args.stdlib).resolve()
    if not compiler.exists() or not (stdlib / "toml").is_dir():
        print("编译器或标准库路径无效")
        return 1
    work = Path(args.workdir).resolve()
    binary = build_decoder(compiler, stdlib, work)
    if binary is None:
        return 1

    entries = [line.strip() for line in manifest.read_text().splitlines()
               if line.strip()]
    valid = [e for e in entries
             if e.startswith("valid/") and e.endswith(".toml")]
    invalid = [e for e in entries
               if e.startswith("invalid/") and e.endswith(".toml")]
    failed = 0
    for relative in valid:
        path = corpus / relative
        expected = json.loads(path.with_suffix(".json").read_text())
        shown = subprocess.run([str(binary), str(path)], capture_output=True,
                               text=True, timeout=120)
        if shown.returncode != 0:
            failed += 1
            print(f"FAIL {relative}: 解码失败 rc={shown.returncode}")
            continue
        try:
            actual = json.loads(shown.stdout)
        except json.JSONDecodeError as error:
            failed += 1
            print(f"FAIL {relative}: JSON 非法 {error}: {shown.stdout[:200]!r}")
            continue
        diff = compare(expected, actual, "")
        if diff:
            failed += 1
            print(f"FAIL {relative}: {diff}")
    for relative in invalid:
        path = corpus / relative
        shown = subprocess.run([str(binary), str(path)], capture_output=True,
                               text=True, timeout=120)
        if shown.returncode == 0:
            failed += 1
            print(f"FAIL {relative}: 非法输入被接受")

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    total = len(valid) + len(invalid)
    print(f"toml-test {CORPUS_VERSION}: 通过 {total - failed}/{total}"
          f"（有效 {len(valid)}，非法 {len(invalid)}）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
