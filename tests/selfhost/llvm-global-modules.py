#!/usr/bin/env python3
"""LL5 多模块门：用真实 .yh 前端构建导入聚合副本与模块私有数据。"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/modules/projects/llvmprivate"
WORK = ROOT / "tmp/ll5-complete/global-modules"
TARGET = "x86_64-unknown-linux-gnu"


def run(command, cwd, env=None):
    """执行候选编译器或目标程序，并将失败输出留给调用方诊断。"""
    return subprocess.run(command, cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=300)


def main():
    """O0/O2 分别冷构建多模块项目，检查链接可见性与真实运行结果。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    # 本专项显式生成 x86_64 对象；让项目最终链接优先使用 WSL 原生 gcc，
    # 避免仓库日常 AArch64 交叉 gcc 包装器误接 x86_64 模块对象。
    build_env = dict(os.environ)
    build_env["PATH"] = "/usr/bin:/bin:" + build_env.get("PATH", "")
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)

    for level in (0, 2):
        project = WORK / f"O{level}"
        shutil.copytree(FIXTURE, project)
        command = [compiler, "--backend", "llvm", "--target", TARGET,
                   f"-O{level}", "build", "--emit-llvm"]
        built = run(command, project, build_env)
        (project / "build.log").write_text(built.stdout + built.stderr, encoding="utf-8")
        assert built.returncode == 0, (
            f"O{level} 多模块 LLVM 构建失败\n{built.stdout[-1200:]}\n{built.stderr[-2000:]}")

        iface_dir = project / ".build" / "iface"
        iface_files = list(iface_dir.glob("*.s.i"))
        ct_files = list(iface_dir.glob("*.s.ct"))
        assert len(iface_files) == 2 and len(ct_files) == 2, (
            f"O{level} 应分别发射 data/main 的 .s.i 与 .s.ct: "
            f"{iface_files}, {ct_files}")
        data_iface = next(path for path in iface_files if path.name.endswith("-data.s.i"))
        main_iface = next(path for path in iface_files if path.name.endswith("-main.s.i"))
        data_ct = next(path for path in ct_files if path.name.endswith("-data.s.ct"))
        assert ("pub const PUBLIC_TABLE [3]int = " in data_iface.read_text(encoding="utf-8")
                and "$__yhct_make_public_table__" in data_iface.read_text(encoding="utf-8")), (
            "data .s.i 未序列化并重写 CT 聚合初始化式")
        assert "same_private_data" not in main_iface.read_text(encoding="utf-8"), (
            "main .s.i 暴露了 data 模块私有对象")
        assert "make_public_table" in data_ct.read_text(encoding="utf-8"), (
            "data .s.ct 未序列化 CT 初始化函数闭包")

        executable = project / ".build" / "llvmprivate"
        assert executable.is_file(), f"O{level} 项目产物缺失: {executable}"
        result = run([str(executable)], project)
        assert result.returncode == 0, (
            f"O{level} 多模块运行失败 rc={result.returncode}\n{result.stdout}\n{result.stderr}")

        ll_files = list((project / ".build" / "llvm").glob("*.ll"))
        assert len(ll_files) == 2, f"O{level} 应恰有 main/data 两个 LLVM 模块: {ll_files}"
        texts = {path.read_text(encoding="utf-8") for path in ll_files}
        main_text = next((text for text in texts if '".LI' in text), "")
        data_text = next((text for text in texts if 'PUBLIC_TABLE__llvmprivate__data_' in text), "")
        assert main_text and data_text, f"O{level} 缺少消费者副本或提供方导出对象"
        assert 'internal global' in main_text and '".LI' in main_text, main_text
        assert 'global [12 x i8]' in data_text and 'PUBLIC_TABLE__llvmprivate__data_' in data_text, data_text
        assert '"same_private_data"' not in main_text + data_text, (
            f"O{level} 源私有对象名泄漏到 LLVM 符号: {main_text + data_text}")

        objects = list((project / ".build" / "asm").glob("*.o"))
        assert len(objects) == 2, f"O{level} 应有两个模块对象: {objects}"
        symbols = run(["/usr/bin/nm", "-g", "--defined-only", *map(str, objects)], project)
        assert symbols.returncode == 0, symbols.stderr
        assert "same_private_data" not in symbols.stdout and ".LI" not in symbols.stdout
        assert "PUBLIC_TABLE" in symbols.stdout

    print("LL5 跨模块数据通过：pub const 本地副本、私有同名对象隔离、getter/setter 状态共享、O0/O2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
