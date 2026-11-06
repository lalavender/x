#!/usr/bin/env python3
"""手建 IRModule 验证 LLVM 全局字节布局、取址读写和拒绝边界；所有产物放 tmp。"""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/llvm-migration/global-backend"
ORACLE = r'''
#include <stdint.h>
extern int32_t read_scalar(void);
extern int32_t write_scalar(void);
extern unsigned char *string_addr(void);
extern const unsigned char public_const[4];
extern const unsigned char wide_bytes[16];
/* main：预期直接取手写布局和语义，不从 LLVM 文本或待测实现推导。 */
int main(void) {
    if (read_scalar() != 42 || write_scalar() != 57 || read_scalar() != 57) return 1;
    unsigned char *bytes = string_addr();
    if (bytes[0] != 34 || bytes[1] != 92 || bytes[2] != 255 || bytes[3] != 0) return 2;
    for (int i = 0; i < 4; ++i) if (public_const[i] != 0) return 3;
    for (int i = 0; i < 16; ++i) {
        unsigned char expected = i == 0 ? 1 : i == 8 ? 128 : i == 15 ? 65 : 0;
        if (wide_bytes[i] != expected) return 4;
    }
    return 0;
}
'''


def run(command, **kwargs):
    """运行单个真实工具并完整保留输出；统一超时避免构建子进程无限等待。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=300, **kwargs)


def main():
    """隔离编译模块构造器，再经 LLVM verifier 和 O0/O2 x64 原生调用验证产物。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    project = WORK / "fixture"
    shutil.rmtree(project, ignore_errors=True)
    shutil.copytree(ROOT / "tests/modules/projects/llvmglobalbackend", project)
    for name in ("gen", "ir"):
        shutil.copytree(ROOT / f"compiler/{name}", project / name)
        (project / name / "project.toml").write_text(f'[project]\nos = "host"\narch = "host"\nname = "{name}"\nsource = "."\n')
    shutil.copytree(ROOT / "compiler/support", project / "support")
    (project / "support/project.toml").write_text(
        '[project]\nos = "host"\narch = "host"\nname = "support"\nsource = "."\n')
    shutil.copytree(ROOT / "compiler/token", project / "token")
    (project / "token/project.toml").write_text(
        '[project]\nos = "host"\narch = "host"\nname = "token"\nsource = "."\n'
        '[dependencies]\nsupport = { path = "../support" }\n')
    (project / "gen/project.toml").write_text(
        '[project]\nos = "host"\narch = "host"\nname = "gen"\nsource = "."\n'
        '[dependencies]\nsupport = { path = "../support" }\n'
        'token = { path = "../token" }\n')
    (project / "backend").mkdir()
    for source in (ROOT / "compiler/backend").glob("llvm_*.yh"):
        if source.name != "llvm_bridge.yh":
            shutil.copy2(source, project / "backend" / source.name)
    (project / "backend/project.toml").write_text(
        '[project]\nos = "host"\narch = "host"\nname = "backend"\nsource = "."\n'
        '[dependencies]\ngen = { path = "../gen" }\nir = { path = "../ir" }\n'
        'support = { path = "../support" }\n')
    compiler = Path(args.compiler_path).resolve()
    result = run([str(compiler), "build"], cwd=project)
    (WORK / "build.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = run([str(project / ".build/llvmglobalbackend")], cwd=project)
    (WORK / "generator.log").write_text(result.stderr)
    assert result.returncode == 0, result.stderr
    assert 'global-backend.yh:2:1: 错误:' in result.stderr, result.stderr
    assert "LLVM 模块未通过 IR verifier" in result.stderr and "尚不支持未定义全局" in result.stderr, result.stderr
    text = result.stdout
    assert '@"zero_pair" = internal global [16 x i8] zeroinitializer, align 16' in text
    assert '@".LD7" = internal constant [4 x i8] c"\\22\\5C\\FF\\00", align 1' in text
    assert '@"scalar" = global [4 x i8] c"*\\00\\00\\00", align 4' in text
    assert '@"null_ptr" = internal global [8 x i8] zeroinitializer, align 8' in text
    assert '@"zero_union" = internal global [8 x i8] zeroinitializer, align 8' in text
    assert '@"public_const" = constant [4 x i8] zeroinitializer, align 4' in text
    assert '@"wide_bytes" = constant [16 x i8] c"\\01\\00\\00\\00\\00\\00\\00\\00\\80\\00\\00\\00\\00\\00\\00A", align 1' in text
    assert 'getelementptr i8, ptr @"scalar", i64 0' in text
    assert 'getelementptr i8, ptr @".LD7", i64 0' in text
    irfile = WORK / "globals.ll"
    irfile.write_text(text)
    oracle = WORK / "oracle.c"
    oracle.write_text(ORACLE)
    result = run(["/usr/bin/opt-21", "-passes=verify", "-disable-output", str(irfile)])
    assert result.returncode == 0, result.stderr
    for level in (0, 2):
        obj = WORK / f"globals-O{level}.o"
        result = run(["/usr/bin/clang-21", "-x", "ir", f"-O{level}", "-c", str(irfile), "-o", str(obj)])
        assert result.returncode == 0, result.stderr
        binary = WORK / f"globals-O{level}"
        result = run(["/usr/bin/gcc", "-no-pie", str(oracle), str(obj), "-o", str(binary)])
        assert result.returncode == 0, result.stderr
        result = run([str(binary)])
        assert result.returncode == 0, f"O{level}: {result}"
    print("LLVM 全局后端通过：字节布局/链接可变性/对齐/全局读写/指针返回/拒绝边界/O0+O2 原生运行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
