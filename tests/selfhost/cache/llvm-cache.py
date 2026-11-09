#!/usr/bin/env python3
"""LL9 项目缓存门：目标隔离、工具身份、对象校验与失败发布。"""

import argparse
import hashlib
import os
import platform
import shutil
import struct
import subprocess
from pathlib import Path

# --stats 已从 CLI 移除（2026-11-10）：统计输出改由 YH_STATS=1 开启。
os.environ.setdefault("YH_STATS", "1")

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests/modules/projects/llvmcache"
TARGET = "x86_64-unknown-linux-gnu"
EXPECTED_MACHINE = 62


def run(command, cwd, env):
    """运行一个测试子进程并保留原始输出。"""
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=300)


def machine(path):
    """读取 ELF e_machine，返回目标机型编号。"""
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"\x7fELF":
        return -1
    return struct.unpack_from("<H", data, 18)[0]


def build(compiler, project, output, env, target=None, level=0):
    """用显式后端参数构建测试项目到指定输出路径。"""
    target = target or TARGET
    return run([str(compiler), "--backend", "llvm", "--target", target,
                f"-O{level}", "build", "-o", str(output)],
               cwd=project, env=env)


def build_archive(compiler, source, archive, env):
    """编译测试用静态库，保持库名和搜索目录不变以检测内容失效。"""
    object_path = source.with_suffix(".o")
    compiled = run([compiler, "-c", str(source), "-o", str(object_path)],
                   cwd=source.parent, env=env)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    archived = run(["ar", "rcs", str(archive), str(object_path)],
                   cwd=source.parent, env=env)
    assert archived.returncode == 0, archived.stdout + archived.stderr


def write_link_wrapper(wrapper, linker, marker):
    """记录每次 cc 调用，确认内嵌 lld 路径不 fork 驱动或链接器。"""
    wrapper.write_text(
        "#!/bin/sh\n"
        f'printf "{marker}\\n" >> "$YH_LLVM_CACHE_LOG"\n'
        f'exec "{linker}" "$@"\n', encoding="utf-8")


def main():
    """验证 LLVM 项目缓存与同名输出切换的完整发布边界。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--target", default=None,
                        help="输出目标；缺省按宿主 Linux 架构选择 x64 或 AArch64")
    args = parser.parse_args()
    global TARGET, EXPECTED_MACHINE
    if args.target:
        TARGET = args.target
    else:
        host = platform.machine().lower()
        TARGET = "aarch64-unknown-linux-gnu" if host in ("aarch64", "arm64") \
            else "x86_64-unknown-linux-gnu"
    EXPECTED_MACHINE = 183 if TARGET.startswith("aarch64-") else 62
    compiler = Path(args.compiler_path).resolve()
    if not compiler.is_file():
        raise SystemExit(f"编译器不存在: {compiler}")
    gcc = "/usr/bin/gcc" if Path("/usr/bin/gcc").is_file() else shutil.which("gcc")
    if not Path(gcc).is_file():
        raise SystemExit("缺少可运行的宿主 gcc")

    temp_root = ROOT / "tmp"
    temp_root.mkdir(exist_ok=True)
    work = temp_root / "llvm-cache-空间 test"
    shutil.rmtree(work, ignore_errors=True)
    project = work / "项目 with spaces"
    shutil.copytree(FIXTURE, project)
    tools = work / "tools"
    tools.mkdir(parents=True)
    wrapper = tools / "gcc-fixed-path"
    log = work / "link.log"
    write_link_wrapper(wrapper, gcc, "v1")
    wrapper.chmod(0o755)
    env = dict(os.environ)
    env.setdefault("YH_CACHE", "off")
    env["YH_CC"] = str(wrapper)
    env["YH_LLVM_CACHE_LOG"] = str(log)
    output = work / "程序 输出"

    cold = build(compiler, project, output, env)
    assert cold.returncode == 0, cold.stdout + cold.stderr
    assert machine(output) == EXPECTED_MACHINE, f"冷构建产物 machine={machine(output)}"
    assert subprocess.run([str(output)]).returncode == 42
    assert not log.exists(), "LLVM 最终链接不应 fork cc/ld"

    cache = project / ".build/targets" / TARGET / "llvm/O0"
    obj = next((cache / "obj").glob("*.o"))
    manifest = cache / "manifest/llvmcache-main.manifest"
    hot = build(compiler, project, output, env)
    assert hot.returncode == 0, hot.stdout + hot.stderr
    assert "[缓存] main" in hot.stdout, hot.stdout
    assert not log.exists(), "LLVM 热链接不应 fork cc/ld"

    write_link_wrapper(wrapper, gcc, "v2")
    tool_changed = build(compiler, project, output, env)
    assert tool_changed.returncode == 0, tool_changed.stdout + tool_changed.stderr
    assert "[缓存] main" in tool_changed.stdout, tool_changed.stdout
    assert not log.exists(), "LLVM 缓存身份不应查询或执行 YH_CC"

    obj.write_bytes(b"corrupt object\n")
    repaired = build(compiler, project, output, env)
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr
    assert "[编译] main" in repaired.stdout, repaired.stdout
    assert machine(obj) == EXPECTED_MACHINE, "损坏对象未被重建为目标架构 ELF"
    assert subprocess.run([str(output)]).returncode == 42
    damaged_manifest = bytearray(manifest.read_bytes())
    damaged_manifest[-1] = ord("0") if damaged_manifest[-1] != ord("0") else ord("1")
    manifest.write_bytes(damaged_manifest)
    repaired_manifest = build(compiler, project, output, env)
    assert repaired_manifest.returncode == 0, \
        repaired_manifest.stdout + repaired_manifest.stderr
    assert "[编译] main" in repaired_manifest.stdout, repaired_manifest.stdout
    iface = project / ".build/targets" / TARGET / "llvm/O0/iface/llvmcache-main.s.i"
    iface.write_bytes(iface.read_bytes() + b"damaged interface\n")
    repaired_iface = build(compiler, project, output, env)
    assert repaired_iface.returncode == 0, repaired_iface.stdout + repaired_iface.stderr
    assert "[编译] main" in repaired_iface.stdout, repaired_iface.stdout

    before = output.read_bytes()
    wrong_name = "x86_64-unknown-linux-gnu" if EXPECTED_MACHINE == 183 \
        else "aarch64-unknown-linux-gnu"
    wrong_expected = 62 if EXPECTED_MACHINE == 183 else 183
    wrong_target = build(compiler, project, output, env, target=wrong_name)
    assert wrong_target.returncode != 0, "目标链接器接受了另一架构的对象"
    wrong_obj = project / ".build/targets" / wrong_name / "llvm/O0/obj/llvmcache-main.o"
    assert wrong_obj.is_file() and machine(wrong_obj) == wrong_expected, \
        "目标切换复用了错误机型的对象"
    assert output.read_bytes() == before, "目标链接失败覆盖了旧可执行文件"
    assert subprocess.run([str(output)]).returncode == 42
    wrong_manifest = wrong_obj.parent.parent / "manifest/llvmcache-main.manifest"
    wrong_object = obj.read_bytes()
    wrong_obj.write_bytes(wrong_object)
    paired = bytearray(wrong_manifest.read_bytes())
    # C4 manifest：ActionID 32 + obj 32 + .s.i 32 + .s.ct 32。
    paired[32:64] = hashlib.sha256(wrong_object).digest()
    wrong_manifest.write_bytes(paired)
    wrong_machine = build(compiler, project, output, env, target=wrong_name)
    assert wrong_machine.returncode != 0 and "[编译] main" in wrong_machine.stdout, \
        wrong_machine.stdout + wrong_machine.stderr
    assert machine(wrong_obj) == wrong_expected, "错误 machine 与配对 manifest 被缓存命中"
    assert output.read_bytes() == before, "错误 machine 对象覆盖了旧可执行文件"

    # 同名输出切换到另一架构并成功链接只覆盖 x64→AArch64 的交叉驱动场景；
    # AArch64 原生宿主没有对应的 x64 交叉 gcc，跳过成功切换，仅保留上面的
    # 错误目标拒绝/缓存隔离断言。
    if EXPECTED_MACHINE == 62:
        arm_gcc = shutil.which("aarch64-linux-gnu-gcc")
        if arm_gcc is None:
            bundled_arm_gcc = ROOT / "tmp/boot/crossbin/aarch64-linux-gnu-gcc"
            if bundled_arm_gcc.is_file():
                arm_gcc = str(bundled_arm_gcc)
        if arm_gcc is not None:
            write_link_wrapper(wrapper, arm_gcc, "arm64")
            switched = build(compiler, project, output, env,
                             target="aarch64-unknown-linux-gnu")
            assert switched.returncode == 0, switched.stdout + switched.stderr
            assert machine(output) == 183, "同名输出切换到 AArch64 后 machine 不正确"

            write_link_wrapper(wrapper, gcc, "x64")
            restored = build(compiler, project, output, env)
            assert restored.returncode == 0, restored.stdout + restored.stderr
            assert machine(output) == EXPECTED_MACHINE and subprocess.run([str(output)]).returncode == 42, \
                "同名输出从 AArch64 切回 x86_64 后没有恢复正确程序"

    optimized = build(compiler, project, output, env, level=2)
    assert optimized.returncode == 0, optimized.stdout + optimized.stderr
    assert (project / ".build/targets" / TARGET / "llvm/O2/obj").is_dir(), \
        "O2 未使用独立缓存命名空间"
    assert machine(output) == EXPECTED_MACHINE and subprocess.run([str(output)]).returncode == 42

    # 同名静态库内容变更必须使最终链接缓存失效。
    library_project = work / "静态库项目"
    shutil.copytree(ROOT / "tests/selfhost/fixtures/llvmcachelib", library_project)
    library_dir = work / "link-libraries"
    library_dir.mkdir()
    archive = library_dir / "libcacheprobe.a"
    library_source = work / "cacheprobe.c"
    library_env = dict(env)
    library_env["LIBRARY_PATH"] = str(library_dir)
    library_log = work / "library-link.log"
    library_env["YH_LLVM_CACHE_LOG"] = str(library_log)
    write_link_wrapper(wrapper, gcc, "library-link")
    library_output = work / "静态库结果"
    library_source.write_text(
        "int cache_probe(void) { return 42; }\n", encoding="utf-8")
    build_archive(gcc, library_source, archive, library_env)
    library_cold = build(compiler, library_project, library_output, library_env)
    assert library_cold.returncode == 0, library_cold.stdout + library_cold.stderr
    assert subprocess.run([str(library_output)]).returncode == 42
    assert not library_log.exists(), "LLVM 库链接不应 fork cc/ld"

    library_source.write_text(
        "int cache_probe(void) { return 43; }\n", encoding="utf-8")
    build_archive(gcc, library_source, archive, library_env)
    library_changed = build(compiler, library_project, library_output, library_env)
    assert library_changed.returncode == 0, \
        library_changed.stdout + library_changed.stderr
    assert not library_log.exists(), "LLVM 库链接不应 fork cc/ld"
    assert subprocess.run([str(library_output)]).returncode == 43, \
        "静态库内容变化后复用了旧可执行文件"

    before_failed_link = library_output.read_bytes()
    archive.unlink()
    failed_library_link = build(compiler, library_project, library_output, library_env)
    assert failed_library_link.returncode != 0, \
        "内嵌 lld 应拒绝缺失的项目静态库"
    assert library_output.read_bytes() == before_failed_link, \
        "内嵌 lld 链接失败覆盖了旧可执行文件"
    assert subprocess.run([str(library_output)]).returncode == 43, \
        "内嵌 lld 链接失败后旧可执行文件不可运行"
    assert not library_log.exists(), "内嵌 lld 链接失败不应 fork cc/ld"

    print("LLVM 项目缓存通过：热命中、工具版本变化、损坏对象修复、目标隔离、失败保留旧产物与路径空格/中文")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
