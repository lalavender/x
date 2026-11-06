#!/usr/bin/env python3
"""F2-10 默认后端门：macOS/ARM64 不带 --backend 时必须走 LLVM。

只验证“默认会话”本身：一个双模块项目在不传任何后端/目标/优化参数时，
统计行应呈现 emitted==checked、fallback=0，产物落在
`.build/targets/aarch64-apple-darwin/llvm/O0`，并可直接运行。
"""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp" / "llvm-migration" / "darwin-default"
FIXTURE = ROOT / "tests/modules/projects/llvmdarwincache"
TRIPLE = "aarch64-apple-darwin"
DEFAULT_HINT = "默认后端不是 LLVM"


def require(condition, message):
    """报告稳定的门禁失败原因，不依赖 assert（Python -O 下不会消失）。"""
    if not condition:
        raise RuntimeError(message)


def run(command, cwd, env):
    """执行命令并完整捕获输出。"""
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=300)


def stats_rows(output):
    """抽取全部 yh-stats 行。"""
    return [dict(item.split("=", 1) for item in line.split()[1:] if "=" in item)
            for line in output.splitlines() if line.startswith("yh-stats ")]


def stat_sum(rows, name):
    """按计数器求和；子进程与父进程的行都要计入。"""
    return sum(int(row.get(name, "0")) for row in rows)


def default_environment():
    """构造默认构建环境：固定 SDK/部署版本，剔除显式后端覆盖。"""
    env = dict(os.environ)
    env.pop("YH_BACKEND", None)
    env.pop("YH_LLVM_SELFHOST", None)
    record = ROOT / "tmp/llvm-migration/darwin-sdk/sdk-darwin-aarch64/host.json"
    if not env.get("SDKROOT") and record.is_file():
        value = json.loads(record.read_text(encoding="utf-8")).get("sdk_root")
        if value:
            env["SDKROOT"] = value
    require(bool(env.get("SDKROOT")), "缺少 SDKROOT，无法验证默认链接")
    env["MACOSX_DEPLOYMENT_TARGET"] = "14.0.0"
    # 这是默认后端/统计门，不是全局缓存门；必须冷编，否则全局 action
    # 命中会让 checked_functions=0，误报“默认后端不是 LLVM”。
    env["YH_CACHE"] = "off"
    return env


def main():
    """默认构建、统计断言、产物地址与运行一次到齐。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    require(compiler.is_file(), f"编译器不存在：{compiler}")
    env = default_environment()

    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE, WORK)

    built = run([str(compiler), "--stats", "build"], WORK, env)
    require(built.returncode == 0,
            f"默认构建失败：{built.stdout[-2000:]}\n{built.stderr[-2000:]}")
    rows = stats_rows(built.stdout + built.stderr)
    checked = stat_sum(rows, "checked_functions")
    emitted = stat_sum(rows, "backend_emitted_functions")
    fallback = stat_sum(rows, "fallback_functions")
    require(rows, "默认构建没有输出 yh-stats，无法确认后端")
    require(checked > 0 and emitted == checked and fallback == 0,
            f"{DEFAULT_HINT}：checked={checked} emitted={emitted} fallback={fallback}")

    artifact = WORK / ".build" / "targets" / TRIPLE / "llvm" / "O0"
    require((artifact / "manifest/link.manifest").is_file()
            and (artifact / "obj/llvmdarwincache-main.o").is_file(),
            f"默认构建没有生成 Darwin LLVM 产物：{artifact}")
    legacy = WORK / ".build" / "asm"
    require(not legacy.exists() or not any(legacy.rglob("*.s")),
            "默认构建仍生成 legacy 汇编")

    executable = WORK / ".build/llvmdarwincache"
    require(executable.is_file(), "默认构建没有产出可执行文件")
    executed = run([str(executable)], WORK, env)
    require(executed.returncode == 0,
            f"默认产物运行失败：rc={executed.returncode}\n{executed.stderr[-800:]}")

    # --emit-llvm/--emit-asm 也必须走默认 LLVM：文本带 Darwin triple，
    # 汇编是 ARM64 机器汇编而不是旧发射器文本。
    probe = str(ROOT / "tests/selfhost/llvm-darwin-fixedpoint.yh")
    ir = run([str(compiler), "--emit-llvm", "--emit-asm", probe], WORK, env)
    require(ir.returncode == 0, f"默认 --emit-llvm 失败：{ir.stderr[-1200:]}")
    require(f'target triple = "{TRIPLE}"' in ir.stdout,
            "默认 LLVM 文本缺少 Darwin triple")
    asm = run([str(compiler), "--emit-asm", probe], WORK, env)
    require(asm.returncode == 0, f"默认 --emit-asm 失败：{asm.stderr[-1200:]}")
    require("_main:" in asm.stdout and "stp" in asm.stdout,
            "默认 --emit-asm 不是 ARM64 机器汇编")

    print(f"PASS 默认后端：checked={checked} emitted={emitted} fallback={fallback}，"
          f"产物 {artifact.relative_to(WORK)} 可运行")


if __name__ == "__main__":
    main()
