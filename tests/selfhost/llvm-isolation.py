#!/usr/bin/env python3
"""LL11：无系统 LLVM 工具/动态库的隔离环境验证。

在 bubblewrap 沙箱里以 PATH=/nonexistent（根文件系统只读，仓库与工作目录
可写）验证最终 x64 编译器：

  1. 单文件编译/链接/运行 .yh；
  2. 冷编 compiler/ 自举一代（--backend llvm，显式目标）；
  3. readelf -d 断言产物 NEEDED 不含 LLVM/lld；
  4. 若宿主有 strace，断言 execve 只出现编译器自身，没有外部 LLVM 旁车。

用法：
  python3 tests/selfhost/llvm-isolation.py [--compiler bin/yh-linux-x64] [--skip-cold]
退出码：全部通过 0。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRIPLE = "x86_64-unknown-linux-gnu"
HELLO = ROOT / "tests" / "yh-run" / "run" / "01-hello.yh"
PROJECT = ROOT / "tests" / "modules" / "projects" / "runtimeplain"
WORK = ROOT / "tmp" / "ll11-isolation"
FORBIDDEN_EXEC = ("clang", "llc", "opt", "llvm-as", "llvm-link", "llvm-mc",
                  "ld.lld", "lld")


def run(command, **kwargs):
    """执行命令并保留输出，失败时由调用方打印诊断。"""
    return subprocess.run(command, capture_output=True, text=True, **kwargs)


def sandbox(command, cwd, env=None, strace_log=None):
    """在 bwrap 沙箱内执行命令；strace_log 非空时先用 strace -f 记录 execve。"""
    # 不单独挂 --dev：WSL 下偶发 execvp 解析问题；--ro-bind / / 已包含 /dev。
    base = ["/usr/bin/bwrap", "--ro-bind", "/", "/", "--tmpfs", "/tmp",
            "--bind", str(ROOT), str(ROOT)]
    base += ["--setenv", "PATH", "/nonexistent"]
    for key, value in (env or {}).items():
        base += ["--setenv", key, value]
    base += ["--chdir", str(cwd)]
    if strace_log is not None:
        base += ["/usr/bin/strace", "-f", "-e", "trace=execve",
                 "-o", str(strace_log)]
    return run(base + list(command), timeout=1800)


def readelf_needs(path):
    """返回 ELF 的动态 NEEDED 列表；readelf 缺失时失败。"""
    result = run(["readelf", "-d", str(path)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-400:])
    needs = []
    for line in result.stdout.splitlines():
        if "NEEDED" in line and "[" in line:
            needs.append(line.split("[", 1)[1].rstrip("]"))
    return needs


def assert_no_llvm_dependency(path):
    """断言产物的动态依赖不含 LLVM/lld。"""
    needs = readelf_needs(path)
    bad = [name for name in needs if "llvm" in name.lower() or "lld" in name.lower()]
    if bad:
        raise RuntimeError(f"{path} 动态依赖 LLVM/lld：{bad}")
    print(f"readelf NEEDED 无 LLVM/lld：{path.name} -> {needs}")


def assert_execve_clean(log):
    """断言 strace 日志的 execve 只出现编译器自身。"""
    if not log.is_file():
        raise RuntimeError(f"缺少 strace 日志：{log}")
    execs = []
    for line in log.read_text(errors="replace").splitlines():
        if 'execve("' in line:
            execs.append(line.split('execve("', 1)[1].split('"', 1)[0])
    bad = [name for name in execs
           if any(token in os.path.basename(name) for token in FORBIDDEN_EXEC)]
    if bad:
        raise RuntimeError(f"隔离环境调用了外部 LLVM 工具：{bad}")
    print(f"execve 审计通过：仅 {sorted(set(execs))}")


def main() -> int:
    """按隔离环境的四个判据顺序执行，全部通过返回 0。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(ROOT / "bin" / "yh-linux-x64"))
    parser.add_argument("--skip-cold", action="store_true",
                        help="跳过冷编自举（只验证单文件与依赖面）")
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve()
    if shutil.which("bwrap") is None:
        print("FAIL 缺少 bubblewrap（bwrap）")
        return 1
    if not compiler.is_file():
        print(f"FAIL 编译器不存在：{compiler}")
        return 1
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    strace_ok = Path("/usr/bin/strace").is_file()

    hello = WORK / "hello"
    log = WORK / "hello-execve.log" if strace_ok else None
    result = sandbox([str(compiler), str(HELLO), "-o", str(hello)], ROOT, strace_log=log)
    if result.returncode != 0:
        print(f"FAIL 单文件编译失败：rc={result.returncode}\n{result.stderr[-600:]}")
        return 1
    execution = run([str(hello)])
    if execution.stdout != "hello, yh!\n":
        print(f"FAIL 单文件运行输出：{execution.stdout!r} {execution.stderr[-300:]}")
        return 1
    print("单文件编译/链接/运行通过（隔离 PATH）")
    assert_no_llvm_dependency(compiler)
    assert_no_llvm_dependency(hello)
    if log is not None:
        assert_execve_clean(log)

    project = WORK / "project"
    shutil.copytree(PROJECT, project)
    log = WORK / "project-execve.log" if strace_ok else None
    result = sandbox([str(compiler), "build"], project, strace_log=log)
    if result.returncode != 0:
        print(f"FAIL 项目构建失败：rc={result.returncode}\n{result.stderr[-600:]}")
        return 1
    print("项目构建通过（隔离 PATH）")

    if not args.skip_cold:
        cold = WORK / "yh-cold"
        shutil.rmtree(ROOT / "compiler" / ".build", ignore_errors=True)
        # compiler/ 已迁移 [link] 清单：桥/lld/LLVM 归档由清单提供，旧闭包注入
        # 必须关闭（否则桥归档在同一条链接命令里出现两次，ld.lld 报
        # duplicate symbol）；运行库参数仍取构建机的配方文件。SELFHOST 显式
        # 置空，避免调用者环境里的旧链路把闭包再注入一次。
        host_record = json.loads((ROOT / "tmp/llvm-migration/llvm-host-linux-x86_64/host.json")
                                 .read_text(encoding="utf-8"))
        runtime_path = (ROOT / host_record["selfhost_runtime"]).resolve()
        result = sandbox([
            str(compiler), "--backend", "llvm", "--target", TRIPLE,
            "--stats", "build", "--emit-llvm", "-o", str(cold),
        ], ROOT / "compiler", env={"YH_LLVM_SELFHOST": "",
                                   "YH_LLVM_SELFHOST_FLAGS": "",
                                   "YH_LINK_MANIFEST_ONLY": "1",
                                   "YH_LINK_RUNTIME_FLAGS": str(runtime_path)})
        if result.returncode != 0:
            print(f"FAIL 隔离冷编自举失败：rc={result.returncode}\n{result.stderr[-800:]}")
            return 1
        if "fallback_functions=0" not in (result.stdout + result.stderr):
            print("FAIL 冷编自举存在后端回退")
            return 1
        assert_no_llvm_dependency(cold)
        probe = WORK / "hello-cold"
        result = sandbox([str(cold), str(HELLO), "-o", str(probe)], ROOT)
        if result.returncode != 0 or run([str(probe)]).stdout != "hello, yh!\n":
            print("FAIL 冷编产物不能编译/运行 .yh")
            return 1
        print("隔离冷编自举通过：yh-cold 可编译/运行 .yh，fallback=0")

    print("LL11 隔离环境验证：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
