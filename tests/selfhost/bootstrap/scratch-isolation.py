#!/usr/bin/env python3
"""同时构建多个项目，验证项目扫描临时状态按编译进程隔离。"""

import argparse
import concurrent.futures
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).with_name("scratch-isolation.yh")


def make_project(parent: Path, index: int) -> Path:
    """生成目录较深的临时项目，增加并发目录扫描交错的机会。"""
    project = parent / f"project{index}"
    source = project / "src"
    source.mkdir(parents=True)
    (project / "project.toml").write_text(
        f'[project]\nos = "host"\narch = "host"\nname = "scratch{index}"\nsource = "src"\n',
        encoding="utf-8",
    )
    (source / "main.yh").write_bytes(FIXTURE.read_bytes())
    for directory in range(32):
        leaf = source / f"noise{directory}" / "nested"
        leaf.mkdir(parents=True)
        (leaf / "ignored.txt").write_text("scan entry\n", encoding="utf-8")
    return project


def build(compiler: Path, project: Path) -> tuple[str, int, str]:
    """构建一个独立临时项目，并返回其路径、状态码和诊断。"""
    result = subprocess.run(
        [str(compiler), "build"], cwd=project, capture_output=True,
        text=True, timeout=90,
    )
    return str(project), result.returncode, result.stdout + result.stderr


def main() -> int:
    """并发运行项目构建并检查所有产物均成功生成。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    temp_root = ROOT / "tmp"
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scratch-isolation-", dir=temp_root) as work:
        projects = [make_project(Path(work), index) for index in range(args.jobs)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(lambda project: build(compiler, project), projects))
        failures = []
        for index, (project, code, output) in enumerate(results):
            product = Path(project) / ".build" / f"scratch{index}"
            if code != 0 or not product.is_file():
                failures.append(f"{project}: exit={code}, product={product.exists()}\n{output[-1000:]}")
        if failures:
            print("并发项目扫描失败：\n" + "\n".join(failures))
            return 1
    print(f"并发项目扫描：通过 {args.jobs}/{args.jobs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
