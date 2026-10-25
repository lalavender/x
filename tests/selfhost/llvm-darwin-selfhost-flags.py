#!/usr/bin/env python3
"""Darwin 自举闭包门：运行时文件优先、缺失诊断与真实闭包可用性。

背景：种子不再烘焙构建机绝对路径（Zig 式做法——闭包路径属于构建环境）。
本门用当前编译器验证四条契约：
  1. 普通链接不注入闭包；
  2. YH_LLVM_SELFHOST_FLAGS 指向的闭包确实进入链接 argv（坏路径必须出现在诊断里，
     从而证明运行时文件优先于任何编译期常量）；
  3. 闭包文件缺失或为空时给出可操作诊断，而不是静默跳过；
  4. 真实闭包能链完自举链接，产物可运行且不动态依赖 LLVM/lld。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# 工作目录不能放在 tmp/llvm-migration 下：CI 里它是指向宿主闭包缓存的软链，
# 探针的 rmtree/mkdir/链接产物会穿透软链写到共享缓存里（曾导致
# 「无法打开文件 …/tmp/llvm-migration/darwin-selfhost-flags/real/out.yh-tmp.<pid>」）。
WORK = ROOT / "tmp/selfhost-flags"
HOST_RECORD = ROOT / "tmp/llvm-migration/llvm-host-darwin-aarch64/host.json"
TRIPLE = "aarch64-apple-darwin"
SOURCE_TEXT = """module main;

fn main() int {
    printf("selfhost flags ok\\n");
    return 0;
}
"""
EXPECTED = "selfhost flags ok\n"


def require(condition, message):
    """报告确定性的门禁失败，避免依赖可被 -O 移除的 assert。"""
    if not condition:
        raise RuntimeError(message)


def run(label, command, environment, cwd=ROOT, timeout=300):
    """执行一步并把原始输出保存在 tmp，失败时可离线复现。"""
    result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True,
                            text=True, timeout=timeout)
    (WORK / f"{label}.stdout").write_text(result.stdout, encoding="utf-8")
    (WORK / f"{label}.stderr").write_text(result.stderr, encoding="utf-8")
    return result


def main():
    """按四条契约验证闭包文件的优先级、诊断与真实链接。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    require(sys.platform == "darwin", "Darwin 自举闭包门只能在 macOS 上运行")
    require(HOST_RECORD.is_file(),
            "缺少固定 Darwin LLVM host.json：先运行 just llvm-host")
    record = json.loads(HOST_RECORD.read_text(encoding="utf-8"))
    flags_file = ROOT / record.get("selfhost_flags_file", "")
    require(flags_file.is_file(), f"缺少自举闭包文件：{flags_file}")
    sdk_root = Path(os.environ.get("SDKROOT") or record.get("sdk_root", "")).resolve()
    require((sdk_root / "SDKSettings.json").is_file(), f"无效 Darwin SDKROOT：{sdk_root}")
    # 每次门禁从空目录开始：残留的项目/产物会让链接缓存产生虚假命中。
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    compiler = str(Path(args.compiler_path).resolve())
    base = dict(os.environ)
    base["SDKROOT"] = str(sdk_root)
    base["MACOSX_DEPLOYMENT_TARGET"] = "14.0.0"
    base.pop("YH_LLVM_SELFHOST", None)
    base.pop("YH_LLVM_SELFHOST_FLAGS", None)

    def project(label):
        """每个用例独立项目目录：避免链接缓存把上一次结果当成命中。"""
        directory = WORK / label
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "project.toml").write_text(
            f'[project]\nos = "host"\narch = "host"\nname = "{label.replace("-", "_")}"\nsource = "."\n',
            encoding="utf-8")
        (directory / "main.yh").write_text(SOURCE_TEXT, encoding="utf-8")
        return directory, directory / "out"

    def build(label, environment):
        """在项目目录里冷编，闭包只由 YH_LLVM_SELFHOST* 环境决定。"""
        directory, output = project(label)
        output.unlink(missing_ok=True)
        command = [compiler, "--backend", "llvm", "--target", TRIPLE,
                   "build", "-o", str(output)]
        return run(f"{label}-build", command, environment, cwd=directory), output

    # 1) 普通链接：不设置自举标记时不注入闭包，产物行为不变。
    result, plain = build("plain", base)
    require(result.returncode == 0, f"普通链接失败：{result.stderr[-800:]}")
    require(run("plain-run", [str(plain)], base).stdout == EXPECTED,
            "普通产物输出错误")

    # 2) 坏闭包文件：缺失归档的绝对路径必须出现在诊断里，证明运行时文件生效。
    bad_flags = WORK / "bad-flags.txt"
    missing_archive = WORK / "missing-selfhost-archive.a"
    missing_archive.unlink(missing_ok=True)
    bad_flags.write_text(f"-force_load\n{missing_archive}\n", encoding="utf-8")
    env = dict(base, YH_LLVM_SELFHOST="1", YH_LLVM_SELFHOST_FLAGS=str(bad_flags))
    result, _ = build("override", env)
    require(result.returncode != 0, "坏闭包文件没有让链接失败")
    output = result.stdout + result.stderr
    require(str(missing_archive) in output,
            f"闭包文件没有进入链接 argv：{output[-800:]}")

    # 3) 缺失 / 空文件：在链接器之前就给出可操作诊断。
    for label in ("missing", "empty"):
        flags_path = WORK / f"{label}-flags.txt"
        if label == "empty":
            flags_path.write_text("", encoding="utf-8")
        else:
            flags_path.unlink(missing_ok=True)
        env = dict(base, YH_LLVM_SELFHOST="1",
                   YH_LLVM_SELFHOST_FLAGS=str(flags_path))
        result, _ = build(f"flags-{label}", env)
        require(result.returncode != 0, f"{label} 闭包没有让链接失败")
        require("YH_LLVM_SELFHOST_FLAGS" in result.stdout + result.stderr,
                f"{label} 缺少可操作诊断")

    # 4) 真实闭包：自举链接成功，产物可运行且没有动态 LLVM/lld 依赖。
    env = dict(base, YH_LLVM_SELFHOST="1",
               YH_LLVM_SELFHOST_FLAGS=str(flags_file))
    result, good = build("real", env)
    require(result.returncode == 0, f"真实闭包链接失败：{result.stderr[-1200:]}")
    require(run("real-run", [str(good)], base).stdout == EXPECTED,
            "自举产物输出错误")
    dependencies = run("real-deps", ["otool", "-L", str(good)], base).stdout
    require("libLLVM" not in dependencies and "liblld" not in dependencies,
            f"自举产物仍动态依赖 LLVM/lld：{dependencies}")
    print("PASS Darwin 自举闭包：运行时文件优先、缺失诊断、真实闭包可运行")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"FAIL Darwin 自举闭包：{error}")
        raise SystemExit(1)
