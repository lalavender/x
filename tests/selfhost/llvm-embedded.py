#!/usr/bin/env python3
"""独立验收静态 LLVM C ABI 桥；测试宿主并不代表 yh 已完成后端替换。"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/llvm-migration/embedded"
TRIPLE = "x86_64-unknown-linux-gnu"
IR = "define i32 @main() { entry: ret i32 0 }\n"
BAD_VERIFY = "define i32 @main() { entry: %x = add i32 %x, 1\n ret i32 %x }\n"
CLIENT = r'''
#include "bridge.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* main：以重复的成功/失败调用检查桥的资源生命周期与有界诊断。 */
int main(int argc, char **argv) {
    if (argc != 7) return 90;
    /* 零/一字节诊断缓冲与空输入必须明确失败，且不能写过调用方缓冲。 */
    char guard[2] = {'X', 'Y'};
    if (yh_llvm_emit(NULL, 0, argv[2], 0, 0, argv[5], guard, 1) != -1
        || guard[0] != 0 || guard[1] != 'Y') return 98;
    if (yh_llvm_emit(NULL, 0, argv[2], 0, 0, argv[5], NULL, 0) != -1) return 99;
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 91;
    if (fseek(f, 0, SEEK_END)) return 92;
    long length = ftell(f);
    if (length < 0 || fseek(f, 0, SEEK_SET)) return 93;
    char *text = malloc((size_t)length + 1);
    if (!text || fread(text, 1, (size_t)length, f) != (size_t)length) return 94;
    fclose(f);
    text[length] = 0;
    char diagnostic[4096];
    int result = 0;
    for (int i = 0; i < 4; ++i) {
        diagnostic[0] = 'X';
        result = yh_llvm_emit(text, (uint64_t)length, argv[2], atoi(argv[3]),
                              atoi(argv[4]), argv[5], diagnostic, sizeof(diagnostic));
        if (result == 0 && diagnostic[0]) return 95;
        if (result && !diagnostic[0]) return 96;
    }
    if (result) fprintf(stderr, "%s\n", diagnostic);
    if (strcmp(yh_llvm_version(), "21.1.8")) return 97;
    free(text);
    return result ? 1 : 0;
}
'''


def run(command: list[str], timeout: int = 120, **kwargs) -> subprocess.CompletedProcess:
    """执行有超时的真实工具或宿主，保留 stdout/stderr 供失败诊断。"""
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, **kwargs)


def main() -> int:
    """构建静态测试宿主，验证 O0/O2 输出、拒绝层与无系统 LLVM 的隔离根。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--chroot", action="store_true", help="在只有动态 OS 库的隔离根复验")
    args = parser.parse_args()
    assert (ROOT / "compiler/llvm/bridge.c").is_file(), "内嵌 LLVM 桥尚未实现"
    assert (ROOT / "tools/llvm-sdk.py").is_file(), "固定 SDK 构建工具尚未实现"
    WORK.mkdir(parents=True, exist_ok=True)
    client = WORK / "client.c"
    client.write_text(CLIENT, encoding="utf-8")
    executable = WORK / "client"
    client_object = WORK / "client.o"
    compiled = run(["/usr/bin/gcc", "-O2", "-I" + str(ROOT / "compiler/llvm"), "-c", str(client),
                    "-o", str(client_object)])
    assert compiled.returncode == 0, compiled.stderr
    linked = run(["/usr/bin/python3", str(ROOT / "tools/llvm-sdk.py"), "link",
                  "--object", str(client_object), "--output", str(executable)], timeout=300)
    assert linked.returncode == 0, linked.stdout + linked.stderr
    config = json.loads(linked.stdout)
    assert config["llvm_version"] == "21.1.8" and config["bridge_abi"] == 1
    signature = run([str(ROOT / "yh"), "--emit-asm",
                     str(ROOT / "tests/selfhost/llvm-embedded-probe.yh")])
    assert signature.returncode == 0, signature.stderr
    (WORK / "yh-probe.s").write_text(signature.stdout, encoding="utf-8")
    dynamic = run(["/usr/bin/readelf", "-d", str(executable)])
    assert dynamic.returncode == 0 and "libLLVM" not in dynamic.stdout, dynamic.stdout
    env = dict(os.environ, PATH=str(WORK / "no-tools"))
    (WORK / "no-tools").mkdir(exist_ok=True)
    irfile = WORK / "valid.ll"
    irfile.write_text(IR, encoding="utf-8")
    for opt in (0, 2):
        for target, machine in ((TRIPLE, 62), ("aarch64-unknown-linux-gnu", 183)):
            obj = WORK / f"probe-{machine}-O{opt}.o"
            result = run([str(executable), str(irfile), target, str(opt), "0", str(obj), "probe"], env=env)
            assert result.returncode == 0, result.stderr
            data = obj.read_bytes()
            assert data[:5] == b"\x7fELF\x02" and int.from_bytes(data[18:20], "little") == machine
            if machine == 62:
                binary = WORK / f"probe-O{opt}"
                result = run(["/usr/bin/gcc", "-no-pie", str(obj), "-o", str(binary)])
                assert result.returncode == 0, result.stderr
                result = run([str(binary)], env=env)
                assert result.returncode == 0, result.stderr
        assembly = WORK / f"probe-O{opt}.s"
        result = run([str(executable), str(irfile), TRIPLE, str(opt), "1", str(assembly), "probe"], env=env)
        assert result.returncode == 0 and "main" in assembly.read_text(), result.stderr
    failures = [("bad-ir", "not LLVM", TRIPLE, 0, 0, WORK / "bad-ir.o"),
                ("bad-verify", BAD_VERIFY, TRIPLE, 0, 0, WORK / "bad-verify.o"),
                ("bad-target", IR, "unknown-yh-target", 0, 0, WORK / "bad-target.o"),
                ("bad-opt", IR, TRIPLE, 1, 0, WORK / "bad-opt.o"),
                ("bad-kind", IR, TRIPLE, 0, 2, WORK / "bad-kind.o"),
                ("bad-layout", 'target datalayout = "e-p:32:32"\n' + IR,
                 TRIPLE, 0, 0, WORK / "bad-layout.o"),
                ("bad-module-target", 'target triple = "aarch64-unknown-linux-gnu"\n' + IR,
                 TRIPLE, 0, 0, WORK / "bad-module-target.o"),
                ("bad-path", IR, TRIPLE, 0, 0, WORK / "missing/output.o")]
    for name, text, target, opt, kind, output in failures:
        source = WORK / f"{name}.ll"
        source.write_text(text, encoding="utf-8")
        output.unlink(missing_ok=True)
        result = run([str(executable), str(source), target, str(opt), str(kind), str(output), "probe"], env=env)
        assert result.returncode == 1 and result.stderr, f"{name}: {result}"
        assert not output.exists(), f"{name} 发布了失败产物"
    preserved = WORK / "preserved.o"
    preserved.write_bytes(b"previous valid artifact")
    result = run([str(executable), str(WORK / "bad-verify.ll"), TRIPLE, "0", "0",
                  str(preserved), "probe"], env=env)
    assert result.returncode == 1 and preserved.read_bytes() == b"previous valid artifact"
    directory = WORK / "directory-output"
    directory.mkdir(exist_ok=True)
    result = run([str(executable), str(irfile), TRIPLE, "0", "0", str(directory), "probe"], env=env)
    assert result.returncode == 1 and directory.is_dir()
    assert not list(WORK.glob("*.yh-llvm-*")), "原子写入失败遗留临时文件"
    if args.chroot:
        assert os.geteuid() == 0, "--chroot 必须在 WSL root 下运行"
        # 每轮使用空根；此前排查留下的工具或库不能参与本轮无系统 LLVM 证明。
        with tempfile.TemporaryDirectory(prefix="isolated-root-", dir=WORK) as directory:
            sandbox = Path(directory)
            shutil.copy2(executable, sandbox / "client")
            shutil.copy2(irfile, sandbox / "input.ll")
            dependencies = run(["/usr/bin/ldd", str(executable)])
            assert dependencies.returncode == 0, dependencies.stderr
            for line in dependencies.stdout.splitlines():
                paths = [part for part in line.split() if part.startswith("/")]
                for path in paths:
                    assert "llvm" not in path.lower(), path
                    dest = sandbox / path.lstrip("/")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dest)
            chroot = shutil.which("chroot", path="/usr/sbin:/usr/bin:/sbin:/bin")
            assert chroot, "缺少 chroot 隔离工具"
            result = run([chroot, str(sandbox), "/client", "/input.ll", TRIPLE,
                          "2", "0", "/output.o", "probe"], env=env)
            assert result.returncode == 0, result.stderr
            assert (sandbox / "output.o").read_bytes()[:5] == b"\x7fELF\x02"
    report = {"llvm": "21.1.8", "needed": dynamic.stdout, "o0_o2": True,
              "machines": [62, 183], "negative_cases": len(failures), "chroot": args.chroot,
              "scope": "独立桥测试宿主；未接入 yh 前端/自举"}
    (WORK / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"内嵌 LLVM 桥门通过：O0/O2、x64/ARM64、{len(failures)} 个拒绝案例、无 LLVM 工具 PATH，chroot={args.chroot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
