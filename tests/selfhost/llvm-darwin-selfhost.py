#!/usr/bin/env python3
"""F2-8：Darwin/ARM64 从入库种子编 A，A 以 LLVM 连续编 B/C/D。

- A：现有 Darwin 种子以 LLVM 代码生成、链入真实静态 LLVM 桥的过渡代
  （LL12 后种子只支持 LLVM，A 与 B/C/D 同一后端）；
- B/C/D：A 及后续代以显式 `--backend llvm` 编出，O0/O2 各自比较 B→C→D 的
  `.ll/.s.i/.s.ct` 逐字节固定点，并冻结各代 checked/emitted/rejected/fallback；
- 最终 D-O2 上跑自解析、语法/运行/模块/项目全门与 Darwin 专项门（ABI、runtime、
  链接、缓存、桥身份），同时在隔离 PATH 下确认没有调用系统 LLVM 工具。
"""

import argparse
import concurrent.futures
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILER = ROOT / "compiler"
TRIPLE = "aarch64-apple-darwin"
PROBE = ROOT / "tests/selfhost/llvm-darwin-fixedpoint.yh"
HOST_RECORD = ROOT / "tmp/llvm-migration/llvm-host-darwin-aarch64/host.json"
SDK_RECORD = ROOT / "tmp/llvm-migration/darwin-sdk/sdk-darwin-aarch64/host.json"
GENERATIONS = ("B", "C", "D")
LEVELS = ("0", "2")
MACHO_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
CPU_TYPE_X86_64 = 0x01000007
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))
from selfhost_snapshot_gate import default_seed, expected_llvm_artifacts, \
    llvm_snapshot_errors, save_llvm_snapshot, snapshot_errors, verify_seed


def run(command, *, cwd=ROOT, env=None, timeout=3600):
    """执行一步自举命令并完整捕获输出。"""
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=timeout)


def require_darwin_arm64():
    """本门只接受可原生执行 arm64 Mach-O 的 Darwin 宿主。"""
    if sys.platform != "darwin" or platform.machine().lower() not in ("arm64", "aarch64"):
        raise RuntimeError("F2-8 自举门需要 Darwin/ARM64 原生宿主")


def macho_cpu_type(path: Path) -> int:
    """读取 64 位 Mach-O 的 cputype；非 Mach-O 或截断返回 -1。"""
    data = path.read_bytes()[:8]
    if len(data) < 8:
        return -1
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != MACHO_MAGIC_64:
        return -1
    return struct.unpack_from("<I", data, 4)[0]


def base_environment() -> dict:
    """构造构建环境：显式 SDKROOT、自举闭包文件，剔除会改变后端选择的变量。"""
    environment = dict(os.environ)
    environment.pop("YH_LLVM_SELFHOST", None)
    environment.pop("YH_CC", None)
    # 自举闭包由构建机提供（种子不再烘焙绝对路径）；与 make / seed-build
    # 使用同一份 selfhost-flags.txt，换机器只需重新 prepare。
    if HOST_RECORD.is_file():
        record = json.loads(HOST_RECORD.read_text(encoding="utf-8"))
        flags_file = record.get("selfhost_flags_file")
        if flags_file:
            environment["YH_LLVM_SELFHOST_FLAGS"] = str((ROOT / flags_file).resolve())
    if not environment.get("SDKROOT") and SDK_RECORD.is_file():
        record = json.loads(SDK_RECORD.read_text(encoding="utf-8"))
        if record.get("sdk_root"):
            environment["SDKROOT"] = record["sdk_root"]
    if not environment.get("SDKROOT"):
        discovered = subprocess.run(["xcrun", "--sdk", "macosx", "--show-sdk-path"],
                                    capture_output=True, text=True, check=False)
        if discovered.returncode != 0 or not discovered.stdout.strip():
            raise RuntimeError("未找到 macOS SDK：请设置 SDKROOT 或安装 xcrun")
        environment["SDKROOT"] = discovered.stdout.strip()
    return environment


def log_result(work: Path, label: str, result):
    """保存每步的 stdout/stderr，失败时可离线复现。"""
    logs = work / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"{label}.stdout.log").write_text(result.stdout, encoding="utf-8")
    (logs / f"{label}.stderr.log").write_text(result.stderr, encoding="utf-8")


def parse_stats(output: str):
    """抽取 yh-stats 行并按计数器求和。"""
    rows = []
    for line in output.splitlines():
        if line.startswith("yh-stats "):
            rows.append(dict(item.split("=", 1) for item in line.split()[1:]
                             if "=" in item))
    return rows


def check_build_stats(output: str, label: str):
    """要求 LLVM 构建无后端回退且覆盖数与受检数一致。"""
    rows = parse_stats(output)
    if not rows:
        raise RuntimeError(f"{label} 未输出 LLVM yh-stats")
    checked = sum(int(row.get("checked_functions", "0")) for row in rows)
    emitted = sum(int(row.get("backend_emitted_functions", "0")) for row in rows)
    rejected = sum(int(row.get("rejected_functions", "0")) for row in rows)
    backend_rejected = sum(int(row.get("backend_rejected_functions", "0")) for row in rows)
    fallback = sum(int(row.get("fallback_functions", "0")) for row in rows)
    if checked <= 0 or emitted != checked or fallback != 0:
        raise RuntimeError(f"{label} LLVM 覆盖门失败：checked={checked} "
                           f"emitted={emitted} rejected={rejected} "
                           f"backend_rejected={backend_rejected} fallback={fallback}")
    return {"checked": checked, "emitted": emitted, "rejected": rejected,
            "backend_rejected": backend_rejected, "fallback": fallback}


def generation_errors(rows, expected_labels):
    """拒绝代号、顺序或快照目录变化，防止错代比较或同目录自比较。"""
    labels = tuple(label for label, _snapshot, _directory in rows)
    if labels != tuple(expected_labels):
        return [f"候选代号/顺序不符：{labels}，期望 {tuple(expected_labels)}"]
    directories = []
    for label, _snapshot, directory in rows:
        path = Path(directory).resolve()
        if path.name != label:
            return [f"{label} 快照目录名不符：{path.name}"]
        directories.append(path)
    if len(set(directories)) != len(directories):
        return ["不同候选代复用了同一快照目录"]
    return []


def self_test():
    """自检：缺 .ll、错接口版本/triple/arch、错代号与目录、错 CPU 均被拒绝。"""
    expected = {"llvm/demo-main.ll", "iface/demo-main.s.i", "iface/demo-main.s.ct"}
    good = {
        "llvm/demo-main.ll": f'target triple = "{TRIPLE}"\n'.encode(),
        "iface/demo-main.s.i": b"// yh-iface v3 arch=arm64 suffix=demo\n",
        "iface/demo-main.s.ct": b"// yh-ctiface v1 arch=arm64 suffix=demo\n",
    }
    assert not llvm_snapshot_errors(good, expected, TRIPLE)
    missing = {key: value for key, value in good.items() if not key.endswith(".ll")}
    assert llvm_snapshot_errors(missing, expected, TRIPLE), "缺失 .ll 未被拒绝"
    bad_version = dict(good)
    bad_version["iface/demo-main.s.i"] = b"// yh-iface v9 arch=arm64 suffix=demo\n"
    assert llvm_snapshot_errors(bad_version, expected, TRIPLE), "接口版本错误未被拒绝"
    bad_triple = dict(good)
    bad_triple["llvm/demo-main.ll"] = b'target triple = "x86_64-unknown-linux-gnu"\n'
    assert llvm_snapshot_errors(bad_triple, expected, TRIPLE), "triple 错误未被拒绝"
    bad_arch = dict(good)
    bad_arch["iface/demo-main.s.ct"] = b"// yh-ctiface v1 arch=x64 suffix=demo\n"
    assert llvm_snapshot_errors(bad_arch, expected, TRIPLE), "接口 arch 错误未被拒绝"
    assert not generation_errors(
        [(name, {}, Path("snapshots") / name) for name in GENERATIONS], GENERATIONS)
    assert generation_errors(
        [("A", {}, Path("snapshots/A")), ("C", {}, Path("snapshots/C")),
         ("C", {}, Path("snapshots/C2")), ("D", {}, Path("snapshots/D"))],
        GENERATIONS), "错代号/复用目录未被拒绝"
    assert generation_errors(
        [(name, {}, Path("snapshots/wrong" if name == "C" else name))
         for name in GENERATIONS], GENERATIONS), "快照目录名不符未被拒绝"

    work = ROOT / "tmp/llvm-migration/darwin-selfhost-selftest"
    work.mkdir(parents=True, exist_ok=True)
    arm = work / "arm"
    x64 = work / "x64"
    trunc = work / "trunc"
    arm.write_bytes(struct.pack("<II", MACHO_MAGIC_64, CPU_TYPE_ARM64))
    x64.write_bytes(struct.pack("<II", MACHO_MAGIC_64, CPU_TYPE_X86_64))
    trunc.write_bytes(b"\xcf\xfa")
    assert macho_cpu_type(arm) == CPU_TYPE_ARM64
    assert macho_cpu_type(x64) == CPU_TYPE_X86_64 != CPU_TYPE_ARM64
    assert macho_cpu_type(trunc) == -1
    print("F2-8 自检通过：快照缺失/版本/triple/arch、代号与目录、Mach-O CPU 均按预期拒绝")


def verify_candidate(path: Path, env: dict, label: str):
    """核验候选是 arm64 Mach-O、可运行、无动态 LLVM/lld 且内嵌固定桥身份。"""
    if not path.is_file() or macho_cpu_type(path) != CPU_TYPE_ARM64:
        raise RuntimeError(f"{label} 不是 arm64 Mach-O：{path}")
    described = run(["/usr/bin/file", str(path)])
    if described.returncode != 0 or "Mach-O 64-bit executable arm64" not in described.stdout:
        raise RuntimeError(f"{label} file 校验失败：{described.stdout.strip()}")
    dependencies = run(["/usr/bin/otool", "-L", str(path)])
    if dependencies.returncode != 0:
        raise RuntimeError(f"{label} otool -L 失败：{dependencies.stderr[-1000:]}")
    for line in dependencies.stdout.splitlines()[1:]:
        library = line.strip().split(" ")[0]
        if not library:
            continue
        if "libLLVM" in library or "liblld" in library or "libclang" in library:
            raise RuntimeError(f"{label} 动态依赖 LLVM/lld：{library}")
        if not library.startswith("/usr/lib/"):
            raise RuntimeError(f"{label} 出现未审计的动态依赖：{library}")
    verified = run(["/usr/bin/codesign", "--verify", "--verbose=2", str(path)])
    if verified.returncode != 0:
        raise RuntimeError(f"{label} ad-hoc 签名校验失败：{verified.stderr[-800:]}")
    symbols = run(["/usr/bin/nm", "-gU", str(path)])
    if symbols.returncode != 0:
        raise RuntimeError(f"{label} nm 失败：{symbols.stderr[-800:]}")
    for line in symbols.stdout.splitlines():
        if re.search(r"\s[ABCDGIRSTVW]\s+_(?:malloc|free)$", line):
            raise RuntimeError(f"{label} 导出裸分配器名称：{line.strip()}")
    record = json.loads(HOST_RECORD.read_text(encoding="utf-8"))
    identity = record.get("lld_identity", "")
    if not re.fullmatch(r"[0-9a-f]{64}", identity):
        raise RuntimeError("宿主身份记录缺少 lld_identity")
    if identity.encode("ascii") not in path.read_bytes():
        raise RuntimeError(f"{label} 未嵌入固定 lld 链接身份")
    version = run([str(path), "version"], cwd=COMPILER, env=env)
    if version.returncode != 0:
        raise RuntimeError(f"{label} 不能原生执行 version：{version.stderr[-800:]}")
    print(f"{label}：arm64 Mach-O、签名有效、无动态 LLVM、原生可执行")


def build_transition_a(seed: Path, work: Path, env: dict):
    """用入库种子以 legacy 代码生成编出链入真实桥的过渡代 A。"""
    if (COMPILER / ".build").exists():
        shutil.rmtree(COMPILER / ".build")
    output = work / "candidates" / "yh-A"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(ROOT / "tools/seed-build.py"),
               "--compiler", str(seed), "--project", str(COMPILER),
               "--output", str(output), "--llvm-host", "darwin-aarch64",
               "--llvm-mode", "require"]
    result = run(command, env=env)
    log_result(work, "A-build", result)
    if result.returncode != 0:
        raise RuntimeError("过渡代 A 构建失败：\n"
                           f"{result.stdout[-3000:]}\n{result.stderr[-3000:]}")
    verify_candidate(output, env, "A")
    return output


def build_candidate(compiler: Path, label: str, level: str, work: Path,
                    env: dict, expected: set):
    """冷编一代候选并保存快照与统计。"""
    if (COMPILER / ".build").exists():
        shutil.rmtree(COMPILER / ".build")
    output = work / "candidates" / f"yh-{label}-O{level}"
    command = [str(compiler), "--backend", "llvm", "--target", TRIPLE,
               f"-O{level}", "--emit-llvm", "--stats", "build", "-o", str(output)]
    result = run(command, cwd=COMPILER, env=env)
    log_result(work, f"{label}-O{level}-build", result)
    if result.returncode != 0:
        raise RuntimeError(f"构建 {label}-O{level} 失败（rc={result.returncode}）：\n"
                           f"{result.stdout[-4000:]}\n{result.stderr[-4000:]}")
    stats = check_build_stats(result.stdout + result.stderr, f"{label}-O{level}")
    verify_candidate(output, env, f"{label}-O{level}")
    build_dir = COMPILER / ".build" / "targets" / TRIPLE / "llvm" / f"O{level}"
    snapshot_dir = work / "snapshots" / f"O{level}" / label
    snapshot = save_llvm_snapshot(build_dir, snapshot_dir)
    errors = llvm_snapshot_errors(snapshot, expected, TRIPLE)
    if errors:
        raise RuntimeError(f"{label}-O{level} 快照门失败：" + "；".join(errors))
    return output, snapshot, snapshot_dir, stats


def require_fixedpoint(rows, expected):
    """校验相邻代（B→C→D）.ll/.s.i/.s.ct 逐字节一致。"""
    errors = generation_errors(rows, GENERATIONS)
    if errors:
        raise RuntimeError("；".join(errors))
    for (left, left_files, _left_dir), (right, right_files, _right_dir) in zip(rows, rows[1:]):
        differences = snapshot_errors([(left, left_files), (right, right_files)], expected)
        if differences:
            raise RuntimeError(f"{left}→{right} 未达固定点：" + "；".join(differences))
        print(f"{left}→{right} 固定点：{len(expected)} 个 .ll/.s.i/.s.ct 逐字节一致")


def run_probe(compiler: Path, level: str, work: Path, env: dict):
    """用指定候选编译并运行 Darwin 固定点探针。"""
    output = work / "probes" / f"probe-O{level}-{compiler.name}"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [str(compiler), "--backend", "llvm", "--target", TRIPLE,
               f"-O{level}", "-o", str(output), str(PROBE)]
    result = run(command, cwd=ROOT, env=env)
    log_result(work, f"probe-{level}-{compiler.name}-build", result)
    if result.returncode != 0:
        raise RuntimeError(f"固定点探针构建失败：{result.stderr[-2000:]}")
    execution = run([str(output), "probe"], cwd=ROOT, env=env)
    log_result(work, f"probe-{level}-{compiler.name}-run", execution)
    if execution.returncode != 0 or not execution.stdout.startswith("llvm-darwin "):
        raise RuntimeError(f"固定点探针退出码 {execution.returncode}："
                           f"{execution.stdout!r} {execution.stderr[-800:]}")
    print(f"{compiler.name} LLVM O{level} 固定点探针：通过")


def self_parse(compiler: Path, jobs: int, work: Path, env: dict):
    """要求最终候选逐个自解析 compiler/ 下所有 .yh 文件。"""
    sources = sorted(COMPILER.rglob("*.yh"))
    def parse_one(source):
        return source, run([str(compiler), "--syntax-check", str(source)],
                           cwd=ROOT, env=env, timeout=120)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        failures = [(source, result) for source, result in pool.map(parse_one, sources)
                    if result.returncode != 0]
    if failures:
        detail = "\n".join(f"{path}: {result.stderr[-400:]}" for path, result in failures[:20])
        raise RuntimeError(f"最终候选自解析失败 {len(failures)}/{len(sources)}：\n{detail}")
    print(f"最终候选自解析：{len(sources)}/{len(sources)}")


def run_gate(label: str, command, work: Path, env: dict):
    """运行一条门禁命令、保存日志并在失败时给出摘要。"""
    result = run(command, cwd=ROOT, env=env)
    log_result(work, label, result)
    if result.returncode != 0:
        raise RuntimeError(f"{label} 失败：\n{result.stdout[-4000:]}\n{result.stderr[-4000:]}")
    summary = (result.stdout.strip().splitlines() or ["通过"])[-1]
    print(f"{label}：{summary}")


def run_final_gates(compiler: Path, jobs: int, work: Path, env: dict):
    """在 D-O2 上运行语法/运行/模块/项目与 Darwin 专项门。"""
    run_gate("final-grammar", [sys.executable, str(ROOT / "tests/yh/check.py"),
             "--compiler", "--compiler-path", str(compiler), "--quiet",
             "--jobs", str(max(1, jobs))], work, env)
    for level in LEVELS:
        run_gate(f"yh-run-O{level}", [sys.executable, str(ROOT / "tests/yh-run/check.py"),
                 "--compiler", str(compiler), "--backend", "llvm", "--target", TRIPLE,
                 "--opt-level", level, "--quiet", "--jobs", str(max(1, jobs)),
                 "--workdir", str(work / f"yh-run-O{level}")], work, env)
        run_gate(f"modules-O{level}", [sys.executable, str(ROOT / "tests/modules/check.py"),
                 "--compiler-path", str(compiler), "--backend", "llvm", "--target", TRIPLE,
                 "--opt-level", level, "--quiet", "--jobs", str(max(1, jobs))], work, env)
        run_gate(f"build-check-O{level}",
                 [sys.executable, str(ROOT / "tests/modules/build-check.py"),
                  "--compiler-path", str(compiler), "--backend", "llvm",
                  "--target", TRIPLE, "--opt-level", level, "--jobs",
                  str(max(1, min(jobs, 4))), "--workdir", str(work / f"modcheck-O{level}")],
                 work, env)
    for label, script, extra in (
            ("darwin-sdk", "llvm-darwin-sdk.py", []),
            ("darwin-host", "llvm-darwin-host.py", []),
            ("darwin-bridge", "llvm-darwin-bridge.py", ["--require-embedded"]),
            ("darwin-object", "llvm-darwin-object.py", []),
            ("darwin-abi", "llvm-darwin-abi.py", ["--suite", "full"]),
            ("darwin-runtime", "llvm-darwin-runtime.py", []),
            ("darwin-link", "llvm-darwin-link.py", []),
            ("darwin-cache", "llvm-darwin-cache.py", [])):
        run_gate(label, [sys.executable, str(ROOT / "tests/selfhost" / script),
                         "--compiler-path", str(compiler)] + extra, work, env)


def run_isolated_llvm_check(compiler: Path, work: Path, env: dict):
    """隔离 PATH：审计编译过程没有调用系统 clang/ld/lld/codesign/xcrun。"""
    watch = work / "isolated-tools"
    watch.mkdir(parents=True, exist_ok=True)
    log = work / "logs" / "isolated-tools.log"
    if log.exists():
        log.unlink()
    for name in ("clang", "clang++", "ld", "ld64.lld", "codesign", "xcrun", "cc"):
        tool = watch / name
        tool.write_text(f"#!/bin/sh\necho {name} \"$@\" >> \"{log}\"\nexit 127\n",
                        encoding="utf-8")
        tool.chmod(0o755)
    isolated = dict(env)
    isolated["PATH"] = str(watch)
    output = work / "probes" / "probe-isolated"
    result = run([str(compiler), "--backend", "llvm", "--target", TRIPLE, "-O0",
                  "-o", str(output), str(PROBE)], cwd=ROOT, env=isolated)
    log_result(work, "isolated-llvm-build", result)
    if result.returncode != 0:
        raise RuntimeError(f"隔离 PATH 下发射/链接失败：{result.stderr[-2000:]}")
    if log.exists():
        raise RuntimeError("编译过程调用了外部工具：\n" + log.read_text(encoding="utf-8"))
    execution = run([str(output), "probe"], cwd=ROOT, env=isolated)
    if execution.returncode != 0:
        raise RuntimeError(f"隔离 PATH 产物运行失败：{execution.stderr[-800:]}")
    print("隔离 PATH 门：LLVM 发射与 lld 链接全程无 clang/ld/lld/codesign/xcrun 调用")


def project_artifacts():
    """发现 compiler/ 在 Darwin 目标下的预期 LLVM/接口快照集合。"""
    expected = expected_llvm_artifacts(COMPILER)
    if not expected:
        raise RuntimeError("compiler/ 预期 LLVM 快照集合为空")
    return expected


def main() -> int:
    """执行 A→B/C/D 的 O0/O2 固定点、自解析与最终 Darwin 全门。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=default_seed(ROOT),
                        help="Darwin/arm64 入库种子（默认 bin/yh-darwin-arm64）")
    parser.add_argument("--workdir", type=Path,
                        help="证据与候选输出目录（缺省 tmp/f2-8/selfhost-时间戳）")
    parser.add_argument("--jobs", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    parser.add_argument("--self-test", action="store_true",
                        help="只运行快照/代号/目录/Mach-O CPU 失败门自检")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require_darwin_arm64()
    work = args.workdir.resolve() if args.workdir else ROOT / "tmp" / "f2-8" / \
        f"selfhost-{time.strftime('%Y%m%d-%H%M%S')}"
    if work.exists() and any(work.iterdir()):
        raise RuntimeError(f"工作目录非空，拒绝覆盖：{work}")
    work.mkdir(parents=True, exist_ok=True)
    seed = args.seed.resolve()
    seed_digest = verify_seed(seed)
    expected = project_artifacts()
    env = base_environment()
    print(f"F2-8 启动种子：{seed} SHA-256={seed_digest}；目标={TRIPLE}")

    a = build_transition_a(seed, work, env)
    # B/C/D 的最终链接由内嵌 raw lld 完成，需要显式自举标记才会追加固定
    # 桥与 LLVM/lld 静态闭包；普通程序与探针保持不注入。
    build_env = dict(env)
    build_env["YH_LLVM_SELFHOST"] = "1"
    flags_file = Path(build_env.get("YH_LLVM_SELFHOST_FLAGS", ""))
    if not flags_file.is_file():
        raise RuntimeError("缺少自举闭包文件：先运行 make llvm-host"
                           "（tools/llvm-darwin-host.py prepare）")
    frozen = {"A": {"legacy": True}}
    final_candidates = {}
    for level in LEVELS:
        rows = []
        previous = a
        for generation in GENERATIONS:
            current, files, directory, stats = build_candidate(
                previous, generation, level, work, build_env, expected)
            rows.append((generation, files, directory))
            frozen[f"{generation}-O{level}"] = stats
            previous = current
            final_candidates[f"{generation}-O{level}"] = current
        require_fixedpoint(rows, expected)
    (work / "stats.json").write_text(
        json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for level in LEVELS:
        run_probe(final_candidates[f"D-O{level}"], level, work, env)
    final = final_candidates["D-O2"]
    self_parse(final, max(1, args.jobs), work, env)
    run_isolated_llvm_check(final, work, env)
    run_final_gates(final, max(1, args.jobs), work, env)
    print(f"F2-8 全门通过；A/B/C/D、O0/O2 快照与统计保留在 {work}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"F2-8 Darwin 原生自举：{error}", file=sys.stderr)
        raise SystemExit(1)
