#!/usr/bin/env python3
"""性能冻结输入在 Windows CRLF 检出后仍按入库 LF 校验，内容改动必须拒绝。"""

import importlib.util
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("performance", ROOT / "tools/compiler-performance.py")
performance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(performance)


def main() -> int:
    """用真实冻结语料的副本验证行尾等价、内容篡改拒绝与复制规范化。"""
    with tempfile.TemporaryDirectory(dir=ROOT / "tmp", prefix="perf-input-") as temp:
        work = Path(temp)
        corpus = work / "corpus"
        shutil.copytree(performance.CORPUS, corpus)
        performance.CORPUS = corpus
        performance.FROZEN_PROJECT = corpus / "compiler"
        sources = sorted(performance.FROZEN_PROJECT.rglob("*.yh"))
        for source in sources:
            source.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
        manifest = performance.FROZEN_PROJECT / "project.toml"
        manifest.write_bytes(manifest.read_bytes().replace(b"\r\n", b"\n"))
        expected = performance.verify_corpus()
        for source in sources:
            source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
        assert performance.verify_corpus() == expected, "CRLF 改变冻结输入统计"
        copied = performance.make_project(work / "copy")
        for source in copied.rglob("*.yh"):
            assert b"\r\n" not in source.read_bytes(), "临时性能负载未规范化为 LF"
        sources[0].write_bytes(sources[0].read_bytes() + "// 内容变化\n".encode("utf-8"))
        try:
            performance.verify_corpus()
        except RuntimeError as error:
            assert "冻结语料校验失败" in str(error)
        else:
            raise AssertionError("冻结语料内容篡改被接受")
    print("性能冻结输入门通过：LF/CRLF 等价、内容篡改拒绝、临时负载 LF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
