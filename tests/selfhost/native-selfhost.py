#!/usr/bin/env python3
"""tests/selfhost/native-selfhost.py —— 本机全套自举门（0.0.3 滚动自举）。

链路（无 stage0；种子 = 入库的 bin/yh-<平台>-<架构>）：
    bin/yh-<平台>-<架构> build compiler/  → cc2（冷编）
    cc2     build compiler/     → cc3（冷编）
    cc3     build compiler/     → cc4（冷编）
门：
    1. 固定点：候选 cc3/cc4 全部模块 .s/.s.i/.s.ct 逐字节一致；
    2. cc4 自解析：compiler/ 全部 .yh 源文件 --syntax-check 通过；
    3. cc4 语法语料：tests/yh 正例全过、反例全拒；
    4. cc4 运行语料：tests/yh-run 全量（run/fail/pass）。

用法：python3 tests/selfhost/native-selfhost.py [--keep] [--jobs N]
    自解析与两遍语料按 --jobs 并发（缺省 min(8, CPU 核数)）；--workdir 可把
    候选编译器与语料产物放到快速文件系统（cc2/cc3/cc4 会被反复 exec）；
    --skip-corpus 供「同一轮 make test 已跑过等价语料」时省掉重复的一遍。
退出码：全部通过 0。
"""

import argparse
import concurrent.futures
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILER = ROOT / "compiler"
WORK = ROOT / "tmp" / "selfhost"
HOST_DRIVER = ROOT / "tools" / "llvm-host.py"
HOST_DRIVER_DARWIN = ROOT / "tools" / "llvm-darwin-host.py"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))
from selfhost_snapshot_gate import (default_seed, expected_artifacts,
                                    expected_llvm_artifacts,
                                    expected_seed_flat_artifacts,
                                    save_llvm_snapshot, save_snapshot)
from selfhost_snapshot_gate import self_test, snapshot_errors, verify_seed

# 并发上限：自解析与两遍语料都是「一个文件一次编译器进程」，进程启动在
# qemu/容器里约 0.5s，串行跑 86 个源文件与 300 多个用例是纯等待。
DEFAULT_JOBS = max(1, min(8, os.cpu_count() or 1))

# 自举链每一代都要编译 compiler/backend/llvm_bridge.yh，因此各代链接必须能拿到
# 内嵌静态 LLVM 桥。这里复用 tools/llvm-*-host.py 的链接包装器：准备成功就把它的
# 目录前置到子进程 PATH，并把闭包文件经 YH_LLVM_SELFHOST_FLAGS 交给编译器；
# 未准备时，Linux 仍按旧路径继续，Darwin 默认后端是 LLVM，直接给出准备命令。
SHIM_DIR = None
SELFHOST_FLAGS = None
SELFHOST_RUNTIME = None
SELFHOST_LLVM = False
SELFHOST_MANIFEST = False


def host_triple() -> str:
    """返回当前宿主可原生自举的完整目标 triple。"""
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return "aarch64-apple-darwin" if machine in ("arm64", "aarch64") \
            else "x86_64-apple-darwin"
    if machine in ("x86_64", "amd64"):
        return "x86_64-unknown-linux-gnu"
    return "aarch64-unknown-linux-gnu"


def llvm_shim_for_seed(seed: Path):
    """按种子文件名推导 LLVM 宿主架构并返回本机宿主记录；不可用时按平台处理。

    返回的记录含 `shim_dir`（链接包装器目录）与 `selfhost_flags`（每行一个
    链接参数的闭包文件）。闭包路径属于构建机，不再烘焙进种子。
    """
    name = seed.name
    if "darwin" in name:
        host = "darwin-aarch64"
        driver = HOST_DRIVER_DARWIN
    elif "linux" in name:
        driver = HOST_DRIVER
        if "aarch64" in name or "arm64" in name:
            host = "linux-aarch64"
        elif "x64" in name or "x86_64" in name:
            host = "linux-x86_64"
        else:
            return None
    else:
        return None
    request = [sys.executable, str(driver), "shim", "--host", host, "--mode", "auto"]
    result = subprocess.run(request, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"警告：本次自举未链入内嵌 LLVM 桥（{host}）："
              f"{(result.stderr or result.stdout).strip()[-200:]}", file=sys.stderr)
        if sys.platform == "darwin":
            # Darwin 默认后端已是 LLVM，没有闭包就无法继续自举；给出可操作的
            # 准备命令，而不是让链接器在半路报缺少归档。
            raise SystemExit("错误：Darwin 自举需要本机固定 LLVM 闭包；"
                             "先运行 make llvm-host（或 tools/llvm-darwin-host.py prepare）")
        return None
    record = json.loads([line for line in result.stdout.splitlines() if line.strip()][-1])
    print(f"自举链接已接入内嵌 LLVM 桥：host={record['host']} "
          f"bridge={record['bridge_sha256'][:12]}", file=sys.stderr)
    return record


def seed_supports_llvm(seed: Path) -> bool:
    """探测启动种子是否能完整走 LLVM 目标链路（发射、运行时、链接、执行）。

    只看 `--emit-asm` 会误判：旧 Linux/ARM64 种子能发纯标量 IR，却因自带
    x86_64 syscall 运行时无法编出可运行程序。这里用 malloc/printf 探针实际
    链接并运行；不能完整通过时按过渡种子处理：先 legacy 编 cc2，再由 cc2
    以 LLVM 连续自编（与 F2-8 的 A→B/C/D 链一致）。
    """
    probe = WORK / "seed-llvm-probe.yh"
    binary = WORK / "seed-llvm-probe"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(
        "module main;\n\n"
        "fn main() int {\n"
        "    let p *u8 = malloc(8).to_type(*u8);\n"
        "    if (p == 0) { return 1; }\n"
        "    p[0] = 65; p[1] = 0;\n"
        "    printf(\"%s\\n\", p.to_type(*char));\n"
        "    free(p.to_type(*void));\n"
        "    return 0;\n"
        "}\n", encoding="utf-8")
    result = run([str(seed), "--backend", "llvm", "--target", host_triple(),
                  "-o", str(binary), str(probe)])
    if result.returncode != 0 or not binary.is_file():
        return False
    execution = run([str(binary)])
    return execution.returncode == 0 and execution.stdout.strip() == "A"


def compiler_uses_link_manifest() -> bool:
    """compiler/project.toml 是否已迁移到 [link] 归档清单。"""
    try:
        text = (COMPILER / "project.toml").read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(r"^\[link(?:-[a-z0-9-]+)?\]", text, re.MULTILINE) is not None


def run(cmd, cwd=None, shim=False, seed_link=False):
    """执行子命令；shim=True 时把内嵌桥的链接包装器前置到 PATH。

    只有「编译 compiler/ 自身」的调用需要 shim（那一步会链接 llvm_bridge.yh）；
    语料检查、自解析等步骤必须保持原始 PATH，否则会把桥链接强加给语料程序。
    seed_link=True 表示调用方是过渡种子：它只会用自己烘焙的闭包，必须通过
    YH_CC 把最终链接交给本机 shim，才能链入当前构建机的桥（Zig 式配方）。
    """
    environment = dict(os.environ)
    if sys.platform == "darwin" and "SDKROOT" not in environment:
        # 自举闭包末尾带 -lc++，只有宿主 SDK 能解析；优先用固定 SDK 记录里的
        # 真实 SDK，避免调用方每次手工导出 SDKROOT。
        sdk_record = ROOT / "tmp/llvm-migration/darwin-sdk/sdk-darwin-aarch64/host.json"
        if sdk_record.is_file():
            sdk_root = json.loads(sdk_record.read_text(encoding="utf-8")).get("sdk_root")
            if sdk_root and (Path(sdk_root) / "SDKSettings.json").is_file():
                environment["SDKROOT"] = sdk_root
    if sys.platform == "darwin" and "YH_DARWIN_SDK" not in environment:
        bundle = ROOT / "compiler/darwin-sdk"
        if bundle.is_dir():
            environment["YH_DARWIN_SDK"] = str(bundle)
    if shim and SHIM_DIR is not None:
        environment["PATH"] = str(SHIM_DIR) + os.pathsep + environment.get("PATH", "")
    if shim and SELFHOST_LLVM:
        if SELFHOST_MANIFEST:
            environment.pop("YH_LLVM_SELFHOST", None)
            environment.pop("YH_LLVM_SELFHOST_FLAGS", None)
            environment["YH_LINK_MANIFEST_ONLY"] = "1"
            if SELFHOST_RUNTIME is not None:
                environment["YH_LINK_RUNTIME_FLAGS"] = SELFHOST_RUNTIME
        else:
            environment["YH_LLVM_SELFHOST"] = "1"
            if SELFHOST_FLAGS is not None:
                environment["YH_LLVM_SELFHOST_FLAGS"] = SELFHOST_FLAGS
    if seed_link and SHIM_DIR is not None and not SELFHOST_MANIFEST:
        linker = "clang" if sys.platform == "darwin" else "gcc"
        environment["YH_CC"] = str(SHIM_DIR / linker)
    return subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True,
                          text=True, timeout=1800, env=environment)


def build(cc, out, generation, expected, compatible=(), llvm_mode=False,
          seed_link=False):
    """冷编一代，并在共享的 .build 被后续代覆盖前保存其产物。

    llvm_mode=True 时显式选择 LLVM 后端并保存 .ll/接口快照；默认仍按
    宿主默认后端（Linux/x86_64 已是 LLVM，旧平台为 legacy）构建。
    seed_link=True 只用于第一代：过渡种子改用本机 shim 链接，避免它把自己的
    烘焙闭包（含旧桥）带进新编译器。
    """
    bdir = COMPILER / ".build"
    if bdir.exists():
        shutil.rmtree(bdir)
    command = [str(cc)]
    triple = host_triple()
    if llvm_mode:
        command += ["--backend", "llvm", "--target", triple, "--emit-llvm"]
    command += ["build", "-o", str(out)]
    r = run(command, cwd=COMPILER, shim=True, seed_link=seed_link)
    if r.returncode != 0:
        print(f"FAIL 构建 {out.name}:", r.stderr[-400:])
        sys.exit(1)
    if llvm_mode:
        bdir = bdir / "targets" / triple / "llvm" / "O0"
        snapshot = save_llvm_snapshot(bdir, WORK / "snapshots" / generation)
    else:
        snapshot = save_snapshot(bdir, WORK / "snapshots" / generation)
    errors = snapshot_errors([(generation, snapshot)], expected)
    if errors:
        for compatible_expected in compatible:
            if not snapshot_errors([(generation, snapshot)], compatible_expected):
                errors = []
                break
    if errors:
        print(f"FAIL {generation} 产物：", "；".join(errors))
        sys.exit(1)
    return snapshot


def run_fixedpoint_probe(cc, generation):
    """构建并运行覆盖前向调用、聚合浮点与循环的 .yh 自举探针。"""
    source = ROOT / "tests" / "selfhost" / "fixedpoint-probe.yh"
    output = WORK / f"fixedpoint-probe-{generation}"
    result = run([cc, str(source), "-o", str(output)])
    if result.returncode != 0:
        print(f"FAIL {generation} 探针构建：", result.stderr[-400:])
        return False
    result = run([str(output)])
    if result.returncode != 0:
        print(f"FAIL {generation} 探针退出码：{result.returncode}")
        return False
    print(f"{generation} 固定点探针：OK")
    return True


def run_cli_probe(cc):
    """CLI 冒烟：裸调用与坏参数必须打印完整用法并以用法错误码 2 退出。"""
    ok = True
    r = run([cc])
    # 末行必须出现，防止用法输出被截断；信号死亡时 returncode 为负值。
    if r.returncode != 2 or "用法: yh" not in r.stderr \
            or "yh list" not in r.stderr:
        print(f"FAIL cli 裸调用：rc={r.returncode}, stderr 尾部：{r.stderr[-120:]}")
        ok = False
    r = run([cc, "--bogus-flag", "x.yh"])
    if r.returncode != 2 or "用法: yh" not in r.stderr:
        print(f"FAIL cli 坏参数：rc={r.returncode}, stderr 尾部：{r.stderr[-120:]}")
        ok = False
    print("CLI 冒烟（裸调用/坏参数，用法完整且退出码 2）："
          + ("OK" if ok else "FAIL"))
    return ok


def main() -> int:
    """运行种子迁移后的最终双代固定点与语言全量语料。"""
    global SHIM_DIR, WORK
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--seed", type=Path, default=default_seed(ROOT))
    ap.add_argument("--jobs", type=int, default=DEFAULT_JOBS,
                    help=f"自解析与语料并发数（缺省 {DEFAULT_JOBS}；1 为串行）")
    ap.add_argument("--workdir", default=str(WORK),
                    help="候选编译器与探针产物目录（缺省 tmp/selfhost；"
                         "可指向快速文件系统，cc2/cc3/cc4 会被反复 exec）")
    ap.add_argument("--skip-corpus", action="store_true",
                    help="跳过两遍语料（仅当同一轮里 make test 已用等价编译器"
                         "跑过语料时才用；默认不跳过）")
    ap.add_argument("--backend", choices=("auto", "llvm"), default="auto",
                    help="自举链使用的后端；LL12 后 LLVM 是唯一后端，"
                         "legacy 已退役")
    args = ap.parse_args()
    args.jobs = max(1, args.jobs)
    WORK = Path(args.workdir)
    WORK.mkdir(parents=True, exist_ok=True)
    if not self_test():
        print("FAIL 自举快照门自检")
        return 1
    print("自举快照门自检：OK")
    seed = args.seed.resolve()
    try:
        seed_hash = verify_seed(seed)
    except (OSError, ValueError) as error:
        print(f"FAIL 自举种子：{error}")
        return 1
    print(f"自举种子 SHA-256：{seed_hash}")
    global SHIM_DIR, SELFHOST_FLAGS, SELFHOST_RUNTIME, SELFHOST_LLVM, SELFHOST_MANIFEST
    host_record = llvm_shim_for_seed(seed)
    if host_record:
        SHIM_DIR = Path(host_record["shim_dir"])
        flags_file = host_record.get("selfhost_flags")
        if flags_file and Path(flags_file).is_file():
            SELFHOST_FLAGS = str(flags_file)
        runtime_file = host_record.get("selfhost_runtime")
        if runtime_file and Path(runtime_file).is_file():
            SELFHOST_RUNTIME = str(runtime_file)
    SELFHOST_MANIFEST = compiler_uses_link_manifest()
    machine = platform.machine().lower()
    llvm_mode = args.backend == "llvm" or (
        args.backend == "auto" and (
            (sys.platform == "linux" and machine in ("x86_64", "amd64", "aarch64", "arm64"))
            or (sys.platform == "darwin" and machine in ("arm64", "aarch64"))))
    SELFHOST_LLVM = llvm_mode
    if not llvm_mode:
        print("FAIL 该宿主没有 LLVM 自举后端（LL12 已退役 legacy）")
        return 1
    if not seed_supports_llvm(seed):
        print("FAIL 启动种子不支持 LLVM：LL12 已退役 legacy，请先升级种子")
        return 1

    ok = True
    expected = expected_llvm_artifacts(COMPILER)
    seed_flat = expected_seed_flat_artifacts(COMPILER)
    d2 = build(seed, WORK / "cc2", "cc2", expected, llvm_mode=True, seed_link=True)
    d3 = build(WORK / "cc2", WORK / "cc3", "cc3", expected, llvm_mode=True)
    d4 = build(WORK / "cc3", WORK / "cc4", "cc4", expected, llvm_mode=True)
    print(f"cc2/cc3/cc4 构建完成（种子 = {seed}）")

    # 最终候选相邻两代必须达到固定点。
    transition = snapshot_errors([("cc2", d2), ("cc3", d3)], expected)
    if transition:
        print(f"种子迁移后续跑验证：cc2→cc3 有 {len(transition)} 项内容变化")
    errors = snapshot_errors([("cc3", d3), ("cc4", d4)], expected)
    if errors:
        print("FAIL 模块固定点：", "；".join(errors))
        ok = False
    else:
        print(f"模块固定点（候选 cc3→cc4，共 {len(expected)} 个产物）：一致")

    cc4 = str(WORK / "cc4")
    # 2) 最终候选自解析（每个源文件一次进程，并发跑）
    sources = sorted(COMPILER.rglob("*.yh"))

    def self_parse(src):
        """返回自解析失败的源文件名（成功返回 None）。"""
        return None if run([cc4, "--syntax-check", str(src)]).returncode == 0 \
            else src.name

    if args.jobs > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            bad = [name for name in pool.map(self_parse, sources) if name]
    else:
        bad = [name for name in (self_parse(src) for src in sources) if name]
    print(f"cc4 自解析（{len(sources)} 个源文件，并发 {args.jobs}）："
          + ("OK" if not bad else "FAIL " + ",".join(bad)))
    ok = ok and not bad

    # 3) 固定点探针
    ok = run_fixedpoint_probe(cc4, "cc4") and ok

    # 3b) CLI 冒烟
    ok = run_cli_probe(cc4) and ok

    # 4/5) 语法语料与运行语料。--skip-corpus 供「同一轮里 make test 已经用
    # 等价编译器跑过两遍语料」时省掉这 1 分钟；默认不跳过，门不因此变松。
    if args.skip_corpus:
        print("语法语料与运行语料：按 --skip-corpus 跳过（调用方已跑过）")
    else:
        corpus_work = WORK / "yh-run-work"
        r = run(["python3", "tests/yh/check.py", "--compiler",
                 "--compiler-path", cc4, "--quiet", "--jobs", str(args.jobs)])
        print("语法语料：", (r.stdout.strip().splitlines() or ["无输出"])[-1])
        if r.returncode != 0:
            print(r.stdout, r.stderr, sep="\n")
        ok = ok and r.returncode == 0

        r = run(["python3", "tests/yh-run/check.py", "--compiler", cc4,
                 "--quiet", "--jobs", str(args.jobs),
                 "--workdir", str(corpus_work)])
        print("运行语料：", (r.stdout.strip().splitlines() or ["无输出"])[-1])
        if r.returncode != 0:
            print(r.stdout, r.stderr, sep="\n")
        ok = ok and r.returncode == 0

    if not args.keep:
        shutil.rmtree(WORK, ignore_errors=True)
    print("总计：%s" % ("全部通过" if ok else "存在失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
