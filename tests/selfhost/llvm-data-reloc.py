#!/usr/bin/env python3
"""LL5 后端门：真实 IRModule 序列化读回后验证重定位、切片布局和重叠副本。"""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/ll5-complete/backend-data"
DRIVER = r'''
#include <stdint.h>
#include <string.h>
extern unsigned char *base_address(void);
extern void copy_bytes(void *, const void *);
extern unsigned char record[40];
extern struct { uint64_t len; int32_t *ptr; } view, empty_view;
extern void *pointers[3];
/* main：手写布局/地址预期独立于待测发射器，正反向重叠均按原始副本判定。 */
int main(void) {
    unsigned char *base = base_address();
    uintptr_t first, second;
    memcpy(&first, record + 8, 8); memcpy(&second, record + 24, 8);
    if (record[0] != 17 || record[16] != 6 || record[32] != 34) return 1;
    if (first != (uintptr_t)base + 8 || second != (uintptr_t)base - 4) return 2;
    for (unsigned i = 1; i < 40; i++) {
        if ((i >= 8 && i < 17) || (i >= 24 && i < 33)) continue;
        if (record[i] != 0) return 3;
    }
    if ((uintptr_t)record % 16 != 0) return 4;
    if (view.len != 3 || view.ptr != (int32_t *)(base + 4)
        || view.ptr[0] != 20 || view.ptr[1] != 30 || view.ptr[2] != 40) return 5;
    view.ptr[1] = 77;
    if (*(int32_t *)(base + 8) != 77) return 6;
    if (empty_view.len != 0 || empty_view.ptr != 0) return 7;
    if (pointers[0] != base + 12 || pointers[1] != base + 4) return 8;
    if (((int (*)(void))pointers[2])() != 99) return 9;
    unsigned char data[532];
    for (unsigned i = 0; i < 532; i++) data[i] = (unsigned char)i;
    copy_bytes(data + 4, data);
    for (unsigned i = 0; i < 512; i++) if (data[i + 4] != (unsigned char)i) return 10;
    for (unsigned i = 0; i < 532; i++) data[i] = (unsigned char)i;
    copy_bytes(data, data + 4);
    for (unsigned i = 0; i < 512; i++) if (data[i] != (unsigned char)(i + 4)) return 11;
    copy_bytes(data, data);
    for (unsigned i = 0; i < 512; i++) if (data[i] != (unsigned char)(i + 4)) return 12;
    return 0;
}
#ifdef YH_NO_LIBC
/* _start：独立测试入口按 SysV 对齐栈，只用 Linux exit syscall 退出。 */
__asm__(".globl _start\n_start:\n xor %rbp,%rbp\n and $-16,%rsp\n"
        " call main\n mov %eax,%edi\n mov $60,%eax\n syscall\n");
#endif
'''


def run(command, **kwargs):
    """运行实际构造器、LLVM verifier 与原生驱动，失败保留命令输出。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=600, **kwargs)


def main():
    """隔离构建真实 backend/ir，读回模块分别经 O0/O2 优化和运行验证。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    project = WORK / "fixture"
    shutil.rmtree(project, ignore_errors=True)
    shutil.copytree(ROOT / "tests/modules/projects/llvmdatareloc", project)
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
    result = run([str(Path(args.compiler_path).resolve()), "build"], cwd=project)
    (WORK / "build.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = run([str(project / ".build/llvmdatareloc")], cwd=project)
    (WORK / "generator.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, f"generator rc={result.returncode}\n{result.stdout}\n{result.stderr}"
    assert "聚合副本需要兼容的 memmove" in result.stderr, result.stderr
    text = result.stdout
    llfile = WORK / "reloc.ll"
    llfile.write_text(text)
    assert 'ptr getelementptr (i8, ptr @"private_bytes", i64 -4)' in text
    assert 'ptr getelementptr (i8, ptr @"private_target", i64 0)' in text
    assert '@"empty_view" = global [16 x i8] zeroinitializer, align 8' in text
    assert 'llvm.memmove.p0.p0.i64' in text
    assert 'define weak ptr @memmove(' in text
    result = run(["/usr/bin/opt-21", "-passes=verify", "-disable-output", str(llfile)])
    assert result.returncode == 0, result.stderr
    driver = WORK / "driver.c"
    driver.write_text(DRIVER)
    for level in (0, 2):
        obj = WORK / f"reloc-O{level}.o"
        result = run(["/usr/bin/clang-21", "-x", "ir", f"-O{level}", "-c", str(llfile), "-o", str(obj)])
        assert result.returncode == 0, result.stderr
        result = run(["/usr/bin/nm", "-g", "--defined-only", str(obj)])
        assert result.returncode == 0 and "private_bytes" not in result.stdout and "private_target" not in result.stdout
        executable = WORK / f"reloc-O{level}"
        result = run(["/usr/bin/gcc", "-O2", "-fno-builtin", "-no-pie", str(driver), str(obj), "-o", str(executable)])
        assert result.returncode == 0, result.stderr
        result = run([str(executable)])
        assert result.returncode == 0, f"O{level} runtime rc={result.returncode}\n{result.stdout}\n{result.stderr}"
        result = run(["/usr/bin/nm", "-u", str(obj)])
        (WORK / f"undefined-O{level}.log").write_text(result.stdout + result.stderr)
        assert "memmove" not in result.stdout, result.stdout
        disasm = run(["/usr/bin/objdump", "-dr", "--disassemble=memmove", str(obj)])
        (WORK / f"memmove-O{level}.log").write_text(disasm.stdout + disasm.stderr)
        assert "R_X86_64_PLT32\tmemmove" not in disasm.stdout, disasm.stdout
        standalone = WORK / f"reloc-nolibc-O{level}"
        result = run(["/usr/bin/gcc", "-O2", "-fno-builtin", "-fno-stack-protector", "-no-pie",
                      "-nostdlib", "-DYH_NO_LIBC", str(driver), str(obj), "-o", str(standalone)])
        assert result.returncode == 0, f"O{level} 无 libc 链接失败\n{result.stderr}"
        result = run([str(standalone)])
        assert result.returncode == 0, f"O{level} 无 libc 重叠复制失败 rc={result.returncode}"
    print("LL5 数据重定位通过：乱序槽/填充/对齐/正负加数/私有目标与函数/切片/序列化读回/O0+O2/重叠复制")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
