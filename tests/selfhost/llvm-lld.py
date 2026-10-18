#!/usr/bin/env python3
"""LL9L 探针：固定 LLVM SDK + 同进程 lld ELF 链接。"""

import json
import os
import runpy
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/llvm-migration/lld-probe"
HOST = "linux-x86_64"

START_SOURCE = r"""
.globl _start
.text
_start:
    mov $60, %rax
    mov $7, %rdi
    syscall
"""

CLIENT_SOURCE = r"""
#include <stdio.h>
#include <stdint.h>
#include <string.h>

extern int yh_llvm_emit(const char *, uint64_t, const char *, int, int,
                        const char *, char *, uint64_t);
extern int yh_lld_link(const char **argv, int argc, char *diagnostic,
                       unsigned long capacity);
extern int yh_lld_link_driver(const char *output, const char **objects,
                              int object_count, const char **extra_args,
                              int extra_count, char *diagnostic,
                              unsigned long capacity);
extern const char *yh_lld_link_identity(void);

static int link_one(const char *object, const char *output) {
    const char *args[] = {"ld.lld", "-static", "-o", output,
                          "-e", "_start", object};
    char diagnostic[4096] = {0};
    int rc = yh_lld_link(args, 7, diagnostic, sizeof(diagnostic));
    if (rc != 0) {
        fprintf(stderr, "%s\n", diagnostic[0] ? diagnostic : "lld 失败且无诊断");
        return rc;
    }
    return 0;
}

static int link_driver_one(const char *object, const char *output) {
    const char *objects[] = {object};
    char diagnostic[4096] = {0};
    int rc = yh_lld_link_driver(output, objects, 1, NULL, 0,
                                diagnostic, sizeof(diagnostic));
    if (rc != 0) {
        fprintf(stderr, "%s\n", diagnostic[0] ? diagnostic : "lld 驱动链接失败且无诊断");
        return rc;
    }
    return 0;
}

static int emit_target_object(const char *triple, const char *output) {
    char ir[256];
    char diagnostic[4096] = {0};
    int length = snprintf(ir, sizeof(ir),
        "target triple = \"%s\"\ndefine i32 @main() { entry: ret i32 0 }\n",
        triple);
    if (length < 0 || (size_t)length >= sizeof(ir)) return 37;
    int rc = yh_llvm_emit(ir, (uint64_t)length, triple, 0, 0, output,
                          diagnostic, sizeof(diagnostic));
    if (rc != 0) {
        fprintf(stderr, "%s\n", diagnostic[0] ? diagnostic : "LLVM 跨目标对象发射失败");
        return 38;
    }
    return 0;
}

static int link_macho(const char *object, const char *output) {
    const char *args[] = {"ld64.lld", "-flavor", "darwin", "-arch", "x86_64",
        "-platform_version", "macos", "10.13", "14.0", "-e", "_main",
        "-o", output, object};
    char diagnostic[4096] = {0};
    int rc = yh_lld_link(args, (int)(sizeof(args) / sizeof(args[0])),
                         diagnostic, sizeof(diagnostic));
    if (rc != 0) {
        fprintf(stderr, "%s\n", diagnostic[0] ? diagnostic : "Mach-O lld 链接失败");
        return 39;
    }
    return 0;
}

static int link_coff(const char *object, const char *output) {
    char output_arg[1024];
    if (snprintf(output_arg, sizeof(output_arg), "/out:%s", output) < 0 ||
        strlen(output_arg) >= sizeof(output_arg) - 1) return 40;
    const char *args[] = {"lld-link", "-flavor", "link", "/entry:main",
        "/subsystem:console", "/nodefaultlib", output_arg, object};
    char diagnostic[4096] = {0};
    int rc = yh_lld_link(args, (int)(sizeof(args) / sizeof(args[0])),
                         diagnostic, sizeof(diagnostic));
    if (rc != 0) {
        fprintf(stderr, "%s\n", diagnostic[0] ? diagnostic : "COFF lld 链接失败");
        return 41;
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 4 && strcmp(argv[1], "--driver") == 0)
        return link_driver_one(argv[2], argv[3]) == 0 ? 0 : 35;
    if (argc == 4 && strcmp(argv[1], "--cross-macho") == 0) {
        int rc = emit_target_object("x86_64-apple-darwin", argv[2]);
        return rc == 0 ? link_macho(argv[2], argv[3]) : rc;
    }
    if (argc == 4 && strcmp(argv[1], "--cross-coff") == 0) {
        int rc = emit_target_object("x86_64-pc-windows-msvc", argv[2]);
        return rc == 0 ? link_coff(argv[2], argv[3]) : rc;
    }
    if (argc == 2 && strcmp(argv[1], "--identity") == 0)
        return strlen(yh_lld_link_identity()) == 64 ? 0 : 36;
    if (argc == 4 && strcmp(argv[1], "--reject") == 0) {
        const char *args[] = {"ld.lld", "-o", argv[2], argv[3]};
        char diagnostic[8];
        memset(diagnostic, 'x', sizeof(diagnostic));
        int rc = yh_lld_link(args, 4, diagnostic, sizeof(diagnostic));
        if (rc == 0 || diagnostic[0] == '\0' || diagnostic[7] != '\0')
            return 31;
        return 0;
    }
    if (argc != 4) return 32;
    if (link_one(argv[1], argv[2]) != 0) return 33;
    if (link_one(argv[1], argv[3]) != 0) return 34;
    return 0;
}
"""

SELFHOST_SOURCE = r"""
extern const char *yh_llvm_version(void);

int main(void) {
    const char *version = yh_llvm_version();
    return version != 0 && version[0] == '2' ? 0 : 1;
}
"""


def run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """运行一条探针命令并保留输出，供失败信息与差分检查使用。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=600, env=env)


def require_success(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """执行必须成功的构建或检查命令，失败时带上原始 stdout/stderr。"""
    result = run(command, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"命令失败 {command}:\n{result.stdout}{result.stderr}")
    return result


def elf_machine(path: Path) -> int:
    """读取 ELF 头部的 Machine 名称，并返回 x86_64 的编号 62。"""
    result = require_success(["/usr/bin/readelf", "-h", str(path)])
    for line in result.stdout.splitlines():
        if line.strip().startswith("Machine:"):
            machine = line.split(":", 1)[1].strip()
            if machine == "Advanced Micro Devices X86-64":
                return 62
            raise RuntimeError(f"ELF machine 不符：{machine}")
    raise RuntimeError(f"readelf 未输出 Machine：{path}")


def macho_magic(path: Path) -> bytes:
    """读取 Mach-O 文件魔数，确认 lld 实际产出 64 位小端 Mach-O。"""
    magic = path.read_bytes()[:4]
    if magic != b"\xcf\xfa\xed\xfe":
        raise RuntimeError(f"Mach-O magic 不符：{path} = {magic.hex()}")
    return magic


def pe_machine(path: Path) -> int:
    """读取 PE/COFF 文件头，确认 Windows x86_64 链接结果。"""
    data = path.read_bytes()
    if data[:2] != b"MZ" or len(data) < 0x40:
        raise RuntimeError(f"PE DOS 头不符：{path}")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise RuntimeError(f"PE 签名不符：{path}")
    machine = struct.unpack_from("<H", data, pe_offset + 4)[0]
    if machine != 0x8664:
        raise RuntimeError(f"PE machine 不符：{path} = 0x{machine:04x}")
    return machine


def elf_needed(path: Path) -> list[str]:
    """读取 ELF 的直接动态依赖，用于拒绝 LLVM/lld 动态库旁车。"""
    result = require_success(["/usr/bin/readelf", "-d", str(path)])
    return [line.split("[", 1)[1].split("]", 1)[0]
            for line in result.stdout.splitlines() if "(NEEDED)" in line]


def check_program(path: Path, env: dict[str, str], expected: tuple[int, str]) -> None:
    """运行无 libc 入口程序并核对退出码、标准输出和动态依赖。"""
    result = run([str(path)], env=env)
    if (result.returncode, result.stdout) != expected:
        raise RuntimeError(f"运行结果不符 {path.name}: rc={result.returncode}, stdout={result.stdout!r}")
    if any("llvm" in name.lower() or "lld" in name.lower() for name in elf_needed(path)):
        raise RuntimeError(f"产物动态依赖 LLVM/lld：{path}")


def main() -> int:
    """从固定 SDK 构建 shim，隔离 PATH 调用 lld，并和 gcc 的 ELF 结果对照。"""
    manifest = json.loads((ROOT / "vendor/llvm/sdk.lock.json").read_text(encoding="utf-8"))
    host_lock = manifest["hosts"][HOST]
    if "lld" not in host_lock:
        raise RuntimeError("固定 SDK 尚未锁定 LL9L 的 x86_64 lld 归档")

    sdk = runpy.run_path(str(ROOT / "tools/llvm-sdk.py"))
    lock = {**manifest, **host_lock, "host": HOST}
    prefix = sdk["prepare"](lock)
    config = sdk["build"](lock, prefix)
    if config.get("lld_version") != lock["lld"]["version"]:
        raise RuntimeError("桥配置中的 lld 版本与固定清单不符")
    if len(config.get("lld_link_config_sha256", "")) != 64:
        raise RuntimeError("桥配置缺少稳定的 lld 默认链接身份")
    if "share/LICENSE-lld" not in {Path(path).relative_to(prefix).as_posix()
                                   for path in config["licenses"]}:
        raise RuntimeError("SDK 未保留 LLD 版权/许可文件")

    WORK.mkdir(parents=True, exist_ok=True)
    start = WORK / "start.s"
    start.write_text(START_SOURCE, encoding="utf-8")
    object_file = WORK / "start.o"
    require_success([config["cc"], "-c", str(start), "-o", str(object_file)])

    main_source = WORK / "main.c"
    main_source.write_text("int main(void) { return 7; }\n", encoding="utf-8")
    main_object = WORK / "main.o"
    require_success([config["cc"], "-std=c11", "-c", str(main_source), "-o",
                     str(main_object)])

    selfhost_source = WORK / "selfhost.c"
    selfhost_source.write_text(SELFHOST_SOURCE, encoding="utf-8")
    selfhost_object = WORK / "selfhost.o"
    require_success([config["cc"], "-std=c11", "-c", str(selfhost_source), "-o",
                     str(selfhost_object)])

    client_source = WORK / "client.c"
    client_source.write_text(CLIENT_SOURCE, encoding="utf-8")
    client_object = WORK / "client.o"
    require_success([config["cc"], "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                     "-c", str(client_source), "-o", str(client_object)])
    client = WORK / "lld-client"
    client.unlink(missing_ok=True)
    sdk["link"](config, [str(client_object)], client)
    if elf_machine(client) != 62:
        raise RuntimeError("lld shim 客户端不是 x86_64 ELF")
    if any("llvm" in name.lower() or "lld" in name.lower() for name in elf_needed(client)):
        raise RuntimeError("lld shim 客户端动态依赖 LLVM/lld")

    shim_result = subprocess.run(
        [sys.executable, str(ROOT / "tools/llvm-host.py"), "shim",
         "--host", HOST, "--mode", "auto"],
        cwd=ROOT, capture_output=True, text=True, check=True)
    shim_info = json.loads(shim_result.stdout.splitlines()[-1])
    shim = Path(shim_info["shim_dir"]) / "gcc"
    query = subprocess.run([str(shim), "-print-search-dirs"],
                           capture_output=True, text=True)
    query_oracle = subprocess.run([config["cc"], "-print-search-dirs"],
                                  capture_output=True, text=True)
    if query.returncode != 0 or query.stdout != query_oracle.stdout:
        raise RuntimeError("内嵌 LLVM gcc shim 未透传链接器缓存所需查询")

    empty_path = WORK / "empty-path"
    empty_path.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["PATH"] = str(empty_path)
    for name in ("cc", "gcc", "lld", "ld.lld"):
        if shutil.which(name, path=env["PATH"]):
            raise RuntimeError(f"隔离 PATH 意外包含工具：{name}")

    outputs = [WORK / "lld-one", WORK / "lld-two"]
    for path in outputs:
        path.unlink(missing_ok=True)
    require_success([str(client), str(object_file), *(str(path) for path in outputs)], env=env)
    driver_output = WORK / "lld-driver"
    driver_output.unlink(missing_ok=True)
    require_success([str(client), "--driver", str(main_object), str(driver_output)], env=env)
    selfhost_env = dict(env)
    selfhost_env["YH_LLVM_SELFHOST"] = "1"
    selfhost_output = WORK / "lld-selfhost"
    selfhost_output.unlink(missing_ok=True)
    require_success([str(client), "--driver", str(selfhost_object),
                     str(selfhost_output)], env=selfhost_env)
    check_program(selfhost_output, env, (0, ""))
    require_success([str(client), "--identity"], env=env)
    cross_macho_object = WORK / "cross-macho.o"
    cross_macho = WORK / "cross-macho"
    cross_coff_object = WORK / "cross-coff.obj"
    cross_coff = WORK / "cross-coff.exe"
    for path in (cross_macho_object, cross_macho, cross_coff_object, cross_coff):
        path.unlink(missing_ok=True)
    require_success([str(client), "--cross-macho", str(cross_macho_object),
                    str(cross_macho)], env=env)
    require_success([str(client), "--cross-coff", str(cross_coff_object),
                    str(cross_coff)], env=env)
    macho_magic(cross_macho)
    pe_machine(cross_coff)
    baseline = WORK / "gcc-baseline"
    baseline.unlink(missing_ok=True)
    require_success([config["cc"], "-no-pie", "-o", str(baseline), str(main_object)])
    for output in [*outputs]:
        if elf_machine(output) != 62:
            raise RuntimeError(f"探针输出不是 ELF machine=62：{output}")
        check_program(output, env, (7, ""))
    require_success([config["cc"], "-no-pie", "-o", str(baseline), str(main_object)])
    for output in (driver_output, baseline):
        if elf_machine(output) != 62:
            raise RuntimeError(f"探针输出不是 ELF machine=62：{output}")
        check_program(output, env, (7, ""))
    rejected = WORK / "should-not-exist"
    rejected.unlink(missing_ok=True)
    require_success([str(client), "--reject", str(rejected), str(WORK / "missing.o")], env=env)
    if rejected.exists():
        raise RuntimeError("lld 拒绝输入后仍发布了产物")
    print("LL9L 探针通过：内嵌 ELF 链接模板、自举桥注入、同进程 lld 重入、诊断截断、ELF/Mach-O/PE 头、退出码与 gcc 对照、无 LLVM/lld 动态依赖")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        print(f"LL9L 探针：{error}", file=sys.stderr)
        raise SystemExit(1)
