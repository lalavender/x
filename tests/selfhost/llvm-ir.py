#!/usr/bin/env python3
"""LL3 文本发射门：真实 yh 模块构造器 → 静态 LLVM 桥 → x64 O0/O2 原生执行。"""
import argparse
import json
import os
import re
from pathlib import Path
import runpy
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'tmp/llvm-migration/llvm-emitter'
ORACLE = r'''
#include <stdint.h>
#include <limits.h>
extern int yh_scalar_main(void);
extern int64_t add32(int32_t, int32_t) __asm__("add.i32");
extern int32_t left32(int32_t, int32_t) __asm__("shift.i32");
extern int32_t right32(int32_t, int32_t) __asm__("right.i32");
extern uint32_t uright32(uint32_t, uint32_t) __asm__("right.u32");
extern int64_t divide64(int64_t, int64_t) __asm__("divide.i64");
extern int64_t remainder64(int64_t, int64_t) __asm__("remainder.i64");
extern uint64_t udivide64(uint64_t, uint64_t) __asm__("divide.u64");
extern uint64_t uremainder64(uint64_t, uint64_t) __asm__("remainder.u64");
extern int64_t left64(int64_t, int64_t) __asm__("shift.i64");
extern uint64_t uright64(uint64_t, uint64_t) __asm__("right.u64");
extern int64_t divide32(int32_t, int32_t) __asm__("divide.i32");
extern int32_t boolcast(int64_t) __asm__("bool.cast");
extern uint8_t choose(uint8_t) __asm__("choose.byte");
extern int64_t narrow16(int64_t) __asm__("narrow.i16");
extern uint64_t narrow8(int64_t) __asm__("narrow.u8");
/* main：预期来自契约与 C 定宽常量，独立于 yh 构造器和 LLVM 文本中的常量。 */
int main(void) {
    if (yh_scalar_main()) return 1;
    if (add32(INT32_MAX, 1) != INT32_MIN) return 2;
    if (left32(1, 32) != 0 || left32(1, 64) != 1 || left32(1, -1) != 0) return 3;
    if (right32(-2, 32) != -1 || uright32(UINT32_MAX, 32) != 0) return 4;
    if (divide64(INT64_MIN, -1) != INT64_MIN || remainder64(INT64_MIN, -1) != 0) return 5;
    if (divide64(INT64_MIN, 0) != 0 || remainder64(INT64_MIN, 0) != INT64_MIN) return 6;
    if (divide64(-17, 5) != -3 || remainder64(-17, 5) != -2) return 7;
    if (udivide64(UINT64_MAX, 2) != INT64_MAX || uremainder64(UINT64_MAX, 0) != UINT64_MAX) return 8;
    if (left64(1, 63) != INT64_MIN || left64(1, 64) != 1 || uright64(UINT64_MAX, UINT64_MAX) != 1) return 9;
    if (divide32(INT32_MIN, -1) != INT32_MIN) return 10;
    if (boolcast(2) != 2 || boolcast(-2) != 254 || choose(2) != 254 || choose(0) != 7) return 11;
    if (narrow16(32768) != -32768 || narrow8(-1) != 255) return 12;
    return 0;
}
'''


def run(command, **kwargs):
    """执行构建/测试工具并保留原始输出；超时视为门失败。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=300, **kwargs)


def main():
    """先编译真实 .yh 发射器，再用固定 SDK 验证 IR 与实际整数边界行为。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler-path', default=str(ROOT / 'yh'))
    parser.add_argument('--suite', choices=['scalar'], default='scalar')
    args = parser.parse_args()
    project = WORK / 'scalar'
    WORK.mkdir(parents=True, exist_ok=True)
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(ROOT / 'tests/modules/projects/llvmscalar', project)
    for name in ('gen', 'ir'):
        shutil.copytree(ROOT / f'compiler/{name}', project / name)
        (project / name / 'project.toml').write_text(f'[project]\nname = "{name}"\nsource = "."\n')
    (project / 'backend').mkdir()
    for source in (ROOT / 'compiler/backend').glob('llvm_*.yh'):
        shutil.copy2(source, project / 'backend' / source.name)
    (project / 'backend/project.toml').write_text('[project]\nname = "backend"\nsource = "."\n'
        '[dependencies]\ngen = { path = "../gen" }\nir = { path = "../ir" }\n')
    compiler = Path(args.compiler_path).resolve()
    result = run([str(compiler), 'build'], cwd=project)
    (WORK / 'build.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = run([str(project / '.build/llvmscalar')], cwd=project)
    (WORK / 'generator.log').write_text(result.stderr)
    assert result.returncode == 0, result.stderr
    assert 'fixture"\\测试.yh:2:1: 错误:' in result.stderr, result.stderr
    counts = re.search(r'LL3 fixture: functions=(\d+) cases=(\d+) maps=(\d+)', result.stderr)
    assert counts, result.stderr
    emitted, cases, maps = map(int, counts.groups())
    assert emitted == result.stdout.count('define ') and cases >= 40 and maps > emitted
    irfile = WORK / 'scalar.ll'
    irfile.write_text(result.stdout)
    oracle = WORK / 'oracle.c'
    oracle.write_text(ORACLE)
    common = runpy.run_path(str(ROOT / 'tests/selfhost/llvm-embedded.py'))
    client, obj, executable = WORK / 'client.c', WORK / 'client.o', WORK / 'bridge-client'
    client.write_text(common['CLIENT'])
    result = run(['/usr/bin/gcc', '-O2', '-I' + str(ROOT / 'compiler/llvm'), '-c', str(client), '-o', str(obj)])
    assert result.returncode == 0, result.stderr
    result = run(['/usr/bin/python3', str(ROOT / 'tools/llvm-sdk.py'), 'link', '--host', 'linux-x86_64',
                  '--object', str(obj), '--output', str(executable)])
    assert result.returncode == 0, result.stdout + result.stderr
    env = dict(os.environ, PATH=str(WORK / 'no-tools'))
    (WORK / 'no-tools').mkdir(exist_ok=True)
    for opt in (0, 2):
        target = WORK / f'scalar-O{opt}.o'
        result = run([str(executable), str(irfile), 'x86_64-unknown-linux-gnu', str(opt), '0', str(target), 'probe'], env=env)
        assert result.returncode == 0, result.stderr
        data = target.read_bytes()
        assert data[:5] == b'\x7fELF\x02' and int.from_bytes(data[18:20], 'little') == 62
        binary = WORK / f'scalar-O{opt}'
        result = run(['/usr/bin/gcc', '-no-pie', str(target), '-o', str(binary)])
        assert result.returncode == 0, result.stderr
        result = run([str(binary)], env=env)
        assert result.returncode == 0, f'O{opt}: {result}'
        renamed = WORK / f'oracle-O{opt}.o'
        result = run(['/usr/bin/objcopy', '--redefine-sym', 'main=yh_scalar_main', str(target), str(renamed)])
        assert result.returncode == 0, result.stderr
        oracle_binary = WORK / f'oracle-O{opt}'
        result = run(['/usr/bin/gcc', '-O2', '-no-pie', str(oracle), str(renamed), '-o', str(oracle_binary)])
        assert result.returncode == 0, result.stderr
        result = run([str(oracle_binary)], env=env)
        assert result.returncode == 0, f'O{opt} 独立字面量 oracle: {result}'
        assembly = WORK / f'scalar-O{opt}.s'
        result = run([str(executable), str(irfile), 'x86_64-unknown-linux-gnu', str(opt), '1', str(assembly), 'probe'], env=env)
        assert result.returncode == 0, result.stderr
    (WORK / 'report.json').write_text(json.dumps({'o0_o2': True, 'machine': 62,
        'functions': emitted, 'cases': cases, 'source_maps': maps, 'fallback': 0, 'independent_oracle': True,
        'scope': '真实 IRModule → .yh 文本发射器 → 静态 LLVM；前端/cmd 接入由总门验收'}, ensure_ascii=False, indent=2))
    print('LL3 文本发射通过：真实模块、O0/O2 验证/对象/汇编、x64 原生运行、无 LLVM 工具 PATH')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
