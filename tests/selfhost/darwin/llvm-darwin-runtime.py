#!/usr/bin/env python3
"""Darwin/ARM64 LLVM runtime 门：allocator、va_list、字节 helper 与 libSystem imports。"""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "tmp/llvm-migration/darwin-runtime"
SOURCE = ROOT / "tests/selfhost/darwin/llvm-darwin-runtime.yh"
PROCESS_SOURCE = ROOT / "tests/selfhost/darwin/llvm-darwin-process.yh"
OPEN_INVALID_SOURCE = ROOT / "tests/selfhost/darwin/llvm-darwin-open-invalid.yh"
SDK_PACKAGE = ROOT / "tmp/llvm-migration/darwin-sdk/sdk-darwin-aarch64"
TRIPLE = "aarch64-apple-darwin"
EXPECTED = ("darwin-runtime:-7 8 -9 10 hi A %\n"
            "many:12345678\n" + "x" * 299 + "\n")
RUNTIMEBYTES_EXPECTED = ("fmt:-7 8 -9 10 str A %\n"
                        "args:12345678\n" + "x" * 299)
LIBSBASE_EXPECTED = "yh libs base ok\n"


def require(condition, message):
    """报告确定性的门禁失败，不使用可被 Python -O 移除的 assert。"""
    if not condition:
        raise RuntimeError(message)


def run(label, command, environment, cwd=ROOT):
    """执行 runtime 编译/运行步骤，并把原始输出保存在 tmp 供定位。"""
    result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True,
                            text=True, timeout=120)
    (WORK / f"{label}.stdout").write_text(result.stdout, encoding="utf-8")
    (WORK / f"{label}.stderr").write_text(result.stderr, encoding="utf-8")
    return result


def main():
    """在 O0/O2 构建并运行 Darwin runtime，核对字节输出和导入面。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--min-os", default="14.0.0")
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    record_path = SDK_PACKAGE / "host.json"
    require(record_path.is_file(), "缺少固定 Darwin LLVM host.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    sdk_root = Path(os.environ.get("SDKROOT") or record.get("sdk_root", "")).resolve()
    require((sdk_root / "SDKSettings.json").is_file(), f"无效 Darwin SDKROOT：{sdk_root}")
    environment = os.environ.copy()
    environment["SDKROOT"] = str(sdk_root)
    environment["MACOSX_DEPLOYMENT_TARGET"] = args.min_os
    compiler = str(Path(args.compiler_path).resolve())
    for opt in ("-O0", "-O2"):
        executable = WORK / f"runtime-{opt[2:]}"
        executable.unlink(missing_ok=True)
        built = run(f"build-{opt[2:]}", [compiler, "--backend", "llvm", "--target",
            TRIPLE, opt, "-o", str(executable), str(SOURCE)], environment)
        require(built.returncode == 0 and executable.is_file(),
                f"{opt} Darwin runtime 构建失败：{built.stderr[-3000:]}")
        executed = run(f"run-{opt[2:]}", [str(executable)], environment)
        require(executed.returncode == 0 and executed.stdout == EXPECTED,
                f"{opt} Darwin runtime 输出/退出码错误：{executed.returncode} {executed.stdout!r}")
        imports = run(f"imports-{opt[2:]}", ["nm", "-u", str(executable)], environment)
        require(imports.returncode == 0, f"{opt} 无法检查 Darwin runtime 导入：{imports.stderr}")
        require(re.search(r"(?m)^_?(?:malloc|free|printf|strlen|memcpy|memmove|memset)$",
                          imports.stdout) is None,
                f"{opt} Darwin runtime 导入了 libc allocator/format/string helper")
        for name in ("mmap", "munmap", "write"):
            require(re.search(rf"(?m)^_?{name}$", imports.stdout) is not None,
                    f"{opt} Darwin runtime 没有经 libSystem 使用 {name}")

    # 用标准 runtimebytes 项目覆盖 UTF-8 字节长度、函数值、零长度复制与格式化。
    project = WORK / "runtimebytes-project"
    shutil.rmtree(project, ignore_errors=True)
    shutil.copytree(ROOT / "tests/modules/projects/runtimebytes", project)
    for opt in ("-O0", "-O2"):
        executable = WORK / f"runtimebytes-{opt[2:]}"
        executable.unlink(missing_ok=True)
        built = run(f"project-build-{opt[2:]}", [compiler, "--backend", "llvm",
            "--target", TRIPLE, opt, "build", "-o", str(executable)],
            environment, cwd=project)
        require(built.returncode == 0 and executable.is_file(),
                f"{opt} runtimebytes Darwin 项目构建失败：{built.stderr[-3000:]}")
        executed = run(f"project-run-{opt[2:]}", [str(executable)], environment)
        require(executed.returncode == 0 and executed.stdout == RUNTIMEBYTES_EXPECTED,
                f"{opt} runtimebytes Darwin 项目输出/退出码错误："
                f"{executed.returncode} {executed.stdout!r}")
        imports = run(f"project-imports-{opt[2:]}", ["nm", "-u", str(executable)],
                      environment)
        require(imports.returncode == 0,
                f"{opt} 无法检查 runtimebytes Darwin 导入：{imports.stderr}")
        names = {line.split()[-1].lstrip("_") for line in imports.stdout.splitlines()
                 if line.split()}
        forbidden = sorted(names.intersection(
            {"malloc", "free", "printf", "strlen", "memcpy", "memmove", "memset"}))
        require(not forbidden and {"mmap", "munmap", "write"}.issubset(names),
                f"{opt} runtimebytes Darwin 导入边界错误："
                f"forbidden={forbidden}, imports={sorted(names)}")

    # libsbase 经 yh 标准库覆盖 time、内存与 Darwin 文件/目录 OS API。
    libsbase = WORK / "libsbase-project"
    shutil.rmtree(libsbase, ignore_errors=True)
    shutil.copytree(ROOT / "tests/modules/projects/libsbase", libsbase)
    library_environment = dict(environment)
    library_environment["YH_STDLIB"] = str(ROOT / "libs")
    for opt in ("-O0", "-O2"):
        executable = WORK / f"libsbase-{opt[2:]}"
        executable.unlink(missing_ok=True)
        built = run(f"libsbase-build-{opt[2:]}", [compiler, "--backend", "llvm",
            "--target", TRIPLE, opt, "build", "-o", str(executable)],
            library_environment, cwd=libsbase)
        require(built.returncode == 0 and executable.is_file(),
                f"{opt} yh libs/time Darwin 消费者构建失败：{built.stderr[-3000:]}")
        executed = run(f"libsbase-run-{opt[2:]}", [str(executable)], library_environment)
        require(executed.returncode == 0 and executed.stdout == LIBSBASE_EXPECTED,
                f"{opt} yh libs/time Darwin 消费者输出/退出码错误："
                f"{executed.returncode} {executed.stdout!r} {executed.stderr[-500:]}")

    # fork/execvp/waitpid 的调用结果也须在两档优化下保持 Darwin C ABI。
    for opt in ("-O0", "-O2"):
        executable = WORK / f"process-{opt[2:]}"
        executable.unlink(missing_ok=True)
        built = run(f"process-build-{opt[2:]}", [compiler, "--backend", "llvm",
            "--target", TRIPLE, opt, "-o", str(executable), str(PROCESS_SOURCE)],
            environment)
        require(built.returncode == 0 and executable.is_file(),
                f"{opt} Darwin 进程 API 构建失败：{built.stderr[-3000:]}")
        executed = run(f"process-run-{opt[2:]}", [str(executable)], environment)
        require(executed.returncode == 0,
                f"{opt} Darwin fork/execvp/waitpid 互操作失败："
                f"{executed.returncode} {executed.stderr[-1000:]}")
    invalid_open = run("open-invalid", [compiler, "--backend", "llvm",
        "--target", TRIPLE, "-o", str(WORK / "open-invalid"), str(OPEN_INVALID_SOURCE)],
        environment)
    require(invalid_open.returncode != 0 and not (WORK / "open-invalid").exists(),
            "Darwin 可变参数 open 接受了非整型 mode")
    print("PASS Darwin/ARM64 LLVM runtime：O0/O2 allocator、printf va_list、helper 与导入面")


if __name__ == "__main__":
    main()
