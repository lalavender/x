#!/usr/bin/env python3
"""LL2 模块 IR 门：编译真实跨模块模型，并运行所有权和坏模块拒绝探针。"""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'tmp/llvm-migration/ir-module'


def main():
    """使用指定候选构建隔离项目；所有编译产物与日志均放 tmp。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler-path', default=str(ROOT / 'yh'))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    project = WORK / 'model'
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(ROOT / 'tests/modules/projects/llvmmodule', project)
    shutil.copytree(ROOT / 'compiler/ir', project / 'ir')
    (project / 'ir/project.toml').write_text('[project]\nos = "host"\narch = "host"\nname = "ir"\nsource = "."\n')
    result = subprocess.run([str(compiler), 'build'], cwd=project,
                            capture_output=True, text=True, timeout=180)
    (WORK / 'build.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(project / '.build/llvmmodule')], cwd=project,
                            capture_output=True, text=True, timeout=60)
    (WORK / 'run.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0 and result.stdout == 'module-model=ok\n', result
    print('LL2 模块 IR 通过：完整模型/深拷贝/目标/布局/重定位/函数 verifier/重复释放')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
