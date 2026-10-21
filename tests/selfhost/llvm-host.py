#!/usr/bin/env python3
"""tests/selfhost/llvm-host.py —— 构建并验收自包含静态 LLVM 宿主（LL3 起的通用能力）。

产物（<host> 取 linux-x86_64 或 linux-aarch64，默认按本机架构）：

    tmp/llvm-migration/llvm-host-<host>/yh-llvm-host   宿主可执行文件
    tmp/llvm-migration/llvm-host-<host>/host.json      可复现身份记录

“宿主”指最终运行 LLVM 桥的架构，与桥参数里的发射目标无关：x86_64 宿主在
本机原生运行，AArch64 宿主在 x86_64/WSL 上经 qemu-user 运行。

复用边界：
    * 解包、校验、桥归档编译与静态链接全部复用 tools/llvm-sdk.py 的
      prepare/build/link，本脚本不重复实现下载或 SHA-256 校验逻辑；
    * 本脚本只提供最小 C 驱动、验收断言与身份记录；
    * 不安装系统 LLVM，不调用 llvm-config，不动态链接 libLLVM/libclang。

验收项：readelf -d 依赖面不含 libLLVM/libclang、readelf -h 机器码正确、
nm 中 yh_llvm_* 为定义符号（不是 U）、真实运行 --version、两个目标 triple
的 O0/O2 对象与汇编发射冒烟。

用法：python3 tests/selfhost/llvm-host.py [--host linux-x86_64|linux-aarch64]
退出码：全部通过 0，失败非 0（保留原始错误）。
"""

import argparse
import hashlib
import json
import platform
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from llvm_cache import cache_root  # noqa: E402
WORK_ROOT = cache_root()

# 受支持的宿主：宿主标识 → ELF e_machine 编号、qemu-user 运行器与目标 sysroot。
# machine 用宿主 readelf -h 打印的名字反查，保证「生成它的人」与「验收它的人」
# 用同一份判定依据；qemu 为 None 表示同架构可直接原生运行。
HOSTS = {
    "linux-x86_64": {"machine": 62, "expected_name": "Advanced Micro Devices X86-64",
                     "qemu": None, "sysroot": None},
    "linux-aarch64": {"machine": 183, "expected_name": "AArch64",
                      "qemu": "/usr/bin/qemu-aarch64", "sysroot": "/usr/aarch64-linux-gnu"},
}

# 桥暴露给 C 调用方的入口；宿主必须**定义**它们（nm 里不能是 U）。
BRIDGE_SYMBOLS = (
    "yh_llvm_emit", "yh_llvm_version", "yh_lld_link", "yh_lld_link_driver",
    "yh_lld_link_identity", "yh_lld_default_file_count", "yh_lld_default_file",
    "yh_lld_default_library_count", "yh_lld_default_library",
    "yh_lld_resolve_library",
)

# IR：最小可验证模块，两个目标都能发射成可直接链接的 ELF 对象。
PROBE_IR = "define i32 @main() { entry: ret i32 0 }\n"

# HOST_CLIENT：自包含静态 LLVM 宿主的最小 C 驱动，只使用 bridge.h 的 C ABI。
# 存在的意义是「有一个真的能跑、能发射对象的宿主可执行文件」，
# 而不是让门禁只检查文件类型。
HOST_CLIENT = r'''
/* yh-llvm-host：静态 LLVM 宿主的最小 CLI，用于证明内嵌桥自包含可用。
 *
 * 用法：
 *   yh-llvm-host --version
 *       打印桥编译进来的 LLVM 版本，正常退出码 0。
 *   yh-llvm-host --emit <ir> <triple> <opt> <kind> <out>
 *       读入 LLVM 文本 IR，发射对象（kind=0）或汇编（kind=1）。
 *       成功退出 0，桥返回失败打印有界诊断并退出 1，用法错误退出 2。
 *
 * 退出码 90+ 表示宿主自身的输入/内存错误，与桥的语义失败区分开。
 */
#include "bridge.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* emit_file：读入 IR 文本后交给桥；桥失败时不发布输出文件。 */
static int emit_file(const char *ir_path, const char *triple, int opt,
                     int kind, const char *out_path) {
    FILE *f = fopen(ir_path, "rb");
    if (f == NULL) {
        fprintf(stderr, "无法读取 IR: %s\n", ir_path);
        return 90;
    }
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return 91; }
    long length = ftell(f);
    if (length < 0 || fseek(f, 0, SEEK_SET) != 0) { fclose(f); return 92; }
    char *text = malloc((size_t)length + 1);
    if (text == NULL || fread(text, 1, (size_t)length, f) != (size_t)length) {
        fclose(f);
        return 93;
    }
    fclose(f);
    text[length] = 0;
    char diagnostic[4096];
    diagnostic[0] = 0;
    int rc = yh_llvm_emit(text, (uint64_t)length, triple, opt, kind, out_path,
                          diagnostic, sizeof(diagnostic));
    free(text);
    if (rc != 0) {
        fprintf(stderr, "%s\n", diagnostic[0] ? diagnostic : "桥失败但未给出诊断");
        return 1;
    }
    return 0;
}

/* main：只接受 --version 与 --emit 两种形态，其余一律按用法错误处理。 */
int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        printf("yh-llvm-host llvm %s\n", yh_llvm_version());
        return 0;
    }
    if (argc == 7 && strcmp(argv[1], "--emit") == 0) {
        return emit_file(argv[2], argv[3], atoi(argv[4]), atoi(argv[5]), argv[6]);
    }
    fprintf(stderr, "用法: yh-llvm-host --version | --emit <ir> <triple> <opt> <kind> <out>\n");
    return 2;
}
'''


def local_host() -> str:
    """本机架构对应的宿主标识；固定 SDK 只支持这两种 Linux 宿主。"""
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(platform.machine(),
                                                          platform.machine())
    host = "linux-" + machine
    if host not in HOSTS:
        raise RuntimeError(f"本机不是受支持的 LLVM 宿主：{host}")
    return host


def run(command: list[str], timeout: int = 600, **kwargs) -> subprocess.CompletedProcess:
    """执行固定工具或宿主；输出全部保留，失败时由调用方原样报告。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, **kwargs)


def digest(path: Path) -> str:
    """分块计算产物身份；宿主可达几十 MB，不整块读入内存。"""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def relative(path: Path) -> str:
    """身份记录优先写仓库相对路径，便于在别的 WSL/容器里对照同一份产物。

    共享闭包缓存按绝对路径挂进容器时（workspace 里的 tmp/llvm-migration 是指向
    缓存的符号链接），产物解析后会落在仓库根之外；此时保留绝对路径，避免
    relative_to 抛错。消费方用 (ROOT / value) 拼接，绝对路径同样可用。
    """
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def readelf_machine(executable: Path) -> tuple[int, str]:
    """用宿主 readelf -h 的 Machine 行判定 ELF 机器码，返回（编号，名字）。"""
    result = run(["/usr/bin/readelf", "-h", str(executable)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    name = ""
    for line in result.stdout.splitlines():
        if line.strip().startswith("Machine:"):
            name = line.split(":", 1)[1].strip()
            break
    for host, info in HOSTS.items():
        if info["expected_name"] == name:
            return info["machine"], name
    raise RuntimeError(f"未知的 ELF 机器名：{name!r}")


def readelf_needed(executable: Path) -> list[str]:
    """读取 ELF 的直接动态依赖；这是「没有动态链接 libLLVM」的唯一判据。"""
    result = run(["/usr/bin/readelf", "-d", str(executable)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return [line.split("[", 1)[1].split("]", 1)[0] for line in result.stdout.splitlines()
            if "(NEEDED)" in line]


def symbol_type(executable: Path, name: str) -> str:
    """返回 nm 里该符号的类型字符；未定义（U）或不存在返回空串表示未通过。"""
    result = run(["/usr/bin/nm", str(executable)], timeout=900)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[-1] == name and fields[-2] != "U":
            return fields[-2]
    return ""


def runner_for(host: str, executable: Path) -> list[str]:
    """给出宿主可执行文件的运行前缀：同架构原生运行，AArch64 走 qemu-user。"""
    if host == local_host():
        return [str(executable)]
    info = HOSTS[host]
    if not info["qemu"] or not Path(info["qemu"]).is_file():
        raise RuntimeError(f"缺少 qemu-user 运行器：{info['qemu']}")
    return [info["qemu"], "-L", info["sysroot"], str(executable)]


def emit_probes(work: Path, runner: list[str]) -> list[dict]:
    """两个目标 triple 的 O0/O2 对象与一次汇编发射；返回每步的实测机器码。"""
    irfile = work / "probe.ll"
    irfile.write_text(PROBE_IR, encoding="utf-8")
    observed = []
    for triple, machine in (("x86_64-unknown-linux-gnu", 62),
                            ("aarch64-unknown-linux-gnu", 183)):
        for opt in (0, 2):
            output = work / f"probe-{machine}-O{opt}.o"
            output.unlink(missing_ok=True)
            result = run([*runner, "--emit", str(irfile), triple, str(opt), "0", str(output)])
            if result.returncode != 0:
                raise RuntimeError(result.stderr)
            data = output.read_bytes()
            if data[:5] != b"\x7fELF\x02" or int.from_bytes(data[18:20], "little") != machine:
                raise RuntimeError(f"发射对象架构不符：{output.name}")
            observed.append({"triple": triple, "opt": opt, "kind": 0, "machine": machine})
    assembly = work / "probe.s"
    result = run([*runner, "--emit", str(irfile), "x86_64-unknown-linux-gnu", "2", "1",
                  str(assembly)])
    if result.returncode != 0 or "main" not in assembly.read_text(encoding="utf-8"):
        raise RuntimeError(f"汇编发射失败：{result.stderr}")
    observed.append({"triple": "x86_64-unknown-linux-gnu", "opt": 2, "kind": 1, "machine": 62})
    return observed


def negative_probes(work: Path, runner: list[str]) -> int:
    """失败路径必须非 0 且不发布产物，宿主才不会把坏 IR 当成成功。"""
    bad = work / "probe-bad.ll"
    bad.write_text("not LLVM IR\n", encoding="utf-8")
    cases = [("bad-ir", bad, "x86_64-unknown-linux-gnu", 0, 0),
             ("bad-target", work / "probe.ll", "unknown-yh-target", 0, 0),
             ("bad-opt", work / "probe.ll", "x86_64-unknown-linux-gnu", 1, 0),
             ("bad-kind", work / "probe.ll", "x86_64-unknown-linux-gnu", 0, 2)]
    for name, source, triple, opt, kind in cases:
        output = work / f"{name}.o"
        output.unlink(missing_ok=True)
        result = run([*runner, "--emit", str(source), triple, str(opt), str(kind),
                      str(output)])
        if result.returncode != 1 or not result.stderr:
            raise RuntimeError(f"{name} 未被拒绝：rc={result.returncode}")
        if output.exists():
            raise RuntimeError(f"{name} 发布了失败产物")
    return len(cases)


def main() -> int:
    """构建一个宿主的自包含静态 LLVM 可执行文件并逐项验收。"""
    parser = argparse.ArgumentParser(description="构建并验收自包含静态 LLVM 宿主")
    parser.add_argument("--host", choices=sorted(HOSTS),
                        help="运行 LLVM 桥的架构；默认按本机架构")
    args = parser.parse_args()
    host = args.host or local_host()
    work = WORK_ROOT / f"llvm-host-{host}"
    work.mkdir(parents=True, exist_ok=True)

    sdk = runpy.run_path(str(ROOT / "tools/llvm-sdk.py"))
    lock = json.loads((ROOT / "vendor/llvm/sdk.lock.json").read_text(encoding="utf-8"))
    manifest_sha256 = digest(ROOT / "vendor/llvm/sdk.lock.json")
    lock = {**lock, **lock["hosts"][host], "host": host}
    prefix = sdk["prepare"](lock)
    config = sdk["build"](lock, prefix)

    client = work / "host-client.c"
    client.write_text(HOST_CLIENT, encoding="utf-8")
    object_file = work / "host-client.o"
    compiled = run([config["cc"], "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I" + str(ROOT / "compiler/llvm"), "-c", str(client),
                    "-o", str(object_file)])
    if compiled.returncode != 0:
        raise RuntimeError(compiled.stderr)

    executable = work / "yh-llvm-host"
    executable.unlink(missing_ok=True)
    sdk["link"](config, [str(object_file)], executable)

    needed = readelf_needed(executable)
    lowered = [name.lower() for name in needed]
    if any("llvm" in name or "clang" in name for name in lowered):
        raise RuntimeError(f"宿主仍动态依赖 LLVM：{needed}")
    machine, machine_name = readelf_machine(executable)
    if machine != HOSTS[host]["machine"]:
        raise RuntimeError(f"宿主机器码不符：{machine_name}（期望 {HOSTS[host]['machine']}）")
    symbols = {name: symbol_type(executable, name) for name in BRIDGE_SYMBOLS}
    if not all(symbols.values()):
        raise RuntimeError(f"宿主未定义桥符号：{symbols}")

    runner = runner_for(host, executable)
    version = run([*runner, "--version"])
    if version.returncode != 0:
        raise RuntimeError(version.stderr)
    version_line = version.stdout.strip()
    if not version_line.startswith(f"yh-llvm-host llvm {lock['llvm_version']}"):
        raise RuntimeError(f"宿主版本行不符：{version_line}")
    probes = emit_probes(work, runner)
    rejected = negative_probes(work, runner)

    executable_sha256 = digest(executable)
    record = {
        "host": host, "build_host": sdk["build_host"](), "llvm_version": lock["llvm_version"],
        "bridge_abi": lock["bridge_abi"], "machine": machine, "machine_name": machine_name,
        "executable": relative(executable), "executable_sha256": executable_sha256,
        "executable_bytes": executable.stat().st_size,
        "runner": [str(Path(runner[0]).name), *runner[1:-1]], "version_line": version_line,
        "bridge_archive": relative(Path(config["archive"])),
        "bridge_sha256": config["bridge_sha256"],
        "selfhost_flags": relative(Path(config["selfhost_flags"])),
        "selfhost_flags_sha256": config["selfhost_flags_sha256"],
        "selfhost_runtime": relative(Path(config["selfhost_runtime"])),
        "selfhost_runtime_sha256": config["selfhost_runtime_sha256"],
        "bridge_source_sha256": config["bridge_source_sha256"],
        "bridge_header_sha256": config["bridge_header_sha256"],
        "lld_stub_source_sha256": config["lld_stub_source_sha256"],
        "sdk_builder_sha256": config["sdk_builder_sha256"],
        "sdk_sha256": config["sdk_sha256"], "sdk_manifest_sha256": manifest_sha256,
        "sdk_prefix": relative(prefix), "cc": config["cc"], "cxx": config["cxx"],
        "ar": config["ar"], "link_flags": config["link_flags"],
        "needed": needed, "no_llvm_shared_dependency": True, "symbols": symbols,
        "probes": probes, "rejected_cases": rejected,
        "scope": "自包含静态 LLVM 宿主；不安装系统 LLVM，不调用 llvm-config",
        **({"lld_version": config["lld_version"],
            "lld_bridge_source_sha256": config["lld_bridge_source_sha256"],
            "lld_archives": config["lld_archives"],
            "lld_component_count": config["lld_component_count"]}
           if config.get("lld_version") else {}),
    }
    (work / "host.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
    print(f"静态 LLVM 宿主通过：{host} machine={machine}({machine_name}) "
          f"needed={needed} 符号={symbols} sha256={executable_sha256}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, OSError) as error:
        print(f"LLVM 宿主：{error}", file=sys.stderr)
        raise SystemExit(1)
