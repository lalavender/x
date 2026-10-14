#!/usr/bin/env python3
"""在 Linux 原生 ARM64 或 x64/qemu 下验收 AArch64 静态 LLVM 桥。"""

import argparse
import json
import os
import platform
import re
import runpy
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/llvm-migration/arm-sdk/embedded"
HOST = "linux-aarch64"
TRIPLE = "aarch64-unknown-linux-gnu"
COMMON = runpy.run_path(str(ROOT / "tests/selfhost/llvm-embedded.py"))
run, IR, BAD_VERIFY = COMMON["run"], COMMON["IR"], COMMON["BAD_VERIFY"]


def needed(path: Path) -> list[str]:
    """读取 ELF 的直接动态依赖；不尝试在 x64 宿主执行 ARM 程序。"""
    result = run(["/usr/bin/readelf", "-d", str(path)])
    assert result.returncode == 0, result.stderr
    return [line.split("[")[1].split("]")[0] for line in result.stdout.splitlines()
            if "(NEEDED)" in line]


def isolated(executable: Path, irfile: Path, config: dict, env: dict, native: bool) -> None:
    """只复制测试宿主、qemu 和普通 OS 动态库，在无 LLVM/工具的 chroot 复验。"""
    assert os.geteuid() == 0, "--chroot 必须在 WSL root 或容器 root 下运行"
    with tempfile.TemporaryDirectory(prefix="isolated-root-", dir=WORK) as directory:
        isolated_root(Path(directory), executable, irfile, config, env, native)


def isolated_root(sandbox: Path, executable: Path, irfile: Path,
                  config: dict, env: dict, native: bool) -> None:
    """在本轮新建的空根中复制明确依赖，旧验收或排查残留不能参与隔离结果。"""
    shutil.copy2(executable, sandbox / "client")
    shutil.copy2(irfile, sandbox / "input.ll")
    locations = [Path(config["prefix"]) / "lib", Path("/usr/aarch64-linux-gnu/lib"),
                 Path("/lib/aarch64-linux-gnu"), Path("/usr/lib/aarch64-linux-gnu")]
    pending, copied = needed(executable) + ["ld-linux-aarch64.so.1"], set()
    while pending:
        name = pending.pop()
        if name in copied:
            continue
        assert "llvm" not in name.lower() and "clang" not in name.lower(), name
        source = next((base / name for base in locations if (base / name).exists()), None)
        assert source, f"找不到 ARM OS 依赖：{name}"
        target = sandbox / "lib" / name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(source, target)
        copied.add(name)
        pending.extend(needed(source))
    runner = ["/client"]
    if not native:
        qemu = Path("/usr/bin/qemu-aarch64")
        shutil.copy2(qemu, sandbox / "qemu-aarch64")
        dependencies = run(["/usr/bin/ldd", str(qemu)])
        assert dependencies.returncode == 0, dependencies.stderr
        for line in dependencies.stdout.splitlines():
            for path in [part for part in line.split() if part.startswith("/")]:
                assert "llvm" not in path.lower() and "clang" not in path.lower(), path
                target = sandbox / path.lstrip("/")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        runner = ["/qemu-aarch64", "/client"]
    chroot = shutil.which("chroot", path="/usr/sbin:/usr/bin:/sbin:/bin")
    assert chroot, "缺少 chroot 隔离工具"
    for opt in (0, 2):
        for kind in (0, 1):
            output = f"/output-O{opt}-kind{kind}"
            result = run([chroot, str(sandbox), *runner, "/input.ll", TRIPLE,
                          str(opt), str(kind), output, "probe"], env=env)
            assert result.returncode == 0, result.stderr
            data = (sandbox / output.lstrip("/")).read_bytes()
            assert (data[:5] == b"\x7fELF\x02" if kind == 0 else b"main" in data), output


def yh_probe(compiler: Path, config: dict, cc: str, native: bool) -> None:
    """额外编译真实 yh 调用者，以自身运行时和 C ABI 驱动 ARM 静态桥生成 x64 对象。"""
    work = WORK.parent
    source = ROOT / "tests/selfhost/llvm-embedded-arm64-probe.yh"
    emitted = run([str(compiler.resolve()), "--target", TRIPLE, "--emit-asm", str(source)])
    assert emitted.returncode == 0, emitted.stderr
    assembly, obj, binary = work / "yh-probe.s", work / "yh-probe-caller.o", work / "yh-probe"
    assembly.write_text(emitted.stdout, encoding="utf-8")
    compiled = run([cc, "-c", str(assembly), "-o", str(obj)])
    assert compiled.returncode == 0, compiled.stderr
    sdk = runpy.run_path(str(ROOT / "tools/llvm-sdk.py"))
    sdk["link"](config, [str(obj)], binary)
    runner = [str(binary)] if native else ["/usr/bin/qemu-aarch64", "-L", "/usr/aarch64-linux-gnu", str(binary)]
    result = run(runner, cwd=ROOT, timeout=180)
    assert result.returncode == 0, result.stderr
    output = work / "yh-probe.o"
    data = output.read_bytes()
    assert data[:5] == b"\x7fELF\x02" and int.from_bytes(data[18:20], "little") == 62
    if not native:
        binary = work / "yh-probe-native"
        linked = run(["/usr/bin/gcc", "-no-pie", str(output), "-o", str(binary)])
        assert linked.returncode == 0, linked.stderr
        result = run([str(binary)])
        assert result.returncode == 0, result.stderr


def main() -> int:
    """检验架构选择、ARM ELF 生命周期、两个发射目标与原子失败语义。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--chroot", action="store_true", help="在无系统 LLVM 的隔离根复验")
    parser.add_argument("--compiler-path", type=Path, help="额外验证指定 yh 的 ARM64 源级桥调用")
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    native = platform.machine() in ("aarch64", "arm64")
    cc = "/usr/bin/gcc" if native else "/usr/bin/aarch64-linux-gnu-gcc"
    client, obj, executable = WORK / "client.c", WORK / "client.o", WORK / "client"
    client.write_text(COMMON["CLIENT"], encoding="utf-8")
    compiled = run([cc, "-O2", "-I" + str(ROOT / "compiler/llvm"), "-c", str(client), "-o", str(obj)])
    assert compiled.returncode == 0, compiled.stderr
    linked = run(["/usr/bin/python3", str(ROOT / "tools/llvm-sdk.py"), "link", "--host", HOST,
                  "--object", str(obj), "--output", str(executable)], timeout=300)
    assert linked.returncode == 0, linked.stdout + linked.stderr
    config = json.loads(linked.stdout)
    assert config["host"] == HOST and config["llvm_version"] == "21.1.8"
    assert config["sdk_sha256"] == "8210ff444cdf2d17881946f1e102ff598c2dec53eb267a346c5ddb216cd94d5b"
    assert config["bridge_abi"] == 1
    corrupt = WORK / "bad-cache.deb"
    corrupt.write_bytes(b"untrusted cached SDK")
    sdk = runpy.run_path(str(ROOT / "tools/llvm-sdk.py"))
    try:
        sdk["download"]({"package": str(corrupt.relative_to(ROOT / "tmp/llvm-migration")),
                         "sha256": "8210ff444cdf2d17881946f1e102ff598c2dec53eb267a346c5ddb216cd94d5b"})
    except RuntimeError as error:
        assert "SHA-256" in str(error), error
    else:
        raise AssertionError("固定 SDK 接受了损坏的缓存包")
    finally:
        corrupt.unlink()
    data = executable.read_bytes()
    assert data[:5] == b"\x7fELF\x02" and int.from_bytes(data[18:20], "little") == 183
    dependencies = needed(executable)
    assert all("llvm" not in name.lower() and "clang" not in name.lower() for name in dependencies)
    assert "libstdc++.so.6" not in dependencies and "libgcc_s.so.1" not in dependencies
    versions = run(["/usr/bin/readelf", "--version-info", str(executable)])
    assert versions.returncode == 0, versions.stderr
    glibc = sorted({tuple(map(int, item.split(".")))
                    for item in re.findall(r"Name: GLIBC_([0-9.]+)", versions.stdout)})
    assert glibc and glibc[-1] <= (2, 38), f"ARM SDK 超出已声明 glibc 2.38 下限：{glibc}"
    if not native:
        wrong_object, preserved_link = WORK / "wrong-host.o", WORK / "preserved-link"
        compiled = run(["/usr/bin/gcc", "-O2", "-I" + str(ROOT / "compiler/llvm"),
                        "-c", str(client), "-o", str(wrong_object)])
        assert compiled.returncode == 0, compiled.stderr
        preserved_link.write_bytes(b"previous valid artifact")
        rejected = run(["/usr/bin/python3", str(ROOT / "tools/llvm-sdk.py"), "link", "--host", HOST,
                        "--object", str(wrong_object), "--output", str(preserved_link)], timeout=300)
        assert rejected.returncode == 1 and rejected.stderr
        assert preserved_link.read_bytes() == b"previous valid artifact", "架构错配破坏了已有宿主"
    env = dict(os.environ, PATH=str(WORK / "no-tools"))
    (WORK / "no-tools").mkdir(exist_ok=True)
    env["LD_LIBRARY_PATH"] = str(Path(config["prefix"]) / "lib")
    runner = [str(executable)] if native else ["/usr/bin/qemu-aarch64", "-L", "/usr/aarch64-linux-gnu", str(executable)]
    irfile = WORK / "valid.ll"
    irfile.write_text(IR, encoding="utf-8")
    for opt in (0, 2):
        for target, machine in ((TRIPLE, 183), ("x86_64-unknown-linux-gnu", 62)):
            output = WORK / f"probe-{machine}-O{opt}.o"
            result = run([*runner, str(irfile), target, str(opt), "0", str(output), "probe"], env=env)
            assert result.returncode == 0, result.stderr
            data = output.read_bytes()
            assert data[:5] == b"\x7fELF\x02" and int.from_bytes(data[18:20], "little") == machine
            if machine == 183:
                binary = WORK / f"probe-O{opt}"
                result = run([cc, "-no-pie", str(output), "-o", str(binary)])
                assert result.returncode == 0, result.stderr
                invoke = [str(binary)] if native else ["/usr/bin/qemu-aarch64", "-L", "/usr/aarch64-linux-gnu", str(binary)]
                result = run(invoke, env=env)
                assert result.returncode == 0, result.stderr
            assembly = WORK / f"probe-{machine}-O{opt}.s"
            result = run([*runner, str(irfile), target, str(opt), "1", str(assembly), "probe"], env=env)
            assert result.returncode == 0 and "main" in assembly.read_text(), result.stderr
    failures = [("bad-ir", "not LLVM", TRIPLE, 0, 0, WORK / "bad-ir.o"),
                ("bad-verify", BAD_VERIFY, TRIPLE, 0, 0, WORK / "bad-verify.o"),
                ("bad-target", IR, "unknown-yh-target", 0, 0, WORK / "bad-target.o"),
                ("bad-opt", IR, TRIPLE, 1, 0, WORK / "bad-opt.o"),
                ("bad-kind", IR, TRIPLE, 0, 2, WORK / "bad-kind.o"),
                ("bad-layout", 'target datalayout = "e-p:32:32"\n' + IR, TRIPLE, 0, 0, WORK / "bad-layout.o"),
                ("bad-module-target", 'target triple = "x86_64-unknown-linux-gnu"\n' + IR,
                 TRIPLE, 0, 0, WORK / "bad-module-target.o"),
                ("bad-path", IR, TRIPLE, 0, 0, WORK / "missing/output.o")]
    for name, text, target, opt, kind, output in failures:
        source = WORK / f"{name}.ll"
        source.write_text(text, encoding="utf-8")
        output.unlink(missing_ok=True)
        result = run([*runner, str(source), target, str(opt), str(kind), str(output), "probe"], env=env)
        assert result.returncode == 1 and result.stderr, f"{name}: {result}"
        assert not output.exists(), f"{name} 发布了失败产物"
    preserved = WORK / "preserved.o"
    preserved.write_bytes(b"previous valid artifact")
    result = run([*runner, str(WORK / "bad-verify.ll"), TRIPLE, "0", "0", str(preserved), "probe"], env=env)
    assert result.returncode == 1 and preserved.read_bytes() == b"previous valid artifact"
    directory = WORK / "directory-output"
    directory.mkdir(exist_ok=True)
    result = run([*runner, str(irfile), TRIPLE, "0", "0", str(directory), "probe"], env=env)
    assert result.returncode == 1 and directory.is_dir()
    assert not list(WORK.glob("*.yh-llvm-*")), "原子写入失败遗留临时文件"
    if args.chroot:
        isolated(executable, irfile, config, env, native)
    if args.compiler_path:
        yh_probe(args.compiler_path, config, cc, native)
    report = {"llvm": "21.1.8", "host": HOST, "config": config, "needed": dependencies,
              "o0_o2": True, "machines": [183, 62], "negative_cases": len(failures),
              "glibc_minimum": ".".join(map(str, glibc[-1])), "wrong_host_rejected": not native,
              "corrupt_cache_rejected": True,
              "yh_source_probe": args.compiler_path is not None,
              "chroot": args.chroot, "scope": "独立 ARM64 静态桥测试；前端/自举由主门验收"}
    (WORK / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ARM64 内嵌 LLVM 桥门通过：O0/O2、ARM64/x64、{len(failures)} 个拒绝案例，chroot={args.chroot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
