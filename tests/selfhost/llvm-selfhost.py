#!/usr/bin/env python3
"""LL10：从 ARM64 种子交叉生成 x64 A，再原生连续自编 B/C/D。"""

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
SEED = ROOT / "bin/yh-linux-arm64"
TRIPLE = "x86_64-unknown-linux-gnu"
PROBE = ROOT / "tests/selfhost/llvm-fixedpoint-probe.yh"
GENERATIONS = ("A", "B", "C", "D")
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))
from selfhost_snapshot_gate import expected_llvm_artifacts
from selfhost_snapshot_gate import llvm_snapshot_errors, save_llvm_snapshot
from selfhost_snapshot_gate import snapshot_errors, verify_seed


def run(command, *, cwd=ROOT, env=None, timeout=1800):
    """执行自举步骤并完整捕获输出，失败时由调用者保留日志。"""
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=timeout)


def require_linux_x64():
    """首期只接受可原生执行 x86_64 ELF 的 Linux 宿主。"""
    if sys.platform != "linux" or platform.machine().lower() not in ("x86_64", "amd64"):
        raise RuntimeError("LL10 首期需要 Linux/x86_64 原生宿主")


def elf_machine(path: Path) -> int:
    """读取 ELF e_machine，要求文件是小端 ELF64。"""
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        raise RuntimeError(f"不是 ELF64 little-endian：{path}")
    return struct.unpack_from("<H", data, 18)[0]


def verify_x64_candidate(path: Path):
    """要求候选为 x64 ELF，不依赖动态 LLVM/lld，也不导出裸 yh 分配器。"""
    if not path.is_file() or elf_machine(path) != 62:
        raise RuntimeError(f"候选不是 x86_64 ELF machine=62：{path}")
    readelf = shutil.which("readelf")
    if readelf is None:
        raise RuntimeError("LL10 门缺少 readelf")
    result = run([readelf, "-d", str(path)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr or f"readelf 失败：{path}")
    if re.search(r"lib(?:LLVM|lld)", result.stdout, re.IGNORECASE):
        raise RuntimeError(f"候选动态依赖 LLVM/lld：{path}")
    nm = shutil.which("nm")
    if nm is None:
        raise RuntimeError("LL10 分配器命名门缺少 nm")
    symbols = run([nm, "-g", str(path)])
    if symbols.returncode != 0:
        raise RuntimeError(symbols.stderr or f"nm 失败：{path}")
    for line in symbols.stdout.splitlines():
        if re.search(r"\s[ABCDGIRSTVW]\s+(?:malloc|free)$", line):
            raise RuntimeError(f"候选把 yh 分配器导出为 libc 名称：{line.strip()}")


def verify_embedded_lld_identity(path: Path):
    """确认候选内嵌固定 SDK 的 lld 版本和编译期链接配置身份。"""
    lock = json.loads((ROOT / "vendor/llvm/sdk.lock.json").read_text(encoding="utf-8"))
    record_path = ROOT / "tmp/llvm-migration/llvm-host-linux-x86_64/host.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    config_path = (ROOT / record["bridge_archive"]).parent / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    expected_version = lock["hosts"]["linux-x86_64"]["lld"]["version"]
    identity = config.get("lld_link_config_sha256", "")
    if record.get("lld_version") != expected_version \
            or config.get("lld_version") != expected_version:
        raise RuntimeError(
            f"lld 身份版本不符：记录={record.get('lld_version')} 固定={expected_version}")
    if config.get("bridge_sha256") != record.get("bridge_sha256"):
        raise RuntimeError("lld 身份配置与宿主身份记录的桥归档不一致")
    if not re.fullmatch(r"[0-9a-f]{64}", identity):
        raise RuntimeError("固定 lld 链接配置缺少 SHA-256 身份")
    if identity.encode("ascii") not in path.read_bytes():
        raise RuntimeError(f"候选未嵌入固定 lld 链接身份：{path}")
    print(f"{path.name} 内嵌 lld {expected_version}，身份 SHA-256={identity}")


def check_build_stats(output: str, label: str):
    """检查编译器项目的每个 stats 行均无后端回退且覆盖数相符。"""
    rows = []
    for line in output.splitlines():
        if line.startswith("yh-stats "):
            rows.append(dict(item.split("=", 1) for item in line.split()[1:]
                             if "=" in item))
    if not rows:
        raise RuntimeError(f"{label} 未输出 LLVM yh-stats")
    checked = sum(int(row.get("checked_functions", "0")) for row in rows)
    emitted = sum(int(row.get("backend_emitted_functions", "0")) for row in rows)
    fallback = sum(int(row.get("fallback_functions", "0")) for row in rows)
    if checked <= 0 or emitted != checked or fallback != 0:
        raise RuntimeError(
            f"{label} LLVM 覆盖门失败：checked={checked} emitted={emitted} fallback={fallback}")


def generation_errors(rows, expected_labels):
    """拒绝代号、顺序或快照目录变化，防止比较错代或同目录自比较。"""
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
    """测试缺 .ll、错接口版本、错 triple、代号与目录误用均被拒绝。"""
    expected = {"llvm/demo-main.ll", "iface/demo-main.s.i",
                "iface/demo-main.s.ct"}
    good = {
        "llvm/demo-main.ll": b'target triple = "x86_64-unknown-linux-gnu"\n',
        "iface/demo-main.s.i": b"// yh-iface v3 arch=arm64 suffix=demo\n",
        "iface/demo-main.s.ct": b"// yh-ctiface v1 arch=arm64 suffix=demo\n",
    }
    assert not llvm_snapshot_errors(good, expected, TRIPLE)
    assert llvm_snapshot_errors({key: value for key, value in good.items()
                                 if not key.endswith(".ll")}, expected, TRIPLE)
    bad_version = good.copy()
    bad_version["iface/demo-main.s.i"] = b"// yh-iface v9 arch=arm64 suffix=demo\n"
    assert llvm_snapshot_errors(bad_version, expected, TRIPLE)
    bad_triple = good.copy()
    bad_triple["llvm/demo-main.ll"] = b'target triple = "aarch64-unknown-linux-gnu"\n'
    assert llvm_snapshot_errors(bad_triple, expected, TRIPLE)
    assert not generation_errors(
        [(name, {}, Path("snapshots") / name) for name in GENERATIONS], GENERATIONS)
    assert generation_errors(
        [("A", {}, Path("snapshots/A")), ("C", {}, Path("snapshots/C")),
         ("C", {}, Path("snapshots/C2")), ("D", {}, Path("snapshots/D"))],
        GENERATIONS)
    assert generation_errors(
        [(name, {}, Path("snapshots/wrong" if name == "C" else name))
         for name in GENERATIONS], GENERATIONS)
    print("LLVM 固定点门自检通过：缺失 .ll、接口版本、target、代号与目录误用均拒绝")


def log_result(work: Path, label: str, result):
    """把每个完整命令的 stdout/stderr 留在本轮工作目录。"""
    logs = work / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"{label}.stdout.log").write_text(result.stdout, encoding="utf-8")
    (logs / f"{label}.stderr.log").write_text(result.stderr, encoding="utf-8")


def build_candidate(compiler: Path, label: str, level: str, work: Path,
                   env: dict[str, str], expected: set[str], seed=False):
    """冷编一代候选，校验 stats/机型/LLVM 接口并立即保存快照。"""
    if (COMPILER / ".build").exists():
        shutil.rmtree(COMPILER / ".build")
    output = work / "candidates" / f"yh-{label}-O{level}"
    output.parent.mkdir(parents=True, exist_ok=True)
    if seed:
        command = [sys.executable, str(ROOT / "tools/seed-build.py"),
                   "--compiler", str(compiler), "--project", str(COMPILER),
                   "--output", str(output), "--llvm-host", "linux-x86_64",
                   "--llvm-mode", "require", "--backend", "llvm", "--target",
                   TRIPLE, "--opt-level", level, "--emit-llvm", "--stats"]
    else:
        command = [str(compiler), "--backend", "llvm", "--target", TRIPLE,
                   f"-O{level}", "--emit-llvm", "--stats", "build", "-o",
                   str(output)]
    result = run(command, cwd=COMPILER, env=env)
    log_result(work, f"{label}-O{level}-build", result)
    if result.returncode != 0:
        raise RuntimeError(
            f"构建 {label}-O{level} 失败（rc={result.returncode}）：\n"
            f"{result.stdout[-5000:]}\n{result.stderr[-5000:]}")
    check_build_stats(result.stdout + result.stderr, f"{label}-O{level}")
    verify_x64_candidate(output)

    build_dir = COMPILER / ".build" / "targets" / TRIPLE / "llvm" / f"O{level}"
    snapshot_dir = work / "snapshots" / f"O{level}" / label
    snapshot = save_llvm_snapshot(build_dir, snapshot_dir)
    errors = llvm_snapshot_errors(snapshot, expected, TRIPLE)
    if errors:
        raise RuntimeError(f"{label}-O{level} 快照门失败：" + "；".join(errors))
    version = run([str(output), "version"], cwd=COMPILER, env=env)
    if version.returncode != 0:
        raise RuntimeError(f"{label}-O{level} 不能原生执行 version：{version.stderr[-1000:]}")
    print(f"{label}-O{level}：ELF machine=62，{len(snapshot)} 个 LLVM/接口产物，原生可执行")
    return output, snapshot, snapshot_dir


def require_fixedpoint(rows, expected_labels, expected):
    """校验连续候选目录正确并逐字节比较其 .ll/.s.i/.s.ct。"""
    errors = generation_errors(rows, expected_labels)
    if errors:
        raise RuntimeError("；".join(errors))
    for (left, left_files, _left_dir), (right, right_files, _right_dir) in zip(rows, rows[1:]):
        differences = snapshot_errors([(left, left_files), (right, right_files)], expected)
        if differences:
            raise RuntimeError(f"{left}→{right} 未达固定点：" + "；".join(differences))
        print(f"{left}→{right} 固定点：{len(expected)} 个 .ll/.s.i/.s.ct 逐字节一致")


def run_probe(compiler: Path, level: str, work: Path, env: dict[str, str]):
    """用指定原生候选编译并运行固定点探针。"""
    output = work / "probes" / f"probe-O{level}-{compiler.name}"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [str(compiler), "--backend", "llvm", "--target", TRIPLE,
               f"-O{level}", "-o", str(output), str(PROBE)]
    result = run(command, cwd=ROOT, env=env)
    log_result(work, f"probe-{level}-{compiler.name}-build", result)
    if result.returncode != 0:
        raise RuntimeError(f"固定点探针构建失败：{result.stderr[-3000:]}")
    verify_x64_candidate(output)
    execution = run([str(output)], cwd=ROOT, env=env)
    if execution.returncode != 0:
        raise RuntimeError(f"固定点探针退出码 {execution.returncode}：{execution.stderr[-1000:]}")
    print(f"{compiler.name} LLVM O{level} 固定点探针：通过")


def self_parse(compiler: Path, jobs: int, work: Path):
    """要求最终原生候选逐个自解析 compiler/ 下所有 .yh 文件。"""
    sources = sorted(COMPILER.rglob("*.yh"))
    env = dict(os.environ)
    env.pop("YH_LLVM_SELFHOST", None)
    def parse_one(source):
        result = run([str(compiler), "--syntax-check", str(source)],
                     cwd=ROOT, env=env, timeout=120)
        return source, result
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        failures = [(source, result) for source, result in pool.map(parse_one, sources)
                    if result.returncode != 0]
    if failures:
        detail = "\n".join(f"{path}: {result.stderr[-500:]}" for path, result in failures[:20])
        raise RuntimeError(f"最终候选自解析失败 {len(failures)}/{len(sources)}：\n{detail}")
    print(f"最终候选自解析：{len(sources)}/{len(sources)}")


def run_language_gates(compiler: Path, level: str, jobs: int, work: Path):
    """用最终原生候选运行语法、语义、模块与项目 LLVM O0/O2 全门。"""
    env = dict(os.environ)
    env.pop("YH_LLVM_SELFHOST", None)
    commands = [
        [sys.executable, str(ROOT / "tests/yh-run/check.py"), "--compiler",
         str(compiler), "--backend", "llvm", "--target", TRIPLE,
         "--opt-level", level, "--quiet", "--jobs", str(jobs),
         "--workdir", str(work / f"yh-run-O{level}")],
        [sys.executable, str(ROOT / "tests/modules/check.py"), "--compiler-path",
         str(compiler), "--backend", "llvm", "--target", TRIPLE,
         "--opt-level", level, "--quiet", "--jobs", str(jobs)],
        [sys.executable, str(ROOT / "tests/modules/build-check.py"),
         "--compiler-path", str(compiler), "--backend", "llvm", "--target",
         TRIPLE, "--opt-level", level, "--jobs", str(max(1, min(jobs, 4))),
         "--workdir", str(work / f"modcheck-O{level}")],
    ]
    for index, command in enumerate(commands):
        result = run(command, cwd=ROOT, env=env)
        log_result(work, f"language-O{level}-{index}", result)
        if result.returncode != 0:
            raise RuntimeError(f"LLVM O{level} 语料门失败：\n"
                               f"{result.stdout[-5000:]}\n{result.stderr[-5000:]}")
        summary = (result.stdout.strip().splitlines() or ["通过"])[-1]
        print(f"LLVM O{level} 语料门：{summary}")


def run_specialized_gates(compiler: Path, jobs: int, work: Path):
    """在最终候选上核验嵌入 lld、LLVM 驱动、缓存及运行时导入面。"""
    commands = [
        [sys.executable, str(ROOT / "tests/selfhost/llvm-lld.py")],
        [sys.executable, str(ROOT / "tests/selfhost/llvm-cache.py"),
         "--compiler-path", str(compiler)],
        [sys.executable, str(ROOT / "tests/selfhost/llvm-driver.py"),
         "--compiler-path", str(compiler)],
        [sys.executable, str(ROOT / "tests/selfhost/runtime-memory.py"),
         "--compiler-path", str(compiler), "--llvm-x64"],
    ]
    env = dict(os.environ)
    env.pop("YH_LLVM_SELFHOST", None)
    for index, command in enumerate(commands):
        result = run(command, cwd=ROOT, env=env)
        log_result(work, f"specialized-{index}", result)
        if result.returncode != 0:
            raise RuntimeError(f"原生 LL9/runtime 专项门失败：\n"
                               f"{result.stdout[-5000:]}\n{result.stderr[-5000:]}")
        summary = (result.stdout.strip().splitlines() or ["通过"])[-1]
        print(f"原生专项：{summary}")


def main() -> int:
    """执行 A→B/C/D 的 O0/O2 固定点、自解析及最终原生全门。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, default=SEED,
                        help="过渡 AArch64 Linux 种子（默认 bin/yh-linux-arm64）")
    parser.add_argument("--workdir", type=Path,
                        help="证据与候选输出目录（缺省 tmp/ll10/selfhost-时间戳）")
    parser.add_argument("--jobs", type=int, default=max(1, min(2, os.cpu_count() or 1)))
    parser.add_argument("--self-test", action="store_true",
                        help="只运行快照/代号/目录失败门自检")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require_linux_x64()
    work = args.workdir.resolve() if args.workdir else ROOT / "tmp" / "ll10" / \
        f"selfhost-{time.strftime('%Y%m%d-%H%M%S')}"
    if work.exists() and any(work.iterdir()):
        raise RuntimeError(f"工作目录非空，拒绝覆盖：{work}")
    work.mkdir(parents=True, exist_ok=True)
    seed = args.seed.resolve()
    seed_digest = verify_seed(seed)
    if elf_machine(seed) != 183:
        raise RuntimeError(f"过渡种子不是 AArch64 ELF machine=183：{seed}")
    seed_version = run([str(seed), "version"], cwd=COMPILER)
    if seed_version.returncode != 0:
        raise RuntimeError(f"AArch64 种子不能由宿主直接执行（需启用 qemu-user/binfmt）："
                           f"{seed_version.stderr[-1000:]}")
    print(f"LL10 启动种子：{seed} SHA-256={seed_digest}；候选目标={TRIPLE}")
    expected = expected_llvm_artifacts(COMPILER)
    if not expected:
        raise RuntimeError("compiler/ 预期 LLVM 快照集合为空")

    base_env = dict(os.environ)
    base_env.pop("YH_LLVM_SELFHOST", None)
    base_env.pop("YH_CC", None)
    a, a_files, a_dir = build_candidate(seed, "A", "0", work, base_env,
                                        expected, seed=True)
    a_row = [("A", a_files, a_dir)]
    verify_x64_candidate(a)

    direct_env = dict(base_env)
    wrapper_dir = work / "tools"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    wrapper = wrapper_dir / "gcc-log"
    link_log = work / "logs" / "external-linker.log"
    # C 源编译（-c/-E/-S）必须走外部 C 驱动；只有最终链接才应使用内嵌 lld。
    # 包装器只记录链接调用，避免把 bridge_stub.c 的正常编译误判为外链回退。
    wrapper.write_text(
        "#!/bin/sh\n"
        "for arg in \"$@\"; do\n"
        "  case \"$arg\" in -c|-E|-S) exec /usr/bin/gcc \"$@\";; esac\n"
        "done\n"
        "printf '%s\\n' \"$*\" >> \"" + str(link_log) + "\"\n"
        "exec /usr/bin/gcc \"$@\"\n",
        encoding="utf-8")
    wrapper.chmod(0o755)
    direct_env["YH_CC"] = str(wrapper)
    direct_env["YH_LLVM_SELFHOST"] = "1"
    # 自举闭包不再烘焙进编译器：B/C/D 的最终链接必须读构建机的运行时闭包文件。
    host_record = json.loads((ROOT / "tmp/llvm-migration/llvm-host-linux-x86_64/host.json")
                             .read_text(encoding="utf-8"))
    closure = host_record.get("selfhost_flags")
    if not closure:
        raise RuntimeError("LLVM x64 宿主身份缺少 selfhost_flags 闭包文件")
    closure_path = (ROOT / closure).resolve()
    if not closure_path.is_file():
        raise RuntimeError(f"LLVM x64 自举闭包文件不存在：{closure_path}")
    direct_env["YH_LLVM_SELFHOST_FLAGS"] = str(closure_path)

    final_candidates = {}
    for level in ("0", "2"):
        rows = list(a_row) if level == "0" else []
        previous = a
        for generation in ("B", "C", "D"):
            current, files, directory = build_candidate(
                previous, generation, level, work, direct_env, expected)
            rows.append((generation, files, directory))
            previous = current
            if generation in ("B", "C", "D"):
                final_candidates[f"{generation}-O{level}"] = current
        # A 是跨目标迁移代；候选固定点从第一次原生自编 B 开始核对。
        fixedpoint_rows = rows[1:] if level == "0" else rows
        require_fixedpoint(fixedpoint_rows, ("B", "C", "D"), expected)

    if link_log.exists():
        raise RuntimeError("B/C/D 自编调用了外部 gcc wrapper："
                           + link_log.read_text(encoding="utf-8")[-2000:])
    print("LL9L-6 链接路径：B/C/D 自编未调用 gcc wrapper，使用内嵌 lld")
    verify_embedded_lld_identity(final_candidates["D-O0"])
    verify_embedded_lld_identity(final_candidates["D-O2"])

    for level in ("0", "2"):
        run_probe(final_candidates[f"D-O{level}"], level, work, base_env)
    final = final_candidates["D-O2"]
    self_parse(final, max(1, args.jobs), work)
    grammar = run([sys.executable, str(ROOT / "tests/yh/check.py"), "--compiler",
                   "--compiler-path", str(final), "--quiet", "--jobs",
                   str(max(1, args.jobs))], cwd=ROOT, env=base_env)
    log_result(work, "final-grammar", grammar)
    if grammar.returncode != 0:
        raise RuntimeError(f"最终原生候选语法门失败：\n{grammar.stdout[-4000:]}\n"
                           f"{grammar.stderr[-4000:]}")
    print((grammar.stdout.strip().splitlines() or ["语法门通过"])[-1])
    run_language_gates(final, "0", max(1, args.jobs), work)
    run_language_gates(final, "2", max(1, args.jobs), work)
    run_specialized_gates(final, max(1, args.jobs), work)
    print(f"LL10 全门通过；A/B/C/D 与 O0/O2 候选、快照、日志保留在 {work}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        print(f"LL10 原生自举：{error}", file=sys.stderr)
        raise SystemExit(1)
